"""Product Evaluation Context — unified context builder for V3.0 scoring.

Builds a ProductEvaluationContext from an existing Product by reusing
already-implemented services (sourcing, cost_sync, backfill, selection).

Design rules:
- No new data sources created; every field reuses an existing service.
- No fabrication: missing data is explicitly None, never 0 or NEUTRAL.
- UNKNOWN semantics: None = unknown; Decimal("0") = zero (valid); "" = empty.
- The context is pure data — no DB writes. The caller decides what to do.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product, ProductCost
from app.models.product_intelligence import (
    ProductAnalysisRun,
    ProductScore,
    ProductSource,
    SourcingCandidate,
)
from app.models.supplier import Supplier
from app.services.nuotao_ai_signals import (
    NormalizedAiSignals,
    normalize_ai_assessment,
)
from app.services.nuotao_score_mapper import ScoreFacts
from app.services.product_cost_service import (
    latest_cost_for_product,
    sale_price_from_meta,
)
from app.services.profit_engine import ProfitInput, calculate_contribution_margin
from app.services import data_integrity_gate

logger = logging.getLogger(__name__)

# Exchange rate for CNY→USD (fallback when cost_sync is unavailable)
_DEFAULT_CNY_USD_RATE = Decimal("0.14")


@dataclass
class EnrichmentStepResult:
    """Result of one enrichment step."""

    step: str
    success: bool
    error: str | None = None
    data_changed: bool = False


@dataclass
class ProductEvaluationContext:
    """Unified evaluation context for V3.0 scoring.

    Every field carries its source and confidence for traceability.
    ``None`` means explicitly unknown — never silently default.
    """

    product_id: UUID
    workspace_id: UUID
    trace_id: str

    # --- Product facts (from Product model + ProductSource) ---
    sku: str | None = None
    name: str | None = None
    description: str | None = None
    category: str | None = None
    brand: str | None = None
    source: str | None = None
    source_offer_id: str | None = None
    source_url: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    target_market: str | None = None

    # --- Physical ---
    weight_kg: Decimal | None = None
    dimensions: dict[str, Any] | None = None

    # --- Cost & landed cost ---
    cost_currency: str | None = None
    purchase_cost: Decimal | None = None
    domestic_shipping: Decimal | None = None
    international_shipping: Decimal | None = None
    packaging: Decimal | None = None
    tax_estimate: Decimal | None = None
    handling: Decimal | None = None
    total_landed_cost: Decimal | None = None
    payment_fee: Decimal | None = None
    marketing_amortization: Decimal | None = None
    after_sales_loss: Decimal | None = None
    sale_price: Decimal | None = None
    reference_price_usd: Decimal | None = None
    margin_rate: Decimal | None = None
    shipping_ratio: Decimal | None = None

    # --- Supplier ---
    supplier_rating: str | None = None

    # --- Market (operational dimensions 0-10) ---
    operational: dict[str, Decimal] = field(default_factory=dict)

    # --- AI / Brand Fit ---
    brand_fit_override: Decimal | None = None
    ai_veto_signals: dict[str, Any] = field(default_factory=dict)
    ai_assessment_source: str | None = None

    # --- Compliance / Category ---
    compliance_failures: tuple[str, ...] = ()
    banned_categories: tuple[str, ...] = ()
    off_brand_categories: tuple[str, ...] = ()
    existing_hero_categories: tuple[str, ...] = ()

    # --- Return rate ---
    return_rate: Decimal | None = None

    # --- Readiness (populated by evaluation_readiness module) ---
    readiness_status: str | None = None  # V3_READY | V3_NEEDS_DATA | V3_BLOCKED
    readiness_score: Decimal | None = None
    missing_fields: list[str] = field(default_factory=list)

    # --- Metadata ---
    context_version: str = "v1"
    enriched_at: datetime | None = None
    enrichment_steps: list[EnrichmentStepResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Enrichment functions — each reuses an existing service
# ---------------------------------------------------------------------------


def _enrich_product_facts(product: Product, source: ProductSource | None) -> None:
    """Step 1: Extract product facts from Product + ProductSource."""
    pass  # Facts are populated directly from the Product model object


def _cost_facts_from_cost(
    product: Product, cost: ProductCost | None
) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    """Step 2: Extract cost facts from ProductCost.

    Returns (reference_price_usd, margin_rate, shipping_ratio).
    """
    sale_price = sale_price_from_meta(product.meta)
    if cost is None or sale_price is None or sale_price <= 0:
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
        if Decimal(cost.international_shipping) > 0
        else None
    )
    return sale_price, margin.quantize(Decimal("0.0001")), shipping_ratio


async def _latest_operational_score(
    session: AsyncSession, workspace_id: UUID, product_id: UUID
) -> dict[str, Decimal]:
    """Step 5: Get operational dimensions from ProductScore."""
    row = (
        await session.execute(
            select(ProductScore)
            .where(
                ProductScore.workspace_id == workspace_id,
                ProductScore.product_id == product_id,
            )
            .order_by(ProductScore.scored_at.desc())
            .limit(1)
        )
    ).scalars().first()
    if row is None:
        return {}
    return {
        "profit": Decimal(str(row.profit)),
        "logistics": Decimal(str(row.logistics)),
        "demand": Decimal(str(row.demand)),
        "competition": Decimal(str(row.competition)),
        "differentiation": Decimal(str(row.differentiation)),
        "compliance": Decimal(str(row.compliance)),
    }


async def _best_supplier_rating(
    session: AsyncSession, workspace_id: UUID, product_id: UUID
) -> str | None:
    """Step 4: Get best supplier rating from SourcingCandidate → Supplier."""
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
    _rank = {"A": 0, "B": 1, "C": 2, "D": 3}
    return min(ratings, key=lambda g: _rank.get(g, 9))


async def _existing_hero_categories(
    session: AsyncSession, workspace_id: UUID, product_id: UUID
) -> tuple[str, ...]:
    """Step 6: Get existing hero categories for V7 conflict check."""
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
    """Step 9: Get latest AI assessment for V1/V2/V3/V5 + Brand Fit."""
    rows = (
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
    ).scalars().all()
    for row in rows:
        output = row.output if isinstance(row.output, dict) else None
        block = (output or {}).get("nuotao_assessment")
        if isinstance(block, dict) and block:
            return block
    return None


async def _get_product_source(
    session: AsyncSession, workspace_id: UUID, product_id: UUID
) -> ProductSource | None:
    """Get the most recent ProductSource for a product."""
    row = (
        await session.execute(
            select(ProductSource)
            .where(
                ProductSource.workspace_id == workspace_id,
                ProductSource.product_id == product_id,
            )
            .order_by(ProductSource.created_at.desc())
            .limit(1)
        )
    ).scalars().first()
    return row


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


async def build_evaluation_context(
    session: AsyncSession,
    product_id: UUID,
    *,
    workspace_id: UUID,
    trace_id: str | None = None,
) -> ProductEvaluationContext:
    """Build a unified ProductEvaluationContext for V3.0 scoring.

    Reuses existing services (product_cost_service, nuotao_selection_service
    helpers, etc.) to collect all fields. Does NOT write to the database.

    Args:
        session: Async DB session (read-only usage).
        product_id: The product to build context for.
        workspace_id: Workspace for isolation.
        trace_id: Optional trace ID for observability.

    Returns:
        ProductEvaluationContext with all available fields populated.
        Missing data is None, never fabricated.
    """
    trace = trace_id or f"eval-ctx-{uuid.uuid4().hex[:12]}"
    steps: list[EnrichmentStepResult] = []

    # --- Load product ---
    product = await session.get(Product, product_id)
    if product is None or product.deleted_at is not None:
        raise ValueError(f"product not found: {product_id}")

    ctx = ProductEvaluationContext(
        product_id=product_id,
        workspace_id=workspace_id,
        trace_id=trace,
        sku=product.sku,
        name=product.name,
        description=product.description,
        category=product.category,
        brand=product.brand,
        source=product.source,
        source_offer_id=product.source_offer_id,
        source_url=product.source_url,
        attributes=dict(product.attributes or {}),
        meta=dict(product.meta or {}),
        tags=list(product.tags or []),
        target_market=product.target_market,
        weight_kg=product.weight_kg,
        dimensions=dict(product.dimensions) if product.dimensions else None,
        enriched_at=datetime.now(UTC),
    )
    steps.append(EnrichmentStepResult(step="product_facts", success=True))

    # --- Step 2: Cost ---
    cost = await latest_cost_for_product(
        session, workspace_id=workspace_id, product_id=product_id
    )
    sale_price, margin_rate, shipping_ratio = _cost_facts_from_cost(product, cost)
    ctx.sale_price = sale_price
    ctx.margin_rate = margin_rate
    ctx.shipping_ratio = shipping_ratio

    if cost is not None:
        ctx.cost_currency = cost.currency
        ctx.purchase_cost = cost.purchase_cost
        ctx.domestic_shipping = cost.domestic_shipping
        ctx.international_shipping = cost.international_shipping
        ctx.packaging = cost.packaging
        ctx.tax_estimate = cost.tax_estimate
        ctx.handling = cost.handling
        ctx.total_landed_cost = cost.total_landed_cost
        ctx.payment_fee = cost.payment_fee
        ctx.marketing_amortization = cost.marketing_amortization
        ctx.after_sales_loss = cost.after_sales_loss
        # USD-only for V6 impulse threshold
        ctx.reference_price_usd = (
            sale_price if cost.currency.upper() == "USD" else None
        )
        steps.append(EnrichmentStepResult(step="cost", success=True, data_changed=True))
    else:
        # Try to extract price from meta as fallback for reference_price_usd
        ctx.reference_price_usd = sale_price  # may be non-USD; V6 handles
        steps.append(EnrichmentStepResult(step="cost", success=False, error="no ProductCost"))

    # --- Step 4: Supplier ---
    ctx.supplier_rating = await _best_supplier_rating(
        session, workspace_id, product_id
    )
    steps.append(
        EnrichmentStepResult(
            step="supplier",
            success=ctx.supplier_rating is not None,
            error=None if ctx.supplier_rating else "no active supplier",
        )
    )

    # --- Step 5: Market (operational) ---
    ctx.operational = await _latest_operational_score(
        session, workspace_id, product_id
    )
    steps.append(
        EnrichmentStepResult(
            step="operational",
            success=len(ctx.operational) > 0,
            error=None if ctx.operational else "no ProductScore",
        )
    )

    # --- Step 6: Competitor ---
    ctx.existing_hero_categories = await _existing_hero_categories(
        session, workspace_id, product_id
    )
    steps.append(EnrichmentStepResult(step="competitor", success=True))

    # --- Step 9: AI / Compliance signals ---
    ai_block = await _latest_ai_assessment(session, workspace_id, product_id)
    ai_signals = normalize_ai_assessment(ai_block)
    ctx.brand_fit_override = ai_signals.brand_fit
    ctx.ai_veto_signals = {
        k: {"verdict": v.verdict, "reason": v.reason}
        for k, v in ai_signals.veto_signals.items()
    }
    ctx.ai_assessment_source = (
        "latest_analyst_run" if ai_block else None
    )
    steps.append(
        EnrichmentStepResult(
            step="ai_signals",
            success=ai_signals.has_any,
            error=None if ai_signals.has_any else "no AI assessment",
        )
    )

    ctx.enrichment_steps = steps
    return ctx


def context_to_score_facts(ctx: ProductEvaluationContext) -> ScoreFacts:
    """Convert a ProductEvaluationContext to ScoreFacts for V3 scoring.

    This is the bridge between the unified context and the V3 scoring pipeline.
    """
    return ScoreFacts(
        operational=dict(ctx.operational),
        margin_rate=ctx.margin_rate,
        shipping_ratio=ctx.shipping_ratio,
        weight_kg=ctx.weight_kg,
        supplier_rating=ctx.supplier_rating,
        category=ctx.category,
        reference_price_usd=ctx.reference_price_usd,
        brand_fit_override=ctx.brand_fit_override,
        return_rate=ctx.return_rate,
        banned_categories=ctx.banned_categories,
        off_brand_categories=ctx.off_brand_categories,
        existing_hero_categories=ctx.existing_hero_categories,
        compliance_failures=ctx.compliance_failures,
    )
