# M4.2.0-R3 采购成本真实性闭环整改报告

> 采购审批治理 R0 → R1 → R2 → R3 的 R3 轮。R3 = Cost-Truth Closure（成本真实性闭环）。
> 目标：让 `cost_confirmed=true` 从「一个布尔标记」变成「一个可被审计证明的事实」——**逐 SKU 真实 ProductCost、金额经过重算、全程留痕**。
> 日期：2026-11-21 · 分支：`feat/m4-2-0-procurement-governance`
>
> 命名澄清：仓库中已有一份 `M420_R3_POSTGRES_CI_EVIDENCE.md`，它记录的是并发验证 **CI 基础设施**（属于并发治理线的延续）。本报告聚焦另一条独立的 R3 工作线——**成本确认的真实性收口**（R3.1 / R3.2）。两者同名不同域，互不替代。

---

## 1. 背景与目标

### 1.1 为什么 `cost_confirmed=true` 在 R2 之后仍不够可信

R2 把「审批」做成了代码层面可证明的唯一可达状态（真实审批主体 + 成本确认门禁 + 事件留痕）。但 R2 的成本确认门禁依赖的 `cost_confirmed` 标记本身，是由 `confirm_purchase_order_cost` 写入的——而这个函数在 R2 时**并不保证「确认的成本是真实的」**：

| # | R2 遗留缺口 | 为什么 `cost_confirmed=true` 因此不可信 |
|---|---|---|
| C1 | 确认时不校验每个 SKU 是否有真实 ProductCost | PO 行项可能在创建时填了 fallback 比例估算（`unit_price * procurement_fallback_cost_ratio`）作为 `unit_cost` 残留。确认成本时若不逐行解析真实成本，这些 fallback 残留会**原地保留**，PO 却被标成 `cost_confirmed=true`——「已确认成本」实际是估算值 |
| C2 | 确认时不回写 unit_cost、不重算金额 | 即便行项带了真实成本，`line_total / subtotal / total` 也可能仍是创建时的旧值或估算值。`cost_confirmed=true` 的金额未经重算，与真实成本脱节 |
| C3 | 确认时直接 `po.status = "draft"`（裸赋值） | 状态变更绕过 `PO_TRANSITIONS` 状态机，无转换合法性校验、无 from→to 留痕，理论上可被改成任意状态 |
| C4 | 确认无主体鉴权 | 旧签名无 `confirmer_user_id`，任何能调到 service 的调用方（脚本 / notebook / 未来 agent 路径）都能确认成本，`cost_confirmed_by` 只是自述字符串 |
| C5 | 确认事件不携带成本构成 | 即便发了事件，也不含「确认时刻每个 SKU 的 quantity/unit_cost」快照，事后无法追溯「当时据以确认的成本数字从何而来」 |

核心矛盾：**治理链条的末端（成本确认）建立在一个不被验证的布尔上**。审批门禁问「cost_confirmed 是不是 true」，却没人保证这个 true 意味着「成本是真的」。

### 1.2 R3 的目标

R3 不再满足于「有个成本确认动作」，而是让 `cost_confirmed=true` 成为**一个可被审计证明的复合事实**：确认那一刻，PO 每一行的 `unit_cost` 都来自权威 `product_cost` 表、金额经重算、由真实授权人确认、并留下成本快照。确立的不变量见 §4。

---

## 2. R3.1 成本确认原子化（核心改动）

**文件**：`backend/app/services/supply_chain.py`（新增核心实现）、`backend/app/services/fulfillment_service.py`（改为薄委托，保留 API 兼容）

核心实现收敛到 `supply_chain.confirm_purchase_order_cost`；`fulfillment_service.confirm_purchase_order_cost` 现在是一层薄委托（解析默认 workspace 后转调），对外签名兼容，治理逻辑唯一来源仍是 `supply_chain`。

### R3.1.1 逐 SKU 校验真实 ProductCost

新增 helper `_resolve_real_item_cost(session, *, workspace_id, item)`：

| | 说明 |
|---|---|
| 解析顺序 | 先按 `item.product_id` 查 `product_cost` 表；查不到再按 `item.sku → Product → 其 cost` 兜底 |
| 真实性门槛 | 要求 `purchase_cost > 0`；成本行不存在、或 `purchase_cost <= 0`，一律返回 `None` |
| 返回语义 | 返回 `Decimal \| None`——`None` 明确表示「这个 SKU 没有可用真实成本」 |

**治理意义**：把「有没有真实成本」的判定从「调用方自觉」下沉为「逐 SKU 强制解析」，且只认 `product_cost` 权威行，绝不接受 fallback 比例推算的数字。

### R3.1.2 任一 SKU 缺真实成本 → 整体回滚（fail-closed）

`confirm_purchase_order_cost` 先**解析全部 item**，收集 `missing`；只要有**任何一个** SKU 解析不到真实成本，立即抛 `SupplyChainError("still missing real ProductCost for items: ...")`，整个确认回滚。

| | before（R2 及以前） | after（R3.1） |
|---|---|---|
| 确认语义 | 不逐行校验，缺成本的行项 fallback 残留原地保留 | 先全量解析，缺一即整体失败 |
| fallback 去向 | 可能随 `cost_confirmed=true` 进入执行态 | **永远进不了** `cost_confirmed=true` 的 PO |
| 失败后状态 | — | PO 保持 `pending_cost_confirmation`、`cost_confirmed=false`（见 test_cost_blocker.py Test 6） |

**治理意义**：PO 绝不会在任一行还带 fallback/估算残留时被标 `cost_confirmed=true`。这是 fail-closed——不确定就拒绝，绝不「部分确认」。

### R3.1.3 回写 unit_cost + 重算金额

解析全部成功后：

- 把真实成本写回每个 `PurchaseOrderItem.unit_cost`；
- 重算 `line_total = unit_cost * quantity`；
- 重算 PO 级 `subtotal = Σ line_total`、`total = subtotal + shipping_cost`。

**治理意义**：`cost_confirmed=true` 的 PO，其每一行成本与各级金额都由权威成本**当场重算得出**，金额不再与真实成本脱节（解决 C2）。

### R3.1.4 成本快照（cost_snapshot）

确认时构建 `cost_snapshot`（每个 SKU 的 `quantity` / `unit_cost`），落入 `supply.purchase_order_cost_confirmed` 审计事件 payload。

**治理意义**：可追溯「确认那一刻的成本构成」——事后审计能精确还原当时据以确认的每行成本数字，而非只有一个总额（解决 C5）。

### R3.1.5 禁止 fallback 残留

因为只有真实 ProductCost（`purchase_cost > 0`）才被接受，fallback 比例推算值在结构上**永远无法**进入 `cost_confirmed=true` 的 PO。确认成功后同时置 `cost_source = "product_cost"`、`cost_confidence = 0.95`、清空 `cost_block_reason`。

---

## 3. R3.2 成本确认权限与状态机

**文件**：`backend/app/services/supply_chain.py`

### R3.2.1 状态机化——`_apply_status_transition`

提取共享 helper `_apply_status_transition(purchase_order, *, target)`：

| | before | after |
|---|---|---|
| 状态变更 | `po.status = "draft"` 裸赋值 | 经 helper 校验 `target ∈ PO_TRANSITIONS[from_status]` 后才改，并返回 `from_status` |
| 转换合法性 | 无校验 | 不合法即抛 `SupplyChainError` |
| 审计 from→to | 隐患 | helper 在变更前捕获 `from_status`，事件记录正确的 from→to |
| 复用 | — | 通用转换路径与成本确认路径共用同一状态机（single source of truth） |

confirm 走它做 `pending_cost_confirmation → draft`，**绝不**一跳到 approved/ordered——审批仍只走专用 `approve_purchase_order` 端点。`PO_TRANSITIONS` 中 `pending_cost_confirmation` 仅可达 `{draft, cancelled}`，结构性杜绝成本确认直接授权执行。

**治理意义**：成本确认的状态变更从「裸赋值」纳入唯一状态机，可校验、可留痕、不可越级（解决 C3）。

### R3.2.2 确认人须 operator/admin

confirm 入口调 `_validate_approver(session, caller_user_id=confirmer_user_id, caller_role=None)`，查 DB 验证确认人是**真实、active、role ∈ {admin, operator}** 的用户，返回稳定 `user.id`。新增 `confirmer_user_id` 参数（`confirmed_by` 仍是记录在 PO 上的展示标签，`confirmer_user_id` 才是用于鉴权的真实主体，二者分离）。

**治理意义**：AI Agent / automation 没有用户记录，**结构性被拒**——成本确认这一高权限动作必须是可归因的人类操作者（解决 C4）。复用 R2 已验证的 `_validate_approver`，不另造鉴权逻辑。

### R3.2.3 event_log 审计

确认时发**单一** `supply.purchase_order_cost_confirmed` 事件，payload 含：

`po_number` / `action` / `from_status` / `to_status` / `actor_user_id` / `confirmed_by` / `cost_source` / `cost_snapshot` / `subtotal` / `total`。

**治理意义**：一个事件讲完整「成本确认」故事——谁确认的（身份）、在什么状态下（from→to）、依据什么成本（cost_source + cost_snapshot）、重算出多少钱（subtotal/total）。状态变更与成本快照合并为单一事件，避免多事件口径不一致。

### R3.2.4 trace_id

事件携带 `trace_id`，可跨链路关联。

### R3.2.5 幂等确认不产生重复事件

若 PO 已 `cost_confirmed` 且 `status == "draft"`，直接返回、不重复发事件。重复确认返回同一 PO（test_cost_blocker.py Test 5 验证不产生重复 PO）。

**治理意义**：重试 / 重复调用不会污染审计流、不会产生重复单据。

### 测试适配

`backend/tests/test_cost_blocker.py` 四个用例适配新 `confirmer_user_id` 参数：seed 一个 admin 用户并传 `str(admin.id)`；负向测试（Test 6）期望改为捕获 `SupplyChainError`（`still missing real ProductCost`）。

---

## 4. 治理不变量总结

R3 之后，`cost_confirmed=true` 的**可信含义**是一个四要素复合事实：

| 不变量 | 保障机制 |
|---|---|
| **真实成本** | 每行 `unit_cost` 均由 `_resolve_real_item_cost` 从权威 `product_cost` 表解析，要求 `purchase_cost > 0`；fallback 比例结构性进不来 |
| **重算金额** | `line_total / subtotal / total` 在确认时由真实成本当场重算，与成本一致 |
| **授权确认人** | `_validate_approver` 查库验证真实、active、admin/operator 人类用户；AI Agent / automation 结构性被拒 |
| **全程留痕** | 单一 `cost_confirmed` 事件携带 from→to、身份、cost_source、cost_snapshot、重算金额、trace_id；幂等不重复 |

一句话：**`cost_confirmed=true` 不再只是一个布尔，而是「真实成本 + 重算金额 + 授权确认人 + 全程留痕」四项同时成立的可审计证明。** 审批门禁据以放行的成本标记，由此获得可信基础。

---

## 5. 验证结果

| 项 | 结果 |
|---|---|
| 采购治理回归 | **57 passed, 1 skipped**（skip 的是 Postgres 物理竞态用例——CI 的 `backend` job 无 Postgres 环境，该竞态由独立的 `postgres-concurrency` job 真跑，见 `M420_R3_POSTGRES_CI_EVIDENCE.md`） |
| ruff 阻塞类 | **F821 / F811 / E9 / F 全绿** |
| 关键行为用例 | `test_cost_blocker.py`：确认→draft、确认后可审批、幂等不重复、缺真实成本 fail-closed 四类均通过 |

---

## 6. 诚实边界

1. **「真实」的边界是 `product_cost` 表**：R3.1 保证的是「成本来自权威 `product_cost` 行且 > 0」，而非「该成本数字本身经人工逐单核对无误」。若上游录入的 `product_cost` 有误，确认环节无法识别——成本数据的准确性仍依赖上游维护流程。
2. **fallback 计算逻辑仍在（用于未确认阶段）**：`fulfillment_service` 创建 PO 时仍用 `procurement_fallback_cost_ratio` 推算估算成本，用于把缺成本的订单推进 `pending_cost_confirmation`。R3 保证的是 fallback **进不了** `cost_confirmed=true`，而非删除 fallback——它是「阻塞前」的临时标记，不是「执行」依据。
3. **`cost_confidence = 0.95` 是约定常量**：确认成功后写入的置信度是代码约定的固定值，非统计推导。
4. **SQLite 上无物理行锁竞态**：confirm 使用 `for_update=True`，在 Postgres 上是 `SELECT..FOR UPDATE`，在 SQLite 上是 no-op。并发安全由 Postgres 行锁保证，其证据依赖 `postgres-concurrency` CI job 实跑。
5. **本报告未覆盖并发 CI 基础设施**：Postgres 并发 job 的设计属于另一份 `M420_R3_POSTGRES_CI_EVIDENCE.md`，本报告不重复。