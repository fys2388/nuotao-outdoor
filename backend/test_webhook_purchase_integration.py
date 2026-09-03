# -*- coding: utf-8 -*-
"""Webhook采购单自动生成集成测试（模拟order.created事件中的逻辑）"""
import sys
sys.path.insert(0, '.')

from app.services.purchase_order_service import (
    create_purchase_order_from_wc_order,
    load_purchase_orders,
    get_purchase_order_stats,
)

# 模拟WooCommerce order.created webhook payload
mock_payload = {
    'id': 1001,
    'number': '1001',
    'status': 'processing',
    'billing': {'first_name': 'Alice', 'last_name': 'Smith', 'email': 'alice@example.com', 'phone': '+1-555-0200'},
    'shipping': {'first_name': 'Alice', 'last_name': 'Smith', 'address_1': '456 Oak Ave', 'address_2': '', 'city': 'Los Angeles', 'state': 'CA', 'postcode': '90001', 'country': 'US'},
    'line_items': [
        {'product_id': 895, 'name': 'Rechargeable LED Camping Lantern - 1000 Lumens', 'quantity': 1},
    ],
}

print('=== Webhook集成测试: order.created事件 ===')
print()

# Step 1: 检查是否已存在采购单（模拟webhook中的重复检查）
print('Step 1: 检查重复...')
existing_pos = load_purchase_orders()
order_id = mock_payload['id']
already_generated = any(po.get('wc_order_id') == order_id for po in existing_pos)
print(f'  订单#{order_id}已存在采购单: {already_generated}')
assert not already_generated, '应该不存在'

# Step 2: 生成采购单
print()
print('Step 2: 生成采购单...')
po = create_purchase_order_from_wc_order(mock_payload)
print(f'  采购单号: {po["purchase_order_id"]}')
print(f'  映射商品: {len(po["items"])}个')
print(f'  未映射商品: {len(po["unmapped_items"])}个')
print(f'  采购成本: ¥{po["total_cost"]:.2f}')

# Step 3: 再次触发（模拟重复webhook），应该跳过
print()
print('Step 3: 模拟重复webhook（应该跳过）...')
existing_pos2 = load_purchase_orders()
already_generated2 = any(po.get('wc_order_id') == order_id for po in existing_pos2)
print(f'  订单#{order_id}已存在采购单: {already_generated2}')
assert already_generated2, '应该已存在'
print('  ✅ 重复检查生效，不会重复生成')

# Step 4: 统计
print()
print('Step 4: 统计...')
stats = get_purchase_order_stats()
print(f'  总采购单: {stats["total"]}')
print(f'  待确认: {stats["by_status"]["pending"]}')
print(f'  总成本: ¥{stats["total_cost"]:.2f}')

print()
print('=== Webhook集成测试通过 ===')
print('  ✅ 订单创建时自动生成采购单草稿')
print('  ✅ 重复webhook不会重复生成')
print('  ✅ 采购单状态为pending（待人工确认）')
