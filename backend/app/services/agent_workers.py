"""Agent worker registry and heartbeat (M5.3).

Worker state lives in Redis hashes (``worker_registry_prefix:<worker_id>``)
with a TTL, so crashed workers expire naturally and no database table is
needed. Each heartbeat refreshes the TTL; a worker is considered ``dead``
when ``now - last_heartbeat_at > worker_heartbeat_timeout_seconds``
(config-driven, never hardcoded).

Statuses: ``starting`` / ``idle`` / ``busy`` / ``stopping`` (``dead`` is a
derived status returned by :func:`list_workers`).

Workers are infrastructure (like the queue itself), not business data: the
registry is global, not workspace-scoped. All state changes are mirrored to
``event_log`` (``agent.queue.worker_*``) with a trace id.
"""

from __future__ import annotations

import logging
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.services import event_service, task_queue

logger = logging.getLogger(__name__)

# Worker lifecycle statuses (``dead`` is derived, never stored).
WORKER_STARTING = "starting"
WORKER_IDLE = "idle"
WORKER_BUSY = "busy"
WORKER_STOPPING = "stopping"
WORKER_DEAD = "dead"


class WorkerRegistryError(Exception):
    """Raised when a worker registry operation fails."""


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def registry_key(worker_id: str) -> str:
    """Redis hash key for one worker."""
    return f"{get_settings().worker_registry_prefix}:{worker_id}"


async def register_worker(
    backend: task_queue.TaskQueueBackend,
    *,
    worker_id: str,
    hostname: str | None = None,
    trace_id: str | None = None,
) -> None:
    """Register a worker as ``starting`` (idempotent overwrite)."""
    now = _now()
    await backend.hash_set(
        registry_key(worker_id),
        {
            "worker_id": worker_id,
            "hostname": hostname or socket.gethostname(),
            "status": WORKER_STARTING,
            "started_at": now.isoformat(),
            "last_heartbeat_at": now.isoformat(),
            "current_task_id": "",
            "current_execution_id": "",
            "processed_count": "0",
            "failed_count": "0",
        },
        ttl_seconds=_registry_ttl(),
    )
    logger.info("worker %s registered (hostname=%s)", worker_id, hostname or socket.gethostname())


async def heartbeat(
    backend: task_queue.TaskQueueBackend,
    *,
    worker_id: str,
    hostname: str | None = None,
    status: str = WORKER_IDLE,
    current_task_id: str | None = None,
    current_execution_id: str | None = None,
    processed_count: int | None = None,
    failed_count: int | None = None,
    started_at: str | None = None,
    trace_id: str | None = None,
) -> None:
    """Refresh a worker's registry entry (keeps it alive)."""
    existing = await backend.hash_get_all(registry_key(worker_id))
    if not existing:
        # Unknown worker: auto-register (keeps the API usable from tests).
        now = _now()
        existing = {
            "worker_id": worker_id,
            "hostname": hostname or socket.gethostname(),
            "status": WORKER_STARTING,
            "started_at": started_at or now.isoformat(),
            "last_heartbeat_at": now.isoformat(),
            "current_task_id": "",
            "current_execution_id": "",
            "processed_count": "0",
            "failed_count": "0",
        }
    mapping = dict(existing)
    mapping.update(
        {
            "worker_id": worker_id,
            "hostname": hostname or existing.get("hostname") or socket.gethostname(),
            "status": status,
            "last_heartbeat_at": _now().isoformat(),
            "started_at": started_at or existing.get("started_at"),
        }
    )
    # ``None`` keeps the stored value; "" explicitly clears it (idle worker).
    if current_task_id is not None:
        mapping["current_task_id"] = current_task_id or ""
    if current_execution_id is not None:
        mapping["current_execution_id"] = current_execution_id or ""
    processed = processed_count
    failed = failed_count
    if processed is not None:
        mapping["processed_count"] = str(processed)
    if failed is not None:
        mapping["failed_count"] = str(failed)
    await backend.hash_set(registry_key(worker_id), mapping, ttl_seconds=_registry_ttl())
    logger.debug("worker %s heartbeat status=%s", worker_id, status)


async def list_workers(
    backend: task_queue.TaskQueueBackend,
    *,
    heartbeat_timeout_seconds: int | None = None,
) -> list[dict[str, Any]]:
    """List live/dead workers; derives ``dead`` from heartbeat age."""
    timeout = (
        heartbeat_timeout_seconds
        if heartbeat_timeout_seconds is not None
        else get_settings().worker_heartbeat_timeout_seconds
    )
    now = _now()
    workers: list[dict[str, Any]] = []
    for key in await backend.scan_keys(f"{get_settings().worker_registry_prefix}:*"):
        row = await backend.hash_get_all(key)
        if not row:
            continue
        worker_id = row.get("worker_id") or key.rsplit(":", 1)[-1]
        last = _parse_iso(row.get("last_heartbeat_at"))
        is_dead = last is None or (now - last).total_seconds() > timeout
        workers.append(
            {
                "worker_id": worker_id,
                "hostname": row.get("hostname", ""),
                "status": WORKER_DEAD if is_dead else row.get("status", WORKER_STARTING),
                "is_dead": is_dead,
                "started_at": row.get("started_at"),
                "last_heartbeat_at": row.get("last_heartbeat_at"),
                "current_task_id": row.get("current_task_id") or None,
                "current_execution_id": row.get("current_execution_id") or None,
                "processed_count": int(row.get("processed_count", "0") or 0),
                "failed_count": int(row.get("failed_count", "0") or 0),
            }
        )
    workers.sort(key=lambda worker: worker["worker_id"])
    return workers


async def mark_stopping(
    backend: task_queue.TaskQueueBackend,
    *,
    worker_id: str,
    trace_id: str | None = None,
) -> None:
    """Mark a worker as ``stopping`` (graceful shutdown)."""
    existing = await backend.hash_get_all(registry_key(worker_id))
    mapping = dict(existing) if existing else {"worker_id": worker_id}
    mapping.update(
        {
            "worker_id": worker_id,
            "status": WORKER_STOPPING,
            "last_heartbeat_at": _now().isoformat(),
        }
    )
    await backend.hash_set(registry_key(worker_id), mapping, ttl_seconds=_registry_ttl())


async def emit_worker_event(
    session: AsyncSession,
    *,
    event_type: str,
    worker_id: str,
    payload: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> None:
    """Mirror a worker state change to ``event_log`` (infra events use the
    default workspace - workers are shared infrastructure)."""
    await event_service.create_event(
        session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        event_type=event_type,
        entity_type="agent_worker",
        entity_id=worker_id,
        payload=payload or {},
        trace_id=trace_id,
    )


def _registry_ttl() -> int:
    return get_settings().worker_registry_ttl_seconds


@dataclass
class WorkerRuntime:
    """Resident-worker helper: registers, heartbeats and stops a worker.

    The resident loop creates one and calls :meth:`beat` between messages.
    Heartbeat ``event_log`` writes are throttled to
    ``worker_heartbeat_event_interval_seconds`` (config-driven).
    """

    backend: task_queue.TaskQueueBackend
    worker_id: str
    hostname: str | None = None
    trace_id: str | None = None

    def __post_init__(self) -> None:
        self.started_at = _now()
        self.processed_count = 0
        self.failed_count = 0
        self._last_event_emit: float = 0.0
        self._current_task_id: str | None = None
        self._current_execution_id: str | None = None

    async def start(self, *, session: AsyncSession | None = None) -> None:
        await register_worker(
            self.backend,
            worker_id=self.worker_id,
            hostname=self.hostname,
            trace_id=self.trace_id,
        )
        if session is not None:
            await emit_worker_event(
                session,
                event_type="agent.queue.worker_started",
                worker_id=self.worker_id,
                payload={
                    "hostname": self.hostname or socket.gethostname(),
                    "started_at": _iso(self.started_at),
                },
                trace_id=self.trace_id,
            )

    async def beat(
        self,
        *,
        status: str = WORKER_IDLE,
        current_task_id: str | None = None,
        current_execution_id: str | None = None,
        session: AsyncSession | None = None,
    ) -> None:
        if current_task_id is not None:
            self._current_task_id = current_task_id
        if current_execution_id is not None:
            self._current_execution_id = current_execution_id
        await heartbeat(
            backend=self.backend,
            worker_id=self.worker_id,
            hostname=self.hostname,
            status=status,
            current_task_id=self._current_task_id,
            current_execution_id=self._current_execution_id,
            processed_count=self.processed_count,
            failed_count=self.failed_count,
            started_at=_iso(self.started_at),
            trace_id=self.trace_id,
        )
        # Throttled event mirror (heartbeats are frequent, events are audit).
        if session is not None:
            interval = get_settings().worker_heartbeat_event_interval_seconds
            import time as _time

            if _time.monotonic() - self._last_event_emit >= interval:
                self._last_event_emit = _time.monotonic()
                await emit_worker_event(
                    session,
                    event_type="agent.queue.worker_heartbeat",
                    worker_id=self.worker_id,
                    payload={
                        "status": status,
                        "current_task_id": self._current_task_id,
                        "current_execution_id": self._current_execution_id,
                        "processed_count": self.processed_count,
                        "failed_count": self.failed_count,
                    },
                    trace_id=self.trace_id,
                )

    async def stop(self, *, session: AsyncSession | None = None) -> None:
        await mark_stopping(self.backend, worker_id=self.worker_id, trace_id=self.trace_id)
        if session is not None:
            await emit_worker_event(
                session,
                event_type="agent.queue.worker_stopped",
                worker_id=self.worker_id,
                payload={
                    "processed_count": self.processed_count,
                    "failed_count": self.failed_count,
                },
                trace_id=self.trace_id,
            )

    async def mark_processed(self, *, session: AsyncSession | None = None) -> None:
        self.processed_count += 1
        await self.beat(
            status=WORKER_IDLE,
            current_task_id="",
            current_execution_id="",
            session=session,
        )

    async def mark_failed(self, *, session: AsyncSession | None = None) -> None:
        self.failed_count += 1
        await self.beat(
            status=WORKER_IDLE,
            current_task_id="",
            current_execution_id="",
            session=session,
        )
