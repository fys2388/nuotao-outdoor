# ADR FULFILLMENT-001 — B2B 订单、WMS 与 TMS 履约边界

> 状态：**Accepted**（2026-09-13）  
> 决策编号：FULFILLMENT-001  
> 关联：`COMMERCE-001`、`FINANCE-001`、`docs/b2c_b2b_compatibility_audit.md`

---

## Context（背景）

B2B 订单不能只保存物流单号后就直接修改订单状态。报价、合同和应收已经形成独立
闭环，但订单出库如果没有库存预占、行级数量快照和 TMS 运单关联，会出现超卖、
重复出库、订单状态与库存不一致，以及无法回答“哪批库存服务了哪张订单”的问题。

B2C 与 B2B 共享 WMS 和 TMS 底座，但 B2B 具有批量、MOQ、分仓、账期和出库审批等
特征，因此履约必须在共享库存之上使用独立的 B2B 订单履约状态机。

## Decision（决策）

### 1. 固定履约主链路

```text
confirmed
  -> reserve inventory
  -> processing
  -> ship / create TMS shipment
  -> shipped
  -> delivered
```

未出库前允许：

```text
reserved -> released -> confirmed
```

通用订单接口只允许确认和取消订单，不得直接写入 `processing`、`shipped` 或
`delivered`。

### 2. 每张 B2B 订单只有一张履约主单

`b2b_order_fulfillments` 以 `(workspace_id, order_id)` 唯一，保存：

- 履约单号、仓库和状态。
- 预占、出库、送达和释放时间。
- 关联 TMS 运单。
- 操作者和 trace ID。

`b2b_order_fulfillment_items` 按订单行保存 `quantity`、`reserved_quantity`、
`shipped_quantity` 和 `released_quantity`，任一时刻必须满足：

```text
shipped_quantity + released_quantity <= quantity
```

### 3. 库存动作必须原子化

- 预占用行锁读取 `inventory_snapshots`，校验可用库存后再增加 `reserved`。
- 释放只允许处理未出库数量，并同步恢复 `available`。
- 出库在同一事务内扣减 `quantity` 和 `reserved`，再写入履约行数量。
- 缺少库存、并发预占冲突或状态不一致时整笔事务回滚。

### 4. 出库必须创建 TMS 运单

确认出库时创建 `shipment_records`，通过 `b2b_order_id` 关联订单，并写入
`logistics_events`。B2B 订单上的物流公司、物流单号和运单 ID 只作为履约结果同步，
不能由普通状态接口直接填写。

### 5. 主要动作必须幂等

- 重复预占返回同一履约单，不重复占用库存。
- 重复出库返回已存在履约结果，不重复扣减库存或创建运单。
- 重复送达返回已送达履约结果，不重复写物流事件。
- 已释放履约单不能直接复用，必须重新建立订单履约。

## Consequences（后果）

### 正面

- B2B 订单、库存预占、出库数量和 TMS 运单形成可追溯链路。
- 并发预占不会超卖，取消或换仓不会重复释放库存。
- 订单状态与库存、物流事实保持同一事务边界。
- B2C 与 B2B 可以共享 WMS/TMS，同时保留不同的履约状态机。

### 成本

- 订单履约需要按预占、出库、送达多个动作操作。
- 历史 `processing` 订单如果没有履约单，需要补建预占后才能继续。
- 库存快照上的汇总值是对外读取口径，最终审计仍以履约行和事件日志为准。

## Verification（验收）

- 库存不足时整个预占事务回滚，订单仍为 `confirmed`。
- 重复预占不会增加第二次 `reserved`。
- 释放只恢复未出库数量，已出库数量不可释放。
- 出库同时扣减库存和预占，并创建关联订单的 TMS 运单。
- 送达同步履约单、运单和订单状态，并写入物流事件。
- 通用状态接口无法绕过履约服务写入 `processing/shipped/delivered`。
- 跨工作区无法读取或操作履约记录。
- PostgreSQL `0038 -> 0039 -> 0038 -> 0039` 迁移往返成功。
