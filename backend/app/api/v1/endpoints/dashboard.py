"""Unified operating dashboard API endpoints."""
from __future__ import annotations

import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.workspace import get_workspace_id
from app.services.dashboard_service import (
    get_dashboard_status,
    get_dashboard_summary_real,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]


# ============================================
# API 端点
# ============================================

@router.get(
    "/status",
    summary="获取经营看板系统状态",
)
async def get_status() -> dict[str, Any]:
    """获取经营看板系统状态、支持的功能、追踪的指标"""
    return get_dashboard_status()


@router.get(
    "/summary",
    summary="获取经营看板汇总数据",
)
async def get_summary(
    db: DbSession,
    workspace_id: WorkspaceId,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Return dashboard totals, comparisons, and cost-quality status."""
    try:
        summary = await get_dashboard_summary_real(
            db,
            workspace_id,
            start_date=start_date,
            end_date=end_date,
        )
        return {
            "success": True,
            "summary": summary,
        }
    except Exception as exc:
        logger.exception("Get dashboard summary failed: %s", str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Get dashboard summary failed: {exc!s}",
        ) from exc


@router.post(
    "/daily-metrics",
    summary="生成每日经营指标",
    status_code=status.HTTP_410_GONE,
    deprecated=True,
)
async def generate_daily_metrics_endpoint() -> dict[str, Any]:
    """Retire the legacy endpoint that estimated cost as 60% of revenue."""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=(
            "This endpoint is retired because it produced estimated profit. "
            "Use persisted order cost snapshots and channel analytics instead."
        ),
    )


@router.get(
    "/product-performance",
    summary="获取产品表现排行",
    status_code=status.HTTP_410_GONE,
    deprecated=True,
)
async def get_product_performance_endpoint() -> dict[str, Any]:
    """Retire the legacy endpoint that returned simulated product rankings."""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=(
            "This endpoint is retired because it returned simulated data. "
            "Use /api/v1/analytics/channel-performance for product inventory signals."
        ),
    )


@router.get(
    "/key-metrics",
    summary="获取关键经营指标",
)
async def get_key_metrics(
    db: DbSession,
    workspace_id: WorkspaceId,
) -> dict[str, Any]:
    """Return the core persisted metrics and period-over-period trends."""
    try:
        summary = await get_dashboard_summary_real(db, workspace_id)
        key_metrics = summary["key_metrics"]
        trends = summary["trends"]

        return {
            "success": True,
            "key_metrics": key_metrics,
            "trends": trends,
            "generated_at": summary["period"]["generated_at"],
        }
    except Exception as exc:
        logger.exception("Get key metrics failed: %s", str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Get key metrics failed: {exc!s}",
        ) from exc
