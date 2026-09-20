"""Unified operating dashboard backed only by persisted business data."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any


def _calculate_trend(current: float, previous: float) -> dict[str, Any]:
    """Calculate a period-over-period trend."""
    change_percent = (
        (100 if current > 0 else 0)
        if previous == 0
        else (current - previous) / previous * 100
    )

    direction = "up" if change_percent > 0 else "down" if change_percent < 0 else "flat"

    return {
        "current": round(current, 2),
        "previous": round(previous, 2),
        "change": round(current - previous, 2),
        "change_percent": round(change_percent, 2),
        "direction": direction,
    }


def get_dashboard_status() -> dict[str, Any]:
    """获取经营看板系统状态"""
    return {
        "status": "running",
        "features": [
            "revenue_tracking",
            "gross_margin_analysis",
            "cost_coverage",
            "refund_tracking",
            "marketing_roas",
            "trend_analysis",
        ],
        "data_frequency": "database_query",
        "metrics_tracked": [
            "total_orders",
            "total_revenue",
            "gross_profit",
            "gross_margin",
            "avg_order_value",
            "refund_rate",
            "ad_spend",
            "roas",
            "roi",
            "new_customers",
            "returning_customers",
            "new_customer_rate",
        ],
        "data_source": "orders_database",
        "note": "Dashboard values come from persisted orders and cost snapshots; missing evidence is reported as missing.",
    }


# ============================================
# Persisted order aggregation
# ============================================

async def get_dashboard_summary_real(
    session,
    workspace_id,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Aggregate the dashboard from persisted orders and cost snapshots."""
    from sqlalchemy import and_, func, select

    from app.models.order import Order

    now = datetime.utcnow()

    if start_date is None:
        start_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    if end_date is None:
        end_date = now.strftime("%Y-%m-%d")

    async def _calc_period(date_from: datetime, date_to: datetime) -> dict[str, Any]:
        """Calculate order metrics for one period."""
        result = await session.execute(
            select(
                func.count(Order.id).label("total_orders"),
                func.coalesce(func.sum(Order.total), 0).label("total_revenue"),
                func.coalesce(func.sum(Order.refunded_amount), 0).label("refunded_amount"),
                func.coalesce(func.sum(Order.advertising_cost), 0).label("advertising_cost"),
            ).where(
                and_(
                    Order.workspace_id == workspace_id,
                    Order.received_at >= date_from,
                    Order.received_at <= date_to,
                )
            )
        )
        row = result.first()
        total_orders = row.total_orders or 0
        total_revenue = float(row.total_revenue or 0)
        refunded_amount = float(row.refunded_amount or 0)
        advertising_cost = float(row.advertising_cost or 0)

        order_rows = (
            await session.execute(
                select(Order.total, Order.profit_snapshot).where(
                    and_(
                        Order.workspace_id == workspace_id,
                        Order.received_at >= date_from,
                        Order.received_at <= date_to,
                    )
                )
            )
        ).all()

        gross_profit = 0.0
        profit_revenue = 0.0
        profit_known_orders = 0
        for order_total, profit_snapshot in order_rows:
            snapshot = profit_snapshot
            if isinstance(snapshot, str):
                try:
                    snapshot = json.loads(snapshot)
                except (TypeError, ValueError):
                    snapshot = None
            if not isinstance(snapshot, dict) or snapshot.get("contribution_margin") is None:
                continue
            try:
                contribution_margin = float(snapshot["contribution_margin"])
            except (TypeError, ValueError):
                continue
            gross_profit += contribution_margin
            profit_revenue += float(order_total or 0)
            profit_known_orders += 1

        cost_coverage = (
            profit_known_orders / total_orders * 100 if total_orders > 0 else 0.0
        )
        if cost_coverage >= 99.999:
            cost_status = "verified"
            estimated_cost = total_revenue - gross_profit
            gross_margin = gross_profit / profit_revenue * 100 if profit_revenue > 0 else 0.0
        elif profit_known_orders > 0:
            cost_status = "partial"
            estimated_cost = None
            gross_margin = gross_profit / profit_revenue * 100 if profit_revenue > 0 else None
        else:
            cost_status = "missing"
            estimated_cost = None
            gross_margin = None

        # 计算客单价
        avg_order_value = (total_revenue / total_orders) if total_orders > 0 else 0

        return {
            "period": {"start_date": date_from.strftime("%Y-%m-%d"), "end_date": date_to.strftime("%Y-%m-%d")},
            "orders": {
                "total_orders": total_orders,
                "total_items": 0,
                "avg_order_value": round(avg_order_value, 2),
                "refunded_orders": 0,
                "refund_rate_percent": round(
                    refunded_amount / total_revenue * 100 if total_revenue > 0 else 0,
                    2,
                ),
            },
            "revenue": {
                "total_revenue": round(total_revenue, 2),
                "estimated_cost": round(estimated_cost, 2) if estimated_cost is not None else None,
                "gross_profit": round(gross_profit, 2),
                "gross_margin_percent": round(gross_margin, 2) if gross_margin is not None else None,
                "profit_revenue": round(profit_revenue, 2),
            },
            "marketing": {
                "ad_spend": round(advertising_cost, 2),
                "roas": round(total_revenue / advertising_cost, 2) if advertising_cost > 0 else None,
            },
            "customers": {
                "new_customers": 0,
                "returning_customers": total_orders,
                "new_customer_rate_percent": 0,
            },
            "data_quality": {
                "orders_count": total_orders,
                "profit_known_orders": profit_known_orders,
                "cost_coverage_percent": round(cost_coverage, 2),
                "cost_status": cost_status,
                "has_real_data": total_orders > 0,
                "note": (
                    "Profit uses stored per-order contribution margin snapshots."
                    if cost_status == "verified"
                    else "Profit is partial: only orders with cost snapshots are included."
                    if cost_status == "partial"
                    else "Profit unavailable: no order has a cost snapshot in this period."
                )
                if total_orders > 0
                else "No orders in this period.",
            },
        }

    # 今日数据
    today_start = datetime(now.year, now.month, now.day)
    today_end = today_start + timedelta(days=1) - timedelta(seconds=1)
    today_data = await _calc_period(today_start, today_end)
    today_data["date"] = now.strftime("%Y-%m-%d")
    today_data["generated_at"] = now.isoformat()

    # 本周数据
    week_start = today_start - timedelta(days=now.weekday())
    week_data = await _calc_period(week_start, today_end)

    # 本月数据
    month_start = datetime(now.year, now.month, 1)
    month_data = await _calc_period(month_start, today_end)

    # 上周数据
    last_week_start = week_start - timedelta(days=7)
    last_week_end = week_start - timedelta(seconds=1)
    last_week_data = await _calc_period(last_week_start, last_week_end)

    # 计算趋势
    revenue_trend = _calculate_trend(
        week_data["revenue"]["total_revenue"],
        last_week_data["revenue"]["total_revenue"],
    )
    orders_trend = _calculate_trend(
        week_data["orders"]["total_orders"],
        last_week_data["orders"]["total_orders"],
    )

    return {
        "period": {
            "start_date": start_date,
            "end_date": end_date,
            "generated_at": now.isoformat(),
        },
        "today": today_data,
        "this_week": week_data,
        "this_month": month_data,
        "last_week": last_week_data,
        "trends": {
            "revenue_week_over_week": revenue_trend,
            "orders_week_over_week": orders_trend,
        },
        "key_metrics": {
            "today_revenue": today_data["revenue"]["total_revenue"],
            "today_orders": today_data["orders"]["total_orders"],
            "today_gross_margin": today_data["revenue"]["gross_margin_percent"],
            "today_roas": today_data["marketing"]["roas"],
            "week_revenue": week_data["revenue"]["total_revenue"],
            "week_orders": week_data["orders"]["total_orders"],
            "month_revenue": month_data["revenue"]["total_revenue"],
            "month_orders": month_data["orders"]["total_orders"],
        },
        "data_source": "woocommerce_real_orders",
    }
