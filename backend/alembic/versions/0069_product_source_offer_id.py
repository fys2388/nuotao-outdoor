"""1688 来源唯一键：``products.source_offer_id``

为每个 1688 来源的商品记录规范化后的 offer id，并建立部分唯一索引，保证同一
workspace 内同一个 1688 链接只存在一条活行（``deleted_at IS NULL``）。

背景：此前 ``products`` 上唯一的唯一性保障是 ``(workspace_id, sku)``，而 pipeline
生成的 SKU 由「LLM 生成标题 + 分钟级时间戳」构成，同一链接在不同时间导入必然得到
不同 SKU，于是同一 1688 offer 被重复建档为多条候选，并最终在 WooCommerce 里推成
多个商品。应用层的「先 SELECT 再 INSERT」查重会被并发绕过，因此防线放在数据库。

索引条件里的 ``source_offer_id IS NOT NULL`` 让非 1688 来源（手工录入、CSV 导入、
WooCommerce 反向同步）完全不受此约束影响。

**存量数据不由本迁移回填**：回填需要与 ``parse_1688_url`` 一致的正则，且很可能
发现已经存在的重复行。请使用 ``backend/scripts/backfill_source_offer_id.py``，
它会先做只读诊断、报告冲突，再由人工决定如何处置。

Revision ID: 0069
Revises: 0068
Create Date: 2026-10-03
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None

_TABLE = "products"
_INDEX = "uq_products_workspace_source_offer"
_LIVE_AND_SOURCED = sa.text("deleted_at IS NULL AND source_offer_id IS NOT NULL")


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column("source_offer_id", sa.String(length=32), nullable=True),
    )
    op.create_index(
        _INDEX,
        _TABLE,
        ["workspace_id", "source_offer_id"],
        unique=True,
        postgresql_where=_LIVE_AND_SOURCED,
    )


def downgrade() -> None:
    op.drop_index(_INDEX, table_name=_TABLE, postgresql_where=_LIVE_AND_SOURCED)
    op.drop_column(_TABLE, "source_offer_id")
