"""Connector framework (M4.3): unified external data sync interface.

Every connector implements the four-method contract used by the connector
service: ``validate()`` (config/source checks), ``transform()`` (pure raw ->
normalized), ``sync()`` (fetch + transform + persist) and ``audit()``
(connector_runs + event_log). Data flows one way: external systems are read,
records are written through the same workspace/trace/event discipline as the
rest of the OS. **No automatic business actions.**
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


class ConnectorError(Exception):
    """Raised when a connector cannot complete a synchronization."""


@dataclass
class SyncSummary:
    """Result of one connector sync (JSON-safe counts)."""

    records_count: int = 0
    created_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0

    def as_dict(self) -> dict[str, int]:
        """Return the summary as a plain dict for audit payloads."""
        return {
            "records_count": self.records_count,
            "created_count": self.created_count,
            "updated_count": self.updated_count,
            "skipped_count": self.skipped_count,
        }


class Connector(ABC):
    """Base connector contract: validate / transform / sync / audit."""

    name: str = "base"

    @abstractmethod
    def validate(self, source: Any) -> list[str]:
        """Return source/config validation issues (empty list = valid)."""

    @abstractmethod
    def transform(self, raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Pure transform: raw external records -> normalized dicts."""

    @abstractmethod
    async def sync(
        self,
        session: AsyncSession,
        *,
        workspace_id: UUID,
        source: Any,
        trace_id: str | None,
    ) -> SyncSummary:
        """Fetch from source, transform and persist records."""

    async def audit(
        self,
        session: AsyncSession,
        *,
        workspace_id: UUID,
        run,
        trace_id: str | None,
    ) -> None:
        """Persist the audit trail for a completed run (run + event)."""
        from app.services import event_service

        await event_service.create_event(
            session,
            workspace_id=workspace_id,
            event_type="connector.run_completed",
            entity_type="connector",
            entity_id=self.name,
            payload={
                "run_id": str(run.id),
                "status": run.status,
                "records_count": run.records_count,
                "error_message": run.error_message,
            },
            trace_id=trace_id,
        )
