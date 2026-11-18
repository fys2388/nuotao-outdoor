# M440-18 容器入口边界负向测试（APR-INC-002 补测）

> 日期：2026-11-18 | 状态：测试A（权限不足）PASS；测试B（容器恢复不迁移）静态断言 PASS + 容器真实执行 NEEDS_EVIDENCE
> 对应 Owner 指令：APR-INC-002 补测（P0）

## 1. 测试A：容器读取批准清单权限不足 → 拒绝
- **方法**：`chmod 000 migration_approvals.yaml` + `runuser -u nobody`（非 root 运行，模拟容器内非特权进程）。
- **先确认权限拒绝可复现**：`runuser -u nobody -- cat <file>` 失败（EACCES）→ 确认测试环境能触发权限拒绝，非"文件不存在"。
- **断言**：
  - `migration_gate.sh` 退出码 = 1（拒绝）。
  - 输出含 `FAIL-CLOSED`（错误日志明确）。
  - **无默认批准版本**：gate 无 hardcode 版本（读清单失败 → `approved_revision` 空 → 拒绝）。
  - **无 `upgrade head` 回退**：gate 无 `upgrade head` 分支（仅打印 FAIL-CLOSED 并 exit）。
- **结果**：CI 负向测试套件（`infra/test_migration_gate.sh`，含本场景）全绿。

## 2. 测试B：容器恢复不自动迁移
- **整改**：`docker-restore-api.yml` 容器启动命令改为 **`sh -c "exec uvicorn ..."`（只启动服务，无任何迁移调用）**；同时 `docker-redeploy-api.yml` 与 `backend/Dockerfile` CMD 按"普通应用部署不自动迁移"核心原则改为只启动服务。
- **静态断言**（`infra/test_migration_gate.sh`）：
  - `docker-restore-api.yml` **不含** `alembic upgrade` / `migration_gate` / `upgrade head`。
  - 容器启动命令为 `sh -c "exec uvicorn ..."`（无 alembic）。
- **容器真实执行**：本环境无 docker daemon/服务器，无法执行真实 `docker run` 恢复流程 → **NEEDS_EVIDENCE**（标记为待 Staging 恢复阶段验证；届时确认 `alembic_version` 在恢复动作前后保持不变）。
- **边界说明**：数据库迁移统一走 B2B Lead Migration Gate workflow（fail-closed 门禁）；普通应用部署/容器启动不再自动迁移。

## 3. 关键改动（本批）
| 文件 | 改动 |
|---|---|
| `docker-restore-api.yml` | 容器启动改为只 `uvicorn`（不迁移，Owner 测试B）|
| `docker-redeploy-api.yml` | 同上（普通应用部署不自动迁移）|
| `backend/Dockerfile` | CMD 改为只 `uvicorn`（不迁移）|
| `infra/test_migration_gate.sh` | 补测试A（权限不足）+ 测试B（无迁移调用断言）|

## 4. 结论
- **M4.4-INC-001 关闭前置**：测试A 通过（真实权限拒绝）；测试B 静态断言通过（恢复无迁移调用）。
- **容器真实执行**（测试B 运行证据）：**NEEDS_EVIDENCE**（无容器环境；待 Staging 恢复阶段）。
- 不批准生产容器重建/部署（本次仅代码/静态/CI）。
