"""WooCommerce Clickback Events — SOP 阶段 ⑤「数据回流」.

BUG #18: 商品上架后，WC 前台的曝光、点击、加购、购买等事件回流到系统，
供选品评分模型、运营看板和复盘分析使用。

API 设计
--------
1. POST /webhooks/woocommerce/clickback  — WC 插件/自定义脚本推送事件
2. POST /wc-clickback/events             — 通用入库（带认证）
3. GET  /wc-clickback/events             — 查询产品回流数据（带认证）
4. GET  /wc-clickback/summary            — 产品回流汇总（带认证）
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import get_current_user, get_current_workspace_id
from app.core.config import get_settings
from app.core.database import get_db
from app.core.tracing import get_trace_id
from app.models.wc_clickback import CLICKBACK_EVENT_TYPES, WcClickbackEvent
from app.schemas.user import UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wc-clickback", tags=["wc-clickback"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[UserResponse, Depends(get_current_user)]

# 默认工作空间 ID（Webhook 不需要用户认证）。
DEFAULT_WORKSPACE_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


# ============================================
# 请求/响应模型
# ============================================

class ClickbackEventItem(BaseModel):
    """单条事件（webhook payload 中的元素）。"""
    product_id: str = Field(..., description="Product UUID")
    event_type: str = Field(..., description="Event type: impression/click/view/add_to_cart/purchase")
    count: int = Field(default=1, ge=1, description="Event count (batch)")
    window_start: str | None = Field(default=None, description="ISO datetime window start")
    window_end: str | None = Field(default=None, description="ISO datetime window end")
    source: str = Field(default="custom_webhook", description="Event source")
    raw_payload: dict | None = Field(default=None, description="Raw payload snapshot")


class ClickbackEventBatch(BaseModel):
    """批量事件入库请求。"""
    events: list[ClickbackEventItem] = Field(..., min_length=1)
    trace_id: str | None = Field(default=None)


class ClickbackEventResponse(BaseModel):
    """单条事件入库响应。"""
    id: str
    product_id: str
    event_type: str
    count: int
    window_start: str
    source: str
    created_at: str | None = None


class ClickbackSummary(BaseModel):
    """产品回流汇总。"""
    product_id: str
    event_type: str
    total_count: int
    last_window_start: str | None = None
    record_count: int


# ============================================
# Webhook 端点（无需认证，HMAC 签名验证）
# ============================================

SIGNATURE_HEADER = "x-wc-webhook-signature"


def _compute_signature(body: bytes, secret: str) -> str:
    import base64
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def _verify_signature(body: bytes, header_value: str | None, secret: str) -> bool:
    if not header_value:
        return False
    import base64
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected_base64 = base64.b64encode(digest).decode("utf-8")
    expected_hex = digest.hex()
    return hmac.compare_digest(header_value, expected_base64) or hmac.compare_digest(
        header_value, expected_hex
    )


@router.post(
    "/webhook",
    summary="接收 WC 点击回流事件 webhook",
)
async def receive_clickback_webhook(
    request: Request,
    db: DbSession,
) -> dict:
    """接收 WooCommerce 点击回流事件 webhook。

    支持的 payload 格式：
    1. 单条事件：{product_id, event_type, count, window_start, ...}
    2. 批量事件：{events: [{...}, ...]}
    """
    trace_id = get_trace_id(request)
    body = await request.body()

    # HMAC 签名验证（如果配置了 secret）。
    settings = get_settings()
    secret = getattr(settings, "woocommerce_webhook_secret", None)
    if secret:
        signature = request.headers.get(SIGNATURE_HEADER)
        if not _verify_signature(body, signature, secret):
            logger.warning("clickback webhook rejected: invalid signature trace=%s", trace_id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid webhook signature",
            )

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        logger.warning("clickback webhook rejected: invalid JSON trace=%s", trace_id)
        raise HTTPException(status_code=400, detail="invalid JSON payload")

    # 支持单条和批量两种格式。
    if isinstance(payload, dict) and "events" in payload:
        items = payload["events"]
        trace_id = payload.get("trace_id") or trace_id
    elif isinstance(payload, dict):
        items = [payload]
    elif isinstance(payload, list):
        items = payload
    else:
        raise HTTPException(status_code=400, detail="payload must be object or array")

    ingested = 0
    for item in items:
        event_type = item.get("event_type", "")
        if event_type not in CLICKBACK_EVENT_TYPES:
            logger.warning("skipping unknown event_type=%s trace=%s", event_type, trace_id)
            continue

        try:
            product_id = uuid.UUID(item["product_id"])
        except (KeyError, ValueError):
            logger.warning("skipping invalid product_id trace=%s", trace_id)
            continue

        # Parse window_start (default to now).
        ws_raw = item.get("window_start")
        if ws_raw:
            try:
                window_start = datetime.fromisoformat(ws_raw.replace("Z", "+00:00"))
            except ValueError:
                window_start = datetime.now(timezone.utc)
        else:
            window_start = datetime.now(timezone.utc)

        we_raw = item.get("window_end")
        window_end = None
        if we_raw:
            try:
                window_end = datetime.fromisoformat(we_raw.replace("Z", "+00:00"))
            except ValueError:
                pass

        count = item.get("count", 1)
        source = item.get("source", "custom_webhook")

        # UPSERT: find existing record with same product+type+window, update count.
        existing = await db.execute(
            select(WcClickbackEvent).where(
                WcClickbackEvent.workspace_id == DEFAULT_WORKSPACE_ID,
                WcClickbackEvent.product_id == product_id,
                WcClickbackEvent.event_type == event_type,
                WcClickbackEvent.window_start == window_start,
            )
        )
        row = existing.scalar_one_or_none()

        if row:
            row.count += count
            if window_end and (not row.window_end or row.window_end < window_end):
                row.window_end = window_end
            row.updated_at = datetime.now(timezone.utc)
        else:
            row = WcClickbackEvent(
                workspace_id=DEFAULT_WORKSPACE_ID,
                product_id=product_id,
                event_type=event_type,
                count=count,
                window_start=window_start,
                window_end=window_end,
                source=source,
                raw_payload=item.get("raw_payload"),
                trace_id=trace_id,
            )
            db.add(row)

        ingested += 1

    await db.commit()
    logger.info(
        "clickback webhook ingested=%d trace=%s", ingested, trace_id
    )
    return {
        "status": "ok",
        "ingested": ingested,
        "trace_id": trace_id,
    }


# ============================================
# REST API 端点（需要认证）
# ============================================


@router.post(
    "/events",
    response_model=list[ClickbackEventResponse],
    summary="批量入库点击回流事件",
)
async def create_clickback_events(
    req: ClickbackEventBatch,
    db: DbSession,
    user: CurrentUser,
) -> list[dict]:
    """批量入库点击回流事件（需要认证）。"""
    results = []
    trace_id = req.trace_id

    for item in req.events:
        if item.event_type not in CLICKBACK_EVENT_TYPES:
            continue

        try:
            product_id = uuid.UUID(item.product_id)
        except ValueError:
            continue

        ws_raw = item.window_start
        if ws_raw:
            try:
                window_start = datetime.fromisoformat(ws_raw.replace("Z", "+00:00"))
            except ValueError:
                window_start = datetime.now(timezone.utc)
        else:
            window_start = datetime.now(timezone.utc)

        we_raw = item.window_end
        window_end = None
        if we_raw:
            try:
                window_end = datetime.fromisoformat(we_raw.replace("Z", "+00:00"))
            except ValueError:
                pass

        # UPSERT
        existing = await db.execute(
            select(WcClickbackEvent).where(
                WcClickbackEvent.workspace_id == DEFAULT_WORKSPACE_ID,
                WcClickbackEvent.product_id == product_id,
                WcClickbackEvent.event_type == item.event_type,
                WcClickbackEvent.window_start == window_start,
            )
        )
        row = existing.scalar_one_or_none()

        if row:
            row.count += item.count
            if window_end and (not row.window_end or row.window_end < window_end):
                row.window_end = window_end
            row.updated_at = datetime.now(timezone.utc)
        else:
            row = WcClickbackEvent(
                workspace_id=DEFAULT_WORKSPACE_ID,
                product_id=product_id,
                event_type=item.event_type,
                count=item.count,
                window_start=window_start,
                window_end=window_end,
                source=item.source,
                raw_payload=item.raw_payload,
                trace_id=trace_id,
            )
            db.add(row)
            await db.flush()

        results.append({
            "id": str(row.id),
            "product_id": str(row.product_id),
            "event_type": row.event_type,
            "count": row.count,
            "window_start": row.window_start.isoformat(),
            "source": row.source,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        })

    await db.commit()
    return results


@router.get(
    "/events",
    response_model=list[dict],
    summary="查询产品点击回流事件",
)
async def list_clickback_events(
    db: DbSession,
    user: CurrentUser,
    product_id: str = Query(..., description="Product UUID"),
    event_type: str | None = Query(default=None, description="Filter by event type"),
    window_start: str | None = Query(default=None, description="ISO datetime window start"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    """查询产品的点击回流事件列表。"""
    try:
        pid = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid product_id UUID")

    query = select(WcClickbackEvent).where(
        WcClickbackEvent.workspace_id == DEFAULT_WORKSPACE_ID,
        WcClickbackEvent.product_id == pid,
    )
    if event_type:
        query = query.where(WcClickbackEvent.event_type == event_type)
    if window_start:
        try:
            ws = datetime.fromisoformat(window_start.replace("Z", "+00:00"))
            query = query.where(WcClickbackEvent.window_start >= ws)
        except ValueError:
            pass
    query = query.order_by(WcClickbackEvent.window_start.desc()).limit(limit).offset(offset)

    result = await db.execute(query)
    rows = result.scalars().all()
    return [r.to_dict() for r in rows]


@router.get(
    "/summary",
    response_model=list[ClickbackSummary],
    summary="产品点击回流汇总",
)
async def get_clickback_summary(
    db: DbSession,
    user: CurrentUser,
    product_id: str = Query(..., description="Product UUID"),
) -> list[dict]:
    """按事件类型汇总产品的点击回流数据。"""
    try:
        pid = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid product_id UUID")

    query = (
        select(
            WcClickbackEvent.product_id,
            WcClickbackEvent.event_type,
            func.sum(WcClickbackEvent.count).label("total_count"),
            func.max(WcClickbackEvent.window_start).label("last_window_start"),
            func.count(WcClickbackEvent.id).label("record_count"),
        )
        .where(
            WcClickbackEvent.workspace_id == DEFAULT_WORKSPACE_ID,
            WcClickbackEvent.product_id == pid,
        )
        .group_by(WcClickbackEvent.product_id, WcClickbackEvent.event_type)
    )

    result = await db.execute(query)
    rows = result.all()
    return [
        {
            "product_id": str(r.product_id),
            "event_type": r.event_type,
            "total_count": r.total_count,
            "last_window_start": r.last_window_start.isoformat() if r.last_window_start else None,
            "record_count": r.record_count,
        }
        for r in rows
    ]
