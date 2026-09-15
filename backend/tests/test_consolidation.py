"""Brand/legal-entity attribution and consolidated-reporting tests."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.b2b import B2BAgent, B2BOrder, B2BOrderItem
from app.models.b2b_finance import B2BInvoice
from app.models.consolidation import CommerceAttribution
from app.models.order import Order, OrderItem
from app.models.product import Product, ProductCost
from app.schemas.order import WebhookOrderPayload
from app.services import b2b_finance_service, consolidation_service, order_service

OTHER_WORKSPACE = UUID("00000000-0000-0000-0000-000000000099")


async def _create_master_data(db_session):
    seller = await consolidation_service.create_legal_entity(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        code="nuotao-us",
        name="Nuotao US",
        legal_name="Nuotao US LLC",
        country="US",
        functional_currency="USD",
        status="active",
        notes=None,
        actor="tester@example.com",
    )
    buyer = await consolidation_service.create_legal_entity(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        code="nuotao-de",
        name="Nuotao DE",
        legal_name="Nuotao Deutschland GmbH",
        country="DE",
        functional_currency="EUR",
        status="active",
        notes=None,
        actor="tester@example.com",
    )
    brand = await consolidation_service.create_brand(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        code="nuotao",
        name="Nuotao Outdoor",
        status="active",
        default_legal_entity_id=seller.id,
        notes=None,
        actor="tester@example.com",
    )
    return seller, buyer, brand


@pytest.mark.asyncio
async def test_consolidation_report_only_eliminates_approved_intercompany(
    db_session,
) -> None:
    seller, buyer, brand = await _create_master_data(db_session)
    product = Product(
        workspace_id=DEFAULT_WORKSPACE_ID,
        sku="CONS-1",
        name="Consolidation Product",
        status="active",
        brand_id=brand.id,
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
        external_order_id="CONS-B2C-1",
        status="completed",
        currency="USD",
        business_model="B2C",
        total=Decimal("100.00"),
        profit_snapshot={"contribution_margin": "30.00"},
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
        agent_number="AG-CONS",
        company_name="Consolidation Buyer",
        contact_name="Buyer",
        email="consolidation@example.com",
        hashed_password="not-used",
        tier="gold",
        status="active",
        currency="USD",
        credit_limit=Decimal("5000.00"),
        current_balance=Decimal("200.00"),
    )
    db_session.add(agent)
    await db_session.flush()

    b2b_order = B2BOrder(
        workspace_id=DEFAULT_WORKSPACE_ID,
        order_number="CONS-B2B-1",
        agent_id=agent.id,
        status="confirmed",
        payment_status="unpaid",
        subtotal=Decimal("200.00"),
        shipping_cost=Decimal("0"),
        total=Decimal("200.00"),
        currency="USD",
        shipping_address={},
        items=[
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
        ],
    )
    db_session.add(b2b_order)
    await db_session.flush()

    today = date.today()
    invoice = B2BInvoice(
        workspace_id=DEFAULT_WORKSPACE_ID,
        invoice_number="INV-CONS-1",
        order_id=b2b_order.id,
        agent_id=agent.id,
        status="issued",
        currency="USD",
        issue_date=today,
        due_date=today + timedelta(days=30),
        subtotal=Decimal("200.00"),
        shipping_amount=Decimal("0"),
        total=Decimal("200.00"),
        balance_due=Decimal("200.00"),
        items_snapshot=[],
        created_by="tester",
    )
    db_session.add(invoice)
    await db_session.commit()

    await consolidation_service.upsert_attribution(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        entity_type="b2c_order",
        entity_id=b2c_order.id,
        brand_id=brand.id,
        legal_entity_id=seller.id,
        is_intercompany=False,
        counterparty_legal_entity_id=None,
        evidence={"source": "test"},
        actor="operator@example.com",
    )
    intercompany = await consolidation_service.upsert_attribution(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        entity_type="b2b_order",
        entity_id=b2b_order.id,
        brand_id=brand.id,
        legal_entity_id=seller.id,
        is_intercompany=True,
        counterparty_legal_entity_id=buyer.id,
        evidence={"contract": "IC-2026-001"},
        actor="operator@example.com",
    )
    invoice_attribution = await consolidation_service.upsert_attribution(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        entity_type="b2b_invoice",
        entity_id=invoice.id,
        brand_id=brand.id,
        legal_entity_id=seller.id,
        is_intercompany=True,
        counterparty_legal_entity_id=buyer.id,
        evidence={"contract": "IC-2026-001"},
        actor="operator@example.com",
    )

    before_approval = await consolidation_service.build_consolidated_report(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        start_date=today,
        end_date=today,
    )
    assert before_approval.totals.external_revenue == Decimal("300.00")
    assert before_approval.totals.intercompany_revenue == Decimal("0.00")
    row = before_approval.rows[0]
    assert row.open_receivables == Decimal("200.00")

    await consolidation_service.approve_elimination(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        attribution_id=intercompany.id,
        amount=Decimal("200.00"),
        evidence={"approved": "test"},
        actor="admin@example.com",
    )
    await consolidation_service.approve_elimination(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        attribution_id=invoice_attribution.id,
        amount=Decimal("200.00"),
        evidence={"approved": "test"},
        actor="admin@example.com",
    )

    after_approval = await consolidation_service.build_consolidated_report(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        start_date=today,
        end_date=today,
    )
    assert after_approval.totals.gross_revenue == Decimal("300.00")
    assert after_approval.totals.intercompany_revenue == Decimal("200.00")
    assert after_approval.totals.external_revenue == Decimal("100.00")
    assert after_approval.rows[0].open_receivables == Decimal("0.00")
    assert any(
        "profit is not eliminated" in note
        for note in after_approval.data_quality.notes
    )


@pytest.mark.asyncio
async def test_missing_attribution_is_visible_not_silently_assigned(
    db_session,
) -> None:
    order = Order(
        workspace_id=DEFAULT_WORKSPACE_ID,
        external_order_id="CONS-UNASSIGNED-1",
        status="completed",
        currency="USD",
        business_model="B2C",
        total=Decimal("80.00"),
        profit_snapshot={},
        received_at=datetime.now(UTC),
    )
    db_session.add(order)
    await db_session.commit()

    today = date.today()
    report = await consolidation_service.build_consolidated_report(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        start_date=today,
        end_date=today,
    )

    assert report.totals.external_revenue == Decimal("80.00")
    assert report.rows[0].brand_id is None
    assert report.rows[0].legal_entity_id is None
    assert report.rows[0].attribution_status == "missing"
    assert report.data_quality.attributed_order_percent == Decimal("0.00")
    assert report.data_quality.status == "partial"


@pytest.mark.asyncio
async def test_consolidation_is_workspace_scoped_and_respects_elimination_limit(
    db_session,
) -> None:
    seller, buyer, brand = await _create_master_data(db_session)
    order = Order(
        workspace_id=DEFAULT_WORKSPACE_ID,
        external_order_id="CONS-LIMIT-1",
        status="completed",
        currency="USD",
        business_model="B2C",
        total=Decimal("50.00"),
        profit_snapshot={},
        received_at=datetime.now(UTC),
    )
    db_session.add(order)
    await db_session.commit()

    attribution = await consolidation_service.upsert_attribution(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        entity_type="b2c_order",
        entity_id=order.id,
        brand_id=brand.id,
        legal_entity_id=seller.id,
        is_intercompany=True,
        counterparty_legal_entity_id=buyer.id,
        evidence={},
        actor="operator@example.com",
    )
    with pytest.raises(
        consolidation_service.ConsolidationError,
        match="cannot exceed",
    ):
        await consolidation_service.approve_elimination(
            db_session,
            workspace_id=DEFAULT_WORKSPACE_ID,
            attribution_id=attribution.id,
            amount=Decimal("50.01"),
            evidence={},
            actor="admin@example.com",
        )

    with pytest.raises(consolidation_service.ConsolidationNotFoundError):
        await consolidation_service.get_brand(
            db_session,
            workspace_id=OTHER_WORKSPACE,
            brand_id=brand.id,
        )

    today = date.today()
    other_report = await consolidation_service.build_consolidated_report(
        db_session,
        workspace_id=OTHER_WORKSPACE,
        start_date=today,
        end_date=today,
    )
    assert other_report.rows == []


@pytest.mark.asyncio
async def test_master_codes_are_unique_per_workspace(db_session) -> None:
    await _create_master_data(db_session)
    with pytest.raises(consolidation_service.ConsolidationConflictError):
        await consolidation_service.create_brand(
            db_session,
            workspace_id=DEFAULT_WORKSPACE_ID,
            code="nuotao",
            name="Duplicate",
            status="active",
            default_legal_entity_id=None,
            notes=None,
            actor="tester@example.com",
        )


@pytest.mark.asyncio
async def test_attribution_inference_and_invoice_copy(db_session) -> None:
    seller, _buyer, brand = await _create_master_data(db_session)
    product = Product(
        workspace_id=DEFAULT_WORKSPACE_ID,
        sku="CONS-AUTO-1",
        name="Automatic Attribution Product",
        status="active",
        brand_id=brand.id,
    )
    db_session.add(product)
    await db_session.flush()

    agent = B2BAgent(
        workspace_id=DEFAULT_WORKSPACE_ID,
        agent_number="AG-CONS-AUTO",
        company_name="Automatic Attribution Buyer",
        contact_name="Buyer",
        email="consolidation-auto@example.com",
        hashed_password="not-used",
        tier="gold",
        status="active",
        currency="USD",
        credit_limit=Decimal("5000.00"),
        current_balance=Decimal("0.00"),
    )
    db_session.add(agent)
    await db_session.flush()

    order = B2BOrder(
        workspace_id=DEFAULT_WORKSPACE_ID,
        order_number="CONS-AUTO-B2B-1",
        agent_id=agent.id,
        status="confirmed",
        payment_status="unpaid",
        subtotal=Decimal("120.00"),
        shipping_cost=Decimal("0.00"),
        total=Decimal("120.00"),
        currency="USD",
        shipping_address={},
        items=[
            B2BOrderItem(
                workspace_id=DEFAULT_WORKSPACE_ID,
                product_id=product.id,
                product_name=product.name,
                sku=product.sku,
                quantity=10,
                unit_price=Decimal("12.00"),
                subtotal=Decimal("120.00"),
                currency="USD",
            )
        ],
    )
    db_session.add(order)
    await db_session.commit()

    order_attribution = await consolidation_service.ensure_attribution(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        entity_type="b2b_order",
        entity_id=order.id,
        actor="system:test",
    )
    assert order_attribution is not None
    assert order_attribution.brand_id == brand.id
    assert order_attribution.legal_entity_id == seller.id
    assert order_attribution.assignment_source == "auto"

    invoice = await b2b_finance_service.create_invoice_from_order(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        order_id=order.id,
        created_by="tester@example.com",
    )
    invoice_attribution = (
        await db_session.execute(
            select(CommerceAttribution).where(
                CommerceAttribution.workspace_id == DEFAULT_WORKSPACE_ID,
                CommerceAttribution.entity_type == "b2b_invoice",
                CommerceAttribution.entity_id == invoice.id,
            )
        )
    ).scalar_one()
    assert invoice_attribution.brand_id == brand.id
    assert invoice_attribution.legal_entity_id == seller.id
    assert invoice_attribution.assignment_source == "auto"


@pytest.mark.asyncio
async def test_order_ingestion_auto_assigns_consolidation_dimensions(
    db_session,
) -> None:
    seller, _buyer, brand = await _create_master_data(db_session)
    product = Product(
        workspace_id=DEFAULT_WORKSPACE_ID,
        sku="CONS-INGEST-1",
        name="Ingested Attribution Product",
        status="active",
        brand_id=brand.id,
    )
    db_session.add(product)
    await db_session.commit()

    response = await order_service.ingest_order(
        db_session,
        WebhookOrderPayload(
            id=987654,
            status="processing",
            currency="USD",
            total=Decimal("75.00"),
            subtotal=Decimal("75.00"),
            line_items=[
                {
                    "id": 1,
                    "sku": product.sku,
                    "name": product.name,
                    "quantity": 1,
                    "total": "75.00",
                }
            ],
        ),
        workspace_id=DEFAULT_WORKSPACE_ID,
        trace_id="consolidation-ingest-test",
    )

    attribution = (
        await db_session.execute(
            select(CommerceAttribution).where(
                CommerceAttribution.workspace_id == DEFAULT_WORKSPACE_ID,
                CommerceAttribution.entity_type == "b2c_order",
                CommerceAttribution.entity_id == UUID(response.order_id),
            )
        )
    ).scalar_one()
    assert attribution.brand_id == brand.id
    assert attribution.legal_entity_id == seller.id
    assert attribution.assignment_source == "auto"


@pytest.mark.asyncio
async def test_product_brand_governance_reconciles_historical_attribution(
    db_session,
) -> None:
    seller, _buyer, brand = await _create_master_data(db_session)
    product = Product(
        workspace_id=DEFAULT_WORKSPACE_ID,
        sku="CONS-GOV-1",
        name="Governance Product",
        status="active",
    )
    db_session.add(product)
    await db_session.flush()

    agent = B2BAgent(
        workspace_id=DEFAULT_WORKSPACE_ID,
        agent_number="AG-CONS-GOV",
        company_name="Governance Buyer",
        contact_name="Buyer",
        email="consolidation-governance@example.com",
        hashed_password="not-used",
        tier="gold",
        status="active",
        currency="USD",
        credit_limit=Decimal("5000.00"),
        current_balance=Decimal("0.00"),
    )
    db_session.add(agent)
    await db_session.flush()

    order = B2BOrder(
        workspace_id=DEFAULT_WORKSPACE_ID,
        order_number="CONS-GOV-B2B-1",
        agent_id=agent.id,
        status="confirmed",
        payment_status="unpaid",
        subtotal=Decimal("120.00"),
        shipping_cost=Decimal("0.00"),
        total=Decimal("120.00"),
        currency="USD",
        shipping_address={},
        items=[
            B2BOrderItem(
                workspace_id=DEFAULT_WORKSPACE_ID,
                product_id=product.id,
                product_name=product.name,
                sku=product.sku,
                quantity=10,
                unit_price=Decimal("12.00"),
                subtotal=Decimal("120.00"),
                currency="USD",
            )
        ],
    )
    db_session.add(order)
    await db_session.commit()

    product_gaps = await consolidation_service.list_product_brand_gaps(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        limit=20,
    )
    assert [row.product_id for row in product_gaps] == [str(product.id)]

    before = await consolidation_service.list_attribution_gaps(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        entity_type="b2b_order",
        limit=20,
    )
    assert len(before) == 1
    assert before[0].entity_id == str(order.id)
    assert before[0].reason == "missing_product_brand"
    assert before[0].suggested_brand_id is None

    skipped = await consolidation_service.reconcile_attribution_gaps(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        actor="operator@example.com",
        entity_type="b2b_order",
    )
    assert skipped.created == 0
    assert skipped.skipped == 1

    assigned = await consolidation_service.assign_product_brands(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        product_ids=[str(product.id)],
        brand_id=brand.id,
        actor="operator@example.com",
    )
    assert assigned.assigned == 1
    assert assigned.failed == 0
    await db_session.refresh(product)
    assert product.brand_id == brand.id

    ready = await consolidation_service.list_attribution_gaps(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        entity_type="b2b_order",
        limit=20,
    )
    assert len(ready) == 1
    assert ready[0].reason == "ready"
    assert ready[0].suggested_brand_id == str(brand.id)
    assert ready[0].suggested_legal_entity_id == str(seller.id)

    reconciled = await consolidation_service.reconcile_attribution_gaps(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        actor="operator@example.com",
        entity_type="b2b_order",
    )
    assert reconciled.created == 1
    assert reconciled.skipped == 0

    remaining = await consolidation_service.list_attribution_gaps(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        entity_type="b2b_order",
        limit=20,
    )
    assert remaining == []
    attribution = (
        await db_session.execute(
            select(CommerceAttribution).where(
                CommerceAttribution.workspace_id == DEFAULT_WORKSPACE_ID,
                CommerceAttribution.entity_type == "b2b_order",
                CommerceAttribution.entity_id == order.id,
            )
        )
    ).scalar_one()
    assert attribution.brand_id == brand.id
    assert attribution.legal_entity_id == seller.id
