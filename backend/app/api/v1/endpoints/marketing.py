"""Marketing intelligence endpoints (M3.1): campaigns, creatives, feedback, experiments.

Data capture + proposal only - no marketing action is executed automatically.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.tracing import get_trace_id
from app.core.workspace import get_workspace_id
from app.schemas.marketing import (
    CampaignCreate,
    CampaignOut,
    CampaignUpdate,
    CreativeCreate,
    CreativeOut,
    CreativeUpdate,
    ExperimentCompleteRequest,
    ExperimentCreate,
    ExperimentOut,
    ExperimentStartRequest,
    FeedbackCreate,
    FeedbackOut,
    FeedbackUpdate,
)
from app.services import marketing

router = APIRouter(tags=["marketing"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]


def _http_error(exc: marketing.MarketingError) -> HTTPException:
    """Map service errors to 404 (missing) or 400/409 (conflict/invalid)."""
    message = str(exc)
    if "not found" in message:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)
    if "already exists" in message:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def _campaign_out(campaign) -> CampaignOut:
    """Serialize a campaign including the derived ROI metric."""
    out = CampaignOut.model_validate(campaign)
    out.roi = marketing.calculate_roi(campaign.revenue, campaign.spend)
    return out


# --------------------------------------------------------------------------- #
# Campaigns
# --------------------------------------------------------------------------- #


@router.post("/campaigns", response_model=CampaignOut, status_code=201, summary="Create a campaign")
async def create_campaign(
    body: CampaignCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> CampaignOut:
    """Register an external campaign; derived metrics computed when omitted."""
    try:
        campaign = await marketing.create_campaign(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except marketing.MarketingError as exc:
        raise _http_error(exc) from exc
    return _campaign_out(campaign)


@router.get("/campaigns", response_model=list[CampaignOut], summary="List campaigns")
async def list_campaigns(
    db: DbSession,
    workspace_id: WorkspaceId,
    platform: str | None = Query(default=None, max_length=16),
    product_id: Annotated[UUID | None, Query()] = None,
    campaign_status: str | None = Query(default=None, alias="status", max_length=16),
    limit: int = 50,
    offset: int = 0,
) -> list[CampaignOut]:
    """Return campaigns with optional platform/product/status filters."""
    rows = await marketing.list_campaigns(
        db,
        workspace_id=workspace_id,
        platform=platform,
        product_id=product_id,
        status=campaign_status,
        limit=limit,
        offset=offset,
    )
    return [_campaign_out(row) for row in rows]


@router.get("/campaigns/{campaign_id}", response_model=CampaignOut, summary="Get a campaign")
async def get_campaign(
    campaign_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> CampaignOut:
    """Return one campaign by internal id."""
    campaign = await marketing._load_campaign(  # noqa: SLF001
        db, workspace_id=workspace_id, campaign_id=campaign_id
    )
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="campaign not found")
    return _campaign_out(campaign)


@router.put("/campaigns/{campaign_id}", response_model=CampaignOut, summary="Update a campaign")
async def update_campaign(
    campaign_id: UUID,
    body: CampaignUpdate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> CampaignOut:
    """Partially update a campaign; derived metrics are recomputed."""
    try:
        campaign = await marketing.update_campaign(
            db,
            workspace_id=workspace_id,
            campaign_id=campaign_id,
            data=body,
            trace_id=get_trace_id(),
        )
    except marketing.MarketingError as exc:
        raise _http_error(exc) from exc
    return _campaign_out(campaign)


@router.delete("/campaigns/{campaign_id}", status_code=204, summary="Delete a campaign")
async def delete_campaign(
    campaign_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> None:
    """Delete a campaign (audited via event)."""
    try:
        await marketing.delete_campaign(
            db, workspace_id=workspace_id, campaign_id=campaign_id, trace_id=get_trace_id()
        )
    except marketing.MarketingError as exc:
        raise _http_error(exc) from exc


# --------------------------------------------------------------------------- #
# Creative assets
# --------------------------------------------------------------------------- #


@router.post("/creatives", response_model=CreativeOut, status_code=201, summary="Create a creative")
async def create_creative(
    body: CreativeCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> CreativeOut:
    """Register a creative asset for a product."""
    try:
        creative = await marketing.create_creative(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except marketing.MarketingError as exc:
        raise _http_error(exc) from exc
    return CreativeOut.model_validate(creative)


@router.get("/creatives", response_model=list[CreativeOut], summary="List creatives")
async def list_creatives(
    db: DbSession,
    workspace_id: WorkspaceId,
    product_id: Annotated[UUID | None, Query()] = None,
    platform: str | None = Query(default=None, max_length=16),
    limit: int = 50,
) -> list[CreativeOut]:
    """Return creatives with optional product/platform filters."""
    rows = await marketing.list_creatives(
        db, workspace_id=workspace_id, product_id=product_id, platform=platform, limit=limit
    )
    return [CreativeOut.model_validate(row) for row in rows]


@router.get("/creatives/{creative_id}", response_model=CreativeOut, summary="Get a creative")
async def get_creative(
    creative_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> CreativeOut:
    """Return one creative asset."""
    creative = await marketing._load_creative(  # noqa: SLF001
        db, workspace_id=workspace_id, creative_id=creative_id
    )
    if creative is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="creative not found")
    return CreativeOut.model_validate(creative)


@router.put("/creatives/{creative_id}", response_model=CreativeOut, summary="Update a creative")
async def update_creative(
    creative_id: UUID,
    body: CreativeUpdate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> CreativeOut:
    """Partially update a creative."""
    try:
        creative = await marketing.update_creative(
            db,
            workspace_id=workspace_id,
            creative_id=creative_id,
            data=body,
            trace_id=get_trace_id(),
        )
    except marketing.MarketingError as exc:
        raise _http_error(exc) from exc
    return CreativeOut.model_validate(creative)


@router.delete("/creatives/{creative_id}", status_code=204, summary="Delete a creative")
async def delete_creative(
    creative_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> None:
    """Delete a creative (audited via event)."""
    try:
        await marketing.delete_creative(
            db, workspace_id=workspace_id, creative_id=creative_id, trace_id=get_trace_id()
        )
    except marketing.MarketingError as exc:
        raise _http_error(exc) from exc


# --------------------------------------------------------------------------- #
# Customer feedback
# --------------------------------------------------------------------------- #


@router.post("/feedback", response_model=FeedbackOut, status_code=201, summary="Create feedback")
async def create_feedback(
    body: FeedbackCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> FeedbackOut:
    """Record customer feedback."""
    try:
        feedback = await marketing.create_feedback(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except marketing.MarketingError as exc:
        raise _http_error(exc) from exc
    return FeedbackOut.model_validate(feedback)


@router.get("/feedback", response_model=list[FeedbackOut], summary="Query feedback")
async def list_feedback(
    db: DbSession,
    workspace_id: WorkspaceId,
    product_id: Annotated[UUID | None, Query()] = None,
    source: str | None = Query(default=None, max_length=24),
    sentiment: str | None = Query(default=None, max_length=16),
    limit: int = 50,
) -> list[FeedbackOut]:
    """Return feedback filtered by product/source/sentiment."""
    rows = await marketing.list_feedback(
        db,
        workspace_id=workspace_id,
        product_id=product_id,
        source=source,
        sentiment=sentiment,
        limit=limit,
    )
    return [FeedbackOut.model_validate(row) for row in rows]


@router.get("/feedback/{feedback_id}", response_model=FeedbackOut, summary="Get feedback")
async def get_feedback(
    feedback_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> FeedbackOut:
    """Return one feedback record."""
    feedback = await marketing._load_feedback(  # noqa: SLF001
        db, workspace_id=workspace_id, feedback_id=feedback_id
    )
    if feedback is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="feedback not found")
    return FeedbackOut.model_validate(feedback)


@router.put("/feedback/{feedback_id}", response_model=FeedbackOut, summary="Update feedback")
async def update_feedback(
    feedback_id: UUID,
    body: FeedbackUpdate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> FeedbackOut:
    """Update feedback classification (content stays immutable)."""
    try:
        feedback = await marketing.update_feedback(
            db,
            workspace_id=workspace_id,
            feedback_id=feedback_id,
            data=body,
            trace_id=get_trace_id(),
        )
    except marketing.MarketingError as exc:
        raise _http_error(exc) from exc
    return FeedbackOut.model_validate(feedback)


@router.delete("/feedback/{feedback_id}", status_code=204, summary="Delete feedback")
async def delete_feedback(
    feedback_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> None:
    """Delete feedback (audited via event)."""
    try:
        await marketing.delete_feedback(
            db, workspace_id=workspace_id, feedback_id=feedback_id, trace_id=get_trace_id()
        )
    except marketing.MarketingError as exc:
        raise _http_error(exc) from exc


# --------------------------------------------------------------------------- #
# Marketing experiments (lifecycle)
# --------------------------------------------------------------------------- #


@router.post(
    "/marketing-experiments",
    response_model=ExperimentOut,
    status_code=201,
    summary="Propose a marketing A/B experiment",
)
async def propose_experiment(
    body: ExperimentCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ExperimentOut:
    """Propose an experiment (status=proposed; nothing is executed)."""
    try:
        experiment = await marketing.propose_experiment(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except marketing.MarketingError as exc:
        raise _http_error(exc) from exc
    return ExperimentOut.model_validate(experiment)


@router.get(
    "/marketing-experiments",
    response_model=list[ExperimentOut],
    summary="List experiments",
)
async def list_experiments(
    db: DbSession,
    workspace_id: WorkspaceId,
    product_id: Annotated[UUID | None, Query()] = None,
    status_filter: str | None = Query(default=None, alias="status", max_length=16),
    limit: int = 50,
) -> list[ExperimentOut]:
    """Return experiments with optional product/status filters."""
    rows = await marketing.list_experiments(
        db,
        workspace_id=workspace_id,
        product_id=product_id,
        status=status_filter,
        limit=limit,
    )
    return [ExperimentOut.model_validate(row) for row in rows]


@router.get(
    "/marketing-experiments/{experiment_id}",
    response_model=ExperimentOut,
    summary="Get an experiment",
)
async def get_experiment(
    experiment_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ExperimentOut:
    """Return one experiment."""
    experiment = await marketing._load_experiment(  # noqa: SLF001
        db, workspace_id=workspace_id, experiment_id=experiment_id
    )
    if experiment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="experiment not found")
    return ExperimentOut.model_validate(experiment)


@router.post(
    "/marketing-experiments/{experiment_id}/start",
    response_model=ExperimentOut,
    summary="Start an experiment (proposed -> active)",
)
async def start_experiment(
    experiment_id: UUID,
    body: ExperimentStartRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ExperimentOut:
    """Activate the experiment with the executed plan."""
    try:
        experiment = await marketing.start_experiment(
            db,
            workspace_id=workspace_id,
            experiment_id=experiment_id,
            data=body,
            trace_id=get_trace_id(),
        )
    except marketing.MarketingError as exc:
        raise _http_error(exc) from exc
    return ExperimentOut.model_validate(experiment)


@router.post(
    "/marketing-experiments/{experiment_id}/complete",
    response_model=ExperimentOut,
    summary="Complete an experiment (active -> completed)",
)
async def complete_experiment(
    experiment_id: UUID,
    body: ExperimentCompleteRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ExperimentOut:
    """Complete the experiment and compute A/B calibration."""
    try:
        experiment = await marketing.complete_experiment(
            db,
            workspace_id=workspace_id,
            experiment_id=experiment_id,
            data=body,
            trace_id=get_trace_id(),
        )
    except marketing.MarketingError as exc:
        raise _http_error(exc) from exc
    return ExperimentOut.model_validate(experiment)
