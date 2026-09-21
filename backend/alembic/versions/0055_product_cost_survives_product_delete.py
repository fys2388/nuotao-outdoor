"""0055_product_cost_survives_product_delete

把 product_cost.product_id 的外键从 ondelete CASCADE 改为 SET NULL，并允许为空。

背景
----
prod 取证（pg_stat_user_tables）显示 ``product_cost`` 的历史是
``ins=34 del=16 live=18``：成本行被创建过，但 16 行随产品删除一起消失了。
触发方式是双重的 —— 数据库层 ``ForeignKey("products.id", ondelete="CASCADE")``，
以及 ORM 层 ``Product.cost`` 的 ``cascade="all, delete-orphan"``。

采购成本是 PROFIT-001 落地成本主数据，属于业务资产（AGENTS.md 1.2 第 4 条
「数据是资产」）。产品下线、被替换、或像 prod 那样整批软删清理时，采购价、
运费、税费明细都不该被连带销毁 —— 复盘毛利、给下一代产品做成本基线、审计
采购决策，都还要用这些数字。

本次变更
--------
1. 外键 ``product_cost.product_id`` 改为 ``ondelete="SET NULL"``；
2. 列改为可空，``product_id`` 在失去关联时置 NULL 而不是删除整行，
   成本明细与 ``valid_from`` 时间线完整保留；
3. 列已建索引，置空后仍可追溯归属。

已存在的数据不受影响：现有 18 行的 ``product_id`` 都非空。

Revision ID: 0055
Revises: 0054
Create Date: 2026-09-21
"""
import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = '0055'
down_revision = '0054'
branch_labels = None
depends_on = None


def _fk_name(bind, table: str, column: str) -> str | None:
    """按列反查外键约束名（不同环境的自动命名可能不同）。"""
    insp = inspect(bind)
    for fk in insp.get_foreign_keys(table):
        if column in fk.get("constrained_columns", []):
            return fk.get("name")
    return None


def upgrade() -> None:
    bind = op.get_bind()
    name = _fk_name(bind, "product_cost", "product_id")
    if name:
        op.drop_constraint(name, "product_cost", type_="foreignkey")

    op.alter_column("product_cost", "product_id", existing_type=sa.Uuid(), nullable=True)

    op.create_foreign_key(
        "fk_product_cost_product_id",
        "product_cost",
        "products",
        ["product_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_product_cost_product_id", "product_cost", type_="foreignkey")

    # 回填会破坏外键：先把失去归属的行移走，再恢复 NOT NULL。
    op.execute(
        "DELETE FROM product_cost WHERE product_id IS NULL"
    )
    op.alter_column("product_cost", "product_id", existing_type=sa.Uuid(), nullable=False)

    op.create_foreign_key(
        "fk_product_cost_product_id",
        "product_cost",
        "products",
        ["product_id"],
        ["id"],
        ondelete="CASCADE",
    )
