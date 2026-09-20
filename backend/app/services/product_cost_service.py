"""Product cost management service.

Provides the management/read layer that sits on top of the already-existing
authoritative ``ProductCost`` model and the contribution-margin engine:

- :func:`list_cost_overview` - one row per live product with its newest cost,
  reference B2C price and derived contribution margin (the /products/costs page).
- :func:`upsert_product_cost` - manual, versioned cost edit; appends an immutable
  ``ProductCostSnapshot`` and an audit event.
- :func:`profit_analysis` - single-product profitability breakdown.

No new table is introduced and the service never commits (the request-scoped
session owns the transaction, matching the rest of the service layer).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, or_, select

from app.models.product import Product, ProductCost
from app.models.product_intelligence import ProductCostSnapshot
from app.services import event_service
from app.services.profit_engine import ProfitInput, calculate_contribution_margin

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


class ProductCostError(Exception):
    """Domain error for product cost operations."""


def _money(value: Decimal | None) -> Decimal:
    return Decimal("0.00") if value is None else Decimal(value).quantize(CENT)


def bump_version(version: str | None) -> str:
    """Increment a ``vN`` version string (v1 -> v2), defaulting unknowns to v2."""
    try:
        number = int((version or "v1").removeprefix("v"))
    except ValueError:
        return "v2"
    return f"v{number + 1}"


def landed_breakdown(
    *,
    purchase_cost: Decimal,
    domestic_shipping: Decimal,
    first_leg_shipping: Decimal,
    last_leg_shipping: Decimal,
    international_shipping: Decimal | None,
    packaging: Decimal,
    tax_estimate: Decimal,
    handling: Decimal,
) -> tuple[Decimal, Decimal, Decimal]:
    """Return ``(international, total_landed, legacy_total)`` following PROFIT-001.

    ``international_shipping`` falls back to first-leg + last-leg, mirroring the
    intake pipeline so manual edits and AI intake share one cost definition.
    """
    international = (
        international_shipping
        if international_shipping is not None
        else first_leg_shipping + last_leg_shipping
    )
    total_landed = (
        purchase_cost
        + domestic_shipping
        + international
        + packaging
        + tax_estimate
        + handling
    )
    legacy_total = purchase_cost + domestic_shipping + first_leg_shipping + last_leg_shipping
    return _money(international), _money(total_landed), _money(legacy_total)


def sale_price_from_meta(meta: dict[str, Any] | None) -> Decimal | None:
    """Read the B2C reference price stored on ``Product.meta`` by Woo sync."""
    for key in ("sale_price", "regular_price", "price"):
        raw = (meta or {}).get(key)
        if raw in (None, "", 0, "0"):
            continue
        try:
            value = Decimal(str(raw))
        except (ArithmeticError, ValueError):
            continue
        if value > 0:
            return _money(value)
    return None


def period_cost(cost: ProductCost) -> Decimal:
    """Recurring per-unit period costs: payment + marketing amortization + after-sales."""
    return _money(
        cost.payment_fee + cost.marketing_amortization + cost.after_sales_loss
    )


async def latest_cost_for_product(
    session: AsyncSession, *, workspace_id: UUID, product_id: UUID
) -> ProductCost | None:
    rows = (
        (
            await session.execute(
                select(ProductCost)
                .where(
                    ProductCost.workspace_id == workspace_id,
                    ProductCost.product_id == product_id,
                )
                .order_by(ProductCost.valid_from.desc())
            )
        )
        .scalars()
        .all()
    )
    return rows[0] if rows else None


def _margin(sale_price: Decimal | None, cost: ProductCost) -> dict[str, Decimal | None]:
    """Derive contribution margin / rate from a reference price, if present."""
    if sale_price is None:
        return {"contribution_margin": None, "margin_rate": None}
    result = calculate_contribution_margin(
        ProfitInput(
            revenue=sale_price,
            product_cost=cost.total_landed_cost,
            payment_fee=cost.payment_fee,
            advertising_cost=cost.marketing_amortization,
            refund=cost.after_sales_loss,
        )
    )
    return {
        "contribution_margin": _money(result.contribution_margin),
        "margin_rate": result.contribution_margin_rate.quantize(Decimal("0.0001")),
    }


def _overview_row(product: Product, cost: ProductCost | None) -> dict[str, Any]:
    sale_price = sale_price_from_meta(product.meta)
    row: dict[str, Any] = {
        "product_id": product.id,
        "sku": product.sku,
        "name": product.name,
        "category": product.category,
        "target_market": product.target_market,
        "status": product.status,
        "has_cost": cost is not None,
        "currency": cost.currency if cost else None,
        "version": cost.version if cost else None,
        "valid_from": cost.valid_from if cost else None,
        "sale_price": sale_price,
        "purchase_cost": ZERO,
        "domestic_shipping": ZERO,
        "first_leg_shipping": ZERO,
        "last_leg_shipping": ZERO,
        "international_shipping": ZERO,
        "packaging": ZERO,
        "tax_estimate": ZERO,
        "handling": ZERO,
        "payment_fee": ZERO,
        "marketing_amortization": ZERO,
        "after_sales_loss": ZERO,
        "total_landed_cost": ZERO,
        "period_cost": ZERO,
        "contribution_margin": None,
        "margin_rate": None,
    }
    if cost is not None:
        row.update(
            {
                "purchase_cost": _money(cost.purchase_cost),
                "domestic_shipping": _money(cost.domestic_shipping),
                "first_leg_shipping": _money(cost.first_leg_shipping),
                "last_leg_shipping": _money(cost.last_leg_shipping),
                "international_shipping": _money(cost.international_shipping),
                "packaging": _money(cost.packaging),
                "tax_estimate": _money(cost.tax_estimate),
                "handling": _money(cost.handling),
                "payment_fee": _money(cost.payment_fee),
                "marketing_amortization": _money(cost.marketing_amortization),
                "after_sales_loss": _money(cost.after_sales_loss),
                "total_landed_cost": _money(cost.total_landed_cost),
                "period_cost": period_cost(cost),
                **_margin(sale_price, cost),
            }
        )
    return row


async def list_cost_overview(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    search: str | None = None,
    cost_status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Return per-product cost + derived profit overview for live products."""
    search_base = select(Product).where(
        Product.workspace_id == workspace_id,
        Product.deleted_at.is_(None),
    )
    if search:
        like = f"%{search.strip()}%"
        search_base = search_base.where(
            or_(
                Product.name.ilike(like),
                Product.sku.ilike(like),
                Product.category.ilike(like),
            )
        )

    cost_exists = (
        select(ProductCost.product_id)
        .where(ProductCost.workspace_id == workspace_id)
        .distinct()
    )

    # Coverage counters are scoped to the search (not the known/missing tab).
    coverage_total = (
        await session.execute(
            select(func.count()).select_from(search_base.subquery())
        )
    ).scalar_one()
    coverage_known = (
        await session.execute(
            select(func.count())
            .select_from(search_base.where(Product.id.in_(cost_exists)).subquery())
        )
    ).scalar_one()

    page_base = search_base
    if cost_status == "known":
        page_base = page_base.where(Product.id.in_(cost_exists))
    elif cost_status == "missing":
        page_base = page_base.where(~Product.id.in_(cost_exists))

    total = (
        await session.execute(
            select(func.count()).select_from(page_base.subquery())
        )
    ).scalar_one()
    products = (
        (
            await session.execute(
                page_base.order_by(Product.created_at.desc()).limit(limit).offset(offset)
            )
        )
        .scalars()
        .all()
    )
    costs = await _latest_cost_map(session, workspace_id, [p.id for p in products])
    items = [_overview_row(p, costs.get(p.id)) for p in products]

    return {
        "items": items,
        "total": total,
        "known": coverage_known,
        "missing": coverage_total - coverage_known,
    }


async def _latest_cost_map(
    session: AsyncSession, workspace_id: UUID, product_ids: list[UUID]
) -> dict[UUID, ProductCost]:
    if not product_ids:
        return {}
    rows = (
        (
            await session.execute(
                select(ProductCost)
                .where(
                    ProductCost.workspace_id == workspace_id,
                    ProductCost.product_id.in_(product_ids),
                )
                .order_by(ProductCost.valid_from.desc())
            )
        )
        .scalars()
        .all()
    )
    newest: dict[UUID, ProductCost] = {}
    for cost in rows:  # already newest-first; keep first occurrence per product
        newest.setdefault(cost.product_id, cost)
    return newest


async def upsert_product_cost(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    data: Any,
    trace_id: str | None,
) -> dict[str, Any]:
    """Create or version-bump a product's authoritative cost and log a snapshot."""
    product = (
        (
            await session.execute(
                select(Product).where(
                    Product.workspace_id == workspace_id,
                    Product.id == product_id,
                    Product.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .one_or_none()
    )
    if product is None:
        raise ProductCostError("product not found")

    international, landed, legacy_total = landed_breakdown(
        purchase_cost=data.purchase_cost,
        domestic_shipping=data.domestic_shipping,
        first_leg_shipping=data.first_leg_shipping,
        last_leg_shipping=data.last_leg_shipping,
        international_shipping=data.international_shipping,
        packaging=data.packaging,
        tax_estimate=data.tax_estimate,
        handling=data.handling,
    )

    cost = await latest_cost_for_product(
        session, workspace_id=workspace_id, product_id=product_id
    )
    common: dict[str, Any] = {
        "currency": data.currency,
        "purchase_cost": _money(data.purchase_cost),
        "domestic_shipping": _money(data.domestic_shipping),
        "first_leg_shipping": _money(data.first_leg_shipping),
        "last_leg_shipping": _money(data.last_leg_shipping),
        "international_shipping": international,
        "packaging": _money(data.packaging),
        "tax_estimate": _money(data.tax_estimate),
        "handling": _money(data.handling),
        "payment_fee": _money(data.payment_fee),
        "marketing_amortization": _money(data.marketing_amortization),
        "after_sales_loss": _money(data.after_sales_loss),
        "total_landed_cost": landed,
        "total_cost": legacy_total,
    }
    if cost is None:
        cost = ProductCost(
            workspace_id=workspace_id,
            product_id=product_id,
            version="v1",
            valid_from=datetime.now(UTC),
            **common,
        )
        session.add(cost)
        version = "v1"
    else:
        version = bump_version(cost.version)
        for field, value in common.items():
            setattr(cost, field, value)
        cost.version = version
        cost.valid_from = datetime.now(UTC)
    await session.flush()

    snapshot = ProductCostSnapshot(
        workspace_id=workspace_id,
        product_id=product_id,
        version=version,
        source="manual",
        weight_kg=product.weight_kg,
        trace_id=trace_id,
        **common,
    )
    session.add(snapshot)
    await session.flush()

    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="product.cost.updated",
        entity_type="product",
        entity_id=str(product_id),
        payload={
            "sku": product.sku,
            "version": version,
            "total_landed_cost": str(landed),
            "mode": "manual",
        },
        trace_id=trace_id,
        commit=False,
    )
    return {
        "product_id": product_id,
        "version": version,
        "total_landed_cost": landed,
        "snapshot_id": snapshot.id,
    }


async def profit_analysis(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    sale_price: Decimal | None = None,
) -> dict[str, Any]:
    """Single-product profit breakdown; withholds margin when cost/price missing."""
    product = (
        (
            await session.execute(
                select(Product).where(
                    Product.workspace_id == workspace_id,
                    Product.id == product_id,
                    Product.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .one_or_none()
    )
    if product is None:
        raise ProductCostError("product not found")

    cost = await latest_cost_for_product(
        session, workspace_id=workspace_id, product_id=product_id
    )
    price = _money(sale_price) if sale_price is not None else sale_price_from_meta(product.meta)

    result: dict[str, Any] = {
        "product_id": product.id,
        "sku": product.sku,
        "name": product.name,
        "currency": cost.currency if cost else "USD",
        "cost_status": "KNOWN" if cost is not None else "MISSING",
        "version": cost.version if cost else None,
        "valid_from": cost.valid_from if cost else None,
        "sale_price": price,
        "total_landed_cost": _money(cost.total_landed_cost) if cost else ZERO,
        "payment_fee": _money(cost.payment_fee) if cost else ZERO,
        "marketing_amortization": _money(cost.marketing_amortization) if cost else ZERO,
        "after_sales_loss": _money(cost.after_sales_loss) if cost else ZERO,
        "period_cost": period_cost(cost) if cost else ZERO,
        "total_cost": None,
        "contribution_margin": None,
        "contribution_margin_rate": None,
        "markup_rate": None,
        "breakeven_price": ZERO,
    }
    if cost is None:
        return result

    landed = _money(cost.total_landed_cost)
    period = period_cost(cost)
    result["breakeven_price"] = _money(landed + period)
    if price is None:
        return result

    margin = calculate_contribution_margin(
        ProfitInput(
            revenue=price,
            product_cost=landed,
            payment_fee=cost.payment_fee,
            advertising_cost=cost.marketing_amortization,
            refund=cost.after_sales_loss,
        )
    )
    result["total_cost"] = _money(margin.total_cost)
    result["contribution_margin"] = _money(margin.contribution_margin)
    result["contribution_margin_rate"] = margin.contribution_margin_rate.quantize(
        Decimal("0.0001")
    )
    result["markup_rate"] = (
        ((price - landed) / landed).quantize(Decimal("0.0001")) if landed > 0 else None
    )
    return result
