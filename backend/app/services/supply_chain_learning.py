"""Supply chain learning loop service (M4.2).

Upgrades supply chain intelligence to a learning layer: predicted supplier
performance and logistics delivery outcomes are evaluated against actuals
(deterministic classification), pattern mining runs surface supplier and
logistics patterns, and calibration proposals require human approval.

**Boundaries**: no Supply Chain Agent, no automatic purchasing, and no
business rule is ever modified automatically.
"""

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.supplier import Supplier
from app.models.supply_chain import ShipmentRecord, SupplierProfile
from app.models.supply_chain_learning import (
    LogisticsAiEvaluation,
    LogisticsPatternRun,
    SupplierAiEvaluation,
    SupplierPatternRun,
    SupplyChainCalibrationRun,
)
from app.schemas.supply_chain_learning import (
    LogisticsEvaluationCreate,
    LogisticsPatternRunRequest,
    SupplierEvaluationCreate,
    SupplierPatternRunRequest,
)
from app.services import ai_evaluation, event_service

logger = logging.getLogger(__name__)

ZERO = Decimal("0")
CALIBRATION_MODEL_VERSION = "supply-chain-calibration-v1"
MIN_CALIBRATION_SAMPLES = 1
SUPPLIER_PATTERN_TYPES: tuple[str, ...] = (
    "quality_pattern",
    "delivery_pattern",
    "price_pattern",
    "risk_pattern",
    "capacity_pattern",
)
LOGISTICS_PATTERN_TYPES: tuple[str, ...] = (
    "delay_pattern",
    "carrier_pattern",
    "route_pattern",
    "country_pattern",
)


class SupplyChainLearningError(Exception):
    """Raised when a supply chain learning operation cannot complete."""


def _decimal(value: Any) -> Decimal | None:
    return ai_evaluation._decimal(value)


async def _load_supplier(
    session: AsyncSession, *, workspace_id: UUID, supplier_id: UUID
) -> Supplier | None:
    return (
        await session.execute(
            select(Supplier).where(
                Supplier.workspace_id == workspace_id,
                Supplier.id == supplier_id,
            )
        )
    ).scalar_one_or_none()


async def _load_shipment(
    session: AsyncSession, *, workspace_id: UUID, shipment_id: UUID
) -> ShipmentRecord | None:
    return (
        await session.execute(
            select(ShipmentRecord).where(
                ShipmentRecord.workspace_id == workspace_id,
                ShipmentRecord.id == shipment_id,
            )
        )
    ).scalar_one_or_none()


def _supply_metric_snapshot(prediction: dict, actual: dict, decision_match: bool | None) -> dict:
    """JSON-safe metric summary for supply chain evaluations."""
    snapshot: dict[str, Any] = {}
    confidence = ai_evaluation._prediction_confidence(prediction)
    if confidence is not None:
        snapshot["confidence"] = str(confidence)
    for key in ("decision", "delivery_time_days", "defect_rate", "on_time_rate", "quality_score"):
        if prediction.get(key) is not None:
            snapshot[f"predicted_{key}"] = prediction[key]
        if actual.get(key) is not None:
            snapshot[f"actual_{key}"] = actual[key]
    for key in ("delayed", "defective_units", "rework_cost", "delay_days"):
        if actual.get(key) is not None:
            snapshot[key] = actual[key]
    if decision_match is not None:
        snapshot["decision_match"] = decision_match
    return snapshot


# --------------------------------------------------------------------------- #
# 1. Supplier evaluation
# --------------------------------------------------------------------------- #


async def record_supplier_evaluation(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: SupplierEvaluationCreate,
    trace_id: str | None = None,
) -> SupplierAiEvaluation:
    """Record one predicted-vs-actual supplier evaluation (append-only)."""
    supplier = await _load_supplier(
        session, workspace_id=workspace_id, supplier_id=data.supplier_id
    )
    if supplier is None:
        raise SupplyChainLearningError("supplier not found")

    accuracy = ai_evaluation.compute_accuracy(data.prediction, data.actual_result)
    decision_match = accuracy.get("decision_match")
    success_flag = ai_evaluation._determine_success(
        data.prediction, data.actual_result, decision_match
    )
    prediction_result = (
        "success" if success_flag is True else "failure" if success_flag is False else "unknown"
    )
    error_type = (
        ai_evaluation._error_type(
            data.prediction, data.actual_result, decision_match
        )
        if success_flag is False
        else None
    )
    confidence = ai_evaluation._prediction_confidence(data.prediction)

    evaluation = SupplierAiEvaluation(
        workspace_id=workspace_id,
        supplier_id=data.supplier_id,
        prediction=data.prediction,
        actual_result=data.actual_result,
        accuracy=accuracy,
        prediction_result=prediction_result,
        error_type=error_type,
        confidence=confidence,
        confidence_bucket=ai_evaluation._confidence_bucket(confidence),
        success_flag=success_flag,
        metric_snapshot=_supply_metric_snapshot(
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
        event_type="supply.supplier_evaluation_recorded",
        entity_type="supplier",
        entity_id=str(data.supplier_id),
        payload={
            "evaluation_id": str(evaluation.id),
            "prediction_result": prediction_result,
            "error_type": error_type,
            "human_rating": data.human_rating,
        },
        trace_id=trace_id,
    )
    logger.info(
        "supplier evaluation %s recorded (%s) trace=%s",
        evaluation.id,
        prediction_result,
        trace_id,
    )
    return evaluation


async def list_supplier_evaluations(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    supplier_id: UUID | None = None,
    limit: int = 50,
) -> list[SupplierAiEvaluation]:
    """List supplier evaluations, newest first."""
    stmt = select(SupplierAiEvaluation).where(SupplierAiEvaluation.workspace_id == workspace_id)
    if supplier_id is not None:
        stmt = stmt.where(SupplierAiEvaluation.supplier_id == supplier_id)
    stmt = stmt.order_by(SupplierAiEvaluation.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


# --------------------------------------------------------------------------- #
# 2. Logistics evaluation
# --------------------------------------------------------------------------- #


async def record_logistics_evaluation(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: LogisticsEvaluationCreate,
    trace_id: str | None = None,
) -> LogisticsAiEvaluation:
    """Record one predicted-vs-actual delivery evaluation (append-only)."""
    shipment = await _load_shipment(
        session, workspace_id=workspace_id, shipment_id=data.shipment_id
    )
    if shipment is None:
        raise SupplyChainLearningError("shipment not found")

    carrier = data.carrier or shipment.carrier
    if data.route:
        route = data.route
    elif shipment.origin or shipment.destination:
        route = " -> ".join(part for part in (shipment.origin, shipment.destination) if part)
    else:
        route = None

    accuracy = ai_evaluation.compute_accuracy(data.prediction, data.actual_result)
    decision_match = accuracy.get("decision_match")
    success_flag = ai_evaluation._determine_success(
        data.prediction, data.actual_result, decision_match
    )
    prediction_result = (
        "success" if success_flag is True else "failure" if success_flag is False else "unknown"
    )
    error_type = (
        ai_evaluation._error_type(
            data.prediction, data.actual_result, decision_match
        )
        if success_flag is False
        else None
    )
    confidence = ai_evaluation._prediction_confidence(data.prediction)

    evaluation = LogisticsAiEvaluation(
        workspace_id=workspace_id,
        shipment_id=data.shipment_id,
        carrier=carrier,
        route=route,
        prediction=data.prediction,
        actual_result=data.actual_result,
        delay_reason=data.delay_reason,
        accuracy=accuracy,
        prediction_result=prediction_result,
        error_type=error_type,
        confidence=confidence,
        confidence_bucket=ai_evaluation._confidence_bucket(confidence),
        success_flag=success_flag,
        metric_snapshot=_supply_metric_snapshot(
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
        event_type="supply.logistics_evaluation_recorded",
        entity_type="shipment",
        entity_id=str(data.shipment_id),
        payload={
            "evaluation_id": str(evaluation.id),
            "carrier": carrier,
            "prediction_result": prediction_result,
            "delay_reason": data.delay_reason,
        },
        trace_id=trace_id,
    )
    logger.info(
        "logistics evaluation %s recorded (%s, %s) trace=%s",
        evaluation.id,
        prediction_result,
        carrier,
        trace_id,
    )
    return evaluation


async def list_logistics_evaluations(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    shipment_id: UUID | None = None,
    carrier: str | None = None,
    limit: int = 50,
) -> list[LogisticsAiEvaluation]:
    """List logistics evaluations, newest first."""
    stmt = select(LogisticsAiEvaluation).where(LogisticsAiEvaluation.workspace_id == workspace_id)
    if shipment_id is not None:
        stmt = stmt.where(LogisticsAiEvaluation.shipment_id == shipment_id)
    if carrier:
        stmt = stmt.where(LogisticsAiEvaluation.carrier == carrier)
    stmt = stmt.order_by(LogisticsAiEvaluation.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


# --------------------------------------------------------------------------- #
# 3. Supplier pattern mining
# --------------------------------------------------------------------------- #


def _pattern_confidence(sample_size: int) -> Decimal:
    """Deterministic heuristic confidence: 0.1 per sample, capped at 0.9."""
    if sample_size <= 0:
        return ZERO
    raw = Decimal(sample_size) * Decimal("0.1")
    return min(raw, Decimal("0.9")).quantize(Decimal("0.0001"))


def _extract_supplier_pattern(
    pattern_type: str,
    profiles: list[SupplierProfile],
    evaluations: list[SupplierAiEvaluation],
) -> tuple[dict[str, Any], int]:
    """Deterministically extract one supplier pattern type from inputs."""
    failures = [row for row in evaluations if row.success_flag is False]
    error_types: dict[str, int] = {}
    for row in failures:
        error_type = row.error_type or "other"
        error_types[error_type] = error_types.get(error_type, 0) + 1

    if pattern_type == "quality_pattern":
        quality_scores = [
            profile.quality_score for profile in profiles if profile.quality_score is not None
        ]
        defect_rates = [
            profile.defect_rate for profile in profiles if profile.defect_rate is not None
        ]
        return {
            "profile_count": len(profiles),
            "avg_quality_score": (
                str(sum(quality_scores) / Decimal(len(quality_scores))) if quality_scores else None
            ),
            "avg_defect_rate": (
                str(sum(defect_rates) / Decimal(len(defect_rates))) if defect_rates else None
            ),
            "quality_failure_count": len(failures),
            "error_type_distribution": error_types,
        }, len(profiles) + len(evaluations)

    if pattern_type == "delivery_pattern":
        on_time_rates = [
            profile.on_time_rate for profile in profiles if profile.on_time_rate is not None
        ]
        lead_times = [
            profile.lead_time_days for profile in profiles if profile.lead_time_days is not None
        ]
        return {
            "profile_count": len(profiles),
            "avg_on_time_rate": (
                str(sum(on_time_rates) / Decimal(len(on_time_rates))) if on_time_rates else None
            ),
            "avg_lead_time_days": (
                str(sum(lead_times) / Decimal(len(lead_times))) if lead_times else None
            ),
            "delivery_failure_count": len(failures),
            "error_type_distribution": error_types,
        }, len(profiles) + len(evaluations)

    if pattern_type == "risk_pattern":
        risk_levels: dict[str, int] = {}
        for profile in profiles:
            risk = profile.risk_level or "unknown"
            risk_levels[risk] = risk_levels.get(risk, 0) + 1
        return {
            "profile_count": len(profiles),
            "risk_level_distribution": risk_levels,
            "failure_evaluation_count": len(failures),
            "failure_rate": (
                str(
                    (Decimal(len(failures)) / Decimal(len(evaluations))).quantize(Decimal("0.0001"))
                )
                if evaluations
                else None
            ),
        }, len(evaluations)

    if pattern_type == "capacity_pattern":
        moqs = [
            profile.minimum_order_qty
            for profile in profiles
            if profile.minimum_order_qty is not None
        ]
        lead_times = [
            profile.lead_time_days for profile in profiles if profile.lead_time_days is not None
        ]
        return {
            "profile_count": len(profiles),
            "avg_minimum_order_qty": (str(sum(moqs) / Decimal(len(moqs))) if moqs else None),
            "avg_lead_time_days": (
                str(sum(lead_times) / Decimal(len(lead_times))) if lead_times else None
            ),
        }, len(profiles)

    # price_pattern (deterministic: price-related evaluation signals).
    price_evaluations = [
        row
        for row in evaluations
        if any(
            key in row.prediction or key in row.actual_result
            for key in ("price", "unit_cost", "margin")
        )
    ]
    return {
        "price_evaluation_count": len(price_evaluations),
        "total_evaluation_count": len(evaluations),
        "failure_count": len(failures),
    }, len(price_evaluations)


async def run_supplier_pattern_mining(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: SupplierPatternRunRequest,
    trace_id: str | None = None,
) -> SupplierPatternRun:
    """Run one deterministic supplier pattern mining pass and audit it."""
    if data.pattern_type not in SUPPLIER_PATTERN_TYPES:
        raise SupplyChainLearningError(f"pattern_type must be one of {SUPPLIER_PATTERN_TYPES}")
    if data.supplier_id is not None:
        supplier = await _load_supplier(
            session, workspace_id=workspace_id, supplier_id=data.supplier_id
        )
        if supplier is None:
            raise SupplyChainLearningError("supplier not found")

    profiles_stmt = select(SupplierProfile).where(SupplierProfile.workspace_id == workspace_id)
    evaluations_stmt = select(SupplierAiEvaluation).where(
        SupplierAiEvaluation.workspace_id == workspace_id
    )
    if data.supplier_id is not None:
        profiles_stmt = profiles_stmt.where(SupplierProfile.supplier_id == data.supplier_id)
        evaluations_stmt = evaluations_stmt.where(
            SupplierAiEvaluation.supplier_id == data.supplier_id
        )
    profiles = list((await session.execute(profiles_stmt)).scalars().all())
    evaluations = list((await session.execute(evaluations_stmt)).scalars().all())

    output_pattern, sample_size = _extract_supplier_pattern(
        data.pattern_type, profiles, evaluations
    )
    run = SupplierPatternRun(
        workspace_id=workspace_id,
        supplier_id=data.supplier_id,
        pattern_type=data.pattern_type,
        input_snapshot={
            "pattern_type": data.pattern_type,
            "profile_count": len(profiles),
            "evaluation_count": len(evaluations),
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
        event_type="supply.supplier_pattern_run_completed",
        entity_type="supplier",
        entity_id=str(data.supplier_id) if data.supplier_id else str(workspace_id),
        payload={
            "run_id": str(run.id),
            "pattern_type": data.pattern_type,
            "confidence": str(run.confidence),
            "sample_size": sample_size,
        },
        trace_id=trace_id,
    )
    logger.info(
        "supplier pattern run %s completed (%s, n=%s) trace=%s",
        run.id,
        data.pattern_type,
        sample_size,
        trace_id,
    )
    return run


async def list_supplier_pattern_runs(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    pattern_type: str | None = None,
    supplier_id: UUID | None = None,
    limit: int = 50,
) -> list[SupplierPatternRun]:
    """List supplier pattern runs, newest first."""
    stmt = select(SupplierPatternRun).where(SupplierPatternRun.workspace_id == workspace_id)
    if pattern_type:
        stmt = stmt.where(SupplierPatternRun.pattern_type == pattern_type)
    if supplier_id is not None:
        stmt = stmt.where(SupplierPatternRun.supplier_id == supplier_id)
    stmt = stmt.order_by(SupplierPatternRun.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


# --------------------------------------------------------------------------- #
# 4. Logistics pattern mining
# --------------------------------------------------------------------------- #


def _country_from_destination(destination: str | None) -> str | None:
    """Deterministic country extraction from a destination string.

    Uses the last comma-separated token, uppercased (e.g. "Los Angeles, US"
    -> "US", "Hamburg DE" -> "DE"). Returns None when undetectable.
    """
    if not destination:
        return None
    parts = [part.strip() for part in destination.split(",")]
    candidate = parts[-1] if parts else ""
    tokens = candidate.split()
    country = tokens[-1].upper() if tokens else candidate.upper()
    return country or None


def _extract_logistics_pattern(
    pattern_type: str,
    shipments: list[ShipmentRecord],
    evaluations: list[LogisticsAiEvaluation],
) -> tuple[dict[str, Any], int]:
    """Deterministically extract one logistics pattern type from inputs."""
    failures = [row for row in evaluations if row.success_flag is False]

    if pattern_type == "delay_pattern":
        delay_reasons: dict[str, int] = {}
        for row in failures:
            reason = row.delay_reason or "unknown"
            delay_reasons[reason] = delay_reasons.get(reason, 0) + 1
        return {
            "failure_evaluation_count": len(failures),
            "delay_reason_distribution": delay_reasons,
            "top_delay_reason": (
                max(delay_reasons, key=delay_reasons.get) if delay_reasons else None
            ),
            "total_evaluation_count": len(evaluations),
        }, len(evaluations)

    if pattern_type == "carrier_pattern":
        by_carrier: dict[str, dict[str, Any]] = {}
        for row in evaluations:
            carrier = row.carrier or "unknown"
            bucket = by_carrier.setdefault(carrier, {"count": 0, "success": 0, "failure": 0})
            bucket["count"] += 1
            if row.success_flag is True:
                bucket["success"] += 1
            elif row.success_flag is False:
                bucket["failure"] += 1
        return {"carriers": by_carrier}, len(evaluations)

    if pattern_type == "country_pattern":
        by_country: dict[str, dict[str, Any]] = {}
        for row in evaluations:
            country = None
            if row.route:
                destination = row.route.split("->")[-1].strip()
                country = _country_from_destination(destination)
            country = country or "unknown"
            bucket = by_country.setdefault(country, {"count": 0, "failure": 0})
            bucket["count"] += 1
            if row.success_flag is False:
                bucket["failure"] += 1
        return {"countries": by_country}, len(evaluations)

    # route_pattern
    by_route: dict[str, dict[str, Any]] = {}
    for row in evaluations:
        route = row.route or "unknown"
        bucket = by_route.setdefault(route, {"count": 0, "failure": 0})
        bucket["count"] += 1
        if row.success_flag is False:
            bucket["failure"] += 1
    return {"routes": by_route}, len(evaluations)


async def run_logistics_pattern_mining(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: LogisticsPatternRunRequest,
    trace_id: str | None = None,
) -> LogisticsPatternRun:
    """Run one deterministic logistics pattern mining pass and audit it."""
    if data.pattern_type not in LOGISTICS_PATTERN_TYPES:
        raise SupplyChainLearningError(f"pattern_type must be one of {LOGISTICS_PATTERN_TYPES}")
    if data.shipment_id is not None:
        shipment = await _load_shipment(
            session, workspace_id=workspace_id, shipment_id=data.shipment_id
        )
        if shipment is None:
            raise SupplyChainLearningError("shipment not found")

    shipments_stmt = select(ShipmentRecord).where(ShipmentRecord.workspace_id == workspace_id)
    evaluations_stmt = select(LogisticsAiEvaluation).where(
        LogisticsAiEvaluation.workspace_id == workspace_id
    )
    if data.shipment_id is not None:
        shipments_stmt = shipments_stmt.where(ShipmentRecord.id == data.shipment_id)
        evaluations_stmt = evaluations_stmt.where(
            LogisticsAiEvaluation.shipment_id == data.shipment_id
        )
    if data.carrier:
        evaluations_stmt = evaluations_stmt.where(LogisticsAiEvaluation.carrier == data.carrier)
    shipments = list((await session.execute(shipments_stmt)).scalars().all())
    evaluations = list((await session.execute(evaluations_stmt)).scalars().all())

    output_pattern, sample_size = _extract_logistics_pattern(
        data.pattern_type, shipments, evaluations
    )
    run = LogisticsPatternRun(
        workspace_id=workspace_id,
        shipment_id=data.shipment_id,
        carrier=data.carrier,
        pattern_type=data.pattern_type,
        input_snapshot={
            "pattern_type": data.pattern_type,
            "shipment_count": len(shipments),
            "evaluation_count": len(evaluations),
            "carrier": data.carrier,
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
        event_type="supply.logistics_pattern_run_completed",
        entity_type="shipment",
        entity_id=str(data.shipment_id) if data.shipment_id else str(workspace_id),
        payload={
            "run_id": str(run.id),
            "pattern_type": data.pattern_type,
            "confidence": str(run.confidence),
            "sample_size": sample_size,
        },
        trace_id=trace_id,
    )
    logger.info(
        "logistics pattern run %s completed (%s, n=%s) trace=%s",
        run.id,
        data.pattern_type,
        sample_size,
        trace_id,
    )
    return run


async def list_logistics_pattern_runs(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    pattern_type: str | None = None,
    shipment_id: UUID | None = None,
    limit: int = 50,
) -> list[LogisticsPatternRun]:
    """List logistics pattern runs, newest first."""
    stmt = select(LogisticsPatternRun).where(LogisticsPatternRun.workspace_id == workspace_id)
    if pattern_type:
        stmt = stmt.where(LogisticsPatternRun.pattern_type == pattern_type)
    if shipment_id is not None:
        stmt = stmt.where(LogisticsPatternRun.shipment_id == shipment_id)
    stmt = stmt.order_by(LogisticsPatternRun.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


# --------------------------------------------------------------------------- #
# 5. Supply chain calibration (human approval only)
# --------------------------------------------------------------------------- #


async def run_supply_chain_calibration(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    trace_id: str | None = None,
) -> SupplyChainCalibrationRun:
    """Discover supply chain patterns and propose a calibration (never applied)."""
    supplier_evaluations = list(
        (
            await session.execute(
                select(SupplierAiEvaluation)
                .where(SupplierAiEvaluation.workspace_id == workspace_id)
                .order_by(SupplierAiEvaluation.created_at)
            )
        )
        .scalars()
        .all()
    )
    logistics_evaluations = list(
        (
            await session.execute(
                select(LogisticsAiEvaluation)
                .where(LogisticsAiEvaluation.workspace_id == workspace_id)
                .order_by(LogisticsAiEvaluation.created_at)
            )
        )
        .scalars()
        .all()
    )
    supplier_pattern_runs = list(
        (
            await session.execute(
                select(SupplierPatternRun)
                .where(SupplierPatternRun.workspace_id == workspace_id)
                .order_by(SupplierPatternRun.created_at)
            )
        )
        .scalars()
        .all()
    )
    logistics_pattern_runs = list(
        (
            await session.execute(
                select(LogisticsPatternRun)
                .where(LogisticsPatternRun.workspace_id == workspace_id)
                .order_by(LogisticsPatternRun.created_at)
            )
        )
        .scalars()
        .all()
    )

    sample_size = len(supplier_evaluations) + len(logistics_evaluations)
    if sample_size < MIN_CALIBRATION_SAMPLES:
        raise SupplyChainLearningError(
            f"not enough evaluations (need >= {MIN_CALIBRATION_SAMPLES}, got {sample_size})"
        )

    supplier_success = sum(1 for row in supplier_evaluations if row.success_flag is True)
    supplier_failure = sum(1 for row in supplier_evaluations if row.success_flag is False)
    logistics_success = sum(1 for row in logistics_evaluations if row.success_flag is True)
    logistics_failure = sum(1 for row in logistics_evaluations if row.success_flag is False)

    supplier_error_types: dict[str, int] = {}
    logistics_error_types: dict[str, int] = {}
    for row in supplier_evaluations:
        if row.success_flag is False and row.error_type:
            supplier_error_types[row.error_type] = supplier_error_types.get(row.error_type, 0) + 1
    for row in logistics_evaluations:
        if row.success_flag is False and row.error_type:
            logistics_error_types[row.error_type] = logistics_error_types.get(row.error_type, 0) + 1

    latest_supplier_pattern = supplier_pattern_runs[-1] if supplier_pattern_runs else None
    latest_logistics_pattern = logistics_pattern_runs[-1] if logistics_pattern_runs else None
    successful_patterns: dict[str, Any] = {
        "supplier_evaluation_success_count": supplier_success,
        "logistics_evaluation_success_count": logistics_success,
        "latest_supplier_pattern": (
            {
                "pattern_type": latest_supplier_pattern.pattern_type,
                "output_pattern": latest_supplier_pattern.output_pattern,
            }
            if latest_supplier_pattern
            else None
        ),
        "latest_logistics_pattern": (
            {
                "pattern_type": latest_logistics_pattern.pattern_type,
                "output_pattern": latest_logistics_pattern.output_pattern,
            }
            if latest_logistics_pattern
            else None
        ),
    }
    failure_patterns: dict[str, Any] = {
        "supplier_evaluation_failure_count": supplier_failure,
        "logistics_evaluation_failure_count": logistics_failure,
        "supplier_error_type_distribution": supplier_error_types,
        "logistics_error_type_distribution": logistics_error_types,
    }
    metrics: dict[str, Any] = {
        "sample_size": sample_size,
        "supplier_evaluation_count": len(supplier_evaluations),
        "logistics_evaluation_count": len(logistics_evaluations),
        "supplier_success_count": supplier_success,
        "supplier_failure_count": supplier_failure,
        "logistics_success_count": logistics_success,
        "logistics_failure_count": logistics_failure,
        "supplier_pattern_run_count": len(supplier_pattern_runs),
        "logistics_pattern_run_count": len(logistics_pattern_runs),
    }

    run = SupplyChainCalibrationRun(
        workspace_id=workspace_id,
        status="proposed",
        model_version=CALIBRATION_MODEL_VERSION,
        input_snapshot={
            "model_version": CALIBRATION_MODEL_VERSION,
            "sample_size": sample_size,
            "supplier_evaluation_count": len(supplier_evaluations),
            "logistics_evaluation_count": len(logistics_evaluations),
        },
        successful_patterns=successful_patterns,
        failure_patterns=failure_patterns,
        metrics=metrics,
        sample_size=sample_size,
        rationale=(
            "Deterministic pattern extraction from supplier/logistics "
            "evaluations and pattern runs. Proposal only - business rules "
            "are never modified automatically."
        ),
        trace_id=trace_id,
    )
    session.add(run)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="supply.calibration_run_proposed",
        entity_type="workspace",
        entity_id=str(workspace_id),
        payload={
            "run_id": str(run.id),
            "sample_size": sample_size,
            "supplier_failure_count": supplier_failure,
            "logistics_failure_count": logistics_failure,
        },
        trace_id=trace_id,
    )
    logger.info(
        "supply chain calibration run %s proposed (n=%s) trace=%s",
        run.id,
        sample_size,
        trace_id,
    )
    return run


async def _load_calibration_run(
    session: AsyncSession, *, workspace_id: UUID, run_id: UUID
) -> SupplyChainCalibrationRun | None:
    return (
        await session.execute(
            select(SupplyChainCalibrationRun).where(
                SupplyChainCalibrationRun.workspace_id == workspace_id,
                SupplyChainCalibrationRun.id == run_id,
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
) -> SupplyChainCalibrationRun:
    """Shared approve/reject logic (human-only; rules never auto-edited)."""
    run = await _load_calibration_run(session, workspace_id=workspace_id, run_id=run_id)
    if run is None:
        raise SupplyChainLearningError("calibration run not found")
    if run.status != "proposed":
        raise SupplyChainLearningError("calibration run is not proposed")
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
        event_type=f"supply.calibration_run_{decision}",
        entity_type="workspace",
        entity_id=str(workspace_id),
        payload={"run_id": str(run.id), "actor": actor, "note": note},
        trace_id=trace_id,
    )
    return run


async def approve_supply_chain_calibration(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    run_id: UUID,
    actor: str,
    note: str | None = None,
    trace_id: str | None = None,
) -> SupplyChainCalibrationRun:
    """Approve a supply chain calibration proposal (human-only)."""
    return await _decide_calibration(
        session,
        workspace_id=workspace_id,
        run_id=run_id,
        actor=actor,
        decision="approved",
        note=note,
        trace_id=trace_id,
    )


async def reject_supply_chain_calibration(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    run_id: UUID,
    actor: str,
    note: str | None = None,
    trace_id: str | None = None,
) -> SupplyChainCalibrationRun:
    """Reject a supply chain calibration proposal (human-only)."""
    return await _decide_calibration(
        session,
        workspace_id=workspace_id,
        run_id=run_id,
        actor=actor,
        decision="rejected",
        note=note,
        trace_id=trace_id,
    )


async def list_supply_chain_calibration_runs(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    status: str | None = None,
    limit: int = 50,
) -> list[SupplyChainCalibrationRun]:
    """List supply chain calibration runs, newest first."""
    stmt = select(SupplyChainCalibrationRun).where(
        SupplyChainCalibrationRun.workspace_id == workspace_id
    )
    if status:
        stmt = stmt.where(SupplyChainCalibrationRun.status == status)
    stmt = stmt.order_by(SupplyChainCalibrationRun.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)
