"""修订条款生成器。

对中高风险条款，依据审计结果调用 LLM 生成可直接替换的修订文本。
"""
from __future__ import annotations

import json
import re
from typing import Optional

from llm_client import LlmClient


_REVISION_PROMPT = """你是一位资深合同法律专家。请根据以下审计意见，直接输出修改后的条款文本。

要求：
1. 保持条款编号和标题不变
2. 消除审计发现的风险点
3. 条款应完整、通顺、可直接替换原文
4. 只输出修改后的条款文本，不要解释

原始条款：
{clause}

风险类型：{risk_type}
问题分析：{reason}
修改建议：{suggestion}

请输出修改后的条款："""


class RevisionEngine:
    def __init__(self, llm_client: Optional[LlmClient] = None):
        self.llm = llm_client or LlmClient()

    def revise(self, clause: str, audit: dict) -> str:
        """根据审计结果生成可直接替换的修订条款。

        若 LLM 调用失败或返回异常，回退到 suggestion（若可用）或原文，
        绝不把错误 JSON 暴露给用户。
        """
        if not clause or not audit:
            return clause

        # 审计结果本身就有 LLM 错误 → 直接回退
        if audit.get("_error"):
            return self._fallback(clause, audit)

        prompt = _REVISION_PROMPT.format(
            clause=clause,
            risk_type=audit.get("risk_type", "其他"),
            reason=audit.get("reason", ""),
            suggestion=audit.get("suggestion", ""),
        )

        raw = self.llm.chat(
            system="你是一位合同法律专家，只输出修改后的条款文本，不附加任何解释、标题或 markdown 代码块标记。",
            user=prompt,
            temperature=0.2,
            max_tokens=2048,
        )

        # 检查 LLM 是否返回了错误 JSON
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and parsed.get("_error"):
                return self._fallback(clause, audit)
        except Exception:
            pass

        revised = self._clean(raw)

        # 清洗后过短或为空 → 回退
        if not revised or len(revised) < len(clause) * 0.3:
            return self._fallback(clause, audit)
        return revised

    def _fallback(self, clause: str, audit: dict) -> str:
        """LLM 失败时的回退：优先用 suggestion，其次用原文。"""
        suggestion = audit.get("suggestion", "").strip()
        # suggestion 若只是错误提示语，不采纳
        if suggestion and "稍后重试" not in suggestion and "检查网络" not in suggestion and len(suggestion) > 10:
            return suggestion
        return clause

    @staticmethod
    def _clean(text: str) -> str:
        text = text.strip()
        # 去掉可能的 markdown 围栏
        fence = re.search(r"```(?:\w+)?\s*([\s\S]*?)\s*```", text)
        if fence:
            text = fence.group(1).strip()
        # 去掉常见前缀
        for prefix in ("修改后的条款：", "修改后的条款:", "修订后的条款：", "修订后的条款:", "修改后：", "修改后:"):
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
        return text
