"""Marketing intelligence schemas (M3.1)."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

ASSET_TYPES = ("image", "video", "carousel", "text", "other")
CAMPAIGN_STATUSES = ("active", "paused", "completed", "archived")
FEEDBACK_SOURCES = ("email", "review", "social", "support", "survey", "other")
SENTIMENTS = ("positive", "neutral", "negative", "unknown")


class CampaignCreate(BaseModel):
    """Create a campaign (derived metrics are computed when omitted)."""

    platform: Literal["meta", "google", "tiktok", "pinterest", "other"] = "meta"
    campaign_id: str = Field(min_length=1, max_length=128)
    name: str | None = Field(default=None, max_length=255)
    product_id: UUID | None = None
    status: Literal["active", "paused", "completed", "archived"] = "active"
    currency: str = Field(default="USD", max_length=8)
    budget: Decimal = Field(default=Decimal("0"), ge=0)
    spend: Decimal = Field(default=Decimal("0"), ge=0)
    impressions: int = Field(default=0, ge=0)
    clicks: int = Field(default=0, ge=0)
    ctr: Decimal | None = Field(default=None, ge=0, le=1)
    cpc: Decimal | None = Field(default=None, ge=0)
    conversion: int = Field(default=0, ge=0)
    revenue: Decimal = Field(default=Decimal("0"), ge=0)
    roas: Decimal | None = Field(default=None, ge=0)
    started_at: datetime | None = None
    ended_at: datetime | None = None


class CampaignUpdate(BaseModel):
    """Partial campaign update; derived metrics are recomputed."""

    name: str | None = Field(default=None, max_length=255)
    status: Literal["active", "paused", "completed", "archived"] | None = None
    budget: Decimal | None = Field(default=None, ge=0)
    spend: Decimal | None = Field(default=None, ge=0)
    impressions: int | None = Field(default=None, ge=0)
    clicks: int | None = Field(default=None, ge=0)
    conversion: int | None = Field(default=None, ge=0)
    revenue: Decimal | None = Field(default=None, ge=0)
    ctr: Decimal | None = Field(default=None, ge=0, le=1)
    cpc: Decimal | None = Field(default=None, ge=0)
    roas: Decimal | None = Field(default=None, ge=0)
    started_at: datetime | None = None
    ended_at: datetime | None = None


class CampaignOut(BaseModel):
    """A campaign as returned by the API (with derived ROI)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    platform: str
    campaign_id: str
    name: str | None
    product_id: UUID | None
    status: str
    currency: str
    budget: Decimal
    spend: Decimal
    impressions: int
    clicks: int
    ctr: Decimal | None
    cpc: Decimal | None
    conversion: int
    revenue: Decimal
    roas: Decimal | None
    roi: Decimal | None = None
    started_at: datetime | None
    ended_at: datetime | None
    trace_id: str | None
    created_at: datetime
    updated_at: datetime

    @field_serializer("ctr", "cpc", "roas", "roi")
    def _ser_decimal(self, value: Decimal | None) -> str | None:
        """Serialize derived metrics without trailing zeros (e.g. 1.4)."""
        return None if value is None else f"{value.normalize():f}"


class CreativeCreate(BaseModel):
    """Create a creative asset."""

    product_id: UUID | None = None
    platform: Literal["meta", "google", "tiktok", "pinterest", "other"] = "meta"
    asset_type: Literal["image", "video", "carousel", "text", "other"] = "image"
    reference: str | None = Field(default=None, max_length=1024)
    hook: str | None = Field(default=None, max_length=500)
    angle: str | None = Field(default=None, max_length=255)
    copy: str | None = Field(default=None, max_length=2000)
    performance_snapshot: dict[str, Any] = Field(default_factory=dict)
    status: Literal["draft", "active", "archived"] = "draft"


class CreativeUpdate(BaseModel):
    """Partial creative update."""

    reference: str | None = Field(default=None, max_length=1024)
    hook: str | None = Field(default=None, max_length=500)
    angle: str | None = Field(default=None, max_length=255)
    copy: str | None = Field(default=None, max_length=2000)
    performance_snapshot: dict[str, Any] | None = None
    status: Literal["draft", "active", "archived"] | None = None


class CreativeOut(BaseModel):
    """A creative asset as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    product_id: UUID | None
    platform: str
    asset_type: str
    reference: str | None
    hook: str | None
    angle: str | None
    copy: str | None
    performance_snapshot: dict[str, Any]
    status: str
    trace_id: str | None
    created_at: datetime
    updated_at: datetime


class FeedbackCreate(BaseModel):
    """Create a customer feedback record."""

    product_id: UUID | None = None
    source: Literal["email", "review", "social", "support", "survey", "other"] = "other"
    content: str = Field(min_length=1, max_length=4000)
    sentiment: Literal["positive", "neutral", "negative", "unknown"] = "unknown"
    issue_type: str | None = Field(default=None, max_length=32)
    rating: int | None = Field(default=None, ge=1, le=5)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeedbackUpdate(BaseModel):
    """Partial feedback update (append-only content is kept)."""

    sentiment: Literal["positive", "neutral", "negative", "unknown"] | None = None
    issue_type: str | None = Field(default=None, max_length=32)
    rating: int | None = Field(default=None, ge=1, le=5)
    metadata: dict[str, Any] | None = None


class FeedbackOut(BaseModel):
    """A customer feedback record as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    product_id: UUID | None
    source: str
    content: str
    sentiment: str
    issue_type: str | None
    rating: int | None
    metadata: dict[str, Any] = Field(validation_alias="metadata_json")
    trace_id: str | None
    created_at: datetime


class ExperimentCreate(BaseModel):
    """Propose a marketing A/B experiment (status=proposed)."""

    product_id: UUID | None = None
    name: str | None = Field(default=None, max_length=255)
    hypothesis: str = Field(min_length=1, max_length=2000)
    variant_a: dict[str, Any] = Field(default_factory=dict)
    variant_b: dict[str, Any] = Field(default_factory=dict)


class ExperimentStartRequest(BaseModel):
    """Activate an experiment with the executed plan."""

    variant_a: dict[str, Any] = Field(default_factory=dict)
    variant_b: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None


class ExperimentCompleteRequest(BaseModel):
    """Complete an experiment with measured results (A/B)."""

    variant_a_result: dict[str, Any] = Field(default_factory=dict)
    variant_b_result: dict[str, Any] = Field(default_factory=dict)
    winner: str | None = Field(default=None, max_length=16)
    notes: str | None = Field(default=None, max_length=2000)
    completed_at: datetime | None = None


class ExperimentOut(BaseModel):
    """A marketing experiment as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    product_id: UUID | None
    name: str | None
    hypothesis: str
    status: str
    variant_a: dict[str, Any]
    variant_b: dict[str, Any]
    result: dict[str, Any]
    calibration: dict[str, Any]
    trace_id: str | None
    created_at: datetime
    updated_at: datetime

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: str) -> str:
        if value not in ("proposed", "active", "completed"):
            raise ValueError("status must be proposed/active/completed")
        return value
