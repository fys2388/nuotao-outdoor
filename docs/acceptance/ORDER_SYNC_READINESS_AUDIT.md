# 订单同步准备度审计报告

| 元信息 | 值 |
|---|---|
| 任务编号 | **D8-A2** 交付物 |
| 报告名称 | ORDER_SYNC_READINESS_AUDIT（订单同步准备度审计） |
| 审计日期 | 2026-11-19 |
| 端到端状态 | **PENDING_REAL_ORDER**（待真实订单） |
| 审计方式 | 只读代码审查（read/grep 工具），未修改任何代码 |
| 审核人要求 | 每项必须标记 `VERIFIED_BY_CODE` / `VERIFIED_BY_TEST` / `NOT_VERIFIED` / `BLOCKED`，不得把未验证说成已验证 |
| 审计范围 | WooCommerce 订单进入 AI OS 的代码路径（API → webhook → sync → 落库） |

> **重要说明**：WooCommerce 当前 `orders=0`，**无法做端到端实测**。本报告所有结论均为**代码层面审查**，状态标记一律为 `VERIFIED_BY_CODE`（代码可读、逻辑存在）或 `NOT_VERIFIED`（无真实订单无法实测）。**无任何一项达到 `VERIFIED_BY_TEST`**，因缺真实订单。此诚实标注是本审计的核心约束。

---

## 1. 执行摘要

Nuotao AI OS 对 WooCommerce 订单的摄取代码路径**架构成熟度较高**，存在**三条并行的订单摄取通道**，均以 `(workspace_id, source, external_order_id)` 幂等键为基础：

1. **Webhook 通道**（推荐，实时）：`/webhooks/woocommerce` → HMAC-SHA256 验签 → `order_service.ingest_order()` 幂等落库 + 利润引擎 + 规则引擎 + 事件审计。这是**最完整**的通道，含利润快照、规则检查、`order.created` 审计事件。
2. **批量拉取通道**：`POST /orders/sync-woocommerce` → `sync_orders_to_db()` → 按 `external_order_id` upsert，含客户身份解析与归因（attribution）。
3. **Connector 通道**（M4.3，只读）：`WooCommerceConnector.sync()` → `order_service.ingest_order()` 复用 webhook 同款幂等逻辑，全链路 `trace_id`。

**核心结论**：订单摄取代码**设计为幂等、可审计、带 trace 传播**，webhook 验签采用常数时间比较（防时序攻击），并发竞态有 `IntegrityError` 兜底。**代码准备度可评为 READY_PENDING_E2E**。

**主要缺口**（诚实标注）：
- **无任何端到端实测**（orders=0），所有"幂等生效""验签通过""字段正确落库"均为 `VERIFIED_BY_CODE`，非 `VERIFIED_BY_TEST`。
- 批量通道 `sync_orders_to_db` **未传递 trace_id** 到 Order 行（`trace_id=None` 硬编码在客户身份解析处），trace 传播在该通道存在断点。
- 批量通道**不写 `order.created` 审计事件**（仅 webhook 通道写），两条通道审计粒度不一致。
- 认证凭据有 `dev-webhook-secret-change-me` 默认值，生产未强制校验。

---

## 2. 逐维度审计表

| # | 审计维度 | 状态标记 | 证据（文件:行号 + 代码片段） | 结论 |
|---|---|---|---|---|
| 1 | **API 连接与认证** | `VERIFIED_BY_CODE` | `woocommerce_sync_service.py:106-114` `requests.get(url, auth=_get_wc_auth(), ..., timeout=30)` + `response.raise_for_status()`；`:130-137` `except RequestException` 返回 `success:False`；`integrations/woocommerce.py:343-358` `httpx.AsyncClient(timeout=timeout)` + `ConnectorError` | consumer key Basic 认证（`auth=(key, secret)`）；超时 30s；错误捕获为 `RequestException`/`ConnectorError`，不暴露原始堆栈。**但无重试逻辑**（见维度 8）。代码确认，未实测。 |
| 1b | 认证凭据配置 | `VERIFIED_BY_CODE`（含风险） | `config.py:52-54` `woocommerce_base_url/consumer_key/consumer_secret` 默认空；`config.py:76` `woocommerce_webhook_secret: str = "dev-webhook-secret-change-me"` | 凭据从 settings/.env 读取。webhook secret 有**不安全默认值**，生产若未覆盖则验签形同虚设。需生产强制非默认值（见风险 R4）。 |
| 2 | **订单读取（分页/状态/字段）** | `VERIFIED_BY_CODE` | `woocommerce_sync_service.py:75-129` `fetch_woocommerce_orders(per_page, page, status="any", date_after, date_before)`；`:97` `per_page=min(per_page,100)`；`:117-118` 读 `X-WP-TotalPages`/`X-WP-Total`；`:311-331` while 循环翻页直到 `total_pages` | 分页完整（读 WP 头翻页 + `max_orders` 上限）；状态过滤 `any/pending/...`；`date_after/before` 时间窗。字段映射见维度 7。代码确认，未实测真实分页。 |
| 2b | 单订单读取 | `VERIFIED_BY_CODE` | `:140-185` `fetch_woocommerce_order_by_id`，`:166-172` 404 返回 `success:False, order:None` | 按 ID 取单订单，404 单独处理。供 webhook 补偿拉取用。代码确认，未实测。 |
| 3 | **订单落库幂等性** | `VERIFIED_BY_CODE` | DB 约束 `models/order.py:74-81` `UniqueConstraint("workspace_id","source","external_order_id", name="uq_orders_workspace_source_external")`；`order_sync_service.py:141-150` 查 `external_order_id` 决定 insert/update；`:184-217` `except IntegrityError` 回滚转 update（并发竞态兜底） | **三层幂等**：(a) DB 唯一约束为最终防线；(b) 先查后决定 insert/update；(c) `IntegrityError` 捕获并发冲突。重复同步**不会重复建单**。代码确认，未实测重复投递。 |
| 3b | webhook 幂等（ingest_order） | `VERIFIED_BY_CODE` | `order_service.py:220-239` 先查 `_find_order`，存在则返回 `status="duplicate"`；`:361-386` `commit` 捕获 `IntegrityError` 并发兜底返回 duplicate | webhook 重复投递返回 `duplicate`（HTTP 200），新建返回 `created`（HTTP 201）。幂等设计正确。代码确认，未实测。 |
| 4 | **Webhook 验签（HMAC-SHA256）** | `VERIFIED_BY_CODE` | `webhooks.py:56-59` `_compute_signature` `hmac.new(secret, body, sha256)` + base64；`:62-70` `_verify_signature` 用 `hmac.compare_digest` 比较 base64 或 legacy hex（**常数时间，防时序攻击**）；`:109-114` 验签失败返回 401 | 验签算法正确，常数时间比较。支持 WooCommerce 标准 base64 与 legacy hex 双格式。**未用真实 webhook 投递实测**。 |
| 4b | webhook 非法输入防护 | `VERIFIED_BY_CODE` | `webhooks.py:87-101` 空体/非法 JSON/非 dict 返回 400；`:102-106` 支付网关注册 topic（`woocommerce.payments.gateways`）返回 404；`:116-123` Pydantic 校验失败返回 400 | 完整的输入防护链：空体→400、坏 JSON→400、网关 topic→404、schema 不符→400。代码确认。 |
| 5 | **trace_id 传播** | `VERIFIED_BY_CODE`（webhook/connector 通道）+ `NOT_VERIFIED`（批量通道断点） | 中间件 `main.py:255-256` 每请求 `set_trace_id(header or new_trace_id())`；`tracing.py:38-43` `TraceIdFilter` 注入日志；webhook 链路 `webhooks.py:85` `trace_id=get_trace_id()` → `ingest_order(trace_id)` → `order_service.py:345` `Order(trace_id=trace_id)` + `:389-403` event 带 trace_id；connector `woocommerce.py:187-232` 全程传 `trace_id` | **webhook 与 connector 通道**：trace_id 从请求头/中间件 → webhook → ingest → Order 行 + event_log + 日志，**全链路贯穿**。**批量通道断点**：`sync_orders_to_db`（`woocommerce_sync_service.py:957-970`）调用 `ensure_account_for_identity(trace_id=None)` 且 Order 构造（:991-1009）**未写 trace_id 字段**。见风险 R2。 |
| 6 | **event_service / event_log 审计** | `VERIFIED_BY_CODE`（webhook 通道）+ `NOT_VERIFIED`（批量通道无审计事件） | `order_service.py:389-403` `event_service.create_event(event_type="order.created", entity_type="order", payload={external_order_id,total,currency,profit,rules}, trace_id)`；`:276,299` 客户身份解析传 `external_system="woocommerce"`；`customer_identity_service` 写 `external_system` 审计；`woocommerce.py:269-296` 产品同步写 `product.created/updated` 事件 | **webhook 通道**：每单写 `order.created` 审计事件（含利润快照+规则结果），客户身份解析带 `external_system="woocommerce"`。**批量通道 `sync_orders_to_db` 不写 `order.created` 事件**（只调 `consolidation_service.ensure_attribution`），两条通道审计粒度不一致。见风险 R3。 |
| 7 | **字段映射完整性** | `VERIFIED_BY_CODE` | 见下方"字段映射对照表"；`woocommerce_sync_service.py:223-286` `convert_wc_order_to_internal`；`order_sync_service.py:155-174,251-262` Order/OrderItem 构造；`order_service.py:326-358` webhook Order/OrderItem 构造 | WC order → AI OS Order 字段映射覆盖：ID、金额（subtotal/shipping/discount/tax/total，全 Decimal）、币种、SKU、状态、客户（非 PII，仅 country + 身份 hash/account）。**客户姓名/邮箱/地址不落库**（PII 策略，`models/order.py:26-28`）。代码确认。 |
| 8 | **错误处理与重试** | `VERIFIED_BY_CODE`（错误处理）+ `NOT_VERIFIED`（主动重试缺失） | 错误处理：`webhooks.py:12-14` 文档声明 5xx 触发 WooCommerce 指数退避重试，幂等保证重试安全；`:132-137` `OrderIngestError`→500。**主动重试**：`woocommerce_sync_service.py` 所有 `requests.get` 均**单次调用，无 retry/backoff** | **错误处理**：webhook 失败返回 5xx 让 WooCommerce 重试（依赖对方重试 + 幂等护栏），设计合理。**但 AI OS 主动拉取侧无重试/熔断**——`AGENTS.md` §2.4 要求"所有外部调用必须有超时、重试、熔断与降级"，批量拉取仅有超时，缺重试与熔断。见风险 R1。 |
| 9 | **商品同步（辅助）** | `VERIFIED_BY_CODE` | `woocommerce_sync_service.py:597-837` `sync_products_to_db` upsert by workspace+sku（`:652-660`）；`:526-594` `_upsert_inventory_snapshot` 按 (workspace,product,location) upsert；`:718-781` 状态漂移写 `product.wc_status_drift`/`product.wc_unauthorized_publish` 事件；`integrations/woocommerce.py:240-297` Connector 产品 upsert + 事件 | 商品同步幂等（SKU 唯一），库存快照单独落表（供 agent 低库存判断），状态漂移有审计事件。订单项需商品主数据匹配成本（`order_service.py:82-128` 按 SKU 取落地成本）。代码确认，未实测。 |
| 10 | **端到端状态** | `PENDING_REAL_ORDER` | WooCommerce `orders=0`，无真实订单可走通 webhook→落库→查询全链路 | **端到端验证阻塞于缺真实订单**。代码路径齐备，但"真实订单能否稳定、正确、幂等进入 OS"**无法证明**，须待首笔真实订单产生后回补 `VERIFIED_BY_TEST`。 |

---

## 3. 字段映射对照表（WC order → AI OS Order）

映射依据：`order_service.py:326-358`（webhook 通道，最完整）、`order_sync_service.py:155-262`（批量/幂等通道）、`models/order.py:33-72`（Order 模型）、`woocommerce_sync_service.py:223-286`（转换函数）。

| WooCommerce 字段 | AI OS Order 字段 | 类型/处理 | 备注 |
|---|---|---|---|
| `id` | `external_order_id` | `String(64)`，幂等键 | 唯一约束 `(workspace, source, external_order_id)` |
| `number` | `meta.order_number`（profit_snapshot） | JSON | 批量通道存 meta；webhook 通道不单独存 |
| `status` | `status` + `payment_status` + `fulfillment_status` | 状态机映射 | 见下方状态映射表 |
| `currency` | `currency` | `String(8)`，默认 USD | — |
| `total` | `total` | `Numeric(12,2)` Decimal | — |
| `subtotal` | `subtotal` | `Numeric(12,2)` | — |
| `shipping_total` | `shipping_total` | `Numeric(12,2)` | — |
| `discount_total` | `discount_total` | `Numeric(12,2)` | — |
| `total_tax` | `tax_total` | `Numeric(12,2)` | — |
| `refunds[].total` | `refunded_amount` | Decimal 求和 | `order_sync_service.py:110-112` |
| （派生） | `payment_fee` | Decimal | `settings.payment_fee_rate/fixed` 估算，`order_service.py:131-135` |
| `payment_method` / `payment_method_title` | `payment_method` / `meta.payment_method_title` | String | — |
| `shipping.country` 或 `billing.country` | `country` | `String(8)` | 非敏感，可存 |
| `billing.email` | → `customer_account_id`（经 `ensure_account_for_identity`） | UUID FK | **邮箱明文不落 Order**，解析为统一账户 ID（`order_service.py:267-289`） |
| `billing.phone` | → `customer_account_id`（补充身份） | UUID FK | **电话明文不落 Order**（`order_service.py:291-313`） |
| `billing.first_name/last_name/...` | **不落库** | — | PII 策略，`models/order.py:26-28` |
| `shipping.address_1/city/...` | **不落库** | — | PII 策略 |
| `line_items[].id` | `OrderItem.external_item_id` | String | — |
| `line_items[].sku` | `OrderItem.sku` | String | 供成本匹配 `order_service.py:82-128` |
| `line_items[].name` | `OrderItem.name` | String | — |
| `line_items[].quantity` | `OrderItem.quantity` | Integer | — |
| `line_items[].price` / `total` | `OrderItem.unit_price` / `line_total` | Numeric(12,2) | webhook 通道 `unit_price = total/quantity`（`order_service.py:354`） |
| `date_created/date_paid` | （支付状态推断） | — | `_map_payment_status`（`order_sync_service.py:55-67`） |
| （派生） | `profit_snapshot` / `rule_results` | JSON | 利润引擎 + 规则引擎输出，可审计（`order_service.py:315-344`） |
| （派生） | `trace_id` | String(64) | webhook/connector 通道写入；批量通道未写（R2） |

**状态映射表**（`order_sync_service.py:40-78`、`woocommerce_sync_service.py:922-932`）：

| WC status | AI OS status | payment_status | fulfillment_status |
|---|---|---|---|
| pending | pending | pending | — |
| processing | processing | paid | processing |
| on-hold | on_hold | — | processing |
| completed | completed | paid | fulfilled |
| cancelled | cancelled | — | cancelled |
| refunded | refunded | refunded | — |
| failed | failed | failed | — |
| trash | trash | — | — |

---

## 4. 幂等性分析

幂等是 ChatGPT 审核的核心关注点（"稳定、正确、幂等地进入 AI OS"）。逐通道分析：

### 4.1 幂等键
- **统一幂等键**：`(workspace_id, source, external_order_id)`，由 DB 唯一约束 `uq_orders_workspace_source_external` 兜底（`models/order.py:74-81`）。
- `source` 固定为 `"woocommerce"`，`external_order_id` 为 WC `id`。

### 4.2 三通道幂等机制

| 通道 | 入口 | 幂等实现 | 并发竞态处理 |
|---|---|---|---|
| Webhook | `/webhooks/woocommerce` → `ingest_order` | 先查 `_find_order`（`order_service.py:220-239`），存在返回 `duplicate` | `commit` 捕获 `IntegrityError` 转查并返回 `duplicate`（`:361-386`） |
| Connector | `WooCommerceConnector._sync_order` → `ingest_order` | 复用 `ingest_order` 同款逻辑 | 同 webhook |
| 批量拉取 | `/orders/sync-woocommerce` → `sync_orders_to_db` | 先查 `external_order_id`（`order_sync_service.py:141-150` / `woocommerce_sync_service.py:911-919`）决定 insert/update | `IntegrityError` 回滚转 update（`order_sync_service.py:184-217`） |

### 4.3 幂等性评估
- **重复投递不重复建单**：三层防护（先查 + 唯一约束 + IntegrityError 兜底）。**代码层面确认正确**（`VERIFIED_BY_CODE`）。
- **订单项（OrderItem）同步**：webhook/connector 通道新建时一次性插入；`order_sync_service` 更新时**先删旧项再插新项**（`order_sync_service.py:244-262`），避免订单项重复累积。设计正确。
- **未实测**：因 orders=0，"重复投递同一订单返回 duplicate 而非二次建单"**未做真实验证**（`NOT_VERIFIED` for E2E）。代码逻辑存在且正确，但缺 `VERIFIED_BY_TEST`。

---

## 5. 风险与待验证项

### 5.1 风险（代码审查发现）

| ID | 风险 | 严重度 | 证据 | 建议 |
|---|---|---|---|---|
| R1 | **主动拉取无重试/熔断**：`fetch_woocommerce_orders/products` 单次 `requests.get`，无 retry/backoff/熔断，违反 AGENTS.md §2.4"外部调用必须有重试、熔断、降级" | 中 | `woocommerce_sync_service.py:106-114,206-208` | 引入 `tenacity`/`urllib3.Retry` 做指数退避重试 + 熔断器 |
| R2 | **批量通道 trace_id 断点**：`sync_orders_to_db` 未把 trace_id 写入 Order 行，客户身份解析传 `trace_id=None` | 中 | `woocommerce_sync_service.py:957-970(trace_id=None)`, `:991-1009(Order 无 trace_id)` | 给 `sync_orders_to_db` 增加 trace_id 参数并透传到 Order 行 |
| R3 | **批量通道无 order.created 审计事件**：仅调 `ensure_attribution`，不写 event_log，与 webhook 通道审计粒度不一致 | 中 | `woocommerce_sync_service.py:1055-1073`（无 `create_event`）vs `order_service.py:389-403`（webhook 写事件） | 批量通道对新建订单补写 `order.created` 审计事件，统一审计口径 |
| R4 | **webhook secret 不安全默认值**：`dev-webhook-secret-change-me`，生产未强制覆盖则验签形同虚设 | 高（生产） | `config.py:76` | 生产环境启动时校验 secret ≠ 默认值，否则拒绝启动 |
| R5 | **三通道并存一致性**：webhook（ingest_order，最全）、批量（sync_orders_to_db，无审计事件/无 trace）、connector（复用 ingest_order）三条路径对同一订单行为不完全一致 | 中 | 见维度 6/5 | 长期收敛到单一摄取内核（ingest_order），批量/connector 复用，避免行为分叉 |
| R6 | **占位函数未实现**：`get_woocommerce_order`/`update_order_tracking` 等返回空/未实现 | 低 | `integrations/woocommerce.py:365-377` | 标注 TODO(tech-debt)，订单物流追踪待实现 |

### 5.2 待验证项（PENDING_REAL_ORDER / NOT_VERIFIED）

| 项 | 当前状态 | 解除条件 |
|---|---|---|
| 端到端订单摄取（webhook→落库→查询） | `PENDING_REAL_ORDER` | WooCommerce 产生首笔真实订单后实测 |
| HMAC 验签真实投递通过 | `NOT_VERIFIED`（仅代码确认） | 配置真实 webhook secret 并用 WC 测试投递 |
| 重复投递幂等（返回 duplicate） | `NOT_VERIFIED`（仅代码确认） | 同一订单重复投递实测 |
| 字段正确落库（金额/SKU/币种） | `NOT_VERIFIED`（仅代码确认） | 真实订单落库后核对 DB |
| 分页拉取真实订单 | `NOT_VERIFIED`（仅代码确认） | 订单数 >1 页时实测翻页 |
| 利润引擎 + 规则引擎真实计算 | `NOT_VERIFIED`（仅代码确认） | 真实订单触发 ingest 实测 |
| trace_id 全链路贯穿（批量通道） | `NOT_VERIFIED`（代码发现断点 R2） | 修复 R2 后实测 |

> **诚实声明**：本审计**无任何 `VERIFIED_BY_TEST` 项**。所有"正确/幂等/完整"结论均为代码可读性层面的确认（`VERIFIED_BY_CODE`），真实订单场景下的实际行为未经实测。

---

## 6. 结论

**订单同步代码准备度：`READY_PENDING_E2E`**（代码就绪，待端到端验证）。

- **成熟度**：订单摄取代码架构成熟——统一幂等键 + DB 唯一约束 + 并发竞态兜底；webhook 通道最完整（HMAC 验签 + 幂等 + 利润引擎 + 规则引擎 + 审计事件 + trace 全链路）；字段映射覆盖 ID/金额/币种/SKU/状态/客户且遵循 PII 最小化（姓名邮箱地址不落库）。
- **阻塞项**：**端到端验证 `PENDING_REAL_ORDER`**——WooCommerce orders=0，无法证明"真实订单能稳定、正确、幂等进入 AI OS"。这是本轮无法逾越的硬阻塞。
- **代码层待修项**（不阻塞代码就绪判定，但建议在真实订单前处理）：R4（生产 secret 强制非默认值，高优先）、R1（拉取重试/熔断）、R2（批量通道 trace 断点）、R3（批量通道审计事件）、R5（三通道行为收敛）。
- **下一步**：待 WooCommerce 产生首笔真实订单后，执行端到端实测（webhook 投递 → 落库核对 → 重复投递幂等 → 字段校验 → trace 贯穿），将本报告相关项从 `PENDING_REAL_ORDER`/`NOT_VERIFIED` 升级为 `VERIFIED_BY_TEST`，方可判定为完全就绪。

---

*本报告为只读代码审计，未修改任何代码。所有结论严格区分 `VERIFIED_BY_CODE`（代码审查确认）与 `NOT_VERIFIED`/`PENDING_REAL_ORDER`（未验证/待真实订单），未将未验证项表述为已验证。*
