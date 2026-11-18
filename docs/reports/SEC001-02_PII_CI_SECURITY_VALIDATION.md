# SEC001-02 — PII 加密与 CI 集成安全验证

- 任务: APR-PII-CI-001 (P1) — 安全专项验证
- 关联: M440-13_PII_CI_INTEGRATION_TEST.md、APR-M440-PII-001 设计、AGENTS.md §4 数据安全
- 日期: 2026-11-18
- 执行者: Nuotao Dev Agent (Sensenova)
- 验证级别: **CI 临时 PostgreSQL，合成数据，测试密钥；不连生产、无真实客户 PII、无生产密钥**

---

## 1. 验证目标

针对 M4.4 PII 加密（AES-256-GCM）+ 搜索哈希（HMAC-SHA-256，workspace 隔离）+ 回填逻辑，在 CI 中验证**安全属性**：

1. 加密强度与往返正确性（AES-256-GCM，带认证 tag）。
2. 搜索哈希确定性 + **workspace 隔离**（跨租户不可枚举/关联）。
3. **Fail-closed**：密钥缺失 / 密钥错误 / 密文损坏 → 一律抛 `PiiCryptoError`，**绝不静默回退明文**。
4. 回填逻辑正确性（明文→密文+哈希+key_version）与幂等。
5. 迁移可回滚（0087 downgrade）。
6. **密钥管理边界**：CI 用独立测试密钥，不使用/不暴露生产密钥。

---

## 2. 安全控制映射（AGENTS.md §4）

| AGENTS.md 要求 | 本实现 | CI 验证 |
|---|---|---|
| §4.2 PII 加密存储（AES-256） | `encrypt_field` = AES-256-GCM（`iv‖ct‖tag` base64） | `test_aes_roundtrip` ✅ |
| §4.2 密钥用 Secrets 管理，禁提交 | 密钥走 env（`PII_ENCRYPTION_KEY`/`PII_HMAC_KEY`）；CI 用测试值 | workflow env；无密钥入库 ✅ |
| §4.1 L4 PII 加密 + workspace 隔离 | `build_email_hash` = HMAC-SHA-256，workspace-scoped | `test_email_hash_deterministic_and_scoped` ✅ |
| §4.5 fail-closed（不静默降级） | 缺密钥/错密钥/坏密文 → `PiiCryptoError` | `test_key_missing_fail_closed`、`test_wrong_key_rejects`、`test_corrupted_ciphertext_rejects` ✅ |
| §4.4 GDPR（可删除） | 回填可逆（downgrade）、测试数据可清理 | `test_rollback_0087`、`test_cleanup` ✅ |
| §2.4 禁止打印密钥/PII | 密钥仅 env；测试用合成 PII | 全流程无明文入库（除 `email` 业务列，见 §5 已知边界） |

---

## 3. 证据

- **GitHub Actions Run ID**: `44270204004` — `10 passed`
- **URL**: https://github.com/fys2388/nuotao-outdoor/actions/runs/44270204004
- **commit**: `3f6df4e`
- **密钥隔离证据**（workflow 日志）：
  - `PII_HMAC_KEY: ci-test-hmac-key-0001`
  - `PII_ENCRYPTION_KEY: AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=`（32B 测试密钥）
  - `DATABASE_URL: ***localhost:5432/nuotao_pii_ci`（临时库，非生产）

### 关键安全用例明细

1. **AES-256-GCM 往返**（`test_aes_roundtrip`）：加密→解密还原明文，认证 tag 保证完整性。
2. **HMAC workspace 隔离**（`test_email_hash_deterministic_and_scoped`）：同 email 不同 workspace → 不同哈希（防跨租户关联）；同 email 同 workspace → 确定性哈希（可搜索）。
3. **Fail-closed 三态**：
   - 缺 `PII_ENCRYPTION_KEY` → `PiiCryptoError`（硬错误，不回退）
   - 错误密钥解密 → `PiiCryptoError`（GCM tag 校验失败，不静默回退明文）
   - 密文损坏（篡改 base64 字符）→ `PiiCryptoError`
4. **回填对账**（`test_backfill_and_reconcile`）：解密==原文、哈希==重算、`pii_key_version='v1'`。
5. **幂等**（`test_repeat_idempotent`）：重跑不破坏可解密性、哈希一致。
6. **回滚**（`test_rollback_0087`）：`alembic downgrade 0086` 删除全部 PII 列、版本回退。

---

## 4. 安全结论

PII 加密 + HMAC 哈希 + 回填逻辑在 CI 临时库验证了**核心安全属性**：加密强度（AES-256-GCM）、租户隔离（workspace-scoped HMAC）、fail-closed（三态异常一律拒绝，不静默回退明文）、可回滚、可清理。**密钥边界**满足：CI 仅用一次性测试密钥与合成数据，生产密钥零暴露。

- `CI_INTEGRATION_TEST = PASS`（含安全用例全绿）
- `STAGING_ACCEPTANCE = BLOCKED`（容器级执行证据待补）
- `PRODUCTION_READINESS = NOT_APPROVED`（生产加密+回填待 Owner 批准）

---

## 5. 已知边界 / 残余风险（交 Owner 判断）

1. **业务列 `email` 仍存明文**：`b2b_leads.email`（用于回填源/对账）当前保留明文列。真正"邮箱密文化"需 Owner 批准移除/置空明文列的后续迁移——**本轮未做，超出批准范围**。当前是"新增密文列 + 哈希"，非"替换明文"。
2. **`contact_name` 明文列同理**：`contact_name_encrypted` 为新增列，`contact_name` 明文列未移除。
3. **CI 覆盖 ≠ 生产**：CI 验证逻辑正确性，但生产密钥轮换、KMS 集成、访问留痕（audit log）等**运维安全**未在本轮覆盖。
4. **HMAC 非加密**：`email_hash` 是确定性哈希，workspace 内可被已知 email 字典试探（设计取舍：为可搜索性）；跨 workspace 不可关联。是否符合 Owner 威胁模型？

---

## 6. Owner-pending

- 明文 `email`/`contact_name` 列的最终处置（保留对账 vs 后续迁移密文化）？
- workspace-scoped HMAC 的可搜索性/抗枚举取舍是否接受？
- 是否需要 KMS 集成 + 访问留痕（audit log）作为生产批准前置？
