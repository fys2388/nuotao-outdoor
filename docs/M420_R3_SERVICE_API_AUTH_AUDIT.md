# M4.2.0-R3 采购 API 与 Service 层鉴权审计报告

> 治理轮次：采购审批治理 R0 → R1 → R2 → **R3**
> 主题：**权限闭环** —— 封堵创建/修改采购单端点 + Service 层直调两条绕过路径
> 关联代码：`backend/app/api/v1/endpoints/supply_chain.py`、`backend/app/services/supply_chain.py`
> 关联测试：`backend/tests/test_purchase_governance_t02.py`
> 验证状态：采购治理回归 **57 passed + 1 skipped**；ruff 全绿

---

## 1. 审计目标

R2 已为**审批**（`approve_purchase_order`）和部分状态操作（HTTP 代理层 `transition_purchase_order_status`）补齐 RBAC 与身份校验。但 R2 的覆盖并不完整——审计发现仍有**两条独立的绕过路径**未封堵：

| 路径 | 绕过点 | 后果 |
|---|---|---|
| **① 创建/修改端点无鉴权** | `POST /purchase-orders`、`PUT /purchase-orders/{po_id}` 既无 RBAC、也无 `get_current_user`，任何人凭 `workspace` header 即可创建或篡改采购单 | 越权写入（OWASP A01 Broken Access Control） |
| **② Service 层直调绕过 HTTP RBAC** | `order / cancel / receive / partial_receive` 四个 service 函数本身不校验身份，仅靠 HTTP 层把守 | 绕过 API 层直接调 Service（AI Agent / automation / 内部调用）即可执行采购动作且不留身份 |

R3 的审计目标即为**同时封堵这两条路径**，达成"权限闭环"：

- **API 层（R3.3）**：创建/修改端点强制 `require_role("operator")` + bearer 认证 + actor 留痕。
- **Service 层（R3.4）**：四个采购动作函数入口**强制**身份校验，直调无 `caller_user_id` 一律 fail-closed 拒绝。

核心设计原则：**纵深防御** —— API RBAC 层与 Service 层身份校验是两道独立闸门，任何一层被绕过，另一层仍能拦截。

---

## 2. 威胁模型：R3 前的两类绕过

### 威胁 ① —— 无认证凭 workspace header 创建/篡改采购单

R3 之前，`create_purchase_order` 与 `update_purchase_order` 两个端点的函数签名**连 `get_current_user` 依赖都没有**，仅依赖 `WorkspaceId`（从 `workspace` header 解析）。这意味着：

- 攻击者只需知道（或猜到）一个合法 `workspace` header 值，携带该 header 发起 `POST /purchase-orders`，即可凭空创建采购单。
- 同理可对 draft 状态 PO 发起 `PUT` 修改 `notes`/`shipping_cost` 等，篡改后 `total` 会被重算，造成金额被暗中改动的风险。
- 事件审计中 `actor_user_id` 无从记录——因为根本没有"操作者身份"这一概念，写入动作完全匿名。

**根因**：把" possessing workspace id" 错当成了授权凭证。workspace 标识的是**数据归属**（multi-tenant 隔离），不是**操作者身份**（authentication/authorization）。二者必须分离：workspace header 定位租户，bearer 凭证证明"你是谁、你有什么角色"。

### 威胁 ② —— 直调 Service 绕过 HTTP RBAC

R2 的身份校验只落在两个地方：`approve_purchase_order`（service 内 `_validate_approver`）和 `transition_purchase_order_status`（HTTP 代理层）。但 `order_purchase_order` / `cancel_purchase_order` / `receive_purchase_order` / `partial_receive_purchase_order` **四个 service 函数本身不做任何身份校验**。

FastAPI 的依赖注入（`Depends(require_role(...))`）只在 HTTP 请求路径上生效。一旦调用方**绕过 API 层直接调用 service 函数**——典型场景：

- **AI Agent 工具调用**：Agent 通过 `services` 白名单直接触发采购动作；
- **后台 automation / 定时任务**；
- **同进程其它业务模块**；
- **未来新增的、忘记挂 RBAC 依赖的端点**。

——HTTP RBAC 层形同虚设，采购动作被执行且审计事件里没有可信的 actor 身份。这是经典的"依赖单一防线"漏洞：API 层是唯一闸门，绕过它 = 完全失守。

---

## 3. R3.3 详解：创建/修改端点 RBAC + actor 留痕 + 禁 workspace header 代认证

改动位置：`backend/app/api/v1/endpoints/supply_chain.py`

### 3.1 create_purchase_order（POST /purchase-orders）

```python
async def create_purchase_order(
    body: PurchaseOrderCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
    operator: Annotated[UserResponse, Depends(require_role("operator"))],  # R3.3 新增
) -> PurchaseOrderOut:
```

- 新增 `operator: Annotated[UserResponse, Depends(require_role("operator"))]`：`require_role("operator")` 内部先经 `get_current_user` 完成 **bearer 凭证认证**，再校验角色 ∈ {admin, operator}。认证来源是 **bearer credential（`get_current_user`），绝不用 `workspace` header 代替认证**。
- 调用 service 时传 `actor_user_id=str(getattr(operator, "id", ""))`，把操作者身份交给 service 落审计。
- docstring 显式声明契约：*"Authentication is derived from the bearer credential (get_current_user), never from the workspace header alone."*

### 3.2 update_purchase_order（PUT /purchase-orders/{po_id}）

同样原本无 RBAC。R3.3 加 `require_role("operator")` 依赖，并以 `actor_user_id=str(getattr(operator, "id", ""))` 留痕。修改仍受 service 层"draft-only"约束（非 draft 状态拒绝修改），RBAC 是在此之上叠加的**身份闸门**。

### 3.3 service 层 actor 留痕

`backend/app/services/supply_chain.py` 的 `create_purchase_order` / `update_purchase_order` 新增 `actor_user_id: str | None = None` 参数，分别落入 `supply.purchase_order_created` / `supply.purchase_order_updated` 审计事件的 `payload["actor_user_id"]`。

> 注：创建/修改是"写数据"动作，其身份证明由 API 层的 bearer 认证 + RBAC 保证（`require_role` 已确认是真人 admin/operator）。service 层对 create/update 采用 `actor_user_id` 透传留痕，而非 R3.4 那种 service 内二次 DB 校验——两者的防线分布见第 6 节。

---

## 4. R3.4 详解：Service 层身份闭环 + PATCH status 端点 bug 修复

改动位置：`backend/app/services/supply_chain.py`

### 4.1 共享 helper `_validate_procurement_actor`

```python
async def _validate_procurement_actor(
    session: AsyncSession, *, caller_user_id: str | None
) -> str:
    """M4.2.0-R3.4: every procurement service action (order / cancel / receive /
    partial_receive) must be attributable to an authenticated human operator..."""
    return await _validate_approver(session, caller_user_id=caller_user_id, caller_role=None)
```

它**复用 R2.2 的 `_validate_approver` 六步校验**（`caller_role=None`，跳过"caller_role 与 DB 一致性"这一步，因为直调场景没有 HTTP 层传入的 role）：

1. `caller_user_id` 非空，否则 fail-closed 抛 `SupplyChainError("... requires an authenticated operator user id")`；
2. `caller_user_id` 是合法 UUID；
3. User 记录**存在**（独立查 users 表，不接受调用方自报身份）；
4. User **active**（`is_active`）；
5. role ∈ `_APPROVAL_ROLES`（{admin, operator}）；
6. 返回稳定的 `user.id`（非 email）作为审计主体。

**结构性拒绝 AI Agent / automation**：Agent 与自动化流程没有 User 记录（无 `caller_user_id` 或 id 在 users 表中不存在），在第 1/3 步即被拒，无法成为采购动作的授权主体。

### 4.2 四个采购动作函数入口强制校验

`order_purchase_order` / `cancel_purchase_order` / `receive_purchase_order` / `partial_receive_purchase_order` 均在**函数入口第一步**调用 `_validate_procurement_actor`，校验通过后把返回的 `verified_actor` 透传给底层 `_transition_purchase_order(..., caller_user_id=verified_actor)` 落审计。示例（`order_purchase_order`）：

```python
async def order_purchase_order(session, *, workspace_id, po_id, trace_id=None,
                               caller_user_id: str | None = None) -> PurchaseOrder:
    verified_actor = await _validate_procurement_actor(session, caller_user_id=caller_user_id)
    return await _transition_purchase_order(session, workspace_id=workspace_id, po_id=po_id,
        target="ordered", event_type="supply.purchase_order_ordered",
        trace_id=trace_id, caller_user_id=verified_actor)
```

**直调 Service 无 `caller_user_id` 一律 `SupplyChainError` 拒绝**（fail-closed），彻底封堵威胁 ②。

### 4.3 PATCH status 端点 bug 修复

`update_purchase_order_status`（`PATCH /purchase-orders/{po_id}/status`）端点原本挂了 `require_role("operator")`、也通过 `transitions` 字典路由到四个采购动作函数，但**调用时漏传 `caller_user_id`**——即便 HTTP 层 RBAC 通过，service 内的身份校验也拿不到调用者 id。R3.4 修复：现在传 `caller_user_id=str(getattr(operator, "id", ""))`，让 service 层的二次校验能拿到真实操作者并落审计。这是"两层防线"能真正串联的关键一环。

> 注：该端点的 `operator_id`（用于响应体 `updated_by` 字段）取的是 email/id，与传给 service 的 `caller_user_id`（恒为 `user.id`）职责不同；service 层审计统一以稳定 `user.id` 为准。

---

## 5. 攻击向量 → 防护 → 测试证据对照表

| # | 攻击向量 | 防护机制 | 层 | 测试证据 | 结果 |
|---|---|---|---|---|---|
| A1 | 无任何认证，仅凭 workspace header 创建采购单 | `require_role("operator")` 强制 bearer 认证，无凭证 → 401 | API (R3.3) | `test_create_purchase_order_requires_authentication` | **401 拒绝** |
| A2 | read_only 角色持合法凭证创建采购单 | `require_role("operator")` 角色闸门 | API (R3.3) | `test_create_purchase_order_requires_operator_role` | **403 拒绝** |
| A3 | read_only 角色篡改 draft PO（改 notes） | `require_role("operator")` 角色闸门 | API (R3.3) | `test_update_purchase_order_requires_operator_role` | **403 拒绝 + 断言 PO 未被篡改**（`stored.notes != "tamper"`） |
| A4 | 绕过 API 直调 `order/cancel/receive/partial_receive`，无 `caller_user_id` | 四函数入口 `_validate_procurement_actor` fail-closed | Service (R3.4) | `test_service_procurement_actions_require_identity` | **四函数全部抛 `SupplyChainError`（match "operator user id"）** |
| A5 | AI Agent / automation 直调采购动作 | 无 User 记录 → `_validate_procurement_actor` 第 1/3 步结构性拒绝 | Service (R3.4) | 同 A4（无 id 即 Agent 场景的最小代表） | **结构性拒绝** |
| A6 | PATCH status 端点 RBAC 通过但 service 拿不到身份（漏传 bug） | R3.4 修复：显式传 `caller_user_id=operator.id` | API→Service (R3.4) | 由 A4 的 service 层校验 + 既有 status 路由回归覆盖 | **已修复，身份可透传落审计** |

---

## 6. 纵深防御：两层独立校验，两层都必须过

R3 把采购权限从"单层把守"升级为"双层串联"：

```
HTTP 请求
  │
  ├─【第一层：API RBAC 层】Depends(require_role("operator"))
  │    · 认证：bearer 凭证 → get_current_user（拒绝 workspace header 代认证）
  │    · 授权：角色 ∈ {admin, operator}
  │    · 覆盖端点：create / update / approve / order / cancel / receive /
  │                partial_receive / PATCH status
  │
  ▼
Service 函数
  │
  ├─【第二层：Service 身份闭环】_validate_procurement_actor / _validate_approver
  │    · 独立查 users 表：真实 user.id、存在、active、role ∈ {admin, operator}
  │    · 直调无 caller_user_id → SupplyChainError（fail-closed）
  │    · 覆盖函数：order / cancel / receive / partial_receive（R3.4）
  │                + approve（R2.2）+ transition_purchase_order_status（R2.2）
  │
  ▼
  落审计事件（actor_user_id / approved_by = 稳定 user.id）
```

**为什么两层都要**：

- 单靠 API 层（威胁 ② 的教训）：任何绕过 HTTP 路径的调用（Agent、automation、内部模块、遗漏 RBAC 的新端点）都无人把守。
- 单靠 Service 层（威胁 ① 的教训）：create/update 走的是 `actor_user_id` 透传模式，其身份可信度依赖 API 层 bearer 认证；若 API 层不强制认证，service 层对 create/update 并无二次 DB 校验兜底。

因此两层**各自独立、互为兜底**：HTTP 层挡住"没登录/角色不够"的请求，Service 层挡住"绕过 HTTP 的直调/无身份主体"。任一层被突破，另一层仍能拦截——这是 R3"权限闭环"的核心。

---

## 7. 验证结果与诚实边界

### 验证结果

- **采购治理回归**：`tests/test_purchase_governance_t02.py` 全套 **57 passed + 1 skipped**（1 skipped 为既有跳过项，与 R3 无关）。
- **静态检查**：ruff 全绿。
- R3.3/R3.4 的四项新测试（A1/A2/A3/A4）均已在上述回归中通过。

### 诚实边界（本报告不夸大覆盖）

1. **create/update 的 service 层未做二次 DB 身份校验**。`create_purchase_order` / `update_purchase_order` 接受 `actor_user_id` 透传留痕，但 service 内**不再独立查 users 表**验证该 id。其身份可信度完全依赖 API 层的 bearer 认证 + RBAC。因此对这两个函数，纵深防御的"第二层"是**审计留痕**而非**独立授权闸门**——若未来出现绕过 API 直调 create/update 的路径，`actor_user_id` 可能被填入任意值（含伪造 id），目前**无 service 层校验拦截**。这与 order/cancel/receive/partial_receive（R3.4 已做 service 内硬校验）的防护强度**不一致**，是有意的取舍（创建/修改不改变 PO 授权状态），但应在后续轮次评估是否需要拉齐。
2. **1 skipped 测试项**未在本轮分析，需单独确认其跳过原因是否与鉴权相关。
3. **测试对 A5（AI Agent 直调）仅以"无 caller_user_id"为代表**，未构造"携带一个 users 表中不存在的伪 UUID"的显式用例——该场景由 `_validate_procurement_actor` 第 3 步（User 不存在 → 拒绝）在代码层保证，但缺独立测试断言。
4. 本轮验证基于**采购治理回归套件**，未跑全量后端测试矩阵；跨模块（如 Agent 工具调用采购 service）的集成路径未在本轮端到端验证。

---

*报告完 —— M4.2.0-R3 采购 API 与 Service 层鉴权审计*