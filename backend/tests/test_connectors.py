"""Tests for M4.3 Real Data Connectors + Decision Intelligence.

Covers: connector syncs (WooCommerce orders/products/customers, logistics
tracking, marketing campaigns, suppliers), sync audit + events, duplicate /
idempotency handling, workspace isolation, and the business-recommendation
human-approval workflow.
"""

from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.connector import ConnectorRun
from app.models.customer import CustomerProfile
from app.models.event import EventLog
from app.models.marketing import Campaign
from app.models.order import Order
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.supply_chain import LogisticsEvent, ShipmentRecord

WORKSPACE = DEFAULT_WORKSPACE_ID
OTHER_WORKSPACE = UUID("00000000-0000-0000-0000-000000000099")


def _headers(workspace: UUID | None = None) -> dict:
    return {"X-Workspace-Id": str(workspace)} if workspace else {}


async def _event_types(db_session) -> set[str]:
    rows = (await db_session.execute(select(EventLog.event_type))).scalars().all()
    return set(rows)


def _order_record(order_id: int = 90001) -> dict:
    """A PII-free WooCommerce order record (same shape as the webhook)."""
    return {
        "kind": "orders",
        "data": {
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
                    "name": "Camping Headlamp",
                    "sku": "SKU-900",
                    "quantity": 1,
                    "total": "90.00",
                }
            ],
        },
    }


def _product_record(sku: str = "SKU-WC-1", name: str = "Headlamp") -> dict:
    return {
        "kind": "products",
        "data": {
            "sku": sku,
            "name": name,
            "description": "Rechargeable headlamp",
            "categories": [{"name": "Lighting"}],
            "status": "publish",
            "permalink": "https://shop.example/headlamp",
            "weight": "0.25",
        },
    }


def _customer_record(customer_id: int = 7001) -> dict:
    return {
        "kind": "customers",
        "data": {
            "id": customer_id,
            "email": "buyer@example.com",
            "billing": {"country": "US"},
            "orders_count": 2,
            "total_spent": "150.00",
        },
    }


def _tracking_record(tracking: str = "LP90001") -> dict:
    return {
        "carrier": "Cainiao",
        "tracking_number": tracking,
        "status": "in_transit",
        "origin": "Yiwu, China",
        "destination": "Los Angeles, US",
        "events": [
            {
                "event_type": "pickup",
                "location": "Yiwu",
                "description": "Parcel picked up",
                "occurred_at": "2026-08-01T08:00:00Z",
            }
        ],
    }


def _campaign_record(campaign_id: str = "c-conn-1") -> dict:
    return {
        "platform": "meta",
        "campaign_id": campaign_id,
        "name": "US Summer Tent",
        "status": "active",
        "currency": "USD",
        "budget": "500.00",
        "spend": "120.00",
        "impressions": 10000,
        "clicks": 250,
        "conversion": 8,
        "revenue": "480.00",
    }


def _supplier_record(code: str = "1688-conn-1") -> dict:
    return {
        "code": code,
        "name": "Yiwu Camping Factory",
        "platform": "1688",
        "shop_url": "https://shop1688.example/conn-1",
        "rating": "A",
        "status": "active",
    }


async def _run_sync(
    api_client, connector: str, data: list[dict], workspace: UUID | None = None
) -> dict:
    response = api_client.post(
        f"/api/v1/connectors/{connector}/sync",
        json={"data": data},
        headers=_headers(workspace),
    )
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------- #
# 1. WooCommerce connector
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_woocommerce_order_sync_creates_order(db_session, api_client) -> None:
    """An order batch sync creates the order, the run audit and the event."""
    body = await _run_sync(api_client, "woocommerce", [_order_record()])
    assert body["status"] == "success"
    assert body["records_count"] == 1
    assert body["connector_name"] == "woocommerce"

    orders = (await db_session.execute(select(Order))).scalars().all()
    assert len(orders) == 1
    assert orders[0].external_order_id == "90001"
    assert "connector.run_completed" in await _event_types(db_session)
    assert "order.created" in await _event_types(db_session)


@pytest.mark.asyncio
async def test_woocommerce_order_sync_duplicate_idempotent(db_session, api_client) -> None:
    """Re-syncing the same order does not create a second order row."""
    await _run_sync(api_client, "woocommerce", [_order_record(90002)])
    await _run_sync(api_client, "woocommerce", [_order_record(90002)])

    order_count = (await db_session.execute(select(func.count()).select_from(Order))).scalar_one()
    assert order_count == 1


@pytest.mark.asyncio
async def test_woocommerce_product_sync_upsert(db_session, api_client) -> None:
    """Product sync creates then updates the same product by SKU."""
    await _run_sync(api_client, "woocommerce", [_product_record(sku="SKU-WC-2", name="Headlamp")])
    await _run_sync(
        api_client, "woocommerce", [_product_record(sku="SKU-WC-2", name="Headlamp Pro")]
    )

    products = (await db_session.execute(select(Product))).scalars().all()
    assert len(products) == 1
    assert products[0].name == "Headlamp Pro"
    assert products[0].source == "woocommerce"
    events = await _event_types(db_session)
    assert "product.created" in events
    assert "product.updated" in events


@pytest.mark.asyncio
async def test_woocommerce_customer_reference_hash_no_pii(db_session, api_client) -> None:
    """Customers are stored as a reference hash; email is never persisted."""
    await _run_sync(api_client, "woocommerce", [_customer_record(7002)])

    profiles = (await db_session.execute(select(CustomerProfile))).scalars().all()
    assert len(profiles) == 1
    profile = profiles[0]
    assert profile.customer_reference_id != "buyer@example.com"
    hex_digits = "0123456789abcdef"
    assert profile.customer_reference_id[0] in hex_digits
    assert "buyer@example.com" not in profile.customer_reference_id
    assert profile.country == "US"


# --------------------------------------------------------------------------- #
# 2. Logistics connector
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_logistics_sync_creates_shipment_and_events(db_session, api_client) -> None:
    """Tracking sync creates the shipment and appends its events."""
    body = await _run_sync(api_client, "logistics", [_tracking_record("LP-ABC-1")])
    assert body["status"] == "success"
    assert body["records_count"] == 1

    shipments = (await db_session.execute(select(ShipmentRecord))).scalars().all()
    assert len(shipments) == 1
    assert shipments[0].tracking_number == "LP-ABC-1"
    events = (await db_session.execute(select(LogisticsEvent))).scalars().all()
    assert len(events) == 1
    assert events[0].event_type == "pickup"
    assert "connector.run_completed" in await _event_types(db_session)


@pytest.mark.asyncio
async def test_logistics_sync_duplicate_does_not_repeat_events(db_session, api_client) -> None:
    """Re-syncing the same tracking record updates the shipment only."""
    record = _tracking_record("LP-ABC-2")
    await _run_sync(api_client, "logistics", [record])
    await _run_sync(api_client, "logistics", [record])

    shipments = (await db_session.execute(select(ShipmentRecord))).scalars().all()
    assert len(shipments) == 1
    events = (await db_session.execute(select(LogisticsEvent))).scalars().all()
    assert len(events) == 1


# --------------------------------------------------------------------------- #
# 3. Marketing connector
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_marketing_campaign_sync_create_then_update(db_session, api_client) -> None:
    """Campaign metrics sync creates then updates by (platform, campaign_id)."""
    await _run_sync(api_client, "marketing", [_campaign_record("c-conn-m1")])
    record = _campaign_record("c-conn-m1")
    record["spend"] = "200.00"
    record["revenue"] = "760.00"
    await _run_sync(api_client, "marketing", [record])

    campaigns = (await db_session.execute(select(Campaign))).scalars().all()
    assert len(campaigns) == 1
    assert campaigns[0].spend == Decimal("200.00")
    assert campaigns[0].revenue == Decimal("760.00")


# --------------------------------------------------------------------------- #
# 4. Supplier connector
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_supplier_sync_upsert(db_session, api_client) -> None:
    """Supplier master sync creates then updates by (workspace, code)."""
    await _run_sync(api_client, "supplier", [_supplier_record("1688-conn-s1")])
    record = _supplier_record("1688-conn-s1")
    record["name"] = "Yiwu Camping Factory v2"
    await _run_sync(api_client, "supplier", [record])

    suppliers = (await db_session.execute(select(Supplier))).scalars().all()
    assert len(suppliers) == 1
    assert suppliers[0].name == "Yiwu Camping Factory v2"


# --------------------------------------------------------------------------- #
# 5. Audit, validation, isolation
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_connector_run_audit_persisted(db_session, api_client) -> None:
    """Every sync writes a connector_runs row and a run_completed event."""
    await _run_sync(api_client, "supplier", [_supplier_record("1688-conn-a1")])

    runs = (await db_session.execute(select(ConnectorRun))).scalars().all()
    assert len(runs) == 1
    assert runs[0].status == "success"
    assert runs[0].records_count == 1
    assert runs[0].connector_name == "supplier"
    assert runs[0].trace_id is not None

    events = (await db_session.execute(select(EventLog))).scalars().all()
    run_events = [e for e in events if e.event_type == "connector.run_completed"]
    assert len(run_events) == 1
    assert run_events[0].payload["status"] == "success"


@pytest.mark.asyncio
async def test_unknown_connector_returns_422(api_client) -> None:
    """An unregistered connector name is rejected before any sync."""
    response = api_client.post(
        "/api/v1/connectors/not-a-connector/sync",
        json={"data": []},
    )
    assert response.status_code == 422
    assert "unknown connector" in response.json()["detail"]


@pytest.mark.asyncio
async def test_invalid_connector_payload_returns_400(api_client) -> None:
    """A connector with an invalid/empty batch is rejected with a message."""
    response = api_client.post(
        "/api/v1/connectors/logistics/sync",
        json={"data": []},
    )
    assert response.status_code == 400
    assert "data must be a non-empty list" in response.json()["detail"]


@pytest.mark.asyncio
async def test_connector_runs_workspace_isolation(db_session, api_client) -> None:
    """Connector run audit rows are scoped per workspace."""
    await _run_sync(api_client, "supplier", [_supplier_record("1688-conn-w1")], workspace=WORKSPACE)
    await _run_sync(
        api_client, "supplier", [_supplier_record("1688-conn-w2")], workspace=OTHER_WORKSPACE
    )

    visible = api_client.get("/api/v1/connector-runs")
    assert visible.status_code == 200
    assert len(visible.json()) == 1

    other_visible = api_client.get("/api/v1/connector-runs", headers=_headers(OTHER_WORKSPACE))
    assert other_visible.status_code == 200
    assert len(other_visible.json()) == 1
    assert other_visible.json()[0]["workspace_id"] == str(OTHER_WORKSPACE)


# --------------------------------------------------------------------------- #
# 6. Decision intelligence: business recommendations
# --------------------------------------------------------------------------- #


def _proposal() -> dict:
    return {
        "domain": "supply_chain",
        "entity_type": "product",
        "entity_id": "SKU-900",
        "recommendation": "Reorder 200 units before peak season",
        "reason": "Inventory below 2 weeks of coverage",
        "confidence": 0.82,
    }


@pytest.mark.asyncio
async def test_recommendation_approve_workflow(db_session, api_client) -> None:
    """A proposal is created, approved once, and re-approval is rejected."""
    created = api_client.post("/api/v1/business-recommendations", json=_proposal())
    assert created.status_code == 201, created.text
    rec_id = created.json()["id"]
    assert created.json()["status"] == "proposed"

    approved = api_client.post(
        f"/api/v1/business-recommendations/{rec_id}/approve",
        json={"actor": "ops-lead", "note": "stock is low"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["approved_by"] == "ops-lead"
    assert approved.json()["approved_at"] is not None

    double = api_client.post(
        f"/api/v1/business-recommendations/{rec_id}/approve",
        json={"actor": "ops-lead"},
    )
    assert double.status_code == 400
    assert "already approved" in double.json()["detail"]

    events = await _event_types(db_session)
    assert "business.recommendation_proposed" in events
    assert "business.recommendation_approved" in events


@pytest.mark.asyncio
async def test_recommendation_reject_workflow(db_session, api_client) -> None:
    """A proposal can be rejected and cannot then be approved."""
    created = api_client.post("/api/v1/business-recommendations", json=_proposal())
    rec_id = created.json()["id"]

    rejected = api_client.post(
        f"/api/v1/business-recommendations/{rec_id}/reject",
        json={"actor": "ops-lead", "note": "seasonal demand unclear"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    after = api_client.post(
        f"/api/v1/business-recommendations/{rec_id}/approve",
        json={"actor": "ops-lead"},
    )
    assert after.status_code == 400
    assert "already rejected" in after.json()["detail"]


@pytest.mark.asyncio
async def test_recommendation_unknown_id_404(api_client) -> None:
    """Deciding an unknown recommendation returns 404."""
    missing = UUID("00000000-0000-0000-0000-00000000dead")
    response = api_client.post(
        f"/api/v1/business-recommendations/{missing}/approve",
        json={"actor": "ops-lead"},
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_recommendation_list_filters_and_isolation(db_session, api_client) -> None:
    """Recommendations are filterable and workspace-scoped."""
    api_client.post("/api/v1/business-recommendations", json=_proposal())
    api_client.post(
        "/api/v1/business-recommendations",
        json={**_proposal(), "domain": "marketing"},
    )
    api_client.post(
        "/api/v1/business-recommendations",
        json={**_proposal(), "domain": "marketing"},
        headers=_headers(OTHER_WORKSPACE),
    )

    all_recs = api_client.get("/api/v1/business-recommendations")
    assert all_recs.status_code == 200
    assert len(all_recs.json()) == 2

    marketing_only = api_client.get(
        "/api/v1/business-recommendations", params={"domain": "marketing"}
    )
    assert len(marketing_only.json()) == 1

    other = api_client.get("/api/v1/business-recommendations", headers=_headers(OTHER_WORKSPACE))
    assert len(other.json()) == 1
