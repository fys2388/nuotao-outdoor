"""Contracts for brand/legal-entity attribution and consolidated reporting."""

from __future__ import annotations

from datetime import date, datetime  # noqa: TC003 - Pydantic resolves runtime
from decimal import Decimal  # noqa: TC003 - Pydantic resolves runtime
from typing import Any, Literal

from pydantic import BaseModel, Field

MasterStatus = Literal["active", "inactive"]
AttributionEntityType = Literal["b2c_order", "b2b_order", "b2b_invoice"]
EliminationStatus = Literal["not_applicable", "pending", "approved", "rejected"]


class LegalEntityCreate(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=1, max_length=128)
    legal_name: str = Field(min_length=1, max_length=255)
    country: str = Field(min_length=2, max_length=8)
    functional_currency: str = Field(min_length=3, max_length=8)
    status: MasterStatus = "active"
    notes: str | None = Field(default=None, max_length=2000)


class LegalEntityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    legal_name: str | None = Field(default=None, min_length=1, max_length=255)
    country: str | None = Field(default=None, min_length=2, max_length=8)
    functional_currency: str | None = Field(default=None, min_length=3, max_length=8)
    status: MasterStatus | None = None
    notes: str | None = Field(default=None, max_length=2000)


class LegalEntityResponse(BaseModel):
    id: str
    code: str
    name: str
    legal_name: str
    country: str
    functional_currency: str
    status: MasterStatus
    notes: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime


class LegalEntityListResponse(BaseModel):
    items: list[LegalEntityResponse]
    total: int


class BrandCreate(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=1, max_length=128)
    status: MasterStatus = "active"
    default_legal_entity_id: str | None = None
    notes: str | None = Field(default=None, max_length=2000)


class BrandUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    status: MasterStatus | None = None
    default_legal_entity_id: str | None = None
    notes: str | None = Field(default=None, max_length=2000)


class BrandResponse(BaseModel):
    id: str
    code: str
    name: str
    status: MasterStatus
    default_legal_entity_id: str | None
    default_legal_entity_name: str | None
    notes: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime


class BrandListResponse(BaseModel):
    items: list[BrandResponse]
    total: int


class ProductBrandAssignRequest(BaseModel):
    brand_id: str


class ProductBrandResponse(BaseModel):
    product_id: str
    sku: str
    brand_id: str
    brand_code: str
    brand_name: str


class ProductBrandGapResponse(BaseModel):
    product_id: str
    sku: str
    name: str
    status: str
    category: str | None
    legacy_brand: str | None
    created_at: datetime


class ProductBrandGapListResponse(BaseModel):
    items: list[ProductBrandGapResponse]
    total: int


class ProductBrandBulkAssignRequest(BaseModel):
    product_ids: list[str] = Field(min_length=1, max_length=200)
    brand_id: str


class ProductBrandBulkAssignItem(BaseModel):
    product_id: str
    sku: str | None
    status: Literal["assigned", "already_assigned", "not_found", "failed"]
    error: str | None


class ProductBrandBulkAssignResponse(BaseModel):
    requested: int
    assigned: int
    skipped: int
    failed: int
    items: list[ProductBrandBulkAssignItem]


class AttributionGapResponse(BaseModel):
    entity_type: AttributionEntityType
    entity_id: str
    reference: str
    occurred_at: datetime
    business_model: Literal["B2C", "B2B"]
    amount: Decimal
    currency: str
    reason: str
    product_count: int
    sample_skus: list[str]
    suggested_brand_id: str | None
    suggested_brand_name: str | None
    suggested_legal_entity_id: str | None
    suggested_legal_entity_name: str | None


class AttributionGapListResponse(BaseModel):
    items: list[AttributionGapResponse]
    total: int


class AttributionReconcileItem(BaseModel):
    entity_type: AttributionEntityType
    entity_id: str
    reference: str
    status: Literal["created", "skipped"]
    reason: str


class AttributionReconcileResponse(BaseModel):
    attempted: int
    created: int
    skipped: int
    items: list[AttributionReconcileItem]


class CommerceAttributionUpsert(BaseModel):
    brand_id: str
    legal_entity_id: str
    is_intercompany: bool = False
    counterparty_legal_entity_id: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class EliminationDecisionRequest(BaseModel):
    elimination_amount: Decimal = Field(gt=0)
    evidence: dict[str, Any] = Field(default_factory=dict)


class EliminationRejectionRequest(BaseModel):
    evidence: dict[str, Any] = Field(default_factory=dict)


class AttributionResponse(BaseModel):
    id: str
    entity_type: AttributionEntityType
    entity_id: str
    brand_id: str | None
    brand_name: str | None
    legal_entity_id: str | None
    legal_entity_name: str | None
    assignment_source: str
    is_intercompany: bool
    counterparty_legal_entity_id: str | None
    counterparty_legal_entity_name: str | None
    elimination_status: EliminationStatus
    elimination_amount: Decimal
    evidence: dict[str, Any]
    assigned_by: str
    approved_by: str | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AttributionListResponse(BaseModel):
    items: list[AttributionResponse]
    total: int


class ConsolidationDataQuality(BaseModel):
    status: Literal["verified", "partial", "missing"]
    attributed_order_percent: Decimal | None
    cost_coverage_percent: Decimal | None
    notes: list[str]


class ConsolidatedPerformanceRow(BaseModel):
    brand_id: str | None
    brand_name: str
    legal_entity_id: str | None
    legal_entity_name: str
    business_model: Literal["B2C", "B2B"]
    currency: str
    gross_revenue: Decimal
    intercompany_revenue: Decimal
    external_revenue: Decimal
    orders: int
    open_receivables: Decimal
    profit_revenue: Decimal
    gross_profit: Decimal | None
    gross_margin_percent: Decimal | None
    cost_coverage_percent: Decimal
    attribution_status: Literal["complete", "partial", "missing"]


class ConsolidatedTotals(BaseModel):
    currency: str | None
    gross_revenue: Decimal | None
    intercompany_revenue: Decimal | None
    external_revenue: Decimal | None
    gross_profit: Decimal | None
    orders: int


class ConsolidatedReportResponse(BaseModel):
    period: dict[str, date]
    generated_at: datetime
    reporting_currency: str | None
    brand_filter: str | None
    legal_entity_filter: str | None
    totals: ConsolidatedTotals
    rows: list[ConsolidatedPerformanceRow]
    data_quality: ConsolidationDataQuality
    notes: list[str]
