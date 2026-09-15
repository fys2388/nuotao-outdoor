"""Unit tests for V3.0 dimension mapping, veto evaluation and funnel stage."""

from decimal import Decimal

import pytest

from app.services.nuotao_score_mapper import (
    DEFAULT_BRAND_FIT,
    NEUTRAL,
    ScoreFacts,
    map_dimensions,
)
from app.services.nuotao_veto import FAIL, PENDING, PASS, decide_funnel_stage, evaluate_vetoes


def _healthy_facts(**overrides):
    facts = ScoreFacts(
        operational={
            "profit": 8, "logistics": 8, "demand": 8,
            "competition": 9, "differentiation": 8, "compliance": 8,
        },
        margin_rate=Decimal("0.50"),
        shipping_ratio=Decimal("0.10"),
        weight_kg=Decimal("0.5"),
        supplier_rating="B",
        category="camping-light",
        reference_price_usd=Decimal("19.9"),
    )
    for key, value in overrides.items():
        setattr(facts, key, value)
    return facts


def test_mapping_uses_all_sources_and_defaults_brand_fit():
    dims, evidence = map_dimensions(_healthy_facts())
    assert set(dims) == {
        "value", "utility", "weight_packability",
        "durability", "brand_fit", "differentiation",
    }
    assert all(Decimal("0") <= v <= Decimal("10") for v in dims.values())
    assert dims["brand_fit"] == DEFAULT_BRAND_FIT
    assert "neutral" in evidence["brand_fit"]
    # Strong margin should keep Value at/above the operational profit dimension.
    assert dims["value"] >= Decimal("8.0")
    # Low competition (4/10) lifts differentiation above raw 8.
    assert dims["differentiation"] > Decimal("8.0")


def test_mapping_brand_fit_override_wins():
    dims, _ = map_dimensions(_healthy_facts(brand_fit_override=Decimal("9")))
    assert dims["brand_fit"] == Decimal("9.0")


def test_mapping_missing_inputs_are_neutral_and_flagged():
    dims, evidence = map_dimensions(ScoreFacts())
    assert dims["value"] == NEUTRAL
    assert dims["utility"] == NEUTRAL
    assert dims["weight_packability"] == NEUTRAL
    assert dims["durability"] == NEUTRAL
    assert dims["differentiation"] == NEUTRAL
    assert dims["brand_fit"] == DEFAULT_BRAND_FIT
    assert "missing" in evidence["value"]


def test_supplier_d_drives_durability_down_without_compliance():
    dims, _ = map_dimensions(ScoreFacts(supplier_rating="D"))
    assert dims["durability"] == Decimal("3.0")


def test_veto_healthy_product_has_no_hard_fail():
    dims, _ = map_dimensions(_healthy_facts())
    result = evaluate_vetoes(_healthy_facts(), dims)
    assert result["vetoed"] is False
    assert result["failed"] == []
    status = {f.rule_id: f.status for f in result["findings"]}
    # AI / not-configured / missing-data rules stay pending, never auto-pass.
    assert status["V1"] == PENDING and status["V2"] == PENDING and status["V3"] == PENDING
    assert status["V4"] == PENDING and status["V5"] == PENDING and status["V12"] == PENDING
    # Deterministically clear rules pass.
    for rule in ("V6", "V7", "V8", "V9", "V10", "V11"):
        assert status[rule] == PASS


@pytest.mark.parametrize(
    "field,value,expected_rule",
    [
        ("margin_rate", Decimal("0.10"), "V10"),
        ("shipping_ratio", Decimal("0.55"), "V9"),
        ("supplier_rating", "D", "V11"),
        ("reference_price_usd", Decimal("3.0"), "V6"),
    ],
)
def test_deterministic_commercial_vetoes(field, value, expected_rule):
    facts = _healthy_facts(**{field: value})
    dims, _ = map_dimensions(facts)
    result = evaluate_vetoes(facts, dims)
    assert expected_rule in result["failed"]
    assert result["vetoed"] is True


def test_brand_fit_below_floor_is_v8_fail():
    facts = _healthy_facts(brand_fit_override=Decimal("4"))
    dims, _ = map_dimensions(facts)
    result = evaluate_vetoes(facts, dims)
    assert "V8" in result["failed"]


def test_configured_category_lists_hit_or_pass():
    hit = _healthy_facts(
        category="swimwear",
        banned_categories=("swimwear",),
        off_brand_categories=("swimwear",),
    )
    dims, _ = map_dimensions(hit)
    result = evaluate_vetoes(hit, dims)
    assert {"V4", "V5"}.issubset(set(result["failed"]))

    clear = _healthy_facts(
        banned_categories=("swimwear",), off_brand_categories=("swimwear",)
    )
    dims2, _ = map_dimensions(clear)
    status = {f.rule_id: f.status for f in evaluate_vetoes(clear, dims2)["findings"]}
    assert status["V4"] == PASS and status["V5"] == PASS


def test_explicit_compliance_flags_fail():
    facts = _healthy_facts(compliance_failures=("V2",))
    dims, _ = map_dimensions(facts)
    status = {f.rule_id: f.status for f in evaluate_vetoes(facts, dims)["findings"]}
    assert status["V2"] == FAIL
    assert status["V1"] == PENDING


def test_funnel_stage_decisions():
    assert decide_funnel_stage(
        vetoed=True, grade="core", operational_total=Decimal("90"),
        nuotao_total=Decimal("80"),
    ) == "rejected"
    assert decide_funnel_stage(
        vetoed=False, grade="reject", operational_total=Decimal("90"),
        nuotao_total=Decimal("60"),
    ) == "rejected"
    # Operational score below the deep-candidate bar stays screened.
    assert decide_funnel_stage(
        vetoed=False, grade="core", operational_total=Decimal("65"),
        nuotao_total=Decimal("78"),
    ) == "screened"
    # Cleared gates + strong scores advance to test candidate.
    assert decide_funnel_stage(
        vetoed=False, grade="hero", operational_total=Decimal("85"),
        nuotao_total=Decimal("88"),
    ) == "test_candidate"
    # No operational score yet: Nuotao score alone can advance.
    assert decide_funnel_stage(
        vetoed=False, grade="core", operational_total=None,
        nuotao_total=Decimal("70"),
    ) == "test_candidate"
