"""飞书回调端点 — 接收用户在飞书卡片上的按钮点击，自动审批建议。

端点: POST /api/v1/feishu/card-callback

飞书配置:
1. 飞书自建应用后台 → 事件订阅 → 请求地址填写此端点 URL
2. 开启「卡片动作回调」事件（card.action.trigger）
3. 首次配置时飞书会发送 URL 验证挑战，此端点自动响应
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory, get_db
from app.services import agent_suggestion_service
from app.services.execution_router import execute_suggestion
from app.services.feishu_approval_service import send_approval_result_notification

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feishu", tags=["飞书集成"])


async def _execute_suggestion_async(suggestion_id: int) -> None:
    """异步执行单条建议（批准后立即执行，不阻塞回调响应）。"""
    try:
        async with async_session_factory() as session:
            result = await execute_suggestion(session, suggestion_id)
            await session.commit()
            logger.info("建议 %s 即时执行完成: %s", suggestion_id, result)
    except Exception as e:
        logger.exception("建议 %s 即时执行失败: %s", suggestion_id, e)


@router.post("/card-callback")
async def feishu_card_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """接收飞书卡片动作回调（用户点击批准/拒绝按钮）。"""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # 1. 飞书 URL 验证挑战（首次配置回调地址时）
    if body.get("type") == "url_verification":
        challenge = body.get("challenge", "")
        logger.info("飞书 URL 验证挑战: %s", challenge[:20])
        return {"challenge": challenge}

    # 2. 卡片动作回调
    header = body.get("header", {})
    event = body.get("event", {})
    event_type = header.get("event_type", "")

    if event_type != "card.action.trigger":
        logger.info("忽略非卡片动作事件: %s", event_type)
        return {"code": 0, "msg": "ignored"}

    # 解析按钮值
    action_data = event.get("action", {}).get("value", {})
    action = action_data.get("action", "")
    suggestion_id = action_data.get("suggestion_id")
    operator = event.get("operator", {}).get("name", "飞书用户")

    logger.info(
        "飞书卡片回调: suggestion_id=%s action=%s operator=%s",
        suggestion_id, action, operator,
    )

    if not suggestion_id or action not in ("approve", "reject", "view"):
        return {"code": 1, "msg": "invalid action or suggestion_id"}

    # 查看详情（不改变状态）
    if action == "view":
        suggestion = await agent_suggestion_service.get_suggestion(db, int(suggestion_id))
        if not suggestion:
            return {"code": 1, "msg": "suggestion not found"}
        return {
            "code": 0,
            "data": {
                "id": suggestion.id,
                "title": suggestion.title,
                "description": suggestion.description,
                "status": suggestion.status,
                "agent_id": suggestion.agent_id,
                "suggestion_type": suggestion.suggestion_type,
                "risk_level": suggestion.risk_level,
            },
        }

    # 批准或拒绝
    try:
        # 幂等性检查：先获取建议当前状态，避免重复处理
        existing = await agent_suggestion_service.get_suggestion(db, int(suggestion_id))
        if not existing:
            return {"code": 1, "msg": "suggestion not found"}

        if action == "approve":
            # 如果已经批准过，直接返回，不重复处理
            if existing.status in ("approved", "executing", "executed", "execution_failed"):
                logger.info("建议 %s 已处于 %s 状态，跳过重复批准", suggestion_id, existing.status)
                return {
                    "code": 0,
                    "msg": "already_approved",
                    "data": {"suggestion_id": suggestion_id, "status": existing.status},
                }
            result = await agent_suggestion_service.approve_suggestion(
                db, int(suggestion_id), approved_by=operator
            )
            # 推送审批结果通知
            send_approval_result_notification(
                suggestion_id=int(suggestion_id),
                title=result.title if hasattr(result, "title") else f"建议 #{suggestion_id}",
                action="approve",
                operator=operator,
            )
            logger.info("建议 %s 已通过飞书审批，立即触发执行", suggestion_id)
            # 批准后立即异步执行（不阻塞回调响应）
            asyncio.create_task(_execute_suggestion_async(int(suggestion_id)))
        else:  # reject
            # 如果已经拒绝过，直接返回
            if existing.status == "rejected":
                logger.info("建议 %s 已拒绝，跳过重复处理", suggestion_id)
                return {
                    "code": 0,
                    "msg": "already_rejected",
                    "data": {"suggestion_id": suggestion_id, "status": existing.status},
                }
            result = await agent_suggestion_service.reject_suggestion(
                db, int(suggestion_id), rejected_by=operator, reason="飞书卡片拒绝"
            )
            send_approval_result_notification(
                suggestion_id=int(suggestion_id),
                title=result.title if hasattr(result, "title") else f"建议 #{suggestion_id}",
                action="reject",
                operator=operator,
            )
            logger.info("建议 %s 已通过飞书拒绝", suggestion_id)

        return {
            "code": 0,
            "msg": "ok",
            "data": {"suggestion_id": suggestion_id, "action": action},
        }
    except Exception as e:
        logger.exception("飞书回调处理失败: suggestion_id=%s", suggestion_id)
        return {"code": 1, "msg": str(e)}


@router.get("/approval-test")
async def approval_test():
    """测试端点：发送一张测试审批卡片到飞书。"""
    from app.services.feishu_approval_service import send_approval_card

    result = send_approval_card(
        suggestion_id=99999,
        title="测试审批卡片",
        description="这是一张测试卡片，用于验证飞书审批流程是否正常工作。点击批准或拒绝按钮测试回调。",
        agent_name="Test Agent",
        suggestion_type="business_insight",
        risk_level="low",
        execution_params={"test_param": "test_value", "foo": "bar"},
    )
    return result


@router.get("/trigger-product-test")
async def trigger_product_test(db: AsyncSession = Depends(get_db)):
    """测试端点：手动创建一条真实测试建议，验证完整流程（创建→飞书推送→审批→执行）。"""
    from app.services import agent_suggestion_service

    try:
        # 直接创建一条真实的选品建议（不依赖产品数据）
        suggestion = await agent_suggestion_service.create_suggestion(
            db,
            agent_id="product_analyst",
            suggestion_type="product_optimization",
            title="【测试】户外露营灯选品建议：高流明可充电款",
            description=(
                "基于户外品类趋势分析，建议新增高流明可充电露营灯SKU。"
                "目标售价 $29.99，预计毛利率 45%，月销预期 500+ 件。"
                "建议立即启动1688选品和样品采购流程。"
            ),
            execution_params={
                "category": "camping_lights",
                "target_price": 29.99,
                "expected_margin": 0.45,
                "expected_monthly_sales": 500,
                "action": "start_sourcing",
            },
            execution_action="start_product_sourcing",
            expected_impact="新增SKU，月营收预期 +$15000",
            priority="high",
            risk_level="low",
        )
        await db.commit()
        return {
            "success": True,
            "message": "测试建议已创建，飞书审批卡片已推送",
            "suggestion_id": suggestion.id,
            "title": suggestion.title,
            "status": suggestion.status,
        }
    except Exception as e:
        logger.exception("测试建议创建失败")
        return {"success": False, "error": str(e)}
