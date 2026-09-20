"""Tests for B2B credit policy, risk scoring, holds, and insurance."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.b2b import B2BAgent, B2BOrder
from app.services import b2b_credit_service, b2b_finance_service

WORKSPACE = DEFAULT_WORKSPACE_ID


async def _create_agent(
    db_session,
    *,
    number: str = "AG-CREDIT",
    credit_limit: Decimal = Decimal("1000.00"),
    balance: Decimal = Decimal("0.00"),
) -> B2BAgent:
    agent = B2BAgent(
        workspace_id=WORKSPACE,
        agent_number=number,
        company_name=f"Company {number}",
        contact_name="Credit Buyer",
        email=f"{number.lower()}@example.com",
        hashed_password="not-used",
        tier="gold",
        status="active",
        currency="USD",
        credit_limit=credit_limit,
        current_balance=balance,
    )
    db_session.add(agent)
    await db_session.commit()
    return agent


async def _create_overdue_invoice(
    db_session,
    *,
    agent: B2BAgent,
    total: Decimal,
    overdue_days: int,
) -> None:
    order = B2BOrder(
        workspace_id=WORKSPACE,
        order_number=f"B2B-CREDIT-{agent.agent_number}",
        agent_id=agent.id,
        business_model="B2B",
        status="pending",
        payment_status="unpaid",
        subtotal=total,
        discount_amount=Decimal("0"),
        shipping_cost=Decimal("0"),
        total=total,
        currency="USD",
        shipping_address={},
        payment_due_date=date.today() - timedelta(days=overdue_days),
    )
    db_session.add(order)
    await db_session.commit()
    invoice = await b2b_finance_service.create_invoice_from_order(
        db_session,
        workspace_id=WORKSPACE,
        order_id=order.id,
        created_by="finance@example.com",
        issue_date=date.today() - timedelta(days=overdue_days + 30),
        due_date=date.today() - timedelta(days=overdue_days),
    )
    await b2b_finance_service.issue_invoice(
        db_session,
        workspace_id=WORKSPACE,
        invoice_id=invoice.id,
        actor="finance@example.com",
    )


async def _approved_policy(
    db_session,
    *,
    hold_score: int = 60,
    freeze_score: int = 80,
    auto_hold: bool = True,
    auto_freeze: bool = False,
    max_utilization: Decimal = Decimal("100"),
    max_overdue_days: int = 60,
):
    policy = await b2b_credit_service.create_policy(
        db_session,
        workspace_id=WORKSPACE,
        actor="operator@example.com",
        watch_score=35,
        hold_score=hold_score,
        freeze_score=freeze_score,
        auto_hold_enabled=auto_hold,
        auto_freeze_enabled=auto_freeze,
        max_utilization_percent=max_utilization,
        max_overdue_days=max_overdue_days,
    )
    await b2b_credit_service.submit_policy(
        db_session,
        workspace_id=WORKSPACE,
        policy_id=policy.id,
        actor="operator@example.com",
    )
    return await b2b_credit_service.approve_policy(
        db_session,
        workspace_id=WORKSPACE,
        policy_id=policy.id,
        actor="admin@example.com",
    )


@pytest.mark.asyncio
async def test_policy_requires_separate_approver_and_supersedes_previous(
    db_session,
) -> None:
    first = await b2b_credit_service.create_policy(
        db_session,
        workspace_id=WORKSPACE,
        actor="operator@example.com",
    )
    await b2b_credit_service.submit_policy(
        db_session,
        workspace_id=WORKSPACE,
        policy_id=first.id,
        actor="operator@example.com",
    )
    with pytest.raises(
        b2b_credit_service.B2BCreditStateError,
        match="cannot approve",
    ):
        await b2b_credit_service.approve_policy(
            db_session,
            workspace_id=WORKSPACE,
            policy_id=first.id,
            actor="operator@example.com",
        )
    first = await b2b_credit_service.approve_policy(
        db_session,
        workspace_id=WORKSPACE,
        policy_id=first.id,
        actor="admin@example.com",
    )
    assert first.status == "active"

    second = await b2b_credit_service.create_policy(
        db_session,
        workspace_id=WORKSPACE,
        actor="operator@example.com",
        watch_score=30,
    )
    await b2b_credit_service.submit_policy(
        db_session,
        workspace_id=WORKSPACE,
        policy_id=second.id,
        actor="operator@example.com",
    )
    second = await b2b_credit_service.approve_policy(
        db_session,
        workspace_id=WORKSPACE,
        policy_id=second.id,
        actor="admin@example.com",
    )
    refreshed_first = await b2b_credit_service.get_policy(
        db_session,
        workspace_id=WORKSPACE,
        policy_id=first.id,
    )
    assert refreshed_first is not None
    assert refreshed_first.status == "superseded"
    assert second.status == "active"


@pytest.mark.asyncio
async def test_overdue_exposure_triggers_auto_hold_and_blocks_orders(
    db_session,
) -> None:
    agent = await _create_agent(
        db_session,
        balance=Decimal("800.00"),
    )
    await _create_overdue_invoice(
        db_session,
        agent=agent,
        total=Decimal("800.00"),
        overdue_days=70,
    )
    await _approved_policy(
        db_session,
        hold_score=65,
        freeze_score=95,
        auto_hold=True,
    )

    assessment = await b2b_credit_service.assess_agent(
        db_session,
        workspace_id=WORKSPACE,
        agent_id=agent.id,
        actor="risk@example.com",
    )
    assert assessment.recommended_action == "hold"
    assert assessment.applied_action == "hold"
    assert assessment.credit_status_after == "hold"
    assert assessment.max_days_overdue == 70
    assert assessment.utilization_percent == Decimal("80.00")

    with pytest.raises(
        b2b_credit_service.B2BCreditStateError,
        match="credit status is hold",
    ):
        await b2b_credit_service.assert_order_credit(
            db_session,
            workspace_id=WORKSPACE,
            agent_id=agent.id,
            additional_amount=Decimal("10.00"),
        )


@pytest.mark.asyncio
async def test_policy_can_disable_auto_hold_and_admin_can_release(db_session) -> None:
    agent = await _create_agent(
        db_session,
        balance=Decimal("900.00"),
    )
    await _create_overdue_invoice(
        db_session,
        agent=agent,
        total=Decimal("900.00"),
        overdue_days=90,
    )
    await _approved_policy(
        db_session,
        hold_score=60,
        freeze_score=95,
        auto_hold=False,
        auto_freeze=False,
    )
    assessment = await b2b_credit_service.assess_agent(
        db_session,
        workspace_id=WORKSPACE,
        agent_id=agent.id,
        actor="risk@example.com",
    )
    assert assessment.recommended_action in {"hold", "freeze"}
    assert assessment.applied_action == "none"
    assert assessment.credit_status_after == "normal"

    held = await b2b_credit_service.manual_update_status(
        db_session,
        workspace_id=WORKSPACE,
        agent_id=agent.id,
        new_status="hold",
        actor="admin@example.com",
        reason="Manual review pending",
    )
    assert held.credit_status == "hold"
    with pytest.raises(
        b2b_credit_service.B2BCreditStateError,
        match="credit status is hold",
    ):
        await b2b_credit_service.assert_order_credit(
            db_session,
            workspace_id=WORKSPACE,
            agent_id=agent.id,
            additional_amount=Decimal("1.00"),
        )

    released = await b2b_credit_service.manual_update_status(
        db_session,
        workspace_id=WORKSPACE,
        agent_id=agent.id,
        new_status="normal",
        actor="admin@example.com",
        reason="Payment plan approved",
    )
    assert released.credit_status == "normal"
    events = await b2b_credit_service.list_status_events(
        db_session,
        workspace_id=WORKSPACE,
        agent_id=agent.id,
    )
    assert {event.action for event in events} == {"release", "manual_freeze"}


@pytest.mark.asyncio
async def test_auto_freeze_requires_approved_policy_flag(db_session) -> None:
    agent = await _create_agent(
        db_session,
        balance=Decimal("1000.00"),
    )
    await _create_overdue_invoice(
        db_session,
        agent=agent,
        total=Decimal("1000.00"),
        overdue_days=120,
    )
    await _approved_policy(
        db_session,
        hold_score=40,
        freeze_score=70,
        auto_hold=True,
        auto_freeze=True,
        max_utilization=Decimal("100"),
        max_overdue_days=60,
    )
    assessment = await b2b_credit_service.assess_agent(
        db_session,
        workspace_id=WORKSPACE,
        agent_id=agent.id,
        actor="risk@example.com",
    )
    assert assessment.recommended_action == "freeze"
    assert assessment.applied_action == "freeze"
    assert assessment.credit_status_after == "frozen"


@pytest.mark.asyncio
async def test_insurance_coverage_reduces_risk_and_claim_lifecycle(db_session) -> None:
    agent = await _create_agent(
        db_session,
        balance=Decimal("500.00"),
    )
    unused = await _create_agent(
        db_session,
        number="AG-UNINSURED",
        balance=Decimal("500.00"),
    )
    await _create_overdue_invoice(
        db_session,
        agent=agent,
        total=Decimal("500.00"),
        overdue_days=30,
    )
    await _create_overdue_invoice(
        db_session,
        agent=unused,
        total=Decimal("500.00"),
        overdue_days=30,
    )
    await _approved_policy(
        db_session,
        hold_score=90,
        freeze_score=100,
        auto_hold=False,
        max_overdue_days=120,
    )
    policy = await b2b_credit_service.create_insurance_policy(
        db_session,
        workspace_id=WORKSPACE,
        agent_id=agent.id,
        policy_number="INS-CREDIT-001",
        provider="Test Credit Insurer",
        currency="USD",
        coverage_limit=Decimal("500.00"),
        coverage_percent=Decimal("80.00"),
        effective_from=date.today() - timedelta(days=1),
        effective_to=date.today() + timedelta(days=365),
        status="active",
        actor="operator@example.com",
    )
    insured = await b2b_credit_service.assess_agent(
        db_session,
        workspace_id=WORKSPACE,
        agent_id=agent.id,
        actor="risk@example.com",
    )
    uninsured = await b2b_credit_service.assess_agent(
        db_session,
        workspace_id=WORKSPACE,
        agent_id=unused.id,
        actor="risk@example.com",
    )
    assert insured.insurance_coverage_amount == Decimal("400.00")
    assert insured.insurance_coverage_percent == Decimal("80.00")
    assert insured.score < uninsured.score

    invoice = (
        await b2b_finance_service.list_invoices(
            db_session,
            workspace_id=WORKSPACE,
            agent_id=agent.id,
        )
    )[0][0]
    claim = await b2b_credit_service.create_insurance_claim(
        db_session,
        workspace_id=WORKSPACE,
        policy_id=policy.id,
        invoice_id=invoice.id,
        claimed_amount=Decimal("300.00"),
        reason="Customer insolvency",
        actor="operator@example.com",
    )
    assert claim.status == "draft"
    submitted = await b2b_credit_service.transition_insurance_claim(
        db_session,
        workspace_id=WORKSPACE,
        claim_id=claim.id,
        new_status="submitted",
        actor="operator@example.com",
    )
    assert submitted.status == "submitted"
    approved = await b2b_credit_service.transition_insurance_claim(
        db_session,
        workspace_id=WORKSPACE,
        claim_id=claim.id,
        new_status="approved",
        actor="admin@example.com",
    )
    assert approved.status == "approved"
    settled = await b2b_credit_service.transition_insurance_claim(
        db_session,
        workspace_id=WORKSPACE,
        claim_id=claim.id,
        new_status="settled",
        actor="admin@example.com",
        recovered_amount=Decimal("240.00"),
        settlement_reference="INS-PAY-001",
    )
    assert settled.status == "settled"
    assert settled.recovered_amount == Decimal("240.00")


@pytest.mark.asyncio
async def test_credit_records_are_workspace_scoped(db_session) -> None:
    agent = await _create_agent(db_session)
    policy = await b2b_credit_service.create_policy(
        db_session,
        workspace_id=WORKSPACE,
        actor="operator@example.com",
    )
    await _create_overdue_invoice(
        db_session,
        agent=agent,
        total=Decimal("500.00"),
        overdue_days=30,
    )
    insurance_policy = await b2b_credit_service.create_insurance_policy(
        db_session,
        workspace_id=WORKSPACE,
        agent_id=agent.id,
        policy_number="INS-SCOPE-001",
        provider="Scoped Insurer",
        currency="USD",
        coverage_limit=Decimal("500.00"),
        coverage_percent=Decimal("80.00"),
        effective_from=date.today() - timedelta(days=1),
        effective_to=date.today() + timedelta(days=365),
        status="active",
        actor="operator@example.com",
    )
    invoice = (
        await b2b_finance_service.list_invoices(
            db_session,
            workspace_id=WORKSPACE,
            agent_id=agent.id,
        )
    )[0][0]
    claim = await b2b_credit_service.create_insurance_claim(
        db_session,
        workspace_id=WORKSPACE,
        policy_id=insurance_policy.id,
        invoice_id=invoice.id,
        claimed_amount=Decimal("100.00"),
        reason="Workspace scope regression",
        actor="operator@example.com",
    )
    other_workspace = uuid4()
    assert (
        await b2b_credit_service.get_policy(
            db_session,
            workspace_id=other_workspace,
            policy_id=policy.id,
        )
        is None
    )
    with pytest.raises(b2b_credit_service.B2BCreditNotFoundError):
        await b2b_credit_service.get_agent_risk_detail(
            db_session,
            workspace_id=other_workspace,
            agent_id=agent.id,
        )
    assert (
        await b2b_credit_service.list_insurance_policies(
            db_session,
            workspace_id=other_workspace,
        )
        == []
    )
    assert (
        await b2b_credit_service.list_insurance_claims(
            db_session,
            workspace_id=other_workspace,
        )
        == []
    )
    assert claim.workspace_id == WORKSPACE
