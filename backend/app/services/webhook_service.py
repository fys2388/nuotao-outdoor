"""
WooCommerce Webhook 事件处理服务
支持订单、产品、客户等多种事件类型
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_sync_service import sync_order_from_woocommerce

logger = logging.getLogger(__name__)


# 支持的 Webhook 事件类型
SUPPORTED_EVENTS = {
    # 订单事件
    "order.created": "订单创建",
    "order.updated": "订单更新",
    "order.deleted": "订单删除",
    "order.restored": "订单恢复",
    # 产品事件
    "product.created": "产品创建",
    "product.updated": "产品更新",
    "product.deleted": "产品删除",
    "product.restored": "产品恢复",
    # 客户事件
    "customer.created": "客户创建",
    "customer.updated": "客户更新",
    "customer.deleted": "客户删除",
    # 优惠券事件
    "coupon.created": "优惠券创建",
    "coupon.updated": "优惠券更新",
    "coupon.deleted": "优惠券删除",
    # 笔记事件
    "order_note.created": "订单笔记创建",
}


class WebhookEvent:
    """Webhook 事件数据结构"""

    def __init__(
        self,
        event_type: str,
        payload: dict[str, Any],
        webhook_id: str | None = None,
        delivery_id: str | None = None,
    ):
        self.event_type = event_type
        self.payload = payload
        self.webhook_id = webhook_id
        self.delivery_id = delivery_id
        self.received_at = datetime.now(UTC)

    @property
    def event_name(self) -> str:
        return SUPPORTED_EVENTS.get(self.event_type, self.event_type)

    @property
    def resource_type(self) -> str:
        return self.event_type.split(".")[0]

    @property
    def resource_id(self) -> str | None:
        return str(self.payload.get("id")) if "id" in self.payload else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "event_name": self.event_name,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "webhook_id": self.webhook_id,
            "delivery_id": self.delivery_id,
            "received_at": self.received_at.isoformat(),
            "payload": self.payload,
        }


async def process_webhook_event(
    session: AsyncSession,
    event: WebhookEvent,
    workspace_id: str | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """
    处理 Webhook 事件

    Args:
        session: 数据库会话
        event: Webhook 事件
        workspace_id: 工作区 ID
        trace_id: 追踪 ID

    Returns:
        处理结果
    """
    logger.info(
        "Processing webhook event: type=%s, resource=%s, id=%s, trace=%s",
        event.event_type,
        event.resource_type,
        event.resource_id,
        trace_id,
    )

    result = {
        "status": "processed",
        "event_type": event.event_type,
        "event_name": event.event_name,
        "resource_type": event.resource_type,
        "resource_id": event.resource_id,
        "processed_at": datetime.now(UTC).isoformat(),
    }

    try:
        # 根据事件类型分发处理
        if event.resource_type == "order":
            result["details"] = await _process_order_event(session, event, workspace_id, trace_id)
        elif event.resource_type == "product":
            result["details"] = await _process_product_event(session, event, workspace_id, trace_id)
        elif event.resource_type == "customer":
            result["details"] = await _process_customer_event(session, event, workspace_id, trace_id)
        elif event.resource_type == "coupon":
            result["details"] = await _process_coupon_event(session, event, workspace_id, trace_id)
        elif event.resource_type == "order_note":
            result["details"] = await _process_order_note_event(session, event, workspace_id, trace_id)
        else:
            result["status"] = "ignored"
            result["details"] = {"reason": f"Unsupported event type: {event.event_type}"}
            logger.info("Ignored unsupported webhook event: %s", event.event_type)

        # 记录事件到事件日志
        await _log_event(session, event, result, workspace_id, trace_id)

        logger.info(
            "Webhook event processed successfully: type=%s, status=%s",
            event.event_type,
            result["status"],
        )

    except Exception as e:
        logger.exception("Failed to process webhook event: %s", str(e))
        result["status"] = "failed"
        result["error"] = str(e)

    return result


async def _process_order_event(
    session: AsyncSession,
    event: WebhookEvent,
    workspace_id: str | None,
    trace_id: str | None,
) -> dict[str, Any]:
    """处理订单事件"""
    payload = event.payload

    # 同步订单到本地数据库
    sync_result = None
    sync_error = None
    try:
        from uuid import UUID as _UUID
        ws_id = _UUID(workspace_id) if workspace_id else None
        order, is_new = await sync_order_from_woocommerce(
            session=session,
            wc_order=payload,
            workspace_id=ws_id,
            trace_id=trace_id,
        )
        sync_result = {
            "local_order_id": str(order.id),
            "is_new": is_new,
            "status": order.status,
            "total": str(order.total),
        }
        logger.info(
            "Order synced to local DB: external_id=%s, local_id=%s, is_new=%s, trace=%s",
            payload.get("id"),
            order.id,
            is_new,
            trace_id,
        )
    except Exception as e:
        sync_error = str(e)
        logger.exception("Order sync failed: order_id=%s, error=%s, trace=%s", payload.get("id"), str(e), trace_id)

    details = {
        "order_id": payload.get("id"),
        "order_number": payload.get("number"),
        "status": payload.get("status"),
        "total": payload.get("total"),
        "customer_id": payload.get("customer_id"),
        "items_count": len(payload.get("line_items", [])),
        "local_sync": {
            "success": sync_result is not None,
            "result": sync_result,
            "error": sync_error,
        },
    }

    # 订单创建时触发 AI 分析（可选）
    if event.event_type == "order.created":
        details["ai_analysis_triggered"] = True
        logger.info("Order created, AI analysis could be triggered: order_id=%s", payload.get("id"))

        # 发送订单确认邮件
        try:
            from app.services.email_service import (
                get_email_service,
                render_order_confirmation_email,
            )
            email_service = get_email_service()
            customer_email = (payload.get("billing", {}) or {}).get("email", f"customer_{payload.get('id')}@example.com")
            subject, html_content, text_content = render_order_confirmation_email(payload)
            email_result = await email_service.send_email(
                to_email=customer_email,
                subject=subject,
                html_content=html_content,
                text_content=text_content,
                metadata={"order_id": payload.get("id"), "email_type": "order_confirmation"},
            )
            details["order_confirmation_email"] = {
                "sent": email_result.get("success", False),
                "email_id": email_result.get("email_id"),
                "mode": email_result.get("mode"),
            }
            logger.info("Order confirmation email sent: order_id=%s, email_id=%s, mode=%s", payload.get("id"), email_result.get("email_id"), email_result.get("mode"))
        except Exception as e:
            details["order_confirmation_email_error"] = str(e)
            logger.exception("Order confirmation email failed: order_id=%s, error=%s", payload.get("id"), str(e))

    # 订单状态变更时记录
    if event.event_type == "order.updated":
        details["previous_status"] = payload.get("status")
        logger.info("Order updated: order_id=%s, status=%s", payload.get("id"), payload.get("status"))

        # 订单完成时发送发货确认邮件
        if payload.get("status") == "completed":
            try:
                from app.services.email_service import (
                    get_email_service,
                    render_shipping_confirmation_email,
                )
                email_service = get_email_service()
                customer_email = (payload.get("billing", {}) or {}).get("email", f"customer_{payload.get('id')}@example.com")
                tracking_info = {
                    "carrier": "Standard Shipping",
                    "tracking_number": f"TRK{payload.get('id')}{int(datetime.now().timestamp())}",
                    "tracking_url": "",
                    "estimated_delivery": "7-14 business days",
                }
                subject, html_content, text_content = render_shipping_confirmation_email(payload, tracking_info)
                email_result = await email_service.send_email(
                    to_email=customer_email,
                    subject=subject,
                    html_content=html_content,
                    text_content=text_content,
                    metadata={"order_id": payload.get("id"), "email_type": "shipping_confirmation"},
                )
                details["shipping_confirmation_email"] = {
                    "sent": email_result.get("success", False),
                    "email_id": email_result.get("email_id"),
                    "mode": email_result.get("mode"),
                }
                logger.info("Shipping confirmation email sent: order_id=%s, email_id=%s", payload.get("id"), email_result.get("email_id"))
            except Exception as e:
                details["shipping_confirmation_email_error"] = str(e)
                logger.exception("Shipping confirmation email failed: order_id=%s, error=%s", payload.get("id"), str(e))

        # 订单取消时发送取消邮件
        if payload.get("status") == "cancelled":
            try:
                from app.services.email_service import (
                    get_email_service,
                    render_order_cancelled_email,
                )
                email_service = get_email_service()
                customer_email = (payload.get("billing", {}) or {}).get("email", f"customer_{payload.get('id')}@example.com")
                subject, html_content, text_content = render_order_cancelled_email(payload)
                email_result = await email_service.send_email(
                    to_email=customer_email,
                    subject=subject,
                    html_content=html_content,
                    text_content=text_content,
                    metadata={"order_id": payload.get("id"), "email_type": "order_cancelled"},
                )
                details["order_cancelled_email"] = {
                    "sent": email_result.get("success", False),
                    "email_id": email_result.get("email_id"),
                    "mode": email_result.get("mode"),
                }
                logger.info("Order cancelled email sent: order_id=%s, email_id=%s", payload.get("id"), email_result.get("email_id"))
            except Exception as e:
                details["order_cancelled_email_error"] = str(e)
                logger.exception("Order cancelled email failed: order_id=%s, error=%s", payload.get("id"), str(e))

    # 支付成功检测：订单状态为 processing 或 completed 表示已支付
    payment_status = payload.get("status", "")
    payment_method = payload.get("payment_method", "")
    payment_method_title = payload.get("payment_method_title", "")
    date_paid = payload.get("date_paid", "")

    if payment_status in ("processing", "completed") and date_paid:
        details["payment_successful"] = True
        details["payment_method"] = payment_method
        details["payment_method_title"] = payment_method_title
        details["date_paid"] = date_paid
        details["payment_total"] = payload.get("total")

        # 支付成功后自动生成采购单
        try:
            from uuid import UUID as _UUID

            from app.services.fulfillment_service import create_purchase_order_from_order
            from app.services.order_sync_service import get_order_by_external_id

            ws_id = _UUID(workspace_id) if workspace_id else None
            local_order = await get_order_by_external_id(
                session=session,
                external_order_id=str(payload.get("id")),
                workspace_id=ws_id,
            )

            if local_order:
                po, is_new = await create_purchase_order_from_order(
                    session=session,
                    order=local_order,
                    wc_order_data=payload,
                    workspace_id=ws_id,
                    trace_id=trace_id,
                )
                details["purchase_order"] = {
                    "created": is_new,
                    "po_number": po.po_number,
                    "po_id": str(po.id),
                    "status": po.status,
                    "total": str(po.total),
                }
                logger.info(
                    "Purchase order auto-generated: order=%s, po=%s, is_new=%s, trace=%s",
                    payload.get("id"),
                    po.po_number,
                    is_new,
                    trace_id,
                )
            else:
                details["purchase_order_error"] = "Local order not found"
                logger.warning("Local order not found for PO generation: order_id=%s", payload.get("id"))
        except Exception as e:
            details["purchase_order_error"] = str(e)
            logger.exception("Purchase order generation failed: order_id=%s, error=%s", payload.get("id"), str(e))
        logger.info(
            "Payment successful: order_id=%s, method=%s, total=%s, date_paid=%s",
            payload.get("id"),
            payment_method_title or payment_method,
            payload.get("total"),
            date_paid,
        )
    elif payment_status == "pending":
        details["payment_pending"] = True
        logger.info("Payment pending: order_id=%s", payload.get("id"))
    elif payment_status == "failed":
        details["payment_failed"] = True
        logger.warning("Payment failed: order_id=%s", payload.get("id"))
    elif payment_status == "refunded":
        details["payment_refunded"] = True
        logger.info("Payment refunded: order_id=%s", payload.get("id"))

    return details


async def _process_product_event(
    session: AsyncSession,
    event: WebhookEvent,
    workspace_id: str | None,
    trace_id: str | None,
) -> dict[str, Any]:
    """处理产品事件"""
    payload = event.payload
    details = {
        "product_id": payload.get("id"),
        "sku": payload.get("sku"),
        "name": payload.get("name"),
        "price": payload.get("price"),
        "stock_quantity": payload.get("stock_quantity"),
        "status": payload.get("status"),
    }

    # 产品创建/更新时触发产品分析师 AI 分析（可选）
    if event.event_type in ("product.created", "product.updated"):
        details["product_analyst_triggered"] = True
        logger.info("Product event, product analyst could be triggered: product_id=%s", payload.get("id"))

    return details


async def _process_customer_event(
    session: AsyncSession,
    event: WebhookEvent,
    workspace_id: str | None,
    trace_id: str | None,
) -> dict[str, Any]:
    """处理客户事件"""
    payload = event.payload
    details = {
        "customer_id": payload.get("id"),
        "email": payload.get("email"),
        "first_name": payload.get("first_name"),
        "last_name": payload.get("last_name"),
        "orders_count": payload.get("orders_count"),
        "total_spent": payload.get("total_spent"),
    }

    # 客户创建时触发客户经理 AI 分析（可选）
    if event.event_type == "customer.created":
        details["customer_manager_triggered"] = True
        logger.info("Customer created, customer manager could be triggered: customer_id=%s", payload.get("id"))

    return details


async def _process_coupon_event(
    session: AsyncSession,
    event: WebhookEvent,
    workspace_id: str | None,
    trace_id: str | None,
) -> dict[str, Any]:
    """处理优惠券事件"""
    payload = event.payload
    return {
        "coupon_id": payload.get("id"),
        "code": payload.get("code"),
        "discount_type": payload.get("discount_type"),
        "amount": payload.get("amount"),
        "usage_count": payload.get("usage_count"),
    }


async def _process_order_note_event(
    session: AsyncSession,
    event: WebhookEvent,
    workspace_id: str | None,
    trace_id: str | None,
) -> dict[str, Any]:
    """处理订单笔记事件"""
    payload = event.payload
    return {
        "note_id": payload.get("id"),
        "order_id": payload.get("order_id"),
        "note": payload.get("note"),
        "customer_note": payload.get("customer_note"),
        "author": payload.get("author"),
    }


async def _log_event(
    session: AsyncSession,
    event: WebhookEvent,
    result: dict[str, Any],
    workspace_id: str | None,
    trace_id: str | None,
) -> None:
    """记录事件到事件日志"""
    try:
        # 这里可以记录到数据库事件表
        # 由于事件表结构可能不同，这里只做日志记录
        logger.info(
            "Webhook event logged: type=%s, resource_id=%s, status=%s, trace=%s",
            event.event_type,
            event.resource_id,
            result.get("status"),
            trace_id,
        )
    except Exception as e:
        logger.warning("Failed to log webhook event: %s", str(e))


def parse_webhook_event(
    payload: dict[str, Any],
    headers: dict[str, str],
) -> WebhookEvent:
    """
    从 Webhook 请求中解析事件

    WooCommerce Webhook 头部包含：
    - X-Wc-Webhook-Id: Webhook ID
    - X-Wc-Webhook-Event: 事件类型（如 order.created）
    - X-Wc-Webhook-Delivery-Id: 交付 ID
    - X-Wc-Webhook-Signature: HMAC 签名
    """
    event_type = headers.get("x-wc-webhook-topic")
    if not event_type:
        # 如果没有 topic 头部，则用 resource + event 组合
        resource = headers.get("x-wc-webhook-resource", "unknown")
        event = headers.get("x-wc-webhook-event", "unknown")
        event_type = f"{resource}.{event}"
    webhook_id = headers.get("x-wc-webhook-id")
    delivery_id = headers.get("x-wc-webhook-delivery-id")

    return WebhookEvent(
        event_type=event_type,
        payload=payload,
        webhook_id=webhook_id,
        delivery_id=delivery_id,
    )
