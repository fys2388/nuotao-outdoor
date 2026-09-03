"""Customer intelligence endpoints (M3.3): profiles, interactions, reviews, refunds, knowledge.

Data capture only - no Customer Agent, no automatic customer support.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.tracing import get_trace_id
from app.core.workspace import get_workspace_id
from app.schemas.customer import (
    CustomerKnowledgeCreate,
    CustomerKnowledgeOut,
    CustomerProfileCreate,
    CustomerProfileOut,
    CustomerProfileUpdate,
    InteractionCreate,
    InteractionOut,
    InteractionUpdate,
    RefundCreate,
    RefundOut,
    RefundStatsOut,
    RefundUpdate,
    ReviewCreate,
    ReviewOut,
    ReviewUpdate,
)
from app.services import customer

router = APIRouter(tags=["customer-intelligence"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]


def _http_error(exc: customer.CustomerError) -> HTTPException:
    """Map service errors: missing -> 404, conflict -> 409, others -> 400."""
    message = str(exc)
    if "not found" in message:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)
    if "already exists" in message:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


# --------------------------------------------------------------------------- #
# Customer profiles
# --------------------------------------------------------------------------- #


@router.post(
    "/customer-profiles",
    response_model=CustomerProfileOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a non-PII customer profile",
)
async def create_profile(
    body: CustomerProfileCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> CustomerProfileOut:
    """Create a profile; duplicate reference id returns 409."""
    try:
        profile = await customer.create_profile(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except customer.CustomerError as exc:
        raise _http_error(exc) from exc
    return CustomerProfileOut.model_validate(profile)


@router.get(
    "/customer-profiles",
    response_model=list[CustomerProfileOut],
    summary="List customer profiles",
)
async def list_profiles(
    db: DbSession,
    workspace_id: WorkspaceId,
    segment: str | None = Query(default=None, max_length=32),
    country: str | None = Query(default=None, max_length=8),
    limit: int = 50,
    offset: int = 0,
) -> list[CustomerProfileOut]:
    """Return profiles, newest first, with optional filters."""
    rows = await customer.list_profiles(
        db,
        workspace_id=workspace_id,
        segment=segment,
        country=country,
        limit=limit,
        offset=offset,
    )
    return [CustomerProfileOut.model_validate(row) for row in rows]


@router.get(
    "/customer-profiles/{profile_id}",
    response_model=CustomerProfileOut,
    summary="Get a customer profile",
)
async def get_profile(
    profile_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> CustomerProfileOut:
    """Return one profile by internal id."""
    profile = await customer.get_profile(db, workspace_id=workspace_id, profile_id=profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not found")
    return CustomerProfileOut.model_validate(profile)


@router.put(
    "/customer-profiles/{profile_id}",
    response_model=CustomerProfileOut,
    summary="Update a customer profile",
)
async def update_profile(
    profile_id: UUID,
    body: CustomerProfileUpdate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> CustomerProfileOut:
    """Partially update a profile (no PII fields exist)."""
    try:
        profile = await customer.update_profile(
            db,
            workspace_id=workspace_id,
            profile_id=profile_id,
            data=body,
            trace_id=get_trace_id(),
        )
    except customer.CustomerError as exc:
        raise _http_error(exc) from exc
    return CustomerProfileOut.model_validate(profile)


@router.delete(
    "/customer-profiles/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a customer profile",
)
async def delete_profile(
    profile_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> None:
    """Delete a profile (audited via event)."""
    try:
        await customer.delete_profile(
            db, workspace_id=workspace_id, profile_id=profile_id, trace_id=get_trace_id()
        )
    except customer.CustomerError as exc:
        raise _http_error(exc) from exc


# --------------------------------------------------------------------------- #
# Customer interactions
# --------------------------------------------------------------------------- #


@router.post(
    "/customer-interactions",
    response_model=InteractionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record a customer interaction",
)
async def create_interaction(
    body: InteractionCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> InteractionOut:
    """Record an email/chat/review/social interaction (content immutable)."""
    try:
        interaction = await customer.create_interaction(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except customer.CustomerError as exc:
        raise _http_error(exc) from exc
    return InteractionOut.model_validate(interaction)


@router.get(
    "/customer-interactions",
    response_model=list[InteractionOut],
    summary="List customer interactions",
)
async def list_interactions(
    db: DbSession,
    workspace_id: WorkspaceId,
    customer_id: Annotated[UUID | None, Query()] = None,
    channel: str | None = Query(default=None, max_length=16),
    sentiment: str | None = Query(default=None, max_length=16),
    limit: int = 50,
) -> list[InteractionOut]:
    """Return interactions, newest first, with optional filters."""
    rows = await customer.list_interactions(
        db,
        workspace_id=workspace_id,
        customer_id=customer_id,
        channel=channel,
        sentiment=sentiment,
        limit=limit,
    )
    return [InteractionOut.model_validate(row) for row in rows]


@router.get(
    "/customer-interactions/{interaction_id}",
    response_model=InteractionOut,
    summary="Get a customer interaction",
)
async def get_interaction(
    interaction_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> InteractionOut:
    """Return one interaction by internal id."""
    interaction = await customer._load_interaction(
        db, workspace_id=workspace_id, interaction_id=interaction_id
    )
    if interaction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="interaction not found")
    return InteractionOut.model_validate(interaction)


@router.put(
    "/customer-interactions/{interaction_id}",
    response_model=InteractionOut,
    summary="Update interaction classification",
)
async def update_interaction(
    interaction_id: UUID,
    body: InteractionUpdate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> InteractionOut:
    """Update sentiment/type/metadata; content stays immutable."""
    try:
        interaction = await customer.update_interaction(
            db,
            workspace_id=workspace_id,
            interaction_id=interaction_id,
            data=body,
            trace_id=get_trace_id(),
        )
    except customer.CustomerError as exc:
        raise _http_error(exc) from exc
    return InteractionOut.model_validate(interaction)


@router.delete(
    "/customer-interactions/{interaction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a customer interaction",
)
async def delete_interaction(
    interaction_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> None:
    """Delete an interaction (audited via event)."""
    try:
        await customer.delete_interaction(
            db, workspace_id=workspace_id, interaction_id=interaction_id, trace_id=get_trace_id()
        )
    except customer.CustomerError as exc:
        raise _http_error(exc) from exc


# --------------------------------------------------------------------------- #
# Product reviews
# --------------------------------------------------------------------------- #


@router.post(
    "/product-reviews",
    response_model=ReviewOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record a product review",
)
async def create_review(
    body: ReviewCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ReviewOut:
    """Record a review (content immutable afterwards)."""
    try:
        review = await customer.create_review(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except customer.CustomerError as exc:
        raise _http_error(exc) from exc
    return ReviewOut.model_validate(review)


@router.get(
    "/product-reviews",
    response_model=list[ReviewOut],
    summary="List product reviews",
)
async def list_reviews(
    db: DbSession,
    workspace_id: WorkspaceId,
    product_id: Annotated[UUID | None, Query()] = None,
    platform: str | None = Query(default=None, max_length=16),
    sentiment: str | None = Query(default=None, max_length=16),
    limit: int = 50,
) -> list[ReviewOut]:
    """Return reviews, newest first, with optional filters."""
    rows = await customer.list_reviews(
        db,
        workspace_id=workspace_id,
        product_id=product_id,
        platform=platform,
        sentiment=sentiment,
        limit=limit,
    )
    return [ReviewOut.model_validate(row) for row in rows]


@router.put(
    "/product-reviews/{review_id}",
    response_model=ReviewOut,
    summary="Update review classification",
)
async def update_review(
    review_id: UUID,
    body: ReviewUpdate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ReviewOut:
    """Update sentiment/issue/keywords; content stays immutable."""
    try:
        review = await customer.update_review(
            db,
            workspace_id=workspace_id,
            review_id=review_id,
            data=body,
            trace_id=get_trace_id(),
        )
    except customer.CustomerError as exc:
        raise _http_error(exc) from exc
    return ReviewOut.model_validate(review)


@router.delete(
    "/product-reviews/{review_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a product review",
)
async def delete_review(
    review_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> None:
    """Delete a review (audited via event)."""
    try:
        await customer.delete_review(
            db, workspace_id=workspace_id, review_id=review_id, trace_id=get_trace_id()
        )
    except customer.CustomerError as exc:
        raise _http_error(exc) from exc


# --------------------------------------------------------------------------- #
# Refund intelligence
# --------------------------------------------------------------------------- #


@router.post(
    "/refund-cases",
    response_model=RefundOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record a refund case",
)
async def create_refund(
    body: RefundCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> RefundOut:
    """Record a refund/return case with Decimal amount."""
    try:
        refund = await customer.create_refund(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except customer.CustomerError as exc:
        raise _http_error(exc) from exc
    return RefundOut.model_validate(refund)


@router.get(
    "/refund-cases",
    response_model=list[RefundOut],
    summary="List refund cases",
)
async def list_refunds(
    db: DbSession,
    workspace_id: WorkspaceId,
    category: str | None = Query(default=None, max_length=32),
    product_id: Annotated[UUID | None, Query()] = None,
    resolution: str | None = Query(default=None, max_length=32),
    limit: int = 50,
) -> list[RefundOut]:
    """Return refund cases, newest first, with optional filters."""
    rows = await customer.list_refunds(
        db,
        workspace_id=workspace_id,
        category=category,
        product_id=product_id,
        resolution=resolution,
        limit=limit,
    )
    return [RefundOut.model_validate(row) for row in rows]


@router.get(
    "/refund-cases/stats",
    response_model=list[RefundStatsOut],
    summary="Refund statistics by category",
)
async def refund_stats(
    db: DbSession,
    workspace_id: WorkspaceId,
) -> list[RefundStatsOut]:
    """Aggregate refunds by category: case count + total amount."""
    rows = await customer.refund_stats(db, workspace_id=workspace_id)
    return [RefundStatsOut.model_validate(row) for row in rows]


@router.put(
    "/refund-cases/{refund_id}",
    response_model=RefundOut,
    summary="Update a refund case",
)
async def update_refund(
    refund_id: UUID,
    body: RefundUpdate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> RefundOut:
    """Partially update a refund case."""
    try:
        refund = await customer.update_refund(
            db,
            workspace_id=workspace_id,
            refund_id=refund_id,
            data=body,
            trace_id=get_trace_id(),
        )
    except customer.CustomerError as exc:
        raise _http_error(exc) from exc
    return RefundOut.model_validate(refund)


@router.delete(
    "/refund-cases/{refund_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a refund case",
)
async def delete_refund(
    refund_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> None:
    """Delete a refund case (audited via event)."""
    try:
        await customer.delete_refund(
            db, workspace_id=workspace_id, refund_id=refund_id, trace_id=get_trace_id()
        )
    except customer.CustomerError as exc:
        raise _http_error(exc) from exc


# --------------------------------------------------------------------------- #
# Customer knowledge memory
# --------------------------------------------------------------------------- #


@router.post(
    "/customer-knowledge-entries",
    response_model=CustomerKnowledgeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a customer knowledge entry",
)
async def create_knowledge_entry(
    body: CustomerKnowledgeCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> CustomerKnowledgeOut:
    """Record a purchase/pain/segment/refund/loyalty pattern."""
    try:
        entry = await customer.create_knowledge_entry(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except customer.CustomerError as exc:
        raise _http_error(exc) from exc
    return CustomerKnowledgeOut.model_validate(entry)


@router.get(
    "/customer-knowledge-entries",
    response_model=list[CustomerKnowledgeOut],
    summary="Query customer knowledge entries",
)
async def list_knowledge_entries(
    db: DbSession,
    workspace_id: WorkspaceId,
    category: str | None = Query(default=None, max_length=64),
    entry_type: str | None = Query(default=None, max_length=32),
    customer_id: Annotated[UUID | None, Query()] = None,
    product_id: Annotated[UUID | None, Query()] = None,
    limit: int = 100,
) -> list[CustomerKnowledgeOut]:
    """Return matching entries, newest first."""
    rows = await customer.list_knowledge_entries(
        db,
        workspace_id=workspace_id,
        category=category,
        entry_type=entry_type,
        customer_id=customer_id,
        product_id=product_id,
        limit=limit,
    )
    return [CustomerKnowledgeOut.model_validate(row) for row in rows]
