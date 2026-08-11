"""Profit engine: contribution margin calculation (all amounts in Decimal).

Follows operating rules PROFIT-001/002/005:
- total_cost = product_cost + shipping_cost + payment_fee + advertising_cost + refund
- contribution_margin = revenue - total_cost
- contribution_margin_rate = contribution_margin / revenue (0 when revenue is 0)
"""

from dataclasses import dataclass
from decimal import Decimal

ZERO = Decimal("0")


@dataclass(frozen=True)
class ProfitInput:
    """Inputs for a contribution margin calculation."""

    revenue: Decimal
    product_cost: Decimal = ZERO
    shipping_cost: Decimal = ZERO
    payment_fee: Decimal = ZERO
    discount: Decimal = ZERO
    refund: Decimal = ZERO
    advertising_cost: Decimal = ZERO


@dataclass(frozen=True)
class ProfitResult:
    """Outputs of a contribution margin calculation."""

    revenue: Decimal
    total_cost: Decimal
    contribution_margin: Decimal
    contribution_margin_rate: Decimal

    def as_snapshot(self) -> dict:
        """Serialize to a JSON-safe snapshot for order storage."""
        return {
            "revenue": str(self.revenue),
            "total_cost": str(self.total_cost),
            "contribution_margin": str(self.contribution_margin),
            "contribution_margin_rate": str(self.contribution_margin_rate),
        }


def calculate_contribution_margin(inputs: ProfitInput) -> ProfitResult:
    """Compute contribution margin from the given inputs.

    Note: ``discount`` is already reflected in ``revenue`` (the amount the
    customer actually paid); it is documented for audit purposes only.
    """
    total_cost = (
        inputs.product_cost
        + inputs.shipping_cost
        + inputs.payment_fee
        + inputs.advertising_cost
        + inputs.refund
    )
    contribution_margin = inputs.revenue - total_cost
    rate = (
        contribution_margin / inputs.revenue
        if inputs.revenue != ZERO
        else ZERO
    )
    return ProfitResult(
        revenue=inputs.revenue,
        total_cost=total_cost,
        contribution_margin=contribution_margin,
        contribution_margin_rate=rate,
    )
