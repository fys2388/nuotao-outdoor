"""Product intelligence models: sources, cost history, scores, analysis, decisions.

All rows are workspace-scoped; scores/analysis/snapshots are append-only so
history is never overwritten (audit + calibration requirements).
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AI_JSON, Base, CreatedAtMixin, TimestampMixin, WorkspaceMixin

# Source types supported in Phase 1 (1688 / manual / other).
SOURCE_TYPES: tuple[str, ...] = ("1688", "MANUAL", "OTHER")

# Decision states (product lifecycle, see docs/product_strategy.md §8).
DECISION_TYPES: tuple[str, ...] = ("test", "hold", "reject")
APPROVAL_STATES: tuple[str, ...] = ("pending", "approved", "rejected")


class ProductSource(Base, TimestampMixin, WorkspaceMixin):
    """A captured product source (1688 page, manual record, or other)."""

    __tablename__ = "product_sources"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    product_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    supplier_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
    )
    supplier_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    raw_data: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_product_sources_captured", "workspace_id", "captured_at"),
    )


class ProductCostSnapshot(Base, CreatedAtMixin, WorkspaceMixin):
    """Append-only landing cost history per product.

    A new row is inserted on every cost change; rows are never updated or
    deleted, so historical costs remain available for calibration and audit.
    """

    __tablename__ = "product_cost_snapshots"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    product_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    purchase_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    domestic_shipping: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    first_leg_shipping: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    last_leg_shipping: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    payment_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    marketing_amortization: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=0
    )
    after_sales_loss: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=0
    )
    total_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ProductScore(Base, CreatedAtMixin, WorkspaceMixin):
    """Structured six-dimension product score (0-10 each, total 0-100).

    Follows docs/product_strategy.md §6: weights profit 30%, logistics 20%,
    demand 15%, competition 10%, differentiation 15%, compliance 10%.
    """

    __tablename__ = "product_scores"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    product_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    profit: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    logistics: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    demand: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    competition: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    differentiation: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    compliance: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False)
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ProductAnalysisRun(Base, CreatedAtMixin, WorkspaceMixin):
    """Audit record of one product analysis run (LLM or deterministic).

    ``provider``/``model`` describe the engine (e.g. ``deterministic`` /
    ``heuristic-v1`` for the M2.1 no-LLM pipeline). Token usage, estimated
    cost and latency enable per-run cost accounting.
    """

    __tablename__ = "product_analysis_runs"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    product_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    output: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    token_usage: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    estimated_cost: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="completed")
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ProductDecision(Base, TimestampMixin, WorkspaceMixin):
    """A product decision proposal with human approval workflow.

    State machine: pending -> approved | rejected (approve sets approved_by /
    approved_at and may advance the product lifecycle status; see
    docs/product_strategy.md §8).
    """

    __tablename__ = "product_decisions"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    product_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    reasons: Mapped[list[Any]] = mapped_column(AI_JSON, nullable=False, default=list)
    risks: Mapped[list[Any]] = mapped_column(AI_JSON, nullable=False, default=list)
    recommended_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    max_cac: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    test_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    test_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approval_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
