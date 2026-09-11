"""AI evaluation service (M2.2): prediction vs actual calibration data.

Records how well an AI prediction (analysis run output or experiment
prediction) matched the measured actuals. ``accuracy`` is a deterministic
delta map so the scoring model can be calibrated from real outcomes without
any LLM involvement.
"""

import logging
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product_intelligence import (
    ProductAiEvaluation,
    ProductAnalysisRun,
    ProductExperiment,
)
from app.schemas.product_analyst import EvaluationCreate

logger = logging.getLogger(__name__)


class EvaluationError(Exception):
    """Raised when an evaluation cannot be recorded."""


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _flatten(value: dict, prefix: str = "") -> dict:
    """Flatten nested dicts into dotted keys (lists/arrays are skipped)."""
    flat: dict[str, Any] = {}
    for key, item in value.items():
        full = f"{prefix}.{key}" if prefix else key
        if isinstance(item, dict):
            flat.update(_flatten(item, full))
        elif not isinstance(item, (list, tuple)):
            flat[full] = item
    return flat


def compute_accuracy(prediction: dict, actual: dict) -> dict:
    """Compute numeric deltas for keys present in both prediction and actual.

    Nested dicts are flattened to dotted keys (e.g. ``test_plan.kpis.roas``)
    so structured predictions compare against measured actuals. Returns
    ``{"deltas": {key: str(actual - prediction)}, "keys": [...]}`` plus a
    boolean ``decision_match`` when both sides carry a top-level decision.
    Deterministic and JSON-safe (deltas are strings).
    """
    flat_prediction = _flatten(prediction)
    flat_actual = _flatten(actual)
    deltas: dict[str, str] = {}
    for key, predicted_raw in flat_prediction.items():
        if key not in flat_actual:
            continue
        predicted = _decimal(predicted_raw)
        observed = _decimal(flat_actual[key])
        if predicted is not None and observed is not None:
            delta = (observed - predicted).quantize(Decimal("0.0001"), ROUND_HALF_UP)
            deltas[key] = str(delta)
    result: dict[str, Any] = {
        "deltas": deltas,
        "keys": sorted(deltas),
        "decision_match": None,
    }
    if "decision" in prediction and "decision" in actual:
        result["decision_match"] = prediction["decision"] == actual["decision"]
    return result


async def _resolve_prediction(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: EvaluationCreate,
) -> tuple[dict, UUID | None, UUID | None]:
    """Load the prediction snapshot from the linked run/experiment."""
    analysis_run_id = data.analysis_run_id
    experiment_id = data.experiment_id
    if experiment_id is not None:
        experiment = (
            await session.execute(
                select(ProductExperiment).where(
                    ProductExperiment.workspace_id == workspace_id,
                    ProductExperiment.id == experiment_id,
                )
            )
        ).scalar_one_or_none()
        if experiment is None:
            raise EvaluationError("experiment not found")
        return experiment.prediction, analysis_run_id, experiment_id
    if analysis_run_id is not None:
        run = (
            await session.execute(
                select(ProductAnalysisRun).where(
                    ProductAnalysisRun.workspace_id == workspace_id,
                    ProductAnalysisRun.id == analysis_run_id,
                )
            )
        ).scalar_one_or_none()
        if run is None:
            raise EvaluationError("analysis run not found")
        return run.output, analysis_run_id, None
    return {}, None, None


# Confidence buckets used for calibration reporting (LOW < 0.5, MEDIUM
# 0.5-0.7, HIGH > 0.7). Kept as module constants for deterministic behavior.
BUCKET_LOW_MAX = Decimal("0.5")
BUCKET_MEDIUM_MAX = Decimal("0.7")
PREDICTION_RESULTS = ("success", "failure", "unknown")


def _confidence_bucket(confidence: Decimal | None) -> str | None:
    """Map an AI confidence value to LOW / MEDIUM / HIGH (None when absent)."""
    if confidence is None:
        return None
    if confidence < BUCKET_LOW_MAX:
        return "LOW"
    if confidence <= BUCKET_MEDIUM_MAX:
        return "MEDIUM"
    return "HIGH"


def _prediction_confidence(prediction: dict) -> Decimal | None:
    """Extract the AI confidence from a prediction snapshot (any shape)."""
    for key in ("confidence", "predicted_confidence"):
        value = prediction.get(key)
        if value is not None:
            return _decimal(value)
    return None


def _determine_success(
    prediction: dict,
    actual: dict,
    decision_match: bool | None,
) -> bool | None:
    """Deterministic success classification.

    Precedence:
    1. explicit ``success`` boolean in actual_result
    2. top-level decision on both sides -> decision match
    3. roas present -> roas >= 1
    4. margin_rate present -> margin_rate >= 0
    Returns None when no signal is available.
    """
    if "success" in actual and isinstance(actual["success"], bool):
        return actual["success"]
    if decision_match is not None:
        return decision_match
    if "roas" in actual:
        roas = _decimal(actual["roas"])
        if roas is not None:
            return roas >= Decimal("1")
    if "margin_rate" in actual:
        margin = _decimal(actual["margin_rate"])
        if margin is not None:
            return margin >= Decimal("0")
    return None


def _error_type(prediction: dict, actual: dict, decision_match: bool | None) -> str | None:
    """Classify the failure mode when a prediction did not succeed."""
    if decision_match is False:
        return "decision_mismatch"
    if "roas" in actual:
        roas = _decimal(actual["roas"])
        if roas is not None and roas < Decimal("1"):
            return "metric_miss"
    if "margin_rate" in actual:
        margin = _decimal(actual["margin_rate"])
        if margin is not None and margin < Decimal("0"):
            return "margin_miss"
    return "other"


def _metric_snapshot(prediction: dict, actual: dict, decision_match: bool | None) -> dict:
    """JSON-safe summary of the measured metrics relevant to calibration."""
    snapshot: dict[str, Any] = {}
    confidence = _prediction_confidence(prediction)
    if confidence is not None:
        snapshot["confidence"] = str(confidence)
    for key in ("decision", "roas", "conversion_rate", "margin_rate", "return_rate"):
        if prediction.get(key) is not None:
            snapshot[f"predicted_{key}"] = prediction[key]
        if actual.get(key) is not None:
            snapshot[f"actual_{key}"] = actual[key]
    for key in ("units_sold", "revenue", "orders"):
        if actual.get(key) is not None:
            snapshot[key] = actual[key]
    if decision_match is not None:
        snapshot["decision_match"] = decision_match
    return snapshot


async def record_evaluation(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: EvaluationCreate,
    trace_id: str | None = None,
) -> ProductAiEvaluation:
    """Record one AI evaluation (append-only) and emit an audit event."""
    prediction, analysis_run_id, experiment_id = await _resolve_prediction(
        session, workspace_id=workspace_id, data=data
    )
    accuracy = compute_accuracy(prediction, data.actual_result)
    decision_match = accuracy.get("decision_match")
    success_flag = _determine_success(prediction, data.actual_result, decision_match)
    prediction_result = (
        "success" if success_flag is True else "failure" if success_flag is False else "unknown"
    )
    error_type = (
        _error_type(prediction, data.actual_result, decision_match)
        if success_flag is False
        else None
    )
    confidence = _prediction_confidence(prediction)
    evaluation = ProductAiEvaluation(
        workspace_id=workspace_id,
        product_id=data.product_id,
        analysis_run_id=analysis_run_id,
        experiment_id=experiment_id,
        prediction=prediction,
        actual_result=data.actual_result,
        accuracy=accuracy,
        prediction_result=prediction_result,
        error_type=error_type,
        confidence_bucket=_confidence_bucket(confidence),
        success_flag=success_flag,
        metric_snapshot=_metric_snapshot(prediction, data.actual_result, decision_match),
        human_rating=data.human_rating,
        notes=data.notes,
        trace_id=trace_id,
    )
    session.add(evaluation)
    await session.flush()
    from app.services import event_service

    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="product.ai_evaluation.recorded",
        entity_type="product",
        entity_id=str(data.product_id),
        payload={
            "evaluation_id": str(evaluation.id),
            "analysis_run_id": str(analysis_run_id) if analysis_run_id else None,
            "experiment_id": str(experiment_id) if experiment_id else None,
            "human_rating": data.human_rating,
        },
        trace_id=trace_id,
    )
    logger.info(
        "evaluation %s recorded for product %s trace=%s",
        evaluation.id,
        data.product_id,
        trace_id,
    )
    return evaluation


async def list_evaluations(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID | None = None,
    limit: int = 50,
) -> list[ProductAiEvaluation]:
    """List evaluations (newest first), optionally filtered by product."""
    stmt = select(ProductAiEvaluation).where(ProductAiEvaluation.workspace_id == workspace_id)
    if product_id is not None:
        stmt = stmt.where(ProductAiEvaluation.product_id == product_id)
    stmt = stmt.order_by(ProductAiEvaluation.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)
