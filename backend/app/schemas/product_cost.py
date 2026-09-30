"""Schemas for product cost management and per-product profit analysis."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

ZERO = Decimal("0")


class ProductCostUpsertRequest(BaseModel):
    """Manual cost edit. All components are non-negative; international shipping
    falls back to first-leg + last-leg when omitted (matches the intake pipeline)."""

    currency: str = Field(default="USD", max_length=8)
    purchase_cost: Decimal = Field(default=ZERO, ge=0)
    domestic_shipping: Decimal = Field(default=ZERO, ge=0)
    first_leg_shipping: Decimal = Field(default=ZERO, ge=0)
    last_leg_shipping: Decimal = Field(default=ZERO, ge=0)
    international_shipping: Decimal | None = Field(default=None, ge=0)
    packaging: Decimal = Field(default=ZERO, ge=0)
    tax_estimate: Decimal = Field(default=ZERO, ge=0)
    handling: Decimal = Field(default=ZERO, ge=0)
    payment_fee: Decimal = Field(default=ZERO, ge=0)
    marketing_amortization: Decimal = Field(default=ZERO, ge=0)
    after_sales_loss: Decimal = Field(default=ZERO, ge=0)
    notes: dict[str, str] | None = None


class ProductCostOverviewRow(BaseModel):
    product_id: UUID
    sku: str
    name: str
    category: str | None = None
    target_market: str
    status: str
    has_cost: bool
    has_effective_cost: bool = False
    cost_gap_reason: str | None = None
    currency: str | None = None
    version: str | None = None
    valid_from: datetime | None = None
    sale_price: Decimal | None = None
    purchase_cost: Decimal = ZERO
    domestic_shipping: Decimal = ZERO
    first_leg_shipping: Decimal = ZERO
    last_leg_shipping: Decimal = ZERO
    international_shipping: Decimal = ZERO
    packaging: Decimal = ZERO
    tax_estimate: Decimal = ZERO
    handling: Decimal = ZERO
    payment_fee: Decimal = ZERO
    marketing_amortization: Decimal = ZERO
    after_sales_loss: Decimal = ZERO
    total_landed_cost: Decimal = ZERO
    period_cost: Decimal = ZERO
    contribution_margin: Decimal | None = None
    margin_rate: Decimal | None = None


class ProductCostOverview(BaseModel):
    items: list[ProductCostOverviewRow]
    total: int
    known: int
    missing: int
    invalid: int = 0


class ProductCostUpsertResult(BaseModel):
    product_id: UUID
    version: str
    total_landed_cost: Decimal
    snapshot_id: UUID


class ProfitAnalysisRequest(BaseModel):
    """Optional override of the reference sale price for what-if analysis."""

    sale_price: Decimal | None = Field(default=None, gt=0)


class ProfitAnalysisOut(BaseModel):
    product_id: UUID
    sku: str
    name: str
    currency: str
    cost_status: str  # KNOWN / MISSING
    version: str | None = None
    valid_from: datetime | None = None
    sale_price: Decimal | None = None
    total_landed_cost: Decimal = ZERO
    payment_fee: Decimal = ZERO
    marketing_amortization: Decimal = ZERO
    after_sales_loss: Decimal = ZERO
    period_cost: Decimal = ZERO
    total_cost: Decimal | None = None
    contribution_margin: Decimal | None = None
    contribution_margin_rate: Decimal | None = None
    markup_rate: Decimal | None = None
    breakeven_price: Decimal = ZERO


# --------------------------------------------------------------------------- #
# P2-9 cost coverage governance
# --------------------------------------------------------------------------- #


class ProductCostGapRow(BaseModel):
    """One product lacking an effective cost."""

    product_id: UUID
    sku: str
    name: str
    category: str | None = None
    target_market: str
    status: str
    gap_type: str  # missing | invalid
    gap_reason: str | None  # missing | invalid_zero_purchase | invalid_zero_landed
    currency: str | None = None
    version: str | None = None
    valid_from: datetime | None = None
    total_landed_cost: Decimal = ZERO
    sale_price: Decimal | None = None


class ProductCostGapList(BaseModel):
    items: list[ProductCostGapRow]
    total: int
    known: int
    missing: int
    invalid: int


class TransactionCostGapRow(BaseModel):
    """One order whose line items lack effective cost evidence."""

    order_id: UUID
    order_number: str
    received_at: datetime
    currency: str
    gap_item_count: int
    gap_line_total: Decimal
    gap_reasons: list[str]


class TransactionCostGapList(BaseModel):
    items: list[TransactionCostGapRow]
    total: int
    gap_line_count: int
    gap_line_total: Decimal


class BatchCostFillItem(BaseModel):
    """One product cost to fill in a batch."""

    product_id: UUID
    cost: ProductCostUpsertRequest


class BatchCostFillRequest(BaseModel):
    items: list[BatchCostFillItem] = Field(..., min_length=1, max_length=200)


class BatchCostFillResultItem(BaseModel):
    product_id: UUID
    sku: str | None = None
    success: bool
    version: str | None = None
    total_landed_cost: Decimal | None = None
    error: str | None = None


class BatchCostFillResult(BaseModel):
    results: list[BatchCostFillResultItem]
    success_count: int
    failed_count: int
