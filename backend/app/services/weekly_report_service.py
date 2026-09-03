"""
AI 经营周报服务
支持自动生成周报、异常解释、趋势分析、建议与行动项
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

# 周报数据存储路径
DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "weekly_reports",
)


def _ensure_data_dir() -> None:
    """确保数据目录存在"""
    os.makedirs(DATA_DIR, exist_ok=True)


def _get_report_path(report_id: str) -> str:
    """获取周报数据文件路径"""
    return os.path.join(DATA_DIR, f"report_{report_id}.json")


def _load_report(report_id: str) -> dict[str, Any] | None:
    """加载周报数据"""
    path = _get_report_path(report_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to load report %s: %s", report_id, str(e))
        return None


def _save_report(report: dict[str, Any]) -> None:
    """保存周报数据"""
    _ensure_data_dir()
    path = _get_report_path(report["id"])
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("Failed to save report %s: %s", report["id"], str(e))


def generate_weekly_report(
    week_start: str | None = None,
    week_end: str | None = None,
    business_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    生成 AI 经营周报

    Args:
        week_start: 周报开始日期
        week_end: 周报结束日期
        business_data: 经营数据（可选，不提供则使用模拟数据）

    Returns:
        完整的 AI 经营周报
    """
    now = datetime.utcnow()

    if week_start is None:
        week_start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    if week_end is None:
        week_end = now.strftime("%Y-%m-%d")

    # 如果没有提供经营数据，使用模拟数据
    if business_data is None:
        business_data = _generate_mock_business_data(week_start, week_end)

    # 分析异常
    anomalies = _analyze_anomalies(business_data)

    # 生成趋势分析
    trends = _analyze_trends(business_data)

    # 生成 AI 洞察和建议
    insights = _generate_ai_insights(business_data, anomalies, trends)

    # 生成行动项
    action_items = _generate_action_items(insights, anomalies)

    report_id = str(uuid4())
    report = {
        "id": report_id,
        "type": "weekly_business_report",
        "title": f"Nuotao Outdoor 经营周报 ({week_start} ~ {week_end})",
        "period": {
            "start": week_start,
            "end": week_end,
            "generated_at": now.isoformat(),
        },
        "executive_summary": _generate_executive_summary(business_data, anomalies),
        "key_metrics": business_data.get("key_metrics", {}),
        "trend_analysis": trends,
        "anomaly_detection": anomalies,
        "ai_insights": insights,
        "action_items": action_items,
        "product_highlights": business_data.get("product_highlights", []),
        "marketing_performance": business_data.get("marketing_performance", {}),
        "customer_insights": business_data.get("customer_insights", {}),
        "risk_factors": _identify_risks(business_data, anomalies),
        "next_week_outlook": _generate_outlook(business_data, trends),
        "status": "generated",
    }

    _save_report(report)
    logger.info("Weekly report generated: id=%s, period=%s~%s", report_id, week_start, week_end)
    return report


def _generate_mock_business_data(start: str, end: str) -> dict[str, Any]:
    """生成模拟经营数据"""
    return {
        "key_metrics": {
            "total_orders": {"current": 156, "previous": 142, "change_percent": 9.86},
            "total_revenue": {"current": 23456.78, "previous": 21234.56, "change_percent": 10.47, "currency": "USD"},
            "gross_profit": {"current": 9851.85, "previous": 8918.51, "change_percent": 10.47},
            "gross_margin": {"current": 42.0, "previous": 42.0, "change_percent": 0},
            "avg_order_value": {"current": 150.36, "previous": 149.54, "change_percent": 0.55},
            "refund_rate": {"current": 3.2, "previous": 2.8, "change_percent": 14.29},
            "ad_spend": {"current": 2500.0, "previous": 2200.0, "change_percent": 13.64},
            "roas": {"current": 9.38, "previous": 9.65, "change_percent": -2.80},
            "new_customers": {"current": 68, "previous": 62, "change_percent": 9.68},
            "returning_customers": {"current": 88, "previous": 80, "change_percent": 10.0},
            "customer_acquisition_cost": {"current": 36.76, "previous": 35.48, "change_percent": 3.61},
        },
        "product_highlights": [
            {"name": "Premium Camping Tent 4-Person", "units_sold": 45, "revenue": 6749.55, "margin": 42.5, "trend": "up", "note": "本周销量冠军，同比增长 15%"},
            {"name": "Lightweight Hiking Backpack 40L", "units_sold": 38, "revenue": 3419.62, "margin": 48.2, "trend": "up", "note": "毛利率最高产品之一"},
            {"name": "Waterproof Sleeping Bag -10°C", "units_sold": 32, "revenue": 2559.68, "margin": 38.7, "trend": "flat", "note": "销量持平，考虑促销"},
        ],
        "marketing_performance": {
            "channels": [
                {"name": "Google Ads", "spend": 1200, "revenue": 14400, "roas": 12.0, "conversions": 45},
                {"name": "Facebook Ads", "spend": 800, "revenue": 6400, "roas": 8.0, "conversions": 32},
                {"name": "Email Marketing", "spend": 200, "revenue": 2400, "roas": 12.0, "conversions": 28},
                {"name": "Organic Search", "spend": 300, "revenue": 256.78, "roas": 0.86, "conversions": 8},
            ],
            "best_channel": "Google Ads",
            "worst_channel": "Organic Search",
        },
        "customer_insights": {
            "new_customer_rate": 43.59,
            "repeat_purchase_rate": 56.41,
            "avg_customer_lifetime_value": 450.0,
            "top_regions": ["United States (62%)", "United Kingdom (12%)", "Germany (8%)", "Canada (6%)", "Other (12%)"],
        },
    }


def _analyze_anomalies(data: dict[str, Any]) -> dict[str, Any]:
    """分析经营异常"""
    anomalies = []
    key_metrics = data.get("key_metrics", {})

    # 检查退款率异常
    refund_rate = key_metrics.get("refund_rate", {})
    if refund_rate.get("current", 0) > 3.0:
        anomalies.append({
            "type": "refund_rate_high",
            "severity": "warning",
            "metric": "refund_rate",
            "current_value": refund_rate.get("current"),
            "threshold": 3.0,
            "description": f"退款率 {refund_rate.get('current')}% 超过警戒线 3.0%，环比增长 {refund_rate.get('change_percent')}%",
            "possible_causes": ["产品质量问题", "物流延迟导致退货", "产品描述与实际不符", "竞争对手降价导致比较退货"],
            "recommended_action": "立即审查本周退款订单原因，联系退款客户了解具体问题，检查产品质量和物流时效。",
        })

    # 检查 ROAS 下降
    roas = key_metrics.get("roas", {})
    if roas.get("change_percent", 0) < -2:
        anomalies.append({
            "type": "roas_decline",
            "severity": "warning",
            "metric": "roas",
            "current_value": roas.get("current"),
            "previous_value": roas.get("previous"),
            "change_percent": roas.get("change_percent"),
            "description": f"广告 ROAS 从 {roas.get('previous')} 下降到 {roas.get('current')}，降幅 {abs(roas.get('change_percent'))}%",
            "possible_causes": ["广告创意疲劳", "关键词竞争加剧", "落地页转化率下降", "季节性需求变化"],
            "recommended_action": "审查各广告渠道表现，暂停低效广告组，A/B 测试新创意，优化落地页。",
        })

    # 检查毛利率下降
    gross_margin = key_metrics.get("gross_margin", {})
    if gross_margin.get("change_percent", 0) < -1:
        anomalies.append({
            "type": "margin_decline",
            "severity": "critical",
            "metric": "gross_margin",
            "current_value": gross_margin.get("current"),
            "previous_value": gross_margin.get("previous"),
            "change_percent": gross_margin.get("change_percent"),
            "description": f"毛利率从 {gross_margin.get('previous')}% 下降到 {gross_margin.get('current')}%",
            "possible_causes": ["产品成本上升", "折扣力度过大", "低毛利产品占比增加", "运费上涨"],
            "recommended_action": "分析产品成本结构，优化采购价格，调整定价策略，减少低毛利产品促销。",
        })

    # 检查客单价下降
    aov = key_metrics.get("avg_order_value", {})
    if aov.get("change_percent", 0) < -3:
        anomalies.append({
            "type": "aov_decline",
            "severity": "info",
            "metric": "avg_order_value",
            "current_value": aov.get("current"),
            "previous_value": aov.get("previous"),
            "change_percent": aov.get("change_percent"),
            "description": f"客单价从 ${aov.get('previous')} 下降到 ${aov.get('current')}",
            "possible_causes": ["低价产品促销", "捆绑销售效果下降", "客户预算减少"],
            "recommended_action": "优化产品推荐算法，增加捆绑销售和满减活动，提升高价值产品曝光。",
        })

    return {
        "total_anomalies": len(anomalies),
        "critical_count": sum(1 for a in anomalies if a["severity"] == "critical"),
        "warning_count": sum(1 for a in anomalies if a["severity"] == "warning"),
        "info_count": sum(1 for a in anomalies if a["severity"] == "info"),
        "anomalies": anomalies,
    }


def _analyze_trends(data: dict[str, Any]) -> dict[str, Any]:
    """分析趋势"""
    key_metrics = data.get("key_metrics", {})

    positive_trends = []
    negative_trends = []
    stable_trends = []

    for metric_name, metric_data in key_metrics.items():
        change = metric_data.get("change_percent", 0)
        if change > 2:
            positive_trends.append({"metric": metric_name, "change_percent": change, "direction": "up"})
        elif change < -2:
            negative_trends.append({"metric": metric_name, "change_percent": change, "direction": "down"})
        else:
            stable_trends.append({"metric": metric_name, "change_percent": change, "direction": "stable"})

    return {
        "positive_trends": positive_trends,
        "negative_trends": negative_trends,
        "stable_trends": stable_trends,
        "summary": {
            "improving_metrics": len(positive_trends),
            "declining_metrics": len(negative_trends),
            "stable_metrics": len(stable_trends),
            "overall_direction": "positive" if len(positive_trends) > len(negative_trends) else "negative" if len(negative_trends) > len(positive_trends) else "mixed",
        },
    }


def _generate_ai_insights(
    data: dict[str, Any],
    anomalies: dict[str, Any],
    trends: dict[str, Any],
) -> list[dict[str, Any]]:
    """生成 AI 洞察"""
    insights = []
    key_metrics = data.get("key_metrics", {})

    # 收入增长洞察
    revenue = key_metrics.get("total_revenue", {})
    if revenue.get("change_percent", 0) > 5:
        insights.append({
            "category": "growth",
            "title": "收入增长强劲",
            "insight": f"本周收入 ${revenue.get('current'):,.2f}，环比增长 {revenue.get('change_percent')}%，主要由订单量增长驱动。Google Ads 和 Email Marketing 渠道表现优异，ROAS 均达到 12.0。",
            "confidence": "high",
            "impact": "positive",
        })

    # 客户结构洞察
    customer_insights = data.get("customer_insights", {})
    if customer_insights.get("repeat_purchase_rate", 0) > 50:
        insights.append({
            "category": "customer",
            "title": "复购率健康",
            "insight": f"复购客户占比 {customer_insights.get('repeat_purchase_rate')}%，表明客户忠诚度良好。新客户率 {customer_insights.get('new_customer_rate')}%，客户获取成本 ${key_metrics.get('customer_acquisition_cost', {}).get('current')}，在可接受范围内。",
            "confidence": "high",
            "impact": "positive",
        })

    # 产品洞察
    product_highlights = data.get("product_highlights", [])
    if product_highlights:
        top_product = product_highlights[0]
        insights.append({
            "category": "product",
            "title": f"明星产品: {top_product['name']}",
            "insight": f"{top_product['name']} 本周销量 {top_product['units_sold']} 件，收入 ${top_product['revenue']:,.2f}，毛利率 {top_product['margin']}%。{top_product.get('note', '')} 建议增加库存并加大推广力度。",
            "confidence": "high",
            "impact": "positive",
        })

    # 营销渠道洞察
    marketing = data.get("marketing_performance", {})
    if marketing.get("worst_channel"):
        insights.append({
            "category": "marketing",
            "title": f"渠道优化机会: {marketing['worst_channel']}",
            "insight": f"{marketing['best_channel']} 表现最佳，ROAS 领先。{marketing['worst_channel']} 渠道 ROAS 较低，建议优化 SEO 策略和内容营销，提升自然搜索流量质量。",
            "confidence": "medium",
            "impact": "neutral",
        })

    # 异常洞察
    if anomalies.get("warning_count", 0) > 0:
        insights.append({
            "category": "risk",
            "title": "需要关注的风险指标",
            "insight": f"本周检测到 {anomalies['total_anomalies']} 个异常指标，其中 {anomalies['warning_count']} 个警告。退款率上升和 ROAS 下降需要重点关注，建议立即采取行动防止问题扩大。",
            "confidence": "high",
            "impact": "negative",
        })

    return insights


def _generate_action_items(
    insights: list[dict[str, Any]],
    anomalies: dict[str, Any],
) -> list[dict[str, Any]]:
    """生成行动项"""
    action_items = []

    # 基于异常生成行动项
    for anomaly in anomalies.get("anomalies", []):
        priority = "high" if anomaly["severity"] == "critical" else "medium" if anomaly["severity"] == "warning" else "low"
        action_items.append({
            "id": str(uuid4()),
            "title": f"处理{anomaly['type']}问题",
            "description": anomaly["recommended_action"],
            "priority": priority,
            "status": "pending",
            "due_date": (datetime.utcnow() + timedelta(days=7 if priority == "high" else 14)).strftime("%Y-%m-%d"),
            "related_anomaly": anomaly["type"],
        })

    # 基于洞察生成行动项
    for insight in insights:
        if insight["category"] == "growth" and insight["impact"] == "positive":
            action_items.append({
                "id": str(uuid4()),
                "title": "扩大增长渠道投入",
                "description": "对表现优异的 Google Ads 和 Email Marketing 渠道增加预算，测试新的广告创意和邮件序列，争取下周收入增长 15%。",
                "priority": "medium",
                "status": "pending",
                "due_date": (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d"),
                "related_insight": insight["title"],
            })
        elif insight["category"] == "product":
            action_items.append({
                "id": str(uuid4()),
                "title": "优化明星产品库存和推广",
                "description": "增加 Premium Camping Tent 库存，确保不断货。制作产品使用视频和用户评价内容，提升转化率。",
                "priority": "medium",
                "status": "pending",
                "due_date": (datetime.utcnow() + timedelta(days=10)).strftime("%Y-%m-%d"),
                "related_insight": insight["title"],
            })

    return action_items


def _generate_executive_summary(
    data: dict[str, Any],
    anomalies: dict[str, Any],
) -> str:
    """生成执行摘要"""
    key_metrics = data.get("key_metrics", {})
    revenue = key_metrics.get("total_revenue", {})
    orders = key_metrics.get("total_orders", {})
    margin = key_metrics.get("gross_margin", {})

    summary = (
        f"本周经营表现整体良好，收入 ${revenue.get('current', 0):,.2f}，环比增长 {revenue.get('change_percent', 0)}%；"
        f"订单量 {orders.get('current', 0)} 单，环比增长 {orders.get('change_percent', 0)}%；"
        f"毛利率保持在 {margin.get('current', 0)}%。"
    )

    if anomalies.get("total_anomalies", 0) > 0:
        summary += (
            f"需要关注：检测到 {anomalies['total_anomalies']} 个异常指标"
            f"（{anomalies.get('critical_count', 0)} 个严重，{anomalies.get('warning_count', 0)} 个警告），"
            f"主要集中在退款率上升和广告 ROAS 下降。"
        )

    summary += "建议重点优化退款原因分析和广告渠道效率，同时扩大高 ROAS 渠道投入。"

    return summary


def _identify_risks(
    data: dict[str, Any],
    anomalies: dict[str, Any],
) -> list[dict[str, Any]]:
    """识别风险因素"""
    risks = []

    if anomalies.get("warning_count", 0) > 0:
        risks.append({
            "type": "operational",
            "level": "medium",
            "description": "退款率持续上升可能影响品牌声誉和利润率",
            "mitigation": "建立退款原因追踪机制，每周分析退款趋势，及时解决产品和物流问题",
        })

    key_metrics = data.get("key_metrics", {})
    if key_metrics.get("roas", {}).get("change_percent", 0) < 0:
        risks.append({
            "type": "marketing",
            "level": "medium",
            "description": "广告 ROAS 下降可能导致获客成本上升，影响盈利能力",
            "mitigation": "优化广告投放策略，增加自然流量和邮件营销占比，降低对付费广告的依赖",
        })

    risks.append({
        "type": "market",
        "level": "low",
        "description": "户外用品行业季节性波动，Q4 可能面临需求下降",
        "mitigation": "提前规划假日促销活动，拓展室内户外和冬季户外产品线",
    })

    return risks


def _generate_outlook(
    data: dict[str, Any],
    trends: dict[str, Any],
) -> dict[str, Any]:
    """生成下周展望"""
    key_metrics = data.get("key_metrics", {})
    current_revenue = key_metrics.get("total_revenue", {}).get("current", 0)
    growth_rate = key_metrics.get("total_revenue", {}).get("change_percent", 0) / 100

    # 保守预测
    conservative_forecast = current_revenue * (1 + growth_rate * 0.5)
    # 乐观预测
    optimistic_forecast = current_revenue * (1 + growth_rate * 1.2)

    return {
        "forecast": {
            "conservative_revenue": round(conservative_forecast, 2),
            "optimistic_revenue": round(optimistic_forecast, 2),
            "expected_orders": round(key_metrics.get("total_orders", {}).get("current", 0) * (1 + growth_rate * 0.7)),
        },
        "opportunities": [
            "扩大 Google Ads 和 Email Marketing 高 ROAS 渠道投入",
            "优化明星产品库存，防止断货",
            "实施退款原因分析，降低退款率",
        ],
        "challenges": [
            "广告 ROAS 下降趋势需要扭转",
            "退款率上升需要找到根本原因",
            "季节性需求变化需要提前应对",
        ],
        "focus_areas": ["退款率优化", "广告效率提升", "客户留存计划"],
    }


def get_report(report_id: str) -> dict[str, Any]:
    """获取周报详情"""
    report = _load_report(report_id)
    if not report:
        raise ValueError(f"Report not found: {report_id}")
    return report


def list_reports(limit: int = 20) -> dict[str, Any]:
    """获取周报列表"""
    _ensure_data_dir()

    reports = []
    for filename in sorted(os.listdir(DATA_DIR), reverse=True):
        if not filename.startswith("report_") or not filename.endswith(".json"):
            continue
        try:
            with open(os.path.join(DATA_DIR, filename), encoding="utf-8") as f:
                report = json.load(f)
                reports.append({
                    "id": report["id"],
                    "title": report["title"],
                    "period": report["period"],
                    "status": report["status"],
                    "generated_at": report["period"]["generated_at"],
                })
        except Exception as e:
            logger.warning("Failed to load report file %s: %s", filename, str(e))

        if len(reports) >= limit:
            break

    return {
        "reports": reports,
        "total": len(reports),
    }


def get_weekly_report_status() -> dict[str, Any]:
    """获取 AI 经营周报系统状态"""
    return {
        "status": "running",
        "features": [
            "auto_report_generation",
            "anomaly_detection",
            "trend_analysis",
            "ai_insights",
            "action_items",
            "executive_summary",
            "risk_identification",
            "next_week_outlook",
            "product_highlights",
            "marketing_performance",
            "customer_insights",
        ],
        "anomaly_types": [
            "refund_rate_high",
            "roas_decline",
            "margin_decline",
            "aov_decline",
        ],
        "severity_levels": ["critical", "warning", "info"],
        "note": "AI weekly business report system is ready. Supports automatic report generation, anomaly detection with root cause analysis, AI insights, and actionable recommendations.",
    }
