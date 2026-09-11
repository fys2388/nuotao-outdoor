"""Marketing intelligence models (M3.1): campaigns, creatives, feedback, experiments.

All rows are workspace-scoped; every create/update/state change must also be
written to ``event_log`` by the service layer. No marketing action is ever
executed automatically - these tables only capture data and proposals.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AI_JSON, Base, CreatedAtMixin, TimestampMixin, WorkspaceMixin

# BigInteger on PostgreSQL; INTEGER on SQLite so tests keep working.
BIGINT = BigInteger().with_variant(Integer, "sqlite")

# Platform whitelist (Phase 1). Meta first for the US DTC primary market.
PLATFORMS: tuple[str, ...] = ("meta", "google", "tiktok", "pinterest", "other")


class Campaign(Base, TimestampMixin, WorkspaceMixin):
    """One advertising campaign on an external platform (M3.1).

    ``campaign_id`` is the external platform identifier; the pair
    ``(workspace_id, platform, campaign_id)`` is unique. Derived metrics
    (ctr / cpc / roas) are stored when provided or computed deterministically
    by the service layer.
    """

    __tablename__ = "campaigns"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    campaign_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    product_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    budget: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    spend: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    impressions: Mapped[int] = mapped_column(BIGINT, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(BIGINT, nullable=False, default=0)
    ctr: Mapped[Decimal | None] = mapped_column(Numeric(8, 6), nullable=True)
    cpc: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    conversion: Mapped[int] = mapped_column(BIGINT, nullable=False, default=0)
    revenue: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    roas: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "platform",
            "campaign_id",
            name="uq_campaigns_workspace_platform_campaign",
        ),
        Index("ix_campaigns_workspace_platform", "workspace_id", "platform"),
        Index("ix_campaigns_workspace_product", "workspace_id", "product_id"),
    )


class CreativeAsset(Base, TimestampMixin, WorkspaceMixin):
    """A creative asset (ad image/video/text) for a product (M3.1).

    ``reference`` is the URL or file reference; ``hook``/``angle``/``copy``
    capture the marketing positioning so the future Growth Agent can learn
    from what worked.
    """

    __tablename__ = "creative_assets"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    product_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    platform: Mapped[str] = mapped_column(String(16), nullable=False, default="meta")
    asset_type: Mapped[str] = mapped_column(String(24), nullable=False, default="image")
    reference: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    hook: Mapped[str | None] = mapped_column(String(500), nullable=True)
    angle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    copy: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    performance_snapshot: Mapped[dict[str, Any]] = mapped_column(
        AI_JSON, nullable=False, default=dict
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_creative_assets_workspace_product", "workspace_id", "product_id"),
        Index("ix_creative_assets_workspace_platform", "workspace_id", "platform"),
    )


class CustomerFeedback(Base, CreatedAtMixin, WorkspaceMixin):
    """Customer feedback captured from reviews/support/social (M3.1).

    Append-only by nature (reviews cannot be rewritten); ``updated_at`` is
    intentionally absent. Sentiment/issue classification is stored so the
    future Customer Agent can route and learn.
    """

    __tablename__ = "customer_feedback"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    product_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="other")
    content: Mapped[str] = mapped_column(String(4000), nullable=False)
    sentiment: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    issue_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", AI_JSON, nullable=False, default=dict
    )
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_feedback_workspace_product", "workspace_id", "product_id"),
        Index("ix_feedback_workspace_sentiment", "workspace_id", "sentiment"),
    )


class MarketingExperiment(Base, TimestampMixin, WorkspaceMixin):
    """A marketing A/B test proposal with lifecycle (M3.1).

    State machine: ``proposed -> active -> completed``. ``variant_a`` /
    ``variant_b`` hold the tested creatives/offers; ``result`` the measured
    outcome; ``calibration`` the A/B deltas (deterministic, computed on
    completion).
    """

    __tablename__ = "marketing_experiments"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    product_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hypothesis: Mapped[str] = mapped_column(String(2000), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")
    variant_a: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    variant_b: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    calibration: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_marketing_experiments_workspace_product", "workspace_id", "product_id"),
        Index("ix_marketing_experiments_workspace_status", "workspace_id", "status"),
    )
