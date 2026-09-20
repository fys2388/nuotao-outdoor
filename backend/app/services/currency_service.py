"""Currency normalization, rate resolution, and Decimal-safe conversion."""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.currency import ExchangeRate

if TYPE_CHECKING:
    from datetime import date
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

MONEY = Decimal("0.01")
ZERO = Decimal("0.00")
_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3,8}$")


class CurrencyRateError(ValueError):
    """Base class for exchange-rate domain errors."""


class InvalidCurrencyCodeError(CurrencyRateError):
    """Raised when a currency code is not a supported ISO-style code."""


class ExchangeRateNotFoundError(CurrencyRateError):
    """Raised when no direct rate exists on or before the requested date."""


class ExchangeRateConflictError(CurrencyRateError):
    """Raised when the same workspace pair/date already has a rate."""


def normalize_currency_code(value: str) -> str:
    normalized = value.strip().upper()
    if not _CURRENCY_PATTERN.fullmatch(normalized):
        raise InvalidCurrencyCodeError(
            "currency codes must contain 3 to 8 ASCII letters"
        )
    return normalized


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


async def create_exchange_rate(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    base_currency: str,
    quote_currency: str,
    rate: Decimal,
    effective_date: date,
    source: str,
    source_reference: str | None,
    created_by: str,
) -> ExchangeRate:
    base = normalize_currency_code(base_currency)
    quote = normalize_currency_code(quote_currency)
    if base == quote:
        raise CurrencyRateError("base and quote currencies must be different")
    normalized_rate = Decimal(rate)
    if normalized_rate <= 0:
        raise CurrencyRateError("exchange rate must be greater than zero")
    normalized_source = source.strip()
    if not normalized_source:
        raise CurrencyRateError("exchange-rate source is required")
    normalized_actor = created_by.strip()
    if not normalized_actor:
        raise CurrencyRateError("exchange-rate creator is required")

    existing = (
        await session.execute(
            select(ExchangeRate.id).where(
                ExchangeRate.workspace_id == workspace_id,
                ExchangeRate.base_currency == base,
                ExchangeRate.quote_currency == quote,
                ExchangeRate.effective_date == effective_date,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ExchangeRateConflictError(
            f"{base}/{quote} already has a rate for {effective_date.isoformat()}"
        )

    row = ExchangeRate(
        workspace_id=workspace_id,
        base_currency=base,
        quote_currency=quote,
        rate=normalized_rate,
        effective_date=effective_date,
        source=normalized_source,
        source_reference=source_reference.strip() if source_reference else None,
        created_by=normalized_actor,
    )
    session.add(row)
    await session.flush()
    return row


async def list_exchange_rates(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    base_currency: str | None = None,
    quote_currency: str | None = None,
    as_of: date | None = None,
    limit: int = 200,
) -> list[ExchangeRate]:
    if limit < 1 or limit > 1000:
        raise CurrencyRateError("limit must be between 1 and 1000")
    statement = select(ExchangeRate).where(ExchangeRate.workspace_id == workspace_id)
    if base_currency:
        statement = statement.where(
            ExchangeRate.base_currency == normalize_currency_code(base_currency)
        )
    if quote_currency:
        statement = statement.where(
            ExchangeRate.quote_currency == normalize_currency_code(quote_currency)
        )
    if as_of:
        statement = statement.where(ExchangeRate.effective_date <= as_of)
    statement = statement.order_by(
        ExchangeRate.effective_date.desc(),
        ExchangeRate.base_currency,
        ExchangeRate.quote_currency,
    ).limit(limit)
    return list((await session.execute(statement)).scalars().all())


async def resolve_exchange_rate(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    base_currency: str,
    quote_currency: str,
    as_of: date,
) -> ExchangeRate | None:
    base = normalize_currency_code(base_currency)
    quote = normalize_currency_code(quote_currency)
    if base == quote:
        return None
    return (
        await session.execute(
            select(ExchangeRate)
            .where(
                ExchangeRate.workspace_id == workspace_id,
                ExchangeRate.base_currency == base,
                ExchangeRate.quote_currency == quote,
                ExchangeRate.effective_date <= as_of,
            )
            .order_by(ExchangeRate.effective_date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def convert_amount(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    amount: Decimal,
    base_currency: str,
    quote_currency: str,
    as_of: date,
    rate_cache: dict[tuple[str, str, date], ExchangeRate | None] | None = None,
) -> Decimal:
    base = normalize_currency_code(base_currency)
    quote = normalize_currency_code(quote_currency)
    if base == quote:
        return _money(Decimal(amount))
    if Decimal(amount) == 0:
        return ZERO

    cache = rate_cache if rate_cache is not None else {}
    cache_key = (base, quote, as_of)
    if cache_key not in cache:
        cache[cache_key] = await resolve_exchange_rate(
            session,
            workspace_id=workspace_id,
            base_currency=base,
            quote_currency=quote,
            as_of=as_of,
        )
    rate_row = cache[cache_key]
    if rate_row is None:
        raise ExchangeRateNotFoundError(
            f"missing direct exchange rate {base}/{quote} on or before {as_of.isoformat()}"
        )
    return _money(Decimal(amount) * Decimal(rate_row.rate))
