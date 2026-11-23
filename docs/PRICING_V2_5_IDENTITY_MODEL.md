# M4 V2.5 P0-2 — SKU / Variation 身份模型设计（修订）

- 指令：`docs/_audit/V2_5_CHATGPT_DIRECTIVE.md`（三、P0）
- 修订目标：**历史数据不能因为 wc_variation_id 为空就自动认定为商品级记录**；明确三种身份状态。
- 范围：只交付设计 + 迁移 DDL 草案 + 测试方案，**不执行生产数据库迁移**。

---

## 1. 三种身份状态

| 身份状态 | 含义 | 判定条件 |
|---|---|---|
| `PRODUCT` | 记录绑定**商品级**（产品本身无变体） | wc_variation_id 为空 **且** WC 商品确实无变体（GET /products/{id} variations 为空） |
| `VARIATION` | 记录绑定**变体级** | wc_variation_id 非空（WC 变体存在，有唯一变体 SKU） |
| `UNKNOWN_LEGACY` | 历史记录**无法确定**商品级/变体级 | wc_variation_id 为空，但无足够证据判断商品是否有变体（来源残缺/早于变体映射） |

**核心规则（ChatGPT 修正）**：wc_variation_id 为空**不代表商品级**。必须显式判定：

```
identity_state(wc_product_id, wc_variation_id, evidence):
  if wc_variation_id is not None and wc_variation_id != '':
      return VARIATION
  # wc_variation_id 为空
  if evidence.product_has_variations is False:      # WC 商品无变体（产品级）
      return PRODUCT
  if evidence.product_has_variations is True:       # 商品有变体但本条记录无变体 id
      if evidence.record_has_variation_context:      # 记录来源可确定变体
          return VARIATION                           # 按上下文变体归类
      return UNKNOWN_LEGACY                          # 无法确定 → 不猜测
  return UNKNOWN_LEGACY                              # 无证据 → 不猜测
```

- **SKU 仅作辅助识别字段，不得作为唯一身份主键**（SKU 可重、可空、可变）。

## 2. 数据库设计（product_mappings 修订 + 关联表身份维度）

### 2.1 product_mappings 新增字段（全 nullable，默认 UNKNOWN_LEGACY）

```sql
ALTER TABLE product_mappings
  ADD COLUMN woocommerce_variation_id BIGINT NULL,
  ADD COLUMN variation_sku           VARCHAR(191) NULL,
  ADD COLUMN source_offer_id         VARCHAR(64)  NULL,
  ADD COLUMN source_variation_spec   JSONB        NULL,
  ADD COLUMN identity_state          VARCHAR(16)  NOT NULL DEFAULT 'UNKNOWN_LEGACY';
```

### 2.2 关联表身份维度（新增/修订）

| 表 | 新增字段 | 说明 |
|---|---|---|
| `order_items` | `wc_variation_id BIGINT NULL`、`variation_sku VARCHAR(191) NULL`、`identity_state VARCHAR(16) DEFAULT 'UNKNOWN_LEGACY'` | 订单行绑定变体；历史无法确定 → UNKNOWN_LEGACY |
| `inventory_snapshots` | `variation_id BIGINT NULL`、`variation_sku VARCHAR(191) NULL`、`source_timestamp TIMESTAMPTZ NULL` | 库存快照变体维度 |
| `product_cost`（成本快照） | `variation_id BIGINT NULL`、`variation_sku VARCHAR(191) NULL` | 成本按变体 |
| `product_mappings` | 见 2.1 | 映射身份 |

### 2.3 唯一性约束（PostgreSQL 部分唯一索引）

```sql
-- 商品级唯一：每个商品仅一条商品级映射
CREATE UNIQUE INDEX ux_product_mapping_product
  ON product_mappings(workspace_id, woocommerce_id)
  WHERE identity_state = 'PRODUCT';

-- 变体级唯一：每个 (商品, 变体) 仅一条
CREATE UNIQUE INDEX ux_product_mapping_variation
  ON product_mappings(workspace_id, woocommerce_id, woocommerce_variation_id)
  WHERE identity_state = 'VARIATION';

-- SKU 辅助索引（非唯一，允许重/空/历史 SKU）
CREATE INDEX ix_product_mapping_variation_sku
  ON product_mappings(workspace_id, variation_sku);

-- 订单行：变体级唯一键（商品+变体）
CREATE UNIQUE INDEX ux_order_item_variation
  ON order_items(workspace_id, wc_product_id, wc_variation_id)
  WHERE identity_state = 'VARIATION';

-- 库存快照：变体级唯一（商品+变体+位置+时间）
CREATE UNIQUE INDEX ux_inventory_snapshot_variation
  ON inventory_snapshots(workspace_id, product_id, variation_id, location_id)
  WHERE identity_state = 'VARIATION';
```

## 3. 身份关系（实体边界）

```
Product (商品)
  ├── ProductMapping [PRODUCT]      (商品级：woocommerce_id, identity_state='PRODUCT')
  ├── ProductMapping [VARIATION]    (变体级：woocommerce_id + woocommerce_variation_id)
  │     └── source_offer_id ── SupplierQuote (多供应商报价 1:N)
  ├── OrderItem  [VARIATION/UNKNOWN_LEGACY]  (订单行按 wc_variation_id)
  ├── InventorySnapshot [VARIATION/UNKNOWN_LEGACY]
  └── ProductCost [VARIATION/UNKNOWN_LEGACY]
```

- 商品级与变体级**互斥**：同一 woocommerce_id 不同时存在 PRODUCT 与 VARIATION 映射（部分唯一索引区分）。
- `source_offer_id` 支持**多供应商报价**：一个变体可关联多个供应商 offer（报价历史），映射表变体—供应商 1:N。

## 4. 新订单记录规则

- 新订单 webhook：从 WC 订单行取 `product_id` + `variation_id` + `sku`（变体级）→ 写 `order_items.wc_product_id / wc_variation_id / variation_sku / identity_state='VARIATION'`。
- 无变体商品 → `wc_variation_id=NULL` + `identity_state='PRODUCT'`。
- 数据异常（变体 id 缺失但商品有变体）→ `UNKNOWN_LEGACY`（不猜测）。

## 5. 历史数据 UNKNOWN_LEGACY 保留

- 历史订单/库存/成本快照若无法确定变体（无 wc_variation_id 且商品有变体）→ 保留 `identity_state='UNKNOWN_LEGACY'`。
- **不自动回退为商品级**；保留原始标识 + 审计标记，人工/后续核对后更新。
- 回填可逆：备份原表 → 回填 → 校验 → 出错 DROP COLUMN 回滚（详见迁移 DDL 草案）。

## 6. 71 行核对结论（详见 `PRICING_V2_5_IDENTITY_71ROW_AUDIT.md`）

- **70 行 VARIATION**（每个有唯一 wc_variation_id + 唯一 WC 变体 SKU，无重复）。
- **1 行 PRODUCT**（2687 净水器：无变体，商品级正确）。
- **0 行 UNKNOWN_LEGACY**（本批 71 行快照全部可确定身份）。
- 70 变体 + 1 商品 = 71 行，与"70 个有效变体"一致（70 变体 + 1 产品级商品）。

## 7. 交付边界（遵守）

- 只交付设计 + DDL 草案 + 测试方案。
- **不执行生产数据库迁移**；不修改线上 SKU；SKU 仅辅助。
- 迁移/回填需 Owner 单独书面授权。
