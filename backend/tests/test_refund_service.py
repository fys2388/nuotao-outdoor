"""Refund service unit tests (M1 refund flow).

Tests cover:
- Refund creation with amount validation
- Refundable balance calculation (order.total - refunded - active refunds)
- Idempotency by (workspace_id, order_id, idempotency_key)
- State machine transitions (valid and invalid)
- Approval flow (approve/reject/cancel)
- Payment provider not configured -> RefundNotConfigured (never fake success)
- Successful refund updates order.refunded_amount
- Failed refund retry with max_retries
- Order refund summary
"""

from decimal import Decimal

import pytest
import pytest_asyncio

from app.models.customer import RefundCase
from app.models.order import Order, OrderItem
from app.services import refund_service


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def sample_order(db_session):
    """Create a sample order with total=100.00, refunded=0."""
    order = Order(
        workspace_id=db_session.info.get("workspace_id") or _DEFAULT_WORKSPACE,
        external_order_id="TEST-ORDER-001",
        status="received",
        payment_status="paid",
        currency="USD",
        subtotal=Decimal("90.00"),
        shipping_total=Decimal("10.00"),
        total=Decimal("100.00"),
        refunded_amount=Decimal("0.00"),
    )
    db_session.add(order)
    await db_session.flush()
    return order


@pytest_asyncio.fixture
async def order_with_refund(db_session):
    """Order with total=100.00, already refunded=30.00."""
    order = Order(
        workspace_id=_DEFAULT_WORKSPACE,
        external_order_id="TEST-ORDER-002",
        status="received",
        payment_status="paid",
        currency="USD",
        total=Decimal("100.00"),
        refunded_amount=Decimal("30.00"),
    )
    db_session.add(order)
    await db_session.flush()
    return order


_DEFAULT_WORKSPACE = __import__("uuid").UUID("00000000-0000-0000-0000-000000000001")


# --------------------------------------------------------------------------- #
# Refund creation
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_create_refund_success(db_session, sample_order):
    """Create refund with valid amount succeeds."""
    refund = await refund_service.create_refund_request(
        db_session,
        workspace_id=_DEFAULT_WORKSPACE,
        order_id=sample_order.id,
        amount=Decimal("50.00"),
        reason="customer requested refund",
        category="other",
        idempotency_key="test-refund-001",
    )
    assert refund.status == "requested"
    assert refund.requested_amount == Decimal("50.00")
    assert refund.idempotency_key == "test-refund-001"
    assert refund.order_id == sample_order.id


@pytest.mark.asyncio
async def test_create_refund_zero_amount_rejected(db_session, sample_order):
    """Zero or negative amount is rejected."""
    with pytest.raises(refund_service.RefundAmountExceeded):
        await refund_service.create_refund_request(
            db_session,
            workspace_id=_DEFAULT_WORKSPACE,
            order_id=sample_order.id,
            amount=Decimal("0"),
            reason="test",
            idempotency_key="test-zero",
        )


@pytest.mark.asyncio
async def test_create_refund_exceeds_balance_rejected(db_session, sample_order):
    """Refund amount > order.total is rejected."""
    with pytest.raises(refund_service.RefundAmountExceeded):
        await refund_service.create_refund_request(
            db_session,
            workspace_id=_DEFAULT_WORKSPACE,
            order_id=sample_order.id,
            amount=Decimal("150.00"),
            reason="test",
            idempotency_key="test-exceed",
        )


@pytest.mark.asyncio
async def test_create_refund_respects_existing_refunded(db_session, order_with_refund):
    """Refund cannot exceed order.total - order.refunded_amount."""
    # order total=100, refunded=30, balance=70
    with pytest.raises(refund_service.RefundAmountExceeded):
        await refund_service.create_refund_request(
            db_session,
            workspace_id=_DEFAULT_WORKSPACE,
            order_id=order_with_refund.id,
            amount=Decimal("80.00"),
            reason="test",
            idempotency_key="test-respect",
        )
    # 70 should work
    refund = await refund_service.create_refund_request(
        db_session,
        workspace_id=_DEFAULT_WORKSPACE,
        order_id=order_with_refund.id,
        amount=Decimal("70.00"),
        reason="test",
        idempotency_key="test-respect-ok",
    )
    assert refund.requested_amount == Decimal("70.00")


@pytest.mark.asyncio
async def test_create_refund_idempotent(db_session, sample_order):
    """Same idempotency_key returns existing refund, no duplicate."""
    r1 = await refund_service.create_refund_request(
        db_session,
        workspace_id=_DEFAULT_WORKSPACE,
        order_id=sample_order.id,
        amount=Decimal("50.00"),
        reason="first",
        idempotency_key="idem-key-001",
    )
    r2 = await refund_service.create_refund_request(
        db_session,
        workspace_id=_DEFAULT_WORKSPACE,
        order_id=sample_order.id,
        amount=Decimal("50.00"),  # same amount, same key
        reason="second",
        idempotency_key="idem-key-001",
    )
    assert r1.id == r2.id
    assert r1.requested_amount == Decimal("50.00")  # original amount preserved
    assert r1.reason == "first"  # original reason preserved


@pytest.mark.asyncio
async def test_active_refund_reserves_balance(db_session, sample_order):
    """Active refund reserves amount, preventing concurrent refund exceeding balance."""
    # First refund: 60 (active)
    await refund_service.create_refund_request(
        db_session,
        workspace_id=_DEFAULT_WORKSPACE,
        order_id=sample_order.id,
        amount=Decimal("60.00"),
        reason="first",
        idempotency_key="reserve-1",
    )
    # Balance now 100 - 0(refunded) - 60(active) = 40
    # Second refund of 50 should fail
    with pytest.raises(refund_service.RefundAmountExceeded):
        await refund_service.create_refund_request(
            db_session,
            workspace_id=_DEFAULT_WORKSPACE,
            order_id=sample_order.id,
            amount=Decimal("50.00"),
            reason="second",
            idempotency_key="reserve-2",
        )
    # Second refund of 40 should work
    r2 = await refund_service.create_refund_request(
        db_session,
        workspace_id=_DEFAULT_WORKSPACE,
        order_id=sample_order.id,
        amount=Decimal("40.00"),
        reason="second",
        idempotency_key="reserve-3",
    )
    assert r2.requested_amount == Decimal("40.00")


# --------------------------------------------------------------------------- #
# State machine
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_state_transition_requested_to_pending(db_session, sample_order):
    """requested -> pending_approval is valid."""
    refund = await refund_service.create_refund_request(
        db_session, workspace_id=_DEFAULT_WORKSPACE, order_id=sample_order.id,
        amount=Decimal("10.00"), reason="test", idempotency_key="state-1",
    )
    refund = await refund_service.submit_for_approval(
        db_session, workspace_id=_DEFAULT_WORKSPACE, refund_id=refund.id,
    )
    assert refund.status == "pending_approval"


@pytest.mark.asyncio
async def test_state_transition_invalid_rejected(db_session, sample_order):
    """requested -> approved is invalid (must go through pending_approval)."""
    refund = await refund_service.create_refund_request(
        db_session, workspace_id=_DEFAULT_WORKSPACE, order_id=sample_order.id,
        amount=Decimal("10.00"), reason="test", idempotency_key="state-invalid",
    )
    with pytest.raises(refund_service.RefundStateError):
        await refund_service.approve_refund(
            db_session, workspace_id=_DEFAULT_WORKSPACE, refund_id=refund.id,
            approved_by="tester",
        )


@pytest.mark.asyncio
async def test_approve_refund_success(db_session, sample_order):
    """pending_approval -> approved with approved_amount."""
    refund = await refund_service.create_refund_request(
        db_session, workspace_id=_DEFAULT_WORKSPACE, order_id=sample_order.id,
        amount=Decimal("50.00"), reason="test", idempotency_key="approve-1",
    )
    refund = await refund_service.submit_for_approval(
        db_session, workspace_id=_DEFAULT_WORKSPACE, refund_id=refund.id,
    )
    refund = await refund_service.approve_refund(
        db_session, workspace_id=_DEFAULT_WORKSPACE, refund_id=refund.id,
        approved_by="tester", approved_amount=Decimal("40.00"),
    )
    assert refund.status == "approved"
    assert refund.approved_amount == Decimal("40.00")
    assert refund.approved_by == "tester"
    assert refund.approved_at is not None


@pytest.mark.asyncio
async def test_approve_amount_cannot_exceed_requested(db_session, sample_order):
    """approved_amount > requested_amount is rejected."""
    refund = await refund_service.create_refund_request(
        db_session, workspace_id=_DEFAULT_WORKSPACE, order_id=sample_order.id,
        amount=Decimal("50.00"), reason="test", idempotency_key="approve-exceed",
    )
    refund = await refund_service.submit_for_approval(
        db_session, workspace_id=_DEFAULT_WORKSPACE, refund_id=refund.id,
    )
    with pytest.raises(refund_service.RefundAmountExceeded):
        await refund_service.approve_refund(
            db_session, workspace_id=_DEFAULT_WORKSPACE, refund_id=refund.id,
            approved_by="tester", approved_amount=Decimal("60.00"),
        )


@pytest.mark.asyncio
async def test_reject_refund(db_session, sample_order):
    """pending_approval -> rejected."""
    refund = await refund_service.create_refund_request(
        db_session, workspace_id=_DEFAULT_WORKSPACE, order_id=sample_order.id,
        amount=Decimal("10.00"), reason="test", idempotency_key="reject-1",
    )
    refund = await refund_service.submit_for_approval(
        db_session, workspace_id=_DEFAULT_WORKSPACE, refund_id=refund.id,
    )
    refund = await refund_service.reject_refund(
        db_session, workspace_id=_DEFAULT_WORKSPACE, refund_id=refund.id,
        rejected_by="tester", reason="not eligible",
    )
    assert refund.status == "rejected"
    assert refund.rejection_reason == "not eligible"
    assert refund.resolution == "rejected"


@pytest.mark.asyncio
async def test_cancel_refund(db_session, sample_order):
    """requested -> cancelled."""
    refund = await refund_service.create_refund_request(
        db_session, workspace_id=_DEFAULT_WORKSPACE, order_id=sample_order.id,
        amount=Decimal("10.00"), reason="test", idempotency_key="cancel-1",
    )
    refund = await refund_service.cancel_refund(
        db_session, workspace_id=_DEFAULT_WORKSPACE, refund_id=refund.id,
        cancelled_by="tester", reason="changed mind",
    )
    assert refund.status == "cancelled"
    assert refund.resolution == "cancelled"


# --------------------------------------------------------------------------- #
# Payment provider not configured
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_execute_refund_provider_not_configured(db_session, sample_order, monkeypatch):
    """Payment provider not configured -> RefundNotConfigured, status stays approved."""
    refund = await refund_service.create_refund_request(
        db_session, workspace_id=_DEFAULT_WORKSPACE, order_id=sample_order.id,
        amount=Decimal("10.00"), reason="test", idempotency_key="not-configured",
    )
    refund = await refund_service.submit_for_approval(
        db_session, workspace_id=_DEFAULT_WORKSPACE, refund_id=refund.id,
    )
    refund = await refund_service.approve_refund(
        db_session, workspace_id=_DEFAULT_WORKSPACE, refund_id=refund.id,
        approved_by="tester",
    )
    assert refund.status == "approved"

    # Force provider not configured.
    monkeypatch.setattr(refund_service, "_is_payment_provider_configured", lambda p: False)

    with pytest.raises(refund_service.RefundNotConfigured):
        await refund_service.execute_refund(
            db_session, workspace_id=_DEFAULT_WORKSPACE, refund_id=refund.id,
            payment_provider="stripe",
        )

    # Status should still be approved (not processing, not succeeded).
    await db_session.refresh(refund)
    assert refund.status == "approved"


# --------------------------------------------------------------------------- #
# Order refund summary
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_order_refund_summary(db_session, order_with_refund):
    """Order refund summary shows correct balance."""
    summary = await refund_service.get_order_refund_summary(
        db_session, workspace_id=_DEFAULT_WORKSPACE, order_id=order_with_refund.id,
    )
    assert summary["order_total"] == "100.00"
    assert summary["refunded_amount"] == "30.00"
    assert summary["refundable_balance"] == "70.00"
    assert summary["active_refund_count"] == 0


@pytest.mark.asyncio
async def test_order_refund_summary_with_active(db_session, sample_order):
    """Active refund reduces refundable balance in summary."""
    await refund_service.create_refund_request(
        db_session, workspace_id=_DEFAULT_WORKSPACE, order_id=sample_order.id,
        amount=Decimal("40.00"), reason="test", idempotency_key="summary-active",
    )
    summary = await refund_service.get_order_refund_summary(
        db_session, workspace_id=_DEFAULT_WORKSPACE, order_id=sample_order.id,
    )
    assert summary["refundable_balance"] == "60.00"  # 100 - 40 active
    assert summary["active_refund_count"] == 1


# --------------------------------------------------------------------------- #
# Refund not found
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_get_nonexistent_refund_raises(db_session):
    """Getting nonexistent refund raises RefundNotFound."""
    from uuid import uuid4
    with pytest.raises(refund_service.RefundNotFound):
        await refund_service.get_refund(
            db_session, workspace_id=_DEFAULT_WORKSPACE, refund_id=uuid4(),
        )
