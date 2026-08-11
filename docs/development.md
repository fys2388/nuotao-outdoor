# 开发启动文档（Development Guide）

适用于 M0 工程基座。规划与决策文档见 `docs/` 其他文件。

## 1. 前置条件

| 工具 | 版本 | 说明 |
|---|---|---|
| Python | >= 3.12 | 后端运行时（AGENTS.md 技术基线） |
| Docker + Compose | 任意较新版本 | 一键启动基础设施（postgres/redis/backend） |
| Node.js（可选） | >= 20 | 前端占位工程，M1 正式搭建 |

> 未安装 Docker 时：可用本机 PostgreSQL 16 + Redis 7 代替，或仅运行不依赖外部服务的测试。

## 2. 环境配置

```bash
cp .env.example .env
```

- 后端 `Settings`（`backend/app/core/config.py`）从环境变量或 `.env`（当前目录或其父目录）读取配置。
- 所有密钥只放 `.env` / Secrets，禁止提交仓库（见 `.gitignore`）。

## 3. 方式 A：Docker Compose（推荐）

```bash
docker compose up --build
```

- 服务：`postgres:16-alpine`、`redis:7-alpine`、`backend`（自动执行 `alembic upgrade head` 后启动 uvicorn）。
- 验证：`curl http://localhost:8000/api/v1/healthz` 返回 `{"status":"ok"}`。
- 日志：`docker compose logs -f backend`。
- 停止：`docker compose down`（保留数据卷）；彻底清理：`docker compose down -v`。

## 4. 方式 B：本地 venv 开发

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows
pip install -e ".[dev]"
```

启动基础设施（若已安装 Docker，仅启动依赖）：

```bash
docker compose up -d postgres redis
```

执行迁移并启动服务：

```bash
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

## 5. 数据库迁移（Alembic）

```bash
cd backend
alembic upgrade head        # 应用所有迁移
alembic downgrade -1        # 回退一步
alembic revision --autogenerate -m "describe change"   # 基于模型自动生成（M1 起使用）
alembic history            # 查看迁移历史
```

- `alembic/env.py` 已接入应用配置（`DATABASE_URL`）与 `Base.metadata`。
- M0 基线迁移（`0001_baseline`）不建业务表；领域表随 M1 领域模型加入。
- 迁移文件必须在 PR 中评审；禁止直接手工改库。

## 6. 测试

```bash
cd backend
pytest                 # 单元/接口测试（含健康检查依赖降级用例）
ruff check .           # 代码规范
```

- 测试策略分层见 `tests/README.md`；M0 测试不依赖外部服务（使用依赖覆盖）。
- CI（`.github/workflows/ci.yml`）：push/PR 自动执行 ruff + pytest。

## 7. 常用脚本速查

| 操作 | 命令 |
|---|---|
| 启动后端（本地） | `uvicorn app.main:app --reload` |
| 查看 OpenAPI | `http://localhost:8000/docs` |
| 存活探针 | `GET /api/v1/healthz` |
| 就绪探针 | `GET /api/v1/readyz` |
| 运行全部测试 | `pytest` |
| 代码检查 | `ruff check .` |
| 自动修复 | `ruff check . --fix` |
## 7. WooCommerce Webhook（订单接入）

M1.5 已落地 `POST /api/v1/webhooks/woocommerce` 订单接收闭环（order.created），
配置与行为如下。

### 7.1 环境变量

```bash
# .env（本地/CI 示例值；生产必须替换为强随机密钥）
WOOCOMMERCE_WEBHOOK_SECRET=dev-webhook-secret-change-me

# 支付手续费估算（利润快照使用；WooCommerce 未提供手续费时）
PAYMENT_FEE_RATE=0.029
PAYMENT_FEE_FIXED=0.30
```

### 7.2 WooCommerce 后台注册

1. WooCommerce → Settings → Advanced → Webhooks → Add webhook。
2. 名称 `nuotao-order-created`；Topic 选择 `Order created`（order.created）。
3. Delivery URL 填后端地址：`https://<your-domain>/api/v1/webhooks/woocommerce`。
4. Secret 与 `WOOCOMMERCE_WEBHOOK_SECRET` 保持一致（WooCommerce 用它对请求体做
   HMAC-SHA256 签名，放入 `X-Wc-Webhook-Signature` 头）。
5. Status 设为 Active，保存后可在 Webhook 列表点击 Deliver 测试投递。

### 7.3 行为与重试

- 签名校验失败 → 401；payload 非法 → 400；支付网关 topic（含
  `woocommerce.payments.gateways` 键）→ 404；均不重试。
- 成功创建 → 201 `{"status": "created", ...}`；重复投递 → 200
  `{"status": "duplicate", ...}`（幂等，不产生新订单/事件）。
- 服务端错误（500）由 WooCommerce 按指数退避自动重试，幂等约束保证重试安全。
- 全链路 `trace_id`：响应头 `x-trace-id`，并写入 orders / event_log /
  rule_execution_logs，可用于跨系统排查。

### 7.4 本地验证

```bash
cd backend
pytest tests/test_webhook_orders.py -q   # 验签/幂等/payload/规则/审计
```
## 8. 订单查询与产品智能（M1.6 / M2.1）

### 8.1 订单查询

```bash
# 列表：status / external_order_id / sku / date_from / date_to / 分页 / 排序
curl "http://localhost:8000/api/v1/orders?status=received&sku=SKU-001&sort_by=total&sort_order=desc&limit=20"
# 详情（含行明细与利润/规则快照）
curl "http://localhost:8000/api/v1/orders/<order-uuid>"
```

### 8.2 产品智能

```bash
# 人工录入（1688 URL / 供应商 / 采购成本 / 重量 / 尺寸 / 目标市场），自动评分
curl -X POST http://localhost:8000/api/v1/products/intake \
  -H "Content-Type: application/json" \
  -d '{"title":"Camping Headlamp","source_type":"1688","source_url":"https://detail.1688.com/offer/1.html","purchase_cost":"10.00","weight_kg":"0.3","dimensions":{"length":8,"width":5,"height":4},"target_market":"US"}'

# 查看智能聚合（评分 + 分析审计 + 决策）
curl "http://localhost:8000/api/v1/products/<product-uuid>/intelligence"

# 决策工作流：提议 -> 审批
curl -X POST http://localhost:8000/api/v1/products/<product-uuid>/decisions
curl -X POST http://localhost:8000/api/v1/product-decisions/<decision-uuid>/approve \
  -H "Content-Type: application/json" -d '{"actor":"owner@nuotao.example"}'
```

- 评分维度：profit / logistics / demand / competition / differentiation / compliance（0-10），总分 0-100；
  权重 30/20/15/10/15/10（v1，见 `docs/product_strategy.md` §6）。
- 成本历史 `product_cost_snapshots` 只追加；利润快照含 `cost_status` / `profit_confidence`，
  UNKNOWN 成本时 `PROFIT-003` 硬规则拒绝盈利结论。


### 8.3 产品智能数据完整性（M2.1.5）

```bash
# 产品录入（新增落地成本分量字段）
curl -X POST http://localhost:8000/api/v1/products/intake \
  -H "Content-Type: application/json" \
  -d '{"title":"Camping Headlamp","source_type":"1688","source_url":"https://detail.1688.com/offer/1.html","purchase_cost":"10.00","domestic_shipping":"1.50","international_shipping":"4.20","packaging":"0.80","tax_estimate":"1.20","handling":"0.50","weight_kg":"0.3","dimensions":{"length":8,"width":5,"height":4},"target_market":"US"}'

# 供应商候选（一个产品多个供应商报价）
curl -X POST http://localhost:8000/api/v1/products/<product-uuid>/candidates \
  -H "Content-Type: application/json" \
  -d '{"supplier_code":"S-1688-01","source_type":"1688","source_url":"https://detail.1688.com/offer/2.html","purchase_price":"8.50","moq":50,"lead_time_days":7,"trend_score":8.0,"profit_model":{"margin_rate":0.42},"notes":"factory A"}'
curl "http://localhost:8000/api/v1/products/<product-uuid>/candidates"

# 评分证据（每次评分逐维度：score/source/evidence/confidence）
curl "http://localhost:8000/api/v1/product-decisions/scores/<score-uuid>/evidence"

# 产品测试闭环：proposed -> active -> completed
curl -X POST http://localhost:8000/api/v1/products/<product-uuid>/experiments \
  -H "Content-Type: application/json" \
  -d '{"experiment_type":"market_test","prediction":{"expected_roas":2.0,"expected_conversion_rate":0.03,"score":82.5}}'
curl -X POST http://localhost:8000/api/v1/product-decisions/experiments/<experiment-uuid>/start \
  -H "Content-Type: application/json" \
  -d '{"quantity":50,"channels":["meta"],"budget":"500.00","targets":{"roas":2.0}}'
curl -X POST http://localhost:8000/api/v1/product-decisions/experiments/<experiment-uuid>/complete \
  -H "Content-Type: application/json" \
  -d '{"units_sold":28,"revenue":"1200.00","orders":26,"conversion_rate":0.028,"roas":2.4,"return_rate":0.05,"margin_rate":0.35}'
curl "http://localhost:8000/api/v1/products/<product-uuid>/experiments"
```

- 落地成本口径：`total_landed_cost = purchase_cost + domestic_shipping + international_shipping
  + packaging + tax_estimate + handling`；未显式提供国际运费时回退 `first_leg + last_leg`。
- 成本/候选/证据/实验均带 `workspace_id / version / trace_id`；重复录入成本快照版本自动 `v1 -> v2`，只追加不覆盖。
- 实验完成时自动计算 `calibration`（预测 vs 实际的数值差，如 roas / 转化率 / 评分差）。

### 8.4 产品分析师 AI 层（M2.2）

**环境变量（LLM Gateway）**

| 变量 | 默认 | 说明 |
|---|---|---|
| `LLM_PROVIDER` | `openai` | 主供应商（openai / deepseek） |
| `LLM_FALLBACK_PROVIDER` | `deepseek` | 故障降级供应商 |
| `OPENAI_API_KEY` | 空 | OpenAI API Key（生产必填） |
| `OPENAI_BASE_URL` / `OPENAI_DEFAULT_MODEL` | 官方地址 / `gpt-4o-mini` | 可指向兼容端点 |
| `DEEPSEEK_API_KEY` | 空 | DeepSeek API Key |
| `DEEPSEEK_BASE_URL` / `DEEPSEEK_DEFAULT_MODEL` | 官方地址 / `deepseek-chat` | DeepSeek 配置 |

**常用接口**

```bash
# 运行产品分析（Agent：分析 + 提案，不执行任何动作）
curl -X POST http://localhost:8000/api/v1/agents/product-analyst/analyze/<product-uuid>

# 查看某产品的 AI 分析运行记录
curl "http://localhost:8000/api/v1/agents/product-analyst/runs/<product-uuid>"

# 记录 AI 预测评估（prediction vs actual，自动计算差值 + 人工评分）
curl -X POST http://localhost:8000/api/v1/ai-evaluations \
  -H "Content-Type: application/json" \
  -d '{"product_id":"<product-uuid>","analysis_run_id":"<run-uuid>","actual_result":{"decision":"test","test_plan.kpis.roas":2.5},"human_rating":4}'
curl "http://localhost:8000/api/v1/ai-evaluations?product_id=<product-uuid>"

# Prompt 注册表管理（prompt 存数据库，禁止硬编码）
curl -X POST http://localhost:8000/api/v1/prompts \
  -H "Content-Type: application/json" \
  -d '{"prompt_id":"PRODUCT_ANALYST","name":"PRODUCT_ANALYST","version":"v2","template":"...{context_json}...{output_schema}","variables":["context_json","output_schema"],"status":"active"}'
curl "http://localhost:8000/api/v1/prompts?name=PRODUCT_ANALYST"
```

**校验与门禁**

- 结构化输出：`decision ∈ {test, hold, reject}`、`confidence ∈ [0, 1]`、pricing/test_plan 字段范围校验；失败按 failed 运行审计落库，不产生提案。
- 业务门禁（PROFIT-003）：成本 `UNKNOWN` 时禁止 `test` 决策且置信度 ≤ 0.5。
- 硬规则否决（PRODUCT 域）：校验通过后若硬规则未通过，提案强制降级为 `reject` 并记录原因。
- Agent 权限：只读产品数据；仅写 `product_analysis_runs` + pending 决策提案；无 approve / publish / purchase 能力。
