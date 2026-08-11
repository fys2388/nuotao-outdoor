"""Marketing learning loop schemas (M3.2)."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MARKETING_ENTRY_TYPES = (
    "creative_pattern",
    "copy_pattern",
    "audience_pattern",
    "offer_pattern",
    "failure_pattern",
)


class CampaignEvaluationCreate(BaseModel):
    """Record how a campaign prediction matched actual performance."""

    campaign_id: UUID
    prediction: dict[str, Any] = Field(default_factory=dict)
    actual_result: dict[str, Any] = Field(default_factory=dict)
    human_rating: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = Field(default=None, max_length=500)


class CampaignEvaluationOut(BaseModel):
    """A campaign evaluation row as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    campaign_id: UUID | None
    prediction: dict[str, Any]
    actual_result: dict[str, Any]
    accuracy: dict[str, Any]
    prediction_result: str | None
    error_type: str | None
    confidence: Decimal | None
    confidence_bucket: str | None
    success_flag: bool | None
    metric_snapshot: dict[str, Any]
    human_rating: int | None
    notes: str | None
    trace_id: str | None
    created_at: datetime


class CreativeAnalysisCreate(BaseModel):
    """Record one AI/analytic pass over a creative asset."""

    creative_id: UUID
    input_snapshot: dict[str, Any] = Field(default_factory=dict)
    analysis_output: dict[str, Any] = Field(default_factory=dict)
    performance_result: dict[str, Any] = Field(default_factory=dict)
    model_version: str = Field(min_length=1, max_length=32)
    status: Literal["completed", "failed"] = "completed"


class CreativeAnalysisOut(BaseModel):
    """A creative analysis run as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    creative_id: UUID | None
    input_snapshot: dict[str, Any]
    analysis_output: dict[str, Any]
    performance_result: dict[str, Any]
    model_version: str
    status: str
    trace_id: str | None
    created_at: datetime
    updated_at: datetime


class MarketingKnowledgeCreate(BaseModel):
    """Create a marketing knowledge memory entry."""

    campaign_id: UUID | None = None
    creative_id: UUID | None = None
    category: str | None = Field(default=None, max_length=64)
    entry_type: Literal[
        "creative_pattern",
        "copy_pattern",
        "audience_pattern",
        "offer_pattern",
        "failure_pattern",
    ]
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=4000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    source: str = Field(default="manual", max_length=32)
    confidence: Decimal = Field(default=Decimal("0"), ge=0, le=1)


class MarketingKnowledgeOut(BaseModel):
    """A marketing knowledge entry as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    campaign_id: UUID | None
    creative_id: UUID | None
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


class MarketingCalibrationOut(BaseModel):
    """A marketing calibration run as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    status: str
    model_version: str
    input_snapshot: dict[str, Any]
    successful_patterns: dict[str, Any]
    failure_patterns: dict[str, Any]
    metrics: dict[str, Any]
    sample_size: int
    rationale: str | None
    approved_by: str | None
    approved_at: datetime | None
    trace_id: str | None
    created_at: datetime
    updated_at: datetime
