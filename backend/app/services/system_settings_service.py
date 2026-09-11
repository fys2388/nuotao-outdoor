"""
系统设置服务层
使用PostgreSQL数据库存储，支持异步操作
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_setting import SystemSetting as SystemSettingModel
from app.schemas.system_settings import SystemSettings, SystemSettingsUpdate

logger = logging.getLogger(__name__)


def _model_to_schema(model: SystemSettingModel) -> SystemSettings:
    """将数据库模型转换为Pydantic schema"""
    return SystemSettings(
        site_name=model.site_name,
        site_url=model.site_url,
        admin_email=model.admin_email,
        timezone=model.timezone,
        language=model.language,
        currency=model.currency,
        order_auto_confirm=model.order_auto_confirm,
        low_stock_threshold=model.low_stock_threshold,
        ai_auto_reply=model.ai_auto_reply,
        log_retention_days=model.log_retention_days,
        backup_enabled=model.backup_enabled,
        backup_schedule=model.backup_schedule,
    )


def _get_default_model() -> SystemSettingModel:
    """获取默认设置的数据库模型"""
    return SystemSettingModel(
        site_name="Nuotao Outdoor AI OS",
        site_url="https://admin.nuotaooutdoor.com",
        admin_email="admin@nuotaooutdoor.com",
        timezone="Asia/Shanghai",
        language="zh-CN",
        currency="USD",
        order_auto_confirm=False,
        low_stock_threshold=10,
        ai_auto_reply=True,
        log_retention_days=90,
        backup_enabled=True,
        backup_schedule="0 2 * * *",
    )


async def get_settings(db: AsyncSession) -> SystemSettings:
    """获取系统设置（从数据库）"""
    result = await db.execute(select(SystemSettingModel).limit(1))
    model = result.scalar_one_or_none()

    if model is None:
        # 如果数据库中没有设置，创建默认设置
        model = _get_default_model()
        db.add(model)
        await db.commit()
        await db.refresh(model)
        logger.info("Default system settings created in database")

    return _model_to_schema(model)


async def update_settings(db: AsyncSession, update: SystemSettingsUpdate) -> SystemSettings:
    """更新系统设置（保存到数据库）"""
    result = await db.execute(select(SystemSettingModel).limit(1))
    model = result.scalar_one_or_none()

    if model is None:
        model = _get_default_model()
        db.add(model)

    # 将更新字段转换为字典，排除None值
    update_data = update.model_dump(exclude_none=True)

    # 更新模型字段
    for key, value in update_data.items():
        if hasattr(model, key):
            setattr(model, key, value)

    await db.commit()
    await db.refresh(model)

    logger.info("System settings updated in database: %s", list(update_data.keys()))
    return _model_to_schema(model)


async def reset_settings(db: AsyncSession) -> SystemSettings:
    """重置为默认设置（更新数据库）"""
    result = await db.execute(select(SystemSettingModel).limit(1))
    model = result.scalar_one_or_none()

    if model is None:
        model = _get_default_model()
        db.add(model)
    else:
        # 重置为默认值
        default = _get_default_model()
        model.site_name = default.site_name
        model.site_url = default.site_url
        model.admin_email = default.admin_email
        model.timezone = default.timezone
        model.language = default.language
        model.currency = default.currency
        model.order_auto_confirm = default.order_auto_confirm
        model.low_stock_threshold = default.low_stock_threshold
        model.ai_auto_reply = default.ai_auto_reply
        model.log_retention_days = default.log_retention_days
        model.backup_enabled = default.backup_enabled
        model.backup_schedule = default.backup_schedule

    await db.commit()
    await db.refresh(model)

    logger.info("System settings reset to default in database")
    return _model_to_schema(model)
