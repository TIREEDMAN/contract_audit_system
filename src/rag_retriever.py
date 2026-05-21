"""RAG 检索器:封装向量相似度检索与阈值过滤。

对应论文 2.2/2.4/4.3.2:Top-3 召回,相似度阈值 0.7。
本实现使用 numpy 批量点积计算余弦相似度,不依赖 Chroma/HNSW,
彻底规避不同平台/版本的二进制兼容性问题。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
from langchain_community.embeddings import HuggingFaceEmbeddings


# 论文 2.4 指定 paraphrase-MiniLM-L6-v2 (384维)
EMBEDDING_MODEL = "sentence-transformers/paraphrase-MiniLM-L6-v2"
DEFAULT_TOP_K = 3
DEFAULT_THRESHOLD = 0.7


@dataclass
class RetrievedDoc:
    content: str
    similarity: float
    source: str = ""

    def to_dict(self) -> dict:
        return {"content": self.content, "similarity": round(self.similarity, 4), "source": self.source}


class RagRetriever:
    """主知识库检索器(法规/模板/判例)。"""

    def __init__(
        self,
        persist_dir: str,
        embedding_model: str = EMBEDDING_MODEL,
        embeddings: Optional[HuggingFaceEmbeddings] = None,
    ):
        self.persist_dir = persist_dir
        self._err: Optional[str] = None
        self.embeddings: Optional[HuggingFaceEmbeddings] = embeddings
        self._matrix: Optional[np.ndarray] = None  # shape [N, dim]
        self._docs: List[dict] = []
        try:
            if self.embeddings is None:
                self.embeddings = HuggingFaceEmbeddings(
                    model_name=embedding_model,
                    model_kwargs={"device": "cpu"},
                )
            self._load()
        except Exception as e:
            self.embeddings = None
            self._err = f"向量库初始化失败:{e}"

    def _load(self) -> None:
        emb_path = os.path.join(self.persist_dir, "embeddings.npy")
        idx_path = os.path.join(self.persist_dir, "index.json")
        if not os.path.exists(emb_path) or not os.path.exists(idx_path):
            self._err = "向量库文件缺失,请先运行 step2_build_rag_db.py 构建。"
            return
        try:
            self._matrix = np.load(emb_path)
            with open(idx_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._docs = data.get("documents", [])
            if self._matrix.shape[0] != len(self._docs):
                self._err = "向量库 embeddings 与索引数量不一致。"
                self._matrix = None
                self._docs = []
        except Exception as e:
            self._err = f"加载向量库失败:{e}"
            self._matrix = None
            self._docs = []

    def is_ready(self) -> bool:
        return self.embeddings is not None and self._matrix is not None

    def error(self) -> Optional[str]:
        return self._err

    def retrieve(
        self,
        query: str,
        k: int = DEFAULT_TOP_K,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> List[RetrievedDoc]:
        if not self.is_ready() or not query.strip():
            return []
        q_vec = np.array(self.embeddings.embed_query(query), dtype=np.float32)
        q_vec = q_vec / (np.linalg.norm(q_vec) + 1e-9)
        sims = self._matrix.dot(q_vec)  # [N]
        top_k = min(k, len(sims))
        top_idx = np.argsort(sims)[::-1][:top_k]
        docs: List[RetrievedDoc] = []
        for i in top_idx:
            sim = float(sims[i])
            if sim < threshold:
                continue
            d = self._docs[i]
            docs.append(
                RetrievedDoc(
                    content=d.get("content", ""),
                    similarity=sim,
                    source=d.get("source", "") or d.get("category", ""),
                )
            )
        return docs

    def to_context(self, docs: List[RetrievedDoc]) -> str:
        if not docs:
            return ""
        lines = []
        for i, d in enumerate(docs, 1):
            tag = f"[{d.source}]" if d.source else ""
            lines.append(f"({i}){tag} 相似度{d.similarity:.2f}\n{d.content}")
        return "\n\n".join(lines)
