"""
订单同步服务
将 WooCommerce 订单数据同步到本地 PostgreSQL 数据库
支持创建、更新、幂等性保证
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, OrderItem

logger = logging.getLogger(__name__)

# 默认工作空间 ID（Webhook 场景使用）
DEFAULT_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000001")


def _safe_decimal(value: Any, default: float = 0.0) -> Decimal:
    """安全转换为 Decimal"""
    try:
        if value is None or value == "":
            return Decimal(str(default))
        return Decimal(str(value))
    except (ValueError, TypeError):
        return Decimal(str(default))


def _map_order_status(wc_status: str) -> str:
    """将 WooCommerce 订单状态映射为本地状态"""
    status_map = {
        "pending": "pending",
        "processing": "processing",
        "on-hold": "on_hold",
        "completed": "completed",
        "cancelled": "cancelled",
        "refunded": "refunded",
        "failed": "failed",
        "trash": "trash",
    }
    return status_map.get(wc_status, wc_status)


def _map_payment_status(wc_status: str, date_paid: str | None) -> str | None:
    """根据订单状态和支付时间推断支付状态"""
    if date_paid:
        return "paid"
    if wc_status in ("processing", "completed"):
        return "paid"
    if wc_status == "refunded":
        return "refunded"
    if wc_status == "failed":
        return "failed"
    if wc_status == "pending":
        return "pending"
    return None


def _map_fulfillment_status(wc_status: str) -> str | None:
    """根据订单状态推断履约状态"""
    if wc_status == "completed":
        return "fulfilled"
    if wc_status in ("processing", "on-hold"):
        return "processing"
    if wc_status == "cancelled":
        return "cancelled"
    return None


async def sync_order_from_woocommerce(
    session: AsyncSession,
    wc_order: dict[str, Any],
    workspace_id: UUID | None = None,
    trace_id: str | None = None,
) -> tuple[Order, bool]:
    """
    从 WooCommerce 订单数据同步到本地数据库

    Args:
        session: 数据库会话
        wc_order: WooCommerce 订单数据（来自 API 或 Webhook）
        workspace_id: 工作空间 ID
        trace_id: 追踪 ID

    Returns:
        (订单对象, 是否新建)
    """
    if workspace_id is None:
        workspace_id = DEFAULT_WORKSPACE_ID

    external_order_id = str(wc_order.get("id", ""))
    if not external_order_id:
        raise ValueError("WooCommerce order missing 'id' field")

    wc_status = wc_order.get("status", "pending")
    date_paid = wc_order.get("date_paid")
    date_completed = wc_order.get("date_completed")

    # 计算退款总额
    refunded_amount = Decimal("0")
    for refund in wc_order.get("refunds", []):
        refunded_amount += _safe_decimal(refund.get("total", 0))

    # 查找现有订单
    result = await session.execute(
        select(Order).where(
            Order.workspace_id == workspace_id,
            Order.external_order_id == external_order_id,
        )
    )
    existing_order = result.scalar_one_or_none()

    is_new = existing_order is None

    if is_new:
        # 创建新订单（处理竞态条件：如果并发创建导致唯一约束冲突，则回滚并更新现有订单）
        try:
            order = Order(
                workspace_id=workspace_id,
                external_order_id=external_order_id,
                status=_map_order_status(wc_status),
                payment_status=_map_payment_status(wc_status, date_paid),
                fulfillment_status=_map_fulfillment_status(wc_status),
                currency=wc_order.get("currency", "USD"),
                country=(wc_order.get("billing", {}) or {}).get("country"),
                payment_method=wc_order.get("payment_method"),
                source="woocommerce",
                customer_reference_id=str(wc_order.get("customer_id", "")) if wc_order.get("customer_id") else None,
                subtotal=_safe_decimal(wc_order.get("subtotal")),
                shipping_total=_safe_decimal(wc_order.get("shipping_total")),
                discount_total=_safe_decimal(wc_order.get("discount_total")),
                tax_total=_safe_decimal(wc_order.get("total_tax")),
                total=_safe_decimal(wc_order.get("total")),
                refunded_amount=refunded_amount,
                trace_id=trace_id,
            )
            session.add(order)
            await session.flush()
            logger.info(
                "Created local order: external_id=%s, total=%s, status=%s, trace=%s",
                external_order_id,
                order.total,
                order.status,
                trace_id,
            )
        except IntegrityError:
            # 竞态条件：另一个请求已经创建了这个订单，回滚并更新现有订单
            await session.rollback()
            result = await session.execute(
                select(Order).where(
                    Order.workspace_id == workspace_id,
                    Order.external_order_id == external_order_id,
                )
            )
            order = result.scalar_one_or_none()
            if order is None:
                raise  # 不应该发生，但如果发生则抛出异常
            is_new = False
            logger.info(
                "Race condition handled: order already exists, updating instead: external_id=%s, trace=%s",
                external_order_id,
                trace_id,
            )
            # 更新现有订单
            order.status = _map_order_status(wc_status)
            order.payment_status = _map_payment_status(wc_status, date_paid)
            order.fulfillment_status = _map_fulfillment_status(wc_status)
            order.currency = wc_order.get("currency", order.currency)
            order.country = (wc_order.get("billing", {}) or {}).get("country", order.country)
            order.payment_method = wc_order.get("payment_method", order.payment_method)
            order.subtotal = _safe_decimal(wc_order.get("subtotal"), float(order.subtotal))
            order.shipping_total = _safe_decimal(wc_order.get("shipping_total"), float(order.shipping_total))
            order.discount_total = _safe_decimal(wc_order.get("discount_total"), float(order.discount_total))
            order.tax_total = _safe_decimal(wc_order.get("total_tax"), float(order.tax_total))
            order.total = _safe_decimal(wc_order.get("total"), float(order.total))
            order.refunded_amount = refunded_amount
            order.trace_id = trace_id
    else:
        # 更新现有订单
        order = existing_order
        order.status = _map_order_status(wc_status)
        order.payment_status = _map_payment_status(wc_status, date_paid)
        order.fulfillment_status = _map_fulfillment_status(wc_status)
        order.currency = wc_order.get("currency", order.currency)
        order.country = (wc_order.get("billing", {}) or {}).get("country", order.country)
        order.payment_method = wc_order.get("payment_method", order.payment_method)
        order.subtotal = _safe_decimal(wc_order.get("subtotal"), float(order.subtotal))
        order.shipping_total = _safe_decimal(wc_order.get("shipping_total"), float(order.shipping_total))
        order.discount_total = _safe_decimal(wc_order.get("discount_total"), float(order.discount_total))
        order.tax_total = _safe_decimal(wc_order.get("total_tax"), float(order.tax_total))
        order.total = _safe_decimal(wc_order.get("total"), float(order.total))
        order.refunded_amount = refunded_amount
        order.trace_id = trace_id
        logger.info(
            "Updated local order: external_id=%s, total=%s, status=%s, trace=%s",
            external_order_id,
            order.total,
            order.status,
            trace_id,
        )

    # 同步订单商品项（先删除旧的，再插入新的）
    if not is_new:
        # 删除旧的商品项
        for item in order.items:
            await session.delete(item)
        await session.flush()

    # 插入新的商品项
    for line_item in wc_order.get("line_items", []):
        order_item = OrderItem(
            order_id=order.id,
            workspace_id=workspace_id,
            external_item_id=str(line_item.get("id", "")) if line_item.get("id") else None,
            sku=line_item.get("sku"),
            name=line_item.get("name", "Unknown Product"),
            quantity=int(line_item.get("quantity", 1)),
            unit_price=_safe_decimal(line_item.get("price", line_item.get("unit_price", 0))),
            line_total=_safe_decimal(line_item.get("total", 0)),
        )
        session.add(order_item)

    await session.flush()

    logger.info(
        "Order items synced: order_id=%s, item_count=%d, trace=%s",
        external_order_id,
        len(wc_order.get("line_items", [])),
        trace_id,
    )

    return order, is_new


async def get_order_by_external_id(
    session: AsyncSession,
    external_order_id: str,
    workspace_id: UUID | None = None,
) -> Order | None:
    """根据外部订单 ID 获取本地订单"""
    if workspace_id is None:
        workspace_id = DEFAULT_WORKSPACE_ID

    result = await session.execute(
        select(Order).where(
            Order.workspace_id == workspace_id,
            Order.external_order_id == external_order_id,
        )
    )
    return result.scalar_one_or_none()


async def get_order_stats(
    session: AsyncSession,
    workspace_id: UUID | None = None,
) -> dict[str, Any]:
    """获取订单统计信息"""
    if workspace_id is None:
        workspace_id = DEFAULT_WORKSPACE_ID

    result = await session.execute(
        select(Order).where(Order.workspace_id == workspace_id)
    )
    orders = result.scalars().all()

    total_orders = len(orders)
    total_revenue = sum(float(o.total) for o in orders)
    total_refunded = sum(float(o.refunded_amount) for o in orders)
    status_counts: dict[str, int] = {}
    for order in orders:
        status_counts[order.status] = status_counts.get(order.status, 0) + 1

    return {
        "total_orders": total_orders,
        "total_revenue": round(total_revenue, 2),
        "total_refunded": round(total_refunded, 2),
        "net_revenue": round(total_revenue - total_refunded, 2),
        "status_counts": status_counts,
        "average_order_value": round(total_revenue / total_orders, 2) if total_orders > 0 else 0,
    }
