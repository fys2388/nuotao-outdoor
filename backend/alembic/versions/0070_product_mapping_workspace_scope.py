"""product_mappings 的唯一约束补上 workspace 维度

原约束是全局的 ``uq_product_mappings_nuotao_id`` / ``uq_product_mappings_woo_id``，
没有 workspace 维度。而 WooCommerce 是**按店铺隔离**的：同一个数字商品 ID 在不同
workspace 里完全可能是两个不同的商品。全局唯一会把它们错误地互斥——B 空间的本地商品
无法映射到一个 A 空间已经在用的 WC 商品 ID。

本次改动同时把约束名写得更清楚（``workspace`` 前缀），避免后来者再误以为它是全局的。

Revision ID: 0070
Revises: 0069
Create Date: 2026-10-03
"""

from __future__ import annotations

from alembic import op

revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None

_TABLE = "product_mappings"
_OLD_NUOTAO = "uq_product_mappings_nuotao_id"
_OLD_WOO = "uq_product_mappings_woo_id"
_NEW_NUOTAO = "uq_product_mappings_workspace_nuotao"
_NEW_WOO = "uq_product_mappings_workspace_woo"


def upgrade() -> None:
    op.drop_constraint(_OLD_NUOTAO, _TABLE, type_="unique")
    op.drop_constraint(_OLD_WOO, _TABLE, type_="unique")
    op.create_unique_constraint(
        _NEW_NUOTAO, _TABLE, ["workspace_id", "nuotao_product_id"]
    )
    op.create_unique_constraint(
        _NEW_WOO, _TABLE, ["workspace_id", "woocommerce_id"]
    )


def downgrade() -> None:
    # 注意：若此时已存在跨 workspace 复用的同一个 woocommerce_id，
    # 重建全局唯一约束会失败——需要先清理这些行。
    op.drop_constraint(_NEW_WOO, _TABLE, type_="unique")
    op.drop_constraint(_NEW_NUOTAO, _TABLE, type_="unique")
    op.create_unique_constraint(_OLD_WOO, _TABLE, ["woocommerce_id"])
    op.create_unique_constraint(_OLD_NUOTAO, _TABLE, ["nuotao_product_id"])
