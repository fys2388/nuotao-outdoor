# Agent / Agents Team 工作流重构 — 部署接线与身份治理

> 版本: v1.0 | 日期: 2026-09-20 | 状态: ✅ 本轮已落地（P0 + P1）
> 关联: `AGENTS.md` §1/§3、`docs/agent_scheduler_deployment.md`、`docs/ai_agent_config_summary.md`
> 决策人: 总负责人 | 范围: P0 部署接线 + P1 能力闭环 | 身份策略: 保留 5 角色，统一 snake_case

---

## 一、评估结论

按「优秀 Agent 五维能力 + 优秀 Agents Team 六维能力」框架逐项核查后，结论是：

**不是 Agent 太多，而是"身份膨胀 + 能力未接线"。**

- 5 个概念角色与 `AGENTS.md` §1.1 五岗位定位一一对应，能力互补、无盲区，数量合理；
- 但同一角色在 3 条互不相通的注册路径中产生了 **11 个 Agent 身份**，且真实执行路径与文档口径脱节；
- 唯一"能调 LLM + 过成本门禁"的 Worker 进程**从未部署**；唯一被部署的 Scheduler 跑的是**不调 LLM、不落审计**的规则桩。

### 1.1 身份清单（重构前）

| 身份 | 注册来源 | 模型 | 可执行 |
|---|---|---|---|
| `product_analyst` | `app/agents/agent_seed.py` | gpt-4o-mini | ✅ 唯一有 executor |
| `marketing_manager` / `supply_chain_manager` / `customer_manager` / `business_analyst` | `init_all_agents.py` + `app/agents/*.py` | — | ⚠️ 仅 API on-demand |
| `product-manager` / `marketing-manager` / `supply-chain-manager` / `customer-manager` / `business-analyst` | `scripts/configure_agent_roles.sql` | deepseek-chat | ❌ 零引用 |
| `customer_service_manager` | `init_all_agents.py` | — | ❌ 客户角色第三 ID |

### 1.2 执行路径真实分布（重构前）

| 进程 | 部署 | 工具 handler | 工具循环 | 写 `ai_agent_runs` | 过预算门禁 |
|---|---|---|---|---|---|
| API (`uvicorn`) | ✅ | 5 个 | 有 | ✅ | ❌ |
| Scheduler (systemd) | ✅ | 0 | ❌ | ❌ | ❌ |
| Worker (`python -m app.worker`) | **❌ 无 systemd 单元** | **0** | **❌** | ✅ | ✅ |

### 1.3 工具层断裂（重构前）

- `scripts/register_agent_tools.sql` 注册 26 个工具，`handler_name` 写成 `module.func` 路径形式；
- 实际注册进网关的 handler 只有 5 个：`generate_product_image`、`generate_activity_plan`、`match_influencers`、`localize_listing`、`get_customer_template`；
- **0 个名字匹配** → 26 个工具全部 whitelist-only（仅审计、不可执行），含 2 个 L3 高风险工具；
- 反过来那 5 个真 handler 不在白名单 → 任何 Agent 调用会被门禁拒绝；
- `get_m6_tool_registry()` 定义了但全仓零调用，所以这 5 个工具也从未入库。

---

## 二、本轮变更清单（P0 + P1）

### P0 — 部署接线

| # | 变更 | 文件 |
|---|---|---|
| 1 | 新增 Worker systemd 单元（`User=nuotao`，与 backend 一致，消除调度器 `User=root` 的权限偏差） | `infra/systemd/nuotao-agent-worker.service` |
| 2 | deploy.yml 新增 §7.6 安装并启动 Worker；§7.4 之后新增 §3.6 幂等种子步骤 | `.github/workflows/deploy.yml` |
| 3 | CI 幂等种子：规范 ID 注册 5 Agent + 工具白名单（handler_name 用真实注册名，无 handler 的置空）+ 成本护栏 + 审批 SLA | `backend/scripts/seed_agent_config.py` |
| 4 | Worker 进程补齐工具 handler 注册（否则进程内工具网关为空） | `backend/app/worker/__main__.py` |
| 5 | 修正 compose scheduler 命令（原命令实际跑的是 AlertScheduler） | `docker-compose.yml` |
| 6 | 删除被 `app/scheduler/` 包遮蔽的死代码兼容入口 | `backend/app/scheduler.py`（删除） |
| 7 | 删除死代码调度器（每日 08:00 / 5 Agent 版本，无入口引用） | `backend/app/scheduler/agent_scheduler.py`、`agent_scheduler_config.py`（删除） |
| 8 | 删除与 runtime 身份冲突的 SQL 配置（改由 CI 种子接管） | `scripts/configure_agent_roles.sql`（删除） |
| 9 | 3 个巡检工作流服务清单补 `nuotao-agent-worker` | `post-deploy-verify.yml`、`system-health-check.yml`、`server-preflight.yml` |
| 10 | 移除生产环境 `alembic revision --autogenerate`（只保留 `upgrade head`） | `.github/workflows/db-migration-and-scheduler.yml` |

### P1 — 能力闭环

| # | 变更 | 文件 |
|---|---|---|
| 11 | 建议表增加 `dedup_key`（唯一索引），调度任务按 `workspace+agent+type+时间窗` 去重，杜绝 `Restart=always` 后全量重跑灌入重复建议 | `backend/alembic/versions/0035_agent_suggestion_dedup_key.py`、`app/models/agent_suggestion.py`、`app/services/agent_suggestion_service.py` |
| 12 | 调度器 `last_run` 从进程内存持久化到 Redis（键 `nuotao:scheduler:task:<任务名>`，TTL 7 天），重启后不重复触发 | `app/services/agent_scheduler.py` |
| 13 | 去除调度/建议路径的硬编码 workspace，统一改从 `app.core.workspace` 读取 | `app/services/agent_scheduler.py`、`app/tasks/daily_agents.py` |

### 明确不在本轮范围（P2，另行立项）

- 调度任务改走 `agent_runtime` 入队由 Worker 执行真实 LLM Agent（需先验证 Worker 生产稳定性，避免一步到位引入新风险）；
- 引入 Captain / Reviewer / Repair 三类团队角色，用显式 DAG + 任务契约替代 6 个并行间隔任务；
- AGENTS.md §4.5 要求的 LLM 输入输出注入防护；
- 职责交叉收敛（库存补货归 `supply_chain_manager`，客户触达归 `marketing_manager`）；
- `services/newton_agent_service.py` 归位到 `integrations/`；
- 部署路径基线统一（`/opt/nuotao-ai-os` → `/opt/nuotao`，`infra/*.sh` 与 5 篇 docs 共 13+ 处）。

### 二·补 落地状态（本地已验证 / 待生产执行）

| 项 | 状态 | 证据 |
|---|---|---|
| P0 #1–#10 代码与工作流改动 | ✅ 已落地 | `git diff --stat` 覆盖 5 个工作流 + 2 个 compose + 2 个 systemd + 2 个删除 |
| P0 #3 种子脚本可导入、数据自洽 | ✅ 已验证 | 5 Agent / 31 工具（26 白名单 + 5 真实 handler）/ 31 schema 全覆盖 / L3 仅 `publish_woocommerce_product`、`submit_1688_order` / 预算合计 $230.00 |
| P0 #4 Worker 工具网关补齐 | ✅ 已验证 | `register_m6_tool_handlers()` 后 `TOOL_HANDLERS` = 5 个真实名，与 `M6_TOOL_HANDLERS` 逐一匹配 |
| P0 #10 迁移链完整 | ✅ 已验证 | `alembic heads` → `0035 (head)` |
| P1 #11–#13 模块可导入 | ✅ 已验证 | `app.worker` / `app.worker.__main__` / `agent_scheduler` / `daily_agents` / `agent_suggestion_service` / `agent_suggestion` 全部 import OK |
| 相关单测 | ✅ 通过 | `pytest -k "suggestion or scheduler or worker or prompt or tool" --ignore=tests/integration` → 52 passed |
| `backend/scripts/*.py` 被 `.gitignore` 排除 | ⚠️ 已修复 | 新增例外 `!/backend/scripts/seed_agent_config.py`（否则 CI 拿不到种子脚本，deploy.yml §3.6 必失败） |
| 集成测试（Redis/Postgres 真机） | ⛔ 本地无法验证 | `tests/integration/*` 因本机无 Redis 服务在 fixture 阶段 ERROR（`redis server did not become ready`），与本次改动无关 |
| P0 全部生产效果 | ⏳ 待生产执行 | 需人工触发 `deploy.yml`；未获得部署授权前不推送 |
| P2 全部项 | 📋 已记录未实施 | 见上方 P2 清单，另行立项 |

> **诚实边界**：本次改动**没有**改变任何 Agent 的提议者/执行者边界，
> 也没有改变 L0–L3 权限门禁与人工审批流程。种子脚本把 21 个无 handler 的
> 工具写成 `handler_name=None`（白名单即审计），这是**收紧**而非放开；
> 只有 `m6_tool_registry` 中真实存在的 5 个工具被标记为可执行。

---

### 二·补2 LLM 智能分析能力实测覆盖（2026-09-21 复核）

结论：**部署后 5 个规范角色均具备 LLM 能力，但只在 on-demand 触发时生效；
没有任何角色在定时调度路径上真正调用 LLM。**

| 角色 | REST 入口 | 种子创建的 prompt | 定时路径 LLM |
|---|---|---|---|
| `product_analyst` | `POST /agents/product-analysis`（`agents.py`） | `AGENT_PRODUCT_ANALYST` ✅（`PRODUCT_ANALYST` 由迁移 0006 提供） | ❌ |
| `marketing_manager` | `POST /agents/marketing-manager/analyze` | `AGENT_MARKETING_MANAGER` ✅ | ❌ |
| `supply_chain_manager` | `POST /agents/supply-chain-manager/analyze` | `AGENT_SUPPLY_CHAIN_MANAGER` ✅ | ❌ |
| `customer_manager` | `POST /agents/customer-service-manager/analyze` | `AGENT_CUSTOMER_MANAGER` ✅ | ❌ |
| `business_analyst` | `POST /agents/business-analyst/analyze` | `AGENT_BUSINESS_ANALYST` ✅ | ❌ |
| `activity_planner`（服务级） | `activity_planner.py` + M6 工具 | `ACTIVITY_PLANNER_V1` ✅ | ❌ |
| 客服回复（服务级） | `customer_template_service` | `CUSTOMER_RESPONSE_V1` ✅ | ❌ |
| listing 本地化（服务级） | `listing_localization_service` | `LISTING_LOCALIZATION_V1` ✅ | ❌ |

本轮修的 3 处 LLM 可用性缺陷：

1. **种子脚本漏 4 个线上 prompt**（已修）：`ACTIVITY_PLANNER_V1`、
   `CUSTOMER_RESPONSE_V1`、`LISTING_LOCALIZATION_V1`、
   `AGENT_CUSTOMER_SERVICE_MANAGER`。前三个已补入 `SERVICE_PROMPTS`；
   第四个通过下面的身份收敛消除。
   后果原本是：`generate_activity_plan` / `localize_listing` 两个被登记为
   「有 handler 可执行」的 M6 工具，第一次调用就会 `PromptNotFoundError`。
2. **`customer_service_manager` 分叉身份**（已修）：`agents_generic.py` 的
   `customer-service-manager` 配置块改指 `customer_manager` +
   `AGENT_CUSTOMER_MANAGER`。**URL key 保持不变**，现有客户端不受影响；
   仅 `ai_agent_runs.agent` 与 prompt 查找改到规范身份。
3. **prompt 覆盖校验**：全仓扫描 `prompt_name=` / `"prompt_name":` /
   `PROMPT_NAME =` 三种形态，确认 `app/` 内引用的 9 个 prompt 名
   全部有来源（8 个由种子创建 + `PRODUCT_ANALYST` 由迁移 0006 插入）。

仍未闭合的 LLM 缺口（P2）：

- **定时路径零 LLM**：`app/tasks/daily_agents.py` 800 行、11 个建议调用点，
  实际 0 个 LLM 调用。全文件仅第 5、10 行 docstring 提到 `llm_gateway`，
  正文是硬编码 stub（`简化版，实际应从 product_intelligence_service 获取`）。
  该模块是每 15–360 分钟真正自动运行的路径，产出无任何 LLM 分析。
- **`app/agents/` 下 4 个角色模块为死代码**（~37KB）：`marketing_manager.py`、
  `supply_chain_manager.py`、`customer_manager.py`、`business_analyst.py`
  均真实调用 `run_generic_agent`，但被 `agents_generic.py` 的内联
  `system_instruction` 取代，除 `app/agents/__init__.py` re-export 外零调用。
- **Worker `llm_executor` 无工具循环**：`executor.py:83-94` 只有单次
  `llm_gateway.complete()`，从不调用 `execute_tool_call`，是单轮提示而非 agentic。
- **`main.py:61-62`** 明确 `Worker + Scheduler temporarily disabled in-process`，
  进程内不跑；依赖本轮新增的独立 systemd worker。

### 二·补3 SenseNova 主模型接入（2026-09-21）

主模型切换为 **SenseNova（商汤）`sensenova-6.8-flash-lite`**，兜底 DeepSeek。

| 项 | 值 |
|---|---|
| Base URL | `https://token.sensenova.cn/v1`（OpenAI 兼容 `/chat/completions`） |
| 模型 | `sensenova-6.8-flash-lite` |
| Key 名称 | `nuotao-ai-os`（掩码 `sk-A••••••YRpr`，长期有效） |
| 定价 | Free 公测，**$0 / token** |

改动（5 处代码 + 3 处 env，全部已本地验证）：

1. `app/core/config.py`：新增 `sensenova_api_key` / `sensenova_base_url` /
   `sensenova_default_model`；`llm_provider` 默认值 → `sensenova`；
   `llm_max_tokens` 1500 → **4000**。
2. `app/services/llm_gateway.py`：`SUPPORTED_PROVIDERS` 加入 `sensenova`；
   `PRICING` 加入 `"sensenova:sensenova-6.8-flash-lite": (0, 0)`；
   `_provider_config()` 增加 sensenova 分支。
3. `app/schemas/agent_runtime.py`：`model_provider` Literal 扩为
   `("sensenova", "openai", "deepseek")`，默认 sensenova。
4. `app/models/agent_runtime.py`：列默认值同步为 sensenova。
5. `scripts/seed_agent_config.py`：5 个 Agent 的 `model_provider` /
   `model_name` 全部指向 sensenova。

env（均已确认被 `.gitignore` 排除，key 不入库）：

- `/.env`（**优先级最高**，见下方注意）
- `backend/.env`
- `backend/.env.production`

⚠️ **两个必须知道的坑**：

1. **`sensenova-6.8-flash-lite` 是推理模型**。每次调用先在
   `message.reasoning` 里产出推理 token，再产出 `message.content`。
   `max_tokens` 必须同时容纳两者：实测一条 `max_tokens=20` 的请求，
   20 个 token 全部耗在 reasoning 上，`finish_reason=length`，
   **`content` 为空**。已把默认 `llm_max_tokens` 提到 4000。
   若某条路径传了很小的显式 `max_tokens`，会出现"LLM 有响应但正文为空"。
2. **根目录 `.env` 会覆盖 `backend/.env`**。`Settings.model_config` 的
   `env_file=(".env", "../.env")` 按顺序读取、**后者胜出**，所以本地开发
   的 LLM 配置必须写在**根目录** `.env`。只改 `backend/.env` 不生效。

🔧 **顺带发现的生产配置漂移**：`backend/.env.production` 原本写的是
`LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`——这三个名字在 `Settings` 里
**没有对应字段**，被 `extra="ignore"` 静默丢弃。即生产环境此前
`deepseek_api_key` 恒为默认空串，**任何 LLM 调用都拿不到 key**。已改为
`SENSENOVA_*` / `DEEPSEEK_*` 的正确字段名，并加了注释说明原因。

端到端验证（临时脚本，已删除）：`llm_gateway.complete()` 走项目自身网关
真实返回 `provider=sensenova / model=sensenova-6.8-flash-lite / content=OK`；
`estimate_cost("sensenova", ..., {1k,1k})` = `0.000000`（Free 模型不占用预算）。

---

## 三、部署验证清单

```bash
# 1) 四个服务全部 active
for s in nuotao-backend nuotao-agent-scheduler nuotao-agent-worker postgresql redis nginx; do
  printf '%-28s %s\n' "$s" "$(systemctl is-active $s)"
done

# 2) Worker 心跳注册表（Redis）
redis-cli KEYS 'nuotao:agent-worker:*'

# 3) Agent 身份唯一性（期望：5 行，全部 snake_case）
psql "$DATABASE_URL" -c "SELECT agent_id, permission_level, status FROM agents ORDER BY agent_id;"

# 4) 工具白名单与 handler 可执行性
psql "$DATABASE_URL" -c \
  "SELECT tool_name, permission_level, handler_name,
          (handler_name IS NULL) AS whitelist_only
   FROM agent_tools WHERE enabled ORDER BY permission_level, tool_name;"

# 5) 预算策略已入库
psql "$DATABASE_URL" -c "SELECT agent_id, monthly_budget FROM agent_budget_policies;"

# 6) 建议幂等键生效（重复调度不产生重复建议）
psql "$DATABASE_URL" -c \
  "SELECT dedup_key, count(*) FROM agent_suggestions
   WHERE dedup_key IS NOT NULL GROUP BY dedup_key HAVING count(*) > 1;"

# 7) 调度器状态已持久化（重启前后 last_run 保留）
redis-cli KEYS 'nuotao:scheduler:*'

# 8) 双进程检查（期望均为 1）
pgrep -fc 'app.services.agent_scheduler'
pgrep -fc 'app.worker'

# 9) Prompt 覆盖检查（期望 8 个种子 prompt 全部 active，
#    另 PRODUCT_ANALYST 由迁移 0006 提供，共 9 个可被 LLM 路径引用）
psql "$DATABASE_URL" -c \
  "SELECT name, version, status FROM prompts
   WHERE workspace_id = '00000000-0000-0000-0000-000000000001'
     AND name IN ('AGENT_PRODUCT_ANALYST','AGENT_MARKETING_MANAGER',
                  'AGENT_SUPPLY_CHAIN_MANAGER','AGENT_CUSTOMER_MANAGER',
                  'AGENT_BUSINESS_ANALYST','ACTIVITY_PLANNER_V1',
                  'CUSTOMER_RESPONSE_V1','LISTING_LOCALIZATION_V1',
                  'PRODUCT_ANALYST')
   ORDER BY name;"

# 10) LLM 网关真机冒烟（期望：content 非空且含 OK，provider=sensenova）
cd /opt/nuotao/backend && .venv/bin/python -c "
import asyncio
from app.core.config import get_settings
from app.services import llm_gateway

s = get_settings()
assert s.llm_provider == 'sensenova', s.llm_provider
assert s.sensenova_api_key, 'SENSENOVA_API_KEY not set'
r = asyncio.run(llm_gateway.complete(llm_gateway.LLMRequest(
    messages=[{'role':'user','content':'Reply with exactly: OK'}],
    task_type='deploy.smoke')))
print('provider =', r.provider)
print('model    =', r.model)
print('tokens   =', r.tokens)
print('content  =[%s]' % r.content.strip())
assert r.provider == 'sensenova'
assert 'OK' in r.content, 'empty content -> check LLM_MAX_TOKENS vs reasoning tokens'
print('LLM smoke OK')
"
```

---

## 四、风险与缓解

| 风险 | 缓解 |
|---|---|
| Worker 首次上线，生产 Redis Stream 消费行为未验证 | §3.6 种子先于 Worker 安装执行；Worker 单元 `Restart=always` + 心跳注册表可观测；`queue_health_max_pending` 阈值告警；异常时 `systemctl stop nuotao-agent-worker` 即可回退到"仅调度器"现状 |
| 种子脚本误删既有 Agent 数据 | 全部为 upsert 语义（`create-if-missing` / `UPDATE`），不执行 `DELETE`；`agents` 表数据可回滚 |
| `dedup_key` 唯一索引与历史数据冲突 | 迁移中 `dedup_key` 为可空列，历史行不回填；仅新建建议带键 |
| 删除 `configure_agent_roles.sql` 影响已有环境 | 该脚本仅 `UPDATE agents`，已由 CI 种子以同一语义接管；hyphen ID 行不删除，仅停止更新 |
| 移除 `autogenerate` 后遗漏新表 | 迁移文件在仓库内版本化，CI 只执行 `upgrade head`；本地开发仍可用 `alembic revision --autogenerate` 生成 |

---

## 五、后续里程碑建议

1. **P2-1 Worker 稳定运行 7 天**后，把 `daily_agents.py` 改为走 `agent_runtime` 入队（真实 LLM + 成本门禁 + `ai_agent_runs` 审计），规则桩降级为 `rule_based_suggestions.py`；
2. **P2-2** 引入 Captain 编排角色，用任务契约（`objective`/`acceptance`/`inScope`/`verify`）替代固定间隔任务；
3. **P2-3** 推广 `report_truthfulness` 的防造假校验到全部 5 个 Agent（当前仅营销经理接入）；
4. **P2-4** 实现 LLM 输入输出注入防护，补齐 AGENTS.md §4.5。
