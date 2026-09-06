"""Agent 建议服务 — 建议生命周期管理（创建/查询/审批/拒绝/执行/反馈）。

与 approval_service.py 的区别：
- approval_service 是通用审批引擎（任意实体的审批流）
- 本服务是 Agent 建议的专属生命周期管理，内嵌审批+执行+反馈闭环
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_suggestion import (
    SUGGESTION_STATUSES,
    SUGGESTION_TYPES,
    AgentSuggestion,
)
from app.schemas.agent_suggestion import (
    SuggestionCreate,
    SuggestionFilter,
    SuggestionUpdate,
)

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000001")


# --------------------------------------------------------------------------- #
# 创建
# --------------------------------------------------------------------------- #

async def create_suggestion(
    session: AsyncSession,
    *,
    agent_id: str,
    suggestion_type: str,
    title: str,
    description: str,
    execution_params: dict[str, Any] | None = None,
    execution_action: str | None = None,
    expected_impact: str | None = None,
    priority: str = "medium",
    risk_level: str = "medium",
    agent_run_id: int | None = None,
    workspace_id: UUID | None = None,
) -> AgentSuggestion:
    """创建一条 Agent 建议，状态为 pending_approval。

    低风险建议可自动审批（auto_approve_low_risk 配置开启时），
    中高风险必须人工审批。
    """
    if suggestion_type not in SUGGESTION_TYPES:
        logger.warning("未知建议类型: %s，降级为 other", suggestion_type)
        suggestion_type = "other"

    suggestion = AgentSuggestion(
        workspace_id=workspace_id or DEFAULT_WORKSPACE_ID,
        agent_id=agent_id,
        agent_run_id=agent_run_id,
        suggestion_type=suggestion_type,
        title=title,
        description=description,
        expected_impact=expected_impact,
        priority=priority,
        risk_level=risk_level,
        execution_params=execution_params or {},
        execution_action=execution_action,
        status="pending_approval",
    )
    session.add(suggestion)
    await session.flush()

    logger.info(
        "Agent建议已创建: id=%s agent=%s type=%s risk=%s",
        suggestion.id, agent_id, suggestion_type, risk_level,
    )

    # 同步推送飞书审批卡片
    try:
        from app.services.feishu_approval_service import send_approval_card
        result = send_approval_card(
            suggestion_id=suggestion.id,
            title=title,
            description=description,
            agent_name=agent_id,
            suggestion_type=suggestion_type,
            risk_level=risk_level,
            execution_params=execution_params,
        )
        logger.info("飞书审批卡片推送结果: suggestion_id=%s, success=%s", suggestion.id, result.get("success") if result else False)
    except Exception as e:
        logger.warning("飞书审批卡片推送失败（非阻塞）: %s", e)

    await session.commit()
    return suggestion


# --------------------------------------------------------------------------- #
# 查询
# --------------------------------------------------------------------------- #

async def get_suggestion(session: AsyncSession, suggestion_id: int) -> AgentSuggestion | None:
    """按 ID 获取建议。"""
    result = await session.execute(
        select(AgentSuggestion).where(AgentSuggestion.id == suggestion_id)
    )
    return result.scalar_one_or_none()


async def list_suggestions(
    session: AsyncSession,
    *,
    workspace_id: UUID | None = None,
    status: str | None = None,
    agent_id: str | None = None,
    suggestion_type: str | None = None,
    priority: str | None = None,
    risk_level: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AgentSuggestion], int]:
    """分页查询建议列表，返回 (列表, 总数)。"""
    stmt = select(AgentSuggestion)
    count_stmt = select(func.count(AgentSuggestion.id))

    if workspace_id:
        stmt = stmt.where(AgentSuggestion.workspace_id == workspace_id)
        count_stmt = count_stmt.where(AgentSuggestion.workspace_id == workspace_id)
    if status:
        stmt = stmt.where(AgentSuggestion.status == status)
        count_stmt = count_stmt.where(AgentSuggestion.status == status)
    if agent_id:
        stmt = stmt.where(AgentSuggestion.agent_id == agent_id)
        count_stmt = count_stmt.where(AgentSuggestion.agent_id == agent_id)
    if suggestion_type:
        stmt = stmt.where(AgentSuggestion.suggestion_type == suggestion_type)
        count_stmt = count_stmt.where(AgentSuggestion.suggestion_type == suggestion_type)
    if priority:
        stmt = stmt.where(AgentSuggestion.priority == priority)
        count_stmt = count_stmt.where(AgentSuggestion.priority == priority)
    if risk_level:
        stmt = stmt.where(AgentSuggestion.risk_level == risk_level)
        count_stmt = count_stmt.where(AgentSuggestion.risk_level == risk_level)

    # 排序：待审批优先，然后按优先级和创建时间
    status_order = func.array_position(
        func.array(["pending_approval", "approved", "executing", "completed", "failed", "rejected", "skipped"]),
        AgentSuggestion.status,
    )
    priority_order = func.array_position(
        func.array(["high", "medium", "low"]),
        AgentSuggestion.priority,
    )
    stmt = stmt.order_by(status_order, priority_order, AgentSuggestion.created_at.desc())
    stmt = stmt.limit(limit).offset(offset)

    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0

    list_result = await session.execute(stmt)
    items = list(list_result.scalars().all())

    return items, total


async def get_pending_approval_count(
    session: AsyncSession, *, workspace_id: UUID | None = None
) -> dict[str, int]:
    """获取待审批建议统计（按类型分组）。"""
    stmt = select(
        AgentSuggestion.suggestion_type,
        func.count(AgentSuggestion.id),
    ).where(AgentSuggestion.status == "pending_approval")
    if workspace_id:
        stmt = stmt.where(AgentSuggestion.workspace_id == workspace_id)
    stmt = stmt.group_by(AgentSuggestion.suggestion_type)

    result = await session.execute(stmt)
    counts = {row[0]: row[1] for row in result.all()}
    counts["total"] = sum(counts.values())
    return counts


# --------------------------------------------------------------------------- #
# 审批
# --------------------------------------------------------------------------- #

async def approve_suggestion(
    session: AsyncSession,
    suggestion_id: int,
    *,
    approved_by: str,
    comment: str | None = None,
    auto_execute: bool = True,
) -> AgentSuggestion | None:
    """审批通过建议。

    Args:
        auto_execute: 是否立即触发执行（低风险建议默认自动执行，
                      中高风险建议审批后进入 approved 状态等待执行调度）
    """
    suggestion = await get_suggestion(session, suggestion_id)
    if not suggestion:
        return None
    if suggestion.status != "pending_approval":
        logger.warning("建议 %s 状态为 %s，无法审批", suggestion_id, suggestion.status)
        return suggestion

    suggestion.status = "approved"
    suggestion.approved_by = approved_by
    suggestion.approved_at = datetime.now(UTC)
    suggestion.approval_comment = comment
    await session.flush()
    await session.commit()

    logger.info("建议 %s 已审批通过 by %s", suggestion_id, approved_by)

    # 低风险且配置了自动执行时，立即触发执行
    if auto_execute and suggestion.risk_level == "low":
        from app.services.execution_router import execute_suggestion
        await execute_suggestion(session, suggestion)

    return suggestion


async def reject_suggestion(
    session: AsyncSession,
    suggestion_id: int,
    *,
    rejected_by: str,
    comment: str | None = None,
) -> AgentSuggestion | None:
    """拒绝建议。"""
    suggestion = await get_suggestion(session, suggestion_id)
    if not suggestion:
        return None
    if suggestion.status != "pending_approval":
        return suggestion

    suggestion.status = "rejected"
    suggestion.approved_by = rejected_by
    suggestion.approved_at = datetime.now(UTC)
    suggestion.approval_comment = comment or "已拒绝"
    await session.flush()
    await session.commit()

    logger.info("建议 %s 已拒绝 by %s", suggestion_id, rejected_by)
    return suggestion


async def skip_suggestion(
    session: AsyncSession,
    suggestion_id: int,
    *,
    skipped_by: str,
    comment: str | None = None,
) -> AgentSuggestion | None:
    """跳过建议（不执行，但保留记录）。"""
    suggestion = await get_suggestion(session, suggestion_id)
    if not suggestion:
        return None

    suggestion.status = "skipped"
    suggestion.approval_comment = comment or "已跳过"
    await session.flush()
    return suggestion


# --------------------------------------------------------------------------- #
# 执行状态更新（由 execution_router 调用）
# --------------------------------------------------------------------------- #

async def mark_executing(session: AsyncSession, suggestion_id: int) -> AgentSuggestion | None:
    """标记为执行中。"""
    suggestion = await get_suggestion(session, suggestion_id)
    if not suggestion or suggestion.status != "approved":
        return suggestion
    suggestion.status = "executing"
    await session.flush()
    return suggestion


async def mark_completed(
    session: AsyncSession,
    suggestion_id: int,
    *,
    result: dict[str, Any] | None = None,
) -> AgentSuggestion | None:
    """标记执行完成。"""
    suggestion = await get_suggestion(session, suggestion_id)
    if not suggestion:
        return None
    suggestion.status = "completed"
    suggestion.executed_at = datetime.now(UTC)
    suggestion.execution_result = result or {}
    await session.flush()

    logger.info("建议 %s 执行完成", suggestion_id)
    return suggestion


async def mark_failed(
    session: AsyncSession,
    suggestion_id: int,
    *,
    error: str,
) -> AgentSuggestion | None:
    """标记执行失败。"""
    suggestion = await get_suggestion(session, suggestion_id)
    if not suggestion:
        return None
    suggestion.status = "failed"
    suggestion.executed_at = datetime.now(UTC)
    suggestion.execution_error = error
    await session.flush()

    logger.error("建议 %s 执行失败: %s", suggestion_id, error)
    return suggestion


# --------------------------------------------------------------------------- #
# 反馈
# --------------------------------------------------------------------------- #

async def submit_feedback(
    session: AsyncSession,
    suggestion_id: int,
    *,
    score: int,
    comment: str | None = None,
) -> AgentSuggestion | None:
    """提交执行反馈（评分 1-5）。"""
    if score not in (1, 2, 3, 4, 5):
        raise ValueError("反馈评分必须为 1-5")

    suggestion = await get_suggestion(session, suggestion_id)
    if not suggestion:
        return None

    suggestion.feedback_score = score
    suggestion.feedback_comment = comment
    suggestion.feedback_at = datetime.now(UTC)
    await session.flush()

    logger.info("建议 %s 收到反馈: 评分=%d", suggestion_id, score)
    return suggestion


async def get_learnable_suggestions(
    session: AsyncSession,
    *,
    agent_id: str | None = None,
    limit: int = 100,
) -> list[AgentSuggestion]:
    """获取可用于 Agent 学习的已完成建议（有反馈且未被学习）。"""
    stmt = select(AgentSuggestion).where(
        AgentSuggestion.status == "completed",
        AgentSuggestion.feedback_score.isnot(None),
        AgentSuggestion.learned == False,  # noqa: E712
    )
    if agent_id:
        stmt = stmt.where(AgentSuggestion.agent_id == agent_id)
    stmt = stmt.order_by(AgentSuggestion.feedback_score.desc()).limit(limit)

    result = await session.execute(stmt)
    return list(result.scalars().all())


async def mark_learned(session: AsyncSession, suggestion_ids: list[int]) -> int:
    """批量标记为已学习。"""
    if not suggestion_ids:
        return 0
    stmt = select(AgentSuggestion).where(AgentSuggestion.id.in_(suggestion_ids))
    result = await session.execute(stmt)
    suggestions = list(result.scalars().all())
    for s in suggestions:
        s.learned = True
    await session.flush()
    return len(suggestions)
