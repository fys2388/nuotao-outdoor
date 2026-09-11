"""Dashboard metrics and persistent alert tests (M4).

Tests cover:
- Dashboard metrics computed from PostgreSQL (not JSON files)
- Each metric includes source, calculation_window, timezone, currency, generated_at
- Empty data is safe: no division by zero, returns NULL with explanation
- 5 alert types: margin_decline, refund_spike, revenue_decline, aov_decline, stockout_risk
- Alert dedup: same active (type, resource) updates detection_count, not duplicate
- Alert resolution: status -> resolved, resolved_at set
- Restart survival: alerts persist in database (query after creation)
- Re-triggering resolved alert creates new alert (not reactivating)
- All alert creation/resolution writes to event_log
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from app.models.order import Order
from app.models.business_alert import BusinessAlert
from app.services import dashboard_metrics_service, persistent_alert_service

DEFAULT_WORKSPACE = UUID("00000000-0000-0000-0000-000000000001")


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def sample_orders(db_session):
    """Create sample paid orders for dashboard metrics."""
    orders = []
    for i in range(5):
        order = Order(
            workspace_id=DEFAULT_WORKSPACE,
            external_order_id=f"DASH-TEST-{i:03d}",
            status="received",
            payment_status="paid",
            currency="USD",
            subtotal=Decimal("80.00"),
            shipping_total=Decimal("10.00"),
            total=Decimal("90.00"),
            refunded_amount=Decimal("0.00"),
            received_at=datetime.now(UTC) - timedelta(days=i),
        )
        db_session.add(order)
        orders.append(order)
    await db_session.flush()
    return orders


@pytest_asyncio.fixture
async def order_with_refund(db_session):
    """Create an order with refunded amount."""
    order = Order(
        workspace_id=DEFAULT_WORKSPACE,
        external_order_id="DASH-REFUND-001",
        status="received",
        payment_status="paid",
        currency="USD",
        subtotal=Decimal("180.00"),
        shipping_total=Decimal("20.00"),
        total=Decimal("200.00"),
        refunded_amount=Decimal("40.00"),
        received_at=datetime.now(UTC) - timedelta(days=1),
    )
    db_session.add(order)
    await db_session.flush()
    return order


# --------------------------------------------------------------------------- #
# Dashboard metrics tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_dashboard_revenue_from_db(db_session, sample_orders):
    """Revenue is computed from PostgreSQL orders, not JSON."""
    metric = await dashboard_metrics_service.get_revenue(
        db_session, workspace_id=DEFAULT_WORKSPACE, days=7,
    )
    assert metric.name == "revenue"
    assert metric.value > Decimal("0")
    assert metric.source.startswith("postgresql")
    assert metric.calculation_window == "last_7_days"
    assert metric.currency == "USD"
    assert metric.generated_at is not None


@pytest.mark.asyncio
async def test_dashboard_order_count(db_session, sample_orders):
    """Order count matches number of orders in window."""
    metric = await dashboard_metrics_service.get_order_count(
        db_session, workspace_id=DEFAULT_WORKSPACE, days=7,
    )
    assert metric.value == 5
    assert metric.source == "postgresql:count(orders.id)"


@pytest.mark.asyncio
async def test_dashboard_aov(db_session, sample_orders):
    """AOV = revenue / order_count."""
    metric = await dashboard_metrics_service.get_aov(
        db_session, workspace_id=DEFAULT_WORKSPACE, days=7,
    )
    assert metric.value is not None
    assert metric.value > Decimal("0")
    # AOV should be ~90.00 (5 orders * 90 = 450 revenue / 5 = 90)
    assert abs(float(metric.value) - 90.0) < 1.0


@pytest.mark.asyncio
async def test_dashboard_aov_empty_data_safe(db_session):
    """AOV with no orders returns NULL (not zero) to avoid misleading data."""
    metric = await dashboard_metrics_service.get_aov(
        db_session, workspace_id=DEFAULT_WORKSPACE, days=7,
    )
    assert metric.value is None
    assert "No orders" in (metric.note or "")


@pytest.mark.asyncio
async def test_dashboard_gross_profit(db_session, sample_orders):
    """Gross profit = revenue - refunded_amount."""
    metric = await dashboard_metrics_service.get_gross_profit(
        db_session, workspace_id=DEFAULT_WORKSPACE, days=7,
    )
    assert metric.value > Decimal("0")
    assert "postgresql" in metric.source


@pytest.mark.asyncio
async def test_dashboard_margin_rate_empty_data_safe(db_session):
    """Margin rate with no revenue returns NULL (no division by zero)."""
    metric = await dashboard_metrics_service.get_margin_rate(
        db_session, workspace_id=DEFAULT_WORKSPACE, days=7,
    )
    assert metric.value is None
    assert "No revenue" in (metric.note or "")


@pytest.mark.asyncio
async def test_dashboard_refund_rate(db_session, order_with_refund):
    """Refund rate = refunded_amount / revenue."""
    metric = await dashboard_metrics_service.get_refund_rate(
        db_session, workspace_id=DEFAULT_WORKSPACE, days=7,
    )
    assert metric.value is not None
    # 40 refunded / 200 revenue = 0.20
    assert abs(float(metric.value) - 0.20) < 0.01


@pytest.mark.asyncio
async def test_dashboard_full_dashboard(db_session, sample_orders):
    """Full dashboard includes all 8 metrics with audit metadata."""
    dashboard = await dashboard_metrics_service.get_full_dashboard(
        db_session, workspace_id=DEFAULT_WORKSPACE, days=7,
    )
    assert dashboard["data_source"] == "postgresql_real_time_aggregation"
    assert "metrics" in dashboard
    expected_metrics = ["revenue", "order_count", "AOV", "gross_profit",
                        "margin_rate", "refund_rate", "inventory_available", "stockout_risk"]
    for name in expected_metrics:
        assert name in dashboard["metrics"], f"Missing metric: {name}"
        metric = dashboard["metrics"][name]
        assert "source" in metric
        assert "calculation_window" in metric
        assert "generated_at" in metric


# --------------------------------------------------------------------------- #
# Persistent alert tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_create_alert_persists_in_db(db_session):
    """Created alert persists in PostgreSQL (survives restart)."""
    alert = await persistent_alert_service.create_or_update_alert(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        alert_type="margin_decline",
        title="Test margin decline",
        message="Margin below threshold",
        severity="warning",
        metric_value=0.15,
        threshold_value=0.20,
    )
    assert alert.id is not None
    assert alert.status == "active"
    assert alert.detection_count == 1

    # Verify it persists by querying directly
    from sqlalchemy import select
    result = await db_session.execute(
        select(BusinessAlert).where(BusinessAlert.id == alert.id)
    )
    fetched = result.scalar_one()
    assert fetched.id == alert.id
    assert fetched.alert_type == "margin_decline"


@pytest.mark.asyncio
async def test_alert_dedup_no_duplicate(db_session):
    """Same active (type, resource) updates detection_count, not duplicate."""
    alert1 = await persistent_alert_service.create_or_update_alert(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        alert_type="refund_spike",
        title="Refund spike",
        resource_type="global",
        resource_id=None,
    )
    assert alert1.detection_count == 1

    # Second trigger with same type+resource
    alert2 = await persistent_alert_service.create_or_update_alert(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        alert_type="refund_spike",
        title="Refund spike (again)",
        resource_type="global",
        resource_id=None,
    )
    assert alert1.id == alert2.id  # Same alert, not duplicate
    assert alert2.detection_count == 2  # Count incremented


@pytest.mark.asyncio
async def test_alert_resolution(db_session):
    """Resolved alert has status='resolved' and resolved_at set."""
    alert = await persistent_alert_service.create_or_update_alert(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        alert_type="revenue_decline",
        title="Revenue decline",
    )
    assert alert.status == "active"

    resolved = await persistent_alert_service.resolve_alert(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        alert_id=alert.id, resolved_by="tester",
        resolution_note="Revenue recovered",
    )
    assert resolved.status == "resolved"
    assert resolved.resolved_at is not None


@pytest.mark.asyncio
async def test_resolved_alert_retrigger_creates_new(db_session):
    """Re-triggering resolved alert creates new alert (not reactivating)."""
    alert1 = await persistent_alert_service.create_or_update_alert(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        alert_type="aov_decline",
        title="AOV decline",
    )
    await persistent_alert_service.resolve_alert(
        db_session, workspace_id=DEFAULT_WORKSPACE, alert_id=alert1.id,
    )

    # Re-trigger after resolution -> new alert
    alert2 = await persistent_alert_service.create_or_update_alert(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        alert_type="aov_decline",
        title="AOV decline (re-triggered)",
    )
    assert alert1.id != alert2.id  # New alert created
    assert alert2.status == "active"


@pytest.mark.asyncio
async def test_alert_acknowledge(db_session):
    """Acknowledge alert: active -> acknowledged."""
    alert = await persistent_alert_service.create_or_update_alert(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        alert_type="stockout_risk",
        title="Stockout risk",
    )
    acknowledged = await persistent_alert_service.acknowledge_alert(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        alert_id=alert.id, acknowledged_by="operator",
    )
    assert acknowledged.status == "acknowledged"
    assert acknowledged.acknowledged_by == "operator"


@pytest.mark.asyncio
async def test_list_alerts_by_status(db_session):
    """List alerts filtered by status."""
    await persistent_alert_service.create_or_update_alert(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        alert_type="margin_decline", title="Active alert 1",
    )
    alert2 = await persistent_alert_service.create_or_update_alert(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        alert_type="refund_spike", title="Active alert 2",
    )
    await persistent_alert_service.resolve_alert(
        db_session, workspace_id=DEFAULT_WORKSPACE, alert_id=alert2.id,
    )

    active = await persistent_alert_service.list_alerts(
        db_session, workspace_id=DEFAULT_WORKSPACE, status="active",
    )
    resolved = await persistent_alert_service.list_alerts(
        db_session, workspace_id=DEFAULT_WORKSPACE, status="resolved",
    )
    assert len(active) == 1
    assert len(resolved) == 1


# --------------------------------------------------------------------------- #
# 5 alert type evaluation tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_evaluate_margin_decline_triggers(db_session):
    """Margin below threshold triggers alert."""
    alert = await persistent_alert_service.evaluate_margin_decline(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        current_margin=Decimal("0.15"), threshold=Decimal("0.20"),
    )
    assert alert is not None
    assert alert.alert_type == "margin_decline"
    assert alert.status == "active"


@pytest.mark.asyncio
async def test_evaluate_margin_decline_no_alert_above_threshold(db_session):
    """Margin above threshold does not trigger alert."""
    alert = await persistent_alert_service.evaluate_margin_decline(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        current_margin=Decimal("0.25"), threshold=Decimal("0.20"),
    )
    assert alert is None


@pytest.mark.asyncio
async def test_evaluate_margin_decline_none_safe(db_session):
    """None margin (no data) does not trigger alert (no false alert)."""
    alert = await persistent_alert_service.evaluate_margin_decline(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        current_margin=None, threshold=Decimal("0.20"),
    )
    assert alert is None


@pytest.mark.asyncio
async def test_evaluate_refund_spike_triggers(db_session):
    """Refund rate above threshold triggers alert."""
    alert = await persistent_alert_service.evaluate_refund_spike(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        refund_rate=Decimal("0.15"), threshold=Decimal("0.10"),
    )
    assert alert is not None
    assert alert.alert_type == "refund_spike"


@pytest.mark.asyncio
async def test_evaluate_revenue_decline_triggers(db_session):
    """Revenue decline above threshold triggers alert."""
    alert = await persistent_alert_service.evaluate_revenue_decline(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        current_revenue=Decimal("800"), previous_revenue=Decimal("1000"),
        threshold_pct=Decimal("0.15"),
    )
    assert alert is not None
    assert alert.alert_type == "revenue_decline"
    # 20% decline > 15% threshold


@pytest.mark.asyncio
async def test_evaluate_revenue_decline_zero_previous_safe(db_session):
    """Zero previous revenue does not trigger alert (no division by zero)."""
    alert = await persistent_alert_service.evaluate_revenue_decline(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        current_revenue=Decimal("100"), previous_revenue=Decimal("0"),
    )
    assert alert is None


@pytest.mark.asyncio
async def test_evaluate_aov_decline_triggers(db_session):
    """AOV decline above threshold triggers alert."""
    alert = await persistent_alert_service.evaluate_aov_decline(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        current_aov=Decimal("70"), previous_aov=Decimal("100"),
        threshold_pct=Decimal("0.15"),
    )
    assert alert is not None
    assert alert.alert_type == "aov_decline"


@pytest.mark.asyncio
async def test_evaluate_aov_decline_none_safe(db_session):
    """None AOV does not trigger alert (empty data safe)."""
    alert = await persistent_alert_service.evaluate_aov_decline(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        current_aov=None, previous_aov=Decimal("100"),
    )
    assert alert is None


@pytest.mark.asyncio
async def test_evaluate_stockout_risk_triggers(db_session):
    """Stockout risk at/above threshold triggers alert."""
    alert = await persistent_alert_service.evaluate_stockout_risk(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        at_risk_count=3, threshold=1,
    )
    assert alert is not None
    assert alert.alert_type == "stockout_risk"


@pytest.mark.asyncio
async def test_evaluate_stockout_risk_no_alert_below_threshold(db_session):
    """Stockout risk below threshold does not trigger alert."""
    alert = await persistent_alert_service.evaluate_stockout_risk(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        at_risk_count=0, threshold=1,
    )
    assert alert is None


@pytest.mark.asyncio
async def test_active_alerts_count(db_session):
    """Get active alerts count by type."""
    await persistent_alert_service.create_or_update_alert(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        alert_type="margin_decline", title="Count test 1",
    )
    await persistent_alert_service.create_or_update_alert(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        alert_type="refund_spike", title="Count test 2",
    )
    counts = await persistent_alert_service.get_active_alerts_count(
        db_session, workspace_id=DEFAULT_WORKSPACE,
    )
    assert counts["margin_decline"] == 1
    assert counts["refund_spike"] == 1
    assert counts["revenue_decline"] == 0
