"""Tests for the M5.5 Alert Scheduler.

Covers the scheduler lifecycle (start/stop/disabled), interval ticks,
per-workspace exception isolation, workspace/agent scope, event auditing
(``agent.alert.scheduler_run``) and alert dedup (no duplicate active alerts).
The scheduler only opens alerts - it never auto-resolves or auto-executes.
"""

import asyncio
from uuid import UUID

import pytest
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.agent_operations import AgentAlert
from app.models.event import EventLog
from app.models.workspace import Workspace
from app.services import alert_scheduler, alert_service, task_queue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

WORKSPACE = DEFAULT_WORKSPACE_ID
OTHER_WORKSPACE = UUID("00000000-0000-0000-0000-000000000099")


async def _seed_workspace(db_session, workspace_id: UUID) -> None:
    row = await db_session.get(Workspace, str(workspace_id))
    if row is None:
        db_session.add(
            Workspace(
                id=str(workspace_id),
                name=f"ws-{workspace_id}",
                code=f"WS_{str(workspace_id)[-4:]}",
                market="US",
                currency="USD",
            )
        )
        await db_session.flush()


async def _count_events(db_session, event_type: str, workspace_id: UUID) -> int:
    rows = (
        (
            await db_session.execute(
                select(EventLog).where(
                    EventLog.workspace_id == workspace_id,
                    EventLog.event_type == event_type,
                )
            )
        )
        .scalars()
        .all()
    )
    return len(list(rows))


async def _force_alert(
    db_session, *, workspace_id: UUID, alert_type: str = "queue_backlog"
) -> None:
    """Open one alert directly so dedup behavior can be asserted."""
    await alert_service.open_alert(
        db_session,
        workspace_id=workspace_id,
        agent_id=None,
        alert_type=alert_type,
        severity="warning",
        resource="queue",
        message="test alert",
        trace_id="test",
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_run_once_records_scheduler_event(db_engine, db_session) -> None:
    """One pass writes ``agent.alert.scheduler_run`` for each workspace."""
    await _seed_workspace(db_session, WORKSPACE)
    await db_session.commit()
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    scheduler = alert_scheduler.AlertScheduler(
        session_factory=factory,
        backend=task_queue.get_queue_backend(),
        workspace_ids=[str(WORKSPACE)],
    )
    results = await scheduler.run_once(trace_id="trace-sched-1")
    assert len(results) == 1
    assert results[0].workspace_id == str(WORKSPACE)
    assert results[0].error is None
    assert await _count_events(db_session, "agent.alert.scheduler_run", WORKSPACE) == 1


@pytest.mark.asyncio
async def test_run_once_workspace_scope_limits_workspaces(db_engine, db_session) -> None:
    """Only the configured workspace ids are evaluated."""
    await _seed_workspace(db_session, WORKSPACE)
    await _seed_workspace(db_session, OTHER_WORKSPACE)
    await db_session.commit()
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    scheduler = alert_scheduler.AlertScheduler(
        session_factory=factory,
        backend=task_queue.get_queue_backend(),
        workspace_ids=[str(OTHER_WORKSPACE)],
    )
    results = await scheduler.run_once(trace_id="trace-sched-2")
    assert [r.workspace_id for r in results] == [str(OTHER_WORKSPACE)]


@pytest.mark.asyncio
async def test_run_once_agent_scope_is_forwarded(db_engine, db_session, monkeypatch) -> None:
    """The agent scope is passed through to ``evaluate_alerts``."""
    await _seed_workspace(db_session, WORKSPACE)
    await db_session.commit()
    captured: dict = {}

    async def fake_evaluate(session, backend, *, workspace_id, agent_ids=None, trace_id=None):
        captured["agent_ids"] = agent_ids
        captured["workspace_id"] = workspace_id
        return []

    monkeypatch.setattr(alert_service, "evaluate_alerts", fake_evaluate)
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    scheduler = alert_scheduler.AlertScheduler(
        session_factory=factory,
        backend=task_queue.get_queue_backend(),
        workspace_ids=[str(WORKSPACE)],
        agent_ids=["product_analyst"],
    )
    await scheduler.run_once(trace_id="trace-sched-3")
    assert captured["agent_ids"] == ["product_analyst"]
    assert str(captured["workspace_id"]) == str(WORKSPACE)


@pytest.mark.asyncio
async def test_exception_isolation_keeps_other_workspaces(
    db_engine, db_session, monkeypatch
) -> None:
    """A failing workspace must not take down the other evaluations."""
    await _seed_workspace(db_session, WORKSPACE)
    await _seed_workspace(db_session, OTHER_WORKSPACE)
    await db_session.commit()
    failing = {"hit": False}

    async def flaky_evaluate(session, backend, *, workspace_id, agent_ids=None, trace_id=None):
        if str(workspace_id) == str(OTHER_WORKSPACE):
            failing["hit"] = True
            raise RuntimeError("boom")
        return []

    monkeypatch.setattr(alert_service, "evaluate_alerts", flaky_evaluate)
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    scheduler = alert_scheduler.AlertScheduler(
        session_factory=factory,
        backend=task_queue.get_queue_backend(),
        workspace_ids=[str(WORKSPACE), str(OTHER_WORKSPACE)],
    )
    results = await scheduler.run_once(trace_id="trace-sched-4")
    by_ws = {r.workspace_id: r for r in results}
    assert by_ws[str(OTHER_WORKSPACE)].error == "boom"
    assert by_ws[str(WORKSPACE)].error is None
    assert failing["hit"] is True


@pytest.mark.asyncio
async def test_start_stop_lifecycle(db_engine, db_session) -> None:
    """start() spawns the loop; stop() joins it gracefully."""
    await _seed_workspace(db_session, WORKSPACE)
    await db_session.commit()
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    scheduler = alert_scheduler.AlertScheduler(
        session_factory=factory,
        backend=task_queue.get_queue_backend(),
        workspace_ids=[str(WORKSPACE)],
        interval_seconds=1,
    )
    await scheduler.start()
    assert scheduler._task is not None and not scheduler._task.done()
    await asyncio.sleep(0.3)
    await scheduler.stop()
    assert scheduler._task is None
    # A second stop is a no-op (idempotent).
    await scheduler.stop()


@pytest.mark.asyncio
async def test_disabled_scheduler_does_not_start(db_engine, db_session) -> None:
    """enabled=False keeps the loop stopped."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    scheduler = alert_scheduler.AlertScheduler(
        session_factory=factory,
        backend=task_queue.get_queue_backend(),
        workspace_ids=[str(WORKSPACE)],
        enabled=False,
    )
    await scheduler.start()
    assert scheduler._task is None


@pytest.mark.asyncio
async def test_start_is_idempotent(db_engine, db_session) -> None:
    """Calling start() twice must not spawn two loops."""
    await _seed_workspace(db_session, WORKSPACE)
    await db_session.commit()
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    scheduler = alert_scheduler.AlertScheduler(
        session_factory=factory,
        backend=task_queue.get_queue_backend(),
        workspace_ids=[str(WORKSPACE)],
        interval_seconds=30,
    )
    await scheduler.start()
    first_task = scheduler._task
    await scheduler.start()
    assert scheduler._task is first_task
    await scheduler.stop()


@pytest.mark.asyncio
async def test_loop_tick_calls_run_once(db_engine, db_session, monkeypatch) -> None:
    """The resident loop evaluates on the configured interval."""
    await _seed_workspace(db_session, WORKSPACE)
    await db_session.commit()
    ticks = {"count": 0}

    async def fake_run_once(trace_id=None):
        ticks["count"] += 1
        return []

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    scheduler = alert_scheduler.AlertScheduler(
        session_factory=factory,
        backend=task_queue.get_queue_backend(),
        workspace_ids=[str(WORKSPACE)],
        interval_seconds=1,
    )
    monkeypatch.setattr(scheduler, "run_once", fake_run_once)
    await scheduler.start()
    await asyncio.sleep(2.4)
    await scheduler.stop()
    assert ticks["count"] >= 2


@pytest.mark.asyncio
async def test_tick_exception_does_not_kill_loop(db_engine, db_session, monkeypatch) -> None:
    """An unexpected run_once exception is swallowed; the loop survives."""
    await _seed_workspace(db_session, WORKSPACE)
    await db_session.commit()
    ticks = {"count": 0}

    async def flaky_run_once(trace_id=None):
        ticks["count"] += 1
        if ticks["count"] == 1:
            raise RuntimeError("tick boom")
        return []

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    scheduler = alert_scheduler.AlertScheduler(
        session_factory=factory,
        backend=task_queue.get_queue_backend(),
        workspace_ids=[str(WORKSPACE)],
        interval_seconds=1,
    )
    monkeypatch.setattr(scheduler, "run_once", flaky_run_once)
    await scheduler.start()
    await asyncio.sleep(2.4)
    await scheduler.stop()
    assert ticks["count"] >= 2


@pytest.mark.asyncio
async def test_run_once_does_not_duplicate_active_alert(db_engine, db_session) -> None:
    """Repeated passes never open a second alert for the same problem."""
    await _seed_workspace(db_session, WORKSPACE)
    await db_session.commit()
    await _force_alert(db_session, workspace_id=WORKSPACE)
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    scheduler = alert_scheduler.AlertScheduler(
        session_factory=factory,
        backend=task_queue.get_queue_backend(),
        workspace_ids=[str(WORKSPACE)],
    )
    # Second pass sees the active alert and must not create a duplicate.
    results = await scheduler.run_once(trace_id="trace-sched-5")
    assert results[0].alerts_created == 0
    active = (
        (
            await db_session.execute(
                select(AgentAlert).where(
                    AgentAlert.workspace_id == WORKSPACE,
                    AgentAlert.alert_type == "queue_backlog",
                    AgentAlert.status.in_(("open", "acknowledged")),
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(list(active)) == 1


@pytest.mark.asyncio
async def test_run_once_workspace_isolation(db_engine, db_session) -> None:
    """Alerts opened for one workspace never leak into another."""
    await _seed_workspace(db_session, WORKSPACE)
    await _seed_workspace(db_session, OTHER_WORKSPACE)
    await db_session.commit()
    await _force_alert(db_session, workspace_id=WORKSPACE)
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    scheduler = alert_scheduler.AlertScheduler(
        session_factory=factory,
        backend=task_queue.get_queue_backend(),
        workspace_ids=[str(WORKSPACE), str(OTHER_WORKSPACE)],
    )
    await scheduler.run_once(trace_id="trace-sched-6")
    other_alerts = (
        (
            await db_session.execute(
                select(AgentAlert).where(AgentAlert.workspace_id == OTHER_WORKSPACE)
            )
        )
        .scalars()
        .all()
    )
    assert len(list(other_alerts)) == 0
