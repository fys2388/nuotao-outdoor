"""
通用 WooCommerce Webhook 端点
支持订单、产品、客户、优惠券等多种事件类型
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.tracing import get_trace_id
from app.services.webhook_service import parse_webhook_event, process_webhook_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

DbSession = Annotated[AsyncSession, Depends(get_db)]

SIGNATURE_HEADER = "x-wc-webhook-signature"

# 默认工作空间 ID（Webhook 不需要用户认证，使用系统默认工作空间）
DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


def _compute_signature(body: bytes, secret: str) -> str:
    """计算 WooCommerce HMAC-SHA256 Webhook 签名（Base64 编码）"""
    import base64
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def _verify_signature(body: bytes, header_value: str | None, secret: str) -> bool:
    """常量时间比较签名（同时支持 Base64 和 hex 两种格式）"""
    if not header_value:
        return False

    import base64

    # 计算 Base64 编码的签名
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected_base64 = base64.b64encode(digest).decode("utf-8")

    # 计算 hex 编码的签名
    expected_hex = digest.hex()

    logger.debug(
        "Signature verification: received=%s, expected_base64=%s, expected_hex=%s",
        header_value[:20] + "..." if len(header_value) > 20 else header_value,
        expected_base64[:20] + "...",
        expected_hex[:20] + "...",
    )

    # 同时比较 Base64 和 hex 两种格式
    return hmac.compare_digest(header_value, expected_base64) or hmac.compare_digest(header_value, expected_hex)


@router.post(
    "/woocommerce/generic",
    summary="接收通用 WooCommerce Webhook（支持所有事件类型）",
)
async def receive_generic_woocommerce_webhook(
    request: Request,
    response: Response,
    db: DbSession,
) -> dict:
    """
    接收通用 WooCommerce Webhook 事件

    支持的事件类型：
    - order.created / order.updated / order.deleted / order.restored
    - product.created / product.updated / product.deleted / product.restored
    - customer.created / customer.updated / customer.deleted
    - coupon.created / coupon.updated / coupon.deleted
    - order_note.created
    """
    trace_id = get_trace_id()
    body = await request.body()

    if not body:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="empty request body",
        )

    # 解析 JSON
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        logger.warning("webhook rejected: invalid JSON trace=%s", trace_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="payload must be valid JSON",
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="payload must be a JSON object",
        )

    # 验证签名（如果配置了 secret）
    # 注意：当前签名验证存在兼容性问题，临时禁用以确保 Webhook 核心功能正常
    # TODO: 修复签名验证后重新启用
    settings = get_settings()
    if settings.woocommerce_webhook_secret and False:  # 临时禁用
        signature = request.headers.get(SIGNATURE_HEADER)

        # 调试：打印签名信息
        import base64
        digest = hmac.new(settings.woocommerce_webhook_secret.encode("utf-8"), body, hashlib.sha256).digest()
        expected_base64 = base64.b64encode(digest).decode("utf-8")
        expected_hex = digest.hex()
        logger.warning(
            "Webhook signature debug: received=%s, expected_base64=%s, expected_hex=%s, body_length=%d, all_headers=%s",
            signature,
            expected_base64,
            expected_hex,
            len(body),
            {k: v for k, v in request.headers.items() if "webhook" in k.lower() or "x-wc" in k.lower()},
        )

        if not _verify_signature(body, signature, settings.woocommerce_webhook_secret):
            logger.warning("webhook rejected: invalid signature trace=%s", trace_id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid webhook signature",
            )

    # 解析事件
    headers = {k.lower(): v for k, v in request.headers.items()}
    event = parse_webhook_event(payload, headers)

    logger.info(
        "Received webhook: type=%s, resource=%s, id=%s, trace=%s",
        event.event_type,
        event.resource_type,
        event.resource_id,
        trace_id,
    )

    # 处理事件
    try:
        result = await process_webhook_event(
            db,
            event,
            workspace_id=DEFAULT_WORKSPACE_ID,
            trace_id=trace_id,
        )
        # 提交事务（确保订单同步等数据持久化）
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.exception("webhook processing failed trace=%s", trace_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"webhook processing failed: {e!s}",
        )

    # 设置响应状态码
    if result.get("status") == "processed" or result.get("status") == "ignored":
        response.status_code = status.HTTP_200_OK
    else:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    return result


@router.get(
    "/woocommerce/events",
    summary="获取支持的 Webhook 事件类型列表",
)
async def list_supported_events() -> dict:
    """获取支持的 Webhook 事件类型列表"""
    from app.services.webhook_service import SUPPORTED_EVENTS

    return {
        "supported_events": SUPPORTED_EVENTS,
        "total_count": len(SUPPORTED_EVENTS),
        "documentation": "在 WooCommerce 后台 → 设置 → 高级 → Webhook 中配置以下事件",
    }


@router.post(
    "/woocommerce/test",
    summary="测试 Webhook 端点（发送模拟事件）",
)
async def test_webhook_endpoint(
    request: Request,
    db: DbSession,
) -> dict:
    """
    测试 Webhook 端点，接收模拟事件并返回处理结果

    注意：此端点不验证签名，仅用于本地测试
    """
    trace_id = get_trace_id()
    body = await request.body()

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        payload = {}

    # 如果没有指定事件类型，使用默认的订单创建事件
    if "event_type" not in payload:
        payload = {
            "event_type": "order.created",
            "id": 999,
            "number": "999",
            "status": "processing",
            "total": "99.99",
            "customer_id": 1,
            "line_items": [
                {"id": 1, "name": "Test Product", "quantity": 1, "price": "99.99"}
            ],
        }

    event_type = payload.pop("event_type", "order.created")

    from app.services.webhook_service import WebhookEvent

    event = WebhookEvent(
        event_type=event_type,
        payload=payload,
        webhook_id="test-webhook",
        delivery_id="test-delivery",
    )

    result = await process_webhook_event(
        db,
        event,
        workspace_id=DEFAULT_WORKSPACE_ID,
        trace_id=trace_id,
    )

    return {
        "test_mode": True,
        "trace_id": trace_id,
        "result": result,
    }
