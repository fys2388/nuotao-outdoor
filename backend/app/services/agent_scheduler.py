"""Agent 调度器 — 替代独立 Cron shell 脚本，通过 agent_runtime 统一调度。

设计：
- 轻量级定时调度器，使用 asyncio 事件循环
- 支持 cron 表达式和固定间隔两种调度方式
- 所有 Agent 任务通过 agent_runtime 执行，结果入库可审计
- 失败自动重试 + 飞书告警
- 可通过 API 动态增删调度任务（后续扩展）

当前内置3个每日任务（替代服务器上的3个Cron脚本）：
- 06:00 产品分析师每日分析
- 07:00 营销经理每日分析
- 08:00 供应链经理每日分析
- 09:00 执行已审批建议（批量执行）
- 10:00 反馈学习处理（生成学习摘要）
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Coroutine

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.redis import create_redis_client
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.services import agent_suggestion_service, execution_router, feedback_loop

logger = logging.getLogger(__name__)


def _get_schedule_time(env_var: str, default_hour: int, default_minute: int = 0) -> tuple[int, int]:
    """从环境变量读取调度时间，格式 HH:MM，失败则使用默认值。"""
    val = os.getenv(env_var, "")
    if val and ":" in val:
        try:
            h, m = val.split(":")
            return int(h), int(m)
        except (ValueError, TypeError):
            pass
    return default_hour, default_minute


# 调度任务时间配置（可通过环境变量覆盖）
SCHEDULE_PRODUCT_HOUR, SCHEDULE_PRODUCT_MINUTE = _get_schedule_time("SCHEDULE_PRODUCT_HOUR", 6, 0)
SCHEDULE_MARKETING_HOUR, SCHEDULE_MARKETING_MINUTE = _get_schedule_time("SCHEDULE_MARKETING_HOUR", 7, 0)
SCHEDULE_SUPPLY_CHAIN_HOUR, SCHEDULE_SUPPLY_CHAIN_MINUTE = _get_schedule_time("SCHEDULE_SUPPLY_CHAIN_HOUR", 8, 0)
SCHEDULE_EXECUTION_HOUR, SCHEDULE_EXECUTION_MINUTE = _get_schedule_time("SCHEDULE_EXECUTION_HOUR", 9, 0)
SCHEDULE_FEEDBACK_HOUR, SCHEDULE_FEEDBACK_MINUTE = _get_schedule_time("SCHEDULE_FEEDBACK_HOUR", 10, 0)

# 调度任务注册表: name -> (cron_expr, func, description)
SCHEDULED_TASKS: dict[str, dict[str, Any]] = {}

# Agent 间协作规则：当源 Agent 完成任务后，自动触发目标 Agent
# 格式：{ "源任务名": { "target": "目标任务名", "condition": "触发条件描述", "delay_seconds": 延迟秒数 } }
COLLABORATION_RULES: dict[str, dict[str, Any]] = {
    "daily_product_analyst": {
        "target": "daily_marketing_manager",
        "condition": "产品分析师生成选品/优化建议后，自动触发营销经理生成推广文案",
        "delay_seconds": 5,
    },
    "daily_supply_chain_manager": {
        "target": "daily_product_analyst",
        "condition": "供应链经理生成库存预警/补货建议后，自动触发产品分析师更新产品状态",
        "delay_seconds": 5,
    },
    "daily_marketing_manager": {
        "target": "feedback_learning",
        "condition": "营销经理生成活动优化建议后，自动触发反馈学习汇总效果",
        "delay_seconds": 10,
    },
}


def register_scheduled_task(
    name: str,
    *,
    hour: int | None = None,
    minute: int = 0,
    interval_minutes: int | None = None,
    description: str = "",
):
    """装饰器：注册定时任务。

    支持两种模式：
    - 每日定时：指定 hour 和 minute，每天运行一次
    - 间隔调度：指定 interval_minutes，每隔 N 分钟运行一次（24小时不停）
    """
    def decorator(func: Callable[[AsyncSession], Coroutine[Any, Any, dict[str, Any]]]):
        SCHEDULED_TASKS[name] = {
            "hour": hour,
            "minute": minute,
            "interval_minutes": interval_minutes,
            "func": func,
            "description": description,
            "last_run": None,
            "last_result": None,
            "last_error": None,
            "run_count": 0,
        }
        if interval_minutes:
            logger.info("注册间隔任务: %s @ 每%d分钟 - %s", name, interval_minutes, description)
        else:
            logger.info("注册定时任务: %s @ %02d:%02d - %s", name, hour or 0, minute, description)
        return func
    return decorator


# --------------------------------------------------------------------------- #
# 内置每日任务
# --------------------------------------------------------------------------- #

@register_scheduled_task(
    "daily_product_analyst",
    interval_minutes=30,
    description="产品分析师分析：选品评分、竞品监控、利润模型（每30分钟）",
)
async def daily_product_analyst(session: AsyncSession) -> dict[str, Any]:
    """每日产品分析师任务。"""
    from app.tasks.daily_agents import run_product_analyst_daily
    return await run_product_analyst_daily(session)


@register_scheduled_task(
    "daily_marketing_manager",
    interval_minutes=30,
    description="营销经理分析：活动ROAS、文案优化、SEO建议（每30分钟）",
)
async def daily_marketing_manager(session: AsyncSession) -> dict[str, Any]:
    """每日营销经理任务。"""
    from app.tasks.daily_agents import run_marketing_manager_daily
    return await run_marketing_manager_daily(session)


@register_scheduled_task(
    "daily_supply_chain_manager",
    interval_minutes=30,
    description="供应链经理分析：库存预警、补货建议、物流跟踪（每30分钟）",
)
async def daily_supply_chain_manager(session: AsyncSession) -> dict[str, Any]:
    """每日供应链经理任务。"""
    from app.tasks.daily_agents import run_supply_chain_daily
    return await run_supply_chain_daily(session)


@register_scheduled_task(
    "execute_pending_suggestions",
    interval_minutes=15,
    description="批量执行所有已审批待执行的建议（每15分钟）",
)
async def execute_pending_suggestions_task(session: AsyncSession) -> dict[str, Any]:
    """执行已审批建议。"""
    results = await execution_router.execute_pending_approved(session, limit=20)
    await session.commit()
    return {"executed": len(results), "results": results}


@register_scheduled_task(
    "feedback_learning",
    interval_minutes=60,
    description="处理可学习建议，生成Agent学习摘要（每60分钟）",
)
async def feedback_learning_task(session: AsyncSession) -> dict[str, Any]:
    """反馈学习处理。"""
    result = await feedback_loop.process_learnable_suggestions(session, limit=100)
    await session.commit()
    return result


@register_scheduled_task(
    "business_alerts",
    interval_minutes=360,
    description="业务指标预警评估：毛利下滑/退款率上升/断货风险/收入下滑（每6小时）",
)
async def business_alerts_task(session: AsyncSession) -> dict[str, Any]:
    """业务预警自动评估。"""
    from app.services import business_alert_service

    alerts = await business_alert_service.evaluate_business_alerts(
        session,
        workspace_id=DEFAULT_WORKSPACE_ID,
    )
    await session.commit()
    return {
        "new_alerts": len(alerts),
        "active_alerts": len(business_alert_service.get_active_alerts()),
        "alerts": [
            {"type": a.alert_type, "severity": a.severity, "title": a.title}
            for a in alerts
        ],
    }


def _parse_last_run(raw: str) -> datetime:
    """Parse a persisted last_run into an aware UTC datetime.

    _check_and_run subtracts this value from datetime.now(UTC), so a naive
    datetime raises "can't subtract offset-naive and offset-aware datetimes"
    and crash-loops the whole scheduler. Values without an explicit UTC offset
    are assumed to already be UTC and normalized; anything with an offset is
    converted to UTC so the subtraction is always safe.
    """
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


# --------------------------------------------------------------------------- #
# 调度器核心
# --------------------------------------------------------------------------- #

class AgentScheduler:
    """Agent 定时调度器。

    使用方式：
        scheduler = AgentScheduler()
        await scheduler.start()  # 阻塞运行
        # 或
        asyncio.create_task(scheduler.run())
    """

    def __init__(self, check_interval: int = 30):
        """
        Args:
            check_interval: 检查间隔（秒），默认30秒检查一次是否有任务到点
        """
        self.check_interval = check_interval
        self._running = False
        self._task: asyncio.Task | None = None
        self._state_key_prefix = "nuotao:scheduler:task:"

    def _state_key(self, name: str) -> str:
        """任务状态在 Redis 中的键（进程重启后 last_run 不丢失）。"""
        return f"{self._state_key_prefix}{name}"

    async def _restore_state(self) -> int:
        """从 Redis 恢复各任务的 last_run，消除重启后的首轮全量重跑。

        调度器由 systemd 以 ``Restart=always`` 托管，此前 ``last_run`` 只存在
        进程内存里；任何重启（发布、OOM、维护）都会让所有间隔任务在首轮全部
        触发，把重复建议灌入审批队列。恢复失败不影响调度本身，只降级为
        无状态启动（等价于原先行为）。
        """
        restored = 0
        try:
            r = create_redis_client()
            try:
                for name, task in SCHEDULED_TASKS.items():
                    # create_redis_client() returns a redis.asyncio client, so
                    # .get()/.set() are coroutines. Without await, `raw` is the
                    # coroutine object itself (never None), json.loads() raises
                    # TypeError, and every task logged "调度状态解析失败" while
                    # restoring 0/6 - the state never reached Redis.
                    raw = await r.get(self._state_key(name))
                    if raw is None:
                        continue
                    try:
                        payload = json.loads(raw)
                        last_run = payload.get("last_run")
                        if last_run:
                            task["last_run"] = _parse_last_run(last_run)
                            task["run_count"] = int(payload.get("run_count", 0))
                            restored += 1
                    except (ValueError, TypeError):
                        logger.warning("调度状态解析失败，忽略: %s", name)
            finally:
                await r.aclose()
        except Exception:
            logger.exception("调度状态恢复失败，降级为无状态启动")
        logger.info("调度状态恢复完成: %d/%d 个任务", restored, len(SCHEDULED_TASKS))
        return restored

    async def _save_last_run(self, name: str, task: dict[str, Any]) -> None:
        """把 last_run 持久化到 Redis（best-effort，失败不阻塞任务）。"""
        try:
            r = create_redis_client()
            try:
                await r.set(
                    self._state_key(name),
                    json.dumps(
                        {"last_run": task["last_run"].isoformat(), "run_count": task.get("run_count", 0)}
                    ),
                    ex=60 * 60 * 24 * 7,  # 7 天，足以跨越任何发布窗口
                )
            finally:
                await r.aclose()
        except Exception:
            logger.exception("调度状态持久化失败: %s", name)

    async def start(self):
        """启动调度器（阻塞）。"""
        self._running = True
        await self._restore_state()
        logger.info("Agent调度器启动，检查间隔: %ds，已注册任务: %d", self.check_interval, len(SCHEDULED_TASKS))
        for name, task in SCHEDULED_TASKS.items():
            # Interval tasks have hour=None, so %02d would raise TypeError
            # inside the logging formatter (a per-startup traceback that
            # buries real errors).
            if task["hour"] is not None:
                schedule = f"{task['hour']:02d}:{task['minute']:02d}"
            else:
                schedule = f"每{task['interval_minutes']}分钟"
            logger.info("  - %s @ %s: %s", name, schedule, task["description"])

        try:
            while self._running:
                await self._check_and_run()
                await asyncio.sleep(self.check_interval)
        except asyncio.CancelledError:
            logger.info("调度器被取消")
        finally:
            self._running = False
            logger.info("调度器已停止")

    def run_in_background(self) -> asyncio.Task:
        """在后台运行调度器，返回 Task 对象。"""
        self._task = asyncio.create_task(self.start(), name="agent-scheduler")
        return self._task

    def stop(self):
        """停止调度器。"""
        self._running = False
        if self._task:
            self._task.cancel()

    async def _check_and_run(self):
        """检查是否有任务到点，到点则执行。"""
        now = datetime.now(UTC)
        current_hour = now.hour
        current_minute = now.minute

        for name, task in SCHEDULED_TASKS.items():
            interval = task.get("interval_minutes")

            if interval:
                # 间隔调度模式：每隔 N 分钟运行一次（24小时不停）
                last_run = task.get("last_run")
                if last_run:
                    elapsed = (now - last_run).total_seconds() / 60
                    if elapsed < interval:
                        continue
                # 首次运行或间隔已到，执行任务
                logger.info("间隔任务触发: %s (每%d分钟)", name, interval)
                await self._run_task(name, task)
            else:
                # 每日定时模式：小时和分钟匹配
                if task["hour"] != current_hour or task["minute"] != current_minute:
                    continue

                # 检查今天是否已经运行过（避免重复执行）
                last_run = task.get("last_run")
                if last_run and last_run.date() == now.date():
                    continue

                # 执行任务
                logger.info("定时任务触发: %s", name)
                await self._run_task(name, task)

    async def _run_task(self, name: str, task: dict[str, Any]):
        """执行单个定时任务。"""
        task["last_run"] = datetime.now(UTC)
        task["run_count"] = task.get("run_count", 0) + 1
        await self._save_last_run(name, task)

        try:
            async with async_session_factory() as session:
                result = await task["func"](session)
            task["last_result"] = result
            task["last_error"] = None
            logger.info("定时任务完成: %s, 结果: %s", name, _summarize_result(result))
        except Exception as e:
            task["last_error"] = str(e)
            logger.exception("定时任务失败: %s", name)
            # TODO: 飞书告警
            try:
                await _send_alert(name, str(e))
            except Exception:
                logger.exception("发送告警失败")

        # Agent 间协作：任务完成后检查是否需要触发相关 Agent
        if name in COLLABORATION_RULES:
            rule = COLLABORATION_RULES[name]
            target_name = rule["target"]
            if target_name in SCHEDULED_TASKS:
                delay = rule.get("delay_seconds", 5)
                logger.info(
                    "🤝 Agent协作触发: %s 完成 -> %s 秒后触发 %s (%s)",
                    name, delay, target_name, rule["condition"]
                )
                # 延迟触发协作任务（不阻塞当前流程）
                asyncio.create_task(self._trigger_collaboration_task(target_name, delay))

    async def _trigger_collaboration_task(self, target_name: str, delay_seconds: int):
        """延迟触发协作任务。"""
        try:
            await asyncio.sleep(delay_seconds)
            target_task = SCHEDULED_TASKS.get(target_name)
            if target_task:
                logger.info("🤝 协作任务开始执行: %s", target_name)
                # 直接执行目标任务（不经过调度检查，立即执行）
                try:
                    async with async_session_factory() as session:
                        result = await target_task["func"](session)
                    target_task["last_run"] = datetime.now(UTC)
                    target_task["run_count"] = target_task.get("run_count", 0) + 1
                    await self._save_last_run(target_name, target_task)
                    target_task["last_result"] = result
                    target_task["last_error"] = None
                    logger.info("🤝 协作任务完成: %s, 结果: %s", target_name, _summarize_result(result))
                except Exception as e:
                    target_task["last_error"] = str(e)
                    logger.exception("🤝 协作任务失败: %s", target_name)
        except Exception as e:
            logger.exception("🤝 协作触发异常: %s", e)

    def get_status(self) -> dict[str, Any]:
        """获取调度器状态（所有任务的运行状态）。"""
        return {
            "running": self._running,
            "check_interval": self.check_interval,
            "tasks": {
                name: {
                    "hour": task["hour"],
                    "minute": task["minute"],
                    "interval_minutes": task.get("interval_minutes"),
                    "schedule": f"每{task['interval_minutes']}分钟" if task.get("interval_minutes") else f"每日{task['hour'] or 0:02d}:{task['minute']:02d}",
                    "description": task["description"],
                    "last_run": task["last_run"].isoformat() if task.get("last_run") else None,
                    "last_error": task.get("last_error"),
                    "run_count": task.get("run_count", 0),
                    "collaboration_trigger": COLLABORATION_RULES.get(name, {}).get("target"),
                }
                for name, task in SCHEDULED_TASKS.items()
            },
            "collaboration_rules": {
                name: {
                    "target": rule["target"],
                    "condition": rule["condition"],
                    "delay_seconds": rule.get("delay_seconds", 5),
                }
                for name, rule in COLLABORATION_RULES.items()
            },
        }


# --------------------------------------------------------------------------- #
# 辅助
# --------------------------------------------------------------------------- #

def _summarize_result(result: dict[str, Any]) -> str:
    """精简结果摘要用于日志。"""
    if not result:
        return "empty"
    keys = list(result.keys())[:3]
    return f"{{{', '.join(f'{k}={result[k]}' for k in keys)}}}"


async def _send_alert(task_name: str, error: str):
    """发送飞书告警（简化版，实际应调用飞书webhook）。"""
    # TODO: 接入飞书告警服务
    logger.warning("【告警】定时任务 %s 失败: %s", task_name, error[:200])


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #

async def main():
    """调度器入口（可直接运行: python -m app.services.agent_scheduler）。"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    scheduler = AgentScheduler()

    # 优雅退出
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, scheduler.stop)

    await scheduler.start()


if __name__ == "__main__":
    asyncio.run(main())
