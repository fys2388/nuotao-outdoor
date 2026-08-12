"""Tests for M1.6: order query API and profit cost confidence."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from app.core.config import get_settings
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.product import Product, ProductCost
from app.schemas.rule import RuleCreate
from app.services import rule_engine

WORKSPACE = DEFAULT_WORKSPACE_ID
WEBHOOK_URL = "/api/v1/webhooks/woocommerce"
ORDERS_URL = "/api/v1/orders"


def _sign(body: bytes) -> str:
    secret = get_settings().woocommerce_webhook_secret
    import hashlib
    import hmac

    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _order_payload(order_id: int, sku: str = "SKU-001", total: str = "100.00") -> dict:
    return {
        "id": order_id,
        "status": "processing",
        "currency": "USD",
        "payment_method": "stripe",
        "total": total,
        "subtotal": "95.00",
        "shipping_total": "5.00",
        "discount_total": "5.00",
        "tax_total": "0.00",
        "shipping": {"country": "US"},
        "line_items": [
            {
                "id": 1,
                "product_id": 101,
                "name": "Camping Headlamp",
                "sku": sku,
                "quantity": 1,
                "total": "90.00",
            }
        ],
    }


async def _seed_order_rules(db_session) -> None:
    """Seed order rules including PROFIT-003 (confidence gate)."""
    rules = [
        RuleCreate(
            rule_id="PRICE-001",
            name="Order discount ratio must not exceed 30%",
            category="PRICE",
            rule_type="hard",
            version="v1",
            status="active",
            when_conditions={"field": "price.discount_ratio", "op": "lte", "value": 0.3},
            then_result={"passed_message": "ok", "failed_message": "too high"},
        ),
        RuleCreate(
            rule_id="PROFIT-002",
            name="Contribution margin rate must be >= 20%",
            category="PROFIT",
            rule_type="hard",
            version="v1",
            status="active",
            when_conditions={"field": "profit.contribution_margin_rate", "op": "gte", "value": 0.2},
            then_result={"passed_message": "ok", "failed_message": "low"},
        ),
        RuleCreate(
            rule_id="PROFIT-003",
            name="Profit conclusion requires non-unknown product cost",
            category="PROFIT",
            rule_type="hard",
            version="v1",
            status="active",
            when_conditions={
                "field": "profit.cost_status",
                "op": "in",
                "value": ["KNOWN", "ESTIMATED"],
            },
            then_result={"passed_message": "ok", "failed_message": "cost unknown"},
        ),
        RuleCreate(
            rule_id="FULFILLMENT-001",
            name="Payment status must be payable to fulfill",
            category="FULFILLMENT",
            rule_type="hard",
            version="v1",
            status="active",
            when_conditions={
                "field": "fulfillment.payment_status",
                "op": "in",
                "value": ["processing", "completed"],
            },
            then_result={"passed_message": "ok", "failed_message": "not payable"},
        ),
    ]
    for data in rules:
        await rule_engine.create_rule(db_session, workspace_id=WORKSPACE, data=data)


async def _ingest_webhook(
    db_session, api_client, order_id: int, sku: str = "SKU-001", total: str = "100.00"
) -> dict:
    body = json.dumps(_order_payload(order_id, sku, total)).encode("utf-8")
    response = api_client.post(
        WEBHOOK_URL,
        content=body,
        headers={"Content-Type": "application/json", "X-Wc-Webhook-Signature": _sign(body)},
    )
    assert response.status_code == 201
    return response.json()


# ---------------------------------------------------------------- order query API


@pytest.mark.asyncio
async def test_orders_list_filters_and_pagination(db_session, api_client) -> None:
    """List filters: status, external id, sku, date range; pagination works."""
    await _seed_order_rules(db_session)
    await _ingest_webhook(db_session, api_client, order_id=1001, sku="SKU-AAA")
    await _ingest_webhook(db_session, api_client, order_id=1002, sku="SKU-BBB")

    # status filter (internal status is always "received" in M1.5).
    body = api_client.get(ORDERS_URL, params={"status": "received"}).json()
    assert body["total"] == 2

    # external_order_id filter.
    body = api_client.get(ORDERS_URL, params={"external_order_id": "1001"}).json()
    assert body["total"] == 1
    assert body["items"][0]["external_order_id"] == "1001"

    # SKU filter (join on order_items).
    body = api_client.get(ORDERS_URL, params={"sku": "SKU-BBB"}).json()
    assert body["total"] == 1
    assert body["items"][0]["external_order_id"] == "1002"

    # Date range around now.
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    body = api_client.get(ORDERS_URL, params={"date_from": past, "date_to": future}).json()
    assert body["total"] == 2

    # Pagination.
    body = api_client.get(ORDERS_URL, params={"limit": 1, "offset": 1}).json()
    assert body["total"] == 2
    assert len(body["items"]) == 1


@pytest.mark.asyncio
async def test_orders_list_sorting_and_validation(db_session, api_client) -> None:
    """Sorting by total/asc works; unknown sort columns are rejected."""
    await _seed_order_rules(db_session)
    for order_id in (2001, 2002, 2003):
        total = {"2001": "50.00", "2002": "30.00", "2003": "80.00"}[str(order_id)]
        await _ingest_webhook(db_session, api_client, order_id=order_id, total=total)

    body = api_client.get(ORDERS_URL, params={"sort_by": "total", "sort_order": "asc"}).json()
    totals = [item["total"] for item in body["items"]]
    assert totals == ["30.00", "50.00", "80.00"]

    bad = api_client.get(ORDERS_URL, params={"sort_by": "user_input"})
    assert bad.status_code == 422

    bad_order = api_client.get(ORDERS_URL, params={"sort_order": "sideways"})
    assert bad_order.status_code == 422


@pytest.mark.asyncio
async def test_orders_get_by_id(db_session, api_client) -> None:
    """GET /orders/{id} returns the detail with line items; missing -> 404."""
    await _seed_order_rules(db_session)
    created = await _ingest_webhook(db_session, api_client, order_id=3001)

    response = api_client.get(f"{ORDERS_URL}/{created['order_id']}")
    assert response.status_code == 200
    detail = response.json()
    assert detail["external_order_id"] == "3001"
    assert detail["status"] == "received"
    assert len(detail["items"]) == 1
    assert detail["items"][0]["sku"] == "SKU-001"
    assert detail["profit_snapshot"]["cost_status"] in {"KNOWN", "ESTIMATED", "UNKNOWN"}

    missing = api_client.get(f"{ORDERS_URL}/{uuid4()}")
    assert missing.status_code == 404


# ------------------------------------------------------------ confidence handling


@pytest.mark.asyncio
async def test_order_unknown_cost_low_confidence_gate(db_session, api_client) -> None:
    """UNKNOWN product cost must not yield a high-confidence profit conclusion."""
    await _seed_order_rules(db_session)
    result = await _ingest_webhook(db_session, api_client, order_id=4001, sku="NO-COST-SKU")

    profit = result["profit"]
    assert profit["cost_status"] == "UNKNOWN"
    assert profit["profit_confidence"] == "LOW"
    assert "no product cost data matched" in profit["confidence_reasons"]

    # PROFIT-003 hard gate fails -> PROFIT domain not all-passed.
    profit_rules = result["rules"]["PROFIT"]
    assert profit_rules["all_passed"] is False
    rule_ids = {r["rule_id"] for r in profit_rules["results"]}
    assert "PROFIT-003" in rule_ids
    failed = [r for r in profit_rules["results"] if not r["passed"]]
    assert any(r["rule_id"] == "PROFIT-003" for r in failed)


@pytest.mark.asyncio
async def test_order_known_cost_high_confidence(db_session, api_client) -> None:
    """Fully known product cost produces a KNOWN/HIGH profit conclusion."""
    await _seed_order_rules(db_session)
    product = Product(
        workspace_id=WORKSPACE, sku="SKU-KNOWN", name="Known Cost Lamp", status="draft"
    )
    db_session.add(product)
    await db_session.flush()
    db_session.add(
        ProductCost(
            workspace_id=WORKSPACE,
            product_id=product.id,
            total_cost=Decimal("20.00"),
            valid_from=datetime.now(UTC),
        )
    )
    await db_session.commit()

    result = await _ingest_webhook(db_session, api_client, order_id=4002, sku="SKU-KNOWN")
    profit = result["profit"]
    assert profit["cost_status"] == "KNOWN"
    assert profit["profit_confidence"] == "HIGH"
    assert result["rules"]["PROFIT"]["all_passed"] is True
