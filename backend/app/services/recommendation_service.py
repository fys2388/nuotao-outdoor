"""Decision intelligence service (M4.3).

Business recommendations are proposals only: they are created in the
``proposed`` state and require explicit human approval or rejection. Nothing
is applied automatically and no business rule is ever modified by this
service. Each state transition is recorded in the event log.
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.connector import BusinessRecommendation
from app.schemas.recommendation import RecommendationCreate
from app.services import event_service

logger = logging.getLogger(__name__)


class RecommendationError(Exception):
    """Raised when a recommendation operation cannot complete."""


async def propose_recommendation(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: RecommendationCreate,
    trace_id: str | None = None,
) -> BusinessRecommendation:
    """Create a recommendation awaiting human approval (status=proposed)."""
    recommendation = BusinessRecommendation(
        workspace_id=workspace_id,
        domain=data.domain,
        entity_type=data.entity_type,
        entity_id=data.entity_id,
        recommendation=data.recommendation,
        reason=data.reason,
        confidence=data.confidence,
        status="proposed",
        trace_id=trace_id,
    )
    session.add(recommendation)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="business.recommendation_proposed",
        entity_type="recommendation",
        entity_id=str(recommendation.id),
        payload={
            "domain": data.domain,
            "entity_type": data.entity_type,
            "entity_id": data.entity_id,
            "confidence": str(data.confidence),
        },
        trace_id=trace_id,
    )
    logger.info(
        "recommendation %s proposed (%s) trace=%s", recommendation.id, data.domain, trace_id
    )
    await session.refresh(recommendation)
    return recommendation


async def _load_recommendation(
    session: AsyncSession, *, workspace_id: UUID, recommendation_id: UUID
) -> BusinessRecommendation | None:
    return (
        await session.execute(
            select(BusinessRecommendation).where(
                BusinessRecommendation.workspace_id == workspace_id,
                BusinessRecommendation.id == recommendation_id,
            )
        )
    ).scalar_one_or_none()


async def _decide(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    recommendation_id: UUID,
    actor: str,
    note: str | None,
    decision: str,
    trace_id: str | None,
) -> BusinessRecommendation:
    """Approve or reject a proposed recommendation (state machine guard)."""
    recommendation = await _load_recommendation(
        session, workspace_id=workspace_id, recommendation_id=recommendation_id
    )
    if recommendation is None:
        raise RecommendationError("recommendation not found")
    if recommendation.status != "proposed":
        raise RecommendationError(
            f"recommendation already {recommendation.status}; "
            "only proposed recommendations can be decided"
        )
    recommendation.status = decision
    recommendation.approved_by = actor
    recommendation.approved_at = datetime.now(UTC)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type=f"business.recommendation_{decision}",
        entity_type="recommendation",
        entity_id=str(recommendation.id),
        payload={"actor": actor, "note": note},
        trace_id=trace_id,
    )
    logger.info("recommendation %s %s by %s trace=%s", recommendation.id, decision, actor, trace_id)
    await session.refresh(recommendation)
    return recommendation


async def approve_recommendation(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    recommendation_id: UUID,
    actor: str,
    note: str | None = None,
    trace_id: str | None = None,
) -> BusinessRecommendation:
    """Approve a proposed recommendation (human-in-the-loop gate)."""
    return await _decide(
        session,
        workspace_id=workspace_id,
        recommendation_id=recommendation_id,
        actor=actor,
        note=note,
        decision="approved",
        trace_id=trace_id,
    )


async def reject_recommendation(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    recommendation_id: UUID,
    actor: str,
    note: str | None = None,
    trace_id: str | None = None,
) -> BusinessRecommendation:
    """Reject a proposed recommendation (human-in-the-loop gate)."""
    return await _decide(
        session,
        workspace_id=workspace_id,
        recommendation_id=recommendation_id,
        actor=actor,
        note=note,
        decision="rejected",
        trace_id=trace_id,
    )


async def list_recommendations(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    status: str | None = None,
    domain: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[BusinessRecommendation], int]:
    """Query recommendations (workspace-scoped) with optional filters."""
    filters = [BusinessRecommendation.workspace_id == workspace_id]
    if status:
        filters.append(BusinessRecommendation.status == status)
    if domain:
        filters.append(BusinessRecommendation.domain == domain)

    total = (
        await session.execute(
            select(func.count()).select_from(BusinessRecommendation).where(*filters)
        )
    ).scalar_one()
    rows = (
        (
            await session.execute(
                select(BusinessRecommendation)
                .where(*filters)
                .order_by(BusinessRecommendation.created_at.desc(), BusinessRecommendation.id)
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), total
