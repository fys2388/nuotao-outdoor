# WooCommerce 下架 · 回收站 · 彻底删除 设计

> **版本**: v2.0
> **最后更新**: 2026-10-03
> **状态**: Active
> **关联文档**: `PRODUCT_LIFECYCLE_WORKFLOW.md`、`woocommerce_setup_guide.md`、`AGENTS.md`

---

## 1. 背景与问题

### 1.1 现象

在系统前端删除商品后，WooCommerce 店铺中的对应商品**不受任何影响**，仍处于 `publish` 状态、前台可见、可被下单。

### 1.2 根因（已核实的代码事实）

前端删除走的是本地软删除，链路中没有任何一步调用 WooCommerce：

| 环节 | 位置 | 行为 |
|---|---|---|
| 前端单个删除 | `frontend/src/pages/OperationsPages.tsx:314` | `deleteOne()` 弹确认框 |
| 前端批量删除 | `frontend/src/pages/OperationsPages.tsx:337` | `batchDelete()` |
| API 客户端 | `frontend/src/api/client.ts:434` | `DELETE /products/{id}`、`POST /products/batch-delete` |
| 后端端点 | `backend/app/api/v1/endpoints/products.py` | 转调服务层 |
| 服务层 | `backend/app/services/product_service.py:362` | `soft_delete_products()`：仅打 `deleted_at` + 写 `product.deleted` 审计事件 |

全库检索 `product.deleted` 事件的消费方，**没有任何一处会调用 WooCommerce**。WC 侧的删除语义仅存在于反向 Webhook（`backend/app/api/v1/endpoints/webhooks.py:145`），方向是 `WC → 本地`。

### 1.3 功能缺口

现行生命周期（`PRODUCT_LIFECYCLE_WORKFLOW.md`）从 `candidate` 到终态 `wc_published`，**只有"发布"没有"下架"**，也**没有可恢复的中间态**。删除是"一步到位且不联动渠道"的。

---

## 2. 目标模型：三层生命周期

```
   商品在售                                    可恢复
  ┌──────────┐   下架    ┌──────────┐   恢复    ┌──────────┐
  │  在售中   │ ────────► │  回收站   │ ────────► │  在售中   │
  │  active  │           │ 已下架    │           │  active  │
  │ WC:publish│          │ WC: trash │           │WC:publish│
  └──────────┘           └─────┬────┘           └──────────┘
                               │ 彻底删除（不可逆）
                               ▼
                         ┌──────────┐
                         │ 永久删除  │
                         │ 本地: 硬删 │
                         │ WC: force │
                         └──────────┘
```

| 操作 | 本地数据库 | WooCommerce | 可逆性 |
|---|---|---|---|
| **下架（移入回收站）** | `deleted_at = now()` | `status = trash` | 可恢复 |
| **恢复** | `deleted_at = NULL` | `status = publish`（原为 active）或 `draft` | — |
| **彻底删除** | **硬删除** `products` 行 | `DELETE /products/{id}?force=true` | **不可逆** |

### 2.1 为什么用 WC 的 `trash`

WooCommerce 原生就有回收站（`status = trash`），后台可一键恢复，语义与"下架待定"完全一致，比自造 `draft` 更贴合且运营可直接在 WC 后台操作。

**已知代价（必须告知运营）**：WordPress 默认约 **30 天**后自动清空回收站。超过该期限未恢复的 WC 商品会被 WordPress 自动永久删除，届时系统的"恢复"会失败。因此恢复窗口实际受 WordPress 配置限制。

### 2.2 本地"回收站"复用 `deleted_at`

不新增状态值：`deleted_at IS NULL` = 正常，`deleted_at` 有值 = 在回收站。这与既有软删除机制、既有唯一索引 `uq_products_workspace_sku ... WHERE deleted_at IS NULL` 完全兼容——商品进回收站后，同 SKU 可以重新建档，不会冲突。

---

## 3. 关键设计决策

### 3.1 下架/恢复不经过 V3.0 选品闸门

上架通道（`listing_publish.py`）执行 V3.0 闸门与 Listing Approved 闸门，`blocked` 硬阻断、`needs_review` 需 `force` 放行。

**下架与恢复绝不能走这两个闸门。** 闸门的目的是阻止不合格商品上架；下架是降低风险的方向。现实场景：某商品已上架，之后运营改成本导致闸门变为 `needs_review`，甚至英文文案被撤回变为 `blocked`——若下架也走闸门，就会出现**「想下架却下架不了、商品继续在售」**，这是比错误上架更危险的失效模式。

### 3.2 全部走 WC REST API，不碰 WC 数据库

`AGENTS.md` §1.4 明确「WooCommerce（自托管，通过 REST/Webhook 集成，禁止直接改其数据库）」。本设计全部通过 `wp-json/wc/v3` 实现。

### 3.3 彻底删除必须尊重业务数据的 RESTRICT 保护

外键普查结果（`backend/app/models/`）：

| 外键策略 | 表 | 含义 |
|---|---|---|
| `RESTRICT` | `b2b_rfq_items`（询价单明细）、`b2b_order_items`（B2B 订单明细）、B2B 履约记录 | **有真实交易的商品不可删除** |
| `CASCADE` | `product_mappings`、`product_intelligence` 下多张评分/选品表 | 随商品一并删除 |
| `SET NULL` | `product_cost`、`orders` 明细、创意/营销/客服等 | 保留业务数据，仅解除关联 |

**结论**：被 B2B 询价单、B2B 订单或履约记录引用的商品，数据库会**拒绝**硬删除。这在 `AGENTS.md` §1.2「数据是资产」下是刻意保护，必须如实反馈给运营，而不是绕过（例如偷偷改成软删）。

- 彻底删除对这类商品返回明确错误，说明被哪类业务单据引用。
- **这不是缺陷，是约束**：需要删除有交易记录的商品时，正确做法是下架（回收站），不是抹掉交易凭证。

### 3.4 执行顺序

**下架（→回收站）**：先改 WC 为 `trash`，成功后再置本地 `deleted_at`。
失败则中止，保证「回收站里的商品，店铺一定已不可见」。

**彻底删除**：先试本地硬删，成功后再删 WC。
理由：本地被 RESTRICT 挡住是**确定性失败**，先做可以避免动 WC；若先删 WC 而本地删不掉，就会出现「WC 已没了、本地还挂着」的悬空记录。反过来 WC 删除失败是网络性失败，可重试，且此时审计事件里已记下 `wc_id`，仍可人工清理。

```
彻底删除请求
   ↓
1. 记录 wc_id（写审计事件，先于删除）
2. 本地硬删除（savepoint 内）
   ├─ 被 RESTRICT 拒绝 → 回滚，返回错误，WC 完全不动
   └─ 成功
3. WC DELETE ?force=true
   ├─ 成功 → 审计 product.purged
   └─ 失败 → 审计 product.purge_wc_failed（含 wc_id），返回部分成功警告
```

### 3.5 绝不静默失败

响应体必须区分「本地已删 + WC 已永久删除」与「本地已删 + WC 仍存在」。禁止把「WC 没删掉」报成干净的成功（沿用代码库既有的「杜绝假成功」原则，见 `product_pipeline_service.py`、`listing_publish.py` 的同类处理）。

---

## 4. 后端设计

### 4.1 `backend/app/services/wc_unpublish_service.py`（WC 状态与删除集成层）

遵循 `AGENTS.md` §2.3：外部 API 的鉴权、重试、超时、降级集中在集成层。

| 函数 | 作用 |
|---|---|
| `set_wc_product_status(product, target_status)` | 通用：只发送 `{"status": target}` 最小 payload |
| `unpublish_product_from_wc(product)` | 下架封装，目标 `trash`，成功动作名 `unpublished` |
| `restore_product_to_wc(product)` | 恢复封装，目标按本地 `status` 推导，成功动作名 `restored` |
| `delete_wc_product_permanently(product)` | `DELETE /products/{id}?force=true` |
| `resolve_wc_id(product, ...)` / `find_wc_id_by_sku(sku, ...)` | 本地 `meta.woocommerce_id` 丢失时按 SKU 找回 |

`action` 取值：`unpublished` / `restored` / `updated` / `already_set` / `already_absent` /
`skipped` / `deleted` / `failed`。通用的 `updated` 会被下架/恢复封装替换成语义化名称——
`action` 会直接进入 API 响应与审计事件，"updated" 对运营和排障都不够明确。

共同要点：

- 复用既有的 Cloudflare 重试策略（超时 12s、最多 4 次、指数退避、共享 wall-clock 预算），与 `listing_publish.py:_wc_call` 一致——店铺前面是 Cloudflare，会间歇性掐断 TLS 握手。
- 4xx 不重试（是明确答复），5xx 与连接层错误才重试。
- **回读验证**：改状态后 `GET` 确认状态真的落库；确认不了就报失败，不谎报成功。
- `404` 视为「已不存在」，按幂等成功处理。
- 只改状态，**不回写文案/价格/图片**，避免下架动作意外覆盖商品内容。

### 4.2 `backend/app/services/product_lifecycle_service.py`（编排层）

分层：本模块只做编排。外部调用在集成层，DB 写在 `product_service`，审计在 `event_service`。

| 函数 | 作用 |
|---|---|
| `unpublish_products(...)` | 下架到回收站（WC `trash` + 本地 `deleted_at`） |
| `restore_products(...)` | 从回收站恢复（WC 状态按本地 `status` 还原 + `deleted_at = NULL`） |
| `purge_products(...)` | 彻底删除（本地硬删 + WC 永久删除，尊重 RESTRICT） |
| `list_recycled_products(...)` | 回收站列表 |

批量上限与批量推送 `_BATCH_PUSH_MAX = 25` 保持一致：每个商品要占用数十秒 WC 调用预算，批量串行执行（Cloudflare 场景并行不可靠），不设上限会挂死客户端。

### 4.3 API 端点

置于 `products.py`（该文件已有 `_current_user` 鉴权与 `workspace_id` 隔离）。

> **为什么不放在 `listing_publish.py`**：该文件的上架端点（`push_product_to_woocommerce_gated` 等）**没有任何鉴权依赖**（`api_router` 无全局依赖，见 `router.py:96`）。把下架/删除这类破坏性操作放进未鉴权的文件会复制该缺陷。此问题已单独记录，见 §7。

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/products/{product_id}/unpublish` | 下架到回收站（可恢复） |
| `POST` | `/products/unpublish` | 批量下架 |
| `GET` | `/products/recycle-bin` | 回收站列表（`deleted_at` 非空） |
| `POST` | `/products/{product_id}/restore` | 从回收站恢复 |
| `POST` | `/products/restore` | 批量恢复 |
| `DELETE` | `/products/{product_id}/purge` | 彻底删除（不可逆） |
| `POST` | `/products/purge` | 批量彻底删除 |
| `DELETE` | `/products/{product_id}` | **改为**下架到回收站（原为纯本地软删） |
| `POST` | `/products/batch-delete` | **改为**批量下架到回收站 |

**路由顺序注意**：`/products/recycle-bin` 是字面量路径，必须注册在 `GET /products/{product_id}` 之前，否则会被 `{product_id}` 吞掉（此坑 `router.py:111-115` 已有先例：`product_intelligence.product_router` 特意排在 `products.router` 前）。因此回收站列表端点放在 `product_intelligence.product_router` 同一批次，或统一在各路由内部把字面量放在动态段之前。

### 4.4 审计事件

| 事件 | 触发 |
|---|---|
| `product.unpublished` | 下架成功（含 sku、wc_id、wc_status、action） |
| `product.wc_unpublish_failed` | WC 下架失败（含 `local_deleted`：本地是否仍被移入回收站） |
| `product.unpublish_blocked_by_wc_failure` | 下架失败且未 `force_local`，整体中止（未改变任何状态） |
| `product.restored` | 从回收站恢复 |
| `product.restore_wc_failed` | 恢复时 WC 状态还原失败（含 `local_restored`） |
| `product.restore_blocked_by_wc_failure` | 恢复失败且未 `force_local`，整体中止 |
| `product.purged` | 彻底删除成功（本地 + WC 均已删除） |
| `product.purge_blocked` | 本地被业务单据引用（RESTRICT），未删除 |
| `product.purge_wc_failed` | 本地已删但 WC 永久删除失败（含 wc_id 供人工清理） |

> 下架**不再复用** `product.deleted`：回收站只是 `deleted_at` 标记，商品并未被删除，
> 用 `product.unpublished` 更准确；真正不可逆的删除是 `product.purged`。

### 4.5 `force_local` 语义（实现校正）

`force_local=true` 表示运营**明确接受「店铺侧未变更」**，此时本地仍照常变更：

| 场景 | 本地 | WC | 结果 |
|---|---|---|---|
| 下架成功 | 进回收站 | `trash` | 正常 |
| 下架失败 + 未 force | **不动** | 未动 | 409，整体中止 |
| 下架失败 + force | 进回收站 | 未动 | 成功，但 `wc_unpublish_failed` 如实列出 |
| 恢复成功 | 出回收站 | 还原 | 正常 |
| 恢复失败 + 未 force | 留在回收站 | 未动 | 409，整体中止 |
| 恢复失败 + force | 出回收站 | 未动 | 成功，但 `wc_restore_failed` 如实列出 |

**否则会出现自相矛盾的谎报**：返回值声称「已移入回收站」，而 `deleted_at` 仍为空。
该缺陷由 `tests/test_product_lifecycle_service.py` 捕获并修复。

---

## 5. 前端设计

`frontend/src/pages/OperationsPages.tsx`：

1. 商品列表「删除」按钮改为「**下架**」，确认文案明确说明「移入回收站，可在回收站恢复；同时下架 WooCommerce 商品」。
2. 工具栏「批量删除」改为「批量下架」。
3. **新增回收站页面**：列出 `deleted_at` 非空的商品，操作列为「恢复」与「彻底删除」。
   - 彻底删除需二次确认，文案写明**不可逆**且会**永久删除 WooCommerce 商品**。
   - 被业务单据引用的商品，彻底删除失败时展示后端返回的具体原因。
4. 下架/恢复成功后刷新列表，`status` 列沿用既有 `productStatus` 标签。

---

## 6. 边界情况

| 场景 | 处理 |
|---|---|
| WC 凭据未配置 | 返回明确错误，不伪装成功 |
| WC 商品已被人工删除 | `404` 视为已达成目标，幂等成功，记 `already_absent` |
| WC 商品已是 `trash` | 幂等成功，不报错 |
| 重复点击下架/恢复 | 幂等（改状态操作可重复执行） |
| 本地 `woocommerce_id` 丢失 | 按 SKU 找回后再操作 |
| 恢复时 WC 商品已被 WordPress 自动清空 | 报明确错误；可选按 SKU 重建（默认不重建，避免意外复活） |
| 商品被 B2B 单据引用 | 彻底删除返回明确错误，本地与 WC 均不动 |
| 批量中部分失败 | 逐项返回结果，不因单项失败中断整批 |
| 未关联 WC 的商品 | 下架仅改本地，标记 `skipped`，不算失败 |

---

## 7. 发现的相关问题（本次不修，另行跟踪）

1. **`listing_publish.py` 的上架端点未鉴权**：`POST /products/{id}/push-woocommerce`、`POST /products/push-woocommerce` 均无 `_current_user` 依赖，而 `api_router` 没有全局鉴权依赖（`router.py:96`）。任何能访问该 API 的人都可以向线上店铺推送商品。属独立安全问题。
2. **`POST /products/push-woocommerce` 重复注册**：`listing_publish.py:635` 与 `products.py` 中同名同前缀路由并存，依赖注册顺序（`router.py:107` 早于 `:116`）决定谁生效，`products.py` 中那个实际是死代码。
3. **`product_mappings` 表存在但从未被写入**：仅 `product_workbench.py` 只读，推送路径既不读也不写，`meta.woocommerce_id` 是实际唯一判据。两套映射机制并存导致口径不一致。

---

## 8. 测试计划

| 层次 | 用例 |
|---|---|
| 单元（集成层） | 无 `wc_id` → `skipped`；HTTP 404 → 幂等成功；5xx → 重试后失败；回读状态不符 → `verified=False` |
| 单元（编排层） | 下架时 WC 失败 → 本地 `deleted_at` 保持不变；恢复时 WC 失败 → 本地仍留在回收站；purge 被 RESTRICT 拒绝 → WC 完全未被调用 |
| 集成（API） | 下架 → 回收站列表可见 → 恢复 → 回到正常列表；purge 后本地行确实消失且成本数据仍在 |
| **闸门回归** | 构造 V3.0 闸门判定为 `blocked` 的已上架商品，断言**下架与恢复仍然成功**（守护 §3.1） |
| **RESTRICT 回归** | 构造被 `b2b_order_items` 引用的商品，断言 purge 返回明确错误且商品与 WC 均未被删 |

---

## 9. 非目标（Non-Goals）

- 不做「WC 端操作 → 自动同步回本地」的反向联动。
- 不改变 V3.0 闸门规则本身。
- 不为被交易单据引用的商品提供"强制绕过 RESTRICT"的删除通道——那会破坏 `AGENTS.md` §1.2「数据是资产」。

---

## 10. 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-10-03 | 初始版本：下架语义、闸门豁免、删除联动 |
| v2.0 | 2026-10-03 | 改为三层模型：下架=回收站（WC `trash`，可恢复）、独立恢复、彻底删除（本地硬删 + WC 永久删除）；补充 RESTRICT 业务数据保护与执行顺序决策 |
| v2.1 | 2026-10-03 | 实现校正：补 `force_local` 语义表、`action` 命名规则与完整审计事件表；说明下架不再复用 `product.deleted` |

---

## 11. 实现落点与验证

| 文件 | 内容 |
|---|---|
| `backend/app/services/wc_unpublish_service.py` | WC 状态变更与永久删除（集成层） |
| `backend/app/services/product_lifecycle_service.py` | 下架 / 恢复 / 彻底删除 / 回收站列表（编排层） |
| `backend/app/schemas/product.py` | `ProductDeleteResult`、`ProductRestoreResult`、`ProductPurgeResult`、`ProductRecycleBinOut` |
| `backend/app/api/v1/endpoints/products.py` | 9 个端点（见 §4.3） |
| `frontend/src/api/client.ts` | 对应 API 方法与结果类型 |
| `frontend/src/pages/OperationsPages.tsx` | 「商品列表 / 回收站」双视图、下架/恢复/彻底删除操作 |
| `backend/tests/test_wc_unpublish_service.py` | 10 个用例：trash 目标、回读验证、幂等、force 删除 |
| `backend/tests/test_product_lifecycle_service.py` | 8 个用例：失败中止、`force_local`、RESTRICT 时不碰 WC |

**测试驱动发现的实现缺陷（均已修复）**：

1. `unpublish_product_from_wc` 返回通用 `updated`，与语义不符 → 改为 `unpublished` / `restored`。
2. `force_local=true` 时返回值声称「已移入回收站」，但 `deleted_at` 未被设置——自相矛盾的谎报 → 修正为 `move_to_bin = success or force_local`。

> 本地测试环境的既有阻塞（与本次改动无关）：`tests/conftest.py` 用 SQLite 建表，
> 而 `users.mfa_backup_codes` 是 PostgreSQL 专有的 `JSONB`，导致全部 DB 相关用例在
> setup 阶段即报错；`mfa_service` 依赖的 `qrcode` 也未在 `requirements.txt`／
> `pyproject.toml` 中声明。新增的两组测试刻意不依赖数据库，因此可独立运行。
