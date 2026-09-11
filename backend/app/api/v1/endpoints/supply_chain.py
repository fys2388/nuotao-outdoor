"""Supply chain intelligence endpoints (M4.1): suppliers, POs, inventory, logistics, knowledge.

Data capture + lifecycle only. No Supply Chain Agent, no automatic purchasing.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
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
    SupplierCreate,
    SupplierOut,
    SupplierProfileCreate,
    SupplierUpdate,
    SupplierProfileOut,
    SupplierProfileUpdate,
    SupplyChainKnowledgeCreate,
    SupplyChainKnowledgeOut,
)
from app.models.supplier import Supplier
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
# Suppliers (master data)
# --------------------------------------------------------------------------- #


@router.post(
    "/suppliers",
    response_model=SupplierOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a supplier",
)
async def create_supplier(
    body: SupplierCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> SupplierOut:
    try:
        supplier = await supply_chain.create_supplier(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except supply_chain.SupplyChainError as exc:
        raise _http_error(exc) from exc
    return SupplierOut.model_validate(supplier)


@router.get(
    "/suppliers",
    response_model=list[SupplierOut],
    summary="List suppliers",
)
async def list_suppliers(
    db: DbSession,
    workspace_id: WorkspaceId,
    status: str | None = Query(default=None, max_length=16),
    platform: str | None = Query(default=None, max_length=32),
    search: str | None = Query(default=None, max_length=100),
    limit: int = 50,
) -> list[SupplierOut]:
    rows = await supply_chain.list_suppliers(
        db, workspace_id=workspace_id, status=status, platform=platform, search=search, limit=limit
    )
    return [SupplierOut.model_validate(row) for row in rows]


@router.get(
    "/suppliers/{supplier_id}",
    response_model=SupplierOut,
    summary="Get a supplier",
)
async def get_supplier(
    supplier_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> SupplierOut:
    try:
        supplier = await supply_chain.get_supplier(db, workspace_id=workspace_id, supplier_id=supplier_id)
    except supply_chain.SupplyChainError as exc:
        raise _http_error(exc) from exc
    return SupplierOut.model_validate(supplier)


@router.put(
    "/suppliers/{supplier_id}",
    response_model=SupplierOut,
    summary="Update a supplier",
)
async def update_supplier(
    supplier_id: UUID,
    body: SupplierUpdate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> SupplierOut:
    try:
        supplier = await supply_chain.update_supplier(
            db, workspace_id=workspace_id, supplier_id=supplier_id, data=body, trace_id=get_trace_id()
        )
    except supply_chain.SupplyChainError as exc:
        raise _http_error(exc) from exc
    return SupplierOut.model_validate(supplier)


@router.delete(
    "/suppliers/{supplier_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a supplier",
    response_model=None,
)
async def delete_supplier(
    supplier_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> None:
    try:
        await supply_chain.delete_supplier(
            db, workspace_id=workspace_id, supplier_id=supplier_id, trace_id=get_trace_id()
        )
    except supply_chain.SupplyChainError as exc:
        raise _http_error(exc) from exc


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
    response_model=None,
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
    "/purchase-orders/{po_id}/partial-receive",
    response_model=PurchaseOrderOut,
    summary="Receive a partial batch (ordered -> partial_received)",
)
async def partial_receive_purchase_order(
    po_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> PurchaseOrderOut:
    """Move the PO to partial_received (first delivery batch arrived)."""
    try:
        purchase_order = await supply_chain.partial_receive_purchase_order(
            db, workspace_id=workspace_id, po_id=po_id, trace_id=get_trace_id()
        )
    except supply_chain.SupplyChainError as exc:
        raise _http_error(exc) from exc
    return PurchaseOrderOut.model_validate(purchase_order)


@router.post(
    "/purchase-orders/{po_id}/receive",
    response_model=PurchaseOrderOut,
    summary="Receive goods (ordered/partial_received -> received)",
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
    response_model=None,
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
    response_model=None,
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



# --------------------------------------------------------------------------- #
# Purchase order statistics
# --------------------------------------------------------------------------- #


@router.get(
    "/purchase-orders/stats",
    summary="Get purchase order statistics by supplier",
)
async def get_purchase_order_stats(
    db: DbSession,
    workspace_id: WorkspaceId,
) -> dict:
    """Return purchase order statistics grouped by supplier."""
    from app.models.supplier import Supplier
    from sqlalchemy import select, func
    
    # 查询所有供应商
    suppliers = (await db.execute(
        select(Supplier).where(Supplier.workspace_id == workspace_id)
    )).scalars().all()
    
    # 查询采购订单统计（使用原生SQL）
    result = await db.execute("""
        SELECT 
            s.id as supplier_id,
            s.code as supplier_code,
            s.name as supplier_name,
            COUNT(po.id) as order_count,
            COALESCE(SUM(po.total), 0) as total_amount,
            COUNT(CASE WHEN po.status = 'received' THEN 1 END) as received_count,
            COUNT(CASE WHEN po.status = 'shipped' THEN 1 END) as shipped_count,
            COUNT(CASE WHEN po.status = 'ordered' THEN 1 END) as ordered_count
        FROM suppliers s
        LEFT JOIN purchase_orders po ON po.supplier_id = s.id
        WHERE s.workspace_id = :workspace_id
        GROUP BY s.id, s.code, s.name
        ORDER BY total_amount DESC
    """, {"workspace_id": str(workspace_id)})
    
    rows = result.fetchall()
    
    stats = []
    for row in rows:
        stats.append({
            "supplier_id": str(row[0]),
            "supplier_code": row[1],
            "supplier_name": row[2],
            "order_count": row[3],
            "total_amount": float(row[4]) if row[4] else 0,
            "received_count": row[5],
            "shipped_count": row[6],
            "ordered_count": row[7],
        })
    
    return {
        "total_suppliers": len(suppliers),
        "total_orders": sum(s["order_count"] for s in stats),
        "total_amount": sum(s["total_amount"] for s in stats),
        "by_supplier": stats,
    }



@router.post(
    "/purchase-orders",
    summary="Create a new purchase order",
)
async def create_purchase_order(
    db: DbSession,
    workspace_id: WorkspaceId,
    body: dict = Body(...),
) -> dict:
    """Create a new purchase order."""
    from sqlalchemy import text
    from uuid import uuid4
    from datetime import datetime
    
    try:
        po_id = str(uuid4())
        po_number = body.get("po_number") or f"PO-{datetime.now().strftime('%Y%m%d')}-{uuid4().hex[:4].upper()}"
        supplier_id = body.get("supplier_id")
        status = body.get("status", "pending")
        currency = body.get("currency", "CNY")
        subtotal = float(body.get("subtotal", 0))
        shipping_cost = float(body.get("shipping_cost", 0))
        total = float(body.get("total", subtotal + shipping_cost))
        expected_delivery_at = body.get("expected_delivery_at")
        notes = body.get("notes", "")
        
        await db.execute(text("""
            INSERT INTO purchase_orders 
            (id, workspace_id, po_number, supplier_id, status, currency, 
             subtotal, shipping_cost, total, expected_delivery_at, notes, created_at, updated_at)
            VALUES (:id, :workspace_id, :po_number, :supplier_id, :status, :currency,
                    :subtotal, :shipping_cost, :total, :expected_delivery_at, :notes, NOW(), NOW())
        """), {
            "id": po_id,
            "workspace_id": str(workspace_id),
            "po_number": po_number,
            "supplier_id": supplier_id,
            "status": status,
            "currency": currency,
            "subtotal": subtotal,
            "shipping_cost": shipping_cost,
            "total": total,
            "expected_delivery_at": expected_delivery_at,
            "notes": notes,
        })
        await db.commit()
        
        return {
            "success": True,
            "id": po_id,
            "po_number": po_number,
            "message": "采购订单创建成功",
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建采购订单失败: {str(e)}",
        )



@router.patch(
    "/purchase-orders/{po_id}/status",
    summary="Update purchase order status",
)
async def update_purchase_order_status(
    po_id: str,
    db: DbSession,
    workspace_id: WorkspaceId,
    body: dict = Body(...),
) -> dict:
    """Update purchase order status (pending -> ordered -> shipped -> received)."""
    from sqlalchemy import text
    
    valid_statuses = ["pending", "ordered", "shipped", "received", "completed", "cancelled"]
    new_status = body.get("status")
    
    if not new_status or new_status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的状态: {new_status}，有效状态: {', '.join(valid_statuses)}",
        )
    
    try:
        # 更新状态
        update_fields = "status = :status, updated_at = NOW()"
        params = {"status": new_status, "id": po_id, "workspace_id": str(workspace_id)}
        
        # 如果状态变为received，设置received_at
        if new_status == "received":
            update_fields += ", received_at = NOW()"
        
        result = await db.execute(text(f"""
            UPDATE purchase_orders 
            SET {update_fields}
            WHERE id = :id AND workspace_id = :workspace_id
            RETURNING po_number, status
        """), params)
        await db.commit()
        
        row = result.fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="采购订单不存在",
            )
        
        return {
            "success": True,
            "po_number": row[0],
            "status": row[1],
            "message": f"状态已更新为: {new_status}",
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新状态失败: {str(e)}",
        )
