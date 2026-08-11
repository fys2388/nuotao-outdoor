"""Event log API endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.workspace import get_workspace_id
from app.schemas.event import EventCreate, EventListOut, EventOut
from app.services import event_service

router = APIRouter(prefix="/events", tags=["events"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]


@router.post("", response_model=EventOut, status_code=201, summary="Create an event")
async def create_event(
    body: EventCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> EventOut:
    """Append an event to the workspace event log."""
    event = await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type=body.event_type,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        payload=body.payload,
        trace_id=body.trace_id,
    )
    return EventOut.model_validate(event)


@router.get("", response_model=EventListOut, summary="Query events")
async def list_events(
    db: DbSession,
    workspace_id: WorkspaceId,
    event_type: str | None = Query(default=None, max_length=128),
    entity_type: str | None = Query(default=None, max_length=64),
    entity_id: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> EventListOut:
    """Query events with optional filters, newest first."""
    rows, total = await event_service.query_events(
        db,
        workspace_id=workspace_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
        offset=offset,
    )
    return EventListOut(
        items=[EventOut.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
