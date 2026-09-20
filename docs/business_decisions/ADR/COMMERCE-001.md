# ADR COMMERCE-001 — B2C + B2B 一体化商务架构

> 状态：**Accepted**（2026-09-13）  
> 决策编号：COMMERCE-001  
> 关联：`docs/b2c_b2b_compatibility_audit.md`、`docs/frontend_b2c_b2b_architecture.md`、`docs/project_architecture.md`

---

## Context（背景）

Nuotao AI OS 原规划把 B2B 放在海外仓之后作为后续阶段。当前业务已经明确需要同时服务：

- B2C：独立站、平台、社媒与零售消费者。
- B2B：零售客户、批发客户、代理商、分销商与战略客户。

现有系统已经有 B2B 代理商、价格、订单和客户门户的第一版实现，但这些实现缺少多工作区隔离、阶梯价、报价、合同、账期、应收和统一客户主数据。继续按“先做 B2C，未来再补 B2B”的方式扩张，会造成订单、价格、客户和权限层的大规模重构。

因此产品定位正式调整为：

> **Nuotao AI OS：面向全球市场的 AI 原生 B2C + B2B 跨境电商经营操作系统。**

## Decision（决策）

### 1. 共用底座，业务分流

商品主数据、供应商、采购、库存、WMS、TMS、CRM、Agent Runtime、AI 审计和 BI 作为共享底座。

销售域按业务模式分流：

- B2C：消费者、零售价格、支付后履约、退款售后。
- B2B：企业客户、价格簿、阶梯价、RFQ、报价、合同、PO、账期、发票、收款与核销。

禁止建立两套互不相通的商品、库存、供应商和客户孤岛。

### 2. 订单保留双状态机，分析层统一

- B2C 订单继续使用零售履约状态机。
- B2B 订单使用询盘到回款的批发状态机。
- 不允许把 B2B 的报价、合同、账期硬塞进 B2C 订单状态。
- 经营分析使用统一只读模型或聚合视图，按 `business_model` 汇总。

说明：`BOTH` 只用于商品或渠道能力，不用于单笔订单。单笔订单必须明确为 `B2C` 或 `B2B`。

### 3. 统一值域

```text
product.sales_scope   = B2C | B2B | BOTH
order.business_model  = B2C | B2B
customer_type         = CONSUMER | RETAILER | WHOLESALER | DISTRIBUTOR | AGENT | STRATEGIC
price_channel         = B2C | B2B
price_tier            = RETAIL | WHOLESALE_1 | WHOLESALE_2 | DISTRIBUTOR | CONTRACT
agent.business_scope  = B2C | B2B | SHARED
```

### 4. 所有租户业务表必须工作区隔离

`b2b_agents`、`b2b_product_prices`、`b2b_orders`、`b2b_order_items` 必须补齐 `workspace_id`。所有唯一键和查询索引必须包含 `workspace_id`。

外部订单号唯一键从：

```text
(workspace_id, external_order_id)
```

调整为：

```text
(workspace_id, source, external_order_id)
```

避免 WooCommerce、Shopify、手工录入等渠道出现相同外部单号时互相冲突。

### 5. B2B 商业链路采用版本化、快照化设计

目标闭环：

```text
RFQ
  -> 报价单（可多版本）
  -> 客户接受/合同
  -> PO / B2B 订单
  -> 库存预占或采购
  -> 出库与 TMS 物流
  -> 发票
  -> 收款与应收核销
```

订单明细必须保存下单时的商品、价格、折扣、税率、币种和成本快照，后续商品或价格变更不得改写历史订单。

### 6. Agent 按业务边界分层

```text
B2C Agents
  Product / Marketing / Customer / Pricing / Retention

B2B Agents
  Lead / Sales / Quotation / Account / Collection

Shared Agents
  Supply Chain / Inventory / Logistics / Business Analyst
```

Agent Registry 使用 `business_scope` 控制工具、数据、提示词和审批权限。Agent 仍然是提议者，高风险动作必须进入 Human-in-the-loop 审批。

### 7. 废弃旧版文件型 B2B API

`/api/v1/m5-m6/b2b/*` 与 `/api/v1/p3/b2b/*` 依赖进程本地 JSON 文件，缺少工作区隔离、数据库审计、状态机和统一权限。正式入口只保留：

- 管理端：`/api/v1/admin/b2b/*`
- 代理商门户：`/api/v1/b2b-portal/*`

旧接口先标记 deprecated，再通过迁移窗口返回 `410 Gone`，禁止继续写入 JSON 文件。

## Consequences（后果）

### 正面

- 同一个商品、库存和供应链可同时服务 B2C 与 B2B。
- 报价、合同、账期和应收拥有独立且可审计的状态机。
- 经营分析可以按业务模式准确归因。
- 多工作区和多品牌扩展不需要再次重构 B2B 主表。
- Agent 权限可以按 B2C、B2B、共享能力最小授权。

### 成本

- 需要执行一系列数据库迁移和旧数据回填。
- 管理端、门户端和服务层需要统一业务模式上下文。
- 发票、报价、合同和应收模型会增加业务复杂度。
- 旧 B2B JSON API 需要下线并处理潜在调用方。

### 实施约束

- 采用 expand-migrate-contract，禁止一次性重写现有生产表。
- 数据回填必须使用工作区映射，无法归属的数据进入隔离表等待人工处理。
- 新旧接口迁移期间必须双读校验，禁止静默丢单。
- 未完成状态机、权限和审计前，不开放真实 B2B 写操作。

## Alternatives（备选与否定理由）

| 方案 | 成本 | 优点 | 缺点 | 适用场景 |
|---|---|---|---|---|
| B2C 主表 + 后期补 B2B | 初期低，后期高 | 起步快 | 订单、价格、客户和权限大概率重构 | 仅做少量批发，且不计划系统化 B2B |
| 单套通用订单表 | 中 | 报表简单 | 两套状态机耦合，字段大量为空，流程难维护 | 订单模型高度一致的轻量业务 |
| B2C/B2B 两套完全独立系统 | 高 | 边界简单 | 商品、库存、供应链和客户重复，数据无法飞轮 | 两个独立公司或完全隔离的渠道 |
| 本 ADR：共享底座 + 业务分流 + 统一分析 | 中高 | 可演进、隔离清晰、支持数据飞轮 | 需要严格的领域建模和迁移纪律 | 当前 Nuotao 的 B2C + B2B 双轮模式 |
| 继续使用 JSON 文件型 B2B | 表面低 | 改动少 | 无租户隔离、无审计、无法多实例部署 | 仅本地演示，不可用于生产 |

## Rollout（落地顺序）

1. 完成本 ADR 与兼容性审计评审。
2. 建立字段字典、状态机和 API 契约。
3. 迁移 `0035`：B2B 工作区隔离与租户唯一键。
4. 迁移 `0036`：统一客户主数据关系。
5. 迁移 `0037`：RFQ、报价、合同与订单快照（已完成）。
6. 迁移 `0038`：发票、收款、应收与核销（已完成）。
7. 迁移 `0039`：B2B 订单与 WMS/TMS 履约关联（已完成）。
8. 迁移 `0040`：Agent `business_scope` 与权限（已完成）。
9. 完成真实数据回填、回归测试、灰度切换和旧接口下线。

## Verification（验收）

- 任意工作区无法读取或修改其他工作区的 B2B 数据。
- 同一商品的 B2C 与 B2B 订单可同时存在，且价格、库存和利润口径可区分。
- 100 件、500 件等阶梯价可按生效日期和版本正确匹配。
- 报价版本、订单、合同、发票和收款之间可完整追溯。
- 非法状态跳转返回业务错误，并写入审计事件。
- 旧 JSON API 不再暴露写能力。
- 前端所有业务模式入口只调用真实后端接口。
- B2C、B2B 与共享 Agent 无法越权读取不属于其业务范围的数据。

## Related Decisions（关联决策）

- `IDENTITY-001`：生产身份、零信任边界、workspace 映射与 RBAC。
- `DEC-001`：原三阶段演进决策由本 ADR 修订为 B2C + B2B 同步规划、分期开放。
