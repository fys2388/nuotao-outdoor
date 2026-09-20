"""B2B invoicing, receivables, receipt allocation, and collections."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.b2b import B2BAgent, B2BOrder
from app.models.b2b_finance import (
    B2BInvoice,
    B2BReceipt,
    B2BReceivableEntry,
)
from app.services import consolidation_service, event_service

MONEY = Decimal("0.01")
ZERO = Decimal("0.00")
logger = logging.getLogger(__name__)
CLOSED_INVOICE_STATUSES = {"paid", "written_off", "void"}
ALLOCATABLE_INVOICE_STATUSES = {"issued", "partially_paid", "overdue"}


class B2BFinanceError(ValueError):
    """Base class for B2B finance domain errors."""


class B2BFinanceNotFoundError(B2BFinanceError):
    """Raised when an order, invoice, receipt, or agent cannot be found."""


class B2BFinanceStateError(B2BFinanceError):
    """Raised when a finance operation is invalid for the current state."""


class B2BFinanceConflictError(B2BFinanceError):
    """Raised when a unique business key conflicts with existing data."""


def _uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _money(value: Decimal | str | int | float) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def _number(prefix: str) -> str:
    now = datetime.now(timezone.utc)
    return f"{prefix}-{now.strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"


def effective_invoice_status(invoice: B2BInvoice, *, as_of: date | None = None) -> str:
    """Return the operational status, including overdue as a derived state."""
    effective_date = as_of or date.today()
    if (
        invoice.balance_due > ZERO
        and invoice.due_date < effective_date
        and invoice.status in {"issued", "partially_paid"}
    ):
        return "overdue"
    return invoice.status


def receivable_age_days(invoice: B2BInvoice, *, as_of: date | None = None) -> int:
    effective_date = as_of or date.today()
    if invoice.balance_due <= ZERO or invoice.due_date >= effective_date:
        return 0
    return (effective_date - invoice.due_date).days


def receivable_aging_bucket(
    invoice: B2BInvoice,
    *,
    as_of: date | None = None,
) -> str:
    days = receivable_age_days(invoice, as_of=as_of)
    if days <= 0:
        return "current"
    if days <= 30:
        return "0-30"
    if days <= 60:
        return "31-60"
    if days <= 90:
        return "61-90"
    return "90+"


async def _get_agent(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    agent_id: str | UUID,
) -> B2BAgent:
    agent = (
        await db.execute(
            select(B2BAgent).where(
                B2BAgent.workspace_id == workspace_id,
                B2BAgent.id == _uuid(agent_id),
            )
        )
    ).scalar_one_or_none()
    if agent is None:
        raise B2BFinanceNotFoundError("agent not found")
    return agent


async def _get_order(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    order_id: str | UUID,
) -> B2BOrder:
    order = (
        await db.execute(
            select(B2BOrder)
            .where(
                B2BOrder.workspace_id == workspace_id,
                B2BOrder.id == _uuid(order_id),
            )
            .options(selectinload(B2BOrder.items))
        )
    ).scalar_one_or_none()
    if order is None:
        raise B2BFinanceNotFoundError("B2B order not found")
    return order


async def create_invoice_from_order(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    order_id: str | UUID,
    created_by: str,
    issue_date: date | None = None,
    due_date: date | None = None,
    notes: str | None = None,
) -> B2BInvoice:
    """Create one invoice for a B2B order; repeated calls return the invoice."""
    order = await _get_order(db, workspace_id=workspace_id, order_id=order_id)
    existing = (
        await db.execute(
            select(B2BInvoice)
            .where(
                B2BInvoice.workspace_id == workspace_id,
                B2BInvoice.order_id == order.id,
            )
            .options(selectinload(B2BInvoice.entries))
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if existing is not None:
        try:
            await consolidation_service.ensure_attribution(
                db,
                workspace_id=workspace_id,
                entity_type="b2b_invoice",
                entity_id=existing.id,
                actor="system:b2b-invoice-creation",
            )
        except Exception:
            logger.warning(
                "automatic consolidation attribution failed for B2B invoice %s",
                existing.id,
                exc_info=True,
            )
        return existing
    if order.status == "cancelled":
        raise B2BFinanceStateError("cancelled order cannot be invoiced")

    resolved_issue_date = issue_date or date.today()
    resolved_due_date = due_date or order.payment_due_date or resolved_issue_date
    if resolved_due_date < resolved_issue_date:
        raise B2BFinanceError("due_date cannot be before issue_date")
    total = _money(order.total)
    if total <= ZERO:
        raise B2BFinanceError("invoice total must be positive")
    subtotal = _money(order.subtotal)
    discount_amount = _money(order.discount_amount)
    shipping_amount = _money(order.shipping_cost)
    tax_amount = _money(total - subtotal + discount_amount - shipping_amount)
    if tax_amount < ZERO:
        tax_amount = ZERO

    invoice = B2BInvoice(
        workspace_id=workspace_id,
        invoice_number=_number("INV"),
        order_id=order.id,
        agent_id=order.agent_id,
        customer_account_id=order.customer_account_id,
        status="draft",
        currency=order.currency,
        issue_date=resolved_issue_date,
        due_date=resolved_due_date,
        subtotal=subtotal,
        discount_amount=discount_amount,
        shipping_amount=shipping_amount,
        tax_amount=tax_amount,
        total=total,
        amount_paid=ZERO,
        amount_written_off=ZERO,
        balance_due=total,
        items_snapshot=[
            {
                "order_item_id": str(item.id),
                "product_id": str(item.product_id),
                "sku": item.sku,
                "product_name": item.product_name,
                "quantity": item.quantity,
                "unit_price": str(item.unit_price),
                "line_total": str(item.subtotal),
                "currency": item.currency,
            }
            for item in order.items
        ],
        notes=notes,
        created_by=created_by,
    )
    db.add(invoice)
    await db.flush()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_invoice.created",
        entity_type="b2b_invoice",
        entity_id=str(invoice.id),
        payload={
            "invoice_number": invoice.invoice_number,
            "order_id": str(order.id),
            "order_number": order.order_number,
            "total": str(invoice.total),
            "currency": invoice.currency,
            "actor": created_by,
        },
    )
    try:
        await consolidation_service.ensure_attribution(
            db,
            workspace_id=workspace_id,
            entity_type="b2b_invoice",
            entity_id=invoice.id,
            actor="system:b2b-invoice-creation",
        )
    except Exception:
        logger.warning(
            "automatic consolidation attribution failed for B2B invoice %s",
            invoice.id,
            exc_info=True,
        )
    return await get_invoice(
        db,
        workspace_id=workspace_id,
        invoice_id=invoice.id,
    )  # type: ignore[return-value]


async def get_invoice(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    invoice_id: str | UUID,
) -> B2BInvoice | None:
    return (
        await db.execute(
            select(B2BInvoice)
            .where(
                B2BInvoice.workspace_id == workspace_id,
                B2BInvoice.id == _uuid(invoice_id),
            )
            .options(selectinload(B2BInvoice.entries))
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()


async def list_invoices(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    page: int = 1,
    page_size: int = 50,
    status: str | None = None,
    agent_id: str | UUID | None = None,
) -> tuple[list[B2BInvoice], int]:
    query = select(B2BInvoice).where(B2BInvoice.workspace_id == workspace_id)
    count_query = select(func.count(B2BInvoice.id)).where(
        B2BInvoice.workspace_id == workspace_id
    )
    if status:
        if status == "overdue":
            effective_filter = (
                B2BInvoice.due_date < date.today(),
                B2BInvoice.balance_due > ZERO,
                B2BInvoice.status.in_(["issued", "partially_paid"]),
            )
            query = query.where(*effective_filter)
            count_query = count_query.where(*effective_filter)
        elif status in {"issued", "partially_paid"}:
            effective_filter = (
                B2BInvoice.status == status,
                B2BInvoice.due_date >= date.today(),
            )
            query = query.where(*effective_filter)
            count_query = count_query.where(*effective_filter)
        else:
            query = query.where(B2BInvoice.status == status)
            count_query = count_query.where(B2BInvoice.status == status)
    if agent_id:
        agent_uuid = _uuid(agent_id)
        query = query.where(B2BInvoice.agent_id == agent_uuid)
        count_query = count_query.where(B2BInvoice.agent_id == agent_uuid)

    total = (await db.execute(count_query)).scalar_one()
    rows = (
        await db.execute(
            query.options(selectinload(B2BInvoice.entries))
            .order_by(B2BInvoice.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return list(rows), int(total)


async def issue_invoice(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    invoice_id: str | UUID,
    actor: str,
    trace_id: str | None = None,
) -> B2BInvoice:
    """Issue a draft invoice and append its charge once."""
    invoice = (
        await db.execute(
            select(B2BInvoice)
            .where(
                B2BInvoice.workspace_id == workspace_id,
                B2BInvoice.id == _uuid(invoice_id),
            )
            .options(selectinload(B2BInvoice.entries))
            .execution_options(populate_existing=True)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if invoice is None:
        raise B2BFinanceNotFoundError("invoice not found")
    if invoice.status != "draft":
        if invoice.status in {"issued", "partially_paid", "paid", "overdue"}:
            return invoice
        raise B2BFinanceStateError("only draft invoices can be issued")

    now = datetime.now(timezone.utc)
    charge_key = f"invoice-charge:{invoice.id}"
    existing_entry = next(
        (entry for entry in invoice.entries if entry.entry_key == charge_key),
        None,
    )
    if existing_entry is None:
        db.add(
            B2BReceivableEntry(
                workspace_id=workspace_id,
                agent_id=invoice.agent_id,
                invoice_id=invoice.id,
                entry_type="charge",
                amount=invoice.total,
                currency=invoice.currency,
                occurred_at=now,
                entry_key=charge_key,
                description=f"invoice {invoice.invoice_number} issued",
                created_by=actor,
            )
        )
    invoice.status = "issued"
    invoice.issued_at = now
    if invoice.due_date < date.today():
        invoice.status = "overdue"
    await db.flush()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_invoice.issued",
        entity_type="b2b_invoice",
        entity_id=str(invoice.id),
        payload={
            "invoice_number": invoice.invoice_number,
            "order_id": str(invoice.order_id),
            "total": str(invoice.total),
            "currency": invoice.currency,
            "actor": actor,
        },
        trace_id=trace_id,
    )
    return await get_invoice(
        db,
        workspace_id=workspace_id,
        invoice_id=invoice.id,
    )  # type: ignore[return-value]


async def create_receipt(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    agent_id: str | UUID,
    amount: Decimal,
    currency: str,
    idempotency_key: str,
    created_by: str,
    received_at: datetime | None = None,
    payment_method: str = "bank_transfer",
    bank_reference: str | None = None,
    notes: str | None = None,
    trace_id: str | None = None,
) -> B2BReceipt:
    """Register cash receipt. The idempotency key is unique per workspace."""
    normalized_key = idempotency_key.strip()
    if not normalized_key:
        raise B2BFinanceError("idempotency_key is required")
    normalized_amount = _money(amount)
    if normalized_amount <= ZERO:
        raise B2BFinanceError("receipt amount must be positive")
    normalized_currency = currency.strip().upper()
    agent = await _get_agent(db, workspace_id=workspace_id, agent_id=agent_id)
    existing = (
        await db.execute(
            select(B2BReceipt)
            .where(
                B2BReceipt.workspace_id == workspace_id,
                B2BReceipt.idempotency_key == normalized_key,
            )
            .options(selectinload(B2BReceipt.entries))
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if existing is not None:
        if (
            existing.agent_id != agent.id
            or _money(existing.amount) != normalized_amount
            or existing.currency != normalized_currency
        ):
            raise B2BFinanceConflictError(
                "idempotency key already belongs to a different receipt"
            )
        return existing

    receipt = B2BReceipt(
        workspace_id=workspace_id,
        receipt_number=_number("RCT"),
        agent_id=agent.id,
        customer_account_id=agent.customer_account_id,
        status="unapplied",
        amount=normalized_amount,
        unapplied_amount=normalized_amount,
        currency=normalized_currency,
        received_at=received_at or datetime.now(timezone.utc),
        payment_method=payment_method,
        bank_reference=bank_reference,
        idempotency_key=normalized_key,
        notes=notes,
        created_by=created_by,
    )
    db.add(receipt)
    await db.flush()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_receipt.created",
        entity_type="b2b_receipt",
        entity_id=str(receipt.id),
        payload={
            "receipt_number": receipt.receipt_number,
            "agent_id": str(receipt.agent_id),
            "amount": str(receipt.amount),
            "currency": receipt.currency,
            "actor": created_by,
        },
        trace_id=trace_id,
    )
    return await get_receipt(
        db,
        workspace_id=workspace_id,
        receipt_id=receipt.id,
    )  # type: ignore[return-value]


async def get_receipt(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    receipt_id: str | UUID,
) -> B2BReceipt | None:
    return (
        await db.execute(
            select(B2BReceipt)
            .where(
                B2BReceipt.workspace_id == workspace_id,
                B2BReceipt.id == _uuid(receipt_id),
            )
            .options(selectinload(B2BReceipt.entries))
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()


async def list_receipts(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    page: int = 1,
    page_size: int = 50,
    status: str | None = None,
    agent_id: str | UUID | None = None,
) -> tuple[list[B2BReceipt], int]:
    query = select(B2BReceipt).where(B2BReceipt.workspace_id == workspace_id)
    count_query = select(func.count(B2BReceipt.id)).where(
        B2BReceipt.workspace_id == workspace_id
    )
    if status:
        query = query.where(B2BReceipt.status == status)
        count_query = count_query.where(B2BReceipt.status == status)
    if agent_id:
        agent_uuid = _uuid(agent_id)
        query = query.where(B2BReceipt.agent_id == agent_uuid)
        count_query = count_query.where(B2BReceipt.agent_id == agent_uuid)
    total = (await db.execute(count_query)).scalar_one()
    rows = (
        await db.execute(
            query.options(selectinload(B2BReceipt.entries))
            .order_by(B2BReceipt.received_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return list(rows), int(total)


async def allocate_receipt(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    receipt_id: str | UUID,
    invoice_id: str | UUID,
    amount: Decimal,
    actor: str,
    idempotency_key: str | None = None,
    notes: str | None = None,
    trace_id: str | None = None,
) -> tuple[B2BReceipt, B2BInvoice]:
    """Apply a receipt to an invoice and update all derived balances."""
    allocation_amount = _money(amount)
    if allocation_amount <= ZERO:
        raise B2BFinanceError("allocation amount must be positive")
    receipt = (
        await db.execute(
            select(B2BReceipt)
            .where(
                B2BReceipt.workspace_id == workspace_id,
                B2BReceipt.id == _uuid(receipt_id),
            )
            .options(selectinload(B2BReceipt.entries))
            .execution_options(populate_existing=True)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if receipt is None:
        raise B2BFinanceNotFoundError("receipt not found")
    invoice = (
        await db.execute(
            select(B2BInvoice)
            .where(
                B2BInvoice.workspace_id == workspace_id,
                B2BInvoice.id == _uuid(invoice_id),
            )
            .options(selectinload(B2BInvoice.entries))
            .execution_options(populate_existing=True)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if invoice is None:
        raise B2BFinanceNotFoundError("invoice not found")
    if receipt.agent_id != invoice.agent_id:
        raise B2BFinanceStateError("receipt and invoice must belong to the same customer")
    if receipt.currency != invoice.currency:
        raise B2BFinanceStateError("receipt and invoice currencies must match")
    if invoice.status == "draft":
        raise B2BFinanceStateError("draft invoice cannot receive payment")
    if invoice.status in {"void", "written_off"}:
        raise B2BFinanceStateError("closed invoice cannot receive payment")
    if _money(receipt.unapplied_amount) < allocation_amount:
        raise B2BFinanceStateError("allocation exceeds receipt unapplied amount")
    if _money(invoice.balance_due) < allocation_amount:
        raise B2BFinanceStateError("allocation exceeds invoice balance due")

    key_suffix = (idempotency_key or "default").strip() or "default"
    entry_key = f"payment:{receipt.id}:{invoice.id}:{key_suffix}"
    existing_entry = next(
        (entry for entry in invoice.entries if entry.entry_key == entry_key),
        None,
    )
    if existing_entry is not None:
        return (
            await get_receipt(
                db,
                workspace_id=workspace_id,
                receipt_id=receipt.id,
            ),  # type: ignore[return-value]
            await get_invoice(
                db,
                workspace_id=workspace_id,
                invoice_id=invoice.id,
            ),  # type: ignore[return-value]
        )

    now = datetime.now(timezone.utc)
    receipt.unapplied_amount = _money(
        _money(receipt.unapplied_amount) - allocation_amount
    )
    if receipt.unapplied_amount == ZERO:
        receipt.status = "applied"
    elif receipt.unapplied_amount < _money(receipt.amount):
        receipt.status = "partially_applied"

    invoice.amount_paid = _money(
        _money(invoice.amount_paid) + allocation_amount
    )
    invoice.balance_due = _money(
        _money(invoice.balance_due) - allocation_amount
    )
    if invoice.balance_due == ZERO:
        invoice.status = "paid"
    else:
        invoice.status = "partially_paid"

    order = (
        await db.execute(
            select(B2BOrder).where(
                B2BOrder.workspace_id == workspace_id,
                B2BOrder.id == invoice.order_id,
            )
        )
    ).scalar_one_or_none()
    if order is None:
        raise B2BFinanceStateError("invoice order no longer exists")
    order.payment_status = "paid" if invoice.balance_due == ZERO else "partial"

    agent = await _get_agent(
        db,
        workspace_id=workspace_id,
        agent_id=invoice.agent_id,
    )
    agent.current_balance = _money(
        _money(agent.current_balance) - allocation_amount
    )
    db.add(
        B2BReceivableEntry(
            workspace_id=workspace_id,
            agent_id=invoice.agent_id,
            invoice_id=invoice.id,
            receipt_id=receipt.id,
            entry_type="payment",
            amount=-allocation_amount,
            currency=invoice.currency,
            occurred_at=now,
            entry_key=entry_key,
            description=notes
            or f"receipt {receipt.receipt_number} allocated to {invoice.invoice_number}",
            created_by=actor,
        )
    )
    await db.flush()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_receipt.allocated",
        entity_type="b2b_receipt",
        entity_id=str(receipt.id),
        payload={
            "receipt_number": receipt.receipt_number,
            "invoice_id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "amount": str(allocation_amount),
            "currency": invoice.currency,
            "invoice_status": invoice.status,
            "order_payment_status": order.payment_status,
            "actor": actor,
        },
        trace_id=trace_id,
    )
    return (
        await get_receipt(
            db,
            workspace_id=workspace_id,
            receipt_id=receipt.id,
        ),  # type: ignore[return-value]
        await get_invoice(
            db,
            workspace_id=workspace_id,
            invoice_id=invoice.id,
        ),  # type: ignore[return-value]
    )


async def write_off_invoice(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    invoice_id: str | UUID,
    actor: str,
    amount: Decimal | None = None,
    idempotency_key: str | None = None,
    reason: str | None = None,
    trace_id: str | None = None,
) -> tuple[B2BInvoice, B2BReceipt | None]:
    """Write off all or part of an open invoice balance."""
    invoice = (
        await db.execute(
            select(B2BInvoice)
            .where(
                B2BInvoice.workspace_id == workspace_id,
                B2BInvoice.id == _uuid(invoice_id),
            )
            .options(selectinload(B2BInvoice.entries))
            .execution_options(populate_existing=True)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if invoice is None:
        raise B2BFinanceNotFoundError("invoice not found")
    if invoice.status == "written_off" and invoice.balance_due == ZERO:
        return invoice, None
    if invoice.status in {"draft", "void", "paid"}:
        raise B2BFinanceStateError(
            "only open issued or overdue invoices can be written off"
        )
    write_off_amount = (
        _money(amount)
        if amount is not None
        else _money(invoice.balance_due)
    )
    if write_off_amount <= ZERO:
        raise B2BFinanceError("write-off amount must be positive")
    if write_off_amount > _money(invoice.balance_due):
        raise B2BFinanceStateError("write-off exceeds invoice balance due")

    key_suffix = (idempotency_key or "default").strip() or "default"
    entry_key = f"write-off:{invoice.id}:{key_suffix}"
    existing_entry = next(
        (entry for entry in invoice.entries if entry.entry_key == entry_key),
        None,
    )
    if existing_entry is not None:
        return (
            await get_invoice(
                db,
                workspace_id=workspace_id,
                invoice_id=invoice.id,
            ),  # type: ignore[return-value]
            None,
        )

    now = datetime.now(timezone.utc)
    invoice.amount_written_off = _money(
        _money(invoice.amount_written_off) + write_off_amount
    )
    invoice.balance_due = _money(
        _money(invoice.balance_due) - write_off_amount
    )
    if invoice.balance_due == ZERO:
        invoice.status = "written_off"
    elif invoice.amount_paid > ZERO or invoice.amount_written_off > ZERO:
        invoice.status = "partially_paid"

    order = (
        await db.execute(
            select(B2BOrder).where(
                B2BOrder.workspace_id == workspace_id,
                B2BOrder.id == invoice.order_id,
            )
        )
    ).scalar_one_or_none()
    if order is None:
        raise B2BFinanceStateError("invoice order no longer exists")
    if invoice.balance_due == ZERO and invoice.status == "written_off":
        order.payment_status = "written_off"
    else:
        order.payment_status = "partial"

    agent = await _get_agent(
        db,
        workspace_id=workspace_id,
        agent_id=invoice.agent_id,
    )
    agent.current_balance = _money(
        _money(agent.current_balance) - write_off_amount
    )
    db.add(
        B2BReceivableEntry(
            workspace_id=workspace_id,
            agent_id=invoice.agent_id,
            invoice_id=invoice.id,
            entry_type="write_off",
            amount=-write_off_amount,
            currency=invoice.currency,
            occurred_at=now,
            entry_key=entry_key,
            description=reason
            or f"write off {invoice.invoice_number}",
            created_by=actor,
        )
    )
    await db.flush()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_invoice.written_off",
        entity_type="b2b_invoice",
        entity_id=str(invoice.id),
        payload={
            "invoice_number": invoice.invoice_number,
            "amount": str(write_off_amount),
            "balance_due": str(invoice.balance_due),
            "status": invoice.status,
            "reason": reason,
            "actor": actor,
        },
        trace_id=trace_id,
    )
    return (
        await get_invoice(
            db,
            workspace_id=workspace_id,
            invoice_id=invoice.id,
        ),  # type: ignore[return-value]
        None,
    )


async def list_receivables(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    page: int = 1,
    page_size: int = 50,
    agent_id: str | UUID | None = None,
    overdue_only: bool = False,
) -> tuple[list[B2BInvoice], int]:
    query = select(B2BInvoice).where(
        B2BInvoice.workspace_id == workspace_id,
        B2BInvoice.balance_due > ZERO,
        B2BInvoice.status.in_(["issued", "partially_paid", "overdue"]),
    )
    count_query = select(func.count(B2BInvoice.id)).where(
        B2BInvoice.workspace_id == workspace_id,
        B2BInvoice.balance_due > ZERO,
        B2BInvoice.status.in_(["issued", "partially_paid", "overdue"]),
    )
    if overdue_only:
        query = query.where(B2BInvoice.due_date < date.today())
        count_query = count_query.where(B2BInvoice.due_date < date.today())
    if agent_id:
        agent_uuid = _uuid(agent_id)
        query = query.where(B2BInvoice.agent_id == agent_uuid)
        count_query = count_query.where(B2BInvoice.agent_id == agent_uuid)
    total = (await db.execute(count_query)).scalar_one()
    rows = (
        await db.execute(
            query.options(selectinload(B2BInvoice.entries))
            .order_by(B2BInvoice.due_date.asc(), B2BInvoice.created_at.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return list(rows), int(total)


async def receivable_stats(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    as_of: date | None = None,
) -> dict:
    effective_date = as_of or date.today()
    invoices = (
        await db.execute(
            select(B2BInvoice).where(B2BInvoice.workspace_id == workspace_id)
        )
    ).scalars().all()
    buckets = {
        "current": {"count": 0, "amount": ZERO},
        "0-30": {"count": 0, "amount": ZERO},
        "31-60": {"count": 0, "amount": ZERO},
        "61-90": {"count": 0, "amount": ZERO},
        "90+": {"count": 0, "amount": ZERO},
    }
    outstanding = ZERO
    overdue = ZERO
    paid = ZERO
    written_off = ZERO
    open_count = 0
    overdue_count = 0

    for invoice in invoices:
        paid += _money(invoice.amount_paid)
        written_off += _money(invoice.amount_written_off)
        balance = _money(invoice.balance_due)
        if balance <= ZERO:
            continue
        open_count += 1
        outstanding += balance
        bucket = receivable_aging_bucket(invoice, as_of=effective_date)
        buckets[bucket]["count"] += 1
        buckets[bucket]["amount"] += balance
        if invoice.due_date < effective_date:
            overdue += balance
            overdue_count += 1

    return {
        "as_of": effective_date,
        "invoice_count": len(invoices),
        "open_invoice_count": open_count,
        "overdue_invoice_count": overdue_count,
        "outstanding_amount": _money(outstanding),
        "overdue_amount": _money(overdue),
        "paid_amount": _money(paid),
        "written_off_amount": _money(written_off),
        "aging": {
            key: {
                "count": value["count"],
                "amount": _money(value["amount"]),
            }
            for key, value in buckets.items()
        },
    }
