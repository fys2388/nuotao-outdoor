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
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product, ProductCost
from app.models.product_intelligence import ProductScore

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
        profit_margin = None
        selection_score = score.total if score else None
        current_stock = product.meta.get("stock", 0) if isinstance(product.meta, dict) else 0

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

        suggestions.append(ProcurementSuggestion(
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
        ))

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
