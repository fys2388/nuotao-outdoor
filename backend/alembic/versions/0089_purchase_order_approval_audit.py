"""0089: purchase_orders 审批留痕字段（M4.2.0 T0.2 采购治理收口）。

为采购单审批补可追溯的操作者留痕，使任何 approved 采购单都能回答
「谁在何时批准、依据什么」。治理铁律：approved 状态只能由受权限保护的
显式审批操作产生，AI Agent 不得作为自行批准的授权主体。

新增列（全部可空，不回填历史数据）：
- approved_at：审批时间（UTC）。
- approved_by：审批操作者身份（email/user id），AI 不得作为该主体。
- approval_note：审批理由/备注。

本迁移只加可空列，不改变现有状态机与读取路径；历史行三字段为 NULL 表示
「审批留痕制度建立前的存量单据」，符合「生产批量改数据需 Owner 批准」。

Revision: 0089
Create Date: 2026-11-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0089"
down_revision = "0088"
branch_labels = None
depends_on = None

_TABLE = "purchase_orders"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column(
            "approved_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="审批时间(UTC)；approved 状态必须留痕",
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "approved_by",
            sa.String(length=128),
            nullable=True,
            comment="审批操作者身份(email/user id)；AI 不得作为授权主体",
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "approval_note",
            sa.String(length=500),
            nullable=True,
            comment="审批理由/备注",
        ),
    )


def downgrade() -> None:
    op.drop_column(_TABLE, "approval_note")
    op.drop_column(_TABLE, "approved_by")
    op.drop_column(_TABLE, "approved_at")
