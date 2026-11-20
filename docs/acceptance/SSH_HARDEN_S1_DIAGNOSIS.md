# SSH 加固 S1 诊断报告

**任务**：ChatGPT 第十一轮 SSH 加固 S1（Owner APPROVED WITH CONDITIONS）
**执行日期**：2026-11-20
**执行方式**：GitHub Actions 通道（ssh-harden-s1-diagnose.yml，只读）
**状态**：**VERIFIED**（只读诊断完成，证据齐全）

---

## 1. SSH 配置现状（sshd -T）

| 指令 | 当前值 | 风险评估 |
|---|---|---|
| port | 22 | 默认端口（可选改，非必须）|
| **passwordauthentication** | **yes** | 🔴 **密码认证开启 = 暴力破解攻击面** |
| permit***login | prohibit-password | ✅ root 仅密钥（已禁 root 密码）|
| pubkeyauthentication | yes | ✅ 密钥认证开启 |
| maxauthtries | 6 | 默认 |
| **maxstartups** | 10:30:100 | 攻击占满未认证连接上限（S6 暂不调）|
| allowusers/allowgroups | 未设置 | 可选加固（限用户）|

---

## 2. 认证方式与密钥

| 项 | 状态 |
|---|---|
| **管理员登录方式** | **全部 publickey**（journalctl 无密码登录记录）|
| 主密钥指纹 | SHA256:hdKNGr4Lpv+usK9qcw3R70tFhxeLJs/339DE53Ua1Eo（ED25519）|
| 第二密钥指纹 | SHA256:LLvOLrN9ZfQrOlcaYW6t4FVSiU04ukKN/RhrwGhewy0 |
| authorized_keys | root + 部署用户各 2 个密钥 |
| 当前连接 | 20.102.103.194 / 20.109.87.96（GitHub Actions runner，我方）|

**结论**：管理员**全部用密钥登录，无密码登录记录** → **禁用密码认证（S4）安全**，不会锁死管理员。

---

## 3. 登录日志（最近成功登录）

全部 `Accepted publickey`（无密码登录）：
- 18.214.123.177（AWS）、20.109.x.x（Azure/GitHub）等
- 时间：Nov 20 00:53 ~ 01:16（我方 GitHub Actions 诊断连接）

**暴力破解证据**（前次诊断）：多 IP（4.149.232.37、165.154.6.112 等）`Invalid user` / `Failed password` 持续攻击 —— 因密码认证开启。

---

## 4. fail2ban 状态

| 项 | 状态 |
|---|---|
| fail2ban-client | **未安装**（command not found）|
| fail2ban 服务 | inactive / not running |

**结论**：**无暴力破解自动防护**（S3 需安装 + 配置 SSH jail）。

---

## 5. 系统状态

| 项 | 值 |
|---|---|
| OS | Ubuntu 26.04.1 LTS |
| uptime | 13 天 15 小时 |
| load average | 0.76 / 0.51 / 0.54（正常）|

---

## 6. S1 结论与下一步

**安全画像**：
- ✅ 管理员全密钥登录（禁密码安全）
- ✅ root 已禁密码（prohibit-password）
- 🔴 密码认证开启（passwordauthentication yes）= 暴力破解攻击面
- 🔴 无 fail2ban 防护

**下一步（ChatGPT 批准的 S2-S5）**：
| 阶段 | 动作 | 依赖 |
|---|---|---|
| S2 | 验证密钥登录正常 + Hetzner Console 应急访问 | 已确认密钥正常（本报告）|
| **S3** | **安装 fail2ban + 配置 SSH jail + 测试** | S1 完成 ✅ |
| S4 | 禁用密码认证（passwordauthentication no）| **S2 确认第二通道（Hetzner Console）后** |
| S5 | 验证新连接/旧连接/fail2ban/日志 | S3-S4 后 |
| S6 | 调整 MaxStartups | **暂不批准**（先提供方案）|

**⚠️ S4 前置红线**（ChatGPT）：必须先确认 Hetzner Console 应急访问可用（第二通道），才能禁密码。

---

## 7. Git commits

- 3d788f2：ci: SSH harden S1 read-only diagnosis

---

*S1 诊断：2026-11-20，GitHub Actions 通道，只读无修改*
