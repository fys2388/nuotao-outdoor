"""Customer intelligence schemas (M3.3).

PII policy: no name/email/phone/address fields exist anywhere in these
schemas - only non-identifying references and behavioral/aggregate data.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

CUSTOMER_ENTRY_TYPES = (
    "purchase_pattern",
    "pain_point",
    "segment_pattern",
    "refund_pattern",
    "loyalty_pattern",
)
INTERACTION_CHANNELS = ("email", "chat", "review", "social", "other")
SENTIMENTS = ("positive", "neutral", "negative", "unknown")
REVIEW_PLATFORMS = ("shopify", "amazon", "google", "facebook", "woocommerce", "other")
REFUND_CATEGORIES = (
    "quality", "size", "shipping", "damaged", "changed_mind",
    "not_as_described", "other",
)
REFUND_RESOLUTIONS = ("refunded", "partial", "rejected", "escalated")


class CustomerProfileCreate(BaseModel):
    """Create a non-PII customer profile."""

    customer_reference_id: str = Field(min_length=1, max_length=128)
    country: str | None = Field(default=None, max_length=8)
    language: str | None = Field(default=None, max_length=8)
    segment: str | None = Field(default=None, max_length=32)
    tags: list[str] = Field(default_factory=list, max_length=50)
    first_order_at: datetime | None = None
    total_orders: int = Field(default=0, ge=0)
    total_revenue: Decimal = Field(default=Decimal("0"), ge=0)


class CustomerProfileUpdate(BaseModel):
    """Partial profile update (no PII fields)."""

    country: str | None = Field(default=None, max_length=8)
    language: str | None = Field(default=None, max_length=8)
    segment: str | None = Field(default=None, max_length=32)
    tags: list[str] | None = None
    first_order_at: datetime | None = None
    total_orders: int | None = Field(default=None, ge=0)
    total_revenue: Decimal | None = Field(default=None, ge=0)


class CustomerProfileOut(BaseModel):
    """A customer profile as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    customer_reference_id: str
    country: str | None
    language: str | None
    segment: str | None
    tags: list[Any]
    first_order_at: datetime | None
    total_orders: int
    total_revenue: Decimal
    trace_id: str | None
    created_at: datetime
    updated_at: datetime


class InteractionCreate(BaseModel):
    """Create an append-only customer interaction."""

    customer_id: UUID | None = None
    product_id: UUID | None = None
    channel: Literal["email", "chat", "review", "social", "other"] = "other"
    interaction_type: str = Field(default="message", max_length=32)
    content: str = Field(min_length=1, max_length=4000)
    sentiment: Literal["positive", "neutral", "negative", "unknown"] = "unknown"
    metadata: dict[str, Any] = Field(default_factory=dict)


class InteractionUpdate(BaseModel):
    """Partial interaction update (content stays immutable)."""

    sentiment: Literal["positive", "neutral", "negative", "unknown"] | None = None
    interaction_type: str | None = Field(default=None, max_length=32)
    metadata: dict[str, Any] | None = None


class InteractionOut(BaseModel):
    """A customer interaction as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    customer_id: UUID | None
    product_id: UUID | None
    channel: str
    interaction_type: str
    content: str
    sentiment: str
    metadata: dict[str, Any] = Field(validation_alias="metadata_json")
    trace_id: str | None
    created_at: datetime


class ReviewCreate(BaseModel):
    """Create an append-only product review."""

    product_id: UUID | None = None
    platform: Literal["shopify", "amazon", "google", "facebook", "woocommerce", "other"] = "other"
    rating: int = Field(default=5, ge=1, le=5)
    content: str = Field(min_length=1, max_length=4000)
    sentiment: Literal["positive", "neutral", "negative", "unknown"] = "unknown"
    issue_type: str | None = Field(default=None, max_length=32)
    keywords: list[str] = Field(default_factory=list, max_length=30)


class ReviewUpdate(BaseModel):
    """Partial review update (content stays immutable)."""

    sentiment: Literal["positive", "neutral", "negative", "unknown"] | None = None
    issue_type: str | None = Field(default=None, max_length=32)
    keywords: list[str] | None = None


class ReviewOut(BaseModel):
    """A product review as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    product_id: UUID | None
    platform: str
    rating: int
    content: str
    sentiment: str
    issue_type: str | None
    keywords: list[Any]
    trace_id: str | None
    created_at: datetime


class RefundCreate(BaseModel):
    """Create a refund/return case."""

    order_id: UUID | None = None
    product_id: UUID | None = None
    reason: str = Field(min_length=1, max_length=500)
    category: Literal[
        "quality", "size", "shipping", "damaged", "changed_mind", "not_as_described", "other"
    ] = "other"
    amount: Decimal = Field(default=Decimal("0"), ge=0)
    resolution: Literal["refunded", "partial", "rejected", "escalated"] | None = None


class RefundUpdate(BaseModel):
    """Partial refund update."""

    reason: str | None = Field(default=None, max_length=500)
    category: Literal[
        "quality", "size", "shipping", "damaged", "changed_mind", "not_as_described", "other"
    ] | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    resolution: Literal["refunded", "partial", "rejected", "escalated"] | None = None


class RefundOut(BaseModel):
    """A refund case as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    order_id: UUID | None
    product_id: UUID | None
    reason: str
    category: str
    amount: Decimal
    resolution: str | None
    trace_id: str | None
    created_at: datetime
    updated_at: datetime


class RefundStatsOut(BaseModel):
    """Refund statistics aggregated by category."""

    category: str
    case_count: int
    total_amount: Decimal


class CustomerKnowledgeCreate(BaseModel):
    """Create a customer knowledge memory entry."""

    customer_id: UUID | None = None
    product_id: UUID | None = None
    category: str | None = Field(default=None, max_length=64)
    entry_type: Literal[
        "purchase_pattern",
        "pain_point",
        "segment_pattern",
        "refund_pattern",
        "loyalty_pattern",
    ]
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=4000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    source: str = Field(default="manual", max_length=32)
    confidence: Decimal = Field(default=Decimal("0"), ge=0, le=1)


class CustomerKnowledgeOut(BaseModel):
    """A customer knowledge entry as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    customer_id: UUID | None
    product_id: UUID | None
    category: str | None
    entry_type: str
    title: str
    content: str
    tags: list[Any]
    source: str
    confidence: Decimal
    trace_id: str | None
    created_at: datetime
    updated_at: datetime
