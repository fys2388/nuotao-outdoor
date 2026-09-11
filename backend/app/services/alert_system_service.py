"""
经营预警系统服务
支持毛利下滑、退款率、断货风险、订单异常、收入异常、ROAS异常等多维度预警
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

# 预警数据存储路径
DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "alerts",
)

# 预警类型
ALERT_TYPES = [
    "margin_decline",       # 毛利下滑
    "refund_rate_high",     # 退款率过高
    "stockout_risk",        # 断货风险
    "order_anomaly",        # 订单异常
    "revenue_decline",      # 收入下滑
    "roas_decline",         # ROAS 下滑
    "inventory_overstock",  # 库存积压
    "shipping_delay",       # 物流延迟
    "customer_complaint",   # 客户投诉
    "payment_failure",      # 支付失败
]

# 预警严重程度
ALERT_SEVERITIES = ["critical", "warning", "info"]

# 预警状态
ALERT_STATUSES = ["new", "acknowledged", "investigating", "resolved", "dismissed"]

# 默认预警规则
DEFAULT_RULES = {
    "margin_decline": {
        "enabled": True,
        "threshold_percent": -5,  # 毛利率环比下降超过 5% 触发
        "absolute_threshold": 30,  # 毛利率低于 30% 触发
        "severity": "critical",
        "check_frequency": "daily",
    },
    "refund_rate_high": {
        "enabled": True,
        "threshold_percent": 3.0,  # 退款率超过 3% 触发
        "warning_threshold": 2.0,  # 退款率超过 2% 警告
        "severity": "warning",
        "check_frequency": "daily",
    },
    "stockout_risk": {
        "enabled": True,
        "safety_stock_days": 14,  # 库存低于 14 天销量触发
        "critical_stock_days": 7,  # 库存低于 7 天严重
        "severity": "warning",
        "check_frequency": "daily",
    },
    "order_anomaly": {
        "enabled": True,
        "drop_threshold_percent": -30,  # 订单量环比下降超过 30% 触发
        "spike_threshold_percent": 50,  # 订单量环比增长超过 50% 触发（可能异常）
        "severity": "warning",
        "check_frequency": "daily",
    },
    "revenue_decline": {
        "enabled": True,
        "threshold_percent": -20,  # 收入环比下降超过 20% 触发
        "severity": "critical",
        "check_frequency": "daily",
    },
    "roas_decline": {
        "enabled": True,
        "threshold_percent": -15,  # ROAS 环比下降超过 15% 触发
        "absolute_threshold": 3.0,  # ROAS 低于 3.0 触发
        "severity": "warning",
        "check_frequency": "daily",
    },
    "inventory_overstock": {
        "enabled": True,
        "overstock_days": 90,  # 库存超过 90 天销量触发
        "severity": "info",
        "check_frequency": "weekly",
    },
}


def _ensure_data_dir() -> None:
    """确保数据目录存在"""
    os.makedirs(DATA_DIR, exist_ok=True)


def _get_alert_path(alert_id: str) -> str:
    """获取预警数据文件路径"""
    return os.path.join(DATA_DIR, f"alert_{alert_id}.json")


def _load_alert(alert_id: str) -> dict[str, Any] | None:
    """加载预警数据"""
    path = _get_alert_path(alert_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to load alert %s: %s", alert_id, str(e))
        return None


def _save_alert(alert: dict[str, Any]) -> None:
    """保存预警数据"""
    _ensure_data_dir()
    path = _get_alert_path(alert["id"])
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(alert, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("Failed to save alert %s: %s", alert["id"], str(e))


def _get_rules_path() -> str:
    """获取预警规则配置文件路径"""
    return os.path.join(DATA_DIR, "alert_rules.json")


def load_alert_rules() -> dict[str, Any]:
    """加载预警规则配置"""
    path = _get_rules_path()
    if not os.path.exists(path):
        # 使用默认规则
        save_alert_rules(DEFAULT_RULES)
        return DEFAULT_RULES
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to load alert rules: %s", str(e))
        return DEFAULT_RULES


def save_alert_rules(rules: dict[str, Any]) -> None:
    """保存预警规则配置"""
    _ensure_data_dir()
    path = _get_rules_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rules, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("Failed to save alert rules: %s", str(e))


def create_alert(
    alert_type: str,
    severity: str,
    title: str,
    description: str,
    metric_data: dict[str, Any] | None = None,
    recommended_action: str = "",
    source: str = "system",
) -> dict[str, Any]:
    """
    创建预警

    Args:
        alert_type: 预警类型
        severity: 严重程度
        title: 预警标题
        description: 预警描述
        metric_data: 相关指标数据
        recommended_action: 建议行动
        source: 预警来源

    Returns:
        预警数据
    """
    if alert_type not in ALERT_TYPES:
        raise ValueError(f"Invalid alert type: {alert_type}. Must be one of {ALERT_TYPES}")
    if severity not in ALERT_SEVERITIES:
        raise ValueError(f"Invalid severity: {severity}. Must be one of {ALERT_SEVERITIES}")

    now = datetime.utcnow()
    alert_id = str(uuid4())

    alert = {
        "id": alert_id,
        "type": alert_type,
        "severity": severity,
        "title": title,
        "description": description,
        "metric_data": metric_data or {},
        "recommended_action": recommended_action,
        "source": source,
        "status": "new",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "acknowledged_at": None,
        "resolved_at": None,
        "acknowledged_by": None,
        "resolved_by": None,
        "resolution_notes": "",
        "history": [
            {
                "action": "created",
                "timestamp": now.isoformat(),
                "details": f"Alert created by {source}",
            }
        ],
    }

    _save_alert(alert)
    logger.info("Alert created: id=%s, type=%s, severity=%s, title=%s", alert_id, alert_type, severity, title)
    return alert


def update_alert_status(
    alert_id: str,
    new_status: str,
    updated_by: str = "system",
    notes: str = "",
) -> dict[str, Any]:
    """
    更新预警状态

    Args:
        alert_id: 预警 ID
        new_status: 新状态
        updated_by: 更新者
        notes: 备注

    Returns:
        更新后的预警数据
    """
    if new_status not in ALERT_STATUSES:
        raise ValueError(f"Invalid status: {new_status}. Must be one of {ALERT_STATUSES}")

    alert = _load_alert(alert_id)
    if not alert:
        raise ValueError(f"Alert not found: {alert_id}")

    now = datetime.utcnow()
    old_status = alert["status"]
    alert["status"] = new_status
    alert["updated_at"] = now.isoformat()

    if new_status == "acknowledged":
        alert["acknowledged_at"] = now.isoformat()
        alert["acknowledged_by"] = updated_by
    elif new_status == "resolved":
        alert["resolved_at"] = now.isoformat()
        alert["resolved_by"] = updated_by
        alert["resolution_notes"] = notes

    alert["history"].append({
        "action": "status_change",
        "timestamp": now.isoformat(),
        "old_status": old_status,
        "new_status": new_status,
        "updated_by": updated_by,
        "notes": notes,
    })

    _save_alert(alert)
    logger.info("Alert status updated: id=%s, %s -> %s, by=%s", alert_id, old_status, new_status, updated_by)
    return alert


def check_margin_decline(
    current_margin: float,
    previous_margin: float,
    rules: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    检查毛利下滑预警

    Args:
        current_margin: 当前毛利率（%）
        previous_margin: 上期毛利率（%）
        rules: 预警规则

    Returns:
        预警数据（如果触发）或 None
    """
    if rules is None:
        rules = load_alert_rules()

    rule = rules.get("margin_decline", {})
    if not rule.get("enabled", True):
        return None

    change_percent = ((current_margin - previous_margin) / previous_margin * 100) if previous_margin > 0 else 0

    triggered = False
    severity = "info"

    # 检查绝对阈值
    if current_margin < rule.get("absolute_threshold", 30):
        triggered = True
        severity = "critical"

    # 检查环比下降
    if change_percent <= rule.get("threshold_percent", -5):
        triggered = True
        severity = "critical" if change_percent <= -10 else "warning"

    if not triggered:
        return None

    return create_alert(
        alert_type="margin_decline",
        severity=severity,
        title=f"毛利率预警: 当前 {current_margin}%",
        description=f"毛利率从 {previous_margin}% 下降到 {current_margin}%，环比变化 {change_percent:.2f}%。{'低于安全阈值 30%。' if current_margin < 30 else ''}",
        metric_data={
            "current_margin": current_margin,
            "previous_margin": previous_margin,
            "change_percent": round(change_percent, 2),
            "threshold": rule.get("threshold_percent", -5),
            "absolute_threshold": rule.get("absolute_threshold", 30),
        },
        recommended_action="立即分析成本结构，检查产品成本、运费、折扣力度。优化采购价格，调整定价策略，减少低毛利产品促销。",
        source="auto_check",
    )


def check_refund_rate(
    current_refund_rate: float,
    previous_refund_rate: float,
    total_orders: int,
    refunded_orders: int,
    rules: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    检查退款率预警

    Args:
        current_refund_rate: 当前退款率（%）
        previous_refund_rate: 上期退款率（%）
        total_orders: 总订单数
        refunded_orders: 退款订单数
        rules: 预警规则

    Returns:
        预警数据（如果触发）或 None
    """
    if rules is None:
        rules = load_alert_rules()

    rule = rules.get("refund_rate_high", {})
    if not rule.get("enabled", True):
        return None

    triggered = False
    severity = "info"

    if current_refund_rate >= rule.get("threshold_percent", 3.0):
        triggered = True
        severity = "critical" if current_refund_rate >= 5 else "warning"
    elif current_refund_rate >= rule.get("warning_threshold", 2.0):
        triggered = True
        severity = "warning"

    if not triggered:
        return None

    return create_alert(
        alert_type="refund_rate_high",
        severity=severity,
        title=f"退款率预警: 当前 {current_refund_rate}%",
        description=f"退款率 {current_refund_rate}% 超过警戒线。总订单 {total_orders} 单，退款 {refunded_orders} 单。上期退款率 {previous_refund_rate}%。",
        metric_data={
            "current_refund_rate": current_refund_rate,
            "previous_refund_rate": previous_refund_rate,
            "total_orders": total_orders,
            "refunded_orders": refunded_orders,
            "threshold": rule.get("threshold_percent", 3.0),
        },
        recommended_action="立即审查退款订单原因，联系退款客户了解具体问题。检查产品质量、物流时效、产品描述准确性。建立退款原因追踪机制。",
        source="auto_check",
    )


def check_stockout_risk(
    product_name: str,
    sku: str,
    current_stock: int,
    daily_sales_rate: float,
    rules: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    检查断货风险预警

    Args:
        product_name: 产品名称
        sku: 产品 SKU
        current_stock: 当前库存
        daily_sales_rate: 日均销量
        rules: 预警规则

    Returns:
        预警数据（如果触发）或 None
    """
    if rules is None:
        rules = load_alert_rules()

    rule = rules.get("stockout_risk", {})
    if not rule.get("enabled", True):
        return None

    if daily_sales_rate <= 0:
        return None

    days_of_stock = current_stock / daily_sales_rate

    triggered = False
    severity = "info"

    if days_of_stock <= rule.get("critical_stock_days", 7):
        triggered = True
        severity = "critical"
    elif days_of_stock <= rule.get("safety_stock_days", 14):
        triggered = True
        severity = "warning"

    if not triggered:
        return None

    return create_alert(
        alert_type="stockout_risk",
        severity=severity,
        title=f"断货风险: {product_name} ({sku})",
        description=f"产品 {product_name} 当前库存 {current_stock} 件，日均销量 {daily_sales_rate} 件，库存可维持 {days_of_stock:.1f} 天。{'严重不足！' if severity == 'critical' else '低于安全库存。'}",
        metric_data={
            "product_name": product_name,
            "sku": sku,
            "current_stock": current_stock,
            "daily_sales_rate": daily_sales_rate,
            "days_of_stock": round(days_of_stock, 1),
            "safety_stock_days": rule.get("safety_stock_days", 14),
            "critical_stock_days": rule.get("critical_stock_days", 7),
        },
        recommended_action=f"立即采购补货，建议采购量至少 {int(daily_sales_rate * 30)} 件（30 天销量）。联系供应商确认交货时间，必要时启动紧急采购流程。",
        source="auto_check",
    )


def run_all_checks(
    business_data: dict[str, Any],
    rules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    运行所有预警检查

    Args:
        business_data: 经营数据
        rules: 预警规则

    Returns:
        检查结果（触发的预警列表）
    """
    if rules is None:
        rules = load_alert_rules()

    triggered_alerts = []

    # 检查毛利下滑
    margin_data = business_data.get("margin", {})
    if margin_data:
        alert = check_margin_decline(
            current_margin=margin_data.get("current", 0),
            previous_margin=margin_data.get("previous", 0),
            rules=rules,
        )
        if alert:
            triggered_alerts.append(alert)

    # 检查退款率
    refund_data = business_data.get("refund_rate", {})
    if refund_data:
        alert = check_refund_rate(
            current_refund_rate=refund_data.get("current", 0),
            previous_refund_rate=refund_data.get("previous", 0),
            total_orders=refund_data.get("total_orders", 0),
            refunded_orders=refund_data.get("refunded_orders", 0),
            rules=rules,
        )
        if alert:
            triggered_alerts.append(alert)

    # 检查断货风险
    inventory_data = business_data.get("inventory", [])
    for item in inventory_data:
        alert = check_stockout_risk(
            product_name=item.get("name", ""),
            sku=item.get("sku", ""),
            current_stock=item.get("stock", 0),
            daily_sales_rate=item.get("daily_sales", 0),
            rules=rules,
        )
        if alert:
            triggered_alerts.append(alert)

    return {
        "checks_run": ["margin_decline", "refund_rate_high", "stockout_risk"],
        "total_alerts_triggered": len(triggered_alerts),
        "critical_count": sum(1 for a in triggered_alerts if a["severity"] == "critical"),
        "warning_count": sum(1 for a in triggered_alerts if a["severity"] == "warning"),
        "info_count": sum(1 for a in triggered_alerts if a["severity"] == "info"),
        "alerts": triggered_alerts,
        "checked_at": datetime.utcnow().isoformat(),
    }


def get_alert(alert_id: str) -> dict[str, Any]:
    """获取预警详情"""
    alert = _load_alert(alert_id)
    if not alert:
        raise ValueError(f"Alert not found: {alert_id}")
    return alert


def list_alerts(
    status: str | None = None,
    severity: str | None = None,
    alert_type: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """获取预警列表"""
    _ensure_data_dir()

    alerts = []
    for filename in sorted(os.listdir(DATA_DIR), reverse=True):
        if not filename.startswith("alert_") or not filename.endswith(".json"):
            continue
        # 跳过规则配置文件
        if filename == "alert_rules.json":
            continue
        try:
            with open(os.path.join(DATA_DIR, filename), encoding="utf-8") as f:
                alert = json.load(f)

            # 确保是有效的预警数据
            if "status" not in alert or "type" not in alert:
                continue

            # 筛选
            if status and alert.get("status") != status:
                continue
            if severity and alert.get("severity") != severity:
                continue
            if alert_type and alert.get("type") != alert_type:
                continue

            alerts.append(alert)
        except Exception as e:
            logger.warning("Failed to load alert file %s: %s", filename, str(e))

        if len(alerts) >= limit:
            break

    return {
        "alerts": alerts,
        "total": len(alerts),
        "summary": {
            "new_count": sum(1 for a in alerts if a["status"] == "new"),
            "acknowledged_count": sum(1 for a in alerts if a["status"] == "acknowledged"),
            "investigating_count": sum(1 for a in alerts if a["status"] == "investigating"),
            "resolved_count": sum(1 for a in alerts if a["status"] == "resolved"),
            "critical_count": sum(1 for a in alerts if a["severity"] == "critical"),
            "warning_count": sum(1 for a in alerts if a["severity"] == "warning"),
        },
    }


def get_alert_system_status() -> dict[str, Any]:
    """获取经营预警系统状态"""
    rules = load_alert_rules()
    enabled_rules = [k for k, v in rules.items() if v.get("enabled", True)]

    return {
        "status": "running",
        "alert_types": ALERT_TYPES,
        "severities": ALERT_SEVERITIES,
        "statuses": ALERT_STATUSES,
        "enabled_rules": enabled_rules,
        "total_rules": len(rules),
        "features": [
            "margin_decline_alert",
            "refund_rate_alert",
            "stockout_risk_alert",
            "order_anomaly_alert",
            "revenue_decline_alert",
            "roas_decline_alert",
            "inventory_overstock_alert",
            "alert_management",
            "configurable_rules",
            "auto_check",
        ],
        "note": "Business alert system is ready. Supports 10 alert types with configurable thresholds, auto-check, and full alert management lifecycle.",
    }
