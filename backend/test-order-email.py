#!/usr/bin/env python3
"""测试订单确认邮件发送"""
import sys
import asyncio

sys.path.insert(0, '/opt/nuotao/backend')

from app.services.email_service import (
    render_order_confirmation_email,
    get_email_service,
)

# 模拟订单数据
test_order = {
    "id": "TEST-2026-001",
    "order_number": "NUO-1001",
    "customer_name": "Test Customer",
    "customer_email": "fys2388@gmail.com",
    "total": 129.99,
    "currency": "USD",
    "status": "processing",
    "items": [
        {
            "name": "Camping Tent 2-Person",
            "quantity": 1,
            "price": 89.99,
            "image": "https://nuotaooutdoor.com/wp-content/uploads/tent.jpg",
        },
        {
            "name": "Sleeping Bag -10°C",
            "quantity": 1,
            "price": 39.99,
            "image": "https://nuotaooutdoor.com/wp-content/uploads/sleepingbag.jpg",
        },
    ],
    "shipping_address": {
        "first_name": "Test",
        "last_name": "Customer",
        "address_1": "123 Main Street",
        "city": "New York",
        "state": "NY",
        "postcode": "10001",
        "country": "US",
    },
    "payment_method": "Credit Card",
    "created_at": "2026-09-03 10:00:00",
}

async def main():
    print("=" * 60)
    print("测试订单确认邮件发送")
    print("=" * 60)

    # 渲染邮件
    subject, html_body, text_body = render_order_confirmation_email(test_order)
    print(f"\n邮件主题: {subject}")
    print(f"HTML 长度: {len(html_body)} 字符")
    print(f"纯文本长度: {len(text_body)} 字符")

    # 获取邮件服务并发送
    email_service = get_email_service()
    mode = "Mock模式" if email_service.use_mock else "真实SMTP"
    print(f"\n邮件模式: {mode}")
    print(f"SMTP Host: {email_service.smtp_host}")
    print(f"发件人: {email_service.from_name} <{email_service.from_email}>")
    print(f"发送到: {test_order['customer_email']}...")

    result = await email_service.send_email(
        to_email=test_order["customer_email"],
        subject=subject,
        html_content=html_body,
        text_content=text_body,
    )

    print(f"\n发送结果:")
    print(f"  邮件ID: {result.get('email_id')}")
    print(f"  模式: {result.get('mode')}")
    print(f"  成功: {result.get('success')}")
    print(f"  耗时: {result.get('duration_ms')}ms")
    if result.get('error'):
        print(f"  错误: {result['error']}")
    if result.get('mock_file'):
        print(f"  Mock文件: {result['mock_file']}")

    if result.get('success'):
        print("\n✅ 订单确认邮件发送成功！")
        if not email_service.use_mock:
            print("请检查 Gmail 收件箱（包括垃圾邮件文件夹）")
    else:
        print("\n❌ 邮件发送失败")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
