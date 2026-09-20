# Nuotao B2B 代理商年度协议、目标与分级返利设计

> 版本：v1.1  
> 状态：已完成首期  
> 创建日期：2026-09-13  
> 关联：`docs/business_decisions/ADR/SALES-003.md`、`docs/b2b_portal_design.md`

---

## 1. 目标与边界

### 1.1 目标

为代理商、批发商和经销商建立可审计的年度协议，支持：

- 年度或自定义周期销售目标。
- 按订单、已开票金额或已收款金额计算目标达成。
- 代理商等级返利阶梯。
- 周期返利计算、人工审批和结算登记。
- 多币种订单按工作区直接汇率换算到协议币种。
- 管理层查看目标进度、返利负债和历史凭证。

### 1.2 明确不做

- 不复制订单、发票和收款数据；所有目标与返利计算都读取现有事实表。
- 不自动生成付款、银行指令或会计凭证。
- 不允许创建人审批自己的返利计算单。
- 不允许在缺少直接汇率时静默按 `1:1` 或反向汇率估算。
- 第一阶段不支持增量累进返利，只支持“总销售额命中档位后按该档比例返利”。
- 门户客户默认只读查看已生效协议和目标进度，不能修改协议或审批返利。

---

## 2. 核心定义

### 2.1 协议

协议绑定一个工作区和一个代理商，包含：

```text
agreement_number
agent_id
effective_from / effective_to
currency
target_amount
qualification_basis
calculation_method
status
```

状态机：

```text
draft -> pending_approval -> active
pending_approval -> rejected -> pending_approval
active -> terminated
```

同一代理商同一时期内只能有一份生效协议。审批时锁定该代理商已有生效协议，存在期间重叠时将旧协议标记为 `expired`。

### 2.2 资格口径

```text
ordered   非取消 B2B 订单总额，按订单创建时间归属
invoiced  非草稿、非作废发票总额，按开票日期归属
paid      收款分录金额，按核销发生时间归属
```

默认使用 `invoiced`。该口径代表已形成应收的企业销售收入，避免把未确认订单直接计入返利。

所有金额必须换算到协议币种。汇率使用 `workspace_id + base + quote + 生效日期` 的唯一事实来源，缺失直接汇率时该笔记录排除，并在进度响应中返回缺失汇率提示。

### 2.3 返利阶梯

```text
min_sales_amount <= 实际销售额 < max_sales_amount
rebate_percent
```

阶梯必须从 `0` 开始、连续衔接且最后一段无上限。例如：

```text
0       - 100000  0%
100000  - 300000  2%
300000+           4%
```

命中 `300000+` 时，第一阶段按总销售额 `× 4%` 计算返利，不按区间分段累加。

### 2.4 返利计算单

返利计算单是周期返利快照和审批载体：

```text
draft -> pending_approval -> approved -> settled
pending_approval -> rejected -> draft
```

- `draft` 可重新计算，覆盖尚未审批的快照。
- `pending_approval` 锁定销售额、档位、比例和金额。
- 提交人与审批人必须不同。
- `approved` 代表形成返利负债，但仍未结算。
- `settled` 只登记结算凭证和操作人，不执行资金支付。

---

## 3. 数据库设计

迁移 `0043` 新增：

### 3.1 `b2b_agent_agreements`

| 字段 | 说明 |
|---|---|
| `workspace_id` | 租户隔离 |
| `agreement_number` | 工作区内唯一协议号 |
| `agent_id` | 代理商 |
| `name` | 协议名称 |
| `status` | 协议状态 |
| `currency` | 协议及返利币种 |
| `effective_from/to` | 生效周期 |
| `target_amount` | 销售目标 |
| `qualification_basis` | `ordered / invoiced / paid` |
| `calculation_method` | 首期固定为 `retroactive` |
| `created_by` | 创建人 |
| `submitted_by/at` | 提交审计 |
| `approved_by/at` | 审批审计 |
| `rejection_reason` | 驳回原因 |
| `terminated_by/at` | 终止审计 |

### 3.2 `b2b_rebate_tiers`

| 字段 | 说明 |
|---|---|
| `agreement_id` | 所属协议 |
| `min_sales_amount` | 区间下界，包含 |
| `max_sales_amount` | 区间上界，不包含；空表示无上限 |
| `rebate_percent` | 返利比例，0-100 |

数据库约束防止负数和倒置区间；服务层在提交审批前校验阶梯连续、无重叠、无缺口。

### 3.3 `b2b_rebate_accruals`

| 字段 | 说明 |
|---|---|
| `agreement_id` | 所属协议 |
| `period_start/end` | 返利周期 |
| `status` | 计算单状态 |
| `qualifying_sales` | 锁定销售额 |
| `rebate_percent` | 锁定档位比例 |
| `rebate_amount` | 锁定返利金额 |
| `currency` | 锁定币种 |
| `evidence` | 记录数、排除数、缺失汇率和档位快照 |
| `created_by` | 计算人 |
| `submitted/approved/rejected/settled` | 审批和结算审计 |

同一协议、同一周期的计算单唯一，重复计算不会生成第二张负债。

---

## 4. 服务与公式

### 4.1 目标进度

```text
qualifying_sales = Σ convert(事实金额, 事实币种, 协议币种, 事实日期)
achievement_percent = qualifying_sales / target_amount × 100
remaining_amount = max(target_amount - qualifying_sales, 0)
```

返回：

- 当前档位比例和预估返利。
- 距离下一档还需的销售额。
- 周期剩余天数。
- 纳入和排除的事实记录数。
- 缺失直接汇率的币种集合。

### 4.2 返利计算

```text
rebate_amount = qualifying_sales × matched_tier.rebate_percent / 100
```

金额使用 `Decimal`，最终按 `0.01` 四舍五入。

### 4.3 并发与幂等

- 审批协议和创建返利计算单使用行锁。
- 同周期重复创建返回既有计算单。
- `draft/rejected` 计算单允许重算；已提交后的快照不可修改。
- 重复审批、重复驳回和重复结算返回当前结果，不重复写入负债或凭证。
- 所有状态变更写入 `event_log`。

---

## 5. API 设计

```text
GET    /api/v1/admin/b2b/agreements
POST   /api/v1/admin/b2b/agreements
GET    /api/v1/admin/b2b/agreements/{id}
PUT    /api/v1/admin/b2b/agreements/{id}
POST   /api/v1/admin/b2b/agreements/{id}/tiers
PUT    /api/v1/admin/b2b/agreements/{id}/tiers/{tier_id}
DELETE /api/v1/admin/b2b/agreements/{id}/tiers/{tier_id}
POST   /api/v1/admin/b2b/agreements/{id}/submit
POST   /api/v1/admin/b2b/agreements/{id}/approve
POST   /api/v1/admin/b2b/agreements/{id}/reject
POST   /api/v1/admin/b2b/agreements/{id}/terminate
GET    /api/v1/admin/b2b/agreements/{id}/progress
GET    /api/v1/admin/b2b/rebate-accruals
POST   /api/v1/admin/b2b/agreements/{id}/rebate-accruals
POST   /api/v1/admin/b2b/rebate-accruals/{id}/submit
POST   /api/v1/admin/b2b/rebate-accruals/{id}/approve
POST   /api/v1/admin/b2b/rebate-accruals/{id}/reject
POST   /api/v1/admin/b2b/rebate-accruals/{id}/settle
```

权限：

- 查询：登录用户。
- 协议、阶梯和计算单编辑/提交：`operator`。
- 协议审批/终止、返利审批/结算：`admin`。
- actor 和 workspace 均来自认证身份，不接收前端传入。

---

## 6. 前端结构

新增 `/b2b/agreements`：

1. 顶部指标：生效协议、年度目标、已达成金额、待审批返利。
2. 协议列表：客户、周期、口径、目标、达成率、状态。
3. 协议详情：
   - 基础条款。
   - 连续返利阶梯。
   - 目标进度与下一档缺口。
   - 返利计算单列表。
4. 操作：
   - 创建/编辑协议和阶梯。
   - 提交、审批、驳回。
   - 计算周期返利、提交审批。
   - 管理员审批和登记结算凭证。

页面不得展示模拟目标、模拟返利或前端计算后的负债金额；所有金额与状态来自后端。

---

## 7. 验收标准

- [x] 跨工作区无法读取或修改协议、阶梯和返利计算单。
- [x] 阶梯重叠、缺口、未从 0 开始或缺失开放尾段时不能提交。
- [x] 提交人不能审批自己的协议或返利计算单。
- [x] 同一周期重复计算返回同一计算单。
- [x] `draft/rejected` 可重算，`pending_approval/approved/settled` 快照不可修改。
- [x] `ordered/invoiced/paid` 三种口径只统计对应事实表。
- [x] 非协议币种金额按历史直接汇率换算；缺失汇率时明确排除并返回提示。
- [x] 审批、驳回、终止和结算均有操作人、时间和事件日志。
- [x] PostgreSQL `0042 -> 0043 -> 0042 -> 0043` 迁移往返通过。
- [x] 服务、API、Chrome 端到端、类型检查和生产构建全部通过。

首期验收证据：

- `backend/tests/test_b2b_agreements.py`：8 项通过。
- PostgreSQL `0042 -> 0043 -> 0042 -> 0043`：升级、降级和再次升级通过。
- `frontend/e2e/b2b-agreements.spec.ts`：在 Google Chrome 中完成协议创建、审批、真实订单进度、返利审批和结算登记。
- `frontend/e2e/b2b-p1-smoke.spec.ts`：既有 B2B 六路由加 `/b2b/agreements` 回归通过。
- 协议、财务、履约、门户、价格、销售、P0 和权限组合回归：29 项通过。
- `npm run typecheck` 与 `npm run build`：通过。

---

## 8. 后续迭代

- 增量累进返利。
- 多目标 KPI（销售额、回款额、品类目标、新客数）。
- 月度/季度自动生成计算单和计划任务。
- 返利抵扣应收、贷项通知单和总账对接。
- 代理商门户只读协议与目标进度。
- 折扣、市场发展基金和联合营销费用预算。

---

## 9. 变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.1 | 2026-09-13 | 首期完成：补充真实订单进度、审批边界、并发锁、迁移往返、Chrome 端到端与组合回归证据 |
| v1.0 | 2026-09-13 | 首版：年度协议、目标进度、连续阶梯返利、人工审批与结算登记 |
