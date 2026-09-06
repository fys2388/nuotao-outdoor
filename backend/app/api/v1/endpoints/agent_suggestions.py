"""Agent 建议 API 端点 — 建议→审批→执行→反馈闭环的 HTTP 接口。

Routes:
- GET    /api/v1/agent-suggestions/              — 建议列表（分页+过滤）
- POST   /api/v1/agent-suggestions/              — 创建建议
- GET    /api/v1/agent-suggestions/{id}          — 建议详情
- GET    /api/v1/agent-suggestions/pending-stats — 待审批统计
- POST   /api/v1/agent-suggestions/{id}/approve  — 审批通过
- POST   /api/v1/agent-suggestions/{id}/reject   — 拒绝
- POST   /api/v1/agent-suggestions/{id}/skip     — 跳过
- POST   /api/v1/agent-suggestions/{id}/execute  — 手动触发执行
- POST   /api/v1/agent-suggestions/execute-pending — 批量执行已审批建议
- POST   /api/v1/agent-suggestions/{id}/feedback — 提交反馈
- GET    /api/v1/agent-suggestions/feedback-stats — 反馈统计
- GET    /api/v1/agent-suggestions/learning-summary/{agent_id} — 学习摘要
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.agent_suggestion import (
    ApproveRequest,
    ExecutionResponse,
    FeedbackRequest,
    FeedbackStatsResponse,
    LearningSummaryResponse,
    PendingStatsResponse,
    RejectRequest,
    SkipRequest,
    SuggestionCreate,
    SuggestionFilter,
    SuggestionListResponse,
    SuggestionResponse,
)
from app.services import agent_suggestion_service, execution_router, feedback_loop

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent-suggestions", tags=["agent_suggestions"])


# --------------------------------------------------------------------------- #
# 列表 & 详情
# --------------------------------------------------------------------------- #

@router.get("", response_model=SuggestionListResponse)
async def list_suggestions(
    status: str | None = Query(None, description="状态过滤"),
    agent_id: str | None = Query(None, description="Agent ID"),
    suggestion_type: str | None = Query(None, description="类型"),
    priority: str | None = Query(None, description="优先级"),
    risk_level: str | None = Query(None, description="风险等级"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """分页查询建议列表。"""
    items, total = await agent_suggestion_service.list_suggestions(
        db,
        status=status,
        agent_id=agent_id,
        suggestion_type=suggestion_type,
        priority=priority,
        risk_level=risk_level,
        limit=limit,
        offset=offset,
    )
    return SuggestionListResponse(
        items=[SuggestionResponse.model_validate(s) for s in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{suggestion_id}", response_model=SuggestionResponse)
async def get_suggestion(suggestion_id: int, db: AsyncSession = Depends(get_db)):
    """获取建议详情。"""
    suggestion = await agent_suggestion_service.get_suggestion(db, suggestion_id)
    if not suggestion:
        raise HTTPException(status_code=404, detail="建议不存在")
    return SuggestionResponse.model_validate(suggestion)


@router.get("/pending/stats", response_model=PendingStatsResponse)
async def pending_stats(db: AsyncSession = Depends(get_db)):
    """获取待审批建议统计。"""
    stats = await agent_suggestion_service.get_pending_approval_count(db)
    return PendingStatsResponse(total=stats.get("total", 0), by_type=stats)


# --------------------------------------------------------------------------- #
# 创建
# --------------------------------------------------------------------------- #

@router.post("", response_model=SuggestionResponse, status_code=201)
async def create_suggestion(
    req: SuggestionCreate,
    db: AsyncSession = Depends(get_db),
):
    """创建一条 Agent 建议（状态为 pending_approval）。"""
    suggestion = await agent_suggestion_service.create_suggestion(
        db,
        agent_id=req.agent_id,
        suggestion_type=req.suggestion_type,
        title=req.title,
        description=req.description,
        execution_params=req.execution_params,
        execution_action=req.execution_action,
        expected_impact=req.expected_impact,
        priority=req.priority,
        risk_level=req.risk_level,
        agent_run_id=req.agent_run_id,
    )
    await db.commit()
    await db.refresh(suggestion)
    return SuggestionResponse.model_validate(suggestion)


# --------------------------------------------------------------------------- #
# 审批
# --------------------------------------------------------------------------- #

@router.post("/{suggestion_id}/approve", response_model=SuggestionResponse)
async def approve_suggestion(
    suggestion_id: int,
    req: ApproveRequest,
    db: AsyncSession = Depends(get_db),
):
    """审批通过建议。低风险建议会自动执行。"""
    suggestion = await agent_suggestion_service.approve_suggestion(
        db,
        suggestion_id,
        approved_by=req.approved_by,
        comment=req.comment,
        auto_execute=req.auto_execute,
    )
    if not suggestion:
        raise HTTPException(status_code=404, detail="建议不存在或状态不允许审批")
    await db.commit()
    await db.refresh(suggestion)
    return SuggestionResponse.model_validate(suggestion)


@router.post("/{suggestion_id}/reject", response_model=SuggestionResponse)
async def reject_suggestion(
    suggestion_id: int,
    req: RejectRequest,
    db: AsyncSession = Depends(get_db),
):
    """拒绝建议。"""
    suggestion = await agent_suggestion_service.reject_suggestion(
        db, suggestion_id, rejected_by=req.rejected_by, comment=req.comment
    )
    if not suggestion:
        raise HTTPException(status_code=404, detail="建议不存在")
    await db.commit()
    await db.refresh(suggestion)
    return SuggestionResponse.model_validate(suggestion)


@router.post("/{suggestion_id}/skip", response_model=SuggestionResponse)
async def skip_suggestion(
    suggestion_id: int,
    req: SkipRequest,
    db: AsyncSession = Depends(get_db),
):
    """跳过建议（不执行，保留记录）。"""
    suggestion = await agent_suggestion_service.skip_suggestion(
        db, suggestion_id, skipped_by=req.skipped_by, comment=req.comment
    )
    if not suggestion:
        raise HTTPException(status_code=404, detail="建议不存在")
    await db.commit()
    await db.refresh(suggestion)
    return SuggestionResponse.model_validate(suggestion)


# --------------------------------------------------------------------------- #
# 执行
# --------------------------------------------------------------------------- #

@router.post("/{suggestion_id}/execute", response_model=ExecutionResponse)
async def execute_suggestion(
    suggestion_id: int,
    db: AsyncSession = Depends(get_db),
):
    """手动触发执行一条已审批的建议。"""
    suggestion = await agent_suggestion_service.get_suggestion(db, suggestion_id)
    if not suggestion:
        raise HTTPException(status_code=404, detail="建议不存在")
    if suggestion.status not in ("approved", "executing"):
        raise HTTPException(
            status_code=400,
            detail=f"建议状态为 {suggestion.status}，无法执行（需 approved）",
        )

    result = await execution_router.execute_suggestion(db, suggestion)
    await db.commit()
    return ExecutionResponse(suggestion_id=suggestion_id, **result)


@router.post("/execute-pending", response_model=list[ExecutionResponse])
async def execute_pending(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """批量执行所有已审批待执行的建议（由调度器定时调用）。"""
    results = await execution_router.execute_pending_approved(db, limit=limit)
    await db.commit()
    return [ExecutionResponse(**r) for r in results]


# --------------------------------------------------------------------------- #
# 反馈
# --------------------------------------------------------------------------- #

@router.post("/{suggestion_id}/feedback", response_model=SuggestionResponse)
async def submit_feedback(
    suggestion_id: int,
    req: FeedbackRequest,
    db: AsyncSession = Depends(get_db),
):
    """提交执行反馈（评分 1-5）。"""
    suggestion = await agent_suggestion_service.submit_feedback(
        db, suggestion_id, score=req.score, comment=req.comment
    )
    if not suggestion:
        raise HTTPException(status_code=404, detail="建议不存在")
    await db.commit()
    await db.refresh(suggestion)
    return SuggestionResponse.model_validate(suggestion)


@router.get("/feedback/stats", response_model=FeedbackStatsResponse)
async def feedback_stats(
    agent_id: str | None = Query(None),
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """获取建议反馈统计。"""
    stats = await feedback_loop.get_feedback_stats(db, agent_id=agent_id, days=days)
    return FeedbackStatsResponse(**stats)


@router.get("/learning-summary/{agent_id}", response_model=LearningSummaryResponse)
async def learning_summary(
    agent_id: str,
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
):
    """为指定 Agent 生成学习摘要（注入其下次运行上下文）。"""
    summary = await feedback_loop.generate_learning_summary(db, agent_id=agent_id, days=days)
    return LearningSummaryResponse(agent_id=agent_id, days=days, summary=summary)
