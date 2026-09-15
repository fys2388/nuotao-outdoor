"""Build a V3.0 sourcing/selection report from already-collected data — pure.

Mirrors docs/sourcing_report_template_v3.0.md: executive summary, V1-V12 vetoes,
six Nuotao dimensions, the 11-dimension operational view, landed cost, AI market
reasoning, pricing/test proposal and a human-review placeholder. The function
never touches the database or an LLM — the service layer collects rows and
passes plain dicts; missing inputs are rendered as explicit "待补" rather than
fabricated, so a report is always honest about data completeness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.services.nuotao_score_v3 import (
    DIMENSION_KEYS,
    DIMENSION_LABELS,
    DIMENSION_WEIGHTS,
    VETO_RULES,
    COMPLIANCE_VETOES,
    BRAND_VETOES,
    COMMERCIAL_VETOES,
)
from app.services.operational_score_v2 import V2_DIMENSIONS

GRADE_LABELS = {
    "hero": "Hero Candidate",
    "core": "Core",
    "long_tail": "Long-tail",
    "reject": "Reject",
}
PENDING_TXT = "待补"


@dataclass
class ReportData:
    """Plain, already-loaded inputs (all optional; gaps are surfaced, not faked)."""

    product: dict[str, Any] = field(default_factory=dict)
    nuotao: dict[str, Any] | None = None       # latest ProductNuotaoScore as dict
    operational: dict[str, Any] | None = None  # latest M2.1 score (6 dims + total)
    cost: dict[str, Any] | None = None
    supplier: dict[str, Any] | None = None
    analyst: dict[str, Any] | None = None      # latest completed analyst run output
    coverage: dict[str, Any] = field(default_factory=dict)
    generated_at: str | None = None


def _f(value: Any, digits: int = 2) -> Any:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _recommendation(grade: str | None, vetoed: bool, stage: str | None) -> str:
    if vetoed or grade == "reject":
        return "reject"
    if stage == "test_candidate":
        return "test"
    return "hold"


def _veto_groups(findings: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_id = {item.get("rule_id"): item for item in findings or []}
    groups: dict[str, list[dict[str, Any]]] = {}
    for group_name, ids in (
        ("compliance", COMPLIANCE_VETOES),
        ("brand", BRAND_VETOES),
        ("commercial", COMMERCIAL_VETOES),
    ):
        rows = []
        for rule_id in ids:
            meta = VETO_RULES[rule_id]
            found = by_id.get(rule_id, {})
            rows.append(
                {
                    "id": rule_id,
                    "name": meta.name,
                    "check_type": meta.check_type,
                    "status": found.get("status", "pending"),
                    "detail": found.get("detail", PENDING_TXT),
                }
            )
        groups[group_name] = rows
    return groups


def _nuotao_dimensions(nuotao: dict[str, Any] | None) -> list[dict[str, Any]]:
    score_map = {
        "value": (nuotao or {}).get("value_score"),
        "utility": (nuotao or {}).get("utility_score"),
        "weight_packability": (nuotao or {}).get("weight_packability_score"),
        "durability": (nuotao or {}).get("durability_score"),
        "brand_fit": (nuotao or {}).get("brand_fit_score"),
        "differentiation": (nuotao or {}).get("differentiation_score"),
    }
    rows = []
    for key in DIMENSION_KEYS:
        score = _f(score_map.get(key), 1)
        weight = DIMENSION_WEIGHTS[key]
        rows.append(
            {
                "key": key,
                "label": DIMENSION_LABELS[key],
                "weight": _f(weight, 2),
                "score": score,
                "weighted": _f(score * float(weight) * 10, 2) if score is not None else None,
            }
        )
    return rows


def _operational_view(
    operational: dict[str, Any] | None, supplier: dict[str, Any] | None
) -> list[dict[str, Any]]:
    op = operational or {}
    supplier_score = None
    if supplier and supplier.get("score") is not None:
        supplier_score = _f(supplier["score"], 1)
    rows = []
    for dim in V2_DIMENSIONS:
        if dim.key == "supplier_qualification":
            score = supplier_score
        else:
            score = _f(op.get(dim.supplied_by_m21), 1) if dim.supplied_by_m21 else None
        rows.append(
            {
                "key": dim.key,
                "label": dim.label_cn,
                "weight": _f(dim.weight, 2),
                "source": dim.source,
                "score": score,
            }
        )
    return rows


def _missing_inputs(data: ReportData) -> list[str]:
    missing = []
    if data.nuotao is None:
        missing.append("Nuotao 评分（请先执行 V3 评估）")
    if data.operational is None:
        missing.append("11 维运营分（运营评分未生成）")
    if data.cost is None:
        missing.append("全成本测算（成本与利润未录入）")
    if data.supplier is None:
        missing.append("供应商分级")
    if data.analyst is None:
        missing.append("AI 市场分析（Product Analyst 未运行）")
    return missing


def build_selection_report(data: ReportData) -> dict[str, Any]:
    nuotao = data.nuotao or {}
    analyst = data.analyst or {}
    assessment = analyst.get("nuotao_assessment") or {}
    product = data.product or {}

    findings = nuotao.get("reject_reasons") or []
    # Full V1-V12 findings live in reject_reasons only for failures; prefer the
    # complete findings list the service stores in dimension_evidence when present.
    evidence = nuotao.get("dimension_evidence") or {}
    all_findings = evidence.get("veto_findings") or findings

    grade = nuotao.get("grade")
    stage = nuotao.get("funnel_stage") or product.get("funnel_stage")
    failed = [f.get("rule_id") for f in all_findings if f.get("status") == "fail"]
    vetoed = bool(failed)
    recommendation = _recommendation(grade, vetoed, stage)

    why = assessment.get("why_we_recommend") or []
    one_liner = analyst.get("market_reasoning")
    if not one_liner:
        one_liner = (
            f"自动摘要：Nuotao {_f(nuotao.get('total'), 1)} 分、"
            f"等级 {GRADE_LABELS.get(grade, '未评估')}；"
            + (f"触发否决 {failed}。" if failed else "暂无 AI 市场叙述，待 Product Analyst 补充。")
        )

    return {
        "header": {
            "sku": product.get("sku"),
            "name": product.get("name"),
            "category": product.get("category"),
            "source_url": product.get("source_url"),
            "generated_at": data.generated_at,
            "reviewer": "AI Product Analyst + 人工复核",
        },
        "summary": {
            "nuotao_total": _f(nuotao.get("total"), 1),
            "grade": grade,
            "grade_label": GRADE_LABELS.get(grade, "未评估"),
            "operational_total": _f((data.operational or {}).get("total"), 1),
            "vetoed": vetoed,
            "failed": failed,
            "funnel_stage": stage,
            "recommendation": recommendation,
            "confidence": _f(analyst.get("confidence"), 2),
            "one_liner": one_liner,
            "why_recommend": why,
        },
        "vetoes": _veto_groups(all_findings),
        "nuotao_dimensions": _nuotao_dimensions(nuotao),
        "operational_v2": {
            "coverage": data.coverage,
            "dimensions": _operational_view(data.operational, data.supplier),
        },
        "costing": data.cost,
        "market_and_ai": {
            "market_reasoning": analyst.get("market_reasoning"),
            "risks": analyst.get("risks") or [],
            "differentiation_note": assessment.get("differentiation_note"),
            "brand_fit": _f(assessment.get("brand_fit"), 1),
        },
        "pricing": analyst.get("pricing"),
        "test_plan": analyst.get("test_plan") if recommendation == "test" else None,
        "human_review": {
            "status": "pending",
            "note": "AI 生成初稿，人工复核后生效；AI 不预填评审结论。",
        },
        "data_completeness": {
            "missing": _missing_inputs(data),
            "model_version": nuotao.get("model_version"),
            "rule_version": nuotao.get("rule_version"),
        },
    }
