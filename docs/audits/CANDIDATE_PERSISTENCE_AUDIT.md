# P0-1 Candidate Persistence — Phase 1 只读审计报告

日期: 2026-10-05
状态: 审计完成，未修改任何代码
范围: `1688 / Newton → 加入候选 → Product Candidate 持久化` 全链路

---

## 0. 结论摘要

「加入候选」按钮（`NewtonSourcing.tsx`）调用的 `POST /newton/sourcing/import`
**确实会持久化** `products` 行（source=1688, candidate_status=candidate）和
`product_sources` 行，并且整个批量在一条请求事务中提交。

但它与 Active SOP（`docs/PRODUCT_UPLOAD_SOP.md` §1.5）之间的持久化契约
有 **5 个缺口**，这正是"UI 显示 16 个 candidate，但生产库 0 条"类问题的
根本原因：

| # | 缺口 | 影响 |
|---|------|------|
| G1 | 不创建 `product_sourcing_candidates` 行 | SOP 要求 1:1 供应商候选；生产库该表恒为 0 |
| G2 | 不创建 `product_cost_snapshots` 行（写的是 `product_cost`） | SOP 要求成本快照链路；成本历史/审计缺失 |
| G3 | 不写 `event_log` | 无审计事件；验收证据链断裂 |
| G4 | SKU 用 `NEWTON_<offer_id>`，违反 SOP 红线 `SKU = NT-<offer_id>` | 同一 offer 走 pipeline 路径生成 `NT-<id>`、走 Newton 路径生成 `NEWTON_<id>`，SKU 查重在跨路径时失效 |
| G5 | 响应未回传逐条 `product_id`/`candidate_id`/`trace_id`/`source_offer_id`，且 500 时不显式回滚 | 前端无法用真实 ID 更新 UI；部分失败语义含糊 |

"16 个"的真实来源（与 `CANDIDATE_SOURCE_LINEAGE_REPORT.md` 的结论一致）：
`sourcing_import_results.json`（Excel 导出 60 个，只生成 JSON 报告不写库）
+ 本地 `data/newton_sourcing_results/*.json`（Newton 搜索缓存，从未导入 DB）
+ 前端 `localStorage`（带入工作流）。**16 个候选从未真实落库**，UI 上的
数字来自搜索/缓存层，不来自 `products` 表。

---

## 1. 链路逐跳追踪

### 1.1 前端「加入候选」→ 哪个 API

- 页面: `frontend/src/pages/NewtonSourcing.tsx`
  - 单个按钮 `handleAddCandidate(item, index)`（L169）
  - 批量按钮 `handleBatchAddCandidates()`（L145）
  - 都收敛到 `addCandidates(products, keys)`（L113）
- 调用: `api.importNewtonSourcing(products, result?.task_id, result?.query)`
  （`frontend/src/api/client.ts` L1449）
- 实际 HTTP: **`POST /api/v1/newton/sourcing/import`**
  （body: `{ products, sourcing_id, source_query }`）
- 另一入口 `handleCarryToPipeline`（L156）："带入工作流"先写
  `localStorage('product_pipeline_input')` 再**并行**调用同一个
  `addCandidates`。工作流页面本身不建 candidate。

### 1.2 API → 哪个 service

`backend/app/api/v1/endpoints/newton_agent.py` L452-483:
`import_sourcing_to_candidates(request, db)` 直接调用
`newton_sourcing_storage.import_products_to_candidates(session, products,
sourcing_id, source_query)`。

### 1.3 是否调用 get_or_create_by_source()

**是，间接调用**。`import_products_to_candidates`（L274）对每条商品调用
`sourcing_service.create_product_candidate(...)`，后者内部调用
`product_source_identity.get_or_create_by_source(session, workspace_id,
source_offer_id, build, fallback_sku)`（`sourcing_service.py` L110）。

### 1.4 source_offer_id 是否正确解析

**基本正确**。`newton_sourcing_storage` 把 1688 offer id 放进
`candidate_data["source_id"]` 和 `["ali1688_product_id"]`（L241/245），
`resolve_source_offer_id` 优先级 `source_id` → `source_url` → meta 历史键，
能解析出规范化 offer id 并写入 `products.source_offer_id`。
数据库有唯一索引 `uq_products_workspace_source_offer`
（migration 0069）作为并发兜底。

缺陷：`create_product_candidate` 在**有 offer id 时生成的 SKU 是
`SKU-1688-<offer_id>`**（`sourcing_service.py` L91），而 SOP 规定
`SKU = NT-<offer_id>`；Newton 路径又自己先拼了 `NEWTON_<offer_id>`
作为 fallback_sku。三条路径三种 SKU，跨路径 SKU 查重失效（来源键
查重仍有效，所以不会出现重复行，但 SOP 红线违规）。

### 1.5 workspace_id 是否正确

- `import_sourcing_to_candidates` **没有注入** `workspace_id`，
  依赖 service 端 `workspace_id or DEFAULT_WORKSPACE_ID`
  （`newton_sourcing_storage.py` L181/193）。
- `DEFAULT_WORKSPACE_ID = 00000000-0000-0000-0000-000000000001`
  与 `sourcing_service` 常量、alembic seed 一致；`list_newton_candidates`
  也按 `Product.source == "1688"` 过滤，但**没有按 workspace 过滤**
  （L340-343）——多 workspace 时会跨租户泄露（当前单 workspace 部署，
  属潜在缺陷）。

### 1.6 Product 是否真正 INSERT / UPDATE

**是**。`create_product_candidate` → `get_or_create_by_source` 在 savepoint
里 `session.add(product)` + flush；命中已有来源键则 UPDATE 字段。
最终由调用方 commit（见 1.9）。

### 1.7 product_sourcing_candidates 是否创建

**否。整条链路没有任何代码写 `product_sourcing_candidates`**
（`SourcingCandidate` 模型只在 `product_intelligence.py` 被读，
`candidate_editor.py` 被读）。生产库 0 条是**代码契约缺口**，不是数据丢失。

### 1.8 product_sources 是否保存 raw snapshot

**是**。`create_product_candidate` L164 创建
`ProductSource(workspace_id, product_id, source_type, source_url,
raw_data=product_data, trace_id)`，`raw_data` 是 AI_JSON，包含
`ali1688_product_id`、`source_id`、价格、图片等完整快照。
注意 `sourcing_service.create_product_candidate` **不写**
`product_cost_snapshots`（只写 `product_cost`），与 SOP §1.5 不符。

### 1.9 是否 commit

`import_products_to_candidates` 在循环末尾
`await session.commit()`（L312）。端点层没有再 commit。

**关键缺陷**：循环内单条失败执行 `session.rollback()`（L292/300）——
这是**整个请求事务**的 rollback，把之前所有已 flush 成功的条目也一并
回滚。后果：

1. 批量 16 条中任何 1 条失败 → 之前 15 条全部撤销 → 最终 commit 为
   空 → **products=0 但 API 可能返回 success=True**（当
   `skipped >= total` 时，L469 `ok = imported > 0 or (total > 0 and
   skipped >= total)`）。这是"UI 显示存在、库里为 0"的最可能触发器。
2. 部分成功时（前 N 条成功、第 N+1 条失败后后续条目又成功）：
   rollback 后 session 仍可继续使用，后续条目会**重新写入**；
   结果不可预测，`imported` 计数与实际落库数不一致。

正确做法：单条隔离用 **savepoint**（`session.begin_nested()`），
与 `get_or_create_by_source` 内部已有的 savepoint 模式一致。

### 1.10 event_log 是否记录

**否**。`import_products_to_candidates` 和 `create_product_candidate`
都不写 `event_log`（`event_service.create_event` 完全未出现）。
只有 `product_service.import_products`（CSV 路径）和
`product_intelligence.intake_product` 写事件。

### 1.11 UI 为什么会显示成功

- `addCandidates` 成功分支：`imported > 0` 时
  `message.success('已加入候选库 N 个')` 并把 key 加入
  `importedKeys`，按钮变"已加入候选"。
- **skipped == total（全部已存在）时也走 success 分支**（L469），
  文案是 warning"没有可导入的商品（可能已存在）"——但按钮态仍可能
  被上游逻辑误读为成功。
- 失败路径：HTTP 500 被 catch，`message.error`，本地 `importedKeys`
  不更新——**没有 optimistic success**。
- 真正的"假成功"来源是 **搜索/缓存层**：16 个数字来自
  Newton 搜索结果（`/newton/search` 的临时返回 + 本地 JSON 缓存
  `data/newton_sourcing_results/`），与 DB 无关。只要用户没点
  "加入候选库"或点了但批量回滚，DB 永远是 0。

### 1.12 为什么数据库最终可能为 0

按概率排序：

1. **用户未真正点击"加入候选库"**：16 个来自搜索结果渲染，
   "带入工作流"只写 localStorage，不写 DB。
2. **点击了，但批量中某条触发整事务 rollback**（1.9 的 G5/G1 缺口）：
   之前成功的条目被撤销，commit 为空或残缺。
3. **后端当时指向的库与验收查的库不一致**：前端 `VITE_API_BASE`
   默认 `/api/v1` 同源代理；dev 环境 SQLite（`_local_dev.db`）与
   prod PostgreSQL 是两个库。若按钮在 dev 前端 + dev SQLite 上点成功，
   去查 Production PostgreSQL 自然是 0。（audit_env.py 证据：
   production 单 workspace，无环境错位。）

---

## 2. 现有代码定位（修复落点）

| 文件 | 角色 |
|------|------|
| `backend/app/services/newton_sourcing_storage.py` | 批量导入编排（需改造为 savepoint 隔离 + SourcingCandidate + event + 真实 ID 返回） |
| `backend/app/services/sourcing_service.py` `create_product_candidate` | 唯一 candidate 创建 service（需补 NT- SKU、cost snapshot、event） |
| `backend/app/services/product_source_identity.py` | `get_or_create_by_source` / `resolve_source_offer_id`（幂等唯一真相源，不动） |
| `backend/app/api/v1/endpoints/newton_agent.py` `/sourcing/import` | 端点（需注入 trace_id、workspace，commit 后返回真实 ID） |
| `backend/app/models/product_intelligence.py` `SourcingCandidate` | `product_sourcing_candidates` 模型（复用，不建新表） |
| `frontend/src/pages/NewtonSourcing.tsx` | 按钮与响应处理（需按真实 ID 更新 UI） |

## 3. 修复契约（Phase 2-6 落地依据）

**唯一入口**: `create_product_candidate()`（sourcing_service）。
Newton 批量导入是它的**编排层**，不建第二套创建逻辑。

单条候选事务内必须一起提交:

```
products (source=1688, candidate_status=candidate, source_offer_id, sku=NT-<offer_id>)
product_cost_snapshots (append-only 成本快照)
product_sourcing_candidates (1:1 供应商候选)
product_sources (raw_data 快照)
event_log (product.candidate.imported, 带 trace_id)
```

幂等键: `workspace_id + source_offer_id`（`get_or_create_by_source`，
DB 唯一索引兜底），**禁止按标题去重**。

API 响应: 仅当 commit 成功后才返回
`{ created, exists, product_id, candidate_id, source_offer_id, trace_id }`；
失败回 500，前端显示真实错误，禁止 optimistic success。
