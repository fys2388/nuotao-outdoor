"""
海外仓对接框架服务
支持入库、出库、库存同步、头程发货管理
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
    "overseas_warehouse",
)

INBOUND_STATUSES = ["draft", "shipped", "in_transit", "received", "putaway", "cancelled"]
OUTBOUND_STATUSES = ["pending", "picking", "packed", "shipped", "delivered", "cancelled"]
SHIPMENT_TYPES = ["air", "sea", "express", "truck"]


def _ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def _get_inbound_path(inbound_id: str) -> str:
    return os.path.join(DATA_DIR, f"inbound_{inbound_id}.json")


def _load_inbound(inbound_id: str) -> dict[str, Any] | None:
    path = _get_inbound_path(inbound_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to load inbound %s: %s", inbound_id, str(e))
        return None


def _save_inbound(inbound: dict[str, Any]) -> None:
    _ensure_data_dir()
    path = _get_inbound_path(inbound["id"])
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(inbound, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("Failed to save inbound %s: %s", inbound["id"], str(e))


def create_inbound_shipment(
    warehouse_id: str,
    items: list[dict[str, Any]],
    shipment_type: str = "sea",
    carrier: str = "",
    tracking_number: str = "",
    expected_delivery_date: str = "",
    notes: str = "",
) -> dict[str, Any]:
    """创建入库单（头程发货到海外仓）"""
    now = datetime.utcnow()
    inbound_id = str(uuid4())

    total_quantity = sum(item.get("quantity", 0) for item in items)
    total_value = sum(item.get("quantity", 0) * item.get("unit_value", 0) for item in items)

    inbound = {
        "id": inbound_id,
        "inbound_number": f"IN-{now.strftime('%Y%m%d')}-{inbound_id[:8].upper()}",
        "warehouse_id": warehouse_id,
        "status": "draft",
        "shipment_type": shipment_type,
        "carrier": carrier,
        "tracking_number": tracking_number,
        "items": items,
        "total_quantity": total_quantity,
        "total_value": round(total_value, 2),
        "expected_delivery_date": expected_delivery_date,
        "actual_delivery_date": None,
        "notes": notes,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "history": [{"action": "created", "timestamp": now.isoformat()}],
    }

    _save_inbound(inbound)
    logger.info("Inbound shipment created: id=%s, warehouse=%s, items=%d", inbound_id, warehouse_id, len(items))
    return inbound


def update_inbound_status(
    inbound_id: str,
    new_status: str,
    notes: str = "",
) -> dict[str, Any]:
    """更新入库单状态"""
    if new_status not in INBOUND_STATUSES:
        raise ValueError(f"Invalid status: {new_status}")

    inbound = _load_inbound(inbound_id)
    if not inbound:
        raise ValueError(f"Inbound not found: {inbound_id}")

    now = datetime.utcnow()
    old_status = inbound["status"]
    inbound["status"] = new_status
    inbound["updated_at"] = now.isoformat()

    if new_status == "received":
        inbound["actual_delivery_date"] = now.isoformat()

    inbound["history"].append({
        "action": "status_change",
        "old_status": old_status,
        "new_status": new_status,
        "timestamp": now.isoformat(),
        "notes": notes,
    })

    _save_inbound(inbound)
    return inbound


def create_outbound_order(
    warehouse_id: str,
    order_number: str,
    items: list[dict[str, Any]],
    shipping_address: dict[str, Any],
    shipping_method: str = "standard",
    carrier: str = "",
    tracking_number: str = "",
) -> dict[str, Any]:
    """创建出库单（海外仓发货给终端客户）"""
    now = datetime.utcnow()
    outbound_id = str(uuid4())

    total_quantity = sum(item.get("quantity", 0) for item in items)

    outbound = {
        "id": outbound_id,
        "outbound_number": f"OUT-{now.strftime('%Y%m%d')}-{outbound_id[:8].upper()}",
        "warehouse_id": warehouse_id,
        "order_number": order_number,
        "status": "pending",
        "items": items,
        "total_quantity": total_quantity,
        "shipping_address": shipping_address,
        "shipping_method": shipping_method,
        "carrier": carrier,
        "tracking_number": tracking_number,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "history": [{"action": "created", "timestamp": now.isoformat()}],
    }

    _save_outbound(outbound)
    logger.info("Outbound order created: id=%s, warehouse=%s, order=%s", outbound_id, warehouse_id, order_number)
    return outbound


def _save_outbound(outbound: dict[str, Any]) -> None:
    _ensure_data_dir()
    path = os.path.join(DATA_DIR, f"outbound_{outbound['id']}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(outbound, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("Failed to save outbound %s: %s", outbound["id"], str(e))


def update_outbound_status(
    outbound_id: str,
    new_status: str,
    tracking_number: str = "",
    notes: str = "",
) -> dict[str, Any]:
    """更新出库单状态"""
    if new_status not in OUTBOUND_STATUSES:
        raise ValueError(f"Invalid status: {new_status}")

    path = os.path.join(DATA_DIR, f"outbound_{outbound_id}.json")
    if not os.path.exists(path):
        raise ValueError(f"Outbound not found: {outbound_id}")

    with open(path, encoding="utf-8") as f:
        outbound = json.load(f)

    now = datetime.utcnow()
    old_status = outbound["status"]
    outbound["status"] = new_status
    outbound["updated_at"] = now.isoformat()

    if tracking_number:
        outbound["tracking_number"] = tracking_number

    outbound["history"].append({
        "action": "status_change",
        "old_status": old_status,
        "new_status": new_status,
        "timestamp": now.isoformat(),
        "notes": notes,
    })

    with open(path, "w", encoding="utf-8") as f:
        json.dump(outbound, f, indent=2, ensure_ascii=False, default=str)

    return outbound


def sync_inventory(
    warehouse_id: str,
    inventory_data: dict[str, int],
) -> dict[str, Any]:
    """同步库存（从海外仓系统拉取库存数据）"""
    now = datetime.utcnow()
    sync_id = str(uuid4())

    sync_record = {
        "id": sync_id,
        "warehouse_id": warehouse_id,
        "sync_time": now.isoformat(),
        "items_synced": len(inventory_data),
        "inventory_data": inventory_data,
        "status": "completed",
    }

    _ensure_data_dir()
    path = os.path.join(DATA_DIR, f"sync_{sync_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sync_record, f, indent=2, ensure_ascii=False, default=str)

    logger.info("Inventory synced: warehouse=%s, items=%d", warehouse_id, len(inventory_data))
    return sync_record


def get_overseas_warehouse_status() -> dict[str, Any]:
    """获取海外仓对接系统状态"""
    return {
        "status": "running",
        "inbound_statuses": INBOUND_STATUSES,
        "outbound_statuses": OUTBOUND_STATUSES,
        "shipment_types": SHIPMENT_TYPES,
        "features": [
            "inbound_shipment_management",
            "outbound_order_management",
            "inventory_sync",
            "tracking_management",
            "status_history",
        ],
        "note": "Overseas warehouse integration framework is ready. Supports inbound shipments, outbound orders, and inventory synchronization.",
    }
