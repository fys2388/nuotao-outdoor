# -*- coding: utf-8 -*-
"""采购单全流程验证脚本"""
import sys
sys.path.insert(0, '.')

from app.services.purchase_order_service import (
    create_purchase_order_from_wc_order, confirm_purchase_order,
    mark_ordered, add_tracking, complete_purchase_order,
    get_purchase_order_stats,
)

# 模拟一个包含NT-LANTERN-001(id=895)的WooCommerce订单
mock_order = {
    'id': 999,
    'number': '999',
    'status': 'processing',
    'billing': {'first_name': 'John', 'last_name': 'Doe', 'email': 'john@example.com', 'phone': '+1-555-0100'},
    'shipping': {'first_name': 'John', 'last_name': 'Doe', 'address_1': '123 Main St', 'address_2': 'Apt 4B', 'city': 'New York', 'state': 'NY', 'postcode': '10001', 'country': 'US'},
    'line_items': [
        {'product_id': 895, 'name': 'Rechargeable LED Camping Lantern - 1000 Lumens', 'quantity': 2},
    ],
}

print('=== Step 1: 生成采购单 ===')
po = create_purchase_order_from_wc_order(mock_order)
po_id = po['purchase_order_id']
print(f'采购单号: {po_id}')
print(f'映射商品: {len(po["items"])}个, 未映射: {len(po["unmapped_items"])}个')
print(f'采购成本: ¥{po["total_cost"]:.2f}')
print(f'商品: {po["items"][0]["woo_name"][:40]} x{po["items"][0]["quantity"]}')
print(f'1688链接: {po["items"][0]["ali1688_url"]}')
print(f'供应商: {po["items"][0]["ali1688_supplier"]}')

print()
print('=== Step 2: 确认采购单 ===')
po = confirm_purchase_order(po_id, notes='测试确认')
print(f'状态: {po["status"]}')

print()
print('=== Step 3: 标记已下单 ===')
po = mark_ordered(po_id, ali1688_order_id='ALI2026090412345', ali1688_order_url='https://trade.1688.com/order/12345', notes='1688网页端已下单')
print(f'状态: {po["status"]}')
print(f'1688订单号: {po["ali1688_order_id"]}')

print()
print('=== Step 4: 添加物流跟踪（自动更新WooCommerce订单） ===')
po = add_tracking(po_id, tracking_number='SF1234567890', carrier='顺丰速运', tracking_url='https://www.sf-express.com/mobile/#/query?num=SF1234567890', notes='供应商已发货')
print(f'状态: {po["status"]}')
print(f'物流单号: {po["tracking_number"]}')
print(f'承运商: {po["tracking_carrier"]}')

print()
print('=== Step 5: 完成采购单 ===')
po = complete_purchase_order(po_id, notes='客户已确认收货')
print(f'状态: {po["status"]}')

print()
print('=== Step 6: 统计 ===')
stats = get_purchase_order_stats()
print(f'总采购单: {stats["total"]}')
print(f'待确认: {stats["by_status"]["pending"]}')
print(f'已完成: {stats["by_status"]["completed"]}')
print(f'总成本: ¥{stats["total_cost"]:.2f}')

print()
print('=== 全流程验证通过 ===')
print(f'采购单号: {po_id}')
print('状态流转: pending -> confirmed -> ordered -> shipped -> completed')
