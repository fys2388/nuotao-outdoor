"""Influencer / KOL service (M6): creator profiles and collaboration management.

Phase 1: influencer data is manually entered / CSV imported (no scraping —
compliance-gated per AGENTS.md §4.4). The service provides CRUD for
influencer profiles and collaboration records, plus AI-powered matching
recommendations (via the LLM gateway).

Agent access: Marketing Manager uses ``match_influencers`` via the whitelist
tool; agents never mutate influencer rows directly.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import desc, select

from app.models.influencer import (
    COLLAB_STATUSES,
    COLLAB_TYPES,
    INFLUENCER_PLATFORMS,
    Influencer,
    InfluencerCollaboration,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000001")


class InfluencerServiceError(Exception):
    """Raised when the influencer service cannot fulfill a request."""


def get_influencer_status() -> dict[str, Any]:
    """Return service status and configuration."""
    return {
        "service": "influencer",
        "status": "operational",
        "phase": "Phase 1 (manual entry only, no scraping)",
        "platforms": list(INFLUENCER_PLATFORMS),
        "collab_types": list(COLLAB_TYPES),
        "collab_statuses": list(COLLAB_STATUSES),
    }


# ---------------------------------------------------------------------------
# Influencer CRUD
# ---------------------------------------------------------------------------


async def create_influencer(
    session: AsyncSession,
    *,
    workspace_id: UUID | None = None,
    name: str,
    platform: str = "instagram",
    handle: str | None = None,
    profile_url: str | None = None,
    followers: int = 0,
    engagement_rate: float | None = None,
    avg_views: int | None = None,
    category: str | None = None,
    region: str | None = None,
    language: str | None = None,
    contact_email: str | None = None,
    notes: str | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Create a new influencer profile."""
    if platform not in INFLUENCER_PLATFORMS:
        raise InfluencerServiceError(f"invalid platform: {platform}; must be one of {INFLUENCER_PLATFORMS}")

    ws = workspace_id or DEFAULT_WORKSPACE_ID
    influencer = Influencer(
        id=uuid4(),
        workspace_id=ws,
        name=name,
        handle=handle,
        platform=platform,
        profile_url=profile_url,
        followers=followers,
        engagement_rate=Decimal(str(engagement_rate)) if engagement_rate is not None else None,
        avg_views=avg_views,
        category=category,
        region=region,
        language=language,
        contact_email=contact_email,
        notes=notes,
        trace_id=trace_id,
    )
    session.add(influencer)
    await session.flush()
    return _influencer_to_dict(influencer)


async def update_influencer(
    session: AsyncSession,
    *,
    influencer_id: UUID,
    workspace_id: UUID | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Update an influencer profile (only provided fields)."""
    ws = workspace_id or DEFAULT_WORKSPACE_ID
    influencer = await _get_influencer(session, influencer_id=influencer_id, workspace_id=ws)
    if not influencer:
        raise InfluencerServiceError(f"influencer not found: {influencer_id}")

    allowed_fields = {
        "name", "handle", "platform", "profile_url", "followers",
        "engagement_rate", "avg_views", "category", "region", "language",
        "contact_email", "contact_info", "rating", "notes", "status",
    }
    for key, value in kwargs.items():
        if key in allowed_fields and value is not None:
            if key == "engagement_rate" and value is not None:
                value = Decimal(str(value))
            setattr(influencer, key, value)

    await session.flush()
    return _influencer_to_dict(influencer)


async def delete_influencer(
    session: AsyncSession,
    *,
    influencer_id: UUID,
    workspace_id: UUID | None = None,
) -> dict[str, Any]:
    """Soft-delete an influencer (set status to inactive)."""
    ws = workspace_id or DEFAULT_WORKSPACE_ID
    influencer = await _get_influencer(session, influencer_id=influencer_id, workspace_id=ws)
    if not influencer:
        raise InfluencerServiceError(f"influencer not found: {influencer_id}")
    influencer.status = "inactive"
    await session.flush()
    return {"id": str(influencer.id), "status": influencer.status, "deleted": True}


async def get_influencer(
    session: AsyncSession,
    *,
    influencer_id: UUID,
    workspace_id: UUID | None = None,
) -> dict[str, Any] | None:
    """Get a single influencer by ID."""
    ws = workspace_id or DEFAULT_WORKSPACE_ID
    influencer = await _get_influencer(session, influencer_id=influencer_id, workspace_id=ws)
    return _influencer_to_dict(influencer) if influencer else None


async def list_influencers(
    session: AsyncSession,
    *,
    workspace_id: UUID | None = None,
    platform: str | None = None,
    category: str | None = None,
    region: str | None = None,
    min_followers: int | None = None,
    max_followers: int | None = None,
    status: str = "active",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List influencers with filters."""
    ws = workspace_id or DEFAULT_WORKSPACE_ID
    stmt = select(Influencer).where(Influencer.workspace_id == ws)
    if platform:
        stmt = stmt.where(Influencer.platform == platform)
    if category:
        stmt = stmt.where(Influencer.category == category)
    if region:
        stmt = stmt.where(Influencer.region == region)
    if min_followers is not None:
        stmt = stmt.where(Influencer.followers >= min_followers)
    if max_followers is not None:
        stmt = stmt.where(Influencer.followers <= max_followers)
    if status:
        stmt = stmt.where(Influencer.status == status)
    stmt = stmt.order_by(desc(Influencer.followers)).limit(limit).offset(offset)

    result = await session.execute(stmt)
    influencers = result.scalars().all()

    return {
        "influencers": [_influencer_to_dict(i) for i in influencers],
        "total": len(influencers),
        "limit": limit,
        "offset": offset,
    }


# ---------------------------------------------------------------------------
# AI-powered matching
# ---------------------------------------------------------------------------


async def match_influencers(
    session: AsyncSession,
    *,
    workspace_id: UUID | None = None,
    product_category: str,
    target_region: str | None = None,
    target_platform: str | None = None,
    min_followers: int = 1000,
    max_followers: int = 1000000,
    budget: float | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """AI-powered influencer matching for a product/campaign.

    Filters the influencer database by criteria, then uses a deterministic
    scoring algorithm (follower count, engagement rate, category match,
    region match) to rank candidates. Phase 1 does not call the LLM for
    matching — the scoring is transparent and auditable.
    """
    ws = workspace_id or DEFAULT_WORKSPACE_ID

    # Base filter
    stmt = select(Influencer).where(
        Influencer.workspace_id == ws,
        Influencer.status == "active",
        Influencer.followers >= min_followers,
        Influencer.followers <= max_followers,
    )
    if target_platform:
        stmt = stmt.where(Influencer.platform == target_platform)
    if target_region:
        stmt = stmt.where(Influencer.region == target_region)

    result = await session.execute(stmt)
    candidates = result.scalars().all()

    # Score each candidate
    scored = []
    for inf in candidates:
        score = 0.0
        reasons = []

        # Follower score (log scale, 0-40 points)
        import math
        follower_score = min(40.0, math.log10(max(1, inf.followers)) * 8)
        score += follower_score
        reasons.append(f"follower count ({inf.followers:,})")

        # Engagement score (0-30 points)
        if inf.engagement_rate is not None:
            eng = float(inf.engagement_rate)
            eng_score = min(30.0, eng * 10)
            score += eng_score
            reasons.append(f"engagement rate ({eng:.2f}%)")

        # Category match (0-20 points)
        if inf.category and product_category.lower() in inf.category.lower():
            score += 20.0
            reasons.append("category match")
        elif inf.category:
            score += 5.0
            reasons.append("related category")

        # Region match (0-10 points)
        if target_region and inf.region == target_region:
            score += 10.0
            reasons.append("region match")

        scored.append({
            "influencer": _influencer_to_dict(inf),
            "match_score": round(score, 2),
            "match_reasons": reasons,
        })

    # Sort by score descending
    scored.sort(key=lambda x: x["match_score"], reverse=True)
    top_matches = scored[:limit]

    return {
        "product_category": product_category,
        "target_region": target_region,
        "target_platform": target_platform,
        "candidates_evaluated": len(candidates),
        "matches": top_matches,
        "scoring_method": "deterministic (follower + engagement + category + region)",
    }


# ---------------------------------------------------------------------------
# Collaboration CRUD
# ---------------------------------------------------------------------------


async def create_collaboration(
    session: AsyncSession,
    *,
    workspace_id: UUID | None = None,
    influencer_id: UUID,
    activity_plan_id: UUID | None = None,
    collab_type: str = "product_seeding",
    compensation_amount: float = 0.0,
    compensation_currency: str = "USD",
    commission_rate: float | None = None,
    content_requirements: str | None = None,
    notes: str | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Create a new collaboration record."""
    if collab_type not in COLLAB_TYPES:
        raise InfluencerServiceError(f"invalid collab_type: {collab_type}; must be one of {COLLAB_TYPES}")

    ws = workspace_id or DEFAULT_WORKSPACE_ID
    collab = InfluencerCollaboration(
        id=uuid4(),
        workspace_id=ws,
        influencer_id=influencer_id,
        activity_plan_id=activity_plan_id,
        collab_type=collab_type,
        compensation_amount=Decimal(str(compensation_amount)),
        compensation_currency=compensation_currency,
        commission_rate=Decimal(str(commission_rate)) if commission_rate is not None else None,
        content_requirements=content_requirements,
        status="prospecting",
        notes=notes,
        trace_id=trace_id,
    )
    session.add(collab)
    await session.flush()
    return _collab_to_dict(collab)


async def update_collaboration_status(
    session: AsyncSession,
    *,
    collaboration_id: UUID,
    new_status: str,
    workspace_id: UUID | None = None,
    content_url: str | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Update a collaboration status (prospecting -> contacted -> ... -> completed)."""
    if new_status not in COLLAB_STATUSES:
        raise InfluencerServiceError(f"invalid status: {new_status}; must be one of {COLLAB_STATUSES}")

    ws = workspace_id or DEFAULT_WORKSPACE_ID
    collab = await _get_collaboration(session, collaboration_id=collaboration_id, workspace_id=ws)
    if not collab:
        raise InfluencerServiceError(f"collaboration not found: {collaboration_id}")

    collab.status = new_status
    if new_status == "in_progress" and not collab.started_at:
        collab.started_at = datetime.now(UTC)
    if new_status == "completed":
        collab.completed_at = datetime.now(UTC)
    if content_url:
        collab.content_url = content_url
    if metrics:
        collab.metrics_json = metrics

    await session.flush()
    return _collab_to_dict(collab)


async def list_collaborations(
    session: AsyncSession,
    *,
    workspace_id: UUID | None = None,
    influencer_id: UUID | None = None,
    activity_plan_id: UUID | None = None,
    status: str | None = None,
    collab_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List collaborations with filters."""
    ws = workspace_id or DEFAULT_WORKSPACE_ID
    stmt = select(InfluencerCollaboration).where(InfluencerCollaboration.workspace_id == ws)
    if influencer_id:
        stmt = stmt.where(InfluencerCollaboration.influencer_id == influencer_id)
    if activity_plan_id:
        stmt = stmt.where(InfluencerCollaboration.activity_plan_id == activity_plan_id)
    if status:
        stmt = stmt.where(InfluencerCollaboration.status == status)
    if collab_type:
        stmt = stmt.where(InfluencerCollaboration.collab_type == collab_type)
    stmt = stmt.order_by(desc(InfluencerCollaboration.created_at)).limit(limit).offset(offset)

    result = await session.execute(stmt)
    collabs = result.scalars().all()

    return {
        "collaborations": [_collab_to_dict(c) for c in collabs],
        "total": len(collabs),
        "limit": limit,
        "offset": offset,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _get_influencer(
    session: AsyncSession, *, influencer_id: UUID, workspace_id: UUID
) -> Influencer | None:
    stmt = select(Influencer).where(
        Influencer.id == influencer_id,
        Influencer.workspace_id == workspace_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _get_collaboration(
    session: AsyncSession, *, collaboration_id: UUID, workspace_id: UUID
) -> InfluencerCollaboration | None:
    stmt = select(InfluencerCollaboration).where(
        InfluencerCollaboration.id == collaboration_id,
        InfluencerCollaboration.workspace_id == workspace_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _influencer_to_dict(inf: Influencer) -> dict[str, Any]:
    return {
        "id": str(inf.id),
        "name": inf.name,
        "handle": inf.handle,
        "platform": inf.platform,
        "profile_url": inf.profile_url,
        "followers": inf.followers,
        "engagement_rate": float(inf.engagement_rate) if inf.engagement_rate else None,
        "avg_views": inf.avg_views,
        "category": inf.category,
        "region": inf.region,
        "language": inf.language,
        "contact_email": inf.contact_email,
        "rating": float(inf.rating) if inf.rating else None,
        "notes": inf.notes,
        "status": inf.status,
        "created_at": inf.created_at.isoformat() if inf.created_at else None,
    }


def _collab_to_dict(c: InfluencerCollaboration) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "influencer_id": str(c.influencer_id),
        "activity_plan_id": str(c.activity_plan_id) if c.activity_plan_id else None,
        "collab_type": c.collab_type,
        "compensation_amount": float(c.compensation_amount),
        "compensation_currency": c.compensation_currency,
        "commission_rate": float(c.commission_rate) if c.commission_rate else None,
        "content_requirements": c.content_requirements,
        "content_url": c.content_url,
        "metrics": c.metrics_json,
        "status": c.status,
        "started_at": c.started_at.isoformat() if c.started_at else None,
        "completed_at": c.completed_at.isoformat() if c.completed_at else None,
        "notes": c.notes,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }
