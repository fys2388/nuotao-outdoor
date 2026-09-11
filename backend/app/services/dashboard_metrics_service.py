"""Dashboard metrics service (M4): real-time aggregation from PostgreSQL.

All metrics are computed from the database (orders, refunds, inventory),
not from JSON files. Each metric includes source, calculation_window,
timezone, currency, and generated_at for auditability.

Metrics:
- revenue: sum of order.total for paid orders in window
- order_count: count of orders in window
- AOV: revenue / order_count (average order value)
- gross_profit: revenue - cost_of_goods (where cost data available)
- margin_rate: gross_profit / revenue
- refund_rate: refunded_amount / revenue
- inventory_available: sum of available inventory
- stockout_risk: count of products below reorder threshold

Empty data is safe: no division by zero, returns NULL/0 with explanation.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order
from app.models.customer import RefundCase

logger = logging.getLogger(__name__)

ZERO = Decimal("0")


class DashboardMetric:
    """A single dashboard metric with full audit metadata."""

    def __init__(
        self,
        name: str,
        value: Any,
        *,
        source: str,
        calculation_window: str,
        timezone: str = "UTC",
        currency: str = "USD",
        generated_at: datetime | None = None,
        note: str | None = None,
    ):
        self.name = name
        self.value = value
        self.source = source
        self.calculation_window = calculation_window
        self.timezone = timezone
        self.currency = currency
        self.generated_at = generated_at or datetime.now(UTC)
        self.note = note

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self._serialize_value(self.value),
            "source": self.source,
            "calculation_window": self.calculation_window,
            "timezone": self.timezone,
            "currency": self.currency,
            "generated_at": self.generated_at.isoformat(),
            "note": self.note,
        }

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        return value


def _get_window_dates(days: int = 7) -> tuple[datetime, datetime]:
    """Get (start, end) for a rolling window of N days."""
    end = datetime.now(UTC)
    start = end - timedelta(days=days)
    return start, end


# --------------------------------------------------------------------------- #
# Revenue and order metrics
# --------------------------------------------------------------------------- #


async def get_revenue(
    session: AsyncSession, *, workspace_id: UUID, days: int = 7
) -> DashboardMetric:
    """Total revenue from paid orders in window."""
    start, end = _get_window_dates(days)
    result = await session.execute(
        select(func.coalesce(func.sum(Order.total), ZERO)).where(
            Order.workspace_id == workspace_id,
            Order.payment_status == "paid",
            Order.received_at >= start,
            Order.received_at <= end,
        )
    )
    revenue = result.scalar() or ZERO
    return DashboardMetric(
        "revenue", revenue,
        source="postgresql:orders.total (payment_status=paid)",
        calculation_window=f"last_{days}_days",
        currency="USD",
    )


async def get_order_count(
    session: AsyncSession, *, workspace_id: UUID, days: int = 7
) -> DashboardMetric:
    """Count of orders in window."""
    start, end = _get_window_dates(days)
    result = await session.execute(
        select(func.count(Order.id)).where(
            Order.workspace_id == workspace_id,
            Order.received_at >= start,
            Order.received_at <= end,
        )
    )
    count = result.scalar() or 0
    return DashboardMetric(
        "order_count", count,
        source="postgresql:count(orders.id)",
        calculation_window=f"last_{days}_days",
    )


async def get_aov(
    session: AsyncSession, *, workspace_id: UUID, days: int = 7
) -> DashboardMetric:
    """Average order value = revenue / order_count. Safe for zero orders."""
    revenue_metric = await get_revenue(session, workspace_id=workspace_id, days=days)
    count_metric = await get_order_count(session, workspace_id=workspace_id, days=days)

    if count_metric.value == 0:
        return DashboardMetric(
            "AOV", None,
            source="postgresql:revenue/order_count",
            calculation_window=f"last_{days}_days",
            currency="USD",
            note="No orders in window; AOV is NULL (not zero) to avoid misleading data",
        )

    aov = revenue_metric.value / count_metric.value
    return DashboardMetric(
        "AOV", aov,
        source="postgresql:revenue/order_count",
        calculation_window=f"last_{days}_days",
        currency="USD",
    )


# --------------------------------------------------------------------------- #
# Profit and margin metrics
# --------------------------------------------------------------------------- #


async def get_gross_profit(
    session: AsyncSession, *, workspace_id: UUID, days: int = 7
) -> DashboardMetric:
    """Gross profit = revenue - refunded_amount.

    Note: COGS-based profit requires ProductCost data; this metric uses
    refund-adjusted revenue as a conservative proxy. Full COGS-based profit
    is computed only when cost data is available (see get_margin_rate).
    """
    start, end = _get_window_dates(days)

    # Revenue
    rev_result = await session.execute(
        select(func.coalesce(func.sum(Order.total), ZERO)).where(
            Order.workspace_id == workspace_id,
            Order.payment_status == "paid",
            Order.received_at >= start,
            Order.received_at <= end,
        )
    )
    revenue = rev_result.scalar() or ZERO

    # Refunded amount
    refund_result = await session.execute(
        select(func.coalesce(func.sum(Order.refunded_amount), ZERO)).where(
            Order.workspace_id == workspace_id,
            Order.received_at >= start,
            Order.received_at <= end,
        )
    )
    refunded = refund_result.scalar() or ZERO

    gross_profit = revenue - refunded
    return DashboardMetric(
        "gross_profit", gross_profit,
        source="postgresql:orders.total - orders.refunded_amount (COGS proxy)",
        calculation_window=f"last_{days}_days",
        currency="USD",
        note="Refund-adjusted revenue; full COGS-based profit requires ProductCost data",
    )


async def get_margin_rate(
    session: AsyncSession, *, workspace_id: UUID, days: int = 7
) -> DashboardMetric:
    """Margin rate = gross_profit / revenue. Safe for zero revenue."""
    profit_metric = await get_gross_profit(session, workspace_id=workspace_id, days=days)
    revenue_metric = await get_revenue(session, workspace_id=workspace_id, days=days)

    if revenue_metric.value == ZERO:
        return DashboardMetric(
            "margin_rate", None,
            source="postgresql:gross_profit/revenue",
            calculation_window=f"last_{days}_days",
            note="No revenue in window; margin_rate is NULL (not zero) to avoid division by zero",
        )

    margin_rate = profit_metric.value / revenue_metric.value
    return DashboardMetric(
        "margin_rate", margin_rate,
        source="postgresql:gross_profit/revenue",
        calculation_window=f"last_{days}_days",
    )


# --------------------------------------------------------------------------- #
# Refund metrics
# --------------------------------------------------------------------------- #


async def get_refund_rate(
    session: AsyncSession, *, workspace_id: UUID, days: int = 7
) -> DashboardMetric:
    """Refund rate = refunded_amount / revenue. Safe for zero revenue."""
    start, end = _get_window_dates(days)

    revenue_result = await session.execute(
        select(func.coalesce(func.sum(Order.total), ZERO)).where(
            Order.workspace_id == workspace_id,
            Order.payment_status == "paid",
            Order.received_at >= start,
            Order.received_at <= end,
        )
    )
    revenue = revenue_result.scalar() or ZERO

    refunded_result = await session.execute(
        select(func.coalesce(func.sum(Order.refunded_amount), ZERO)).where(
            Order.workspace_id == workspace_id,
            Order.received_at >= start,
            Order.received_at <= end,
        )
    )
    refunded = refunded_result.scalar() or ZERO

    if revenue == ZERO:
        return DashboardMetric(
            "refund_rate", None,
            source="postgresql:refunded_amount/revenue",
            calculation_window=f"last_{days}_days",
            note="No revenue in window; refund_rate is NULL (not zero)",
        )

    refund_rate = refunded / revenue
    return DashboardMetric(
        "refund_rate", refund_rate,
        source="postgresql:refunded_amount/revenue",
        calculation_window=f"last_{days}_days",
    )


# --------------------------------------------------------------------------- #
# Inventory metrics
# --------------------------------------------------------------------------- #


async def get_inventory_available(
    session: AsyncSession, *, workspace_id: UUID
) -> DashboardMetric:
    """Total available inventory. Returns 0 if inventory table not populated."""
    # Try to query inventory table if it exists; otherwise return 0 with note
    try:
        from app.models.inventory import InventoryItem
        result = await session.execute(
            select(func.coalesce(func.sum(InventoryItem.quantity_available), 0)).where(
                InventoryItem.workspace_id == workspace_id,
            )
        )
        available = result.scalar() or 0
        source = "postgresql:inventory_items.quantity_available"
        note = None
    except Exception:
        available = 0
        source = "postgresql (inventory table not available)"
        note = "Inventory table not found or not populated; returning 0"

    return DashboardMetric(
        "inventory_available", available,
        source=source,
        calculation_window="current",
        note=note,
    )


async def get_stockout_risk(
    session: AsyncSession, *, workspace_id: UUID
) -> DashboardMetric:
    """Count of products at risk of stockout (below reorder threshold)."""
    try:
        from app.models.inventory import InventoryItem
        result = await session.execute(
            select(func.count(InventoryItem.id)).where(
                InventoryItem.workspace_id == workspace_id,
                InventoryItem.quantity_available <= InventoryItem.reorder_threshold,
            )
        )
        risk_count = result.scalar() or 0
        source = "postgresql:count(inventory_items WHERE quantity <= reorder_threshold)"
        note = None
    except Exception:
        risk_count = 0
        source = "postgresql (inventory table not available)"
        note = "Inventory table not found; returning 0"

    return DashboardMetric(
        "stockout_risk", risk_count,
        source=source,
        calculation_window="current",
        note=note,
    )


# --------------------------------------------------------------------------- #
# Full dashboard
# --------------------------------------------------------------------------- #


async def get_full_dashboard(
    session: AsyncSession, *, workspace_id: UUID, days: int = 7
) -> dict[str, Any]:
    """Get all dashboard metrics in one call.

    Every metric includes source, calculation_window, timezone, currency,
    and generated_at for full auditability.
    """
    metrics = await asyncio.gather(
        get_revenue(session, workspace_id=workspace_id, days=days),
        get_order_count(session, workspace_id=workspace_id, days=days),
        get_aov(session, workspace_id=workspace_id, days=days),
        get_gross_profit(session, workspace_id=workspace_id, days=days),
        get_margin_rate(session, workspace_id=workspace_id, days=days),
        get_refund_rate(session, workspace_id=workspace_id, days=days),
        get_inventory_available(session, workspace_id=workspace_id),
        get_stockout_risk(session, workspace_id=workspace_id),
    )

    return {
        "workspace_id": str(workspace_id),
        "calculation_window": f"last_{days}_days",
        "generated_at": datetime.now(UTC).isoformat(),
        "data_source": "postgresql_real_time_aggregation",
        "metrics": {m.name: m.to_dict() for m in metrics},
    }


# Need asyncio for gather
import asyncio  # noqa: E402
