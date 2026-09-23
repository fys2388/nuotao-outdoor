"""Tests for BUG #5: WC 反向同步不应覆盖本地 status，但记录漂移。"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.services.woocommerce_sync_service import (
    convert_wc_product_to_internal,
    sync_products_to_db,
)


def _wc_product(status: str = "draft") -> dict:
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


@pytest.mark.asyncio
async def test_sync_existing_does_not_overwrite_local_status() -> None:
    """本地产品已存在且 status='draft'，WC 端 status='publish'，反向同步后本地 status 保持 draft。"""
    ws = uuid4()
    pid = uuid4()
    existing = Product(
        id=pid,
        workspace_id=ws,
        sku="WC-DRAFT-001",
        name="本地原名字",
        status="draft",
        candidate_status="approved",
        source="manual",
        tags=[],
        attributes={},
        meta={"local_key": "keep"},
        reject_reasons=[],
    )

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = existing
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result_mock)
    session.commit = AsyncMock()
    session.flush = AsyncMock()

    with (
        patch(
            "app.services.woocommerce_sync_service.fetch_woocommerce_products",
            return_value={"success": True, "products": [_wc_product("publish")], "pagination": {"total_pages": 1}},
        ),
        patch("app.services.woocommerce_sync_service._upsert_inventory_snapshot", new=AsyncMock(return_value="skipped")),
    ):
        result = await sync_products_to_db(session, workspace_id=ws)

    assert result["updated"] == 1
    assert existing.status == "draft"
    assert existing.candidate_status == "approved"
    assert existing.meta["woocommerce_status"] == "publish"
    assert existing.meta["local_key"] == "keep"
    assert existing.name == "Yueye Draft"  # 名称等仍同步


@pytest.mark.asyncio
async def test_sync_new_product_uses_wc_status_initial() -> None:
    """新产品（本地不存在）走新建分支，status 用 WC 端的映射值。"""
    ws = uuid4()

    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result_mock)
    session.commit = AsyncMock()
    session.flush = AsyncMock()

    with (
        patch(
            "app.services.woocommerce_sync_service.fetch_woocommerce_products",
            return_value={"success": True, "products": [_wc_product("publish")], "pagination": {"total_pages": 1}},
        ),
        patch("app.services.woocommerce_sync_service._upsert_inventory_snapshot", new=AsyncMock(return_value="skipped")),
    ):
        result = await sync_products_to_db(session, workspace_id=ws)

    assert result["imported"] == 1
    session.add.assert_called_once()
    new_product = session.add.call_args.args[0]
    assert new_product.status == "active"  # publish -> active


def test_convert_wc_product_returns_woocommerce_status() -> None:
    """convert_wc_product_to_internal 返回体里应带 woocommerce_status 字段。"""
    data = convert_wc_product_to_internal(_wc_product("publish"))
    assert data["woocommerce_status"] == "publish"
    assert data["status"] == "active"  # 新建时的映射

    data2 = convert_wc_product_to_internal(_wc_product("draft"))
    assert data2["woocommerce_status"] == "draft"
    assert data2["status"] == "draft"
