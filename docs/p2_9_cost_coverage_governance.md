# P2-9 成本覆盖治理 设计文档

> 版本：v1.0
> 创建日期：2026-09-13
> 状态：设计稿（待实施）
> 前置：P2-8 商品品牌归因治理已完成（v0.15）
> 关联：`docs/development_roadmap.md`、`docs/b2c_b2b_compatibility_audit.md`、
>       `docs/frontend_b2c_b2b_architecture.md`

---

## 1. 目标与原则

### 1.1 目标（引用路线图 v0.15）

> P2-9 下一步为成本覆盖治理：列出缺少有效 `ProductCost` 的商品和交易，
> 提供可审计的成本补齐入口；成本证据完整前不计算伪造毛利，不启用内部利润抵销。

### 1.2 本次首期交付范围

| # | 交付物 | 验收要点 |
|---|--------|----------|
| 1 | 「有效成本」语义落地 | `purchase_cost > 0` 且 `total_landed_cost > 0` 才算有效；零成本/无成本行一律视为缺口 |
| 2 | 缺成本商品清单 | 商品级缺口（missing = 无成本行；invalid = 成本行无效）带原因、可筛选分页 |
| 3 | 交易级缺口清单 | 订单行项目关联商品缺有效成本的交易，按订单聚合，可追溯 |
| 4 | 批量可审计补齐入口 | 一次提交多个商品成本，逐项结果、失败隔离、`event_log` 审计 |
| 5 | 伪造毛利风险修复 | `profit_analysis` 对无效成本 withholding，绝不因零成本行给出假毛利 |
| 6 | 前端治理视图 | `ProductCostsPage` 新增「成本覆盖治理」区块：缺口清单 + 交易缺口 + 批量补齐 |
| 7 | 测试与文档 | 单元测试覆盖分类/交易缺口/批量补齐/审计/权限；docs 升版本 |

### 1.3 原则（沿用 P2 系列）

- **不伪造数据**：成本证据不完整时毛利保持缺失（None），不估算、不归零。
- **可审计**：每次补齐写入 `product_cost_snapshots`（不可变快照）+ `event_log`。
- **逐项隔离**：批量补齐单项失败不中断其余项（与 CSV intake 坏行隔离一致）。
- **工作区隔离**：所有查询/写入强制 `workspace_id` 过滤。

---

## 2. 现状盘点（代码侦察结论）

### 2.1 已有能力

| 能力 | 位置 | 说明 |
|------|------|------|
| 商品成本总览 | `GET /products/cost-overview` | 每商品最新成本 + 参考价 + 毛利；`known/missing` 计数 |
| 单品成本编辑 | `POST /products/{id}/cost-snapshots` | 版本递增 + 快照 + `event_log` 审计 |
| 单品毛利分析 | `GET /products/{id}/profit-analysis` | 成本/价格缺失时 withhold |
| 数据质量指标 | `dashboard_service` / `channel_analytics_service` | `cost_coverage_percent` + `cost_status`(verified/partial/missing) |
| 内部利润抵销门禁 | `consolidation_service` | 成本覆盖率 < 99.99% 不允许抵销 |
| 采购成本门禁 | `fulfillment_service._get_product_cost_detailed` | `purchase_cost > 0` 才认可真实成本，否则 fallback（仅估算） |

### 2.2 缺口与风险

1. **二元判定不区分「无效成本」**：`list_cost_overview.has_cost` 只判断「存在成本行」；
   `known/missing` 计数同样。成本行为零（`purchase_cost = 0`）仍被当作 known。
2. **伪造毛利风险点（必修）**：`profit_analysis` 只要 `cost is not None` 就计算毛利。
   零成本行会使 `total_landed_cost = 0`，毛利 ≈ 售价全额 —— 这正是「凭感觉」与
   「伪造数据」的反面教材，必须按有效成本门禁修复。
3. **无交易级缺口清单**：无法回答「哪些订单因为成本证据缺失而没进入毛利口径」。
4. **无批量补齐入口**：只能逐商品手工编辑，治理效率低且缺少批量审计标识。

### 2.3 有效成本定义（统一口径）

```
有效成本 effective_cost ⇔ 存在 ProductCost 行 且 purchase_cost > 0
                        且 total_landed_cost > 0
```

- 与 `fulfillment_service`（采购执行）的 `purchase_cost > 0` 判定一致；
- `total_landed_cost > 0` 是落地成本完整性兜底（防止全组件为零的占位行）。

成本状态枚举（成本治理语境）：

| 状态 | 判定 | 说明 |
|------|------|------|
| `known` | 存在有效成本 | 可计算真实毛利 |
| `invalid` | 存在成本行但无效（purchase_cost=0 或 total_landed_cost=0） | 占位/待补 |
| `missing` | 无成本行 | 未录入 |

---

## 3. 设计

### 3.1 后端：服务层（`backend/app/services/product_cost_service.py`）

新增/修改函数：

| 函数 | 行为 |
|------|------|
| `is_effective_cost(cost) -> bool` | `cost is not None and purchase_cost > 0 and total_landed_cost > 0` |
| `cost_gap_reason(cost) -> str` | `"missing"`（无行）/ `"invalid_zero_purchase"` / `"invalid_zero_landed"` |
| `list_cost_overview`（修改） | 增加 `has_effective_cost`、`cost_gap_reason` 字段；`cost_status` 支持 `invalid`；known/missing 计数基于有效成本 |
| `list_product_cost_gaps(...)` | 商品级缺口清单：missing + invalid 合并查询，带原因、分页、筛选（`gap_type=missing\|invalid\|all`） |
| `list_transaction_cost_gaps(...)` | 交易级缺口：`OrderItem` 关联商品无有效成本（或商品已删除无法溯源）的订单聚合；返回订单号、时间、缺口行数、缺口行金额 |
| `batch_fill_product_costs(...)` | 批量补齐：逐项复用 `upsert_product_cost`，单项异常记录 error 不中断；返回逐项结果（product_id、sku、version、total_landed_cost、success、error）；`event_log` 事件 `product.cost.batch_filled` |

> 事务语义：沿用服务层「不 commit」约定，由请求作用域 session 统一提交；
> 单项失败用 `savepoint` 隔离（`session.begin_nested()`），保证部分成功不污染其余项。

### 3.2 后端：Schema（`backend/app/schemas/product_cost.py`）

| Schema | 字段要点 |
|--------|----------|
| `ProductCostOverviewRow`（扩展） | + `has_effective_cost: bool`、`cost_gap_reason: str \| None` |
| `ProductCostGapRow` | product_id、sku、name、gap_type、gap_reason、total_landed_cost（若有）、sale_price |
| `ProductCostGapList` | items、total、missing、invalid、known |
| `TransactionCostGapRow` | order_id、order_number、received_at、currency、gap_item_count、gap_line_total、gap_reasons(聚合) |
| `TransactionCostGapList` | items、total、gap_order_count、gap_line_count、gap_line_total |
| `BatchCostFillItem` | product_id + `ProductCostUpsertRequest` 组件 |
| `BatchCostFillRequest` | items: list[BatchCostFillItem] |
| `BatchCostFillResultItem` | product_id、sku、success、version、total_landed_cost、error |
| `BatchCostFillResult` | results、success_count、failed_count、gap_remaining |

### 3.3 后端：API（`backend/app/api/v1/endpoints/product_intelligence.py`）

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /products/cost-gaps` | GET | 商品级缺口清单（`gap_type=missing\|invalid\|all`、search、limit、offset） |
| `GET /products/cost-gaps/transactions` | GET | 交易级缺口清单（分页） |
| `POST /products/cost-gaps/batch-fill` | POST | 批量补齐；逐项结果；与单品编辑一致的工作区权限 |

> 权限：与现有 `POST /products/{id}/cost-snapshots` 保持一致（工作区鉴权，无需额外审批流；
> 补齐只是数据录入，不涉及资金动作）。所有变更经 `event_log` 审计。

### 3.4 伪造毛利修复

`profit_analysis`：
- `cost_status` 改为基于有效成本：`KNOWN`（有效） / `MISSING`（无行或无效）；
- 无效成本时不计算 contribution_margin / margin_rate / markup_rate（保持 None），
  与「成本证据完整前不计算伪造毛利」一致；
- `breakeven_price` 仅在有效成本时给出。

`list_cost_overview` 同步修复：known/missing 计数基于有效成本，毛利列（contribution_margin）
仅在有效成本 + 参考价存在时给出（现状已如此，但需确认 invalid 行也不出毛利）。

### 3.5 前端（`frontend/src/pages/ProductCostsPage.tsx` + `api/client.ts`）

- `api/client.ts` 新增：`getCostGaps(params)`、`getTransactionCostGaps(params)`、`batchFillCosts(items)`。
- `ProductCostsPage` 新增「成本覆盖治理」区块（Segmented 切换）：
  1. 覆盖统计卡片：商品 known/missing/invalid 数、交易缺口订单数/行数/金额；
  2. 商品缺口表：sku/name/gap_type/reason/落地成本/售价，可勾选多行；
  3. 交易缺口表：订单号/时间/缺口行数/金额；
  4. 批量补齐 Drawer：勾选商品后批量录入成本组件 → 调用 batch-fill → 刷新清单。
- 全部接真实 API；失败显示错误（沿用 `apiErrorMessage`）。

### 3.6 无需数据库迁移

不新增表：复用 `product_cost` / `product_cost_snapshots` / `event_log` / `orders` / `order_items`。
`has_effective_cost` / `cost_gap_reason` 为派生字段，不落库。

---

## 4. 测试计划（`backend/tests/test_cost_coverage_governance.py`）

| 分组 | 用例 |
|------|------|
| 有效成本分类 | missing（无行）/ invalid（零采购价 / 零落地成本）/ known 三类判定正确 |
| 伪造毛利修复 | 无效成本行：profit_analysis 返回 MISSING、margin 为 None、breakeven 为 0 |
| 总览修复 | cost-overview 的 known/missing 计数基于有效成本；invalid 可筛选 |
| 商品缺口清单 | missing+invalid 合并返回；gap_type 过滤；工作区隔离 |
| 交易缺口清单 | 缺成本商品订单被列出；补齐后从清单消失；删除商品订单列为「无法溯源」 |
| 批量补齐 | 全部成功 / 部分成功（单项错误隔离）/ 版本递增 / 快照 + event_log 审计 |
| 权限 | 只读角色（viewer）调用 batch-fill 被拒 |

---

## 5. 文档同步（实施后执行）

1. `docs/development_roadmap.md`：状态 → P2-9 完成，v0.16 变更记录。
2. `docs/frontend_b2c_b2b_architecture.md`：追加 P2-9 完成段落。
3. `docs/b2c_b2b_compatibility_audit.md`：追加 P2-9 回归结果段落。

---

## 6. 风险与边界（明确不做）

| 事项 | 边界说明 |
|------|----------|
| 成本过期机制 | `valid_from` 无过期语义，本期不引入有效期/过期判定（避免范围膨胀） |
| 内部利润抵销 | 保持现状：覆盖率 < 99.99% 不允许抵销（已实现，本期不改动） |
| fallback 估算 | 不落库、不参与治理清单（履约层仅估算用途，已有 confidence<0.5 标记） |
| 成本来源追溯 | 沿用 snapshot 的 `source`（manual/intake）；本期不新增来源类型 |
| B2B 发票/报价缺口 | 本期只覆盖订单（`orders`），发票侧沿用订单归因的成本口径 |
