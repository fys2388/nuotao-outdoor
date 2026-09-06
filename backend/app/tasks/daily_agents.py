"""每日 Agent 任务实现 — 替代服务器上的3个独立 Cron shell 脚本。

每个任务：
1. 从数据库获取最新业务数据
2. 调用 LLM（通过 llm_gateway）生成分析和建议
3. 将建议写入 agent_suggestions 表（进入审批队列）
4. 生成报告摘要，可推送到飞书

与原 shell 脚本的区别：
- 原脚本：直连DB → 调DeepSeek API → 输出文本 → 飞书
- 新实现：通过 agent_runtime 调度 → 建议入库 → 审批→执行→反馈闭环
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import agent_suggestion_service

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 产品分析师每日任务
# --------------------------------------------------------------------------- #

async def run_product_analyst_daily(session: AsyncSession) -> dict[str, Any]:
    """产品分析师每日分析。

    分析内容：
    - 在售产品表现（销量/利润/转化率）
    - 竞品价格监控
    - 选品机会识别
    - 产品优化建议

    输出：建议写入 agent_suggestions 表
    """
    logger.info("=== 产品分析师每日分析开始 ===")
    started_at = datetime.now(UTC)

    suggestions_created = []

    # 1. 获取产品数据（简化版，实际应从 product_intelligence_service 获取）
    product_stats = await _get_product_stats(session)

    # 2. 生成选品建议（简化版，实际应调用 LLM）
    if product_stats.get("low_stock_products"):
        for product in product_stats["low_stock_products"]:
            suggestion = await agent_suggestion_service.create_suggestion(
                session,
                agent_id="product_analyst",
                suggestion_type="inventory_restock",
                title=f"库存预警: {product.get('name', '未知产品')} 库存不足",
                description=(
                    f"产品 {product.get('name')} 当前库存 {product.get('stock', 0)}，"
                    f"低于安全库存阈值。建议立即补货 {product.get('reorder_qty', 50)} 件。"
                ),
                execution_params={
                    "product_id": product.get("id"),
                    "quantity": product.get("reorder_qty", 50),
                    "current_stock": product.get("stock", 0),
                },
                execution_action="restock_inventory",
                expected_impact="避免断货，维持销售连续性",
                priority="high",
                risk_level="medium",
            )
            suggestions_created.append(suggestion.id)

    # 3. 生成产品优化建议（简化版）
    if product_stats.get("low_conversion_products"):
        for product in product_stats["low_conversion_products"]:
            suggestion = await agent_suggestion_service.create_suggestion(
                session,
                agent_id="product_analyst",
                suggestion_type="listing_optimization",
                title=f"转化率优化: {product.get('name')} 转化率偏低",
                description=(
                    f"产品 {product.get('name')} 最近7天转化率 {product.get('conversion_rate', 0):.2%}，"
                    f"低于品类平均水平。建议优化产品标题、主图和详情页。"
                ),
                execution_params={
                    "product_id": product.get("id"),
                    "current_conversion": product.get("conversion_rate"),
                    "optimization_areas": ["title", "main_image", "description"],
                },
                execution_action="optimize_listing",
                expected_impact="提升转化率 15-30%",
                priority="medium",
                risk_level="low",
            )
            suggestions_created.append(suggestion.id)

    await session.commit()

    duration = (datetime.now(UTC) - started_at).total_seconds()
    logger.info(
        "=== 产品分析师每日分析完成: 耗时%.1fs, 创建建议%d条 ===",
        duration, len(suggestions_created),
    )

    return {
        "agent": "product_analyst",
        "duration_seconds": round(duration, 1),
        "suggestions_created": len(suggestions_created),
        "suggestion_ids": suggestions_created,
        "product_stats_summary": {
            "total_products": product_stats.get("total_products", 0),
            "low_stock_count": len(product_stats.get("low_stock_products", [])),
            "low_conversion_count": len(product_stats.get("low_conversion_products", [])),
        },
    }


# --------------------------------------------------------------------------- #
# 营销经理每日任务
# --------------------------------------------------------------------------- #

async def run_marketing_manager_daily(session: AsyncSession) -> dict[str, Any]:
    """营销经理每日分析。

    分析内容：
    - 营销活动 ROAS 分析
    - 文案优化建议
    - SEO 关键词机会
    - 客户触达建议
    """
    logger.info("=== 营销经理每日分析开始 ===")
    started_at = datetime.now(UTC)

    suggestions_created = []

    # 获取营销数据（简化版）
    marketing_stats = await _get_marketing_stats(session)

    # 生成营销优化建议
    if marketing_stats.get("underperforming_campaigns"):
        for campaign in marketing_stats["underperforming_campaigns"]:
            suggestion = await agent_suggestion_service.create_suggestion(
                session,
                agent_id="marketing_manager",
                suggestion_type="marketing_optimization",
                title=f"活动优化: {campaign.get('name')} ROAS 低于目标",
                description=(
                    f"营销活动 {campaign.get('name')} 当前 ROAS {campaign.get('roas', 0):.2f}，"
                    f"低于目标 {campaign.get('target_roas', 3.0)}。建议优化受众定向和广告素材。"
                ),
                execution_params={
                    "campaign_id": campaign.get("id"),
                    "current_roas": campaign.get("roas"),
                    "target_roas": campaign.get("target_roas"),
                    "optimization_actions": ["adjust_audience", "refresh_creatives", "adjust_bid"],
                },
                execution_action="optimize_campaign",
                expected_impact="提升 ROAS 至目标水平",
                priority="high",
                risk_level="medium",
            )
            suggestions_created.append(suggestion.id)

    await session.commit()

    duration = (datetime.now(UTC) - started_at).total_seconds()
    logger.info(
        "=== 营销经理每日分析完成: 耗时%.1fs, 创建建议%d条 ===",
        duration, len(suggestions_created),
    )

    return {
        "agent": "marketing_manager",
        "duration_seconds": round(duration, 1),
        "suggestions_created": len(suggestions_created),
        "suggestion_ids": suggestions_created,
    }


# --------------------------------------------------------------------------- #
# 供应链经理每日任务
# --------------------------------------------------------------------------- #

async def run_supply_chain_daily(session: AsyncSession) -> dict[str, Any]:
    """供应链经理每日分析。

    分析内容：
    - 库存健康度
    - 采购订单跟踪
    - 物流时效分析
    - 供应商表现评估
    """
    logger.info("=== 供应链经理每日分析开始 ===")
    started_at = datetime.now(UTC)

    suggestions_created = []

    # 获取供应链数据（简化版）
    supply_stats = await _get_supply_chain_stats(session)

    # 生成补货建议
    if supply_stats.get("need_reorder_products"):
        for product in supply_stats["need_reorder_products"]:
            suggestion = await agent_suggestion_service.create_suggestion(
                session,
                agent_id="supply_chain_manager",
                suggestion_type="inventory_restock",
                title=f"补货建议: {product.get('name')} 需补货",
                description=(
                    f"产品 {product.get('name')} 库存 {product.get('stock', 0)}，"
                    f"预计 {product.get('days_to_stockout', 7)} 天后断货。"
                    f"建议向 {product.get('supplier', '默认供应商')} 采购 {product.get('reorder_qty', 100)} 件。"
                ),
                execution_params={
                    "product_id": product.get("id"),
                    "quantity": product.get("reorder_qty", 100),
                    "supplier": product.get("supplier"),
                    "estimated_delivery_days": product.get("delivery_days", 15),
                },
                execution_action="create_purchase_order",
                expected_impact=f"避免 {product.get('days_to_stockout', 7)} 天后断货",
                priority="high",
                risk_level="medium",
            )
            suggestions_created.append(suggestion.id)

    await session.commit()

    duration = (datetime.now(UTC) - started_at).total_seconds()
    logger.info(
        "=== 供应链经理每日分析完成: 耗时%.1fs, 创建建议%d条 ===",
        duration, len(suggestions_created),
    )

    return {
        "agent": "supply_chain_manager",
        "duration_seconds": round(duration, 1),
        "suggestions_created": len(suggestions_created),
        "suggestion_ids": suggestions_created,
    }


# --------------------------------------------------------------------------- #
# 数据获取辅助函数（简化版，实际应调用对应业务服务）
# --------------------------------------------------------------------------- #

async def _get_product_stats(session: AsyncSession) -> dict[str, Any]:
    """获取产品统计数据（简化版）。"""
    # 实际应从 product_intelligence_service / product_service 获取
    # 这里返回空结构，避免在没有数据时报错
    return {
        "total_products": 0,
        "low_stock_products": [],
        "low_conversion_products": [],
    }


async def _get_marketing_stats(session: AsyncSession) -> dict[str, Any]:
    """获取营销统计数据（简化版）。"""
    return {
        "active_campaigns": 0,
        "underperforming_campaigns": [],
        "total_spend": 0,
        "total_revenue": 0,
    }


async def _get_supply_chain_stats(session: AsyncSession) -> dict[str, Any]:
    """获取供应链统计数据（简化版）。"""
    return {
        "total_inventory_value": 0,
        "need_reorder_products": [],
        "pending_purchase_orders": 0,
        "supplier_count": 0,
    }
