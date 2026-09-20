"""Recommendation-only B2B agents for sales, quoting, and collections.

These agents read authoritative B2B services and return evidence-backed
recommendations. They never create quotes, change payment terms, send
collection notices, allocate receipts, or mutate commercial data.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.b2b import B2BAgent
from app.models.b2b_sales import B2BRFQ
from app.models.product import ProductCost
from app.services import b2b_finance_service, b2b_pricing_service, b2b_sales_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

MONEY = Decimal("0.01")
PERCENT = Decimal("0.01")
ACTIVE_RFQ_STATUSES = ("submitted", "in_review", "quoted")


class B2BAgentInputError(ValueError):
    """Raised when a B2B agent task input is malformed."""


def _uuid(value: Any, *, field: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError):
        raise B2BAgentInputError(f"invalid '{field}': {value!r}") from None


def _date(value: Any, *, default: date | None = None) -> date:
    if value in (None, ""):
        return default or date.today()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise B2BAgentInputError(f"invalid date: {value!r}") from None


def _int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise B2BAgentInputError(f"invalid integer: {value!r}") from None
    return max(minimum, min(maximum, parsed))


def _decimal(value: Any, *, default: Decimal = Decimal("0")) -> Decimal:
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (TypeError, ValueError):
        raise B2BAgentInputError(f"invalid decimal: {value!r}") from None


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def _percent(value: Decimal) -> Decimal:
    return value.quantize(PERCENT, rounding=ROUND_HALF_UP)


def _age_days(start: datetime | None, *, as_of: date) -> int:
    if start is None:
        return 0
    start_date = start.date() if isinstance(start, datetime) else start
    return max(0, (as_of - start_date).days)


async def analyze_sales_pipeline(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    task_input: dict[str, Any],
) -> dict[str, Any]:
    """Prioritize active RFQs and recommend the next sales action."""
    as_of = _date(task_input.get("as_of"))
    limit = _int(task_input.get("limit"), default=50, minimum=1, maximum=200)
    stale_days = _int(
        task_input.get("stale_days"),
        default=3,
        minimum=1,
        maximum=60,
    )

    rows = (
        (
            await db.execute(
                select(B2BRFQ)
                .where(
                    B2BRFQ.workspace_id == workspace_id,
                    B2BRFQ.status.in_(ACTIVE_RFQ_STATUSES),
                )
                .options(selectinload(B2BRFQ.items), selectinload(B2BRFQ.quotes))
                .order_by(B2BRFQ.created_at.asc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    opportunities: list[dict[str, Any]] = []
    for rfq in rows:
        age_days = _age_days(rfq.submitted_at or rfq.created_at, as_of=as_of)
        target_value = sum(
            (
                item.target_unit_price * item.requested_quantity
                for item in rfq.items
                if item.target_unit_price is not None
            ),
            Decimal("0"),
        )
        stage_weight = {"submitted": 40, "in_review": 60, "quoted": 80}.get(
            rfq.status,
            30,
        )
        urgency = min(20, max(0, age_days - stale_days + 1) * 4)
        value_weight = min(10, int(target_value / Decimal("1000"))) if target_value else 0
        priority_score = min(100, stage_weight + urgency + value_weight)

        quote_expired = any(
            quote.valid_until < as_of
            and quote.status in {"draft", "pending_approval", "sent"}
            for quote in rfq.quotes
        )
        missing_target = any(item.target_unit_price is None for item in rfq.items)

        if rfq.status == "submitted" and age_days >= stale_days:
            action = "assign_and_qualify"
            reason = f"RFQ 已提交 {age_days} 天仍未进入报价评审"
        elif rfq.status == "in_review" and age_days >= stale_days:
            action = "prepare_quote"
            reason = f"RFQ 已评审 {age_days} 天, 需完成报价草稿"
        elif rfq.status == "quoted" and quote_expired:
            action = "renew_quote"
            reason = "客户报价已过期, 需要重新确认价格有效期"
        elif rfq.status == "quoted" and age_days >= stale_days:
            action = "follow_up"
            reason = f"报价后 {age_days} 天没有成交更新"
        else:
            action = "monitor"
            reason = "当前处于正常处理时效内"

        risk_flags: list[str] = []
        if missing_target:
            risk_flags.append("MISSING_TARGET_PRICE")
        if quote_expired:
            risk_flags.append("QUOTE_EXPIRED")
        if age_days >= stale_days * 3:
            risk_flags.append("SLA_AT_RISK")
        if rfq.requested_delivery_date and rfq.requested_delivery_date < as_of:
            risk_flags.append("DELIVERY_DATE_PASSED")

        opportunities.append(
            {
                "rfq_id": str(rfq.id),
                "rfq_number": rfq.rfq_number,
                "agent_id": str(rfq.agent_id),
                "status": rfq.status,
                "age_days": age_days,
                "target_value": str(_money(target_value)),
                "currency": rfq.requested_currency,
                "priority_score": priority_score,
                "recommended_action": action,
                "reason": reason,
                "risk_flags": risk_flags,
            }
        )

    opportunities.sort(
        key=lambda item: (item["priority_score"], item["age_days"]),
        reverse=True,
    )
    return {
        "analysis_type": "b2b_sales_pipeline",
        "as_of": as_of.isoformat(),
        "summary": {
            "active_rfq_count": len(opportunities),
            "action_required_count": sum(
                1 for item in opportunities if item["recommended_action"] != "monitor"
            ),
            "at_risk_count": sum(
                1 for item in opportunities if "SLA_AT_RISK" in item["risk_flags"]
            ),
            "target_value": str(
                _money(
                    sum(
                        (Decimal(item["target_value"]) for item in opportunities),
                        Decimal("0"),
                    )
                )
            ),
        },
        "opportunities": opportunities,
        "requires_human_approval": True,
        "write_actions_performed": [],
    }


async def recommend_quote(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    task_input: dict[str, Any],
) -> dict[str, Any]:
    """Calculate a quote recommendation from published B2B prices and costs."""
    rfq_id = _uuid(task_input.get("rfq_id"), field="rfq_id")
    target_margin_percent = _decimal(
        task_input.get("target_margin_percent"),
        default=Decimal("20"),
    )
    valid_days = _int(
        task_input.get("valid_days"),
        default=14,
        minimum=1,
        maximum=180,
    )
    if target_margin_percent < 0 or target_margin_percent > 100:
        raise B2BAgentInputError("target_margin_percent must be between 0 and 100")

    rfq = await b2b_sales_service.get_rfq(
        db,
        workspace_id=workspace_id,
        rfq_id=rfq_id,
    )
    if rfq is None:
        raise B2BAgentInputError("RFQ not found")
    agent = (
        await db.execute(
            select(B2BAgent).where(
                B2BAgent.workspace_id == workspace_id,
                B2BAgent.id == rfq.agent_id,
            )
        )
    ).scalar_one_or_none()
    if agent is None:
        raise B2BAgentInputError("B2B customer not found")

    product_ids = [item.product_id for item in rfq.items]
    costs = {
        row.product_id: row
        for row in (
            await db.execute(
                select(ProductCost).where(
                    ProductCost.workspace_id == workspace_id,
                    ProductCost.product_id.in_(product_ids),
                )
            )
        )
        .scalars()
        .all()
    }

    lines: list[dict[str, Any]] = []
    blockers: list[str] = []
    total_revenue = Decimal("0")
    total_cost = Decimal("0")
    target_value = Decimal("0")
    for item in rfq.items:
        try:
            resolved = await b2b_pricing_service.resolve_b2b_price(
                db,
                workspace_id=workspace_id,
                product_id=item.product_id,
                agent=agent,
                quantity=item.requested_quantity,
            )
        except b2b_pricing_service.PricingError as exc:
            blockers.append(f"{item.sku_snapshot}: {exc}")
            lines.append(
                {
                    "rfq_item_id": str(item.id),
                    "sku": item.sku_snapshot,
                    "product_name": item.product_name_snapshot,
                    "quantity": item.requested_quantity,
                    "target_unit_price": (
                        str(item.target_unit_price)
                        if item.target_unit_price is not None
                        else None
                    ),
                    "published_unit_price": None,
                    "price_source": None,
                    "margin_percent": None,
                    "recommendation": "prepare_price_book",
                }
            )
            continue

        line_revenue = _money(resolved.unit_price * item.requested_quantity)
        cost = costs.get(item.product_id)
        line_cost = (
            _money(cost.total_landed_cost * item.requested_quantity)
            if cost is not None
            else None
        )
        margin_percent = None
        if line_cost is not None and line_revenue > 0:
            margin_percent = _percent(
                ((line_revenue - line_cost) / line_revenue) * Decimal("100")
            )
        if item.target_unit_price is not None:
            target_value += item.target_unit_price * item.requested_quantity
        total_revenue += line_revenue
        if line_cost is not None:
            total_cost += line_cost

        if line_cost is None:
            line_recommendation = "verify_cost"
            blockers.append(f"{item.sku_snapshot}: missing landed cost")
        elif margin_percent is not None and margin_percent < target_margin_percent:
            line_recommendation = "negotiate_or_escalate"
        else:
            line_recommendation = "proceed_to_quote"

        lines.append(
            {
                "rfq_item_id": str(item.id),
                "sku": item.sku_snapshot,
                "product_name": item.product_name_snapshot,
                "quantity": item.requested_quantity,
                "target_unit_price": (
                    str(item.target_unit_price)
                    if item.target_unit_price is not None
                    else None
                ),
                "published_unit_price": str(resolved.unit_price),
                "price_source": resolved.source,
                "price_tier_id": str(resolved.price_tier_id),
                "price_book_version_id": str(resolved.price_book_version_id),
                "line_revenue": str(line_revenue),
                "line_landed_cost": str(line_cost) if line_cost is not None else None,
                "margin_percent": str(margin_percent) if margin_percent is not None else None,
                "recommendation": line_recommendation,
            }
        )

    overall_margin = None
    if total_revenue > 0 and total_cost > 0 and not blockers:
        overall_margin = _percent(
            ((total_revenue - total_cost) / total_revenue) * Decimal("100")
        )

    if blockers:
        recommended_action = "do_not_quote"
    elif overall_margin is not None and overall_margin < target_margin_percent:
        recommended_action = "negotiate_or_escalate"
    else:
        recommended_action = "proceed_to_quote"

    target_gap = (
        _money(target_value - total_revenue)
        if target_value > 0 and total_revenue > 0
        else None
    )
    valid_until = date.today() + timedelta(days=valid_days)
    return {
        "analysis_type": "b2b_quote_recommendation",
        "rfq_id": str(rfq.id),
        "rfq_number": rfq.rfq_number,
        "customer": {
            "agent_id": str(agent.id),
            "company_name": agent.company_name,
            "tier": agent.tier,
            "currency": agent.currency,
        },
        "recommended_action": recommended_action,
        "confidence": "0.40" if blockers else "0.85",
        "summary": {
            "currency": rfq.requested_currency,
            "line_count": len(lines),
            "published_revenue": str(_money(total_revenue)),
            "landed_cost": str(_money(total_cost)) if total_cost else None,
            "overall_margin_percent": (
                str(overall_margin) if overall_margin is not None else None
            ),
            "target_margin_percent": str(target_margin_percent),
            "target_value": str(_money(target_value)) if target_value else None,
            "target_gap": str(target_gap) if target_gap is not None else None,
            "suggested_valid_until": valid_until.isoformat(),
        },
        "lines": lines,
        "blockers": blockers,
        "requires_human_approval": True,
        "write_actions_performed": [],
    }


async def analyze_collections(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    task_input: dict[str, Any],
) -> dict[str, Any]:
    """Prioritize open receivables and recommend collection actions."""
    as_of = _date(task_input.get("as_of"))
    limit = _int(task_input.get("limit"), default=100, minimum=1, maximum=500)
    overdue_only = bool(task_input.get("overdue_only", False))

    invoices, _ = await b2b_finance_service.list_receivables(
        db,
        workspace_id=workspace_id,
        page=1,
        page_size=limit,
        overdue_only=overdue_only,
    )
    customer_ids = {invoice.agent_id for invoice in invoices}
    customers = {
        row.id: row
        for row in (
            await db.execute(
                select(B2BAgent).where(
                    B2BAgent.workspace_id == workspace_id,
                    B2BAgent.id.in_(customer_ids),
                )
            )
        )
        .scalars()
        .all()
    }

    bucket_weight = {"current": 20, "0-30": 40, "31-60": 60, "61-90": 80, "90+": 100}
    actions = {
        "current": "monitor",
        "0-30": "send_reminder",
        "31-60": "sales_escalation",
        "61-90": "credit_hold_review",
        "90+": "collections_review",
    }
    priorities: list[dict[str, Any]] = []
    by_customer: dict[UUID, Decimal] = defaultdict(lambda: Decimal("0"))
    for invoice in invoices:
        customer = customers.get(invoice.agent_id)
        bucket = b2b_finance_service.receivable_aging_bucket(invoice, as_of=as_of)
        age_days = b2b_finance_service.receivable_age_days(invoice, as_of=as_of)
        balance = _money(invoice.balance_due)
        by_customer[invoice.agent_id] += balance
        credit_limit = customer.credit_limit if customer is not None else Decimal("0")
        utilization = (
            _percent((by_customer[invoice.agent_id] / credit_limit) * Decimal("100"))
            if credit_limit > 0
            else Decimal("0")
        )
        utilization_bonus = min(20, max(0, int(utilization - Decimal("70")) // 2))
        priority_score = min(100, bucket_weight.get(bucket, 20) + utilization_bonus)
        risk_flags: list[str] = []
        if customer is None:
            risk_flags.append("CUSTOMER_NOT_FOUND")
        elif customer.status != "active":
            risk_flags.append("CUSTOMER_NOT_ACTIVE")
        if credit_limit > 0 and by_customer[invoice.agent_id] >= credit_limit:
            risk_flags.append("CREDIT_LIMIT_EXCEEDED")
        if bucket in {"61-90", "90+"}:
            risk_flags.append("AGED_RECEIVABLE")

        priorities.append(
            {
                "invoice_id": str(invoice.id),
                "invoice_number": invoice.invoice_number,
                "order_id": str(invoice.order_id),
                "agent_id": str(invoice.agent_id),
                "company_name": customer.company_name if customer else None,
                "status": b2b_finance_service.effective_invoice_status(
                    invoice,
                    as_of=as_of,
                ),
                "currency": invoice.currency,
                "balance_due": str(balance),
                "due_date": invoice.due_date.isoformat(),
                "age_days": age_days,
                "aging_bucket": bucket,
                "credit_utilization_percent": str(utilization),
                "priority_score": priority_score,
                "recommended_action": actions[bucket],
                "risk_flags": risk_flags,
            }
        )

    priorities.sort(
        key=lambda item: (item["priority_score"], item["balance_due"]),
        reverse=True,
    )
    stats = await b2b_finance_service.receivable_stats(
        db,
        workspace_id=workspace_id,
        as_of=as_of,
    )
    return {
        "analysis_type": "b2b_collections",
        "as_of": as_of.isoformat(),
        "summary": {
            "open_invoice_count": stats["open_invoice_count"],
            "overdue_invoice_count": stats["overdue_invoice_count"],
            "outstanding_amount": str(_money(stats["outstanding_amount"])),
            "overdue_amount": str(_money(stats["overdue_amount"])),
            "action_required_count": sum(
                1 for item in priorities if item["recommended_action"] != "monitor"
            ),
            "aging": {
                key: {
                    "count": value["count"],
                    "amount": str(_money(value["amount"])),
                }
                for key, value in stats["aging"].items()
            },
        },
        "priorities": priorities,
        "requires_human_approval": True,
        "write_actions_performed": [],
    }
