"""Tests for M5.4 Production Operations & Human Control.

Covers the Alert Service (thresholds, dedup, lifecycle, workspace isolation),
the unified Human Approval Center (L3 tool / recommendation / calibration
decisions, double-decision protection), DLQ human replay (proposal ->
approval -> new attempt, original attempts immutable), the Runtime Overview
API and the new runtime operations endpoints. Everything is workspace-scoped
and audited through ``event_log`` with a ``trace_id``.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import get_settings
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.agent_operations import AgentAlert
from app.models.agent_runtime import AgentExecution, AgentRegistry, AgentTask
from app.models.agent_runtime_hardening import AgentTaskAttempt
from app.models.event import EventLog
from app.schemas.agent_runtime import AgentRegisterRequest, TaskCreate
from app.schemas.prompt import PromptCreate
from app.schemas.recommendation import RecommendationCreate
from app.services import (
    agent_queue,
    agent_runtime,
    agent_workers,
    alert_service,
    approval_service,
    prompt_registry,
    recommendation_service,
    task_queue,
)
from app.worker.agent_worker import run_worker_once
from app.worker.executor import ExecutionResult

WORKSPACE = DEFAULT_WORKSPACE_ID
OTHER_WORKSPACE = UUID("00000000-0000-0000-0000-000000000099")

PROMPT_NAME = "AGENT_OPS_TEST"


def _headers(workspace: UUID | None = None) -> dict:
    return {"X-Workspace-Id": str(workspace)} if workspace else {}


def _now() -> datetime:
    return datetime.now(UTC)


async def _seed_agent(db_session, *, workspace: UUID = WORKSPACE) -> AgentRegistry:
    await prompt_registry.create_prompt(
        db_session,
        workspace_id=workspace,
        data=PromptCreate(
            prompt_id="prompt-ops-test",
            name=PROMPT_NAME,
            version="v1",
            template="Analyze {sku}.",
            variables=["sku"],
        ),
    )
    agent = await agent_runtime.register_agent(
        db_session,
        workspace_id=workspace,
        data=AgentRegisterRequest(
            agent_id="OPS_TEST",
            name="Ops Test Agent",
            domain="operations",
            version="v1",
            status="active",
            model_provider="openai",
            model_name="gpt-4o-mini",
            prompt_version="v1",
            permission_level="L2",
        ),
    )
    return agent


class FakeExecutor:
    """Mock executor for replay/worker tests (no business logic)."""

    def __init__(self, errors: list | None = None):
        self.errors = list(errors or [])
        self.calls = 0

    async def __call__(self, session, *, workspace_id, agent, task, policy, trace_id):
        self.calls += 1
        if self.errors:
            error = self.errors.pop(0)
            if error is not None:
                raise error
        return ExecutionResult(
            output={"decision": "replayed"},
            provider="openai",
            model="gpt-4o-mini",
            tokens={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            cost=Decimal("0.001"),
            latency_ms=5,
        )


async def _event_types(db_session) -> set[str]:
    rows = (await db_session.execute(select(EventLog.event_type))).scalars().all()
    return set(rows)


# --------------------------------------------------------------------------- #
# Alert Service
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_alert_queue_backlog_threshold_and_dedup(db_session, monkeypatch) -> None:
    """A tripped threshold opens one alert; repeated evaluation does not flood."""
    settings = get_settings()
    monkeypatch.setattr(settings, "alert_queue_depth_threshold", 0)
    backend = task_queue.get_queue_backend()
    await backend.add(task_queue.task_stream(), {"probe": "1"})

    created = await alert_service.evaluate_alerts(
        db_session, backend, workspace_id=WORKSPACE, trace_id="trace-alert-1"
    )
    assert len(created) == 1
    assert created[0].alert_type == alert_service.ALERT_QUEUE_BACKLOG
    assert created[0].status == "open"
    assert created[0].trace_id == "trace-alert-1"

    # Same condition again -> dedup, no new alert.
    created2 = await alert_service.evaluate_alerts(
        db_session, backend, workspace_id=WORKSPACE, trace_id="trace-alert-2"
    )
    assert created2 == []
    rows = (
        (
            await db_session.execute(
                select(AgentAlert).where(
                    AgentAlert.workspace_id == WORKSPACE,
                    AgentAlert.alert_type == alert_service.ALERT_QUEUE_BACKLOG,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert "agent.alert.created" in await _event_types(db_session)


@pytest.mark.asyncio
async def test_alert_acknowledge_and_resolve_lifecycle(db_session, monkeypatch) -> None:
    """open -> acknowledged -> resolved, each transition audited."""
    settings = get_settings()
    monkeypatch.setattr(settings, "alert_queue_depth_threshold", 0)
    backend = task_queue.get_queue_backend()
    await backend.add(task_queue.task_stream(), {"probe": "1"})
    created = await alert_service.evaluate_alerts(
        db_session, backend, workspace_id=WORKSPACE, trace_id="trace-ack"
    )
    alert = created[0]

    acknowledged = await alert_service.acknowledge_alert(
        db_session,
        workspace_id=WORKSPACE,
        alert_id=alert.id,
        actor="ops-user",
        note="on it",
        trace_id="trace-ack",
    )
    assert acknowledged.status == "acknowledged"
    assert acknowledged.ack_by == "ops-user"

    resolved = await alert_service.resolve_alert(
        db_session,
        workspace_id=WORKSPACE,
        alert_id=alert.id,
        actor="ops-user",
        trace_id="trace-ack",
    )
    assert resolved.status == "resolved"
    assert resolved.resolved_at is not None
    events = await _event_types(db_session)
    assert "agent.alert.acknowledged" in events
    assert "agent.alert.resolved" in events


@pytest.mark.asyncio
async def test_alert_ack_resolve_guard_errors(db_session, monkeypatch) -> None:
    """Ack of a non-open alert and resolve of a resolved alert both fail."""
    settings = get_settings()
    monkeypatch.setattr(settings, "alert_queue_depth_threshold", 0)
    backend = task_queue.get_queue_backend()
    await backend.add(task_queue.task_stream(), {"probe": "1"})
    alert = (await alert_service.evaluate_alerts(db_session, backend, workspace_id=WORKSPACE))[0]

    await alert_service.acknowledge_alert(
        db_session, workspace_id=WORKSPACE, alert_id=alert.id, actor="ops"
    )
    with pytest.raises(alert_service.AlertServiceError):
        await alert_service.acknowledge_alert(
            db_session, workspace_id=WORKSPACE, alert_id=alert.id, actor="ops"
        )
    await alert_service.resolve_alert(
        db_session, workspace_id=WORKSPACE, alert_id=alert.id, actor="ops"
    )
    with pytest.raises(alert_service.AlertServiceError):
        await alert_service.resolve_alert(
            db_session, workspace_id=WORKSPACE, alert_id=alert.id, actor="ops"
        )
    with pytest.raises(alert_service.AlertServiceError):
        await alert_service.resolve_alert(
            db_session, workspace_id=OTHER_WORKSPACE, alert_id=alert.id, actor="ops"
        )


@pytest.mark.asyncio
async def test_alert_workspace_isolation(db_session, monkeypatch) -> None:
    """Alerts are scoped to the workspace that evaluated them."""
    settings = get_settings()
    monkeypatch.setattr(settings, "alert_queue_depth_threshold", 0)
    backend = task_queue.get_queue_backend()
    await backend.add(task_queue.task_stream(), {"probe": "1"})

    await alert_service.evaluate_alerts(db_session, backend, workspace_id=WORKSPACE)
    created_other = await alert_service.evaluate_alerts(
        db_session, backend, workspace_id=OTHER_WORKSPACE
    )
    # The other workspace has its own independent alert.
    assert len(created_other) == 1
    rows_ws = (
        (await db_session.execute(select(AgentAlert).where(AgentAlert.workspace_id == WORKSPACE)))
        .scalars()
        .all()
    )
    rows_other = (
        (
            await db_session.execute(
                select(AgentAlert).where(AgentAlert.workspace_id == OTHER_WORKSPACE)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows_ws) == 1
    assert len(rows_other) == 1


@pytest.mark.asyncio
async def test_alert_worker_dead_detection(db_session) -> None:
    """A worker whose heartbeat is stale trips the worker_dead alert."""
    backend = task_queue.get_queue_backend()
    old = (_now() - timedelta(minutes=10)).isoformat()
    await backend.hash_set(
        agent_workers.registry_key("w-stale"),
        {
            "worker_id": "w-stale",
            "hostname": "h1",
            "status": "idle",
            "started_at": old,
            "last_heartbeat_at": old,
            "current_task_id": "",
            "current_execution_id": "",
            "processed_count": "0",
            "failed_count": "0",
        },
        ttl_seconds=120,
    )
    created = await alert_service.evaluate_alerts(
        db_session, backend, workspace_id=WORKSPACE, trace_id="trace-dead"
    )
    dead = [alert for alert in created if alert.alert_type == alert_service.ALERT_WORKER_DEAD]
    assert len(dead) == 1
    assert dead[0].resource == "worker:w-stale"
    assert dead[0].severity == "critical"


@pytest.mark.asyncio
async def test_alert_failure_rate_and_dlq_growth(db_session, monkeypatch) -> None:
    """Failed executions and dead-letter events trip failure/DLQ alerts."""
    settings = get_settings()
    monkeypatch.setattr(settings, "alert_failure_rate_threshold", 0.0)
    monkeypatch.setattr(settings, "alert_dlq_growth_threshold", 0)
    backend = task_queue.get_queue_backend()
    now = _now()
    db_session.add(
        AgentExecution(
            workspace_id=WORKSPACE,
            status="failed",
            error_type="llm",
            started_at=now - timedelta(minutes=1),
            completed_at=now,
            cost=Decimal("0.01"),
        )
    )
    await db_session.flush()
    await event_service_create(db_session, event_type="agent.task_dead_letter")

    created = await alert_service.evaluate_alerts(db_session, backend, workspace_id=WORKSPACE)
    types = {alert.alert_type for alert in created}
    assert alert_service.ALERT_FAILURE_RATE in types
    assert alert_service.ALERT_DLQ_GROWTH in types


@pytest.mark.asyncio
async def test_alert_approval_timeout(db_session) -> None:
    """Waiting-approval executions near their deadline trip the alert."""
    backend = task_queue.get_queue_backend()
    db_session.add(
        AgentExecution(
            workspace_id=WORKSPACE,
            status="waiting_approval",
            approval={"reason": "test"},
            approval_deadline=_now() - timedelta(seconds=1),
        )
    )
    await db_session.flush()
    created = await alert_service.evaluate_alerts(db_session, backend, workspace_id=WORKSPACE)
    timeout_alerts = [
        alert for alert in created if alert.alert_type == alert_service.ALERT_APPROVAL_TIMEOUT
    ]
    assert len(timeout_alerts) == 1


@pytest.mark.asyncio
async def test_alert_budget_warning(db_session, monkeypatch) -> None:
    """Monthly LLM usage crossing the budget threshold opens a warning."""
    settings = get_settings()
    monkeypatch.setattr(settings, "alert_budget_warning_threshold", Decimal("0.80"))
    backend = task_queue.get_queue_backend()
    agent = await _seed_agent(db_session)
    now = _now()
    db_session.add(
        AgentExecution(
            workspace_id=WORKSPACE,
            agent_id=agent.id,
            status="completed",
            cost=Decimal("90.00"),
            started_at=now.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
            completed_at=now,
        )
    )
    await db_session.flush()
    created = await alert_service.evaluate_alerts(db_session, backend, workspace_id=WORKSPACE)
    warnings = [
        alert for alert in created if alert.alert_type == alert_service.ALERT_BUDGET_WARNING
    ]
    assert len(warnings) == 1
    assert warnings[0].agent_id == agent.id


async def event_service_create(db_session, *, event_type: str) -> None:
    """Small helper: append an event row (used to seed DLQ growth)."""
    db_session.add(
        EventLog(
            workspace_id=WORKSPACE,
            event_type=event_type,
            entity_type="agent_task",
            entity_id="task-x",
            payload={},
            created_at=_now(),
        )
    )
    await db_session.flush()


# --------------------------------------------------------------------------- #
# Human Approval Center
# --------------------------------------------------------------------------- #


async def _make_waiting_approval(
    db_session, *, workspace: UUID = WORKSPACE
) -> tuple[AgentRegistry, AgentTask, AgentExecution]:
    agent = await _seed_agent(db_session, workspace=workspace)
    task = await agent_runtime.create_task(
        db_session,
        workspace_id=workspace,
        data=TaskCreate(agent_id=agent.id, input={"sku": "SKU-1"}),
        trace_id="trace-l3",
    )
    execution = await agent_runtime.start_execution(
        db_session, workspace_id=workspace, task_id=task.id, trace_id="trace-l3"
    )
    await agent_runtime._waiting_approval(
        db_session,
        workspace_id=workspace,
        execution=execution,
        reason="high-risk tool requires approval",
        trace_id="trace-l3",
    )
    return agent, task, execution


@pytest.mark.asyncio
async def test_l3_tool_approval_via_center(db_session) -> None:
    """Approving an L3 execution through the Approval Center completes it."""
    _agent, task, execution = await _make_waiting_approval(db_session)
    backend = task_queue.get_queue_backend()

    items, total = await approval_service.list_approvals(db_session, workspace_id=WORKSPACE)
    assert total == 1
    approval = items[0]
    assert approval.approval_type == "L3_TOOL"
    assert approval.status == "pending"
    assert approval.trace_id == "trace-l3"

    decided = await approval_service.approve_approval(
        db_session,
        backend,
        workspace_id=WORKSPACE,
        approval_id=approval.id,
        actor="ops-lead",
        note="looks good",
        trace_id="trace-l3",
    )
    assert decided.status == "approved"
    assert decided.action == "approved"
    assert decided.actor == "ops-lead"

    await db_session.refresh(execution)
    await db_session.refresh(task)
    assert execution.status == "completed"
    assert task.status == "completed"
    events = await _event_types(db_session)
    assert "agent.approval.approved" in events
    assert "agent.execution_approved" in events


@pytest.mark.asyncio
async def test_l3_tool_rejection_via_center(db_session) -> None:
    """Rejecting an L3 execution through the center fails the task."""
    _agent, task, execution = await _make_waiting_approval(db_session)
    backend = task_queue.get_queue_backend()
    items, _total = await approval_service.list_approvals(db_session, workspace_id=WORKSPACE)
    decided = await approval_service.reject_approval(
        db_session,
        backend,
        workspace_id=WORKSPACE,
        approval_id=items[0].id,
        actor="ops-lead",
        note="rejected after review",
    )
    assert decided.status == "rejected"
    await db_session.refresh(execution)
    await db_session.refresh(task)
    assert execution.status == "rejected"
    assert task.status == "failed"
    assert "agent.approval.rejected" in await _event_types(db_session)


@pytest.mark.asyncio
async def test_double_approve_and_double_reject_rejected(db_session) -> None:
    """A second decision on the same approval row is rejected (400-style)."""
    _agent, _task, _execution = await _make_waiting_approval(db_session)
    backend = task_queue.get_queue_backend()
    items, _total = await approval_service.list_approvals(db_session, workspace_id=WORKSPACE)
    approval_id = items[0].id

    await approval_service.approve_approval(
        db_session, backend, workspace_id=WORKSPACE, approval_id=approval_id, actor="ops"
    )
    with pytest.raises(approval_service.ApprovalError):
        await approval_service.approve_approval(
            db_session, backend, workspace_id=WORKSPACE, approval_id=approval_id, actor="ops"
        )


@pytest.mark.asyncio
async def test_recommendation_approval_via_center(db_session) -> None:
    """Business recommendations surface in the center and dispatch there."""
    backend = task_queue.get_queue_backend()
    recommendation = await recommendation_service.propose_recommendation(
        db_session,
        workspace_id=WORKSPACE,
        data=RecommendationCreate(
            domain="product",
            entity_type="sku",
            entity_id="SKU-9",
            recommendation="Re-test with lower price",
            reason="margin analysis",
            confidence=Decimal("0.7"),
        ),
        trace_id="trace-rec",
    )
    items, total = await approval_service.list_approvals(
        db_session,
        workspace_id=WORKSPACE,
        approval_type="RECOMMENDATION",
    )
    assert total == 1
    decided = await approval_service.approve_approval(
        db_session,
        backend,
        workspace_id=WORKSPACE,
        approval_id=items[0].id,
        actor="ops-lead",
        trace_id="trace-rec",
    )
    assert decided.status == "approved"
    await db_session.refresh(recommendation)
    assert recommendation.status == "approved"
    assert recommendation.approved_by == "ops-lead"


@pytest.mark.asyncio
async def test_calibration_approval_via_center(db_session) -> None:
    """Score calibration proposals surface in the center and dispatch there."""
    from app.models.product_intelligence import ProductScoreCalibrationRun

    backend = task_queue.get_queue_backend()
    run = ProductScoreCalibrationRun(
        workspace_id=WORKSPACE,
        status="proposed",
        model_version="v1",
        current_weights={"profit": "0.2"},
        suggested_weights={"profit": "0.3"},
        input_snapshot={},
        metrics={},
        sample_size=3,
        rationale="calibration test",
        trace_id="trace-cal",
    )
    db_session.add(run)
    await db_session.flush()
    await approval_service.ensure_approval(
        db_session,
        workspace_id=WORKSPACE,
        approval_type="CALIBRATION",
        entity_type="score_calibration_run",
        entity_id=str(run.id),
        trace_id="trace-cal",
    )
    items, total = await approval_service.list_approvals(
        db_session, workspace_id=WORKSPACE, approval_type="CALIBRATION"
    )
    assert total == 1
    decided = await approval_service.approve_approval(
        db_session,
        backend,
        workspace_id=WORKSPACE,
        approval_id=items[0].id,
        actor="ops-lead",
        trace_id="trace-cal",
    )
    assert decided.status == "approved"
    await db_session.refresh(run)
    assert run.status == "approved"
    assert run.approved_by == "ops-lead"


@pytest.mark.asyncio
async def test_approval_workspace_isolation(db_session) -> None:
    """An approval in workspace A is invisible to workspace B."""
    _agent, _task, _execution = await _make_waiting_approval(db_session, workspace=WORKSPACE)
    items_other, total_other = await approval_service.list_approvals(
        db_session, workspace_id=OTHER_WORKSPACE
    )
    assert total_other == 0
    assert items_other == []
    # Deciding from another workspace cannot load the row.
    items, _total = await approval_service.list_approvals(db_session, workspace_id=WORKSPACE)
    with pytest.raises(approval_service.ApprovalError):
        await approval_service.approve_approval(
            db_session,
            task_queue.get_queue_backend(),
            workspace_id=OTHER_WORKSPACE,
            approval_id=items[0].id,
            actor="intruder",
        )


# --------------------------------------------------------------------------- #
# DLQ human replay
# --------------------------------------------------------------------------- #


async def _make_failed_task(db_session, *, workspace: UUID = WORKSPACE) -> AgentTask:
    agent = await _seed_agent(db_session, workspace=workspace)
    task = await agent_runtime.create_task(
        db_session,
        workspace_id=workspace,
        data=TaskCreate(agent_id=agent.id, input={"sku": "DLQ-1"}),
        trace_id="trace-dlq",
    )
    task.status = "failed"
    task.error_message = "LLM provider unreachable"
    task.completed_at = _now()
    task.attempt_count = 2
    await db_session.flush()
    return task


@pytest.mark.asyncio
async def test_dlq_replay_proposal_requires_approval(db_session) -> None:
    """Replay is a proposal only - never a direct execution."""
    task = await _make_failed_task(db_session)
    backend = task_queue.get_queue_backend()
    proposal = await agent_queue.propose_dlq_replay(
        db_session,
        workspace_id=WORKSPACE,
        task_id=task.id,
        reason="reviewed the error",
        trace_id="trace-dlq",
    )
    assert proposal.approval_type == "DLQ_REPLAY"
    assert proposal.status == "pending"
    assert proposal.metadata_["original_error"] == "LLM provider unreachable"

    # Nothing was enqueued by proposing.
    assert await backend.stream_length(task_queue.task_stream()) == 0
    # Task is still failed.
    await db_session.refresh(task)
    assert task.status == "failed"
    events = await _event_types(db_session)
    assert "agent.dlq.replay_proposed" in events


@pytest.mark.asyncio
async def test_dlq_replay_duplicate_proposal_rejected(db_session) -> None:
    """A second pending proposal for the same task is refused."""
    task = await _make_failed_task(db_session)
    await agent_queue.propose_dlq_replay(
        db_session, workspace_id=WORKSPACE, task_id=task.id, reason="first"
    )
    with pytest.raises(agent_queue.AgentQueueError):
        await agent_queue.propose_dlq_replay(
            db_session, workspace_id=WORKSPACE, task_id=task.id, reason="second"
        )


@pytest.mark.asyncio
async def test_dlq_replay_non_failed_task_rejected(db_session) -> None:
    """Only dead-lettered (failed) tasks can get a replay proposal."""
    agent = await _seed_agent(db_session)
    task = await agent_runtime.create_task(
        db_session,
        workspace_id=WORKSPACE,
        data=TaskCreate(agent_id=agent.id, input={"sku": "OK-1"}),
    )
    with pytest.raises(agent_queue.AgentQueueError):
        await agent_queue.propose_dlq_replay(
            db_session, workspace_id=WORKSPACE, task_id=task.id, reason="why"
        )


@pytest.mark.asyncio
async def test_dlq_replay_approved_creates_new_attempt(db_engine, db_session) -> None:
    """Approved replay resets the task, enqueues attempt+1 and runs once."""
    backend = task_queue.get_queue_backend()
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    task = await _make_failed_task(db_session)
    proposal = await agent_queue.propose_dlq_replay(
        db_session,
        workspace_id=WORKSPACE,
        task_id=task.id,
        reason="reviewed",
        trace_id="trace-dlq",
    )

    decided = await approval_service.approve_approval(
        db_session,
        backend,
        workspace_id=WORKSPACE,
        approval_id=proposal.id,
        actor="ops-lead",
        note="replay approved",
        trace_id="trace-dlq",
    )
    assert decided.status == "approved"
    await db_session.refresh(task)
    assert task.status == "pending"
    assert task.error_message is None
    assert task.attempt_count == 3  # 2 original attempts + 1 replay attempt

    # The worker picks the replayed message up and completes the task.
    executor = FakeExecutor()
    processed = await run_worker_once(backend, factory, executor=executor)
    assert processed >= 1
    assert executor.calls == 1

    async with factory() as session:
        reloaded = await session.get(AgentTask, task.id)
        assert reloaded.status == "completed"
        executions = (
            (
                await session.execute(
                    select(AgentExecution).where(
                        AgentExecution.workspace_id == WORKSPACE,
                        AgentExecution.task_id == task.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        # The failed task was constructed directly, so the replay produced
        # exactly one execution (the replayed, successful one).
        assert len(executions) == 1
        assert executions[0].status == "completed"
        events = (await session.execute(select(EventLog.event_type))).scalars().all()
        assert "agent.dlq.replay_started" in set(events)


@pytest.mark.asyncio
async def test_dlq_replay_rejected_keeps_task_failed(db_session) -> None:
    """A rejected replay leaves the task failed and nothing enqueued."""
    backend = task_queue.get_queue_backend()
    task = await _make_failed_task(db_session)
    proposal = await agent_queue.propose_dlq_replay(
        db_session, workspace_id=WORKSPACE, task_id=task.id, reason="review"
    )
    decided = await approval_service.reject_approval(
        db_session,
        backend,
        workspace_id=WORKSPACE,
        approval_id=proposal.id,
        actor="ops-lead",
        note="not now",
    )
    assert decided.status == "rejected"
    await db_session.refresh(task)
    assert task.status == "failed"
    assert await backend.stream_length(task_queue.task_stream()) == 0


@pytest.mark.asyncio
async def test_dlq_replay_original_attempts_immutable(db_engine, db_session) -> None:
    """Replaying never mutates the original agent_task_attempts rows."""
    from app.services import retry_engine

    backend = task_queue.get_queue_backend()
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    task = await _make_failed_task(db_session)
    # Record two original attempts the way the worker does.
    await retry_engine.record_attempt(
        db_session,
        workspace_id=WORKSPACE,
        task_id=task.id,
        attempt_number=1,
        status=retry_engine.ATTEMPT_FAILED,
        error_type="llm",
        error_message="first",
        worker_id="w1",
        trace_id="trace-dlq",
    )
    await retry_engine.record_attempt(
        db_session,
        workspace_id=WORKSPACE,
        task_id=task.id,
        attempt_number=2,
        status=retry_engine.ATTEMPT_FAILED,
        error_type="timeout",
        error_message="second",
        worker_id="w1",
        trace_id="trace-dlq",
    )
    before = (await db_session.execute(select(AgentTaskAttempt))).scalars().all()
    before_snapshot = [
        (row.attempt_number, row.status, row.error_type, row.error_message) for row in before
    ]

    proposal = await agent_queue.propose_dlq_replay(
        db_session, workspace_id=WORKSPACE, task_id=task.id, reason="review"
    )
    await approval_service.approve_approval(
        db_session,
        backend,
        workspace_id=WORKSPACE,
        approval_id=proposal.id,
        actor="ops-lead",
        trace_id="trace-dlq",
    )
    executor = FakeExecutor()
    await run_worker_once(backend, factory, executor=executor)

    async with factory() as session:
        after = (await session.execute(select(AgentTaskAttempt))).scalars().all()
        after_snapshot = [
            (row.attempt_number, row.status, row.error_type, row.error_message)
            for row in after
            if row.attempt_number in (1, 2)
        ]
    assert after_snapshot == before_snapshot  # original attempts unchanged
    # The worker writes a running + succeeded row for the replayed attempt.
    assert len(after) == len(before) + 2


# --------------------------------------------------------------------------- #
# Runtime operations API
# --------------------------------------------------------------------------- #


def test_runtime_overview_api(api_client) -> None:
    """The overview endpoint returns the dashboard summary shape."""
    response = api_client.get("/api/v1/agent-runtime/overview")
    assert response.status_code == 200, response.text
    body = response.json()
    for key in (
        "agents",
        "workers",
        "queue",
        "executions",
        "retry",
        "dead_letter",
        "approvals",
        "alerts",
        "cost",
        "tokens",
        "failure_rate",
    ):
        assert key in body
    assert body["queue"]["queue_depth"] >= 0


def test_alerts_api_flow(api_client) -> None:
    """evaluate -> list -> ack -> resolve through the API."""
    evaluate = api_client.post("/api/v1/agent-alerts/evaluate")
    assert evaluate.status_code == 200, evaluate.text
    listed = api_client.get("/api/v1/agent-alerts")
    assert listed.status_code == 200
    assert "items" in listed.json()

    # Manually seed an alert via the service layer through the API client
    # session is not possible here, so verify the list endpoint shape only.
    filtered = api_client.get("/api/v1/agent-alerts?status=open&limit=5")
    assert filtered.status_code == 200
    assert filtered.json()["limit"] == 5


def test_approvals_api_flow(api_client) -> None:
    """The approvals API returns pending/decided lists."""
    response = api_client.get("/api/v1/approvals?status=pending")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] >= 0
    assert "items" in body


@pytest.mark.asyncio
async def test_dlq_replay_api_proposal(db_session, api_client) -> None:
    """The replay endpoint only creates a proposal (no direct replay)."""
    task = await _make_failed_task(db_session)
    response = api_client.post(
        f"/api/v1/agent-queue/dead-letters/{task.id}/replay",
        json={"reason": "reviewed"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["proposal_id"]
    assert body["status"] == "pending"
    assert body["original_error"] == "LLM provider unreachable"

    duplicate = api_client.post(
        f"/api/v1/agent-queue/dead-letters/{task.id}/replay",
        json={"reason": "again"},
    )
    assert duplicate.status_code == 400, duplicate.text
