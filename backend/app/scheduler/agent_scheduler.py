"""Agent 任务定时调度器 — 每天定时自动执行所有 Agent 每日任务。

功能：
1. 每天固定时间（默认 08:00）自动触发所有 Agent 每日任务
2. 任务自动分发给对应 Agent 执行
3. 生成的建议自动写入审批队列（agent_suggestions 表）
4. 记录执行日志和成本
5. 支持手动触发和配置执行时间

与 AGENTS.md 保持一致：
- Agent 是「提议者」不是「执行者」，高风险操作必须进入审批队列
- 全链路可审计，每次 Agent 运行的输入、输出、成本必须落库
- 成本护栏：每 Agent 设月度成本预算，超限自动告警并降级
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, time, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.logging import setup_logging
from app.tasks.agent_dispatcher import (
    AGENT_DESCRIPTIONS,
    get_agent_status,
    run_all_agents_daily,
)

logger = logging.getLogger(__name__)

# 默认执行时间（每天 08:00 UTC+8 = 00:00 UTC）
DEFAULT_EXECUTION_HOUR = 0  # UTC 时间，对应北京时间 08:00
DEFAULT_EXECUTION_MINUTE = 0

# 执行间隔检查（秒）
SCHEDULER_TICK_INTERVAL = 60  # 每分钟检查一次


class AgentScheduler:
    """Agent 任务定时调度器。

    职责：
    1. 每天固定时间触发所有 Agent 每日任务
    2. 管理执行状态和日志
    3. 支持手动触发
    4. 防止重复执行
    """

    def __init__(
        self,
        session_factory: Any = async_session_factory,
        execution_hour: int = DEFAULT_EXECUTION_HOUR,
        execution_minute: int = DEFAULT_EXECUTION_MINUTE,
    ) -> None:
        self.session_factory = session_factory
        self.execution_hour = execution_hour
        self.execution_minute = execution_minute
        self._running = False
        self._last_execution_date: str | None = None
        self._execution_lock = asyncio.Lock()

    async def start(self) -> None:
        """启动调度器，进入定时循环。"""
        self._running = True
        logger.info(
            "Agent 调度器启动: 每天 %02d:%02d UTC 执行所有 Agent 任务",
            self.execution_hour, self.execution_minute,
        )

        # 打印 Agent 状态
        status = get_agent_status()
        logger.info(
            "已注册 Agent: %d/%d (待实现: %d)",
            status["registered_agents"],
            status["total_agents"],
            status["pending_agents"],
        )
        for agent in status["agents"]:
            logger.info(
                "  - %s: %s [%s]",
                agent["agent_id"],
                agent["description"],
                agent["status"],
            )

        while self._running:
            try:
                await self._check_and_execute()
            except Exception as e:
                logger.exception("调度器执行异常: %s", e)
            await asyncio.sleep(SCHEDULER_TICK_INTERVAL)

    async def stop(self) -> None:
        """停止调度器。"""
        self._running = False
        logger.info("Agent 调度器停止")

    async def _check_and_execute(self) -> None:
        """检查是否到达执行时间，如果是则执行所有 Agent 任务。"""
        now = datetime.now(UTC)
        today_str = now.strftime("%Y-%m-%d")

        # 检查是否已经执行过今天的任务
        if self._last_execution_date == today_str:
            return

        # 检查是否到达执行时间
        if now.hour != self.execution_hour or now.minute < self.execution_minute:
            return

        # 到达执行时间，执行所有 Agent 任务
        logger.info("=" * 70)
        logger.info("到达每日执行时间，开始执行所有 Agent 任务")
        logger.info("=" * 70)

        await self.execute_all_agents()

        # 记录今天已执行
        self._last_execution_date = today_str

    async def execute_all_agents(self) -> dict[str, Any]:
        """手动触发所有 Agent 每日任务执行。

        Returns:
            执行结果汇总
        """
        async with self._execution_lock:
            async with self.session_factory() as session:
                result = await run_all_agents_daily(session)

            # 记录执行日志
            logger.info(
                "Agent 任务执行完成: 成功%d/失败%d, 总建议%d条, 耗时%.1fs",
                result.get("success_count", 0),
                result.get("failed_count", 0),
                result.get("total_suggestions_created", 0),
                result.get("duration_seconds", 0),
            )

            return result

    async def execute_single_agent(self, agent_id: str) -> dict[str, Any]:
        """手动触发单个 Agent 每日任务执行。

        Args:
            agent_id: Agent ID

        Returns:
            执行结果
        """
        from app.tasks.agent_dispatcher import AGENT_TASK_REGISTRY

        task_func = AGENT_TASK_REGISTRY.get(agent_id)
        if not task_func:
            return {
                "status": "agent_not_found",
                "agent_id": agent_id,
                "message": f"Agent {agent_id} 未注册或未实现",
            }

        logger.info("手动触发 Agent %s 任务执行", agent_id)

        async with self.session_factory() as session:
            try:
                result = await task_func(session)
                result["status"] = "success"
                logger.info(
                    "Agent %s 执行成功: 建议%d条, 耗时%.1fs",
                    agent_id,
                    result.get("suggestions_created", 0),
                    result.get("duration_seconds", 0),
                )
                return result
            except Exception as e:
                logger.exception("Agent %s 执行失败: %s", agent_id, e)
                return {
                    "status": "failed",
                    "agent_id": agent_id,
                    "error": str(e),
                }


def main() -> None:
    """调度器入口点：``python -m app.scheduler.agent_scheduler``。"""
    setup_logging()
    logger.info("启动 Agent 任务定时调度器...")

    scheduler = AgentScheduler()

    async def _run() -> None:
        await scheduler.start()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在停止调度器...")
        asyncio.run(scheduler.stop())
        logger.info("调度器已停止")


if __name__ == "__main__":
    main()
