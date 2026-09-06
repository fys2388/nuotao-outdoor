"""AI能力深化 API 端点"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.ai_capability_service import (
    run_sourcing_model,
    generate_customer_reply,
    calculate_dynamic_price,
    get_ai_capability_status,
)

router = APIRouter(prefix="/ai-capability", tags=["AI能力深化"])


# ========== 请求模型 ==========

class SourcingModelRequest(BaseModel):
    product_name: str
    category: str = ""
    price: float = Field(0, ge=0)
    cost: float = Field(0, ge=0)
    competition_level: str = "medium"  # low/medium/high
    market_demand: str = "medium"  # low/medium/high
    seasonality: str = "year-round"  # year-round/seasonal/holiday


class CustomerReplyRequest(BaseModel):
    customer_message: str
    order_id: str = ""
    customer_name: str = ""
    context: dict[str, Any] | None = None


class DynamicPricingRequest(BaseModel):
    product_id: str
    base_price: float = Field(..., gt=0)
    cost: float = Field(..., ge=0)
    current_inventory: int = Field(0, ge=0)
    sales_velocity: float = Field(0, ge=0)
    competitor_price: float = Field(0, ge=0)
    demand_level: str = "medium"  # low/medium/high
    season_factor: float = Field(1.0, gt=0, le=2)


# ========== API 端点 ==========

@router.get("/status")
async def get_status() -> dict[str, Any]:
    """获取AI能力深化系统状态"""
    return get_ai_capability_status()


@router.post("/sourcing-model")
async def sourcing_model(req: SourcingModelRequest) -> dict[str, Any]:
    """运行选品模型，评估产品市场潜力和盈利能力"""
    try:
        result = run_sourcing_model(
            product_name=req.product_name,
            category=req.category,
            price=req.price,
            cost=req.cost,
            competition_level=req.competition_level,
            market_demand=req.market_demand,
            seasonality=req.seasonality,
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/customer-reply")
async def customer_reply(req: CustomerReplyRequest) -> dict[str, Any]:
    """生成客服自动回复"""
    try:
        result = generate_customer_reply(
            customer_message=req.customer_message,
            order_id=req.order_id,
            customer_name=req.customer_name,
            context=req.context,
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dynamic-pricing")
async def dynamic_pricing(req: DynamicPricingRequest) -> dict[str, Any]:
    """计算动态定价建议"""
    try:
        result = calculate_dynamic_price(
            product_id=req.product_id,
            base_price=req.base_price,
            cost=req.cost,
            current_inventory=req.current_inventory,
            sales_velocity=req.sales_velocity,
            competitor_price=req.competitor_price,
            demand_level=req.demand_level,
            season_factor=req.season_factor,
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
