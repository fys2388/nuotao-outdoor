"""Nuotao Product Score V3.0 — pure scoring spec and deterministic functions.

Implements the brand-facing six-dimension score and the V1-V12 proactive veto
catalogue defined in ``docs/nuotao_product_score_v3.0.md``.

This module is intentionally side-effect free: no DB, LLM or network access.
P0 delivers the spec (weights, grade boundaries, veto catalogue) and the
deterministic arithmetic; the P1 selection pipeline is responsible for
collecting the inputs, calling :func:`compute_nuotao_score` and persisting the
result. Keeping the math pure makes the whole V3.0 model unit-testable and
prevents hard-coding business judgement into service code (AGENTS.md §1.2.5).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

# Version stamps written onto every persisted score row.
MODEL_VERSION = "nuotao-score-v3.0"
RULE_VERSION = "veto-v3.0"

# §2.1 dimension weights — must sum to 1.
DIMENSION_WEIGHTS: dict[str, Decimal] = {
    "value": Decimal("0.25"),
    "utility": Decimal("0.20"),
    "weight_packability": Decimal("0.15"),
    "durability": Decimal("0.15"),
    "brand_fit": Decimal("0.15"),
    "differentiation": Decimal("0.10"),
}
DIMENSION_KEYS: tuple[str, ...] = tuple(DIMENSION_WEIGHTS.keys())

# Human-readable dimension labels (zh + en) for reports / UI.
DIMENSION_LABELS: dict[str, str] = {
    "value": "Value 性价比",
    "utility": "Utility 实用性",
    "weight_packability": "Weight & Packability 轻量便携",
    "durability": "Durability 耐用性",
    "brand_fit": "Brand Fit 品牌契合",
    "differentiation": "Differentiation 差异化",
}

# §2.3 grade boundaries (inclusive lower bounds).
GRADE_HERO = "hero"
GRADE_CORE = "core"
GRADE_LONG_TAIL = "long_tail"
GRADE_REJECT = "reject"
HERO_MIN = Decimal("85")
CORE_MIN = Decimal("75")
LONG_TAIL_MIN = Decimal("65")

# V8: a Brand Fit dimension score below this is a hard veto regardless of total.
BRAND_FIT_VETO_BELOW = Decimal("5")
# V9 / V10 / V12 commercial thresholds.
SHIPPING_RATIO_MAX = Decimal("0.40")
MARGIN_MIN = Decimal("0.20")
RETURN_RATE_MAX = Decimal("0.15")

_DIM_Q = Decimal("0.1")
_TOTAL_Q = Decimal("0.01")


@dataclass(frozen=True)
class VetoRule:
    """One entry of the V1-V12 proactive rejection catalogue."""

    id: str
    name: str
    category: str  # compliance | brand | commercial
    check_type: str  # deterministic | ai | hybrid
    data_source: str
    rule: str


# §3 proactive rejection catalogue. ``check_type`` says how P1 evaluates it:
# deterministic = computable from structured data, ai = LLM/knowledge assisted,
# hybrid = structured gate plus AI explanation.
VETO_RULES: dict[str, VetoRule] = {
    "V1": VetoRule("V1", "知识产权侵权", "compliance", "ai",
                   "专利/商标检索", "外观专利、商标、品牌图案侵权风险"),
    "V2": VetoRule("V2", "法规合规", "compliance", "ai",
                   "CPSC/CPSIA、REACH、FDA、电池运输规则",
                   "目标市场强制法规/认证无法满足"),
    "V3": VetoRule("V3", "安全风险", "compliance", "hybrid",
                   "产品结构/材质 + 安全知识库",
                   "存在人身安全隐患且无法通过设计规避"),
    "V4": VetoRule("V4", "违禁品", "compliance", "deterministic",
                   "目标市场禁运/禁售品类清单",
                   "属于目标市场禁止进口或销售的品类"),
    "V5": VetoRule("V5", "品牌聚焦破坏", "brand", "hybrid",
                   "品类战略/品牌定位配置",
                   "品类与专业户外装备定位严重不符"),
    "V6": VetoRule("V6", "低价杂货感", "brand", "deterministic",
                   "价格带 + 品类配置",
                   "天然属于低价 impulse buy 品类，拉低品牌认知"),
    "V7": VetoRule("V7", "与现有 Hero 冲突", "brand", "deterministic",
                   "现有 Hero 产品库",
                   "与已确定 Hero 直接同质化、无差异化"),
    "V8": VetoRule("V8", "Brand Fit 过低", "brand", "deterministic",
                   "Nuotao Score 的 brand_fit 维度",
                   "Brand Fit 维度低于 5/10 直接否决"),
    "V9": VetoRule("V9", "物流不可行", "commercial", "deterministic",
                   "全成本模型 shipping_ratio",
                   "运费占售价 > 40% 或属于国际运输禁运品"),
    "V10": VetoRule("V10", "利润不可行", "commercial", "deterministic",
                    "全成本模型利润率",
                    "全成本利润率 < 20% 且无法优化"),
    "V11": VetoRule("V11", "供应商不可行", "commercial", "hybrid",
                    "供应商分级/认证/样品",
                    "无 C 级以上合格供应商或无法提供样品/认证"),
    "V12": VetoRule("V12", "退货风险过高", "commercial", "hybrid",
                    "品类先验退货率 + 评价",
                    "预估退货率 > 15%"),
}
VETO_ORDER: tuple[str, ...] = tuple(f"V{i}" for i in range(1, 13))
COMPLIANCE_VETOES = tuple(r.id for r in VETO_RULES.values() if r.category == "compliance")
BRAND_VETOES = tuple(r.id for r in VETO_RULES.values() if r.category == "brand")
COMMERCIAL_VETOES = tuple(r.id for r in VETO_RULES.values() if r.category == "commercial")


def grade_of(total: Decimal | float | int | str) -> str:
    """Map a 0-100 Nuotao Score total to its V3.0 grade."""
    value = Decimal(str(total))
    if value >= HERO_MIN:
        return GRADE_HERO
    if value >= CORE_MIN:
        return GRADE_CORE
    if value >= LONG_TAIL_MIN:
        return GRADE_LONG_TAIL
    return GRADE_REJECT


def compute_nuotao_score(dimensions: dict[str, Any]) -> dict[str, Any]:
    """Compute the weighted Nuotao Score from six 0-10 dimension scores.

    ``dimensions`` must provide every key in :data:`DIMENSION_KEYS`. Returns the
    per-dimension scores (quantized to 0.1), the weighted total 0-100
    (quantized to 0.01) and the grade. Raises ``ValueError`` on a missing or
    out-of-range dimension.
    """
    missing = [key for key in DIMENSION_KEYS if key not in dimensions]
    if missing:
        raise ValueError(f"missing Nuotao Score dimensions: {missing}")

    dim_scores: dict[str, Decimal] = {}
    weighted = Decimal("0")
    for key in DIMENSION_KEYS:
        raw = Decimal(str(dimensions[key]))
        if raw < 0 or raw > 10:
            raise ValueError(f"dimension {key} out of 0-10 range: {raw}")
        score = raw.quantize(_DIM_Q, ROUND_HALF_UP)
        dim_scores[key] = score
        weighted += score * DIMENSION_WEIGHTS[key]

    total = (weighted * Decimal("10")).quantize(_TOTAL_Q, ROUND_HALF_UP)
    return {
        "dimensions": dim_scores,
        "total": total,
        "grade": grade_of(total),
    }


def brand_fit_veto(brand_fit: Decimal | float | int | str) -> bool:
    """V8: True when the Brand Fit dimension is below the hard floor."""
    return Decimal(str(brand_fit)) < BRAND_FIT_VETO_BELOW
