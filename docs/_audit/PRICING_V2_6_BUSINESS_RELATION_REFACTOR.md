# M4 V2.6 业务关系重构报告（Product / Variation 身份模型）

> 版本：v2.6.0 | 状态：已完成（模型/服务/测试）；**未执行生产迁移/回填**

## 1. 重构内容

| 项 | 变更 | 影响 |
|---|---|---|
| `product_mappings` | 移除 `uq_product_mappings_workspace_woo` / `uq_product_mappings_workspace_nuotao` | 一商品可对应多变体映射 |
| `product_mappings` | 加 `woocommerce_variation_id`、`identity_state` 等 6 列 | 三态身份 |
| `product_mappings` | 部分唯一索引（商品级/变体级） | 一变体一映射 |
| `order_items` | 加 `wc_variation_id`、`variation_sku`、`identity_state` | 订单项关联变体 |
| `inventory_snapshots` | 加 `variation_id`、`variation_sku`、`source_timestamp` | 库存按变体维度 |
| `inventory_snapshots` | 移除全局 `uq_inventory_workspace_product_location` | 按变体 + 商品级并存 |
| `product_costs` / `product_cost_snapshots` | 加 `variation_id`、`variation_sku` | 成本按变体维度 |
| `supplier_offer_mappings` | **新表** | 一变体 ↔ 多供应商 ↔ 多 Offer |

## 2. 业务关系语义变化

**旧模型**：`product_mappings` 全局唯一 → 一 Nuotao 商品 ↔ 一 WC 商品（无变体概念）；库存按商品+地点唯一；成本按商品聚合。

**新模型**：

- 一 Nuotao 商品 ↔ 1 条商品级（`PRODUCT`）+ N 条变体级（`VARIATION`）映射。
- 一 WC 变体 ↔ N 个供应商、N 个 1688 Offer（独立多对多）；Offer 失效保留历史。
- 库存与成本可按 `variation_id`（确定身份）或商品级（`variation_id IS NULL`）分开核算。
- `UNKNOWN_LEGACY`：历史记录无法确定维度，**不自动归类**，避免错误聚合。

## 3. 身份判定证据链

`identity_state(wc_product_id, wc_variation_id, product_has_variations, record_has_variation_context=False)`：

- 非空 `wc_variation_id` → `VARIATION`（无需额外证据）。
- 空 `wc_variation_id` + 商品无变体 → `PRODUCT`。
- 空 `wc_variation_id` + 商品有变体 + 记录有变体上下文 → `VARIATION`。
- 其余（含无证据）→ `UNKNOWN_LEGACY`（禁止自动归类）。

## 4. 兼容性

- 历史行（无 `woocommerce_variation_id` / `identity_state`）默认 `UNKNOWN_LEGACY`，不会自动变成 `PRODUCT`，**不破坏**旧数据读取。
- 新增列均可空/有默认；migration `downgrade` 完全可逆（多变体时重建旧约束受限，已记录）。
- 所有唯一约束含 `workspace_id`，跨 workspace 隔离。

## 5. 验证

- 19 项单元/隔离测试通过（含：一商品多变体、变体级唯一、SKU 重复/缺失、workspace 隔离、多 Offer 独立、Offer 失效、冲突保留最新、Inventory 变体级更新与防父商品误更新、成本快照历史一致性、回填幂等、event_log+trace_id、历史兼容）。
- PG 集成测试未运行（无可用 PG/Docker），如实记录。
