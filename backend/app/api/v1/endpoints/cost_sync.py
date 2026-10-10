"""Cost source synchronization API endpoints (PHASE 4).

Provides endpoints to sync cost data from 1688 sources into product
cost records. Part of the V3.0 evaluation fix: ensuring candidates
have real cost data before scoring.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.workspace import get_workspace_id
from app.services import cost_sync_service
from app.services.cost_sync_service import CostSyncError

router = APIRouter(prefix="/sourcing/cost-sync", tags=["cost-sync"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CostSyncResult(BaseModel):
    product_id: UUID
    sku: str
    name: str
    sync_status: str
    details: str
    cost_version: str | None = None
    purchase_cost: str | None = None
    currency: str | None = None


class CostSyncBatchRequest(BaseModel):
    product_ids: list[str] | None = Field(
        default=None,
        description="Specific product IDs to sync. Null = all 1688-sourced candidates.",
    )
    force: bool = Field(
        default=False,
        description="Overwrite existing effective costs with a new version.",
    )


class CostSyncBatchResult(BaseModel):
    total: int
    synced: int
    skipped: int
    errors: int
    exchange_rate: str
    results: list[CostSyncResult]


class CostSyncStatus(BaseModel):
    total_products: int
    products_with_1688_source: int
    products_with_effective_cost: int
    pending_sync: int
    already_synced: int
    no_1688_source: int
    exchange_rate_cny_usd: str
    pending_product_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/status",
    response_model=CostSyncStatus,
    summary="Get cost sync status overview",
)
async def get_status(
    db: DbSession,
    workspace_id: WorkspaceId,
) -> CostSyncStatus:
    """Return an overview of cost sync coverage: how many products have
    1688 sources, how many have effective costs, how many are pending sync.
    """
    result = await cost_sync_service.get_cost_sync_status(
        db, workspace_id=workspace_id,
    )
    return CostSyncStatus.model_validate(result)


@router.post(
    "/batch",
    response_model=CostSyncBatchResult,
    summary="Batch sync costs from 1688 sources",
)
async def sync_batch(
    body: CostSyncBatchRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> CostSyncBatchResult:
    """Sync costs for multiple products in one call.

    - If product_ids is provided, sync only those products.
    - If product_ids is null, sync all products that have a 1688 source.
    - force=true overwrites existing effective costs.

    Each product is synced independently; a failure for one product does
    not block the others. Results are returned per-product.
    """
    from app.core.tracing import get_trace_id

    try:
        result = await cost_sync_service.sync_cost_batch(
            db,
            workspace_id=workspace_id,
            product_ids=body.product_ids,
            force=body.force,
            trace_id=get_trace_id(),
        )
        await db.commit()
    except CostSyncError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc),
        ) from exc
    except Exception:
        await db.rollback()
        raise

    return CostSyncBatchResult.model_validate(result)


@router.post(
    "/{product_id}",
    response_model=CostSyncResult,
    summary="Sync cost from 1688 source for a single product",
)
async def sync_single_product(
    product_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
    force: Annotated[bool, Query()] = False,
) -> CostSyncResult:
    """Sync cost data from the product's 1688 source into its cost record.

    - Fetches the latest 1688 source for the product
    - Extracts the purchase price (CNY)
    - Converts to USD at the configured exchange rate
    - Creates or bumps the ProductCost version
    - Appends a ProductCostSnapshot
    - Emits a product.cost.synced audit event

    If the product already has an effective cost, it is skipped unless
    force=true. The conversion rate can be overridden via the
    COST_SYNC_CNY_USD_RATE environment variable.
    """
    from app.core.tracing import get_trace_id

    try:
        result = await cost_sync_service.sync_cost_from_1688(
            db,
            workspace_id=workspace_id,
            product_id=product_id,
            force=force,
            trace_id=get_trace_id(),
        )
        await db.commit()
    except CostSyncError as exc:
        await db.rollback()
        msg = str(exc)
        if "not found" in msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=msg,
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=msg,
        ) from exc
    except Exception:
        await db.rollback()
        raise

    return CostSyncResult.model_validate(result)
