"""V3.0 proactive veto (V1-V12) and funnel-stage decision — pure functions.

Each rule resolves to one of:
* ``pass``    — structured data proves the product clears the rule;
* ``fail``    — structured data proves the rule is triggered (hard veto);
* ``pending`` — the data is missing or the rule needs AI/rulebook input (P2).

A ``pending`` rule never silently counts as a pass nor invents a veto: it is
surfaced so a human / later AI stage can close it. Only a concrete ``fail`` is
a hard veto in P1 (AGENTS.md: explicit null handling, no fabricated results).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.services.nuotao_score_mapper import DEEP_CANDIDATE_OP_MIN, ScoreFacts
from app.services.nuotao_score_v3 import (
    BRAND_FIT_VETO_BELOW,
    GRADE_REJECT,
    MARGIN_MIN,
    RETURN_RATE_MAX,
    SHIPPING_RATIO_MAX,
    VETO_ORDER,
)

PASS = "pass"
FAIL = "fail"
PENDING = "pending"


@dataclass(frozen=True)
class VetoFinding:
    rule_id: str
    status: str
    detail: str


def _category_hit(category: str | None, configured: tuple[str, ...]) -> bool:
    if not category or not configured:
        return False
    cat = category.strip().lower()
    return any(item.strip().lower() == cat for item in configured)


def _ai_finding(
    rule_id: str,
    ai_signals: "NormalizedAiSignals | None",
    *,
    risk_label: str,
    pending_detail: str,
) -> VetoFinding:
    """Resolve an AI-owned rule (V1/V2/V3/V5).

    Deterministic evidence is handled by the caller and always wins; here only
    an explicit AI pass/fail closes the rule, uncertain/missing stays pending.
    """
    ai = ai_signals.verdict_of(rule_id) if ai_signals is not None else None
    if ai is None:
        return VetoFinding(rule_id, PENDING, pending_detail)
    if ai.verdict == FAIL:
        detail = f"AI 判定{risk_label}：{ai.reason}" if ai.reason else f"AI 判定触发（{risk_label}）"
        return VetoFinding(rule_id, FAIL, detail)
    if ai.verdict == PASS:
        return VetoFinding(
            rule_id, PASS, f"AI 判定通过{('：' + ai.reason) if ai.reason else ''}"
        )
    return VetoFinding(rule_id, PENDING, "AI 无法判定，待人工/证据补全")


def evaluate_vetoes(
    facts: ScoreFacts,
    dimensions: dict[str, Decimal],
    ai_signals: "NormalizedAiSignals | None" = None,
) -> dict[str, Any]:
    """Evaluate every V1-V12 rule from structured facts and mapped dimensions.

    ``ai_signals`` (from the Product Analyst) may close the AI-owned rules
    V1/V2/V3/V5; deterministic evidence in ``facts`` always takes precedence.
    """
    findings: dict[str, VetoFinding] = {}

    # --- V1-V3 compliance/safety: deterministic flag wins, else AI closes ----
    for rule_id in ("V1", "V2", "V3"):
        if rule_id in facts.compliance_failures:
            findings[rule_id] = VetoFinding(rule_id, FAIL, "合规判定触发")
        else:
            findings[rule_id] = _ai_finding(
                rule_id,
                ai_signals,
                risk_label="存在合规/安全风险",
                pending_detail="待 AI 合规/安全判定",
            )

    # V4 banned import/sale category.
    if _category_hit(facts.category, facts.banned_categories):
        findings["V4"] = VetoFinding("V4", FAIL, f"品类 {facts.category} 命中禁售清单")
    elif facts.banned_categories:
        findings["V4"] = VetoFinding("V4", PASS, "不在禁售清单")
    else:
        findings["V4"] = VetoFinding("V4", PENDING, "禁售品类清单未配置")

    # V5 brand-focus破坏.
    if _category_hit(facts.category, facts.off_brand_categories):
        findings["V5"] = VetoFinding("V5", FAIL, f"品类 {facts.category} 偏离专业户外定位")
    elif facts.off_brand_categories:
        findings["V5"] = VetoFinding("V5", PASS, "未命中偏离品类")
    else:
        findings["V5"] = _ai_finding(
            "V5",
            ai_signals,
            risk_label="偏离品牌品类聚焦",
            pending_detail="品牌品类红线未配置/待 AI 判定",
        )

    # V6 low-price impulse feel.
    if facts.reference_price_usd is None:
        findings["V6"] = VetoFinding("V6", PENDING, "缺参考售价，无法判断低价杂货感")
    elif Decimal(str(facts.reference_price_usd)) < Decimal("5"):
        findings["V6"] = VetoFinding(
            "V6", FAIL, f"参考售价 ${facts.reference_price_usd} 低于 $5 impulse 阈值"
        )
    else:
        findings["V6"] = VetoFinding("V6", PASS, f"参考售价 ${facts.reference_price_usd}")

    # V7 conflict with an existing Hero.
    if not facts.existing_hero_categories:
        findings["V7"] = VetoFinding("V7", PASS, "尚无在册 Hero，无同质化冲突")
    elif _category_hit(facts.category, facts.existing_hero_categories):
        findings["V7"] = VetoFinding("V7", FAIL, f"品类 {facts.category} 与现有 Hero 同质化")
    else:
        findings["V7"] = VetoFinding("V7", PASS, "与现有 Hero 品类不冲突")

    # V8 Brand Fit hard floor.
    brand_fit = dimensions["brand_fit"]
    if brand_fit < BRAND_FIT_VETO_BELOW:
        findings["V8"] = VetoFinding("V8", FAIL, f"Brand Fit {brand_fit} < {BRAND_FIT_VETO_BELOW}")
    else:
        findings["V8"] = VetoFinding("V8", PASS, f"Brand Fit {brand_fit}")

    # V9 logistics feasibility.
    if facts.shipping_ratio is None:
        findings["V9"] = VetoFinding("V9", PENDING, "缺成本/售价，无法计算运费占比")
    elif Decimal(str(facts.shipping_ratio)) > SHIPPING_RATIO_MAX:
        findings["V9"] = VetoFinding(
            "V9", FAIL, f"运费占售价比 {facts.shipping_ratio} > {SHIPPING_RATIO_MAX}"
        )
    else:
        findings["V9"] = VetoFinding("V9", PASS, f"运费占比 {facts.shipping_ratio}")

    # V10 margin feasibility.
    if facts.margin_rate is None:
        findings["V10"] = VetoFinding("V10", PENDING, "缺成本/售价，无法计算全成本利润率")
    elif Decimal(str(facts.margin_rate)) < MARGIN_MIN:
        findings["V10"] = VetoFinding(
            "V10", FAIL, f"全成本利润率 {facts.margin_rate} < {MARGIN_MIN}"
        )
    else:
        findings["V10"] = VetoFinding("V10", PASS, f"利润率 {facts.margin_rate}")

    # V11 supplier feasibility.
    rating = str(facts.supplier_rating or "").upper()
    if not rating:
        findings["V11"] = VetoFinding("V11", PENDING, "无供应商分级信息")
    elif rating == "D":
        findings["V11"] = VetoFinding("V11", FAIL, "供应商为 D 级（C 级以下）")
    else:
        findings["V11"] = VetoFinding("V11", PASS, f"供应商 {rating} 级")

    # V12 return-rate risk.
    if facts.return_rate is None:
        findings["V12"] = VetoFinding("V12", PENDING, "缺退货率先验/实测，待补")
    elif Decimal(str(facts.return_rate)) > RETURN_RATE_MAX:
        findings["V12"] = VetoFinding(
            "V12", FAIL, f"预估退货率 {facts.return_rate} > {RETURN_RATE_MAX}"
        )
    else:
        findings["V12"] = VetoFinding("V12", PASS, f"退货率 {facts.return_rate}")

    ordered = [findings[rule_id] for rule_id in VETO_ORDER]
    failed = [f.rule_id for f in ordered if f.status == FAIL]
    pending = [f.rule_id for f in ordered if f.status == PENDING]
    return {
        "findings": ordered,
        "failed": failed,
        "pending": pending,
        "vetoed": bool(failed),
    }


def decide_funnel_stage(
    *,
    vetoed: bool,
    grade: str,
    operational_total: Decimal | None,
    nuotao_total: Decimal,
) -> str:
    """Resolve the V3.0 funnel stage from veto / scores.

    rejected <- any hard veto or Nuotao grade Reject (<65);
    screened <- passed vetoes but operational score below the deep-candidate bar;
    test_candidate <- cleared vetoes, operational bar met and Nuotao Score >= 65.
    """
    if vetoed or grade == GRADE_REJECT:
        return "rejected"
    if operational_total is not None and Decimal(str(operational_total)) < DEEP_CANDIDATE_OP_MIN:
        return "screened"
    if Decimal(str(nuotao_total)) >= Decimal("65"):
        return "test_candidate"
    return "screened"
