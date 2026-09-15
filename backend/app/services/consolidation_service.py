"""Brand/legal-entity attribution and deterministic consolidation reporting.

The service separates operational facts from reporting dimensions. Missing
attribution is visible as ``UNATTRIBUTED`` rather than silently assigned.
Intercompany revenue is removed from external revenue only after an
administrator approves the explicit elimination amount. Profit elimination is
not simulated because that requires a paired buyer-side accounting ledger.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import or_, select

from app.models.b2b import B2BOrder, B2BOrderItem
from app.models.b2b_finance import B2BInvoice
from app.models.consolidation import (
    ATTRIBUTION_ENTITY_TYPES,
    Brand,
    CommerceAttribution,
    LegalEntity,
)
from app.models.order import Order, OrderItem
from app.models.product import Product, ProductCost
from app.services import currency_service, event_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

ZERO = Decimal("0")
CENT = Decimal("0.01")


class ConsolidationError(ValueError):
    """Base class for attribution and consolidation errors."""


class ConsolidationNotFoundError(ConsolidationError):
    """Raised when a referenced reporting fact or master row is missing."""


class ConsolidationConflictError(ConsolidationError):
    """Raised when a code or attribution already exists."""


class ConsolidationStateError(ConsolidationError):
    """Raised when an elimination transition is invalid."""


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(CENT)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (TypeError, ValueError):
        return None


def _percent(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator <= ZERO:
        return None
    return (numerator / denominator * Decimal("100")).quantize(CENT)


def _normalize_code(value: str) -> str:
    normalized = value.strip().upper()
    if not normalized:
        raise ConsolidationError("code is required")
    return normalized


def _require_actor(actor: str) -> str:
    normalized = actor.strip()
    if not normalized:
        raise ConsolidationError("actor is required")
    return normalized


def _snapshot_margin(snapshot: Any) -> Decimal | None:
    if isinstance(snapshot, str):
        try:
            snapshot = json.loads(snapshot)
        except (TypeError, ValueError):
            return None
    if not isinstance(snapshot, dict):
        return None
    return _decimal(snapshot.get("contribution_margin"))


async def create_legal_entity(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    code: str,
    name: str,
    legal_name: str,
    country: str,
    functional_currency: str,
    status: str,
    notes: str | None,
    actor: str,
) -> LegalEntity:
    normalized_code = _normalize_code(code)
    normalized_actor = _require_actor(actor)
    existing = (
        await session.execute(
            select(LegalEntity.id).where(
                LegalEntity.workspace_id == workspace_id,
                LegalEntity.code == normalized_code,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConsolidationConflictError(
            f"legal entity code already exists: {normalized_code}"
        )
    row = LegalEntity(
        workspace_id=workspace_id,
        code=normalized_code,
        name=name.strip(),
        legal_name=legal_name.strip(),
        country=country.strip().upper(),
        functional_currency=currency_service.normalize_currency_code(
            functional_currency
        ),
        status=status,
        notes=notes.strip() if notes else None,
        created_by=normalized_actor,
    )
    session.add(row)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="consolidation.legal_entity_created",
        entity_type="legal_entity",
        entity_id=str(row.id),
        payload={"code": row.code, "actor": normalized_actor},
    )
    return row


async def update_legal_entity(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    legal_entity_id: UUID,
    changes: dict[str, Any],
    actor: str,
) -> LegalEntity:
    row = await get_legal_entity(
        session,
        workspace_id=workspace_id,
        legal_entity_id=legal_entity_id,
    )
    normalized_actor = _require_actor(actor)
    if "functional_currency" in changes:
        changes["functional_currency"] = currency_service.normalize_currency_code(
            str(changes["functional_currency"])
        )
    if "country" in changes and changes["country"] is not None:
        changes["country"] = str(changes["country"]).strip().upper()
    for key in ("name", "legal_name"):
        if key in changes and changes[key] is not None:
            changes[key] = str(changes[key]).strip()
    for key, value in changes.items():
        if key not in {
            "name",
            "legal_name",
            "country",
            "functional_currency",
            "status",
            "notes",
        }:
            raise ConsolidationError(f"unsupported legal-entity field: {key}")
        setattr(row, key, value)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="consolidation.legal_entity_updated",
        entity_type="legal_entity",
        entity_id=str(row.id),
        payload={"changed_fields": sorted(changes), "actor": normalized_actor},
    )
    await session.refresh(row)
    return row


async def get_legal_entity(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    legal_entity_id: UUID,
) -> LegalEntity:
    row = (
        await session.execute(
            select(LegalEntity).where(
                LegalEntity.workspace_id == workspace_id,
                LegalEntity.id == legal_entity_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise ConsolidationNotFoundError("legal entity not found")
    return row


async def list_legal_entities(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    status: str | None = None,
    limit: int = 200,
) -> list[LegalEntity]:
    statement = select(LegalEntity).where(LegalEntity.workspace_id == workspace_id)
    if status:
        statement = statement.where(LegalEntity.status == status)
    statement = statement.order_by(LegalEntity.code).limit(max(1, min(limit, 500)))
    return list((await session.execute(statement)).scalars().all())


async def create_brand(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    code: str,
    name: str,
    status: str,
    default_legal_entity_id: UUID | None,
    notes: str | None,
    actor: str,
) -> Brand:
    normalized_code = _normalize_code(code)
    normalized_actor = _require_actor(actor)
    existing = (
        await session.execute(
            select(Brand.id).where(
                Brand.workspace_id == workspace_id,
                Brand.code == normalized_code,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConsolidationConflictError(f"brand code already exists: {normalized_code}")
    if default_legal_entity_id is not None:
        await get_legal_entity(
            session,
            workspace_id=workspace_id,
            legal_entity_id=default_legal_entity_id,
        )
    row = Brand(
        workspace_id=workspace_id,
        code=normalized_code,
        name=name.strip(),
        status=status,
        default_legal_entity_id=default_legal_entity_id,
        notes=notes.strip() if notes else None,
        created_by=normalized_actor,
    )
    session.add(row)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="consolidation.brand_created",
        entity_type="brand",
        entity_id=str(row.id),
        payload={"code": row.code, "actor": normalized_actor},
    )
    return row


async def update_brand(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    brand_id: UUID,
    changes: dict[str, Any],
    actor: str,
) -> Brand:
    row = await get_brand(
        session,
        workspace_id=workspace_id,
        brand_id=brand_id,
    )
    normalized_actor = _require_actor(actor)
    if "default_legal_entity_id" in changes:
        value = changes["default_legal_entity_id"]
        if value is not None:
            await get_legal_entity(
                session,
                workspace_id=workspace_id,
                legal_entity_id=UUID(str(value)),
            )
            changes["default_legal_entity_id"] = UUID(str(value))
    if "name" in changes and changes["name"] is not None:
        changes["name"] = str(changes["name"]).strip()
    for key, value in changes.items():
        if key not in {
            "name",
            "status",
            "default_legal_entity_id",
            "notes",
        }:
            raise ConsolidationError(f"unsupported brand field: {key}")
        setattr(row, key, value)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="consolidation.brand_updated",
        entity_type="brand",
        entity_id=str(row.id),
        payload={"changed_fields": sorted(changes), "actor": normalized_actor},
    )
    await session.refresh(row)
    return row


async def get_brand(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    brand_id: UUID,
) -> Brand:
    row = (
        await session.execute(
            select(Brand).where(
                Brand.workspace_id == workspace_id,
                Brand.id == brand_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise ConsolidationNotFoundError("brand not found")
    return row


async def list_brands(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    status: str | None = None,
    limit: int = 200,
) -> list[Brand]:
    statement = select(Brand).where(Brand.workspace_id == workspace_id)
    if status:
        statement = statement.where(Brand.status == status)
    statement = statement.order_by(Brand.code).limit(max(1, min(limit, 500)))
    return list((await session.execute(statement)).scalars().all())


async def assign_product_brand(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    brand_id: UUID,
    actor: str,
) -> tuple[Product, Brand]:
    product = (
        await session.execute(
            select(Product).where(
                Product.workspace_id == workspace_id,
                Product.id == product_id,
            )
        )
    ).scalar_one_or_none()
    if product is None:
        raise ConsolidationNotFoundError("product not found")
    brand = await get_brand(
        session,
        workspace_id=workspace_id,
        brand_id=brand_id,
    )
    product.brand_id = brand.id
    product.brand = brand.name
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="consolidation.product_brand_assigned",
        entity_type="product",
        entity_id=str(product.id),
        payload={"brand_id": str(brand.id), "actor": _require_actor(actor)},
    )
    return product, brand


async def _entity_snapshot(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    entity_type: str,
    entity_id: UUID,
) -> dict[str, Any]:
    if entity_type not in ATTRIBUTION_ENTITY_TYPES:
        raise ConsolidationError(f"unsupported attribution entity type: {entity_type}")

    if entity_type == "b2c_order":
        order = (
            await session.execute(
                select(Order).where(
                    Order.workspace_id == workspace_id,
                    Order.id == entity_id,
                )
            )
        ).scalar_one_or_none()
        if order is None:
            raise ConsolidationNotFoundError("B2C order not found")
        items = list(
            (
                await session.execute(
                    select(OrderItem).where(OrderItem.order_id == order.id)
                )
            )
            .scalars()
            .all()
        )
        return {
            "entity_type": entity_type,
            "entity_id": order.id,
            "amount": _money(order.total),
            "currency": order.currency,
            "business_model": "B2C",
            "product_ids": {row.product_id for row in items if row.product_id},
            "skus": {row.sku for row in items if row.sku},
            "occurred_at": order.received_at,
        }

    if entity_type == "b2b_order":
        order = (
            await session.execute(
                select(B2BOrder).where(
                    B2BOrder.workspace_id == workspace_id,
                    B2BOrder.id == entity_id,
                )
            )
        ).scalar_one_or_none()
        if order is None:
            raise ConsolidationNotFoundError("B2B order not found")
        items = list(
            (
                await session.execute(
                    select(B2BOrderItem).where(B2BOrderItem.order_id == order.id)
                )
            )
            .scalars()
            .all()
        )
        return {
            "entity_type": entity_type,
            "entity_id": order.id,
            "amount": _money(order.total),
            "currency": order.currency,
            "business_model": "B2B",
            "product_ids": {row.product_id for row in items},
            "skus": set(),
            "occurred_at": order.created_at,
        }

    invoice = (
        await session.execute(
            select(B2BInvoice).where(
                B2BInvoice.workspace_id == workspace_id,
                B2BInvoice.id == entity_id,
            )
        )
    ).scalar_one_or_none()
    if invoice is None:
        raise ConsolidationNotFoundError("B2B invoice not found")
    order = (
        await session.execute(
            select(B2BOrder).where(
                B2BOrder.workspace_id == workspace_id,
                B2BOrder.id == invoice.order_id,
            )
        )
    ).scalar_one()
    items = list(
        (
            await session.execute(
                select(B2BOrderItem).where(B2BOrderItem.order_id == order.id)
            )
        )
        .scalars()
        .all()
    )
    return {
        "entity_type": entity_type,
        "entity_id": invoice.id,
        "amount": _money(invoice.total),
        "currency": invoice.currency,
        "business_model": "B2B",
        "product_ids": {row.product_id for row in items},
        "skus": set(),
        "occurred_at": datetime.combine(
            invoice.issue_date,
            time.min,
            tzinfo=UTC,
        ),
        "order_id": order.id,
    }


async def _infer_dimensions(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    snapshot: dict[str, Any],
) -> tuple[UUID | None, UUID | None]:
    if snapshot["entity_type"] == "b2b_invoice":
        order_attribution = (
            await session.execute(
                select(CommerceAttribution).where(
                    CommerceAttribution.workspace_id == workspace_id,
                    CommerceAttribution.entity_type == "b2b_order",
                    CommerceAttribution.entity_id == snapshot["order_id"],
                )
            )
        ).scalar_one_or_none()
        if order_attribution is not None:
            return order_attribution.brand_id, order_attribution.legal_entity_id

    product_ids = set(snapshot["product_ids"])
    skus = set(snapshot["skus"])
    filters = [Product.workspace_id == workspace_id]
    if product_ids:
        filters.append(Product.id.in_(product_ids))
    elif skus:
        filters.append(Product.sku.in_(skus))
    else:
        return None, None
    product_rows = (
        await session.execute(select(Product).where(*filters))
    ).scalars().all()
    brand_ids = {row.brand_id for row in product_rows if row.brand_id}
    if len(brand_ids) != 1:
        return None, None
    brand_id = next(iter(brand_ids))
    brand = (
        await session.execute(
            select(Brand).where(
                Brand.workspace_id == workspace_id,
                Brand.id == brand_id,
            )
        )
    ).scalar_one_or_none()
    return brand_id, brand.default_legal_entity_id if brand else None


async def ensure_attribution(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    entity_type: str,
    entity_id: UUID,
    actor: str,
    trace_id: str | None = None,
    commit_event: bool = True,
) -> CommerceAttribution | None:
    existing = (
        await session.execute(
            select(CommerceAttribution).where(
                CommerceAttribution.workspace_id == workspace_id,
                CommerceAttribution.entity_type == entity_type,
                CommerceAttribution.entity_id == entity_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    snapshot = await _entity_snapshot(
        session,
        workspace_id=workspace_id,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    brand_id, legal_entity_id = await _infer_dimensions(
        session,
        workspace_id=workspace_id,
        snapshot=snapshot,
    )
    if brand_id is None and legal_entity_id is None:
        return None
    row = CommerceAttribution(
        workspace_id=workspace_id,
        entity_type=entity_type,
        entity_id=entity_id,
        brand_id=brand_id,
        legal_entity_id=legal_entity_id,
        assignment_source="auto",
        assigned_by=_require_actor(actor),
    )
    session.add(row)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="consolidation.attribution_auto_assigned",
        entity_type="commerce_attribution",
        entity_id=str(row.id),
        payload={
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "brand_id": str(brand_id) if brand_id else None,
            "legal_entity_id": str(legal_entity_id) if legal_entity_id else None,
            "actor": _require_actor(actor),
        },
        trace_id=trace_id,
        commit=commit_event,
    )
    return row


async def upsert_attribution(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    entity_type: str,
    entity_id: UUID,
    brand_id: UUID,
    legal_entity_id: UUID,
    is_intercompany: bool,
    counterparty_legal_entity_id: UUID | None,
    evidence: dict[str, Any],
    actor: str,
    trace_id: str | None = None,
) -> CommerceAttribution:
    await _entity_snapshot(
        session,
        workspace_id=workspace_id,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    await get_brand(session, workspace_id=workspace_id, brand_id=brand_id)
    await get_legal_entity(
        session,
        workspace_id=workspace_id,
        legal_entity_id=legal_entity_id,
    )
    if is_intercompany:
        if counterparty_legal_entity_id is None:
            raise ConsolidationError(
                "counterparty legal entity is required for intercompany facts"
            )
        if counterparty_legal_entity_id == legal_entity_id:
            raise ConsolidationError(
                "counterparty legal entity must differ from the seller legal entity"
            )
        await get_legal_entity(
            session,
            workspace_id=workspace_id,
            legal_entity_id=counterparty_legal_entity_id,
        )
    else:
        counterparty_legal_entity_id = None

    row = (
        await session.execute(
            select(CommerceAttribution).where(
                CommerceAttribution.workspace_id == workspace_id,
                CommerceAttribution.entity_type == entity_type,
                CommerceAttribution.entity_id == entity_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = CommerceAttribution(
            workspace_id=workspace_id,
            entity_type=entity_type,
            entity_id=entity_id,
            assigned_by=_require_actor(actor),
        )
        session.add(row)

    row.brand_id = brand_id
    row.legal_entity_id = legal_entity_id
    row.assignment_source = "manual"
    row.assigned_by = _require_actor(actor)
    row.is_intercompany = is_intercompany
    row.counterparty_legal_entity_id = counterparty_legal_entity_id
    row.evidence = evidence
    row.elimination_status = "pending" if is_intercompany else "not_applicable"
    row.elimination_amount = ZERO
    row.approved_by = None
    row.approved_at = None
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="consolidation.attribution_updated",
        entity_type="commerce_attribution",
        entity_id=str(row.id),
        payload={
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "brand_id": str(brand_id),
            "legal_entity_id": str(legal_entity_id),
            "is_intercompany": is_intercompany,
            "actor": _require_actor(actor),
        },
        trace_id=trace_id,
    )
    await session.refresh(row)
    return row


async def _get_attribution(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    attribution_id: UUID,
) -> CommerceAttribution:
    row = (
        await session.execute(
            select(CommerceAttribution).where(
                CommerceAttribution.workspace_id == workspace_id,
                CommerceAttribution.id == attribution_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise ConsolidationNotFoundError("attribution not found")
    return row


async def approve_elimination(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    attribution_id: UUID,
    amount: Decimal,
    evidence: dict[str, Any],
    actor: str,
    trace_id: str | None = None,
) -> CommerceAttribution:
    row = await _get_attribution(
        session,
        workspace_id=workspace_id,
        attribution_id=attribution_id,
    )
    if not row.is_intercompany:
        raise ConsolidationStateError(
            "elimination approval requires an intercompany attribution"
        )
    if row.elimination_status not in {"pending", "rejected"}:
        raise ConsolidationStateError("elimination is not awaiting approval")
    snapshot = await _entity_snapshot(
        session,
        workspace_id=workspace_id,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
    )
    normalized_amount = _money(amount)
    if normalized_amount <= ZERO:
        raise ConsolidationError("elimination amount must be greater than zero")
    if normalized_amount > snapshot["amount"]:
        raise ConsolidationError("elimination amount cannot exceed the source total")
    row.elimination_amount = normalized_amount
    row.elimination_status = "approved"
    row.evidence = {**(row.evidence or {}), **evidence}
    row.approved_by = _require_actor(actor)
    row.approved_at = datetime.now(UTC)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="consolidation.elimination_approved",
        entity_type="commerce_attribution",
        entity_id=str(row.id),
        payload={
            "entity_type": row.entity_type,
            "entity_id": str(row.entity_id),
            "amount": str(row.elimination_amount),
            "currency": snapshot["currency"],
            "actor": _require_actor(actor),
        },
        trace_id=trace_id,
    )
    await session.refresh(row)
    return row


async def reject_elimination(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    attribution_id: UUID,
    evidence: dict[str, Any],
    actor: str,
    trace_id: str | None = None,
) -> CommerceAttribution:
    row = await _get_attribution(
        session,
        workspace_id=workspace_id,
        attribution_id=attribution_id,
    )
    if not row.is_intercompany or row.elimination_status not in {
        "pending",
        "approved",
    }:
        raise ConsolidationStateError("elimination is not awaiting a decision")
    row.elimination_status = "rejected"
    row.elimination_amount = ZERO
    row.evidence = {**(row.evidence or {}), **evidence}
    row.approved_by = None
    row.approved_at = None
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="consolidation.elimination_rejected",
        entity_type="commerce_attribution",
        entity_id=str(row.id),
        payload={"actor": _require_actor(actor)},
        trace_id=trace_id,
    )
    await session.refresh(row)
    return row


async def get_attribution(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    entity_type: str,
    entity_id: UUID,
) -> CommerceAttribution | None:
    return (
        await session.execute(
            select(CommerceAttribution).where(
                CommerceAttribution.workspace_id == workspace_id,
                CommerceAttribution.entity_type == entity_type,
                CommerceAttribution.entity_id == entity_id,
            )
        )
    ).scalar_one_or_none()


async def list_attributions(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    entity_type: str | None = None,
    elimination_status: str | None = None,
    limit: int = 200,
) -> list[CommerceAttribution]:
    statement = select(CommerceAttribution).where(
        CommerceAttribution.workspace_id == workspace_id
    )
    if entity_type:
        statement = statement.where(CommerceAttribution.entity_type == entity_type)
    if elimination_status:
        statement = statement.where(
            CommerceAttribution.elimination_status == elimination_status
        )
    statement = statement.order_by(CommerceAttribution.created_at.desc()).limit(
        max(1, min(limit, 500))
    )
    return list((await session.execute(statement)).scalars().all())


async def list_product_brand_gaps(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    search: str | None = None,
    limit: int = 200,
) -> list[Any]:
    from app.schemas.consolidation import ProductBrandGapResponse

    statement = select(Product).where(
        Product.workspace_id == workspace_id,
        Product.brand_id.is_(None),
    )
    if search:
        normalized_search = search.strip()
        if normalized_search:
            pattern = f"%{normalized_search}%"
            statement = statement.where(
                or_(
                    Product.sku.ilike(pattern),
                    Product.name.ilike(pattern),
                )
            )
    statement = statement.order_by(Product.created_at.desc()).limit(
        max(1, min(limit, 500))
    )
    rows = list((await session.execute(statement)).scalars().all())
    return [
        ProductBrandGapResponse(
            product_id=str(row.id),
            sku=row.sku,
            name=row.name,
            status=row.status,
            category=row.category,
            legacy_brand=row.brand,
            created_at=row.created_at,
        )
        for row in rows
    ]


async def assign_product_brands(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_ids: list[str],
    brand_id: UUID,
    actor: str,
) -> Any:
    from app.schemas.consolidation import (
        ProductBrandBulkAssignItem,
        ProductBrandBulkAssignResponse,
    )

    brand = await get_brand(
        session,
        workspace_id=workspace_id,
        brand_id=brand_id,
    )
    normalized_actor = _require_actor(actor)
    unique_product_ids = list(dict.fromkeys(product_ids))
    results: list[ProductBrandBulkAssignItem] = []
    assigned_count = 0
    skipped_count = 0
    failed_count = 0

    for raw_product_id in unique_product_ids:
        try:
            product_id = UUID(str(raw_product_id))
        except (TypeError, ValueError):
            failed_count += 1
            results.append(
                ProductBrandBulkAssignItem(
                    product_id=str(raw_product_id),
                    sku=None,
                    status="failed",
                    error="invalid product id",
                )
            )
            continue

        product = (
            await session.execute(
                select(Product).where(
                    Product.workspace_id == workspace_id,
                    Product.id == product_id,
                )
            )
        ).scalar_one_or_none()
        if product is None:
            failed_count += 1
            results.append(
                ProductBrandBulkAssignItem(
                    product_id=str(product_id),
                    sku=None,
                    status="not_found",
                    error="product not found in workspace",
                )
            )
            continue
        if product.brand_id == brand.id:
            skipped_count += 1
            results.append(
                ProductBrandBulkAssignItem(
                    product_id=str(product.id),
                    sku=product.sku,
                    status="already_assigned",
                    error=None,
                )
            )
            continue
        if product.brand_id is not None:
            skipped_count += 1
            results.append(
                ProductBrandBulkAssignItem(
                    product_id=str(product.id),
                    sku=product.sku,
                    status="already_assigned",
                    error="product already has a different brand",
                )
            )
            continue

        product.brand_id = brand.id
        product.brand = brand.name
        await session.flush()
        await event_service.create_event(
            session,
            workspace_id=workspace_id,
            event_type="consolidation.product_brand_bulk_assigned",
            entity_type="product",
            entity_id=str(product.id),
            payload={
                "brand_id": str(brand.id),
                "brand_code": brand.code,
                "actor": normalized_actor,
            },
            commit=False,
        )
        assigned_count += 1
        results.append(
            ProductBrandBulkAssignItem(
                product_id=str(product.id),
                sku=product.sku,
                status="assigned",
                error=None,
            )
        )

    if assigned_count:
        await session.commit()

    return ProductBrandBulkAssignResponse(
        requested=len(product_ids),
        assigned=assigned_count,
        skipped=skipped_count,
        failed=failed_count,
        items=results,
    )


async def _diagnose_attribution_dimensions(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    snapshot: dict[str, Any],
) -> tuple[UUID | None, UUID | None, str]:
    if snapshot["entity_type"] == "b2b_invoice":
        order_attribution = (
            await session.execute(
                select(CommerceAttribution).where(
                    CommerceAttribution.workspace_id == workspace_id,
                    CommerceAttribution.entity_type == "b2b_order",
                    CommerceAttribution.entity_id == snapshot["order_id"],
                )
            )
        ).scalar_one_or_none()
        if order_attribution is not None:
            return (
                order_attribution.brand_id,
                order_attribution.legal_entity_id,
                "ready_from_order",
            )

    product_ids = set(snapshot["product_ids"])
    skus = set(snapshot["skus"])
    filters = [Product.workspace_id == workspace_id]
    if product_ids:
        filters.append(Product.id.in_(product_ids))
    elif skus:
        filters.append(Product.sku.in_(skus))
    else:
        return None, None, "missing_product_reference"

    product_rows = list(
        (await session.execute(select(Product).where(*filters))).scalars().all()
    )
    if not product_rows:
        return None, None, "product_not_found"
    brand_ids = {row.brand_id for row in product_rows if row.brand_id}
    if not brand_ids:
        return None, None, "missing_product_brand"
    if len(brand_ids) > 1:
        return None, None, "mixed_brand"

    brand_id = next(iter(brand_ids))
    brand = (
        await session.execute(
            select(Brand).where(
                Brand.workspace_id == workspace_id,
                Brand.id == brand_id,
            )
        )
    ).scalar_one_or_none()
    if brand is None:
        return None, None, "product_brand_not_found"
    if brand.default_legal_entity_id is None:
        return brand.id, None, "missing_default_legal_entity"
    return brand.id, brand.default_legal_entity_id, "ready"


async def list_attribution_gaps(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    entity_type: str | None = None,
    limit: int = 200,
) -> list[Any]:
    from app.schemas.consolidation import AttributionGapResponse

    normalized_limit = max(1, min(limit, 500))
    candidates: list[dict[str, Any]] = []
    if entity_type in {None, "b2c_order"}:
        orders = list(
            (
                await session.execute(
                    select(Order)
                    .where(
                        Order.workspace_id == workspace_id,
                        Order.status != "cancelled",
                    )
                    .order_by(Order.received_at.desc())
                    .limit(normalized_limit)
                )
            )
            .scalars()
            .all()
        )
        candidates.extend(
            {
                "entity_type": "b2c_order",
                "entity_id": row.id,
                "reference": row.external_order_id,
                "occurred_at": _as_utc(row.received_at),
                "business_model": "B2C",
                "amount": row.total,
                "currency": row.currency,
            }
            for row in orders
        )
    if entity_type in {None, "b2b_order"}:
        orders = list(
            (
                await session.execute(
                    select(B2BOrder)
                    .where(
                        B2BOrder.workspace_id == workspace_id,
                        B2BOrder.status != "cancelled",
                    )
                    .order_by(B2BOrder.created_at.desc())
                    .limit(normalized_limit)
                )
            )
            .scalars()
            .all()
        )
        candidates.extend(
            {
                "entity_type": "b2b_order",
                "entity_id": row.id,
                "reference": row.order_number,
                "occurred_at": _as_utc(row.created_at),
                "business_model": "B2B",
                "amount": row.total,
                "currency": row.currency,
            }
            for row in orders
        )
    if entity_type in {None, "b2b_invoice"}:
        invoices = list(
            (
                await session.execute(
                    select(B2BInvoice)
                    .where(
                        B2BInvoice.workspace_id == workspace_id,
                        B2BInvoice.status.notin_(("draft", "voided")),
                    )
                    .order_by(B2BInvoice.issue_date.desc())
                    .limit(normalized_limit)
                )
            )
            .scalars()
            .all()
        )
        candidates.extend(
            {
                "entity_type": "b2b_invoice",
                "entity_id": row.id,
                "reference": row.invoice_number,
                "occurred_at": datetime.combine(
                    row.issue_date,
                    time.min,
                    tzinfo=UTC,
                ),
                "business_model": "B2B",
                "amount": row.total,
                "currency": row.currency,
            }
            for row in invoices
        )

    entity_ids = {candidate["entity_id"] for candidate in candidates}
    attributed_ids: set[tuple[str, UUID]] = set()
    if entity_ids:
        attributed_ids = {
            (row.entity_type, row.entity_id)
            for row in (
                await session.execute(
                    select(CommerceAttribution).where(
                        CommerceAttribution.workspace_id == workspace_id,
                        CommerceAttribution.entity_id.in_(entity_ids),
                    )
                )
            )
            .scalars()
            .all()
        }

    gap_candidates = [
        candidate
        for candidate in candidates
        if (candidate["entity_type"], candidate["entity_id"]) not in attributed_ids
    ]
    gap_candidates.sort(
        key=lambda candidate: candidate["occurred_at"],
        reverse=True,
    )
    gap_candidates = gap_candidates[:normalized_limit]

    brand_cache: dict[UUID, Brand | None] = {}
    legal_entity_cache: dict[UUID, LegalEntity | None] = {}
    results: list[AttributionGapResponse] = []
    for candidate in gap_candidates:
        snapshot = await _entity_snapshot(
            session,
            workspace_id=workspace_id,
            entity_type=candidate["entity_type"],
            entity_id=candidate["entity_id"],
        )
        suggested_brand_id, suggested_legal_entity_id, reason = (
            await _diagnose_attribution_dimensions(
                session,
                workspace_id=workspace_id,
                snapshot=snapshot,
            )
        )
        suggested_brand: Brand | None = None
        if suggested_brand_id is not None:
            if suggested_brand_id not in brand_cache:
                brand_cache[suggested_brand_id] = (
                    await session.execute(
                        select(Brand).where(
                            Brand.workspace_id == workspace_id,
                            Brand.id == suggested_brand_id,
                        )
                    )
                ).scalar_one_or_none()
            suggested_brand = brand_cache[suggested_brand_id]
        suggested_legal_entity: LegalEntity | None = None
        if suggested_legal_entity_id is not None:
            if suggested_legal_entity_id not in legal_entity_cache:
                legal_entity_cache[suggested_legal_entity_id] = (
                    await session.execute(
                        select(LegalEntity).where(
                            LegalEntity.workspace_id == workspace_id,
                            LegalEntity.id == suggested_legal_entity_id,
                        )
                    )
                ).scalar_one_or_none()
            suggested_legal_entity = legal_entity_cache[suggested_legal_entity_id]
        product_ids = set(snapshot["product_ids"])
        sample_skus = sorted(str(sku) for sku in snapshot["skus"] if sku)[:5]
        if not sample_skus and product_ids:
            products = list(
                (
                    await session.execute(
                        select(Product).where(
                            Product.workspace_id == workspace_id,
                            Product.id.in_(product_ids),
                        )
                    )
                )
                .scalars()
                .all()
            )
            sample_skus = sorted(row.sku for row in products)[:5]
        results.append(
            AttributionGapResponse(
                entity_type=candidate["entity_type"],
                entity_id=str(candidate["entity_id"]),
                reference=candidate["reference"],
                occurred_at=candidate["occurred_at"],
                business_model=candidate["business_model"],
                amount=_money(candidate["amount"]),
                currency=candidate["currency"],
                reason=reason,
                product_count=len(product_ids) or len(snapshot["skus"]),
                sample_skus=sample_skus,
                suggested_brand_id=(
                    str(suggested_brand.id)
                    if suggested_brand is not None
                    else str(suggested_brand_id)
                    if suggested_brand_id is not None
                    else None
                ),
                suggested_brand_name=(
                    suggested_brand.name if suggested_brand is not None else None
                ),
                suggested_legal_entity_id=(
                    str(suggested_legal_entity.id)
                    if suggested_legal_entity is not None
                    else str(suggested_legal_entity_id)
                    if suggested_legal_entity_id is not None
                    else None
                ),
                suggested_legal_entity_name=(
                    suggested_legal_entity.name
                    if suggested_legal_entity is not None
                    else None
                ),
            )
        )
    return results


async def reconcile_attribution_gaps(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    actor: str,
    entity_type: str | None = None,
    limit: int = 200,
    trace_id: str | None = None,
) -> Any:
    from app.schemas.consolidation import (
        AttributionReconcileItem,
        AttributionReconcileResponse,
    )

    gaps = await list_attribution_gaps(
        session,
        workspace_id=workspace_id,
        entity_type=entity_type,
        limit=limit,
    )
    items: list[AttributionReconcileItem] = []
    created_count = 0
    skipped_count = 0
    for gap in gaps:
        if gap.reason not in {"ready", "ready_from_order"}:
            skipped_count += 1
            items.append(
                AttributionReconcileItem(
                    entity_type=gap.entity_type,
                    entity_id=gap.entity_id,
                    reference=gap.reference,
                    status="skipped",
                    reason=gap.reason,
                )
            )
            continue
        attribution = await ensure_attribution(
            session,
            workspace_id=workspace_id,
            entity_type=gap.entity_type,
            entity_id=UUID(gap.entity_id),
            actor=actor,
            trace_id=trace_id,
            commit_event=False,
        )
        if attribution is None:
            skipped_count += 1
            items.append(
                AttributionReconcileItem(
                    entity_type=gap.entity_type,
                    entity_id=gap.entity_id,
                    reference=gap.reference,
                    status="skipped",
                    reason="not_eligible",
                )
            )
            continue
        created_count += 1
        items.append(
            AttributionReconcileItem(
                entity_type=gap.entity_type,
                entity_id=gap.entity_id,
                reference=gap.reference,
                status="created",
                reason=gap.reason,
            )
        )
    if created_count:
        await session.commit()
    return AttributionReconcileResponse(
        attempted=len(gaps),
        created=created_count,
        skipped=skipped_count,
        items=items,
    )


async def _latest_b2b_costs(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_ids: set[UUID],
) -> dict[UUID, tuple[Decimal, str, date]]:
    if not product_ids:
        return {}
    rows = (
        await session.execute(
            select(ProductCost)
            .where(
                ProductCost.workspace_id == workspace_id,
                ProductCost.product_id.in_(product_ids),
            )
            .order_by(ProductCost.product_id, ProductCost.valid_from.desc())
        )
    ).scalars().all()
    result: dict[UUID, tuple[Decimal, str, date]] = {}
    for row in rows:
        unit_cost = (
            row.total_landed_cost
            if row.total_landed_cost and row.total_landed_cost > ZERO
            else row.total_cost
        )
        result.setdefault(
            row.product_id,
            (unit_cost, row.currency, row.valid_from.date()),
        )
    return result


def _row_bucket() -> dict[str, Any]:
    return {
        "gross_revenue": ZERO,
        "intercompany_revenue": ZERO,
        "external_revenue": ZERO,
        "orders": 0,
        "open_receivables": ZERO,
        "profit_revenue": ZERO,
        "gross_profit": ZERO,
        "profit_rows": 0,
        "attributed_orders": 0,
        "complete_attribution_orders": 0,
        "pending_elimination_orders": 0,
    }


async def build_consolidated_report(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    start_date: date,
    end_date: date,
    reporting_currency: str | None = None,
    brand_id: UUID | None = None,
    legal_entity_id: UUID | None = None,
    limit: int = 50,
) -> Any:
    from app.schemas.consolidation import (
        ConsolidatedPerformanceRow,
        ConsolidatedReportResponse,
        ConsolidatedTotals,
        ConsolidationDataQuality,
    )

    if start_date > end_date:
        raise ConsolidationError("start_date must be on or before end_date")
    if (end_date - start_date).days > 366:
        raise ConsolidationError("report range cannot exceed 366 days")
    if limit < 1 or limit > 200:
        raise ConsolidationError("limit must be between 1 and 200")
    if brand_id is not None:
        await get_brand(session, workspace_id=workspace_id, brand_id=brand_id)
    if legal_entity_id is not None:
        await get_legal_entity(
            session,
            workspace_id=workspace_id,
            legal_entity_id=legal_entity_id,
        )

    normalized_reporting_currency = (
        currency_service.normalize_currency_code(reporting_currency)
        if reporting_currency
        else None
    )
    start_at = datetime.combine(start_date, time.min, tzinfo=UTC)
    end_at = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=UTC)
    rate_cache: dict[tuple[str, str, date], Any] = {}

    async def convert(
        amount: Decimal | None,
        source_currency: str,
        rate_date: date,
    ) -> Decimal:
        value = _decimal(amount) or ZERO
        if normalized_reporting_currency is None:
            return value
        return await currency_service.convert_amount(
            session,
            workspace_id=workspace_id,
            amount=value,
            base_currency=source_currency,
            quote_currency=normalized_reporting_currency,
            as_of=rate_date,
            rate_cache=rate_cache,
        )

    b2c_orders = list(
        (
            await session.execute(
                select(Order).where(
                    Order.workspace_id == workspace_id,
                    Order.business_model == "B2C",
                    Order.status != "cancelled",
                    Order.received_at >= start_at,
                    Order.received_at < end_at,
                )
            )
        )
        .scalars()
        .all()
    )
    b2b_orders = list(
        (
            await session.execute(
                select(B2BOrder).where(
                    B2BOrder.workspace_id == workspace_id,
                    B2BOrder.status != "cancelled",
                    B2BOrder.created_at >= start_at,
                    B2BOrder.created_at < end_at,
                )
            )
        )
        .scalars()
        .all()
    )
    b2c_items = list(
        (
            await session.execute(
                select(OrderItem).where(
                    OrderItem.order_id.in_([row.id for row in b2c_orders])
                )
            )
        )
        .scalars()
        .all()
    ) if b2c_orders else []
    b2b_items = list(
        (
            await session.execute(
                select(B2BOrderItem).where(
                    B2BOrderItem.order_id.in_([row.id for row in b2b_orders])
                )
            )
        )
        .scalars()
        .all()
    ) if b2b_orders else []
    b2b_order_ids = {row.id for row in b2b_orders}
    invoice_rows = list(
        (
            await session.execute(
                select(B2BInvoice).where(
                    B2BInvoice.workspace_id == workspace_id,
                    B2BInvoice.balance_due > ZERO,
                    B2BInvoice.status.in_(("issued", "partially_paid", "overdue")),
                )
            )
        )
        .scalars()
        .all()
    )

    entity_ids = (
        {row.id for row in b2c_orders}
        | b2b_order_ids
        | {row.id for row in invoice_rows}
    )
    attribution_rows = list(
        (
            await session.execute(
                select(CommerceAttribution).where(
                    CommerceAttribution.workspace_id == workspace_id,
                    CommerceAttribution.entity_type.in_(ATTRIBUTION_ENTITY_TYPES),
                    CommerceAttribution.entity_id.in_(entity_ids),
                )
            )
        )
        .scalars()
        .all()
    ) if entity_ids else []
    attributions = {
        (row.entity_type, row.entity_id): row for row in attribution_rows
    }

    brand_ids = {
        row.brand_id for row in attribution_rows if row.brand_id is not None
    }
    legal_entity_ids = {
        row.legal_entity_id
        for row in attribution_rows
        if row.legal_entity_id is not None
    } | {
        row.counterparty_legal_entity_id
        for row in attribution_rows
        if row.counterparty_legal_entity_id is not None
    }
    brands = {
        row.id: row
        for row in (
            await session.execute(
                select(Brand).where(
                    Brand.workspace_id == workspace_id,
                    Brand.id.in_(brand_ids),
                )
            )
        ).scalars().all()
    } if brand_ids else {}
    legal_entities = {
        row.id: row
        for row in (
            await session.execute(
                select(LegalEntity).where(
                    LegalEntity.workspace_id == workspace_id,
                    LegalEntity.id.in_(legal_entity_ids),
                )
            )
        ).scalars().all()
    } if legal_entity_ids else {}

    product_ids = {
        row.product_id for row in [*b2c_items, *b2b_items] if row.product_id
    }
    latest_costs = await _latest_b2b_costs(
        session,
        workspace_id=workspace_id,
        product_ids=product_ids,
    )
    b2b_items_by_order: dict[UUID, list[B2BOrderItem]] = defaultdict(list)
    for item in b2b_items:
        b2b_items_by_order[item.order_id].append(item)

    buckets: dict[tuple[UUID | None, UUID | None, str, str], dict[str, Any]] = (
        defaultdict(_row_bucket)
    )

    def matches_filters(
        resolved_brand_id: UUID | None,
        resolved_legal_entity_id: UUID | None,
    ) -> bool:
        return not (
            (brand_id is not None and resolved_brand_id != brand_id)
            or (
                legal_entity_id is not None
                and resolved_legal_entity_id != legal_entity_id
            )
        )

    total_orders = 0
    complete_order_rows = 0
    pending_elimination_orders = 0

    async def add_order(
        *,
        entity_type: str,
        entity_id: UUID,
        business_model: str,
        amount: Decimal,
        currency: str,
        rate_date: date,
        margin: Decimal | None,
        margin_currency: str,
        margin_rate_date: date,
    ) -> None:
        nonlocal total_orders, complete_order_rows
        nonlocal pending_elimination_orders
        attribution = attributions.get((entity_type, entity_id))
        resolved_brand_id = attribution.brand_id if attribution else None
        resolved_legal_entity_id = attribution.legal_entity_id if attribution else None
        if not matches_filters(resolved_brand_id, resolved_legal_entity_id):
            return

        total_orders += 1
        is_complete = (
            resolved_brand_id is not None and resolved_legal_entity_id is not None
        )
        if is_complete:
            complete_order_rows += 1
        if attribution and attribution.elimination_status == "pending":
            pending_elimination_orders += 1

        summary_currency = normalized_reporting_currency or currency
        key = (
            resolved_brand_id,
            resolved_legal_entity_id,
            business_model,
            summary_currency,
        )
        bucket = buckets[key]
        gross_revenue = await convert(amount, currency, rate_date)
        bucket["gross_revenue"] += gross_revenue
        bucket["orders"] += 1
        if is_complete and attribution is not None:
            bucket["complete_attribution_orders"] += 1
        intercompany = ZERO
        if (
            attribution is not None
            and attribution.is_intercompany
            and attribution.elimination_status == "approved"
        ):
            intercompany = min(
                await convert(
                    attribution.elimination_amount,
                    currency,
                    rate_date,
                ),
                gross_revenue,
            )
        bucket["intercompany_revenue"] += intercompany
        bucket["external_revenue"] += gross_revenue - intercompany
        if margin is not None:
            converted_margin = await convert(
                margin,
                margin_currency,
                margin_rate_date,
            )
            bucket["profit_rows"] += 1
            bucket["profit_revenue"] += gross_revenue
            bucket["gross_profit"] += converted_margin

    for order in b2c_orders:
        await add_order(
            entity_type="b2c_order",
            entity_id=order.id,
            business_model="B2C",
            amount=order.total,
            currency=order.currency,
            rate_date=order.received_at.date(),
            margin=_snapshot_margin(order.profit_snapshot),
            margin_currency=order.currency,
            margin_rate_date=order.received_at.date(),
        )

    for order in b2b_orders:
        margin = ZERO
        margin_found = False
        for item in b2b_items_by_order.get(order.id, []):
            cost = latest_costs.get(item.product_id)
            if cost is None:
                continue
            unit_cost, cost_currency, cost_date = cost
            try:
                converted_unit_cost = await currency_service.convert_amount(
                    session,
                    workspace_id=workspace_id,
                    amount=unit_cost,
                    base_currency=cost_currency,
                    quote_currency=order.currency,
                    as_of=cost_date,
                    rate_cache=rate_cache,
                )
            except currency_service.ExchangeRateNotFoundError:
                continue
            margin += item.subtotal - converted_unit_cost * Decimal(item.quantity)
            margin_found = True
        await add_order(
            entity_type="b2b_order",
            entity_id=order.id,
            business_model="B2B",
            amount=order.total,
            currency=order.currency,
            rate_date=order.created_at.date(),
            margin=margin if margin_found else None,
            margin_currency=order.currency,
            margin_rate_date=order.created_at.date(),
        )

    order_attributions = {
        row.entity_id: row
        for row in attribution_rows
        if row.entity_type == "b2b_order"
    }
    for invoice in invoice_rows:
        attribution = attributions.get(("b2b_invoice", invoice.id))
        if attribution is None:
            attribution = order_attributions.get(invoice.order_id)
        resolved_brand_id = attribution.brand_id if attribution else None
        resolved_legal_entity_id = attribution.legal_entity_id if attribution else None
        if not matches_filters(resolved_brand_id, resolved_legal_entity_id):
            continue
        summary_currency = normalized_reporting_currency or invoice.currency
        key = (
            resolved_brand_id,
            resolved_legal_entity_id,
            "B2B",
            summary_currency,
        )
        bucket = buckets[key]
        balance = await convert(invoice.balance_due, invoice.currency, end_date)
        if (
            attribution is not None
            and attribution.is_intercompany
            and attribution.elimination_status == "approved"
        ):
            eliminated = await convert(
                attribution.elimination_amount,
                invoice.currency,
                end_date,
            )
            balance = max(balance - eliminated, ZERO)
        bucket["open_receivables"] += balance

    rows: list[ConsolidatedPerformanceRow] = []
    for (
        resolved_brand_id,
        resolved_legal_entity_id,
        business_model,
        currency,
    ), bucket in buckets.items():
        row_brand = brands.get(resolved_brand_id) if resolved_brand_id else None
        row_legal_entity = (
            legal_entities.get(resolved_legal_entity_id)
            if resolved_legal_entity_id
            else None
        )
        profit_revenue = bucket["profit_revenue"]
        gross_profit = (
            bucket["gross_profit"] if bucket["profit_rows"] > 0 else None
        )
        coverage = _percent(profit_revenue, bucket["gross_revenue"]) or ZERO
        complete = (
            bucket["orders"] > 0
            and bucket["complete_attribution_orders"] == bucket["orders"]
        )
        attribution_status = (
            "complete"
            if complete
            else "partial"
            if resolved_brand_id is not None or resolved_legal_entity_id is not None
            else "missing"
        )
        rows.append(
            ConsolidatedPerformanceRow(
                brand_id=str(resolved_brand_id) if resolved_brand_id else None,
                brand_name=row_brand.name if row_brand else "未归因品牌",
                legal_entity_id=(
                    str(resolved_legal_entity_id)
                    if resolved_legal_entity_id
                    else None
                ),
                legal_entity_name=(
                    row_legal_entity.name if row_legal_entity else "未归因法人"
                ),
                business_model=business_model,
                currency=currency,
                gross_revenue=_money(bucket["gross_revenue"]),
                intercompany_revenue=_money(bucket["intercompany_revenue"]),
                external_revenue=_money(bucket["external_revenue"]),
                orders=bucket["orders"],
                open_receivables=_money(bucket["open_receivables"]),
                profit_revenue=_money(profit_revenue),
                gross_profit=_money(gross_profit) if gross_profit is not None else None,
                gross_margin_percent=(
                    _percent(gross_profit, profit_revenue)
                    if gross_profit is not None
                    else None
                ),
                cost_coverage_percent=coverage,
                attribution_status=attribution_status,
            )
        )
    rows.sort(key=lambda row: row.gross_revenue, reverse=True)
    all_rows = rows
    rows = all_rows[:limit]

    currencies = {row.currency for row in all_rows}
    can_total = len(currencies) <= 1
    total_currency = next(iter(currencies)) if len(currencies) == 1 else None
    totals = ConsolidatedTotals(
        currency=total_currency,
        gross_revenue=(
            _money(sum((row.gross_revenue for row in all_rows), ZERO))
            if can_total
            else None
        ),
        intercompany_revenue=(
            _money(sum((row.intercompany_revenue for row in all_rows), ZERO))
            if can_total
            else None
        ),
        external_revenue=(
            _money(sum((row.external_revenue for row in all_rows), ZERO))
            if can_total
            else None
        ),
        gross_profit=(
            _money(sum((row.gross_profit or ZERO for row in all_rows), ZERO))
            if can_total and all(row.gross_profit is not None for row in all_rows)
            else None
        ),
        orders=sum(row.orders for row in all_rows),
    )

    attributed_percent = _percent(
        Decimal(complete_order_rows),
        Decimal(total_orders),
    )
    total_profit_revenue = sum((row.profit_revenue for row in all_rows), ZERO)
    total_gross_revenue = sum((row.gross_revenue for row in all_rows), ZERO)
    cost_coverage = (
        _percent(total_profit_revenue, total_gross_revenue) if can_total else None
    )
    if not rows or total_orders == 0:
        quality_status = "missing"
    elif (
        complete_order_rows == total_orders
        and pending_elimination_orders == 0
        and cost_coverage is not None
        and cost_coverage >= Decimal("99.99")
        and all(row.attribution_status == "complete" for row in all_rows)
    ):
        quality_status = "verified"
    else:
        quality_status = "partial"

    notes = [
        "Revenue is grouped by brand, legal entity, business model, and currency.",
        "Approved intercompany amounts reduce external revenue only after administrator review.",
        "Intercompany profit is not eliminated in this phase; paired buyer-side accounting is required for a group P&L.",
    ]
    if not can_total:
        notes.append(
            "Totals are omitted across currencies; select a reporting currency or review rows by currency."
        )
    if complete_order_rows < total_orders:
        notes.append(
            "Some operating facts are not fully attributed and are shown as unassigned dimensions."
        )
    if pending_elimination_orders:
        notes.append(
            "Pending intercompany eliminations remain in gross and external revenue until approved."
        )

    return ConsolidatedReportResponse(
        period={"start_date": start_date, "end_date": end_date},
        generated_at=datetime.now(UTC),
        reporting_currency=normalized_reporting_currency,
        brand_filter=str(brand_id) if brand_id else None,
        legal_entity_filter=str(legal_entity_id) if legal_entity_id else None,
        totals=totals,
        rows=rows,
        data_quality=ConsolidationDataQuality(
            status=quality_status,
            attributed_order_percent=attributed_percent,
            cost_coverage_percent=cost_coverage,
            notes=notes,
        ),
        notes=notes,
    )
