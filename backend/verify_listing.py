# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, '.')
from app.services.product_listing_service import (
    create_listing_queue, check_experiment_status, get_listing_status,
    is_restricted, replace_1688_mock_data
)
print("C组服务 import OK")

# 测试管制物品过滤
r1, reason1 = is_restricted('Multi-tool Camping Knife', 'NT-TOOL-001')
print("管制物品检测: 刀具 -> {} ({})".format(r1, reason1))
r2, reason2 = is_restricted('Camping Tent', 'NT-TENT-001')
print("管制物品检测: 帐篷 -> {}".format(r2))

# 实验状态
exp = check_experiment_status()
print("实验状态: {}个进行中, {}个已完成".format(exp['running'], exp['completed']))
for e in exp['experiments']:
    print("  {}: {}, 剩余{}天, 进度{}%, {}".format(
        e['sku'], e['status'], e['days_remaining'], e['progress_pct'], e['action_required']))

# 上架队列测试
from batch_add_products import PRODUCTS as P1
from batch_add_products_v2 import PRODUCTS as P2
all_products = P1 + P2
queue = create_listing_queue(all_products)
print("\n上架队列: 输入{}个, 待上架{}个, 过滤{}个".format(
    queue['total_input'], queue['queued_count'], queue['filtered_count']))
print("被过滤的产品:")
for f in queue['filtered']:
    print("  {}: {}".format(f['sku'], f['reason']))
print("\n待上架产品:")
for q in queue['queued']:
    print("  {}: {} ${}".format(q['sku'], q['name'][:40], q['regular_price']))

# 1688数据替换测试
result = replace_1688_mock_data("test_001", {
    "product_id": "123456",
    "subject": "真实产品",
    "price": "25.80",
    "company_name": "真实供应商",
})
print("\n1688数据替换: success={}, source={}".format(result['success'], result['source']))
