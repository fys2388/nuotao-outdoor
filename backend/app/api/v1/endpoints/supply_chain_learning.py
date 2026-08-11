"""Supply chain learning loop endpoints (M4.2): evaluations, pattern mining, calibration.

Reads + proposal writes only. No Supply Chain Agent, no automatic purchasing,
no automatic business rule changes.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.tracing import get_trace_id
from app.core.workspace import get_workspace_id
from app.schemas.product_analyst import CalibrationApproveRequest
from app.schemas.supply_chain_learning import (
    LogisticsEvaluationCreate,
    LogisticsEvaluationOut,
    LogisticsPatternRunOut,
    LogisticsPatternRunRequest,
    SupplierEvaluationCreate,
    SupplierEvaluationOut,
    SupplierPatternRunOut,
    SupplierPatternRunRequest,
    SupplyChainCalibrationOut,
)
from app.services import supply_chain_learning

router = APIRouter(tags=["supply-chain-learning"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]


def _http_error(exc: supply_chain_learning.SupplyChainLearningError) -> HTTPException:
    """Map learning-loop errors: missing resources -> 404, others -> 400."""
    if "not found" in str(exc):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# --------------------------------------------------------------------------- #
# Supplier evaluations
# --------------------------------------------------------------------------- #


@router.post(
    "/supplier-evaluations",
    response_model=SupplierEvaluationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record a supplier performance prediction evaluation",
)
async def record_supplier_evaluation(
    body: SupplierEvaluationCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> SupplierEvaluationOut:
    """Record and auto-classify (success/failure + error type)."""
    try:
        evaluation = await supply_chain_learning.record_supplier_evaluation(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except supply_chain_learning.SupplyChainLearningError as exc:
        raise _http_error(exc) from exc
    return SupplierEvaluationOut.model_validate(evaluation)


@router.get(
    "/supplier-evaluations",
    response_model=list[SupplierEvaluationOut],
    summary="List supplier evaluations",
)
async def list_supplier_evaluations(
    db: DbSession,
    workspace_id: WorkspaceId,
    supplier_id: Annotated[UUID | None, Query()] = None,
    limit: int = 50,
) -> list[SupplierEvaluationOut]:
    """Return evaluations, newest first, optionally filtered by supplier."""
    rows = await supply_chain_learning.list_supplier_evaluations(
        db, workspace_id=workspace_id, supplier_id=supplier_id, limit=limit
    )
    return [SupplierEvaluationOut.model_validate(row) for row in rows]


# --------------------------------------------------------------------------- #
# Logistics evaluations
# --------------------------------------------------------------------------- #


@router.post(
    "/logistics-evaluations",
    response_model=LogisticsEvaluationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record a delivery outcome prediction evaluation",
)
async def record_logistics_evaluation(
    body: LogisticsEvaluationCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> LogisticsEvaluationOut:
    """Record and auto-classify (success/failure + error type)."""
    try:
        evaluation = await supply_chain_learning.record_logistics_evaluation(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except supply_chain_learning.SupplyChainLearningError as exc:
        raise _http_error(exc) from exc
    return LogisticsEvaluationOut.model_validate(evaluation)


@router.get(
    "/logistics-evaluations",
    response_model=list[LogisticsEvaluationOut],
    summary="List logistics evaluations",
)
async def list_logistics_evaluations(
    db: DbSession,
    workspace_id: WorkspaceId,
    shipment_id: Annotated[UUID | None, Query()] = None,
    carrier: str | None = Query(default=None, max_length=64),
    limit: int = 50,
) -> list[LogisticsEvaluationOut]:
    """Return evaluations, newest first, optionally filtered."""
    rows = await supply_chain_learning.list_logistics_evaluations(
        db,
        workspace_id=workspace_id,
        shipment_id=shipment_id,
        carrier=carrier,
        limit=limit,
    )
    return [LogisticsEvaluationOut.model_validate(row) for row in rows]


# --------------------------------------------------------------------------- #
# Supplier pattern mining
# --------------------------------------------------------------------------- #


@router.post(
    "/supplier-pattern-runs",
    response_model=SupplierPatternRunOut,
    status_code=status.HTTP_201_CREATED,
    summary="Run deterministic supplier pattern mining",
)
async def run_supplier_pattern_mining(
    body: SupplierPatternRunRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> SupplierPatternRunOut:
    """Extract one pattern type (quality/delivery/price/risk/capacity)."""
    try:
        run = await supply_chain_learning.run_supplier_pattern_mining(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except supply_chain_learning.SupplyChainLearningError as exc:
        raise _http_error(exc) from exc
    return SupplierPatternRunOut.model_validate(run)


@router.get(
    "/supplier-pattern-runs",
    response_model=list[SupplierPatternRunOut],
    summary="List supplier pattern runs",
)
async def list_supplier_pattern_runs(
    db: DbSession,
    workspace_id: WorkspaceId,
    pattern_type: str | None = Query(default=None, max_length=32),
    supplier_id: Annotated[UUID | None, Query()] = None,
    limit: int = 50,
) -> list[SupplierPatternRunOut]:
    """Return pattern runs, newest first."""
    rows = await supply_chain_learning.list_supplier_pattern_runs(
        db,
        workspace_id=workspace_id,
        pattern_type=pattern_type,
        supplier_id=supplier_id,
        limit=limit,
    )
    return [SupplierPatternRunOut.model_validate(row) for row in rows]


# --------------------------------------------------------------------------- #
# Logistics pattern mining
# --------------------------------------------------------------------------- #


@router.post(
    "/logistics-pattern-runs",
    response_model=LogisticsPatternRunOut,
    status_code=status.HTTP_201_CREATED,
    summary="Run deterministic logistics pattern mining",
)
async def run_logistics_pattern_mining(
    body: LogisticsPatternRunRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> LogisticsPatternRunOut:
    """Extract one pattern type (delay/carrier/route/country)."""
    try:
        run = await supply_chain_learning.run_logistics_pattern_mining(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except supply_chain_learning.SupplyChainLearningError as exc:
        raise _http_error(exc) from exc
    return LogisticsPatternRunOut.model_validate(run)


@router.get(
    "/logistics-pattern-runs",
    response_model=list[LogisticsPatternRunOut],
    summary="List logistics pattern runs",
)
async def list_logistics_pattern_runs(
    db: DbSession,
    workspace_id: WorkspaceId,
    pattern_type: str | None = Query(default=None, max_length=32),
    shipment_id: Annotated[UUID | None, Query()] = None,
    limit: int = 50,
) -> list[LogisticsPatternRunOut]:
    """Return pattern runs, newest first."""
    rows = await supply_chain_learning.list_logistics_pattern_runs(
        db,
        workspace_id=workspace_id,
        pattern_type=pattern_type,
        shipment_id=shipment_id,
        limit=limit,
    )
    return [LogisticsPatternRunOut.model_validate(row) for row in rows]


# --------------------------------------------------------------------------- #
# Supply chain calibration (human approval only)
# --------------------------------------------------------------------------- #


@router.post(
    "/supply-chain-calibration/runs",
    response_model=SupplyChainCalibrationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Propose a supply chain calibration",
)
async def create_calibration_run(
    db: DbSession,
    workspace_id: WorkspaceId,
) -> SupplyChainCalibrationOut:
    """Propose successful/failure patterns (never applied automatically)."""
    try:
        run = await supply_chain_learning.run_supply_chain_calibration(
            db, workspace_id=workspace_id, trace_id=get_trace_id()
        )
    except supply_chain_learning.SupplyChainLearningError as exc:
        raise _http_error(exc) from exc
    return SupplyChainCalibrationOut.model_validate(run)


@router.get(
    "/supply-chain-calibration/runs",
    response_model=list[SupplyChainCalibrationOut],
    summary="List supply chain calibration runs",
)
async def list_calibration_runs(
    db: DbSession,
    workspace_id: WorkspaceId,
    status_filter: str | None = Query(default=None, alias="status", max_length=16),
    limit: int = 50,
) -> list[SupplyChainCalibrationOut]:
    """Return calibration runs, newest first."""
    rows = await supply_chain_learning.list_supply_chain_calibration_runs(
        db, workspace_id=workspace_id, status=status_filter, limit=limit
    )
    return [SupplyChainCalibrationOut.model_validate(row) for row in rows]


@router.post(
    "/supply-chain-calibration/runs/{run_id}/approve",
    response_model=SupplyChainCalibrationOut,
    summary="Approve a supply chain calibration proposal (human-only)",
)
async def approve_calibration_run(
    run_id: UUID,
    body: CalibrationApproveRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> SupplyChainCalibrationOut:
    """Record human approval; business rules are never auto-edited."""
    try:
        run = await supply_chain_learning.approve_supply_chain_calibration(
            db,
            workspace_id=workspace_id,
            run_id=run_id,
            actor=body.actor,
            note=body.note,
            trace_id=get_trace_id(),
        )
    except supply_chain_learning.SupplyChainLearningError as exc:
        raise _http_error(exc) from exc
    return SupplyChainCalibrationOut.model_validate(run)


@router.post(
    "/supply-chain-calibration/runs/{run_id}/reject",
    response_model=SupplyChainCalibrationOut,
    summary="Reject a supply chain calibration proposal (human-only)",
)
async def reject_calibration_run(
    run_id: UUID,
    body: CalibrationApproveRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> SupplyChainCalibrationOut:
    """Record human rejection; no pattern changes."""
    try:
        run = await supply_chain_learning.reject_supply_chain_calibration(
            db,
            workspace_id=workspace_id,
            run_id=run_id,
            actor=body.actor,
            note=body.note,
            trace_id=get_trace_id(),
        )
    except supply_chain_learning.SupplyChainLearningError as exc:
        raise _http_error(exc) from exc
    return SupplyChainCalibrationOut.model_validate(run)
