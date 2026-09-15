"""Response contracts for cross-channel operating analytics."""

from __future__ import annotations

from datetime import date, datetime  # noqa: TC003 - Pydantic resolves these at runtime
from decimal import Decimal  # noqa: TC003 - Pydantic resolves this at runtime
from typing import Literal

from pydantic import BaseModel

BusinessModel = Literal["B2C", "B2B"]
DataQualityStatus = Literal["verified", "partial", "missing"]


class AnalyticsDataQuality(BaseModel):
    status: DataQualityStatus
    cost_coverage_percent: Decimal | None
    notes: list[str]


class ChannelAnalyticsSummary(BaseModel):
    business_model: BusinessModel
    currency: str
    revenue: Decimal
    orders: int
    units: int
    average_order_value: Decimal
    profit_revenue: Decimal
    gross_profit: Decimal | None
    gross_margin_percent: Decimal | None
    refund_amount: Decimal
    advertising_cost: Decimal
    roas: Decimal | None
    data_quality: AnalyticsDataQuality


class CustomerContribution(BaseModel):
    business_model: BusinessModel
    customer_id: str
    customer_name: str
    currency: str
    revenue: Decimal
    orders: int
    profit_revenue: Decimal
    gross_profit: Decimal | None
    gross_margin_percent: Decimal | None
    cost_coverage_percent: Decimal
    credit_limit: Decimal | None = None
    current_balance: Decimal | None = None
    available_credit: Decimal | None = None


class ReceivableAgingSummary(BaseModel):
    business_model: Literal["B2B"] = "B2B"
    currency: str
    current: Decimal
    days_1_30: Decimal
    days_31_60: Decimal
    days_61_90: Decimal
    days_over_90: Decimal
    total: Decimal


class InventoryPerformance(BaseModel):
    product_id: str
    sku: str
    name: str
    b2c_units: int
    b2b_units: int
    total_units: int
    current_inventory: int
    reserved: int
    available: int
    in_transit: int
    turnover_ratio: Decimal | None
    days_of_inventory: Decimal | None
    inventory_basis: str


class ChannelAnalyticsResponse(BaseModel):
    period: dict[str, date]
    generated_at: datetime
    currency_filter: str | None
    reporting_currency: str | None
    channel_summaries: list[ChannelAnalyticsSummary]
    top_customers: list[CustomerContribution]
    receivable_aging: list[ReceivableAgingSummary]
    inventory_performance: list[InventoryPerformance]
    data_quality: AnalyticsDataQuality
    notes: list[str]
