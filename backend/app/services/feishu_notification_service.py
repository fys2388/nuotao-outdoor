"""
飞书通知服务
支持将经营预警、订单通知、系统消息推送到飞书群机器人
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any
from uuid import uuid4

import requests

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "notifications",
)

# 飞书 Webhook URL（从环境变量或配置文件读取）
FEISHU_WEBHOOK_URL = os.getenv(
    "FEISHU_WEBHOOK_URL",
    "https://open.feishu.cn/open-apis/bot/v2/hook/1035e5f2-8984-44d1-83f4-9fb60f274371",
)

# 通知类型
NOTIFICATION_TYPES = [
    "alert_critical",      # 严重预警
    "alert_warning",       # 警告预警
    "order_new",           # 新订单
    "order_shipped",       # 订单发货
    "order_refunded",      # 订单退款
    "inventory_low",       # 库存不足
    "weekly_report",       # 周报通知
    "system_error",        # 系统错误
    "custom",              # 自定义消息
]

# 通知状态
NOTIFICATION_STATUSES = ["pending", "sent", "failed", "retry"]


def _ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def _get_notification_path(notification_id: str) -> str:
    return os.path.join(DATA_DIR, f"notification_{notification_id}.json")


def _save_notification(notification: dict[str, Any]) -> None:
    _ensure_data_dir()
    path = _get_notification_path(notification["id"])
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(notification, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("Failed to save notification %s: %s", notification["id"], str(e))


def send_feishu_text_message(
    content: str,
    webhook_url: str | None = None,
) -> dict[str, Any]:
    """
    发送飞书文本消息

    Args:
        content: 消息内容
        webhook_url: 飞书 Webhook URL（可选，默认使用配置的 URL）

    Returns:
        发送结果
    """
    url = webhook_url or FEISHU_WEBHOOK_URL
    payload = {
        "msg_type": "text",
        "content": {
            "text": content,
        },
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        result = response.json()

        if result.get("code") == 0 or result.get("StatusCode") == 0:
            return {"success": True, "response": result, "message": "消息发送成功"}
        else:
            return {"success": False, "response": result, "message": f"飞书 API 返回错误: {result.get('msg', result.get('StatusMessage', 'Unknown error'))}"}
    except requests.exceptions.RequestException as e:
        logger.error("Failed to send Feishu message: %s", str(e))
        return {"success": False, "error": str(e), "message": "网络请求失败"}


def send_feishu_rich_message(
    title: str,
    content: list[list[dict[str, Any]]],
    webhook_url: str | None = None,
) -> dict[str, Any]:
    """
    发送飞书富文本消息（post 类型）

    Args:
        title: 消息标题
        content: 富文本内容（二维数组，每行一个数组）
        webhook_url: 飞书 Webhook URL

    Returns:
        发送结果
    """
    url = webhook_url or FEISHU_WEBHOOK_URL
    payload = {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": title,
                    "content": content,
                }
            }
        },
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        result = response.json()

        if result.get("code") == 0 or result.get("StatusCode") == 0:
            return {"success": True, "response": result, "message": "富文本消息发送成功"}
        else:
            return {"success": False, "response": result, "message": f"飞书 API 返回错误: {result.get('msg', 'Unknown error')}"}
    except requests.exceptions.RequestException as e:
        logger.error("Failed to send Feishu rich message: %s", str(e))
        return {"success": False, "error": str(e), "message": "网络请求失败"}


def send_alert_notification(
    alert_type: str,
    severity: str,
    title: str,
    description: str,
    metric_data: dict[str, Any] | None = None,
    recommended_action: str = "",
    webhook_url: str | None = None,
) -> dict[str, Any]:
    """
    发送经营预警通知到飞书

    Args:
        alert_type: 预警类型
        severity: 严重程度（critical/warning/info）
        title: 预警标题
        description: 预警描述
        metric_data: 指标数据
        recommended_action: 建议行动
        webhook_url: 飞书 Webhook URL

    Returns:
        通知结果
    """
    now = datetime.utcnow()
    notification_id = str(uuid4())

    # 严重程度对应的 emoji 和颜色
    severity_config = {
        "critical": {"emoji": "🔴", "label": "严重"},
        "warning": {"emoji": "🟡", "label": "警告"},
        "info": {"emoji": "🔵", "label": "提示"},
    }
    config = severity_config.get(severity, severity_config["info"])

    # 构建富文本内容
    content_lines = [
        [{"tag": "text", "text": f"{config['emoji']} 【{config['label']}预警】{title}"}],
        [{"tag": "text", "text": f"预警类型: {alert_type}"}],
        [{"tag": "text", "text": f"预警时间: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}"}],
        [{"tag": "text", "text": f"详细描述: {description}"}],
    ]

    if metric_data:
        metric_str = ", ".join([f"{k}={v}" for k, v in list(metric_data.items())[:5]])
        content_lines.append([{"tag": "text", "text": f"关键指标: {metric_str}"}])

    if recommended_action:
        content_lines.append([{"tag": "text", "text": f"建议行动: {recommended_action}"}])

    content_lines.append([{"tag": "text", "text": "请及时处理，登录管理控制台查看详情。"}])

    # 发送消息
    send_result = send_feishu_rich_message(
        title=f"{config['emoji']} 经营预警 - {config['label']}",
        content=content_lines,
        webhook_url=webhook_url,
    )

    # 保存通知记录
    notification = {
        "id": notification_id,
        "type": f"alert_{severity}",
        "alert_type": alert_type,
        "severity": severity,
        "title": title,
        "description": description,
        "metric_data": metric_data or {},
        "recommended_action": recommended_action,
        "status": "sent" if send_result["success"] else "failed",
        "send_result": send_result,
        "created_at": now.isoformat(),
        "sent_at": now.isoformat() if send_result["success"] else None,
    }
    _save_notification(notification)

    return {
        "success": send_result["success"],
        "notification_id": notification_id,
        "message": send_result.get("message", "未知结果"),
        "notification": notification,
    }


def send_order_notification(
    order_type: str,
    order_id: str,
    customer_name: str,
    total_amount: float,
    currency: str = "USD",
    items_count: int = 0,
    webhook_url: str | None = None,
) -> dict[str, Any]:
    """
    发送订单通知到飞书

    Args:
        order_type: 订单类型（order_new/order_shipped/order_refunded）
        order_id: 订单 ID
        customer_name: 客户名称
        total_amount: 订单金额
        currency: 货币
        items_count: 商品数量
        webhook_url: 飞书 Webhook URL

    Returns:
        通知结果
    """
    now = datetime.utcnow()
    notification_id = str(uuid4())

    type_config = {
        "order_new": {"emoji": "🟢", "label": "新订单"},
        "order_shipped": {"emoji": "📦", "label": "订单发货"},
        "order_refunded": {"emoji": "🔄", "label": "订单退款"},
    }
    config = type_config.get(order_type, type_config["order_new"])

    content_lines = [
        [{"tag": "text", "text": f"{config['emoji']} 【{config['label']}】订单号: {order_id}"}],
        [{"tag": "text", "text": f"客户: {customer_name}"}],
        [{"tag": "text", "text": f"金额: {currency} {total_amount:,.2f}"}],
        [{"tag": "text", "text": f"商品数量: {items_count} 件"}],
        [{"tag": "text", "text": f"时间: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}"}],
    ]

    send_result = send_feishu_rich_message(
        title=f"{config['emoji']} 订单通知 - {config['label']}",
        content=content_lines,
        webhook_url=webhook_url,
    )

    notification = {
        "id": notification_id,
        "type": order_type,
        "order_id": order_id,
        "customer_name": customer_name,
        "total_amount": total_amount,
        "currency": currency,
        "items_count": items_count,
        "status": "sent" if send_result["success"] else "failed",
        "send_result": send_result,
        "created_at": now.isoformat(),
    }
    _save_notification(notification)

    return {
        "success": send_result["success"],
        "notification_id": notification_id,
        "message": send_result.get("message", "未知结果"),
    }


def send_weekly_report_notification(
    report_title: str,
    total_revenue: float,
    total_orders: int,
    gross_margin: float,
    alerts_count: int,
    report_url: str = "",
    webhook_url: str | None = None,
) -> dict[str, Any]:
    """
    发送周报通知到飞书

    Args:
        report_title: 周报标题
        total_revenue: 总收入
        total_orders: 总订单数
        gross_margin: 毛利率
        alerts_count: 预警数量
        report_url: 周报链接
        webhook_url: 飞书 Webhook URL

    Returns:
        通知结果
    """
    now = datetime.utcnow()
    notification_id = str(uuid4())

    content_lines = [
        [{"tag": "text", "text": f"📊 【AI 经营周报】{report_title}"}],
        [{"tag": "text", "text": f"💰 总收入: ${total_revenue:,.2f}"}],
        [{"tag": "text", "text": f"📦 总订单: {total_orders} 单"}],
        [{"tag": "text", "text": f"📈 毛利率: {gross_margin}%"}],
        [{"tag": "text", "text": f"⚠️ 预警数量: {alerts_count} 个"}],
        [{"tag": "text", "text": f"生成时间: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}"}],
    ]

    if report_url:
        content_lines.append([{"tag": "a", "text": "点击查看完整周报", "href": report_url}])

    send_result = send_feishu_rich_message(
        title="📊 AI 经营周报已生成",
        content=content_lines,
        webhook_url=webhook_url,
    )

    notification = {
        "id": notification_id,
        "type": "weekly_report",
        "report_title": report_title,
        "total_revenue": total_revenue,
        "total_orders": total_orders,
        "gross_margin": gross_margin,
        "alerts_count": alerts_count,
        "status": "sent" if send_result["success"] else "failed",
        "send_result": send_result,
        "created_at": now.isoformat(),
    }
    _save_notification(notification)

    return {
        "success": send_result["success"],
        "notification_id": notification_id,
        "message": send_result.get("message", "未知结果"),
    }


def get_notification_status() -> dict[str, Any]:
    """获取通知系统状态"""
    return {
        "status": "ready",
        "webhook_configured": bool(FEISHU_WEBHOOK_URL),
        "notification_types": NOTIFICATION_TYPES,
        "features": [
            "alert_notification",
            "order_notification",
            "weekly_report_notification",
            "text_message",
            "rich_text_message",
            "notification_history",
        ],
        "note": "Feishu notification service is ready. Supports alert, order, and weekly report notifications to Feishu group bot.",
    }
