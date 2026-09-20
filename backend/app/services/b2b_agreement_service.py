"""B2B agent agreements, target progress, and rebate accruals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from itertools import pairwise
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002
from sqlalchemy.orm import selectinload

from app.models.b2b import B2BAgent, B2BOrder
from app.models.b2b_agreements import (
    B2BAgentAgreement,
    B2BRebateAccrual,
    B2BRebateTier,
)
from app.models.b2b_finance import B2BInvoice, B2BReceivableEntry
from app.services import currency_service, event_service

MONEY = Decimal("0.01")
HUNDRED = Decimal("100")
ZERO = Decimal("0.00")
EDITABLE_AGREEMENT_STATUSES = {"draft", "rejected"}
EDITABLE_ACCRUAL_STATUSES = {"draft", "rejected"}


class B2BAgreementError(ValueError):
    """Base class for agreement and rebate domain errors."""


class B2BAgreementNotFoundError(B2BAgreementError):
    """Raised when a scoped agreement, tier, or accrual is missing."""


class B2BAgreementConflictError(B2BAgreementError):
    """Raised when a unique or overlap constraint is violated."""


class B2BAgreementStateError(B2BAgreementError):
    """Raised when an operation is invalid for the current state."""


@dataclass(frozen=True)
class QualificationResult:
    amount: Decimal
    included_record_count: int
    excluded_record_count: int
    missing_rate_currencies: tuple[str, ...]


def _uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _money(value: Decimal | str | int | float) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def _number(prefix: str) -> str:
    now = datetime.now(timezone.utc)
    return f"{prefix}-{now.strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"


def _normalize_currency(value: str) -> str:
    return currency_service.normalize_currency_code(value)


def effective_agreement_status(
    agreement: B2BAgentAgreement,
    *,
    as_of: date | None = None,
) -> str:
    effective_date = as_of or date.today()
    if agreement.status == "active" and effective_date > agreement.effective_to:
        return "expired"
    return agreement.status


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
        raise B2BAgreementNotFoundError("agent not found")
    return agent


async def get_agreement(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    agreement_id: str | UUID,
    for_update: bool = False,
) -> B2BAgentAgreement | None:
    statement = (
        select(B2BAgentAgreement)
        .where(
            B2BAgentAgreement.workspace_id == workspace_id,
            B2BAgentAgreement.id == _uuid(agreement_id),
        )
        .options(
            selectinload(B2BAgentAgreement.tiers),
            selectinload(B2BAgentAgreement.accruals),
        )
        .execution_options(populate_existing=True)
    )
    if for_update:
        statement = statement.with_for_update()
    return (await db.execute(statement)).scalar_one_or_none()


async def _require_agreement(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    agreement_id: str | UUID,
    for_update: bool = False,
) -> B2BAgentAgreement:
    agreement = await get_agreement(
        db,
        workspace_id=workspace_id,
        agreement_id=agreement_id,
        for_update=for_update,
    )
    if agreement is None:
        raise B2BAgreementNotFoundError("agreement not found")
    return agreement


async def _require_accrual(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    accrual_id: str | UUID,
    for_update: bool = False,
) -> B2BRebateAccrual:
    statement = (
        select(B2BRebateAccrual)
        .where(
            B2BRebateAccrual.workspace_id == workspace_id,
            B2BRebateAccrual.id == _uuid(accrual_id),
        )
        .options(selectinload(B2BRebateAccrual.agreement))
        .execution_options(populate_existing=True)
    )
    if for_update:
        statement = statement.with_for_update()
    accrual = (await db.execute(statement)).scalar_one_or_none()
    if accrual is None:
        raise B2BAgreementNotFoundError("rebate accrual not found")
    return accrual


async def create_agreement(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    agent_id: str | UUID,
    name: str,
    currency: str,
    effective_from: date,
    effective_to: date,
    target_amount: Decimal,
    qualification_basis: str,
    calculation_method: str,
    created_by: str,
    notes: str | None = None,
) -> B2BAgentAgreement:
    agent = await _get_agent(db, workspace_id=workspace_id, agent_id=agent_id)
    if effective_to <= effective_from:
        raise B2BAgreementError("effective_to must be after effective_from")
    if qualification_basis not in {"ordered", "invoiced", "paid"}:
        raise B2BAgreementError("unsupported qualification basis")
    if calculation_method != "retroactive":
        raise B2BAgreementError("only retroactive rebates are supported")
    normalized_target = _money(target_amount)
    if normalized_target <= ZERO:
        raise B2BAgreementError("target amount must be positive")

    agreement = B2BAgentAgreement(
        workspace_id=workspace_id,
        agreement_number=_number("AGR"),
        agent_id=agent.id,
        name=name.strip(),
        status="draft",
        currency=_normalize_currency(currency),
        effective_from=effective_from,
        effective_to=effective_to,
        target_amount=normalized_target,
        qualification_basis=qualification_basis,
        calculation_method=calculation_method,
        notes=notes,
        created_by=created_by,
    )
    db.add(agreement)
    await db.commit()
    await db.refresh(agreement)
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_agreement.created",
        entity_type="b2b_agent_agreement",
        entity_id=str(agreement.id),
        payload={
            "agreement_number": agreement.agreement_number,
            "agent_id": str(agent.id),
            "actor": created_by,
            "target_amount": str(agreement.target_amount),
            "currency": agreement.currency,
        },
    )
    return await _require_agreement(
        db,
        workspace_id=workspace_id,
        agreement_id=agreement.id,
    )


async def update_agreement(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    agreement_id: str | UUID,
    actor: str,
    **changes: object,
) -> B2BAgentAgreement:
    agreement = await _require_agreement(
        db,
        workspace_id=workspace_id,
        agreement_id=agreement_id,
        for_update=True,
    )
    if agreement.status not in EDITABLE_AGREEMENT_STATUSES:
        raise B2BAgreementStateError(
            "only draft or rejected agreements can be edited"
        )
    if "currency" in changes and agreement.accruals:
        raise B2BAgreementStateError(
            "currency cannot change after rebate calculations exist"
        )

    next_from = changes.get("effective_from", agreement.effective_from)
    next_to = changes.get("effective_to", agreement.effective_to)
    if not isinstance(next_from, date) or not isinstance(next_to, date):
        raise B2BAgreementError("invalid agreement period")
    if next_to <= next_from:
        raise B2BAgreementError("effective_to must be after effective_from")

    for field, value in changes.items():
        if value is None:
            continue
        if field == "currency":
            value = _normalize_currency(str(value))
        elif field == "target_amount":
            value = _money(str(value))
            if value <= ZERO:
                raise B2BAgreementError("target amount must be positive")
        elif field == "qualification_basis":
            if value not in {"ordered", "invoiced", "paid"}:
                raise B2BAgreementError("unsupported qualification basis")
        elif field == "calculation_method":
            if value != "retroactive":
                raise B2BAgreementError("only retroactive rebates are supported")
        elif field == "name":
            value = str(value).strip()
        setattr(agreement, field, value)

    agreement.rejection_reason = None
    await db.commit()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_agreement.updated",
        entity_type="b2b_agent_agreement",
        entity_id=str(agreement.id),
        payload={"actor": actor, "fields": sorted(changes)},
    )
    return await _require_agreement(
        db,
        workspace_id=workspace_id,
        agreement_id=agreement.id,
    )


async def list_agreements(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    page: int = 1,
    page_size: int = 50,
    status: str | None = None,
    agent_id: str | UUID | None = None,
    search: str | None = None,
) -> tuple[list[B2BAgentAgreement], int]:
    query = select(B2BAgentAgreement).where(
        B2BAgentAgreement.workspace_id == workspace_id
    )
    count_query = select(func.count(B2BAgentAgreement.id)).where(
        B2BAgentAgreement.workspace_id == workspace_id
    )
    if status:
        query = query.where(B2BAgentAgreement.status == status)
        count_query = count_query.where(B2BAgentAgreement.status == status)
    if agent_id:
        parsed_agent_id = _uuid(agent_id)
        query = query.where(B2BAgentAgreement.agent_id == parsed_agent_id)
        count_query = count_query.where(B2BAgentAgreement.agent_id == parsed_agent_id)
    if search:
        pattern = f"%{search.strip()}%"
        condition = or_(
            B2BAgentAgreement.name.ilike(pattern),
            B2BAgentAgreement.agreement_number.ilike(pattern),
        )
        query = query.where(condition)
        count_query = count_query.where(condition)

    total = int((await db.execute(count_query)).scalar_one())
    rows = (
        await db.execute(
            query.options(
                selectinload(B2BAgentAgreement.tiers),
                selectinload(B2BAgentAgreement.accruals),
            )
            .order_by(B2BAgentAgreement.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return list(rows), total


def _normalized_tiers(
    tiers: list[B2BRebateTier],
    *,
    exclude_tier_id: UUID | None = None,
) -> list[tuple[Decimal, Decimal | None]]:
    values = [
        (_money(tier.min_sales_amount), (
            _money(tier.max_sales_amount)
            if tier.max_sales_amount is not None
            else None
        ))
        for tier in tiers
        if exclude_tier_id is None or tier.id != exclude_tier_id
    ]
    return sorted(values, key=lambda item: item[0])


def _validate_no_overlap(
    tiers: list[tuple[Decimal, Decimal | None]],
) -> None:
    for previous, current in pairwise(tiers):
        previous_max = previous[1]
        if previous_max is None or current[0] < previous_max:
            raise B2BAgreementConflictError("rebate tiers overlap")


def _validate_complete_schedule(tiers: list[B2BRebateTier]) -> None:
    if not tiers:
        raise B2BAgreementStateError("at least one rebate tier is required")
    values = _normalized_tiers(tiers)
    if values[0][0] != ZERO:
        raise B2BAgreementStateError("first rebate tier must start at zero")
    for previous, current in pairwise(values):
        if previous[1] is None:
            raise B2BAgreementStateError("only the last rebate tier can be open-ended")
        if current[0] != previous[1]:
            raise B2BAgreementStateError("rebate tiers must be contiguous without gaps")
    if values[-1][1] is not None:
        raise B2BAgreementStateError("last rebate tier must be open-ended")


async def create_rebate_tier(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    agreement_id: str | UUID,
    min_sales_amount: Decimal,
    max_sales_amount: Decimal | None,
    rebate_percent: Decimal,
) -> B2BRebateTier:
    agreement = await _require_agreement(
        db,
        workspace_id=workspace_id,
        agreement_id=agreement_id,
        for_update=True,
    )
    if agreement.status not in EDITABLE_AGREEMENT_STATUSES:
        raise B2BAgreementStateError(
            "only draft or rejected agreements can change rebate tiers"
        )
    normalized_min = _money(min_sales_amount)
    normalized_max = (
        _money(max_sales_amount) if max_sales_amount is not None else None
    )
    normalized_percent = Decimal(str(rebate_percent)).quantize(
        MONEY,
        rounding=ROUND_HALF_UP,
    )
    if normalized_min < ZERO:
        raise B2BAgreementError("min_sales_amount cannot be negative")
    if normalized_max is not None and normalized_max <= normalized_min:
        raise B2BAgreementError(
            "max_sales_amount must be greater than min_sales_amount"
        )
    if normalized_percent < ZERO or normalized_percent > HUNDRED:
        raise B2BAgreementError("rebate_percent must be between 0 and 100")

    candidate = (normalized_min, normalized_max)
    existing = _normalized_tiers(agreement.tiers)
    combined = sorted([*existing, candidate], key=lambda item: item[0])
    _validate_no_overlap(combined)

    tier = B2BRebateTier(
        workspace_id=workspace_id,
        agreement_id=agreement.id,
        min_sales_amount=normalized_min,
        max_sales_amount=normalized_max,
        rebate_percent=normalized_percent,
    )
    db.add(tier)
    await db.commit()
    await db.refresh(tier)
    return tier


async def update_rebate_tier(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    agreement_id: str | UUID,
    tier_id: str | UUID,
    min_sales_amount: Decimal | None = None,
    max_sales_amount: Decimal | None = None,
    max_sales_amount_set: bool = False,
    rebate_percent: Decimal | None = None,
) -> B2BRebateTier:
    agreement = await _require_agreement(
        db,
        workspace_id=workspace_id,
        agreement_id=agreement_id,
        for_update=True,
    )
    if agreement.status not in EDITABLE_AGREEMENT_STATUSES:
        raise B2BAgreementStateError(
            "only draft or rejected agreements can change rebate tiers"
        )
    tier = next((row for row in agreement.tiers if row.id == _uuid(tier_id)), None)
    if tier is None:
        raise B2BAgreementNotFoundError("rebate tier not found")

    next_min = _money(
        min_sales_amount if min_sales_amount is not None else tier.min_sales_amount
    )
    if max_sales_amount_set:
        next_max = _money(max_sales_amount) if max_sales_amount is not None else None
    else:
        next_max = (
            _money(tier.max_sales_amount)
            if tier.max_sales_amount is not None
            else None
        )
    next_percent = Decimal(
        str(
            rebate_percent
            if rebate_percent is not None
            else tier.rebate_percent
        )
    ).quantize(MONEY, rounding=ROUND_HALF_UP)
    if next_min < ZERO:
        raise B2BAgreementError("min_sales_amount cannot be negative")
    if next_max is not None and next_max <= next_min:
        raise B2BAgreementError(
            "max_sales_amount must be greater than min_sales_amount"
        )
    if next_percent < ZERO or next_percent > HUNDRED:
        raise B2BAgreementError("rebate_percent must be between 0 and 100")

    combined = sorted(
        [*_normalized_tiers(agreement.tiers, exclude_tier_id=tier.id), (next_min, next_max)],
        key=lambda item: item[0],
    )
    _validate_no_overlap(combined)

    tier.min_sales_amount = next_min
    tier.max_sales_amount = next_max
    tier.rebate_percent = next_percent
    await db.commit()
    await db.refresh(tier)
    return tier


async def delete_rebate_tier(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    agreement_id: str | UUID,
    tier_id: str | UUID,
) -> None:
    agreement = await _require_agreement(
        db,
        workspace_id=workspace_id,
        agreement_id=agreement_id,
        for_update=True,
    )
    if agreement.status not in EDITABLE_AGREEMENT_STATUSES:
        raise B2BAgreementStateError(
            "only draft or rejected agreements can change rebate tiers"
        )
    tier = next((row for row in agreement.tiers if row.id == _uuid(tier_id)), None)
    if tier is None:
        raise B2BAgreementNotFoundError("rebate tier not found")
    await db.delete(tier)
    await db.commit()


async def submit_agreement(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    agreement_id: str | UUID,
    actor: str,
) -> B2BAgentAgreement:
    agreement = await _require_agreement(
        db,
        workspace_id=workspace_id,
        agreement_id=agreement_id,
        for_update=True,
    )
    if agreement.status not in EDITABLE_AGREEMENT_STATUSES:
        raise B2BAgreementStateError(
            "only draft or rejected agreements can be submitted"
        )
    _validate_complete_schedule(agreement.tiers)
    agreement.status = "pending_approval"
    agreement.submitted_by = actor
    agreement.submitted_at = datetime.now(timezone.utc)
    agreement.rejection_reason = None
    await db.commit()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_agreement.submitted",
        entity_type="b2b_agent_agreement",
        entity_id=str(agreement.id),
        payload={"actor": actor, "agreement_number": agreement.agreement_number},
    )
    return await _require_agreement(
        db,
        workspace_id=workspace_id,
        agreement_id=agreement.id,
    )


async def approve_agreement(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    agreement_id: str | UUID,
    actor: str,
) -> B2BAgentAgreement:
    agreement = await _require_agreement(
        db,
        workspace_id=workspace_id,
        agreement_id=agreement_id,
        for_update=True,
    )
    if agreement.status != "pending_approval":
        raise B2BAgreementStateError(
            "only pending_approval agreements can be approved"
        )
    if agreement.submitted_by and agreement.submitted_by == actor:
        raise B2BAgreementStateError(
            "submitter cannot approve the same agreement"
        )
    _validate_complete_schedule(agreement.tiers)

    # Serialize approvals for one agent so concurrent requests cannot create
    # overlapping active agreements.
    await db.execute(
        select(B2BAgent.id)
        .where(
            B2BAgent.workspace_id == workspace_id,
            B2BAgent.id == agreement.agent_id,
        )
        .with_for_update()
    )
    current_actives = (
        await db.execute(
            select(B2BAgentAgreement)
            .where(
                B2BAgentAgreement.workspace_id == workspace_id,
                B2BAgentAgreement.agent_id == agreement.agent_id,
                B2BAgentAgreement.status == "active",
                B2BAgentAgreement.id != agreement.id,
                B2BAgentAgreement.effective_from <= agreement.effective_to,
                B2BAgentAgreement.effective_to >= agreement.effective_from,
            )
            .with_for_update()
        )
    ).scalars().all()
    for current in current_actives:
        current.status = "expired"

    # Flush expirations before activating the replacement. This keeps the
    # operation correct even if a database-level active uniqueness index exists.
    await db.flush()
    agreement.status = "active"
    agreement.approved_by = actor
    agreement.approved_at = datetime.now(timezone.utc)
    agreement.rejection_reason = None
    await db.commit()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_agreement.approved",
        entity_type="b2b_agent_agreement",
        entity_id=str(agreement.id),
        payload={
            "actor": actor,
            "agreement_number": agreement.agreement_number,
            "expired_agreement_ids": [str(row.id) for row in current_actives],
        },
    )
    return await _require_agreement(
        db,
        workspace_id=workspace_id,
        agreement_id=agreement.id,
    )


async def reject_agreement(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    agreement_id: str | UUID,
    actor: str,
    reason: str,
) -> B2BAgentAgreement:
    agreement = await _require_agreement(
        db,
        workspace_id=workspace_id,
        agreement_id=agreement_id,
        for_update=True,
    )
    if agreement.status != "pending_approval":
        raise B2BAgreementStateError(
            "only pending_approval agreements can be rejected"
        )
    if agreement.submitted_by and agreement.submitted_by == actor:
        raise B2BAgreementStateError(
            "submitter cannot reject the same agreement"
        )
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise B2BAgreementError("rejection reason is required")
    agreement.status = "rejected"
    agreement.rejection_reason = normalized_reason
    await db.commit()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_agreement.rejected",
        entity_type="b2b_agent_agreement",
        entity_id=str(agreement.id),
        payload={"actor": actor, "reason": normalized_reason},
    )
    return await _require_agreement(
        db,
        workspace_id=workspace_id,
        agreement_id=agreement.id,
    )


async def terminate_agreement(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    agreement_id: str | UUID,
    actor: str,
    reason: str,
) -> B2BAgentAgreement:
    agreement = await _require_agreement(
        db,
        workspace_id=workspace_id,
        agreement_id=agreement_id,
        for_update=True,
    )
    if agreement.status != "active":
        raise B2BAgreementStateError("only active agreements can be terminated")
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise B2BAgreementError("termination reason is required")
    agreement.status = "terminated"
    agreement.terminated_by = actor
    agreement.terminated_at = datetime.now(timezone.utc)
    agreement.termination_reason = normalized_reason
    await db.commit()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_agreement.terminated",
        entity_type="b2b_agent_agreement",
        entity_id=str(agreement.id),
        payload={"actor": actor, "reason": normalized_reason},
    )
    return await _require_agreement(
        db,
        workspace_id=workspace_id,
        agreement_id=agreement.id,
    )


async def _qualifying_sales(
    db: AsyncSession,
    *,
    agreement: B2BAgentAgreement,
    period_start: date,
    period_end: date,
) -> QualificationResult:
    if period_end < period_start:
        return QualificationResult(
            amount=ZERO,
            included_record_count=0,
            excluded_record_count=0,
            missing_rate_currencies=(),
        )

    start_at = datetime.combine(period_start, time.min, tzinfo=timezone.utc)
    end_at = datetime.combine(
        period_end + timedelta(days=1),
        time.min,
        tzinfo=timezone.utc,
    )

    if agreement.qualification_basis == "ordered":
        rows = (
            await db.execute(
                select(
                    B2BOrder.id,
                    B2BOrder.total,
                    B2BOrder.currency,
                    B2BOrder.created_at,
                ).where(
                    B2BOrder.workspace_id == agreement.workspace_id,
                    B2BOrder.agent_id == agreement.agent_id,
                    B2BOrder.status != "cancelled",
                    B2BOrder.created_at >= start_at,
                    B2BOrder.created_at < end_at,
                )
            )
        ).all()
        facts = [
            (row[0], row[1], row[2], row[3].date())
            for row in rows
        ]
    elif agreement.qualification_basis == "invoiced":
        rows = (
            await db.execute(
                select(
                    B2BInvoice.id,
                    B2BInvoice.total,
                    B2BInvoice.currency,
                    B2BInvoice.issue_date,
                ).where(
                    B2BInvoice.workspace_id == agreement.workspace_id,
                    B2BInvoice.agent_id == agreement.agent_id,
                    B2BInvoice.status.not_in({"draft", "void"}),
                    B2BInvoice.issue_date >= period_start,
                    B2BInvoice.issue_date <= period_end,
                )
            )
        ).all()
        facts = [
            (row[0], row[1], row[2], row[3])
            for row in rows
        ]
    else:
        rows = (
            await db.execute(
                select(
                    B2BReceivableEntry.id,
                    B2BReceivableEntry.amount,
                    B2BReceivableEntry.currency,
                    B2BReceivableEntry.occurred_at,
                ).where(
                    B2BReceivableEntry.workspace_id == agreement.workspace_id,
                    B2BReceivableEntry.agent_id == agreement.agent_id,
                    B2BReceivableEntry.entry_type == "payment",
                    B2BReceivableEntry.occurred_at >= start_at,
                    B2BReceivableEntry.occurred_at < end_at,
                )
            )
        ).all()
        facts = [
            (row[0], abs(Decimal(row[1])), row[2], row[3].date())
            for row in rows
        ]

    total = ZERO
    included_count = 0
    excluded_count = 0
    missing_currencies: set[str] = set()
    rate_cache: dict[tuple[str, str, date], object] = {}
    for _record_id, amount, source_currency, occurred_on in facts:
        try:
            converted = await currency_service.convert_amount(
                db,
                workspace_id=agreement.workspace_id,
                amount=Decimal(amount),
                base_currency=source_currency,
                quote_currency=agreement.currency,
                as_of=occurred_on,
                rate_cache=rate_cache,  # type: ignore[arg-type]
            )
        except currency_service.ExchangeRateNotFoundError:
            excluded_count += 1
            missing_currencies.add(str(source_currency).upper())
            continue
        total += converted
        included_count += 1

    return QualificationResult(
        amount=_money(total),
        included_record_count=included_count,
        excluded_record_count=excluded_count,
        missing_rate_currencies=tuple(sorted(missing_currencies)),
    )


def _resolve_rebate_tier(
    tiers: list[B2BRebateTier],
    qualifying_sales: Decimal,
) -> B2BRebateTier | None:
    matched: B2BRebateTier | None = None
    for tier in sorted(tiers, key=lambda row: row.min_sales_amount):
        if Decimal(tier.min_sales_amount) <= qualifying_sales:
            matched = tier
        else:
            break
    return matched


def _next_rebate_tier(
    tiers: list[B2BRebateTier],
    qualifying_sales: Decimal,
) -> B2BRebateTier | None:
    candidates = [
        tier
        for tier in tiers
        if Decimal(tier.min_sales_amount) > qualifying_sales
    ]
    return min(candidates, key=lambda row: row.min_sales_amount) if candidates else None


async def agreement_progress(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    agreement_id: str | UUID,
    as_of: date | None = None,
) -> dict[str, object]:
    agreement = await _require_agreement(
        db,
        workspace_id=workspace_id,
        agreement_id=agreement_id,
    )
    if not agreement.tiers:
        raise B2BAgreementStateError("agreement has no rebate tiers")
    effective_date = as_of or date.today()
    result = await _qualifying_sales(
        db,
        agreement=agreement,
        period_start=agreement.effective_from,
        period_end=min(effective_date, agreement.effective_to),
    )
    target = Decimal(agreement.target_amount)
    sales = result.amount
    achievement = (
        (sales / target * HUNDRED).quantize(MONEY, rounding=ROUND_HALF_UP)
        if target > ZERO
        else ZERO
    )
    current_tier = _resolve_rebate_tier(agreement.tiers, sales)
    next_tier = _next_rebate_tier(agreement.tiers, sales)
    current_percent = (
        Decimal(current_tier.rebate_percent) if current_tier else ZERO
    )
    projected_rebate = _money(sales * current_percent / HUNDRED)
    return {
        "agreement_id": str(agreement.id),
        "as_of": effective_date,
        "period_start": agreement.effective_from,
        "period_end": agreement.effective_to,
        "currency": agreement.currency,
        "qualification_basis": agreement.qualification_basis,
        "target_amount": target,
        "qualifying_sales": sales,
        "achievement_percent": achievement,
        "remaining_amount": max(target - sales, ZERO),
        "current_tier_id": str(current_tier.id) if current_tier else None,
        "current_rebate_percent": current_percent,
        "projected_rebate_amount": projected_rebate,
        "next_tier_min_sales": (
            Decimal(next_tier.min_sales_amount) if next_tier else None
        ),
        "amount_to_next_tier": (
            max(Decimal(next_tier.min_sales_amount) - sales, ZERO)
            if next_tier
            else None
        ),
        "days_remaining": max((agreement.effective_to - effective_date).days, 0),
        "included_record_count": result.included_record_count,
        "excluded_record_count": result.excluded_record_count,
        "missing_rate_currencies": list(result.missing_rate_currencies),
    }


async def calculate_rebate_accrual(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    agreement_id: str | UUID,
    period_start: date,
    period_end: date,
    actor: str,
) -> B2BRebateAccrual:
    agreement = await _require_agreement(
        db,
        workspace_id=workspace_id,
        agreement_id=agreement_id,
        for_update=True,
    )
    if agreement.status != "active":
        raise B2BAgreementStateError("only active agreements can calculate rebates")
    if period_end < period_start:
        raise B2BAgreementError("period_end cannot be before period_start")
    if period_start < agreement.effective_from or period_end > agreement.effective_to:
        raise B2BAgreementError("rebate period must be inside the agreement period")
    if not agreement.tiers:
        raise B2BAgreementStateError("agreement has no rebate tiers")
    _validate_complete_schedule(agreement.tiers)

    existing = (
        await db.execute(
            select(B2BRebateAccrual)
            .where(
                B2BRebateAccrual.workspace_id == workspace_id,
                B2BRebateAccrual.agreement_id == agreement.id,
                B2BRebateAccrual.period_start == period_start,
                B2BRebateAccrual.period_end == period_end,
            )
            .options(selectinload(B2BRebateAccrual.agreement))
            .execution_options(populate_existing=True)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if existing is not None and existing.status not in EDITABLE_ACCRUAL_STATUSES:
        return existing

    qualification = await _qualifying_sales(
        db,
        agreement=agreement,
        period_start=period_start,
        period_end=period_end,
    )
    tier = _resolve_rebate_tier(agreement.tiers, qualification.amount)
    if tier is None:
        raise B2BAgreementStateError("no rebate tier matches qualifying sales")
    percent = Decimal(tier.rebate_percent)
    amount = _money(qualification.amount * percent / HUNDRED)
    evidence = {
        "agreement_number": agreement.agreement_number,
        "target_amount": str(agreement.target_amount),
        "qualification_basis": agreement.qualification_basis,
        "included_record_count": qualification.included_record_count,
        "excluded_record_count": qualification.excluded_record_count,
        "missing_rate_currencies": list(qualification.missing_rate_currencies),
        "matched_tier": {
            "id": str(tier.id),
            "min_sales_amount": str(tier.min_sales_amount),
            "max_sales_amount": (
                str(tier.max_sales_amount)
                if tier.max_sales_amount is not None
                else None
            ),
            "rebate_percent": str(tier.rebate_percent),
        },
    }

    if existing is None:
        existing = B2BRebateAccrual(
            workspace_id=workspace_id,
            accrual_number=_number("RBA"),
            agreement_id=agreement.id,
            agent_id=agreement.agent_id,
            status="draft",
            period_start=period_start,
            period_end=period_end,
            qualification_basis=agreement.qualification_basis,
            calculation_method=agreement.calculation_method,
            qualifying_sales=qualification.amount,
            rebate_percent=percent,
            rebate_amount=amount,
            currency=agreement.currency,
            evidence=evidence,
            created_by=actor,
        )
        db.add(existing)
    else:
        existing.qualifying_sales = qualification.amount
        existing.rebate_percent = percent
        existing.rebate_amount = amount
        existing.currency = agreement.currency
        existing.evidence = evidence
        existing.created_by = actor
        existing.rejection_reason = None
        existing.rejected_by = None
        existing.rejected_at = None

    await db.commit()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_rebate_accrual.calculated",
        entity_type="b2b_rebate_accrual",
        entity_id=str(existing.id),
        payload={
            "actor": actor,
            "agreement_id": str(agreement.id),
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "qualifying_sales": str(existing.qualifying_sales),
            "rebate_amount": str(existing.rebate_amount),
        },
    )
    return await _require_accrual(
        db,
        workspace_id=workspace_id,
        accrual_id=existing.id,
    )


async def list_rebate_accruals(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    page: int = 1,
    page_size: int = 50,
    status: str | None = None,
    agreement_id: str | UUID | None = None,
    agent_id: str | UUID | None = None,
) -> tuple[list[B2BRebateAccrual], int]:
    query = select(B2BRebateAccrual).where(
        B2BRebateAccrual.workspace_id == workspace_id
    )
    count_query = select(func.count(B2BRebateAccrual.id)).where(
        B2BRebateAccrual.workspace_id == workspace_id
    )
    if status:
        query = query.where(B2BRebateAccrual.status == status)
        count_query = count_query.where(B2BRebateAccrual.status == status)
    if agreement_id:
        parsed = _uuid(agreement_id)
        query = query.where(B2BRebateAccrual.agreement_id == parsed)
        count_query = count_query.where(B2BRebateAccrual.agreement_id == parsed)
    if agent_id:
        parsed = _uuid(agent_id)
        query = query.where(B2BRebateAccrual.agent_id == parsed)
        count_query = count_query.where(B2BRebateAccrual.agent_id == parsed)
    total = int((await db.execute(count_query)).scalar_one())
    rows = (
        await db.execute(
            query.options(selectinload(B2BRebateAccrual.agreement))
            .order_by(B2BRebateAccrual.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return list(rows), total


async def submit_rebate_accrual(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    accrual_id: str | UUID,
    actor: str,
) -> B2BRebateAccrual:
    accrual = await _require_accrual(
        db,
        workspace_id=workspace_id,
        accrual_id=accrual_id,
        for_update=True,
    )
    if accrual.status not in EDITABLE_ACCRUAL_STATUSES:
        raise B2BAgreementStateError(
            "only draft or rejected accruals can be submitted"
        )
    if Decimal(accrual.rebate_amount) <= ZERO:
        raise B2BAgreementStateError(
            "rebate amount must be positive before submission"
        )
    accrual.status = "pending_approval"
    accrual.submitted_by = actor
    accrual.submitted_at = datetime.now(timezone.utc)
    accrual.rejection_reason = None
    accrual.rejected_by = None
    accrual.rejected_at = None
    await db.commit()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_rebate_accrual.submitted",
        entity_type="b2b_rebate_accrual",
        entity_id=str(accrual.id),
        payload={"actor": actor, "rebate_amount": str(accrual.rebate_amount)},
    )
    return await _require_accrual(
        db,
        workspace_id=workspace_id,
        accrual_id=accrual.id,
    )


async def approve_rebate_accrual(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    accrual_id: str | UUID,
    actor: str,
) -> B2BRebateAccrual:
    accrual = await _require_accrual(
        db,
        workspace_id=workspace_id,
        accrual_id=accrual_id,
        for_update=True,
    )
    if accrual.status == "approved":
        return accrual
    if accrual.status != "pending_approval":
        raise B2BAgreementStateError(
            "only pending_approval accruals can be approved"
        )
    if accrual.submitted_by and accrual.submitted_by == actor:
        raise B2BAgreementStateError(
            "submitter cannot approve the same rebate accrual"
        )
    accrual.status = "approved"
    accrual.approved_by = actor
    accrual.approved_at = datetime.now(timezone.utc)
    await db.commit()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_rebate_accrual.approved",
        entity_type="b2b_rebate_accrual",
        entity_id=str(accrual.id),
        payload={"actor": actor, "rebate_amount": str(accrual.rebate_amount)},
    )
    return await _require_accrual(
        db,
        workspace_id=workspace_id,
        accrual_id=accrual.id,
    )


async def reject_rebate_accrual(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    accrual_id: str | UUID,
    actor: str,
    reason: str,
) -> B2BRebateAccrual:
    accrual = await _require_accrual(
        db,
        workspace_id=workspace_id,
        accrual_id=accrual_id,
        for_update=True,
    )
    if accrual.status != "pending_approval":
        raise B2BAgreementStateError(
            "only pending_approval accruals can be rejected"
        )
    if accrual.submitted_by and accrual.submitted_by == actor:
        raise B2BAgreementStateError(
            "submitter cannot reject the same rebate accrual"
        )
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise B2BAgreementError("rejection reason is required")
    accrual.status = "rejected"
    accrual.rejected_by = actor
    accrual.rejected_at = datetime.now(timezone.utc)
    accrual.rejection_reason = normalized_reason
    await db.commit()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_rebate_accrual.rejected",
        entity_type="b2b_rebate_accrual",
        entity_id=str(accrual.id),
        payload={"actor": actor, "reason": normalized_reason},
    )
    return await _require_accrual(
        db,
        workspace_id=workspace_id,
        accrual_id=accrual.id,
    )


async def settle_rebate_accrual(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    accrual_id: str | UUID,
    actor: str,
    settlement_reference: str,
) -> B2BRebateAccrual:
    accrual = await _require_accrual(
        db,
        workspace_id=workspace_id,
        accrual_id=accrual_id,
        for_update=True,
    )
    if accrual.status == "settled":
        return accrual
    if accrual.status != "approved":
        raise B2BAgreementStateError(
            "only approved accruals can be settled"
        )
    reference = settlement_reference.strip()
    if not reference:
        raise B2BAgreementError("settlement reference is required")
    accrual.status = "settled"
    accrual.settled_by = actor
    accrual.settled_at = datetime.now(timezone.utc)
    accrual.settlement_reference = reference
    await db.commit()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_rebate_accrual.settled",
        entity_type="b2b_rebate_accrual",
        entity_id=str(accrual.id),
        payload={
            "actor": actor,
            "settlement_reference": reference,
            "rebate_amount": str(accrual.rebate_amount),
        },
    )
    return await _require_accrual(
        db,
        workspace_id=workspace_id,
        accrual_id=accrual.id,
    )
