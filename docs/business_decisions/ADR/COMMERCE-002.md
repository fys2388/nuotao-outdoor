# ADR COMMERCE-002 — 牛顿 Agent 1688 商品获取集成方案

> 状态：**Accepted**（2026-09-06）
> 决策编号：COMMERCE-002
> 关联：`docs/project_architecture.md`、`docs/business_context.md`、`docs/M5.13_PRODUCT_CANDIDATE_SOURCE_DESIGN.md`

---

## Context（背景）

Nuotao AI OS 的 1688 选品导入功能需要获取商品详情数据（标题、价格、图片、SKU、供应商信息）。原设计通过 1688 开放平台 API（`gw.open.1688.com/openapi`）直接调用商品详情接口。

### 问题

1688 开放平台 API 的 `detail.1688.com/offer/{id}` 接口需要：
1. **ISV 应用资质** — AppKey 必须属于 1688 开放平台的 ISV 服务商
2. **ACL 授权** — 必须获得商品所属商家的 ACL 白名单授权
3. **铺货关系** — 调用方与商品供应商之间存在铺货/代发关系

当前 AppKey `2819733` 属于账号 `tb638676`（采购服务商），已订购「牛顿云代理解决方案」（solutionKey=1781231961978），但该 AppKey 未在任何商品商家侧完成 ACL 授权。调用开放平台商品详情接口返回：

```
gw.APIACLDecline: AppKey is not allowed(acl)
```

### 根因分析

1688 开放平台的三层权限模型：

```
Layer 1: 解决方案订购        ✅ 已订购「牛顿云代理」
Layer 2: API 能力订购        ❌ 能力列表为空
Layer 3: 商家 ACL 授权       ❌ 商品商家未授权 AppKey
```

即使完成能力订购，Layer 3 仍需逐个商家授权，无法批量解决。对于跨境选品场景（需从任意商家获取商品信息），此路径不可行。

## Decision（决策）

### 1. 采用牛顿 Agent 作为 1688 商品获取主通道

放弃 1688 开放平台商品详情 API 作为主通道，改用牛顿 Agent（`newtoncloud.*`）作为商品数据获取引擎。

**牛顿 Agent 的优势：**
- 通过 AI Agent 语义理解页面内容，不依赖固定 API 结构
- 使用 ISV 自身的 AppKey 凭证，无需商家 ACL 授权
- 可获取页面全部信息（标题、价格、SKU、图片、描述、供应商等）
- 支持自然语言查询（关键词搜品、比价、筛选）

**积分消耗：**
- 每次商品提取约消耗 1-3 积分
- 当前余额：9842 积分（可用约 3000-9000 次提取）
- 可通过 `com.alibaba.agent.newtoncloud.points.query` 查询

### 2. 后端架构：牛顿 Agent 优先，开放平台兜底

`product_pipeline_service._fetch_1688_product()` 的调用链：

```
_fetch_1688_product(url)
  │
  ├─ Step 1: 解析 URL 提取商品 ID
  │
  ├─ Step 2: 优先使用牛顿 Agent
  │    ├─ newton_is_configured() → 检查 ALI1688_APP_KEY/SECRET/TOKEN
  │    ├─ extract_1688_product(url, product_id)
  │    │    ├─ create_agent_task(message, model="qwen3.6-plus")
  │    │    ├─ 轮询任务状态（间隔 3 秒，超时 300 秒）
  │    │    └─ 解析 JSON 结果 → 标准化为 product_info
  │    └─ 成功 → 返回，data_source = "newton_agent"
  │
  ├─ Step 3: 牛顿失败 → 降级到开放平台 API
  │    └─ get_product_detail(product_id) → data_source = "1688_open_api"
  │
  └─ Step 4: 两者都失败 → 错误处理 + 错误码翻译
```

### 3. 异步任务架构

牛顿 Agent 单次提取耗时 78-114 秒（实测均值 ~111 秒），远超 HTTP 网关超时限制（通常 30-60 秒）。

**方案：Redis 持久化异步任务**

```
POST /product-pipeline/import-from-1688/jobs       → 创建任务，立即返回 job_id
GET  /product-pipeline/import-from-1688/jobs/{id}  → 轮询状态
```

- 任务状态：`pending → running → succeeded | failed`
- 任务数据持久化到 Redis，TTL 24 小时
- 前端每 3 秒轮询一次，超时 20 分钟
- 后台执行通过 `asyncio.create_task` 调度，不阻塞事件循环

**三页面前端统一异步化：**

| 页面 | 端点 | 模式 |
|---|---|---|
| ProductAnalysis | `/import-and-analyze-1688/jobs` | 异步轮询（已有） |
| ProductPipeline | `/import-from-1688/jobs` | 异步轮询（本次新增） |
| Sourcing | `/import-from-1688/jobs` | 异步轮询（本次新增） |

### 4. 缓存策略

牛顿 Agent 的提取结果按 `url_or_id` 缓存到 `data/1688_cache/`，TTL 24 小时。

- 首次调用：~111 秒
- 缓存命中：< 1 秒
- 防止重复提取同一商品浪费积分

### 5. 错误处理与用户提示

| 错误码 | 含义 | 用户提示 |
|---|---|---|
| `ACL_DENIED` | 开放平台 ACL 拒绝 | "牛顿 Agent 正在处理中，约需 1-2 分钟" |
| `PRODUCT_NOT_FOUND` | 商品不存在 | "商品链接无效或已下架" |
| `NEWTON_TIMEOUT` | 牛顿 Agent 超时 | "商品处理超时，请稍后重试" |
| `CREDENTIALS_MISSING` | 凭证未配置 | "1688 集成未配置，请检查环境变量" |

## Consequences（后果）

### 正面

1. **无需商家 ACL 授权** — 任意 1688 商品均可提取
2. **数据完整度高** — 实测获取到标题、价格、SKU（3 个颜色变体）、图片、供应商、描述、包装尺寸、跨境认证等完整信息
3. **AI 原生能力** — 自然语言查询、语义理解、智能筛选
4. **前端体验一致** — 三个页面统一异步轮询，进度提示友好

### 负面

1. **延迟较高** — 111 秒 vs 开放平台 API 的 < 5 秒
2. **积分消耗** — 每次提取 1-3 积分，需监控余额
3. **结果不确定性** — AI Agent 可能偶尔返回非结构化数据（代码已做 JSON 解析容错）
4. **积分耗尽风险** — 9842 积分约可用 3000-9000 次，需提前监控

### 缓解措施

1. **积分监控** — 通过 `points.query` API 定期检查余额，低于阈值告警
2. **缓存复用** — 同一商品不重复提取，缓存 TTL 24 小时
3. **降级兜底** — 牛顿失败自动降级到开放平台 API
4. **缓存预热** — 批量导入时，缓存可跨页面复用

## Credential Configuration（凭证配置）

### 环境变量

```bash
# .env.development 或 .env
ALI1688_APP_KEY=2819733
ALI1688_APP_SECRET=xxx
ALI1688_ACCESS_TOKEN=2459bef5-eb1a-45bc-8af1-5d51d1236f47
```

### 加载逻辑

```
Settings(settings.py) 加载顺序：
  .env.development → .env → backend/.env → os.environ

Newton Agent (newton_agent_service.py)：
  _load_env_file() 强制加载 backend/.env.development
  os.getenv("ALI1688_APP_KEY")
```

### 已订购解决方案

| 解决方案 | solutionKey | 有效期 | API 能力 |
|---|---|---|---|
| 牛顿云代理 | 1781231961978 | 至 2027-09-04 | newtoncloud.* |

## 验证记录

### 端到端测试（2026-09-06）

**测试商品：** 跨境新品多功能户外野营灯（Offer ID: 914568922127）

**供应商：** 义乌市星迈照明电器有限公司

**测试结果：** ✅ 成功

| 环节 | 结果 |
|---|---|
| Newton Agent 抓取 | ✅ data_source: newton_agent |
| AI 识别（10 字段） | ✅ brand_name, product_category, appearance, material, selling_points, scenarios, audience, visual_style, colors, page_types |
| 产品报告（17 字段） | ✅ brand, name, category, dimensions, material, color, capacity, audience, features, scenarios, style, colors, extendable_pages, description, quality_assurance |
| 总耗时 | 111.1 秒 |

**对比测试（商品 758925276700）：** ❌ 失败 — 该商品在 1688 上不存在（页面 404）

---

## 相关文档

- `docs/project_architecture.md` — 系统整体架构
- `docs/M5.13_PRODUCT_CANDIDATE_SOURCE_DESIGN.md` — 商品候选源设计
- `docs/business_context.md` — 业务上下文
- `docs/business_decisions/ADR/COMMERCE-001.md` — B2C+B2B 一体化商务架构