"""
M5海外仓 + M6 B2B API 端点
覆盖：入库/出库/库存同步、代理商管理/B2B订单/收款记录
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.overseas_warehouse_service import (
    create_inbound_shipment,
    create_outbound_order,
    get_overseas_warehouse_status,
    sync_inventory,
    update_inbound_status,
    update_outbound_status,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/m5-m6", tags=["m5_m6"])


# ============================================
# M5: 海外仓
# ============================================

class InboundShipmentRequest(BaseModel):
    warehouse_id: str = Field(..., description="海外仓ID")
    items: list[dict[str, Any]] = Field(..., description="入库产品列表")
    shipment_type: str = Field("sea", description="运输方式: sea/air/land")
    carrier: str | None = None
    tracking_number: str | None = None
    expected_delivery_date: str | None = None
    notes: str | None = None


@router.post("/overseas-warehouse/inbound", summary="创建入库单")
async def api_create_inbound(req: InboundShipmentRequest) -> dict[str, Any]:
    return create_inbound_shipment(
        warehouse_id=req.warehouse_id,
        items=req.items,
        shipment_type=req.shipment_type,
        carrier=req.carrier or "",
        tracking_number=req.tracking_number or "",
        expected_delivery_date=req.expected_delivery_date or "",
        notes=req.notes or "",
    )


class UpdateStatusRequest(BaseModel):
    status: str = Field(..., description="新状态")
    notes: str | None = None


@router.post("/overseas-warehouse/inbound/{inbound_id}/status", summary="更新入库单状态")
async def api_update_inbound_status(inbound_id: str, req: UpdateStatusRequest) -> dict[str, Any]:
    return update_inbound_status(inbound_id, req.status, req.notes)


class OutboundOrderRequest(BaseModel):
    warehouse_id: str = Field(..., description="海外仓ID")
    order_number: str = Field(..., description="关联订单号")
    items: list[dict[str, Any]] = Field(..., description="出库产品列表")
    shipping_address: dict[str, Any] | None = None
    shipping_method: str = Field("standard", description="运输方式")
    carrier: str | None = None
    tracking_number: str | None = None


@router.post("/overseas-warehouse/outbound", summary="创建出库单")
async def api_create_outbound(req: OutboundOrderRequest) -> dict[str, Any]:
    return create_outbound_order(
        warehouse_id=req.warehouse_id,
        order_number=req.order_number,
        items=req.items,
        shipping_address=req.shipping_address or {},
        shipping_method=req.shipping_method,
        carrier=req.carrier or "",
        tracking_number=req.tracking_number or "",
    )


@router.post("/overseas-warehouse/outbound/{outbound_id}/status", summary="更新出库单状态")
async def api_update_outbound_status(outbound_id: str, req: UpdateStatusRequest) -> dict[str, Any]:
    return update_outbound_status(outbound_id, req.status, req.notes)


@router.post("/overseas-warehouse/{warehouse_id}/sync-inventory", summary="同步海外仓库存")
async def api_sync_inventory(warehouse_id: str) -> dict[str, Any]:
    return sync_inventory(warehouse_id)


@router.get("/overseas-warehouse/status", summary="海外仓系统状态")
async def api_warehouse_status() -> dict[str, Any]:
    return get_overseas_warehouse_status()


# ============================================
# M6: B2B/代理商
# ============================================

LEGACY_B2B_GONE_DETAIL = (
    "Legacy file-based B2B API is retired. Use /api/v1/admin/b2b "
    "or /api/v1/b2b-portal."
)


def _legacy_b2b_gone() -> None:
    raise HTTPException(status_code=410, detail=LEGACY_B2B_GONE_DETAIL)


@router.post("/b2b/agents", summary="创建代理商")
async def api_create_agent() -> dict[str, Any]:
    _legacy_b2b_gone()


@router.get("/b2b/agents", summary="列出代理商")
async def api_list_agents() -> dict[str, Any]:
    _legacy_b2b_gone()


@router.post("/b2b/agents/{agent_id}/status", summary="更新代理商状态")
async def api_update_agent_status(agent_id: str) -> dict[str, Any]:
    _legacy_b2b_gone()


@router.post("/b2b/orders", summary="创建B2B订单")
async def api_create_b2b_order() -> dict[str, Any]:
    _legacy_b2b_gone()


@router.post("/b2b/orders/{order_id}/status", summary="更新B2B订单状态")
async def api_update_b2b_order_status(order_id: str) -> dict[str, Any]:
    _legacy_b2b_gone()


@router.post("/b2b/orders/{order_id}/payment", summary="记录B2B收款")
async def api_record_payment(order_id: str) -> dict[str, Any]:
    _legacy_b2b_gone()


@router.get("/b2b/status", summary="B2B系统状态")
async def api_b2b_status() -> dict[str, Any]:
    _legacy_b2b_gone()
