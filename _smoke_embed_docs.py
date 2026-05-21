# -*- coding: utf-8 -*-
import os, sys
os.environ.setdefault('HF_ENDPOINT', 'https://hf-mirror.com')
os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')
from langchain_community.embeddings import HuggingFaceEmbeddings
emb = HuggingFaceEmbeddings(model_name='sentence-transformers/paraphrase-MiniLM-L6-v2', model_kwargs={'device':'cpu'})
print('created')
vecs = emb.embed_documents(['hello', 'world'])
print('docs len', len(vecs), len(vecs[0]))
q = emb.embed_query('hello')
print('query len', len(q))
print('done')
