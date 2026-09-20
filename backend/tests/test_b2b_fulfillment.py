"""P1 regression tests for B2B fulfillment across WMS inventory and TMS."""

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.b2b import B2BAgent, B2BOrder, B2BOrderItem
from app.models.b2b_fulfillment import B2BFulfillment
from app.models.event import EventLog
from app.models.product import Product
from app.models.supply_chain import InventorySnapshot, LogisticsEvent, ShipmentRecord
from app.services import b2b_fulfillment_service, b2b_portal_service

WORKSPACE = DEFAULT_WORKSPACE_ID


async def _create_order(
    db_session,
    *,
    quantity: int = 10,
    inventory_quantity: int = 50,
    order_status: str = "confirmed",
):
    agent = B2BAgent(
        workspace_id=WORKSPACE,
        agent_number=f"AG-FF-{uuid4().hex[:8]}",
        company_name="Fulfillment Buyer",
        contact_name="Buyer",
        email=f"ff-{uuid4().hex[:8]}@example.com",
        hashed_password="not-used",
        tier="bronze",
        status="active",
        currency="USD",
        credit_limit=Decimal("100000"),
    )
    product = Product(
        workspace_id=WORKSPACE,
        sku=f"SKU-FF-{uuid4().hex[:8]}",
        name="Fulfillment Product",
        status="active",
        source="manual",
    )
    db_session.add_all([agent, product])
    await db_session.flush()
    inventory = InventorySnapshot(
        workspace_id=WORKSPACE,
        product_id=product.id,
        location="us",
        quantity=inventory_quantity,
        reserved=0,
        available=inventory_quantity,
        in_transit=0,
    )
    order = B2BOrder(
        workspace_id=WORKSPACE,
        order_number=f"B2B-FF-{uuid4().hex[:8]}",
        agent_id=agent.id,
        business_model="B2B",
        status=order_status,
        payment_status="unpaid",
        subtotal=Decimal("100.00"),
        discount_amount=Decimal("0"),
        shipping_cost=Decimal("0"),
        total=Decimal("100.00"),
        currency="USD",
        shipping_address={
            "address": "100 Main Street",
            "city": "Los Angeles",
            "country": "US",
        },
    )
    db_session.add_all([inventory, order])
    await db_session.flush()
    db_session.add(
        B2BOrderItem(
            workspace_id=WORKSPACE,
            order_id=order.id,
            product_id=product.id,
            product_name=product.name,
            sku=product.sku,
            quantity=quantity,
            unit_price=Decimal("10.00"),
            subtotal=Decimal("100.00"),
            currency="USD",
        )
    )
    await db_session.commit()
    return order, product, inventory


async def _event_types(db_session) -> list[str]:
    return list(
        (
            await db_session.execute(
                select(EventLog.event_type).order_by(EventLog.id)
            )
        ).scalars().all()
    )


@pytest.mark.asyncio
async def test_reserve_is_atomic_and_idempotent(db_session) -> None:
    order, _product, inventory = await _create_order(db_session)
    fulfillment = await b2b_fulfillment_service.reserve_b2b_order_inventory(
        db_session,
        workspace_id=WORKSPACE,
        order_id=order.id,
        warehouse_location="us",
        actor="ops@example.com",
        reservation_key="reserve-1",
    )
    assert fulfillment.status == "reserved"
    assert order.status == "processing"
    assert inventory.reserved == 10
    assert inventory.available == 40
    assert fulfillment.items[0].reserved_quantity == 10

    duplicate = await b2b_fulfillment_service.reserve_b2b_order_inventory(
        db_session,
        workspace_id=WORKSPACE,
        order_id=order.id,
        warehouse_location="us",
        actor="ops@example.com",
        reservation_key="reserve-1",
    )
    assert duplicate.id == fulfillment.id
    assert inventory.reserved == 10
    assert inventory.available == 40
    count = (
        await db_session.execute(
            select(func.count(B2BFulfillment.id)).where(
                B2BFulfillment.workspace_id == WORKSPACE,
                B2BFulfillment.order_id == order.id,
            )
        )
    ).scalar_one()
    assert count == 1


@pytest.mark.asyncio
async def test_reservation_rejects_insufficient_inventory_without_mutation(
    db_session,
) -> None:
    order, _product, inventory = await _create_order(
        db_session,
        quantity=12,
        inventory_quantity=10,
    )
    with pytest.raises(
        b2b_fulfillment_service.B2BFulfillmentStateError,
        match="insufficient inventory",
    ):
        await b2b_fulfillment_service.reserve_b2b_order_inventory(
            db_session,
            workspace_id=WORKSPACE,
            order_id=order.id,
            warehouse_location="us",
            actor="ops@example.com",
        )
    assert inventory.reserved == 0
    assert inventory.available == 10
    assert order.status == "confirmed"


@pytest.mark.asyncio
async def test_release_restores_only_unshipped_inventory(db_session) -> None:
    order, _product, inventory = await _create_order(db_session)
    fulfillment = await b2b_fulfillment_service.reserve_b2b_order_inventory(
        db_session,
        workspace_id=WORKSPACE,
        order_id=order.id,
        warehouse_location="us",
        actor="ops@example.com",
    )
    released = await b2b_fulfillment_service.release_b2b_order_inventory(
        db_session,
        workspace_id=WORKSPACE,
        order_id=order.id,
        actor="ops@example.com",
        reason="customer changed warehouse",
    )
    assert released.id == fulfillment.id
    assert released.status == "released"
    assert order.status == "confirmed"
    assert inventory.reserved == 0
    assert inventory.available == 50
    assert released.items[0].released_quantity == 10
    assert released.items[0].reserved_quantity == 0


@pytest.mark.asyncio
async def test_ship_consumes_stock_creates_tms_and_delivery_syncs_order(
    db_session,
) -> None:
    order, _product, inventory = await _create_order(db_session)
    await b2b_fulfillment_service.reserve_b2b_order_inventory(
        db_session,
        workspace_id=WORKSPACE,
        order_id=order.id,
        warehouse_location="us",
        actor="ops@example.com",
    )
    shipped = await b2b_fulfillment_service.ship_b2b_order(
        db_session,
        workspace_id=WORKSPACE,
        order_id=order.id,
        carrier="DHL",
        tracking_number="DHL-B2B-001",
        actor="ops@example.com",
    )
    assert shipped.status == "shipped"
    assert shipped.shipment_id is not None
    assert order.status == "shipped"
    assert order.tracking_number == "DHL-B2B-001"
    assert inventory.quantity == 40
    assert inventory.reserved == 0
    assert inventory.available == 40
    assert shipped.items[0].shipped_quantity == 10

    shipment = await db_session.get(ShipmentRecord, shipped.shipment_id)
    assert shipment is not None
    assert shipment.b2b_order_id == order.id
    assert shipment.status == "in_transit"
    assert shipment.destination == "100 Main Street, Los Angeles, US"
    logistics_count = (
        await db_session.execute(
            select(func.count(LogisticsEvent.id)).where(
                LogisticsEvent.workspace_id == WORKSPACE,
                LogisticsEvent.shipment_id == shipment.id,
            )
        )
    ).scalar_one()
    assert logistics_count == 1

    delivered = await b2b_fulfillment_service.deliver_b2b_order(
        db_session,
        workspace_id=WORKSPACE,
        order_id=order.id,
        actor="ops@example.com",
    )
    assert delivered.status == "delivered"
    assert order.status == "delivered"
    await db_session.refresh(shipment)
    assert shipment.status == "delivered"
    events = await _event_types(db_session)
    assert "b2b_fulfillment.inventory_reserved" in events
    assert "b2b_fulfillment.shipped" in events
    assert "b2b_fulfillment.delivered" in events


@pytest.mark.asyncio
async def test_generic_status_update_cannot_bypass_fulfillment(db_session) -> None:
    order, _product, _inventory = await _create_order(db_session)
    with pytest.raises(
        b2b_portal_service.B2BOrderStateError,
        match="fulfillment workflow",
    ):
        await b2b_portal_service.update_b2b_order_status(
            db_session,
            workspace_id=WORKSPACE,
            order_id=order.id,
            new_status="processing",
            actor="ops@example.com",
        )


@pytest.mark.asyncio
async def test_generic_status_update_only_allows_confirm_and_cancel(db_session) -> None:
    order, _product, _inventory = await _create_order(
        db_session,
        order_status="pending",
    )
    confirmed = await b2b_portal_service.update_b2b_order_status(
        db_session,
        workspace_id=WORKSPACE,
        order_id=order.id,
        new_status="confirmed",
        actor="ops@example.com",
    )
    assert confirmed.status == "confirmed"

    order.status = "confirmed"
    cancelled = await b2b_portal_service.update_b2b_order_status(
        db_session,
        workspace_id=WORKSPACE,
        order_id=order.id,
        new_status="cancelled",
        actor="ops@example.com",
    )
    assert cancelled.status == "cancelled"


@pytest.mark.asyncio
async def test_delivery_accepts_naive_timestamp(db_session) -> None:
    order, _product, _inventory = await _create_order(db_session)
    await b2b_fulfillment_service.reserve_b2b_order_inventory(
        db_session,
        workspace_id=WORKSPACE,
        order_id=order.id,
        warehouse_location="us",
        actor="ops@example.com",
    )
    shipped = await b2b_fulfillment_service.ship_b2b_order(
        db_session,
        workspace_id=WORKSPACE,
        order_id=order.id,
        carrier="DHL",
        tracking_number="DHL-B2B-NAIVE",
        actor="ops@example.com",
    )
    delivered = await b2b_fulfillment_service.deliver_b2b_order(
        db_session,
        workspace_id=WORKSPACE,
        order_id=order.id,
        actor="ops@example.com",
        occurred_at=datetime(2026, 9, 13, 12, 0, 0),
    )
    shipment = await db_session.get(ShipmentRecord, shipped.shipment_id)
    assert delivered.status == "delivered"
    assert shipment is not None
    assert shipment.delivery_time_days is not None
    assert shipment.delivery_time_days >= 0


@pytest.mark.asyncio
async def test_fulfillment_is_workspace_scoped(db_session) -> None:
    order, _product, _inventory = await _create_order(db_session)
    fulfillment = await b2b_fulfillment_service.reserve_b2b_order_inventory(
        db_session,
        workspace_id=WORKSPACE,
        order_id=order.id,
        warehouse_location="us",
        actor="ops@example.com",
    )
    assert (
        await b2b_fulfillment_service.get_order_fulfillment(
            db_session,
            workspace_id=uuid4(),
            order_id=order.id,
        )
        is None
    )
    assert fulfillment.workspace_id == WORKSPACE
