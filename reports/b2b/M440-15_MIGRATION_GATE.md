# M440-15 生产迁移授权门禁设计（M4.4-INC-001 整改）

> 日期：2026-11-18 | 状态：设计 + 实现 + 宿主入口接入（CI 待验证）
> 对应 Owner 指令：M4.4-INC-001（0087 未授权应用事故整改）

## 1. 硬性原则（Owner 2026-11-18）

1. **普通应用部署不自动迁移数据库**——部署与迁移解耦。
2. **生产迁移目标 revision 必须来自独立批准清单**——`infra/migration_approvals.yaml`。
3. **未批准 revision 必须 fail-closed**——门禁脚本拒绝并中止。
4. **每次生产迁移记录** `approval_id / target_revision / actor / run_id / 时间 / 结果`（审计）。

## 2. 实现

### 2.1 批准清单 `infra/migration_approvals.yaml`
- `approved_revision: "0086"`（Owner 已批准的最高 revision）
- `approved_list: ["0085","0086"]`
- `last_approval`：`approval_id=APR-M440-DB-001`、`approved_by=Owner`、`approved_at=2026-11-18`
- **0087（PII）未列入**——生产禁止。

### 2.2 门禁脚本 `infra/migration_gate.sh`
- 用法：`migration_gate.sh <target_revision>`；target 不在 `approved_list` → **exit 1（FAIL-CLOSED）**。
- 批准清单缺失 / `approved_revision` 空 → **exit 1**。
- 生产迁移入口统一调用；未批准 revision 一律拒绝。

### 2.3 接入点（本批已改）
| 入口 | 原行为 | 现行为 |
|---|---|---|
| `deploy-production.sh` | `alembic upgrade head`（**事故根源**）| `alembic upgrade 0086`（已修，上一批）|
| `db-migration-and-scheduler.yml` | `alembic upgrade head`（主迁移入口）| gate + `alembic upgrade $APPROVED` |
| `production-deploy.yml` | `alembic upgrade head` | gate + `alembic upgrade $APPROVED` |
| `server-code-repair.yml` | `alembic upgrade head`（+stamp）| gate + `alembic upgrade $APPROVED`（stamp 标注应急）|
| `docker-redeploy-api.yml` | `alembic upgrade head && uvicorn` | **待专项修复**（容器需挂载批准清单）|
| `docker-restore-api.yml` | `alembic upgrade head && uvicorn` | **待专项修复**（同上）|
| `hotdeploy-seedream5-i2i.yml` | `alembic upgrade head` | **待专项修复**（同上）|
| `staging-acceptance / enable-staging / deploy-staging.sh` | `alembic upgrade head` | Staging 属允许环境（PII 验证）；保留 head，标注 |
| `deploy.sh` / `deploy_b2b_portal.sh` | `alembic upgrade head` | 本地/文档；标注（非生产直连）|

## 3. 待后续
- 容器入口（docker-redeploy/restore/hotdeploy）专项修复：容器构建时挂载批准清单或改为显式 approved revision。
- 生产部署与迁移解耦落地：`deploy-production.sh` 仅部署不迁移（迁移走门禁 workflow）；需 Owner 确认后实施（避免破坏现有 0086 基线）。
