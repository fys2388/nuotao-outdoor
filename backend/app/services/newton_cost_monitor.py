"""
阿里牛顿API成本监控服务
功能：
- 每日用量统计（调用次数、积分消耗、token使用）
- 额度告警（用量超过阈值时告警）
- 成本估算（积分换算）
- 用量趋势分析
- 监控报告生成
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any

from app.services.newton_agent_service import query_points, is_configured

logger = logging.getLogger(__name__)

# 监控配置
DAILY_LIMIT = 5000  # 每日调用额度
ALERT_THRESHOLD_80 = 0.80  # 80%告警阈值
ALERT_THRESHOLD_90 = 0.90  # 90%严重告警阈值
COST_PER_CREDIT = 0.001  # 每积分估算成本（元，可配置）

# 用量记录文件
USAGE_LOG_FILE = "data/newton_usage_log.json"


def load_usage_log() -> list[dict[str, Any]]:
    """加载用量记录"""
    if os.path.exists(USAGE_LOG_FILE):
        with open(USAGE_LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_usage_log(records: list[dict[str, Any]]):
    """保存用量记录"""
    os.makedirs(os.path.dirname(USAGE_LOG_FILE), exist_ok=True)
    with open(USAGE_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def log_api_call(
    api_name: str,
    task_id: str = "",
    credits_consumed: float = 0,
    tokens_used: int = 0,
    success: bool = True,
    error: str = "",
):
    """
    记录一次API调用

    Args:
        api_name: API名称（如task.create、task.get、search等）
        task_id: 任务ID
        credits_consumed: 积分消耗
        tokens_used: token使用量
        success: 是否成功
        error: 错误信息
    """
    records = load_usage_log()
    record = {
        "timestamp": datetime.now().isoformat(),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "api_name": api_name,
        "task_id": task_id,
        "credits_consumed": credits_consumed,
        "tokens_used": tokens_used,
        "success": success,
        "error": error,
    }
    records.append(record)
    # 只保留最近30天的记录
    cutoff = (datetime.now() - timedelta(days=30)).isoformat()
    records = [r for r in records if r["timestamp"] >= cutoff]
    save_usage_log(records)


def get_daily_usage(date: str = None) -> dict[str, Any]:
    """
    获取指定日期的用量统计

    Args:
        date: 日期（YYYY-MM-DD），默认为今天

    Returns:
        用量统计
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    records = load_usage_log()
    daily_records = [r for r in records if r.get("date") == date]

    total_calls = len(daily_records)
    success_calls = len([r for r in daily_records if r.get("success")])
    failed_calls = total_calls - success_calls
    total_credits = sum(r.get("credits_consumed", 0) for r in daily_records)
    total_tokens = sum(r.get("tokens_used", 0) for r in daily_records)

    # 按API分组统计
    api_stats = {}
    for r in daily_records:
        api = r.get("api_name", "unknown")
        if api not in api_stats:
            api_stats[api] = {"calls": 0, "credits": 0, "tokens": 0}
        api_stats[api]["calls"] += 1
        api_stats[api]["credits"] += r.get("credits_consumed", 0)
        api_stats[api]["tokens"] += r.get("tokens_used", 0)

    usage_percent = (total_calls / DAILY_LIMIT * 100) if DAILY_LIMIT > 0 else 0

    return {
        "date": date,
        "total_calls": total_calls,
        "success_calls": success_calls,
        "failed_calls": failed_calls,
        "success_rate": (success_calls / total_calls * 100) if total_calls > 0 else 0,
        "total_credits": round(total_credits, 2),
        "total_tokens": total_tokens,
        "daily_limit": DAILY_LIMIT,
        "usage_percent": round(usage_percent, 2),
        "remaining_calls": max(0, DAILY_LIMIT - total_calls),
        "estimated_cost": round(total_credits * COST_PER_CREDIT, 4),
        "api_stats": api_stats,
    }


def get_weekly_usage() -> dict[str, Any]:
    """获取最近7天的用量趋势"""
    daily_stats = []
    for i in range(6, -1, -1):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        stats = get_daily_usage(date)
        daily_stats.append({
            "date": date,
            "calls": stats["total_calls"],
            "credits": stats["total_credits"],
            "tokens": stats["total_tokens"],
        })

    total_calls = sum(d["calls"] for d in daily_stats)
    total_credits = sum(d["credits"] for d in daily_stats)
    avg_daily_calls = total_calls / 7 if total_calls > 0 else 0

    return {
        "period": "7天",
        "total_calls": total_calls,
        "total_credits": round(total_credits, 2),
        "avg_daily_calls": round(avg_daily_calls, 1),
        "estimated_cost": round(total_credits * COST_PER_CREDIT, 4),
        "daily_stats": daily_stats,
    }


def check_alerts() -> dict[str, Any]:
    """
    检查额度告警

    Returns:
        告警信息
    """
    daily = get_daily_usage()
    alerts = []

    usage_percent = daily["usage_percent"]

    if usage_percent >= ALERT_THRESHOLD_90 * 100:
        alerts.append({
            "level": "critical",
            "message": f"今日API用量已达{usage_percent}%（{daily['total_calls']}/{DAILY_LIMIT}），即将耗尽！",
            "action": "建议立即降低调用频率或申请额度提升",
        })
    elif usage_percent >= ALERT_THRESHOLD_80 * 100:
        alerts.append({
            "level": "warning",
            "message": f"今日API用量已达{usage_percent}%（{daily['total_calls']}/{DAILY_LIMIT}），请注意控制",
            "action": "建议监控剩余额度，避免超限",
        })

    # 检查失败率
    if daily["total_calls"] > 10 and daily["success_rate"] < 80:
        alerts.append({
            "level": "warning",
            "message": f"今日API成功率仅{daily['success_rate']:.1f}%，低于80%阈值",
            "action": "建议检查API调用是否有异常",
        })

    return {
        "has_alerts": len(alerts) > 0,
        "alerts": alerts,
        "daily_usage": daily,
    }


def get_remote_credits() -> dict[str, Any]:
    """
    从牛顿API获取远程积分详情

    Returns:
        积分信息
    """
    if not is_configured():
        return {"success": False, "error": "未配置API凭证"}

    try:
        result = query_points()
        if not result.get("success"):
            return {"success": False, "error": result.get("error", "查询积分失败")}

        raw = result.get("raw", {})
        records = raw.get("records", [])

        # 统计远程积分消耗
        total_credits_consumed = sum(r.get("creditsConsumed", 0) for r in records)
        total_tokens = sum(r.get("totalTokens", 0) for r in records)

        return {
            "success": True,
            "available_credits": raw.get("availableCredits", 0),
            "total_sessions": raw.get("total", 0),
            "total_credits_consumed": round(total_credits_consumed, 2),
            "total_tokens": total_tokens,
            "estimated_cost": round(total_credits_consumed * COST_PER_CREDIT, 4),
            "recent_sessions": [
                {
                    "session_id": r.get("sessionId"),
                    "name": r.get("sessionName", "")[:50],
                    "credits": r.get("creditsConsumed", 0),
                    "tokens": r.get("totalTokens", 0),
                }
                for r in records[:5]
            ],
        }
    except Exception as e:
        logger.error("Get remote credits failed: %s", str(e))
        return {"success": False, "error": str(e)}


def generate_monitor_report() -> dict[str, Any]:
    """
    生成完整的成本监控报告

    Returns:
        监控报告
    """
    daily = get_daily_usage()
    weekly = get_weekly_usage()
    alerts = check_alerts()
    remote = get_remote_credits()

    report = {
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "daily_calls": daily["total_calls"],
            "daily_limit": DAILY_LIMIT,
            "usage_percent": daily["usage_percent"],
            "remaining_calls": daily["remaining_calls"],
            "daily_credits": daily["total_credits"],
            "weekly_calls": weekly["total_calls"],
            "weekly_credits": weekly["total_credits"],
            "estimated_monthly_cost": round(weekly["total_credits"] * 4.3 * COST_PER_CREDIT, 2),
        },
        "daily_usage": daily,
        "weekly_usage": weekly,
        "alerts": alerts,
        "remote_credits": remote,
    }

    return report


def print_monitor_report():
    """打印监控报告到控制台"""
    report = generate_monitor_report()

    print("=" * 70)
    print("阿里牛顿API成本监控报告")
    print(f"生成时间: {report['generated_at'][:19]}")
    print("=" * 70)

    s = report["summary"]
    print(f"\n【今日用量】")
    print(f"  调用次数: {s['daily_calls']}/{s['daily_limit']} ({s['usage_percent']}%)")
    print(f"  剩余额度: {s['remaining_calls']}次")
    print(f"  积分消耗: {s['daily_credits']}")
    print(f"  估算成本: ¥{s['estimated_monthly_cost']}/月")

    print(f"\n【7天趋势】")
    print(f"  总调用: {s['weekly_calls']}次")
    print(f"  总积分: {s['weekly_credits']}")
    for d in report["weekly_usage"]["daily_stats"]:
        bar = "█" * int(d["calls"] / 10) if d["calls"] > 0 else ""
        print(f"  {d['date']}: {d['calls']:4d}次 {bar}")

    print(f"\n【告警状态】")
    if report["alerts"]["has_alerts"]:
        for a in report["alerts"]["alerts"]:
            level_icon = "🔴" if a["level"] == "critical" else "🟡"
            print(f"  {level_icon} [{a['level'].upper()}] {a['message']}")
            print(f"     建议: {a['action']}")
    else:
        print(f"  🟢 正常，无告警")

    print(f"\n【远程积分】")
    rc = report["remote_credits"]
    if rc.get("success"):
        print(f"  可用积分: {rc['available_credits']}")
        print(f"  总会话: {rc['total_sessions']}")
        print(f"  已消耗积分: {rc['total_credits_consumed']}")
        print(f"  总Token: {rc['total_tokens']}")
        print(f"  最近会话:")
        for s in rc.get("recent_sessions", []):
            print(f"    - {s['name'][:40]}... (积分:{s['credits']}, Token:{s['tokens']})")
    else:
        print(f"  查询失败: {rc.get('error')}")

    print("\n" + "=" * 70)
    return report


if __name__ == "__main__":
    print_monitor_report()
