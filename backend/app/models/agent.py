"""AI agent run audit model."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AI_JSON, BIGINT_PK, Base, WorkspaceMixin


class AiAgentRun(Base, WorkspaceMixin):
    """Full audit trail of an AI agent run (input, plan, tool calls, output).

    Populated from M1.5 onwards when the first agents are implemented.
    """

    __tablename__ = "ai_agent_runs"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    agent: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    trigger: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    plan: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    tool_calls: Mapped[list[Any]] = mapped_column(AI_JSON, nullable=False, default=list)
    output: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    approval: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    cost: Mapped[Any] = mapped_column(Numeric(12, 6), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_ai_agent_runs_created", "workspace_id", text("created_at DESC")),)
