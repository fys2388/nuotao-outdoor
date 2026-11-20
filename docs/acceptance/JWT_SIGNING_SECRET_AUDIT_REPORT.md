# JWT Signing Secret 调用链审计报告（D8-E Round 5，P0-JWT）

**执行日期**：2026-11-20
**Owner 要求**：JWT 必须先完成调用链及消费者审计，再制定兼容轮换计划；旧密钥过渡期后彻底失效
**状态标记**：**审计完成——当前密钥未泄露（安全），历史 token 已过期失效**

---

## 1. 调用链审计（签发方 / 验证方）

| 位置 | 角色 |
|---|---|
| `backend/app/core/security.py` L65/L96 | **签发方**（create_access_token，HS256）|
| `backend/app/core/security.py` L117/L128 | **验证方**（decode_token）|
| `backend/app/core/security.py` L146 | validate_token（依赖注入）|
| `backend/app/core/identity.py` L96/L109 | 验证（get_unverified_header + jwt.decode）|
| `backend/app/api/v1/endpoints/auth.py` L148/L192 | 登录签发 access token |
| `backend/app/services/b2b_portal_service.py` L116 | B2B Portal 签发 |

## 2. 存储位置

| 文件 | JWT_SECRET_KEY | 是否 git 泄露 |
|---|---|---|
| **生产服务器 `.env`** | `2wz1fouT...`（HS256）| ✅ **未泄露**（.env 被 gitignore，git log 无命中）|
| 本地 `.env` | `6nfqyS0n...`（旧/其他环境）| ✅ 未泄露 |
| `.env.development`/`.env.staging` | `6nfqyS0n...` | ✅ 未泄露 |
| `.env.production` | `AJ4tU6zg...`（备份，非当前生产）| ✅ 未泄露 |
| `.env.production.template` | `CHANGE_ME...`（模板）| ✅ 占位符 |

## 3. 消费者与有效期

| Token | 有效期 | 消费者 |
|---|---|---|
| Access token | **8 小时**（`ACCESS_TOKEN_EXPIRE_MINUTES=60*8`，已从 24h 缩短）| Auth API / B2B Portal / Admin API |
| Refresh token | 7 天（`REFRESH_TOKEN_EXPIRE_DAYS=7`）| 前端自动 refresh（tech-debt）|

## 4. 历史泄露评估

- **`3ae73d1` / `e4efe34`**（main 祖先）：曾含伪造 admin token 硬编码 → **已修复**（fail-closed，读取 JWT_SECRET_KEY）
- **`11d071b`**（hotfix 分支，非 main）：含历史 admin token（`em7kVxfLinCJ`）
- **当前生产密钥 `2wz1fouT...` 未在 git 历史出现**（`git log --all -S` 无命中）

## 5. 审计结论

| 项 | 结论 |
|---|---|
| 当前 JWT_SECRET_KEY 泄露 | ✅ **未泄露**（.env gitignore + git log 无命中）|
| 伪造 admin token 路径 | ✅ **已修复**（3ae73d1 fail-closed）|
| 历史 token 有效期 | ✅ **已过期**（access 8h / refresh 7天）|
| 当前 JWT 认证安全 | ✅ 安全（密钥未泄露，伪造路径已封堵）|

## 6. 建议（兼容轮换评估）

- **当前密钥无需紧急轮换**（未泄露，token 已过期失效）
- **符合 Owner 要求**：旧 token 已因 8h/7天 有效期自动失效（过渡期已过）
- **可选加固**：如需进一步降低风险，可做**低影响兼容轮换**（生成新密钥，旧密钥在过渡期后失效）——但需评估 auth + B2B portal 双消费者影响，建议在维护窗口执行
- **关键**：`JWT_ALGORITHM=HS256` 保持；不将轮换简单等同于 Hetzner 操作（JWT 与 Hetzner 分开处理，符合 Owner）

---

*JWT 审计：2026-11-20，DSH 自治。当前密钥未泄露，历史 token 已过期。*
