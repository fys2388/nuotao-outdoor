"""P2 regression tests for agent agreements and rebate accruals."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.b2b import B2BAgent, B2BOrder
from app.models.b2b_finance import B2BInvoice, B2BReceivableEntry
from app.schemas.b2b_agreements import B2BRebateProgressResponse
from app.services import (
    b2b_agreement_service,
    currency_service,
)

WORKSPACE = DEFAULT_WORKSPACE_ID


async def _create_agent(
    db_session,
    *,
    suffix: str,
    workspace_id=WORKSPACE,
) -> B2BAgent:
    agent = B2BAgent(
        workspace_id=workspace_id,
        agent_number=f"AG-{suffix}",
        company_name=f"Company {suffix}",
        contact_name="Agreement Buyer",
        email=f"{suffix.lower()}@example.com",
        hashed_password="not-used",
        tier="gold",
        status="active",
        currency="USD",
        credit_limit=Decimal("100000"),
    )
    db_session.add(agent)
    await db_session.commit()
    return agent


async def _create_agreement(
    db_session,
    *,
    agent: B2BAgent,
    suffix: str,
    basis: str,
    target: Decimal = Decimal("300.00"),
    workspace_id=WORKSPACE,
):
    agreement = await b2b_agreement_service.create_agreement(
        db_session,
        workspace_id=workspace_id,
        agent_id=agent.id,
        name=f"Annual agreement {suffix}",
        currency="USD",
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
        target_amount=target,
        qualification_basis=basis,
        calculation_method="retroactive",
        created_by="operator@example.com",
    )
    await b2b_agreement_service.create_rebate_tier(
        db_session,
        workspace_id=workspace_id,
        agreement_id=agreement.id,
        min_sales_amount=Decimal("0"),
        max_sales_amount=Decimal("100"),
        rebate_percent=Decimal("1"),
    )
    await b2b_agreement_service.create_rebate_tier(
        db_session,
        workspace_id=workspace_id,
        agreement_id=agreement.id,
        min_sales_amount=Decimal("100"),
        max_sales_amount=None,
        rebate_percent=Decimal("3"),
    )
    return await b2b_agreement_service._require_agreement(
        db_session,
        workspace_id=workspace_id,
        agreement_id=agreement.id,
    )


async def _create_order_and_invoice(
    db_session,
    *,
    agent: B2BAgent,
    suffix: str,
    amount: Decimal,
    issue_date: date,
    status: str = "issued",
    workspace_id=WORKSPACE,
) -> tuple[B2BOrder, B2BInvoice]:
    order = B2BOrder(
        workspace_id=workspace_id,
        order_number=f"B2B-{suffix}",
        agent_id=agent.id,
        business_model="B2B",
        status="delivered",
        payment_status="unpaid",
        subtotal=amount,
        discount_amount=Decimal("0"),
        shipping_cost=Decimal("0"),
        total=amount,
        currency="USD",
        shipping_address={},
        payment_due_date=issue_date + timedelta(days=30),
    )
    db_session.add(order)
    await db_session.flush()
    invoice = B2BInvoice(
        workspace_id=workspace_id,
        invoice_number=f"INV-{suffix}",
        order_id=order.id,
        agent_id=agent.id,
        status=status,
        currency="USD",
        issue_date=issue_date,
        due_date=issue_date + timedelta(days=30),
        subtotal=amount,
        discount_amount=Decimal("0"),
        shipping_amount=Decimal("0"),
        tax_amount=Decimal("0"),
        total=amount,
        amount_paid=Decimal("0"),
        amount_written_off=Decimal("0"),
        balance_due=amount,
        items_snapshot=[],
        created_by="finance@example.com",
    )
    db_session.add(invoice)
    await db_session.commit()
    return order, invoice


@pytest.mark.asyncio
async def test_agreement_requires_contiguous_tiers_and_separate_approver(
    db_session,
) -> None:
    agent = await _create_agent(db_session, suffix="AGR-APPROVAL")
    agreement = await _create_agreement(
        db_session,
        agent=agent,
        suffix="APPROVAL",
        basis="invoiced",
    )

    submitted = await b2b_agreement_service.submit_agreement(
        db_session,
        workspace_id=WORKSPACE,
        agreement_id=agreement.id,
        actor="operator@example.com",
    )
    assert submitted.status == "pending_approval"

    with pytest.raises(
        b2b_agreement_service.B2BAgreementStateError,
        match="submitter cannot approve",
    ):
        await b2b_agreement_service.approve_agreement(
            db_session,
            workspace_id=WORKSPACE,
            agreement_id=agreement.id,
            actor="operator@example.com",
        )

    approved = await b2b_agreement_service.approve_agreement(
        db_session,
        workspace_id=WORKSPACE,
        agreement_id=agreement.id,
        actor="admin@example.com",
    )
    assert approved.status == "active"
    assert approved.approved_by == "admin@example.com"

    replacement = await _create_agreement(
        db_session,
        agent=agent,
        suffix="REPLACEMENT",
        basis="invoiced",
    )
    await b2b_agreement_service.submit_agreement(
        db_session,
        workspace_id=WORKSPACE,
        agreement_id=replacement.id,
        actor="operator@example.com",
    )
    replacement = await b2b_agreement_service.approve_agreement(
        db_session,
        workspace_id=WORKSPACE,
        agreement_id=replacement.id,
        actor="admin@example.com",
    )
    previous = await b2b_agreement_service.get_agreement(
        db_session,
        workspace_id=WORKSPACE,
        agreement_id=agreement.id,
    )
    assert replacement.status == "active"
    assert previous is not None
    assert previous.status == "expired"


@pytest.mark.asyncio
async def test_non_overlapping_active_agreements_are_allowed(
    db_session,
) -> None:
    agent = await _create_agent(db_session, suffix="AGR-NON-OVERLAP")
    first = await _create_agreement(
        db_session,
        agent=agent,
        suffix="NON-OVERLAP-1",
        basis="invoiced",
    )
    await b2b_agreement_service.submit_agreement(
        db_session,
        workspace_id=WORKSPACE,
        agreement_id=first.id,
        actor="operator@example.com",
    )
    first = await b2b_agreement_service.approve_agreement(
        db_session,
        workspace_id=WORKSPACE,
        agreement_id=first.id,
        actor="admin@example.com",
    )

    future = await b2b_agreement_service.create_agreement(
        db_session,
        workspace_id=WORKSPACE,
        agent_id=agent.id,
        name="Future annual agreement",
        currency="USD",
        effective_from=date(2027, 1, 1),
        effective_to=date(2027, 12, 31),
        target_amount=Decimal("300.00"),
        qualification_basis="invoiced",
        calculation_method="retroactive",
        created_by="operator@example.com",
    )
    await b2b_agreement_service.create_rebate_tier(
        db_session,
        workspace_id=WORKSPACE,
        agreement_id=future.id,
        min_sales_amount=Decimal("0"),
        max_sales_amount=None,
        rebate_percent=Decimal("2"),
    )
    await b2b_agreement_service.submit_agreement(
        db_session,
        workspace_id=WORKSPACE,
        agreement_id=future.id,
        actor="operator@example.com",
    )
    future = await b2b_agreement_service.approve_agreement(
        db_session,
        workspace_id=WORKSPACE,
        agreement_id=future.id,
        actor="admin@example.com",
    )

    refreshed_first = await b2b_agreement_service.get_agreement(
        db_session,
        workspace_id=WORKSPACE,
        agreement_id=first.id,
    )
    assert future.status == "active"
    assert refreshed_first is not None
    assert refreshed_first.status == "active"


@pytest.mark.asyncio
async def test_rebate_tier_can_be_changed_to_open_ended(db_session) -> None:
    agent = await _create_agent(db_session, suffix="AGR-OPEN-TIER")
    agreement = await b2b_agreement_service.create_agreement(
        db_session,
        workspace_id=WORKSPACE,
        agent_id=agent.id,
        name="Open tier agreement",
        currency="USD",
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
        target_amount=Decimal("300.00"),
        qualification_basis="invoiced",
        calculation_method="retroactive",
        created_by="operator@example.com",
    )
    await b2b_agreement_service.create_rebate_tier(
        db_session,
        workspace_id=WORKSPACE,
        agreement_id=agreement.id,
        min_sales_amount=Decimal("0"),
        max_sales_amount=Decimal("100"),
        rebate_percent=Decimal("1"),
    )
    second = await b2b_agreement_service.create_rebate_tier(
        db_session,
        workspace_id=WORKSPACE,
        agreement_id=agreement.id,
        min_sales_amount=Decimal("100"),
        max_sales_amount=Decimal("200"),
        rebate_percent=Decimal("2"),
    )
    updated = await b2b_agreement_service.update_rebate_tier(
        db_session,
        workspace_id=WORKSPACE,
        agreement_id=agreement.id,
        tier_id=second.id,
        max_sales_amount=None,
        max_sales_amount_set=True,
    )
    assert updated.max_sales_amount is None

    submitted = await b2b_agreement_service.submit_agreement(
        db_session,
        workspace_id=WORKSPACE,
        agreement_id=agreement.id,
        actor="operator@example.com",
    )
    assert submitted.status == "pending_approval"


@pytest.mark.asyncio
async def test_progress_uses_ordered_invoiced_and_paid_facts(
    db_session,
) -> None:
    agent = await _create_agent(db_session, suffix="AGR-BASIS")
    ordered_agreement = await _create_agreement(
        db_session,
        agent=agent,
        suffix="ORDERED",
        basis="ordered",
    )
    invoiced_agreement = await _create_agreement(
        db_session,
        agent=agent,
        suffix="INVOICED",
        basis="invoiced",
    )
    paid_agreement = await _create_agreement(
        db_session,
        agent=agent,
        suffix="PAID",
        basis="paid",
    )
    occurred_on = datetime(2026, 6, 15, 10, 0, tzinfo=UTC)
    order = B2BOrder(
        workspace_id=WORKSPACE,
        order_number="B2B-BASIS",
        agent_id=agent.id,
        business_model="B2B",
        status="delivered",
        payment_status="partial",
        subtotal=Decimal("100.00"),
        discount_amount=Decimal("0"),
        shipping_cost=Decimal("0"),
        total=Decimal("100.00"),
        currency="USD",
        shipping_address={},
        payment_due_date=date(2026, 7, 15),
        created_at=occurred_on,
    )
    db_session.add(order)
    await db_session.flush()
    invoice = B2BInvoice(
        workspace_id=WORKSPACE,
        invoice_number="INV-BASIS",
        order_id=order.id,
        agent_id=agent.id,
        status="partially_paid",
        currency="USD",
        issue_date=date(2026, 6, 15),
        due_date=date(2026, 7, 15),
        subtotal=Decimal("150.00"),
        discount_amount=Decimal("0"),
        shipping_amount=Decimal("0"),
        tax_amount=Decimal("0"),
        total=Decimal("150.00"),
        amount_paid=Decimal("40.00"),
        amount_written_off=Decimal("0"),
        balance_due=Decimal("110.00"),
        items_snapshot=[],
        created_by="finance@example.com",
    )
    db_session.add(invoice)
    await db_session.flush()
    db_session.add(
        B2BReceivableEntry(
            workspace_id=WORKSPACE,
            agent_id=agent.id,
            invoice_id=invoice.id,
            entry_type="payment",
            amount=Decimal("-40.00"),
            currency="USD",
            occurred_at=occurred_on,
            entry_key="basis-payment",
            created_by="finance@example.com",
        )
    )
    await db_session.commit()

    ordered = await b2b_agreement_service.agreement_progress(
        db_session,
        workspace_id=WORKSPACE,
        agreement_id=ordered_agreement.id,
        as_of=date(2026, 12, 31),
    )
    invoiced = await b2b_agreement_service.agreement_progress(
        db_session,
        workspace_id=WORKSPACE,
        agreement_id=invoiced_agreement.id,
        as_of=date(2026, 12, 31),
    )
    paid = await b2b_agreement_service.agreement_progress(
        db_session,
        workspace_id=WORKSPACE,
        agreement_id=paid_agreement.id,
        as_of=date(2026, 12, 31),
    )

    assert ordered["qualifying_sales"] == Decimal("100.00")
    assert invoiced["qualifying_sales"] == Decimal("150.00")
    assert paid["qualifying_sales"] == Decimal("40.00")
    assert isinstance(ordered["agreement_id"], str)
    assert isinstance(ordered["current_tier_id"], str)
    B2BRebateProgressResponse(**ordered)
    assert ordered["included_record_count"] == 1
    assert invoiced["included_record_count"] == 1
    assert paid["included_record_count"] == 1


@pytest.mark.asyncio
async def test_progress_before_period_start_is_zero(db_session) -> None:
    agent = await _create_agent(db_session, suffix="AGR-EARLY")
    agreement = await _create_agreement(
        db_session,
        agent=agent,
        suffix="EARLY",
        basis="ordered",
    )
    await _create_order_and_invoice(
        db_session,
        agent=agent,
        suffix="EARLY",
        amount=Decimal("120.00"),
        issue_date=date(2026, 1, 1),
    )

    progress = await b2b_agreement_service.agreement_progress(
        db_session,
        workspace_id=WORKSPACE,
        agreement_id=agreement.id,
        as_of=date(2025, 12, 31),
    )
    assert progress["qualifying_sales"] == Decimal("0.00")
    assert progress["included_record_count"] == 0


@pytest.mark.asyncio
async def test_progress_converts_currency_and_reports_missing_rate(
    db_session,
) -> None:
    agent = await _create_agent(db_session, suffix="AGR-FX")
    agreement = await _create_agreement(
        db_session,
        agent=agent,
        suffix="FX",
        basis="ordered",
    )
    occurred = datetime(2026, 5, 1, 10, 0, tzinfo=UTC)
    for suffix, amount, currency in [
        ("USD", Decimal("100.00"), "USD"),
        ("EUR", Decimal("50.00"), "EUR"),
    ]:
        db_session.add(
            B2BOrder(
                workspace_id=WORKSPACE,
                order_number=f"B2B-FX-{suffix}",
                agent_id=agent.id,
                business_model="B2B",
                status="confirmed",
                payment_status="unpaid",
                subtotal=amount,
                discount_amount=Decimal("0"),
                shipping_cost=Decimal("0"),
                total=amount,
                currency=currency,
                shipping_address={},
                payment_due_date=date(2026, 6, 1),
                created_at=occurred,
            )
        )
    await db_session.commit()

    missing_rate = await b2b_agreement_service.agreement_progress(
        db_session,
        workspace_id=WORKSPACE,
        agreement_id=agreement.id,
        as_of=date(2026, 12, 31),
    )
    assert missing_rate["qualifying_sales"] == Decimal("100.00")
    assert missing_rate["excluded_record_count"] == 1
    assert missing_rate["missing_rate_currencies"] == ["EUR"]

    await currency_service.create_exchange_rate(
        db_session,
        workspace_id=WORKSPACE,
        base_currency="EUR",
        quote_currency="USD",
        rate=Decimal("1.2"),
        effective_date=date(2026, 1, 1),
        source="manual",
        source_reference="test",
        created_by="finance@example.com",
    )
    converted = await b2b_agreement_service.agreement_progress(
        db_session,
        workspace_id=WORKSPACE,
        agreement_id=agreement.id,
        as_of=date(2026, 12, 31),
    )
    assert converted["qualifying_sales"] == Decimal("160.00")
    assert converted["excluded_record_count"] == 0


@pytest.mark.asyncio
async def test_rebate_accrual_is_idempotent_and_freezes_after_submission(
    db_session,
) -> None:
    agent = await _create_agent(db_session, suffix="AGR-REBATE")
    agreement = await _create_agreement(
        db_session,
        agent=agent,
        suffix="REBATE",
        basis="invoiced",
    )
    agreement = await b2b_agreement_service.submit_agreement(
        db_session,
        workspace_id=WORKSPACE,
        agreement_id=agreement.id,
        actor="operator@example.com",
    )
    agreement = await b2b_agreement_service.approve_agreement(
        db_session,
        workspace_id=WORKSPACE,
        agreement_id=agreement.id,
        actor="admin@example.com",
    )

    _, first_invoice = await _create_order_and_invoice(
        db_session,
        agent=agent,
        suffix="REBATE-1",
        amount=Decimal("120.00"),
        issue_date=date(2026, 4, 10),
    )
    _, _second_invoice = await _create_order_and_invoice(
        db_session,
        agent=agent,
        suffix="REBATE-2",
        amount=Decimal("80.00"),
        issue_date=date(2026, 5, 10),
    )
    first = await b2b_agreement_service.calculate_rebate_accrual(
        db_session,
        workspace_id=WORKSPACE,
        agreement_id=agreement.id,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
        actor="operator@example.com",
    )
    duplicate = await b2b_agreement_service.calculate_rebate_accrual(
        db_session,
        workspace_id=WORKSPACE,
        agreement_id=agreement.id,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
        actor="operator@example.com",
    )
    assert duplicate.id == first.id
    assert first.qualifying_sales == Decimal("200.00")
    assert first.rebate_percent == Decimal("3.00")
    assert first.rebate_amount == Decimal("6.00")

    _, _third_invoice = await _create_order_and_invoice(
        db_session,
        agent=agent,
        suffix="REBATE-3",
        amount=Decimal("50.00"),
        issue_date=date(2026, 6, 10),
    )
    recalculated = await b2b_agreement_service.calculate_rebate_accrual(
        db_session,
        workspace_id=WORKSPACE,
        agreement_id=agreement.id,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
        actor="operator@example.com",
    )
    assert recalculated.qualifying_sales == Decimal("250.00")
    assert recalculated.rebate_amount == Decimal("7.50")

    submitted = await b2b_agreement_service.submit_rebate_accrual(
        db_session,
        workspace_id=WORKSPACE,
        accrual_id=recalculated.id,
        actor="operator@example.com",
    )
    assert submitted.status == "pending_approval"
    _, fourth_invoice = await _create_order_and_invoice(
        db_session,
        agent=agent,
        suffix="REBATE-4",
        amount=Decimal("40.00"),
        issue_date=date(2026, 7, 10),
    )
    frozen = await b2b_agreement_service.calculate_rebate_accrual(
        db_session,
        workspace_id=WORKSPACE,
        agreement_id=agreement.id,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
        actor="operator@example.com",
    )
    assert frozen.id == first.id
    assert frozen.qualifying_sales == Decimal("250.00")
    assert frozen.rebate_amount == Decimal("7.50")
    assert fourth_invoice.status == "issued"

    with pytest.raises(
        b2b_agreement_service.B2BAgreementStateError,
        match="submitter cannot approve",
    ):
        await b2b_agreement_service.approve_rebate_accrual(
            db_session,
            workspace_id=WORKSPACE,
            accrual_id=first.id,
            actor="operator@example.com",
        )
    approved = await b2b_agreement_service.approve_rebate_accrual(
        db_session,
        workspace_id=WORKSPACE,
        accrual_id=first.id,
        actor="admin@example.com",
    )
    settled = await b2b_agreement_service.settle_rebate_accrual(
        db_session,
        workspace_id=WORKSPACE,
        accrual_id=approved.id,
        actor="controller@example.com",
        settlement_reference="BANK-REBATE-2026-001",
    )
    assert settled.status == "settled"
    assert settled.settlement_reference == "BANK-REBATE-2026-001"
    assert first_invoice.status == "issued"


@pytest.mark.asyncio
async def test_agreement_queries_are_workspace_scoped(db_session) -> None:
    other_workspace = uuid4()
    own_agent = await _create_agent(db_session, suffix="AGR-WS-A")
    other_agent = await _create_agent(
        db_session,
        suffix="AGR-WS-B",
        workspace_id=other_workspace,
    )
    own = await _create_agreement(
        db_session,
        agent=own_agent,
        suffix="WS-A",
        basis="invoiced",
    )
    other = await _create_agreement(
        db_session,
        agent=other_agent,
        suffix="WS-B",
        basis="invoiced",
        workspace_id=other_workspace,
    )

    rows, total = await b2b_agreement_service.list_agreements(
        db_session,
        workspace_id=WORKSPACE,
    )
    assert total == 1
    assert rows[0].id == own.id
    assert (
        await b2b_agreement_service.get_agreement(
            db_session,
            workspace_id=WORKSPACE,
            agreement_id=other.id,
        )
        is None
    )
