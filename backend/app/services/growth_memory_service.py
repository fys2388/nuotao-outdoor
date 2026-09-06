"""成长记忆服务 — 记忆的 CRUD、检索、注入、置信度管理。

核心功能：
1. 从 Agent 建议/运行结果中自动提取记忆
2. 按 Agent/类型/标签/关键词检索记忆
3. 为 Agent 运行构建上下文（注入相关记忆）
4. 置信度管理（自动提升/降低/人工审核）
5. 记忆过期和归档
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.growth_memory import MEMORY_SOURCES, MEMORY_TYPES, GrowthMemory

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000001")

# 置信度阈值
CONFIDENCE_AUTO_INJECT = 0.5   # 高于此值自动注入 Agent 上下文
CONFIDENCE_PENDING_REVIEW = 0.3  # 低于此值进入待审核


# --------------------------------------------------------------------------- #
# 创建
# --------------------------------------------------------------------------- #

async def create_memory(
    session: AsyncSession,
    *,
    agent_id: str,
    memory_type: str,
    title: str,
    content: str,
    summary: str | None = None,
    tags: list[str] | None = None,
    source: str = "agent_suggestion",
    source_id: str | None = None,
    confidence: float = 0.5,
    metadata: dict[str, Any] | None = None,
    expires_at: datetime | None = None,
    workspace_id: UUID | None = None,
) -> GrowthMemory:
    """创建一条成长记忆。"""
    if memory_type not in MEMORY_TYPES:
        logger.warning("未知记忆类型: %s，降级为 other", memory_type)
        memory_type = "other"
    if source not in MEMORY_SOURCES:
        logger.warning("未知记忆来源: %s，降级为 manual", source)
        source = "manual"

    confidence = max(0.0, min(1.0, confidence))
    status = "pending_review" if confidence < CONFIDENCE_PENDING_REVIEW else "active"

    memory = GrowthMemory(
        workspace_id=workspace_id or DEFAULT_WORKSPACE_ID,
        agent_id=agent_id,
        memory_type=memory_type,
        title=title,
        content=content,
        summary=summary,
        tags=tags or [],
        source=source,
        source_id=source_id,
        confidence=confidence,
        status=status,
        expires_at=expires_at,
        metadata_=metadata or {},
    )
    session.add(memory)
    await session.flush()

    logger.info(
        "成长记忆已创建: id=%s agent=%s type=%s confidence=%.2f",
        memory.id, agent_id, memory_type, confidence,
    )
    return memory


# --------------------------------------------------------------------------- #
# 从建议反馈中自动提取记忆
# --------------------------------------------------------------------------- #

async def extract_memory_from_suggestion(
    session: AsyncSession,
    *,
    suggestion_id: int,
    agent_id: str,
    feedback_score: int,
    suggestion_title: str,
    suggestion_description: str,
    execution_result: dict[str, Any] | None = None,
    execution_error: str | None = None,
) -> GrowthMemory | None:
    """从一条有反馈的建议中自动提取成长记忆。

    - 评分 >= 4 → 提取为 success_pattern
    - 评分 <= 2 或执行失败 → 提取为 failure_lesson
    - 其他 → 不自动提取（避免噪音）
    """
    if feedback_score >= 4:
        memory_type = "success_pattern"
        confidence = min(0.5 + feedback_score * 0.1, 0.9)
        title = f"成功模式: {suggestion_title}"
        content = (
            f"建议「{suggestion_title}」获得高评分 ({feedback_score}/5)。\n\n"
            f"建议内容: {suggestion_description}\n\n"
            f"执行结果: {execution_result or '无详细结果'}\n\n"
            f"关键成功因素: 建议具体、可执行、有明确预期影响。"
        )
        summary = f"「{suggestion_title}」类建议效果好（评分{feedback_score}），可复制该模式。"
        tags = ["success", "high_score", suggestion_title[:20]]

    elif feedback_score <= 2 or execution_error:
        memory_type = "failure_lesson"
        confidence = 0.6
        title = f"失败教训: {suggestion_title}"
        content = (
            f"建议「{suggestion_title}」效果不佳 (评分: {feedback_score}/5)。\n\n"
            f"建议内容: {suggestion_description}\n\n"
            f"执行错误: {execution_error or '无错误信息'}\n\n"
            f"教训: 此类建议需要更多数据支撑或更保守的执行方式。"
        )
        summary = f"「{suggestion_title}」类建议效果差，避免重复类似策略。"
        tags = ["failure", "lesson", suggestion_title[:20]]

    else:
        # 中等评分不自动提取
        return None

    return await create_memory(
        session,
        agent_id=agent_id,
        memory_type=memory_type,
        title=title,
        content=content,
        summary=summary,
        tags=tags,
        source="agent_suggestion",
        source_id=str(suggestion_id),
        confidence=confidence,
        metadata={"suggestion_id": suggestion_id, "feedback_score": feedback_score},
    )


# --------------------------------------------------------------------------- #
# 查询/检索
# --------------------------------------------------------------------------- #

async def get_memory(session: AsyncSession, memory_id: int) -> GrowthMemory | None:
    """按 ID 获取记忆。"""
    result = await session.execute(
        select(GrowthMemory).where(GrowthMemory.id == memory_id)
    )
    return result.scalar_one_or_none()


async def search_memories(
    session: AsyncSession,
    *,
    agent_id: str | None = None,
    memory_type: str | None = None,
    tags: list[str] | None = None,
    keyword: str | None = None,
    min_confidence: float = CONFIDENCE_AUTO_INJECT,
    status: str = "active",
    limit: int = 20,
    offset: int = 0,
    workspace_id: UUID | None = None,
) -> tuple[list[GrowthMemory], int]:
    """检索记忆（支持多条件过滤 + 关键词搜索）。

    关键词搜索匹配 title、content、summary 字段。
    """
    stmt = select(GrowthMemory)
    count_stmt = select(func.count(GrowthMemory.id))

    conditions = []
    if workspace_id:
        conditions.append(GrowthMemory.workspace_id == workspace_id)
    if agent_id:
        # 同时匹配指定 Agent 和全局共享记忆
        conditions.append(or_(GrowthMemory.agent_id == agent_id, GrowthMemory.agent_id == "global"))
    if memory_type:
        conditions.append(GrowthMemory.memory_type == memory_type)
    if status:
        conditions.append(GrowthMemory.status == status)
    if min_confidence > 0:
        conditions.append(GrowthMemory.confidence >= min_confidence)
    if keyword:
        keyword_pattern = f"%{keyword}%"
        conditions.append(
            or_(
                GrowthMemory.title.ilike(keyword_pattern),
                GrowthMemory.content.ilike(keyword_pattern),
                GrowthMemory.summary.ilike(keyword_pattern),
            )
        )
    # 不过期或未过期
    conditions.append(
        or_(GrowthMemory.expires_at.is_(None), GrowthMemory.expires_at > datetime.now(UTC))
    )

    if conditions:
        stmt = stmt.where(and_(*conditions))
        count_stmt = count_stmt.where(and_(*conditions))

    # 按置信度 + 最近访问排序
    stmt = stmt.order_by(
        GrowthMemory.confidence.desc(),
        GrowthMemory.last_accessed_at.desc().nullslast(),
        GrowthMemory.created_at.desc(),
    )
    stmt = stmt.limit(limit).offset(offset)

    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0

    list_result = await session.execute(stmt)
    items = list(list_result.scalars().all())

    # 更新访问计数
    for item in items:
        item.access_count += 1
        item.last_accessed_at = datetime.now(UTC)

    return items, total


async def get_memories_for_agent_context(
    session: AsyncSession,
    *,
    agent_id: str,
    task_context: str | None = None,
    limit: int = 10,
) -> list[GrowthMemory]:
    """为 Agent 运行获取相关记忆（注入上下文用）。

    优先返回：
    1. 高置信度的成功模式和失败教训
    2. 与任务上下文相关的记忆（关键词匹配）
    3. 最近访问的记忆
    """
    # 先获取高置信度记忆
    items, _ = await search_memories(
        session,
        agent_id=agent_id,
        min_confidence=CONFIDENCE_AUTO_INJECT,
        limit=limit * 2,  # 多取一些再过滤
    )

    # 如果有关键词，优先排序相关记忆
    if task_context:
        keywords = [w for w in task_context.lower().split() if len(w) > 2]
        if keywords:
            def relevance_score(m: GrowthMemory) -> float:
                score = m.confidence
                text = (m.title + " " + (m.summary or "") + " " + m.content).lower()
                for kw in keywords:
                    if kw in text:
                        score += 0.2
                return score
            items.sort(key=relevance_score, reverse=True)

    return items[:limit]


def format_memories_for_prompt(memories: list[GrowthMemory]) -> str:
    """将记忆列表格式化为可注入 Agent 提示词的文本。"""
    if not memories:
        return "[成长记忆] 暂无相关历史经验。"

    lines = ["[成长记忆 - 历史经验参考]"]
    for i, m in enumerate(memories, 1):
        lines.append(f"\n{i}. [{m.memory_type}] {m.title} (置信度: {m.confidence:.2f})")
        if m.summary:
            lines.append(f"   摘要: {m.summary}")
        else:
            lines.append(f"   内容: {m.content[:200]}...")
    lines.append("\n[成长记忆结束]")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 置信度管理
# --------------------------------------------------------------------------- #

async def update_confidence(
    session: AsyncSession,
    memory_id: int,
    *,
    delta: float | None = None,
    absolute: float | None = None,
) -> GrowthMemory | None:
    """更新记忆置信度。

    Args:
        delta: 相对调整（+0.1 / -0.1）
        absolute: 绝对设置（0-1）
    """
    memory = await get_memory(session, memory_id)
    if not memory:
        return None

    if absolute is not None:
        memory.confidence = max(0.0, min(1.0, absolute))
    elif delta is not None:
        memory.confidence = max(0.0, min(1.0, memory.confidence + delta))

    # 置信度变化可能影响状态
    if memory.confidence < CONFIDENCE_PENDING_REVIEW and memory.status == "active":
        memory.status = "pending_review"
    elif memory.confidence >= CONFIDENCE_PENDING_REVIEW and memory.status == "pending_review":
        memory.status = "active"

    await session.flush()
    return memory


async def mark_useful(session: AsyncSession, memory_id: int) -> GrowthMemory | None:
    """标记记忆为有用（提升置信度）。"""
    memory = await get_memory(session, memory_id)
    if not memory:
        return None
    memory.useful_count += 1
    # 每被标记有用3次，置信度+0.05
    if memory.useful_count % 3 == 0:
        memory.confidence = min(1.0, memory.confidence + 0.05)
    await session.flush()
    return memory


# --------------------------------------------------------------------------- #
# 统计
# --------------------------------------------------------------------------- #

async def get_memory_stats(
    session: AsyncSession,
    *,
    agent_id: str | None = None,
    workspace_id: UUID | None = None,
) -> dict[str, Any]:
    """获取记忆统计。"""
    stmt = select(GrowthMemory)
    conditions = []
    if workspace_id:
        conditions.append(GrowthMemory.workspace_id == workspace_id)
    if agent_id:
        conditions.append(GrowthMemory.agent_id == agent_id)
    if conditions:
        stmt = stmt.where(and_(*conditions))

    result = await session.execute(stmt)
    memories = list(result.scalars().all())

    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    total_confidence = 0.0
    total_access = 0

    for m in memories:
        by_type[m.memory_type] = by_type.get(m.memory_type, 0) + 1
        by_status[m.status] = by_status.get(m.status, 0) + 1
        total_confidence += m.confidence
        total_access += m.access_count

    return {
        "total": len(memories),
        "avg_confidence": round(total_confidence / len(memories), 3) if memories else 0,
        "total_accesses": total_access,
        "by_type": by_type,
        "by_status": by_status,
        "pending_review": by_status.get("pending_review", 0),
    }
