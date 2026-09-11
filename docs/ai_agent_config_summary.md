# Nuotao AI OS - AI Agent 管控流程配置总结

**版本**: v1.1  
**配置日期**: 2026-09-05  
**更新日期**: 2026-09-06  
**状态**: ✅ 已完成并验证通过

> v1.1 变更：新增 **报告防造假规则 v1.0**（report_truthfulness），
> 营销经理报告强制收入对账、来源标注、预测带模型、小样本禁结论，
> 详见本文档「十三、报告防造假规则」。

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

## 二、Agent注册配置（5个）

| Agent ID | 名称 | 领域 | 权限 | 模型 | 职责 |
|----------|------|------|------|------|------|
| product-manager | 产品经理AI | product | L2 | deepseek-chat | 1688选品分析、产品导入、图片合规检查、WooCommerce上架 |
| marketing-manager | 营销经理AI | marketing | L2 | deepseek-chat | AI文案生成、文案合规检查、AI生图（主图+详情图）、生图质量检查 |
| supply-chain-manager | 供应链经理AI | supply_chain | L2 | deepseek-chat | 库存同步、采购单创建、1688下单、采购物流追踪、物流信息同步 |
| customer-manager | 客户经理AI | customer | L1 | deepseek-chat | 客户咨询回复、订单状态查询、售后问题处理 |
| business-analyst | 商业分析师AI | analytics | L3 | deepseek-chat | 经营数据分析、成本模型、AI周报、选品模型评估 |

**权限级别说明**:
- L0: 公开读
- L1: 内部读
- L2: 提议（可创建草稿，需人工确认）
- L3: 高风险执行（必须人工审批）

---

## 三、工具白名单配置（26个工具，9个类别）

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
