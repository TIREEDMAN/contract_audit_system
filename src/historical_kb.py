"""历史采纳建议库:独立向量集合,存放用户勾选'采纳'的审计结果。

用户在审计完成后可勾选'采纳'入库,后续相似条款检索时优先参考。
本实现使用 numpy + JSON,不依赖 Chroma,与 RagRetriever 保持一致。
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
from langchain_community.embeddings import HuggingFaceEmbeddings

from rag_retriever import EMBEDDING_MODEL


@dataclass
class HistoricalRecord:
    record_id: str
    clause: str
    risk_type: str
    risk_level: str
    suggestion: str
    similarity: float = 0.0

    def to_dict(self) -> dict:
        return {
            "record_id": self.record_id,
            "clause": self.clause,
            "risk_type": self.risk_type,
            "risk_level": self.risk_level,
            "suggestion": self.suggestion,
            "similarity": round(self.similarity, 4),
        }


class HistoricalKB:
    def __init__(
        self,
        persist_dir: str,
        embedding_model: str = EMBEDDING_MODEL,
        embeddings: Optional[HuggingFaceEmbeddings] = None,
    ):
        os.makedirs(persist_dir, exist_ok=True)
        self.persist_dir = persist_dir
        self._err: Optional[str] = None
        self.embeddings: Optional[HuggingFaceEmbeddings] = embeddings
        self._matrix: Optional[np.ndarray] = None
        self._records: List[dict] = []
        try:
            if self.embeddings is None:
                self.embeddings = HuggingFaceEmbeddings(
                    model_name=embedding_model,
                    model_kwargs={"device": "cpu"},
                )
            self._load()
        except Exception as e:
            self.embeddings = None
            self._err = f"历史库初始化失败:{e}"

    def _load(self) -> None:
        emb_path = os.path.join(self.persist_dir, "embeddings.npy")
        idx_path = os.path.join(self.persist_dir, "index.json")
        if not os.path.exists(emb_path) or not os.path.exists(idx_path):
            return
        try:
            self._matrix = np.load(emb_path)
            with open(idx_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._records = data.get("records", [])
            if self._matrix.shape[0] != len(self._records):
                self._err = "历史库 embeddings 与索引数量不一致"
                self._matrix = None
                self._records = []
        except Exception as e:
            self._err = f"加载历史库失败:{e}"
            self._matrix = None
            self._records = []

    def _save(self) -> None:
        if self._matrix is not None:
            np.save(os.path.join(self.persist_dir, "embeddings.npy"), self._matrix)
        with open(os.path.join(self.persist_dir, "index.json"), "w", encoding="utf-8") as f:
            json.dump({"records": self._records}, f, ensure_ascii=False, indent=2)

    def is_ready(self) -> bool:
        return self.embeddings is not None

    def error(self) -> Optional[str]:
        return self._err

    def add(self, clause: str, risk_type: str, risk_level: str, suggestion: str) -> Optional[str]:
        if not self.embeddings or not clause.strip():
            return None
        rid = str(uuid.uuid4())
        new_rec = {
            "record_id": rid,
            "clause": clause,
            "risk_type": risk_type,
            "risk_level": risk_level,
            "suggestion": suggestion,
            "created_at": int(time.time()),
        }
        self._records.append(new_rec)
        try:
            # 增量编码：只处理新增记录，O(1) 追加，避免 O(n²) 全量重算
            vecs = self.embeddings.embed_documents([clause])
            new_vec = np.array(vecs, dtype=np.float32)
            norms = np.linalg.norm(new_vec, axis=1, keepdims=True)
            new_vec = new_vec / (norms + 1e-9)

            if self._matrix is None or self._matrix.shape[0] == 0:
                self._matrix = new_vec
            else:
                self._matrix = np.vstack([self._matrix, new_vec])

            self._save()
            return rid
        except Exception:
            self._records.pop()
            return None

    def search(self, clause: str, k: int = 3, threshold: float = 0.7) -> List[HistoricalRecord]:
        if not self.is_ready() or self._matrix is None or not clause.strip():
            return []
        q_vec = np.array(self.embeddings.embed_query(clause), dtype=np.float32)
        q_vec = q_vec / (np.linalg.norm(q_vec) + 1e-9)
        sims = self._matrix.dot(q_vec)
        top_k = min(k, len(sims))
        top_idx = np.argsort(sims)[::-1][:top_k]
        out: List[HistoricalRecord] = []
        for i in top_idx:
            sim = float(sims[i])
            if sim < threshold:
                continue
            r = self._records[i]
            out.append(
                HistoricalRecord(
                    record_id=r["record_id"],
                    clause=r["clause"],
                    risk_type=r["risk_type"],
                    risk_level=r["risk_level"],
                    suggestion=r["suggestion"],
                    similarity=sim,
                )
            )
        return out

    def to_context(self, records: List[HistoricalRecord]) -> str:
        if not records:
            return ""
        lines = []
        for i, r in enumerate(records, 1):
            lines.append(
                f"({i}) 相似度{r.similarity:.2f} 风险类型:{r.risk_type} 等级:{r.risk_level}\n"
                f"   原条款:{r.clause[:120]}\n"
                f"   已采纳建议:{r.suggestion}"
            )
        return "\n".join(lines)

    def count(self) -> int:
        return len(self._records)

    def list_recent(self, limit: int = 50) -> List[dict]:
        recs = sorted(self._records, key=lambda x: x.get("created_at", 0), reverse=True)[:limit]
        return [
            {
                "record_id": r["record_id"],
                "clause": r["clause"],
                "risk_type": r["risk_type"],
                "risk_level": r["risk_level"],
                "suggestion": r["suggestion"],
                "created_at": r.get("created_at", 0),
            }
            for r in recs
        ]
