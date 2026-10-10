"""Product Factory Orchestrator — 13-stage automated pipeline.

Orchestrates the full Candidate → Data → V3 → Decision → Master → Creative →
Listing → WC → Verify → Learning lifecycle by calling existing business
services. Does NOT replace any Product Lifecycle state; it tracks *how* the
orchestration progressed.

Key invariants:
- Never modifies V3 scoring, Hard Rules, Creative, Listing Gate, or WC sync.
- Stage functions call existing services; the orchestrator only controls flow.
- Every stage transition emits an event_log entry.
- Idempotent: same product+workflow_type reuses existing non-terminal run.
- WAITING_APPROVAL idle state supports human-in-the-loop resume.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import (
    STAGE_MAX_RETRIES,
    STAGE_POLICIES,
    WORKFLOW_STAGES,
    WORKFLOW_TERMINAL_STATUSES,
    WorkflowException,
    WorkflowRun,
)

logger = logging.getLogger(__name__)

# ── Stage result types ──────────────────────────────────────────────

STAGE_RESULT_PASS = "PASS"
STAGE_RESULT_FAIL = "FAIL"
STAGE_RESULT_RETRY = "RETRY"
STAGE_RESULT_WAIT = "WAIT"
STAGE_RESULT_END = "END"


class StageResult:
    """Result of executing one orchestration stage."""

    def __init__(
        self,
        outcome: str,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
        retryable: bool = False,
        metadata: dict[str, Any] | None = None,
        next_action: str | None = None,
    ) -> None:
        self.outcome = outcome
        self.error_code = error_code
        self.error_message = error_message
        self.retryable = retryable
        self.metadata = metadata or {}
        self.next_action = next_action


class WorkflowError(Exception):
    """Raised when a workflow operation cannot proceed."""


# ── Public API ──────────────────────────────────────────────────────


async def trigger_workflow(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    workflow_type: str = "product_factory",
    trace_id: str | None = None,
) -> WorkflowRun:
    """Start (or resume an existing non-terminal) workflow for a product.

    Idempotent: if a non-terminal run already exists for the same
    (workspace, product, type), it is returned as-is.
    """
    trace_id = trace_id or _generate_trace_id()

    # Check for existing non-terminal run
    existing = await _find_active_run(
        session,
        workspace_id=workspace_id,
        product_id=product_id,
        workflow_type=workflow_type,
    )
    if existing is not None:
        logger.info(
            "Reusing existing workflow run: run_id=%s product_id=%s stage=%s",
            existing.id, product_id, existing.current_stage,
        )
        return existing

    run = WorkflowRun(
        workspace_id=workspace_id,
        product_id=product_id,
        workflow_type=workflow_type,
        current_stage="CANDIDATE_READY",
        execution_status="RUNNING",
        trace_id=trace_id,
        started_at=datetime.now(UTC),
    )
    session.add(run)
    await session.flush()

    await _emit_event(
        session,
        workspace_id=workspace_id,
        event_type="workflow.started",
        entity_type="workflow_run",
        entity_id=str(run.id),
        payload={
            "product_id": str(product_id),
            "workflow_type": workflow_type,
            "current_stage": run.current_stage,
        },
        trace_id=trace_id,
    )

    logger.info(
        "Workflow started: run_id=%s product_id=%s type=%s",
        run.id, product_id, workflow_type,
    )
    return run


async def execute_workflow(
    session: AsyncSession,
    *,
    run_id: UUID,
    workspace_id: UUID,
    trace_id: str | None = None,
) -> WorkflowRun:
    """Execute the current stage of a workflow and advance if possible.

    Returns the updated WorkflowRun. The caller is responsible for commit.
    If the run reaches a terminal state, execution_status is updated accordingly.
    """
    run = await _load_run(session, run_id=run_id, workspace_id=workspace_id)
    if run.execution_status in WORKFLOW_TERMINAL_STATUSES:
        logger.info(
            "Workflow already terminal: run_id=%s status=%s",
            run.id, run.execution_status,
        )
        return run

    trace_id = trace_id or run.trace_id or _generate_trace_id()
    run.trace_id = trace_id

    # ── Execute current stage ──────────────────────────────────
    stage_fn = _STAGE_HANDLERS.get(run.current_stage)
    if stage_fn is None:
        raise WorkflowError(f"No handler for stage: {run.current_stage}")

    result = await stage_fn(
        session,
        workspace_id=workspace_id,
        product_id=run.product_id,
        run=run,
        trace_id=trace_id,
    )

    # ── Handle result ──────────────────────────────────────────
    if result.outcome == STAGE_RESULT_PASS:
        # A stage that previously required approval can pass on re-execution
        # (the human approved). If execution_status were left at
        # WAITING_APPROVAL while current_stage advances, the run would look
        # permanently stuck and no later stage could ever be scheduled, so the
        # wait must be cleared here.
        if run.execution_status == "WAITING_APPROVAL":
            run.execution_status = "RUNNING"
            run.next_action_at = None
        # Merge metadata
        if result.metadata:
            run.stage_metadata = {
                **(run.stage_metadata or {}),
                **result.metadata,
            }
        # Advance to next stage
        next_stage = _next_stage(run.current_stage)
        if next_stage is None:
            # Terminal: all stages completed
            run.execution_status = "COMPLETED"
            run.completed_at = datetime.now(UTC)
            await _emit_event(
                session,
                workspace_id=workspace_id,
                event_type="workflow.completed",
                entity_type="workflow_run",
                entity_id=str(run.id),
                payload={
                    "product_id": str(run.product_id),
                    "total_stages": len(WORKFLOW_STAGES),
                },
                trace_id=trace_id,
            )
        else:
            run.current_stage = next_stage
            await _emit_event(
                session,
                workspace_id=workspace_id,
                event_type="workflow.stage_completed",
                entity_type="workflow_run",
                entity_id=str(run.id),
                payload={
                    "product_id": str(run.product_id),
                    "completed_stage": run.current_stage,
                    "next_stage": next_stage,
                },
                trace_id=trace_id,
            )
        logger.info(
            "Stage %s passed → %s (run_id=%s)",
            run.current_stage, run.current_stage, run.id,
        )

    elif result.outcome == STAGE_RESULT_WAIT:
        # Human approval needed
        run.execution_status = "WAITING_APPROVAL"
        if result.metadata:
            run.stage_metadata = {
                **(run.stage_metadata or {}),
                **result.metadata,
            }
        run.next_action_at = datetime.now(UTC)
        await _emit_event(
            session,
            workspace_id=workspace_id,
            event_type="workflow.waiting_approval",
            entity_type="workflow_run",
            entity_id=str(run.id),
            payload={
                "product_id": str(run.product_id),
                "stage": run.current_stage,
                "next_action": result.next_action,
            },
            trace_id=trace_id,
        )
        logger.info(
            "Workflow waiting approval: run_id=%s stage=%s",
            run.id, run.current_stage,
        )

    elif result.outcome == STAGE_RESULT_RETRY:
        # Retryable failure
        max_retries = STAGE_MAX_RETRIES.get(run.current_stage, 0)
        if result.metadata and "stage_retry_count" in result.metadata:
            stage_retries = result.metadata["stage_retry_count"]
        else:
            stage_retries = run.retry_count
        if stage_retries >= max_retries:
            # Retry exhausted → exception
            await _record_exception(
                session,
                workspace_id=workspace_id,
                run=run,
                stage=run.current_stage,
                error_code=result.error_code or "RETRY_EXHAUSTED",
                error_message=result.error_message or "Max retries exhausted",
                retryable=False,
                retry_count=run.retry_count,
                next_action="MANUAL_INTERVENTION",
                trace_id=trace_id,
            )
            run.execution_status = "EXCEPTION"
            run.completed_at = datetime.now(UTC)
            run.last_error = result.error_message
        else:
            # Schedule retry
            run.retry_count += 1
            run.last_error = result.error_message
            backoff = _compute_backoff(run.retry_count)
            run.next_action_at = datetime.now(UTC)
            # Store retry metadata for the stage to know how many times retried
            retry_key = f"_retry_{run.current_stage}"
            run.stage_metadata = {
                **(run.stage_metadata or {}),
                retry_key: run.retry_count,
            }
            await _emit_event(
                session,
                workspace_id=workspace_id,
                event_type="workflow.stage_retry",
                entity_type="workflow_run",
                entity_id=str(run.id),
                payload={
                    "product_id": str(run.product_id),
                    "stage": run.current_stage,
                    "retry_count": run.retry_count,
                    "max_retries": max_retries,
                    "error_code": result.error_code,
                    "backoff_seconds": backoff,
                },
                trace_id=trace_id,
            )
            logger.info(
                "Stage %s retry %d/%d: run_id=%s error=%s",
                run.current_stage, run.retry_count, max_retries, run.id, result.error_code,
            )

    elif result.outcome == STAGE_RESULT_FAIL:
        # Non-retryable failure → exception
        await _record_exception(
            session,
            workspace_id=workspace_id,
            run=run,
            stage=run.current_stage,
            error_code=result.error_code or "STAGE_FAILED",
            error_message=result.error_message or "Stage failed",
            retryable=False,
            retry_count=run.retry_count,
            next_action=result.next_action or "MANUAL_INTERVENTION",
            trace_id=trace_id,
        )
        run.execution_status = "EXCEPTION"
        run.completed_at = datetime.now(UTC)
        run.last_error = result.error_message
        logger.warning(
            "Stage %s FAILED: run_id=%s error=%s",
            run.current_stage, run.id, result.error_code,
        )

    elif result.outcome == STAGE_RESULT_END:
        # Workflow ended (e.g. decision == REJECT)
        run.execution_status = "FAILED"
        run.completed_at = datetime.now(UTC)
        run.last_error = result.error_message
        if result.metadata:
            run.stage_metadata = {
                **(run.stage_metadata or {}),
                **result.metadata,
            }
        await _emit_event(
            session,
            workspace_id=workspace_id,
            event_type="workflow.failed",
            entity_type="workflow_run",
            entity_id=str(run.id),
            payload={
                "product_id": str(run.product_id),
                "stage": run.current_stage,
                "reason": result.error_message,
            },
            trace_id=trace_id,
        )
        logger.info(
            "Workflow ended: run_id=%s status=FAILED reason=%s",
            run.id, result.error_message,
        )

    await session.flush()
    return run


async def resume_workflow(
    session: AsyncSession,
    *,
    run_id: UUID,
    workspace_id: UUID,
    actor: str,
    trace_id: str | None = None,
) -> WorkflowRun:
    """Resume a WAITING_APPROVAL workflow after human action.

    Re-evaluates the current stage (which may now pass) and advances.
    """
    run = await _load_run(session, run_id=run_id, workspace_id=workspace_id)
    if run.execution_status != "WAITING_APPROVAL":
        raise WorkflowError(
            f"Cannot resume run in status {run.execution_status}"
        )

    trace_id = trace_id or run.trace_id or _generate_trace_id()
    run.trace_id = trace_id
    run.execution_status = "RUNNING"
    run.next_action_at = None

    await _emit_event(
        session,
        workspace_id=workspace_id,
        event_type="workflow.resumed",
        entity_type="workflow_run",
        entity_id=str(run.id),
        payload={
            "product_id": str(run.product_id),
            "stage": run.current_stage,
            "actor": actor,
        },
        trace_id=trace_id,
    )

    # Re-execute the current stage (it may pass now)
    return await execute_workflow(
        session,
        run_id=run.id,
        workspace_id=workspace_id,
        trace_id=trace_id,
    )


async def get_workflow_status(
    session: AsyncSession,
    *,
    run_id: UUID,
    workspace_id: UUID,
) -> dict[str, Any] | None:
    """Get the full status of a workflow run."""
    run = await _load_run(session, run_id=run_id, workspace_id=workspace_id)
    if run is None:
        return None

    status = run.to_dict()

    # Attach unresolved exceptions
    exceptions = await session.execute(
        select(WorkflowException)
        .where(
            WorkflowException.workflow_run_id == run.id,
            WorkflowException.resolved == False,
        )
        .order_by(WorkflowException.created_at.desc())
    )
    exc_list = exceptions.scalars().all()
    status["unresolved_exceptions"] = [e.to_dict() for e in exc_list]

    # Attach event log tail
    events = await session.execute(
        select("event_log").select_from(
            _get_event_log_model()
        )
        .where(
            _get_event_log_model().entity_type == "workflow_run",
            _get_event_log_model().entity_id == str(run.id),
        )
        .order_by(_get_event_log_model().created_at.desc())
        .limit(20)
    )
    event_rows = events.scalars().all()
    status["recent_events"] = [
        {
            "event_type": e.event_type,
            "payload": e.payload or {},
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in event_rows
    ]

    return status


async def list_workflow_runs(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    status: str | None = None,
    product_id: UUID | None = None,
    stage: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List workflow runs with optional filters."""
    query = select(WorkflowRun).where(WorkflowRun.workspace_id == workspace_id)
    if status:
        query = query.where(WorkflowRun.execution_status == status)
    if product_id:
        query = query.where(WorkflowRun.product_id == product_id)
    if stage:
        query = query.where(WorkflowRun.current_stage == stage)
    query = query.order_by(WorkflowRun.created_at.desc()).limit(limit).offset(offset)
    rows = (await session.execute(query)).scalars().all()
    return [r.to_dict() for r in rows]


async def get_exception_queue(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    unresolved_only: bool = True,
    stage: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Get the exception queue."""
    query = select(WorkflowException).where(
        WorkflowException.workspace_id == workspace_id
    )
    if unresolved_only:
        query = query.where(WorkflowException.resolved == False)
    if stage:
        query = query.where(WorkflowException.stage == stage)
    query = query.order_by(WorkflowException.created_at.desc()).limit(limit).offset(offset)
    rows = (await session.execute(query)).scalars().all()
    return [e.to_dict() for e in rows]


async def resolve_exception(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    exception_id: int,
    actor: str,
    note: str | None = None,
) -> dict[str, Any] | None:
    """Mark an exception as resolved."""
    exc = await session.get(WorkflowException, exception_id)
    if exc is None or exc.workspace_id != workspace_id:
        return None
    if exc.resolved:
        return exc.to_dict()

    exc.resolved = True
    exc.resolved_at = datetime.now(UTC)
    exc.resolved_by = actor
    if note:
        exc.next_action = note

    await session.flush()
    return exc.to_dict()


# ── Internal helpers ────────────────────────────────────────────────


async def _find_active_run(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    workflow_type: str,
) -> WorkflowRun | None:
    rows = (
        await session.execute(
            select(WorkflowRun).where(
                WorkflowRun.workspace_id == workspace_id,
                WorkflowRun.product_id == product_id,
                WorkflowRun.workflow_type == workflow_type,
                WorkflowRun.execution_status.notin_(WORKFLOW_TERMINAL_STATUSES),
            )
            .order_by(WorkflowRun.created_at.desc())
            .limit(1)
        )
    ).scalars().all()
    return rows[0] if rows else None


async def _load_run(
    session: AsyncSession, *, run_id: UUID, workspace_id: UUID
) -> WorkflowRun:
    run = await session.get(WorkflowRun, run_id)
    if run is None or run.workspace_id != workspace_id:
        raise WorkflowError(f"Workflow run not found: {run_id}")
    return run


def _next_stage(current: str) -> str | None:
    """Return the next stage after `current`, or None if terminal."""
    try:
        idx = WORKFLOW_STAGES.index(current)
    except ValueError:
        return None
    if idx + 1 < len(WORKFLOW_STAGES):
        return WORKFLOW_STAGES[idx + 1]
    return None


def _compute_backoff(retry_count: int) -> int:
    """Exponential backoff: 1s, 2s, 4s, 8s... capped at 30s."""
    return min(2 ** (retry_count - 1), 30)


def _generate_trace_id() -> str:
    return f"wf-{uuid4().hex[:12]}"


async def _emit_event(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    event_type: str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any],
    trace_id: str | None,
) -> None:
    """Emit an event_log entry (fire-and-forget, best-effort)."""
    try:
        from app.services.event_service import create_event

        await create_event(
            session,
            workspace_id=workspace_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
            trace_id=trace_id,
            commit=False,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to emit event %s: %s", event_type, exc)


async def _record_exception(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    run: WorkflowRun,
    stage: str,
    error_code: str,
    error_message: str | None,
    retryable: bool,
    retry_count: int,
    next_action: str | None,
    trace_id: str | None,
) -> WorkflowException:
    """Record an exception in the workflow_exception queue."""
    exc = WorkflowException(
        workspace_id=workspace_id,
        workflow_run_id=run.id,
        product_id=run.product_id,
        stage=stage,
        error_code=error_code,
        error_message=error_message,
        retryable=retryable,
        retry_count=retry_count,
        next_action=next_action,
        trace_id=trace_id,
    )
    session.add(exc)
    await session.flush()

    await _emit_event(
        session,
        workspace_id=workspace_id,
        event_type="workflow.exception",
        entity_type="workflow_run",
        entity_id=str(run.id),
        payload={
            "product_id": str(run.product_id),
            "stage": stage,
            "error_code": error_code,
            "retryable": retryable,
            "next_action": next_action,
        },
        trace_id=trace_id,
    )
    return exc


def _get_event_log_model() -> Any:
    """Lazy-import EventLog to avoid circular import at module level."""
    from app.models.event import EventLog

    return EventLog


# ── Stage Handlers ──────────────────────────────────────────────────


async def _stage_candidate_ready(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    run: WorkflowRun,
    trace_id: str,
) -> StageResult:
    """S1: Check that the product exists and is a candidate."""
    from app.models.product import Product

    product = await session.get(Product, product_id)
    if product is None or product.deleted_at is not None:
        return StageResult(
            STAGE_RESULT_END,
            error_code="PRODUCT_NOT_FOUND",
            error_message=f"Product not found: {product_id}",
        )

    # candidate_status must be "candidate" to proceed
    if product.candidate_status != "candidate":
        return StageResult(
            STAGE_RESULT_END,
            error_code="NOT_A_CANDIDATE",
            error_message=f"Product candidate_status is '{product.candidate_status}', expected 'candidate'",
            metadata={"candidate_status": product.candidate_status},
        )

    return StageResult(
        STAGE_RESULT_PASS,
        metadata={"product_name": product.name, "sku": product.sku},
    )


async def _stage_data_readiness(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    run: WorkflowRun,
    trace_id: str,
) -> StageResult:
    """S2: Build evaluation context, check readiness, auto-backfill if needed."""
    from app.models.product import Product
    from app.services.evaluation_context import build_evaluation_context
    from app.services.evaluation_readiness import evaluate_readiness

    product = await session.get(Product, product_id)
    if product is None:
        return StageResult(
            STAGE_RESULT_END,
            error_code="PRODUCT_NOT_FOUND",
            error_message="Product not found during data readiness check",
        )

    # Build full evaluation context (reuses existing services)
    ctx = await build_evaluation_context(
        session,
        product_id,
        workspace_id=workspace_id,
        trace_id=trace_id,
    )

    # Evaluate readiness
    readiness = evaluate_readiness(ctx)
    ctx.readiness_status = readiness.status
    ctx.readiness_score = readiness.score
    ctx.missing_fields = readiness.missing_fields

    # Update product's data integrity fields
    product.data_integrity_status = readiness.status
    product.data_integrity_score = readiness.score
    product.data_integrity_missing = readiness.missing_fields
    product.data_integrity_checked_at = datetime.now(UTC)
    product.data_integrity_trace_id = trace_id
    await session.flush()

    if readiness.status == "V3_READY":
        return StageResult(
            STAGE_RESULT_PASS,
            metadata={
                "data_integrity_score": str(readiness.score),
                "readiness_status": "V3_READY",
            },
        )

    # V3_NEEDS_DATA or V3_BLOCKED — attempt auto-backfill if enrichable
    if readiness.status == "V3_NEEDS_DATA" and readiness.auto_enrichable_missing:
        retry_count = run.retry_count
        if retry_count < 3:
            try:
                from app.services.backfill_1688_service import backfill_1688_products

                await backfill_1688_products(
                    session,
                    workspace_id=workspace_id,
                    product_ids=[str(product_id)],
                    candidate_only=True,
                    dry_run=False,
                )
                await session.flush()
            except Exception as exc:  # noqa: BLE001
                return StageResult(
                    STAGE_RESULT_RETRY,
                    error_code="BACKFILL_FAILED",
                    error_message=str(exc),
                    retryable=True,
                    metadata={
                        "stage_retry_count": retry_count,
                        "missing_fields": readiness.missing_fields,
                    },
                )

            # Re-evaluate after backfill
            ctx2 = await build_evaluation_context(
                session,
                product_id,
                workspace_id=workspace_id,
                trace_id=trace_id,
            )
            readiness2 = evaluate_readiness(ctx2)
            product.data_integrity_status = readiness2.status
            product.data_integrity_score = readiness2.score
            product.data_integrity_missing = readiness2.missing_fields
            product.data_integrity_checked_at = datetime.now(UTC)
            await session.flush()

            if readiness2.status == "V3_READY":
                return StageResult(
                    STAGE_RESULT_PASS,
                    metadata={
                        "data_integrity_score": str(readiness2.score),
                        "readiness_status": "V3_READY",
                        "backfilled": True,
                    },
                )

            # Still needs data — retry
            return StageResult(
                STAGE_RESULT_RETRY,
                error_code="DATA_INCOMPLETE",
                error_message=f"Data still incomplete after backfill: missing={readiness2.missing_fields}",
                retryable=True,
                metadata={
                    "stage_retry_count": retry_count + 1,
                    "missing_fields": readiness2.missing_fields,
                },
            )

    # Retries exhausted or V3_BLOCKED (non-enrichable fields missing)
    return StageResult(
        STAGE_RESULT_FAIL,
        error_code="DATA_INCOMPLETE_EXHAUSTED",
        error_message=f"Data completeness gate failed: status={readiness.status}, missing={readiness.missing_fields}",
        retryable=False,
        metadata={
            "missing_fields": readiness.missing_fields,
            "next_actions": readiness.next_actions,
        },
        next_action="MANUAL_DATA_ENRICHMENT",
    )


def _json_safe_scalar(value: Any) -> Any:
    """Coerce a value into something JSONB (stage_metadata) can store.

    Stage metadata is persisted to a JSON column, so a raw ``Decimal`` (pydantic
    Decimal fields, assessment blocks) raises
    ``TypeError: Object of type Decimal is not JSON serializable`` and rolls back
    the whole stage transaction.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


async def _stage_ai_analysis(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    run: WorkflowRun,
    trace_id: str,
) -> StageResult:
    """S3: Run the Product Analyst to produce the brand_fit / AI veto signals.

    Why this stage exists: ``map_dimensions_strict`` (used by V3_EVALUATION)
    hard-requires a ``brand_fit`` override and cannot fabricate one, and
    ``brand_fit`` is only ever produced by a Product Analyst run. Without this
    stage the pipeline could not reach V3 on its own - an external script had
    to call the analyst first, which is not an automated factory loop.

    Idempotent by reuse: if a completed run already carries a non-empty
    ``nuotao_assessment`` block, the stage passes without spending another LLM
    call (the same block V3 reads is the one we check here).
    """
    from app.agents import product_analyst
    from app.agents.product_analyst import ProductAnalystError
    from app.services.evaluation_context import _latest_ai_assessment
    from app.services.llm_gateway import LLMError

    existing = await _latest_ai_assessment(
        session, workspace_id=workspace_id, product_id=product_id
    )
    if isinstance(existing, dict) and existing:
        return StageResult(
            STAGE_RESULT_PASS,
            metadata={
                "ai_analysis": "reused_existing",
                "ai_brand_fit": _json_safe_scalar(existing.get("brand_fit")),
            },
        )

    try:
        result = await product_analyst.analyze_product(
            session,
            workspace_id=workspace_id,
            product_id=product_id,
            trace_id=trace_id,
        )
    except LLMError as exc:
        # Provider/network/timeout/truncated: transient, worth a bounded retry.
        return StageResult(
            STAGE_RESULT_RETRY,
            error_code="AI_ANALYSIS_LLM_ERROR",
            error_message=str(exc),
            retryable=True,
            metadata={"stage_retry_count": run.retry_count + 1},
        )
    except ProductAnalystError as exc:
        message = str(exc)
        # analyze_product wraps provider failures as "LLM call failed: ...";
        # those are transient. Anything else (missing product, unusable
        # structured output) is terminal - retrying would just repeat it.
        if message.startswith("LLM call failed"):
            return StageResult(
                STAGE_RESULT_RETRY,
                error_code="AI_ANALYSIS_LLM_ERROR",
                error_message=message,
                retryable=True,
                metadata={"stage_retry_count": run.retry_count + 1},
            )
        return StageResult(
            STAGE_RESULT_FAIL,
            error_code="AI_ANALYSIS_FAILED",
            error_message=message,
            retryable=False,
            next_action="MANUAL_REVIEW",
        )
    except Exception as exc:  # noqa: BLE001 - defensive
        return StageResult(
            STAGE_RESULT_FAIL,
            error_code="AI_ANALYSIS_FAILED",
            error_message=str(exc),
            retryable=False,
            next_action="MANUAL_REVIEW",
        )

    output = getattr(result, "output", None)
    assessment = (output.model_dump() if output is not None else {}).get(
        "nuotao_assessment"
    ) or {}
    if not assessment:
        return StageResult(
            STAGE_RESULT_FAIL,
            error_code="AI_ANALYSIS_NO_ASSESSMENT",
            error_message="analyst produced no nuotao_assessment block",
            retryable=False,
            next_action="MANUAL_REVIEW",
        )

    return StageResult(
        STAGE_RESULT_PASS,
        metadata={
            "ai_analysis": "completed",
            "ai_analysis_run_id": str(result.analysis_run.id) if result.analysis_run else None,
            "ai_brand_fit": _json_safe_scalar(assessment.get("brand_fit")),
            "ai_decision": _json_safe_scalar(getattr(output, "decision", None)),
        },
    )


async def _stage_v3_evaluation(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    run: WorkflowRun,
    trace_id: str,
) -> StageResult:
    """S3: Run V3 evaluation via nuotao_selection_service.evaluate_product."""
    from app.services.nuotao_selection_service import evaluate_product

    try:
        evaluation = await evaluate_product(
            session,
            product_id,
            workspace_id=workspace_id,
            trace_id=trace_id,
        )
        veto = evaluation.get("veto") or {}
        veto_failed = [str(v) for v in (veto.get("failed") or [])]
        result_metadata = {
            "v3_grade": evaluation.get("grade"),
            "v3_total": evaluation.get("nuotao_total"),
            "v3_funnel_stage": evaluation.get("funnel_stage"),
            "v3_gate_blocked": evaluation.get("gate_blocked", False),
            "v3_veto_failed": veto_failed,
            "v3_veto_pending": [str(v) for v in (veto.get("pending") or [])],
        }
        return StageResult(STAGE_RESULT_PASS, metadata=result_metadata)
    except Exception as exc:  # noqa: BLE001
        return StageResult(
            STAGE_RESULT_FAIL,
            error_code="V3_EVALUATION_FAILED",
            error_message=str(exc),
            retryable=False,
        )


async def _stage_hard_rules(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    run: WorkflowRun,
    trace_id: str,
) -> StageResult:
    """S4: Check V3 hard veto rules from the evaluation result."""
    metadata = run.stage_metadata or {}
    veto_failed = metadata.get("v3_veto_failed", [])
    gate_blocked = metadata.get("v3_gate_blocked", False)

    if gate_blocked or veto_failed:
        return StageResult(
            STAGE_RESULT_END,
            error_code="HARD_VETO",
            error_message=f"V3 hard veto triggered: {veto_failed}",
            metadata={"veto_failed": veto_failed},
            next_action="MANUAL_REVIEW",
        )

    return StageResult(STAGE_RESULT_PASS)


async def _stage_product_decision(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    run: WorkflowRun,
    trace_id: str,
) -> StageResult:
    """S5: Check decision state. AUTO if approve conditions met; HUMAN otherwise."""
    from app.models.product import Product

    product = await session.get(Product, product_id)
    if product is None:
        return StageResult(
            STAGE_RESULT_END,
            error_code="PRODUCT_NOT_FOUND",
            error_message="Product not found during decision check",
        )

    # Check if product has already been decided
    candidate_status = product.candidate_status
    if candidate_status in ("approved", "testing", "winner"):
        # Already approved — proceed
        return StageResult(
            STAGE_RESULT_PASS,
            metadata={"decision": "APPROVED", "candidate_status": candidate_status},
        )

    if candidate_status == "rejected":
        return StageResult(
            STAGE_RESULT_END,
            error_code="DECISION_REJECTED",
            error_message="Product decision is REJECT",
            metadata={"decision": "REJECT"},
        )

    # Check if there's an existing approved approval first (highest priority)
    from app.models.agent_operations import AgentApproval

    approved_approval = (
        await session.execute(
            select(AgentApproval)
            .where(
                AgentApproval.workspace_id == workspace_id,
                AgentApproval.entity_type == "product",
                AgentApproval.entity_id == str(product_id),
                AgentApproval.status == "approved",
            )
            .limit(1)
        )
    ).scalar_one_or_none()

    if approved_approval:
        return StageResult(
            STAGE_RESULT_PASS,
            metadata={"decision": "APPROVED", "approval_id": str(approved_approval.id)},
        )

    # Check for existing approval (any status)
    approval = (
        await session.execute(
            select(AgentApproval)
            .where(
                AgentApproval.workspace_id == workspace_id,
                AgentApproval.entity_type == "product",
                AgentApproval.entity_id == str(product_id),
            )
            .order_by(AgentApproval.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if approval and approval.status == "rejected":
        return StageResult(
            STAGE_RESULT_END,
            error_code="DECISION_REJECTED",
            error_message="Product decision approval was rejected",
            metadata={"decision": "REJECT"},
        )

    # No approval or pending — HUMAN REQUIRED
    # Create approval request if none exists
    if approval is None or approval.status == "expired":
        from app.services.approval_service import ensure_approval

        await ensure_approval(
            session,
            workspace_id=workspace_id,
            approval_type="product_decision",
            entity_type="product",
            entity_id=str(product_id),
            metadata_={"workflow_run_id": str(run.id), "stage": "PRODUCT_DECISION"},
            trace_id=trace_id,
        )
        await session.flush()

    return StageResult(
        STAGE_RESULT_WAIT,
        error_code="APPROVAL_REQUIRED",
        error_message="Product decision requires human approval",
        metadata={"needs_approval": True, "approval_entity_id": str(product_id)},
        next_action="APPROVE_DECISION",
    )


async def _stage_product_master(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    run: WorkflowRun,
    trace_id: str,
) -> StageResult:
    """S6: Promote to Product Master if decision is APPROVE."""
    from app.models.product import Product

    product = await session.get(Product, product_id)
    if product is None:
        return StageResult(
            STAGE_RESULT_END,
            error_code="PRODUCT_NOT_FOUND",
            error_message="Product not found during master promotion",
        )

    # Check if already mastered
    if product.mastered_at is not None:
        return StageResult(
            STAGE_RESULT_PASS,
            metadata={"already_mastered": True, "mastered_at": product.mastered_at.isoformat()},
        )

    # Check candidate_status must be approved
    if product.candidate_status not in ("approved", "testing", "winner"):
        return StageResult(
            STAGE_RESULT_END,
            error_code="NOT_APPROVED",
            error_message=f"Product candidate_status is '{product.candidate_status}', expected approved/testing/winner",
        )

    # Promote to Product Master
    product.mastered_at = datetime.now(UTC)
    product.mastered_by = "product_factory_orchestrator"
    product.mastered_trace_id = trace_id

    # Advance candidate_status to "winner" if currently approved/testing
    if product.candidate_status in ("approved", "testing"):
        product.candidate_status = "winner"

    await session.flush()

    return StageResult(
        STAGE_RESULT_PASS,
        metadata={"mastered_at": product.mastered_at.isoformat(), "candidate_status": product.candidate_status},
    )


async def _stage_creative(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    run: WorkflowRun,
    trace_id: str,
) -> StageResult:
    """S7: Create creative brief and generate assets."""
    from app.services import creative_service

    try:
        # Check if brief already exists
        existing_brief = (
            await session.execute(
                select(creative_service.CreativeBrief).where(
                    creative_service.CreativeBrief.product_id == product_id,
                    creative_service.CreativeBrief.workspace_id == workspace_id,
                )
                .order_by(creative_service.CreativeBrief.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        if existing_brief:
            # Use existing brief
            brief_id = existing_brief.id
        else:
            # Create new brief
            brief = await creative_service.create_brief_from_product(
                session,
                product_id=product_id,
                workspace_id=workspace_id,
                created_by="product_factory_orchestrator",
                trace_id=trace_id,
            )
            brief_id = brief.id

        # Generate assets from brief
        runs = await creative_service.generate_brief_assets(
            session,
            brief_id=brief_id,
            workspace_id=workspace_id,
            trace_id=trace_id,
        )

        return StageResult(
            STAGE_RESULT_PASS,
            metadata={"brief_id": str(brief_id), "generation_runs": len(runs)},
        )
    except Exception as exc:  # noqa: BLE001
        retry_count = run.retry_count
        if retry_count < 2:
            return StageResult(
                STAGE_RESULT_RETRY,
                error_code="CREATIVE_GENERATION_FAILED",
                error_message=str(exc),
                retryable=True,
                metadata={"stage_retry_count": retry_count},
            )
        return StageResult(
            STAGE_RESULT_FAIL,
            error_code="CREATIVE_GENERATION_FAILED",
            error_message=str(exc),
            retryable=False,
        )


async def _stage_creative_qc(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    run: WorkflowRun,
    trace_id: str,
) -> StageResult:
    """S8: Run quality check on creative assets."""
    from app.services import creative_service
    from sqlalchemy import func

    # Find all assets for this product's brief
    assets = (
        await session.execute(
            select(creative_service.CreativeStudioAsset)
            .where(
                creative_service.CreativeStudioAsset.workspace_id == workspace_id,
            )
            .order_by(creative_service.CreativeStudioAsset.created_at.desc())
            .limit(20)
        )
    ).scalars().all()

    if not assets:
        return StageResult(
            STAGE_RESULT_RETRY,
            error_code="NO_ASSETS_FOUND",
            error_message="No creative assets found for QC",
            retryable=True,
            metadata={"stage_retry_count": run.retry_count},
        )

    passed_count = 0
    failed_count = 0
    for asset in assets:
        try:
            qc_result = await creative_service.run_quality_check(
                session,
                asset_id=asset.id,
                workspace_id=workspace_id,
                trace_id=trace_id,
            )
            if qc_result.get("passed"):
                passed_count += 1
            else:
                failed_count += 1
        except Exception as exc:  # noqa: BLE001
            failed_count += 1

    if failed_count == 0:
        return StageResult(
            STAGE_RESULT_PASS,
            metadata={"qc_passed": passed_count, "qc_failed": 0, "total_assets": len(assets)},
        )

    # Some failed — retry if retries available
    if run.retry_count < 2:
        return StageResult(
            STAGE_RESULT_RETRY,
            error_code="QC_PARTIAL_FAILURE",
            error_message=f"{failed_count}/{len(assets)} assets failed QC",
            retryable=True,
            metadata={"stage_retry_count": run.retry_count, "qc_passed": passed_count, "qc_failed": failed_count},
        )

    return StageResult(
        STAGE_RESULT_FAIL,
        error_code="QC_FAILED",
        error_message=f"{failed_count}/{len(assets)} assets failed QC after retries",
        retryable=False,
        metadata={"qc_passed": passed_count, "qc_failed": failed_count},
    )


async def _stage_listing_build(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    run: WorkflowRun,
    trace_id: str,
) -> StageResult:
    """S9: Build listing data for the product."""
    from app.models.product import Product

    product = await session.get(Product, product_id)
    if product is None:
        return StageResult(
            STAGE_RESULT_END,
            error_code="PRODUCT_NOT_FOUND",
            error_message="Product not found during listing build",
        )

    # Check if listing_data already exists in meta
    meta = product.meta or {}
    if meta.get("listing_data"):
        return StageResult(
            STAGE_RESULT_PASS,
            metadata={"listing_build": "already_exists"},
        )

    # Build listing data using the pipeline service
    from app.services.product_pipeline_service import _generate_listing_data

    product_info = {
        "name": product.name,
        "description": product.description or "",
        "category": product.category or "",
        "brand": product.brand or "",
        "sku": product.sku,
        "price": str(product.meta.get("regular_price", "")) if product.meta else "",
        "target_market": product.target_market or "US",
    }

    listing_data = _generate_listing_data(product_info)

    # Store in product meta
    product.meta = {
        **(product.meta or {}),
        "listing_data": listing_data,
    }
    await session.flush()

    return StageResult(
        STAGE_RESULT_PASS,
        metadata={"listing_build": "completed", "sku": product.sku},
    )


async def _stage_listing_gate(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    run: WorkflowRun,
    trace_id: str,
) -> StageResult:
    """S10: Evaluate listing gate."""
    from app.models.product import Product
    from app.services.listing_gate import evaluate_gate_from_dict

    product = await session.get(Product, product_id)
    if product is None:
        return StageResult(
            STAGE_RESULT_END,
            error_code="PRODUCT_NOT_FOUND",
            error_message="Product not found during listing gate",
        )

    listing_data = (product.meta or {}).get("listing_data", {})
    gate = evaluate_gate_from_dict(listing_data)

    if gate["status"] == "passed":
        return StageResult(
            STAGE_RESULT_PASS,
            metadata={"gate_status": "passed"},
        )

    if gate["status"] == "blocked":
        return StageResult(
            STAGE_RESULT_END,
            error_code="GATE_BLOCKED",
            error_message=f"Listing gate blocked: {gate['reasons']}",
            metadata={"gate_status": "blocked", "gate_reasons": gate["reasons"]},
            next_action="FIX_GATE_ISSUES",
        )

    # needs_review — human approval
    return StageResult(
        STAGE_RESULT_WAIT,
        error_code="GATE_NEEDS_REVIEW",
        error_message=f"Listing gate needs review: {gate['reasons']}",
        metadata={"gate_status": "needs_review", "gate_reasons": gate["reasons"]},
        next_action="REVIEW_GATE",
    )


async def _stage_wc_sync(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    run: WorkflowRun,
    trace_id: str,
) -> StageResult:
    """S11: Push product to WooCommerce."""
    from app.services.woocommerce_sync_service import push_product_to_woocommerce

    try:
        result = await push_product_to_woocommerce(
            str(product_id),
            db_session=session,
        )

        if result.get("success"):
            return StageResult(
                STAGE_RESULT_PASS,
                metadata={
                    "wc_sync": "success",
                    "wc_product_id": result.get("woocommerce_id"),
                    "action": result.get("action"),
                },
            )

        # Check if error is retryable
        error = result.get("error", "")
        status_code = result.get("status_code")
        is_retryable = _is_wc_retryable(error, status_code)

        if is_retryable and run.retry_count < 3:
            return StageResult(
                STAGE_RESULT_RETRY,
                error_code="WC_SYNC_RETRYABLE",
                error_message=error,
                retryable=True,
                metadata={"stage_retry_count": run.retry_count},
            )

        return StageResult(
            STAGE_RESULT_FAIL,
            error_code="WC_SYNC_FAILED",
            error_message=error,
            retryable=False,
        )
    except Exception as exc:  # noqa: BLE001
        retry_count = run.retry_count
        if retry_count < 3:
            return StageResult(
                STAGE_RESULT_RETRY,
                error_code="WC_SYNC_EXCEPTION",
                error_message=str(exc),
                retryable=True,
                metadata={"stage_retry_count": retry_count},
            )
        return StageResult(
            STAGE_RESULT_FAIL,
            error_code="WC_SYNC_EXCEPTION",
            error_message=str(exc),
            retryable=False,
        )


async def _stage_wc_verify(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    run: WorkflowRun,
    trace_id: str,
) -> StageResult:
    """S12: Verify WC product was created/updated correctly."""
    from app.models.product import Product
    from app.services.wc_product_link_service import resolve_wc_product_id

    product = await session.get(Product, product_id)
    if product is None:
        return StageResult(
            STAGE_RESULT_END,
            error_code="PRODUCT_NOT_FOUND",
            error_message="Product not found during WC verify",
        )

    meta = product.meta or {}
    wc_id = meta.get("woocommerce_id")

    if not wc_id:
        # Try to resolve by SKU
        from app.services.wc_product_link_service import resolve_wc_product_id
        try:
            from app.services.woocommerce_sync_service import _get_wc_auth, _get_wc_headers

            wc_id, _ = resolve_wc_product_id(
                product,
                auth=_get_wc_auth(),
                headers=_get_wc_headers(),
            )
            if wc_id:
                meta["woocommerce_id"] = wc_id
                product.meta = meta
                await session.flush()
        except Exception:  # noqa: BLE001
            pass

    if not wc_id:
        return StageResult(
            STAGE_RESULT_FAIL,
            error_code="WC_VERIFY_NO_ID",
            error_message="No WooCommerce product ID found for verification",
            retryable=False,
            metadata={"wc_verify": "no_wc_id"},
        )

    return StageResult(
        STAGE_RESULT_PASS,
        metadata={"wc_verify": "passed", "wc_product_id": wc_id},
    )


async def _stage_learning_event(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    run: WorkflowRun,
    trace_id: str,
) -> StageResult:
    """S13: Log learning event for the completed workflow."""
    metadata = run.stage_metadata or {}

    # Gather key data points
    learning_payload = {
        "product_id": str(product_id),
        "workflow_run_id": str(run.id),
        "total_stages_completed": len(WORKFLOW_STAGES),
        "total_retries": run.retry_count,
        "v3_grade": metadata.get("v3_grade"),
        "data_integrity_score": metadata.get("data_integrity_score"),
        "wc_product_id": metadata.get("wc_product_id"),
        "trace_id": trace_id,
    }

    await _emit_event(
        session,
        workspace_id=workspace_id,
        event_type="workflow.completed",
        entity_type="product",
        entity_id=str(product_id),
        payload=learning_payload,
        trace_id=trace_id,
    )

    return StageResult(STAGE_RESULT_PASS, metadata={"learning_logged": True})


def _is_wc_retryable(error: str, status_code: int | None) -> bool:
    """Determine if a WC error is retryable."""
    if status_code and status_code in (429, 500, 502, 503, 504):
        return True
    if status_code in (400, 422):
        return False
    # Network errors are typically retryable
    retryable_keywords = ("timeout", "connection", "network", "temporarily", "503", "429")
    return any(kw in error.lower() for kw in retryable_keywords)


# ── Stage handler registry ──────────────────────────────────────────

_STAGE_HANDLERS: dict[str, Any] = {
    "CANDIDATE_READY": _stage_candidate_ready,
    "DATA_READINESS": _stage_data_readiness,
    "AI_ANALYSIS": _stage_ai_analysis,
    "V3_EVALUATION": _stage_v3_evaluation,
    "HARD_RULES": _stage_hard_rules,
    "PRODUCT_DECISION": _stage_product_decision,
    "PRODUCT_MASTER": _stage_product_master,
    "CREATIVE": _stage_creative,
    "CREATIVE_QC": _stage_creative_qc,
    "LISTING_BUILD": _stage_listing_build,
    "LISTING_GATE": _stage_listing_gate,
    "WC_SYNC": _stage_wc_sync,
    "WC_VERIFY": _stage_wc_verify,
    "LEARNING_EVENT": _stage_learning_event,
}
