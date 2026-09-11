"""
采购/发货服务
订单支付成功后自动生成采购单，支持物流号回填和发货状态管理
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order
from app.models.product import Product, ProductCost
from app.models.supply_chain import PurchaseOrder, PurchaseOrderItem
from app.core.config import get_settings

logger = logging.getLogger(__name__)

# 默认工作空间 ID
DEFAULT_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000001")

# 采购单状态流转
PO_STATUS_FLOW = {
    "draft": ["approved", "cancelled"],
    "approved": ["ordered", "cancelled"],
    "ordered": ["partial_received", "received", "shipped"],
    "partial_received": ["received"],
    "received": ["shipped"],
    "shipped": ["delivered", "completed"],
    "delivered": ["completed"],
    "completed": [],
    "cancelled": [],
}


def _safe_decimal(value: Any, default: float = 0.0) -> Decimal:
    """安全转换为 Decimal"""
    try:
        if value is None or value == "":
            return Decimal(str(default))
        return Decimal(str(value))
    except (ValueError, TypeError):
        return Decimal(str(default))


def generate_po_number(order_id: str) -> str:
    """生成采购单号"""
    timestamp = int(time.time())
    return f"PO-{order_id}-{timestamp}"


async def _get_product_cost(
    session: AsyncSession,
    order_item: "OrderItem",
    workspace_id: UUID,
) -> tuple[Decimal, Decimal]:
    """
    获取订单商品的采购成本和国内运费。

    优先级：
    1. 通过 order_item.product_id 关联 ProductCost 表（权威来源）
    2. 通过 SKU 查找 Product 再关联 ProductCost
    3. 兜底：使用配置的默认成本比例 × 售价

    Returns:
        (unit_purchase_cost, domestic_shipping_per_unit)
    """
    settings = get_settings()
    fallback_ratio = settings.procurement_fallback_cost_ratio
    default_domestic_shipping = settings.procurement_default_domestic_shipping

    unit_price = order_item.unit_price if order_item.unit_price else Decimal("0")
    product_id = getattr(order_item, "product_id", None)
    sku = getattr(order_item, "sku", None)

    # 1. 通过 product_id 直接查找
    if product_id:
        result = await session.execute(
            select(ProductCost).where(
                ProductCost.product_id == product_id,
                ProductCost.workspace_id == workspace_id,
            )
        )
        cost = result.scalar_one_or_none()
        if cost:
            purchase_cost = cost.purchase_cost if cost.purchase_cost > 0 else unit_price * fallback_ratio
            domestic = cost.domestic_shipping if cost.domestic_shipping > 0 else default_domestic_shipping
            logger.info("Product cost from ProductCost table: product_id=%s, cost=%s", product_id, purchase_cost)
            return purchase_cost, domestic

    # 2. 通过 SKU 查找 Product 再关联成本
    if sku:
        result = await session.execute(
            select(Product).where(
                Product.sku == sku,
                Product.workspace_id == workspace_id,
            )
        )
        product = result.scalar_one_or_none()
        if product and product.cost:
            cost = product.cost
            purchase_cost = cost.purchase_cost if cost.purchase_cost > 0 else unit_price * fallback_ratio
            domestic = cost.domestic_shipping if cost.domestic_shipping > 0 else default_domestic_shipping
            logger.info("Product cost via SKU lookup: sku=%s, cost=%s", sku, purchase_cost)
            return purchase_cost, domestic

    # 3. 兜底：配置的默认成本比例
    fallback_cost = unit_price * fallback_ratio
    logger.warning(
        "No ProductCost found for order_item=%s (product_id=%s, sku=%s), using fallback ratio=%s, cost=%s",
        getattr(order_item, "id", "unknown"), product_id, sku, fallback_ratio, fallback_cost,
    )
    return fallback_cost, default_domestic_shipping


async def _get_product_cost_detailed(
    session: AsyncSession,
    order_item: "OrderItem",
    workspace_id: UUID,
) -> dict[str, Any]:
    """
    获取订单商品的采购成本，附带来源和置信度。

    Returns:
        dict with keys:
        - purchase_cost: Decimal
        - domestic_shipping: Decimal
        - source: "product_cost" (real) | "fallback" (estimate, NOT for execution)
        - confidence: Decimal (0.0-1.0), fallback must be < 0.5
        - has_real_cost: bool
    """
    settings = get_settings()
    fallback_ratio = settings.procurement_fallback_cost_ratio
    default_domestic_shipping = settings.procurement_default_domestic_shipping

    unit_price = order_item.unit_price if order_item.unit_price else Decimal("0")
    product_id = getattr(order_item, "product_id", None)
    sku = getattr(order_item, "sku", None)

    # 1. 通过 product_id 直接查找
    if product_id:
        result = await session.execute(
            select(ProductCost).where(
                ProductCost.product_id == product_id,
                ProductCost.workspace_id == workspace_id,
            )
        )
        cost = result.scalar_one_or_none()
        if cost and cost.purchase_cost > 0:
            domestic = cost.domestic_shipping if cost.domestic_shipping > 0 else default_domestic_shipping
            logger.info("Product cost from ProductCost table: product_id=%s, cost=%s", product_id, cost.purchase_cost)
            return {
                "purchase_cost": cost.purchase_cost,
                "domestic_shipping": domestic,
                "source": "product_cost",
                "confidence": Decimal("0.95"),
                "has_real_cost": True,
            }

    # 2. 通过 SKU 查找 Product 再关联成本
    if sku:
        result = await session.execute(
            select(Product).where(
                Product.sku == sku,
                Product.workspace_id == workspace_id,
            )
        )
        product = result.scalar_one_or_none()
        if product and product.cost and product.cost.purchase_cost > 0:
            cost = product.cost
            domestic = cost.domestic_shipping if cost.domestic_shipping > 0 else default_domestic_shipping
            logger.info("Product cost via SKU lookup: sku=%s, cost=%s", sku, cost.purchase_cost)
            return {
                "purchase_cost": cost.purchase_cost,
                "domestic_shipping": domestic,
                "source": "product_cost",
                "confidence": Decimal("0.90"),
                "has_real_cost": True,
            }

    # 3. 兜底：配置的默认成本比例 (estimate ONLY, not for execution)
    fallback_cost = unit_price * fallback_ratio
    logger.warning(
        "No ProductCost found for order_item=%s (product_id=%s, sku=%s), using FALLBACK ratio=%s, cost=%s (ESTIMATE ONLY)",
        getattr(order_item, "id", "unknown"), product_id, sku, fallback_ratio, fallback_cost,
    )
    return {
        "purchase_cost": fallback_cost,
        "domestic_shipping": default_domestic_shipping,
        "source": "fallback",
        "confidence": Decimal("0.30"),
        "has_real_cost": False,
    }


async def create_purchase_order_from_order(
    session: AsyncSession,
    order: Order,
    wc_order_data: dict[str, Any] | None = None,
    workspace_id: UUID | None = None,
    trace_id: str | None = None,
) -> tuple[PurchaseOrder, bool]:
    """
    从订单创建采购单

    Args:
        session: 数据库会话
        order: 本地订单
        wc_order_data: WooCommerce 订单数据（包含商品详情）
        workspace_id: 工作空间 ID
        trace_id: 追踪 ID

    Returns:
        (采购单对象, 是否新建)
    """
    if workspace_id is None:
        workspace_id = DEFAULT_WORKSPACE_ID

    # Reload order with items using selectinload to avoid lazy-load in async context
    order_result = await session.execute(
        select(Order).options(selectinload(Order.items)).where(Order.id == order.id)
    )
    order = order_result.scalar_one()

    # 检查是否已存在采购单
    existing_po = await session.execute(
        select(PurchaseOrder).where(
            PurchaseOrder.workspace_id == workspace_id,
            PurchaseOrder.notes.contains(f"order_id={order.external_order_id}"),
        )
    )
    existing = existing_po.scalar_one_or_none()
    if existing:
        logger.info("Purchase order already exists for order %s: po=%s", order.external_order_id, existing.po_number)
        return existing, False

    # 生成采购单号
    po_number = generate_po_number(order.external_order_id)

    # 计算采购成本：优先从 ProductCost 表获取每个商品的实际成本
    # 汇总所有商品的采购成本 + 国内运费
    # M0-M4.1: 成本缺失时采购单进入 pending_cost_confirmation，不得执行
    subtotal = Decimal("0")
    total_domestic_shipping = Decimal("0")
    item_costs: list[tuple["OrderItem", Decimal, Decimal]] = []
    all_items_have_real_cost = True
    cost_sources: list[str] = []
    min_confidence = Decimal("1.0")
    missing_cost_items: list[str] = []

    for order_item in order.items:
        cost_detail = await _get_product_cost_detailed(session, order_item, workspace_id)
        unit_cost = cost_detail["purchase_cost"]
        domestic_shipping = cost_detail["domestic_shipping"]
        quantity = order_item.quantity
        line_cost = unit_cost * quantity
        subtotal += line_cost
        total_domestic_shipping += domestic_shipping * quantity
        item_costs.append((order_item, unit_cost, domestic_shipping))

        cost_sources.append(cost_detail["source"])
        if cost_detail["confidence"] < min_confidence:
            min_confidence = cost_detail["confidence"]
        if not cost_detail["has_real_cost"]:
            all_items_have_real_cost = False
            missing_cost_items.append(getattr(order_item, "sku", str(getattr(order_item, "id", "unknown"))))

    # 如果订单没有商品项（异常情况），使用兜底比例 (estimate ONLY)
    if not order.items:
        settings = get_settings()
        subtotal = order.total * settings.procurement_fallback_cost_ratio
        total_domestic_shipping = settings.procurement_default_domestic_shipping
        all_items_have_real_cost = False
        min_confidence = Decimal("0.30")
        cost_sources = ["fallback"]
        missing_cost_items = ["NO_ITEMS"]
        logger.warning("Order %s has no items, using FALLBACK cost calculation (ESTIMATE ONLY)", order.external_order_id)

    shipping_cost = total_domestic_shipping
    total = subtotal + shipping_cost

    # Determine PO status and cost confirmation
    # M0-M4.1: cost missing -> pending_cost_confirmation, cannot be approved/ordered
    if all_items_have_real_cost:
        po_status = "draft"
        cost_confirmed = True
        cost_source = "product_cost"
        cost_block_reason = None
    else:
        po_status = "pending_cost_confirmation"
        cost_confirmed = False
        cost_source = "fallback" if "fallback" in cost_sources else "unknown"
        cost_block_reason = f"Missing real ProductCost for items: {', '.join(missing_cost_items[:5])}. Fallback ratio is ESTIMATE ONLY, not for execution."
        logger.warning(
            "PO for order %s entering pending_cost_confirmation: missing cost for %d items",
            order.external_order_id, len(missing_cost_items),
        )

    # 创建采购单
    purchase_order = PurchaseOrder(
        workspace_id=workspace_id,
        po_number=po_number,
        supplier_id=None,  # 待分配供应商
        status=po_status,
        currency=order.currency,
        subtotal=subtotal,
        shipping_cost=shipping_cost,
        total=total,
        expected_delivery_at=datetime.utcnow() + timedelta(days=7),
        notes=f"Auto-generated from order_id={order.external_order_id}, trace_id={trace_id or 'N/A'}",
        trace_id=trace_id,
        cost_confirmed=cost_confirmed,
        cost_source=cost_source,
        cost_confidence=min_confidence,
        cost_block_reason=cost_block_reason,
    )
    session.add(purchase_order)
    await session.flush()

    # 创建采购单商品项（统一使用从 ProductCost 表获取的实际成本）
    for order_item, unit_cost, _domestic_shipping in item_costs:
        quantity = order_item.quantity
        line_total = unit_cost * quantity

        po_item = PurchaseOrderItem(
            purchase_order_id=purchase_order.id,
            workspace_id=workspace_id,
            product_id=getattr(order_item, "product_id", None),
            sku=order_item.sku or f"SKU-{getattr(order_item, 'id', 'unknown')}",
            name=order_item.name,
            quantity=quantity,
            unit_cost=unit_cost,
            line_total=line_total,
        )
        session.add(po_item)

    # 如果 wc_order_data 提供了额外的商品信息（如外部 SKU 映射），记录到 notes
    if wc_order_data and wc_order_data.get("line_items"):
        external_skus = [
            item.get("sku", "") for item in wc_order_data["line_items"] if item.get("sku")
        ]
        if external_skus:
            purchase_order.notes += f"; external_skus={','.join(external_skus)}"

    await session.flush()

    logger.info(
        "Purchase order created: po=%s, order=%s, total=%s, items=%d, trace=%s",
        po_number,
        order.external_order_id,
        total,
        len(item_costs),
        trace_id,
    )

    return purchase_order, True


async def update_purchase_order_status(
    session: AsyncSession,
    po_id: UUID,
    new_status: str,
    workspace_id: UUID | None = None,
    trace_id: str | None = None,
) -> PurchaseOrder:
    """
    更新采购单状态

    Args:
        session: 数据库会话
        po_id: 采购单 ID
        new_status: 新状态
        workspace_id: 工作空间 ID
        trace_id: 追踪 ID

    Returns:
        更新后的采购单
    """
    if workspace_id is None:
        workspace_id = DEFAULT_WORKSPACE_ID

    # 获取采购单
    result = await session.execute(
        select(PurchaseOrder).where(
            PurchaseOrder.id == po_id,
            PurchaseOrder.workspace_id == workspace_id,
        )
    )
    po = result.scalar_one_or_none()
    if not po:
        raise ValueError(f"Purchase order not found: {po_id}")

    # 验证状态流转
    allowed_statuses = PO_STATUS_FLOW.get(po.status, [])
    if new_status not in allowed_statuses:
        raise ValueError(
            f"Invalid status transition: {po.status} -> {new_status}. "
            f"Allowed: {allowed_statuses}"
        )

    old_status = po.status
    po.status = new_status
    po.trace_id = trace_id

    # 如果状态为 received，记录收货时间
    if new_status == "received" and not po.received_at:
        po.received_at = datetime.utcnow()

    await session.flush()

    logger.info(
        "Purchase order status updated: po=%s, %s -> %s, trace=%s",
        po.po_number,
        old_status,
        new_status,
        trace_id,
    )

    return po


async def add_tracking_to_order(
    session: AsyncSession,
    order_id: UUID,
    tracking_number: str,
    carrier: str,
    tracking_url: str | None = None,
    workspace_id: UUID | None = None,
    trace_id: str | None = None,
) -> Order:
    """
    为订单添加物流追踪信息

    Args:
        session: 数据库会话
        order_id: 订单 ID
        tracking_number: 物流单号
        carrier: 物流公司
        tracking_url: 物流追踪链接
        workspace_id: 工作空间 ID
        trace_id: 追踪 ID

    Returns:
        更新后的订单
    """
    if workspace_id is None:
        workspace_id = DEFAULT_WORKSPACE_ID

    # 获取订单
    result = await session.execute(
        select(Order).where(
            Order.id == order_id,
            Order.workspace_id == workspace_id,
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise ValueError(f"Order not found: {order_id}")

    # 更新订单履约状态
    order.fulfillment_status = "shipped"

    # 将物流信息保存到 profit_snapshot（简化处理）
    # 实际项目中应该有专门的物流追踪表
    tracking_info = {
        "tracking_number": tracking_number,
        "carrier": carrier,
        "tracking_url": tracking_url,
        "shipped_at": datetime.utcnow().isoformat(),
        "trace_id": trace_id,
    }

    # 更新 profit_snapshot 中的物流信息
    snapshot = order.profit_snapshot or {}
    snapshot["tracking"] = tracking_info
    order.profit_snapshot = snapshot

    await session.flush()

    logger.info(
        "Tracking added to order: order=%s, tracking=%s, carrier=%s, trace=%s",
        order.external_order_id,
        tracking_number,
        carrier,
        trace_id,
    )

    return order


async def get_purchase_orders(
    session: AsyncSession,
    status: str | None = None,
    workspace_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """
    获取采购单列表

    Args:
        session: 数据库会话
        status: 按状态筛选
        workspace_id: 工作空间 ID
        limit: 每页数量
        offset: 偏移量

    Returns:
        采购单列表和分页信息
    """
    if workspace_id is None:
        workspace_id = DEFAULT_WORKSPACE_ID

    query = select(PurchaseOrder).where(PurchaseOrder.workspace_id == workspace_id)

    if status:
        query = query.where(PurchaseOrder.status == status)

    query = query.order_by(PurchaseOrder.created_at.desc()).limit(limit).offset(offset)

    result = await session.execute(query)
    pos = result.scalars().all()

    # 统计总数
    count_query = select(PurchaseOrder).where(PurchaseOrder.workspace_id == workspace_id)
    if status:
        count_query = count_query.where(PurchaseOrder.status == status)
    count_result = await session.execute(count_query)
    total = len(count_result.scalars().all())

    return {
        "purchase_orders": [
            {
                "id": str(po.id),
                "po_number": po.po_number,
                "status": po.status,
                "currency": po.currency,
                "subtotal": str(po.subtotal),
                "shipping_cost": str(po.shipping_cost),
                "total": str(po.total),
                "expected_delivery_at": po.expected_delivery_at.isoformat() if po.expected_delivery_at else None,
                "received_at": po.received_at.isoformat() if po.received_at else None,
                "notes": po.notes,
                "created_at": po.created_at.isoformat() if po.created_at else None,
            }
            for po in pos
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


async def get_purchase_order_detail(
    session: AsyncSession,
    po_id: UUID,
    workspace_id: UUID | None = None,
) -> dict[str, Any]:
    """
    获取采购单详情（包含商品项）

    Args:
        session: 数据库会话
        po_id: 采购单 ID
        workspace_id: 工作空间 ID

    Returns:
        采购单详情
    """
    if workspace_id is None:
        workspace_id = DEFAULT_WORKSPACE_ID

    result = await session.execute(
        select(PurchaseOrder).where(
            PurchaseOrder.id == po_id,
            PurchaseOrder.workspace_id == workspace_id,
        )
    )
    po = result.scalar_one_or_none()
    if not po:
        raise ValueError(f"Purchase order not found: {po_id}")

    # 获取商品项
    items_result = await session.execute(
        select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == po.id)
    )
    items = items_result.scalars().all()

    return {
        "id": str(po.id),
        "po_number": po.po_number,
        "supplier_id": str(po.supplier_id) if po.supplier_id else None,
        "status": po.status,
        "currency": po.currency,
        "subtotal": str(po.subtotal),
        "shipping_cost": str(po.shipping_cost),
        "total": str(po.total),
        "expected_delivery_at": po.expected_delivery_at.isoformat() if po.expected_delivery_at else None,
        "received_at": po.received_at.isoformat() if po.received_at else None,
        "notes": po.notes,
        "trace_id": po.trace_id,
        "created_at": po.created_at.isoformat() if po.created_at else None,
        "updated_at": po.updated_at.isoformat() if po.updated_at else None,
        "items": [
            {
                "id": str(item.id),
                "sku": item.sku,
                "name": item.name,
                "quantity": item.quantity,
                "unit_cost": str(item.unit_cost),
                "line_total": str(item.line_total),
            }
            for item in items
        ],
        "allowed_next_statuses": PO_STATUS_FLOW.get(po.status, []),
    }



async def confirm_purchase_order_cost(
    session: AsyncSession,
    po_id: UUID,
    confirmed_by: str,
    workspace_id: UUID | None = None,
    trace_id: str | None = None,
) -> PurchaseOrder:
    """
    确认采购单成本，将 pending_cost_confirmation 转为 draft。

    M0-M4.1: 成本缺失时采购单进入 pending_cost_confirmation，
    只有在真实 ProductCost 补齐后才能确认成本并进入审批流程。

    Rules:
    - 只能从 pending_cost_confirmation 转为 draft
    - 确认后 cost_confirmed=True, cost_source="product_cost"
    - 重复确认不会产生重复采购单（幂等）
    - confirmed_by 来自认证上下文，不得由客户端传入绕过
    """
    if workspace_id is None:
        workspace_id = DEFAULT_WORKSPACE_ID

    result = await session.execute(
        select(PurchaseOrder).where(
            PurchaseOrder.id == po_id,
            PurchaseOrder.workspace_id == workspace_id,
        )
    )
    po = result.scalar_one_or_none()
    if po is None:
        raise ValueError(f"Purchase order not found: {po_id}")

    # Idempotent: if already confirmed, return as-is
    if po.cost_confirmed and po.status == "draft":
        logger.info("PO %s already cost-confirmed, idempotent return", po.po_number)
        return po

    # Only pending_cost_confirmation can be confirmed
    if po.status != "pending_cost_confirmation":
        raise ValueError(
            f"Cannot confirm cost for PO {po.po_number}: status is '{po.status}', "
            f"expected 'pending_cost_confirmation'"
        )

    # Verify all items now have real ProductCost
    items_result = await session.execute(
        select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == po.id)
    )
    items = items_result.scalars().all()

    missing_cost_items = []
    for item in items:
        if item.product_id:
            cost_result = await session.execute(
                select(ProductCost).where(
                    ProductCost.product_id == item.product_id,
                    ProductCost.workspace_id == workspace_id,
                )
            )
            cost = cost_result.scalar_one_or_none()
            if not cost or cost.purchase_cost <= 0:
                missing_cost_items.append(item.sku)
        elif item.sku:
            product_result = await session.execute(
                select(Product).where(
                    Product.sku == item.sku,
                    Product.workspace_id == workspace_id,
                )
            )
            product = product_result.scalar_one_or_none()
            if not product or not product.cost or product.cost.purchase_cost <= 0:
                missing_cost_items.append(item.sku)
        else:
            missing_cost_items.append(f"item-{item.id}")

    if missing_cost_items:
        raise ValueError(
            f"Cannot confirm cost for PO {po.po_number}: still missing real ProductCost "
            f"for items: {', '.join(missing_cost_items[:5])}"
        )

    # Confirm cost and transition to draft
    po.status = "draft"
    po.cost_confirmed = True
    po.cost_source = "product_cost"
    po.cost_confidence = Decimal("0.95")
    po.cost_confirmed_at = datetime.utcnow()
    po.cost_confirmed_by = confirmed_by
    po.cost_block_reason = None

    if po.notes:
        po.notes += f"\n[cost_confirmed] by={confirmed_by} at={po.cost_confirmed_at.isoformat()}"
    else:
        po.notes = f"[cost_confirmed] by={confirmed_by} at={po.cost_confirmed_at.isoformat()}"

    await session.flush()

    logger.info(
        "PO cost confirmed: po=%s, by=%s, trace=%s",
        po.po_number, confirmed_by, trace_id,
    )
    return po
