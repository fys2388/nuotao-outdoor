"""Regression tests for real dashboard profit aggregation."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.order import Order
from app.services.dashboard_service import get_dashboard_summary_real


@pytest.mark.asyncio
async def test_dashboard_uses_order_profit_snapshot_and_reports_partial_coverage(
    db_session,
) -> None:
    db_session.add_all(
        [
            Order(
                workspace_id=DEFAULT_WORKSPACE_ID,
                external_order_id="DASH-PROFIT-KNOWN",
                status="received",
                currency="USD",
                total=Decimal("100.00"),
                profit_snapshot={
                    "contribution_margin": "30.00",
                    "cost_status": "KNOWN",
                },
                received_at=datetime.now(UTC),
            ),
            Order(
                workspace_id=DEFAULT_WORKSPACE_ID,
                external_order_id="DASH-PROFIT-MISSING",
                status="received",
                currency="USD",
                total=Decimal("100.00"),
                profit_snapshot={},
                received_at=datetime.now(UTC),
            ),
        ]
    )
    await db_session.commit()

    summary = await get_dashboard_summary_real(db_session, DEFAULT_WORKSPACE_ID)
    today = summary["today"]

    assert today["revenue"]["gross_profit"] == 30.0
    assert today["revenue"]["gross_margin_percent"] == 30.0
    assert today["revenue"]["estimated_cost"] is None
    assert today["data_quality"]["cost_status"] == "partial"
    assert today["data_quality"]["profit_known_orders"] == 1
    assert today["data_quality"]["cost_coverage_percent"] == 50.0


@pytest.mark.asyncio
async def test_dashboard_does_not_invent_profit_without_snapshots(db_session) -> None:
    db_session.add(
        Order(
            workspace_id=DEFAULT_WORKSPACE_ID,
            external_order_id="DASH-NO-COST",
            status="received",
            currency="USD",
            total=Decimal("75.00"),
            profit_snapshot={},
            received_at=datetime.now(UTC),
        )
    )
    await db_session.commit()

    summary = await get_dashboard_summary_real(db_session, DEFAULT_WORKSPACE_ID)
    today = summary["today"]

    assert today["revenue"]["gross_profit"] == 0.0
    assert today["revenue"]["gross_margin_percent"] is None
    assert today["revenue"]["estimated_cost"] is None
    assert today["data_quality"]["cost_status"] == "missing"
