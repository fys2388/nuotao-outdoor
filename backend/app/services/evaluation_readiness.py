"""Evaluation Readiness — V3_READY / V3_NEEDS_DATA / V3_BLOCKED matrix.

Determines whether a ProductEvaluationContext has enough data for V3 scoring,
and what the next actions should be.

Design rules:
- UNKNOWN is never treated as PASS, 0, or NEUTRAL.
- Auto-enrichable fields trigger V3_NEEDS_DATA (with retry instructions).
- Non-enrichable missing fields trigger V3_BLOCKED.
- Every decision is traceable via missing_fields + next_actions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.services import data_integrity_gate
from app.services.evaluation_context import ProductEvaluationContext
from app.services.nuotao_score_mapper import ScoreFacts


# Fields that can be auto-enriched by the orchestrator's enrichment loop
AUTO_ENRICHABLE_FIELDS: frozenset[str] = frozenset({
    "operational_dimensions",
    "margin_rate",
    "shipping_ratio",
    "reference_price_usd",
    "weight_kg",
    "supplier_rating",
    "category",
})

# Fields that cannot be auto-enriched (require AI or historical data)
NON_ENRICHABLE_FIELDS: frozenset[str] = frozenset({
    "brand_fit",
    "return_rate",
})

# Fields whose ABSENCE makes V3 scoring impossible. ``map_dimensions_strict``
# hard-requires the six operational dimensions and a brand_fit override; a
# missing return_rate is tolerated there (veto V12 simply stays "pending").
# Only these may block V3_READY - treating every non-enrichable field as a
# blocker would deadlock the pipeline, because return_rate has no data source
# yet (see docs/design/PRODUCT_EVALUATION_CONTEXT_V1.md 6.3) and is therefore
# missing on every product.
REQUIRED_FOR_V3: frozenset[str] = frozenset({
    "operational_dimensions",
    "brand_fit",
})

# Subset of REQUIRED_FOR_V3 produced by a LATER orchestrator stage
# (AI_ANALYSIS), not by enrichment. S2 must not require these: it runs before
# that stage, so demanding them here would deadlock the pipeline (S2 waits for
# an output that only exists after S2).
AI_SUPPLIED_FIELDS: frozenset[str] = frozenset({
    "brand_fit",
})


@dataclass
class ReadinessResult:
    """Outcome of a readiness check."""

    status: str  # V3_READY | V3_NEEDS_DATA | V3_BLOCKED
    score: Decimal
    missing_fields: list[str]
    auto_enrichable_missing: list[str]
    non_enrichable_missing: list[str]
    next_actions: list[str]
    version: str = "v1"

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "score": float(self.score),
            "missing_fields": self.missing_fields,
            "auto_enrichable_missing": self.auto_enrichable_missing,
            "non_enrichable_missing": self.non_enrichable_missing,
            "next_actions": self.next_actions,
            "version": self.version,
        }


def evaluate_readiness(ctx: ProductEvaluationContext) -> ReadinessResult:
    """Evaluate V3 readiness for a ProductEvaluationContext.

    Uses data_integrity_gate.check_integrity() for the completeness score,
    then classifies missing fields into auto-enrichable vs non-enrichable.

    Returns:
        ReadinessResult with status, missing fields, and next actions.
    """
    facts = ScoreFacts(
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

    gate = data_integrity_gate.check_integrity(facts)

    auto_missing = [f for f in gate.missing_fields if f in AUTO_ENRICHABLE_FIELDS]
    non_enrichable = [f for f in gate.missing_fields if f in NON_ENRICHABLE_FIELDS]
    # Only gaps this stage is responsible for resolving block readiness:
    # REQUIRED_FOR_V3 minus whatever a later stage supplies (brand_fit comes
    # from AI_ANALYSIS) - otherwise S2 would wait on its own downstream stage.
    blocking = [
        f
        for f in gate.missing_fields
        if f in REQUIRED_FOR_V3 and f not in AI_SUPPLIED_FIELDS
    ]

    # Readiness decision (design doc 6.1-6.3), scoped to what S2 can act on:
    # - V3_READY: gate passed AND no gap left that only this stage could close.
    #   brand_fit is excluded because AI_ANALYSIS supplies it downstream;
    #   return_rate is tolerated by map_dimensions_strict (V12 stays pending).
    #   Requiring either here would deadlock or permanently block the pipeline.
    # - V3_NEEDS_DATA: an auto-enrichable gap remains -> backfill and retry.
    # - V3_BLOCKED: nothing left that enrichment can fix -> Exception Queue.
    if gate.passed and not blocking:
        status = "V3_READY"
        next_actions = ["Run V3 evaluation"]
    elif auto_missing:
        status = "V3_NEEDS_DATA"
        next_actions = _build_enrichment_actions(auto_missing)
        if non_enrichable:
            next_actions += [
                f"Manually resolve: {', '.join(non_enrichable)}",
                "AI assessment closes brand_fit; return_rate has no source yet",
            ]
    else:
        status = "V3_BLOCKED"
        next_actions = [
            f"Cannot auto-enrich: {', '.join(non_enrichable or blocking)}",
            "Require AI assessment (brand_fit) or historical data (return_rate)",
        ]

    return ReadinessResult(
        status=status,
        score=gate.score,
        missing_fields=gate.missing_fields,
        auto_enrichable_missing=auto_missing,
        non_enrichable_missing=non_enrichable,
        next_actions=next_actions,
    )


def _build_enrichment_actions(missing: list[str]) -> list[str]:
    """Map missing fields to concrete enrichment actions."""
    actions = []
    for field in missing:
        if field == "operational_dimensions":
            actions.append("Run operational scoring (ProductScore)")
        elif field == "margin_rate":
            actions.append("Sync cost data (cost_sync_service)")
        elif field == "shipping_ratio":
            actions.append("Sync cost data (cost_sync_service)")
        elif field == "reference_price_usd":
            actions.append("Extract price from Product.meta or sync cost")
        elif field == "weight_kg":
            actions.append("Backfill from 1688 (backfill_1688_service)")
        elif field == "supplier_rating":
            actions.append("Link supplier (SourcingCandidate)")
        elif field == "category":
            actions.append("Backfill from 1688 (backfill_1688_service)")
    return actions
