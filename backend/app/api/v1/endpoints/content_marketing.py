"""Content marketing endpoints (M3.2): ContentItem, EDMCampaign, SEORecord.

Database-backed CRUD with approval workflow. All status changes go through
service functions; clients cannot directly set status to approved/published.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.tracing import get_trace_id
from app.core.workspace import get_workspace_id
from app.services import content_marketing_service

router = APIRouter(prefix="/content-marketing", tags=["content-marketing"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]


def _http_error(exc: content_marketing_service.ContentMarketingError) -> HTTPException:
    if isinstance(exc, content_marketing_service.ContentNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, content_marketing_service.ContentStateError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, content_marketing_service.ContentVersionConflict):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _get_actor() -> str:
    """Get authenticated actor from context. TODO: integrate auth middleware."""
    return "system"


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #


class ContentItemCreate(BaseModel):
    content_type: str = Field(..., max_length=32)
    title: str = Field(..., min_length=1, max_length=500)
    body: str | None = None
    content_json: dict | None = None
    product_id: UUID | None = None
    language: str = "en"
    keywords: list[str] | None = None
    source: str = "ai_generated"


class ContentItemUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    content_json: dict | None = None
    keywords: list[str] | None = None
    expected_version: int | None = None


class ContentApproveRequest(BaseModel):
    quality_score: float | None = Field(default=None, ge=0, le=100)


class ContentRejectRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class EDMCampaignCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    campaign_type: str = Field(..., max_length=32)
    subject: str | None = None
    from_name: str = "Nuotao Outdoor"
    from_email: str = "noreply@nuotaooutdoor.com"
    content_json: dict | None = None
    flow_config: dict | None = None
    segment_filter: dict | None = None
    scheduled_at: str | None = None


class EDMCampaignUpdate(BaseModel):
    name: str | None = None
    subject: str | None = None
    content_json: dict | None = None
    flow_config: dict | None = None
    segment_filter: dict | None = None
    scheduled_at: str | None = None


class EDMTransitionRequest(BaseModel):
    target_status: str = Field(..., max_length=16)


class SEORecordCreate(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=255)
    target_url: str | None = None
    target_page_type: str = "product"
    product_id: UUID | None = None
    language: str = "en"
    country: str = "US"
    search_volume: int | None = None
    keyword_difficulty: float | None = None
    meta_title: str | None = None
    meta_description: str | None = None


class SEORecordUpdate(BaseModel):
    keyword: str | None = None
    target_url: str | None = None
    search_volume: int | None = None
    keyword_difficulty: float | None = None
    current_position: int | None = None
    meta_title: str | None = None
    meta_description: str | None = None
    status: str | None = None


class SEORankingSnapshot(BaseModel):
    position: int = Field(..., ge=1)
    url: str | None = None
    snapshot_date: str | None = None
    source: str = Field(default="manual", pattern="^(manual|external_real|ai_estimated)$")


# --------------------------------------------------------------------------- #
# ContentItem endpoints
# --------------------------------------------------------------------------- #


@router.post("/content", status_code=status.HTTP_201_CREATED, summary="Create content item")
async def create_content(body: ContentItemCreate, db: DbSession, workspace_id: WorkspaceId):
    try:
        item = await content_marketing_service.create_content_item(
            db, workspace_id=workspace_id,
            content_type=body.content_type, title=body.title, body=body.body,
            content_json=body.content_json, product_id=body.product_id,
            language=body.language, keywords=body.keywords, source=body.source,
            trace_id=get_trace_id(),
        )
    except content_marketing_service.ContentMarketingError as exc:
        raise _http_error(exc) from exc
    return {"id": str(item.id), "status": item.status, "version": item.version}


@router.get("/content", summary="List content items")
async def list_content(
    db: DbSession, workspace_id: WorkspaceId,
    content_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    product_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    items = await content_marketing_service.list_content_items(
        db, workspace_id=workspace_id, content_type=content_type,
        status=status_filter, product_id=product_id, limit=limit, offset=offset,
    )
    return [{"id": str(i.id), "title": i.title, "content_type": i.content_type,
             "status": i.status, "version": i.version, "created_at": i.created_at.isoformat()}
            for i in items]


@router.get("/content/{content_id}", summary="Get content item")
async def get_content(content_id: UUID, db: DbSession, workspace_id: WorkspaceId):
    try:
        item = await content_marketing_service.get_content_item(
            db, workspace_id=workspace_id, content_id=content_id,
        )
    except content_marketing_service.ContentMarketingError as exc:
        raise _http_error(exc) from exc
    return {"id": str(item.id), "title": item.title, "content_type": item.content_type,
            "body": item.body, "content_json": item.content_json, "status": item.status,
            "version": item.version, "approved_by": item.approved_by,
            "published_at": item.published_at.isoformat() if item.published_at else None,
            "created_at": item.created_at.isoformat()}


@router.put("/content/{content_id}", summary="Update content item (optimistic locking)")
async def update_content(content_id: UUID, body: ContentItemUpdate, db: DbSession, workspace_id: WorkspaceId):
    try:
        item = await content_marketing_service.update_content_item(
            db, workspace_id=workspace_id, content_id=content_id,
            title=body.title, body=body.body, content_json=body.content_json,
            keywords=body.keywords, expected_version=body.expected_version,
            trace_id=get_trace_id(),
        )
    except content_marketing_service.ContentMarketingError as exc:
        raise _http_error(exc) from exc
    return {"id": str(item.id), "status": item.status, "version": item.version}


@router.post("/content/{content_id}/submit", summary="Submit for review (draft -> pending_review)")
async def submit_content(content_id: UUID, db: DbSession, workspace_id: WorkspaceId):
    try:
        item = await content_marketing_service.submit_content_for_review(
            db, workspace_id=workspace_id, content_id=content_id, trace_id=get_trace_id(),
        )
    except content_marketing_service.ContentMarketingError as exc:
        raise _http_error(exc) from exc
    return {"id": str(item.id), "status": item.status}


@router.post("/content/{content_id}/approve", summary="Approve (pending_review -> approved)")
async def approve_content(content_id: UUID, body: ContentApproveRequest, db: DbSession, workspace_id: WorkspaceId):
    try:
        item = await content_marketing_service.approve_content(
            db, workspace_id=workspace_id, content_id=content_id,
            approved_by=_get_actor(), quality_score=body.quality_score, trace_id=get_trace_id(),
        )
    except content_marketing_service.ContentMarketingError as exc:
        raise _http_error(exc) from exc
    return {"id": str(item.id), "status": item.status, "approved_by": item.approved_by}


@router.post("/content/{content_id}/reject", summary="Reject (pending_review -> rejected)")
async def reject_content(content_id: UUID, body: ContentRejectRequest, db: DbSession, workspace_id: WorkspaceId):
    try:
        item = await content_marketing_service.reject_content(
            db, workspace_id=workspace_id, content_id=content_id,
            rejected_by=_get_actor(), reason=body.reason, trace_id=get_trace_id(),
        )
    except content_marketing_service.ContentMarketingError as exc:
        raise _http_error(exc) from exc
    return {"id": str(item.id), "status": item.status, "rejection_reason": item.rejection_reason}


@router.post("/content/{content_id}/publish", summary="Publish (approved -> published)")
async def publish_content(content_id: UUID, db: DbSession, workspace_id: WorkspaceId):
    try:
        item = await content_marketing_service.publish_content(
            db, workspace_id=workspace_id, content_id=content_id, trace_id=get_trace_id(),
        )
    except content_marketing_service.ContentMarketingError as exc:
        raise _http_error(exc) from exc
    return {"id": str(item.id), "status": item.status, "published_at": item.published_at.isoformat()}


@router.post("/content/{content_id}/revert", summary="Revert to draft (rejected -> draft)")
async def revert_content(content_id: UUID, db: DbSession, workspace_id: WorkspaceId):
    try:
        item = await content_marketing_service.revert_content_to_draft(
            db, workspace_id=workspace_id, content_id=content_id, trace_id=get_trace_id(),
        )
    except content_marketing_service.ContentMarketingError as exc:
        raise _http_error(exc) from exc
    return {"id": str(item.id), "status": item.status}


@router.post("/content/{content_id}/archive", summary="Archive content")
async def archive_content(content_id: UUID, db: DbSession, workspace_id: WorkspaceId):
    try:
        item = await content_marketing_service.archive_content(
            db, workspace_id=workspace_id, content_id=content_id, trace_id=get_trace_id(),
        )
    except content_marketing_service.ContentMarketingError as exc:
        raise _http_error(exc) from exc
    return {"id": str(item.id), "status": item.status}


# --------------------------------------------------------------------------- #
# EDMCampaign endpoints
# --------------------------------------------------------------------------- #


@router.post("/edm", status_code=status.HTTP_201_CREATED, summary="Create EDM campaign")
async def create_edm(body: EDMCampaignCreate, db: DbSession, workspace_id: WorkspaceId):
    try:
        campaign = await content_marketing_service.create_edm_campaign(
            db, workspace_id=workspace_id, name=body.name, campaign_type=body.campaign_type,
            subject=body.subject, from_name=body.from_name, from_email=body.from_email,
            content_json=body.content_json, flow_config=body.flow_config,
            segment_filter=body.segment_filter, trace_id=get_trace_id(),
        )
    except content_marketing_service.ContentMarketingError as exc:
        raise _http_error(exc) from exc
    return {"id": str(campaign.id), "name": campaign.name, "status": campaign.status}


@router.get("/edm", summary="List EDM campaigns")
async def list_edm(
    db: DbSession, workspace_id: WorkspaceId,
    campaign_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
):
    campaigns = await content_marketing_service.list_edm_campaigns(
        db, workspace_id=workspace_id, campaign_type=campaign_type,
        status=status_filter, limit=limit,
    )
    return [{"id": str(c.id), "name": c.name, "campaign_type": c.campaign_type,
             "status": c.status, "total_sent": c.total_sent} for c in campaigns]


@router.get("/edm/{campaign_id}", summary="Get EDM campaign")
async def get_edm(campaign_id: UUID, db: DbSession, workspace_id: WorkspaceId):
    try:
        campaign = await content_marketing_service.get_edm_campaign(
            db, workspace_id=workspace_id, campaign_id=campaign_id,
        )
    except content_marketing_service.ContentMarketingError as exc:
        raise _http_error(exc) from exc
    return {"id": str(campaign.id), "name": campaign.name, "campaign_type": campaign.campaign_type,
            "status": campaign.status, "subject": campaign.subject,
            "total_sent": campaign.total_sent, "total_opened": campaign.total_opened,
            "total_clicked": campaign.total_clicked, "revenue_attributed": str(campaign.revenue_attributed),
            "created_at": campaign.created_at.isoformat()}


@router.put("/edm/{campaign_id}", summary="Update EDM campaign")
async def update_edm(campaign_id: UUID, body: EDMCampaignUpdate, db: DbSession, workspace_id: WorkspaceId):
    try:
        campaign = await content_marketing_service.update_edm_campaign(
            db, workspace_id=workspace_id, campaign_id=campaign_id,
            name=body.name, subject=body.subject, content_json=body.content_json,
            flow_config=body.flow_config, segment_filter=body.segment_filter,
            trace_id=get_trace_id(),
        )
    except content_marketing_service.ContentMarketingError as exc:
        raise _http_error(exc) from exc
    return {"id": str(campaign.id), "status": campaign.status}


@router.post("/edm/{campaign_id}/transition", summary="Transition EDM campaign status")
async def transition_edm(campaign_id: UUID, body: EDMTransitionRequest, db: DbSession, workspace_id: WorkspaceId):
    try:
        campaign = await content_marketing_service.transition_edm_campaign(
            db, workspace_id=workspace_id, campaign_id=campaign_id,
            target_status=body.target_status, trace_id=get_trace_id(),
        )
    except content_marketing_service.ContentMarketingError as exc:
        raise _http_error(exc) from exc
    return {"id": str(campaign.id), "status": campaign.status}


# --------------------------------------------------------------------------- #
# SEORecord endpoints
# --------------------------------------------------------------------------- #


@router.post("/seo", status_code=status.HTTP_201_CREATED, summary="Create SEO record")
async def create_seo(body: SEORecordCreate, db: DbSession, workspace_id: WorkspaceId):
    try:
        record = await content_marketing_service.create_seo_record(
            db, workspace_id=workspace_id, keyword=body.keyword, target_url=body.target_url,
            target_page_type=body.target_page_type, product_id=body.product_id,
            language=body.language, country=body.country, search_volume=body.search_volume,
            keyword_difficulty=body.keyword_difficulty, meta_title=body.meta_title,
            meta_description=body.meta_description, trace_id=get_trace_id(),
        )
    except content_marketing_service.ContentMarketingError as exc:
        raise _http_error(exc) from exc
    return {"id": str(record.id), "keyword": record.keyword, "status": record.status}


@router.get("/seo", summary="List SEO records")
async def list_seo(
    db: DbSession, workspace_id: WorkspaceId,
    keyword: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    product_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    records = await content_marketing_service.list_seo_records(
        db, workspace_id=workspace_id, keyword=keyword, status=status_filter,
        product_id=product_id, limit=limit,
    )
    return [{"id": str(r.id), "keyword": r.keyword, "current_position": r.current_position,
             "search_volume": r.search_volume, "status": r.status} for r in records]


@router.get("/seo/{seo_id}", summary="Get SEO record")
async def get_seo(seo_id: UUID, db: DbSession, workspace_id: WorkspaceId):
    try:
        record = await content_marketing_service.get_seo_record(
            db, workspace_id=workspace_id, seo_id=seo_id,
        )
    except content_marketing_service.ContentMarketingError as exc:
        raise _http_error(exc) from exc
    return {"id": str(record.id), "keyword": record.keyword, "target_url": record.target_url,
            "current_position": record.current_position, "best_position": record.best_position,
            "search_volume": record.search_volume, "keyword_difficulty": str(record.keyword_difficulty) if record.keyword_difficulty else None,
            "ranking_history": record.ranking_history, "status": record.status,
            "created_at": record.created_at.isoformat()}


@router.put("/seo/{seo_id}", summary="Update SEO record")
async def update_seo(seo_id: UUID, body: SEORecordUpdate, db: DbSession, workspace_id: WorkspaceId):
    try:
        record = await content_marketing_service.update_seo_record(
            db, workspace_id=workspace_id, seo_id=seo_id, keyword=body.keyword,
            target_url=body.target_url, search_volume=body.search_volume,
            keyword_difficulty=body.keyword_difficulty, current_position=body.current_position,
            meta_title=body.meta_title, meta_description=body.meta_description,
            status=body.status, trace_id=get_trace_id(),
        )
    except content_marketing_service.ContentMarketingError as exc:
        raise _http_error(exc) from exc
    return {"id": str(record.id), "keyword": record.keyword, "status": record.status}


@router.post("/seo/{seo_id}/ranking", summary="Add ranking snapshot")
async def add_seo_ranking(seo_id: UUID, body: SEORankingSnapshot, db: DbSession, workspace_id: WorkspaceId):
    try:
        record = await content_marketing_service.add_seo_ranking_snapshot(
            db, workspace_id=workspace_id, seo_id=seo_id, position=body.position,
            url=body.url, source=body.source, trace_id=get_trace_id(),
        )
    except content_marketing_service.ContentMarketingError as exc:
        raise _http_error(exc) from exc
    return {"id": str(record.id), "current_position": record.current_position,
            "best_position": record.best_position, "ranking_count": len(record.ranking_history)}
