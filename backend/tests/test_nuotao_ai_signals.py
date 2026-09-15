"""Tests for AI-signal normalization and AI-driven V3 veto closure (P2-a)."""

from decimal import Decimal

import pytest

from app.services.nuotao_ai_signals import UNCERTAIN, normalize_ai_assessment
from app.services.nuotao_score_mapper import ScoreFacts, map_dimensions
from app.services.nuotao_veto import FAIL, PASS, PENDING, evaluate_vetoes


def _empty_dims() -> dict:
    dims, _ = map_dimensions(ScoreFacts())
    return dims


# ---------------- normalization ----------------

def test_normalize_full_block():
    signals = normalize_ai_assessment(
        {
            "brand_fit": 8.4,
            "veto_signals": {
                "V1": {"verdict": "pass", "reason": "无商标冲突"},
                "V2": {"verdict": "fail", "reason": "缺 CE"},
                "V5": {"verdict": "uncertain", "reason": ""},
                # non-AI rule must be dropped
                "V9": {"verdict": "fail", "reason": "x"},
            },
            "why_we_recommend": ["a", "b"],
        }
    )
    assert signals.brand_fit == Decimal("8.4")
    assert signals.verdict_of("V1").verdict == PASS
    assert signals.verdict_of("V2").verdict == FAIL
    assert signals.verdict_of("V5").verdict == UNCERTAIN
    assert signals.verdict_of("V9") is None
    assert signals.why_we_recommend == ("a", "b")
    assert signals.has_any is True


@pytest.mark.parametrize("bad", [None, [], "x", 42])
def test_normalize_non_dict_is_empty(bad):
    signals = normalize_ai_assessment(bad)
    assert signals.veto_signals == {}
    assert signals.brand_fit is None
    assert signals.has_any is False


def test_normalize_shorthand_and_bad_verdict():
    signals = normalize_ai_assessment(
        {"veto_signals": {"V1": "fail", "V2": "maybe", "V3": {"verdict": "PASS"}}}
    )
    assert signals.verdict_of("V1").verdict == FAIL
    assert signals.verdict_of("V2").verdict == UNCERTAIN
    assert signals.verdict_of("V3").verdict == PASS


@pytest.mark.parametrize(
    "raw,expected",
    [("12", Decimal("10.0")), ("-3", Decimal("0.0")), ("abc", None), (None, None)],
)
def test_normalize_brand_fit_clamped(raw, expected):
    signals = normalize_ai_assessment({"brand_fit": raw})
    assert signals.brand_fit == expected


# ---------------- veto closure ----------------

def test_without_ai_compliance_rules_stay_pending():
    veto = evaluate_vetoes(ScoreFacts(), _empty_dims())
    for rule in ("V1", "V2", "V3", "V5"):
        finding = next(f for f in veto["findings"] if f.rule_id == rule)
        assert finding.status == PENDING


def test_ai_fail_hard_vetoes():
    signals = normalize_ai_assessment(
        {"veto_signals": {"V1": {"verdict": "fail", "reason": "商标近似"}}}
    )
    veto = evaluate_vetoes(ScoreFacts(), _empty_dims(), signals)
    v1 = next(f for f in veto["findings"] if f.rule_id == "V1")
    assert v1.status == FAIL
    assert "商标近似" in v1.detail
    assert veto["vetoed"] is True
    assert "V1" in veto["failed"]


def test_ai_pass_closes_pending():
    signals = normalize_ai_assessment(
        {
            "veto_signals": {
                "V1": "pass",
                "V2": "pass",
                "V3": "pass",
                "V5": "pass",
            }
        }
    )
    veto = evaluate_vetoes(ScoreFacts(), _empty_dims(), signals)
    for rule in ("V1", "V2", "V3", "V5"):
        finding = next(f for f in veto["findings"] if f.rule_id == rule)
        assert finding.status == PASS
    assert not set(veto["pending"]) & {"V1", "V2", "V3", "V5"}


def test_deterministic_failure_beats_ai_pass():
    facts = ScoreFacts(compliance_failures=("V1",))
    signals = normalize_ai_assessment({"veto_signals": {"V1": "pass"}})
    veto = evaluate_vetoes(facts, _empty_dims(), signals)
    v1 = next(f for f in veto["findings"] if f.rule_id == "V1")
    assert v1.status == FAIL


def test_ai_brand_fit_override_flows_to_dimension():
    signals = normalize_ai_assessment({"brand_fit": 9})
    facts = ScoreFacts(brand_fit_override=signals.brand_fit)
    dims, evidence = map_dimensions(facts)
    assert dims["brand_fit"] == Decimal("9.0")
    assert evidence["brand_fit"] == "override"


def test_output_schema_v3_block_optional_and_validated():
    from app.schemas.product_analyst import ProductAnalysisOutput

    base = {
        "decision": "test",
        "confidence": "0.7",
        "market_reasoning": "ok",
        "pricing": {},
        "test_plan": {},
    }
    # Backward compatible: an older prompt/model omits the block entirely.
    legacy = ProductAnalysisOutput.model_validate(base)
    assert legacy.nuotao_assessment is None

    full = ProductAnalysisOutput.model_validate(
        {
            **base,
            "nuotao_assessment": {
                "brand_fit": 8,
                # V9 is not an AI-owned rule and must be dropped.
                "veto_signals": {
                    "V1": {"verdict": "pass", "reason": "clear"},
                    "V9": {"verdict": "fail"},
                },
                "why_we_recommend": ["r1", "r2", "r3", "r4", "r5", "r6"],
            },
        }
    )
    assessment = full.nuotao_assessment
    assert assessment.brand_fit == Decimal("8")
    assert set(assessment.veto_signals) == {"V1"}
    assert len(assessment.why_we_recommend) == 5  # capped at 5
