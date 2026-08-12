"""Unified agent evaluation bridge (M5.2.1).

M5.0 ``agent_evaluations`` (generic agent-level prediction vs actual) and
M2.3 ``product_ai_evaluations`` (product-domain evaluation that feeds score
calibration) carry overlapping semantics: prediction / actual_result /
accuracy / confidence bucket / success flag / error type. This bridge is the
single mapping layer between them:

- classification logic lives ONCE in ``ai_evaluation`` (``compute_accuracy``,
  ``_determine_success``, ``_error_type``, ``_confidence_bucket``,
  ``_prediction_confidence``); ``agent_runtime.record_evaluation`` reuses
  those helpers, and this bridge never re-implements them;
- ``record_agent_evaluation`` writes the M5 agent row and, when a product
  domain link is supplied, mirrors the M2.3 product row through
  ``ai_evaluation.record_evaluation`` (append-only, one call);
- ``backfill_agent_evaluation`` appends measured actuals to the linked
  product evaluation so M2.3 calibration (confidence report + score run)
  consumes real outcomes;
- ``sync_calibration_to_knowledge`` closes the loop (calibration -> knowledge)
  and may only run on a human-approved calibration proposal.

Safety: the bridge never edits SCORE_WEIGHTS or rules; calibration stays
``proposed`` until a human approves/rejects (M2.3 service enforces this).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_runtime import AgentEvaluation
from app.models.product_intelligence import ProductScoreCalibrationRun
from app.schemas.agent_runtime import AgentEvaluationCreate
from app.schemas.knowledge import KnowledgeEntryCreate
from app.schemas.product_analyst import EvaluationCreate
from app.services import agent_runtime, ai_evaluation, event_service, knowledge

logger = logging.getLogger(__name__)

# Reserved metadata key inside an AgentEvaluation prediction that records the
# product-domain link used to mirror the M2.3 evaluation row.
DOMAIN_META_KEY = "_domain"


class EvaluationBridgeError(Exception):
    """Raised when an evaluation cannot be bridged between domains."""


@dataclass(frozen=True)
class ProductDomainLink:
    """Link an agent evaluation to the product-analysis domain."""

    product_id: UUID
    analysis_run_id: UUID | None = None


def extract_product_link(prediction: dict[str, Any]) -> ProductDomainLink | None:
    """Read a product link from the reserved prediction metadata (if any)."""
    meta = (prediction or {}).get(DOMAIN_META_KEY)
    if not isinstance(meta, dict) or meta.get("domain") != "product":
        return None
    product_id = meta.get("product_id")
    if product_id is None:
        return None
    analysis_run_id = meta.get("analysis_run_id")
    return ProductDomainLink(
        product_id=UUID(str(product_id)),
        analysis_run_id=UUID(str(analysis_run_id)) if analysis_run_id else None,
    )


def _with_link(prediction: dict[str, Any], link: ProductDomainLink) -> dict[str, Any]:
    """Return a copy of the prediction carrying the product link metadata."""
    snapshot = dict(prediction or {})
    snapshot[DOMAIN_META_KEY] = {
        "domain": "product",
        "product_id": str(link.product_id),
        "analysis_run_id": str(link.analysis_run_id) if link.analysis_run_id else None,
    }
    return snapshot


async def record_agent_evaluation(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent_id: UUID,
    prediction: dict[str, Any],
    actual_result: dict[str, Any] | None = None,
    domain: ProductDomainLink | None = None,
    human_rating: int | None = None,
    notes: str | None = None,
    trace_id: str | None = None,
) -> AgentEvaluation:
    """Write the M5 agent evaluation and mirror the product-domain row.

    The M5 row keeps its classification fields; the product row is appended
    through ``ai_evaluation.record_evaluation`` so M2.3 calibration sees the
    same prediction. A bridge event records the mapping for audit.
    """
    actual = actual_result or {}
    link = domain or extract_product_link(prediction)
    stored_prediction = _with_link(prediction, link) if link else dict(prediction or {})

    agent_evaluation = await agent_runtime.record_evaluation(
        session,
        workspace_id=workspace_id,
        data=AgentEvaluationCreate(
            agent_id=agent_id,
            prediction=stored_prediction,
            actual_result=actual,
            human_rating=human_rating,
            notes=notes,
        ),
        trace_id=trace_id,
    )

    if link is not None:
        product_evaluation = await ai_evaluation.record_evaluation(
            session,
            workspace_id=workspace_id,
            data=EvaluationCreate(
                product_id=link.product_id,
                analysis_run_id=link.analysis_run_id,
                actual_result=actual,
                human_rating=human_rating,
                notes=notes,
            ),
            trace_id=trace_id,
        )
        await event_service.create_event(
            session,
            workspace_id=workspace_id,
            event_type="agent.evaluation.domain_mirrored",
            entity_type="agent_evaluation",
            entity_id=str(agent_evaluation.id),
            payload={
                "domain": "product",
                "product_evaluation_id": str(product_evaluation.id),
                "analysis_run_id": str(link.analysis_run_id) if link.analysis_run_id else None,
            },
            trace_id=trace_id,
        )
        logger.info(
            "agent evaluation %s mirrored to product evaluation %s trace=%s",
            agent_evaluation.id,
            product_evaluation.id,
            trace_id,
        )
    return agent_evaluation


async def backfill_agent_evaluation(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    evaluation_id: UUID,
    actual_result: dict[str, Any],
    trace_id: str | None = None,
) -> AgentEvaluation:
    """Backfill measured actuals into an agent evaluation and its mirror.

    Recomputes classification with the shared ``ai_evaluation`` helpers and
    appends a new product-domain evaluation row (append-only actuals), which
    is what M2.3 confidence reports and score calibration consume.
    """
    evaluation = (
        await session.execute(
            select(AgentEvaluation).where(
                AgentEvaluation.workspace_id == workspace_id,
                AgentEvaluation.id == evaluation_id,
            )
        )
    ).scalar_one_or_none()
    if evaluation is None:
        raise EvaluationBridgeError("agent evaluation not found")

    prediction = evaluation.prediction or {}
    accuracy = ai_evaluation.compute_accuracy(prediction, actual_result)
    decision_match = accuracy.get("decision_match")
    success_flag = ai_evaluation._determine_success(prediction, actual_result, decision_match)
    prediction_result = (
        "success" if success_flag is True else "failure" if success_flag is False else "unknown"
    )
    error_type = (
        ai_evaluation._error_type(prediction, actual_result, decision_match)
        if success_flag is False
        else None
    )
    confidence = ai_evaluation._prediction_confidence(prediction)
    bucket = ai_evaluation._confidence_bucket(confidence)

    evaluation.actual_result = actual_result
    evaluation.accuracy = accuracy
    evaluation.prediction_result = prediction_result
    evaluation.error_type = error_type
    evaluation.success_flag = success_flag
    evaluation.confidence = confidence
    evaluation.confidence_bucket = bucket
    evaluation.calibration = {
        "confidence": str(confidence) if confidence is not None else None,
        "bucket": bucket,
        "prediction_result": prediction_result,
        "success_flag": success_flag,
        "sample_size": 1,
    }
    await session.flush()

    link = extract_product_link(prediction)
    if link is not None:
        product_evaluation = await ai_evaluation.record_evaluation(
            session,
            workspace_id=workspace_id,
            data=EvaluationCreate(
                product_id=link.product_id,
                analysis_run_id=link.analysis_run_id,
                actual_result=actual_result,
            ),
            trace_id=trace_id,
        )
        await event_service.create_event(
            session,
            workspace_id=workspace_id,
            event_type="agent.evaluation.actual_backfilled",
            entity_type="agent_evaluation",
            entity_id=str(evaluation.id),
            payload={
                "product_evaluation_id": str(product_evaluation.id),
                "prediction_result": prediction_result,
                "error_type": error_type,
            },
            trace_id=trace_id,
        )
    return evaluation


async def sync_calibration_to_knowledge(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    run_id: UUID,
    trace_id: str | None = None,
):
    """Close the calibration -> knowledge leg of the learning loop.

    Only a human-approved calibration run may be distilled into knowledge;
    proposed/rejected runs raise, so knowledge never reflects unapproved
    suggestions. Rules and SCORE_WEIGHTS are never modified here.
    """
    run = (
        await session.execute(
            select(ProductScoreCalibrationRun).where(
                ProductScoreCalibrationRun.workspace_id == workspace_id,
                ProductScoreCalibrationRun.id == run_id,
            )
        )
    ).scalar_one_or_none()
    if run is None:
        raise EvaluationBridgeError("calibration run not found")
    if run.status != "approved":
        raise EvaluationBridgeError("only an approved calibration run can sync to knowledge")

    suggested = run.suggested_weights or {}
    content = (
        f"Approved score-model calibration ({run.model_version}): "
        + ", ".join(f"{dim}={value}" for dim, value in sorted(suggested.items()))
        + f" | rationale: {run.rationale or ''}"
    )
    entry = await knowledge.create_knowledge_entry(
        session,
        workspace_id=workspace_id,
        data=KnowledgeEntryCreate(
            category="score_model",
            entry_type="category_insight",
            title="Score calibration approved",
            content=content,
            tags=["score_model", run.model_version, "calibration"],
            source="calibration",
        ),
        trace_id=trace_id,
    )
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.evaluation.calibration_knowledge_synced",
        entity_type="agent_evaluation",
        entity_id=str(run.id),
        payload={"knowledge_id": str(entry.id), "model_version": run.model_version},
        trace_id=trace_id,
    )
    return entry
