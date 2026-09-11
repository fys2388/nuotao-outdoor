"""Agent 任务自动分发器 — 根据任务类型自动路由到对应 Agent。

职责：
1. 接收任务请求（手动触发或定时调度）
2. 根据任务类型/领域自动路由到对应 Agent
3. 执行 Agent 任务，生成建议写入审批队列
4. 记录执行日志和成本
5. 支持批量执行所有 Agent 的每日任务

Agent 职责映射（与 AGENTS.md 保持一致）：
- product_analyst: 选品、定价、Listing优化、库存预警
- marketing_manager: 营销活动、文案、SEO、客户触达
- supply_chain_manager: 采购、库存、物流、供应商
- customer_manager: 客户服务、评价、退换货、客户分群
- business_analyst: 经营分析、财务、竞品、战略建议
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.tasks.daily_agents import (
    run_business_analyst_daily,
    run_customer_manager_daily,
    run_marketing_manager_daily,
    run_product_analyst_daily,
    run_supply_chain_daily,
)

logger = logging.getLogger(__name__)

# Agent ID 到执行函数的映射
AgentTaskFunc = Callable[[AsyncSession], dict[str, Any]]

AGENT_TASK_REGISTRY: dict[str, AgentTaskFunc] = {
    "product_analyst": run_product_analyst_daily,
    "marketing_manager": run_marketing_manager_daily,
    "supply_chain_manager": run_supply_chain_daily,
    "customer_manager": run_customer_manager_daily,
    "business_analyst": run_business_analyst_daily,
}

# Agent 职责描述（用于日志和报告）
AGENT_DESCRIPTIONS: dict[str, str] = {
    "product_analyst": "产品分析师 — 选品/定价/Listing优化/库存预警",
    "marketing_manager": "营销经理 — 活动/文案/SEO/客户触达",
    "supply_chain_manager": "供应链经理 — 采购/库存/物流/供应商",
    "customer_manager": "客户经理 — 客服/评价/退换货/客户分群",
    "business_analyst": "商业分析师 — 经营分析/财务/竞品/战略",
}

# 任务类型到 Agent 的路由映射
TASK_TYPE_TO_AGENT: dict[str, str] = {
    # 产品相关
    "product_selection": "product_analyst",
    "pricing": "product_analyst",
    "listing_optimization": "product_analyst",
    "inventory_restock": "product_analyst",
    "product_research": "product_analyst",
    # 营销相关
    "campaign_optimization": "marketing_manager",
    "copywriting": "marketing_manager",
    "seo_optimization": "marketing_manager",
    "customer_outreach": "marketing_manager",
    "social_media": "marketing_manager",
    # 供应链相关
    "purchase_order": "supply_chain_manager",
    "inventory_management": "supply_chain_manager",
    "logistics": "supply_chain_manager",
    "supplier_management": "supply_chain_manager",
    # 客户相关
    "customer_service": "customer_manager",
    "review_management": "customer_manager",
    "returns_refunds": "customer_manager",
    "customer_segmentation": "customer_manager",
    # 商业分析相关
    "business_analysis": "business_analyst",
    "financial_analysis": "business_analyst",
    "competitor_analysis": "business_analyst",
    "strategy": "business_analyst",
}


def route_task_to_agent(task_type: str) -> str | None:
    """根据任务类型路由到对应 Agent。

    Args:
        task_type: 任务类型标识符

    Returns:
        Agent ID，如果未匹配则返回 None
    """
    agent_id = TASK_TYPE_TO_AGENT.get(task_type)
    if agent_id:
        logger.info("任务 [%s] 路由到 Agent: %s", task_type, agent_id)
    else:
        logger.warning("任务类型 [%s] 未匹配到任何 Agent", task_type)
    return agent_id


async def dispatch_task(
    session: AsyncSession,
    task_type: str,
    task_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """分发单个任务到对应 Agent 执行。

    Args:
        session: 数据库会话
        task_type: 任务类型
        task_params: 任务参数

    Returns:
        执行结果字典
    """
    started_at = datetime.now(UTC)
    agent_id = route_task_to_agent(task_type)

    if not agent_id:
        return {
            "status": "no_agent_matched",
            "task_type": task_type,
            "message": f"任务类型 {task_type} 未匹配到任何 Agent",
            "duration_seconds": 0,
        }

    task_func = AGENT_TASK_REGISTRY.get(agent_id)
    if not task_func:
        return {
            "status": "agent_not_implemented",
            "agent_id": agent_id,
            "task_type": task_type,
            "message": f"Agent {agent_id} 尚未实现任务函数",
            "duration_seconds": 0,
        }

    logger.info("开始执行任务: type=%s, agent=%s", task_type, agent_id)

    try:
        result = await task_func(session)
        duration = (datetime.now(UTC) - started_at).total_seconds()
        result["status"] = "success"
        result["task_type"] = task_type
        result["dispatched_agent"] = agent_id
        result["duration_seconds"] = round(duration, 1)
        logger.info(
            "任务执行成功: type=%s, agent=%s, 耗时%.1fs, 建议%d条",
            task_type, agent_id, duration,
            result.get("suggestions_created", 0),
        )
        return result
    except Exception as e:
        duration = (datetime.now(UTC) - started_at).total_seconds()
        logger.exception("任务执行失败: type=%s, agent=%s, error=%s", task_type, agent_id, e)
        return {
            "status": "failed",
            "task_type": task_type,
            "dispatched_agent": agent_id,
            "error": str(e),
            "duration_seconds": round(duration, 1),
        }


async def run_all_agents_daily(session: AsyncSession) -> dict[str, Any]:
    """批量执行所有已注册 Agent 的每日任务。

    这是定时调度器的主要入口，每天定时执行一次。

    Returns:
        批量执行结果汇总
    """
    logger.info("=" * 60)
    logger.info("开始批量执行所有 Agent 每日任务")
    logger.info("=" * 60)

    started_at = datetime.now(UTC)
    results: dict[str, Any] = {}
    total_suggestions = 0
    success_count = 0
    failed_count = 0

    for agent_id, task_func in AGENT_TASK_REGISTRY.items():
        logger.info("-" * 40)
        logger.info("执行 Agent: %s (%s)", agent_id, AGENT_DESCRIPTIONS.get(agent_id, "未知"))

        try:
            result = await task_func(session)
            suggestions = result.get("suggestions_created", 0)
            total_suggestions += suggestions
            success_count += 1
            results[agent_id] = {
                "status": "success",
                "suggestions_created": suggestions,
                "duration_seconds": result.get("duration_seconds", 0),
            }
            logger.info(
                "Agent %s 执行成功: 建议%d条, 耗时%.1fs",
                agent_id, suggestions, result.get("duration_seconds", 0),
            )
        except Exception as e:
            failed_count += 1
            results[agent_id] = {
                "status": "failed",
                "error": str(e),
            }
            logger.exception("Agent %s 执行失败: %s", agent_id, e)

    duration = (datetime.now(UTC) - started_at).total_seconds()

    summary = {
        "status": "completed",
        "total_agents": len(AGENT_TASK_REGISTRY),
        "success_count": success_count,
        "failed_count": failed_count,
        "total_suggestions_created": total_suggestions,
        "duration_seconds": round(duration, 1),
        "agent_results": results,
        "executed_at": started_at.isoformat(),
    }

    logger.info("=" * 60)
    logger.info(
        "批量执行完成: 成功%d/失败%d, 总建议%d条, 总耗时%.1fs",
        success_count, failed_count, total_suggestions, duration,
    )
    logger.info("=" * 60)

    return summary


def get_agent_status() -> dict[str, Any]:
    """获取所有 Agent 的注册状态和职责。

    Returns:
        Agent 状态字典
    """
    agents = []
    for agent_id, description in AGENT_DESCRIPTIONS.items():
        is_registered = agent_id in AGENT_TASK_REGISTRY
        agents.append({
            "agent_id": agent_id,
            "description": description,
            "is_registered": is_registered,
            "status": "active" if is_registered else "pending_implementation",
        })

    return {
        "total_agents": len(AGENT_DESCRIPTIONS),
        "registered_agents": len(AGENT_TASK_REGISTRY),
        "pending_agents": len(AGENT_DESCRIPTIONS) - len(AGENT_TASK_REGISTRY),
        "agents": agents,
    }
