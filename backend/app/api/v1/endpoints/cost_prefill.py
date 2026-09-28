"""Cost prefill endpoints (PROFIT-001 compliant).

Given outer dimensions + actual weight + category + purchase cost,
compute the full PROFIT-001 landing cost breakdown plus a suggested
selling price, contribution margin, and contribution margin rate.

These endpoints are read-only — they return computed values but do NOT
write to any database tables. The caller (frontend or intake pipeline)
decides whether to persist via ``POST /products/intake`` (which
auto-versions ProductCost and appends an immutable ProductCostSnapshot).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.product import Product, ProductCost
from app.services.cost_prefill_service import (
    CostPrefillResult,
    prefill_landed_cost,
    USD_BASE_EXCHANGE,
    MARKETING_RATE,
    RETURN_RATE,
    FIXED_AMORTIZATION,
    DOMESTIC_HANDLING,
)

router = APIRouter(prefix="/cost-prefill", tags=["cost-prefill"])


# ============================================
# 请求/响应模型
# ============================================

class CostPrefillRequest(BaseModel):
    """Input for the cost prefill calculator."""

    purchase_cost_cny: Decimal | None = Field(
        default=None, ge=0, description="1688 采购价 (CNY)"
    )
    purchase_cost_usd: Decimal | None = Field(
        default=None, ge=0, description="采购价 (USD)"
    )
    weight_kg: Decimal | None = Field(
        default=None, gt=0, description="实际重量 (kg)"
    )
    length_cm: Decimal | None = Field(
        default=None, gt=0, description="外包装长度 (cm)"
    )
    width_cm: Decimal | None = Field(
        default=None, gt=0, description="外包装宽度 (cm)"
    )
    height_cm: Decimal | None = Field(
        default=None, gt=0, description="外包装高度 (cm)"
    )
    category: str = Field(default="户外用品", max_length=64)
    packaging_usd: Decimal | None = Field(
        default=None, ge=0, description="包装费 (USD, 覆盖默认值)"
    )
    handling_usd: Decimal | None = Field(
        default=None, ge=0, description="操作费 (USD, 覆盖默认值)"
    )
    target_margin: Decimal = Field(
        default=Decimal("0.35"),
        ge=0,
        le=0.9,
        description="目标贡献毛利率 (0-1), 用于倒推建议售价",
    )


class CostPrefillResponse(BaseModel):
    """Full PROFIT-001 breakdown + suggested pricing."""

    # PROFIT-001 detail fields
    purchase_cost: str
    domestic_shipping: str
    first_leg_shipping: str
    last_leg_shipping: str
    tax_estimate: str
    packaging: str
    handling: str
    fixed_amortization: str
    payment_fee: str
    marketing_amortization: str
    after_sales_loss: str
    total_landed_cost: str
    total_cost_full: str
    # Suggested pricing
    suggested_selling_price: str
    contribution_margin: str
    contribution_margin_rate: str
    gross_margin: str
    net_margin: str
    break_even_price: str
    # Weight used
    weight_kg_effective: str
    # Metadata
    model_version: str
    rule_version: str
    weight_source: str  # "actual" | "volumetric" | "fallback"


class ProductCostPrefillRequest(BaseModel):
    """Auto-prefill product cost from existing product data."""

    product_id: str = Field(..., description="产品 ID")
    persist: bool = Field(
        default=True, description="是否持久化到数据库 (默认 True)"
    )


class ProductCostPrefillResponse(BaseModel):
    """Auto-prefill result for a product."""

    product_id: str
    product_name: str
    sku: str
    # Original purchase cost (CNY)
    original_purchase_cost_cny: str
    # Calculated cost breakdown
    cost_breakdown: CostPrefillResponse
    # Suggested pricing (CNY)
    suggested_price_cny: str
    # Status
    persisted: bool
    message: str


# ============================================
# API 端点
# ============================================

@router.post(
    "/calculate",
    response_model=CostPrefillResponse,
    summary="Compute PROFIT-001 cost breakdown from outer dimensions",
)
async def calculate_prefill(request: CostPrefillRequest) -> CostPrefillResponse:
    """Deterministic cost prefill — no DB writes.

    Purchase cost is accepted either in CNY (converted at fixed rate)
    or USD. If both are provided, USD wins. Effective weight is
    ``max(actual_weight, volumetric_weight)``; fallback 0.3 kg when
    neither is provided.
    """
    purchase_usd = request.purchase_cost_usd
    if purchase_usd is None:
        if request.purchase_cost_cny is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="必须提供 purchase_cost_usd 或 purchase_cost_cny 之一",
            )
        purchase_usd = (request.purchase_cost_cny / USD_BASE_EXCHANGE).quantize(
            Decimal("0.01")
        )

    dimensions: dict[str, Any] | None = None
    if request.length_cm is not None and request.width_cm is not None and request.height_cm is not None:
        dimensions = {
            "length": float(request.length_cm),
            "width": float(request.width_cm),
            "height": float(request.height_cm),
        }

    result = prefill_landed_cost(
        purchase_cost_usd=purchase_usd,
        weight_kg=request.weight_kg,
        dimensions_cm=dimensions,
        category=request.category,
        packaging=request.packaging_usd,
        handling=request.handling_usd,
    )

    # Determine which weight source won
    if request.weight_kg is None:
        weight_source = "volumetric" if dimensions else "fallback"
    elif dimensions:
        from app.services.cost_prefill_service import _volumetric_weight_kg
        vol = _volumetric_weight_kg(dimensions)
        weight_source = "volumetric" if (vol is not None and vol > request.weight_kg) else "actual"
    else:
        weight_source = "actual"

    return CostPrefillResponse(
        purchase_cost=str(result.purchase_cost),
        domestic_shipping=str(result.domestic_shipping),
        first_leg_shipping=str(result.first_leg_shipping),
        last_leg_shipping=str(result.last_leg_shipping),
        tax_estimate=str(result.tax_estimate),
        packaging=str(result.packaging),
        handling=str(result.handling),
        fixed_amortization=str(result.fixed_amortization),
        payment_fee=str(result.payment_fee),
        marketing_amortization=str(result.marketing_amortization),
        after_sales_loss=str(result.after_sales_loss),
        total_landed_cost=str(result.total_landed_cost),
        total_cost_full=str(result.total_cost_full),
        suggested_selling_price=str(result.suggested_selling_price),
        contribution_margin=str(result.contribution_margin),
        contribution_margin_rate=str(round(result.contribution_margin_rate, 4)),
        gross_margin=str(result.gross_margin),
        net_margin=str(result.net_margin),
        break_even_price=str(result.break_even_price),
        weight_kg_effective=str(result.weight_kg_effective),
        model_version=result.model_version,
        rule_version=result.rule_version,
        weight_source=weight_source,
    )


@router.post(
    "/auto-prefill-product",
    response_model=ProductCostPrefillResponse,
    summary="Auto-prefill product cost from existing product data",
)
async def auto_prefill_product_cost(
    request: ProductCostPrefillRequest,
    db: AsyncSession = Depends(get_db),
) -> ProductCostPrefillResponse:
    """Auto-prefill product cost breakdown from existing product data.

    This endpoint:
    1. Fetches the product from the database
    2. Uses existing purchase cost (or 0 if not set)
    3. Calculates full PROFIT-001 cost breakdown using industry baselines
    4. Optionally persists the calculated costs to the database
    5. Returns the calculated costs and suggested pricing
    """
    # Fetch product
    product = await db.execute(
        select(Product).where(Product.id == request.product_id)
    )
    prod = product.scalar_one_or_none()

    if not prod:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"产品未找到: {request.product_id}",
        )

    # Get purchase cost from meta or cost table
    purchase_cost_cny = Decimal("0")
    if prod.meta and "cost_price" in prod.meta:
        purchase_cost_cny = Decimal(str(prod.meta["cost_price"]))

    if purchase_cost_cny <= 0:
        # Try to get from cost table
        cost_result = await db.execute(
            select(ProductCost).where(ProductCost.product_id == prod.id)
        )
        cost = cost_result.scalar_one_or_none()
        if cost and cost.purchase_cost > 0:
            purchase_cost_cny = cost.purchase_cost

    if purchase_cost_cny <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="产品没有采购成本数据，无法计算成本模型",
        )

    # Convert CNY to USD
    purchase_cost_usd = (purchase_cost_cny / USD_BASE_EXCHANGE).quantize(Decimal("0.01"))

    # Get dimensions and weight from product
    weight_kg = Decimal(str(prod.weight_kg)) if prod.weight_kg else None
    dimensions = prod.dimensions if prod.dimensions else None

    # Calculate cost breakdown
    result = prefill_landed_cost(
        purchase_cost_usd=purchase_cost_usd,
        weight_kg=weight_kg,
        dimensions_cm=dimensions,
        category=prod.category or "户外用品",
    )

    # Persist to database if requested
    persisted = False
    if request.persist:
        cost_result = await db.execute(
            select(ProductCost).where(ProductCost.product_id == prod.id)
        )
        cost = cost_result.scalar_one_or_none()

        if cost:
            # Update existing cost
            cost.domestic_shipping = result.domestic_shipping
            cost.first_leg_shipping = result.first_leg_shipping
            cost.last_leg_shipping = result.last_leg_shipping
            cost.packaging = result.packaging
            cost.tax_estimate = result.tax_estimate
            cost.handling = result.handling
            cost.total_landed_cost = result.total_landed_cost
            cost.payment_fee = result.payment_fee
            cost.marketing_amortization = result.marketing_amortization
            cost.after_sales_loss = result.after_sales_loss
            cost.total_cost = result.total_cost_full
            cost.version = "v2-auto"
        else:
            # Create new cost
            new_cost = ProductCost(
                product_id=prod.id,
                currency="USD",
                purchase_cost=purchase_cost_usd,
                domestic_shipping=result.domestic_shipping,
                first_leg_shipping=result.first_leg_shipping,
                last_leg_shipping=result.last_leg_shipping,
                packaging=result.packaging,
                tax_estimate=result.tax_estimate,
                handling=result.handling,
                total_landed_cost=result.total_landed_cost,
                version="v2-auto",
                payment_fee=result.payment_fee,
                marketing_amortization=result.marketing_amortization,
                after_sales_loss=result.after_sales_loss,
                total_cost=result.total_cost_full,
            )
            db.add(new_cost)

        await db.commit()
        persisted = True

    # Calculate suggested price in CNY
    suggested_price_cny = (result.suggested_selling_price * USD_BASE_EXCHANGE).quantize(Decimal("0.01"))

    return ProductCostPrefillResponse(
        product_id=str(prod.id),
        product_name=prod.name,
        sku=prod.sku,
        original_purchase_cost_cny=str(purchase_cost_cny),
        cost_breakdown=CostPrefillResponse(
            purchase_cost=str(result.purchase_cost),
            domestic_shipping=str(result.domestic_shipping),
            first_leg_shipping=str(result.first_leg_shipping),
            last_leg_shipping=str(result.last_leg_shipping),
            tax_estimate=str(result.tax_estimate),
            packaging=str(result.packaging),
            handling=str(result.handling),
            fixed_amortization=str(result.fixed_amortization),
            payment_fee=str(result.payment_fee),
            marketing_amortization=str(result.marketing_amortization),
            after_sales_loss=str(result.after_sales_loss),
            total_landed_cost=str(result.total_landed_cost),
            total_cost_full=str(result.total_cost_full),
            suggested_selling_price=str(result.suggested_selling_price),
            contribution_margin=str(result.contribution_margin),
            contribution_margin_rate=str(round(result.contribution_margin_rate, 4)),
            gross_margin=str(result.gross_margin),
            net_margin=str(result.net_margin),
            break_even_price=str(result.break_even_price),
            weight_kg_effective=str(result.weight_kg_effective),
            model_version=result.model_version,
            rule_version=result.rule_version,
            weight_source="actual" if weight_kg else ("volumetric" if dimensions else "fallback"),
        ),
        suggested_price_cny=str(suggested_price_cny),
        persisted=persisted,
        message="成本模型已自动计算" + ("并保存到数据库" if persisted else ""),
    )
