"""B2B lead quote service (M440-04, M4.4).

Quotes are versioned and immutable once approved. Core rules enforced here:

- A new version is created instead of mutating an approved quote in place.
- A quote is never "sent" by this service: sending requires an explicit human
  approval (``approved``) and is a separate, out-of-scope action (production
  quote sending needs Owner approval per the M4.4 boundaries).
- Currency and trade terms are recorded explicitly; no implicit conversion is
  performed and no profit claim is invented.
- Every mutation appends an ``event_log`` entry (append-only audit) with the
  actor, so quote history is fully traceable.

Spec: reports/b2b/CHATGPT_M1_M2_SPEC.md + M4.4 M440-04 instruction.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.b2b_lead_quote import B2BLeadQuote
from app.models.b2b_leads import B2BLead
from app.services import event_service

logger = logging.getLogger(__name__)


class QuoteError(ValueError):
    """Raised when a quote cannot be created, approved or rejected."""


def _quote_number(version: int) -> str:
    return f"QT-{uuid4().hex[:8].upper()}-V{version}"


async def _next_version(db: AsyncSession, lead_id: UUID) -> int:
    result = await db.execute(
        select(func.coalesce(func.max(B2BLeadQuote.quote_version), 0)).where(
            B2BLeadQuote.lead_id == lead_id
        )
    )
    return int(result.scalar_one()) + 1


async def create_quote(
    db: AsyncSession,
    *,
    lead: B2BLead,
    unit_price: float,
    currency: str,
    quantity: int = 1,
    shipping_cost: float = 0,
    valid_until: Any = None,
    payment_terms: str | None = None,
    shipping_terms: str | None = None,
    notes: str | None = None,
    actor: str | None = None,
    workspace_id: UUID = DEFAULT_WORKSPACE_ID,
) -> B2BLeadQuote:
    """Create the next quote version for a lead (internal, unapproved by default)."""
    version = await _next_version(db, lead.id)
    estimated_total = float(unit_price) * max(quantity, 1) + float(shipping_cost)
    quote = B2BLeadQuote(
        id=uuid4(),
        workspace_id=workspace_id,
        lead_id=lead.id,
        quote_number=_quote_number(version),
        quote_version=version,
        currency=currency.strip() or "USD",
        unit_price=unit_price,
        quantity=max(quantity, 1),
        shipping_cost=shipping_cost,
        estimated_total=estimated_total,
        valid_until=valid_until,
        payment_terms=payment_terms,
        shipping_terms=shipping_terms,
        approval_status="draft",
        created_by=actor,
        notes=notes,
    )
    db.add(quote)
    await db.commit()
    await db.refresh(quote)
    await event_service.create_event(
        db,
        workspace_id=quote.workspace_id,
        event_type="b2b_quote.created",
        entity_type="b2b_lead_quote",
        entity_id=str(quote.id),
        payload={
            "reference_number": lead.reference_number,
            "quote_number": quote.quote_number,
            "version": quote.quote_version,
            "currency": quote.currency,
            "actor": actor,
        },
    )
    return quote


async def list_quotes(
    db: AsyncSession,
    *,
    lead_id: UUID,
    workspace_id: UUID = DEFAULT_WORKSPACE_ID,
) -> list[B2BLeadQuote]:
    """List all quote versions of a lead (newest version first)."""
    result = await db.execute(
        select(B2BLeadQuote)
        .where(
            B2BLeadQuote.lead_id == lead_id,
            B2BLeadQuote.workspace_id == workspace_id,
        )
        .order_by(B2BLeadQuote.quote_version.desc())
    )
    return list(result.scalars().all())


async def approve_quote(
    db: AsyncSession,
    *,
    quote_id: UUID,
    actor: str,
    workspace_id: UUID = DEFAULT_WORKSPACE_ID,
) -> B2BLeadQuote:
    """Approve a draft/pending quote (human-in-the-loop gate).

    An approved quote is immutable: a change requires a new version. Only
    ``draft``/``pending`` quotes can be approved.
    """
    quote = await db.get(B2BLeadQuote, quote_id)
    if quote is None or quote.workspace_id != workspace_id:
        raise QuoteError("Quote not found")
    if quote.approval_status not in ("draft", "pending"):
        raise QuoteError(
            f"Only draft/pending quotes can be approved, got {quote.approval_status}"
        )
    lead = await db.get(B2BLead, quote.lead_id)
    quote.approval_status = "approved"
    quote.approved_by = actor
    await db.commit()
    await db.refresh(quote)
    await event_service.create_event(
        db,
        workspace_id=quote.workspace_id,
        event_type="b2b_quote.approved",
        entity_type="b2b_lead_quote",
        entity_id=str(quote.id),
        payload={
            "quote_number": quote.quote_number,
            "version": quote.quote_version,
            "approved_by": actor,
            "reference_number": lead.reference_number if lead else None,
        },
    )
    return quote


async def reject_quote(
    db: AsyncSession,
    *,
    quote_id: UUID,
    actor: str,
    workspace_id: UUID = DEFAULT_WORKSPACE_ID,
) -> B2BLeadQuote:
    """Reject a draft/pending quote (immutable once approved)."""
    quote = await db.get(B2BLeadQuote, quote_id)
    if quote is None or quote.workspace_id != workspace_id:
        raise QuoteError("Quote not found")
    if quote.approval_status not in ("draft", "pending"):
        raise QuoteError(
            f"Only draft/pending quotes can be rejected, got {quote.approval_status}"
        )
    quote.approval_status = "rejected"
    await db.commit()
    await db.refresh(quote)
    await event_service.create_event(
        db,
        workspace_id=quote.workspace_id,
        event_type="b2b_quote.rejected",
        entity_type="b2b_lead_quote",
        entity_id=str(quote.id),
        payload={"quote_number": quote.quote_number, "rejected_by": actor},
    )
    return quote
