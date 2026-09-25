"""Opportunity API schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.opportunity import OPPORTUNITY_STATUSES, SIGNAL_TYPES


class OpportunityCreate(BaseModel):
    """Create an opportunity (manual entry; no backend inference)."""

    title: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    category: str | None = Field(default=None, max_length=128)
    keywords: list[str] = Field(default_factory=list)
    signal_type: str = Field(default="manual")
    signal_source: dict[str, Any] | None = None
    market_signals: list[Any] = Field(default_factory=list)
    evidence: list[Any] = Field(default_factory=list)
    confidence: Decimal | None = Field(default=None, ge=0, le=100)


class OpportunityUpdate(BaseModel):
    """Partial update. Only fields present are written."""

    title: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    category: str | None = Field(default=None, max_length=128)
    keywords: list[str] | None = None
    status: str | None = Field(default=None, max_length=16)
    confidence: Decimal | None = Field(default=None, ge=0, le=100)
    closed_reason: str | None = Field(default=None, max_length=256)


class OpportunityCandidateIn(BaseModel):
    """Attach one product candidate to an opportunity."""

    product_id: UUID
    link_reason: str | None = Field(default=None, max_length=256)


class OpportunityCandidateOut(BaseModel):
    """Link row plus a summary of the linked product."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    opportunity_id: UUID
    product_id: UUID
    linked_at: datetime
    link_reason: str | None
    # denormalised product summary, filled by the service
    product_sku: str | None = None
    product_name: str | None = None
    product_status: str | None = None
    candidate_status: str | None = None


class OpportunityOut(BaseModel):
    """Opportunity as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    title: str
    description: str | None
    category: str | None
    keywords: list[Any]
    signal_type: str
    signal_source: dict[str, Any] | None
    market_signals: list[Any]
    evidence: list[Any]
    status: str
    confidence: Decimal | None
    closed_at: datetime | None
    closed_reason: str | None
    created_at: datetime
    updated_at: datetime
    # denormalised, filled by the service
    candidate_count: int = 0


class OpportunityDetail(OpportunityOut):
    """Detail view: opportunity plus its linked candidates."""

    candidates: list[OpportunityCandidateOut] = Field(default_factory=list)


class OpportunityMeta(BaseModel):
    """Enum catalogue, so the frontend never hardcodes the vocabularies."""

    statuses: list[str]
    signal_types: list[str]


_OPPORTUNITY_CREATE_FIELDS = ("title", "description", "category", "keywords",
                             "signal_type", "signal_source", "market_signals",
                             "evidence", "confidence")
_OPPORTUNITY_UPDATE_FIELDS = ("title", "description", "category", "keywords",
                              "status", "confidence", "closed_reason")
_OPPORTUNITY_STATUSES_VALID = set(OPPORTUNITY_STATUSES)
_SIGNAL_TYPES_VALID = set(SIGNAL_TYPES)
