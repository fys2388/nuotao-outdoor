"""Cross-channel operating analytics for the shared B2C + B2B business model.

The service never converts currencies without a stored FX rate and never
invents a profit number when cost evidence is missing. Results are grouped by
business model and currency so the console cannot show a misleading total.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select

from app.models.b2b import B2BAgent, B2BOrder, B2BOrderItem
from app.models.b2b_finance import B2BInvoice
from app.models.order import Order, OrderItem
from app.models.product import Product, ProductCost
from app.models.supply_chain import InventorySnapshot
from app.schemas.analytics import (
    AnalyticsDataQuality,
    ChannelAnalyticsResponse,
    ChannelAnalyticsSummary,
    CustomerContribution,
    InventoryPerformance,
    ReceivableAgingSummary,
)
from app.services import currency_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

ZERO = Decimal("0")
CENT = Decimal("0.01")


class ChannelAnalyticsError(ValueError):
    """Raised when a report range is invalid."""


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (TypeError, ValueError):
        return None


def _snapshot_margin(snapshot: Any) -> Decimal | None:
    if isinstance(snapshot, str):
        try:
            snapshot = json.loads(snapshot)
        except (TypeError, ValueError):
            return None
    if not isinstance(snapshot, dict):
        return None
    return _decimal(snapshot.get("contribution_margin"))


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT)


def _percent(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator <= ZERO:
        return None
    return (numerator / denominator * Decimal("100")).quantize(CENT)


def _summary_bucket() -> dict[str, Any]:
    return {
        "revenue": ZERO,
        "orders": 0,
        "units": 0,
        "profit_revenue": ZERO,
        "gross_profit": ZERO,
        "profit_rows": 0,
        "refund_amount": ZERO,
        "advertising_cost": ZERO,
    }


def _customer_bucket() -> dict[str, Any]:
    return {
        "revenue": ZERO,
        "orders": 0,
        "profit_revenue": ZERO,
        "gross_profit": ZERO,
        "profit_rows": 0,
    }


def _to_summary(
    business_model: str,
    currency: str,
    bucket: dict[str, Any],
) -> ChannelAnalyticsSummary:
    revenue = bucket["revenue"]
    profit_revenue = bucket["profit_revenue"]
    gross_profit = bucket["gross_profit"] if bucket["profit_rows"] > 0 else None
    coverage = _percent(profit_revenue, revenue) or ZERO
    quality_status = (
        "verified"
        if revenue > ZERO and coverage >= Decimal("99.99")
        else "partial"
        if gross_profit is not None
        else "missing"
    )
    notes = []
    if quality_status == "partial":
        notes.append("Only orders and order lines with cost evidence are included in profit.")
    if quality_status == "missing":
        notes.append("No cost evidence is available for this channel and period.")

    return ChannelAnalyticsSummary(
        business_model=business_model,
        currency=currency,
        revenue=_money(revenue),
        orders=bucket["orders"],
        units=bucket["units"],
        average_order_value=_money(revenue / bucket["orders"])
        if bucket["orders"]
        else ZERO,
        profit_revenue=_money(profit_revenue),
        gross_profit=_money(gross_profit) if gross_profit is not None else None,
        gross_margin_percent=_percent(gross_profit, profit_revenue)
        if gross_profit is not None
        else None,
        refund_amount=_money(bucket["refund_amount"]),
        advertising_cost=_money(bucket["advertising_cost"]),
        roas=(revenue / bucket["advertising_cost"]).quantize(CENT)
        if bucket["advertising_cost"] > ZERO
        else None,
        data_quality=AnalyticsDataQuality(
            status=quality_status,
            cost_coverage_percent=coverage,
            notes=notes,
        ),
    )


async def build_channel_analytics(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    start_date: date,
    end_date: date,
    currency: str | None = None,
    reporting_currency: str | None = None,
    limit: int = 10,
) -> ChannelAnalyticsResponse:
    """Build a traceable B2C/B2B operating report for one workspace."""
    if start_date > end_date:
        raise ChannelAnalyticsError("start_date must be on or before end_date")
    if (end_date - start_date).days > 366:
        raise ChannelAnalyticsError("report range cannot exceed 366 days")
    if limit < 1 or limit > 50:
        raise ChannelAnalyticsError("limit must be between 1 and 50")

    start_at = datetime.combine(start_date, time.min, tzinfo=UTC)
    end_at = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=UTC)
    normalized_currency = currency.upper() if currency else None
    normalized_reporting_currency = (
        currency_service.normalize_currency_code(reporting_currency)
        if reporting_currency
        else None
    )
    period_days = Decimal(str((end_date - start_date).days + 1))
    rate_cache: dict[tuple[str, str, date], Any] = {}

    async def convert(
        amount: Decimal | int | float | None,
        source_currency: str,
        rate_date: date,
    ) -> Decimal:
        value = _decimal(amount) or ZERO
        if normalized_reporting_currency is None:
            return value
        return await currency_service.convert_amount(
            session,
            workspace_id=workspace_id,
            amount=value,
            base_currency=source_currency,
            quote_currency=normalized_reporting_currency,
            as_of=rate_date,
            rate_cache=rate_cache,
        )

    summaries: dict[tuple[str, str], dict[str, Any]] = defaultdict(_summary_bucket)
    customers: dict[tuple[str, str, str], dict[str, Any]] = {}
    product_units: dict[tuple[UUID, str], int] = defaultdict(int)

    b2c_orders = (
        await session.execute(
            select(Order).where(
                Order.workspace_id == workspace_id,
                Order.business_model == "B2C",
                Order.status != "cancelled",
                Order.received_at >= start_at,
                Order.received_at < end_at,
            )
        )
    ).scalars().all()
    if normalized_currency:
        b2c_orders = [row for row in b2c_orders if row.currency == normalized_currency]

    b2c_order_ids = [row.id for row in b2c_orders]
    b2c_items: list[OrderItem] = []
    if b2c_order_ids:
        b2c_items = (
            await session.execute(
                select(OrderItem).where(OrderItem.order_id.in_(b2c_order_ids))
            )
        ).scalars().all()

    products = (
        await session.execute(
            select(Product).where(Product.workspace_id == workspace_id)
        )
    ).scalars().all()
    products_by_id = {row.id: row for row in products}
    products_by_sku = {row.sku: row for row in products}

    for order in b2c_orders:
        order_currency = order.currency
        summary_currency = normalized_reporting_currency or order_currency
        rate_date = order.received_at.date()
        order_total = await convert(order.total, order_currency, rate_date)
        refund_amount = await convert(
            order.refunded_amount,
            order_currency,
            rate_date,
        )
        advertising_cost = await convert(
            order.advertising_cost,
            order_currency,
            rate_date,
        )
        bucket = summaries[("B2C", summary_currency)]
        bucket["orders"] += 1
        bucket["revenue"] += order_total
        bucket["refund_amount"] += refund_amount
        bucket["advertising_cost"] += advertising_cost

        margin = _snapshot_margin(order.profit_snapshot)
        if margin is not None:
            bucket["profit_rows"] += 1
            bucket["profit_revenue"] += order_total
            bucket["gross_profit"] += await convert(
                margin,
                order_currency,
                rate_date,
            )

        customer_id = order.customer_reference_id or "UNIDENTIFIED"
        customer_name = "未识别 B2C 客户"
        customer_key = ("B2C", summary_currency, customer_id)
        customer_bucket = customers.setdefault(customer_key, _customer_bucket())
        if customer_bucket["orders"] == 0:
            customer_bucket["customer_name"] = customer_name
        customer_bucket["orders"] += 1
        customer_bucket["revenue"] += order_total
        if margin is not None:
            customer_bucket["profit_rows"] += 1
            customer_bucket["profit_revenue"] += order_total
            customer_bucket["gross_profit"] += await convert(
                margin,
                order_currency,
                rate_date,
            )

    b2c_order_by_id = {row.id: row for row in b2c_orders}
    for item in b2c_items:
        order = b2c_order_by_id.get(item.order_id)
        if order is not None:
            summaries[("B2C", order.currency)]["units"] += item.quantity or 0
        product = products_by_id.get(item.product_id) if item.product_id else None
        if product is None and item.sku:
            product = products_by_sku.get(item.sku)
        if product is not None:
            product_units[(product.id, "B2C")] += item.quantity or 0

    b2b_orders = (
        await session.execute(
            select(B2BOrder).where(
                B2BOrder.workspace_id == workspace_id,
                B2BOrder.status != "cancelled",
                B2BOrder.created_at >= start_at,
                B2BOrder.created_at < end_at,
            )
        )
    ).scalars().all()
    if normalized_currency:
        b2b_orders = [row for row in b2b_orders if row.currency == normalized_currency]

    b2b_order_ids = [row.id for row in b2b_orders]
    b2b_items: list[B2BOrderItem] = []
    if b2b_order_ids:
        b2b_items = (
            await session.execute(
                select(B2BOrderItem).where(B2BOrderItem.order_id.in_(b2b_order_ids))
            )
        ).scalars().all()

    agent_ids = {row.agent_id for row in b2b_orders}
    agents = {}
    if agent_ids:
        agents = {
            row.id: row
            for row in (
                await session.execute(
                    select(B2BAgent).where(
                        B2BAgent.workspace_id == workspace_id,
                        B2BAgent.id.in_(agent_ids),
                    )
                )
            ).scalars().all()
        }

    b2b_product_ids = {item.product_id for item in b2b_items}
    latest_costs: dict[UUID, tuple[Decimal, str, date]] = {}
    if b2b_product_ids:
        cost_rows = (
            await session.execute(
                select(ProductCost)
                .where(
                    ProductCost.workspace_id == workspace_id,
                    ProductCost.product_id.in_(b2b_product_ids),
                )
                .order_by(ProductCost.product_id, ProductCost.valid_from.desc())
            )
        ).scalars().all()
        for cost in cost_rows:
            unit_cost = (
                cost.total_landed_cost
                if cost.total_landed_cost and cost.total_landed_cost > ZERO
                else cost.total_cost
            )
            latest_costs.setdefault(
                cost.product_id,
                (unit_cost, cost.currency, cost.valid_from.date()),
            )

    order_by_id = {row.id: row for row in b2b_orders}
    for order in b2b_orders:
        summary_currency = normalized_reporting_currency or order.currency
        rate_date = order.created_at.date()
        order_total = await convert(order.total, order.currency, rate_date)
        bucket = summaries[("B2B", summary_currency)]
        bucket["orders"] += 1
        bucket["revenue"] += order_total

        agent = agents.get(order.agent_id)
        customer_key = ("B2B", summary_currency, str(order.agent_id))
        customer_bucket = customers.setdefault(customer_key, _customer_bucket())
        customer_bucket["customer_name"] = (
            agent.company_name if agent is not None else str(order.agent_id)
        )
        customer_bucket["orders"] += 1
        customer_bucket["revenue"] += order_total
        if agent is not None:
            customer_bucket["credit_limit"] = agent.credit_limit
            customer_bucket["current_balance"] = agent.current_balance

    for item in b2b_items:
        order = order_by_id[item.order_id]
        summary_currency = normalized_reporting_currency or order.currency
        bucket = summaries[("B2B", summary_currency)]
        bucket["units"] += item.quantity or 0
        product_units[(item.product_id, "B2B")] += item.quantity or 0

        cost_evidence = latest_costs.get(item.product_id)
        if cost_evidence is None:
            continue
        unit_cost, cost_currency, cost_date = cost_evidence
        line_subtotal = item.subtotal or ZERO
        try:
            order_currency_unit_cost = await currency_service.convert_amount(
                session,
                workspace_id=workspace_id,
                amount=unit_cost,
                base_currency=cost_currency,
                quote_currency=order.currency,
                as_of=cost_date,
                rate_cache=rate_cache,
            )
        except currency_service.ExchangeRateNotFoundError:
            continue
        margin_in_order_currency = (
            line_subtotal
            - order_currency_unit_cost * Decimal(item.quantity or 0)
        )
        rate_date = order.created_at.date()
        converted_line_subtotal = await convert(
            line_subtotal,
            order.currency,
            rate_date,
        )
        margin = await convert(
            margin_in_order_currency,
            order.currency,
            rate_date,
        )
        bucket["profit_rows"] += 1
        bucket["profit_revenue"] += converted_line_subtotal
        bucket["gross_profit"] += margin

        customer_key = ("B2B", summary_currency, str(order.agent_id))
        customer_bucket = customers[customer_key]
        customer_bucket["profit_rows"] += 1
        customer_bucket["profit_revenue"] += converted_line_subtotal
        customer_bucket["gross_profit"] += margin

    channel_summaries = [
        _to_summary(model, summary_currency, bucket)
        for (model, summary_currency), bucket in sorted(summaries.items())
        if bucket["orders"] > 0
    ]

    top_customers: list[CustomerContribution] = []
    for (model, customer_currency, customer_id), bucket in customers.items():
        gross_profit = (
            bucket["gross_profit"] if bucket["profit_rows"] > 0 else None
        )
        profit_revenue = bucket["profit_revenue"]
        coverage = _percent(profit_revenue, bucket["revenue"]) or ZERO
        agent = None
        if model == "B2B":
            try:
                agent = agents.get(UUID(customer_id))
            except ValueError:
                agent = None
        available_credit = None
        if agent is not None:
            available_credit = max(
                agent.credit_limit - agent.current_balance,
                ZERO,
            )
        top_customers.append(
            CustomerContribution(
                business_model=model,
                customer_id=customer_id,
                customer_name=bucket.get("customer_name") or customer_id,
                currency=customer_currency,
                revenue=_money(bucket["revenue"]),
                orders=bucket["orders"],
                profit_revenue=_money(profit_revenue),
                gross_profit=_money(gross_profit) if gross_profit is not None else None,
                gross_margin_percent=_percent(gross_profit, profit_revenue)
                if gross_profit is not None
                else None,
                cost_coverage_percent=coverage,
                credit_limit=agent.credit_limit if agent is not None else None,
                current_balance=agent.current_balance if agent is not None else None,
                available_credit=available_credit,
            )
        )
    top_customers.sort(key=lambda row: row.revenue, reverse=True)
    top_customers = top_customers[:limit]

    invoice_rows = (
        await session.execute(
            select(B2BInvoice).where(
                B2BInvoice.workspace_id == workspace_id,
                B2BInvoice.balance_due > ZERO,
                B2BInvoice.status.in_(("issued", "partially_paid", "overdue")),
            )
        )
    ).scalars().all()
    aging: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {
            "current": ZERO,
            "days_1_30": ZERO,
            "days_31_60": ZERO,
            "days_61_90": ZERO,
            "days_over_90": ZERO,
        }
    )
    for invoice in invoice_rows:
        if normalized_currency and invoice.currency != normalized_currency:
            continue
        summary_currency = normalized_reporting_currency or invoice.currency
        balance_due = await convert(
            invoice.balance_due,
            invoice.currency,
            end_date,
        )
        days_overdue = (end_date - invoice.due_date).days
        target = aging[summary_currency]
        if days_overdue <= 0:
            target["current"] += balance_due
        elif days_overdue <= 30:
            target["days_1_30"] += balance_due
        elif days_overdue <= 60:
            target["days_31_60"] += balance_due
        elif days_overdue <= 90:
            target["days_61_90"] += balance_due
        else:
            target["days_over_90"] += balance_due

    receivable_aging = [
        ReceivableAgingSummary(
            currency=aging_currency,
            current=_money(bucket["current"]),
            days_1_30=_money(bucket["days_1_30"]),
            days_31_60=_money(bucket["days_31_60"]),
            days_61_90=_money(bucket["days_61_90"]),
            days_over_90=_money(bucket["days_over_90"]),
            total=_money(sum(bucket.values(), ZERO)),
        )
        for aging_currency, bucket in sorted(aging.items())
    ]

    inventory_rows = (
        await session.execute(
            select(InventorySnapshot).where(
                InventorySnapshot.workspace_id == workspace_id
            )
        )
    ).scalars().all()
    inventory: dict[UUID, dict[str, int]] = defaultdict(
        lambda: {
            "current_inventory": 0,
            "reserved": 0,
            "available": 0,
            "in_transit": 0,
        }
    )
    for row in inventory_rows:
        if row.product_id is None:
            continue
        bucket = inventory[row.product_id]
        bucket["current_inventory"] += row.quantity or 0
        bucket["reserved"] += row.reserved or 0
        bucket["available"] += row.available or 0
        bucket["in_transit"] += row.in_transit or 0

    performance_rows: list[InventoryPerformance] = []
    for (product_id, _model), _units in product_units.items():
        product = products_by_id.get(product_id)
        if product is None:
            continue
        b2c_units = product_units.get((product_id, "B2C"), 0)
        b2b_units = product_units.get((product_id, "B2B"), 0)
        total_units = b2c_units + b2b_units
        bucket = inventory.get(product_id)
        current_inventory = bucket["current_inventory"] if bucket else 0
        turnover_ratio = (
            Decimal(total_units) / Decimal(current_inventory)
            if current_inventory > 0
            else None
        )
        average_daily_units = Decimal(total_units) / period_days
        days_of_inventory = (
            (Decimal(current_inventory) / average_daily_units).quantize(CENT)
            if average_daily_units > ZERO
            else None
        )
        performance_rows.append(
            InventoryPerformance(
                product_id=str(product_id),
                sku=product.sku,
                name=product.name,
                b2c_units=b2c_units,
                b2b_units=b2b_units,
                total_units=total_units,
                current_inventory=current_inventory,
                reserved=bucket["reserved"] if bucket else 0,
                available=bucket["available"] if bucket else 0,
                in_transit=bucket["in_transit"] if bucket else 0,
                turnover_ratio=turnover_ratio.quantize(CENT)
                if turnover_ratio is not None
                else None,
                days_of_inventory=days_of_inventory,
                inventory_basis="period_units_over_current_snapshot",
            )
        )
    performance_rows.sort(key=lambda row: row.total_units, reverse=True)
    performance_rows = performance_rows[:limit]

    channel_currencies = {row.currency for row in channel_summaries}
    channel_quality_statuses = {
        row.data_quality.status for row in channel_summaries
    }
    overall_status = (
        "verified"
        if channel_quality_statuses == {"verified"}
        else "missing"
        if channel_quality_statuses == {"missing"}
        else "partial"
    )
    overall_coverage = None
    if len(channel_currencies) == 1:
        total_revenue = sum(
            (row.revenue for row in channel_summaries),
            ZERO,
        )
        total_profit_revenue = sum(
            (row.profit_revenue for row in channel_summaries),
            ZERO,
        )
        overall_coverage = _percent(total_profit_revenue, total_revenue)

    notes = [
        "Amounts are grouped by currency and are never summed across currencies.",
        "Profit includes only orders or order lines with a traceable cost snapshot.",
        "Inventory turnover uses period units divided by the current inventory snapshot, not a historical average.",
    ]
    if len(channel_currencies) > 1:
        notes.append(
            "Overall cost coverage is omitted across multiple currencies; "
            "review the per-channel coverage values."
        )
    if normalized_reporting_currency:
        notes.append(
            f"Amounts are converted to {normalized_reporting_currency} using "
            "the latest direct workspace rate on or before each transaction date."
        )

    return ChannelAnalyticsResponse(
        period={"start_date": start_date, "end_date": end_date},
        generated_at=datetime.now(UTC),
        currency_filter=normalized_currency,
        reporting_currency=normalized_reporting_currency,
        channel_summaries=channel_summaries,
        top_customers=top_customers,
        receivable_aging=receivable_aging,
        inventory_performance=performance_rows,
        data_quality=AnalyticsDataQuality(
            status=overall_status,
            cost_coverage_percent=overall_coverage,
            notes=notes,
        ),
        notes=notes,
    )
