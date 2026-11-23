# M4 V2.6 供应商 / 1688 Offer 映射说明

> 版本：v2.6.0 | 实体：`supplier_offer_mappings`（新表）

## 1. 设计动机

旧模型把 `source_offer_id` 设计为商品/变体的**一对一属性**，无法表达：一个 WC 变体对应多个供应商、一个供应商对应多个 1688 Offer、同一 Offer 不同规格/不同报价、Offer 更换与失效。V2.6 引入**独立多对多实体** `SupplierOfferMapping`。

## 2. 列

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | UUID PK | |
| `workspace_id` | UUID | 隔离维度 |
| `supplier_id` | UUID (FK `suppliers.id`, nullable) | 可空：来源未定时保持 `unconfirmed` |
| `source_offer_id` | String(64) | 规范化数字 offer id，非空 |
| `wc_product_id` | Integer | WC 商品 ID |
| `wc_variation_id` | Integer (nullable) | 空 = 商品级映射 |
| `specification_mapping` | JSON | 供应商规格 ↔ WC 变体规格映射证据 |
| `mapping_status` | String(16) | `mapped` / `unconfirmed` / `archived` |
| `evidence_source` | String(32) | 1688 抓取 / 人工确认 / 历史导入 |
| `effective_at` | DateTime tz | 报价生效时间（冲突时保留最新） |
| `source_timestamp` | DateTime tz | 外部系统时间戳 |
| `trace_id` | String(64) | 审计 |

## 3. 唯一性（仅活跃行）

- `ux_supplier_offer_mapping_variation`：`(workspace_id, supplier_id, source_offer_id, wc_variation_id)` **WHERE `mapping_status='mapped'`**（部分唯一）。
- `ux_supplier_offer_mapping_product`：`(workspace_id, supplier_id, source_offer_id)` **WHERE `wc_variation_id IS NULL AND mapping_status='mapped'`**。

> 为什么用部分唯一而不是 `UNIQUE(..., wc_variation_id)`：历史 `archived` 行与当前 `mapped` 行允许**同键共存**（历史报价保留不删除）；若全局唯一，同键插入新 mapped 会与已 archived 行冲突。部分唯一使唯一性只约束**活跃**行。

## 4. 冲突策略（服务层 `upsert_offer_mapping`）

同键 `(workspace, supplier, offer, variation)`：

- 新请求 `effective_at` **晚于**现有最新 → 现有全部 `archived`，新行 `mapped`。
- 新请求 `effective_at` **早于**现有最新 → 新行直接 `archived`（不覆盖正确映射），现有保留。
- `effective_at` 比较统一为 UTC（SQLite 存 naive，PG 存 aware）。

## 5. Offer 失效（`archive_offer_mapping`）

`mapping_status='archived'`，**保留行**（历史报价可追溯），不物理删除。

## 6. 审计

每次 upsert/archive 经 `event_service.create_event` 写 `event_log`（`entity_type="supplier_offer_mapping"`，`payload=mapping.to_summary()`，`trace_id`），与业务同事务。
