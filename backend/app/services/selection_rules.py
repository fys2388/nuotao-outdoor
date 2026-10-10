"""Selection veto rules engine — V1-V12 proactive rejection execution.

Executes the 12 proactive veto rules defined in nuotao_score_v3.py against
a product's structured context. This is the deterministic layer of the
LangGraph selection workflow; AI-assisted rules (V1, V2) return
``uncertain`` and are resolved by the Product Analyst Agent.

Design principles (AGENTS.md §3):
- Agent is a "proposer" not an "executor": veto results are proposals
  that feed into the decision node, not direct rejections.
- Deterministic checks are computed from structured data only; no
  LLM calls in this module.
- AI/hybrid rules return ``uncertain`` so the LLM layer can resolve them.
- Every result carries evidence for audit (ai_agent_runs / ai_suggestions).

Maps to:
- docs/nuotao_product_score_v3.0.md §3 (V1-V12 catalogue)
- backend/app/services/nuotao_score_v3.py (VETO_RULES spec)
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.schemas.selection_workflow import VetoCheckResult
from app.services.nuotao_score_v3 import (
    BRAND_FIT_VETO_BELOW,
    MARGIN_MIN,
    RETURN_RATE_MAX,
    SHIPPING_RATIO_MAX,
    VETO_RULES,
)


# ── Rule context ────────────────────────────────────────────────────
@dataclass
class VetoRuleContext:
    """Structured context required to evaluate all 12 veto rules.

    All fields are optional: a None value means "data not available"
    and the rule returns ``uncertain`` rather than failing open or
    closed. This prevents the engine from fabricating clearance on
    missing data (AGENTS.md §1.2 rule 5).
    """

    # Pricing & margin
    reference_price_usd: Decimal | None = None
    margin_rate: Decimal | None = None
    shipping_ratio: Decimal | None = None

    # Brand & scoring
    brand_fit: Decimal | None = None
    nuotao_score_total: Decimal | None = None

    # Supplier
    supplier_rating: str | None = None  # A / B / C / D

    # Category & compliance
    category: str | None = None
    category_in_banned_list: bool | None = None
    category_overlaps_hero: bool | None = None
    compliance_requirements: list[str] | None = None
    banned_subcategories: list[str] | None = None

    # Logistics & returns
    return_rate: Decimal | None = None
    is_banned_shipment: bool | None = None

    # AI-owned signals (filled by Product Analyst Agent)
    ai_ip_risk_verdict: str | None = None  # pass / fail / uncertain
    ai_regulatory_verdict: str | None = None
    ai_safety_verdict: str | None = None
    ai_brand_focus_verdict: str | None = None
    ai_supplier_verdict: str | None = None
    ai_return_risk_verdict: str | None = None

    # AI reasons (one-line explanations from the analyst)
    ai_reasons: dict[str, str] | None = None


def _reasons(context: VetoRuleContext) -> dict[str, str]:
    return context.ai_reasons or {}


def _as_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (TypeError, ValueError):
        return None


# ── Individual rule evaluators ──────────────────────────────────────
# Each returns a VetoCheckResult. Verdict is pass / fail / uncertain.


def _eval_v1_ip(context: VetoRuleContext) -> VetoCheckResult:
    """V1: intellectual property infringement (AI-owned)."""
    verdict = context.ai_ip_risk_verdict or "uncertain"
    reason = _reasons(context).get(
        "V1", "IP risk requires AI patent/trademark analysis"
    )
    return VetoCheckResult(
        rule_id="V1",
        rule_name=VETO_RULES["V1"].name,
        category="compliance",
        check_type="ai",
        verdict=verdict,
        reason=reason,
        evidence={"source": "ai_product_analyst"},
    )


def _eval_v2_regulatory(context: VetoRuleContext) -> VetoCheckResult:
    """V2: regulatory and certification compliance (AI-owned)."""
    verdict = context.ai_regulatory_verdict or "uncertain"
    reason = _reasons(context).get(
        "V2", "Regulatory compliance requires AI certification analysis"
    )
    return VetoCheckResult(
        rule_id="V2",
        rule_name=VETO_RULES["V2"].name,
        category="compliance",
        check_type="ai",
        verdict=verdict,
        reason=reason,
        evidence={"source": "ai_product_analyst"},
    )


def _eval_v3_safety(context: VetoRuleContext) -> VetoCheckResult:
    """V3: product safety (hybrid: AI verdict + structured evidence)."""
    verdict = context.ai_safety_verdict or "uncertain"
    reason = _reasons(context).get(
        "V3", "Safety assessment requires AI product-structure analysis"
    )
    return VetoCheckResult(
        rule_id="V3",
        rule_name=VETO_RULES["V3"].name,
        category="compliance",
        check_type="hybrid",
        verdict=verdict,
        reason=reason,
        evidence={"source": "ai_product_analyst"},
    )


def _eval_v4_banned(context: VetoRuleContext) -> VetoCheckResult:
    """V4: target-market banned category (deterministic)."""
    if context.category_in_banned_list is True:
        return VetoCheckResult(
            rule_id="V4",
            rule_name=VETO_RULES["V4"].name,
            category="compliance",
            check_type="deterministic",
            verdict="fail",
            reason=f"Category '{context.category}' is in the banned list",
            evidence={"category": context.category},
        )
    if context.category_in_banned_list is None:
        return VetoCheckResult(
            rule_id="V4",
            rule_name=VETO_RULES["V4"].name,
            category="compliance",
            check_type="deterministic",
            verdict="uncertain",
            reason="Banned list check requires category data",
            evidence={},
        )
    return VetoCheckResult(
        rule_id="V4",
        rule_name=VETO_RULES["V4"].name,
        category="compliance",
        check_type="deterministic",
        verdict="pass",
        reason=f"Category '{context.category}' is not in the banned list",
        evidence={"category": context.category},
    )


def _eval_v5_brand_focus(context: VetoRuleContext) -> VetoCheckResult:
    """V5: brand focus disruption (hybrid)."""
    verdict = context.ai_brand_focus_verdict or "uncertain"
    reason = _reasons(context).get(
        "V5", "Brand focus requires AI category-strategy analysis"
    )
    return VetoCheckResult(
        rule_id="V5",
        rule_name=VETO_RULES["V5"].name,
        category="brand",
        check_type="hybrid",
        verdict=verdict,
        reason=reason,
        evidence={"source": "ai_product_analyst"},
    )


def _eval_v6_low_price(context: VetoRuleContext) -> VetoCheckResult:
    """V6: low-price general merchandise (deterministic, price < $5)."""
    price = _as_decimal(context.reference_price_usd)
    if price is None:
        return VetoCheckResult(
            rule_id="V6",
            rule_name=VETO_RULES["V6"].name,
            category="brand",
            check_type="deterministic",
            verdict="uncertain",
            reason="Price data not available",
            evidence={},
        )
    if price < Decimal("5"):
        return VetoCheckResult(
            rule_id="V6",
            rule_name=VETO_RULES["V6"].name,
            category="brand",
            check_type="deterministic",
            verdict="fail",
            reason=f"Reference price ${price} is below $5 impulse-buy threshold",
            evidence={"price_usd": str(price), "threshold": "5.00"},
        )
    return VetoCheckResult(
        rule_id="V6",
        rule_name=VETO_RULES["V6"].name,
        category="brand",
        check_type="deterministic",
        verdict="pass",
        reason=f"Reference price ${price} is above $5 threshold",
        evidence={"price_usd": str(price)},
    )


def _eval_v7_hero_conflict(context: VetoRuleContext) -> VetoCheckResult:
    """V7: conflict with existing Hero products (deterministic)."""
    if context.category_overlaps_hero is True:
        return VetoCheckResult(
            rule_id="V7",
            rule_name=VETO_RULES["V7"].name,
            category="brand",
            check_type="deterministic",
            verdict="fail",
            reason=f"Category '{context.category}' overlaps with an existing Hero product",
            evidence={"category": context.category},
        )
    if context.category_overlaps_hero is None:
        return VetoCheckResult(
            rule_id="V7",
            rule_name=VETO_RULES["V7"].name,
            category="brand",
            check_type="deterministic",
            verdict="uncertain",
            reason="Hero overlap check requires category + Hero catalogue data",
            evidence={},
        )
    return VetoCheckResult(
        rule_id="V7",
        rule_name=VETO_RULES["V7"].name,
        category="brand",
        check_type="deterministic",
        verdict="pass",
        reason=f"Category '{context.category}' does not overlap with Hero products",
        evidence={"category": context.category},
    )


def _eval_v8_brand_fit(context: VetoRuleContext) -> VetoCheckResult:
    """V8: Brand Fit dimension below 5/10 (deterministic)."""
    brand_fit = _as_decimal(context.brand_fit)
    if brand_fit is None:
        return VetoCheckResult(
            rule_id="V8",
            rule_name=VETO_RULES["V8"].name,
            category="brand",
            check_type="deterministic",
            verdict="uncertain",
            reason="Brand Fit score not available",
            evidence={},
        )
    if brand_fit < BRAND_FIT_VETO_BELOW:
        return VetoCheckResult(
            rule_id="V8",
            rule_name=VETO_RULES["V8"].name,
            category="brand",
            check_type="deterministic",
            verdict="fail",
            reason=f"Brand Fit {brand_fit} is below the hard floor of {BRAND_FIT_VETO_BELOW}",
            evidence={"brand_fit": str(brand_fit), "floor": str(BRAND_FIT_VETO_BELOW)},
        )
    return VetoCheckResult(
        rule_id="V8",
        rule_name=VETO_RULES["V8"].name,
        category="brand",
        check_type="deterministic",
        verdict="pass",
        reason=f"Brand Fit {brand_fit} is above the hard floor of {BRAND_FIT_VETO_BELOW}",
        evidence={"brand_fit": str(brand_fit)},
    )


def _eval_v9_logistics(context: VetoRuleContext) -> VetoCheckResult:
    """V9: logistics infeasibility (deterministic, shipping_ratio > 40%)."""
    if context.is_banned_shipment is True:
        return VetoCheckResult(
            rule_id="V9",
            rule_name=VETO_RULES["V9"].name,
            category="commercial",
            check_type="deterministic",
            verdict="fail",
            reason="Product is a banned shipment item (e.g. pure gas cylinder)",
            evidence={"banned_shipment": True},
        )
    ratio = _as_decimal(context.shipping_ratio)
    if ratio is None:
        return VetoCheckResult(
            rule_id="V9",
            rule_name=VETO_RULES["V9"].name,
            category="commercial",
            check_type="deterministic",
            verdict="uncertain",
            reason="Shipping ratio not available",
            evidence={},
        )
    if ratio > SHIPPING_RATIO_MAX:
        return VetoCheckResult(
            rule_id="V9",
            rule_name=VETO_RULES["V9"].name,
            category="commercial",
            check_type="deterministic",
            verdict="fail",
            reason=f"Shipping ratio {float(ratio):.1%} exceeds {float(SHIPPING_RATIO_MAX):.0%} threshold",
            evidence={
                "shipping_ratio": str(ratio),
                "threshold": str(SHIPPING_RATIO_MAX),
            },
        )
    return VetoCheckResult(
        rule_id="V9",
        rule_name=VETO_RULES["V9"].name,
        category="commercial",
        check_type="deterministic",
        verdict="pass",
        reason=f"Shipping ratio {float(ratio):.1%} is within {float(SHIPPING_RATIO_MAX):.0%} threshold",
        evidence={"shipping_ratio": str(ratio)},
    )


def _eval_v10_margin(context: VetoRuleContext) -> VetoCheckResult:
    """V10: profit infeasibility (deterministic, margin_rate < 20%)."""
    margin = _as_decimal(context.margin_rate)
    if margin is None:
        return VetoCheckResult(
            rule_id="V10",
            rule_name=VETO_RULES["V10"].name,
            category="commercial",
            check_type="deterministic",
            verdict="uncertain",
            reason="Margin rate not available",
            evidence={},
        )
    if margin < MARGIN_MIN:
        return VetoCheckResult(
            rule_id="V10",
            rule_name=VETO_RULES["V10"].name,
            category="commercial",
            check_type="deterministic",
            verdict="fail",
            reason=f"Margin rate {float(margin):.1%} is below {float(MARGIN_MIN):.0%} threshold",
            evidence={"margin_rate": str(margin), "threshold": str(MARGIN_MIN)},
        )
    return VetoCheckResult(
        rule_id="V10",
        rule_name=VETO_RULES["V10"].name,
        category="commercial",
        check_type="deterministic",
        verdict="pass",
        reason=f"Margin rate {float(margin):.1%} is above {float(MARGIN_MIN):.0%} threshold",
        evidence={"margin_rate": str(margin)},
    )


def _eval_v11_supplier(context: VetoRuleContext) -> VetoCheckResult:
    """V11: supplier infeasibility (hybrid, rating below C)."""
    rating = (context.supplier_rating or "").strip().upper()
    if not rating:
        verdict = context.ai_supplier_verdict or "uncertain"
        reason = _reasons(context).get(
            "V11", "Supplier rating not available; AI assessment pending"
        )
    elif rating in ("D",):
        verdict = "fail"
        reason = f"Supplier rating '{rating}' is below the minimum 'C' threshold"
    else:
        # A / B / C are all acceptable
        verdict = "pass"
        reason = f"Supplier rating '{rating}' meets the minimum 'C' threshold"

    return VetoCheckResult(
        rule_id="V11",
        rule_name=VETO_RULES["V11"].name,
        category="commercial",
        check_type="hybrid",
        verdict=verdict,
        reason=reason,
        evidence={"rating": rating or None},
    )


def _eval_v12_return_risk(context: VetoRuleContext) -> VetoCheckResult:
    """V12: return risk (hybrid, return_rate > 15%)."""
    rate = _as_decimal(context.return_rate)
    if rate is None:
        verdict = context.ai_return_risk_verdict or "uncertain"
        reason = _reasons(context).get(
            "V12", "Return rate not available; AI category-risk assessment pending"
        )
    elif rate > RETURN_RATE_MAX:
        verdict = "fail"
        reason = f"Estimated return rate {float(rate):.1%} exceeds {float(RETURN_RATE_MAX):.0%} threshold"
    else:
        verdict = "pass"
        reason = f"Estimated return rate {float(rate):.1%} is within {float(RETURN_RATE_MAX):.0%} threshold"

    return VetoCheckResult(
        rule_id="V12",
        rule_name=VETO_RULES["V12"].name,
        category="commercial",
        check_type="hybrid",
        verdict=verdict,
        reason=reason,
        evidence={"return_rate": str(rate) if rate else None},
    )


# ── Rule dispatch ───────────────────────────────────────────────────
_RULE_EVALUATORS: dict[str, callable] = {
    "V1": _eval_v1_ip,
    "V2": _eval_v2_regulatory,
    "V3": _eval_v3_safety,
    "V4": _eval_v4_banned,
    "V5": _eval_v5_brand_focus,
    "V6": _eval_v6_low_price,
    "V7": _eval_v7_hero_conflict,
    "V8": _eval_v8_brand_fit,
    "V9": _eval_v9_logistics,
    "V10": _eval_v10_margin,
    "V11": _eval_v11_supplier,
    "V12": _eval_v12_return_risk,
}


def evaluate_all_vetoes(context: VetoRuleContext) -> list[VetoCheckResult]:
    """Evaluate all 12 veto rules against the given context.

    Returns a list of 12 VetoCheckResult in V1-V12 order.
    """
    return [_RULE_EVALUATORS[f"V{i}"](context) for i in range(1, 13)]


def any_veto_failed(results: list[VetoCheckResult]) -> bool:
    """True when any veto rule has a definitive 'fail' verdict.

    ``uncertain`` does NOT count as a fail — it must be resolved by the
    AI layer or a human reviewer before a decision is proposed.
    """
    return any(r.verdict == "fail" for r in results)


def veto_summary(results: list[VetoCheckResult]) -> dict[str, Any]:
    """Aggregate veto results into a summary dict for reporting."""
    failed = [r for r in results if r.verdict == "fail"]
    uncertain = [r for r in results if r.verdict == "uncertain"]
    passed = [r for r in results if r.verdict == "pass"]
    return {
        "total": len(results),
        "passed": len(passed),
        "failed": len(failed),
        "uncertain": len(uncertain),
        "any_failed": bool(failed),
        "failed_rules": [r.rule_id for r in failed],
        "uncertain_rules": [r.rule_id for r in uncertain],
    }
