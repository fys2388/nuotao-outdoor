"""
物流监控服务
支持物流轨迹同步、时效异常预警、物流状态管理
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

# 物流数据存储路径
DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "logistics",
)

# 物流状态
SHIPMENT_STATUSES = [
    "created",        # 已创建
    "picked_up",      # 已揽收
    "in_transit",     # 运输中
    "out_for_delivery",  # 派送中
    "delivered",      # 已签收
    "exception",      # 异常
    "delayed",        # 延迟
    "returned",       # 已退回
]

# 物流商
CARRIERS = [
    "DHL eCommerce",
    "DHL Express",
    "UPS",
    "FedEx",
    "USPS",
    "Royal Mail",
    "Deutsche Post",
    "Correos",
    "China Post",
    "Yanwen",
    "4PX",
]

# 默认时效配置（天）
DEFAULT_DELIVERY_TIMES = {
    "US": {"standard": 10, "express": 5},
    "DE": {"standard": 12, "express": 6},
    "FR": {"standard": 12, "express": 6},
    "GB": {"standard": 10, "express": 5},
    "CA": {"standard": 12, "express": 6},
    "AU": {"standard": 14, "express": 7},
    "ES": {"standard": 14, "express": 7},
    "default": {"standard": 14, "express": 7},
}

# 异常预警阈值
ALERT_THRESHOLDS = {
    "delay_warning_hours": 24,      # 延迟超过 24 小时预警
    "delay_critical_hours": 72,     # 延迟超过 72 小时严重预警
    "no_update_hours": 48,          # 超过 48 小时无更新预警
    "exception_statuses": ["exception", "returned"],  # 异常状态
}


def _ensure_data_dir() -> None:
    """确保数据目录存在"""
    os.makedirs(DATA_DIR, exist_ok=True)


def _get_shipment_path(tracking_number: str) -> str:
    """获取物流单数据文件路径"""
    return os.path.join(DATA_DIR, f"{tracking_number}.json")


def _load_shipment(tracking_number: str) -> dict[str, Any] | None:
    """加载物流单数据"""
    path = _get_shipment_path(tracking_number)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to load shipment %s: %s", tracking_number, str(e))
        return None


def _save_shipment(shipment: dict[str, Any]) -> None:
    """保存物流单数据"""
    _ensure_data_dir()
    path = _get_shipment_path(shipment["tracking_number"])
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(shipment, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("Failed to save shipment %s: %s", shipment["tracking_number"], str(e))


def create_shipment(
    order_id: str,
    tracking_number: str,
    carrier: str,
    destination_country: str = "US",
    shipping_method: str = "standard",
    expected_delivery_days: int | None = None,
) -> dict[str, Any]:
    """
    创建物流单

    Args:
        order_id: 订单 ID
        tracking_number: 物流单号
        carrier: 物流商
        destination_country: 目的国家
        shipping_method: 运输方式（standard/express）
        expected_delivery_days: 预计送达天数（不提供则使用默认值）

    Returns:
        物流单数据
    """
    # 计算预计送达时间
    if expected_delivery_days is None:
        country_times = DEFAULT_DELIVERY_TIMES.get(
            destination_country.upper(),
            DEFAULT_DELIVERY_TIMES["default"],
        )
        expected_delivery_days = country_times.get(shipping_method, country_times["standard"])

    now = datetime.utcnow()
    expected_delivery = now + timedelta(days=expected_delivery_days)

    shipment = {
        "id": str(uuid4()),
        "order_id": order_id,
        "tracking_number": tracking_number,
        "carrier": carrier,
        "destination_country": destination_country.upper(),
        "shipping_method": shipping_method,
        "status": "created",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "shipped_at": None,
        "expected_delivery_at": expected_delivery.isoformat(),
        "delivered_at": None,
        "tracking_history": [
            {
                "timestamp": now.isoformat(),
                "status": "created",
                "location": "Origin warehouse",
                "description": "Shipment created, waiting for pickup",
            }
        ],
        "alerts": [],
        "expected_delivery_days": expected_delivery_days,
    }

    _save_shipment(shipment)
    logger.info("Shipment created: %s, order=%s, carrier=%s", tracking_number, order_id, carrier)
    return shipment


def update_tracking(
    tracking_number: str,
    status: str,
    location: str = "",
    description: str = "",
) -> dict[str, Any]:
    """
    更新物流轨迹

    Args:
        tracking_number: 物流单号
        status: 物流状态
        location: 当前位置
        description: 描述

    Returns:
        更新后的物流单数据
    """
    shipment = _load_shipment(tracking_number)
    if not shipment:
        raise ValueError(f"Shipment not found: {tracking_number}")

    if status not in SHIPMENT_STATUSES:
        raise ValueError(f"Invalid status: {status}. Must be one of {SHIPMENT_STATUSES}")

    now = datetime.utcnow()

    # 更新状态
    shipment["status"] = status
    shipment["updated_at"] = now.isoformat()

    # 如果是已揽收，记录发货时间
    if status == "picked_up" and not shipment.get("shipped_at"):
        shipment["shipped_at"] = now.isoformat()

    # 如果是已签收，记录签收时间
    if status == "delivered":
        shipment["delivered_at"] = now.isoformat()

    # 添加轨迹记录
    tracking_event = {
        "timestamp": now.isoformat(),
        "status": status,
        "location": location,
        "description": description,
    }
    shipment["tracking_history"].append(tracking_event)

    # 检查异常和时效
    alerts = check_shipment_alerts(shipment)
    shipment["alerts"] = alerts

    _save_shipment(shipment)
    logger.info("Tracking updated: %s, status=%s, alerts=%d", tracking_number, status, len(alerts))
    return shipment


def check_shipment_alerts(shipment: dict[str, Any]) -> list[dict[str, Any]]:
    """
    检查物流单异常和时效预警

    Args:
        shipment: 物流单数据

    Returns:
        预警列表
    """
    alerts = []
    now = datetime.utcnow()

    # 1. 检查异常状态
    if shipment["status"] in ALERT_THRESHOLDS["exception_statuses"]:
        alerts.append({
            "type": "status_exception",
            "severity": "critical",
            "message": f"物流状态异常: {shipment['status']}",
            "timestamp": now.isoformat(),
        })

    # 2. 检查是否已签收
    if shipment["status"] == "delivered":
        # 检查是否延迟签收
        if shipment.get("delivered_at") and shipment.get("expected_delivery_at"):
            delivered_at = datetime.fromisoformat(shipment["delivered_at"].replace("Z", "+00:00"))
            expected_at = datetime.fromisoformat(shipment["expected_delivery_at"].replace("Z", "+00:00"))
            delay_hours = (delivered_at - expected_at).total_seconds() / 3600

            if delay_hours > ALERT_THRESHOLDS["delay_critical_hours"]:
                alerts.append({
                    "type": "delivery_delayed_critical",
                    "severity": "critical",
                    "message": f"严重延迟签收: 延迟 {delay_hours:.1f} 小时",
                    "delay_hours": delay_hours,
                    "timestamp": now.isoformat(),
                })
            elif delay_hours > ALERT_THRESHOLDS["delay_warning_hours"]:
                alerts.append({
                    "type": "delivery_delayed_warning",
                    "severity": "warning",
                    "message": f"延迟签收: 延迟 {delay_hours:.1f} 小时",
                    "delay_hours": delay_hours,
                    "timestamp": now.isoformat(),
                })
        return alerts

    # 3. 检查运输中是否延迟
    if shipment["status"] in ["in_transit", "out_for_delivery", "picked_up"]:
        if shipment.get("expected_delivery_at"):
            expected_at = datetime.fromisoformat(shipment["expected_delivery_at"].replace("Z", "+00:00"))
            delay_hours = (now - expected_at).total_seconds() / 3600

            if delay_hours > ALERT_THRESHOLDS["delay_critical_hours"]:
                alerts.append({
                    "type": "in_transit_delayed_critical",
                    "severity": "critical",
                    "message": f"运输严重延迟: 已超过预计送达时间 {delay_hours:.1f} 小时",
                    "delay_hours": delay_hours,
                    "timestamp": now.isoformat(),
                })
            elif delay_hours > ALERT_THRESHOLDS["delay_warning_hours"]:
                alerts.append({
                    "type": "in_transit_delayed_warning",
                    "severity": "warning",
                    "message": f"运输延迟: 已超过预计送达时间 {delay_hours:.1f} 小时",
                    "delay_hours": delay_hours,
                    "timestamp": now.isoformat(),
                })

    # 4. 检查长时间无更新
    if shipment["tracking_history"]:
        last_update = datetime.fromisoformat(
            shipment["tracking_history"][-1]["timestamp"].replace("Z", "+00:00")
        )
        no_update_hours = (now - last_update).total_seconds() / 3600

        if no_update_hours > ALERT_THRESHOLDS["no_update_hours"] and shipment["status"] not in ["delivered", "exception"]:
            alerts.append({
                "type": "no_tracking_update",
                "severity": "warning",
                "message": f"长时间无物流更新: 已 {no_update_hours:.1f} 小时无更新",
                "no_update_hours": no_update_hours,
                "timestamp": now.isoformat(),
            })

    return alerts


def get_shipment(tracking_number: str) -> dict[str, Any]:
    """
    获取物流单详情

    Args:
        tracking_number: 物流单号

    Returns:
        物流单数据
    """
    shipment = _load_shipment(tracking_number)
    if not shipment:
        raise ValueError(f"Shipment not found: {tracking_number}")

    # 实时检查异常
    alerts = check_shipment_alerts(shipment)
    shipment["alerts"] = shipment.get("alerts", []) + [
        a for a in alerts if a["type"] not in [x.get("type") for x in shipment.get("alerts", [])]
    ]

    return shipment


def list_shipments(
    status: str | None = None,
    carrier: str | None = None,
    has_alerts: bool | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """
    获取物流单列表

    Args:
        status: 按状态筛选
        carrier: 按物流商筛选
        has_alerts: 是否有预警
        limit: 返回数量限制

    Returns:
        物流单列表和统计
    """
    _ensure_data_dir()

    shipments = []
    for filename in os.listdir(DATA_DIR):
        if not filename.endswith(".json"):
            continue
        try:
            with open(os.path.join(DATA_DIR, filename), encoding="utf-8") as f:
                shipment = json.load(f)

            # 筛选
            if status and shipment.get("status") != status:
                continue
            if carrier and shipment.get("carrier") != carrier:
                continue
            if has_alerts is not None:
                alert_count = len(shipment.get("alerts", []))
                if has_alerts and alert_count == 0:
                    continue
                if not has_alerts and alert_count > 0:
                    continue

            shipments.append(shipment)
        except Exception as e:
            logger.warning("Failed to load shipment file %s: %s", filename, str(e))

    # 按更新时间排序
    shipments.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    shipments = shipments[:limit]

    # 统计
    stats = {
        "total": len(shipments),
        "by_status": {},
        "with_alerts": sum(1 for s in shipments if len(s.get("alerts", [])) > 0),
        "delivered": sum(1 for s in shipments if s.get("status") == "delivered"),
        "in_transit": sum(1 for s in shipments if s.get("status") in ["in_transit", "out_for_delivery"]),
        "exception": sum(1 for s in shipments if s.get("status") in ["exception", "delayed", "returned"]),
    }

    for s in shipments:
        status_name = s.get("status", "unknown")
        stats["by_status"][status_name] = stats["by_status"].get(status_name, 0) + 1

    return {
        "shipments": shipments,
        "stats": stats,
    }


def get_logistics_monitor_status() -> dict[str, Any]:
    """获取物流监控系统状态"""
    return {
        "status": "running",
        "supported_carriers": CARRIERS,
        "shipment_statuses": SHIPMENT_STATUSES,
        "default_delivery_times": DEFAULT_DELIVERY_TIMES,
        "alert_thresholds": ALERT_THRESHOLDS,
        "features": [
            "shipment_creation",
            "tracking_update",
            "delivery_time_estimation",
            "delay_alert",
            "exception_detection",
            "no_update_alert",
        ],
        "note": "Logistics monitoring system is ready. Supports tracking synchronization, delivery time estimation, and anomaly alerts.",
    }
