# -*- coding: utf-8 -*-
"""Test native chromadb create + query."""
import os, sys, shutil
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
sys.path.insert(0, 'src')

from langchain_community.embeddings import HuggingFaceEmbeddings
import chromadb

emb = HuggingFaceEmbeddings(model_name='sentence-transformers/paraphrase-MiniLM-L6-v2', model_kwargs={'device':'cpu'})
test_dir = 'data/_test_native'
if os.path.exists(test_dir):
    shutil.rmtree(test_dir)
client = chromadb.PersistentClient(path=test_dir)
col = client.get_or_create_collection(name='docs', metadata={'hnsw:space': 'cosine'})

texts = ['违约金为合同总价的50%', '双方应永久保密', '疫情属于不可抗力']
metas = [{'category':'regulations','source':'test.txt'} for _ in texts]
vecs = emb.embed_documents(texts)
col.add(ids=['a','b','c'], embeddings=vecs, documents=texts, metadatas=metas)
print('added', col.count())

qvec = emb.embed_query('违约金比例过高怎么办')
res = col.query(query_embeddings=[qvec], n_results=2)
print('queried', len(res['ids'][0]))
print('done')
