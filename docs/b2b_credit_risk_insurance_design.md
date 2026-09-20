# Nuotao B2B 信用风控与信用保险设计

> 版本：v1.1  
> 状态：已完成首期  
> 创建日期：2026-09-13  
> 关联：`docs/business_decisions/ADR/FINANCE-003.md`、`FINANCE-001`、`AGENTS-002`

---

## 1. 需求分析

### 1.1 业务目标

为 B2B 经营建立统一、可解释、可审计的信用准入：

- 从额度占用、逾期、账龄和坏账形成客户风险评分。
- 用已审批规则自动进入 watch/hold/freeze，减少人工漏判。
- 所有订单入口统一阻断冻结客户和超额度订单。
- 管理员可人工冻结、解除和调整信用状态，必须保留原因。
- 记录信用保险保单、覆盖范围和索赔进展。
- 为 Collection、Sales Agent 提供确定性风险证据，而非自由推断。

### 1.2 首期边界

- 不接入外部征信机构、企业工商或国际信用报告 API。
- 不自动购买保险、提交索赔或确认赔款。
- 不自动提高额度，不把保险覆盖直接等同于可用授信。
- 不自动核销坏账；沿用现有管理员坏账流程。
- 不为 B2C 客户评分。

## 2. 架构设计

```text
现有应收事实
  invoice / receipt / receivable entry / write-off
                    |
                    v
           信用风险评分服务
                    |
        +-----------+-----------+
        |                       |
  风险快照                  保险覆盖
 b2b_credit_risk_*       b2b_credit_insurance_*
        |                       |
        +-----------+-----------+
                    |
         当前客户信用状态
       normal/watch/hold/frozen
                    |
        +-----------+-----------+
        |                       |
  管理端/API                 订单准入
  评估、冻结、解除       RFQ 转订单 / 门户下单
```

### 2.1 分层职责

- `b2b_credit_service`：额度、逾期、评分、政策、状态和保险的唯一业务入口。
- `b2b_sales_service` / `b2b_portal_service`：下单前调用信用检查，不自行解释规则。
- `b2b_finance_service`：继续作为发票、收款、账龄和坏账事实来源。
- Agent：只读取信用评估结果和证据；高风险动作进入人工审批。

## 3. 数据库设计

迁移 `0044`：

### 3.1 `b2b_credit_policies`

| 字段 | 说明 |
|---|---|
| `workspace_id` | 租户隔离 |
| `version_number` | 工作区内递增版本 |
| `status` | draft / pending_approval / active / rejected / superseded |
| `watch_score` | 进入观察的最低分 |
| `hold_score` | 自动暂停的最低分 |
| `freeze_score` | 自动冻结的最低分 |
| `max_utilization_percent` | 自动暂停/冻结的额度利用率阈值 |
| `max_overdue_days` | 自动暂停/冻结的最大逾期天数 |
| `auto_hold_enabled` | 是否允许自动 hold |
| `auto_freeze_enabled` | 是否允许自动 freeze |
| `insurance_required_above` | 要求的保险覆盖敞口下限，0 表示不强制 |
| `notes` | 政策备注 |
| 审批字段 | created/submitted/approved/rejected 的 actor 与时间 |

约束：

- `0 <= watch_score < hold_score < freeze_score <= 100`。
- 同一工作区最多一份 active 政策，使用部分唯一索引。
- 已有 active 时重复审批返回冲突，不产生两份生效政策。

### 3.2 `b2b_credit_risk_assessments`

| 字段 | 说明 |
|---|---|
| `agent_id` | 被评估客户 |
| `policy_id` | 使用的政策版本 |
| `score` | 0-100 分值 |
| `risk_level` | low / medium / high / critical |
| `recommended_action` | none / watch / hold / freeze |
| `applied_action` | 实际执行动作 |
| `credit_status_before/after` | 状态变化快照 |
| `exposure_amount` | 当前应收敞口 |
| `overdue_amount` | 逾期敞口 |
| `utilization_percent` | 额度利用率 |
| `overdue_ratio_percent` | 逾期 / 敞口 |
| `max_days_overdue` | 最大逾期天数 |
| `past_due_invoice_count` | 逾期发票数 |
| `written_off_amount` | 历史核销金额 |
| `insurance_coverage_amount` | 有效保险覆盖上限 |
| `insurance_coverage_percent` | 有效保险覆盖比例 |
| `net_exposure_amount` | 敞口减保险覆盖，最低为 0 |
| `factors` | 可解释评分因子 JSON |
| `message` | 阻断/提示说明 |
| `assessed_by/at` | 评估审计 |

每次评估追加一条快照，不覆盖历史。

### 3.3 `b2b_credit_status_events`

| 字段 | 说明 |
|---|---|
| `agent_id` | 客户 |
| `assessment_id` | 可关联自动评分 |
| `previous_status/new_status` | 状态迁移 |
| `action` | assess / auto_hold / auto_freeze / manual_freeze / release |
| `reason` | 触发或人工原因 |
| `actor` | 操作者或 `credit-policy:{id}` |
| `evidence` | 规则、分值和关键金额快照 |

状态变化只追加事件，不改历史事件。

### 3.4 `b2b_credit_insurance_policies`

| 字段 | 说明 |
|---|---|
| `agent_id` | 被保险人 |
| `policy_number` | 工作区内唯一保单号 |
| `provider` | 承保人 |
| `currency` | 保单币种 |
| `coverage_limit` | 覆盖上限 |
| `coverage_percent` | 覆盖比例 0-100 |
| `effective_from/to` | 有效期 |
| `status` | draft / active / expired / cancelled |
| `created_by/updated_by` | 审计 |

同客户可以保留历史保单，但同一时间只有一份 active 保单；服务层按生效日期解析。

### 3.5 `b2b_credit_insurance_claims`

| 字段 | 说明 |
|---|---|
| `policy_id / invoice_id` | 索赔关联 |
| `claim_number` | 工作区内唯一索赔号 |
| `status` | draft / submitted / approved / rejected / settled |
| `claimed_amount` | 申请金额 |
| `recovered_amount` | 已确认回收金额 |
| `currency` | 必须与保单和发票一致 |
| `evidence` | 支持材料元数据，不保存密钥 |
| `reason/rejection_reason` | 业务原因 |
| `filed/decided/settled` | 时间与操作者 |

索赔不会自动改变发票余额。实际赔款需要后续通过现有收款流程登记，避免重复核销。

### 3.6 `b2b_agents` 新字段

```text
credit_status
credit_status_reason
credit_status_updated_by
credit_status_updated_at
credit_policy_id
```

## 4. 评分与动作规则

### 4.1 输入事实

- 信用额度：`b2b_agents.credit_limit`
- 当前余额：`b2b_agents.current_balance`
- 应收敞口：未结发票 `balance_due` 合计
- 逾期：未结发票到期日小于评估日
- 最大逾期天数：按未结逾期发票计算
- 坏账：已核销金额合计
- 保险：评估日有效 active 保单

### 4.2 初版评分

```text
utilization_score = min(utilization_percent / 100, 1) * 40
overdue_ratio_score = min(overdue_ratio_percent / 100, 1) * 30
overdue_days_score = min(max_days_overdue / 90, 1) * 20
write_off_score = min(write_off_amount / max(exposure + write_off, 1), 1) * 10
insurance_discount = min(coverage_percent / 100, 1) * 15
score = clamp(round(sum(score parts) - insurance_discount), 0, 100)
```

政策阈值决定：

```text
score >= freeze_score                  -> freeze
score >= hold_score or
  utilization >= max_utilization or
  max_days_overdue >= max_overdue_days -> hold
score >= watch_score                   -> watch
otherwise                              -> none
```

### 4.3 自动执行

- 只有 active 政策可以评估。
- `hold` 仅在 `auto_hold_enabled=true` 时自动执行。
- `freeze` 仅在 `auto_freeze_enabled=true` 时自动执行。
- 未启用的自动动作只写入推荐结果和界面提示。
- 人工解除 `hold/frozen` 只允许 admin，且原因必填。
- 订单创建始终以客户当前状态为准，不因历史评估为 low 而绕过。

## 5. API 设计

```text
GET    /api/v1/admin/b2b/credit/overview
GET    /api/v1/admin/b2b/credit/policies
POST   /api/v1/admin/b2b/credit/policies
POST   /api/v1/admin/b2b/credit/policies/{id}/submit
POST   /api/v1/admin/b2b/credit/policies/{id}/approve
POST   /api/v1/admin/b2b/credit/policies/{id}/reject
GET    /api/v1/admin/b2b/credit/risks
GET    /api/v1/admin/b2b/credit/agents/{agent_id}
POST   /api/v1/admin/b2b/credit/agents/{agent_id}/assess
POST   /api/v1/admin/b2b/credit/agents/{agent_id}/status
GET    /api/v1/admin/b2b/credit/agents/{agent_id}/history
GET    /api/v1/admin/b2b/credit/insurance
POST   /api/v1/admin/b2b/credit/insurance
PUT    /api/v1/admin/b2b/credit/insurance/{id}
GET    /api/v1/admin/b2b/credit/claims
POST   /api/v1/admin/b2b/credit/claims
POST   /api/v1/admin/b2b/credit/claims/{id}/submit
POST   /api/v1/admin/b2b/credit/claims/{id}/approve
POST   /api/v1/admin/b2b/credit/claims/{id}/reject
POST   /api/v1/admin/b2b/credit/claims/{id}/settle
```

权限：

- 查询：登录用户。
- 政策草稿、提交、单客户评估、保单维护和索赔草稿/提交：operator。
- 政策审批、人工冻结/解除、索赔批准/驳回/结算：admin。
- actor 和 workspace 只从认证身份获取。

## 6. 技术选型

| 方案 | 成本 | 优点 | 缺点 | 适用场景 |
|---|---|---|---|---|
| 规则引擎库（如 json-rules-engine/本地规则 DSL） | 低 | 表达力强 | 增加依赖和学习成本，首期收益有限 | 多规则、多租户复杂策略 |
| 本服务显式字段和确定性函数 | 最低 | 易审计、易测试、无额外依赖 | 规则变化需要迁移或新版本字段 | 首期信用评分和冻结 |
| 外部征信/保险平台 | 中高 | 数据丰富 | 合规、接口和费用复杂 | 规模化后 |
| LLM 直接决策 | 低开发成本 | 自然语言解释好 | 不可复现、金融风险高 | 仅生成解释或建议，不执行 |

首期选择显式字段和确定性函数，保留后续政策 JSON/规则引擎演进空间。

## 7. 开发步骤

1. 新增迁移 `0044` 和 ORM 模型，补齐代理信用状态列。
2. 实现信用政策、评分快照、状态事件和订单准入服务。
3. 实现保险保单和索赔服务。
4. 接入内部 API 与 RBAC。
5. 替换销售/门户两处重复信用检查。
6. 新增信用风控页面、导航、路由和 API 客户端。
7. 增加单元、迁移、API 和 Chrome 端到端回归。
8. 更新兼容性审计、前端架构和路线图。

## 8. 测试方案

- 政策职责分离、版本替代、跨工作区隔离。
- 评分因子复现、阈值边界、保险折扣和最高分封顶。
- watch/hold/frozen 对订单准入的影响。
- 自动动作只在政策允许时执行；人工解除要求 admin 和原因。
- 保险有效期、保单冲突、索赔金额/币种/状态机。
- `0043 -> 0044 -> 0043 -> 0044` PostgreSQL 往返。
- Chrome 验收政策审批、风险评估、冻结/解除和保险覆盖展示。

## 9. 首期验收结果

验证日期：2026-09-13。

- `tests/test_b2b_credit.py` 覆盖政策职责分离、政策替代、自动暂停、自动冻结开关、人工解除、保险折扣、索赔生命周期和工作区隔离。
- `tests/test_b2b_credit_api_authorization.py` 覆盖匿名 `401`、viewer/operator 权限边界、admin 审批与状态操作、订单入口 `409` 映射，以及政策、风险和保险数据的工作区隔离。
- `tests/test_b2b_sales.py` 与 `tests/test_b2b_portal_sales.py` 覆盖真实报价转订单和门户下单入口：`hold / frozen` 阻断，超额度拒绝。
- `tests/integration/test_b2b_credit_migrations.py` 在 PostgreSQL 完成 `0043 -> 0044 -> 0043 -> 0044` 往返，并验证五张信用风控表、代理信用状态列、唯一索引和状态索引。
- staging Neon 数据库已升级至 `0044`。
- 管理端 `/b2b/credit` 已接入信用政策、风险总览、客户档案、人工解除、信用保险和索赔接口；页面不自行计算评分或覆盖金额。
- `frontend/e2e/b2b-credit-risk.spec.ts` 在 Google Chrome 中完成“政策创建/提交/审批 -> 风险评估 -> 自动暂停 -> 人工解除 -> 保险覆盖展示”的真实后端回归，且无 API `401/403/500` 和控制台错误。
- B2B 管理端路由冒烟覆盖 `/b2b/credit`；`npm run typecheck` 与 `npm run build` 通过，仅保留既有 `antd-vendor` 体积告警。
