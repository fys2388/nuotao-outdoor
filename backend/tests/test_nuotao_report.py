"""Tests for the pure V3.0 sourcing report builder (P2-d)."""

from app.services.nuotao_report import ReportData, build_selection_report
from app.services.nuotao_score_v3 import VETO_ORDER


def _findings(fail: str | None = None) -> list[dict]:
    return [
        {
            "rule_id": rule_id,
            "status": "fail" if rule_id == fail else "pending",
            "detail": "x" if rule_id == fail else "pending",
        }
        for rule_id in VETO_ORDER
    ]


def test_empty_report_is_honest_about_gaps():
    report = build_selection_report(ReportData(product={"sku": "NTO-X"}))
    assert report["summary"]["grade"] is None
    assert report["summary"]["grade_label"] == "未评估"
    assert report["summary"]["recommendation"] == "hold"
    # All 12 vetoes grouped, every one pending when no evaluation exists.
    total = sum(len(rows) for rows in report["vetoes"].values())
    assert total == 12
    assert all(row["status"] == "pending" for rows in report["vetoes"].values() for row in rows)
    assert report["data_completeness"]["missing"]
    assert report["human_review"]["status"] == "pending"


def test_hard_veto_forces_reject_even_with_high_score():
    nuotao = {
        "value_score": 9,
        "utility_score": 9,
        "weight_packability_score": 8,
        "durability_score": 8,
        "brand_fit_score": 8,
        "differentiation_score": 8,
        "total": 84.5,
        "grade": "core",
        "reject_reasons": _findings(fail="V1"),
        "funnel_stage": "rejected",
    }
    report = build_selection_report(ReportData(nuotao=nuotao))
    assert report["summary"]["vetoed"] is True
    assert report["summary"]["failed"] == ["V1"]
    assert report["summary"]["recommendation"] == "reject"
    # Six dimensions with weighted contribution.
    dims = report["nuotao_dimensions"]
    assert len(dims) == 6
    value_row = next(row for row in dims if row["key"] == "value")
    assert value_row["weighted"] == round(9 * 0.25 * 10, 2)


def test_test_candidate_recommendation_and_plan():
    nuotao = {
        "value_score": 7,
        "utility_score": 7,
        "weight_packability_score": 7,
        "durability_score": 7,
        "brand_fit_score": 7,
        "differentiation_score": 7,
        "total": 70,
        "grade": "long_tail",
        "reject_reasons": _findings(),
        "funnel_stage": "test_candidate",
    }
    analyst = {"confidence": 0.6, "test_plan": {"quantity": 50}, "market_reasoning": "ok"}
    report = build_selection_report(ReportData(nuotao=nuotao, analyst=analyst))
    assert report["summary"]["recommendation"] == "test"
    assert report["test_plan"] == {"quantity": 50}
    assert report["summary"]["one_liner"] == "ok"


def test_operational_view_has_eleven_rows():
    operational = {
        "profit": 8,
        "logistics": 7,
        "demand": 6,
        "competition": 5,
        "differentiation": 6,
        "compliance": 7,
        "total": 66,
    }
    supplier = {"rating": "A", "score": 9}
    report = build_selection_report(
        ReportData(nuotao={"reject_reasons": _findings()}, operational=operational, supplier=supplier)
    )
    rows = report["operational_v2"]["dimensions"]
    assert len(rows) == 11
    supplier_row = next(row for row in rows if row["key"] == "supplier_qualification")
    assert supplier_row["score"] == 9
