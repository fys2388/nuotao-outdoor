"""
AI 经营周报 API 端点
支持周报生成、查看、列表、异常分析
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.weekly_report_service import (
    generate_weekly_report,
    get_report,
    get_weekly_report_status,
    list_reports,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/weekly-report", tags=["weekly-report"])


# ============================================
# 请求/响应模型
# ============================================

class GenerateReportRequest(BaseModel):
    """生成周报请求"""
    week_start: str | None = Field(None, description="周报开始日期（YYYY-MM-DD）")
    week_end: str | None = Field(None, description="周报结束日期（YYYY-MM-DD）")
    business_data: dict[str, Any] | None = Field(None, description="经营数据（可选，不提供则使用模拟数据）")


# ============================================
# API 端点
# ============================================

@router.get(
    "/status",
    summary="获取 AI 经营周报系统状态",
)
async def get_status() -> dict[str, Any]:
    """获取 AI 经营周报系统状态、支持的功能、异常类型"""
    return get_weekly_report_status()


@router.post(
    "/generate",
    summary="生成 AI 经营周报",
)
async def generate_report_endpoint(
    request: GenerateReportRequest,
) -> dict[str, Any]:
    """
    生成 AI 经营周报

    包含：执行摘要、关键指标、趋势分析、异常检测（含原因分析和建议）、
    AI 洞察、行动项、产品亮点、营销表现、客户洞察、风险因素、下周展望。

    可自定义时间范围和经营数据，不提供数据则使用模拟数据。
    """
    try:
        report = generate_weekly_report(
            week_start=request.week_start,
            week_end=request.week_end,
            business_data=request.business_data,
        )
        return {
            "success": True,
            "report": report,
            "message": "AI 经营周报生成成功",
        }
    except Exception as e:
        logger.exception("Generate weekly report failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Generate weekly report failed: {e!s}",
        )


@router.get(
    "/{report_id}",
    summary="获取周报详情",
)
async def get_report_endpoint(
    report_id: str,
) -> dict[str, Any]:
    """
    获取指定周报的完整详情

    包含周报的所有内容：执行摘要、指标、趋势、异常、洞察、行动项等。
    """
    try:
        report = get_report(report_id)
        return {
            "success": True,
            "report": report,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.exception("Get report failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Get report failed: {e!s}",
        )


@router.get(
    "",
    summary="获取周报列表",
)
async def list_reports_endpoint(
    limit: int = 20,
) -> dict[str, Any]:
    """
    获取周报列表

    返回最近生成的周报列表，包含 ID、标题、时间范围、状态。
    支持限制返回数量。
    """
    try:
        result = list_reports(limit)
        return result
    except Exception as e:
        logger.exception("List reports failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"List reports failed: {e!s}",
        )


@router.get(
    "/{report_id}/anomalies",
    summary="获取周报异常分析",
)
async def get_report_anomalies(
    report_id: str,
) -> dict[str, Any]:
    """
    获取指定周报的异常分析详情

    包含所有检测到的异常指标、严重程度、可能原因、建议行动。
    """
    try:
        report = get_report(report_id)
        anomalies = report.get("anomaly_detection", {})
        return {
            "success": True,
            "report_id": report_id,
            "anomalies": anomalies,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.exception("Get report anomalies failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Get report anomalies failed: {e!s}",
        )


@router.get(
    "/{report_id}/action-items",
    summary="获取周报行动项",
)
async def get_report_action_items(
    report_id: str,
) -> dict[str, Any]:
    """
    获取指定周报的行动项列表

    包含所有建议的行动项、优先级、截止日期、状态。
    """
    try:
        report = get_report(report_id)
        action_items = report.get("action_items", [])
        return {
            "success": True,
            "report_id": report_id,
            "action_items": action_items,
            "summary": {
                "total": len(action_items),
                "high_priority": sum(1 for item in action_items if item.get("priority") == "high"),
                "medium_priority": sum(1 for item in action_items if item.get("priority") == "medium"),
                "low_priority": sum(1 for item in action_items if item.get("priority") == "low"),
            },
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.exception("Get report action items failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Get report action items failed: {e!s}",
        )
