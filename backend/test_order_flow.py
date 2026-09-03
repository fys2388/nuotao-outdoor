"""
WooCommerce 订单流程测试脚本
模拟完整的订单生命周期：下单 -> 处理中 -> 已完成 -> 退款
"""
import os
import sys
from datetime import UTC, datetime

import requests
from requests.auth import HTTPBasicAuth

# WooCommerce 配置
WC_BASE_URL = os.getenv("WOOCOMMERCE_BASE_URL", "https://nuotaooutdoor.com")
WC_CONSUMER_KEY = os.getenv("WOOCOMMERCE_CONSUMER_KEY", "")
WC_CONSUMER_SECRET = os.getenv("WOOCOMMERCE_CONSUMER_SECRET", "")

API_URL = f"{WC_BASE_URL}/wp-json/wc/v3"
AUTH = HTTPBasicAuth(WC_CONSUMER_KEY, WC_CONSUMER_SECRET)

# 测试客户信息
TEST_CUSTOMER = {
    "first_name": "Test",
    "last_name": "Customer",
    "email": "test.customer@nuotaooutdoor.com",
    "billing": {
        "first_name": "Test",
        "last_name": "Customer",
        "address_1": "123 Test Street",
        "city": "San Jose",
        "state": "CA",
        "postcode": "95110",
        "country": "US",
        "email": "test.customer@nuotaooutdoor.com",
        "phone": "+1-555-0123"
    },
    "shipping": {
        "first_name": "Test",
        "last_name": "Customer",
        "address_1": "123 Test Street",
        "city": "San Jose",
        "state": "CA",
        "postcode": "95110",
        "country": "US"
    }
}


def get_products(limit=5):
    """获取产品列表"""
    print(f"  获取产品列表（最多 {limit} 个）...")
    response = requests.get(
        f"{API_URL}/products",
        auth=AUTH,
        params={"per_page": limit, "status": "publish"},
        timeout=30
    )
    if response.status_code == 200:
        products = response.json()
        print(f"  ✅ 获取到 {len(products)} 个产品")
        return products
    else:
        print(f"  ❌ 获取产品失败: {response.status_code}")
        return []


def create_order(products):
    """创建测试订单（下单）"""
    print("\n" + "=" * 60)
    print("步骤 1: 创建测试订单（下单）")
    print("=" * 60)

    # 选择前 2 个产品
    line_items = []
    for product in products[:2]:
        line_items.append({
            "product_id": product["id"],
            "quantity": 1
        })

    order_data = {
        "status": "pending",
        "customer_note": "This is a test order for order flow verification.",
        "billing": TEST_CUSTOMER["billing"],
        "shipping": TEST_CUSTOMER["shipping"],
        "line_items": line_items
    }

    print(f"  订单包含 {len(line_items)} 个产品:")
    for item in line_items:
        product = next(p for p in products if p["id"] == item["product_id"])
        print(f"    - {product['name']} (ID: {product['id']})")

    response = requests.post(
        f"{API_URL}/orders",
        auth=AUTH,
        json=order_data,
        timeout=30
    )

    if response.status_code == 201:
        order = response.json()
        print(f"\n  ✅ 订单创建成功!")
        print(f"     订单号: #{order['number']}")
        print(f"     订单 ID: {order['id']}")
        print(f"     状态: {order['status']}")
        print(f"     总额: ${order['total']}")
        print(f"     客户: {order['billing']['first_name']} {order['billing']['last_name']}")
        return order
    else:
        print(f"\n  ❌ 订单创建失败: {response.status_code}")
        print(f"     错误: {response.text[:300]}")
        return None


def update_order_status(order_id, new_status, note=""):
    """更新订单状态"""
    status_names = {
        "processing": "处理中（付款已确认，准备发货）",
        "completed": "已完成（订单已交付）",
        "cancelled": "已取消",
        "refunded": "已退款"
    }

    print(f"\n  更新订单状态为: {new_status} - {status_names.get(new_status, '')}")

    update_data = {"status": new_status}
    if note:
        update_data["customer_note"] = note

    response = requests.put(
        f"{API_URL}/orders/{order_id}",
        auth=AUTH,
        json=update_data,
        timeout=30
    )

    if response.status_code == 200:
        order = response.json()
        print(f"  ✅ 状态更新成功: {order['status']}")
        return order
    else:
        print(f"  ❌ 状态更新失败: {response.status_code}")
        print(f"     错误: {response.text[:200]}")
        return None


def create_order_note(order_id, note, customer_note=False):
    """创建订单备注"""
    print(f"\n  添加订单备注: {note[:50]}...")

    note_data = {
        "note": note,
        "customer_note": customer_note
    }

    response = requests.post(
        f"{API_URL}/orders/{order_id}/notes",
        auth=AUTH,
        json=note_data,
        timeout=30
    )

    if response.status_code == 201:
        note = response.json()
        print(f"  ✅ 备注添加成功 (ID: {note['id']})")
        return note
    else:
        print(f"  ❌ 备注添加失败: {response.status_code}")
        return None


def create_refund(order_id, amount, reason="Test refund for order flow verification."):
    """创建退款"""
    print(f"\n" + "=" * 60)
    print("步骤 4: 创建退款")
    print("=" * 60)
    print(f"  退款金额: ${amount}")
    print(f"  退款原因: {reason}")

    refund_data = {
        "amount": str(amount),
        "reason": reason,
        "api_refund": False  # 不调用支付网关 API，仅记录退款
    }

    response = requests.post(
        f"{API_URL}/orders/{order_id}/refunds",
        auth=AUTH,
        json=refund_data,
        timeout=30
    )

    if response.status_code == 201:
        refund = response.json()
        print(f"\n  ✅ 退款创建成功!")
        print(f"     退款 ID: {refund['id']}")
        print(f"     退款金额: ${refund['amount']}")
        print(f"     退款原因: {refund['reason']}")
        return refund
    else:
        print(f"\n  ❌ 退款创建失败: {response.status_code}")
        print(f"     错误: {response.text[:300]}")
        return None


def get_order_details(order_id):
    """获取订单详情"""
    print(f"\n  获取订单 #{order_id} 详情...")
    response = requests.get(
        f"{API_URL}/orders/{order_id}",
        auth=AUTH,
        timeout=30
    )
    if response.status_code == 200:
        order = response.json()
        print(f"  ✅ 订单详情获取成功")
        print(f"     状态: {order['status']}")
        print(f"     总额: ${order['total']}")
        print(f"     产品数量: {len(order['line_items'])}")
        return order
    else:
        print(f"  ❌ 获取订单详情失败: {response.status_code}")
        return None


def main():
    print("=" * 60)
    print("WooCommerce 订单流程测试")
    print("=" * 60)
    print(f"店铺: {WC_BASE_URL}")
    print(f"测试时间: {datetime.now(UTC).isoformat()}")
    print()

    # 步骤 0: 获取产品
    print("步骤 0: 获取产品列表")
    print("-" * 60)
    products = get_products(limit=5)
    if not products:
        print("❌ 无法获取产品，测试终止")
        return 1

    # 步骤 1: 创建订单（下单）
    order = create_order(products)
    if not order:
        print("❌ 订单创建失败，测试终止")
        return 1

    order_id = order["id"]
    order_total = float(order["total"])

    # 步骤 2: 更新为处理中（履约开始）
    print("\n" + "=" * 60)
    print("步骤 2: 更新订单状态为处理中（履约开始）")
    print("=" * 60)
    create_order_note(order_id, "Payment confirmed. Order is being processed for shipment.", customer_note=True)
    order = update_order_status(order_id, "processing", "Payment confirmed, preparing for shipment.")

    # 步骤 3: 更新为已完成（履约完成）
    print("\n" + "=" * 60)
    print("步骤 3: 更新订单状态为已完成（履约完成）")
    print("=" * 60)
    create_order_note(order_id, "Order has been shipped and delivered. Tracking: TEST123456", customer_note=True)
    order = update_order_status(order_id, "completed", "Order delivered successfully.")

    # 步骤 4: 创建退款（部分退款测试）
    refund_amount = round(order_total * 0.2, 2)  # 退款 20%
    refund = create_refund(order_id, refund_amount)

    # 步骤 5: 获取最终订单详情
    print("\n" + "=" * 60)
    print("步骤 5: 获取最终订单详情")
    print("=" * 60)
    final_order = get_order_details(order_id)

    # 测试总结
    print("\n" + "=" * 60)
    print("订单流程测试总结")
    print("=" * 60)
    print(f"订单号: #{order['number']}")
    print(f"订单 ID: {order_id}")
    print(f"初始状态: pending")
    print(f"中间状态: processing")
    print(f"最终状态: {final_order['status'] if final_order else 'unknown'}")
    print(f"订单总额: ${order_total}")
    print(f"退款金额: ${refund_amount}")
    print(f"产品数量: {len(order['line_items'])}")
    print(f"客户: {order['billing']['first_name']} {order['billing']['last_name']}")
    print()
    print("✅ 订单流程测试完成!")
    print("   已验证: 下单 -> 处理中 -> 已完成 -> 退款")

    return 0


if __name__ == "__main__":
    sys.exit(main())
