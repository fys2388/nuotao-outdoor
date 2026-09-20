"""Schemas for versioned B2B pricing."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, PlainSerializer, model_validator

DecimalFloat = Annotated[
    Decimal, PlainSerializer(lambda value: float(value), return_type=float, when_used="json")
]


class B2BPriceBookCreate(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=128)
    currency: str = Field(default="USD", min_length=3, max_length=8)
    is_default: bool = False
    notes: str | None = None


class B2BPriceBookResponse(BaseModel):
    id: str
    code: str
    name: str
    currency: str
    status: str
    is_default: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime


class B2BPriceBookListResponse(BaseModel):
    items: list[B2BPriceBookResponse]
    total: int
    page: int
    page_size: int


class B2BPriceVersionCreate(BaseModel):
    effective_from: date
    effective_to: date | None = None
    source_version_id: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_period(self) -> "B2BPriceVersionCreate":
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be after effective_from")
        return self


class B2BPriceVersionDecision(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class B2BPriceVersionResponse(BaseModel):
    id: str
    price_book_id: str
    version_number: int
    status: str
    effective_from: date
    effective_to: date | None
    submitted_by: str | None
    submitted_at: datetime | None
    approved_by: str | None
    approved_at: datetime | None
    rejection_reason: str | None
    created_by: str
    notes: str | None
    tier_count: int = 0
    created_at: datetime
    updated_at: datetime


class B2BPriceTierCreate(BaseModel):
    product_id: str
    tier: str | None = Field(default=None, pattern="^(bronze|silver|gold|platinum)$")
    agent_id: str | None = None
    min_quantity: int = Field(ge=1)
    max_quantity: int | None = Field(default=None, ge=1)
    unit_price: DecimalFloat = Field(gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=8)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_scope_and_range(self) -> "B2BPriceTierCreate":
        if (self.tier is None) == (self.agent_id is None):
            raise ValueError("exactly one of tier or agent_id is required")
        if self.max_quantity is not None and self.max_quantity <= self.min_quantity:
            raise ValueError("max_quantity must be greater than min_quantity")
        return self


class B2BPriceTierUpdate(BaseModel):
    min_quantity: int | None = Field(default=None, ge=1)
    max_quantity: int | None = Field(default=None, ge=1)
    unit_price: DecimalFloat | None = Field(default=None, gt=0)
    is_active: bool | None = None


class B2BPriceTierResponse(BaseModel):
    id: str
    price_version_id: str
    product_id: str
    product_name: str = ""
    product_sku: str = ""
    tier: str | None
    agent_id: str | None
    agent_company: str | None = None
    min_quantity: int
    max_quantity: int | None
    unit_price: DecimalFloat
    currency: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class B2BPriceVersionDetailResponse(B2BPriceVersionResponse):
    tiers: list[B2BPriceTierResponse] = Field(default_factory=list)


class B2BPricePreviewResponse(BaseModel):
    price_book_id: str
    price_book_version_id: str
    price_tier_id: str
    version_number: int
    source: str
    unit_price: DecimalFloat
    currency: str
    min_quantity: int
    max_quantity: int | None

