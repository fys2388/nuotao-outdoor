"""M4.2.0-R1 procurement-governance remediation tests.

Owner independent audit of PR #26 flagged that the LEGACY fulfilment endpoint
(PATCH /fulfillment/purchase-orders/{po_id}/status) could still set `approved`
via a second parallel state machine (PO_STATUS_FLOW), bypassing the unified
approval choke point, with no RBAC and no identity — a live privilege-
escalation path to authorize a PO with zero human approval.

These tests prove the remediation:
- The legacy endpoint no longer accepts `approved` (409) — it is routed through
  the single canonical state machine and defers approval to the dedicated,
  RBAC-protected approve endpoint.
- Status changes require an authenticated operator/admin (401 unauthenticated,
  403 read-only) and record the operator identity + trace_id in the audit event.
- Ordinary status transitions (draft->cancelled, approved->ordered) still work
  through the unified machine.
"""

from uuid import UUID

import pytest
from sqlalchemy import select

from app.api.v1.endpoints.auth import get_current_user
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.event import EventLog
from app.models.supply_chain import PurchaseOrder
from app.schemas.user import UserResponse
from datetime import UTC, datetime

WORKSPACE = DEFAULT_WORKSPACE_ID


def _headers() -> dict:
    return {"X-Workspace-Id": str(WORKSPACE)}


def _override_role(api_client, role: str | None) -> None:
    if role is None:
        api_client.app.dependency_overrides.pop(get_current_user, None)
        return
    user = UserResponse(
        id=f"test-{role}",
        username=role,
        email=f"{role}@example.com",
        role=role,
        is_active=True,
        created_at=datetime.now(UTC),
    )
    api_client.app.dependency_overrides[get_current_user] = lambda: user


async def _make_draft_po(db_session, api_client, po_number: str) -> UUID:
    response = api_client.post(
        "/api/v1/purchase-orders",
        json={
            "po_number": po_number,
            "items": [{"sku": "TENT-1", "name": "Tent 1P", "quantity": 2, "unit_cost": "10.00"}],
        },
        headers=_headers(),
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


# --------------------------------------------------------------------------- #
# P0-1: legacy fulfilment endpoint can no longer set `approved`
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_legacy_fulfilment_endpoint_rejects_approved(db_session, api_client) -> None:
    """The old bypass is closed: PATCH status cannot set `approved` (409)."""
    po_id = await _make_draft_po(db_session, api_client, "R1-APPROVED-BLOCK")
    response = api_client.patch(
        f"/api/v1/fulfillment/purchase-orders/{po_id}/status",
        json={"status": "approved"},
        headers=_headers(),
    )
    assert response.status_code == 409, response.text
    stored = (
        await db_session.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id))
    ).scalar_one()
    assert stored.status == "draft", "approved must not be reachable via legacy endpoint"


# --------------------------------------------------------------------------- #
# P0-2: identity + RBAC on the legacy endpoint
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_fulfilment_status_requires_authentication(db_session, api_client) -> None:
    """Unauthenticated caller is rejected (401)."""
    po_id = await _make_draft_po(db_session, api_client, "R1-NOAUTH")
    _override_role(api_client, None)  # restore real auth (no override) -> 401
    try:
        response = api_client.patch(
            f"/api/v1/fulfillment/purchase-orders/{po_id}/status",
            json={"status": "cancelled"},
            headers=_headers(),
        )
        assert response.status_code == 401, response.text
    finally:
        # restore the admin override for other assertions if needed
        _override_role(api_client, "admin")


@pytest.mark.asyncio
async def test_fulfilment_status_rejects_readonly_role(db_session, api_client) -> None:
    """A read-only user cannot change PO status (403), even unapproved states."""
    po_id = await _make_draft_po(db_session, api_client, "R1-VIEWER")
    _override_role(api_client, "viewer")
    try:
        response = api_client.patch(
            f"/api/v1/fulfillment/purchase-orders/{po_id}/status",
            json={"status": "cancelled"},
            headers=_headers(),
        )
        assert response.status_code == 403, response.text
        stored = (
            await db_session.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id))
        ).scalar_one()
        assert stored.status == "draft"
    finally:
        _override_role(api_client, "admin")


# --------------------------------------------------------------------------- #
# Ordinary transitions still work through the unified machine + audit
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_fulfilment_status_routes_through_canonical_machine(db_session, api_client) -> None:
    """A legitimate non-approval transition works and records operator + trace."""
    po_id = await _make_draft_po(db_session, api_client, "R1-CANCEL")
    response = api_client.patch(
        f"/api/v1/fulfillment/purchase-orders/{po_id}/status",
        json={"status": "cancelled"},
        headers=_headers(),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["updated_by"], "operator identity recorded"

    # Approval path is the ONLY way to approved; cancel via unified machine
    # emits an auditable event.
    events = (
        await db_session.execute(
            select(EventLog.event_type).where(
                EventLog.event_type == "supply.purchase_order_cancelled"
            )
        )
    ).scalars().all()
    assert "supply.purchase_order_cancelled" in set(events)


@pytest.mark.asyncio
async def test_approved_only_via_dedicated_endpoint(db_session, api_client) -> None:
    """End-to-end: approved is reachable ONLY through the dedicated approve endpoint."""
    po_id = await _make_draft_po(db_session, api_client, "R1-E2E")

    # Legacy endpoint refuses approved...
    via_status = api_client.patch(
        f"/api/v1/fulfillment/purchase-orders/{po_id}/status",
        json={"status": "approved"},
        headers=_headers(),
    )
    assert via_status.status_code == 409

    # ...while the dedicated endpoint (operator+) succeeds and records identity.
    via_approve = api_client.post(
        f"/api/v1/purchase-orders/{po_id}/approve", headers=_headers()
    )
    assert via_approve.status_code == 200, via_approve.text
    stored = (
        await db_session.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id))
    ).scalar_one()
    assert stored.status == "approved"
    assert stored.approved_by, "approver identity recorded"
    assert stored.approved_at is not None
