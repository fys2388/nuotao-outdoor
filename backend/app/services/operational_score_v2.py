"""V2.0 11-dimension operational score — reviewed configuration + coverage.

V3.0 keeps the finer internal operational score alongside the brand-facing
Nuotao Score. The authoritative 11 dimensions and internal weights (summing to
1.00) come from docs/sourcing_report_template_v3.0.md §5; V3.0 §5 maps each
sub-dimension to one of the six brand-facing Nuotao dimensions.

This module is pure and side-effect free. It does NOT change the existing
6-dimension M2.1 total; it exposes the canonical V2 structure, reports which
operational sub-dimensions currently have a real data source, and shows where
the data gaps are. A future full 11-dimension total only needs the missing
dimension scores to be collected — the weights already live here.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

Source = Literal["deterministic", "market", "ai", "supplier"]


@dataclass(frozen=True)
class OperationalDimension:
    key: str
    label_cn: str
    weight: Decimal            # V2 internal weight (sums to 1.00)
    source: Source
    feeds_nuotao: str          # Nuotao 6-dim key it contributes to (or veto gate)
    supplied_by_m21: str | None  # existing M2.1 dimension feeding it (or None)


# Canonical 11 dimensions, order and weights per sourcing_report_template_v3.0
# §5 (weights total 1.00).
V2_DIMENSIONS: tuple[OperationalDimension, ...] = (
    OperationalDimension("supplier_qualification", "供应商资质", Decimal("0.15"), "supplier", "durability", None),
    OperationalDimension("sales_validation", "销量验证", Decimal("0.10"), "market", "value", "demand"),
    OperationalDimension("full_cost_margin", "全成本利润率", Decimal("0.15"), "deterministic", "value", "profit"),
    OperationalDimension("product_quality", "产品质量", Decimal("0.10"), "ai", "durability", "compliance"),
    OperationalDimension("logistics_support", "物流支持", Decimal("0.05"), "deterministic", "weight_packability", "logistics"),
    OperationalDimension("differentiation_space", "差异化空间", Decimal("0.05"), "ai", "utility", "differentiation"),
    OperationalDimension("market_heat", "市场热度", Decimal("0.15"), "market", "utility", "demand"),
    OperationalDimension("amazon_competition", "亚马逊竞争度", Decimal("0.10"), "market", "differentiation", "competition"),
    OperationalDimension("seasonality", "季节性适配", Decimal("0.05"), "market", "differentiation", "differentiation"),
    OperationalDimension("ai_visual_difficulty", "AI 生图难度", Decimal("0.05"), "ai", "differentiation", "differentiation"),
    OperationalDimension("compliance_ip_risk", "合规与侵权风险", Decimal("0.05"), "ai", "veto_gate", "compliance"),
)

TOTAL_WEIGHT = sum((d.weight for d in V2_DIMENSIONS), Decimal("0"))
assert TOTAL_WEIGHT == Decimal("1.00"), "V2 11-dimension weights must sum to 1.00"


def coverage_report(
    present_m21: set[str],
    *,
    supplier_present: bool = False,
) -> dict:
    """Report which V2 sub-dimensions currently have a real data source.

    ``present_m21`` names the M2.1 dimensions backed by real (non-neutral) data
    for this product; ``supplier_present`` indicates a known supplier grade.
    The ratio is the weight of covered dimensions over the full 1.00.
    """
    covered: list[str] = []
    missing: list[str] = []
    covered_weight = Decimal("0")
    for dim in V2_DIMENSIONS:
        if dim.key == "supplier_qualification":
            is_covered = supplier_present
        else:
            is_covered = dim.supplied_by_m21 in present_m21
        if is_covered:
            covered.append(dim.key)
            covered_weight += dim.weight
        else:
            missing.append(dim.key)
    ratio = (covered_weight / TOTAL_WEIGHT).quantize(Decimal("0.01"))
    return {
        "total_dimensions": len(V2_DIMENSIONS),
        "covered": covered,
        "missing": missing,
        "covered_weight": covered_weight,
        "coverage_ratio": ratio,
    }
