"""Supply chain learning loop schemas (M4.2)."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

SUPPLIER_PATTERN_TYPES = (
    "quality_pattern",
    "delivery_pattern",
    "price_pattern",
    "risk_pattern",
    "capacity_pattern",
)

LOGISTICS_PATTERN_TYPES = (
    "delay_pattern",
    "carrier_pattern",
    "route_pattern",
    "country_pattern",
)


class SupplierEvaluationCreate(BaseModel):
    """Record how a predicted supplier outcome matched the actual outcome."""

    supplier_id: UUID
    prediction: dict[str, Any] = Field(default_factory=dict)
    actual_result: dict[str, Any] = Field(default_factory=dict)
    human_rating: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = Field(default=None, max_length=500)


class SupplierEvaluationOut(BaseModel):
    """A supplier evaluation row as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    supplier_id: UUID | None
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


class LogisticsEvaluationCreate(BaseModel):
    """Record how a predicted delivery outcome matched the actual outcome."""

    shipment_id: UUID
    carrier: str | None = Field(default=None, max_length=64)
    route: str | None = Field(default=None, max_length=255)
    prediction: dict[str, Any] = Field(default_factory=dict)
    actual_result: dict[str, Any] = Field(default_factory=dict)
    delay_reason: str | None = Field(default=None, max_length=500)
    human_rating: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = Field(default=None, max_length=500)


class LogisticsEvaluationOut(BaseModel):
    """A logistics evaluation row as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    shipment_id: UUID | None
    carrier: str | None
    route: str | None
    prediction: dict[str, Any]
    actual_result: dict[str, Any]
    delay_reason: str | None
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


class SupplierPatternRunRequest(BaseModel):
    """Trigger a deterministic supplier pattern mining run."""

    pattern_type: Literal[
        "quality_pattern",
        "delivery_pattern",
        "price_pattern",
        "risk_pattern",
        "capacity_pattern",
    ]
    supplier_id: UUID | None = None


class SupplierPatternRunOut(BaseModel):
    """A supplier pattern mining run as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    supplier_id: UUID | None
    pattern_type: str
    input_snapshot: dict[str, Any]
    output_pattern: dict[str, Any]
    confidence: Decimal
    sample_size: int
    status: str
    trace_id: str | None
    created_at: datetime
    updated_at: datetime


class LogisticsPatternRunRequest(BaseModel):
    """Trigger a deterministic logistics pattern mining run."""

    pattern_type: Literal[
        "delay_pattern",
        "carrier_pattern",
        "route_pattern",
        "country_pattern",
    ]
    shipment_id: UUID | None = None
    carrier: str | None = Field(default=None, max_length=64)


class LogisticsPatternRunOut(BaseModel):
    """A logistics pattern mining run as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    shipment_id: UUID | None
    carrier: str | None
    pattern_type: str
    input_snapshot: dict[str, Any]
    output_pattern: dict[str, Any]
    confidence: Decimal
    sample_size: int
    status: str
    trace_id: str | None
    created_at: datetime
    updated_at: datetime


class SupplyChainCalibrationOut(BaseModel):
    """A supply chain calibration run as returned by the API."""

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
