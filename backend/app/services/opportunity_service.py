"""Opportunity service: market-signal aggregation and candidate attribution.

边界（设计文档 §2，违反即为 bug）：
- 不读写 product_scores / product_decisions —— 评分与决策各有唯一载体
- 不写入 products.candidate_status —— 归属关系不等于状态推进
- confidence 只接受人工填写，后端不做任何推断（AGENTS.md §1.2 禁止凭感觉）
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.opportunity import (
    OPPORTUNITY_STATUSES,
    SIGNAL_TYPES,
    Opportunity,
    OpportunityCandidate,
)
from app.models.product import Product
from app.schemas.opportunity import (
    OpportunityCandidateIn,
    OpportunityCreate,
    OpportunityUpdate,
)


class OpportunityError(Exception):
    """Invalid opportunity request payload."""


class OpportunityAlreadyLinked(Exception):
    """The same product is already attributed to this opportunity."""


class OpportunityNotFound(Exception):
    """Opportunity does not exist in the workspace."""


async def _get_or_404(
    session: AsyncSession, *, workspace_id: UUID, opportunity_id: UUID
) -> Opportunity:
    opp = await session.get(Opportunity, opportunity_id)
    if opp is None or opp.workspace_id != workspace_id:
        raise OpportunityNotFound(opportunity_id)
    return opp


async def list_opportunities(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    status: str | None = None,
    category: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[Sequence[Opportunity], int]:
    """List opportunities, newest first."""
    stmt = select(Opportunity).where(Opportunity.workspace_id == workspace_id)
    if status:
        stmt = stmt.where(Opportunity.status == status)
    if category:
        stmt = stmt.where(Opportunity.category == category)

    total = (
        await session.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()

    rows = (
        await session.execute(
            stmt.order_by(Opportunity.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()
    return rows, total


async def create_opportunity(
    session: AsyncSession, *, workspace_id: UUID, payload: OpportunityCreate
) -> Opportunity:
    """Create an opportunity. signal_type is validated here, not in the model."""
    if payload.signal_type not in SIGNAL_TYPES:
        raise OpportunityError(f"非法 signal_type: {payload.signal_type}")

    opp = Opportunity(
        workspace_id=workspace_id,
        title=payload.title,
        description=payload.description,
        category=payload.category,
        keywords=list(payload.keywords),
        signal_type=payload.signal_type,
        signal_source=payload.signal_source,
        market_signals=list(payload.market_signals),
        evidence=list(payload.evidence),
        confidence=payload.confidence,
    )
    session.add(opp)
    await session.commit()
    await session.refresh(opp)
    return opp


async def get_opportunity(
    session: AsyncSession, *, workspace_id: UUID, opportunity_id: UUID
) -> Opportunity:
    return await _get_or_404(
        session, workspace_id=workspace_id, opportunity_id=opportunity_id
    )


async def update_opportunity(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    opportunity_id: UUID,
    payload: OpportunityUpdate,
) -> Opportunity:
    """Partial update. Transitioning into a terminal status stamps closed_at."""
    opp = await _get_or_404(
        session, workspace_id=workspace_id, opportunity_id=opportunity_id
    )

    if payload.status is not None:
        if payload.status not in OPPORTUNITY_STATUSES:
            raise OpportunityError(f"非法 status: {payload.status}")
        terminal = payload.status in ("closed", "discarded")
        if terminal and opp.closed_at is None:
            opp.closed_at = datetime.now(UTC)
        elif payload.status in ("open", "evaluating", "converting"):
            opp.closed_at = None

    for field in ("title", "description", "category", "keywords",
                  "status", "confidence", "closed_reason"):
        value = getattr(payload, field)
        if value is not None:
            setattr(opp, field, value)

    await session.commit()
    await session.refresh(opp)
    return opp


async def list_candidates(
    session: AsyncSession, *, workspace_id: UUID, opportunity_id: UUID
) -> tuple[Sequence[OpportunityCandidate], int]:
    """List links with a denormalised product summary."""
    await _get_or_404(session, workspace_id=workspace_id, opportunity_id=opportunity_id)

    stmt = (
        select(OpportunityCandidate)
        .where(
            OpportunityCandidate.workspace_id == workspace_id,
            OpportunityCandidate.opportunity_id == opportunity_id,
        )
        .order_by(OpportunityCandidate.linked_at.desc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return rows, len(rows)


async def link_candidate(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    opportunity_id: UUID,
    payload: OpportunityCandidateIn,
) -> OpportunityCandidate:
    """Attribute a candidate to this opportunity (idempotent by unique constraint)."""
    opp = await _get_or_404(
        session, workspace_id=workspace_id, opportunity_id=opportunity_id
    )

    product = await session.get(Product, payload.product_id)
    if product is None or product.workspace_id != workspace_id:
        raise OpportunityNotFound(payload.product_id)

    existing = (
        await session.execute(
            select(OpportunityCandidate).where(
                OpportunityCandidate.workspace_id == workspace_id,
                OpportunityCandidate.opportunity_id == opportunity_id,
                OpportunityCandidate.product_id == payload.product_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise OpportunityAlreadyLinked(
            f"候选 {payload.product_id} 已归属机会 {opportunity_id}"
        )

    link = OpportunityCandidate(
        workspace_id=workspace_id,
        opportunity_id=opp.id,
        product_id=product.id,
        link_reason=payload.link_reason,
    )
    session.add(link)
    await session.commit()
    await session.refresh(link)
    return link


async def unlink_candidate(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    opportunity_id: UUID,
    product_id: UUID,
) -> None:
    link = (
        await session.execute(
            select(OpportunityCandidate).where(
                OpportunityCandidate.workspace_id == workspace_id,
                OpportunityCandidate.opportunity_id == opportunity_id,
                OpportunityCandidate.product_id == product_id,
            )
        )
    ).scalar_one_or_none()
    if link is None:
        raise OpportunityNotFound(product_id)
    await session.delete(link)
    await session.commit()
