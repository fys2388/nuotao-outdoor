"""Marketing learning loop service (M3.2).

Turns marketing intelligence into a learning system: campaign predictions are
evaluated against measured outcomes (deterministic classification), creative
analysis runs are audited, knowledge entries accumulate patterns, and
calibration runs surface successful/failure patterns for human approval.

**Boundaries**: no marketing action is executed automatically, no real ad
platform is called, and calibration never modifies marketing rules - it only
produces ``proposed`` suggestions that require human approval.
"""

import logging
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.marketing import (
    Campaign,
    CreativeAsset,
    CustomerFeedback,
    MarketingExperiment,
)
from app.models.marketing_learning import (
    CampaignAiEvaluation,
    CreativeAnalysisRun,
    MarketingCalibrationRun,
    MarketingKnowledgeEntry,
)
from app.schemas.marketing_learning import (
    CampaignEvaluationCreate,
    CreativeAnalysisCreate,
    MarketingKnowledgeCreate,
)
from app.services import ai_evaluation, event_service

logger = logging.getLogger(__name__)

ZERO = Decimal("0")
CALIBRATION_MODEL_VERSION = "marketing-calibration-v1"
MIN_CALIBRATION_SAMPLES = 1


class MarketingLearningError(Exception):
    """Raised when a marketing learning operation cannot complete."""


def _decimal(value: Any) -> Decimal | None:
    return ai_evaluation._decimal(value)


async def _load_campaign(
    session: AsyncSession, *, workspace_id: UUID, campaign_id: UUID
) -> Campaign | None:
    return (
        await session.execute(
            select(Campaign).where(
                Campaign.workspace_id == workspace_id,
                Campaign.id == campaign_id,
            )
        )
    ).scalar_one_or_none()


async def _load_creative(
    session: AsyncSession, *, workspace_id: UUID, creative_id: UUID
) -> CreativeAsset | None:
    return (
        await session.execute(
            select(CreativeAsset).where(
                CreativeAsset.workspace_id == workspace_id,
                CreativeAsset.id == creative_id,
            )
        )
    ).scalar_one_or_none()


def _jsonable(value: Any) -> Any:
    """Convert Decimal/datetime values to JSON-safe primitives."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


# --------------------------------------------------------------------------- #
# 1. Campaign evaluation
# --------------------------------------------------------------------------- #


async def record_campaign_evaluation(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: CampaignEvaluationCreate,
    trace_id: str | None = None,
) -> CampaignAiEvaluation:
    """Record one campaign prediction vs actual evaluation (append-only)."""
    campaign = await _load_campaign(
        session, workspace_id=workspace_id, campaign_id=data.campaign_id
    )
    if campaign is None:
        raise MarketingLearningError("campaign not found")

    accuracy = ai_evaluation.compute_accuracy(data.prediction, data.actual_result)
    decision_match = accuracy.get("decision_match")
    success_flag = ai_evaluation._determine_success(
        data.prediction, data.actual_result, decision_match
    )
    prediction_result = (
        "success" if success_flag is True else "failure" if success_flag is False else "unknown"
    )
    error_type = (
        ai_evaluation._error_type(data.prediction, data.actual_result, decision_match)
        if success_flag is False
        else None
    )
    confidence = ai_evaluation._prediction_confidence(data.prediction)

    evaluation = CampaignAiEvaluation(
        workspace_id=workspace_id,
        campaign_id=data.campaign_id,
        prediction=data.prediction,
        actual_result=data.actual_result,
        accuracy=accuracy,
        prediction_result=prediction_result,
        error_type=error_type,
        confidence=confidence,
        confidence_bucket=ai_evaluation._confidence_bucket(confidence),
        success_flag=success_flag,
        metric_snapshot=ai_evaluation._metric_snapshot(
            data.prediction, data.actual_result, decision_match
        ),
        human_rating=data.human_rating,
        notes=data.notes,
        trace_id=trace_id,
    )
    session.add(evaluation)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="marketing.campaign_evaluation.recorded",
        entity_type="campaign",
        entity_id=str(data.campaign_id),
        payload={
            "evaluation_id": str(evaluation.id),
            "prediction_result": prediction_result,
            "error_type": error_type,
            "human_rating": data.human_rating,
        },
        trace_id=trace_id,
    )
    logger.info(
        "campaign evaluation %s recorded (%s) trace=%s",
        evaluation.id,
        prediction_result,
        trace_id,
    )
    return evaluation


async def list_campaign_evaluations(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    campaign_id: UUID | None = None,
    limit: int = 50,
) -> list[CampaignAiEvaluation]:
    """List campaign evaluations, newest first."""
    stmt = select(CampaignAiEvaluation).where(CampaignAiEvaluation.workspace_id == workspace_id)
    if campaign_id is not None:
        stmt = stmt.where(CampaignAiEvaluation.campaign_id == campaign_id)
    stmt = stmt.order_by(CampaignAiEvaluation.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


# --------------------------------------------------------------------------- #
# 2. Creative intelligence
# --------------------------------------------------------------------------- #


async def create_creative_analysis(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: CreativeAnalysisCreate,
    trace_id: str | None = None,
) -> CreativeAnalysisRun:
    """Audit one analytic pass over a creative asset."""
    creative = await _load_creative(
        session, workspace_id=workspace_id, creative_id=data.creative_id
    )
    if creative is None:
        raise MarketingLearningError("creative not found")

    run = CreativeAnalysisRun(
        workspace_id=workspace_id,
        creative_id=data.creative_id,
        input_snapshot=data.input_snapshot,
        analysis_output=data.analysis_output,
        performance_result=data.performance_result,
        model_version=data.model_version,
        status=data.status,
        trace_id=trace_id,
    )
    session.add(run)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="marketing.creative_analysis.recorded",
        entity_type="creative_asset",
        entity_id=str(data.creative_id),
        payload={
            "run_id": str(run.id),
            "model_version": data.model_version,
            "status": data.status,
        },
        trace_id=trace_id,
    )
    logger.info("creative analysis run %s recorded trace=%s", run.id, trace_id)
    return run


async def list_creative_analysis_runs(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    creative_id: UUID | None = None,
    limit: int = 50,
) -> list[CreativeAnalysisRun]:
    """List creative analysis runs, newest first."""
    stmt = select(CreativeAnalysisRun).where(CreativeAnalysisRun.workspace_id == workspace_id)
    if creative_id is not None:
        stmt = stmt.where(CreativeAnalysisRun.creative_id == creative_id)
    stmt = stmt.order_by(CreativeAnalysisRun.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


# --------------------------------------------------------------------------- #
# 3. Marketing knowledge memory
# --------------------------------------------------------------------------- #


async def create_knowledge_entry(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: MarketingKnowledgeCreate,
    trace_id: str | None = None,
) -> MarketingKnowledgeEntry:
    """Create one marketing knowledge entry (optionally linked to a campaign)."""
    if data.campaign_id is not None:
        campaign = await _load_campaign(
            session, workspace_id=workspace_id, campaign_id=data.campaign_id
        )
        if campaign is None:
            raise MarketingLearningError("campaign not found")
    if data.creative_id is not None:
        creative = await _load_creative(
            session, workspace_id=workspace_id, creative_id=data.creative_id
        )
        if creative is None:
            raise MarketingLearningError("creative not found")

    entry = MarketingKnowledgeEntry(
        workspace_id=workspace_id,
        campaign_id=data.campaign_id,
        creative_id=data.creative_id,
        category=data.category,
        entry_type=data.entry_type,
        title=data.title,
        content=data.content,
        tags=data.tags,
        source=data.source,
        confidence=data.confidence,
        trace_id=trace_id,
    )
    session.add(entry)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="marketing.knowledge.created",
        entity_type="campaign",
        entity_id=str(data.campaign_id) if data.campaign_id else str(workspace_id),
        payload={
            "knowledge_id": str(entry.id),
            "entry_type": data.entry_type,
            "category": data.category,
        },
        trace_id=trace_id,
    )
    logger.info(
        "marketing knowledge entry %s created (%s) trace=%s",
        entry.id,
        data.entry_type,
        trace_id,
    )
    return entry


async def list_knowledge_entries(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    category: str | None = None,
    entry_type: str | None = None,
    campaign_id: UUID | None = None,
    creative_id: UUID | None = None,
    limit: int = 100,
) -> list[MarketingKnowledgeEntry]:
    """Query marketing knowledge entries, newest first."""
    stmt = select(MarketingKnowledgeEntry).where(
        MarketingKnowledgeEntry.workspace_id == workspace_id
    )
    if category:
        stmt = stmt.where(MarketingKnowledgeEntry.category == category)
    if entry_type:
        stmt = stmt.where(MarketingKnowledgeEntry.entry_type == entry_type)
    if campaign_id is not None:
        stmt = stmt.where(MarketingKnowledgeEntry.campaign_id == campaign_id)
    if creative_id is not None:
        stmt = stmt.where(MarketingKnowledgeEntry.creative_id == creative_id)
    stmt = stmt.order_by(MarketingKnowledgeEntry.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


# --------------------------------------------------------------------------- #
# 4. Growth context builder
# --------------------------------------------------------------------------- #


async def build_growth_context(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    campaign_id: UUID,
    trace_id: str | None = None,
) -> dict:
    """Build the full marketing context for one campaign as JSON-safe dict.

    Combines the campaign with its product-linked creatives, experiments and
    feedback plus the campaign's evaluations and knowledge entries - the input
    a future Growth Agent would use, without calling any model.
    """
    campaign = await _load_campaign(session, workspace_id=workspace_id, campaign_id=campaign_id)
    if campaign is None:
        raise MarketingLearningError("campaign not found")

    product_id = campaign.product_id
    creatives: list[CreativeAsset] = []
    experiments: list[MarketingExperiment] = []
    feedback: list[CustomerFeedback] = []
    if product_id is not None:
        creatives = list(
            (
                await session.execute(
                    select(CreativeAsset)
                    .where(
                        CreativeAsset.workspace_id == workspace_id,
                        CreativeAsset.product_id == product_id,
                    )
                    .order_by(CreativeAsset.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        experiments = list(
            (
                await session.execute(
                    select(MarketingExperiment)
                    .where(
                        MarketingExperiment.workspace_id == workspace_id,
                        MarketingExperiment.product_id == product_id,
                    )
                    .order_by(MarketingExperiment.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        feedback = list(
            (
                await session.execute(
                    select(CustomerFeedback)
                    .where(
                        CustomerFeedback.workspace_id == workspace_id,
                        CustomerFeedback.product_id == product_id,
                    )
                    .order_by(CustomerFeedback.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
    evaluations = list(
        (
            await session.execute(
                select(CampaignAiEvaluation)
                .where(
                    CampaignAiEvaluation.workspace_id == workspace_id,
                    CampaignAiEvaluation.campaign_id == campaign_id,
                )
                .order_by(CampaignAiEvaluation.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    knowledge = list(
        (
            await session.execute(
                select(MarketingKnowledgeEntry)
                .where(
                    MarketingKnowledgeEntry.workspace_id == workspace_id,
                    MarketingKnowledgeEntry.campaign_id == campaign_id,
                )
                .order_by(MarketingKnowledgeEntry.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    def _row(row: Any) -> dict:
        return {key: _jsonable(getattr(row, key)) for key in row.__table__.columns.keys()}

    return {
        "campaign": _row(campaign),
        "creatives": [_row(row) for row in creatives],
        "experiments": [_row(row) for row in experiments],
        "feedback": [_row(row) for row in feedback],
        "evaluations": [_row(row) for row in evaluations],
        "knowledge": [_row(row) for row in knowledge],
        "trace_id": trace_id,
    }


# --------------------------------------------------------------------------- #
# 5. Marketing calibration (patterns discovery, human approval only)
# --------------------------------------------------------------------------- #


def _avg_metric(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    total = sum(values, ZERO)
    return (total / Decimal(len(values))).quantize(Decimal("0.0001"), ROUND_HALF_UP)


def _discover_patterns(
    evaluations: list[CampaignAiEvaluation],
    experiments: list[MarketingExperiment],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Deterministically aggregate successful/failure patterns + metrics.

    Success signals: evaluation success (roas/ctr actuals) and experiment
    winners. Failure signals: evaluation error types and negative experiment
    deltas. Returns (successful_patterns, failure_patterns, metrics).
    """
    success_roas: list[Decimal] = []
    success_ctr: list[Decimal] = []
    failure_error_types: dict[str, int] = {}
    success_count = 0
    failure_count = 0
    unknown_count = 0
    for evaluation in evaluations:
        snapshot = evaluation.metric_snapshot
        if evaluation.success_flag is True:
            success_count += 1
            roas = _decimal(snapshot.get("actual_roas"))
            ctr = _decimal(snapshot.get("actual_ctr"))
            if roas is not None:
                success_roas.append(roas)
            if ctr is not None:
                success_ctr.append(ctr)
        elif evaluation.success_flag is False:
            failure_count += 1
            error_type = evaluation.error_type or "other"
            failure_error_types[error_type] = failure_error_types.get(error_type, 0) + 1
        else:
            unknown_count += 1

    experiment_winners = 0
    experiment_negative_deltas: list[str] = []
    for experiment in experiments:
        if experiment.status != "completed":
            continue
        calibration = experiment.calibration or {}
        deltas = calibration.get("deltas", {})
        if experiment.result and experiment.result.get("winner"):
            experiment_winners += 1
        for key, delta_raw in deltas.items():
            delta = _decimal(delta_raw)
            if delta is not None and delta < ZERO:
                experiment_negative_deltas.append(key)

    successful_patterns: dict[str, Any] = {
        "evaluation_success_count": success_count,
        "avg_actual_roas": str(_avg_metric(success_roas)) if success_roas else None,
        "avg_actual_ctr": str(_avg_metric(success_ctr)) if success_ctr else None,
        "experiment_winners": experiment_winners,
    }
    failure_patterns: dict[str, Any] = {
        "evaluation_failure_count": failure_count,
        "error_type_distribution": failure_error_types,
        "experiment_negative_metric_keys": sorted(set(experiment_negative_deltas)),
    }
    metrics: dict[str, Any] = {
        "sample_size": len(evaluations),
        "success_count": success_count,
        "failure_count": failure_count,
        "unknown_count": unknown_count,
        "completed_experiments": sum(
            1 for experiment in experiments if experiment.status == "completed"
        ),
    }
    return successful_patterns, failure_patterns, metrics


async def run_marketing_calibration(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    trace_id: str | None = None,
) -> MarketingCalibrationRun:
    """Discover marketing patterns and propose a calibration (never applied)."""
    evaluations = list(
        (
            await session.execute(
                select(CampaignAiEvaluation)
                .where(CampaignAiEvaluation.workspace_id == workspace_id)
                .order_by(CampaignAiEvaluation.created_at)
            )
        )
        .scalars()
        .all()
    )
    experiments = list(
        (
            await session.execute(
                select(MarketingExperiment)
                .where(MarketingExperiment.workspace_id == workspace_id)
                .order_by(MarketingExperiment.created_at)
            )
        )
        .scalars()
        .all()
    )

    sample_size = len(evaluations)
    if sample_size < MIN_CALIBRATION_SAMPLES:
        raise MarketingLearningError(
            f"not enough evaluations (need >= {MIN_CALIBRATION_SAMPLES}, got {sample_size})"
        )

    successful_patterns, failure_patterns, metrics = _discover_patterns(evaluations, experiments)
    run = MarketingCalibrationRun(
        workspace_id=workspace_id,
        status="proposed",
        model_version=CALIBRATION_MODEL_VERSION,
        input_snapshot={
            "model_version": CALIBRATION_MODEL_VERSION,
            "sample_size": sample_size,
            "evaluation_count": sample_size,
            "experiment_count": len(experiments),
        },
        successful_patterns=successful_patterns,
        failure_patterns=failure_patterns,
        metrics=metrics,
        sample_size=sample_size,
        rationale=(
            "Deterministic pattern discovery from campaign evaluations and "
            "completed experiments. Proposal only - marketing rules are never "
            "modified automatically."
        ),
        trace_id=trace_id,
    )
    session.add(run)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="marketing.calibration_run_proposed",
        entity_type="workspace",
        entity_id=str(workspace_id),
        payload={
            "run_id": str(run.id),
            "sample_size": sample_size,
            "success_count": metrics["success_count"],
            "failure_count": metrics["failure_count"],
        },
        trace_id=trace_id,
    )
    logger.info(
        "marketing calibration run %s proposed (n=%s) trace=%s",
        run.id,
        sample_size,
        trace_id,
    )
    return run


async def _load_calibration_run(
    session: AsyncSession, *, workspace_id: UUID, run_id: UUID
) -> MarketingCalibrationRun | None:
    return (
        await session.execute(
            select(MarketingCalibrationRun).where(
                MarketingCalibrationRun.workspace_id == workspace_id,
                MarketingCalibrationRun.id == run_id,
            )
        )
    ).scalar_one_or_none()


async def approve_marketing_calibration(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    run_id: UUID,
    actor: str,
    note: str | None = None,
    trace_id: str | None = None,
) -> MarketingCalibrationRun:
    """Approve a marketing calibration proposal (human-only)."""
    run = await _load_calibration_run(session, workspace_id=workspace_id, run_id=run_id)
    if run is None:
        raise MarketingLearningError("calibration run not found")
    if run.status != "proposed":
        raise MarketingLearningError("calibration run is not proposed")
    now = datetime.now(UTC)
    run.status = "approved"
    run.approved_by = actor
    run.approved_at = now
    run.updated_at = now
    if note:
        run.rationale = (run.rationale or "") + f" | approved note: {note}"
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="marketing.calibration_run_approved",
        entity_type="workspace",
        entity_id=str(workspace_id),
        payload={"run_id": str(run.id), "approved_by": actor, "note": note},
        trace_id=trace_id,
    )
    return run


async def reject_marketing_calibration(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    run_id: UUID,
    actor: str,
    note: str | None = None,
    trace_id: str | None = None,
) -> MarketingCalibrationRun:
    """Reject a marketing calibration proposal (human-only)."""
    run = await _load_calibration_run(session, workspace_id=workspace_id, run_id=run_id)
    if run is None:
        raise MarketingLearningError("calibration run not found")
    if run.status != "proposed":
        raise MarketingLearningError("calibration run is not proposed")
    now = datetime.now(UTC)
    run.status = "rejected"
    run.approved_by = actor
    run.approved_at = now
    run.updated_at = now
    if note:
        run.rationale = (run.rationale or "") + f" | rejected note: {note}"
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="marketing.calibration_run_rejected",
        entity_type="workspace",
        entity_id=str(workspace_id),
        payload={"run_id": str(run.id), "rejected_by": actor, "note": note},
        trace_id=trace_id,
    )
    return run


async def list_marketing_calibration_runs(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    status: str | None = None,
    limit: int = 50,
) -> list[MarketingCalibrationRun]:
    """List marketing calibration runs, newest first."""
    stmt = select(MarketingCalibrationRun).where(
        MarketingCalibrationRun.workspace_id == workspace_id
    )
    if status:
        stmt = stmt.where(MarketingCalibrationRun.status == status)
    stmt = stmt.order_by(MarketingCalibrationRun.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)
