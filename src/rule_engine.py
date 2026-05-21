"""规则引擎:与 LLM 并行的符号通道。对应论文 4.3.3 节。

规则从 CSV 加载,每行定义一条:
  rule_id, clause_type, pattern, risk_level, reason, suggestion

支持正则匹配。命中后返回结构化结果,与 LLM 结果在 audit_core 中融合。
"""
from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RuleHit:
    rule_id: str
    clause_type: str
    risk_level: str
    reason: str
    suggestion: str
    matched_pattern: str

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "risk_type": self.clause_type,
            "risk_level": self.risk_level,
            "reason": self.reason,
            "suggestion": self.suggestion,
            "matched_pattern": self.matched_pattern,
        }


@dataclass
class Rule:
    rule_id: str
    clause_type: str
    pattern: str
    risk_level: str
    reason: str
    suggestion: str
    _regex: Optional[re.Pattern] = field(default=None, repr=False)

    def compile(self) -> None:
        try:
            self._regex = re.compile(self.pattern)
        except re.error:
            self._regex = None

    def match(self, text: str) -> Optional[RuleHit]:
        if self._regex is None:
            return None
        m = self._regex.search(text)
        if not m:
            return None
        return RuleHit(
            rule_id=self.rule_id,
            clause_type=self.clause_type,
            risk_level=self.risk_level,
            reason=self.reason,
            suggestion=self.suggestion,
            matched_pattern=m.group(0)[:80],
        )


class RuleEngine:
    def __init__(self, csv_path: str):
        self.rules: List[Rule] = []
        self.csv_path = csv_path
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.csv_path):
            return
        with open(self.csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rule = Rule(
                    rule_id=row.get("rule_id", "").strip(),
                    clause_type=row.get("clause_type", "").strip(),
                    pattern=row.get("pattern", "").strip(),
                    risk_level=row.get("risk_level", "中").strip(),
                    reason=row.get("reason", "").strip(),
                    suggestion=row.get("suggestion", "").strip(),
                )
                rule.compile()
                if rule._regex is not None:
                    self.rules.append(rule)

    def evaluate(self, clause_text: str) -> List[RuleHit]:
        hits: List[RuleHit] = []
        for rule in self.rules:
            hit = rule.match(clause_text)
            if hit:
                hits.append(hit)
        return hits

    def best_hit(self, clause_text: str) -> Optional[RuleHit]:
        hits = self.evaluate(clause_text)
        if not hits:
            return None
        order = {"高": 0, "中": 1, "低": 2}
        hits.sort(key=lambda h: order.get(h.risk_level, 3))
        return hits[0]

    def rule_count(self) -> int:
        return len(self.rules)

    def reload(self) -> None:
        """热重载规则 CSV。"""
        self.rules = []
        self._load()

    def list_rules(self) -> List[dict]:
        """返回所有规则（用于前端管理）。"""
        return [
            {
                "rule_id": r.rule_id,
                "clause_type": r.clause_type,
                "pattern": r.pattern,
                "risk_level": r.risk_level,
                "reason": r.reason,
                "suggestion": r.suggestion,
            }
            for r in self.rules
        ]

    def add_rule(self, rule_id: str, clause_type: str, pattern: str,
                 risk_level: str, reason: str, suggestion: str) -> bool:
        """新增一条规则并持久化到 CSV。"""
        rule = Rule(
            rule_id=rule_id.strip(),
            clause_type=clause_type.strip(),
            pattern=pattern.strip(),
            risk_level=risk_level.strip(),
            reason=reason.strip(),
            suggestion=suggestion.strip(),
        )
        rule.compile()
        if rule._regex is None:
            return False
        self.rules.append(rule)
        self._save()
        return True

    def update_rule(self, rule_id: str, **kwargs) -> bool:
        """修改指定规则并持久化。"""
        for i, r in enumerate(self.rules):
            if r.rule_id == rule_id:
                # 新 rule_id 不能与现有其他规则冲突
                new_id = kwargs.get("rule_id", r.rule_id).strip()
                if new_id != rule_id and any(x.rule_id == new_id for x in self.rules):
                    return False
                new_rule = Rule(
                    rule_id=new_id,
                    clause_type=kwargs.get("clause_type", r.clause_type).strip(),
                    pattern=kwargs.get("pattern", r.pattern).strip(),
                    risk_level=kwargs.get("risk_level", r.risk_level).strip(),
                    reason=kwargs.get("reason", r.reason).strip(),
                    suggestion=kwargs.get("suggestion", r.suggestion).strip(),
                )
                new_rule.compile()
                if new_rule._regex is None:
                    return False
                self.rules[i] = new_rule
                self._save()
                return True
        return False

    def delete_rule(self, rule_id: str) -> bool:
        """删除指定规则并持久化。"""
        original = len(self.rules)
        self.rules = [r for r in self.rules if r.rule_id != rule_id]
        if len(self.rules) < original:
            self._save()
            return True
        return False

    def _save(self) -> None:
        """将当前规则写回 CSV。"""
        with open(self.csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["rule_id", "clause_type", "pattern", "risk_level", "reason", "suggestion"],
            )
            writer.writeheader()
            for r in self.rules:
                writer.writerow({
                    "rule_id": r.rule_id,
                    "clause_type": r.clause_type,
                    "pattern": r.pattern,
                    "risk_level": r.risk_level,
                    "reason": r.reason,
                    "suggestion": r.suggestion,
                })
