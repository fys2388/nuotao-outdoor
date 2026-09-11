"""Connector run audit and business recommendation models (M4.3).

``ConnectorRun`` records every external data synchronization (WooCommerce,
logistics, marketing, supplier) with status/counts for audit. ``BusinessRecommendation``
is the decision-intelligence layer: proposed recommendations require human
approval - no automatic business actions, no automatic rule changes.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import DateTime, Index, Integer, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, WorkspaceMixin

# Connector run lifecycle states (M4.3).
CONNECTOR_RUN_STATUSES: tuple[str, ...] = ("running", "success", "failed")

# Recommendation lifecycle states (M4.3).
RECOMMENDATION_STATUSES: tuple[str, ...] = ("proposed", "approved", "rejected")

# Recommendation domains (M4.3).
RECOMMENDATION_DOMAINS: tuple[str, ...] = (
    "product",
    "marketing",
    "customer",
    "supply_chain",
    "operations",
)


class ConnectorRun(Base, TimestampMixin, WorkspaceMixin):
    """Audit record of one connector synchronization run (M4.3)."""

    __tablename__ = "connector_runs"

    id: Mapped[Any] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    connector_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    records_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_connector_runs_workspace_name", "workspace_id", "connector_name"),
        Index("ix_connector_runs_workspace_status", "workspace_id", "status"),
    )


class BusinessRecommendation(Base, TimestampMixin, WorkspaceMixin):
    """A proposed business recommendation awaiting human approval (M4.3).

    Decision intelligence output: domain-scoped advice (e.g. reorder a SKU,
    pause a campaign, switch carrier) with a reason and confidence. Stays
    ``proposed`` until a human approves or rejects it - nothing is applied
    automatically.
    """

    __tablename__ = "business_recommendations"

    id: Mapped[Any] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    recommendation: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_recommendations_workspace_status", "workspace_id", "status"),
        Index("ix_recommendations_workspace_domain", "workspace_id", "domain"),
    )
