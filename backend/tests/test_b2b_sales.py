"""P1 regression tests for the B2B RFQ to order sales chain."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.b2b import B2BAgent
from app.models.product import Product
from app.services import b2b_credit_service, b2b_pricing_service, b2b_sales_service
from app.services.customer_account_service import get_or_create_b2b_account

WORKSPACE = DEFAULT_WORKSPACE_ID


async def _create_agent(
    db_session,
    *,
    number: str = "AG-SALES",
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
        contact_name="Sales Buyer",
        email=f"{number.lower()}@example.com",
        hashed_password="not-used",
        tier="bronze",
        status="active",
        currency="USD",
        credit_limit=credit_limit,
    )
    db_session.add(agent)
    await db_session.commit()
    return agent


async def _create_product(db_session, *, sku: str = "SKU-SALES") -> Product:
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
        code=f"BOOK-{product.sku}",
        name=f"Book {product.sku}",
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
        max_quantity=100,
        unit_price=Decimal("22.00"),
        currency="USD",
    )
    await b2b_pricing_service.create_price_tier(
        db_session,
        workspace_id=WORKSPACE,
        price_version_id=version.id,
        product_id=product.id,
        tier="bronze",
        agent_id=None,
        min_quantity=100,
        max_quantity=None,
        unit_price=Decimal("18.00"),
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


async def _create_quote(
    db_session,
    *,
    product: Product,
    agent: B2BAgent,
    valid_until: date | None = None,
):
    rfq = await b2b_sales_service.create_rfq(
        db_session,
        workspace_id=WORKSPACE,
        agent_id=agent.id,
        items=[{"product_id": product.id, "quantity": 120}],
        created_by="author@example.com",
        incoterm="FOB",
    )
    await b2b_sales_service.update_rfq_status(
        db_session,
        workspace_id=WORKSPACE,
        rfq_id=rfq.id,
        new_status="submitted",
        actor="author@example.com",
    )
    return await b2b_sales_service.create_quote_from_rfq(
        db_session,
        workspace_id=WORKSPACE,
        rfq_id=rfq.id,
        created_by="author@example.com",
        valid_until=valid_until or (date.today() + timedelta(days=14)),
        payment_terms_days=30,
    )


async def _activate_contract(db_session, quote):
    contract = await b2b_sales_service.create_contract_from_quote(
        db_session,
        workspace_id=WORKSPACE,
        quote_id=quote.id,
        created_by="author@example.com",
        effective_from=date.today(),
    )
    contract = await b2b_sales_service.transition_contract(
        db_session,
        workspace_id=WORKSPACE,
        contract_id=contract.id,
        new_status="pending_signature",
        actor="author@example.com",
    )
    return contract


@pytest.mark.asyncio
async def test_full_sales_chain_traces_quote_contract_and_order(db_session) -> None:
    product = await _create_product(db_session)
    agent = await _create_agent(db_session)
    await _publish_price(db_session, product)
    quote = await _create_quote(db_session, product=product, agent=agent)

    assert quote.status == "draft"
    assert quote.rfq is not None
    assert quote.rfq.status == "quoted"
    assert quote.items[0].unit_price == Decimal("18.00")
    assert quote.items[0].quantity == 120

    await b2b_sales_service.transition_quote(
        db_session,
        workspace_id=WORKSPACE,
        quote_id=quote.id,
        new_status="pending_approval",
        actor="author@example.com",
    )
    quote = await b2b_sales_service.transition_quote(
        db_session,
        workspace_id=WORKSPACE,
        quote_id=quote.id,
        new_status="sent",
        actor="approver@example.com",
    )
    quote = await b2b_sales_service.transition_quote(
        db_session,
        workspace_id=WORKSPACE,
        quote_id=quote.id,
        new_status="accepted",
        actor="buyer@example.com",
    )
    contract = await _activate_contract(db_session, quote)
    contract = await b2b_sales_service.sign_contract(
        db_session,
        workspace_id=WORKSPACE,
        contract_id=contract.id,
        party="customer",
        signed_by="Buyer Signer",
    )
    assert contract.status == "pending_signature"
    contract = await b2b_sales_service.sign_contract(
        db_session,
        workspace_id=WORKSPACE,
        contract_id=contract.id,
        party="company",
        signed_by="Company Signer",
    )
    assert contract.status == "active"
    assert contract.activated_at is not None

    order = await b2b_sales_service.convert_quote_to_order(
        db_session,
        workspace_id=WORKSPACE,
        quote_id=quote.id,
        actor="operator@example.com",
    )
    assert order.quote_id == quote.id
    assert order.contract_id == contract.id
    assert order.items[0].quote_item_id == quote.items[0].id
    assert order.items[0].price_book_version_id == quote.price_book_version_id

    duplicate = await b2b_sales_service.convert_quote_to_order(
        db_session,
        workspace_id=WORKSPACE,
        quote_id=quote.id,
        actor="operator@example.com",
    )
    assert duplicate.id == order.id

    converted = await b2b_sales_service.get_quote(
        db_session,
        workspace_id=WORKSPACE,
        quote_id=quote.id,
    )
    assert converted is not None
    assert converted.status == "converted"
    assert converted.rfq is not None
    assert converted.rfq.status == "won"


@pytest.mark.asyncio
async def test_quote_creator_cannot_approve_own_quote(db_session) -> None:
    product = await _create_product(db_session, sku="SKU-SELF-APPROVE")
    agent = await _create_agent(db_session, number="AG-SELF")
    await _publish_price(db_session, product)
    quote = await _create_quote(db_session, product=product, agent=agent)
    await b2b_sales_service.transition_quote(
        db_session,
        workspace_id=WORKSPACE,
        quote_id=quote.id,
        new_status="pending_approval",
        actor="author@example.com",
    )

    with pytest.raises(b2b_sales_service.B2BSalesStateError, match="creator cannot approve"):
        await b2b_sales_service.transition_quote(
            db_session,
            workspace_id=WORKSPACE,
            quote_id=quote.id,
            new_status="sent",
            actor="author@example.com",
        )


@pytest.mark.asyncio
async def test_expired_quote_cannot_be_sent_or_accepted(db_session) -> None:
    product = await _create_product(db_session, sku="SKU-EXPIRED")
    agent = await _create_agent(db_session, number="AG-EXPIRED")
    await _publish_price(db_session, product)
    quote = await _create_quote(db_session, product=product, agent=agent)
    quote.valid_until = date.today() - timedelta(days=1)
    await db_session.commit()
    await b2b_sales_service.transition_quote(
        db_session,
        workspace_id=WORKSPACE,
        quote_id=quote.id,
        new_status="pending_approval",
        actor="author@example.com",
    )

    with pytest.raises(b2b_sales_service.B2BSalesStateError, match="expired quote"):
        await b2b_sales_service.transition_quote(
            db_session,
            workspace_id=WORKSPACE,
            quote_id=quote.id,
            new_status="sent",
            actor="approver@example.com",
        )


@pytest.mark.asyncio
async def test_contract_requires_accepted_quote(db_session) -> None:
    product = await _create_product(db_session, sku="SKU-CONTRACT-STATUS")
    agent = await _create_agent(db_session, number="AG-CONTRACT")
    await _publish_price(db_session, product)
    quote = await _create_quote(db_session, product=product, agent=agent)

    with pytest.raises(b2b_sales_service.B2BSalesStateError, match="accepted quote"):
        await b2b_sales_service.create_contract_from_quote(
            db_session,
            workspace_id=WORKSPACE,
            quote_id=quote.id,
            created_by="author@example.com",
            effective_from=date.today(),
        )


@pytest.mark.asyncio
async def test_contract_requires_both_signatures_and_rejects_duplicate(db_session) -> None:
    product = await _create_product(db_session, sku="SKU-SIGN")
    agent = await _create_agent(db_session, number="AG-SIGN")
    await _publish_price(db_session, product)
    quote = await _create_quote(db_session, product=product, agent=agent)
    await b2b_sales_service.transition_quote(
        db_session,
        workspace_id=WORKSPACE,
        quote_id=quote.id,
        new_status="pending_approval",
        actor="author@example.com",
    )
    quote = await b2b_sales_service.transition_quote(
        db_session,
        workspace_id=WORKSPACE,
        quote_id=quote.id,
        new_status="sent",
        actor="approver@example.com",
    )
    quote = await b2b_sales_service.transition_quote(
        db_session,
        workspace_id=WORKSPACE,
        quote_id=quote.id,
        new_status="accepted",
        actor="buyer@example.com",
    )
    contract = await _activate_contract(db_session, quote)

    with pytest.raises(b2b_sales_service.B2BSalesStateError, match="invalid contract"):
        await b2b_sales_service.transition_contract(
            db_session,
            workspace_id=WORKSPACE,
            contract_id=contract.id,
            new_status="active",
            actor="author@example.com",
        )

    await b2b_sales_service.sign_contract(
        db_session,
        workspace_id=WORKSPACE,
        contract_id=contract.id,
        party="customer",
        signed_by="Buyer Signer",
    )
    with pytest.raises(b2b_sales_service.B2BSalesStateError, match="already recorded"):
        await b2b_sales_service.sign_contract(
            db_session,
            workspace_id=WORKSPACE,
            contract_id=contract.id,
            party="customer",
            signed_by="Buyer Signer",
        )


@pytest.mark.asyncio
async def test_order_conversion_requires_active_contract(db_session) -> None:
    product = await _create_product(db_session, sku="SKU-ACTIVE-CONTRACT")
    agent = await _create_agent(db_session, number="AG-ACTIVE")
    await _publish_price(db_session, product)
    quote = await _create_quote(db_session, product=product, agent=agent)
    await b2b_sales_service.transition_quote(
        db_session,
        workspace_id=WORKSPACE,
        quote_id=quote.id,
        new_status="pending_approval",
        actor="author@example.com",
    )
    quote = await b2b_sales_service.transition_quote(
        db_session,
        workspace_id=WORKSPACE,
        quote_id=quote.id,
        new_status="sent",
        actor="approver@example.com",
    )
    quote = await b2b_sales_service.transition_quote(
        db_session,
        workspace_id=WORKSPACE,
        quote_id=quote.id,
        new_status="accepted",
        actor="buyer@example.com",
    )

    with pytest.raises(b2b_sales_service.B2BSalesStateError, match="active contract"):
        await b2b_sales_service.convert_quote_to_order(
            db_session,
            workspace_id=WORKSPACE,
            quote_id=quote.id,
            actor="operator@example.com",
        )


@pytest.mark.asyncio
async def test_order_conversion_enforces_credit_limit(db_session) -> None:
    product = await _create_product(db_session, sku="SKU-CREDIT")
    agent = await _create_agent(
        db_session,
        number="AG-CREDIT",
        credit_limit=Decimal("100"),
    )
    await _publish_price(db_session, product)
    quote = await _create_quote(db_session, product=product, agent=agent)
    await b2b_sales_service.transition_quote(
        db_session,
        workspace_id=WORKSPACE,
        quote_id=quote.id,
        new_status="pending_approval",
        actor="author@example.com",
    )
    quote = await b2b_sales_service.transition_quote(
        db_session,
        workspace_id=WORKSPACE,
        quote_id=quote.id,
        new_status="sent",
        actor="approver@example.com",
    )
    quote = await b2b_sales_service.transition_quote(
        db_session,
        workspace_id=WORKSPACE,
        quote_id=quote.id,
        new_status="accepted",
        actor="buyer@example.com",
    )
    contract = await _activate_contract(db_session, quote)
    await b2b_sales_service.sign_contract(
        db_session,
        workspace_id=WORKSPACE,
        contract_id=contract.id,
        party="customer",
        signed_by="Buyer Signer",
    )
    await b2b_sales_service.sign_contract(
        db_session,
        workspace_id=WORKSPACE,
        contract_id=contract.id,
        party="company",
        signed_by="Company Signer",
    )

    with pytest.raises(
        b2b_credit_service.B2BCreditStateError,
        match="credit limit",
    ):
        await b2b_sales_service.convert_quote_to_order(
            db_session,
            workspace_id=WORKSPACE,
            quote_id=quote.id,
            actor="operator@example.com",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("credit_status", "reason"),
    [
        ("hold", "Overdue balance requires review"),
        ("frozen", "Account frozen by risk policy"),
    ],
)
async def test_order_conversion_blocks_hold_or_frozen_customer(
    db_session,
    credit_status: str,
    reason: str,
) -> None:
    product = await _create_product(db_session, sku=f"SKU-STATUS-{credit_status}")
    agent = await _create_agent(db_session, number=f"AG-STATUS-{credit_status}")
    await _publish_price(db_session, product)
    quote = await _create_quote(db_session, product=product, agent=agent)
    await b2b_sales_service.transition_quote(
        db_session,
        workspace_id=WORKSPACE,
        quote_id=quote.id,
        new_status="pending_approval",
        actor="author@example.com",
    )
    quote = await b2b_sales_service.transition_quote(
        db_session,
        workspace_id=WORKSPACE,
        quote_id=quote.id,
        new_status="sent",
        actor="approver@example.com",
    )
    quote = await b2b_sales_service.transition_quote(
        db_session,
        workspace_id=WORKSPACE,
        quote_id=quote.id,
        new_status="accepted",
        actor="buyer@example.com",
    )
    contract = await _activate_contract(db_session, quote)
    await b2b_sales_service.sign_contract(
        db_session,
        workspace_id=WORKSPACE,
        contract_id=contract.id,
        party="customer",
        signed_by="Buyer Signer",
    )
    await b2b_sales_service.sign_contract(
        db_session,
        workspace_id=WORKSPACE,
        contract_id=contract.id,
        party="company",
        signed_by="Company Signer",
    )
    await b2b_credit_service.manual_update_status(
        db_session,
        workspace_id=WORKSPACE,
        agent_id=agent.id,
        new_status=credit_status,
        actor="admin@example.com",
        reason=reason,
    )

    with pytest.raises(
        b2b_credit_service.B2BCreditStateError,
        match=f"credit status is {credit_status}",
    ):
        await b2b_sales_service.convert_quote_to_order(
            db_session,
            workspace_id=WORKSPACE,
            quote_id=quote.id,
            actor="operator@example.com",
        )
