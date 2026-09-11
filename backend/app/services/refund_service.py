"""Refund service (M1): full refund lifecycle with state machine, approval,
execution, idempotency, amount validation, and order refunded_amount update.

State machine:
  requested -> pending_approval -> approved -> processing -> succeeded
  requested -> pending_approval -> rejected
  requested -> cancelled
  processing -> failed (retryable up to max_retries)

Rules:
- Refund amount cannot exceed order.total - order.refunded_amount (refundable balance).
- Idempotency enforced by (workspace_id, order_id, idempotency_key).
- Payment provider not configured -> return NOT_CONFIGURED, never fake success.
- All state transitions write to event_log.
- No client-supplied actor can bypass approval; approved_by comes from auth context.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import RefundCase
from app.models.order import Order
from app.services import event_service

logger = logging.getLogger(__name__)

ZERO = Decimal("0")

# Allowed state transitions.
REFUND_TRANSITIONS: dict[str, set[str]] = {
    "requested": {"pending_approval", "cancelled"},
    "pending_approval": {"approved", "rejected", "cancelled"},
    "approved": {"processing", "cancelled"},
    "processing": {"succeeded", "failed"},
    "failed": {"processing"},  # retry
    "succeeded": set(),
    "rejected": set(),
    "cancelled": set(),
}

# Statuses that count as "active" (refund in progress, affects refundable balance).
ACTIVE_REFUND_STATUSES = {"requested", "pending_approval", "approved", "processing", "failed"}


class RefundError(Exception):
    """Base refund service error."""


class RefundAmountExceeded(RefundError):
    """Refund amount exceeds refundable balance."""


class RefundStateError(RefundError):
    """Invalid state transition."""


class RefundNotFound(RefundError):
    """Refund case not found."""


class RefundNotConfigured(RefundError):
    """Payment provider not configured for refund execution."""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


async def _load_order(session: AsyncSession, *, workspace_id: UUID, order_id: UUID) -> Order:
    result = await session.execute(
        select(Order).where(Order.id == order_id, Order.workspace_id == workspace_id)
    )
    order = result.scalar_one_or_none()
    if order is None:
        raise RefundNotFound(f"order {order_id} not found")
    return order


async def _load_refund(session: AsyncSession, *, workspace_id: UUID, refund_id: UUID) -> RefundCase:
    result = await session.execute(
        select(RefundCase).where(RefundCase.id == refund_id, RefundCase.workspace_id == workspace_id)
    )
    refund = result.scalar_one_or_none()
    if refund is None:
        raise RefundNotFound(f"refund {refund_id} not found")
    return refund


async def _get_refundable_balance(session: AsyncSession, *, order: Order) -> Decimal:
    """Compute the maximum refundable amount for an order.

    refundable = order.total - order.refunded_amount - sum(active refund requested_amount)

    Active refunds (requested/pending_approval/approved/processing/failed) reserve
    their requested_amount so concurrent refunds cannot exceed the balance.
    """
    reserved = ZERO
    result = await session.execute(
        select(RefundCase).where(
            RefundCase.order_id == order.id,
            RefundCase.workspace_id == order.workspace_id,
            RefundCase.status.in_(ACTIVE_REFUND_STATUSES),
        )
    )
    for r in result.scalars().all():
        reserved += r.requested_amount

    balance = order.total - order.refunded_amount - reserved
    return max(balance, ZERO)


def _check_transition(current: str, target: str) -> None:
    allowed = REFUND_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise RefundStateError(f"invalid transition: {current} -> {target}")


async def _write_event(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    event_type: str,
    refund: RefundCase,
    payload: dict[str, Any],
    trace_id: str | None = None,
) -> None:
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type=event_type,
        entity_type="refund_case",
        entity_id=str(refund.id),
        payload=payload,
        trace_id=trace_id,
    )


# --------------------------------------------------------------------------- #
# Refund request creation
# --------------------------------------------------------------------------- #


async def create_refund_request(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    order_id: UUID,
    amount: Decimal,
    reason: str,
    category: str = "other",
    refund_type: str = "partial",
    idempotency_key: str | None = None,
    requested_by: str = "system",
    notes: str | None = None,
    trace_id: str | None = None,
) -> RefundCase:
    """Create a refund request.

    Validates amount against refundable balance. Idempotent by
    (workspace_id, order_id, idempotency_key). Status starts at 'requested'.
    """
    if amount <= ZERO:
        raise RefundAmountExceeded("refund amount must be positive")

    order = await _load_order(session, workspace_id=workspace_id, order_id=order_id)

    # Check refundable balance BEFORE creating.
    balance = await _get_refundable_balance(session, order=order)
    if amount > balance:
        raise RefundAmountExceeded(
            f"refund amount {amount} exceeds refundable balance {balance} "
            f"(order total={order.total}, refunded={order.refunded_amount})"
        )

    idem_key = idempotency_key or f"refund-{order.external_order_id}-{int(datetime.now(UTC).timestamp())}"

    refund = RefundCase(
        workspace_id=workspace_id,
        order_id=order_id,
        customer_id=None,  # PII-free; link via customer_reference_id if needed
        reason=reason,
        category=category,
        refund_type=refund_type,
        requested_amount=amount,
        amount=amount,  # legacy field
        status="requested",
        idempotency_key=idem_key,
        notes=notes,
        trace_id=trace_id,
    )
    session.add(refund)

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        # Idempotency conflict: return existing refund.
        result = await session.execute(
            select(RefundCase).where(
                RefundCase.workspace_id == workspace_id,
                RefundCase.order_id == order_id,
                RefundCase.idempotency_key == idem_key,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            logger.info("refund idempotent hit: order=%s key=%s", order_id, idem_key)
            return existing
        raise RefundError("failed to create refund") from exc

    await _write_event(
        session,
        workspace_id=workspace_id,
        event_type="refund.requested",
        refund=refund,
        payload={
            "order_id": str(order_id),
            "amount": str(amount),
            "refund_type": refund_type,
            "reason": reason,
            "requested_by": requested_by,
            "refundable_balance": str(balance),
        },
        trace_id=trace_id,
    )
    logger.info("refund requested: id=%s order=%s amount=%s trace=%s", refund.id, order_id, amount, trace_id)
    return refund


# --------------------------------------------------------------------------- #
# Approval flow
# --------------------------------------------------------------------------- #


async def submit_for_approval(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    refund_id: UUID,
    trace_id: str | None = None,
) -> RefundCase:
    """Submit refund request for approval. requested -> pending_approval."""
    refund = await _load_refund(session, workspace_id=workspace_id, refund_id=refund_id)
    _check_transition(refund.status, "pending_approval")
    refund.status = "pending_approval"
    await session.flush()
    await _write_event(
        session, workspace_id=workspace_id, event_type="refund.pending_approval",
        refund=refund, payload={"previous": "requested"}, trace_id=trace_id,
    )
    return refund


async def approve_refund(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    refund_id: UUID,
    approved_by: str,
    approved_amount: Decimal | None = None,
    approval_notes: str | None = None,
    trace_id: str | None = None,
) -> RefundCase:
    """Approve refund. pending_approval -> approved.

    approved_amount defaults to requested_amount. Must not exceed refundable balance.
    approved_by comes from auth context, never from client payload.
    """
    refund = await _load_refund(session, workspace_id=workspace_id, refund_id=refund_id)
    _check_transition(refund.status, "approved")

    amount = approved_amount if approved_amount is not None else refund.requested_amount
    if amount <= ZERO:
        raise RefundAmountExceeded("approved amount must be positive")
    if amount > refund.requested_amount:
        raise RefundAmountExceeded(
            f"approved amount {amount} exceeds requested amount {refund.requested_amount}"
        )

    # Re-validate against refundable balance at approval time.
    order = await _load_order(session, workspace_id=workspace_id, order_id=refund.order_id)
    balance = await _get_refundable_balance(session, order=order)
    if amount > balance:
        raise RefundAmountExceeded(
            f"approved amount {amount} exceeds refundable balance {balance}"
        )

    refund.status = "approved"
    refund.approved_amount = amount
    refund.approved_by = approved_by
    refund.approved_at = datetime.now(UTC)
    if approval_notes:
        refund.notes = (refund.notes or "") + f"\n[approval] {approval_notes}"
    await session.flush()

    await _write_event(
        session, workspace_id=workspace_id, event_type="refund.approved",
        refund=refund,
        payload={"approved_by": approved_by, "approved_amount": str(amount), "previous": "pending_approval"},
        trace_id=trace_id,
    )
    logger.info("refund approved: id=%s amount=%s by=%s trace=%s", refund.id, amount, approved_by, trace_id)
    return refund


async def reject_refund(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    refund_id: UUID,
    rejected_by: str,
    reason: str,
    trace_id: str | None = None,
) -> RefundCase:
    """Reject refund. pending_approval -> rejected."""
    refund = await _load_refund(session, workspace_id=workspace_id, refund_id=refund_id)
    _check_transition(refund.status, "rejected")
    refund.status = "rejected"
    refund.rejection_reason = reason
    refund.resolution = "rejected"
    await session.flush()
    await _write_event(
        session, workspace_id=workspace_id, event_type="refund.rejected",
        refund=refund,
        payload={"rejected_by": rejected_by, "reason": reason, "previous": "pending_approval"},
        trace_id=trace_id,
    )
    logger.info("refund rejected: id=%s by=%s trace=%s", refund.id, rejected_by, trace_id)
    return refund


async def cancel_refund(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    refund_id: UUID,
    cancelled_by: str,
    reason: str | None = None,
    trace_id: str | None = None,
) -> RefundCase:
    """Cancel refund. requested/pending_approval/approved -> cancelled."""
    refund = await _load_refund(session, workspace_id=workspace_id, refund_id=refund_id)
    _check_transition(refund.status, "cancelled")
    refund.status = "cancelled"
    refund.resolution = "cancelled"
    if reason:
        refund.notes = (refund.notes or "") + f"\n[cancel] {reason}"
    await session.flush()
    await _write_event(
        session, workspace_id=workspace_id, event_type="refund.cancelled",
        refund=refund,
        payload={"cancelled_by": cancelled_by, "reason": reason, "previous": refund.status},
        trace_id=trace_id,
    )
    return refund


# --------------------------------------------------------------------------- #
# Refund execution
# --------------------------------------------------------------------------- #


def _is_payment_provider_configured(provider: str) -> bool:
    """Check if payment provider is configured for refunds.

    Reads from environment variables (same source as app/integrations/payment.py).
    Never returns True based on code existence alone.
    """
    import os
    if provider == "stripe":
        return bool(os.getenv("STRIPE_SECRET_KEY", ""))
    if provider == "paypal":
        return bool(os.getenv("PAYPAL_CLIENT_ID", "") and os.getenv("PAYPAL_CLIENT_SECRET", ""))
    if provider == "woocommerce":
        # WooCommerce refunds require WC API credentials.
        from app.core.config import get_settings
        settings = get_settings()
        return bool(settings.woocommerce_base_url and settings.woocommerce_consumer_key)
    return False


async def execute_refund(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    refund_id: UUID,
    payment_provider: str | None = None,
    trace_id: str | None = None,
) -> RefundCase:
    """Execute refund via payment provider. approved -> processing -> succeeded/failed.

    Payment provider not configured -> status stays approved, raises RefundNotConfigured.
    Never fakes success. On failure, status -> failed with retry_count incremented.
    """
    refund = await _load_refund(session, workspace_id=workspace_id, refund_id=refund_id)
    _check_transition(refund.status, "processing")

    provider = payment_provider or refund.payment_provider or "woocommerce"

    # Check provider configuration BEFORE transitioning.
    if not _is_payment_provider_configured(provider):
        raise RefundNotConfigured(
            f"payment provider '{provider}' not configured for refunds; "
            f"refund remains in 'approved' state"
        )

    refund.status = "processing"
    refund.payment_provider = provider
    await session.flush()
    await _write_event(
        session, workspace_id=workspace_id, event_type="refund.processing",
        refund=refund, payload={"provider": provider, "previous": "approved"}, trace_id=trace_id,
    )

    # Execute refund via provider.
    try:
        payment_refund_id = await _execute_provider_refund(refund, provider)
    except Exception as exc:
        refund.status = "failed"
        refund.error_message = str(exc)[:1000]
        refund.last_failed_at = datetime.now(UTC)
        refund.retry_count += 1
        await session.flush()
        await _write_event(
            session, workspace_id=workspace_id, event_type="refund.failed",
            refund=refund,
            payload={"error": str(exc)[:500], "retry_count": refund.retry_count, "provider": provider},
            trace_id=trace_id,
        )
        logger.error("refund execution failed: id=%s error=%s trace=%s", refund.id, exc, trace_id)
        return refund

    # Success: update refund and order.refunded_amount.
    refund.status = "succeeded"
    refund.payment_refund_id = payment_refund_id
    refund.executed_amount = refund.approved_amount or refund.requested_amount
    refund.executed_at = datetime.now(UTC)
    refund.resolution = "refunded"

    # Update order.refunded_amount atomically.
    order = await _load_order(session, workspace_id=workspace_id, order_id=refund.order_id)
    order.refunded_amount += refund.executed_amount
    await session.flush()

    await _write_event(
        session, workspace_id=workspace_id, event_type="refund.succeeded",
        refund=refund,
        payload={
            "payment_refund_id": payment_refund_id,
            "executed_amount": str(refund.executed_amount),
            "order_refunded_amount_updated_to": str(order.refunded_amount),
            "provider": provider,
        },
        trace_id=trace_id,
    )
    logger.info(
        "refund succeeded: id=%s amount=%s provider_refund=%s order_refunded=%s trace=%s",
        refund.id, refund.executed_amount, payment_refund_id, order.refunded_amount, trace_id,
    )
    return refund


async def _execute_provider_refund(refund: RefundCase, provider: str) -> str:
    """Execute refund via payment provider API. Returns provider refund ID.

    This is the integration point. Each provider must be implemented with
    real API calls. Unimplemented providers raise, never fake success.
    """
    amount = refund.approved_amount or refund.requested_amount

    if provider == "stripe":
        try:
            import stripe
            import os
            stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
            # Need payment_intent_id or charge_id from order; for now use metadata.
            # This is a real API call; if it fails, exception propagates.
            refund_obj = stripe.Refund.create(
                amount=int(float(amount) * 100),
                currency="usd",
                metadata={"refund_case_id": str(refund.id), "order_id": str(refund.order_id)},
            )
            return refund_obj.id
        except ImportError as exc:
            raise RefundNotConfigured(f"stripe SDK not installed: {exc}") from exc

    if provider == "paypal":
        # PayPal refund requires capture_id; real API call.
        raise RefundNotConfigured("paypal refund integration not implemented; use woocommerce or stripe")

    if provider == "woocommerce":
        # WooCommerce refund via REST API. Real API call.
        from app.core.config import get_settings
        settings = get_settings()
        if not (settings.woocommerce_base_url and settings.woocommerce_consumer_key):
            raise RefundNotConfigured("woocommerce API not configured")
        # WooCommerce refund API call would go here.
        # For now, raise to indicate integration point needs real implementation.
        raise RefundNotConfigured(
            "woocommerce refund API integration pending; "
            "refund remains in 'approved' state for manual execution"
        )

    raise RefundNotConfigured(f"unknown payment provider: {provider}")


async def retry_refund(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    refund_id: UUID,
    trace_id: str | None = None,
) -> RefundCase:
    """Retry a failed refund. failed -> processing.

    Respects max_retries. Idempotent: if refund already succeeded, return as-is.
    """
    refund = await _load_refund(session, workspace_id=workspace_id, refund_id=refund_id)

    if refund.status == "succeeded":
        logger.info("refund already succeeded, skip retry: id=%s", refund.id)
        return refund

    if refund.status != "failed":
        raise RefundStateError(f"can only retry failed refunds, current status: {refund.status}")

    if refund.retry_count >= refund.max_retries:
        raise RefundStateError(
            f"max retries ({refund.max_retries}) exceeded; manual intervention required"
        )

    return await execute_refund(session, workspace_id=workspace_id, refund_id=refund_id, trace_id=trace_id)


# --------------------------------------------------------------------------- #
# Queries
# --------------------------------------------------------------------------- #


async def get_refund(
    session: AsyncSession, *, workspace_id: UUID, refund_id: UUID
) -> RefundCase:
    return await _load_refund(session, workspace_id=workspace_id, refund_id=refund_id)


async def list_refunds(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    order_id: UUID | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[RefundCase]:
    query = select(RefundCase).where(RefundCase.workspace_id == workspace_id)
    if order_id:
        query = query.where(RefundCase.order_id == order_id)
    if status:
        query = query.where(RefundCase.status == status)
    query = query.order_by(RefundCase.created_at.desc()).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_order_refund_summary(
    session: AsyncSession, *, workspace_id: UUID, order_id: UUID
) -> dict[str, Any]:
    """Get refund summary for an order: total refunded, active, refundable balance."""
    order = await _load_order(session, workspace_id=workspace_id, order_id=order_id)
    balance = await _get_refundable_balance(session, order=order)

    refunds = await list_refunds(session, workspace_id=workspace_id, order_id=order_id, limit=100)
    total_refunded = sum(
        (r.executed_amount or ZERO) for r in refunds if r.status == "succeeded"
    )
    active_count = sum(1 for r in refunds if r.status in ACTIVE_REFUND_STATUSES)

    return {
        "order_id": str(order_id),
        "order_total": str(order.total),
        "refunded_amount": str(order.refunded_amount),
        "total_refunded_via_cases": str(total_refunded),
        "active_refund_count": active_count,
        "refundable_balance": str(balance),
        "currency": order.currency,
    }
