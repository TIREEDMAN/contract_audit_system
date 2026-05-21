# -*- coding: utf-8 -*-
"""Test embedding in isolation."""
import sys, os
os.environ.setdefault('HF_ENDPOINT', 'https://hf-mirror.com')
os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')
sys.path.insert(0, 'src')
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

emb = HuggingFaceEmbeddings(model_name='sentence-transformers/paraphrase-MiniLM-L6-v2', model_kwargs={'device':'cpu'})
print('embedding created')
vec = emb.embed_query('违约金为合同总价的50%')
print('embedding len:', len(vec))
print('done')
