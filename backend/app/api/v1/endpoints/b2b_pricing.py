"""Internal B2B price book, version, approval, and tier APIs."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import (
    get_current_user,
    get_current_workspace_id,
    require_role,
)
from app.core.database import get_db
from app.core.tracing import get_trace_id
from app.models.b2b import B2BAgent, B2BPriceBook, B2BPriceTier, B2BPriceVersion
from app.models.product import Product
from app.schemas.b2b_pricing import (
    B2BPriceBookCreate,
    B2BPriceBookListResponse,
    B2BPriceBookResponse,
    B2BPricePreviewResponse,
    B2BPriceTierCreate,
    B2BPriceTierResponse,
    B2BPriceTierUpdate,
    B2BPriceVersionCreate,
    B2BPriceVersionDecision,
    B2BPriceVersionDetailResponse,
    B2BPriceVersionResponse,
)
from app.schemas.user import UserResponse
from app.services import b2b_pricing_service, event_service

router = APIRouter(prefix="/admin/b2b", tags=["admin-b2b-pricing"])
WorkspaceId = UUID
PricingEditor = Annotated[UserResponse, Depends(require_role("operator"))]


def _actor(user: UserResponse) -> str:
    return user.email or user.username


def _book_response(book: B2BPriceBook) -> B2BPriceBookResponse:
    return B2BPriceBookResponse(
        id=str(book.id),
        code=book.code,
        name=book.name,
        currency=book.currency,
        status=book.status,
        is_default=book.is_default,
        notes=book.notes,
        created_at=book.created_at,
        updated_at=book.updated_at,
    )


def _version_response(version: B2BPriceVersion) -> B2BPriceVersionResponse:
    return B2BPriceVersionResponse(
        id=str(version.id),
        price_book_id=str(version.price_book_id),
        version_number=version.version_number,
        status=version.status,
        effective_from=version.effective_from,
        effective_to=version.effective_to,
        submitted_by=version.submitted_by,
        submitted_at=version.submitted_at,
        approved_by=version.approved_by,
        approved_at=version.approved_at,
        rejection_reason=version.rejection_reason,
        created_by=version.created_by,
        notes=version.notes,
        tier_count=len(version.tiers) if "tiers" in version.__dict__ else 0,
        created_at=version.created_at,
        updated_at=version.updated_at,
    )


async def _tier_response(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    tier: B2BPriceTier,
    product: Product | None = None,
    agent: B2BAgent | None = None,
) -> B2BPriceTierResponse:
    if product is None:
        product = (
            await db.execute(
                select(Product).where(
                    Product.workspace_id == workspace_id,
                    Product.id == tier.product_id,
                )
            )
        ).scalar_one_or_none()
    if agent is None and tier.agent_id is not None:
        agent = (
            await db.execute(
                select(B2BAgent).where(
                    B2BAgent.workspace_id == workspace_id,
                    B2BAgent.id == tier.agent_id,
                )
            )
        ).scalar_one_or_none()
    return B2BPriceTierResponse(
        id=str(tier.id),
        price_version_id=str(tier.price_version_id),
        product_id=str(tier.product_id),
        product_name=product.name if product else "",
        product_sku=product.sku if product else "",
        tier=tier.tier,
        agent_id=str(tier.agent_id) if tier.agent_id else None,
        agent_company=agent.company_name if agent else None,
        min_quantity=tier.min_quantity,
        max_quantity=tier.max_quantity,
        unit_price=tier.unit_price,
        currency=tier.currency,
        is_active=tier.is_active,
        created_at=tier.created_at,
        updated_at=tier.updated_at,
    )


def _pricing_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, b2b_pricing_service.PricingConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, b2b_pricing_service.PricingStateError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, b2b_pricing_service.PricingError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=500, detail="pricing operation failed")


@router.get("/price-books", response_model=B2BPriceBookListResponse)
async def list_price_books(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BPriceBookListResponse:
    books, total = await b2b_pricing_service.list_price_books(
        db,
        workspace_id=workspace_id,
        page=page,
        page_size=page_size,
    )
    return B2BPriceBookListResponse(
        items=[_book_response(book) for book in books],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/price-books", response_model=B2BPriceBookResponse, status_code=201)
async def create_price_book(
    req: B2BPriceBookCreate,
    user: PricingEditor,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BPriceBookResponse:
    try:
        book = await b2b_pricing_service.create_price_book(
            db,
            workspace_id=workspace_id,
            code=req.code,
            name=req.name,
            currency=req.currency,
            created_by=_actor(user),
            is_default=req.is_default,
            notes=req.notes,
        )
    except b2b_pricing_service.PricingError as exc:
        raise _pricing_http_error(exc) from exc
    return _book_response(book)


@router.get(
    "/price-books/{price_book_id}/versions",
    response_model=list[B2BPriceVersionResponse],
)
async def list_price_versions(
    price_book_id: str,
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> list[B2BPriceVersionResponse]:
    book = await b2b_pricing_service.get_price_book(
        db,
        workspace_id=workspace_id,
        price_book_id=price_book_id,
    )
    if book is None:
        raise HTTPException(status_code=404, detail="Price book not found")
    versions = await b2b_pricing_service.list_price_versions(
        db,
        workspace_id=workspace_id,
        price_book_id=price_book_id,
    )
    return [_version_response(version) for version in versions]


@router.post(
    "/price-books/{price_book_id}/versions",
    response_model=B2BPriceVersionDetailResponse,
    status_code=201,
)
async def create_price_version(
    price_book_id: str,
    req: B2BPriceVersionCreate,
    user: PricingEditor,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BPriceVersionDetailResponse:
    try:
        version = await b2b_pricing_service.create_price_version(
            db,
            workspace_id=workspace_id,
            price_book_id=price_book_id,
            created_by=_actor(user),
            effective_from=req.effective_from,
            effective_to=req.effective_to,
            source_version_id=req.source_version_id,
            notes=req.notes,
        )
    except b2b_pricing_service.PricingError as exc:
        raise _pricing_http_error(exc) from exc
    if version is None:
        raise HTTPException(status_code=500, detail="Price version creation failed")
    tiers = [
        await _tier_response(db, workspace_id=workspace_id, tier=tier)
        for tier in version.tiers
    ]
    return B2BPriceVersionDetailResponse(
        **_version_response(version).model_dump(),
        tiers=tiers,
    )


@router.get(
    "/price-versions/{price_version_id}",
    response_model=B2BPriceVersionDetailResponse,
)
async def get_price_version(
    price_version_id: str,
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BPriceVersionDetailResponse:
    version = await b2b_pricing_service.get_price_version(
        db,
        workspace_id=workspace_id,
        price_version_id=price_version_id,
    )
    if version is None:
        raise HTTPException(status_code=404, detail="Price version not found")
    tiers = [
        await _tier_response(db, workspace_id=workspace_id, tier=tier)
        for tier in version.tiers
    ]
    return B2BPriceVersionDetailResponse(
        **_version_response(version).model_dump(),
        tiers=tiers,
    )


@router.post(
    "/price-versions/{price_version_id}/tiers",
    response_model=B2BPriceTierResponse,
    status_code=201,
)
async def create_price_tier(
    price_version_id: str,
    req: B2BPriceTierCreate,
    _user: PricingEditor,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BPriceTierResponse:
    try:
        tier = await b2b_pricing_service.create_price_tier(
            db,
            workspace_id=workspace_id,
            price_version_id=price_version_id,
            product_id=req.product_id,
            tier=req.tier,
            agent_id=req.agent_id,
            min_quantity=req.min_quantity,
            max_quantity=req.max_quantity,
            unit_price=req.unit_price,
            currency=req.currency,
            is_active=req.is_active,
        )
    except (b2b_pricing_service.PricingError, ValueError) as exc:
        raise _pricing_http_error(exc) from exc
    return await _tier_response(db, workspace_id=workspace_id, tier=tier)


@router.put(
    "/price-tiers/{price_tier_id}",
    response_model=B2BPriceTierResponse,
)
async def update_price_tier(
    price_tier_id: str,
    req: B2BPriceTierUpdate,
    _user: PricingEditor,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BPriceTierResponse:
    try:
        tier = await b2b_pricing_service.update_price_tier(
            db,
            workspace_id=workspace_id,
            price_tier_id=price_tier_id,
            min_quantity=req.min_quantity,
            max_quantity=req.max_quantity,
            unit_price=req.unit_price,
            is_active=req.is_active,
        )
    except (b2b_pricing_service.PricingError, ValueError) as exc:
        raise _pricing_http_error(exc) from exc
    return await _tier_response(db, workspace_id=workspace_id, tier=tier)


@router.delete(
    "/price-tiers/{price_tier_id}",
    status_code=204,
    response_class=Response,
)
async def delete_price_tier(
    price_tier_id: str,
    _user: PricingEditor,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> Response:
    try:
        await b2b_pricing_service.delete_price_tier(
            db,
            workspace_id=workspace_id,
            price_tier_id=price_tier_id,
        )
    except (b2b_pricing_service.PricingError, ValueError) as exc:
        raise _pricing_http_error(exc) from exc
    return Response(status_code=204)


@router.post(
    "/price-versions/{price_version_id}/submit",
    response_model=B2BPriceVersionResponse,
)
async def submit_price_version(
    price_version_id: str,
    user: PricingEditor,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BPriceVersionResponse:
    try:
        version = await b2b_pricing_service.submit_price_version(
            db,
            workspace_id=workspace_id,
            price_version_id=price_version_id,
            actor=_actor(user),
        )
    except b2b_pricing_service.PricingError as exc:
        raise _pricing_http_error(exc) from exc
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_price_version.submitted",
        entity_type="b2b_price_version",
        entity_id=str(version.id),
        payload={"actor": _actor(user), "version_number": version.version_number},
        trace_id=get_trace_id(),
    )
    return _version_response(version)


@router.post(
    "/price-versions/{price_version_id}/approve",
    response_model=B2BPriceVersionResponse,
)
async def approve_price_version(
    price_version_id: str,
    user: UserResponse = Depends(require_role("admin")),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BPriceVersionResponse:
    try:
        version = await b2b_pricing_service.approve_price_version(
            db,
            workspace_id=workspace_id,
            price_version_id=price_version_id,
            actor=_actor(user),
        )
    except b2b_pricing_service.PricingError as exc:
        raise _pricing_http_error(exc) from exc
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_price_version.approved",
        entity_type="b2b_price_version",
        entity_id=str(version.id),
        payload={"actor": _actor(user), "version_number": version.version_number},
        trace_id=get_trace_id(),
    )
    return _version_response(version)


@router.post(
    "/price-versions/{price_version_id}/reject",
    response_model=B2BPriceVersionResponse,
)
async def reject_price_version(
    price_version_id: str,
    req: B2BPriceVersionDecision,
    user: UserResponse = Depends(require_role("admin")),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BPriceVersionResponse:
    try:
        version = await b2b_pricing_service.reject_price_version(
            db,
            workspace_id=workspace_id,
            price_version_id=price_version_id,
            actor=_actor(user),
            reason=req.reason or "rejected",
        )
    except b2b_pricing_service.PricingError as exc:
        raise _pricing_http_error(exc) from exc
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_price_version.rejected",
        entity_type="b2b_price_version",
        entity_id=str(version.id),
        payload={
            "actor": _actor(user),
            "version_number": version.version_number,
            "reason": version.rejection_reason,
        },
        trace_id=get_trace_id(),
    )
    return _version_response(version)


@router.get(
    "/price-resolution/preview",
    response_model=B2BPricePreviewResponse,
)
async def preview_price_resolution(
    product_id: str,
    agent_id: str,
    quantity: int = Query(..., ge=1),
    as_of: date | None = None,
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BPricePreviewResponse:
    resolved = await b2b_pricing_service.preview_price_for_agent(
        db,
        workspace_id=workspace_id,
        product_id=product_id,
        agent_id=agent_id,
        quantity=quantity,
        as_of=as_of,
    )
    if resolved is None:
        raise HTTPException(status_code=404, detail="No active price matches this request")
    return B2BPricePreviewResponse(
        price_book_id=str(resolved.price_book_id),
        price_book_version_id=str(resolved.price_book_version_id),
        price_tier_id=str(resolved.price_tier_id),
        version_number=resolved.version_number,
        source=resolved.source,
        unit_price=resolved.unit_price,
        currency=resolved.currency,
        min_quantity=resolved.min_quantity,
        max_quantity=resolved.max_quantity,
    )
