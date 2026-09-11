"""Real business data aggregation for the weekly report.

Pulls key metrics from the operational database (orders + settlements)
instead of the mock fallback, so decisions sit on auditable numbers:

- revenue / orders / AOV from orders
- gross profit from the per-order profit_snapshot (contribution margin)
- ad spend from orders.advertising_cost (order-attributed scope)
- cash-in from the settlements ledger (received / pending / disputed)

The output is structurally identical to the mock business_data so the
report generator stays untouched; every payload carries a data_source
marker so mock data can never masquerade as real data (AGENTS.md).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, OrderItem
from app.models.product import Product, ProductCost
from app.models.settlement import Settlement

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000001")
ZERO = Decimal("0")


def _fmt(value: Decimal) -> float:
    return float(f"{value:.2f}")


def _snapshot_margin(profit_snapshot: Any) -> Decimal:
    """Extract contribution_margin from an order's stored snapshot."""
    if isinstance(profit_snapshot, str):
        try:
            profit_snapshot = json.loads(profit_snapshot)
        except (ValueError, TypeError):
            return ZERO
    if not isinstance(profit_snapshot, dict):
        return ZERO
    try:
        return Decimal(str(profit_snapshot.get("contribution_margin", "0")))
    except (ValueError, TypeError):
        return ZERO


async def build_business_data_from_db(
    session: AsyncSession,
    week_start: str,
    week_end: str,
    *,
    workspace_id: UUID = DEFAULT_WORKSPACE_ID,
) -> dict[str, Any]:
    """Aggregate a week's operating numbers from the database.

    Returns the same shape as the mock generator, plus a data_source marker
    and a cash_in block from the settlements ledger.
    """
    start_dt = datetime.strptime(f"{week_start} 00:00:00", "%Y-%m-%d %H:%M:%S")
    end_dt = datetime.strptime(f"{week_end} 23:59:59", "%Y-%m-%d %H:%M:%S")

    # ---- orders in window -------------------------------------------------
    order_rows = (
        await session.execute(
            select(Order).where(
                Order.workspace_id == workspace_id,
                Order.received_at >= start_dt,
                Order.received_at <= end_dt,
            )
        )
    ).scalars().all()

    total_orders = len(order_rows)
    total_revenue = sum((o.total or ZERO) for o in order_rows)
    refunded = sum((o.refunded_amount or ZERO) for o in order_rows)
    ad_spend = sum((o.advertising_cost or ZERO) for o in order_rows)
    gross_profit = sum(_snapshot_margin(o.profit_snapshot) for o in order_rows)

    # ---- line-level highlights (top products by revenue) ------------------
    highlights: list[dict[str, Any]] = []
    if order_rows:
        order_ids = [o.id for o in order_rows]
        line_rows = (
            await session.execute(
                select(OrderItem).where(OrderItem.order_id.in_(order_ids))
            )
        ).scalars().all()
        per_sku: dict[str, dict[str, Decimal | int | str]] = {}
        for line in line_rows:
            key = line.sku or line.name
            bucket = per_sku.setdefault(
                key, {"sku": key, "units": 0, "revenue": ZERO, "margin": ZERO}
            )
            bucket["units"] = int(bucket["units"]) + (line.quantity or 0)
            bucket["revenue"] = Decimal(bucket["revenue"]) + (line.line_total or ZERO)
        for key, bucket in sorted(
            per_sku.items(),
            key=lambda kv: Decimal(kv[1]["revenue"]),
            reverse=True,
        )[:5]:
            revenue = Decimal(bucket["revenue"])
            highlights.append(
                {
                    "name": key,
                    "units_sold": bucket["units"],
                    "revenue": _fmt(revenue),
                    "margin": 0.0,  # SKU-level margin requires cost mapping; see note
                    "trend": "n/a",
                    "note": "SKU 毛利待成本映射",
                }
            )

    # ---- settlements ledger (cash-in) -------------------------------------
    settlement_rows = (
        await session.execute(
            select(Settlement).where(
                Settlement.workspace_id == workspace_id,
            )
        )
    ).scalars().all()
    # received_at 落在周内的视为本周回款；其余按状态累计存量
    received_this_week = sum(
        (s.received_amount or ZERO)
        for s in settlement_rows
        if s.received_at is not None
        and start_dt.date() <= s.received_at.date() <= end_dt.date()
    )
    pending_amount = sum(
        max((s.expected_amount or ZERO) - (s.received_amount or ZERO) - (s.fees or ZERO), ZERO)
        for s in settlement_rows
        if s.status in {"expected", "partial", "disputed"}
    )
    disputed_amount = sum(
        max((s.expected_amount or ZERO) - (s.received_amount or ZERO) - (s.fees or ZERO), ZERO)
        for s in settlement_rows
        if s.status == "disputed"
    )

    gross_margin = (
        _fmt(gross_profit / total_revenue * 100) if total_revenue else 0.0
    )
    avg_order_value = _fmt(total_revenue / total_orders) if total_orders else 0.0
    refund_rate = _fmt(refunded / total_revenue * 100) if total_revenue else 0.0
    roas = _fmt(total_revenue / ad_spend) if ad_spend else None

    return {
        "data_source": "database",
        "key_metrics": {
            "total_orders": {"current": total_orders, "previous": None, "change_percent": None},
            "total_revenue": {
                "current": _fmt(total_revenue),
                "previous": None,
                "change_percent": None,
                "currency": "USD",
            },
            "gross_profit": {"current": _fmt(gross_profit), "previous": None, "change_percent": None},
            "gross_margin": {"current": gross_margin, "previous": None, "change_percent": None},
            "avg_order_value": {"current": avg_order_value, "previous": None, "change_percent": None},
            "refund_rate": {"current": refund_rate, "previous": None, "change_percent": None},
            "ad_spend": {"current": _fmt(ad_spend), "previous": None, "change_percent": None},
            "roas": {"current": roas, "previous": None, "change_percent": None},
            "new_customers": {"current": None, "previous": None, "change_percent": None},
            "returning_customers": {"current": None, "previous": None, "change_percent": None},
            "customer_acquisition_cost": {"current": None, "previous": None, "change_percent": None},
        },
        "cash_in": {
            "received_this_week": f"{received_this_week:.2f}",
            "pending_amount": f"{pending_amount:.2f}",
            "disputed_amount": f"{disputed_amount:.2f}",
        },
        "product_highlights": highlights,
        "marketing_performance": {},
        "customer_insights": {},
    }
