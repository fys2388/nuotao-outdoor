"""Order ingestion service: WooCommerce webhook -> order -> event -> rule check.

The pipeline is deliberately sequential and auditable:

1. Idempotency guard on ``(workspace_id, external_order_id)`` (unique
   constraint backs this up for concurrent deliveries).
2. Contribution margin snapshot via the profit engine (all Decimal).
3. Rule engine ``check()`` for the PRICE / PROFIT / FULFILLMENT domains
   (no high-risk actions are executed automatically in M1.5).
4. Order + line items persisted with profit/rule snapshots and trace_id.
5. ``order.created`` event appended to the event log.

Costs come from ``product_cost`` when the SKU is matched; unknown costs are
assumed zero and flagged in the profit snapshot for later reconciliation.
"""

import logging
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.models.order import Order, OrderItem
from app.models.product import Product, ProductCost
from app.schemas.order import WebhookOrderPayload, WebhookResponse
from app.services import event_service, rule_engine
from app.services.profit_engine import (
    ProfitInput,
    assess_cost_confidence,
    calculate_contribution_margin,
)

logger = logging.getLogger(__name__)

ZERO = Decimal("0")

# Rule domains evaluated for every incoming order in M1.5.
ORDER_RULE_GROUPS: tuple[str, ...] = ("PRICE", "PROFIT", "FULFILLMENT")


class OrderIngestError(Exception):
    """Raised when an order cannot be ingested (caller returns 5xx)."""


def _discount_ratio(payload: WebhookOrderPayload) -> Decimal:
    """Discount ratio relative to the pre-discount subtotal."""
    if payload.subtotal == ZERO:
        return ZERO
    return payload.discount_total / payload.subtotal


async def _resolve_product_costs(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    line_items: list,
) -> tuple[Decimal, dict[str, str]]:
    """Sum the newest landing cost per unit for matched SKUs.

    Returns ``(total_cost, details)`` where details maps sku -> unit cost
    string for the profit snapshot (transparency for reconciliation).
    """
    skus = [item.sku for item in line_items if item.sku]
    if not skus:
        return ZERO, {}

    rows = (
        await session.execute(
            select(Product.sku, ProductCost.total_cost)
            .join(ProductCost, ProductCost.product_id == Product.id)
            .where(
                Product.workspace_id == workspace_id,
                Product.sku.in_(skus),
            )
            .order_by(Product.sku, ProductCost.valid_from.desc())
        )
    ).all()
    if not rows:
        return ZERO, {}

    latest: dict[str, Decimal] = {}
    for sku, total_cost in rows:
        latest.setdefault(sku, total_cost)

    total = ZERO
    details: dict[str, str] = {}
    for item in line_items:
        if item.sku and item.sku in latest:
            unit_cost = latest[item.sku]
            total += unit_cost * Decimal(item.quantity)
            details[item.sku] = str(unit_cost)
    return total, details


async def _estimate_payment_fee(payload: WebhookOrderPayload) -> Decimal:
    """Estimate the payment processing fee from configured rates."""
    settings = get_settings()
    fee = payload.total * settings.payment_fee_rate + settings.payment_fee_fixed
    return fee.quantize(Decimal("0.01"))


async def _build_rule_context(
    payload: WebhookOrderPayload,
    margin_rate: Decimal,
    cost_status: str,
    profit_confidence: str,
) -> dict:
    """Build the rule evaluation context for order domains."""
    return {
        "price": {
            "discount_ratio": float(_discount_ratio(payload)),
            "discount_total": str(payload.discount_total),
        },
        "profit": {
            "contribution_margin_rate": float(margin_rate),
            "cost_status": cost_status,
            "profit_confidence": profit_confidence,
        },
        "fulfillment": {
            "payment_status": payload.payment_status or "",
            "order_status": payload.status,
        },
    }


async def _run_rule_checks(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    context: dict,
    trace_id: str,
) -> dict:
    """Check every order rule domain; never executes high-risk actions."""
    checks: dict[str, dict] = {}
    for group in ORDER_RULE_GROUPS:
        result = await rule_engine.check(
            session,
            workspace_id=workspace_id,
            group=group,
            context=context,
            trace_id=trace_id,
        )
        checks[group] = {
            "all_passed": result.all_passed,
            "results": [item.model_dump() for item in result.results],
        }
    return checks


async def _find_order(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    external_order_id: str,
) -> Order | None:
    """Return an existing order for the external id, if any."""
    return (
        await session.execute(
            select(Order).where(
                Order.workspace_id == workspace_id,
                Order.external_order_id == external_order_id,
            )
        )
    ).scalar_one_or_none()


async def ingest_order(
    session: AsyncSession,
    payload: WebhookOrderPayload,
    *,
    workspace_id: UUID,
    trace_id: str,
) -> WebhookResponse:
    """Ingest an ORDER_CREATED webhook payload idempotently.

    Returns a ``WebhookResponse`` with status ``created`` or ``duplicate``.
    Raises ``OrderIngestError`` on unexpected persistence failures so the
    webhook layer can surface a 5xx and let WooCommerce retry.
    """
    external_order_id = str(payload.id)

    existing = await _find_order(
        session, workspace_id=workspace_id, external_order_id=external_order_id
    )
    if existing is not None:
        logger.info("order %s already ingested; duplicate delivery", external_order_id)
        return WebhookResponse(
            status="duplicate",
            order_id=str(existing.id),
            external_order_id=external_order_id,
            trace_id=trace_id,
        )

    product_cost, cost_details = await _resolve_product_costs(
        session, workspace_id=workspace_id, line_items=payload.line_items
    )
    line_skus = [item.sku for item in payload.line_items if item.sku]
    matched_skus = set(cost_details.keys()) & set(line_skus)
    confidence = assess_cost_confidence(matched=len(matched_skus), total=len(line_skus))

    payment_fee = await _estimate_payment_fee(payload)
    profit = calculate_contribution_margin(
        ProfitInput(
            revenue=payload.total,
            product_cost=product_cost,
            payment_fee=payment_fee,
            discount=payload.discount_total,
        )
    )
    context = await _build_rule_context(
        payload,
        profit.contribution_margin_rate,
        confidence.cost_status.value,
        confidence.profit_confidence.value,
    )
    checks = await _run_rule_checks(
        session, workspace_id=workspace_id, context=context, trace_id=trace_id
    )

    profit_snapshot = profit.as_snapshot()
    profit_snapshot["product_cost"] = str(product_cost)
    profit_snapshot["cost_details"] = cost_details
    profit_snapshot["payment_fee"] = str(payment_fee)
    profit_snapshot["discount"] = str(payload.discount_total)
    profit_snapshot["cost_status"] = confidence.cost_status.value
    profit_snapshot["profit_confidence"] = confidence.profit_confidence.value
    profit_snapshot["confidence_reasons"] = confidence.reasons + [
        "payment fee estimated from configured rates"
    ]

    order = Order(
        workspace_id=workspace_id,
        external_order_id=external_order_id,
        status="received",
        payment_status=payload.payment_status,
        currency=payload.currency,
        country=payload.country,
        payment_method=payload.payment_method,
        source="woocommerce",
        subtotal=payload.subtotal,
        shipping_total=payload.shipping_total,
        discount_total=payload.discount_total,
        tax_total=payload.tax_total,
        total=payload.total,
        payment_fee=payment_fee,
        profit_snapshot=profit_snapshot,
        rule_results=checks,
        trace_id=trace_id,
    )
    order.items = [
        OrderItem(
            workspace_id=workspace_id,
            external_item_id=str(item.id) if item.id is not None else None,
            sku=item.sku,
            name=item.name,
            quantity=item.quantity,
            unit_price=item.total / Decimal(item.quantity) if item.quantity else ZERO,
            line_total=item.total,
        )
        for item in payload.line_items
    ]

    session.add(order)
    try:
        await session.commit()
    except IntegrityError as exc:
        # Concurrent duplicate delivery raced past the pre-check.
        await session.rollback()
        existing = await _find_order(
            session, workspace_id=workspace_id, external_order_id=external_order_id
        )
        if existing is not None:
            logger.info("order %s ingested concurrently; duplicate delivery", external_order_id)
            return WebhookResponse(
                status="duplicate",
                order_id=str(existing.id),
                external_order_id=external_order_id,
                trace_id=trace_id,
            )
        raise OrderIngestError(f"failed to persist order: {exc}") from exc
    await session.refresh(order)

    event = await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="order.created",
        entity_type="order",
        entity_id=str(order.id),
        payload={
            "external_order_id": external_order_id,
            "total": str(order.total),
            "currency": order.currency,
            "profit": profit_snapshot,
            "rules": {
                group: {"all_passed": data["all_passed"]}
                for group, data in checks.items()
            },
        },
        trace_id=trace_id,
    )
    logger.info(
        "order %s ingested (event=%s) trace=%s", external_order_id, event.id, trace_id
    )

    return WebhookResponse(
        status="created",
        order_id=str(order.id),
        external_order_id=external_order_id,
        trace_id=trace_id,
        profit=profit_snapshot,
        rules=checks,
        events=[
            {
                "id": event.id,
                "event_type": event.event_type,
                "entity_type": event.entity_type,
                "entity_id": event.entity_id,
                "trace_id": event.trace_id,
            }
        ],
    )


# Allowed sort columns for GET /orders (whitelist to avoid SQL injection).
ORDER_SORT_COLUMNS: dict[str, object] = {
    "received_at": Order.received_at,
    "created_at": Order.created_at,
    "total": Order.total,
    "status": Order.status,
}


async def list_orders(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    status_filter: str | None = None,
    external_order_id: str | None = None,
    sku: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    sort_by: str = "received_at",
    sort_order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Order], int]:
    """Query orders for a workspace with filters, pagination and sorting.

    ``sku`` filters orders containing at least one matching line item.
    ``date_from``/``date_to`` bound the ``received_at`` column (ISO-8601).
    """
    filters = [Order.workspace_id == workspace_id]
    if status_filter:
        filters.append(Order.status == status_filter)
    if external_order_id:
        filters.append(Order.external_order_id == external_order_id)
    if sku:
        filters.append(Order.id.in_(select(OrderItem.order_id).where(OrderItem.sku == sku)))
    if date_from:
        filters.append(Order.received_at >= date_from)
    if date_to:
        filters.append(Order.received_at <= date_to)

    count_stmt = select(func.count()).select_from(Order).where(*filters)
    total = (await session.execute(count_stmt)).scalar_one()

    column = ORDER_SORT_COLUMNS.get(sort_by, Order.received_at)
    order_expr = column.desc() if sort_order == "desc" else column.asc()
    stmt: Select = (
        select(Order)
        .where(*filters)
        .order_by(order_expr, Order.id)
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows), total


async def get_order(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    order_id: UUID,
) -> Order | None:
    """Return one order with its line items eagerly loaded."""
    return (
        await session.execute(
            select(Order)
            .options(selectinload(Order.items))
            .where(
                Order.workspace_id == workspace_id,
                Order.id == order_id,
            )
        )
    ).scalar_one_or_none()
