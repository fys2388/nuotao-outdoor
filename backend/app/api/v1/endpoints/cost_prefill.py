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

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.cost_prefill_service import (
    CostPrefillResult,
    prefill_landed_cost,
)

router = APIRouter(prefix="/cost-prefill", tags=["cost-prefill"])


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
    payment_fee: str
    marketing_amortization: str
    after_sales_loss: str
    total_landed_cost: str
    # Suggested pricing
    suggested_selling_price: str
    contribution_margin: str
    contribution_margin_rate: str
    # Weight used
    weight_kg_effective: str
    # Metadata
    model_version: str
    rule_version: str
    weight_source: str  # "actual" | "volumetric" | "fallback"


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
        # Import the exchange rate from the service module for consistency
        from app.services.cost_prefill_service import USD_BASE_EXCHANGE
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
        payment_fee=str(result.payment_fee),
        marketing_amortization=str(result.marketing_amortization),
        after_sales_loss=str(result.after_sales_loss),
        total_landed_cost=str(result.total_landed_cost),
        suggested_selling_price=str(result.suggested_selling_price),
        contribution_margin=str(result.contribution_margin),
        contribution_margin_rate=str(round(result.contribution_margin_rate, 4)),
        weight_kg_effective=str(result.weight_kg_effective),
        model_version=result.model_version,
        rule_version=result.rule_version,
        weight_source=weight_source,
    )
