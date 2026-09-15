# ADR AGENTS-002 — B2B 专业 Agent 建议闭环

> 状态：**Accepted**（2026-09-13）  
> 决策编号：AGENTS-002  
> 关联：`AGENTS-001`、`SALES-001`、`PRICING-001`、`FINANCE-001`

---

## Context（背景）

`0040` 已为 Agent Runtime 建立 `B2C | B2B | SHARED` 范围、工具白名单、
预算和审批隔离，但 B2B 仍缺少真正读取询盘、报价和应收数据的业务 Agent。

B2B 流程与 B2C 不同：RFQ、报价审批、合同、PO、账期和催收之间存在多轮
人工谈判。若 Agent 直接发送报价、修改价格或执行催收，会绕过销售和财务
审批，风险不可接受。

## Decision（决策）

### 1. 首期只实现三类建议型 Agent

```text
b2b_sales_agent       -> RFQ 优先级、停滞风险和下一步动作
b2b_quotation_agent   -> 已发布阶梯价、成本、目标毛利和报价建议
b2b_collection_agent  -> 账龄、信用占用、风险与回款动作优先级
```

- 三个 Agent 的 `business_scope` 固定为 `B2B`。
- 首期权限级别为 `L2`：允许读取内部经营数据并提出建议，不允许执行写操作。
- 使用确定性规则和数据库事实生成结果；未来可接入 LLM 生成解释文案，但不得
  替代价格解析、毛利计算、账龄和信用风险规则。

### 2. Agent 不绕过领域服务

- RFQ、报价和合同读取必须经过 `b2b_sales_service` 或同一仓储边界。
- 阶梯价必须由 `b2b_pricing_service.resolve_b2b_price` 解析。
- 发票、余额和账龄必须由 `b2b_finance_service` 计算。
- Agent 不允许直接拼装价格、改变发票余额或写 B2B 交易表。

### 3. 输出必须是可审计建议

每次执行至少记录：

- 分析类型和数据截止日期。
- 用作依据的实体 ID、金额、币种和账龄桶。
- 推荐动作、风险标记、阻断项和置信度。
- `requires_human_approval=true` 和 `write_actions_performed=[]`。

Agent 输出不得作为报价、合同、收款或核销的自动执行依据。

### 4. 分析结果进入统一人工审批中心

- B2B Agent 完成分析后，将可行动项幂等转换为 `agent_suggestions`，统一显示在
  `/ai/suggestions` 审批中心。
- B2B 建议 `source=b2b_agent`，初始状态固定为 `pending_approval`，禁用 LLM
  自动审批，必须由业务人员人工批准或拒绝。
- 建议的 `execution_params.evidence` 保存数据截止日期、业务实体、金额、毛利、
  账龄、风险标记和阻断项，前端提供“决策证据”和“人工审批记录”详情。
- B2B 建议使用 `execution_action=manual_review`。批准并确认处理只关闭建议，
  明确返回 `business_write_performed=false`，不得自动创建报价、改价、发送催收
  或核销应收。
- 同一业务实体、分析类型和推荐动作只保留一条未关闭建议，重复运行不重复创建。

### 5. 注册与运行边界

- 内置 Agent 通过幂等 bootstrap 创建，不在 Worker 启动时自动注册。
- Worker 只负责路由到内置执行器；未知 Agent 仍使用通用 LLM 执行器。
- 非 B2B Agent 即使误投 B2B 任务，执行器也必须拒绝。
- 高风险动作继续进入统一审批队列，Agent 不得自批。

### 6. 前端入口

管理端新增 `/b2b/ai` 工作台，用于：

- 检查和初始化三类 B2B Agent。
- 创建销售、报价、回款分析任务。
- 查看任务状态、输入和失败原因。

报价 Agent 必须先选择 RFQ，不能对不存在或未提交的询盘生成报价建议。

## Consequences（后果）

### 正面

- B2B 销售、报价和财务团队可以先用 Agent 获得可解释的工作优先级。
- 分析结果绑定真实业务数据和范围快照，便于复盘。
- 不引入自动改价、自动承诺交期或自动催收风险。
- 后续可在现有建议链路上增加 CRM 跟进、邮件草稿和收款提醒审批。

### 成本

- 初始 Agent 为规则型，LLM 叙事质量取决于后续接入。
- 需要维护价格、成本和账龄规则，但规则本身也是财务事实口径。
- Agent 建议不会自动落地，仍需业务人员确认和执行。

## Verification（验收）

- 三个 Agent 可幂等注册，且范围均为 `B2B`。
- 销售 Agent 能识别停滞 RFQ 并给出优先动作。
- 报价 Agent 只能使用已发布价格，并计算目标价缺口和毛利率。
- 回款 Agent 能按账龄和信用占用排序，并标记风险。
- 三类 Agent 执行后不新增报价、不修改价格、不发送催收、不改发票余额。
- 非 B2B Agent 执行 B2B 分析时被拒绝。
- 三个 Agent 的可行动结果进入统一建议中心，保持 `pending_approval` 且不触发
  自动审批；证据详情和人工审批记录可查看。
- 重复运行同一分析不会重复创建未关闭建议；人工确认建议不产生业务写操作。
- 前端 `/b2b/ai` 可初始化、创建任务并查看状态。
