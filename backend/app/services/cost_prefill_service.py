"""Auto-prefill landing cost from outer dimensions + industry baseline.

Given a product's outer package dimensions (L/W/H cm), actual weight,
category, and purchase price, compute a full PROFIT-001 compliant cost
breakdown. The result is designed to be passed straight into
``_upsert_product_cost`` (via ProductIntakeRequest) which handles
version-bumping and append-only snapshot writes.

All monetary values are in USD unless noted. Chinese logistics are
converted at CNY_TO_USD_RATE = 0.14 (approximate 2026 exchange).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

CNY_TO_USD_RATE = Decimal("0.14")
USD_BASE_EXCHANGE = Decimal("7.2")


def _volumetric_weight_kg(dimensions: dict[str, Any]) -> Decimal:
    """Calculate volumetric weight from dimensions (L/W/H in cm).

    Formula: (length_cm * width_cm * height_cm) / 5000 = kg
    This is the standard IATA dimensional weight divisor for air freight.

    Args:
        dimensions: Dict with keys 'length', 'width', 'height' (in cm)

    Returns:
        Volumetric weight in kg as Decimal
    """
    length = Decimal(str(dimensions.get("length", 0) or 0))
    width = Decimal(str(dimensions.get("width", 0) or 0))
    height = Decimal(str(dimensions.get("height", 0) or 0))

    if length <= 0 or width <= 0 or height <= 0:
        return Decimal("0")

    volumetric_cm3 = length * width * height
    return (volumetric_cm3 / Decimal("5000")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

# ---------------------------------------------------------------------------
# Industry baseline tables (v1, hard-coded for MVP, replaceable via config)
# ---------------------------------------------------------------------------

# First-leg (国内→头程) shipping per tier (kg) → CNY
FIRST_LEG_TIERS: list[tuple[Decimal, Decimal]] = [
    (Decimal("0.5"), Decimal("30")),
    (Decimal("1.0"), Decimal("45")),
    (Decimal("2.0"), Decimal("70")),
    (Decimal("5.0"), Decimal("120")),
    (Decimal("10"), Decimal("180")),
    (Decimal("999"), Decimal("250")),
]

# Last-leg (US inbound tail) shipping per tier (kg) → USD
LAST_LEG_TIERS: list[tuple[Decimal, Decimal]] = [
    (Decimal("0.5"), Decimal("8")),
    (Decimal("1.0"), Decimal("10")),
    (Decimal("2.0"), Decimal("13")),
    (Decimal("5.0"), Decimal("18")),
    (Decimal("10"), Decimal("28")),
    (Decimal("999"), Decimal("45")),
]

# Domestic shipping (仓库→1688 卖家集货) baseline CNY per tier (kg)
DOMESTIC_TIERS: list[tuple[Decimal, Decimal]] = [
    (Decimal("0.5"), Decimal("3")),
    (Decimal("2.0"), Decimal("5")),
    (Decimal("5.0"), Decimal("8")),
    (Decimal("999"), Decimal("15")),
]

# Tariff rates by category (HS 9506 / 3926 / 9507 commonly used)
TARIFF_RATES: dict[str, Decimal] = {
    "户外用品": Decimal("0.05"),
    "户外配件": Decimal("0.05"),
    "户外照明": Decimal("0.05"),
    "炊具": Decimal("0.04"),
    "收纳": Decimal("0.03"),
    "水具": Decimal("0.04"),
    "服装": Decimal("0.16"),
    "鞋类": Decimal("0.20"),
    "电子": Decimal("0.00"),
    "default": Decimal("0.04"),
}

# Reference selling-price multiplier over landed cost
# (used only for computing payment / marketing / returns as % of selling price)
REF_SELLING_MULTIPLIER = Decimal("3.5")

# PROFIT-001 payment fee: 2.9% + $0.30
PAYMENT_RATE = Decimal("0.029")
PAYMENT_FIXED = Decimal("0.30")

# Marketing amortization rate on selling price
MARKETING_RATE = Decimal("0.15")

# After-sales loss rate on selling price
RETURN_RATE = Decimal("0.03")


def _effective_weight_kg(weight_kg: Decimal | None, dimensions: dict[str, Any] | None) -> Decimal:
    """Effective shipping weight = max(actual, volumetric). Fallback 0.3 kg."""
    actual = weight_kg
    volumetric: Decimal | None = None
    if dimensions:
        try:
            l = Decimal(str(dimensions["length"]))
            w = Decimal(str(dimensions["width"]))
            h = Decimal(str(dimensions["height"]))
            volumetric = l * w * h / Decimal("6000")
        except (KeyError, TypeError, ValueError):
            volumetric = None
    if actual is None and volumetric is None:
        return Decimal("0.3")
    if actual is None:
        return volumetric
    if volumetric is None:
        return actual
    return max(actual, volumetric)


def _tier_lookup(weight: Decimal, tiers: list[tuple[Decimal, Decimal]]) -> Decimal:
    for upper, price in tiers:
        if weight <= upper:
            return price
    return tiers[-1][1]


def _r2(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class CostPrefillResult:
    """Full PROFIT-001 cost breakdown + suggested selling price."""

    purchase_cost: Decimal       # USD
    domestic_shipping: Decimal   # USD
    first_leg_shipping: Decimal  # USD
    last_leg_shipping: Decimal   # USD
    tax_estimate: Decimal        # USD (tariff)
    packaging: Decimal           # USD
    handling: Decimal            # USD
    payment_fee: Decimal         # USD
    marketing_amortization: Decimal  # USD
    after_sales_loss: Decimal    # USD
    total_landed_cost: Decimal   # USD (authoritative per PROFIT-001)
    suggested_selling_price: Decimal  # USD
    contribution_margin: Decimal      # USD
    contribution_margin_rate: Decimal # 0-1
    weight_kg_effective: Decimal
    model_version: str = "cost-prefill-v1"
    rule_version: str = "PROFIT-001"


def prefill_landed_cost(
    *,
    purchase_cost_usd: Decimal,
    weight_kg: Decimal | None = None,
    dimensions_cm: dict[str, Any] | None = None,
    category: str = "户外用品",
    currency: str = "USD",
    packaging: Decimal | None = None,
    handling: Decimal | None = None,
) -> CostPrefillResult:
    """
    Compute the full PROFIT-001 landed cost for a product.

    Rules:
    - purchase_cost_usd: authoritative purchase cost in USD
      (if only CNY is known, convert with USD_BASE_EXCHANGE before calling)
    - weight_kg + dimensions_cm: pick max of actual/volumetric weight
    - all rates look up tiers by effective weight
    - tariff applied to (purchase + domestic + first_leg) subtotal
    - payment / marketing / return computed on suggested_selling_price
    - total_landed_cost = purchase + domestic + first_leg + last_leg
                        + packaging + tax_estimate + handling
    - contribution_margin = suggested_selling_price - total_landed_cost
    """
    eff_weight = _effective_weight_kg(weight_kg, dimensions_cm)

    # CNY tier → USD conversion
    domestic_cny = _tier_lookup(eff_weight, DOMESTIC_TIERS)
    first_leg_cny = _tier_lookup(eff_weight, FIRST_LEG_TIERS)
    domestic_shipping = _r2(domestic_cny * CNY_TO_USD_RATE)
    first_leg_shipping = _r2(first_leg_cny * CNY_TO_USD_RATE)

    last_leg_shipping = _r2(_tier_lookup(eff_weight, LAST_LEG_TIERS))

    # Tariff on inbound landed subtotal
    tariff_rate = TARIFF_RATES.get(category, TARIFF_RATES["default"])
    tariff_base = purchase_cost_usd + domestic_shipping + first_leg_shipping
    tax_estimate = _r2(tariff_base * tariff_rate)

    # Fixed overheads (defaults if not provided)
    packaging_val = packaging if packaging is not None else Decimal("0.50")
    handling_val = handling if handling is not None else Decimal("0.30")

    total_landed = _r2(
        purchase_cost_usd
        + domestic_shipping
        + first_leg_shipping
        + last_leg_shipping
        + packaging_val
        + tax_estimate
        + handling_val
    )

    # Suggested selling price = landed / (1 - 35% target margin)
    # (Price band PRICE-002 主力层 35% 目标毛利)
    target_margin = Decimal("0.35")
    suggested_price = _r2(total_landed / (Decimal("1") - target_margin))

    # Payment / marketing / returns on suggested price
    payment_fee = _r2(suggested_price * PAYMENT_RATE + PAYMENT_FIXED)
    marketing = _r2(suggested_price * MARKETING_RATE)
    returns = _r2(suggested_price * RETURN_RATE)

    # Contribution margin = revenue - total_cost (all cost items)
    total_cost_full = _r2(
        total_landed + payment_fee + marketing + returns
    )
    contribution = _r2(suggested_price - total_cost_full)
    rate = contribution / suggested_price if suggested_price > 0 else Decimal("0")

    return CostPrefillResult(
        purchase_cost=purchase_cost_usd,
        domestic_shipping=domestic_shipping,
        first_leg_shipping=first_leg_shipping,
        last_leg_shipping=last_leg_shipping,
        tax_estimate=tax_estimate,
        packaging=packaging_val,
        handling=handling_val,
        payment_fee=payment_fee,
        marketing_amortization=marketing,
        after_sales_loss=returns,
        total_landed_cost=total_landed,
        suggested_selling_price=suggested_price,
        contribution_margin=contribution,
        contribution_margin_rate=rate,
        weight_kg_effective=eff_weight,
    )
