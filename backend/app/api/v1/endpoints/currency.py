"""Internal API for auditable exchange-rate management."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import (
    get_current_user,
    get_current_workspace_id,
    require_role,
)
from app.core.database import get_db
from app.schemas.currency import (
    ExchangeRateCreate,
    ExchangeRateListResponse,
    ExchangeRateResolutionResponse,
    ExchangeRateResponse,
)
from app.schemas.user import UserResponse
from app.services import currency_service

router = APIRouter(prefix="/admin/currency-rates", tags=["currency-rates"])
DBSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_current_workspace_id)]


def _response(row) -> ExchangeRateResponse:
    return ExchangeRateResponse(
        id=str(row.id),
        base_currency=row.base_currency,
        quote_currency=row.quote_currency,
        rate=row.rate,
        effective_date=row.effective_date,
        source=row.source,
        source_reference=row.source_reference,
        created_by=row.created_by,
        created_at=row.created_at,
    )


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, currency_service.ExchangeRateConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, currency_service.ExchangeRateNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, currency_service.CurrencyRateError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="Currency-rate operation failed")


@router.get("", response_model=ExchangeRateListResponse)
async def list_exchange_rates(
    db: DBSession,
    workspace_id: WorkspaceId,
    _user: Annotated[UserResponse, Depends(get_current_user)],
    base_currency: str | None = Query(default=None, min_length=3, max_length=8),
    quote_currency: str | None = Query(default=None, min_length=3, max_length=8),
    as_of: date | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> ExchangeRateListResponse:
    try:
        rows = await currency_service.list_exchange_rates(
            db,
            workspace_id=workspace_id,
            base_currency=base_currency,
            quote_currency=quote_currency,
            as_of=as_of,
            limit=limit,
        )
        return ExchangeRateListResponse(
            items=[_response(row) for row in rows],
            total=len(rows),
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/resolve", response_model=ExchangeRateResolutionResponse)
async def resolve_exchange_rate(
    db: DBSession,
    workspace_id: WorkspaceId,
    _user: Annotated[UserResponse, Depends(get_current_user)],
    base_currency: str = Query(min_length=3, max_length=8),
    quote_currency: str = Query(min_length=3, max_length=8),
    as_of: date | None = None,
) -> ExchangeRateResolutionResponse:
    effective_date = as_of or date.today()
    try:
        base = currency_service.normalize_currency_code(base_currency)
        quote = currency_service.normalize_currency_code(quote_currency)
        if base == quote:
            return ExchangeRateResolutionResponse(
                base_currency=base,
                quote_currency=quote,
                as_of=effective_date,
                rate=1,
                effective_date=effective_date,
                source="identity",
            )
        row = await currency_service.resolve_exchange_rate(
            db,
            workspace_id=workspace_id,
            base_currency=base,
            quote_currency=quote,
            as_of=effective_date,
        )
        if row is None:
            raise currency_service.ExchangeRateNotFoundError(
                f"missing direct exchange rate {base}/{quote} "
                f"on or before {effective_date.isoformat()}"
            )
        return ExchangeRateResolutionResponse(
            base_currency=base,
            quote_currency=quote,
            as_of=effective_date,
            rate=row.rate,
            effective_date=row.effective_date,
            source=row.source,
            source_reference=row.source_reference,
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post(
    "",
    response_model=ExchangeRateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_exchange_rate(
    request: ExchangeRateCreate,
    db: DBSession,
    workspace_id: WorkspaceId,
    user: Annotated[UserResponse, Depends(require_role("admin"))],
) -> ExchangeRateResponse:
    try:
        row = await currency_service.create_exchange_rate(
            db,
            workspace_id=workspace_id,
            base_currency=request.base_currency,
            quote_currency=request.quote_currency,
            rate=request.rate,
            effective_date=request.effective_date,
            source=request.source,
            source_reference=request.source_reference,
            created_by=user.email or user.username,
        )
        await db.commit()
        await db.refresh(row)
        return _response(row)
    except Exception as exc:
        await db.rollback()
        raise _http_error(exc) from exc
