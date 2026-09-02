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
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order
from app.models.supply_chain import PurchaseOrder, PurchaseOrderItem

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

    # 计算采购成本（模拟：售价的 40% 作为采购成本）
    # 实际项目中应该从产品成本表获取
    cost_ratio = Decimal("0.40")
    subtotal = order.total * cost_ratio
    shipping_cost = Decimal("5.00")  # 模拟国内运费
    total = subtotal + shipping_cost

    # 创建采购单
    purchase_order = PurchaseOrder(
        workspace_id=workspace_id,
        po_number=po_number,
        supplier_id=None,  # 待分配供应商
        status="draft",
        currency=order.currency,
        subtotal=subtotal,
        shipping_cost=shipping_cost,
        total=total,
        expected_delivery_at=datetime.utcnow() + timedelta(days=7),
        notes=f"Auto-generated from order_id={order.external_order_id}, trace_id={trace_id or 'N/A'}",
        trace_id=trace_id,
    )
    session.add(purchase_order)
    await session.flush()

    # 创建采购单商品项
    if wc_order_data and wc_order_data.get("line_items"):
        for item in wc_order_data["line_items"]:
            quantity = int(item.get("quantity", 1))
            unit_price = _safe_decimal(item.get("price", item.get("unit_price", 0)))
            unit_cost = unit_price * cost_ratio
            line_total = unit_cost * quantity

            po_item = PurchaseOrderItem(
                purchase_order_id=purchase_order.id,
                workspace_id=workspace_id,
                product_id=None,
                sku=item.get("sku", f"SKU-{item.get('id', 'unknown')}"),
                name=item.get("name", "Unknown Product"),
                quantity=quantity,
                unit_cost=unit_cost,
                line_total=line_total,
            )
            session.add(po_item)
    else:
        # 如果没有 WooCommerce 数据，从订单商品项创建
        for order_item in order.items:
            quantity = order_item.quantity
            unit_cost = order_item.unit_price * cost_ratio
            line_total = unit_cost * quantity

            po_item = PurchaseOrderItem(
                purchase_order_id=purchase_order.id,
                workspace_id=workspace_id,
                product_id=order_item.product_id,
                sku=order_item.sku or f"SKU-{order_item.id}",
                name=order_item.name,
                quantity=quantity,
                unit_cost=unit_cost,
                line_total=line_total,
            )
            session.add(po_item)

    await session.flush()

    logger.info(
        "Purchase order created: po=%s, order=%s, total=%s, items=%d, trace=%s",
        po_number,
        order.external_order_id,
        total,
        len(order.items) if not wc_order_data else len(wc_order_data.get("line_items", [])),
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
