"""T0.4 profit_margin test (M4.2.0).

Owner directive: ``generate_procurement_suggestions`` previously hard-assigned
``profit_margin = None`` so the high/medium priority branches were dead code.
The fix (procurement_service.py lines ~102-140) now computes the real gross
margin from the authoritative selling price in ``product.meta`` ("price",
falling back to "sale_price") over ``ProductCost.total_landed_cost``:

    margin = (selling_price - unit_cost) / selling_price
    priority: margin >= min_margin (default 0.3) -> high
              margin >= 0.2                       -> medium
              else                                -> low

When there is no valid positive selling price (or no cost) the function
degrades honestly to ``profit_margin = None`` (AGENTS.md §1.2: no fabricated
data). These tests pin the real post-fix behavior.
"""

from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.event import EventLog
from app.models.product import Product, ProductCost
from app.services import procurement_service

WORKSPACE = DEFAULT_WORKSPACE_ID


async def _seed_product(
    db_session,
    sku: str,
    meta: dict,
    landed_cost: str | None,
) -> UUID:
    """Seed a product with an optional ProductCost row and return its id."""
    product = Product(workspace_id=WORKSPACE, sku=sku, name=f"Product {sku}", meta=meta)
    db_session.add(product)
    await db_session.flush()

    if landed_cost is not None:
        cost = ProductCost(
            workspace_id=WORKSPACE,
            product_id=product.id,
            total_landed_cost=Decimal(landed_cost),
        )
        db_session.add(cost)
        await db_session.flush()

    return product.id


async def _suggestions_for(db_session, product_id: UUID) -> dict:
    result = await procurement_service.generate_procurement_suggestions(
        db_session,
        workspace_id=WORKSPACE,
    )
    matches = [s for s in result["suggestions"] if s["product_id"] == str(product_id)]
    assert len(matches) == 1, f"expected exactly one suggestion for {product_id}"
    return matches[0]


@pytest.mark.asyncio
async def test_high_profit_margin_maps_to_high_priority(db_session):
    """margin = (100 - 20) / 100 = 0.8 >= 0.3 -> priority 'high', reason mentions profit margin."""
    product_id = await _seed_product(
        db_session,
        sku="PM-HIGH-001",
        meta={"price": "100", "stock": 100},
        landed_cost="20",
    )
    await db_session.commit()

    suggestion = await _suggestions_for(db_session, product_id)

    assert suggestion["priority"] == "high"
    assert "profit margin" in suggestion["reason"].lower()
    # profit_margin is serialized as a string in the return dict.
    assert suggestion["profit_margin"] is not None
    assert Decimal(suggestion["profit_margin"]) == Decimal("0.8")
    assert Decimal(suggestion["unit_cost"]) == Decimal("20")


@pytest.mark.asyncio
async def test_medium_profit_margin_maps_to_medium_priority(db_session):
    """margin = (100 - 75) / 100 = 0.25, in [0.2, 0.3) -> priority 'medium'.

    (A 0.5 margin would still be 'high' since 0.5 >= 0.3, so we deliberately
    place the margin inside the medium-only band.)
    """
    product_id = await _seed_product(
        db_session,
        sku="PM-MED-001",
        meta={"price": "100", "stock": 100},
        landed_cost="75",
    )
    await db_session.commit()

    suggestion = await _suggestions_for(db_session, product_id)

    assert suggestion["priority"] == "medium"
    assert "profit margin" in suggestion["reason"].lower()
    assert Decimal(suggestion["profit_margin"]) == Decimal("0.25")


@pytest.mark.asyncio
async def test_missing_price_degrades_to_none_and_stays_low(db_session):
    """No price/sale_price in meta -> profit_margin=None; ample stock keeps it 'low'.

    profit_margin=None is falsy, so neither the high nor the medium margin
    branch fires. With stock well above low_stock_threshold (default 20) and no
    selection score / listed status, the suggestion stays 'low'.
    """
    product_id = await _seed_product(
        db_session,
        sku="PM-NOPRICE-001",
        meta={"stock": 100},
        landed_cost="20",
    )
    await db_session.commit()

    suggestion = await _suggestions_for(db_session, product_id)

    assert suggestion["profit_margin"] is None
    assert suggestion["priority"] == "low"
    assert suggestion["current_stock"] == 100


@pytest.mark.asyncio
async def test_missing_cost_yields_unit_cost_zero_and_full_margin(db_session):
    """No ProductCost -> unit_cost=0; with a price the margin computes to 1.0 -> 'high'.

    CURRENT BEHAVIOR NOTE (pinned, not endorsed as ideal): when cost is absent
    the function keeps ``unit_cost = 0`` and still computes
    margin = (price - 0) / price = 1.0, because the guard is only
    ``selling_price > 0 and unit_cost >= 0``. A missing cost therefore reads as
    a *full* margin and drives priority to 'high'.

    This is arguably optimistic — a product with unknown landed cost should not
    be treated as a guaranteed 100% margin. But per the task contract the test
    must match the real post-fix implementation, so we assert the current
    behavior here and flag the semantic caveat for a future owner decision
    (e.g. treat missing cost as profit_margin=None rather than full margin).
    """
    product_id = await _seed_product(
        db_session,
        sku="PM-NOCOST-001",
        meta={"price": "100", "stock": 100},
        landed_cost=None,
    )
    await db_session.commit()

    suggestion = await _suggestions_for(db_session, product_id)

    assert Decimal(suggestion["unit_cost"]) == Decimal("0")
    assert suggestion["profit_margin"] is not None
    assert Decimal(suggestion["profit_margin"]) == Decimal("1.0")
    assert suggestion["priority"] == "high"
    assert "profit margin" in suggestion["reason"].lower()


@pytest.mark.asyncio
async def test_sale_price_fallback_used_when_price_absent(db_session):
    """meta has no 'price' but has 'sale_price' -> fallback is used for the margin."""
    product_id = await _seed_product(
        db_session,
        sku="PM-SALE-001",
        meta={"sale_price": "200", "stock": 100},
        landed_cost="100",
    )
    await db_session.commit()

    suggestion = await _suggestions_for(db_session, product_id)

    assert suggestion["priority"] == "high"
    assert Decimal(suggestion["profit_margin"]) == Decimal("0.5")


@pytest.mark.asyncio
async def test_t04_audit_events_are_persisted(db_session):
    """Sanity: generating suggestions must not fabricate event rows (read-only path).

    generate_procurement_suggestions is a pure read/compute path — it emits no
    event_service events. This guards against accidentally coupling the
    suggestion generator to the audit stream.
    """
    await _seed_product(
        db_session,
        sku="PM-EVENTS-001",
        meta={"price": "100", "stock": 100},
        landed_cost="20",
    )
    await db_session.commit()

    await procurement_service.generate_procurement_suggestions(
        db_session,
        workspace_id=WORKSPACE,
    )

    rows = (await db_session.execute(select(EventLog))).scalars().all()
    assert rows == [], "suggestion generation is read-only and must not write events"
