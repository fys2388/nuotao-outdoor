"""WooCommerce webhook endpoint.

Implements the ORDER_CREATED delivery channel:

- HMAC-SHA256 signature verification (``X-Wc-Webhook-Signature``).
- Payment-gateway topic compatibility: payloads carrying
  ``woocommerce.payments.gateways`` are answered 404 (unsupported topic).
- Payload validation via Pydantic (minimal, PII-free projection).
- Idempotent ingestion (duplicate deliveries return 200 with ``duplicate``).
- ``trace_id`` propagation and full-chain structured logging.

Retry strategy: 2xx success (no retry), 4xx client errors (no retry), 5xx
failures (WooCommerce retries with exponential backoff). The idempotency
guard makes retries safe.
"""

import hashlib
import hmac
import json
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.tracing import get_trace_id
from app.core.workspace import get_workspace_id
from app.schemas.order import WebhookOrderPayload, WebhookResponse
from app.services import order_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]

SIGNATURE_HEADER = "x-wc-webhook-signature"

# Key present in payloads for WooCommerce payment-gateway registration topics;
# those webhooks are not part of the order domain.
GATEWAY_TOPIC_KEY = "woocommerce.payments.gateways"


def _is_gateway_payload(payload: dict) -> bool:
    """Return True for payment-gateway registration payloads (unsupported)."""
    return GATEWAY_TOPIC_KEY in payload


def _compute_signature(body: bytes, secret: str) -> str:
    """Compute the WooCommerce HMAC-SHA256 webhook signature (hex)."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _verify_signature(body: bytes, header_value: str | None, secret: str) -> bool:
    """Constant-time comparison of the expected and received signature."""
    if not header_value:
        return False
    expected = _compute_signature(body, secret)
    return hmac.compare_digest(header_value, expected)


@router.post(
    "/woocommerce",
    response_model=WebhookResponse,
    summary="Receive WooCommerce ORDER_CREATED webhook",
)
async def receive_woocommerce_order(
    request: Request,
    response: Response,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> WebhookResponse:
    """Ingest a WooCommerce order webhook into the commercial loop."""
    trace_id = get_trace_id()
    body = await request.body()
    if not body:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="empty request body"
        )

    try:
        raw = json.loads(body)
    except json.JSONDecodeError as exc:
        logger.warning("webhook rejected: invalid JSON trace=%s", trace_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="payload must be valid JSON"
        ) from exc
    if not isinstance(raw, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="payload must be a JSON object",
        )
    if _is_gateway_payload(raw):
        logger.info("webhook rejected: unsupported gateway topic trace=%s", trace_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="unsupported webhook topic"
        )

    settings = get_settings()
    signature = request.headers.get(SIGNATURE_HEADER)
    if not _verify_signature(body, signature, settings.woocommerce_webhook_secret):
        logger.warning("webhook rejected: invalid signature trace=%s", trace_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid webhook signature"
        )

    try:
        payload = WebhookOrderPayload.model_validate(raw)
    except ValidationError as exc:
        logger.warning("webhook rejected: invalid payload trace=%s", trace_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid order payload: {exc.errors()[:3]}",
        ) from exc

    try:
        result = await order_service.ingest_order(
            db,
            payload,
            workspace_id=workspace_id,
            trace_id=trace_id,
        )
    except order_service.OrderIngestError:
        logger.exception("webhook failed: order ingestion error trace=%s", trace_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="order ingestion failed",
        ) from None

    response.status_code = (
        status.HTTP_201_CREATED if result.status == "created" else status.HTTP_200_OK
    )
    return result
