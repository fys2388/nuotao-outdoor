"""Marketing learning loop models (M3.2): evaluation, analysis, knowledge, calibration.

Marketing intelligence becomes a learning system: campaign predictions are
evaluated against measured outcomes, creative analysis runs are audited,
knowledge entries accumulate patterns, and calibration runs deterministically
surface successful/failure patterns. **No marketing rule is ever modified
automatically** - calibration runs stay ``proposed`` until a human approves.
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

# Marketing knowledge entry types (Phase 1).
MARKETING_ENTRY_TYPES: tuple[str, ...] = (
    "creative_pattern",
    "copy_pattern",
    "audience_pattern",
    "offer_pattern",
    "failure_pattern",
)


class CampaignAiEvaluation(Base, CreatedAtMixin, WorkspaceMixin):
    """Evaluation of a campaign prediction against actual performance (M3.2).

    Append-only: each row compares an AI prediction snapshot with the measured
    outcome and classifies the result (success/failure + error type) so the
    marketing learning loop can calibrate future predictions.
    """

    __tablename__ = "campaign_ai_evaluations"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    campaign_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("campaigns.id", ondelete="SET NULL"),
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
            "ix_campaign_evaluations_workspace_campaign",
            "workspace_id",
            "campaign_id",
        ),
        Index(
            "ix_campaign_evaluations_workspace_bucket",
            "workspace_id",
            "confidence_bucket",
        ),
    )


class CreativeAnalysisRun(Base, TimestampMixin, WorkspaceMixin):
    """Audit row for one AI/analytic pass over a creative asset (M3.2).

    Stores the input snapshot (creative + context), the analysis output and the
    later measured performance result so creative intelligence can be learned
    and calibrated over time.
    """

    __tablename__ = "creative_analysis_runs"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    creative_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("creative_assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    analysis_output: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    performance_result: Mapped[dict[str, Any]] = mapped_column(
        AI_JSON, nullable=False, default=dict
    )
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="completed")
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index(
            "ix_creative_analysis_workspace_creative",
            "workspace_id",
            "creative_id",
        ),
    )


class MarketingKnowledgeEntry(Base, TimestampMixin, WorkspaceMixin):
    """Marketing knowledge memory (M3.2): patterns learned from creatives/campaigns.

    Entry types: ``creative_pattern`` / ``copy_pattern`` / ``audience_pattern`` /
    ``offer_pattern`` / ``failure_pattern``. Queryable by category, campaign or
    creative so future Growth Agent reasoning can be grounded in evidence.
    """

    __tablename__ = "marketing_knowledge_entries"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    campaign_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("campaigns.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    creative_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("creative_assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    category: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(String(4000), nullable=False)
    tags: Mapped[list[Any]] = mapped_column(AI_JSON, nullable=False, default=list)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=0)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index(
            "ix_marketing_knowledge_workspace_cat",
            "workspace_id",
            "category",
        ),
        Index(
            "ix_marketing_knowledge_workspace_campaign",
            "workspace_id",
            "campaign_id",
        ),
        Index(
            "ix_marketing_knowledge_workspace_creative",
            "workspace_id",
            "creative_id",
        ),
    )


class MarketingCalibrationRun(Base, TimestampMixin, WorkspaceMixin):
    """Marketing calibration proposal (M3.2): discovered patterns, human-approved.

    Deterministically aggregates successful/failure patterns from evaluations,
    completed experiments and knowledge entries. **Never modifies marketing
    rules automatically**: the run stays ``proposed`` until a human approves or
    rejects it, and approval only records the decision.
    """

    __tablename__ = "marketing_calibration_runs"

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
            "ix_marketing_calibration_workspace_status",
            "workspace_id",
            "status",
        ),
    )
