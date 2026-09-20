"""Schemas for the B2B RFQ, quote, contract, and order-conversion chain."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, Field, PlainSerializer

DecimalFloat = Annotated[
    Decimal,
    PlainSerializer(lambda value: float(value), return_type=float, when_used="json"),
]


class B2BRFQItemCreate(BaseModel):
    product_id: str
    quantity: int = Field(ge=1)
    target_unit_price: DecimalFloat | None = Field(default=None, gt=0)
    specifications: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = Field(default=None, max_length=2000)


class B2BRFQCreate(BaseModel):
    agent_id: str
    source: str = Field(default="manual", min_length=1, max_length=24)
    requested_currency: str = Field(default="USD", min_length=3, max_length=8)
    destination_country: str | None = Field(default=None, max_length=8)
    incoterm: str | None = Field(default=None, max_length=16)
    requested_delivery_date: date | None = None
    notes: str | None = Field(default=None, max_length=5000)
    items: list[B2BRFQItemCreate] = Field(min_length=1)


class B2BRFQStatusUpdate(BaseModel):
    status: str = Field(pattern="^(submitted|in_review|quoted|won|lost|cancelled)$")
    reason: str | None = Field(default=None, max_length=1000)


class B2BRFQItemResponse(BaseModel):
    id: str
    product_id: str
    sku_snapshot: str
    product_name_snapshot: str
    requested_quantity: int
    target_unit_price: DecimalFloat | None
    specifications: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None


class B2BRFQResponse(BaseModel):
    id: str
    rfq_number: str
    agent_id: str
    agent_company: str = ""
    customer_account_id: str | None = None
    status: str
    source: str
    requested_currency: str
    destination_country: str | None = None
    incoterm: str | None = None
    requested_delivery_date: date | None = None
    notes: str | None = None
    created_by: str
    assigned_to: str | None = None
    submitted_at: datetime | None = None
    closed_at: datetime | None = None
    items: list[B2BRFQItemResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class B2BRFQListResponse(BaseModel):
    items: list[B2BRFQResponse]
    total: int
    page: int
    page_size: int


class B2BQuoteCreate(BaseModel):
    valid_until: date
    payment_terms_days: int = Field(default=30, ge=0, le=365)
    exchange_rate_to_base: DecimalFloat = Field(default=Decimal("1"), gt=0)
    base_currency: str = Field(default="USD", min_length=3, max_length=8)
    shipping_cost: DecimalFloat = Field(default=Decimal("0"), ge=0)
    tax_amount: DecimalFloat = Field(default=Decimal("0"), ge=0)
    shipping_terms: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=5000)


class B2BQuoteVersionCreate(BaseModel):
    valid_until: date
    notes: str | None = Field(default=None, max_length=5000)


class B2BQuoteStatusUpdate(BaseModel):
    status: str = Field(
        pattern="^(pending_approval|sent|accepted|rejected|expired|cancelled)$"
    )
    reason: str | None = Field(default=None, max_length=1000)


class B2BQuoteItemResponse(BaseModel):
    id: str
    product_id: str
    sku_snapshot: str
    product_name_snapshot: str
    quantity: int
    unit_price: DecimalFloat
    discount_percent: DecimalFloat
    line_subtotal: DecimalFloat
    line_total: DecimalFloat
    price_tier_id: str | None = None
    price_source: str
    cost_snapshot: dict[str, Any] = Field(default_factory=dict)
    specifications: dict[str, Any] = Field(default_factory=dict)


class B2BContractSummary(BaseModel):
    id: str
    contract_number: str
    status: str
    customer_signed_at: datetime | None = None
    company_signed_at: datetime | None = None
    activated_at: datetime | None = None


class B2BQuoteResponse(BaseModel):
    id: str
    quote_number: str
    version_number: int
    rfq_id: str | None = None
    rfq_number: str | None = None
    agent_id: str
    agent_company: str = ""
    customer_account_id: str | None = None
    status: str
    currency: str
    base_currency: str
    exchange_rate_to_base: DecimalFloat
    price_book_version_id: str | None = None
    valid_until: date
    payment_terms_days: int
    incoterm: str | None = None
    shipping_terms: str | None = None
    subtotal: DecimalFloat
    discount_amount: DecimalFloat
    shipping_cost: DecimalFloat
    tax_amount: DecimalFloat
    total: DecimalFloat
    created_by: str
    approved_by: str | None = None
    approved_at: datetime | None = None
    sent_at: datetime | None = None
    accepted_at: datetime | None = None
    rejected_at: datetime | None = None
    rejection_reason: str | None = None
    notes: str | None = None
    items: list[B2BQuoteItemResponse] = Field(default_factory=list)
    contract: B2BContractSummary | None = None
    created_at: datetime
    updated_at: datetime


class B2BQuoteListResponse(BaseModel):
    items: list[B2BQuoteResponse]
    total: int
    page: int
    page_size: int


class B2BContractCreate(BaseModel):
    effective_from: date
    effective_to: date | None = None
    document_url: str | None = Field(default=None, max_length=1000)
    terms: dict[str, Any] = Field(default_factory=dict)


class B2BContractStatusUpdate(BaseModel):
    status: str = Field(pattern="^(pending_signature|cancelled|expired|terminated)$")
    reason: str | None = Field(default=None, max_length=1000)


class B2BContractSignRequest(BaseModel):
    party: str = Field(pattern="^(customer|company)$")
    signed_by: str = Field(min_length=1, max_length=128)


class B2BContractResponse(BaseModel):
    id: str
    contract_number: str
    quote_id: str
    quote_number: str | None = None
    version_number: int | None = None
    agent_id: str
    agent_company: str = ""
    customer_account_id: str | None = None
    status: str
    effective_from: date
    effective_to: date | None = None
    currency: str
    total: DecimalFloat
    document_url: str | None = None
    terms: dict[str, Any] = Field(default_factory=dict)
    created_by: str
    customer_signed_by: str | None = None
    customer_signed_at: datetime | None = None
    company_signed_by: str | None = None
    company_signed_at: datetime | None = None
    activated_at: datetime | None = None
    terminated_at: datetime | None = None
    items: list[B2BQuoteItemResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class B2BContractListResponse(BaseModel):
    items: list[B2BContractResponse]
    total: int
    page: int
    page_size: int


class B2BOrderConversionResponse(BaseModel):
    id: str
    order_number: str
    quote_id: str
    contract_id: str
    status: str
    payment_status: str
    total: DecimalFloat
    currency: str
