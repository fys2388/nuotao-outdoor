"""
成本模型服务
支持单订单落地成本与毛利测算
成本组成：产品成本 + 运费 + 关税 + 支付手续费 + 营销费用
"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, OrderItem

logger = logging.getLogger(__name__)

# 默认工作空间 ID
DEFAULT_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000001")

# 默认成本配置
DEFAULT_COST_CONFIG = {
    # 支付手续费（Stripe 标准费率）
    "payment_fee_rate": Decimal("0.029"),  # 2.9%
    "payment_fee_fixed": Decimal("0.30"),   # $0.30 每笔
    # 营销费用率（广告 + 平台佣金）
    "marketing_fee_rate": Decimal("0.15"),  # 15%
    # 默认运费（如果订单没有运费信息）
    "default_shipping_cost": Decimal("5.00"),
    # 默认关税率（如果没有具体国家的税率）
    "default_duty_rate": Decimal("0.05"),   # 5%
}

# 各国关税率（简化版，实际应按 HS 编码查询）
COUNTRY_DUTY_RATES = {
    "US": Decimal("0.00"),   # 美国：800 美元以下免税（de minimis）
    "DE": Decimal("0.19"),   # 德国：19% VAT（进口时征收）
    "FR": Decimal("0.20"),   # 法国：20% VAT
    "GB": Decimal("0.20"),   # 英国：20% VAT
    "CA": Decimal("0.05"),   # 加拿大：5% GST
    "AU": Decimal("0.10"),   # 澳大利亚：10% GST
    "ES": Decimal("0.21"),   # 西班牙：21% VAT
    "IT": Decimal("0.22"),   # 意大利：22% VAT
    "NL": Decimal("0.21"),   # 荷兰：21% VAT
    "PL": Decimal("0.23"),   # 波兰：23% VAT
    "SE": Decimal("0.25"),   # 瑞典：25% VAT
}

# 各国增值税起征点（低于此金额免税）
COUNTRY_VAT_THRESHOLD = {
    "US": Decimal("800.00"),    # 美国：$800
    "EU": Decimal("150.00"),    # 欧盟：€150（IOSS 适用范围）
    "GB": Decimal("135.00"),    # 英国：£135
    "CA": Decimal("20.00"),     # 加拿大：CAD 20
    "AU": Decimal("1000.00"),   # 澳大利亚：AUD 1000
}


def _round_decimal(value: Decimal, places: int = 2) -> Decimal:
    """四舍五入到指定小数位"""
    return value.quantize(Decimal(f"0.{'0' * places}"), rounding=ROUND_HALF_UP)


def calculate_order_cost(
    order_data: dict[str, Any],
    cost_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    计算单订单落地成本与毛利

    Args:
        order_data: 订单数据
            - order_id: 订单 ID
            - order_number: 订单号
            - total_amount: 订单总金额（含运费）
            - subtotal: 商品小计
            - shipping_cost: 运费（向客户收取的）
            - currency: 货币代码
            - country_code: 目的国家代码
            - items: 商品列表 [{product_id, name, quantity, unit_price, cost_price}]
            - payment_method: 支付方式
            - shipping_weight: 总重量（kg）
        cost_config: 成本配置（可选，使用默认值）

    Returns:
        成本明细和毛利分析
    """
    config = DEFAULT_COST_CONFIG.copy()
    if cost_config:
        config.update(cost_config)

    # 订单基本信息
    order_id = order_data.get("order_id", "unknown")
    order_number = order_data.get("order_number", "N/A")
    total_amount = Decimal(str(order_data.get("total_amount", 0)))
    subtotal = Decimal(str(order_data.get("subtotal", total_amount)))
    shipping_revenue = Decimal(str(order_data.get("shipping_cost", 0)))
    currency = order_data.get("currency", "USD")
    country_code = order_data.get("country_code", "US").upper()
    items = order_data.get("items", [])

    # ============================================
    # 1. 产品成本（采购成本）
    # ============================================
    product_cost = Decimal("0")
    for item in items:
        quantity = int(item.get("quantity", 1))
        cost_price = Decimal(str(item.get("cost_price", 0)))
        product_cost += cost_price * quantity

    # 如果没有提供成本价格，按售价的 40% 估算
    if product_cost == 0 and subtotal > 0:
        product_cost = subtotal * Decimal("0.40")
        logger.info("Order %s: No cost price provided, estimated at 40%% of subtotal", order_number)

    # ============================================
    # 2. 运费成本（国内 + 头程 + 尾程）
    # ============================================
    # 简化估算：按重量或按订单金额比例
    shipping_weight = Decimal(str(order_data.get("shipping_weight", 0)))
    if shipping_weight > 0:
        # 按重量估算：$5/kg 基础 + $2/kg 尾程
        shipping_cost = (shipping_weight * Decimal("5.00")) + (shipping_weight * Decimal("2.00"))
    else:
        # 按订单金额估算：10% + $3
        shipping_cost = (subtotal * Decimal("0.10")) + Decimal("3.00")

    shipping_cost = _round_decimal(shipping_cost)

    # ============================================
    # 3. 关税/增值税
    # ============================================
    duty_rate = COUNTRY_DUTY_RATES.get(country_code, config["default_duty_rate"])
    vat_threshold = COUNTRY_VAT_THRESHOLD.get(country_code, Decimal("0"))

    # 检查是否低于免税起征点
    is_duty_exempt = subtotal <= vat_threshold and vat_threshold > 0

    if is_duty_exempt:
        duty_amount = Decimal("0")
        duty_note = f"Below {currency} {vat_threshold} threshold, duty exempt"
    else:
        # 关税 = (产品成本 + 运费) * 关税率
        dutiable_value = product_cost + shipping_cost
        duty_amount = _round_decimal(dutiable_value * duty_rate)
        duty_note = f"Calculated at {float(duty_rate) * 100:.1f}% on dutiable value"

    # ============================================
    # 4. 支付手续费
    # ============================================
    payment_fee_rate = Decimal(str(config.get("payment_fee_rate", DEFAULT_COST_CONFIG["payment_fee_rate"])))
    payment_fee_fixed = Decimal(str(config.get("payment_fee_fixed", DEFAULT_COST_CONFIG["payment_fee_fixed"])))
    payment_fee = _round_decimal((total_amount * payment_fee_rate) + payment_fee_fixed)

    # ============================================
    # 5. 营销费用
    # ============================================
    marketing_fee_rate = Decimal(str(config.get("marketing_fee_rate", DEFAULT_COST_CONFIG["marketing_fee_rate"])))
    marketing_fee = _round_decimal(subtotal * marketing_fee_rate)

    # ============================================
    # 汇总成本
    # ============================================
    total_cost = product_cost + shipping_cost + duty_amount + payment_fee + marketing_fee
    total_cost = _round_decimal(total_cost)

    # ============================================
    # 毛利计算
    # ============================================
    gross_profit = total_amount - total_cost
    gross_profit = _round_decimal(gross_profit)
    gross_margin = (gross_profit / total_amount * 100) if total_amount > 0 else Decimal("0")
    gross_margin = _round_decimal(gross_margin, 1)

    # 成本占比
    cost_breakdown = {
        "product_cost": {
            "amount": float(product_cost),
            "percentage": float(_round_decimal(product_cost / total_cost * 100, 1)) if total_cost > 0 else 0,
            "description": "Product purchase cost",
        },
        "shipping_cost": {
            "amount": float(shipping_cost),
            "percentage": float(_round_decimal(shipping_cost / total_cost * 100, 1)) if total_cost > 0 else 0,
            "description": "Shipping & logistics (domestic + first leg + last leg)",
        },
        "duty_vat": {
            "amount": float(duty_amount),
            "percentage": float(_round_decimal(duty_amount / total_cost * 100, 1)) if total_cost > 0 else 0,
            "description": f"Import duty/VAT ({duty_note})",
        },
        "payment_fee": {
            "amount": float(payment_fee),
            "percentage": float(_round_decimal(payment_fee / total_cost * 100, 1)) if total_cost > 0 else 0,
            "description": f"Payment processing fee ({float(payment_fee_rate) * 100:.1f}% + {currency} {float(payment_fee_fixed):.2f})",
        },
        "marketing_fee": {
            "amount": float(marketing_fee),
            "percentage": float(_round_decimal(marketing_fee / total_cost * 100, 1)) if total_cost > 0 else 0,
            "description": f"Marketing & advertising ({float(marketing_fee_rate) * 100:.0f}% of subtotal)",
        },
    }

    # 盈利状态判断
    if gross_margin >= Decimal("30"):
        profit_status = "healthy"
        profit_note = "Healthy margin (>= 30%)"
    elif gross_margin >= Decimal("15"):
        profit_status = "acceptable"
        profit_note = "Acceptable margin (15-30%), consider optimization"
    elif gross_margin >= Decimal("0"):
        profit_status = "low"
        profit_note = "Low margin (< 15%), risk of loss after unexpected costs"
    else:
        profit_status = "loss"
        profit_note = "Loss-making order, immediate review required"

    return {
        "order_id": order_id,
        "order_number": order_number,
        "currency": currency,
        "country_code": country_code,
        "revenue": {
            "total_amount": float(total_amount),
            "subtotal": float(subtotal),
            "shipping_revenue": float(shipping_revenue),
        },
        "costs": {
            "total_cost": float(total_cost),
            "breakdown": cost_breakdown,
        },
        "profit": {
            "gross_profit": float(gross_profit),
            "gross_margin_percent": float(gross_margin),
            "status": profit_status,
            "note": profit_note,
        },
        "calculation_notes": {
            "duty_exempt": is_duty_exempt,
            "duty_rate_applied": float(duty_rate),
            "vat_threshold": float(vat_threshold),
            "estimated_costs": product_cost == Decimal(str(order_data.get("subtotal", 0))) * Decimal("0.40"),
            "timestamp": datetime.utcnow().isoformat(),
        },
    }


async def calculate_order_cost_from_db(
    session: AsyncSession,
    order_id: UUID,
    cost_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    从数据库读取订单并计算成本

    Args:
        session: 数据库会话
        order_id: 订单 ID（UUID）
        cost_config: 成本配置（可选）

    Returns:
        成本明细和毛利分析
    """
    # 查询订单
    order_result = await session.execute(
        select(Order).where(Order.id == order_id)
    )
    order = order_result.scalar_one_or_none()

    if not order:
        raise ValueError(f"Order not found: {order_id}")

    # 查询订单商品项
    items_result = await session.execute(
        select(OrderItem).where(OrderItem.order_id == order_id)
    )
    order_items = items_result.scalars().all()

    # 构建订单数据
    items_data = []
    for item in order_items:
        items_data.append({
            "product_id": str(item.product_id) if item.product_id else None,
            "name": item.product_name or "Unknown",
            "quantity": item.quantity,
            "unit_price": float(item.unit_price) if item.unit_price else 0,
            "cost_price": 0,  # 数据库中可能没有成本价，需要从产品表查询
        })

    order_data = {
        "order_id": str(order.id),
        "order_number": order.order_number or str(order.id),
        "total_amount": float(order.total_amount) if order.total_amount else 0,
        "subtotal": float(order.subtotal) if hasattr(order, "subtotal") and order.subtotal else float(order.total_amount or 0),
        "shipping_cost": float(order.shipping_cost) if hasattr(order, "shipping_cost") and order.shipping_cost else 0,
        "currency": order.currency or "USD",
        "country_code": order.shipping_country or "US",
        "items": items_data,
        "payment_method": order.payment_method or "unknown",
    }

    return calculate_order_cost(order_data, cost_config)


def get_cost_model_status() -> dict[str, Any]:
    """获取成本模型状态和配置"""
    return {
        "status": "running",
        "cost_components": [
            "product_cost",
            "shipping_cost",
            "duty_vat",
            "payment_fee",
            "marketing_fee",
        ],
        "default_config": {
            "payment_fee_rate": float(DEFAULT_COST_CONFIG["payment_fee_rate"]),
            "payment_fee_fixed": float(DEFAULT_COST_CONFIG["payment_fee_fixed"]),
            "marketing_fee_rate": float(DEFAULT_COST_CONFIG["marketing_fee_rate"]),
            "default_shipping_cost": float(DEFAULT_COST_CONFIG["default_shipping_cost"]),
            "default_duty_rate": float(DEFAULT_COST_CONFIG["default_duty_rate"]),
        },
        "supported_countries": list(COUNTRY_DUTY_RATES.keys()),
        "profit_thresholds": {
            "healthy": ">= 30%",
            "acceptable": "15-30%",
            "low": "0-15%",
            "loss": "< 0%",
        },
        "note": "Cost model supports single-order landing cost and gross margin calculation. Costs include product, shipping, duty/VAT, payment fees, and marketing.",
    }
