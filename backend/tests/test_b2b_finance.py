"""P1 regression tests for B2B invoicing and receivables."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.b2b import B2BAgent, B2BOrder
from app.services import b2b_finance_service

WORKSPACE = DEFAULT_WORKSPACE_ID


async def _create_agent(
    db_session,
    *,
    number: str = "AG-FIN",
    balance: Decimal = Decimal("0"),
) -> B2BAgent:
    agent = B2BAgent(
        workspace_id=WORKSPACE,
        agent_number=number,
        company_name=f"Company {number}",
        contact_name="Finance Buyer",
        email=f"{number.lower()}@example.com",
        hashed_password="not-used",
        tier="bronze",
        status="active",
        currency="USD",
        credit_limit=Decimal("100000"),
        current_balance=balance,
    )
    db_session.add(agent)
    await db_session.commit()
    return agent


async def _create_order(
    db_session,
    *,
    agent: B2BAgent,
    number: str = "B2B-FIN",
    total: Decimal = Decimal("100.00"),
    due_date: date | None = None,
) -> B2BOrder:
    order = B2BOrder(
        workspace_id=WORKSPACE,
        order_number=number,
        agent_id=agent.id,
        business_model="B2B",
        status="pending",
        payment_status="unpaid",
        subtotal=total,
        discount_amount=Decimal("0"),
        shipping_cost=Decimal("0"),
        total=total,
        currency=agent.currency,
        shipping_address={},
        payment_due_date=due_date or (date.today() + timedelta(days=30)),
    )
    db_session.add(order)
    await db_session.commit()
    return order


@pytest.mark.asyncio
async def test_invoice_is_unique_per_order_and_draft_cannot_be_allocated(
    db_session,
) -> None:
    agent = await _create_agent(db_session, balance=Decimal("100.00"))
    order = await _create_order(db_session, agent=agent)
    invoice = await b2b_finance_service.create_invoice_from_order(
        db_session,
        workspace_id=WORKSPACE,
        order_id=order.id,
        created_by="finance@example.com",
    )
    duplicate = await b2b_finance_service.create_invoice_from_order(
        db_session,
        workspace_id=WORKSPACE,
        order_id=order.id,
        created_by="finance@example.com",
    )
    assert duplicate.id == invoice.id

    receipt = await b2b_finance_service.create_receipt(
        db_session,
        workspace_id=WORKSPACE,
        agent_id=agent.id,
        amount=Decimal("20.00"),
        currency="USD",
        idempotency_key="draft-allocation",
        created_by="finance@example.com",
    )
    with pytest.raises(
        b2b_finance_service.B2BFinanceStateError,
        match="draft invoice",
    ):
        await b2b_finance_service.allocate_receipt(
            db_session,
            workspace_id=WORKSPACE,
            receipt_id=receipt.id,
            invoice_id=invoice.id,
            amount=Decimal("20.00"),
            actor="finance@example.com",
        )


@pytest.mark.asyncio
async def test_receipt_idempotency_partial_and_full_allocation(db_session) -> None:
    agent = await _create_agent(db_session, balance=Decimal("100.00"))
    order = await _create_order(db_session, agent=agent)
    invoice = await b2b_finance_service.create_invoice_from_order(
        db_session,
        workspace_id=WORKSPACE,
        order_id=order.id,
        created_by="finance@example.com",
    )
    invoice = await b2b_finance_service.issue_invoice(
        db_session,
        workspace_id=WORKSPACE,
        invoice_id=invoice.id,
        actor="finance@example.com",
    )
    receipt = await b2b_finance_service.create_receipt(
        db_session,
        workspace_id=WORKSPACE,
        agent_id=agent.id,
        amount=Decimal("100.00"),
        currency="USD",
        idempotency_key="bank-tx-001",
        created_by="finance@example.com",
    )
    duplicate_receipt = await b2b_finance_service.create_receipt(
        db_session,
        workspace_id=WORKSPACE,
        agent_id=agent.id,
        amount=Decimal("100.00"),
        currency="USD",
        idempotency_key="bank-tx-001",
        created_by="finance@example.com",
    )
    assert duplicate_receipt.id == receipt.id

    receipt, invoice = await b2b_finance_service.allocate_receipt(
        db_session,
        workspace_id=WORKSPACE,
        receipt_id=receipt.id,
        invoice_id=invoice.id,
        amount=Decimal("40.00"),
        actor="finance@example.com",
        idempotency_key="partial-1",
    )
    assert receipt.unapplied_amount == Decimal("60.00")
    assert receipt.status == "partially_applied"
    assert invoice.status == "partially_paid"
    assert invoice.amount_paid == Decimal("40.00")
    assert invoice.balance_due == Decimal("60.00")

    duplicate_receipt, duplicate_invoice = await b2b_finance_service.allocate_receipt(
        db_session,
        workspace_id=WORKSPACE,
        receipt_id=receipt.id,
        invoice_id=invoice.id,
        amount=Decimal("40.00"),
        actor="finance@example.com",
        idempotency_key="partial-1",
    )
    assert duplicate_receipt.unapplied_amount == Decimal("60.00")
    assert duplicate_invoice.amount_paid == Decimal("40.00")

    refreshed_order = await db_session.get(B2BOrder, order.id)
    refreshed_agent = await db_session.get(B2BAgent, agent.id)
    assert refreshed_order is not None
    assert refreshed_order.payment_status == "partial"
    assert refreshed_agent is not None
    assert refreshed_agent.current_balance == Decimal("60.00")

    receipt, invoice = await b2b_finance_service.allocate_receipt(
        db_session,
        workspace_id=WORKSPACE,
        receipt_id=receipt.id,
        invoice_id=invoice.id,
        amount=Decimal("60.00"),
        actor="finance@example.com",
        idempotency_key="partial-2",
    )
    assert receipt.status == "applied"
    assert receipt.unapplied_amount == Decimal("0.00")
    assert invoice.status == "paid"
    assert invoice.balance_due == Decimal("0.00")

    refreshed_order = await db_session.get(B2BOrder, order.id)
    refreshed_agent = await db_session.get(B2BAgent, agent.id)
    assert refreshed_order is not None
    assert refreshed_order.payment_status == "paid"
    assert refreshed_agent is not None
    assert refreshed_agent.current_balance == Decimal("0.00")
    assert len(invoice.entries) == 3


@pytest.mark.asyncio
async def test_allocation_rejects_overpayment_and_currency_mismatch(
    db_session,
) -> None:
    agent = await _create_agent(db_session, balance=Decimal("100.00"))
    order = await _create_order(db_session, agent=agent)
    invoice = await b2b_finance_service.create_invoice_from_order(
        db_session,
        workspace_id=WORKSPACE,
        order_id=order.id,
        created_by="finance@example.com",
    )
    invoice = await b2b_finance_service.issue_invoice(
        db_session,
        workspace_id=WORKSPACE,
        invoice_id=invoice.id,
        actor="finance@example.com",
    )
    usd_receipt = await b2b_finance_service.create_receipt(
        db_session,
        workspace_id=WORKSPACE,
        agent_id=agent.id,
        amount=Decimal("150.00"),
        currency="USD",
        idempotency_key="overpay",
        created_by="finance@example.com",
    )
    with pytest.raises(
        b2b_finance_service.B2BFinanceStateError,
        match="invoice balance due",
    ):
        await b2b_finance_service.allocate_receipt(
            db_session,
            workspace_id=WORKSPACE,
            receipt_id=usd_receipt.id,
            invoice_id=invoice.id,
            amount=Decimal("150.00"),
            actor="finance@example.com",
        )

    eur_receipt = await b2b_finance_service.create_receipt(
        db_session,
        workspace_id=WORKSPACE,
        agent_id=agent.id,
        amount=Decimal("50.00"),
        currency="EUR",
        idempotency_key="currency-mismatch",
        created_by="finance@example.com",
    )
    with pytest.raises(
        b2b_finance_service.B2BFinanceStateError,
        match="currencies",
    ):
        await b2b_finance_service.allocate_receipt(
            db_session,
            workspace_id=WORKSPACE,
            receipt_id=eur_receipt.id,
            invoice_id=invoice.id,
            amount=Decimal("50.00"),
            actor="finance@example.com",
        )


@pytest.mark.asyncio
async def test_write_off_updates_invoice_order_and_agent_balance(db_session) -> None:
    agent = await _create_agent(db_session, balance=Decimal("100.00"))
    order = await _create_order(db_session, agent=agent)
    invoice = await b2b_finance_service.create_invoice_from_order(
        db_session,
        workspace_id=WORKSPACE,
        order_id=order.id,
        created_by="finance@example.com",
    )
    invoice = await b2b_finance_service.issue_invoice(
        db_session,
        workspace_id=WORKSPACE,
        invoice_id=invoice.id,
        actor="finance@example.com",
    )
    receipt = await b2b_finance_service.create_receipt(
        db_session,
        workspace_id=WORKSPACE,
        agent_id=agent.id,
        amount=Decimal("20.00"),
        currency="USD",
        idempotency_key="writeoff-payment",
        created_by="finance@example.com",
    )
    await b2b_finance_service.allocate_receipt(
        db_session,
        workspace_id=WORKSPACE,
        receipt_id=receipt.id,
        invoice_id=invoice.id,
        amount=Decimal("20.00"),
        actor="finance@example.com",
    )
    invoice, _ = await b2b_finance_service.write_off_invoice(
        db_session,
        workspace_id=WORKSPACE,
        invoice_id=invoice.id,
        actor="controller@example.com",
        reason="customer insolvency",
    )
    assert invoice.status == "written_off"
    assert invoice.amount_paid == Decimal("20.00")
    assert invoice.amount_written_off == Decimal("80.00")
    assert invoice.balance_due == Decimal("0.00")

    repeated, _ = await b2b_finance_service.write_off_invoice(
        db_session,
        workspace_id=WORKSPACE,
        invoice_id=invoice.id,
        actor="controller@example.com",
    )
    assert repeated.amount_written_off == Decimal("80.00")
    refreshed_order = await db_session.get(B2BOrder, order.id)
    refreshed_agent = await db_session.get(B2BAgent, agent.id)
    assert refreshed_order is not None
    assert refreshed_order.payment_status == "written_off"
    assert refreshed_agent is not None
    assert refreshed_agent.current_balance == Decimal("0.00")


@pytest.mark.asyncio
async def test_overdue_status_and_aging_stats(db_session) -> None:
    agent = await _create_agent(db_session, balance=Decimal("100.00"))
    order = await _create_order(
        db_session,
        agent=agent,
        due_date=date.today() - timedelta(days=40),
    )
    invoice = await b2b_finance_service.create_invoice_from_order(
        db_session,
        workspace_id=WORKSPACE,
        order_id=order.id,
        created_by="finance@example.com",
        issue_date=date.today() - timedelta(days=60),
        due_date=date.today() - timedelta(days=40),
    )
    invoice = await b2b_finance_service.issue_invoice(
        db_session,
        workspace_id=WORKSPACE,
        invoice_id=invoice.id,
        actor="finance@example.com",
    )
    assert invoice.status == "overdue"
    assert b2b_finance_service.effective_invoice_status(invoice) == "overdue"
    assert b2b_finance_service.receivable_age_days(invoice) == 40

    stats = await b2b_finance_service.receivable_stats(
        db_session,
        workspace_id=WORKSPACE,
    )
    assert stats["outstanding_amount"] == Decimal("100.00")
    assert stats["overdue_amount"] == Decimal("100.00")
    assert stats["overdue_invoice_count"] == 1
    assert stats["aging"]["31-60"]["count"] == 1
    assert stats["aging"]["31-60"]["amount"] == Decimal("100.00")


@pytest.mark.asyncio
async def test_finance_records_are_workspace_scoped(db_session) -> None:
    agent = await _create_agent(db_session, balance=Decimal("100.00"))
    order = await _create_order(db_session, agent=agent)
    invoice = await b2b_finance_service.create_invoice_from_order(
        db_session,
        workspace_id=WORKSPACE,
        order_id=order.id,
        created_by="finance@example.com",
    )
    receipt = await b2b_finance_service.create_receipt(
        db_session,
        workspace_id=WORKSPACE,
        agent_id=agent.id,
        amount=Decimal("20.00"),
        currency="USD",
        idempotency_key="workspace-scope",
        created_by="finance@example.com",
    )
    other_workspace = uuid4()
    assert (
        await b2b_finance_service.get_invoice(
            db_session,
            workspace_id=other_workspace,
            invoice_id=invoice.id,
        )
        is None
    )
    assert (
        await b2b_finance_service.get_receipt(
            db_session,
            workspace_id=other_workspace,
            receipt_id=receipt.id,
        )
        is None
    )
