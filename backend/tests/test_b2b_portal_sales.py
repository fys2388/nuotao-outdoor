"""P2 regression tests for the B2B customer portal sales closure."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from app.api.v1.endpoints.b2b_portal import get_current_b2b_agent
from app.core.security import create_access_token
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.main import app
from app.models.b2b import B2BAgent
from app.models.event import EventLog
from app.models.product import Product
from app.services import b2b_portal_service, b2b_pricing_service, b2b_sales_service
from app.services.customer_account_service import get_or_create_b2b_account

WORKSPACE = DEFAULT_WORKSPACE_ID
OTHER_WORKSPACE = UUID("00000000-0000-0000-0000-000000000099")


async def _create_agent(
    db_session,
    *,
    number: str,
    email: str,
    credit_limit: Decimal = Decimal("100000"),
) -> B2BAgent:
    account = await get_or_create_b2b_account(
        db_session,
        workspace_id=WORKSPACE,
        agent_number=number,
        company_name=f"Company {number}",
    )
    agent = B2BAgent(
        workspace_id=WORKSPACE,
        agent_number=number,
        customer_account_id=account.id,
        company_name=f"Company {number}",
        contact_name="Portal Buyer",
        email=email,
        hashed_password="not-used-in-tests",
        tier="bronze",
        status="active",
        currency="USD",
        credit_limit=credit_limit,
    )
    db_session.add(agent)
    await db_session.commit()
    return agent


async def _create_product(db_session, *, sku: str) -> Product:
    product = Product(
        workspace_id=WORKSPACE,
        sku=sku,
        name=f"Product {sku}",
        status="active",
        source="manual",
    )
    db_session.add(product)
    await db_session.commit()
    return product


async def _publish_price(db_session, product: Product) -> None:
    book = await b2b_pricing_service.create_price_book(
        db_session,
        workspace_id=WORKSPACE,
        code=f"PORTAL-{product.sku}",
        name=f"Portal {product.sku}",
        currency="USD",
        created_by="pricing@example.com",
        is_default=True,
    )
    version = await b2b_pricing_service.create_price_version(
        db_session,
        workspace_id=WORKSPACE,
        price_book_id=book.id,
        created_by="pricing@example.com",
        effective_from=date.today(),
    )
    await b2b_pricing_service.create_price_tier(
        db_session,
        workspace_id=WORKSPACE,
        price_version_id=version.id,
        product_id=product.id,
        tier="bronze",
        agent_id=None,
        min_quantity=1,
        max_quantity=None,
        unit_price=Decimal("16.00"),
        currency="USD",
    )
    await b2b_pricing_service.submit_price_version(
        db_session,
        workspace_id=WORKSPACE,
        price_version_id=version.id,
        actor="pricing@example.com",
    )
    await b2b_pricing_service.approve_price_version(
        db_session,
        workspace_id=WORKSPACE,
        price_version_id=version.id,
        actor="pricing-approver@example.com",
    )


async def _create_sent_quote(
    db_session,
    *,
    product: Product,
    agent: B2BAgent,
):
    rfq = await b2b_sales_service.create_rfq(
        db_session,
        workspace_id=WORKSPACE,
        agent_id=agent.id,
        items=[{"product_id": product.id, "quantity": 50}],
        created_by="sales@example.com",
        incoterm="FOB",
    )
    await b2b_sales_service.update_rfq_status(
        db_session,
        workspace_id=WORKSPACE,
        rfq_id=rfq.id,
        new_status="submitted",
        actor="sales@example.com",
    )
    quote = await b2b_sales_service.create_quote_from_rfq(
        db_session,
        workspace_id=WORKSPACE,
        rfq_id=rfq.id,
        created_by="sales@example.com",
        valid_until=date.today() + timedelta(days=14),
    )
    await b2b_sales_service.transition_quote(
        db_session,
        workspace_id=WORKSPACE,
        quote_id=quote.id,
        new_status="pending_approval",
        actor="sales@example.com",
    )
    return await b2b_sales_service.transition_quote(
        db_session,
        workspace_id=WORKSPACE,
        quote_id=quote.id,
        new_status="sent",
        actor="sales-approver@example.com",
    )


@pytest.mark.asyncio
async def test_portal_rfq_is_owned_and_submitted_by_authenticated_agent(db_session) -> None:
    product = await _create_product(db_session, sku="PORTAL-RFQ")
    agent_a = await _create_agent(
        db_session,
        number="AG-PORTAL-A",
        email="portal-a@example.com",
    )
    agent_b = await _create_agent(
        db_session,
        number="AG-PORTAL-B",
        email="portal-b@example.com",
    )

    rfq = await b2b_portal_service.create_agent_rfq(
        db_session,
        agent_a,
        items=[{"product_id": str(product.id), "quantity": 25}],
        incoterm="FOB",
    )

    assert rfq.status == "submitted"
    assert rfq.source == "portal"
    assert rfq.created_by == agent_a.email
    assert await b2b_portal_service.get_agent_rfq(db_session, agent_a, str(rfq.id)) is not None
    assert await b2b_portal_service.get_agent_rfq(db_session, agent_b, str(rfq.id)) is None

    agent_a_items, agent_a_total = await b2b_portal_service.list_agent_rfqs(
        db_session,
        agent_a,
    )
    agent_b_items, agent_b_total = await b2b_portal_service.list_agent_rfqs(
        db_session,
        agent_b,
    )
    assert agent_a_total == 1
    assert agent_a_items[0].id == rfq.id
    assert agent_b_total == 0
    assert agent_b_items == []


@pytest.mark.asyncio
async def test_portal_quote_visibility_acceptance_and_audit(db_session) -> None:
    product = await _create_product(db_session, sku="PORTAL-QUOTE")
    agent_a = await _create_agent(
        db_session,
        number="AG-QUOTE-A",
        email="quote-a@example.com",
    )
    agent_b = await _create_agent(
        db_session,
        number="AG-QUOTE-B",
        email="quote-b@example.com",
    )
    await _publish_price(db_session, product)
    quote = await _create_sent_quote(
        db_session,
        product=product,
        agent=agent_a,
    )

    assert await b2b_portal_service.get_agent_quote(
        db_session,
        agent_b,
        str(quote.id),
    ) is None
    agent_b_quotes, agent_b_total = await b2b_portal_service.list_agent_quotes(
        db_session,
        agent_b,
    )
    assert agent_b_total == 0
    assert agent_b_quotes == []

    accepted = await b2b_portal_service.accept_agent_quote(
        db_session,
        agent_a,
        str(quote.id),
    )
    assert accepted.status == "accepted"
    assert accepted.accepted_by == agent_a.email
    assert accepted.accepted_at is not None

    with pytest.raises(ValueError, match="awaiting a customer decision"):
        await b2b_portal_service.accept_agent_quote(
            db_session,
            agent_a,
            str(quote.id),
        )

    events = (
        await db_session.execute(
            select(EventLog)
            .where(
                EventLog.event_type == "b2b_quote.status_changed",
                EventLog.entity_id == str(quote.id),
            )
        )
    ).scalars().all()
    accepted_event = next(
        event for event in events if event.payload["new_status"] == "accepted"
    )
    assert accepted_event.payload["actor"] == agent_a.email


@pytest.mark.asyncio
async def test_portal_customer_signature_and_idempotent_order_conversion(
    db_session,
) -> None:
    product = await _create_product(db_session, sku="PORTAL-CONTRACT")
    agent_a = await _create_agent(
        db_session,
        number="AG-CONTRACT-A",
        email="contract-a@example.com",
    )
    agent_b = await _create_agent(
        db_session,
        number="AG-CONTRACT-B",
        email="contract-b@example.com",
    )
    await _publish_price(db_session, product)
    quote = await _create_sent_quote(
        db_session,
        product=product,
        agent=agent_a,
    )
    quote = await b2b_portal_service.accept_agent_quote(
        db_session,
        agent_a,
        str(quote.id),
    )

    contract = await b2b_sales_service.create_contract_from_quote(
        db_session,
        workspace_id=WORKSPACE,
        quote_id=quote.id,
        created_by="sales@example.com",
        effective_from=date.today(),
    )
    contract = await b2b_sales_service.transition_contract(
        db_session,
        workspace_id=WORKSPACE,
        contract_id=contract.id,
        new_status="pending_signature",
        actor="sales@example.com",
    )
    assert await b2b_portal_service.get_agent_contract(
        db_session,
        agent_b,
        str(contract.id),
    ) is None

    contract = await b2b_portal_service.sign_agent_contract(
        db_session,
        agent_a,
        str(contract.id),
        signed_by="Portal Buyer",
    )
    assert contract.customer_signed_by == "Portal Buyer"
    assert contract.status == "pending_signature"

    contract = await b2b_sales_service.sign_contract(
        db_session,
        workspace_id=WORKSPACE,
        contract_id=contract.id,
        party="company",
        signed_by="Company Signer",
    )
    assert contract.status == "active"

    first_order = await b2b_portal_service.convert_agent_contract_to_order(
        db_session,
        agent_a,
        str(contract.id),
    )
    second_order = await b2b_portal_service.convert_agent_contract_to_order(
        db_session,
        agent_a,
        str(contract.id),
    )

    assert first_order.id == second_order.id
    await db_session.refresh(agent_a)
    assert agent_a.current_balance == first_order.total

    converted_quote = await b2b_sales_service.get_quote(
        db_session,
        workspace_id=WORKSPACE,
        quote_id=quote.id,
    )
    assert converted_quote is not None
    assert converted_quote.status == "converted"


@pytest.mark.asyncio
async def test_portal_api_enforces_agent_scope_and_token_type(
    db_session,
    api_client,
) -> None:
    product = await _create_product(db_session, sku="PORTAL-API")
    agent_a = await _create_agent(
        db_session,
        number="AG-API-A",
        email="api-a@example.com",
    )
    agent_b = await _create_agent(
        db_session,
        number="AG-API-B",
        email="api-b@example.com",
    )
    await _publish_price(db_session, product)
    quote_a = await _create_sent_quote(
        db_session,
        product=product,
        agent=agent_a,
    )
    quote_b = await _create_sent_quote(
        db_session,
        product=product,
        agent=agent_b,
    )

    app.dependency_overrides[get_current_b2b_agent] = lambda: agent_a
    try:
        own_quotes = api_client.get("/api/v1/b2b-portal/quotes")
        assert own_quotes.status_code == 200, own_quotes.text
        assert [item["id"] for item in own_quotes.json()["items"]] == [str(quote_a.id)]

        other_quote = api_client.get(f"/api/v1/b2b-portal/quotes/{quote_b.id}")
        assert other_quote.status_code == 404

        other_quote_accept = api_client.post(
            f"/api/v1/b2b-portal/quotes/{quote_b.id}/accept"
        )
        assert other_quote_accept.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_b2b_agent, None)

    internal_token = create_access_token(
        "internal-admin",
        {"type": "access", "role": "admin"},
    )
    rejected = api_client.get(
        "/api/v1/b2b-portal/quotes",
        headers={"Authorization": f"Bearer {internal_token}"},
    )
    assert rejected.status_code == 401

    portal_token = b2b_portal_service.create_agent_token(agent_a)
    workspace_mismatch = api_client.get(
        "/api/v1/b2b-portal/quotes",
        headers={
            "Authorization": f"Bearer {portal_token}",
            "X-Workspace-Id": str(OTHER_WORKSPACE),
        },
    )
    assert workspace_mismatch.status_code == 403
