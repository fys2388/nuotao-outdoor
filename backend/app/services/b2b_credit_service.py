"""Deterministic B2B credit policy, risk scoring, holds, and insurance."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.b2b import B2BAgent
from app.models.b2b_credit import (
    B2BCreditInsuranceClaim,
    B2BCreditInsurancePolicy,
    B2BCreditPolicy,
    B2BCreditRiskAssessment,
    B2BCreditStatusEvent,
)
from app.models.b2b_finance import B2BInvoice
from app.services import event_service

MONEY = Decimal("0.01")
PERCENT = Decimal("0.01")
ZERO = Decimal("0.00")
ONE_HUNDRED = Decimal("100")

CLAIM_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"submitted"},
    "submitted": {"approved", "rejected"},
    "approved": {"settled"},
    "rejected": set(),
    "settled": set(),
}


class B2BCreditError(ValueError):
    """Base class for B2B credit domain errors."""


class B2BCreditNotFoundError(B2BCreditError):
    """Raised when a policy, agent, invoice, or claim does not exist."""


class B2BCreditStateError(B2BCreditError):
    """Raised when credit state or a transition forbids the operation."""


class B2BCreditConflictError(B2BCreditError):
    """Raised when a unique credit business key conflicts with existing data."""


def _uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _money(value: Decimal | str | int | float) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def _percent(value: Decimal | str | int | float) -> Decimal:
    return Decimal(str(value)).quantize(PERCENT, rounding=ROUND_HALF_UP)


def _number(prefix: str) -> str:
    now = datetime.now(timezone.utc)
    return f"{prefix}-{now.strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"


async def _get_agent(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    agent_id: str | UUID,
    for_update: bool = False,
) -> B2BAgent:
    query = select(B2BAgent).where(
        B2BAgent.workspace_id == workspace_id,
        B2BAgent.id == _uuid(agent_id),
    )
    if for_update:
        query = query.with_for_update()
    agent = (await db.execute(query)).scalar_one_or_none()
    if agent is None:
        raise B2BCreditNotFoundError("agent not found")
    return agent


async def get_policy(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    policy_id: str | UUID,
) -> B2BCreditPolicy | None:
    return (
        await db.execute(
            select(B2BCreditPolicy).where(
                B2BCreditPolicy.workspace_id == workspace_id,
                B2BCreditPolicy.id == _uuid(policy_id),
            )
        )
    ).scalar_one_or_none()


async def get_active_policy(
    db: AsyncSession,
    *,
    workspace_id: UUID,
) -> B2BCreditPolicy | None:
    return (
        await db.execute(
            select(B2BCreditPolicy).where(
                B2BCreditPolicy.workspace_id == workspace_id,
                B2BCreditPolicy.status == "active",
            )
        )
    ).scalar_one_or_none()


async def list_policies(
    db: AsyncSession,
    *,
    workspace_id: UUID,
) -> list[B2BCreditPolicy]:
    rows = (
        await db.execute(
            select(B2BCreditPolicy)
            .where(B2BCreditPolicy.workspace_id == workspace_id)
            .order_by(B2BCreditPolicy.version_number.desc())
        )
    ).scalars().all()
    return list(rows)


def _validate_policy_thresholds(
    *,
    watch_score: int,
    hold_score: int,
    freeze_score: int,
    max_utilization_percent: Decimal,
    max_overdue_days: int,
    insurance_required_above: Decimal,
) -> None:
    if not (0 <= watch_score < hold_score < freeze_score <= 100):
        raise B2BCreditError(
            "credit score thresholds must satisfy 0 <= watch < hold < freeze <= 100"
        )
    if Decimal(max_utilization_percent) < ZERO:
        raise B2BCreditError("max_utilization_percent must be non-negative")
    if max_overdue_days < 0:
        raise B2BCreditError("max_overdue_days must be non-negative")
    if Decimal(insurance_required_above) < ZERO:
        raise B2BCreditError("insurance_required_above must be non-negative")


async def create_policy(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    actor: str,
    watch_score: int = 35,
    hold_score: int = 60,
    freeze_score: int = 80,
    max_utilization_percent: Decimal = Decimal("100"),
    max_overdue_days: int = 60,
    auto_hold_enabled: bool = True,
    auto_freeze_enabled: bool = False,
    insurance_required_above: Decimal = ZERO,
    notes: str | None = None,
) -> B2BCreditPolicy:
    _validate_policy_thresholds(
        watch_score=watch_score,
        hold_score=hold_score,
        freeze_score=freeze_score,
        max_utilization_percent=max_utilization_percent,
        max_overdue_days=max_overdue_days,
        insurance_required_above=insurance_required_above,
    )
    latest = (
        await db.execute(
            select(func.coalesce(func.max(B2BCreditPolicy.version_number), 0)).where(
                B2BCreditPolicy.workspace_id == workspace_id
            )
        )
    ).scalar_one()
    policy = B2BCreditPolicy(
        workspace_id=workspace_id,
        version_number=int(latest) + 1,
        status="draft",
        watch_score=watch_score,
        hold_score=hold_score,
        freeze_score=freeze_score,
        max_utilization_percent=_percent(max_utilization_percent),
        max_overdue_days=max_overdue_days,
        auto_hold_enabled=auto_hold_enabled,
        auto_freeze_enabled=auto_freeze_enabled,
        insurance_required_above=_money(insurance_required_above),
        notes=notes,
        created_by=actor,
    )
    db.add(policy)
    await db.flush()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_credit_policy.created",
        entity_type="b2b_credit_policy",
        entity_id=str(policy.id),
        payload={
            "version_number": policy.version_number,
            "actor": actor,
            "watch_score": policy.watch_score,
            "hold_score": policy.hold_score,
            "freeze_score": policy.freeze_score,
        },
    )
    await db.commit()
    return await get_policy(
        db,
        workspace_id=workspace_id,
        policy_id=policy.id,
    )  # type: ignore[return-value]


async def _get_policy_for_update(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    policy_id: str | UUID,
) -> B2BCreditPolicy:
    policy = (
        await db.execute(
            select(B2BCreditPolicy)
            .where(
                B2BCreditPolicy.workspace_id == workspace_id,
                B2BCreditPolicy.id == _uuid(policy_id),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if policy is None:
        raise B2BCreditNotFoundError("credit policy not found")
    return policy


async def submit_policy(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    policy_id: str | UUID,
    actor: str,
) -> B2BCreditPolicy:
    policy = await _get_policy_for_update(
        db,
        workspace_id=workspace_id,
        policy_id=policy_id,
    )
    if policy.status not in {"draft", "rejected"}:
        raise B2BCreditStateError("only draft or rejected policies can be submitted")
    policy.status = "pending_approval"
    policy.submitted_by = actor
    policy.submitted_at = datetime.now(timezone.utc)
    policy.rejection_reason = None
    await db.flush()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_credit_policy.submitted",
        entity_type="b2b_credit_policy",
        entity_id=str(policy.id),
        payload={"version_number": policy.version_number, "actor": actor},
    )
    await db.commit()
    return await get_policy(
        db,
        workspace_id=workspace_id,
        policy_id=policy.id,
    )  # type: ignore[return-value]


async def approve_policy(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    policy_id: str | UUID,
    actor: str,
) -> B2BCreditPolicy:
    policy = await _get_policy_for_update(
        db,
        workspace_id=workspace_id,
        policy_id=policy_id,
    )
    if policy.status != "pending_approval":
        raise B2BCreditStateError("only pending policies can be approved")
    if policy.submitted_by == actor:
        raise B2BCreditStateError("policy submitter cannot approve the same policy")

    active_policy = (
        await db.execute(
            select(B2BCreditPolicy)
            .where(
                B2BCreditPolicy.workspace_id == workspace_id,
                B2BCreditPolicy.status == "active",
                B2BCreditPolicy.id != policy.id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if active_policy is not None:
        active_policy.status = "superseded"
        await db.flush()

    now = datetime.now(timezone.utc)
    policy.status = "active"
    policy.approved_by = actor
    policy.approved_at = now
    await db.flush()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_credit_policy.approved",
        entity_type="b2b_credit_policy",
        entity_id=str(policy.id),
        payload={
            "version_number": policy.version_number,
            "superseded_policy_id": str(active_policy.id) if active_policy else None,
            "actor": actor,
        },
    )
    await db.commit()
    return await get_policy(
        db,
        workspace_id=workspace_id,
        policy_id=policy.id,
    )  # type: ignore[return-value]


async def reject_policy(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    policy_id: str | UUID,
    actor: str,
    reason: str,
) -> B2BCreditPolicy:
    if not reason.strip():
        raise B2BCreditError("rejection reason is required")
    policy = await _get_policy_for_update(
        db,
        workspace_id=workspace_id,
        policy_id=policy_id,
    )
    if policy.status != "pending_approval":
        raise B2BCreditStateError("only pending policies can be rejected")
    if policy.submitted_by == actor:
        raise B2BCreditStateError("policy submitter cannot reject the same policy")
    policy.status = "rejected"
    policy.rejected_by = actor
    policy.rejected_at = datetime.now(timezone.utc)
    policy.rejection_reason = reason.strip()
    await db.flush()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_credit_policy.rejected",
        entity_type="b2b_credit_policy",
        entity_id=str(policy.id),
        payload={
            "version_number": policy.version_number,
            "reason": policy.rejection_reason,
            "actor": actor,
        },
    )
    await db.commit()
    return await get_policy(
        db,
        workspace_id=workspace_id,
        policy_id=policy.id,
    )  # type: ignore[return-value]


def calculate_risk_score(
    *,
    exposure_amount: Decimal,
    credit_limit: Decimal,
    overdue_amount: Decimal,
    max_days_overdue: int,
    written_off_amount: Decimal,
    insurance_coverage_percent: Decimal,
    policy: B2BCreditPolicy,
) -> dict[str, Decimal | int | str]:
    """Return a deterministic score and explainable factors."""
    exposure = max(_money(exposure_amount), ZERO)
    limit = max(_money(credit_limit), ZERO)
    overdue = min(max(_money(overdue_amount), ZERO), exposure)
    written_off = max(_money(written_off_amount), ZERO)
    coverage_percent = max(min(_percent(insurance_coverage_percent), ONE_HUNDRED), ZERO)

    utilization = (
        (exposure / limit * ONE_HUNDRED).quantize(PERCENT, rounding=ROUND_HALF_UP)
        if limit > ZERO
        else ZERO
    )
    overdue_ratio = (
        (overdue / exposure * ONE_HUNDRED).quantize(PERCENT, rounding=ROUND_HALF_UP)
        if exposure > ZERO
        else ZERO
    )
    utilization_component = min(utilization / ONE_HUNDRED, Decimal("1")) * Decimal("40")
    overdue_component = min(overdue_ratio / ONE_HUNDRED, Decimal("1")) * Decimal("30")
    overdue_days_component = min(
        Decimal(max(max_days_overdue, 0)) / Decimal("90"),
        Decimal("1"),
    ) * Decimal("20")
    write_off_base = exposure + written_off
    write_off_component = (
        min(written_off / write_off_base, Decimal("1")) * Decimal("10")
        if write_off_base > ZERO
        else ZERO
    )
    insurance_discount = (
        min(coverage_percent / ONE_HUNDRED, Decimal("1")) * Decimal("15")
    )
    raw_score = (
        utilization_component
        + overdue_component
        + overdue_days_component
        + write_off_component
        - insurance_discount
    )
    score = int(
        max(Decimal("0"), min(Decimal("100"), raw_score)).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )

    action = "none"
    if score >= policy.freeze_score:
        action = "freeze"
    elif (
        score >= policy.hold_score
        or (
            policy.max_utilization_percent > ZERO
            and utilization >= policy.max_utilization_percent
        )
        or (
            policy.max_overdue_days > 0
            and max_days_overdue >= policy.max_overdue_days
        )
    ):
        action = "hold"
    elif score >= policy.watch_score:
        action = "watch"

    if score >= policy.freeze_score:
        level = "critical"
    elif score >= policy.hold_score:
        level = "high"
    elif score >= policy.watch_score:
        level = "medium"
    else:
        level = "low"

    return {
        "score": score,
        "risk_level": level,
        "recommended_action": action,
        "exposure_amount": exposure,
        "overdue_amount": overdue,
        "utilization_percent": utilization,
        "overdue_ratio_percent": overdue_ratio,
        "insurance_coverage_percent": coverage_percent,
        "factors": {
            "utilization_component": str(
                utilization_component.quantize(MONEY, rounding=ROUND_HALF_UP)
            ),
            "overdue_ratio_component": str(
                overdue_component.quantize(MONEY, rounding=ROUND_HALF_UP)
            ),
            "overdue_days_component": str(
                overdue_days_component.quantize(MONEY, rounding=ROUND_HALF_UP)
            ),
            "write_off_component": str(
                write_off_component.quantize(MONEY, rounding=ROUND_HALF_UP)
            ),
            "insurance_discount": str(
                insurance_discount.quantize(MONEY, rounding=ROUND_HALF_UP)
            ),
            "weights": {
                "utilization": "40",
                "overdue_ratio": "30",
                "overdue_days": "20",
                "write_off": "10",
                "insurance_max_discount": "15",
            },
        },
    }


async def _resolve_insurance(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    agent_id: UUID,
    as_of: date,
) -> B2BCreditInsurancePolicy | None:
    return (
        await db.execute(
            select(B2BCreditInsurancePolicy)
            .where(
                B2BCreditInsurancePolicy.workspace_id == workspace_id,
                B2BCreditInsurancePolicy.agent_id == agent_id,
                B2BCreditInsurancePolicy.status == "active",
                B2BCreditInsurancePolicy.effective_from <= as_of,
                B2BCreditInsurancePolicy.effective_to >= as_of,
            )
            .order_by(B2BCreditInsurancePolicy.effective_from.desc())
        )
    ).scalars().first()


async def assess_agent(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    agent_id: str | UUID,
    actor: str,
    as_of: date | None = None,
    trace_id: str | None = None,
) -> B2BCreditRiskAssessment:
    policy = await get_active_policy(db, workspace_id=workspace_id)
    if policy is None:
        raise B2BCreditStateError("an active credit policy is required")
    agent = await _get_agent(
        db,
        workspace_id=workspace_id,
        agent_id=agent_id,
        for_update=True,
    )
    assessment_date = as_of or date.today()
    invoices = (
        await db.execute(
            select(B2BInvoice).where(
                B2BInvoice.workspace_id == workspace_id,
                B2BInvoice.agent_id == agent.id,
            )
        )
    ).scalars().all()

    open_balances = [
        _money(invoice.balance_due)
        for invoice in invoices
        if _money(invoice.balance_due) > ZERO
    ]
    exposure = sum(open_balances, ZERO)
    if not open_balances:
        exposure = max(_money(agent.current_balance), ZERO)
    overdue = sum(
        (
            _money(invoice.balance_due)
            for invoice in invoices
            if _money(invoice.balance_due) > ZERO and invoice.due_date < assessment_date
        ),
        ZERO,
    )
    overdue_days = [
        (assessment_date - invoice.due_date).days
        for invoice in invoices
        if _money(invoice.balance_due) > ZERO and invoice.due_date < assessment_date
    ]
    written_off = sum(
        (_money(invoice.amount_written_off) for invoice in invoices),
        ZERO,
    )
    insurance = await _resolve_insurance(
        db,
        workspace_id=workspace_id,
        agent_id=agent.id,
        as_of=assessment_date,
    )
    coverage_percent = (
        _percent(insurance.coverage_percent) if insurance is not None else ZERO
    )
    coverage_amount = ZERO
    if insurance is not None:
        covered_base = min(exposure, _money(insurance.coverage_limit))
        coverage_amount = _money(covered_base * coverage_percent / ONE_HUNDRED)

    result = calculate_risk_score(
        exposure_amount=exposure,
        credit_limit=agent.credit_limit,
        overdue_amount=overdue,
        max_days_overdue=max(overdue_days, default=0),
        written_off_amount=written_off,
        insurance_coverage_percent=coverage_percent,
        policy=policy,
    )
    recommended_action = str(result["recommended_action"])
    previous_status = agent.credit_status
    desired_status = previous_status
    applied_action = "none"
    reason = "Risk assessment recorded; no automatic status change."

    if previous_status not in {"hold", "frozen"}:
        if recommended_action == "freeze" and policy.auto_freeze_enabled:
            desired_status = "frozen"
            applied_action = "freeze"
            reason = (
                f"Automatic freeze: score {result['score']} reached "
                f"policy threshold {policy.freeze_score}."
            )
        elif recommended_action == "hold" and policy.auto_hold_enabled:
            desired_status = "hold"
            applied_action = "hold"
            reason = (
                f"Automatic hold: score or exposure reached policy "
                f"thresholds (score {result['score']})."
            )
        elif recommended_action == "watch":
            desired_status = "watch"
            applied_action = "watch"
            reason = f"Automatic watch: score {result['score']}."
        else:
            desired_status = "normal"
            applied_action = "none"
    elif previous_status == "hold" and recommended_action == "freeze":
        if policy.auto_freeze_enabled:
            desired_status = "frozen"
            applied_action = "freeze"
            reason = (
                f"Automatic escalation from hold to frozen: score "
                f"{result['score']} reached {policy.freeze_score}."
            )
        else:
            reason = "Recommended freeze requires an administrator."
    else:
        reason = "Existing hold or freeze is protected from automatic release."

    now = datetime.now(timezone.utc)
    assessment = B2BCreditRiskAssessment(
        workspace_id=workspace_id,
        agent_id=agent.id,
        policy_id=policy.id,
        score=int(result["score"]),
        risk_level=str(result["risk_level"]),
        recommended_action=recommended_action,
        applied_action=applied_action,
        credit_status_before=previous_status,
        credit_status_after=desired_status,
        exposure_amount=_money(exposure),
        overdue_amount=_money(overdue),
        utilization_percent=_percent(result["utilization_percent"]),
        overdue_ratio_percent=_percent(result["overdue_ratio_percent"]),
        max_days_overdue=max(overdue_days, default=0),
        past_due_invoice_count=len(overdue_days),
        written_off_amount=_money(written_off),
        insurance_coverage_amount=coverage_amount,
        insurance_coverage_percent=coverage_percent,
        net_exposure_amount=_money(max(exposure - coverage_amount, ZERO)),
        factors=result["factors"],
        message=reason,
        assessed_by=actor,
        assessed_at=now,
    )
    db.add(assessment)
    await db.flush()

    if desired_status != previous_status:
        agent.credit_status = desired_status
        agent.credit_status_reason = reason
        agent.credit_status_updated_by = (
            f"credit-policy:{policy.id}" if applied_action != "none" else actor
        )
        agent.credit_status_updated_at = now
        agent.credit_policy_id = policy.id
        db.add(
            B2BCreditStatusEvent(
                workspace_id=workspace_id,
                agent_id=agent.id,
                assessment_id=assessment.id,
                previous_status=previous_status,
                new_status=desired_status,
                action=f"auto_{applied_action}" if applied_action != "none" else "assess",
                reason=reason,
                actor=f"credit-policy:{policy.id}",
                evidence={
                    "score": assessment.score,
                    "risk_level": assessment.risk_level,
                    "recommended_action": recommended_action,
                    "exposure_amount": str(assessment.exposure_amount),
                    "overdue_amount": str(assessment.overdue_amount),
                },
            )
        )
    await db.flush()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_credit.assessed",
        entity_type="b2b_agent",
        entity_id=str(agent.id),
        payload={
            "assessment_id": str(assessment.id),
            "policy_id": str(policy.id),
            "score": assessment.score,
            "risk_level": assessment.risk_level,
            "recommended_action": recommended_action,
            "applied_action": applied_action,
            "credit_status": desired_status,
            "actor": actor,
        },
        trace_id=trace_id,
    )
    await db.commit()
    return (
        await db.execute(
            select(B2BCreditRiskAssessment).where(
                B2BCreditRiskAssessment.id == assessment.id
            )
        )
    ).scalar_one()


async def assert_order_credit(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    agent_id: str | UUID,
    additional_amount: Decimal,
) -> B2BAgent:
    """Central order-admission check shared by every B2B order entry point."""
    agent = await _get_agent(
        db,
        workspace_id=workspace_id,
        agent_id=agent_id,
        for_update=True,
    )
    if agent.credit_status in {"hold", "frozen"}:
        raise B2BCreditStateError(
            f"customer credit status is {agent.credit_status}: "
            f"{agent.credit_status_reason or 'manual review required'}"
        )
    amount = _money(additional_amount)
    limit = _money(agent.credit_limit)
    if limit > ZERO and _money(agent.current_balance) + amount > limit:
        available = max(limit - _money(agent.current_balance), ZERO)
        raise B2BCreditStateError(
            f"credit limit exceeded; available {available}, order total {amount}"
        )
    return agent


async def manual_update_status(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    agent_id: str | UUID,
    new_status: str,
    actor: str,
    reason: str,
    trace_id: str | None = None,
) -> B2BAgent:
    if new_status not in {"normal", "watch", "hold", "frozen"}:
        raise B2BCreditError("invalid credit status")
    if not reason.strip():
        raise B2BCreditError("credit status reason is required")
    agent = await _get_agent(
        db,
        workspace_id=workspace_id,
        agent_id=agent_id,
        for_update=True,
    )
    previous = agent.credit_status
    if previous == new_status:
        return agent
    now = datetime.now(timezone.utc)
    agent.credit_status = new_status
    agent.credit_status_reason = reason.strip()
    agent.credit_status_updated_by = actor
    agent.credit_status_updated_at = now
    event = B2BCreditStatusEvent(
        workspace_id=workspace_id,
        agent_id=agent.id,
        previous_status=previous,
        new_status=new_status,
        action="release" if new_status in {"normal", "watch"} else "manual_freeze",
        reason=reason.strip(),
        actor=actor,
        evidence={},
    )
    db.add(event)
    await db.flush()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_credit.status_changed",
        entity_type="b2b_agent",
        entity_id=str(agent.id),
        payload={
            "previous_status": previous,
            "new_status": new_status,
            "reason": reason.strip(),
            "actor": actor,
        },
        trace_id=trace_id,
    )
    await db.commit()
    return await _get_agent(
        db,
        workspace_id=workspace_id,
        agent_id=agent.id,
    )


async def list_status_events(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    agent_id: str | UUID,
    limit: int = 100,
) -> list[B2BCreditStatusEvent]:
    rows = (
        await db.execute(
            select(B2BCreditStatusEvent)
            .where(
                B2BCreditStatusEvent.workspace_id == workspace_id,
                B2BCreditStatusEvent.agent_id == _uuid(agent_id),
            )
            .order_by(B2BCreditStatusEvent.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return list(rows)


async def list_risk_overview(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    limit: int = 200,
) -> tuple[list[tuple[B2BAgent, B2BCreditRiskAssessment | None]], B2BCreditPolicy | None]:
    policy = await get_active_policy(db, workspace_id=workspace_id)
    agents = (
        await db.execute(
            select(B2BAgent)
            .where(B2BAgent.workspace_id == workspace_id)
            .order_by(B2BAgent.company_name.asc())
            .limit(limit)
        )
    ).scalars().all()
    agent_ids = [agent.id for agent in agents]
    assessments: dict[UUID, B2BCreditRiskAssessment] = {}
    if agent_ids:
        rows = (
            await db.execute(
                select(B2BCreditRiskAssessment)
                .where(
                    B2BCreditRiskAssessment.workspace_id == workspace_id,
                    B2BCreditRiskAssessment.agent_id.in_(agent_ids),
                )
                .order_by(B2BCreditRiskAssessment.assessed_at.desc())
            )
        ).scalars().all()
        for assessment in rows:
            assessments.setdefault(assessment.agent_id, assessment)
    return [(agent, assessments.get(agent.id)) for agent in agents], policy


async def get_agent_risk_detail(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    agent_id: str | UUID,
) -> tuple[B2BAgent, B2BCreditRiskAssessment | None, B2BCreditInsurancePolicy | None]:
    agent = await _get_agent(db, workspace_id=workspace_id, agent_id=agent_id)
    assessment = (
        await db.execute(
            select(B2BCreditRiskAssessment)
            .where(
                B2BCreditRiskAssessment.workspace_id == workspace_id,
                B2BCreditRiskAssessment.agent_id == agent.id,
            )
            .order_by(B2BCreditRiskAssessment.assessed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    insurance = await _resolve_insurance(
        db,
        workspace_id=workspace_id,
        agent_id=agent.id,
        as_of=date.today(),
    )
    return agent, assessment, insurance


async def create_insurance_policy(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    agent_id: str | UUID,
    policy_number: str,
    provider: str,
    currency: str,
    coverage_limit: Decimal,
    coverage_percent: Decimal,
    effective_from: date,
    effective_to: date,
    actor: str,
    status: str = "draft",
    notes: str | None = None,
    trace_id: str | None = None,
) -> B2BCreditInsurancePolicy:
    agent = await _get_agent(db, workspace_id=workspace_id, agent_id=agent_id)
    normalized_number = policy_number.strip().upper()
    if not normalized_number or not provider.strip():
        raise B2BCreditError("insurance policy number and provider are required")
    if status not in {"draft", "active"}:
        raise B2BCreditError("new insurance policy must be draft or active")
    if _money(coverage_limit) <= ZERO:
        raise B2BCreditError("coverage_limit must be positive")
    if not (ZERO < _percent(coverage_percent) <= ONE_HUNDRED):
        raise B2BCreditError("coverage_percent must be greater than 0 and at most 100")
    if effective_to < effective_from:
        raise B2BCreditError("effective_to cannot be before effective_from")
    existing = (
        await db.execute(
            select(B2BCreditInsurancePolicy).where(
                B2BCreditInsurancePolicy.workspace_id == workspace_id,
                B2BCreditInsurancePolicy.policy_number == normalized_number,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise B2BCreditConflictError("insurance policy number already exists")
    if status == "active":
        overlap = (
            await db.execute(
                select(B2BCreditInsurancePolicy).where(
                    B2BCreditInsurancePolicy.workspace_id == workspace_id,
                    B2BCreditInsurancePolicy.agent_id == agent.id,
                    B2BCreditInsurancePolicy.status == "active",
                    B2BCreditInsurancePolicy.effective_from <= effective_to,
                    B2BCreditInsurancePolicy.effective_to >= effective_from,
                )
            )
        ).scalars().first()
        if overlap is not None:
            raise B2BCreditConflictError("active insurance policy periods overlap")
    policy = B2BCreditInsurancePolicy(
        workspace_id=workspace_id,
        agent_id=agent.id,
        policy_number=normalized_number,
        provider=provider.strip(),
        status=status,
        currency=currency.upper(),
        coverage_limit=_money(coverage_limit),
        coverage_percent=_percent(coverage_percent),
        effective_from=effective_from,
        effective_to=effective_to,
        notes=notes,
        created_by=actor,
        updated_by=actor,
    )
    db.add(policy)
    await db.flush()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_credit_insurance.created",
        entity_type="b2b_credit_insurance_policy",
        entity_id=str(policy.id),
        payload={
            "agent_id": str(agent.id),
            "policy_number": policy.policy_number,
            "status": policy.status,
            "coverage_limit": str(policy.coverage_limit),
            "coverage_percent": str(policy.coverage_percent),
            "actor": actor,
        },
        trace_id=trace_id,
    )
    await db.commit()
    return (
        await db.execute(
            select(B2BCreditInsurancePolicy).where(
                B2BCreditInsurancePolicy.id == policy.id
            )
        )
    ).scalar_one()


async def list_insurance_policies(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    agent_id: str | UUID | None = None,
) -> list[B2BCreditInsurancePolicy]:
    query = select(B2BCreditInsurancePolicy).where(
        B2BCreditInsurancePolicy.workspace_id == workspace_id
    )
    if agent_id:
        query = query.where(B2BCreditInsurancePolicy.agent_id == _uuid(agent_id))
    rows = (
        await db.execute(
            query.order_by(B2BCreditInsurancePolicy.effective_from.desc())
        )
    ).scalars().all()
    return list(rows)


async def update_insurance_policy(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    policy_id: str | UUID,
    actor: str,
    provider: str | None = None,
    status: str | None = None,
    coverage_limit: Decimal | None = None,
    coverage_percent: Decimal | None = None,
    effective_from: date | None = None,
    effective_to: date | None = None,
    notes: str | None = None,
    trace_id: str | None = None,
) -> B2BCreditInsurancePolicy:
    policy = (
        await db.execute(
            select(B2BCreditInsurancePolicy)
            .where(
                B2BCreditInsurancePolicy.workspace_id == workspace_id,
                B2BCreditInsurancePolicy.id == _uuid(policy_id),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if policy is None:
        raise B2BCreditNotFoundError("insurance policy not found")
    if policy.status in {"expired", "cancelled"} and status not in {"expired", "cancelled"}:
        raise B2BCreditStateError("closed insurance policy cannot be reopened")

    next_provider = provider.strip() if provider is not None else policy.provider
    next_status = status or policy.status
    next_limit = (
        _money(coverage_limit)
        if coverage_limit is not None
        else _money(policy.coverage_limit)
    )
    next_percent = (
        _percent(coverage_percent)
        if coverage_percent is not None
        else _percent(policy.coverage_percent)
    )
    next_from = effective_from or policy.effective_from
    next_to = effective_to or policy.effective_to
    if not next_provider:
        raise B2BCreditError("provider is required")
    if next_status not in {"draft", "active", "expired", "cancelled"}:
        raise B2BCreditError("invalid insurance policy status")
    if next_limit <= ZERO:
        raise B2BCreditError("coverage_limit must be positive")
    if not (ZERO < next_percent <= ONE_HUNDRED):
        raise B2BCreditError("coverage_percent must be greater than 0 and at most 100")
    if next_to < next_from:
        raise B2BCreditError("effective_to cannot be before effective_from")
    if next_status == "active":
        overlap = (
            await db.execute(
                select(B2BCreditInsurancePolicy).where(
                    B2BCreditInsurancePolicy.workspace_id == workspace_id,
                    B2BCreditInsurancePolicy.agent_id == policy.agent_id,
                    B2BCreditInsurancePolicy.status == "active",
                    B2BCreditInsurancePolicy.id != policy.id,
                    B2BCreditInsurancePolicy.effective_from <= next_to,
                    B2BCreditInsurancePolicy.effective_to >= next_from,
                )
            )
        ).scalars().first()
        if overlap is not None:
            raise B2BCreditConflictError("active insurance policy periods overlap")

    policy.provider = next_provider
    policy.status = next_status
    policy.coverage_limit = next_limit
    policy.coverage_percent = next_percent
    policy.effective_from = next_from
    policy.effective_to = next_to
    if notes is not None:
        policy.notes = notes
    policy.updated_by = actor
    await db.flush()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_credit_insurance.updated",
        entity_type="b2b_credit_insurance_policy",
        entity_id=str(policy.id),
        payload={
            "policy_number": policy.policy_number,
            "status": policy.status,
            "coverage_limit": str(policy.coverage_limit),
            "coverage_percent": str(policy.coverage_percent),
            "actor": actor,
        },
        trace_id=trace_id,
    )
    await db.commit()
    return (
        await db.execute(
            select(B2BCreditInsurancePolicy).where(
                B2BCreditInsurancePolicy.id == policy.id
            )
        )
    ).scalar_one()


async def create_insurance_claim(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    policy_id: str | UUID,
    invoice_id: str | UUID,
    claimed_amount: Decimal,
    reason: str,
    actor: str,
    evidence: dict | None = None,
    trace_id: str | None = None,
) -> B2BCreditInsuranceClaim:
    policy = (
        await db.execute(
            select(B2BCreditInsurancePolicy).where(
                B2BCreditInsurancePolicy.workspace_id == workspace_id,
                B2BCreditInsurancePolicy.id == _uuid(policy_id),
            )
        )
    ).scalar_one_or_none()
    if policy is None:
        raise B2BCreditNotFoundError("insurance policy not found")
    if policy.status != "active":
        raise B2BCreditStateError("claims require an active insurance policy")
    invoice = (
        await db.execute(
            select(B2BInvoice).where(
                B2BInvoice.workspace_id == workspace_id,
                B2BInvoice.id == _uuid(invoice_id),
            )
        )
    ).scalar_one_or_none()
    if invoice is None:
        raise B2BCreditNotFoundError("invoice not found")
    if invoice.agent_id != policy.agent_id:
        raise B2BCreditStateError("policy and invoice must belong to the same customer")
    if invoice.currency != policy.currency:
        raise B2BCreditStateError("policy and invoice currencies must match")
    amount = _money(claimed_amount)
    if amount <= ZERO:
        raise B2BCreditError("claimed_amount must be positive")
    if amount > _money(invoice.balance_due):
        raise B2BCreditStateError("claimed amount exceeds invoice balance due")
    if amount > _money(policy.coverage_limit):
        raise B2BCreditStateError("claimed amount exceeds policy coverage limit")
    if not reason.strip():
        raise B2BCreditError("claim reason is required")

    claim = B2BCreditInsuranceClaim(
        workspace_id=workspace_id,
        policy_id=policy.id,
        invoice_id=invoice.id,
        agent_id=policy.agent_id,
        claim_number=_number("CLM"),
        status="draft",
        claimed_amount=amount,
        recovered_amount=ZERO,
        currency=policy.currency,
        reason=reason.strip(),
        evidence=evidence or {},
        created_by=actor,
    )
    db.add(claim)
    await db.flush()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_credit_insurance_claim.created",
        entity_type="b2b_credit_insurance_claim",
        entity_id=str(claim.id),
        payload={
            "claim_number": claim.claim_number,
            "policy_id": str(policy.id),
            "invoice_id": str(invoice.id),
            "claimed_amount": str(claim.claimed_amount),
            "currency": claim.currency,
            "actor": actor,
        },
        trace_id=trace_id,
    )
    await db.commit()
    return (
        await db.execute(
            select(B2BCreditInsuranceClaim).where(
                B2BCreditInsuranceClaim.id == claim.id
            )
        )
    ).scalar_one()


async def list_insurance_claims(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    status: str | None = None,
    agent_id: str | UUID | None = None,
) -> list[B2BCreditInsuranceClaim]:
    query = select(B2BCreditInsuranceClaim).where(
        B2BCreditInsuranceClaim.workspace_id == workspace_id
    )
    if status:
        query = query.where(B2BCreditInsuranceClaim.status == status)
    if agent_id:
        query = query.where(B2BCreditInsuranceClaim.agent_id == _uuid(agent_id))
    rows = (
        await db.execute(query.order_by(B2BCreditInsuranceClaim.created_at.desc()))
    ).scalars().all()
    return list(rows)


async def transition_insurance_claim(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    claim_id: str | UUID,
    new_status: str,
    actor: str,
    reason: str | None = None,
    recovered_amount: Decimal | None = None,
    settlement_reference: str | None = None,
    trace_id: str | None = None,
) -> B2BCreditInsuranceClaim:
    claim = (
        await db.execute(
            select(B2BCreditInsuranceClaim)
            .where(
                B2BCreditInsuranceClaim.workspace_id == workspace_id,
                B2BCreditInsuranceClaim.id == _uuid(claim_id),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if claim is None:
        raise B2BCreditNotFoundError("insurance claim not found")
    if new_status not in CLAIM_TRANSITIONS.get(claim.status, set()):
        raise B2BCreditStateError(
            f"invalid insurance claim transition: {claim.status} -> {new_status}"
        )
    now = datetime.now(timezone.utc)
    if new_status == "submitted":
        claim.status = "submitted"
        claim.submitted_by = actor
        claim.submitted_at = now
    elif new_status == "approved":
        claim.status = "approved"
        claim.decided_by = actor
        claim.decided_at = now
    elif new_status == "rejected":
        if not reason or not reason.strip():
            raise B2BCreditError("rejection reason is required")
        claim.status = "rejected"
        claim.decided_by = actor
        claim.decided_at = now
        claim.rejection_reason = reason.strip()
    elif new_status == "settled":
        if not settlement_reference or not settlement_reference.strip():
            raise B2BCreditError("settlement_reference is required")
        recovered = (
            _money(recovered_amount)
            if recovered_amount is not None
            else _money(claim.claimed_amount)
        )
        if recovered <= ZERO or recovered > _money(claim.claimed_amount):
            raise B2BCreditError(
                "recovered_amount must be positive and no greater than claimed_amount"
            )
        claim.status = "settled"
        claim.recovered_amount = recovered
        claim.settled_by = actor
        claim.settled_at = now
        claim.settlement_reference = settlement_reference.strip()
    await db.flush()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type=f"b2b_credit_insurance_claim.{new_status}",
        entity_type="b2b_credit_insurance_claim",
        entity_id=str(claim.id),
        payload={
            "claim_number": claim.claim_number,
            "status": claim.status,
            "recovered_amount": str(claim.recovered_amount),
            "reason": reason,
            "actor": actor,
        },
        trace_id=trace_id,
    )
    await db.commit()
    return (
        await db.execute(
            select(B2BCreditInsuranceClaim).where(
                B2BCreditInsuranceClaim.id == claim.id
            )
        )
    ).scalar_one()
