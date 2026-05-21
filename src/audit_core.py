"""审计核心:协调 LLM、规则引擎、检索器、历史库 与 P×L×D 评分。

流程:
1. 主知识库 RAG 检索(法规/模板/判例) + 历史采纳库检索
2. 并行通道
   - LLM:CoT + 小样本 + 自一致性投票(3次)
   - 规则引擎:正则匹配
3. 融合:类型一致直出,不一致以 LLM 为准但标记复核
4. P×L×D 评分 + 三色分级
5. 返回结构化结果(含各阶段耗时)
"""
from __future__ import annotations

import os
import time
from typing import Optional

from historical_kb import HistoricalKB
from llm_client import LlmClient
from prompts import build_system_prompt, build_user_prompt
from rag_retriever import RagRetriever
from risk_model import compute_risk
from rule_engine import RuleEngine


try:
    from langchain_community.embeddings import HuggingFaceEmbeddings
except Exception:
    HuggingFaceEmbeddings = None


class AuditCore:
    def __init__(
        self,
        vector_db_dir: str,
        historical_db_dir: str,
        rules_csv: str,
        embedding_model: str = "sentence-transformers/paraphrase-MiniLM-L6-v2",
    ):
        # 共享嵌入模型实例，避免重复加载（节省内存和启动时间）
        shared_embeddings = None
        if HuggingFaceEmbeddings is not None:
            try:
                shared_embeddings = HuggingFaceEmbeddings(
                    model_name=embedding_model,
                    model_kwargs={"device": "cpu"},
                )
            except Exception:
                pass
        self.retriever = RagRetriever(
            persist_dir=vector_db_dir, embeddings=shared_embeddings
        )
        self.history = HistoricalKB(
            persist_dir=historical_db_dir, embeddings=shared_embeddings
        )
        self.rules = RuleEngine(csv_path=rules_csv)
        self.llm = LlmClient()
        self._system_prompt = build_system_prompt()

    def is_ready(self) -> dict:
        return {
            "llm": self.llm.is_ready(),
            "vector_db": self.retriever.is_ready(),
            "historical_db": self.history.is_ready(),
            "rules_loaded": self.rules.rule_count(),
            "llm_error": self.llm.error(),
            "vector_db_error": self.retriever.error(),
            "historical_db_error": self.history.error(),
            "llm_config": self.llm.get_config(),
        }

    def update_llm_config(self, api_key: str = "", base_url: str = "", model: str = "") -> dict:
        """动态更新 LLM 配置，立即生效。"""
        ok = self.llm.update_config(
            api_key=api_key or None,
            base_url=base_url or None,
            model=model or None,
        )
        return {"success": ok, "config": self.llm.get_config()}

    def audit(self, clause: str) -> dict:
        timing = {}
        clause = (clause or "").strip()
        if not clause:
            return {
                "clause": "",
                "risk_type": "其他",
                "level": "低风险",
                "reason": "条款为空",
                "suggestion": "请提供有效合同文本",
                "formula": "RPN = 0",
                "confidence": 0.0,
                "need_review": False,
                "timing": timing,
            }

        # 1. RAG 检索
        t0 = time.time()
        rag_docs = self.retriever.retrieve(clause, k=3, threshold=0.7)
        law_context = self.retriever.to_context(rag_docs)
        historical_recs = self.history.search(clause, k=3, threshold=0.7)
        historical_context = self.history.to_context(historical_recs)
        timing["retrieve"] = round(time.time() - t0, 3)

        # 2a. 规则引擎
        t1 = time.time()
        rule_hits = self.rules.evaluate(clause)
        timing["rule_engine"] = round(time.time() - t1, 3)

        # 2b. LLM 自一致性
        t2 = time.time()
        user_prompt = build_user_prompt(clause, law_context, historical_context)
        llm_result = self.llm.chat_with_self_consistency(
            system=self._system_prompt,
            user=user_prompt,
            samples=3,
            temperature=0.3,
        )
        timing["llm_audit"] = round(time.time() - t2, 3)

        # 3. 融合
        t3 = time.time()
        fused = self._fuse(llm_result, rule_hits)
        timing["fusion"] = round(time.time() - t3, 3)

        # 4. P×L×D 评分
        t4 = time.time()
        risk = compute_risk(
            clause_text=clause,
            llm_risk_level=fused["risk_level"],
            matched_by_rule=bool(rule_hits),
            need_expert=fused.get("need_review", False),
        )
        timing["scoring"] = round(time.time() - t4, 3)
        timing["total"] = round(sum(timing.values()), 3)

        return {
            "clause": clause,
            "risk_type": fused["risk_type"],
            "risk_level": fused["risk_level"],  # 高/中/低 (LLM 原始)
            "level": risk.level,  # 高风险/中风险/低风险 (P×L×D 映射)
            "reason": fused["reason"],
            "suggestion": fused["suggestion"],
            "confidence": fused.get("confidence", 0.0),
            "need_review": fused.get("need_review", False),
            "voting": fused.get("voting", {}),
            "source": fused.get("source", "llm_only"),
            "law_context": law_context,
            "rag_docs": [d.to_dict() for d in rag_docs],
            "historical_context": historical_context,
            "historical_recs": [r.to_dict() for r in historical_recs],
            "rule_hits": [h.to_dict() for h in rule_hits],
            "risk_score": risk.to_dict(),
            "formula": risk.formula,
            "rpn": risk.rpn,
            "bg_hex": risk.bg_hex,
            "bootstrap": risk.bootstrap,
            "timing": timing,
        }

    def _fuse(self, llm: dict, rule_hits: list) -> dict:
        """LLM + 规则双通道融合。

        - 都判定且类型一致:置信度 +0.1
        - 都判定但类型不一致:以 LLM 为准,标记复核,置信度 ×0.8
        - 只有 LLM:沿用 LLM
        - 只有规则:用规则结果(置信度赋 0.8)
        """
        llm_type = llm.get("risk_type", "其他")
        llm_level = llm.get("risk_level", "中")
        llm_conf = float(llm.get("confidence", 0.5))

        if not rule_hits:
            return {
                "risk_type": llm_type,
                "risk_level": llm_level,
                "reason": llm.get("reason", ""),
                "suggestion": llm.get("suggestion", ""),
                "confidence": llm_conf,
                "need_review": llm.get("need_review", False),
                "voting": llm.get("voting", {}),
                "source": "llm_only",
            }

        order = {"高": 0, "中": 1, "低": 2}
        rule_hits_sorted = sorted(rule_hits, key=lambda h: order.get(h.risk_level, 3))
        top = rule_hits_sorted[0]

        if top.clause_type == llm_type:
            # 一致
            return {
                "risk_type": llm_type,
                "risk_level": _max_level(llm_level, top.risk_level),
                "reason": f"{llm.get('reason', '')}\n(规则 {top.rule_id} 同步命中)",
                "suggestion": llm.get("suggestion", ""),
                "confidence": min(1.0, llm_conf + 0.1),
                "need_review": llm.get("need_review", False),
                "voting": llm.get("voting", {}),
                "source": "agreement",
            }
        else:
            # 不一致
            return {
                "risk_type": llm_type,
                "risk_level": _max_level(llm_level, top.risk_level),
                "reason": (
                    f"{llm.get('reason', '')}\n"
                    f"(规则引擎命中 {top.rule_id}/{top.clause_type},与 LLM 判定不一致,建议人工复核)"
                ),
                "suggestion": llm.get("suggestion", "") + f"\n规则建议:{top.suggestion}",
                "confidence": round(llm_conf * 0.8, 3),
                "need_review": True,
                "voting": llm.get("voting", {}),
                "source": "conflict",
            }


def _max_level(a: str, b: str) -> str:
    order = {"高": 0, "中": 1, "低": 2}
    return min([a, b], key=lambda x: order.get(x, 3))
