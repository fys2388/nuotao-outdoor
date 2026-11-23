# M4 V2.6 ER 关系图（Product / Variation 身份模型）

> 版本：v2.6.0 | 与 `PRICING_V2_6_IDENTITY_IMPLEMENTATION.md` 配套

## 1. 实体关系总览

```
                          +--------------------------+
                          |       products           |   (Nuotao 本地商品)
                          +--------------------------+
                                | 1
                                | 1..N（一变体一映射）
                                v
+--------------------------+   +------------------------------+
|    product_mappings      |   |  supplier_offer_mappings     |
+--------------------------+   +------------------------------+
| PK id (UUID)             |   | PK id (UUID)                 |
| workspace_id (UUID)      |   | workspace_id (UUID)          |
| nuotao_product_id (FK)   |   | supplier_id (FK, nullable)   |
| woocommerce_id (Integer) |   | source_offer_id (String)     |
| woocommerce_variation_id |   | wc_product_id (Integer)      |
| variation_sku            |   | wc_variation_id (Integer)    |
| source_offer_id          |   | specification_mapping (JSON) |
| source_variation_spec    |   | mapping_status               |
| identity_state           |   | effective_at / source_timestamp
| trace_id                 |   | trace_id                     |
+--------------------------+   +------------------------------+
        | 1                          | N (多供应商/多 Offer)
        | 1..N                        |
        v                             v
+----------------------+        +--------------+
|     order_items      |        |   suppliers  |
+----------------------+        +--------------+
| wc_variation_id      |
| variation_sku        |
| identity_state       |
+----------------------+

+----------------------------+        +-----------------------------+
|     inventory_snapshots    |        |  product_costs / _snapshots |
+----------------------------+        +-----------------------------+
| variation_id (Integer)     |        | variation_id (Integer)      |
| variation_sku              |        | variation_sku               |
| source_timestamp           |        | (成本按商品或变体维度)       |
+----------------------------+        +-----------------------------+
```

## 2. 关键关系

| 关系 | 基数 | 说明 |
|---|---|---|
| `products` → `product_mappings` | 1 : 1..N | 一本地商品对应 1 商品级 + N 变体级映射 |
| `product_mappings` → `supplier_offer_mappings` | 1 : N | 一变体/商品 ↔ 多供应商、多 Offer（独立多对多） |
| `supplier_offer_mappings` → `suppliers` | N : 1 | `supplier_id` 可空（来源未定时保持 `unconfirmed`） |
| `product_mappings` → `order_items` | 1 : N | 订单项按 `wc_variation_id` 关联变体身份 |
| `product_mappings` → `inventory_snapshots` | 1 : N | 库存按 `variation_id`（确定身份）或商品级（`variation_id IS NULL`） |
| `product_mappings` → `product_costs` | 1 : N | 成本/成本快照按商品或变体维度 |

## 3. 唯一性约束（均含 `workspace_id`）

| 表 | 索引/约束 | 作用域 | 类型 |
|---|---|---|---|
| `product_mappings` | `ux_product_mapping_product` | `(workspace, woocommerce_id)` WHERE `identity_state='PRODUCT'` | 部分唯一 |
| `product_mappings` | `ux_product_mapping_variation` | `(workspace, woocommerce_id, woocommerce_variation_id)` WHERE `identity_state='VARIATION' AND woocommerce_variation_id IS NOT NULL` | 部分唯一 |
| `product_mappings` | `ix_product_mapping_variation_sku` | `(workspace, variation_sku)` WHERE `variation_sku IS NOT NULL` | 辅助（非唯一） |
| `supplier_offer_mappings` | `ux_supplier_offer_mapping_variation` | `(workspace, supplier, offer, variation)` WHERE `mapping_status='mapped'` | 部分唯一（活跃行） |
| `supplier_offer_mappings` | `ux_supplier_offer_mapping_product` | `(workspace, supplier, offer)` WHERE `wc_variation_id IS NULL AND mapping_status='mapped'` | 部分唯一（活跃行） |
| `inventory_snapshots` | `ux_inventory_snapshot_variation` | `(workspace, product, location, variation_id)` WHERE `variation_id IS NOT NULL` | 部分唯一 |
| `inventory_snapshots` | `ux_inventory_snapshot_product` | `(workspace, product, location)` WHERE `variation_id IS NULL` | 部分唯一 |

## 4. 已移除的全局唯一约束

| 表 | 移除约束 | 原因 |
|---|---|---|
| `product_mappings` | `uq_product_mappings_workspace_woo` | 无法表达「一商品多变体」 |
| `product_mappings` | `uq_product_mappings_workspace_nuotao` | 一变体一映射后一本地商品可对应多变体 |
| `inventory_snapshots` | `uq_inventory_workspace_product_location` | 需按变体维护库存，改为两个部分唯一 |

## 5. 身份状态流转

```
[空 vid + 无变体证据] ────────────────► UNKNOWN_LEGACY（禁止自动归类）
[空 vid + 商品无变体] ────────────────► PRODUCT
[空 vid + 商品有变体 + 记录有变体上下文] ► VARIATION
[非空 vid] ─────────────────────────► VARIATION
```
