"""策略版本模型 — A/B 测试结论自动更新策略的可审计版本记录。

每次策略变更写入一条版本记录（含旧/新配置与变更原因），
支持按版本回滚（rollback_strategy 从本表恢复配置）。
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AI_JSON, BIGINT_PK, Base, TimestampMixin, WorkspaceMixin


class StrategyVersion(Base, TimestampMixin, WorkspaceMixin):
    """策略版本记录。

    策略类型：pricing / listing / marketing / inventory / content。
    每次变更 new_config 必须完整可恢复；rollback 时读取指定版本恢复。
    """

    __tablename__ = "strategy_versions"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)

    # --- 归属 ---
    strategy_type: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True, comment="策略类型"
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="策略版本号（同类型内自增）"
    )

    # --- 配置 ---
    old_config: Mapped[dict[str, Any]] = mapped_column(
        AI_JSON, nullable=False, default=dict, comment="变更前配置"
    )
    new_config: Mapped[dict[str, Any]] = mapped_column(
        AI_JSON, nullable=False, default=dict, comment="变更后配置（可完整恢复）"
    )

    # --- 元数据 ---
    reason: Mapped[str] = mapped_column(
        Text, nullable=False, comment="变更原因（A/B结论/人工调整/回滚）"
    )
    changed_by: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="变更发起方（agent_id / user / ab_test_auto）"
    )
    experiment_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True, comment="关联 A/B 实验ID"
    )
    suggestion_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_suggestions.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联审批建议ID",
    )
    change_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="update",
        comment="变更类型: update(更新)/rollback(回滚)",
    )
    rolled_back_from: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="回滚操作记录的上一版本号"
    )

    __table_args__ = (
        # 按类型+版本检索（回滚/审计路径）
        Index(
            "ix_strategy_versions_type_version",
            "workspace_id", "strategy_type", "version",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<StrategyVersion id={self.id} type={self.strategy_type} "
            f"v{self.version} by={self.changed_by}>"
        )
