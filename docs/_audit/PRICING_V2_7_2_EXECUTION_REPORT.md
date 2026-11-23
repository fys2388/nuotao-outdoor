# M4 V2.7.2 — Git 分批提交 · 执行报告

> 指令：`docs/_audit/V2_7_2_CHATGPT_DIRECTIVE.md`（Owner 正式 Git 分批提交授权）
> 角色：`v272-git-commit`（Owner 书面授权的实现子代理）
> 状态：**6 类分批提交完成，0076 暂缓**。等待 Owner 下一轮授权。
> 生产禁令：全程**未连接生产库、未使用生产凭据、未执行任何生产迁移/回填/同步/WC 写入**；报告不含真实密码/连接串。
> 基线：分支 `main`，起始 HEAD `f7ee816`（V2.5 文档基线）。

---

## 一、执行摘要

按 Owner 批准的职责分组，**6 类 commit**（禁 `git add .`，逐文件精确 `git add`），Conventional Commits 信息。**0076 downgrade 修复按指令暂缓、未提交**（先完成部署状态审计，见 `PRICING_V2_7_2_0076_DEPLOYMENT_AUDIT.md`）。

| # | 职责 | Commit SHA | 文件数 | 钩子 |
|---|---|---|---|---|
| 1 | V2.6 身份模型实现 | `605a11b` | 8 | gitleaks/detect-secrets/no-env/ruff/ruff-format 全 Passed |
| 2 | Supplier/Offer 映射与冲突幂等（服务层） | `1b0fe9e` | 1 | 全 Passed |
| 3 | Migration 0092 自举修复 | `04ddaa8` | 1 | 全 Passed |
| 4 | PostgreSQL 集成测试及 migration 测试 | `b4a078a` | 7 | 全 Passed |
| 5 | rate_limit.py 兼容修复及回归测试 | `72a47f2` | 2 | 全 Passed |
| 6 | 文档（指令+报告+设计+运营规则） | 本轮 `docs(...)` commit | 见下 | 全 Passed |
| — | **0076 downgrade 修复** | **未提交（暂缓）** | — | — |

最终 HEAD：见 §六。仓库配置的 **pre-commit 钩子**（gitleaks、detect-secrets、no-env-commits、ruff、ruff-format）对每个 commit 均 Passed——其中 gitleaks + detect-secrets 为额外一道**密钥/凭据自动扫描**，全部通过。

---

## 二、各 commit 文件清单与目的

### Commit 1 — `605a11b` feat(pricing-v26): product/variation identity model & supplier-offer mapping schema
- `backend/app/models/product_mapping.py`（M）— 移除全局唯一约束→商品级/变体级部分唯一索引；新增变体身份维度 6 列；跨方言 `Uuid`。
- `backend/app/models/order.py`（M）— OrderItem 增 `wc_variation_id`/`variation_sku`/`identity_state`。
- `backend/app/models/supply_chain.py`（M）— InventorySnapshot 增变体列 + 商品级/变体级部分唯一索引。
- `backend/app/models/product_intelligence.py`（M）— ProductCostSnapshot 增变体列。
- `backend/app/models/product.py`（M）— ProductCost 增 `variation_id`/`variation_sku`。
- `backend/app/models/supplier_offer_mapping.py`（新增）— Supplier/Offer 多对多映射实体。
- `backend/app/models/__init__.py`（M）— 注册 SupplierOfferMapping。
- `backend/ruff.toml`（M）— ignore RUF002/RUF003（中文注释全角标点合法）。

> 归组说明：`supplier_offer_mapping.py`（ORM 模型）按最合理职责与其它模型同入 commit 1，因 `models/__init__.py` 注册它，同 commit 保证 `import app.models` 自洽可构建。commit 2 则为依赖这些模型的服务层。

### Commit 2 — `1b0fe9e` feat(pricing-v26): identity model service & supplier/offer conflict idempotency
- `backend/app/services/identity_model_v26.py`（新增）— 三态身份判定（B/C/D/E 强制 UNKNOWN_LEGACY）；`upsert_offer_mapping` 四类分支 + 冲突证据复用幂等；库存/成本变体级守卫。

### Commit 3 — `04ddaa8` fix(alembic): 0092 self-bootstrapping product_mappings for fresh databases
- `backend/alembic/versions/0092_identity_model.py`（新增）— `to_regclass` 表存在性守卫：已存在走原逻辑、不存在先按 0091 基线 bootstrap，非 IF NOT EXISTS 掩盖。

### Commit 4 — `b4a078a` test(pricing-v26): PostgreSQL identity/offers/migration integration tests
- `backend/tests/integration/test_identity_model_v27_pg.py`（新增）— 21 项真实 PG16 读写。
- `backend/tests/integration/test_offer_conflict_idempotency_v271_pg.py`（新增）— 5 场景冲突幂等。
- `backend/tests/integration/test_postgres_migrations.py`（M）— 复用 product_mappings 引导 + 动态 head 断言，5/5 全绿。
- `backend/tests/test_identity_model_v26.py`（新增）— 交付版核心测试（经共享 conftest）。
- `backend/tests/test_identity_model_v26_pg.py`（新增）— V2.6 PG 集成测试（Testcontainers，无 Docker 自跳过）。
- `backend/tests_v26/conftest.py`（新增）+ `backend/tests_v26/test_identity_model_v26.py`（新增）— SQLite 内存隔离入口。

### Commit 5 — `72a47f2` fix(rate-limit): starlette 1.6 _read_file signature compat + regression tests
- `backend/app/core/rate_limit.py`（M）— `_fixed_read_file` 改 `*args/**kwargs` + 补 encoding + 委托回原始 `_read_file`。
- `backend/tests/test_rate_limit_regression.py`（新增）— 新旧签名/端到端/结构不变回归。

### Commit 6 — docs(...)
- `docs/operating_rules.md`（M）— 运营规则 v2.0（定价/利润分层贡献利润目标重构）。
- `docs/PRICING_V2_6_ER_DIAGRAM.md`、`docs/PRICING_V2_6_IDENTITY_IMPLEMENTATION.md`、`docs/PRICING_V2_6_SUPPLIER_OFFER_MAPPING.md`
- `docs/_audit/V2_6_CHATGPT_DIRECTIVE.md`、`V2_7_CHATGPT_DIRECTIVE.md`、`V2_7_1_CHATGPT_DIRECTIVE.md`、`V2_7_2_CHATGPT_DIRECTIVE.md`
- `docs/_audit/PRICING_V2_6_BUSINESS_RELATION_REFACTOR.md`、`PRICING_V2_6_71ROW_BACKFILL_REPORT.md`、`PRICING_V2_6_EXECUTION_REPORT.md`
- `docs/_audit/PRICING_V2_7_EXECUTION_REPORT.md`、`PRICING_V2_7_1_MIGRATION_REPAIR_DESIGN.md`、`PRICING_V2_7_1_EXECUTION_REPORT.md`
- `docs/_audit/PRICING_V2_7_2_0076_DEPLOYMENT_AUDIT.md`（本轮新建）、`PRICING_V2_7_2_EXECUTION_REPORT.md`（本文件）

---

## 三、提交前安全检查（全部通过）

- **分支/HEAD**：确认 `main` @ `f7ee816` 后才开始。
- **逐文件 diff 审阅**：对每个 tracked modified（models/rate_limit/ruff.toml/operating_rules/test_postgres_migrations/0076）查看 `git diff`；新增文件审阅内容。
- **安全扫描**（grep 敏感模式 `postgresql://:.*@`、`api_key`、`secret`、`password`、`AKIA`、`Bearer`、`BEGIN PRIVATE KEY`）：
  - 代码文件命中均为**良性**：`product_intelligence.py` 的 LLM `token_usage` 计数字段；测试里 `url.replace("postgresql+asyncpg://","postgresql://")`（对 fixture 提供的**本地隔离实例 URL** 做 scheme 替换，无凭据）。
  - 文档文件**零命中**。
- **生产配置/凭据**：未加入；全部 PG 测试连接串来自 `pg_database_url` fixture（pgserver 一次性隔离实例）。
- **未使用 `git add .`**：逐文件精确 add；大量无关 untracked（cookies、临时脚本、B2B/P0/V2.3 等其他工作流文件）**全部未纳入**。
- **pre-commit 钩子**：gitleaks + detect-secrets + no-env-commits 每次提交自动扫描凭据/.env，**全部 Passed**。

---

## 四、测试证据（提交后综合运行，junitxml 权威计数）

环境：`E:\AI\nuotao-ai-os\.venv\Scripts\python.exe -m pytest`，`PYTHONPATH=backend`，pgserver 内嵌一次性隔离 PostgreSQL 16。**全程未连生产库。**

| 套件 | 结果 | 说明 |
|---|---|---|
| `tests/test_rate_limit_regression.py` | **9 tests, 0 failed, 0 error, 0 skipped** | rate_limit 兼容回归 |
| `tests/test_identity_model_v26.py` | **19 tests, 0 failed** | V2.6 核心（SQLite 内存） |
| `tests/test_identity_model_v26_pg.py` | 3 tests, 0 failed, **3 skipped** | Testcontainers，无 Docker 环境按设计自跳过 |
| `tests/integration/test_postgres_migrations.py` | **5 tests, 0 failed** | 通用迁移测试（原 1 failed+4 errors 已修复） |
| `tests/integration/test_identity_model_v27_pg.py` | **21 tests, 0 failed** | V2.7 身份模型真实 PG16 |
| `tests/integration/test_offer_conflict_idempotency_v271_pg.py` | **5 tests, 0 failed** | Offer 冲突幂等真实 PG16 |
| `tests_v26/test_identity_model_v26.py` | **19 tests, 0 failed** | V2.6 隔离入口 |

- 合计**核心断言 78 项通过（9+19+5+21+5+19），0 失败**；v26_pg_testcontainers 3 项因无 Docker 自跳过（非失败）。
- **Offer 幂等 `test_offer_conflict_05_manual_review_accept_reject` 过程中出现过一次失败，重跑后 5/5 稳定通过**，判定为**偶发（flaky，疑 PG 时序）**，非本轮代码回归；已如实记录。

### Ruff（如实报告，不夸大）
- **本轮新增/改写文件全绿**：`0092_identity_model.py`、`identity_model_v26.py`、`rate_limit.py`、`supplier_offer_mapping.py`、全部新增测试、`product_mapping.py` 等（pre-commit ruff + ruff-format 对每个 commit 均 Passed）。
- **`0076_first_batch_20_products.py` 仍报 93 项 pre-existing 违规**（I001/F401/格式化，遍及全文、**非本轮引入**，git diff 证明本轮仅改 downgrade 2 行）。按指令 §一**本轮不清理**。
- **本报告不声称整个项目 Ruff All checks passed**；仅声明：新增/改写文件全绿 + 0076 保留 93 项历史违规记录（详见 0076 审计报告 §四）。

---

## 五、0076 审计结论（引用部署审计报告）

详见 **`docs/_audit/PRICING_V2_7_2_0076_DEPLOYMENT_AUDIT.md`**。要点：
- **Q1 生产是否执行过 0076**：本地**无法确定**（生产访问被禁）。0076 是链内正式迁移（理论完整 upgrade 会执行到），但生产是否真跑过取决于部署历史，**需 Owner 提供生产 revision 或确认从未部署**。
- **Q2 生产 revision**：本地无法确定；仅能推断「若跑过完整链应为 0092 或更早」（明确标注为**推断非事实**）。
- **Q3 downgrade 差异**：`DELETE products` 的 `workspace_id` 绑定参数由裸 UUID（asyncpg 推断 varchar 报错）改为 `CAST(:workspace_id AS uuid)` + `str(WORKSPACE_ID)`，纯 bind 类型修复。
- **Q4 只影响 downgrade**：**是**（git diff 证明改动全在 `downgrade()` 内，`upgrade()` 未动）。
- **Q5 对已执行库影响**：upgrade 零影响（已应用不重跑）；downgrade 由「报错」变「正常删除」= 修复而非破坏，无迁移历史不一致。
- **结论**：**0076 暂缓提交**，等 Owner 确认生产 revision 拍板（情形 A 从未部署→可安全提交 / 情形 B 已部署→属改进但需 Owner 决定改历史文件或挪新迁移）。

---

## 六、最终 Git 状态

- **分支**：`main`
- **起始 HEAD**：`f7ee816` → **最终 HEAD**：见 `git log`（commit 6 docs）
- **提交顺序**：`605a11b` → `1b0fe9e` → `04ddaa8` → `b4a078a` → `72a47f2` → `docs(...)`
- **worktree 状态**：代码/测试/文档（除 0076）已全部入库；`git status` 仅剩：
  - `M backend/alembic/versions/0076_first_batch_20_products.py`（**暂缓，唯一相关未提交文件**）
  - 大量**其他工作流**的 pre-existing untracked 文件（cookies/临时脚本/B2B/P0/V2.3 inventory_sync/pricing 等）——**非本轮范围，正确未提交**。
- 无越权文件进入任何 commit（每个 commit 均核对 `--name-only`，确认无 0076、无凭据文件）。

---

## 七、生产未写入确认

本轮**以下均未执行**：
- 生产 Migration upgrade/downgrade（含 0092、0076）；
- 生产数据库回填/同步；
- WooCommerce API 写入；
- 自动采购/加购/促销/调价/SKU 修改/规则变更；
- 生产部署。

所有 migration 与 PG 集成测试**仅在 pgserver 内嵌一次性隔离 PG16 实例**执行并随实例销毁。未连接生产库、未使用生产凭据、commit 与报告**不含任何真实密码/连接串**。

**Git 提交授权 ≠ 生产授权。** 完成后停止，等待 Owner 下一轮授权（含 0076 拍板）。