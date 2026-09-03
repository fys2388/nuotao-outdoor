# -*- coding: utf-8 -*-
"""
实际上架脚本：把本地14个非管制产品上架到生产WooCommerce
排除：实验产品(保温水壶)、管制物品(2把刀、丁烷炉)
"""
import sys
import os

# 配置 WooCommerce 密钥
os.environ["WOOCOMMERCE_URL"] = "https://nuotaooutdoor.com"
os.environ["WOOCOMMERCE_CONSUMER_KEY"] = "***REMOVED_WOOCOMMERCE_KEY***"
os.environ["WOOCOMMERCE_CONSUMER_SECRET"] = "***REMOVED_WOOCOMMERCE_SECRET***"

sys.path.insert(0, '.')

from app.services.product_listing_service import (
    create_listing_queue, batch_list_to_woocommerce, check_experiment_status
)
from batch_add_products import PRODUCTS as P1
from batch_add_products_v2 import PRODUCTS as P2

print("=" * 60)
print("产品上架执行脚本")
print("=" * 60)

# 检查实验状态
exp = check_experiment_status()
print("\n实验产品状态:")
for e in exp['experiments']:
    print("  {}: {} (剩余{}天)".format(e['sku'], e['status'], e['days_remaining']))

# 合并本地产品
all_products = P1 + P2
print("\n本地产品总数: {}".format(len(all_products)))

# 创建上架队列（自动过滤管制物品和实验产品）
queue = create_listing_queue(all_products)
print("\n上架队列: 待上架{}个, 过滤{}个".format(queue['queued_count'], queue['filtered_count']))
print("被过滤的产品:")
for f in queue['filtered']:
    print("  - {}: {}".format(f['sku'], f['reason']))

# 执行批量上架
print("\n开始批量上架到 WooCommerce...")
result = batch_list_to_woocommerce(all_products, status="publish", auto_filter=True)

print("\n" + "=" * 60)
print("上架结果")
print("=" * 60)
print("输入: {}个".format(result['total_input']))
print("待上架: {}个".format(result['queued']))
print("过滤: {}个".format(result['filtered']))
print("成功: {}个".format(result['success']))
print("失败: {}个".format(result['failed']))

print("\n成功上架的产品:")
for r in result['results']:
    if r['success']:
        print("  ✅ {} (ID:{}) - {}".format(r['sku'], r['woocommerce_id'], r['name'][:40]))

if result['failed'] > 0:
    print("\n失败的产品:")
    for r in result['results']:
        if not r['success']:
            print("  ❌ {}: {}".format(r['sku'], r.get('error', '未知错误')))

print("\n被过滤的产品:")
for f in result['filtered_items']:
    print("  ⏸️ {}: {}".format(f['sku'], f['reason']))
