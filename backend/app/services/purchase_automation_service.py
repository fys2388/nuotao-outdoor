"""
采购自动化服务
支持采购规则配置、按规则自动生成采购单、异常检测、人工介入
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.supply_chain import PurchaseOrder, PurchaseOrderItem

logger = logging.getLogger(__name__)

# 默认工作空间 ID
DEFAULT_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000001")

# 默认采购规则
DEFAULT_PURCHASE_RULES = {
    "auto_purchase_enabled": False,  # 默认关闭自动采购
    "min_stock_threshold": 10,       # 最低库存阈值
    "default_purchase_quantity": 50, # 默认采购数量
    "max_purchase_amount": Decimal("5000.00"),  # 单次采购最大金额
    "cost_variance_threshold": Decimal("0.20"),  # 成本波动阈值（20%）
    "require_approval_above": Decimal("1000.00"),  # 超过此金额需要审批
    "supplier_blacklist": [],  # 供应商黑名单
    "auto_approve_low_value": True,  # 低价值采购单自动审批
}

# 异常类型
ANOMALY_TYPES = [
    "cost_spike",           # 成本激增
    "supplier_blacklisted", # 供应商在黑名单
    "quantity_abnormal",    # 数量异常
    "amount_exceeds_limit", # 金额超限
    "no_supplier",          # 无供应商
    "stock_negative",       # 库存负数
]


def _round_decimal(value: Decimal, places: int = 2) -> Decimal:
    """四舍五入到指定小数位"""
    return value.quantize(Decimal(f"0.{'0' * places}"))


def load_purchase_rules() -> dict[str, Any]:
    """
    加载采购规则

    从配置文件或数据库加载，这里使用默认值 + 可覆盖的配置文件
    """
    rules = DEFAULT_PURCHASE_RULES.copy()

    # 尝试从配置文件加载
    try:
        import os
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "purchase_rules.json",
        )
        if os.path.exists(config_path):
            with open(config_path, encoding="utf-8") as f:
                saved_rules = json.load(f)
                rules.update(saved_rules)
                logger.info("Purchase rules loaded from %s", config_path)
    except Exception as e:
        logger.warning("Failed to load purchase rules from file: %s", str(e))

    # 转换 Decimal 类型
    for key in ["max_purchase_amount", "cost_variance_threshold", "require_approval_above"]:
        if key in rules and not isinstance(rules[key], Decimal):
            rules[key] = Decimal(str(rules[key]))

    return rules


def save_purchase_rules(rules: dict[str, Any]) -> None:
    """
    保存采购规则到配置文件
    """
    try:
        import os
        data_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
        )
        os.makedirs(data_dir, exist_ok=True)
        config_path = os.path.join(data_dir, "purchase_rules.json")

        # 转换 Decimal 为字符串
        serializable_rules = {}
        for key, value in rules.items():
            if isinstance(value, Decimal):
                serializable_rules[key] = str(value)
            else:
                serializable_rules[key] = value

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(serializable_rules, f, indent=2, ensure_ascii=False)

        logger.info("Purchase rules saved to %s", config_path)
    except Exception as e:
        logger.error("Failed to save purchase rules: %s", str(e))
        raise


def detect_anomalies(
    product: Product,
    quantity: int,
    unit_cost: Decimal,
    supplier_id: str | None = None,
    rules: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    检测采购异常

    Args:
        product: 产品对象
        quantity: 采购数量
        unit_cost: 单位成本
        supplier_id: 供应商 ID
        rules: 采购规则

    Returns:
        异常列表
    """
    if rules is None:
        rules = load_purchase_rules()

    anomalies = []

    # 1. 检查数量异常
    if quantity <= 0:
        anomalies.append({
            "type": "quantity_abnormal",
            "severity": "critical",
            "message": f"采购数量异常: {quantity}（必须大于 0）",
            "blocking": True,
        })
    elif quantity > 1000:
        anomalies.append({
            "type": "quantity_abnormal",
            "severity": "warning",
            "message": f"采购数量较大: {quantity}（建议人工审核）",
            "blocking": False,
        })

    # 2. 检查成本异常（与产品成本对比）
    if hasattr(product, "cost") and product.cost and hasattr(product.cost, "purchase_cost"):
        historical_cost = product.cost.purchase_cost
        if historical_cost and historical_cost > 0:
            cost_variance = abs(unit_cost - historical_cost) / historical_cost
            if cost_variance > rules["cost_variance_threshold"]:
                direction = "上涨" if unit_cost > historical_cost else "下降"
                anomalies.append({
                    "type": "cost_spike",
                    "severity": "warning",
                    "message": f"成本{direction}: 历史成本 ${historical_cost}, 当前成本 ${unit_cost}, 波动 {float(cost_variance) * 100:.1f}%",
                    "blocking": False,
                    "historical_cost": float(historical_cost),
                    "current_cost": float(unit_cost),
                    "variance_percent": float(cost_variance) * 100,
                })

    # 3. 检查金额超限
    total_amount = unit_cost * Decimal(str(quantity))
    if total_amount > rules["max_purchase_amount"]:
        anomalies.append({
            "type": "amount_exceeds_limit",
            "severity": "critical",
            "message": f"采购金额超限: ${total_amount}（最大限制 ${rules['max_purchase_amount']}）",
            "blocking": True,
        })

    # 4. 检查供应商黑名单
    if supplier_id and supplier_id in rules.get("supplier_blacklist", []):
        anomalies.append({
            "type": "supplier_blacklisted",
            "severity": "critical",
            "message": f"供应商在黑名单中: {supplier_id}",
            "blocking": True,
        })

    # 5. 检查无供应商
    if not supplier_id:
        anomalies.append({
            "type": "no_supplier",
            "severity": "info",
            "message": "未指定供应商（建议补充供应商信息）",
            "blocking": False,
        })

    return anomalies


async def auto_generate_purchase_order(
    session: AsyncSession,
    product_id: UUID,
    quantity: int | None = None,
    unit_cost: Decimal | None = None,
    supplier_id: str | None = None,
    workspace_id: UUID | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """
    自动生成采购单（带异常检测和人工介入）

    Args:
        session: 数据库会话
        product_id: 产品 ID
        quantity: 采购数量（如果不提供，使用默认值）
        unit_cost: 单位成本（如果不提供，使用产品成本）
        supplier_id: 供应商 ID
        workspace_id: 工作空间 ID
        trace_id: 追踪 ID

    Returns:
        采购单生成结果（包含异常信息和审批状态）
    """
    if workspace_id is None:
        workspace_id = DEFAULT_WORKSPACE_ID

    rules = load_purchase_rules()

    # 检查自动采购是否启用
    if not rules["auto_purchase_enabled"]:
        return {
            "success": False,
            "blocked": True,
            "reason": "auto_purchase_disabled",
            "message": "自动采购功能未启用，请在采购规则中启用 auto_purchase_enabled",
            "rules": {k: str(v) if isinstance(v, Decimal) else v for k, v in rules.items()},
        }

    # 查询产品（预加载 cost 关系，避免异步懒加载问题）
    from sqlalchemy.orm import selectinload
    product_query = (
        select(Product)
        .where(Product.id == product_id)
        .options(selectinload(Product.cost))
    )
    product_result = await session.execute(product_query)
    product = product_result.scalar_one_or_none()

    if not product:
        raise ValueError(f"Product not found: {product_id}")

    # 使用默认数量
    if quantity is None:
        quantity = rules["default_purchase_quantity"]

    # 使用产品成本
    if unit_cost is None:
        if hasattr(product, "cost") and product.cost and hasattr(product.cost, "purchase_cost"):
            unit_cost = product.cost.purchase_cost
        else:
            unit_cost = Decimal("10.00")  # 默认成本

    # 异常检测
    anomalies = detect_anomalies(product, quantity, unit_cost, supplier_id, rules)

    # 检查是否有阻塞性异常
    blocking_anomalies = [a for a in anomalies if a.get("blocking")]
    if blocking_anomalies:
        return {
            "success": False,
            "blocked": True,
            "reason": "anomalies_detected",
            "message": "检测到阻塞性异常，采购单未生成，需要人工介入",
            "product": {
                "id": str(product.id),
                "name": product.name,
                "sku": product.sku,
            },
            "quantity": quantity,
            "unit_cost": float(unit_cost),
            "total_amount": float(unit_cost * Decimal(str(quantity))),
            "anomalies": anomalies,
            "required_action": "请人工审核异常情况，修正后重新生成采购单",
        }

    # 检查是否需要审批
    total_amount = unit_cost * Decimal(str(quantity))
    requires_approval = total_amount > rules["require_approval_above"]

    # 确定采购单状态
    if requires_approval:
        po_status = "pending_approval"
        auto_approved = False
    elif rules["auto_approve_low_value"]:
        po_status = "approved"
        auto_approved = True
    else:
        po_status = "draft"
        auto_approved = False

    # 创建采购单（使用时间戳+随机数避免冲突）
    import random
    po_number = f"PO-AUTO-{int(time.time())}-{random.randint(1000, 9999)}"
    purchase_order = PurchaseOrder(
        workspace_id=workspace_id,
        po_number=po_number,
        supplier_id=supplier_id,
        status=po_status,
        subtotal=total_amount,
        shipping_cost=Decimal("0"),
        total=total_amount,
        currency="USD",
        expected_delivery_at=datetime.utcnow() + timedelta(days=14),
        notes=f"Auto-generated by purchase automation. Anomalies: {len(anomalies)}",
        trace_id=trace_id,
    )
    session.add(purchase_order)
    await session.flush()

    # 创建采购单商品项
    po_item = PurchaseOrderItem(
        workspace_id=workspace_id,
        purchase_order_id=purchase_order.id,
        product_id=product_id,
        sku=product.sku,
        name=product.name,
        quantity=quantity,
        unit_cost=unit_cost,
        line_total=total_amount,
    )
    session.add(po_item)
    await session.flush()

    logger.info(
        "Purchase order auto-generated: id=%s, po_number=%s, product=%s, quantity=%d, amount=%.2f, status=%s, auto_approved=%s, anomalies=%d",
        purchase_order.id,
        purchase_order.po_number,
        product.name,
        quantity,
        float(total_amount),
        po_status,
        auto_approved,
        len(anomalies),
    )

    return {
        "success": True,
        "blocked": False,
        "purchase_order": {
            "id": str(purchase_order.id),
            "po_number": purchase_order.po_number,
            "status": po_status,
            "total_amount": float(total_amount),
            "auto_approved": auto_approved,
            "requires_approval": requires_approval,
        },
        "product": {
            "id": str(product.id),
            "name": product.name,
            "sku": product.sku,
        },
        "quantity": quantity,
        "unit_cost": float(unit_cost),
        "anomalies": anomalies,
        "message": "采购单已自动生成" + ("，需要人工审批" if requires_approval else "，已自动审批" if auto_approved else "，待处理"),
    }


def get_purchase_automation_status() -> dict[str, Any]:
    """获取采购自动化系统状态"""
    rules = load_purchase_rules()
    return {
        "status": "running",
        "auto_purchase_enabled": rules["auto_purchase_enabled"],
        "rules": {k: str(v) if isinstance(v, Decimal) else v for k, v in rules.items()},
        "anomaly_types": ANOMALY_TYPES,
        "workflow": "Check rules → Detect anomalies → Generate PO → Auto-approve low value → Pending approval for high value → Human review for anomalies",
        "note": "Purchase automation system is ready. Supports rule-based auto purchase, anomaly detection, and human-in-the-loop approval.",
    }
