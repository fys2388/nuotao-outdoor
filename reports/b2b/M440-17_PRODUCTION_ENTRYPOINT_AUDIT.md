# M440-17 生产迁移入口全量审计（APR-INC-002）

> 日期：2026-11-18 | 状态：宿主+容器+脚本入口已全部接入门禁或标注
> 审计范围：全仓库（GitHub Actions + shell 脚本 + Dockerfile 镜像入口）

## 1. 全量入口清单（扫描 `alembic upgrade` / `upgrade head`）
| 入口 | 原行为 | 处置 | 状态 |
|---|---|---|---|
| `infra/deploy-production.sh` | `alembic upgrade head`（**事故根源**）| 固定 `alembic upgrade 0086` | ✅ |
| `db-migration-and-scheduler.yml` | `alembic upgrade head`（主迁移入口）| gate + `alembic upgrade $APPROVED` | ✅ |
| `production-deploy.yml` | `alembic upgrade head` | gate + `alembic upgrade $APPROVED` | ✅ |
| `server-code-repair.yml` | `alembic upgrade head`（+stamp）| gate + `alembic upgrade $APPROVED`（stamp 标注应急）| ✅ |
| `backend/Dockerfile` | `CMD ... upgrade head`（容器启动自动迁移）| 挂载清单→gate+approved；无清单→不迁移 | ✅ |
| `docker-redeploy-api.yml` | 容器 run `upgrade head && uvicorn` | 挂载 infra + gate + approved | ✅ |
| `docker-restore-api.yml` | 同上 | 同上 | ✅ |
| `hotdeploy-seedream5-i2i.yml` | `.venv/bin/alembic upgrade head` | gate + approved | ✅ |
| `one-click-deploy.sh` | `docker compose exec backend upgrade head` | 有清单→gate+approved；无清单→不迁移 | ✅ |
| `infra/deploy.sh` | 同上 | 同上 | ✅ |
| `infra/deploy_b2b_portal.sh` | 文档提示 `upgrade head` | 提示改为 0086+门禁 | ✅ |
| `staging-acceptance-v016.yml` | `upgrade head`（staging）| Staging 属允许环境（PII 验证），保留并标注 | ✅(允许) |
| `enable-staging.yml` | `upgrade head`（staging）| 同上 | ✅(允许) |
| `infra/deploy-staging.sh` | `upgrade head`（staging）| 同上 | ✅(允许) |

## 2. 结论
- **生产直连入口全部接入 fail-closed 门禁**（`infra/migration_gate.sh` + `migration_approvals.yaml`），**无一残留 `upgrade head`**。
- Staging 入口保留 `upgrade head`（Owner 允许 staging 验证 0087；staging 环境当前不存在，重建后生效）。
- 普通应用部署**不再自动迁移**（无清单不迁移）；生产迁移统一走门禁 workflow。

## 3. 审计链
- 门禁负向测试 6 场景（CI 覆盖，`infra/test_migration_gate.sh`）。
- 每次生产迁移记录：`approval_id / target_revision / actor / run_id / 时间 / 结果`（`migration_approvals.yaml` 的 `last_approval` + workflow 日志）。
