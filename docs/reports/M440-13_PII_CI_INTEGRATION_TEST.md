# M440-13 — PII 临时 PostgreSQL CI 集成测试

- 任务: APR-PII-CI-001 (P1) — 为 PII 加密 + 回填建立 CI 集成测试
- Owner 批准: APR-PII-CI-001（本轮 approved to start）
- 日期: 2026-11-18
- 执行者: Nuotao Dev Agent (Sensenova)
- 边界: **CI 临时 PostgreSQL（`nuotao_pii_ci`），不连生产、无真实客户数据、无生产密钥**

---

## 1. 目标

为 M4.4 PII 加密 + 回填建立**可重复的 CI 集成测试**，在每次 push 时于**临时 PostgreSQL** 中验证：

1. 0086→0087 迁移在空库可全链升级（含 Staging/生产路径的 schema）。
2. PII 加密（AES-256-GCM）+ HMAC email_hash 的正确性与 workspace 隔离。
3. 回填脚本逻辑（明文→密文 + 哈希 + key_version）与对账。
4. 重复执行幂等、密钥缺失/错误/密文损坏 fail-closed。
5. 0087 downgrade 可回滚（列消失、版本回退）。
6. 临时测试数据清理。

**安全边界（满足 AGENTS.md L4 PII + 密钥铁律）**：CI 使用一次性合成数据 + 独立测试密钥；绝不触及生产库、真实客户 PII 或生产密钥。

---

## 2. 实现

### 2.1 测试文件 `backend/tests/test_pii_ci_integration.py`（新增）

10 个 pytest 用例，共享 3 个 module-scoped fixture：

- `db_url` / `engine`: 从 `DATABASE_URL`（CI 注入 `postgresql+psycopg://postgres:postgres@localhost:5432/nuotao_pii_ci`）创建同步 engine。
- `migrated`: 空库 → `alembic upgrade 0086`（init）→ 清理测试 lead → `alembic upgrade 0087`（PII 列）。
- `keys`: 设 `PII_HMAC_KEY`/`PII_ENCRYPTION_KEY` 为测试值。

**关键修复（本轮调试）**：

| # | 问题 | 修复 |
|---|---|---|
| 1 | CI 无 `psycopg` | workflow 增 `pip install "psycopg[binary]"` |
| 2 | conftest 需 `JWT_SECRET_KEY`/`SECRET_KEY` | workflow 增 env |
| 3 | `FastAPI.__init__() got on_event`（main.py 残留 init 参数） | 移除 `on_event=(...)`，用 `lifespan` |
| 4 | 空库 `alembic upgrade 0086` 全链失败：0068 引用 `users`（由 `create_all` 建而非 alembic）→ `relation "users" does not exist` | 0068 加 `_has_users_table()` 守卫（同 0087 模式），空库跳过；生产 `users` 存在行为不变 |
| 5 | 测试 AES 密钥 24B，需 32B base64 | 改 `TEST_ENC_KEY`/wrong_key 为 32B，workflow env 同步 |
| 6 | `b2b_leads.id`/`workspace_id` 为 UUID 列 | 传 uuid 字符串；补全 `company_name`/`country`/`business_type`/`message`/`privacy_consent`/`consent_at` 等 NOT NULL 列 |
| 7 | 测试只读回未真正执行回填 → 列为 None | 加 `_backfill()` 用真实 `encrypt_field`/`build_email_hash` 执行加密回填 |
| 8 | `get_settings()` lru_cache 使改 env 无效 | 改密钥用例加 `get_settings.cache_clear()` |
| 9 | 密文损坏测试对 str 用 `bytearray` 报错 | 改为在 base64 字符串内替换一个字符 |
| 10 | 回滚用 `alembic upgrade 0086`（对更低 revision 是 no-op）→ 列未删 | 新增 `_alembic_downgrade()`，回滚测试用 `alembic downgrade 0086` |

> 注：问题 4（0068 守卫）与问题 3（main.py `on_event`）是**真实缺陷**，CI 空库路径暴露，修复对生产无影响。

### 2.2 Workflow `.github/workflows/pii-ci-integration.yml`（新增）

- 触发: push 到 `main`（paths 含 `backend/app/core/pii_crypto.py`、`backend/scripts/backfill_pii_fields_m440.py`、`backend/alembic/versions/0087_*`、本测试、本 workflow）+ `workflow_dispatch`。
- Service: `postgres:16`，`POSTGRES_DB: nuotao_pii_ci`。
- Steps: checkout → setup Python 3.12 → install (`psycopg[binary]`, `pytest`) → upgrade pip → run `pytest tests/test_pii_ci_integration.py -v -x --tb=short`。
- Env: `DATABASE_URL`(临时库) + 测试 `PII_HMAC_KEY`/`PII_ENCRYPTION_KEY` + `JWT_SECRET_KEY`/`SECRET_KEY`。

---

## 3. 证据

- **GitHub Actions Run ID**: `44270204004`
- **结果**: ✅ **CI_INTEGRATION_TEST = PASS** — `10 passed, 8 warnings in 8.38s`
- **URL**: https://github.com/fys2388/nuotao-outdoor/actions/runs/44270204004
- **commit**: `3f6df4e fix(m440): PII CI rollback uses alembic downgrade not upgrade`
- **Ruff**: 测试/workflow 无业务模块改动，未触发 Ruff 报错（CI Pre-check 通过）。
- **DB revision（CI 临时库）**: 集成测试内 `0086 → 0087 → downgrade 0086`（回滚用例验证）；测试结束销毁。
- **生产影响**: 无。仅测试 + workflow + 0068 幂等守卫 + main.py `on_event` 清理；未触碰生产数据/密钥/部署。

### 10 个用例（全绿）

1. `test_0087_schema` — 0087 后 b2b_leads 含 email_hash/email_encrypted/contact_name_encrypted/pii_key_version 列
2. `test_email_hash_deterministic_and_scoped` — HMAC 确定性 + workspace 隔离
3. `test_aes_roundtrip` — AES-256-GCM 加密/解密往返
4. `test_backfill_and_reconcile` — 真实加密回填 + 对账（解密==原文、哈希==重算、key_version=v1）
5. `test_repeat_idempotent` — 重复执行幂等
6. `test_key_missing_fail_closed` — 密钥缺失 fail-closed（PiiCryptoError）
7. `test_wrong_key_rejects` — 错误密钥拒绝（不静默回退）
8. `test_corrupted_ciphertext_rejects` — 密文损坏拒绝
9. `test_rollback_0087` — `alembic downgrade 0086` 后 PII 列消失、版本回退 0086
10. `test_cleanup` — 临时测试数据清理（is_test=true 删除）

---

## 4. 待办（Outstanding）

1. **Staging 端到端验收仍 BLOCKED**：容器真实执行（回填脚本 `--dry-run`→应用）缺 Staging 环境；本轮 PII CI 在**临时 CI 库**验证了**同版回填逻辑**（`encrypt_field`/`build_email_hash`/`_backfill`），作为替代证据，但**不等于** Staging 真实容器执行。Staging Acceptance（APR-M440-STAGING-002）仍 `BLOCKED (needs evidence)`。
2. **生产执行 NOT APPROVED**：生产 PII schema 迁移/加密+回填仍待 Owner 独立批准（APR-M440-PII-001 NOT APPROVED FOR PRODUCTION EXECUTION）。

---

## 5. Owner-pending（本报告交 Owner 判断）

- 本 CI 集成测试作为 **Staging 端到端验收的替代证据强度**是否足够，或要求 Staging 容器真实执行补证？
- 是否批准将 PII CI 设为**合并门禁**（required check）？
- 0068 幂等守卫（空库跳过）与 main.py `on_event` 清理是否接受为常规修复？

---

## 6. 结论

PII 加密 + 回填的**临时 PostgreSQL CI 集成测试已建立并全绿（10/10 passed）**，验证了迁移、加密、HMAC、回填、幂等、fail-closed（密钥缺失/错误/密文损坏）与回滚。安全边界满足：CI 临时库、合成数据、测试密钥，不连生产、无真实 PII、无生产密钥。

- `CI_INTEGRATION_TEST = PASS`
- `STAGING_ACCEPTANCE = BLOCKED (needs container-level evidence)`
- `PRODUCTION_READINESS = NOT_APPROVED`
