"""
AI 产品经理选品建议服务
基于产品评分、成本模型、市场分析生成选品候选清单
支持审批流程（pending → approved/rejected）
"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_intelligence import (
    APPROVAL_STATES,
    DECISION_TYPES,
    ProductDecision,
    ProductScore,
)

logger = logging.getLogger(__name__)

# 默认工作空间 ID
DEFAULT_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000001")

# 选品建议阈值
SELECTION_THRESHOLDS = {
    "strong_buy": Decimal("80.0"),   # >= 80 分：强烈推荐
    "buy": Decimal("65.0"),           # >= 65 分：推荐
    "watch": Decimal("50.0"),         # >= 50 分：观察
    "reject": Decimal("50.0"),        # < 50 分：拒绝
}

# 推荐测试数量和天数
DEFAULT_TEST_QUANTITY = 50
DEFAULT_TEST_DAYS = 30


async def generate_selection_recommendations(
    session: AsyncSession,
    workspace_id: UUID | None = None,
    limit: int = 20,
    min_score: float = 50.0,
) -> dict[str, Any]:
    """
    生成选品建议候选清单

    基于产品评分排序，筛选出符合最低分数要求的产品，
    生成分级建议（强烈推荐/推荐/观察/拒绝）。

    Args:
        session: 数据库会话
        workspace_id: 工作空间 ID
        limit: 返回数量限制
        min_score: 最低分数要求

    Returns:
        选品建议候选清单
    """
    if workspace_id is None:
        workspace_id = DEFAULT_WORKSPACE_ID

    # 查询最新的产品评分
    # 注意：ProductScore 是 append-only 的，需要取每个产品的最新评分
    score_query = (
        select(ProductScore)
        .where(ProductScore.workspace_id == workspace_id)
        .order_by(desc(ProductScore.scored_at))
        .limit(100)
    )
    score_result = await session.execute(score_query)
    all_scores = score_result.scalars().all()

    # 取每个产品的最新评分
    latest_scores = {}
    for score in all_scores:
        if score.product_id not in latest_scores:
            latest_scores[score.product_id] = score

    # 筛选符合最低分数要求的产品
    filtered_scores = [
        s for s in latest_scores.values()
        if float(s.total) >= min_score
    ]

    # 按总分排序
    filtered_scores.sort(key=lambda s: float(s.total), reverse=True)

    # 限制返回数量
    filtered_scores = filtered_scores[:limit]

    # 查询产品信息
    product_ids = [s.product_id for s in filtered_scores]
    if product_ids:
        product_query = select(Product).where(Product.id.in_(product_ids))
        product_result = await session.execute(product_query)
        products = {p.id: p for p in product_result.scalars().all()}
    else:
        products = {}

    # 生成分级建议
    recommendations = []
    for score in filtered_scores:
        product = products.get(score.product_id)
        if not product:
            continue

        total_score = float(score.total)

        # 分级
        if Decimal(str(total_score)) >= SELECTION_THRESHOLDS["strong_buy"]:
            recommendation = "strong_buy"
            recommendation_label = "强烈推荐"
            action = "test"
        elif Decimal(str(total_score)) >= SELECTION_THRESHOLDS["buy"]:
            recommendation = "buy"
            recommendation_label = "推荐"
            action = "test"
        elif Decimal(str(total_score)) >= SELECTION_THRESHOLDS["watch"]:
            recommendation = "watch"
            recommendation_label = "观察"
            action = "hold"
        else:
            recommendation = "reject"
            recommendation_label = "拒绝"
            action = "reject"

        # 生成建议理由
        reasons = []
        if float(score.profit) >= 7:
            reasons.append("利润空间良好")
        if float(score.logistics) >= 7:
            reasons.append("物流可行性高")
        if float(score.demand) >= 7:
            reasons.append("市场需求旺盛")
        if float(score.competition) <= 5:
            reasons.append("竞争程度较低")
        if float(score.differentiation) >= 7:
            reasons.append("产品差异化明显")
        if float(score.compliance) >= 7:
            reasons.append("合规风险低")

        # 生成风险提示
        risks = []
        if float(score.profit) < 5:
            risks.append("利润空间不足")
        if float(score.logistics) < 5:
            risks.append("物流复杂度高")
        if float(score.demand) < 5:
            risks.append("市场需求不确定")
        if float(score.competition) > 7:
            risks.append("市场竞争激烈")
        if float(score.compliance) < 5:
            risks.append("合规风险较高")

        recommendations.append({
            "product_id": str(product.id),
            "product_name": product.name,
            "sku": product.sku,
            "category": product.category,
            "candidate_status": product.candidate_status,
            "score": {
                "total": float(score.total),
                "profit": float(score.profit),
                "logistics": float(score.logistics),
                "demand": float(score.demand),
                "competition": float(score.competition),
                "differentiation": float(score.differentiation),
                "compliance": float(score.compliance),
            },
            "recommendation": recommendation,
            "recommendation_label": recommendation_label,
            "suggested_action": action,
            "reasons": reasons,
            "risks": risks,
            "suggested_test_quantity": DEFAULT_TEST_QUANTITY if action == "test" else None,
            "suggested_test_days": DEFAULT_TEST_DAYS if action == "test" else None,
            "scored_at": score.scored_at.isoformat() if score.scored_at else None,
        })

    # 统计
    stats = {
        "total_scanned": len(latest_scores),
        "meeting_threshold": len(filtered_scores),
        "strong_buy": sum(1 for r in recommendations if r["recommendation"] == "strong_buy"),
        "buy": sum(1 for r in recommendations if r["recommendation"] == "buy"),
        "watch": sum(1 for r in recommendations if r["recommendation"] == "watch"),
        "reject": sum(1 for r in recommendations if r["recommendation"] == "reject"),
    }

    return {
        "recommendations": recommendations,
        "stats": stats,
        "thresholds": {k: float(v) for k, v in SELECTION_THRESHOLDS.items()},
        "generated_at": datetime.utcnow().isoformat(),
    }


async def create_selection_decision(
    session: AsyncSession,
    product_id: UUID,
    decision: str,
    score: float | None = None,
    confidence: float | None = None,
    reasons: list[str] | None = None,
    risks: list[str] | None = None,
    recommended_price: float | None = None,
    max_cac: float | None = None,
    test_quantity: int | None = None,
    test_days: int | None = None,
    workspace_id: UUID | None = None,
    trace_id: str | None = None,
) -> ProductDecision:
    """
    创建选品决策（进入审批队列）

    Args:
        session: 数据库会话
        product_id: 产品 ID
        decision: 决策类型（test/hold/reject）
        score: 产品评分
        confidence: 置信度（0-1）
        reasons: 决策理由
        risks: 风险提示
        recommended_price: 建议售价
        max_cac: 最大客户获取成本
        test_quantity: 测试数量
        test_days: 测试天数
        workspace_id: 工作空间 ID
        trace_id: 追踪 ID

    Returns:
        选品决策对象
    """
    if workspace_id is None:
        workspace_id = DEFAULT_WORKSPACE_ID

    # 验证决策类型
    if decision not in DECISION_TYPES:
        raise ValueError(f"Invalid decision type: {decision}. Must be one of {DECISION_TYPES}")

    # 创建决策记录
    product_decision = ProductDecision(
        workspace_id=workspace_id,
        product_id=product_id,
        decision=decision,
        score=Decimal(str(score)) if score is not None else None,
        confidence=Decimal(str(confidence)) if confidence is not None else None,
        reasons=reasons or [],
        risks=risks or [],
        recommended_price=Decimal(str(recommended_price)) if recommended_price is not None else None,
        max_cac=Decimal(str(max_cac)) if max_cac is not None else None,
        test_quantity=test_quantity,
        test_days=test_days,
        approval_status="pending",
        trace_id=trace_id,
    )
    session.add(product_decision)
    await session.flush()

    logger.info(
        "Selection decision created: product=%s, decision=%s, id=%s, trace=%s",
        product_id,
        decision,
        product_decision.id,
        trace_id,
    )

    return product_decision


async def approve_selection_decision(
    session: AsyncSession,
    decision_id: UUID,
    approved_by: str = "system",
    workspace_id: UUID | None = None,
) -> ProductDecision:
    """
    审批通过选品决策

    Args:
        session: 数据库会话
        decision_id: 决策 ID
        approved_by: 审批人
        workspace_id: 工作空间 ID

    Returns:
        更新后的选品决策对象
    """
    if workspace_id is None:
        workspace_id = DEFAULT_WORKSPACE_ID

    # 查询决策
    decision = await session.get(ProductDecision, decision_id)
    if not decision:
        raise ValueError(f"Decision not found: {decision_id}")

    if decision.approval_status != "pending":
        raise ValueError(f"Decision already processed: {decision.approval_status}")

    # 更新审批状态
    decision.approval_status = "approved"
    decision.approved_by = approved_by
    decision.approved_at = datetime.utcnow()

    # 如果决策是 test，更新产品候选状态为 testing
    if decision.decision == "test":
        product = await session.get(Product, decision.product_id)
        if product:
            product.candidate_status = "testing"

    await session.flush()

    logger.info(
        "Selection decision approved: id=%s, product=%s, by=%s",
        decision_id,
        decision.product_id,
        approved_by,
    )

    return decision


async def reject_selection_decision(
    session: AsyncSession,
    decision_id: UUID,
    rejected_by: str = "system",
    reject_reason: str | None = None,
    workspace_id: UUID | None = None,
) -> ProductDecision:
    """
    拒绝选品决策

    Args:
        session: 数据库会话
        decision_id: 决策 ID
        rejected_by: 拒绝人
        reject_reason: 拒绝原因
        workspace_id: 工作空间 ID

    Returns:
        更新后的选品决策对象
    """
    if workspace_id is None:
        workspace_id = DEFAULT_WORKSPACE_ID

    # 查询决策
    decision = await session.get(ProductDecision, decision_id)
    if not decision:
        raise ValueError(f"Decision not found: {decision_id}")

    if decision.approval_status != "pending":
        raise ValueError(f"Decision already processed: {decision.approval_status}")

    # 更新审批状态
    decision.approval_status = "rejected"
    decision.approved_by = rejected_by
    decision.approved_at = datetime.utcnow()

    # 如果有拒绝原因，添加到 risks 中
    if reject_reason:
        decision.risks = list(decision.risks or []) + [f"Rejected: {reject_reason}"]

    # 如果决策是 reject，更新产品候选状态为 rejected
    if decision.decision == "reject":
        product = await session.get(Product, decision.product_id)
        if product:
            product.candidate_status = "rejected"

    await session.flush()

    logger.info(
        "Selection decision rejected: id=%s, product=%s, by=%s, reason=%s",
        decision_id,
        decision.product_id,
        rejected_by,
        reject_reason,
    )

    return decision


async def get_selection_decisions(
    session: AsyncSession,
    approval_status: str | None = None,
    decision_type: str | None = None,
    workspace_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """
    获取选品决策列表

    Args:
        session: 数据库会话
        approval_status: 按审批状态筛选（pending/approved/rejected）
        decision_type: 按决策类型筛选（test/hold/reject）
        workspace_id: 工作空间 ID
        limit: 每页数量
        offset: 偏移量

    Returns:
        选品决策列表和分页信息
    """
    if workspace_id is None:
        workspace_id = DEFAULT_WORKSPACE_ID

    query = select(ProductDecision).where(ProductDecision.workspace_id == workspace_id)

    if approval_status:
        query = query.where(ProductDecision.approval_status == approval_status)
    if decision_type:
        query = query.where(ProductDecision.decision == decision_type)

    query = query.order_by(desc(ProductDecision.created_at)).limit(limit).offset(offset)

    result = await session.execute(query)
    decisions = result.scalars().all()

    # 统计总数
    count_query = select(ProductDecision).where(ProductDecision.workspace_id == workspace_id)
    if approval_status:
        count_query = count_query.where(ProductDecision.approval_status == approval_status)
    if decision_type:
        count_query = count_query.where(ProductDecision.decision == decision_type)
    count_result = await session.execute(count_query)
    total = len(count_result.scalars().all())

    return {
        "decisions": [
            {
                "id": str(d.id),
                "product_id": str(d.product_id),
                "decision": d.decision,
                "score": float(d.score) if d.score else None,
                "confidence": float(d.confidence) if d.confidence else None,
                "reasons": d.reasons,
                "risks": d.risks,
                "recommended_price": float(d.recommended_price) if d.recommended_price else None,
                "test_quantity": d.test_quantity,
                "test_days": d.test_days,
                "approval_status": d.approval_status,
                "approved_by": d.approved_by,
                "approved_at": d.approved_at.isoformat() if d.approved_at else None,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in decisions
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_selection_manager_status() -> dict[str, Any]:
    """获取选品管理系统状态"""
    return {
        "status": "running",
        "decision_types": list(DECISION_TYPES),
        "approval_states": list(APPROVAL_STATES),
        "selection_thresholds": {k: float(v) for k, v in SELECTION_THRESHOLDS.items()},
        "default_test_quantity": DEFAULT_TEST_QUANTITY,
        "default_test_days": DEFAULT_TEST_DAYS,
        "workflow": "AI generates recommendations → create decision (pending) → human approve/reject → update product status",
        "note": "AI Product Manager selection system is ready. Supports recommendation generation, decision creation, and human-in-the-loop approval workflow.",
    }
