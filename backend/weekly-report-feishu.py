#!/usr/bin/env python3
"""
Nuotao AI OS 经营周报生成与推送
每周一早上自动生成上周经营数据并推送到飞书
"""

import os
import json
import requests
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# 加载环境变量
load_dotenv('/opt/nuotao/backend/.env')

# 配置
FEISHU_WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/1035e5f2-8984-44d1-83f4-9fb60f274371"
DATABASE_URL = os.getenv('DATABASE_URL', '')
if DATABASE_URL.startswith('postgresql+asyncpg://'):
    DATABASE_URL = DATABASE_URL.replace('postgresql+asyncpg://', 'postgresql+psycopg2://')

engine = create_engine(DATABASE_URL)

def get_weekly_data():
    """获取上周经营数据"""
    # 计算上周日期范围
    today = datetime.now()
    last_monday = (today - timedelta(days=today.weekday() + 7))
    last_sunday = last_monday + timedelta(days=6)
    start_date = last_monday.strftime('%Y-%m-%d')
    end_date = last_sunday.strftime('%Y-%m-%d')

    with engine.connect() as conn:
        # 订单统计
        order_stats = conn.execute(text("""
            SELECT
                COUNT(*) as total_orders,
                COALESCE(SUM(total), 0) as total_revenue,
                COALESCE(AVG(total), 0) as avg_order_value,
                COALESCE(SUM(refunded_amount), 0) as total_refund,
                COALESCE(SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END), 0) as completed_orders,
                COALESCE(SUM(CASE WHEN status = 'processing' THEN 1 ELSE 0 END), 0) as processing_orders
            FROM orders
            WHERE created_at >= :start AND created_at <= :end
        """), {"start": start_date + " 00:00:00", "end": end_date + " 23:59:59"}).fetchone()

        # 产品销售排行（简化版，从订单 JSON 中提取）
        top_products = []

        # 国家/地区分布
        country_stats = conn.execute(text("""
            SELECT
                COALESCE(country, 'Unknown') as country,
                COUNT(*) as order_count,
                COALESCE(SUM(total), 0) as revenue
            FROM orders
            WHERE created_at >= :start AND created_at <= :end
            GROUP BY country
            ORDER BY revenue DESC
            LIMIT 5
        """), {"start": start_date + " 00:00:00", "end": end_date + " 23:59:59"}).fetchall()

    return {
        "start_date": start_date,
        "end_date": end_date,
        "order_stats": order_stats,
        "top_products": top_products,
        "country_stats": country_stats
    }

def format_weekly_report(data):
    """格式化周报内容（飞书 Markdown 格式）"""
    stats = data["order_stats"]
    start = data["start_date"]
    end = data["end_date"]

    content = f"""## 📊 Nuotao 经营周报
**统计周期**: {start} ~ {end}

### 💰 核心指标
| 指标 | 数值 |
|------|------|
| 订单总数 | {stats.total_orders} 单 |
| 总收入 | ${stats.total_revenue:,.2f} |
| 平均订单金额 | ${stats.avg_order_value:,.2f} |
| 退款金额 | ${stats.total_refund:,.2f} |
| 已完成订单 | {stats.completed_orders} 单 |
| 处理中订单 | {stats.processing_orders} 单 |

### 🏆 产品销售排行 TOP 5
"""

    if data["top_products"]:
        for i, p in enumerate(data["top_products"], 1):
            content += f"{i}. **{p.name}** - {p.sales_count}件，${p.sales_revenue:,.2f}\n"
    else:
        content += "暂无销售数据\n"

    content += "\n### 🌍 地区销售分布 TOP 5\n"
    if data["country_stats"]:
        for c in data["country_stats"]:
            content += f"- **{c.country}**: {c.order_count}单，${c.revenue:,.2f}\n"
    else:
        content += "暂无地区数据\n"

    content += f"""
---
*由 Nuotao AI OS 自动生成 | {datetime.now().strftime('%Y-%m-%d %H:%M')}*
"""
    return content

def send_to_feishu(content):
    """发送周报到飞书"""
    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "📊 Nuotao 经营周报"
                },
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": content
                }
            ]
        }
    }

    try:
        response = requests.post(FEISHU_WEBHOOK_URL, json=payload, timeout=10)
        result = response.json()
        if result.get("code") == 0 or result.get("StatusCode") == 0:
            print("✅ 周报已成功推送到飞书")
            return True
        else:
            print(f"❌ 飞书推送失败: {result}")
            return False
    except Exception as e:
        print(f"❌ 飞书推送异常: {e}")
        return False

def main():
    print(f"=== Nuotao 经营周报生成 - {datetime.now()} ===")

    # 获取数据
    print("正在获取经营数据...")
    data = get_weekly_data()
    print(f"统计周期: {data['start_date']} ~ {data['end_date']}")
    print(f"订单数: {data['order_stats'].total_orders}, 收入: ${data['order_stats'].total_revenue:,.2f}")

    # 格式化周报
    print("正在格式化周报...")
    content = format_weekly_report(data)

    # 推送到飞书
    print("正在推送到飞书...")
    success = send_to_feishu(content)

    if success:
        print("=== 周报生成与推送完成 ===")
    else:
        print("=== 周报推送失败，请检查 ===")
        exit(1)

if __name__ == "__main__":
    main()
