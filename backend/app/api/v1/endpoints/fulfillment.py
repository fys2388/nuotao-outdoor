"""
采购/发货 API 端点
支持采购单管理、物流号回填、发货状态跟踪
"""
from __future__ import annotations

import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.fulfillment_service import (
    add_tracking_to_order,
    get_purchase_order_detail,
    get_purchase_orders,
    update_purchase_order_status,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fulfillment", tags=["fulfillment"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


# ============================================
# 请求/响应模型
# ============================================

class UpdatePOStatusRequest(BaseModel):
    """更新采购单状态请求"""
    status: str = Field(..., description="新状态：draft/approved/ordered/partial_received/received/shipped/delivered/completed/cancelled")


class AddTrackingRequest(BaseModel):
    """添加物流追踪请求"""
    order_id: str = Field(..., description="订单 ID（UUID）")
    tracking_number: str = Field(..., description="物流单号")
    carrier: str = Field(..., description="物流公司")
    tracking_url: str | None = Field(None, description="物流追踪链接")


# ============================================
# API 端点
# ============================================

@router.get(
    "/purchase-orders",
    summary="获取采购单列表",
)
async def list_purchase_orders(
    db: DbSession,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """
    获取采购单列表

    - 支持按状态筛选
    - 支持分页
    """
    try:
        result = await get_purchase_orders(
            session=db,
            status=status,
            limit=limit,
            offset=offset,
        )
        return result
    except Exception as e:
        logger.exception("Failed to list purchase orders: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list purchase orders: {e!s}",
        )


@router.get(
    "/purchase-orders/{po_id}",
    summary="获取采购单详情",
)
async def get_purchase_order(
    po_id: str,
    db: DbSession,
) -> dict[str, Any]:
    """获取采购单详情（包含商品项）"""
    try:
        po_uuid = UUID(po_id)
        result = await get_purchase_order_detail(
            session=db,
            po_id=po_uuid,
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.exception("Failed to get purchase order: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get purchase order: {e!s}",
        )


@router.patch(
    "/purchase-orders/{po_id}/status",
    summary="更新采购单状态",
)
async def update_po_status(
    po_id: str,
    request: UpdatePOStatusRequest,
    db: DbSession,
) -> dict[str, Any]:
    """
    更新采购单状态

    状态流转：
    - draft -> approved / cancelled
    - approved -> ordered / cancelled
    - ordered -> partial_received / received / shipped
    - received -> shipped
    - shipped -> delivered / completed
    """
    try:
        po_uuid = UUID(po_id)
        po = await update_purchase_order_status(
            session=db,
            po_id=po_uuid,
            new_status=request.status,
        )
        await db.commit()
        return {
            "success": True,
            "po_id": str(po.id),
            "po_number": po.po_number,
            "status": po.status,
            "message": f"Purchase order status updated to {request.status}",
        }
    except ValueError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        await db.rollback()
        logger.exception("Failed to update PO status: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update PO status: {e!s}",
        )


@router.post(
    "/tracking",
    summary="为订单添加物流追踪信息",
)
async def add_order_tracking(
    request: AddTrackingRequest,
    db: DbSession,
) -> dict[str, Any]:
    """
    为订单添加物流追踪信息

    发货后将物流单号和物流公司回填到订单，
    同时更新订单履约状态为已发货。
    """
    try:
        order_uuid = UUID(request.order_id)
        order = await add_tracking_to_order(
            session=db,
            order_id=order_uuid,
            tracking_number=request.tracking_number,
            carrier=request.carrier,
            tracking_url=request.tracking_url,
        )
        await db.commit()
        return {
            "success": True,
            "order_id": str(order.id),
            "external_order_id": order.external_order_id,
            "fulfillment_status": order.fulfillment_status,
            "tracking_number": request.tracking_number,
            "carrier": request.carrier,
            "message": "Tracking information added successfully",
        }
    except ValueError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        await db.rollback()
        logger.exception("Failed to add tracking: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add tracking: {e!s}",
        )


@router.get(
    "/status",
    summary="获取履约服务状态",
)
async def get_fulfillment_status() -> dict[str, Any]:
    """获取履约服务配置状态"""
    return {
        "service": "fulfillment",
        "status": "running",
        "po_status_flow": {
            "draft": ["approved", "cancelled"],
            "approved": ["ordered", "cancelled"],
            "ordered": ["partial_received", "received", "shipped"],
            "partial_received": ["received"],
            "received": ["shipped"],
            "shipped": ["delivered", "completed"],
            "delivered": ["completed"],
            "completed": [],
            "cancelled": [],
        },
        "auto_generate_po_on_payment": True,
        "cost_ratio": 0.40,
        "message": "Fulfillment service is running. Purchase orders are auto-generated on successful payment.",
    }
