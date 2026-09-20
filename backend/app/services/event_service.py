"""Event log service: the system's append-only event stream."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import EventLog


async def create_event(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    event_type: str,
    entity_type: str,
    entity_id: str,
    payload: dict | None = None,
    trace_id: str | None = None,
    commit: bool = True,
) -> EventLog:
    """Append an event to the event log.

    Events are the source of truth for audit and downstream analytics, so
    every business state change should publish one.

    ``commit=False`` keeps the event in the caller's transaction. Use it when
    the event must be atomic with the business fact that produced it.
    """
    event = EventLog(
        workspace_id=workspace_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload or {},
        trace_id=trace_id,
    )
    session.add(event)
    if commit:
        await session.commit()
        await session.refresh(event)
    else:
        await session.flush()
    return event


async def query_events(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    event_type: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[Sequence[EventLog], int]:
    """Query events for a workspace with optional filters and pagination.

    Returns ``(rows, total_count)`` ordered newest first.
    """
    filters = [EventLog.workspace_id == workspace_id]
    if event_type is not None:
        filters.append(EventLog.event_type == event_type)
    if entity_type is not None:
        filters.append(EventLog.entity_type == entity_type)
    if entity_id is not None:
        filters.append(EventLog.entity_id == entity_id)

    count_stmt = select(func.count()).select_from(EventLog).where(*filters)
    total = (await session.execute(count_stmt)).scalar_one()

    stmt = select(EventLog).where(*filters).order_by(EventLog.id.desc()).limit(limit).offset(offset)
    rows = (await session.execute(stmt)).scalars().all()
    return rows, total
