# Nuotao AI OS — API Authentication Coverage Matrix

> **文件**：`docs/AUTHENTICATION_COVERAGE_MATRIX.md`
> **版本**：v1.0（2026-08-24）
> **阶段**：P0-1 Security Remediation — 第一阶段（只读审计）
> **性质**：**READ → SCAN → CLASSIFY → DOCUMENT**。本轮未修改任何业务代码、
> 未创建 migration、未修改数据库、未修改前端、未删除文件、未修改测试期望。
>
> 本文件每一条结论都有可复现的代码证据（文件 + 行号或 AST 扫描结果）。
> **不猜测。** 无法从代码判定的，标注为 `UNKNOWN` 并单独列出。

---

## 0. 方法学与可复现性

审计不使用人工抽样，而是对整个 `backend/app/api/v1/endpoints/` 做 AST 解析。

| 工具 | 作用 |
|---|---|
| `_auth_audit.py` | AST 解析 77 个端点文件，抽取每个路由的 method / path / handler / 依赖 |
| `_auth_classify.py` | 规则化分类 + 风险定级 + 测试覆盖探测，产出矩阵 |
| `_auth_rank.py` | 严重度排序 |
| `_auth_stats.py` / `_auth_top20.py` | 交叉校验 |

### 三个必须处理的技术陷阱（否则统计会严重失真）

1. **模块级 `Annotated[..., Depends(...)]` 别名**。项目大量使用
   `WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]`，
   依赖声明在**类型注解**里而非 `= Depends(...)` 默认值里。
   若只扫描 `Depends(...)` 字面量，会把这些路由误报为「零依赖」。
2. **`Depends(require_role("admin"))` 嵌套调用**。依赖工厂本身是 Call 表达式，
   需展开否则 4 条 ADMIN 路由会被误报为未认证。
3. **传输层鉴权不走 `Depends()`**。`webhooks.py` / `webhooks_generic.py` 用
   请求体 HMAC 校验；`feishu.py` 则**完全没有**。仅扫描依赖会同时漏报前两者。

### 与用户给定数字的偏差（必须更正）

| 指标 | 用户给定 | 实测 | 说明 |
|---|---|---|---|
| Endpoint 文件 | 77 | **77** ✅ | 一致 |
| Routes | 795 | **652** | AST 扫描到 652 个路由装饰器；
运行中应用 OpenAPI 报告 **650 个 path+method 操作 / 547 个唯一 path**，
两者互为印证。795 可能计入了 `HEAD`/`OPTIONS` 自动路由或重复项。**以 652 为准。** |

---

## 1. 数字总览

### 1.1 按认证类别

| 类别 | 数量 | 占比 | 其中写操作 |
|---|---|---|---|
| **UNKNOWN**（无任何认证机制） | **590** | 90.5% | **345** |
| AUTHENTICATED_USER（OAuth2 JWT） | 20 | 3.1% | 11 |
| SPECIAL_AUTH（B2B Agent JWT + 飞书） | 11 | 1.7% | 3 |
| SYSTEM（worker/scheduler/backup/deployment） | 15 | 2.3% | 3 |
| PUBLIC（健康检查 + 登录注册） | 6 | 0.9% | 4 |
| M2M_WEBHOOK（WooCommerce HMAC） | 4 | 0.6% | 3 |
| ADMIN（`require_role("admin")`） | 5 | 0.8% | 4 |
| WORKSPACE_USER（身份 + 工作区授权） | 1 | 0.2% | 0 |
| **合计** | **652** | 100% | **373** |

> **只有 41 条路由（6.3%）具备任何形式的认证**（20 + 11 + 4 + 5 + 1）。
> 其中真正的人类用户认证仅 26 条（AUTHENTICATED_USER 20 + ADMIN 5 + WORKSPACE_USER 1）。

### 1.2 按风险等级

| 等级 | 数量 |
|---|---|
| **P0** | **444** |
| P1 | 25 |
| P2 | 12 |
| P3 | 171 |
| **合计** | **652** |

> **P0 风险已降至 444 条。** 唯一的例外项已关闭：
> `/webhooks/woocommerce/test`（行 470）此前是**唯一的 P0-OPEN**——
> 无签名校验且无条件注册进 `api_router`，可匿名向默认 workspace 写入订单。
> 现已改为独立 `test_router`，仅 `not get_settings().is_production` 时挂载
> （生产返回 404），非生产必须携带已验证 JWT 且 `role=admin`；
> 风险等级由 **P0-OPEN 降为 P2**，分类由 M2M_WEBHOOK 归入 ADMIN。

### 1.3 用户要求的十项统计

| # | 指标 | 值 |
|---|---|---|
| 1 | 总 routes 数 | **652** |
| 2 | PUBLIC 数量 | **6** |
| 3 | AUTHENTICATED 数量 | **20** |
| 4 | WORKSPACE_USER 数量 | **1** |
| 5 | ADMIN 数量 | **5** |
| 6 | M2M 数量 | **4** |
| 7 | SYSTEM 数量 | **15** |
| 8 | UNKNOWN 数量 | **590** |
| 9 | P0 数量 | **444** |
| 10 | P1 数量 | **25** |

### 1.4 按文件

**72 / 77 个端点文件的鉴权覆盖率为 0。**

只有 3 个文件使用了基于 `Depends()` 的认证依赖：

| 文件 | 认证依赖 | 说明 |
|---|---|---|
| `auth.py` | `get_current_user` / `require_role` | OAuth2 密码登录 + JWT，真实认证 ✅ |
| `b2b_portal.py` | `get_current_b2b_agent` | B2B 代理商独立认证域 ✅ |
| `identity.py` | `require_authenticated_actor` + `require_workspace_context` | 唯一做了身份+工作区双重校验的业务端点 ✅ |

另有 2 个文件使用传输层 HMAC（`webhooks.py`、`webhooks_generic.py`），
以及 1 个文件（`feishu.py`）**完全没有认证**。

> **P0 修复后**：`webhooks_generic.py` 的签名校验 webhook
> （`/woocommerce/generic`、`/woocommerce/events`）仍走 HMAC；而原先无条件挂载的
> `POST /webhooks/woocommerce/test` 已移出 `api_router`，改由独立
> `test_router` 承载，仅在生产之外注册并要求 `require_role("admin")`。

---

## 2. 本轮新发现（5 项，此前所有文档均未记录）

这 5 项是按代码证据新确认的，改变了对 P0-1 严重度的判断。

### 2.1 🔴 `POST /feishu/card-callback`：可伪造审批人并触发自动执行

这是本轮最严重的发现，**比「无鉴权」更严重**。

`backend/app/api/v1/endpoints/feishu.py` L108–132：

```python
@router.post("/card-callback")
async def feishu_card_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ...
    body = await request.json()
    ...
    action = event.get("action", {}).get("tag", "")
    ...
    operator = event.get("operator", {}).get("name", "飞书用户")
    ...
    await suggestion_service.approve_suggestion(db, suggestion_id, approved_by=operator)
    ...
    asyncio.create_task(_execute_suggestion_async(suggestion_id))
```

三个问题叠加：

| # | 问题 | 证据 |
|---|---|---|
| 1 | **无签名校验**。飞书回调的 `timestamp` / `nonce` / `sign` 全部被忽略，
全文件无 `hmac` / `verify` / `signature` 任何一处 | `feishu.py` 全文 290 行 |
| 2 | **审批人身份来自攻击者可控的 JSON 字段**
`event.get("operator", {}).get("name")` | L130 |
| 3 | **批准后立即自动执行**，`asyncio.create_task(_execute_suggestion_async)` | L132 |

后果：**任何能访问后端 IP 的调用方**，都能：

```json
POST /api/v1/feishu/card-callback
{"event": {"action": {"tag": "approve"},
            "operator": {"name": "admin@company.com"},
            "context": {"suggestion_id": "778"}}}
```

→ 以「admin@company.com」的身份批准任意一条 Agent 建议，
并**自动触发其执行**。

这直接违反 `AGENTS.md` §3.1「Agent 是提议者不是执行者，
高风险操作（发货、退款、改价、删除）必须进入审批队列，人工确认后执行」。
这里「人工确认」这一步被完全旁路了。

### 2.2 🔴 身份来源可配置，且**默认值是「请求体自声明」**

`backend/app/core/actor.py` L9–11 与 L67–73：

```python
- ``body``   (default, staging-safe): actor comes from the request body
...
class BodyActorProvider:
    """Staging default: actor is declared in the request body."""
    def resolve(self, request: Request, body_actor: str | None) -> str:
        if body_actor is None:
            raise ActorResolutionError("actor is required")
        return _validate_actor(body_actor)
```

`backend/app/core/config.py` **L183**：`actor_provider: str = "body"`

配置漂移实测：

| 文件 | `ACTOR_PROVIDER` | 实际身份来源 |
|---|---|---|
| `.env`（本地） | `header` | ✅ Clerk RS256 JWT |
| `.env.development` | **未设置** | ❌ 回落到代码默认 `body` = 请求体自声明 |
| `.env.staging` | **未设置** | ❌ 同上 |
| `.env.production` | **未设置** | ❌ 同上 |
| `.env.production.template` | **未设置** | ❌ 同上 |

**任何从 production template 新建的环境，只要没手动补上
`ACTOR_PROVIDER=header`，就自动进入「自声明身份」模式。**
这是个静默失效的开关——不会报错，只会让认证形同虚设。

### 2.3 🔴 RBAC 有两处静默放行

`backend/app/services/approval_rbac.py` L138–147：

```python
settings = get_settings()
if not settings.approval_rbac_enabled:
    return True
roles = await _enabled_roles(session, workspace_id=workspace_id)
if not roles:
    logger.info("approval RBAC: workspace %s has no enabled roles - legacy open mode", ...)
    return True
```

- `approval_rbac_enabled` 代码默认 `True`（`config.py` L171）✅
- 但**只要某工作区没有配置任何 enabled role，全部权限检查返回 True**

即：RBAC 的默认行为是「**没配规则就等于全放行**」，而不是「默认拒绝」。
对新工作区这是静默失效。

### 2.4 🟡 RBAC HTTP 依赖存在但从未接线

`backend/app/api/deps.py` L161–198 定义了 `require_permission(permission)`，
它组合了 `require_authenticated_actor` + `require_workspace_context` + RBAC 检查。
**设计完整、可用。**

但全仓库检索：`require_permission` 的 4 次出现**全部在 `deps.py` 内部**
（docstring L8、`def` L161、内部函数 L164、`return` L198）。
**没有任何一条路由使用它。**

同时，RBAC 在**服务层**有直接调用（不是经 HTTP 依赖）：

| 位置 | 权限 |
|---|---|
| `product_intelligence.py` L603 | `product.candidate.manage` |
| `product_intelligence.py` L645 | `product.candidate.promote` |
| `scraping.py` L58 | `scraping.job.submit` |

注意 `scraping.py` L55–63 的写法：

```python
actor = resolve_actor(request, body.actor) if getattr(body, "actor", None) else None
try:
    if actor:          # ← actor 为 None 时整段权限检查被跳过
        await check_actor_permission(...)
```

**请求体不带 `actor` 字段就跳过全部权限校验。**

### 2.5 🟡 重复路由注册：`/products/batch-update` 注册了两次

`product_intelligence.py` 中 `product_router.post("/batch-update")`
出现在 **L776** 与 **L828** 两处。FastAPI 会按注册顺序匹配，
**第二个 handler 是不可达的死代码**——任何修复、审查、测试如果落在
第二个 handler 上都不会生效。这是一条真实的治理缺陷。

---

## 3. Top 20 最高风险端点（按严重度排序，14 字段全量）

### #1 `POST /feishu/card-callback` — 🔴 最严重

| 字段 | 值 |
|---|---|
| HTTP method | `POST` |
| Path | `/api/v1/feishu/card-callback` |
| Endpoint file | `feishu.py` |
| Handler | `feishu_card_callback` |
| Current dependencies | `get_db`（仅此一个） |
| Authentication mechanism | **NONE** — handler 内无任何签名校验 |
| Workspace mechanism | **none**（连工作区解析都没有） |
| Authorization mechanism | **FORGED** — `operator` 从攻击者可控 JSON 读取 |
| Current risk | **P0** |
| Expected access scope | 已验证的飞书用户身份 |
| Recommended dependency | 接入飞书回调签名校验（`timestamp`+`nonce`+`sign`）；`operator` 必须来自已验证的飞书 `open_id`，不得取自 body；自动执行前二次确认 |
| Business impact | 🔴 **可远程伪造审批人 + 自动执行 Agent 建议**（发货/退款/改价/删除类），直接违反 `AGENTS.md` §3.1 |
| Test coverage | **none detected** |
| Priority | **P0（最高，建议单独成项）** |

### #2 `POST /products/{product_id}/push-woocommerce`

| 字段 | 值 |
|---|---|
| HTTP method | `POST` |
| Path | `/api/v1/products/{product_id}/push-woocommerce` |
| Endpoint file | `products.py` |
| Handler | `push_single_product_to_woocommerce` |
| Current dependencies | `get_db`, `get_workspace_id` |
| Authentication mechanism | **NONE** — `get_workspace_id` 是请求头回显，不是认证 |
| Workspace mechanism | `get_workspace_id`（未校验的 `X-Workspace-Id` 回显） |
| Authorization mechanism | none |
| Current risk | **P0** |
| Expected access scope | workspace-scoped，需 `product.publish` 权限 |
| Recommended dependency | `require_workspace_context` + `require_permission("product.publish")` |
| Business impact | **未认证即可向 WooCommerce 发布商品**；`?force=true` 可绕过闸门 |
| Test coverage | none detected |
| Priority | **P0** |

### #3 `POST /products/push-woocommerce`（批量推送）

| 字段 | 值 |
|---|---|
| HTTP method | `POST` |
| Path | `/api/v1/products/push-woocommerce` |
| Endpoint file | `products.py` |
| Handler | `push_products_to_woocommerce` |
| Current dependencies | `get_db`, `get_workspace_id` |
| Authentication mechanism | **NONE** |
| Workspace mechanism | `get_workspace_id`（未校验） |
| Authorization mechanism | none |
| Current risk | **P0** |
| Expected access scope | workspace-scoped，需 `product.publish` |
| Recommended dependency | `require_workspace_context` + `require_permission("product.publish")` |
| Business impact | **未认证批量发布到 WooCommerce** |
| Test coverage | none detected |
| Priority | **P0** |

### #4 `POST /products/import`

| 字段 | 值 |
|---|---|
| HTTP method | `POST` |
| Path | `/api/v1/products/import` |
| Endpoint file | `products.py` |
| Handler | `import_products` |
| Current dependencies | `get_db`, `get_workspace_id` |
| Authentication mechanism | **NONE** |
| Workspace mechanism | `get_workspace_id`（未校验） |
| Authorization mechanism | none |
| Current risk | **P0** |
| Expected access scope | workspace-scoped，需 `product.manage` |
| Recommended dependency | `require_workspace_context` + `require_permission("product.manage")` |
| Business impact | **未认证写入任意产品数据（含成本字段）** |
| Test coverage | indirect（771 处对 `'import'` 的测试引用） |
| Priority | **P0** |

### #5 `POST /product-candidates/{product_id}/promote`

| 字段 | 值 |
|---|---|
| HTTP method | `POST` |
| Path | `/api/v1/product-candidates/{product_id}/promote` |
| Endpoint file | `product_intelligence.py` |
| Handler | `promote_candidate` |
| Current dependencies | `get_db`, `get_workspace_id`；handler 内 `resolve_actor` + `check_actor_permission("product.candidate.promote")` |
| Authentication mechanism | **取决于 `ACTOR_PROVIDER`**：`header` 时为 JWT ✅；`body` 时（代码默认值）**为请求体自声明** ❌ |
| Workspace mechanism | `get_workspace_id`（未校验） |
| Authorization mechanism | RBAC 有调用，但**工作区无 enabled role 时静默放行** |
| Current risk | **P0**（生产配置）/ **P1**（本地 `.env` 为 `header` 时） |
| Expected access scope | workspace-scoped，需 `product.candidate.promote` |
| Recommended dependency | 强制 `ACTOR_PROVIDER=header` 为唯一允许值；RBAC 改为「无角色时拒绝」 |
| Business impact | 触发 Product Master → WooCommerce Draft 生成流程 |
| Test coverage | indirect（19 处） |
| Priority | **P0** |

### #6 `POST /approvals/{approval_id}/approve`

| 字段 | 值 |
|---|---|
| HTTP method | `POST` |
| Path | `/api/v1/approvals/{approval_id}/approve` |
| Endpoint file | `agent_operations.py` |
| Handler | `approve_approval` |
| Current dependencies | `get_db`, `get_workspace_id` |
| Authentication mechanism | **NONE** |
| Workspace mechanism | `get_workspace_id`（未校验） |
| Authorization mechanism | none |
| Current risk | **P0** |
| Expected access scope | workspace-scoped，需 `approval.decide` |
| Recommended dependency | `require_workspace_context` + `require_permission("approval.decide")` |
| Business impact | **未认证决定 Agent 审批结果** |
| Test coverage | indirect（451 处） |
| Priority | **P0** |

### #7 `POST /purchase-orders/{po_id}/approve`

| 字段 | 值 |
|---|---|
| HTTP method | `POST` |
| Path | `/api/v1/purchase-orders/{po_id}/approve` |
| Endpoint file | `supply_chain.py` |
| Handler | `approve_purchase_order` |
| Current dependencies | `get_db`, `get_workspace_id` |
| Authentication mechanism | **NONE** |
| Workspace mechanism | `get_workspace_id`（未校验） |
| Authorization mechanism | none |
| Current risk | **P0** |
| Expected access scope | workspace-scoped，需 `procurement.approve` |
| Recommended dependency | `require_workspace_context` + `require_permission("procurement.approve")` |
| Business impact | **未认证批准采购单 → 触发对供应商的采购支出** |
| Test coverage | indirect（451 处） |
| Priority | **P0** |

### #8 `POST /refunds/{refund_id}/approve`

| 字段 | 值 |
|---|---|
| HTTP method | `POST` |
| Path | `/api/v1/refunds/{refund_id}/approve` |
| Endpoint file | `refunds.py` |
| Handler | `approve_refund` |
| Current dependencies | `get_db`, `get_workspace_id` |
| Authentication mechanism | **NONE** |
| Workspace mechanism | `get_workspace_id`（未校验） |
| Authorization mechanism | none |
| Current risk | **P0** |
| Expected access scope | workspace-scoped，需 `refund.approve` |
| Recommended dependency | `require_workspace_context` + `require_permission("refund.approve")` |
| Business impact | **未认证批准退款**（资金流出 + L4 PII） |
| Test coverage | indirect（451 处） |
| Priority | **P0** |

### #9 `POST /selection/decisions/{decision_id}/approve`

| 字段 | 值 |
|---|---|
| HTTP method | `POST` |
| Path | `/api/v1/selection/decisions/{decision_id}/approve` |
| Endpoint file | `selection.py` |
| Handler | `approve_decision` |
| Current dependencies | `get_db`（**连工作区解析都没有**） |
| Authentication mechanism | **NONE** |
| Workspace mechanism | **none** |
| Authorization mechanism | none |
| Current risk | **P0** |
| Expected access scope | workspace-scoped，需 `selection.decide` |
| Recommended dependency | `require_workspace_context` + `require_permission("selection.decide")` |
| Business impact | 未认证决定选品审批结果 |
| Test coverage | indirect（64 处） |
| Priority | **P0** |

### #10 `POST /supply-chain-calibration/runs/{run_id}/approve`

| 字段 | 值 |
|---|---|
| HTTP method | `POST` |
| Path | `/api/v1/supply-chain-calibration/runs/{run_id}/approve` |
| Endpoint file | `supply_chain_learning.py` |
| Handler | `approve_calibration_run` |
| Current dependencies | `get_db`, `get_workspace_id` |
| Authentication mechanism | **NONE** |
| Workspace mechanism | `get_workspace_id`（未校验） |
| Authorization mechanism | none |
| Current risk | **P0** |
| Expected access scope | workspace-scoped，需 `calibration.approve` |
| Recommended dependency | `require_workspace_context` + `require_permission("calibration.approve")` |
| Business impact | **未认证批准校准 → 影响后续成本/供应链预测权重** |
| Test coverage | indirect（123 处） |
| Priority | **P0** |

### #11 `POST /procurement/sync-from-wc-order`

| 字段 | 值 |
|---|---|
| HTTP method | `POST` |
| Path | `/api/v1/procurement/sync-from-wc-order` |
| Endpoint file | `procurement_workbench.py` |
| Handler | `sync_from_wc_order` |
| Current dependencies | **`[]`（零依赖）** |
| Authentication mechanism | **NONE** |
| Workspace mechanism | **none** |
| Authorization mechanism | none |
| Current risk | **P0** |
| Expected access scope | workspace-scoped，需 `procurement.manage` |
| Recommended dependency | `require_workspace_context` + `require_permission("procurement.manage")` |
| Business impact | 未认证从 WC 订单触发采购流程 |
| Test coverage | none detected |
| Priority | **P0** |

### #12 `POST /woocommerce-sync/sync-orders`

| 字段 | 值 |
|---|---|
| HTTP method | `POST` |
| Path | `/api/v1/woocommerce-sync/sync-orders` |
| Endpoint file | `woocommerce_sync.py` |
| Handler | `sync_orders` |
| Current dependencies | **`[]`（零依赖）** |
| Authentication mechanism | **NONE** |
| Workspace mechanism | **none** |
| Authorization mechanism | none |
| Current risk | **P0** |
| Expected access scope | system / 需 `commerce.sync` |
| Recommended dependency | `require_workspace_context` + `require_permission("commerce.sync")` |
| Business impact | **未认证触发 WooCommerce → 内部订单同步（L4 PII 数据面）** |
| Test coverage | none detected |
| Priority | **P0** |

### #13 `POST /sourcing/batch-import`

| 字段 | 值 |
|---|---|
| HTTP method | `POST` |
| Path | `/api/v1/sourcing/batch-import` |
| Endpoint file | `sourcing.py` |
| Handler | `batch_import` |
| Current dependencies | `get_db`（无工作区解析） |
| Authentication mechanism | **NONE** |
| Workspace mechanism | **none** |
| Authorization mechanism | none |
| Current risk | **P0** |
| Expected access scope | workspace-scoped，需 `sourcing.manage` |
| Recommended dependency | `require_workspace_context` + `require_permission("sourcing.manage")` |
| Business impact | 未认证批量导入 sourcing 数据（含 1688 外部数据） |
| Test coverage | none detected |
| Priority | **P0** |

### #14 `POST /products/sync-inventory`

| 字段 | 值 |
|---|---|
| HTTP method | `POST` |
| Path | `/api/v1/products/sync-inventory` |
| Endpoint file | `product_intelligence.py` |
| Handler | `sync_inventory` |
| Current dependencies | `get_db`, `get_workspace_id` |
| Authentication mechanism | **NONE** |
| Workspace mechanism | `get_workspace_id`（未校验） |
| Authorization mechanism | none |
| Current risk | **P0** |
| Expected access scope | workspace-scoped，需 `inventory.sync` |
| Recommended dependency | `require_workspace_context` + `require_permission("inventory.sync")` |
| Business impact | **未认证写入库存**（影响线上可售状态） |
| Test coverage | none detected |
| Priority | **P0** |

### #15 `PUT /system-settings/`

| 字段 | 值 |
|---|---|
| HTTP method | `PUT` |
| Path | `/api/v1/system-settings/` |
| Endpoint file | `system_settings.py` |
| Handler | `update_system_settings` |
| Current dependencies | `get_db`（无工作区解析） |
| Authentication mechanism | **NONE** |
| Workspace mechanism | **none** |
| Authorization mechanism | none |
| Current risk | **P0** |
| Expected access scope | **admin** |
| Recommended dependency | `require_workspace_context` + `require_permission("system.admin")` |
| Business impact | **未认证修改全局系统配置** |
| Test coverage | none detected |
| Priority | **P0** |

### #16 `POST /system-settings/reset`

| 字段 | 值 |
|---|---|
| HTTP method | `POST` |
| Path | `/api/v1/system-settings/reset` |
| Endpoint file | `system_settings.py` |
| Handler | `reset_system_settings` |
| Current dependencies | `get_db` |
| Authentication mechanism | **NONE** |
| Workspace mechanism | **none** |
| Authorization mechanism | none |
| Current risk | **P0** |
| Expected access scope | **admin** |
| Recommended dependency | `require_workspace_context` + `require_permission("system.admin")` |
| Business impact | **未认证重置系统配置** |
| Test coverage | indirect（10 处） |
| Priority | **P0** |

### #17 `POST /products/batch-update`（⚠️ 重复注册）

| 字段 | 值 |
|---|---|
| HTTP method | `POST` |
| Path | `/api/v1/products/batch-update` |
| Endpoint file | `product_intelligence.py`（**L776 与 L828 各注册一次**） |
| Handler | `batch_update_products`（L776，可达）/ `batch_update`（L828，**死代码**） |
| Current dependencies | `get_db`, `get_workspace_id` |
| Authentication mechanism | **NONE** |
| Workspace mechanism | `get_workspace_id`（未校验） |
| Authorization mechanism | none |
| Current risk | **P0** |
| Expected access scope | workspace-scoped，需 `product.manage` |
| Recommended dependency | `require_workspace_context` + `require_permission("product.manage")`；**并删除 L828 的重复注册** |
| Business impact | **未认证批量修改产品主数据** |
| Test coverage | none detected |
| Priority | **P0** |

### #18 `POST /agent-registry/{agent_uuid}/rollback`

| 字段 | 值 |
|---|---|
| HTTP method | `POST` |
| Path | `/api/v1/agent-registry/{agent_uuid}/rollback` |
| Endpoint file | `agent_platform.py` |
| Handler | `rollback_agent` |
| Current dependencies | `get_db`, `get_workspace_id` |
| Authentication mechanism | **NONE** |
| Workspace mechanism | `get_workspace_id`（未校验） |
| Authorization mechanism | none |
| Current risk | **P0** |
| Expected access scope | workspace-scoped，需 `agent.admin` |
| Recommended dependency | `require_workspace_context` + `require_permission("agent.admin")` |
| Business impact | **未认证回滚 Agent 版本**（可回退到任意旧版本） |
| Test coverage | indirect（22 处） |
| Priority | **P0** |

### #19 `POST /agent-queue/dead-letters/{task_id}/replay`

| 字段 | 值 |
|---|---|
| HTTP method | `POST` |
| Path | `/api/v1/agent-queue/dead-letters/{task_id}/replay` |
| Endpoint file | `agent_operations.py` |
| Handler | `propose_dlq_replay` |
| Current dependencies | `get_db`, `get_workspace_id` |
| Authentication mechanism | **NONE** |
| Workspace mechanism | `get_workspace_id`（未校验） |
| Authorization mechanism | none |
| Current risk | **P0** |
| Expected access scope | workspace-scoped，需 `agent.admin` |
| Recommended dependency | `require_workspace_context` + `require_permission("agent.admin")` |
| Business impact | **未认证重放失败任务**（可重放任意曾失败的 Agent 执行） |
| Test coverage | indirect（6 处） |
| Priority | **P0** |

### #20 `DELETE /feedback/{feedback_id}`

| 字段 | 值 |
|---|---|
| HTTP method | `DELETE` |
| Path | `/api/v1/feedback/{feedback_id}` |
| Endpoint file | `marketing.py` |
| Handler | `delete_feedback` |
| Current dependencies | `get_db`, `get_workspace_id` |
| Authentication mechanism | **NONE** |
| Workspace mechanism | `get_workspace_id`（未校验） |
| Authorization mechanism | none |
| Current risk | **P0** |
| Expected access scope | workspace-scoped，需 `marketing.manage` |
| Recommended dependency | `require_workspace_context` + `require_permission("marketing.manage")` |
| Business impact | 未认证删除反馈数据 |
| Test coverage | indirect（22 处） |
| Priority | **P0** |

---

## 4. 认证类别定义与判定依据

| 类别 | 判定依据（代码事实） |
|---|---|
| **PUBLIC** | 路径属于 `{/healthz, /readyz, /health, /auth/login, /auth/register, /auth/refresh, /b2b-portal/auth/login}`。`healthz` 仅返回字符串，`readyz` 为就绪探针 |
| **AUTHENTICATED_USER** | handler 依赖 `get_current_user`（`auth.py` L48–73：OAuth2PasswordBearer + `validate_token` + 用户存在性/激活校验，**无 dev bypass**） |
| **WORKSPACE_USER** | 依赖 `require_workspace_context`（`deps.py`：身份解析 + 工作区映射 + 403 on mismatch） |
| **ADMIN** | 依赖 `require_role("admin")`（`auth.py` L76–89，4 处，全部为用户管理） |
| **SYSTEM** | 路径含 `worker` / `scheduler` / `backup` / `sweeper` / `deployment` |
| **M2M_WEBHOOK** | `webhooks.py` / `webhooks_generic.py`：请求体 HMAC-SHA256 + `hmac.compare_digest` |
| **SPECIAL_AUTH** | `get_current_b2b_agent`（B2B 独立 JWT 域）或 `feishu.py`（**无任何校验，见 §2.1**） |
| **INTERNAL** | 本轮无匹配项（所有内部端点都被归入 SYSTEM 或 UNKNOWN） |
| **UNKNOWN** | **以上全都不满足 = 无任何认证机制**。这是本轮的主体：590 条 |

### UNKNOWN 的进一步细分

| 子类型 | 数量 | 含义 |
|---|---|---|
| `get_workspace_id` 请求头回显（非认证） | 283 | 有工作区参数但**由调用方任意声明** |
| 零依赖（连 `get_db` 之外什么都没有） | 230 | 完全无鉴权上下文 |
| 其中为写操作（POST/PUT/PATCH/DELETE） | **345** | 未认证即改业务数据 |

### 单独列出：590 条 UNKNOWN 的完整清单

见**附录 A**（第 1–590 行按风险排序）。可筛选 `Category = UNKNOWN`。

---

## 5. 重点项核对（按用户要求 A–F）

| 项 | 结论 |
|---|---|
| **A.** `Depends(get_workspace_id)` 是否算 authenticated | **不算。** `core/workspace.py` L15–21 是纯请求头回显 + 默认值，无任何身份校验。审计中一律记为 `NONE` |
| **B.** `require_authenticated_workspace_id` | **该函数不存在**（全库 0 匹配）。实际可用的是 `require_workspace_context`（2 处使用）与 `require_authenticated_actor`（2 处）。**注意名称差异，避免接线时找不到** |
| **C.** `webhooks.py` 保持 M2M/HMAC | ✅ 已按 M2M 分类，**未改判为人类认证**。签名格式已修正为 WooCommerce 契约的 **base64 raw digest**，`webhooks.py` 与 `webhooks_generic.py` 共用 `app/core/woocommerce_security.py`（**P0-2 已解决**） |
| **D.** `healthz` / `readyz` 是否应公开 | ✅ 应公开。`health.py` 的 `healthz()` 仅返回状态字符串，`readyz` 为就绪探针，无敏感信息泄露 |
| **E.** login / register / refresh | 已单独归入 **PUBLIC**（6 条）。`auth.py` 的 JWT 实现真实有效；`b2b_portal.py` 的登录同理 |
| **F.** admin / system operations 是否有真正 admin 认证 | ❌ **几乎全部没有。** 唯一有 admin 认证的是 `auth.py` 的 4 条用户管理端点（`require_role("admin")`）。而 `system_settings.py`、`deployment.py`、`database_backup.py`、`agent_platform.py`（回滚/退役/激活版本）全部**未认证**。真正需要 admin 的操作与真正有 admin 认证的操作**几乎不重叠** |

---

## 6. 最终判断

### 问题

> 如果一个完全未经身份验证的调用方能够访问当前 backend，
> 它理论上还能执行哪些真实业务操作？

### 回答（全部基于代码事实）

**前提**：`/healthz` 与 `/readyz` 是公开端点，因此**存在一条无需任何凭据即可到达后端的路径**。
一旦网络可达，以下操作全部可执行。

#### 6.1 可完全自动执行（含触发外部系统与资金动作）

| 类别 | 可执行操作 |
|---|---|
| **伪造审批并自动执行** | `POST /feishu/card-callback` — 伪造任意 `operator` 身份批准任意 Agent 建议，并**自动触发执行**（发货/退款/改价/删除类） |
| **发布到线上商城** | `POST /products/{id}/push-woocommerce?force=true`、`POST /products/push-woocommerce` — 绕过 4/6 条闸门原因，发布到 WooCommerce |
| **写入产品主数据** | `POST /products/import`、`POST /products/batch-update` — 写入任意产品与成本字段 |
| **批准采购支出** | `POST /purchase-orders/{po_id}/approve`、`/receive`、`/partial-receive` — 批准采购单并确认收货 |
| **批准退款（资金流出）** | `POST /refunds/{refund_id}/approve` |
| **决定 Agent 审批** | `POST /approvals/{id}/approve`、`/reject` — 决定所有 Agent 审批结果 |
| **批准校准（影响后续预测）** | `POST /supply-chain-calibration/runs/{id}/approve`、`/customer-calibration/...` |
| **触发外部同步** | `POST /woocommerce-sync/sync-orders`、`/fetch-orders`、`/procurement/sync-from-wc-order`、各 `sync-inventory` |
| **修改全局系统配置** | `PUT /system-settings/`、`POST /system-settings/reset` |
| **控制 Agent 生命周期** | `POST /agent-registry/{id}/rollback`、`/retire`、`/pause`、`/resume`、`/versions/{v}/activate`、`POST /agent-queue/dead-letters/{id}/replay` |
| **数据删除** | `DELETE /feedback/{id}` 等 16 条 DELETE |

#### 6.2 可读取的敏感数据面

- **L2 内部**：全部产品成本 / 落地成本（`GET /products`、成本模型端点）、利润与毛利、定价与阶梯价
- **L3 机密**：供应商数据、采购单、合同、系统设置、密钥相关配置
- **L4 PII**：客户数据、订单、退款、结算

#### 6.3 可跨越工作区

`X-Workspace-Id` 由调用方提供且**不做归属校验**（`get_workspace_id` 仅做格式校验），
因此攻击者可以**枚举或指定任意工作区 UUID** 进行定向写入与读取。

#### 6.4 即使按 `.env` 配置了 `ACTOR_PROVIDER=header`

仍有两个绕过面：

1. **只有 3 条路径走服务层 RBAC**（`product_intelligence.py` ×2、`scraping.py` ×1），
其余 442 条 P0 全部无 RBAC 检查；
2. **`scraping.py` 在请求体不带 `actor` 时跳过全部权限检查**（L55–63）。

#### 6.5 结论

> **是的——一个完全未认证的调用方，理论上可以：伪造身份批准 Agent 建议并自动执行、
> 把商品发布到线上 WooCommerce 店铺、批准采购单与退款（产生真实资金动作）、
> 修改全局系统配置、回滚 Agent 版本、读取全部成本与 PII 数据、并定向攻击任意工作区。**
>
> 「可信闭环」的前提是「只有被验证的调用者才能触发业务动作」。
> 当前 backend 的 445 条 P0 路由使得这一前提完全不成立。

---

## 附录 A：完整路由认证覆盖矩阵（652 条）

按风险等级（P0 → P3）排序，每条含 14 个必填字段。
生成脚本：`_auth_classify.py`。

| # | Method | Path | File | Handler | Current deps | Auth mechanism | Workspace | Authz | Category | Risk | Expected scope | Recommended dep | Business impact | Test coverage | Priority |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `POST` | `/activity-planner/generate` | activity_planner.py | `generate_plan` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (25 refs to 'generate') | P0 |
| 2 | `POST` | `/activity-planner/plans/{plan_id}/approve` | activity_planner.py | `approve_activity_plan` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (3 refs to 'plans') | P0 |
| 3 | `POST` | `/activity-planner/plans/{plan_id}/optimize` | activity_planner.py | `optimize_plan` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (3 refs to 'plans') | P0 |
| 4 | `POST` | `/activity-planner/plans/{plan_id}/reject` | activity_planner.py | `reject_activity_plan` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (3 refs to 'plans') | P0 |
| 5 | `POST` | `/activity-planner/plans/{plan_id}/rewrite` | activity_planner.py | `rewrite_plan` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (3 refs to 'plans') | P0 |
| 6 | `POST` | `/agent-alerts/evaluate` | agent_operations.py | `evaluate_alerts` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (97 refs to 'evaluate') | P0 |
| 7 | `POST` | `/agent-alerts/{alert_id}/ack` | agent_operations.py | `acknowledge_alert` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (771 refs to 'ack') | P0 |
| 8 | `POST` | `/agent-alerts/{alert_id}/resolve` | agent_operations.py | `resolve_alert` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (103 refs to 'resolve') | P0 |
| 9 | `POST` | `/agent-analysis/analyze` | agent_analysis.py | `analyze_with_agent` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (28 refs to 'analyze') | P0 |
| 10 | `POST` | `/agent-analysis/analyze/batch` | agent_analysis.py | `batch_analyze` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (28 refs to 'analyze') | P0 |
| 11 | `POST` | `/agent-evaluations` | agent_runtime.py | `record_evaluation` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (4 refs to 'agent-evaluations') | P0 |
| 12 | `POST` | `/agent-executions` | agent_runtime.py | `start_execution` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (19 refs to 'agent-executions') | P0 |
| 13 | `POST` | `/agent-executions/{execution_id}/approve` | agent_runtime.py | `approve_execution` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (451 refs to 'approve') | P0 |
| 14 | `POST` | `/agent-executions/{execution_id}/complete` | agent_runtime.py | `complete_execution` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (325 refs to 'complete') | P0 |
| 15 | `POST` | `/agent-executions/{execution_id}/fail` | agent_runtime.py | `fail_execution` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (306 refs to 'fail') | P0 |
| 16 | `POST` | `/agent-executions/{execution_id}/reject` | agent_runtime.py | `reject_execution` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (222 refs to 'reject') | P0 |
| 17 | `POST` | `/agent-executions/{execution_id}/tool-calls` | agent_runtime.py | `execute_tool_call` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (10 refs to 'tool-calls') | P0 |
| 18 | `POST` | `/agent-memory` | agent_runtime.py | `store_memory` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (6 refs to 'agent-memory') | P0 |
| 19 | `POST` | `/agent-metrics/snapshot` | agent_runtime_hardening.py | `snapshot_metrics` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (111 refs to 'snapshot') | P0 |
| 20 | `POST` | `/agent-policies/budget` | agent_runtime_hardening.py | `set_budget_policy` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (61 refs to 'budget') | P0 |
| 21 | `POST` | `/agent-policies/execution` | agent_runtime_hardening.py | `set_execution_policy` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (345 refs to 'execution') | P0 |
| 22 | `GET` | `/agent-queue/dead-letters` | agent_runtime_hardening.py | `list_dead_letters` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：队列外部投递 | indirect (6 refs to 'dead-letters') | P0 |
| 23 | `POST` | `/agent-queue/dead-letters/{task_id}/replay` | agent_operations.py | `propose_dlq_replay` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：队列外部投递 | indirect (6 refs to 'dead-letters') | P0 |
| 24 | `GET` | `/agent-queue/health` | agent_runtime_hardening.py | `queue_health` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：队列外部投递 | indirect (31 refs to 'health') | P0 |
| 25 | `GET` | `/agent-queue/stats` | agent_runtime_hardening.py | `queue_stats` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：队列外部投递 | indirect (55 refs to 'stats') | P0 |
| 26 | `POST` | `/agent-registry` | agent_runtime.py | `register_agent` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (20 refs to 'agent-registry') | P0 |
| 27 | `POST` | `/agent-registry/{agent_uuid}/pause` | agent_platform.py | `pause_agent` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (16 refs to 'pause') | P0 |
| 28 | `POST` | `/agent-registry/{agent_uuid}/resume` | agent_platform.py | `resume_agent` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (7 refs to 'resume') | P0 |
| 29 | `POST` | `/agent-registry/{agent_uuid}/retire` | agent_platform.py | `retire_agent` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (24 refs to 'retire') | P0 |
| 30 | `POST` | `/agent-registry/{agent_uuid}/rollback` | agent_platform.py | `rollback_agent` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (22 refs to 'rollback') | P0 |
| 31 | `POST` | `/agent-registry/{agent_uuid}/versions` | agent_platform.py | `publish_version` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (14 refs to 'versions') | P0 |
| 32 | `POST` | `/agent-registry/{agent_uuid}/versions/{version}/activate` | agent_platform.py | `activate_version` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (14 refs to 'versions') | P0 |
| 33 | `POST` | `/agent-retry-policies` | agent_runtime_hardening.py | `set_retry_policy` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (2 refs to 'agent-retry-policies') | P0 |
| 34 | `POST` | `/agent-runtime/console-audit` | agent_platform.py | `console_audit` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：Agent 运行时外部执行 | indirect (3 refs to 'console-audit') | P0 |
| 35 | `GET` | `/agent-runtime/metrics` | agent_platform.py | `get_runtime_metrics` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：Agent 运行时外部执行 | indirect (92 refs to 'metrics') | P0 |
| 36 | `GET` | `/agent-runtime/overview` | agent_operations.py | `runtime_overview` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：Agent 运行时外部执行 | indirect (3 refs to 'overview') | P0 |
| 37 | `POST` | `/agent-suggestions/` | agent_suggestions.py | `create_suggestion` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 38 | `POST` | `/agent-suggestions/execute-pending` | agent_suggestions.py | `execute_pending` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 39 | `POST` | `/agent-suggestions/{suggestion_id}/approve` | agent_suggestions.py | `approve_suggestion` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (451 refs to 'approve') | P0 |
| 40 | `POST` | `/agent-suggestions/{suggestion_id}/execute` | agent_suggestions.py | `execute_suggestion` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (298 refs to 'execute') | P0 |
| 41 | `POST` | `/agent-suggestions/{suggestion_id}/feedback` | agent_suggestions.py | `submit_feedback` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (22 refs to 'feedback') | P0 |
| 42 | `POST` | `/agent-suggestions/{suggestion_id}/reject` | agent_suggestions.py | `reject_suggestion` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (222 refs to 'reject') | P0 |
| 43 | `POST` | `/agent-suggestions/{suggestion_id}/skip` | agent_suggestions.py | `skip_suggestion` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (57 refs to 'skip') | P0 |
| 44 | `POST` | `/agent-sweeper/run` | agent_runtime_hardening.py | `run_sweeper` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | SYSTEM | **P0** | system | require_authenticated_actor + 内网来源限制 | 低影响：非敏感读 | indirect (748 refs to 'run') | P0 |
| 45 | `POST` | `/agent-tasks` | agent_runtime.py | `create_task` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (9 refs to 'agent-tasks') | P0 |
| 46 | `POST` | `/agent-tasks/{task_id}/cancel` | agent_runtime.py | `cancel_task` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (27 refs to 'cancel') | P0 |
| 47 | `POST` | `/agent-tools` | agent_runtime.py | `register_tool` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (5 refs to 'agent-tools') | P0 |
| 48 | `PATCH` | `/agent-tools/{tool_name}` | agent_runtime.py | `update_tool` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (5 refs to 'agent-tools') | P0 |
| 49 | `GET` | `/agent-workers` | agent_runtime_hardening.py | `list_workers` | — | NONE — no dependency at all | none | none (no role / permission check) | SYSTEM | **P0** | system | require_authenticated_actor + 内网来源限制 | 外部系统影响：Worker 外部执行 | indirect (2 refs to 'agent-workers') | P0 |
| 50 | `POST` | `/agent-workers/heartbeat` | agent_runtime_hardening.py | `worker_heartbeat` | — | NONE — no dependency at all | none | none (no role / permission check) | SYSTEM | **P0** | system | require_authenticated_actor + 内网来源限制 | 外部系统影响：Worker 外部执行 | indirect (17 refs to 'heartbeat') | P0 |
| 51 | `POST` | `/agents/business-analyst/analyze` | agents_generic.py | `analyze_business` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 52 | `POST` | `/agents/customer-service-manager/analyze` | agents_generic.py | `analyze_customer_service` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | none detected | P0 |
| 53 | `POST` | `/agents/marketing-manager/analyze` | agents_generic.py | `analyze_marketing` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 54 | `POST` | `/agents/product-analyst/analyze/{product_id}` | agents.py | `analyze_product` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (7 refs to 'product-analyst') | P0 |
| 55 | `POST` | `/agents/product-analyst/pilot` | agents.py | `pilot_analysis` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (7 refs to 'product-analyst') | P0 |
| 56 | `POST` | `/agents/supply-chain-manager/analyze` | agents_generic.py | `analyze_supply_chain` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 57 | `POST` | `/ai-capability/customer-reply` | ai_capability.py | `customer_reply` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | none detected | P0 |
| 58 | `POST` | `/ai-capability/dynamic-pricing` | ai_capability.py | `dynamic_pricing` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 59 | `POST` | `/ai-capability/sourcing-model` | ai_capability.py | `sourcing_model` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：1688 / 外部 sourcing | none detected | P0 |
| 60 | `POST` | `/ai-evaluations/` | agents.py | `create_evaluation` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (1 refs to 'ai-evaluations') | P0 |
| 61 | `POST` | `/alerts/` | alerts.py | `create_alert_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (42 refs to 'alerts') | P0 |
| 62 | `POST` | `/alerts/check/all` | alerts.py | `run_all_checks_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (102 refs to 'check') | P0 |
| 63 | `POST` | `/alerts/check/margin` | alerts.py | `check_margin_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：利润与毛利数据（L2 内部） | indirect (102 refs to 'check') | P0 |
| 64 | `POST` | `/alerts/check/refund-rate` | alerts.py | `check_refund_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：退款数据（含客户 PII，L4） | indirect (102 refs to 'check') | P0 |
| 65 | `POST` | `/alerts/check/stockout` | alerts.py | `check_stockout_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (102 refs to 'check') | P0 |
| 66 | `PUT` | `/alerts/rules` | alerts.py | `update_rules` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (97 refs to 'rules') | P0 |
| 67 | `PUT` | `/alerts/{alert_id}/status` | alerts.py | `update_status_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (1164 refs to 'status') | P0 |
| 68 | `POST` | `/approval-roles` | agent_platform.py | `create_role` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (4 refs to 'approval-roles') | P0 |
| 69 | `DELETE` | `/approval-roles/{role_name}` | agent_platform.py | `delete_role` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (4 refs to 'approval-roles') | P0 |
| 70 | `POST` | `/approval-slas` | agent_platform.py | `upsert_sla` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (2 refs to 'approval-slas') | P0 |
| 71 | `POST` | `/approvals/sla-scan` | agent_platform.py | `sla_scan` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (1 refs to 'sla-scan') | P0 |
| 72 | `POST` | `/approvals/{approval_id}/approve` | agent_operations.py | `approve_approval` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (451 refs to 'approve') | P0 |
| 73 | `POST` | `/approvals/{approval_id}/reject` | agent_operations.py | `reject_approval` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (222 refs to 'reject') | P0 |
| 74 | `POST` | `/b2b-portal/applications` | b2b_portal.py | `b2b_submit_application` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 75 | `GET` | `/backup/download/{file_name}` | database_backup.py | `download_backup` | — | NONE — no dependency at all | none | none (no role / permission check) | SYSTEM | **P0** | system | require_authenticated_actor + 内网来源限制 | 外部系统影响：备份外部对象存储 | indirect (8 refs to 'download') | P0 |
| 76 | `GET` | `/backup/list` | database_backup.py | `list_backups` | — | NONE — no dependency at all | none | none (no role / permission check) | SYSTEM | **P0** | system | require_authenticated_actor + 内网来源限制 | 外部系统影响：备份外部对象存储 | indirect (217 refs to 'list') | P0 |
| 77 | `POST` | `/backup/run` | database_backup.py | `run_backup` | — | NONE — no dependency at all | none | none (no role / permission check) | SYSTEM | **P0** | system | require_authenticated_actor + 内网来源限制 | 外部系统影响：备份外部对象存储 | indirect (748 refs to 'run') | P0 |
| 78 | `GET` | `/backup/status` | database_backup.py | `backup_status` | — | NONE — no dependency at all | none | none (no role / permission check) | SYSTEM | **P0** | system | require_authenticated_actor + 内网来源限制 | 外部系统影响：备份外部对象存储 | indirect (1164 refs to 'status') | P0 |
| 79 | `POST` | `/business-recommendations` | connectors.py | `propose_recommendation` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (13 refs to 'business-recommendations') | P0 |
| 80 | `POST` | `/business-recommendations/{recommendation_id}/approve` | connectors.py | `approve_recommendation` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (451 refs to 'approve') | P0 |
| 81 | `POST` | `/business-recommendations/{recommendation_id}/reject` | connectors.py | `reject_recommendation` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (222 refs to 'reject') | P0 |
| 82 | `POST` | `/calibration/runs` | calibration.py | `create_calibration_run` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (123 refs to 'runs') | P0 |
| 83 | `POST` | `/calibration/runs/{run_id}/approve` | calibration.py | `approve_calibration_run` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (123 refs to 'runs') | P0 |
| 84 | `POST` | `/calibration/runs/{run_id}/reject` | calibration.py | `reject_calibration_run` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (123 refs to 'runs') | P0 |
| 85 | `POST` | `/campaigns` | marketing.py | `create_campaign` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (25 refs to 'campaigns') | P0 |
| 86 | `PUT` | `/campaigns/{campaign_id}` | marketing.py | `update_campaign` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (25 refs to 'campaigns') | P0 |
| 87 | `DELETE` | `/campaigns/{campaign_id}` | marketing.py | `delete_campaign` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (25 refs to 'campaigns') | P0 |
| 88 | `GET` | `/connector-runs` | connectors.py | `list_connector_runs` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：外部连接器 | indirect (2 refs to 'connector-runs') | P0 |
| 89 | `POST` | `/connectors/{connector_name}/sync` | connectors.py | `sync_connector` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：外部连接器；触发外部系统同步 | indirect (1760 refs to 'sync') | P0 |
| 90 | `POST` | `/content-marketing/content` | content_marketing.py | `create_content` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (270 refs to 'content') | P0 |
| 91 | `PUT` | `/content-marketing/content/{content_id}` | content_marketing.py | `update_content` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (270 refs to 'content') | P0 |
| 92 | `POST` | `/content-marketing/content/{content_id}/approve` | content_marketing.py | `approve_content` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (270 refs to 'content') | P0 |
| 93 | `POST` | `/content-marketing/content/{content_id}/archive` | content_marketing.py | `archive_content` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (270 refs to 'content') | P0 |
| 94 | `POST` | `/content-marketing/content/{content_id}/publish` | content_marketing.py | `publish_content` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：触发对外发布 | indirect (270 refs to 'content') | P0 |
| 95 | `POST` | `/content-marketing/content/{content_id}/reject` | content_marketing.py | `reject_content` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (270 refs to 'content') | P0 |
| 96 | `POST` | `/content-marketing/content/{content_id}/revert` | content_marketing.py | `revert_content` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (270 refs to 'content') | P0 |
| 97 | `POST` | `/content-marketing/content/{content_id}/submit` | content_marketing.py | `submit_content` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (270 refs to 'content') | P0 |
| 98 | `POST` | `/content-marketing/edm` | content_marketing.py | `create_edm` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：EDM 外发 | indirect (69 refs to 'edm') | P0 |
| 99 | `GET` | `/content-marketing/edm` | content_marketing.py | `list_edm` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：EDM 外发 | indirect (69 refs to 'edm') | P0 |
| 100 | `GET` | `/content-marketing/edm/{campaign_id}` | content_marketing.py | `get_edm` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：EDM 外发 | indirect (69 refs to 'edm') | P0 |
| 101 | `PUT` | `/content-marketing/edm/{campaign_id}` | content_marketing.py | `update_edm` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：EDM 外发 | indirect (69 refs to 'edm') | P0 |
| 102 | `POST` | `/content-marketing/edm/{campaign_id}/transition` | content_marketing.py | `transition_edm` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：EDM 外发 | indirect (69 refs to 'edm') | P0 |
| 103 | `POST` | `/content-marketing/seo` | content_marketing.py | `create_seo` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (23 refs to 'seo') | P0 |
| 104 | `PUT` | `/content-marketing/seo/{seo_id}` | content_marketing.py | `update_seo` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (23 refs to 'seo') | P0 |
| 105 | `POST` | `/content-marketing/seo/{seo_id}/ranking` | content_marketing.py | `add_seo_ranking` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (23 refs to 'seo') | P0 |
| 106 | `POST` | `/content/generate/batch` | content_generation.py | `batch_generate_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (25 refs to 'generate') | P0 |
| 107 | `POST` | `/content/generate/edm` | content_generation.py | `generate_edm_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：EDM 外发 | indirect (25 refs to 'generate') | P0 |
| 108 | `POST` | `/content/generate/selling-points` | content_generation.py | `generate_selling_points_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (25 refs to 'generate') | P0 |
| 109 | `POST` | `/content/generate/seo` | content_generation.py | `generate_seo_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (25 refs to 'generate') | P0 |
| 110 | `POST` | `/content/items/{content_id}/review` | content_generation.py | `review_content_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (98 refs to 'items') | P0 |
| 111 | `POST` | `/content/items/{content_id}/submit-review` | content_generation.py | `submit_review_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (98 refs to 'items') | P0 |
| 112 | `POST` | `/cost-model/batch-calculate` | cost_model.py | `batch_calculate_cost` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：产品成本 / 落地成本（L2 内部） | none detected | P0 |
| 113 | `POST` | `/cost-model/calculate` | cost_model.py | `calculate_cost` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：产品成本 / 落地成本（L2 内部） | indirect (9 refs to 'calculate') | P0 |
| 114 | `GET` | `/cost-model/order/{order_id}` | cost_model.py | `calculate_order_cost_db` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：产品成本 / 落地成本（L2 内部）；订单数据（含客户 PII，L4） | indirect (423 refs to 'order') | P0 |
| 115 | `GET` | `/cost-model/status` | cost_model.py | `get_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：产品成本 / 落地成本（L2 内部） | indirect (1164 refs to 'status') | P0 |
| 116 | `POST` | `/creative-analysis-runs` | marketing_learning.py | `create_creative_analysis` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (2 refs to 'creative-analysis-runs') | P0 |
| 117 | `POST` | `/creatives` | marketing.py | `create_creative` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (8 refs to 'creatives') | P0 |
| 118 | `PUT` | `/creatives/{creative_id}` | marketing.py | `update_creative` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (8 refs to 'creatives') | P0 |
| 119 | `DELETE` | `/creatives/{creative_id}` | marketing.py | `delete_creative` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (8 refs to 'creatives') | P0 |
| 120 | `POST` | `/customer-calibration/runs` | customer_learning.py | `create_calibration_run` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | indirect (123 refs to 'runs') | P0 |
| 121 | `GET` | `/customer-calibration/runs` | customer_learning.py | `list_calibration_runs` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | indirect (123 refs to 'runs') | P0 |
| 122 | `POST` | `/customer-calibration/runs/{run_id}/approve` | customer_learning.py | `approve_calibration_run` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | indirect (123 refs to 'runs') | P0 |
| 123 | `POST` | `/customer-calibration/runs/{run_id}/reject` | customer_learning.py | `reject_calibration_run` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | indirect (123 refs to 'runs') | P0 |
| 124 | `GET` | `/customer-context/{customer_id}` | customer_learning.py | `get_customer_context` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | indirect (3 refs to 'customer-context') | P0 |
| 125 | `POST` | `/customer-evaluations` | customer_learning.py | `record_customer_evaluation` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | indirect (10 refs to 'customer-evaluations') | P0 |
| 126 | `GET` | `/customer-evaluations` | customer_learning.py | `list_customer_evaluations` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | indirect (10 refs to 'customer-evaluations') | P0 |
| 127 | `POST` | `/customer-interactions` | customer.py | `create_interaction` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | indirect (7 refs to 'customer-interactions') | P0 |
| 128 | `GET` | `/customer-interactions` | customer.py | `list_interactions` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | indirect (7 refs to 'customer-interactions') | P0 |
| 129 | `GET` | `/customer-interactions/{interaction_id}` | customer.py | `get_interaction` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | indirect (7 refs to 'customer-interactions') | P0 |
| 130 | `PUT` | `/customer-interactions/{interaction_id}` | customer.py | `update_interaction` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | indirect (7 refs to 'customer-interactions') | P0 |
| 131 | `DELETE` | `/customer-interactions/{interaction_id}` | customer.py | `delete_interaction` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | indirect (7 refs to 'customer-interactions') | P0 |
| 132 | `POST` | `/customer-knowledge-entries` | customer.py | `create_knowledge_entry` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | indirect (10 refs to 'customer-knowledge-entries') | P0 |
| 133 | `GET` | `/customer-knowledge-entries` | customer.py | `list_knowledge_entries` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | indirect (10 refs to 'customer-knowledge-entries') | P0 |
| 134 | `POST` | `/customer-pattern-runs` | customer_learning.py | `run_pattern_mining` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | indirect (3 refs to 'customer-pattern-runs') | P0 |
| 135 | `GET` | `/customer-pattern-runs` | customer_learning.py | `list_pattern_runs` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | indirect (3 refs to 'customer-pattern-runs') | P0 |
| 136 | `POST` | `/customer-profiles` | customer.py | `create_profile` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | indirect (12 refs to 'customer-profiles') | P0 |
| 137 | `GET` | `/customer-profiles` | customer.py | `list_profiles` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | indirect (12 refs to 'customer-profiles') | P0 |
| 138 | `GET` | `/customer-profiles/{profile_id}` | customer.py | `get_profile` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | indirect (12 refs to 'customer-profiles') | P0 |
| 139 | `PUT` | `/customer-profiles/{profile_id}` | customer.py | `update_profile` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | indirect (12 refs to 'customer-profiles') | P0 |
| 140 | `DELETE` | `/customer-profiles/{profile_id}` | customer.py | `delete_profile` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | indirect (12 refs to 'customer-profiles') | P0 |
| 141 | `POST` | `/customer-service/chat` | customer_service.py | `chat_with_customer_service` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | indirect (17 refs to 'chat') | P0 |
| 142 | `GET` | `/customer-service/faq` | customer_service.py | `list_faq` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | none detected | P0 |
| 143 | `GET` | `/customer-service/faq/categories` | customer_service.py | `list_faq_categories` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | none detected | P0 |
| 144 | `GET` | `/customer-service/faq/search` | customer_service.py | `search_faq` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | none detected | P0 |
| 145 | `POST` | `/customer-service/human-ticket` | customer_service.py | `create_human_support_ticket` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | none detected | P0 |
| 146 | `POST` | `/dashboard/daily-metrics` | dashboard.py | `generate_daily_metrics_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 147 | `POST` | `/edm/campaigns` | edm_automation.py | `create_campaign_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：EDM 外发 | indirect (25 refs to 'campaigns') | P0 |
| 148 | `GET` | `/edm/campaigns` | edm_automation.py | `list_campaigns_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：EDM 外发 | indirect (25 refs to 'campaigns') | P0 |
| 149 | `GET` | `/edm/campaigns/{campaign_id}/stats` | edm_automation.py | `get_stats_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：EDM 外发 | indirect (25 refs to 'campaigns') | P0 |
| 150 | `PUT` | `/edm/campaigns/{campaign_id}/status` | edm_automation.py | `update_status_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：EDM 外发 | indirect (25 refs to 'campaigns') | P0 |
| 151 | `POST` | `/edm/send` | edm_automation.py | `send_email_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：EDM 外发 | indirect (81 refs to 'send') | P0 |
| 152 | `GET` | `/edm/status` | edm_automation.py | `get_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：EDM 外发 | indirect (1164 refs to 'status') | P0 |
| 153 | `POST` | `/edm/track` | edm_automation.py | `track_event_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：EDM 外发 | indirect (13 refs to 'track') | P0 |
| 154 | `GET` | `/emails/records` | emails.py | `list_email_records` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：邮件外发 | indirect (18 refs to 'records') | P0 |
| 155 | `GET` | `/emails/records/{email_id}` | emails.py | `get_email_record` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：邮件外发 | indirect (18 refs to 'records') | P0 |
| 156 | `POST` | `/emails/send-test` | emails.py | `send_test_email` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：邮件外发 | none detected | P0 |
| 157 | `GET` | `/emails/status` | emails.py | `get_email_service_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：邮件外发 | indirect (1164 refs to 'status') | P0 |
| 158 | `POST` | `/events/` | events.py | `create_event` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (208 refs to 'events') | P0 |
| 159 | `POST` | `/feedback` | marketing.py | `create_feedback` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (22 refs to 'feedback') | P0 |
| 160 | `PUT` | `/feedback/{feedback_id}` | marketing.py | `update_feedback` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (22 refs to 'feedback') | P0 |
| 161 | `DELETE` | `/feedback/{feedback_id}` | marketing.py | `delete_feedback` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (22 refs to 'feedback') | P0 |
| 162 | `GET` | `/feishu/approval-test` | feishu.py | `approval_test` | — | NONE — no signature verification in handler body | none (not even workspace resolution) | FORGED — 'operator' read from attacker-controlled JSON body | SPECIAL_AUTH | **P0** | human approver (currently anyone) | 接入飞书回调签名校验（timestamp+nonce+sign）；operator 必须来自已验证的飞书身份而非 body | 🔴 可远程伪造审批并自动执行 Agent 建议（违反 AGENTS.md §3.1） | none detected | P0 |
| 163 | `POST` | `/feishu/card-callback` | feishu.py | `feishu_card_callback` | get_db | NONE — no signature verification in handler body | none (not even workspace resolution) | FORGED — 'operator' read from attacker-controlled JSON body | SPECIAL_AUTH | **P0** | human approver (currently anyone) | 接入飞书回调签名校验（timestamp+nonce+sign）；operator 必须来自已验证的飞书身份而非 body | 🔴 可远程伪造审批并自动执行 Agent 建议（违反 AGENTS.md §3.1） | none detected | P0 |
| 164 | `GET` | `/feishu/trigger-product-test` | feishu.py | `trigger_product_test` | get_db | NONE — no signature verification in handler body | none (not even workspace resolution) | FORGED — 'operator' read from attacker-controlled JSON body | SPECIAL_AUTH | **P0** | human approver (currently anyone) | 接入飞书回调签名校验（timestamp+nonce+sign）；operator 必须来自已验证的飞书身份而非 body | 🔴 可远程伪造审批并自动执行 Agent 建议（违反 AGENTS.md §3.1） | none detected | P0 |
| 165 | `GET` | `/fulfillment/purchase-orders` | fulfillment.py | `list_purchase_orders` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4）；采购单 / 供应商商务（L3 机密）；外部系统影响：LLM 外部调用（成本） | indirect (20 refs to 'purchase-orders') | P0 |
| 166 | `GET` | `/fulfillment/purchase-orders/{po_id}` | fulfillment.py | `get_purchase_order` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4）；采购单 / 供应商商务（L3 机密）；外部系统影响：LLM 外部调用（成本） | indirect (20 refs to 'purchase-orders') | P0 |
| 167 | `PATCH` | `/fulfillment/purchase-orders/{po_id}/status` | fulfillment.py | `update_po_status` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4）；采购单 / 供应商商务（L3 机密）；外部系统影响：LLM 外部调用（成本） | indirect (20 refs to 'purchase-orders') | P0 |
| 168 | `GET` | `/fulfillment/status` | fulfillment.py | `get_fulfillment_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：LLM 外部调用（成本） | indirect (1164 refs to 'status') | P0 |
| 169 | `POST` | `/fulfillment/tracking` | fulfillment.py | `add_order_tracking` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：LLM 外部调用（成本） | indirect (13 refs to 'tracking') | P0 |
| 170 | `POST` | `/i18n-tax/i18n/convert-currency` | i18n_tax.py | `convert_currency_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 171 | `POST` | `/i18n-tax/tax/calculate` | i18n_tax.py | `calculate_tax_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (9 refs to 'tax') | P0 |
| 172 | `POST` | `/image-gen/generate` | image_gen.py | `generate_image` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：外部图像生成（成本） | indirect (25 refs to 'generate') | P0 |
| 173 | `GET` | `/image-gen/models` | image_gen.py | `list_models` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：外部图像生成（成本） | indirect (125 refs to 'models') | P0 |
| 174 | `GET` | `/image-gen/status` | image_gen.py | `get_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：外部图像生成（成本） | indirect (1164 refs to 'status') | P0 |
| 175 | `POST` | `/image-gen/tasks` | image_gen.py | `create_task` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：外部图像生成（成本） | indirect (53 refs to 'tasks') | P0 |
| 176 | `GET` | `/image-gen/tasks` | image_gen.py | `list_image_tasks` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：外部图像生成（成本） | indirect (53 refs to 'tasks') | P0 |
| 177 | `GET` | `/image-gen/tasks/{task_id}` | image_gen.py | `get_task_detail` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：外部图像生成（成本） | indirect (53 refs to 'tasks') | P0 |
| 178 | `POST` | `/image-gen/tasks/{task_id}/approve` | image_gen.py | `approve_generated_image` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：外部图像生成（成本） | indirect (53 refs to 'tasks') | P0 |
| 179 | `POST` | `/image-gen/tasks/{task_id}/execute` | image_gen.py | `execute_task` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：外部图像生成（成本） | indirect (53 refs to 'tasks') | P0 |
| 180 | `POST` | `/image-gen/tasks/{task_id}/reject` | image_gen.py | `reject_generated_image` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：外部图像生成（成本） | indirect (53 refs to 'tasks') | P0 |
| 181 | `POST` | `/influencers/` | influencer.py | `create_influencer_endpoint` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (10 refs to 'influencers') | P0 |
| 182 | `POST` | `/influencers/collaborations/{collaboration_id}/status` | influencer.py | `update_collab_status_endpoint` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (3 refs to 'collaborations') | P0 |
| 183 | `PUT` | `/influencers/{influencer_id}` | influencer.py | `update_influencer_endpoint` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (10 refs to 'influencers') | P0 |
| 184 | `DELETE` | `/influencers/{influencer_id}` | influencer.py | `delete_influencer_endpoint` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (10 refs to 'influencers') | P0 |
| 185 | `POST` | `/influencers/{influencer_id}/collaborations` | influencer.py | `create_collaboration_endpoint` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (3 refs to 'collaborations') | P0 |
| 186 | `POST` | `/inventory-snapshots` | supply_chain.py | `create_inventory` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (8 refs to 'inventory-snapshots') | P0 |
| 187 | `PUT` | `/inventory-snapshots/{inventory_id}` | supply_chain.py | `update_inventory` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (8 refs to 'inventory-snapshots') | P0 |
| 188 | `DELETE` | `/inventory-snapshots/{inventory_id}` | supply_chain.py | `delete_inventory` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (8 refs to 'inventory-snapshots') | P0 |
| 189 | `POST` | `/inventory/alerts/check` | inventory.py | `check_inventory_alerts_endpoint` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (42 refs to 'alerts') | P0 |
| 190 | `POST` | `/inventory/sync/1688` | inventory.py | `sync_1688_inventory` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：1688 外部数据；触发外部系统同步 | indirect (1760 refs to 'sync') | P0 |
| 191 | `GET` | `/inventory/sync/history` | inventory.py | `get_inventory_sync_history` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：触发外部系统同步 | indirect (1760 refs to 'sync') | P0 |
| 192 | `POST` | `/inventory/sync/woocommerce` | inventory.py | `sync_woocommerce_inventory` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：触发外部系统同步 | indirect (1760 refs to 'sync') | P0 |
| 193 | `POST` | `/inventory/warehouses` | inventory.py | `create_warehouse_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 194 | `POST` | `/inventory/warehouses/{warehouse_id}/fulfill` | inventory.py | `fulfill_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 195 | `POST` | `/inventory/warehouses/{warehouse_id}/inventory` | inventory.py | `update_inventory_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 196 | `POST` | `/inventory/warehouses/{warehouse_id}/release` | inventory.py | `release_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 197 | `POST` | `/inventory/warehouses/{warehouse_id}/replenishment` | inventory.py | `replenishment_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 198 | `POST` | `/inventory/warehouses/{warehouse_id}/reserve` | inventory.py | `reserve_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 199 | `POST` | `/knowledge-entries/` | knowledge.py | `create_knowledge_entry` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (23 refs to 'knowledge-entries') | P0 |
| 200 | `POST` | `/llm-gateway/chat` | llm_gateway.py | `chat` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：LLM 外部调用（成本） | indirect (17 refs to 'chat') | P0 |
| 201 | `POST` | `/llm-gateway/chat/simple` | llm_gateway.py | `simple_chat` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：LLM 外部调用（成本） | indirect (17 refs to 'chat') | P0 |
| 202 | `POST` | `/llm-gateway/cost/estimate` | llm_gateway.py | `estimate_call_cost` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：产品成本 / 落地成本（L2 内部）；外部系统影响：LLM 外部调用（成本） | indirect (369 refs to 'cost') | P0 |
| 203 | `GET` | `/llm-gateway/models` | llm_gateway.py | `list_models` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：LLM 外部调用（成本） | indirect (125 refs to 'models') | P0 |
| 204 | `GET` | `/llm-gateway/status` | llm_gateway.py | `get_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：LLM 外部调用（成本） | indirect (1164 refs to 'status') | P0 |
| 205 | `POST` | `/logistics-evaluations` | supply_chain_learning.py | `record_logistics_evaluation` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (6 refs to 'logistics-evaluations') | P0 |
| 206 | `POST` | `/logistics-pattern-runs` | supply_chain_learning.py | `run_logistics_pattern_mining` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (2 refs to 'logistics-pattern-runs') | P0 |
| 207 | `POST` | `/logistics/shipments` | logistics.py | `create_shipment_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (12 refs to 'shipments') | P0 |
| 208 | `POST` | `/logistics/tracking` | logistics.py | `update_tracking_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (13 refs to 'tracking') | P0 |
| 209 | `POST` | `/m5-m6/b2b/agents` | m5_m6.py | `api_create_agent` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 210 | `POST` | `/m5-m6/b2b/agents/{agent_id}/status` | m5_m6.py | `api_update_agent_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 211 | `POST` | `/m5-m6/b2b/orders` | m5_m6.py | `api_create_b2b_order` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4） | none detected | P0 |
| 212 | `POST` | `/m5-m6/b2b/orders/{order_id}/payment` | m5_m6.py | `api_record_payment` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4）；外部系统影响：支付外部调用 | none detected | P0 |
| 213 | `POST` | `/m5-m6/b2b/orders/{order_id}/status` | m5_m6.py | `api_update_b2b_order_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4） | none detected | P0 |
| 214 | `POST` | `/m5-m6/overseas-warehouse/inbound` | m5_m6.py | `api_create_inbound` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 215 | `POST` | `/m5-m6/overseas-warehouse/inbound/{inbound_id}/status` | m5_m6.py | `api_update_inbound_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 216 | `POST` | `/m5-m6/overseas-warehouse/outbound` | m5_m6.py | `api_create_outbound` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 217 | `POST` | `/m5-m6/overseas-warehouse/outbound/{outbound_id}/status` | m5_m6.py | `api_update_outbound_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 218 | `POST` | `/m5-m6/overseas-warehouse/{warehouse_id}/sync-inventory` | m5_m6.py | `api_sync_inventory` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：触发外部系统同步 | none detected | P0 |
| 219 | `POST` | `/m6-extras/customer-templates/generate` | m6_extras.py | `generate_customer_response_endpoint` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | none detected | P0 |
| 220 | `POST` | `/m6-extras/customer-templates/get` | m6_extras.py | `get_customer_template_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | none detected | P0 |
| 221 | `GET` | `/m6-extras/customer-templates/list` | m6_extras.py | `list_customer_templates` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | none detected | P0 |
| 222 | `GET` | `/m6-extras/customer-templates/status` | m6_extras.py | `customer_template_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：客户数据（PII，L4） | none detected | P0 |
| 223 | `POST` | `/m6-extras/listing-localization/batch` | m6_extras.py | `localize_listing_batch_endpoint` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 224 | `POST` | `/m6-extras/listing-localization/localize` | m6_extras.py | `localize_listing_endpoint` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 225 | `POST` | `/main-image/all-copy` | main_image.py | `api_generate_all_copy` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：外部图像生成（成本） | none detected | P0 |
| 226 | `POST` | `/main-image/checklist` | main_image.py | `api_generate_checklist` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：外部图像生成（成本） | none detected | P0 |
| 227 | `POST` | `/main-image/copy` | main_image.py | `api_generate_copy` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：外部图像生成（成本） | indirect (87 refs to 'copy') | P0 |
| 228 | `POST` | `/main-image/directions` | main_image.py | `api_generate_directions` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：外部图像生成（成本） | none detected | P0 |
| 229 | `GET` | `/main-image/directions/config` | main_image.py | `api_get_directions_config` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：外部图像生成（成本） | none detected | P0 |
| 230 | `GET` | `/main-image/selling-points/config` | main_image.py | `api_get_selling_points_config` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：外部图像生成（成本） | none detected | P0 |
| 231 | `GET` | `/main-image/status` | main_image.py | `api_get_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：外部图像生成（成本） | indirect (1164 refs to 'status') | P0 |
| 232 | `GET` | `/main-image/template` | main_image.py | `api_get_template` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：外部图像生成（成本） | indirect (60 refs to 'template') | P0 |
| 233 | `POST` | `/main-image/variants` | main_image.py | `api_generate_variants` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：外部图像生成（成本） | none detected | P0 |
| 234 | `POST` | `/main-image/workflow` | main_image.py | `api_run_workflow` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：外部图像生成（成本） | indirect (11 refs to 'workflow') | P0 |
| 235 | `POST` | `/marketing-calibration/runs` | marketing_learning.py | `create_calibration_run` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (123 refs to 'runs') | P0 |
| 236 | `POST` | `/marketing-calibration/runs/{run_id}/approve` | marketing_learning.py | `approve_calibration_run` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (123 refs to 'runs') | P0 |
| 237 | `POST` | `/marketing-calibration/runs/{run_id}/reject` | marketing_learning.py | `reject_calibration_run` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (123 refs to 'runs') | P0 |
| 238 | `POST` | `/marketing-evaluations` | marketing_learning.py | `record_campaign_evaluation` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (11 refs to 'marketing-evaluations') | P0 |
| 239 | `POST` | `/marketing-experiments` | marketing.py | `propose_experiment` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (7 refs to 'marketing-experiments') | P0 |
| 240 | `POST` | `/marketing-experiments/{experiment_id}/complete` | marketing.py | `complete_experiment` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (325 refs to 'complete') | P0 |
| 241 | `POST` | `/marketing-experiments/{experiment_id}/start` | marketing.py | `start_experiment` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (162 refs to 'start') | P0 |
| 242 | `POST` | `/marketing-knowledge-entries` | marketing_learning.py | `create_knowledge_entry` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (5 refs to 'marketing-knowledge-entries') | P0 |
| 243 | `POST` | `/memories/{memory_id}/approve` | growth_memory.py | `approve_memory` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (451 refs to 'approve') | P0 |
| 244 | `POST` | `/memories/{memory_id}/reject` | growth_memory.py | `reject_memory` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (222 refs to 'reject') | P0 |
| 245 | `POST` | `/newton/auto-inquiry/trigger` | newton_agent.py | `trigger_auto_inquiry_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 246 | `GET` | `/newton/cost/alerts` | newton_agent.py | `get_cost_alerts` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：产品成本 / 落地成本（L2 内部） | indirect (369 refs to 'cost') | P0 |
| 247 | `GET` | `/newton/cost/credits` | newton_agent.py | `get_remote_cost_credits` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：产品成本 / 落地成本（L2 内部） | indirect (369 refs to 'cost') | P0 |
| 248 | `GET` | `/newton/cost/daily` | newton_agent.py | `get_daily_cost_usage` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：产品成本 / 落地成本（L2 内部） | indirect (369 refs to 'cost') | P0 |
| 249 | `GET` | `/newton/cost/report` | newton_agent.py | `get_cost_monitor_report` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：产品成本 / 落地成本（L2 内部） | indirect (369 refs to 'cost') | P0 |
| 250 | `GET` | `/newton/cost/weekly` | newton_agent.py | `get_weekly_cost_usage` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：产品成本 / 落地成本（L2 内部） | indirect (369 refs to 'cost') | P0 |
| 251 | `POST` | `/newton/inquiry` | newton_agent.py | `create_batch_inquiry` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 252 | `POST` | `/newton/search` | newton_agent.py | `search_products` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (10 refs to 'search') | P0 |
| 253 | `GET` | `/newton/sourcing/candidates` | newton_agent.py | `get_newton_sourcing_candidates` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：1688 / 外部 sourcing | indirect (4 refs to 'sourcing') | P0 |
| 254 | `POST` | `/newton/sourcing/import` | newton_agent.py | `import_sourcing_to_candidates` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：1688 / 外部 sourcing | indirect (4 refs to 'sourcing') | P0 |
| 255 | `GET` | `/newton/sourcing/results` | newton_agent.py | `get_sourcing_results_list` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：1688 / 外部 sourcing | indirect (4 refs to 'sourcing') | P0 |
| 256 | `GET` | `/newton/sourcing/results/{sourcing_id}` | newton_agent.py | `get_sourcing_result_detail` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：1688 / 外部 sourcing | indirect (4 refs to 'sourcing') | P0 |
| 257 | `GET` | `/newton/sourcing/stats` | newton_agent.py | `get_sourcing_candidate_stats` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：1688 / 外部 sourcing | indirect (4 refs to 'sourcing') | P0 |
| 258 | `POST` | `/newton/tasks` | newton_agent.py | `create_task` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (53 refs to 'tasks') | P0 |
| 259 | `POST` | `/notifications/send-alert` | notifications.py | `send_alert` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 260 | `POST` | `/notifications/send-order` | notifications.py | `send_order` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4） | none detected | P0 |
| 261 | `POST` | `/notifications/send-text` | notifications.py | `send_text` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 262 | `POST` | `/notifications/send-weekly-report` | notifications.py | `send_weekly_report` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 263 | `POST` | `/opportunities/` | opportunity.py | `create_opportunity` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (47 refs to 'opportunities') | P0 |
| 264 | `PATCH` | `/opportunities/{opportunity_id}` | opportunity.py | `update_opportunity` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (47 refs to 'opportunities') | P0 |
| 265 | `POST` | `/opportunities/{opportunity_id}/candidates` | opportunity.py | `link_candidate` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (47 refs to 'candidates') | P0 |
| 266 | `DELETE` | `/opportunities/{opportunity_id}/candidates/{product_id}` | opportunity.py | `unlink_candidate` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (47 refs to 'candidates') | P0 |
| 267 | `GET` | `/orders/` | orders.py | `list_orders` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4） | indirect (71 refs to 'orders') | P0 |
| 268 | `POST` | `/orders/sync-woocommerce` | orders.py | `sync_woocommerce_orders` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4）；外部系统影响：触发外部系统同步 | none detected | P0 |
| 269 | `GET` | `/orders/{order_id}` | orders.py | `get_order` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4） | indirect (71 refs to 'orders') | P0 |
| 270 | `POST` | `/overseas-warehouse/inbound` | overseas_warehouse.py | `create_inbound` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 271 | `PUT` | `/overseas-warehouse/inbound/{inbound_id}/status` | overseas_warehouse.py | `update_inbound` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 272 | `POST` | `/overseas-warehouse/outbound` | overseas_warehouse.py | `create_outbound` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 273 | `PUT` | `/overseas-warehouse/outbound/{outbound_id}/status` | overseas_warehouse.py | `update_outbound` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 274 | `POST` | `/overseas-warehouse/sync-inventory` | overseas_warehouse.py | `sync_inventory_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：触发外部系统同步 | none detected | P0 |
| 275 | `POST` | `/p3/b2b/agents` | p3.py | `create_agent_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 276 | `PUT` | `/p3/b2b/agents/{agent_id}/status` | p3.py | `update_agent_status_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 277 | `POST` | `/p3/b2b/orders` | p3.py | `create_b2b_order_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4） | none detected | P0 |
| 278 | `POST` | `/p3/b2b/orders/{order_id}/payment` | p3.py | `record_payment_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4）；外部系统影响：支付外部调用 | none detected | P0 |
| 279 | `PUT` | `/p3/b2b/orders/{order_id}/status` | p3.py | `update_b2b_order_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4） | none detected | P0 |
| 280 | `POST` | `/p3/inventory/warehouses` | p3.py | `create_wh` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (23 refs to 'inventory') | P0 |
| 281 | `POST` | `/p3/inventory/warehouses/{warehouse_id}/fulfill` | p3.py | `fulfill_inv` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (23 refs to 'inventory') | P0 |
| 282 | `POST` | `/p3/inventory/warehouses/{warehouse_id}/release` | p3.py | `release_inv` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (23 refs to 'inventory') | P0 |
| 283 | `POST` | `/p3/inventory/warehouses/{warehouse_id}/replenishment` | p3.py | `replenishment` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (23 refs to 'inventory') | P0 |
| 284 | `POST` | `/p3/inventory/warehouses/{warehouse_id}/reserve` | p3.py | `reserve_inv` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (23 refs to 'inventory') | P0 |
| 285 | `POST` | `/p3/inventory/warehouses/{warehouse_id}/update` | p3.py | `update_inv` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (23 refs to 'inventory') | P0 |
| 286 | `POST` | `/p3/overseas/inbound` | p3.py | `create_inbound` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 287 | `PUT` | `/p3/overseas/inbound/{inbound_id}/status` | p3.py | `update_inbound` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 288 | `POST` | `/p3/overseas/outbound` | p3.py | `create_outbound` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 289 | `PUT` | `/p3/overseas/outbound/{outbound_id}/status` | p3.py | `update_outbound` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 290 | `POST` | `/p3/overseas/sync-inventory` | p3.py | `sync_inv` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：触发外部系统同步 | none detected | P0 |
| 291 | `GET` | `/procurement/orders` | procurement_workbench.py | `get_purchase_order_list` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4）；采购单 / 供应商商务（L3 机密） | indirect (71 refs to 'orders') | P0 |
| 292 | `GET` | `/procurement/orders/{po_id}` | procurement_workbench.py | `get_purchase_order_detail` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4）；采购单 / 供应商商务（L3 机密） | indirect (71 refs to 'orders') | P0 |
| 293 | `GET` | `/procurement/orders/{po_id}/1688-links` | procurement_workbench.py | `get_1688_links` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4）；采购单 / 供应商商务（L3 机密）；外部系统影响：1688 外部数据 | indirect (71 refs to 'orders') | P0 |
| 294 | `PUT` | `/procurement/orders/{po_id}/cancel` | procurement_workbench.py | `cancel_order` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4）；采购单 / 供应商商务（L3 机密） | indirect (71 refs to 'orders') | P0 |
| 295 | `PUT` | `/procurement/orders/{po_id}/complete` | procurement_workbench.py | `complete_order` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4）；采购单 / 供应商商务（L3 机密） | indirect (71 refs to 'orders') | P0 |
| 296 | `PUT` | `/procurement/orders/{po_id}/confirm` | procurement_workbench.py | `confirm_order` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4）；采购单 / 供应商商务（L3 机密） | indirect (71 refs to 'orders') | P0 |
| 297 | `PUT` | `/procurement/orders/{po_id}/international-tracking` | procurement_workbench.py | `add_international_tracking_info` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4）；采购单 / 供应商商务（L3 机密） | indirect (71 refs to 'orders') | P0 |
| 298 | `PUT` | `/procurement/orders/{po_id}/order` | procurement_workbench.py | `mark_as_ordered` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4）；采购单 / 供应商商务（L3 机密） | indirect (71 refs to 'orders') | P0 |
| 299 | `PUT` | `/procurement/orders/{po_id}/tracking` | procurement_workbench.py | `add_tracking_info` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4）；采购单 / 供应商商务（L3 机密） | indirect (71 refs to 'orders') | P0 |
| 300 | `GET` | `/procurement/stats` | procurement_workbench.py | `get_procurement_stats` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：采购单 / 供应商商务（L3 机密） | indirect (55 refs to 'stats') | P0 |
| 301 | `POST` | `/procurement/sync-from-wc-order` | procurement_workbench.py | `sync_from_wc_order` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4）；采购单 / 供应商商务（L3 机密）；外部系统影响：触发外部系统同步 | none detected | P0 |
| 302 | `POST` | `/product-analysis/analyze` | product_analysis.py | `api_analyze_product` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (28 refs to 'analyze') | P0 |
| 303 | `POST` | `/product-analysis/analyze-and-report` | product_analysis.py | `api_analyze_and_report` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 304 | `POST` | `/product-analysis/batch-prompts` | product_analysis.py | `api_generate_batch_prompts` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 305 | `POST` | `/product-analysis/prompt` | product_analysis.py | `api_generate_prompt` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (206 refs to 'prompt') | P0 |
| 306 | `POST` | `/product-analysis/report` | product_analysis.py | `api_generate_report` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (22 refs to 'report') | P0 |
| 307 | `POST` | `/product-candidates/{product_id}/promote` | product_intelligence.py | `promote_candidate` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (19 refs to 'promote') | P0 |
| 308 | `POST` | `/product-candidates/{product_id}/status` | product_intelligence.py | `set_candidate_status` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (1164 refs to 'status') | P0 |
| 309 | `POST` | `/product-decisions/experiments/{experiment_id}/complete` | product_intelligence.py | `complete_experiment` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (45 refs to 'experiments') | P0 |
| 310 | `POST` | `/product-decisions/experiments/{experiment_id}/start` | product_intelligence.py | `start_experiment` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (45 refs to 'experiments') | P0 |
| 311 | `POST` | `/product-decisions/{decision_id}/approve` | product_intelligence.py | `approve_decision` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (451 refs to 'approve') | P0 |
| 312 | `POST` | `/product-decisions/{decision_id}/experiment` | product_intelligence.py | `propose_decision_experiment` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (315 refs to 'experiment') | P0 |
| 313 | `POST` | `/product-decisions/{decision_id}/reject` | product_intelligence.py | `reject_decision` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (222 refs to 'reject') | P0 |
| 314 | `POST` | `/product-pipeline/confirm-list` | product_pipeline.py | `confirm_product_listing` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 315 | `POST` | `/product-pipeline/import-from-1688` | product_pipeline.py | `import_product_from_1688` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：1688 外部数据 | none detected | P0 |
| 316 | `POST` | `/product-pipeline/run` | product_pipeline.py | `run_product_pipeline` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (748 refs to 'run') | P0 |
| 317 | `POST` | `/product-reviews` | customer.py | `create_review` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (5 refs to 'product-reviews') | P0 |
| 318 | `PUT` | `/product-reviews/{review_id}` | customer.py | `update_review` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (5 refs to 'product-reviews') | P0 |
| 319 | `DELETE` | `/product-reviews/{review_id}` | customer.py | `delete_review` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (5 refs to 'product-reviews') | P0 |
| 320 | `POST` | `/products/batch-update` | product_intelligence.py | `batch_update_products` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 321 | `POST` | `/products/batch-update` | product_intelligence.py | `batch_update` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 322 | `POST` | `/products/import` | products.py | `import_products` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (771 refs to 'import') | P0 |
| 323 | `POST` | `/products/intake` | product_intelligence.py | `intake_product` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (215 refs to 'intake') | P0 |
| 324 | `POST` | `/products/intake/csv` | product_intelligence.py | `intake_candidates_csv` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (215 refs to 'intake') | P0 |
| 325 | `POST` | `/products/listing/batch` | product_listing.py | `api_batch_list` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (29 refs to 'listing') | P0 |
| 326 | `POST` | `/products/listing/queue` | product_listing.py | `api_create_queue` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：队列外部投递 | indirect (29 refs to 'listing') | P0 |
| 327 | `POST` | `/products/listing/replace-1688-data` | product_listing.py | `api_replace_1688` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：1688 外部数据 | indirect (29 refs to 'listing') | P0 |
| 328 | `POST` | `/products/listing/single` | product_listing.py | `api_single_list` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (29 refs to 'listing') | P0 |
| 329 | `GET` | `/products/procurement-suggestions` | product_intelligence.py | `get_procurement_suggestions` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：采购单 / 供应商商务（L3 机密） | none detected | P0 |
| 330 | `POST` | `/products/push-woocommerce` | products.py | `push_products_to_woocommerce` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：触发 WooCommerce 写入 | none detected | P0 |
| 331 | `POST` | `/products/sync-inventory` | product_intelligence.py | `sync_inventory` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：触发外部系统同步 | none detected | P0 |
| 332 | `POST` | `/products/sync-woocommerce` | products.py | `sync_woocommerce_products` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：触发外部系统同步 | none detected | P0 |
| 333 | `POST` | `/products/{product_id}/analyze` | product_intelligence.py | `analyze_product` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (28 refs to 'analyze') | P0 |
| 334 | `POST` | `/products/{product_id}/candidates` | product_intelligence.py | `create_sourcing_candidate` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (47 refs to 'candidates') | P0 |
| 335 | `GET` | `/products/{product_id}/cost-snapshots` | product_intelligence.py | `list_cost_snapshots` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：产品成本 / 落地成本（L2 内部） | indirect (2 refs to 'cost-snapshots') | P0 |
| 336 | `POST` | `/products/{product_id}/decisions` | product_intelligence.py | `propose_decision` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (64 refs to 'decisions') | P0 |
| 337 | `POST` | `/products/{product_id}/experiments` | product_intelligence.py | `propose_experiment` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (45 refs to 'experiments') | P0 |
| 338 | `POST` | `/products/{product_id}/generate-copy` | product_intelligence.py | `generate_product_copy` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 339 | `POST` | `/products/{product_id}/push-woocommerce` | products.py | `push_single_product_to_woocommerce` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：触发 WooCommerce 写入 | none detected | P0 |
| 340 | `POST` | `/prompts/` | prompts.py | `create_prompt` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (6 refs to 'prompts') | P0 |
| 341 | `POST` | `/purchase-automation/auto-purchase` | purchase_automation.py | `auto_purchase` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：采购单 / 供应商商务（L3 机密） | none detected | P0 |
| 342 | `POST` | `/purchase-automation/detect-anomalies` | purchase_automation.py | `detect_anomalies_endpoint` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：采购单 / 供应商商务（L3 机密） | none detected | P0 |
| 343 | `GET` | `/purchase-automation/rules` | purchase_automation.py | `get_rules` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：采购单 / 供应商商务（L3 机密） | indirect (97 refs to 'rules') | P0 |
| 344 | `PUT` | `/purchase-automation/rules` | purchase_automation.py | `update_rules` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：采购单 / 供应商商务（L3 机密） | indirect (97 refs to 'rules') | P0 |
| 345 | `GET` | `/purchase-automation/status` | purchase_automation.py | `get_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：采购单 / 供应商商务（L3 机密） | indirect (1164 refs to 'status') | P0 |
| 346 | `POST` | `/purchase-orders` | supply_chain.py | `create_purchase_order` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4）；采购单 / 供应商商务（L3 机密） | indirect (20 refs to 'purchase-orders') | P0 |
| 347 | `GET` | `/purchase-orders` | supply_chain.py | `list_purchase_orders` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4）；采购单 / 供应商商务（L3 机密） | indirect (20 refs to 'purchase-orders') | P0 |
| 348 | `POST` | `/purchase-orders` | supply_chain.py | `create_purchase_order` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4）；采购单 / 供应商商务（L3 机密） | indirect (20 refs to 'purchase-orders') | P0 |
| 349 | `GET` | `/purchase-orders/stats` | supply_chain.py | `get_purchase_order_stats` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4）；采购单 / 供应商商务（L3 机密） | indirect (55 refs to 'stats') | P0 |
| 350 | `GET` | `/purchase-orders/{po_id}` | supply_chain.py | `get_purchase_order` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4）；采购单 / 供应商商务（L3 机密） | indirect (20 refs to 'purchase-orders') | P0 |
| 351 | `PUT` | `/purchase-orders/{po_id}` | supply_chain.py | `update_purchase_order` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4）；采购单 / 供应商商务（L3 机密） | indirect (20 refs to 'purchase-orders') | P0 |
| 352 | `POST` | `/purchase-orders/{po_id}/approve` | supply_chain.py | `approve_purchase_order` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4）；采购单 / 供应商商务（L3 机密） | indirect (451 refs to 'approve') | P0 |
| 353 | `POST` | `/purchase-orders/{po_id}/cancel` | supply_chain.py | `cancel_purchase_order` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4）；采购单 / 供应商商务（L3 机密） | indirect (27 refs to 'cancel') | P0 |
| 354 | `POST` | `/purchase-orders/{po_id}/order` | supply_chain.py | `order_purchase_order` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4）；采购单 / 供应商商务（L3 机密） | indirect (423 refs to 'order') | P0 |
| 355 | `POST` | `/purchase-orders/{po_id}/partial-receive` | supply_chain.py | `partial_receive_purchase_order` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4）；采购单 / 供应商商务（L3 机密） | indirect (3 refs to 'partial-receive') | P0 |
| 356 | `POST` | `/purchase-orders/{po_id}/receive` | supply_chain.py | `receive_purchase_order` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4）；采购单 / 供应商商务（L3 机密） | indirect (55 refs to 'receive') | P0 |
| 357 | `PATCH` | `/purchase-orders/{po_id}/status` | supply_chain.py | `update_purchase_order_status` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4）；采购单 / 供应商商务（L3 机密） | indirect (1164 refs to 'status') | P0 |
| 358 | `POST` | `/refund-cases` | customer.py | `create_refund` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：退款数据（含客户 PII，L4） | indirect (6 refs to 'refund-cases') | P0 |
| 359 | `GET` | `/refund-cases` | customer.py | `list_refunds` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：退款数据（含客户 PII，L4） | indirect (6 refs to 'refund-cases') | P0 |
| 360 | `GET` | `/refund-cases/stats` | customer.py | `refund_stats` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：退款数据（含客户 PII，L4） | indirect (55 refs to 'stats') | P0 |
| 361 | `PUT` | `/refund-cases/{refund_id}` | customer.py | `update_refund` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：退款数据（含客户 PII，L4） | indirect (6 refs to 'refund-cases') | P0 |
| 362 | `DELETE` | `/refund-cases/{refund_id}` | customer.py | `delete_refund` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：退款数据（含客户 PII，L4） | indirect (6 refs to 'refund-cases') | P0 |
| 363 | `POST` | `/refunds/` | refunds.py | `create_refund` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：退款数据（含客户 PII，L4） | indirect (4 refs to 'refunds') | P0 |
| 364 | `GET` | `/refunds/` | refunds.py | `list_refunds` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：退款数据（含客户 PII，L4） | indirect (4 refs to 'refunds') | P0 |
| 365 | `GET` | `/refunds/order/{order_id}/summary` | refunds.py | `get_order_refund_summary` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4）；退款数据（含客户 PII，L4） | indirect (423 refs to 'order') | P0 |
| 366 | `GET` | `/refunds/{refund_id}` | refunds.py | `get_refund` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：退款数据（含客户 PII，L4） | indirect (4 refs to 'refunds') | P0 |
| 367 | `POST` | `/refunds/{refund_id}/approve` | refunds.py | `approve_refund` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：退款数据（含客户 PII，L4） | indirect (451 refs to 'approve') | P0 |
| 368 | `POST` | `/refunds/{refund_id}/cancel` | refunds.py | `cancel_refund` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：退款数据（含客户 PII，L4） | indirect (27 refs to 'cancel') | P0 |
| 369 | `POST` | `/refunds/{refund_id}/execute` | refunds.py | `execute_refund` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：退款数据（含客户 PII，L4） | indirect (298 refs to 'execute') | P0 |
| 370 | `POST` | `/refunds/{refund_id}/reject` | refunds.py | `reject_refund` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：退款数据（含客户 PII，L4） | indirect (222 refs to 'reject') | P0 |
| 371 | `POST` | `/refunds/{refund_id}/retry` | refunds.py | `retry_refund` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：退款数据（含客户 PII，L4） | indirect (191 refs to 'retry') | P0 |
| 372 | `POST` | `/refunds/{refund_id}/submit` | refunds.py | `submit_refund` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：退款数据（含客户 PII，L4） | indirect (10 refs to 'submit') | P0 |
| 373 | `POST` | `/rules/` | rules.py | `create_rule` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (97 refs to 'rules') | P0 |
| 374 | `POST` | `/rules/check` | rules.py | `check` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (102 refs to 'check') | P0 |
| 375 | `POST` | `/rules/evaluate` | rules.py | `evaluate` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (97 refs to 'evaluate') | P0 |
| 376 | `POST` | `/rules/override` | rules.py | `override` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (117 refs to 'override') | P0 |
| 377 | `POST` | `/rules/suggest` | rules.py | `suggest` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (21 refs to 'suggest') | P0 |
| 378 | `POST` | `/scraping/jobs` | scraping.py | `submit_scrape_job` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：外部爬取 | indirect (2 refs to 'jobs') | P0 |
| 379 | `POST` | `/selection/decisions` | selection.py | `create_decision` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (64 refs to 'decisions') | P0 |
| 380 | `POST` | `/selection/decisions/{decision_id}/approve` | selection.py | `approve_decision` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (64 refs to 'decisions') | P0 |
| 381 | `POST` | `/selection/decisions/{decision_id}/reject` | selection.py | `reject_decision` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (64 refs to 'decisions') | P0 |
| 382 | `POST` | `/seo/audit` | seo.py | `seo_audit_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (73 refs to 'audit') | P0 |
| 383 | `POST` | `/seo/keyword-strategy` | seo.py | `generate_keyword_strategy_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 384 | `POST` | `/seo/sitemap` | seo.py | `generate_sitemap_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 385 | `POST` | `/seo/structured-data/breadcrumb` | seo.py | `generate_breadcrumb_sd` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 386 | `POST` | `/seo/structured-data/faq` | seo.py | `generate_faq_sd` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 387 | `POST` | `/seo/structured-data/product` | seo.py | `generate_product_sd` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 388 | `POST` | `/settlements` | settlements.py | `register_settlement` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：回款 / 对账数据（L2） | indirect (8 refs to 'settlements') | P0 |
| 389 | `GET` | `/settlements` | settlements.py | `list_settlements` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：回款 / 对账数据（L2） | indirect (8 refs to 'settlements') | P0 |
| 390 | `GET` | `/settlements/stats` | settlements.py | `settlements_stats` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：回款 / 对账数据（L2） | indirect (55 refs to 'stats') | P0 |
| 391 | `POST` | `/settlements/{settlement_id}/dispute` | settlements.py | `mark_disputed` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：回款 / 对账数据（L2） | indirect (6 refs to 'dispute') | P0 |
| 392 | `POST` | `/settlements/{settlement_id}/receipt` | settlements.py | `record_receipt` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：回款 / 对账数据（L2） | indirect (9 refs to 'receipt') | P0 |
| 393 | `POST` | `/shipments` | supply_chain.py | `create_shipment` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (12 refs to 'shipments') | P0 |
| 394 | `PUT` | `/shipments/{shipment_id}` | supply_chain.py | `update_shipment` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (12 refs to 'shipments') | P0 |
| 395 | `DELETE` | `/shipments/{shipment_id}` | supply_chain.py | `delete_shipment` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (12 refs to 'shipments') | P0 |
| 396 | `POST` | `/shipments/{shipment_id}/events` | supply_chain.py | `add_logistics_event` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (208 refs to 'events') | P0 |
| 397 | `GET` | `/sourcing/1688/price-trend/{product_id}` | sourcing_enhanced.py | `api_1688_price_trend` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：定价 / 阶梯价（L2 内部）；外部系统影响：1688 / 外部 sourcing；1688 外部数据 | indirect (84 refs to '1688') | P0 |
| 398 | `GET` | `/sourcing/1688/product/{product_id}` | sourcing_enhanced.py | `api_1688_product_detail` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：1688 / 外部 sourcing；1688 外部数据 | indirect (84 refs to '1688') | P0 |
| 399 | `GET` | `/sourcing/1688/search` | sourcing_enhanced.py | `api_1688_search` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：1688 / 外部 sourcing；1688 外部数据 | indirect (84 refs to '1688') | P0 |
| 400 | `GET` | `/sourcing/1688/status` | sourcing_enhanced.py | `api_1688_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：1688 / 外部 sourcing；1688 外部数据 | indirect (84 refs to '1688') | P0 |
| 401 | `GET` | `/sourcing/1688/supplier/{member_id}` | sourcing_enhanced.py | `api_1688_supplier` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：供应商数据（L3 机密）；外部系统影响：1688 / 外部 sourcing；1688 外部数据 | indirect (84 refs to '1688') | P0 |
| 402 | `POST` | `/sourcing/batch-import` | sourcing.py | `batch_import` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：1688 / 外部 sourcing | none detected | P0 |
| 403 | `POST` | `/sourcing/candidates` | sourcing.py | `create_candidate` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：1688 / 外部 sourcing | indirect (47 refs to 'candidates') | P0 |
| 404 | `GET` | `/sourcing/candidates` | sourcing.py | `list_candidates` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：1688 / 外部 sourcing | indirect (47 refs to 'candidates') | P0 |
| 405 | `POST` | `/sourcing/competitors/analyze` | sourcing_enhanced.py | `api_competitor_analysis` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：1688 / 外部 sourcing | none detected | P0 |
| 406 | `POST` | `/sourcing/competitors/pricing` | sourcing_enhanced.py | `api_pricing_compare` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：1688 / 外部 sourcing | none detected | P0 |
| 407 | `POST` | `/sourcing/competitors/reviews` | sourcing_enhanced.py | `api_review_analysis` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：1688 / 外部 sourcing | none detected | P0 |
| 408 | `POST` | `/sourcing/evaluation/run` | sourcing_enhanced.py | `api_evaluation_run` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：1688 / 外部 sourcing | indirect (162 refs to 'evaluation') | P0 |
| 409 | `GET` | `/sourcing/evaluation/status` | sourcing_enhanced.py | `api_evaluation_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：1688 / 外部 sourcing | indirect (162 refs to 'evaluation') | P0 |
| 410 | `POST` | `/sourcing/experiments/auto-manage` | sourcing_enhanced.py | `api_experiment_auto_manage` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：1688 / 外部 sourcing | indirect (45 refs to 'experiments') | P0 |
| 411 | `POST` | `/sourcing/experiments/create` | sourcing_enhanced.py | `api_experiment_create` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：1688 / 外部 sourcing | indirect (45 refs to 'experiments') | P0 |
| 412 | `POST` | `/sourcing/experiments/evaluate` | sourcing_enhanced.py | `api_experiment_evaluate` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：1688 / 外部 sourcing | indirect (45 refs to 'experiments') | P0 |
| 413 | `POST` | `/sourcing/experiments/record` | sourcing_enhanced.py | `api_experiment_record` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：1688 / 外部 sourcing | indirect (45 refs to 'experiments') | P0 |
| 414 | `POST` | `/sourcing/experiments/start` | sourcing_enhanced.py | `api_experiment_start` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：1688 / 外部 sourcing | indirect (45 refs to 'experiments') | P0 |
| 415 | `GET` | `/sourcing/market-trend/analyze` | sourcing_enhanced.py | `api_market_trend` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：1688 / 外部 sourcing | none detected | P0 |
| 416 | `POST` | `/sourcing/market-trend/compare` | sourcing_enhanced.py | `api_category_compare` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：1688 / 外部 sourcing | none detected | P0 |
| 417 | `GET` | `/sourcing/market-trend/hot-keywords` | sourcing_enhanced.py | `api_hot_keywords` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：1688 / 外部 sourcing | none detected | P0 |
| 418 | `POST` | `/sourcing/quality-check` | sourcing.py | `quality_check` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：1688 / 外部 sourcing | none detected | P0 |
| 419 | `POST` | `/sourcing/score` | sourcing.py | `calculate_score` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：1688 / 外部 sourcing | indirect (104 refs to 'score') | P0 |
| 420 | `GET` | `/sourcing/status` | sourcing.py | `get_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：1688 / 外部 sourcing | indirect (1164 refs to 'status') | P0 |
| 421 | `POST` | `/supplier-evaluations` | supply_chain_learning.py | `record_supplier_evaluation` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：供应商数据（L3 机密） | indirect (9 refs to 'supplier-evaluations') | P0 |
| 422 | `GET` | `/supplier-evaluations` | supply_chain_learning.py | `list_supplier_evaluations` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：供应商数据（L3 机密） | indirect (9 refs to 'supplier-evaluations') | P0 |
| 423 | `POST` | `/supplier-pattern-runs` | supply_chain_learning.py | `run_supplier_pattern_mining` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：供应商数据（L3 机密） | indirect (4 refs to 'supplier-pattern-runs') | P0 |
| 424 | `GET` | `/supplier-pattern-runs` | supply_chain_learning.py | `list_supplier_pattern_runs` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：供应商数据（L3 机密） | indirect (4 refs to 'supplier-pattern-runs') | P0 |
| 425 | `POST` | `/supplier-profiles` | supply_chain.py | `create_supplier_profile` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：供应商数据（L3 机密） | indirect (7 refs to 'supplier-profiles') | P0 |
| 426 | `GET` | `/supplier-profiles` | supply_chain.py | `list_supplier_profiles` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：供应商数据（L3 机密） | indirect (7 refs to 'supplier-profiles') | P0 |
| 427 | `PUT` | `/supplier-profiles/{profile_id}` | supply_chain.py | `update_supplier_profile` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：供应商数据（L3 机密） | indirect (7 refs to 'supplier-profiles') | P0 |
| 428 | `DELETE` | `/supplier-profiles/{profile_id}` | supply_chain.py | `delete_supplier_profile` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：供应商数据（L3 机密） | indirect (7 refs to 'supplier-profiles') | P0 |
| 429 | `POST` | `/suppliers` | supply_chain.py | `create_supplier` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：供应商数据（L3 机密） | indirect (9 refs to 'suppliers') | P0 |
| 430 | `GET` | `/suppliers` | supply_chain.py | `list_suppliers` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：供应商数据（L3 机密） | indirect (9 refs to 'suppliers') | P0 |
| 431 | `GET` | `/suppliers/{supplier_id}` | supply_chain.py | `get_supplier` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：供应商数据（L3 机密） | indirect (9 refs to 'suppliers') | P0 |
| 432 | `PUT` | `/suppliers/{supplier_id}` | supply_chain.py | `update_supplier` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：供应商数据（L3 机密） | indirect (9 refs to 'suppliers') | P0 |
| 433 | `DELETE` | `/suppliers/{supplier_id}` | supply_chain.py | `delete_supplier` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：供应商数据（L3 机密） | indirect (9 refs to 'suppliers') | P0 |
| 434 | `POST` | `/supply-chain-calibration/runs` | supply_chain_learning.py | `create_calibration_run` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (123 refs to 'runs') | P0 |
| 435 | `POST` | `/supply-chain-calibration/runs/{run_id}/approve` | supply_chain_learning.py | `approve_calibration_run` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (123 refs to 'runs') | P0 |
| 436 | `POST` | `/supply-chain-calibration/runs/{run_id}/reject` | supply_chain_learning.py | `reject_calibration_run` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (123 refs to 'runs') | P0 |
| 437 | `POST` | `/supply-chain-knowledge-entries` | supply_chain.py | `create_knowledge_entry` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (8 refs to 'supply-chain-knowledge-entries') | P0 |
| 438 | `PUT` | `/system-settings/` | system_settings.py | `update_system_settings` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P0 |
| 439 | `POST` | `/system-settings/reset` | system_settings.py | `reset_system_settings` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (10 refs to 'reset') | P0 |
| 440 | `POST` | `/weekly-report/generate` | weekly_report.py | `generate_report_endpoint` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (25 refs to 'generate') | P0 |
| 441 | `POST` | `/woocommerce-sync/fetch-orders` | woocommerce_sync.py | `fetch_orders` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4）；外部系统影响：触发外部系统同步 | none detected | P0 |
| 442 | `GET` | `/woocommerce-sync/fetch-products` | woocommerce_sync.py | `fetch_products` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：触发外部系统同步 | none detected | P0 |
| 443 | `GET` | `/woocommerce-sync/status` | woocommerce_sync.py | `status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：触发外部系统同步 | indirect (1164 refs to 'status') | P0 |
| 444 | `POST` | `/woocommerce-sync/sync-orders` | woocommerce_sync.py | `sync_orders` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4）；外部系统影响：触发外部系统同步 | none detected | P0 |
| 445 | `POST` | `/woocommerce-sync/sync-products` | woocommerce_sync.py | `sync_products` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P0** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 外部系统影响：触发外部系统同步 | none detected | P0 |
| 446 | `GET` | `/admin/b2b/agents` | b2b_admin.py | `admin_b2b_list_agents` | get_current_user, get_db | OAuth2 JWT (get_current_user) | none | none (no role / permission check) | AUTHENTICATED_USER | **P1** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P1 |
| 447 | `POST` | `/admin/b2b/agents` | b2b_admin.py | `admin_b2b_create_agent` | get_current_user, get_db | OAuth2 JWT (get_current_user) | none | none (no role / permission check) | AUTHENTICATED_USER | **P1** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P1 |
| 448 | `GET` | `/admin/b2b/agents/{agent_id}` | b2b_admin.py | `admin_b2b_get_agent` | get_current_user, get_db | OAuth2 JWT (get_current_user) | none | none (no role / permission check) | AUTHENTICATED_USER | **P1** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P1 |
| 449 | `PUT` | `/admin/b2b/agents/{agent_id}` | b2b_admin.py | `admin_b2b_update_agent` | get_current_user, get_db | OAuth2 JWT (get_current_user) | none | none (no role / permission check) | AUTHENTICATED_USER | **P1** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P1 |
| 450 | `POST` | `/admin/b2b/agents/{agent_id}/reset-password` | b2b_admin.py | `admin_b2b_reset_password` | get_current_user, get_db | OAuth2 JWT (get_current_user) | none | none (no role / permission check) | AUTHENTICATED_USER | **P1** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：密码（L3 机密） | none detected | P1 |
| 451 | `PATCH` | `/admin/b2b/agents/{agent_id}/status` | b2b_admin.py | `admin_b2b_update_agent_status` | get_current_user, get_db | OAuth2 JWT (get_current_user) | none | none (no role / permission check) | AUTHENTICATED_USER | **P1** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P1 |
| 452 | `GET` | `/admin/b2b/orders` | b2b_admin.py | `admin_b2b_list_orders` | get_current_user, get_db | OAuth2 JWT (get_current_user) | none | none (no role / permission check) | AUTHENTICATED_USER | **P1** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4） | none detected | P1 |
| 453 | `GET` | `/admin/b2b/orders/{order_id}` | b2b_admin.py | `admin_b2b_get_order` | get_current_user, get_db | OAuth2 JWT (get_current_user) | none | none (no role / permission check) | AUTHENTICATED_USER | **P1** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4） | none detected | P1 |
| 454 | `PATCH` | `/admin/b2b/orders/{order_id}/status` | b2b_admin.py | `admin_b2b_update_order_status` | get_current_user, get_db | OAuth2 JWT (get_current_user) | none | none (no role / permission check) | AUTHENTICATED_USER | **P1** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4） | none detected | P1 |
| 455 | `GET` | `/admin/b2b/prices` | b2b_admin.py | `admin_b2b_list_prices` | get_current_user, get_db | OAuth2 JWT (get_current_user) | none | none (no role / permission check) | AUTHENTICATED_USER | **P1** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：定价 / 阶梯价（L2 内部） | none detected | P1 |
| 456 | `POST` | `/admin/b2b/prices` | b2b_admin.py | `admin_b2b_create_price` | get_current_user, get_db | OAuth2 JWT (get_current_user) | none | none (no role / permission check) | AUTHENTICATED_USER | **P1** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：定价 / 阶梯价（L2 内部） | none detected | P1 |
| 457 | `PUT` | `/admin/b2b/prices/{price_id}` | b2b_admin.py | `admin_b2b_update_price` | get_current_user, get_db | OAuth2 JWT (get_current_user) | none | none (no role / permission check) | AUTHENTICATED_USER | **P1** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：定价 / 阶梯价（L2 内部） | none detected | P1 |
| 458 | `GET` | `/admin/b2b/stats` | b2b_admin.py | `admin_b2b_stats` | get_current_user, get_db | OAuth2 JWT (get_current_user) | none | none (no role / permission check) | AUTHENTICATED_USER | **P1** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P1 |
| 459 | `GET` | `/auth/me` | auth.py | `get_me` | get_current_user | OAuth2 JWT (get_current_user) | none | none (no role / permission check) | AUTHENTICATED_USER | **P1** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (2286 refs to 'me') | P1 |
| 460 | `PUT` | `/auth/me/password` | auth.py | `change_my_password` | get_current_user, get_db | OAuth2 JWT (get_current_user) | none | none (no role / permission check) | AUTHENTICATED_USER | **P1** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：密码（L3 机密） | indirect (2286 refs to 'me') | P1 |
| 461 | `POST` | `/cache/clear` | cache.py | `clear_cache` | get_current_user | OAuth2 JWT (get_current_user) | none | none (no role / permission check) | AUTHENTICATED_USER | **P1** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (18 refs to 'clear') | P1 |
| 462 | `GET` | `/cache/keys` | cache.py | `list_cache_keys` | get_current_user | OAuth2 JWT (get_current_user) | none | none (no role / permission check) | AUTHENTICATED_USER | **P1** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (48 refs to 'keys') | P1 |
| 463 | `POST` | `/cache/reset-stats` | cache.py | `reset_cache_stats` | get_current_user | OAuth2 JWT (get_current_user) | none | none (no role / permission check) | AUTHENTICATED_USER | **P1** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P1 |
| 464 | `GET` | `/cache/stats` | cache.py | `get_cache_stats` | get_current_user | OAuth2 JWT (get_current_user) | none | none (no role / permission check) | AUTHENTICATED_USER | **P1** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (55 refs to 'stats') | P1 |
| 465 | `DELETE` | `/cache/{cache_key}` | cache.py | `delete_cache_key` | get_current_user | OAuth2 JWT (get_current_user) | none | none (no role / permission check) | AUTHENTICATED_USER | **P1** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (24 refs to 'cache') | P1 |
| 466 | `POST` | `/webhooks/woocommerce` | webhooks.py | `receive_woocommerce_order` | get_db, get_workspace_id | HMAC-SHA256 over raw body (base64 digest) | get_workspace_id (unvalidated X-Workspace-Id echo) | none (secret only; no per-topic scope) | M2M_WEBHOOK | **P1** | system | secret 缺失时 503 fail closed；只接受 base64（WooCommerce 契约）；WooCommerce 协议无 timestamp/nonce，重放由订单幂等守卫兜底 | 外部系统同步（WooCommerce）；签名错误时 401，无 secret 时 503 | covered (app.core.woocommerce_security.verify_webhook_signature -> hmac.compare_digest) | P1 |
| 467 | `POST` | `/webhooks/woocommerce-product` | webhooks.py | `receive_woocommerce_product` | get_db | HMAC-SHA256 over raw body (base64 digest) | hardcoded DEFAULT_WORKSPACE_ID | none (secret only; no per-topic scope) | M2M_WEBHOOK | **P1** | system | 与 466 同一 verifier；secret 缺失时 503 fail closed | 外部系统同步（WooCommerce）；签名错误时 401，无 secret 时 503 | covered (app.core.woocommerce_security.verify_webhook_signature -> hmac.compare_digest) | P1 |
| 468 | `GET` | `/webhooks/woocommerce/events` | webhooks_generic.py | `list_supported_events` | — | none (只读静态元数据；无 secret 参与) | none | none | M2M_WEBHOOK | **P2** | system | 无需签名：只返回事件名列表，不含业务数据 | 外部系统同步（WooCommerce） | not applicable - no secret involved | P2 |
| 469 | `POST` | `/webhooks/woocommerce/generic` | webhooks_generic.py | `receive_generic_woocommerce_webhook` | get_db | HMAC-SHA256 over raw body (base64 digest) | hardcoded DEFAULT_WORKSPACE_ID | none (secret only; no per-topic scope) | M2M_WEBHOOK | **P1** | system | 与 466 同一 verifier；**已移除 hex 兼容分支**（错误格式容忍）与打印签名/secret 的 debug 日志 | 外部系统同步（WooCommerce）；签名错误时 401，无 secret 时 503 | covered (app.core.woocommerce_security.verify_webhook_signature -> hmac.compare_digest) | P1 |
| 470 | `POST` | `/webhooks/woocommerce/test` | webhooks_generic.py | `test_webhook_endpoint` | get_db, require_role('admin') | OAuth2 JWT + require_role('admin')；生产环境不注册该路由 | hardcoded DEFAULT_WORKSPACE_ID | role='admin' check (require_role) | ADMIN | **P2** | admin | **P0 已修复**：端点移出 `api_router`，改由独立 `test_router` 承载，仅在 `not get_settings().is_production` 时挂载；生产返回 404（路由不存在），非生产必须携带已验证 JWT 且 `role=admin`。DEFAULT_WORKSPACE_ID 不再是匿名写入目标 | 测试辅助端点（非业务数据面）；生产 404，非生产需 admin JWT；正式签名 webhook 未受影响 | **VERIFIED** (`tests/test_webhook_test_endpoint_security.py` 10 例：production 路由表缺失 / production 404 / 匿名 401 且不落库 / 非法 token 401 / viewer 403 且不落库 / admin 200 并落库 / 自定义 payload 200 / 正式 webhook 仍 401 / OpenAPI 不暴露) | P2 |
| 471 | `POST` | `/auth/users` | auth.py | `create_user_admin` | get_db, require_role | OAuth2 JWT + require_role('admin') | none | role='admin' check (require_role) | ADMIN | **P2** | admin | require_authenticated_actor + require_role('admin') 或 require_permission | 敏感数据面：用户账户（L4 PII） | none detected | P2 |
| 472 | `PUT` | `/auth/users/{user_id}` | auth.py | `update_user_admin` | get_db, require_role | OAuth2 JWT + require_role('admin') | none | role='admin' check (require_role) | ADMIN | **P2** | admin | require_authenticated_actor + require_role('admin') 或 require_permission | 敏感数据面：用户账户（L4 PII） | none detected | P2 |
| 473 | `DELETE` | `/auth/users/{user_id}` | auth.py | `delete_user_admin` | get_db, require_role | OAuth2 JWT + require_role('admin') | none | role='admin' check (require_role) | ADMIN | **P2** | admin | require_authenticated_actor + require_role('admin') 或 require_permission | 敏感数据面：用户账户（L4 PII） | none detected | P2 |
| 474 | `GET` | `/b2b-portal/account/summary` | b2b_portal.py | `b2b_account_summary` | get_current_b2b_agent, get_db | B2B agent JWT (get_current_b2b_agent) | none | implicit agent principal only; no role/permission | SPECIAL_AUTH | **P2** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (10 refs to 'account') | P2 |
| 475 | `POST` | `/b2b-portal/auth/change-password` | b2b_portal.py | `b2b_change_password` | get_current_b2b_agent, get_db | B2B agent JWT (get_current_b2b_agent) | none | implicit agent principal only; no role/permission | SPECIAL_AUTH | **P2** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：密码（L3 机密） | indirect (68 refs to 'auth') | P2 |
| 476 | `GET` | `/b2b-portal/auth/me` | b2b_portal.py | `b2b_me` | get_current_b2b_agent | B2B agent JWT (get_current_b2b_agent) | none | implicit agent principal only; no role/permission | SPECIAL_AUTH | **P2** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (68 refs to 'auth') | P2 |
| 477 | `POST` | `/b2b-portal/orders` | b2b_portal.py | `b2b_create_order` | get_current_b2b_agent, get_db | B2B agent JWT (get_current_b2b_agent) | none | implicit agent principal only; no role/permission | SPECIAL_AUTH | **P2** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4） | indirect (71 refs to 'orders') | P2 |
| 478 | `GET` | `/b2b-portal/orders` | b2b_portal.py | `b2b_list_orders` | get_current_b2b_agent, get_db | B2B agent JWT (get_current_b2b_agent) | none | implicit agent principal only; no role/permission | SPECIAL_AUTH | **P2** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4） | indirect (71 refs to 'orders') | P2 |
| 479 | `GET` | `/b2b-portal/orders/{order_id}` | b2b_portal.py | `b2b_get_order` | get_current_b2b_agent, get_db | B2B agent JWT (get_current_b2b_agent) | none | implicit agent principal only; no role/permission | SPECIAL_AUTH | **P2** | workspace-scoped role | require_workspace_context + require_permission('<domain>.<action>') | 敏感数据面：订单数据（含客户 PII，L4） | indirect (71 refs to 'orders') | P2 |
| 480 | `GET` | `/b2b-portal/products` | b2b_portal.py | `b2b_list_products` | get_current_b2b_agent, get_db | B2B agent JWT (get_current_b2b_agent) | none | implicit agent principal only; no role/permission | SPECIAL_AUTH | **P2** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (86 refs to 'products') | P2 |
| 481 | `GET` | `/b2b-portal/products/{product_id}` | b2b_portal.py | `b2b_get_product` | get_current_b2b_agent, get_db | B2B agent JWT (get_current_b2b_agent) | none | implicit agent principal only; no role/permission | SPECIAL_AUTH | **P2** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (86 refs to 'products') | P2 |
| 482 | `GET` | `/activity-planner/plans` | activity_planner.py | `list_activity_plans` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (3 refs to 'plans') | P3 |
| 483 | `GET` | `/activity-planner/plans/{plan_id}` | activity_planner.py | `get_plan_detail` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (3 refs to 'plans') | P3 |
| 484 | `GET` | `/activity-planner/status` | activity_planner.py | `get_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (1164 refs to 'status') | P3 |
| 485 | `GET` | `/agent-alerts` | agent_operations.py | `list_alerts` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (3 refs to 'agent-alerts') | P3 |
| 486 | `GET` | `/agent-alerts/{alert_id}` | agent_operations.py | `get_alert` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (3 refs to 'agent-alerts') | P3 |
| 487 | `GET` | `/agent-analysis/agents` | agent_analysis.py | `list_agents` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (35 refs to 'agents') | P3 |
| 488 | `GET` | `/agent-evaluations` | agent_runtime.py | `list_evaluations` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (4 refs to 'agent-evaluations') | P3 |
| 489 | `GET` | `/agent-executions` | agent_runtime.py | `list_executions` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (19 refs to 'agent-executions') | P3 |
| 490 | `GET` | `/agent-memory` | agent_runtime.py | `search_memory` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (6 refs to 'agent-memory') | P3 |
| 491 | `GET` | `/agent-memory/knowledge-snapshot` | agent_runtime.py | `knowledge_snapshot` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (2 refs to 'knowledge-snapshot') | P3 |
| 492 | `GET` | `/agent-metrics` | agent_runtime_hardening.py | `list_metrics` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (2 refs to 'agent-metrics') | P3 |
| 493 | `GET` | `/agent-policies/budget` | agent_runtime_hardening.py | `get_budget_policy` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (61 refs to 'budget') | P3 |
| 494 | `GET` | `/agent-policies/execution` | agent_runtime_hardening.py | `get_execution_policy` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (345 refs to 'execution') | P3 |
| 495 | `GET` | `/agent-registry` | agent_runtime.py | `list_agents` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (20 refs to 'agent-registry') | P3 |
| 496 | `GET` | `/agent-registry/{agent_uuid}` | agent_runtime.py | `get_agent` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (20 refs to 'agent-registry') | P3 |
| 497 | `GET` | `/agent-registry/{agent_uuid}/prompt` | agent_runtime.py | `resolve_agent_prompt` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (206 refs to 'prompt') | P3 |
| 498 | `GET` | `/agent-registry/{agent_uuid}/versions` | agent_platform.py | `list_versions` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (14 refs to 'versions') | P3 |
| 499 | `GET` | `/agent-retry-policies` | agent_runtime_hardening.py | `get_retry_policy` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (2 refs to 'agent-retry-policies') | P3 |
| 500 | `GET` | `/agent-suggestions/` | agent_suggestions.py | `list_suggestions` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 501 | `GET` | `/agent-suggestions/feedback/stats` | agent_suggestions.py | `feedback_stats` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (22 refs to 'feedback') | P3 |
| 502 | `GET` | `/agent-suggestions/learning-summary/{agent_id}` | agent_suggestions.py | `learning_summary` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 503 | `GET` | `/agent-suggestions/pending/stats` | agent_suggestions.py | `pending_stats` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (172 refs to 'pending') | P3 |
| 504 | `GET` | `/agent-suggestions/{suggestion_id}` | agent_suggestions.py | `get_suggestion` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 505 | `GET` | `/agent-tasks` | agent_runtime.py | `list_tasks` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (9 refs to 'agent-tasks') | P3 |
| 506 | `GET` | `/agent-tasks/{task_id}` | agent_runtime.py | `get_task` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (9 refs to 'agent-tasks') | P3 |
| 507 | `GET` | `/agent-tools` | agent_runtime.py | `list_tools` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (5 refs to 'agent-tools') | P3 |
| 508 | `GET` | `/agent-traces/{trace_id}` | agent_runtime_hardening.py | `get_trace` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (2 refs to 'agent-traces') | P3 |
| 509 | `GET` | `/agents/product-analyst/roi` | agents.py | `product_analyst_roi` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (7 refs to 'product-analyst') | P3 |
| 510 | `GET` | `/agents/product-analyst/runs/{product_id}` | agents.py | `list_analysis_runs` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (7 refs to 'product-analyst') | P3 |
| 511 | `GET` | `/agents/product-analyst/scorecard` | agents.py | `product_analyst_scorecard` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (7 refs to 'product-analyst') | P3 |
| 512 | `GET` | `/ai-capability/status` | ai_capability.py | `get_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (1164 refs to 'status') | P3 |
| 513 | `GET` | `/ai-evaluations/` | agents.py | `list_evaluations` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (1 refs to 'ai-evaluations') | P3 |
| 514 | `GET` | `/alerts/` | alerts.py | `list_alerts_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (42 refs to 'alerts') | P3 |
| 515 | `GET` | `/alerts/rules` | alerts.py | `get_rules` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (97 refs to 'rules') | P3 |
| 516 | `GET` | `/alerts/status` | alerts.py | `get_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (1164 refs to 'status') | P3 |
| 517 | `GET` | `/alerts/{alert_id}` | alerts.py | `get_alert_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (42 refs to 'alerts') | P3 |
| 518 | `GET` | `/approval-roles` | agent_platform.py | `list_roles` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (4 refs to 'approval-roles') | P3 |
| 519 | `GET` | `/approval-slas` | agent_platform.py | `list_slas` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (2 refs to 'approval-slas') | P3 |
| 520 | `GET` | `/approvals` | agent_operations.py | `list_approvals` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (21 refs to 'approvals') | P3 |
| 521 | `GET` | `/approvals/{approval_id}` | agent_operations.py | `get_approval` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (21 refs to 'approvals') | P3 |
| 522 | `POST` | `/auth/login` | auth.py | `login` | get_db | NONE — no dependency at all | none | none (no role / permission check) | PUBLIC | **P3** | public | 保持公开；新增路由级拒绝清单防止误公开 | 低影响：非敏感读 | none detected | P3 |
| 523 | `POST` | `/auth/refresh` | auth.py | `refresh_token` | get_db | NONE — no dependency at all | none | none (no role / permission check) | PUBLIC | **P3** | public | 保持公开；新增路由级拒绝清单防止误公开 | 低影响：非敏感读 | indirect (51 refs to 'refresh') | P3 |
| 524 | `POST` | `/auth/register` | auth.py | `register` | get_db | NONE — no dependency at all | none | none (no role / permission check) | PUBLIC | **P3** | public | 保持公开；新增路由级拒绝清单防止误公开 | 低影响：非敏感读 | indirect (46 refs to 'register') | P3 |
| 525 | `GET` | `/auth/users` | auth.py | `get_users` | get_db, require_role | OAuth2 JWT + require_role('admin') | none | role='admin' check (require_role) | ADMIN | **P3** | admin | require_authenticated_actor + require_role('admin') 或 require_permission | 敏感数据面：用户账户（L4 PII） | none detected | P3 |
| 526 | `POST` | `/b2b-portal/auth/login` | b2b_portal.py | `b2b_login` | get_db | NONE — no dependency at all | none | none (no role / permission check) | PUBLIC | **P3** | public | 保持公开；新增路由级拒绝清单防止误公开 | 低影响：非敏感读 | indirect (68 refs to 'auth') | P3 |
| 527 | `GET` | `/business-recommendations` | connectors.py | `list_recommendations` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (13 refs to 'business-recommendations') | P3 |
| 528 | `GET` | `/calibration/confidence-report` | calibration.py | `confidence_report` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 529 | `GET` | `/calibration/runs` | calibration.py | `list_calibration_runs` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (123 refs to 'runs') | P3 |
| 530 | `GET` | `/campaigns` | marketing.py | `list_campaigns` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (25 refs to 'campaigns') | P3 |
| 531 | `GET` | `/campaigns/{campaign_id}` | marketing.py | `get_campaign` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (25 refs to 'campaigns') | P3 |
| 532 | `GET` | `/content-marketing/content` | content_marketing.py | `list_content` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (270 refs to 'content') | P3 |
| 533 | `GET` | `/content-marketing/content/{content_id}` | content_marketing.py | `get_content` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (270 refs to 'content') | P3 |
| 534 | `GET` | `/content-marketing/seo` | content_marketing.py | `list_seo` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (23 refs to 'seo') | P3 |
| 535 | `GET` | `/content-marketing/seo/{seo_id}` | content_marketing.py | `get_seo` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (23 refs to 'seo') | P3 |
| 536 | `GET` | `/content/items` | content_generation.py | `list_content_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (98 refs to 'items') | P3 |
| 537 | `GET` | `/content/status` | content_generation.py | `get_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (1164 refs to 'status') | P3 |
| 538 | `GET` | `/creative-analysis-runs` | marketing_learning.py | `list_creative_analysis_runs` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (2 refs to 'creative-analysis-runs') | P3 |
| 539 | `GET` | `/creatives` | marketing.py | `list_creatives` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (8 refs to 'creatives') | P3 |
| 540 | `GET` | `/creatives/{creative_id}` | marketing.py | `get_creative` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (8 refs to 'creatives') | P3 |
| 541 | `GET` | `/dashboard/key-metrics` | dashboard.py | `get_key_metrics` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 542 | `GET` | `/dashboard/product-performance` | dashboard.py | `get_product_performance_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 543 | `GET` | `/dashboard/status` | dashboard.py | `get_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (1164 refs to 'status') | P3 |
| 544 | `GET` | `/dashboard/summary` | dashboard.py | `get_summary` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (22 refs to 'summary') | P3 |
| 545 | `GET` | `/deployment/config/linux-systemd` | deployment.py | `linux_systemd_config` | — | NONE — no dependency at all | none | none (no role / permission check) | SYSTEM | **P3** | system | require_authenticated_actor + 内网来源限制 | 低影响：非敏感读 | indirect (109 refs to 'config') | P3 |
| 546 | `GET` | `/deployment/config/nginx` | deployment.py | `nginx_config` | — | NONE — no dependency at all | none | none (no role / permission check) | SYSTEM | **P3** | system | require_authenticated_actor + 内网来源限制 | 低影响：非敏感读 | indirect (109 refs to 'config') | P3 |
| 547 | `GET` | `/deployment/config/windows-startup` | deployment.py | `windows_startup_script` | — | NONE — no dependency at all | none | none (no role / permission check) | SYSTEM | **P3** | system | require_authenticated_actor + 内网来源限制 | 低影响：非敏感读 | indirect (109 refs to 'config') | P3 |
| 548 | `GET` | `/deployment/guide/cloud-deployment` | deployment.py | `cloud_deployment_guide` | — | NONE — no dependency at all | none | none (no role / permission check) | SYSTEM | **P3** | system | require_authenticated_actor + 内网来源限制 | 低影响：非敏感读 | none detected | P3 |
| 549 | `GET` | `/deployment/services/health` | deployment.py | `services_health` | — | NONE — no dependency at all | none | none (no role / permission check) | SYSTEM | **P3** | system | require_authenticated_actor + 内网来源限制 | 低影响：非敏感读 | indirect (108 refs to 'services') | P3 |
| 550 | `GET` | `/deployment/services/{service_name}/health` | deployment.py | `service_health` | — | NONE — no dependency at all | none | none (no role / permission check) | SYSTEM | **P3** | system | require_authenticated_actor + 内网来源限制 | 低影响：非敏感读 | indirect (108 refs to 'services') | P3 |
| 551 | `GET` | `/deployment/status` | deployment.py | `status` | — | NONE — no dependency at all | none | none (no role / permission check) | SYSTEM | **P3** | system | require_authenticated_actor + 内网来源限制 | 低影响：非敏感读 | indirect (1164 refs to 'status') | P3 |
| 552 | `GET` | `/deployment/system-info` | deployment.py | `system_info` | — | NONE — no dependency at all | none | none (no role / permission check) | SYSTEM | **P3** | system | require_authenticated_actor + 内网来源限制 | 低影响：非敏感读 | none detected | P3 |
| 553 | `GET` | `/events/` | events.py | `list_events` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (208 refs to 'events') | P3 |
| 554 | `GET` | `/feedback` | marketing.py | `list_feedback` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (22 refs to 'feedback') | P3 |
| 555 | `GET` | `/feedback/{feedback_id}` | marketing.py | `get_feedback` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (22 refs to 'feedback') | P3 |
| 556 | `GET` | `/healthz` | health.py | `healthz` | — | NONE — no dependency at all | none | none (no role / permission check) | PUBLIC | **P3** | public | 保持公开；新增路由级拒绝清单防止误公开 | 低影响：非敏感读 | indirect (2 refs to 'healthz') | P3 |
| 557 | `GET` | `/i18n-tax/i18n/currencies` | i18n_tax.py | `list_currencies` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 558 | `GET` | `/i18n-tax/i18n/languages` | i18n_tax.py | `list_languages` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 559 | `GET` | `/i18n-tax/i18n/locale/{country_code}` | i18n_tax.py | `get_country_locale` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 560 | `GET` | `/i18n-tax/i18n/status` | i18n_tax.py | `get_i18n_service_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 561 | `GET` | `/i18n-tax/tax/eu/countries` | i18n_tax.py | `get_eu_vat_rates` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (9 refs to 'tax') | P3 |
| 562 | `GET` | `/i18n-tax/tax/rates` | i18n_tax.py | `get_all_tax_rates` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (9 refs to 'tax') | P3 |
| 563 | `GET` | `/i18n-tax/tax/status` | i18n_tax.py | `get_tax_service_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (9 refs to 'tax') | P3 |
| 564 | `GET` | `/i18n-tax/tax/us/states` | i18n_tax.py | `get_us_state_tax_rates` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (9 refs to 'tax') | P3 |
| 565 | `GET` | `/identity/me` | identity.py | `whoami` | require_authenticated_actor, require_workspace_context | identity header JWT (require_authenticated_actor) | require_workspace_context (identity-bound, 403 on mismatch) | none (no role / permission check) | WORKSPACE_USER | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (2286 refs to 'me') | P3 |
| 566 | `GET` | `/influencers/` | influencer.py | `list_influencers_endpoint` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (10 refs to 'influencers') | P3 |
| 567 | `GET` | `/influencers/match` | influencer.py | `match_influencers_endpoint` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (80 refs to 'match') | P3 |
| 568 | `GET` | `/influencers/status` | influencer.py | `get_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (1164 refs to 'status') | P3 |
| 569 | `GET` | `/influencers/{influencer_id}` | influencer.py | `get_influencer_endpoint` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (10 refs to 'influencers') | P3 |
| 570 | `GET` | `/influencers/{influencer_id}/collaborations` | influencer.py | `list_collaborations_endpoint` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (3 refs to 'collaborations') | P3 |
| 571 | `GET` | `/inventory-snapshots` | supply_chain.py | `list_inventory` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (8 refs to 'inventory-snapshots') | P3 |
| 572 | `GET` | `/inventory/status` | inventory.py | `get_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (1164 refs to 'status') | P3 |
| 573 | `GET` | `/inventory/warehouses` | inventory.py | `list_warehouses_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 574 | `GET` | `/inventory/warehouses/{warehouse_id}` | inventory.py | `get_warehouse_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 575 | `GET` | `/knowledge-entries/` | knowledge.py | `list_knowledge_entries` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (23 refs to 'knowledge-entries') | P3 |
| 576 | `GET` | `/logistics-evaluations` | supply_chain_learning.py | `list_logistics_evaluations` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (6 refs to 'logistics-evaluations') | P3 |
| 577 | `GET` | `/logistics-pattern-runs` | supply_chain_learning.py | `list_logistics_pattern_runs` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (2 refs to 'logistics-pattern-runs') | P3 |
| 578 | `GET` | `/logistics/shipments` | logistics.py | `list_shipments_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (12 refs to 'shipments') | P3 |
| 579 | `GET` | `/logistics/shipments/{tracking_number}` | logistics.py | `get_shipment_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (12 refs to 'shipments') | P3 |
| 580 | `GET` | `/logistics/status` | logistics.py | `get_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (1164 refs to 'status') | P3 |
| 581 | `GET` | `/m5-m6/b2b/agents` | m5_m6.py | `api_list_agents` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 582 | `GET` | `/m5-m6/b2b/status` | m5_m6.py | `api_b2b_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 583 | `GET` | `/m5-m6/overseas-warehouse/status` | m5_m6.py | `api_warehouse_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 584 | `GET` | `/m6-extras/listing-localization/status` | m6_extras.py | `listing_localization_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 585 | `GET` | `/marketing-calibration/runs` | marketing_learning.py | `list_calibration_runs` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (123 refs to 'runs') | P3 |
| 586 | `GET` | `/marketing-context/{campaign_id}` | marketing_learning.py | `get_growth_context` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (3 refs to 'marketing-context') | P3 |
| 587 | `GET` | `/marketing-evaluations` | marketing_learning.py | `list_campaign_evaluations` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (11 refs to 'marketing-evaluations') | P3 |
| 588 | `GET` | `/marketing-experiments` | marketing.py | `list_experiments` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (7 refs to 'marketing-experiments') | P3 |
| 589 | `GET` | `/marketing-experiments/{experiment_id}` | marketing.py | `get_experiment` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (7 refs to 'marketing-experiments') | P3 |
| 590 | `GET` | `/marketing-knowledge-entries` | marketing_learning.py | `list_knowledge_entries` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (5 refs to 'marketing-knowledge-entries') | P3 |
| 591 | `GET` | `/memories` | growth_memory.py | `list_memories` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 592 | `GET` | `/memories/stats` | growth_memory.py | `memory_stats` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (55 refs to 'stats') | P3 |
| 593 | `GET` | `/newton/auto-inquiry/history` | newton_agent.py | `get_auto_inquiry_history` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 594 | `GET` | `/newton/auto-inquiry/stats` | newton_agent.py | `get_auto_inquiry_stats` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 595 | `GET` | `/newton/models` | newton_agent.py | `get_models` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (125 refs to 'models') | P3 |
| 596 | `GET` | `/newton/points` | newton_agent.py | `get_points` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (10 refs to 'points') | P3 |
| 597 | `GET` | `/newton/status` | newton_agent.py | `get_config_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (1164 refs to 'status') | P3 |
| 598 | `GET` | `/newton/tasks` | newton_agent.py | `get_task_list` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (53 refs to 'tasks') | P3 |
| 599 | `GET` | `/newton/tasks/{task_id}` | newton_agent.py | `get_task` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (53 refs to 'tasks') | P3 |
| 600 | `GET` | `/newton/tasks/{task_id}/result` | newton_agent.py | `get_task_result` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (53 refs to 'tasks') | P3 |
| 601 | `GET` | `/notifications/status` | notifications.py | `status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (1164 refs to 'status') | P3 |
| 602 | `GET` | `/operation-logs/` | operation_logs.py | `get_operation_logs` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 603 | `GET` | `/operation-logs/stats` | operation_logs.py | `get_operation_log_stats` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (55 refs to 'stats') | P3 |
| 604 | `GET` | `/opportunities/` | opportunity.py | `list_opportunities` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (47 refs to 'opportunities') | P3 |
| 605 | `GET` | `/opportunities/meta` | opportunity.py | `get_meta` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (108 refs to 'meta') | P3 |
| 606 | `GET` | `/opportunities/{opportunity_id}` | opportunity.py | `get_opportunity` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (47 refs to 'opportunities') | P3 |
| 607 | `GET` | `/opportunities/{opportunity_id}/candidates` | opportunity.py | `list_candidates` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (47 refs to 'candidates') | P3 |
| 608 | `GET` | `/overseas-warehouse/status` | overseas_warehouse.py | `get_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (1164 refs to 'status') | P3 |
| 609 | `GET` | `/p3/b2b/agents` | p3.py | `list_agents_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 610 | `GET` | `/p3/b2b/status` | p3.py | `b2b_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 611 | `GET` | `/p3/inventory/status` | p3.py | `inventory_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (23 refs to 'inventory') | P3 |
| 612 | `GET` | `/p3/inventory/warehouses` | p3.py | `list_wh` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (23 refs to 'inventory') | P3 |
| 613 | `GET` | `/p3/inventory/warehouses/{warehouse_id}` | p3.py | `get_wh` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (23 refs to 'inventory') | P3 |
| 614 | `GET` | `/p3/overseas/status` | p3.py | `overseas_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 615 | `GET` | `/product-analysis/page-types` | product_analysis.py | `api_get_page_types` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 616 | `GET` | `/product-analysis/status` | product_analysis.py | `api_get_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (1164 refs to 'status') | P3 |
| 617 | `GET` | `/product-candidates/{product_id}/drafts` | product_intelligence.py | `list_woocommerce_drafts` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (14 refs to 'drafts') | P3 |
| 618 | `GET` | `/product-decisions/experiments/{experiment_id}` | product_intelligence.py | `get_experiment` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (45 refs to 'experiments') | P3 |
| 619 | `GET` | `/product-decisions/scores/{score_id}/evidence` | product_intelligence.py | `score_evidence` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (11 refs to 'scores') | P3 |
| 620 | `GET` | `/product-pipeline/status` | product_pipeline.py | `get_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (1164 refs to 'status') | P3 |
| 621 | `GET` | `/product-pipeline/steps` | product_pipeline.py | `get_steps` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 622 | `GET` | `/product-reviews` | customer.py | `list_reviews` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (5 refs to 'product-reviews') | P3 |
| 623 | `GET` | `/products/` | products.py | `list_products` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (86 refs to 'products') | P3 |
| 624 | `GET` | `/products/listing/experiments` | product_listing.py | `api_experiment_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (29 refs to 'listing') | P3 |
| 625 | `GET` | `/products/listing/status` | product_listing.py | `api_listing_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (29 refs to 'listing') | P3 |
| 626 | `GET` | `/products/low-stock` | product_intelligence.py | `get_low_stock_products` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 627 | `GET` | `/products/low-stock` | product_intelligence.py | `get_low_stock` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 628 | `GET` | `/products/{product_id}/candidates` | product_intelligence.py | `list_sourcing_candidates` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (47 refs to 'candidates') | P3 |
| 629 | `GET` | `/products/{product_id}/experiments` | product_intelligence.py | `list_experiments` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (45 refs to 'experiments') | P3 |
| 630 | `GET` | `/products/{product_id}/intelligence` | product_intelligence.py | `get_intelligence` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (40 refs to 'intelligence') | P3 |
| 631 | `GET` | `/products/{product_id}/listing-gate` | products.py | `preview_listing_gate` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 632 | `GET` | `/products/{product_id}/sources` | product_intelligence.py | `list_sources` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (21 refs to 'sources') | P3 |
| 633 | `GET` | `/prompts/` | prompts.py | `list_prompts` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (6 refs to 'prompts') | P3 |
| 634 | `GET` | `/readyz` | health.py | `readyz` | get_db, get_redis | NONE — no dependency at all | none | none (no role / permission check) | PUBLIC | **P3** | public | 保持公开；新增路由级拒绝清单防止误公开 | 低影响：非敏感读 | indirect (2 refs to 'readyz') | P3 |
| 635 | `GET` | `/rules/` | rules.py | `list_rules` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (97 refs to 'rules') | P3 |
| 636 | `GET` | `/rules/{rule_id}` | rules.py | `get_rule` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (97 refs to 'rules') | P3 |
| 637 | `GET` | `/selection/decisions` | selection.py | `list_decisions` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (64 refs to 'decisions') | P3 |
| 638 | `GET` | `/selection/recommendations` | selection.py | `get_recommendations` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (16 refs to 'recommendations') | P3 |
| 639 | `GET` | `/selection/status` | selection.py | `get_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (1164 refs to 'status') | P3 |
| 640 | `GET` | `/seo/robots-txt` | seo.py | `generate_robots_txt_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 641 | `GET` | `/seo/status` | seo.py | `get_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (1164 refs to 'status') | P3 |
| 642 | `GET` | `/seo/structured-data/organization` | seo.py | `generate_organization_sd` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 643 | `GET` | `/shipments` | supply_chain.py | `list_shipments` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (12 refs to 'shipments') | P3 |
| 644 | `GET` | `/shipments/{shipment_id}/events` | supply_chain.py | `list_logistics_events` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (208 refs to 'events') | P3 |
| 645 | `GET` | `/supply-chain-calibration/runs` | supply_chain_learning.py | `list_calibration_runs` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (123 refs to 'runs') | P3 |
| 646 | `GET` | `/supply-chain-knowledge-entries` | supply_chain.py | `list_knowledge_entries` | get_db, get_workspace_id | NONE — get_workspace_id is a header echo, not auth | get_workspace_id (unvalidated X-Workspace-Id echo) | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (8 refs to 'supply-chain-knowledge-entries') | P3 |
| 647 | `GET` | `/system-settings/` | system_settings.py | `get_system_settings` | get_db | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 648 | `GET` | `/weekly-report/` | weekly_report.py | `list_reports_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 649 | `GET` | `/weekly-report/status` | weekly_report.py | `get_status` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | indirect (1164 refs to 'status') | P3 |
| 650 | `GET` | `/weekly-report/{report_id}` | weekly_report.py | `get_report_endpoint` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 651 | `GET` | `/weekly-report/{report_id}/action-items` | weekly_report.py | `get_report_action_items` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |
| 652 | `GET` | `/weekly-report/{report_id}/anomalies` | weekly_report.py | `get_report_anomalies` | — | NONE — no dependency at all | none | none (no role / permission check) | UNKNOWN | **P3** | workspace-scoped user | require_workspace_context + require_permission('<domain>.<action>') | 低影响：非敏感读 | none detected | P3 |

---

## 附录 B：审计工具（只读分析产物）

以下为本轮创建的分析脚本与中间产物，**未修改任何业务代码**：

| 文件 | 作用 |
|---|---|
| `backend/_auth_audit.py` | AST 解析器（含 `Annotated` 别名解析与嵌套工厂展开） |
| `backend/_auth_classify.py` | 分类器 + 风险定级 + 矩阵生成 |
| `backend/_auth_rank.py` | 严重度排序 |
| `backend/_auth_stats.py` | 交叉校验统计 |
| `backend/_auth_top20.py` | Top 20 校验 |
| `backend/_auth_routes.json` | AST 原始扫描结果（652 条） |
| `backend/_auth_matrix.md` | 附录 A 原始表 |
| `backend/_auth_summary.txt` | 统计汇总 JSON |

可复现：`python backend/_auth_audit.py && python backend/_auth_classify.py`

---

## 附录 C：边界声明

本轮为**只读差距分析**：

- ✅ 创建 `docs/AUTHENTICATION_COVERAGE_MATRIX.md`
- ✅ 创建只读分析脚本（附录 B，可删除）
- ❌ 未修改任何业务代码
- ❌ 未创建 migration
- ❌ 未修改数据库
- ❌ 未修改前端
- ❌ 未删除任何文件
- ❌ 未修改测试期望
- ❌ 未重构、未提交 Git
- ❌ 未运行 `webhooks.py` 之外的任何生产写操作
