"""Opportunity API endpoints (ADR IDENTITY-002 阶段①②).

路由层只做依赖注入与状态码映射；业务规则集中在
``app.services.opportunity_service``（AGENTS.md §2.3）。
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.workspace import get_workspace_id
from app.models.opportunity import OPPORTUNITY_STATUSES, SIGNAL_TYPES
from app.models.product import Product
from app.schemas.opportunity import (
    OpportunityCandidateIn,
    OpportunityCandidateOut,
    OpportunityCreate,
    OpportunityDetail,
    OpportunityMeta,
    OpportunityOut,
    OpportunityUpdate,
)
from app.services import opportunity_service
from app.services.opportunity_service import (
    OpportunityAlreadyLinked,
    OpportunityError,
    OpportunityNotFound,
)

router = APIRouter(prefix="/opportunities", tags=["opportunities 机会池"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]


def _candidate_payload(
    link: Any, products: dict[UUID, Any]
) -> OpportunityCandidateOut:
    """Link row plus a denormalised product summary."""
    product = products.get(link.product_id)
    return OpportunityCandidateOut(
        id=link.id,
        opportunity_id=link.opportunity_id,
        product_id=link.product_id,
        linked_at=link.linked_at,
        link_reason=link.link_reason,
        product_sku=product.sku if product else None,
        product_name=product.name if product else None,
        product_status=product.status if product else None,
        candidate_status=product.candidate_status if product else None,
    )


def _opportunity_payload(opp: Any, candidate_count: int = 0) -> OpportunityOut:
    return OpportunityOut(
        id=opp.id,
        workspace_id=opp.workspace_id,
        title=opp.title,
        description=opp.description,
        category=opp.category,
        keywords=opp.keywords or [],
        signal_type=opp.signal_type,
        signal_source=opp.signal_source,
        market_signals=opp.market_signals or [],
        evidence=opp.evidence or [],
        status=opp.status,
        confidence=opp.confidence,
        closed_at=opp.closed_at,
        closed_reason=opp.closed_reason,
        created_at=opp.created_at,
        updated_at=opp.updated_at,
        candidate_count=candidate_count,
    )


@router.get("/meta", response_model=OpportunityMeta, summary="枚举字典")
async def get_meta() -> OpportunityMeta:
    """Vocabulary catalogue so the frontend never hardcodes enum values."""
    return OpportunityMeta(statuses=list(OPPORTUNITY_STATUSES),
                           signal_types=list(SIGNAL_TYPES))


@router.get("", response_model=list[OpportunityOut], summary="机会列表")
async def list_opportunities(
    db: DbSession,
    workspace_id: WorkspaceId,
    status: str | None = Query(default=None, max_length=16),
    category: str | None = Query(default=None, max_length=128),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[OpportunityOut]:
    """List opportunities, newest first."""
    rows, _total = await opportunity_service.list_opportunities(
        db,
        workspace_id=workspace_id,
        status=status,
        category=category,
        limit=limit,
        offset=offset,
    )
    return [_opportunity_payload(opp) for opp in rows]


@router.post("", response_model=OpportunityOut, status_code=status.HTTP_201_CREATED,
             summary="创建机会")
async def create_opportunity(
    payload: OpportunityCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> OpportunityOut:
    """Create an opportunity manually. 不自动从市场信号生成（设计文档 §2）。"""
    try:
        opp = await opportunity_service.create_opportunity(
            db, workspace_id=workspace_id, payload=payload
        )
    except OpportunityError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return _opportunity_payload(opp)


@router.get("/{opportunity_id}", response_model=OpportunityDetail, summary="机会详情")
async def get_opportunity(
    opportunity_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> OpportunityDetail:
    """Opportunity plus its attributed candidates."""
    try:
        opp = await opportunity_service.get_opportunity(
            db, workspace_id=workspace_id, opportunity_id=opportunity_id
        )
        links, count = await opportunity_service.list_candidates(
            db, workspace_id=workspace_id, opportunity_id=opportunity_id
        )
    except OpportunityNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"机会不存在: {exc}"
        ) from exc

    product_ids = {link.product_id for link in links}
    products: dict[UUID, Any] = {}
    for pid in product_ids:
        product = await db.get(Product, pid)
        if product is not None:
            products[pid] = product

    base = _opportunity_payload(opp, candidate_count=count)
    return OpportunityDetail(
        **base.model_dump(),
        candidates=[_candidate_payload(l, products) for l in links],
    )


@router.patch("/{opportunity_id}", response_model=OpportunityOut, summary="更新机会")
async def update_opportunity(
    opportunity_id: UUID,
    payload: OpportunityUpdate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> OpportunityOut:
    """Partial update: status / confidence / closed_reason / fields."""
    try:
        opp = await opportunity_service.update_opportunity(
            db, workspace_id=workspace_id, opportunity_id=opportunity_id,
            payload=payload,
        )
    except OpportunityNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"机会不存在: {exc}"
        ) from exc
    except OpportunityError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return _opportunity_payload(opp)


@router.get("/{opportunity_id}/candidates", response_model=list[OpportunityCandidateOut],
            summary="已关联候选")
async def list_candidates(
    opportunity_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> list[OpportunityCandidateOut]:
    try:
        links, _count = await opportunity_service.list_candidates(
            db, workspace_id=workspace_id, opportunity_id=opportunity_id
        )
    except OpportunityNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"机会不存在: {exc}"
        ) from exc

    products: dict[UUID, Any] = {}
    for link in links:
        product = await db.get(Product, link.product_id)
        if product is not None:
            products[link.product_id] = product
    return [_candidate_payload(link, products) for link in links]


@router.post("/{opportunity_id}/candidates", response_model=OpportunityCandidateOut,
             status_code=status.HTTP_201_CREATED, summary="关联候选")
async def link_candidate(
    opportunity_id: UUID,
    payload: OpportunityCandidateIn,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> OpportunityCandidateOut:
    """Attribute a candidate to this opportunity. 不推进 candidate_status。"""
    try:
        link = await opportunity_service.link_candidate(
            db, workspace_id=workspace_id, opportunity_id=opportunity_id,
            payload=payload,
        )
    except OpportunityNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"机会或产品不存在: {exc}",
        ) from exc
    except OpportunityAlreadyLinked as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

    product = await db.get(Product, link.product_id)
    return _candidate_payload(link, {link.product_id: product} if product else {})


@router.delete("/{opportunity_id}/candidates/{product_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="解除关联")
async def unlink_candidate(
    opportunity_id: UUID,
    product_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> None:
    try:
        await opportunity_service.unlink_candidate(
            db, workspace_id=workspace_id, opportunity_id=opportunity_id,
            product_id=product_id,
        )
    except OpportunityNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"关联关系不存在: {exc}"
        ) from exc
