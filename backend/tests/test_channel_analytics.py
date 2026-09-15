"""Regression tests for B2C/B2B channel analytics."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.b2b import B2BAgent, B2BOrder, B2BOrderItem
from app.models.b2b_finance import B2BInvoice
from app.models.order import Order, OrderItem
from app.models.product import Product, ProductCost
from app.models.supply_chain import InventorySnapshot
from app.services.channel_analytics_service import build_channel_analytics

OTHER_WORKSPACE = UUID("00000000-0000-0000-0000-000000000099")


def test_channel_analytics_endpoint_requires_authentication(client) -> None:
    response = client.get("/api/v1/analytics/channel-performance")
    assert response.status_code == 401


def test_legacy_simulated_dashboard_endpoints_are_retired(client) -> None:
    product_response = client.get("/api/v1/dashboard/product-performance")
    daily_response = client.post("/api/v1/dashboard/daily-metrics")
    assert product_response.status_code == 410
    assert daily_response.status_code == 410


@pytest.mark.asyncio
async def test_channel_analytics_attributes_sales_profit_customer_ar_and_inventory(
    db_session,
) -> None:
    product = Product(
        workspace_id=DEFAULT_WORKSPACE_ID,
        sku="CHANNEL-1",
        name="Channel Test Product",
        status="active",
    )
    db_session.add(product)
    await db_session.flush()
    db_session.add(
        ProductCost(
            workspace_id=DEFAULT_WORKSPACE_ID,
            product_id=product.id,
            currency="USD",
            total_landed_cost=Decimal("40.00"),
            total_cost=Decimal("40.00"),
        )
    )

    b2c_order = Order(
        workspace_id=DEFAULT_WORKSPACE_ID,
        external_order_id="CHANNEL-B2C-1",
        status="completed",
        currency="USD",
        business_model="B2C",
        customer_reference_id="customer-1",
        total=Decimal("100.00"),
        profit_snapshot={
            "contribution_margin": "30.00",
            "cost_status": "KNOWN",
        },
        received_at=datetime.now(UTC),
    )
    b2c_order.items = [
        OrderItem(
            workspace_id=DEFAULT_WORKSPACE_ID,
            product_id=product.id,
            sku=product.sku,
            name=product.name,
            quantity=2,
            unit_price=Decimal("50.00"),
            line_total=Decimal("100.00"),
        )
    ]
    db_session.add(b2c_order)

    agent = B2BAgent(
        workspace_id=DEFAULT_WORKSPACE_ID,
        agent_number="AG-CHANNEL",
        company_name="Channel Buyer",
        contact_name="Buyer",
        email="buyer@example.com",
        hashed_password="not-used",
        tier="gold",
        status="active",
        currency="USD",
        credit_limit=Decimal("1000.00"),
        current_balance=Decimal("100.00"),
    )
    db_session.add(agent)
    await db_session.flush()

    b2b_order = B2BOrder(
        workspace_id=DEFAULT_WORKSPACE_ID,
        order_number="CHANNEL-B2B-1",
        agent_id=agent.id,
        business_model="B2B",
        status="confirmed",
        payment_status="unpaid",
        subtotal=Decimal("200.00"),
        shipping_cost=Decimal("40.00"),
        total=Decimal("240.00"),
        currency="USD",
        shipping_address={},
    )
    b2b_order.items = [
        B2BOrderItem(
            workspace_id=DEFAULT_WORKSPACE_ID,
            product_id=product.id,
            product_name=product.name,
            sku=product.sku,
            quantity=4,
            unit_price=Decimal("50.00"),
            subtotal=Decimal("200.00"),
            currency="USD",
        )
    ]
    db_session.add(b2b_order)
    await db_session.flush()

    today = date.today()
    db_session.add(
        B2BInvoice(
            workspace_id=DEFAULT_WORKSPACE_ID,
            invoice_number="INV-CHANNEL-1",
            order_id=b2b_order.id,
            agent_id=agent.id,
            status="issued",
            currency="USD",
            issue_date=today - timedelta(days=60),
            due_date=today - timedelta(days=45),
            subtotal=Decimal("200.00"),
            shipping_amount=Decimal("40.00"),
            total=Decimal("240.00"),
            balance_due=Decimal("240.00"),
            items_snapshot=[],
            created_by="tester",
        )
    )
    db_session.add(
        InventorySnapshot(
            workspace_id=DEFAULT_WORKSPACE_ID,
            product_id=product.id,
            location="cn",
            quantity=10,
            reserved=2,
            available=8,
            in_transit=3,
        )
    )

    other_product = Product(
        workspace_id=OTHER_WORKSPACE,
        sku="OTHER-1",
        name="Other Workspace Product",
        status="active",
    )
    db_session.add(other_product)
    await db_session.flush()
    db_session.add(
        Order(
            workspace_id=OTHER_WORKSPACE,
            external_order_id="OTHER-B2C-1",
            status="completed",
            currency="USD",
            business_model="B2C",
            total=Decimal("999.00"),
            profit_snapshot={"contribution_margin": "500.00"},
            received_at=datetime.now(UTC),
        )
    )
    await db_session.commit()

    report = await build_channel_analytics(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        start_date=today,
        end_date=today,
    )

    summaries = {
        (row.business_model, row.currency): row
        for row in report.channel_summaries
    }
    assert summaries[("B2C", "USD")].revenue == Decimal("100.00")
    assert summaries[("B2C", "USD")].gross_profit == Decimal("30.00")
    assert summaries[("B2B", "USD")].revenue == Decimal("240.00")
    assert summaries[("B2B", "USD")].gross_profit == Decimal("40.00")
    assert summaries[("B2B", "USD")].gross_margin_percent == Decimal("20.00")

    b2b_customer = next(
        row for row in report.top_customers if row.business_model == "B2B"
    )
    assert b2b_customer.customer_id == str(agent.id)
    assert b2b_customer.revenue == Decimal("240.00")
    assert b2b_customer.available_credit == Decimal("900.00")

    assert report.receivable_aging[0].days_31_60 == Decimal("240.00")
    inventory = report.inventory_performance[0]
    assert inventory.product_id == str(product.id)
    assert inventory.b2c_units == 2
    assert inventory.b2b_units == 4
    assert inventory.current_inventory == 10
    assert inventory.turnover_ratio == Decimal("0.60")
    assert inventory.days_of_inventory == Decimal("1.67")
    assert report.data_quality.cost_coverage_percent == Decimal("88.24")


@pytest.mark.asyncio
async def test_channel_analytics_never_combines_cost_coverage_across_currencies(
    db_session,
) -> None:
    now = datetime.now(UTC)
    db_session.add_all(
        [
            Order(
                workspace_id=DEFAULT_WORKSPACE_ID,
                external_order_id="CHANNEL-USD-1",
                status="completed",
                currency="USD",
                business_model="B2C",
                total=Decimal("100.00"),
                profit_snapshot={"contribution_margin": "30.00"},
                received_at=now,
            ),
            Order(
                workspace_id=DEFAULT_WORKSPACE_ID,
                external_order_id="CHANNEL-EUR-1",
                status="completed",
                currency="EUR",
                business_model="B2C",
                total=Decimal("80.00"),
                profit_snapshot=None,
                received_at=now,
            ),
        ]
    )
    await db_session.commit()

    today = date.today()
    report = await build_channel_analytics(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        start_date=today,
        end_date=today,
    )

    coverage_by_currency = {
        row.currency: row.data_quality.cost_coverage_percent
        for row in report.channel_summaries
    }
    assert coverage_by_currency == {
        "EUR": Decimal("0.00"),
        "USD": Decimal("100.00"),
    }
    assert report.data_quality.status == "partial"
    assert report.data_quality.cost_coverage_percent is None
    assert any("multiple currencies" in note for note in report.data_quality.notes)


@pytest.mark.asyncio
async def test_channel_analytics_rejects_oversized_range(db_session) -> None:
    today = date.today()
    with pytest.raises(ValueError, match="cannot exceed 366 days"):
        await build_channel_analytics(
            db_session,
            workspace_id=DEFAULT_WORKSPACE_ID,
            start_date=today - timedelta(days=367),
            end_date=today,
        )
