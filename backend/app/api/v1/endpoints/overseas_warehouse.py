"""海外仓对接 API 端点"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.overseas_warehouse_service import (
    create_inbound_shipment,
    update_inbound_status,
    create_outbound_order,
    update_outbound_status,
    sync_inventory,
    get_overseas_warehouse_status,
)

router = APIRouter(prefix="/overseas-warehouse", tags=["海外仓对接"])


# ========== 请求模型 ==========

class InboundItem(BaseModel):
    sku: str
    product_name: str = ""
    quantity: int = Field(..., ge=1)
    unit_value: float = Field(0, ge=0)


class CreateInboundRequest(BaseModel):
    warehouse_id: str = "default-overseas"
    items: list[InboundItem]
    shipment_type: str = "sea"  # air/sea/express/truck
    carrier: str = ""
    tracking_number: str = ""
    expected_delivery_date: str = ""
    notes: str = ""


class UpdateInboundStatusRequest(BaseModel):
    status: str  # draft/shipped/in_transit/received/putaway/cancelled
    notes: str = ""


class OutboundItem(BaseModel):
    sku: str
    product_name: str = ""
    quantity: int = Field(..., ge=1)


class CreateOutboundRequest(BaseModel):
    warehouse_id: str = "default-overseas"
    order_id: str = ""
    customer_name: str = ""
    customer_address: str = ""
    items: list[OutboundItem]
    carrier: str = ""
    tracking_number: str = ""
    notes: str = ""


class UpdateOutboundStatusRequest(BaseModel):
    status: str  # pending/picking/packed/shipped/delivered/cancelled
    notes: str = ""


class SyncInventoryRequest(BaseModel):
    warehouse_id: str = "default-overseas"


# ========== API 端点 ==========

@router.get("/status")
async def get_status() -> dict[str, Any]:
    """获取海外仓对接系统状态"""
    return get_overseas_warehouse_status()


@router.post("/inbound")
async def create_inbound(req: CreateInboundRequest) -> dict[str, Any]:
    """创建入库单（头程发货到海外仓）"""
    try:
        items = [item.model_dump() for item in req.items]
        result = create_inbound_shipment(
            warehouse_id=req.warehouse_id,
            items=items,
            shipment_type=req.shipment_type,
            carrier=req.carrier,
            tracking_number=req.tracking_number,
            expected_delivery_date=req.expected_delivery_date,
            notes=req.notes,
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/inbound/{inbound_id}/status")
async def update_inbound(inbound_id: str, req: UpdateInboundStatusRequest) -> dict[str, Any]:
    """更新入库单状态"""
    try:
        result = update_inbound_status(inbound_id, req.status, req.notes)
        if result is None:
            raise HTTPException(status_code=404, detail="入库单不存在")
        return {"success": True, "data": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/outbound")
async def create_outbound(req: CreateOutboundRequest) -> dict[str, Any]:
    """创建出库单（海外仓发货给终端客户）"""
    try:
        items = [item.model_dump() for item in req.items]
        result = create_outbound_order(
            warehouse_id=req.warehouse_id,
            order_id=req.order_id,
            customer_name=req.customer_name,
            customer_address=req.customer_address,
            items=items,
            carrier=req.carrier,
            tracking_number=req.tracking_number,
            notes=req.notes,
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/outbound/{outbound_id}/status")
async def update_outbound(outbound_id: str, req: UpdateOutboundStatusRequest) -> dict[str, Any]:
    """更新出库单状态"""
    try:
        result = update_outbound_status(outbound_id, req.status, req.notes)
        if result is None:
            raise HTTPException(status_code=404, detail="出库单不存在")
        return {"success": True, "data": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync-inventory")
async def sync_inventory_endpoint(req: SyncInventoryRequest) -> dict[str, Any]:
    """同步库存（从海外仓系统拉取库存数据）"""
    try:
        result = sync_inventory(req.warehouse_id)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
