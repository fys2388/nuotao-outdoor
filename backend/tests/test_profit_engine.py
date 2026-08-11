"""Tests for the profit engine (contribution margin, all Decimal)."""

from decimal import Decimal

from app.services.profit_engine import (
    ProfitInput,
    calculate_contribution_margin,
)


def test_profit_engine_calculates_margin() -> None:
    """Contribution margin and rate follow operating rule PROFIT-001."""
    result = calculate_contribution_margin(
        ProfitInput(
            revenue=Decimal("100.00"),
            product_cost=Decimal("40.00"),
            shipping_cost=Decimal("10.00"),
            payment_fee=Decimal("3.20"),
            discount=Decimal("5.00"),
            refund=Decimal("0.00"),
            advertising_cost=Decimal("5.00"),
        )
    )
    assert result.revenue == Decimal("100.00")
    assert result.total_cost == Decimal("58.20")
    assert result.contribution_margin == Decimal("41.80")
    assert result.contribution_margin_rate == Decimal("0.418")
    assert result.as_snapshot() == {
        "revenue": "100.00",
        "total_cost": "58.20",
        "contribution_margin": "41.80",
        "contribution_margin_rate": "0.418",
    }


def test_profit_engine_zero_revenue_has_zero_rate() -> None:
    """A zero-revenue order must not divide by zero."""
    result = calculate_contribution_margin(
        ProfitInput(revenue=Decimal("0.00"), product_cost=Decimal("5.00"))
    )
    assert result.revenue == Decimal("0.00")
    assert result.total_cost == Decimal("5.00")
    assert result.contribution_margin == Decimal("-5.00")
    assert result.contribution_margin_rate == Decimal("0.00")


def test_profit_engine_refund_reduces_margin() -> None:
    """Refunds are part of total cost and lower the contribution margin."""
    result = calculate_contribution_margin(
        ProfitInput(
            revenue=Decimal("50.00"),
            product_cost=Decimal("20.00"),
            refund=Decimal("10.00"),
        )
    )
    assert result.total_cost == Decimal("30.00")
    assert result.contribution_margin == Decimal("20.00")
