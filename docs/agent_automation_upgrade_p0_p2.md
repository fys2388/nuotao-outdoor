# AI Agent 自动化升级方案 P0-P2

> 版本: v1.0 | 日期: 2026-09-06 | 分支: feature/agent-automation-upgrade

## 背景

当前系统五大 Agent 代码完整、运行时框架齐全，但存在三大缺口：
1. 服务器上跑的是独立 Cron shell 脚本，未通过 `agent_runtime.py` 统一调度
2. Agent 建议推送到飞书后即终止，无执行→反馈闭环
3. 无成长记忆、无自进化、无自动回滚

## P0：核心闭环（优先级最高，5天）

### P0-1: Agent 运行时统一调度

**目标**: 将3个每日 Cron Agent 接入 `agent_runtime.py`，实现可监控、可管理、可审计。

**实现**:
- 新增 `backend/app/services/agent_scheduler.py` — 定时任务调度器，替代 Cron shell 脚本
- 新增 `backend/app/tasks/daily_agents.py` — 每日 Agent 任务定义（产品/营销/供应链）
- 修改 `setup-ai-agent-automation.sh` — 改为调用 `python -m app.scheduler` 而非独立 shell
- Agent 运行结果写入 `ai_agent_runs` 表（已有模型），可通过 API 查询

**验收**:
- [x] 调度器部署件已补齐（2026-09-07 总负责人下令，见 `docs/agent_scheduler_deployment.md`）：infra/systemd 版本化模板 + deploy.yml §7.5 模板优先 + db-migration-and-scheduler.yml 移除 crontab 双启动 + 兼容入口 `backend/app/scheduler.py`
- [ ] 3个 Agent 通过运行时调度执行，结果入库
- [ ] API 可查询 Agent 运行历史（输入/输出/成本/状态）
- [ ] Agent 失败自动告警到飞书

### P0-2: 建议→审批→执行→反馈闭环

**目标**: Agent 生成的建议不再是终点，而是进入审批队列，人工确认后自动执行，结果回流。

**实现**:
- 新增 `backend/app/models/agent_suggestion.py` — 建议表（agent_id, type, content, status, approval_by, execution_result, feedback_score）
- 新增 `backend/app/services/agent_suggestion_service.py` — 建议生命周期管理
- 新增 `backend/app/api/v1/endpoints/agent_suggestions.py` — 建议审批 API（列表/审批/拒绝/执行）
- 新增 `backend/app/services/execution_router.py` — 执行路由器，根据建议类型调用对应服务
  - 产品优化建议 → `product_service.py`
  - 营销优化建议 → `marketing.py`
  - 库存补货建议 → `inventory_service.py` + `procurement_service.py`
- 新增 `backend/app/services/feedback_loop.py` — 反馈回流，执行结果写入建议表，定期汇总给 Agent 优化提示词

**验收**:
- [ ] Agent 建议自动入库，状态为 pending_approval
- [ ] 前端/API 可审批建议
- [ ] 审批通过后自动执行，执行结果记录
- [ ] 执行结果回流，Agent 下次运行时可参考历史反馈

## P1：智能学习（4天）

### P1-1: 成长记忆模块

**目标**: Agent 经验持久化积累，跨天/跨周知识不丢失。

**实现**:
- 新增 `backend/app/models/growth_memory.py` — 成长记忆表（agent_id, memory_type, content, source, confidence, tags, created_at, last_accessed）
- 新增 `backend/app/services/growth_memory_service.py` — 记忆 CRUD + 检索（按 agent/标签/时间/相似度）
- 新增 `backend/app/services/memory_consumer.py` — 记忆消费者，Agent 运行时自动注入相关记忆
- 记忆类型: success_pattern（成功模式）、failure_lesson（失败教训）、market_insight（市场洞察）、customer_preference（客户偏好）、optimization_result（优化结果）

**验收**:
- [ ] Agent 每次运行后自动沉淀关键经验到记忆库
- [ ] Agent 运行时自动检索相关历史记忆注入上下文
- [ ] 记忆可按 Agent/类型/时间查询

### P1-2: A/B 测试结果自动更新策略

**目标**: A/B 测试结论自动更新营销策略，无需人工干预。

**实现**:
- 修改 `experiment_automation_service.py` — 新增测试结论自动评估（统计显著性判断）
- 新增 `backend/app/services/strategy_updater.py` — 策略更新器，根据 A/B 结论自动更新营销配置
- 新增 `backend/app/models/strategy_version.py` — 策略版本表，记录每次策略变更（可回滚）
- 策略更新需经审批（高风险），低风险（如文案优化）可自动执行

**验收**:
- [ ] A/B 测试达到统计显著性后自动生成结论
- [ ] 结论经审批后自动更新营销策略
- [ ] 策略变更有版本记录，可回滚

## P2：运维与运营自动化（5天）

### P2-1: 部署失败自动回滚 + 灰度发布

**目标**: 部署失败自动回滚，支持灰度发布降低风险。

**实现**:
- 修改 `.github/workflows/deploy.yml` — 新增部署前自动备份（代码+数据库）
- 新增 `infra/deploy-rollback.sh` — 回滚脚本（代码回滚 + 数据库回滚 + 服务重启）
- 修改 deploy.yml — 健康检查失败后自动调用回滚脚本
- 新增灰度发布支持: 先部署到 staging 环境，验证通过后再推 prod
- 新增 `infra/health-check-enhanced.sh` — 增强健康检查（API端点+数据库+前端+关键业务流程）

**验收**:
- [ ] 部署失败后5分钟内自动回滚到上一版本
- [ ] 支持 staging → prod 两阶段发布
- [ ] 回滚后自动发送飞书告警

### P2-2: 选品→上架全链路自动化

**目标**: 选品审批通过后自动完成产品信息录入→文案生成→图片处理→WooCommerce上架。

**实现**:
- 修改 `product_pipeline_service.py` — 完善流水线状态机（选品→信息录入→文案→图片→定价→库存→上架→SEO）
- 新增 `backend/app/services/pipeline_orchestrator.py` — 流水线编排器，自动推进状态
- 新增 `backend/app/api/v1/endpoints/pipeline.py` — 流水线监控 API
- 选品审批通过后自动触发:
  1. 1688 产品信息自动抓取（`sourcing_1688_service.py`）
  2. AI 文案生成（`content_generation_service.py`）
  3. AI 图片生成/优化（`image_generation_service.py`）
  4. 定价计算（`cost_model_service.py`）
  5. WooCommerce 自动上架（`woocommerce_sync_service.py`）
  6. SEO 提交（`seo_service.py`）
- 每个环节失败可重试，人工可介入

**验收**:
- [ ] 选品审批通过后自动触发流水线
- [ ] 流水线各环节自动推进，状态可监控
- [ ] 最终自动上架到 WooCommerce
- [ ] 失败环节可重试/人工介入

## 实施顺序

```
P0-1 (运行时调度) → P0-2 (建议闭环) → P1-1 (成长记忆) → P1-2 (AB策略) → P2-1 (回滚灰度) → P2-2 (选品上架)
```

## 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| Agent 自动执行出错 | 高风险操作必须人审，低风险自动执行，所有操作可回滚 |
| 部署回滚失败 | 回滚前双重备份，回滚脚本独立测试 |
| 选品流水线卡住 | 每个环节有超时和重试，人工可随时介入 |
| 成长记忆污染 | 记忆有人工审核机制，低置信度记忆不自动注入 |
