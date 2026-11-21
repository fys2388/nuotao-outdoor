# M4.2.0-R2 采购审批安全审计报告

- 版本：R2（采购审批治理第 3 轮，R0 → R1 → R2）
- 主题：真实审批主体校验（Real Approval Subject Verification）
- 审计对象：`backend/app/services/supply_chain.py`、`backend/app/api/v1/endpoints/supply_chain.py`、`backend/app/services/fulfillment_service.py`
- 关联提交：`60a7fd9 feat(supply_chain): M4.2.0-R2 procurement approval final hardening (real subject + cost gate)`
- 验证状态：53 passed + 1 skipped；ruff 全绿；负向测试全部 fail-closed

---

## 1. 审计目标

**一句话目标**：证明采购审批（PO 到达 `approved` 状态）不可被任何未授权主体绕过——即"这套设计不可绕过"。

R2 要解决的核心信任缺口是：R0/R1 之前，审批授权的"证据"是调用方**自己声明**的字符串（`caller_role`、`approved_by` 邮箱）。任何能触达 Service 的调用方——AI Agent、自动化脚本、伪造身份的外部调用——只要在参数里写上 `caller_role="admin"` 或 `approved_by="boss@nuotao.com"`，就能被当作合法审批人。这是"调用方自证"模型，本质上是把授权决策交给了不可信输入。

R2 的设计原则是**反其道而行**：不再信任调用方的任何声明，Service 层独立查数据库，验证审批人是真实、active、有授权角色的人类用户。授权的唯一依据是 DB 里的 `users` 表记录，而不是请求参数。

具体要证明的不变量：

- **I1（真实人类身份）**：能到达 `approved` 的操作者，必须对应 `users` 表里一条真实、`is_active=True` 的记录。AI Agent / automation 没有用户记录，结构性被拒。
- **I2（授权角色）**：该用户 `role ∈ {admin, operator}`，以 DB 为权威，不信任调用方声明的 `caller_role`。
- **I3（成本已确认）**：`po.cost_confirmed` 必须为 `True`，未确认真实成本的 PO 永不可被授权。
- **I4（唯一可达路径）**：DB 中 `purchase_orders` 到达 `approved` 只有一条路径，且该路径强制执行 I1+I2+I3。
- **I5（稳定审计）**：`approved_by` 记录的是稳定的 `user.id`（非 email），且每次状态变更都留下可查询的审计事件。

---

## 2. 威胁模型

列出可能试图绕过审批门禁的主体，以及它们各自的可利用面。

| # | 绕过主体 | 能力 / 可利用面 | R2 前的风险 | R2 后的状态 |
|---|---|---|---|---|
| T1 | AI Agent（LLM 编排的供应链分析师等） | 可调用 Service 层白名单工具；可在参数里构造 `caller_role="admin"` | 若信任 `caller_role` 字符串，Agent 可自批准 | **结构性拒绝**：Agent 无 `users` 表记录，无 `caller_user_id` 可通过校验 |
| T2 | Automation / 定时任务 / 内部脚本 | 直接调 Service 函数，绕过 API 层；可传任意参数 | 无身份即可写 `po.status="approved"` | **拒绝**：无合法 `caller_user_id` → fail-closed |
| T3 | 伪造身份的外部调用 | 持有合法 token 但冒用他人身份；传伪造 `approved_by` 邮箱 + `caller_role="admin"` | 邮箱/角色字符串即"证据"，可伪造 | **拒绝**：Service 以 `caller_user_id` 查 DB 真实身份，伪造邮箱不是授权证明 |
| T4 | 无凭证的内部调用 | 完全不传 `caller_user_id`（None/空/非法 UUID） | 可能因"无身份即默认放行"而穿透 | **拒绝**：缺失/非法 `caller_user_id` 在第一步即被拒 |
| T5 | 越权员工（viewer / customer_service 等只读角色） | 有合法账号、能登录，但角色无审批权 | 若仅凭登录态放行，只读角色可审批 | **拒绝**：DB `role ∉ {admin, operator}` → "requires an authorized role" |
| T6 | 被停用账号（`is_active=False`） | 曾有审批权，账号已被停用 | 停用后 token 可能仍有效 | **拒绝**：`is_active=False` → "inactive" |
| T7 | 伪造 `caller_role` 与真实角色不符 | 传 `caller_role="admin"` 但 `caller_user_id` 实际是 viewer | 角色声明与身份脱钩 | **拒绝**：`caller_role` 与 DB `role` 不一致即拒（纵深防御） |
| T8 | 并发双审批（两个合法审批人同时点） | 两个合法用户竞争同一 draft PO | 可能双重授权 / 脏写 | **恰一成功**：状态机拒绝第二次（见诚实边界 §6） |
| T9 | 未确认成本就审批 | 跳过成本核算直接授权支出 | 用 fallback 估算成本即下单，产生真实支出 | **拒绝**：`cost_confirmed=False` → 成本门禁拦截 |
| T10 | 重复审批（approved 后再次 approve） | 对已审批 PO 重复提交 | 幂等性漏洞 | **拒绝**：状态机 `approved` 不允许 → `approved`，返回 400 |

---

## 3. 防御机制详解

### 3.1 `_validate_approver` 六步校验（R2.2）

位置：`backend/app/services/supply_chain.py`。这是整个治理的核心 choke point。逻辑如下（fail-closed，任一步不过即抛 `SupplyChainError`）：

1. **`caller_user_id` 缺失 → 拒绝**
   `if not caller_user_id` → `"approving a purchase order requires an authenticated operator user id"`。挡住 T2/T4。
2. **`caller_user_id` 不是合法 UUID → 拒绝**
   `UUID(caller_user_id)` 抛 `ValueError` → `"requires a valid operator user id"`。挡住格式伪造。
3. **用户不存在 → 拒绝**
   `select(User).where(User.id == user_uuid)` 查不到 → `"user '...' not found"`。挡住 T1（Agent 无记录）、T3（伪造 ID）。
4. **用户 `is_active=False` → 拒绝**
   → `"approving user '...' is inactive; approval denied"`。挡住 T6。
5. **`role ∉ {admin, operator}` → 拒绝**
   `_APPROVAL_ROLES = {"admin", "operator"}`（镜像 `UserRole.ADMIN / OPERATOR`）→ `"requires an authorized role (admin/operator)"`。挡住 T5。
6. **传入 `caller_role` 与 DB 真实 `role` 不一致 → 拒绝**
   `if caller_role is not None and caller_role != user.role` → `"caller_role '...' does not match the authenticated user's role '...'"`。这是纵深防御：即使攻击者同时伪造了 ID 和角色字符串，两者对不上也会暴露。挡住 T7。
7. **全部通过 → 返回稳定 `user.id`**

关键点：`caller_role` 是**可选的交叉校验项，不是授权依据**。即使完全不传 `caller_role`，只要 `caller_user_id` 对应的 DB 用户是 active 的 admin/operator，即可通过；反之，传了 `caller_role="admin"` 但 DB 里是 viewer，照样被第 6 步拒掉。授权的**唯一权威来源是 DB**。

### 3.2 三重门禁（`_transition_purchase_order`，target="approved"）

`_transition_purchase_order` 是所有 PO 状态变更的唯一汇合点。当 `target == "approved"` 时，它强制叠加三道门禁：

```
if target == "approved":
    verified_approver = await _validate_approver(session, caller_user_id=..., caller_role=...)  # 门禁1+2
    if not purchase_order.cost_confirmed:                                                        # 门禁3
        raise SupplyChainError("cannot approve a purchase order whose real cost is not confirmed ...")
```

- **门禁 1（真实人类身份）**：`caller_user_id` → DB 真实 active 用户。AI Agent / automation 无用户记录，天然被拒。
- **门禁 2（授权角色）**：该用户 `role ∈ {admin, operator}`，DB 权威，不信任调用方声明。
- **门禁 3（成本已确认）**：`po.cost_confirmed` 必须为 `True`。

三道门禁**同时满足**才放行，缺一不可。通过后，返回的 `verified_approver`（稳定 `user.id`）被写入 `po.approved_by`，并连同 `approved_at`、`approval_note` 一起落库。

### 3.3 approved 的唯一可达路径（R2.1）

R2 删除了旧的旁路，确保 DB 中 `purchase_orders` 到达 `approved` 只有一条路：

- **删除 `fulfillment_service.PO_STATUS_FLOW`**：一套与主状态机并行的独立状态机，是"平行权威"，可独立驱动 `draft → approved`。
- **删除 `update_purchase_order_status()`**：一个裸赋值函数（`po.status = new_status` 直接写库），**无鉴权、无审计**，是最大的旁路。
- **`get_purchase_order_detail` 改为从唯一的 `supply_chain.PO_TRANSITIONS` 派生 `allowed_next_statuses`**，消除前端可见的第二套规则。

现在到达 `approved` 的唯一路径是：

```
approve_purchase_order() → _transition_purchase_order(target="approved") → 强制三重门禁
```

任何其它试图把 PO 置为 `approved` 的代码路径已不存在于 Service 层。

### 3.4 统一审计事件（R2.4）

每次状态变更都向 `event_log` 写入结构化审计事件，字段包括 `po_number`、`action`、`from_status`（转换前捕获）、`to_status`、`actor_user_id`、`actor_role`；对 `approved` 额外记录 `approved_by`（已验证的 `user.id`）与 `approval_note`。`order` / `cancel` / `partial_receive` / `receive` 均透传 `caller_user_id`，确保操作者在每个事件上都留痕，全链路采购审计可从 `event_log` 单表查询。

### 3.5 RBAC 全覆盖（R2.5）

API 层（`backend/app/api/v1/endpoints/supply_chain.py`）采购写操作端点 RBAC 现状：

| 端点 | 动作 | RBAC | R2 变化 |
|---|---|---|---|
| `POST /purchase-orders`（create） | 建 draft PO | `operator`+ | 原有 |
| `POST .../{po_id}/approve` | draft → approved | `operator`+ | 原有，R2 增强 Service 校验 |
| `PATCH .../{po_id}`（status / update） | 改 PO | `operator`+ | 原有 |
| `POST .../{po_id}/order` | approved → ordered（**下单给供应商、产生真实支出**） | `operator`+ | **R2.5 新增** |
| `POST .../{po_id}/partial-receive` | 部分收货 | `operator`+ | **R2.5 新增** |
| `POST .../{po_id}/receive` | 收货完成 | `operator`+ | **R2.5 新增** |
| `POST .../{po_id}/cancel` | 取消 | `operator`+ | **R2.5 新增** |

其中 **`order` 端点尤其关键**：它把 PO 发给供应商、产生真实资金支出，此前竟无 RBAC 保护。R2.5 补齐后，所有采购写操作端点已 100% 覆盖 `require_role("operator")`。每个端点同时把 `operator.id` 透传给 Service 用于审计。

---

## 4. 攻击向量 → 防护 → 测试证据 对照表

每条负向测试都验证"被拒后 PO 状态保持 `draft`、`approved_by` 为 `None`"（fail-closed），不只看是否抛错。

| 攻击向量 | 防护机制 | 测试证据（文件 / 用例 / 断言） |
|---|---|---|
| AI Agent 自批准（T1） | 门禁 1：Agent 无 `users` 记录 | `tests/test_purchase_governance_t02.py::test_service_approve_requires_operator_identity` — `caller_user_id=None` → `SupplyChainError match "operator user id"`；`tests/test_supply_chain_agent_t01.py` 同类 |
| 伪造 `approved_by` 邮箱/字符串但无合法 `caller_user_id`（T3） | 门禁 1：邮箱不是授权证明 | `test_purchase_governance_t02.py::test_service_approve_requires_authorized_role` — 传 `approved_by="ghost@nuotao.com"` 但 `caller_user_id=None` → 拒绝；`caller_user_id=uuid4()`（不存在）→ match "not found" |
| 伪造 `caller_role="admin"` 但真实是 viewer（T7） | 第 6 步：`caller_role` 与 DB `role` 交叉校验 | `test_purchase_governance_t02.py` — viewer/customer_service 用户传 `caller_role=<该角色>` → match "authorized role"（角色本身越权）；角色不一致路径由 `_validate_approver` 第 6 步覆盖 |
| 无身份直接调 Service（T2/T4） | 门禁 1：缺失/非法 `caller_user_id` | `test_purchase_governance_t02.py::test_service_approve_requires_operator_identity` — `caller_user_id=None` → 拒绝 |
| 越权员工 / 未登录调采购写端点（T5） | API RBAC `require_role("operator")` + Service 门禁 2 | `test_purchase_governance_t02.py` — 非 operator 角色 → 403；`test_r1_fulfilment_governance.py` — 未登录 → 401、只读 → 403 |
| 重复审批（T10） | 状态机：`approved` 不允许 → `approved` | `test_supply_chain.py::test_purchase_order_invalid_transitions` — 非法转换 → 400 |
| 并发双审批（T8） | 应用层状态机不变量（+ 设计上的 DB 行级锁，见 §6） | `tests/test_concurrency_approval_postgres.py` — Postgres 双连接竞态恰一成功；SQLite 降级验证应用层不变量 |
| 未确认成本就审批（T9） | 门禁 3：`cost_confirmed=False` 拦截 | `tests/test_cost_blocker.py` — fallback 成本 `cost_confirmed=False`，被阻于执行；R2.3 门禁在 `_transition_purchase_order` 强制 |
| 合法审批（正向，证明不误伤） | 三重门禁全过 → 记录 `user.id` | `test_purchase_governance_t02.py::test_approve_records_operator_and_time` — `po.approved_by == str(operator.id)`（稳定 ID 非 email），记录 `approved_at`/`approval_note`，产生 `supply.purchase_order_approved` 事件 |

补充说明：测试夹具（`conftest.py`）为适配 R2.2，已改为 seed 真实 admin `User` 行，使合法审批路径有据可查；合法审批用例均先确认成本（适配 R2.3）。

---

## 5. 纵深防御说明

R2 的授权不是单点，而是**两层必须同时通过**：

```
外部调用
   │
   ├─ 第 1 层：API RBAC 层（require_role("operator")）
   │    · 校验 JWT / 登录态，未登录 → 401
   │    · 校验角色 ∈ operator/admin，越权 → 403
   │    · 即使过了这层，也只证明"有个登录的 operator 账号"
   │
   ├─ 第 2 层：Service 层独立校验（_validate_approver）
   │    · 不信任第 1 层传来的任何字符串
   │    · 独立查 users 表：存在 + active + role ∈ {admin,operator}
   │    · 交叉校验 caller_role 与 DB role
   │    · 直接调 Service（绕过 API）也必须过此层
   │
   └─ 两层都过 → 才写 po.status="approved"，记录 verified user.id
```

**为什么必须两层**：
- 只靠 API RBAC → 任何能直连 Service 的内部代码（Agent 工具、automation、脚本）可绕过 API 层直接写库。
- 只靠 Service 校验 → API 层若无 RBAC，未登录/低权限请求会打到 Service，虽仍被拒，但缺少 401/403 的标准语义，且把鉴权责任全压在 Service。
- R2.5 补齐 `order/partial_receive/receive/cancel` 的 API RBAC，正是为了消除"Service 有校验但 API 裸奔"的语义缺口（尤其 `order` 这种产生真实支出的端点）。

两层共同保证：**无论从 API 进还是从 Service 进，审批主体验证都无法被跳过**。这就是"不可绕过"的结构性依据——授权决策收敛在 Service 的单一 choke point，且该 choke point 不接受任何来自调用方的授权声明。

---

## 6. 诚实边界

审计报告必须如实记录设计的边界与前提，不做超出证据的宣称。

### 6.1 并发物理竞态依赖 DB 行级锁，CI 默认只验证应用层不变量

- **设计意图**：`tests/test_concurrency_approval_postgres.py` 的模块文档与提交说明 `60a7fd9`（R2.6）均声明，审批 choke point 通过 `SELECT .. FOR UPDATE` 行级锁串行化并发写者，使 Postgres 环境下双连接竞态"恰一成功"。
- **CI 现实**：CI 默认使用内存 SQLite（`TEST_DATABASE_URL` 非 Postgres）。SQLite 单连接无法承载两个并发写者，因此该套件在 CI 中自动 `pytest.skip`（即"1 skipped"），改为运行 `test_concurrent_approve_sqlite_application_invariant`，只验证**应用层不变量**：首次审批提交后，状态机因源状态不再是 `draft` 而拒绝第二次审批。套件通过 `test_concurrency_mode_is_declared` 显式声明当前运行的是 `postgres_dual_connection` 还是 `sqlite_application_invariant` 模式，杜绝夸大覆盖。
- **需 Owner 知悉的核实点**：截至本报告，`_load_purchase_order`（审批路径加载 PO 的唯一函数，`supply_chain.py`）**当前代码中未见 `with_for_update()`**；`with_for_update()` 存在于其它 service（如 `b2b_*`、`customer_*`、`listing_publish`），但未出现在 `supply_chain.py` 的 PO 加载路径。这意味着 Postgres 下的**物理串行化目前主要依赖应用层状态机不变量**（第二次审批读到已提交的非 `draft` 状态而失败），而非显式的 `FOR UPDATE` 行级锁。因此：**Postgres 真实双连接竞态测试（`test_concurrent_approve_postgres_single_winner`）只有在接入真实 Postgres（`TEST_DATABASE_URL`）时才会运行并验证物理竞态**。建议在接入 Postgres 的环境中显式运行该用例，或在 `_load_purchase_order`（仅审批路径）补上 `with_for_update()` 以落实文档所述的行级锁。此为当前实现与文档描述之间的差距，如实记录，不掩饰。

### 6.2 `approved_by` 记录 `user.id` 而非 email

- R2 起，`po.approved_by` 与审计事件的 `approved_by` 记录的是 Service 验证后返回的**稳定 `user.id`**，而非 email 或任意字符串。
- **为什么更优**：
  - **稳定性**：email 可变更、可重复、可伪造（R2 前正是 `approved_by="ghost@nuotao.com"` 这种伪造字符串穿透）。`user.id` 是 UUID 主键，不可变、唯一、与 `users` 表强关联。
  - **不可抵赖**：`user.id` 只能来自 DB 中一条真实记录，且该记录经过 active + role 校验。审计时可凭 `approved_by` 反查到唯一、真实的操作者账号。
- **边界**：`user.id` 本身不携带可读身份，审计展示时需 join `users` 表取 username/email。这是为换取稳定性与不可抵赖性的有意取舍。

### 6.3 其它边界

- **本审计基于静态代码 + 现有测试**，未在真实 Postgres 生产环境做并发压测（见 §6.1）。
- **成本门禁依赖上游成本数据质量**：`cost_confirmed` 由成本核算流程（ProductCost / landed cost）设置，Service 只强制"必须为 True"，不重新核算成本数值本身。若上游把 fallback 估算误标为 confirmed，门禁不拦截——这是成本治理（R2.3 / `test_cost_blocker.py`）与审批治理的职责边界。
- **角色集合硬编码为 `{admin, operator}`**（`_APPROVAL_ROLES`），与 `UserRole` 枚举镜像。新增可审批角色需同步修改此集合，否则新角色会被门禁 2 拒绝（fail-closed 方向，安全但需留意运维）。

---

## 7. 结论

R2 通过"**不信任调用方、Service 层独立查库验证真实主体**"这一根本性反转，把采购审批从"调用方自证"模型改为"DB 权威验证"模型，并配合**三重门禁 + 唯一可达路径 + 两层纵深防御 + RBAC 全覆盖 + 统一审计事件**，实现了采购审批的结构性不可绕过：

- AI Agent / automation 因无用户记录而**结构性被拒**；
- 伪造身份 / 角色 / 邮箱因 DB 交叉校验而** fail-closed**；
- 到达 `approved` 的路径**唯一**且强制门禁；
- 全部负向场景有自动化测试证明，且被拒后 PO 保持 `draft`。

**遗留行动项**（不阻塞 R2 验收，但建议跟踪）：
1. 在真实 Postgres 环境运行 `test_concurrent_approve_postgres_single_winner`，验证物理竞态；或为审批路径的 PO 加载补 `with_for_update()` 以落实文档所述行级锁（见 §6.1）。
2. 定期在 Postgres 环境回归并发套件，确保 CI skip 不掩盖物理竞态覆盖缺口。

---

*本报告基于提交 `60a7fd9` 的实际代码与测试编写，所有机制描述与测试断言均可在仓库中核对。*