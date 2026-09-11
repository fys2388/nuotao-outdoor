"""成长记忆消费者 — Agent 运行时自动注入相关历史记忆。

P1-1 成长记忆模块的运行时接入层：
- 每次 Agent 运行前，按 agent_id + 任务上下文检索高置信度记忆
- 格式化为提示词文本，注入到 Agent context["growth_memory"]
- 低置信度记忆不自动注入（符合 AGENTS.md §3.3 防污染原则）
- 记忆检索失败时降级为无记忆运行，不阻塞 Agent

与 growth_memory_service 的关系：
- growth_memory_service 负责记忆的 CRUD / 检索 / 格式化（数据层）
- 本模块负责在 Agent 运行时消费记忆（运行时层）

设计原则（对齐 AGENTS.md）：
- 上下文最小化：单次运行最多注入 DEFAULT_MEMORY_LIMIT 条
- 降级链：记忆不可用 -> 无记忆运行（不阻塞）
- 全链路可审计：注入条数记录到日志
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import growth_memory_service

logger = logging.getLogger(__name__)

# 单次运行注入记忆上限（控制上下文长度，符合上下文最小化原则）
DEFAULT_MEMORY_LIMIT = 8

# 注入到 context 中的字段名
MEMORY_CONTEXT_KEY = "growth_memory"
MEMORY_COUNT_KEY = "growth_memory_count"


async def inject_growth_memory(
    session: AsyncSession,
    *,
    agent_id: str,
    context: dict[str, Any],
    task_context: str | None = None,
    limit: int = DEFAULT_MEMORY_LIMIT,
) -> dict[str, Any]:
    """将相关成长记忆注入到 Agent 上下文中。

    Args:
        session: 数据库会话
        agent_id: Agent 标识（如 'marketing_manager'）
        context: 待注入的 Agent 上下文（会被浅拷贝后返回，不修改原对象）
        task_context: 本次任务的上下文描述（用于关键词相关性排序，如 trigger 名）
        limit: 最大注入记忆条数

    Returns:
        注入了 growth_memory / growth_memory_count 字段的新 context dict。
        无论检索成功与否，这两个字段始终存在（失败时为降级提示文本）。
    """
    enriched = dict(context)  # 浅拷贝，不修改原对象

    try:
        memories = await growth_memory_service.get_memories_for_agent_context(
            session,
            agent_id=agent_id,
            task_context=task_context,
            limit=limit,
        )
        if memories:
            memory_text = growth_memory_service.format_memories_for_prompt(memories)
            enriched[MEMORY_CONTEXT_KEY] = memory_text
            enriched[MEMORY_COUNT_KEY] = len(memories)
            logger.info(
                "Agent %s 注入成长记忆 %d 条（task_context=%s）",
                agent_id, len(memories), task_context,
            )
        else:
            enriched[MEMORY_CONTEXT_KEY] = "[成长记忆] 暂无相关历史经验。"
            enriched[MEMORY_COUNT_KEY] = 0
    except Exception as exc:
        # 记忆注入失败不阻塞 Agent 运行（降级链：无记忆也能跑）
        logger.warning(
            "成长记忆注入失败（降级为无记忆运行）: agent=%s error=%s",
            agent_id, exc,
        )
        enriched[MEMORY_CONTEXT_KEY] = "[成长记忆] 记忆检索失败，本次无历史经验参考。"
        enriched[MEMORY_COUNT_KEY] = 0

    return enriched
