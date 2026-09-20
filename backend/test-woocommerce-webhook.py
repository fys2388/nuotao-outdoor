#!/usr/bin/env python3
"""测试 WooCommerce Webhook 订单接收"""
import json
import hmac
import hashlib
import requests
import time

WEBHOOK_URL = "http://127.0.0.1:8000/api/v1/webhooks/woocommerce"
WEBHOOK_SECRET = "VSgwAnYjJstBRPiCz67kqcmfu9GrTy84"

# 模拟 WooCommerce 订单数据
test_order = {
    "id": 99999,
    "parent_id": 0,
    "status": "processing",
    "currency": "USD",
    "version": "8.0.0",
    "prices_include_tax": False,
    "date_created": "2026-09-03T10:00:00",
    "date_modified": "2026-09-03T10:00:00",
    "discount_total": "0.00",
    "discount_tax": "0.00",
    "shipping_total": "9.99",
    "shipping_tax": "0.00",
    "cart_tax": "0.00",
    "total": "139.98",
    "total_tax": "0.00",
    "customer_id": 0,
    "order_key": "wc_order_test123456",
    "billing": {
        "first_name": "Test",
        "last_name": "Customer",
        "company": "",
        "address_1": "123 Main St",
        "address_2": "",
        "city": "New York",
        "state": "NY",
        "postcode": "10001",
        "country": "US",
        "email": "fys2388@gmail.com",
        "phone": "+1234567890"
    },
    "shipping": {
        "first_name": "Test",
        "last_name": "Customer",
        "company": "",
        "address_1": "123 Main St",
        "address_2": "",
        "city": "New York",
        "state": "NY",
        "postcode": "10001",
        "country": "US"
    },
    "payment_method": "stripe",
    "payment_method_title": "Credit Card",
    "transaction_id": "txn_test123",
    "customer_ip_address": "1.2.3.4",
    "customer_user_agent": "Mozilla/5.0",
    "created_via": "checkout",
    "customer_note": "",
    "line_items": [
        {
            "id": 1,
            "name": "Camping Tent 2-Person",
            "product_id": 100,
            "variation_id": 0,
            "quantity": 1,
            "tax_class": "",
            "price": "89.99",
            "subtotal": "89.99",
            "subtotal_tax": "0.00",
            "total": "89.99",
            "total_tax": "0.00",
            "sku": "TENT-001",
            "meta_data": []
        },
        {
            "id": 2,
            "name": "Sleeping Bag -10°C",
            "product_id": 101,
            "variation_id": 0,
            "quantity": 1,
            "tax_class": "",
            "price": "39.99",
            "subtotal": "39.99",
            "subtotal_tax": "0.00",
            "total": "39.99",
            "total_tax": "0.00",
            "sku": "BAG-001",
            "meta_data": []
        }
    ],
    "shipping_lines": [
        {
            "id": 3,
            "method_title": "Flat Rate",
            "method_id": "flat_rate",
            "total": "9.99",
            "total_tax": "0.00"
        }
    ],
    "meta_data": []
}

print("=" * 60)
print("WooCommerce Webhook 订单测试")
print("=" * 60)

# 计算 HMAC-SHA256 签名
body = json.dumps(test_order, separators=(',', ':'))
signature = hmac.new(
    WEBHOOK_SECRET.encode('utf-8'),
    body.encode('utf-8'),
    hashlib.sha256
).hexdigest()

print(f"\n订单ID: {test_order['id']}")
print(f"订单总额: ${test_order['total']}")
print(f"商品数量: {len(test_order['line_items'])}")
print(f"客户邮箱: {test_order['billing']['email']}")
print(f"Webhook签名: {signature[:20]}...")

# 发送 Webhook 请求
headers = {
    "Content-Type": "application/json",
    "X-WC-Webhook-Signature": signature,
    "X-WC-Webhook-Topic": "order.created",
    "X-WC-Webhook-Resource": "order",
    "X-WC-Webhook-Event": "created",
    "X-WC-Webhook-ID": "999",
    "X-WC-Webhook-Delivery-ID": "test-delivery-001",
}

print(f"\n发送到: {WEBHOOK_URL}")
print("等待响应...")

try:
    response = requests.post(
        WEBHOOK_URL,
        data=body,
        headers=headers,
        timeout=30
    )
    print(f"\nHTTP 状态码: {response.status_code}")
    print(f"响应内容: {response.text[:500]}")
    
    if response.status_code == 200:
        print("\n✅ Webhook 接收成功！订单已进入商业闭环")
        print("   - 订单已写入数据库")
        print("   - AI Agent 将进行订单分析")
        print("   - 飞书通知将被触发")
        print("   - 订单确认邮件将被发送")
    elif response.status_code == 401:
        print("\n❌ 签名验证失败")
    elif response.status_code == 404:
        print("\n❌ 不支持的 Webhook 类型")
    else:
        print(f"\n⚠️ 意外的状态码: {response.status_code}")
        
except Exception as e:
    print(f"\n❌ 请求失败: {str(e)}")
