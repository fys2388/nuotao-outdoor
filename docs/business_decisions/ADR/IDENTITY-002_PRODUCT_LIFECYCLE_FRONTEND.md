# ADR IDENTITY-002 — Nuotao 前端信息架构按产品生命周期重排

> 状态：**Accepted**（2026-08-24）
> 决策编号：IDENTITY-002
> 关联：`docs/project_architecture.md` v0.5；`docs/nuotao_product_score_v3.0.md`；`docs/M5.13_PRODUCT_CANDIDATE_SOURCE_DESIGN.md`；`docs/OPPORTUNITY_DATA_DOMAIN_DESIGN.md`
> 修订：v1.1（2026-08-24）— 记录 Phase 2 后端治理修复，见文末 §Implementation Notes
> 修订：v1.2（2026-08-24）— 阶段⑧ `DecisionQueue.tsx` 实装，并修正 §7 中不成立的 veto / 请求修改承诺
> 修订：v1.3（2026-08-24）— 闸门接入主后端（§Implementation Notes Phase 4）、阶段①② Opportunity 数据域落地、§5 三页收敛实装
> 修订：v1.4（2026-08-24）— 阶段② `Opportunity.tsx` 页面落地、闸门与机会域 74 个测试、修掉 `list_opportunities` 的 `func` 缺失阻断缺陷、前端新增 `typecheck` 脚本

---

## Context（背景）

前端现状与信息架构问题：

1. **无路由**。`frontend/src/App.tsx` 用 `useState<MenuKey>` + `switch(activeKey)` 驱动，无 URL、无深链、无前进后退。产品/候选/审批无法被深链定位。
2. **信息架构按功能域组织**，而非按业务生命周期。侧边栏 4 组（供应链 / 营销增长 / 经营分析 / M5M6）混在一起，用户无法顺着「发现机会 → 评估候选 → 决策 → 发布 → 回流」的流程走。
3. **选品/产品相关 6 个页面互不共享状态**：`Sourcing`（1688 搜索）、`NewtonSourcing`（牛顿选品）、`ProductAnalysis`（AI 分析）、`ProductPipeline`（6 步运行工具）、`ProductListing`（生成文案）、`Products`（推 WC）。后两者打同一个 `/api/v1/products`，一个管文案、一个管推送，没有共享的产品详情视图。
4. **后端已就绪、前端是字符串占位**：`/api/v1/selection/recommendations`、`/api/v1/selection/decisions`、`/api/v1/selection/decisions/{id}/approve` 只作为字符串出现在 `GenericPage.tsx` 的 `apiEndpoints` 列表里，无任何真实页面。后端 `selection_manager_service.py` 已实现。
5. **阶段⑫ 前端空壳**：`Events.tsx` 存在但全库无 `/api/v1/` 调用；后端 `event.py` 模型、`feedback_loop.py`、WC 订单同步均已存在。
6. **死代码**：`frontend/src/components/Layout.tsx`（v0.1.0 遗留，全库无人引用）。

生命周期阶段与后端能力的实际对照（2026-08-24 核对）：

| 阶段 | 前端现状 | 后端现状 |
|---|---|---|
| ① 市场情报 | 无 | `market_trend_service.py`、`competitor_analysis_service.py` |
| ② 机会池 | 无 | **无 Opportunity 模型**（全库仅 3 处字符串提及） |
| ③ 产品候选 | `Sourcing` / `NewtonSourcing` | `products.candidate_status` + 1688 入库 |
| ④ AI 分析 | `ProductAnalysis` / `ProductPipeline` | `product_analysis_service.py`、`pilot_product_analyst.py`、`ai_evaluation.py` |
| ⑤ 成本利润 | `CostModel` | `ProductCost` + `cost_model_service.py`、`profit_engine.py` |
| ⑥ 风险供应链 | `Suppliers` | `supplier.py`、`supply_chain.py`、**`nuotao_veto.py` V1–V12** |
| ⑦ B2C/B2B 评估 | `B2BAgents` | `b2b_service.py`、`b2b_portal_service.py` |
| ⑧ AI 决策+人审 | **字符串占位** | `selection_manager_service.py` + `approval_service.py` + `nuotao_veto.py` |
| ⑨ Product Master | `Products` | 单表 `products`，无显式转正标记 |
| ⑩ AI 内容 | `ProductListing` / `ContentGenerator` | `product_copy_service.py`、`listing_localization_service.py` |
| ⑪ WC 同步 | `Products` | `woocommerce.py`、`product_mapping_service.py` |
| ⑫ 经营回流 | **空壳** | `event.py`、`feedback_loop.py`、WC 订单同步 |

参考 `IDENTITY-001` 的做法：先记录决策与约束，再实施。

## Decision（决策）

前端信息架构按**产品生命周期**重排，12 阶段作为数据模型而非 12 个页面。

### 1. 5 条生命周期道（侧边栏顺序即业务流程顺序）

```
① 机会 Opportunity          ← 阶段 ①②
② 候选评估 Candidate Review ← 阶段 ③④⑤⑥⑦
③ 决策 Decision             ← 阶段 ⑧⑨
④ 内容与发布 Launch         ← 阶段 ⑩⑪
⑤ 经营回流 Growth Loop      ← 阶段 ⑫
+ 经营看板 / 供应履约 / 营销增长 / 系统（横切）
```

### 2. 阶段是数据模型，不是页面

新增 `frontend/src/lifecycle/stages.ts` 作为唯一来源，每个阶段带 `id` / `n` / `lane` / `label` / `backend: ready|partial|missing`。`ProductPipeline.tsx` 的 `PIPELINE_STEPS` 改为从此派生。**禁止任何页面硬编码步骤数组。**

### 3. 三个产品身份用正交状态轴 + 一个时间线组件

新增 `frontend/src/components/lifecycle/ProductTimeline.tsx`，从**已有后端字段**渲染三身份，不引入新状态字段：

| 身份 | 数据源 |
|---|---|
| Candidate | `products.candidate_status` |
| Master | `products.status`（`active`） |
| Listing | `products.meta.woocommerce_id` + `meta.localizations` |

Product Master **不建新表、不建新枚举**，沿用现有三轴正交：`products.status` / `products.candidate_status` / WC `status`。

### 4. 引入 react-router

无 URL 无法实现 `/products/:id`、`/candidates/:id`、可深链的审批队列。引入 `react-router`，`switch(activeKey)` 迁移为路由表；`activeKey` 保留为渲染选择但由 `useLocation` 驱动。**一次性 PR 完成，不渐进迁移。**

### 5. 六个选品页收敛为三个

| 现状 | 目标 |
|---|---|
| `Sourcing` + `NewtonSourcing` + `ProductAnalysis` | `CandidatePool`（列表+详情，1688 抓取与 AI 分析在候选详情 Tab 内） |
| `ProductPipeline` | `PipelineRunner`（输入改为从候选池选择，不再手填） |
| `Products` + `ProductListing` | `ProductMaster`（文案生成 + 闸门预览 + 推 WC 同一详情视图） |

现有页面保留为路由别名重定向一个版本后再移除。

### 6. 缺口阶段做契约优先占位，不造假数据

阶段 ①② 无后端模型，⑫ 前端空壳。渲染明确的契约态（期望模型名、字段、端点），**禁止 mock 数据**。符合 AGENTS.md §1.2「最小闭环优先」与 §2.5。

### 7. 阶段⑧ 优先实装

`/api/v1/selection/*` 后端已就绪。新增 `DecisionQueue.tsx`：决策审批队列 + AI 选品建议双面板，通过 / 拒绝，拒绝必填原因回流 risks。**实施前须先核对 `selection_manager_service.py` 的实际返回结构。**

> **v1.1 契约修正（2026-08-24，实施时核对后端发现）**：本 ADR 初稿写的
> 「veto 明细（V1–V12 的 pass/fail/**pending** 三态）」与「通过/拒绝/**请求修改**」
> 在现实中都不成立：
>
> - `ProductDecision` 模型**不含任何 veto 规则字段**。V1–V12 仅存在于
>   `hotfix-listing-gate/`（未应用补丁），主后端无实现。因此页面只渲染后端真实
>   返回的 `score` / `reasons` / `risks`，并在详情抽屉标注「闸门明细未接入」，
>   不伪造闸门状态。
> - 后端只有 `approve` / `reject` 两个端点，无「请求修改」。第三个动作若需要，
>   属后端新增工作，不在本轮范围。
>
> 同期修正 `frontend/src/lifecycle/stages.ts` 中三个阶段的就绪度标注：
> 阶段 ⑥ 与 ⑪ 由 `ready` 降为 `partial`（闸门缺口），阶段 ⑧ 由「无页面」
> 更新为 `pages: ['decision-queue']`。

## 约束（不可违背）

- 不新增第 4 条线性状态枚举；正交三轴是唯一合法表示。
- 不建 Product Master 独立表；单表 + 生命周期推进是唯一合法表示。
- 不做 12 个页面；缺口阶段必须有显式「后端未接入」契约态，禁止 mock 数据。
- 阶段定义只允许在 `lifecycle/stages.ts` 定义，禁止页面内重复。
- 任何新增外部集成或数据域仍按 AGENTS.md §5 先补设计文档。

## Consequences（后果）

- **正面**：侧边栏顺序即业务流程顺序；三身份时间线成为全 OS 视觉脊柱；`/products/:id` 可深链；阶段⑧ 后端能力被前端真正使用。
- **成本**：react-router 引入触及每个页面（一次性 PR）；新增 3 个真实页面；需先核对 `selection_manager_service.py` 契约。
- **前置依赖（已修复，见 §Implementation Notes）**：阶段③④⑤⑥⑦ 的候选评估道此前受后端两个缺口阻塞——WC→DB 同步直接建行 `candidate_status=NULL` 绕过审批、工作台推送读 dict 绕开主数据闸门。2026-08-24 已修复写入路径。
- **不在本 ADR 范围**：Opportunity 模型设计（阶段①②）需独立数据域设计文档；学习闭环实证（阶段⑫）。

## Alternatives（备选与否定理由）

| 方案 | 否定理由 |
|---|---|
| 建 12 个页面对应 12 阶段 | 单人开发下 = 12 个半空页面；大量阶段后端能力不齐 |
| Product Master 建独立表 | 双写 bug 源；`product_cost` / `meta.localizations` 已挂单表 |
| 8 层线性状态枚举（Candidate→…→Published） | 与现有三轴正交冲突，会把「内容就绪」与「已同步」焊死 |
| B2C Listing 持久化成实体 | `build_wc_payload` 按需生成更优；独立审批已由闸门预览端点覆盖 |
| 渐进迁移路由（新旧并存多版本） | 半套路由比没有更糟，心智负担更高 |
| 缺口阶段填 mock 数据保证页面「看起来完整」 | 违反 AGENTS.md §1.2 最小闭环优先与 §2.5；用户会误信假数据 |

---

## Implementation Notes — Phase 2 后端治理修复（2026-08-24）

ADR §Decision 3 的 PIM 原则在**后端写入路径**上不成立：AI 流水线生成的 listing 数据被直接推送到
WooCommerce，本地 `products` 表**没有对应行**。60 分钟后 WC→DB 反向同步 `sync_products_to_db` 补建行时，
`candidate_status` 取模型默认值 `NULL`，而 `NULL` 的模型语义是「下游渠道原生商品，免候选评审」——
于是 AI 生成的内容在 PIM 中成为一条「已上架、等效于已审批」的产品，零评审。

**根因在写入路径，不在读取路径。** 修复如下：

### 修复 1：`confirm_and_list` 先建本地行再推 WC

`backend/app/services/product_pipeline_service.py` — `confirm_and_list` 签名扩展为
`async def confirm_and_list(pipeline_result, *, status="publish", session, workspace_id)`：

```
is_restricted 检查
  → _create_or_reuse_local_product(session, workspace_id, listing_data)   # 新建，candidate_status="candidate"
  → list_to_woocommerce(listing_data, status)
  → _backfill_woocommerce_id(session, product_id, wc_id, listing_result)  # 回写 meta.woocommerce_id
```

新增 helper `_create_or_reuse_local_product`：按 `workspace_id + sku` 去重（SKU 缺失时 `AI-{uuid4[:8]}`），
写入 `candidate_status="candidate"` / `source="ai_pipeline"` / `status="draft"` /
`meta.created_by` / `meta.listing_data_snapshot`。

端点 `POST /api/v1/product-pipeline/confirm-list` 注入 `db` / `workspace_id`（路由层仍只做依赖注入，
不写业务逻辑，符合 AGENTS.md §2.3）。

### 修复 2：`run_pipeline(auto_list=True)` 同源修复

`run_pipeline` 签名同步扩展 `session` / `workspace_id`（均为可选，向后兼容旧调用方），
`auto_list` 分支复用同一对 helper，`meta.created_by="product_pipeline_auto_list"` 区分触发入口。
`_create_or_reuse_local_product` 增加 `created_by` 参数。

端点 `POST /api/v1/product-pipeline/run` 同样注入 `db` / `workspace_id`。

### 修复 3：反向同步只加审计，不改语义

`backend/app/services/woocommerce_sync_service.py` — `sync_products_to_db` **刻意不在 create 分支
设置 `candidate_status`**。`NULL` 对 WC 端人工发布的原生商品是正确的。改动仅两处：

- 每次新建未评审行打一条 `WARNING` 日志（含 sku / wc_id）
- 返回体新增 `no_candidate_lifecycle` 计数

这两条让「渠道 → PIM」路径绕过评审的规模变得可观测，而不误伤人工发布的商品。
修复 1/2 落地后，工作台产出的商品在反向同步时命中 UPDATE 分支，不再新建行。

### 后续工作（v1.3 更新）

v1.1 时记录为「未解决」的三项，在 v1.3（Phase 4，同日）已全部落地，见下方 Phase 4 记录：

| 项 | v1.1 状态 | v1.3 状态 |
|---|---|---|
| 真正的 veto 闸门 | 主后端无实现 | ✅ `listing_gate.py` 迁入主后端并接线 |
| `push_product_to_woocommerce` 无闸门 | 推送不过评审 | ✅ 同批接线，裁决 200/409/422 |
| `import_from_1688` coroutine bug | 返回 coroutine 而非 dict | ✅ 改 async + 补 `await` + 注入 db session |

仍未在本轮解决：

| 项 | 说明 |
|---|---|
| V1–V12 完整规则集 | 本次落地的是发布前 6 条规则（缺 SKU / 缺价格 / 中文文案无英文本地化 / 候选未批准 / 英文文案未批准 / 文案过薄）。`nuotao_veto.py` 的完整 V1–V12 供应链硬规则未评估、未迁移，属独立评审项 |
| 信号 → 机会自动聚类 | 见 `docs/OPPORTUNITY_DATA_DOMAIN_DESIGN.md` §6；需要聚类规则与阈值定义，属 AGENTS.md §1.2「禁止凭感觉」高风险区 |
| 阶段⑫ 学习闭环实证 | `Events.tsx` 仍是空壳（本 ADR §Context 第 5 点），未在本轮范围 |

### Phase 3：阶段⑧ `DecisionQueue.tsx`（2026-08-24）

新增 `frontend/src/pages/DecisionQueue.tsx`，双面板：

- **决策审批队列** — `GET /api/v1/selection/decisions`，支持按审批状态
  （pending/approved/rejected）与决策类型（test/hold/reject）筛选；
  通过 → `POST /decisions/{id}/approve`；拒绝 → `POST /decisions/{id}/reject`，
  拒绝原因必填并回流 `risks`。
- **AI 选品建议** — `GET /api/v1/selection/recommendations`（按 `ProductScore`
  实时生成，非持久化），「转决策」→ `POST /decisions` 进入 pending 队列。

前端类型定义严格对齐 `selection.py` / `selection_manager_service.py` 的实际返回
结构。已注册路由 `decision-queue`，侧边栏置于「AI建议审批」之后（同为人工审批队列）。

**未做**：veto 明细（见 §7 契约修正）、「请求修改」动作（后端无端点）。

### Phase 4：发布前闸门进入主后端（2026-08-24）

**根因**：v1.1 记录了治理写入路径的修复，但闸门本身仍在 `hotfix-listing-gate/` 补丁目录里，
从未进入主后端。`evaluate_gate` 与 `nuotao_veto.py` 实际**不存在于任何已应用代码**（全库检索
仅命中本 ADR 自身的文字），因此「V1–V12」是当时的一个未核实表述。实际可迁移的是一套自包含的
发布前规则模块。

**落地**：

- `backend/app/services/listing_gate.py` — 迁入 `hotfix-listing-gate/backend/app/services/listing_gate.py`
  （自包含，仅依赖 `logging` / `re` / `typing`）。6 条规则：
  - **硬阻断**（`blocked` → 422，不可放行）：`missing_sku`、`cjk_without_localization`
  - **需人工复核**（`needs_review` → 409，`force=true` 可放行）：`missing_price`、
    `unapproved_candidate`、`unapproved_copy`、`thin_copy`
  - `cjk_in_approved_copy`（已批准英文文案仍含中文）归入 needs_review
- 新增 `gate_product_for_publish(product, force=)` 单一入口：`resolve_prices` +
  `get_english_copy` + `evaluate_gate`，避免每条发布路径各自实现前置检查而漂移。
- 接线点（业务规则集中在服务层，端点只做依赖注入与状态码映射，符合 AGENTS.md §2.3）：
  - `push_product_to_woocommerce(product_id, session, force=False)` → 端点
    `POST /products/{id}/push-woocommerce?force=true` 映射 409 / 422
  - `product_pipeline.confirm_and_list(..., force)` → `POST /product-pipeline/confirm-list`
    的 `ConfirmListRequest.force`
  - `run_pipeline(auto_list=True)` 同源闸门
  - 新增只读预览 `GET /products/{id}/listing-gate`，返回
    `{gate, reasons, hard, forceable, ...}`，不执行推送 —— AGENTS.md §3.1 的
    human-in-the-loop 由此从口号变为可审计的前置检查

**边界**：本次是 6 条**发布前**规则，不是 `nuotao_veto.py` 的完整 V1–V12 供应链硬规则集。

### Phase 4：`import_from_1688` coroutine bug

`product_pipeline_service.py::import_from_1688` 是同步 `def`，直接调用 async `run_pipeline`
而未 `await`，返回 coroutine 对象而非结果 dict。修复：函数改 `async def`、调用处补 `await`、
端点 `POST /product-pipeline/import-from-1688` 注入 `db` / `workspace_id`。

同时补一个防御：`auto_list=True` 但无 db session 时**显式降级为只分析、不推送**，并在返回体
置 `auto_list_skipped` 说明。否则无会话路径会静默退化回 v1.1 记录的那个治理漏洞。

### Phase 4：阶段①② Opportunity 数据域

设计先行（AGENTS.md §5）：`docs/OPPORTUNITY_DATA_DOMAIN_DESIGN.md`。落地两张表与端点族：

- `opportunities` — 市场信号的归属实体。`signal_type` ∈
  `search_trend / competitor_gap / review_pain / social / manual / other`；
  `status` ∈ `open / evaluating / converting / closed / discarded`（唯一状态轴）；
  `confidence` 仅接受人工填写，后端不推断（AGENTS.md §1.2 禁止凭感觉）；
  `market_signals` / `evidence` 为追加式 JSON（信号形态异构，不做规范化外键）
- `opportunity_candidates` — 机会 ↔ 产品候选连接表，唯一约束
  `(workspace_id, opportunity_id, product_id)`，任一端删除级联删除
- `GET/POST /api/v1/opportunities`、`GET/PATCH /{id}`、`GET/POST /{id}/candidates`、
  `DELETE /{id}/candidates/{product_id}`、`GET /api/v1/opportunities/meta`（枚举字典，
  前端禁止硬编码枚举）

**刻意不做**：不读不写 `product_scores` / `product_decisions`（各有唯一载体）；
**不写入 `products.candidate_status`**（归属关系 ≠ 状态推进，M5.13 的状态机归候选所有）；
不做信号 → 机会自动聚类（需独立评审）。

### Phase 4：§5 三页收敛

按 §5 把 6 个选品页收敛为 3 个：

| 原页面 | 目标页面 |
|---|---|
| `Sourcing` + `NewtonSourcing` + `ProductAnalysis` | `CandidatePool` |
| `ProductPipeline` | `PipelineRunner`（输入改为从候选池选择） |
| `Products` + `ProductListing` | `ProductMaster`（文案 + 闸门预览 + 推 WC 同一详情视图） |

三个新页面一律用真实 `fetch`，能力缺失时渲染显式契约态，不造 mock 数据（§6）。
原页面保留为路由别名一个版本后再移除。

### Phase 5：阶段② `Opportunity.tsx` 与闸门测试（2026-08-24）

Phase 4 把数据域与闸门落进后端，但阶段②没有界面，闸门也没有测试。Phase 5 补这两块。

**阶段②机会池页面** `frontend/src/pages/Opportunity.tsx`：

- 接通 8 个真实端点（`/meta` 枚举字典 + 机会 CRUD + 候选关联/解绑 + 关联弹窗的
  `GET /api/v1/products`）。零 mock 数据，错误一律 `message.error`，
  三态（空态 / 加载 / 错误）齐全。
- 枚举**值**全部来自 `GET /meta`，仅中文 label 映射写死 —— 遵守 §6「缺口阶段做契约优先
  占位」的同一原则：前端不复制后端词汇表。
- 阶段定义只从 `../lifecycle/stages` 取（`STAGE_BY_ID.get('opportunity')`），
  页面内不硬编码阶段数组。
- 详情抽屉 4 Tab：基本信息（含 `market_signals` / `evidence` / `signal_source` 可读 JSON）、
  状态（改到 `closed` / `discarded` 时 `closed_reason` 必填）、关联候选（含解绑二次确认）、
  信号与证据。
- `stages.ts` 阶段② 由 `pages: []` 改为 `pages: ['opportunity']`。
  路由接线走既有 `route.ts` 的 `ROUTE_RE`（`[a-z0-9-]+`），无需额外配置。

**接线的实际契约偏差**（前端已适配，记录以免下次误判）：

| 项 | ADR / 任务描述 | 后端实际 | 前端处理 |
|---|---|---|---|
| 列表返回形状 | `{items, total}` | 扁平数组 | `extractList()` 兼容两种 |
| 列表查询参数 | 含 `signal_type` | 仅 `status` / `category` / `limit` / `offset` | `signal_type` 改前端过滤 |
| 详情候选 | 独立 `GET /{id}/candidates` | `GET /{id}` 已内联 `candidates` | 复用内联数据，省一次往返 |
| `limit` 上限 | 未注明 | `le=200` | 请求 `limit=200` |

**闸门与机会域测试** `backend/tests/test_listing_gate.py`（40）+
`test_opportunity_domain.py`（34），合计 **74 passed**，全部跑在 `conftest.py` 的
in-memory SQLite 上，不依赖外部服务：

- 三态 + `forced`：完整数据 → `passed`；缺 SKU → `blocked`；候选未过审 → `needs_review`
  且 `forceable=true`；`force=true` → `forced`
- **最关键断言**：`test_gate_hard_block_cannot_be_forced` —— 缺 SKU + `force=true` 仍然
  `blocked` 且 `forced=false`。这是本模块存在的理由。
- 7 个 reason code 各自独立触发；`thin_copy` 不与 `unapproved_copy` 叠加（后者检查在前）
- `candidate_status=None` **不产生** `unapproved_candidate`（NULL 表示已是下游商务产品，
  不归候选状态机管）
- `resolve_prices` 六级优先级；**不认** `cost_price` / `suggested_price`（成本价不是零售价）
- PIM 隔离：关联与解绑前后 `products.candidate_status` 不变（service 层与 endpoint 层各测一次）

**修复一个阻断缺陷**：`opportunity_service.py` 用了 `func.count()` 但未 import `func`，
`list_opportunities` 一调用就 `NameError`，`GET /opportunities` 整个列表端点不可用。
改为 `from sqlalchemy import func, select`。三个受影响测试原本带 `@pytest.mark.xfail(strict=True)`
标记，修复后移除标记 —— 现在它们是活测试，再回归会直接失败。

**前端类型门禁**：`frontend/package.json` 新增 `typecheck` 脚本（`tsc --noEmit`），
并把 `src/App.tsx` 的 3 个 TS2339 `.badge` 错误一并清掉。历史基线 232 个错误中的
141 个是 `@ant-design/icons` 6.3.4 删掉的图标导出，已按语义等价映射批量修好；
其余 91 个逐文件修完（补漏 import 12 处、antd v6 API 适配 4 处、类型修正 5 处、
import 语法 2 处），并删掉 5 个零引用的孤立页面。错误数归零后接入 CI：
`ci-check.yml` 的 frontend job 在 build 前增加 `npm run typecheck` 步骤。
`build` 只用 vite/esbuild、不检查类型，此前 232 个 TS 错误可以一路进 main。

修掉一个真实运行时 bug：`AgentSuggestions.tsx` 在 `setStats()` 里引用了从未定义的
`allItems`（4 次），该代码路径一执行就抛 ReferenceError。
