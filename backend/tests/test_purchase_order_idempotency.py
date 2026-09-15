"""采购单自动创建幂等性测试。

回归问题：Agent 补货链路曾缺少幂等，调度器对同一低库存商品反复触发，
堆积多张处于未结状态的重复/零成本采购单。约束：
- 同一商品已有未结 PO 时，再次自动补货必须去重，不得新增；
- 已进入 ordered 等终结/在途状态后，不拦截新建；
- 命中历史零成本“僵尸单”且本次带有效成本时，就地补齐。
"""

import pytest
from sqlalchemy import func, select
from uuid import UUID

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.product import Product
from app.models.supply_chain import PurchaseOrder, PurchaseOrderItem
from app.services.procurement_service import create_purchase_order

WORKSPACE = DEFAULT_WORKSPACE_ID


async def _seed_product(db_session, sku: str = "IDEM-001") -> str:
    product = Product(workspace_id=WORKSPACE, sku=sku, name=f"Product {sku}")
    db_session.add(product)
    await db_session.flush()
    return str(product.id)


async def _po_count(db_session) -> int:
    return (await db_session.execute(select(func.count(PurchaseOrder.id)))).scalar_one()


@pytest.mark.asyncio
async def test_existing_open_po_is_deduplicated(db_session) -> None:
    product_id = await _seed_product(db_session)
    params = {"unit_cost": 5.0, "workspace_id": str(WORKSPACE)}

    first = await create_purchase_order(db_session, product_id, 10, params)
    assert first["success"] is True
    assert not first.get("deduplicated")

    second = await create_purchase_order(db_session, product_id, 20, dict(params))
    assert second["success"] is True
    assert second.get("deduplicated") is True
    assert second["po_number"] == first["po_number"]

    assert await _po_count(db_session) == 1


@pytest.mark.asyncio
async def test_closed_status_does_not_block_new_po(db_session) -> None:
    product_id = await _seed_product(db_session, "IDEM-002")
    params = {"unit_cost": 5.0, "workspace_id": str(WORKSPACE)}

    first = await create_purchase_order(db_session, product_id, 10, params)
    po = (
        await db_session.execute(select(PurchaseOrder).where(PurchaseOrder.po_number == first["po_number"]))
    ).scalar_one()
    po.status = "ordered"
    await db_session.flush()

    second = await create_purchase_order(db_session, product_id, 10, dict(params))
    assert second["success"] is True
    assert not second.get("deduplicated")
    assert await _po_count(db_session) == 2


@pytest.mark.asyncio
async def test_zero_cost_open_po_is_patched_with_real_cost(db_session) -> None:
    product_id = await _seed_product(db_session, "IDEM-003")

    first = await create_purchase_order(
        db_session, product_id, 30, {"unit_cost": 0, "workspace_id": str(WORKSPACE)}
    )
    assert float(first["total"]) == 0.0

    second = await create_purchase_order(
        db_session, product_id, 30, {"unit_cost": 4.0, "workspace_id": str(WORKSPACE)}
    )
    assert second.get("deduplicated") is True
    assert second.get("cost_patched") is True
    assert await _po_count(db_session) == 1

    item = (
        await db_session.execute(
            select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == UUID(first["purchase_order_id"]))
        )
    ).scalar_one()
    assert float(item.unit_cost) == 4.0
    assert float(item.line_total) == 120.0
