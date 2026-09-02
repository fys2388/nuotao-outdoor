"""Alert Scheduler (M5.5): configurable background evaluation of alert rules.

Wraps the existing ``alert_service.evaluate_alerts()`` - the judgement logic
is never copied here. The scheduler owns only the *when* and *scope*:

- ``run_once()``: one evaluation pass over every workspace (or the configured
  ``alert_workspace_ids``), restricted to the configured ``alert_agent_ids``
  for per-agent rules. Every pass gets a fresh ``trace_id``, mirrors to
  ``event_log`` (``agent.alert.scheduler_run``), and isolates per-workspace
  exceptions so one bad workspace can never kill the loop.
- ``start()`` / ``stop()``: a resident asyncio loop with graceful shutdown.
  ``stop()`` never cancels an in-flight evaluation mid-way; it signals and
  joins. Exceptions inside a tick are swallowed and logged - the loop always
  survives.

No business agent, no auto-executed business action and no auto-resolve live
here; the scheduler only opens alerts when thresholds trip (same semantics as
``evaluate_alerts``).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.tracing import new_trace_id
from app.models.workspace import Workspace
from app.services import alert_service, event_service, task_queue

logger = logging.getLogger(__name__)

EVENT_SCHEDULER_RUN = "agent.alert.scheduler_run"


@dataclass
class SchedulerRunResult:
    """Summary of one evaluation pass (per workspace)."""

    workspace_id: str
    alerts_created: int = 0
    error: str | None = None


@dataclass
class AlertScheduler:
    """Resident alert evaluation loop with graceful start/stop.

    ``session_factory`` is the async session maker; ``backend`` may be left
    as ``None`` to use the configured queue backend. Scope comes from the
    settings (``alert_workspace_ids`` / ``alert_agent_ids``) and can be
    overridden per instance for tests.
    """

    session_factory: async_sessionmaker
    backend: task_queue.TaskQueueBackend | None = None
    interval_seconds: int | None = None
    workspace_ids: list[str] | None = None
    agent_ids: list[str] | None = None
    enabled: bool | None = None
    _task: asyncio.Task | None = field(default=None, init=False, repr=False)
    _stop: asyncio.Event | None = field(default=None, init=False, repr=False)

    def _resolve_settings(self) -> None:
        settings = get_settings()
        if self.enabled is None:
            self.enabled = settings.agent_alert_scheduler_enabled
        if self.interval_seconds is None:
            self.interval_seconds = settings.agent_alert_interval_seconds
        if self.workspace_ids is None:
            self.workspace_ids = list(settings.alert_workspace_ids)
        if self.agent_ids is None:
            self.agent_ids = list(settings.alert_agent_ids)

    async def _workspace_scope(self, session: AsyncSession) -> list[str]:
        """Return the workspace ids to evaluate (config override or all)."""
        if self.workspace_ids:
            return list(self.workspace_ids)
        rows = (await session.execute(select(Workspace.id))).scalars().all()
        return [str(row) for row in rows]

    async def run_once(self, *, trace_id: str | None = None) -> list[SchedulerRunResult]:
        """Run one evaluation pass; never raises (per-workspace isolation)."""
        self._resolve_settings()
        trace_id = trace_id or new_trace_id()
        backend = self.backend or task_queue.get_queue_backend()
        results: list[SchedulerRunResult] = []
        async with self.session_factory() as session:
            for workspace_id in await self._workspace_scope(session):
                result = SchedulerRunResult(workspace_id=str(workspace_id))
                try:
                    created = await alert_service.evaluate_alerts(
                        session,
                        backend,
                        workspace_id=UUID(str(workspace_id)),
                        agent_ids=self.agent_ids,
                        trace_id=trace_id,
                    )
                    result.alerts_created = len(created)
                    await event_service.create_event(
                        session,
                        workspace_id=UUID(str(workspace_id)),
                        event_type=EVENT_SCHEDULER_RUN,
                        entity_type="agent_alert",
                        entity_id="*",
                        payload={
                            "alerts_created": len(created),
                            "agent_scope": self.agent_ids or [],
                        },
                        trace_id=trace_id,
                    )
                except Exception as exc:
                    # never take the scheduler down.
                    result.error = str(exc)
                    logger.exception(
                        "alert scheduler workspace %s failed (trace=%s)",
                        workspace_id,
                        trace_id,
                    )
                    await session.rollback()
                results.append(result)
        logger.info(
            "alert scheduler pass done trace=%s workspaces=%d",
            trace_id,
            len(results),
        )
        return results

    async def start(self) -> None:
        """Start the resident loop unless disabled (idempotent)."""
        self._resolve_settings()
        if not self.enabled:
            logger.info("alert scheduler disabled - not starting")
            return
        if self._task is not None and not self._task.done():
            logger.info("alert scheduler already running")
            return
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._loop(), name="agent-alert-scheduler")
        logger.info(
            "alert scheduler started (interval=%ss, workspaces=%s, agents=%s)",
            self.interval_seconds,
            self.workspace_ids or "all",
            self.agent_ids or "all",
        )

    async def _loop(self) -> None:
        """Run ``run_once`` every interval until stop is requested."""
        assert self._stop is not None
        try:
            while not self._stop.is_set():
                try:
                    await self.run_once()
                except Exception:
                    logger.exception("alert scheduler tick failed")
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.interval_seconds)
                except TimeoutError:
                    continue
        except asyncio.CancelledError:
            logger.info("alert scheduler task cancelled")
            raise

    async def stop(self) -> None:
        """Signal the loop to stop and join it (graceful shutdown)."""
        if self._stop is not None:
            self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=float(self.interval_seconds or 10) + 5)
            except (TimeoutError, asyncio.CancelledError):
                self._task.cancel()
                try:
                    await self._task
                except (asyncio.CancelledError, Exception):
                    logger.debug("alert scheduler task joined after cancel")
            self._task = None
            self._stop = None
        logger.info("alert scheduler stopped")
