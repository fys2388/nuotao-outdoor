"""Product intelligence service: deterministic analysis chain (M2.1, no LLM).

Chain: Product -> Cost -> Logistics -> Profit -> Rule Engine -> Score Context.

The pipeline only performs deterministic data processing in this phase; no
LLM is invoked. Every run is audited in ``product_analysis_runs`` and every
score persisted in ``product_scores`` (model_version + rule_version + trace_id).
Scoring follows docs/product_strategy.md §6 (weights 30/20/15/10/15/10,
0-10 dimensions, total 0-100) and decision gates follow operating_rules.md
(PROD-SEL / PROFIT domains, loaded from the rules registry, never hardcoded).
"""

import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product, ProductCost
from app.models.product_intelligence import (
    ProductAnalysisRun,
    ProductCostSnapshot,
    ProductDecision,
    ProductScore,
    ProductSource,
)
from app.models.supplier import Supplier
from app.schemas.product_intelligence import (
    ProductIntakeRequest,
    ProductIntakeResult,
)
from app.services import event_service, rule_engine
from app.services.profit_engine import (
    ProfitInput,
    calculate_contribution_margin,
)

logger = logging.getLogger(__name__)

ZERO = Decimal("0")

# Deterministic score model v1 (docs/product_strategy.md §6.1). Weights are
# recorded per score row (rule_version) for future calibration.
SCORE_WEIGHTS: dict[str, float] = {
    "profit": 0.30,
    "logistics": 0.20,
    "demand": 0.15,
    "competition": 0.10,
    "differentiation": 0.15,
    "compliance": 0.10,
}
SCORE_MODEL_VERSION = "score-model-v1"
SCORE_RULE_VERSION = "prod-score-v1"
NEUTRAL_DIMENSION = Decimal("5.00")  # neutral 5/10 until real data exists

# Target gross margin used to derive a recommended price (PRICE-002 Hero band).
TARGET_MARGIN = Decimal("0.40")
TEST_QUANTITY = 30
TEST_DAYS = 30
CONFIDENCE_BY_STATUS = {
    "KNOWN": Decimal("0.900"),
    "ESTIMATED": Decimal("0.600"),
    "UNKNOWN": Decimal("0.300"),
}


class ProductIntelligenceError(Exception):
    """Raised when a product intelligence operation cannot complete."""


@dataclass(frozen=True)
class ScoreContext:
    """Output of the deterministic analysis chain."""

    product_id: UUID
    dimensions: dict[str, Decimal]
    total: Decimal
    vetoed: bool
    margin_rate: Decimal | None
    recommended_price: Decimal | None
    shipping_ratio: Decimal | None
    cost_status: str
    reasons: dict[str, list[str]] = field(default_factory=dict)
    rule_results: list[dict] = field(default_factory=list)


def _volumetric_weight_kg(dimensions: dict | None) -> Decimal | None:
    """Compute volumetric weight (cm^3 / 6000) when dimensions are present."""
    if not dimensions:
        return None
    try:
        volume = (
            Decimal(str(dimensions["length"]))
            * Decimal(str(dimensions["width"]))
            * Decimal(str(dimensions["height"]))
        )
    except (KeyError, TypeError, ValueError):
        return None
    return volume / Decimal("6000")


def _effective_weight_kg(weight_kg: Decimal | None, dimensions: dict | None) -> Decimal | None:
    """Effective shipping weight = max(actual weight, volumetric weight)."""
    volumetric = _volumetric_weight_kg(dimensions)
    if weight_kg is None:
        return volumetric
    if volumetric is None:
        return weight_kg
    return max(weight_kg, volumetric)


def _logistics_score(weight_kg: Decimal | None) -> Decimal:
    """Deterministic logistics score from effective weight (0-10).

    Tiers (docs/product_strategy.md §6.1, 物流友好度): light items score high;
    heavy/bulky items score low. A missing weight is treated as unknown (low).
    """
    if weight_kg is None:
        return Decimal("0.00")
    tiers = (
        (Decimal("0.3"), Decimal("10.00")),
        (Decimal("0.5"), Decimal("9.00")),
        (Decimal("1.0"), Decimal("7.50")),
        (Decimal("2.0"), Decimal("6.00")),
        (Decimal("3.0"), Decimal("4.50")),
        (Decimal("5.0"), Decimal("3.00")),
    )
    for threshold, score in tiers:
        if weight_kg <= threshold:
            return score
    return Decimal("1.00")


def _profit_score(margin_rate: Decimal | None) -> Decimal:
    """Map a gross margin rate to a 0-10 profit score.

    docs/product_strategy.md §6.1: >=45% -> 10, each 5pp below deducts 1.5,
    <25% -> 0. No margin (unknown cost) -> 0.
    """
    if margin_rate is None:
        return Decimal("0.00")
    rate = float(margin_rate)
    if rate >= 0.45:
        return Decimal("10.00")
    if rate < 0.25:
        return Decimal("0.00")
    score = 10.0 - (0.45 - rate) / 0.05 * 1.5
    return Decimal(str(round(max(0.0, min(10.0, score)), 2)))


def _recommended_price(total_cost: Decimal) -> Decimal | None:
    """Price = total_cost / (1 - target_margin), psychological .99 ending."""
    if total_cost <= ZERO:
        return None
    price = total_cost / (Decimal("1") - TARGET_MARGIN)
    return (price.quantize(Decimal("1"), ROUND_HALF_UP) - Decimal("0.01")).quantize(Decimal("0.01"))


def _derive_sku(title: str, source_url: str | None) -> str:
    """Deterministic SKU from source url (or title) for intake without sku."""
    seed = source_url or title
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10].upper()
    return f"NTO-{digest}"


async def _load_cost(
    session: AsyncSession, *, workspace_id: UUID, product_id: UUID
) -> ProductCost | None:
    """Return the newest current cost row for a product (if any)."""
    rows = (
        await session.execute(
            select(ProductCost)
            .where(
                ProductCost.workspace_id == workspace_id,
                ProductCost.product_id == product_id,
            )
            .order_by(ProductCost.valid_from.desc())
        )
    ).scalars().all()
    return rows[0] if rows else None


async def _rule_context(
    *,
    total_cost: Decimal,
    margin_rate: Decimal | None,
    cost_status: str,
    weight_kg: Decimal | None,
    shipping_ratio: Decimal | None,
) -> dict:
    """Build the PRODUCT rule check context (numbers as JSON-safe floats)."""
    return {
        "product": {"weight_kg": float(weight_kg) if weight_kg is not None else None},
        "cost": {"total_cost": float(total_cost)},
        "profit": {
            "margin_rate": float(margin_rate) if margin_rate is not None else None,
            "cost_status": cost_status,
        },
        "logistics": {
            "shipping_ratio": float(shipping_ratio) if shipping_ratio is not None else None,
            "weight_kg": float(weight_kg) if weight_kg is not None else None,
        },
    }


async def analyze_product(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    trace_id: str | None = None,
) -> ScoreContext:
    """Run the deterministic chain: Cost -> Logistics -> Profit -> Rules -> Score.

    Persists a ``product_scores`` row and a ``product_analysis_runs`` audit row.
    """
    started = time.perf_counter()
    product = (
        await session.execute(
            select(Product).where(
                Product.workspace_id == workspace_id,
                Product.id == product_id,
            )
        )
    ).scalar_one_or_none()
    if product is None:
        raise ProductIntelligenceError("product not found")

    cost = await _load_cost(session, workspace_id=workspace_id, product_id=product_id)
    total_cost = cost.total_cost if cost else ZERO
    cost_status = "KNOWN" if total_cost > ZERO else "UNKNOWN"

    effective_weight = _effective_weight_kg(product.weight_kg, product.dimensions)
    logistics = _logistics_score(effective_weight)

    price = _recommended_price(total_cost)
    margin_rate: Decimal | None = None
    shipping_ratio: Decimal | None = None
    if price is not None:
        profit = calculate_contribution_margin(
            ProfitInput(revenue=price, product_cost=total_cost)
        )
        margin_rate = profit.contribution_margin_rate
        shipping = (cost.first_leg_shipping + cost.last_leg_shipping) if cost else ZERO
        if shipping > ZERO and price > ZERO:
            shipping_ratio = (shipping / price).quantize(Decimal("0.0001"))

    profit_dim = _profit_score(margin_rate)
    dimensions: dict[str, Decimal] = {
        "profit": profit_dim,
        "logistics": logistics,
        "demand": NEUTRAL_DIMENSION,
        "competition": NEUTRAL_DIMENSION,
        "differentiation": NEUTRAL_DIMENSION,
        "compliance": NEUTRAL_DIMENSION,
    }
    reasons: dict[str, list[str]] = {
        "profit": ["derived from gross margin at recommended price"]
        if margin_rate is not None
        else ["cost unknown; profit dimension not scored"],
        "logistics": [
            f"effective weight {effective_weight} kg (actual/volumetric)"
            if effective_weight is not None
            else "weight missing; logistics dimension not scored"
        ],
        "demand": ["requires market trend data (deterministic phase; LLM pending)"],
        "competition": ["requires competitor research (deterministic phase; LLM pending)"],
        "differentiation": ["requires product analysis (deterministic phase; LLM pending)"],
        "compliance": ["requires compliance checklist review (deterministic phase; LLM pending)"],
    }

    total = sum(
        dimensions[key] * Decimal(str(SCORE_WEIGHTS[key]))
        for key in SCORE_WEIGHTS
    ) * Decimal("10")
    total = total.quantize(Decimal("0.01"))

    # Rule engine step (rules loaded from the registry, never hardcoded).
    context = await _rule_context(
        total_cost=total_cost,
        margin_rate=margin_rate,
        cost_status=cost_status,
        weight_kg=effective_weight,
        shipping_ratio=shipping_ratio,
    )
    check = await rule_engine.check(
        session,
        workspace_id=workspace_id,
        group="PRODUCT",
        context=context,
        trace_id=trace_id,
    )
    vetoed = any(
        r.rule_type == "hard" and not r.passed for r in check.results
    )
    rule_results = [r.model_dump() for r in check.results]

    scored_at = datetime.now(UTC)
    score = ProductScore(
        workspace_id=workspace_id,
        product_id=product_id,
        profit=profit_dim,
        logistics=logistics,
        demand=dimensions["demand"],
        competition=dimensions["competition"],
        differentiation=dimensions["differentiation"],
        compliance=dimensions["compliance"],
        total=total,
        model_version=SCORE_MODEL_VERSION,
        rule_version=SCORE_RULE_VERSION,
        scored_at=scored_at,
        trace_id=trace_id,
    )
    session.add(score)

    latency_ms = int((time.perf_counter() - started) * 1000)
    run = ProductAnalysisRun(
        workspace_id=workspace_id,
        product_id=product_id,
        provider="deterministic",
        model="heuristic-v1",
        prompt_version=None,
        input_snapshot={
            "product_id": str(product_id),
            "total_cost": str(total_cost),
            "cost_status": cost_status,
            "weight_kg": str(effective_weight) if effective_weight is not None else None,
            "dimensions": product.dimensions,
            "target_market": product.target_market,
        },
        output={
            "dimensions": {k: str(v) for k, v in dimensions.items()},
            "total": str(total),
            "vetoed": vetoed,
            "recommended_price": str(price) if price is not None else None,
            "shipping_ratio": str(shipping_ratio) if shipping_ratio is not None else None,
        },
        token_usage={},
        estimated_cost=ZERO,
        latency_ms=latency_ms,
        status="completed",
        trace_id=trace_id,
    )
    session.add(run)
    await session.flush()

    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="product.scored",
        entity_type="product",
        entity_id=str(product_id),
        payload={
            "total": str(total),
            "vetoed": vetoed,
            "model_version": SCORE_MODEL_VERSION,
        },
        trace_id=trace_id,
    )

    logger.info(
        "product %s scored total=%s vetoed=%s trace=%s",
        product_id, total, vetoed, trace_id,
    )
    return ScoreContext(
        product_id=product_id,
        dimensions=dimensions,
        total=total,
        vetoed=vetoed,
        margin_rate=margin_rate,
        recommended_price=price,
        shipping_ratio=shipping_ratio,
        cost_status=cost_status,
        reasons=reasons,
        rule_results=rule_results,
    )


def _raw_data_snapshot(data: ProductIntakeRequest) -> dict:
    """Serialize intake fields to a JSON-safe raw_data dict (Decimal -> str)."""
    snapshot = data.model_dump()
    cost_keys = ("purchase_cost", "domestic_shipping", "first_leg_shipping",
                 "last_leg_shipping", "weight_kg")
    for key in cost_keys:
        value = snapshot.get(key)
        if isinstance(value, Decimal):
            snapshot[key] = str(value)
    return snapshot


async def _upsert_product_cost(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    data: ProductIntakeRequest,
    trace_id: str | None,
) -> tuple[ProductCost, Decimal, UUID]:
    """Upsert the current cost row and append an immutable history snapshot."""
    total_cost = (
        data.purchase_cost
        + data.domestic_shipping
        + data.first_leg_shipping
        + data.last_leg_shipping
    )
    cost = await _load_cost(session, workspace_id=workspace_id, product_id=product_id)
    if cost is None:
        cost = ProductCost(
            workspace_id=workspace_id,
            product_id=product_id,
            currency=data.currency,
            purchase_price=data.purchase_cost,
            domestic_shipping=data.domestic_shipping,
            first_leg_shipping=data.first_leg_shipping,
            last_leg_shipping=data.last_leg_shipping,
            total_cost=total_cost,
            valid_from=datetime.now(UTC),
        )
        session.add(cost)
        await session.flush()
    else:
        cost.currency = data.currency
        cost.purchase_price = data.purchase_cost
        cost.domestic_shipping = data.domestic_shipping
        cost.first_leg_shipping = data.first_leg_shipping
        cost.last_leg_shipping = data.last_leg_shipping
        cost.total_cost = total_cost
        cost.valid_from = datetime.now(UTC)

    snapshot = ProductCostSnapshot(
        workspace_id=workspace_id,
        product_id=product_id,
        currency=data.currency,
        purchase_price=data.purchase_cost,
        domestic_shipping=data.domestic_shipping,
        first_leg_shipping=data.first_leg_shipping,
        last_leg_shipping=data.last_leg_shipping,
        total_cost=total_cost,
        weight_kg=data.weight_kg,
        source="intake",
        valid_from=datetime.now(UTC),
        trace_id=trace_id,
    )
    session.add(snapshot)
    await session.flush()
    return cost, total_cost, snapshot.id


async def intake_product(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: ProductIntakeRequest,
    trace_id: str | None = None,
) -> ProductIntakeResult:
    """Manual product intake: product + source + cost + snapshot + analysis.

    The intake runs the deterministic analysis chain immediately so every
    candidate has a persisted score and audit trail.
    """
    sku = data.sku or _derive_sku(data.title, data.source_url)
    supplier_id: UUID | None = None
    if data.supplier_code:
        supplier = (
            await session.execute(
                select(Supplier.id).where(
                    Supplier.workspace_id == workspace_id,
                    Supplier.code == data.supplier_code,
                )
            )
        ).scalar_one_or_none()
        if supplier is None:
            raise ProductIntelligenceError(
                f"supplier_code '{data.supplier_code}' not found"
            )
        supplier_id = supplier

    product = (
        await session.execute(
            select(Product).where(
                Product.workspace_id == workspace_id,
                Product.sku == sku,
            )
        )
    ).scalar_one_or_none()
    if product is None:
        product = Product(
            workspace_id=workspace_id,
            sku=sku,
            name=data.title,
            status="candidate",
            source="intake",
            source_url=data.source_url,
            weight_kg=data.weight_kg,
            dimensions=data.dimensions,
            target_market=data.target_market,
        )
        session.add(product)
        await session.flush()
    else:
        product.name = data.title
        product.description = data.description
        product.source_url = data.source_url
        product.weight_kg = data.weight_kg
        product.dimensions = data.dimensions
        product.target_market = data.target_market

    source = ProductSource(
        workspace_id=workspace_id,
        product_id=product.id,
        source_type=data.source_type,
        source_url=data.source_url,
        supplier_id=supplier_id,
        supplier_code=data.supplier_code,
        captured_at=datetime.now(UTC),
        raw_data=_raw_data_snapshot(data),
        trace_id=trace_id,
    )
    session.add(source)

    _cost, total_cost, snapshot_id = await _upsert_product_cost(
        session,
        workspace_id=workspace_id,
        product_id=product.id,
        data=data,
        trace_id=trace_id,
    )
    await session.flush()

    score = await analyze_product(
        session, workspace_id=workspace_id, product_id=product.id, trace_id=trace_id
    )

    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="product.intaked",
        entity_type="product",
        entity_id=str(product.id),
        payload={
            "sku": sku,
            "source_type": data.source_type,
            "total_cost": str(total_cost),
            "score": str(score.total),
        },
        trace_id=trace_id,
    )

    # Locate the just-created score row for the response.
    score_row = (
        await session.execute(
            select(ProductScore)
            .where(
                ProductScore.workspace_id == workspace_id,
                ProductScore.product_id == product.id,
            )
            .order_by(ProductScore.scored_at.desc())
        )
    ).scalars().first()

    return ProductIntakeResult(
        product=product,
        source_id=source.id,
        cost_snapshot_id=snapshot_id,
        score_id=score_row.id if score_row is not None else product.id,
    )


async def propose_decision(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    trace_id: str | None = None,
) -> ProductDecision:
    """Propose a decision from the latest score (deterministic, pending approval)."""
    score = (
        await session.execute(
            select(ProductScore)
            .where(
                ProductScore.workspace_id == workspace_id,
                ProductScore.product_id == product_id,
            )
            .order_by(ProductScore.scored_at.desc())
        )
    ).scalars().first()
    if score is None:
        raise ProductIntelligenceError("product has no score; run analysis first")

    cost = await _load_cost(session, workspace_id=workspace_id, product_id=product_id)
    total_cost = cost.total_cost if cost else ZERO
    cost_status = "KNOWN" if total_cost > ZERO else "UNKNOWN"
    price = _recommended_price(total_cost)

    # Re-run the PRODUCT rule check so the decision reflects current gates.
    margin_rate: Decimal | None = None
    if price is not None:
        margin_rate = calculate_contribution_margin(
            ProfitInput(revenue=price, product_cost=total_cost)
        ).contribution_margin_rate
    context = await _rule_context(
        total_cost=total_cost,
        margin_rate=margin_rate,
        cost_status=cost_status,
        weight_kg=None,
        shipping_ratio=None,
    )
    check = await rule_engine.check(
        session,
        workspace_id=workspace_id,
        group="PRODUCT",
        context=context,
        trace_id=trace_id,
    )
    vetoed = any(r.rule_type == "hard" and not r.passed for r in check.results)

    if vetoed:
        decision_type = "reject"
    elif cost_status == "UNKNOWN":
        decision_type = "hold"
    elif score.total >= Decimal("75.00") and (margin_rate or ZERO) >= Decimal("0.30"):
        decision_type = "test"
    elif score.total >= Decimal("60.00"):
        decision_type = "hold"
    else:
        decision_type = "reject"

    reasons = [
        f"total score {score.total} (model {SCORE_MODEL_VERSION}, rules {SCORE_RULE_VERSION})",
        f"gross margin at recommended price {margin_rate * 100:.1f}%"
        if margin_rate is not None
        else "gross margin unavailable (cost unknown)",
        f"cost status {cost_status}",
    ]
    if vetoed:
        reasons.append("hard product gate failed (veto)")
    risks = [
        "market/competition data not collected (deterministic phase; LLM pending)",
        "costs are initial intake values and need supplier verification",
    ]
    if cost_status == "UNKNOWN":
        risks.append("product cost is UNKNOWN; profitability not concluded")

    confidence = CONFIDENCE_BY_STATUS.get(cost_status, Decimal("0.300"))
    max_cac: Decimal | None = None
    if price is not None:
        max_cac = (price - total_cost).quantize(Decimal("0.01"))

    decision = ProductDecision(
        workspace_id=workspace_id,
        product_id=product_id,
        decision=decision_type,
        score=score.total,
        confidence=confidence,
        reasons=reasons,
        risks=risks,
        recommended_price=price,
        max_cac=max_cac,
        test_quantity=TEST_QUANTITY if decision_type == "test" else None,
        test_days=TEST_DAYS if decision_type == "test" else None,
        approval_status="pending",
        trace_id=trace_id,
    )
    session.add(decision)
    await session.flush()

    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="product.decision.proposed",
        entity_type="product",
        entity_id=str(product_id),
        payload={
            "decision": decision_type,
            "score": str(score.total),
            "confidence": str(confidence),
        },
        trace_id=trace_id,
    )
    logger.info("product %s decision=%s proposed trace=%s", product_id, decision_type, trace_id)
    return decision


async def _load_decision(
    session: AsyncSession, *, workspace_id: UUID, decision_id: UUID
) -> ProductDecision | None:
    return (
        await session.execute(
            select(ProductDecision).where(
                ProductDecision.workspace_id == workspace_id,
                ProductDecision.id == decision_id,
            )
        )
    ).scalar_one_or_none()


async def approve_decision(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    decision_id: UUID,
    actor: str,
    trace_id: str | None = None,
) -> ProductDecision:
    """Approve a pending decision; a test decision advances the lifecycle."""
    decision = await _load_decision(session, workspace_id=workspace_id, decision_id=decision_id)
    if decision is None:
        raise ProductIntelligenceError("decision not found")
    if decision.approval_status != "pending":
        raise ProductIntelligenceError("decision is not pending")
    now = datetime.now(UTC)
    decision.approval_status = "approved"
    decision.approved_by = actor
    decision.approved_at = now
    decision.updated_at = now  # onupdate is SQL-side; keep the attribute current

    if decision.decision == "test":
        product = (
            await session.execute(
                select(Product).where(
                    Product.workspace_id == workspace_id,
                    Product.id == decision.product_id,
                )
            )
        ).scalar_one_or_none()
        if product is not None:
            product.status = "test"

    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="product.decision.approved",
        entity_type="product",
        entity_id=str(decision.product_id),
        payload={"decision": decision.decision, "approved_by": actor},
        trace_id=trace_id,
    )
    return decision


async def reject_decision(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    decision_id: UUID,
    actor: str,
    trace_id: str | None = None,
) -> ProductDecision:
    """Reject a pending decision (audited, lifecycle unchanged)."""
    decision = await _load_decision(session, workspace_id=workspace_id, decision_id=decision_id)
    if decision is None:
        raise ProductIntelligenceError("decision not found")
    if decision.approval_status != "pending":
        raise ProductIntelligenceError("decision is not pending")
    now = datetime.now(UTC)
    decision.approval_status = "rejected"
    decision.approved_by = actor
    decision.approved_at = now
    decision.updated_at = now  # onupdate is SQL-side; keep the attribute current
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="product.decision.rejected",
        entity_type="product",
        entity_id=str(decision.product_id),
        payload={"decision": decision.decision, "approved_by": actor},
        trace_id=trace_id,
    )
    return decision


async def list_sources(
    session: AsyncSession, *, workspace_id: UUID, product_id: UUID
) -> list[ProductSource]:
    rows = (
        await session.execute(
            select(ProductSource)
            .where(
                ProductSource.workspace_id == workspace_id,
                ProductSource.product_id == product_id,
            )
            .order_by(ProductSource.captured_at.desc())
        )
    ).scalars().all()
    return list(rows)


async def list_cost_snapshots(
    session: AsyncSession, *, workspace_id: UUID, product_id: UUID
) -> list[ProductCostSnapshot]:
    rows = (
        await session.execute(
            select(ProductCostSnapshot)
            .where(
                ProductCostSnapshot.workspace_id == workspace_id,
                ProductCostSnapshot.product_id == product_id,
            )
            .order_by(ProductCostSnapshot.valid_from.desc())
        )
    ).scalars().all()
    return list(rows)


async def latest_score(
    session: AsyncSession, *, workspace_id: UUID, product_id: UUID
) -> ProductScore | None:
    return (
        await session.execute(
            select(ProductScore)
            .where(
                ProductScore.workspace_id == workspace_id,
                ProductScore.product_id == product_id,
            )
            .order_by(ProductScore.scored_at.desc())
        )
    ).scalars().first()


async def latest_analysis(
    session: AsyncSession, *, workspace_id: UUID, product_id: UUID
) -> ProductAnalysisRun | None:
    return (
        await session.execute(
            select(ProductAnalysisRun)
            .where(
                ProductAnalysisRun.workspace_id == workspace_id,
                ProductAnalysisRun.product_id == product_id,
            )
            .order_by(ProductAnalysisRun.created_at.desc())
        )
    ).scalars().first()


async def latest_decision(
    session: AsyncSession, *, workspace_id: UUID, product_id: UUID
) -> ProductDecision | None:
    return (
        await session.execute(
            select(ProductDecision)
            .where(
                ProductDecision.workspace_id == workspace_id,
                ProductDecision.product_id == product_id,
            )
            .order_by(ProductDecision.created_at.desc())
        )
    ).scalars().first()
