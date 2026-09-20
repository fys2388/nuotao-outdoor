"""Brand, legal-entity, attribution, and consolidated-report APIs."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import (
    get_current_user,
    get_current_workspace_id,
    require_role,
)
from app.core.database import get_db
from app.models.consolidation import Brand, CommerceAttribution, LegalEntity
from app.schemas.consolidation import (
    AttributionEntityType,
    AttributionGapListResponse,
    AttributionListResponse,
    AttributionReconcileResponse,
    AttributionResponse,
    BrandCreate,
    BrandListResponse,
    BrandResponse,
    BrandUpdate,
    CommerceAttributionUpsert,
    ConsolidatedReportResponse,
    EliminationDecisionRequest,
    EliminationRejectionRequest,
    LegalEntityCreate,
    LegalEntityListResponse,
    LegalEntityResponse,
    LegalEntityUpdate,
    ProductBrandAssignRequest,
    ProductBrandBulkAssignRequest,
    ProductBrandBulkAssignResponse,
    ProductBrandGapListResponse,
    ProductBrandResponse,
)
from app.schemas.user import UserResponse
from app.services import consolidation_service
from app.services.currency_service import CurrencyRateError

router = APIRouter(tags=["consolidation"])
logger = logging.getLogger(__name__)
DBSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_current_workspace_id)]
ConsolidationEditor = Annotated[UserResponse, Depends(require_role("operator"))]
ConsolidationAdmin = Annotated[UserResponse, Depends(require_role("admin"))]


def _actor(user: UserResponse) -> str:
    return user.email or user.username


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, consolidation_service.ConsolidationNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, consolidation_service.ConsolidationConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, consolidation_service.ConsolidationStateError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(
        exc,
        (
            consolidation_service.ConsolidationError,
            CurrencyRateError,
            ValueError,
        ),
    ):
        return HTTPException(status_code=422, detail=str(exc))
    logger.error(
        "unexpected consolidation operation failure",
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return HTTPException(status_code=500, detail="Consolidation operation failed")


def _legal_entity_response(row: LegalEntity) -> LegalEntityResponse:
    return LegalEntityResponse(
        id=str(row.id),
        code=row.code,
        name=row.name,
        legal_name=row.legal_name,
        country=row.country,
        functional_currency=row.functional_currency,
        status=row.status,
        notes=row.notes,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _brand_response(
    row: Brand,
    legal_entities: dict[UUID, LegalEntity],
) -> BrandResponse:
    legal_entity = (
        legal_entities.get(row.default_legal_entity_id)
        if row.default_legal_entity_id
        else None
    )
    return BrandResponse(
        id=str(row.id),
        code=row.code,
        name=row.name,
        status=row.status,
        default_legal_entity_id=(
            str(row.default_legal_entity_id)
            if row.default_legal_entity_id
            else None
        ),
        default_legal_entity_name=legal_entity.name if legal_entity else None,
        notes=row.notes,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _legal_entity_map(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    legal_entity_ids: set[UUID],
) -> dict[UUID, LegalEntity]:
    if not legal_entity_ids:
        return {}
    rows = (
        await db.execute(
            select(LegalEntity).where(
                LegalEntity.workspace_id == workspace_id,
                LegalEntity.id.in_(legal_entity_ids),
            )
        )
    ).scalars().all()
    return {row.id: row for row in rows}


def _attribution_response(
    row: CommerceAttribution,
    *,
    brands: dict[UUID, Brand],
    legal_entities: dict[UUID, LegalEntity],
) -> AttributionResponse:
    brand = brands.get(row.brand_id) if row.brand_id else None
    legal_entity = (
        legal_entities.get(row.legal_entity_id) if row.legal_entity_id else None
    )
    counterparty = (
        legal_entities.get(row.counterparty_legal_entity_id)
        if row.counterparty_legal_entity_id
        else None
    )
    return AttributionResponse(
        id=str(row.id),
        entity_type=row.entity_type,  # type: ignore[arg-type]
        entity_id=str(row.entity_id),
        brand_id=str(row.brand_id) if row.brand_id else None,
        brand_name=brand.name if brand else None,
        legal_entity_id=str(row.legal_entity_id) if row.legal_entity_id else None,
        legal_entity_name=legal_entity.name if legal_entity else None,
        assignment_source=row.assignment_source,
        is_intercompany=row.is_intercompany,
        counterparty_legal_entity_id=(
            str(row.counterparty_legal_entity_id)
            if row.counterparty_legal_entity_id
            else None
        ),
        counterparty_legal_entity_name=counterparty.name if counterparty else None,
        elimination_status=row.elimination_status,  # type: ignore[arg-type]
        elimination_amount=row.elimination_amount,
        evidence=row.evidence or {},
        assigned_by=row.assigned_by,
        approved_by=row.approved_by,
        approved_at=row.approved_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _attribution_bundle(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    rows: list[CommerceAttribution],
) -> tuple[dict[UUID, Brand], dict[UUID, LegalEntity]]:
    brand_ids = {row.brand_id for row in rows if row.brand_id}
    legal_entity_ids = {
        value
        for row in rows
        for value in (row.legal_entity_id, row.counterparty_legal_entity_id)
        if value
    }
    brands = {
        row.id: row
        for row in (
            await db.execute(
                select(Brand).where(
                    Brand.workspace_id == workspace_id,
                    Brand.id.in_(brand_ids),
                )
            )
        ).scalars().all()
    } if brand_ids else {}
    legal_entities = await _legal_entity_map(
        db,
        workspace_id=workspace_id,
        legal_entity_ids=legal_entity_ids,
    )
    return brands, legal_entities


@router.get(
    "/admin/consolidation/legal-entities",
    response_model=LegalEntityListResponse,
)
async def list_legal_entities(
    db: DBSession,
    workspace_id: WorkspaceId,
    _user: Annotated[UserResponse, Depends(get_current_user)],
    entity_status: str | None = Query(default=None, alias="status", max_length=16),
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> LegalEntityListResponse:
    rows = await consolidation_service.list_legal_entities(
        db,
        workspace_id=workspace_id,
        status=entity_status,
        limit=limit,
    )
    return LegalEntityListResponse(
        items=[_legal_entity_response(row) for row in rows],
        total=len(rows),
    )


@router.post(
    "/admin/consolidation/legal-entities",
    response_model=LegalEntityResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_legal_entity(
    request: LegalEntityCreate,
    db: DBSession,
    workspace_id: WorkspaceId,
    user: ConsolidationEditor,
) -> LegalEntityResponse:
    try:
        row = await consolidation_service.create_legal_entity(
            db,
            workspace_id=workspace_id,
            code=request.code,
            name=request.name,
            legal_name=request.legal_name,
            country=request.country,
            functional_currency=request.functional_currency,
            status=request.status,
            notes=request.notes,
            actor=_actor(user),
        )
        return _legal_entity_response(row)
    except Exception as exc:
        await db.rollback()
        raise _http_error(exc) from exc


@router.patch(
    "/admin/consolidation/legal-entities/{legal_entity_id}",
    response_model=LegalEntityResponse,
)
async def update_legal_entity(
    legal_entity_id: UUID,
    request: LegalEntityUpdate,
    db: DBSession,
    workspace_id: WorkspaceId,
    user: ConsolidationEditor,
) -> LegalEntityResponse:
    try:
        row = await consolidation_service.update_legal_entity(
            db,
            workspace_id=workspace_id,
            legal_entity_id=legal_entity_id,
            changes=request.model_dump(exclude_unset=True),
            actor=_actor(user),
        )
        return _legal_entity_response(row)
    except Exception as exc:
        await db.rollback()
        raise _http_error(exc) from exc


@router.get("/admin/consolidation/brands", response_model=BrandListResponse)
async def list_brands(
    db: DBSession,
    workspace_id: WorkspaceId,
    _user: Annotated[UserResponse, Depends(get_current_user)],
    entity_status: str | None = Query(default=None, alias="status", max_length=16),
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> BrandListResponse:
    rows = await consolidation_service.list_brands(
        db,
        workspace_id=workspace_id,
        status=entity_status,
        limit=limit,
    )
    legal_entities = await _legal_entity_map(
        db,
        workspace_id=workspace_id,
        legal_entity_ids={
            row.default_legal_entity_id
            for row in rows
            if row.default_legal_entity_id
        },
    )
    return BrandListResponse(
        items=[_brand_response(row, legal_entities) for row in rows],
        total=len(rows),
    )


@router.post(
    "/admin/consolidation/brands",
    response_model=BrandResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_brand(
    request: BrandCreate,
    db: DBSession,
    workspace_id: WorkspaceId,
    user: ConsolidationEditor,
) -> BrandResponse:
    try:
        row = await consolidation_service.create_brand(
            db,
            workspace_id=workspace_id,
            code=request.code,
            name=request.name,
            status=request.status,
            default_legal_entity_id=(
                UUID(request.default_legal_entity_id)
                if request.default_legal_entity_id
                else None
            ),
            notes=request.notes,
            actor=_actor(user),
        )
        legal_entities = await _legal_entity_map(
            db,
            workspace_id=workspace_id,
            legal_entity_ids=(
                {row.default_legal_entity_id}
                if row.default_legal_entity_id
                else set()
            ),
        )
        return _brand_response(row, legal_entities)
    except Exception as exc:
        await db.rollback()
        raise _http_error(exc) from exc


@router.patch(
    "/admin/consolidation/brands/{brand_id}",
    response_model=BrandResponse,
)
async def update_brand(
    brand_id: UUID,
    request: BrandUpdate,
    db: DBSession,
    workspace_id: WorkspaceId,
    user: ConsolidationEditor,
) -> BrandResponse:
    try:
        row = await consolidation_service.update_brand(
            db,
            workspace_id=workspace_id,
            brand_id=brand_id,
            changes=request.model_dump(exclude_unset=True),
            actor=_actor(user),
        )
        legal_entities = await _legal_entity_map(
            db,
            workspace_id=workspace_id,
            legal_entity_ids=(
                {row.default_legal_entity_id}
                if row.default_legal_entity_id
                else set()
            ),
        )
        return _brand_response(row, legal_entities)
    except Exception as exc:
        await db.rollback()
        raise _http_error(exc) from exc


@router.post(
    "/admin/consolidation/products/{product_id}/brand",
    response_model=ProductBrandResponse,
)
async def assign_product_brand(
    product_id: UUID,
    request: ProductBrandAssignRequest,
    db: DBSession,
    workspace_id: WorkspaceId,
    user: ConsolidationEditor,
) -> ProductBrandResponse:
    try:
        product, brand = await consolidation_service.assign_product_brand(
            db,
            workspace_id=workspace_id,
            product_id=product_id,
            brand_id=UUID(request.brand_id),
            actor=_actor(user),
        )
        return ProductBrandResponse(
            product_id=str(product.id),
            sku=product.sku,
            brand_id=str(brand.id),
            brand_code=brand.code,
            brand_name=brand.name,
        )
    except Exception as exc:
        await db.rollback()
        raise _http_error(exc) from exc


@router.get(
    "/admin/consolidation/product-brand-gaps",
    response_model=ProductBrandGapListResponse,
)
async def list_product_brand_gaps(
    db: DBSession,
    workspace_id: WorkspaceId,
    _user: Annotated[UserResponse, Depends(get_current_user)],
    search: str | None = Query(default=None, max_length=128),
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> ProductBrandGapListResponse:
    rows = await consolidation_service.list_product_brand_gaps(
        db,
        workspace_id=workspace_id,
        search=search,
        limit=limit,
    )
    return ProductBrandGapListResponse(items=rows, total=len(rows))


@router.post(
    "/admin/consolidation/product-brands/bulk",
    response_model=ProductBrandBulkAssignResponse,
)
async def bulk_assign_product_brands(
    request: ProductBrandBulkAssignRequest,
    db: DBSession,
    workspace_id: WorkspaceId,
    user: ConsolidationEditor,
) -> ProductBrandBulkAssignResponse:
    try:
        return await consolidation_service.assign_product_brands(
            db,
            workspace_id=workspace_id,
            product_ids=request.product_ids,
            brand_id=UUID(request.brand_id),
            actor=_actor(user),
        )
    except Exception as exc:
        await db.rollback()
        raise _http_error(exc) from exc


@router.get(
    "/admin/consolidation/attributions",
    response_model=AttributionListResponse,
)
async def list_attributions(
    db: DBSession,
    workspace_id: WorkspaceId,
    _user: Annotated[UserResponse, Depends(get_current_user)],
    entity_type: AttributionEntityType | None = None,
    elimination_status: str | None = Query(default=None, max_length=16),
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> AttributionListResponse:
    rows = await consolidation_service.list_attributions(
        db,
        workspace_id=workspace_id,
        entity_type=entity_type,
        elimination_status=elimination_status,
        limit=limit,
    )
    brands, legal_entities = await _attribution_bundle(
        db,
        workspace_id=workspace_id,
        rows=rows,
    )
    return AttributionListResponse(
        items=[
            _attribution_response(
                row,
                brands=brands,
                legal_entities=legal_entities,
            )
            for row in rows
        ],
        total=len(rows),
    )


@router.get(
    "/admin/consolidation/attribution-gaps",
    response_model=AttributionGapListResponse,
)
async def list_attribution_gaps(
    db: DBSession,
    workspace_id: WorkspaceId,
    _user: Annotated[UserResponse, Depends(get_current_user)],
    entity_type: AttributionEntityType | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> AttributionGapListResponse:
    rows = await consolidation_service.list_attribution_gaps(
        db,
        workspace_id=workspace_id,
        entity_type=entity_type,
        limit=limit,
    )
    return AttributionGapListResponse(items=rows, total=len(rows))


@router.post(
    "/admin/consolidation/attribution-gaps/reconcile",
    response_model=AttributionReconcileResponse,
)
async def reconcile_attribution_gaps(
    db: DBSession,
    workspace_id: WorkspaceId,
    user: ConsolidationEditor,
    entity_type: AttributionEntityType | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> AttributionReconcileResponse:
    try:
        return await consolidation_service.reconcile_attribution_gaps(
            db,
            workspace_id=workspace_id,
            entity_type=entity_type,
            limit=limit,
            actor=_actor(user),
        )
    except Exception as exc:
        await db.rollback()
        raise _http_error(exc) from exc


@router.put(
    "/admin/consolidation/attributions/{entity_type}/{entity_id}",
    response_model=AttributionResponse,
)
async def upsert_attribution(
    entity_type: AttributionEntityType,
    entity_id: UUID,
    request: CommerceAttributionUpsert,
    db: DBSession,
    workspace_id: WorkspaceId,
    user: ConsolidationEditor,
) -> AttributionResponse:
    try:
        row = await consolidation_service.upsert_attribution(
            db,
            workspace_id=workspace_id,
            entity_type=entity_type,
            entity_id=entity_id,
            brand_id=UUID(request.brand_id),
            legal_entity_id=UUID(request.legal_entity_id),
            is_intercompany=request.is_intercompany,
            counterparty_legal_entity_id=(
                UUID(request.counterparty_legal_entity_id)
                if request.counterparty_legal_entity_id
                else None
            ),
            evidence=request.evidence,
            actor=_actor(user),
        )
        brands, legal_entities = await _attribution_bundle(
            db,
            workspace_id=workspace_id,
            rows=[row],
        )
        return _attribution_response(
            row,
            brands=brands,
            legal_entities=legal_entities,
        )
    except Exception as exc:
        await db.rollback()
        raise _http_error(exc) from exc


@router.post(
    "/admin/consolidation/attributions/{attribution_id}/approve-elimination",
    response_model=AttributionResponse,
)
async def approve_elimination(
    attribution_id: UUID,
    request: EliminationDecisionRequest,
    db: DBSession,
    workspace_id: WorkspaceId,
    user: ConsolidationAdmin,
) -> AttributionResponse:
    try:
        row = await consolidation_service.approve_elimination(
            db,
            workspace_id=workspace_id,
            attribution_id=attribution_id,
            amount=request.elimination_amount,
            evidence=request.evidence,
            actor=_actor(user),
        )
        brands, legal_entities = await _attribution_bundle(
            db,
            workspace_id=workspace_id,
            rows=[row],
        )
        return _attribution_response(
            row,
            brands=brands,
            legal_entities=legal_entities,
        )
    except Exception as exc:
        await db.rollback()
        raise _http_error(exc) from exc


@router.post(
    "/admin/consolidation/attributions/{attribution_id}/reject-elimination",
    response_model=AttributionResponse,
)
async def reject_elimination(
    attribution_id: UUID,
    request: EliminationRejectionRequest,
    db: DBSession,
    workspace_id: WorkspaceId,
    user: ConsolidationAdmin,
) -> AttributionResponse:
    try:
        row = await consolidation_service.reject_elimination(
            db,
            workspace_id=workspace_id,
            attribution_id=attribution_id,
            evidence=request.evidence,
            actor=_actor(user),
        )
        brands, legal_entities = await _attribution_bundle(
            db,
            workspace_id=workspace_id,
            rows=[row],
        )
        return _attribution_response(
            row,
            brands=brands,
            legal_entities=legal_entities,
        )
    except Exception as exc:
        await db.rollback()
        raise _http_error(exc) from exc


@router.get(
    "/analytics/consolidation",
    response_model=ConsolidatedReportResponse,
)
async def get_consolidated_report(
    db: DBSession,
    workspace_id: WorkspaceId,
    _user: Annotated[UserResponse, Depends(get_current_user)],
    start_date: date | None = None,
    end_date: date | None = None,
    reporting_currency: Annotated[
        str | None,
        Query(min_length=3, max_length=8),
    ] = None,
    brand_id: UUID | None = None,
    legal_entity_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ConsolidatedReportResponse:
    effective_end = end_date or date.today()
    effective_start = start_date or (effective_end - timedelta(days=29))
    try:
        return await consolidation_service.build_consolidated_report(
            db,
            workspace_id=workspace_id,
            start_date=effective_start,
            end_date=effective_end,
            reporting_currency=reporting_currency,
            brand_id=brand_id,
            legal_entity_id=legal_entity_id,
            limit=limit,
        )
    except Exception as exc:
        raise _http_error(exc) from exc
