"""
统一经营看板 API 端点
支持经营指标查询、趋势分析、产品表现、营销 ROI
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.dashboard_service import (
    generate_daily_metrics,
    get_dashboard_status,
    get_dashboard_summary,
    get_product_performance,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ============================================
# 请求/响应模型
# ============================================

class GenerateDailyMetricsRequest(BaseModel):
    """生成每日经营指标请求"""
    date: str | None = Field(None, description="日期（YYYY-MM-DD），默认今天")
    orders_data: list[dict[str, Any]] | None = Field(None, description="订单数据列表")
    ad_spend: float = Field(0, description="广告投入", ge=0)


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
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """
    获取经营看板汇总数据

    包含：今日数据、本周数据、本月数据、上周数据、环比趋势、关键指标。
    支持自定义时间范围。
    """
    try:
        summary = get_dashboard_summary(start_date, end_date)
        return {
            "success": True,
            "summary": summary,
        }
    except Exception as e:
        logger.exception("Get dashboard summary failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Get dashboard summary failed: {e!s}",
        )


@router.post(
    "/daily-metrics",
    summary="生成每日经营指标",
)
async def generate_daily_metrics_endpoint(
    request: GenerateDailyMetricsRequest,
) -> dict[str, Any]:
    """
    生成每日经营指标

    基于订单数据和广告投入，计算订单、收入、成本、毛利、营销 ROI、客户等指标。
    生成后自动保存为每日数据文件。
    """
    try:
        metrics = generate_daily_metrics(
            date=request.date,
            orders_data=request.orders_data,
            ad_spend=request.ad_spend,
        )
        return {
            "success": True,
            "metrics": metrics,
            "message": "每日经营指标生成成功",
        }
    except Exception as e:
        logger.exception("Generate daily metrics failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Generate daily metrics failed: {e!s}",
        )


@router.get(
    "/product-performance",
    summary="获取产品表现排行",
)
async def get_product_performance_endpoint(
    limit: int = 10,
) -> dict[str, Any]:
    """
    获取产品表现排行

    包含：销量、收入、毛利率、趋势。
    支持限制返回数量。
    """
    try:
        performance = get_product_performance(limit)
        return {
            "success": True,
            "performance": performance,
        }
    except Exception as e:
        logger.exception("Get product performance failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Get product performance failed: {e!s}",
        )


@router.get(
    "/key-metrics",
    summary="获取关键经营指标",
)
async def get_key_metrics() -> dict[str, Any]:
    """
    获取关键经营指标（精简版）

    返回最核心的经营指标：今日收入、今日订单、毛利率、ROAS、
    本周收入、本周订单、本月收入、本月订单、环比趋势。
    """
    try:
        summary = get_dashboard_summary()
        key_metrics = summary["key_metrics"]
        trends = summary["trends"]

        return {
            "success": True,
            "key_metrics": key_metrics,
            "trends": trends,
            "generated_at": summary["period"]["generated_at"],
        }
    except Exception as e:
        logger.exception("Get key metrics failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Get key metrics failed: {e!s}",
        )
