# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, '.')
from batch_add_products import PRODUCTS as P1
from batch_add_products_v2 import PRODUCTS as P2

print("=== 第一批产品（batch_add_products）===")
for p in P1:
    print("  {}: {} | ${} | 库存{}".format(p['sku'], p['name'][:45], p['regular_price'], p['stock_quantity']))
print("共 {} 个".format(len(P1)))

print()
print("=== 第二批产品（batch_add_products_v2）===")
for p in P2:
    print("  {}: {} | ${} | 库存{}".format(p['sku'], p['name'][:45], p['regular_price'], p['stock_quantity']))
print("共 {} 个".format(len(P2)))
