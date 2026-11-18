# M440-16 容器/部署入口迁移门禁修复（APR-INC-002）

> 日期：2026-11-18 | 状态：修复已提交（89c721f），CI 验证中
> 对应 Owner 指令：APR-INC-002（P0：容器入口专项修复，仅代码/静态/CI，不批生产容器重建）

## 1. 修复内容
| 入口 | 原行为 | 修复后 |
|---|---|---|
| `backend/Dockerfile`（镜像默认 CMD）| `alembic upgrade head && uvicorn`（**每次容器启动自动迁移到 head**）| 挂载批准清单则 gate+approved 迁移；无清单→**不迁移只启动**（部署与迁移解耦）|
| `docker-redeploy-api.yml` | `docker run ... sh -c "alembic upgrade head && uvicorn"` | 挂载 `/opt/nuotao-ai-os/infra:/app/infra:ro` + gate + `alembic upgrade $APPROVED` |
| `docker-restore-api.yml` | 同上 | 同上 |
| `hotdeploy-seedream5-i2i.yml` | `.venv/bin/alembic upgrade head` | gate + `alembic upgrade $APPROVED` |
| `one-click-deploy.sh` | `docker compose exec backend alembic upgrade head` | 有清单则 gate+approved；无清单→不迁移 |
| `infra/deploy.sh` | `docker compose exec backend alembic upgrade head` | 同 |
| `infra/deploy_b2b_portal.sh` | 文档提示 `upgrade head` | 提示改为 `upgrade 0086`（+门禁）|

## 2. 门禁加强（migration_gate.sh）
- **版本一致性**：target 必须精确等于 `approved_revision`（低于/猜测 → 拒绝）。
- **格式校验**：`approved_revision` 非 4 位数字（malformed YAML/错误类型）→ 拒绝。
- 原有：批准清单缺失 → 拒绝；target 不在 `approved_list` → 拒绝。

## 3. 负向测试（infra/test_migration_gate.sh，CI 覆盖）
| 场景 | 期望 |
|---|---|
| target=0086（批准）| 允许 |
| target=0087（未批）| 拒绝 |
| target=0084（低于）| 拒绝 |
| 批准清单不存在 | 拒绝 |
| YAML 格式错误 | 拒绝 |
| approved_revision 为空 | 拒绝 |

## 4. 边界
- 仅代码/静态/CI 变更；**未**触发生产容器重建/部署。
- 生产迁移仍由门禁 workflow（B2B Lead Migration Gate）统一管理；`approved_revision=0086` 未变。
