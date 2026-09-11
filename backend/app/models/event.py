"""Event log model - the system's append-only event stream."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AI_JSON, BIGINT_PK, Base, WorkspaceMixin


class EventLog(Base, WorkspaceMixin):
    """Append-only record of business events for audit and analytics."""

    __tablename__ = "event_log"

    id: Mapped[int] = mapped_column(
        BIGINT_PK,
        primary_key=True,
        autoincrement=True,
    )
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_event_log_workspace_created", "workspace_id", text("created_at DESC")),
        Index("ix_event_log_entity", "entity_type", "entity_id"),
    )
