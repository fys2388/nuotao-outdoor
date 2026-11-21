"""T0.2 procurement governance closure tests (M4.2.0).

Owner directive: prove the ENTIRE purchase-approval system has no bypass path,
not merely that one function was patched. These tests assert:

- No creation entry point can produce an ``approved`` purchase order directly
  (Agent auto-create, low-value automation, raw-status endpoint all fail-closed).
- ``approved`` is reachable ONLY through the explicit, RBAC-protected approve
  endpoint, which records an attributable operator identity.
- AI / automation can never be the authorizing subject of its own approval.
- Illegal state jumps are rejected (fail-closed); history stays compatible.
- Every write emits an auditable event with trace_id.
"""

from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from app.api.v1.endpoints.auth import get_current_user
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.event import EventLog
from app.models.product import Product
from app.models.supply_chain import PurchaseOrder
from app.schemas.user import UserResponse
from app.services import procurement_service, purchase_automation_service, supply_chain
from datetime import UTC, datetime

WORKSPACE = DEFAULT_WORKSPACE_ID


def _headers() -> dict:
    return {"X-Workspace-Id": str(WORKSPACE)}


async def _event_types(db_session) -> set[str]:
    rows = (await db_session.execute(select(EventLog.event_type))).scalars().all()
    return set(rows)


async def _seed_product(db_session, sku: str = "GOV-PROD-001") -> UUID:
    product = Product(workspace_id=WORKSPACE, sku=sku, name=f"Product {sku}")
    db_session.add(product)
    await db_session.flush()
    return product.id


async def _make_draft_po(db_session, api_client, po_number: str) -> UUID:
    """Create a PO via the canonical API; assert it lands in draft (never approved)."""
    response = api_client.post(
        "/api/v1/purchase-orders",
        json={
            "po_number": po_number,
            "items": [{"sku": "TENT-1", "name": "Tent 1P", "quantity": 2, "unit_cost": "10.00"}],
        },
        headers=_headers(),
    )
    assert response.status_code == 201, response.text
    po = response.json()
    assert po["status"] == "draft", "creation must never be approved"
    return UUID(po["id"])


def _override_role(api_client, role: str) -> None:
    """Swap the resolved current user to a given role for RBAC negative tests."""
    user = UserResponse(
        id=f"test-{role}",
        username=role,
        email=f"{role}@example.com",
        role=role,
        is_active=True,
        created_at=datetime.now(UTC),
    )
    api_client.app.dependency_overrides[get_current_user] = lambda: user


# --------------------------------------------------------------------------- #
# 1. Creation entries can never produce `approved` directly
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_agent_create_purchase_order_lands_in_draft(db_session) -> None:
    """procurement_service.create_purchase_order (Agent path) must create draft."""
    product_id = await _seed_product(db_session)
    result = await procurement_service.create_purchase_order(
        db_session, str(product_id), 5, {"workspace_id": str(WORKSPACE), "unit_cost": 10}
    )
    assert result["success"] is True
    assert result["status"] == "draft", "Agent-created PO must be draft, not approved"

    po = (
        await db_session.execute(
            select(PurchaseOrder).where(PurchaseOrder.id == UUID(result["purchase_order_id"]))
        )
    ).scalar_one()
    assert po.status == "draft"


@pytest.mark.asyncio
async def test_low_value_automation_never_auto_approves(db_session) -> None:
    """Low-value automation must NOT auto-approve; approved requires a human gate."""
    product_id = await _seed_product(db_session, sku="GOV-AUTO-001")
    rules = purchase_automation_service.DEFAULT_PURCHASE_RULES.copy()
    rules["auto_purchase_enabled"] = True
    rules["auto_approve_low_value"] = True  # even when low-value auto-approve is on
    rules["require_approval_above"] = Decimal("1000000.00")  # force the low-value branch

    import app.services.purchase_automation_service as pas

    original = pas.load_purchase_rules
    pas.load_purchase_rules = lambda: rules
    try:
        result = await pas.auto_generate_purchase_order(
            db_session,
            product_id=product_id,
            quantity=2,
            unit_cost=Decimal("5.00"),
            workspace_id=WORKSPACE,
        )
    finally:
        pas.load_purchase_rules = original

    assert result["success"] is True
    po_info = result["purchase_order"]
    assert po_info["status"] != "approved", "automation must never emit approved"
    assert po_info["auto_approved"] is False


# --------------------------------------------------------------------------- #
# 2. approved is only reachable via explicit, attributable approval
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_service_approve_requires_operator_identity(db_session, api_client) -> None:
    """Approving without an operator identity fails closed (AI cannot self-approve)."""
    po_id = await _make_draft_po(db_session, api_client, "GOV-001")
    with pytest.raises(supply_chain.SupplyChainError, match="approved_by"):
        await supply_chain.approve_purchase_order(
            db_session, workspace_id=WORKSPACE, po_id=po_id, approved_by=None
        )


@pytest.mark.asyncio
async def test_approve_records_operator_and_time(db_session, api_client) -> None:
    """A legitimate approval records who approved and when, plus an audit event."""
    po_id = await _make_draft_po(db_session, api_client, "GOV-002")
    po = await supply_chain.approve_purchase_order(
        db_session,
        workspace_id=WORKSPACE,
        po_id=po_id,
        approved_by="buyer@nuotao.com",
        approval_note="stock replenishment",
    )
    assert po.status == "approved"
    assert po.approved_by == "buyer@nuotao.com"
    assert po.approved_at is not None
    assert po.approval_note == "stock replenishment"
    assert "supply.purchase_order_approved" in await _event_types(db_session)


@pytest.mark.asyncio
async def test_api_approve_endpoint_records_identity(db_session, api_client) -> None:
    """The approve endpoint (RBAC operator+) persists the approving identity."""
    po_id = await _make_draft_po(db_session, api_client, "GOV-003")
    # api_client resolves an admin user (email admin@example.com) by default.
    response = api_client.post(f"/api/v1/purchase-orders/{po_id}/approve", headers=_headers())
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "approved"
    stored = (
        await db_session.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id))
    ).scalar_one()
    assert stored.approved_by, "approved_by must be recorded by the endpoint"


# --------------------------------------------------------------------------- #
# 3. RBAC: unauthorized roles cannot approve
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_readonly_role_cannot_approve(db_session, api_client) -> None:
    """A non-operator (read-only) role is rejected with 403."""
    po_id = await _make_draft_po(db_session, api_client, "GOV-004")
    _override_role(api_client, "read_only")
    try:
        response = api_client.post(
            f"/api/v1/purchase-orders/{po_id}/approve", headers=_headers()
        )
        assert response.status_code == 403, response.text
        # fail-closed: PO must remain draft
        stored = (
            await db_session.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id))
        ).scalar_one()
        assert stored.status == "draft"
    finally:
        api_client.app.dependency_overrides.pop(get_current_user, None)


# --------------------------------------------------------------------------- #
# 4. Illegal transitions / double-approve fail closed
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_double_approve_rejected(db_session, api_client) -> None:
    """Approving an already-approved PO is an illegal jump -> 400."""
    po_id = await _make_draft_po(db_session, api_client, "GOV-005")
    first = api_client.post(f"/api/v1/purchase-orders/{po_id}/approve", headers=_headers())
    assert first.status_code == 200
    second = api_client.post(f"/api/v1/purchase-orders/{po_id}/approve", headers=_headers())
    assert second.status_code == 400
    assert "cannot transition" in second.json()["detail"]


@pytest.mark.asyncio
async def test_draft_to_received_rejected(db_session, api_client) -> None:
    """draft -> received is an illegal jump; must go through approval + ordering."""
    po_id = await _make_draft_po(db_session, api_client, "GOV-006")
    response = api_client.post(f"/api/v1/purchase-orders/{po_id}/receive", headers=_headers())
    assert response.status_code == 400
    stored = (
        await db_session.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id))
    ).scalar_one()
    assert stored.status == "draft"


@pytest.mark.asyncio
async def test_status_endpoint_cannot_set_approved(db_session, api_client) -> None:
    """The PATCH status endpoint must refuse to set `approved` (bypass guard)."""
    po_id = await _make_draft_po(db_session, api_client, "GOV-007")
    response = api_client.patch(
        f"/api/v1/purchase-orders/{po_id}/status",
        json={"status": "approved"},
        headers=_headers(),
    )
    assert response.status_code == 409, response.text
    stored = (
        await db_session.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id))
    ).scalar_one()
    assert stored.status == "draft"


@pytest.mark.asyncio
async def test_status_endpoint_routes_through_state_machine(db_session, api_client) -> None:
    """PATCH status uses the canonical state machine and records the operator."""
    po_id = await _make_draft_po(db_session, api_client, "GOV-008")
    api_client.post(f"/api/v1/purchase-orders/{po_id}/approve", headers=_headers())
    response = api_client.patch(
        f"/api/v1/purchase-orders/{po_id}/status",
        json={"status": "cancelled"},
        headers=_headers(),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["updated_by"], "operator identity recorded on status change"


# --------------------------------------------------------------------------- #
# 5. History compatibility + trace_id / event integrity
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_history_po_without_approval_fields_readable(db_session, api_client) -> None:
    """Legacy POs (approved before audit fields existed) remain readable; new fields NULL."""
    po_id = await _make_draft_po(db_session, api_client, "GOV-009")
    # Simulate a legacy approved row written before audit fields existed.
    po = (
        await db_session.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id))
    ).scalar_one()
    po.status = "approved"
    po.approved_at = None
    po.approved_by = None
    await db_session.flush()

    detail = api_client.get(f"/api/v1/purchase-orders/{po_id}", headers=_headers())
    assert detail.status_code == 200, detail.text
    assert detail.json()["status"] == "approved"


@pytest.mark.asyncio
async def test_agent_creation_emits_traceable_event(db_session) -> None:
    """Agent auto-create emits an auditable event carrying the trace_id."""
    product_id = await _seed_product(db_session, sku="GOV-TRACE-001")
    trace = "trace-gov-unit"
    await procurement_service.create_purchase_order(
        db_session, str(product_id), 3, {"workspace_id": str(WORKSPACE), "trace_id": trace}
    )
    row = (
        await db_session.execute(
            select(EventLog).where(EventLog.event_type == "supply.purchase_order_created")
        )
    ).scalars().first()
    assert row is not None, "Agent auto-create must emit an auditable event"
    assert row.trace_id == trace, "event must carry the originating trace_id"
    assert row.payload.get("status") == "draft"
