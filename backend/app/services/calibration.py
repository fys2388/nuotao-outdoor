"""Calibration services (M2.3): the Product Analyst learning loop.

Two calibration outputs:

- Confidence report (:func:`generate_confidence_report`): aggregates AI
  confidence buckets against measured success rates.
- Score model calibration (:func:`run_score_calibration`): deterministically
  suggests six-dimension weight adjustments from historical experiments,
  AI predictions and actual outcomes.

**Approval protection**: a calibration run is only a ``proposed`` suggestion.
Approving it records the human decision (and the suggested weights for the
next model version) but **never modifies the rules registry or the scoring
code** - version updates are applied by humans from the approved proposal.
"""

import logging
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product_intelligence import (
    ConfidenceCalibration,
    ProductAiEvaluation,
    ProductExperiment,
    ProductScore,
    ProductScoreCalibrationRun,
    ProductScoreEvidence,
)
from app.schemas.calibration import CalibrationApproveRequest
from app.services import ai_evaluation, event_service
from app.services.product_intelligence import SCORE_MODEL_VERSION, SCORE_WEIGHTS

logger = logging.getLogger(__name__)

ZERO = Decimal("0")
DIMENSIONS = tuple(SCORE_WEIGHTS.keys())

# Minimum completed experiments before weight changes are suggested.
MIN_CALIBRATION_SAMPLES = 3


class CalibrationError(Exception):
    """Raised when a calibration operation cannot complete."""


def _normalize_weights(weights: dict[str, Decimal]) -> dict[str, Decimal]:
    """Quantize to 0.01 and force the total to exactly 1.00."""
    total = sum(weights.values(), Decimal("0"))
    if total <= ZERO:
        return dict.fromkeys(DIMENSIONS, ZERO)
    quantized = {
        key: (value / total * Decimal("1")).quantize(Decimal("0.01"), ROUND_HALF_UP)
        for key, value in weights.items()
    }
    remainder = Decimal("1") - sum(quantized.values(), Decimal("0"))
    # Distribute the rounding remainder on the first dimension.
    first = DIMENSIONS[0]
    quantized[first] = (quantized[first] + remainder).quantize(Decimal("0.01"))
    return quantized


async def _completed_experiments(
    session: AsyncSession, *, workspace_id: UUID
) -> list[ProductExperiment]:
    rows = (
        (
            await session.execute(
                select(ProductExperiment)
                .where(
                    ProductExperiment.workspace_id == workspace_id,
                    ProductExperiment.status == "completed",
                )
                .order_by(ProductExperiment.created_at)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def _dimension_confidences(
    session: AsyncSession, *, workspace_id: UUID, product_id: UUID
) -> dict[str, Decimal]:
    """Latest per-dimension evidence confidence for a product's newest score."""
    score = (
        (
            await session.execute(
                select(ProductScore)
                .where(
                    ProductScore.workspace_id == workspace_id,
                    ProductScore.product_id == product_id,
                )
                .order_by(ProductScore.scored_at.desc())
            )
        )
        .scalars()
        .first()
    )
    if score is None:
        return {}
    rows = (
        (
            await session.execute(
                select(ProductScoreEvidence).where(
                    ProductScoreEvidence.workspace_id == workspace_id,
                    ProductScoreEvidence.product_score_id == score.id,
                )
            )
        )
        .scalars()
        .all()
    )
    return {row.dimension: row.confidence for row in rows}


async def generate_confidence_report(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    trace_id: str | None = None,
) -> list[ConfidenceCalibration]:
    """Aggregate AI confidence buckets vs measured success rate.

    Upserts one row per bucket (LOW / MEDIUM / HIGH) for the workspace.
    Evaluations without a confidence bucket or a success signal are excluded.
    """
    rows = (
        (
            await session.execute(
                select(ProductAiEvaluation).where(
                    ProductAiEvaluation.workspace_id == workspace_id,
                    ProductAiEvaluation.confidence_bucket.is_not(None),
                    ProductAiEvaluation.success_flag.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )

    aggregates: dict[str, dict[str, Any]] = {
        "LOW": {"count": 0, "success": 0, "confidence_sum": Decimal("0")},
        "MEDIUM": {"count": 0, "success": 0, "confidence_sum": Decimal("0")},
        "HIGH": {"count": 0, "success": 0, "confidence_sum": Decimal("0")},
    }
    for row in rows:
        bucket = row.confidence_bucket or ""
        aggregate = aggregates.get(bucket)
        if aggregate is None:
            continue
        aggregate["count"] += 1
        if row.success_flag:
            aggregate["success"] += 1
        confidence = ai_evaluation._prediction_confidence(row.prediction)
        if confidence is not None:
            aggregate["confidence_sum"] += confidence

    existing = (
        (
            await session.execute(
                select(ConfidenceCalibration).where(
                    ConfidenceCalibration.workspace_id == workspace_id
                )
            )
        )
        .scalars()
        .all()
    )
    by_bucket = {row.bucket: row for row in existing}
    now = datetime.now(UTC)
    report_rows: list[ConfidenceCalibration] = []
    for bucket, aggregate in aggregates.items():
        count = aggregate["count"]
        success = aggregate["success"]
        row = by_bucket.get(bucket)
        if row is None:
            row = ConfidenceCalibration(workspace_id=workspace_id, bucket=bucket, trace_id=trace_id)
            session.add(row)
        row.sample_count = count
        row.success_count = success
        row.success_rate = (
            (Decimal(success) / Decimal(count)).quantize(Decimal("0.0001"), ROUND_HALF_UP)
            if count
            else ZERO
        )
        row.avg_confidence = (
            (aggregate["confidence_sum"] / Decimal(count)).quantize(
                Decimal("0.0001"), ROUND_HALF_UP
            )
            if count
            else ZERO
        )
        row.computed_at = now
        report_rows.append(row)
    await session.flush()

    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="calibration.confidence_report_generated",
        entity_type="workspace",
        entity_id=str(workspace_id),
        payload={
            "buckets": {
                bucket: {
                    "sample_count": aggregates[bucket]["count"],
                    "success_count": aggregates[bucket]["success"],
                }
                for bucket in aggregates
            }
        },
        trace_id=trace_id,
    )
    logger.info("confidence calibration report generated trace=%s", trace_id)
    return report_rows


async def run_score_calibration(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    trace_id: str | None = None,
) -> ProductScoreCalibrationRun:
    """Generate a score weight adjustment proposal from real outcomes.

    The suggestion is deterministic and **never applied automatically**.
    """
    experiments = await _completed_experiments(session, workspace_id=workspace_id)

    # Per-dimension confidence stats grouped by actual success/failure.
    stats: dict[str, dict[str, Any]] = {
        dimension: {
            "conf_success": Decimal("0"),
            "conf_failure": Decimal("0"),
            "conf_all": Decimal("0"),
            "n_success": 0,
            "n_failure": 0,
            "n_all": 0,
        }
        for dimension in DIMENSIONS
    }
    sample_rows: list[dict[str, Any]] = []
    for experiment in experiments:
        actual = experiment.actual_result or {}
        prediction = experiment.prediction or {}
        decision_match = None
        if "decision" in prediction and "decision" in actual:
            decision_match = prediction["decision"] == actual["decision"]
        success = ai_evaluation._determine_success(
            prediction, actual, decision_match
        )
        confidences = await _dimension_confidences(
            session, workspace_id=workspace_id, product_id=experiment.product_id
        )
        sample_rows.append(
            {
                "product_id": str(experiment.product_id),
                "experiment_id": str(experiment.id),
                "success": success,
                "roas": actual.get("roas"),
                "decision": actual.get("decision"),
            }
        )
        for dimension in DIMENSIONS:
            confidence = confidences.get(dimension, Decimal("0"))
            stats[dimension]["conf_all"] += confidence
            stats[dimension]["n_all"] += 1
            if success is True:
                stats[dimension]["conf_success"] += confidence
                stats[dimension]["n_success"] += 1
            elif success is False:
                stats[dimension]["conf_failure"] += confidence
                stats[dimension]["n_failure"] += 1

    sample_size = len(experiments)
    current_weights = {key: Decimal(str(value)) for key, value in SCORE_WEIGHTS.items()}
    if sample_size < MIN_CALIBRATION_SAMPLES:
        suggested_weights = current_weights
        rationale = (
            f"insufficient completed experiments ({sample_size} < "
            f"{MIN_CALIBRATION_SAMPLES}); weights unchanged"
        )
    else:
        # Weight each dimension by the ratio of success-confidence to the
        # overall confidence average, then normalize to sum 1.00.
        adjusted: dict[str, Decimal] = {}
        for dimension in DIMENSIONS:
            stat = stats[dimension]
            avg_all = stat["conf_all"] / Decimal(stat["n_all"]) if stat["n_all"] else ZERO
            ratio = (
                stat["conf_success"] / Decimal(stat["n_success"]) / avg_all
                if stat["n_success"] and avg_all > ZERO
                else Decimal("1")
            )
            adjusted[dimension] = current_weights[dimension] * ratio
        suggested_weights = _normalize_weights(adjusted)
        rationale = (
            "weight shift follows the observed correlation between per-dimension "
            "evidence confidence and experiment success (proposal only)"
        )

    metrics = {
        dimension: {
            "avg_confidence_all": str(
                (stat["conf_all"] / Decimal(stat["n_all"])).quantize(Decimal("0.0001"))
                if stat["n_all"]
                else "0"
            ),
            "avg_confidence_success": str(
                (stat["conf_success"] / Decimal(stat["n_success"])).quantize(Decimal("0.0001"))
                if stat["n_success"]
                else None
            ),
            "avg_confidence_failure": str(
                (stat["conf_failure"] / Decimal(stat["n_failure"])).quantize(Decimal("0.0001"))
                if stat["n_failure"]
                else None
            ),
            "n_success": stat["n_success"],
            "n_failure": stat["n_failure"],
        }
        for dimension, stat in stats.items()
    }

    run = ProductScoreCalibrationRun(
        workspace_id=workspace_id,
        status="proposed",
        model_version=SCORE_MODEL_VERSION,
        current_weights={key: str(value) for key, value in current_weights.items()},
        suggested_weights={key: str(value) for key, value in suggested_weights.items()},
        input_snapshot={
            "model_version": SCORE_MODEL_VERSION,
            "sample_size": sample_size,
            "experiments": sample_rows,
        },
        metrics=metrics,
        sample_size=sample_size,
        rationale=rationale,
        trace_id=trace_id,
    )
    session.add(run)
    await session.flush()

    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="calibration.score_run_proposed",
        entity_type="workspace",
        entity_id=str(workspace_id),
        payload={
            "run_id": str(run.id),
            "sample_size": sample_size,
            "suggested_weights": run.suggested_weights,
        },
        trace_id=trace_id,
    )
    # M5.4: surface calibration proposals in the unified Approval Center.
    from app.services.approval_service import ensure_approval

    await ensure_approval(
        session,
        workspace_id=workspace_id,
        approval_type="CALIBRATION",
        entity_type="score_calibration_run",
        entity_id=str(run.id),
        metadata_={"suggested_weights": run.suggested_weights},
        trace_id=trace_id,
    )
    logger.info(
        "score calibration run %s proposed (n=%s) trace=%s",
        run.id,
        sample_size,
        trace_id,
    )
    return run


async def _load_run(
    session: AsyncSession, *, workspace_id: UUID, run_id: UUID
) -> ProductScoreCalibrationRun | None:
    return (
        await session.execute(
            select(ProductScoreCalibrationRun).where(
                ProductScoreCalibrationRun.workspace_id == workspace_id,
                ProductScoreCalibrationRun.id == run_id,
            )
        )
    ).scalar_one_or_none()


async def approve_calibration(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    run_id: UUID,
    data: CalibrationApproveRequest,
    trace_id: str | None = None,
) -> ProductScoreCalibrationRun:
    """Approve a calibration proposal (human-only; rules are never auto-edited).

    Approval records the human decision and keeps the suggested weights on the
    run row for the next score model version rollout. The rules registry and
    the scoring code stay untouched.
    """
    run = await _load_run(session, workspace_id=workspace_id, run_id=run_id)
    if run is None:
        raise CalibrationError("calibration run not found")
    if run.status != "proposed":
        raise CalibrationError("calibration run is not proposed")
    now = datetime.now(UTC)
    run.status = "approved"
    run.approved_by = data.actor
    run.approved_at = now
    run.updated_at = now
    if data.note:
        run.rationale = (run.rationale or "") + f" | approved note: {data.note}"
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="calibration.score_run_approved",
        entity_type="workspace",
        entity_id=str(workspace_id),
        payload={
            "run_id": str(run.id),
            "approved_by": data.actor,
            "suggested_weights": run.suggested_weights,
            "note": data.note,
        },
        trace_id=trace_id,
    )
    logger.info("calibration run %s approved by %s trace=%s", run.id, data.actor, trace_id)
    from app.services.approval_service import sync_approval

    await sync_approval(
        session,
        workspace_id=workspace_id,
        approval_type="CALIBRATION",
        entity_id=str(run.id),
        decision="approved",
        actor=data.actor,
        note=data.note,
        trace_id=trace_id,
    )
    return run


async def reject_calibration(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    run_id: UUID,
    data: CalibrationApproveRequest,
    trace_id: str | None = None,
) -> ProductScoreCalibrationRun:
    """Reject a calibration proposal (human-only; no weight changes)."""
    run = await _load_run(session, workspace_id=workspace_id, run_id=run_id)
    if run is None:
        raise CalibrationError("calibration run not found")
    if run.status != "proposed":
        raise CalibrationError("calibration run is not proposed")
    now = datetime.now(UTC)
    run.status = "rejected"
    run.approved_by = data.actor
    run.approved_at = now
    run.updated_at = now
    if data.note:
        run.rationale = (run.rationale or "") + f" | rejected note: {data.note}"
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="calibration.score_run_rejected",
        entity_type="workspace",
        entity_id=str(workspace_id),
        payload={"run_id": str(run.id), "rejected_by": data.actor, "note": data.note},
        trace_id=trace_id,
    )
    from app.services.approval_service import sync_approval

    await sync_approval(
        session,
        workspace_id=workspace_id,
        approval_type="CALIBRATION",
        entity_id=str(run.id),
        decision="rejected",
        actor=data.actor,
        note=data.note,
        trace_id=trace_id,
    )
    return run


async def list_calibration_runs(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    status: str | None = None,
    limit: int = 50,
) -> list[ProductScoreCalibrationRun]:
    """List calibration runs, newest first."""
    stmt = select(ProductScoreCalibrationRun).where(
        ProductScoreCalibrationRun.workspace_id == workspace_id
    )
    if status:
        stmt = stmt.where(ProductScoreCalibrationRun.status == status)
    stmt = stmt.order_by(ProductScoreCalibrationRun.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)
