# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, '.')
from app.services.purchase_order_service import load_mappings

mappings = load_mappings()
active = [m for m in mappings if m.get('status') == 'active']
pending = [m for m in mappings if m.get('status') == 'pending_mapping']
print(f'总映射: {len(mappings)}个')
print(f'已启用(active): {len(active)}个')
for m in active:
    supplier = m.get('ali1688_supplier', '')[:15]
    score = m.get('sourcing_score', 'N/A')
    print(f'  - {m["woo_sku"]} (id={m["woo_product_id"]}) -> ¥{m["ali1688_cost"]} {supplier} 评分{score}')
print(f'待配置(pending_mapping): {len(pending)}个')
for m in pending:
    keywords = ', '.join(m.get('suggested_search_keywords', [])[:3])
    print(f'  - {m["woo_sku"]} (id={m["woo_product_id"]}) 建议搜索: {keywords}')
