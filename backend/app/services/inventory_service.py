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
            "woocommerce_sync",
            "1688_sync",
        ],
        "note": "Multi-warehouse inventory management system is ready. Supports domestic and overseas warehouses, inventory tracking, safety stock, and replenishment suggestions.",
    }


# ============================================
# 库存同步功能
# ============================================

SYNC_HISTORY_FILE = os.path.join(DATA_DIR, "sync_history.json")


def _load_sync_history() -> list[dict[str, Any]]:
    """加载同步历史记录"""
    if not os.path.exists(SYNC_HISTORY_FILE):
        return []
    try:
        with open(SYNC_HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to load sync history: %s", str(e))
        return []


def _save_sync_history(history: list[dict[str, Any]]) -> None:
    """保存同步历史记录"""
    _ensure_data_dir()
    try:
        with open(SYNC_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history[-100:], f, indent=2, ensure_ascii=False, default=str)  # 只保留最近100条
    except Exception as e:
        logger.error("Failed to save sync history: %s", str(e))


def record_sync_history(
    sync_type: str,
    source: str,
    status: str,
    items_synced: int = 0,
    items_failed: int = 0,
    details: str = "",
) -> dict[str, Any]:
    """
    记录同步历史

    Args:
        sync_type: 同步类型（woocommerce/1688/manual）
        source: 同步来源
        status: 同步状态（success/failed/partial）
        items_synced: 同步成功的商品数
        items_failed: 同步失败的商品数
        details: 详细信息

    Returns:
        同步记录
    """
    record = {
        "id": str(uuid4()),
        "sync_type": sync_type,
        "source": source,
        "status": status,
        "items_synced": items_synced,
        "items_failed": items_failed,
        "details": details,
        "started_at": datetime.utcnow().isoformat(),
        "completed_at": datetime.utcnow().isoformat(),
    }

    history = _load_sync_history()
    history.append(record)
    _save_sync_history(history)

    return record


def get_sync_history(limit: int = 20) -> dict[str, Any]:
    """
    获取同步历史记录

    Args:
        limit: 返回条数

    Returns:
        同步历史记录列表
    """
    history = _load_sync_history()
    return {
        "success": True,
        "data": {
            "history": history[-limit:][::-1],  # 最新的在前
            "total": len(history),
        },
    }


def sync_inventory_from_woocommerce(warehouse_id: str = "default") -> dict[str, Any]:
    """
    从WooCommerce同步库存

    流程：
    1. 从WooCommerce获取所有商品的库存数据
    2. 更新本地仓库库存
    3. 记录同步历史

    Args:
        warehouse_id: 仓库ID（默认default）

    Returns:
        同步结果
    """
    sync_id = str(uuid4())
    start_time = datetime.utcnow()
    logger.info("WooCommerce inventory sync %s started", sync_id)

    try:
        # 从WooCommerce获取商品库存
        from app.services.woocommerce_sync_service import fetch_woocommerce_products

        all_products = []
        page = 1
        while True:
            result = fetch_woocommerce_products(per_page=100, page=page)
            if not result.get("success"):
                break
            products = result.get("products", [])
            if not products:
                break
            all_products.extend(products)
            if len(products) < 100:
                break
            page += 1

        logger.info("WooCommerce inventory sync %s: fetched %d products", sync_id, len(all_products))

        # 更新本地仓库库存
        items_synced = 0
        items_failed = 0
        synced_skus = []

        for product in all_products:
            try:
                sku = product.get("sku", "")
                if not sku:
                    sku = f"WC-{product.get('id')}"

                stock_quantity = product.get("stock_quantity", 0) or 0
                stock_status = product.get("stock_status", "instock")

                # 更新库存
                update_inventory(
                    warehouse_id=warehouse_id,
                    sku=sku,
                    quantity=int(stock_quantity),
                    reason=f"WooCommerce sync - {product.get('name', '')}",
                    reference_id=f"wc-{product.get('id')}",
                )

                items_synced += 1
                synced_skus.append(sku)
            except Exception as e:
                items_failed += 1
                logger.error("WooCommerce inventory sync %s: failed to sync product %s: %s",
                            sync_id, product.get('id'), str(e))

        # 记录同步历史
        status = "success" if items_failed == 0 else "partial"
        record_sync_history(
            sync_type="woocommerce",
            source=f"WooCommerce ({len(all_products)} products)",
            status=status,
            items_synced=items_synced,
            items_failed=items_failed,
            details=f"Synced {items_synced} SKUs from WooCommerce, {items_failed} failed",
        )

        elapsed = (datetime.utcnow() - start_time).total_seconds()
        logger.info("WooCommerce inventory sync %s completed: synced=%d, failed=%d, elapsed=%.2fs",
                    sync_id, items_synced, items_failed, elapsed)

        return {
            "success": True,
            "data": {
                "sync_id": sync_id,
                "status": status,
                "total_products": len(all_products),
                "items_synced": items_synced,
                "items_failed": items_failed,
                "synced_skus": synced_skus[:50],  # 只返回前50个
                "elapsed_seconds": round(elapsed, 2),
            },
        }

    except Exception as e:
        logger.error("WooCommerce inventory sync %s failed: %s", sync_id, str(e))
        record_sync_history(
            sync_type="woocommerce",
            source="WooCommerce",
            status="failed",
            items_synced=0,
            items_failed=0,
            details=str(e),
        )
        return {
            "success": False,
            "error": str(e),
            "data": {"sync_id": sync_id},
        }


def sync_inventory_from_1688(warehouse_id: str = "default") -> dict[str, Any]:
    """
    从1688同步供应商库存

    流程：
    1. 获取已映射的1688商品列表
    2. 调用1688 API获取商品库存
    3. 更新本地仓库库存
    4. 记录同步历史

    Args:
        warehouse_id: 仓库ID（默认default）

    Returns:
        同步结果
    """
    sync_id = str(uuid4())
    start_time = datetime.utcnow()
    logger.info("1688 inventory sync %s started", sync_id)

    try:
        # 获取已映射的1688商品（从产品映射表）
        # 注意：这里简化处理，实际应该从数据库获取已映射的商品
        mapped_products = []

        # 尝试从产品映射服务获取
        try:
            from app.services.product_mapping_service import get_all_mappings
            mappings = get_all_mappings()
            if mappings.get("success"):
                mapped_products = mappings.get("data", {}).get("mappings", [])
        except ImportError:
            logger.warning("Product mapping service not available, using empty list")
        except Exception as e:
            logger.warning("Failed to get product mappings: %s", str(e))

        logger.info("1688 inventory sync %s: found %d mapped products", sync_id, len(mapped_products))

        items_synced = 0
        items_failed = 0
        synced_skus = []

        # 同步每个已映射商品的库存
        for mapping in mapped_products:
            try:
                ali1688_product_id = mapping.get("ali1688_product_id", "")
                woo_sku = mapping.get("woo_sku", "")
                if not ali1688_product_id or not woo_sku:
                    continue

                # 调用1688 API获取商品详情（包含库存信息）
                from app.services.sourcing_1688_service import get_product_detail
                product_detail = get_product_detail(ali1688_product_id)

                if product_detail.get("success"):
                    product = product_detail.get("product", {})
                    # 从商品详情中提取库存信息
                    # 注意：1688 API的库存字段可能不同，这里做兼容处理
                    stock_quantity = product.get("stock", 0) or product.get("available_stock", 0) or 0

                    # 更新本地仓库库存
                    update_inventory(
                        warehouse_id=warehouse_id,
                        sku=woo_sku,
                        quantity=int(stock_quantity),
                        reason=f"1688 sync - {product.get('subject', '')}",
                        reference_id=f"1688-{ali1688_product_id}",
                    )

                    items_synced += 1
                    synced_skus.append(woo_sku)
                else:
                    items_failed += 1
            except Exception as e:
                items_failed += 1
                logger.error("1688 inventory sync %s: failed to sync product %s: %s",
                            sync_id, mapping.get('ali1688_product_id'), str(e))

        # 记录同步历史
        status = "success" if items_failed == 0 else "partial"
        record_sync_history(
            sync_type="1688",
            source=f"1688 ({len(mapped_products)} mapped products)",
            status=status,
            items_synced=items_synced,
            items_failed=items_failed,
            details=f"Synced {items_synced} SKUs from 1688, {items_failed} failed",
        )

        elapsed = (datetime.utcnow() - start_time).total_seconds()
        logger.info("1688 inventory sync %s completed: synced=%d, failed=%d, elapsed=%.2fs",
                    sync_id, items_synced, items_failed, elapsed)

        return {
            "success": True,
            "data": {
                "sync_id": sync_id,
                "status": status,
                "total_mapped_products": len(mapped_products),
                "items_synced": items_synced,
                "items_failed": items_failed,
                "synced_skus": synced_skus[:50],
                "elapsed_seconds": round(elapsed, 2),
            },
        }

    except Exception as e:
        logger.error("1688 inventory sync %s failed: %s", sync_id, str(e))
        record_sync_history(
            sync_type="1688",
            source="1688",
            status="failed",
            items_synced=0,
            items_failed=0,
            details=str(e),
        )
        return {
            "success": False,
            "error": str(e),
            "data": {"sync_id": sync_id},
        }



# --------------------------------------------------------------------------- #
# 库存预警：低于阈值自动生成补货建议
# --------------------------------------------------------------------------- #

async def check_inventory_alerts(
    session,
    *,
    workspace_id,
    warehouse_id: str = "default",
    low_stock_threshold: int = 10,
    auto_create_suggestion: bool = True,
) -> dict:
    """检查库存预警，当库存低于阈值时自动生成补货建议。

    Args:
        session: 数据库会话
        workspace_id: 工作区 ID
        warehouse_id: 仓库 ID
        low_stock_threshold: 低库存阈值
        auto_create_suggestion: 是否自动创建补货建议

    Returns:
        预警结果统计
    """
    from app.models.product import Product
    from app.models.agent_suggestion import AgentSuggestion
    from sqlalchemy import select
    from uuid import uuid4
    import json

    warehouse = _load_warehouse(warehouse_id)
    if not warehouse:
        return {
            "success": False,
            "error": f"仓库 {warehouse_id} 不存在",
            "alerts": [],
            "suggestions_created": 0,
        }

    alerts = []
    suggestions_created = 0

    for sku, item in warehouse["inventory"].items():
        available = item.get("available", 0)
        if available <= low_stock_threshold:
            # 查找对应的产品
            product = (
                await session.execute(
                    select(Product).where(
                        Product.workspace_id == workspace_id,
                        Product.sku == sku,
                    )
                )
            ).scalar_one_or_none()

            product_name = product.name if product else sku
            product_id = str(product.id) if product else None

            alert = {
                "sku": sku,
                "product_name": product_name,
                "product_id": product_id,
                "available": available,
                "quantity": item.get("quantity", 0),
                "reserved": item.get("reserved", 0),
                "urgency": "critical" if available == 0 else "warning" if available <= 5 else "advisory",
            }
            alerts.append(alert)

            # 自动创建补货建议
            if auto_create_suggestion and product_id:
                # 检查是否已存在相同的待审批建议
                existing = (
                    await session.execute(
                        select(AgentSuggestion).where(
                            AgentSuggestion.workspace_id == workspace_id,
                            AgentSuggestion.suggestion_type == "inventory_restock",
                            AgentSuggestion.status == "pending_approval",
                            AgentSuggestion.execution_params["product_id"].astext == product_id,
                        )
                    )
                ).scalar_one_or_none()

                if not existing:
                    suggestion = AgentSuggestion(
                        id=uuid4(),
                        workspace_id=workspace_id,
                        agent_id="inventory-manager",
                        suggestion_type="inventory_restock",
                        title=f"库存预警：{product_name} 库存不足",
                        description=f"产品 {product_name} (SKU: {sku}) 当前可用库存为 {available}，低于阈值 {low_stock_threshold}。建议立即补货。",
                        priority="high" if available <= 5 else "medium",
                        status="pending_approval",
                        risk_level="medium",
                        execution_action="create_purchase_order",
                        execution_params={
                            "product_id": product_id,
                            "sku": sku,
                            "product_name": product_name,
                            "current_stock": available,
                            "recommended_quantity": max(100, low_stock_threshold * 10),
                            "warehouse_id": warehouse_id,
                        },
                        expected_impact=f"避免 {product_name} 缺货，预计补货 {max(100, low_stock_threshold * 10)} 件",
                    )
                    session.add(suggestion)
                    suggestions_created += 1

    await session.commit()

    # 按紧急程度排序
    urgency_order = {"critical": 0, "warning": 1, "advisory": 2}
    alerts.sort(key=lambda x: urgency_order.get(x["urgency"], 3))

    return {
        "success": True,
        "warehouse_id": warehouse_id,
        "threshold": low_stock_threshold,
        "total_alerts": len(alerts),
        "critical_count": sum(1 for a in alerts if a["urgency"] == "critical"),
        "warning_count": sum(1 for a in alerts if a["urgency"] == "warning"),
        "advisory_count": sum(1 for a in alerts if a["urgency"] == "advisory"),
        "suggestions_created": suggestions_created,
        "alerts": alerts[:20],  # 只返回前20个预警
    }
