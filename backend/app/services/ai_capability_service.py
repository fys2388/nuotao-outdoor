"""
AI能力深化服务
包含：选品模型、客服自动回复、动态定价
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "ai_capability",
)


def _ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


# ========== 选品模型 ==========

def run_sourcing_model(
    product_name: str,
    category: str = "",
    price: float = 0,
    cost: float = 0,
    competition_level: str = "medium",
    market_demand: str = "medium",
    seasonality: str = "year-round",
) -> dict[str, Any]:
    """
    运行选品模型，评估产品的市场潜力和盈利能力

    评分维度：
    - 市场需求 (0-100)
    - 竞争程度 (0-100，越低越好)
    - 利润空间 (0-100)
    - 季节性适配 (0-100)
    - 供应链稳定性 (0-100)
    """
    # 基础评分
    demand_score = {"low": 40, "medium": 65, "high": 85}.get(market_demand, 65)
    competition_score = {"low": 85, "medium": 60, "high": 35}.get(competition_level, 60)

    # 利润空间计算
    if price > 0 and cost > 0:
        profit_margin = (price - cost) / price * 100
        profit_score = min(100, max(0, profit_margin * 1.5))
    else:
        profit_margin = 0
        profit_score = 50

    # 季节性适配
    season_score = {"year-round": 90, "seasonal": 70, "holiday": 60}.get(seasonality, 70)

    # 供应链稳定性（基于品类的简化评估）
    supply_score = 70 if category in ["electronics", "outdoor", "home"] else 60

    # 综合评分（加权平均）
    weights = {
        "demand": 0.25,
        "competition": 0.20,
        "profit": 0.25,
        "season": 0.15,
        "supply": 0.15,
    }
    total_score = (
        demand_score * weights["demand"] +
        competition_score * weights["competition"] +
        profit_score * weights["profit"] +
        season_score * weights["season"] +
        supply_score * weights["supply"]
    )

    # 决策建议
    if total_score >= 75:
        recommendation = "强烈推荐上架"
        action = "priority_listing"
    elif total_score >= 60:
        recommendation = "推荐上架，需优化"
        action = "list_with_optimization"
    elif total_score >= 45:
        recommendation = "谨慎考虑，需进一步调研"
        action = "further_research"
    else:
        recommendation = "不推荐上架"
        action = "reject"

    result = {
        "id": str(uuid4()),
        "product_name": product_name,
        "category": category,
        "price": price,
        "cost": cost,
        "profit_margin": round(profit_margin, 2),
        "scores": {
            "market_demand": demand_score,
            "competition": competition_score,
            "profit_space": round(profit_score, 1),
            "seasonality": season_score,
            "supply_chain": supply_score,
        },
        "total_score": round(total_score, 1),
        "recommendation": recommendation,
        "action": action,
        "created_at": datetime.utcnow().isoformat(),
    }

    # 保存结果
    _ensure_data_dir()
    path = os.path.join(DATA_DIR, f"sourcing_{result['id']}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("Failed to save sourcing result: %s", str(e))

    return result


# ========== 客服自动回复 ==========

def generate_customer_reply(
    customer_message: str,
    order_id: str = "",
    customer_name: str = "",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    生成客服自动回复

    支持的场景：
    - 订单查询
    - 物流查询
    - 退货退款
    - 产品咨询
    - 投诉建议
    """
    message_lower = customer_message.lower()

    # 场景识别
    if any(kw in message_lower for kw in ["订单", "order", "下单", "购买"]):
        scenario = "order_inquiry"
        template = "您好{name}！感谢您的咨询。关于您的订单{order_id}，我们正在为您查询详细信息。您可以在订单详情页查看最新状态，如有其他问题请随时联系我们。"
    elif any(kw in message_lower for kw in ["物流", "快递", "shipping", "tracking", "发货", "配送"]):
        scenario = "shipping_inquiry"
        template = "您好{name}！您的订单{order_id}已发货，物流信息正在更新中。通常国际配送需要7-15个工作日，您可以通过物流单号实时追踪包裹状态。如有延误我们会及时通知您。"
    elif any(kw in message_lower for kw in ["退货", "退款", "return", "refund", "换货"]):
        scenario = "return_refund"
        template = "您好{name}！很抱歉给您带来不便。关于您的退货退款请求，我们已为您记录。请您提供订单号{order_id}和问题描述，我们将在24小时内处理您的申请。"
    elif any(kw in message_lower for kw in ["产品", "商品", "product", "尺寸", "规格", "材质"]):
        scenario = "product_inquiry"
        template = "您好{name}！感谢您对我们产品的关注。关于您咨询的产品问题，我们的产品均经过严格质检，提供详细的规格说明。如需更多信息请查看产品详情页，或告诉我们您的具体需求。"
    elif any(kw in message_lower for kw in ["投诉", "抱怨", "complain", "问题", "差评", "不满意"]):
        scenario = "complaint"
        template = "您好{name}！非常抱歉给您带来不好的体验。我们非常重视您的反馈，已将您的问题记录并转交相关部门处理。我们会在24小时内给您满意的答复，请您耐心等待。"
    else:
        scenario = "general"
        template = "您好{name}！感谢您的咨询。我们已收到您的消息，客服团队会尽快为您解答。如有紧急问题，请提供订单号{order_id}，我们会优先处理。"

    # 填充模板
    reply = template.format(
        name=customer_name or "尊敬的客户",
        order_id=order_id or "（请提供订单号）",
    )

    # 置信度评分
    confidence = {
        "order_inquiry": 0.85,
        "shipping_inquiry": 0.82,
        "return_refund": 0.78,
        "product_inquiry": 0.75,
        "complaint": 0.70,
        "general": 0.60,
    }.get(scenario, 0.60)

    # 是否需要人工审核
    needs_human_review = confidence < 0.75 or scenario == "complaint"

    result = {
        "id": str(uuid4()),
        "customer_message": customer_message,
        "scenario": scenario,
        "reply": reply,
        "confidence": confidence,
        "needs_human_review": needs_human_review,
        "order_id": order_id,
        "customer_name": customer_name,
        "created_at": datetime.utcnow().isoformat(),
    }

    # 保存结果
    _ensure_data_dir()
    path = os.path.join(DATA_DIR, f"reply_{result['id']}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("Failed to save reply: %s", str(e))

    return result


# ========== 动态定价 ==========

def calculate_dynamic_price(
    product_id: str,
    base_price: float,
    cost: float,
    current_inventory: int,
    sales_velocity: float = 0,  # 每日销量
    competitor_price: float = 0,
    demand_level: str = "medium",
    season_factor: float = 1.0,
) -> dict[str, Any]:
    """
    计算动态定价建议

    定价策略：
    - 基础价格：成本 + 目标利润
    - 库存调整：库存低时涨价，库存高时降价
    - 销量调整：销量高时涨价，销量低时降价
    - 竞争调整：参考竞品价格
    - 需求调整：需求高时涨价
    - 季节调整：旺季涨价，淡季降价
    """
    # 目标利润率（40%）
    target_margin = 0.40
    target_price = cost / (1 - target_margin)

    # 库存系数
    if current_inventory < 10:
        inventory_factor = 1.10  # 库存低，涨价10%
    elif current_inventory < 50:
        inventory_factor = 1.05
    elif current_inventory > 200:
        inventory_factor = 0.90  # 库存高，降价10%
    else:
        inventory_factor = 1.00

    # 销量系数
    if sales_velocity > 10:
        velocity_factor = 1.08  # 销量高，涨价8%
    elif sales_velocity > 5:
        velocity_factor = 1.04
    elif sales_velocity < 1:
        velocity_factor = 0.92  # 销量低，降价8%
    else:
        velocity_factor = 1.00

    # 竞争系数
    if competitor_price > 0:
        if base_price > competitor_price * 1.15:
            competition_factor = 0.95  # 比竞品高15%以上，降价5%
        elif base_price < competitor_price * 0.85:
            competition_factor = 1.05  # 比竞品低15%以上，涨价5%
        else:
            competition_factor = 1.00
    else:
        competition_factor = 1.00

    # 需求系数
    demand_factor = {"low": 0.92, "medium": 1.00, "high": 1.08}.get(demand_level, 1.00)

    # 综合计算
    suggested_price = base_price * inventory_factor * velocity_factor * competition_factor * demand_factor * season_factor

    # 价格下限（成本 + 10%利润）
    min_price = cost * 1.10
    # 价格上限（基础价格 + 30%）
    max_price = base_price * 1.30

    # 限制价格范围
    suggested_price = max(min_price, min(max_price, suggested_price))

    # 利润计算
    expected_profit = suggested_price - cost
    expected_margin = (expected_profit / suggested_price * 100) if suggested_price > 0 else 0

    # 定价建议
    if suggested_price > base_price * 1.05:
        action = "increase_price"
        recommendation = f"建议涨价至 ${suggested_price:.2f}（+{(suggested_price/base_price-1)*100:.1f}%）"
    elif suggested_price < base_price * 0.95:
        action = "decrease_price"
        recommendation = f"建议降价至 ${suggested_price:.2f}（{(suggested_price/base_price-1)*100:.1f}%）"
    else:
        action = "maintain_price"
        recommendation = f"建议维持当前价格 ${base_price:.2f}"

    result = {
        "id": str(uuid4()),
        "product_id": product_id,
        "base_price": base_price,
        "cost": cost,
        "current_inventory": current_inventory,
        "sales_velocity": sales_velocity,
        "competitor_price": competitor_price,
        "factors": {
            "inventory_factor": inventory_factor,
            "velocity_factor": velocity_factor,
            "competition_factor": competition_factor,
            "demand_factor": demand_factor,
            "season_factor": season_factor,
        },
        "suggested_price": round(suggested_price, 2),
        "expected_profit": round(expected_profit, 2),
        "expected_margin": round(expected_margin, 2),
        "price_range": {
            "min": round(min_price, 2),
            "max": round(max_price, 2),
        },
        "action": action,
        "recommendation": recommendation,
        "created_at": datetime.utcnow().isoformat(),
    }

    # 保存结果
    _ensure_data_dir()
    path = os.path.join(DATA_DIR, f"pricing_{result['id']}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("Failed to save pricing result: %s", str(e))

    return result


# ========== 系统状态 ==========

def get_ai_capability_status() -> dict[str, Any]:
    """获取AI能力深化系统状态"""
    return {
        "status": "ready",
        "version": "1.0.0",
        "capabilities": {
            "sourcing_model": {
                "enabled": True,
                "description": "AI选品模型，评估产品市场潜力和盈利能力",
                "dimensions": ["市场需求", "竞争程度", "利润空间", "季节性", "供应链"],
            },
            "customer_auto_reply": {
                "enabled": True,
                "description": "客服自动回复，支持订单查询、物流查询、退货退款等场景",
                "scenarios": ["订单查询", "物流查询", "退货退款", "产品咨询", "投诉建议", "通用"],
                "human_review_threshold": 0.75,
            },
            "dynamic_pricing": {
                "enabled": True,
                "description": "动态定价，基于库存、销量、竞争、需求、季节等因素自动调整价格",
                "factors": ["库存", "销量", "竞争", "需求", "季节"],
                "target_margin": "40%",
            },
        },
        "data_dir": DATA_DIR,
        "last_updated": datetime.utcnow().isoformat(),
    }
