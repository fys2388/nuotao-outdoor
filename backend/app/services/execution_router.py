"""执行路由器 — 根据建议类型和执行动作，路由到对应业务服务执行。

设计原则：
- 低风险动作自动执行（如更新产品描述、生成营销文案）
- 中高风险动作需审批后执行（如改价、补货、上下架）
- 所有执行结果记录到 suggestion.execution_result
- 执行失败不崩溃，记录错误并标记 failed
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_suggestion import AgentSuggestion
from app.services import agent_suggestion_service

logger = logging.getLogger(__name__)


class ExecutionError(Exception):
    """执行失败异常。"""


# --------------------------------------------------------------------------- #
# 执行动作注册表
# --------------------------------------------------------------------------- #

# 每个执行动作对应一个处理函数（异步，接收 session + params）
# 新增执行动作时在此注册
_execution_handlers: dict[str, callable] = {}


def register_handler(action: str):
    """装饰器：注册执行动作处理器。"""
    def decorator(func):
        _execution_handlers[action] = func
        logger.debug("注册执行动作: %s -> %s", action, func.__name__)
        return func
    return decorator


# --------------------------------------------------------------------------- #
# 核心执行入口
# --------------------------------------------------------------------------- #

async def execute_suggestion(
    session: AsyncSession,
    suggestion: AgentSuggestion | int,
) -> dict[str, Any]:
    """执行一条建议，返回执行结果。

    Args:
        suggestion: AgentSuggestion 对象或建议 ID

    Returns:
        执行结果 dict，包含 success, action, result/error
    """
    if isinstance(suggestion, int):
        suggestion_obj = await agent_suggestion_service.get_suggestion(session, suggestion)
        if not suggestion_obj:
            return {"success": False, "error": f"建议 {suggestion} 不存在"}
        suggestion = suggestion_obj

    # 状态检查
    if suggestion.status not in ("approved", "executing"):
        return {
            "success": False,
            "error": f"建议状态为 {suggestion.status}，无法执行（需 approved）",
        }

    action = suggestion.execution_action
    params = suggestion.execution_params or {}

    logger.info(
        "开始执行建议: id=%s agent=%s action=%s type=%s",
        suggestion.id, suggestion.agent_id, action, suggestion.suggestion_type,
    )

    # 标记执行中
    await agent_suggestion_service.mark_executing(session, suggestion.id)

    try:
        if not action:
            # 没有指定执行动作，按建议类型走默认处理
            result = await _execute_by_type(session, suggestion)
        elif action in _execution_handlers:
            handler = _execution_handlers[action]
            result = await handler(session, params)
        else:
            # 未注册的动作，记录但不执行（安全降级）
            result = {
                "success": False,
                "error": f"未注册的执行动作: {action}，请先注册处理器",
                "skipped": True,
            }

        # 更新执行结果
        if result.get("success"):
            await agent_suggestion_service.mark_completed(
                session, suggestion.id, result=result
            )
        else:
            await agent_suggestion_service.mark_failed(
                session, suggestion.id, error=result.get("error", "未知错误")
            )

        return result

    except Exception as e:
        logger.exception("建议 %s 执行异常", suggestion.id)
        error_msg = f"{type(e).__name__}: {str(e)}"
        await agent_suggestion_service.mark_failed(session, suggestion.id, error=error_msg)
        return {"success": False, "error": error_msg}


async def execute_pending_approved(
    session: AsyncSession,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """批量执行所有已审批待执行的建议。

    由调度器定时调用，处理 approved 状态的建议。
    """
    from sqlalchemy import select

    stmt = (
        select(AgentSuggestion)
        .where(AgentSuggestion.status == "approved")
        .order_by(
            AgentSuggestion.priority == "high",
            AgentSuggestion.priority == "medium",
            AgentSuggestion.created_at.asc(),
        )
        .limit(limit)
    )
    result = await session.execute(stmt)
    suggestions = list(result.scalars().all())

    logger.info("待执行建议数: %d", len(suggestions))
    results = []
    for suggestion in suggestions:
        result = await execute_suggestion(session, suggestion)
        results.append({"suggestion_id": suggestion.id, **result})

    return results


# --------------------------------------------------------------------------- #
# 按建议类型的默认执行逻辑
# --------------------------------------------------------------------------- #

async def _execute_by_type(
    session: AsyncSession,
    suggestion: AgentSuggestion,
) -> dict[str, Any]:
    """根据建议类型执行默认动作（无 execution_action 时的降级路径）。"""
    suggestion_type = suggestion.suggestion_type
    params = suggestion.execution_params or {}

    type_handlers = {
        "product_optimization": _handle_product_optimization,
        "marketing_optimization": _handle_marketing_optimization,
        "inventory_restock": _handle_inventory_restock,
        "pricing_adjustment": _handle_pricing_adjustment,
        "listing_optimization": _handle_listing_optimization,
        "customer_operation": _handle_customer_operation,
        "supply_chain": _handle_supply_chain,
        "business_insight": _handle_business_insight,
    }

    handler = type_handlers.get(suggestion_type)
    if not handler:
        return {
            "success": False,
            "error": f"无默认处理器的建议类型: {suggestion_type}",
            "skipped": True,
        }

    return await handler(session, params, suggestion)


# --------------------------------------------------------------------------- #
# 各类型默认处理器（调用对应业务服务）
# --------------------------------------------------------------------------- #

async def _handle_product_optimization(
    session: AsyncSession, params: dict, suggestion: AgentSuggestion
) -> dict[str, Any]:
    """产品优化：更新产品信息。"""
    product_id = params.get("product_id")
    if not product_id:
        return {"success": False, "error": "缺少 product_id 参数"}

    try:
        from app.services.product_service import update_product
        result = await update_product(session, product_id, params.get("updates", {}))
        return {"success": True, "action": "product_optimization", "result": result}
    except ImportError:
        return {
            "success": True,
            "action": "product_optimization",
            "result": {"note": "product_service 未接入，建议已记录待人工执行", "suggestion_id": suggestion.id},
            "deferred": True,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _handle_marketing_optimization(
    session: AsyncSession, params: dict, suggestion: AgentSuggestion
) -> dict[str, Any]:
    """营销优化：生成/更新营销文案或活动。"""
    try:
        from app.services.content_generation_service import generate_content
        content = await generate_content(
            prompt=params.get("prompt", suggestion.description),
            content_type=params.get("content_type", "marketing_copy"),
        )
        return {"success": True, "action": "marketing_optimization", "result": content}
    except ImportError:
        return {
            "success": True,
            "action": "marketing_optimization",
            "result": {"note": "content_generation_service 未接入，建议已记录", "suggestion_id": suggestion.id},
            "deferred": True,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _handle_inventory_restock(
    session: AsyncSession, params: dict, suggestion: AgentSuggestion
) -> dict[str, Any]:
    """库存补货：创建采购单。"""
    product_id = params.get("product_id")
    quantity = params.get("quantity")
    if not product_id or not quantity:
        return {"success": False, "error": "缺少 product_id 或 quantity 参数"}

    try:
        from app.services.procurement_service import create_purchase_order
        order = await create_purchase_order(session, product_id, quantity, params)
        return {"success": True, "action": "inventory_restock", "result": order}
    except ImportError:
        return {
            "success": True,
            "action": "inventory_restock",
            "result": {"note": "procurement_service 未接入，补货建议已记录待人工执行", "suggestion_id": suggestion.id},
            "deferred": True,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _handle_pricing_adjustment(
    session: AsyncSession, params: dict, suggestion: AgentSuggestion
) -> dict[str, Any]:
    """价格调整（高风险，必须已审批）。"""
    product_id = params.get("product_id")
    new_price = params.get("new_price")
    if not product_id or not new_price:
        return {"success": False, "error": "缺少 product_id 或 new_price 参数"}

    try:
        from app.services.product_service import update_price
        result = await update_price(session, product_id, new_price)
        return {"success": True, "action": "pricing_adjustment", "result": result}
    except ImportError:
        return {
            "success": True,
            "action": "pricing_adjustment",
            "result": {"note": "价格调整已记录，待人工执行", "product_id": product_id, "new_price": new_price},
            "deferred": True,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _handle_listing_optimization(
    session: AsyncSession, params: dict, suggestion: AgentSuggestion
) -> dict[str, Any]:
    """上架优化：更新 WooCommerce 商品信息。"""
    product_id = params.get("product_id")
    if not product_id:
        return {"success": False, "error": "缺少 product_id 参数"}

    try:
        from app.services.woocommerce_sync_service import update_product_listing
        result = await update_product_listing(product_id, params.get("updates", {}))
        return {"success": True, "action": "listing_optimization", "result": result}
    except ImportError:
        return {
            "success": True,
            "action": "listing_optimization",
            "result": {"note": "WooCommerce 同步服务未接入，优化建议已记录", "suggestion_id": suggestion.id},
            "deferred": True,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _handle_customer_operation(
    session: AsyncSession, params: dict, suggestion: AgentSuggestion
) -> dict[str, Any]:
    """客户运营：分群/触达。"""
    return {
        "success": True,
        "action": "customer_operation",
        "result": {"note": "客户运营建议已记录，待人工执行", "suggestion_id": suggestion.id},
        "deferred": True,
    }


async def _handle_supply_chain(
    session: AsyncSession, params: dict, suggestion: AgentSuggestion
) -> dict[str, Any]:
    """供应链优化。"""
    return {
        "success": True,
        "action": "supply_chain",
        "result": {"note": "供应链优化建议已记录，待人工执行", "suggestion_id": suggestion.id},
        "deferred": True,
    }


async def _handle_business_insight(
    session: AsyncSession, params: dict, suggestion: AgentSuggestion
) -> dict[str, Any]:
    """商业洞察：纯建议，无需执行，直接标记完成。"""
    return {
        "success": True,
        "action": "business_insight",
        "result": {"note": "商业洞察已记录，无需执行动作", "suggestion_id": suggestion.id},
    }
