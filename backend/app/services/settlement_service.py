"""Settlement ledger service: COD / clearance / fee cash-in tracking.

Operates the expected -> partial -> received status machine and exposes
ledger queries plus status rollups so the cash loop is auditable:
what is owed, what has been collected, what is disputed — per carrier.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settlement import Settlement

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000001")

ZERO = Decimal("0")

VALID_STATUSES = {"expected", "partial", "received", "disputed"}
VALID_KINDS = {"cod", "clearance", "fee", "refund"}


class SettlementError(ValueError):
    """Invalid settlement operation."""


async def register_settlement(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    carrier: str,
    expected_amount: Decimal,
    settlement_kind: str = "cod",
    order_id: UUID | None = None,
    external_order_id: str | None = None,
    fees: Decimal = ZERO,
    currency: str = "USD",
    due_date: date | None = None,
    note: str | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Register an expected cash settlement (COD payout, customs bill, fee)."""
    if settlement_kind not in VALID_KINDS:
        raise SettlementError(f"invalid settlement_kind: {settlement_kind}")
    if expected_amount < ZERO:
        raise SettlementError("expected_amount must be >= 0")
    if fees < ZERO:
        raise SettlementError("fees must be >= 0")

    entry = Settlement(
        workspace_id=workspace_id,
        order_id=order_id,
        external_order_id=external_order_id,
        carrier=carrier,
        settlement_kind=settlement_kind,
        expected_amount=expected_amount,
        fees=fees,
        currency=currency,
        status="expected",
        due_date=due_date,
        note=note,
        trace_id=trace_id,
    )
    session.add(entry)
    await session.flush()
    logger.info(
        "settlement registered: id=%s carrier=%s kind=%s expected=%s",
        entry.id, carrier, settlement_kind, expected_amount,
    )
    return _serialize(entry)


async def record_receipt(
    session: AsyncSession,
    *,
    settlement_id: UUID,
    received_amount: Decimal,
    fees: Decimal | None = None,
    received_at: datetime | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Record an actual receipt; advances status by the collected amount.

    received >= expected -> received; 0 < received < expected -> partial.
    A disputed entry keeps its status so it stays on the follow-up list.
    """
    if received_amount < ZERO:
        raise SettlementError("received_amount must be >= 0")
    if isinstance(settlement_id, str):
        settlement_id = UUID(settlement_id)
    entry = await session.get(Settlement, settlement_id)
    if entry is None:
        raise SettlementError(f"settlement not found: {settlement_id}")

    entry.received_amount = received_amount
    if fees is not None:
        if fees < ZERO:
            raise SettlementError("fees must be >= 0")
        entry.fees = fees
    entry.received_at = received_at or datetime.now()
    if note:
        entry.note = f"{entry.note} | {note}" if entry.note else note

    if entry.status != "disputed":
        # 实收 + 渠道扣费 >= 应回款 => 全额结清（扣费是应回款的一部分）
        if entry.received_amount + entry.fees >= entry.expected_amount:
            entry.status = "received"
        elif entry.received_amount > ZERO:
            entry.status = "partial"
        else:
            entry.status = "expected"

    await session.flush()
    logger.info(
        "settlement receipt: id=%s received=%s status=%s",
        settlement_id, received_amount, entry.status,
    )
    return _serialize(entry)


async def mark_disputed(
    session: AsyncSession,
    *,
    settlement_id: UUID,
    note: str | None = None,
) -> dict[str, Any]:
    """Mark an entry disputed so it stays visible on the follow-up list."""
    if isinstance(settlement_id, str):
        settlement_id = UUID(settlement_id)
    entry = await session.get(Settlement, settlement_id)
    if entry is None:
        raise SettlementError(f"settlement not found: {settlement_id}")
    entry.status = "disputed"
    if note:
        entry.note = f"{entry.note} | {note}" if entry.note else note
    await session.flush()
    return _serialize(entry)


async def list_settlements(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    status: str | None = None,
    carrier: str | None = None,
    settlement_kind: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Filtered ledger query with a matching total (for pagination)."""
    conditions = [Settlement.workspace_id == workspace_id]
    if status:
        if status not in VALID_STATUSES:
            raise SettlementError(f"invalid status: {status}")
        conditions.append(Settlement.status == status)
    if carrier:
        conditions.append(Settlement.carrier == carrier)
    if settlement_kind:
        conditions.append(Settlement.settlement_kind == settlement_kind)

    total = await session.scalar(
        select(func.count()).select_from(Settlement).where(*conditions)
    )
    rows = (
        await session.execute(
            select(Settlement)
            .where(*conditions)
            .order_by(Settlement.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    return {"items": [_serialize(r) for r in rows], "total": total or 0}


async def settlement_stats(
    session: AsyncSession,
    *,
    workspace_id: UUID,
) -> dict[str, Any]:
    """Cash-in rollup: by status and by carrier."""
    conditions = [Settlement.workspace_id == workspace_id]

    rows = (
        await session.execute(
            select(
                Settlement.status,
                func.count().label("count"),
                func.coalesce(func.sum(Settlement.expected_amount), ZERO).label("expected"),
                func.coalesce(func.sum(Settlement.received_amount), ZERO).label("received"),
                func.coalesce(func.sum(Settlement.fees), ZERO).label("fees"),
            )
            .where(*conditions)
            .group_by(Settlement.status)
        )
    ).all()

    by_status: dict[str, dict[str, Any]] = {}
    for status, count, expected, received, fees in rows:
        by_status[status] = {
            "count": count,
            "expected_amount": _fmt(expected),
            "received_amount": _fmt(received),
            "pending_amount": _fmt(max(expected - received - fees, ZERO)),
        }

    carrier_rows = (
        await session.execute(
            select(
                Settlement.carrier,
                func.count().label("count"),
                func.coalesce(func.sum(Settlement.expected_amount), ZERO).label("expected"),
                func.coalesce(func.sum(Settlement.received_amount), ZERO).label("received"),
                func.coalesce(func.sum(Settlement.fees), ZERO).label("fees"),
            )
            .where(*conditions)
            .group_by(Settlement.carrier)
            .order_by(func.count().desc())
        )
    ).all()

    by_carrier: dict[str, dict[str, Any]] = {}
    for carrier, count, expected, received, fees in carrier_rows:
        by_carrier[carrier] = {
            "count": count,
            "expected_amount": _fmt(expected),
            "received_amount": _fmt(received),
            "pending_amount": _fmt(max(expected - received - fees, ZERO)),
        }

    return {
        "by_status": by_status,
        "by_carrier": by_carrier,
        "totals": {
            "entries": sum(v["count"] for v in by_status.values()),
            "expected_amount": _fmt(
                sum(Decimal(v["expected_amount"]) for v in by_status.values())
            ),
            "received_amount": _fmt(
                sum(Decimal(v["received_amount"]) for v in by_status.values())
            ),
            "pending_amount": _fmt(
                sum(
                    Decimal(v.get("pending_amount", "0"))
                    for v in by_status.values()
                    if v.get("pending_amount")
                )
            ),
        },
    }


def _fmt(value: Decimal) -> str:
    """Deterministic string serialization for JSON-safe API output."""
    return f"{value:.2f}"


def _serialize(entry: Settlement) -> dict[str, Any]:
    return {
        "id": str(entry.id),
        "workspace_id": str(entry.workspace_id),
        "order_id": str(entry.order_id) if entry.order_id else None,
        "external_order_id": entry.external_order_id,
        "carrier": entry.carrier,
        "settlement_kind": entry.settlement_kind,
        "expected_amount": _fmt(entry.expected_amount),
        "received_amount": _fmt(entry.received_amount),
        "fees": _fmt(entry.fees),
        "currency": entry.currency,
        "status": entry.status,
        "due_date": entry.due_date.isoformat() if entry.due_date else None,
        "received_at": entry.received_at.isoformat() if entry.received_at else None,
        "note": entry.note,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }
