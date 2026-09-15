"""One-off drill: make ONE existing candidate data-complete for the V3 loop.

Purpose: exercise the full 8 -> 3 -> 1-2 V3.0 closed loop on production without
hand-editing SQL. It fills the structured facts the evaluator reads — B2C
reference price, weight, six-dimension operational score, USD landed cost, and
an A-grade supplier link — for a single product. It does NOT fabricate an AI
analysis (Brand Fit stays at its honest neutral default) and does NOT run the
evaluation itself; the evaluation is triggered through the real HTTP API.

Idempotent: re-running never duplicates rows. Roll back with MODE=cleanup.

Env:
  TARGET_PRODUCT_ID  product to complete (required)
  MODE               seed (default) | cleanup
"""

from __future__ import annotations

import asyncio
import json
import os
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import _engine
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.product import Product
from app.models.product_intelligence import (
    ProductCostSnapshot,
    ProductScore,
    SourcingCandidate,
)
from app.models.supplier import Supplier
from app.services.product_cost_service import landed_breakdown

TRACE = "v3-drill-sample"
SUPPLIER_CODE = "S-DRILL-A"
SALE_PRICE = Decimal("29.99")
DRILL_WEIGHT = Decimal("1.2")

# Six-dimension operational score (0-10 each); weights per ProductScore doc:
# profit .30 logistics .20 demand .15 competition .10 differentiation .15 compliance .10
OP_DIMS = {
    "profit": Decimal("9"),
    "logistics": Decimal("9"),
    "demand": Decimal("9"),
    "competition": Decimal("9"),
    "differentiation": Decimal("9"),
    "compliance": Decimal("9"),
}
OP_TOTAL = Decimal("90.00")

# USD landed-cost drill values.
COST = {
    "purchase_cost": Decimal("5.50"),
    "domestic_shipping": Decimal("0.50"),
    "first_leg_shipping": Decimal("0"),
    "last_leg_shipping": Decimal("0"),
    "international_shipping": Decimal("2.00"),
    "packaging": Decimal("0.30"),
    "tax_estimate": Decimal("0"),
    "handling": Decimal("0.20"),
}
PERIOD = {
    "payment_fee": Decimal("0.90"),
    "marketing_amortization": Decimal("1.50"),
    "after_sales_loss": Decimal("0.60"),
}


async def _latest_score(session: AsyncSession, product_id):
    return (
        (
            await session.execute(
                select(ProductScore)
                .where(ProductScore.product_id == product_id)
                .order_by(ProductScore.scored_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


async def _supplier(session: AsyncSession):
    supplier = (
        (
            await session.execute(
                select(Supplier).where(
                    Supplier.workspace_id == DEFAULT_WORKSPACE_ID,
                    Supplier.code == SUPPLIER_CODE,
                )
            )
        )
        .scalars()
        .first()
    )
    created = False
    if supplier is None:
        supplier = Supplier(
            workspace_id=DEFAULT_WORKSPACE_ID,
            code=SUPPLIER_CODE,
            name="V3 Drill Sample Factory (A)",
            platform="1688",
            rating="A",
            status="active",
        )
        session.add(supplier)
        await session.flush()
        created = True
    elif supplier.rating != "A":
        supplier.rating = "A"
    return supplier, created


async def seed(session: AsyncSession, product_id) -> dict:
    product = await session.get(Product, product_id)
    if product is None or product.deleted_at is not None:
        raise SystemExit(f"product missing or soft-deleted: {product_id}")

    before = {"meta": product.meta, "weight_kg": str(product.weight_kg) if product.weight_kg else None}

    # 1) reference price + weight
    meta = dict(product.meta or {})
    meta["sale_price"] = str(SALE_PRICE)
    meta["_v3_drill"] = True
    product.meta = meta
    weight_set = False
    if product.weight_kg is None:
        product.weight_kg = DRILL_WEIGHT
        weight_set = True

    # 2) operational score (idempotent: skip if a >=70 score already exists)
    score = await _latest_score(session, product_id)
    score_created = False
    if score is None or Decimal(score.total) < Decimal("70"):
        score = ProductScore(
            workspace_id=DEFAULT_WORKSPACE_ID,
            product_id=product_id,
            **OP_DIMS,
            total=OP_TOTAL,
            model_version="heuristic-v1",
            rule_version="m2.1-v1",
            trace_id=TRACE,
        )
        session.add(score)
        await session.flush()
        score_created = True

    # 3) USD landed cost snapshot (append-only)
    international, landed, _ = landed_breakdown(**COST)
    total_cost = landed + sum(PERIOD.values(), Decimal("0"))
    cost = ProductCostSnapshot(
        workspace_id=DEFAULT_WORKSPACE_ID,
        product_id=product_id,
        currency="USD",
        **COST,
        international_shipping=international,
        total_landed_cost=landed,
        total_cost=total_cost,
        version="v1",
        source="manual",
        trace_id=TRACE,
        **PERIOD,
    )
    session.add(cost)
    await session.flush()

    # 4) A supplier + link (idempotent per product/supplier pair)
    supplier, supplier_created = await _supplier(session)
    link = (
        (
            await session.execute(
                select(SourcingCandidate).where(
                    SourcingCandidate.workspace_id == DEFAULT_WORKSPACE_ID,
                    SourcingCandidate.product_id == product_id,
                    SourcingCandidate.supplier_id == supplier.id,
                )
            )
        )
        .scalars()
        .first()
    )
    link_created = False
    if link is None:
        link = SourcingCandidate(
            workspace_id=DEFAULT_WORKSPACE_ID,
            product_id=product_id,
            supplier_id=supplier.id,
            supplier_code=supplier.code,
            source_type="drill",
            status="active",
            title=product.name,
            purchase_price=COST["purchase_cost"],
            trace_id=TRACE,
        )
        session.add(link)
        await session.flush()
        link_created = True

    await session.commit()
    return {
        "product": {"id": str(product_id), "sku": product.sku, "name": product.name},
        "before": before,
        "sale_price": str(SALE_PRICE),
        "weight_set_to_1_2": weight_set,
        "operational_total": str(OP_TOTAL),
        "score_created": score_created,
        "cost": {"id": str(cost.id), "landed": str(landed), "total_cost": str(total_cost), "currency": "USD"},
        "supplier": {"id": str(supplier.id), "code": supplier.code, "rating": supplier.rating, "created": supplier_created},
        "supplier_link_created": link_created,
        "trace": TRACE,
    }


async def cleanup(session: AsyncSession, product_id) -> dict:
    removed = {"scores": 0, "costs": 0, "links": 0, "suppliers": 0}
    for model, key in ((ProductScore, "scores"), (ProductCostSnapshot, "costs"), (SourcingCandidate, "links")):
        rows = (
            (
                await session.execute(
                    select(model).where(
                        model.workspace_id == DEFAULT_WORKSPACE_ID,
                        model.product_id == product_id,
                        model.trace_id == TRACE,
                    )
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            await session.delete(row)
            removed[key] += 1
    supplier = (
        (
            await session.execute(
                select(Supplier).where(
                    Supplier.workspace_id == DEFAULT_WORKSPACE_ID,
                    Supplier.code == SUPPLIER_CODE,
                )
            )
        )
        .scalars()
        .first()
    )
    if supplier is not None:
        await session.delete(supplier)
        removed["suppliers"] = 1
    product = await session.get(Product, product_id)
    if product is not None and product.meta:
        meta = dict(product.meta)
        meta.pop("_v3_drill", None)
        product.meta = meta
    await session.commit()
    return removed


async def main() -> None:
    product_id = os.environ.get("TARGET_PRODUCT_ID")
    if not product_id:
        raise SystemExit("TARGET_PRODUCT_ID is required")
    mode = os.environ.get("MODE", "seed")
    async with AsyncSession(_engine, expire_on_commit=False) as session:
        if mode == "cleanup":
            result = await cleanup(session, product_id)
        else:
            result = await seed(session, product_id)
    print(json.dumps({"mode": mode, "result": result}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
