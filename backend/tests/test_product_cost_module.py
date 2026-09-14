"""Tests for product cost management: overview, versioned manual upsert, profit."""

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.event import EventLog
from app.models.product import Product
from app.models.product_intelligence import ProductCostSnapshot
from app.schemas.product_cost import ProductCostUpsertRequest
from app.services import product_cost_service as pcs

WORKSPACE = DEFAULT_WORKSPACE_ID
D = Decimal


def _product(sku: str, *, meta: dict | None = None, workspace_id: object = WORKSPACE) -> Product:
    return Product(workspace_id=workspace_id, sku=sku, name=f"Product {sku}", meta=meta or {})


def _cost_request(**overrides) -> ProductCostUpsertRequest:
    base = {
        "purchase_cost": D("5.00"),
        "domestic_shipping": D("0.50"),
        "first_leg_shipping": D("1.00"),
        "last_leg_shipping": D("0.80"),
        "packaging": D("0.20"),
        "tax_estimate": D("0.30"),
        "handling": D("0.20"),
        "payment_fee": D("0.30"),
        "marketing_amortization": D("0.40"),
        "after_sales_loss": D("0.10"),
    }
    base.update(overrides)
    return ProductCostUpsertRequest(**base)


@pytest.mark.asyncio
async def test_landed_breakdown_international_falls_back_to_legs() -> None:
    international, landed, legacy = pcs.landed_breakdown(
        purchase_cost=D("5"),
        domestic_shipping=D("0.5"),
        first_leg_shipping=D("1"),
        last_leg_shipping=D("0.8"),
        international_shipping=None,
        packaging=D("0.2"),
        tax_estimate=D("0.3"),
        handling=D("0.2"),
    )
    assert international == D("1.80")
    assert landed == D("8.00")
    assert legacy == D("7.30")


@pytest.mark.asyncio
async def test_first_upsert_is_v1_and_writes_snapshot_and_audit(db_session) -> None:
    product = _product("SKU-C1")
    db_session.add(product)
    await db_session.flush()

    result = await pcs.upsert_product_cost(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product.id,
        data=_cost_request(),
        trace_id="trace-cost",
    )
    await db_session.flush()

    assert result["version"] == "v1"
    assert result["total_landed_cost"] == D("8.00")

    snapshots = (
        (
            await db_session.execute(
                select(ProductCostSnapshot).where(
                    ProductCostSnapshot.product_id == product.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(snapshots) == 1
    assert snapshots[0].source == "manual"
    assert snapshots[0].trace_id == "trace-cost"

    events = (
        (
            await db_session.execute(
                select(EventLog).where(EventLog.event_type == "product.cost.updated")
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert events[0].entity_id == str(product.id)


@pytest.mark.asyncio
async def test_second_upsert_bumps_version_and_appends_history(db_session) -> None:
    product = _product("SKU-C2")
    db_session.add(product)
    await db_session.flush()

    await pcs.upsert_product_cost(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product.id,
        data=_cost_request(),
        trace_id=None,
    )
    second = await pcs.upsert_product_cost(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product.id,
        data=_cost_request(purchase_cost=D("6.00")),
        trace_id=None,
    )
    await db_session.flush()

    assert second["version"] == "v2"
    # History is append-only: both versions remain.
    snapshots = (
        (
            await db_session.execute(
                select(ProductCostSnapshot)
                .where(ProductCostSnapshot.product_id == product.id)
                .order_by(ProductCostSnapshot.version)
            )
        )
        .scalars()
        .all()
    )
    assert [s.version for s in snapshots] == ["v1", "v2"]

    latest = await pcs.latest_cost_for_product(
        db_session, workspace_id=WORKSPACE, product_id=product.id
    )
    assert latest is not None
    assert latest.version == "v2"
    assert latest.purchase_cost == D("6.00")


@pytest.mark.asyncio
async def test_upsert_unknown_product_raises(db_session) -> None:
    with pytest.raises(pcs.ProductCostError, match="not found"):
        await pcs.upsert_product_cost(
            db_session,
            workspace_id=WORKSPACE,
            product_id=uuid4(),
            data=_cost_request(),
            trace_id=None,
        )


@pytest.mark.asyncio
async def test_upsert_is_scoped_to_workspace(db_session) -> None:
    foreign = _product("SKU-FOREIGN", workspace_id=uuid4())
    db_session.add(foreign)
    await db_session.flush()

    with pytest.raises(pcs.ProductCostError, match="not found"):
        await pcs.upsert_product_cost(
            db_session,
            workspace_id=WORKSPACE,
            product_id=foreign.id,
            data=_cost_request(),
            trace_id=None,
        )


@pytest.mark.asyncio
async def test_profit_analysis_missing_cost_withholds_margin(db_session) -> None:
    product = _product("SKU-NC", meta={"regular_price": "19.99"})
    db_session.add(product)
    await db_session.flush()

    analysis = await pcs.profit_analysis(
        db_session, workspace_id=WORKSPACE, product_id=product.id
    )
    assert analysis["cost_status"] == "MISSING"
    assert analysis["contribution_margin"] is None
    assert analysis["sale_price"] == D("19.99")


@pytest.mark.asyncio
async def test_profit_analysis_known_cost_computes_margin(db_session) -> None:
    product = _product("SKU-PF", meta={"regular_price": "19.99"})
    db_session.add(product)
    await db_session.flush()
    await pcs.upsert_product_cost(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product.id,
        data=_cost_request(),
        trace_id=None,
    )

    analysis = await pcs.profit_analysis(
        db_session, workspace_id=WORKSPACE, product_id=product.id
    )
    assert analysis["cost_status"] == "KNOWN"
    assert analysis["total_landed_cost"] == D("8.00")
    assert analysis["period_cost"] == D("0.80")  # payment + marketing + after-sales
    assert analysis["breakeven_price"] == D("8.80")
    assert analysis["total_cost"] == D("8.80")
    assert analysis["contribution_margin"] == D("11.19")
    assert analysis["contribution_margin_rate"] == D("0.5598")  # 11.19 / 19.99

    # What-if sale price overrides the meta reference price.
    what_if = await pcs.profit_analysis(
        db_session, workspace_id=WORKSPACE, product_id=product.id, sale_price=D("9.00")
    )
    assert what_if["sale_price"] == D("9.00")
    assert what_if["contribution_margin"] == D("0.20")


@pytest.mark.asyncio
async def test_overview_reports_coverage_and_derived_margin(db_session) -> None:
    with_cost = _product("SKU-WITH", meta={"sale_price": "19.99"})
    no_cost = _product("SKU-WITHOUT")
    db_session.add_all([with_cost, no_cost])
    await db_session.flush()
    await pcs.upsert_product_cost(
        db_session,
        workspace_id=WORKSPACE,
        product_id=with_cost.id,
        data=_cost_request(),
        trace_id=None,
    )

    overview = await pcs.list_cost_overview(db_session, workspace_id=WORKSPACE)
    assert overview["total"] == 2
    assert overview["known"] == 1
    assert overview["missing"] == 1
    by_sku = {row["sku"]: row for row in overview["items"]}
    assert by_sku["SKU-WITH"]["has_cost"] is True
    assert by_sku["SKU-WITH"]["total_landed_cost"] == D("8.00")
    assert by_sku["SKU-WITH"]["contribution_margin"] == D("11.19")
    assert by_sku["SKU-WITHOUT"]["has_cost"] is False

    known_only = await pcs.list_cost_overview(
        db_session, workspace_id=WORKSPACE, cost_status="known"
    )
    assert known_only["total"] == 1
    assert known_only["items"][0]["sku"] == "SKU-WITH"

    missing_only = await pcs.list_cost_overview(
        db_session, workspace_id=WORKSPACE, cost_status="missing"
    )
    assert missing_only["total"] == 1
    assert missing_only["items"][0]["sku"] == "SKU-WITHOUT"


@pytest.mark.asyncio
async def test_overview_hides_soft_deleted(db_session) -> None:
    from app.services import product_service

    live = _product("SKU-LIVE")
    dead = _product("SKU-DEAD")
    db_session.add_all([live, dead])
    await db_session.flush()
    await product_service.soft_delete_products(
        db_session, workspace_id=WORKSPACE, product_ids=[dead.id]
    )

    overview = await pcs.list_cost_overview(db_session, workspace_id=WORKSPACE)
    assert overview["total"] == 1
    assert overview["items"][0]["sku"] == "SKU-LIVE"
