# -*- coding: utf-8 -*-
import json, io
from collections import Counter
d = json.load(io.open('wc_products2.json', encoding='utf-8'))
print('WooCommerce产品总数:', len(d))
print('状态分布:', dict(Counter(p['status'] for p in d)))
print()
for p in sorted(d, key=lambda x: x['id']):
    print("  id={} | {} | {} | ${}".format(p['id'], p.get('sku', ''), p['name'][:45], p.get('price')))
