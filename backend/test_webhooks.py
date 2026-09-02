"""
WooCommerce Webhook 测试脚本
模拟发送各种 Webhook 事件到本地后端，验证处理逻辑
"""
import json
import os
import sys
import time
from datetime import UTC, datetime

import requests

# 后端 API 配置
API_BASE = os.getenv("API_BASE", "http://localhost:8000/api/v1")
WEBHOOK_GENERIC_URL = f"{API_BASE}/webhooks/woocommerce/generic"
WEBHOOK_TEST_URL = f"{API_BASE}/webhooks/woocommerce/test"
WEBHOOK_EVENTS_URL = f"{API_BASE}/webhooks/woocommerce/events"

# WooCommerce Webhook Secret（用于签名验证，测试时可以留空）
WEBHOOK_SECRET = os.getenv("WOOCOMMERCE_WEBHOOK_SECRET", "")


def send_webhook_event(event_type: str, payload: dict, use_test_endpoint: bool = True) -> dict:
    """
    发送 Webhook 事件

    Args:
        event_type: 事件类型（如 order.created）
        payload: 事件负载
        use_test_endpoint: 是否使用测试端点（不验证签名）

    Returns:
        响应结果
    """
    url = WEBHOOK_TEST_URL if use_test_endpoint else WEBHOOK_GENERIC_URL

    headers = {
        "Content-Type": "application/json",
        "X-Wc-Webhook-Event": event_type,
        "X-Wc-Webhook-Id": "test-webhook-001",
        "X-Wc-Webhook-Delivery-Id": f"delivery-{int(time.time())}",
    }

    # 如果使用正式端点且配置了 secret，添加签名
    if not use_test_endpoint and WEBHOOK_SECRET:
        import hashlib
        import hmac
        body = json.dumps(payload).encode("utf-8")
        signature = hmac.new(WEBHOOK_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
        headers["X-Wc-Webhook-Signature"] = signature

    # 测试端点需要在 payload 中包含 event_type
    if use_test_endpoint:
        payload = {"event_type": event_type, **payload}

    try:
        # 禁用系统代理，避免本地请求被代理拦截
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=30,
            proxies={"http": None, "https": None},
        )
        return {
            "status_code": response.status_code,
            "response": response.json() if response.text else {},
            "success": response.status_code in (200, 201),
        }
    except Exception as e:
        return {
            "status_code": 0,
            "response": {"error": str(e)},
            "success": False,
        }


# ============================================
# 测试用例
# ============================================

TEST_CASES = [
    {
        "name": "订单创建事件",
        "event_type": "order.created",
        "payload": {
            "id": 1001,
            "number": "1001",
            "status": "processing",
            "total": "159.98",
            "customer_id": 1,
            "billing": {
                "first_name": "John",
                "last_name": "Doe",
                "email": "john.doe@example.com",
            },
            "line_items": [
                {"id": 1, "name": "Camping Tent", "quantity": 1, "price": "79.99"},
                {"id": 2, "name": "Sleeping Bag", "quantity": 1, "price": "79.99"},
            ],
        },
    },
    {
        "name": "订单更新事件",
        "event_type": "order.updated",
        "payload": {
            "id": 1001,
            "number": "1001",
            "status": "completed",
            "total": "159.98",
            "customer_id": 1,
        },
    },
    {
        "name": "产品创建事件",
        "event_type": "product.created",
        "payload": {
            "id": 2001,
            "sku": "NT-NEW-001",
            "name": "New Outdoor Product",
            "price": "49.99",
            "stock_quantity": 100,
            "status": "publish",
            "categories": [{"id": 15, "name": "Camping"}],
        },
    },
    {
        "name": "产品更新事件",
        "event_type": "product.updated",
        "payload": {
            "id": 2001,
            "sku": "NT-NEW-001",
            "name": "Updated Outdoor Product",
            "price": "54.99",
            "stock_quantity": 85,
            "status": "publish",
        },
    },
    {
        "name": "客户创建事件",
        "event_type": "customer.created",
        "payload": {
            "id": 3001,
            "email": "new.customer@example.com",
            "first_name": "Jane",
            "last_name": "Smith",
            "orders_count": 0,
            "total_spent": "0.00",
            "billing": {"city": "New York", "country": "US"},
        },
    },
    {
        "name": "客户更新事件",
        "event_type": "customer.updated",
        "payload": {
            "id": 3001,
            "email": "jane.smith@example.com",
            "first_name": "Jane",
            "last_name": "Smith",
            "orders_count": 3,
            "total_spent": "254.97",
        },
    },
    {
        "name": "优惠券创建事件",
        "event_type": "coupon.created",
        "payload": {
            "id": 4001,
            "code": "SUMMER20",
            "discount_type": "percent",
            "amount": "20.00",
            "usage_count": 0,
            "date_expires": "2026-09-30T23:59:59",
        },
    },
    {
        "name": "订单笔记创建事件",
        "event_type": "order_note.created",
        "payload": {
            "id": 5001,
            "order_id": 1001,
            "note": "Customer requested expedited shipping.",
            "customer_note": True,
            "author": "system",
            "date_created": datetime.now(UTC).isoformat(),
        },
    },
]


def main():
    print("=" * 70)
    print("WooCommerce Webhook 测试")
    print("=" * 70)
    print(f"API 地址: {API_BASE}")
    print(f"测试端点: {WEBHOOK_TEST_URL}")
    print(f"测试用例数: {len(TEST_CASES)}")
    print(f"测试时间: {datetime.now().isoformat()}")
    print()

    # 1. 先检查支持的事件类型
    print("步骤 1: 检查支持的事件类型")
    print("-" * 70)
    try:
        response = requests.get(WEBHOOK_EVENTS_URL, timeout=10, proxies={"http": None, "https": None})
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 成功获取支持的事件类型列表")
            print(f"   支持的事件总数: {data.get('total_count', 0)}")
            events = data.get('supported_events', {})
            for event_type, event_name in list(events.items())[:5]:
                print(f"   - {event_type}: {event_name}")
            if len(events) > 5:
                print(f"   ... 还有 {len(events) - 5} 个事件")
        else:
            print(f"⚠️ 获取事件类型列表失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 获取事件类型列表异常: {e!s}")
    print()

    # 2. 运行所有测试用例
    print("步骤 2: 运行 Webhook 事件测试")
    print("-" * 70)

    results = []
    for i, test_case in enumerate(TEST_CASES, 1):
        print(f"\n[{i}/{len(TEST_CASES)}] 测试: {test_case['name']}")
        print(f"   事件类型: {test_case['event_type']}")

        result = send_webhook_event(
            event_type=test_case["event_type"],
            payload=test_case["payload"],
            use_test_endpoint=True,
        )

        status = "✅" if result["success"] else "❌"
        print(f"   状态码: {result['status_code']}")
        print(f"   结果: {status}")

        if result["success"]:
            resp_data = result.get("response", {})
            result_data = resp_data.get("result", resp_data)
            print(f"   处理状态: {result_data.get('status', 'N/A')}")
            print(f"   事件名称: {result_data.get('event_name', 'N/A')}")
            print(f"   资源类型: {result_data.get('resource_type', 'N/A')}")
            print(f"   资源 ID: {result_data.get('resource_id', 'N/A')}")

            details = result_data.get("details", {})
            if details:
                print(f"   详情字段: {list(details.keys())}")
        else:
            print(f"   错误: {result.get('response', {}).get('error', 'Unknown error')}")

        results.append({
            "test_case": test_case["name"],
            "event_type": test_case["event_type"],
            "success": result["success"],
            "status_code": result["status_code"],
        })

    # 3. 测试总结
    print("\n" + "=" * 70)
    print("测试总结")
    print("=" * 70)

    success_count = sum(1 for r in results if r["success"])
    fail_count = len(results) - success_count

    print(f"✅ 成功: {success_count}/{len(results)}")
    print(f"❌ 失败: {fail_count}/{len(results)}")
    print()

    print(f"{'测试用例':<25} {'事件类型':<20} {'状态':<8} {'状态码':<8}")
    print("-" * 65)
    for r in results:
        status = "✅" if r["success"] else "❌"
        print(f"{r['test_case']:<25} {r['event_type']:<20} {status:<8} {r['status_code']:<8}")

    # 保存测试结果
    output_file = "webhook_test_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "test_time": datetime.now(UTC).isoformat(),
            "api_base": API_BASE,
            "total_tests": len(results),
            "success_count": success_count,
            "fail_count": fail_count,
            "results": results,
        }, f, indent=2, ensure_ascii=False)

    print(f"\n📄 测试结果已保存到: {output_file}")

    if fail_count > 0:
        print(f"\n⚠️ 有 {fail_count} 个测试失败，请检查上方错误信息")
        return 1
    else:
        print("\n🎉 所有 Webhook 测试通过！")
        return 0


if __name__ == "__main__":
    sys.exit(main())
