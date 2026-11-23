# M4 V2.5 P0-2 — 数据库约束及迁移 DDL 草案

- 指令：`docs/_audit/V2_5_CHATGPT_DIRECTIVE.md`（三、P0，交付第 3 项）
- 状态：**草案，不执行**（需 Owner 单独书面授权）

---

## 1. 迁移文件

`backend/alembic/versions/2026_11_23_v25_identity_model.py`（草案；upgrade/downgrade 可逆）

## 2. upgrade() — 身份维度字段

```python
def upgrade() -> None:
    # 1) product_mappings：变体维度 + 身份状态
    op.add_column('product_mappings', sa.Column('woocommerce_variation_id', sa.BigInteger(), nullable=True))
    op.add_column('product_mappings', sa.Column('variation_sku', sa.String(191), nullable=True))
    op.add_column('product_mappings', sa.Column('source_offer_id', sa.String(64), nullable=True))
    op.add_column('product_mappings', sa.Column('source_variation_spec', postgresql.JSONB(), nullable=True))
    op.add_column('product_mappings', sa.Column('identity_state', sa.String(16), nullable=False, server_default='UNKNOWN_LEGACY'))

    # 2) order_items：变体身份
    op.add_column('order_items', sa.Column('wc_variation_id', sa.BigInteger(), nullable=True))
    op.add_column('order_items', sa.Column('variation_sku', sa.String(191), nullable=True))
    op.add_column('order_items', sa.Column('identity_state', sa.String(16), nullable=False, server_default='UNKNOWN_LEGACY'))

    # 3) inventory_snapshots：变体身份
    op.add_column('inventory_snapshots', sa.Column('variation_id', sa.BigInteger(), nullable=True))
    op.add_column('inventory_snapshots', sa.Column('variation_sku', sa.String(191), nullable=True))
    op.add_column('inventory_snapshots', sa.Column('source_timestamp', sa.DateTime(timezone=True), nullable=True))

    # 4) product_cost：变体身份
    op.add_column('product_cost', sa.Column('variation_id', sa.BigInteger(), nullable=True))
    op.add_column('product_cost', sa.Column('variation_sku', sa.String(191), nullable=True))

    # 5) 部分唯一索引（PostgreSQL）
    op.create_index('ux_product_mapping_product',
        'product_mappings', ['workspace_id', 'woocommerce_id'],
        unique=True, postgresql_where=sa.text("identity_state = 'PRODUCT'"))
    op.create_index('ux_product_mapping_variation',
        'product_mappings', ['workspace_id', 'woocommerce_id', 'woocommerce_variation_id'],
        unique=True, postgresql_where=sa.text("identity_state = 'VARIATION'"))
    op.create_index('ix_product_mapping_variation_sku',
        'product_mappings', ['workspace_id', 'variation_sku'],
        unique=False, postgresql_where=sa.text("variation_sku IS NOT NULL"))
    op.create_index('ux_order_item_variation',
        'order_items', ['workspace_id', 'wc_product_id', 'wc_variation_id'],
        unique=True, postgresql_where=sa.text("identity_state = 'VARIATION'"))
    op.create_index('ux_inventory_snapshot_variation',
        'inventory_snapshots', ['workspace_id', 'product_id', 'variation_id', 'location_id'],
        unique=True, postgresql_where=sa.text("identity_state = 'VARIATION'"))
```

## 3. downgrade() — 可逆回滚

```python
def downgrade() -> None:
    # 回滚：先删索引，再删列（数据备份先行）
    op.drop_index('ux_inventory_snapshot_variation', table_name='inventory_snapshots')
    op.drop_index('ux_order_item_variation', table_name='order_items')
    op.drop_index('ix_product_mapping_variation_sku', table_name='product_mappings')
    op.drop_index('ux_product_mapping_variation', table_name='product_mappings')
    op.drop_index('ux_product_mapping_product', table_name='product_mappings')
    op.drop_column('product_cost', 'variation_sku')
    op.drop_column('product_cost', 'variation_id')
    op.drop_column('inventory_snapshots', 'source_timestamp')
    op.drop_column('inventory_snapshots', 'variation_sku')
    op.drop_column('inventory_snapshots', 'variation_id')
    op.drop_column('order_items', 'identity_state')
    op.drop_column('order_items', 'variation_sku')
    op.drop_column('order_items', 'wc_variation_id')
    op.drop_column('product_mappings', 'identity_state')
    op.drop_column('product_mappings', 'source_variation_spec')
    op.drop_column('product_mappings', 'source_offer_id')
    op.drop_column('product_mappings', 'variation_sku')
    op.drop_column('product_mappings', 'woocommerce_variation_id')
```

## 4. 回填方案（数据迁移，需单独授权）

1. **备份**：迁移前全表备份（`CREATE TABLE product_mappings_bak AS SELECT * FROM product_mappings;` 等）。
2. **身份回填**（71 行快照 + WC 变体 API）：
   - wc_variation_id 非空 → `identity_state='VARIATION'`，`variation_sku` 填 WC 变体 SKU。
   - wc_variation_id 空 + 商品无变体 → `identity_state='PRODUCT'`。
   - wc_variation_id 空 + 商品有变体 → `identity_state='UNKNOWN_LEGACY'`（不猜测）。
3. **校验**：逐行核对 71 行（70 VARIATION / 1 PRODUCT / 0 UNKNOWN），唯一约束无冲突。
4. **回滚**：任何校验失败 → `DROP COLUMN`（downgrade）+ 恢复备份。
5. **SKU 不动**：线上 SKU 保留（仅新增 variation_sku 辅助列，SKU 不作唯一主键）。

## 5. 禁止项（草案内不执行）

- 生产迁移 / 回填：**不执行**（仅草案）。
- 修改线上 SKU：**不执行**。
- 回填前不删除/重写任何现有数据。
