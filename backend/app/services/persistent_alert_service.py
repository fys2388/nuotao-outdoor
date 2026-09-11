"""Persistent business alert service (M4): alerts stored in PostgreSQL.

Alerts survive restarts, support dedup (unique active alert per type+resource),
recovery (status -> resolved), and audit (all state changes logged).

Alert types:
- margin_decline
- refund_spike
- revenue_decline
- aov_decline
- stockout_risk

Rules:
- Duplicate active alert for same (type, resource) updates last_detected_at and detection_count
- Resolved alerts don't conflict; re-triggering creates a new alert
- Empty data is safe: no false alerts, no division by zero
- All alert creation/resolution writes to event_log
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business_alert import ALERT_SEVERITIES, ALERT_STATUSES, ALERT_TYPES, BusinessAlert
from app.services import event_service

logger = logging.getLogger(__name__)

ZERO = Decimal("0")


class BusinessAlertError(Exception):
    """Base alert service error."""


class AlertNotFound(BusinessAlertError):
    """Alert not found."""


class AlertStateError(BusinessAlertError):
    """Invalid alert state transition."""


# --------------------------------------------------------------------------- #
# Alert creation (with dedup)
# --------------------------------------------------------------------------- #


async def create_or_update_alert(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    alert_type: str,
    title: str,
    message: str | None = None,
    severity: str = "warning",
    resource_type: str = "global",
    resource_id: str | None = None,
    metric_value: float | None = None,
    threshold_value: float | None = None,
    metric_name: str | None = None,
    comparison: str | None = None,
    metadata: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> BusinessAlert:
    """Create alert or update existing active alert (dedup).

    If an active alert with same (workspace, alert_type, resource_type, resource_id)
    exists, update its last_detected_at and detection_count instead of creating
    a duplicate. This prevents alert spam.
    """
    if alert_type not in ALERT_TYPES:
        raise BusinessAlertError(f"Unknown alert_type: {alert_type}. Valid: {ALERT_TYPES}")
    if severity not in ALERT_SEVERITIES:
        raise BusinessAlertError(f"Unknown severity: {severity}. Valid: {ALERT_SEVERITIES}")

    # Look for existing active alert
    result = await session.execute(
        select(BusinessAlert).where(
            BusinessAlert.workspace_id == workspace_id,
            BusinessAlert.alert_type == alert_type,
            BusinessAlert.resource_type == resource_type,
            BusinessAlert.resource_id == resource_id,
            BusinessAlert.status == "active",
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        # Update existing alert (dedup)
        existing.last_detected_at = datetime.now(UTC)
        existing.detection_count += 1
        if metric_value is not None:
            existing.metric_value = metric_value
        if threshold_value is not None:
            existing.threshold_value = threshold_value
        if message is not None:
            existing.message = message
        if metadata:
            existing.metadata_json = {**existing.metadata_json, **metadata}
        await session.flush()

        await event_service.create_event(
            session, workspace_id=workspace_id, event_type="alert.retriggered",
            entity_type="business_alert", entity_id=str(existing.id),
            payload={"detection_count": existing.detection_count, "alert_type": alert_type},
            trace_id=trace_id,
        )
        logger.info("alert retriggered (dedup): id=%s type=%s count=%d", existing.id, alert_type, existing.detection_count)
        return existing

    # Create new alert
    alert = BusinessAlert(
        workspace_id=workspace_id,
        alert_type=alert_type,
        resource_type=resource_type,
        resource_id=resource_id,
        severity=severity,
        status="active",
        metric_value=metric_value,
        threshold_value=threshold_value,
        metric_name=metric_name,
        comparison=comparison,
        title=title,
        message=message,
        first_detected_at=datetime.now(UTC),
        last_detected_at=datetime.now(UTC),
        detection_count=1,
        metadata_json=metadata or {},
        trace_id=trace_id,
    )
    session.add(alert)
    await session.flush()

    await event_service.create_event(
        session, workspace_id=workspace_id, event_type="alert.created",
        entity_type="business_alert", entity_id=str(alert.id),
        payload={"alert_type": alert_type, "severity": severity, "title": title},
        trace_id=trace_id,
    )
    logger.info("alert created: id=%s type=%s severity=%s", alert.id, alert_type, severity)
    return alert


# --------------------------------------------------------------------------- #
# Alert resolution and acknowledgement
# --------------------------------------------------------------------------- #


async def resolve_alert(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    alert_id: UUID,
    resolved_by: str = "system",
    resolution_note: str | None = None,
    trace_id: str | None = None,
) -> BusinessAlert:
    """Resolve an active alert. status -> resolved, resolved_at set."""
    alert = await _load_alert(session, workspace_id=workspace_id, alert_id=alert_id)

    if alert.status == "resolved":
        logger.info("alert already resolved: id=%s", alert_id)
        return alert

    if alert.status not in ("active", "acknowledged"):
        raise AlertStateError(f"Cannot resolve alert in status '{alert.status}'")

    alert.status = "resolved"
    alert.resolved_at = datetime.now(UTC)
    if resolution_note:
        alert.metadata_json = {**alert.metadata_json, "resolution_note": resolution_note}
    await session.flush()

    await event_service.create_event(
        session, workspace_id=workspace_id, event_type="alert.resolved",
        entity_type="business_alert", entity_id=str(alert.id),
        payload={"resolved_by": resolved_by, "resolution_note": resolution_note},
        trace_id=trace_id,
    )
    logger.info("alert resolved: id=%s by=%s", alert.id, resolved_by)
    return alert


async def acknowledge_alert(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    alert_id: UUID,
    acknowledged_by: str,
    trace_id: str | None = None,
) -> BusinessAlert:
    """Acknowledge an active alert. status -> acknowledged."""
    alert = await _load_alert(session, workspace_id=workspace_id, alert_id=alert_id)

    if alert.status != "active":
        raise AlertStateError(f"Cannot acknowledge alert in status '{alert.status}'")

    alert.status = "acknowledged"
    alert.acknowledged_at = datetime.now(UTC)
    alert.acknowledged_by = acknowledged_by
    await session.flush()

    await event_service.create_event(
        session, workspace_id=workspace_id, event_type="alert.acknowledged",
        entity_type="business_alert", entity_id=str(alert.id),
        payload={"acknowledged_by": acknowledged_by},
        trace_id=trace_id,
    )
    return alert


# --------------------------------------------------------------------------- #
# Alert evaluation (5 types)
# --------------------------------------------------------------------------- #


async def evaluate_margin_decline(
    session: AsyncSession, *, workspace_id: UUID, current_margin: Decimal, threshold: Decimal = Decimal("0.20")
) -> BusinessAlert | None:
    """Evaluate margin_decline alert. Returns alert if margin below threshold, None otherwise."""
    if current_margin is None:
        return None  # No data, no alert
    if current_margin < threshold:
        return await create_or_update_alert(
            session, workspace_id=workspace_id,
            alert_type="margin_decline",
            title=f"Margin decline: {float(current_margin):.1%} below threshold {float(threshold):.1%}",
            message=f"Current margin rate is {float(current_margin):.1%}, below threshold {float(threshold):.1%}",
            severity="critical" if current_margin < threshold * Decimal("0.5") else "warning",
            metric_value=float(current_margin),
            threshold_value=float(threshold),
            metric_name="margin_rate",
            comparison="lt",
        )
    return None


async def evaluate_refund_spike(
    session: AsyncSession, *, workspace_id: UUID, refund_rate: Decimal, threshold: Decimal = Decimal("0.10")
) -> BusinessAlert | None:
    """Evaluate refund_spike alert."""
    if refund_rate is None:
        return None
    if refund_rate > threshold:
        return await create_or_update_alert(
            session, workspace_id=workspace_id,
            alert_type="refund_spike",
            title=f"Refund spike: {float(refund_rate):.1%} above threshold {float(threshold):.1%}",
            message=f"Refund rate is {float(refund_rate):.1%}, above threshold {float(threshold):.1%}",
            severity="critical" if refund_rate > threshold * 2 else "warning",
            metric_value=float(refund_rate),
            threshold_value=float(threshold),
            metric_name="refund_rate",
            comparison="gt",
        )
    return None


async def evaluate_revenue_decline(
    session: AsyncSession, *, workspace_id: UUID, current_revenue: Decimal, previous_revenue: Decimal, threshold_pct: Decimal = Decimal("0.20")
) -> BusinessAlert | None:
    """Evaluate revenue_decline alert. Compares current vs previous period."""
    if previous_revenue == ZERO or current_revenue is None:
        return None
    decline_pct = (previous_revenue - current_revenue) / previous_revenue
    if decline_pct > threshold_pct:
        return await create_or_update_alert(
            session, workspace_id=workspace_id,
            alert_type="revenue_decline",
            title=f"Revenue decline: {float(decline_pct):.1%} below previous period",
            message=f"Revenue dropped from {float(previous_revenue):.2f} to {float(current_revenue):.2f} ({float(decline_pct):.1%} decline)",
            severity="critical" if decline_pct > threshold_pct * 2 else "warning",
            metric_value=float(decline_pct),
            threshold_value=float(threshold_pct),
            metric_name="revenue_decline_pct",
            comparison="gt",
        )
    return None


async def evaluate_aov_decline(
    session: AsyncSession, *, workspace_id: UUID, current_aov: Decimal | None, previous_aov: Decimal | None, threshold_pct: Decimal = Decimal("0.15")
) -> BusinessAlert | None:
    """Evaluate aov_decline alert."""
    if current_aov is None or previous_aov is None or previous_aov == ZERO:
        return None
    decline_pct = (previous_aov - current_aov) / previous_aov
    if decline_pct > threshold_pct:
        return await create_or_update_alert(
            session, workspace_id=workspace_id,
            alert_type="aov_decline",
            title=f"AOV decline: {float(decline_pct):.1%} below previous period",
            message=f"AOV dropped from {float(previous_aov):.2f} to {float(current_aov):.2f} ({float(decline_pct):.1%} decline)",
            severity="warning",
            metric_value=float(decline_pct),
            threshold_value=float(threshold_pct),
            metric_name="aov_decline_pct",
            comparison="gt",
        )
    return None


async def evaluate_stockout_risk(
    session: AsyncSession, *, workspace_id: UUID, at_risk_count: int, threshold: int = 1
) -> BusinessAlert | None:
    """Evaluate stockout_risk alert."""
    if at_risk_count >= threshold:
        return await create_or_update_alert(
            session, workspace_id=workspace_id,
            alert_type="stockout_risk",
            title=f"Stockout risk: {at_risk_count} product(s) below reorder threshold",
            message=f"{at_risk_count} product(s) have inventory at or below reorder threshold",
            severity="warning" if at_risk_count < 5 else "critical",
            metric_value=at_risk_count,
            threshold_value=threshold,
            metric_name="stockout_risk_count",
            comparison="gte",
        )
    return None


# --------------------------------------------------------------------------- #
# Queries
# --------------------------------------------------------------------------- #


async def _load_alert(
    session: AsyncSession, *, workspace_id: UUID, alert_id: UUID
) -> BusinessAlert:
    result = await session.execute(
        select(BusinessAlert).where(
            BusinessAlert.id == alert_id,
            BusinessAlert.workspace_id == workspace_id,
        )
    )
    alert = result.scalar_one_or_none()
    if alert is None:
        raise AlertNotFound(f"Alert {alert_id} not found")
    return alert


async def get_alert(
    session: AsyncSession, *, workspace_id: UUID, alert_id: UUID
) -> BusinessAlert:
    return await _load_alert(session, workspace_id=workspace_id, alert_id=alert_id)


async def list_alerts(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    status: str | None = None,
    alert_type: str | None = None,
    severity: str | None = None,
    limit: int = 50,
) -> list[BusinessAlert]:
    query = select(BusinessAlert).where(BusinessAlert.workspace_id == workspace_id)
    if status:
        query = query.where(BusinessAlert.status == status)
    if alert_type:
        query = query.where(BusinessAlert.alert_type == alert_type)
    if severity:
        query = query.where(BusinessAlert.severity == severity)
    query = query.order_by(BusinessAlert.last_detected_at.desc()).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_active_alerts_count(
    session: AsyncSession, *, workspace_id: UUID
) -> dict[str, int]:
    """Get count of active alerts by type."""
    counts = {t: 0 for t in ALERT_TYPES}
    result = await session.execute(
        select(BusinessAlert.alert_type, func.count(BusinessAlert.id)).where(
            BusinessAlert.workspace_id == workspace_id,
            BusinessAlert.status == "active",
        ).group_by(BusinessAlert.alert_type)
    )
    for alert_type, count in result.all():
        counts[alert_type] = count
    return counts


# Need func for count queries
from sqlalchemy import func  # noqa: E402
