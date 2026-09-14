"""Tests for product soft-delete (single + batch) service behaviour."""

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.event import EventLog
from app.models.product import Product
from app.services import product_service

WORKSPACE = DEFAULT_WORKSPACE_ID


def _make_product(workspace_id: object, sku: str, name: str | None = None) -> Product:
    return Product(workspace_id=workspace_id, sku=sku, name=name or f"Product {sku}")


async def _seed(session, *skus: str, workspace_id: object = WORKSPACE) -> dict[str, Product]:
    products = {sku: _make_product(workspace_id, sku) for sku in skus}
    for product in products.values():
        session.add(product)
    await session.flush()
    return products


@pytest.mark.asyncio
async def test_single_soft_delete_hides_from_list(db_session) -> None:
    """A deleted product disappears from list_products but keeps its row + timestamp."""
    await _seed(db_session, "SKU-A", "SKU-B")
    target = (
        await db_session.execute(select(Product).where(Product.sku == "SKU-A"))
    ).scalar_one()

    result = await product_service.soft_delete_products(
        db_session, workspace_id=WORKSPACE, product_ids=[target.id]
    )
    await db_session.flush()

    assert result.deleted == 1
    assert result.not_found == []

    rows, total = await product_service.list_products(
        db_session, workspace_id=WORKSPACE
    )
    assert total == 1
    assert [p.sku for p in rows] == ["SKU-B"]

    # The row is not physically removed; deleted_at is stamped.
    raw = (
        await db_session.execute(select(Product).where(Product.sku == "SKU-A"))
    ).scalar_one()
    assert raw.deleted_at is not None


@pytest.mark.asyncio
async def test_batch_soft_delete(db_session) -> None:
    """Batch delete removes several live rows and leaves the rest."""
    await _seed(db_session, "SKU-1", "SKU-2", "SKU-3")
    ids = [
        p.id
        for p in (
            await db_session.execute(
                select(Product).where(Product.sku.in_(["SKU-1", "SKU-2"]))
            )
        ).scalars().all()
    ]

    result = await product_service.soft_delete_products(
        db_session, workspace_id=WORKSPACE, product_ids=ids
    )
    assert result.deleted == 2

    _, total = await product_service.list_products(db_session, workspace_id=WORKSPACE)
    assert total == 1


@pytest.mark.asyncio
async def test_missing_and_double_delete_are_not_found(db_session) -> None:
    """Unknown or already-deleted IDs come back in not_found and do not count."""
    seeded = await _seed(db_session, "SKU-X")
    first = await product_service.soft_delete_products(
        db_session, workspace_id=WORKSPACE, product_ids=[seeded["SKU-X"].id]
    )
    assert first.deleted == 1

    ghost = uuid4()
    second = await product_service.soft_delete_products(
        db_session,
        workspace_id=WORKSPACE,
        product_ids=[seeded["SKU-X"].id, ghost],
    )
    assert second.deleted == 0
    assert set(second.not_found) == {seeded["SKU-X"].id, ghost}


@pytest.mark.asyncio
async def test_delete_is_scoped_to_workspace(db_session) -> None:
    """A product owned by another workspace cannot be deleted and stays live."""
    other_workspace = uuid4()
    foreign = _make_product(other_workspace, "SKU-FOREIGN")
    db_session.add(foreign)
    await db_session.flush()

    result = await product_service.soft_delete_products(
        db_session, workspace_id=WORKSPACE, product_ids=[foreign.id]
    )
    assert result.deleted == 0
    assert result.not_found == [foreign.id]
    # Service never touched this row, so it stays live.
    assert foreign.deleted_at is None


@pytest.mark.asyncio
async def test_same_sku_can_be_recreated_after_delete(db_session) -> None:
    """Partial unique index lets a soft-deleted SKU be created again as live."""
    original = _make_product(WORKSPACE, "SKU-DUP", "Old")
    db_session.add(original)
    await db_session.flush()

    await product_service.soft_delete_products(
        db_session, workspace_id=WORKSPACE, product_ids=[original.id]
    )
    await db_session.flush()

    recreated = _make_product(WORKSPACE, "SKU-DUP", "New")
    db_session.add(recreated)
    await db_session.flush()  # must not raise a uniqueness violation

    rows, total = await product_service.list_products(
        db_session, workspace_id=WORKSPACE
    )
    assert total == 1
    assert rows[0].name == "New"


@pytest.mark.asyncio
async def test_delete_writes_audit_event(db_session) -> None:
    """Every soft-deleted product emits a product.deleted event."""
    seeded = await _seed(db_session, "SKU-E")
    await product_service.soft_delete_products(
        db_session,
        workspace_id=WORKSPACE,
        product_ids=[seeded["SKU-E"].id],
        trace_id="trace-test",
    )
    events = (
        await db_session.execute(
            select(EventLog).where(EventLog.event_type == "product.deleted")
        )
    ).scalars().all()
    assert len(events) == 1
    assert events[0].entity_id == str(seeded["SKU-E"].id)
    assert events[0].trace_id == "trace-test"


@pytest.mark.asyncio
async def test_empty_id_list_is_noop(db_session) -> None:
    """An empty delete request changes nothing."""
    result = await product_service.soft_delete_products(
        db_session, workspace_id=WORKSPACE, product_ids=[]
    )
    assert result.deleted == 0
    assert result.not_found == []
