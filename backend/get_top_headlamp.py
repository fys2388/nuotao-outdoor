# -*- coding: utf-8 -*-
import json
with open('sourcing_import_results.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
products = data['products']
products.sort(key=lambda x: x['sourcing_score']['total_score'], reverse=True)
# TOP1和TOP2的完整信息
for idx in [0, 1]:
    p = products[idx]
    print(f'=== 排名{idx+1} ===')
    print('标题:', p['subject'])
    print('ID:', p.get('product_id', ''))
    print('价格:', p.get('price'))
    print('销量:', p.get('sales'))
    print('复购率:', p.get('repurchase_rate'))
    print('供应商:', p.get('supplier'))
    print('链接:', p.get('detail_url'))
    print('评分:', p['sourcing_score']['total_score'])
    print()
