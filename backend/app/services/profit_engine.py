"""Profit engine: contribution margin calculation (all amounts in Decimal).

Follows operating rules PROFIT-001/002/005:
- total_cost = product_cost + shipping_cost + payment_fee + advertising_cost + refund
- contribution_margin = revenue - total_cost
- contribution_margin_rate = contribution_margin / revenue (0 when revenue is 0)

M1.6 confidence model: an UNKNOWN product cost must never produce a high
confidence profitability conclusion. Statuses are KNOWN / ESTIMATED / UNKNOWN
with confidence HIGH / MEDIUM / LOW respectively.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

ZERO = Decimal("0")


class CostStatus(StrEnum):
    """How complete the product cost data behind a profit number is."""

    KNOWN = "KNOWN"
    ESTIMATED = "ESTIMATED"
    UNKNOWN = "UNKNOWN"


class ProfitConfidence(StrEnum):
    """Confidence of a profitability conclusion."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass(frozen=True)
class ConfidenceResult:
    """Assessed cost completeness for a profit snapshot."""

    cost_status: CostStatus
    profit_confidence: ProfitConfidence
    reasons: list[str]


def assess_cost_confidence(*, matched: int, total: int) -> ConfidenceResult:
    """Assess cost confidence from how many line units have known costs.

    - matched == total (and total > 0): KNOWN / HIGH
    - 0 < matched < total: ESTIMATED / MEDIUM
    - matched == 0: UNKNOWN / LOW
    """
    if total > 0 and matched == total:
        return ConfidenceResult(
            cost_status=CostStatus.KNOWN,
            profit_confidence=ProfitConfidence.HIGH,
            reasons=["product cost matched for all line items"],
        )
    if matched > 0:
        return ConfidenceResult(
            cost_status=CostStatus.ESTIMATED,
            profit_confidence=ProfitConfidence.MEDIUM,
            reasons=[
                f"product cost matched for {matched} of {total} line items",
                "profit is partially estimated",
            ],
        )
    return ConfidenceResult(
        cost_status=CostStatus.UNKNOWN,
        profit_confidence=ProfitConfidence.LOW,
        reasons=[
            "no product cost data matched",
            "profit conclusion withheld (low confidence)",
        ],
    )


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
    rate = contribution_margin / inputs.revenue if inputs.revenue != ZERO else ZERO
    return ProfitResult(
        revenue=inputs.revenue,
        total_cost=total_cost,
        contribution_margin=contribution_margin,
        contribution_margin_rate=rate,
    )
