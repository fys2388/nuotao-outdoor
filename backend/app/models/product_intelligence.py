"""Product intelligence models: sources, cost history, scores, analysis, decisions.

All rows are workspace-scoped; scores/analysis/snapshots are append-only so
history is never overwritten (audit + calibration requirements).
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
    UniqueConstraint,
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
    purchase_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    domestic_shipping: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    first_leg_shipping: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    last_leg_shipping: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    international_shipping: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=0
    )
    packaging: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_estimate: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    handling: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total_landed_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1")
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


class SourcingCandidate(Base, TimestampMixin, WorkspaceMixin):
    """A supplier candidate for a product (one product, many candidates).

    Candidates are discovered before or during product intake (e.g. multiple
    ?1688 offers for the same product); each carries its own quote data.
    """

    __tablename__ = "product_sourcing_candidates"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    product_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    supplier_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
    )
    supplier_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False, default="1688")
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    purchase_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    moq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trend_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 2), nullable=True)
    profit_model: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1")
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_sourcing_candidates_product", "workspace_id", "product_id"),
    )


class ProductScoreEvidence(Base, CreatedAtMixin, WorkspaceMixin):
    """Per-dimension score evidence for a product score row.

    Each evidence entry carries score / source / evidence / confidence so
    every dimension is explainable and auditable (docs/product_strategy.md ?6.4).
    """

    __tablename__ = "product_score_evidences"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    product_score_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("product_scores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dimension: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence: Mapped[list[Any]] = mapped_column(AI_JSON, nullable=False, default=list)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False, default=0)
    version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1")
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ProductAiEvaluation(Base, CreatedAtMixin, WorkspaceMixin):
    """Evaluation of an AI prediction against actual results (M2.2).

    Links back to the originating analysis run and/or experiment; stores the
    prediction snapshot, the measured actuals, computed accuracy deltas and an
    optional human rating (1-5). Rows are append-only so the calibration
    history is preserved.
    """

    __tablename__ = "product_ai_evaluations"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    product_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    analysis_run_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("product_analysis_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    experiment_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("product_experiments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    prediction: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    actual_result: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    accuracy: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    # M2.3 learning-loop fields: outcome classification for calibration.
    prediction_result: Mapped[str | None] = mapped_column(String(16), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence_bucket: Mapped[str | None] = mapped_column(String(8), nullable=True)
    success_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    metric_snapshot: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    human_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ProductExperiment(Base, TimestampMixin, WorkspaceMixin):

    """Product testing loop: prediction -> experiment -> actual_result.

    ``prediction`` holds what the intelligence layer expected (score, decision,
    price, targets), ``experiment`` the executed test plan, and ``actual_result``
    the measured outcome. ``calibration`` stores prediction-vs-actual deltas
    for scoring model calibration (docs/product_strategy.md ?6.4).
    """

    __tablename__ = "product_experiments"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    product_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    experiment_type: Mapped[str] = mapped_column(String(32), nullable=False, default="market_test")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")
    prediction: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    experiment: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    actual_result: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    calibration: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1")
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_product_experiments_product", "workspace_id", "product_id"),
    )


class ConfidenceCalibration(Base, CreatedAtMixin, WorkspaceMixin):
    """Confidence calibration report bucket (M2.3).

    Aggregates AI confidence buckets against measured success rates so the
    team can see whether "HIGH" confidence actually correlates with success.
    One row per bucket per workspace (upserted by the report generator).
    """

    __tablename__ = "confidence_calibration"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    bucket: Mapped[str] = mapped_column(String(8), nullable=False)  # LOW | MEDIUM | HIGH
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=0)
    avg_confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=0)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "bucket", name="uq_confidence_calibration_workspace_bucket"
        ),
    )


class ProductScoreCalibrationRun(Base, TimestampMixin, WorkspaceMixin):
    """Score model calibration proposal (M2.3).

    Generated deterministically from historical experiments + AI predictions +
    actual outcomes. Proposes weight adjustments for the six scoring
    dimensions. **Never modifies rules automatically**: the run stays
    ``proposed`` until a human approves it, and approval only records the
    decision + suggested weights (version update is applied by humans).
    """

    __tablename__ = "score_calibration_runs"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    current_weights: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    suggested_weights: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    metrics: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rationale: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ProductKnowledgeEntry(Base, TimestampMixin, WorkspaceMixin):
    """Product knowledge memory (M2.3).

    Stores success/failure patterns and category insights learned from
    experiments and evaluations. Queryable by category and/or product so
    future agents can ground their reasoning in accumulated evidence.
    """

    __tablename__ = "product_knowledge_entries"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    product_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    category: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    entry_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="category_insight", index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(String(4000), nullable=False)
    tags: Mapped[list[Any]] = mapped_column(AI_JSON, nullable=False, default=list)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_knowledge_entries_workspace_cat", "workspace_id", "category"),
        Index("ix_knowledge_entries_workspace_product", "workspace_id", "product_id"),
    )

