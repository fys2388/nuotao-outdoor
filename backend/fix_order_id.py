#!/usr/bin/env python3
with open('app/api/v1/endpoints/webhooks.py', 'r') as f:
    content = f.read()
content = content.replace('"order_id": None', '"order_id": ""')
content = content.replace('"external_order_id": None', '"external_order_id": ""')
with open('app/api/v1/endpoints/webhooks.py', 'w') as f:
    f.write(content)
print('修改完成')
