"""Selection scorecard service — configurable weights + computation.

Implements the V2.0 11-dimension operational scorecard as a pure,
configurable module (AGENTS.md §1.2 rule 5: business values live in
configuration, never inside formulas).

Weights are loaded from the database when available (strategy_versions),
falling back to the canonical defaults below. The computation is pure
and side-effect free so it can be unit-tested and reused by both the
LangGraph workflow and the legacy selection_manager_service.

Maps to:
- docs/product_selection_logic_v2.0.md §2 (11 dimensions + weights)
- docs/nuotao_product_score_v3.0.md §5 (V2.0 -> V3.0 mapping)
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.strategy_version import StrategyVersion


# ── Canonical defaults (V2.0 §2,勘误后 100%) ─────────────────────────
OPERATIONAL_WEIGHTS: dict[str, Decimal] = {
    "supplier_quality": Decimal("0.15"),  # 供应商资质
    "sales_validation": Decimal("0.10"),  # 销量验证
    "margin_rate": Decimal("0.15"),  # 全成本利润率
    "product_quality": Decimal("0.10"),  # 产品质量
    "logistics_support": Decimal("0.05"),  # 物流支持
    "differentiation": Decimal("0.05"),  # 差异化空间
    "market_heat": Decimal("0.15"),  # 市场热度 (勘误后)
    "amazon_competition": Decimal("0.10"),  # 亚马逊竞争度
    "seasonality": Decimal("0.05"),  # 季节性适配
    "ai_image_difficulty": Decimal("0.05"),  # AI生图难度
    "compliance_risk": Decimal("0.05"),  # 合规与侵权风险
}

DIMENSION_KEYS: tuple[str, ...] = tuple(OPERATIONAL_WEIGHTS.keys())

# Dimension labels (zh) for reports/UI.
DIMENSION_LABELS: dict[str, str] = {
    "supplier_quality": "供应商资质",
    "sales_validation": "销量验证",
    "margin_rate": "全成本利润率",
    "product_quality": "产品质量",
    "logistics_support": "物流支持",
    "differentiation": "差异化空间",
    "market_heat": "市场热度",
    "amazon_competition": "亚马逊竞争度",
    "seasonality": "季节性适配",
    "ai_image_difficulty": "AI生图难度",
    "compliance_risk": "合规与侵权风险",
}

# Decision thresholds (V2.0 §2).
GRADE_THRESHOLDS: dict[str, Decimal] = {
    "A": Decimal("85"),  # 优先上架
    "B": Decimal("70"),  # 可上架
    "C": Decimal("60"),  # 待观察
    "D": Decimal("0"),  # 淘汰
}

_Q = Decimal("0.01")


class ScorecardError(ValueError):
    """Raised when a scorecard computation is invalid."""


async def load_operational_weights(
    session: AsyncSession,
    *,
    workspace_id: str,
    category: str | None = None,
) -> dict[str, Decimal]:
    """Load operational scorecard weights, preferring the DB over defaults.

    If ``category`` is provided, loads category-specific weights from
    ``strategy_versions`` (strategy_type='category_weights_{category}').
    Falls back to the canonical V2.0 defaults. Never raises.
    """
    try:
        # Try category-specific weights first
        if category:
            cat_strategy_type = f"category_weights_{category}"
            row = (
                (
                    await session.execute(
                        select(StrategyVersion)
                        .where(
                            StrategyVersion.workspace_id == workspace_id,
                            StrategyVersion.strategy_type == cat_strategy_type,
                        )
                        .order_by(StrategyVersion.version.desc())
                        .limit(1)
                    )
                )
                .scalars()
                .first()
            )
            if row is not None:
                params = row.new_config if isinstance(row.new_config, dict) else {}
                weights_data = params.get("operational_weights", {})
                if weights_data:
                    weights = {
                        key: Decimal(str(value))
                        for key, value in weights_data.items()
                        if key in OPERATIONAL_WEIGHTS
                    }
                    if weights and abs(
                        sum(weights.values()) - Decimal("1.0")
                    ) < Decimal("0.01"):
                        return weights

        # Fall back to global V2.0 operational weights
        row = (
            (
                await session.execute(
                    select(StrategyVersion)
                    .where(
                        StrategyVersion.workspace_id == workspace_id,
                        StrategyVersion.strategy_type == "v2.0_operational",
                    )
                    .order_by(StrategyVersion.version.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        if row is not None:
            params = row.new_config if isinstance(row.new_config, dict) else {}
            weights_data = params.get("operational_weights", {})
            if weights_data:
                weights = {
                    key: Decimal(str(value))
                    for key, value in weights_data.items()
                    if key in OPERATIONAL_WEIGHTS
                }
                if weights and abs(
                    sum(weights.values()) - Decimal("1.0")
                ) < Decimal("0.01"):
                    return weights
    except Exception:
        pass
    return dict(OPERATIONAL_WEIGHTS)


def compute_operational_score(
    dimensions: dict[str, Any],
    weights: dict[str, Decimal] | None = None,
) -> dict[str, Any]:
    """Compute the weighted V2.0 operational score from 11 dimension scores.

    Args:
        dimensions: Must provide every key in OPERATIONAL_WEIGHTS (0-100 each).
        weights: Optional override; defaults to OPERATIONAL_WEIGHTS.

    Returns:
        dict with 'dimensions' (quantized), 'total' (0-100), 'grade' (A/B/C/D).

    Raises:
        ScorecardError: on missing or out-of-range dimensions.
    """
    # Convert weights to Decimal if they are floats
    weights = {k: (Decimal(str(v)) if isinstance(v, float) else v) for k, v in (weights or dict(OPERATIONAL_WEIGHTS)).items()}

    missing = [key for key in DIMENSION_KEYS if key not in dimensions]
    if missing:
        raise ScorecardError(f"missing scorecard dimensions: {missing}")

    total_weight = sum(weights.values())
    if abs(total_weight - Decimal("1.0")) > Decimal("0.01"):
        raise ScorecardError(
            f"weights must sum to 1.0, got {total_weight}"
        )

    dim_scores: dict[str, Decimal] = {}
    weighted = Decimal("0")
    for key in DIMENSION_KEYS:
        raw = Decimal(str(dimensions[key]))
        if raw < 0 or raw > 100:
            raise ScorecardError(f"dimension {key} out of 0-100 range: {raw}")
        score = raw.quantize(_Q, ROUND_HALF_UP)
        dim_scores[key] = score
        weight = weights.get(key, Decimal("0"))
        weighted += score * weight

    total = weighted.quantize(_Q, ROUND_HALF_UP)
    grade = _grade_of(total)

    return {
        "dimensions": dim_scores,
        "total": total,
        "grade": grade,
        "weights": {key: str(weight) for key, weight in weights.items()},
    }


def _grade_of(total: Decimal) -> str:
    """Map a 0-100 operational score to its A/B/C/D grade."""
    for grade, threshold in GRADE_THRESHOLDS.items():
        if total >= threshold:
            return grade
    return "D"


# ── V2.0 -> V3.0 Nuotao Score mapping (V3.0 §5) ─────────────────────
# Maps 6 Nuotao Score dimensions to V2.0 operational dimensions.
# Brand Fit has no V2.0 equivalent and must come from AI/LLM assessment.
NUOTAO_FROM_OPERATIONAL: dict[str, dict[str, tuple[str, float]]] = {
    "value": {
        "margin_rate": 0.7,
        "sales_validation": 0.3,
    },
    "utility": {
        "market_heat": 0.6,
        "differentiation": 0.4,
    },
    "weight_packability": {
        "logistics_support": 0.8,
        "margin_rate": 0.2,
    },
    "durability": {
        "product_quality": 0.6,
        "supplier_quality": 0.4,
    },
    "differentiation": {
        "amazon_competition": 0.4,
        "ai_image_difficulty": 0.3,
        "seasonality": 0.3,
    },
    # brand_fit: no V2.0 mapping; must be supplied by AI assessment
}


def map_operational_to_nuotao(
    operational: dict[str, Any],
    *,
    brand_fit: float | None = None,
) -> dict[str, float]:
    """Map V2.0 operational dimensions to V3.0 Nuotao Score dimensions.

    ``operational['dimensions']`` must contain the 11 V2.0 scores.
    ``brand_fit`` is required (no V2.0 equivalent) and must be 0-10.

    Returns a dict with all 6 Nuotao Score dimensions (0-10 scale).
    """
    dims = operational.get("dimensions", {})

    if brand_fit is None:
        raise ScorecardError("brand_fit is required (no V2.0 mapping)")

    nuotao: dict[str, float] = {}

    for nuotao_key, mapping in NUOTAO_FROM_OPERATIONAL.items():
        mapped_total = Decimal("0")
        weight_sum = Decimal("0")
        for op_key, weight in mapping.items():
            op_value = dims.get(op_key)
            if op_value is None:
                continue
            # Convert 0-100 operational to 0-10 Nuotao scale
            scaled = Decimal(str(op_value)) / Decimal("10")
            mapped_total += scaled * Decimal(str(weight))
            weight_sum += Decimal(str(weight))

        if weight_sum > 0:
            # Normalize if weights don't sum to 1 (partial data)
            mapped_total = mapped_total / weight_sum
            nuotao[nuotao_key] = round(float(mapped_total), 1)
        else:
            nuotao[nuotao_key] = 5.0  # neutral default

    nuotao["brand_fit"] = round(min(max(float(brand_fit), 0.0), 10.0), 1)
    return nuotao
