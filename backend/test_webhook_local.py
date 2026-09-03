"""测试 WooCommerce Webhook 端点"""
import hashlib
import hmac
import json
import urllib.request

WEBHOOK_URL = "http://localhost:8000/api/v1/webhooks/woocommerce"
WEBHOOK_SECRET = "dev-webhook-secret-change-me"  # 配置文件中的默认值

# 模拟 WooCommerce 订单数据
order_payload = {
    "id": 12345,
    "status": "processing",
    "currency": "USD",
    "total": "79.98",
    "customer_id": 0,
    "billing": {
        "first_name": "John",
        "last_name": "Doe",
        "email": "john@example.com",
        "phone": "+1234567890",
        "address_1": "123 Main St",
        "city": "New York",
        "state": "NY",
        "postcode": "10001",
        "country": "US",
    },
    "shipping": {
        "first_name": "John",
        "last_name": "Doe",
        "address_1": "123 Main St",
        "city": "New York",
        "state": "NY",
        "postcode": "10001",
        "country": "US",
    },
    "line_items": [
        {
            "id": 1,
            "product_id": 100,
            "name": "Camping Tent 2P",
            "quantity": 1,
            "price": "59.99",
            "total": "59.99",
        },
        {
            "id": 2,
            "product_id": 101,
            "name": "Sleeping Bag",
            "quantity": 1,
            "price": "19.99",
            "total": "19.99",
        },
    ],
    "date_created": "2026-09-02T09:00:00",
    "date_modified": "2026-09-02T09:00:00",
}

body = json.dumps(order_payload).encode("utf-8")
signature = hmac.new(
    WEBHOOK_SECRET.encode("utf-8"),
    body,
    hashlib.sha256,
).hexdigest()

req = urllib.request.Request(
    WEBHOOK_URL,
    data=body,
    headers={
        "Content-Type": "application/json",
        "X-Wc-Webhook-Signature": signature,
        "X-Wc-Webhook-Topic": "order.created",
        "X-Wc-Webhook-Resource": "order",
        "X-Wc-Webhook-Event": "created",
    },
    method="POST",
)

try:
    with urllib.request.urlopen(req, timeout=10) as response:
        print(f"✅ Webhook 接收成功")
        print(f"   状态码: {response.status}")
        print(f"   响应: {response.read().decode('utf-8')}")
except urllib.error.HTTPError as e:
    print(f"❌ Webhook 接收失败")
    print(f"   状态码: {e.code}")
    print(f"   响应: {e.read().decode('utf-8')}")
except Exception as e:
    print(f"❌ 请求异常: {e}")
