"""构建 RAG 主知识库:遍历 regulations/templates/cases 三个子目录。

对应论文 4.3.2:法规库 + 模板库 + 判例库 三类知识。
输出为 embeddings.npy + index.json,供 RagRetriever 加载。
"""
import json
import os
import shutil

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB_DIR = os.path.join(BASE_DIR, "data", "knowledge_base")
VECTOR_DB_DIR = os.path.join(BASE_DIR, "data", "vector_db")
EMBEDDING_MODEL = "sentence-transformers/paraphrase-MiniLM-L6-v2"

CATEGORIES = {
    "regulations": {"chunk_size": 300, "chunk_overlap": 50},
    "templates": {"chunk_size": 400, "chunk_overlap": 60},
    "cases": {"chunk_size": 500, "chunk_overlap": 80},
}


def collect_files() -> list[tuple[str, str, str]]:
    """返回 (类别, 源文件名, 全文)"""
    items = []
    for cat in CATEGORIES:
        sub = os.path.join(KB_DIR, cat)
        if not os.path.isdir(sub):
            print(f"⚠️  子目录不存在,跳过:{sub}")
            continue
        for fname in os.listdir(sub):
            if not fname.endswith(".txt"):
                continue
            path = os.path.join(sub, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    items.append((cat, fname, f.read()))
            except Exception as e:
                print(f"⚠️  读取失败:{path} → {e}")
    return items


def build():
    print("====== 构建 RAG 知识库(法规/模板/判例) ======")
    items = collect_files()
    if not items:
        print("❌ 未找到任何 .txt 知识源文件。请把法规/模板/判例放入对应子目录后再跑。")
        return

    texts: list[str] = []
    metadatas: list[dict] = []
    for cat, fname, content in items:
        opts = CATEGORIES[cat]
        seps = ["\n\n", "\n", "第.+条", "。", ""] if cat == "regulations" else ["\n\n", "\n", "。", ""]
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=opts["chunk_size"],
            chunk_overlap=opts["chunk_overlap"],
            separators=seps,
        )
        chunks = splitter.split_text(content)
        for chunk in chunks:
            if not chunk.strip():
                continue
            texts.append(chunk)
            metadatas.append({"category": cat, "source": fname})

    print(f"切分完成,共 {len(texts)} 个文本片段。分类统计:")
    from collections import Counter
    cnt = Counter(m["category"] for m in metadatas)
    for k, v in cnt.items():
        print(f"  - {k}: {v}")

    print(f"加载嵌入模型:{EMBEDDING_MODEL}")
    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs={"device": "cpu"},
    )

    print("生成 embeddings...")
    vecs = embeddings.embed_documents(texts)
    matrix = np.array(vecs, dtype=np.float32)
    # 归一化 → 点积即余弦相似度
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    matrix = matrix / (norms + 1e-9)

    # 清理旧库
    if os.path.exists(VECTOR_DB_DIR):
        print(f"清理旧向量库:{VECTOR_DB_DIR}")
        shutil.rmtree(VECTOR_DB_DIR, ignore_errors=True)
    os.makedirs(VECTOR_DB_DIR, exist_ok=True)

    np.save(os.path.join(VECTOR_DB_DIR, "embeddings.npy"), matrix)
    with open(os.path.join(VECTOR_DB_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "embedding_model": EMBEDDING_MODEL,
                "documents": [
                    {"content": t, "category": m["category"], "source": m["source"]}
                    for t, m in zip(texts, metadatas)
                ],
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"[完成] 向量库:{VECTOR_DB_DIR}  文档数:{len(texts)}  维度:{matrix.shape[1]}")


if __name__ == "__main__":
    build()
