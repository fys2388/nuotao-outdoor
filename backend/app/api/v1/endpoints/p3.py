"""
P3 API 端点 - 库存管理、海外仓对接、B2B 代理商管理
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.b2b_service import (
    create_agent,
    create_b2b_order,
    get_b2b_system_status,
    list_agents,
    record_payment,
    update_agent_status,
    update_b2b_order_status,
)
from app.services.inventory_service import (
    calculate_replenishment,
    create_warehouse,
    fulfill_inventory,
    get_inventory_status,
    get_inventory_system_status,
    list_warehouses,
    release_inventory,
    reserve_inventory,
    update_inventory,
)
from app.services.overseas_warehouse_service import (
    create_inbound_shipment,
    create_outbound_order,
    get_overseas_warehouse_status,
    sync_inventory,
    update_inbound_status,
    update_outbound_status,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/p3", tags=["p3"])


# ============================================
# 库存管理端点
# ============================================

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


class InventoryOperationRequest(BaseModel):
    sku: str
    quantity: int
    reason: str = "manual"
    reference_id: str = ""
    order_id: str = ""


class ReplenishmentRequest(BaseModel):
    sku: str
    daily_sales_rate: float
    safety_stock_days: int = 14
    lead_time_days: int = 30
    order_quantity: int = 100


@router.get("/inventory/status")
async def inventory_status() -> dict[str, Any]:
    return get_inventory_system_status()


@router.post("/inventory/warehouses")
async def create_wh(request: CreateWarehouseRequest) -> dict[str, Any]:
    try:
        return {"success": True, "warehouse": create_warehouse(**request.dict())}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/inventory/warehouses")
async def list_wh() -> dict[str, Any]:
    return list_warehouses()


@router.get("/inventory/warehouses/{warehouse_id}")
async def get_wh(warehouse_id: str) -> dict[str, Any]:
    try:
        return get_inventory_status(warehouse_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/inventory/warehouses/{warehouse_id}/update")
async def update_inv(warehouse_id: str, request: InventoryOperationRequest) -> dict[str, Any]:
    try:
        return {"success": True, "result": update_inventory(warehouse_id, request.sku, request.quantity, request.reason, request.reference_id)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/inventory/warehouses/{warehouse_id}/reserve")
async def reserve_inv(warehouse_id: str, request: InventoryOperationRequest) -> dict[str, Any]:
    try:
        return {"success": True, "result": reserve_inventory(warehouse_id, request.sku, request.quantity, request.order_id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/inventory/warehouses/{warehouse_id}/release")
async def release_inv(warehouse_id: str, request: InventoryOperationRequest) -> dict[str, Any]:
    try:
        return {"success": True, "result": release_inventory(warehouse_id, request.sku, request.quantity, request.order_id, request.reason)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/inventory/warehouses/{warehouse_id}/fulfill")
async def fulfill_inv(warehouse_id: str, request: InventoryOperationRequest) -> dict[str, Any]:
    try:
        return {"success": True, "result": fulfill_inventory(warehouse_id, request.sku, request.quantity, request.order_id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/inventory/warehouses/{warehouse_id}/replenishment")
async def replenishment(warehouse_id: str, request: ReplenishmentRequest) -> dict[str, Any]:
    try:
        return {"success": True, "result": calculate_replenishment(warehouse_id, request.sku, request.daily_sales_rate, request.safety_stock_days, request.lead_time_days, request.order_quantity)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================
# 海外仓对接端点
# ============================================

class InboundRequest(BaseModel):
    warehouse_id: str
    items: list[dict[str, Any]]
    shipment_type: str = "sea"
    carrier: str = ""
    tracking_number: str = ""
    expected_delivery_date: str = ""
    notes: str = ""


class OutboundRequest(BaseModel):
    warehouse_id: str
    order_number: str
    items: list[dict[str, Any]]
    shipping_address: dict[str, Any]
    shipping_method: str = "standard"
    carrier: str = ""
    tracking_number: str = ""


class StatusUpdateRequest(BaseModel):
    status: str
    notes: str = ""
    tracking_number: str = ""


class InventorySyncRequest(BaseModel):
    warehouse_id: str
    inventory_data: dict[str, int]


@router.get("/overseas/status")
async def overseas_status() -> dict[str, Any]:
    return get_overseas_warehouse_status()


@router.post("/overseas/inbound")
async def create_inbound(request: InboundRequest) -> dict[str, Any]:
    return {"success": True, "inbound": create_inbound_shipment(**request.dict())}


@router.put("/overseas/inbound/{inbound_id}/status")
async def update_inbound(inbound_id: str, request: StatusUpdateRequest) -> dict[str, Any]:
    try:
        return {"success": True, "inbound": update_inbound_status(inbound_id, request.status, request.notes)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/overseas/outbound")
async def create_outbound(request: OutboundRequest) -> dict[str, Any]:
    return {"success": True, "outbound": create_outbound_order(**request.dict())}


@router.put("/overseas/outbound/{outbound_id}/status")
async def update_outbound(outbound_id: str, request: StatusUpdateRequest) -> dict[str, Any]:
    try:
        return {"success": True, "outbound": update_outbound_status(outbound_id, request.status, request.tracking_number, request.notes)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/overseas/sync-inventory")
async def sync_inv(request: InventorySyncRequest) -> dict[str, Any]:
    return {"success": True, "sync": sync_inventory(request.warehouse_id, request.inventory_data)}


# ============================================
# B2B 代理商管理端点
# ============================================

class CreateAgentRequest(BaseModel):
    name: str
    contact_person: str
    email: str
    phone: str = ""
    country: str = ""
    city: str = ""
    address: str = ""
    tier: str = "bronze"
    commission_rate: float = 5.0
    discount_percent: float = 0
    credit_limit: float = 0
    payment_terms_days: int = 30
    notes: str = ""


class B2BOrderRequest(BaseModel):
    agent_id: str
    items: list[dict[str, Any]]
    shipping_address: dict[str, Any] | None = None
    notes: str = ""


class PaymentRequest(BaseModel):
    amount: float
    payment_method: str = "bank_transfer"


@router.get("/b2b/status")
async def b2b_status() -> dict[str, Any]:
    return get_b2b_system_status()


@router.post("/b2b/agents")
async def create_agent_endpoint(request: CreateAgentRequest) -> dict[str, Any]:
    try:
        return {"success": True, "agent": create_agent(**request.dict())}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/b2b/agents")
async def list_agents_endpoint() -> dict[str, Any]:
    return list_agents()


@router.put("/b2b/agents/{agent_id}/status")
async def update_agent_status_endpoint(agent_id: str, request: StatusUpdateRequest) -> dict[str, Any]:
    try:
        return {"success": True, "agent": update_agent_status(agent_id, request.status)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/b2b/orders")
async def create_b2b_order_endpoint(request: B2BOrderRequest) -> dict[str, Any]:
    try:
        return {"success": True, "order": create_b2b_order(request.agent_id, request.items, request.shipping_address, request.notes)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/b2b/orders/{order_id}/status")
async def update_b2b_order_endpoint(order_id: str, request: StatusUpdateRequest) -> dict[str, Any]:
    try:
        return {"success": True, "order": update_b2b_order_status(order_id, request.status)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/b2b/orders/{order_id}/payment")
async def record_payment_endpoint(order_id: str, request: PaymentRequest) -> dict[str, Any]:
    try:
        return {"success": True, "payment": record_payment(order_id, request.amount, request.payment_method)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
