# -*- coding: utf-8 -*-
"""Test Chroma query in isolation."""
import sys, os
os.environ.setdefault('HF_ENDPOINT', 'https://hf-mirror.com')
os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')
sys.path.insert(0, 'src')
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

emb = HuggingFaceEmbeddings(model_name='sentence-transformers/paraphrase-MiniLM-L6-v2', model_kwargs={'device':'cpu'})
store = Chroma(persist_directory='data/vector_db', embedding_function=emb)
print('chroma created')
results = store.similarity_search_with_score('违约金为合同总价的50%', k=3)
print('results count:', len(results))
for doc, score in results:
    print(score, doc.page_content[:60])
print('done')
