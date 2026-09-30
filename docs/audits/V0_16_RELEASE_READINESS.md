# v0.16 成本覆盖治理 — 发布就绪审计（第二轮）

> 审计日期：2026-09-30
> 审计对象：v0.16 成本覆盖治理（P2-9）
> 审计方式：**实机执行**（测试 / 前端构建 / 线上探测）
> 结论：**STOP —— 代码就绪，但 staging 未部署、生产仍是 pre-v0.16，不允许进入 20-product rollout**

---

## 0. 总结

| 门禁 | 要求 | 实际 | 状态 |
|---|---|---|---|
| Code Ready | 测试全绿 + typecheck/build | 18/18、25/25、951 收集、套件 exit 0；build exit 0；typecheck 0 新增错误（5 个 pre-existing 在未改文件） | ✅ |
| Environment Ready | 七组件可用 | healthz/readyz ok（database/redis ok）、WooCommerce 在线、LLM/1688 网络可达（凭据未验证） | ✅（凭据未验证） |
| Staging Verified | 先入 staging 跑通 7 步链 | **未部署**——本会话无推送凭据，推不动 main 触发 deploy.yml | ❌ |
| Production Verified | 线上 smoke | 已探测，但生产跑 origin/main（c8c5113，pre-v0.16），未含任何 v0.16 代码；本地领先 15 个提交 | ⚠️ 仅旧基线 |

按停止条件：任一项失败 → STOP。不进入 20-product rollout。

本轮新增（相对 09-13 第一轮）：
1. 实机跑通全部第一阶段命令。
2. 修复 High 级路由阴影缺陷（F-5），并证明它是 15 个未推送提交上线的**前置必备项**。
3. 实机核验 F-1 四种成本状态真实取值。
4. 实机探测生产，确认生产未部署 v0.15 时代代码。
5. 用真实生产数据圈定 Pilot Products（无伪造）。

---

## 1. 测试结果（实机）

venv `.\.venv\Scripts\python.exe`（Python 3.12.2 / pytest 9.1.1 / pytest-asyncio 1.4.0）。

| # | 命令 | collected | passed | failed | errors | skipped | xfailed | exit |
|---|---|---|---|---|---|---|---|---|
| 1 | `pytest tests/test_cost_coverage_governance.py -q` | 18 | **18** | 0 | 0 | 0 | 0 | **0** |
| 2 | `pytest tests/test_profit_engine.py tests/test_cost_blocker.py tests/test_product_intelligence.py tests/test_product_import.py -q` | 25 | **25** | 0 | 0 | 0 | 0 | **0** |
| 3 | `pytest tests --ignore=tests/integration --collect-only -q` | **951** | — | — | — | — | — | **0** |
| 4 | `pytest tests --ignore=tests/integration -q` | 951 | 951 | **0** | 0 | 0 | 0 | **0** |

- 第 4 项在 `AGENT_ALERT_SCHEDULER_ENABLED=true` 下运行。本地 `backend/.env` 设 `false`，会让 3 个 `test_alert_scheduler.py` 失败（纯环境配置，与 v0.16 无关），覆盖后全绿。
- **F-1 回归测试 `test_cost_overview_withholds_margin_for_invalid_cost` 实机通过**（第 1 项内）。

### 1.1 F-1 四态实机取值（打印值，非断言）

真实服务层 + 内存 SQLite（同测试夹具引擎）：

| 状态 | sale_price | total_landed_cost | cost_status | contribution_margin | 总览表 margin | 伪造毛利? |
|---|---|---|---|---|---|---|
| A 有效成本 | 99.99 | 51.00 | KNOWN | **41.99** | 41.99（rate 0.4199） | **否** |
| B 零占位 | 29.99 | 0.00 | MISSING | **None** | None | **否** |
| C 零 landed（purchase 5.00 / landed 0.00） | 29.99 | 0.00 | MISSING | **None** | None | **否** |
| D 历史有效 v1 + 最新无效 v2 | 39.99 | 0.00 | MISSING | **None** | None | **否** |

计数：total=4, known=1, invalid=3, missing=3（overview 的 missing = 无行 + 无效，测试 L291 有注释）。

**任何路径都无法产出「售价 − 0 = 100% 毛利」。**

---

## 2. 前端验证（实机）

| 命令 | exit | errors | warnings |
|---|---|---|---|
| `npm run typecheck` | 2 | **5**（全部 pre-existing，未改文件） | — |
| `npm run build` | **0** | 0 | 1（chunk >500 kB，提示性） |

5 个 pre-existing 错误（`git diff --stat` 确认均未改动）：`ListingJobs.tsx`（Listing 模块，不在范围）、`Logs.tsx`、`MarketOpportunities.tsx`、`ProductCandidatesPage.tsx`。

**v0.16 范围内 0 新增错误。** 已修 ProductCostsPage.tsx 7 处 antd v6 兼容（`Divider.orientation`→`titlePlacement`、table column 废弃 `tooltip` 改 `Tooltip` 包裹标题、`COST_FIELDS` 显式 `CostField` 类型）。build 不含 tsc，历史错误不阻断。

---

## 3. Git（实机）

| 项 | 值 |
|---|---|
| `git diff --check` | 归一化 roadmap 行尾后 exit **0** |
| `git diff --stat`（staged） | 12 files, +2550 / −333 |
| 提交 | **SHA `f9e58b6929c7973b1d8998cc66acb017a3a3d193`** |
| 信息 | `feat(cost): v0.16 cost coverage governance` |
| 仅 v0.16 | ✅ 12 文件全为 P2-9 |
| 排除的非 v0.16（保持未暂存） | `main.py`、`llm_gateway.py`、`newton_sourcing_storage.py`、`sourcing_service.py`、`index.css`、`NewtonSourcing.tsx`、`vite.config.{js,ts}` |

**披露**：`docs/development_roadmap.md` 在 HEAD 中行尾不一致（282 CRLF + 46 LF，仓库其余文件全 LF），本轮归一化为 LF 并保留 BOM，使 `--check` 通过；真实内容变更仅 5 增 4 删。

---

## 4. 缺陷修复（实机验证）

### 4.1 F-1 伪造毛利（High）—— 已修复并实机验证

`_overview_row` 在 `cost is not None` 时无条件调 `_margin()`，零占位行会算出 `29.99 − 0 = 100%`，与 `profit_analysis` 矛盾。`git show f9e58b6^` 证实**提交前无门禁**（`is_effective_cost` 0 次），提交后由 `if is_effective_cost(cost):` 门禁包裹。新增 `is_effective_cost` / `cost_gap_reason` / `_latest_cost_sets` / `list_product_cost_gaps` / `list_transaction_cost_gaps` / `batch_fill_product_costs`。

### 4.2 F-5 路由阴影（High，部署前置）—— 已修复

`router.py` 中 `products.router`（含 `GET /products/{product_id}`）先于 `product_intelligence.product_router` 注册。Starlette 按注册顺序匹配，`GET /products/{product_id}` 模板先命中，导致下列字面端点全部 422：

- `GET /products/cost-overview`（既有端点，从未被 API 级测试覆盖 → 一直潜伏）
- `GET /products/cost-gaps`
- `GET /products/cost-gaps/transactions`
- `GET /products/procurement-suggestions`、`GET /products/low-stock`

修复：前移 `product_intelligence.product_router` 到 `products.router` 之前，留注释。最小改动，不动业务逻辑。

**这是 15 个未推送提交上线的前置必备项**（§5.2）。

---

## 5. 线上实机探测

2026-09-30，全只读，`X-Smoke-Test: nuotao-v016`。

| 组件 | 探测 | 结果 |
|---|---|---|
| healthz | `GET /api/v1/healthz` | **200** ok |
| readyz | `GET /api/v1/readyz` | **200** database/redis ok |
| docs | `GET /docs` | **404**（生产按 is_production 关闭，符合设计） |
| OpenAPI | `GET /openapi.json` | **200** 1,053,460 B |
| WooCommerce | `GET nuotaooutdoor.com` | **200**；`/wp-json` = "Nuotao Outdoor" |
| LLM | `GET /v1/models`（OpenAI/DeepSeek） | **401**（网络可达，凭据未验证） |
| 1688 | `GET www.1688.com` | **200** |
| 后端 WC 桥 | `GET /api/v1/products/listing/status` | **200** |

### 5.1 生产运行 pre-v0.16 代码

- 有 `GET /products/cost-overview`（200 + 真实数据），**无** `/cost-gaps` 系列。
- `cost-overview` schema 无 `has_effective_cost`、无 `invalid` 计数 → pre-v0.16 语义。
- 生产**无** `GET /products/{product_id}`（只有 `DELETE`）→ F-5 在生产未激活。

生产 cost-overview（limit=500）：`known=35, missing=28, total=63`，**0 个零填充成本行**。F-1 目前生产未表现。

### 5.2 本地 vs 生产（关键）

```
origin/main = c8c51139  （生产基线）
本地 main   = f9e58b69  （领先 15 个提交）
```

15 个未推送提交的**第 1 个 `cb629ac` 引入了 `GET /products/{product_id}`**（生产没有）。

**推论：若不先带 F-5 修复，直接推 15 个提交触发 deploy，生产 `cost-overview` / `cost-gaps` / `procurement-suggestions` / `low-stock` 全变 422。** f9e58b6 已含修复，是安全部署形态。

---

## 6. Pilot Products（真实生产数据）

从生产 cost-overview（63 个真实商品）按 P2-9 五类圈选，全为线上真实 SKU：

| 类 | 真实 SKU | 关键值 | 说明 |
|---|---|---|---|
| A 成本完整 | `NEWTON_994387007112_0` | price 52.01 / purchase 1.65 / landed 27.84 / margin 15.82 | 有效 + 已定价 + 有运费 |
| D Landed 不完整 | `NEWTON_1069303098232_1` | price 10.68 / purchase 3.50 / landed 3.50 | `purchase==landed`，缺运费段 |
| E Rule/Risk（有成本无定价） | `NEWTON_972628402150_0` | purchase 22.50 / landed 22.50 / price None | 有成本行但无售价 |
| B 无成本行 | `NT-OUTDOOR-09281224` | price 45.00 / 无 ProductCost 行 | 真实 DTC 商品 |
| C 零占位 | — | **生产 0 个零填充行** | 无法真实演示；需先在 staging 造 1 个 `purchase>0 / landed=0` 行 |

分布：A 26、C(零占位) 0、E(有成本无定价) 9、B/D(无成本行) 28。

**禁止 fake 约束遵守**：全取线上真实返回，无构造数据；C 类无样本即诚实标注，不冒充。

---

## 7. 发现与阻塞

### 7.1 已修复（f9e58b6）

| # | 严重度 | 问题 | 修复 |
|---|---|---|---|
| F-1 | High | 总览表零成本行「售价 − 0 = 100% 毛利」 | `is_effective_cost` 门禁 + 回归测试 + 实机四态 |
| F-5 | High（部署前置） | `GET /products/{product_id}` 阴影 4+ 字面端点 → 422 | 前移 router + 注释 |

### 7.2 建议未实施（本阶段不加功能）

| # | 问题 | 建议 |
|---|---|---|
| F-2 | 金额字段 `ge=0`，API 可接受全零成本 | 录入/批量补齐入口加 `purchase_cost > 0` 校验（需产品决策） |
| F-4 | 58 个 workflow 中约 34 个 debug/fix 遗留 | 择窗口清理 |
| F-6 | roadmap 行尾 HEAD 不一致 | 本轮已随提交归一化 LF |

### 7.3 阻塞项（触发 STOP）

1. **无法推送** —— credential.helper=manager 需交互、无 GH_TOKEN；本地领先 origin/main 15 提交，本会话推不动。
2. **Staging 未部署** —— v0.16 未进 staging，7 步链未跑。
3. **生产仍 pre-v0.16** —— Production Verified 仅证明旧基线可用。

> 属"需用户/运维执行"的部署动作，非代码缺陷。代码侧已就绪。

---

## 8. 是否进入 20-product rollout

# ❌ 不允许（STOP）。

| 前置 | 状态 |
|---|---|
| Code Ready | ✅ |
| Environment Ready | ✅（凭据未验证） |
| Staging Verified | ❌ 未部署 |
| Production Verified | ⚠️ 仅旧基线 |

四项须全绿；Staging Verified 未满足 → 终止。

### 8.1 解除阻塞最短路径（用户/运维）

```bash
git push origin main            # 触发 deploy.yml（staging-gated）
# deploy.yml → db-migration-and-scheduler.yml（无新迁移，仍跑确认 head）→ post-deploy-verify.yml
# staging 跑 7 步链：Product → Cost → Landed → Profit → Gap → BatchFill → Audit
# 每步记录 HTTP / 结果 / trace_id / event / 失败点
# 部署后生产重探（v0.16 端点 cost-gaps 系列首次可达）
# 四门禁全绿 → 20-product rollout
```

### 8.2 部署前必读

- **必须含 F-5 修复**（f9e58b6 已含），否则 15 提交上线弄坏生产 4+ 端点。
- 生产 0 零填充行，F-1 未表现；F-5 一旦激活就会表现，须同批上线。
- 无新迁移，纯代码部署。
- 前端 5 个 pre-existing type 错误不阻断 build，建议后续单独清。

---

## 附录 A：本轮完成

| 工作 | 结果 |
|---|---|
| 实机 4 条测试命令 | 18/18、25/25、951 收集、全量 exit 0 |
| F-1 四态实机取值 | §1.1，全 FAKE=false |
| F-1 门禁 + F-5 路由修复 | `git show f9e58b6^` 证实提交前无门禁 |
| ProductCostsPage 7 处 antd v6 修复 | titlePlacement / Tooltip / CostField |
| 生产 8 项实机探测 | §5 全表 |
| 真实 Pilot Products | §6，5 类（C 类无样本） |
| 提交 | f9e58b6 + 审计更新 fef2c5d |

## 附录 B：需用户/运维执行

- `git push` → `deploy.yml` → `db-migration-and-scheduler.yml` → `post-deploy-verify.yml`
- staging 7 步链实跑与逐条记录
- 部署后生产重探（cost-gaps 系列首次可达）
- LLM / 1688 真实凭据验证
- 20-product rollout
