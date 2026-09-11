"""Influencer / KOL API endpoints (M6).

Routes:
- GET  /api/v1/influencers/status          — service status
- POST /api/v1/influencers                 — create influencer
- GET  /api/v1/influencers                 — list influencers
- GET  /api/v1/influencers/{id}            — get influencer detail
- PUT  /api/v1/influencers/{id}            — update influencer
- DELETE /api/v1/influencers/{id}           — soft-delete influencer
- POST /api/v1/influencers/match           — AI-powered matching
- POST /api/v1/influencers/{id}/collaborations — create collaboration
- GET  /api/v1/influencers/{id}/collaborations  — list collaborations
- POST /api/v1/collaborations/{id}/status       — update collaboration status
"""
from __future__ import annotations

import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.influencer_service import (
    InfluencerServiceError,
    create_collaboration,
    create_influencer,
    delete_influencer,
    get_influencer,
    get_influencer_status,
    list_collaborations,
    list_influencers,
    match_influencers,
    update_collaboration_status,
    update_influencer,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/influencers", tags=["influencer"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


# ============================================
# Request models
# ============================================


class CreateInfluencerRequest(BaseModel):
    """Request to create an influencer profile."""
    name: str = Field(..., min_length=1, max_length=255)
    platform: str = Field("instagram", description="Platform: instagram/tiktok/youtube/facebook/pinterest/twitter/blog/other")
    handle: str | None = Field(None, max_length=255)
    profile_url: str | None = Field(None, max_length=2048)
    followers: int = Field(0, ge=0)
    engagement_rate: float | None = Field(None, ge=0, le=100)
    avg_views: int | None = Field(None, ge=0)
    category: str | None = Field(None, max_length=128)
    region: str | None = Field(None, max_length=64)
    language: str | None = Field(None, max_length=32)
    contact_email: str | None = Field(None, max_length=255)
    notes: str | None = Field(None, max_length=2000)


class UpdateInfluencerRequest(BaseModel):
    """Request to update an influencer (only provided fields)."""
    name: str | None = None
    handle: str | None = None
    platform: str | None = None
    profile_url: str | None = None
    followers: int | None = None
    engagement_rate: float | None = None
    avg_views: int | None = None
    category: str | None = None
    region: str | None = None
    language: str | None = None
    contact_email: str | None = None
    notes: str | None = None
    status: str | None = None


class MatchRequest(BaseModel):
    """Request for AI-powered influencer matching."""
    product_category: str = Field(..., min_length=1, max_length=128)
    target_region: str | None = None
    target_platform: str | None = None
    min_followers: int = Field(1000, ge=0)
    max_followers: int = Field(1000000, ge=0)
    budget: float | None = None
    limit: int = Field(10, ge=1, le=50)


class CreateCollaborationRequest(BaseModel):
    """Request to create a collaboration."""
    activity_plan_id: str | None = None
    collab_type: str = Field("product_seeding", description="Type: product_seeding/affiliate/sponsored_post/brand_ambassador/other")
    compensation_amount: float = Field(0.0, ge=0)
    compensation_currency: str = "USD"
    commission_rate: float | None = Field(None, ge=0, le=100)
    content_requirements: str | None = Field(None, max_length=2000)
    notes: str | None = Field(None, max_length=2000)


class UpdateCollabStatusRequest(BaseModel):
    """Request to update collaboration status."""
    new_status: str = Field(..., description="New status: prospecting/contacted/negotiating/confirmed/in_progress/completed/cancelled")
    content_url: str | None = None
    metrics: dict[str, Any] | None = None


# ============================================
# API endpoints
# ============================================


@router.get("/status", summary="Get influencer service status")
async def get_status() -> dict[str, Any]:
    return get_influencer_status()


@router.post("", summary="Create a new influencer profile")
async def create_influencer_endpoint(
    request: CreateInfluencerRequest,
    db: DbSession,
) -> dict[str, Any]:
    try:
        result = await create_influencer(db, **request.model_dump(exclude_none=True))
        await db.commit()
        return {"success": True, "influencer": result}
    except InfluencerServiceError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except Exception as e:
        await db.rollback()
        logger.exception("Create influencer failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Create influencer failed: {e!s}") from None


@router.get("", summary="List influencers")
async def list_influencers_endpoint(
    db: DbSession,
    platform: str | None = None,
    category: str | None = None,
    region: str | None = None,
    min_followers: int | None = None,
    max_followers: int | None = None,
    status: str = "active",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    try:
        return await list_influencers(
            db,
            platform=platform,
            category=category,
            region=region,
            min_followers=min_followers,
            max_followers=max_followers,
            status=status,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        logger.exception("List influencers failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"List influencers failed: {e!s}") from None


@router.get("/match", summary="AI-powered influencer matching")
async def match_influencers_endpoint(
    request: MatchRequest,
    db: DbSession,
) -> dict[str, Any]:
    """Match influencers for a product/campaign based on deterministic scoring."""
    try:
        return await match_influencers(
            db,
            product_category=request.product_category,
            target_region=request.target_region,
            target_platform=request.target_platform,
            min_followers=request.min_followers,
            max_followers=request.max_followers,
            budget=request.budget,
            limit=request.limit,
        )
    except Exception as e:
        logger.exception("Match influencers failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Match influencers failed: {e!s}") from None


@router.get("/{influencer_id}", summary="Get influencer detail")
async def get_influencer_endpoint(
    influencer_id: str,
    db: DbSession,
) -> dict[str, Any]:
    result = await get_influencer(db, influencer_id=UUID(influencer_id))
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Influencer not found") from None
    return result


@router.put("/{influencer_id}", summary="Update influencer profile")
async def update_influencer_endpoint(
    influencer_id: str,
    request: UpdateInfluencerRequest,
    db: DbSession,
) -> dict[str, Any]:
    try:
        result = await update_influencer(
            db,
            influencer_id=UUID(influencer_id),
            **request.model_dump(exclude_none=True),
        )
        await db.commit()
        return {"success": True, "influencer": result}
    except InfluencerServiceError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except Exception as e:
        await db.rollback()
        logger.exception("Update influencer failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Update influencer failed: {e!s}") from None


@router.delete("/{influencer_id}", summary="Delete (soft-delete) an influencer")
async def delete_influencer_endpoint(
    influencer_id: str,
    db: DbSession,
) -> dict[str, Any]:
    try:
        result = await delete_influencer(db, influencer_id=UUID(influencer_id))
        await db.commit()
        return {"success": True, "result": result}
    except InfluencerServiceError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except Exception as e:
        await db.rollback()
        logger.exception("Delete influencer failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Delete influencer failed: {e!s}") from None


@router.post("/{influencer_id}/collaborations", summary="Create a collaboration record")
async def create_collaboration_endpoint(
    influencer_id: str,
    request: CreateCollaborationRequest,
    db: DbSession,
) -> dict[str, Any]:
    try:
        activity_plan_id = UUID(request.activity_plan_id) if request.activity_plan_id else None
        result = await create_collaboration(
            db,
            influencer_id=UUID(influencer_id),
            activity_plan_id=activity_plan_id,
            collab_type=request.collab_type,
            compensation_amount=request.compensation_amount,
            compensation_currency=request.compensation_currency,
            commission_rate=request.commission_rate,
            content_requirements=request.content_requirements,
            notes=request.notes,
        )
        await db.commit()
        return {"success": True, "collaboration": result}
    except InfluencerServiceError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except Exception as e:
        await db.rollback()
        logger.exception("Create collaboration failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Create collaboration failed: {e!s}") from None


@router.get("/{influencer_id}/collaborations", summary="List collaborations for an influencer")
async def list_collaborations_endpoint(
    influencer_id: str,
    db: DbSession,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    try:
        return await list_collaborations(
            db,
            influencer_id=UUID(influencer_id),
            status=status,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        logger.exception("List collaborations failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"List collaborations failed: {e!s}") from None


@router.post("/collaborations/{collaboration_id}/status", summary="Update collaboration status")
async def update_collab_status_endpoint(
    collaboration_id: str,
    request: UpdateCollabStatusRequest,
    db: DbSession,
) -> dict[str, Any]:
    try:
        result = await update_collaboration_status(
            db,
            collaboration_id=UUID(collaboration_id),
            new_status=request.new_status,
            content_url=request.content_url,
            metrics=request.metrics,
        )
        await db.commit()
        return {"success": True, "collaboration": result}
    except InfluencerServiceError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except Exception as e:
        await db.rollback()
        logger.exception("Update collab status failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Update collab status failed: {e!s}") from None
