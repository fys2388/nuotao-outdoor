"""
产品上架管理 API 端点
支持：上架队列、批量上架WooCommerce、实验产品跟踪、1688数据替换
"""
from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.product_listing_service import (
    batch_list_to_woocommerce,
    check_experiment_status,
    create_listing_queue,
    get_listing_status,
    list_to_woocommerce,
    replace_1688_mock_data,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/products/listing", tags=["product_listing"])


class ProductItem(BaseModel):
    name: str
    sku: str | None = None
    regular_price: float | None = None
    sale_price: float | None = None
    description: str | None = ""
    short_description: str | None = ""
    stock_quantity: int = 0
    categories: list[dict[str, Any]] = []
    tags: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []


class QueueCreateRequest(BaseModel):
    products: list[ProductItem]
    auto_filter_restricted: bool = True


class BatchListRequest(BaseModel):
    products: list[ProductItem]
    status: str = Field("publish", description="上架状态: publish/draft/pending")
    auto_filter: bool = True


class Replace1688Request(BaseModel):
    product_id: str
    real_data: dict[str, Any]


@router.get("/status")
async def api_listing_status() -> dict[str, Any]:
    """获取上架状态总览"""
    return get_listing_status()


@router.post("/queue")
async def api_create_queue(req: QueueCreateRequest) -> dict[str, Any]:
    """创建上架队列（自动过滤管制物品和实验产品）"""
    products = [p.model_dump() for p in req.products]
    return create_listing_queue(products, auto_filter_restricted=req.auto_filter_restricted)


@router.post("/single")
async def api_single_list(product: ProductItem) -> dict[str, Any]:
    """单个产品上架到 WooCommerce"""
    result = list_to_woocommerce(product.model_dump())
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "上架失败"))
    return result


@router.post("/batch")
async def api_batch_list(req: BatchListRequest) -> dict[str, Any]:
    """批量上架到 WooCommerce"""
    products = [p.model_dump() for p in req.products]
    result = batch_list_to_woocommerce(products, status=req.status, auto_filter=req.auto_filter)
    return result


@router.get("/experiments")
async def api_experiment_status() -> dict[str, Any]:
    """检查实验产品状态"""
    return check_experiment_status()


@router.post("/replace-1688-data")
async def api_replace_1688(req: Replace1688Request) -> dict[str, Any]:
    """替换产品的示例 1688 数据为真实数据"""
    result = replace_1688_mock_data(req.product_id, req.real_data)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "替换失败"))
    return result
