"""Rule registry and rule execution log models."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import DateTime, Index, String, UniqueConstraint, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AI_JSON, BIGINT_PK, Base, TimestampMixin, WorkspaceMixin


class Rule(Base, TimestampMixin, WorkspaceMixin):
    """Versioned operating rule registry.

    Rules are stored in the database (never hardcoded) and evaluated by the
    rule engine. ``when_conditions`` is a structured expression tree; ``params``
    holds configurable thresholds/weights; ``then_result`` defines the outcome.
    """

    __tablename__ = "rules"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    rule_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    rule_type: Mapped[str] = mapped_column(String(16), nullable=False, default="hard")
    version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scope: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    when_conditions: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False)
    then_result: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    params: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    approval_level: Mapped[str] = mapped_column(String(8), nullable=False, default="L0")
    owner: Mapped[str | None] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        # One versioned rule row per (workspace, rule_id, version).
        UniqueConstraint(
            "workspace_id",
            "rule_id",
            "version",
            name="uq_rules_workspace_rule_version",
        ),
    )


class RuleExecutionLog(Base, WorkspaceMixin):
    """Audit trail for every rule evaluation and override."""

    __tablename__ = "rule_execution_logs"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    rule_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(16), nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_rule_execution_created", "workspace_id", text("created_at DESC")),
    )
