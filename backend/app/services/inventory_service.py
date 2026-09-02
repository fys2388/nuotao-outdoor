"""
多仓库库存管理服务
支持仓库管理、库存同步、安全库存、补货建议、库存调拨
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "inventory",
)

WAREHOUSE_TYPES = ["domestic", "overseas", "fulfillment_center", "drop_shipping"]
WAREHOUSE_STATUSES = ["active", "inactive", "maintenance"]


def _ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def _get_warehouse_path(warehouse_id: str) -> str:
    return os.path.join(DATA_DIR, f"warehouse_{warehouse_id}.json")


def _load_warehouse(warehouse_id: str) -> dict[str, Any] | None:
    path = _get_warehouse_path(warehouse_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to load warehouse %s: %s", warehouse_id, str(e))
        return None


def _save_warehouse(warehouse: dict[str, Any]) -> None:
    _ensure_data_dir()
    path = _get_warehouse_path(warehouse["id"])
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(warehouse, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("Failed to save warehouse %s: %s", warehouse["id"], str(e))


def create_warehouse(
    name: str,
    warehouse_type: str,
    country: str,
    city: str,
    address: str = "",
    contact_person: str = "",
    contact_phone: str = "",
    contact_email: str = "",
    shipping_methods: list[str] | None = None,
    handling_days: int = 2,
) -> dict[str, Any]:
    """创建仓库"""
    if warehouse_type not in WAREHOUSE_TYPES:
        raise ValueError(f"Invalid warehouse type: {warehouse_type}")

    now = datetime.utcnow()
    warehouse_id = str(uuid4())

    warehouse = {
        "id": warehouse_id,
        "name": name,
        "type": warehouse_type,
        "status": "active",
        "location": {
            "country": country,
            "city": city,
            "address": address,
        },
        "contact": {
            "person": contact_person,
            "phone": contact_phone,
            "email": contact_email,
        },
        "shipping_methods": shipping_methods or [],
        "handling_days": handling_days,
        "inventory": {},  # sku -> {quantity, reserved, available, last_updated}
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }

    _save_warehouse(warehouse)
    logger.info("Warehouse created: id=%s, name=%s, type=%s", warehouse_id, name, warehouse_type)
    return warehouse


def update_inventory(
    warehouse_id: str,
    sku: str,
    quantity: int,
    reason: str = "manual_adjustment",
    reference_id: str = "",
) -> dict[str, Any]:
    """更新库存数量"""
    warehouse = _load_warehouse(warehouse_id)
    if not warehouse:
        raise ValueError(f"Warehouse not found: {warehouse_id}")

    now = datetime.utcnow()
    if sku not in warehouse["inventory"]:
        warehouse["inventory"][sku] = {
            "quantity": 0,
            "reserved": 0,
            "available": 0,
            "last_updated": now.isoformat(),
            "history": [],
        }

    item = warehouse["inventory"][sku]
    old_quantity = item["quantity"]
    item["quantity"] = quantity
    item["available"] = quantity - item["reserved"]
    item["last_updated"] = now.isoformat()
    item["history"].append({
        "timestamp": now.isoformat(),
        "old_quantity": old_quantity,
        "new_quantity": quantity,
        "change": quantity - old_quantity,
        "reason": reason,
        "reference_id": reference_id,
    })

    warehouse["updated_at"] = now.isoformat()
    _save_warehouse(warehouse)

    return {
        "warehouse_id": warehouse_id,
        "sku": sku,
        "old_quantity": old_quantity,
        "new_quantity": quantity,
        "change": quantity - old_quantity,
        "available": item["available"],
        "reserved": item["reserved"],
        "reason": reason,
    }


def reserve_inventory(
    warehouse_id: str,
    sku: str,
    quantity: int,
    order_id: str = "",
) -> dict[str, Any]:
    """预留库存（下单时）"""
    warehouse = _load_warehouse(warehouse_id)
    if not warehouse:
        raise ValueError(f"Warehouse not found: {warehouse_id}")

    if sku not in warehouse["inventory"]:
        raise ValueError(f"SKU not found in warehouse: {sku}")

    item = warehouse["inventory"][sku]
    if item["available"] < quantity:
        raise ValueError(f"Insufficient available inventory: available={item['available']}, requested={quantity}")

    now = datetime.utcnow()
    item["reserved"] += quantity
    item["available"] = item["quantity"] - item["reserved"]
    item["last_updated"] = now.isoformat()
    item["history"].append({
        "timestamp": now.isoformat(),
        "action": "reserve",
        "quantity": quantity,
        "order_id": order_id,
    })

    warehouse["updated_at"] = now.isoformat()
    _save_warehouse(warehouse)

    return {
        "warehouse_id": warehouse_id,
        "sku": sku,
        "reserved": quantity,
        "available": item["available"],
        "order_id": order_id,
    }


def release_inventory(
    warehouse_id: str,
    sku: str,
    quantity: int,
    order_id: str = "",
    reason: str = "order_cancelled",
) -> dict[str, Any]:
    """释放预留库存（取消订单时）"""
    warehouse = _load_warehouse(warehouse_id)
    if not warehouse:
        raise ValueError(f"Warehouse not found: {warehouse_id}")

    if sku not in warehouse["inventory"]:
        raise ValueError(f"SKU not found in warehouse: {sku}")

    item = warehouse["inventory"][sku]
    if item["reserved"] < quantity:
        raise ValueError(f"Insufficient reserved inventory: reserved={item['reserved']}, requested={quantity}")

    now = datetime.utcnow()
    item["reserved"] -= quantity
    item["available"] = item["quantity"] - item["reserved"]
    item["last_updated"] = now.isoformat()
    item["history"].append({
        "timestamp": now.isoformat(),
        "action": "release",
        "quantity": quantity,
        "order_id": order_id,
        "reason": reason,
    })

    warehouse["updated_at"] = now.isoformat()
    _save_warehouse(warehouse)

    return {
        "warehouse_id": warehouse_id,
        "sku": sku,
        "released": quantity,
        "available": item["available"],
        "order_id": order_id,
    }


def fulfill_inventory(
    warehouse_id: str,
    sku: str,
    quantity: int,
    order_id: str = "",
) -> dict[str, Any]:
    """扣减库存（发货时）"""
    warehouse = _load_warehouse(warehouse_id)
    if not warehouse:
        raise ValueError(f"Warehouse not found: {warehouse_id}")

    if sku not in warehouse["inventory"]:
        raise ValueError(f"SKU not found in warehouse: {sku}")

    item = warehouse["inventory"][sku]
    if item["reserved"] < quantity:
        raise ValueError(f"Insufficient reserved inventory: reserved={item['reserved']}, requested={quantity}")

    now = datetime.utcnow()
    item["quantity"] -= quantity
    item["reserved"] -= quantity
    item["available"] = item["quantity"] - item["reserved"]
    item["last_updated"] = now.isoformat()
    item["history"].append({
        "timestamp": now.isoformat(),
        "action": "fulfill",
        "quantity": quantity,
        "order_id": order_id,
    })

    warehouse["updated_at"] = now.isoformat()
    _save_warehouse(warehouse)

    return {
        "warehouse_id": warehouse_id,
        "sku": sku,
        "fulfilled": quantity,
        "remaining": item["quantity"],
        "available": item["available"],
        "order_id": order_id,
    }


def calculate_replenishment(
    warehouse_id: str,
    sku: str,
    daily_sales_rate: float,
    safety_stock_days: int = 14,
    lead_time_days: int = 30,
    order_quantity: int = 100,
) -> dict[str, Any]:
    """计算补货建议"""
    warehouse = _load_warehouse(warehouse_id)
    if not warehouse:
        raise ValueError(f"Warehouse not found: {warehouse_id}")

    item = warehouse["inventory"].get(sku, {"quantity": 0, "available": 0})
    current_stock = item["available"]
    safety_stock = int(daily_sales_rate * safety_stock_days)
    lead_time_demand = int(daily_sales_rate * lead_time_days)
    reorder_point = safety_stock + lead_time_demand

    needs_reorder = current_stock <= reorder_point
    days_of_stock = current_stock / daily_sales_rate if daily_sales_rate > 0 else 999

    if needs_reorder:
        recommended_quantity = max(order_quantity, reorder_point - current_stock + int(daily_sales_rate * 30))
        urgency = "critical" if days_of_stock <= 7 else "warning" if days_of_stock <= 14 else "advisory"
    else:
        recommended_quantity = 0
        urgency = "none"

    return {
        "warehouse_id": warehouse_id,
        "sku": sku,
        "current_stock": current_stock,
        "daily_sales_rate": daily_sales_rate,
        "days_of_stock": round(days_of_stock, 1),
        "safety_stock": safety_stock,
        "lead_time_demand": lead_time_demand,
        "reorder_point": reorder_point,
        "needs_reorder": needs_reorder,
        "recommended_quantity": recommended_quantity,
        "urgency": urgency,
    }


def get_inventory_status(warehouse_id: str) -> dict[str, Any]:
    """获取仓库库存状态"""
    warehouse = _load_warehouse(warehouse_id)
    if not warehouse:
        raise ValueError(f"Warehouse not found: {warehouse_id}")

    total_sku = len(warehouse["inventory"])
    total_quantity = sum(item["quantity"] for item in warehouse["inventory"].values())
    total_available = sum(item["available"] for item in warehouse["inventory"].values())
    total_reserved = sum(item["reserved"] for item in warehouse["inventory"].values())

    low_stock_items = []
    for sku, item in warehouse["inventory"].items():
        if item["available"] <= 10:
            low_stock_items.append({"sku": sku, "available": item["available"], "quantity": item["quantity"]})

    return {
        "warehouse_id": warehouse_id,
        "warehouse_name": warehouse["name"],
        "warehouse_type": warehouse["type"],
        "status": warehouse["status"],
        "total_sku": total_sku,
        "total_quantity": total_quantity,
        "total_available": total_available,
        "total_reserved": total_reserved,
        "low_stock_count": len(low_stock_items),
        "low_stock_items": low_stock_items,
        "last_updated": warehouse["updated_at"],
    }


def list_warehouses() -> dict[str, Any]:
    """获取仓库列表"""
    _ensure_data_dir()
    warehouses = []
    for filename in os.listdir(DATA_DIR):
        if not filename.startswith("warehouse_") or not filename.endswith(".json"):
            continue
        try:
            with open(os.path.join(DATA_DIR, filename), encoding="utf-8") as f:
                wh = json.load(f)
                warehouses.append({
                    "id": wh["id"],
                    "name": wh["name"],
                    "type": wh["type"],
                    "status": wh["status"],
                    "country": wh["location"]["country"],
                    "city": wh["location"]["city"],
                    "total_sku": len(wh["inventory"]),
                    "created_at": wh["created_at"],
                })
        except Exception as e:
            logger.warning("Failed to load warehouse file %s: %s", filename, str(e))

    return {
        "warehouses": warehouses,
        "total": len(warehouses),
        "active_count": sum(1 for w in warehouses if w["status"] == "active"),
    }


def get_inventory_system_status() -> dict[str, Any]:
    """获取库存系统状态"""
    return {
        "status": "running",
        "warehouse_types": WAREHOUSE_TYPES,
        "features": [
            "warehouse_management",
            "inventory_tracking",
            "reserve_release_fulfill",
            "safety_stock",
            "replenishment_suggestion",
            "low_stock_alert",
            "inventory_history",
        ],
        "note": "Multi-warehouse inventory management system is ready. Supports domestic and overseas warehouses, inventory tracking, safety stock, and replenishment suggestions.",
    }
