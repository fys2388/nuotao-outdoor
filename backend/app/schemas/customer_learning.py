"""Customer learning loop schemas (M3.4)."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

CUSTOMER_PATTERN_TYPES = (
    "purchase_pattern",
    "segment_pattern",
    "bundle_pattern",
    "churn_pattern",
    "pain_pattern",
)


class CustomerEvaluationCreate(BaseModel):
    """Record how a predicted customer behavior matched actual behavior."""

    customer_id: UUID
    prediction: dict[str, Any] = Field(default_factory=dict)
    actual_behavior: dict[str, Any] = Field(default_factory=dict)
    human_rating: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = Field(default=None, max_length=500)


class CustomerEvaluationOut(BaseModel):
    """A customer evaluation row as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    customer_id: UUID | None
    prediction: dict[str, Any]
    actual_behavior: dict[str, Any]
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


class PatternRunRequest(BaseModel):
    """Trigger a deterministic pattern mining run for one pattern type."""

    pattern_type: Literal[
        "purchase_pattern",
        "segment_pattern",
        "bundle_pattern",
        "churn_pattern",
        "pain_pattern",
    ]
    customer_id: UUID | None = None


class PatternRunOut(BaseModel):
    """A customer pattern mining run as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    customer_id: UUID | None
    pattern_type: str
    input_snapshot: dict[str, Any]
    output_pattern: dict[str, Any]
    confidence: Decimal
    sample_size: int
    status: str
    trace_id: str | None
    created_at: datetime
    updated_at: datetime


class CustomerCalibrationOut(BaseModel):
    """A customer calibration run as returned by the API."""

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
