# 历史泄露凭据评估报告（D8-E Round 4，P0-3）

**执行日期**：2026-11-20
**Owner 决策**：D4 升级 P0——审计 PGPASSWORD / API_TOKEN / JWT / rescue_password，如仍有效必须轮换或吊销
**状态标记**：**PGPASSWORD 已失效（PASS）/ API_TOKEN / JWT 待 Owner 配合轮换（PARTIAL）**

---

## 1. 泄露凭据清单（gitleaks 历史扫描）

| 凭据 | 值指纹 | 来源 | 当前状态 |
|---|---|---|---|
| PGPASSWORD | `s2o7bdFw...` | hotfix/listing-gate 分支脚本 | ❌ 已失效（DB 密码已两次轮换）|
| API_TOKEN | `xd2lNU9...` | 同分支（Hetzner API token）| ⚠️ 待确认（需 Hetzner 控制台吊销/轮换）|
| rescue_password | `em7kVxfLinCJ` | 同分支（SSH rescue）| ⚠️ 待确认 |
| JWT admin token | admin 用户 | 同分支 | ⚠️ 待评估（需确认会话影响）|

## 2. 服务器实测（95.217.218.178）

- **当前运行配置（.env）无残留**：仅 `LOGIN_COOKIE` + `JWT_SECRET_KEY`（均脱敏，无 API_TOKEN/rescue_password）
- **泄露凭据仅存在于 .git/objects/pack**（git 历史对象库，hotfix/listing-gate 分支，非 main 祖先）
- **PGPASSWORD**：对应 DB 密码已在两次轮换中失效 ✅

## 3. 评估结论

### 3.1 PGPASSWORD（DB 密码）— ✅ PASS
- 已在 Round 3（`Nuotao_AxRG...`）+ Round 4（`Db_2...`）两次轮换
- 泄露的 `s2o7bdFw...` 已失效（当前使用全新唯一密码）

### 3.2 API_TOKEN（Hetzner）— ⚠️ 需 Owner 配合
- Hetzner API token 需在 **Hetzner 控制台**吊销/重新生成（DSH 无法访问 Hetzner 控制台）
- **需 Owner 操作**：Hetzner 控制台 → API tokens → 吊销旧 token

### 3.3 JWT admin token — ⚠️ 需评估
- Owner 明确"JWT 必须先评估消费者、密钥版本和会话影响，安排兼容轮换"
- JWT_SECRET_KEY 在生产 .env（当前值未泄露，但与泄露的 admin token 对应关系需评估）
- **不能擅自轮换** JWT_SECRET_KEY（会影响现有会话）→ 需 Owner 批准兼容轮换方案

### 3.4 rescue_password（SSH）— ⚠️ 需确认
- 若为 Hostinger/Hetzner rescue 密码，需在对应控制台轮换
- 需 Owner 确认来源并配合

## 4. 结论

- ✅ **PGPASSWORD 已失效**（DB 密码两次轮换）
- ⚠️ **API_TOKEN / JWT / rescue_password**：仅存在于 git 历史（非 main），当前运行配置无残留；但若对应外部服务仍使用原值，需 Owner 配合轮换（Hetzner 控制台 / JWT 兼容轮换评估）
- **无未经授权的生产变更**（未改 JWT_SECRET_KEY，未改 Hetzner token）

---

*历史泄露凭据评估：2026-11-20，DSH 自治。PGPASSWORD 已闭环；API_TOKEN/JWT 需 Owner 配合（如实记录）。*
