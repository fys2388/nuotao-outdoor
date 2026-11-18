# M440-10 生产执行证据报告（APR-M440-DB-001 / APR-M440-DATA-001）

> 日期：2026-11-18
> 执行人：dsh-agent（经 Owner 在 ChatGPT 明确批准后执行）
> 门禁工作流：`.github/workflows/b2b-lead-migration-gate.yml`（三阶段：preflight → migrate → postverify，另加 mark-test-leads 阶段）
> 原则：批准 ≠ 成功；本报告只记录**实测证据**，无证据不判 PASS。

---

## 0. 摘要

| 审批项 | 结果 | 依据 |
| --- | --- | --- |
| APR-M440-DB-001 生产迁移 0085/0086 | **PASS** | preflight 全绿 → 迁移执行 → revision 0084→0086 → 结构/约束/数据复核通过 |
| APR-M440-DATA-001 标记两条测试 Lead | **PASS** | matched_count=2，`is_test=true` 已提交，审计事件 2 条，统计排除已验证 |
| APR-M440-PII-001 PII 加密 | **NOT_STARTED** | Owner 未批准生产执行；本轮未触碰任何 PII |

---

## 1. 前置检查（Preflight）证据

**Run：44216727460**（只读，不改动数据库）

| 检查项 | 实测值 | 判定 |
| --- | --- | --- |
| 生产库连通 | `db=nuotao recovery=false`（主库，无恢复态） | ✅ |
| 迁移前 revision | `current_revision=0084` | ✅ 符合预期起点 |
| 生产代码 HEAD | `7f58e9a`（含 0085/0086 迁移文件，4453B / 2985B） | ✅ |
| Lead 基线 | `lead_total=2` | ✅ |
| 空值检查 | `email=NULL: 0`、`status=NULL: 0`、`created_at=NULL: 0` | ✅ |
| 状态分布 | `new` × 2 | ✅ 全部在合法集合内 |
| 非法状态 | `(0 rows)` | ✅ |
| 测试 Lead 命中 | `matched_count=2`（两条 `is_test_col_exists=0`，列尚未存在） | ✅ |
| 备份 | `/opt/nuotao/backups/nuotao_20261118_003850.sql.gz`（当日 00:38 生成，`wal_lsn=0/9E50350`） | ✅ 有可回滚点 |
| 环境事实 | PG 角色 `nuotao`（`POSTGRES_USER` 覆盖默认值），容器 `nuotao-ai-os-postgres-1` | 已记录 |

**结论：允许进入迁移阶段。**

---

## 2. 迁移执行（Migrate）

**执行路径**：生产宿主机 `/opt/nuotao-ai-os/backend/.venv/bin/alembic`（该环境使用 psycopg，连接 `localhost:5432`，Postgres 容器已做端口映射）。
> 说明：`nuotao-ai-os-scheduler-1` 镜像内只有 asyncpg，`create_async_engine` 报 `No module named 'psycopg'`，故**不采用**容器内 alembic，也不挂载旧代码卷。

**第一次尝试（run 44218912774）**：
```
INFO Running upgrade 0084 -> 0085, 0085_b2b_lead_workflow
INFO Running upgrade 0085 -> 0086, 0086_b2b_lead_quotes
TypeError: string indices must be integers, not 'str'
  at 0086_b2b_lead_quotes.py:66  if _TABLE in [t["name"] for t in insp.get_table_names()]:
```
**根因**：`Inspector.get_table_names()` 返回 `list[str]`，却按 dict 取 `t["name"]`。0085 已成功、0086 未成功。
**修复**：commit `d7995de` — `if _TABLE in insp.get_table_names():`（upgrade/downgrade 两处）。CI Pre-check / Deploy / Staging Acceptance 均 success 后才在生产重跑。

**执行结果**：生产 `alembic_version` 到达 `0086`（run 44220777078 前置校验读到 `current_revision=0086`，即迁移已完成）。

**未使用**：手工改 `alembic_version`、`alembic stamp`、或任何无关 schema 变更。

---

## 3. 迁移后独立验证（Postverify）

**Run：44221060195**

| 验证项 | 实测值 | 判定 |
| --- | --- | --- |
| 当前 revision | `0086` | ✅ |
| `b2b_lead_quotes` 存在 | `quotes_table_exists=1`，`quotes_rows=0`（空表，符合预期） | ✅ |
| 索引 | `b2b_lead_quotes_pkey`、`ix_b2b_lead_quotes_lead_id`、**`ix_b2b_lead_quotes_lead_version`**、`ix_b2b_lead_quotes_workspace_id` | ✅ |
| 新增列 | `closed_won_reason:text`、`is_test:boolean`、`notified_at:timestamptz`、`notify_attempts:integer`、`notify_last_error:text`、`notify_status:varchar`、`trace_id:varchar` | ✅ 7 列齐 |
| 状态约束 | `ck_b2b_leads_status` 已扩展为 11 状态集合 | ✅ |
| 来源约束 | `ck_b2b_leads_source` 仍为 `b2b_public_website`/`manual` | ✅ 未被破坏 |
| Lead 完整性 | `lead_total=2`（与迁移前一致，无删除/无批量变更） | ✅ |
| 测试 Lead 命中 | `matched_count=2` | ✅ |

---

## 4. 测试 Lead 标记（APR-M440-DATA-001）

**方式**：新增受控脚本 `backend/scripts/mark_test_leads_m440.py`（已入库，commit `4da810c`；`.gitignore` 增加例外，与既有 `seed_agent_config.py` 例外并列），**不绕过审计**。
**运行方式**：`mark-test-leads-dry`（只读）→ 核对 → `mark-test-leads`（写库）。

**Dry-run（run 44223519636）**：`matched_count=2`；两条 `status=new`、`is_test=None`；明确输出「DRY-RUN：未写库」。

**执行（run 44223963156，conclusion=success）**：
```
[1] matched_count=2 expected=2
[2] LD-20261117-3ECF02 id=ce985b9c-a29e-4945-8e71-bf212289bfea status=new is_test=None
[2] LD-20261117-6B43B6 id=69ff3410-290a-437a-a35f-f344f74a0d6c status=new is_test=None
[3] committed：is_test 更新 2 条；event_log 写入 2 条（b2b_lead.test_flagged）
[4] verify LD-20261117-6B43B6 is_test=True
[4] verify LD-20261117-3ECF02 is_test=True
[5] 统计复核：lead_total=2 valid_leads=0 已排除=2
MARK_RC=0
```

**审计事件**（`event_log`，`event_type=b2b_lead.test_flagged`，`commit=False` 与数据变更同事务）：
```
event=b2b_lead.test_flagged | entity=b2b_lead:ce985b9c-... | payload={"actor":"dsh-agent","reason":"M4.3 测试数据；排除出经营统计与报表","run_id":"APR-M440-DATA-001-run-0086","is_test":true,...}
event=b2b_lead.test_flagged | entity=b2b_lead:69ff3410-... | payload={...同上...}
```
payload **不含 email / contact_name 等 PII**。

**边界遵守**：仅改 `is_test`；未删除记录；未触碰其他字段；命中数为 2 才继续（脚本内置 abort 逻辑，命中不为 2 直接返回 2 且不写库）。

**统计排除验证**：`lead_total=2`、`valid_leads=0`、`已排除=2` → 经营统计已不再计入这两条。✅

---

## 5. 本轮修复的缺陷（生产暴露）

| 缺陷 | 影响 | 修复 |
| --- | --- | --- |
| `0086` 幂等判断用 `t["name"]` 遍历 `get_table_names()` | 生产首次迁移在 0086 抛 `TypeError` | commit `d7995de` |
| `.gitignore` 排除 `backend/scripts/*.py` 导致受控脚本无法部署 | 生产无脚本，无法执行受控维护 | commit `4da810c`（增加例外） |
| 门禁脚本 `CODE_ROOT` 仅 migrate 分支定义，`set -u` 下其余阶段报 unbound | 阶段误报失败 | commit `8d25368` |
| `GITHUB_OUTPUT` 未设置时被 `set -u` 拦截 | 阶段误报失败 | commit `79ef2fc` |

---

## 6. 未完成 / 阻塞项

1. **APR-M440-PII-001（PII 加密）**：Owner 明确**未批准生产执行**；本轮零改动，状态 **NOT_STARTED**（设计仍为 NEEDS_EVIDENCE）。
2. **secret-scanning workflow**：本轮推送仍为 failure，属**独立于 M4.4 的预存在故障**（`total_jobs=0`），需单独排查，不能忽略。
3. **生产代码镜像滞后**：`nuotao-ai-os-scheduler-1` 镜像内 alembic 停在 `0080`，与宿主机代码脱节——建议后续统一镜像重建或统一使用宿主机 venv 执行迁移，避免再次误判迁移路径。

---

## 7. 提交清单（本轮）

| commit | 内容 |
| --- | --- |
| `d7995de` | fix(m440): 0086 幂等判断改为字符串比较 |
| `a284cf9` | fix(m440): migrate 允许 0085 为前置状态（0086 回滚后重跑） |
| `6bc2bdc` | feat(m440): 门禁新增 mark-test-leads-dry / mark-test-leads 阶段 |
| `4da810c` | feat(m440): 受控测试 Lead 标记脚本入库（.gitignore 例外） |
| `8d25368` | fix(m440): CODE_ROOT 提升到公共区 |
| `79ef2fc` | fix(m440): 容忍未设置的 GITHUB_OUTPUT |
