"""Tests for BUG #6: 候选通过前必须已完成定价。

覆盖：
- candidate -> approved 缺零售价时被拒
- candidate -> approved 缺采购成本时被拒
- candidate -> approved 定价齐全时通过
- candidate -> rejected 不检查定价（淘汰不受定价约束）
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product, ProductCost
from app.services.product_intelligence import (
    ProductIntelligenceError,
    update_candidate_status,
)


def _make_session_with_product(product: Product) -> AsyncSession:
    """session.execute() 只服务 update_candidate_status 的 product 查询。

    成本查询通过 patch 掉 latest_cost_for_product 直接返回结果。
    """
    product_result = MagicMock()
    product_result.scalar_one_or_none.return_value = product
    session = AsyncMock()
    session.execute = AsyncMock(return_value=product_result)
    session.flush = AsyncMock()
    return session


def _build_product(candidate_status: str, meta: dict | None = None) -> Product:
    pid = uuid.uuid4()
    ws = uuid.uuid4()
    return Product(
        id=pid,
        workspace_id=ws,
        sku="TEST-SKU",
        name="test product",
        status="candidate",
        candidate_status=candidate_status,
        source="manual",
        tags=[],
        attributes={},
        meta=meta or {},
        reject_reasons=[],
    )


def _build_cost(purchase_cost: Decimal) -> ProductCost:
    return ProductCost(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        product_id=uuid.uuid4(),
        purchase_cost=purchase_cost,
    )


@pytest.mark.asyncio
async def test_candidate_to_approved_blocked_without_retail_price() -> None:
    """缺零售价时，candidate -> approved 被拒。"""
    product = _build_product(candidate_status="candidate", meta={})
    session = _make_session_with_product(product)

    with patch(
        "app.services.product_cost_service.latest_cost_for_product",
        new=AsyncMock(return_value=_build_cost(Decimal("10.00"))),
    ):
        with pytest.raises(ProductIntelligenceError, match="零售价"):
            await update_candidate_status(
                session,
                workspace_id=product.workspace_id,
                product_id=product.id,
                new_status="approved",
                actor="admin",
            )


@pytest.mark.asyncio
async def test_candidate_to_approved_blocked_without_purchase_cost() -> None:
    """有零售价但缺采购成本时，candidate -> approved 被拒。"""
    product = _build_product(
        candidate_status="candidate",
        meta={"price": "25.00"},
    )
    session = _make_session_with_product(product)

    with patch(
        "app.services.product_cost_service.latest_cost_for_product",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(ProductIntelligenceError, match="采购成本"):
            await update_candidate_status(
                session,
                workspace_id=product.workspace_id,
                product_id=product.id,
                new_status="approved",
                actor="admin",
            )


@pytest.mark.asyncio
async def test_candidate_to_approved_passes_when_pricing_complete() -> None:
    """零售价 + 采购成本 齐全时，candidate -> approved 通过。"""
    product = _build_product(
        candidate_status="candidate",
        meta={"price": "25.00"},
    )
    session = _make_session_with_product(product)

    with (
        patch(
            "app.services.product_cost_service.latest_cost_for_product",
            new=AsyncMock(return_value=_build_cost(Decimal("10.00"))),
        ),
        patch(
            "app.services.product_intelligence.event_service.create_event",
            new=AsyncMock(),
        ),
    ):
        result = await update_candidate_status(
            session,
            workspace_id=product.workspace_id,
            product_id=product.id,
            new_status="approved",
            actor="admin",
        )

    assert result.candidate_status == "approved"


@pytest.mark.asyncio
async def test_candidate_to_rejected_skips_pricing_check() -> None:
    """candidate -> rejected 不检查定价（淘汰不受定价约束）。"""
    product = _build_product(candidate_status="candidate", meta={})
    session = _make_session_with_product(product)

    # 不 patch latest_cost_for_product，让它是原实现。
    # 如果 update_candidate_status 在 rejected 分支错误地调用了成本查询，
    # session.execute 会额外触发一次调用；这里断言只调用了 1 次。
    with patch(
        "app.services.product_intelligence.event_service.create_event",
        new=AsyncMock(),
    ):
        result = await update_candidate_status(
            session,
            workspace_id=product.workspace_id,
            product_id=product.id,
            new_status="rejected",
            actor="admin",
        )

    assert result.candidate_status == "rejected"
    # 只调用了 1 次（product 查询），没有 cost 查询
    assert session.execute.await_count == 1, (
        f"rejected 分支不应调用成本查询；实际调用 {session.execute.await_count} 次"
    )
