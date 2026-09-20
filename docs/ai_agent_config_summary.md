# Nuotao AI OS - AI Agent 管控流程配置总结

**版本**: v2.0  
**配置日期**: 2026-09-05  
**更新日期**: 2026-09-20（v2.0 身份治理修订）  
**状态**: ⚠️ 部分已落地，工具层可执行覆盖率待补齐

> **v2.0 修订说明（重要，请先读）**
>
> v1.1 记录的"5 个 Agent 全部 active、26 个工具注册成功、2 个 L3 工具必须人工审批"
> 是**一次性人工执行 SQL 的结果**，无部署可复现性，且与 runtime 实际状态不一致：
>
> 1. **Agent 身份重复**：v1.1 使用 hyphen ID（`product-manager` 等）写入 `agents` 表，
>    而 runtime 种子（`app/agents/agent_seed.py`、`init_all_agents.py`）使用 snake_case
>    （`product_analyst` 等），同一角色最多出现 3 个 ID（客户角色：
>    `customer_manager` / `customer-manager` / `customer_service_manager`）。
>    v2.0 统一为 **snake_case 规范 ID**，由 `backend/scripts/seed_agent_config.py`
>    在 CI 中幂等执行。详见 `docs/agent_team_workflow_refactor.md`。
>
> 2. **工具白名单与 handler 注册 0 匹配**：`register_agent_tools.sql` 的 `handler_name`
>    写成 `module.func` 路径形式，而 `tool_gateway` 实际注册的 handler 只有 5 个
>    （`generate_product_image`、`generate_activity_plan`、`match_influencers`、
>    `localize_listing`、`get_customer_template`）。结果：26 个工具全部
>    whitelist-only（仅审计、**不可执行**，含 2 个 L3 高风险工具），
>    而那 5 个真 handler 不在白名单内（调用会被门禁拒绝）。
>
> 3. **调度路径不写 `ai_agent_runs`**：`app/tasks/daily_agents.py` 的 5 个 `run_*_daily`
>    当前不调用 LLM（属规则建议生成器），因此不产生 `ai_agent_runs` 审计行，
>    也不经过 Budget Gate / Execution Policy。真正调 LLM 的 5 个 Agent 仅通过
>    API 端点与 Worker executor 可达。
>
> 下文保留 v1.1 的管控设计口径（职责/权限/预算/审批/防造假），
> 但**实际可执行状态以 v2.0 修订说明与「十一·补、实际状态核对」为准**。
> 相关技术债已登记到 `docs/agent_team_workflow_refactor.md` P2 清单。

---

## 一、配置概述

本次配置完成了Nuotao AI OS的AI Agent管控流程，按照AGENTS.md 3.1-3.4原则设计，实现了从选品到采购的全流程Agent管控。

### 核心原则
1. **Agent是「提议者」不是「执行者」**：高风险操作必须进入审批队列，人工确认后执行
2. **全链路可审计**：每次Agent运行的输入、规划、工具调用、输出、成本、审批结果全部落库
3. **白名单工具**：Agent只能调用注册过的26个工具函数
4. **上下文最小化**：只把完成任务所需数据给模型
5. **成本护栏**：每Agent设月度成本预算，超限自动告警并降级

---

## 二、Agent 注册配置（5 个，v2.0 统一 snake_case 规范 ID）

> ❗ v1.1 使用的 hyphen ID（`product-manager` 等）已在 v2.0 废弃。
> `agents` 表中同名的 hyphen 行**不删除**（避免破坏已有引用），但不再更新；
> 唯一权威身份为下表 snake_case ID，由 `backend/scripts/seed_agent_config.py` 幂等注册。

| Agent ID（规范） | 名称 | 领域 | 权限 | 模型 | 职责 |
|----------|------|------|------|------|------|
| product_analyst | 产品分析师AI | product | L2 | gpt-4o-mini（种子默认） | 1688选品分析、产品导入、图片合规检查、WooCommerce上架 |
| marketing_manager | 营销经理AI | marketing | L2 | deepseek-chat | AI文案生成、文案合规检查、AI生图（主图+详情图）、生图质量检查 |
| supply_chain_manager | 供应链经理AI | supply_chain | L2 | deepseek-chat | 库存同步、采购单创建、1688下单、采购物流追踪、物流信息同步 |
| customer_manager | 客户经理AI | customer | L1 | deepseek-chat | 客户咨询回复、订单状态查询、售后问题处理 |
| business_analyst | 商业分析师AI | analytics | L3 | deepseek-chat | 经营数据分析、成本模型、AI周报、选品模型评估 |

> ⚠️ v1.1 曾出现的第三个客户角色 ID `customer_service_manager` 已废弃，不再注册。

**权限级别说明**:
- L0: 公开读
- L1: 内部读
- L2: 提议（可创建草稿，需人工确认）
- L3: 高风险执行（必须人工审批）

---

## 三、工具白名单配置（26个工具，9个类别）

> ⚠️ **v2.0 实际可执行状态**：下表 26 个工具已入库为白名单，但其中
> **仅 5 个真正可执行**（`generate_product_image`、`generate_activity_plan`、
> `match_influencers`、`localize_listing`、`get_customer_template`，
> 见 `app/services/m6_tool_registry.py`）。其余 21 个工具的 `handler_name`
> 与实际注册的 handler 名不匹配，处于 **whitelist-only（仅审计、不可执行）** 状态，
> 包含 2 个 L3 高风险工具 `publish_woocommerce_product`、`submit_1688_order`——
> 因此文档所述"L3 人工审批后执行"当前**实际什么都执行不了**（偏安全侧，但非预期）。
>
> 补齐方式：在 `m6_tool_registry.py` 中按真实 handler 名注册对应 handler，
> 并让 `seed_agent_config.py` 写入一致的 `handler_name`。已列为 P2 待办。

| 类别 | 工具数 | L0 | L1 | L2 | L3高风险 |
|------|--------|----|----|----|----------|
| common | 4 | 3 | 0 | 1 | 0 |
| copywriting | 3 | 0 | 2 | 1 | 0 |
| image | 2 | 0 | 2 | 0 | 0 |
| image_generation | 4 | 0 | 3 | 1 | 0 |
| inventory | 2 | 0 | 1 | 1 | 0 |
| procurement | 4 | 0 | 1 | 2 | 1 |
| selection | 2 | 0 | 0 | 2 | 0 |
| sourcing | 2 | 0 | 2 | 0 | 0 |
| woocommerce | 3 | 0 | 0 | 2 | 1 |
| **合计** | **26** | **3** | **11** | **10** | **2** |

### 高风险工具（L3，必须人工审批）

| 工具名 | 类别 | 描述 | Handler |
|--------|------|------|---------|
| publish_woocommerce_product | woocommerce | 发布WooCommerce产品 | woocommerce_sync_service.publish_product |
| submit_1688_order | procurement | 提交1688订单 | purchase_automation_service.submit_order |

---

## 四、产品全生命周期状态机

### 状态流转（14个状态）

```
draft → candidate → selection_approved → copy_generated → copy_approved 
→ image_checking → (image_approved | image_generating → image_approved) 
→ ready_to_list → listing_draft → published → (out_of_stock ↔ published) → archived
```

### 关键审批节点

| 状态转换 | 触发 | Agent | 审批 |
|----------|------|-------|------|
| candidate → selection_approved | 选品分析通过 | product-manager | ✅ 人工审批 |
| copy_generated → copy_approved | 文案合规通过 | marketing-manager | ✅ 人工审批 |
| image_generating → image_approved | AI生图质量通过 | marketing-manager | ✅ 人工审批 |
| listing_draft → published | 发布产品 | product-manager | ✅ 人工审批（L3高风险） |

---

## 五、订单与采购流程状态机

### 状态流转（11个状态）

```
order_received → order_verified → purchase_order_created → waiting_purchase_approval 
→ purchase_submitted → supplier_shipped → warehouse_received → international_shipped 
→ delivered → completed
```

### 关键审批节点

| 状态转换 | 触发 | Agent | 审批 |
|----------|------|-------|------|
| waiting_purchase_approval → purchase_submitted | 审批并提交1688订单 | supply-chain-manager | ✅ 人工审批（L3高风险） |

---

## 六、AI生图SOP流程（严格执行）

### 主图生产流程（8步）
1. 先喂商品信息
2. 先出3套主图方向（白底清爽/真实场景/促销转化）
3. 把方案改成绘图提示词
4. 一张跑通后再批量
5. 主图文案只讲一个卖点（≤10字）
6. 整理成执行清单
7. 把商品资料粘进去
8. 核心理念：先拆商品资料，再交给图像模型

### 详情图生产流程（4步+6板块）
1. 先让AI读懂产品
2. 先检查，再生成
3. 最后再写提示词（8部分结构）
4. 输入提示词，开始生成

**详情页6个标准板块**: 品牌主视觉 → 核心卖点 → 功能结构 → 使用场景 → 产品细节 → 品质保障

### 严格规则（强制执行）
- ✅ 主图和详情图逻辑必须严格区分，不得混用
- ✅ 必须使用I2I图生图，以1688原图为参考基准
- ✅ 禁止纯文字T2I生成产品图
- ✅ 生图后必须逐张检查产品外观一致性
- ✅ 所有文字必须是英文，禁止中文混入
- ✅ 发现问题立即重新生成，不得批量通过

---

## 七、成本护栏与降级链

### 月度成本预算（总计 $230/月）

| Agent | 月度预算（美元） |
|-------|-----------------|
| product-manager | $50.00 |
| marketing-manager | $100.00（含生图） |
| supply-chain-manager | $30.00 |
| customer-manager | $20.00 |
| business-analyst | $30.00 |
| **合计** | **$230.00** |

### 成本告警阈值
- 80%: 发送警告通知
- 95%: 自动降级到低配模型
- 100%: 暂停Agent并通知人工

### 降级链
- **LLM不可用**: deepseek-chat → gpt-3.5-turbo → 规则引擎 → 人工
- **生图失败**: 重试1次（相同参数）→ 重试1次（简化参数）→ 使用1688原图 → 人工
- **客服场景**: 回复不了也比乱回复强，不确定时降级到人工

### 单次运行限制
- 最大token数: 10,000
- 最大工具调用次数: 20
- 最大延迟: 120秒

---

## 八、审批SLA配置

| 审批类型 | SLA（小时） | 说明 |
|----------|------------|------|
| 选品审批 | 24 | 选品分析结果需人工确认 |
| 文案审批 | 12 | AI生成的文案需人工确认 |
| 图片审批 | 12 | AI生成的图片需人工确认质量 |
| 上架审批 | 24 | WooCommerce产品发布必须人工审批 |
| 采购审批 | 4 | 1688实际下单必须人工审批 |

---

## 九、全链路审计配置

### 审计字段（必填）
agent_id, input, plan, tool_calls, output, approval, cost, status, trace_id, created_at, completed_at

### 日志保留期
- Agent运行审计: 365天
- Agent执行审计: 365天
- 审批记录: 730天

### PII保护
- 日志/提示词/Agent运行记录中禁止出现PII明文
- 需要时脱敏（mask/截断）
- 客户姓名/邮箱/地址/支付信息加密存储

---

## 十、配置文件清单

| 文件 | 路径 | 说明 |
|------|------|------|
| 工具白名单SQL | scripts/register_agent_tools.sql | 26个工具注册 |
| Agent职责SQL | scripts/configure_agent_roles.sql | 5个Agent职责权限配置 |
| 成本护栏SQL | scripts/configure_agent_guardrails.sql | 成本护栏与系统配置 |
| 流程编排配置 | docs/ai_agent_workflow_config.yaml | 完整流程编排配置（状态机+SOP+审批+成本） |
| 配置总结文档 | docs/ai_agent_config_summary.md | 本文档 |

---

## 十一、验证结果

✅ **Agent注册**: 5个Agent全部active，权限级别正确  
✅ **工具白名单**: 26个工具注册成功，9个类别，2个L3高风险工具  
✅ **高风险工具**: publish_woocommerce_product + submit_1688_order 必须人工审批  
✅ **成本护栏**: v1.0配置生效，月度预算$230，告警阈值80/95/100%  
✅ **生图方法**: i2i_only（仅允许I2I图生图，禁止纯文字T2I）  
✅ **审批队列**: 系统已有2条PRODUCT_DECISION审批记录（approved）  
✅ **流程编排**: 产品生命周期14状态 + 订单采购11状态 + 生图SOP完整配置

---

### 11.2 v2.0 实际状态核对（2026-09-20，如实标注）

| 项 | v1.1 声称 | 实际核查 | 差距 |
|----|-----------|----------|------|
| Agent 身份 | 5 个全部 active | 5 角色 / **11 个身份** / 3 条注册路径 | 🔴 已治理（v2.0 统一 snake_case） |
| 工具白名单 | 26 个注册成功 | 26 个入库，但 **0 个 handler 名匹配** | 🔴 5/26 可执行，21/26 仅审计 |
| 高风险工具 | 2 个 L3 必须人工审批 | L3 门禁逻辑正确，但 handler 未注册 → 无法执行 | 🟠 门禁生效、执行通路未通 |
| 成本护栏 | v1.0 生效，月度预算 $230 | `agent_budget.py` 仅在 Worker 内生效；调度路径绕过 | 🟠 |
| 审批队列 | 已有 2 条 PRODUCT_DECISION approved | 审批流 + RBAC + SLA 完整；但 `create_suggestion` 对低风险建议**自动审批后自动执行** | 🟡 低风险绕过人工 |
| 调度审计 | 5 个 Agent 每日运行入库 | 调度路径**不调 LLM、不写 `ai_agent_runs`** | 🔴 见 P2-1 |
| 提示词入库 | 5 个 Agent 提示词版本化 | 仅 `AGENT_PRODUCT_ANALYST v1` 有幂等种子；其余靠手工脚本 | 🟠 |
| Worker 部署 | 未提及 | **此前无 systemd 单元**，队列无人消费 | 🔴 已补齐（v2.0） |

完整评估、变更清单与验证命令见 `docs/agent_team_workflow_refactor.md`。

---

## 十二、下一步建议

1. **前端审批中心**: 在管理控制台增加审批队列页面，展示所有待审批项
2. **Agent运行监控**: 增加Agent运行状态监控面板，实时查看成本和调用量
3. **流程编排引擎**: 实现基于状态机的自动流程编排，减少人工干预
4. **评测集建设**: 为每个Agent建立≥20个代表性用例的评测集
5. **提示词版本管理**: 将提示词入库管理，支持版本化和A/B测试

---

## 十三、报告防造假规则（v1.0，2026-09-06 新增）

> 触发背景：营销经理每日分析出现「活动收入 $8,500 与客户分群收入 $529.88 对不平，
> 缺口 $7,970.12 未披露」及「无模型预期收益」等弄虚作假问题。用户明确要求：
> **各种报告禁止弄虚作假，实事求是**。

### 13.1 七条硬规则

| 编号 | 规则 | 落地位置 |
|------|------|----------|
| R1 | 每个数字必须带来源（广告平台/CRM/GA4/支付单），无来源数字禁止出现 | `marketing_manager.py` OUTPUT_SCHEMA.data_sources |
| R2 | 生成前自动对账：活动收入 == Σ订单收入；对不平强制披露缺口 | `services/report_truthfulness.py` `reconcile_revenue()` |
| R3 | 预测必须带模型：无公式的「预期收益/ROAS 提升」一律拒绝，只允许「若 X 则 Y」情景测算并标注假设 | `check_predictions()` + schema `basis`/`formula` 字段 |
| R4 | 小样本禁下结论：样本量 <30 只做描述性陈述，禁止统计性/评价性结论（如「价值 5.6 倍」「客单价极高」） | `check_sample_size()` |
| R5 | 未投放活动标 N/A：planned 活动 ROAS 不得写 0.00，不得给出「暂停/删除」指令 | `check_campaign_status()` |
| R6 | 输出完整性校验：报告截断/缺字段视为生成失败，禁止交付半句 | `check_output_completeness()` |
| R7 | 全链路落库：校验结果随 `ai_agent_runs` 审计，人工可复核 | `generic_agent.py` + daily 任务返回 `truthfulness` |

### 13.2 校验流程

```
营销数据 → 规范化指标（CampaignMetric / SegmentMetric）
        → validate_marketing_report()（R1-R7 全量校验）
        → 通过: 生成建议入库（agent_suggestions, pending_approval）
        → 失败: 只写入「收入对账失败」披露建议，禁止生成带数字结论
```

### 13.3 涉及文件

| 文件 | 变更 |
|------|------|
| `backend/app/services/report_truthfulness.py` | 新增：防造假校验服务（规则唯一来源） |
| `backend/app/tasks/daily_agents.py` | 营销经理每日任务强制跑校验；失败只披露缺口 |
| `backend/app/agents/marketing_manager.py` | 提示词 + OUTPUT_SCHEMA 升级 v2（data_sources/reconciliation/basis/formula） |
| `backend/update_agent_prompts.py` | 提示词库模板同步升级（Truthfulness Rules + Business Rules 7-12） |

### 13.4 验证结果

✅ report_truthfulness.py 语法校验通过  
✅ daily_agents.py 语法校验通过，营销经理任务接入校验  
✅ marketing_manager.py schema v2（required: data_sources + reconciliation）  
✅ update_agent_prompts.py 模板升级（Truthfulness Rules 段落）

---

**配置完成时间**: 2026-09-05  
**配置更新**: 2026-09-06（v1.1，报告防造假规则）  
**配置执行人**: Nuotao AI OS System  
**状态**: ✅ 全部完成并验证通过
