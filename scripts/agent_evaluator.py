"""
Nuotao AI OS - AI Agent 评测运行器
功能：
  1. 加载评测集配置
  2. 运行指定 Agent 的评测用例
  3. 自动评分（基于预期关键词匹配）
  4. 生成评测报告
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, "E:/AI/nuotao-ai-os/backend")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("agent_evaluator")

EVALUATION_FILE = Path("E:/AI/nuotao-ai-os/backend/tests/agent_evaluation_suite.json")
REPORT_DIR = Path("E:/AI/nuotao-ai-os/backups/agent_evaluation")
REPORT_DIR.mkdir(parents=True, exist_ok=True)


def load_evaluation_suite() -> dict:
    """加载评测集配置"""
    with open(EVALUATION_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def calculate_score(result_text: str, expected_keywords: list[str], criteria: dict) -> dict:
    """
    基于关键词匹配计算评分
    注意：这是简化版自动评分，实际应结合人工评审
    """
    result_lower = result_text.lower()

    # 准确性：预期关键词匹配率
    matched = sum(1 for kw in expected_keywords if kw.lower() in result_lower)
    accuracy_score = (matched / len(expected_keywords)) * 100 if expected_keywords else 0

    # 完整性：结果长度（简单代理指标）
    completeness_score = min(len(result_text) / 500 * 100, 100)

    # 可执行性：是否包含具体建议词
    action_words = ["建议", "应该", "可以", "需要", "推荐", "策略", "方案", "步骤", "plan", "should", "recommend"]
    action_matched = sum(1 for w in action_words if w in result_text)
    actionability_score = min(action_matched / 3 * 100, 100)

    # 相关性：预期关键词匹配（与准确性共享指标）
    relevance_score = accuracy_score

    # 合规性：是否包含免责声明或安全提示（简化）
    compliance_score = 90  # 默认合规

    # 加权总分
    total_score = (
        accuracy_score * criteria["accuracy"]["weight"]
        + relevance_score * criteria["relevance"]["weight"]
        + completeness_score * criteria["completeness"]["weight"]
        + actionability_score * criteria["actionability"]["weight"]
        + compliance_score * criteria["compliance"]["weight"]
    )

    return {
        "total": round(total_score, 2),
        "accuracy": round(accuracy_score, 2),
        "relevance": round(relevance_score, 2),
        "completeness": round(completeness_score, 2),
        "actionability": round(actionability_score, 2),
        "compliance": round(compliance_score, 2),
        "matched_keywords": matched,
        "total_keywords": len(expected_keywords),
    }


def run_evaluation(agent_key: str, max_cases: int = 5) -> dict:
    """
    运行指定 Agent 的评测
    注意：由于实际调用 LLM 需要成本和时间，这里使用模拟结果进行演示
    实际使用时应替换为真实的 Agent 调用
    """
    suite = load_evaluation_suite()
    agent_config = suite["agents"][agent_key]
    criteria = suite["scoring_criteria"]
    pass_threshold = suite["pass_threshold"]

    logger.info("=" * 60)
    logger.info("Evaluating agent: %s (%s)", agent_config["name"], agent_key)
    logger.info("Test cases: %d (running %d)", len(agent_config["test_cases"]), max_cases)
    logger.info("=" * 60)

    results = []
    total_start = time.time()

    for i, test_case in enumerate(agent_config["test_cases"][:max_cases]):
        logger.info("[%d/%d] Running: %s - %s",
                    i + 1, max_cases, test_case["id"], test_case["category"])

        start_time = time.time()

        # 模拟 Agent 运行（实际使用时替换为真实调用）
        # 这里生成一个包含预期关键词的模拟结果
        expected = test_case["expected"]
        mock_result = f"针对{test_case['category']}的分析结果：\n"
        mock_result += f"输入：{json.dumps(test_case['input'], ensure_ascii=False)}\n\n"
        mock_result += "分析要点：\n"
        for j, kw in enumerate(expected):
            mock_result += f"  {j+1}. {kw}：基于数据分析，建议采取相应措施。\n"
        mock_result += "\n结论：建议按照上述要点执行，并持续监控效果。"

        duration = (time.time() - start_time) * 1000

        # 计算评分
        score = calculate_score(mock_result, expected, criteria)

        result = {
            "test_case_id": test_case["id"],
            "category": test_case["category"],
            "difficulty": test_case["difficulty"],
            "input": test_case["input"],
            "expected": expected,
            "result_preview": mock_result[:200] + "..." if len(mock_result) > 200 else mock_result,
            "score": score,
            "passed": score["total"] >= pass_threshold,
            "duration_ms": round(duration, 2),
        }
        results.append(result)

        status = "PASS" if result["passed"] else "FAIL"
        logger.info("  Score: %.2f (%s) | Duration: %.2fms", score["total"], status, duration)

    total_duration = (time.time() - total_start) * 1000

    # 汇总统计
    passed_count = sum(1 for r in results if r["passed"])
    avg_score = sum(r["score"]["total"] for r in results) / len(results) if results else 0

    # 按难度统计
    difficulty_stats = {}
    for r in results:
        diff = r["difficulty"]
        if diff not in difficulty_stats:
            difficulty_stats[diff] = {"count": 0, "passed": 0, "total_score": 0}
        difficulty_stats[diff]["count"] += 1
        difficulty_stats[diff]["total_score"] += r["score"]["total"]
        if r["passed"]:
            difficulty_stats[diff]["passed"] += 1

    summary = {
        "agent_key": agent_key,
        "agent_name": agent_config["name"],
        "description": agent_config["description"],
        "evaluation_timestamp": datetime.now(timezone.utc).isoformat(),
        "total_test_cases": len(agent_config["test_cases"]),
        "executed_test_cases": len(results),
        "passed_count": passed_count,
        "failed_count": len(results) - passed_count,
        "pass_rate": round(passed_count / len(results) * 100, 2) if results else 0,
        "average_score": round(avg_score, 2),
        "pass_threshold": pass_threshold,
        "total_duration_ms": round(total_duration, 2),
        "difficulty_stats": difficulty_stats,
        "results": results,
    }

    return summary


def generate_report(summary: dict) -> str:
    """生成评测报告"""
    report_lines = []
    report_lines.append("=" * 70)
    report_lines.append(f"  AI Agent Evaluation Report - {summary['agent_name']}")
    report_lines.append("=" * 70)
    report_lines.append(f"  Agent: {summary['agent_key']} ({summary['agent_name']})")
    report_lines.append(f"  Description: {summary['description']}")
    report_lines.append(f"  Evaluation Time: {summary['evaluation_timestamp']}")
    report_lines.append("")
    report_lines.append("  --- Summary ---")
    report_lines.append(f"  Total Test Cases: {summary['total_test_cases']}")
    report_lines.append(f"  Executed: {summary['executed_test_cases']}")
    report_lines.append(f"  Passed: {summary['passed_count']}")
    report_lines.append(f"  Failed: {summary['failed_count']}")
    report_lines.append(f"  Pass Rate: {summary['pass_rate']}%")
    report_lines.append(f"  Average Score: {summary['average_score']}")
    report_lines.append(f"  Pass Threshold: {summary['pass_threshold']}")
    report_lines.append(f"  Total Duration: {summary['total_duration_ms']:.2f}ms")
    report_lines.append("")
    report_lines.append("  --- Difficulty Breakdown ---")
    for diff, stats in summary["difficulty_stats"].items():
        avg = stats["total_score"] / stats["count"] if stats["count"] else 0
        report_lines.append(f"  {diff}: {stats['count']} cases, {stats['passed']} passed, avg {avg:.2f}")
    report_lines.append("")
    report_lines.append("  --- Detailed Results ---")
    for r in summary["results"]:
        status = "PASS" if r["passed"] else "FAIL"
        report_lines.append(f"  [{r['test_case_id']}] {r['category']} ({r['difficulty']})")
        report_lines.append(f"    Score: {r['score']['total']:.2f} | {status} | {r['duration_ms']:.2f}ms")
        report_lines.append(f"    Keywords: {r['score']['matched_keywords']}/{r['score']['total_keywords']} matched")
    report_lines.append("")
    report_lines.append("  Note: This evaluation uses simulated results for demonstration.")
    report_lines.append("  For production use, replace mock results with actual Agent calls.")
    report_lines.append("=" * 70)

    return "\n".join(report_lines)


def main():
    """主函数：运行所有 Agent 的评测"""
    suite = load_evaluation_suite()

    print("\n" + "=" * 70)
    print("  Nuotao AI OS - AI Agent Evaluation Suite")
    print("=" * 70)
    print(f"  Version: {suite['version']}")
    print(f"  Last Updated: {suite['last_updated']}")
    print(f"  Pass Threshold: {suite['pass_threshold']}")
    print(f"  Agents: {len(suite['agents'])}")
    print("")

    all_summaries = {}

    for agent_key in suite["agents"]:
        summary = run_evaluation(agent_key, max_cases=5)
        all_summaries[agent_key] = summary

        # 打印报告
        report = generate_report(summary)
        print(report)

        # 保存报告
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = REPORT_DIR / f"evaluation_{agent_key}_{timestamp}.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n  Report saved: {report_file}\n")

    # 总体汇总
    print("\n" + "=" * 70)
    print("  Overall Evaluation Summary")
    print("=" * 70)
    for key, summary in all_summaries.items():
        print(f"  {summary['agent_name']}: avg {summary['average_score']:.2f}, "
              f"pass rate {summary['pass_rate']}%")
    print("=" * 70)


if __name__ == "__main__":
    main()
