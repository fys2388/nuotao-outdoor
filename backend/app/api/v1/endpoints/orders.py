"""Order query API endpoints."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.workspace import get_workspace_id
from app.schemas.order import OrderDetailOut, OrderListOut, OrderOut
from app.services import order_service

router = APIRouter(prefix="/orders", tags=["orders"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]


def _parse_datetime(value: str | None, field: str) -> datetime | None:
    """Parse an ISO-8601 datetime query parameter."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field} must be ISO-8601 datetime",
        ) from exc


@router.get("", response_model=OrderListOut, summary="List orders")
async def list_orders(
    db: DbSession,
    workspace_id: WorkspaceId,
    order_status: str | None = Query(default=None, alias="status", max_length=24),
    external_order_id: str | None = Query(default=None, max_length=64),
    sku: str | None = Query(default=None, max_length=64),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    sort_by: str = Query(default="received_at"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> OrderListOut:
    """Query orders with filters, pagination and sorting (newest first)."""
    if sort_by not in order_service.ORDER_SORT_COLUMNS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"sort_by must be one of: {', '.join(order_service.ORDER_SORT_COLUMNS)}",
        )
    rows, total = await order_service.list_orders(
        db,
        workspace_id=workspace_id,
        status_filter=order_status,
        external_order_id=external_order_id,
        sku=sku,
        date_from=_parse_datetime(date_from, "date_from"),
        date_to=_parse_datetime(date_to, "date_to"),
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )
    return OrderListOut(
        items=[OrderOut.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{order_id}", response_model=OrderDetailOut, summary="Get an order")
async def get_order(
    order_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> OrderDetailOut:
    """Return one order including its line items."""
    order = await order_service.get_order(
        db, workspace_id=workspace_id, order_id=order_id
    )
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="order not found"
        )
    return OrderDetailOut.model_validate(order)
