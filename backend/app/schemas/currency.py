"""Schemas for auditable currency exchange rates."""

from __future__ import annotations

from datetime import date, datetime  # noqa: TC003 - Pydantic resolves these
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, PlainSerializer

DecimalFloat = Annotated[
    Decimal,
    PlainSerializer(lambda value: float(value), return_type=float, when_used="json"),
]


class ExchangeRateCreate(BaseModel):
    base_currency: str = Field(min_length=3, max_length=8)
    quote_currency: str = Field(min_length=3, max_length=8)
    rate: DecimalFloat = Field(gt=0)
    effective_date: date
    source: str = Field(default="manual", min_length=1, max_length=64)
    source_reference: str | None = Field(default=None, max_length=255)


class ExchangeRateResponse(BaseModel):
    id: str
    base_currency: str
    quote_currency: str
    rate: DecimalFloat
    effective_date: date
    source: str
    source_reference: str | None = None
    created_by: str
    created_at: datetime


class ExchangeRateListResponse(BaseModel):
    items: list[ExchangeRateResponse]
    total: int


class ExchangeRateResolutionResponse(BaseModel):
    base_currency: str
    quote_currency: str
    as_of: date
    rate: DecimalFloat
    effective_date: date
    source: str
    source_reference: str | None = None
