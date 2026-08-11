"""Customer intelligence service (M3.3): profiles, interactions, reviews, refunds, knowledge.

Pure data layer for the future Customer Agent. **No Customer Agent, no
automatic customer support.** PII policy: profiles/interactions/reviews/refunds
store only non-identifying references and behavioral data; free-form metadata
is scanned for PII keys and rejected. All writes emit events with trace_id.
"""

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import (
    CustomerInteraction,
    CustomerKnowledgeEntry,
    CustomerProfile,
    ProductReview,
    RefundCase,
)
from app.models.order import Order
from app.models.product import Product
from app.schemas.customer import (
    CustomerKnowledgeCreate,
    CustomerProfileCreate,
    CustomerProfileUpdate,
    InteractionCreate,
    InteractionUpdate,
    RefundCreate,
    RefundUpdate,
    ReviewCreate,
    ReviewUpdate,
)
from app.services import event_service

logger = logging.getLogger(__name__)

ZERO = Decimal("0")

# Keys never allowed in free-form metadata (defense in depth; the schemas
# already have no PII fields at all).
PII_KEYS: tuple[str, ...] = (
    "email",
    "phone",
    "mobile",
    "name",
    "first_name",
    "last_name",
    "address",
    "street",
    "city",
    "zip",
    "postal_code",
    "ip",
    "ssn",
    "credit_card",
    "card_number",
    "birth",
    "birthday",
)


class CustomerError(Exception):
    """Raised when a customer operation cannot complete."""


def _assert_no_pii(data: dict[str, Any], field: str = "metadata") -> None:
    """Reject free-form metadata containing obvious PII keys."""
    for key in data:
        normalized = key.lower().replace(" ", "_").replace("-", "_")
        if normalized in PII_KEYS:
            raise CustomerError(f"PII not allowed in {field}: {key}")


async def _ensure_product(
    session: AsyncSession, *, workspace_id: UUID, product_id: UUID | None
) -> None:
    if product_id is None:
        return
    exists = (
        await session.execute(
            select(Product.id).where(
                Product.workspace_id == workspace_id, Product.id == product_id
            )
        )
    ).scalar_one_or_none()
    if exists is None:
        raise CustomerError("product not found")


async def _ensure_order(
    session: AsyncSession, *, workspace_id: UUID, order_id: UUID | None
) -> None:
    if order_id is None:
        return
    exists = (
        await session.execute(
            select(Order.id).where(
                Order.workspace_id == workspace_id, Order.id == order_id
            )
        )
    ).scalar_one_or_none()
    if exists is None:
        raise CustomerError("order not found")


# --------------------------------------------------------------------------- #
# Customer profiles
# --------------------------------------------------------------------------- #


async def create_profile(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: CustomerProfileCreate,
    trace_id: str | None = None,
) -> CustomerProfile:
    """Create a non-PII customer profile (reference id unique per workspace)."""
    profile = CustomerProfile(
        workspace_id=workspace_id,
        customer_reference_id=data.customer_reference_id,
        country=data.country,
        language=data.language,
        segment=data.segment,
        tags=data.tags,
        first_order_at=data.first_order_at,
        total_orders=data.total_orders,
        total_revenue=data.total_revenue,
        trace_id=trace_id,
    )
    session.add(profile)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise CustomerError(
            f"profile '{data.customer_reference_id}' already exists"
        ) from exc
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="customer.profile_created",
        entity_type="customer_profile",
        entity_id=str(profile.id),
        payload={
            "customer_reference_id": data.customer_reference_id,
            "segment": data.segment,
            "country": data.country,
        },
        trace_id=trace_id,
    )
    logger.info("customer profile %s created trace=%s", profile.id, trace_id)
    return profile


async def _load_profile(
    session: AsyncSession, *, workspace_id: UUID, profile_id: UUID
) -> CustomerProfile | None:
    return (
        await session.execute(
            select(CustomerProfile).where(
                CustomerProfile.workspace_id == workspace_id,
                CustomerProfile.id == profile_id,
            )
        )
    ).scalar_one_or_none()


async def get_profile(
    session: AsyncSession, *, workspace_id: UUID, profile_id: UUID
) -> CustomerProfile | None:
    """Return one profile or None (workspace-scoped)."""
    return await _load_profile(
        session, workspace_id=workspace_id, profile_id=profile_id
    )


async def update_profile(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    profile_id: UUID,
    data: CustomerProfileUpdate,
    trace_id: str | None = None,
) -> CustomerProfile:
    """Partially update a profile (no PII fields exist)."""
    profile = await _load_profile(
        session, workspace_id=workspace_id, profile_id=profile_id
    )
    if profile is None:
        raise CustomerError("profile not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(profile, key, value)
    profile.updated_at = datetime.now(UTC)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="customer.profile_updated",
        entity_type="customer_profile",
        entity_id=str(profile.id),
        payload={"segment": profile.segment},
        trace_id=trace_id,
    )
    return profile


async def list_profiles(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    segment: str | None = None,
    country: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[CustomerProfile]:
    """List profiles, newest first, with optional segment/country filters."""
    stmt = select(CustomerProfile).where(
        CustomerProfile.workspace_id == workspace_id
    )
    if segment:
        stmt = stmt.where(CustomerProfile.segment == segment)
    if country:
        stmt = stmt.where(CustomerProfile.country == country)
    stmt = stmt.order_by(CustomerProfile.created_at.desc()).limit(limit).offset(offset)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


async def delete_profile(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    profile_id: UUID,
    trace_id: str | None = None,
) -> None:
    """Delete a profile (audited via event)."""
    profile = await _load_profile(
        session, workspace_id=workspace_id, profile_id=profile_id
    )
    if profile is None:
        raise CustomerError("profile not found")
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="customer.profile_deleted",
        entity_type="customer_profile",
        entity_id=str(profile.id),
        payload={"customer_reference_id": profile.customer_reference_id},
        trace_id=trace_id,
    )
    await session.delete(profile)
    await session.flush()


# --------------------------------------------------------------------------- #
# Customer interactions (append-only content)
# --------------------------------------------------------------------------- #


async def create_interaction(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: InteractionCreate,
    trace_id: str | None = None,
) -> CustomerInteraction:
    """Record one customer interaction (content immutable afterwards)."""
    _assert_no_pii(data.metadata)
    if data.customer_id is not None:
        profile = await _load_profile(
            session, workspace_id=workspace_id, profile_id=data.customer_id
        )
        if profile is None:
            raise CustomerError("customer profile not found")
    await _ensure_product(
        session, workspace_id=workspace_id, product_id=data.product_id
    )
    interaction = CustomerInteraction(
        workspace_id=workspace_id,
        customer_id=data.customer_id,
        product_id=data.product_id,
        channel=data.channel,
        interaction_type=data.interaction_type,
        content=data.content,
        sentiment=data.sentiment,
        metadata_json=data.metadata,
        trace_id=trace_id,
    )
    session.add(interaction)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="customer.interaction_created",
        entity_type="customer_interaction",
        entity_id=str(interaction.id),
        payload={
            "customer_id": str(data.customer_id) if data.customer_id else None,
            "channel": data.channel,
            "sentiment": data.sentiment,
        },
        trace_id=trace_id,
    )
    logger.info("customer interaction %s created trace=%s", interaction.id, trace_id)
    return interaction


async def _load_interaction(
    session: AsyncSession, *, workspace_id: UUID, interaction_id: UUID
) -> CustomerInteraction | None:
    return (
        await session.execute(
            select(CustomerInteraction).where(
                CustomerInteraction.workspace_id == workspace_id,
                CustomerInteraction.id == interaction_id,
            )
        )
    ).scalar_one_or_none()


async def update_interaction(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    interaction_id: UUID,
    data: InteractionUpdate,
    trace_id: str | None = None,
) -> CustomerInteraction:
    """Update classification fields; original content stays immutable."""
    interaction = await _load_interaction(
        session, workspace_id=workspace_id, interaction_id=interaction_id
    )
    if interaction is None:
        raise CustomerError("interaction not found")
    updates = data.model_dump(exclude_unset=True)
    if "metadata" in updates:
        _assert_no_pii(updates["metadata"])
        interaction.metadata_json = updates.pop("metadata")
    for key, value in updates.items():
        setattr(interaction, key, value)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="customer.interaction_updated",
        entity_type="customer_interaction",
        entity_id=str(interaction.id),
        payload={"sentiment": interaction.sentiment},
        trace_id=trace_id,
    )
    return interaction


async def list_interactions(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    customer_id: UUID | None = None,
    channel: str | None = None,
    sentiment: str | None = None,
    limit: int = 50,
) -> list[CustomerInteraction]:
    """List interactions, newest first, with optional filters."""
    stmt = select(CustomerInteraction).where(
        CustomerInteraction.workspace_id == workspace_id
    )
    if customer_id is not None:
        stmt = stmt.where(CustomerInteraction.customer_id == customer_id)
    if channel:
        stmt = stmt.where(CustomerInteraction.channel == channel)
    if sentiment:
        stmt = stmt.where(CustomerInteraction.sentiment == sentiment)
    stmt = stmt.order_by(CustomerInteraction.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


async def delete_interaction(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    interaction_id: UUID,
    trace_id: str | None = None,
) -> None:
    """Delete an interaction (audited via event)."""
    interaction = await _load_interaction(
        session, workspace_id=workspace_id, interaction_id=interaction_id
    )
    if interaction is None:
        raise CustomerError("interaction not found")
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="customer.interaction_deleted",
        entity_type="customer_interaction",
        entity_id=str(interaction.id),
        payload={"channel": interaction.channel},
        trace_id=trace_id,
    )
    await session.delete(interaction)
    await session.flush()


# --------------------------------------------------------------------------- #
# Product reviews (append-only content)
# --------------------------------------------------------------------------- #


async def create_review(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: ReviewCreate,
    trace_id: str | None = None,
) -> ProductReview:
    """Record one product review (content immutable afterwards)."""
    await _ensure_product(
        session, workspace_id=workspace_id, product_id=data.product_id
    )
    review = ProductReview(
        workspace_id=workspace_id,
        product_id=data.product_id,
        platform=data.platform,
        rating=data.rating,
        content=data.content,
        sentiment=data.sentiment,
        issue_type=data.issue_type,
        keywords=data.keywords,
        trace_id=trace_id,
    )
    session.add(review)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="customer.review_created",
        entity_type="product_review",
        entity_id=str(review.id),
        payload={
            "product_id": str(data.product_id) if data.product_id else None,
            "rating": data.rating,
            "sentiment": data.sentiment,
        },
        trace_id=trace_id,
    )
    logger.info("product review %s created trace=%s", review.id, trace_id)
    return review


async def _load_review(
    session: AsyncSession, *, workspace_id: UUID, review_id: UUID
) -> ProductReview | None:
    return (
        await session.execute(
            select(ProductReview).where(
                ProductReview.workspace_id == workspace_id,
                ProductReview.id == review_id,
            )
        )
    ).scalar_one_or_none()


async def update_review(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    review_id: UUID,
    data: ReviewUpdate,
    trace_id: str | None = None,
) -> ProductReview:
    """Update classification; original content stays immutable."""
    review = await _load_review(
        session, workspace_id=workspace_id, review_id=review_id
    )
    if review is None:
        raise CustomerError("review not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(review, key, value)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="customer.review_updated",
        entity_type="product_review",
        entity_id=str(review.id),
        payload={"sentiment": review.sentiment},
        trace_id=trace_id,
    )
    return review


async def list_reviews(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID | None = None,
    platform: str | None = None,
    sentiment: str | None = None,
    limit: int = 50,
) -> list[ProductReview]:
    """List reviews, newest first, with optional filters."""
    stmt = select(ProductReview).where(ProductReview.workspace_id == workspace_id)
    if product_id is not None:
        stmt = stmt.where(ProductReview.product_id == product_id)
    if platform:
        stmt = stmt.where(ProductReview.platform == platform)
    if sentiment:
        stmt = stmt.where(ProductReview.sentiment == sentiment)
    stmt = stmt.order_by(ProductReview.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


async def delete_review(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    review_id: UUID,
    trace_id: str | None = None,
) -> None:
    """Delete a review (audited via event)."""
    review = await _load_review(
        session, workspace_id=workspace_id, review_id=review_id
    )
    if review is None:
        raise CustomerError("review not found")
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="customer.review_deleted",
        entity_type="product_review",
        entity_id=str(review.id),
        payload={"product_id": str(review.product_id) if review.product_id else None},
        trace_id=trace_id,
    )
    await session.delete(review)
    await session.flush()


# --------------------------------------------------------------------------- #
# Refund intelligence
# --------------------------------------------------------------------------- #


async def create_refund(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: RefundCreate,
    trace_id: str | None = None,
) -> RefundCase:
    """Record a refund/return case (monetary fields are Decimal)."""
    await _ensure_order(session, workspace_id=workspace_id, order_id=data.order_id)
    await _ensure_product(
        session, workspace_id=workspace_id, product_id=data.product_id
    )
    refund = RefundCase(
        workspace_id=workspace_id,
        order_id=data.order_id,
        product_id=data.product_id,
        reason=data.reason,
        category=data.category,
        amount=data.amount,
        resolution=data.resolution,
        trace_id=trace_id,
    )
    session.add(refund)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="customer.refund_created",
        entity_type="refund_case",
        entity_id=str(refund.id),
        payload={
            "order_id": str(data.order_id) if data.order_id else None,
            "category": data.category,
            "amount": str(data.amount),
        },
        trace_id=trace_id,
    )
    logger.info("refund case %s created (category=%s) trace=%s", refund.id, data.category, trace_id)
    return refund


async def _load_refund(
    session: AsyncSession, *, workspace_id: UUID, refund_id: UUID
) -> RefundCase | None:
    return (
        await session.execute(
            select(RefundCase).where(
                RefundCase.workspace_id == workspace_id,
                RefundCase.id == refund_id,
            )
        )
    ).scalar_one_or_none()


async def update_refund(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    refund_id: UUID,
    data: RefundUpdate,
    trace_id: str | None = None,
) -> RefundCase:
    """Partially update a refund case."""
    refund = await _load_refund(
        session, workspace_id=workspace_id, refund_id=refund_id
    )
    if refund is None:
        raise CustomerError("refund not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(refund, key, value)
    refund.updated_at = datetime.now(UTC)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="customer.refund_updated",
        entity_type="refund_case",
        entity_id=str(refund.id),
        payload={"category": refund.category, "resolution": refund.resolution},
        trace_id=trace_id,
    )
    return refund


async def list_refunds(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    category: str | None = None,
    product_id: UUID | None = None,
    resolution: str | None = None,
    limit: int = 50,
) -> list[RefundCase]:
    """List refund cases, newest first, with optional filters."""
    stmt = select(RefundCase).where(RefundCase.workspace_id == workspace_id)
    if category:
        stmt = stmt.where(RefundCase.category == category)
    if product_id is not None:
        stmt = stmt.where(RefundCase.product_id == product_id)
    if resolution:
        stmt = stmt.where(RefundCase.resolution == resolution)
    stmt = stmt.order_by(RefundCase.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


async def refund_stats(
    session: AsyncSession, *, workspace_id: UUID
) -> list[dict[str, Any]]:
    """Aggregate refund cases by category: case_count + total_amount."""
    rows = (
        await session.execute(
            select(
                RefundCase.category,
                func.count(RefundCase.id),
                func.coalesce(func.sum(RefundCase.amount), ZERO),
            )
            .where(RefundCase.workspace_id == workspace_id)
            .group_by(RefundCase.category)
            .order_by(RefundCase.category)
        )
    ).all()
    return [
        {
            "category": category,
            "case_count": int(count),
            "total_amount": Decimal(total),
        }
        for category, count, total in rows
    ]


async def delete_refund(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    refund_id: UUID,
    trace_id: str | None = None,
) -> None:
    """Delete a refund case (audited via event)."""
    refund = await _load_refund(
        session, workspace_id=workspace_id, refund_id=refund_id
    )
    if refund is None:
        raise CustomerError("refund not found")
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="customer.refund_deleted",
        entity_type="refund_case",
        entity_id=str(refund.id),
        payload={"category": refund.category},
        trace_id=trace_id,
    )
    await session.delete(refund)
    await session.flush()


# --------------------------------------------------------------------------- #
# Customer knowledge memory
# --------------------------------------------------------------------------- #


async def create_knowledge_entry(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: CustomerKnowledgeCreate,
    trace_id: str | None = None,
) -> CustomerKnowledgeEntry:
    """Create one customer knowledge entry."""
    if data.customer_id is not None:
        profile = await _load_profile(
            session, workspace_id=workspace_id, profile_id=data.customer_id
        )
        if profile is None:
            raise CustomerError("customer profile not found")
    await _ensure_product(
        session, workspace_id=workspace_id, product_id=data.product_id
    )
    entry = CustomerKnowledgeEntry(
        workspace_id=workspace_id,
        customer_id=data.customer_id,
        product_id=data.product_id,
        category=data.category,
        entry_type=data.entry_type,
        title=data.title,
        content=data.content,
        tags=data.tags,
        source=data.source,
        confidence=data.confidence,
        trace_id=trace_id,
    )
    session.add(entry)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="customer.knowledge_created",
        entity_type="customer_profile",
        entity_id=str(data.customer_id) if data.customer_id else str(workspace_id),
        payload={
            "knowledge_id": str(entry.id),
            "entry_type": data.entry_type,
            "category": data.category,
        },
        trace_id=trace_id,
    )
    logger.info(
        "customer knowledge entry %s created (%s) trace=%s",
        entry.id, data.entry_type, trace_id,
    )
    return entry


async def list_knowledge_entries(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    category: str | None = None,
    entry_type: str | None = None,
    customer_id: UUID | None = None,
    product_id: UUID | None = None,
    limit: int = 100,
) -> list[CustomerKnowledgeEntry]:
    """Query customer knowledge entries, newest first."""
    stmt = select(CustomerKnowledgeEntry).where(
        CustomerKnowledgeEntry.workspace_id == workspace_id
    )
    if category:
        stmt = stmt.where(CustomerKnowledgeEntry.category == category)
    if entry_type:
        stmt = stmt.where(CustomerKnowledgeEntry.entry_type == entry_type)
    if customer_id is not None:
        stmt = stmt.where(CustomerKnowledgeEntry.customer_id == customer_id)
    if product_id is not None:
        stmt = stmt.where(CustomerKnowledgeEntry.product_id == product_id)
    stmt = stmt.order_by(CustomerKnowledgeEntry.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)
