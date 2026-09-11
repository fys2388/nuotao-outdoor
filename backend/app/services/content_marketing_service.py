"""Content marketing service (M3.2): ContentItem, EDMCampaign, SEORecord.

Database-backed CRUD with approval workflow, version control, event audit,
and optimistic concurrency control. Replaces JSON-file storage.

Content approval workflow:
  draft -> pending_review -> approved -> published
  pending_review -> rejected -> draft
  (approved -> archived)

Rules:
-未经approved不得published
- status changes go through service functions, not direct client status assignment
- version increments on every content update (optimistic locking)
- all state transitions write to event_log
- workspace isolation enforced on every query
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content_marketing import (
    CONTENT_STATUSES,
    ContentItem,
    EDMCampaign,
    EDM_STATUSES,
    SEORecord,
)
from app.services import event_service

logger = logging.getLogger(__name__)

# Content approval workflow transitions.
CONTENT_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"pending_review", "archived"},
    "pending_review": {"approved", "rejected"},
    "approved": {"published", "archived"},
    "rejected": {"draft"},
    "published": {"archived"},
    "archived": set(),
}

# EDM campaign status transitions.
EDM_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"scheduled", "cancelled"},
    "scheduled": {"active", "cancelled"},
    "active": {"paused", "completed"},
    "paused": {"active", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


class ContentMarketingError(Exception):
    """Base content marketing error."""


class ContentNotFound(ContentMarketingError):
    """Content item not found."""


class ContentStateError(ContentMarketingError):
    """Invalid state transition."""


class ContentVersionConflict(ContentMarketingError):
    """Optimistic locking version conflict."""


# --------------------------------------------------------------------------- #
# ContentItem CRUD
# --------------------------------------------------------------------------- #


async def create_content_item(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    content_type: str,
    title: str,
    body: str | None = None,
    content_json: dict[str, Any] | None = None,
    product_id: UUID | None = None,
    language: str = "en",
    keywords: list[str] | None = None,
    source: str = "ai_generated",
    trace_id: str | None = None,
) -> ContentItem:
    """Create a new content item in draft status."""
    item = ContentItem(
        workspace_id=workspace_id,
        content_type=content_type,
        title=title,
        body=body,
        content_json=content_json or {},
        product_id=product_id,
        status="draft",
        language=language,
        keywords=keywords or [],
        version=1,
        source=source,
        trace_id=trace_id,
    )
    session.add(item)
    await session.flush()

    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="content.created",
        entity_type="content_item",
        entity_id=str(item.id),
        payload={"content_type": content_type, "title": title, "source": source},
        trace_id=trace_id,
    )
    logger.info("content created: id=%s type=%s trace=%s", item.id, content_type, trace_id)
    return item


async def get_content_item(
    session: AsyncSession, *, workspace_id: UUID, content_id: UUID
) -> ContentItem:
    result = await session.execute(
        select(ContentItem).where(ContentItem.id == content_id, ContentItem.workspace_id == workspace_id)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise ContentNotFound(f"content item {content_id} not found")
    return item


async def list_content_items(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    content_type: str | None = None,
    status: str | None = None,
    product_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[ContentItem]:
    query = select(ContentItem).where(ContentItem.workspace_id == workspace_id)
    if content_type:
        query = query.where(ContentItem.content_type == content_type)
    if status:
        query = query.where(ContentItem.status == status)
    if product_id:
        query = query.where(ContentItem.product_id == product_id)
    query = query.order_by(ContentItem.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(query)
    return list(result.scalars().all())


async def update_content_item(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    content_id: UUID,
    title: str | None = None,
    body: str | None = None,
    content_json: dict[str, Any] | None = None,
    keywords: list[str] | None = None,
    expected_version: int | None = None,
    trace_id: str | None = None,
) -> ContentItem:
    """Update content item with optimistic locking.

    If expected_version is provided and does not match current version,
    raises ContentVersionConflict (concurrent update protection).
    Version increments on every update. Content must be in draft/rejected
    status to be edited; approved/published content cannot be modified directly.
    """
    item = await get_content_item(session, workspace_id=workspace_id, content_id=content_id)

    # Optimistic locking check.
    if expected_version is not None and item.version != expected_version:
        raise ContentVersionConflict(
            f"version conflict: expected={expected_version}, current={item.version}"
        )

    # Approved/published content cannot be edited directly; must create new version.
    if item.status in ("approved", "published"):
        raise ContentStateError(
            f"cannot edit content in '{item.status}' status; "
            f"revert to draft or create a new version"
        )

    if title is not None:
        item.title = title
    if body is not None:
        item.body = body
    if content_json is not None:
        item.content_json = content_json
    if keywords is not None:
        item.keywords = keywords

    item.version += 1
    await session.flush()

    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="content.updated",
        entity_type="content_item",
        entity_id=str(item.id),
        payload={"version": item.version, "fields_updated": [k for k in [title, body, content_json, keywords] if k is not None]},
        trace_id=trace_id,
    )
    return item


# --------------------------------------------------------------------------- #
# ContentItem approval workflow
# --------------------------------------------------------------------------- #


def _check_content_transition(current: str, target: str) -> None:
    allowed = CONTENT_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise ContentStateError(f"invalid content transition: {current} -> {target}")


async def submit_content_for_review(
    session: AsyncSession, *, workspace_id: UUID, content_id: UUID, trace_id: str | None = None
) -> ContentItem:
    """draft -> pending_review."""
    item = await get_content_item(session, workspace_id=workspace_id, content_id=content_id)
    _check_content_transition(item.status, "pending_review")
    item.status = "pending_review"
    await session.flush()
    await event_service.create_event(
        session, workspace_id=workspace_id, event_type="content.submitted_for_review",
        entity_type="content_item", entity_id=str(item.id),
        payload={"previous": "draft"}, trace_id=trace_id,
    )
    return item


async def approve_content(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    content_id: UUID,
    approved_by: str,
    quality_score: float | None = None,
    trace_id: str | None = None,
) -> ContentItem:
    """pending_review -> approved. approved_by comes from auth context."""
    item = await get_content_item(session, workspace_id=workspace_id, content_id=content_id)
    _check_content_transition(item.status, "approved")
    item.status = "approved"
    item.approved_by = approved_by
    item.approved_at = datetime.now(UTC)
    if quality_score is not None:
        item.quality_score = quality_score
    await session.flush()
    await event_service.create_event(
        session, workspace_id=workspace_id, event_type="content.approved",
        entity_type="content_item", entity_id=str(item.id),
        payload={"approved_by": approved_by, "quality_score": quality_score, "previous": "pending_review"},
        trace_id=trace_id,
    )
    logger.info("content approved: id=%s by=%s trace=%s", item.id, approved_by, trace_id)
    return item


async def reject_content(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    content_id: UUID,
    rejected_by: str,
    reason: str,
    trace_id: str | None = None,
) -> ContentItem:
    """pending_review -> rejected."""
    item = await get_content_item(session, workspace_id=workspace_id, content_id=content_id)
    _check_content_transition(item.status, "rejected")
    item.status = "rejected"
    item.rejection_reason = reason
    await session.flush()
    await event_service.create_event(
        session, workspace_id=workspace_id, event_type="content.rejected",
        entity_type="content_item", entity_id=str(item.id),
        payload={"rejected_by": rejected_by, "reason": reason, "previous": "pending_review"},
        trace_id=trace_id,
    )
    return item


async def publish_content(
    session: AsyncSession, *, workspace_id: UUID, content_id: UUID, trace_id: str | None = None
) -> ContentItem:
    """approved -> published. Cannot publish without approval."""
    item = await get_content_item(session, workspace_id=workspace_id, content_id=content_id)
    _check_content_transition(item.status, "published")
    item.status = "published"
    item.published_at = datetime.now(UTC)
    await session.flush()
    await event_service.create_event(
        session, workspace_id=workspace_id, event_type="content.published",
        entity_type="content_item", entity_id=str(item.id),
        payload={"previous": "approved", "published_at": item.published_at.isoformat()},
        trace_id=trace_id,
    )
    logger.info("content published: id=%s trace=%s", item.id, trace_id)
    return item


async def revert_content_to_draft(
    session: AsyncSession, *, workspace_id: UUID, content_id: UUID, trace_id: str | None = None
) -> ContentItem:
    """rejected -> draft (for re-editing after rejection)."""
    item = await get_content_item(session, workspace_id=workspace_id, content_id=content_id)
    _check_content_transition(item.status, "draft")
    item.status = "draft"
    item.rejection_reason = None
    await session.flush()
    await event_service.create_event(
        session, workspace_id=workspace_id, event_type="content.reverted_to_draft",
        entity_type="content_item", entity_id=str(item.id),
        payload={"previous": "rejected"}, trace_id=trace_id,
    )
    return item


async def archive_content(
    session: AsyncSession, *, workspace_id: UUID, content_id: UUID, trace_id: str | None = None
) -> ContentItem:
    """draft/approved/published -> archived."""
    item = await get_content_item(session, workspace_id=workspace_id, content_id=content_id)
    _check_content_transition(item.status, "archived")
    item.status = "archived"
    await session.flush()
    await event_service.create_event(
        session, workspace_id=workspace_id, event_type="content.archived",
        entity_type="content_item", entity_id=str(item.id),
        payload={"previous": item.status}, trace_id=trace_id,
    )
    return item


# --------------------------------------------------------------------------- #
# EDMCampaign CRUD
# --------------------------------------------------------------------------- #


async def create_edm_campaign(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    name: str,
    campaign_type: str,
    subject: str | None = None,
    from_name: str = "Nuotao Outdoor",
    from_email: str = "noreply@nuotaooutdoor.com",
    content_json: dict[str, Any] | None = None,
    flow_config: dict[str, Any] | None = None,
    segment_filter: dict[str, Any] | None = None,
    scheduled_at: datetime | None = None,
    trace_id: str | None = None,
) -> EDMCampaign:
    campaign = EDMCampaign(
        workspace_id=workspace_id,
        name=name,
        campaign_type=campaign_type,
        status="draft",
        subject=subject,
        from_name=from_name,
        from_email=from_email,
        content_json=content_json or {},
        flow_config=flow_config or {},
        segment_filter=segment_filter or {},
        scheduled_at=scheduled_at,
        trace_id=trace_id,
    )
    session.add(campaign)
    await session.flush()
    await event_service.create_event(
        session, workspace_id=workspace_id, event_type="edm.campaign_created",
        entity_type="edm_campaign", entity_id=str(campaign.id),
        payload={"name": name, "campaign_type": campaign_type}, trace_id=trace_id,
    )
    return campaign


async def get_edm_campaign(
    session: AsyncSession, *, workspace_id: UUID, campaign_id: UUID
) -> EDMCampaign:
    result = await session.execute(
        select(EDMCampaign).where(EDMCampaign.id == campaign_id, EDMCampaign.workspace_id == workspace_id)
    )
    campaign = result.scalar_one_or_none()
    if campaign is None:
        raise ContentNotFound(f"EDM campaign {campaign_id} not found")
    return campaign


async def list_edm_campaigns(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    campaign_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[EDMCampaign]:
    query = select(EDMCampaign).where(EDMCampaign.workspace_id == workspace_id)
    if campaign_type:
        query = query.where(EDMCampaign.campaign_type == campaign_type)
    if status:
        query = query.where(EDMCampaign.status == status)
    query = query.order_by(EDMCampaign.created_at.desc()).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def update_edm_campaign(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    campaign_id: UUID,
    name: str | None = None,
    subject: str | None = None,
    content_json: dict[str, Any] | None = None,
    flow_config: dict[str, Any] | None = None,
    segment_filter: dict[str, Any] | None = None,
    scheduled_at: datetime | None = None,
    trace_id: str | None = None,
) -> EDMCampaign:
    campaign = await get_edm_campaign(session, workspace_id=workspace_id, campaign_id=campaign_id)
    if campaign.status in ("active", "completed"):
        raise ContentStateError(f"cannot edit EDM campaign in '{campaign.status}' status")
    if name is not None:
        campaign.name = name
    if subject is not None:
        campaign.subject = subject
    if content_json is not None:
        campaign.content_json = content_json
    if flow_config is not None:
        campaign.flow_config = flow_config
    if segment_filter is not None:
        campaign.segment_filter = segment_filter
    if scheduled_at is not None:
        campaign.scheduled_at = scheduled_at
    await session.flush()
    await event_service.create_event(
        session, workspace_id=workspace_id, event_type="edm.campaign_updated",
        entity_type="edm_campaign", entity_id=str(campaign.id),
        payload={"fields_updated": "multiple"}, trace_id=trace_id,
    )
    return campaign


async def transition_edm_campaign(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    campaign_id: UUID,
    target_status: str,
    trace_id: str | None = None,
) -> EDMCampaign:
    """Transition EDM campaign status with validation."""
    campaign = await get_edm_campaign(session, workspace_id=workspace_id, campaign_id=campaign_id)
    allowed = EDM_TRANSITIONS.get(campaign.status, set())
    if target_status not in allowed:
        raise ContentStateError(f"invalid EDM transition: {campaign.status} -> {target_status}")
    previous = campaign.status
    campaign.status = target_status
    if target_status == "active":
        campaign.started_at = datetime.now(UTC)
    if target_status == "completed":
        campaign.completed_at = datetime.now(UTC)
    await session.flush()
    await event_service.create_event(
        session, workspace_id=workspace_id, event_type="edm.campaign_status_changed",
        entity_type="edm_campaign", entity_id=str(campaign.id),
        payload={"previous": previous, "target": target_status}, trace_id=trace_id,
    )
    return campaign


# --------------------------------------------------------------------------- #
# SEORecord CRUD
# --------------------------------------------------------------------------- #


async def create_seo_record(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    keyword: str,
    target_url: str | None = None,
    target_page_type: str = "product",
    product_id: UUID | None = None,
    language: str = "en",
    country: str = "US",
    search_volume: int | None = None,
    keyword_difficulty: float | None = None,
    meta_title: str | None = None,
    meta_description: str | None = None,
    trace_id: str | None = None,
) -> SEORecord:
    record = SEORecord(
        workspace_id=workspace_id,
        keyword=keyword,
        target_url=target_url,
        target_page_type=target_page_type,
        product_id=product_id,
        language=language,
        country=country,
        search_volume=search_volume,
        keyword_difficulty=keyword_difficulty,
        meta_title=meta_title,
        meta_description=meta_description,
        status="active",
        trace_id=trace_id,
    )
    session.add(record)
    await session.flush()
    await event_service.create_event(
        session, workspace_id=workspace_id, event_type="seo.record_created",
        entity_type="seo_record", entity_id=str(record.id),
        payload={"keyword": keyword, "target_page_type": target_page_type}, trace_id=trace_id,
    )
    return record


async def get_seo_record(
    session: AsyncSession, *, workspace_id: UUID, seo_id: UUID
) -> SEORecord:
    result = await session.execute(
        select(SEORecord).where(SEORecord.id == seo_id, SEORecord.workspace_id == workspace_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise ContentNotFound(f"SEO record {seo_id} not found")
    return record


async def list_seo_records(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    keyword: str | None = None,
    status: str | None = None,
    product_id: UUID | None = None,
    limit: int = 50,
) -> list[SEORecord]:
    query = select(SEORecord).where(SEORecord.workspace_id == workspace_id)
    if keyword:
        query = query.where(SEORecord.keyword.ilike(f"%{keyword}%"))
    if status:
        query = query.where(SEORecord.status == status)
    if product_id:
        query = query.where(SEORecord.product_id == product_id)
    query = query.order_by(SEORecord.created_at.desc()).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def update_seo_record(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    seo_id: UUID,
    keyword: str | None = None,
    target_url: str | None = None,
    search_volume: int | None = None,
    keyword_difficulty: float | None = None,
    current_position: int | None = None,
    meta_title: str | None = None,
    meta_description: str | None = None,
    status: str | None = None,
    trace_id: str | None = None,
) -> SEORecord:
    record = await get_seo_record(session, workspace_id=workspace_id, seo_id=seo_id)
    if keyword is not None:
        record.keyword = keyword
    if target_url is not None:
        record.target_url = target_url
    if search_volume is not None:
        record.search_volume = search_volume
    if keyword_difficulty is not None:
        record.keyword_difficulty = keyword_difficulty
    if current_position is not None:
        record.current_position = current_position
        if record.best_position is None or current_position < record.best_position:
            record.best_position = current_position
    if meta_title is not None:
        record.meta_title = meta_title
    if meta_description is not None:
        record.meta_description = meta_description
    if status is not None:
        record.status = status
    await session.flush()
    await event_service.create_event(
        session, workspace_id=workspace_id, event_type="seo.record_updated",
        entity_type="seo_record", entity_id=str(record.id),
        payload={"fields_updated": "multiple"}, trace_id=trace_id,
    )
    return record


async def add_seo_ranking_snapshot(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    seo_id: UUID,
    position: int,
    url: str | None = None,
    snapshot_date: datetime | None = None,
    source: str = "manual",
    trace_id: str | None = None,
) -> SEORecord:
    """Add a ranking snapshot to SEO record. source distinguishes real vs AI-estimated data."""
    record = await get_seo_record(session, workspace_id=workspace_id, seo_id=seo_id)
    snapshot = {
        "date": (snapshot_date or datetime.now(UTC)).isoformat(),
        "position": position,
        "url": url or record.target_url,
        "source": source,  # "external_real" / "manual" / "ai_estimated"
    }
    history = list(record.ranking_history)
    history.append(snapshot)
    record.ranking_history = history
    record.current_position = position
    if record.best_position is None or position < record.best_position:
        record.best_position = position
    await session.flush()
    await event_service.create_event(
        session, workspace_id=workspace_id, event_type="seo.ranking_snapshot_added",
        entity_type="seo_record", entity_id=str(record.id),
        payload={"position": position, "source": source}, trace_id=trace_id,
    )
    return record
