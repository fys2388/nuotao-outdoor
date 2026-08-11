"""Calibration endpoints (M2.3): learning loop reports + approval workflow."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.tracing import get_trace_id
from app.core.workspace import get_workspace_id
from app.schemas.calibration import (
    CalibrationApproveRequest,
    ConfidenceCalibrationOut,
    ScoreCalibrationRunOut,
)
from app.services import calibration

router = APIRouter(prefix="/calibration", tags=["calibration"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]


def _http_error(exc: calibration.CalibrationError) -> HTTPException:
    """Map calibration errors: missing resources -> 404, others -> 400."""
    if "not found" in str(exc):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get(
    "/confidence-report",
    response_model=list[ConfidenceCalibrationOut],
    summary="Generate/report AI confidence vs actual success calibration",
)
async def confidence_report(
    db: DbSession,
    workspace_id: WorkspaceId,
) -> list[ConfidenceCalibrationOut]:
    """Aggregate confidence buckets (LOW/MEDIUM/HIGH) against success rates."""
    try:
        rows = await calibration.generate_confidence_report(
            db, workspace_id=workspace_id, trace_id=get_trace_id()
        )
    except calibration.CalibrationError as exc:
        raise _http_error(exc) from exc
    return [ConfidenceCalibrationOut.model_validate(row) for row in rows]


@router.post(
    "/runs",
    response_model=ScoreCalibrationRunOut,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a score weight calibration proposal",
)
async def create_calibration_run(
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ScoreCalibrationRunOut:
    """Propose weight adjustments (never applied automatically)."""
    try:
        run = await calibration.run_score_calibration(
            db, workspace_id=workspace_id, trace_id=get_trace_id()
        )
    except calibration.CalibrationError as exc:
        raise _http_error(exc) from exc
    return ScoreCalibrationRunOut.model_validate(run)


@router.get(
    "/runs",
    response_model=list[ScoreCalibrationRunOut],
    summary="List calibration runs",
)
async def list_calibration_runs(
    db: DbSession,
    workspace_id: WorkspaceId,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = 50,
) -> list[ScoreCalibrationRunOut]:
    """Return calibration runs, newest first."""
    rows = await calibration.list_calibration_runs(
        db, workspace_id=workspace_id, status=status_filter, limit=limit
    )
    return [ScoreCalibrationRunOut.model_validate(row) for row in rows]


@router.post(
    "/runs/{run_id}/approve",
    response_model=ScoreCalibrationRunOut,
    summary="Approve a calibration proposal (human-only)",
)
async def approve_calibration_run(
    run_id: UUID,
    body: CalibrationApproveRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ScoreCalibrationRunOut:
    """Approve the proposal; rules/code are never modified automatically."""
    try:
        run = await calibration.approve_calibration(
            db,
            workspace_id=workspace_id,
            run_id=run_id,
            data=body,
            trace_id=get_trace_id(),
        )
    except calibration.CalibrationError as exc:
        raise _http_error(exc) from exc
    return ScoreCalibrationRunOut.model_validate(run)


@router.post(
    "/runs/{run_id}/reject",
    response_model=ScoreCalibrationRunOut,
    summary="Reject a calibration proposal (human-only)",
)
async def reject_calibration_run(
    run_id: UUID,
    body: CalibrationApproveRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ScoreCalibrationRunOut:
    """Reject the proposal; no weight changes."""
    try:
        run = await calibration.reject_calibration(
            db,
            workspace_id=workspace_id,
            run_id=run_id,
            data=body,
            trace_id=get_trace_id(),
        )
    except calibration.CalibrationError as exc:
        raise _http_error(exc) from exc
    return ScoreCalibrationRunOut.model_validate(run)
