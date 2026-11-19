# Nuotao AI OS — Authentication & Authorization Policy

> **文件**：`docs/AUTHENTICATION_POLICY.md`
> **版本**：v1.1（2026-11-19）— **认证架构已变更，见下方 v1.1 声明**
> **阶段**：P0-Critical Security Remediation — 策略基线
> **依据**：`docs/AUTHENTICATION_COVERAGE_MATRIX.md`（652 路由全量 AST 审计）

---

## ⚠️ v1.1 变更声明（2026-11-19）：认证架构 Clerk → 自建统一登录

> **本节为最新事实，下方正文中的 Clerk 相关描述为 v1.0 历史背景，生产已不再使用 Clerk。**

**生产环境（admin.nuotaooutdoor.com）认证已从 Clerk 迁移为自建统一登录**：

| 维度 | v1.0（已过时） | v1.1 现状（生产） |
|---|---|---|
| **Authentication** | Clerk RS256 JWT（JWKS 密码学校验） | **自建**：邮箱+密码 → 后端签发 HS256 JWT（`app/core/security.py`）|
| **登录入口** | Clerk Hosted UI / Clerk JS | 统一登录页 `UnifiedLoginPage`（B2B portal + admin 双 fallback）|
| **admin 账户来源** | Clerk Dashboard 创建 | 自建 `users` 表（`role=admin`），由 `scripts/create_admin_user.py` 自举 |
| **access token 有效期** | Clerk 默认 | **24 小时**（`ACCESS_TOKEN_EXPIRE_MINUTES = 60*24`，偏长，建议缩短至 60min）|
| **refresh token 有效期** | Clerk 默认 | **7 天**（`REFRESH_TOKEN_EXPIRE_DAYS = 7`）|
| **B2C 前台** | Clerk | WooCommerce 自带会话（WordPress），不经过 AI OS JWT |

**v1.1 安全基线（P0-4 已落地）**：
- 生产 `.env` 权限 `600`（含密钥，禁止 world-readable）
- WooCommerce Webhook Secret 使用强随机值（禁用 `dev-webhook-secret-change-me` 默认值）
- 生产 admin 账户：`owner`（admin）、`admin`（admin），均活跃；密码策略由 Owner 维护
- JWT_SECRET_KEY 强度 ≥ 86 字符

**未变更（仍然有效）**：下方正文定义的四个正交概念、9 类策略矩阵、RBAC/Workspace Authorization 语义、`app/core/identity.py` + `app/api/deps.py` + `app/services/approval_rbac.py` 三件套行为。仅 Authentication 的**签发与校验实现**从 Clerk 换为自建 JWT，鉴权语义不变。

---

## 1. 四个正交概念

这四个概念**不可互相替代**。审计中出现的所有漏洞，本质都是把其中两个
当成同一个东西。

| 概念 | 回答的问题 | 失败码 | 唯一可信来源 |
|---|---|---|---|
| **Authentication** | 你是谁？ | **401** | 经 JWKS 密码学校验的 RS256 JWT（Clerk） |
| **Workspace Authorization** | 你能进入哪个 workspace？ | **403** | `workspace_identity_links` 表：identity 的 `org` → workspace |
| **RBAC / Permission** | 你在这个 workspace 能做什么？ | **403** | `agent_approval_roles`：actor → 权限集合 |
| **Requested Workspace** | 请求想指向哪个 workspace？ | 400/403 | `X-Workspace-Id`（**仅路由提示**） |

### 1.1 明确禁止的替代关系

| 禁止 | 原因 |
|---|---|
| `X-Workspace-Id` 代替身份 | header 由调用方任意填写，仅做「目标」声明 |
| `X-Workspace-Id` 代替 membership | 没有映射表记录就不能进入该 workspace |
| `body.actor` 代替 JWT | 请求体自声明，攻击者可任意填写 |
| `body.operator` 代替签名校验 | Feishu 身份字段只在签名有效后可信 |
| 缺角色配置 代替 授权通过 | 无配置 = 策略未知 = **DENY** |
| 未定义 permission 代替授权通过 | 未知策略 = **DENY** |

---

## 2. 策略矩阵（9 类 × 4 轴）

| 类别 | Authentication | Workspace Authorization | RBAC / Permission | 当前路由数 |
|---|---|---|---|---|
| **PUBLIC** | 无（设计公开） | 无 | 无 | 6 |
| **AUTHENTICATED_USER** | `require_authenticated_actor`（JWT → Identity） | 可选：`require_workspace_context` | 按路由需要 | 20 |
| **WORKSPACE_USER** | `require_authenticated_actor` | **必需**：`require_workspace_context` | 可选 | 1 |
| **ADMIN** | `require_authenticated_actor` | **必需** | `require_permission("<domain>.admin")` | 4 |
| **M2M_WEBHOOK** | 请求体 HMAC-SHA256 + `hmac.compare_digest` | 不适用（独立边界） | 不适用（主题级 scope 建议） | 5 |
| **SYSTEM** | `require_authenticated_actor` + 内网来源限制 | **必需** | `require_permission("<domain>.admin")` | 15 |
| **SPECIAL_AUTH** | 独立认证域（B2B Agent JWT / 飞书签名） | 需映射到 workspace | 需映射到 actor + 权限 | 11 |
| **INTERNAL** | 同 SYSTEM | **必需** | `require_permission` | 0 |
| **UNKNOWN** | **无 —— 本类是漏洞，不是类别** | — | — | 590 |

> `UNKNOWN` 不是合法分类。它表示「尚未归类，因此不可信」。
> 治理路径是把它逐条迁移到前 8 类。

### 2.1 每类的具体依赖组合

```python
# PUBLIC —— 健康检查、登录注册、B2B 登录
@router.get("/healthz", ...)            # 无任何 Depends

# AUTHENTICATED_USER
identity: Annotated[Identity, Depends(require_authenticated_actor)]

# WORKSPACE_USER / ADMIN / SYSTEM —— 身份 + 工作区
principal: Annotated[AuthzPrincipal, Depends(require_authorized_principal())]

# ADMIN / SYSTEM / 高危写 —— 身份 + 工作区 + 权限
principal: Annotated[AuthzPrincipal, Depends(require_authorized_principal("product.publish"))]

# M2M_WEBHOOK —— 传输层签名，绝不用人类 JWT
await feishu_security.verify_callback(request)   # 见 §3
```

---

## 3. 边界定义（Boundary Definitions）

### 3.1 Human User Boundary

```
CF-Access-Jwt-Assertion: <RS256 JWT signed by Clerk>
        │
        ├─ 密码学校验（JWKS, iss/aud/exp/nbf/sub, alg=RS256 only）
        │     失败 ──────────────────────────► 401
        │
        ├─ normalize: sub → actor_id, o.id/org → organization_id
        │     缺 org claim ──────────────────► 401
        │     sub ∈ {agent, system} ─────────► 401   （系统身份不得冒充人）
        │
        ├─ workspace_identity_links lookup
        │     无映射 ────────────────────────► 403
        │     X-Workspace-Id 与映射不符 ─────► 403
        │
        └─ approval_rbac.check_actor_permission
              无 enabled role ──────────────► 403   （fail closed）
              缺权限 / 未知权限 ─────────────► 403
              通过 ──────────────────────────► ALLOW
```

**实现位置**：`app/core/identity.py` → `app/api/deps.py` →
`app/services/approval_rbac.py`。
三者已存在且已测试（`tests/test_identity_api.py` 14 条），本阶段只做
**fail-closed 收紧**与**接线**，不新建系统。

### 3.2 Machine-to-Machine Boundary（独立，不得套用人类 JWT）

Webhook 是**独立认证边界**。把 `require_authenticated_actor` 套到 webhook 上
是错误的——外部系统不会携带人类 JWT。

| 类型 | 认证机制 | 实现 |
|---|---|---|
| WooCommerce webhook | HMAC-SHA256 over **原始 body bytes**，base64 raw digest | `app/core/woocommerce_security.py`（`webhooks.py` 与 `webhooks_generic.py` 共用；**只接受 base64**） |
| Feishu card callback | SHA256 over `timestamp + nonce + encrypt_key + body`，hex | `app/core/feishu_security.py` |

**两个边界不可混用**：Feishu 是 hex + 三头 + 时间戳；WooCommerce 是 base64、单头、无时间戳。
一个 digest 从不是另一个 digest 的合法格式，错误复用会让每条合法投递都变成 401。

**共同要求**：

1. 签名校验必须 **fail closed**：无密钥配置 = 拒绝（503），不是放行；签名用**原始 body bytes** 计算，不得对 JSON 重新序列化后验签
2. 必须做**重放防护**（timestamp 新鲜度窗口 + nonce）。WooCommerce 协议本身不提供时间戳/nonce，因此不凭空新增协议字段——由 `order_service.ingest_order` 在 `(workspace_id, external_order_id)` 上的幂等守卫兜底
3. 签名校验通过后，请求体字段才可被信任
4. 签名校验通过后仍需 workspace 归属校验与权限校验（Feishu operator → actor 映射）
5. secret 与签名值本身**禁止写入日志**

**禁止**：删除 webhook 认证改用人类 JWT；用 `X-Workspace-Id` 代替签名。

### 3.3 System Boundary

`worker` / `scheduler` / `backup` / `sweeper` / `deployment` 端点。
这些是运维面，攻击价值最高。要求：人类 JWT + workspace + admin 级权限。
未来应收敛到内网 mTLS 或专用服务账号，但**本阶段不引入新凭证体系**
（避免过度工程化）。

### 3.4 Test-Only Webhook Helper Boundary（P0 修复，2026-09-22）

`POST /webhooks/woocommerce/test` 曾是无签名校验、无条件挂载进 `api_router`
的写入口，可匿名向 `DEFAULT_WORKSPACE_ID` 写入订单。**现已关闭该缺口**：

| 层 | 规则 |
|---|---|
| 路由层 | 端点从全局 `router` 移出，改由独立 `test_router` 承载；`api/v1/router.py` 仅在 `not get_settings().is_production` 时挂载。**生产环境该路由不存在**（404），且不进入生产 OpenAPI |
| 认证层 | 任何环境下都必须携带已验证 JWT 且 DB `role=admin`（`Depends(require_role("admin"))`） |
| 数据层 | `DEFAULT_WORKSPACE_ID` 常量保留，但**不再是匿名写入目标** |

**边界语义**：这是开发/预发调试工具，不是业务能力。它属于 ADMIN 边界
（人类 JWT + 角色），**不属于** M2M_WEBHOOK 边界——不能以「webhook 不带
人类 JWT」为由对其保留匿名访问。生产可达的未授权写入口一律视为 P0。

**禁止**：

1. 在生产环境保留任何未认证的 webhook 测试/调试入口
2. 用固定默认 secret 充当测试认证（等效于无认证）
3. 为「方便调试」让测试路由绕过 `is_production` 门禁

**验证**：`backend/tests/test_webhook_test_endpoint_security.py`（10 例）——
production 路由表缺失与 404、dev/staging 路径存在、匿名 401 且不落库、
viewer 403 且不落库、admin 200 且落库、正式签名 webhook 仍 401。

---

## 4. 禁止行为清单（11 条，对应本阶段红线）

| # | 禁止 | 违规后果 |
|---|---|---|
| 1 | 删除任何已有安全校验 | 立即回滚 |
| 2 | 恢复 legacy open mode 作为默认行为 | 只能作为显式 opt-out flag |
| 3 | 用 `body.actor` 绕过 JWT | 身份边界必须不可旁路 |
| 4 | 用 `X-Workspace-Id` 代替身份/membership | 它只是路由提示 |
| 5 | 为了兼容旧测试而默认 allow | 测试应改用真实认证凭据 |
| 6 | 把所有 API 粗暴套成同一种认证 | M2M / PUBLIC 必须独立 |
| 7 | 删除 webhook authentication | M2M 边界必须保持 |
| 8 | 自动批准 Agent | 违反 `AGENTS.md` §3.1 |
| 9 | 未认证调用方触发 Agent suggestion 执行 | 伪造身份执行 |
| 10 | 修改测试期望来隐藏权限失败 | 测试必须真实验证拒绝路径 |
| 11 | 保留生产可达的未认证写入口（含 webhook 测试/调试路由） | 见 §3.4；生产可达未授权写入视为 P0 |

---

## 5. 迁移顺序（分批，不一次改完 652 条）

| 批次 | 范围 | 本阶段 |
|---|---|---|
| **B0** | 身份边界基础（fail-closed、禁 body 身份） | ✅ 本阶段 |
| **B1** | Critical path：Feishu callback | ✅ 本阶段 |
| **B2** | 高危写接口（approve / publish / push / force / delete / reset / replay / rollback / refund / receive / import / sync） | ✅ 本阶段（用户点名的 11 条） |
| **B3** | Workspace business reads/writes | ⏳ 后续子阶段 |
| **B4** | Admin / System | ⏳ 后续子阶段 |
| **B5** | 剩余 400+ 条 UNKNOWN | ⏳ 后续子阶段 |

### 5.1 批次 B2 的具体接线

| 路由 | Permission | 说明 |
|---|---|---|
| `POST /approvals/{id}/approve` | —（服务层已有类型级 RBAC） | 补 Authentication + Workspace |
| `POST /approvals/{id}/reject` | —（同上） | 同上 |
| `POST /agent-queue/dead-letters/{id}/replay` | `dlq_replay.approve` | |
| `POST /agent-registry/{id}/rollback` | `agent.lifecycle.approve` | |
| `POST /purchase-orders/{id}/approve` | `procurement.approve` | 新 permission |
| `POST /purchase-orders/{id}/receive` | `procurement.receive` | 新 permission |
| `POST /refunds/{id}/approve` | `refund.approve` | 新 permission |
| `POST /products/import` | `product.manage` | 新 permission |
| `POST /products/{id}/push-woocommerce` | `product.publish` | 新 permission |
| `POST /products/push-woocommerce` | `product.publish` | 新 permission |
| `PUT /system-settings/` | `system.admin` | 新 permission |
| `POST /system-settings/reset` | `system.admin` | 新 permission |

> Permission 命名沿用既有 `APPROVAL_PERMISSIONS` 注册表风格
> （`<domain>.<verb>`）。新增条目集中在
> `app/services/approval_rbac.py::KNOWN_PERMISSIONS`。

---

## 6. Fail-Closed 语义

`RBAC` 在任何不确定状态下必须拒绝：

| 条件 | 行为 |
|---|---|
| 无认证主体 | DENY（401） |
| 主体来自 body 自声明 | DENY（401） |
| 无 workspace membership | DENY（403） |
| `X-Workspace-Id` 与映射不符 | DENY（403） |
| workspace 无 enabled role | DENY（403）— **本阶段变更** |
| actor 不在任何 role 的 actors 中 | DENY（403） |
| 缺所需 permission | DENY（403） |
| permission 字符串为空/非法 | DENY（403） |
| RBAC 全局开关关闭 | DENY（403）— **本阶段变更** |
| 飞书签名校验失败 / 缺失 | DENY（401/403） |
| 飞书 timestamp 超新鲜度窗口 | DENY（403，重放防护） |

**兼容退路**：保留 `approval_rbac_fail_closed=False` 作为**显式 opt-out**
（仅本地/演练用），并记录 `WARNING`。默认值为 `True`。
不删除 legacy 逻辑——它作为显式关闭态保留，避免锁死未配置完的环境。

---

## 7. 审计要求

所有 deny / allow 决策必须落 `event_log`（已有 `identity.*` 事件族）：

| 事件 | 触发 |
|---|---|
| `identity.authenticated` | JWT 校验通过 |
| `identity.authentication_failed` | JWT 缺失/无效（401） |
| `identity.workspace_resolved` | workspace 映射成功 |
| `identity.authorization_denied` | workspace / permission deny（403） |

> 飞书 M2M 边界目前**只写结构化日志**（`feishu.callback.rejected reason=...`），
> 不落 `event_log`；补 `feishu.callback.signature_rejected` /
> `feishu.callback.replay_rejected` 两个事件类型已登记为后续建议
> （见 `docs/audits/P0_AUTH_REMEDIATION_REPORT.md` §7 R1）。

**审计 payload 禁止包含**：JWT、token、secret、signature、email、PII。

---

## 8. 完成判定（本阶段）

| # | 判定项 | 验证方式 | 状态 |
|---|---|---|---|
| 1 | Feishu card callback 不再允许伪造身份执行 | `tests/test_auth_security.py` 9 个 Feishu 场景 | ✅ |
| 2 | body actor/operator 不再作为可信身份 | `tests/test_actor_provider.py` + `tests/test_auth_security.py` | ✅ |
| 3 | RBAC 默认 fail closed | `tests/test_approval_rbac.py`（更新 3 + 新增 4） | ✅ |
| 4 | 高危写接口不能匿名执行 | `tests/test_auth_security.py`（body actor / X-Actor / workspace） | ✅ |
| 5 | workspace authorization 仍然有效 | `tests/test_identity_api.py` 保持全绿 | ✅ |
| 6 | M2M webhook 不被破坏 | 未改动 `webhooks.py`；10 个既有失败见报告 §5 | ⚠️ 既有 |
| 7 | permission architecture 有真实接线 | 28 条路由（9 个 endpoint 文件）grep 可验证 | ✅ |
| 8 | targeted security tests 通过 | `tests/test_auth_security.py` 18 passed | ✅ |
| 9 | 未新增安全绕过 | 复审清单见报告 §6 | ✅ |
| 10 | 文档同步 | 本文件 + `docs/audits/P0_AUTH_REMEDIATION_REPORT.md` | ✅ |
| 11 | 生产不存在未认证的 webhook 测试写入口（§3.4，2026-09-22） | `tests/test_webhook_test_endpoint_security.py` 10 例：production 路由表不含该路径且 404、匿名 401 不落库、viewer 403 不落库、admin 200 落库、正式签名 webhook 仍 401 | ✅ |
