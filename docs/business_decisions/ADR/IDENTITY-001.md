# ADR IDENTITY-001 — Nuotao 全平台身份认证与访问控制

> 状态：**Accepted**（2026-08-14）
> 决策编号：IDENTITY-001
> 关联：`docs/identity_architecture.md`；`docs/project_architecture.md` §3.24

---

## Context（背景）

- M5.8 记录 `AUTHENTICATION_GAP`：审批/审计 actor 默认由 `request body` 声明（`ACTOR_PROVIDER=body`），仅靠服务端 RBAC 兜底，**不构成生产可信身份**。
- 后续里程碑（M5.9~M5.12）readiness / activation gate 一致将 `ACTOR_PROVIDER=body` 判为 `BLOCKED_REAL_OPERATOR`。
- 需要正式确定生产级身份链路：登录 → 零信任边界 → JWT → 应用内验证 → 业务 RBAC。

## Decision（决策）

Nuotao 全平台身份认证与访问控制正式采用三层架构：

1. **Clerk / Enterprise Identity** — 身份提供方：Login / User / Organization / JWT / Identity lifecycle。
2. **Cloudflare Access** — Zero Trust 边界：SSO / Application Access Policy / Edge protection / JWT propagation（注入 `CF-Access-Jwt-Assertion`）。
3. **Nuotao Identity Layer + Nuotao RBAC** — 应用内：JWT verification（JWKS）→ identity normalization → user↔workspace mapping → actor resolution → 业务权限。

约束（不可违背）：

- 生产可信身份**唯一来源**是经 Cloudflare Access + Clerk 签名验证的 JWT。
- 禁止 `request body actor` 作为生产可信身份；禁止直接相信裸 `X-Actor`；禁止 Agent 自声明 actor/admin/operator；禁止前端决定权限。
- 生产配置 `ACTOR_PROVIDER=header`，且 header 必须经过 Cloudflare Access / trusted proxy + JWT 签名/claims 验证。
- Staging 与 Production 必须保持**同一套身份模型**（同一代码路径，仅 provider 配置、JWKS、网关不同）。
- `CLERK_SECRET_KEY` / JWT / Cloudflare 凭据禁止写入 DB、event_log、trace、console、应用日志。

## Consequences（后果）

- 正面：生产身份可信、可审计、workspace 隔离可服务端强制；对接企业 SSO（Entra ID / Okta via Clerk Enterprise）平滑。
- 成本：必须接入真实 Clerk（Test → Production）与 Cloudflare Access；staging 需可用测试身份源；实施身份层代码（JwtActorProvider + 验证中间件 + workspace 映射）。
- 过渡：在真实身份系统接入前，staging 保持 `BLOCKED_REAL_OPERATOR`，不伪造 PASS。
- 落地范围（后续实施）：`app/core/actor.py` 新增 `JwtActorProvider`；`app/core/workspace.py` 服务端 org→workspace 映射；JWT 验证中间件；`agent_approval_roles` 角色 seed 与 `product.candidate.*` 权限扩展（M5.13）。

## Alternatives（备选与否定理由）

| 方案 | 否定理由 |
|---|---|
| Auth0 | 功能相近，但与现有 Clerk 集成成本更高；未形成既有选型约束 |
| 自建 SSO（OAuth2 + 自管 IdP） | 安全合规、MFA、组织管理自维护成本高，不符合低成本优先 |
| Keycloak（自托管开源） | 可作为成本敏感备选；当前优先托管方案降低运维负担，若成本超限可回退 |
| 维持 `ACTOR_PROVIDER=body` + 服务端 RBAC | 无真实身份，无法满足生产信任/审计要求（AUTHENTICATION_GAP 不关闭） |
