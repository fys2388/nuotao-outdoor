"""Tests for the customer-facing public Nuotao badge (P3-c)."""

from decimal import Decimal

from app.services.nuotao_report import build_public_badge


def _dims():
    return {
        "value": Decimal("8"),
        "utility": Decimal("7.5"),
        "weight_packability": Decimal("8"),
        "durability": Decimal("7"),
        "brand_fit": Decimal("8"),
        "differentiation": Decimal("7"),
    }


def test_core_and_above_display_badge():
    badge = build_public_badge(
        sku="NTO-HERO-1",
        total=Decimal("78.4"),
        grade="core",
        dimensions=_dims(),
        scored_at="2026-09-15T00:00:00",
        model_version="nuotao-score-v3.0",
    )
    assert badge["display"] is True
    assert badge["sku"] == "NTO-HERO-1"
    assert badge["nuotao_total"] == 78.4
    assert set(badge.keys()) == {
        "display", "sku", "grade", "grade_label", "nuotao_total",
        "dimensions", "scored_at", "model_version",
    }


def test_below_core_hidden():
    badge = build_public_badge(
        sku="NTO-WEAK", total=Decimal("74.9"), grade="long_tail",
        dimensions=_dims(), scored_at=None, model_version="v",
    )
    assert badge == {"display": False, "reason": "below_core"}


def test_no_score_hidden():
    badge = build_public_badge(
        sku="NTO-NONE", total=None, grade=None, dimensions=None,
        scored_at=None, model_version=None,
    )
    assert badge["display"] is False
    assert badge["reason"] == "no_score"
