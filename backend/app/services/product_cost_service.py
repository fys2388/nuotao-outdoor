"""Product cost management service.

Provides the management/read layer that sits on top of the already-existing
authoritative ``ProductCost`` model and the contribution-margin engine:

- :func:`list_cost_overview` - one row per live product with its newest cost,
  reference B2C price and derived contribution margin (the /products/costs page).
- :func:`upsert_product_cost` - manual, versioned cost edit; appends an immutable
  ``ProductCostSnapshot`` and an audit event.
- :func:`profit_analysis` - single-product profitability breakdown (margin is
  withheld unless the cost is *effective*).
- :func:`list_product_cost_gaps` - products lacking an *effective* cost (P2-9).
- :func:`list_transaction_cost_gaps` - orders whose line items lack effective
  cost evidence (P2-9).
- :func:`batch_fill_product_costs` - auditable batch cost fill (P2-9).

No new table is introduced and the service never commits (the request-scoped
session owns the transaction, matching the rest of the service layer).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, or_, select

from app.models.order import Order, OrderItem
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


def is_effective_cost(cost: ProductCost | None) -> bool:
    """A cost is effective only when it carries a real purchase price and a
    positive landed total.

    Zero-cost placeholder rows (``purchase_cost == 0`` or
    ``total_landed_cost == 0``) must never count as known cost evidence -
    otherwise a placeholder row would produce a fabricated near-100% margin
    (P2-9 cost coverage governance).
    """
    return (
        cost is not None
        and cost.purchase_cost > 0
        and cost.total_landed_cost > 0
    )


def cost_gap_reason(cost: ProductCost | None) -> str | None:
    """Return the P2-9 gap reason for a non-effective cost, or None when fine.

    - ``missing`` - no cost row at all
    - ``invalid_zero_purchase`` - row exists but purchase_cost <= 0
    - ``invalid_zero_landed`` - row exists, purchase_cost > 0 but
      total_landed_cost <= 0
    """
    if cost is None:
        return "missing"
    if cost.purchase_cost <= 0:
        return "invalid_zero_purchase"
    if cost.total_landed_cost <= 0:
        return "invalid_zero_landed"
    return None


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
        "has_effective_cost": is_effective_cost(cost),
        "cost_gap_reason": cost_gap_reason(cost),
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
            }
        )
        # P2-9: an invalid (zero) cost row must never yield a derived margin -
        # the same withholding rule as profit_analysis. Without this gate a
        # placeholder row renders as "sale price - 0" = 100% margin in the
        # overview table while profit_analysis correctly withholds it.
        if is_effective_cost(cost):
            row.update(_margin(sale_price, cost))
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
    """Return per-product cost + derived profit overview for live products.

    ``known`` counts products with an *effective* cost (P2-9); ``missing`` is
    the complement (no row or an invalid row) and ``invalid`` the subset that
    has a row without effective values.
    """
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

    any_cost_ids, effective_cost_ids = await _latest_cost_sets(session, workspace_id)

    # Coverage counters are scoped to the search (not the known/missing tab).
    coverage_total = (
        await session.execute(
            select(func.count()).select_from(search_base.subquery())
        )
    ).scalar_one()
    coverage_known = (
        await session.execute(
            select(func.count())
            .select_from(
                search_base.where(Product.id.in_(effective_cost_ids)).subquery()
            )
        )
    ).scalar_one()
    coverage_invalid = (
        await session.execute(
            select(func.count())
            .select_from(
                search_base.where(
                    Product.id.in_(any_cost_ids),
                    ~Product.id.in_(effective_cost_ids),
                ).subquery()
            )
        )
    ).scalar_one()

    page_base = search_base
    if cost_status == "known":
        page_base = page_base.where(Product.id.in_(effective_cost_ids))
    elif cost_status == "missing":
        # missing = no effective cost (missing row or invalid row).
        page_base = page_base.where(~Product.id.in_(effective_cost_ids))
    elif cost_status == "invalid":
        page_base = page_base.where(
            Product.id.in_(any_cost_ids),
            ~Product.id.in_(effective_cost_ids),
        )

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
        "invalid": coverage_invalid,
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


async def _latest_cost_sets(
    session: AsyncSession, workspace_id: UUID
) -> tuple[set[UUID], set[UUID]]:
    """Return ``(any_ids, effective_ids)`` based on the NEWEST cost row per product.

    An old effective row must not keep a product "known" once a newer invalid
    (zero) row exists - counters, filters and gap lists all agree on the latest
    row so the overview and the governance view can never contradict each other.
    """
    rows = (
        (
            await session.execute(
                select(ProductCost)
                .where(ProductCost.workspace_id == workspace_id)
                .order_by(ProductCost.valid_from.desc())
            )
        )
        .scalars()
        .all()
    )
    newest: dict[UUID, ProductCost] = {}
    for cost in rows:  # newest-first; keep first occurrence per product
        newest.setdefault(cost.product_id, cost)
    return set(newest.keys()), {
        product_id for product_id, cost in newest.items() if is_effective_cost(cost)
    }


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
        "cost_status": "KNOWN" if is_effective_cost(cost) else "MISSING",
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
    # P2-9: an invalid (zero) cost row is as good as missing - never derive a
    # fabricated margin from it.
    if not is_effective_cost(cost):
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


async def list_product_cost_gaps(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    gap_type: str = "all",
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """List live products lacking an *effective* cost (P2-9).

    ``gap_type``: ``all`` (missing + invalid), ``missing`` (no row) or
    ``invalid`` (row exists without effective values).
    """
    base = select(Product).where(
        Product.workspace_id == workspace_id,
        Product.deleted_at.is_(None),
    )
    if search:
        like = f"%{search.strip()}%"
        base = base.where(
            or_(
                Product.name.ilike(like),
                Product.sku.ilike(like),
                Product.category.ilike(like),
            )
        )

    any_cost_ids, effective_cost_ids = await _latest_cost_sets(session, workspace_id)

    gap_base = base.where(~Product.id.in_(effective_cost_ids))
    if gap_type == "missing":
        gap_base = gap_base.where(~Product.id.in_(any_cost_ids))
    elif gap_type == "invalid":
        gap_base = gap_base.where(Product.id.in_(any_cost_ids))

    total = (
        await session.execute(
            select(func.count()).select_from(gap_base.subquery())
        )
    ).scalar_one()
    known = (
        await session.execute(
            select(func.count())
            .select_from(base.where(Product.id.in_(effective_cost_ids)).subquery())
        )
    ).scalar_one()
    invalid = (
        await session.execute(
            select(func.count())
            .select_from(
                base.where(
                    Product.id.in_(any_cost_ids),
                    ~Product.id.in_(effective_cost_ids),
                ).subquery()
            )
        )
    ).scalar_one()

    products = (
        (
            await session.execute(
                gap_base.order_by(Product.created_at.desc()).limit(limit).offset(offset)
            )
        )
        .scalars()
        .all()
    )
    costs = await _latest_cost_map(session, workspace_id, [p.id for p in products])
    items: list[dict[str, Any]] = []
    for product in products:
        cost = costs.get(product.id)
        items.append(
            {
                "product_id": product.id,
                "sku": product.sku,
                "name": product.name,
                "category": product.category,
                "target_market": product.target_market,
                "status": product.status,
                "gap_type": "missing" if cost is None else "invalid",
                "gap_reason": cost_gap_reason(cost),
                "currency": cost.currency if cost else None,
                "version": cost.version if cost else None,
                "valid_from": cost.valid_from if cost else None,
                "total_landed_cost": _money(cost.total_landed_cost) if cost else ZERO,
                "sale_price": sale_price_from_meta(product.meta),
            }
        )
    return {
        "items": items,
        "total": total,
        "known": known,
        "missing": total - invalid,
        "invalid": invalid,
    }


async def list_transaction_cost_gaps(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """List orders whose line items lack effective cost evidence (P2-9).

    A line item is a gap when it cannot be traced to a live product with an
    effective cost: ``product_id`` missing, product archived (soft-deleted),
    or the product has no effective cost row.
    """
    any_ids, effective_ids = await _latest_cost_sets(session, workspace_id)
    alive_products = (
        select(Product.id)
        .where(
            Product.workspace_id == workspace_id,
            Product.deleted_at.is_(None),
        )
        .distinct()
    )
    alive_ids = {row.id for row in (await session.execute(alive_products)).all()}

    gap_items = (
        (
            await session.execute(
                select(
                    OrderItem.id,
                    OrderItem.order_id,
                    OrderItem.product_id,
                    OrderItem.line_total,
                ).where(
                    OrderItem.workspace_id == workspace_id,
                    or_(
                        OrderItem.product_id.is_(None),
                        ~OrderItem.product_id.in_(alive_ids),
                        ~OrderItem.product_id.in_(effective_ids),
                    ),
                )
            )
        )
        .all()
    )

    orders_stats: dict[UUID, dict[str, Any]] = {}
    for row in gap_items:
        stats = orders_stats.setdefault(
            row.order_id,
            {"gap_item_count": 0, "gap_line_total": ZERO, "gap_reasons": set()},
        )
        stats["gap_item_count"] += 1
        stats["gap_line_total"] += row.line_total or ZERO
        stats["gap_reasons"].add(
            _item_gap_reason(row.product_id, alive_ids, any_ids, effective_ids)
        )

    order_rows: list[dict[str, Any]] = []
    if orders_stats:
        orders = (
            (
                await session.execute(
                    select(Order).where(Order.id.in_(list(orders_stats.keys())))
                )
            )
            .scalars()
            .all()
        )
        for order in orders:
            stats = orders_stats[order.id]
            order_rows.append(
                {
                    "order_id": order.id,
                    "order_number": order.external_order_id,
                    "received_at": order.received_at,
                    "currency": order.currency,
                    "gap_item_count": stats["gap_item_count"],
                    "gap_line_total": _money(stats["gap_line_total"]),
                    "gap_reasons": sorted(stats["gap_reasons"]),
                }
            )
    order_rows.sort(key=lambda row: row["received_at"], reverse=True)

    gap_line_count = sum(row["gap_item_count"] for row in order_rows)
    gap_line_total = _money(sum(row["gap_line_total"] for row in order_rows))
    return {
        "items": order_rows[offset : offset + limit],
        "total": len(order_rows),
        "gap_line_count": gap_line_count,
        "gap_line_total": gap_line_total,
    }


def _item_gap_reason(
    product_id: UUID | None,
    alive_ids: set[UUID],
    any_ids: set[UUID],
    effective_ids: set[UUID],
) -> str:
    """Classify why one order line item is a cost gap."""
    if product_id is None:
        return "product_missing"
    if product_id not in alive_ids:
        return "product_archived"
    if product_id not in effective_ids:
        return "invalid_cost" if product_id in any_ids else "missing_cost"
    return "unknown"


async def batch_fill_product_costs(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    items: list[Any],
    trace_id: str | None,
) -> dict[str, Any]:
    """Fill effective costs for multiple products in one auditable call (P2-9).

    Every item reuses the versioned :func:`upsert_product_cost` under its own
    savepoint, so a failing item is isolated and reported without aborting the
    rest (same philosophy as CSV intake row isolation). One ``event_log`` entry
    summarizes the batch on top of the per-item ``product.cost.updated`` events.
    """
    product_ids = [item.product_id for item in items]
    sku_map: dict[UUID, str | None] = {}
    if product_ids:
        sku_rows = (
            (
                await session.execute(
                    select(Product.id, Product.sku).where(
                        Product.workspace_id == workspace_id,
                        Product.id.in_(product_ids),
                    )
                )
            )
            .all()
        )
        sku_map = {row.id: row.sku for row in sku_rows}

    results: list[dict[str, Any]] = []
    success_count = 0
    failed_count = 0
    for item in items:
        try:
            async with session.begin_nested():
                filled = await upsert_product_cost(
                    session,
                    workspace_id=workspace_id,
                    product_id=item.product_id,
                    data=item.cost,
                    trace_id=trace_id,
                )
            results.append(
                {
                    "product_id": item.product_id,
                    "sku": sku_map.get(item.product_id),
                    "success": True,
                    "version": filled["version"],
                    "total_landed_cost": filled["total_landed_cost"],
                    "error": None,
                }
            )
            success_count += 1
        except Exception as exc:  # ProductCostError or anything else: isolate
            results.append(
                {
                    "product_id": item.product_id,
                    "sku": sku_map.get(item.product_id),
                    "success": False,
                    "version": None,
                    "total_landed_cost": None,
                    "error": str(exc),
                }
            )
            failed_count += 1

    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="product.cost.batch_filled",
        entity_type="product_cost",
        entity_id="batch",
        payload={
            "success_count": success_count,
            "failed_count": failed_count,
            "items": [
                {"product_id": str(result["product_id"]), "success": result["success"]}
                for result in results
            ],
        },
        trace_id=trace_id,
        commit=False,
    )
    return {
        "results": results,
        "success_count": success_count,
        "failed_count": failed_count,
    }
