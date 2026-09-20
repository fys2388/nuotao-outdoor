#!/usr/bin/env python3
"""
Nuotao AI OS 业务异常预警
每天检查业务数据，发现异常时推送到飞书
预警规则：
1. 订单量异常下降（相比前7天均值下降超过50%）
2. 退款率异常上升（最近7天退款率超过10%）
3. 收入异常下降（相比前7天均值下降超过40%）
"""

import os
import json
import requests
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv('/opt/nuotao/backend/.env')

FEISHU_WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/1035e5f2-8984-44d1-83f4-9fb60f274371"
DATABASE_URL = os.getenv('DATABASE_URL', '')
if DATABASE_URL.startswith('postgresql+asyncpg://'):
    DATABASE_URL = DATABASE_URL.replace('postgresql+asyncpg://', 'postgresql+psycopg2://')

engine = create_engine(DATABASE_URL)

def check_order_volume_drop():
    """检查订单量异常下降"""
    with engine.connect() as conn:
        # 最近1天订单数
        today_orders = conn.execute(text("""
            SELECT COUNT(*) FROM orders
            WHERE created_at >= NOW() - INTERVAL '1 day'
        """)).fetchone()[0]

        # 前7天日均订单数
        avg_orders = conn.execute(text("""
            SELECT COUNT(*) / 7.0 FROM orders
            WHERE created_at >= NOW() - INTERVAL '8 days'
            AND created_at < NOW() - INTERVAL '1 day'
        """)).fetchone()[0]

    if avg_orders > 0:
        drop_rate = (avg_orders - today_orders) / avg_orders * 100
        if drop_rate > 50 and today_orders > 0:
            return {
                "level": "warning",
                "title": "订单量异常下降",
                "message": f"最近1天订单数: {today_orders}单，前7天日均: {avg_orders:.1f}单，下降{drop_rate:.1f}%"
            }
    return None

def check_refund_rate_rise():
    """检查退款率异常上升"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT
                COUNT(*) as total_orders,
                COALESCE(SUM(CASE WHEN refunded_amount > 0 THEN 1 ELSE 0 END), 0) as refund_orders,
                COALESCE(SUM(total), 0) as total_revenue,
                COALESCE(SUM(refunded_amount), 0) as total_refund
            FROM orders
            WHERE created_at >= NOW() - INTERVAL '7 days'
        """)).fetchone()

    if result.total_orders > 0:
        refund_rate = result.refund_orders / result.total_orders * 100
        refund_amount_rate = result.total_refund / result.total_revenue * 100 if result.total_revenue > 0 else 0

        if refund_rate > 10 or refund_amount_rate > 15:
            return {
                "level": "critical",
                "title": "退款率异常上升",
                "message": f"最近7天退款订单率: {refund_rate:.1f}%，退款金额率: {refund_amount_rate:.1f}%（总订单{result.total_orders}单，退款{result.refund_orders}单）"
            }
    return None

def check_revenue_drop():
    """检查收入异常下降"""
    with engine.connect() as conn:
        # 最近1天收入
        today_revenue = conn.execute(text("""
            SELECT COALESCE(SUM(total), 0) FROM orders
            WHERE created_at >= NOW() - INTERVAL '1 day'
        """)).fetchone()[0]

        # 前7天日均收入
        avg_revenue = conn.execute(text("""
            SELECT COALESCE(SUM(total), 0) / 7.0 FROM orders
            WHERE created_at >= NOW() - INTERVAL '8 days'
            AND created_at < NOW() - INTERVAL '1 day'
        """)).fetchone()[0]

    if avg_revenue > 0:
        drop_rate = (avg_revenue - today_revenue) / avg_revenue * 100
        if drop_rate > 40 and today_revenue > 0:
            return {
                "level": "warning",
                "title": "收入异常下降",
                "message": f"最近1天收入: ${today_revenue:,.2f}，前7天日均: ${avg_revenue:,.2f}，下降{drop_rate:.1f}%"
            }
    return None

def check_server_health():
    """检查服务器基础健康状态"""
    alerts = []
    try:
        # 检查后端 API
        response = requests.get("http://127.0.0.1:8000/", timeout=5)
        if response.status_code != 200:
            alerts.append({
                "level": "critical",
                "title": "后端API异常",
                "message": f"后端API返回状态码: {response.status_code}"
            })
    except Exception as e:
        alerts.append({
            "level": "critical",
            "title": "后端API不可达",
            "message": f"无法连接后端API: {str(e)[:100]}"
        })

    return alerts

def send_alert_to_feishu(alerts):
    """发送告警到飞书"""
    if not alerts:
        print("✅ 无异常，无需发送告警")
        return True

    # 按严重程度排序
    alerts.sort(key=lambda x: 0 if x["level"] == "critical" else 1)

    content = "## ⚠️ Nuotao 业务异常预警\n\n"
    content += f"**检查时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"

    for alert in alerts:
        icon = "🔴" if alert["level"] == "critical" else "🟡"
        content += f"### {icon} {alert['title']}\n"
        content += f"{alert['message']}\n\n"

    content += "---\n*由 Nuotao AI OS 自动监控系统生成*"

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "⚠️ Nuotao 业务异常预警"
                },
                "template": "red" if any(a["level"] == "critical" for a in alerts) else "orange"
            },
            "elements": [
                {"tag": "markdown", "content": content}
            ]
        }
    }

    try:
        response = requests.post(FEISHU_WEBHOOK_URL, json=payload, timeout=10)
        result = response.json()
        if result.get("code") == 0 or result.get("StatusCode") == 0:
            print(f"✅ 已发送 {len(alerts)} 条告警到飞书")
            return True
        else:
            print(f"❌ 飞书推送失败: {result}")
            return False
    except Exception as e:
        print(f"❌ 飞书推送异常: {e}")
        return False

def main():
    print(f"=== Nuotao 业务异常预警检查 - {datetime.now()} ===")

    alerts = []

    # 执行各项检查
    print("1. 检查订单量异常下降...")
    alert = check_order_volume_drop()
    if alert:
        alerts.append(alert)
        print(f"   ⚠️ {alert['title']}: {alert['message']}")
    else:
        print("   ✅ 正常")

    print("2. 检查退款率异常上升...")
    alert = check_refund_rate_rise()
    if alert:
        alerts.append(alert)
        print(f"   ⚠️ {alert['title']}: {alert['message']}")
    else:
        print("   ✅ 正常")

    print("3. 检查收入异常下降...")
    alert = check_revenue_drop()
    if alert:
        alerts.append(alert)
        print(f"   ⚠️ {alert['title']}: {alert['message']}")
    else:
        print("   ✅ 正常")

    print("4. 检查服务器健康状态...")
    server_alerts = check_server_health()
    alerts.extend(server_alerts)
    if server_alerts:
        for a in server_alerts:
            print(f"   ⚠️ {a['title']}: {a['message']}")
    else:
        print("   ✅ 正常")

    # 发送告警
    print(f"\n共发现 {len(alerts)} 条异常")
    send_alert_to_feishu(alerts)

    print("=== 检查完成 ===")

if __name__ == "__main__":
    main()
