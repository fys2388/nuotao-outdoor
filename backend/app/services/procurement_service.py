"""
Procurement Suggestion Service
Generates procurement suggestions based on product metrics:
- Profit margin
- Inventory level
- Selection score
- Listing status
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select

from app.models.product import Product, ProductCost
from app.models.product_intelligence import ProductScore
from app.models.supply_chain import PurchaseOrder, PurchaseOrderItem
from app.services import event_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class ProcurementSuggestion:
    """A single procurement suggestion."""

    product_id: str
    sku: str
    name: str
    category: str | None
    source_url: str | None
    priority: str  # high | medium | low
    reason: str
    suggested_quantity: int
    unit_cost: Decimal
    total_cost: Decimal
    profit_margin: Decimal | None
    selection_score: Decimal | None
    current_stock: int
    status: str
    candidate_status: str | None


async def generate_procurement_suggestions(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    min_margin: float = 0.3,
    low_stock_threshold: int = 20,
    limit: int = 50,
) -> dict[str, Any]:
    """Generate procurement suggestions for all products.

    Args:
        session: Database session
        workspace_id: Workspace ID
        min_margin: Minimum profit margin to consider (default 30%)
        low_stock_threshold: Stock level below which to flag as low stock
        limit: Maximum number of suggestions to return

    Returns:
        Dict with suggestions list and summary statistics
    """
    # Query all products with their cost and score
    result = await session.execute(
        select(Product)
        .where(Product.workspace_id == workspace_id)
        .order_by(Product.created_at.desc())
        .limit(limit * 2)  # Query more to allow filtering
    )
    products = result.scalars().all()

    suggestions: list[ProcurementSuggestion] = []

    for product in products:
        # Load cost
        cost_result = await session.execute(
            select(ProductCost).where(
                ProductCost.workspace_id == workspace_id,
                ProductCost.product_id == product.id,
            )
        )
        cost = cost_result.scalars().first()

        # Load latest score
        score_result = await session.execute(
            select(ProductScore)
            .where(
                ProductScore.workspace_id == workspace_id,
                ProductScore.product_id == product.id,
            )
            .order_by(ProductScore.scored_at.desc())
        )
        score = score_result.scalars().first()

        # Calculate metrics
        unit_cost = cost.total_landed_cost if cost else Decimal("0")
        total_cost = unit_cost * Decimal("10")  # Default suggest 10 units
        selection_score = score.total if score else None
        meta = product.meta if isinstance(product.meta, dict) else {}
        current_stock = meta.get("stock", 0)

        # T0.4 fix: profit_margin was previously assigned None and never computed,
        # so the high/medium-margin priority branches below were dead code. The
        # authoritative selling price lives in product.meta ("price", falling back
        # to "sale_price") — Product has no dedicated price column. Compute the
        # real gross margin = (price - landed_cost) / price. When there is no
        # valid positive selling price (or no cost), degrade honestly to None
        # rather than fabricating a margin (AGENTS.md §1.2: no fabricated data).
        profit_margin: Decimal | None = None
        raw_price = meta.get("price") or meta.get("sale_price")
        if raw_price is not None:
            try:
                selling_price = Decimal(str(raw_price))
            except (ArithmeticError, ValueError):
                selling_price = Decimal("0")
            if selling_price > 0 and unit_cost >= 0:
                profit_margin = (selling_price - unit_cost) / selling_price

        # Determine priority and reason
        priority = "low"
        reason = "Regular product"
        suggested_quantity = 10

        # High margin products
        if profit_margin and profit_margin >= Decimal(str(min_margin)):
            priority = "high"
            reason = f"High profit margin ({profit_margin * 100:.1f}%)"
            suggested_quantity = 50
        elif profit_margin and profit_margin >= Decimal("0.2"):
            priority = "medium"
            reason = f"Moderate profit margin ({profit_margin * 100:.1f}%)"
            suggested_quantity = 20

        # Low stock products
        if current_stock <= low_stock_threshold:
            if priority == "low":
                priority = "medium"
            reason += f" | Low stock ({current_stock} units)"
            suggested_quantity = max(suggested_quantity, 30)

        # High selection score products
        if selection_score and selection_score >= Decimal("70"):
            if priority == "low":
                priority = "medium"
            reason += f" | High selection score ({selection_score})"
            suggested_quantity = max(suggested_quantity, 20)

        # Already listed products need stock
        if product.status == "listed" or product.candidate_status == "winner":
            if priority == "low":
                priority = "medium"
            reason += " | Already listed, need stock保障"
            suggested_quantity = max(suggested_quantity, 30)

        # Calculate total cost
        total_cost = unit_cost * Decimal(str(suggested_quantity))

        suggestions.append(
            ProcurementSuggestion(
                product_id=str(product.id),
                sku=product.sku,
                name=product.name,
                category=product.category,
                source_url=product.source_url,
                priority=priority,
                reason=reason,
                suggested_quantity=suggested_quantity,
                unit_cost=unit_cost,
                total_cost=total_cost,
                profit_margin=profit_margin,
                selection_score=selection_score,
                current_stock=current_stock,
                status=product.status,
                candidate_status=product.candidate_status,
            )
        )

    # Sort by priority (high > medium > low)
    priority_order = {"high": 0, "medium": 1, "low": 2}
    suggestions.sort(key=lambda s: (priority_order.get(s.priority, 3), -s.suggested_quantity))

    # Limit results
    suggestions = suggestions[:limit]

    # Calculate summary
    high_priority = sum(1 for s in suggestions if s.priority == "high")
    medium_priority = sum(1 for s in suggestions if s.priority == "medium")
    low_priority = sum(1 for s in suggestions if s.priority == "low")
    total_units = sum(s.suggested_quantity for s in suggestions)
    total_estimated_cost = sum(s.total_cost for s in suggestions)

    return {
        "suggestions": [
            {
                "product_id": s.product_id,
                "sku": s.sku,
                "name": s.name,
                "category": s.category,
                "source_url": s.source_url,
                "priority": s.priority,
                "reason": s.reason,
                "suggested_quantity": s.suggested_quantity,
                "unit_cost": str(s.unit_cost),
                "total_cost": str(s.total_cost),
                "profit_margin": str(s.profit_margin) if s.profit_margin else None,
                "selection_score": str(s.selection_score) if s.selection_score else None,
                "current_stock": s.current_stock,
                "status": s.status,
                "candidate_status": s.candidate_status,
            }
            for s in suggestions
        ],
        "summary": {
            "total_products": len(suggestions),
            "high_priority": high_priority,
            "medium_priority": medium_priority,
            "low_priority": low_priority,
            "total_units": total_units,
            "total_estimated_cost": str(total_estimated_cost),
        },
    }


async def create_purchase_order(
    session: AsyncSession,
    product_id: str,
    quantity: int,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """创建采购单(真实写入 purchase_orders + purchase_order_items 表).

    Args:
        session: 数据库会话
        product_id: 产品 ID
        quantity: 采购数量
        params: 额外参数(supplier_id, unit_cost, workspace_id 等)

    Returns:
        采购单信息字典
    """
    params = params or {}

    # id 列是 UUID 类型:调用方(execution_router)常以字符串传入,需显式转换,
    # 否则 SQLAlchemy 绑定字符串到 UUID 列会抛 'str' object has no attribute 'hex'.
    def _to_uuid(value: Any) -> UUID | None:
        if value is None or isinstance(value, UUID):
            return value
        try:
            return UUID(str(value))
        except (ValueError, AttributeError, TypeError):
            return None

    product_uuid = _to_uuid(product_id)
    if product_uuid is None:
        return {"success": False, "error": f"产品 {product_id} 不存在"}

    # 查询产品信息
    product_result = await session.execute(select(Product).where(Product.id == product_uuid))
    product = product_result.scalar_one_or_none()
    if not product:
        return {"success": False, "error": f"产品 {product_id} 不存在"}

    workspace_uuid = _to_uuid(params.get("workspace_id")) or product.workspace_id
    supplier_uuid = _to_uuid(params.get("supplier_id"))
    unit_cost = float(params.get("unit_cost", 0))
    sku = params.get("sku") or product.sku or "UNKNOWN"
    product_name = product.name or "Unknown Product"

    # 生成唯一采购单号
    po_number = f"PO-AGENT-{int(datetime.now(timezone.utc).timestamp())}-{uuid.uuid4().hex[:6].upper()}"

    # 计算金额
    subtotal = unit_cost * quantity
    shipping_cost = float(params.get("shipping_cost", 0))
    total = subtotal + shipping_cost

    # 创建采购单
    # M4.2.0 T0.2 governance: Agent 创建的采购单一律进入 draft,绝不直接 approved.
    # approved 只能由受权限保护的显式审批操作(supply_chain.approve_purchase_order)
    # 产生;AI Agent 不得作为自行批准的授权主体.
    po_id = uuid.uuid4()
    po = PurchaseOrder(
        id=po_id,
        po_number=po_number,
        supplier_id=supplier_uuid,
        status="draft",
        currency=params.get("currency", "USD"),
        subtotal=subtotal,
        shipping_cost=shipping_cost,
        total=total,
        expected_delivery_at=datetime.now(timezone.utc) + timedelta(days=15),
        notes=params.get("notes", f"Agent 自动创建: {product_name} 补货 {quantity} 件"),
        trace_id=params.get("trace_id"),
        workspace_id=workspace_uuid,
    )
    session.add(po)

    # 创建采购单明细
    item = PurchaseOrderItem(
        id=uuid.uuid4(),
        purchase_order_id=po_id,
        product_id=product_uuid,
        sku=sku,
        name=product_name,
        quantity=quantity,
        unit_cost=unit_cost,
        line_total=subtotal,
        workspace_id=workspace_uuid,
    )
    session.add(item)

    await session.flush()

    # 审计事件:Agent 自动创建采购单必须落 event_service(trace_id 关联),
    # 且明确标注状态为 draft,供采购治理审计追溯(不得静默写入).
    await event_service.create_event(
        session,
        workspace_id=workspace_uuid,
        event_type="supply.purchase_order_created",
        entity_type="purchase_order",
        entity_id=str(po_id),
        payload={
            "po_number": po_number,
            "status": "draft",
            "product_id": str(product_uuid),
            "quantity": quantity,
            "total": str(total),
            "origin": "agent_auto",
        },
        trace_id=params.get("trace_id"),
        commit=False,
    )

    logger.info("Agent 自动创建采购单: %s product=%s qty=%d total=%.2f", po_number, product_name, quantity, total)

    return {
        "success": True,
        "po_number": po_number,
        "purchase_order_id": str(po_id),
        "product_id": product_id,
        "product_name": product_name,
        "sku": sku,
        "quantity": quantity,
        "unit_cost": str(unit_cost),
        "subtotal": str(subtotal),
        "total": str(total),
        "status": "draft",
        "supplier_id": str(supplier_uuid) if supplier_uuid else None,
        "expected_delivery_at": (datetime.now(timezone.utc) + timedelta(days=15)).isoformat(),
    }
