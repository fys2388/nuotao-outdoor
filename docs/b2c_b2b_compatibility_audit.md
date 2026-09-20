# Nuotao AI OS B2C + B2B 双模式兼容性审计

> 文档版本：v2.3  
> 审计日期：2026-09-13  
> P0 修复日期：2026-09-13  
> P2-7 完成日期：2026-09-13  
> 当前迁移版本：`0046`  
> 审计范围：数据库、API、前端路由、状态机、权限与 Agent 架构  
> 决策文档：`docs/business_decisions/ADR/COMMERCE-001.md`

---

## 1. 结论

Nuotao AI OS 可以在现有模块化单体架构上升级为 B2C + B2B 一体化经营系统，不需要推倒重来。

P0 租户隔离、客户主数据、订单唯一键、B2B 状态机、旧接口下线与退款身份安全问题已关闭。P1-1 价格簿、版本、审批、阶梯价和订单价格快照已通过 `0036` 落地；P1-2 RFQ、版本化报价、双签合同和订单转换已通过 `0037` 落地；P1-3 发票、收款、核销、账龄和坏账处理已通过 `0038` 落地；P1-4 B2B 订单与 WMS/TMS 履约关联已通过 `0039` 落地；P1-5 Agent `business_scope`、工具、预算和审批隔离已通过 `0040` 落地；P2 汇率快照、成本币种换算和报告币种合并已通过 `0041` 落地；P2 B2B 客户门户自助 RFQ、报价决策、客户签署和合同转订单已通过 `0042` 落地；P2 代理商年度协议、三口径目标进度、连续阶梯返利、审批和结算登记已通过 `0043` 落地；P2 信用政策审批、风险评分、自动暂停/冻结、人工解除和信用保险首期已通过 `0044` 落地；P2 跨渠道身份链接、确定性冲突、人工合并、追加式同意账本和数据主体请求首期已通过 `0045` 落地；P2-7 多品牌、多法人、B2C/B2B/发票归因、自动归因、内部收入审批消除和合并报表首期已通过 `0046` 落地；P2-8 商品品牌批量绑定、品牌默认法人编辑、归因缺口和历史自动归因补全已完成首期。P2 首批 B2B Sales、Quotation、Collection 建议型 Agent 和 B2C/B2B 双渠道经营分析已落地。

产品定位正式确定为：

> **面向全球市场的 AI 原生 B2C + B2B 跨境电商经营操作系统。**

## 2. 审计方法与事实来源

本次审计基于：

- 当前 PostgreSQL 实际表结构、约束和索引。
- Alembic 迁移 `0001` 至 `0044`。
- `backend/app/models` 与 `backend/app/services` 的领域模型和服务逻辑。
- 管理端实际路由 `frontend/src/app/AppRoutes.tsx` 与导航配置。
- 浏览器实测管理端核心路由、接口错误和控制台错误。

本报告中的“缺失”表示当前数据库或代码中不存在，不包含推测性能力。

## 3. 当前能力矩阵

| 领域 | 当前能力 | 双模式结论 | 风险 |
|---|---|---|---|
| 商品主数据 | 单套商品模型 | 可作为共享底座 | 缺 `sales_scope` |
| 供应商/采购 | 共享供应链模型 | 可共用 | 无 B2C/B2B 分流必要 |
| 库存/WMS | `inventory_snapshots` 按工作区、商品、地点 | 可共用 | B2B 订单级预占、释放和出库已关联 |
| 物流/TMS | `shipment_records` 与轨迹事件 | 可共用 | B2B 订单和出库履约已关联 TMS 运单 |
| B2C 订单 | WooCommerce 订单同步与零售状态 | 继续独立状态机 | 缺业务模式和渠道级唯一键 |
| B2B 代理商 | 工作区隔离、统一客户账户、独立门户账号、信用状态和跨渠道身份 | 已形成自助、信用风控与隐私合规首期闭环 | 多品牌/多法人归因属于 P2-7 |
| B2B 价格 | 价格簿、版本、审批、阶梯价和客户专属价 | 已实现 | 多币种折算和协议返利属于 P2 |
| B2B 订单 | RFQ、报价、合同、订单、履约与应收闭环 | 已形成真实闭环 | 经营归因和多品牌报表仍待统一 |
| RFQ/报价/合同 | 独立模型、状态机、版本和审计 | 已实现 | 外部电子签属于后续接入 |
| 发票/应收/核销 | 发票、收款、不可变分录和账龄 | 已实现 | 多币种核销与税务属于后续扩展 |
| 汇率/合并分析 | 工作区级直接汇率快照、成本换算和报告币种合并 | 已实现首期 | 实时汇率源和税务折算属于后续扩展 |
| 品牌/法人/合并 | 品牌、法人、商品品牌、交易归因和内部收入消除 | P2-7/P2-8 首期完成 | 内部利润抵销、成本覆盖和法定合并属于后续扩展 |
| 客户主数据 | `customer_profiles` 为无 PII 行为档案 | 不完整 | 与 `b2b_agents` 无统一关系 |
| Agent | Runtime、审批、审计和 B2C/B2B 范围隔离 | 可复用 | B2B 专业 Agent 业务实现属于 P2 |
| 前端 | 已有 B2C/B2B/共享 URL 路由 | 已重构并验证 | 部分能力按缺口页明确禁用 |

## 4. 风险分级

### P0：继续扩展前必须修复

#### P0 修复结果

| 编号 | 问题 | 状态 | 实现与验证 |
|---|---|---|---|
| P0-1 | B2B 主表缺少工作区隔离 | 已修复 | 四张 B2B 表增加 `workspace_id`，唯一键按工作区重建，管理端、门户与服务查询全部带工作区条件 |
| P0-2 | 旧版 JSON B2B API 仍存在 | 已修复 | 路由返回 `410 Gone`，文件型服务实现已删除，回归测试覆盖 |
| P0-3 | B2B 订单状态可任意赋值 | 已修复 | 状态机限制合法迁移，非法迁移返回 `409`，状态变化写入带真实 actor 的审计事件 |
| P0-4 | 外部订单唯一键无法区分渠道 | 已修复 | 唯一约束改为 `(workspace_id, source, external_order_id)`，WooCommerce 查询统一限定 `source` |
| P0-5 | 客户主数据割裂 | 已修复 | 新增 `customer_accounts`，B2C 画像和 B2B 代理商均关联统一账户 |
| P0-6 | 售后退款写操作不安全 | 已修复 | 写接口要求登录与 RBAC，actor 来自认证用户，工作区来自认证绑定，不再信任 `X-Workspace-Id` |

补充加固：

- B2B 价格增加“等级价或客户专属价”二选一约束，防止空范围重复定价。
- B2B 订单与审计事件改为同一事务提交。
- WooCommerce Webhook 同时兼容标准 Base64 签名和旧 hex 签名。
- 审计文档与迁移版本的 P0 回归覆盖 B2B、订单、Webhook、退款和客户域。

#### P0-1 B2B 主表缺少工作区隔离（已修复）

受影响对象：

- `b2b_agents`
- `b2b_product_prices`
- `b2b_orders`
- `b2b_order_items`

`b2b_agents.agent_number` 和 `b2b_agents.email` 目前是全局唯一，导致不同工作区不能拥有相同代理商编号或邮箱；这不是品牌隔离，而是租户隔离缺陷。

必须：

- 所有表增加 `workspace_id`。
- 所有唯一约束改为 `(workspace_id, ...)`。
- 所有查询默认带工作区条件。
- Service 层不得接受前端自由传入的 workspace。

#### P0-2 旧版 JSON 文件 B2B API 仍存在（已修复）

旧入口：

```text
/api/v1/m5-m6/b2b/*
/api/v1/p3/b2b/*
```

它们写入进程本地 JSON 文件，缺少数据库事务、工作区隔离、统一鉴权和审计。它们与当前数据库版 B2B 服务并存，会造成重复数据和错误事实来源。

必须：

- 立即标记 deprecated。
- 禁止生产环境写操作。
- 完成调用方盘点后返回 `410 Gone`。
- 删除文件型存储实现，避免再次被引用。

#### P0-3 B2B 订单状态可任意赋值（已修复）

当前管理端状态接口可以将订单直接改为任意合法枚举值，没有检查合法迁移。

例如：

```text
delivered -> pending
cancelled -> shipped
```

必须建立状态机：

```text
draft
  -> pending_approval
  -> confirmed
  -> reserved
  -> processing
  -> shipped
  -> delivered
  -> completed

pending/confirmed -> cancelled
paid/partial -> refund/credit-note flow
```

非法迁移返回业务错误，并写事件日志。

#### P0-4 外部订单唯一键无法区分渠道（已修复）

当前：

```text
unique(workspace_id, external_order_id)
```

WooCommerce、Shopify、手工订单或 B2B 门户可能产生相同外部号码。

目标：

```text
unique(workspace_id, source, external_order_id)
```

#### P0-5 客户主数据割裂（已修复）

`customer_profiles` 保存无 PII 的行为画像；`b2b_agents` 保存企业联系人和登录信息。两者没有主数据关系。

后果：

- 同一个企业无法关联 B2B 报价、订单、应收、售后和互动。
- B2C 与 B2B 统一 CRM 无法建立。
- Agent 无法获得一致客户上下文。

必须先建立统一客户主数据，再让行为画像和 B2B 代理商引用它。

#### P0-6 售后退款写操作仍不安全（已修复）

退款服务中的 `_get_actor()` 仍可能返回硬编码 `system`。在当前身份链路未完成前，不应开放退款执行写操作。

前端已只展示真实只读数据并保留审批边界，后端仍需完成可信 actor、RBAC、审批和审计闭环。

### P1：进入真实 B2B 经营前必须完成

#### P1-1 阶梯价与价格版本（已实现，迁移 `0036`）

当前 `b2b_product_prices` 只有单个 `moq` 和 `wholesale_price`，不能表达：

```text
1-99        $22
100-499     $18
500+        $15
```

需要：

- 价格簿与价格等级。
- 数量区间。
- 生效期和版本。
- 客户/等级/专属价优先级。
- 审批与报价快照。
- 币种和汇率快照。

当前实现：

- `b2b_price_books`：默认价格簿、币种和状态。
- `b2b_price_versions`：草稿、提交审批、发布、驳回和历史版本。
- `b2b_price_tiers`：客户等级价与客户专属价的数量区间。
- 区间统一使用左闭右开：`min_quantity <= quantity < max_quantity`。
- 下单只解析已发布价格，并快照价格版本、阶梯价行、币种和单价。
- 缺少已发布价格时明确拒绝下单，不再使用成本价乘固定倍数兜底。

#### P1-2 RFQ 到订单链路（已实现，迁移 `0037`）

当前实现：

- `b2b_rfqs`、`b2b_rfq_items`：保存客户需求、商品、数量、目标价、贸易条件和交期。
- `b2b_quotes`、`b2b_quote_items`：报价草稿、审批、发送、接受、拒绝、版本复制和价格快照。
- `b2b_contracts`：合同草稿、待签署、客户签署、公司签署和自动生效。
- `b2b_orders.quote_id`、`b2b_orders.contract_id`：订单可反查报价和合同。
- `b2b_order_items.quote_item_id`：订单行可追溯到具体报价行。
- 订单转换要求报价已接受且合同已双签生效，并按工作区与报价唯一约束防止重复订单。
- 报价创建人不能审批自己的报价；过期报价不能发送或接受。

#### P1-3 发票与应收闭环（已实现，迁移 `0038`）

当前实现：

- `b2b_invoices`：订单一对一发票、金额快照、到期日、已收、坏账和余额。
- `b2b_receipts`：银行流水、收款金额、未核销余额和幂等键。
- `b2b_receivable_entries`：`charge`、`payment`、`write_off`、`adjustment` 不可变分录。
- 发票开票、部分/全额收款、跨发票核销、坏账核销和账龄统计。
- 核销同步更新发票、B2B 订单 `payment_status` 和代理 `current_balance`。
- 跨币种、超额、草稿发票核销和重复请求均被约束。

#### P1-4 B2B 订单与 WMS/TMS 履约关联（已实现，迁移 `0039`）

当前实现：

- `b2b_order_fulfillments`：订单履约主单、仓库、状态、预占/出库/送达时间和操作者。
- `b2b_order_fulfillment_items`：按订单行记录预占、出库和释放数量。
- `shipment_records.b2b_order_id`：B2B 出库物流可反查订单。
- 库存预占和释放使用行锁，防止并发超卖或重复释放。
- 出库同时扣减 `quantity` 与 `reserved`，并创建 TMS 运单和物流事件。
- 确认送达同步履约单、TMS 运单和 B2B 订单状态。
- 通用订单状态接口只允许 `confirmed` 和 `cancelled`；`processing`、`shipped`、`delivered` 只能由履约服务驱动。
- 重复预占、出库和送达请求返回同一履约结果，主要动作具备幂等边界。

#### P1-5 Agent 业务范围与权限隔离（已实现，迁移 `0040`）

`agents.domain` 只能表达产品、营销、供应链等领域，不能表达 B2C、B2B 或共享范围。

当前实现：

```text
agents.business_scope             = B2C | B2B | SHARED
agent_tasks.business_scope        = 任务范围快照
agent_executions.business_scope   = 执行范围快照
agent_tools.business_scope        = 工具可服务范围
agent_*_policies.business_scope   = 预算/执行策略范围
agent_approval_roles.business_scope = 审批角色范围
agent_approvals.business_scope    = 审批对象范围快照
```

- B2C Agent 只能调用 B2C 或 SHARED 工具，B2B Agent 只能调用 B2B 或 SHARED 工具。
- SHARED Agent 可为 B2C、B2B 或明确共享任务服务；未声明时按历史 B2C 安全口径回落。
- 非共享 Agent 创建任务时只能继承自身范围，不能通过任务、版本或注册更新自动扩权。
- 策略按业务范围独立版本化和回退，预算使用量按执行范围统计。
- 审批 RBAC 按业务范围匹配，B2C 审批人不能处理 B2B 审批；旧数据默认 `SHARED`。
- 高风险工具仍进入统一审批队列，不因业务范围扩大而绕过人工确认。
- Agent Runtime、Agent Operations 与 Agent Platform 入口要求管理端登录，工作区由认证身份绑定，不再接受调用方通过请求头选择租户。
- 价格草稿、B2B 履约动作和 Agent 运营写操作要求 `operator`；价格发布/驳回继续要求 `admin`，审批中心继续执行工作区级 RBAC。

#### P1 完成审计矩阵（2026-09-13）

| P1 能力 | 数据与约束 | 服务/API | 前端入口 | 自动与人工证据 |
|---|---|---|---|---|
| 价格版本与阶梯价 | `0036`：价格簿、版本、客户等级价/专属价、数量区间与审批约束 | 已发布价格解析、版本快照、MOQ、提交/发布/驳回；写接口要求 operator，审批要求 admin | `/b2b/pricing` | 业务测试通过；迁移往返通过；浏览器路由和空态/错误态通过 |
| RFQ、报价与合同 | `0037`：RFQ、报价版本、合同、订单/报价/合同关联 | RFQ 状态机、报价复制/审批/接受、合同双签、唯一订单转换 | `/b2b/rfqs`、`/b2b/quotes` | 业务测试通过；迁移往返通过；浏览器路由和真实接口返回通过 |
| 发票、应收与收款 | `0038`：发票、收款、不可变应收分录、幂等键和余额约束 | 开票、核销、部分/全额收款、坏账、账龄统计；写接口要求 operator/admin | `/b2b/receivables` | 业务测试通过；迁移往返通过；浏览器路由和真实接口返回通过 |
| B2B 履约关联 | `0039`：履约单、履约行、库存预占与 TMS 关联 | 预占、释放、出库、送达状态机；重复动作幂等；写接口要求 operator | `/b2b/orders` 履约详情 | 业务测试通过；`0038 -> 0039` 往返通过；浏览器路由通过 |
| Agent `business_scope` | `0040`：Agent、任务、执行、工具、策略、审批角色和审批范围 | 范围继承不放宽、工具/预算/审批隔离；Runtime/Operations/Platform 登录与工作区绑定 | `/b2b/ai`、`/ai/agents` | 业务与 Agent 组合测试通过；`0039 -> 0040` 往返通过；浏览器路由通过 |

### P2：规模化后增强

- B2B Sales、Quotation、Collection Agent 已完成首期建议闭环：RFQ 优先级、发布价/成本/目标毛利报价建议、账龄/信用/回款优先级，并幂等进入统一人工审批中心；证据、审批记录和 `manual_review` 无业务写操作状态可追溯。
- 渠道毛利、客户贡献、账龄、库存周转按 B2C/B2B 双维度分析。**已完成首期**：`GET /api/v1/analytics/channel-performance` 返回渠道收入、订单、件数、客单价、可信毛利、退款、广告投入、ROAS、客户贡献、应收账龄和商品库存周转，管理端入口为 `/analytics/channels`。
- 经营利润只读取订单 `profit_snapshot.contribution_margin` 或 B2B 订单行可追溯的 `ProductCost`。没有成本证据时返回 `missing`，部分覆盖返回 `partial`，禁止按收入比例估算。
- 所有金额按业务模式与币种分组；不同币种不汇总收入、利润或成本覆盖率。多币种报告只在单条渠道内显示覆盖率，全局质量状态只汇总各渠道的可信状态。
- 多品牌、多法人、多币种合并报表。**P2-7 已完成首期（`0046`）**：
  `brands`、`legal_entities` 和 `commerce_attributions` 统一保存品牌、法人与内部交易
  归因；商品品牌、订单和发票支持自动归因；管理员批准后按品牌、法人、业务模式和
  币种消除内部收入。未归因数据保持显式缺口，内部交易利润不做会计级模拟。
- 商品品牌与归因治理。**P2-8 已完成首期**：未绑定品牌商品可批量绑定，批量操作只补
  空、不覆盖已有品牌并逐项写审计；品牌可编辑默认销售法人；未归因订单/发票、混品牌
  和缺少法人证据可查询，具备完整证据的历史交易可一键补全自动归因。
- 多币种合并已补齐汇率底座。**已完成首期**：`exchange_rates` 保存工作区级直接汇率、来源、凭证和维护人；渠道经营分析支持 `reporting_currency`，B2B 毛利先把采购成本换算到订单币种再计算；缺失汇率明确拒绝，不自动推断反向汇率。
- 汇率管理入口为 `/settings/currency-rates`，内部 API 为 `/api/v1/admin/currency-rates`。
- 代理商分级返利、年度协议与目标管理。**已完成首期（`0043`）**：支持 `ordered / invoiced / paid` 三种目标口径、连续阶梯返利、汇率换算、职责分离审批和结算登记；协议审批使用代理商行锁避免并发产生重叠生效协议。
- 信用保险、风控评分和自动冻结。**已完成首期（`0044`）**：信用政策先审批后执行，评分基于敞口、逾期、账龄和坏账事实；`hold/frozen` 统一阻断报价转订单与门户下单，人工解除、保单和索赔均具备工作区隔离与审计；保险只缓释风险，不自动提高额度。管理端入口为 `/b2b/credit`。
- B2B 客户门户：已发送报价接受/拒绝、客户签署和生效合同幂等转订单；门户与内部管理端使用独立令牌，所有查询强制限定 `workspace_id + agent_id`。**已完成首期（`0042`）**。
- 跨渠道客户身份合并与隐私合规流程。**已完成首期（`0045`）**：工作区级
  HMAC 身份链接、确定性冲突、管理员合并、追加式同意账本、营销发送门禁和数据主体
  请求台账均具备工作区隔离与审计；管理端入口为 `/settings/customer-data`。

## 5. 目标领域模型

```text
                         Product Master
                               |
              +----------------+----------------+
              |                                 |
         B2C Channel                       B2B Channel
              |                                 |
        Consumer Customer                 Business Customer
              |                                 |
        Retail Order                    RFQ -> Quote -> Contract
              |                                 |
         Payment/Refund                    B2B Order / PO
              |                                 |
              +---------------+-----------------+
                              |
                  Inventory / Fulfillment / TMS
                              |
                     Invoice / Receipt / AR
                              |
                      Event Log / BI / Agents
```

### 5.1 统一客户

建议新增 `customer_accounts` 作为稳定主数据：

```text
id
workspace_id
customer_number
customer_type
business_model
display_name
status
country
default_currency
owner_user_id
created_at / updated_at
```

PII 联系人信息按现有 L4 安全要求加密或拆分到受控表。`customer_profiles` 只保留行为画像，通过 `customer_account_id` 关联；`b2b_agents` 通过同一字段关联。

### 5.2 订单

保留两套交易表：

```text
orders
  business_model = B2C

b2b_orders
  business_model = B2B
  quote_id
  contract_id
  customer_account_id
  po_number
  inventory_reservation_id
  warehouse_id
  shipment_id
```

统一分析层按业务模式汇总，禁止在单笔订单上写 `BOTH`。

### 5.3 价格

```text
b2b_price_books
  id / workspace_id / name / currency / customer_id / tier
  effective_from / effective_to / version / status

b2b_price_tiers
  id / price_book_id / product_id / min_quantity / max_quantity
  unit_price / status
```

订单明细保存解析后的 `unit_price_snapshot`、`discount_snapshot`、`tax_snapshot`、`cost_snapshot` 和 `price_book_version`。

## 6. 迁移顺序

采用 expand-migrate-contract，每一步都可在不丢数据的前提下独立回滚。

| 迁移 | 内容 | 上线门槛 |
|---|---|---|
| `0035` | P0 合并迁移：B2B 工作区隔离、`customer_accounts`、订单 `business_model/source` 渠道级唯一键、B2B 价格范围约束 | 已实现；跨租户、订单、退款和客户测试通过 |
| `0036` | 价格簿、阶梯价、版本与审批 | 已实现；数量边界、专属价优先、区间冲突、版本不可变、跨租户和订单快照测试通过 |
| `0037` | RFQ、报价、合同、订单快照 | 已实现；状态机、双方签名、信用额度、重复转换和报价到订单追溯测试通过 |
| `0038` | 发票、收款、应收与核销 | 已实现；发票唯一性、部分/全额收款、幂等核销、跨币种、坏账、账龄和跨租户测试通过 |
| `0039` | B2B 订单预占、释放、出库、TMS 运单和送达同步 | 已实现；库存原子性、幂等、状态绕过、工作区隔离和 PostgreSQL 升降级测试通过 |
| `0040` | Agent `business_scope`、工具权限与预算 | 已实现；跨范围调用、任务/策略/预算/审批隔离、防扩权和 PostgreSQL 升降级测试通过 |
| `0041` | 可审计汇率快照与报告币种前置能力 | 已实现；直接汇率、历史生效日、跨租户隔离、成本币种换算、无汇率拒绝和 PostgreSQL 升降级测试通过 |
| `0042` | B2B 门户报价决策人审计 | 已实现；客户范围隔离、报价接受/拒绝、客户签署、重复订单转换幂等和 PostgreSQL 升降级测试通过 |
| `0043` | 代理商年度协议、目标进度与分级返利 | 已实现；三口径统计、连续阶梯、直接汇率、职责分离、快照冻结、并发锁和 PostgreSQL 升降级测试通过 |
| `0044` | B2B 信用政策、风险评分、自动状态、保险保单与索赔 | 已实现；政策审批、评分可复现、订单阻断、职责分离、工作区隔离、保险覆盖和 PostgreSQL 升降级测试通过 |
| `0045` | 跨渠道身份链接、人工合并、同意账本与数据主体请求 | 已实现；确定性冲突、管理员合并、EDM 同意门禁、访问/导出、删除/限制处理、工作区隔离和 PostgreSQL 升降级测试通过 |
| `0046` | 品牌、法人、商品品牌归因、交易归因和内部收入消除 | 已实现；工作区唯一键、自动归因、归因更新、管理员审批、金额上限、内部收入消除、合并币种和多维报表测试通过 |

### 回填原则

- 先新增可空列，再回填，最后切换 `NOT NULL`。
- 使用明确的 `default_workspace_id` 映射；无法归属的数据进入隔离表。
- 新旧约束并存期间执行双读校验，不直接删除旧列。
- 每步迁移前执行数据库备份。
- 大表创建索引使用并发索引，避免阻塞生产请求。

## 7. API 与权限契约

### 7.1 API 分面

```text
/api/v1/admin/b2b/*       内部管理端，RBAC 管理权限
/api/v1/b2b-portal/*      代理商门户，只能访问当前代理商
/api/v1/orders/*          B2C 订单
/api/v1/inventory/*       共享库存只读/受控服务
/api/v1/shipments/*       共享履约与物流
/api/v1/admin/b2b/orders/{id}/fulfillment/*  B2B 订单履约动作
/api/v1/admin/currency-rates              汇率查询、解析和管理
/api/v1/admin/consolidation/*             品牌、法人、商品品牌和交易归因
/api/v1/analytics/consolidation           品牌/法人多维合并报表
/api/v1/admin/consolidation/product-brand-gaps        未绑定品牌商品
/api/v1/admin/consolidation/product-brands/bulk       商品品牌批量补空
/api/v1/admin/consolidation/attribution-gaps          订单/发票归因缺口
/api/v1/admin/consolidation/attribution-gaps/reconcile 历史自动归因补全
```

### 7.2 通用要求

- 所有写接口要求可信 actor 和 RBAC。
- 所有创建订单/报价/收款接口支持 `Idempotency-Key`。
- 金额使用 Decimal，不使用浮点数。
- 所有列表支持分页和稳定的排序。
- 所有状态转换使用专门动作接口，禁止通用 `PATCH status`。
- 所有错误返回统一业务错误码。
- 所有关键写操作写 `event_log`，包含 `workspace_id`、actor、trace_id。

### 7.3 高风险动作

以下动作必须进入审批队列：

- 专属价格和合同价发布。
- 超出信用额度的订单。
- 大幅折扣或低于成本报价。
- 人工库存调整。
- 订单取消、退款和坏账核销。

## 8. Agent 分层

```text
B2C
  Product Agent
  Marketing Agent
  Customer Agent
  Pricing Agent
  Retention Agent

B2B
  Lead Agent
  Sales Agent
  Quotation Agent
  Account Agent
  Collection Agent

SHARED
  Supply Chain Agent
  Inventory Agent
  Logistics Agent
  Business Analyst
```

Agent 读取数据时必须同时满足：

```text
workspace_id
+ business_scope
+ 工具白名单
+ 数据分级
+ 审批策略
```

## 9. 前端治理

已完成的治理：

- URL 路由和统一 AppShell。
- B2C、B2B、共享底座菜单分流。
- 真实数据接口接入。
- API 失败不回退模拟数据。
- 未完成后端能力显示明确缺口页。
- WMS 使用真实只读库存接口。
- 禁用假成功、模拟订单、模拟周报和模拟内容指标入口。

后续约束：

- 页面不得自行推导工作区、价格、库存结果或审批状态。
- B2C、B2B 页面必须使用后端业务模式过滤。
- 能力缺口页只有在数据模型、API、权限和审计全部完成后才能替换。
- 导航、路由和业务范围配置保持单一事实来源。

## 10. 测试方案

### 10.1 数据库

- 迁移升级/降级。
- 工作区隔离。
- 唯一约束与并发写入。
- 阶梯价边界、生效期和版本。
- 金额精度和币种。

### 10.2 服务与 API

- 状态机合法/非法迁移。
- RFQ -> 报价 -> 合同 -> 订单 -> 发票 -> 收款。
- 库存预占、释放、出库和取消。
- RBAC、actor 和 idempotency。
- 跨租户越权、价格篡改和审批绕过。

### 10.3 Agent

- B2C/B2B/Shared 工具白名单。
- PII 和 L2/L3 数据边界。
- 高风险建议必须进入审批。
- 无证据时不得生成经营结论。
- 模型预算和降级链。

### 10.4 前端与端到端

- 桌面和移动端导航。
- API 成功、空数据、错误、未登录和无权限状态。
- 不存在模拟数据回退和假成功提示。
- 关键路由无控制台错误和横向溢出。

### 10.5 P0 回归结果

- `tests/test_b2b_p0.py`：6 项通过。
- B2B、订单、Webhook、退款、客户组合回归：52 项通过。
- `compileall`、迁移 head、模型元数据和变更文件 Ruff `F` 规则检查通过。

### 10.6 P1-4 回归结果

- P0、价格、销售、财务、履约组合回归：45 项通过。
- 供应链与连接器回归：22 项通过。
- PostgreSQL `0038 -> 0039 -> 0038 -> 0039` 迁移往返通过，外键和索引验证通过。
- 前端 `npm run typecheck` 与 `npm run build` 通过。
- 现有 `b2b_product_prices` 无空范围或双范围脏数据。

### 10.6 P1-1 回归结果

- `tests/test_b2b_pricing.py`：6 项通过。
- `0036` 在本地 PostgreSQL 完成升级、降级和再次升级验证。
- 前端 `npm run typecheck` 与 `npm run build` 通过。
- `/b2b/pricing` 浏览器验收通过，控制台无错误和警告。

### 10.7 P1-2 回归结果

- `tests/test_b2b_sales.py`：7 项通过。
- P0 与 P1-1 回归共 12 项通过。
- `0037` 在本地 PostgreSQL 完成升级、降级和再次升级验证。
- 前端 `npm run typecheck` 与 `npm run build` 通过。
- `/b2b/rfqs`、`/b2b/quotes` 和合同页签浏览器验收通过，桌面与移动端无横向溢出，控制台无错误和警告。

### 10.8 P1-3 回归结果

- `tests/test_b2b_finance.py`：6 项通过。
- P0、P1-1、P1-2 回归共 19 项通过。
- `0038` 在本地 PostgreSQL 完成升级、降级 `0037` 和再次升级验证。
- 前端 `npm run typecheck` 与 `npm run build` 通过。
- `/b2b/receivables` 浏览器验收通过，桌面和移动端无横向溢出，控制台无错误和警告。

### 10.9 P1-4 回归结果

- P0、价格、销售、财务和履约组合回归通过。
- 供应链与连接器回归 22 项通过。
- PostgreSQL `0038 -> 0039 -> 0038 -> 0039` 迁移往返通过。
- 前端 `npm run typecheck` 与 `npm run build` 通过。
- B2B 订单详情在桌面和 390px 移动端完成“确认 -> 预占 -> 出库 -> 送达”验收。
- B2B Agent 建议在 `/b2b/ai` 与 `/ai/suggestions` 完成桌面和 390px 移动端验收，证据详情、人工审批记录和无自动写操作提示可见。

### 10.10 P1-5 回归结果

- `tests/test_agent_business_scope.py`：6 项通过。
- Agent Runtime、Operations、Platform、Lifecycle、RBAC 与 SLA 组合回归 115 项通过。
- PostgreSQL `0039 -> 0040 -> 0039 -> 0040` 迁移往返通过，范围列、检查约束、索引和策略唯一键验证通过。
- 前端 `npm run typecheck` 与 `npm run build` 通过；Agent 运行页展示业务范围并支持筛选。
- B2C 调用 B2B 工具、B2B 调用 B2C 工具、跨范围任务、跨范围预算和跨范围审批均被拒绝。
- 五项 P1 加权限回归共 47 项通过；匿名访问 Agent Runtime、Agent Operations 和 B2B 管理接口返回 `401`，viewer 写操作返回 `403`。
- Agent Runtime 与业务范围回归验证工作区头不能冒充其他租户。
- `frontend/e2e/b2b-p1-smoke.spec.ts` 通过：登录后依次加载 `/b2b/pricing`、`/b2b/rfqs`、`/b2b/quotes`、`/b2b/orders`、`/b2b/receivables`、`/b2b/ai`，无 401/403 API 响应和控制台错误。

### 10.11 P2-1 双渠道经营分析回归结果

- `tests/test_channel_analytics.py` 与 `tests/test_dashboard_profit_snapshot.py`：7 项通过。
- P0、价格、销售、财务、履约、Agent 范围与 B2B Agent 组合回归：46 项通过。
- 跨租户数据隔离、B2C/B2B 利润归因、应收账龄、库存周转和跨币种不合并规则均有测试覆盖。
- 旧的 `/api/v1/dashboard/daily-metrics` 与 `/api/v1/dashboard/product-performance` 已返回 `410 Gone`，不再提供 60% 收入估算或模拟商品排行。
- 前端 `npm run typecheck` 与 `npm run build` 通过；`/analytics/channels` 页面已接入真实接口。

### 10.12 P2-2 汇率与报告币种回归结果

- `tests/test_currency_service.py`：5 项通过，覆盖历史生效汇率、跨工作区隔离、重复货币对、显式报告币种合并和 B2B 成本币种换算。
- 渠道分析、价格、销售和财务组合回归通过。
- PostgreSQL `0040 -> 0041 -> 0040 -> 0041` 迁移往返通过，表、唯一约束、正数约束和索引验证通过。
- 前端 `/settings/currency-rates` 汇率管理页和 `/analytics/channels` 报告币种选择完成类型检查与生产构建。

### 10.13 P2-3 B2B 客户门户回归结果

- `tests/test_b2b_portal_sales.py`、`tests/test_b2b_sales.py` 与 `tests/test_p1_api_authorization.py`：19 项通过。
- 覆盖门户 RFQ 自动归属当前客户、客户 A 不能读取客户 B 数据、报价接受/拒绝操作人审计、客户签署、重复转订单返回同一订单、内部令牌不能访问门户和 `X-Workspace-Id` 不能切换租户。
- PostgreSQL `0041 -> 0042 -> 0041 -> 0042` 迁移往返通过，客户决策人字段、升级与降级流程验证通过。
- `frontend/e2e/b2b-portal.spec.ts` 在 Google Chrome 中通过：独立门户登录后进入 `/portal`，工作台和商品、RFQ、报价、合同、订单、账户路由均正常，无 401/403 API 响应和控制台错误。
- `frontend/e2e/b2b-p1-smoke.spec.ts` 管理端 B2B 六路由回归通过，门户改造未破坏内部销售链路。

### 10.14 P2-4 代理商年度协议与返利回归结果

- `tests/test_b2b_agreements.py`：8 项通过，覆盖跨工作区隔离、连续阶梯校验、三口径目标、历史直接汇率、快照冻结、职责分离审批、终止与结算。
- 协议审批仅终止期间重叠的 active 协议，并锁定代理商行；非重叠周期协议可以并存，并发审批不会产生两份重叠生效协议。
- 早于协议生效期的进度返回 `0`；提交后的返利快照不受后续销售事实影响；开放尾档可正确更新。
- PostgreSQL `0042 -> 0043 -> 0042 -> 0043` 迁移往返通过，表、检查约束、索引和唯一约束验证通过。
- Google Chrome `frontend/e2e/b2b-agreements.spec.ts` 通过，覆盖协议创建、审批、真实订单进度、返利计算、审批和结算登记。
- `frontend/e2e/b2b-p1-smoke.spec.ts` 在既有 B2B 六路由基础上加入 `/b2b/agreements`，回归通过。
- 协议、财务、履约、门户、价格、销售、P0 和权限组合回归 29 项通过；`npm run typecheck` 与 `npm run build` 通过。

### 10.15 P2-5 信用风控、自动冻结与信用保险回归结果

- `tests/test_b2b_credit.py` 覆盖政策职责分离与版本替代、额度利用率与逾期评分、自动暂停/冻结开关、人工解除、保险折扣、索赔状态机和工作区隔离。
- `tests/test_b2b_credit_api_authorization.py` 覆盖匿名 `401`、viewer/operator 权限边界、admin 政策审批与人工状态操作，以及政策、风险和保险读取的工作区隔离。
- `tests/test_b2b_sales.py` 与 `tests/test_b2b_portal_sales.py` 覆盖真实报价转订单和门户下单入口；`hold/frozen` 客户被阻断，超额度订单被拒绝，信用业务错误统一返回 `409`。
- PostgreSQL `0043 -> 0044 -> 0043 -> 0044` 迁移往返通过，五张信用风控表、代理信用状态列、active 政策唯一索引和状态查询索引验证通过。
- staging Neon 数据库已执行 `0044`，当前版本为 `0044`。
- `frontend/e2e/b2b-credit-risk.spec.ts` 在 Google Chrome 中完成政策创建/提交/审批、风险评估、自动暂停、人工解除和保险覆盖展示；无 API `401/403/500` 和控制台错误。
- `frontend/e2e/b2b-p1-smoke.spec.ts` 已将 `/b2b/credit` 纳入 B2B 路由冒烟；`npm run typecheck` 与 `npm run build` 通过，仅有既有 `antd-vendor` 大包告警。

### 10.16 P2-6 跨渠道客户身份与隐私合规回归结果

- `tests/test_customer_identity_privacy.py`、`tests/test_customer_data_api_authorization.py` 与 `tests/test_edm_send_service.py` 共 30 项通过。
- 覆盖工作区级 HMAC、规范化一致性、跨租户哈希隔离、确定性身份冲突、管理员合并、业务外键重定向、同意事件优先级、EDM 撤回阻断、访问/导出、匿名化删除、限制处理和 API RBAC。
- 身份合并先写入冲突证据，再重定向业务外键；合并完成后目标账户冲突链接提升为 `verified`，来源重复链接标记为 `merged`，避免后续再次产生错误冲突。
- 数据主体访问/导出快照中的 `datetime` 统一转换为 ISO 字符串，修复 JSONB 执行阶段的序列化 `500`。
- PostgreSQL `0044 -> 0045 -> 0044 -> 0045` 迁移往返通过，五张治理表、账户合并字段、订单/订阅关联列和唯一约束验证通过。
- `frontend/e2e/customer-data.spec.ts` 在 Google Chrome 中完成桌面端真实业务链路：身份冲突、合并审批、合并执行、同意授权/撤回，以及访问请求“登记 -> 核验 -> 批准 -> 执行 -> 已完成”。
- 390px 移动端通过：无横向溢出、无 API `401/403/500`、无控制台错误。
- `npm run typecheck` 与 `npm run build` 通过；仅保留既有 `antd-vendor` 大包告警。
- 生产开放边界：必须配置 `CUSTOMER_IDENTITY_HMAC_KEY` 并完成 staging 迁移、密钥/备份恢复演练和法务保留规则确认后，才能开放删除与限制处理。

### 10.17 P2-7 多品牌、多法人与内部交易合并回归结果

- `tests/test_consolidation.py` 与
  `tests/test_consolidation_api_authorization.py`：12 项通过。
- 合并、B2B 销售、B2B 财务和权限组合回归：25 项通过。
- 覆盖工作区隔离、品牌/法人唯一编码、商品品牌推断、B2C 订单入库自动归因、B2B
  报价转订单自动归因、发票继承归因、归因缺口可见、管理员审批和消除金额上限。
- PostgreSQL 当前迁移版本为 `0046`；迁移实现包含品牌、法人、商品品牌和归因表，
  并在降级时按外键依赖顺序删除。
- `frontend/e2e/consolidation.spec.ts` 在 Google Chrome 中通过：创建两个法人和
  一个品牌、登记 B2B 内部交易、管理员批准、刷新归因状态和合并报表。
- E2E 验证账面收入 `200.00`、内部交易 `200.00`、外部收入 `0.00`；审批请求只发送
  一次，无 API `401/403/500` 和控制台错误。
- 390px 移动端无横向溢出；`npm run typecheck` 和 `npm run build` 通过。
- 明确边界：本期只做内部收入消除，不做内部利润会计级抵销；后续需要买方侧配对
  分录和集团会计规则。
### 10.18 P2-8 商品品牌归因治理回归结果

- `tests/test_consolidation.py` 与
  `tests/test_consolidation_api_authorization.py`：17 项通过。
- 合并、B2B 销售、B2B 财务和权限组合回归：32 项通过。
- 覆盖未绑定品牌商品查询、批量补空、不覆盖已有品牌、逐项结果、归因缺口原因、
  历史自动归因补全、工作区隔离和 viewer 写权限拒绝。
- `frontend/e2e/consolidation.spec.ts` 在 Google Chrome 中通过完整治理链路：
  商品未绑定品牌、批量绑定、品牌缺少默认法人、页面编辑品牌、自动补全历史归因和
  合并报表出现 `300.00` 收入。
- Chrome 回归 3 项全部通过，包括原有多品牌合并流程和 390px 无横向溢出检查；
  无 API `401/403/500` 和控制台错误。
- `npm run typecheck` 与 `npm run build` 通过。
- 下一项 P2-9 应先做成本覆盖治理：列出缺少有效 `ProductCost` 的商品和交易，提供
  可审计的成本补齐入口；内部利润抵销在成本证据完整前保持禁用。

## 11. 上线判定

只有满足以下条件，双模式 B2B 才能从试点转为生产：

- P0 全部关闭。
- P1 至少完成价格、订单状态机、客户主数据和应收闭环。
- 旧 JSON API 已下线。
- 多工作区安全测试通过。
- 真实业务数据完成一条端到端验收。
- 备份与恢复演练通过。

在此之前，管理端可以继续使用真实只读和受控管理能力，但不得开启未经审批的批量下单、库存扣减、退款和财务核销。
