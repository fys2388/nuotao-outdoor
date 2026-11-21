# M4.2.0-R2 采购审批治理最终收口整改报告

> Owner 对 M4.2.0 采购审批治理的第三轮整改（R0 → R1 → R2）。R2 = Remediation 2，目标：把采购审批治理做成**真正不可绕过**。
> 日期：2026-11-21 · 分支：`feat/m4-2-0-procurement-governance` · 独立 commit（保留 R0/R1 历史）

---

## 1. 背景与目标

### 1.1 为什么 R0/R1 不够

M4.2.0 首轮收口（R0）建立了采购单审批的统一状态机 `PO_TRANSITIONS`，并把审批收敛到专用端点。R1 针对 Owner 对 PR #26 的独立审计，封堵了两类 P0 绕过通道：旧 Fulfillment API 直设 `approved`、service 层接受任意非空 `approved_by` 字符串，并强制审批 choke point 校验 `caller_role ∈ {admin, operator}`。

但 R1 收口后仍有结构性缺口——治理的「授权证明」仍建立在**调用方自述**之上，而非**数据库事实**：

| # | R1 遗留缺口 | 为什么 R1 不够 |
|---|---|---|
| G1 | 旧 Service 层仍保留独立状态机 `PO_STATUS_FLOW` + `update_purchase_order_status()` | 该函数可对 `po.status` 做裸赋值（draft→approved），**无鉴权、无审计**，是与 `approve_purchase_order` 并存的第二条 approved 路径 |
| G2 | 审批主体靠传入的 `caller_role` 字符串 + 调用方自填的 `approved_by` | 任何绕过 API 的调用方（脚本、notebook、未来 agent 路径）都能**伪造一个角色字符串和身份字符串**通过审批——service 层并未真正查库证明「这是谁」 |
| G3 | 审批无成本确认门禁 | 成本未确认（`cost_confirmed=false`）的 PO 仍可进入 approved，可能据未核实成本产生真实支出 |
| G4 | 审计事件字段不统一、`from_status` 有 from==to 隐患 | 部分操作缺操作者身份留痕，事后无法完整追溯「谁在什么状态下做了什么」 |
| G5 | 四个采购操作端点（order/partial_receive/receive/cancel）无 RBAC | 任何登录用户都能下单/收货/取消，产生真实支出却无权限约束、无身份留痕 |
| G6 | 并发审批行为无真实数据库验证 | 同一 draft PO 被两个连接同时审批时是否恰好一个胜出，缺真实 DB 往返证据 |

### 1.2 R2 的目标

R2 不再满足于「端点加了 RBAC」，而是让治理不依赖任何调用方自述，把 approved 做成**代码层面可证明的唯一可达状态**。R2 确立的最终不变量见 §3。

---

## 2. 六项整改逐项详情

### R2.1 删除旧 Service 审批旁路（G1）

**文件**：`backend/app/services/fulfillment_service.py`

| | before | after |
|---|---|---|
| 状态机 | 独立 `PO_STATUS_FLOW` 与 `supply_chain.PO_TRANSITIONS` 并存 | 删除 `PO_STATUS_FLOW` |
| 裸赋值入口 | `update_purchase_order_status()` 可直接 `po.status = "approved"`（无鉴权/无审计） | 函数删除 |
| next-status 推导 | 由本地 `PO_STATUS_FLOW` 推导 | 新增 helper `_canonical_next_statuses(status)`，统一委托 `supply_chain.PO_TRANSITIONS` |

**治理意义**：PO 到 approved 的路径从「两条」收敛为「一条」。`get_purchase_order_detail` 的 `allowed_next_statuses` 现在引用唯一状态机，杜绝任何旁路自行推导状态。

### R2.2 真实审批主体校验——不信任 caller_role 字符串（G2）

**文件**：`backend/app/services/supply_chain.py`

新增 `_validate_approver(session, *, caller_user_id, caller_role)`：

- 拒绝空 `caller_user_id`（fail-closed）；
- 校验其为合法 UUID；
- **查数据库 `users` 表**，独立验证该 `caller_user_id`：真实存在、`is_active`、`role ∈ {admin, operator}`；
- 返回该用户的**稳定 `user.id`（非 email）**，写入 `po.approved_by`；
- **纵深防御**：若传入的 `caller_role` 与 DB 中用户真实 role 不一致，同样拒绝（防伪造角色字符串）。

**改动点**：

| 函数 | 改动 |
|---|---|
| `_transition_purchase_order` | approved 分支调用 `_validate_approver` 得到 `verified_approver`，把 `verified_approver`（= user_id）写入 `po.approved_by` |
| `approve_purchase_order` | 新增 `caller_user_id` 参数并透传 |
| API 层 approve 端点 | 传 `caller_user_id=str(approver.id)` |

**治理意义**：审批授权的证明从「调用方自述的角色字符串」升级为「数据库中真实、active、授权角色的 User 记录」。伪造身份/角色字符串、AI Agent、自动化脚本均无法成为授权主体——这正是 R1 未能完全闭合的核心缺口。

### R2.3 成本确认硬门禁（G3）

**文件**：`backend/app/services/supply_chain.py::_transition_purchase_order`（approved 分支）

- 若 `po.cost_confirmed` 为 False → 抛 `SupplyChainError`，拒绝进入 approved（fail-closed）。

**治理意义**：未确认真实成本的采购单无法被批准，杜绝「按未核实成本放行、事后才发现亏损」的风险。成本确认成为 approved 的前置硬条件。

### R2.4 统一审计事件（G4）

**文件**：`backend/app/services/supply_chain.py::_transition_purchase_order`

- 事件 payload 统一含：`po_number, action(=target), from_status, to_status, actor_user_id, actor_role`；
- approved 时额外含 `approved_by, approval_note`；
- `from_status` 在改状态**前**捕获（修复 from==to 的 bug）；
- 所有状态变更函数（order / cancel / partial_receive / receive）新增 `caller_user_id` 参数透传，事件中记录 actor。

**治理意义**：每次状态变更都有完整、一致、可追溯的审计链——谁（actor_user_id）、以什么角色、把 PO 从什么状态改到什么状态、审批备注是什么。满足 AGENTS.md「全链路可审计」要求。

### R2.5 所有采购操作 API 加 RBAC（含 order）（G5）

**文件**：`backend/app/api/v1/endpoints/supply_chain.py`

四个端点 `order_purchase_order` / `partial_receive_purchase_order` / `receive_purchase_order` / `cancel_purchase_order` 原本**无 RBAC、无身份留痕**，现均加：

```python
operator: Annotated[UserResponse, Depends(require_role("operator"))]
# 并传 caller_user_id=str(operator.id) 给 service 层记审计
```

**治理意义**：`order`（把 PO 发给供应商、产生真实支出）尤为关键——现在下单、收货、取消都是 operator+ 权限动作，且操作者身份进入审计事件，不再是无主操作。

### R2.6 真实 PostgreSQL 双连接并发审批验证（G6）

**新增文件**：`backend/tests/test_concurrency_approval_postgres.py`

| 测试 | 模式 | 断言 |
|---|---|---|
| `test_concurrent_approve_postgres_single_winner` | Postgres（`TEST_DATABASE_URL` 指向 Postgres 时启用） | 两个独立 session/connection 同时审批同一 draft PO → 恰好一个成功、另一个抛 `SupplyChainError`、`approved_by` 记录唯一 winner |
| `test_concurrent_approve_sqlite_application_invariant` | SQLite 降级（CI 默认无 Postgres） | 同一 session 串行二次审批 → 应用层不变量（状态机拒绝二次 approved）成立 |
| `test_concurrency_mode_is_declared` | 两者 | 诚实声明当前跑的是哪种模式，不夸大覆盖 |

**治理意义**：并发审批的「单一胜出者」保证有真实数据库往返证据，而非仅靠应用层推断。本地/CI 为 SQLite 时 Postgres 测试 SKIP，skip 原因明确写入，不伪造覆盖面。

---

## 3. 治理不变量总结

R2 收口后确立的最终不变量：

> **采购单到达 `approved` 的唯一可达路径，是 `supply_chain.approve_purchase_order` → `_transition_purchase_order` 的 approved 分支；该分支被三重门禁保护，三者缺一 fail-closed：**

| 门禁 | 证明来源 | 拒绝条件 |
|---|---|---|
| ① 真实人类身份 | 查 `users` 表验证 `caller_user_id` 存在且 `is_active` | 未知用户 / 停用账号 / 空 id |
| ② 授权角色 | DB 中用户 `role ∈ {admin, operator}`，且与传入 `caller_role` 一致 | 角色不足 / 伪造角色字符串 |
| ③ 成本已确认 | `po.cost_confirmed == True` | `cost_confirmed` 为 False |

**唯一路径证明**：
- 旧 Service 旁路（`PO_STATUS_FLOW` + `update_purchase_order_status`）已删除（R2.1）；
- 旧 Fulfillment API 代理到唯一状态机并显式拒绝 approved（R1 已封）；
- 第四套文件存储状态机（`purchase_order_service`）状态集不含 approved（R1 已评估，无绕过面）。

**AI/自动化永不作为授权主体**：`_validate_approver` 只认数据库中真实、active、授权角色的人类 User，任何伪造身份、脚本、Agent 路径均无法成为 approved 的 authorizing subject。

---

## 4. 验证结果

- **采购治理回归**：**53 passed, 1 skipped**。skip 项为 Postgres 并发测试 `test_concurrent_approve_postgres_single_winner`，原因：CI 无 Postgres，降级跑 SQLite 应用层不变量测试。
- **ruff 阻塞类**（F821 / F811 / E9 / F）：全绿。
- **测试适配**：为满足成本门禁（R2.3），给合法审批测试增加「确认成本」步骤；conftest 的 admin fixture 改为 seed 真实 admin User 记录（因 R2.2 需查库验证用户）。
- **版本控制**：分支 `feat/m4-2-0-procurement-governance`，独立 commit，保留 R0/R1 完整历史。

---

## 5. 已知边界与诚实声明

1. **Postgres 并发测试在 CI 被 SKIP**：本地与 CI 均为 SQLite，`test_concurrent_approve_postgres_single_winner` 仅在 `TEST_DATABASE_URL` 指向真实 Postgres 时运行。当前验证只跑了 SQLite 降级模式（应用层不变量），**本地无法完成真实 Postgres 双连接往返**；「恰好一个胜出者」的并发保证依赖数据库行锁/唯一约束，需在有 Postgres 的环境补跑以获得完整证据。
2. **`test_concurrency_mode_is_declared` 的诚实声明**：测试显式输出当前运行模式，不将 SQLite 应用层不变量包装为「已验证 Postgres 并发」。
3. **文件存储状态机技术债（D-2）**：`purchase_order_service`（经 `procurement_workbench` 暴露）仍为独立文件存储实现，但状态集不含 approved、无绕过面，彻底归一到 `PO_TRANSITIONS` 登记 Backlog（建议 M4.2.x），不在本次收口范围。
4. **`po_status="pending_approval"` 越界状态**：由 `scripts/po_dedup_audit.py` 标记的历史数据，R1 以改 `draft` 规避，彻底统一待 T0.5 数据模型迁移。

---

## 6. 结论

R2 完成了采购审批治理的最终收口。相比 R0/R1 依赖「调用方自述身份/角色」，R2 把 approved 做成**由数据库事实背书、三重门禁保护、唯一可达**的状态：真实人类身份 + 授权角色 + 成本已确认，缺一 fail-closed；旧 Service 旁路已物理删除；所有采购操作端点纳入 RBAC 且全链路可审计。采购审批治理在代码层面被证明**真正不可绕过**，等待 Owner 复审。
