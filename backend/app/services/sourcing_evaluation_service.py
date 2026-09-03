"""
选品评测服务
加载标准化评测集，运行选品决策模型，计算准确率并生成评测报告
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

EVALUATION_SUITE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tests",
    "sourcing_evaluation_suite.json",
)


def load_evaluation_suite(path: str | None = None) -> dict[str, Any]:
    """加载评测集"""
    suite_path = path or EVALUATION_SUITE_PATH
    try:
        with open(suite_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error("Evaluation suite not found: %s", suite_path)
        return {"error": f"评测集文件不存在: {suite_path}", "test_cases": []}
    except json.JSONDecodeError as e:
        logger.error("Evaluation suite parse error: %s", str(e))
        return {"error": f"评测集解析失败: {str(e)}", "test_cases": []}


def run_evaluation(
    decision_fn: Any | None = None,
    test_case_ids: list[str] | None = None,
    path: str | None = None,
) -> dict[str, Any]:
    """
    运行评测

    Args:
        decision_fn: 选品决策函数，接收 input dict，返回 {decision, score, key_factors, risk_flags}
                     为 None 时使用内置基准评分器
        test_case_ids: 指定测试用例 ID，None 表示全部
        path: 评测集路径

    Returns:
        评测报告
    """
    suite = load_evaluation_suite(path)
    if suite.get("error"):
        return suite

    test_cases = suite.get("test_cases", [])
    if test_case_ids:
        test_cases = [tc for tc in test_cases if tc["id"] in test_case_ids]

    if not test_cases:
        return {"error": "无测试用例", "total": 0}

    # 使用决策函数或内置基准评分器
    decide = decision_fn or _baseline_scorer

    # 逐条评测
    results = []
    for tc in test_cases:
        try:
            output = decide(tc["input"])
            result = _evaluate_case(tc, output)
            results.append(result)
        except Exception as e:
            logger.error("Test case %s failed: %s", tc.get("id"), str(e))
            results.append({
                "id": tc.get("id"),
                "error": str(e),
                "passed": False,
                "score": 0,
            })

    # 汇总统计
    report = _summarize_results(results, suite)
    return report


def get_evaluation_status(path: str | None = None) -> dict[str, Any]:
    """获取评测集状态"""
    suite = load_evaluation_suite(path)
    if suite.get("error"):
        return suite

    test_cases = suite.get("test_cases", [])
    edge_cases = suite.get("edge_cases", [])

    # 按难度统计
    by_difficulty: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for tc in test_cases:
        diff = tc.get("difficulty", "unknown")
        by_difficulty[diff] = by_difficulty.get(diff, 0) + 1
        cat = tc.get("category", "unknown")
        by_category[cat] = by_category.get(cat, 0) + 1

    return {
        "success": True,
        "suite_name": suite.get("name", ""),
        "version": suite.get("version", ""),
        "total_test_cases": len(test_cases),
        "total_edge_cases": len(edge_cases),
        "pass_threshold": suite.get("pass_threshold", 70),
        "scoring_dimensions": suite.get("scoring_dimensions", []),
        "by_difficulty": by_difficulty,
        "by_category": by_category,
        "categories": list(by_category.keys()),
        "test_case_ids": [tc["id"] for tc in test_cases],
    }


# ============================================
# 内部工具函数
# ============================================

def _baseline_scorer(input_data: dict[str, Any]) -> dict[str, Any]:
    """
    内置基准评分器（基于规则的简单评分）
    用于无外部决策函数时的基准评测
    """
    cost = float(input_data.get("cost_price", 0))
    retail = float(input_data.get("retail_price", 0))
    weight = float(input_data.get("weight", 0))
    competitor_count = int(input_data.get("competitor_count", 0))
    monthly_sales = int(input_data.get("monthly_sales_est", 0))
    supplier_rating = float(input_data.get("supplier_rating", 0))
    hazardous = bool(input_data.get("hazardous", False))
    regulated = bool(input_data.get("regulated", False))
    battery = bool(input_data.get("battery", False))
    size = input_data.get("size", "")

    # 利润评分
    profit_margin = (retail - cost) / retail * 100 if retail else 0
    profit_score = min(100, profit_margin * 1.5) if profit_margin > 0 else 0

    # 需求评分
    demand_score = min(100, monthly_sales / 20) if monthly_sales else 50

    # 竞争评分（竞争越少分越高）
    competition_score = max(0, 100 - competitor_count) if competitor_count else 50

    # 物流评分
    logistics_score = max(0, 100 - weight * 15)
    if size == "large":
        logistics_score -= 20
    if hazardous:
        logistics_score -= 30
    if battery:
        logistics_score -= 10

    # 合规评分
    compliance_score = 80
    if regulated:
        compliance_score -= 50
    if hazardous:
        compliance_score -= 20
    certs = input_data.get("certifications", [])
    if certs:
        compliance_score = min(100, compliance_score + len(certs) * 5)

    # 供应商评分
    supplier_score = supplier_rating * 20 if supplier_rating else 50

    # 综合评分
    total_score = (
        profit_score * 0.30
        + demand_score * 0.20
        + competition_score * 0.15
        + logistics_score * 0.15
        + compliance_score * 0.10
        + supplier_score * 0.10
    )

    # 决策
    risk_flags = []
    if regulated:
        risk_flags.append("管制物品")
    if hazardous:
        risk_flags.append("危险品物流限制")
    if battery:
        risk_flags.append("电池物流限制")
    if size == "large":
        risk_flags.append("大件物流成本高")
    if competitor_count > 60:
        risk_flags.append("竞争激烈")
    if supplier_rating and supplier_rating < 4.0:
        risk_flags.append("供应商评分低")

    if regulated or (hazardous and compliance_score < 50):
        decision = "reject"
    elif total_score >= 70 and len(risk_flags) <= 2:
        decision = "approve"
    elif total_score >= 55:
        decision = "approve_with_caution"
    elif total_score >= 45:
        decision = "pending_review"
    else:
        decision = "reject"

    key_factors = []
    if profit_margin > 50:
        key_factors.append("高利润率")
    if monthly_sales > 1000:
        key_factors.append("高需求")
    if weight < 1:
        key_factors.append("轻小件")
    if supplier_rating >= 4.5:
        key_factors.append("优质供应商")

    return {
        "decision": decision,
        "score": round(total_score, 1),
        "key_factors": key_factors,
        "risk_flags": risk_flags,
        "dimension_scores": {
            "profit": round(profit_score, 1),
            "demand": round(demand_score, 1),
            "competition": round(competition_score, 1),
            "logistics": round(logistics_score, 1),
            "compliance": round(compliance_score, 1),
            "supplier": round(supplier_score, 1),
        },
    }


def _evaluate_case(test_case: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    """评估单个测试用例"""
    expected = test_case["expected"]
    expected_decision = expected.get("decision", "")
    actual_decision = output.get("decision", "")

    # 决策匹配
    decision_match = actual_decision == expected_decision
    decision_partial = _is_decision_close(actual_decision, expected_decision)

    # 分数匹配
    actual_score = output.get("score", 0)
    if "min_score" in expected:
        score_pass = actual_score >= expected["min_score"]
    elif "max_score" in expected:
        score_pass = actual_score <= expected["max_score"]
    else:
        score_pass = True

    # 关键因素匹配
    expected_factors = set(expected.get("key_factors", []))
    actual_factors = set(output.get("key_factors", []))
    factor_match = len(expected_factors & actual_factors) / len(expected_factors) if expected_factors else 1.0

    # 风险标记匹配
    expected_risks = set(expected.get("risk_flags", []))
    actual_risks = set(output.get("risk_flags", []))
    risk_match = len(expected_risks & actual_risks) / len(expected_risks) if expected_risks else 1.0

    # 综合得分（百分制）
    case_score = (
        (100 if decision_match else 60 if decision_partial else 0) * 0.40
        + (100 if score_pass else 0) * 0.30
        + factor_match * 100 * 0.20
        + risk_match * 100 * 0.10
    )

    passed = case_score >= 70

    return {
        "id": test_case["id"],
        "category": test_case.get("category", ""),
        "difficulty": test_case.get("difficulty", ""),
        "expected_decision": expected_decision,
        "actual_decision": actual_decision,
        "decision_match": decision_match,
        "expected_score_range": {
            "min": expected.get("min_score"),
            "max": expected.get("max_score"),
        },
        "actual_score": actual_score,
        "score_pass": score_pass,
        "factor_match_pct": round(factor_match * 100, 1),
        "risk_match_pct": round(risk_match * 100, 1),
        "case_score": round(case_score, 1),
        "passed": passed,
        "output": output,
    }


def _is_decision_close(actual: str, expected: str) -> bool:
    """判断决策是否接近（相邻决策视为部分匹配）"""
    order = ["reject", "pending_review", "approve_with_caution", "approve"]
    try:
        return abs(order.index(actual) - order.index(expected)) <= 1
    except ValueError:
        return False


def _summarize_results(results: list[dict[str, Any]], suite: dict[str, Any]) -> dict[str, Any]:
    """汇总评测结果"""
    total = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    failed = total - passed
    avg_score = sum(r.get("case_score", 0) for r in results) / total if total else 0

    # 决策准确率
    decision_accuracy = sum(1 for r in results if r.get("decision_match")) / total * 100 if total else 0

    # 按难度统计
    by_difficulty: dict[str, dict[str, Any]] = {}
    for r in results:
        diff = r.get("difficulty", "unknown")
        if diff not in by_difficulty:
            by_difficulty[diff] = {"total": 0, "passed": 0, "scores": []}
        by_difficulty[diff]["total"] += 1
        if r.get("passed"):
            by_difficulty[diff]["passed"] += 1
        by_difficulty[diff]["scores"].append(r.get("case_score", 0))

    for diff, data in by_difficulty.items():
        data["pass_rate"] = round(data["passed"] / data["total"] * 100, 1) if data["total"] else 0
        data["avg_score"] = round(sum(data["scores"]) / len(data["scores"]), 1) if data["scores"] else 0
        del data["scores"]

    # 错误案例
    failed_cases = [r for r in results if not r.get("passed")]

    # 整体通过
    overall_pass = avg_score >= suite.get("pass_threshold", 70)

    return {
        "success": True,
        "evaluated_at": datetime.utcnow().isoformat(),
        "suite_name": suite.get("name", ""),
        "suite_version": suite.get("version", ""),
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(passed / total * 100, 1) if total else 0,
        "avg_score": round(avg_score, 1),
        "decision_accuracy": round(decision_accuracy, 1),
        "pass_threshold": suite.get("pass_threshold", 70),
        "overall_pass": overall_pass,
        "by_difficulty": by_difficulty,
        "failed_cases": [
            {
                "id": r["id"],
                "expected": r["expected_decision"],
                "actual": r["actual_decision"],
                "score": r["case_score"],
                "reason": _diagnose_failure(r),
            }
            for r in failed_cases
        ],
        "results": results,
        "recommendations": _generate_recommendations(by_difficulty, failed_cases, overall_pass),
    }


def _diagnose_failure(result: dict[str, Any]) -> str:
    """诊断失败原因"""
    reasons = []
    if not result.get("decision_match"):
        reasons.append(f"决策不匹配（期望{result['expected_decision']}，实际{result['actual_decision']}）")
    if not result.get("score_pass"):
        reasons.append("分数不在期望范围")
    if result.get("factor_match_pct", 100) < 50:
        reasons.append("关键因素识别不足")
    if result.get("risk_match_pct", 100) < 50:
        reasons.append("风险标记识别不足")
    return "; ".join(reasons) or "综合得分不足"


def _generate_recommendations(
    by_difficulty: dict[str, Any],
    failed_cases: list[dict[str, Any]],
    overall_pass: bool,
) -> list[str]:
    """生成改进建议"""
    recs = []
    if not overall_pass:
        recs.append("整体未通过评测阈值，建议优先优化评分模型权重和决策边界")

    # 按难度分析
    for diff, data in by_difficulty.items():
        if data.get("pass_rate", 100) < 60:
            recs.append(f"{diff}难度用例通过率仅{data['pass_rate']}%，建议加强该难度级别的规则覆盖")

    # 失败案例共性
    if failed_cases:
        reject_failures = [f for f in failed_cases if f.get("expected", f.get("expected_decision", "")) == "reject"]
        if len(reject_failures) > len(failed_cases) * 0.5:
            recs.append("多数失败案例为应拒绝产品，建议加强风险识别（管制/危险品/质量问题）")

        regulated_failures = [f for f in failed_cases if "管制" in f.get("reason", "") or "合规" in f.get("reason", "")]
        if regulated_failures:
            recs.append("合规风险识别不足，建议强化管制物品/药监/专利风险的检测规则")

    if not recs:
        recs.append("评测表现良好，建议持续扩充测试用例覆盖更多品类和边界场景")

    return recs
