# 历史泄露凭据最终闭环报告（D8-E Round 5，P0）

**执行日期**：2026-11-20
**Owner 验收看板**：DB / 1688 / Hetzner API / Rescue / JWT
**状态标记**：DB ✅ / JWT ✅ / 1688 ⏸️ / Hetzner ⏸️ / Rescue ⏸️

---

## 1. DB 密码（PGPASSWORD）— ✅ 已闭环

| 项 | 结果 |
|---|---|
| 泄露值 | `s2o7bdFw...`（hotfix 分支）|
| 轮换 | 两次轮换（Round 3 `Nuotao_AxRG...` 已失效 + Round 4 `Db_2...` 生效）|
| 当前凭据 | 全新唯一密码（未公开，安全）|
| 验证 | 新密码 ✅ CONNECT OK；所有旧密码 ❌ 认证失败 |
| 服务器 .env | 已更新（脱敏，无明文残留）|
| GitHub Secret | 已同步 |

## 2. JWT Signing Secret — ✅ 已闭环（审计确认安全）

| 项 | 结果 |
|---|---|
| 当前密钥 | `2wz1fouT...`（HS256，生产服务器 .env）|
| git 泄露 | ✅ **未泄露**（.env gitignore + git log 无命中）|
| 伪造 admin token 路径 | ✅ 已修复（3ae73d1 fail-closed）|
| 历史 token | ✅ 已过期（access 8h / refresh 7天）|
| 结论 | 当前密钥安全，无需紧急轮换；兼容轮换可选（维护窗口）|

## 3. 1688 Cookie — ⏸️ BLOCKED（需 Owner）

- Owner 官方登录 → 安全渠道写入 Secret（禁发聊天明文）
- DSH 待验证：调用位置 / Secret 一致性 / 旧会话失效 / 新会话有效 / 只读验证 / 无泄露

## 4. Hetzner API Token — ⏸️ 需 Owner 控制台

- 新旧 Token 并行验证 → 确认新 Token 可用后撤销旧 Token
- 仅存在于 git 历史（hotfix 分支），当前服务器配置无残留

## 5. Rescue 凭据 — ⏸️ 需 Owner 确认

- 先确认实际使用方式及暴露证据，**不得误撤销生产 SSH 运维密钥**
- 若为 Hostinger/Hetzner rescue，需对应控制台重置

---

## 6. 汇总

| 凭据 | 状态 | 说明 |
|---|---|---|
| DB 密码 | ✅ 闭环 | 两次轮换，旧凭据全部失效 |
| JWT | ✅ 闭环 | 当前密钥未泄露，历史 token 过期，伪造路径已修复 |
| 1688 Cookie | ⏸️ 待 Owner | 安全渠道更新 |
| Hetzner API | ⏸️ 待 Owner | 并行验证 + 撤销旧 |
| Rescue | ⏸️ 待 Owner | 确认暴露证据 + 重置 |

**核心安全成果**：DB + JWT 已闭环（当前无有效历史暴露凭据）。1688/Hetzner/Rescue 待 Owner 安全渠道操作。

---

*历史凭据最终闭环：2026-11-20，DSH 自治。DB+JWT 已闭环，其余待 Owner。*
