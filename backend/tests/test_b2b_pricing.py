"""P1 regression tests for versioned B2B pricing."""

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.b2b import B2BAgent
from app.models.product import Product
from app.services import b2b_credit_service, b2b_pricing_service, b2b_portal_service
from app.services.customer_account_service import get_or_create_b2b_account

WORKSPACE = DEFAULT_WORKSPACE_ID
OTHER_WORKSPACE = UUID("00000000-0000-0000-0000-000000000099")


async def _create_agent(
    db_session,
    *,
    workspace_id: UUID = WORKSPACE,
    number: str = "AG-PRICING",
    tier: str = "bronze",
    email: str = "pricing@example.com",
) -> B2BAgent:
    account = await get_or_create_b2b_account(
        db_session,
        workspace_id=workspace_id,
        agent_number=number,
        company_name=f"Company {number}",
    )
    agent = B2BAgent(
        workspace_id=workspace_id,
        agent_number=number,
        customer_account_id=account.id,
        company_name=f"Company {number}",
        contact_name="Pricing Buyer",
        email=email,
        hashed_password="not-used",
        tier=tier,
        status="active",
        currency="USD",
        credit_limit=Decimal("100000"),
    )
    db_session.add(agent)
    await db_session.commit()
    return agent


async def _create_product(
    db_session,
    *,
    workspace_id: UUID = WORKSPACE,
    sku: str = "SKU-PRICING",
) -> Product:
    product = Product(
        workspace_id=workspace_id,
        sku=sku,
        name=f"Product {sku}",
        status="active",
        source="manual",
    )
    db_session.add(product)
    await db_session.commit()
    return product


async def _published_quantity_tiers(db_session, product: Product):
    book = await b2b_pricing_service.create_price_book(
        db_session,
        workspace_id=WORKSPACE,
        code="DEFAULT",
        name="Default",
        currency="USD",
        created_by="author@example.com",
        is_default=True,
    )
    version = await b2b_pricing_service.create_price_version(
        db_session,
        workspace_id=WORKSPACE,
        price_book_id=book.id,
        created_by="author@example.com",
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
        max_quantity=500,
        unit_price=Decimal("18.00"),
        currency="USD",
    )
    await b2b_pricing_service.create_price_tier(
        db_session,
        workspace_id=WORKSPACE,
        price_version_id=version.id,
        product_id=product.id,
        tier="bronze",
        agent_id=None,
        min_quantity=500,
        max_quantity=None,
        unit_price=Decimal("15.00"),
        currency="USD",
    )
    await b2b_pricing_service.submit_price_version(
        db_session,
        workspace_id=WORKSPACE,
        price_version_id=version.id,
        actor="author@example.com",
    )
    return await b2b_pricing_service.approve_price_version(
        db_session,
        workspace_id=WORKSPACE,
        price_version_id=version.id,
        actor="approver@example.com",
    )


@pytest.mark.asyncio
async def test_quantity_tiers_use_left_closed_right_open_boundaries(db_session) -> None:
    product = await _create_product(db_session)
    agent = await _create_agent(db_session)
    await _published_quantity_tiers(db_session, product)

    first = await b2b_pricing_service.resolve_b2b_price(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product.id,
        agent=agent,
        quantity=1,
    )
    boundary = await b2b_pricing_service.resolve_b2b_price(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product.id,
        agent=agent,
        quantity=100,
    )
    upper_boundary = await b2b_pricing_service.resolve_b2b_price(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product.id,
        agent=agent,
        quantity=499,
    )
    top = await b2b_pricing_service.resolve_b2b_price(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product.id,
        agent=agent,
        quantity=500,
    )

    assert first.unit_price == Decimal("22.00")
    assert boundary.unit_price == Decimal("18.00")
    assert upper_boundary.unit_price == Decimal("18.00")
    assert top.unit_price == Decimal("15.00")


@pytest.mark.asyncio
async def test_agent_specific_price_has_priority(db_session) -> None:
    product = await _create_product(db_session)
    agent = await _create_agent(db_session)
    version = await _published_quantity_tiers(db_session, product)
    await b2b_pricing_service.create_price_version(
        db_session,
        workspace_id=WORKSPACE,
        price_book_id=version.price_book_id,
        created_by="author@example.com",
        effective_from=date.today(),
        source_version_id=version.id,
    )

    specific_book = await b2b_pricing_service.get_price_book(
        db_session,
        workspace_id=WORKSPACE,
        price_book_id=version.price_book_id,
    )
    assert specific_book is not None
    draft = next(item for item in specific_book.versions if item.status == "draft")
    await b2b_pricing_service.create_price_tier(
        db_session,
        workspace_id=WORKSPACE,
        price_version_id=draft.id,
        product_id=product.id,
        tier=None,
        agent_id=agent.id,
        min_quantity=1,
        max_quantity=None,
        unit_price=Decimal("10.00"),
        currency="USD",
    )
    # The active version continues to win until the customer-specific draft is approved.
    active = await b2b_pricing_service.resolve_b2b_price(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product.id,
        agent=agent,
        quantity=100,
    )
    assert active.source == "TIER"
    assert active.unit_price == Decimal("18.00")

    await b2b_pricing_service.submit_price_version(
        db_session,
        workspace_id=WORKSPACE,
        price_version_id=draft.id,
        actor="author@example.com",
    )
    await b2b_pricing_service.approve_price_version(
        db_session,
        workspace_id=WORKSPACE,
        price_version_id=draft.id,
        actor="approver@example.com",
    )
    specific = await b2b_pricing_service.resolve_b2b_price(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product.id,
        agent=agent,
        quantity=1,
    )
    assert specific.source == "AGENT"
    assert specific.unit_price == Decimal("10.00")


@pytest.mark.asyncio
async def test_overlapping_quantity_ranges_are_rejected(db_session) -> None:
    product = await _create_product(db_session, sku="SKU-OVERLAP")
    book = await b2b_pricing_service.create_price_book(
        db_session,
        workspace_id=WORKSPACE,
        code="OVERLAP",
        name="Overlap",
        currency="USD",
        created_by="author@example.com",
        is_default=True,
    )
    version = await b2b_pricing_service.create_price_version(
        db_session,
        workspace_id=WORKSPACE,
        price_book_id=book.id,
        created_by="author@example.com",
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
        unit_price=Decimal("20.00"),
        currency="USD",
    )
    with pytest.raises(b2b_pricing_service.PricingConflictError):
        await b2b_pricing_service.create_price_tier(
            db_session,
            workspace_id=WORKSPACE,
            price_version_id=version.id,
            product_id=product.id,
            tier="bronze",
            agent_id=None,
            min_quantity=99,
            max_quantity=200,
            unit_price=Decimal("18.00"),
            currency="USD",
        )


@pytest.mark.asyncio
async def test_active_version_is_immutable(db_session) -> None:
    product = await _create_product(db_session, sku="SKU-IMMUTABLE")
    version = await _published_quantity_tiers(db_session, product)

    with pytest.raises(b2b_pricing_service.PricingStateError):
        await b2b_pricing_service.create_price_tier(
            db_session,
            workspace_id=WORKSPACE,
            price_version_id=version.id,
            product_id=product.id,
            tier="silver",
            agent_id=None,
            min_quantity=1,
            max_quantity=None,
            unit_price=Decimal("9.00"),
            currency="USD",
        )


@pytest.mark.asyncio
async def test_cross_workspace_price_is_not_resolved(db_session) -> None:
    product = await _create_product(db_session, sku="SKU-TENANT")
    other_agent = await _create_agent(
        db_session,
        workspace_id=OTHER_WORKSPACE,
        number="AG-OTHER",
        email="other@example.com",
    )
    await _published_quantity_tiers(db_session, product)

    with pytest.raises(b2b_pricing_service.PricingError):
        await b2b_pricing_service.resolve_b2b_price(
            db_session,
            workspace_id=OTHER_WORKSPACE,
            product_id=product.id,
            agent=other_agent,
            quantity=100,
        )


@pytest.mark.asyncio
async def test_b2b_order_snapshots_published_price_version(db_session) -> None:
    product = await _create_product(db_session, sku="SKU-ORDER-SNAPSHOT")
    agent = await _create_agent(db_session)
    version = await _published_quantity_tiers(db_session, product)

    order = await b2b_portal_service.create_b2b_order(
        db_session,
        agent,
        [{"product_id": str(product.id), "quantity": 120}],
    )

    item = order.items[0]
    assert item.unit_price == Decimal("18.00")
    assert item.currency == "USD"
    assert item.price_book_version_id == version.id
    assert item.price_tier_id is not None
    assert item.price_source == "TIER"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("credit_status", "expected_message"),
    [
        ("hold", "credit status is hold"),
        ("frozen", "credit status is frozen"),
    ],
)
async def test_portal_order_blocks_held_or_frozen_customer(
    db_session,
    credit_status: str,
    expected_message: str,
) -> None:
    product = await _create_product(
        db_session,
        sku=f"SKU-PORTAL-{credit_status}",
    )
    agent = await _create_agent(
        db_session,
        number=f"AG-PORTAL-{credit_status}",
    )
    await _published_quantity_tiers(db_session, product)
    await b2b_credit_service.manual_update_status(
        db_session,
        workspace_id=WORKSPACE,
        agent_id=agent.id,
        new_status=credit_status,
        actor="admin@example.com",
        reason=f"Portal {credit_status} regression",
    )

    with pytest.raises(
        b2b_credit_service.B2BCreditStateError,
        match=expected_message,
    ):
        await b2b_portal_service.create_b2b_order(
            db_session,
            agent,
            [{"product_id": str(product.id), "quantity": 120}],
        )


@pytest.mark.asyncio
async def test_portal_order_enforces_credit_limit(db_session) -> None:
    product = await _create_product(db_session, sku="SKU-PORTAL-LIMIT")
    agent = await _create_agent(db_session, number="AG-PORTAL-LIMIT")
    agent.credit_limit = Decimal("10.00")
    await db_session.commit()
    await _published_quantity_tiers(db_session, product)

    with pytest.raises(
        b2b_credit_service.B2BCreditStateError,
        match="credit limit",
    ):
        await b2b_portal_service.create_b2b_order(
            db_session,
            agent,
            [{"product_id": str(product.id), "quantity": 120}],
        )
