"""Cost source synchronization service (PHASE 4).

Syncs cost data from the 1688 source into the product's authoritative
cost records. When a product was imported from 1688, the source price
is stored in the ProductSource raw_data. This service extracts that
price, optionally converts from CNY to USD, and creates/updates the
ProductCost row with proper versioning and snapshots.

Design principles:
- No fabrication: if 1688 price data is missing, the sync is reported
  as "skipped" rather than creating a zero-cost row.
- Currency-aware: CNY prices are converted to USD at the configured
  rate (default 1 CNY = 0.14 USD, overridable).
- Versioned: every sync creates a new cost version (v1 -> v2 -> v3).
- Snapshot: every sync appends an immutable ProductCostSnapshot.
- Audit: every sync emits a product.cost.synced event.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product, ProductCost
from app.models.product_intelligence import ProductCostSnapshot, ProductSource
from app.services import event_service
from app.services.product_cost_service import (
    landed_breakdown,
    latest_cost_for_product,
    bump_version,
    _money,
    ZERO,
)

logger = logging.getLogger(__name__)


class CostSyncError(Exception):
    """Raised when a cost sync operation cannot complete."""


# Default exchange rate: 1 CNY = 0.14 USD (approximate, for estimation).
# Override via environment variable COST_SYNC_CNY_USD_RATE.
_DEFAULT_CNY_USD_RATE = Decimal("0.14")


def _cny_usd_rate() -> Decimal:
    """Get the CNY->USD conversion rate from environment or default."""
    import os
    raw = os.getenv("COST_SYNC_CNY_USD_RATE", "")
    if raw:
        try:
            rate = Decimal(raw)
            if rate > 0:
                return rate
        except (ArithmeticError, ValueError):
            pass
    return _DEFAULT_CNY_USD_RATE


def _convert_cny_to_usd(amount: Decimal) -> Decimal:
    """Convert CNY to USD using the configured rate."""
    return (amount * _cny_usd_rate()).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _parse_decimal(value: Any) -> Decimal | None:
    """Parse a value to Decimal, returning None if invalid."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw or raw == "0":
        return None
    # Strip currency symbols and non-numeric chars except dot and minus
    import re
    cleaned = re.sub(r"[^\d.\-]", "", raw)
    if not cleaned or cleaned in ("-", "."):
        return None
    try:
        result = Decimal(cleaned)
        return result if result > 0 else None
    except (ArithmeticError, ValueError):
        return None


def _extract_1688_price(raw_data: dict[str, Any]) -> Decimal | None:
    """Extract the purchase price from a 1688 ProductSource raw_data dict.

    1688 stores price data in various field names depending on the import
    path (open API, Newton, scraping, manual). This function tries all
    known field names and returns the first valid price found.

    Priority order:
    1. price_range (list of tiered prices) - use the lowest
    2. price (string like "25.80" or "¥25.80")
    3. cost_price, purchase_cost, unit_price
    4. saleInfo.retailprice
    5. skuInfos[0].priceRange
    """
    if not isinstance(raw_data, dict):
        return None

    # 1. Try price_range (lowest price in the range)
    price_range = raw_data.get("price_range")
    if isinstance(price_range, list) and price_range:
        prices: list[Decimal] = []
        for item in price_range:
            if isinstance(item, dict):
                val = _parse_decimal(item.get("price"))
                if val is not None:
                    prices.append(val)
            else:
                val = _parse_decimal(item)
                if val is not None:
                    prices.append(val)
        if prices:
            return min(prices)

    # 2. Try direct price fields
    for key in ("price", "cost_price", "purchase_cost", "unit_price"):
        val = _parse_decimal(raw_data.get(key))
        if val is not None:
            return val

    # 3. Try saleInfo
    sale_info = raw_data.get("saleInfo")
    if isinstance(sale_info, dict):
        val = _parse_decimal(sale_info.get("retailprice") or sale_info.get("price"))
        if val is not None:
            return val

    # 4. Try skuInfos
    sku_infos = raw_data.get("skuInfos") or raw_data.get("skuList")
    if isinstance(sku_infos, list) and sku_infos:
        for sku in sku_infos:
            if isinstance(sku, dict):
                # sku-level price_range
                sku_range = sku.get("priceRange")
                if isinstance(sku_range, list) and sku_range:
                    for item in sku_range:
                        if isinstance(item, dict):
                            val = _parse_decimal(item.get("price"))
                            if val is not None:
                                return val
                # sku-level price
                val = _parse_decimal(sku.get("price"))
                if val is not None:
                    return val

    return None


async def _find_product_source(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
) -> ProductSource | None:
    """Find the most recent 1688 source for a product."""
    rows = (
        (
            await session.execute(
                select(ProductSource)
                .where(
                    ProductSource.workspace_id == workspace_id,
                    ProductSource.product_id == product_id,
                    ProductSource.source_type.in_(["1688", "NEWTON_AI"]),
                )
                .order_by(ProductSource.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return rows[0] if rows else None


async def _load_product(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
) -> Product | None:
    """Load a live product or return None."""
    return (
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


async def sync_cost_from_1688(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    force: bool = False,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Sync cost from the 1688 source for a single product.

    Args:
        session: DB session (caller owns the transaction).
        workspace_id: Workspace scope.
        product_id: Product to sync.
        force: If True, overwrite existing cost even if it's already
               effective (creates a new version). Default False: skip
               if an effective cost already exists.
        trace_id: Audit trace id.

    Returns:
        Dict with sync result:
        - product_id, sku, name
        - sync_status: "synced" | "skipped" | "error"
        - details: human-readable explanation
        - cost_version: new version if synced
        - purchase_cost: the synced purchase cost
        - currency: target currency

    Raises:
        CostSyncError: Only for infrastructure failures (product not found).
    """
    product = await _load_product(
        session, workspace_id=workspace_id, product_id=product_id,
    )
    if product is None:
        raise CostSyncError(f"product not found: {product_id}")

    # Check if an effective cost already exists
    existing_cost = await latest_cost_for_product(
        session, workspace_id=workspace_id, product_id=product_id,
    )

    # Find 1688 source
    source = await _find_product_source(
        session, workspace_id=workspace_id, product_id=product_id,
    )

    if source is None:
        return {
            "product_id": str(product.id),
            "sku": product.sku,
            "name": product.name,
            "sync_status": "skipped",
            "details": "no 1688 source found for this product",
            "cost_version": None,
            "purchase_cost": None,
            "currency": None,
        }

    # Extract price from source raw_data
    raw_data = source.raw_data if isinstance(source.raw_data, dict) else {}
    cny_price = _extract_1688_price(raw_data)

    if cny_price is None:
        return {
            "product_id": str(product.id),
            "sku": product.sku,
            "name": product.name,
            "sync_status": "skipped",
            "details": "1688 source found but no valid price data in raw_data",
            "cost_version": None,
            "purchase_cost": None,
            "currency": None,
        }

    # Convert to USD (1688 prices are always CNY)
    usd_price = _convert_cny_to_usd(cny_price)

    # Skip if effective cost already exists and not forced
    if not force and existing_cost is not None:
        if existing_cost.purchase_cost > 0 and existing_cost.total_landed_cost > 0:
            return {
                "product_id": str(product.id),
                "sku": product.sku,
                "name": product.name,
                "sync_status": "skipped",
                "details": (
                    f"effective cost already exists (version={existing_cost.version}, "
                    f"purchase_cost={existing_cost.purchase_cost} "
                    f"{existing_cost.currency}); use force=true to overwrite"
                ),
                "cost_version": existing_cost.version,
                "purchase_cost": str(usd_price),
                "currency": "USD",
            }

    # Build the cost update
    intl, total_landed, legacy_total = landed_breakdown(
        purchase_cost=usd_price,
        domestic_shipping=ZERO,
        first_leg_shipping=ZERO,
        last_leg_shipping=ZERO,
        international_shipping=None,
        packaging=ZERO,
        tax_estimate=ZERO,
        handling=ZERO,
    )

    notes = {
        "sync_source": "1688_api",
        "sync_mode": "force" if force else "auto",
        "cny_price": str(cny_price),
        "usd_price": str(usd_price),
        "exchange_rate": str(_cny_usd_rate()),
        "source_type": source.source_type,
    }

    # Create or update cost
    if existing_cost is None:
        cost = ProductCost(
            workspace_id=workspace_id,
            product_id=product_id,
            currency="USD",
            purchase_cost=_money(usd_price),
            domestic_shipping=ZERO,
            first_leg_shipping=ZERO,
            last_leg_shipping=ZERO,
            international_shipping=intl,
            packaging=ZERO,
            tax_estimate=ZERO,
            handling=ZERO,
            total_landed_cost=_money(total_landed),
            total_cost=_money(legacy_total),
            version="v1",
            notes=notes,
            valid_from=datetime.now(UTC),
        )
        session.add(cost)
        version = "v1"
    else:
        version = bump_version(existing_cost.version)
        existing_cost.currency = "USD"
        existing_cost.purchase_cost = _money(usd_price)
        existing_cost.international_shipping = intl
        existing_cost.total_landed_cost = _money(total_landed)
        existing_cost.total_cost = _money(legacy_total)
        existing_cost.version = version
        existing_cost.valid_from = datetime.now(UTC)
        existing_cost.notes = {**(existing_cost.notes or {}), **notes}
        cost = existing_cost

    await session.flush()

    # Create snapshot
    snapshot = ProductCostSnapshot(
        workspace_id=workspace_id,
        product_id=product_id,
        version=version,
        source="1688_sync",
        weight_kg=product.weight_kg,
        trace_id=trace_id,
        currency="USD",
        purchase_cost=_money(usd_price),
        domestic_shipping=ZERO,
        first_leg_shipping=ZERO,
        last_leg_shipping=ZERO,
        international_shipping=intl,
        packaging=ZERO,
        tax_estimate=ZERO,
        handling=ZERO,
        total_landed_cost=_money(total_landed),
        total_cost=_money(legacy_total),
    )
    session.add(snapshot)
    await session.flush()

    # Audit event
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="product.cost.synced",
        entity_type="product",
        entity_id=str(product_id),
        payload={
            "sku": product.sku,
            "version": version,
            "purchase_cost_usd": str(usd_price),
            "purchase_cost_cny": str(cny_price),
            "exchange_rate": str(_cny_usd_rate()),
            "source_type": source.source_type,
            "total_landed_cost": str(_money(total_landed)),
            "mode": "force" if force else "auto",
        },
        trace_id=trace_id,
        commit=False,
    )
    await session.flush()

    return {
        "product_id": str(product.id),
        "sku": product.sku,
        "name": product.name,
        "sync_status": "synced",
        "details": (
            f"cost synced from 1688: CNY {cny_price} -> USD {usd_price} "
            f"(version {version}, landed cost {_money(total_landed)})"
        ),
        "cost_version": version,
        "purchase_cost": str(usd_price),
        "currency": "USD",
    }


async def sync_cost_batch(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_ids: list[str] | None = None,
    force: bool = False,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Batch sync costs from 1688 sources.

    Args:
        session: DB session (caller owns the transaction).
        workspace_id: Workspace scope.
        product_ids: Specific product IDs to sync. None = all candidates
                     with 1688 sources.
        force: Overwrite existing effective costs.
        trace_id: Audit trace id.

    Returns:
        Summary with total, synced, skipped, errors, and per-item results.
    """
    from uuid import UUID as _UUID

    results: list[dict[str, Any]] = []
    synced = 0
    skipped = 0
    errors = 0

    if product_ids:
        ids = [_UUID(pid) for pid in product_ids]
        # Load all products at once
        rows = (
            (
                await session.execute(
                    select(Product).where(
                        Product.workspace_id == workspace_id,
                        Product.id.in_(ids),
                        Product.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        for product in rows:
            try:
                result = await sync_cost_from_1688(
                    session,
                    workspace_id=workspace_id,
                    product_id=product.id,
                    force=force,
                    trace_id=trace_id,
                )
                results.append(result)
                if result["sync_status"] == "synced":
                    synced += 1
                elif result["sync_status"] == "skipped":
                    skipped += 1
                else:
                    errors += 1
            except Exception as exc:
                errors += 1
                results.append({
                    "product_id": str(product.id),
                    "sku": product.sku,
                    "sync_status": "error",
                    "details": str(exc),
                })
    else:
        # Find all products with 1688 sources
        source_rows = (
            (
                await session.execute(
                    select(ProductSource.product_id)
                    .where(
                        ProductSource.workspace_id == workspace_id,
                        ProductSource.source_type.in_(["1688", "NEWTON_AI"]),
                    )
                    .distinct()
                )
            )
            .scalars()
            .all()
        )
        for pid in source_rows:
            product = await _load_product(
                session, workspace_id=workspace_id, product_id=pid,
            )
            if product is None:
                continue
            try:
                result = await sync_cost_from_1688(
                    session,
                    workspace_id=workspace_id,
                    product_id=pid,
                    force=force,
                    trace_id=trace_id,
                )
                results.append(result)
                if result["sync_status"] == "synced":
                    synced += 1
                elif result["sync_status"] == "skipped":
                    skipped += 1
                else:
                    errors += 1
            except Exception as exc:
                errors += 1
                results.append({
                    "product_id": str(pid),
                    "sku": "",
                    "sync_status": "error",
                    "details": str(exc),
                })

    return {
        "total": len(results),
        "synced": synced,
        "skipped": skipped,
        "errors": errors,
        "exchange_rate": str(_cny_usd_rate()),
        "results": results,
    }


async def get_cost_sync_status(
    session: AsyncSession,
    *,
    workspace_id: UUID,
) -> dict[str, Any]:
    """Get cost sync status overview.

    Returns counts of products with/without 1688 sources, effective costs,
    and pending syncs.
    """
    # All products with 1688 sources
    source_pids = (
        (
            await session.execute(
                select(ProductSource.product_id)
                .where(
                    ProductSource.workspace_id == workspace_id,
                    ProductSource.source_type.in_(["1688", "NEWTON_AI"]),
                )
                .distinct()
            )
        )
        .scalars()
        .all()
    )

    # All live products
    all_products = (
        (
            await session.execute(
                select(Product).where(
                    Product.workspace_id == workspace_id,
                    Product.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )

    # Products with effective costs
    cost_rows = (
        (
            await session.execute(
                select(ProductCost).where(
                    ProductCost.workspace_id == workspace_id,
                    ProductCost.product_id.isnot(None),
                    ProductCost.purchase_cost > 0,
                    ProductCost.total_landed_cost > 0,
                )
            )
        )
        .scalars()
        .all()
    )
    effective_cost_pids = {c.product_id for c in cost_rows if c.product_id}

    has_source = set(source_pids)
    has_effective_cost = effective_cost_pids

    pending_sync = has_source - has_effective_cost
    synced = has_source & has_effective_cost
    no_source = {p.id for p in all_products} - has_source

    return {
        "total_products": len(all_products),
        "products_with_1688_source": len(has_source),
        "products_with_effective_cost": len(has_effective_cost & {p.id for p in all_products}),
        "pending_sync": len(pending_sync),
        "already_synced": len(synced),
        "no_1688_source": len(no_source),
        "exchange_rate_cny_usd": str(_cny_usd_rate()),
        "pending_product_ids": [str(pid) for pid in pending_sync][:50],
    }
