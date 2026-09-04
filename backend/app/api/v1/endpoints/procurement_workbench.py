"""
代采工作台 API 端点
半自动代采流程：WooCommerce出单 → 采购单生成 → 人工确认 → 1688下单 → 物流回填 → 完成

状态机: pending(待确认) → confirmed(已确认) → ordered(已下单) → shipped(已发货) → completed(已完成)
                                    ↘ cancelled(已取消)
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.purchase_order_service import (
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_CONFIRMED,
    STATUS_INTERNATIONAL_SHIPPED,
    STATUS_ORDERED,
    STATUS_PENDING,
    STATUS_SHIPPED,
    add_international_tracking,
    add_tracking,
    cancel_purchase_order,
    complete_purchase_order,
    confirm_purchase_order,
    get_purchase_order,
    get_purchase_order_stats,
    list_purchase_orders,
    mark_ordered,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/procurement", tags=["procurement-workbench"])


# ============================================
# 请求/响应模型
# ============================================

class StandardResponse(BaseModel):
    """统一响应格式"""
    success: bool = True
    data: Any = None
    error: str | None = None


class MarkOrderedRequest(BaseModel):
    """标记已下单请求"""
    ali1688_order_id: str = Field("", description="1688订单号")
    ali1688_order_url: str = Field("", description="1688订单链接")
    notes: str = Field("", description="备注")


class AddTrackingRequest(BaseModel):
    """添加国内采购物流单号请求（1688供应商→货代/集运仓）"""
    tracking_number: str = Field(..., description="国内物流单号")
    carrier: str = Field("", description="国内快递公司（韵达/中通/圆通等）")
    tracking_url: str = Field("", description="国内物流查询链接")
    notes: str = Field("", description="备注")


class AddInternationalTrackingRequest(BaseModel):
    """添加国际发货物流单号请求（货代/集运仓→海外客户，自动回传WooCommerce）"""
    tracking_number: str = Field(..., description="国际物流单号（4PX/燕文/云途等）")
    carrier: str = Field("", description="国际快递公司")
    tracking_url: str = Field("", description="国际物流查询链接")
    notes: str = Field("", description="备注")


class CancelRequest(BaseModel):
    """取消采购单请求"""
    reason: str = Field("", description="取消原因")


class ConfirmRequest(BaseModel):
    """确认采购单请求"""
    notes: str = Field("", description="备注")


class CompleteRequest(BaseModel):
    """完成采购单请求"""
    notes: str = Field("", description="备注")


# ============================================
# API 端点
# ============================================

@router.get("/stats", summary="获取代采工作台统计")
async def get_procurement_stats() -> StandardResponse:
    """获取采购单统计数据（各状态数量、今日新增、总成本等）"""
    try:
        stats = get_purchase_order_stats()
        return StandardResponse(success=True, data=stats)
    except Exception as e:
        logger.error("Get procurement stats failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orders", summary="采购单列表")
async def get_purchase_order_list(
    status: str = Query(None, description="按状态筛选：pending/confirmed/ordered/shipped/completed/cancelled"),
    limit: int = Query(50, ge=1, le=200, description="每页条数"),
    offset: int = Query(0, ge=0, description="偏移量"),
) -> StandardResponse:
    """获取采购单列表，支持状态筛选和分页"""
    try:
        orders = list_purchase_orders(status=status, limit=limit + offset)
        # 分页
        paginated = orders[offset:offset + limit]
        return StandardResponse(success=True, data={
            "orders": paginated,
            "total": len(orders),
            "limit": limit,
            "offset": offset,
            "has_more": len(orders) > offset + limit,
        })
    except Exception as e:
        logger.error("Get purchase order list failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orders/{po_id}", summary="采购单详情")
async def get_purchase_order_detail(po_id: str) -> StandardResponse:
    """获取采购单详细信息，包含商品明细、客户信息、物流信息等"""
    try:
        order = get_purchase_order(po_id)
        if not order:
            raise HTTPException(status_code=404, detail=f"采购单 {po_id} 不存在")
        return StandardResponse(success=True, data=order)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get purchase order detail failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/orders/{po_id}/confirm", summary="确认采购单")
async def confirm_order(po_id: str, request: ConfirmRequest) -> StandardResponse:
    """确认采购单，状态从 pending → confirmed"""
    try:
        result = confirm_purchase_order(po_id, notes=request.notes)
        if not result:
            raise HTTPException(status_code=404, detail=f"采购单 {po_id} 不存在或状态不允许确认")
        return StandardResponse(success=True, data=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Confirm order failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/orders/{po_id}/order", summary="标记已下单（回填1688订单号）")
async def mark_as_ordered(po_id: str, request: MarkOrderedRequest) -> StandardResponse:
    """标记采购单已下单，回填1688订单号和订单链接，状态 confirmed → ordered"""
    try:
        result = mark_ordered(
            po_id,
            ali1688_order_id=request.ali1688_order_id,
            ali1688_order_url=request.ali1688_order_url,
            notes=request.notes,
        )
        if not result:
            raise HTTPException(status_code=404, detail=f"采购单 {po_id} 不存在或状态不允许标记已下单")
        return StandardResponse(success=True, data=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Mark ordered failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/orders/{po_id}/tracking", summary="添加国内采购物流单号")
async def add_tracking_info(po_id: str, request: AddTrackingRequest) -> StandardResponse:
    """添加国内采购物流单号（1688供应商→货代/集运仓），不回传WooCommerce"""
    try:
        result = add_tracking(
            po_id,
            tracking_number=request.tracking_number,
            carrier=request.carrier,
            tracking_url=request.tracking_url,
            notes=request.notes,
        )
        if not result:
            raise HTTPException(status_code=404, detail=f"采购单 {po_id} 不存在或状态不允许添加国内物流")
        return StandardResponse(success=True, data=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Add domestic tracking failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/orders/{po_id}/international-tracking", summary="添加国际发货物流单号")
async def add_international_tracking_info(po_id: str, request: AddInternationalTrackingRequest) -> StandardResponse:
    """添加国际发货物流单号（货代/集运仓→海外客户），自动回传WooCommerce订单"""
    try:
        result = add_international_tracking(
            po_id,
            tracking_number=request.tracking_number,
            carrier=request.carrier,
            tracking_url=request.tracking_url,
            notes=request.notes,
        )
        if not result:
            raise HTTPException(status_code=404, detail=f"采购单 {po_id} 不存在或状态不允许添加国际物流")
        return StandardResponse(success=True, data=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Add international tracking failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/orders/{po_id}/complete", summary="完成采购单")
async def complete_order(po_id: str, request: CompleteRequest) -> StandardResponse:
    """完成采购单，状态 shipped → completed"""
    try:
        result = complete_purchase_order(po_id, notes=request.notes)
        if not result:
            raise HTTPException(status_code=404, detail=f"采购单 {po_id} 不存在或状态不允许完成")
        return StandardResponse(success=True, data=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Complete order failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/orders/{po_id}/cancel", summary="取消采购单")
async def cancel_order(po_id: str, request: CancelRequest) -> StandardResponse:
    """取消采购单，pending/confirmed/ordered 状态可取消"""
    try:
        result = cancel_purchase_order(po_id, reason=request.reason)
        if not result:
            raise HTTPException(status_code=404, detail=f"采购单 {po_id} 不存在或状态不允许取消")
        return StandardResponse(success=True, data=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Cancel order failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orders/{po_id}/1688-links", summary="获取采购单的1688商品链接")
async def get_1688_links(po_id: str) -> StandardResponse:
    """获取采购单中所有商品的1688链接，用于一键打开下单"""
    try:
        order = get_purchase_order(po_id)
        if not order:
            raise HTTPException(status_code=404, detail=f"采购单 {po_id} 不存在")

        items = order.get("items", [])
        links = []
        for item in items:
            url = item.get("ali1688_url", "")
            if url:
                links.append({
                    "woo_product_id": item.get("woo_product_id"),
                    "woo_name": item.get("woo_name"),
                    "quantity": item.get("quantity"),
                    "unit_cost": item.get("unit_cost"),
                    "ali1688_product_id": item.get("ali1688_product_id"),
                    "ali1688_url": url,
                    "ali1688_supplier": item.get("ali1688_supplier"),
                })

        return StandardResponse(success=True, data={
            "po_id": po_id,
            "total_items": len(items),
            "mapped_items": len(links),
            "unmapped_items": len(items) - len(links),
            "links": links,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get 1688 links failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))
