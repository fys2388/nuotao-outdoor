"""Event log request/response schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EventCreate(BaseModel):
    """Payload for creating a new event log entry."""

    event_type: str = Field(min_length=1, max_length=128)
    entity_type: str = Field(min_length=1, max_length=64)
    entity_id: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = Field(default=None, max_length=64)


class EventOut(BaseModel):
    """Event log entry as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    workspace_id: UUID
    event_type: str
    entity_type: str
    entity_id: str
    payload: dict[str, Any]
    trace_id: str | None
    created_at: datetime


class EventListOut(BaseModel):
    """Paginated event log list."""

    items: list[EventOut]
    total: int
    limit: int
    offset: int
