"""
物流监控 API 端点
支持物流单创建、轨迹更新、异常预警、物流单查询
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.logistics_monitor_service import (
    create_shipment,
    get_logistics_monitor_status,
    get_shipment,
    list_shipments,
    update_tracking,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/logistics", tags=["logistics"])


# ============================================
# 请求/响应模型
# ============================================

class CreateShipmentRequest(BaseModel):
    """创建物流单请求"""
    order_id: str = Field(..., description="订单 ID")
    tracking_number: str = Field(..., description="物流单号")
    carrier: str = Field(..., description="物流商")
    destination_country: str = Field("US", description="目的国家代码")
    shipping_method: str = Field("standard", description="运输方式：standard/express")
    expected_delivery_days: int | None = Field(None, description="预计送达天数（不提供则使用默认值）", gt=0)


class UpdateTrackingRequest(BaseModel):
    """更新物流轨迹请求"""
    tracking_number: str = Field(..., description="物流单号")
    status: str = Field(..., description="物流状态")
    location: str = Field("", description="当前位置")
    description: str = Field("", description="轨迹描述")


# ============================================
# API 端点
# ============================================

@router.get(
    "/status",
    summary="获取物流监控系统状态",
)
async def get_status() -> dict[str, Any]:
    """获取物流监控系统状态、支持的物流商、预警阈值"""
    return get_logistics_monitor_status()


@router.post(
    "/shipments",
    summary="创建物流单",
)
async def create_shipment_endpoint(
    request: CreateShipmentRequest,
) -> dict[str, Any]:
    """
    创建物流单

    自动计算预计送达时间（根据目的国和运输方式），
    初始化轨迹记录和预警检查。
    """
    try:
        shipment = create_shipment(
            order_id=request.order_id,
            tracking_number=request.tracking_number,
            carrier=request.carrier,
            destination_country=request.destination_country,
            shipping_method=request.shipping_method,
            expected_delivery_days=request.expected_delivery_days,
        )
        return {
            "success": True,
            "shipment": shipment,
            "message": "物流单创建成功",
        }
    except Exception as e:
        logger.exception("Create shipment failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Create shipment failed: {e!s}",
        )


@router.post(
    "/tracking",
    summary="更新物流轨迹",
)
async def update_tracking_endpoint(
    request: UpdateTrackingRequest,
) -> dict[str, Any]:
    """
    更新物流轨迹

    支持的状态：created, picked_up, in_transit, out_for_delivery, delivered, exception, delayed, returned

    更新后自动检查异常和时效预警。
    """
    try:
        shipment = update_tracking(
            tracking_number=request.tracking_number,
            status=request.status,
            location=request.location,
            description=request.description,
        )
        return {
            "success": True,
            "shipment": shipment,
            "alert_count": len(shipment.get("alerts", [])),
            "message": "物流轨迹更新成功",
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.exception("Update tracking failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Update tracking failed: {e!s}",
        )


@router.get(
    "/shipments/{tracking_number}",
    summary="获取物流单详情",
)
async def get_shipment_endpoint(
    tracking_number: str,
) -> dict[str, Any]:
    """
    获取物流单详情

    包含完整轨迹历史、当前状态、预计送达时间、异常预警信息。
    """
    try:
        shipment = get_shipment(tracking_number)
        return {
            "success": True,
            "shipment": shipment,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.exception("Get shipment failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Get shipment failed: {e!s}",
        )


@router.get(
    "/shipments",
    summary="获取物流单列表",
)
async def list_shipments_endpoint(
    status: str | None = None,
    carrier: str | None = None,
    has_alerts: bool | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """
    获取物流单列表

    支持按状态、物流商、是否有预警筛选。
    返回物流单列表和统计信息。
    """
    try:
        result = list_shipments(
            status=status,
            carrier=carrier,
            has_alerts=has_alerts,
            limit=limit,
        )
        return result
    except Exception as e:
        logger.exception("List shipments failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"List shipments failed: {e!s}",
        )
