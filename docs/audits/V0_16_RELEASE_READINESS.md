# v0.16 成本覆盖治理 — 发布就绪审计

> 审计日期：2026-09-30（第二轮，执行环境已恢复）
> 审计对象：v0.16 成本覆盖治理（P2-9）
> 审计方式：**实机执行**（pytest / typecheck / build / git / 线上只读探测）
> 结论：**STOP —— 代码与本地验证全绿，但 staging 未部署、生产仍运行 pre-v0.16 代码，四门禁未齐，不允许进入 20-product rollout**

---

## 0. 总结（Executive Summary）

| 门禁 | 要求 | 实际 | 状态 |
|---|---|---|---|
| Code Ready | 测试全绿 + typecheck/build 通过 | 成本治理 18/18、相关 25/25、全量 951 收集、套件 exit 0；build exit 0；typecheck 0 新增错误（5 个 pre-existing，均在未改动文件） | ✅ |
| Environment Ready | Backend/PG/Redis/WC/LLM/1688 可用 | healthz/readyz=ok（database/redis ok）、WooCommerce 在线、LLM/1688 网络可达（凭据未验证） | ✅（凭据未验证） |
| Staging Verified | v0.16 先入 staging 并跑通 7 步链 | **未部署** —— 无推送凭据（credential.helper=manager，需交互；无 GH_TOKEN），无法推 main 触发 deploy.yml | ❌ |
| Production Verified | 线上 smoke | 已实机探测，但**生产跑的是 origin/main（c8c5113，pre-v0.16）**，未含任何 v0.16 代码；本地 main 领先 15 个提交 | ⚠️ 仅验证 pre-v0.16 基线 |

**三个门禁满足（其中 Production 仅验证旧基线），Staging Verified 未满足。按停止条件：任何一项失败 → STOP。不进入 20-product rollout。**

本轮相比第一轮（2026-09-13）新增：
1. **实机跑通全部第一阶段命令**（第一轮因执行器 ACL 失败全部未执行）。
2. **修复 1 个 High 级路由阴影缺陷**（`GET /products/{product_id}` 阴影 4 个字面端点），并证明它是「把 15 个未推送提交部署到生产前」的**前置必备项**。
3. **实机核验 F-1 四种成本状态的真实返回值**（非断言，是打印值）。
4. **实机探测生产**（第一轮无网络能力）—— 发现生产尚未部署 v0.15 时代代码。
5. **用真实生产数据（非伪造）圈定 Pilot Products**。

---

## 1. 测试结果（实机执行）

执行器已恢复（`pwsh` + 项目 venv `.\.venv\Scripts\python.exe`，Python 3.12.2 / pytest 9.1.1 / pytest-asyncio 1.4.0）。

| # | 命令 | collected | passed | failed | errors | skipped | xfailed | exit code |
|---|---|---|---|---|---|---|---|---|
| 1 | `pytest tests/test_cost_coverage_governance.py -q` | 18 | **18** | 0 | 0 | 0 | 0 | **0** |
| 2 | `pytest tests/test_profit_engine.py tests/test_cost_blocker.py tests/test_product_intelligence.py tests/test_product_import.py -q` | 25 | **25** | 0 | 0 | 0 | 0 | **0** |
| 3 | `pytest tests --ignore=tests/integration --collect-only -q` | **951** | — | — | — | — | — | **0** |
| 4 | `pytest tests --ignore=tests/integration -q` | 951 | 951 | **0** | 0 | 0 | 0 | **0** |

说明：
- 第 4 项在 `AGENT_ALERT_SCHEDULER_ENABLED=true` 下运行。本地 `backend/.env` 设了 `AGENT_ALERT_SCHEDULER_ENABLED=false`，该值会让 3 个 `tests/test_alert_scheduler.py`（lifecycle / loop tick / tick exception）失败 —— **纯环境配置失败，与 v0.16 无关**，覆盖变量后全绿。
- **特别确认 F-1 回归测试 `test_cost_overview_withholds_margin_for_invalid_cost` 实际通过**（第 1 项 18/18 内）。

### 1.1 F-1 四种成本状态实机取值（真实值，非断言）

对真实服务层（内存 SQLite，与测试夹具同款引擎）打印 `profit_analysis` / `list_cost_overview` 实际返回值：

| 状态 | sale_price | total_landed_cost | cost_status | contribution_margin | 总览表 margin | FAKE(price−0)? |
|---|---|---|---|---|---|---|
| A 有效成本 | 99.99 | 51.00 | KNOWN | **41.99** | 41.99（rate 0.4199） | **否** |
| B 零占位 | 29.99 | 0.00 | MISSING | **None** | None | **否** |
| C 零 landed（purchase 5.00 / landed 0.00） | 29.99 | 0.00 | MISSING | **None** | None | **否** |
| D 历史有效 v1 + 最新无效 v2 | 39.99 | 0.00 | MISSING | **None** | None | **否** |

计数：total=4, known=1, invalid=3（B/C/D 均有行且无效）, missing=3（overview 语义 = 无行+无效，非"仅无行"，测试 L291 已注释说明）。

**结论：任何路径都无法产出「售价 − 0 = 100% 毛利」。**

---

## 2. 前端验证（实机执行）

| 命令 | exit | errors | warnings | 说明 |
|---|---|---|---|---|
| `npm run typecheck` | 2 | **5** | — | 5 个全部为 pre-existing，位于未改动文件 |
| `npm run build`（vite build） | **0** | 0 | 1（chunk >500 kB，提示性，pre-existing） | 产物含 `ProductCostsPage-7WSEnwLG.js`（20.1 KB） |

5 个 pre-existing typecheck 错误（均已 `git diff --stat` 确认为 HEAD 未改动文件，非 v0.16 引入）：
- `ListingJobs.tsx(238,250)` — `'decision'` 不存在（Listing 模块，不在本次范围）
- `Logs.tsx(205)` — `Avatar` 未定义
- `MarketOpportunities.tsx(7)` — `TrendChartOutlined` 不存在
- `ProductCandidatesPage.tsx(834)` — `Element` 不可赋 `string`

**v0.16 范围内 0 新增 typecheck 错误。** 我修复了 ProductCostsPage.tsx 中 7 处 antd v6 兼容问题（`Divider.orientation`→`titlePlacement`、table column 移除已废弃的 `tooltip` 改用 `Tooltip` 包裹标题、`COST_FIELDS` 显式 `CostField` 类型让 `.required` 合法）。

> `npm run build` 不跑 tsc，故 typecheck 的历史错误不阻断 build。

---

## 3. Git（实机执行）

| 项 | 值 |
|---|---|
| `git diff --check`（提交前） | exit 2 —— 全部由 `docs/development_roadmap.md` 的 CRLF 行尾触发；归一化为 LF 后 exit **0** |
| `git diff --stat`（staged） | 12 files, 2550 insertions(+), 333 deletions(-) |
| 提交 | **SHA `f9e58b6929c7973b1d8998cc66acb017a3a3d193`（f9e58b6）** |
| 提交信息 | `feat(cost): v0.16 cost coverage governance` |
| 是否仅 v0.16 | ✅ 12 个文件全部为 P2-9 成本覆盖治理（3 backend + 1 test + 4 docs + 2 frontend + 1 audit + 1 design） |
| 排除的非 v0.16 文件（保持未暂存） | `main.py`（本地代理绕过）、`llm_gateway.py`/`newton_sourcing_storage.py`/`sourcing_service.py`（1688）、`index.css`/`NewtonSourcing.tsx`/`vite.config.{js,ts}`（本地开发） |

**重要披露**：`docs/development_roadmap.md` 在 HEAD 中行尾不一致（282 CRLF + 46 LF，而仓库其他文件全 LF），本轮将其归一化为 LF 并保留 UTF-8 BOM，使 `git diff --check` 通过。这是一次机械编码清理，真实内容变更仅 5 增 4 删（版本头、状态、P2-9 段落、changelog）。

---

## 4. 缺陷修复（本轮实机验证发现）

### 4.1 F-1 伪造毛利（High）—— 已修复并实机验证

`product_cost_service.py::_overview_row` 在 `cost is not None` 时无条件调用 `_margin(sale_price, cost)`，零成本占位行会算出 `29.99 − 0 = 100%` 毛利，与 `profit_analysis`（有门禁）口径矛盾。

`git show f9e58b6^` 证实**修复前无门禁**（`is_effective_cost` 出现 0 次，`**_margin(...)` 无条件展开）；修复后由 `if is_effective_cost(cost):` 门禁包裹。本提交新增 `is_effective_cost`/`cost_gap_reason`/`_latest_cost_sets`/`_item_gap_reason`/`list_product_cost_gaps`/`list_transaction_cost_gaps`/`batch_fill_product_costs`。

回归测试 `test_cost_overview_withholds_margin_for_invalid_cost` 通过，§1.1 实机取值确认 B/C/D 三态 margin 全为 None。

### 4.2 F-5 路由阴影（High，部署前置）—— 已修复

**`backend/app/api/v1/router.py` 中 `products.router`（含 `GET /products/{product_id}`）先于 `product_intelligence.product_router` 注册。Starlette 按注册顺序匹配，`GET /products/{product_id}` 模板先命中，导致以下 4 个字面端点永远返回 422（`product_id` 非合法 UUID）而非 200：**

- `GET /products/cost-overview`（既有端点，从未被 API 级测试覆盖 → 一直潜伏）
- `GET /products/cost-gaps`
- `GET /products/cost-gaps/transactions`
- `GET /products/procurement-suggestions`、`GET /products/low-stock`（同 prefix 的字面路径，同被阴影）

修复：把 `api_router.include_router(product_intelligence.product_router)` 前移到 `products.router` 之前（`router.py` L110 上方），并留注释。最小改动，不动任何业务逻辑。

**这是把 15 个未推送提交部署到生产前的前置必备项**（见 §5.2）。

---

## 5. 线上实机探测（第一轮无此能力）

探测时间 2026-09-30，全部只读，`X-Smoke-Test: nuotao-v016`。

| 组件 | 探测 | 结果 |
|---|---|---|
| Backend healthz | `GET /api/v1/healthz` | **200** `{"status":"ok"}` |
| Backend readyz | `GET /api/v1/readyz` | **200** `database=ok, redis=ok` |
| API docs | `GET /docs` | **404**（生产按 `settings.is_production` 关闭，符合设计） |
| OpenAPI | `GET /openapi.json` | **200** 1,053,460 bytes |
| WooCommerce 独立站 | `GET nuotaooutdoor.com` | **200**；`/wp-json` = "Nuotao Outdoor"，1.44 MB |
| LLM（OpenAI/DeepSeek） | `GET /v1/models` | **401**（网络可达，凭据未验证） |
| 1688 | `GET www.1688.com` | **200** |
| 后端 WC 桥 | `GET /api/v1/products/listing/status` | **200** |

### 5.1 生产当前运行 pre-v0.16 代码

`openapi.json` 证实：
- 生产有 `GET /api/v1/products/cost-overview`（200，含真实数据），但**无** `/cost-gaps`、`/cost-gaps/transactions`、`/cost-gaps/batch-fill`。
- `cost-overview` 响应 schema 无 `has_effective_cost`、无 `cost_gap_reason`、顶层计数只有 `known/missing/total`、无 `invalid` → **pre-v0.16 语义**。
- 生产**无** `GET /api/v1/products/{product_id}`（只有 `DELETE`）→ 这正是 F-5 在生产上未激活的原因。

生产 cost-overview 实测（limit=500）：`known=35, missing=28, total=63`，**0 个零填充成本行**（28 个 missing 是"无行"，不是"零行"）。所以 F-1 目前在生产上**未表现**——不存在伪造毛利数据。

### 5.2 本地与生产的差距（关键）

```
origin/main = c8c51139  （生产运行的基线）
本地 main   = f9e58b69  （领先 origin/main 15 个提交）
```

`git log origin/main..main` 列出 15 个未推送提交，**第 1 个 `cb629ac feat(product): add product workbench and decision cockpit` 引入了 `GET /products/{product_id}`**（生产上没有）。

**推论：若不先应用 F-5 路由修复，直接把这 15 个提交推到 main 触发 deploy，生产上 `cost-overview` / `cost-gaps` / `procurement-suggestions` / `low-stock` 会全部变 422。** 我的 f9e58b6 已含该修复，故 f9e58b6 是安全的部署形态。

---

## 6. Pilot Products（真实生产数据，非伪造）

从生产 `cost-overview`（63 个真实商品）按 P2-9 五类圈选，全部为线上真实 SKU：

| 类 | 真实 SKU | 关键值 | 说明 |
|---|---|---|---|
| A 成本完整 | `NEWTON_994387007112_0` | price 52.01 / purchase 1.65 / landed 27.84 / margin 15.82 | 有效且已定价，有真实运费 |
| D Landed 不完整 | `NEWTON_1069303098232_1` | price 10.68 / purchase 3.50 / landed 3.50 | `purchase==landed`，缺运费段 |
| E Rule/Risk（有成本无定价） | `NEWTON_972628402150_0` | purchase 22.50 / landed 22.50 / price None | 有成本行但无 meta 售价 |
| B 无成本行 | `NT-OUTDOOR-09281224` | price 45.00 / 无 ProductCost 行 | 真实 DTC 商品 |
| C Return Rate UNKNOWN | — | **生产 0 个零填充行** | 无法用真实数据演示；需先在 staging 构造 1 个 `purchase_cost>0 / landed=0` 行 |

生产实际分布：A 26 个、C(零占位) 0 个、E(有成本无定价) 9 个、B/D(无成本行) 28 个。

**禁止 fake 约束遵守**：上表全部取自线上真实 `cost-overview` 返回，无构造数据。C 类因生产无样本而诚实标注"未可用"，不用占位行冒充。

---

## 7. 发现与阻塞项

### 7.1 已修复（本提交 f9e58b6）

| # | 严重度 | 问题 | 修复 |
|---|---|---|---|
| F-1 | **High** | 总览表对零成本行算出「售价 − 0 = 100% 毛利」，与 `profit_analysis` 矛盾 | `_overview_row` 增加 `is_effective_cost` 门禁 + 回归测试，实机四态验证 |
| F-5 | **High（部署前置）** | `GET /products/{product_id}` 阴影 4+ 个字面端点 → 422 | `router.py` 前移 `product_intelligence.product_router`，注释说明 |

### 7.2 建议但未实施（本阶段不开发新功能）

| # | 问题 | 建议 |
|---|---|---|
| F-2 | `ProductCostUpsertRequest` 金额字段 `ge=0`，API 可接受全零成本（含批量补齐），持续产生无效行 | 成本录入/批量补齐入口加 `purchase_cost > 0` 服务端校验（需产品决策：是否允许占位录入） |
| F-4 | `.github/workflows/` 58 个 workflow 中约 34 个为 `debug-*` / `fix-staging-*` 事故遗留 | 择窗口清理，减少误触发与维护面 |
| F-6 | `docs/development_roadmap.md` 行尾在 HEAD 中不一致（282 CRLF + 46 LF） | 本轮已随 v0.16 提交归一化为 LF（披露于 §3） |

### 7.3 阻塞项（触发停止条件）

1. **无法推送** —— `credential.helper=manager` 需交互式浏览器、无 `GH_TOKEN`，本地 main 领先 origin/main 15 个提交，**我（本会话）不能完成 `git push` → 不能触发 staging/production 部署**。
2. **Staging 未部署** —— v0.16 未进入 staging，7 步链未跑。
3. **生产仍 pre-v0.16** —— 实机探测证实；Production Verified 仅能证明旧基线可用，未验证 v0.16 代码。

> 这三项均属"需用户/运维执行"的部署动作，不是代码缺陷。代码侧已就绪。

---

## 8. 是否允许进入 20-product rollout

# ❌ 不允许（STOP）。

| 前置条件 | 状态 |
|---|---|
| Code Ready | ✅（测试全绿、build 0、0 新增 type 错误） |
| Environment Ready | ✅（七组件实机可达，LLM/1688 凭据未验证） |
| Staging Verified | ❌ 未部署未验证 |
| Production Verified | ⚠️ 仅验证 pre-v0.16 基线 |

**四项必须全绿方可 rollout；Staging Verified 未满足 → 按停止条件终止。**

### 8.1 解除阻塞的最短路径（供用户/运维执行）

```bash
# 1. 推送（需有凭据的机器或交互式 credential manager）
git push origin main            # 触发 deploy.yml（staging-gated）

# 2. 部署链
#    deploy.yml            → staging 阶段校验
#    db-migration-and-scheduler.yml  （本轮无新迁移，仍跑以确认 head 一致）
#    post-deploy-verify.yml

# 3. staging 跑 7 步链（在 staging 环境）
#    Product → Product Cost → Landed Cost → Profit Analysis
#    → Cost Gap → Batch Fill → Audit Event
#    每步记录 HTTP 状态 / 结果 / trace_id / event / 失败点

# 4. 生产 smoke（已在 §5 完成 pre-v0.16 基线探测；部署后重探）
#    Backend / Frontend / PostgreSQL / Redis / WooCommerce / LLM / 1688

# 5. 四门禁全绿后 → 20-product rollout
```

### 8.2 部署前必读（风险）

- **必须先含 F-5 路由修复**（f9e58b6 已含）—— 否则 15 个未推送提交上线会弄坏生产 4+ 端点。
- 生产当前 0 个零填充成本行，F-1 未表现；但 F-5 一旦激活（部署 v0.15 时代代码）就会表现，**必须随同一批上线**。
- 无新数据库迁移，部署面为纯代码。
- 前端 typecheck 有 5 个 pre-existing 错误（非 v0.16）；`vite build` 不含 tsc，不阻断。建议后续单独清掉。

---

## 附录 A：本轮实际完成的工作

| 工作 | 结果 |
|---|---|
| 实机跑 4 条第一阶段测试命令 | 18/18、25/25、951 收集、全量 exit 0（覆盖本地 .env 调度器开关后） |
| 实机打印 F-1 四态真实取值 | §1.1 表格，全部 FAKE=false |
| 修复 F-1 门禁（经 `git show f9e58b6^` 确认提交前无门禁） | `is_effective_cost` 门禁 + 回归测试 |
| 修复 F-5 路由阴影 | `router.py` 前移 + 注释 |
| 修复 ProductCostsPage 7 处 antd v6 兼容 | `titlePlacement` / `Tooltip` 包裹 / `CostField` 类型 |
| 实机探测生产 8 项 | §5 全表 |
| 实机圈定真实 Pilot Products | §6，5 类（C 类诚实标注生产无样本） |
| 提交 v0.16 | SHA f9e58b6929c7973b1d8998cc66acb017a3a3d193 |

## 附录 B：本会话未执行、需用户/运维执行的

- `git push` → 触发 `deploy.yml`（staging）→ `db-migration-and-scheduler.yml` → `post-deploy-verify.yml`
- staging 7 步链实跑与逐条记录
- 部署后生产重探（含 v0.16 端点 `cost-gaps` / `cost-gaps/transactions` / `batch-fill` 首次可达）
- LLM / 1688 真实凭据验证（401 仅证明网络可达）
- 20-product rollout
