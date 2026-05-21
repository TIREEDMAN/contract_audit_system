# -*- coding: utf-8 -*-
"""Standalone audit smoke test."""
import sys, os
os.environ.setdefault('HF_ENDPOINT', 'https://hf-mirror.com')
os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')
sys.path.insert(0, 'src')
from audit_core import AuditCore

core = AuditCore(
    vector_db_dir='data/vector_db',
    historical_db_dir='data/historical_db',
    rules_csv='src/rules.csv',
)
print('ready:', core.is_ready())
clause = '违约金为合同总价的50%,乙方有权单方面处置甲方所有财产'
print('auditing:', clause[:40])
result = core.audit(clause)
print('risk_type:', result.get('risk_type'))
print('level:', result.get('level'))
print('rpn:', result.get('rpn'))
print('rule_hits:', [h['rule_id'] for h in result.get('rule_hits', [])])
print('timing:', result.get('timing'))
