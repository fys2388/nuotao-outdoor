"""M5.6 Product Analyst production pilot orchestration.

Turns the runtime-validated Product Analyst into a real business pilot:
task -> worker -> context -> LLM -> decision proposal -> human approval ->
experiment proposal -> human start -> actual result -> evaluation ->
calibration -> knowledge -> next context. Nothing here auto-approves, auto-
starts experiments or auto-applies calibration; every business action keeps a
human gate (the Approval Center + the experiment start endpoint).

Scorecard / ROI are workspace-scoped aggregates over the existing M2/M5 rows;
ROI never fabricates business impact (revenue/margin/roas impacts stay null
until a real attribution pipeline exists).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_runtime import AgentRegistry, AgentTask
from app.models.product import Product
from app.models.product_intelligence import (
    ProductAiEvaluation,
    ProductAnalysisRun,
    ProductDecision,
    ProductExperiment,
    ProductKnowledgeEntry,
)
from app.schemas.agent_runtime import TaskCreate
from app.schemas.knowledge import KnowledgeEntryCreate
from app.schemas.product_analyst import ConfidenceCalibrationOut, ScoreCalibrationRunOut
from app.schemas.product_intelligence import ExperimentCompleteRequest
from app.services import (
    agent_runtime,
    ai_evaluation,
    calibration,
    evaluation_bridge,
    event_service,
    knowledge,
    product_intelligence,
    task_queue,
)

logger = logging.getLogger(__name__)

PRODUCT_ANALYST_AGENT_ID = "product_analyst"
PILOT_WAIT_TIMEOUT_SECONDS = 300
PILOT_WAIT_INTERVAL_SECONDS = 1.0


class PilotError(Exception):
    """Raised when a pilot step cannot complete."""


# --------------------------------------------------------------------------- #
# Pilot task creation + wait
# --------------------------------------------------------------------------- #


async def _product_analyst_agent(session: AsyncSession, *, workspace_id: UUID) -> AgentRegistry:
    agent = await agent_runtime.get_agent_by_code(
        session, workspace_id=workspace_id, agent_id=PRODUCT_ANALYST_AGENT_ID
    )
    if agent is None:
        raise PilotError(
            "product_analyst agent is not registered in this workspace; "
            "register it (AGENT_PRODUCT_ANALYST prompt) before running a pilot"
        )
    return agent


async def create_pilot_task(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    actor: str | None = None,
    trace_id: str | None = None,
) -> AgentTask:
    """Create + enqueue one product-analysis task (never auto-approved)."""
    product = (
        await session.execute(
            select(Product.id).where(
                Product.workspace_id == workspace_id,
                Product.id == product_id,
            )
        )
    ).scalar_one_or_none()
    if product is None:
        raise PilotError("product not found")
    agent = await _product_analyst_agent(session, workspace_id=workspace_id)
    task = await agent_runtime.create_task(
        session,
        workspace_id=workspace_id,
        data=TaskCreate(
            agent_id=agent.id,
            input={"product_id": str(product_id)},
            priority=3,
        ),
        trace_id=trace_id,
    )
    backend = task_queue.get_queue_backend()
    if task.enqueued_at is None:
        await task_queue.enqueue_task(
            backend,
            workspace_id=workspace_id,
            task_id=task.id,
            attempt=1,
            idempotency_key=task.idempotency_key,
        )
        task.enqueued_at = datetime.now(UTC)
        await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.product_analyst.pilot_started",
        entity_type="agent_task",
        entity_id=str(task.id),
        payload={
            "product_id": str(product_id),
            "agent_id": agent.agent_id,
            "actor": actor,
        },
        trace_id=trace_id,
    )
    return task


async def wait_for_task(
    session: AsyncSession,
    *,
    task_id: UUID,
    timeout_seconds: float = PILOT_WAIT_TIMEOUT_SECONDS,
    interval: float = PILOT_WAIT_INTERVAL_SECONDS,
) -> AgentTask:
    """Poll the DB task row until it reaches a terminal state."""
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    while True:
        await session.rollback()
        task = (
            await session.execute(select(AgentTask).where(AgentTask.id == task_id))
        ).scalar_one_or_none()
        if task is None:
            raise PilotError("task not found")
        if task.status in ("completed", "failed", "cancelled"):
            return task
        if asyncio.get_event_loop().time() >= deadline:
            raise PilotError(
                f"task {task_id} did not reach a terminal state within {timeout_seconds}s"
            )
        await asyncio.sleep(interval)


# --------------------------------------------------------------------------- #
# Experiment completion -> evaluation backfill
# --------------------------------------------------------------------------- #


async def complete_experiment_with_evaluation(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    experiment_id: UUID,
    data: ExperimentCompleteRequest,
    trace_id: str | None = None,
) -> ProductExperiment:
    """Complete the experiment (active -> completed) and backfill actuals.

    The backfill reuses ``ai_evaluation`` classification through the unified
    bridge (``evaluation_bridge.backfill_experiment_evaluation``) so M2.3
    confidence reports + score calibration consume real outcomes. Append-only.
    """
    experiment = await product_intelligence.complete_experiment(
        session,
        workspace_id=workspace_id,
        experiment_id=experiment_id,
        data=data,
        trace_id=trace_id,
    )
    actual = experiment.actual_result or {}
    await evaluation_bridge.backfill_experiment_evaluation(
        session,
        workspace_id=workspace_id,
        experiment_id=experiment.id,
        actual_result=actual,
        trace_id=trace_id,
    )
    return experiment


# --------------------------------------------------------------------------- #
# Calibration (proposals only - never auto-applied)
# --------------------------------------------------------------------------- #


async def run_calibration(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Generate the confidence report + a score calibration proposal.

    Only runs when completed experiments exist; the proposal stays
    ``proposed`` until a human decides it. SCORE_WEIGHTS/rules are never
    modified automatically.
    """
    completed = (
        (
            await session.execute(
                select(ProductExperiment).where(
                    ProductExperiment.workspace_id == workspace_id,
                    ProductExperiment.status == "completed",
                )
            )
        )
        .scalars()
        .all()
    )
    if not completed:
        return {"confidence": [], "calibration_run": None, "skipped": True}

    report = await calibration.generate_confidence_report(
        session, workspace_id=workspace_id, trace_id=trace_id
    )
    run = await calibration.run_score_calibration(
        session, workspace_id=workspace_id, trace_id=trace_id
    )
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.product_calibration.proposed",
        entity_type="score_calibration_run",
        entity_id=str(run.id),
        payload={
            "model_version": run.model_version,
            "sample_size": run.sample_size,
            "status": run.status,
        },
        trace_id=trace_id,
    )
    return {
        "confidence": [
            ConfidenceCalibrationOut.model_validate(row).model_dump(mode="json") for row in report
        ],
        "calibration_run": ScoreCalibrationRunOut.model_validate(run).model_dump(mode="json"),
        "skipped": False,
    }


# --------------------------------------------------------------------------- #
# Knowledge feedback (only after human-approved calibration)
# --------------------------------------------------------------------------- #


async def feedback_knowledge(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    calibration_run_id: UUID,
    trace_id: str | None = None,
) -> list[ProductKnowledgeEntry]:
    """Distill approved calibration + experiment outcomes into knowledge.

    ``sync_calibration_to_knowledge`` enforces that only an APPROVED run is
    distilled. Experiment success/failure patterns are created once per
    (product, type, source trace) - append-only, never duplicated.
    """
    entry = await evaluation_bridge.sync_calibration_to_knowledge(
        session,
        workspace_id=workspace_id,
        run_id=calibration_run_id,
        trace_id=trace_id,
    )
    created: list[ProductKnowledgeEntry] = [entry]

    completed = (
        (
            await session.execute(
                select(ProductExperiment).where(
                    ProductExperiment.workspace_id == workspace_id,
                    ProductExperiment.status == "completed",
                )
            )
        )
        .scalars()
        .all()
    )
    existing = (
        (
            await session.execute(
                select(ProductKnowledgeEntry).where(
                    ProductKnowledgeEntry.workspace_id == workspace_id,
                    ProductKnowledgeEntry.source == "experiment",
                )
            )
        )
        .scalars()
        .all()
    )
    # Dedup on the stable source trace (the experiment's trace) so a new
    # feedback run never duplicates the same experiment pattern.
    existing_keys = {(row.product_id, row.entry_type, row.trace_id) for row in existing}
    for experiment in completed:
        actual = experiment.actual_result or {}
        prediction = experiment.prediction or {}
        decision_match = None
        if "decision" in prediction and "decision" in actual:
            decision_match = prediction["decision"] == actual["decision"]
        success = ai_evaluation._determine_success(  # noqa: SLF001
            prediction, actual, decision_match
        )
        if success is None:
            continue
        entry_type = "success_pattern" if success is True else "failure_pattern"
        if (experiment.product_id, entry_type, experiment.trace_id) in existing_keys:
            continue
        product = (
            await session.execute(
                select(Product).where(
                    Product.workspace_id == workspace_id,
                    Product.id == experiment.product_id,
                )
            )
        ).scalar_one_or_none()
        result = "success" if success is True else "failure"
        title = f"Experiment {experiment.experiment_type} {result}: product {experiment.product_id}"
        content = (
            f"Completed experiment (trace {experiment.trace_id}) with {result}; "
            f"predicted decision={prediction.get('decision')} actual={actual.get('decision')} "
            f"roas={actual.get('roas')} margin_rate={actual.get('margin_rate')}"
        )
        row = await knowledge.create_knowledge_entry(
            session,
            workspace_id=workspace_id,
            data=KnowledgeEntryCreate(
                product_id=experiment.product_id,
                category=product.category if product else None,
                entry_type=entry_type,
                title=title,
                content=content[:4000],
                tags=["experiment", experiment.experiment_type],
                source="experiment",
            ),
            # The knowledge row keeps the experiment's source trace so the
            # dedup key (product, type, trace) is stable across feedback runs.
            trace_id=experiment.trace_id or trace_id,
        )
        await event_service.create_event(
            session,
            workspace_id=workspace_id,
            event_type="agent.product_knowledge.created",
            entity_type="product_knowledge_entry",
            entity_id=str(row.id),
            payload={
                "entry_type": row.entry_type,
                "product_id": str(experiment.product_id),
                "source_experiment": str(experiment.id),
            },
            trace_id=trace_id,
        )
        created.append(row)
    return created


# --------------------------------------------------------------------------- #
# Scorecard + ROI
# --------------------------------------------------------------------------- #


async def scorecard(session: AsyncSession, *, workspace_id: UUID) -> dict[str, Any]:
    """Workspace-scoped Product Analyst scorecard (no PII, no fabrication)."""
    runs = (
        (
            await session.execute(
                select(ProductAnalysisRun).where(
                    ProductAnalysisRun.workspace_id == workspace_id,
                    ProductAnalysisRun.provider != "deterministic",
                )
            )
        )
        .scalars()
        .all()
    )
    analyzed_products = {row.product_id for row in runs if row.product_id is not None}
    success_runs = [row for row in runs if row.status == "completed"]
    failed_runs = [row for row in runs if row.status != "completed"]

    decisions = (
        (
            await session.execute(
                select(ProductDecision).where(ProductDecision.workspace_id == workspace_id)
            )
        )
        .scalars()
        .all()
    )
    experiments = (
        (
            await session.execute(
                select(ProductExperiment).where(ProductExperiment.workspace_id == workspace_id)
            )
        )
        .scalars()
        .all()
    )
    evaluations = (
        (
            await session.execute(
                select(ProductAiEvaluation).where(ProductAiEvaluation.workspace_id == workspace_id)
            )
        )
        .scalars()
        .all()
    )

    prediction_counts = {"success": 0, "failure": 0, "unknown": 0}
    decision_matches = 0
    decision_compared = 0
    bucket_stats: dict[str, dict[str, int]] = {}
    for evaluation in evaluations:
        result = evaluation.prediction_result or "unknown"
        prediction_counts[result] = prediction_counts.get(result, 0) + 1
        accuracy = evaluation.accuracy or {}
        if accuracy.get("decision_match") is not None:
            decision_compared += 1
            if accuracy["decision_match"] is True:
                decision_matches += 1
        bucket = evaluation.confidence_bucket
        if bucket:
            stats = bucket_stats.setdefault(bucket, {"sample_count": 0, "success_count": 0})
            stats["sample_count"] += 1
            if evaluation.success_flag is True:
                stats["success_count"] += 1

    approved = [d for d in decisions if d.approval_status == "approved"]
    rejected = [d for d in decisions if d.approval_status == "rejected"]
    decided = len(approved) + len(rejected)

    experiment_counts = {
        "proposed": sum(1 for e in experiments if e.status == "proposed"),
        "approved": sum(1 for e in experiments if e.status in ("approved", "ready")),
        "active": sum(1 for e in experiments if e.status == "active"),
        "completed": sum(1 for e in experiments if e.status == "completed"),
    }

    avg_cost = (
        sum((row.estimated_cost or Decimal("0")) for row in runs) / len(runs) if runs else None
    )
    avg_tokens = None
    token_rows = [row.token_usage or {} for row in runs if row.token_usage]
    if token_rows:
        totals = [int(t.get("total_tokens") or 0) for t in token_rows if t.get("total_tokens")]
        avg_tokens = round(sum(totals) / len(totals)) if totals else None
    avg_latency = round(sum(row.latency_ms for row in runs) / len(runs)) if runs else None

    return {
        "workspace_id": str(workspace_id),
        "analyzed_products": len(analyzed_products),
        "analysis_success": len(success_runs),
        "analysis_failed": len(failed_runs),
        "decision_proposed": sum(1 for d in decisions if d.approval_status == "pending"),
        "decision_approved": len(approved),
        "decision_rejected": len(rejected),
        "experiment_proposed": experiment_counts["proposed"],
        "experiment_approved": experiment_counts["approved"],
        "experiment_completed": experiment_counts["completed"],
        "prediction_success": prediction_counts["success"],
        "prediction_failure": prediction_counts["failure"],
        "prediction_unknown": prediction_counts["unknown"],
        "success_rate": (round(len(success_runs) / len(runs), 4) if runs else None),
        "decision_accuracy": (
            round(decision_matches / decision_compared, 4) if decision_compared else None
        ),
        "confidence_buckets": {
            bucket: {
                "sample_count": stats["sample_count"],
                "success_count": stats["success_count"],
                "success_rate": (
                    round(stats["success_count"] / stats["sample_count"], 4)
                    if stats["sample_count"]
                    else None
                ),
            }
            for bucket, stats in sorted(bucket_stats.items())
        },
        "avg_llm_cost": str(avg_cost) if avg_cost is not None else None,
        "avg_tokens": avg_tokens,
        "avg_latency_ms": avg_latency,
        "retry_rate": (round(len(failed_runs) / len(runs), 4) if runs else None),
        "llm_failure_rate": (round(len(failed_runs) / len(runs), 4) if runs else None),
        "human_override_rate": (round(len(rejected) / decided, 4) if decided else None),
    }


async def roi(session: AsyncSession, *, workspace_id: UUID) -> dict[str, Any]:
    """Product Analyst ROI - costs from real runs, impact stays null.

    Business impact (revenue/margin/roas) is only measurable with a real
    attribution pipeline; until then it is explicitly ``null`` - never mocked.
    """
    runs = (
        (
            await session.execute(
                select(ProductAnalysisRun).where(
                    ProductAnalysisRun.workspace_id == workspace_id,
                    ProductAnalysisRun.provider != "deterministic",
                )
            )
        )
        .scalars()
        .all()
    )
    total_llm_cost = sum((row.estimated_cost or Decimal("0")) for row in runs)

    completed = (
        (
            await session.execute(
                select(ProductExperiment).where(
                    ProductExperiment.workspace_id == workspace_id,
                    ProductExperiment.status == "completed",
                )
            )
        )
        .scalars()
        .all()
    )
    successful = 0
    for experiment in completed:
        actual = experiment.actual_result or {}
        prediction = experiment.prediction or {}
        decision_match = None
        if "decision" in prediction and "decision" in actual:
            decision_match = prediction["decision"] == actual["decision"]
        success = ai_evaluation._determine_success(  # noqa: SLF001
            prediction, actual, decision_match
        )
        if success is True:
            successful += 1

    return {
        "workspace_id": str(workspace_id),
        "total_llm_cost": str(total_llm_cost),
        "total_experiments": len(completed),
        "successful_experiments": successful,
        "revenue_impact": None,
        "margin_impact": None,
        "roas_impact": None,
        "agent_cost_per_experiment": (
            str(total_llm_cost / Decimal(len(completed))) if completed else None
        ),
        "agent_cost_per_success": (
            str(total_llm_cost / Decimal(successful)) if successful else None
        ),
        "note": (
            "revenue/margin/roas impacts are null until a real attribution "
            "pipeline links experiments to business outcomes; no figures are simulated"
        ),
    }
