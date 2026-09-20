"""B2B pre-sales lifecycle from RFQ through contract and order conversion."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.b2b import B2BAgent, B2BOrder, B2BOrderItem
from app.models.b2b_sales import (
    B2BRFQ,
    B2BContract,
    B2BQuote,
    B2BQuoteItem,
    B2BRFQItem,
)
from app.models.product import Product, ProductCost
from app.services import (
    b2b_credit_service,
    b2b_pricing_service,
    consolidation_service,
    event_service,
)

MONEY = Decimal("0.01")
logger = logging.getLogger(__name__)

RFQ_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"submitted", "cancelled"},
    "submitted": {"in_review", "quoted", "cancelled"},
    "in_review": {"quoted", "lost", "cancelled"},
    "quoted": {"won", "lost"},
    "won": set(),
    "lost": set(),
    "cancelled": set(),
}

QUOTE_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"pending_approval", "cancelled"},
    "pending_approval": {"sent", "rejected", "cancelled"},
    "sent": {"accepted", "rejected", "expired", "cancelled"},
    "accepted": {"converted", "cancelled"},
    "rejected": set(),
    "expired": set(),
    "converted": set(),
    "cancelled": set(),
}

CONTRACT_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"pending_signature", "cancelled"},
    "pending_signature": {"cancelled"},
    "active": {"expired", "terminated"},
    "expired": set(),
    "terminated": set(),
    "cancelled": set(),
}


class B2BSalesStateError(ValueError):
    """Raised when an RFQ, quote, or contract transition is invalid."""


def _uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def _number(prefix: str) -> str:
    now = datetime.now(timezone.utc)
    return f"{prefix}-{now.strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"


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
        raise ValueError("agent not found")
    return agent


async def create_rfq(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    agent_id: str | UUID,
    items: list[dict],
    created_by: str,
    source: str = "manual",
    requested_currency: str = "USD",
    destination_country: str | None = None,
    incoterm: str | None = None,
    requested_delivery_date: date | None = None,
    notes: str | None = None,
) -> B2BRFQ:
    if not items:
        raise ValueError("at least one RFQ item is required")
    agent = await _get_agent(db, workspace_id=workspace_id, agent_id=agent_id)
    rfq_id = uuid4()
    rfq = B2BRFQ(
        id=rfq_id,
        workspace_id=workspace_id,
        rfq_number=_number("RFQ"),
        agent_id=agent.id,
        customer_account_id=agent.customer_account_id,
        status="draft",
        source=source,
        requested_currency=requested_currency.upper(),
        destination_country=destination_country,
        incoterm=incoterm,
        requested_delivery_date=requested_delivery_date,
        notes=notes,
        created_by=created_by,
    )
    db.add(rfq)
    for item in items:
        product = (
            await db.execute(
                select(Product).where(
                    Product.workspace_id == workspace_id,
                    Product.id == _uuid(item["product_id"]),
                )
            )
        ).scalar_one_or_none()
        if product is None:
            raise ValueError(f"product not found: {item['product_id']}")
        quantity = int(item["quantity"])
        if quantity < 1:
            raise ValueError("RFQ quantity must be at least 1")
        target_price = item.get("target_unit_price")
        db.add(
            B2BRFQItem(
                workspace_id=workspace_id,
                rfq_id=rfq_id,
                product_id=product.id,
                sku_snapshot=product.sku,
                product_name_snapshot=product.name,
                requested_quantity=quantity,
                target_unit_price=Decimal(str(target_price)) if target_price is not None else None,
                specifications=item.get("specifications") or {},
                notes=item.get("notes"),
            )
        )
    await db.commit()
    return await get_rfq(db, workspace_id=workspace_id, rfq_id=rfq.id)  # type: ignore[return-value]


async def get_rfq(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    rfq_id: str | UUID,
) -> B2BRFQ | None:
    return (
        await db.execute(
            select(B2BRFQ)
            .where(
                B2BRFQ.workspace_id == workspace_id,
                B2BRFQ.id == _uuid(rfq_id),
            )
            .options(selectinload(B2BRFQ.items))
        )
    ).scalar_one_or_none()


async def list_rfqs(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    page: int = 1,
    page_size: int = 50,
    status: str | None = None,
    agent_id: str | UUID | None = None,
) -> tuple[list[B2BRFQ], int]:
    query = select(B2BRFQ).where(B2BRFQ.workspace_id == workspace_id)
    count_query = select(func.count(B2BRFQ.id)).where(B2BRFQ.workspace_id == workspace_id)
    if status:
        query = query.where(B2BRFQ.status == status)
        count_query = count_query.where(B2BRFQ.status == status)
    if agent_id:
        query = query.where(B2BRFQ.agent_id == _uuid(agent_id))
        count_query = count_query.where(B2BRFQ.agent_id == _uuid(agent_id))
    total = (await db.execute(count_query)).scalar_one()
    rows = (
        await db.execute(
            query.options(selectinload(B2BRFQ.items))
            .order_by(B2BRFQ.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return list(rows), int(total)


async def update_rfq_status(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    rfq_id: str | UUID,
    new_status: str,
    actor: str,
    reason: str | None = None,
    trace_id: str | None = None,
) -> B2BRFQ:
    rfq = await get_rfq(db, workspace_id=workspace_id, rfq_id=rfq_id)
    if rfq is None:
        raise ValueError("RFQ not found")
    allowed = RFQ_TRANSITIONS.get(rfq.status, set())
    if new_status not in allowed:
        raise B2BSalesStateError(f"invalid RFQ transition: {rfq.status} -> {new_status}")
    old_status = rfq.status
    now = datetime.now(timezone.utc)
    rfq.status = new_status
    if new_status == "submitted":
        rfq.submitted_at = now
    if new_status in {"won", "lost", "cancelled"}:
        rfq.closed_at = now
    await db.flush()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_rfq.status_changed",
        entity_type="b2b_rfq",
        entity_id=str(rfq.id),
        payload={
            "rfq_number": rfq.rfq_number,
            "previous_status": old_status,
            "new_status": new_status,
            "actor": actor,
            "reason": reason,
        },
        trace_id=trace_id,
    )
    await db.commit()
    return await get_rfq(db, workspace_id=workspace_id, rfq_id=rfq.id)  # type: ignore[return-value]


async def create_quote_from_rfq(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    rfq_id: str | UUID,
    created_by: str,
    valid_until: date,
    payment_terms_days: int = 30,
    exchange_rate_to_base: Decimal = Decimal("1"),
    base_currency: str = "USD",
    shipping_cost: Decimal = Decimal("0"),
    tax_amount: Decimal = Decimal("0"),
    shipping_terms: str | None = None,
    notes: str | None = None,
) -> B2BQuote:
    rfq = await get_rfq(db, workspace_id=workspace_id, rfq_id=rfq_id)
    if rfq is None:
        raise ValueError("RFQ not found")
    if rfq.status not in {"submitted", "in_review"}:
        raise B2BSalesStateError("RFQ must be submitted or in_review before quoting")
    agent = await _get_agent(db, workspace_id=workspace_id, agent_id=rfq.agent_id)
    if valid_until < date.today():
        raise ValueError("quote valid_until cannot be in the past")
    if exchange_rate_to_base <= 0:
        raise ValueError("exchange rate must be positive")

    quote_id = uuid4()
    quote_items: list[B2BQuoteItem] = []
    version_ids: set[UUID] = set()
    subtotal = Decimal("0")
    discount_amount = Decimal("0")
    for rfq_item in rfq.items:
        resolved = await b2b_pricing_service.resolve_b2b_price(
            db,
            workspace_id=workspace_id,
            product_id=rfq_item.product_id,
            agent=agent,
            quantity=rfq_item.requested_quantity,
        )
        version_ids.add(resolved.price_book_version_id)
        line_subtotal = _money(resolved.unit_price * rfq_item.requested_quantity)
        line_total = line_subtotal
        subtotal += line_subtotal
        cost = (
            await db.execute(
                select(ProductCost).where(
                    ProductCost.workspace_id == workspace_id,
                    ProductCost.product_id == rfq_item.product_id,
                )
            )
        ).scalar_one_or_none()
        cost_snapshot = {}
        if cost is not None:
            cost_snapshot = {
                "currency": cost.currency,
                "total_landed_cost": str(cost.total_landed_cost),
                "total_cost": str(cost.total_cost),
                "version": cost.version,
            }
        quote_items.append(
            B2BQuoteItem(
                workspace_id=workspace_id,
                quote_id=quote_id,
                rfq_item_id=rfq_item.id,
                product_id=rfq_item.product_id,
                sku_snapshot=rfq_item.sku_snapshot,
                product_name_snapshot=rfq_item.product_name_snapshot,
                quantity=rfq_item.requested_quantity,
                unit_price=resolved.unit_price,
                discount_percent=Decimal("0"),
                line_subtotal=line_subtotal,
                line_total=line_total,
                price_tier_id=resolved.price_tier_id,
                price_source=resolved.source,
                cost_snapshot=cost_snapshot,
                specifications=rfq_item.specifications or {},
            )
        )
    if len(version_ids) != 1:
        raise B2BSalesStateError("all quote items must resolve from one price version")

    total = _money(
        subtotal
        - discount_amount
        + Decimal(shipping_cost)
        + Decimal(tax_amount)
    )
    quote = B2BQuote(
        id=quote_id,
        workspace_id=workspace_id,
        quote_number=_number("QUO"),
        version_number=1,
        rfq_id=rfq.id,
        agent_id=agent.id,
        customer_account_id=agent.customer_account_id,
        status="draft",
        currency=agent.currency,
        base_currency=base_currency.upper(),
        exchange_rate_to_base=Decimal(exchange_rate_to_base),
        price_book_version_id=next(iter(version_ids)),
        valid_until=valid_until,
        payment_terms_days=payment_terms_days,
        incoterm=rfq.incoterm,
        shipping_terms=shipping_terms,
        subtotal=_money(subtotal),
        discount_amount=_money(discount_amount),
        shipping_cost=_money(Decimal(shipping_cost)),
        tax_amount=_money(Decimal(tax_amount)),
        total=total,
        created_by=created_by,
        notes=notes,
        items=quote_items,
    )
    db.add(quote)
    await db.flush()
    await update_rfq_status(
        db,
        workspace_id=workspace_id,
        rfq_id=rfq.id,
        new_status="quoted",
        actor=created_by,
    )
    return await get_quote(db, workspace_id=workspace_id, quote_id=quote.id)  # type: ignore[return-value]


async def create_quote_version(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    quote_id: str | UUID,
    created_by: str,
    valid_until: date,
    notes: str | None = None,
) -> B2BQuote:
    source = await get_quote(db, workspace_id=workspace_id, quote_id=quote_id)
    if source is None:
        raise ValueError("quote not found")
    if source.status in {"converted", "cancelled"}:
        raise B2BSalesStateError("cannot version a converted or cancelled quote")
    next_version = (
        await db.execute(
            select(func.coalesce(func.max(B2BQuote.version_number), 0)).where(
                B2BQuote.workspace_id == workspace_id,
                B2BQuote.quote_number == source.quote_number,
            )
        )
    ).scalar_one() + 1
    quote_id_new = uuid4()
    clone = B2BQuote(
        id=quote_id_new,
        workspace_id=workspace_id,
        quote_number=source.quote_number,
        version_number=int(next_version),
        rfq_id=source.rfq_id,
        agent_id=source.agent_id,
        customer_account_id=source.customer_account_id,
        status="draft",
        currency=source.currency,
        base_currency=source.base_currency,
        exchange_rate_to_base=source.exchange_rate_to_base,
        price_book_version_id=source.price_book_version_id,
        valid_until=valid_until,
        payment_terms_days=source.payment_terms_days,
        incoterm=source.incoterm,
        shipping_terms=source.shipping_terms,
        subtotal=source.subtotal,
        discount_amount=source.discount_amount,
        shipping_cost=source.shipping_cost,
        tax_amount=source.tax_amount,
        total=source.total,
        created_by=created_by,
        notes=notes,
    )
    db.add(clone)
    for item in source.items:
        db.add(
            B2BQuoteItem(
                workspace_id=workspace_id,
                quote_id=quote_id_new,
                rfq_item_id=item.rfq_item_id,
                product_id=item.product_id,
                sku_snapshot=item.sku_snapshot,
                product_name_snapshot=item.product_name_snapshot,
                quantity=item.quantity,
                unit_price=item.unit_price,
                discount_percent=item.discount_percent,
                line_subtotal=item.line_subtotal,
                line_total=item.line_total,
                price_tier_id=item.price_tier_id,
                price_source=item.price_source,
                cost_snapshot=item.cost_snapshot,
                specifications=item.specifications,
            )
        )
    await db.commit()
    return await get_quote(db, workspace_id=workspace_id, quote_id=quote_id_new)  # type: ignore[return-value]


async def get_quote(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    quote_id: str | UUID,
    for_update: bool = False,
) -> B2BQuote | None:
    query = (
        select(B2BQuote)
        .where(
            B2BQuote.workspace_id == workspace_id,
            B2BQuote.id == _uuid(quote_id),
        )
        .execution_options(populate_existing=True)
        .options(
            selectinload(B2BQuote.items),
            selectinload(B2BQuote.contract),
            selectinload(B2BQuote.rfq),
        )
    )
    if for_update:
        query = query.with_for_update()
    return (await db.execute(query)).scalar_one_or_none()


async def list_quotes(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    page: int = 1,
    page_size: int = 50,
    status: str | None = None,
    agent_id: str | UUID | None = None,
) -> tuple[list[B2BQuote], int]:
    query = select(B2BQuote).where(B2BQuote.workspace_id == workspace_id)
    count_query = select(func.count(B2BQuote.id)).where(B2BQuote.workspace_id == workspace_id)
    if status:
        query = query.where(B2BQuote.status == status)
        count_query = count_query.where(B2BQuote.status == status)
    if agent_id:
        query = query.where(B2BQuote.agent_id == _uuid(agent_id))
        count_query = count_query.where(B2BQuote.agent_id == _uuid(agent_id))
    total = (await db.execute(count_query)).scalar_one()
    rows = (
        await db.execute(
            query.options(
                selectinload(B2BQuote.items),
                selectinload(B2BQuote.contract),
                selectinload(B2BQuote.rfq),
            )
            .order_by(B2BQuote.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return list(rows), int(total)


async def transition_quote(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    quote_id: str | UUID,
    new_status: str,
    actor: str,
    reason: str | None = None,
    trace_id: str | None = None,
) -> B2BQuote:
    quote = await get_quote(
        db,
        workspace_id=workspace_id,
        quote_id=quote_id,
        for_update=True,
    )
    if quote is None:
        raise ValueError("quote not found")
    allowed = QUOTE_TRANSITIONS.get(quote.status, set())
    if new_status not in allowed:
        raise B2BSalesStateError(f"invalid quote transition: {quote.status} -> {new_status}")
    if new_status == "pending_approval" and not quote.items:
        raise B2BSalesStateError("quote requires at least one item")
    if new_status == "sent" and quote.created_by == actor:
        raise B2BSalesStateError("quote creator cannot approve the same quote")
    if new_status == "sent" and quote.valid_until < date.today():
        raise B2BSalesStateError("expired quote cannot be sent")
    if new_status == "accepted" and quote.valid_until < date.today():
        raise B2BSalesStateError("expired quote cannot be accepted")
    if new_status == "expired" and quote.valid_until >= date.today():
        raise B2BSalesStateError("quote is not expired yet")

    previous = quote.status
    now = datetime.now(timezone.utc)
    quote.status = new_status
    if new_status == "sent":
        quote.approved_by = actor
        quote.approved_at = now
        quote.sent_at = now
    elif new_status == "accepted":
        quote.accepted_at = now
        quote.accepted_by = actor
    elif new_status == "rejected":
        quote.rejected_at = now
        quote.rejected_by = actor
        quote.rejection_reason = reason
    elif new_status == "expired":
        quote.rejection_reason = reason or "quote expired"
    await db.flush()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_quote.status_changed",
        entity_type="b2b_quote",
        entity_id=str(quote.id),
        payload={
            "quote_number": quote.quote_number,
            "version_number": quote.version_number,
            "previous_status": previous,
            "new_status": new_status,
            "actor": actor,
            "reason": reason,
        },
        trace_id=trace_id,
    )
    await db.commit()
    return await get_quote(db, workspace_id=workspace_id, quote_id=quote.id)  # type: ignore[return-value]


async def create_contract_from_quote(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    quote_id: str | UUID,
    created_by: str,
    effective_from: date,
    effective_to: date | None = None,
    document_url: str | None = None,
    terms: dict | None = None,
) -> B2BContract:
    quote = await get_quote(db, workspace_id=workspace_id, quote_id=quote_id)
    if quote is None:
        raise ValueError("quote not found")
    if quote.status != "accepted":
        raise B2BSalesStateError("contract requires an accepted quote")
    if quote.contract is not None:
        raise B2BSalesStateError("quote already has a contract")
    if effective_to is not None and effective_to < effective_from:
        raise ValueError("effective_to cannot be before effective_from")
    contract = B2BContract(
        workspace_id=workspace_id,
        contract_number=_number("CON"),
        quote_id=quote.id,
        agent_id=quote.agent_id,
        customer_account_id=quote.customer_account_id,
        status="draft",
        effective_from=effective_from,
        effective_to=effective_to,
        currency=quote.currency,
        total=quote.total,
        document_url=document_url,
        terms=terms or {},
        created_by=created_by,
    )
    db.add(contract)
    await db.commit()
    return await get_contract(db, workspace_id=workspace_id, contract_id=contract.id)  # type: ignore[return-value]


async def get_contract(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    contract_id: str | UUID,
    for_update: bool = False,
) -> B2BContract | None:
    query = (
        select(B2BContract)
        .where(
            B2BContract.workspace_id == workspace_id,
            B2BContract.id == _uuid(contract_id),
        )
        .execution_options(populate_existing=True)
        .options(selectinload(B2BContract.quote).selectinload(B2BQuote.items))
    )
    if for_update:
        query = query.with_for_update()
    return (await db.execute(query)).scalar_one_or_none()


async def list_contracts(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    page: int = 1,
    page_size: int = 50,
    status: str | None = None,
) -> tuple[list[B2BContract], int]:
    query = select(B2BContract).where(B2BContract.workspace_id == workspace_id)
    count_query = select(func.count(B2BContract.id)).where(
        B2BContract.workspace_id == workspace_id
    )
    if status:
        query = query.where(B2BContract.status == status)
        count_query = count_query.where(B2BContract.status == status)
    total = (await db.execute(count_query)).scalar_one()
    rows = (
        await db.execute(
            query.options(
                selectinload(B2BContract.quote).selectinload(B2BQuote.items)
            )
            .order_by(B2BContract.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return list(rows), int(total)


async def transition_contract(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    contract_id: str | UUID,
    new_status: str,
    actor: str,
    reason: str | None = None,
    trace_id: str | None = None,
) -> B2BContract:
    contract = await get_contract(
        db,
        workspace_id=workspace_id,
        contract_id=contract_id,
        for_update=True,
    )
    if contract is None:
        raise ValueError("contract not found")
    allowed = CONTRACT_TRANSITIONS.get(contract.status, set())
    if new_status not in allowed:
        raise B2BSalesStateError(
            f"invalid contract transition: {contract.status} -> {new_status}"
        )
    now = datetime.now(timezone.utc)
    previous = contract.status
    if new_status == "active" and (
        contract.customer_signed_at is None or contract.company_signed_at is None
    ):
        raise B2BSalesStateError("both customer and company signatures are required")
    contract.status = new_status
    if new_status == "active":
        contract.activated_at = now
    if new_status == "terminated":
        contract.terminated_at = now
    await db.flush()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_contract.status_changed",
        entity_type="b2b_contract",
        entity_id=str(contract.id),
        payload={
            "contract_number": contract.contract_number,
            "previous_status": previous,
            "new_status": new_status,
            "actor": actor,
            "reason": reason,
        },
        trace_id=trace_id,
    )
    await db.commit()
    return await get_contract(
        db,
        workspace_id=workspace_id,
        contract_id=contract.id,
    )  # type: ignore[return-value]


async def sign_contract(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    contract_id: str | UUID,
    party: str,
    signed_by: str,
    trace_id: str | None = None,
) -> B2BContract:
    """Record one party's signature and activate after both parties signed."""
    if party not in {"customer", "company"}:
        raise ValueError("party must be customer or company")
    if not signed_by.strip():
        raise ValueError("signed_by is required")
    contract = await get_contract(
        db,
        workspace_id=workspace_id,
        contract_id=contract_id,
        for_update=True,
    )
    if contract is None:
        raise ValueError("contract not found")
    if contract.status != "pending_signature":
        raise B2BSalesStateError("contract must be pending_signature before signing")

    now = datetime.now(timezone.utc)
    if party == "customer":
        if contract.customer_signed_at is not None:
            raise B2BSalesStateError("customer signature already recorded")
        contract.customer_signed_by = signed_by
        contract.customer_signed_at = now
    else:
        if contract.company_signed_at is not None:
            raise B2BSalesStateError("company signature already recorded")
        contract.company_signed_by = signed_by
        contract.company_signed_at = now

    previous = contract.status
    activated = (
        contract.customer_signed_at is not None
        and contract.company_signed_at is not None
    )
    if activated:
        contract.status = "active"
        contract.activated_at = now
    await db.flush()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_contract.signed",
        entity_type="b2b_contract",
        entity_id=str(contract.id),
        payload={
            "contract_number": contract.contract_number,
            "party": party,
            "signed_by": signed_by,
            "auto_activated": activated,
        },
        trace_id=trace_id,
    )
    if activated:
        await event_service.create_event(
            db,
            workspace_id=workspace_id,
            event_type="b2b_contract.status_changed",
            entity_type="b2b_contract",
            entity_id=str(contract.id),
            payload={
                "contract_number": contract.contract_number,
                "previous_status": previous,
                "new_status": "active",
                "actor": signed_by,
                "reason": "both parties signed",
            },
            trace_id=trace_id,
        )
    await db.commit()
    return await get_contract(
        db,
        workspace_id=workspace_id,
        contract_id=contract.id,
    )  # type: ignore[return-value]


async def get_b2b_order(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    order_id: str | UUID,
) -> B2BOrder | None:
    return (
        await db.execute(
            select(B2BOrder)
            .where(
                B2BOrder.workspace_id == workspace_id,
                B2BOrder.id == _uuid(order_id),
            )
            .options(
                selectinload(B2BOrder.agent),
                selectinload(B2BOrder.items),
            )
        )
    ).scalar_one_or_none()


async def convert_quote_to_order(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    quote_id: str | UUID,
    actor: str,
    trace_id: str | None = None,
) -> B2BOrder:
    quote = await get_quote(
        db,
        workspace_id=workspace_id,
        quote_id=quote_id,
        for_update=True,
    )
    if quote is None:
        raise ValueError("quote not found")
    if quote.status not in {"accepted", "converted"}:
        raise B2BSalesStateError("only accepted quotes can be converted")
    existing = (
        await db.execute(
            select(B2BOrder).where(
                B2BOrder.workspace_id == workspace_id,
                B2BOrder.quote_id == quote.id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        try:
            await consolidation_service.ensure_attribution(
                db,
                workspace_id=workspace_id,
                entity_type="b2b_order",
                entity_id=existing.id,
                actor="system:b2b-order-conversion",
                trace_id=trace_id,
            )
        except Exception:
            logger.warning(
                "automatic consolidation attribution failed for B2B order %s",
                existing.id,
                exc_info=True,
            )
        return await get_b2b_order(
            db,
            workspace_id=workspace_id,
            order_id=existing.id,
        )  # type: ignore[return-value]
    if quote.status != "accepted":
        raise B2BSalesStateError("only accepted quotes can be converted")
    contract = quote.contract
    if contract is None or contract.status != "active":
        raise B2BSalesStateError("an active contract is required before order conversion")
    agent = await _get_agent(db, workspace_id=workspace_id, agent_id=quote.agent_id)
    await b2b_credit_service.assert_order_credit(
        db,
        workspace_id=workspace_id,
        agent_id=agent.id,
        additional_amount=quote.total,
    )

    now = datetime.now(timezone.utc)
    order_id = uuid4()
    order = B2BOrder(
        id=order_id,
        workspace_id=workspace_id,
        order_number=_number("B2B"),
        agent_id=agent.id,
        customer_account_id=quote.customer_account_id,
        quote_id=quote.id,
        contract_id=contract.id,
        business_model="B2B",
        status="pending",
        payment_status="unpaid",
        subtotal=quote.subtotal,
        discount_amount=quote.discount_amount,
        shipping_cost=quote.shipping_cost,
        total=quote.total,
        currency=quote.currency,
        shipping_address={
            "company": agent.company_name,
            "contact": agent.contact_name,
            "phone": agent.phone,
            "country": agent.country,
            "city": agent.city,
            "address": agent.address,
        },
        payment_due_date=(now + timedelta(days=quote.payment_terms_days)).date(),
        notes=quote.notes,
    )
    db.add(order)
    for item in quote.items:
        db.add(
            B2BOrderItem(
                workspace_id=workspace_id,
                order_id=order_id,
                product_id=item.product_id,
                product_name=item.product_name_snapshot,
                sku=item.sku_snapshot,
                quantity=item.quantity,
                unit_price=item.unit_price,
                subtotal=item.line_total,
                currency=quote.currency,
                price_book_version_id=quote.price_book_version_id,
                price_tier_id=item.price_tier_id,
                price_source=item.price_source,
                quote_item_id=item.id,
            )
        )
    agent.current_balance += quote.total
    quote.status = "converted"
    if quote.rfq is not None:
        quote.rfq.status = "won"
        quote.rfq.closed_at = now
    await db.flush()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_quote.converted",
        entity_type="b2b_quote",
        entity_id=str(quote.id),
        payload={
            "quote_number": quote.quote_number,
            "version_number": quote.version_number,
            "order_id": str(order.id),
            "order_number": order.order_number,
            "contract_id": str(contract.id),
            "actor": actor,
        },
        trace_id=trace_id,
    )
    await db.commit()
    try:
        await consolidation_service.ensure_attribution(
            db,
            workspace_id=workspace_id,
            entity_type="b2b_order",
            entity_id=order.id,
            actor="system:b2b-order-conversion",
            trace_id=trace_id,
        )
    except Exception:
        logger.warning(
            "automatic consolidation attribution failed for B2B order %s",
            order.id,
            exc_info=True,
        )
    return await get_b2b_order(
        db,
        workspace_id=workspace_id,
        order_id=order.id,
    )  # type: ignore[return-value]
