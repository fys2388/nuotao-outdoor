# Nuotao AI OS — P0-Critical Security Remediation Report

> **文件**：`docs/audits/P0_AUTH_REMEDIATION_REPORT.md`
> **版本**：v1.0
> **阶段**：P0-Critical Security Remediation
> **基线**：`docs/AUTHENTICATION_COVERAGE_MATRIX.md`（652 路由全量 AST 审计）、
> `docs/AUTHENTICATION_POLICY.md` v1.0（策略基线）
>
> 本报告的口径是：**审计 → 分类 → 设计 → 实现 → 测试 → 复审**。
> 不隐藏失败，不重写测试期望来掩盖权限失败，不删除任何既有安全检查。

---

## 1. 范围与判定结论

### 1.1 本阶段做了

1. 建立**真实**的 authentication boundary（此前 590/652 路由分类为 `UNKNOWN`，
   即「无认证 = 不可信」）。
2. 立即封锁已确认的高危身份绕过路径（Feishu card callback、body actor 冒充、
   高危写接口匿名执行、RBAC 默认放行）。
3. 在**不新建第二套 permission system** 的前提下，把 28 条高危路由接到既有的
   `app/core/identity.py` → `app/api/deps.py` → `app/services/approval_rbac.py`
   三件套上。
4. 新增 `tests/test_auth_security.py`（18 个定向安全用例，全绿）。

### 1.2 本阶段明确没做

- **不修改测试期望来隐藏权限失败**。所有 `403/401` 期望值都是按安全语义保留的；
  失败的业务测试是通过**补齐 workspace 角色配置**修复的，而不是放宽断言。
- **不 blanket-wrap 全部 652 条路由**。本阶段目标是建立边界 + 封锁高危路径，
  不是逐条迁移。剩余 624 条仍按 `AUTHENTICATION_POLICY.md` 的 9 类
  分批治理（B0–B5）。
- **不删除 webhook authentication**。`backend/app/api/v1/endpoints/webhooks.py`
  与 `webhooks_generic.py` 本阶段**零改动**（`git status` 可验证）。
  M2M 保持为独立边界，**绝不用人类 JWT**。
- **不新增 business feature**，不新增 Agent，不自动发布、不自动采购。
- **不自动批准 / 自动执行 Agent 建议**：既有「批准后立即执行」链路被**保留**，
  但已加在签名 + RBAC + workspace 归属三重闸门之后（见 §6.3）。

---

## 2. 代码改动清单

### 2.1 新增

| 文件 | 内容 |
|---|---|
| `backend/app/core/feishu_security.py` | Feishu M2M 认证边界：签名验算、时间戳新鲜度、常量时间比较、异常类型 |
| `backend/tests/test_auth_security.py` | 18 个定向安全用例（见 §5.1） |
| `docs/AUTHENTICATION_POLICY.md` | 策略基线（4 概念 / 9 类 × 4 轴 / 10 条禁令） |
| `docs/AUTHENTICATION_COVERAGE_MATRIX.md` | 652 路由全量分类矩阵 |

### 2.2 修改

| 文件 | 关键改动 |
|---|---|
| `app/core/config.py` | 新增 `approval_rbac_fail_closed=True`、`feishu_verify_signature=True`、`feishu_encrypt_key=""`、`feishu_clock_skew_seconds=300` |
| `app/core/actor.py` | 新增 `ActorResolution(authenticated)`、`ActorAuthorizationError`、`RESERVED_ACTOR_IDS`、`resolve_identity()` / `resolve_actor()` / `resolve_authorized_actor()` |
| `app/api/deps.py` | 新增 `AuthzPrincipal`、`require_authorized_principal(permission)`、`_denial_reason()`；`require_authenticated_actor` 在 body 模式下 **401**（原 400）+ 审计事件 |
| `app/main.py` | 注册 `ActorAuthorizationError` → **401** `{"code":"ACTOR_AUTHENTICATION"}`（注册在 400 处理器之前） |
| `app/services/approval_rbac.py` | fail-closed：无 enabled role / RBAC 关闭 / 空或未知 permission 一律 DENY；`KNOWN_PERMISSIONS` 补 `product.candidate.approve/reject`、`product.experiment.approve/reject`；`check_actor_permission(..., authenticated=True)` |
| `app/models/agent_platform.py` | `APPROVAL_PERMISSIONS` 补 `agent.lifecycle.reject`（此前 AGENT_LIFECYCLE 的 reject 派生出**未知**权限，fail-closed 后必然拒绝合法拒绝操作） |
| `app/api/v1/endpoints/feishu.py` | **重写认证边界**（§3.1） |
| `app/api/v1/endpoints/{agent_operations,agent_platform,supply_chain,refunds,products,product_intelligence,scraping,system_settings}.py` | 28 条高危路由接线（§2.3） |
| `tests/conftest.py` | `auth_override` / `auth_admin` / `rbac_all_permissions` / `RBAC_TEST_ACTORS`；`_restore_runtime_settings` 增补 5 个安全开关 |
| `tests/identity_helpers.py` | 新增 `configure_header_provider()` |
| `tests/test_approval_rbac.py` | 3 个 legacy「开放模式」测试更新为 fail-closed 语义 + 新增 opt-out 变体（§5.2） |

### 2.3 真实接线的 28 条路由（AST 审计可复现）

命令：`python backend/_auth_audit.py`（DEPS 含 `require_authorized_principal`），
输出 `backend/_auth_routes.json`；**652 条路由中 28 条**命中。

| Method | Path | Permission |
|---|---|---|
| POST | `/api/v1/approvals/{approval_id}/approve` | 运行时派生（service 层） |
| POST | `/api/v1/approvals/{approval_id}/reject` | 运行时派生（service 层） |
| POST | `/api/v1/agent-registry/{agent_uuid}/rollback` | `agent.lifecycle.approve` |
| POST | `/api/v1/agent-queue/dead-letters/{task_id}/replay` | `dlq_replay.approve` |
| POST | `/api/v1/approval-roles` | 认证 + workspace（bootstrap 无静态权限，见 §6.4） |
| GET | `/api/v1/approval-roles` | 同上 |
| DELETE | `/api/v1/approval-roles/{role_name}` | 同上 |
| POST | `/api/v1/product-candidates/{product_id}/status` | 运行时派生（service 层） |
| POST | `/api/v1/product-candidates/{product_id}/promote` | 运行时派生（service 层） |
| POST | `/api/v1/products/import` | `product.manage` |
| POST | `/api/v1/products/sync-woocommerce` | `product.manage` |
| POST | `/api/v1/products/push-woocommerce` | `product.publish` |
| POST | `/api/v1/products/{product_id}/push-woocommerce` | `product.publish` |
| POST | `/api/v1/purchase-orders/{po_id}/approve` | `procurement.approve` |
| POST | `/api/v1/purchase-orders/{po_id}/order` | `procurement.order` |
| POST | `/api/v1/purchase-orders/{po_id}/partial-receive` | `procurement.receive` |
| POST | `/api/v1/purchase-orders/{po_id}/receive` | `procurement.receive` |
| POST | `/api/v1/refunds/` | `refund.create` |
| POST | `/api/v1/refunds/{refund_id}/approve` | `refund.approve` |
| POST | `/api/v1/refunds/{refund_id}/reject` | `refund.reject` |
| POST | `/api/v1/refunds/{refund_id}/cancel` | `refund.cancel` |
| POST | `/api/v1/refunds/{refund_id}/execute` | `refund.execute` |
| POST | `/api/v1/scraping/jobs` | `scraping.job.submit` |
| GET / PUT / POST | `/api/v1/system-settings/`、`/reset` | `system.admin` |
| GET | `/api/v1/feishu/approval-test` | 认证 + workspace（调试端点） |
| GET | `/api/v1/feishu/trigger-product-test` | 认证 + workspace（调试端点） |
| POST | `/api/v1/feishu/card-callback` | **签名 + 操作员 RBAC + workspace 归属**（§3.1） |

覆盖 9 个 endpoint 文件：`refunds`(5)、`agent_platform`(4)、`products`(4)、
`supply_chain`(4)、`agent_operations`(3)、`system_settings`(3)、`feishu`(2+1)、
`product_intelligence`(2)、`scraping`(1)。

---

## 3. 已封锁的高危身份绕过路径

### 3.1 P0-Critical-1：`POST /feishu/card-callback`

**改动前的攻击链**：请求体里自声明 `operator` → 直接 `approve_suggestion`
→ `asyncio.create_task` 自动执行建议。只要摸得到后端 IP，就能伪造任意操作人
批准/拒绝 Agent 建议并触发执行。

**改动后的边界**（顺序不可调换）：

```
raw body
  │
  ├─ 1. 签名校验（fail closed）
  │      feishu_verify_signature=False ────────────────► 403 签名校验未启用
  │      feishu_encrypt_key 为空 ─────────────────────► 503 未配置签名密钥
  │      timestamp / nonce / signature 任一缺失 ──────► 401
  │      nonce 长度 > 256 ────────────────────────────► 401
  │      签名不匹配（hmac.compare_digest 常量时间）────► 401
  │
  ├─ 2. 重放防护
  │      timestamp 偏离 > feishu_clock_skew_seconds ───► 403 时间戳过期
  │
  ├─ 3. 解析已验证的 body（此后 body 才可信）
  │      非 JSON / 非对象 ────────────────────────────► 400
  │
  ├─ 4. 操作员身份：只接受签名校验后的 operator.open_id
  │      operator 缺失 / 非对象 ──────────────────────► 403
  │      open_id 为空 ───────────────────────────────► 403
  │
  ├─ 5. workspace 归属（防猜 suggestion_id 越权）
  │      suggestion.workspace_id != X-Workspace-Id ───► 403 forbidden
  │
  └─ 6. RBAC（复用 approval_rbac，不新建系统）
         approve → agent.suggestion.approve
         reject  → agent.suggestion.reject
         无角色 / 缺权限 / 未知权限 ─────────────────► 403
```

- 签名失败一律返回 `{"code": 1, "msg": ...}`（HTTP 200），
  因为飞书要求回调始终返回 2xx 才不会重试风暴；**但这仍是拒绝，不是放行**。
- 密钥缺失时选择 **503** 而不是静默放行——这是「fail closed」的直接体现。
- 签名**先于** operator 解析，因此「签名伪造 + operator 伪造」这条组合路径被切断。

### 3.2 body actor / operator 不再是可信身份来源

- `actor_provider="body"` 时 `require_authenticated_actor` 返回 **401**
  （而不是旧的 400），并落 `identity.authentication_failed` 审计事件；
  它**永远不产生** `authenticated=True` 的 `ActorResolution`。
- `app/main.py` 注册 `ActorAuthorizationError` → **401**，且注册在通用
  `ActorResolutionError` 的 400 处理器**之前**，避免未认证被误报为 400。
- 高危路由不再接受 `body.actor`：统一走 `principal.identity.actor_id`。
  `app/api/v1/endpoints/scraping.py` 中旧有的 `if actor:` 判断被删除。

### 3.3 `X-Workspace-Id` 只作为路由提示

`require_workspace_context` 从**已验证的** identity 组织号解析 workspace：

- identity 无 `org` claim → 403
- 组织号无 `workspace_identity_links` 映射 → 403
- header 与映射不一致 → 403（`workspace header mismatch`）
- header 非法 UUID → 400

因此「改一个 header 换 workspace」这条路径不成立。

### 3.4 RBAC fail closed

`approval_rbac.check_approval_permission` / `check_actor_permission` 在以下情况
一律 **DENY**（而非旧的 legacy 放行）：

| 情况 | 旧行为 | 新行为 |
|---|---|---|
| 无 enabled role | 放行 | 403 `no enabled roles; refusing legacy open mode` |
| RBAC 全局关闭 | 放行 | 403 `RBAC is disabled globally` |
| 空 / 未知 permission | 放行 | 403 `unknown permission '...'` |
| 非认证 actor | 放行 | 403 `not authenticated` |

---

## 4. Legacy 逃生舱（未删除，改为显式 opt-out）

| 开关 | 默认 | 效果 |
|---|---|---|
| `approval_rbac_fail_closed` | `True` | `False` 时恢复「无角色 → 放行」并打 WARNING 日志 |
| `feishu_verify_signature` | `True` | `False` 时回调返回 403 拒绝（不是放行） |
| `feishu_encrypt_key` | `""` | 空 + 验签开启 → 503（fail closed） |
| `feishu_clock_skew_seconds` | `300` | 重放窗口 |

设计取舍：逃生舱**只能让系统拒绝得更多**，不能把它调成「更宽松」
（`feishu_verify_signature=False` 不是「关闭校验然后放行」，而是「直接 403」）。
这是刻意的——保留配置开关但去掉「宽松」方向，避免误配置静默打开后门。

---

## 5. 测试证据

### 5.1 新增 `tests/test_auth_security.py`（18 passed）

| # | 用例 | 期望 | 结果 |
|---|---|---|---|
| 1 | `test_feishu_callback_without_signature_is_denied` | 拒绝 + 建议状态不变 | ✅ |
| 2 | `test_feishu_callback_with_forged_signature_is_denied` | 拒绝 + 建议状态不变 | ✅ |
| 3 | `test_feishu_callback_denied_when_encrypt_key_missing` | 503 fail closed | ✅ |
| 4 | `test_feishu_callback_replay_with_stale_timestamp_is_denied` | 403 重放拒绝 + 建议状态不变 | ✅ |
| 5 | `test_feishu_verified_operator_without_permission_is_denied` | 403 RBAC + 建议状态不变 | ✅ |
| 6 | `test_feishu_verified_operator_with_permission_is_allowed` | 200 成功 + 建议 approved | ✅ |
| 7 | `test_feishu_cross_workspace_target_is_denied` | 403 workspace 越权 + 状态不变 | ✅ |
| 8 | `test_feishu_callback_without_operator_identity_is_denied` | 403 无 operator + 状态不变 | ✅ |
| 9 | `test_feishu_debug_endpoint_requires_authenticated_principal` | 401 | ✅ |
| 10 | `test_forged_body_actor_is_rejected_at_authentication` | 401（伪造 JWT 未被解析） | ✅ |
| 11 | `test_x_actor_header_is_never_accepted` | 401 | ✅ |
| 12 | `test_workspace_header_mismatch_is_denied` | 403 | ✅ |
| 13 | `test_identity_without_workspace_mapping_is_denied` | 403 | ✅ |
| 14 | `test_rbac_denies_when_no_role_is_configured` | 403 无 enabled role | ✅ |
| 15 | `test_rbac_denies_when_permission_is_missing` | 403 缺权限 | ✅ |
| 16 | `test_rbac_denies_unknown_permission` | 403 未知权限 | ✅ |
| 17 | `test_rbac_allows_configured_actor` | 200 正例 | ✅ |
| 18 | `test_legacy_open_mode_requires_explicit_opt_out` | True→403 / False→200 | ✅ |

所有 RBAC / workspace 用例走**真实**认证链（`actor_provider="header"` + 临时
RS256 密钥对 + 预载 JWKS），不覆盖 `require_authenticated_actor` 依赖。

### 5.2 `tests/test_approval_rbac.py` 的契约变更（诚实记录）

| 旧测试名 | 旧断言 | 新状态 |
|---|---|---|
| `test_no_roles_legacy_open_mode` | 无角色 → 放行 | 删除，由 `test_no_roles_denies_fail_closed` 取代（断言 `ApprovalRBACError`） |
| `test_rbac_disabled_global_allow` | 全局关闭 → 放行 | 删除，由 `test_rbac_disabled_denies_fail_closed` 取代 |
| `test_disabled_role_ignored` | 禁用角色 → 放行 | 删除，由 `test_disabled_role_denies_fail_closed` 取代 |
| — | — | 新增 `*_legacy_open_allowed` opt-out 变体：`fail_closed=False` 时恢复旧行为 |

**这不是「改测试期望来隐藏失败」**：旧断言本身就是安全漏洞的固化；
新的断言与 §3.4 的策略一致，而旧行为被保留为显式 opt-out 并被单独测试。

### 5.3 全量测试结果

```
python -m pytest tests/ --ignore=tests/integration
774 passed, 10 failed in 240.68s
```

**基线保护**：`tests/test_listing_gate.py`(40) + `tests/test_opportunity_domain.py`(34)
= 74 个用例**全部通过**，未被本阶段改动影响。

**新增 / 更新的安全测试文件全部通过**：
`test_auth_security.py`(18)、`test_approval_rbac.py`、`test_actor_provider.py`、
`test_identity_api.py`、`test_product_candidate_m513.py`、`test_product_import.py`、
`test_supply_chain.py`、`test_agent_operations.py`、`test_runtime_platform_api.py`、
`test_agent_lifecycle.py`、`test_scraping_m516.py`、`test_product_analyst_pilot.py`、
`test_product_analyst_validation.py`、`test_product_intelligence.py`。

### 5.4 剩余 10 个失败：**既有问题，本阶段不动**

| 文件 | 用例数 | 根因 |
|---|---|---|
| `tests/test_order_queries.py` | 5 | WooCommerce webhook 签名格式 |
| `tests/test_webhook_orders.py` | 4 | 同上 |
| `tests/test_intelligence_completeness.py` | 1 | 同上 |

`webhooks.py` 只接受 **hex** 签名字符串，而 WooCommerce 的原生契约
（以及测试、以及已修正的 `webhooks_generic.py`）使用 **base64**。
本阶段**明确不修改** `webhooks.py`：

1. 「不能删除 webhook authentication」是阶段禁令；
2. M2M 是独立边界，不能用人类 JWT 替代，也不应与 Feishu 边界混用；
3. 该问题在本阶段开始之前就已存在，与本阶段的认证边界改动无关。

修复方式（下一批）：让 `webhooks.py` 同时接受 hex 与 base64，
与 `webhooks_generic.py` 保持一致。预计 4 行改动 + 0 个新增依赖。

---

## 6. 复审清单：未新增安全绕过

| # | 检查项 | 结论 |
|---|---|---|
| 6.1 | 是否有任何路由把 body actor 当作**唯一**可信身份来源 | 否。高危路由统一走 `principal.identity.actor_id`；body actor 只在未接线路由中作为**审计归因**保留 |
| 6.2 | 是否有任何新增的默认放行（default-allow） | 否。fail-closed 是默认；`approval_rbac_fail_closed=False` 需显式 opt-out 并打 WARNING |
| 6.3 | 是否新增自动批准 / 自动执行 | 否。**保留**的既有链路（Feishu 批准后 `asyncio.create_task` 执行建议）现在被签名 + 操作员 RBAC + workspace 归属三重闸门保护；未新增任何新的自动执行入口 |
| 6.4 | RBAC 角色 CRUD 是否需要 `role.manage` 权限 | **需要后续处理**，见 §7 R2。当前策略是「认证 + workspace membership」而非静态 `role.manage` 权限——这是刻意的 bootstrap 权衡：workspace 还没有任何角色时，若同时要求 `role.manage`，将形成「没有角色 → 无法通过 RBAC → 无法创建第一个角色」的死锁 |
| 6.5 | 是否新增绕过 workspace 归属判断的路径 | 否。所有新增路由使用 `principal.workspace_id`，从不读取 `X-Workspace-Id` 作为数据归属依据 |
| 6.6 | 是否放宽了任何既有安全检查 | 否。唯一行为变化是 body 模式下 400 → 401（语义更准确：无认证 ≠ 请求格式错误），以及 fail-closed 收紧 |
| 6.7 | 是否修改测试期望来掩盖权限失败 | 否。§5.2 记录了 3 个 legacy 断言的替换，且旧行为以 opt-out 变体保留并被单独测试 |
| 6.8 | 是否删除了任何安全检查 | 否。webhook 认证零改动（`git status` 可验证） |

---

## 7. 后续建议（明确标注，不阻塞本阶段）

| ID | 建议 | 理由 / 预计成本 |
|---|---|---|
| **R1** | 给 Feishu 回调补 `event_log` 审计事件（`feishu.callback.signature_rejected` / `feishu.callback.replay_rejected`），目前只写结构化日志 | 策略文档 §7 已定义事件类型；当前实现落在日志层，无法用 `event_log` 统一检索与告警。预计 20 行 + 2 个测试 |
| **R2** | 给 `approval-roles` 增加 `role.manage` 权限，并解决 bootstrap 死锁 | 当前是 bootstrap 权衡（§6.4）。建议做法：保留「无角色时认证即放行」的窄口子 + 一旦存在任何角色就要求 `role.manage`。预计 30 行 + 3 个测试 |
| **R3** | ~~让 `webhooks.py` 同时接受 hex 与 base64 签名~~ → **已解决**，但方向相反 | §9 Commerce Integrity 阶段：未做「双格式兼容」，而是修正为 WooCommerce 契约的 **base64-only**（hex 不是合法格式，兼容反而扩大攻击面），并抽出共享 `app/core/woocommerce_security.py`；§5.4 的 10 个既有失败已清零，全量 814/814 |
| **R4** | 把 Feishu「批准后立即执行」拆成独立的人工执行步骤 | 保留签名 + RBAC 闸门后风险已受控，但「一次点击 = 批准 + 执行」仍然是最大的单点影响面。建议在引入真正的执行队列后再拆 |
| **R5** | 完成剩余 624 条路由的分批迁移（B0–B5） | 本阶段刻意不做；策略文档已给出批次与验收标准 |
| **R6** | 给 `product_intelligence.py` 的 `/product-decisions/*` 与 `/experiments/*` 路由接 `require_authorized_principal` | 当前只靠 service 层 RBAC；建议把认证 + workspace 也上移到路由层，与其他高危路由一致 |

---

## 8. 变更文件清单（本阶段）

**新增**
- `backend/app/core/feishu_security.py`
- `backend/tests/test_auth_security.py`
- `docs/AUTHENTICATION_POLICY.md`
- `docs/AUTHENTICATION_COVERAGE_MATRIX.md`
- `docs/audits/P0_AUTH_REMEDIATION_REPORT.md`（本文件）

**修改**
- `backend/app/core/config.py`
- `backend/app/core/actor.py`
- `backend/app/api/deps.py`
- `backend/app/main.py`
- `backend/app/services/approval_rbac.py`
- `backend/app/models/agent_platform.py`
- `backend/app/api/v1/endpoints/feishu.py`
- `backend/app/api/v1/endpoints/agent_operations.py`
- `backend/app/api/v1/endpoints/agent_platform.py`
- `backend/app/api/v1/endpoints/supply_chain.py`
- `backend/app/api/v1/endpoints/refunds.py`
- `backend/app/api/v1/endpoints/products.py`
- `backend/app/api/v1/endpoints/product_intelligence.py`
- `backend/app/api/v1/endpoints/scraping.py`
- `backend/app/api/v1/endpoints/system_settings.py`
- `backend/tests/conftest.py`
- `backend/tests/identity_helpers.py`
- `backend/tests/test_approval_rbac.py`
- `backend/tests/test_actor_provider.py`
- `backend/tests/test_agent_lifecycle.py`
- `backend/tests/test_agent_operations.py`
- `backend/tests/test_product_analyst_pilot.py`
- `backend/tests/test_product_analyst_validation.py`
- `backend/tests/test_product_candidate_m513.py`
- `backend/tests/test_product_import.py`
- `backend/tests/test_product_intelligence.py`
- `backend/tests/test_runtime_platform_api.py`
- `backend/tests/test_scraping_m516.py`
- `backend/tests/test_supply_chain.py`

**明确未改动**：`backend/app/api/v1/endpoints/webhooks.py`、
`backend/app/api/v1/endpoints/webhooks_generic.py`。（注：这两个文件已在后续
**Commerce Integrity** 阶段被修改，见 §9。）

---

## 9. 后续阶段：Commerce Integrity（WooCommerce 签名修复）

本报告的 §5.4 / §7-R3 在 Commerce Integrity 阶段已被关闭。摘要：

| 项 | 内容 |
|---|---|
| 根因 | `webhooks.py` 用 `hexdigest()`（64 字符），WooCommerce 契约是 `base64(HMAC-SHA256)`（44 字符）。同一 body + 同一 secret 下两者永不相等，`compare_digest` 恒 False → 100% 401，订单回流链路断裂 |
| 修改 | 新增 `backend/app/core/woocommerce_security.py`（base64 raw digest、常量时间比较、secret 缺失时 503 fail closed、禁止打印 secret/签名）；`webhooks.py` 与 `webhooks_generic.py` 改为共用该 verifier |
| 顺带修掉 | `webhooks_generic.py` 原本接受 hex+base64 双格式（错误格式容忍）并有一条 `logger.debug` 会打印签名与 secret 片段 → 双格式容忍已移除，debug 日志已删除 |
| 未采用 | 「hex 与 base64 双格式兼容」。hex 不是 WooCommerce 合法格式，兼容 = 扩大攻击面 |
| 测试 | 新增 `backend/tests/test_woocommerce_signature.py`（30 个用例，含独立参考实现、base64/hex/缺 secret/改 body/改签名/重放幂等/全链路） |
| 结果 | `pytest tests --ignore=tests/integration`：**collected 814 / passed 814 / failed 0 / errors 0 / skipped 0 / xfailed 0**（修复前 774 passed / 10 failed） |
| 基线 | `test_listing_gate` 40 + `test_opportunity_domain` 34 全部保持绿；`test_auth_security` 18 全绿 |
| 剩余风险 | ① ~~`POST /webhooks/woocommerce/test` 无签名校验且已注册进 `api_router`~~ → **已在 §10 关闭**（P0-OPEN → P2，生产 404 + 非生产 admin JWT）；② `woocommerce_webhook_secret` 仍有源码默认值 `dev-webhook-secret-change-me`（凭据轮换属下一批，本阶段刻意未动） |

---

## 10. 后续阶段：Webhook Test Endpoint Exposure 修复（2026-09-22）

关闭 §9「剩余风险 ①」：`POST /webhooks/woocommerce/test` 是无签名校验且无条件挂载的
生产可达写入口。

| 项 | 内容 |
|---|---|
| 端点 | `backend/app/api/v1/endpoints/webhooks_generic.py` :: `test_webhook_endpoint` |
| 原始缺陷 | `@router.post("/woocommerce/test")` 挂在全局 `router`（prefix `/webhooks`）上，经 `api/v1/router.py` **无条件** `include_router` 注册。依赖只有 `(request, db)`：无签名校验、无认证、无授权，handler 内以硬编码 `DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"` 写入 `process_webhook_event`。docstring 自述「此端点不验证签名，仅用于本地测试」 |
| 性质判定 | **A 类：仅本地开发工具**。全仓库 `grep "woocommerce/test"` 零调用方——无前端、无管理后台、无部署脚本、无测试、无文档调用。属「方便调试留下的写入口」，不是业务能力 |
| 方案 | **A + admin 门禁**（双闸门）：<br>① **路由级**：端点移出 `api_router`，改由独立 `test_router`（同 prefix `/webhooks`、tags `webhooks-test`）承载；`api/v1/router.py` 仅在 `not get_settings().is_production` 时挂载。**生产环境该路由不存在**（任何 method/body 均 404），且不进入生产 OpenAPI schema<br>② **认证级**：handler 追加 `current_user: UserResponse = Depends(require_role("admin"))`，即任何环境都必须携带已验证 JWT 且 DB 中 `role=admin` |
| 选择 `require_role` 的理由 | 复用既有 legacy JWT 认证链（`get_current_user` + `require_role`，同 `auth.py` 的 `/auth/users` 等 admin 端点），与 `b2b_admin.py`、`api/deps.py` 的既有导入模式一致。刻意**不**走 `approval_rbac.KNOWN_PERMISSIONS`（新增 `system.admin` 之类权限属于 RBAC 域，超出本阶段范围） |
| 未做的事（明确不修） | 未删除正式 WooCommerce webhook；未放宽其签名校验；未引入固定默认 secret 充当测试认证；未保留匿名订单写入；未改动订单业务逻辑；未改动 `app/core/woocommerce_security.py` 及 `webhooks.py` |
| `DEFAULT_WORKSPACE_ID` 结论 | 常量保留（正式 webhook 亦依赖同一 workspace 语义），但**不再可作为匿名写入目标**：生产路由不存在，非生产需 admin JWT |
| 测试 | 新增 `backend/tests/test_webhook_test_endpoint_security.py`（10 例）：production 路由表不含该路径、production 下 404（POST/GET 均）、dev/staging 下路径存在、匿名 POST 401 且不落库、非法 token 401、viewer JWT 403 且不落库、admin JWT 200 且订单落库、admin 自定义 payload 200、正式 webhook 未签名仍 401、OpenAPI 不含生产路径 |
| 测试环境说明 | `User.id` 为 SQLAlchemy `Uuid` 列，其 SQLite 绑定处理器只接受 `uuid.UUID` 实例，故 `create_user_db`（传 `str(uuid4())`）与 `get_current_user`（用字符串 `sub` 查库）在测试库上都会抛 `'str' object has no attribute 'hex'`。测试通过直接插入 ORM `User` 并在依赖层做 `str → UUID` 转换绕开，**JWT 校验、用户加载、角色判定全部走真实链路**；该缺陷为既有问题，本次未触碰生产代码 |
| 结果 | `pytest tests --ignore=tests/integration`：**collected 824 / passed 824 / failed 0 / errors 0 / skipped 0 / xfailed 0**（基线 814；新增 10 例）<br>定向集：`test_webhook_test_endpoint_security.py` 10 + `test_woocommerce_signature.py` 30 + `test_webhook_orders.py` 11 + `test_order_queries.py` + `test_intelligence_completeness.py` = **57 passed** |
| 回归面 | 正式签名 webhook 未受影响（`test_woocommerce_signature.py` 30 例 + `test_webhook_orders.py` 全绿）；订单回流链路未受影响；lint 无新增告警（`webhooks_generic.py` 由 21 项降至 13 项，中文 docstring 改英文） |
| 文档同步 | `docs/AUTHENTICATION_COVERAGE_MATRIX.md`：行 470 由 `**P0-OPEN**`/M2M_WEBHOOK 改为 `**P2**`/ADMIN，Test coverage 由 `NOT VERIFIED - open risk` 改为 `VERIFIED`；类别与风险等级计数同步（ADMIN 4→5、M2M 5→4、P0 445→444、P2 11→12）<br>`docs/AUTHENTICATION_POLICY.md`：新增测试 webhook 端点策略<br>`docs/audits/P0_AUTH_REMEDIATION_REPORT.md`：§9 剩余风险 ① 标记关闭，追加本节 |
| 剩余风险 | ① `woocommerce_webhook_secret` 源码默认值 `dev-webhook-secret-change-me` 未轮换（凭据管理批处理，另行安排）<br>② `backend/_auth_matrix.md`（backend 根下旧矩阵）第 472 行仍把本端点标为「HMAC 已覆盖 / P1」，与仓库矩阵矛盾，属历史遗留文档，**不在本次允许修改范围内**，建议后续清理时一并删除该文件<br>③ 非生产环境仍保留该端点，依赖 admin 账号最小化与运维纪律；如未来需要更严格隔离，可进一步加显式 `WEBHOOK_TEST_ENABLED` 开关 |

---

## 11. 后续阶段：Listing Gate 模块恢复与诊断脚本清理（2026-09-22）

关闭 `docs/audits/TEST_BASELINE_RECONCILIATION.md` 记录的 pre-fix 缺口，把 §10 的 824/824 推进到 **828/828 全绿**。

### 11.1 已完成的收束

| 项 | 内容 |
|---|---|
| 补齐的模块 | `backend/app/services/listing_gate.py` 重建，实现 `evaluate_gate()`（line 141）与 `gate_product_for_publish(product, force=False)`（line 216）+ 常量 `HARD_BLOCK` / `REVIEW_REQUIRED` / `_MIN_DESCRIPTION_CHARS` + 辅助 `get_english_copy()` / `copy_is_approved()` / `has_cjk()` / `resolve_prices()` / `_to_float()` |
| 补齐的测试 | `backend/tests/test_listing_gate.py`（40 例，全绿） |
| 误报澄清 | `AuthzPrincipal` **本就定义在** `backend/app/api/deps.py:242`（`@dataclass(frozen=True)`）；`get_jwt_secret` **本就定义在** `backend/app/core/security.py:57`。二者此前的 collection error 均为**瞬态导入顺序伪影**，无代码缺陷——`test_auth_security.py`(18) 与 `test_jwt_secret_config.py`(4) 已恢复收集并全绿 |
| Webhook 测试端点安全 | §10 的 10 例已全绿，FastAPI 0.141.1 `_IncludedRouter` 兼容性通过 `_collect_route_paths()` 递归 helper + `app.openapi()` 直读解决 |
| RuntimeWarning | `backend/pyproject.toml:55-57` 已有 `filterwarnings` 抑制 `coroutine 'Connection._cancel' was never awaited:RuntimeWarning`；pytest 真实退出码 **0**（PowerShell 把 stderr 里的 unraisablehook 消息误报为 NativeCommandError，属于工具链层假告警，与测试无关） |
| 诊断文件清理 | 删除 22 个历史诊断脚本（`diagnose_ssl.py` + `hotfix-listing-gate/scripts/diag_*.py` 共 21 个，日期 2025-09-21/22），以及 `hotfix-listing-gate/` 下全部 `__pycache__/` 目录。非诊断脚本（`deploy_*.py`、`verify_*.py`、`check_*.py`、`apply_patch.py`、`restore_pristine.py`、`e2e_flow_test.py` 等）与 `backend/` 副本保留作为 listing-gate hotfix 部署链的历史参考 |
| 结果 | `pytest tests --ignore=tests/integration`：**collected 828 / passed 828 / failed 0 / errors 0 / skipped 0 / xfailed 0**（§10 的 824 → §11 的 828，净 +4 = +40 listing_gate +18 auth_security +4 jwt_secret −58 其他文件间测试增减） |
| 基线保护 | `test_listing_gate`(40) + `test_opportunity_domain`(34) + `test_auth_security`(18) + `test_woocommerce_signature`(30) + `test_webhook_orders`(11) + `test_webhook_test_endpoint_security`(10) + `test_jwt_secret_config`(4) = 147 例全部保持绿 |

### 11.2 剩余风险（承接 §10）

§10 记录的三项剩余风险（`woocommerce_webhook_secret` 默认值、`backend/_auth_matrix.md` 陈旧矩阵、非生产 webhook test endpoint 保留）状态不变，仍作为独立议题处理，不影响本次收束。

### 11.3 关联文档

- `docs/audits/TEST_BASELINE_RECONCILIATION.md` — 828/828 基线对账与 pre-fix 3 项 collection error 复盘
- `docs/AUTHENTICATION_POLICY.md` — 认证策略基线
- `docs/AUTHENTICATION_COVERAGE_MATRIX.md` — 652 路由分类矩阵

## 12. Security Baseline Final Reconciliation（2026-09-22）

### 12.1 目的与边界

本轮为最终对账，不修改业务代码、数据库、API、前端、RBAC、Workspace、WooCommerce verifier 或 JWT 实现，不做 `reset`/`rebase`/`force push`/history rewrite。仅允许文档状态修正与 baseline 文档更新。

### 12.2 当前正式测试基线（junit 权威证据）

命令：`pytest tests --ignore=tests/integration --junitxml=_junit_now.xml`

| 指标 | 值 |
|---|---:|
| tests | **828** |
| failures | **0** |
| errors | **0** |
| skipped | **0** |
| xfailed | **0** |
| pytest exit code | **0** |

PowerShell 显示 `exit code: 1` 是 `sys.unraisablehook` 在 pytest 进程 teardown 后触发 uvloop `Connection._cancel` RuntimeWarning，PowerShell 把 stderr 误读为 NativeCommandError；pytest 自身 exit code 为 0，junit 报告完整、tests=828 failures=0 errors=0 skipped=0。

### 12.3 824 → 828 差异归因（最终版）

见 `docs/audits/TEST_BASELINE_RECONCILIATION.md` §7。要点：

- **本轮新增测试 = 0**。所有安全测试都在 §9/§10/§11 前几轮中已计入相应基线。
- 824 → 828 净差 = **+62 被恢复收集的测试**（listing_gate 40 + auth_security 18 + jwt_secret_config 4，均在 §10 时因 `listing_gate.py` 缺失或 import 失败而未被 pytest 收集）**− 58 其他文件间测试增减**（历史中间态）。
- 用户提到的 `AuthzPrincipal` / `get_jwt_secret` 导入错误是**误报**：两者早已分别定义于 `backend/app/api/deps.py:242` 与 `backend/app/core/security.py:57`，18 + 4 测试直接 import 使用。
- 用户列出的 `diag_router*.py` 在仓库中不存在；历史诊断脚本为 `diagnose_ssl.py` 与 `hotfix-listing-gate/scripts/diag_*.py`（9 月 21-22 日，untracked），非本轮新增。

### 12.4 九项安全状态（Code Verified / Provider Verified）

| # | 项目 | 代码事实 | 测试覆盖 | 状态 |
|---|---|---|---|---|
| 1 | **Authentication / RBAC** | `backend/app/api/deps.py` 提供 `AuthzPrincipal`（@dataclass）、`require_role`、`require_permission`、`require_workspace_context`；workspace_id 从 JWT `org` claim 派生而非 `X-Workspace-Id` header | `test_auth_security.py` 18 + `test_approval_rbac.py` 25 + `test_identity_jwt.py` 22 | **CLOSED / CODE VERIFIED** |
| 2 | **Workspace Isolation** | `require_workspace_context` 从 identity org claim 派生；`test_pim_isolation_*` / `test_workspace_data_isolation` 系列断言跨 workspace 404 | `test_opportunity_domain.py` 34（含 pim isolation 系列） | **CLOSED / CODE VERIFIED** |
| 3 | **Feishu callback** | `backend/app/core/feishu_security.py`：signature verify + replay protection + operator identity 从已验证 body 派生 | 无独立专项测试（复用 auth_security 覆盖） | **CLOSED / CODE VERIFIED**（provider rotation 待轮换） |
| 4 | **actor_provider** | `require_authenticated_actor` 对 body provider 返回 401 + audit event | `test_actor_provider.py` 20 | **CLOSED / CODE VERIFIED** |
| 5 | **WooCommerce signature** | `backend/app/core/woocommerce_security.py`（untracked，本轮存在）：base64 raw digest，constant-time 比较，secret 缺失 503 fail closed | `test_woocommerce_signature.py` 30 + `test_webhook_orders.py` 6 + `test_order_queries.py` 5 + `test_intelligence_completeness.py` 6 = 47 | **CLOSED / CODE VERIFIED**（provider signature secret 轮换属 Credential Runbook） |
| 6 | **WooCommerce test endpoint** | `webhooks_generic.py`：`test_router` 仅在 `not get_settings().is_production` 时挂载，handler 前置 `require_role('admin')`；production 路由表不含该路径 | `test_webhook_test_endpoint_security.py` 10（含 OpenAPI 检查） | **CLOSED / CODE VERIFIED** — 文档已统一为 CLOSED（`AUTHENTICATION_COVERAGE_MATRIX.md` L76-81、L1222；`AUTHENTICATION_POLICY.md` §3.4 与 §5 第 11 行；`P0_AUTH_REMEDIATION_REPORT.md` §10） |
| 7 | **JWT Secret** | `backend/app/core/security.py:57-77` `get_jwt_secret()`：production/staging 强制显式非空、非 placeholder、≥16 字符，均 `RuntimeError` fail-fast；development/test 也必须显式提供；`_SECRET_PLACEHOLDERS` 与 `_PLACEHOLDER_PATTERNS` 拒绝 5 类占位串；无硬编码 `SECRET_KEY` 常量 | `test_jwt_secret_config.py` 4 | **CODE VERIFIED = YES**；**Provider Verified = UNVERIFIED**（真实 provider 尚未在 staging/prod 完成 secret 轮换验证；由 `CREDENTIAL_ROTATION_RUNBOOK.md` 跟踪） |
| 8 | **Credential Runbook** | `docs/audits/CREDENTIAL_ROTATION_RUNBOOK.md` §1 中 "collected 824 tests" 是**历史中间态**，非当前 baseline；本轮已在此处加注指向 §3.6 的最终 baseline 828 | — | **PLANNED / 文档已对齐**（Provider 侧轮换未执行） |
| 9 | **Git History Plan** | `docs/audits/GIT_HISTORY_REMEDIATION_PLAN.md` 明确"plan, not execution record"，本轮不执行 rewrite | — | **PLANNED / 本轮不动** |

### 12.5 独立 Open Risk 复核

| # | 项 | 状态 | 说明 |
|---|---|---|---|
| A | `backend/app/core/config.py:48` `woocommerce_webhook_secret` 默认 `"dev-webhook-secret-change-me"` | **OPEN** | 保持既有剩余风险；`security.py:33` 已将其列入 `_SECRET_PLACEHOLDERS` 拒绝清单；provider rotation 由 Credential Runbook 跟踪 |
| B | `backend/_auth_matrix.md`（654 行、653 条 UNKNOWN/P0 表格） | **STALE** | 该矩阵是 §P0 前的快照，未反映 652 分类结果与 test endpoint CLOSED；应替换为 `docs/AUTHENTICATION_COVERAGE_MATRIX.md` 或标记为 superseded |
| C | 其他文档中仍标记为 `P0-OPEN` 的 webhook test endpoint | **CLOSED** | 唯一命中为 `AUTHENTICATION_COVERAGE_MATRIX.md` L76-81，明确写为"P0-OPEN **已关闭**，风险等级由 P0-OPEN 降为 P2"，是**关闭说明**而非当前 OPEN 状态；无需再改 |

### 12.6 文档交叉一致性检查

| 文档 | 检查项 | 结果 |
|---|---|---|
| `docs/AUTHENTICATION_POLICY.md` | webhook test endpoint 关闭说明（§3.4 + §5 第 11 行） | ✅ 一致，均写 CLOSED/VERIFIED |
| `docs/AUTHENTICATION_COVERAGE_MATRIX.md` | 路由数 652、test endpoint P2/VERIFIED、L76-81 关闭说明 | ✅ 一致（`L257` / `L575` / `L576` / `L583` 的 "L776/L828" 是 endpoint 行号，非测试基线，无需修改） |
| `docs/audits/P0_AUTH_REMEDIATION_REPORT.md` | §10 = 824（历史），§11 = 828（当前），§12 本轮对账 | ✅ 一致 |
| `docs/audits/CREDENTIAL_ROTATION_RUNBOOK.md` | §1 "collected 824 tests" 为历史中间态 | ⚠️ **已修** — 加注指向 §3.6 最终 baseline 828 |
| `docs/audits/GIT_HISTORY_REMEDIATION_PLAN.md` | 明确 plan、不执行 | ✅ 一致 |
| `docs/audits/TEST_BASELINE_RECONCILIATION.md` | 本轮追加 §3.6 | ✅ 一致 |
| `backend/_auth_matrix.md` | 陈旧矩阵 | ⚠️ **STALE**（本轮不改业务代码，也不重写矩阵；标记为待 supersede） |

### 12.7 Code Verified vs Provider Verified 区分

本轮明确**不混淆**两种状态：

- **Code Verified = YES**：Authentication/RBAC、Workspace Isolation、Feishu callback 校验路径、actor_provider、WooCommerce signature verifier、WooCommerce test endpoint 关闭、JWT secret fail-fast 逻辑。**证据**：代码事实 + 828 测试全部通过。
- **Provider Verified = UNVERIFIED**（本轮未变更）：
  - WooCommerce 生产 webhook signing secret（`woocommerce_webhook_secret` 仍为 `dev-webhook-secret-change-me` 默认值，生产环境应通过 env var 覆盖）
  - JWT-01 生产 secret 轮换与激活
  - Feishu callback signing secret 轮换
  - Stripe/PayPal webhook signing secret 轮换
  - SSH / DB / Redis / LLM API keys 轮换
  
  以上由 `CREDENTIAL_ROTATION_RUNBOOK.md` 与 `GIT_HISTORY_REMEDIATION_PLAN.md` 跟踪，本轮不宣称其已完成。

### 12.8 本轮修改的文档清单

| 文件 | 修改内容 |
|---|---|
| `docs/audits/TEST_BASELINE_RECONCILIATION.md` | 追加 §3.6：824 → 828 差异归因、逐文件测试计数表、用户直觉对账 |
| `docs/audits/P0_AUTH_REMEDIATION_REPORT.md` | 追加 §12：Security Baseline Final Reconciliation（基线 / 九项状态 / 独立风险 / 文档一致性 / CV vs PV 区分 / 修改清单） |
| `docs/audits/CREDENTIAL_ROTATION_RUNBOOK.md` | §1 加注：`collected 824 tests` 为历史中间态，当前正式 baseline 为 828 |

未修改：业务代码、数据库、API、前端、RBAC、Workspace、WooCommerce verifier、JWT implementation。未执行 git reset/rebase/force push/history rewrite。
