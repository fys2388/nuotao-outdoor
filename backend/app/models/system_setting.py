"""系统设置数据库模型"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SystemSetting(Base):
    """系统设置表 - 使用单例模式，只有一条记录"""

    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    site_name: Mapped[str] = mapped_column(String(200), default="Nuotao Outdoor AI OS")
    site_url: Mapped[str] = mapped_column(String(500), default="https://admin.nuotaooutdoor.com")
    admin_email: Mapped[str] = mapped_column(String(200), default="admin@nuotaooutdoor.com")
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Shanghai")
    language: Mapped[str] = mapped_column(String(20), default="zh-CN")
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    order_auto_confirm: Mapped[bool] = mapped_column(default=False)
    low_stock_threshold: Mapped[int] = mapped_column(default=10)
    ai_auto_reply: Mapped[bool] = mapped_column(default=True)
    log_retention_days: Mapped[int] = mapped_column(default=90)
    backup_enabled: Mapped[bool] = mapped_column(default=True)
    backup_schedule: Mapped[str] = mapped_column(String(50), default="0 2 * * *")
    extra_config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "site_name": self.site_name,
            "site_url": self.site_url,
            "admin_email": self.admin_email,
            "timezone": self.timezone,
            "language": self.language,
            "currency": self.currency,
            "order_auto_confirm": self.order_auto_confirm,
            "low_stock_threshold": self.low_stock_threshold,
            "ai_auto_reply": self.ai_auto_reply,
            "log_retention_days": self.log_retention_days,
            "backup_enabled": self.backup_enabled,
            "backup_schedule": self.backup_schedule,
            "extra_config": self.extra_config or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
