"""Business alert model (M4): persistent alerts with dedup and recovery.

Alerts are stored in PostgreSQL, not in-memory, so they survive restarts.
Unique constraint on (workspace_id, alert_type, resource_type, resource_id, active_status)
prevents duplicate active alerts. Recovery events are audited.

Alert types:
- margin_decline
- refund_spike
- revenue_decline
- aov_decline
- stockout_risk
"""

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AI_JSON, Base, TimestampMixin, WorkspaceMixin

# Alert types.
ALERT_TYPES: tuple[str, ...] = (
    "margin_decline",
    "refund_spike",
    "revenue_decline",
    "aov_decline",
    "stockout_risk",
)

# Alert severities.
ALERT_SEVERITIES: tuple[str, ...] = ("info", "warning", "critical")

# Alert statuses.
ALERT_STATUSES: tuple[str, ...] = (
    "active",
    "acknowledged",
    "resolved",
    "suppressed",
)


class BusinessAlert(Base, TimestampMixin, WorkspaceMixin):
    """Persistent business alert with dedup, recovery, and audit (M4).

    Unique constraint prevents duplicate active alerts for the same
    (workspace, alert_type, resource_type, resource_id).
    Recovery sets resolved_at and status='resolved'; re-triggering creates
    a new alert (not reactivating resolved ones).
    """

    __tablename__ = "business_alerts"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False, default="global")
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="warning")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", index=True)

    # Metric values that triggered the alert.
    metric_value: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    threshold_value: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    metric_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    comparison: Mapped[str | None] = mapped_column(String(16), nullable=True)  # "lt", "gt", "lte", "gte"

    # Human-readable message.
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps.
    first_detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    last_detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Detection count (how many times this alert condition was detected).
    detection_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Context / metadata.
    metadata_json: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)

    # Trace.
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        # Prevent duplicate ACTIVE alerts for same (workspace, type, resource).
        # Resolved alerts don't conflict (can re-trigger later).
        UniqueConstraint(
            "workspace_id", "alert_type", "resource_type", "resource_id", "status",
            name="uq_business_alerts_active_dedup",
        ),
        Index("ix_business_alerts_workspace_type_status", "workspace_id", "alert_type", "status"),
        Index("ix_business_alerts_workspace_severity", "workspace_id", "severity"),
        Index("ix_business_alerts_workspace_resource", "workspace_id", "resource_type", "resource_id"),
    )
