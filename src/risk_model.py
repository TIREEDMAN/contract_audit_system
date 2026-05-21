"""P×L×D 风险量化模型。对应论文 2.5 节。

- P(发生概率): 1-10, 由 LLM 风险等级 + 条款关键词共同决定
- L(损失程度): L = log10(A * M) + 5, A 标的金额(万元), M 违约乘数
- D(可检测性): D = 11 - E_system - 3*E_expert, 越小越易检测
- RPN = P * L * D, 范围 [1, 1000]
- 等级映射: RPN <= 125 低, 126-343 中, > 343 高 (按 P×L×D 自然分级近似)
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, asdict
from typing import Optional


# ===== P 的关键词权重表 =====
P_KEYWORDS = {
    # 高发概率(7-10)
    "违约金": 8, "赔偿": 7, "解除合同": 7, "单方": 9, "永久": 8,
    "无限": 9, "不予退还": 8, "全部财产": 9, "强制": 8,
    # 中(4-6)
    "通知": 5, "保密": 5, "知识产权": 5, "管辖": 5, "仲裁": 5,
    "争议": 5, "适用法律": 4, "履行期限": 5,
    # 低(1-3)
    "签订": 2, "生效": 2, "标题": 1, "附件": 2, "份数": 1,
}

LEVEL_TO_P = {"高": 9, "中": 5, "低": 2}


def calc_probability(risk_level: str, clause_text: str) -> int:
    """基于风险等级 + 关键词,得到 1-10 的发生概率分。"""
    base = LEVEL_TO_P.get(risk_level, 5)
    bumps = [w for k, w in P_KEYWORDS.items() if k in clause_text]
    if bumps:
        peak = max(bumps)
        score = max(base, min(10, round((base + peak) / 2)))
    else:
        score = base
    return max(1, min(10, int(score)))


_AMOUNT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(万元|万|元|百万|千万|亿)")
_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%|百分之(\d+(?:\.\d+)?)|日万分之(\d+(?:\.\d+)?)")


def _parse_amount_wan(text: str) -> float:
    """从条款文本里提取金额(万元单位),失败返回默认 10 万。"""
    best = 0.0
    for m in _AMOUNT_RE.finditer(text):
        val = float(m.group(1))
        unit = m.group(2)
        if unit == "万元" or unit == "万":
            wan = val
        elif unit == "元":
            wan = val / 10000.0
        elif unit == "百万":
            wan = val * 100
        elif unit == "千万":
            wan = val * 1000
        elif unit == "亿":
            wan = val * 10000
        else:
            wan = val
        best = max(best, wan)
    return best if best > 0 else 10.0


def _parse_multiplier(text: str) -> float:
    """从条款文本里提取违约乘数 M(默认 1)。

    匹配优先级:
    1. 百分比(如50%) → 直接作为乘数
    2. 中文百分比(如百分之五) → 数值作为乘数
    3. 日万分之X → 年化约 X*3.65%, 乘数取年化值
    """
    best = 1.0
    for m in _PCT_RE.finditer(text):
        g1, g2, g3 = m.groups()
        if g1 is not None:
            val = float(g1)
            best = max(best, val)
        elif g2 is not None:
            val = float(g2)
            best = max(best, val)
        elif g3 is not None:
            val = float(g3) * 3.65  # 日万分之5 ≈ 年化18.25%, 乘数为18.25
            best = max(best, val)
    return best


def calc_loss(clause_text: str) -> int:
    """L = log10(A * M) + 5, 截断到 [1, 10]。"""
    a = _parse_amount_wan(clause_text)
    m = _parse_multiplier(clause_text)
    raw = math.log10(max(1.0, a * m)) + 5
    return max(1, min(10, int(round(raw))))


def calc_detectability(matched_by_rule: bool, need_expert: bool) -> int:
    """D = 11 - E_system - 3 * E_expert, 截断到 [1, 10]。

    E_system: 系统(规则引擎)能否自动识别 0/1
    E_expert: 是否需要专家复核 0/1
    """
    e_sys = 1 if matched_by_rule else 0
    e_exp = 1 if need_expert else 0
    raw = 11 - e_sys - 3 * e_exp
    return max(1, min(10, int(raw)))


def rpn_level(rpn: int) -> tuple[str, str, str]:
    """(等级中文, bootstrap class, 背景色 hex)"""
    if rpn <= 125:
        return "低风险", "success", "d1e7dd"
    if rpn <= 343:
        return "中风险", "warning", "fff3cd"
    return "高风险", "danger", "f8d7da"


@dataclass
class RiskScore:
    p: int
    l: int
    d: int
    rpn: int
    level: str
    bootstrap: str
    bg_hex: str
    formula: str

    def to_dict(self) -> dict:
        return asdict(self)


def compute_risk(
    clause_text: str,
    llm_risk_level: str,
    matched_by_rule: bool,
    need_expert: bool,
) -> RiskScore:
    p = calc_probability(llm_risk_level, clause_text)
    l = calc_loss(clause_text)
    d = calc_detectability(matched_by_rule, need_expert)
    rpn = p * l * d
    level, bs, bg = rpn_level(rpn)
    return RiskScore(
        p=p,
        l=l,
        d=d,
        rpn=rpn,
        level=level,
        bootstrap=bs,
        bg_hex=bg,
        formula=f"RPN = P({p}) × L({l}) × D({d}) = {rpn}",
    )
