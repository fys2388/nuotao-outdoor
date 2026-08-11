"""Customer learning loop models (M3.4): evaluation, pattern mining, calibration.

Customer intelligence becomes a learning layer: predicted behaviors are
evaluated against real behavior, deterministic pattern runs surface
purchase/segment/bundle/churn/pain patterns, and calibration proposals require
human approval. **No business rule is ever modified automatically.**
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AI_JSON, Base, CreatedAtMixin, TimestampMixin, WorkspaceMixin

# Pattern run types (M3.4).
CUSTOMER_PATTERN_TYPES: tuple[str, ...] = (
    "purchase_pattern",
    "segment_pattern",
    "bundle_pattern",
    "churn_pattern",
    "pain_pattern",
)


class CustomerAiEvaluation(Base, CreatedAtMixin, WorkspaceMixin):
    """Evaluation of a predicted customer behavior against actual behavior (M3.4).

    Append-only: each row compares a prediction snapshot (e.g. will reorder /
    will churn / will buy bundle) with the measured actual behavior and
    classifies success/failure + error type for the learning loop.
    """

    __tablename__ = "customer_ai_evaluations"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    customer_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("customer_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    prediction: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    actual_behavior: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    accuracy: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    prediction_result: Mapped[str | None] = mapped_column(String(16), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    confidence_bucket: Mapped[str | None] = mapped_column(String(8), nullable=True)
    success_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    metric_snapshot: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    human_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index(
            "ix_customer_evaluations_workspace_customer",
            "workspace_id",
            "customer_id",
        ),
        Index(
            "ix_customer_evaluations_workspace_bucket",
            "workspace_id",
            "confidence_bucket",
        ),
    )


class CustomerPatternRun(Base, TimestampMixin, WorkspaceMixin):
    """Deterministic customer pattern mining run (M3.4).

    Aggregates evaluations, profiles, interactions and refunds into one
    pattern type (purchase/segment/bundle/churn/pain) with a confidence score.
    Outputs are proposals for learning - nothing is applied automatically.
    """

    __tablename__ = "customer_pattern_runs"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    customer_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("customer_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    pattern_type: Mapped[str] = mapped_column(String(32), nullable=False)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    output_pattern: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=0)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="completed")
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index(
            "ix_customer_pattern_runs_workspace_type",
            "workspace_id",
            "pattern_type",
        ),
    )


class CustomerCalibrationRun(Base, TimestampMixin, WorkspaceMixin):
    """Customer calibration proposal (M3.4).

    Deterministically aggregates successful/failure patterns from evaluations
    and pattern runs. **Never modifies business rules automatically**: the run
    stays ``proposed`` until a human approves or rejects it.
    """

    __tablename__ = "customer_calibration_runs"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    successful_patterns: Mapped[dict[str, Any]] = mapped_column(
        AI_JSON, nullable=False, default=dict
    )
    failure_patterns: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    metrics: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rationale: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index(
            "ix_customer_calibration_workspace_status",
            "workspace_id",
            "status",
        ),
    )
