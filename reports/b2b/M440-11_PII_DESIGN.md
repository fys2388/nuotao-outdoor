# M440-11 PII 加密设计报告（APR-M440-PII-001 — 设计 / Staging 验证阶段）

> 日期：2026-11-18
> 状态：**设计 + 代码 + 单元测试已交付；Staging 迁移/回填验证待执行（NEEDS_EVIDENCE）**
> Owner 边界：本轮**禁止**触碰生产 PII、禁止生产回填、禁止删除明文字段、禁止修改生产密钥、禁止生产 PII schema 迁移。

---

## 0. 摘要

| 项 | 状态 |
| --- | --- |
| 加密架构设计 | ✅ 本文档（11 项要求全覆盖） |
| 加密原语实现 | ✅ `backend/app/core/pii_crypto.py`（HMAC-SHA-256 + AES-256-GCM） |
| 单元测试 | ✅ `backend/tests/test_pii_crypto.py`（9 用例，含错误密钥/缺钥/畸形密文） |
| Staging 迁移 + 回填验证 | ⏳ 待执行（NEEDS_EVIDENCE，需 staging 库访问） |
| 生产 PII 迁移 | 🚫 未获批准，本轮零改动 |

---

## 1. 加密架构（对应 Owner 11 项要求）

### 1.1 email_hash（Owner 要求 1：HMAC-SHA-256 + 密钥分离）

- **算法**：`HMAC-SHA-256(pii_hmac_key, "{workspace_id}:{normalize_email(email)}")` → hex（64 字符）。
- **规范化**：`normalize_email` 先 `strip()` 再 `casefold()`（大小写/空格不敏感），`@` 校验。
- **密钥分离**：`pii_hmac_key` 独立于既有 `customer_identity_hmac_key`，PII 检索摘要不可跨域复用，可独立轮换。
- **用途**：`email_hash` 唯一索引 → 等值检索（登录/去重/匹配），**不用明文查库**。
- **确定性**：同邮箱 + 同 workspace → 同 hash（可建唯一索引）。

### 1.2 email_encrypted（Owner 要求 2：AES-256-GCM 信封加密）

- **算法**：AES-256-GCM，`base64(iv(12B) || ciphertext || tag(16B))`，无 AAD。
- **密钥**：`pii_encryption_key`（base64、32 字节），环境变量注入，**不落库、不入 Git**。
- **信封**：记录内只存密文 + `pii_key_version`；DEK 由 KEK（环境/KMS）派生，可插拔 `KeyProvider`（后续接 KMS）。
- **IV**：每次 `os.urandom(12)`（随机，同明文两次密文不同）。

### 1.3 contact_name 加密（Owner 要求 3）

- `contact_name_encrypted` 与 `email_encrypted` 同用 `pii_crypto.encrypt_field/decrypt_field`（AES-256-GCM，独立列）。
- 联系人姓名是个人信息，与邮箱同等保护。

### 1.4 双读写过渡（Owner 要求 4）

- **过渡期**：`email`（明文）+ `email_hash` + `email_encrypted` 共存。
- **读**：优先密文（有 `email_encrypted` 用密文解密）；无则回退明文（迁移期）。
- **写**：双写（明文 + hash + 密文），保证任意时刻可读。
- **退役**：回填校验通过后，`email` 明文由回填脚本置 NULL/删除（仅 Staging 验证后决定，生产未批）。

### 1.5 历史回填与对账（Owner 要求 5）

- 回填脚本：读每条 Lead 明文 `email`/`contact_name` → 写 `email_hash`/`email_encrypted`/`contact_name_encrypted` → 复核（解密 == 原文）→ 记录 `pii_backfill` 审计事件。
- **Staging 验证**：staging 库执行迁移 + 回填 + 对账；生产不执行。

### 1.6 重复邮箱 / 规范化处理（Owner 要求 6）

- 唯一索引建在 `email_hash`（不是明文）→ 大小写/空格天然归一。
- 历史重复/冲突：`email_hash` 冲突时记录冲突事件并保留既有记录，人工裁决；**不自动覆盖**。
- 空值/历史空 email：跳过（hash/encrypted 均为 NULL）。

### 1.7 Admin 解密权限矩阵（Owner 要求 7）

| 操作 | 角色 | 行为 |
| --- | --- | --- |
| 列表/导出 | `operator` | 脱敏（`a***@domain`），不解密 |
| 详情解密 | `operator` + 明确动作 | 解密并写 `pii_decrypted` 审计事件 |
| 检索 | `operator` | 按 `email_hash` 等值，不用明文 LIKE |
| 通知/外部 | 禁止 | 不自动发邮件；未经批准不发 |
| 日志/提示词 | 禁止 | 明文 PII 禁止入日志/Agent 上下文 |

### 1.8 密钥轮换 / KMS 故障 / 恢复（Owner 要求 8）

- 轮换：新增密钥版本 → `pii_key_version` 增量 → 分批重加密（`email_encrypted` 用新 DEK）→ 旧版本退役。
- KMS 不可用：加密写失败即抛错（不写不可读数据）；解密失败记录 `pii_decrypt_failed` 事件，不落日志明文。
- 恢复：密钥由环境/KMS 恢复，密文可解；无需明文副本。

### 1.9 备份/恢复兼容（Owner 要求 9）

- 备份为密文（`email_encrypted`），不额外泄露明文；`email_hash` 单向。
- 恢复后需可用 KEK（环境/KMS）解密密文；无明文依赖。

### 1.10 回滚 / 明文退役（Owner 要求 10）

- 回滚：`email_hash`/`email_encrypted`/`contact_name_encrypted` 列 DROP（保留明文 `email`/`contact_name`）→ 回到现状。
- 明文退役：仅当 Staging 回填 + 对账 + 权限评审全部通过，且另获 Owner 批准后才执行（生产未批）。

### 1.11 Staging 测试 + 安全评审（Owner 要求 11）

- ⏳ **待执行**：staging 库应用迁移（0087）+ 回填脚本 + 对账 + 回滚演练。
- 安全评审：密钥不入库/不入 Git（`pii_hmac_key`/`pii_encryption_key` 仅 Secrets）；日志脱敏；审计事件落库。

---

## 2. 边界确认

- ✅ 本模块为**纯函数原语**（无 DB 访问、无网络），`app/core/pii_crypto.py`。
- ✅ **未触碰生产 PII**：未改生产数据、未跑生产回填、未删明文字段、未改生产密钥、未做生产 PII schema 迁移。
- ✅ 密钥**不提交仓库**（config 默认空；生产缺失即硬失败 `PiiCryptoError`）。

## 3. 待后续（向 Owner 申请下一步）

1. **Staging 验证**：迁移 0087（新列 `email_hash`/`email_encrypted`/`contact_name_encrypted`/`pii_key_version`）+ 回填脚本 + 对账 + 回滚演练 → 提供结果。
2. 之后才向 Owner 申请生产 PII 迁移批准（**本次不申请**）。
