"""Tests for M4.1 Supply Chain Intelligence Foundation.

Covers: supplier profiles (duplicate protection + workspace isolation),
purchase order lifecycle (draft -> approved -> ordered -> received, invalid
transitions, cancel), inventory calculation (available = quantity - reserved),
shipment logistics events, supply chain knowledge retrieval and event audit
(every write emits an event with trace_id).
"""

from decimal import Decimal
from uuid import UUID

import pytest
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.event import EventLog
from app.models.product import Product
from app.models.supplier import Supplier
from sqlalchemy import select

WORKSPACE = DEFAULT_WORKSPACE_ID
OTHER_WORKSPACE = UUID("00000000-0000-0000-0000-000000000099")


def _headers(workspace: UUID | None = None) -> dict:
    return {"X-Workspace-Id": str(workspace)} if workspace else {}


async def _event_types(db_session) -> set[str]:
    rows = (await db_session.execute(select(EventLog.event_type))).scalars().all()
    return set(rows)


async def _seed_supplier(db_session, workspace: UUID = WORKSPACE, code: str = "1688-demo") -> UUID:
    supplier = Supplier(workspace_id=workspace, code=code, name=f"Supplier {code}")
    db_session.add(supplier)
    await db_session.flush()
    return supplier.id


async def _seed_product(db_session, workspace: UUID = WORKSPACE, sku: str = "SC-PROD-001") -> UUID:
    product = Product(workspace_id=workspace, sku=sku, name=f"Product {sku}")
    db_session.add(product)
    await db_session.flush()
    return product.id


async def _make_po(db_session, api_client, po_number: str) -> UUID:
    supplier_id = await _seed_supplier(db_session, code=f"supplier-{po_number}")
    response = api_client.post(
        "/api/v1/purchase-orders",
        json={
            "po_number": po_number,
            "supplier_id": str(supplier_id),
            "items": [{"sku": "TENT-1", "name": "Tent 1P", "quantity": 2, "unit_cost": "10.00"}],
        },
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


# --------------------------------------------------------------------------- #
# 1. Supplier profiles
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_supplier_profile_create_and_duplicate_409(db_session, api_client) -> None:
    """A profile is created once per supplier; a duplicate returns 409."""
    supplier_id = await _seed_supplier(db_session)
    payload = {
        "supplier_id": str(supplier_id),
        "category": "camping",
        "location": "Yiwu, Zhejiang",
        "factory_type": "factory",
        "lead_time_days": 7,
        "minimum_order_qty": 50,
        "quality_score": "88.5",
        "on_time_rate": "92.0",
        "defect_rate": "1.5",
        "certifications": ["BSCI"],
        "risk_level": "low",
    }
    response = api_client.post("/api/v1/supplier-profiles", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["supplier_id"] == str(supplier_id)
    assert body["factory_type"] == "factory"
    assert body["risk_level"] == "low"
    assert "supply.supplier_profile_created" in await _event_types(db_session)

    duplicate = api_client.post("/api/v1/supplier-profiles", json=payload)
    assert duplicate.status_code == 409
    assert "already exists" in duplicate.json()["detail"]


@pytest.mark.asyncio
async def test_supplier_profile_unknown_supplier_404(db_session, api_client) -> None:
    """Profiles cannot reference suppliers outside the workspace."""
    missing = UUID("00000000-0000-0000-0000-00000000dead")
    response = api_client.post(
        "/api/v1/supplier-profiles",
        json={"supplier_id": str(missing), "risk_level": "low"},
    )
    assert response.status_code == 404
    assert "supplier not found" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# 2. Purchase order lifecycle
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_purchase_order_full_lifecycle(db_session, api_client) -> None:
    """A PO moves draft -> approved -> ordered -> received with computed totals."""
    supplier_id = await _seed_supplier(db_session)
    payload = {
        "po_number": "PO-2026-001",
        "supplier_id": str(supplier_id),
        "currency": "USD",
        "shipping_cost": "20.00",
        "items": [
            {"sku": "TENT-1", "name": "Tent 1P", "quantity": 10, "unit_cost": "12.50"},
            {"sku": "PAD-1", "name": "Sleeping pad", "quantity": 5, "unit_cost": "8.00"},
        ],
    }
    created = api_client.post("/api/v1/purchase-orders", json=payload)
    assert created.status_code == 201, created.text
    po = created.json()
    assert po["status"] == "draft"
    assert Decimal(po["subtotal"]) == Decimal("165.00")
    assert Decimal(po["total"]) == Decimal("185.00")

    po_id = po["id"]
    detail = api_client.get(f"/api/v1/purchase-orders/{po_id}")
    assert detail.status_code == 200, detail.text
    assert len(detail.json()["items"]) == 2

    approved = api_client.post(f"/api/v1/purchase-orders/{po_id}/approve")
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    ordered = api_client.post(f"/api/v1/purchase-orders/{po_id}/order")
    assert ordered.status_code == 200, ordered.text
    assert ordered.json()["status"] == "ordered"

    partial = api_client.post(f"/api/v1/purchase-orders/{po_id}/partial-receive")
    assert partial.status_code == 200, partial.text
    assert partial.json()["status"] == "partial_received"

    received = api_client.post(f"/api/v1/purchase-orders/{po_id}/receive")
    assert received.status_code == 200, received.text
    assert received.json()["status"] == "received"
    assert received.json()["received_at"] is not None

    events = await _event_types(db_session)
    for expected in (
        "supply.purchase_order_created",
        "supply.purchase_order_approved",
        "supply.purchase_order_ordered",
        "supply.purchase_order_partial_received",
        "supply.purchase_order_received",
    ):
        assert expected in events


@pytest.mark.asyncio
async def test_purchase_order_invalid_transitions(db_session, api_client) -> None:
    """Illegal state jumps are rejected; draft can be cancelled."""
    po_id = await _make_po(db_session, api_client, "PO-2026-002")

    receive = api_client.post(f"/api/v1/purchase-orders/{po_id}/receive")
    assert receive.status_code == 400
    assert "cannot transition" in receive.json()["detail"]

    cancelled = api_client.post(f"/api/v1/purchase-orders/{po_id}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"

    approve = api_client.post(f"/api/v1/purchase-orders/{po_id}/approve")
    assert approve.status_code == 400


@pytest.mark.asyncio
async def test_purchase_order_partial_received_guardrails(db_session, api_client) -> None:
    """From partial_received only receive is allowed (no cancel, no repeat)."""
    po_id = await _make_po(db_session, api_client, "PO-2026-004")
    api_client.post(f"/api/v1/purchase-orders/{po_id}/approve")
    api_client.post(f"/api/v1/purchase-orders/{po_id}/order")
    partial = api_client.post(f"/api/v1/purchase-orders/{po_id}/partial-receive")
    assert partial.status_code == 200
    assert partial.json()["status"] == "partial_received"

    repeat = api_client.post(f"/api/v1/purchase-orders/{po_id}/partial-receive")
    assert repeat.status_code == 400
    assert "cannot transition" in repeat.json()["detail"]

    cancel = api_client.post(f"/api/v1/purchase-orders/{po_id}/cancel")
    assert cancel.status_code == 400

    received = api_client.post(f"/api/v1/purchase-orders/{po_id}/receive")
    assert received.status_code == 200
    assert received.json()["status"] == "received"


@pytest.mark.asyncio
async def test_purchase_order_duplicate_number_409(db_session, api_client) -> None:
    """PO numbers are unique per workspace."""
    supplier_id = await _seed_supplier(db_session)
    payload = {
        "po_number": "PO-2026-003",
        "supplier_id": str(supplier_id),
        "items": [{"sku": "A", "name": "Item A", "quantity": 1, "unit_cost": "5.00"}],
    }
    assert api_client.post("/api/v1/purchase-orders", json=payload).status_code == 201
    duplicate = api_client.post("/api/v1/purchase-orders", json=payload)
    assert duplicate.status_code == 409


# --------------------------------------------------------------------------- #
# 3. Inventory
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_inventory_calculation(db_session, api_client) -> None:
    """available = quantity - reserved unless explicitly provided."""
    product_id = await _seed_product(db_session)
    created = api_client.post(
        "/api/v1/inventory-snapshots",
        json={
            "product_id": str(product_id),
            "location": "us",
            "quantity": 100,
            "reserved": 30,
        },
    )
    assert created.status_code == 201, created.text
    snapshot = created.json()
    assert snapshot["available"] == 70
    assert snapshot["snapshot_time"] is not None

    inventory_id = snapshot["id"]
    updated = api_client.put(
        f"/api/v1/inventory-snapshots/{inventory_id}",
        json={"reserved": 55},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["available"] == 45

    explicit = api_client.put(
        f"/api/v1/inventory-snapshots/{inventory_id}",
        json={"quantity": 120, "available": 60},
    )
    assert explicit.status_code == 200, explicit.text
    assert explicit.json()["available"] == 60

    events = await _event_types(db_session)
    assert "supply.inventory_created" in events
    assert "supply.inventory_updated" in events


@pytest.mark.asyncio
async def test_inventory_duplicate_product_location_409(db_session, api_client) -> None:
    """One snapshot per product/location."""
    product_id = await _seed_product(db_session)
    payload = {"product_id": str(product_id), "location": "cn", "quantity": 10}
    assert api_client.post("/api/v1/inventory-snapshots", json=payload).status_code == 201
    duplicate = api_client.post("/api/v1/inventory-snapshots", json=payload)
    assert duplicate.status_code == 409


@pytest.mark.asyncio
async def test_inventory_invalid_location_422(db_session, api_client) -> None:
    """Only cn/us/eu warehouse locations are accepted."""
    product_id = await _seed_product(db_session)
    response = api_client.post(
        "/api/v1/inventory-snapshots",
        json={"product_id": str(product_id), "location": "mars", "quantity": 10},
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# 4. Shipments + logistics events
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_shipment_and_logistics_events(db_session, api_client) -> None:
    """A shipment accepts append-only tracking events and status updates."""
    created = api_client.post(
        "/api/v1/shipments",
        json={
            "carrier": "Cainiao",
            "origin": "Yiwu, China",
            "destination": "Los Angeles, US",
            "tracking_number": "CN123456789",
            "status": "created",
        },
    )
    assert created.status_code == 201, created.text
    shipment_id = created.json()["id"]

    event = api_client.post(
        f"/api/v1/shipments/{shipment_id}/events",
        json={"event_type": "picked_up", "location": "Yiwu", "description": "Parcel picked up"},
    )
    assert event.status_code == 201, event.text
    assert event.json()["event_type"] == "picked_up"

    listing = api_client.get(f"/api/v1/shipments/{shipment_id}/events")
    assert listing.status_code == 200
    assert len(listing.json()) == 1

    updated = api_client.put(
        f"/api/v1/shipments/{shipment_id}",
        json={"status": "delayed", "delay_reason": "customs hold", "delivery_time_days": 12},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "delayed"

    events = await _event_types(db_session)
    for expected in (
        "supply.shipment_created",
        "supply.logistics_event_added",
        "supply.shipment_updated",
    ):
        assert expected in events


@pytest.mark.asyncio
async def test_shipment_missing_404(db_session, api_client) -> None:
    """Tracking events cannot be added to an unknown shipment."""
    missing = UUID("00000000-0000-0000-0000-00000000dead")
    response = api_client.post(
        f"/api/v1/shipments/{missing}/events",
        json={"event_type": "picked_up"},
    )
    assert response.status_code == 404
    assert "shipment not found" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# 5. Supply chain knowledge
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_supply_chain_knowledge_retrieval(db_session, api_client) -> None:
    """Knowledge entries are queryable by category/type/supplier/product."""
    supplier_id = await _seed_supplier(db_session)
    product_id = await _seed_product(db_session)
    payload = {
        "supplier_id": str(supplier_id),
        "product_id": str(product_id),
        "category": "logistics",
        "entry_type": "delay_pattern",
        "title": "Customs delays Q4",
        "content": "US customs clearance takes 2-3 extra days in Q4.",
        "tags": ["customs", "q4"],
        "source": "manual",
        "confidence": "0.8",
    }
    created = api_client.post("/api/v1/supply-chain-knowledge-entries", json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["entry_type"] == "delay_pattern"

    by_category = api_client.get(
        "/api/v1/supply-chain-knowledge-entries", params={"category": "logistics"}
    )
    assert by_category.status_code == 200
    assert len(by_category.json()) == 1

    by_type = api_client.get(
        "/api/v1/supply-chain-knowledge-entries", params={"entry_type": "delay_pattern"}
    )
    assert len(by_type.json()) == 1

    by_supplier = api_client.get(
        "/api/v1/supply-chain-knowledge-entries", params={"supplier_id": str(supplier_id)}
    )
    assert len(by_supplier.json()) == 1

    no_match = api_client.get(
        "/api/v1/supply-chain-knowledge-entries", params={"entry_type": "quality_pattern"}
    )
    assert no_match.json() == []

    assert "supply.knowledge_created" in await _event_types(db_session)


# --------------------------------------------------------------------------- #
# 6. Event audit + workspace isolation
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_event_audit_has_trace_id(db_session, api_client) -> None:
    """Every supply chain write lands in event_log with trace_id."""
    supplier_id = await _seed_supplier(db_session)
    api_client.post(
        "/api/v1/supplier-profiles",
        json={"supplier_id": str(supplier_id), "risk_level": "high"},
    )
    rows = (
        (
            await db_session.execute(
                select(EventLog).where(EventLog.event_type == "supply.supplier_profile_created")
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].workspace_id == WORKSPACE
    assert rows[0].entity_type == "supplier"
    assert rows[0].trace_id is not None


@pytest.mark.asyncio
async def test_workspace_isolation(db_session, api_client) -> None:
    """All five domains are invisible across workspaces."""
    supplier_id = await _seed_supplier(db_session, workspace=WORKSPACE)
    await _seed_supplier(db_session, workspace=OTHER_WORKSPACE, code="other-sup")
    product_id = await _seed_product(db_session, workspace=WORKSPACE)

    assert (
        api_client.post(
            "/api/v1/supplier-profiles",
            headers=_headers(WORKSPACE),
            json={"supplier_id": str(supplier_id), "risk_level": "low"},
        ).status_code
        == 201
    )
    assert (
        api_client.get("/api/v1/supplier-profiles", headers=_headers(OTHER_WORKSPACE)).json() == []
    )
    cross = api_client.post(
        "/api/v1/supplier-profiles",
        headers=_headers(OTHER_WORKSPACE),
        json={"supplier_id": str(supplier_id), "risk_level": "low"},
    )
    assert cross.status_code == 404

    assert (
        api_client.post(
            "/api/v1/inventory-snapshots",
            headers=_headers(WORKSPACE),
            json={"product_id": str(product_id), "quantity": 10},
        ).status_code
        == 201
    )
    assert (
        api_client.get("/api/v1/inventory-snapshots", headers=_headers(OTHER_WORKSPACE)).json()
        == []
    )

    assert (
        api_client.post(
            "/api/v1/purchase-orders",
            headers=_headers(WORKSPACE),
            json={
                "po_number": "PO-ISO-001",
                "supplier_id": str(supplier_id),
                "items": [{"sku": "S1", "name": "Item", "quantity": 1, "unit_cost": "1.00"}],
            },
        ).status_code
        == 201
    )
    assert api_client.get("/api/v1/purchase-orders", headers=_headers(OTHER_WORKSPACE)).json() == []

    assert (
        api_client.post(
            "/api/v1/shipments",
            headers=_headers(WORKSPACE),
            json={"carrier": "Cainiao", "status": "created"},
        ).status_code
        == 201
    )
    assert api_client.get("/api/v1/shipments", headers=_headers(OTHER_WORKSPACE)).json() == []

    assert (
        api_client.post(
            "/api/v1/supply-chain-knowledge-entries",
            headers=_headers(WORKSPACE),
            json={
                "entry_type": "supplier_pattern",
                "title": "Reliable",
                "content": "On-time 92%",
            },
        ).status_code
        == 201
    )
    assert (
        api_client.get(
            "/api/v1/supply-chain-knowledge-entries", headers=_headers(OTHER_WORKSPACE)
        ).json()
        == []
    )
