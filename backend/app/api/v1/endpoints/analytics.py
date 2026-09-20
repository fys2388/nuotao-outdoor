"""Operating analytics endpoints for B2C + B2B channel attribution."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated
from uuid import UUID  # noqa: TC003 - FastAPI resolves this annotation at runtime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import get_current_user, get_current_workspace_id
from app.core.database import get_db
from app.schemas.analytics import ChannelAnalyticsResponse
from app.schemas.user import UserResponse
from app.services.channel_analytics_service import (
    ChannelAnalyticsError,
    build_channel_analytics,
)
from app.services.currency_service import CurrencyRateError

router = APIRouter(prefix="/analytics", tags=["analytics"])
DBSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/channel-performance", response_model=ChannelAnalyticsResponse)
async def get_channel_performance(
    db: DBSession,
    _current_user: Annotated[UserResponse, Depends(get_current_user)],
    workspace_id: Annotated[UUID, Depends(get_current_workspace_id)],
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    currency: Annotated[str | None, Query(min_length=3, max_length=8)] = None,
    reporting_currency: Annotated[
        str | None,
        Query(min_length=3, max_length=8),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> ChannelAnalyticsResponse:
    """Return auditable B2C/B2B performance, customer, AR, and inventory views."""
    effective_end = end_date or date.today()
    effective_start = start_date or (effective_end - timedelta(days=29))
    try:
        return await build_channel_analytics(
            db,
            workspace_id=workspace_id,
            start_date=effective_start,
            end_date=effective_end,
            currency=currency,
            reporting_currency=reporting_currency,
            limit=limit,
        )
    except (ChannelAnalyticsError, CurrencyRateError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
