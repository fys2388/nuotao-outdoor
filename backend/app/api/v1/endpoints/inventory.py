"""
多仓库库存管理 API 端点
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.inventory_service import (
    calculate_replenishment,
    create_warehouse,
    fulfill_inventory,
    get_inventory_status,
    get_inventory_system_status,
    get_sync_history,
    list_warehouses,
    release_inventory,
    reserve_inventory,
    sync_inventory_from_1688,
    sync_inventory_from_woocommerce,
    update_inventory,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/inventory", tags=["inventory"])


class CreateWarehouseRequest(BaseModel):
    name: str
    warehouse_type: str
    country: str
    city: str
    address: str = ""
    contact_person: str = ""
    contact_phone: str = ""
    contact_email: str = ""
    shipping_methods: list[str] | None = None
    handling_days: int = 2


class UpdateInventoryRequest(BaseModel):
    sku: str
    quantity: int
    reason: str = "manual_adjustment"
    reference_id: str = ""


class ReserveInventoryRequest(BaseModel):
    sku: str
    quantity: int
    order_id: str = ""


class ReleaseInventoryRequest(BaseModel):
    sku: str
    quantity: int
    order_id: str = ""
    reason: str = "order_cancelled"


class FulfillInventoryRequest(BaseModel):
    sku: str
    quantity: int
    order_id: str = ""


class ReplenishmentRequest(BaseModel):
    sku: str
    daily_sales_rate: float
    safety_stock_days: int = 14
    lead_time_days: int = 30
    order_quantity: int = 100


@router.get("/status")
async def get_status() -> dict[str, Any]:
    return get_inventory_system_status()


@router.post("/warehouses")
async def create_warehouse_endpoint(request: CreateWarehouseRequest) -> dict[str, Any]:
    try:
        warehouse = create_warehouse(
            name=request.name,
            warehouse_type=request.warehouse_type,
            country=request.country,
            city=request.city,
            address=request.address,
            contact_person=request.contact_person,
            contact_phone=request.contact_phone,
            contact_email=request.contact_email,
            shipping_methods=request.shipping_methods,
            handling_days=request.handling_days,
        )
        return {"success": True, "warehouse": warehouse}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/warehouses")
async def list_warehouses_endpoint() -> dict[str, Any]:
    return list_warehouses()


@router.get("/warehouses/{warehouse_id}")
async def get_warehouse_status(warehouse_id: str) -> dict[str, Any]:
    try:
        return get_inventory_status(warehouse_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/warehouses/{warehouse_id}/inventory")
async def update_inventory_endpoint(warehouse_id: str, request: UpdateInventoryRequest) -> dict[str, Any]:
    try:
        result = update_inventory(warehouse_id, request.sku, request.quantity, request.reason, request.reference_id)
        return {"success": True, "result": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/warehouses/{warehouse_id}/reserve")
async def reserve_endpoint(warehouse_id: str, request: ReserveInventoryRequest) -> dict[str, Any]:
    try:
        result = reserve_inventory(warehouse_id, request.sku, request.quantity, request.order_id)
        return {"success": True, "result": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/warehouses/{warehouse_id}/release")
async def release_endpoint(warehouse_id: str, request: ReleaseInventoryRequest) -> dict[str, Any]:
    try:
        result = release_inventory(warehouse_id, request.sku, request.quantity, request.order_id, request.reason)
        return {"success": True, "result": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/warehouses/{warehouse_id}/fulfill")
async def fulfill_endpoint(warehouse_id: str, request: FulfillInventoryRequest) -> dict[str, Any]:
    try:
        result = fulfill_inventory(warehouse_id, request.sku, request.quantity, request.order_id)
        return {"success": True, "result": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/warehouses/{warehouse_id}/replenishment")
async def replenishment_endpoint(warehouse_id: str, request: ReplenishmentRequest) -> dict[str, Any]:
    try:
        result = calculate_replenishment(
            warehouse_id, request.sku, request.daily_sales_rate,
            request.safety_stock_days, request.lead_time_days, request.order_quantity
        )
        return {"success": True, "result": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================
# 库存同步 API 端点
# ============================================


class SyncRequest(BaseModel):
    """库存同步请求"""
    warehouse_id: str = "default"


@router.post("/sync/woocommerce", summary="从WooCommerce同步库存")
async def sync_woocommerce_inventory(request: SyncRequest) -> dict[str, Any]:
    """
    从WooCommerce同步所有商品的库存数据到本地仓库

    流程：
    1. 从WooCommerce获取所有商品的库存数据
    2. 更新本地仓库库存
    3. 记录同步历史

    Args:
        warehouse_id: 仓库ID（默认default）

    Returns:
        同步结果，包含同步成功/失败的商品数
    """
    try:
        result = sync_inventory_from_woocommerce(warehouse_id=request.warehouse_id)
        return result
    except Exception as e:
        logger.error("Sync WooCommerce inventory failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync/1688", summary="从1688同步供应商库存")
async def sync_1688_inventory(request: SyncRequest) -> dict[str, Any]:
    """
    从1688同步已映射商品的供应商库存数据到本地仓库

    流程：
    1. 获取已映射的1688商品列表
    2. 调用1688 API获取商品库存
    3. 更新本地仓库库存
    4. 记录同步历史

    Args:
        warehouse_id: 仓库ID（默认default）

    Returns:
        同步结果，包含同步成功/失败的商品数
    """
    try:
        result = sync_inventory_from_1688(warehouse_id=request.warehouse_id)
        return result
    except Exception as e:
        logger.error("Sync 1688 inventory failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sync/history", summary="获取库存同步历史记录")
async def get_inventory_sync_history(limit: int = 20) -> dict[str, Any]:
    """
    获取库存同步历史记录

    Args:
        limit: 返回条数（默认20）

    Returns:
        同步历史记录列表
    """
    try:
        result = get_sync_history(limit=limit)
        return result
    except Exception as e:
        logger.error("Get sync history failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))
