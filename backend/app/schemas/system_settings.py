"""
系统设置 Pydantic schemas
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class SystemSettings(BaseModel):
    """系统设置"""
    site_name: str = Field(default="Nuotao Outdoor AI OS", description="站点名称")
    site_url: str = Field(default="https://admin.nuotaooutdoor.com", description="站点URL")
    admin_email: str = Field(default="admin@nuotaooutdoor.com", description="管理员邮箱")
    timezone: str = Field(default="Asia/Shanghai", description="时区")
    language: str = Field(default="zh-CN", description="语言")
    currency: str = Field(default="USD", description="货币")
    order_auto_confirm: bool = Field(default=False, description="订单自动确认")
    low_stock_threshold: int = Field(default=10, description="低库存阈值")
    ai_auto_reply: bool = Field(default=True, description="AI自动回复")
    log_retention_days: int = Field(default=90, description="日志保留天数")
    backup_enabled: bool = Field(default=True, description="备份启用")
    backup_frequency: str = Field(default="daily", description="备份频率")


class SystemSettingsUpdate(BaseModel):
    """系统设置更新（部分字段可选）"""
    site_name: Optional[str] = None
    site_url: Optional[str] = None
    admin_email: Optional[str] = None
    timezone: Optional[str] = None
    language: Optional[str] = None
    currency: Optional[str] = None
    order_auto_confirm: Optional[bool] = None
    low_stock_threshold: Optional[int] = None
    ai_auto_reply: Optional[bool] = None
    log_retention_days: Optional[int] = None
    backup_enabled: Optional[bool] = None
    backup_frequency: Optional[str] = None


class SystemSettingsResponse(BaseModel):
    """系统设置响应"""
    data: SystemSettings
    message: str = "success"
