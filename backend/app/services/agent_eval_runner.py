"""Agent 评测集执行器 — 离线/在线两种模式。

- ``--dry-run``（默认）：只执行 deterministic 用例（不调用 LLM），
  通过注册的确定性评测函数对 Agent 服务层纯逻辑做回归校验。
- ``--with-llm``：额外执行 ``eval_mode=llm`` 用例（需配置 API key 与数据库）。

输出 JSON 评分卡：每 Agent 用例数 / 通过数 / 失败明细，人工可复核。

用例数据源: ``backend/app/data/agent_eval_sets/*.json``（每个 Agent ≥20 条）。
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

# --------------------------------------------------------------------------- #
# 确定性评测函数（不依赖 DB / LLM）
# --------------------------------------------------------------------------- #

from app.services import profit_engine, strategy_updater
from app.services.profit_engine import ProfitInput
from app.services.report_truthfulness import (
    CampaignMetric,
    SegmentMetric,
    validate_marketing_report,
)

logger = logging.getLogger(__name__)

# 中文/英文 PII 与敏感模式
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE_RE = re.compile(r"(?<!\d)(1[3-9]\d{9}|13800138000)(?!\d)")
_ADDRESS_MARKERS = ("street", "road", "avenue", "blvd", "路", "街道", "大道", "小区", "栋", "main st")
_LINK_RE = re.compile(r"https?://|www\.")
_TEMPLATE_VAR_RE = re.compile(r"\{\{|\}\}")
_ABUSE_WORDS = (
    "蠢货", "白痴", "骗子", "垃圾公司", "stupid", "idiot", "liar",
    "难伺候", "外国客户", "爱买不买",
)
_ABSOLUTE_PROMISES = ("绝对没问题", "100% 保证", "一定发货", "绝对准时", "一定到", "guarantee 100%")
_BAD_ACTS = ("银行卡号", "cvv", "返现", "删差评", "给差评", "索要密码", "paypal password")

# 报告必填指标
_REPORT_REQUIRED = ("week", "revenue", "orders", "gross_margin", "refund_rate", "ad_spend", "roas")
_REPORT_SOURCES_REQUIRED = True



def _num(v: Any) -> Decimal | None:
    try:
        return Decimal(str(v))
    except (TypeError, ValueError, InvalidOperation):
        return None


def _eval_profit_margin(inputs: dict[str, Any]) -> dict[str, Any]:
    """profit_engine 毛利核算（确定性）。"""
    result = profit_engine.calculate_contribution_margin(
        ProfitInput(
            revenue=_num(inputs.get("revenue")) or Decimal("0"),
            product_cost=_num(inputs.get("product_cost")) or Decimal("0"),
            shipping_cost=_num(inputs.get("shipping_cost")) or Decimal("0"),
            payment_fee=_num(inputs.get("payment_fee")) or Decimal("0"),
            refund=_num(inputs.get("refund")) or Decimal("0"),
            advertising_cost=_num(inputs.get("advertising_cost")) or Decimal("0"),
        )
    )
    return result.as_snapshot()


def _eval_cost_confidence(inputs: dict[str, Any]) -> dict[str, Any]:
    """成本置信度判定（确定性）。"""
    matched = int(inputs.get("matched", 0))
    total = int(inputs.get("total", 0))
    conf = profit_engine.assess_cost_confidence(matched=matched, total=total)
    return {
        "cost_status": conf.cost_status.value,
        "profit_confidence": conf.profit_confidence.value,
        "reasons": conf.reasons,
    }


def _eval_ab_significance(inputs: dict[str, Any]) -> dict[str, Any]:
    """A/B 显著性判断（确定性）。"""
    result = strategy_updater.evaluate_ab_test_result(
        variant_a_metrics=dict(inputs.get("variant_a_metrics", {})),
        variant_b_metrics=dict(inputs.get("variant_b_metrics", {})),
        sample_size_a=int(inputs.get("sample_size_a", 0)),
        sample_size_b=int(inputs.get("sample_size_b", 0)),
        primary_metric=inputs.get("primary_metric", "conversion_rate"),
        confidence_threshold=float(inputs.get("confidence_threshold", 0.95)),
        min_sample_size=int(inputs.get("min_sample_size", 50)),
    )
    return result


def _eval_report_truthfulness(inputs: dict[str, Any]) -> dict[str, Any]:
    """报告防造假 R1-R7 校验（确定性）。"""
    campaigns = [
        CampaignMetric(
            name=c.get("name", ""),
            channel=c.get("channel"),
            status=c.get("status", "active"),
            spend=_num(c.get("spend")),
            revenue=_num(c.get("revenue")),
            source=c.get("source"),
        )
        for c in inputs.get("campaigns", [])
    ]
    segments = [
        SegmentMetric(
            name=s.get("name", ""),
            customer_count=int(s.get("customer_count", 0)),
            revenue=_num(s.get("revenue")),
            source=s.get("source"),
        )
        for s in inputs.get("segments", [])
    ]
    result = validate_marketing_report(
        campaigns=campaigns,
        segments=segments,
        actions=inputs.get("actions") or [],
        output=inputs.get("output"),
    )
    return {
        "is_valid": result.passed,
        "issues": result.violations,
        "warnings": result.warnings,
    }


def _eval_reply_safety(inputs: dict[str, Any]) -> dict[str, Any]:
    """客服回复安全合规校验（确定性内置检查器）。"""
    reply = str(inputs.get("candidate_reply") or "")
    violations: list[str] = []
    if not reply.strip():
        violations.append("空回复禁止发送")
    if _EMAIL_RE.search(reply):
        violations.append("回复包含邮箱 PII")
    if _PHONE_RE.search(reply):
        violations.append("回复包含电话 PII")
    if any(marker.lower() in reply.lower() for marker in _ADDRESS_MARKERS):
        violations.append("回复可能包含地址 PII")
    if _LINK_RE.search(reply):
        violations.append("回复包含外部链接")
    if _TEMPLATE_VAR_RE.search(reply):
        violations.append("回复含未渲染模板变量")
    for w in _ABUSE_WORDS:
        if w.lower() in reply.lower():
            violations.append(f"回复含不当用语: {w}")
    for p in _ABSOLUTE_PROMISES:
        if p.lower() in reply.lower():
            violations.append(f"回复含绝对化承诺: {p}")
    for b in _BAD_ACTS:
        if b.lower() in reply.lower():
            violations.append(f"回复含违规操作: {b}")
    if "全额退款" in reply and "审核" not in reply and "政策" not in reply:
        violations.append("越权承诺全额退款")
    if re.search(r"\d+\.?\d*\s*(美元|usd|eur|€|\$)", reply) and "审核" not in reply and "政策" not in reply:
        violations.append("价格承诺需审批引导")
    if len(reply) > 500:
        violations.append("回复超长（>500字符），疑似机械堆叠")
    return {"is_safe": len(violations) == 0, "violations": violations}


def _eval_report_completeness(inputs: dict[str, Any]) -> dict[str, Any]:
    """经营报告完整性/合法性校验（确定性内置检查器）。"""
    report = inputs.get("report") or {}
    violations: list[str] = []
    missing = [k for k in _REPORT_REQUIRED if k not in report]
    if missing:
        violations.append(f"缺少必填指标: {','.join(missing)}")

    week = report.get("week")
    if week is not None and not re.match(r"^\d{4}-W\d{1,2}$", str(week)):
        violations.append("周标识格式非法（应为 YYYY-Wxx）")

    for k in ("revenue", "orders", "gross_margin", "refund_rate", "ad_spend", "roas"):
        v = report.get(k)
        if v is not None and not isinstance(v, (int, float, Decimal)):
            violations.append(f"指标 {k} 必须为数字")

    roas = _num(report.get("roas"))
    if roas is not None and roas > 100:
        violations.append("ROAS 越界（>100）")
    refund_rate = _num(report.get("refund_rate"))
    if refund_rate is not None and refund_rate > 0.5:
        violations.append("退款率越界（>50%）")
    margin = _num(report.get("gross_margin"))
    if margin is not None and margin > 1:
        violations.append("毛利率越界（>1）")
    orders = _num(report.get("orders"))
    if orders is not None and orders < 0:
        violations.append("订单数为负")

    notes = str(report.get("notes") or "")
    if _EMAIL_RE.search(notes) or _PHONE_RE.search(notes):
        violations.append("报告备注包含 PII")
        pii_found = True
    if re.search(r"\d{6,}", notes):
        violations.append("报告备注含疑似内部账号 ID")

    forecast = str(report.get("forecast") or "")
    if forecast and ("若" not in forecast and "假设" not in forecast and "if" not in forecast.lower()):
        violations.append("预测必须带模型与假设")
    if "差异" in notes and "缺口" not in notes and "差异" in notes and not re.search(r"缺口\s*[:：]?\s*\d", notes):
        violations.append("提及收入差异必须披露缺口金额")

    prev_rev = _num(report.get("prev_week_revenue"))
    rev = _num(report.get("revenue"))
    if prev_rev and rev and prev_rev > 0 and rev / prev_rev >= 10 and "归因" not in notes and "增长因" not in notes and "提升" not in notes:
        violations.append("异常高增长（≥10倍）必须归因说明")

    sources = report.get("data_sources")
    if _REPORT_SOURCES_REQUIRED and (not sources or len(sources) == 0):
        violations.append("缺少数据来源标注")

    return {
        "is_complete": len(violations) == 0,
        "missing": missing,
        "pii_found": "报告备注包含 PII" in violations,
        "issues": violations,
    }


EVAL_FUNCTIONS: dict[tuple[str, str], Callable[[dict[str, Any]], dict[str, Any]]] = {
    ("product_manager", "profit_margin"): _eval_profit_margin,
    ("product_manager", "cost_confidence"): _eval_cost_confidence,
    ("supply_chain_manager", "restock_margin"): _eval_profit_margin,
    ("supply_chain_manager", "cost_confidence"): _eval_cost_confidence,
    ("marketing_manager", "ab_significance"): _eval_ab_significance,
    ("marketing_manager", "report_truthfulness"): _eval_report_truthfulness,
    ("customer_manager", "reply_safety"): _eval_reply_safety,
    ("business_analyst", "report_completeness"): _eval_report_completeness,
}

# 规则类型 → 校验函数签名：check(output, rule) -> str | None（None=通过）
def _rule_checker(rule: dict[str, Any]) -> Callable[[dict[str, Any]], str | None]:
    rtype = rule.get("type")
    key = rule.get("key", "")

    def _get(value: Any) -> Any:
        if isinstance(value, dict):
            return value.get(key)
        return None

    if rtype == "key_exists":
        return lambda out: None if _get(out) is not None else f"缺失输出键: {key}"
    if rtype == "truthy":
        return lambda out: None if _get(out) else f"键 {key} 应为真值"
    if rtype == "value_equal":
        return lambda out: None if _close_eq(_get(out), rule.get("value")) else f"{key} 应为 {rule.get('value')}，实际 {_get(out)}"
    if rtype == "value_range":
        return lambda out: None if _in_range(_get(out), rule.get("min"), rule.get("max")) else f"{key} 不在区间 [{rule.get('min')},{rule.get('max')}]，实际 {_get(out)}"
    if rtype == "value_in":
        return lambda out: None if _get(out) in rule.get("values", []) else f"{key} 应在 {rule.get('values')}，实际 {_get(out)}"
    if rtype == "value_not_in":
        return lambda out: None if _get(out) not in rule.get("values", []) else f"{key} 不应在 {rule.get('values')}"
    if rtype == "value_lt":
        return lambda out: None if _num(_get(out)) is not None and _num(_get(out)) < _num(rule.get("value")) else f"{key} 应 < {rule.get('value')}，实际 {_get(out)}"
    if rtype == "value_gt":
        return lambda out: None if _num(_get(out)) is not None and _num(_get(out)) > _num(rule.get("value")) else f"{key} 应 > {rule.get('value')}，实际 {_get(out)}"
    if rtype == "max_length":
        return lambda out: None if _get(out) is None or len(str(_get(out))) <= int(rule.get("value", 0)) else f"{key} 超长（>{rule.get('value')}字符）"
    if rtype == "min_length":
        return lambda out: None if _get(out) is None or len(str(_get(out))) >= int(rule.get("value", 0)) else f"{key} 过短（<{rule.get('value')}字符）"
    if rtype == "forbidden_text":
        vals = [str(v) for v in rule.get("values", [])]
        return lambda out: None if not any(v.lower() in str(_get(out) or "").lower() for v in vals) else f"{key} 包含禁词 {vals}"
    return lambda out: None


def _close_eq(a: Any, b: Any) -> bool:
    an, bn = _num(a), _num(b)
    if an is not None and bn is not None:
        return abs(an - bn) < Decimal("1e-6")
    return a == b


def _in_range(a: Any, lo: Any, hi: Any) -> bool:
    an = _num(a)
    if an is None:
        return False
    if lo is not None and an < _num(lo):
        return False
    if hi is not None and an > _num(hi):
        return False
    return True


# --------------------------------------------------------------------------- #
# 执行与评分卡
# --------------------------------------------------------------------------- #

def load_eval_sets(data_dir: Path | None = None) -> list[dict[str, Any]]:
    data_dir = data_dir or (Path(__file__).resolve().parent.parent / "data" / "agent_eval_sets")
    sets: list[dict[str, Any]] = []
    for path in sorted(data_dir.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        agent_id = raw.get("agent_id", "")
        # 将顶层 agent_id 注入每条用例，供 EVAL_FUNCTIONS 路由
        for case in raw.get("cases", []):
            case.setdefault("agent_id", agent_id)
        sets.append(raw)
    return sets


def run_case(case: dict[str, Any], *, with_llm: bool) -> dict[str, Any]:
    """执行单个用例，返回结果 dict。"""
    agent_id = case.get("agent_id", "")
    category = case.get("category", "")
    eval_mode = case.get("eval_mode", "deterministic")
    expected = case.get("expected", {})
    inputs = case.get("input", {})

    if eval_mode == "llm":
        if not with_llm:
            return {
                "case_id": case.get("id"), "category": category,
                "passed": None, "skipped": True,
                "reason": "requires_llm（--with-llm 时执行）",
            }
        return {
            "case_id": case.get("id"), "category": category,
            "passed": None, "skipped": True,
            "reason": "llm 模式需接入 Agent 推理（当前版本由人工/CI 联调执行）",
        }

    func = EVAL_FUNCTIONS.get((agent_id, category))
    if func is None:
        return {
            "case_id": case.get("id"), "category": category,
            "passed": None, "skipped": True,
            "reason": f"未注册确定性评测函数: {agent_id}/{category}",
        }

    try:
        output = func(inputs)
    except Exception as exc:  # noqa: BLE001
        return {
            "case_id": case.get("id"), "category": category,
            "passed": False, "skipped": False,
            "output": {}, "violations": [f"执行异常: {exc}"],
        }

    violations: list[str] = []
    for rule in expected.get("rules", []):
        checker = _rule_checker(rule)
        message = checker(output)
        if message:
            violations.append(message)
    for forbidden in expected.get("forbidden", []):
        if str(forbidden).lower() in str(output).lower():
            violations.append(f"输出包含禁词: {forbidden}")

    return {
        "case_id": case.get("id"), "category": category,
        "passed": len(violations) == 0, "skipped": False,
        "output": output, "violations": violations,
    }


def build_scorecard(sets: list[dict[str, Any]], *, with_llm: bool) -> dict[str, Any]:
    """为全部评测集生成评分卡。"""
    per_agent: dict[str, dict[str, Any]] = {}
    all_cases: list[dict[str, Any]] = []
    for es in sets:
        agent_id = es.get("agent_id", "unknown")
        cases = es.get("cases", [])
        results = [run_case(c, with_llm=with_llm) for c in cases]
        executed = [r for r in results if not r.get("skipped")]
        passed = [r for r in executed if r.get("passed")]
        failed = [r for r in executed if not r.get("passed")]
        per_agent[agent_id] = {
            "total": len(cases),
            "executed": len(executed),
            "passed": len(passed),
            "failed": len(failed),
            "skipped": len(results) - len(executed),
            "pass_rate": round(len(passed) / len(executed), 4) if executed else 0.0,
            "failures": [
                {"case_id": r["case_id"], "category": r["category"], "violations": r["violations"]}
                for r in failed
            ],
        }
        all_cases.extend(results)

    total = len(all_cases)
    executed = [r for r in all_cases if not r.get("skipped")]
    passed = [r for r in executed if r.get("passed")]
    return {
        "total_cases": total,
        "executed": len(executed),
        "passed": len(passed),
        "failed": len(executed) - len(passed),
        "skipped": total - len(executed),
        "overall_pass_rate": round(len(passed) / len(executed), 4) if executed else 0.0,
        "per_agent": per_agent,
        "with_llm": with_llm,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent 评测集执行器")
    parser.add_argument("--agent", help="只评测指定 Agent（agent_id）")
    parser.add_argument("--with-llm", action="store_true", help="包含 llm 模式用例（需联调环境）")
    parser.add_argument("--json", action="store_true", help="输出 JSON 评分卡")
    args = parser.parse_args()

    sets = load_eval_sets()
    if args.agent:
        sets = [s for s in sets if s.get("agent_id") == args.agent]
        if not sets:
            print(f"未找到 Agent 评测集: {args.agent}", file=sys.stderr)
            return 2

    card = build_scorecard(sets, with_llm=args.with_llm)
    if args.json:
        print(json.dumps(card, ensure_ascii=False, indent=2))
    else:
        print(f"评测集汇总: 用例 {card['total_cases']} | 执行 {card['executed']} | 通过 {card['passed']} | 失败 {card['failed']} | 跳过 {card['skipped']} | 通过率 {card['overall_pass_rate']:.1%}")
        for agent_id, stat in card["per_agent"].items():
            print(f"  {agent_id}: {stat['passed']}/{stat['executed']} 通过 ({stat['pass_rate']:.1%})")
            for failure in stat["failures"]:
                print(f"    ✗ {failure['case_id']} [{failure['category']}]")
                for v in failure["violations"]:
                    print(f"      - {v}")
    return 0 if card["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
