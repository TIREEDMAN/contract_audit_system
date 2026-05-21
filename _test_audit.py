# -*- coding: utf-8 -*-
import json, urllib.request

body = json.dumps({"clause": "违约金为合同总价的50%,乙方有权单方面处置甲方所有财产"}, ensure_ascii=False).encode('utf-8')
req = urllib.request.Request(
    'http://127.0.0.1:8000/audit',
    data=body,
    headers={'Content-Type': 'application/json; charset=utf-8'},
    method='POST'
)
resp = urllib.request.urlopen(req, timeout=60)
d = json.loads(resp.read().decode('utf-8'))
for k in ['risk_type', 'level', 'rpn', 'confidence', 'need_review', 'rule_hits', 'voting', 'timing']:
    print(f'{k}: {d.get(k)}')
print('reason:', d.get('reason', '')[:200])
print('suggestion:', d.get('suggestion', '')[:200])
