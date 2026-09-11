"""执行路由器 — 根据建议类型和执行动作，路由到对应业务服务执行。

设计原则：
- 所有外部服务调用使用动态导入（importlib + getattr），函数不存在时自动降级
- 低风险动作自动执行（如更新产品描述、生成营销文案）
- 中高风险动作需审批后执行（如改价、补货、上下架）
- 所有执行结果记录到 suggestion.execution_result
- 执行失败不崩溃，记录错误并标记 failed
"""

from __future__ import annotations

import importlib
import inspect
import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_suggestion import AgentSuggestion
from app.services import agent_suggestion_service

logger = logging.getLogger(__name__)


class ExecutionError(Exception):
    """执行失败异常。"""


async def _safe_call(module_path: str, func_name: str, *args, **kwargs) -> tuple[bool, Any]:
    """安全调用外部服务函数（支持 async 函数自动 await）。

    Returns:
        (success, result_or_error)
    """
    try:
        mod = importlib.import_module(module_path)
        func = getattr(mod, func_name, None)
        if func is None or not callable(func):
            return False, f"函数 {module_path}.{func_name} 不存在"
        result = func(*args, **kwargs)
        if inspect.iscoroutine(result):
            result = await result
        return True, result
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)}"


# --------------------------------------------------------------------------- #
# 执行动作注册表
# --------------------------------------------------------------------------- #

_execution_handlers: dict[str, callable] = {}

# Action 别名映射：旧 action 名称 -> 已注册的处理器名称
# 用于兼容 daily_agents.py 中使用的旧 action 名称
ACTION_ALIASES: dict[str, str] = {
    "restock_inventory": "create_purchase_order",       # 库存补货 -> 创建采购单
    "optimize_listing": "update_product_listing",         # 上架优化 -> 更新商品上架信息
    "investigate_revenue_gap": "generate_marketing_content",  # 收入差距分析 -> 生成营销内容
    "optimize_campaign": "generate_marketing_content",    # 优化营销活动 -> 生成营销内容
    "start_sourcing": "start_product_sourcing",           # 开始选品 -> 开始产品选品
}




# --------------------------------------------------------------------------- #
# 执行失败自动升级映射
# --------------------------------------------------------------------------- #
ESCALATION_AGENT_MAP: dict[str, dict[str, str]] = {
    "product_manager": {
        "product_optimization": "supply_chain_manager",
        "pricing_adjustment": "business_analyst",
        "listing_optimization": "marketing_manager",
        "inventory_restock": "supply_chain_manager",
        "data_quality": "business_analyst",
        "other": "business_analyst",
    },
    "marketing_manager": {
        "marketing_optimization": "product_manager",
        "campaign_optimization": "business_analyst",
        "content_generation": "product_manager",
        "data_quality": "business_analyst",
        "other": "business_analyst",
    },
    "supply_chain_manager": {
        "inventory_restock": "product_manager",
        "procurement": "business_analyst",
        "supplier_management": "business_analyst",
        "data_quality": "business_analyst",
        "other": "business_analyst",
    },
    "customer_manager": {
        "customer_operation": "marketing_manager",
        "refund": "business_analyst",
        "complaint": "business_analyst",
        "data_quality": "business_analyst",
        "other": "business_analyst",
    },
    "business_analyst": {
        "business_insight": "product_manager",
        "data_quality": "product_manager",
        "other": "product_manager",
    },
}

def register_handler(action: str):
    """装饰器：注册执行动作处理器。"""
    def decorator(func):
        _execution_handlers[action] = func
        return func
    return decorator


# --------------------------------------------------------------------------- #
# 核心执行入口
# --------------------------------------------------------------------------- #



async def escalate_failed_suggestion(
    session: AsyncSession,
    suggestion: AgentSuggestion,
    error: str,
) -> AgentSuggestion | None:
    """执行失败后自动升级：生成一条新的升级建议分配给相关 Agent。"""
    if suggestion.title and "[执行失败升级]" in suggestion.title:
        logger.info("建议 %s 已是升级建议，跳过二次升级", suggestion.id)
        return None

    agent_map = ESCALATION_AGENT_MAP.get(suggestion.agent_id, {})
    target_agent = agent_map.get(suggestion.suggestion_type, agent_map.get("other", "business_analyst"))

    escalated_title = f"[执行失败升级] {suggestion.title}"
    escalated_reason = (
        f"原建议 ID={suggestion.id} 执行失败，错误: {error[:200]}\n"
        f"原 Agent: {suggestion.agent_id}，建议类型: {suggestion.suggestion_type}\n"
        f"请 {target_agent} 介入处理或升级为人工审批。"
    )

    try:
        from app.services.agent_suggestion_service import create_suggestion
        new_suggestion = await create_suggestion(
            session,
            agent_id=target_agent,
            suggestion_type="escalation",
            title=escalated_title,
            description=escalated_reason,
            risk_level="medium",
            priority="high",
            execution_action="manual_review",
            execution_params={"original_suggestion_id": suggestion.id, "original_error": error[:500]},
            workspace_id=suggestion.workspace_id,
        )
        logger.info("建议 %s 执行失败已自动升级为建议 %s (分配给 %s)",
                    suggestion.id, new_suggestion.id if new_suggestion else "?", target_agent)
        return new_suggestion
    except Exception as e:
        logger.error("自动升级建议失败: %s", e, exc_info=True)
        return None

async def execute_suggestion(
    session: AsyncSession,
    suggestion: AgentSuggestion | int,
) -> dict[str, Any]:
    """执行一条建议，返回执行结果。"""
    if isinstance(suggestion, int):
        suggestion_obj = await agent_suggestion_service.get_suggestion(session, suggestion)
        if not suggestion_obj:
            return {"success": False, "error": f"建议 {suggestion} 不存在"}
        suggestion = suggestion_obj

    if suggestion.status not in ("approved", "executing"):
        return {
            "success": False,
            "error": f"建议状态为 {suggestion.status}，无法执行（需 approved）",
        }

    action = suggestion.execution_action
    params = suggestion.execution_params or {}

    # Action 别名解析：如果 action 不在已注册处理器中，尝试通过别名映射解析
    if action and action not in _execution_handlers and action in ACTION_ALIASES:
        logger.info("Action 别名映射: %s -> %s", action, ACTION_ALIASES[action])
        action = ACTION_ALIASES[action]

    # 如果 execution_action 为空，但 execution_params 中有 action 字段，也尝试解析
    if not action and isinstance(params, dict) and params.get("action"):
        param_action = params["action"]
        if param_action in _execution_handlers:
            action = param_action
        elif param_action in ACTION_ALIASES:
            logger.info("Params action 别名映射: %s -> %s", param_action, ACTION_ALIASES[param_action])
            action = ACTION_ALIASES[param_action]

    logger.info(
        "开始执行建议: id=%s agent=%s action=%s type=%s",
        suggestion.id, suggestion.agent_id, action, suggestion.suggestion_type,
    )

    await agent_suggestion_service.mark_executing(session, suggestion.id)

    try:
        if not action:
            result = await _execute_by_type(session, suggestion)
        elif action in _execution_handlers:
            handler = _execution_handlers[action]
            result = await handler(session, params)
        else:
            # 回退：按 suggestion_type 查找旧处理器（兼容未迁移到 @register_handler 的动作）
            logger.warning("动作 %s 未注册到 _execution_handlers，回退到按类型执行", action)
            result = await _execute_by_type(session, suggestion)

        if result.get("success"):
            await agent_suggestion_service.mark_completed(session, suggestion.id, result=result)
        else:
            err_msg = result.get("error", "未知错误")
            await agent_suggestion_service.mark_failed(session, suggestion.id, error=err_msg)
            try:
                await escalate_failed_suggestion(session, suggestion, err_msg)
            except Exception as esc_e:
                logger.warning("自动升级失败（不影响主流程）: %s", esc_e)
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
    """批量执行所有已审批待执行的建议。"""
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
    """根据建议类型执行默认动作。"""
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
# 各类型默认处理器（动态调用外部服务，不存在时降级）
# --------------------------------------------------------------------------- #

async def _handle_product_optimization(
    session: AsyncSession, params: dict, suggestion: AgentSuggestion
) -> dict[str, Any]:
    """产品优化：更新产品信息或开始选品。"""
    # 如果是选品动作，转发到 start_product_sourcing 处理器
    param_action = params.get("action")
    if param_action in ("start_sourcing", "start_product_sourcing"):
        handler = _execution_handlers.get("start_product_sourcing")
        if handler:
            return await handler(session, params)
        return {"success": False, "error": "start_product_sourcing 处理器未注册"}

    product_id = params.get("product_id")
    if not product_id:
        return {"success": False, "error": "缺少 product_id 参数，且未指定选品动作"}

    ok, result = await _safe_call("app.services.product_service", "update_product",
                             session, product_id, params.get("updates", {}))
    if ok:
        return {"success": True, "action": "product_optimization", "result": result}

    return {
        "success": False,
        "action": "product_optimization",
        "error": f"产品优化执行失败: {result}",
    }


async def _handle_marketing_optimization(
    session: AsyncSession, params: dict, suggestion: AgentSuggestion
) -> dict[str, Any]:
    """营销优化：生成/更新营销文案或活动。"""
    ok, result = await _safe_call("app.services.content_generation_service", "generate_content",
                             prompt=params.get("prompt", suggestion.description),
                             content_type=params.get("content_type", "marketing_copy"))
    if ok:
        return {"success": True, "action": "marketing_optimization", "result": result}

    return {
        "success": False,
        "action": "marketing_optimization",
        "error": f"营销优化执行失败: {result}",
    }


async def _handle_inventory_restock(
    session: AsyncSession, params: dict, suggestion: AgentSuggestion
) -> dict[str, Any]:
    """库存补货：创建采购单。"""
    product_id = params.get("product_id")
    quantity = params.get("quantity")
    if not product_id or not quantity:
        return {"success": False, "error": "缺少 product_id 或 quantity 参数"}

    ok, result = await _safe_call("app.services.procurement_service", "create_purchase_order",
                             session, product_id, quantity, params)
    if ok:
        return {"success": True, "action": "inventory_restock", "result": result}

    return {
        "success": False,
        "action": "inventory_restock",
        "error": f"采购单创建失败: {result}",
    }


async def _handle_pricing_adjustment(
    session: AsyncSession, params: dict, suggestion: AgentSuggestion
) -> dict[str, Any]:
    """价格调整（高风险，必须已审批）。"""
    product_id = params.get("product_id")
    new_price = params.get("new_price")
    if not product_id or not new_price:
        return {"success": False, "error": "缺少 product_id 或 new_price 参数"}

    ok, result = await _safe_call("app.services.product_service", "update_price",
                             session, product_id, new_price)
    if ok:
        return {"success": True, "action": "pricing_adjustment", "result": result}

    return {
        "success": False,
        "action": "pricing_adjustment",
        "error": f"定价调整执行失败: {result}",
    }


async def _handle_listing_optimization(
    session: AsyncSession, params: dict, suggestion: AgentSuggestion
) -> dict[str, Any]:
    """上架优化：更新 WooCommerce 商品信息。"""
    product_id = params.get("product_id")
    if not product_id:
        return {"success": False, "error": "缺少 product_id 参数"}

    ok, result = await _safe_call("app.services.woocommerce_sync_service", "update_product_listing",
                             product_id, params.get("updates", {}))
    if ok:
        return {"success": True, "action": "listing_optimization", "result": result}

    return {
        "success": False,
        "action": "listing_optimization",
        "error": f"上架优化执行失败: {result}",
    }


async def _handle_customer_operation(
    session: AsyncSession, params: dict, suggestion: AgentSuggestion
) -> dict[str, Any]:
    """客户运营：分群/触达。"""
    return {
        "success": False,
        "action": "customer_operation",
        "error": "客户运营功能待接入，建议已记录待人工执行",
    }


async def _handle_supply_chain(
    session: AsyncSession, params: dict, suggestion: AgentSuggestion
) -> dict[str, Any]:
    """供应链优化。"""
    return {
        "success": False,
        "action": "supply_chain",
        "error": "供应链优化功能待接入，建议已记录待人工执行",
    }


async def _handle_business_insight(
    session: AsyncSession, params: dict, suggestion: AgentSuggestion
) -> dict[str, Any]:
    """商业洞察：纯建议，无需执行，直接标记完成。"""
    return {
        "success": False,
        "action": "business_insight",
        "error": "商业洞察功能待接入，建议已记录待人工执行",
    }



# --------------------------------------------------------------------------- #
# 具体执行动作处理器（注册到 _execution_handlers）
# --------------------------------------------------------------------------- #

@register_handler("start_product_sourcing")
async def handle_start_product_sourcing(session: AsyncSession, params: dict) -> dict:
    """开始选品：创建选品任务，记录候选产品。"""
    from app.models.product import Product
    from sqlalchemy import select

    keywords = params.get("keywords", "")
    category = params.get("category", "")
    target_market = params.get("target_market", "US")
    budget = params.get("budget")

    # 查询现有产品中匹配的候选
    query = select(Product).where(Product.target_market == target_market)
    if category:
        query = query.where(Product.category == category)
    query = query.limit(10)

    result = await session.execute(query)
    candidates = list(result.scalars().all())

    return {
        "success": True,
        "action": "start_product_sourcing",
        "result": {
            "note": "选品任务已创建，候选产品已筛选",
            "keywords": keywords,
            "category": category,
            "target_market": target_market,
            "budget": budget,
            "candidate_count": len(candidates),
            "candidates": [{"id": str(p.id), "sku": p.sku, "name": p.name} for p in candidates],
            "next_step": "人工审核候选产品，确认后进入上架流程",
        },
    }


@register_handler("update_product_info")
async def handle_update_product_info(session: AsyncSession, params: dict) -> dict:
    """更新产品信息。"""
    from app.models.product import Product
    from sqlalchemy import select

    product_id = params.get("product_id")
    updates = params.get("updates", {})

    if not product_id:
        return {"success": False, "error": "缺少 product_id 参数"}

    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()

    if not product:
        return {"success": False, "error": f"产品 {product_id} 不存在"}

    # 更新允许的字段
    allowed_fields = ["name", "description", "category", "brand", "status", "tags", "attributes", "weight_kg", "dimensions"]
    updated_fields = []
    for field in allowed_fields:
        if field in updates:
            setattr(product, field, updates[field])
            updated_fields.append(field)

    await session.commit()

    return {
        "success": True,
        "action": "update_product_info",
        "result": {
            "note": "产品信息已更新",
            "product_id": product_id,
            "updated_fields": updated_fields,
        },
    }


@register_handler("generate_marketing_content")
async def handle_generate_marketing_content(session: AsyncSession, params: dict) -> dict:
    """生成营销内容。"""
    content_type = params.get("content_type", "marketing_copy")
    prompt = params.get("prompt", "")
    product_id = params.get("product_id")

    # 尝试调用内容生成服务，不存在则降级
    ok, result = await _safe_call(
        "app.services.content_generation_service", "generate_content",
        prompt=prompt, content_type=content_type,
    )

    if ok:
        return {"success": True, "action": "generate_marketing_content", "result": result}

    return {
        "success": False,
        "action": "generate_marketing_content",
        "error": f"生成营销内容执行失败: {result}",
    }


@register_handler("create_purchase_order")
async def handle_create_purchase_order(session: AsyncSession, params: dict) -> dict:
    """创建采购单。"""
    product_id = params.get("product_id")
    quantity = params.get("quantity")
    supplier_id = params.get("supplier_id")
    unit_cost = params.get("unit_cost")

    if not product_id or not quantity:
        return {"success": False, "error": "缺少 product_id 或 quantity 参数"}

    # 尝试调用采购服务，不存在则记录待人工执行
    ok, result = await _safe_call(
        "app.services.procurement_service", "create_purchase_order",
        session, product_id, quantity, params,
    )

    if ok:
        return {"success": True, "action": "create_purchase_order", "result": result}

    total_cost = float(unit_cost) * int(quantity) if unit_cost and quantity else None

    return {
        "success": False,
        "action": "create_purchase_order",
        "error": f"创建采购单执行失败: {result}",
    }


@register_handler("adjust_product_price")
async def handle_adjust_product_price(session: AsyncSession, params: dict) -> dict:
    """调整产品价格（高风险，必须已审批）。"""
    from app.models.product import Product
    from sqlalchemy import select

    product_id = params.get("product_id")
    new_price = params.get("new_price")
    reason = params.get("reason", "")

    if not product_id or not new_price:
        return {"success": False, "error": "缺少 product_id 或 new_price 参数"}

    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()

    if not product:
        return {"success": False, "error": f"产品 {product_id} 不存在"}

    # 记录价格变更到 meta
    old_price = product.meta.get("price") if product.meta else None
    product.meta = {
        **(product.meta or {}),
        "price": new_price,
        "price_history": [
            *(product.meta.get("price_history", []) if product.meta else []),
            {"old_price": old_price, "new_price": new_price, "reason": reason, "timestamp": __import__("datetime").datetime.now().isoformat()},
        ],
    }

    await session.commit()

    return {
        "success": False,
        "action": "adjust_product_price",
        "error": f"调整产品价格执行失败: {result}",
    }


@register_handler("update_product_listing")
async def handle_update_product_listing(session: AsyncSession, params: dict) -> dict:
    """更新 WooCommerce 商品上架信息。"""
    product_id = params.get("product_id")
    updates = params.get("updates", {})

    if not product_id:
        return {"success": False, "error": "缺少 product_id 参数"}

    # 尝试调用 WooCommerce 同步服务，不存在则降级
    ok, result = await _safe_call(
        "app.services.woocommerce_sync_service", "update_product_listing",
        product_id, updates,
    )

    if ok:
        return {"success": True, "action": "update_product_listing", "result": result}

    return {
        "success": False,
        "action": "update_product_listing",
        "error": f"更新商品上架执行失败: {result}",
    }


@register_handler("execute_customer_operation")
async def handle_execute_customer_operation(session: AsyncSession, params: dict) -> dict:
    """执行客户运营（分群/触达）。"""
    operation_type = params.get("operation_type", "segmentation")
    target_segment = params.get("target_segment", "")
    message = params.get("message", "")

    return {
        "success": False,
        "action": "execute_customer_operation",
        "error": "客户运营功能待接入，建议已记录待人工执行",
    }


@register_handler("optimize_supply_chain")
async def handle_optimize_supply_chain(session: AsyncSession, params: dict) -> dict:
    """优化供应链。"""
    optimization_type = params.get("optimization_type", "logistics")
    suggestions = params.get("suggestions", [])

    return {
        "success": False,
        "action": "optimize_supply_chain",
        "error": "供应链优化功能待接入，建议已记录待人工执行",
    }


# 导出已注册的处理器列表，便于调试
def get_registered_handlers() -> list[str]:
    """获取所有已注册的执行动作处理器。"""
    return list(_execution_handlers.keys())
