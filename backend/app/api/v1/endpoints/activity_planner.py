"""Activity planner API endpoints (M6).

Routes:
- GET  /api/v1/activity-planner/status          — service status
- POST /api/v1/activity-planner/generate        — generate a new activity plan
- POST /api/v1/activity-planner/{id}/rewrite    — rewrite a plan with feedback
- POST /api/v1/activity-planner/{id}/optimize   — optimize a plan
- GET  /api/v1/activity-planner/plans            — list plans
- GET  /api/v1/activity-planner/plans/{id}       — get plan detail
- POST /api/v1/activity-planner/plans/{id}/approve — approve a plan
- POST /api/v1/activity-planner/plans/{id}/reject  — reject a plan
"""
from __future__ import annotations

import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.activity_planner_service import (
    ActivityPlannerError,
    approve_plan,
    generate_activity_plan,
    get_activity_planner_status,
    get_plan,
    list_plans,
    optimize_activity_plan,
    reject_plan,
    rewrite_activity_plan,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/activity-planner", tags=["activity_planner"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


# ============================================
# Request models
# ============================================


class GeneratePlanRequest(BaseModel):
    """Request to generate an activity plan."""
    name: str = Field(..., description="Activity name", min_length=1, max_length=255)
    activity_type: str = Field("other", description="Activity type: big_promotion/new_launch/clearance/seasonal/member_exclusive/flash_sale/other")
    start_date: str | None = Field(None, description="Start date (YYYY-MM-DD)")
    end_date: str | None = Field(None, description="End date (YYYY-MM-DD)")
    budget_total: float = Field(0.0, description="Total budget", ge=0)
    budget_currency: str = Field("USD", description="Budget currency")
    target_revenue: float | None = Field(None, description="Target revenue", ge=0)
    target_orders: int | None = Field(None, description="Target order count", ge=0)
    target_roas: float | None = Field(None, description="Target ROAS", ge=0)
    product_ids: list[str] | None = Field(None, description="Associated product IDs")
    additional_context: dict[str, Any] | None = Field(None, description="Additional context for the LLM")
    created_by: str = Field("system", description="Creator identifier")


class RewritePlanRequest(BaseModel):
    """Request to rewrite a plan."""
    feedback: str = Field(..., description="Human feedback for rewriting", min_length=1, max_length=4000)


class OptimizePlanRequest(BaseModel):
    """Request to optimize a plan."""
    historical_data: dict[str, Any] | None = Field(None, description="Historical performance data")


class ApprovalRequest(BaseModel):
    """Approval request."""
    approved_by: str = Field("admin", description="Approver identifier")


class RejectRequest(BaseModel):
    """Reject request."""
    reject_reason: str = Field(..., description="Reason for rejection", min_length=1, max_length=2000)


# ============================================
# API endpoints
# ============================================


@router.get("/status", summary="Get activity planner service status")
async def get_status() -> dict[str, Any]:
    """Return service status and configuration."""
    return get_activity_planner_status()


@router.post("/generate", summary="Generate a new activity plan")
async def generate_plan(
    request: GeneratePlanRequest,
    db: DbSession,
) -> dict[str, Any]:
    """Generate an activity plan via AI. The plan enters pending approval status."""
    try:
        result = await generate_activity_plan(
            db,
            name=request.name,
            activity_type=request.activity_type,
            start_date=request.start_date,
            end_date=request.end_date,
            budget_total=request.budget_total,
            budget_currency=request.budget_currency,
            target_revenue=request.target_revenue,
            target_orders=request.target_orders,
            target_roas=request.target_roas,
            product_ids=request.product_ids,
            additional_context=request.additional_context,
            created_by=request.created_by,
        )
        await db.commit()
        return {"success": True, "plan": result}
    except ActivityPlannerError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except Exception as e:
        await db.rollback()
        logger.exception("Generate plan failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Generate plan failed: {e!s}") from None


@router.post("/plans/{plan_id}/rewrite", summary="Rewrite an activity plan with feedback")
async def rewrite_plan(
    plan_id: str,
    request: RewritePlanRequest,
    db: DbSession,
) -> dict[str, Any]:
    """Rewrite an existing plan based on human feedback. Creates a new version."""
    try:
        result = await rewrite_activity_plan(
            db,
            plan_id=UUID(plan_id),
            feedback=request.feedback,
        )
        await db.commit()
        return {"success": True, "plan": result}
    except ActivityPlannerError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except Exception as e:
        await db.rollback()
        logger.exception("Rewrite plan failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Rewrite plan failed: {e!s}") from None


@router.post("/plans/{plan_id}/optimize", summary="Optimize an activity plan")
async def optimize_plan(
    plan_id: str,
    request: OptimizePlanRequest,
    db: DbSession,
) -> dict[str, Any]:
    """Optimize a plan based on historical performance data. Creates a new version."""
    try:
        result = await optimize_activity_plan(
            db,
            plan_id=UUID(plan_id),
            historical_data=request.historical_data,
        )
        await db.commit()
        return {"success": True, "plan": result}
    except ActivityPlannerError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except Exception as e:
        await db.rollback()
        logger.exception("Optimize plan failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Optimize plan failed: {e!s}") from None


@router.get("/plans", summary="List activity plans")
async def list_activity_plans(
    db: DbSession,
    status_filter: str | None = None,
    activity_type: str | None = None,
    approval_status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List activity plans with filters."""
    try:
        return await list_plans(
            db,
            status=status_filter,
            activity_type=activity_type,
            approval_status=approval_status,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        logger.exception("List plans failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"List plans failed: {e!s}") from None


@router.get("/plans/{plan_id}", summary="Get activity plan detail")
async def get_plan_detail(
    plan_id: str,
    db: DbSession,
) -> dict[str, Any]:
    """Get a single plan by ID."""
    result = await get_plan(db, plan_id=UUID(plan_id))
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found") from None
    return result


@router.post("/plans/{plan_id}/approve", summary="Approve an activity plan")
async def approve_activity_plan(
    plan_id: str,
    request: ApprovalRequest,
    db: DbSession,
) -> dict[str, Any]:
    """Approve a plan for execution (human-in-the-loop gate)."""
    try:
        result = await approve_plan(
            db,
            plan_id=UUID(plan_id),
            approved_by=request.approved_by,
        )
        await db.commit()
        return {"success": True, "plan": result}
    except ActivityPlannerError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except Exception as e:
        await db.rollback()
        logger.exception("Approve plan failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Approve plan failed: {e!s}") from None


@router.post("/plans/{plan_id}/reject", summary="Reject an activity plan")
async def reject_activity_plan(
    plan_id: str,
    request: RejectRequest,
    db: DbSession,
) -> dict[str, Any]:
    """Reject a plan."""
    try:
        result = await reject_plan(
            db,
            plan_id=UUID(plan_id),
            reject_reason=request.reject_reason,
        )
        await db.commit()
        return {"success": True, "plan": result}
    except ActivityPlannerError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except Exception as e:
        await db.rollback()
        logger.exception("Reject plan failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Reject plan failed: {e!s}") from None
