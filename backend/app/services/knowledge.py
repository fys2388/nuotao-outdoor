"""Product knowledge memory service (M2.3).

Stores success/failure patterns and category insights learned from product
experiments and evaluations. Entries are queryable by category and/or product
so future AI agents can ground their recommendations in accumulated evidence.
"""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_intelligence import ProductKnowledgeEntry
from app.schemas.knowledge import KnowledgeEntryCreate

logger = logging.getLogger(__name__)

ENTRY_TYPES = ("success_pattern", "failure_pattern", "category_insight")


class KnowledgeError(Exception):
    """Raised when a knowledge operation cannot complete."""


async def create_knowledge_entry(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: KnowledgeEntryCreate,
    trace_id: str | None = None,
) -> ProductKnowledgeEntry:
    """Create one knowledge entry (optionally linked to a product/category)."""
    if data.entry_type not in ENTRY_TYPES:
        raise KnowledgeError(f"entry_type must be one of {ENTRY_TYPES}")
    if data.product_id is not None:
        product = (
            await session.execute(
                select(Product.id).where(
                    Product.workspace_id == workspace_id,
                    Product.id == data.product_id,
                )
            )
        ).scalar_one_or_none()
        if product is None:
            raise KnowledgeError("product not found")

    entry = ProductKnowledgeEntry(
        workspace_id=workspace_id,
        product_id=data.product_id,
        category=data.category,
        entry_type=data.entry_type,
        title=data.title,
        content=data.content,
        tags=data.tags,
        source=data.source,
        trace_id=trace_id,
    )
    session.add(entry)
    await session.flush()
    from app.services import event_service

    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="product.knowledge.created",
        entity_type="product",
        entity_id=str(data.product_id) if data.product_id else str(workspace_id),
        payload={
            "knowledge_id": str(entry.id),
            "entry_type": data.entry_type,
            "category": data.category,
        },
        trace_id=trace_id,
    )
    logger.info("knowledge entry %s created (%s) trace=%s", entry.id, data.entry_type, trace_id)
    return entry


async def list_knowledge_entries(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    category: str | None = None,
    product_id: UUID | None = None,
    entry_type: str | None = None,
    limit: int = 100,
) -> list[ProductKnowledgeEntry]:
    """Query knowledge entries by category and/or product, newest first."""
    stmt = select(ProductKnowledgeEntry).where(
        ProductKnowledgeEntry.workspace_id == workspace_id
    )
    if category:
        stmt = stmt.where(ProductKnowledgeEntry.category == category)
    if product_id is not None:
        stmt = stmt.where(ProductKnowledgeEntry.product_id == product_id)
    if entry_type:
        stmt = stmt.where(ProductKnowledgeEntry.entry_type == entry_type)
    stmt = stmt.order_by(ProductKnowledgeEntry.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)
