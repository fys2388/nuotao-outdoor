"""Regression test for BUG #13: WC 端 unauthorized publish audit event.

Runs with --noconftest (conftest imports auth.py which fails on fastapi 0.115
+ starlette 1.7 in this environment; CI image is fine).

Uses asyncio.run() directly instead of pytest-asyncio to avoid the local
environment's missing pytest plugin.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.product import Product
from app.services.woocommerce_sync_service import sync_products_to_db


def _wc_product(status: str = "publish") -> dict:
    return {
        "id": 2106,
        "sku": "WC-DRAFT-001",
        "name": "Yueye Draft",
        "description": "desc",
        "status": status,
        "price": "15.80",
        "regular_price": "15.80",
        "type": "simple",
        "categories": [],
        "tags": [],
        "images": [],
        "attributes": [],
        "weight": "",
        "dimensions": {},
        "manage_stock": True,
        "stock_quantity": 5,
        "in_stock": True,
        "stock_status": "instock",
        "total_sales": 0,
        "average_rating": None,
        "rating_count": 0,
    }


def test_bug13_unauthorized_publish_audit_event() -> None:
    """本地 draft，WC publish → 写 product.wc_unauthorized_publish 审计事件。"""
    ws = uuid4()
    pid = uuid4()
    existing = Product(
        id=pid,
        workspace_id=ws,
        sku="WC-DRAFT-001",
        name="Local name",
        status="draft",
        candidate_status="approved",
        source="manual",
        tags=[],
        attributes={},
        meta={},
        reject_reasons=[],
    )
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = existing
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result_mock)
    session.commit = AsyncMock()
    session.flush = AsyncMock()

    mock_create_event = AsyncMock(return_value=MagicMock(id=1))

    async def _run():
        with (
            patch(
                "app.services.woocommerce_sync_service.fetch_woocommerce_products",
                return_value={
                    "success": True,
                    "products": [_wc_product("publish")],
                    "pagination": {"total_pages": 1},
                },
            ),
            patch("app.services.woocommerce_sync_service._upsert_inventory_snapshot", new=AsyncMock(return_value="skipped")),
            patch("app.services.event_service.create_event", new=mock_create_event),
        ):
            return await sync_products_to_db(session, workspace_id=ws)

    result = asyncio.run(_run())

    assert result["updated"] == 1
    assert result.get("status_drift", 0) >= 1

    event_types = [
        c.kwargs.get("event_type") or (c.args[1] if len(c.args) > 1 else None)
        for c in mock_create_event.call_args_list
    ]
    assert "product.wc_unauthorized_publish" in event_types, (
        f"expected unauthorized_publish event, got: {event_types}"
    )
    authz_call = next(
        c for c in mock_create_event.call_args_list
        if c.kwargs.get("event_type") == "product.wc_unauthorized_publish"
    )
    payload = authz_call.kwargs.get("payload") or {}
    assert payload["local_status"] == "draft"
    assert payload["wc_status"] == "published"
    assert "system:wc-sync" in payload["actor"]


def test_bug13_draft_wc_does_not_emit_unauthorized_publish() -> None:
    """WC 端也是 draft → 不写 unauthorized_publish 事件。"""
    ws = uuid4()
    pid = uuid4()
    existing = Product(
        id=pid,
        workspace_id=ws,
        sku="WC-002",
        name="Local name",
        status="draft",
        candidate_status="approved",
        source="manual",
        tags=[],
        attributes={},
        meta={},
        reject_reasons=[],
    )
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = existing
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result_mock)
    session.commit = AsyncMock()
    session.flush = AsyncMock()

    mock_create_event = AsyncMock(return_value=MagicMock(id=1))

    async def _run():
        with (
            patch(
                "app.services.woocommerce_sync_service.fetch_woocommerce_products",
                return_value={
                    "success": True,
                    "products": [_wc_product("draft")],
                    "pagination": {"total_pages": 1},
                },
            ),
            patch("app.services.woocommerce_sync_service._upsert_inventory_snapshot", new=AsyncMock(return_value="skipped")),
            patch("app.services.event_service.create_event", new=mock_create_event),
        ):
            return await sync_products_to_db(session, workspace_id=ws)

    asyncio.run(_run())

    event_types = [
        c.kwargs.get("event_type") or (c.args[1] if len(c.args) > 1 else None)
        for c in mock_create_event.call_args_list
    ]
    assert "product.wc_unauthorized_publish" not in event_types
