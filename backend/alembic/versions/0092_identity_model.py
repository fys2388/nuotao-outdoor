"""0092: M4 V2.6 Product / Variation 身份模型 + Supplier/1688 Offer 独立映射.

upgrade():
1) product_mappings 身份维度列 + 部分唯一索引(商品级/变体级) + SKU 辅助索引,
   移除原全局唯一 ``uq_product_mappings_workspace_woo``(无法表达一变体多映射)。
2) order_items 变体身份列(wc_variation_id / variation_sku / identity_state)。
3) inventory_snapshots 变体维度列 + 部分唯一索引(变体级/商品级),
   移除原唯一 ``uq_inventory_workspace_product_location``(无法表达多变体库存)。
4) product_cost 变体维度列(variation_id / variation_sku)。
5) product_cost_snapshots 变体维度列(append-only 历史快照按变体)。
6) 新建 ``supplier_offer_mappings`` 表(独立多对多映射实体)。

downgrade() 完全可逆(先删索引/表,再删列)。

**草案,不执行生产迁移**(M4 V2.6 指令 §8):仅能在隔离开发/测试数据库验证。
存量数据不由此迁移回填(身份回填需 Owner 单独书面授权)。

Revision: 0092
Create Date: 2026-11-23
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0092"
down_revision = "0091"
branch_labels = None
depends_on = None

# 跨方言 JSON:PG 用 JSONB,其他(SQLite 测试)用 JSON.
_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _constraint_exists(table: str, name: str) -> bool:
    """检查唯一约束/索引是否已存在(幂等,downgrade/upgrade 可重复安全)."""
    insp = sa.inspect(op.get_bind())
    try:
        constraints = insp.get_unique_constraints(table)
        if any(c["name"] == name for c in constraints):
            return True
        indexes = insp.get_indexes(table)
        return any(i["name"] == name for i in indexes)
    except Exception:  # 表不存在等边界,按不存在处理
        return False


# 0091 时代 product_mappings 基线(V2.7.1 正规化)。
# 历史上该表**从未被任何 Alembic revision create_table**(由 backend/create_tables.py
# 手动建出,生产靠 ensure_tables.py 的 create_all 兜底,见 infra/ensure_tables.py)。
# 0070(alter 本表)因应用角色非属主被 park。故 fresh DB upgrade 到 0092 会因表不存在失败。
# 这里按**有证据的 0091 基线 schema**(含 0070 后的两个 workspace 唯一约束)自举建表,
# 使迁移链首次真正负责该表;已存在的库(表由外部角色持有)走原逻辑,语义不变。
_PM_BASELINE_COLUMNS = (
    ("id", sa.Uuid(), False),
    ("workspace_id", sa.Uuid(), False),
    ("nuotao_product_id", sa.Uuid(), False),
    ("woocommerce_id", sa.Integer(), False),
    ("woocommerce_slug", sa.String(255), True),
    ("sync_status", sa.String(32), True),
    ("last_synced_at", sa.DateTime(timezone=True), True),
    ("created_at", sa.DateTime(timezone=True), True),
    ("updated_at", sa.DateTime(timezone=True), True),
)


def _table_exists(table: str) -> bool:
    """真实探测表是否存在(非 IF NOT EXISTS 掩盖,供分支决策)."""
    return sa.inspect(op.get_bind()).has_table(table)


def _column_exists(table: str, column: str) -> bool:
    """真实探测列是否存在(处理“部分含 V2.6 列”边界,幂等)."""
    insp = sa.inspect(op.get_bind())
    return any(c["name"] == column for c in insp.get_columns(table))


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    """列不存在才添加(真实探测,避免对已部分升级的表重复 add_column)."""
    if not _column_exists(table, column.name):
        op.add_column(table, column)


def _create_pm_baseline() -> None:
    """按 0091 时代基线创建 product_mappings(仅当表缺失时调用)."""
    op.create_table(
        "product_mappings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column(
            "nuotao_product_id",
            sa.Uuid(),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("woocommerce_id", sa.Integer(), nullable=False),
        sa.Column("woocommerce_slug", sa.String(255), nullable=True),
        sa.Column("sync_status", sa.String(32), nullable=True, server_default=sa.text("'synced'")),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("workspace_id", "nuotao_product_id", name="uq_product_mappings_workspace_nuotao"),
        sa.UniqueConstraint("workspace_id", "woocommerce_id", name="uq_product_mappings_workspace_woo"),
    )


def _reconcile_pm_baseline() -> None:
    """对账:表已存在但缺基线列时,按基线类型补齐缺失列(真实比较,非掩盖).

    仅补缺、不改已有列类型(应用角色对历史表可能无权 ALTER COLUMN)。
    """
    insp = sa.inspect(op.get_bind())
    existing = {c["name"] for c in insp.get_columns("product_mappings")}
    for name, col_type, nullable in _PM_BASELINE_COLUMNS:
        if name not in existing:
            op.add_column("product_mappings", sa.Column(name, col_type, nullable=nullable))


def upgrade() -> None:
    # 1) product_mappings:身份维度 + 部分唯一索引.
    # V2.7.1:该表历史上从未入链(C 类人工建表),fresh DB 会因表缺失失败。
    # 显式探测分支:缺失则按 0091 基线建表;已存在则对账补齐基线列。两条路径随后
    # 共用同一升级逻辑,得到一致的最终 schema。
    if not _table_exists("product_mappings"):
        _create_pm_baseline()
    else:
        _reconcile_pm_baseline()
    _drop_unique_if_exists("product_mappings", "uq_product_mappings_workspace_woo")
    # 一变体一映射:一个本地商品可对应 1 商品级 + N 变体级映射,
    # (workspace, nuotao_product_id) 全局唯一会阻止多变体共存,故移除.
    _drop_unique_if_exists("product_mappings", "uq_product_mappings_workspace_nuotao")
    _add_column_if_missing(
        "product_mappings",
        sa.Column("woocommerce_variation_id", sa.Integer(), nullable=True),
    )
    _add_column_if_missing("product_mappings", sa.Column("variation_sku", sa.String(191), nullable=True))
    _add_column_if_missing("product_mappings", sa.Column("source_offer_id", sa.String(32), nullable=True))
    _add_column_if_missing("product_mappings", sa.Column("source_variation_spec", _JSON, nullable=True))
    _add_column_if_missing(
        "product_mappings",
        sa.Column(
            "identity_state",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'UNKNOWN_LEGACY'"),
        ),
    )
    _add_column_if_missing("product_mappings", sa.Column("trace_id", sa.String(64), nullable=True))
    if not _constraint_exists("product_mappings", "ux_product_mapping_product"):
        op.create_index(
            "ux_product_mapping_product",
            "product_mappings",
            ["workspace_id", "woocommerce_id"],
            unique=True,
            postgresql_where=sa.text("identity_state = 'PRODUCT'"),
            sqlite_where=sa.text("identity_state = 'PRODUCT'"),
        )
    if not _constraint_exists("product_mappings", "ux_product_mapping_variation"):
        op.create_index(
            "ux_product_mapping_variation",
            "product_mappings",
            ["workspace_id", "woocommerce_id", "woocommerce_variation_id"],
            unique=True,
            postgresql_where=sa.text("identity_state = 'VARIATION' AND woocommerce_variation_id IS NOT NULL"),
            sqlite_where=sa.text("identity_state = 'VARIATION' AND woocommerce_variation_id IS NOT NULL"),
        )
    if not _constraint_exists("product_mappings", "ix_product_mapping_variation_sku"):
        op.create_index(
            "ix_product_mapping_variation_sku",
            "product_mappings",
            ["workspace_id", "variation_sku"],
            unique=False,
            postgresql_where=sa.text("variation_sku IS NOT NULL"),
            sqlite_where=sa.text("variation_sku IS NOT NULL"),
        )

    # 2) order_items:变体身份列.
    op.add_column("order_items", sa.Column("wc_variation_id", sa.Integer(), nullable=True))
    op.add_column("order_items", sa.Column("variation_sku", sa.String(191), nullable=True))
    op.add_column(
        "order_items",
        sa.Column(
            "identity_state",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'UNKNOWN_LEGACY'"),
        ),
    )

    # 3) inventory_snapshots:变体维度列 + 部分唯一索引.
    _drop_unique_if_exists("inventory_snapshots", "uq_inventory_workspace_product_location")
    op.add_column("inventory_snapshots", sa.Column("variation_id", sa.Integer(), nullable=True))
    op.add_column("inventory_snapshots", sa.Column("variation_sku", sa.String(191), nullable=True))
    op.add_column(
        "inventory_snapshots",
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
    )
    if not _constraint_exists("inventory_snapshots", "ux_inventory_snapshot_variation"):
        op.create_index(
            "ux_inventory_snapshot_variation",
            "inventory_snapshots",
            ["workspace_id", "product_id", "variation_id", "location"],
            unique=True,
            postgresql_where=sa.text("variation_id IS NOT NULL"),
            sqlite_where=sa.text("variation_id IS NOT NULL"),
        )
    if not _constraint_exists("inventory_snapshots", "ux_inventory_snapshot_product"):
        op.create_index(
            "ux_inventory_snapshot_product",
            "inventory_snapshots",
            ["workspace_id", "product_id", "location"],
            unique=True,
            postgresql_where=sa.text("variation_id IS NULL"),
            sqlite_where=sa.text("variation_id IS NULL"),
        )

    # 4) product_cost:变体维度列.
    op.add_column("product_cost", sa.Column("variation_id", sa.Integer(), nullable=True))
    op.add_column("product_cost", sa.Column("variation_sku", sa.String(191), nullable=True))

    # 5) product_cost_snapshots:变体维度列(append-only 历史).
    op.add_column("product_cost_snapshots", sa.Column("variation_id", sa.Integer(), nullable=True))
    op.add_column("product_cost_snapshots", sa.Column("variation_sku", sa.String(191), nullable=True))

    # 6) supplier_offer_mappings:独立映射实体.
    op.create_table(
        "supplier_offer_mappings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column(
            "supplier_id",
            sa.Uuid(),
            sa.ForeignKey("suppliers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_offer_id", sa.String(64), nullable=False),
        sa.Column("wc_product_id", sa.Integer(), nullable=False),
        sa.Column("wc_variation_id", sa.Integer(), nullable=True),
        sa.Column("specification_mapping", _JSON, nullable=True),
        sa.Column("mapping_status", sa.String(16), nullable=False, server_default=sa.text("'mapped'")),
        sa.Column("evidence_source", sa.String(32), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # 变体级唯一(仅活跃行):同键历史 archived 与当前 mapped 可共存,历史报价保留.
    op.create_index(
        "ux_supplier_offer_mapping_variation",
        "supplier_offer_mappings",
        ["workspace_id", "supplier_id", "source_offer_id", "wc_variation_id"],
        unique=True,
        postgresql_where=sa.text("mapping_status = 'mapped'"),
        sqlite_where=sa.text("mapping_status = 'mapped'"),
    )
    op.create_index(
        "ux_supplier_offer_mapping_product",
        "supplier_offer_mappings",
        ["workspace_id", "supplier_id", "source_offer_id"],
        unique=True,
        postgresql_where=sa.text("wc_variation_id IS NULL AND mapping_status = 'mapped'"),
        sqlite_where=sa.text("wc_variation_id IS NULL AND mapping_status = 'mapped'"),
    )
    op.create_index(
        "ix_supplier_offer_mapping_wc",
        "supplier_offer_mappings",
        ["workspace_id", "wc_product_id", "wc_variation_id"],
        unique=False,
    )
    op.create_index(
        "ix_supplier_offer_mapping_status",
        "supplier_offer_mappings",
        ["workspace_id", "mapping_status"],
        unique=False,
    )


def downgrade() -> None:
    # 逆序回滚:先删新表/索引,再删列.
    op.drop_index("ix_supplier_offer_mapping_status", table_name="supplier_offer_mappings")
    op.drop_index("ix_supplier_offer_mapping_wc", table_name="supplier_offer_mappings")
    op.drop_index(
        "ux_supplier_offer_mapping_product",
        table_name="supplier_offer_mappings",
        postgresql_where=sa.text("wc_variation_id IS NULL AND mapping_status = 'mapped'"),
        sqlite_where=sa.text("wc_variation_id IS NULL AND mapping_status = 'mapped'"),
    )
    op.drop_index(
        "ux_supplier_offer_mapping_variation",
        table_name="supplier_offer_mappings",
        postgresql_where=sa.text("mapping_status = 'mapped'"),
        sqlite_where=sa.text("mapping_status = 'mapped'"),
    )
    op.drop_table("supplier_offer_mappings")

    op.drop_column("product_cost_snapshots", "variation_sku")
    op.drop_column("product_cost_snapshots", "variation_id")
    op.drop_column("product_cost", "variation_sku")
    op.drop_column("product_cost", "variation_id")

    op.drop_index(
        "ux_inventory_snapshot_product",
        table_name="inventory_snapshots",
        postgresql_where=sa.text("variation_id IS NULL"),
        sqlite_where=sa.text("variation_id IS NULL"),
    )
    op.drop_index(
        "ux_inventory_snapshot_variation",
        table_name="inventory_snapshots",
        postgresql_where=sa.text("variation_id IS NOT NULL"),
        sqlite_where=sa.text("variation_id IS NOT NULL"),
    )
    op.drop_column("inventory_snapshots", "source_timestamp")
    op.drop_column("inventory_snapshots", "variation_sku")
    op.drop_column("inventory_snapshots", "variation_id")

    op.drop_column("order_items", "identity_state")
    op.drop_column("order_items", "variation_sku")
    op.drop_column("order_items", "wc_variation_id")

    op.drop_index(
        "ix_product_mapping_variation_sku",
        table_name="product_mappings",
        postgresql_where=sa.text("variation_sku IS NOT NULL"),
        sqlite_where=sa.text("variation_sku IS NOT NULL"),
    )
    op.drop_index(
        "ux_product_mapping_variation",
        table_name="product_mappings",
        postgresql_where=sa.text("identity_state = 'VARIATION' AND woocommerce_variation_id IS NOT NULL"),
        sqlite_where=sa.text("identity_state = 'VARIATION' AND woocommerce_variation_id IS NOT NULL"),
    )
    op.drop_index(
        "ux_product_mapping_product",
        table_name="product_mappings",
        postgresql_where=sa.text("identity_state = 'PRODUCT'"),
        sqlite_where=sa.text("identity_state = 'PRODUCT'"),
    )
    for _col in (
        "trace_id",
        "identity_state",
        "source_variation_spec",
        "source_offer_id",
        "variation_sku",
        "woocommerce_variation_id",
    ):
        if _column_exists("product_mappings", _col):
            op.drop_column("product_mappings", _col)
    # 回滚时重建旧全局唯一约束(仅当无多变体映射时完全可逆;若已有
    # 多变体映射则回滚失败并报错,属预期限制,如实记录于执行报告).
    if not _constraint_exists("product_mappings", "uq_product_mappings_workspace_nuotao"):
        with op.batch_alter_table("product_mappings") as batch_op:
            batch_op.create_unique_constraint(
                "uq_product_mappings_workspace_nuotao",
                ["workspace_id", "nuotao_product_id"],
            )
    if not _constraint_exists("product_mappings", "uq_product_mappings_workspace_woo"):
        with op.batch_alter_table("product_mappings") as batch_op:
            batch_op.create_unique_constraint(
                "uq_product_mappings_workspace_woo",
                ["workspace_id", "woocommerce_id"],
            )


def _drop_unique_if_exists(table: str, name: str) -> None:
    """安全删除旧全局唯一约束(若存在)."""
    if _constraint_exists(table, name):
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_constraint(name, type_="unique")
