"""Activity plan models (M6): AI-generated e-commerce campaign proposals.

All rows are workspace-scoped. An activity plan is a *proposal* — it is
never executed automatically. ``plan_json`` holds the full structured plan;
``approval_status`` gates human review before any downstream action (EDM
sends, image batches, discount configuration).
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

# Activity type whitelist.
ACTIVITY_TYPES: tuple[str, ...] = (
    "big_promotion",    # Black Friday, Cyber Monday, Christmas, etc.
    "new_launch",       # new product launch
    "clearance",        # inventory clearance
    "seasonal",         # seasonal / holiday marketing
    "member_exclusive", # member / VIP exclusive
    "flash_sale",       # flash sale / limited time
    "other",
)

# Plan lifecycle: draft -> pending_review -> approved -> rejected -> executing -> completed
PLAN_STATUSES: tuple[str, ...] = (
    "draft", "pending_review", "approved", "rejected", "executing", "completed", "archived",
)


class ActivityPlan(Base, TimestampMixin, WorkspaceMixin):
    """One AI-generated e-commerce activity plan (M6).

    ``plan_json`` stores the full structured plan (objectives, budget,
    discount strategy, product selection, channel plan, creative assets,
    timeline, risk mitigation, KPI tracking). The service layer validates
    critical fields (dates, discount rates) before persisting.
    """

    __tablename__ = "activity_plans"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    activity_type: Mapped[str] = mapped_column(String(32), nullable=False, default="other")
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    budget_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    budget_currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    target_revenue: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    target_orders: Mapped[int | None] = mapped_column(nullable=True)
    target_roas: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    plan_json: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    approval_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    parent_plan_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("activity_plans.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    version: Mapped[int] = mapped_column(default=1)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_activity_plans_workspace_status", "workspace_id", "status"),
        Index("ix_activity_plans_workspace_type", "workspace_id", "activity_type"),
        Index("ix_activity_plans_workspace_approval", "workspace_id", "approval_status"),
    )
