"""Regression tests for B2C + B2B P0 compatibility hardening."""

import importlib.util
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.v1.endpoints.auth import get_current_user
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.main import app
from app.models.b2b import B2BAgent, B2BOrder
from app.models.event import EventLog
from app.models.order import Order
from app.schemas.user import UserResponse
from app.services import b2b_portal_service
from app.services.customer_account_service import get_or_create_b2b_account

WORKSPACE = DEFAULT_WORKSPACE_ID
OTHER_WORKSPACE = UUID("00000000-0000-0000-0000-000000000099")


def _load_p0_migration():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0035_b2c_b2b_p0.py"
    )
    spec = importlib.util.spec_from_file_location("p0_migration", migration_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_p0_migration_normalizes_legacy_country_labels() -> None:
    migration = _load_p0_migration()

    assert migration._country_code("United Kingdom") == "GB"
    assert migration._country_code("United States") == "US"
    assert migration._country_code("us") == "US"
    assert migration._country_code("Germany") == "DE"
    assert migration._country_code("Atlantis") == "Atlantis"
    assert migration._country_code("Unknown Country") is None
    assert migration._country_code(None) is None


async def _create_agent(
    db_session,
    *,
    workspace_id: UUID,
    agent_number: str,
    email: str,
) -> B2BAgent:
    account = await get_or_create_b2b_account(
        db_session,
        workspace_id=workspace_id,
        agent_number=agent_number,
        company_name=f"Company {agent_number}",
    )
    agent = B2BAgent(
        workspace_id=workspace_id,
        agent_number=agent_number,
        customer_account_id=account.id,
        company_name=f"Company {agent_number}",
        contact_name="Buyer",
        email=email,
        hashed_password="not-used-in-tests",
        tier="bronze",
        status="active",
        currency="USD",
    )
    db_session.add(agent)
    await db_session.commit()
    return agent


@pytest.mark.asyncio
async def test_b2b_agent_unique_keys_are_workspace_scoped(db_session) -> None:
    first = await _create_agent(
        db_session,
        workspace_id=WORKSPACE,
        agent_number="AG-001",
        email="buyer@example.com",
    )
    second = await _create_agent(
        db_session,
        workspace_id=OTHER_WORKSPACE,
        agent_number="AG-001",
        email="buyer@example.com",
    )

    assert first.workspace_id != second.workspace_id
    assert first.customer_account_id is not None
    assert second.customer_account_id is not None
    assert (
        await b2b_portal_service.get_agent_by_id(
            db_session,
            str(first.id),
            workspace_id=OTHER_WORKSPACE,
        )
        is None
    )
    assert (
        await b2b_portal_service.get_agent_by_id(
            db_session,
            str(second.id),
            workspace_id=OTHER_WORKSPACE,
        )
        == second
    )


@pytest.mark.asyncio
async def test_b2b_order_state_machine_and_audit_event(db_session) -> None:
    agent = await _create_agent(
        db_session,
        workspace_id=WORKSPACE,
        agent_number="AG-STATE",
        email="state@example.com",
    )
    order = B2BOrder(
        workspace_id=WORKSPACE,
        order_number="B2B-STATE-001",
        agent_id=agent.id,
        customer_account_id=agent.customer_account_id,
        business_model="B2B",
        status="pending",
        payment_status="unpaid",
        subtotal=Decimal("100.00"),
        total=Decimal("100.00"),
        currency="USD",
        shipping_address={},
    )
    db_session.add(order)
    await db_session.commit()

    with pytest.raises(b2b_portal_service.B2BOrderStateError):
        await b2b_portal_service.update_b2b_order_status(
            db_session,
            workspace_id=WORKSPACE,
            order_id=str(order.id),
            new_status="delivered",
            actor="ops@example.com",
        )

    confirmed = await b2b_portal_service.update_b2b_order_status(
        db_session,
        workspace_id=WORKSPACE,
        order_id=str(order.id),
        new_status="confirmed",
        actor="ops@example.com",
    )
    assert confirmed.status == "confirmed"

    cancelled = await b2b_portal_service.update_b2b_order_status(
        db_session,
        workspace_id=WORKSPACE,
        order_id=str(order.id),
        new_status="cancelled",
        actor="ops@example.com",
    )
    assert cancelled.status == "cancelled"

    with pytest.raises(b2b_portal_service.B2BOrderStateError):
        await b2b_portal_service.update_b2b_order_status(
            db_session,
            workspace_id=WORKSPACE,
            order_id=str(order.id),
            new_status="shipped",
            actor="ops@example.com",
        )

    events = (
        await db_session.execute(
            select(EventLog).where(EventLog.event_type == "b2b_order.status_changed")
        )
    ).scalars().all()
    assert [event.payload["new_status"] for event in events] == ["confirmed", "cancelled"]
    assert all(event.payload["actor"] == "ops@example.com" for event in events)


@pytest.mark.asyncio
async def test_external_order_unique_key_includes_source(db_session) -> None:
    db_session.add(
        Order(
            workspace_id=WORKSPACE,
            external_order_id="10001",
            source="woocommerce",
            business_model="B2C",
            status="processing",
            total=Decimal("10.00"),
        )
    )
    await db_session.commit()

    db_session.add(
        Order(
            workspace_id=WORKSPACE,
            external_order_id="10001",
            source="shopify",
            business_model="B2C",
            status="processing",
            total=Decimal("20.00"),
        )
    )
    await db_session.commit()

    db_session.add(
        Order(
            workspace_id=WORKSPACE,
            external_order_id="10001",
            source="woocommerce",
            business_model="B2C",
            status="processing",
            total=Decimal("30.00"),
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


def test_legacy_b2b_apis_return_gone(client) -> None:
    assert client.get("/api/v1/p3/b2b/status").status_code == 410
    assert client.get("/api/v1/m5-m6/b2b/status").status_code == 410
    assert client.post("/api/v1/p3/b2b/orders", json={}).status_code == 410
    assert client.post("/api/v1/m5-m6/b2b/orders", json={}).status_code == 410


@pytest.mark.asyncio
async def test_admin_b2b_workspace_is_bound_to_authenticated_user(api_client) -> None:
    admin = UserResponse(
        id="admin-1",
        username="admin",
        email="admin@example.com",
        full_name="Admin",
        role="admin",
        is_active=True,
        created_at=datetime.now(UTC),
    )
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        created = api_client.post(
            "/api/v1/admin/b2b/agents",
            json={
                "email": "admin-created@example.com",
                "password": "StrongPass123!",
                "company_name": "Admin Created Co",
                "contact_name": "Buyer",
                "tier": "silver",
                "status": "active",
                "currency": "USD",
            },
        )
        assert created.status_code == 201, created.text
        agent_id = created.json()["id"]

        fetched_with_spoofed_header = api_client.get(
            f"/api/v1/admin/b2b/agents/{agent_id}",
            headers={"X-Workspace-Id": str(OTHER_WORKSPACE)},
        )
        assert fetched_with_spoofed_header.status_code == 200, fetched_with_spoofed_header.text
        assert fetched_with_spoofed_header.json()["email"] == "admin-created@example.com"

        orders = api_client.get(
            "/api/v1/admin/b2b/orders",
            params={"agent_id": agent_id},
        )
        assert orders.status_code == 200, orders.text
        assert orders.json()["total"] == 0

        invalid_price = api_client.post(
            "/api/v1/admin/b2b/prices",
            json={
                "product_id": "00000000-0000-0000-0000-000000000010",
                "wholesale_price": "18.00",
            },
        )
        assert invalid_price.status_code == 422, invalid_price.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_refund_create_uses_authenticated_actor(
    db_session, api_client
) -> None:
    order = Order(
        workspace_id=WORKSPACE,
        external_order_id="refund-actor-1",
        source="woocommerce",
        business_model="B2C",
        status="completed",
        total=Decimal("100.00"),
    )
    db_session.add(order)
    await db_session.commit()

    fake_user = UserResponse(
        id="user-1",
        username="refund-operator",
        email="refund.operator@example.com",
        full_name="Refund Operator",
        role="operator",
        is_active=True,
        created_at=datetime.now(UTC),
    )
    app.dependency_overrides[get_current_user] = lambda: fake_user
    try:
        response = api_client.post(
            "/api/v1/refunds",
            headers={"X-Workspace-Id": str(OTHER_WORKSPACE)},
            json={
                "order_id": str(order.id),
                "amount": "20.00",
                "reason": "P0 actor audit",
                "idempotency_key": "p0-refund-actor",
            },
        )
        assert response.status_code == 201, response.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    event = (
        await db_session.execute(
            select(EventLog)
            .where(EventLog.event_type == "refund.requested")
            .order_by(EventLog.created_at.desc())
        )
    ).scalars().first()
    assert event is not None
    assert event.payload["requested_by"] == "refund.operator@example.com"
