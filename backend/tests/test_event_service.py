"""Tests for the event log service."""

import pytest
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.services import event_service

WORKSPACE = DEFAULT_WORKSPACE_ID


@pytest.mark.asyncio
async def test_create_event_roundtrip(db_session) -> None:
    """A created event is persisted and returned by a plain query."""
    event = await event_service.create_event(
        db_session,
        workspace_id=WORKSPACE,
        event_type="order.created",
        entity_type="order",
        entity_id="ord-1",
        payload={"total": 49.99},
        trace_id="trace-1",
    )
    assert event.id is not None
    assert event.payload == {"total": 49.99}

    rows, total = await event_service.query_events(
        db_session, workspace_id=WORKSPACE
    )
    assert total == 1
    assert rows[0].entity_id == "ord-1"
    assert rows[0].trace_id == "trace-1"


@pytest.mark.asyncio
async def test_query_events_filters(db_session) -> None:
    """Event queries support type/entity filters."""
    await event_service.create_event(
        db_session,
        workspace_id=WORKSPACE,
        event_type="order.created",
        entity_type="order",
        entity_id="ord-1",
    )
    await event_service.create_event(
        db_session,
        workspace_id=WORKSPACE,
        event_type="product.created",
        entity_type="product",
        entity_id="prod-1",
    )

    rows, total = await event_service.query_events(
        db_session,
        workspace_id=WORKSPACE,
        event_type="product.created",
    )
    assert total == 1
    assert rows[0].entity_type == "product"

    rows, total = await event_service.query_events(
        db_session,
        workspace_id=WORKSPACE,
        entity_type="order",
        entity_id="ord-1",
    )
    assert total == 1
    assert rows[0].event_type == "order.created"


@pytest.mark.asyncio
async def test_query_events_pagination(db_session) -> None:
    """Event queries paginate newest-first."""
    for i in range(5):
        await event_service.create_event(
            db_session,
            workspace_id=WORKSPACE,
            event_type="test.event",
            entity_type="test",
            entity_id=f"e-{i}",
        )

    first_page, total = await event_service.query_events(
        db_session, workspace_id=WORKSPACE, limit=2, offset=0
    )
    assert total == 5
    assert [row.entity_id for row in first_page] == ["e-4", "e-3"]

    last_page, _ = await event_service.query_events(
        db_session, workspace_id=WORKSPACE, limit=2, offset=4
    )
    assert [row.entity_id for row in last_page] == ["e-0"]
