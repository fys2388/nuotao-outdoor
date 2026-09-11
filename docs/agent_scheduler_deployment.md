# Agent 调度器部署记录 — 选品→上架任务正式落地

> 版本: v1.0 | 日期: 2026-09-07 | 状态: ✅ 已下令部署（总负责人）
> 关联: `docs/agent_automation_upgrade_p0_p2.md`（P0-1/P0-2/P2-2）

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
| 调度器入口 | `python -m app.services.agent_scheduler` | `backend/app/services/agent_scheduler.py` `__main__` |
| systemd 服务名 | `nuotao-agent-scheduler.service` | 本文件新增版本化模板 |
| 服务用户 | `root`（与 deploy.yml 既有实现一致） | deploy.yml §7.5 |
| 重启策略 | `Restart=always` / `RestartSec=10` | 同 backend 服务 |

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
4. **`backend/app/scheduler.py`**（新增）
   兼容入口 `python -m app.scheduler`，消除文档（M5.11/development.md）与实际入口不一致。
5. **文档统一**：本文件记录部署基线；`docs/agent_automation_upgrade_p0_p2.md` P0-1 验收状态更新。

## 四、调度器任务清单（部署后生效）

| 任务 | 频率 | 说明 |
|------|------|------|
| daily_product_analyst | 每 30 分钟 | 选品评分、竞品监控、利润模型 |
| daily_marketing_manager | 每 30 分钟 | 活动 ROAS、文案、SEO（带防造假校验） |
| daily_supply_chain_manager | 每 30 分钟 | 库存预警、补货建议 |
| execute_pending_suggestions | 每 15 分钟 | 执行已审批建议（人工审批后自动执行） |
| feedback_learning | 每 60 分钟 | 学习摘要沉淀 |

## 五、触发与验证

### 触发部署（二选一）
- **自动**：推送 `main/master`，deploy.yml 全流程（ci-gate → staging → production）自动执行；
- **手动**：GitHub Actions → `Deploy to Production (staging-gated)` 或 `DB Migration & Scheduler Setup` → Run workflow。

### 验证命令（服务器上）
```bash
systemctl is-active nuotao-agent-scheduler      # 期望 active
systemctl status nuotao-agent-scheduler --no-pager
journalctl -u nuotao-agent-scheduler -n 50 --no-pager   # 查看调度日志
ps aux | grep agent_scheduler                   # 确认仅一个进程（无双跑）
```

### 业务侧验证
- `GET /api/v1/agent-suggestions/pending/stats` → 待审批建议可查询；
- 产品状态机 `candidate → selection_approved → … → published` 各节点建议入库、人工审批后可执行。

## 六、风险与缓解

| 风险 | 缓解 |
|------|------|
| 调度器与旧 crontab 双进程 | 本部署已移除 crontab 条目，验证命令含单进程检查 |
| deploy.yml 改动影响生产部署 | 仅改 §7.5 调度器段落，模板优先+兜底；部署前 ci-gate 先行 |
| 入口命令不一致 | 新增 `app/scheduler.py` 兼容入口，新旧命令均可用 |
