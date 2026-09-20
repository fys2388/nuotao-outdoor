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
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product, ProductCost
from app.models.product_intelligence import (
    ProductAnalysisRun,
    ProductNuotaoScore,
    ProductScore,
    SourcingCandidate,
)
from app.models.supplier import Supplier
from app.services.nuotao_ai_signals import (
    NormalizedAiSignals,
    normalize_ai_assessment,
)
from app.services.nuotao_score_mapper import (
    SUPPLIER_RATING_SCORE,
    ScoreFacts,
    map_dimensions,
)
from app.services.nuotao_report import (
    ReportData,
    build_public_badge,
    build_selection_report,
)
from app.services.nuotao_handoff import propose_selection_handoff
from app.services.nuotao_score_v3 import (
    MODEL_VERSION,
    RULE_VERSION,
    compute_nuotao_score,
)
from app.services.nuotao_veto import decide_funnel_stage, evaluate_vetoes
from app.services.operational_score_v2 import coverage_report
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


async def _latest_ai_assessment(
    session: AsyncSession, workspace_id: UUID, product_id: UUID
) -> dict[str, Any] | None:
    """Return the nuotao_assessment block from the most recent completed
    Product Analyst run that carries one (closes V1/V2/V3/V5 + Brand Fit)."""
    rows = (
        (
            await session.execute(
                select(ProductAnalysisRun)
                .where(
                    ProductAnalysisRun.workspace_id == workspace_id,
                    ProductAnalysisRun.product_id == product_id,
                    ProductAnalysisRun.status == "completed",
                )
                .order_by(ProductAnalysisRun.created_at.desc())
                .limit(5)
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        output = row.output if isinstance(row.output, dict) else None
        block = (output or {}).get("nuotao_assessment")
        if isinstance(block, dict) and block:
            return block
    return None


def _resolve_signals(
    ai_assessment: dict[str, Any] | NormalizedAiSignals | None,
    auto_block: dict[str, Any] | None,
) -> NormalizedAiSignals:
    if isinstance(ai_assessment, NormalizedAiSignals):
        return ai_assessment
    return normalize_ai_assessment(
        ai_assessment if ai_assessment is not None else auto_block
    )


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
    ai_assessment: dict[str, Any] | NormalizedAiSignals | None = None,
) -> dict[str, Any]:
    """Run the full V3.0 evaluation for one product and persist the result.

    ``ai_assessment`` supplies the Product Analyst's V3 block; when ``None`` the
    most recent completed analyst run is used automatically. It closes the
    AI-owned veto rules V1/V2/V3/V5 and supplies Brand Fit.
    """
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

    auto_block = await _latest_ai_assessment(session, workspace_id, product_id)
    ai_signals = _resolve_signals(ai_assessment, auto_block)

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
        brand_fit_override=ai_signals.brand_fit,
        existing_hero_categories=hero_categories,
    )

    dimensions, evidence = map_dimensions(facts)
    score_result = compute_nuotao_score(dimensions)
    total = score_result["total"]
    grade = score_result["grade"]
    veto = evaluate_vetoes(facts, dimensions, ai_signals)
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
        "ai_vetos_closed": sorted(ai_signals.veto_signals.keys()),
        "ai_brand_fit": (
            float(ai_signals.brand_fit) if ai_signals.brand_fit is not None else None
        ),
        "ai_assessment_source": (
            "inline"
            if ai_assessment is not None
            else ("latest_analyst_run" if auto_block else None)
        ),
        "operational_v2_coverage": {
            key: (float(value) if isinstance(value, Decimal) else value)
            for key, value in coverage_report(
                set(operational.keys()),
                supplier_present=supplier_rating is not None,
            ).items()
        },
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

    handoff = await propose_selection_handoff(
        session,
        workspace_id=workspace_id,
        product_id=product_id,
        product_name=product.name,
        nuotao_total=float(total),
        grade=grade,
        funnel_stage=stage,
        vetoed=veto["vetoed"],
        trace_id=record.trace_id,
    )

    return {
        "product_id": str(product_id),
        "score_id": str(record.id),
        "funnel_stage": stage,
        "handoff": handoff,
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


def _num(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def _latest_nuotao_score(
    session: AsyncSession, product_id: UUID
) -> ProductNuotaoScore | None:
    return (
        (
            await session.execute(
                select(ProductNuotaoScore)
                .where(ProductNuotaoScore.product_id == product_id)
                .order_by(ProductNuotaoScore.scored_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


async def get_public_badge(
    session: AsyncSession,
    *,
    product_id: UUID | None = None,
    sku: str | None = None,
) -> dict[str, Any]:
    """Customer-facing Nuotao badge (>= Core only, whitelisted fields)."""
    if product_id is None and not sku:
        raise ValueError("product_id or sku is required")
    query = select(Product).where(Product.deleted_at.is_(None))
    if product_id is not None:
        query = query.where(Product.id == product_id)
    else:
        query = query.where(Product.sku == sku)
    product = (await session.execute(query.limit(1))).scalars().first()
    if product is None:
        return {"display": False, "reason": "not_found"}

    score = await _latest_nuotao_score(session, product.id)
    if score is None:
        return build_public_badge(
            sku=product.sku, total=None, grade=None, dimensions=None,
            scored_at=None, model_version=None,
        )
    dimensions = {
        "value": score.value_score,
        "utility": score.utility_score,
        "weight_packability": score.weight_packability_score,
        "durability": score.durability_score,
        "brand_fit": score.brand_fit_score,
        "differentiation": score.differentiation_score,
    }
    return build_public_badge(
        sku=product.sku,
        total=score.total,
        grade=score.grade,
        dimensions=dimensions,
        scored_at=score.scored_at.isoformat() if score.scored_at else None,
        model_version=score.model_version,
    )


async def _latest_completed_analysis(
    session: AsyncSession, workspace_id: UUID, product_id: UUID
) -> ProductAnalysisRun | None:
    return (
        (
            await session.execute(
                select(ProductAnalysisRun)
                .where(
                    ProductAnalysisRun.workspace_id == workspace_id,
                    ProductAnalysisRun.product_id == product_id,
                    ProductAnalysisRun.status == "completed",
                )
                .order_by(ProductAnalysisRun.created_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


async def build_product_report(
    session: AsyncSession,
    product_id: UUID,
    *,
    workspace_id: UUID | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Collect every input for one product and assemble the V3.0 report.

    Read-only; missing pieces are surfaced in data_completeness, never faked.
    """
    product = await session.get(Product, product_id)
    if product is None or product.deleted_at is not None:
        raise ValueError(f"product not found: {product_id}")
    workspace_id = workspace_id or product.workspace_id

    nuotao_row = await _latest_nuotao_score(session, product_id)
    op_row = await _latest_operational_score(session, workspace_id, product_id)
    cost = await latest_cost_for_product(
        session, workspace_id=workspace_id, product_id=product_id
    )
    rating = await _best_supplier_rating(session, workspace_id, product_id)
    analysis = await _latest_completed_analysis(session, workspace_id, product_id)
    sale_price, margin_rate, shipping_ratio = _cost_facts(product, cost)

    nuotao_data: dict[str, Any] | None = None
    if nuotao_row is not None:
        nuotao_data = {
            "value_score": _num(nuotao_row.value_score),
            "utility_score": _num(nuotao_row.utility_score),
            "weight_packability_score": _num(nuotao_row.weight_packability_score),
            "durability_score": _num(nuotao_row.durability_score),
            "brand_fit_score": _num(nuotao_row.brand_fit_score),
            "differentiation_score": _num(nuotao_row.differentiation_score),
            "total": _num(nuotao_row.total),
            "grade": nuotao_row.grade,
            "reject_reasons": nuotao_row.reject_reasons,
            "dimension_evidence": nuotao_row.dimension_evidence,
            "model_version": nuotao_row.model_version,
            "rule_version": nuotao_row.rule_version,
            "funnel_stage": product.funnel_stage,
        }

    operational_data: dict[str, Any] | None = None
    if op_row is not None:
        operational_data = {
            "profit": _num(op_row.profit),
            "logistics": _num(op_row.logistics),
            "demand": _num(op_row.demand),
            "competition": _num(op_row.competition),
            "differentiation": _num(op_row.differentiation),
            "compliance": _num(op_row.compliance),
            "total": _num(op_row.total),
        }

    cost_data: dict[str, Any] | None = None
    if cost is not None:
        cost_data = {
            "currency": cost.currency,
            "sale_price": _num(sale_price),
            "purchase_cost": _num(cost.purchase_cost),
            "domestic_shipping": _num(cost.domestic_shipping),
            "first_leg_shipping": _num(cost.first_leg_shipping),
            "last_leg_shipping": _num(cost.last_leg_shipping),
            "international_shipping": _num(cost.international_shipping),
            "packaging": _num(cost.packaging),
            "tax_estimate": _num(cost.tax_estimate),
            "handling": _num(cost.handling),
            "payment_fee": _num(cost.payment_fee),
            "marketing_amortization": _num(cost.marketing_amortization),
            "after_sales_loss": _num(cost.after_sales_loss),
            "total_landed_cost": _num(cost.total_landed_cost),
            "margin_rate": _num(margin_rate),
            "shipping_ratio": _num(shipping_ratio),
        }

    supplier_data = None
    if rating is not None:
        supplier_data = {
            "rating": rating,
            "score": _num(SUPPLIER_RATING_SCORE.get(rating.upper())),
        }

    present_m21 = (
        {"profit", "logistics", "demand", "competition", "differentiation", "compliance"}
        if operational_data is not None
        else set()
    )
    coverage = {
        key: (_num(value) if isinstance(value, Decimal) else value)
        for key, value in coverage_report(
            present_m21, supplier_present=rating is not None
        ).items()
    }

    report_data = ReportData(
        product={
            "sku": product.sku,
            "name": product.name,
            "category": product.category,
            "funnel_stage": product.funnel_stage,
            "source_url": (product.meta or {}).get("source_url"),
        },
        nuotao=nuotao_data,
        operational=operational_data,
        cost=cost_data,
        supplier=supplier_data,
        analyst=analysis.output if analysis is not None else None,
        coverage=coverage,
        generated_at=datetime.now(UTC).isoformat(),
    )
    return build_selection_report(report_data)
