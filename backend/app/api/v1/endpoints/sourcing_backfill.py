"""1688 数据自动回填 API 端点。

提供以下操作：
- GET  /sourcing/1688/backfill/status   — 查看回填状态概览
- POST /sourcing/1688/backfill/scan      — 扫描待回填商品
- POST /sourcing/1688/backfill/run       — 执行批量回填
"""

from __future__ import annotations

import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.sourcing_enhanced import DbSession
from app.core.database import get_db
from app.services.backfill_1688_service import (
    backfill_1688_products,
    get_backfill_status,
    scan_incomplete_products,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sourcing/1688/backfill", tags=["sourcing_backfill"])


# ── 请求模型 ────────────────────────────────────────────────────


class BackfillScanRequest(BaseModel):
    """扫描待回填商品请求。"""

    candidate_only: bool = Field(
        True,
        description="仅扫描候选状态（candidate）商品",
    )
    limit: int = Field(
        50,
        ge=1,
        le=500,
        description="最大扫描数量",
    )


class BackfillRunRequest(BaseModel):
    """执行回填请求。"""

    product_ids: list[str] | None = Field(
        None,
        description="指定商品 ID 列表；null 表示扫描所有不完整商品",
    )
    candidate_only: bool = Field(
        True,
        description="仅回填候选状态商品",
    )
    batch_limit: int = Field(
        50,
        ge=1,
        le=200,
        description="最大回填数量",
    )
    dry_run: bool = Field(
        False,
        description="仅扫描不执行（dry-run 模式）",
    )


# ── 端点 ────────────────────────────────────────────────────────


@router.get("/status", summary="查看 1688 回填状态概览")
async def api_backfill_status(
    session: Annotated[AsyncSession, Depends(get_db)],
    workspace_id: Annotated[UUID, Query()],
) -> dict[str, Any]:
    """获取 1688 来源产品的回填状态概览。

    返回总产品数、不完整数、已完整数，以及前 50 条不完整产品列表。
    """
    return await get_backfill_status(session, workspace_id=workspace_id)


@router.post("/scan", summary="扫描待回填商品")
async def api_backfill_scan(
    req: BackfillScanRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    workspace_id: Annotated[UUID, Query()],
) -> dict[str, Any]:
    """扫描 1688 来源但不完整的产品。

    返回需要回填的商品列表，包括 product_id、sku、name 和缺失字段。
    """
    items = await scan_incomplete_products(
        session,
        workspace_id=workspace_id,
        candidate_only=req.candidate_only,
        limit=req.limit,
    )
    return {
        "success": True,
        "total": len(items),
        "items": items,
    }


@router.post("/run", summary="执行 1688 数据批量回填")
async def api_backfill_run(
    req: BackfillRunRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    workspace_id: Annotated[UUID, Query()],
) -> dict[str, Any]:
    """执行 1688 数据批量回填。

    - 指定 product_ids 时仅回填这些商品
    - 未指定时自动扫描不完整的 1688 候选商品
    - dry_run=True 时仅返回待回填列表，不执行实际更新

    事务边界：service 只 flush，本端点独占 commit/rollback。
    """
    try:
        result = await backfill_1688_products(
            session,
            workspace_id=workspace_id,
            product_ids=req.product_ids,
            candidate_only=req.candidate_only,
            batch_limit=req.batch_limit,
            dry_run=req.dry_run,
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    # 保证 dry_run 标记始终出现在响应里（service 非 dry_run 分支不返回该键）
    if not isinstance(result, dict):
        return result
    result.setdefault("dry_run", req.dry_run)
    return result
