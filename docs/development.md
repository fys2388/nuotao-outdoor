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

### 8.5 学习闭环（M2.3）

```bash
# 置信度校准报告（按 LOW/MEDIUM/HIGH 聚合 AI 置信度 vs 实际成功率）
curl "http://localhost:8000/api/v1/calibration/confidence-report"

# 生成评分权重校准提案（确定性建议；proposed -> 人工审批 -> 版本更新）
curl -X POST http://localhost:8000/api/v1/calibration/runs
curl "http://localhost:8000/api/v1/calibration/runs?status=proposed"

# 人工审批/拒绝（仅记录决策；规则表与评分代码永不被自动修改）
curl -X POST http://localhost:8000/api/v1/calibration/runs/<run-uuid>/approve \
  -H "Content-Type: application/json" -d '{"actor":"owner@nuotao.example","note":"approved for v2"}'
curl -X POST http://localhost:8000/api/v1/calibration/runs/<run-uuid>/reject \
  -H "Content-Type: application/json" -d '{"actor":"owner@nuotao.example","note":"not now"}'

# 产品知识记忆（success/failure 模式 + 品类洞察）
curl -X POST http://localhost:8000/api/v1/knowledge-entries \
  -H "Content-Type: application/json" \
  -d '{"category":"headlamp","entry_type":"success_pattern","title":"Light weight wins","content":"Sub-300g headlamps convert 3x category average.","tags":["lightweight"],"source":"evaluation"}'
curl "http://localhost:8000/api/v1/knowledge-entries?category=headlamp&entry_type=success_pattern"
```

**评估结果分类口径（product_ai_evaluations）**

- `success_flag`：显式 `success` > 双方 decision 一致 > roas >= 1 > margin_rate >= 0。
- `confidence_bucket`：LOW < 0.5；MEDIUM 0.5–0.7；HIGH > 0.7。
- `error_type`：failure 时分类为 decision_mismatch / metric_miss / margin_miss / other。
- 评分权重建议：六维证据置信度与实验成功的相关性（成功率高的维度加权上调后归一化至 1.00）；样本 < 3 时建议保持原权重。

### 8.6 营销智能（M3.1）

```bash
# 广告活动：自动派生 ctr/cpc/roas 并返回 roi；同 (workspace, platform, campaign_id) 幂等冲突返回 409
curl -X POST http://localhost:8000/api/v1/campaigns \
  -H "Content-Type: application/json" \
  -d '{"platform":"meta","campaign_id":"c-001","name":"US launch","budget":"500.00","spend":"100.00","impressions":10000,"clicks":400,"conversion":20,"revenue":"240.00"}'
curl "http://localhost:8000/api/v1/campaigns?platform=meta&status=active"
curl -X PUT http://localhost:8000/api/v1/campaigns/<uuid> \
  -H "Content-Type: application/json" -d '{"spend":"200.00","revenue":"600.00"}'

# 创意素材（hook/angle/copy 结构化保存，供未来 Growth Agent 学习）
curl -X POST http://localhost:8000/api/v1/creatives \
  -H "Content-Type: application/json" \
  -d '{"platform":"meta","asset_type":"video","hook":"Lightest trekking chair","copy":"Carry less. Hike further.","status":"active"}'

# 客户反馈（content 不可变；支持 product_id/source/sentiment 过滤）
curl -X POST http://localhost:8000/api/v1/feedback \
  -H "Content-Type: application/json" \
  -d '{"source":"review","content":"Great quality for the price.","sentiment":"positive","rating":5}'
curl "http://localhost:8000/api/v1/feedback?sentiment=negative&source=support"

# 营销 A/B 实验生命周期：proposed -> active -> completed（完成时自动算 B-A deltas）
curl -X POST http://localhost:8000/api/v1/marketing-experiments \
  -H "Content-Type: application/json" \
  -d '{"name":"Hook A/B","hypothesis":"Weight hook wins","variant_a":{"ctr":0.02},"variant_b":{"ctr":0.04}}'
curl -X POST http://localhost:8000/api/v1/marketing-experiments/<uuid>/start \
  -H "Content-Type: application/json" -d '{"variant_a":{"ctr":0.02},"variant_b":{"ctr":0.04}}'
curl -X POST http://localhost:8000/api/v1/marketing-experiments/<uuid>/complete \
  -H "Content-Type: application/json" \
  -d '{"variant_a_result":{"ctr":0.02,"roas":1.8},"variant_b_result":{"ctr":0.04,"roas":2.4},"winner":"variant_b"}'
```

- 所有写入均走 `event_log`（`campaign.*` / `creative.*` / `feedback.*` / `marketing_experiment.*`），trace_id 贯穿审计链。
- 数据隔离：`X-Workspace-Id` 请求头隔离各市场数据；金额一律 Decimal。

### 8.7 营销学习闭环（M3.2）

```bash
# 广告预测评估：自动分类 success/failure + error_type；只追加
curl -X POST http://localhost:8000/api/v1/marketing-evaluations \
  -H "Content-Type: application/json" \
  -d '{"campaign_id":"<uuid>","prediction":{"decision":"scale","roas":"2.0","confidence":0.8},"actual_result":{"decision":"scale","roas":"2.5"},"human_rating":4}'
curl "http://localhost:8000/api/v1/marketing-evaluations?campaign_id=<uuid>"

# 创意分析审计（input/output/performance_result + model_version）
curl -X POST http://localhost:8000/api/v1/creative-analysis-runs \
  -H "Content-Type: application/json" \
  -d '{"creative_id":"<uuid>","input_snapshot":{"hook":"Lightest chair"},"analysis_output":{"suggested_angle":"weight"},"performance_result":{"ctr":0.03},"model_version":"creative-insight-v1"}'

# 营销知识记忆（creative/copy/audience/offer/failure_pattern）
curl -X POST http://localhost:8000/api/v1/marketing-knowledge-entries \
  -H "Content-Type: application/json" \
  -d '{"campaign_id":"<uuid>","entry_type":"creative_pattern","category":"trekking-chair","title":"Weight hook wins","content":"Weight hooks beat price hooks on CTR.","confidence":0.85}'
curl "http://localhost:8000/api/v1/marketing-knowledge-entries?entry_type=creative_pattern&category=trekking-chair"

# Growth Context Builder：campaign -> 完整营销上下文（JSON）
curl "http://localhost:8000/api/v1/marketing-context/<campaign-uuid>"

# 营销校准：发现成功/失败模式（proposed -> 人工审批；禁止自动改规则）
curl -X POST http://localhost:8000/api/v1/marketing-calibration/runs
curl "http://localhost:8000/api/v1/marketing-calibration/runs?status=proposed"
curl -X POST http://localhost:8000/api/v1/marketing-calibration/runs/<run-uuid>/approve \
  -H "Content-Type: application/json" -d '{"actor":"owner@nuotao.example","note":"ok"}'
curl -X POST http://localhost:8000/api/v1/marketing-calibration/runs/<run-uuid>/reject \
  -H "Content-Type: application/json" -d '{"actor":"owner@nuotao.example","note":"not now"}'
```

- 所有写入均走 `event_log`（`marketing.campaign_evaluation.recorded` / `marketing.creative_analysis.recorded` / `marketing.knowledge.created` / `marketing.calibration_run_*`），trace_id 贯穿审计链。
- 边界：不开发 Growth Agent、不接真实广告平台 API、不自动投放广告；校准只产出提案，人工审批后才生效。

### 8.8 客户智能（M3.3）

```bash
# 非 PII 客户档案（重复 reference id 返回 409）
curl -X POST http://localhost:8000/api/v1/customer-profiles \
  -H "Content-Type: application/json" \
  -d '{"customer_reference_id":"wc-1001","country":"US","language":"en","segment":"new","total_orders":1,"total_revenue":"49.99"}'
curl "http://localhost:8000/api/v1/customer-profiles?segment=new&country=US"

# 客户交互（content 不可变；metadata 含 email/phone/name 等 PII 键会被 400 拒绝）
curl -X POST http://localhost:8000/api/v1/customer-interactions \
  -H "Content-Type: application/json" \
  -d '{"customer_id":"<uuid>","channel":"chat","interaction_type":"question","content":"Is it waterproof?","sentiment":"neutral","metadata":{"topic":"waterproof"}}'
curl "http://localhost:8000/api/v1/customer-interactions?customer_id=<uuid>&channel=chat"

# 产品评论（content 不可变；支持 product_id/platform/sentiment 过滤）
curl -X POST http://localhost:8000/api/v1/product-reviews \
  -H "Content-Type: application/json" \
  -d '{"platform":"amazon","rating":4,"content":"Comfortable but straps slip.","sentiment":"neutral","issue_type":"fit","keywords":["straps"]}'

# 退款智能 + 按品类统计（金额 Decimal）
curl -X POST http://localhost:8000/api/v1/refund-cases \
  -H "Content-Type: application/json" \
  -d '{"order_id":"<uuid>","reason":"Item arrived damaged.","category":"quality","amount":"19.99","resolution":"refunded"}'
curl "http://localhost:8000/api/v1/refund-cases/stats"
curl "http://localhost:8000/api/v1/refund-cases?category=quality&resolution=refunded"

# 客户知识记忆（purchase/pain/segment/refund/loyalty_pattern）
curl -X POST http://localhost:8000/api/v1/customer-knowledge-entries \
  -H "Content-Type: application/json" \
  -d '{"entry_type":"pain_point","category":"trekking-chair","title":"Straps slip","content":"Customers report straps slipping on rocky terrain.","confidence":0.9}'
curl "http://localhost:8000/api/v1/customer-knowledge-entries?entry_type=pain_point&category=trekking-chair"
```

- 所有写入均走 `event_log`（`customer.profile_*` / `customer.interaction_*` / `customer.review_*` / `customer.refund_*` / `customer.knowledge_created`），trace_id 贯穿审计链。
- 边界：不开发 Customer Agent、不自动客服；PII 策略为“非必要不存储 + 自由字段键拦截”。

### 8.9 客户学习闭环（M3.4）

```bash
# 行为预测评估：自动分类 success/failure + error_type；只追加
curl -X POST http://localhost:8000/api/v1/customer-evaluations \
  -H "Content-Type: application/json" \
  -d '{"customer_id":"<uuid>","prediction":{"decision":"reorder","confidence":0.75},"actual_behavior":{"decision":"reorder"},"human_rating":5}'
curl "http://localhost:8000/api/v1/customer-evaluations?customer_id=<uuid>"

# 模式挖掘（purchase/segment/bundle/churn/pain；确定性聚合 + 启发式置信度）
curl -X POST http://localhost:8000/api/v1/customer-pattern-runs \
  -H "Content-Type: application/json" -d '{"pattern_type":"purchase_pattern"}'
curl -X POST http://localhost:8000/api/v1/customer-pattern-runs \
  -H "Content-Type: application/json" -d '{"pattern_type":"churn_pattern"}'
curl "http://localhost:8000/api/v1/customer-pattern-runs?pattern_type=pain_pattern"

# 知识记忆扩展类型（churn/bundle/pain_pattern，兼容 M3.3 五类）
curl -X POST http://localhost:8000/api/v1/customer-knowledge-entries \
  -H "Content-Type: application/json" \
  -d '{"customer_id":"<uuid>","entry_type":"churn_pattern","category":"trekking-chair","title":"Churn after 60d","content":"Repeat customers churn when no follow-up offer arrives.","confidence":0.8}'

# 客户校准：发现成功/失败模式（proposed -> 人工审批；禁止自动改规则）
curl -X POST http://localhost:8000/api/v1/customer-calibration/runs
curl "http://localhost:8000/api/v1/customer-calibration/runs?status=proposed"
curl -X POST http://localhost:8000/api/v1/customer-calibration/runs/<run-uuid>/approve \
  -H "Content-Type: application/json" -d '{"actor":"owner@nuotao.example","note":"ok"}'

# 跨域客户上下文：customer + orders/reviews/refunds/marketing/product/knowledge
curl "http://localhost:8000/api/v1/customer-context/<customer-uuid>"
```

- 所有写入均走 `event_log`（`customer.evaluation_recorded` / `customer.pattern_run_completed` / `customer.calibration_run_*`），trace_id 贯穿审计链。
- 边界：不开发 Customer Agent、不自动客服、不自动修改业务规则；校准只产出提案，人工审批后才生效。

### 8.10 供应链智能（M4.1）

```bash
# 供应商画像：一个供应商一份（重复 409）；factory_type 支持 factory/trading/agent；仅数据采集，不自动采购
curl -X POST http://localhost:8000/api/v1/supplier-profiles \
  -H "Content-Type: application/json" \
  -d '{"supplier_id":"<uuid>","category":"camping","location":"Yiwu, Zhejiang","factory_type":"factory","lead_time_days":7,"minimum_order_qty":50,"quality_score":88.5,"on_time_rate":92,"defect_rate":1.5,"certifications":["BSCI"],"risk_level":"low"}'
curl "http://localhost:8000/api/v1/supplier-profiles?risk_level=low"

# 采购单：draft -> approved -> ordered -> partial_received -> received（draft/approved 可取消；非法转换 400）
curl -X POST http://localhost:8000/api/v1/purchase-orders \
  -H "Content-Type: application/json" \
  -d '{"po_number":"PO-2026-001","supplier_id":"<uuid>","shipping_cost":"20.00","items":[{"sku":"TENT-1","name":"Tent 1P","quantity":10,"unit_cost":"12.50"}]}'
curl "http://localhost:8000/api/v1/purchase-orders?status=draft"
curl -X POST http://localhost:8000/api/v1/purchase-orders/<po-uuid>/approve
curl -X POST http://localhost:8000/api/v1/purchase-orders/<po-uuid>/order
curl -X POST http://localhost:8000/api/v1/purchase-orders/<po-uuid>/partial-receive
curl -X POST http://localhost:8000/api/v1/purchase-orders/<po-uuid>/receive
curl -X POST http://localhost:8000/api/v1/purchase-orders/<po-uuid>/cancel

# 库存：available = quantity - reserved（更新后自动重算）；location 固定三仓 cn/us/eu（中国仓/美国仓/欧洲仓）
curl -X POST http://localhost:8000/api/v1/inventory-snapshots \
  -H "Content-Type: application/json" \
  -d '{"product_id":"<uuid>","location":"us","quantity":100,"reserved":30}'
curl -X PUT http://localhost:8000/api/v1/inventory-snapshots/<inventory-uuid> \
  -H "Content-Type: application/json" -d '{"reserved":55}'

# 物流：发货记录 + 只追加轨迹事件 + 状态/延误更新
curl -X POST http://localhost:8000/api/v1/shipments \
  -H "Content-Type: application/json" \
  -d '{"carrier":"Cainiao","origin":"Yiwu, China","destination":"Los Angeles, US","tracking_number":"CN123456789"}'
curl -X POST http://localhost:8000/api/v1/shipments/<shipment-uuid>/events \
  -H "Content-Type: application/json" -d '{"event_type":"picked_up","location":"Yiwu","description":"Parcel picked up"}'
curl -X PUT http://localhost:8000/api/v1/shipments/<shipment-uuid> \
  -H "Content-Type: application/json" -d '{"status":"delayed","delay_reason":"customs hold"}'

# 供应链知识记忆：五类模式（supplier/logistics/delay/quality/risk_pattern）
curl -X POST http://localhost:8000/api/v1/supply-chain-knowledge-entries \
  -H "Content-Type: application/json" \
  -d '{"supplier_id":"<uuid>","category":"logistics","entry_type":"delay_pattern","title":"Customs delays Q4","content":"US customs clearance takes 2-3 extra days in Q4.","tags":["customs","q4"],"confidence":0.8}'
curl "http://localhost:8000/api/v1/supply-chain-knowledge-entries?entry_type=delay_pattern"
```

- 所有写入均走 `event_log`（`supply.*` 前缀），trace_id 贯穿审计链；工作区隔离通过 `X-Workspace-Id`。
- 边界：不开发 Supply Chain Agent、不自动采购；采购状态机转换必须显式调用，非法转换返回 400。

### 8.11 供应链学习闭环（M4.2）

```bash
# 供应商预测评估：预测 vs 实测，自动分类 success/failure + error_type；只追加
curl -X POST http://localhost:8000/api/v1/supplier-evaluations \
  -H "Content-Type: application/json" \
  -d '{"supplier_id":"<uuid>","prediction":{"decision":"approve","confidence":0.8},"actual_result":{"decision":"approve"}}'
curl "http://localhost:8000/api/v1/supplier-evaluations?supplier_id=<uuid>"

# 物流交付评估：carrier/route 自动回填自 shipment；delay_reason 记录延误原因
curl -X POST http://localhost:8000/api/v1/logistics-evaluations \
  -H "Content-Type: application/json" \
  -d '{"shipment_id":"<uuid>","prediction":{"decision":"on_time","delivery_time_days":10},"actual_result":{"decision":"delayed"},"delay_reason":"customs hold"}'
curl "http://localhost:8000/api/v1/logistics-evaluations?carrier=Cainiao"

# 供应商模式挖掘：quality/delivery/price/risk/capacity（确定性聚合）
curl -X POST http://localhost:8000/api/v1/supplier-pattern-runs \
  -H "Content-Type: application/json" -d '{"pattern_type":"quality_pattern"}'
curl "http://localhost:8000/api/v1/supplier-pattern-runs?pattern_type=risk_pattern"

# 物流模式挖掘：delay/carrier/route/country（确定性聚合）
curl -X POST http://localhost:8000/api/v1/logistics-pattern-runs \
  -H "Content-Type: application/json" -d '{"pattern_type":"delay_pattern"}'
curl "http://localhost:8000/api/v1/logistics-pattern-runs?pattern_type=country_pattern"

# 校准：发现成功/失败模式（proposed -> 人工审批；禁止自动改规则；二次审批 400）
curl -X POST http://localhost:8000/api/v1/supply-chain-calibration/runs
curl "http://localhost:8000/api/v1/supply-chain-calibration/runs?status=proposed"
curl -X POST http://localhost:8000/api/v1/supply-chain-calibration/runs/<run-uuid>/approve \
  -H "Content-Type: application/json" -d '{"actor":"owner@nuotao.example","note":"ok"}'
curl -X POST http://localhost:8000/api/v1/supply-chain-calibration/runs/<run-uuid>/reject \
  -H "Content-Type: application/json" -d '{"actor":"owner@nuotao.example","note":"not now"}'

# 知识沉淀：新增 supplier/logistics success/failure_pattern、season/country_pattern 类型
curl -X POST http://localhost:8000/api/v1/supply-chain-knowledge-entries \
  -H "Content-Type: application/json" \
  -d '{"supplier_id":"<uuid>","entry_type":"supplier_failure_pattern","title":"Defect spike","content":"Defect rate spiked above 5% in August.","confidence":0.8}'
```

- 所有写入均走 `event_log`（`supply.*` 学习事件），trace_id 贯穿审计链；工作区隔离通过 `X-Workspace-Id`。
- 边界：不开发 Supply Chain Agent、不自动采购、不自动修改规则；校准提案必须人工 approve / reject。


### 8.12 真实数据连接器 + 经营建议（M4.3）

连接器统一契约：`validate() / transform() / sync() / audit()`；仅只读外部数据，单向流入，全部经 `event_log` + `trace_id` + workspace 隔离。可推送批次（`data`）或配置实时源（WooCommerce REST v3 Basic Auth）。

```bash
# 1) 连接器同步：WooCommerce 订单（重复推送幂等；客户仅存引用哈希，无 PII）
curl -X POST http://localhost:8000/api/v1/connectors/woocommerce/sync \
  -H "Content-Type: application/json" \
  -d '{"data":[{"kind":"orders","data":{"id":90001,"status":"processing","currency":"USD","total":"100.00","subtotal":"95.00","shipping_total":"5.00","discount_total":"5.00","tax_total":"0.00","shipping":{"country":"US"},"line_items":[{"id":1,"name":"Headlamp","sku":"SKU-001","quantity":1,"total":"90.00"}]}}]}'

# WooCommerce 产品（按 SKU upsert）与客户（customer_reference_id 哈希）
curl -X POST http://localhost:8000/api/v1/connectors/woocommerce/sync \
  -H "Content-Type: application/json" \
  -d '{"data":[{"kind":"products","data":{"sku":"SKU-001","name":"Headlamp","categories":[{"name":"Lighting"}],"status":"publish"}},{"kind":"customers","data":{"id":7001,"email":"buyer@example.com","billing":{"country":"US"},"orders_count":1,"total_spent":"100.00"}}]}'

# WooCommerce 实时同步（配置 REST 凭证，按 kind 拉取 /orders|/products|/customers）
curl -X POST http://localhost:8000/api/v1/connectors/woocommerce/sync \
  -H "Content-Type: application/json" \
  -d '{"config":{"kind":"orders","base_url":"https://shop.example","consumer_key":"ck_xxx","consumer_secret":"cs_xxx"}}'

# 2) 物流：tracking 同步（tracking_number 幂等；轨迹事件去重）
curl -X POST http://localhost:8000/api/v1/connectors/logistics/sync \
  -H "Content-Type: application/json" \
  -d '{"data":[{"carrier":"Cainiao","tracking_number":"LP90001","status":"in_transit","origin":"Yiwu, China","destination":"Los Angeles, US","events":[{"event_type":"pickup","location":"Yiwu","description":"Parcel picked up","occurred_at":"2026-08-01T08:00:00Z"}]}]}'

# 3) 营销：campaign 指标同步（platform + campaign_id 幂等；只读，不投放）
curl -X POST http://localhost:8000/api/v1/connectors/marketing/sync \
  -H "Content-Type: application/json" \
  -d '{"data":[{"platform":"meta","campaign_id":"c-001","name":"US Summer Tent","status":"active","budget":"500.00","spend":"120.00","impressions":10000,"clicks":250,"conversion":8,"revenue":"480.00"}]}'

# 4) 供应商：主数据同步（workspace + code 幂等）
curl -X POST http://localhost:8000/api/v1/connectors/supplier/sync \
  -H "Content-Type: application/json" \
  -d '{"data":[{"code":"1688-001","name":"Yiwu Camping Factory","platform":"1688","shop_url":"https://shop1688.example/001","rating":"A","status":"active"}]}'

# 5) 同步审计：connector_runs（connector_name/status/records_count/trace_id 过滤）
curl http://localhost:8000/api/v1/connector-runs?connector_name=woocommerce&status=success

# 6) 经营建议：propose -> 人工 approve / reject（二次审批 400；不自动执行商业动作）
curl -X POST http://localhost:8000/api/v1/business-recommendations \
  -H "Content-Type: application/json" \
  -d '{"domain":"supply_chain","entity_type":"product","entity_id":"SKU-001","recommendation":"Reorder 200 units before peak season","reason":"Inventory below 2 weeks of coverage","confidence":0.82}'
curl -X POST http://localhost:8000/api/v1/business-recommendations/<uuid>/approve \
  -H "Content-Type: application/json" -d '{"actor":"ops-lead","note":"stock is low"}'
curl -X POST http://localhost:8000/api/v1/business-recommendations/<uuid>/reject \
  -H "Content-Type: application/json" -d '{"actor":"ops-lead","note":"not now"}'
curl http://localhost:8000/api/v1/business-recommendations?status=proposed&domain=supply_chain
```

- 所有同步写入 `connector_runs` 并追加 `connector.run_completed` 事件；推荐状态机 `proposed → approved/rejected`，事件 `business.recommendation_proposed/approved/rejected`。
- 边界：不开发 Agent、不自动执行商业动作、不自动修改规则；建议必须人工审批。
### 8.13 Agent 运行时基础（M5.0）

# 0) 前置：Agent 必须绑定版本化提示词（prompt 禁止硬编码；name 约定 AGENT_<AGENT_ID> 大写）
curl -X POST http://localhost:8000/api/v1/prompts \
  -H "Content-Type: application/json" \
  -d '{"prompt_id":"AGENT_PRODUCT_ANALYST","name":"AGENT_PRODUCT_ANALYST","version":"v1","template":"You are a product analyst agent. ...","variables":["product_context"],"status":"active"}'

# 1) Agent 注册（agent_id 唯一；重复注册视为更新）
curl -X POST http://localhost:8000/api/v1/agent-registry \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"PRODUCT_ANALYST","name":"Product Analyst","domain":"product","version":"v1","status":"active","model_provider":"openai","model_name":"gpt-4o-mini","prompt_version":"v1","permission_level":"L2"}'
curl http://localhost:8000/api/v1/agent-registry
curl http://localhost:8000/api/v1/agent-registry/<uuid>/prompt   # 解析绑定提示词

# 2) 任务 + 执行生命周期（pending -> running -> completed/failed）
curl -X POST http://localhost:8000/api/v1/agent-tasks \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"<agent_uuid>","input":{"product_id":"<uuid>","action":"analyze"},"priority":3}'
curl -X POST http://localhost:8000/api/v1/agent-executions \
  -H "Content-Type: application/json" -d '{"task_id":"<task_uuid>"}'
curl -X POST http://localhost:8000/api/v1/agent-executions/<uuid>/complete \
  -H "Content-Type: application/json" \
  -d '{"output":{"decision":"test","confidence":0.7},"provider":"openai","model":"gpt-4o-mini","tokens":{"prompt":1200,"completion":300},"cost":"0.012","latency_ms":842}'
curl -X POST http://localhost:8000/api/v1/agent-tasks/<uuid>/cancel

# 3) 工具白名单 + L0-L3 权限门禁（L3 高风险 -> waiting_approval -> 人工审批）
curl -X POST http://localhost:8000/api/v1/agent-tools \
  -H "Content-Type: application/json" \
  -d '{"tool_name":"product.read","description":"read product data","permission_level":"L1","enabled":true,"category":"product"}'
curl -X POST http://localhost:8000/api/v1/agent-executions/<uuid>/tool-calls \
  -H "Content-Type: application/json" \
  -d '{"tool_name":"product.read","arguments":{"product_id":"<uuid>"}}'   # L0-L2 放行 + 审计；L3 -> requires_approval
curl -X POST http://localhost:8000/api/v1/agent-executions/<uuid>/approve \
  -H "Content-Type: application/json" -d '{"actor":"ops-lead","note":"approved"}'   # 二次审批 400
curl -X POST http://localhost:8000/api/v1/agent-executions/<uuid>/reject \
  -H "Content-Type: application/json" -d '{"actor":"ops-lead","note":"rejected"}'

# 4) Agent 记忆（知识域 grounding）
curl -X POST http://localhost:8000/api/v1/agent-memory \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"<agent_uuid>","domain":"product","source_type":"product_knowledge","source_id":"<product_uuid>","content":"success pattern: ...","tags":["camping","hero"],"meta":{}}'
curl "http://localhost:8000/api/v1/agent-memory?domain=product&q=camping"
curl http://localhost:8000/api/v1/agent-memory/knowledge-snapshot?domain=product   # 四知识域快照

# 5) Agent 评估（预测 vs 实测；自动分类 success/failure/unknown + 置信度桶）
curl -X POST http://localhost:8000/api/v1/agent-evaluations \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"<agent_uuid>","prediction":{"decision":"test"},"actual_result":{"decision":"test"},"human_rating":4,"notes":""}'
curl "http://localhost:8000/api/v1/agent-evaluations?agent_id=<agent_uuid>"

