"""Pricing policy: the single source of truth for cost-based retail pricing.

Why this module exists
----------------------
``operating_rules.md`` PRICE-002 declares ``售价 = 落地成本 ÷ (1 − 目标毛利率)``
a **hard** rule, but it was never implemented: ``listing_gate`` only checked
"has a price" and "has a cost", never whether the price *covers* the cost. A
root-level ``pricing_policy.py`` existed but **no module in ``backend/`` imported
it**, so it never took effect. The consequence was concrete: product 2230 shipped
at $5.83 against a $6.30 purchase cost - selling at a loss on the storefront
front page, because nothing blocked it.

This module is importable from ``app.services`` and is wired into
``listing_gate.evaluate_gate`` / ``evaluate_gate_from_dict``.

Definitions (PROFIT-001 / PROFIT-002 / PRICE-002)
-------------------------------------------------
    landed_cost   = purchase + domestic shipping + first leg + last mile
                    + packaging + duty
    variable_cost = price * (payment_rate + marketing_rate + after_sales_rate)
                    + payment_fixed
    total_cost    = landed_cost + variable_cost
    net_profit    = price - total_cost
    net_margin    = net_profit / price

All business values come from ``Settings`` (AGENTS.md §1.2 rule 5: no experience
values hardcoded in business logic).
"""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal

from app.core.config import get_settings

logger = logging.getLogger(__name__)

MONEY = Decimal("0.01")


def _dec(value) -> Decimal | None:
    """Coerce a messy money value to a non-negative Decimal, else None."""
    if value is None or value == "":
        return None
    try:
        d = Decimal(str(value).replace(",", "").replace("$", "").replace("¥", "").strip())
    except Exception:
        return None
    return d if d >= 0 else None


def _cfg():
    s = get_settings()
    return {
        "min_net_margin": s.pricing_min_net_margin,
        "payment_rate": s.payment_fee_rate,
        "payment_fixed": s.payment_fee_fixed,
        "marketing_rate": s.pricing_marketing_rate,
        "after_sales_rate": s.pricing_after_sales_rate,
        "last_mile": s.pricing_default_last_mile,
        "first_leg": s.pricing_default_first_leg,
        "packaging": s.pricing_default_packaging,
        "cny_usd": s.pricing_cny_usd_rate,
    }


def to_usd(amount, currency: str = "USD") -> Decimal | None:
    """Convert a purchase amount to USD using the configured CNY rate."""
    v = _dec(amount)
    if v is None:
        return None
    if str(currency).upper() == "CNY":
        return (v * _cfg()["cny_usd"]).quantize(MONEY, rounding=ROUND_HALF_UP)
    return v


def _money_amount(value) -> Decimal | None:
    """Coerce any money-ish input (Decimal/float/int/str) to a Decimal.

    Decimal and float cannot be mixed in arithmetic (``TypeError``), and callers
    legitimately hand us floats - WooCommerce returns strings, the ORM returns
    Decimal, ad-hoc scripts pass floats. Every public entry point funnels money
    through here so a float can never crash the gate.
    """
    if isinstance(value, Decimal):
        return value
    v = _dec(value)
    return v


def estimate_landed_cost(
    purchase_usd,
    *,
    first_leg=None,
    last_mile=None,
    packaging=None,
    domestic_shipping=None,
    duty=None,
) -> Decimal | None:
    """Landed cost with per-item overrides falling back to configured defaults.

    Used when the product has no measured ``ProductCost`` row; measured rows
    should always win (see ``landed_cost_or_estimate``). Returns ``None`` when
    the purchase amount is unusable.
    """
    base = _money_amount(purchase_usd)
    if base is None:
        return None
    c = _cfg()
    parts = [
        base,
        _money_amount(domestic_shipping) or Decimal("0"),
        _money_amount(first_leg) if first_leg is not None else c["first_leg"],
        _money_amount(last_mile) if last_mile is not None else c["last_mile"],
        _money_amount(packaging) if packaging is not None else c["packaging"],
        _money_amount(duty) or Decimal("0"),
    ]
    return sum(parts, Decimal("0"))


def landed_cost_or_estimate(purchase_usd, cost_row=None) -> tuple[Decimal | None, str]:
    """Return ``(landed_cost, basis)``.

    ``basis`` is ``"measured"`` when a valid ``ProductCost`` row supplies
    ``total_landed_cost`` (P2-9 effective-cost semantics: purchase > 0 AND
    landed > 0), else ``"estimated"``.
    """
    if cost_row is not None:
        landed = _money_amount(getattr(cost_row, "total_landed_cost", None))
        purchase = _money_amount(getattr(cost_row, "purchase_cost", None))
        if landed and landed > 0 and purchase and purchase > 0:
            return landed, "measured"
    return estimate_landed_cost(purchase_usd), "estimated"


def total_cost(price, landed_cost) -> Decimal | None:
    p, lc = _money_amount(price), _money_amount(landed_cost)
    if p is None or lc is None:
        return None
    c = _cfg()
    variable = p * (c["payment_rate"] + c["marketing_rate"] + c["after_sales_rate"])
    return lc + variable + c["payment_fixed"]


def net_margin(price, landed_cost) -> Decimal | None:
    """Net margin ratio (PROFIT-002 口径，含营销摊销与售后损耗)."""
    p = _money_amount(price)
    tc = total_cost(price, landed_cost)
    if p is None or p <= 0 or tc is None:
        return None
    return (p - tc) / p


def minimum_price(landed_cost, target_net_margin=None) -> Decimal | None:
    """Lowest price that still yields ``target_net_margin``.

    price * (1 - payment - marketing - after_sales - target) = landed + payment_fixed
    """
    lc = _money_amount(landed_cost)
    if lc is None:
        return None
    c = _cfg()
    target = (target_net_margin if target_net_margin is not None
              else c["min_net_margin"])
    target = _money_amount(target) or Decimal("0")
    denom = Decimal("1") - c["payment_rate"] - c["marketing_rate"] \
        - c["after_sales_rate"] - target
    if denom <= 0:
        raise ValueError(
            "variable cost rate + target margin >= 100%; no price can satisfy it "
            f"(denominator={denom})"
        )
    return (lc + c["payment_fixed"]) / denom


def suggested_retail_price(landed_cost, target_net_margin=None) -> Decimal | None:
    """Price rounded down to a ``.99`` ending (PRICE-004 心理定价)."""
    lc = _money_amount(landed_cost)
    if lc is None or lc <= 0:
        return None
    try:
        p = minimum_price(lc, target_net_margin)
    except ValueError:
        return None
    if p is None:
        return None
    whole = p.to_integral_value(rounding=ROUND_HALF_UP)
    candidate = whole - MONEY
    # .99 rounding must not drop below the floor
    if candidate < p:
        candidate = (whole + 1) - MONEY
    return candidate.quantize(MONEY)


def evaluate_price(
    price,
    purchase_cost,
    *,
    purchase_currency: str = "USD",
    cost_row=None,
    target_net_margin: Decimal | None = None,
) -> dict:
    """Judge one price against the configured margin floor.

    Returns a dict the gate can consume directly::

        {"verdict": "ok"|"negative"|"below_target"|"undeterminable",
         "price": Decimal|None, "purchase_usd": Decimal|None,
         "landed_cost": Decimal|None, "landed_basis": "measured"|"estimated",
         "net_margin": Decimal|None, "min_price": Decimal|None,
         "suggested_price": Decimal|None, "message": str}

    ``verdict`` semantics:
      * ``negative``        price does not even cover landed cost - never sellable
      * ``below_target``    covers cost but misses the net-margin floor
      * ``ok``              meets the floor
      * ``undeterminable``  no price or no cost data (the gate reports
                            missing_price / missing_cost separately)
    """
    c = _cfg()
    target = target_net_margin if target_net_margin is not None else c["min_net_margin"]
    price_d = _dec(price)
    purchase_d = to_usd(purchase_cost, purchase_currency)

    if price_d is None or price_d <= 0 or purchase_d is None or purchase_d <= 0:
        return {
            "verdict": "undeterminable", "price": price_d, "purchase_usd": purchase_d,
            "landed_cost": None, "landed_basis": None, "net_margin": None,
            "min_price": None, "suggested_price": None,
            "message": "价格或成本数据缺失，无法核算毛利",
        }

    landed, basis = landed_cost_or_estimate(purchase_d, cost_row)
    margin = net_margin(price_d, landed)
    min_price = minimum_price(landed, target)
    suggested = suggested_retail_price(landed, target)

    if price_d < landed:
        verdict = "negative"
        message = (
            f"售价 ${price_d} 低于落地成本 ${landed}（{basis}），每单亏损 "
            f"${(landed - price_d).quantize(MONEY)}，禁止上架"
        )
    elif margin is None or margin < target:
        verdict = "below_target"
        pct = f"{(margin * 100).quantize(Decimal('0.1'))}%" if margin is not None else "N/A"
        message = (
            f"净利率 {pct} 低于目标 {target * 100:.0f}%，"
            f"达标最低价 ${min_price.quantize(MONEY)}"
        )
    else:
        verdict = "ok"
        message = f"净利率 {(margin * 100).quantize(Decimal('0.1'))}% 达标（≥{target * 100:.0f}%）"

    return {
        "verdict": verdict, "price": price_d, "purchase_usd": purchase_d,
        "landed_cost": landed, "landed_basis": basis, "net_margin": margin,
        "min_price": min_price, "suggested_price": suggested, "message": message,
    }
