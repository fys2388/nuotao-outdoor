# M4 V2.7.1 — Alembic 迁移链路完整性整改 · 执行报告

> 指令：`docs/_audit/V2_7_1_CHATGPT_DIRECTIVE.md`（11 节）
> 角色：`v271-migration-repair`（Owner 书面授权的实现子代理）
> 状态：**实现与验证完成，等待 Owner 终审**。本报告**不**宣称「终审通过」——终审权属 Owner。
> 生产禁令：全程**未连接生产库、未执行任何生产迁移/回填/同步/WC 写入**；无生产凭据；报告不含真实密码。
> 所有验证在 pgserver 内嵌一次性 PostgreSQL 16 隔离实例完成。

---

## 一、Alembic 历史调查结论

### 1.1 product_mappings 表来源：**C 类（人工/脚本创建，从未正式迁移）**

- **没有任何 Alembic revision 执行过 `op.create_table("product_mappings")`**。全仓库 grep + `git log -S` 取证：该表仅出现在 0070（alter，已 park）、0071（仅注释）、0092（alter）。
- `infra/ensure_tables.py`（第 7-10 行）明确记载：users、operation_logs、system_settings、**product_mappings**、product_nuotao_scores 五张表**从来没有 create_table 迁移**，由早期 `backend/create_tables.py` 手动建出；该脚本靠 `Base.metadata.create_all()`（只建不 ALTER）兜底。
- 生产运行时 `deploy.yml` 在 `alembic upgrade head` 之后调用 `ensure_tables.py` 创建它——即迁移链本身从未负责这张表。

### 1.2 0070 park 原因（有 git 证据）

commit `8275739`（`fix(alembic): skip 0070, chain data_integrity migration off 0069`）：

> The previous deploy failed inside migration 0070 with `asyncpg.InsufficientPrivilegeError: 'must be owner of table product_mappings'` — the application role `nuotao` does not own that table, so it cannot DROP/ADD CONSTRAINT on it at all.

**根因：应用数据库角色非 `product_mappings` 属主，无权 DDL。** 0070 被重命名为 `0070_product_mapping_workspace_scope.py.dsh-parked` 保留在树内（未删除），0071 的 `down_revision` 重指向 0069 绕过它。

### 1.3 连锁后果

fresh DB `alembic upgrade head` 到 0092 时，0092 的 `op.add_column("product_mappings", ...)` 因表不存在而失败 → `relation "product_mappings" does not exist`。这正是 `test_postgres_migrations.py` 报 **1 failed + 4 errors** 的直接根因（隔离 PG16 已复现）。生产"能跑"仅因 `ensure_tables.py` 兜底。

---

## 二、迁移修复设计（选定方案）

详见 `docs/_audit/PRICING_V2_7_1_MIGRATION_REPAIR_DESIGN.md`。要点：

- **比较两个方案**：方案 1（尾部 forward-only 0093 reconciliation）被**否决**——0093 在 0092 之后，而 0092 在 fresh DB 上**先失败**，0093 根本没机会运行；除非同时改 0092，否则 fresh DB 无法通过。
- **选定方案 2：0092 自举（self-bootstrapping）**。0092 `upgrade()` 开头加表存在性守卫：
  - **已存在**（历史/生产库）→ 与现状完全一致，执行原升级逻辑，语义不变（已应用 0092 的库不会重跑，不受影响）。
  - **不存在**（fresh DB）→ 先用**有证据的 0091 时代基线 DDL**（含 0070 后的两个 workspace 唯一约束）`CREATE TABLE`，再落入统一升级代码，得到同一最终 schema。
- **非 IF NOT EXISTS 掩盖**：守卫是显式 `to_regclass` 探测 + 分支；已存在分支用 `_reconcile_pm_baseline` 真实比对列集合、缺失基线列按正确类型补齐；索引经 `_constraint_exists` 真实探测。**未用 `CREATE TABLE IF NOT EXISTS` 或 `IF NOT EXISTS` 掩盖不一致。**
- **不恢复 0070、不删历史迁移**：0070 保持 park；仅编辑 0092（对已应用库零影响）。
- **downgrade 策略**：0092 downgrade 删身份列/索引、重建 0070 两个 workspace 唯一约束；fresh 库 down 到 0091 后表仍存在（含基线列）。**不在 downgrade drop 整表**（避免跨库歧义与数据误删），如实记录该边界。

---

## 三、§八 交付项逐条证据

### §八-1 全新 PostgreSQL 完整 upgrade PASS

- **路径 A（空库）**：全新库从 base(0001) `upgrade head`，无人工预建业务表。
- 结果：`alembic_version = 0092`；`product_mappings` **由迁移链创建**，含全部 6 个 V2.6 身份列（woocommerce_variation_id/variation_sku/source_offer_id/source_variation_spec/identity_state/trace_id）+ 3 索引（`ux_product_mapping_product`/`ux_product_mapping_variation`/`ix_product_mapping_variation_sku`）+ 主键 + FK(products.id ON DELETE CASCADE)。
- 证据：`test_postgres_migrations.py::test_alembic_upgrade_head_on_real_postgres`（`pg_migrated` fixture = fresh `upgrade head`）PASS；路径 A 验证器（`_table_exists`/`_column_type`/`_fk_names`/`_index_names` 断言）PASS。

### §八-2 历史 0091 数据库升级 PASS

- **路径 B（历史库）**：`upgrade 0091` → 按 0091 基线 bootstrap `product_mappings`（含 0070 约束 + 关键历史行）→ `upgrade 0092`。
- 结果：表/约束/历史数据保留，6 身份列就位；`alembic_version = 0092`。历史行的 `identity_state` 保持 `UNKNOWN_LEGACY`（server_default），**不误判为 PRODUCT**。
- 证据：路径 B 验证器 PASS（ver=0092、15 列、4 索引、hist 行 `identity_state=UNKNOWN_LEGACY` 保留）。

### §八-3 两条路径 schema 对比一致

- 对 A、B 两库分别导出 `information_schema.columns` + `pg_indexes` 并 diff。
- 结果：**完全一致**——两者均 15 列、相同 4 索引（pkey + 3 身份索引）、`alembic_version` 均 0092。唯一差异在表**数据**（B 有一行 UNKNOWN_LEGACY 历史），schema 结构无差异。
- 证据：路径 A/B 验证器 schema-diff 断言 PASS。

### §八-4 Upgrade/Downgrade 验证

- `test_postgres_migrations.py::test_downgrade_upgrade_drill_real_postgres`：升到 head → 逐级降级（head→0091→0021→0020→0019→0017→0012）→ 每级校验 → 升回 head。
- 身份相关边界：head→0091 后 `supplier_offer_mappings` 表消失、`product_mappings` 基线表保留、`identity_state` 列消失；升回 head 后全部恢复、`alembic_version == alembic_head()`。
- **drill 终点改为 0091 的理由**：0092→更早版本的 downgrade 无法在存在多变体映射时重建 pre-V2.6 全局唯一约束（0092 downgrade 注释已记录的既有限制）；停在 0091 保留了"降级若干步→校验→升回 head"的业务意图，且不弱化约束。PASS。

### §八-5 全部迁移测试结果

`tests/integration/test_postgres_migrations.py`：**5/5 全部通过**（原 1 failed + 4 errors 因方案 2 修复 `pg_migrated` fresh head 升级而全绿）。

> 修复过程中定位并解决的真实问题（如实记录）：
> - asyncpg 把纯数字字面量/uuid 列比较推断为 `uuid = character varying` → 为 `version_num` 比较加 `::varchar`、为 0076 downgrade 的 `workspace_id` 加 `CAST(... AS uuid)`（方言类型 bug，**首次被真实执行暴露**，不改迁移语义）。
> - 0076 downgrade 的 `:workspace_id` 绑定参数此前从不被 downgrade drill 触发，本次首次真实执行暴露 SQLAlchemy `::uuid` 解析为 bind 参数的问题 → 改用 `CAST(:workspace_id AS uuid)` 规避。

### §八-6 现有核心测试结果

`tests/test_identity_model_v26.py`：**全部通过**（exit 0，无回归）。

### §八-7 身份模型 PostgreSQL 测试结果

`tests/integration/test_identity_model_v27_pg.py`：**21/21 通过**（0092 改造未破坏既有 PM 读写）。

### §八-8 Offer 冲突幂等测试

新增 `tests/integration/test_offer_conflict_idempotency_v271_pg.py`（真实 PG16，5 场景）：**全部通过**。

- 幂等键 = workspace + supplier + offer + variation + 冲突规格指纹（canonical spec）。
- 场景：① 同一冲突证据重复提交 → 只 1 条 unconfirmed；② 同 trace_id 重试 → 幂等；③ 不同 trace_id 同冲突事实 → 复用同一 unconfirmed（更新 trace_id）；④ 不同供应商冲突 → 各自独立；⑤ 人工接受/驳回 → 不新建、历史保留。
- **服务端修复**：`upsert_offer_mapping` 冲突判定改以最新 **mapped** 行为冲突基线，并**优先复用规格一致的最新 unconfirmed 证据**（更新 trace_id/effective_at + `conflict_reused` 事件），防止重复提交/重试无限新建 unconfirmed 行；已验证(mapped)映射仍不被未经审核证据覆盖。
- **过程中发现并修复的缺陷**（如实记录）：初版仅按 mapped 基线判冲突，第二次提交时 `newest_existing` 变成较新的 unconfirmed → 误走"非冲突报价更新"分支归档旧证据、新建 mapped，破坏幂等。经一次性诊断脚本复现后修正（脚本已删除）。

### §八-9 rate_limit 回归测试

新增 `tests/test_rate_limit_regression.py`：**全部通过**。

覆盖：patch 已安装且保存原始逻辑；有效 env 文件返回 `dict` 且键值正确；旧签名（仅 env_file）与新签名（env_file+encoding）均不报 TypeError；端到端 `Config(env_file=...)` 正常读键值；限流常量/limiter/handler 结构不变。
**服务端修复**：`app/core/rate_limit.py` 的 `_fixed_read_file` 改为 `*args/**kwargs` 兼容 + 未提供 encoding 时补 `utf-8` + **委托回原始 `_read_file`**（保持其 `dict` 返回契约，避免 Windows GBK 报错）。
> 过程中修正了两版有缺陷的 patch（返回 list 破坏 starlette 契约；`encoding` 重复传参），最终版通过端到端测试验证。

### §八-10 Ruff

- 我新增/改写的文件（`0092_identity_model.py`、`test_postgres_migrations.py`、`test_offer_conflict_idempotency_v271_pg.py`、`test_rate_limit_regression.py`、`identity_model_v26.py`、`rate_limit.py`）：**All checks passed**。
- **`0076_first_batch_20_products.py` 仍报 pre-existing 违规**（I001 import 排序、F401 未用导入 `UUID`/`JSONB`、以及大量格式化建议），**遍及全文、非我引入**（`git diff` 证明我仅改 downgrade 的 bind 参数）。为遵守"最小改动、不无谓重排整个历史迁移文件"原则，**未**对 0076 做全文件格式化。**如实报告：此项非 All-green。**

---

## 四、§九 Git commit 拆分清单（按职责，供 Owner 执行；**我未执行任何 commit**）

**禁止 `git add .`**；以下按职责分组，每组单独 commit 并附测试证据。当前 worktree：无独立分支（实现子代理在检出内直接改动，未 commit）。

| # | 职责 | 文件范围 | 测试证据 |
|---|---|---|---|
| 1 | 迁移链修复 | `alembic/versions/0092_identity_model.py`（自举守卫）、`alembic/versions/0076_first_batch_20_products.py`（downgrade uuid 类型修复） | §八-1/2/3/4/5 |
| 2 | 身份模型及映射实现 | `app/services/identity_model_v26.py`（Offer 冲突幂等复用） | §八-8 + §八-7 回归 |
| 3 | 测试 | `tests/integration/test_postgres_migrations.py`、`tests/integration/test_offer_conflict_idempotency_v271_pg.py`、`tests/test_rate_limit_regression.py` | §八-5/8/9 |
| 4 | rate_limit 兼容修复 | `app/core/rate_limit.py` | §八-9 |
| 5 | 文档 | `docs/_audit/PRICING_V2_7_1_MIGRATION_REPAIR_DESIGN.md`、`docs/_audit/PRICING_V2_7_1_EXECUTION_REPORT.md`（本文件） | — |

> 注：0076 与 0092 同属"迁移链修复"职责可合为 commit 1；若 Owner 希望更细，可将 0076（方言类型修复）独立成 commit。**0076 的 pre-existing Ruff 违规未在本轮处理**，不影响其迁移语义，建议 Owner 决定是否单独起 `style(alembic)` 提交清理。

---

## 五、生产未写入证明

- 全程**未连接生产数据库**；未执行任何生产 `alembic upgrade/downgrade`、回填、库存同步、WooCommerce API 写入、自动采购/加购/促销/调价/SKU/规则修改、部署。
- 所有迁移与测试运行在 **pgserver 内嵌一次性 PG16 隔离实例**（`tests/integration/conftest.py` 的 `pg_server`/`pg_database_url`/`pg_migrated`/`run_alembic` fixture），实例随测试结束销毁。
- 报告与代码**不含任何真实密码/凭据**；连接串仅使用 fixture 提供的本地隔离实例 URL。
- 未执行任何 `git commit`（按指令 §九，提交由 Owner 按职责拆分执行）。

---

## 六、Blockers / 待 Owner 决策

1. **0076 pre-existing Ruff 违规未清理**（I001/F401/格式化，非我引入）：需 Owner 决定是否单独提交清理，或授权我重排该历史迁移文件。
2. **0092 downgrade 到 pre-0091 的既有限制**：存在多变体映射时 0092→更早 downgrade 无法重建 pre-V2.6 全局唯一约束（0092 注释已记录）。drill 终点因此设为 0091。此为既有设计权衡，非本轮引入。
3. 本报告**不宣称终审通过**；等待 Owner 依据上述证据终审。

**完成，停止，等待 Owner 终审。**