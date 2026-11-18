# M440-14 0087 未授权生产迁移事故复盘（M4.4-INC-001）

> 日期：2026-11-18 | 状态：**PASS（生产无残留验证 + 门禁整改已落地）**
> 对应 Owner 指令：M4.4-INC-001（优先级高于一般功能开发）

## 1. 事件描述
- **现象**：`Deploy to Production (staging-gated)`（run 44247476467 附近）把 Owner **未批准**的迁移 **0087（b2b_leads PII 加密列）** 自动应用到了生产库，`current_revision=0087`。
- **触发链**：`deploy.yml` → `git reset --hard origin/main` → `bash infra/deploy-production.sh` → **`alembic upgrade head`**（生产实际执行，非 dry-run）。
- **为何 0085/0086 没被 deploy 应用**：0085/0086 由受控门禁（APR-M440-DB-001）先手动应用，deploy 时已无 pending；**0087 是新迁移**，deploy 的 `upgrade head` 自动追到 0087。

## 2. 根因（部署与迁移未解耦）
1. **`deploy-production.sh` 在普通应用部署里执行 `alembic upgrade head`**——把"代码仓库最新迁移"错误当成"Owner 已批准的生产迁移"。
2. **无独立批准清单**——部署流程无法区分批准/未批准 revision。
3. **无 fail-closed 机制**——未批准 revision 也能通过。
4. 多个生产入口（GitHub Actions + shell + 容器）各自调用 `alembic upgrade head`，无统一门禁。

## 3. 影响与处置
| 项 | 证据 |
|---|---|
| 生产短暂 revision | 0087（仅空列，**未回填任何 PII 数据**——回填脚本从未在生产运行）|
| 回滚 | 受控门禁 `rollback-0087-prod`：`pre=0087 → downgrade 0087->0086 → post=0086`，`still_exists=0` |
| **残留审计（INC001，run 44252145833，只读）** | `revision=0086`；`pii_columns=0`；`pii_index=0`（ux_b2b_leads_email_hash 无）；`pii_triggers=0`；`quotes_table=1`；`lead_total=2`（无删除）；`status_ck=1` |
| 生产 PII 数据 | **零改动**（无 email_hash/email_encrypted/contact_name_encrypted 列、无回填）|
| 修复 | `deploy-production.sh` 改为 `alembic upgrade 0086`（上一批，commit 686ced2）|

## 4. 部署入口审计（全部生产迁移入口）
| 入口 | 原行为 | 整改 |
|---|---|---|
| `infra/deploy-production.sh` | `alembic upgrade head`（**根源**）| ✅ 固定 `alembic upgrade 0086` |
| `db-migration-and-scheduler.yml` | `alembic upgrade head`（主迁移入口）| ✅ gate + `alembic upgrade $APPROVED` |
| `production-deploy.yml` | `alembic upgrade head` | ✅ gate + `alembic upgrade $APPROVED` |
| `server-code-repair.yml` | `alembic upgrade head`（+stamp）| ✅ gate + `alembic upgrade $APPROVED`（stamp 标注应急）|
| `docker-redeploy-api.yml` | `alembic upgrade head && uvicorn` | ⏳ 容器入口待专项修复 |
| `docker-restore-api.yml` | `alembic upgrade head && uvicorn` | ⏳ 容器入口待专项修复 |
| `hotdeploy-seedream5-i2i.yml` | `alembic upgrade head` | ⏳ 容器入口待专项修复 |
| `staging-acceptance / enable-staging / deploy-staging.sh` | `alembic upgrade head` | Staging 允许环境（PII 验证），保留并标注 |
| `deploy.sh` / `deploy_b2b_portal.sh` | `alembic upgrade head` | 本地/文档；标注（非生产直连）|

## 5. 整改落地（M440-15）
- **`infra/migration_approvals.yaml`**：`approved_revision=0086`、`approved_list=[0085,0086]`、`last_approval=APR-M440-DB-001`；**0087 未列入（生产禁止）**。
- **`infra/migration_gate.sh`**：fail-closed 门禁（target 不在批准清单 → exit 1，不执行任何迁移）。
- **宿主关键入口已接入门禁**（见上表）；容器入口待专项（需挂载批准清单或显式 approved）。
- 硬性原则已建立：**部署与迁移解耦、批准清单、fail-closed、审计记录**。

## 6. 结论
- 0087 未授权事件**已受控回滚、生产零残留、门禁已落地**——**PASS**。
- 容器入口（docker-redeploy/restore/hotdeploy）为**已知待专项修复项**（NEEDS_EVIDENCE，不阻塞门禁落地）。
- **最终原则确认**：任何生产操作必须有独立、明确的 Owner 授权；代码完成/CI 通过/Staging 通过/历史审批 ≠ 生产授权。
