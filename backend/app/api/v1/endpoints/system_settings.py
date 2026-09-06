"""
系统设置 API 端点
获取、更新、重置系统设置（使用PostgreSQL数据库存储）
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.system_settings import SystemSettingsResponse, SystemSettingsUpdate
from app.services.system_settings_service import get_settings, reset_settings, update_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/system-settings", tags=["system-settings"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=SystemSettingsResponse)
async def get_system_settings(db: DbSession):
    """获取系统设置（从数据库）"""
    settings = await get_settings(db)
    return SystemSettingsResponse(data=settings)


@router.put("", response_model=SystemSettingsResponse)
async def update_system_settings(update: SystemSettingsUpdate, db: DbSession):
    """更新系统设置（保存到数据库）"""
    settings = await update_settings(db, update)
    return SystemSettingsResponse(data=settings, message="设置更新成功")


@router.post("/reset", response_model=SystemSettingsResponse)
async def reset_system_settings(db: DbSession):
    """重置系统设置为默认值（更新数据库）"""
    settings = await reset_settings(db)
    return SystemSettingsResponse(data=settings, message="设置已重置为默认值")
