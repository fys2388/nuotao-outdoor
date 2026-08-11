"""Supply chain intelligence endpoints (M4.1): suppliers, POs, inventory, logistics, knowledge.

Data capture + lifecycle only. No Supply Chain Agent, no automatic purchasing.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.tracing import get_trace_id
from app.core.workspace import get_workspace_id
from app.schemas.supply_chain import (
    InventoryCreate,
    InventoryOut,
    InventoryUpdate,
    LogisticsEventCreate,
    LogisticsEventOut,
    PurchaseOrderCreate,
    PurchaseOrderDetailOut,
    PurchaseOrderItemOut,
    PurchaseOrderOut,
    PurchaseOrderUpdate,
    ShipmentCreate,
    ShipmentOut,
    ShipmentUpdate,
    SupplierProfileCreate,
    SupplierProfileOut,
    SupplierProfileUpdate,
    SupplyChainKnowledgeCreate,
    SupplyChainKnowledgeOut,
)
from app.services import supply_chain

router = APIRouter(tags=["supply-chain"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]


def _http_error(exc: supply_chain.SupplyChainError) -> HTTPException:
    """Map service errors: missing -> 404, conflict -> 409, others -> 400."""
    message = str(exc)
    if "not found" in message:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)
    if "already exists" in message:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


# --------------------------------------------------------------------------- #
# Supplier profiles
# --------------------------------------------------------------------------- #


@router.post(
    "/supplier-profiles",
    response_model=SupplierProfileOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a supplier intelligence profile",
)
async def create_supplier_profile(
    body: SupplierProfileCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> SupplierProfileOut:
    """Create one profile per supplier (duplicate returns 409)."""
    try:
        profile = await supply_chain.create_supplier_profile(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except supply_chain.SupplyChainError as exc:
        raise _http_error(exc) from exc
    return SupplierProfileOut.model_validate(profile)


@router.get(
    "/supplier-profiles",
    response_model=list[SupplierProfileOut],
    summary="List supplier profiles",
)
async def list_supplier_profiles(
    db: DbSession,
    workspace_id: WorkspaceId,
    risk_level: str | None = Query(default=None, max_length=16),
    category: str | None = Query(default=None, max_length=64),
    limit: int = 50,
) -> list[SupplierProfileOut]:
    """Return profiles, newest first, with optional filters."""
    rows = await supply_chain.list_supplier_profiles(
        db, workspace_id=workspace_id, risk_level=risk_level, category=category, limit=limit
    )
    return [SupplierProfileOut.model_validate(row) for row in rows]


@router.put(
    "/supplier-profiles/{profile_id}",
    response_model=SupplierProfileOut,
    summary="Update a supplier profile",
)
async def update_supplier_profile(
    profile_id: UUID,
    body: SupplierProfileUpdate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> SupplierProfileOut:
    """Partially update quality/risk fields."""
    try:
        profile = await supply_chain.update_supplier_profile(
            db,
            workspace_id=workspace_id,
            profile_id=profile_id,
            data=body,
            trace_id=get_trace_id(),
        )
    except supply_chain.SupplyChainError as exc:
        raise _http_error(exc) from exc
    return SupplierProfileOut.model_validate(profile)


@router.delete(
    "/supplier-profiles/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a supplier profile",
)
async def delete_supplier_profile(
    profile_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> None:
    """Delete a profile (audited via event)."""
    try:
        await supply_chain.delete_supplier_profile(
            db, workspace_id=workspace_id, profile_id=profile_id, trace_id=get_trace_id()
        )
    except supply_chain.SupplyChainError as exc:
        raise _http_error(exc) from exc


# --------------------------------------------------------------------------- #
# Purchase orders
# --------------------------------------------------------------------------- #


@router.post(
    "/purchase-orders",
    response_model=PurchaseOrderOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a purchase order (draft)",
)
async def create_purchase_order(
    body: PurchaseOrderCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> PurchaseOrderOut:
    """Create a PO in draft state; totals computed from line items."""
    try:
        purchase_order = await supply_chain.create_purchase_order(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except supply_chain.SupplyChainError as exc:
        raise _http_error(exc) from exc
    return PurchaseOrderOut.model_validate(purchase_order)


@router.get(
    "/purchase-orders",
    response_model=list[PurchaseOrderOut],
    summary="List purchase orders",
)
async def list_purchase_orders(
    db: DbSession,
    workspace_id: WorkspaceId,
    po_status: str | None = Query(default=None, alias="status", max_length=16),
    supplier_id: Annotated[UUID | None, Query()] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[PurchaseOrderOut]:
    """Return purchase orders, newest first, with optional filters."""
    rows = await supply_chain.list_purchase_orders(
        db,
        workspace_id=workspace_id,
        status=po_status,
        supplier_id=supplier_id,
        limit=limit,
        offset=offset,
    )
    return [PurchaseOrderOut.model_validate(row) for row in rows]


@router.get(
    "/purchase-orders/{po_id}",
    response_model=PurchaseOrderDetailOut,
    summary="Get a purchase order with line items",
)
async def get_purchase_order(
    po_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> PurchaseOrderDetailOut:
    """Return a PO plus its items."""
    result = await supply_chain.get_purchase_order(db, workspace_id=workspace_id, po_id=po_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="purchase order not found"
        )
    purchase_order, items = result
    detail = PurchaseOrderDetailOut.model_validate(purchase_order)
    detail.items = [PurchaseOrderItemOut.model_validate(item) for item in items]
    return detail


@router.put(
    "/purchase-orders/{po_id}",
    response_model=PurchaseOrderOut,
    summary="Update a purchase order (draft only)",
)
async def update_purchase_order(
    po_id: UUID,
    body: PurchaseOrderUpdate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> PurchaseOrderOut:
    """Update notes/shipping of a draft PO."""
    try:
        purchase_order = await supply_chain.update_purchase_order(
            db,
            workspace_id=workspace_id,
            po_id=po_id,
            data=body,
            trace_id=get_trace_id(),
        )
    except supply_chain.SupplyChainError as exc:
        raise _http_error(exc) from exc
    return PurchaseOrderOut.model_validate(purchase_order)


@router.post(
    "/purchase-orders/{po_id}/approve",
    response_model=PurchaseOrderOut,
    summary="Approve a purchase order (draft -> approved)",
)
async def approve_purchase_order(
    po_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> PurchaseOrderOut:
    """Move the PO from draft to approved."""
    try:
        purchase_order = await supply_chain.approve_purchase_order(
            db, workspace_id=workspace_id, po_id=po_id, trace_id=get_trace_id()
        )
    except supply_chain.SupplyChainError as exc:
        raise _http_error(exc) from exc
    return PurchaseOrderOut.model_validate(purchase_order)


@router.post(
    "/purchase-orders/{po_id}/order",
    response_model=PurchaseOrderOut,
    summary="Send the purchase order (approved -> ordered)",
)
async def order_purchase_order(
    po_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> PurchaseOrderOut:
    """Move the PO from approved to ordered (sent to supplier)."""
    try:
        purchase_order = await supply_chain.order_purchase_order(
            db, workspace_id=workspace_id, po_id=po_id, trace_id=get_trace_id()
        )
    except supply_chain.SupplyChainError as exc:
        raise _http_error(exc) from exc
    return PurchaseOrderOut.model_validate(purchase_order)


@router.post(
    "/purchase-orders/{po_id}/receive",
    response_model=PurchaseOrderOut,
    summary="Receive goods (ordered -> received)",
)
async def receive_purchase_order(
    po_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> PurchaseOrderOut:
    """Mark the PO as received with a received_at timestamp."""
    try:
        purchase_order = await supply_chain.receive_purchase_order(
            db, workspace_id=workspace_id, po_id=po_id, trace_id=get_trace_id()
        )
    except supply_chain.SupplyChainError as exc:
        raise _http_error(exc) from exc
    return PurchaseOrderOut.model_validate(purchase_order)


@router.post(
    "/purchase-orders/{po_id}/cancel",
    response_model=PurchaseOrderOut,
    summary="Cancel a purchase order (draft/approved -> cancelled)",
)
async def cancel_purchase_order(
    po_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> PurchaseOrderOut:
    """Cancel the PO from draft or approved."""
    try:
        purchase_order = await supply_chain.cancel_purchase_order(
            db, workspace_id=workspace_id, po_id=po_id, trace_id=get_trace_id()
        )
    except supply_chain.SupplyChainError as exc:
        raise _http_error(exc) from exc
    return PurchaseOrderOut.model_validate(purchase_order)


# --------------------------------------------------------------------------- #
# Inventory
# --------------------------------------------------------------------------- #


@router.post(
    "/inventory-snapshots",
    response_model=InventoryOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an inventory snapshot",
)
async def create_inventory(
    body: InventoryCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> InventoryOut:
    """Create stock for product/location; available = quantity - reserved."""
    try:
        snapshot = await supply_chain.create_inventory(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except supply_chain.SupplyChainError as exc:
        raise _http_error(exc) from exc
    return InventoryOut.model_validate(snapshot)


@router.get(
    "/inventory-snapshots",
    response_model=list[InventoryOut],
    summary="List inventory snapshots",
)
async def list_inventory(
    db: DbSession,
    workspace_id: WorkspaceId,
    location: str | None = Query(default=None, max_length=32),
    product_id: Annotated[UUID | None, Query()] = None,
    limit: int = 50,
) -> list[InventoryOut]:
    """Return inventory snapshots, newest first."""
    rows = await supply_chain.list_inventory(
        db, workspace_id=workspace_id, location=location, product_id=product_id, limit=limit
    )
    return [InventoryOut.model_validate(row) for row in rows]


@router.put(
    "/inventory-snapshots/{inventory_id}",
    response_model=InventoryOut,
    summary="Update an inventory snapshot",
)
async def update_inventory(
    inventory_id: UUID,
    body: InventoryUpdate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> InventoryOut:
    """Adjust stock; available is recomputed when omitted."""
    try:
        snapshot = await supply_chain.update_inventory(
            db,
            workspace_id=workspace_id,
            inventory_id=inventory_id,
            data=body,
            trace_id=get_trace_id(),
        )
    except supply_chain.SupplyChainError as exc:
        raise _http_error(exc) from exc
    return InventoryOut.model_validate(snapshot)


@router.delete(
    "/inventory-snapshots/{inventory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an inventory snapshot",
)
async def delete_inventory(
    inventory_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> None:
    """Delete a snapshot (audited via event)."""
    try:
        await supply_chain.delete_inventory(
            db, workspace_id=workspace_id, inventory_id=inventory_id, trace_id=get_trace_id()
        )
    except supply_chain.SupplyChainError as exc:
        raise _http_error(exc) from exc


# --------------------------------------------------------------------------- #
# Shipments + logistics events
# --------------------------------------------------------------------------- #


@router.post(
    "/shipments",
    response_model=ShipmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a shipment record",
)
async def create_shipment(
    body: ShipmentCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ShipmentOut:
    """Record a shipment with carrier/tracking."""
    try:
        shipment = await supply_chain.create_shipment(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except supply_chain.SupplyChainError as exc:
        raise _http_error(exc) from exc
    return ShipmentOut.model_validate(shipment)


@router.get(
    "/shipments",
    response_model=list[ShipmentOut],
    summary="List shipments",
)
async def list_shipments(
    db: DbSession,
    workspace_id: WorkspaceId,
    status_filter: str | None = Query(default=None, alias="status", max_length=16),
    carrier: str | None = Query(default=None, max_length=64),
    limit: int = 50,
) -> list[ShipmentOut]:
    """Return shipments, newest first, with optional filters."""
    rows = await supply_chain.list_shipments(
        db, workspace_id=workspace_id, status=status_filter, carrier=carrier, limit=limit
    )
    return [ShipmentOut.model_validate(row) for row in rows]


@router.put(
    "/shipments/{shipment_id}",
    response_model=ShipmentOut,
    summary="Update a shipment",
)
async def update_shipment(
    shipment_id: UUID,
    body: ShipmentUpdate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ShipmentOut:
    """Update status/tracking/delay fields."""
    try:
        shipment = await supply_chain.update_shipment(
            db,
            workspace_id=workspace_id,
            shipment_id=shipment_id,
            data=body,
            trace_id=get_trace_id(),
        )
    except supply_chain.SupplyChainError as exc:
        raise _http_error(exc) from exc
    return ShipmentOut.model_validate(shipment)


@router.post(
    "/shipments/{shipment_id}/events",
    response_model=LogisticsEventOut,
    status_code=status.HTTP_201_CREATED,
    summary="Append a logistics tracking event",
)
async def add_logistics_event(
    shipment_id: UUID,
    body: LogisticsEventCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> LogisticsEventOut:
    """Append a tracking event to the shipment."""
    try:
        event = await supply_chain.add_logistics_event(
            db,
            workspace_id=workspace_id,
            shipment_id=shipment_id,
            data=body,
            trace_id=get_trace_id(),
        )
    except supply_chain.SupplyChainError as exc:
        raise _http_error(exc) from exc
    return LogisticsEventOut.model_validate(event)


@router.get(
    "/shipments/{shipment_id}/events",
    response_model=list[LogisticsEventOut],
    summary="List logistics events for a shipment",
)
async def list_logistics_events(
    shipment_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
    limit: int = 100,
) -> list[LogisticsEventOut]:
    """Return tracking events, newest first."""
    rows = await supply_chain.list_logistics_events(
        db, workspace_id=workspace_id, shipment_id=shipment_id, limit=limit
    )
    return [LogisticsEventOut.model_validate(row) for row in rows]


@router.delete(
    "/shipments/{shipment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a shipment",
)
async def delete_shipment(
    shipment_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> None:
    """Delete a shipment (audited via event)."""
    try:
        await supply_chain.delete_shipment(
            db, workspace_id=workspace_id, shipment_id=shipment_id, trace_id=get_trace_id()
        )
    except supply_chain.SupplyChainError as exc:
        raise _http_error(exc) from exc


# --------------------------------------------------------------------------- #
# Supply chain knowledge memory
# --------------------------------------------------------------------------- #


@router.post(
    "/supply-chain-knowledge-entries",
    response_model=SupplyChainKnowledgeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a supply chain knowledge entry",
)
async def create_knowledge_entry(
    body: SupplyChainKnowledgeCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> SupplyChainKnowledgeOut:
    """Record a supplier/logistics/delay/quality/risk pattern."""
    try:
        entry = await supply_chain.create_knowledge_entry(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except supply_chain.SupplyChainError as exc:
        raise _http_error(exc) from exc
    return SupplyChainKnowledgeOut.model_validate(entry)


@router.get(
    "/supply-chain-knowledge-entries",
    response_model=list[SupplyChainKnowledgeOut],
    summary="Query supply chain knowledge entries",
)
async def list_knowledge_entries(
    db: DbSession,
    workspace_id: WorkspaceId,
    category: str | None = Query(default=None, max_length=64),
    entry_type: str | None = Query(default=None, max_length=32),
    supplier_id: Annotated[UUID | None, Query()] = None,
    product_id: Annotated[UUID | None, Query()] = None,
    limit: int = 100,
) -> list[SupplyChainKnowledgeOut]:
    """Return matching entries, newest first."""
    rows = await supply_chain.list_knowledge_entries(
        db,
        workspace_id=workspace_id,
        category=category,
        entry_type=entry_type,
        supplier_id=supplier_id,
        product_id=product_id,
        limit=limit,
    )
    return [SupplyChainKnowledgeOut.model_validate(row) for row in rows]
