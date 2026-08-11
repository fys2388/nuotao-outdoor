"""Marketing learning loop endpoints (M3.2): evaluation, analysis, knowledge, calibration.

Reads + proposal writes only. No marketing action is executed automatically
and no real ad platform is called.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.tracing import get_trace_id
from app.core.workspace import get_workspace_id
from app.schemas.marketing_learning import (
    CampaignEvaluationCreate,
    CampaignEvaluationOut,
    CreativeAnalysisCreate,
    CreativeAnalysisOut,
    MarketingCalibrationOut,
    MarketingKnowledgeCreate,
    MarketingKnowledgeOut,
)
from app.schemas.product_analyst import CalibrationApproveRequest
from app.services import marketing_learning

router = APIRouter(tags=["marketing-learning"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]


def _http_error(exc: marketing_learning.MarketingLearningError) -> HTTPException:
    """Map learning-loop errors: missing resources -> 404, others -> 400."""
    if "not found" in str(exc):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# --------------------------------------------------------------------------- #
# Campaign evaluations
# --------------------------------------------------------------------------- #


@router.post(
    "/marketing-evaluations",
    response_model=CampaignEvaluationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record a campaign prediction vs actual evaluation",
)
async def record_campaign_evaluation(
    body: CampaignEvaluationCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> CampaignEvaluationOut:
    """Record and auto-classify (success/failure + error type)."""
    try:
        evaluation = await marketing_learning.record_campaign_evaluation(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except marketing_learning.MarketingLearningError as exc:
        raise _http_error(exc) from exc
    return CampaignEvaluationOut.model_validate(evaluation)


@router.get(
    "/marketing-evaluations",
    response_model=list[CampaignEvaluationOut],
    summary="List campaign evaluations",
)
async def list_campaign_evaluations(
    db: DbSession,
    workspace_id: WorkspaceId,
    campaign_id: Annotated[UUID | None, Query()] = None,
    limit: int = 50,
) -> list[CampaignEvaluationOut]:
    """Return evaluations, newest first, optionally filtered by campaign."""
    rows = await marketing_learning.list_campaign_evaluations(
        db, workspace_id=workspace_id, campaign_id=campaign_id, limit=limit
    )
    return [CampaignEvaluationOut.model_validate(row) for row in rows]


# --------------------------------------------------------------------------- #
# Creative analysis runs
# --------------------------------------------------------------------------- #


@router.post(
    "/creative-analysis-runs",
    response_model=CreativeAnalysisOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record a creative analysis run",
)
async def create_creative_analysis(
    body: CreativeAnalysisCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> CreativeAnalysisOut:
    """Audit one analytic pass over a creative asset."""
    try:
        run = await marketing_learning.create_creative_analysis(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except marketing_learning.MarketingLearningError as exc:
        raise _http_error(exc) from exc
    return CreativeAnalysisOut.model_validate(run)


@router.get(
    "/creative-analysis-runs",
    response_model=list[CreativeAnalysisOut],
    summary="List creative analysis runs",
)
async def list_creative_analysis_runs(
    db: DbSession,
    workspace_id: WorkspaceId,
    creative_id: Annotated[UUID | None, Query()] = None,
    limit: int = 50,
) -> list[CreativeAnalysisOut]:
    """Return creative analysis runs, newest first."""
    rows = await marketing_learning.list_creative_analysis_runs(
        db, workspace_id=workspace_id, creative_id=creative_id, limit=limit
    )
    return [CreativeAnalysisOut.model_validate(row) for row in rows]


# --------------------------------------------------------------------------- #
# Marketing knowledge memory
# --------------------------------------------------------------------------- #


@router.post(
    "/marketing-knowledge-entries",
    response_model=MarketingKnowledgeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a marketing knowledge entry",
)
async def create_knowledge_entry(
    body: MarketingKnowledgeCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> MarketingKnowledgeOut:
    """Record a creative/copy/audience/offer/failure pattern."""
    try:
        entry = await marketing_learning.create_knowledge_entry(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except marketing_learning.MarketingLearningError as exc:
        raise _http_error(exc) from exc
    return MarketingKnowledgeOut.model_validate(entry)


@router.get(
    "/marketing-knowledge-entries",
    response_model=list[MarketingKnowledgeOut],
    summary="Query marketing knowledge entries",
)
async def list_knowledge_entries(
    db: DbSession,
    workspace_id: WorkspaceId,
    category: str | None = Query(default=None, max_length=64),
    entry_type: str | None = Query(default=None, max_length=32),
    campaign_id: Annotated[UUID | None, Query()] = None,
    creative_id: Annotated[UUID | None, Query()] = None,
    limit: int = 100,
) -> list[MarketingKnowledgeOut]:
    """Return matching entries, newest first."""
    rows = await marketing_learning.list_knowledge_entries(
        db,
        workspace_id=workspace_id,
        category=category,
        entry_type=entry_type,
        campaign_id=campaign_id,
        creative_id=creative_id,
        limit=limit,
    )
    return [MarketingKnowledgeOut.model_validate(row) for row in rows]


# --------------------------------------------------------------------------- #
# Growth context builder
# --------------------------------------------------------------------------- #


@router.get(
    "/marketing-context/{campaign_id}",
    summary="Build the full marketing context for a campaign",
)
async def get_growth_context(
    campaign_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> dict:
    """Return campaign + creatives/experiments/feedback/evaluations/knowledge."""
    try:
        context = await marketing_learning.build_growth_context(
            db, workspace_id=workspace_id, campaign_id=campaign_id, trace_id=get_trace_id()
        )
    except marketing_learning.MarketingLearningError as exc:
        raise _http_error(exc) from exc
    return context


# --------------------------------------------------------------------------- #
# Marketing calibration
# --------------------------------------------------------------------------- #


@router.post(
    "/marketing-calibration/runs",
    response_model=MarketingCalibrationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Discover marketing patterns and propose a calibration",
)
async def create_calibration_run(
    db: DbSession,
    workspace_id: WorkspaceId,
) -> MarketingCalibrationOut:
    """Propose successful/failure patterns (never applied automatically)."""
    try:
        run = await marketing_learning.run_marketing_calibration(
            db, workspace_id=workspace_id, trace_id=get_trace_id()
        )
    except marketing_learning.MarketingLearningError as exc:
        raise _http_error(exc) from exc
    return MarketingCalibrationOut.model_validate(run)


@router.get(
    "/marketing-calibration/runs",
    response_model=list[MarketingCalibrationOut],
    summary="List marketing calibration runs",
)
async def list_calibration_runs(
    db: DbSession,
    workspace_id: WorkspaceId,
    status_filter: str | None = Query(default=None, alias="status", max_length=16),
    limit: int = 50,
) -> list[MarketingCalibrationOut]:
    """Return calibration runs, newest first."""
    rows = await marketing_learning.list_marketing_calibration_runs(
        db, workspace_id=workspace_id, status=status_filter, limit=limit
    )
    return [MarketingCalibrationOut.model_validate(row) for row in rows]


@router.post(
    "/marketing-calibration/runs/{run_id}/approve",
    response_model=MarketingCalibrationOut,
    summary="Approve a marketing calibration proposal (human-only)",
)
async def approve_calibration_run(
    run_id: UUID,
    body: CalibrationApproveRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> MarketingCalibrationOut:
    """Record human approval; marketing rules are never auto-edited."""
    try:
        run = await marketing_learning.approve_marketing_calibration(
            db,
            workspace_id=workspace_id,
            run_id=run_id,
            actor=body.actor,
            note=body.note,
            trace_id=get_trace_id(),
        )
    except marketing_learning.MarketingLearningError as exc:
        raise _http_error(exc) from exc
    return MarketingCalibrationOut.model_validate(run)


@router.post(
    "/marketing-calibration/runs/{run_id}/reject",
    response_model=MarketingCalibrationOut,
    summary="Reject a marketing calibration proposal (human-only)",
)
async def reject_calibration_run(
    run_id: UUID,
    body: CalibrationApproveRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> MarketingCalibrationOut:
    """Record human rejection; no pattern changes."""
    try:
        run = await marketing_learning.reject_marketing_calibration(
            db,
            workspace_id=workspace_id,
            run_id=run_id,
            actor=body.actor,
            note=body.note,
            trace_id=get_trace_id(),
        )
    except marketing_learning.MarketingLearningError as exc:
        raise _http_error(exc) from exc
    return MarketingCalibrationOut.model_validate(run)
