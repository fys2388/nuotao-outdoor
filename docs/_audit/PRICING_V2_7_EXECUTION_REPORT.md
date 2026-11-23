# M4 V2.7 PostgreSQL 数据库集成验证与 Migration 0092 安全验收执行报告

> 版本：v2.7.0 | 执行人：`v27-pg-verify`（子代理）| 日期：2026-11-23
> 指令：`docs/_audit/V2_7_CHATGPT_DIRECTIVE.md`（Owner 书面授权）
> 范围：**仅真实 PostgreSQL 环境验证 Migration 0092 + 三态身份/Supplier-Offer 数据库约束**。生产目标 PostgreSQL 16。

## 0. 结论摘要

| 项 | 结果 |
|---|---|
| 隔离 PG 环境 | **真实 PostgreSQL 16**（pgserver 内嵌 PG16，一次性隔离实例） |
| Migration 0092 upgrade | **PASS**（0091 → 引导外部 `product_mappings` → 0092） |
| Migration 0092 downgrade | **PASS**（0092 → 0091，表/索引/约束恢复） |
| 索引/约束验证 | **PASS**（PRODUCT/VARIATION 部分唯一索引、SKU 辅助索引、workspace 隔离、NULL 行为） |
| 三态身份边界（A/B/C/D/E） | **PASS**（仅 A→PRODUCT，B/C/D/E→UNKNOWN_LEGACY） |
| Supplier/Offer 冲突修订 | **PASS**（规格映射冲突不再自动覆盖，保持 unconfirmed + 落 event_log） |
| 真实 PG 集成测试 | **21 / 21 PASS** |
| 现有核心测试 | **19/19 PASS**（tests_v26 入口）+ **19/19 PASS**（交付文件经共享 conftest） |
| Ruff | **通过**（3 个改动文件） |
| 依赖兼容性 | **已修复**（slowapi/starlette，见 §10） |
| 生产写入 | **无**（未执行任何生产迁移/回填/同步/WC 写入） |

**未执行生产迁移或任何生产写操作**；migration 仅在 pgserver 隔离实例验证。

---

## 1. PostgreSQL 版本与隔离环境证明

- **PostgreSQL 版本**：**PostgreSQL 16**（`pgserver` 内嵌 PG16 二进制，与项目生产基线 PG16 一致）。测试断言 `current_setting('server_version')` 以 `16` 开头（`test_pg00_isolated_postgres16_environment`）。
- **隔离实现**：`backend/tests/integration/conftest.py` 的 `pg_server` fixture 经 `pgserver` 启动**一次性内嵌 PG16 实例**：
  - 临时数据目录：`C:\temp\dsh\nuotao_pg_<random>`（每次随机）。
  - 随机端口（如 52851），`socket_dir=None`，仅监听 127.0.0.1。
  - 每个测试使用 `pg_database_url` 创建的**全新一次性数据库**（随机库名，非 `nuotao`/`nuotao_prod`/`production`）。
  - 会话结束 `cleanup_mode=delete` 自动清理（数据目录随进程销毁）。
- **测试时间**：2026-11-23。
- **生产禁令遵守**：**未连接任何生产库，未使用任何生产凭据**；本报告与测试代码中不含任何真实密码/连接串。migration 仅在上述隔离实例执行。

## 2. Migration 0092 upgrade 报告（0091 → 0092）

**关键前提（与生产一致）**：`product_mappings` 表由应用数据库角色之外的角色持有（见 0071 迁移说明：`must be owner of table product_mappings`），**不在 alembic 链内创建**（0070 因此被 park）。fresh DB 上 `alembic upgrade` 不会创建它。为忠实复现 0092 的真实前置状态，测试在 `upgrade 0091` 之后、`upgrade 0092` 之前，按 0091 时代 schema（含 0070 后的 workspace 维度全局唯一约束）**引导 `product_mappings` 表**，再执行 0092（见 `test_identity_model_v27_pg.py::_BOOTSTRAP_PM_SQL`）。

执行序列：`alembic upgrade 0091` → 引导外部 `product_mappings` → `alembic upgrade 0092`。

验证（`test_pg01_migration_upgrade_0091_to_0092`，真实 PG）：
- `alembic_version` = `0092`。
- **product_mappings 新增身份字段**全部存在：`woocommerce_variation_id`、`variation_sku`、`source_offer_id`、`source_variation_spec`、`identity_state`、`trace_id`。
- **order_items** 新增：`wc_variation_id`、`variation_sku`、`identity_state`。
- **inventory_snapshots** 新增：`variation_id`、`variation_sku`、`source_timestamp`。
- **product_cost** 与 **product_cost_snapshots** 新增：`variation_id`、`variation_sku`。
- **PRODUCT 部分唯一索引** `ux_product_mapping_product` 存在。
- **VARIATION 部分唯一索引** `ux_product_mapping_variation` 存在。
- **SKU 非唯一辅助索引** `ix_product_mapping_variation_sku` 存在。
- **新表** `supplier_offer_mappings` + 索引 `ux_supplier_offer_mapping_variation`、`ux_supplier_offer_mapping_product` 存在。

## 3. Migration 0092 downgrade 报告（0092 → 0091）

执行：`alembic upgrade 0092`（含引导）→ `alembic downgrade 0091`。

验证（`test_pg02_migration_downgrade_0092_to_0091`，真实 PG）：
- `alembic_version` = `0091`。
- 新表 `supplier_offer_mappings` **已删除**。
- 0092 新增索引全部删除：`ux_product_mapping_product`、`ux_product_mapping_variation`、`ix_product_mapping_variation_sku`、`ux_inventory_snapshot_variation`、`ux_inventory_snapshot_product`。
- 0092 新增列删除：`product_mappings.woocommerce_variation_id/identity_state/trace_id`、`order_items.identity_state`、`inventory_snapshots.variation_id`。
- **旧全局唯一约束恢复**：`uq_product_mappings_workspace_woo`、`uq_product_mappings_workspace_nuotao` 在 `product_mappings` 上重新存在（`pg_constraint` 查证）。

## 4. 数据库索引与约束验证报告（真实 PG 读写）

| 约束/行为 | 测试 | 结果 |
|---|---|---|
| 同 workspace 同 Product 不能重复商品级映射 | `test_pg03` | PASS（重复触发 `UniqueViolationError`） |
| 不同 workspace 可拥有相同外部 Woo ID（商品级） | `test_pg03` | PASS |
| 同 workspace 同 Variation 不能重复变体级映射 | `test_pg04` | PASS |
| 同商品多变体可共存 | `test_pg04` | PASS（2 变体共 2 行） |
| 不同 workspace 可拥有相同外部 WooCommerce ID（变体级） | `test_pg05` | PASS（跨 workspace 同 woo+vid 共存） |
| PRODUCT 行（vid NULL）不与变体行冲突（部分唯一索引区分） | `test_pg07` | PASS |
| NULL `variation_sku` 可入库（NULL 不绕过身份校验） | `test_pg07` | PASS |
| SKU 辅助索引非唯一：重复 SKU 合法 | `test_pg08` | PASS（2 变体共用 SKU） |
| 未知身份不被自动归类 PRODUCT | `test_pg06` | PASS（UNKNOWN_LEGACY 落库，非 PRODUCT） |
| 服务层 workspace 隔离 | `test_pg20` | PASS |

## 5. 三态身份边界测试报告（A/B/C/D/E）

代码修订：`identity_model_v26.py::identity_state()` 新增 `identity_reason` 参数与 `UNKNOWN_IDENTITY_REASONS` 集合（B/C/D/E），**显式未确认原因强制 UNKNOWN_LEGACY，优先于其它判定**。

`test_pg09_identity_boundary_five_cases`（真实 PG 环境下运行纯函数）：
- **A 已确认无变体**（`confirmed_no_variation`）→ **PRODUCT**。
- **B 变体列表未完整获取**（`variation_list_incomplete`）→ **UNKNOWN_LEGACY**。
- **C WC API 请求失败**（`wc_api_failed`）→ **UNKNOWN_LEGACY**。
- **D 本地变体数据未同步完整**（`local_sync_incomplete`）→ **UNKNOWN_LEGACY**。
- **E 有变体但记录缺 Variation ID**（`variation_id_missing`）→ **UNKNOWN_LEGACY**（即便 `product_has_variations=True` + 记录上下文，显式 E 原因仍强制 UNKNOWN_LEGACY）。
- `UNKNOWN_IDENTITY_REASONS` 集合 = {B, C, D, E} 四项齐全。

## 6. Supplier / Offer 冲突处理修订

代码修订：`identity_model_v26.py::upsert_offer_mapping()` **不再直接用最新 `effective_at` 自动覆盖规格映射冲突**。区分四类：
1. 同一 Offer 报价更新（规格未变）→ 新行 `mapped`，旧版本 `archived`（历史报价保留，`test_pg11`）。
2. 同一 Offer 规格映射变更（**已验证 mapped 行**）→ **不覆盖已验证映射**；新证据降级 `unconfirmed`，落 `supplier_offer_mapping.spec_conflict` 事件（`conflict_reason=spec_mapping_changed`、`requires_manual_review=True`、`trace_id`），等人工审核。
3. 多供应商独立报价 → 不同 `supplier_id` 键不同，各自独立（`test_pg10`）。
4. 同一 Offer 冲突规格证据（现有未验证）→ 旧行 `archived`，新证据 `mapped`（可推进）。

`test_pg13_mapping_conflict_no_auto_overwrite`（真实 PG）：
- 已验证 `mapped`（`{"color":"red"}`）不被更晚的冲突规格（`{"color":"blue"}`）覆盖。
- 新证据行 `mapping_status='unconfirmed'`。
- 原验证映射仍为 `mapped` 且规格保持 `{"color":"red"}`（未被覆盖）。
- `event_log` 落 `supplier_offer_mapping.spec_conflict`：`conflict_reason=spec_mapping_changed`、`requires_manual_review=True`、`trace_id=t-cf2`。
- 全部历史证据保留（行永不删除）。

## 7. 真实 PostgreSQL 集成测试结果

文件：`backend/tests/integration/test_identity_model_v27_pg.py`（21 项，**全部真实 PG 读写，不 mock、不用 create_all 判定**）。

命令：`cd backend; $env:PYTHONPATH='.'; .venv/Scripts/python -m pytest tests/integration/test_identity_model_v27_pg.py -p no:cacheprovider -q`

**结果：21 passed, 0 failed**（约 140s，含每测试全新 DB 的 0001→0092 迁移链）。

覆盖指令 §六 18 项对照：

| §六 项 | 测试 |
|---|---|
| PRODUCT 唯一性 | `test_pg03` |
| VARIATION 唯一性 | `test_pg04` |
| UNKNOWN_LEGACY | `test_pg06`、`test_pg09` |
| 部分唯一索引 | `test_pg03/04/07` |
| NULL 边界 | `test_pg07` |
| workspace 隔离 | `test_pg03/05`、`test_pg20` |
| SKU 重复/缺失 | `test_pg08`、`test_pg07` |
| 多供应商多 Offer | `test_pg10` |
| Offer 报价历史 | `test_pg11` |
| Offer 失效归档 | `test_pg12` |
| 映射冲突 | `test_pg13` |
| OrderItem 变体关联 | `test_pg14` |
| InventorySnapshot 变体级更新 | `test_pg15` |
| 父商品误更新阻断 | `test_pg16` |
| CostSnapshot 历史不覆盖 | `test_pg17` |
| 历史回填幂等 | `test_pg18` |
| event_service + trace_id | `test_pg13`、`test_pg19` |
| migration upgrade/downgrade | `test_pg01`、`test_pg02` |

另含 `test_pg00`（PG16 隔离环境证明）。

## 8. 现有核心测试结果

| 入口 | 结果 | 说明 |
|---|---|---|
| `tests_v26/test_identity_model_v26.py` | **19 / 19 PASS** | V2.6 隔离入口（SQLite 内存） |
| `tests/test_identity_model_v26.py`（交付文件，**经共享 conftest**） | **19 / 19 PASS** | 依赖修复后共享 conftest 可加载，交付文件可直接运行 |

## 9. Ruff 检查结果

命令：`ruff check app/services/identity_model_v26.py app/core/rate_limit.py tests/integration/test_identity_model_v27_pg.py`

**结果：All checks passed!**（RUF002/RUF003 已 ignore，中文注释合法）。

## 10. 依赖兼容性处理报告（slowapi 0.1.10 + starlette 1.6.0）

**根因**：共享 `tests/conftest.py` 顶层 `from app.api.v1.endpoints.auth import ...` → `app.core.rate_limit` 中 monkeypatch `starlette.config.Config._read_file(self, env_file)`。starlette 1.6.0 的 `Config.__init__` 改为调用 `self._read_file(env_file, encoding)`（多传 `encoding`），旧签名 `_fixed_read_file(self, env_file)` 报 `TypeError: _fixed_read_file() takes 2 positional arguments but 3 were given`。

**依赖漂移确认**：`backend/pyproject.toml` 约束 `fastapi==0.115.12`、`starlette>=0.37.0`、`slowapi>=0.1.0`；实际安装为 `fastapi 0.141.1` / `starlette 1.6.0` / `slowapi 0.1.10` / `limits 5.8.0`（远高于 pin），属**既有依赖漂移**，非本次变更引起。

**修复方案（最小、可复现、不改依赖版本）**：将 `app/core/rate_limit.py` 的 monkeypatch 签名改为 `def _fixed_read_file(self, *args, **kwargs)`，用 `args[0]/kwargs.get("env_file")` 兼容新旧两种 starlette 调用约定，并显式以 `utf-8` 读取（保留原 Windows GBK 规避意图）。

**变更影响**：仅影响 `app/core/rate_limit.py` 的 .env 读取兼容层，**不改变任何限流行为、不改变依赖版本**。修复后：
- `import app.main` / `app.api.v1.endpoints.auth` 正常。
- 共享 `tests/conftest.py` 可加载 → **交付测试文件 `tests/test_identity_model_v26.py` 可直接运行（19/19）**，消除了 `tests_v26/` 临时入口的必要性（该入口保留但不再是必需）。
- V2.7 PG 集成测试与现有核心测试均可运行。

**未采用**：pin 降级 starlette/fastapi（风险大、影响面广）；未为绕过错误跳过任何核心测试。

## 11. Git 状态与应提交文件清单

- **分支**：`main`；**HEAD**：`f7ee816`（V2.5 文档基线）。
- **未执行任何 `git commit` / `git add .`**（由父代理统一提交）。

**V2.6 + V2.7 应单独提交文件清单（禁 `git add .`）**：

新增（`??`）：
- `backend/alembic/versions/0092_identity_model.py`
- `backend/app/models/supplier_offer_mapping.py`
- `backend/app/services/identity_model_v26.py`
- `backend/tests/test_identity_model_v26.py`
- `backend/tests/test_identity_model_v26_pg.py`
- `backend/tests_v26/`（conftest.py + test_identity_model_v26.py）
- `backend/tests/integration/test_identity_model_v27_pg.py`（**V2.7 新增**）
- `docs/PRICING_V2_6_IDENTITY_IMPLEMENTATION.md`
- `docs/PRICING_V2_6_ER_DIAGRAM.md`
- `docs/PRICING_V2_6_SUPPLIER_OFFER_MAPPING.md`
- `docs/_audit/PRICING_V2_6_BUSINESS_RELATION_REFACTOR.md`
- `docs/_audit/PRICING_V2_6_71ROW_BACKFILL_REPORT.md`
- `docs/_audit/PRICING_V2_6_EXECUTION_REPORT.md`
- `docs/_audit/V2_7_CHATGPT_DIRECTIVE.md`
- `docs/_audit/PRICING_V2_7_EXECUTION_REPORT.md`（**本报告**）

修改（`M`）：
- `backend/app/models/product_mapping.py`（V2.6）
- `backend/app/models/order.py`、`backend/app/models/supply_chain.py`、`backend/app/models/product.py`、`backend/app/models/product_intelligence.py`（V2.6）
- `backend/app/models/__init__.py`（注册新模型，V2.6）
- `backend/app/core/rate_limit.py`（**V2.7 依赖修复**）
- `backend/ruff.toml`（RUF002/RUF003 ignore）
- `docs/operating_rules.md`（如属本轮变更）

## 12. 生产未写入确认

本轮**以下均未执行**（指令 §九）：
- 生产 Migration 0092 upgrade / downgrade；
- 生产数据库回填；
- 生产库存同步；
- WooCommerce API 写入；
- 自动采购 / 自动加购 / 促销 / 商品调价 / SKU 修改；
- 未经 Owner 审批的规则修改；
- 生产部署。

所有 migration 操作**仅在 pgserver 内嵌的一次性隔离 PG16 实例**执行并已随实例清理。未连接生产库、未使用生产凭据、报告与测试中无任何真实密码。

## 13. 已知遗留（非 V2.7 范围，供 Owner 决策）

- `backend/tests/integration/test_postgres_migrations.py`（M5.2.1 通用迁移测试）：**1 failed + 4 errors**，全部根因为 `relation "product_mappings" does not exist`——该表不在 alembic 链内（外部持有，0070 被 park），fresh DB `alembic upgrade head` 到 0092 时失败；且其断言 `version_num == "0024"` 已因 0092 成为新 head 而过期。**此为 V2.6 加入 0092 后的既有问题，非 V2.7 引起，亦非定价身份域范围**。
  - 建议修复（未在本轮执行，避免改动非定价域核心测试）：在共享 `pg_migrated` fixture 中复用本报告 §2 的 `product_mappings` 引导方案（`upgrade 0091` → 引导 → `upgrade head`），并将过期断言改为动态 head。
- V2.7 的 0092 验证由 `test_identity_model_v27_pg.py` 的 `test_pg01/test_pg02` 完整覆盖，不受上述遗留影响。

---

**全部 V2.7 交付项完成，停止，交由 Owner 终审。** 未经 Owner 新的书面授权，不执行生产迁移或任何生产写操作。