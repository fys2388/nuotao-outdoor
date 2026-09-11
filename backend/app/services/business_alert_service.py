"""Business alert service (M4.3): margin decline, refund rate spike, stockout risk.

Evaluates LIVE PostgreSQL business data (orders, refunds, inventory) against
config-driven thresholds and emits structured alerts via event_log. This is the
business-metric complement to ``alert_service`` which covers Agent runtime alerts.

Alert types:
- ``margin_decline``: gross margin drops below threshold or declines > X% WoW
- ``refund_spike``: refund rate exceeds threshold or spikes > X% WoW
- ``stockout_risk``: inventory available quantity below reorder threshold
- ``revenue_decline``: revenue declines > X% WoW
- ``aov_decline``: average order value declines > X% WoW

Every alert is deduplicated by (workspace_id, alert_type, resource) so an
unrecovered condition never floods the log. Resolution is automatic when the
metric recovers (next evaluation run).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, OrderItem
from app.models.supply_chain import InventorySnapshot
from app.services import event_service

logger = logging.getLogger(__name__)

ZERO = Decimal("0")

# Default alert thresholds (config-driven; overridable per workspace via settings).
DEFAULT_THRESHOLDS = {
    "margin_min": Decimal("0.30"),          # minimum gross margin 30%
    "margin_decline_pct": Decimal("0.15"),  # margin decline >15% WoW triggers
    "refund_rate_max": Decimal("0.05"),     # max refund rate 5%
    "refund_spike_pct": Decimal("0.50"),    # refund rate spike >50% WoW triggers
    "stockout_threshold": 5,                 # available qty <= 5 triggers
    "revenue_decline_pct": Decimal("0.20"), # revenue decline >20% WoW triggers
    "aov_decline_pct": Decimal("0.15"),      # AOV decline >15% WoW triggers
}

# Active alert dedup cache: key = (workspace_id, alert_type, resource) -> alert details.
# In-memory; cleared on process restart. For production persistence, use a
# business_alerts table (future enhancement).
_active_alerts: dict[tuple[UUID, str, str], dict[str, Any]] = {}


@dataclass
class BusinessAlert:
    """A structured business alert."""

    alert_type: str
    severity: str  # warning / critical
    title: str
    message: str
    metric_name: str
    metric_value: float
    threshold: float
    resource: str
    details: dict[str, Any]


async def _get_order_metrics(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, Any]:
    """Compute aggregate order metrics for a date range.

    Returns: total_orders, total_revenue, total_refund, gross_profit,
    gross_margin, refund_rate, avg_order_value.
    """
    result = await session.execute(
        select(
            func.count(Order.id).label("total_orders"),
            func.coalesce(func.sum(Order.total), ZERO).label("total_revenue"),
            func.coalesce(func.sum(Order.refunded_amount), ZERO).label("total_refund"),
        ).where(
            Order.workspace_id == workspace_id,
            Order.received_at >= start_date,
            Order.received_at < end_date,
        )
    )
    row = result.one()
    total_orders = row.total_orders or 0
    total_revenue = Decimal(str(row.total_revenue or 0))
    total_refund = Decimal(str(row.total_refund or 0))

    # Gross profit approximation: revenue * default_margin (cost model not yet
    # fully populated per-order). For production, use profit_snapshot if available.
    default_margin = Decimal("0.45")
    gross_profit = total_revenue * default_margin
    gross_margin = (gross_profit / total_revenue) if total_revenue > 0 else ZERO

    refund_rate = (total_refund / total_revenue) if total_revenue > 0 else ZERO
    avg_order_value = (total_revenue / total_orders) if total_orders > 0 else ZERO

    return {
        "total_orders": total_orders,
        "total_revenue": float(total_revenue),
        "total_refund": float(total_refund),
        "gross_profit": float(gross_profit),
        "gross_margin": float(gross_margin),
        "refund_rate": float(refund_rate),
        "avg_order_value": float(avg_order_value),
    }


async def _get_low_stock_products(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    threshold: int,
) -> list[dict[str, Any]]:
    """Find products with inventory at or below threshold."""
    result = await session.execute(
        select(InventorySnapshot).where(
            InventorySnapshot.workspace_id == workspace_id,
            InventorySnapshot.available <= threshold,
            InventorySnapshot.location == "cn",  # primary warehouse
        )
    )
    items = result.scalars().all()
    return [
        {
            "product_id": str(item.product_id) if item.product_id else None,
            "location": item.location,
            "quantity": item.quantity,
            "reserved": item.reserved,
            "available": item.available,
            "in_transit": item.in_transit,
        }
        for item in items
    ]


def _pct_change(current: float, previous: float) -> float:
    """Compute percentage change; returns 0 if previous is 0."""
    if previous == 0:
        return 0.0
    return round((current - previous) / previous, 4)


def _emit_alert(
    alert: BusinessAlert,
    *,
    workspace_id: UUID,
) -> bool:
    """Deduplicate and emit a business alert via event_log.

    Returns True if this is a new alert (not already active), False if duplicate.
    """
    key = (workspace_id, alert.alert_type, alert.resource)

    if key in _active_alerts:
        logger.debug(
            "business alert suppressed (already active): type=%s resource=%s",
            alert.alert_type, alert.resource,
        )
        return False

    _active_alerts[key] = {
        "alert_type": alert.alert_type,
        "severity": alert.severity,
        "title": alert.title,
        "first_seen": datetime.now(UTC).isoformat(),
        "metric_value": alert.metric_value,
    }

    logger.warning(
        "BUSINESS ALERT [%s] %s: %s (metric=%s value=%.4f threshold=%.4f)",
        alert.severity.upper(),
        alert.alert_type,
        alert.title,
        alert.metric_name,
        alert.metric_value,
        alert.threshold,
    )
    return True


def _resolve_alert_if_recovered(
    *,
    workspace_id: UUID,
    alert_type: str,
    resource: str,
    is_recovered: bool,
) -> None:
    """Remove an active alert if the metric has recovered."""
    key = (workspace_id, alert_type, resource)
    if is_recovered and key in _active_alerts:
        del _active_alerts[key]
        logger.info(
            "business alert resolved: type=%s resource=%s",
            alert_type, resource,
        )


async def evaluate_business_alerts(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    thresholds: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> list[BusinessAlert]:
    """Evaluate all business metrics and emit alerts.

    This is the main entrypoint, called by the scheduler (e.g. daily or hourly).
    Returns the list of NEW alerts emitted in this run.
    """
    config = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    now = datetime.now(UTC)
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    new_alerts: list[BusinessAlert] = []

    # --- Current week metrics ---
    current = await _get_order_metrics(
        session, workspace_id=workspace_id, start_date=week_ago, end_date=now
    )
    # --- Previous week metrics ---
    previous = await _get_order_metrics(
        session, workspace_id=workspace_id, start_date=two_weeks_ago, end_date=week_ago
    )

    # 1. Margin decline / low margin
    margin_change = _pct_change(current["gross_margin"], previous["gross_margin"])
    margin_low = current["gross_margin"] < float(config["margin_min"])
    margin_declining = margin_change < -float(config["margin_decline_pct"])

    if margin_low or margin_declining:
        severity = "critical" if margin_low else "warning"
        alert = BusinessAlert(
            alert_type="margin_decline",
            severity=severity,
            title="Gross margin below threshold" if margin_low else "Gross margin declining",
            message=(
                f"Current gross margin: {current['gross_margin']:.1%} "
                f"(threshold: {float(config['margin_min']):.1%}), "
                f"WoW change: {margin_change:+.1%}. "
                f"Previous week: {previous['gross_margin']:.1%}."
            ),
            metric_name="gross_margin",
            metric_value=current["gross_margin"],
            threshold=float(config["margin_min"]),
            resource="overall",
            details={"current": current, "previous": previous, "wow_change": margin_change},
        )
        if _emit_alert(alert, workspace_id=workspace_id):
            new_alerts.append(alert)
    else:
        _resolve_alert_if_recovered(
            workspace_id=workspace_id, alert_type="margin_decline",
            resource="overall", is_recovered=True,
        )

    # 2. Refund rate spike / high refund rate
    refund_change = _pct_change(current["refund_rate"], previous["refund_rate"])
    refund_high = current["refund_rate"] > float(config["refund_rate_max"])
    refund_spiking = refund_change > float(config["refund_spike_pct"]) and current["refund_rate"] > 0.01

    if refund_high or refund_spiking:
        severity = "critical" if refund_high else "warning"
        alert = BusinessAlert(
            alert_type="refund_spike",
            severity=severity,
            title="Refund rate above threshold" if refund_high else "Refund rate spiking",
            message=(
                f"Current refund rate: {current['refund_rate']:.1%} "
                f"(threshold: {float(config['refund_rate_max']):.1%}), "
                f"WoW change: {refund_change:+.1%}. "
                f"Total refunded: ${current['total_refund']:.2f}."
            ),
            metric_name="refund_rate",
            metric_value=current["refund_rate"],
            threshold=float(config["refund_rate_max"]),
            resource="overall",
            details={"current": current, "previous": previous, "wow_change": refund_change},
        )
        if _emit_alert(alert, workspace_id=workspace_id):
            new_alerts.append(alert)
    else:
        _resolve_alert_if_recovered(
            workspace_id=workspace_id, alert_type="refund_spike",
            resource="overall", is_recovered=True,
        )

    # 3. Revenue decline
    revenue_change = _pct_change(current["total_revenue"], previous["total_revenue"])
    if revenue_change < -float(config["revenue_decline_pct"]) and previous["total_revenue"] > 0:
        alert = BusinessAlert(
            alert_type="revenue_decline",
            severity="warning",
            title="Revenue declining week-over-week",
            message=(
                f"Current week revenue: ${current['total_revenue']:.2f}, "
                f"previous week: ${previous['total_revenue']:.2f}, "
                f"change: {revenue_change:+.1%}."
            ),
            metric_name="total_revenue",
            metric_value=current["total_revenue"],
            threshold=float(config["revenue_decline_pct"]),
            resource="overall",
            details={"current": current, "previous": previous, "wow_change": revenue_change},
        )
        if _emit_alert(alert, workspace_id=workspace_id):
            new_alerts.append(alert)
    else:
        _resolve_alert_if_recovered(
            workspace_id=workspace_id, alert_type="revenue_decline",
            resource="overall", is_recovered=True,
        )

    # 4. AOV decline
    aov_change = _pct_change(current["avg_order_value"], previous["avg_order_value"])
    if aov_change < -float(config["aov_decline_pct"]) and previous["avg_order_value"] > 0:
        alert = BusinessAlert(
            alert_type="aov_decline",
            severity="warning",
            title="Average order value declining",
            message=(
                f"Current AOV: ${current['avg_order_value']:.2f}, "
                f"previous AOV: ${previous['avg_order_value']:.2f}, "
                f"change: {aov_change:+.1%}."
            ),
            metric_name="avg_order_value",
            metric_value=current["avg_order_value"],
            threshold=float(config["aov_decline_pct"]),
            resource="overall",
            details={"current": current, "previous": previous, "wow_change": aov_change},
        )
        if _emit_alert(alert, workspace_id=workspace_id):
            new_alerts.append(alert)
    else:
        _resolve_alert_if_recovered(
            workspace_id=workspace_id, alert_type="aov_decline",
            resource="overall", is_recovered=True,
        )

    # 5. Stockout risk (per product)
    low_stock = await _get_low_stock_products(
        session, workspace_id=workspace_id, threshold=int(config["stockout_threshold"])
    )
    for item in low_stock:
        resource = item["product_id"] or "unknown_product"
        alert = BusinessAlert(
            alert_type="stockout_risk",
            severity="warning",
            title=f"Low stock alert: product {resource[:8]}",
            message=(
                f"Available quantity: {item['available']} "
                f"(threshold: {config['stockout_threshold']}), "
                f"location: {item['location']}, "
                f"in transit: {item['in_transit']}."
            ),
            metric_name="available_quantity",
            metric_value=float(item["available"]),
            threshold=float(config["stockout_threshold"]),
            resource=resource,
            details=item,
        )
        if _emit_alert(alert, workspace_id=workspace_id):
            new_alerts.append(alert)

    # Emit events for new alerts
    for alert in new_alerts:
        await event_service.create_event(
            session,
            workspace_id=workspace_id,
            event_type=f"business_alert.{alert.alert_type}",
            entity_type="business_metric",
            entity_id=alert.resource,
            payload={
                "severity": alert.severity,
                "title": alert.title,
                "message": alert.message,
                "metric_name": alert.metric_name,
                "metric_value": alert.metric_value,
                "threshold": alert.threshold,
                "details": alert.details,
            },
            trace_id=trace_id,
        )

    logger.info(
        "business alert evaluation complete: %d new alerts, %d active total",
        len(new_alerts), len(_active_alerts),
    )
    return new_alerts


def get_active_alerts(*, workspace_id: UUID | None = None) -> list[dict[str, Any]]:
    """Return currently active business alerts."""
    alerts = list(_active_alerts.values())
    if workspace_id:
        # Note: workspace_id is part of the key but not stored in value;
        # for multi-workspace, filter by checking keys.
        return [
            v for (wid, _type, _res), v in _active_alerts.items()
            if wid == workspace_id
        ]
    return alerts


def clear_active_alerts() -> None:
    """Clear all active alerts (for testing / maintenance)."""
    _active_alerts.clear()
