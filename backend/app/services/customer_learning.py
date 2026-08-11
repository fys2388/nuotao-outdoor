"""Customer learning loop service (M3.4).

Upgrades customer intelligence to a learning layer: predicted behaviors are
evaluated against actual behavior (deterministic classification), pattern
mining runs surface purchase/segment/bundle/churn/pain patterns, and
calibration proposals require human approval. The cross-domain context builder
combines customer data for future agents.

**Boundaries**: no Customer Agent, no automatic customer support, and no
business rule is ever modified automatically.
"""

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import class_mapper

from app.models.customer import (
    CustomerInteraction,
    CustomerKnowledgeEntry,
    CustomerProfile,
    ProductReview,
    RefundCase,
)
from app.models.customer_learning import (
    CustomerAiEvaluation,
    CustomerCalibrationRun,
    CustomerPatternRun,
)
from app.models.marketing import Campaign
from app.models.order import Order
from app.models.product import Product
from app.schemas.customer_learning import (
    CustomerEvaluationCreate,
    PatternRunRequest,
)
from app.services import ai_evaluation, event_service

logger = logging.getLogger(__name__)

ZERO = Decimal("0")
CALIBRATION_MODEL_VERSION = "customer-calibration-v1"
MIN_CALIBRATION_SAMPLES = 1
PATTERN_TYPES: tuple[str, ...] = (
    "purchase_pattern",
    "segment_pattern",
    "bundle_pattern",
    "churn_pattern",
    "pain_pattern",
)


class CustomerLearningError(Exception):
    """Raised when a customer learning operation cannot complete."""


def _decimal(value: Any) -> Decimal | None:
    return ai_evaluation._decimal(value)  # noqa: SLF001


async def _load_profile(
    session: AsyncSession, *, workspace_id: UUID, customer_id: UUID
) -> CustomerProfile | None:
    return (
        await session.execute(
            select(CustomerProfile).where(
                CustomerProfile.workspace_id == workspace_id,
                CustomerProfile.id == customer_id,
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
# 1. Customer evaluation
# --------------------------------------------------------------------------- #


async def record_customer_evaluation(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: CustomerEvaluationCreate,
    trace_id: str | None = None,
) -> CustomerAiEvaluation:
    """Record one predicted-vs-actual customer behavior evaluation (append-only)."""
    profile = await _load_profile(
        session, workspace_id=workspace_id, customer_id=data.customer_id
    )
    if profile is None:
        raise CustomerLearningError("customer profile not found")

    accuracy = ai_evaluation.compute_accuracy(data.prediction, data.actual_behavior)
    decision_match = accuracy.get("decision_match")
    success_flag = ai_evaluation._determine_success(  # noqa: SLF001
        data.prediction, data.actual_behavior, decision_match
    )
    prediction_result = (
        "success"
        if success_flag is True
        else "failure"
        if success_flag is False
        else "unknown"
    )
    error_type = (
        ai_evaluation._error_type(  # noqa: SLF001
            data.prediction, data.actual_behavior, decision_match
        )
        if success_flag is False
        else None
    )
    confidence = ai_evaluation._prediction_confidence(data.prediction)  # noqa: SLF001

    evaluation = CustomerAiEvaluation(
        workspace_id=workspace_id,
        customer_id=data.customer_id,
        prediction=data.prediction,
        actual_behavior=data.actual_behavior,
        accuracy=accuracy,
        prediction_result=prediction_result,
        error_type=error_type,
        confidence=confidence,
        confidence_bucket=ai_evaluation._confidence_bucket(confidence),  # noqa: SLF001
        success_flag=success_flag,
        metric_snapshot=ai_evaluation._metric_snapshot(  # noqa: SLF001
            data.prediction, data.actual_behavior, decision_match
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
        event_type="customer.evaluation_recorded",
        entity_type="customer_profile",
        entity_id=str(data.customer_id),
        payload={
            "evaluation_id": str(evaluation.id),
            "prediction_result": prediction_result,
            "error_type": error_type,
            "human_rating": data.human_rating,
        },
        trace_id=trace_id,
    )
    logger.info(
        "customer evaluation %s recorded (%s) trace=%s",
        evaluation.id, prediction_result, trace_id,
    )
    return evaluation


async def list_customer_evaluations(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    customer_id: UUID | None = None,
    limit: int = 50,
) -> list[CustomerAiEvaluation]:
    """List customer evaluations, newest first."""
    stmt = select(CustomerAiEvaluation).where(
        CustomerAiEvaluation.workspace_id == workspace_id
    )
    if customer_id is not None:
        stmt = stmt.where(CustomerAiEvaluation.customer_id == customer_id)
    stmt = stmt.order_by(CustomerAiEvaluation.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


# --------------------------------------------------------------------------- #
# 2. Customer pattern mining
# --------------------------------------------------------------------------- #


def _pattern_confidence(sample_size: int) -> Decimal:
    """Deterministic heuristic confidence: 0.1 per sample, capped at 0.9."""
    if sample_size <= 0:
        return ZERO
    raw = Decimal(sample_size) * Decimal("0.1")
    return min(raw, Decimal("0.9")).quantize(Decimal("0.0001"))


async def _pattern_inputs(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    customer_id: UUID | None,
) -> tuple[list[CustomerProfile], list[CustomerAiEvaluation], list[RefundCase]]:
    profiles_stmt = select(CustomerProfile).where(
        CustomerProfile.workspace_id == workspace_id
    )
    evaluations_stmt = select(CustomerAiEvaluation).where(
        CustomerAiEvaluation.workspace_id == workspace_id
    )
    refunds_stmt = select(RefundCase).where(RefundCase.workspace_id == workspace_id)
    if customer_id is not None:
        profiles_stmt = profiles_stmt.where(CustomerProfile.id == customer_id)
        evaluations_stmt = evaluations_stmt.where(
            CustomerAiEvaluation.customer_id == customer_id
        )
        refunds_stmt = refunds_stmt.where(RefundCase.customer_id == customer_id)
    profiles = list((await session.execute(profiles_stmt)).scalars().all())
    evaluations = list((await session.execute(evaluations_stmt)).scalars().all())
    refunds = list((await session.execute(refunds_stmt)).scalars().all())
    return profiles, evaluations, refunds


def _extract_pattern(
    pattern_type: str,
    profiles: list[CustomerProfile],
    evaluations: list[CustomerAiEvaluation],
    refunds: list[RefundCase],
) -> tuple[dict[str, Any], int]:
    """Deterministically extract one pattern type from the inputs."""
    if pattern_type == "purchase_pattern":
        revenue_sum = sum((profile.total_revenue or ZERO) for profile in profiles)
        order_sum = sum(profile.total_orders or 0 for profile in profiles)
        return {
            "profile_count": len(profiles),
            "avg_total_orders": (
                str(Decimal(order_sum) / Decimal(len(profiles))) if profiles else None
            ),
            "avg_total_revenue": (
                str(revenue_sum / Decimal(len(profiles))) if profiles else None
            ),
        }, len(profiles)

    if pattern_type == "segment_pattern":
        segments: dict[str, int] = {}
        for profile in profiles:
            segment = profile.segment or "unknown"
            segments[segment] = segments.get(segment, 0) + 1
        return {"segments": segments}, len(profiles)

    if pattern_type == "churn_pattern":
        failures = [row for row in evaluations if row.success_flag is False]
        error_types: dict[str, int] = {}
        confidence_sum = ZERO
        for row in failures:
            error_type = row.error_type or "other"
            error_types[error_type] = error_types.get(error_type, 0) + 1
            if row.confidence is not None:
                confidence_sum += row.confidence
        top_error_type = (
            max(error_types, key=error_types.get) if error_types else None
        )
        return {
            "failure_evaluation_count": len(failures),
            "top_error_type": top_error_type,
            "error_type_distribution": error_types,
            "avg_confidence": (
                str(
                    (confidence_sum / Decimal(len(failures))).quantize(
                        Decimal("0.0001")
                    )
                )
                if failures
                else None
            ),
        }, len(evaluations)

    if pattern_type == "pain_pattern":
        categories: dict[str, int] = {}
        amount_sum = ZERO
        for refund in refunds:
            category = refund.category or "other"
            categories[category] = categories.get(category, 0) + 1
            amount_sum += refund.amount or ZERO
        top_category = max(categories, key=categories.get) if categories else None
        return {
            "refund_case_count": len(refunds),
            "refund_categories": categories,
            "top_category": top_category,
            "total_refund_amount": str(amount_sum),
        }, len(refunds)

    # bundle_pattern (deterministic: products mentioned across interactions).
    return {"products_mentioned": {}, "note": "requires order line-item data"}, len(profiles)


async def run_pattern_mining(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: PatternRunRequest,
    trace_id: str | None = None,
) -> CustomerPatternRun:
    """Run one deterministic pattern mining pass and audit it."""
    if data.pattern_type not in PATTERN_TYPES:
        raise CustomerLearningError(f"pattern_type must be one of {PATTERN_TYPES}")
    if data.customer_id is not None:
        profile = await _load_profile(
            session, workspace_id=workspace_id, customer_id=data.customer_id
        )
        if profile is None:
            raise CustomerLearningError("customer profile not found")

    profiles, evaluations, refunds = await _pattern_inputs(
        session, workspace_id=workspace_id, customer_id=data.customer_id
    )
    output_pattern, sample_size = _extract_pattern(
        data.pattern_type, profiles, evaluations, refunds
    )
    run = CustomerPatternRun(
        workspace_id=workspace_id,
        customer_id=data.customer_id,
        pattern_type=data.pattern_type,
        input_snapshot={
            "pattern_type": data.pattern_type,
            "profile_count": len(profiles),
            "evaluation_count": len(evaluations),
            "refund_count": len(refunds),
        },
        output_pattern=output_pattern,
        confidence=_pattern_confidence(sample_size),
        sample_size=sample_size,
        status="completed",
        trace_id=trace_id,
    )
    session.add(run)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="customer.pattern_run_completed",
        entity_type="customer_profile",
        entity_id=str(data.customer_id) if data.customer_id else str(workspace_id),
        payload={
            "run_id": str(run.id),
            "pattern_type": data.pattern_type,
            "confidence": str(run.confidence),
            "sample_size": sample_size,
        },
        trace_id=trace_id,
    )
    logger.info(
        "customer pattern run %s completed (%s, n=%s) trace=%s",
        run.id, data.pattern_type, sample_size, trace_id,
    )
    return run


async def list_pattern_runs(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    pattern_type: str | None = None,
    customer_id: UUID | None = None,
    limit: int = 50,
) -> list[CustomerPatternRun]:
    """List pattern runs, newest first."""
    stmt = select(CustomerPatternRun).where(
        CustomerPatternRun.workspace_id == workspace_id
    )
    if pattern_type:
        stmt = stmt.where(CustomerPatternRun.pattern_type == pattern_type)
    if customer_id is not None:
        stmt = stmt.where(CustomerPatternRun.customer_id == customer_id)
    stmt = stmt.order_by(CustomerPatternRun.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


# --------------------------------------------------------------------------- #
# 3. Customer calibration (human approval only)
# --------------------------------------------------------------------------- #


async def run_customer_calibration(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    trace_id: str | None = None,
) -> CustomerCalibrationRun:
    """Discover customer patterns and propose a calibration (never applied)."""
    evaluations = list(
        (
            await session.execute(
                select(CustomerAiEvaluation)
                .where(CustomerAiEvaluation.workspace_id == workspace_id)
                .order_by(CustomerAiEvaluation.created_at)
            )
        )
        .scalars()
        .all()
    )
    pattern_runs = list(
        (
            await session.execute(
                select(CustomerPatternRun)
                .where(CustomerPatternRun.workspace_id == workspace_id)
                .order_by(CustomerPatternRun.created_at)
            )
        )
        .scalars()
        .all()
    )

    sample_size = len(evaluations)
    if sample_size < MIN_CALIBRATION_SAMPLES:
        raise CustomerLearningError(
            f"not enough evaluations (need >= {MIN_CALIBRATION_SAMPLES}, got {sample_size})"
        )

    success_count = sum(1 for row in evaluations if row.success_flag is True)
    failure_count = sum(1 for row in evaluations if row.success_flag is False)
    error_types: dict[str, int] = {}
    for row in evaluations:
        if row.success_flag is False and row.error_type:
            error_types[row.error_type] = error_types.get(row.error_type, 0) + 1

    latest_pattern = pattern_runs[-1] if pattern_runs else None
    successful_patterns: dict[str, Any] = {
        "evaluation_success_count": success_count,
        "latest_pattern_type": latest_pattern.pattern_type if latest_pattern else None,
        "latest_pattern_output": (
            latest_pattern.output_pattern if latest_pattern else {}
        ),
    }
    failure_patterns: dict[str, Any] = {
        "evaluation_failure_count": failure_count,
        "error_type_distribution": error_types,
    }
    metrics: dict[str, Any] = {
        "sample_size": sample_size,
        "success_count": success_count,
        "failure_count": failure_count,
        "pattern_run_count": len(pattern_runs),
    }

    run = CustomerCalibrationRun(
        workspace_id=workspace_id,
        status="proposed",
        model_version=CALIBRATION_MODEL_VERSION,
        input_snapshot={
            "model_version": CALIBRATION_MODEL_VERSION,
            "sample_size": sample_size,
            "evaluation_count": sample_size,
            "pattern_run_count": len(pattern_runs),
        },
        successful_patterns=successful_patterns,
        failure_patterns=failure_patterns,
        metrics=metrics,
        sample_size=sample_size,
        rationale=(
            "Deterministic pattern extraction from customer evaluations and "
            "pattern runs. Proposal only - business rules are never modified "
            "automatically."
        ),
        trace_id=trace_id,
    )
    session.add(run)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="customer.calibration_run_proposed",
        entity_type="workspace",
        entity_id=str(workspace_id),
        payload={
            "run_id": str(run.id),
            "sample_size": sample_size,
            "success_count": success_count,
            "failure_count": failure_count,
        },
        trace_id=trace_id,
    )
    logger.info(
        "customer calibration run %s proposed (n=%s) trace=%s",
        run.id, sample_size, trace_id,
    )
    return run


async def _load_calibration_run(
    session: AsyncSession, *, workspace_id: UUID, run_id: UUID
) -> CustomerCalibrationRun | None:
    return (
        await session.execute(
            select(CustomerCalibrationRun).where(
                CustomerCalibrationRun.workspace_id == workspace_id,
                CustomerCalibrationRun.id == run_id,
            )
        )
    ).scalar_one_or_none()


async def _decide_calibration(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    run_id: UUID,
    actor: str,
    decision: str,
    note: str | None,
    trace_id: str | None,
) -> CustomerCalibrationRun:
    """Shared approve/reject logic (human-only; rules never auto-edited)."""
    run = await _load_calibration_run(
        session, workspace_id=workspace_id, run_id=run_id
    )
    if run is None:
        raise CustomerLearningError("calibration run not found")
    if run.status != "proposed":
        raise CustomerLearningError("calibration run is not proposed")
    now = datetime.now(UTC)
    run.status = decision
    run.approved_by = actor
    run.approved_at = now
    run.updated_at = now
    if note:
        run.rationale = (run.rationale or "") + f" | {decision} note: {note}"
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type=f"customer.calibration_run_{decision}",
        entity_type="workspace",
        entity_id=str(workspace_id),
        payload={"run_id": str(run.id), "actor": actor, "note": note},
        trace_id=trace_id,
    )
    return run


async def approve_customer_calibration(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    run_id: UUID,
    actor: str,
    note: str | None = None,
    trace_id: str | None = None,
) -> CustomerCalibrationRun:
    """Approve a customer calibration proposal (human-only)."""
    return await _decide_calibration(
        session,
        workspace_id=workspace_id,
        run_id=run_id,
        actor=actor,
        decision="approved",
        note=note,
        trace_id=trace_id,
    )


async def reject_customer_calibration(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    run_id: UUID,
    actor: str,
    note: str | None = None,
    trace_id: str | None = None,
) -> CustomerCalibrationRun:
    """Reject a customer calibration proposal (human-only)."""
    return await _decide_calibration(
        session,
        workspace_id=workspace_id,
        run_id=run_id,
        actor=actor,
        decision="rejected",
        note=note,
        trace_id=trace_id,
    )


async def list_customer_calibration_runs(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    status: str | None = None,
    limit: int = 50,
) -> list[CustomerCalibrationRun]:
    """List customer calibration runs, newest first."""
    stmt = select(CustomerCalibrationRun).where(
        CustomerCalibrationRun.workspace_id == workspace_id
    )
    if status:
        stmt = stmt.where(CustomerCalibrationRun.status == status)
    stmt = stmt.order_by(CustomerCalibrationRun.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


# --------------------------------------------------------------------------- #
# 4. Cross-domain customer context builder
# --------------------------------------------------------------------------- #


async def build_customer_context(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    customer_id: UUID,
    trace_id: str | None = None,
) -> dict:
    """Combine customer data across domains into one JSON-safe context.

    Assembled from: customer profile, orders (by customer_reference_id),
    interactions + their product reviews, refunds, campaigns/products of the
    interacted products, knowledge entries and evaluations - the input a
    future Customer Agent would use, without calling any model.
    """
    profile = await _load_profile(
        session, workspace_id=workspace_id, customer_id=customer_id
    )
    if profile is None:
        raise CustomerLearningError("customer profile not found")

    orders = list(
        (
            await session.execute(
                select(Order)
                .where(
                    Order.workspace_id == workspace_id,
                    Order.customer_reference_id == profile.customer_reference_id,
                )
                .order_by(Order.received_at.desc())
            )
        )
        .scalars()
        .all()
    )
    interactions = list(
        (
            await session.execute(
                select(CustomerInteraction)
                .where(
                    CustomerInteraction.workspace_id == workspace_id,
                    CustomerInteraction.customer_id == customer_id,
                )
                .order_by(CustomerInteraction.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    product_ids = [
        row.product_id
        for row in interactions
        if row.product_id is not None
    ]
    unique_product_ids = list(dict.fromkeys(product_ids))

    reviews: list[ProductReview] = []
    campaigns: list[Campaign] = []
    products: list[Product] = []
    if unique_product_ids:
        reviews = list(
            (
                await session.execute(
                    select(ProductReview).where(
                        ProductReview.workspace_id == workspace_id,
                        ProductReview.product_id.in_(unique_product_ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        campaigns = list(
            (
                await session.execute(
                    select(Campaign).where(
                        Campaign.workspace_id == workspace_id,
                        Campaign.product_id.in_(unique_product_ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        products = list(
            (
                await session.execute(
                    select(Product).where(
                        Product.workspace_id == workspace_id,
                        Product.id.in_(unique_product_ids),
                    )
                )
            )
            .scalars()
            .all()
        )

    refunds = list(
        (
            await session.execute(
                select(RefundCase)
                .where(
                    RefundCase.workspace_id == workspace_id,
                    RefundCase.customer_id == customer_id,
                )
                .order_by(RefundCase.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    knowledge = list(
        (
            await session.execute(
                select(CustomerKnowledgeEntry)
                .where(
                    CustomerKnowledgeEntry.workspace_id == workspace_id,
                    CustomerKnowledgeEntry.customer_id == customer_id,
                )
                .order_by(CustomerKnowledgeEntry.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    evaluations = list(
        (
            await session.execute(
                select(CustomerAiEvaluation)
                .where(
                    CustomerAiEvaluation.workspace_id == workspace_id,
                    CustomerAiEvaluation.customer_id == customer_id,
                )
                .order_by(CustomerAiEvaluation.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    def _row(row: Any) -> dict:
        return {
            prop.key: _jsonable(getattr(row, prop.key))
            for prop in class_mapper(type(row)).column_attrs
        }

    return {
        "customer": _row(profile),
        "orders": [_row(row) for row in orders],
        "interactions": [_row(row) for row in interactions],
        "reviews": [_row(row) for row in reviews],
        "refunds": [_row(row) for row in refunds],
        "marketing_data": {"campaigns": [_row(row) for row in campaigns]},
        "product_data": {"products": [_row(row) for row in products]},
        "knowledge": [_row(row) for row in knowledge],
        "evaluations": [_row(row) for row in evaluations],
        "trace_id": trace_id,
    }
