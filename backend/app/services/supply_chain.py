"""Supply chain intelligence service (M4.1).

Pure data + lifecycle layer for the future Supply Chain Agent. **No Supply
Chain Agent and no automatic purchasing.** Purchase orders follow an explicit
state machine (draft -> approved -> ordered -> received; cancellable from
draft/approved), inventory computes available = quantity - reserved, and every
write emits an event with trace_id.
"""

import logging
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.supplier import Supplier
from app.models.supply_chain import (
    InventorySnapshot,
    LogisticsEvent,
    PurchaseOrder,
    PurchaseOrderItem,
    ShipmentRecord,
    SupplierProfile,
    SupplyChainKnowledgeEntry,
)
from app.schemas.supply_chain import (
    InventoryCreate,
    InventoryUpdate,
    LogisticsEventCreate,
    PurchaseOrderCreate,
    PurchaseOrderUpdate,
    ShipmentCreate,
    ShipmentUpdate,
    SupplierProfileCreate,
    SupplierProfileUpdate,
    SupplyChainKnowledgeCreate,
)
from app.services import event_service

logger = logging.getLogger(__name__)

ZERO = Decimal("0")

# Allowed PO state transitions (draft/approved can be cancelled).
# ordered -> partial_received -> received supports split deliveries.
PO_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"approved", "cancelled"},
    "approved": {"ordered", "cancelled"},
    "ordered": {"partial_received", "received"},
    "partial_received": {"received"},
    "received": set(),
    "cancelled": set(),
}


class SupplyChainError(Exception):
    """Raised when a supply chain operation cannot complete."""


async def _load_supplier(
    session: AsyncSession, *, workspace_id: UUID, supplier_id: UUID
) -> Supplier | None:
    return (
        await session.execute(
            select(Supplier).where(
                Supplier.workspace_id == workspace_id,
                Supplier.id == supplier_id,
            )
        )
    ).scalar_one_or_none()


async def _ensure_supplier(
    session: AsyncSession, *, workspace_id: UUID, supplier_id: UUID | None
) -> None:
    if supplier_id is None:
        return
    supplier = await _load_supplier(session, workspace_id=workspace_id, supplier_id=supplier_id)
    if supplier is None:
        raise SupplyChainError("supplier not found")


async def _ensure_product(
    session: AsyncSession, *, workspace_id: UUID, product_id: UUID | None
) -> None:
    if product_id is None:
        return
    exists = (
        await session.execute(
            select(Product.id).where(
                Product.workspace_id == workspace_id,
                Product.id == product_id,
            )
        )
    ).scalar_one_or_none()
    if exists is None:
        raise SupplyChainError("product not found")


# --------------------------------------------------------------------------- #
# Supplier profiles
# --------------------------------------------------------------------------- #


async def create_supplier_profile(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: SupplierProfileCreate,
    trace_id: str | None = None,
) -> SupplierProfile:
    """Create one supplier profile (unique per supplier per workspace)."""
    await _ensure_supplier(session, workspace_id=workspace_id, supplier_id=data.supplier_id)
    profile = SupplierProfile(
        workspace_id=workspace_id,
        supplier_id=data.supplier_id,
        category=data.category,
        location=data.location,
        factory_type=data.factory_type,
        lead_time_days=data.lead_time_days,
        minimum_order_qty=data.minimum_order_qty,
        quality_score=data.quality_score,
        on_time_rate=data.on_time_rate,
        defect_rate=data.defect_rate,
        certifications=data.certifications,
        risk_level=data.risk_level,
        trace_id=trace_id,
    )
    session.add(profile)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise SupplyChainError("supplier profile already exists") from exc
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="supply.supplier_profile_created",
        entity_type="supplier",
        entity_id=str(data.supplier_id),
        payload={
            "profile_id": str(profile.id),
            "risk_level": data.risk_level,
            "category": data.category,
        },
        trace_id=trace_id,
    )
    logger.info("supplier profile %s created trace=%s", profile.id, trace_id)
    return profile


async def _load_supplier_profile(
    session: AsyncSession, *, workspace_id: UUID, profile_id: UUID
) -> SupplierProfile | None:
    return (
        await session.execute(
            select(SupplierProfile).where(
                SupplierProfile.workspace_id == workspace_id,
                SupplierProfile.id == profile_id,
            )
        )
    ).scalar_one_or_none()


async def update_supplier_profile(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    profile_id: UUID,
    data: SupplierProfileUpdate,
    trace_id: str | None = None,
) -> SupplierProfile:
    """Partially update a supplier profile."""
    profile = await _load_supplier_profile(
        session, workspace_id=workspace_id, profile_id=profile_id
    )
    if profile is None:
        raise SupplyChainError("supplier profile not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(profile, key, value)
    profile.updated_at = datetime.now(UTC)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="supply.supplier_profile_updated",
        entity_type="supplier",
        entity_id=str(profile.supplier_id) if profile.supplier_id else str(profile.id),
        payload={"risk_level": profile.risk_level},
        trace_id=trace_id,
    )
    return profile


async def list_supplier_profiles(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    risk_level: str | None = None,
    category: str | None = None,
    limit: int = 50,
) -> list[SupplierProfile]:
    """List supplier profiles, newest first."""
    stmt = select(SupplierProfile).where(SupplierProfile.workspace_id == workspace_id)
    if risk_level:
        stmt = stmt.where(SupplierProfile.risk_level == risk_level)
    if category:
        stmt = stmt.where(SupplierProfile.category == category)
    stmt = stmt.order_by(SupplierProfile.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


async def delete_supplier_profile(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    profile_id: UUID,
    trace_id: str | None = None,
) -> None:
    """Delete a supplier profile (audited via event)."""
    profile = await _load_supplier_profile(
        session, workspace_id=workspace_id, profile_id=profile_id
    )
    if profile is None:
        raise SupplyChainError("supplier profile not found")
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="supply.supplier_profile_deleted",
        entity_type="supplier",
        entity_id=str(profile.supplier_id) if profile.supplier_id else str(profile.id),
        payload={"risk_level": profile.risk_level},
        trace_id=trace_id,
    )
    await session.delete(profile)
    await session.flush()


# --------------------------------------------------------------------------- #
# Purchase orders
# --------------------------------------------------------------------------- #


async def create_purchase_order(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: PurchaseOrderCreate,
    trace_id: str | None = None,
) -> PurchaseOrder:
    """Create a PO in draft state; totals are computed from items."""
    await _ensure_supplier(session, workspace_id=workspace_id, supplier_id=data.supplier_id)
    for item in data.items:
        await _ensure_product(session, workspace_id=workspace_id, product_id=item.product_id)

    subtotal = sum((item.quantity * item.unit_cost for item in data.items), ZERO)
    total = subtotal + data.shipping_cost
    purchase_order = PurchaseOrder(
        workspace_id=workspace_id,
        po_number=data.po_number,
        supplier_id=data.supplier_id,
        status="draft",
        currency=data.currency,
        subtotal=subtotal,
        shipping_cost=data.shipping_cost,
        total=total,
        expected_delivery_at=data.expected_delivery_at,
        notes=data.notes,
        trace_id=trace_id,
    )
    session.add(purchase_order)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise SupplyChainError(f"purchase order '{data.po_number}' already exists") from exc
    for item in data.items:
        session.add(
            PurchaseOrderItem(
                workspace_id=workspace_id,
                purchase_order_id=purchase_order.id,
                product_id=item.product_id,
                sku=item.sku,
                name=item.name,
                quantity=item.quantity,
                unit_cost=item.unit_cost,
                line_total=item.quantity * item.unit_cost,
            )
        )
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="supply.purchase_order_created",
        entity_type="purchase_order",
        entity_id=str(purchase_order.id),
        payload={
            "po_number": data.po_number,
            "status": "draft",
            "item_count": len(data.items),
            "total": str(total),
        },
        trace_id=trace_id,
    )
    logger.info("purchase order %s created (draft) trace=%s", purchase_order.id, trace_id)
    return purchase_order


async def _load_purchase_order(
    session: AsyncSession, *, workspace_id: UUID, po_id: UUID
) -> PurchaseOrder | None:
    return (
        await session.execute(
            select(PurchaseOrder).where(
                PurchaseOrder.workspace_id == workspace_id,
                PurchaseOrder.id == po_id,
            )
        )
    ).scalar_one_or_none()


async def _load_po_items(
    session: AsyncSession, *, workspace_id: UUID, po_id: UUID
) -> list[PurchaseOrderItem]:
    rows = (
        (
            await session.execute(
                select(PurchaseOrderItem)
                .where(
                    PurchaseOrderItem.workspace_id == workspace_id,
                    PurchaseOrderItem.purchase_order_id == po_id,
                )
                .order_by(PurchaseOrderItem.id)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def get_purchase_order(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    po_id: UUID,
) -> tuple[PurchaseOrder, list[PurchaseOrderItem]] | None:
    """Return a PO with its line items or None."""
    purchase_order = await _load_purchase_order(session, workspace_id=workspace_id, po_id=po_id)
    if purchase_order is None:
        return None
    items = await _load_po_items(session, workspace_id=workspace_id, po_id=po_id)
    return purchase_order, items


async def update_purchase_order(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    po_id: UUID,
    data: PurchaseOrderUpdate,
    trace_id: str | None = None,
) -> PurchaseOrder:
    """Update a PO (draft only)."""
    purchase_order = await _load_purchase_order(session, workspace_id=workspace_id, po_id=po_id)
    if purchase_order is None:
        raise SupplyChainError("purchase order not found")
    if purchase_order.status != "draft":
        raise SupplyChainError("purchase order can only be updated in draft")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(purchase_order, key, value)
    purchase_order.total = purchase_order.subtotal + purchase_order.shipping_cost
    purchase_order.updated_at = datetime.now(UTC)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="supply.purchase_order_updated",
        entity_type="purchase_order",
        entity_id=str(purchase_order.id),
        payload={"status": purchase_order.status},
        trace_id=trace_id,
    )
    return purchase_order


async def _transition_purchase_order(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    po_id: UUID,
    target: str,
    event_type: str,
    trace_id: str | None,
    received: bool = False,
) -> PurchaseOrder:
    """Shared PO lifecycle transition with state-machine validation."""
    purchase_order = await _load_purchase_order(session, workspace_id=workspace_id, po_id=po_id)
    if purchase_order is None:
        raise SupplyChainError("purchase order not found")
    allowed = PO_TRANSITIONS.get(purchase_order.status, set())
    if target not in allowed:
        raise SupplyChainError(
            f"cannot transition purchase order from '{purchase_order.status}' to '{target}'"
        )
    purchase_order.status = target
    purchase_order.updated_at = datetime.now(UTC)
    if received:
        purchase_order.received_at = datetime.now(UTC)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type=event_type,
        entity_type="purchase_order",
        entity_id=str(purchase_order.id),
        payload={"po_number": purchase_order.po_number, "status": target},
        trace_id=trace_id,
    )
    logger.info("purchase order %s -> %s trace=%s", purchase_order.id, target, trace_id)
    return purchase_order


async def approve_purchase_order(
    session: AsyncSession, *, workspace_id: UUID, po_id: UUID, trace_id: str | None = None
) -> PurchaseOrder:
    """draft -> approved."""
    return await _transition_purchase_order(
        session,
        workspace_id=workspace_id,
        po_id=po_id,
        target="approved",
        event_type="supply.purchase_order_approved",
        trace_id=trace_id,
    )


async def order_purchase_order(
    session: AsyncSession, *, workspace_id: UUID, po_id: UUID, trace_id: str | None = None
) -> PurchaseOrder:
    """approved -> ordered (PO sent to supplier)."""
    return await _transition_purchase_order(
        session,
        workspace_id=workspace_id,
        po_id=po_id,
        target="ordered",
        event_type="supply.purchase_order_ordered",
        trace_id=trace_id,
    )


async def partial_receive_purchase_order(
    session: AsyncSession, *, workspace_id: UUID, po_id: UUID, trace_id: str | None = None
) -> PurchaseOrder:
    """ordered -> partial_received (first delivery batch arrived)."""
    return await _transition_purchase_order(
        session,
        workspace_id=workspace_id,
        po_id=po_id,
        target="partial_received",
        event_type="supply.purchase_order_partial_received",
        trace_id=trace_id,
    )


async def receive_purchase_order(
    session: AsyncSession, *, workspace_id: UUID, po_id: UUID, trace_id: str | None = None
) -> PurchaseOrder:
    """ordered -> received (goods arrived)."""
    return await _transition_purchase_order(
        session,
        workspace_id=workspace_id,
        po_id=po_id,
        target="received",
        event_type="supply.purchase_order_received",
        trace_id=trace_id,
        received=True,
    )


async def cancel_purchase_order(
    session: AsyncSession, *, workspace_id: UUID, po_id: UUID, trace_id: str | None = None
) -> PurchaseOrder:
    """draft/approved -> cancelled."""
    return await _transition_purchase_order(
        session,
        workspace_id=workspace_id,
        po_id=po_id,
        target="cancelled",
        event_type="supply.purchase_order_cancelled",
        trace_id=trace_id,
    )


async def list_purchase_orders(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    status: str | None = None,
    supplier_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[PurchaseOrder]:
    """List purchase orders, newest first."""
    stmt = select(PurchaseOrder).where(PurchaseOrder.workspace_id == workspace_id)
    if status:
        stmt = stmt.where(PurchaseOrder.status == status)
    if supplier_id is not None:
        stmt = stmt.where(PurchaseOrder.supplier_id == supplier_id)
    stmt = stmt.order_by(PurchaseOrder.created_at.desc()).limit(limit).offset(offset)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


# --------------------------------------------------------------------------- #
# Inventory
# --------------------------------------------------------------------------- #


def _compute_available(quantity: int, reserved: int, available: int | None) -> int:
    """available = quantity - reserved unless explicitly provided."""
    if available is not None:
        return available
    return max(quantity - reserved, 0)


async def create_inventory(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: InventoryCreate,
    trace_id: str | None = None,
) -> InventorySnapshot:
    """Create an inventory snapshot (one per product/location)."""
    await _ensure_product(session, workspace_id=workspace_id, product_id=data.product_id)
    snapshot = InventorySnapshot(
        workspace_id=workspace_id,
        product_id=data.product_id,
        location=data.location,
        quantity=data.quantity,
        reserved=data.reserved,
        available=_compute_available(data.quantity, data.reserved, data.available),
        in_transit=data.in_transit,
        snapshot_time=data.snapshot_time,
        trace_id=trace_id,
    )
    session.add(snapshot)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise SupplyChainError(
            f"inventory for product/location '{data.location}' already exists"
        ) from exc
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="supply.inventory_created",
        entity_type="product",
        entity_id=str(data.product_id) if data.product_id else str(snapshot.id),
        payload={
            "location": data.location,
            "quantity": data.quantity,
            "reserved": data.reserved,
            "available": snapshot.available,
        },
        trace_id=trace_id,
    )
    logger.info(
        "inventory snapshot %s created at %s trace=%s", snapshot.id, data.location, trace_id
    )
    return snapshot


async def _load_inventory(
    session: AsyncSession, *, workspace_id: UUID, inventory_id: UUID
) -> InventorySnapshot | None:
    return (
        await session.execute(
            select(InventorySnapshot).where(
                InventorySnapshot.workspace_id == workspace_id,
                InventorySnapshot.id == inventory_id,
            )
        )
    ).scalar_one_or_none()


async def update_inventory(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    inventory_id: UUID,
    data: InventoryUpdate,
    trace_id: str | None = None,
) -> InventorySnapshot:
    """Partially update inventory; available is recomputed when omitted."""
    snapshot = await _load_inventory(session, workspace_id=workspace_id, inventory_id=inventory_id)
    if snapshot is None:
        raise SupplyChainError("inventory snapshot not found")
    updates = data.model_dump(exclude_unset=True)
    provided_available = updates.pop("available", None)
    for key, value in updates.items():
        setattr(snapshot, key, value)
    snapshot.available = _compute_available(
        snapshot.quantity, snapshot.reserved, provided_available
    )
    snapshot.updated_at = datetime.now(UTC)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="supply.inventory_updated",
        entity_type="product",
        entity_id=str(snapshot.product_id) if snapshot.product_id else str(snapshot.id),
        payload={
            "location": snapshot.location,
            "quantity": snapshot.quantity,
            "available": snapshot.available,
        },
        trace_id=trace_id,
    )
    return snapshot


async def list_inventory(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    location: str | None = None,
    product_id: UUID | None = None,
    limit: int = 50,
) -> list[InventorySnapshot]:
    """List inventory snapshots, newest first."""
    stmt = select(InventorySnapshot).where(InventorySnapshot.workspace_id == workspace_id)
    if location:
        stmt = stmt.where(InventorySnapshot.location == location)
    if product_id is not None:
        stmt = stmt.where(InventorySnapshot.product_id == product_id)
    stmt = stmt.order_by(InventorySnapshot.updated_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


async def delete_inventory(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    inventory_id: UUID,
    trace_id: str | None = None,
) -> None:
    """Delete an inventory snapshot (audited via event)."""
    snapshot = await _load_inventory(session, workspace_id=workspace_id, inventory_id=inventory_id)
    if snapshot is None:
        raise SupplyChainError("inventory snapshot not found")
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="supply.inventory_deleted",
        entity_type="product",
        entity_id=str(snapshot.product_id) if snapshot.product_id else str(snapshot.id),
        payload={"location": snapshot.location},
        trace_id=trace_id,
    )
    await session.delete(snapshot)
    await session.flush()


# --------------------------------------------------------------------------- #
# Shipments + logistics events
# --------------------------------------------------------------------------- #


async def create_shipment(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: ShipmentCreate,
    trace_id: str | None = None,
) -> ShipmentRecord:
    """Create a shipment record."""
    if data.purchase_order_id is not None:
        purchase_order = await _load_purchase_order(
            session, workspace_id=workspace_id, po_id=data.purchase_order_id
        )
        if purchase_order is None:
            raise SupplyChainError("purchase order not found")
    shipment = ShipmentRecord(
        workspace_id=workspace_id,
        purchase_order_id=data.purchase_order_id,
        carrier=data.carrier,
        origin=data.origin,
        destination=data.destination,
        tracking_number=data.tracking_number,
        status=data.status,
        ship_date=data.ship_date,
        delivery_time_days=data.delivery_time_days,
        delay_reason=data.delay_reason,
        trace_id=trace_id,
    )
    session.add(shipment)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="supply.shipment_created",
        entity_type="shipment",
        entity_id=str(shipment.id),
        payload={
            "carrier": data.carrier,
            "tracking_number": data.tracking_number,
            "status": data.status,
        },
        trace_id=trace_id,
    )
    logger.info("shipment %s created (%s) trace=%s", shipment.id, data.carrier, trace_id)
    return shipment


async def _load_shipment(
    session: AsyncSession, *, workspace_id: UUID, shipment_id: UUID
) -> ShipmentRecord | None:
    return (
        await session.execute(
            select(ShipmentRecord).where(
                ShipmentRecord.workspace_id == workspace_id,
                ShipmentRecord.id == shipment_id,
            )
        )
    ).scalar_one_or_none()


async def update_shipment(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    shipment_id: UUID,
    data: ShipmentUpdate,
    trace_id: str | None = None,
) -> ShipmentRecord:
    """Partially update a shipment (status/tracking/delay)."""
    shipment = await _load_shipment(session, workspace_id=workspace_id, shipment_id=shipment_id)
    if shipment is None:
        raise SupplyChainError("shipment not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(shipment, key, value)
    shipment.updated_at = datetime.now(UTC)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="supply.shipment_updated",
        entity_type="shipment",
        entity_id=str(shipment.id),
        payload={"status": shipment.status, "delay_reason": shipment.delay_reason},
        trace_id=trace_id,
    )
    return shipment


async def add_logistics_event(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    shipment_id: UUID,
    data: LogisticsEventCreate,
    trace_id: str | None = None,
) -> LogisticsEvent:
    """Append a tracking event to a shipment."""
    shipment = await _load_shipment(session, workspace_id=workspace_id, shipment_id=shipment_id)
    if shipment is None:
        raise SupplyChainError("shipment not found")
    event = LogisticsEvent(
        workspace_id=workspace_id,
        shipment_id=shipment_id,
        event_type=data.event_type,
        location=data.location,
        description=data.description,
        occurred_at=data.occurred_at,
        trace_id=trace_id,
    )
    session.add(event)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="supply.logistics_event_added",
        entity_type="shipment",
        entity_id=str(shipment_id),
        payload={
            "logistics_event_id": str(event.id),
            "event_type": data.event_type,
            "location": data.location,
        },
        trace_id=trace_id,
    )
    logger.info("logistics event %s added to shipment %s trace=%s", event.id, shipment_id, trace_id)
    return event


async def list_logistics_events(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    shipment_id: UUID,
    limit: int = 100,
) -> list[LogisticsEvent]:
    """List shipment tracking events, newest first."""
    rows = (
        (
            await session.execute(
                select(LogisticsEvent)
                .where(
                    LogisticsEvent.workspace_id == workspace_id,
                    LogisticsEvent.shipment_id == shipment_id,
                )
                .order_by(LogisticsEvent.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def list_shipments(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    status: str | None = None,
    carrier: str | None = None,
    limit: int = 50,
) -> list[ShipmentRecord]:
    """List shipments, newest first."""
    stmt = select(ShipmentRecord).where(ShipmentRecord.workspace_id == workspace_id)
    if status:
        stmt = stmt.where(ShipmentRecord.status == status)
    if carrier:
        stmt = stmt.where(ShipmentRecord.carrier == carrier)
    stmt = stmt.order_by(ShipmentRecord.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


async def delete_shipment(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    shipment_id: UUID,
    trace_id: str | None = None,
) -> None:
    """Delete a shipment (audited via event)."""
    shipment = await _load_shipment(session, workspace_id=workspace_id, shipment_id=shipment_id)
    if shipment is None:
        raise SupplyChainError("shipment not found")
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="supply.shipment_deleted",
        entity_type="shipment",
        entity_id=str(shipment.id),
        payload={"carrier": shipment.carrier},
        trace_id=trace_id,
    )
    await session.delete(shipment)
    await session.flush()


# --------------------------------------------------------------------------- #
# Supply chain knowledge memory
# --------------------------------------------------------------------------- #


async def create_knowledge_entry(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: SupplyChainKnowledgeCreate,
    trace_id: str | None = None,
) -> SupplyChainKnowledgeEntry:
    """Create one supply chain knowledge entry."""
    if data.supplier_id is not None:
        await _ensure_supplier(session, workspace_id=workspace_id, supplier_id=data.supplier_id)
    await _ensure_product(session, workspace_id=workspace_id, product_id=data.product_id)
    entry = SupplyChainKnowledgeEntry(
        workspace_id=workspace_id,
        supplier_id=data.supplier_id,
        product_id=data.product_id,
        category=data.category,
        entry_type=data.entry_type,
        title=data.title,
        content=data.content,
        tags=data.tags,
        source=data.source,
        confidence=data.confidence,
        trace_id=trace_id,
    )
    session.add(entry)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="supply.knowledge_created",
        entity_type="supplier",
        entity_id=str(data.supplier_id) if data.supplier_id else str(workspace_id),
        payload={
            "knowledge_id": str(entry.id),
            "entry_type": data.entry_type,
            "category": data.category,
        },
        trace_id=trace_id,
    )
    logger.info(
        "supply chain knowledge entry %s created (%s) trace=%s",
        entry.id,
        data.entry_type,
        trace_id,
    )
    return entry


async def list_knowledge_entries(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    category: str | None = None,
    entry_type: str | None = None,
    supplier_id: UUID | None = None,
    product_id: UUID | None = None,
    limit: int = 100,
) -> list[SupplyChainKnowledgeEntry]:
    """Query supply chain knowledge entries, newest first."""
    stmt = select(SupplyChainKnowledgeEntry).where(
        SupplyChainKnowledgeEntry.workspace_id == workspace_id
    )
    if category:
        stmt = stmt.where(SupplyChainKnowledgeEntry.category == category)
    if entry_type:
        stmt = stmt.where(SupplyChainKnowledgeEntry.entry_type == entry_type)
    if supplier_id is not None:
        stmt = stmt.where(SupplyChainKnowledgeEntry.supplier_id == supplier_id)
    if product_id is not None:
        stmt = stmt.where(SupplyChainKnowledgeEntry.product_id == product_id)
    stmt = stmt.order_by(SupplyChainKnowledgeEntry.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)
