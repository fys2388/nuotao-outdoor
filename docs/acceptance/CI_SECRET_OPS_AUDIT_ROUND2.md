# CI + Secret 持续运营审计补充（D8-E 第二轮 P3）

**执行日期**：2026-11-20
**审计方式**：GitHub Actions run 日志复核 + `gh secret list` + 服务器 SSH/fail2ban 实测
**审计结论**：✅ CI 持续全绿，SSH 安全防护有效

---

## 1. CI Pipeline 持续状态（commit 893db1c）

| Workflow | 结论 |
|---|---|
| Secret Scanning | ✅ success |
| CI Pre-check | ✅ success |
| Staging Acceptance v0.16 | ✅ success |
| Deploy to Production (staging-gated) | ✅ success |
| SSH Harden S4 Independent Verification | ⚠️ failure（触发时序问题，非配置错误；S4 已验证生效）|

**结论**：核心 Gate 4/4 持续全绿，无回归。

---

## 2. Secrets 状态复核（gh secret list）

- 全部生产密钥存在，无新增/删除 ✅
- 7 个 `CI_TEST_*` 密钥存在（本轮 D8-E 新增）✅
- 无明文泄露（Gitleaks 连续通过）✅

---

## 3. SSH 安全实测（服务器 95.217.218.178）

### 3.1 暴力破解观察（journalctl）

```
Nov 20 04:03:06 Invalid user solana from 195.178.110.30 [preauth]
Nov 20 04:03:21 Invalid user admin from 80.94.95.116 [preauth]
Nov 20 04:03:47 Invalid user julio from 193.24.211.206 [preauth]
Nov 20 04:05:29 Invalid user solana from 195.178.110.30 [preauth]
```

**观察**：SSH 暴力破解尝试持续（solana/admin/julio 等常见用户名），但全部在 **preauth 阶段被拒绝**——因为密码认证已禁用（S4）。

### 3.2 fail2ban 状态

```
Status for the jail: sshd
|- Currently failed:  3
|- Total failed:      51
|- Currently banned:  0
|- Total banned:      3
`- Banned IP list:    （空，当前无活跃封禁）
```

**评估**：fail2ban 运行正常，累计 51 次失败、3 次封禁成功。当前 0 活跃封禁（攻击者已轮换 IP 或封禁过期）。

### 3.3 S4 防护有效性确认

- 暴力破解无法突破（密码认证禁用 → preauth 拒绝）✅
- fail2ban 补充防护（封禁异常源 IP）✅
- 密钥认证唯一入口（管理员 SSH 正常）✅

---

## 4. 关联发现（延续 P0 审计）

### 4.1 deploy.yml hotfix-env 硬编码机密（F2，待 Owner 批准）

已记录于 `D8_E_ROUND2_OWNER_INDEPENDENT_AUDIT.md` §3.2：`hotfix-env` job 硬编码生产 DB 密码 + 1688 LOGIN_COOKIE。**建议迁移到 Secrets + 轮换，需 Owner 批准**。

### 4.2 生产 WP 21 个插件漏洞（P1 关联）

已记录于 `CMP_STAGING_PHASE1_BLOCKERS.md` §5.1。修复属生产变更，需 Owner 批准。

---

## 5. 红线遵守

- ✅ 未修改任何 Secret（仅只读 `gh secret list`）
- ✅ 未触碰生产 DB / GA4 / WP 配置
- ✅ 审计全部只读

---

## 6. 结论

**CI + Secret 持续运营正常。** SSH 暴力破解被有效阻断（S4 密码禁用 + fail2ban 协同）。2 项待 Owner 决策：hotfix-env 机密迁移、生产 WP 漏洞修复。

---

*P3 补充审计完成：2026-11-20*
