"""Tests for the WooCommerce webhook -> order -> event -> rule loop.

Covers signature verification, idempotency, payload validation, order/event
creation, rule execution, profit calculation integration and audit logs.
"""

import hashlib
import hmac
import json
from decimal import Decimal

import pytest
from app.core.config import get_settings
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.event import EventLog
from app.models.order import Order, OrderItem
from app.models.product import Product, ProductCost
from app.models.rule import RuleExecutionLog
from app.schemas.rule import RuleCreate
from app.services import rule_engine
from sqlalchemy import func, select

WORKSPACE = DEFAULT_WORKSPACE_ID
WEBHOOK_URL = "/api/v1/webhooks/woocommerce"


def _sign(body: bytes) -> str:
    """Compute the WooCommerce HMAC-SHA256 signature for the test secret."""
    secret = get_settings().woocommerce_webhook_secret
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _order_payload(order_id: int = 12345) -> dict:
    """A realistic (PII-free) WooCommerce order payload."""
    return {
        "id": order_id,
        "status": "processing",
        "currency": "USD",
        "payment_method": "stripe",
        "payment_method_title": "Credit Card (Stripe)",
        "total": "100.00",
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
                "sku": "SKU-001",
                "quantity": 2,
                "total": "90.00",
            }
        ],
    }


async def _seed_order_rules(db_session) -> None:
    """Seed the three order-domain rules (same shape as migration 0003)."""
    rules = [
        RuleCreate(
            rule_id="PRICE-001",
            name="Order discount ratio must not exceed 30%",
            category="PRICE",
            rule_type="hard",
            version="v1",
            status="active",
            when_conditions={"field": "price.discount_ratio", "op": "lte", "value": 0.3},
            then_result={
                "passed_message": "discount ratio within limit",
                "failed_message": "discount ratio exceeds 30%",
            },
        ),
        RuleCreate(
            rule_id="PROFIT-002",
            name="Contribution margin rate must be >= 20%",
            category="PROFIT",
            rule_type="hard",
            version="v1",
            status="active",
            when_conditions={
                "field": "profit.contribution_margin_rate",
                "op": "gte",
                "value": 0.2,
            },
            then_result={
                "passed_message": "margin rate acceptable",
                "failed_message": "margin rate below 20%",
            },
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
            then_result={
                "passed_message": "payment status payable",
                "failed_message": "payment status not payable",
            },
        ),
    ]
    for data in rules:
        await rule_engine.create_rule(db_session, workspace_id=WORKSPACE, data=data)


def test_webhook_rejects_invalid_signature(api_client) -> None:
    """A delivery without the correct signature is rejected with 401."""
    body = json.dumps(_order_payload()).encode("utf-8")
    response = api_client.post(
        WEBHOOK_URL,
        content=body,
        headers={"Content-Type": "application/json", "X-Wc-Webhook-Signature": "bogus"},
    )
    assert response.status_code == 401


def test_webhook_rejects_invalid_payload(api_client) -> None:
    """Malformed JSON or a payload missing required fields is rejected."""
    bad_json = api_client.post(
        WEBHOOK_URL,
        content=b"{not json",
        headers={"Content-Type": "application/json", "X-Wc-Webhook-Signature": "x"},
    )
    assert bad_json.status_code == 400

    missing_id = json.dumps({"currency": "USD"}).encode("utf-8")
    invalid = api_client.post(
        WEBHOOK_URL,
        content=missing_id,
        headers={"Content-Type": "application/json", "X-Wc-Webhook-Signature": _sign(missing_id)},
    )
    assert invalid.status_code == 400


def test_webhook_gateway_topic_returns_404(api_client) -> None:
    """Payment-gateway registration payloads are answered 404, not processed."""
    body = json.dumps({"woocommerce.payments.gateways": "stripe"}).encode("utf-8")
    response = api_client.post(
        WEBHOOK_URL,
        content=body,
        headers={"Content-Type": "application/json", "X-Wc-Webhook-Signature": "irrelevant"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_webhook_creates_order_with_full_loop(db_session, api_client) -> None:
    """A signed ORDER_CREATED payload creates order + items + event + rules."""
    await _seed_order_rules(db_session)
    product = Product(
        workspace_id=WORKSPACE,
        sku="SKU-001",
        name="Camping Headlamp",
        category="camping",
        status="draft",
    )
    db_session.add(product)
    await db_session.flush()
    db_session.add(
        ProductCost(
            workspace_id=WORKSPACE,
            product_id=product.id,
            currency="USD",
            total_cost=Decimal("10.00"),
        )
    )
    await db_session.commit()

    body = json.dumps(_order_payload()).encode("utf-8")
    response = api_client.post(
        WEBHOOK_URL,
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Wc-Webhook-Signature": _sign(body),
        },
    )
    assert response.status_code == 201
    result = response.json()
    assert result["status"] == "created"
    assert result["external_order_id"] == "12345"
    assert len(result["trace_id"]) == 32

    # Order row persisted with items and no PII.
    order = (
        await db_session.execute(select(Order).where(Order.external_order_id == "12345"))
    ).scalar_one()
    assert order.currency == "USD"
    assert order.payment_status == "processing"
    assert order.total == Decimal("100.00")
    assert order.trace_id == result["trace_id"]
    items = (
        (await db_session.execute(select(OrderItem).where(OrderItem.order_id == order.id)))
        .scalars()
        .all()
    )
    assert len(items) == 1
    item: OrderItem = items[0]
    assert item.sku == "SKU-001"
    assert item.quantity == 2
    assert item.line_total == Decimal("90.00")

    # Profit snapshot uses the seeded landing cost (10.00 * 2 units).
    profit = order.profit_snapshot
    assert profit["product_cost"] == "20.00"
    assert profit["cost_details"] == {"SKU-001": "10.00"}
    assert profit["revenue"] == "100.00"
    assert profit["payment_fee"] == "3.20"

    # Rule results cover all three domains and pass.
    rules = order.rule_results
    assert set(rules) == {"PRICE", "PROFIT", "FULFILLMENT"}
    assert all(rules[group]["all_passed"] for group in rules)

    # order.created event was appended to the event log.
    event = (
        await db_session.execute(
            select(EventLog).where(
                EventLog.event_type == "order.created",
                EventLog.entity_id == str(order.id),
            )
        )
    ).scalar_one()
    assert event.trace_id == result["trace_id"]
    assert event.payload["external_order_id"] == "12345"


@pytest.mark.asyncio
async def test_webhook_duplicate_delivery_is_idempotent(db_session, api_client) -> None:
    """Re-delivering the same order returns duplicate without new rows."""
    await _seed_order_rules(db_session)
    body = json.dumps(_order_payload()).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Wc-Webhook-Signature": _sign(body),
    }

    first = api_client.post(WEBHOOK_URL, content=body, headers=headers)
    assert first.status_code == 201
    assert first.json()["status"] == "created"

    second = api_client.post(WEBHOOK_URL, content=body, headers=headers)
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"
    assert second.json()["order_id"] == first.json()["order_id"]

    orders = (await db_session.execute(select(func.count()).select_from(Order))).scalar_one()
    events = (
        await db_session.execute(
            select(func.count()).select_from(EventLog).where(EventLog.event_type == "order.created")
        )
    ).scalar_one()
    assert orders == 1
    assert events == 1


@pytest.mark.asyncio
async def test_webhook_rule_execution_is_audited(db_session, api_client) -> None:
    """Every rule evaluation writes a rule_execution_log with the trace_id."""
    await _seed_order_rules(db_session)
    body = json.dumps(_order_payload(order_id=999)).encode("utf-8")
    response = api_client.post(
        WEBHOOK_URL,
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Wc-Webhook-Signature": _sign(body),
        },
    )
    assert response.status_code == 201
    trace_id = response.json()["trace_id"]

    logs = (
        (
            await db_session.execute(
                select(RuleExecutionLog).where(RuleExecutionLog.trace_id == trace_id)
            )
        )
        .scalars()
        .all()
    )
    assert {log.rule_id for log in logs} == {
        "PRICE-001",
        "PROFIT-002",
        "FULFILLMENT-001",
    }
    assert all(log.context["profit"]["contribution_margin_rate"] >= 0.2 for log in logs)
