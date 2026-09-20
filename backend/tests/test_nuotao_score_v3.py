"""Unit tests for the Nuotao Product Score V3.0 pure scoring module."""

from decimal import Decimal

import pytest

from app.services.nuotao_score_v3 import (
    BRAND_FIT_VETO_BELOW,
    COMMERCIAL_VETOES,
    COMPLIANCE_VETOES,
    BRAND_VETOES,
    DIMENSION_KEYS,
    DIMENSION_WEIGHTS,
    GRADE_CORE,
    GRADE_HERO,
    GRADE_LONG_TAIL,
    GRADE_REJECT,
    VETO_ORDER,
    VETO_RULES,
    brand_fit_veto,
    compute_nuotao_score,
    grade_of,
)


def _dims(value=9.0, utility=9.0, weight=9.0, durability=9.0, brand=9.0, diff=9.0):
    return {
        "value": value,
        "utility": utility,
        "weight_packability": weight,
        "durability": durability,
        "brand_fit": brand,
        "differentiation": diff,
    }


def test_weights_sum_to_one_and_cover_six_dimensions():
    assert len(DIMENSION_KEYS) == 6
    assert sum(DIMENSION_WEIGHTS.values()) == Decimal("1.00")


def test_doc_example_scores_90_hero():
    # Worked example in docs/nuotao_product_score_v3.0.md §2.2.
    result = compute_nuotao_score(
        _dims(9.2, 9.0, 9.5, 8.0, 9.5, 8.5)
    )
    assert result["total"] == Decimal("90.00")
    assert result["grade"] == GRADE_HERO
    assert result["dimensions"]["brand_fit"] == Decimal("9.5")


@pytest.mark.parametrize(
    "score,expected",
    [
        (85, GRADE_HERO),
        (100, GRADE_HERO),
        (84.99, GRADE_CORE),
        (75, GRADE_CORE),
        (74.99, GRADE_LONG_TAIL),
        (65, GRADE_LONG_TAIL),
        (64.99, GRADE_REJECT),
        (0, GRADE_REJECT),
    ],
)
def test_grade_boundaries(score, expected):
    assert grade_of(score) == expected


def test_all_same_dimension_matches_that_dimension_times_ten():
    result = compute_nuotao_score(_dims(8, 8, 8, 8, 8, 8))
    assert result["total"] == Decimal("80.00")
    assert result["grade"] == GRADE_CORE


def test_missing_dimension_raises():
    dims = _dims()
    del dims["durability"]
    with pytest.raises(ValueError, match="missing"):
        compute_nuotao_score(dims)


@pytest.mark.parametrize("bad", [-0.1, 10.1, 11])
def test_out_of_range_dimension_raises(bad):
    with pytest.raises(ValueError, match="out of 0-10"):
        compute_nuotao_score(_dims(value=bad))


def test_veto_catalogue_has_v1_to_v12_grouped_by_category():
    assert list(VETO_ORDER) == [f"V{i}" for i in range(1, 13)]
    assert set(VETO_RULES) == set(VETO_ORDER)
    assert COMPLIANCE_VETOES == ("V1", "V2", "V3", "V4")
    assert BRAND_VETOES == ("V5", "V6", "V7", "V8")
    assert COMMERCIAL_VETOES == ("V9", "V10", "V11", "V12")
    for rule in VETO_RULES.values():
        assert rule.check_type in {"deterministic", "ai", "hybrid"}
        assert rule.name and rule.rule


def test_v8_brand_fit_floor():
    assert brand_fit_veto(BRAND_FIT_VETO_BELOW) is False
    assert brand_fit_veto(Decimal("4.9")) is True
    assert brand_fit_veto(9) is False
