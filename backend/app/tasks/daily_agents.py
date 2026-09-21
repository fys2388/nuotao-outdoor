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

# 补货目标 = 低库存阈值的 N 倍。阈值本身来自
# business_alert_service.DEFAULT_THRESHOLDS["stockout_threshold"]（"低库存"的
# 唯一权威定义），这里只定一个倍数把"低于阈值"翻译成"补到多少"。
#
# 不做成纯魔法数埋在调用点，是为了让公式可评审、可单点调整；也避免 AGENTS.md
# §1.2 第 5 条禁止的"硬编码业务经验值"。实测 available 为 0 时按目标全量补。
REORDER_TARGET_MULTIPLIER = 4


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

    # 2. 生成库存预警建议（available 来自 inventory_snapshots 实测值）
    low_stock = product_stats.get("low_stock_products")
    unit_costs = await _get_unit_costs(
        session, [str(p["id"]) for p in low_stock]
    ) if low_stock else {}
    if low_stock:
        for product in low_stock:
            threshold = product.get("stockout_threshold", 0)
            unit_cost = unit_costs.get(str(product.get("id")), 0.0)
            suggestion = await agent_suggestion_service.create_suggestion(
                session,
                agent_id="product_analyst",
                suggestion_type="inventory_restock",
                title=f"库存预警: {product.get('name', '未知产品')} 库存不足",
                description=(
                    f"产品 {product.get('name')} 当前可发货库存 {product.get('available', 0)} 件，"
                    f"低于低库存阈值 {threshold}；在途 {product.get('in_transit', 0)} 件，"
                    f"覆盖仓位 {', '.join(product.get('locations', []))}。"
                    f"建议补货 {product.get('reorder_qty', 0)} 件"
                    f"（目标库存 = 阈值 × {REORDER_TARGET_MULTIPLIER}）。"
                ),
                execution_params={
                    "product_id": product.get("id"),
                    "quantity": product.get("reorder_qty", 0),
                    "unit_cost": unit_cost,
                    "current_available": product.get("available", 0),
                    "in_transit": product.get("in_transit", 0),
                    "locations": product.get("locations", []),
                    "stockout_threshold": threshold,
                },
                execution_action="restock_inventory",
                expected_impact=f"可发货库存从 {product.get('available', 0)} 补至 {threshold * REORDER_TARGET_MULTIPLIER}",
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

    # 生成补货建议（available 来自 inventory_snapshots 实测值）
    need_reorder = supply_stats.get("need_reorder_products")
    unit_costs = await _get_unit_costs(
        session, [str(p["id"]) for p in need_reorder]
    ) if need_reorder else {}
    if need_reorder:
        for product in need_reorder:
            threshold = product.get("stockout_threshold", 0)
            unit_cost = unit_costs.get(str(product.get("id")), 0.0)
            suggestion = await agent_suggestion_service.create_suggestion(
                session,
                agent_id="supply_chain_manager",
                suggestion_type="inventory_restock",
                title=f"补货建议: {product.get('name')} 需补货",
                description=(
                    f"产品 {product.get('name')} 可发货库存 {product.get('available', 0)} 件，"
                    f"低于低库存阈值 {threshold}；在途 {product.get('in_transit', 0)} 件，"
                    f"覆盖仓位 {', '.join(product.get('locations', []))}。"
                    f"建议采购 {product.get('reorder_qty', 0)} 件"
                    f"（目标库存 = 阈值 × {REORDER_TARGET_MULTIPLIER}）。"
                    f"供应商与到货周期需审批时指定（当前无供应商主数据）。"
                    + (
                        f"按采购单价 {unit_cost:.2f} 估算金额 "
                        f"{unit_cost * product.get('reorder_qty', 0):.2f}。"
                        if unit_cost > 0 else
                        "产品缺少采购单价（product_cost.purchase_cost 为空），"
                        "审批人需补充单价，否则生成的采购单金额为 0。"
                    )
                ),
                execution_params={
                    "product_id": product.get("id"),
                    "quantity": product.get("reorder_qty", 0),
                    "unit_cost": unit_cost,
                    "current_available": product.get("available", 0),
                    "in_transit": product.get("in_transit", 0),
                    "locations": product.get("locations", []),
                    "stockout_threshold": threshold,
                },
                execution_action="create_purchase_order",
                expected_impact=f"可发货库存从 {product.get('available', 0)} 补至 {threshold * REORDER_TARGET_MULTIPLIER}",
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

async def _low_stock_from_inventory(
    session: AsyncSession, *, workspace_id, product_ids: list[Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """从 inventory_snapshots 查真实低库存产品，返回 (产品列表, 诊断信息)。

    ``inventory_snapshots`` 是**当前状态表**：每个 (workspace, product,
    location) 一行，唯一约束，不是历史快照。``available`` 为可发货量。

    阈值复用 ``business_alert_service.DEFAULT_THRESHOLDS["stockout_threshold"]``，
    与预警引擎和仪表盘共用单一来源 —— 否则三处对"低库存"的定义会各说各话。

    关键约束：**没有快照行的产品不出现在结果里**。此前本函数用
    ``product_rows[:3]`` + 硬编码 ``stock: 5`` 伪造低库存，等于把没测量过的
    数字写进审批队列，人会据此真去补货。宁可返回空列表，也不编造库存水平；
    诊断信息里会给出"多少产品缺快照"，让空结果可解释而不是静默。

    同一产品在多个 location 有库存时按 location 汇总 available。
    """
    from app.models.supply_chain import InventorySnapshot
    from app.services.business_alert_service import DEFAULT_THRESHOLDS

    threshold = int(DEFAULT_THRESHOLDS["stockout_threshold"])
    diagnostic: dict[str, Any] = {
        "source": "inventory_snapshots",
        "stockout_threshold": threshold,
        "snapshot_rows_in_workspace": 0,
        "products_in_scope": len(product_ids),
        "products_without_snapshot": len(product_ids),
    }

    if not product_ids:
        return [], diagnostic

    total_rows = (
        await session.execute(
            select(func.count()).select_from(InventorySnapshot).where(
                InventorySnapshot.workspace_id == workspace_id
            )
        )
    ).scalar() or 0
    diagnostic["snapshot_rows_in_workspace"] = int(total_rows)

    rows = (
        await session.execute(
            select(InventorySnapshot).where(
                InventorySnapshot.workspace_id == workspace_id,
                InventorySnapshot.product_id.in_(product_ids),
                InventorySnapshot.available <= threshold,
            )
        )
    ).scalars().all()

    by_product: dict[Any, list[dict[str, Any]]] = {}
    for r in rows:
        by_product.setdefault(r.product_id, []).append(r)

    covered = set(by_product) | set(
        (await session.execute(
            select(InventorySnapshot.product_id).where(
                InventorySnapshot.workspace_id == workspace_id,
                InventorySnapshot.product_id.in_(product_ids),
            )
        )).scalars().all()
    )
    diagnostic["products_without_snapshot"] = len(product_ids) - len(covered)

    products: list[dict[str, Any]] = []
    for pid, parts in sorted(by_product.items(), key=lambda kv: str(kv[0])):
        available = sum(p.available for p in parts)
        products.append({
            "id": str(pid),
            "available": available,
            "quantity": sum(p.quantity for p in parts),
            "reserved": sum(p.reserved for p in parts),
            "in_transit": sum(p.in_transit for p in parts),
            "locations": sorted({p.location for p in parts}),
            "snapshot_time": max(p.snapshot_time for p in parts),
        })
    return products, diagnostic


async def _get_unit_costs(
    session: AsyncSession, product_ids: list[str]
) -> dict[str, float]:
    """批量取采购单价，返回 {product_id: purchase_cost}。

    采购单金额此前恒为 0：agent 的 execution_params 不带 unit_cost，
    procurement_service 只能用默认值 0，产出 total=0.00 的采购单——这种单据
    进不了真实采购流程（无法算账、无法比对报价）。

    单价来源是 ProductCost.purchase_cost，即 PROFIT-001 落地成本模型里的采购
    单价（total_landed_cost 含运费税费等，不是采购价，不能用来下采购单）。

    没有成本行的产品返回缺失，调用方按 0 处理并在建议里标注需人工补价。
    """
    from app.models.product import ProductCost

    if not product_ids:
        return {}
    rows = (
        await session.execute(
            select(ProductCost.product_id, ProductCost.purchase_cost).where(
                ProductCost.product_id.in_([_uuid(pid) for pid in product_ids])
            )
        )
    ).all()
    return {str(r.product_id): float(r.purchase_cost) for r in rows}


def _uuid(value: Any) -> Any:
    """把 suggestion params 里的字符串 id 转成 UUID；已是 UUID 则原样返回。"""
    from uuid import UUID as _UUID

    if isinstance(value, str):
        try:
            return _UUID(value)
        except ValueError:
            return value
    return value


async def _get_product_stats(session: AsyncSession) -> dict[str, Any]:
    """产品分析师数据：产品取自 products 表，库存取自 inventory_snapshots。

    此前 low_stock_products 用 ``product_rows[:3]`` + 硬编码 ``stock: 5`` 伪造，
    low_conversion_products 用 ``product_rows[3:5]`` + 硬编码 ``conversion_rate:
    0.008`` 伪造。两者都已改为查真实数据或返回空列表。

    low_conversion_products 目前**恒为空**：prod 没有任何订单/转化数据
    （orders 相关表全部为 0 行），转化率无从计算。等有订单数据后再接真实来源。
    """
    from app.models.product import Product

    workspace_id = DEFAULT_WORKSPACE_ID

    # 1. 获取选品候选池（draft + candidate）
    # 必须排除软删产品：prod 上 37 个 1688/pipeline 历史导入产品已全部
    # deleted_at 标记，不排除会把死数据当活候选池（诊断里 products_in_scope
    # 会虚高 40 而实际在售只有 2 个）。
    product_rows = (
        await session.execute(
            select(Product).where(
                Product.workspace_id == workspace_id,
                Product.status.in_(ANALYST_PRODUCT_STATUSES),
                Product.deleted_at.is_(None),
            )
        )
    ).scalars().all()

    total_products = len(product_rows)
    product_ids = [p.id for p in product_rows]

    # 2. 真实低库存产品（来自 inventory_snapshots，无快照则不出现在列表里）
    low_stock_rows, inventory_diagnostic = await _low_stock_from_inventory(
        session, workspace_id=workspace_id, product_ids=product_ids
    )

    threshold = inventory_diagnostic["stockout_threshold"]
    by_id = {str(p.id): p for p in product_rows}
    low_stock_products = []
    for row in low_stock_rows:
        p = by_id.get(row["id"])
        low_stock_products.append({
            "id": row["id"],
            "name": (p.name or p.sku or "未知产品") if p else "未知产品",
            "sku": p.sku if p else None,
            "category": p.category if p else None,
            "available": row["available"],
            "in_transit": row["in_transit"],
            "locations": row["locations"],
            "stockout_threshold": threshold,
            "reorder_qty": max(threshold * REORDER_TARGET_MULTIPLIER - row["available"], 0),
        })

    # 3. 低转化率产品：恒为空。prod 无订单数据，转化率无法计算，不伪造。
    low_conversion_products: list[dict[str, Any]] = []

    return {
        "total_products": total_products,
        "low_stock_products": low_stock_products,
        "low_conversion_products": low_conversion_products,
        "low_conversion_empty_reason": (
            "prod 无订单/转化数据，无法计算产品级转化率；"
            "有 orders 数据后应接真实来源"
        ),
        "inventory_diagnostic": inventory_diagnostic,
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
    """供应链统计：产品取自 products 表，库存取自 inventory_snapshots。

    历史版本此处 `from app.models.inventory import InventorySnapshot` —— 该模块
    不存在，真实的库存模型是 app.models.supply_chain.InventorySnapshot
    （表 inventory_snapshots）。导入位于函数体内且 ImportError 未被捕获，导致
    daily_supply_chain_manager 每次调度都直接失败。

    更早的版本 need_reorder_products 用 ``product_rows[:2]`` + 硬编码
    ``stock: 3`` / ``days_to_stockout: 5`` / ``supplier: "默认供应商"`` 伪造，
    现已改为查真实 inventory_snapshots。

    ``days_to_stockout`` 与 ``supplier`` 已移除：前者需要订单流速数据
    （prod orders 表全空），后者需要供应商主数据（当前无 suppliers 表），
    两者都没有真实来源，宁可不给也不编造。

    ``total_inventory_value`` / ``pending_purchase_orders`` / ``supplier_count``
    仍是占位值：库存价值需要单品成本数据（inventory_snapshots 无单价字段），
    采购单与供应商需要相应业务表。见 docs/agent_team_workflow_refactor.md §P2。
    """
    from app.models.product import Product

    workspace_id = DEFAULT_WORKSPACE_ID

    # 1. 获取已立项产品（candidate + active）
    # 同样排除软删产品，理由见 _get_product_stats。
    product_rows = (
        await session.execute(
            select(Product).where(
                Product.workspace_id == workspace_id,
                Product.status.in_(SUPPLY_CHAIN_PRODUCT_STATUSES),
                Product.deleted_at.is_(None),
            )
        )
    ).scalars().all()

    # 2. 真实需补货产品（来自 inventory_snapshots，无快照则不出现在列表里）
    need_reorder_rows, inventory_diagnostic = await _low_stock_from_inventory(
        session, workspace_id=workspace_id, product_ids=[p.id for p in product_rows]
    )

    threshold = inventory_diagnostic["stockout_threshold"]
    by_id = {str(p.id): p for p in product_rows}
    need_reorder_products = []
    for row in need_reorder_rows:
        p = by_id.get(row["id"])
        need_reorder_products.append({
            "id": row["id"],
            "name": (p.name or p.sku or "未知产品") if p else "未知产品",
            "sku": p.sku if p else None,
            "available": row["available"],
            "in_transit": row["in_transit"],
            "locations": row["locations"],
            "stockout_threshold": threshold,
            "reorder_qty": max(threshold * REORDER_TARGET_MULTIPLIER - row["available"], 0),
        })

    return {
        "total_inventory_value": 15000,  # 占位：需单品成本数据才能真实计算
        "need_reorder_products": need_reorder_products,
        "pending_purchase_orders": 0,     # 占位：需采购单表
        "supplier_count": 3,              # 占位：需供应商主数据
        "inventory_diagnostic": inventory_diagnostic,
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
