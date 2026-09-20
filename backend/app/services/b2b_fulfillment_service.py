"""Atomic B2B order fulfillment across WMS inventory and TMS shipments."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.b2b import B2BOrder
from app.models.b2b_fulfillment import B2BFulfillment, B2BFulfillmentItem
from app.models.supply_chain import InventorySnapshot, LogisticsEvent, ShipmentRecord
from app.services import event_service


class B2BFulfillmentError(ValueError):
    """Base class for B2B fulfillment domain errors."""


class B2BFulfillmentNotFoundError(B2BFulfillmentError):
    """Raised when the order or fulfillment cannot be found."""


class B2BFulfillmentStateError(B2BFulfillmentError):
    """Raised when an operation is invalid for the current state."""


def _uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _number() -> str:
    now = _now()
    return f"FF-{now.strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"


def _destination(order: B2BOrder) -> str | None:
    address = order.shipping_address or {}
    parts = [
        address.get("address"),
        address.get("city"),
        address.get("country"),
    ]
    value = ", ".join(str(part).strip() for part in parts if part)
    return value or None


async def _load_order(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    order_id: str | UUID,
) -> B2BOrder:
    order = (
        await db.execute(
            select(B2BOrder)
            .where(
                B2BOrder.workspace_id == workspace_id,
                B2BOrder.id == _uuid(order_id),
            )
            .options(selectinload(B2BOrder.items))
        )
    ).scalar_one_or_none()
    if order is None:
        raise B2BFulfillmentNotFoundError("B2B order not found")
    if not order.items:
        raise B2BFulfillmentStateError("B2B order has no line items")
    return order


async def get_order_fulfillment(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    order_id: str | UUID,
) -> B2BFulfillment | None:
    """Return the single fulfillment record for an order, if present."""
    return (
        await db.execute(
            select(B2BFulfillment)
            .where(
                B2BFulfillment.workspace_id == workspace_id,
                B2BFulfillment.order_id == _uuid(order_id),
            )
            .options(selectinload(B2BFulfillment.items))
        )
    ).scalar_one_or_none()


async def _load_inventory_for_update(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    warehouse_location: str,
) -> InventorySnapshot:
    snapshot = (
        await db.execute(
            select(InventorySnapshot)
            .where(
                InventorySnapshot.workspace_id == workspace_id,
                InventorySnapshot.product_id == product_id,
                InventorySnapshot.location == warehouse_location,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if snapshot is None:
        raise B2BFulfillmentStateError(
            f"inventory not found for product {product_id} at {warehouse_location}"
        )
    return snapshot


def _sync_available(snapshot: InventorySnapshot) -> None:
    snapshot.available = max(snapshot.quantity - snapshot.reserved, 0)


async def reserve_b2b_order_inventory(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    order_id: str | UUID,
    warehouse_location: str,
    actor: str,
    reservation_key: str | None = None,
    trace_id: str | None = None,
) -> B2BFulfillment:
    """Reserve every order line from one warehouse and move order to processing.

    The operation is idempotent per order. Inventory rows are locked before
    validating availability so concurrent reservations cannot oversell stock.
    """
    if warehouse_location not in {"cn", "us", "eu"}:
        raise B2BFulfillmentStateError("invalid warehouse location")
    order = await _load_order(db, workspace_id=workspace_id, order_id=order_id)
    existing = await get_order_fulfillment(
        db,
        workspace_id=workspace_id,
        order_id=order.id,
    )
    if existing is not None:
        if existing.status == "released":
            raise B2BFulfillmentStateError(
                "released fulfillment cannot be reused; cancel or recreate the order"
            )
        return existing
    if order.status not in {"confirmed", "processing"}:
        raise B2BFulfillmentStateError(
            f"order must be confirmed before inventory reservation, got '{order.status}'"
        )

    required: dict[UUID, int] = {}
    for item in order.items:
        required[item.product_id] = required.get(item.product_id, 0) + item.quantity

    snapshots: dict[UUID, InventorySnapshot] = {}
    for product_id, quantity in required.items():
        snapshot = await _load_inventory_for_update(
            db,
            workspace_id=workspace_id,
            product_id=product_id,
            warehouse_location=warehouse_location,
        )
        if snapshot.available < quantity:
            raise B2BFulfillmentStateError(
                f"insufficient inventory for product {product_id} at "
                f"{warehouse_location}: available {snapshot.available}, required {quantity}"
            )
        snapshots[product_id] = snapshot

    now = _now()
    fulfillment = B2BFulfillment(
        workspace_id=workspace_id,
        fulfillment_number=_number(),
        order_id=order.id,
        status="reserved",
        warehouse_location=warehouse_location,
        reservation_key=reservation_key,
        reserved_at=now,
        created_by=actor,
        trace_id=trace_id,
    )
    db.add(fulfillment)
    await db.flush()

    for item in order.items:
        snapshot = snapshots[item.product_id]
        snapshot.reserved += item.quantity
        _sync_available(snapshot)
        db.add(
            B2BFulfillmentItem(
                workspace_id=workspace_id,
                fulfillment_id=fulfillment.id,
                order_item_id=item.id,
                product_id=item.product_id,
                inventory_snapshot_id=snapshot.id,
                quantity=item.quantity,
                reserved_quantity=item.quantity,
                shipped_quantity=0,
                released_quantity=0,
                created_at=now,
            )
        )

    previous_status = order.status
    order.status = "processing"
    await db.flush()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_fulfillment.inventory_reserved",
        entity_type="b2b_fulfillment",
        entity_id=str(fulfillment.id),
        payload={
            "fulfillment_number": fulfillment.fulfillment_number,
            "order_id": str(order.id),
            "order_number": order.order_number,
            "warehouse_location": warehouse_location,
            "line_count": len(order.items),
            "actor": actor,
        },
        trace_id=trace_id,
    )
    if previous_status != order.status:
        await event_service.create_event(
            db,
            workspace_id=workspace_id,
            event_type="b2b_order.status_changed",
            entity_type="b2b_order",
            entity_id=str(order.id),
            payload={
                "order_number": order.order_number,
                "previous_status": previous_status,
                "new_status": order.status,
                "actor": actor,
                "source": "b2b_fulfillment",
            },
            trace_id=trace_id,
        )
    return await get_order_fulfillment(
        db,
        workspace_id=workspace_id,
        order_id=order.id,
    )  # type: ignore[return-value]


async def release_b2b_order_inventory(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    order_id: str | UUID,
    actor: str,
    reason: str,
    trace_id: str | None = None,
) -> B2BFulfillment:
    """Release all unshipped reserved quantities and restore availability."""
    order = await _load_order(db, workspace_id=workspace_id, order_id=order_id)
    fulfillment = await get_order_fulfillment(
        db,
        workspace_id=workspace_id,
        order_id=order.id,
    )
    if fulfillment is None:
        raise B2BFulfillmentNotFoundError("B2B order fulfillment not found")
    if fulfillment.status == "released":
        return fulfillment
    if fulfillment.status != "reserved":
        raise B2BFulfillmentStateError(
            f"fulfillment in '{fulfillment.status}' state cannot be released"
        )

    snapshots: dict[UUID, InventorySnapshot] = {}
    for item in fulfillment.items:
        quantity = item.quantity - item.shipped_quantity - item.released_quantity
        if quantity <= 0:
            continue
        snapshot = snapshots.get(item.inventory_snapshot_id)
        if snapshot is None:
            snapshot = (
                await db.execute(
                    select(InventorySnapshot)
                    .where(
                        InventorySnapshot.workspace_id == workspace_id,
                        InventorySnapshot.id == item.inventory_snapshot_id,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if snapshot is None:
                raise B2BFulfillmentStateError("reserved inventory row not found")
            snapshots[item.inventory_snapshot_id] = snapshot
        if snapshot.reserved < quantity:
            raise B2BFulfillmentStateError("inventory reservation is inconsistent")
        snapshot.reserved -= quantity
        _sync_available(snapshot)
        item.reserved_quantity = 0
        item.released_quantity += quantity

    now = _now()
    fulfillment.status = "released"
    fulfillment.released_at = now
    fulfillment.release_reason = reason
    if order.status == "processing":
        previous_status = order.status
        order.status = "confirmed"
    else:
        previous_status = order.status
    await db.flush()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_fulfillment.inventory_released",
        entity_type="b2b_fulfillment",
        entity_id=str(fulfillment.id),
        payload={
            "fulfillment_number": fulfillment.fulfillment_number,
            "order_id": str(order.id),
            "order_number": order.order_number,
            "warehouse_location": fulfillment.warehouse_location,
            "reason": reason,
            "actor": actor,
        },
        trace_id=trace_id,
    )
    if previous_status != order.status:
        await event_service.create_event(
            db,
            workspace_id=workspace_id,
            event_type="b2b_order.status_changed",
            entity_type="b2b_order",
            entity_id=str(order.id),
            payload={
                "order_number": order.order_number,
                "previous_status": previous_status,
                "new_status": order.status,
                "actor": actor,
                "source": "b2b_fulfillment",
            },
            trace_id=trace_id,
        )
    return await get_order_fulfillment(
        db,
        workspace_id=workspace_id,
        order_id=order.id,
    )  # type: ignore[return-value]


async def ship_b2b_order(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    order_id: str | UUID,
    carrier: str,
    tracking_number: str,
    actor: str,
    origin: str | None = None,
    destination: str | None = None,
    ship_date: datetime | None = None,
    shipment_key: str | None = None,
    trace_id: str | None = None,
) -> B2BFulfillment:
    """Consume reserved inventory and create the linked TMS shipment."""
    carrier = carrier.strip()
    tracking_number = tracking_number.strip()
    if not carrier:
        raise B2BFulfillmentStateError("carrier is required")
    if not tracking_number:
        raise B2BFulfillmentStateError("tracking_number is required")

    order = await _load_order(db, workspace_id=workspace_id, order_id=order_id)
    fulfillment = await get_order_fulfillment(
        db,
        workspace_id=workspace_id,
        order_id=order.id,
    )
    if fulfillment is None:
        raise B2BFulfillmentNotFoundError("B2B order fulfillment not found")
    if fulfillment.status in {"shipped", "delivered"}:
        return fulfillment
    if fulfillment.status != "reserved":
        raise B2BFulfillmentStateError(
            f"fulfillment in '{fulfillment.status}' state cannot be shipped"
        )
    if order.status != "processing":
        raise B2BFulfillmentStateError("order must be processing before shipment")

    snapshots: dict[UUID, InventorySnapshot] = {}
    for item in fulfillment.items:
        snapshot = snapshots.get(item.inventory_snapshot_id)
        if snapshot is None:
            snapshot = (
                await db.execute(
                    select(InventorySnapshot)
                    .where(
                        InventorySnapshot.workspace_id == workspace_id,
                        InventorySnapshot.id == item.inventory_snapshot_id,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if snapshot is None:
                raise B2BFulfillmentStateError("reserved inventory row not found")
            snapshots[item.inventory_snapshot_id] = snapshot
        quantity = item.quantity - item.shipped_quantity - item.released_quantity
        if quantity <= 0:
            continue
        if snapshot.quantity < quantity or snapshot.reserved < quantity:
            raise B2BFulfillmentStateError("inventory reservation is inconsistent")
        snapshot.quantity -= quantity
        snapshot.reserved -= quantity
        _sync_available(snapshot)
        item.shipped_quantity += quantity
        item.reserved_quantity = 0

    now = _now()
    actual_ship_date = ship_date or now
    shipment = ShipmentRecord(
        workspace_id=workspace_id,
        b2b_order_id=order.id,
        carrier=carrier,
        origin=origin or fulfillment.warehouse_location,
        destination=destination or _destination(order),
        tracking_number=tracking_number,
        status="in_transit",
        ship_date=actual_ship_date,
        trace_id=trace_id,
    )
    db.add(shipment)
    await db.flush()
    db.add(
        LogisticsEvent(
            workspace_id=workspace_id,
            shipment_id=shipment.id,
            event_type="in_transit",
            location=origin or fulfillment.warehouse_location,
            description="B2B order handed to carrier",
            occurred_at=actual_ship_date,
            trace_id=trace_id,
        )
    )

    previous_status = order.status
    fulfillment.status = "shipped"
    fulfillment.shipped_at = now
    fulfillment.shipment_id = shipment.id
    fulfillment.shipment_key = shipment_key
    order.status = "shipped"
    order.tracking_number = tracking_number
    order.tracking_carrier = carrier
    await db.flush()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_fulfillment.shipped",
        entity_type="b2b_fulfillment",
        entity_id=str(fulfillment.id),
        payload={
            "fulfillment_number": fulfillment.fulfillment_number,
            "order_id": str(order.id),
            "order_number": order.order_number,
            "shipment_id": str(shipment.id),
            "carrier": carrier,
            "tracking_number": tracking_number,
            "actor": actor,
        },
        trace_id=trace_id,
    )
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_order.status_changed",
        entity_type="b2b_order",
        entity_id=str(order.id),
        payload={
            "order_number": order.order_number,
            "previous_status": previous_status,
            "new_status": order.status,
            "actor": actor,
            "source": "b2b_fulfillment",
        },
        trace_id=trace_id,
    )
    return await get_order_fulfillment(
        db,
        workspace_id=workspace_id,
        order_id=order.id,
    )  # type: ignore[return-value]


async def deliver_b2b_order(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    order_id: str | UUID,
    actor: str,
    occurred_at: datetime | None = None,
    trace_id: str | None = None,
) -> B2BFulfillment:
    """Mark the linked shipment delivered and synchronize the B2B order."""
    order = await _load_order(db, workspace_id=workspace_id, order_id=order_id)
    fulfillment = await get_order_fulfillment(
        db,
        workspace_id=workspace_id,
        order_id=order.id,
    )
    if fulfillment is None:
        raise B2BFulfillmentNotFoundError("B2B order fulfillment not found")
    if fulfillment.status == "delivered":
        return fulfillment
    if fulfillment.status != "shipped" or fulfillment.shipment_id is None:
        raise B2BFulfillmentStateError("only a shipped fulfillment can be delivered")

    shipment = (
        await db.execute(
            select(ShipmentRecord).where(
                ShipmentRecord.workspace_id == workspace_id,
                ShipmentRecord.id == fulfillment.shipment_id,
            )
        )
    ).scalar_one_or_none()
    if shipment is None:
        raise B2BFulfillmentStateError("linked shipment not found")

    now = _now()
    delivered_at = _as_utc(occurred_at or now)
    shipment.status = "delivered"
    if shipment.ship_date is not None:
        ship_date = _as_utc(shipment.ship_date)
        shipment.delivery_time_days = max((delivered_at - ship_date).days, 0)
    db.add(
        LogisticsEvent(
            workspace_id=workspace_id,
            shipment_id=shipment.id,
            event_type="delivered",
            location=shipment.destination,
            description="B2B order delivered",
            occurred_at=delivered_at,
            trace_id=trace_id,
        )
    )

    previous_status = order.status
    fulfillment.status = "delivered"
    fulfillment.delivered_at = delivered_at
    order.status = "delivered"
    await db.flush()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_fulfillment.delivered",
        entity_type="b2b_fulfillment",
        entity_id=str(fulfillment.id),
        payload={
            "fulfillment_number": fulfillment.fulfillment_number,
            "order_id": str(order.id),
            "order_number": order.order_number,
            "shipment_id": str(shipment.id),
            "actor": actor,
        },
        trace_id=trace_id,
    )
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_order.status_changed",
        entity_type="b2b_order",
        entity_id=str(order.id),
        payload={
            "order_number": order.order_number,
            "previous_status": previous_status,
            "new_status": order.status,
            "actor": actor,
            "source": "b2b_fulfillment",
        },
        trace_id=trace_id,
    )
    return await get_order_fulfillment(
        db,
        workspace_id=workspace_id,
        order_id=order.id,
    )  # type: ignore[return-value]
