"""Influencer / KOL models (M6): creator profiles and collaboration records.

Phase 1: influencer data is manually entered / CSV imported (no scraping —
compliance-gated per AGENTS.md §4.4). All rows are workspace-scoped.
``collaborations`` links an influencer to an activity plan and records the
outcome so the Marketing Manager can learn from what worked.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AI_JSON, Base, TimestampMixin, WorkspaceMixin

# Platform whitelist (Phase 1).
INFLUENCER_PLATFORMS: tuple[str, ...] = (
    "instagram", "tiktok", "youtube", "facebook", "pinterest", "twitter", "blog", "other",
)

# Collaboration types.
COLLAB_TYPES: tuple[str, ...] = (
    "product_seeding",  # free product for review
    "affiliate",         # commission-based
    "sponsored_post",    # paid sponsored content
    "brand_ambassador",  # long-term partnership
    "other",
)

# Collaboration lifecycle.
COLLAB_STATUSES: tuple[str, ...] = (
    "prospecting", "contacted", "negotiating", "confirmed",
    "in_progress", "completed", "cancelled",
)


class Influencer(Base, TimestampMixin, WorkspaceMixin):
    """An influencer / KOL creator profile (M6, Phase 1 manual entry)."""

    __tablename__ = "influencers"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    handle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, default="instagram")
    profile_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    followers: Mapped[int] = mapped_column(default=0)
    engagement_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    avg_views: Mapped[int | None] = mapped_column(nullable=True)
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_info: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 1), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_influencers_workspace_platform", "workspace_id", "platform"),
        Index("ix_influencers_workspace_category", "workspace_id", "category"),
        Index("ix_influencers_workspace_region", "workspace_id", "region"),
    )


class InfluencerCollaboration(Base, TimestampMixin, WorkspaceMixin):
    """A collaboration record between an influencer and an activity plan (M6)."""

    __tablename__ = "influencer_collaborations"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    influencer_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("influencers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    activity_plan_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("activity_plans.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    collab_type: Mapped[str] = mapped_column(String(32), nullable=False, default="product_seeding")
    compensation_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    compensation_currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    commission_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    content_requirements: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    content_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="prospecting")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_collab_workspace_influencer", "workspace_id", "influencer_id"),
        Index("ix_collab_workspace_activity", "workspace_id", "activity_plan_id"),
        Index("ix_collab_workspace_status", "workspace_id", "status"),
    )
