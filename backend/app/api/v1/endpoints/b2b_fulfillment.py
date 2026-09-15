"""Internal APIs for B2B order fulfillment, WMS reservation, and TMS shipping."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import (
    get_current_user,
    get_current_workspace_id,
    require_role,
)
from app.core.database import get_db
from app.core.tracing import get_trace_id
from app.models.b2b_fulfillment import B2BFulfillment
from app.schemas.b2b_fulfillment import (
    B2BFulfillmentDeliverRequest,
    B2BFulfillmentItemResponse,
    B2BFulfillmentLookupResponse,
    B2BFulfillmentReleaseRequest,
    B2BFulfillmentReserveRequest,
    B2BFulfillmentResponse,
    B2BFulfillmentShipRequest,
)
from app.schemas.user import UserResponse
from app.services import b2b_fulfillment_service

router = APIRouter(prefix="/admin/b2b", tags=["admin-b2b-fulfillment"])
WorkspaceId = UUID
FulfillmentOperator = Annotated[UserResponse, Depends(require_role("operator"))]


def _actor(user: UserResponse) -> str:
    return user.email or user.username


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, b2b_fulfillment_service.B2BFulfillmentNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, b2b_fulfillment_service.B2BFulfillmentStateError):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


def _response(fulfillment: B2BFulfillment) -> B2BFulfillmentResponse:
    return B2BFulfillmentResponse(
        id=str(fulfillment.id),
        fulfillment_number=fulfillment.fulfillment_number,
        order_id=str(fulfillment.order_id),
        status=fulfillment.status,
        warehouse_location=fulfillment.warehouse_location,
        shipment_id=str(fulfillment.shipment_id) if fulfillment.shipment_id else None,
        reserved_at=fulfillment.reserved_at,
        shipped_at=fulfillment.shipped_at,
        delivered_at=fulfillment.delivered_at,
        released_at=fulfillment.released_at,
        release_reason=fulfillment.release_reason,
        created_by=fulfillment.created_by,
        items=[
            B2BFulfillmentItemResponse(
                id=str(item.id),
                order_item_id=str(item.order_item_id),
                product_id=str(item.product_id),
                inventory_snapshot_id=str(item.inventory_snapshot_id),
                quantity=item.quantity,
                reserved_quantity=item.reserved_quantity,
                shipped_quantity=item.shipped_quantity,
                released_quantity=item.released_quantity,
            )
            for item in fulfillment.items
        ],
        created_at=fulfillment.created_at,
        updated_at=fulfillment.updated_at,
    )


@router.get(
    "/orders/{order_id}/fulfillment",
    response_model=B2BFulfillmentLookupResponse,
)
async def get_b2b_order_fulfillment(
    order_id: str,
    current_user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BFulfillmentLookupResponse:
    """Return the order fulfillment, or null before inventory is reserved."""
    try:
        fulfillment = await b2b_fulfillment_service.get_order_fulfillment(
            db,
            workspace_id=workspace_id,
            order_id=order_id,
        )
    except (ValueError, b2b_fulfillment_service.B2BFulfillmentError) as exc:
        raise _http_error(exc) from exc
    return B2BFulfillmentLookupResponse(
        fulfillment=_response(fulfillment) if fulfillment else None
    )


@router.post(
    "/orders/{order_id}/fulfillment/reserve",
    response_model=B2BFulfillmentResponse,
    status_code=201,
)
async def reserve_b2b_order_inventory(
    order_id: str,
    body: B2BFulfillmentReserveRequest,
    current_user: FulfillmentOperator,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BFulfillmentResponse:
    """Reserve all order lines and move the order to processing."""
    try:
        fulfillment = await b2b_fulfillment_service.reserve_b2b_order_inventory(
            db,
            workspace_id=workspace_id,
            order_id=order_id,
            warehouse_location=body.warehouse_location,
            actor=_actor(current_user),
            reservation_key=body.reservation_key,
            trace_id=get_trace_id(),
        )
        await db.commit()
    except b2b_fulfillment_service.B2BFulfillmentError as exc:
        await db.rollback()
        raise _http_error(exc) from exc
    return _response(fulfillment)


@router.post(
    "/orders/{order_id}/fulfillment/release",
    response_model=B2BFulfillmentResponse,
)
async def release_b2b_order_inventory(
    order_id: str,
    body: B2BFulfillmentReleaseRequest,
    current_user: FulfillmentOperator,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BFulfillmentResponse:
    """Release unshipped reserved stock and return the order to confirmed."""
    try:
        fulfillment = await b2b_fulfillment_service.release_b2b_order_inventory(
            db,
            workspace_id=workspace_id,
            order_id=order_id,
            actor=_actor(current_user),
            reason=body.reason,
            trace_id=get_trace_id(),
        )
        await db.commit()
    except b2b_fulfillment_service.B2BFulfillmentError as exc:
        await db.rollback()
        raise _http_error(exc) from exc
    return _response(fulfillment)


@router.post(
    "/orders/{order_id}/fulfillment/ship",
    response_model=B2BFulfillmentResponse,
)
async def ship_b2b_order(
    order_id: str,
    body: B2BFulfillmentShipRequest,
    current_user: FulfillmentOperator,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BFulfillmentResponse:
    """Consume reserved stock, create a TMS shipment, and mark the order shipped."""
    try:
        fulfillment = await b2b_fulfillment_service.ship_b2b_order(
            db,
            workspace_id=workspace_id,
            order_id=order_id,
            carrier=body.carrier,
            tracking_number=body.tracking_number,
            actor=_actor(current_user),
            origin=body.origin,
            destination=body.destination,
            ship_date=body.ship_date,
            shipment_key=body.shipment_key,
            trace_id=get_trace_id(),
        )
        await db.commit()
    except b2b_fulfillment_service.B2BFulfillmentError as exc:
        await db.rollback()
        raise _http_error(exc) from exc
    return _response(fulfillment)


@router.post(
    "/orders/{order_id}/fulfillment/deliver",
    response_model=B2BFulfillmentResponse,
)
async def deliver_b2b_order(
    order_id: str,
    body: B2BFulfillmentDeliverRequest,
    current_user: FulfillmentOperator,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BFulfillmentResponse:
    """Mark the linked shipment delivered and synchronize the order status."""
    try:
        fulfillment = await b2b_fulfillment_service.deliver_b2b_order(
            db,
            workspace_id=workspace_id,
            order_id=order_id,
            actor=_actor(current_user),
            occurred_at=body.occurred_at,
            trace_id=get_trace_id(),
        )
        await db.commit()
    except b2b_fulfillment_service.B2BFulfillmentError as exc:
        await db.rollback()
        raise _http_error(exc) from exc
    return _response(fulfillment)
