"""
自动化选品实验服务
支持自动启动 AB 实验、实验跟踪、效果评估、自动决策（上架/拒绝/继续）
实验流程：候选产品 → 小批量上架 → 数据跟踪 → 效果评估 → 决策
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000001")

# 实验配置默认值
DEFAULT_EXPERIMENT_DAYS = 14
DEFAULT_MIN_SAMPLE_SIZE = 50  # 最小样本量（访问量）
DEFAULT_CONFIDENCE_THRESHOLD = 0.80  # 置信度阈值
DEFAULT_SUCCESS_METRICS = {
    "min_conversion_rate": 0.02,  # 最小转化率 2%
    "min_ctr": 0.05,  # 最小点击率 5%
    "max_return_rate": 0.10,  # 最大退货率 10%
    "min_profit_margin": 0.40,  # 最小利润率 40%
}


def create_experiment(
    product_id: str,
    product_name: str,
    variant_a: dict[str, Any] | None = None,
    variant_b: dict[str, Any] | None = None,
    experiment_days: int = DEFAULT_EXPERIMENT_DAYS,
    hypothesis: str | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    创建选品实验

    Args:
        product_id: 产品 ID
        product_name: 产品名称
        variant_a: A 变体配置（价格/标题/图片等）
        variant_b: B 变体配置
        experiment_days: 实验天数
        hypothesis: 实验假设
        metrics: 成功指标配置

    Returns:
        实验配置
    """
    experiment_id = str(uuid4())
    now = datetime.utcnow()
    end_date = now + timedelta(days=experiment_days)

    # 默认变体
    if variant_a is None:
        variant_a = {"name": "control", "price_multiplier": 1.0, "title": product_name}
    if variant_b is None:
        variant_b = {"name": "treatment", "price_multiplier": 0.9, "title": f"{product_name} - Special Offer"}

    success_metrics = {**DEFAULT_SUCCESS_METRICS, **(metrics or {})}

    experiment = {
        "experiment_id": experiment_id,
        "product_id": product_id,
        "product_name": product_name,
        "status": "created",
        "hypothesis": hypothesis or f"测试 {product_name} 的市场接受度，变体B（降价10%）是否优于变体A",
        "created_at": now.isoformat(),
        "start_date": now.isoformat(),
        "end_date": end_date.isoformat(),
        "experiment_days": experiment_days,
        "variants": {
            "A": {**variant_a, "traffic_allocation": 0.5, "data": _empty_variant_data()},
            "B": {**variant_b, "traffic_allocation": 0.5, "data": _empty_variant_data()},
        },
        "success_metrics": success_metrics,
        "min_sample_size": DEFAULT_MIN_SAMPLE_SIZE,
        "confidence_threshold": DEFAULT_CONFIDENCE_THRESHOLD,
        "decisions_log": [],
    }

    logger.info("Experiment created: id=%s, product=%s, days=%d", experiment_id, product_name, experiment_days)
    return experiment


def start_experiment(experiment: dict[str, Any]) -> dict[str, Any]:
    """
    启动实验（状态从 created → running）

    Args:
        experiment: 实验配置

    Returns:
        更新后的实验
    """
    if experiment.get("status") != "created":
        return {"error": f"实验状态为 {experiment.get('status')}，无法启动", "experiment": experiment}

    experiment["status"] = "running"
    experiment["started_at"] = datetime.utcnow().isoformat()
    experiment["decisions_log"].append({
        "timestamp": datetime.utcnow().isoformat(),
        "action": "start",
        "note": "实验启动，开始收集数据",
    })

    logger.info("Experiment started: id=%s", experiment["experiment_id"])
    return experiment


def record_experiment_data(
    experiment: dict[str, Any],
    variant: str,
    impressions: int = 0,
    clicks: int = 0,
    conversions: int = 0,
    revenue: float = 0,
    returns: int = 0,
) -> dict[str, Any]:
    """
    记录实验数据

    Args:
        experiment: 实验配置
        variant: 变体标识（A/B）
        impressions: 曝光量
        clicks: 点击量
        conversions: 转化量
        revenue: 收入
        returns: 退货量

    Returns:
        更新后的实验
    """
    if variant not in experiment.get("variants", {}):
        return {"error": f"无效变体: {variant}", "experiment": experiment}

    data = experiment["variants"][variant]["data"]
    data["impressions"] += impressions
    data["clicks"] += clicks
    data["conversions"] += conversions
    data["revenue"] += revenue
    data["returns"] += returns
    data["last_updated"] = datetime.utcnow().isoformat()

    return experiment


def evaluate_experiment(experiment: dict[str, Any]) -> dict[str, Any]:
    """
    评估实验结果

    Args:
        experiment: 实验配置

    Returns:
        评估报告
    """
    if experiment.get("status") not in ("running", "completed"):
        return {"error": f"实验状态为 {experiment.get('status')}，无法评估", "experiment": experiment}

    variant_a = experiment["variants"]["A"]["data"]
    variant_b = experiment["variants"]["B"]["data"]

    # 计算各变体指标
    metrics_a = _calculate_variant_metrics(variant_a)
    metrics_b = _calculate_variant_metrics(variant_b)

    # 统计显著性检验（Z检验简化版）
    significance = _statistical_significance(metrics_a, metrics_b)

    # 判断成功指标
    success_check = _check_success_metrics(metrics_a, metrics_b, experiment.get("success_metrics", {}))

    # 样本量检查
    sample_check = _check_sample_size(variant_a, variant_b, experiment.get("min_sample_size", DEFAULT_MIN_SAMPLE_SIZE))

    # 综合决策
    decision = _make_decision(metrics_a, metrics_b, significance, success_check, sample_check, experiment)

    # 置信度
    confidence = _calculate_confidence(significance, success_check, sample_check)

    evaluation = {
        "evaluated_at": datetime.utcnow().isoformat(),
        "experiment_id": experiment["experiment_id"],
        "product_name": experiment["product_name"],
        "status": experiment["status"],
        "variant_a_metrics": metrics_a,
        "variant_b_metrics": metrics_b,
        "significance": significance,
        "success_check": success_check,
        "sample_check": sample_check,
        "decision": decision,
        "confidence": round(confidence, 3),
        "recommendation": _get_recommendation(decision, confidence),
    }

    experiment["last_evaluation"] = evaluation
    experiment["decisions_log"].append({
        "timestamp": datetime.utcnow().isoformat(),
        "action": "evaluate",
        "decision": decision,
        "confidence": confidence,
    })

    return evaluation


def auto_manage_experiment(experiment: dict[str, Any]) -> dict[str, Any]:
    """
    自动化实验管理
    检查实验状态，自动执行：启动 → 数据收集 → 评估 → 决策 → 结束

    Args:
        experiment: 实验配置

    Returns:
        管理结果
    """
    status = experiment.get("status")
    now = datetime.utcnow()

    # 自动启动
    if status == "created":
        experiment = start_experiment(experiment)
        return {"action": "auto_start", "experiment": experiment, "message": "实验已自动启动"}

    # 检查是否到期
    if status == "running":
        end_date = datetime.fromisoformat(experiment["end_date"].replace("Z", "+00:00").replace("+00:00", "")) if "end_date" in experiment else None
        if end_date and now >= end_date:
            # 实验到期，自动评估并结束
            evaluation = evaluate_experiment(experiment)
            experiment["status"] = "completed"
            experiment["completed_at"] = now.isoformat()
            experiment["final_decision"] = evaluation["decision"]
            experiment["decisions_log"].append({
                "timestamp": now.isoformat(),
                "action": "auto_complete",
                "decision": evaluation["decision"],
                "confidence": evaluation["confidence"],
            })
            return {
                "action": "auto_complete",
                "experiment": experiment,
                "evaluation": evaluation,
                "message": f"实验已到期，自动评估完成，决策: {evaluation['decision']}",
            }

        # 未到期，检查是否可以提前决策（样本量足够且显著性高）
        evaluation = evaluate_experiment(experiment)
        if evaluation["confidence"] >= 0.90 and evaluation["sample_check"]["sufficient"]:
            # 高置信度提前结束
            experiment["status"] = "completed"
            experiment["completed_at"] = now.isoformat()
            experiment["final_decision"] = evaluation["decision"]
            experiment["early_termination"] = True
            experiment["decisions_log"].append({
                "timestamp": now.isoformat(),
                "action": "early_termination",
                "decision": evaluation["decision"],
                "confidence": evaluation["confidence"],
                "reason": "高置信度提前终止",
            })
            return {
                "action": "early_termination",
                "experiment": experiment,
                "evaluation": evaluation,
                "message": f"高置信度({evaluation['confidence']:.1%})提前终止实验，决策: {evaluation['decision']}",
            }

        return {
            "action": "continue_running",
            "experiment": experiment,
            "evaluation": evaluation,
            "message": f"实验进行中，置信度 {evaluation['confidence']:.1%}，继续收集数据",
        }

    return {"action": "no_op", "experiment": experiment, "message": f"实验状态 {status}，无需操作"}


def list_active_experiments(experiments: list[dict[str, Any]]) -> dict[str, Any]:
    """列出活跃实验"""
    active = [e for e in experiments if e.get("status") == "running"]
    pending = [e for e in experiments if e.get("status") == "created"]
    completed = [e for e in experiments if e.get("status") == "completed"]

    return {
        "total": len(experiments),
        "active": len(active),
        "pending": len(pending),
        "completed": len(completed),
        "active_experiments": [
            {"id": e["experiment_id"], "product": e["product_name"], "days_remaining": _days_remaining(e)}
            for e in active
        ],
    }


# ============================================
# 内部工具函数
# ============================================

def _empty_variant_data() -> dict[str, Any]:
    return {
        "impressions": 0,
        "clicks": 0,
        "conversions": 0,
        "revenue": 0.0,
        "returns": 0,
        "last_updated": None,
    }


def _calculate_variant_metrics(data: dict[str, Any]) -> dict[str, Any]:
    """计算变体指标"""
    impressions = data.get("impressions", 0)
    clicks = data.get("clicks", 0)
    conversions = data.get("conversions", 0)
    revenue = data.get("revenue", 0)
    returns = data.get("returns", 0)

    ctr = clicks / impressions if impressions else 0
    conversion_rate = conversions / clicks if clicks else 0
    overall_conversion = conversions / impressions if impressions else 0
    avg_order_value = revenue / conversions if conversions else 0
    return_rate = returns / conversions if conversions else 0
    profit = revenue * 0.5  # 简化：假设50%利润率

    return {
        "impressions": impressions,
        "clicks": clicks,
        "conversions": conversions,
        "revenue": round(revenue, 2),
        "returns": returns,
        "ctr": round(ctr, 4),
        "click_conversion_rate": round(conversion_rate, 4),
        "overall_conversion_rate": round(overall_conversion, 4),
        "avg_order_value": round(avg_order_value, 2),
        "return_rate": round(return_rate, 4),
        "estimated_profit": round(profit, 2),
    }


def _statistical_significance(metrics_a: dict[str, Any], metrics_b: dict[str, Any]) -> dict[str, Any]:
    """统计显著性检验（转化率Z检验简化版）"""
    conv_a = metrics_a["overall_conversion_rate"]
    conv_b = metrics_b["overall_conversion_rate"]
    n_a = metrics_a["impressions"]
    n_b = metrics_b["impressions"]

    if n_a == 0 or n_b == 0:
        return {"significant": False, "z_score": 0, "p_value": 1.0, "note": "样本量不足"}

    # 合并转化率
    pooled_conv = (conv_a * n_a + conv_b * n_b) / (n_a + n_b)
    if pooled_conv == 0 or pooled_conv == 1:
        return {"significant": False, "z_score": 0, "p_value": 1.0, "note": "转化率极端值"}

    # 标准误
    se = math.sqrt(pooled_conv * (1 - pooled_conv) * (1 / n_a + 1 / n_b))
    if se == 0:
        return {"significant": False, "z_score": 0, "p_value": 1.0, "note": "标准误为0"}

    z_score = (conv_b - conv_a) / se
    # 简化p值计算（正态分布近似）
    p_value = 2 * (1 - _normal_cdf(abs(z_score)))

    significant = p_value < 0.05

    return {
        "significant": significant,
        "z_score": round(z_score, 3),
        "p_value": round(p_value, 4),
        "alpha": 0.05,
        "better_variant": "B" if conv_b > conv_a else "A",
        "conv_diff_pct": round((conv_b - conv_a) * 100, 2),
    }


def _normal_cdf(x: float) -> float:
    """标准正态分布CDF（近似）"""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _check_success_metrics(metrics_a: dict[str, Any], metrics_b: dict[str, Any], thresholds: dict[str, Any]) -> dict[str, Any]:
    """检查成功指标"""
    # 取两个变体中较好的指标
    best_conv = max(metrics_a["overall_conversion_rate"], metrics_b["overall_conversion_rate"])
    best_ctr = max(metrics_a["ctr"], metrics_b["ctr"])
    best_return = min(metrics_a["return_rate"], metrics_b["return_rate"])
    best_profit = max(metrics_a["estimated_profit"], metrics_b["estimated_profit"])
    best_revenue = max(metrics_a["revenue"], metrics_b["revenue"])
    profit_margin = best_profit / best_revenue if best_revenue else 0

    checks = {
        "conversion_rate": {"value": best_conv, "threshold": thresholds.get("min_conversion_rate", 0.02), "pass": best_conv >= thresholds.get("min_conversion_rate", 0.02)},
        "ctr": {"value": best_ctr, "threshold": thresholds.get("min_ctr", 0.05), "pass": best_ctr >= thresholds.get("min_ctr", 0.05)},
        "return_rate": {"value": best_return, "threshold": thresholds.get("max_return_rate", 0.10), "pass": best_return <= thresholds.get("max_return_rate", 0.10)},
        "profit_margin": {"value": round(profit_margin, 4), "threshold": thresholds.get("min_profit_margin", 0.40), "pass": profit_margin >= thresholds.get("min_profit_margin", 0.40)},
    }

    all_pass = all(c["pass"] for c in checks.values())
    return {"all_pass": all_pass, "checks": checks, "passed_count": sum(1 for c in checks.values() if c["pass"]), "total_count": len(checks)}


def _check_sample_size(variant_a: dict[str, Any], variant_b: dict[str, Any], min_size: int) -> dict[str, Any]:
    """检查样本量"""
    total_impressions = variant_a.get("impressions", 0) + variant_b.get("impressions", 0)
    sufficient = total_impressions >= min_size * 2
    return {
        "sufficient": sufficient,
        "total_impressions": total_impressions,
        "required": min_size * 2,
        "progress_pct": round(total_impressions / (min_size * 2) * 100, 1) if min_size else 0,
    }


def _make_decision(
    metrics_a: dict[str, Any],
    metrics_b: dict[str, Any],
    significance: dict[str, Any],
    success_check: dict[str, Any],
    sample_check: dict[str, Any],
    experiment: dict[str, Any],
) -> str:
    """综合决策"""
    # 样本量不足 → 继续实验
    if not sample_check["sufficient"]:
        return "continue_experiment"

    # 成功指标全不通过 → 拒绝
    if success_check["passed_count"] <= 1:
        return "reject"

    # 统计显著且B更优 → 上架B
    if significance["significant"] and significance["better_variant"] == "B":
        return "approve_variant_b"

    # 统计显著且A更优 → 上架A
    if significance["significant"] and significance["better_variant"] == "A":
        return "approve_variant_a"

    # 成功指标大部分通过但不显著 → 小批量上架
    if success_check["all_pass"] and not significance["significant"]:
        return "approve_small_batch"

    # 部分通过 → 继续观察
    if success_check["passed_count"] >= 2:
        return "continue_experiment"

    return "reject"


def _calculate_confidence(significance: dict[str, Any], success_check: dict[str, Any], sample_check: dict[str, Any]) -> float:
    """计算决策置信度"""
    confidence = 0.0

    # 样本量贡献（30%）
    if sample_check["sufficient"]:
        confidence += 0.30
    else:
        confidence += 0.30 * min(1.0, sample_check.get("progress_pct", 0) / 100)

    # 统计显著性贡献（30%）
    if significance["significant"]:
        confidence += 0.30
    elif significance.get("p_value", 1.0) < 0.15:
        confidence += 0.15

    # 成功指标贡献（40%）
    confidence += 0.40 * (success_check.get("passed_count", 0) / success_check.get("total_count", 1))

    return min(1.0, confidence)


def _get_recommendation(decision: str, confidence: float) -> str:
    """获取决策建议文案"""
    recommendations = {
        "approve_variant_a": f"变体A表现更优（置信度{confidence:.0%}），建议正式上架变体A",
        "approve_variant_b": f"变体B表现更优（置信度{confidence:.0%}），建议正式上架变体B",
        "approve_small_batch": f"指标达标但差异不显著（置信度{confidence:.0%}），建议小批量试销后再决策",
        "continue_experiment": f"数据不足或差异不显著（置信度{confidence:.0%}），建议继续实验收集更多数据",
        "reject": f"关键指标未达标（置信度{confidence:.0%}），建议拒绝该产品，重新选品",
    }
    return recommendations.get(decision, f"决策: {decision}（置信度{confidence:.0%}）")


def _days_remaining(experiment: dict[str, Any]) -> int:
    """计算剩余天数"""
    try:
        end = datetime.fromisoformat(experiment["end_date"].replace("Z", ""))
        remaining = (end - datetime.utcnow()).days
        return max(0, remaining)
    except Exception:
        return 0
