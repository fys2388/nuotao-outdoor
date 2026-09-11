"""
操作日志 API 端点
获取操作日志列表、统计、详情（使用PostgreSQL数据库存储）
"""
from __future__ import annotations

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.operation_log import OperationLogListResponse, OperationLogStatsResponse
from app.services.operation_log_service import get_log_stats, list_logs

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/operation-logs", tags=["operation-logs"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=OperationLogListResponse)
async def get_operation_logs(
    db: DbSession,
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    action: Optional[str] = Query(default=None, description="操作类型筛选"),
    module: Optional[str] = Query(default=None, description="操作模块筛选"),
    status: Optional[str] = Query(default=None, description="状态筛选"),
    search: Optional[str] = Query(default=None, description="搜索关键词"),
):
    """获取操作日志列表（支持筛选和分页，从数据库）"""
    items, total = await list_logs(
        db=db,
        page=page,
        page_size=page_size,
        action_filter=action,
        module_filter=module,
        status_filter=status,
        search_text=search,
    )
    return OperationLogListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/stats", response_model=OperationLogStatsResponse)
async def get_operation_log_stats(db: DbSession):
    """获取操作日志统计（从数据库）"""
    stats = await get_log_stats(db)
    return stats
