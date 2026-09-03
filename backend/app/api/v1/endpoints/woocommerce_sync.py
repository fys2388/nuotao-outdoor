"""
WooCommerce 数据同步 API 端点
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.woocommerce_sync_service import (
    fetch_woocommerce_orders,
    fetch_woocommerce_products,
    get_sync_status,
    sync_orders_to_dashboard,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/woocommerce-sync", tags=["woocommerce-sync"])


class SyncRequest(BaseModel):
    days: int = Field(30, description="同步最近多少天的订单", ge=1, le=365)
    max_orders: int = Field(500, description="最大同步订单数", ge=1, le=5000)


class FetchOrdersRequest(BaseModel):
    per_page: int = Field(100, ge=1, le=100)
    page: int = Field(1, ge=1)
    status: str = Field("any")
    date_after: str | None = None
    date_before: str | None = None


@router.get("/status")
async def status() -> dict[str, Any]:
    return get_sync_status()


@router.post("/sync-orders")
async def sync_orders(request: SyncRequest) -> dict[str, Any]:
    """同步 WooCommerce 订单到经营看板格式"""
    try:
        result = sync_orders_to_dashboard(days=request.days, max_orders=request.max_orders)
        return result
    except Exception as e:
        logger.exception("Sync orders failed: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Sync orders failed: {e!s}")


@router.post("/fetch-orders")
async def fetch_orders(request: FetchOrdersRequest) -> dict[str, Any]:
    """从 WooCommerce 获取订单列表（原始数据）"""
    try:
        result = fetch_woocommerce_orders(
            per_page=request.per_page,
            page=request.page,
            status=request.status,
            date_after=request.date_after,
            date_before=request.date_before,
        )
        return result
    except Exception as e:
        logger.exception("Fetch orders failed: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Fetch orders failed: {e!s}")


@router.get("/fetch-products")
async def fetch_products(per_page: int = 100, page: int = 1, status: str = "publish") -> dict[str, Any]:
    """从 WooCommerce 获取产品列表"""
    try:
        result = fetch_woocommerce_products(per_page=per_page, page=page, status=status)
        return result
    except Exception as e:
        logger.exception("Fetch products failed: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Fetch products failed: {e!s}")
