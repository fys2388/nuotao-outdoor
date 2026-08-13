"""Customer learning loop endpoints (M3.4): evaluation, pattern mining, calibration, context.

Reads + proposal writes only. No Customer Agent, no automatic customer
support, no automatic business rule changes.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import resolve_actor
from app.core.database import get_db
from app.core.tracing import get_trace_id
from app.core.workspace import get_workspace_id
from app.schemas.customer_learning import (
    CustomerCalibrationOut,
    CustomerEvaluationCreate,
    CustomerEvaluationOut,
    PatternRunOut,
    PatternRunRequest,
)
from app.schemas.product_analyst import CalibrationApproveRequest
from app.services import customer_learning

router = APIRouter(tags=["customer-learning"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]


def _http_error(exc: customer_learning.CustomerLearningError) -> HTTPException:
    """Map learning-loop errors: missing resources -> 404, others -> 400."""
    if "not found" in str(exc):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# --------------------------------------------------------------------------- #
# Customer evaluations
# --------------------------------------------------------------------------- #


@router.post(
    "/customer-evaluations",
    response_model=CustomerEvaluationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record a customer behavior prediction evaluation",
)
async def record_customer_evaluation(
    body: CustomerEvaluationCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> CustomerEvaluationOut:
    """Record and auto-classify (success/failure + error type)."""
    try:
        evaluation = await customer_learning.record_customer_evaluation(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except customer_learning.CustomerLearningError as exc:
        raise _http_error(exc) from exc
    return CustomerEvaluationOut.model_validate(evaluation)


@router.get(
    "/customer-evaluations",
    response_model=list[CustomerEvaluationOut],
    summary="List customer evaluations",
)
async def list_customer_evaluations(
    db: DbSession,
    workspace_id: WorkspaceId,
    customer_id: Annotated[UUID | None, Query()] = None,
    limit: int = 50,
) -> list[CustomerEvaluationOut]:
    """Return evaluations, newest first, optionally filtered by customer."""
    rows = await customer_learning.list_customer_evaluations(
        db, workspace_id=workspace_id, customer_id=customer_id, limit=limit
    )
    return [CustomerEvaluationOut.model_validate(row) for row in rows]


# --------------------------------------------------------------------------- #
# Customer pattern mining
# --------------------------------------------------------------------------- #


@router.post(
    "/customer-pattern-runs",
    response_model=PatternRunOut,
    status_code=status.HTTP_201_CREATED,
    summary="Run deterministic customer pattern mining",
)
async def run_pattern_mining(
    body: PatternRunRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> PatternRunOut:
    """Extract one pattern type (purchase/segment/bundle/churn/pain)."""
    try:
        run = await customer_learning.run_pattern_mining(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except customer_learning.CustomerLearningError as exc:
        raise _http_error(exc) from exc
    return PatternRunOut.model_validate(run)


@router.get(
    "/customer-pattern-runs",
    response_model=list[PatternRunOut],
    summary="List customer pattern runs",
)
async def list_pattern_runs(
    db: DbSession,
    workspace_id: WorkspaceId,
    pattern_type: str | None = Query(default=None, max_length=32),
    customer_id: Annotated[UUID | None, Query()] = None,
    limit: int = 50,
) -> list[PatternRunOut]:
    """Return pattern runs, newest first."""
    rows = await customer_learning.list_pattern_runs(
        db,
        workspace_id=workspace_id,
        pattern_type=pattern_type,
        customer_id=customer_id,
        limit=limit,
    )
    return [PatternRunOut.model_validate(row) for row in rows]


# --------------------------------------------------------------------------- #
# Customer calibration
# --------------------------------------------------------------------------- #


@router.post(
    "/customer-calibration/runs",
    response_model=CustomerCalibrationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Discover customer patterns and propose a calibration",
)
async def create_calibration_run(
    db: DbSession,
    workspace_id: WorkspaceId,
) -> CustomerCalibrationOut:
    """Propose successful/failure patterns (never applied automatically)."""
    try:
        run = await customer_learning.run_customer_calibration(
            db, workspace_id=workspace_id, trace_id=get_trace_id()
        )
    except customer_learning.CustomerLearningError as exc:
        raise _http_error(exc) from exc
    return CustomerCalibrationOut.model_validate(run)


@router.get(
    "/customer-calibration/runs",
    response_model=list[CustomerCalibrationOut],
    summary="List customer calibration runs",
)
async def list_calibration_runs(
    db: DbSession,
    workspace_id: WorkspaceId,
    status_filter: str | None = Query(default=None, alias="status", max_length=16),
    limit: int = 50,
) -> list[CustomerCalibrationOut]:
    """Return calibration runs, newest first."""
    rows = await customer_learning.list_customer_calibration_runs(
        db, workspace_id=workspace_id, status=status_filter, limit=limit
    )
    return [CustomerCalibrationOut.model_validate(row) for row in rows]


@router.post(
    "/customer-calibration/runs/{run_id}/approve",
    response_model=CustomerCalibrationOut,
    summary="Approve a customer calibration proposal (human-only)",
)
async def approve_calibration_run(
    run_id: UUID,
    body: CalibrationApproveRequest,
    request: Request,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> CustomerCalibrationOut:
    """Record human approval; business rules are never auto-edited."""
    try:
        run = await customer_learning.approve_customer_calibration(
            db,
            workspace_id=workspace_id,
            run_id=run_id,
            actor=resolve_actor(request, body.actor),
            note=body.note,
            trace_id=get_trace_id(),
        )
    except customer_learning.CustomerLearningError as exc:
        raise _http_error(exc) from exc
    return CustomerCalibrationOut.model_validate(run)


@router.post(
    "/customer-calibration/runs/{run_id}/reject",
    response_model=CustomerCalibrationOut,
    summary="Reject a customer calibration proposal (human-only)",
)
async def reject_calibration_run(
    run_id: UUID,
    body: CalibrationApproveRequest,
    request: Request,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> CustomerCalibrationOut:
    """Record human rejection; no pattern changes."""
    try:
        run = await customer_learning.reject_customer_calibration(
            db,
            workspace_id=workspace_id,
            run_id=run_id,
            actor=resolve_actor(request, body.actor),
            note=body.note,
            trace_id=get_trace_id(),
        )
    except customer_learning.CustomerLearningError as exc:
        raise _http_error(exc) from exc
    return CustomerCalibrationOut.model_validate(run)


# --------------------------------------------------------------------------- #
# Cross-domain customer context
# --------------------------------------------------------------------------- #


@router.get(
    "/customer-context/{customer_id}",
    summary="Build the cross-domain context for a customer",
)
async def get_customer_context(
    customer_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> dict:
    """Return customer + orders/reviews/refunds/marketing/product/knowledge."""
    try:
        context = await customer_learning.build_customer_context(
            db, workspace_id=workspace_id, customer_id=customer_id, trace_id=get_trace_id()
        )
    except customer_learning.CustomerLearningError as exc:
        raise _http_error(exc) from exc
    return context
