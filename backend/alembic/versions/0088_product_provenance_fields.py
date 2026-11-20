"""0088: products 来源追溯字段（D8-F P0-2 商品数据真实性与采集供应链）。

为商品数据补字段级来源追溯的落库地基，使每一次采集都记录：
- data_source：采集方式/Provider（manual | browser_cookie | official_api），
  区别于已有 `source`（来源类别 manual/1688/woocommerce）。
- collected_at：采集时间（UTC），支撑证据新鲜度/过期判定。
- evidence_grade：E0-E5 证据等级（复用 reports/b2b/M334_EVIDENCE_GRADE_SYSTEM.md，
  禁止跳跃升级；初始按来源赋值，商品级≠字段级）。
- provenance：完整来源追溯 JSON（ProductProvenance，含 field_provenance 字段级）。

设计依据：D8F_ARCHITECTURE.md §3.2 / §5。缺口：审计 R4/R5/R7/N3。
本迁移只加可空列，不回填历史数据（历史行 provenance 为 NULL 表示未追溯），
不改变现有业务读取路径，符合「仅设计+最小实现，生产批量改数据需 Owner 批准」。

Revision: 0088
Create Date: 2026-11-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0088"
down_revision = "0087"
branch_labels = None
depends_on = None

_TABLE = "products"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column(
            "data_source",
            sa.String(length=32),
            nullable=True,
            comment="采集方式/Provider: manual | browser_cookie | official_api",
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "collected_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="采集时间(UTC)，支撑证据新鲜度/过期判定",
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "evidence_grade",
            sa.String(length=4),
            nullable=True,
            comment="E0-E5 证据等级(复用 M334 体系，禁止跳跃升级)",
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "provenance",
            JSONB(),
            nullable=True,
            comment="完整来源追溯(ProductProvenance，含 field_provenance 字段级)",
        ),
    )


def downgrade() -> None:
    op.drop_column(_TABLE, "provenance")
    op.drop_column(_TABLE, "evidence_grade")
    op.drop_column(_TABLE, "collected_at")
    op.drop_column(_TABLE, "data_source")
