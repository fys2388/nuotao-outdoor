"""Tests for auditable exchange rates and Decimal-safe conversion."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.b2b import B2BAgent, B2BOrder, B2BOrderItem
from app.models.currency import ExchangeRate
from app.models.order import Order
from app.models.product import Product, ProductCost
from app.services.channel_analytics_service import build_channel_analytics
from app.services.currency_service import (
    ExchangeRateConflictError,
    ExchangeRateNotFoundError,
    convert_amount,
    create_exchange_rate,
    list_exchange_rates,
    resolve_exchange_rate,
)

OTHER_WORKSPACE = UUID("00000000-0000-0000-0000-000000000099")


def test_currency_rate_endpoint_requires_authentication(client) -> None:
    response = client.get("/api/v1/admin/currency-rates")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_exchange_rate_uses_latest_direct_rate_and_isolates_workspaces(
    db_session,
) -> None:
    today = date.today()
    await create_exchange_rate(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        base_currency="usd",
        quote_currency="eur",
        rate=Decimal("0.900000000000"),
        effective_date=today - timedelta(days=2),
        source="ecb",
        source_reference="test-1",
        created_by="tester",
    )
    await create_exchange_rate(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        base_currency="USD",
        quote_currency="EUR",
        rate=Decimal("0.800000000000"),
        effective_date=today - timedelta(days=1),
        source="ecb",
        source_reference="test-2",
        created_by="tester",
    )
    await create_exchange_rate(
        db_session,
        workspace_id=OTHER_WORKSPACE,
        base_currency="USD",
        quote_currency="EUR",
        rate=Decimal("0.700000000000"),
        effective_date=today,
        source="other",
        source_reference=None,
        created_by="tester",
    )

    resolved = await resolve_exchange_rate(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        base_currency="USD",
        quote_currency="EUR",
        as_of=today,
    )
    assert resolved is not None
    assert resolved.rate == Decimal("0.800000000000")
    converted = await convert_amount(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        amount=Decimal("125.00"),
        base_currency="USD",
        quote_currency="EUR",
        as_of=today,
    )
    assert converted == Decimal("100.00")

    other_rows = await list_exchange_rates(
        db_session,
        workspace_id=OTHER_WORKSPACE,
    )
    assert len(other_rows) == 1
    assert other_rows[0].rate == Decimal("0.700000000000")

    inverse = await resolve_exchange_rate(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        base_currency="EUR",
        quote_currency="USD",
        as_of=today,
    )
    assert inverse is None
    with pytest.raises(ExchangeRateNotFoundError):
        await convert_amount(
            db_session,
            workspace_id=DEFAULT_WORKSPACE_ID,
            amount=Decimal("100.00"),
            base_currency="EUR",
            quote_currency="USD",
            as_of=today,
        )


@pytest.mark.asyncio
async def test_exchange_rate_duplicate_pair_and_date_is_rejected(db_session) -> None:
    today = date.today()
    kwargs = {
        "workspace_id": DEFAULT_WORKSPACE_ID,
        "base_currency": "USD",
        "quote_currency": "GBP",
        "effective_date": today,
        "source": "manual",
        "source_reference": None,
        "created_by": "tester",
    }
    await create_exchange_rate(db_session, rate=Decimal("0.79"), **kwargs)
    with pytest.raises(ExchangeRateConflictError):
        await create_exchange_rate(db_session, rate=Decimal("0.80"), **kwargs)


@pytest.mark.asyncio
async def test_channel_analytics_converts_reporting_currency_explicitly(
    db_session,
) -> None:
    today = date.today()
    db_session.add(
        ExchangeRate(
            workspace_id=DEFAULT_WORKSPACE_ID,
            base_currency="EUR",
            quote_currency="USD",
            rate=Decimal("1.250000000000"),
            effective_date=today - timedelta(days=1),
            source="ecb",
            source_reference="eur-usd",
            created_by="tester",
        )
    )
    db_session.add_all(
        [
            Order(
                workspace_id=DEFAULT_WORKSPACE_ID,
                external_order_id="FX-USD-1",
                status="completed",
                currency="USD",
                business_model="B2C",
                total=Decimal("100.00"),
                profit_snapshot={"contribution_margin": "30.00"},
                received_at=datetime.now(UTC),
            ),
            Order(
                workspace_id=DEFAULT_WORKSPACE_ID,
                external_order_id="FX-EUR-1",
                status="completed",
                currency="EUR",
                business_model="B2C",
                total=Decimal("80.00"),
                profit_snapshot={"contribution_margin": "20.00"},
                received_at=datetime.now(UTC),
            ),
        ]
    )
    await db_session.commit()

    report = await build_channel_analytics(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        start_date=today,
        end_date=today,
        reporting_currency="USD",
    )

    assert report.reporting_currency == "USD"
    assert len(report.channel_summaries) == 1
    summary = report.channel_summaries[0]
    assert summary.business_model == "B2C"
    assert summary.currency == "USD"
    assert summary.revenue == Decimal("200.00")
    assert summary.gross_profit == Decimal("55.00")
    assert summary.orders == 2


@pytest.mark.asyncio
async def test_channel_analytics_converts_cost_currency_before_b2b_margin(
    db_session,
) -> None:
    today = date.today()
    product = Product(
        workspace_id=DEFAULT_WORKSPACE_ID,
        sku="FX-COST-1",
        name="FX Cost Product",
        status="active",
    )
    db_session.add(product)
    await db_session.flush()
    db_session.add(
        ProductCost(
            workspace_id=DEFAULT_WORKSPACE_ID,
            product_id=product.id,
            currency="CNY",
            total_landed_cost=Decimal("280.00"),
            total_cost=Decimal("280.00"),
            valid_from=datetime.now(UTC) - timedelta(days=2),
        )
    )
    db_session.add(
        ExchangeRate(
            workspace_id=DEFAULT_WORKSPACE_ID,
            base_currency="CNY",
            quote_currency="USD",
            rate=Decimal("0.140000000000"),
            effective_date=today - timedelta(days=3),
            source="bank",
            source_reference="cny-usd",
            created_by="tester",
        )
    )

    agent = B2BAgent(
        workspace_id=DEFAULT_WORKSPACE_ID,
        agent_number="AG-FX-COST",
        company_name="FX Buyer",
        contact_name="Buyer",
        email="fx-buyer@example.com",
        hashed_password="not-used",
        tier="standard",
        status="active",
        currency="USD",
        credit_limit=Decimal("1000.00"),
        current_balance=Decimal("0.00"),
    )
    db_session.add(agent)
    await db_session.flush()
    order = B2BOrder(
        workspace_id=DEFAULT_WORKSPACE_ID,
        order_number="B2B-FX-COST-1",
        agent_id=agent.id,
        business_model="B2B",
        status="confirmed",
        payment_status="unpaid",
        subtotal=Decimal("200.00"),
        shipping_cost=Decimal("0.00"),
        total=Decimal("200.00"),
        currency="USD",
        shipping_address={},
    )
    order.items = [
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
    db_session.add(order)
    await db_session.commit()

    report = await build_channel_analytics(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        start_date=today,
        end_date=today,
    )

    b2b = next(row for row in report.channel_summaries if row.business_model == "B2B")
    assert b2b.gross_profit == Decimal("43.20")
    assert b2b.gross_margin_percent == Decimal("21.60")
