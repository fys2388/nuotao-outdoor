"""
EDM 营销自动化服务
支持弃购挽回、复购营销、欢迎邮件、邮件活动管理、效果追踪
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

# EDM 数据存储路径
DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "edm",
)

# 营销活动类型
CAMPAIGN_TYPES = [
    "abandoned_cart",    # 弃购挽回
    "post_purchase",     # 购后营销
    "welcome",           # 欢迎邮件
    "newsletter",        # 新闻通讯
    "promotional",       # 促销活动
    "win_back",          # 召回邮件
    "review_request",    # 评价请求
]

# 营销活动状态
CAMPAIGN_STATUSES = [
    "draft",       # 草稿
    "scheduled",   # 已调度
    "active",      # 进行中
    "paused",      # 已暂停
    "completed",   # 已完成
    "cancelled",   # 已取消
]

# 弃购挽回流程配置
ABANDONED_CART_FLOW = {
    "name": "Abandoned Cart Recovery",
    "description": "Recover abandoned carts with timed email sequence",
    "trigger": "cart_abandoned",
    "steps": [
        {"delay_hours": 1, "email_type": "reminder", "subject": "You left something in your cart!", "discount_percent": 0},
        {"delay_hours": 24, "email_type": "incentive", "subject": "Still thinking? Here's 10% off!", "discount_percent": 10},
        {"delay_hours": 48, "email_type": "final_reminder", "subject": "Last chance: Your cart is waiting", "discount_percent": 15},
    ],
}

# 复购营销流程配置
REPURCHASE_FLOW = {
    "name": "Post-Purchase Repurchase",
    "description": "Encourage repeat purchases with timed recommendations",
    "trigger": "order_completed",
    "steps": [
        {"delay_days": 7, "email_type": "thank_you", "subject": "Thank you for your purchase!", "discount_percent": 0},
        {"delay_days": 30, "email_type": "cross_sell", "subject": "You might also like these products", "discount_percent": 5},
        {"delay_days": 60, "email_type": "replenishment", "subject": "Time to restock?", "discount_percent": 10},
        {"delay_days": 90, "email_type": "loyalty_reward", "subject": "Loyal customer reward: 15% off your next order", "discount_percent": 15},
    ],
}

# 欢迎邮件流程配置
WELCOME_FLOW = {
    "name": "Welcome Series",
    "description": "Welcome new subscribers with onboarding emails",
    "trigger": "new_subscriber",
    "steps": [
        {"delay_hours": 0, "email_type": "welcome", "subject": "Welcome to Nuotao Outdoor!", "discount_percent": 10},
        {"delay_hours": 24, "email_type": "brand_story", "subject": "Our story: Gear for every adventure", "discount_percent": 0},
        {"delay_hours": 72, "email_type": "best_sellers", "subject": "Customer favorites: Top 5 products", "discount_percent": 5},
    ],
}


def _ensure_data_dir() -> None:
    """确保数据目录存在"""
    os.makedirs(DATA_DIR, exist_ok=True)


def _get_campaign_path(campaign_id: str) -> str:
    """获取营销活动数据文件路径"""
    return os.path.join(DATA_DIR, f"campaign_{campaign_id}.json")


def _load_campaign(campaign_id: str) -> dict[str, Any] | None:
    """加载营销活动数据"""
    path = _get_campaign_path(campaign_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to load campaign %s: %s", campaign_id, str(e))
        return None


def _save_campaign(campaign: dict[str, Any]) -> None:
    """保存营销活动数据"""
    _ensure_data_dir()
    path = _get_campaign_path(campaign["id"])
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(campaign, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("Failed to save campaign %s: %s", campaign["id"], str(e))


def create_campaign(
    campaign_type: str,
    name: str,
    description: str = "",
    subject: str = "",
    email_content: dict[str, Any] | None = None,
    trigger: str = "",
    schedule: dict[str, Any] | None = None,
    target_audience: str = "all",
    discount_percent: int = 0,
    created_by: str = "system",
) -> dict[str, Any]:
    """
    创建营销活动

    Args:
        campaign_type: 活动类型
        name: 活动名称
        description: 活动描述
        subject: 邮件主题
        email_content: 邮件内容
        trigger: 触发条件
        schedule: 调度配置
        target_audience: 目标受众
        discount_percent: 折扣百分比
        created_by: 创建者

    Returns:
        营销活动数据
    """
    if campaign_type not in CAMPAIGN_TYPES:
        raise ValueError(f"Invalid campaign type: {campaign_type}. Must be one of {CAMPAIGN_TYPES}")

    now = datetime.utcnow()
    campaign_id = str(uuid4())

    campaign = {
        "id": campaign_id,
        "type": campaign_type,
        "name": name,
        "description": description,
        "subject": subject,
        "email_content": email_content or {},
        "trigger": trigger,
        "schedule": schedule or {},
        "target_audience": target_audience,
        "discount_percent": discount_percent,
        "status": "draft",
        "created_by": created_by,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "started_at": None,
        "completed_at": None,
        "stats": {
            "total_recipients": 0,
            "sent": 0,
            "delivered": 0,
            "opened": 0,
            "clicked": 0,
            "converted": 0,
            "unsubscribed": 0,
            "bounced": 0,
            "complained": 0,
            "revenue": 0,
        },
        "send_log": [],
    }

    _save_campaign(campaign)
    logger.info("Campaign created: id=%s, type=%s, name=%s", campaign_id, campaign_type, name)
    return campaign


def update_campaign_status(
    campaign_id: str,
    new_status: str,
    updated_by: str = "system",
) -> dict[str, Any]:
    """
    更新营销活动状态

    Args:
        campaign_id: 活动 ID
        new_status: 新状态
        updated_by: 更新者

    Returns:
        更新后的营销活动数据
    """
    if new_status not in CAMPAIGN_STATUSES:
        raise ValueError(f"Invalid status: {new_status}. Must be one of {CAMPAIGN_STATUSES}")

    campaign = _load_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign not found: {campaign_id}")

    now = datetime.utcnow()
    campaign["status"] = new_status
    campaign["updated_at"] = now.isoformat()

    if new_status == "active":
        campaign["started_at"] = now.isoformat()
    elif new_status == "completed":
        campaign["completed_at"] = now.isoformat()

    _save_campaign(campaign)
    logger.info("Campaign status updated: id=%s, status=%s, by=%s", campaign_id, new_status, updated_by)
    return campaign


def send_campaign_email(
    campaign_id: str,
    recipient_email: str,
    recipient_name: str = "Customer",
    order_data: dict[str, Any] | None = None,
    cart_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    发送营销活动邮件

    Args:
        campaign_id: 活动 ID
        recipient_email: 收件人邮箱
        recipient_name: 收件人名称
        order_data: 订单数据（用于购后营销）
        cart_data: 购物车数据（用于弃购挽回）

    Returns:
        发送结果
    """
    campaign = _load_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign not found: {campaign_id}")

    if campaign["status"] not in ["active", "scheduled"]:
        raise ValueError(f"Campaign is not active: {campaign['status']}")

    now = datetime.utcnow()
    send_id = str(uuid4())

    # 模拟邮件发送（实际应调用 email_service）
    send_result = {
        "send_id": send_id,
        "campaign_id": campaign_id,
        "recipient_email": recipient_email,
        "recipient_name": recipient_name,
        "subject": campaign.get("subject", ""),
        "sent_at": now.isoformat(),
        "status": "sent",
        "provider": "mock_smtp",
    }

    # 更新活动统计
    campaign["stats"]["total_recipients"] += 1
    campaign["stats"]["sent"] += 1
    campaign["stats"]["delivered"] += 1  # 模拟全部送达
    campaign["send_log"].append(send_result)
    campaign["updated_at"] = now.isoformat()

    _save_campaign(campaign)
    logger.info("Campaign email sent: campaign=%s, recipient=%s, send_id=%s", campaign_id, recipient_email, send_id)
    return send_result


def track_email_event(
    campaign_id: str,
    send_id: str,
    event_type: str,
    event_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    追踪邮件事件（打开、点击、转化、退订等）

    Args:
        campaign_id: 活动 ID
        send_id: 发送 ID
        event_type: 事件类型（open/click/conversion/unsubscribe/bounce/complaint）
        event_data: 事件数据

    Returns:
        事件记录
    """
    valid_events = ["open", "click", "conversion", "unsubscribe", "bounce", "complaint", "delivery"]
    if event_type not in valid_events:
        raise ValueError(f"Invalid event type: {event_type}. Must be one of {valid_events}")

    campaign = _load_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign not found: {campaign_id}")

    now = datetime.utcnow()
    event = {
        "event_id": str(uuid4()),
        "campaign_id": campaign_id,
        "send_id": send_id,
        "event_type": event_type,
        "event_data": event_data or {},
        "timestamp": now.isoformat(),
    }

    # 更新统计
    stats_mapping = {
        "open": "opened",
        "click": "clicked",
        "conversion": "converted",
        "unsubscribe": "unsubscribed",
        "bounce": "bounced",
        "complaint": "complained",
        "delivery": "delivered",
    }

    stat_key = stats_mapping.get(event_type)
    if stat_key:
        campaign["stats"][stat_key] = campaign["stats"].get(stat_key, 0) + 1

    # 如果是转化事件，记录收入
    if event_type == "conversion" and event_data and "revenue" in event_data:
        campaign["stats"]["revenue"] = float(campaign["stats"].get("revenue", 0)) + float(event_data["revenue"])

    # 在发送日志中记录事件
    for send_log in campaign["send_log"]:
        if send_log.get("send_id") == send_id:
            if "events" not in send_log:
                send_log["events"] = []
            send_log["events"].append(event)
            break

    campaign["updated_at"] = now.isoformat()
    _save_campaign(campaign)

    logger.info("Email event tracked: campaign=%s, send=%s, event=%s", campaign_id, send_id, event_type)
    return event


def get_campaign_stats(campaign_id: str) -> dict[str, Any]:
    """
    获取营销活动统计数据

    Args:
        campaign_id: 活动 ID

    Returns:
        统计数据（包含计算的比率）
    """
    campaign = _load_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign not found: {campaign_id}")

    stats = campaign["stats"]
    total_sent = stats.get("sent", 0)
    total_delivered = stats.get("delivered", 0)
    total_opened = stats.get("opened", 0)
    total_clicked = stats.get("clicked", 0)
    total_converted = stats.get("converted", 0)

    # 计算比率
    delivery_rate = (total_delivered / total_sent * 100) if total_sent > 0 else 0
    open_rate = (total_opened / total_delivered * 100) if total_delivered > 0 else 0
    click_rate = (total_clicked / total_delivered * 100) if total_delivered > 0 else 0
    click_to_open_rate = (total_clicked / total_opened * 100) if total_opened > 0 else 0
    conversion_rate = (total_converted / total_delivered * 100) if total_delivered > 0 else 0
    revenue_per_email = (stats.get("revenue", 0) / total_sent) if total_sent > 0 else 0

    return {
        "campaign_id": campaign_id,
        "campaign_name": campaign["name"],
        "campaign_type": campaign["type"],
        "status": campaign["status"],
        "raw_stats": stats,
        "calculated_rates": {
            "delivery_rate_percent": round(delivery_rate, 2),
            "open_rate_percent": round(open_rate, 2),
            "click_rate_percent": round(click_rate, 2),
            "click_to_open_rate_percent": round(click_to_open_rate, 2),
            "conversion_rate_percent": round(conversion_rate, 2),
            "revenue_per_email": round(revenue_per_email, 2),
        },
        "benchmarks": {
            "industry_avg_open_rate": 18.0,
            "industry_avg_click_rate": 2.5,
            "industry_avg_conversion_rate": 1.5,
        },
        "performance": {
            "open_rate_vs_industry": "above" if open_rate > 18 else "below",
            "click_rate_vs_industry": "above" if click_rate > 2.5 else "below",
            "conversion_rate_vs_industry": "above" if conversion_rate > 1.5 else "below",
        },
    }


def list_campaigns(
    campaign_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """
    获取营销活动列表

    Args:
        campaign_type: 按类型筛选
        status: 按状态筛选
        limit: 返回数量限制

    Returns:
        营销活动列表和统计
    """
    _ensure_data_dir()

    campaigns = []
    for filename in os.listdir(DATA_DIR):
        if not filename.startswith("campaign_") or not filename.endswith(".json"):
            continue
        try:
            with open(os.path.join(DATA_DIR, filename), encoding="utf-8") as f:
                campaign = json.load(f)

            # 筛选
            if campaign_type and campaign.get("type") != campaign_type:
                continue
            if status and campaign.get("status") != status:
                continue

            campaigns.append(campaign)
        except Exception as e:
            logger.warning("Failed to load campaign file %s: %s", filename, str(e))

    # 按创建时间排序
    campaigns.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    campaigns = campaigns[:limit]

    # 统计
    stats = {
        "total": len(campaigns),
        "by_type": {},
        "by_status": {},
        "total_sent": sum(c.get("stats", {}).get("sent", 0) for c in campaigns),
        "total_opened": sum(c.get("stats", {}).get("opened", 0) for c in campaigns),
        "total_revenue": sum(c.get("stats", {}).get("revenue", 0) for c in campaigns),
    }

    for campaign in campaigns:
        ctype = campaign.get("type", "unknown")
        cstatus = campaign.get("status", "unknown")
        stats["by_type"][ctype] = stats["by_type"].get(ctype, 0) + 1
        stats["by_status"][cstatus] = stats["by_status"].get(cstatus, 0) + 1

    return {
        "campaigns": campaigns,
        "stats": stats,
    }


def get_edm_automation_status() -> dict[str, Any]:
    """获取 EDM 营销自动化系统状态"""
    return {
        "status": "running",
        "campaign_types": CAMPAIGN_TYPES,
        "campaign_statuses": CAMPAIGN_STATUSES,
        "available_flows": {
            "abandoned_cart": ABANDONED_CART_FLOW,
            "repurchase": REPURCHASE_FLOW,
            "welcome": WELCOME_FLOW,
        },
        "trackable_events": ["open", "click", "conversion", "unsubscribe", "bounce", "complaint", "delivery"],
        "features": [
            "campaign_management",
            "abandoned_cart_recovery",
            "post_purchase_marketing",
            "welcome_series",
            "email_scheduling",
            "performance_tracking",
            "revenue_attribution",
            "a_b_testing_support",
        ],
        "note": "EDM marketing automation system is ready. Supports abandoned cart recovery, repurchase marketing, welcome series, campaign management, and performance tracking.",
    }
