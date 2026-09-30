"""P2-9 cost coverage governance tests.

Covers:
- Effective-cost classification (missing / invalid / known)
- profit_analysis withholds margin for an invalid (zero) cost row
- cost overview counters use effective cost semantics
- Product-level gap list (missing + invalid, filters, workspace isolation)
- Transaction-level gap list (missing cost / archived product / untraceable item)
  and its resolution after the cost is filled
- Auditable batch cost fill (all success, partial failure, version bump, events)
- API endpoints for gaps and batch fill
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.event import EventLog
from app.models.order import Order, OrderItem
from app.models.product import Product, ProductCost
from app.schemas.product_cost import ProductCostUpsertRequest
from app.services import product_cost_service as pcs

WORKSPACE = UUID("00000000-0000-0000-0000-000000000001")
OTHER_WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")


def _effective_cost_data() -> ProductCostUpsertRequest:
    return ProductCostUpsertRequest(
        currency="USD",
        purchase_cost=Decimal("20.00"),
        domestic_shipping=Decimal("2.00"),
        first_leg_shipping=Decimal("3.00"),
        last_leg_shipping=Decimal("4.00"),
        international_shipping=Decimal("25.00"),
        packaging=Decimal("1.00"),
        tax_estimate=Decimal("2.00"),
        handling=Decimal("1.00"),
        payment_fee=Decimal("3.00"),
        marketing_amortization=Decimal("2.00"),
        after_sales_loss=Decimal("2.00"),
    )


def _effective_cost_payload() -> dict:
    """model_dump() with Decimals stringified so httpx JSON can encode them."""
    return {
        key: (str(value) if isinstance(value, Decimal) else value)
        for key, value in _effective_cost_data().model_dump().items()
    }


@pytest_asyncio.fixture
async def product_without_cost(db_session):
    product = Product(
        workspace_id=WORKSPACE,
        sku="GAP-MISSING-001",
        name="No Cost Product",
        status="active",
        target_market="US",
        meta={"regular_price": "29.99"},
    )
    db_session.add(product)
    await db_session.flush()
    return product


@pytest_asyncio.fixture
async def product_with_invalid_cost(db_session):
    product = Product(
        workspace_id=WORKSPACE,
        sku="GAP-INVALID-001",
        name="Invalid Cost Product",
        status="active",
        target_market="US",
        meta={"regular_price": "29.99"},
    )
    db_session.add(product)
    await db_session.flush()
    cost = ProductCost(
        workspace_id=WORKSPACE,
        product_id=product.id,
        currency="USD",
        purchase_cost=Decimal("0"),
        total_landed_cost=Decimal("0"),
        version="v1",
    )
    db_session.add(cost)
    await db_session.flush()
    return product


@pytest_asyncio.fixture
async def product_with_zero_landed_cost(db_session):
    product = Product(
        workspace_id=WORKSPACE,
        sku="GAP-INVALID-LANDED-001",
        name="Zero Landed Product",
        status="active",
        target_market="US",
        meta={"regular_price": "29.99"},
    )
    db_session.add(product)
    await db_session.flush()
    cost = ProductCost(
        workspace_id=WORKSPACE,
        product_id=product.id,
        currency="USD",
        purchase_cost=Decimal("5.00"),
        total_landed_cost=Decimal("0"),
        version="v1",
    )
    db_session.add(cost)
    await db_session.flush()
    return product


@pytest_asyncio.fixture
async def product_with_effective_cost(db_session):
    product = Product(
        workspace_id=WORKSPACE,
        sku="GAP-KNOWN-001",
        name="Known Cost Product",
        status="active",
        target_market="US",
        meta={"regular_price": "49.99"},
    )
    db_session.add(product)
    await db_session.flush()
    await pcs.upsert_product_cost(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product.id,
        data=_effective_cost_data(),
        trace_id="test-effective",
    )
    return product


# --------------------------------------------------------------------------- #
# Effective-cost classification
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_is_effective_cost_classification(
    db_session,
    product_without_cost,
    product_with_invalid_cost,
    product_with_effective_cost,
) -> None:
    missing = await pcs.latest_cost_for_product(
        db_session, workspace_id=WORKSPACE, product_id=product_without_cost.id
    )
    invalid = await pcs.latest_cost_for_product(
        db_session, workspace_id=WORKSPACE, product_id=product_with_invalid_cost.id
    )
    known = await pcs.latest_cost_for_product(
        db_session, workspace_id=WORKSPACE, product_id=product_with_effective_cost.id
    )

    assert pcs.is_effective_cost(missing) is False
    assert pcs.cost_gap_reason(missing) == "missing"

    assert pcs.is_effective_cost(invalid) is False
    assert pcs.cost_gap_reason(invalid) == "invalid_zero_purchase"

    assert pcs.is_effective_cost(known) is True
    assert pcs.cost_gap_reason(known) is None


@pytest.mark.asyncio
async def test_invalid_zero_landed_classification(
    db_session, product_with_zero_landed_cost
) -> None:
    cost = await pcs.latest_cost_for_product(
        db_session, workspace_id=WORKSPACE, product_id=product_with_zero_landed_cost.id
    )
    assert pcs.is_effective_cost(cost) is False
    assert pcs.cost_gap_reason(cost) == "invalid_zero_landed"

    gaps = await pcs.list_product_cost_gaps(
        db_session, workspace_id=WORKSPACE, gap_type="invalid", limit=100, offset=0
    )
    assert gaps["items"][0]["sku"] == "GAP-INVALID-LANDED-001"
    assert gaps["items"][0]["gap_reason"] == "invalid_zero_landed"


@pytest.mark.asyncio
async def test_newest_row_wins(db_session) -> None:
    """A newer invalid row replaces an older effective row in every view."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="GAP-STALE-001",
        name="Stale Effective Product",
        status="active",
        target_market="US",
        meta={"regular_price": "39.99"},
    )
    db_session.add(product)
    await db_session.flush()

    await pcs.upsert_product_cost(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product.id,
        data=_effective_cost_data(),
        trace_id="test-v1",
    )
    zero_data = ProductCostUpsertRequest(
        currency="USD",
        purchase_cost=Decimal("0"),
        domestic_shipping=Decimal("0"),
        first_leg_shipping=Decimal("0"),
        last_leg_shipping=Decimal("0"),
        packaging=Decimal("0"),
        tax_estimate=Decimal("0"),
        handling=Decimal("0"),
        payment_fee=Decimal("0"),
        marketing_amortization=Decimal("0"),
        after_sales_loss=Decimal("0"),
    )
    await pcs.upsert_product_cost(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product.id,
        data=zero_data,
        trace_id="test-v2",
    )

    cost = await pcs.latest_cost_for_product(
        db_session, workspace_id=WORKSPACE, product_id=product.id
    )
    assert cost.version == "v2"
    assert pcs.is_effective_cost(cost) is False

    overview = await pcs.list_cost_overview(
        db_session, workspace_id=WORKSPACE, limit=100, offset=0
    )
    assert overview["known"] == 0
    assert overview["invalid"] == 1

    gaps = await pcs.list_product_cost_gaps(
        db_session, workspace_id=WORKSPACE, gap_type="all", limit=100, offset=0
    )
    assert {item["sku"] for item in gaps["items"]} == {"GAP-STALE-001"}

    profit = await pcs.profit_analysis(
        db_session, workspace_id=WORKSPACE, product_id=product.id
    )
    assert profit["cost_status"] == "MISSING"


@pytest.mark.asyncio
async def test_list_product_cost_gaps(db_session, product_without_cost, product_with_invalid_cost, product_with_effective_cost) -> None:
    result = await pcs.list_product_cost_gaps(
        db_session, workspace_id=WORKSPACE, gap_type="all", limit=100, offset=0
    )
    by_sku = {item["sku"]: item for item in result["items"]}
    assert by_sku["GAP-MISSING-001"]["gap_type"] == "missing"
    assert by_sku["GAP-MISSING-001"]["gap_reason"] == "missing"
    assert by_sku["GAP-INVALID-001"]["gap_type"] == "invalid"
    assert by_sku["GAP-INVALID-001"]["gap_reason"] == "invalid_zero_purchase"
    assert "GAP-KNOWN-001" not in by_sku
    assert result["known"] == 1
    assert result["missing"] == 1
    assert result["invalid"] == 1
    assert result["total"] == 2

    missing_only = await pcs.list_product_cost_gaps(
        db_session, workspace_id=WORKSPACE, gap_type="missing", limit=100, offset=0
    )
    assert {item["sku"] for item in missing_only["items"]} == {"GAP-MISSING-001"}

    invalid_only = await pcs.list_product_cost_gaps(
        db_session, workspace_id=WORKSPACE, gap_type="invalid", limit=100, offset=0
    )
    assert {item["sku"] for item in invalid_only["items"]} == {"GAP-INVALID-001"}


@pytest.mark.asyncio
async def test_cost_overview_effective_counters(db_session, product_without_cost, product_with_invalid_cost, product_with_effective_cost) -> None:
    overview = await pcs.list_cost_overview(
        db_session, workspace_id=WORKSPACE, limit=100, offset=0
    )
    assert overview["known"] == 1
    assert overview["missing"] == 2  # missing row + invalid row
    assert overview["invalid"] == 1

    known_rows = await pcs.list_cost_overview(
        db_session, workspace_id=WORKSPACE, cost_status="known", limit=100, offset=0
    )
    assert {row["sku"] for row in known_rows["items"]} == {"GAP-KNOWN-001"}

    invalid_rows = await pcs.list_cost_overview(
        db_session, workspace_id=WORKSPACE, cost_status="invalid", limit=100, offset=0
    )
    assert {row["sku"] for row in invalid_rows["items"]} == {"GAP-INVALID-001"}
    row = invalid_rows["items"][0]
    assert row["has_cost"] is True
    assert row["has_effective_cost"] is False
    assert row["cost_gap_reason"] == "invalid_zero_purchase"


@pytest.mark.asyncio
async def test_cost_overview_withholds_margin_for_invalid_cost(
    db_session, product_with_invalid_cost, product_with_effective_cost
) -> None:
    """The overview table must not render "sale price - 0" as 100% margin.

    Zero-cost placeholder rows carry a reference price, so an ungated margin
    calculation would show contribution_margin == sale_price and margin_rate == 1.0
    while profit_analysis correctly withholds it. Both surfaces must agree.
    """
    overview = await pcs.list_cost_overview(
        db_session, workspace_id=WORKSPACE, limit=100, offset=0
    )
    by_sku = {row["sku"]: row for row in overview["items"]}

    invalid_row = by_sku["GAP-INVALID-001"]
    assert invalid_row["has_effective_cost"] is False
    assert invalid_row["sale_price"] == Decimal("29.99")
    assert invalid_row["contribution_margin"] is None
    assert invalid_row["margin_rate"] is None

    known_row = by_sku["GAP-KNOWN-001"]
    assert known_row["has_effective_cost"] is True
    assert known_row["contribution_margin"] is not None
    assert known_row["margin_rate"] is not None


# --------------------------------------------------------------------------- #
# Fake-margin protection
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_profit_analysis_withholds_margin_for_invalid_cost(
    db_session, product_with_invalid_cost
) -> None:
    result = await pcs.profit_analysis(
        db_session, workspace_id=WORKSPACE, product_id=product_with_invalid_cost.id
    )
    assert result["cost_status"] == "MISSING"
    assert result["contribution_margin"] is None
    assert result["contribution_margin_rate"] is None
    assert result["markup_rate"] is None
    assert result["breakeven_price"] == Decimal("0.00")
    assert result["total_cost"] is None


@pytest.mark.asyncio
async def test_profit_analysis_computes_margin_for_effective_cost(
    db_session, product_with_effective_cost
) -> None:
    result = await pcs.profit_analysis(
        db_session, workspace_id=WORKSPACE, product_id=product_with_effective_cost.id
    )
    assert result["cost_status"] == "KNOWN"
    assert result["contribution_margin"] is not None
    assert result["contribution_margin_rate"] is not None
    assert result["breakeven_price"] > Decimal("0")


# --------------------------------------------------------------------------- #
# Transaction-level gaps
# --------------------------------------------------------------------------- #


async def _make_order(db_session, external_id: str, product_id, *, workspace=WORKSPACE) -> Order:
    order = Order(
        workspace_id=workspace,
        external_order_id=external_id,
        status="received",
        payment_status="paid",
        currency="USD",
        subtotal=Decimal("60.00"),
        shipping_total=Decimal("10.00"),
        total=Decimal("70.00"),
    )
    db_session.add(order)
    await db_session.flush()
    item = OrderItem(
        order_id=order.id,
        workspace_id=workspace,
        product_id=product_id,
        sku="ITEM-SKU",
        name="Line Item",
        quantity=1,
        unit_price=Decimal("60.00"),
        line_total=Decimal("60.00"),
    )
    db_session.add(item)
    await db_session.flush()
    return order


@pytest.mark.asyncio
async def test_transaction_gap_missing_cost(
    db_session, product_without_cost
) -> None:
    order = await _make_order(db_session, "GAP-ORD-001", product_without_cost.id)
    result = await pcs.list_transaction_cost_gaps(
        db_session, workspace_id=WORKSPACE, limit=100, offset=0
    )
    assert result["total"] == 1
    row = result["items"][0]
    assert row["order_id"] == order.id
    assert row["order_number"] == "GAP-ORD-001"
    assert row["gap_item_count"] == 1
    assert row["gap_reasons"] == ["missing_cost"]
    assert result["gap_line_count"] == 1
    assert result["gap_line_total"] == Decimal("60.00")

    # Filling the cost removes the order from the gap list.
    await pcs.upsert_product_cost(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product_without_cost.id,
        data=_effective_cost_data(),
        trace_id="test-fill",
    )
    result = await pcs.list_transaction_cost_gaps(
        db_session, workspace_id=WORKSPACE, limit=100, offset=0
    )
    assert result["total"] == 0


@pytest.mark.asyncio
async def test_transaction_gap_untraceable_item(db_session) -> None:
    order = await _make_order(db_session, "GAP-ORD-002", None)
    result = await pcs.list_transaction_cost_gaps(
        db_session, workspace_id=WORKSPACE, limit=100, offset=0
    )
    assert result["total"] == 1
    assert result["items"][0]["order_id"] == order.id
    assert result["items"][0]["gap_reasons"] == ["product_missing"]


@pytest.mark.asyncio
async def test_transaction_gap_archived_product(
    db_session, product_with_effective_cost
) -> None:
    product_with_effective_cost.deleted_at = datetime.now(UTC)
    await db_session.flush()
    order = await _make_order(db_session, "GAP-ORD-003", product_with_effective_cost.id)
    result = await pcs.list_transaction_cost_gaps(
        db_session, workspace_id=WORKSPACE, limit=100, offset=0
    )
    assert result["total"] == 1
    assert result["items"][0]["order_id"] == order.id
    assert result["items"][0]["gap_reasons"] == ["product_archived"]


@pytest.mark.asyncio
async def test_transaction_gap_workspace_isolation(
    db_session, product_without_cost
) -> None:
    other_order = await _make_order(
        db_session, "GAP-ORD-OTHER", product_without_cost.id, workspace=OTHER_WORKSPACE
    )
    result = await pcs.list_transaction_cost_gaps(
        db_session, workspace_id=WORKSPACE, limit=100, offset=0
    )
    assert result["total"] == 0
    assert other_order.id not in [item["order_id"] for item in result["items"]]


# --------------------------------------------------------------------------- #
# Batch fill
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_batch_fill_all_success(
    db_session, product_without_cost, product_with_invalid_cost
) -> None:
    items = [
        type(
            "BatchItem",
            (),
            {"product_id": product_without_cost.id, "cost": _effective_cost_data()},
        )(),
        type(
            "BatchItem",
            (),
            {"product_id": product_with_invalid_cost.id, "cost": _effective_cost_data()},
        )(),
    ]
    result = await pcs.batch_fill_product_costs(
        db_session, workspace_id=WORKSPACE, items=items, trace_id="test-batch"
    )
    assert result["success_count"] == 2
    assert result["failed_count"] == 0
    assert all(item["success"] for item in result["results"])
    assert result["results"][0]["version"] == "v1"

    # Cost is now effective for both.
    overview = await pcs.list_cost_overview(db_session, workspace_id=WORKSPACE, limit=100, offset=0)
    assert overview["known"] == 2

    # Audit: per-item updates + one batch event.
    events = (
        (
            await db_session.execute(
                select(EventLog).where(EventLog.workspace_id == WORKSPACE)
            )
        )
        .scalars()
        .all()
    )
    event_types = {event.event_type for event in events}
    assert "product.cost.updated" in event_types
    assert "product.cost.batch_filled" in event_types
    batch_event = next(e for e in events if e.event_type == "product.cost.batch_filled")
    assert batch_event.payload["success_count"] == 2
    assert batch_event.payload["failed_count"] == 0


@pytest.mark.asyncio
async def test_batch_fill_partial_failure(db_session, product_without_cost) -> None:
    items = [
        type("BatchItem", (), {"product_id": product_without_cost.id, "cost": _effective_cost_data()})(),
        type("BatchItem", (), {"product_id": uuid4(), "cost": _effective_cost_data()})(),
    ]
    result = await pcs.batch_fill_product_costs(
        db_session, workspace_id=WORKSPACE, items=items, trace_id="test-batch-partial"
    )
    assert result["success_count"] == 1
    assert result["failed_count"] == 1
    ok = next(item for item in result["results"] if item["success"])
    failed = next(item for item in result["results"] if not item["success"])
    assert ok["product_id"] == product_without_cost.id
    assert failed["error"] is not None

    # The valid product still got filled (isolated failure).
    overview = await pcs.list_cost_overview(db_session, workspace_id=WORKSPACE, limit=100, offset=0)
    assert overview["known"] == 1


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_api_cost_gaps_endpoints(
    api_client, product_without_cost, product_with_invalid_cost, product_with_effective_cost
) -> None:
    gaps = api_client.get("/api/v1/products/cost-gaps?limit=100")
    assert gaps.status_code == 200
    body = gaps.json()
    assert body["known"] == 1
    assert body["invalid"] == 1
    assert body["missing"] == 1
    skus = {item["sku"] for item in body["items"]}
    assert skus == {"GAP-MISSING-001", "GAP-INVALID-001"}


@pytest.mark.asyncio
async def test_api_transaction_gaps_endpoint(
    api_client, db_session, product_without_cost
) -> None:
    await _make_order(db_session, "GAP-ORD-API", product_without_cost.id)
    response = api_client.get("/api/v1/products/cost-gaps/transactions?limit=100")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["order_number"] == "GAP-ORD-API"
    assert body["gap_line_count"] == 1


@pytest.mark.asyncio
async def test_api_batch_fill(api_client, product_without_cost) -> None:
    payload = _effective_cost_payload()
    response = api_client.post(
        "/api/v1/products/cost-gaps/batch-fill",
        json={"items": [{"product_id": str(product_without_cost.id), "cost": payload}]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success_count"] == 1
    assert body["failed_count"] == 0
    assert body["results"][0]["success"] is True
    assert body["results"][0]["version"] == "v1"


@pytest.mark.asyncio
async def test_api_batch_fill_missing_product(api_client) -> None:
    payload = _effective_cost_payload()
    response = api_client.post(
        "/api/v1/products/cost-gaps/batch-fill",
        json={"items": [{"product_id": str(uuid4()), "cost": payload}]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success_count"] == 0
    assert body["failed_count"] == 1
    assert body["results"][0]["error"] is not None
