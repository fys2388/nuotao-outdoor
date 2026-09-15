"""V3.0 Nuotao selection orchestration service.

This is the only layer that touches the database for a V3.0 evaluation. It
collects structured facts (operational score, landed cost / margin, supplier
grade, weight, category), runs the pure mapping -> Nuotao Score -> V1-V12 veto
-> funnel-stage pipeline, persists an append-only ``ProductNuotaoScore`` row and
updates the product's ``funnel_stage`` / ``reject_reasons`` snapshot.

It deliberately does NOT change ``candidate_status`` (lifecycle) — the V3
funnel is an independent axis (docs/nuotao_product_score_v3.0.md §4).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product, ProductCost
from app.models.product_intelligence import (
    ProductNuotaoScore,
    ProductScore,
    SourcingCandidate,
)
from app.models.supplier import Supplier
from app.services.nuotao_score_mapper import ScoreFacts, map_dimensions
from app.services.nuotao_score_v3 import (
    MODEL_VERSION,
    RULE_VERSION,
    compute_nuotao_score,
)
from app.services.nuotao_veto import decide_funnel_stage, evaluate_vetoes
from app.services.product_cost_service import (
    latest_cost_for_product,
    sale_price_from_meta,
)
from app.services.profit_engine import ProfitInput, calculate_contribution_margin

# Lower is better; used to pick the strongest supplier grade for a product.
_SUPPLIER_RANK = {"A": 0, "B": 1, "C": 2, "D": 3}
_ZERO = Decimal("0")


async def _latest_operational_score(
    session: AsyncSession, workspace_id: UUID, product_id: UUID
) -> ProductScore | None:
    return (
        (
            await session.execute(
                select(ProductScore)
                .where(
                    ProductScore.workspace_id == workspace_id,
                    ProductScore.product_id == product_id,
                )
                .order_by(ProductScore.scored_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


async def _best_supplier_rating(
    session: AsyncSession, workspace_id: UUID, product_id: UUID
) -> str | None:
    rows = (
        await session.execute(
            select(Supplier.rating)
            .join(SourcingCandidate, SourcingCandidate.supplier_id == Supplier.id)
            .where(
                SourcingCandidate.workspace_id == workspace_id,
                SourcingCandidate.product_id == product_id,
                Supplier.status == "active",
            )
        )
    ).all()
    ratings = [row[0].upper() for row in rows if row[0]]
    if not ratings:
        return None
    return min(ratings, key=lambda grade: _SUPPLIER_RANK.get(grade, 9))


async def _existing_hero_categories(
    session: AsyncSession, workspace_id: UUID, product_id: UUID
) -> tuple[str, ...]:
    rows = (
        await session.execute(
            select(Product.category)
            .where(
                Product.workspace_id == workspace_id,
                Product.id != product_id,
                Product.deleted_at.is_(None),
                Product.category.isnot(None),
                or_(
                    Product.funnel_stage == "hero",
                    Product.candidate_status == "winner",
                ),
            )
            .distinct()
        )
    ).all()
    return tuple(row[0] for row in rows if row[0])


def _cost_facts(
    product: Product, cost: ProductCost | None
) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    """Return (reference USD price, margin rate, international shipping ratio)."""
    sale_price = sale_price_from_meta(product.meta)
    if cost is None or sale_price is None or sale_price <= _ZERO:
        return sale_price, None, None
    margin = calculate_contribution_margin(
        ProfitInput(
            revenue=sale_price,
            product_cost=cost.total_landed_cost,
            payment_fee=cost.payment_fee,
            advertising_cost=cost.marketing_amortization,
            refund=cost.after_sales_loss,
        )
    ).contribution_margin_rate
    shipping_ratio = (
        (Decimal(cost.international_shipping) / sale_price).quantize(Decimal("0.0001"))
        if Decimal(cost.international_shipping) > _ZERO
        else None
    )
    return sale_price, margin.quantize(Decimal("0.0001")), shipping_ratio


async def evaluate_product(
    session: AsyncSession,
    product_id: UUID,
    *,
    workspace_id: UUID | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Run the full V3.0 evaluation for one product and persist the result."""
    product = await session.get(Product, product_id)
    if product is None or product.deleted_at is not None:
        raise ValueError(f"product not found: {product_id}")
    workspace_id = workspace_id or product.workspace_id

    operational_score = await _latest_operational_score(
        session, workspace_id, product_id
    )
    cost = await latest_cost_for_product(
        session, workspace_id=workspace_id, product_id=product_id
    )
    supplier_rating = await _best_supplier_rating(session, workspace_id, product_id)
    hero_categories = await _existing_hero_categories(
        session, workspace_id, product_id
    )
    reference_price, margin_rate, shipping_ratio = _cost_facts(product, cost)
    # V6 impulse threshold is USD-denominated; only supply it when cost is USD.
    reference_price_usd = (
        reference_price if cost is not None and cost.currency.upper() == "USD" else None
    )

    operational: dict[str, Any] = {}
    operational_total: Decimal | None = None
    if operational_score is not None:
        operational = {
            "profit": operational_score.profit,
            "logistics": operational_score.logistics,
            "demand": operational_score.demand,
            "competition": operational_score.competition,
            "differentiation": operational_score.differentiation,
            "compliance": operational_score.compliance,
        }
        operational_total = Decimal(operational_score.total)

    facts = ScoreFacts(
        operational=operational,
        margin_rate=margin_rate,
        shipping_ratio=shipping_ratio,
        weight_kg=product.weight_kg,
        supplier_rating=supplier_rating,
        category=product.category,
        reference_price_usd=reference_price_usd,
        existing_hero_categories=hero_categories,
    )

    dimensions, evidence = map_dimensions(facts)
    score_result = compute_nuotao_score(dimensions)
    total = score_result["total"]
    grade = score_result["grade"]
    veto = evaluate_vetoes(facts, dimensions)
    stage = decide_funnel_stage(
        vetoed=veto["vetoed"],
        grade=grade,
        operational_total=operational_total,
        nuotao_total=total,
    )

    findings_payload = [
        {"rule_id": f.rule_id, "status": f.status, "detail": f.detail}
        for f in veto["findings"]
    ]
    input_evidence = {
        "operational_total": float(operational_total) if operational_total is not None else None,
        "margin_rate": float(margin_rate) if margin_rate is not None else None,
        "shipping_ratio": float(shipping_ratio) if shipping_ratio is not None else None,
        "weight_kg": float(product.weight_kg) if product.weight_kg is not None else None,
        "supplier_rating": supplier_rating,
        "reference_price": float(reference_price) if reference_price is not None else None,
        "cost_currency": cost.currency if cost is not None else None,
        **evidence,
    }

    record = ProductNuotaoScore(
        workspace_id=workspace_id,
        product_id=product_id,
        value_score=dimensions["value"],
        utility_score=dimensions["utility"],
        weight_packability_score=dimensions["weight_packability"],
        durability_score=dimensions["durability"],
        brand_fit_score=dimensions["brand_fit"],
        differentiation_score=dimensions["differentiation"],
        total=total,
        grade=grade,
        reject_reasons=findings_payload,
        dimension_evidence=input_evidence,
        model_version=MODEL_VERSION,
        rule_version=RULE_VERSION,
        trace_id=trace_id or f"v3-{uuid.uuid4().hex[:12]}",
    )
    session.add(record)

    product.funnel_stage = stage
    product.reject_reasons = [
        {"rule_id": rule_id, "detail": next(
            f.detail for f in veto["findings"] if f.rule_id == rule_id
        )}
        for rule_id in veto["failed"]
    ]
    await session.flush()

    return {
        "product_id": str(product_id),
        "score_id": str(record.id),
        "funnel_stage": stage,
        "grade": grade,
        "nuotao_total": float(total),
        "operational_total": float(operational_total) if operational_total is not None else None,
        "dimensions": {key: float(value) for key, value in dimensions.items()},
        "veto": {
            "vetoed": veto["vetoed"],
            "failed": veto["failed"],
            "pending": veto["pending"],
            "findings": findings_payload,
        },
        "evidence": input_evidence,
    }


async def evaluate_products(
    session: AsyncSession,
    product_ids: list[UUID],
    *,
    workspace_id: UUID | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Batch evaluate; soft-deleted/missing rows are skipped, one failure never
    aborts the whole batch."""
    evaluated: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    for product_id in product_ids:
        existing = await session.get(Product, product_id)
        if existing is None or existing.deleted_at is not None:
            skipped.append(
                {"product_id": str(product_id), "reason": "missing_or_soft_deleted"}
            )
            continue
        try:
            evaluated.append(
                await evaluate_product(
                    session, product_id, workspace_id=workspace_id, trace_id=trace_id
                )
            )
        except Exception as exc:  # noqa: BLE001 - batch isolation by design
            errors.append({"product_id": str(product_id), "error": str(exc)})
    return {
        "evaluated": evaluated,
        "skipped": skipped,
        "errors": errors,
        "count": len(evaluated),
    }
