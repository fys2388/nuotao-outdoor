"""Data integrity gate for V3.0 Nuotao Score evaluation.

Checks whether a product has enough structured data to be scored reliably.
Replaces the silent ``NEUTRAL=5.0`` default that masked missing data: instead
of fabricating a neutral score for every absent field, the gate surfaces the
gap and blocks scoring when critical inputs are absent.

Design rules (AGENTS.md §1.2.5, §2.1):
* No gut-feel business values hidden in flow control — every threshold lives
  in this reviewed, configurable module.
* A missing input yields a flagged dimension, never a fabricated precise score;
  the caller records the evidence flag.
* The gate is deterministic and side-effect free: it inspects ``ScoreFacts``
  and returns a verdict; persistence is the caller's responsibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.services.nuotao_score_mapper import ScoreFacts

# ---------------------------------------------------------------------------
# Integrity gate specification — reviewed, configurable, never hidden.
# ---------------------------------------------------------------------------

# Minimum completeness score (0-100) required to allow scoring to proceed.
# Below this threshold the gate blocks and the product stays in its current
# funnel stage until data is backfilled.
GATE_MIN_SCORE = Decimal("40.0")

# Weight each field group contributes to the overall completeness score.
# Weights must sum to 100.
_FIELD_WEIGHTS: dict[str, Decimal] = {
    # Critical: at least some operational data must exist.
    "operational_dimensions": Decimal("30"),
    # Commercial: needed for V9/V10/V12 veto evaluation.
    "margin_rate": Decimal("10"),
    "shipping_ratio": Decimal("10"),
    "reference_price_usd": Decimal("10"),
    # Physical: needed for V6 impulse threshold and weight dimension.
    "weight_kg": Decimal("10"),
    # Supplier: needed for V11 supplier feasibility veto.
    "supplier_rating": Decimal("10"),
    # Brand: needed for V5/V8 brand-fit veto and brand_fit dimension.
    "brand_fit": Decimal("10"),
    "category": Decimal("5"),
    # Return rate: needed for V12 return-rate veto.
    "return_rate": Decimal("5"),
}

# Version stamp for the integrity check logic.
INTEGRITY_VERSION = "v1"

# Operational dimension keys that count towards "operational_dimensions" weight.
_OP_KEYS: tuple[str, ...] = (
    "profit",
    "logistics",
    "demand",
    "competition",
    "differentiation",
    "compliance",
)


@dataclass(frozen=True)
class GateResult:
    """Outcome of one data-integrity gate check."""

    passed: bool
    status: str  # "complete" | "partial" | "missing"
    score: Decimal  # 0-100 completeness
    missing_fields: list[str]  # field names that are absent
    total_weight: Decimal
    passed_weight: Decimal
    version: str


def _op_dimensions_present(operational: dict[str, Any]) -> tuple[int, list[str]]:
    """Count how many of the six operational dimensions are present."""
    present = [key for key in _OP_KEYS if operational.get(key) not in (None, "")]
    return len(present), present


def check_integrity(facts: ScoreFacts) -> GateResult:
    """Evaluate data completeness against the V3.0 gate specification.

    Returns a :class:`GateResult` with the completeness score and the list of
    missing fields. Does NOT raise; the caller decides whether to block.
    """
    missing: list[str] = []
    passed_weight = Decimal("0")

    # --- Operational dimensions (weight 30) -------------------------------
    op_present_count, op_present_keys = _op_dimensions_present(facts.operational)
    op_weight = _FIELD_WEIGHTS["operational_dimensions"]
    if op_present_count == 0:
        missing.append("operational_dimensions")
    else:
        # Partial credit: each dimension contributes equally.
        fraction = Decimal(op_present_count) / Decimal(len(_OP_KEYS))
        passed_weight += (op_weight * fraction).quantize(Decimal("0.01"))

    # --- Commercial fields -------------------------------------------------
    for field_name in ("margin_rate", "shipping_ratio", "reference_price_usd"):
        value = getattr(facts, field_name, None)
        if value is None:
            missing.append(field_name)
        else:
            passed_weight += _FIELD_WEIGHTS[field_name]

    # --- Physical / weight -------------------------------------------------
    if facts.weight_kg is None:
        missing.append("weight_kg")
    else:
        passed_weight += _FIELD_WEIGHTS["weight_kg"]

    # --- Supplier rating ---------------------------------------------------
    if not facts.supplier_rating:
        missing.append("supplier_rating")
    else:
        passed_weight += _FIELD_WEIGHTS["supplier_rating"]

    # --- Brand fit ---------------------------------------------------------
    if facts.brand_fit_override is None:
        missing.append("brand_fit")
    else:
        passed_weight += _FIELD_WEIGHTS["brand_fit"]

    # --- Category ----------------------------------------------------------
    if not facts.category:
        missing.append("category")
    else:
        passed_weight += _FIELD_WEIGHTS["category"]

    # --- Return rate -------------------------------------------------------
    if facts.return_rate is None:
        missing.append("return_rate")
    else:
        passed_weight += _FIELD_WEIGHTS["return_rate"]

    total_weight = Decimal("100")
    score = (passed_weight / total_weight * total_weight).quantize(Decimal("0.01"))

    # Determine status.
    if score >= Decimal("90"):
        status = "complete"
    elif score >= GATE_MIN_SCORE:
        status = "partial"
    else:
        status = "missing"

    return GateResult(
        passed=score >= GATE_MIN_SCORE,
        status=status,
        score=score,
        missing_fields=missing,
        total_weight=total_weight,
        passed_weight=passed_weight,
        version=INTEGRITY_VERSION,
    )
