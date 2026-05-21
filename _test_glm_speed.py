# -*- coding: utf-8 -*-
import time, sys, os
os.environ.setdefault('HF_ENDPOINT', 'https://hf-mirror.com')
os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')
sys.path.insert(0, 'src')
from llm_client import LlmClient
from prompts import build_system_prompt, build_user_prompt

client = LlmClient()
print('ready:', client.is_ready())

sys_prompt = build_system_prompt()
user_prompt = build_user_prompt('违约金为合同总价的50%,乙方有权单方面处置甲方所有财产', '', '')

for i in range(3):
    t0 = time.time()
    raw = client.chat(sys_prompt, user_prompt, temperature=0.3)
    print(f'call {i+1} elapsed: {time.time()-t0:.2f}s, len={len(raw)}')
    print(raw[:200])
    print('---')
