"""
操作日志 Pydantic schemas
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class OperationLog(BaseModel):
    """操作日志"""
    id: str = Field(description="日志ID")
    timestamp: datetime = Field(description="操作时间")
    user: str = Field(description="操作用户")
    user_role: str = Field(default="operator", description="用户角色")
    action: str = Field(description="操作类型")
    module: str = Field(description="操作模块")
    detail: str = Field(default="", description="操作详情")
    ip_address: str = Field(default="", description="IP地址")
    status: str = Field(default="success", description="状态：success/failed")
    duration_ms: Optional[int] = Field(default=None, description="耗时（毫秒）")


class OperationLogListResponse(BaseModel):
    """操作日志列表响应"""
    items: list[OperationLog]
    total: int
    page: int
    page_size: int


class OperationLogStatsResponse(BaseModel):
    """操作日志统计响应"""
    total_operations: int
    success_rate: float
    security_alerts: int
    data_changes: int
    today_operations: int
    failed_operations: int
