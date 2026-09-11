"""Supply chain learning loop models (M4.2): evaluation, pattern mining, calibration.

Supply chain intelligence becomes a learning layer: predicted supplier
performance and logistics delivery outcomes are evaluated against actuals,
deterministic pattern runs surface quality/delivery/price/risk/capacity and
delay/carrier/route/country patterns, and calibration proposals require human
approval. **No Supply Chain Agent, no automatic purchasing and no business
rule is ever modified automatically.**
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

# Supplier pattern run types (M4.2).
SUPPLIER_PATTERN_TYPES: tuple[str, ...] = (
    "quality_pattern",
    "delivery_pattern",
    "price_pattern",
    "risk_pattern",
    "capacity_pattern",
)

# Logistics pattern run types (M4.2).
LOGISTICS_PATTERN_TYPES: tuple[str, ...] = (
    "delay_pattern",
    "carrier_pattern",
    "route_pattern",
    "country_pattern",
)


class SupplierAiEvaluation(Base, CreatedAtMixin, WorkspaceMixin):
    """Evaluation of predicted supplier performance vs actuals (M4.2).

    Append-only: compares a prediction snapshot (on_time / quality / price /
    risk expectations) with the measured outcome and classifies
    success/failure + error type for the learning loop.
    """

    __tablename__ = "supplier_ai_evaluations"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    supplier_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    prediction: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    actual_result: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
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
            "ix_supplier_evaluations_workspace_supplier",
            "workspace_id",
            "supplier_id",
        ),
        Index(
            "ix_supplier_evaluations_workspace_bucket",
            "workspace_id",
            "confidence_bucket",
        ),
    )


class LogisticsAiEvaluation(Base, CreatedAtMixin, WorkspaceMixin):
    """Evaluation of predicted delivery outcome vs actuals (M4.2).

    Append-only: compares a prediction snapshot (delivery_time_days / delay /
    decision) with the measured outcome per carrier/route and classifies
    success/failure + error type for the learning loop.
    """

    __tablename__ = "logistics_ai_evaluations"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    shipment_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("shipment_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    carrier: Mapped[str | None] = mapped_column(String(64), nullable=True)
    route: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prediction: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    actual_result: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    delay_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
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
            "ix_logistics_evaluations_workspace_shipment",
            "workspace_id",
            "shipment_id",
        ),
        Index(
            "ix_logistics_evaluations_workspace_carrier",
            "workspace_id",
            "carrier",
        ),
    )


class SupplierPatternRun(Base, TimestampMixin, WorkspaceMixin):
    """Deterministic supplier pattern mining run (M4.2).

    Aggregates supplier profiles and evaluations into one pattern type
    (quality/delivery/price/risk/capacity) with a confidence score. Outputs
    are proposals for learning - nothing is applied automatically.
    """

    __tablename__ = "supplier_pattern_runs"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    supplier_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("suppliers.id", ondelete="SET NULL"),
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
            "ix_supplier_pattern_runs_workspace_type",
            "workspace_id",
            "pattern_type",
        ),
    )


class LogisticsPatternRun(Base, TimestampMixin, WorkspaceMixin):
    """Deterministic logistics pattern mining run (M4.2).

    Aggregates shipment records and logistics evaluations into one pattern
    type (delay/carrier/route/country) with a confidence score. Outputs are
    proposals for learning - nothing is applied automatically.
    """

    __tablename__ = "logistics_pattern_runs"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    shipment_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("shipment_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    carrier: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pattern_type: Mapped[str] = mapped_column(String(32), nullable=False)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    output_pattern: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=0)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="completed")
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index(
            "ix_logistics_pattern_runs_workspace_type",
            "workspace_id",
            "pattern_type",
        ),
    )


class SupplyChainCalibrationRun(Base, TimestampMixin, WorkspaceMixin):
    """Supply chain calibration proposal (M4.2).

    Deterministically aggregates successful/failure patterns from supplier and
    logistics evaluations plus pattern runs. **Never modifies business rules
    automatically**: the run stays ``proposed`` until a human approves or
    rejects it.
    """

    __tablename__ = "supply_chain_calibration_runs"

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
            "ix_supply_chain_calibration_workspace_status",
            "workspace_id",
            "status",
        ),
    )
