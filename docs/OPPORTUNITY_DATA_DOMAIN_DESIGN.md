# Opportunity 数据域设计 — 阶段①② 机会实体

> 状态：**设计稿 → 已实现**（2026-08-24）
> 关联：`docs/business_decisions/ADR/IDENTITY-002_PRODUCT_LIFECYCLE_FRONTEND.md`（阶段①②）、
> `docs/M5.13_PRODUCT_CANDIDATE_SOURCE_DESIGN.md`（候选生命周期）、`docs/nuotao_product_score_v3.0.md`（评分，本域不负责）
> 依据：AGENTS.md §1.2（先规划后编码、最小闭环优先、禁止凭感觉）、§5（新数据域先补设计文档）

---

## 1. 缺口定位

ADR IDENTITY-002 阶段①② 是全链路唯一的**无实体**阶段：

| 阶段 | 现状 |
|---|---|
| ① 市场情报 | `market_trend_service.py`、`competitor_analysis_service.py` 存在，但产出未沉淀为一等实体，前端无页面 |
| ② 机会池 | **无 Opportunity 模型**（全库仅 3 处字符串提及） |

后果：市场信号采集了但没有归属物。候选（`products.candidate_status="candidate"`）只能凭人工记忆回答
「你为什么选这个？」，无法从机会追溯到候选，也无法在机会关闭时回收其候选。这与 AGENTS.md §1.2
「数据是资产」直接冲突。

**本设计只做一件事：给市场信号一个可查询、可引用、可追溯的归属实体，并把它与候选连接起来。**

---

## 2. 边界（明确不做）

| 不做 | 理由 |
|---|---|
| Opportunity 评分模型 | 评分已有唯一载体 `product_scores`（ADR §8 选品逻辑 v2.0），建第二套评分必然漂移 |
| 从 `market_trend_service` 自动生成 Opportunity | 需要信号 → 机会的聚类规则，属 AGENTS.md §1.2「禁止凭感觉」的高风险区。本轮只留人工创建 + 信号挂载入口 |
| Opportunity 自动推进候选状态 | 候选生命周期状态机已在 M5.13 定义（`candidate_status`），本域只记录归属关系，不改写状态 |
| Opportunity 与 Product Decision 联动 | 决策仍挂在 `product_decisions`；机会只是决策的**上下文引用**，不是决策主体 |
| 前端页面 | ADR §6 要求缺口阶段先做契约态；前端页面待后端契约稳定后再做 |

---

## 3. 数据模型（2 张新表）

### 3.1 `opportunities`

一个机会一行。`market_signals` / `evidence` 为 JSON，允许信号形态异构，不做规范化外键——
因为信号来源（搜索趋势 / 竞品缺口 / 评论痛点 / 社媒 / 人工）的字段集完全不同，强行拉平会得到
一张全是 NULL 的宽表。

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | UUID | PK | |
| `workspace_id` | UUID | FK workspaces.id, index | 多租户隔离 |
| `title` | VARCHAR(128) | NOT NULL | 一句话机会描述，如「户外露营灯 30W 以上市场缺口」 |
| `description` | TEXT | NULL | |
| `category` | VARCHAR(128) | NULL | 与 `products.category` 同一词表，供筛选 |
| `keywords` | JSON | NOT NULL, default `[]` | 字符串数组，供全文检索 |
| `signal_type` | VARCHAR(24) | NOT NULL | `search_trend` / `competitor_gap` / `review_pain` / `social` / `manual` / `other` |
| `signal_source` | JSON | NULL | 信号出处元信息：`{origin, url, fetched_at, trace_id}` |
| `market_signals` | JSON | NOT NULL, default `[]` | 已挂载的信号条目数组，追加式 |
| `evidence` | JSON | NOT NULL, default `[]` | 可追溯证据链接，追加式 |
| `status` | VARCHAR(16) | NOT NULL, default `open` | `open` / `evaluating` / `converting` / `closed` / `discarded` |
| `confidence` | NUMERIC(5,2) | NULL | 0–100，人工填写。**禁止后端推断**（§1.2 禁止凭感觉） |
| `closed_at` | TIMESTAMPTZ | NULL | |
| `closed_reason` | VARCHAR(256) | NULL | |
| `created_at` / `updated_at` | TIMESTAMPTZ | | |

`status` 是**唯一**的机会状态轴，不新增第二个生命周期列——M5.13 的教训是候选与商务状态一旦
焊在一个枚举上就会互相污染，这里从第一天就只保留一条。

### 3.2 `opportunity_candidates`（连接表）

| 列 | 类型 | 约束 |
|---|---|---|
| `id` | UUID | PK |
| `workspace_id` | UUID | FK workspaces.id, index |
| `opportunity_id` | UUID | FK opportunities.id, ondelete CASCADE, index |
| `product_id` | UUID | FK products.id, ondelete CASCADE, index |
| `linked_at` | TIMESTAMPTZ | NOT NULL, default now |
| `link_reason` | VARCHAR(256) | NULL |

唯一约束 `(workspace_id, opportunity_id, product_id)`：一个机会对同一候选只记录一次归属。
删除机会或产品任一方，连接行级联删除；**不级联改写候选的 `candidate_status`**（M5.13 的状态机是候选自己的事）。

### 3.3 为什么不是 `opportunities.keywords[]` 直接外键到 products

`products` 是 PIM 单一来源（ADR §3），产品不应知道机会的存在。连接表让两个方向都可查询：
机会 → 候选（评估该机会有多少候选在跑），候选 → 机会（解释为什么选它）。

---

## 4. API 契约

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/v1/opportunities?status=&category=&limit=&offset=` | 列表，新到旧 |
| `POST` | `/api/v1/opportunities` | 创建（人工） |
| `GET` | `/api/v1/opportunities/{id}` | 详情，含已关联候选摘要 |
| `PATCH` | `/api/v1/opportunities/{id}` | 更新状态 / 置信度 / 关闭原因 |
| `POST` | `/api/v1/opportunities/{id}/candidates` | 关联候选（body: `{product_id, link_reason?}`） |
| `GET` | `/api/v1/opportunities/{id}/candidates` | 已关联候选列表 |
| `DELETE` | `/api/v1/opportunities/{id}/candidates/{product_id}` | 解除关联 |

与 ADR IDENTITY-002 §阶段② 声明的契约端点（`/api/v1/opportunities`、
`/api/v1/opportunities/{id}/candidates`）一致。

响应错误：非法 UUID → 400；不存在 → 404；重复关联 → 409。路由层只做依赖注入与状态码映射，
业务规则集中在 `services/opportunity_service.py`（AGENTS.md §2.3）。

---

## 5. 与现有域的交接点

```
market_trend_service / competitor_analysis_service   （阶段①，产出信号，暂无归属）
        │  人工挂载（本轮）        │  未来：聚类规则（未做，见 §6）
        ▼                          ▼
   opportunities  ──── opportunity_candidates ──── products (candidate_status)
        │                                              │
        └── 决策上下文引用 ───────────────── product_decisions（M5.13，决策主体不变）
```

- **本域不读取也不写入 `product_scores` / `product_decisions`**。
- **本域不写入 `products.candidate_status`**。连接 ≠ 状态推进。
- 候选的来源追溯仍走 M5.13 的 `product_sources`；`opportunity_candidates` 回答的是
  「为什么选」，`product_sources` 回答的是「从哪来」，两个问题不合并。

---

## 6. 明确留作后续（不在本轮）

| 项 | 说明 |
|---|---|
| 信号 → 机会自动聚类 | 需定义聚类规则与阈值，属 AGENTS.md §1.2「禁止凭感觉」高风险区，须独立评审 |
| 机会 → 候选状态自动推进 | 需明确「机会关闭时候选怎么办」的业务规则，本设计刻意不预设 |
| 前端页面 | 后端契约稳定后再做；ADR §6 要求缺口阶段先渲染契约态，禁止 mock 数据 |
| 机会的 Agent 工具化 | 需按 AGENTS.md §3.1 走白名单工具注册 + 审批队列 |

---

## 7. 迁移策略

新增两张表 + 无存量数据，故 **non-destructive、无 backfill**：
- `CREATE TABLE opportunities` + 索引
- `CREATE TABLE opportunity_candidates` + 唯一约束
- 不涉及 `products` 表任何 DDL 变更
