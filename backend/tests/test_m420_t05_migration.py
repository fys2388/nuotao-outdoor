"""Tests for M4.2.0 T0.5 migration of base data models.

Verifies the new direct-input columns for M4.2.1 supplier intelligence and
M4.2.2/M4.2.4 cost/logistics reconciliation are readable and writable at the
model layer (in-memory SQLite via the shared ``db_session`` fixture):

- SupplierProfile.risk_score / risk_score_model_version / risk_score_calibrated_at
- ProductCost.source / confidence
- InventorySnapshot.reorder_point
- ShipmentRecord.promised_delivery / actual_cost / actual_cost_currency

None semantics are asserted too: unset fields stay NULL (never fabricated).
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.product import Product, ProductCost
from app.models.supply_chain import InventorySnapshot, ShipmentRecord, SupplierProfile

WORKSPACE = DEFAULT_WORKSPACE_ID


async def _seed_product(db_session) -> Product:
    product = Product(workspace_id=WORKSPACE, sku="T05-PROD", name="T0.5 Product")
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    return product


@pytest.mark.asyncio
async def test_supplier_profile_risk_score_roundtrip(db_session) -> None:
    """risk_score is persisted and read back; risk_level stays its default."""
    profile = SupplierProfile(
        workspace_id=WORKSPACE,
        risk_score=Decimal("45.5"),
        risk_score_model_version="v1",
        risk_score_calibrated_at=datetime(2026, 11, 22, tzinfo=UTC),
    )
    db_session.add(profile)
    await db_session.commit()

    row = (await db_session.execute(select(SupplierProfile))).scalar_one()
    assert row.risk_score == Decimal("45.5")
    assert row.risk_level == "low"
    assert row.risk_score_model_version == "v1"
    assert row.risk_score_calibrated_at is not None


@pytest.mark.asyncio
async def test_supplier_profile_risk_score_none_by_default(db_session) -> None:
    """A profile without calibration keeps risk_score NULL (never fabricated)."""
    profile = SupplierProfile(workspace_id=WORKSPACE)
    db_session.add(profile)
    await db_session.commit()

    row = (await db_session.execute(select(SupplierProfile))).scalar_one()
    assert row.risk_score is None
    assert row.risk_score_calibrated_at is None
    assert row.risk_level == "low"


@pytest.mark.asyncio
async def test_product_cost_source_confidence_roundtrip(db_session) -> None:
    """source/confidence are persisted and read back on a cost row."""
    product = await _seed_product(db_session)
    cost = ProductCost(
        workspace_id=WORKSPACE,
        product_id=product.id,
        source="1688",
        confidence=Decimal("0.6"),
    )
    db_session.add(cost)
    await db_session.commit()

    row = (await db_session.execute(select(ProductCost))).scalar_one()
    assert row.source == "1688"
    assert row.confidence == Decimal("0.6")


@pytest.mark.asyncio
async def test_inventory_snapshot_reorder_point_roundtrip(db_session) -> None:
    """reorder_point is persisted and read back on an inventory snapshot."""
    product = await _seed_product(db_session)
    snapshot = InventorySnapshot(
        workspace_id=WORKSPACE,
        product_id=product.id,
        quantity=100,
        reorder_point=15,
    )
    db_session.add(snapshot)
    await db_session.commit()

    row = (await db_session.execute(select(InventorySnapshot))).scalar_one()
    assert row.reorder_point == 15
    assert row.available == 0  # unchanged default calculation fields


@pytest.mark.asyncio
async def test_shipment_record_promised_delivery_and_actual_cost_roundtrip(
    db_session,
) -> None:
    """promised_delivery/actual_cost/currency are persisted and read back."""
    shipment = ShipmentRecord(
        workspace_id=WORKSPACE,
        carrier="Cainiao",
        promised_delivery=datetime(2026, 12, 1, tzinfo=UTC),
        actual_cost=Decimal("12.50"),
        actual_cost_currency="USD",
    )
    db_session.add(shipment)
    await db_session.commit()

    row = (await db_session.execute(select(ShipmentRecord))).scalar_one()
    assert row.promised_delivery is not None
    assert row.actual_cost == Decimal("12.50")
    assert row.actual_cost_currency == "USD"
