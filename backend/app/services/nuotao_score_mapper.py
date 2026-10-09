"""Map structured product facts to the six V3.0 Nuotao Score dimensions.

Pure and side-effect free. The data the system already holds — the M2.1
six-dimension operational score, contribution margin, shipping ratio, physical
weight and supplier grade (A/B/C/D) — is mapped to the brand-facing V3.0
dimensions Value / Utility / Weight&Packability / Durability / Brand Fit /
Differentiation.

Design rules (AGENTS.md §1.2.5, §2.1):
* No gut-feel business values hidden in flow control — every threshold lives
  in this reviewed, configurable module.
* A missing input yields a neutral, explicitly-flagged dimension, never a
  fabricated precise score; the caller records the evidence flag.
* Brand Fit has no structured source yet, so it uses a neutral default until
  the brand rulebook / AI assessment supplies it (P2); V5/V6/V8 still gate it.

PHASE 6 (data integrity gate):
``map_dimensions`` remains the backward-compatible mapper that uses
``NEUTRAL=5.0`` for absent inputs. The new :func:`map_dimensions_strict`
raises :class:`DataInsufficientError` when a dimension has no real source,
so the V3 selection pipeline never silently fabricates a neutral score.
The data integrity gate (``data_integrity_gate.check_integrity``) must be
called before ``map_dimensions_strict`` to decide whether scoring may proceed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

# Neutral 0-10 score used when a dimension has no structured source yet.
# PHASE 6: this constant is retained for backward compatibility with
# ``map_dimensions``. New code should use ``map_dimensions_strict`` which
# refuses to use it and instead raises when data is missing.
NEUTRAL = Decimal("5.0")
# Supplier A/B/C/D grade -> durability support score (reviewed, configurable).
SUPPLIER_RATING_SCORE: dict[str, Decimal] = {
    "A": Decimal("9.0"),
    "B": Decimal("7.5"),
    "C": Decimal("6.0"),
    "D": Decimal("3.0"),
}
# Reference USD price below which a product reads as an impulse-buy item (V6).
IMPULSE_PRICE_USD = Decimal("5")
# Brand Fit used until a brand rulebook / AI assessment exists (P2).
DEFAULT_BRAND_FIT = Decimal("6.0")
# Operational 0-100 score bar to advance past screening to a deep candidate.
DEEP_CANDIDATE_OP_MIN = Decimal("70")

_ONE = Decimal("1")
_TENTH = Decimal("0.1")


@dataclass
class ScoreFacts:
    """Structured facts collected by the selection service before scoring."""

    # M2.1 operational dimensions (0-10): profit/logistics/demand/competition/
    # differentiation/compliance. Only present keys are treated as real.
    operational: dict[str, Any] = field(default_factory=dict)
    margin_rate: Decimal | None = None          # 0-1 contribution margin rate
    shipping_ratio: Decimal | None = None       # international freight / revenue
    weight_kg: Decimal | None = None
    supplier_rating: str | None = None          # A/B/C/D
    category: str | None = None
    reference_price_usd: Decimal | None = None
    brand_fit_override: Decimal | None = None   # AI/rulebook Brand Fit (P2)
    return_rate: Decimal | None = None          # 0-1 estimated return rate
    banned_categories: tuple[str, ...] = ()      # V4 configured list (hit set)
    off_brand_categories: tuple[str, ...] = ()   # V5 configured list (hit set)
    existing_hero_categories: tuple[str, ...] = ()  # V7 categories with a Hero
    compliance_failures: tuple[str, ...] = ()    # V1-V3 explicit AI flags (P2)


def _op_dim(operational: dict[str, Any], key: str) -> tuple[Decimal, bool]:
    """Return (score 0-10, present) for an operational dimension."""
    raw = operational.get(key)
    if raw is None or raw == "":
        return NEUTRAL, False
    return Decimal(str(raw)), True


def _clamp(score: Decimal) -> Decimal:
    if score < 0:
        return Decimal("0.0")
    if score > 10:
        return Decimal("10.0")
    return score.quantize(_TENTH)


def _blend(primary: Decimal, secondary: Decimal, primary_weight: Decimal) -> Decimal:
    return _clamp(primary * primary_weight + secondary * (_ONE - primary_weight))


def _margin_score(rate: Decimal | None) -> Decimal | None:
    """Contribution margin rate -> 0-10 Value support score."""
    if rate is None:
        return None
    value = Decimal(str(rate))
    if value >= Decimal("0.60"):
        return Decimal("9.0")
    if value >= Decimal("0.45"):
        return Decimal("8.0")
    if value >= Decimal("0.30"):
        return Decimal("7.0")
    if value >= Decimal("0.20"):
        return Decimal("5.5")
    return Decimal("3.5")


def _weight_score(weight_kg: Decimal | None) -> Decimal | None:
    """Physical weight -> 0-10 Weight&Packability support score."""
    if weight_kg is None:
        return None
    weight = Decimal(str(weight_kg))
    if weight <= Decimal("0.3"):
        return Decimal("9.0")
    if weight <= Decimal("0.8"):
        return Decimal("8.0")
    if weight <= Decimal("1.5"):
        return Decimal("7.0")
    if weight <= Decimal("3.0"):
        return Decimal("5.5")
    return Decimal("4.0")


def map_dimensions(facts: ScoreFacts) -> tuple[dict[str, Decimal], dict[str, Any]]:
    """Map :class:`ScoreFacts` to the six V3.0 dimensions plus evidence notes.

    Returns ``(dimensions, evidence)`` where ``dimensions`` has every V3.0 key
    with a 0-10 score and ``evidence`` records the source / missing-data flags
    (persisted for traceability).
    """
    op = facts.operational
    profit, has_profit = _op_dim(op, "profit")
    logistics, has_logistics = _op_dim(op, "logistics")
    demand, has_demand = _op_dim(op, "demand")
    competition, has_competition = _op_dim(op, "competition")
    differentiation, has_diff = _op_dim(op, "differentiation")
    compliance, has_compliance = _op_dim(op, "compliance")

    evidence: dict[str, Any] = {}

    # Value: operational profit dimension, nudged by realised margin rate.
    margin_score = _margin_score(facts.margin_rate)
    if margin_score is not None:
        value = _blend(profit, margin_score, Decimal("0.7"))
        evidence["value"] = f"profit_dim={profit} blended with margin={facts.margin_rate}"
    else:
        value = _clamp(profit)
        evidence["value"] = f"profit_dim={profit}; margin_rate missing"

    # Utility is driven by demonstrated demand / market heat.
    utility = _clamp(demand)
    evidence["utility"] = "demand_dim" if has_demand else "demand missing -> neutral"

    # Weight & Packability: logistics dimension, refined by actual weight.
    weight_score = _weight_score(facts.weight_kg)
    if has_logistics and weight_score is not None:
        weight_packability = _blend(logistics, weight_score, Decimal("0.6"))
        evidence["weight_packability"] = f"logistics_dim={logistics}, weight_kg={facts.weight_kg}"
    elif weight_score is not None:
        weight_packability = _clamp(weight_score)
        evidence["weight_packability"] = f"weight_kg={facts.weight_kg}; logistics dim missing"
    else:
        weight_packability = _clamp(logistics)
        evidence["weight_packability"] = (
            "logistics_dim" if has_logistics else "logistics/weight missing -> neutral"
        )

    # Durability: compliance dimension + supplier grade.
    supplier_score = SUPPLIER_RATING_SCORE.get(str(facts.supplier_rating or "").upper())
    if supplier_score is None:
        supplier_score = NEUTRAL
        evidence["durability_supplier"] = "supplier grade missing -> neutral"
    else:
        evidence["durability_supplier"] = f"supplier_{facts.supplier_rating}={supplier_score}"
    durability = (
        _blend(compliance, supplier_score, Decimal("0.5"))
        if has_compliance
        else _clamp(supplier_score)
    )

    # Brand Fit: override (rulebook/AI) wins; otherwise a flagged neutral.
    if facts.brand_fit_override is not None:
        brand_fit = _clamp(Decimal(str(facts.brand_fit_override)))
        evidence["brand_fit"] = "override"
    else:
        brand_fit = _clamp(DEFAULT_BRAND_FIT)
        evidence["brand_fit"] = "brand rulebook/AI not configured -> neutral default"

    # Differentiation: own differentiation plus whitespace. The operational
    # ``competition`` dimension is a "favourability / whitespace" score (0-10,
    # higher is better, consistent with every other operational dimension), so
    # it blends in the same direction.
    if has_competition:
        differentiation_dim = _blend(differentiation, competition, Decimal("0.6"))
        evidence["differentiation"] = (
            f"differentiation_dim={differentiation}, whitespace_dim={competition}"
        )
    else:
        differentiation_dim = _clamp(differentiation)
        evidence["differentiation"] = (
            "differentiation_dim" if has_diff else "differentiation/competition missing -> neutral"
        )

    dimensions = {
        "value": value,
        "utility": utility,
        "weight_packability": weight_packability,
        "durability": durability,
        "brand_fit": brand_fit,
        "differentiation": differentiation_dim,
    }
    return dimensions, evidence


# ---------------------------------------------------------------------------
# PHASE 6 — strict mapper: no silent NEUTRAL defaults
# ---------------------------------------------------------------------------

class DataInsufficientError(Exception):
    """Raised when a dimension has no real data source and the strict mapper
    refuses to fabricate a neutral score.

    The caller (the V3 selection pipeline) should have already called
    ``data_integrity_gate.check_integrity`` before invoking
    :func:`map_dimensions_strict`; this error is the last line of defence
    against silent NEUTRAL fabrication.
    """

    def __init__(self, missing: list[str], message: str | None = None) -> None:
        self.missing = missing
        super().__init__(message or f"insufficient data for strict scoring: {missing}")


def _op_dim_strict(operational: dict[str, Any], key: str) -> Decimal:
    """Return score 0-10 for an operational dimension, raising if absent.

    Unlike :func:`_op_dim`, this variant does NOT return ``NEUTRAL`` for a
    missing key — it raises :class:`DataInsufficientError` instead, so the
    caller knows the data gap explicitly.
    """
    raw = operational.get(key)
    if raw is None or raw == "":
        raise DataInsufficientError([key])
    return Decimal(str(raw))


def map_dimensions_strict(facts: ScoreFacts) -> tuple[dict[str, Decimal], dict[str, Any]]:
    """Map :class:`ScoreFacts` to the six V3.0 dimensions WITHOUT neutral defaults.

    This is the PHASE 6 replacement for :func:`map_dimensions`. Instead of
    silently filling in ``NEUTRAL=5.0`` for missing data, it raises
    :class:`DataInsufficientError` when a dimension has no real source.

    The caller must call ``data_integrity_gate.check_integrity`` first and
    only invoke this function when the gate passes. When the gate passes,
    most inputs have real data; the few remaining gaps (e.g. brand_fit
    without an AI override) are surfaced explicitly.

    Returns ``(dimensions, evidence)`` where every dimension is backed by
    real data, not a fabricated neutral.
    """
    op = facts.operational
    evidence: dict[str, Any] = {}

    # --- Value: operational profit + margin rate ----------------------------
    profit = _op_dim_strict(op, "profit")
    margin_score = _margin_score(facts.margin_rate)
    if margin_score is not None:
        value = _blend(profit, margin_score, Decimal("0.7"))
        evidence["value"] = f"profit_dim={profit} blended with margin={facts.margin_rate}"
    else:
        # margin_rate missing: use profit only, no neutral padding.
        value = _clamp(profit)
        evidence["value"] = f"profit_dim={profit}; margin_rate missing"

    # --- Utility: demand dimension ------------------------------------------
    demand = _op_dim_strict(op, "demand")
    utility = _clamp(demand)
    evidence["utility"] = f"demand_dim={demand}"

    # --- Weight & Packability: logistics + weight ---------------------------
    logistics = _op_dim_strict(op, "logistics")
    weight_score = _weight_score(facts.weight_kg)
    if weight_score is not None:
        weight_packability = _blend(logistics, weight_score, Decimal("0.6"))
        evidence["weight_packability"] = (
            f"logistics_dim={logistics}, weight_kg={facts.weight_kg}"
        )
    else:
        # weight_kg missing: use logistics only, no neutral padding.
        weight_packability = _clamp(logistics)
        evidence["weight_packability"] = (
            f"logistics_dim={logistics}; weight_kg missing"
        )

    # --- Durability: compliance + supplier grade ----------------------------
    compliance = _op_dim_strict(op, "compliance")
    supplier_score = SUPPLIER_RATING_SCORE.get(str(facts.supplier_rating or "").upper())
    if supplier_score is None:
        # supplier_rating missing: use compliance only, no neutral padding.
        durability = _clamp(compliance)
        evidence["durability_supplier"] = "supplier grade missing -> compliance only"
    else:
        evidence["durability_supplier"] = f"supplier_{facts.supplier_rating}={supplier_score}"
        durability = _blend(compliance, supplier_score, Decimal("0.5"))

    # --- Brand Fit: override only, no DEFAULT_BRAND_FIT fallback ------------
    if facts.brand_fit_override is not None:
        brand_fit = _clamp(Decimal(str(facts.brand_fit_override)))
        evidence["brand_fit"] = "override"
    else:
        # No AI/rulebook brand fit: this is a real gap, surface it.
        raise DataInsufficientError(
            ["brand_fit"],
            "brand_fit_override missing — no AI/rulebook brand fit available",
        )

    # --- Differentiation: own differentiation + whitespace -------------------
    differentiation_raw = _op_dim_strict(op, "differentiation")
    competition = _op_dim_strict(op, "competition")
    differentiation_dim = _blend(differentiation_raw, competition, Decimal("0.6"))
    evidence["differentiation"] = (
        f"differentiation_dim={differentiation_raw}, whitespace_dim={competition}"
    )

    dimensions = {
        "value": value,
        "utility": utility,
        "weight_packability": weight_packability,
        "durability": durability,
        "brand_fit": brand_fit,
        "differentiation": differentiation_dim,
    }
    return dimensions, evidence
