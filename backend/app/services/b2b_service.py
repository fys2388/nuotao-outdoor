"""
B2B 代理商管理服务
支持代理商信息管理、价格体系、佣金返点、B2B 订单管理、账期管理
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "b2b",
)

AGENT_STATUSES = ["active", "inactive", "suspended", "pending"]
AGENT_TIERS = ["bronze", "silver", "gold", "platinum"]
B2B_ORDER_STATUSES = ["pending", "confirmed", "processing", "shipped", "delivered", "cancelled", "refunded"]
PAYMENT_STATUSES = ["unpaid", "partial", "paid", "overdue", "written_off"]


def _ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def _get_agent_path(agent_id: str) -> str:
    return os.path.join(DATA_DIR, f"agent_{agent_id}.json")


def _load_agent(agent_id: str) -> dict[str, Any] | None:
    path = _get_agent_path(agent_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to load agent %s: %s", agent_id, str(e))
        return None


def _save_agent(agent: dict[str, Any]) -> None:
    _ensure_data_dir()
    path = _get_agent_path(agent["id"])
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(agent, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("Failed to save agent %s: %s", agent["id"], str(e))


def create_agent(
    name: str,
    contact_person: str,
    email: str,
    phone: str = "",
    country: str = "",
    city: str = "",
    address: str = "",
    tier: str = "bronze",
    commission_rate: float = 5.0,
    discount_percent: float = 0,
    credit_limit: float = 0,
    payment_terms_days: int = 30,
    notes: str = "",
) -> dict[str, Any]:
    """创建代理商"""
    if tier not in AGENT_TIERS:
        raise ValueError(f"Invalid tier: {tier}")

    now = datetime.utcnow()
    agent_id = str(uuid4())

    agent = {
        "id": agent_id,
        "agent_number": f"AG-{now.strftime('%Y%m%d')}-{agent_id[:8].upper()}",
        "name": name,
        "status": "pending",
        "tier": tier,
        "contact": {
            "person": contact_person,
            "email": email,
            "phone": phone,
        },
        "location": {
            "country": country,
            "city": city,
            "address": address,
        },
        "pricing": {
            "commission_rate": commission_rate,
            "discount_percent": discount_percent,
            "tier_pricing": {},
        },
        "credit": {
            "credit_limit": credit_limit,
            "current_balance": 0,
            "available_credit": credit_limit,
            "payment_terms_days": payment_terms_days,
        },
        "stats": {
            "total_orders": 0,
            "total_revenue": 0,
            "total_commission": 0,
            "last_order_date": None,
        },
        "notes": notes,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }

    _save_agent(agent)
    logger.info("Agent created: id=%s, name=%s, tier=%s", agent_id, name, tier)
    return agent


def update_agent_status(agent_id: str, new_status: str) -> dict[str, Any]:
    """更新代理商状态"""
    if new_status not in AGENT_STATUSES:
        raise ValueError(f"Invalid status: {new_status}")

    agent = _load_agent(agent_id)
    if not agent:
        raise ValueError(f"Agent not found: {agent_id}")

    agent["status"] = new_status
    agent["updated_at"] = datetime.utcnow().isoformat()
    _save_agent(agent)
    return agent


def create_b2b_order(
    agent_id: str,
    items: list[dict[str, Any]],
    shipping_address: dict[str, Any] | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """创建 B2B 订单"""
    agent = _load_agent(agent_id)
    if not agent:
        raise ValueError(f"Agent not found: {agent_id}")

    if agent["status"] not in ["active"]:
        raise ValueError(f"Agent is not active: {agent['status']}")

    now = datetime.utcnow()
    order_id = str(uuid4())

    # 计算订单金额
    subtotal = sum(item.get("quantity", 0) * item.get("unit_price", 0) for item in items)
    discount_percent = agent["pricing"]["discount_percent"]
    discount_amount = subtotal * discount_percent / 100
    total = subtotal - discount_amount
    commission = total * agent["pricing"]["commission_rate"] / 100

    # 检查信用额度
    if agent["credit"]["current_balance"] + total > agent["credit"]["credit_limit"] and agent["credit"]["credit_limit"] > 0:
        raise ValueError(f"Credit limit exceeded. Available: {agent['credit']['available_credit']}, Order total: {total}")

    order = {
        "id": order_id,
        "order_number": f"B2B-{now.strftime('%Y%m%d')}-{order_id[:8].upper()}",
        "agent_id": agent_id,
        "agent_name": agent["name"],
        "status": "pending",
        "payment_status": "unpaid",
        "items": items,
        "subtotal": round(subtotal, 2),
        "discount_percent": discount_percent,
        "discount_amount": round(discount_amount, 2),
        "total": round(total, 2),
        "commission": round(commission, 2),
        "shipping_address": shipping_address or agent["location"],
        "payment_due_date": (now + timedelta(days=agent["credit"]["payment_terms_days"])).strftime("%Y-%m-%d"),
        "notes": notes,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "history": [{"action": "created", "timestamp": now.isoformat()}],
    }

    # 更新代理商信用和统计
    agent["credit"]["current_balance"] += total
    agent["credit"]["available_credit"] = agent["credit"]["credit_limit"] - agent["credit"]["current_balance"]
    agent["stats"]["total_orders"] += 1
    agent["stats"]["total_revenue"] += total
    agent["stats"]["total_commission"] += commission
    agent["stats"]["last_order_date"] = now.isoformat()
    agent["updated_at"] = now.isoformat()
    _save_agent(agent)

    _save_b2b_order(order)
    logger.info("B2B order created: id=%s, agent=%s, total=%.2f", order_id, agent_id, total)
    return order


def _save_b2b_order(order: dict[str, Any]) -> None:
    _ensure_data_dir()
    path = os.path.join(DATA_DIR, f"b2b_order_{order['id']}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(order, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("Failed to save b2b order %s: %s", order["id"], str(e))


def update_b2b_order_status(order_id: str, new_status: str) -> dict[str, Any]:
    """更新 B2B 订单状态"""
    if new_status not in B2B_ORDER_STATUSES:
        raise ValueError(f"Invalid status: {new_status}")

    path = os.path.join(DATA_DIR, f"b2b_order_{order_id}.json")
    if not os.path.exists(path):
        raise ValueError(f"B2B order not found: {order_id}")

    with open(path, encoding="utf-8") as f:
        order = json.load(f)

    old_status = order["status"]
    order["status"] = new_status
    order["updated_at"] = datetime.utcnow().isoformat()
    order["history"].append({
        "action": "status_change",
        "old_status": old_status,
        "new_status": new_status,
        "timestamp": datetime.utcnow().isoformat(),
    })

    with open(path, "w", encoding="utf-8") as f:
        json.dump(order, f, indent=2, ensure_ascii=False, default=str)

    return order


def record_payment(order_id: str, amount: float, payment_method: str = "bank_transfer") -> dict[str, Any]:
    """记录 B2B 订单付款"""
    path = os.path.join(DATA_DIR, f"b2b_order_{order_id}.json")
    if not os.path.exists(path):
        raise ValueError(f"B2B order not found: {order_id}")

    with open(path, encoding="utf-8") as f:
        order = json.load(f)

    now = datetime.utcnow()
    total = order["total"]

    # 计算已付金额
    paid_amount = order.get("paid_amount", 0) + amount
    order["paid_amount"] = paid_amount

    if paid_amount >= total:
        order["payment_status"] = "paid"
    elif paid_amount > 0:
        order["payment_status"] = "partial"

    order["updated_at"] = now.isoformat()
    order.setdefault("payments", []).append({
        "amount": amount,
        "method": payment_method,
        "timestamp": now.isoformat(),
    })

    # 更新代理商信用余额
    agent = _load_agent(order["agent_id"])
    if agent:
        agent["credit"]["current_balance"] = max(0, agent["credit"]["current_balance"] - amount)
        agent["credit"]["available_credit"] = agent["credit"]["credit_limit"] - agent["credit"]["current_balance"]
        agent["updated_at"] = now.isoformat()
        _save_agent(agent)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(order, f, indent=2, ensure_ascii=False, default=str)

    return {
        "order_id": order_id,
        "payment_amount": amount,
        "total_paid": paid_amount,
        "total_due": total,
        "remaining": total - paid_amount,
        "payment_status": order["payment_status"],
    }


def list_agents() -> dict[str, Any]:
    """获取代理商列表"""
    _ensure_data_dir()
    agents = []
    for filename in os.listdir(DATA_DIR):
        if not filename.startswith("agent_") or not filename.endswith(".json"):
            continue
        try:
            with open(os.path.join(DATA_DIR, filename), encoding="utf-8") as f:
                agent = json.load(f)
                agents.append({
                    "id": agent["id"],
                    "agent_number": agent["agent_number"],
                    "name": agent["name"],
                    "status": agent["status"],
                    "tier": agent["tier"],
                    "country": agent["location"]["country"],
                    "total_orders": agent["stats"]["total_orders"],
                    "total_revenue": agent["stats"]["total_revenue"],
                    "credit_balance": agent["credit"]["current_balance"],
                })
        except Exception as e:
            logger.warning("Failed to load agent file %s: %s", filename, str(e))

    return {"agents": agents, "total": len(agents)}


def get_b2b_system_status() -> dict[str, Any]:
    """获取 B2B 系统状态"""
    return {
        "status": "running",
        "agent_statuses": AGENT_STATUSES,
        "agent_tiers": AGENT_TIERS,
        "order_statuses": B2B_ORDER_STATUSES,
        "payment_statuses": PAYMENT_STATUSES,
        "features": [
            "agent_management",
            "tiered_pricing",
            "commission_tracking",
            "credit_management",
            "b2b_order_management",
            "payment_tracking",
            "account_receivable",
        ],
        "note": "B2B agent management system is ready. Supports agent management, tiered pricing, commission tracking, credit management, and B2B order processing.",
    }
