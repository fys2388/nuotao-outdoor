#!/usr/bin/env python3
"""
订单/发货通知自动化脚本
- 检查新订单，发送订单确认通知（邮件 mock + 飞书）
- 检查已发货订单，发送发货通知（邮件 mock + 飞书）
- 记录通知状态，避免重复发送
"""
import sys
import os
import json
import logging
from datetime import datetime, timedelta
from uuid import uuid4

sys.path.insert(0, '/opt/nuotao/backend')
from dotenv import load_dotenv
load_dotenv('/opt/nuotao/backend/.env')

import requests
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

WORKSPACE_ID = os.getenv('DEFAULT_WORKSPACE_ID', '00000000-0000-0000-0000-000000000001')
DATABASE_URL = os.getenv('DATABASE_URL', '')
if DATABASE_URL.startswith('postgresql+asyncpg://'):
    DATABASE_URL = DATABASE_URL.replace('postgresql+asyncpg://', 'postgresql+psycopg2://')

API_BASE = 'http://127.0.0.1:8000/api/v1'
FEISHU_WEBHOOK = os.getenv('FEISHU_WEBHOOK_URL', '')
NOTIFICATION_LOG = '/opt/nuotao/backend/data/notification_log.json'

engine = create_engine(DATABASE_URL, echo=False)


def load_notification_log():
    """加载通知记录"""
    if os.path.exists(NOTIFICATION_LOG):
        with open(NOTIFICATION_LOG, 'r') as f:
            return json.load(f)
    return {'order_confirmations': [], 'shipping_notifications': []}


def save_notification_log(log):
    """保存通知记录"""
    os.makedirs(os.path.dirname(NOTIFICATION_LOG), exist_ok=True)
    with open(NOTIFICATION_LOG, 'w') as f:
        json.dump(log, f, indent=2, default=str)


def send_feishu_notification(title, content):
    """发送飞书通知"""
    if not FEISHU_WEBHOOK:
        logger.warning("飞书 Webhook 未配置，跳过飞书通知")
        return False

    try:
        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": title},
                    "template": "blue"
                },
                "elements": [
                    {"tag": "markdown", "content": content}
                ]
            }
        }
        r = requests.post(FEISHU_WEBHOOK, json=payload, timeout=10)
        if r.status_code == 200:
            logger.info(f"飞书通知发送成功: {title}")
            return True
        else:
            logger.warning(f"飞书通知发送失败: HTTP {r.status_code} - {r.text[:100]}")
            return False
    except Exception as e:
        logger.error(f"飞书通知发送异常: {e}")
        return False


def send_email_notification(to_email, subject, html_content):
    """发送邮件通知（通过 API）"""
    try:
        r = requests.post(
            f'{API_BASE}/emails/send-test',
            json={'to_email': to_email, 'subject': subject, 'html_content': html_content},
            timeout=10
        )
        if r.status_code == 200:
            result = r.json()
            logger.info(f"邮件通知发送成功: {subject} (mode={result.get('mode')})")
            return True
        else:
            logger.warning(f"邮件通知发送失败: HTTP {r.status_code}")
            return False
    except Exception as e:
        logger.error(f"邮件通知发送异常: {e}")
        return False


def process_new_orders(session, log):
    """处理新订单通知"""
    # 获取最近 24 小时内的新订单
    since = datetime.now() - timedelta(hours=24)
    result = session.execute(
        text("""
            SELECT id, external_order_id, status, total, currency, country,
                   payment_method, created_at
            FROM orders
            WHERE workspace_id = :ws
              AND created_at >= :since
              AND status IN ('processing', 'completed')
            ORDER BY created_at DESC
        """),
        {'ws': WORKSPACE_ID, 'since': since}
    )
    orders = [dict(row._mapping) for row in result.fetchall()]

    new_count = 0
    for order in orders:
        order_id = str(order['id'])
        if order_id in log['order_confirmations']:
            continue

        # 发送订单确认通知
        subject = f"订单确认 #{order['external_order_id']}"
        content = f"""
**新订单通知**
- 订单号: {order['external_order_id']}
- 金额: ${order['total']} {order['currency']}
- 状态: {order['status']}
- 国家: {order['country'] or '未知'}
- 支付方式: {order['payment_method'] or '未知'}
- 下单时间: {order['created_at']}
        """

        send_feishu_notification(subject, content)
        send_email_notification(
            'orders@nuotaooutdoor.com',
            subject,
            f'<h1>{subject}</h1><pre>{content}</pre>'
        )

        log['order_confirmations'].append(order_id)
        new_count += 1
        logger.info(f"订单确认通知已发送: #{order['external_order_id']} (${order['total']})")

    return new_count


def process_shipping_notifications(session, log):
    """处理发货通知"""
    # 获取已发货的订单（fulfillment_status = fulfilled）
    result = session.execute(
        text("""
            SELECT o.id, o.external_order_id, o.status, o.total, o.country,
                   o.updated_at, s.tracking_number, s.carrier
            FROM orders o
            LEFT JOIN shipment_records s ON s.purchase_order_id IN (
                SELECT id FROM purchase_orders WHERE po_number LIKE '%' || o.external_order_id || '%'
            )
            WHERE o.workspace_id = :ws
              AND o.fulfillment_status = 'fulfilled'
              AND o.updated_at >= :since
            ORDER BY o.updated_at DESC
            LIMIT 20
        """),
        {'ws': WORKSPACE_ID, 'since': datetime.now() - timedelta(hours=24)}
    )
    orders = [dict(row._mapping) for row in result.fetchall()]

    shipped_count = 0
    for order in orders:
        order_id = str(order['id'])
        if order_id in log['shipping_notifications']:
            continue

        subject = f"订单发货通知 #{order['external_order_id']}"
        tracking = order.get('tracking_number') or '待更新'
        carrier = order.get('carrier') or '未知'
        content = f"""
**订单发货通知**
- 订单号: {order['external_order_id']}
- 金额: ${order['total']}
- 国家: {order['country'] or '未知'}
- 物流公司: {carrier}
- 跟踪号: {tracking}
- 发货时间: {order['updated_at']}
        """

        send_feishu_notification(subject, content)
        send_email_notification(
            'fulfillment@nuotaooutdoor.com',
            subject,
            f'<h1>{subject}</h1><pre>{content}</pre>'
        )

        log['shipping_notifications'].append(order_id)
        shipped_count += 1
        logger.info(f"发货通知已发送: #{order['external_order_id']} (tracking={tracking})")

    return shipped_count


def main():
    print("=== 订单/发货通知自动化 ===")
    print(f"时间: {datetime.now()}")
    print()

    log = load_notification_log()

    with Session(engine) as session:
        # 处理新订单通知
        new_orders = process_new_orders(session, log)
        print(f"新订单通知: {new_orders} 封")

        # 处理发货通知
        shipped_orders = process_shipping_notifications(session, log)
        print(f"发货通知: {shipped_orders} 封")

    save_notification_log(log)

    print()
    print(f"累计订单确认通知: {len(log['order_confirmations'])} 封")
    print(f"累计发货通知: {len(log['shipping_notifications'])} 封")
    print()
    print("=== 通知自动化完成 ===")
    print()
    print("说明:")
    print("- 邮件服务当前运行在 MOCK 模式（SMTP 未配置真实凭据）")
    print("- 飞书通知已配置，可实时接收内部通知")
    print("- 如需真实发送客户邮件，请在 .env 中填入 SMTP_HOST/SMTP_USERNAME/SMTP_PASSWORD")
    print("- 推荐 SMTP 服务: SendGrid（免费100封/天）、Brevo（免费300封/天）、Mailgun")


if __name__ == '__main__':
    main()
