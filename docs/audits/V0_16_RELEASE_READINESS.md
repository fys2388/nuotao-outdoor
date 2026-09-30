# v0.16 Cost Coverage Governance — Release Readiness Audit

> 审计日期：2026-09-13
> 审计对象：v0.16 成本覆盖治理（P2-9）
> 审计方式：**静态代码审查**（执行器不可用，见 §1）
> 结论：**STOP — 不允许进入 20-product rollout**

---

## 0. 总结（Executive Summary）

| 门禁 | 要求 | 实际 | 状态 |
|---|---|---|---|
| Code Ready | 测试全绿 | 未执行（shell 不可用） | ❌ 未满足 |
| Environment Ready | Backend/PG/Redis/WC/LLM/1688 可用 | 未执行（无网络探测能力） | ❌ 未满足 |
| Staging Verified | v0.16 先入 staging 并跑通 7 步链 | 未执行（无 shell/SSH/git） | ❌ 未满足 |
| Production Verified | smoke test | 未执行 | ❌ 未满足 |

**四个门禁零满足。** 按停止条件，流程终止。不进入 20-product rollout。

本次审计虽无法执行任何命令，但**静态审查发现并修复了 1 个伪造毛利漏洞**（详见 §5.3），并把成本治理测试从 17 项扩到 18 项。

---

## 1. 测试结果 —— 未执行

### 1.1 阻塞原因

命令执行器在本环境完全不可用。同一错误在 4 次尝试中 100% 复现：

| 尝试 | 方式 | 结果 |
|---|---|---|
| 1 | `pwsh` 前台，workdir=`E:\AI\nuotao-ai-os` | `SetNamedSecurityInfoW failed (Win32 5): grantWrite(E:\AI\nuotao-ai-os)` |
| 2 | `pwsh` 前台，workdir=`C:\temp` | 同上（错误仍指向 workspace） |
| 3 | `pwsh` 前台，`sandbox_permissions=workspace-write` | 同上 |
| 4 | `pwsh` 后台作业 `pwsh-9` | 同上 |

错误发生在工具初始化阶段，**在任何命令执行之前**，因此 workdir、绝对路径、后台执行均无法绕过。

### 1.2 要求的记录项 —— 全部无法提供

| 项目 | 值 |
|---|---|
| collected | **无法提供** |
| passed | **无法提供** |
| failed | **无法提供** |
| errors | **无法提供** |
| skipped | **无法提供** |
| xfailed | **无法提供** |
| exit code | **无法提供** |

### 1.3 测试资产（已静态核实存在）

- `backend/tests/test_cost_coverage_governance.py`：**18 个测试函数**
- 结构检查：`grep -n "@pytest.mark.skip\|xfail\|pytestmark"` 无匹配 —— **无 skip、无 xfail、无跳过标记**，符合「禁止删除/skip 测试」
- 相关 cost/profit/product 测试文件均存在：
  `test_profit_engine.py`、`test_cost_blocker.py`、`test_product_intelligence.py`、
  `test_product_import.py`、`test_intelligence_completeness.py`、`test_product_context.py`、
  `test_candidate_approval_requires_pricing.py`、`test_dashboard_profit_snapshot.py`、
  `test_nuotao_score_v3.py`、`test_decision_read_model.py`、`test_decision_write_model.py`、
  `test_consolidation.py`、`test_currency_service.py`
- 测试总数：`backend/tests/` 下 107 个 `.py` 文件（含 `integration/` 15 个）

### 1.4 待执行的命令（按原始要求原样保留）

```bash
cd backend
python -m pytest tests/test_cost_coverage_governance.py -q
python -m pytest tests/test_profit_engine.py tests/test_cost_blocker.py tests/test_product_intelligence.py tests/test_product_import.py -q
python -m pytest tests --ignore=tests/integration --collect-only -q
python -m pytest tests --ignore=tests/integration -q
```

> 前两轮审计已确认：`list_cost_overview` 无测试调用方（`grep` 仅命中本文件 + 端点），`profit_analysis` 亦无现有测试调用 —— 本次门禁改动不会破坏既有测试。

---

## 2. 前端验证 —— 未执行

### 2.1 阻塞原因

同 §1.1，`typecheck` / `build` 依赖 node/npm，需 shell 执行。

### 2.2 静态检查结果（可执行的部分）

| 检查项 | 方法 | 结果 |
|---|---|---|
| 导入完整性 | 逐个 grep `ProductCostsPage.tsx` 全部 import 符号的使用位置 | ✅ 全部被使用，无 unused import（`noUnusedLocals` 风险） |
| `Alert` / `Divider` / `Empty` / `Statistic` / `Tooltip` / `Descriptions` / `Segmented` | 使用位置 | ✅ 均出现 |
| 7 个 icon 符号 | `DollarOutlined` `EditOutlined` `LineChartOutlined` `ReloadOutlined` `SearchOutlined` `WalletOutlined` `WarningOutlined` | ✅ 均出现 |
| 4 个 hook | `useCallback` `useEffect` `useMemo` `useState` | ✅ 均出现 |
| `ColumnsType` / `Table` | 3 处 columns 定义（`columns` `gapColumns` `txColumns`） | ✅ 一致 |
| `ApiError` | `apiErrorMessage()` 类型守卫 | ✅ 使用 |
| 组件树闭合 | 逐段阅读 1164 行 JSX（L699–L1164） | ✅ 无明显未闭合标签 |
| API 契约对齐 | `getCostGaps` / `getTransactionCostGaps` / `batchFillCosts` ↔ 后端 `/cost-gaps` 三端点 | ✅ 一致 |
| 空值渲染 | 利润抽屉 L1063–L1088 | ✅ 全部 `null` → `'—'`，不渲染数字 |

> **结论：静态层面未发现 TypeScript error 或 build error 迹象，但这不是 typecheck/build 通过。** 必须由执行器实际验证。

---

## 3. Staging —— 未执行

v0.16 **未进入 staging**。原因：

1. 无 shell → 无法运行 `deploy.yml` / `db-migration-and-scheduler.yml`
2. 无 git 提交 → 无可部署的 commit（本轮及前两轮均未提交）
3. 无 SSH/远端访问能力 → 无法连接 `95.217.218.178`

### 要求的 7 步链路验证状态

| 步骤 | 状态 |
|---|---|
| Product | ❌ 未验证 |
| Product Cost | ❌ 未验证 |
| Landed Cost | ❌ 未验证 |
| Profit Analysis | ❌ 未验证（仅静态确认门禁存在） |
| Cost Gap | ❌ 未验证 |
| Batch Fill | ❌ 未验证 |
| Audit Event | ❌ 未验证 |

### batch-fill 关键属性（静态确认，未运行）

| 属性 | 静态确认 |
|---|---|
| 逐项 savepoint | ✅ `batch_fill_product_costs` 对每个 item 使用独立事务边界，异常捕获后继续 |
| event_log | ✅ 每个成功 item 写 `event_log` + 批次汇总事件 |
| 失败不污染其他产品 | ✅ 异常在 per-item 边界内捕获，`success`/`error` 分离返回 |

---

## 4. Production —— 未执行

**未执行任何线上探测。**

按审计要求：「不要把『仓库配置正确』当成『线上服务可用』」。本审计严格遵守 —— 以下是仓库中记录的配置事实，**不代表线上状态**：

| 组件 | 仓库记录的配置 | 线上可用性 |
|---|---|---|
| Backend | `/opt/nuotao/backend/`，systemd `nuotao-backend.service` | ⚠️ 未探测 |
| Frontend | `/var/www/nuotao-console/` | ⚠️ 未探测 |
| PostgreSQL | PostgreSQL 16 | ⚠️ 未探测 |
| Redis | Redis 5.0+（Stream） | ⚠️ 未探测 |
| WooCommerce | `nuotaooutdoor.com` | ⚠️ 未探测 |
| LLM | LiteLLM，DeepSeek 主 / OpenAI 备 | ⚠️ 未探测 |
| 1688 | 集成模块 | ⚠️ 未探测 |

域名：`nuotaooutdoor.com`（独立站）、`admin.nuotaooutdoor.com`（API + 控制台）、`https://admin.nuotaooutdoor.com/docs`。

---

## 5. 成本治理验证（四种成本状态）

静态代码审查确认四种状态的处理路径。源码位置均已逐行核对。

### 5.1 有效成本（purchase_cost > 0 且 total_landed_cost > 0）

- `is_effective_cost()` → `True`（`product_cost_service.py:145-149`）
- `profit_analysis` → `cost_status = "KNOWN"`，正常计算 margin（L549 门禁通过）
- 总览表 → `has_effective_cost = True`，计算 `contribution_margin`（本次修复后，见 §5.3）
- 测试：`test_profit_analysis_computes_margin_for_effective_cost`、`test_cost_overview_withholds_margin_for_invalid_cost`（对照断言）

### 5.2 purchase_cost > 0 但 Landed Cost 不完整

**重要发现：该状态无法通过 API 产生。** `landed_breakdown` 计算
`total_landed_cost = purchase_cost + domestic_shipping + international + packaging + tax_estimate + handling`，
`purchase_cost > 0` 时 `total_landed_cost` 必然 `> 0`。

该状态**只能由直接 DB 写入/历史遗留数据产生**。若存在：
- `cost_gap_reason` → `"invalid_zero_landed"`（L164-165）
- `is_effective_cost` → `False`（`total_landed_cost` 不满足 `> 0`）
- `profit_analysis` → `MISSING`，margin 全部 `None`
- 测试：`test_invalid_zero_landed_classification`（直接构造 purchase_cost=5、total_landed_cost=0）

### 5.3 修复：total_landed_cost = 0 时总览表伪造毛利 ✅ 已修复

**审计发现的真实漏洞** —— 正是要求阻止的「售价 − 0 = 虚假毛利」：

修复前 `_overview_row`（`list_cost_overview`，即 `/cost-overview` 主表）在 `cost is not None` 时**无条件**调用 `_margin()`：

```python
    if cost is not None:
        row.update({
            ...,
            **_margin(sale_price, cost),   # ← 无 is_effective_cost 门禁
        })
```

零成本占位行（`purchase_cost=0`、`total_landed_cost=0`）会算出：

```
contribution_margin = 29.99 - 0 = 29.99
margin_rate = 1.0  (100%)
```

而 `profit_analysis`（L549）已有门禁 → `MISSING`。**两张表面口径矛盾**：利润抽屉显示「缺成本 / —」，总览表却显示「100% 毛利」。

修复后：

```python
        # P2-9: an invalid (zero) cost row must never yield a derived margin -
        # the same withholding rule as profit_analysis.
        if is_effective_cost(cost):
            row.update(_margin(sale_price, cost))
```

新增回归测试 `test_cost_overview_withholds_margin_for_invalid_cost`，断言无效行
`sale_price=29.99` 且 `contribution_margin is None`、`margin_rate is None`；
对照断言有效行 margin 非空。

### 5.4 历史有效成本 + 当前无效成本

- `latest_cost_for_product` 按 `valid_from DESC` 取最新 → 返回无效行
- `_latest_cost_sets` 使用同一「每商品最新一行」逻辑 → 计数器、过滤器、缺口清单三者口径一致
- `profit_analysis` → `MISSING`，margin 全部 `None`，`breakeven_price = 0`
- 测试：`test_newest_row_wins`

### 5.5 状态矩阵汇总

| # | 状态 | 可否产生 | `is_effective_cost` | `cost_gap_reason` | `profit_analysis.margin` | 总览表 margin | 覆盖计数 |
|---|---|---|---|---|---|---|---|
| 1 | 有效成本 | API 正常路径 | `True` | `None` | 正常计算 | 正常计算 | known |
| 2 | purchase>0 / landed=0 | 仅直接 DB 写入 | `False` | `invalid_zero_landed` | `None`（withhold） | `None` | invalid |
| 3a | 全零占位行 | API 允许（`ge=0`） | `False` | `invalid_zero_purchase` | `None`（withhold） | `None` | invalid |
| 3b | 完全无成本行 | — | `False` | `missing` | `None`（withhold） | `None` | missing |
| 4 | 历史有效 + 当前无效 | API 可产生 | `False`（取最新） | 按最新行 | `None`（withhold） | `None` | invalid |

**伪造毛利确认**：修复后不存在任何路径能产出「售价 − 0」的毛利。`profit_analysis` 与总览表门禁一致。

---

## 6. Pilot Products —— 未准备

要求准备 3–5 个真实 Pilot Products，覆盖 A–E 五类。**未准备任何产品。** 原因：

1. 无 shell → 无法写数据库、无法调用 1688
2. 无法访问 staging/prod → 无处写入
3. 无真实 1688 凭据在本会话内可用

按「只做真实数据，禁止 fake supplier / fake cost / fake market data / fake AI result」的要求，在无法访问真实数据源的前提下**不构造任何占位产品**。

| 分类 | 要求 | 状态 |
|---|---|---|
| A. 成本完整 | 真实商品 | ❌ 未准备 |
| B. Supplier 信息部分缺失 | 真实商品 | ❌ 未准备 |
| C. Return Rate UNKNOWN | 真实商品 | ❌ 未准备 |
| D. Landed Cost 不完整 | 真实商品 | ❌ 未准备 |
| E. Rule UNKNOWN / Risk | 真实商品 | ❌ 未准备 |

---

## 7. 发现与阻塞项

### 7.1 已修复（本次审计内）

| # | 严重度 | 问题 | 修复 |
|---|---|---|---|
| F-1 | **High** | `/cost-overview` 主表对零成本行计算「售价 − 0 = 100% 毛利」，与 `profit_analysis` 口径矛盾 —— 正是 P2-9 要消除的伪造毛利 | `product_cost_service.py` `_overview_row` 增加 `is_effective_cost` 门禁 + 新增回归测试 |

### 7.2 建议但未实施（本阶段不开发新功能）

| # | 问题 | 建议 |
|---|---|---|
| F-2 | `ProductCostUpsertRequest` 所有金额字段 `ge=0`，API 可接受全零成本（含批量补齐），持续产生无效行 | 在成本录入/批量补齐入口增加 `purchase_cost > 0` 服务端校验（需产品决策：是否允许占位录入） |
| F-3 | 1688 ACL 未解决 —— 执行器 `grantWrite(E:\AI\nuotao-ai-os)` 失败，本环境无法执行任何命令 | 修复工作区写权限（属环境层问题，非代码问题）。这是本轮所有执行类验证的根因 |
| F-4 | `.github/workflows/` 下 58 个 workflow 中约 34 个为 `debug-*` / `fix-staging-*` 事故排查遗留 | 择窗口清理，减少 CI 维护面与误触发风险 |

### 7.3 阻塞项（触发停止条件）

1. **执行器不可用** —— 无法运行 pytest / typecheck / build / 部署脚本（§1.1）
2. **无 git 提交** —— v0.16 无任何 commit，无可部署产物
3. **staging 未执行** —— v0.16 未进入 staging
4. **production smoke test 未执行**
5. **1688/环境 ACL 未解决** —— 触发用户定义的停止条件

---

## 8. 是否允许进入 20-product rollout

# ❌ 不允许。

| 前置条件 | 状态 |
|---|---|
| Code Ready | ❌ 测试未执行 |
| Environment Ready | ❌ 七组件均未探测 |
| Staging Verified | ❌ 未部署未验证 |
| Production Verified | ❌ 未探测 |

四个条件全部未满足，**流程按停止条件终止**。

### 8.1 解除阻塞的最短路径

```bash
# 步骤 1：修复执行环境（grantWrite 失败）—— 其余全部依赖此步
# 步骤 2：后端验证
cd backend
python -m pytest tests/test_cost_coverage_governance.py -q
python -m pytest tests/test_profit_engine.py tests/test_cost_blocker.py tests/test_product_intelligence.py tests/test_product_import.py -q
python -m pytest tests --ignore=tests/integration --collect-only -q
python -m pytest tests --ignore=tests/integration -q
# 步骤 3：前端验证
cd ../frontend && npm run typecheck && npm run build
# 步骤 4：提交并部署至 staging
git add -A && git commit -m "feat(cost): v0.16 cost coverage governance"
# 触发 db-migration-and-scheduler.yml（本次无新迁移）→ post-deploy-verify.yml
# 步骤 5：staging 跑通 7 步链路（Product → Cost → Landed → Profit → Gap → BatchFill → Audit）
# 步骤 6：production smoke test（Backend/Frontend/PostgreSQL/Redis/WooCommerce/LLM/1688）
# 步骤 7：四门禁全绿后方可进入 20-product rollout
```

### 8.2 风险说明

- v0.16 **无新数据库迁移**（全部派生字段，复用 `product_cost` / `product_cost_snapshots` / `event_log` / `orders` / `order_items`），部署面小
- 但 **F-1 是 High 级伪造毛利漏洞**，必须在测试通过后才可发布；未测试前不得部署
- 本次修复与新增测试均**未通过实际运行验证**

---

## 附录 A：本次审计实际完成的工作

| 工作 | 结果 |
|---|---|
| 4 次探测执行器（前台×3 + 后台×1） | 全部 `grantWrite` ACL 失败 |
| 逐行静态审查 `_overview_row` / `profit_analysis` / `_latest_cost_sets` / `list_cost_overview` / `list_product_cost_gaps` / `list_transaction_cost_gaps` | 发现 F-1 |
| 修复 F-1 + 新增回归测试 | `product_cost_service.py` + `test_cost_coverage_governance.py`（17→18 项） |
| 静态核验四种成本状态处理路径 | 见 §5.5 矩阵 |
| 静态核验前端导入完整性与空值渲染 | 1164 行 JSX 无 unused import、null 渲染正确 |
| 确认测试资产完整性 | 18 个测试函数，无 skip / xfail |
| 创建本审计报告 | `docs/audits/V0_16_RELEASE_READINESS.md` |

## 附录 B：本审计未执行的事项（诚实声明）

- pytest（任何 target）
- `npm run typecheck` / `npm run build`
- git 提交
- staging 部署与验证
- production smoke test
- Pilot Product 数据准备
- 1688 → Product Candidate → AI Analysis → Cost → Supply Chain → Rule → Decision → Product Master → Listing → WooCommerce 全链路验证

以上均需可执行的 shell / 远端访问 / 真实凭据，本会话不具备。
