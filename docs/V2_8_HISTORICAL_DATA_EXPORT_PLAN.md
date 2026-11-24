# M4 V2.8 历史数据脱敏导出方案 V1.0（V2.8-HISTORICAL-DATA-EXPORT-PREP）

> 工作项：`V2.8-HISTORICAL-DATA-EXPORT-PREP`（Owner 并行开发提速方案 V1.0 §二「历史数据导出准备」）。
> 角色：`v28-historical-export`。分支：`audit/pricing-v28-historical-export`（基于 main `62f29bf`，worktree `phase-export`）。
> 状态：**纯起草，READY FOR REVIEW**。本轮**不连生产库、不执行 SQL、不跑脱敏脚本对真实数据**；脚本逻辑仅在本地测试数据上自校验。
> 基准文档：`docs/_audit/V2_8_PARALLEL_DEVELOPMENT_DIRECTIVE.md`、`docs/V2_8_EXECUTION_REPORT.md`（§5 历史重算缺口）、`docs/V2_8_GAP_AND_RISK_REGISTER.md`（R1/R2/R3/R4/R7）、`docs/V2_8_DATA_LINEAGE_AUDIT.md`（§8/§11 设计字段）。
> **不宣称 V2.8 通过**；0076 继续冻结，未触碰。

---

## §1 导出范围与脱敏规范

### 1.1 数据范围

- 时间窗：默认**最近 90 天**（`?start_date`/`?end_date` 参数化），Owner 要求数据量大时**先 30 天试点**。
- 范围：目标 workspace（单 workspace 部署时即默认 workspace UUID；SQL 全部以 `:workspace_id` 参数限定，不跨 workspace）。
- 对象：B2C WooCommerce 订单链（`business_model='B2C'`）；B2B 链路不在本次 7 组范围内（如需另开工作项）。
- 原则：**缺失字段保留 NULL/空，不填 0**；导出时标注缺失原因（`missing_reason`，见 §1.4）。

### 1.2 七组数据规范（表名 / 必需字段 / 脱敏规则 / 保留字段）

关联键设计（全部保留，保证订单↔成本↔价格↔退款不断链）：

```
orders ──< order_items ──(product_id, wc_variation_id)──> products ──< product_cost_snapshots
orders ──< refund_cases ──(order_id)
orders ──(payment_method, order 金额)──> 支付交易（E 组，见 1.2-E 说明）
products ──< product_mappings ──(woocommerce_id, wc_variation_id)──> 价格历史（D 组）
shipment_records ──< logistics_events ──(shipment_id)   （F 组，含订单履约关联见下）
campaigns ──(product_id)──> products + orders.advertising_cost   （G 组）
```

| 组 | 表 | 必需字段（导出列） | 脱敏规则 |
|---|---|---|---|
| **A 订单** | `orders`, `order_items` | orders: `id, external_order_id, status, payment_status, fulfillment_status, currency, country, payment_method, source, business_model, customer_reference_id, customer_account_id, subtotal, shipping_total, discount_total, tax_total, total, payment_fee, refunded_amount, advertising_cost, profit_snapshot, rule_results, trace_id, received_at, created_at, updated_at`；order_items: `id, order_id, external_item_id, product_id, sku, name, quantity, unit_price, line_total, wc_variation_id, variation_sku, identity_state` | 见 §1.3：`external_order_id` 与 `customer_account_id` 做稳定伪 ID；`profit_snapshot`/`rule_results` JSON 内嵌字段逐键处理（删 PII 键、保留金额/时间/口径键）；`name`（商品名）保留（非 PII）；SKU 保留 |
| **B 税费** | `orders`（税额列）+ 订单行级税分摊 | `orders.id, currency, subtotal, shipping_total, discount_total, tax_total, total`；行级：`order_items.id, order_id, quantity, unit_price, line_total`（行级税额 = tax_total × line_total/（subtotal−discount_total）推导值，标注 `derived=true`；**原表无行级税列时不伪造**，标 `missing_reason='tax_not_collected_at_line'`） | 无 PII；金额/币种/税率相关字段全保留。税额为 0 是真实值（免税）保留 0；NULL 保留 NULL |
| **C 成本快照** | `product_cost_snapshots`（append-only 多版本）+ `product_cost`（当前行） | snapshots: `id, product_id, variation_id, variation_sku, currency, purchase_cost, domestic_shipping, first_leg_shipping, last_leg_shipping, international_shipping, packaging, tax_estimate, handling, total_landed_cost, version, payment_fee, marketing_amortization, after_sales_loss, total_cost, weight_kg, source, valid_from, trace_id, created_at`；当前行 `product_cost` 同列 | 全保留（金额/币种/时间/版本）。R7 关键：快照 `version` 与 `valid_from` 是"历史成本版本缺失"定量的证据列 |
| **D 价格历史** | `products.meta`（价格 JSON 字符串，含 `price`/`regular_price`/`sale_price`/`woocommerce_id`/`total_sales`）+ `products.updated_at/created_at` + `product_mappings`（`woocommerce_id, woocommerce_variation_id, variation_sku, identity_state, last_synced_at`）+ 快照侧 `product_cost_snapshots.valid_from` | 每产品一行：`products.id, sku, meta->>'price' AS price, meta->>'regular_price', meta->>'sale_price', meta->>'woocommerce_id' AS wc_product_id, meta->>'total_sales', updated_at AS price_modified_at, created_at`；映射：`product_mappings.*`；变体价格：`order_items.unit_price` 作为历史成交价佐证（A 组已含） | 价格/币种/修改时间/SKU 全保留；`woocommerce_id` 是 WC 外部 ID（业务标识，保留；Owner 若要求也可伪 ID，默认保留）；**无价格发布记录表（R6 缺口）**——D 组只能给"当前价格 + 最后修改时间 + 映射"，无法给逐次发布历史，导出时如实标 `price_lineage='LEGACY_NO_PUBLICATION_RECORD'`，**不伪造** |
| **E 支付** | `orders`（支付列）+ `refund_cases`（退款生命周期） | orders: `id, payment_method, payment_status, currency, total, payment_fee, refunded_amount, received_at`；refund_cases: `id, order_id, status, refund_type, requested_amount, approved_amount, executed_amount, payment_provider, payment_refund_id, woocommerce_refund_id, executed_at, created_at` | `payment_refund_id`/`woocommerce_refund_id` 为支付交易 ID → 稳定伪 ID（§1.3）；金额/币种/时间保留。**说明：本系统未落支付流水表**（Stripe/PayPal 处理，本地禁止存卡号/CVV）；E 组"支付交易"= 订单级支付列 + 退款执行记录，`missing_reason='payment_transactions_not_stored'` 如实标注，不造流水 |
| **F 物流** | `shipment_records` + `logistics_events` | shipments: `id, purchase_order_id, b2b_order_id, carrier, origin, destination, tracking_number, status, ship_date, delivery_time_days, promised_delivery, actual_cost, actual_cost_currency, delay_reason, created_at`；events: `id, shipment_id, event_type, location, description, occurred_at` | 运输费 `actual_cost`/币种保留；`origin/destination/location` 为城市/仓位（非详细地址）保留；`tracking_number` 稳定伪 ID；**说明：B2C 订单行无 shipment 外键**（现 schema 中 shipment 关联 purchase_order/b2b_order），F 组导出全量时间窗内 shipment，订单↔物流的订单级关联以 `orders.shipping_total`（客户付费运费）+ 成本快照 `last_leg_shipping`（尾程成本）对齐，不强行伪造关联键 |
| **G 营销** | `campaigns` + `creative_assets` + `orders.advertising_cost` + `wc_clickback_events`（购买事件） | campaigns: `id, platform, campaign_id, name, product_id, status, currency, budget, spend, impressions, clicks, conversion, revenue, roas, started_at, ended_at`；orders: `id, advertising_cost, profit_snapshot->>'cost_details'`；clickback: `id, product_id, event_type, count, window_start, window_end, source` | `campaign_id`（平台侧 ID）稳定伪 ID；金额/计数/时间保留；`raw_payload` 大 JSON **不导出**（可能含平台侧 PII/凭据，`missing_reason='payload_excluded'`）；订单归因= `orders.advertising_cost` 当前分摊值（历史逐次分摊记录不存在，如实标注，不造数） |

### 1.3 稳定随机 ID 方案（不可逆 + 多次导出一致）

对以下标识做稳定伪 ID 替换（**在导出后脱敏脚本做，不在 SQL 里做**，见 §2 理由）：

- 订单号 `orders.external_order_id`、客户 `customer_account_id` / `customer_reference_id`、支付交易 `refund_cases.payment_refund_id` / `woocommerce_refund_id`、物流单号 `shipment_records.tracking_number`、广告计划 `campaigns.campaign_id`。

**算法**（二选一，脚本实现 SHA256 为默认，uuid5 为备选）：

```
pseudo_id = HEX( SHA256( f"{entity_kind}|{workspace_id}|{original_id}|{salt}" ) )[:32]
# 备选: uuid.uuid5( UUID_Namespace, f"{entity_kind}|{workspace_id}|{original_id}" )，
# 其中 Namespace = uuid.UUID(bytes=SHA256(b"nuotao|v28-export|" + salt)[:16])
```

- **salt 由 Owner 通过安全渠道单独提供，不写进脚本/仓库/文档/环境变量示例**。脚本运行时从 `--salt-file`（Owner 交付的加密/受控文件）或受控 CLI 参数读入；缺 salt 则脚本拒绝运行（fail-closed）。
- 性质：确定性（同一原始 ID + 同一 salt 永远映射同一伪 ID → 多次导出关联不断）；不可逆（HMAC/SHA256 单向，无盐表反查）；跨组一致（A/E/F/G 共享同一映射表）。**G3 加固**：映射表写入 **Owner 受控的独立受限目录**（`--id-map-dir`，与脱敏交付包、Git 工作树、raw/out 目录全部隔离，0600 文件 / 0700 目录，O_EXCL 防覆盖），**不随脱敏包交付、不入 Git、不进日志/异常输出**；保留期由 `--id-map-retention-days` 显式声明，**销毁时点由 Owner 决定**（30 天审阅 + Owner 签署后执行）。
- SKU、`woocommerce_id`（商品维度业务标识，Owner 指定保留）不替换。

### 1.4 缺失字段处理（不填 0）

- 缺失/未采集字段一律保留 **NULL/空**，并在行内或侧列标注 `missing_reason`：
  - `not_collected`：原系统从未采集（如历史订单无行级税）；
  - `field_not_stored`：当前 schema 无此列（如订单行 `cost_snapshot_id`/`cost_snapshot_version`、`pricing_rule_version`、`pricing_engine_version`、`evidence_grade`——R6/R7/R12/R13 缺口）；
  - `unknown_value`：值为未知但列存在（如 `identity_state='UNKNOWN_LEGACY'` 保留原值）；
  - `legacy_no_record`：历史无记录（如 `price_lineage`、`advertising_cost` 历史分摊）；
  - `payload_excluded`：JSON 大字段主动排除（含潜在 PII/凭据）。
- 0 是合法业务值（免运费、免税、零折扣）——0 保留 0；**禁止把 NULL 填成 0**。脱敏脚本自校验区分"原始即 0"与"被填 0"（见 §3 校验项）。

### 1.5 明确不导出（L4/机密）

- WC 订单 billing/shipping 姓名/邮箱/电话/地址（本地 `orders` 表本就不存，但 E 组来源若含 WC API 原始订单 JSON，脚本必须剥掉 `billing.*`/`shipping.*` 全部 PII 键）；
- 支付凭据/卡号/CVV/Token/Cookie（本系统本地不存；导出文件若混入 `api_key`/`token` 类键值一律剥除，正则兜底，见 §3）；
- `customer_accounts.display_name`（客户主数据名）；`raw_payload`（wc_clickback）；供应商报价原始 URL 与 1688 采集数据（不在 7 组范围）。

---

## §2 只读 SELECT SQL（7 组，全只读，未在生产执行）

> 约定：**PG16 参数** `:workspace_id`、`:start_date`、`:end_date`（timestamptz）、`:cursor`（keyset）、`:batch_size`。全部仅 `SELECT`，无 DDL/DML/写操作。
> **分页**：大表（A/C 组）用 keyset pagination——按 `(received_at, id) > (:start_date, :cursor)` 分批，避免 OFFSET 深扫拖垮生产；批大小建议 500 行/批。C 组小表按 `valid_from` 分批。
> **脱敏在 SELECT 外的理由**：SQL 保持纯只读、可在生产直接给 DBA 审阅；脱敏逻辑（伪 ID 映射 + PII 剥除 + 缺失标注）集中在受控脚本里做，盐不进入 SQL 引擎环境；生产侧只需执行 `COPY ... TO CSV`（或 SELECT 导出），导出产物落到只读副本目录后再本地脱敏。

### 2.0 批次 0 — 计数与游标（辅助只读，非数据导出）

```sql
-- 时间窗内订单数与游标范围（用于分批计划）
SELECT count(*) AS order_count,
       min(o.received_at) AS min_received, max(o.received_at) AS max_received
FROM orders o
WHERE o.workspace_id = :workspace_id
  AND o.business_model = 'B2C'
  AND o.received_at >= :start_date AND o.received_at < :end_date;
```

### 2.1 A 组 — 订单 + 订单行（含税总额与利润快照）

```sql
SELECT
  o.id                 AS order_pk,
  o.workspace_id       AS workspace_id,
  o.external_order_id,
  o.status, o.payment_status, o.fulfillment_status,
  o.currency, o.country, o.payment_method, o.source, o.business_model,
  o.customer_reference_id,
  o.customer_account_id,
  o.subtotal, o.shipping_total, o.discount_total, o.tax_total, o.total,
  o.payment_fee, o.refunded_amount, o.advertising_cost,
  o.profit_snapshot, o.rule_results,
  o.trace_id, o.received_at, o.created_at, o.updated_at,
  oi.id                AS line_pk,
  oi.workspace_id      AS order_item_workspace_id,
  oi.external_item_id,
  oi.product_id,
  oi.sku, oi.name AS line_name,
  oi.quantity, oi.unit_price, oi.line_total,
  oi.wc_variation_id, oi.variation_sku, oi.identity_state
FROM orders o
LEFT JOIN order_items oi
       ON oi.order_id = o.id AND oi.workspace_id = o.workspace_id
WHERE o.workspace_id = :workspace_id
  AND o.business_model = 'B2C'
  AND o.received_at >= :start_date
  AND o.received_at <  :end_date
  AND (:cursor IS NULL
       OR (o.received_at, o.id) > (:cursor, :cursor_pk))   -- keyset 游标
ORDER BY o.received_at ASC, o.id ASC
LIMIT :batch_size;
```

要点：`LEFT JOIN` 保留无行项订单（异常订单也是审计对象）；`profit_snapshot` JSON 整列导出（脱敏脚本逐键剥 PII 键）；`cursor_pk` 为上一批最后一行 `o.id`。

### 2.2 B 组 — 税额/税率/币种（订单头 + 行级税分摊推导标注）

```sql
SELECT
  o.id                AS order_pk,
  o.workspace_id      AS workspace_id,
  o.external_order_id,
  o.currency,
  o.subtotal,
  o.shipping_total,
  o.discount_total,
  o.tax_total,
  o.total,
  CASE WHEN o.total > o.tax_total
       THEN ROUND(o.tax_total / (o.total - o.tax_total), 6)
       ELSE NULL END  AS tax_rate_derived,   -- 推导税率；无法推导时 NULL，不填 0
  o.received_at,
  oi.id               AS line_pk,
  oi.workspace_id     AS order_item_workspace_id,
  oi.sku, oi.quantity, oi.unit_price, oi.line_total,
  CASE
    WHEN o.subtotal - o.discount_total > 0
    THEN ROUND(o.tax_total * (oi.line_total / (o.subtotal - o.discount_total)), 2)
    ELSE NULL
  END AS line_tax_derived,                  -- 推导行级税分摊；无行级税列时不伪造
  'derived_not_stored' AS line_tax_missing_reason
FROM orders o
LEFT JOIN order_items oi ON oi.order_id = o.id AND oi.workspace_id = o.workspace_id
WHERE o.workspace_id = :workspace_id
  AND o.business_model = 'B2C'
  AND o.received_at >= :start_date
  AND o.received_at <  :end_date
  AND (:cursor IS NULL OR (o.received_at, o.id) > (:cursor, :cursor_pk))
ORDER BY o.received_at ASC, o.id ASC
LIMIT :batch_size;
```

（`missing_reason` 在 SQL 内给字面量只是标注，脱敏脚本会依据 schema 事实改写为 `not_collected`/`derived` 枚举，见 §1.4。）

### 2.3 C 组 — 成本快照多版本 + 当前成本行（R7 定量核心）

```sql
-- C-1 快照多版本（append-only，含历史全部版本）
SELECT
  s.id                AS snapshot_pk,
  s.workspace_id      AS workspace_id,
  s.product_id,
  s.variation_id, s.variation_sku,
  s.currency,
  s.purchase_cost, s.domestic_shipping, s.first_leg_shipping,
  s.last_leg_shipping, s.international_shipping, s.packaging,
  s.tax_estimate, s.handling, s.total_landed_cost,
  s.version,
  s.payment_fee, s.marketing_amortization, s.after_sales_loss, s.total_cost,
  s.weight_kg, s.source, s.valid_from, s.trace_id, s.created_at
FROM product_cost_snapshots s
WHERE s.workspace_id = :workspace_id
  AND s.valid_from >= :start_date - INTERVAL '30 days'  -- 略提前，覆盖跨窗口成本变更
  AND s.valid_from <  :end_date
  AND (:cursor IS NULL OR s.valid_from > :cursor
       OR (s.valid_from = :cursor AND s.id > :cursor_pk))
ORDER BY s.valid_from ASC, s.id ASC
LIMIT :batch_size;

-- C-2 当前成本行（订单摄取实际使用的表，R5/R7 对照）
SELECT
  c.id                AS cost_pk,
  c.workspace_id      AS workspace_id,
  c.product_id,
  c.variation_id, c.variation_sku,
  c.currency,
  c.purchase_cost, c.domestic_shipping, c.first_leg_shipping,
  c.last_leg_shipping, c.international_shipping, c.packaging,
  c.tax_estimate, c.handling, c.total_landed_cost,
  c.version,
  c.payment_fee, c.marketing_amortization, c.after_sales_loss, c.total_cost,
  c.source, c.confidence, c.valid_from,
  c.notes
FROM product_cost c
WHERE c.workspace_id = :workspace_id
  AND c.product_id IN (
    SELECT DISTINCT product_id FROM order_items oi
    WHERE oi.workspace_id = :workspace_id
      AND oi.product_id IS NOT NULL
      AND oi.order_id IN (
        SELECT o.id FROM orders o
        WHERE o.workspace_id = :workspace_id
          AND o.received_at >= :start_date AND o.received_at < :end_date
      )
  );
```

C-2 用子查询限定"时间窗内订单引用过的 product_id"，避免全表扫；**不导出与订单无关的成本行**（最小必要）。

### 2.4 D 组 — 价格 + 修改时间 + SKU（R6 追溯）

```sql
SELECT
  p.id                AS product_pk,
  p.workspace_id      AS workspace_id,
  p.sku,
  p.meta ->> 'price'          AS price_current,
  p.meta ->> 'regular_price'  AS regular_price_current,
  p.meta ->> 'sale_price'     AS sale_price_current,
  p.meta ->> 'woocommerce_id' AS wc_product_id,
  p.meta ->> 'total_sales'    AS wc_total_sales,
  p.created_at,
  p.updated_at        AS price_modified_at,   -- meta 合并写于产品更新时；无独立价格发布记录(R6 缺口)
  'LEGACY_NO_PUBLICATION_RECORD' AS price_lineage,
  m.id                AS mapping_pk,
  m.nuotao_product_id,
  m.woocommerce_id,
  m.woocommerce_variation_id,
  m.variation_sku,
  m.identity_state,
  m.last_synced_at
FROM products p
LEFT JOIN product_mappings m
       ON m.nuotao_product_id = p.id AND m.workspace_id = p.workspace_id
WHERE p.workspace_id = :workspace_id
  AND p.deleted_at IS NULL
  AND p.meta ->> 'price' IS NOT NULL              -- 只导有价格的产品
ORDER BY p.id
LIMIT :batch_size;
```

> 注：历史成交价佐证不在 D 组重复 join（避免笛卡尔放大）；A 组 `order_items.unit_price` 已带 `o.received_at`，实施时直接以 A 组批内数据作时间戳佐证。价格"当前值 + 修改时间 + SKU"满足 R6 追溯的现有能力边界（R6 缺口 = 无 `price_publication_records`，导出标 `LEGACY_NO_PUBLICATION_RECORD`，不伪造历史发布记录）。SQL 保持只读、无写操作。

### 2.5 E 组 — 支付交易 + 退款（R4）

```sql
-- E-1 订单级支付列
SELECT
  o.id                AS order_pk,
  o.workspace_id      AS workspace_id,
  o.external_order_id,
  o.payment_method, o.payment_status,
  o.currency, o.total, o.payment_fee, o.refunded_amount,
  o.received_at
FROM orders o
WHERE o.workspace_id = :workspace_id
  AND o.business_model = 'B2C'
  AND o.received_at >= :start_date AND o.received_at < :end_date
  AND o.payment_status IS NOT NULL
ORDER BY o.received_at, o.id
LIMIT :batch_size;

-- E-2 退款生命周期（含退款手续费相关列）
SELECT
  r.id                AS refund_pk,
  r.workspace_id      AS workspace_id,
  r.order_id,
  r.status, r.refund_type,
  r.requested_amount, r.approved_amount, r.executed_amount,
  r.payment_provider,
  r.payment_refund_id, r.woocommerce_refund_id,
  r.executed_at, r.retry_count, r.created_at
FROM refund_cases r
WHERE r.workspace_id = :workspace_id
  AND r.created_at >= :start_date AND r.created_at < :end_date
ORDER BY r.created_at, r.id
LIMIT :batch_size;
```

说明：固定手续费（Stripe $0.30）只存在于 `orders.payment_fee` 的估算值（R4：订单级一次）；退款是否返还手续费**无数据**（`missing_reason='refund_fee_return_not_tracked'`，脚本标注，不假设返还）。

### 2.6 F 组 — 物流（起点/终点/运输费，R3）

```sql
-- F-1 物流主记录（shipments.csv）
SELECT
  s.id                AS shipment_pk,
  s.workspace_id      AS workspace_id,
  s.purchase_order_id,
  s.b2b_order_id,
  s.carrier, s.origin, s.destination,
  s.tracking_number, s.status, s.ship_date, s.delivery_time_days,
  s.promised_delivery, s.actual_cost, s.actual_cost_currency,
  s.delay_reason, s.created_at
FROM shipment_records s
WHERE s.workspace_id = :workspace_id
  AND s.created_at >= :start_date AND s.created_at < :end_date
ORDER BY s.created_at, s.id
LIMIT :batch_size;

-- F-2 物流事件（logistics_events.csv，子记录）
SELECT
  e.id                AS event_pk,
  e.workspace_id      AS workspace_id,
  e.shipment_id,
  e.event_type, e.location, e.description, e.occurred_at
FROM logistics_events e
WHERE e.workspace_id = :workspace_id
  AND e.shipment_id IN (
    SELECT s.id FROM shipment_records s
    WHERE s.workspace_id = :workspace_id
      AND s.created_at >= :start_date AND s.created_at < :end_date
  )
ORDER BY e.occurred_at, e.id
LIMIT :batch_size;
```

> G4 workspace：F-1/F-2 均显式投影 `workspace_id`（源表 `shipment_records`/`logistics_events` 均 workspace-scoped）；`logistics_events.shipment_id → shipments.shipment_pk` 的父子一致性由脱敏脚本以 `(workspace_id, shipment_id)` 解析，不用 `shipment_id` 跨 workspace 匹配。

### 2.7 G 组 — 营销归因 + 分摊（CP 重算分量）

```sql
SELECT
  c.id                AS campaign_pk,
  c.workspace_id      AS workspace_id,
  c.platform, c.campaign_id, c.name,
  c.product_id, c.status, c.currency,
  c.budget, c.spend, c.impressions, c.clicks,
  c.conversion, c.revenue, c.roas,
  c.started_at, c.ended_at
FROM campaigns c
WHERE c.workspace_id = :workspace_id
  AND (c.started_at IS NULL OR c.started_at < :end_date)
  AND (c.ended_at IS NULL OR c.ended_at >= :start_date)
ORDER BY c.started_at, c.id
LIMIT :batch_size;

-- G-2 订单侧营销分量（广告费分摊 + 快照内营销摊销）
SELECT
  o.id                AS order_pk,
  o.workspace_id      AS workspace_id,
  o.advertising_cost,
  o.profit_snapshot ->> 'payment_fee'     AS snapshot_payment_fee,
  o.profit_snapshot ->> 'product_cost'    AS snapshot_product_cost,
  o.profit_snapshot ->> 'cost_status'     AS snapshot_cost_status,
  o.profit_snapshot ->> 'profit_confidence' AS snapshot_profit_confidence,
  o.profit_snapshot ->> 'revenue_excl_tax' AS snapshot_revenue_excl_tax,
  o.profit_snapshot ->> 'formula_version'  AS snapshot_formula_version,
  o.received_at
FROM orders o
WHERE o.workspace_id = :workspace_id
  AND o.business_model = 'B2C'
  AND o.received_at >= :start_date AND o.received_at < :end_date;
```

G 组"订单归因及分摊记录"= `orders.advertising_cost`（订单侧分摊值）+ `campaigns`（计划级 spend/revenue）；**历史逐订单营销分摊明细不存在**（`missing_reason='attribution_history_not_stored'`），脚本标注，不造数。

---

## §3 脱敏脚本设计（`scripts/v28_export_desensitize.py`，本轮只写代码 + 本地测试数据自校验，未跑真实数据）

### 3.1 输入 / 处理 / 输出

- **输入**：7 组原始导出（CSV，UTF-8，含 §2 列；批次文件合并后进入）。目录 `data/raw_export/`。
- **处理**（纯本地，无网络/DB）：
  1. 校验受限 id-map 目录（`--id-map-dir` + `--id-map-retention-days`；G3：目录必须已存在、非符号链接、不与 raw/out 嵌套或重叠、且**不在任何 Git 工作树内**；任一不满足 → exit 2，fail-closed）；
  2. 读 salt（`--salt-file`；缺失则 exit 2，fail-closed，**不写默认 salt**）；
  3. 构建稳定伪 ID 映射（§1.3），对 6 类标识逐一替换；
  4. PII 剥除：枚举键删除（`billing_*`/`shipping_*` 地址块、`display_name`、`name/first_name/last_name` 键）+ JSON 键递归 + 正则兜底（邮箱/电话/卡号/CVV/`token`/`api_key`/`cookie`/`secret`）；命中正则的字段置 `REDACTED:<reason>` 并在报告列出命中计数；
  5. 缺失处理：NULL/空保留；按 §1.4 枚举写 `missing_reason`；**0 值保留 0 并标 `value_is_zero=true`**（供"是否被填 0"校验区分）；
  6. 对齐（G4）：以 A 组 `order_pk` 为主键，校验 `orders_lines/tax/payments/order_marketing/refunds` 五个文件 `order_pk` ⊆ A（按 `(workspace_id, order_pk)` 解析，**不跨 workspace 匹配**）；C 组按 `product_id+variation_id` 索引；F/G 独立；关联/主键/workspace 校验见 §3.2 V2（workspace 检查覆盖**全部 12 个输出文件**，含 `cost_snapshots/cost_current/price_history/shipments/logistics_events/campaigns`）；
  7. **仅当 V1–V7 全通过**才把 `pseudo_map`（剔除 `_salt`/`_workspace` 元键）写入受限目录 `_id_map_pseudo.json`（O_EXCL、0600/0700、fsync）。
- **输出**：`data/desensitized/{orders,orders_lines,tax,cost_snapshots,cost_current,price_history,payments,refunds,shipments,logistics_events,campaigns,order_marketing}.csv` + `desensitization_report.json`（命中统计、缺失清单、行数、sha256 文件指纹、`id_map` 元数据：写入与否/条数/存储类别/保留期，**不含路径与原始 ID**）；映射工件仅在 `--id-map-dir/_id_map_pseudo.json`。

### 3.2 自校验（脚本内置，全部本地）

| # | 校验 | 通过标准 |
|---|---|---|
| V1 | 行数一致 | 脱敏输出行数 == 原始输入行数（逐文件比对，报告输出） |
| V2 | 关联/主键/workspace 完整性 | **G4**：① 引用完整性——`orders_lines/tax/payments/order_marketing/refunds` 五文件的 `order_pk` 必须在 `orders.csv` A 组集合中，按 `(workspace_id, order_pk)` 解析（**绝不只用 `order_pk` 跨 workspace 匹配**）；孤立行按行集记入 detail 并 FAIL，`refunds` 用 `refund_pk` 采样保留既有行为；② 主键完整性——`orders/orders_lines/refunds/cost_snapshots/price_history/shipments/logistics_events/campaigns` 的代理主键列必须存在、非空、不重复；③ workspace 一致性——**全部 12 个实际输出文件**均须有 `workspace_id` 且每行非空、等于 CLI `--workspace-id`；父子记录（orders↔五关联文件、shipments↔logistics_events）以 `(workspace_id, 关联键)` 校验一致；同一 `order_pk` 出现于多个 workspace（跨 workspace 同键）→ 记 `cross_workspace_keys` 并 FAIL；缺 `workspace_id` 列的文件：源 schema 有该字段 → FAIL（`missing_workspace_columns`，schema-contract 违约），源 schema 明确无该字段 → `STRUCTURAL_ASSOCIATION_LIMITS`（如实记录，不伪造）；缺关联列/主键列 → 记 `missing_required_association_fields` + `structural_limitations`（**明确标记，绝不静默跳过，绝不伪造 FK**）；schema 无 FK（shipments/logistics_events/campaigns→orders）或无可信关联字段（tax/payments/order_marketing 无代理主键）→ 如实记录为结构限制 |
| V3 | 无 PII 残留 | 正则扫全量输出：邮箱 ≥1 次、电话模式、Luhn 卡号、`token/api_key/cookie/cvv/secret` 键值 → 命中即 **FAIL**（exit 1） |
| V4 | 缺失未填 0 | 原始 NULL 字段在输出中必须为 NULL/空且带 `missing_reason`；原始 0 字段保留 0；反向：输出中出现 `missing_reason != null` 但值=0 的行 → FAIL |
| V5 | 伪 ID 稳定 | 同一原始 ID 两次独立调用映射出同一伪 ID（脚本内自测，用固定测试 salt 演示，不写真实 salt） |
| V6 | 金额/币种/时间保留 | 抽 10% 行比对原始金额/币种/时间戳逐字节一致（脱敏不得动业务数值） |
| V7 | 文件指纹 | 每文件 sha256 写入报告，供 Owner 复核交付物完整性 |

### 3.3 安全

- 脚本与测试数据全部可入仓（**测试数据为合成**，`tests/fixtures/v28_export_sample/`，与生产无关）；
- salt 文件、原始导出 **gitignore 且不出目录**；**G3**：`_id_map_pseudo.json` **只写 Owner 受限目录**（`--id-map-dir`，仓库外），并额外在 `.gitignore` 加 `_id_map_pseudo.json` 兜底模式（即使误配到工作树内也**不可能被 Git 跟踪**）；`.gitleaks` 规则兜底扫描 `salt`/凭据模式（仓库已有 gitleaks 配置）。
- **G4 结构限制**：`tax/payments/order_marketing` 无独立代理主键、`shipments/logistics_events/campaigns`→`orders` 无 FK、`order_items.cost_snapshot_id` schema 无——均按**结构限制**如实记录，不伪造关联键、不伪造 FK。

---

## §4 数据完整性验证测试设计（本地脱敏副本上跑，不连生产）

> 实现：`tests/test_v28_export_desensitize.py` + `tests/test_v28_recalc_quantification.py`（本地用 §3 脚本对合成样例数据跑全链路；定量算法在 `scripts/v28_recalc_quantify.py`）。

### 4.1 关联键对齐率（6 链）

- 订单→成本：`order_items.(product_id, wc_variation_id)` 能否命中 C 组同一 key 的某版本快照（含 `variation_id IS NULL` 商品级回退）；
- 订单→价格：`order_items.sku` 命中 D 组 `sku`；
- 订单→退款：`refund_cases.order_id` ⊆ 订单；
- 订单→物流：以 `orders.shipping_total` 与成本快照 `last_leg_shipping` 对齐（schema 无订单-shipment FK，如实报告"对齐=成本侧对齐"，不算断链）；
- 订单→营销：`order_pk` 有 `advertising_cost` 即归因存在，金额 0 且 campaigns 时间窗内无 spend 即"无归因"（两态，不混）；
- 输出：每链对齐率 %、未对齐 key 清单（前 50 条样例）。

### 4.2 缺失字段清单（按表×字段，带缺失原因分类）

枚举 R 系列缺口字段在时间窗内的 NULL 分布：`order_items.cost_snapshot_id/cost_snapshot_version`（schema 无 → 100% 缺失，`field_not_stored`）、`pricing_rule_version`、`pricing_engine_version`、`evidence_grade`、行级税、退款手续费返还、营销历史分摊、价格发布记录——输出 `table.field → (null_count, missing_reason)` 矩阵。

### 4.3 历史重算定量（三态 + 缺失原因）

订单级判定（`tests/test_v28_recalc_quantification.py` 核心断言，Owner 要求最终给出**精确数字**，本轮以"算法 + 合成样例验证"交付，生产数字待 Owner 授权导出后跑）：

- **精确可重算** = 订单行全部命中 C 组快照版本（`product_id+variation_id` 在 `received_at` 时点有 `valid_from ≤ received_at` 的快照）AND 税/费/退款/营销分量齐（B/E/G 组非 NULL）AND 成本 `source` 非 NULL；
- **部分可重算** = 命中成本快照但缺 1..n 个分量（列明缺哪个）；
- **不可重算** = 缺关键字段：`cost_snapshot_id/version`（R7，当前 schema 全缺 → 全部订单行在此字段 100% 缺失，定量结果预期为"0 精确 / N 部分 / M 不可重算"，**其中不可重算主因 = LEGACY_UNKNOWN 成本版本**）；
- 每类输出：订单数、行数、缺失原因 Top-N（`field_not_stored` / `not_collected` / `legacy_no_record` 计数）。

### 4.4 R1 历史收入虚增定量

对脱敏副本逐单：`inflated = total − (total − tax_total) = tax_total`（旧口径 revenue=含税 total）；`net = total − tax_total`；聚合：

- 虚增总额 `Σ tax_total`、净收入 `Σ net`、比例 `Σ tax_total / Σ net`（按币种分组，USD 与其余分别给；混合币种先按 `exchange_rates` 表换算（本组 SQL 可选补导汇率窗内行，Owner 审时定）；
- 按日/周曲线，验证 3A 修复前后口径差 = 该数（3A 实测样例 8.00/95.00=8.42% 的"历史全量版"）。

### 4.5 R2 历史 CP 口径差异

对同一脱敏副本跑两套：
- 旧口径（`cost_prefill_service` 语义）：CM 含营销摊销+售后、GM 扣支付费；
- 统一口径（`contribution_margin_service`，`FORMULA_VERSION=v28-pricing-3a`）：GM=(NetMerchRevenue−COGS)/NetMerchRevenue，CP=NetRevenue−COGS−Payment−Fulfillment−Marketing−AfterSales−Refund(一次)，CPMargin=CP/NetRevenue；
- 输出：逐单两套 CP 差值分布（abs/pct）、口径差 = 营销摊销+售后摊销（与 Phase 2 实测 10.06 同构）、`metric_version` 标注（历史行标 `LEGACY_COST_PREFILL`，新算标 `v28-pricing-3a`），**不得把 LEGACY 数字报成统一口径**。

### 4.6 R7 历史成本版本缺失定量

- `order_items` 中 `cost_snapshot_id IS NULL` 行数 / 总行数（当前 schema 预期 100%）；
- 能反查快照版本但无法证明"订单当时用的就是该版本"的行 → 标 `LEGACY_UNKNOWN`（禁止用当前 `product_cost` 数值静默补齐——R5/R7 红线）；
- 输出：可版本化行数、LEGACY_UNKNOWN 行数、每类原因。

### 4.7 测试矩阵（合成样例，本地跑）

| 用例 | 输入 | 断言 |
|---|---|---|
| T1 全量齐 | 完整 7 组样例 | 三态判定=精确可重算；R1 比例=样例税/净额 |
| T2 缺成本版本 | 订单行无 `cost_snapshot_id` 列值 | 不可重算计数+1，原因=`field_not_stored` |
| T3 缺营销分摊 | `advertising_cost` NULL | 部分可重算，原因=`not_collected:advertising` |
| T4 PII 注入 | 样例混入邮箱/卡号/地址 | V3 FAIL（脚本 exit 1） |
| T5 填 0 注入 | NULL 被填 0 的样例 | V4 FAIL |
| T6 伪 ID 稳定 | 同输入两次 | 映射一致（V5） |
| T7 行数不一致 | 删 1 行 | V1 FAIL |
| T8 对齐断裂 | refund.order_id 不在 A | V2 报告孤立行 |

本地运行：`pytest tests/test_v28_export_desensitize.py tests/test_v28_recalc_quantification.py -q`（合成数据，无生产/无 DB 连接；若跑真实样例由 Owner 授权后执行）。

---

## §5 执行流程（本轮止步于 ①）

| 步 | 谁 | 做什么 | 门禁 |
|---|---|---|---|
| ① | DSH（本工作项） | 起草方案 + 脚本 + 本地自校验（已完成，本文档 + `scripts/` + `tests/`） | 脚本在合成数据上 7/7 自校验通过；13/13 单测全绿（仅合成 fixture，无生产数据） |
| ② | **Owner 审查** | 审 §1 字段范围/脱敏规则、§2 SQL 只读性、salt 交付方式、批次大小与时间窗（先 30 天） | Owner 书面批准 + 提供 salt（安全渠道，不入库） |
| ③ | **有权限人员（生产 DBA）** | 在生产**只读**执行 §2 SQL（COPY TO CSV），产物交 DSH；全程无 DDL/DML、无应用改动 | 执行记录（时间/行数/文件 sha256）回传 |
| ④ | DSH 本地 | `scripts/v28_export_desensitize.py` 脱敏（V1–V7 自校验全绿才产出 `data/desensitized/`） | V1–V7 任一 FAIL 即停 |
| ⑤ | DSH 本地 | §4 验证 + 历史重算定量报告（精确/部分/不可重算数量、缺失原因、R1 金额与比例、R2 口径差、R7 LEGACY_UNKNOWN 分布） | 报告交 Owner |
| ⑥ | **Owner** | 终审：数字验收、是否扩大时间窗（30→90 天）、R1 历史幅度结论 | Owner 单独宣布 V2.8 相关项通过 |

---

## §6 合规声明

- 本轮**未连接生产数据库**；**未执行任何 SQL**（§2 SQL 仅起草）；**未运行脱敏/验证脚本对真实数据**（脚本仅在 `tests/fixtures/v28_export_sample/` 合成数据上自校验）；
- **未使用生产凭据**；未连 WooCommerce/Stripe；未写 WC 商品/价格/库存；未部署；未切换定价引擎；
- **salt 未入库**：脚本无 salt 默认值，缺 salt fail-closed；Owner 提供前映射表无法生成；测试仅用合成 fixture 内的 test-only salt（`v28-test-only-salt-do-not-use-in-prod`，标注仅测试用）；
- **0076 未触碰**（未提交/未读 diff/未清理）；未碰 3A/3B/3C/3D 文件（本工作项仅新增 `docs/V2_8_HISTORICAL_DATA_EXPORT_PLAN.md`、`scripts/v28_export_desensitize.py`、`scripts/v28_recalc_quantify.py`、`tests/test_v28_export_desensitize.py`、`tests/test_v28_recalc_quantification.py` 及合成 fixtures）；
- 缺失字段**未用 0/当前数据补齐**；历史成本版本缺失一律标 `LEGACY_UNKNOWN`；
- **未宣布 V2.8 通过**；状态 = READY FOR REVIEW，交 Owner 审查。
