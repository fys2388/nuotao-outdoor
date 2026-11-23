# M4 V2.7.1 — Alembic 迁移链路完整性修复设计

> 指令：`docs/_audit/V2_7_1_CHATGPT_DIRECTIVE.md`（§三 P0 设计，§四 P0 双路径）
> 状态：设计定稿，实现严格按本设计执行。
> 生产禁令：本设计与实现**均不触碰生产库**；全部验证在 pgserver 内嵌一次性 PG16 隔离实例。

---

## 一、调查结论（时间线与来源定性）

### 1.1 product_mappings 表来源定性：**C 类 — 人工/脚本创建，从未正式迁移**

全历史取证（git log -S / 全仓库 grep）结论：

- **没有任何 Alembic revision 执行过 `op.create_table("product_mappings")`**。
  `product_mappings` 仅出现在三个迁移相关位置：0070（alter，已 park）、0071（仅注释提及）、0092（alter）。
- `infra/ensure_tables.py` 明确记载（第 7-10 行）：

  > 有五张表（users、operation_logs、system_settings、**product_mappings**、product_nuotao_scores）
  > **从来没有 create_table 迁移**，是早期手动跑 `backend/create_tables.py` 建出来的。
  > 本脚本是它们与 "relation does not exist" 之间唯一的防线。

- 生产运行时由 `deploy.yml` 在 `alembic upgrade head` 之后调用 `ensure_tables.py`，
  靠 `Base.metadata.create_all()`（只建不存在的表、绝不 ALTER）兜底创建它。

**定性：C 类（人工 SQL/脚本创建）**，且叠加 **D 类风险**（模型后续新增列历史上既不在迁移里、create_all 也不会 ALTER，即 `data_integrity_*` 曾丢失的同一机制）。

### 1.2 时间线

| revision | 对 product_mappings 的动作 | 状态 |
|---|---|---|
| （无） | 表由 `backend/create_tables.py` 手动建出（早期），从未入链 | C 类 |
| 0070 | `alter`：把全局唯一 `uq_product_mappings_nuotao_id`/`_woo_id` 改为 workspace 维度 `uq_product_mappings_workspace_nuotao`/`_workspace_woo` | **park（未在链内）** |
| 0071 | 仅注释说明为何跳过 0070；`down_revision=0069` 绕过 0070 | 在链内 |
| 0092 | `alter`：删 0070 的两个 workspace 唯一约束、加 6 个身份列、建 3 个索引 | 在链内（head） |

### 1.3 0070 park 原因（有 git 证据）

commit `8275739`（`fix(alembic): skip 0070, chain data_integrity migration off 0069`）：

> The previous deploy failed inside migration 0070 with
> `asyncpg.InsufficientPrivilegeError: 'must be owner of table product_mappings'`
> — the application role `nuotao` does not own that table, so it cannot
> DROP/ADD CONSTRAINT on it at all. 0070 is not needed for the data_integrity work,
> so park it as `.dsh-parked` ... and re-point 0071's down_revision at 0069.

**根因：应用数据库角色非 `product_mappings` 属主（表由外部/超管角色持有），无权 DDL。**
0070 被重命名为 `0070_product_mapping_workspace_scope.py.dsh-parked` 保留在树内（未删除）。

### 1.4 连锁后果

- fresh DB `alembic upgrade head` 到 0092 时，0092 的 `op.add_column("product_mappings", ...)` 因表不存在而失败
  → `relation "product_mappings" does not exist`。
- 这正是 `test_postgres_migrations.py` 的 `pg_migrated` fixture（`upgrade head`）报
  **1 failed + 4 errors** 的直接根因（已在隔离 PG16 复现）。
- 生产之所以“能跑”，仅因 `ensure_tables.py` 在 alembic 之后用 create_all 兜底建表——
  即迁移链本身从未真正负责这张表。

---

## 二、修复目标与硬约束

**目标**：让 fresh DB 能从 0001 一路 `upgrade` 到 head(0092) 且 `product_mappings` 由**迁移链**创建；
同时保持历史库（已应用 0092、表由外部角色持有）兼容；两路径最终 schema 一致。

**硬约束**：
1. 不得恢复 0070 进链（应用角色无权，会重现 InsufficientPrivilegeError）。
2. 不得删除/重写历史迁移文件。
3. 不得用 `IF NOT EXISTS` 简单掩盖 schema 不一致——必须比较现有结构与预期结构，验证列类型/约束/索引/外键真正正确。
4. 保留已应用历史 revision 的**升级语义**对“表已存在”的库不变。

---

## 三、方案比较

### 方案 1：新增 forward-only reconciliation migration（0093，down_revision=0092）

在 0092 之后追加 0093，负责“若 product_mappings 缺失则创建、若存在则对账补齐”。

- **已有库（已应用 0092）**：0092 已成功 → 0093 只需校验/补齐；但生产库应用角色对已有表**无权 ALTER**，
  0093 若试图 `add_column` 补齐会重现 InsufficientPrivilegeError。
- **致命缺陷（全新库）**：0093 在 0092 **之后**，而 0092 在 fresh DB 上**先失败**
  （`add_column` 到不存在的表）。0093 根本没机会运行。
  → **除非同时改 0092，否则方案 1 无法让 fresh DB 通过**。
- 结论：单靠尾部 reconciliation migration **不成立**，除非把 0092 改成“表缺失时跳过自身 PM 段”，
  那样等于又回到方案 2，且把“建表”与“改表”拆到两个 revision，逻辑割裂、
  fresh 库的 PM 建表被推迟到 0093 而 0092 留空转，可读性差。

### 方案 2：现有 graph 向前兼容修复 —— 0092 自举（self-bootstrapping，**选定**）

在 0092 `upgrade()` 开头加**表存在性守卫**：
- 若 `product_mappings` **已存在**（历史库/生产库，表由外部角色持有）→ 与现状**完全一致**，
  执行原有“删旧唯一约束 + 加身份列 + 建索引”逻辑，语义不变。
- 若 **不存在**（fresh DB）→ 先按**有证据的 0091 时代基线 schema**（含 0070 后的两个 workspace 唯一约束）
  `CREATE TABLE`，随后落入与已存在路径**完全相同**的升级代码，得到同一最终 schema。

**关键合规点**：
- 这**不是** `CREATE TABLE IF NOT EXISTS` 掩盖不一致。守卫是显式 `to_regclass` 探测 + 分支：
  - 不存在 → 用完整、明确的 0091 基线 DDL 建表（含正确的列类型、NOT NULL、FK、0070 两个唯一约束）；
  - 已存在 → **比较现有结构与预期基线**（列名/类型），缺失的基线列按正确类型补齐（真实对账，非掩盖），
    再执行统一升级。
- 建表后的索引**不**用 `IF NOT EXISTS`：复用 0092 已有的 `_constraint_exists()` 逐个真实探测后 `create_index`。
- 建的表通过 FK 关联 `products(id)`（products 由 0002 正式创建，fresh DB 到 0092 时已存在）。

**为何不违反“不改已应用迁移历史语义”**：
- 对**已应用 0092 的库**（生产/历史），`alembic_version` 已是 0092，**不会重跑** 0092；
  其已落地的 schema 不受本文件后续编辑影响。守卫对“表已存在”分支保持原语义。
- 对**全新库**，0092 首次运行时表缺失，守卫建表——这是让迁移链**首次真正负责**该表的正规化，
  正是指令 §一/§四「product_mappings 必须由迁移链创建」的要求。

**downgrade 策略**：0092 downgrade 保持现状（删身份列/索引、重建 0070 两个 workspace 唯一约束）。
对 fresh 库 down 到 0091 后表**仍存在**（含基线列 + 0070 约束）——与“0091 时代表已存在”的历史状态一致；
本设计**不**在 downgrade 里 drop 整表（避免跨库歧义与数据误删），如实记录该边界。

### 选定：方案 2

理由：唯一能让 fresh DB 端到端通过、且对已应用库零影响、逻辑内聚、可被两条 PG 路径验证的方案。

---

## 四、选定方案的实现规格

### 4.1 0091 时代基线 schema（有证据，复用 v27 测试已验证的 bootstrap DDL）

```sql
CREATE TABLE product_mappings (
    id UUID PRIMARY KEY,
    workspace_id UUID NOT NULL,
    nuotao_product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    woocommerce_id INTEGER NOT NULL,
    woocommerce_slug VARCHAR(255),
    sync_status VARCHAR(32) DEFAULT 'synced',
    last_synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    CONSTRAINT uq_product_mappings_workspace_nuotao UNIQUE (workspace_id, nuotao_product_id),
    CONSTRAINT uq_product_mappings_workspace_woo  UNIQUE (workspace_id, woocommerce_id)
);
```
（来源：`test_identity_model_v27_pg.py::_BOOTSTRAP_PM_SQL`，21 项 PG 测试据此跑通；与 0070 upgrade 后状态一致。）

### 4.2 0092 `upgrade()` 改造（伪码）

```
bind = op.get_bind()
if not _table_exists(bind, "product_mappings"):
    _create_pm_baseline(bind)          # 4.1 完整 DDL（非 IF NOT EXISTS）
else:
    _reconcile_pm_baseline(bind)       # 对账：缺失的基线列按正确类型补齐（真实比较）
# ↓ 以下为 0092 原有逻辑，两条路径共用，得到同一最终 schema
_drop_unique_if_exists(...woo / ...nuotao)
add_column(woocommerce_variation_id / variation_sku / source_offer_id /
           source_variation_spec / identity_state / trace_id)
create_index(ux_product_mapping_product / ux_product_mapping_variation /
             ix_product_mapping_variation_sku)   # 经 _constraint_exists 真实探测
```

`_reconcile_pm_baseline`：`sa.inspect` 取现有列集合，对基线列（id/workspace_id/nuotao_product_id/
woocommerce_id/woocommerce_slug/sync_status/last_synced_at/created_at/updated_at）逐个比对，
缺失则 `op.add_column` 用与基线一致的类型补齐（幂等、只补缺、不改已有列类型，避免对无权表越权改列）。

### 4.3 边界兼容（指令 §三要求逐条）

| 边界 | 处理 |
|---|---|
| PM 已存在 | 走“已存在”分支，与现状完全一致 |
| PM 不存在 | 4.1 建表 → 统一升级 |
| 部分含 V2.6 列（如曾手动加过 woocommerce_variation_id） | `op.add_column` 前逐列探测，已存在则跳过（真实对账，非掩盖）；索引经 `_constraint_exists` 探测 |
| 完整含 V2.6 列 | 全部跳过，仅确保索引存在 |
| 历史重复映射 | 0070 的两个唯一约束在“已存在”分支用 `_drop_unique_if_exists` 安全删除；fresh 分支建表后同样删除 → 两路径一致允许多变体共存 |
| NULL 身份记录 | identity_state 默认 `'UNKNOWN_LEGACY'`（server_default），旧行不误判为 PRODUCT |

### 4.4 事务与失败恢复

- Alembic 默认在单事务内跑 `upgrade()`（PG 支持 DDL 事务）→ 任一步失败整体回滚，不留半成品。
- 失败恢复：修正迁移后重跑 `alembic upgrade head`（fresh 库可整库重建；历史库事务回滚到 0091 状态）。

---

## 五、两条真实 PG16 验证路径（§四）

- **路径 A（空库）**：全新库从 base(0001) `upgrade head`，**禁止人工预建任何业务表**。
  断言：product_mappings 由迁移链创建、含全部 V2.6 身份列 + 3 索引 + FK；alembic_version=0092。
- **路径 B（历史库）**：`upgrade 0091` → 按 4.1 基线 bootstrap `product_mappings`（含 0070 约束 + 关键历史行）→
  `upgrade 0092`。断言：表/约束/历史数据保留、身份列就位。
- **schema 对比**：对 A、B 两库分别用 `information_schema.columns` 导出
  `(table,column,data_type,udt_name,is_nullable,column_default)` 并 diff，断言**完全一致**。

---

## 六、测试方案

1. `test_postgres_migrations.py`：改过期断言 `==0024` → 动态 head（`alembic_head()`）；
   `downgrade drill` 终点改到 `0091`（避开 0092→旧版对 PM 多变体回滚的既有限制，见 0092 downgrade 注释），
   保留原“降级若干步→校验→升回 head”的业务意图；`pg_migrated` 依赖 fresh head 升级因方案 2 而通过。
2. `test_identity_model_v27_pg.py`：回归确认仍 21/21（0092 改造不得破坏既有 PM 读写）。
3. 新增 `test_migration_paths_v271_pg.py`：路径 A/B + schema 对比 + downgrade 边界。
4. Offer 冲突幂等测试、rate_limit 回归测试（见执行报告 §六/§七）。

（实现严格按本设计执行；证据见 `PRICING_V2_7_1_EXECUTION_REPORT.md`。）