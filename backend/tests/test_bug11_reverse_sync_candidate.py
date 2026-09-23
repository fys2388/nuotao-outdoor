"""Regression test for BUG #11 (P1): WC 反向同步插入的 product 应自动标记为 candidate。

Runs with --noconftest (conftest imports auth.py which fails on fastapi 0.115
+ starlette 1.7 locally; CI image is fine).

Uses asyncio.run() directly instead of pytest-asyncio.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.woocommerce_sync_service import sync_products_to_db


def _wc_product(status: str = "publish") -> dict:
    return {
        "id": 2107,
        "sku": "WC-NEW-001",
        "name": "Reverse-sync new product",
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


def test_bug11_reverse_sync_insert_marks_as_candidate() -> None:
    """WC 反向同步插入新产品时，candidate_status='candidate' + funnel_stage='new'。"""
    ws = uuid4()
    session = AsyncMock()

    # existing=None means we're on the insert branch
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result_mock)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()

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
            patch(
                "app.services.woocommerce_sync_service._upsert_inventory_snapshot",
                new=AsyncMock(return_value="skipped"),
            ),
            patch("app.services.event_service.create_event", new=AsyncMock(return_value=MagicMock(id=1))),
        ):
            return await sync_products_to_db(session, workspace_id=ws)

    result = asyncio.run(_run())
    assert result["imported"] == 1

    # Extract the Product that was added
    added = session.add.call_args_list[0].args[0]
    assert added.source == "woocommerce"
    assert added.candidate_status == "candidate", (
        f"BUG #11 regression: WC 反向同步的 product 应 candidate_status='candidate', got {added.candidate_status!r}"
    )
    assert added.funnel_stage == "new", (
        f"BUG #11 regression: WC 反向同步的 product 应 funnel_stage='new', got {added.funnel_stage!r}"
    )
