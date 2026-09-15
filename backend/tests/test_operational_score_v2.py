"""Tests for the V2 11-dimension operational score config + coverage (P2-c)."""

from decimal import Decimal

from app.services.operational_score_v2 import (
    TOTAL_WEIGHT,
    V2_DIMENSIONS,
    coverage_report,
)


def test_eleven_dimensions_and_unit_weights():
    assert len(V2_DIMENSIONS) == 11
    assert TOTAL_WEIGHT == Decimal("1.00")
    targets = {
        "value",
        "utility",
        "weight_packability",
        "durability",
        "differentiation",
        "veto_gate",
    }
    for dim in V2_DIMENSIONS:
        assert dim.feeds_nuotao in targets


def test_empty_coverage():
    report = coverage_report(set())
    assert report["covered"] == []
    assert len(report["missing"]) == 11
    assert report["coverage_ratio"] == Decimal("0.00")


def test_full_coverage():
    all_m21 = {
        "profit",
        "logistics",
        "demand",
        "competition",
        "differentiation",
        "compliance",
    }
    report = coverage_report(all_m21, supplier_present=True)
    assert len(report["covered"]) == 11
    assert report["missing"] == []
    assert report["coverage_ratio"] == Decimal("1.00")


def test_partial_coverage():
    report = coverage_report({"profit", "logistics"})
    assert set(report["covered"]) == {"full_cost_margin", "logistics_support"}
    # 0.15 + 0.05 = 0.20 of 1.00.
    assert report["coverage_ratio"] == Decimal("0.20")
    assert "supplier_qualification" in report["missing"]


def test_demand_feeds_two_subdimensions():
    report = coverage_report({"demand"})
    assert set(report["covered"]) == {"sales_validation", "market_heat"}
