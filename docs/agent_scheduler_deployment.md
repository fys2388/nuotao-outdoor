# Agent 调度器部署记录 — 选品→上架任务正式落地

> 版本: v1.1 | 日期: 2026-09-20（v1.1 修订） | 状态: ✅ 已部署 + Worker 接线补齐
> 关联: `docs/agent_automation_upgrade_p0_p2.md`（P0-1/P0-2/P2-2）、`docs/agent_team_workflow_refactor.md`

> ⚠️ **v1.1 修订说明（重要）**
>
> v1.0 §三.4 曾记录「新增 `backend/app/scheduler.py` 兼容入口 `python -m app.scheduler`，
> 新旧命令均可用」。经 2026-09-20 核查，该声明**不成立**：仓库中同时存在
> `backend/app/scheduler.py`（模块）与 `backend/app/scheduler/`（包），Python 解析时
> **包优先、模块被遮蔽**，`python -m app.scheduler` 实际执行的是 `app/scheduler/__main__.py`
> 中的 **AlertScheduler**，而非 Agent 调度器。`docker-compose.yml` 的 `scheduler` 服务
> 因此也一直在跑错进程。
>
> v1.1 已处置：删除被遮蔽的 `backend/app/scheduler.py`，同步删除死代码
> `backend/app/scheduler/agent_scheduler.py` 与 `agent_scheduler_config.py`；
> `docker-compose.yml` 的 `scheduler` 命令改为 `python -m app.services.agent_scheduler`。
> **唯一权威入口 = `python -m app.services.agent_scheduler`**。
>
> 详见 `docs/agent_team_workflow_refactor.md`。

## 一、背景与决策

此前「选品→上架」链路职责与代码均已就绪，但存在部署缺口：

| 项 | 状态 |
|----|------|
| 职责分工（产品经理 AI 负责选品+上架，营销经理 AI 负责文案/图片，全程人工审批） | ✅ 明确 |
| 调度器代码 `app/services/agent_scheduler.py`（5 个间隔任务） | ✅ 已实现 |
| 选品→上架全链路编排 `app/services/pipeline_orchestrator.py`（P2-2） | ✅ 已实现 |
| **系统服务部署（systemd unit / 开机自启）** | ❌ 未版本化、未落地 |
| **部署工作流（crontab 与 systemd 双进程冲突）** | ❌ 存在冲突 |

**总负责人于 2026-09-07 正式下达部署命令：补齐部署件并接入系统服务。**

## 二、部署基线（权威口径）

| 项 | 值 | 依据 |
|----|----|------|
| 服务器部署根目录 | `/opt/nuotao` | `.github/workflows/deploy.yml`（生产实际执行） |
| Agent 调度器入口（**唯一权威**） | `python -m app.services.agent_scheduler` | `backend/app/services/agent_scheduler.py` `__main__` |
| Agent Worker 入口（**唯一权威**） | `python -m app.worker` | `backend/app/worker/__main__.py` |
| systemd 服务名 | `nuotao-agent-scheduler.service`、`nuotao-agent-worker.service` | `infra/systemd/` 版本化模板 |
| 服务用户 | `nuotao`（与 backend 一致；旧模板的 `root` 已修正） | deploy.yml §7.5 / §7.6 |
| 重启策略 | `Restart=always` / `RestartSec=10` | 同 backend 服务 |

> ❗ `python -m app.scheduler` **不是** Agent 调度器入口。该命令被 `app/scheduler/` 包遮蔽，
> 实际运行的是 `app/scheduler/__main__.py` 中的 **AlertScheduler**。历史文档（M5.11、
> development.md）中的用法已失效，请改用 `python -m app.services.agent_scheduler`。

> ⚠️ 路径基线说明：`infra/systemd/nuotao-backend.service` 及部分早期文档（cloud_deployment_guide 等）使用
> `/opt/nuotao-ai-os`；生产 deploy.yml 与 `docs/development_roadmap.md` 使用 `/opt/nuotao`。
> **本次以 deploy.yml（生产实际执行脚本）为准 = `/opt/nuotao`**，遗留不一致建议后续统一（TODO(tech-debt)）。

## 三、本次变更清单

1. **`infra/systemd/nuotao-agent-scheduler.service`**（新增）
   版本化 systemd 单元，作为部署模板唯一来源（不再只靠 deploy.yml 内联 heredoc）。
2. **`.github/workflows/deploy.yml` §7.5**（修改）
   调度器配置改为「模板优先」：仓库模板存在则直接安装，缺失时才内联生成兜底。
3. **`.github/workflows/db-migration-and-scheduler.yml`**（修改）
   移除 crontab `@reboot + nohup` 启动方式（会与 systemd 双进程重复启动），
   统一为 systemd 管理：daemon-reload → enable → restart。
4. **~~`backend/app/scheduler.py`~~（v1.1 删除）**
   v1.0 曾新增该"兼容入口"，实际被 `app/scheduler/` 包遮蔽而从未生效，已在 v1.1 删除；
   同时删除死代码 `app/scheduler/agent_scheduler.py`、`app/scheduler/agent_scheduler_config.py`
   （每日 08:00 / 5 Agent 版本，无任何入口引用）。
5. **`infra/systemd/nuotao-agent-worker.service`**（v1.1 新增）
   Agent Worker（Redis Streams 队列消费者）此前无任何 systemd 单元，
   `POST /api/v1/agent-tasks` 入队后无人消费。v1.1 补齐该单元并接入 deploy.yml §7.6。
6. **`backend/scripts/seed_agent_config.py`**（v1.1 新增）
   幂等种子：规范 ID 注册 5 个 Agent + 工具白名单（handler_name 对齐真实注册名）
   + 成本护栏 + 审批 SLA，由 CI 在 `alembic upgrade head` 之后执行。
   取代 `scripts/configure_agent_roles.sql`（hyphen ID 与 runtime 冲突，已删除）。
7. **文档统一**：本文件记录部署基线；完整评估与变更清单见 `docs/agent_team_workflow_refactor.md`。

## 四、调度器任务清单（部署后生效）

`app/services/agent_scheduler.py` 实际注册 6 个间隔任务（v1.0 此处漏列 `business_alerts`）：

| 任务 | 频率 | 说明 |
|------|------|------|
| daily_product_analyst | 每 30 分钟 | 库存预警、转化率优化建议 |
| daily_marketing_manager | 每 30 分钟 | 活动 ROAS、文案、SEO（带 `report_truthfulness` 防造假校验） |
| daily_supply_chain_manager | 每 30 分钟 | 库存预警、补货建议 |
| execute_pending_suggestions | 每 15 分钟 | 执行已审批建议（人工审批后自动执行） |
| feedback_learning | 每 60 分钟 | 学习摘要沉淀 |
| business_alerts | 每 360 分钟 | 毛利率/退款率/AOV/断货等业务预警评估 |

另有 3 条 Agent 协作联动规则：`daily_product_analyst → daily_marketing_manager`（5s）、
`daily_supply_chain_manager → daily_product_analyst`（5s）、
`daily_marketing_manager → feedback_learning`（10s）。

> ⚠️ **实现状态如实标注（v1.1）**
>
> `app/tasks/daily_agents.py` 中的 5 个 `run_*_daily` 函数**当前不调用 LLM**
> （文件未 import `llm_gateway`，注释自标"简化版，实际应调用 LLM"），
> 属**规则引擎建议生成器**；不写 `ai_agent_runs`，也不经过 Budget Gate / Execution Policy。
>
> 真正调 LLM 的 5 个 Agent（`app/agents/*.py` → `run_generic_agent` → `llm_gateway`）
> 目前仅通过 API 端点（`/api/v1/agents`、`agents_generic`）与 Worker executor 可达。
>
> **本调度路径与 AGENTS.md §3.1「全链路可审计」存在差距**，已在
> `docs/agent_team_workflow_refactor.md` 列为 P2-1 待办：调度任务改走 `agent_runtime`
> 入队由 Worker 执行，以补齐 `ai_agent_runs` 审计与成本门禁。

## 四·补、Agent Worker（v1.1 新增）

| 项 | 值 |
|----|----|
| 入口 | `python -m app.worker` |
| 职责 | Redis Streams consumer group 消费 `POST /api/v1/agent-tasks` 入队任务；claim → 幂等 → 策略 → 预算门禁 → 并发门禁 → attempt 审计 → 执行 → 重试 → ack |
| Executor 注册 | `product_analyst → product_analyst_executor`；工具 handler 由 `register_m6_tool_handlers()` 注册（v1.1 已补，此前 Worker 进程内工具网关为空） |
| 可观测 | Redis 心跳注册表 `nuotao:agent-worker:*`（TTL 120s，心跳超时 30s 判定 dead）；`GET /api/v1/agent-queue/health`、`/agent-workers` |

> ⚠️ 调度器（`app.services.agent_scheduler`）与 Worker（`app.worker`）是**两个独立 systemd 进程**：
> 调度器负责定时触发规则桩与已审批建议执行，Worker 负责消费队列化任务。两者不互相替代。

## 五、触发与验证

### 触发部署（二选一）
- **自动**：推送 `main/master`，deploy.yml 全流程（ci-gate → staging → production）自动执行；
- **手动**：GitHub Actions → `Deploy to Production (staging-gated)` 或 `DB Migration & Scheduler Setup` → Run workflow。

### 验证命令（服务器上）
```bash
# 服务状态（期望全部 active）
for s in nuotao-backend nuotao-agent-scheduler nuotao-agent-worker postgresql redis nginx; do
  printf '%-28s %s\n' "$s" "$(systemctl is-active $s)"
done

systemctl status nuotao-agent-scheduler --no-pager
systemctl status nuotao-agent-worker   --no-pager
journalctl -u nuotao-agent-scheduler -n 50 --no-pager
journalctl -u nuotao-agent-worker   -n 50 --no-pager

# 单进程检查（期望各为 1，确认无 crontab / compose 双跑）
pgrep -fc 'app.services.agent_scheduler'
pgrep -fc 'app.worker'

# Worker 心跳注册表（有输出说明 worker 已注册并存活）
redis-cli KEYS 'nuotao:agent-worker:*'

# Agent 身份唯一性（期望 5 行 snake_case）
psql "$DATABASE_URL" -c "SELECT agent_id, permission_level, status FROM agents ORDER BY agent_id;"

# 建议幂等键（期望无重复）
psql "$DATABASE_URL" -c \
  "SELECT dedup_key, count(*) FROM agent_suggestions
   WHERE dedup_key IS NOT NULL GROUP BY dedup_key HAVING count(*) > 1;"

# 调度器 last_run 持久化（重启后不重复触发）
redis-cli KEYS 'nuotao:scheduler:*'
```

### 业务侧验证
- `GET /api/v1/agent-suggestions/pending/stats` → 待审批建议可查询；
- 产品状态机 `candidate → selection_approved → … → published` 各节点建议入库、人工审批后可执行。

## 六、风险与缓解

| 风险 | 缓解 |
|------|------|
| 调度器与旧 crontab 双进程 | 本部署已移除 crontab 条目，验证命令含单进程检查 |
| deploy.yml 改动影响生产部署 | 仅改 §7.5 调度器段落 + v1.1 新增 §7.6 Worker 段落，模板优先+兜底；部署前 ci-gate 先行 |
| ~~入口命令不一致~~ | v1.1 已处置：删除被 `app/scheduler/` 包遮蔽的 `app/scheduler.py`，修正 `docker-compose.yml` scheduler 命令为 `python -m app.services.agent_scheduler`；唯一权威入口见「二、部署基线」 |
| Worker 首次上线，队列消费行为未验证 | Worker 单元 `Restart=always`；心跳注册表与 `/agent-queue/health` 可观测；异常时 `systemctl stop nuotao-agent-worker` 即可回退到"仅调度器"现状 |
| 调度器重启导致任务全量重跑、重复灌建议 | v1.1 `last_run` 持久化到 Redis + 建议表 `dedup_key` 唯一索引双重去重 |
| 生产环境执行 `alembic autogenerate` 生成意外迁移 | v1.1 已从 `db-migration-and-scheduler.yml` 移除，仅执行 `upgrade head` |
