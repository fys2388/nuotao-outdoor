"""反馈回流服务 — 执行结果回流到 Agent，形成学习闭环。

核心流程：
1. Agent 生成建议 → 入库 (pending_approval)
2. 人工审批 → 执行 → 结果记录
3. 人工/自动评分 → 反馈入库
4. 反馈回流服务定期汇总 → 生成 Agent 学习摘要
5. 学习摘要注入 Agent 下次运行的上下文 → Agent 持续优化

这是系统从「每天产报告」升级到「每天在进化」的关键模块。
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_suggestion import AgentSuggestion

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 反馈统计
# --------------------------------------------------------------------------- #

async def get_feedback_stats(
    session: AsyncSession,
    *,
    agent_id: str | None = None,
    days: int = 30,
    workspace_id: UUID | None = None,
) -> dict[str, Any]:
    """获取 Agent 建议反馈统计（用于学习摘要和运营看板）。

    Returns:
        {
            "total_suggestions": int,
            "approval_rate": float,          # 审批通过率
            "execution_rate": float,          # 执行完成率
            "avg_feedback_score": float,      # 平均反馈评分
            "by_type": {type: {count, avg_score}},
            "by_agent": {agent_id: {count, avg_score}},
            "top_successful": [...],          # 评分最高的建议
            "top_failed": [...],              # 执行失败的建议
        }
    """
    since = datetime.now(UTC) - timedelta(days=days)

    base_stmt = select(AgentSuggestion).where(AgentSuggestion.created_at >= since)
    if workspace_id:
        base_stmt = base_stmt.where(AgentSuggestion.workspace_id == workspace_id)
    if agent_id:
        base_stmt = base_stmt.where(AgentSuggestion.agent_id == agent_id)

    result = await session.execute(base_stmt)
    suggestions = list(result.scalars().all())

    if not suggestions:
        return {
            "total_suggestions": 0,
            "approval_rate": 0.0,
            "execution_rate": 0.0,
            "avg_feedback_score": 0.0,
            "by_type": {},
            "by_agent": {},
            "top_successful": [],
            "top_failed": [],
        }

    total = len(suggestions)
    approved = sum(1 for s in suggestions if s.status in ("approved", "executing", "completed", "failed"))
    completed = sum(1 for s in suggestions if s.status == "completed")
    failed = sum(1 for s in suggestions if s.status == "failed")
    scored = [s for s in suggestions if s.feedback_score is not None]
    avg_score = sum(s.feedback_score for s in scored) / len(scored) if scored else 0.0

    # 按类型统计
    by_type: dict[str, dict] = defaultdict(lambda: {"count": 0, "scores": [], "completed": 0, "failed": 0})
    for s in suggestions:
        t = s.suggestion_type
        by_type[t]["count"] += 1
        if s.feedback_score is not None:
            by_type[t]["scores"].append(s.feedback_score)
        if s.status == "completed":
            by_type[t]["completed"] += 1
        if s.status == "failed":
            by_type[t]["failed"] += 1

    by_type_result = {}
    for t, data in by_type.items():
        by_type_result[t] = {
            "count": data["count"],
            "avg_score": sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0.0,
            "completed": data["completed"],
            "failed": data["failed"],
        }

    # 按 Agent 统计
    by_agent: dict[str, dict] = defaultdict(lambda: {"count": 0, "scores": []})
    for s in suggestions:
        by_agent[s.agent_id]["count"] += 1
        if s.feedback_score is not None:
            by_agent[s.agent_id]["scores"].append(s.feedback_score)

    by_agent_result = {}
    for a, data in by_agent.items():
        by_agent_result[a] = {
            "count": data["count"],
            "avg_score": sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0.0,
        }

    # 最成功的建议（评分>=4）
    top_successful = sorted(
        [s for s in suggestions if s.feedback_score and s.feedback_score >= 4],
        key=lambda s: s.feedback_score,
        reverse=True,
    )[:10]

    # 失败建议
    top_failed = [s for s in suggestions if s.status == "failed"][:10]

    return {
        "total_suggestions": total,
        "approval_rate": round(approved / total, 3) if total else 0.0,
        "execution_rate": round(completed / total, 3) if total else 0.0,
        "failure_rate": round(failed / total, 3) if total else 0.0,
        "avg_feedback_score": round(avg_score, 2),
        "by_type": by_type_result,
        "by_agent": by_agent_result,
        "top_successful": [_summarize(s) for s in top_successful],
        "top_failed": [_summarize(s) for s in top_failed],
    }


# --------------------------------------------------------------------------- #
# 学习摘要生成（注入 Agent 上下文）
# --------------------------------------------------------------------------- #

async def generate_learning_summary(
    session: AsyncSession,
    *,
    agent_id: str,
    days: int = 7,
    workspace_id: UUID | None = None,
) -> str:
    """为指定 Agent 生成学习摘要文本，注入其下次运行的上下文。

    摘要包含：
    - 近期建议统计（通过率/执行率/评分）
    - 成功模式（高评分建议的共性）
    - 失败教训（被拒绝/执行失败的建议原因）
    - 改进建议（基于反馈数据的具体优化方向）

    Returns:
        学习摘要文本（可直接拼入 Agent 提示词）
    """
    stats = await get_feedback_stats(
        session, agent_id=agent_id, days=days, workspace_id=workspace_id
    )

    if stats["total_suggestions"] == 0:
        return f"[学习摘要] 过去 {days} 天无建议记录，继续保持当前策略。"

    lines = [
        f"[学习摘要 - Agent: {agent_id} - 过去 {days} 天]",
        f"",
        f"📊 总体表现:",
        f"  - 生成建议: {stats['total_suggestions']} 条",
        f"  - 审批通过率: {stats['approval_rate']:.1%}",
        f"  - 执行完成率: {stats['execution_rate']:.1%}",
        f"  - 失败率: {stats['failure_rate']:.1%}",
        f"  - 平均反馈评分: {stats['avg_feedback_score']:.2f}/5.0",
    ]

    # 成功模式
    if stats["top_successful"]:
        lines.append("")
        lines.append("✅ 成功模式（高评分建议）:")
        for s in stats["top_successful"][:5]:
            lines.append(f"  - [{s['type']}] {s['title']} (评分: {s['score']})")

    # 失败教训
    if stats["top_failed"]:
        lines.append("")
        lines.append("❌ 失败教训（执行失败建议）:")
        for s in stats["top_failed"][:5]:
            error = s.get("error", "未知错误")[:100]
            lines.append(f"  - [{s['type']}] {s['title']} - 错误: {error}")

    # 按类型表现
    lines.append("")
    lines.append("📈 各类型表现:")
    for t, data in sorted(stats["by_type"].items(), key=lambda x: x[1]["avg_score"], reverse=True):
        lines.append(
            f"  - {t}: {data['count']}条, 均分{data['avg_score']:.1f}, "
            f"完成{data['completed']}, 失败{data['failed']}"
        )

    # 改进建议
    lines.append("")
    lines.append("💡 改进方向:")
    if stats["avg_feedback_score"] < 3.0:
        lines.append("  - 整体评分偏低，建议减少建议数量、提升单条建议的质量和可执行性")
    if stats["approval_rate"] < 0.5:
        lines.append("  - 审批通过率低，建议在建议中提供更充分的数据支撑和预期影响分析")
    if stats["failure_rate"] > 0.2:
        lines.append("  - 执行失败率高，建议检查 execution_params 是否完整、目标服务是否可用")
    if not lines[-1].startswith("  -"):
        lines.append("  - 整体表现良好，继续保持当前策略，关注高评分建议的模式复制")

    lines.append("")
    lines.append("[学习摘要结束]")

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 批量学习标记
# --------------------------------------------------------------------------- #

async def process_learnable_suggestions(
    session: AsyncSession,
    *,
    agent_id: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """处理可学习的建议：生成学习摘要并标记为已学习。

    由调度器定期调用（如每日一次），将有反馈的建议转化为 Agent 学习素材。
    """
    from app.services.agent_suggestion_service import get_learnable_suggestions, mark_learned

    suggestions = await get_learnable_suggestions(session, agent_id=agent_id, limit=limit)
    if not suggestions:
        return {"processed": 0, "message": "无可学习建议"}

    # 按 Agent 分组生成学习摘要
    agent_ids = set(s.agent_id for s in suggestions)
    summaries = {}
    for aid in agent_ids:
        summary = await generate_learning_summary(session, agent_id=aid, days=30)
        summaries[aid] = summary

    # 标记为已学习
    ids = [s.id for s in suggestions]
    learned_count = await mark_learned(session, ids)

    logger.info("处理可学习建议: %d 条, 涉及 %d 个 Agent", learned_count, len(agent_ids))

    return {
        "processed": learned_count,
        "agents": list(agent_ids),
        "summaries_generated": len(summaries),
    }


# --------------------------------------------------------------------------- #
# 辅助
# --------------------------------------------------------------------------- #

def _summarize(s: AgentSuggestion) -> dict[str, Any]:
    """将建议对象转为摘要 dict。"""
    return {
        "id": s.id,
        "agent_id": s.agent_id,
        "type": s.suggestion_type,
        "title": s.title,
        "status": s.status,
        "score": s.feedback_score,
        "priority": s.priority,
        "risk_level": s.risk_level,
        "error": s.execution_error,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }
