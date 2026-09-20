"""Authoritative B2B pricing, versioning, approval, and resolution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.b2b import (
    B2BAgent,
    B2BPriceBook,
    B2BPriceTier,
    B2BPriceVersion,
)
from app.models.product import Product

EDITABLE_VERSION_STATUSES = {"draft", "rejected"}
SUBMITTABLE_VERSION_STATUSES = {"draft", "rejected"}


class PricingError(ValueError):
    """Base class for domain-level pricing errors."""


class PricingStateError(PricingError):
    """Raised when an operation is invalid for the current version state."""


class PricingConflictError(PricingError):
    """Raised when price ranges or effective periods conflict."""


@dataclass(frozen=True)
class ResolvedB2BPrice:
    """Immutable price snapshot used by quotes, orders, and profit calculations."""

    price_book_id: UUID
    price_book_version_id: UUID
    price_tier_id: UUID
    version_number: int
    source: str
    unit_price: Decimal
    currency: str
    min_quantity: int
    max_quantity: int | None


def _to_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _normalize_currency(value: str) -> str:
    normalized = value.strip().upper()
    if not normalized or len(normalized) > 8:
        raise PricingError("invalid currency")
    return normalized


def _ranges_overlap(
    first_min: int,
    first_max: int | None,
    second_min: int,
    second_max: int | None,
) -> bool:
    return (first_max is None or second_min < first_max) and (
        second_max is None or first_min < second_max
    )


async def create_price_book(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    code: str,
    name: str,
    currency: str,
    created_by: str,
    is_default: bool = False,
    notes: str | None = None,
) -> B2BPriceBook:
    normalized_code = code.strip().upper()
    if not normalized_code:
        raise PricingError("price book code is required")
    existing = (
        await db.execute(
            select(B2BPriceBook).where(
                B2BPriceBook.workspace_id == workspace_id,
                B2BPriceBook.code == normalized_code,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise PricingConflictError("price book code already exists")

    if is_default:
        await db.execute(
            update(B2BPriceBook)
            .where(B2BPriceBook.workspace_id == workspace_id)
            .values(is_default=False)
        )
    book = B2BPriceBook(
        workspace_id=workspace_id,
        code=normalized_code,
        name=name.strip(),
        currency=_normalize_currency(currency),
        status="active",
        is_default=is_default,
        notes=notes,
        created_by=created_by,
    )
    db.add(book)
    await db.commit()
    await db.refresh(book)
    return book


async def list_price_books(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[B2BPriceBook], int]:
    base = select(B2BPriceBook).where(B2BPriceBook.workspace_id == workspace_id)
    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        await db.execute(
            base.order_by(
                B2BPriceBook.is_default.desc(),
                B2BPriceBook.created_at.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return list(rows), int(total)


async def get_price_book(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    price_book_id: str | UUID,
) -> B2BPriceBook | None:
    return (
        await db.execute(
            select(B2BPriceBook)
            .where(
                B2BPriceBook.workspace_id == workspace_id,
                B2BPriceBook.id == _to_uuid(price_book_id),
            )
            .options(selectinload(B2BPriceBook.versions))
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()


async def ensure_default_price_book(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    currency: str = "USD",
    actor: str = "system",
) -> B2BPriceBook:
    book = (
        await db.execute(
            select(B2BPriceBook).where(
                B2BPriceBook.workspace_id == workspace_id,
                B2BPriceBook.is_default.is_(True),
                B2BPriceBook.status == "active",
            )
        )
    ).scalar_one_or_none()
    if book is not None:
        return book
    return await create_price_book(
        db,
        workspace_id=workspace_id,
        code="DEFAULT",
        name="默认 B2B 价格簿",
        currency=currency,
        created_by=actor,
        is_default=True,
    )


async def create_price_version(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    price_book_id: str | UUID,
    created_by: str,
    effective_from: date,
    effective_to: date | None = None,
    source_version_id: str | UUID | None = None,
    notes: str | None = None,
) -> B2BPriceVersion:
    if effective_to is not None and effective_to <= effective_from:
        raise PricingError("effective_to must be after effective_from")
    book = await get_price_book(
        db,
        workspace_id=workspace_id,
        price_book_id=price_book_id,
    )
    if book is None:
        raise PricingError("price book not found")

    max_version = (
        await db.execute(
            select(func.coalesce(func.max(B2BPriceVersion.version_number), 0)).where(
                B2BPriceVersion.workspace_id == workspace_id,
                B2BPriceVersion.price_book_id == book.id,
            )
        )
    ).scalar_one()
    version = B2BPriceVersion(
        workspace_id=workspace_id,
        price_book_id=book.id,
        version_number=int(max_version) + 1,
        status="draft",
        effective_from=effective_from,
        effective_to=effective_to,
        created_by=created_by,
        notes=notes,
    )
    db.add(version)
    await db.flush()

    if source_version_id is not None:
        source = await get_price_version(
            db,
            workspace_id=workspace_id,
            price_version_id=source_version_id,
        )
        if source is None or source.price_book_id != book.id:
            raise PricingError("source price version not found")
        for tier in source.tiers:
            db.add(
                B2BPriceTier(
                    workspace_id=workspace_id,
                    price_version_id=version.id,
                    product_id=tier.product_id,
                    tier=tier.tier,
                    agent_id=tier.agent_id,
                    min_quantity=tier.min_quantity,
                    max_quantity=tier.max_quantity,
                    unit_price=tier.unit_price,
                    currency=tier.currency,
                    is_active=tier.is_active,
                )
            )

    await db.commit()
    return await get_price_version(
        db,
        workspace_id=workspace_id,
        price_version_id=version.id,
    )  # type: ignore[return-value]


async def list_price_versions(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    price_book_id: str | UUID,
) -> list[B2BPriceVersion]:
    rows = (
        await db.execute(
            select(B2BPriceVersion)
            .where(
                B2BPriceVersion.workspace_id == workspace_id,
                B2BPriceVersion.price_book_id == _to_uuid(price_book_id),
            )
            .options(selectinload(B2BPriceVersion.tiers))
            .order_by(B2BPriceVersion.version_number.desc())
        )
    ).scalars().all()
    return list(rows)


async def get_price_version(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    price_version_id: str | UUID,
) -> B2BPriceVersion | None:
    return (
        await db.execute(
            select(B2BPriceVersion)
            .where(
                B2BPriceVersion.workspace_id == workspace_id,
                B2BPriceVersion.id == _to_uuid(price_version_id),
            )
            .options(
                selectinload(B2BPriceVersion.tiers),
                selectinload(B2BPriceVersion.price_book),
            )
        )
    ).scalar_one_or_none()


async def _get_editable_version(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    price_version_id: str | UUID,
) -> B2BPriceVersion:
    version = (
        await db.execute(
            select(B2BPriceVersion)
            .where(
                B2BPriceVersion.workspace_id == workspace_id,
                B2BPriceVersion.id == _to_uuid(price_version_id),
            )
            .options(
                selectinload(B2BPriceVersion.tiers),
                selectinload(B2BPriceVersion.price_book),
            )
            .execution_options(populate_existing=True)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if version is None:
        raise PricingError("price version not found")
    if version.status not in EDITABLE_VERSION_STATUSES:
        raise PricingStateError("only draft or rejected versions can be edited")
    return version


async def _validate_tier(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    version: B2BPriceVersion,
    product_id: UUID,
    tier: str | None,
    agent_id: UUID | None,
    min_quantity: int,
    max_quantity: int | None,
    currency: str,
    exclude_tier_id: UUID | None = None,
) -> None:
    if min_quantity < 1:
        raise PricingError("min_quantity must be at least 1")
    if max_quantity is not None and max_quantity <= min_quantity:
        raise PricingError("max_quantity must be greater than min_quantity")
    if (tier is None) == (agent_id is None):
        raise PricingError("exactly one of tier or agent_id is required")

    product = (
        await db.execute(
            select(Product).where(
                Product.workspace_id == workspace_id,
                Product.id == product_id,
            )
        )
    ).scalar_one_or_none()
    if product is None:
        raise PricingError("product not found")
    if agent_id is not None:
        agent = (
            await db.execute(
                select(B2BAgent).where(
                    B2BAgent.workspace_id == workspace_id,
                    B2BAgent.id == agent_id,
                )
            )
        ).scalar_one_or_none()
        if agent is None:
            raise PricingError("agent not found")

    if _normalize_currency(currency) != version.price_book.currency:
        raise PricingError("tier currency must match the price book currency")

    candidates = version.tiers
    for candidate in candidates:
        if exclude_tier_id is not None and candidate.id == exclude_tier_id:
            continue
        if candidate.product_id != product_id:
            continue
        if candidate.tier != tier or candidate.agent_id != agent_id:
            continue
        if _ranges_overlap(
            min_quantity,
            max_quantity,
            candidate.min_quantity,
            candidate.max_quantity,
        ):
            raise PricingConflictError("price quantity range overlaps an existing tier")


async def create_price_tier(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    price_version_id: str | UUID,
    product_id: str | UUID,
    tier: str | None,
    agent_id: str | UUID | None,
    min_quantity: int,
    max_quantity: int | None,
    unit_price: Decimal,
    currency: str,
    is_active: bool = True,
) -> B2BPriceTier:
    version = await _get_editable_version(
        db,
        workspace_id=workspace_id,
        price_version_id=price_version_id,
    )
    product_uuid = _to_uuid(product_id)
    agent_uuid = _to_uuid(agent_id) if agent_id is not None else None
    if unit_price <= 0:
        raise PricingError("unit_price must be positive")
    await _validate_tier(
        db,
        workspace_id=workspace_id,
        version=version,
        product_id=product_uuid,
        tier=tier,
        agent_id=agent_uuid,
        min_quantity=min_quantity,
        max_quantity=max_quantity,
        currency=currency,
    )
    record = B2BPriceTier(
        workspace_id=workspace_id,
        price_version_id=version.id,
        product_id=product_uuid,
        tier=tier,
        agent_id=agent_uuid,
        min_quantity=min_quantity,
        max_quantity=max_quantity,
        unit_price=unit_price,
        currency=_normalize_currency(currency),
        is_active=is_active,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def update_price_tier(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    price_tier_id: str | UUID,
    min_quantity: int | None = None,
    max_quantity: int | None = None,
    unit_price: Decimal | None = None,
    is_active: bool | None = None,
) -> B2BPriceTier:
    record = (
        await db.execute(
            select(B2BPriceTier).where(
                B2BPriceTier.workspace_id == workspace_id,
                B2BPriceTier.id == _to_uuid(price_tier_id),
            )
        )
    ).scalar_one_or_none()
    if record is None:
        raise PricingError("price tier not found")
    version = await _get_editable_version(
        db,
        workspace_id=workspace_id,
        price_version_id=record.price_version_id,
    )
    next_min = min_quantity if min_quantity is not None else record.min_quantity
    next_max = max_quantity if max_quantity is not None else record.max_quantity
    next_price = unit_price if unit_price is not None else record.unit_price
    if next_price <= 0:
        raise PricingError("unit_price must be positive")
    await _validate_tier(
        db,
        workspace_id=workspace_id,
        version=version,
        product_id=record.product_id,
        tier=record.tier,
        agent_id=record.agent_id,
        min_quantity=next_min,
        max_quantity=next_max,
        currency=record.currency,
        exclude_tier_id=record.id,
    )
    record.min_quantity = next_min
    record.max_quantity = next_max
    record.unit_price = next_price
    if is_active is not None:
        record.is_active = is_active
    await db.commit()
    await db.refresh(record)
    return record


async def delete_price_tier(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    price_tier_id: str | UUID,
) -> None:
    record = (
        await db.execute(
            select(B2BPriceTier).where(
                B2BPriceTier.workspace_id == workspace_id,
                B2BPriceTier.id == _to_uuid(price_tier_id),
            )
        )
    ).scalar_one_or_none()
    if record is None:
        raise PricingError("price tier not found")
    await _get_editable_version(
        db,
        workspace_id=workspace_id,
        price_version_id=record.price_version_id,
    )
    await db.delete(record)
    await db.commit()


async def submit_price_version(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    price_version_id: str | UUID,
    actor: str,
) -> B2BPriceVersion:
    version = (
        await db.execute(
            select(B2BPriceVersion)
            .where(
                B2BPriceVersion.workspace_id == workspace_id,
                B2BPriceVersion.id == _to_uuid(price_version_id),
            )
            .options(
                selectinload(B2BPriceVersion.tiers),
                selectinload(B2BPriceVersion.price_book),
            )
            .execution_options(populate_existing=True)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if version is None:
        raise PricingError("price version not found")
    if version.status not in SUBMITTABLE_VERSION_STATUSES:
        raise PricingStateError("only draft or rejected versions can be submitted")
    if not any(tier.is_active for tier in version.tiers):
        raise PricingStateError("at least one active price tier is required")
    version.status = "pending_approval"
    version.submitted_by = actor
    version.submitted_at = datetime.now(timezone.utc)
    version.rejection_reason = None
    await db.commit()
    await db.refresh(version)
    return version


async def approve_price_version(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    price_version_id: str | UUID,
    actor: str,
) -> B2BPriceVersion:
    version = (
        await db.execute(
            select(B2BPriceVersion)
            .where(
                B2BPriceVersion.workspace_id == workspace_id,
                B2BPriceVersion.id == _to_uuid(price_version_id),
            )
            .options(selectinload(B2BPriceVersion.price_book))
            .with_for_update()
        )
    ).scalar_one_or_none()
    if version is None:
        raise PricingError("price version not found")
    if version.status != "pending_approval":
        raise PricingStateError("only pending_approval versions can be approved")
    if version.submitted_by and version.submitted_by == actor:
        raise PricingStateError("submitter cannot approve the same price version")

    current_versions = (
        await db.execute(
            select(B2BPriceVersion)
            .where(
                B2BPriceVersion.workspace_id == workspace_id,
                B2BPriceVersion.price_book_id == version.price_book_id,
                B2BPriceVersion.status == "active",
                B2BPriceVersion.id != version.id,
            )
            .with_for_update()
        )
    ).scalars().all()
    for current in current_versions:
        if _version_periods_overlap(
            version.effective_from,
            version.effective_to,
            current.effective_from,
            current.effective_to,
        ):
            current.status = "superseded"
            previous_end = version.effective_from - timedelta(days=1)
            if (
                current.effective_to is None
                or current.effective_to > previous_end
            ) and previous_end > current.effective_from:
                current.effective_to = previous_end

    version.status = "active"
    version.approved_by = actor
    version.approved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(version)
    return version


def _version_periods_overlap(
    first_from: date,
    first_to: date | None,
    second_from: date,
    second_to: date | None,
) -> bool:
    return (first_to is None or second_from < first_to) and (
        second_to is None or first_from < second_to
    )


async def reject_price_version(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    price_version_id: str | UUID,
    actor: str,
    reason: str,
) -> B2BPriceVersion:
    version = (
        await db.execute(
            select(B2BPriceVersion)
            .where(
                B2BPriceVersion.workspace_id == workspace_id,
                B2BPriceVersion.id == _to_uuid(price_version_id),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if version is None:
        raise PricingError("price version not found")
    if version.status != "pending_approval":
        raise PricingStateError("only pending_approval versions can be rejected")
    if version.submitted_by and version.submitted_by == actor:
        raise PricingStateError("submitter cannot reject the same price version")
    version.status = "rejected"
    version.rejection_reason = reason.strip() or "rejected"
    await db.commit()
    await db.refresh(version)
    return version


def _base_resolution_query(
    *,
    workspace_id: UUID,
    product_id: UUID,
    agent_id: UUID | None,
    tier: str | None,
    quantity: int,
    as_of: date,
) -> Select:
    scope_condition = (
        B2BPriceTier.agent_id == agent_id
        if agent_id is not None
        else B2BPriceTier.tier == tier
    )
    return (
        select(B2BPriceTier)
        .join(
            B2BPriceVersion,
            B2BPriceVersion.id == B2BPriceTier.price_version_id,
        )
        .join(B2BPriceBook, B2BPriceBook.id == B2BPriceVersion.price_book_id)
        .where(
            B2BPriceTier.workspace_id == workspace_id,
            B2BPriceTier.product_id == product_id,
            B2BPriceTier.is_active.is_(True),
            scope_condition,
            B2BPriceVersion.status == "active",
            B2BPriceVersion.effective_from <= as_of,
            or_(
                B2BPriceVersion.effective_to.is_(None),
                B2BPriceVersion.effective_to >= as_of,
            ),
            B2BPriceBook.status == "active",
            B2BPriceBook.is_default.is_(True),
            B2BPriceTier.min_quantity <= quantity,
            or_(
                B2BPriceTier.max_quantity.is_(None),
                B2BPriceTier.max_quantity > quantity,
            ),
        )
        .order_by(
            B2BPriceTier.min_quantity.desc(),
            B2BPriceTier.created_at.desc(),
        )
        .limit(1)
    )


def _base_display_query(
    *,
    workspace_id: UUID,
    product_id: UUID,
    agent_id: UUID | None,
    tier: str | None,
    as_of: date,
) -> Select:
    scope_condition = (
        B2BPriceTier.agent_id == agent_id
        if agent_id is not None
        else B2BPriceTier.tier == tier
    )
    return (
        select(B2BPriceTier)
        .join(
            B2BPriceVersion,
            B2BPriceVersion.id == B2BPriceTier.price_version_id,
        )
        .join(B2BPriceBook, B2BPriceBook.id == B2BPriceVersion.price_book_id)
        .where(
            B2BPriceTier.workspace_id == workspace_id,
            B2BPriceTier.product_id == product_id,
            B2BPriceTier.is_active.is_(True),
            scope_condition,
            B2BPriceVersion.status == "active",
            B2BPriceVersion.effective_from <= as_of,
            or_(
                B2BPriceVersion.effective_to.is_(None),
                B2BPriceVersion.effective_to >= as_of,
            ),
            B2BPriceBook.status == "active",
            B2BPriceBook.is_default.is_(True),
        )
        .order_by(B2BPriceTier.min_quantity.asc())
        .limit(1)
    )


async def resolve_b2b_display_price(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: str | UUID,
    agent: B2BAgent,
    as_of: date | None = None,
) -> ResolvedB2BPrice:
    """Resolve the entry tier shown in a catalog before a quantity is chosen."""
    effective_date = as_of or date.today()
    product_uuid = _to_uuid(product_id)
    selected = (
        await db.execute(
            _base_display_query(
                workspace_id=workspace_id,
                product_id=product_uuid,
                agent_id=agent.id,
                tier=None,
                as_of=effective_date,
            )
        )
    ).scalar_one_or_none()
    source = "AGENT"
    if selected is None:
        selected = (
            await db.execute(
                _base_display_query(
                    workspace_id=workspace_id,
                    product_id=product_uuid,
                    agent_id=None,
                    tier=agent.tier,
                    as_of=effective_date,
                )
            )
        ).scalar_one_or_none()
        source = "TIER"
    if selected is None:
        raise PricingError(f"no active B2B price for product {product_uuid}")
    version = (
        await db.execute(
            select(B2BPriceVersion).where(B2BPriceVersion.id == selected.price_version_id)
        )
    ).scalar_one()
    return ResolvedB2BPrice(
        price_book_id=version.price_book_id,
        price_book_version_id=version.id,
        price_tier_id=selected.id,
        version_number=version.version_number,
        source=source,
        unit_price=Decimal(selected.unit_price),
        currency=selected.currency,
        min_quantity=selected.min_quantity,
        max_quantity=selected.max_quantity,
    )


async def resolve_b2b_price(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: str | UUID,
    agent: B2BAgent,
    quantity: int,
    as_of: date | None = None,
) -> ResolvedB2BPrice:
    if quantity < 1:
        raise PricingError("quantity must be at least 1")
    if agent.workspace_id != workspace_id:
        raise PricingError("agent does not belong to workspace")
    effective_date = as_of or date.today()
    product_uuid = _to_uuid(product_id)

    selected = (
        await db.execute(
            _base_resolution_query(
                workspace_id=workspace_id,
                product_id=product_uuid,
                agent_id=agent.id,
                tier=None,
                quantity=quantity,
                as_of=effective_date,
            )
        )
    ).scalar_one_or_none()
    source = "AGENT"
    if selected is None:
        selected = (
            await db.execute(
                _base_resolution_query(
                    workspace_id=workspace_id,
                    product_id=product_uuid,
                    agent_id=None,
                    tier=agent.tier,
                    quantity=quantity,
                    as_of=effective_date,
                )
            )
        ).scalar_one_or_none()
        source = "TIER"

    if selected is None:
        raise PricingError(
            f"no active B2B price for product {product_uuid} at quantity {quantity}"
        )
    version = (
        await db.execute(
            select(B2BPriceVersion).where(B2BPriceVersion.id == selected.price_version_id)
        )
    ).scalar_one()
    return ResolvedB2BPrice(
        price_book_id=version.price_book_id,
        price_book_version_id=version.id,
        price_tier_id=selected.id,
        version_number=version.version_number,
        source=source,
        unit_price=Decimal(selected.unit_price),
        currency=selected.currency,
        min_quantity=selected.min_quantity,
        max_quantity=selected.max_quantity,
    )


async def preview_price_for_agent(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: str | UUID,
    agent_id: str | UUID,
    quantity: int,
    as_of: date | None = None,
) -> ResolvedB2BPrice | None:
    agent = (
        await db.execute(
            select(B2BAgent).where(
                B2BAgent.workspace_id == workspace_id,
                B2BAgent.id == _to_uuid(agent_id),
            )
        )
    ).scalar_one_or_none()
    if agent is None:
        return None
    try:
        return await resolve_b2b_price(
            db,
            workspace_id=workspace_id,
            product_id=product_id,
            agent=agent,
            quantity=quantity,
            as_of=as_of,
        )
    except PricingError:
        return None
