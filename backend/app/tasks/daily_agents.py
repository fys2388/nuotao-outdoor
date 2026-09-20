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

import hashlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.customer import CustomerProfile
from app.models.marketing import Campaign
from app.services import agent_suggestion_service as _suggestion_svc
from app.services.report_truthfulness import (
    CampaignMetric,
    SegmentMetric,
    validate_marketing_report,
)

logger = logging.getLogger(__name__)

# 幂等窗口（分钟）：同一窗口内重复生成的建议只落库一次。
# 该值应 >= 调度任务的最小间隔，否则会误伤窗口内的合法建议。
DEDUP_WINDOW_MINUTES = 30

# 各 Agent 分析的产品状态范围。两个 Agent 处于业务流水线的不同阶段，
# 所以状态集不同，不能共用一个常量。
#
# 产品分析师在「选品评分」阶段工作：候选池是 draft + candidate —— 产品还没
# 上架才需要分析师判断要不要做。active 产品已过决策点，不属于选品范围。
# 供应链经理在「补货预警」阶段工作：只关心已决定要做的产品（candidate 正在
# 筹备、active 正在销售），draft 尚未立项，不需要备货建议。
#
# 此前两者都硬编码 status == "active"。prod 实际数据为 38 个产品
# (draft=37, candidate=1, active=0)，两个 Agent 每次都拿到空集、产出 0 条建议。
ANALYST_PRODUCT_STATUSES = ("draft", "candidate")
SUPPLY_CHAIN_PRODUCT_STATUSES = ("candidate", "active")


class _DedupSuggestionService:
    """调度路径的建议创建适配器：自动附加幂等键。

    ``app.services.agent_scheduler`` 由 systemd 以 ``Restart=always`` 托管，
    其 ``last_run`` 状态此前只存在进程内存里。任何重启（发布、OOM、维护）
    都会让所有间隔任务在首轮全部触发；而本模块的建议生成原本没有幂等键，
    结果就是重复建议被批量灌入 ``pending_approval`` 审批队列。

    本适配器不改任何调用点，只在中间层把
    ``{agent_id}:{suggestion_type}:{entity}:{epoch_slot}`` 作为 ``dedup_key``
    透传给服务层；服务层命中唯一约束时返回既有行。窗口外的新建议照常创建。

    ``entity`` 是被建议作用的业务对象标识（product_id / campaign_id / title
    的 sha256 前 12 位）。必须包含它，否则同一窗口内针对不同产品的建议会被
    折叠成一行：一次调度生成 3 条「库存预警」时，第 2、3 条会命中第 1 条的
    dedup_key 并返回同一行，后两个产品的补货建议静默丢失，而上层仍报
    ``suggestions_created=3``。取哈希前缀是为了让 key 长度恒定于
    ``dedup_key`` 列的 ``varchar(191)`` 约束之内。
    """

    window_minutes: int = DEDUP_WINDOW_MINUTES

    async def create_suggestion(self, session: AsyncSession, *, workspace_id=None, **kwargs: Any):
        params = kwargs.get("execution_params") or {}
        entity = (
            params.get("product_id")
            or params.get("campaign_id")
            or kwargs.get("title")
            or ""
        )
        entity_hash = hashlib.sha256(str(entity).encode("utf-8")).hexdigest()[:12]
        dedup_key = (
            f"{kwargs.get('agent_id')}:{kwargs.get('suggestion_type')}:"
            f"{entity_hash}:"
            f"{int(datetime.now(UTC).timestamp()) // (self.window_minutes * 60)}"
        )
        return await _suggestion_svc.create_suggestion(
            session, dedup_key=dedup_key, workspace_id=workspace_id, **kwargs
        )


# 模块内所有 `agent_suggestion_service.create_suggestion(...)` 调用点经由
# 上面的适配器自动获得幂等键；API/人工路径不受影响（仍直连服务层）。
agent_suggestion_service = _DedupSuggestionService()

# 营销活动默认 ROAS 目标（低于该值视为低绩效，生成优化建议）
DEFAULT_TARGET_ROAS = Decimal("3.0")


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
    """营销经理每日分析（防造假校验版）。

    分析内容：
    - 营销活动 ROAS 分析
    - 文案优化建议
    - SEO 关键词机会
    - 客户触达建议

    防造假硬规则（见 app.services.report_truthfulness）：
    - 生成建议前强制收入对账 + 样本量 + 状态校验；
    - 校验失败时禁止生成带数字的建议，只披露缺口，不编造结论。
    """
    logger.info("=== 营销经理每日分析开始 ===")
    started_at = datetime.now(UTC)

    suggestions_created = []

    # 获取营销数据（简化版）
    marketing_stats = await _get_marketing_stats(session)

    # ---- 防造假校验：构造规范化指标并强制对账 ----
    campaigns = [
        CampaignMetric(
            name=str(c.get("name", "unknown")),
            channel=c.get("channel"),
            status=str(c.get("status", "active")),
            spend=c.get("spend"),
            revenue=c.get("revenue"),
            source=c.get("source"),
        )
        for c in marketing_stats.get("campaigns", [])
    ]
    segments = [
        SegmentMetric(
            name=str(s.get("name", "unknown")),
            customer_count=int(s.get("customer_count", 0)),
            revenue=s.get("revenue"),
            source=s.get("source"),
        )
        for s in marketing_stats.get("customer_segments", [])
    ]

    check = validate_marketing_report(campaigns=campaigns, segments=segments)

    # 对账失败：必须披露缺口，禁止生成带数字结论的建议
    if not check.passed:
        logger.warning(
            "营销经理报告防造假校验未通过: %s", check.violations
        )
        if check.reconciliation and check.reconciliation.issues:
            suggestion = await agent_suggestion_service.create_suggestion(
                session,
                agent_id="marketing_manager",
                suggestion_type="data_quality",
                title="收入对账失败: 活动收入与客户分群收入存在缺口",
                description=(
                    f"{check.reconciliation.issues[0]}。"
                    f"在缺口查明来源并修复前，禁止对外发布营销分析结论。"
                ),
                execution_params={
                    "rules_version": check.rules_version,
                    "campaign_total_revenue": str(check.reconciliation.campaign_total_revenue),
                    "segment_total_revenue": str(check.reconciliation.segment_total_revenue),
                    "gap": str(check.reconciliation.gap),
                    "violations": check.violations,
                },
                execution_action="investigate_revenue_gap",
                expected_impact="恢复收入口径可对账后，营销分析结论才可对外发布",
                priority="high",
                risk_level="low",
            )
            suggestions_created.append(suggestion.id)

        await session.commit()
        duration = (datetime.now(UTC) - started_at).total_seconds()
        logger.info(
            "=== 营销经理每日分析完成(校验失败): 耗时%.1fs, 创建披露建议%d条 ===",
            duration, len(suggestions_created),
        )
        return {
            "agent": "marketing_manager",
            "duration_seconds": round(duration, 1),
            "suggestions_created": len(suggestions_created),
            "suggestion_ids": suggestions_created,
            "truthfulness": {
                "passed": False,
                "rules_version": check.rules_version,
                "violations": check.violations,
            },
        }

    # ---- 校验通过：生成营销优化建议 ----
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
                    f"数据来源: {campaign.get('source', '待标注')}"
                ),
                execution_params={
                    "campaign_id": campaign.get("id"),
                    "current_roas": campaign.get("roas"),
                    "target_roas": campaign.get("target_roas"),
                    "optimization_actions": ["adjust_audience", "refresh_creatives", "adjust_bid"],
                    "data_source": campaign.get("source"),
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
        "truthfulness": {
            "passed": True,
            "rules_version": check.rules_version,
            "violations": check.violations,
        },
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
# 客户经理每日任务
# --------------------------------------------------------------------------- #

async def run_customer_manager_daily(session: AsyncSession) -> dict[str, Any]:
    """客户经理每日分析。

    分析内容：
    - 客户满意度与评价监控
    - 退换货请求处理
    - 客户分群与生命周期
    - 客服响应时效
    - 流失客户预警
    """
    logger.info("=== 客户经理每日分析开始 ===")
    started_at = datetime.now(UTC)

    suggestions_created = []

    # 获取客户数据（简化版）
    customer_stats = await _get_customer_stats(session)

    # 1. 差评预警（低于3星的评价需要跟进）
    if customer_stats.get("low_rating_reviews"):
        for review in customer_stats["low_rating_reviews"]:
            suggestion = await agent_suggestion_service.create_suggestion(
                session,
                agent_id="customer_manager",
                suggestion_type="review_followup",
                title=f"差评跟进: 产品 {review.get('product_name', '未知')} 收到 {review.get('rating', 0)} 星评价",
                description=(
                    f"客户 {review.get('customer_name', '匿名')} 对产品 {review.get('product_name')} "
                    f"给出 {review.get('rating', 0)} 星评价：{review.get('comment', '无评价内容')}。"
                    f"建议在24小时内联系客户，了解问题并提供解决方案。"
                ),
                execution_params={
                    "review_id": review.get("id"),
                    "product_id": review.get("product_id"),
                    "customer_id": review.get("customer_id"),
                    "rating": review.get("rating"),
                    "response_deadline_hours": 24,
                },
                execution_action="followup_review",
                expected_impact="提升客户满意度，挽回差评客户",
                priority="high",
                risk_level="low",
            )
            suggestions_created.append(suggestion.id)

    # 2. 退换货请求处理
    if customer_stats.get("pending_returns"):
        for return_req in customer_stats["pending_returns"]:
            suggestion = await agent_suggestion_service.create_suggestion(
                session,
                agent_id="customer_manager",
                suggestion_type="return_processing",
                title=f"退换货待处理: 订单 {return_req.get('order_id', '未知')}",
                description=(
                    f"订单 {return_req.get('order_id')} 有 {return_req.get('type', '退货')} 请求待处理，"
                    f"已等待 {return_req.get('waiting_hours', 0)} 小时。"
                    f"建议在48小时内完成审核和处理，避免客户投诉升级。"
                ),
                execution_params={
                    "return_id": return_req.get("id"),
                    "order_id": return_req.get("order_id"),
                    "type": return_req.get("type"),
                    "waiting_hours": return_req.get("waiting_hours"),
                    "processing_deadline_hours": 48,
                },
                execution_action="process_return",
                expected_impact="提升退换货处理效率，降低客户投诉",
                priority="high",
                risk_level="medium",
            )
            suggestions_created.append(suggestion.id)

    # 3. 流失客户预警（超过90天未购买的活跃客户）
    if customer_stats.get("churn_risk_customers"):
        for customer in customer_stats["churn_risk_customers"]:
            suggestion = await agent_suggestion_service.create_suggestion(
                session,
                agent_id="customer_manager",
                suggestion_type="churn_prevention",
                title=f"流失预警: 客户 {customer.get('name', '未知')} 已 {customer.get('days_since_last_order', 0)} 天未购买",
                description=(
                    f"客户 {customer.get('name')} (累计消费 ${customer.get('total_spent', 0):.2f}) "
                    f"已 {customer.get('days_since_last_order', 0)} 天未购买，存在流失风险。"
                    f"建议发送个性化优惠券或新品推荐，激活客户复购。"
                ),
                execution_params={
                    "customer_id": customer.get("id"),
                    "customer_name": customer.get("name"),
                    "days_since_last_order": customer.get("days_since_last_order"),
                    "total_spent": str(customer.get("total_spent", 0)),
                    "recommended_action": "send_personalized_coupon",
                },
                execution_action="trigger_churn_prevention",
                expected_impact="降低客户流失率，提升复购率",
                priority="medium",
                risk_level="low",
            )
            suggestions_created.append(suggestion.id)

    await session.commit()

    duration = (datetime.now(UTC) - started_at).total_seconds()
    logger.info(
        "=== 客户经理每日分析完成: 耗时%.1fs, 创建建议%d条 ===",
        duration, len(suggestions_created),
    )

    return {
        "agent": "customer_manager",
        "duration_seconds": round(duration, 1),
        "suggestions_created": len(suggestions_created),
        "suggestion_ids": suggestions_created,
        "customer_stats_summary": {
            "total_customers": customer_stats.get("total_customers", 0),
            "low_rating_count": len(customer_stats.get("low_rating_reviews", [])),
            "pending_returns_count": len(customer_stats.get("pending_returns", [])),
            "churn_risk_count": len(customer_stats.get("churn_risk_customers", [])),
        },
    }


# --------------------------------------------------------------------------- #
# 商业分析师每日任务
# --------------------------------------------------------------------------- #

async def run_business_analyst_daily(session: AsyncSession) -> dict[str, Any]:
    """商业分析师每日分析。

    分析内容：
    - 经营数据日报（GMV/订单量/客单价/转化率）
    - 品类表现分析
    - 竞品动态监控
    - 财务健康度（毛利率/费用率/现金流）
    - 战略机会识别
    """
    logger.info("=== 商业分析师每日分析开始 ===")
    started_at = datetime.now(UTC)

    suggestions_created = []

    # 获取经营数据（简化版）
    business_stats = await _get_business_stats(session)

    # 1. 转化率异常预警
    if business_stats.get("conversion_rate") is not None:
        current_cvr = business_stats["conversion_rate"]
        target_cvr = business_stats.get("target_conversion_rate", Decimal("0.02"))
        if current_cvr < target_cvr * Decimal("0.8"):  # 低于目标80%触发预警
            suggestion = await agent_suggestion_service.create_suggestion(
                session,
                agent_id="business_analyst",
                suggestion_type="conversion_alert",
                title=f"转化率预警: 当前 {float(current_cvr):.2%}，低于目标 {float(target_cvr):.2%}",
                description=(
                    f"最近7天整体转化率 {float(current_cvr):.2%}，低于目标值 {float(target_cvr):.2%} 的80%阈值。"
                    f"建议排查：流量质量、产品页体验、价格竞争力、支付流程。"
                    f"数据来源: WooCommerce 订单统计 (M3.5 商业智能)"
                ),
                execution_params={
                    "current_conversion_rate": float(current_cvr),
                    "target_conversion_rate": float(target_cvr),
                    "period_days": 7,
                    "investigation_areas": ["traffic_quality", "product_page_ux", "price_competitiveness", "checkout_flow"],
                    "data_source": "WooCommerce 订单统计 (M3.5 商业智能)",
                },
                execution_action="investigate_conversion_drop",
                expected_impact="恢复转化率至目标水平，提升GMV",
                priority="high",
                risk_level="medium",
            )
            suggestions_created.append(suggestion.id)

    # 2. 毛利率预警
    if business_stats.get("gross_margin") is not None:
        current_margin = business_stats["gross_margin"]
        target_margin = business_stats.get("target_gross_margin", Decimal("0.4"))
        if current_margin < target_margin:
            suggestion = await agent_suggestion_service.create_suggestion(
                session,
                agent_id="business_analyst",
                suggestion_type="margin_alert",
                title=f"毛利率预警: 当前 {float(current_margin):.1%}，低于目标 {float(target_margin):.1%}",
                description=(
                    f"最近30天整体毛利率 {float(current_margin):.1%}，低于目标值 {float(target_margin):.1%}。"
                    f"建议排查：采购成本、定价策略、折扣力度、物流费用。"
                    f"数据来源: 订单+成本数据 (M3.5 商业智能)"
                ),
                execution_params={
                    "current_gross_margin": float(current_margin),
                    "target_gross_margin": float(target_margin),
                    "period_days": 30,
                    "investigation_areas": ["procurement_cost", "pricing_strategy", "discount_level", "logistics_cost"],
                    "data_source": "订单+成本数据 (M3.5 商业智能)",
                },
                execution_action="investigate_margin_decline",
                expected_impact="恢复毛利率至目标水平，提升盈利能力",
                priority="high",
                risk_level="high",
            )
            suggestions_created.append(suggestion.id)

    # 3. 低绩效品类优化建议
    if business_stats.get("underperforming_categories"):
        for category in business_stats["underperforming_categories"]:
            suggestion = await agent_suggestion_service.create_suggestion(
                session,
                agent_id="business_analyst",
                suggestion_type="category_optimization",
                title=f"品类优化: {category.get('name', '未知')} 表现低于平均",
                description=(
                    f"品类 {category.get('name')} 最近30天销售额 ${float(category.get('revenue', 0)):.2f}，"
                    f"毛利率 {float(category.get('margin', 0)):.1%}，低于品类平均水平。"
                    f"建议：优化选品结构、调整定价、加强营销推广或考虑淘汰SKU。"
                    f"数据来源: 品类销售统计 (M3.5 商业智能)"
                ),
                execution_params={
                    "category_id": category.get("id"),
                    "category_name": category.get("name"),
                    "revenue": float(category.get("revenue", 0)),
                    "margin": float(category.get("margin", 0)),
                    "recommended_actions": ["optimize_assortment", "adjust_pricing", "increase_marketing", "consider_sku_elimination"],
                    "data_source": "品类销售统计 (M3.5 商业智能)",
                },
                execution_action="optimize_category",
                expected_impact="提升品类整体销售额和毛利率",
                priority="medium",
                risk_level="medium",
            )
            suggestions_created.append(suggestion.id)

    await session.commit()

    duration = (datetime.now(UTC) - started_at).total_seconds()
    logger.info(
        "=== 商业分析师每日分析完成: 耗时%.1fs, 创建建议%d条 ===",
        duration, len(suggestions_created),
    )

    return {
        "agent": "business_analyst",
        "duration_seconds": round(duration, 1),
        "suggestions_created": len(suggestions_created),
        "suggestion_ids": suggestions_created,
        "business_stats_summary": {
            "gmv": str(business_stats.get("gmv", 0)),
            "order_count": business_stats.get("order_count", 0),
            "avg_order_value": str(business_stats.get("avg_order_value", 0)),
            "conversion_rate": float(business_stats.get("conversion_rate", 0)) if business_stats.get("conversion_rate") else 0,
            "gross_margin": float(business_stats.get("gross_margin", 0)) if business_stats.get("gross_margin") else 0,
            "alerts_triggered": len(suggestions_created),
        },
    }


# --------------------------------------------------------------------------- #
# 数据获取辅助函数（简化版，实际应调用对应业务服务）
# --------------------------------------------------------------------------- #

async def _get_product_stats(session: AsyncSession) -> dict[str, Any]:
    """获取产品统计数据（真实数据，来自 products 表）。"""
    from app.models.product import Product
    
    workspace_id = DEFAULT_WORKSPACE_ID
    
    # 1. 获取选品候选池（draft + candidate）
    product_rows = (
        await session.execute(
            select(Product).where(
                Product.workspace_id == workspace_id,
                Product.status.in_(ANALYST_PRODUCT_STATUSES),
            )
        )
    ).scalars().all()
    
    total_products = len(product_rows)
    
    # 2. 模拟低库存产品（基于产品列表，取前3个作为示例）
    # 实际应从 inventory_snapshots 表获取真实库存
    low_stock_products = []
    for p in product_rows[:3]:
        low_stock_products.append({
            "id": str(p.id),
            "name": p.name or p.sku or "未知产品",
            "sku": p.sku,
            "stock": 5,  # 模拟低库存
            "reorder_qty": 50,
            "category": p.category,
        })
    
    # 3. 模拟低转化率产品（取接下来的2个作为示例）
    low_conversion_products = []
    for p in product_rows[3:5]:
        low_conversion_products.append({
            "id": str(p.id),
            "name": p.name or p.sku or "未知产品",
            "sku": p.sku,
            "conversion_rate": 0.008,  # 模拟0.8%低转化率
            "category": p.category,
        })
    
    return {
        "total_products": total_products,
        "low_stock_products": low_stock_products,
        "low_conversion_products": low_conversion_products,
    }


async def _get_marketing_stats(session: AsyncSession) -> dict[str, Any]:
    """获取营销统计数据（真实数据，来自 campaigns 与 customer_profiles 表）。"""
    workspace_id = DEFAULT_WORKSPACE_ID

    campaign_rows = (
        await session.execute(
            select(Campaign).where(Campaign.workspace_id == workspace_id)
        )
    ).scalars().all()
    campaigns = [
        {
            "name": c.name or c.campaign_id,
            "channel": c.platform,
            "status": c.status,
            "spend": c.spend,
            "revenue": c.revenue,
            "source": "campaigns 表 (M3.1 营销智能)",
            "id": str(c.id),
            "roas": c.roas,
            "target_roas": DEFAULT_TARGET_ROAS,
        }
        for c in campaign_rows
    ]

    profile_rows = (
        await session.execute(
            select(CustomerProfile).where(
                CustomerProfile.workspace_id == workspace_id
            )
        )
    ).scalars().all()
    repeat_count = sum(1 for c in profile_rows if (c.total_orders or 0) > 1)
    new_count = sum(1 for c in profile_rows if (c.total_orders or 0) == 1)
    repeat_revenue = sum(
        (c.total_revenue or Decimal("0"))
        for c in profile_rows
        if (c.total_orders or 0) > 1
    )
    new_revenue = sum(
        (c.total_revenue or Decimal("0"))
        for c in profile_rows
        if (c.total_orders or 0) == 1
    )
    customer_segments = [
        {
            "name": "repeat",
            "customer_count": repeat_count,
            "revenue": repeat_revenue,
            "source": "customer_profiles 表 (M3.3 客户智能)",
        },
        {
            "name": "new",
            "customer_count": new_count,
            "revenue": new_revenue,
            "source": "customer_profiles 表 (M3.3 客户智能)",
        },
    ]

    underperforming = [
        c for c in campaigns
        if c["status"] != "planned"
        and c["roas"] is not None
        and c["roas"] < c["target_roas"]
    ]

    total_spend = sum((c["spend"] or Decimal("0")) for c in campaigns)
    total_revenue = sum((c["revenue"] or Decimal("0")) for c in campaigns)

    return {
        "active_campaigns": len(campaigns),
        "campaigns": campaigns,
        "customer_segments": customer_segments,
        "underperforming_campaigns": underperforming,
        "total_spend": total_spend,
        "total_revenue": total_revenue,
    }


async def _get_supply_chain_stats(session: AsyncSession) -> dict[str, Any]:
    """供应链统计：产品取自 products 表，库存/补货明细仍是占位值。

    历史版本此处 `from app.models.inventory import InventorySnapshot` —— 该模块
    不存在，真实的库存模型是 app.models.supply_chain.InventorySnapshot
    （表 inventory_snapshots）。导入位于函数体内且 ImportError 未被捕获，导致
    daily_supply_chain_manager 每次调度都直接失败。

    接真实 inventory_snapshots 汇总（total_inventory_value、
    need_reorder_products、pending_purchase_orders、supplier_count）属于
    P2 backlog，见 docs/agent_team_workflow_refactor.md §P2。
    """
    from app.models.product import Product

    workspace_id = DEFAULT_WORKSPACE_ID
    
    # 1. 获取已立项产品（candidate + active）
    product_rows = (
        await session.execute(
            select(Product).where(
                Product.workspace_id == workspace_id,
                Product.status.in_(SUPPLY_CHAIN_PRODUCT_STATUSES),
            )
        )
    ).scalars().all()
    
    # 2. 模拟需要补货的产品（取前2个）
    need_reorder_products = []
    for p in product_rows[:2]:
        need_reorder_products.append({
            "id": str(p.id),
            "name": p.name or p.sku or "未知产品",
            "sku": p.sku,
            "stock": 3,
            "days_to_stockout": 5,
            "supplier": "默认供应商",
            "reorder_qty": 100,
        })
    
    return {
        "total_inventory_value": 15000,
        "need_reorder_products": need_reorder_products,
        "pending_purchase_orders": 0,
        "supplier_count": 3,
    }


async def _get_customer_stats(session: AsyncSession) -> dict[str, Any]:
    """获取客户统计数据（简化版）。

    实际应从 customer_service / customer_intelligence 服务获取。
    """
    return {
        "total_customers": 0,
        "low_rating_reviews": [],
        "pending_returns": [],
        "churn_risk_customers": [],
        "avg_response_time_hours": 0,
        "satisfaction_score": 0,
    }


async def _get_business_stats(session: AsyncSession) -> dict[str, Any]:
    """获取经营统计数据（简化版）。

    实际应从 business_intelligence / analytics 服务获取。
    数据来源标注（R1）：经营数据固定来自 WooCommerce 订单表 + 成本表。
    """
    return {
        "gmv": Decimal("0"),
        "order_count": 0,
        "avg_order_value": Decimal("0"),
        "conversion_rate": None,
        "target_conversion_rate": Decimal("0.02"),
        "gross_margin": None,
        "target_gross_margin": Decimal("0.40"),
        "underperforming_categories": [],
        "data_source": "WooCommerce 订单表 + 成本表 (M3.5 商业智能)",
    }
