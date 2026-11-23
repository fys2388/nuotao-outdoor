# M4 V2.6 Product / Variation 身份模型实现

> 版本：v2.6.0 | 状态：实现完成（待 Owner 授权后迁移/回填）| 关联指令：`docs/_audit/V2_6_CHATGPT_DIRECTIVE.md`

## 1. 目标与范围

把 WooCommerce 商品（Product）与变体（Variation）从「扁平商品记录」升级为**三态身份模型**，并建立「Nuotao 商品 ↔ WC 商品/变体 ↔ 供应商/1688 Offer」的关联关系，为成本、库存、报价按变体维度核算提供数据底座。

本实现**不执行**生产数据库迁移、回填、库存同步、WC API 写入、自动采购/加购、价格/SKU/规则变更与部署（指令 §8 禁止项）。

## 2. 三态身份模型

| 状态 | 判定条件（`identity_state` 纯函数） | 语义 |
|---|---|---|
| `PRODUCT` | `wc_variation_id` 为空 **且** WC 商品无变体（有证据） | 商品级映射 |
| `VARIATION` | `wc_variation_id` 非空 | 变体级映射 |
| `UNKNOWN_LEGACY` | `wc_variation_id` 为空但无足够证据（或商品有变体且记录无变体上下文） | 历史未知，**禁止自动归类** |

核心规则（指令 §5/§7）：

- **空 `wc_variation_id` ≠ PRODUCT**：`identity_state(wc_product_id, wc_variation_id, product_has_variations, record_has_variation_context=False)` 中，`wc_variation_id is None` 且无变体证据 → `UNKNOWN_LEGACY`。
- **`UNKNOWN_LEGACY` 永不自动归类**：需外部证据（`record_has_variation_context=True` 或商品无变体）才判定。
- **SKU 是辅助字段**：非唯一主键，可重/可空/可变。
- **`workspace_id` 进入所有唯一约束**：跨 workspace 隔离。
- **部分唯一索引**：商品级 / 变体级分别唯一，允许「一商品多变体」。

## 3. 模型改造

### 3.1 `ProductMapping`（`app/models/product_mapping.py`）

- **新增列**：`woocommerce_variation_id`(Integer)、`variation_sku`(String(191))、`source_offer_id`(String(32))、`source_variation_spec`(AI_JSON)、`identity_state`(String(16) 默认 `UNKNOWN_LEGACY`)、`trace_id`(String(64))。
- **移除唯一约束**：
  - `uq_product_mappings_workspace_woo`：全局唯一「一 WC 商品一映射」，无法表达「一商品多变体」→ 移除。
  - `uq_product_mappings_workspace_nuotao`：全局唯一「一本地商品一映射」，一变体一映射后本地商品可对应 1 商品级 + N 变体级 → 移除。
- **新增部分唯一索引**：
  - `ux_product_mapping_product`：`(workspace_id, woocommerce_id)` WHERE `identity_state='PRODUCT'`。
  - `ux_product_mapping_variation`：`(workspace_id, woocommerce_id, woocommerce_variation_id)` WHERE `identity_state='VARIATION' AND woocommerce_variation_id IS NOT NULL`。
  - `ix_product_mapping_variation_sku`：`(workspace_id, variation_sku)` WHERE `variation_sku IS NOT NULL`（非唯一，辅助识别）。
- **UUID 列改为跨方言 `Uuid`**：PostgreSQL 原生 UUID；SQLite 编译 `CHAR(32)`（TEXT affinity），避免 `postgresql.UUID` 在 SQLite 下 NUMERIC affinity 把全数字 UUID（如 `0000...0001`）误转整数导致读取失败。

### 3.2 `OrderItem`（`app/models/order.py`）

- 新增 `wc_variation_id`(Integer, index)、`variation_sku`(String(191))、`identity_state`(String(16) 默认 `UNKNOWN_LEGACY`)。
- **不设全局 order-item 唯一索引**：`(workspace, product, wc_variation_id)` 唯一会错误阻止「不同订单共享同一变体」，为 V2.5 DDL 已记录偏差。

### 3.3 `InventorySnapshot`（`app/models/supply_chain.py`）

- 新增 `variation_id`(Integer, index)、`variation_sku`(String(191))、`source_timestamp`(DateTime tz)。
- 移除 `uq_inventory_workspace_product_location`（全局「一商品一地点一库存」）→ 改为两个部分唯一索引：
  - `ux_inventory_snapshot_variation`：`(workspace_id, product_id, location_id, variation_id)` WHERE `variation_id IS NOT NULL`。
  - `ux_inventory_snapshot_product`：`(workspace_id, product_id, location_id)` WHERE `variation_id IS NULL`。

### 3.4 `ProductCost` / `ProductCostSnapshot`

- 各新增 `variation_id`(Integer, index)、`variation_sku`(String(191))，使成本/成本快照可明确对应商品或变体。

### 3.5 `SupplierOfferMapping`（新表，`app/models/supplier_offer_mapping.py`）

独立多对多实体：一个 WC 变体/商品 ↔ 多供应商 ↔ 多 1688 Offer；Offer 更换/失效保留历史报价（`archived`）。

- 列：`supplier_id`、`source_offer_id`、`wc_product_id`、`wc_variation_id`、`specification_mapping`(AI_JSON)、`mapping_status`(`mapped`/`unconfirmed`/`archived`)、`evidence_source`、`effective_at`、`source_timestamp`、`trace_id`。
- **活跃行唯一**（部分索引，允许同键历史 archived 与当前 mapped 共存）：
  - `ux_supplier_offer_mapping_variation`：`(workspace_id, supplier_id, source_offer_id, wc_variation_id)` WHERE `mapping_status='mapped'`。
  - `ux_supplier_offer_mapping_product`：`(workspace_id, supplier_id, source_offer_id)` WHERE `wc_variation_id IS NULL AND mapping_status='mapped'`。
- 辅助索引：`ix_supplier_offer_mapping_wc`、`ix_supplier_offer_mapping_status`。

## 4. 服务层（`app/services/identity_model_v26.py`）

| 函数 | 职责 |
|---|---|
| `identity_state` | 纯函数三态判定（无 DB/IO） |
| `classify_rows` / `classify_csv_rows` / `row_from_csv_row` | 批量分类；CSV 行归一化（幂等） |
| `upsert_product_mapping` / `upsert_variation_mapping` | 商品级/变体级映射 upsert |
| `upsert_offer_mapping` | 供应商/Offer 映射 upsert；同键保留最新 `effective_at`，旧版 `archived` |
| `archive_offer_mapping` | Offer 失效归档（保留历史） |
| `record_order_item` | 订单项关联变体身份 |
| `update_inventory_variation` | 库存按确定变体身份更新；guard：无 vid 且商品有变体 → 跳过（不更新父商品批量） |
| `append_cost_snapshot` | 成本快照 append-only（不覆盖历史） |
| `backfill_71_rows` | 71 行历史回填模拟（隔离数据，幂等，**不写生产**） |

**写链路**：所有写操作经 `event_service.create_event(session, *, workspace_id, event_type, entity_type, entity_id, payload, trace_id, commit=False)` 写 `event_log`，由调用方统一 `commit`，身份/历史关系变更保留 `trace_id`。

## 5. 迁移（`alembic/versions/0092_identity_model.py`）

- `upgrade`：条件删除 `uq_product_mappings_workspace_woo` / `uq_product_mappings_workspace_nuotao` / `uq_inventory_workspace_product_location`（inspector 检查存在性）；加列；建部分唯一索引；建 `supplier_offer_mappings` 表。
- `downgrade`：完全可逆（删表/索引/列，重建旧唯一约束）；**限制**：若已存在多变体映射，重建 `uq_product_mappings_workspace_nuotao`/`uq_product_mappings_workspace_woo` 会因重复键失败（预期，如实记录）。
- 类型：`_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")` 保持 SQLite 可测。

## 6. 测试结果

| 项 | 结果 |
|---|---|
| 单元/隔离测试（SQLite 内存，19 项） | **全部通过** |
| PostgreSQL 集成测试（Testcontainers） | **未运行**：无可用 PG/Docker（testcontainers 未安装），文件按设计跳过 |
| Ruff | **全部通过**（4 个服务/模型文件 + 2 个测试文件） |
| Migration `ast.parse` | **通过** |
| 生产迁移/回填 | **未执行**（指令 §8） |

## 7. 边界与偏差记录

- 无全局 order-item 唯一索引（V2.5 DDL 偏差，理由见 §3.2）。
- `identity_state` 纯函数按 `is not None` 判定；`row_from_csv_row` 把 CSV `"0"` 归一化为空（无变体）。
- downgrade 重建旧约束在多变体场景受限（§5）。
