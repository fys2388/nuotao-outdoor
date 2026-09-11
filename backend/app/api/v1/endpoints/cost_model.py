"""
成本模型 API 端点
支持单订单落地成本与毛利测算
"""
from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.cost_model_service import (
    calculate_order_cost,
    calculate_order_cost_from_db,
    get_cost_model_status,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cost-model", tags=["cost-model"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


# ============================================
# 请求/响应模型
# ============================================

class OrderItemCost(BaseModel):
    """订单商品项（成本计算用）"""
    product_id: str | None = Field(None, description="产品 ID")
    name: str = Field(..., description="产品名称")
    quantity: int = Field(1, description="数量", gt=0)
    unit_price: float = Field(..., description="单价", gt=0)
    cost_price: float = Field(0, description="成本价（采购价）", ge=0)


class OrderCostRequest(BaseModel):
    """订单成本计算请求"""
    order_id: str | None = Field(None, description="订单 ID")
    order_number: str | None = Field(None, description="订单号")
    total_amount: float = Field(..., description="订单总金额（含运费）", gt=0)
    subtotal: float | None = Field(None, description="商品小计")
    shipping_cost: float = Field(0, description="向客户收取的运费", ge=0)
    currency: str = Field("USD", description="货币代码")
    country_code: str = Field("US", description="目的国家代码")
    items: list[OrderItemCost] = Field(..., description="商品列表")
    payment_method: str | None = Field(None, description="支付方式")
    shipping_weight: float | None = Field(None, description="总重量（kg）", gt=0)


class CostConfigRequest(BaseModel):
    """成本配置（可选覆盖默认值）"""
    payment_fee_rate: float | None = Field(None, description="支付手续费率（如 0.029 = 2.9%）", ge=0, le=1)
    payment_fee_fixed: float | None = Field(None, description="支付手续费固定金额", ge=0)
    marketing_fee_rate: float | None = Field(None, description="营销费用率（如 0.15 = 15%）", ge=0, le=1)
    default_shipping_cost: float | None = Field(None, description="默认运费", ge=0)
    default_duty_rate: float | None = Field(None, description="默认关税率", ge=0, le=1)


class CostCalculationRequest(BaseModel):
    """成本计算请求（包含订单数据和可选成本配置）"""
    order: OrderCostRequest = Field(..., description="订单数据")
    cost_config: CostConfigRequest | None = Field(None, description="成本配置（可选覆盖默认值）")


# ============================================
# API 端点
# ============================================

@router.get(
    "/status",
    summary="获取成本模型状态和配置",
)
async def get_status() -> dict[str, Any]:
    """获取成本模型状态、支持的成本组成、默认配置"""
    return get_cost_model_status()


@router.post(
    "/calculate",
    summary="计算单订单落地成本与毛利",
)
async def calculate_cost(
    request: CostCalculationRequest,
) -> dict[str, Any]:
    """
    计算单订单落地成本与毛利

    成本组成：
    1. 产品成本（采购成本）
    2. 运费（国内 + 头程 + 尾程）
    3. 关税/增值税（根据目的国）
    4. 支付手续费（如 Stripe 2.9% + $0.30）
    5. 营销费用（广告 + 佣金）

    返回：成本明细、毛利、毛利率、盈利状态
    """
    try:
        # 构建订单数据
        order_data = request.order.model_dump()
        if not order_data.get("subtotal"):
            order_data["subtotal"] = order_data["total_amount"]

        # 构建成本配置
        config = {}
        if request.cost_config:
            config = {k: v for k, v in request.cost_config.model_dump().items() if v is not None}

        result = calculate_order_cost(order_data, config if config else None)
        return result
    except Exception as e:
        logger.exception("Calculate order cost failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Calculate order cost failed: {e!s}",
        )


@router.get(
    "/order/{order_id}",
    summary="从数据库读取订单并计算成本",
)
async def calculate_order_cost_db(
    order_id: str,
    db: DbSession,
) -> dict[str, Any]:
    """
    从数据库读取订单并计算落地成本与毛利

    Args:
        order_id: 订单 ID（UUID 格式）
    """
    try:
        from uuid import UUID as _UUID

        order_uuid = _UUID(order_id)
        result = await calculate_order_cost_from_db(db, order_uuid)
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.exception("Calculate order cost from DB failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Calculate order cost from DB failed: {e!s}",
        )


class BatchCostCalculationRequest(BaseModel):
    """批量成本计算请求"""
    orders: list[OrderCostRequest] = Field(..., description="订单数据列表")
    cost_config: CostConfigRequest | None = Field(None, description="成本配置（可选覆盖默认值）")


@router.post(
    "/batch-calculate",
    summary="批量计算多个订单的成本",
)
async def batch_calculate_cost(
    request: BatchCostCalculationRequest,
) -> dict[str, Any]:
    """
    批量计算多个订单的落地成本与毛利

    返回每个订单的成本明细和汇总统计
    """
    try:
        config = {}
        if request.cost_config:
            config = {k: v for k, v in request.cost_config.model_dump().items() if v is not None}

        results = []
        total_revenue = 0.0
        total_cost = 0.0
        total_profit = 0.0

        for order_request in request.orders:
            order_data = order_request.model_dump()
            if not order_data.get("subtotal"):
                order_data["subtotal"] = order_data["total_amount"]

            result = calculate_order_cost(order_data, config if config else None)
            results.append(result)

            total_revenue += result["revenue"]["total_amount"]
            total_cost += result["costs"]["total_cost"]
            total_profit += result["profit"]["gross_profit"]

        # 汇总统计
        overall_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0

        return {
            "orders": results,
            "summary": {
                "order_count": len(results),
                "total_revenue": round(total_revenue, 2),
                "total_cost": round(total_cost, 2),
                "total_profit": round(total_profit, 2),
                "overall_margin_percent": round(overall_margin, 1),
            },
        }
    except Exception as e:
        logger.exception("Batch calculate cost failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch calculate cost failed: {e!s}",
        )
