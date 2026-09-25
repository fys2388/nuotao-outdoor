# Nuotao AI OS - 工作流引擎实现文档

> 版本: 1.0.0 | 实现日期: 2026-09-24 | 状态: ✅ 已完成

---

## 1. 概述

工作流引擎是 Nuotao AI OS 的核心调度组件，实现了从选品到上架的完整业务链路自动化。

### 1.1 核心特性

- **JSON驱动配置**: 工作流配置完全由JSON文件驱动，支持热更新
- **6模块27子模块**: 完整的商品上架全链路覆盖
- **混合触发模式**: 手动、自动、定时、回调混合触发
- **异常工单机制**: 失败时生成工单挂起，支持断点续跑
- **重试策略**: 支持立即重试、指数退避两种策略

### 1.2 技术栈

| 组件 | 技术选型 |
|------|---------|
| 后端框架 | FastAPI + Pydantic |
| 数据库 | SQLite (可切换PostgreSQL) |
| API网关 | 牛顿AI、火山引擎、WooCommerce |
| 任务调度 | APScheduler + 自定义Cron |
| 测试框架 | pytest |

---

## 2. 模块架构

```
┌─────────────────────────────────────────────────────────────┐
│                      工作流引擎 (Engine)                      │
├─────────────────────────────────────────────────────────────┤
│  core.py (WorkflowEngine)    │  state.py (WorkflowState)    │
│  executor.py (NodeExecutor)  │  scheduler.py (Cron)         │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
┌───────▼───────┐    ┌───────▼───────┐    ┌───────▼───────┐
│  模块1: 选品   │    │  模块2: 商品   │    │  模块3: 视觉   │
│  selection    │    │  product_mgmt │    │  vision       │
└───────┬───────┘    └───────┬───────┘    └───────┬───────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │  模块4: 上架       │
                    │  listing           │
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │  模块5: 同步       │
                    │  sync              │
                    └───────────────────┘
```

---

## 3. 模块详解

### 3.1 工作流引擎 (backend/engine/)

#### 核心文件

| 文件 | 功能 |
|------|------|
| `core.py` | WorkflowEngine主类，实例管理、节点路由 |
| `executor.py` | NodeExecutor，节点执行、重试控制 |
| `state.py` | WorkflowState，状态持久化、日志、工单 |
| `scheduler.py` | WorkflowScheduler，Cron定时任务 |

#### 关键类

```python
class WorkflowEngine:
    - create_instance(product_data) -> instance_id
    - get_instance(instance_id) -> instance
    - execute_node(instance_id, node_id) -> result
    - pause_instance(instance_id, reason)
    - resume_instance(instance_id, from_node, reason)

class NodeExecutor:
    - execute_with_retry(task_func, max_retries, strategy)
    - retry strategies: "immediate", "exponential"
```

---

### 3.2 选品中心 (backend/modules/selection/)

#### 子模块

| 子模块 | 文件 | 功能 |
|--------|------|------|
| 商品采集 | `collection.py` | 1688爬虫、手动录入、批量采集 |
| 牛顿AI评分 | `scoring.py` | 毛利、竞品、搜索热度、侵权初筛 |
| 人工预审 | `review.py` | 通过/淘汰/待定三态 |
| 候选归档池 | `archive.py` | 淘汰商品存储、召回 |
| 采集日志 | `logger.py` | 采集日志、牛顿AI调用日志 |

#### 牛顿AI评分维度

1. **毛利分析**: 成本、售价、利润率
2. **竞品销量**: 竞品数量、销量趋势
3. **搜索热度**: 关键词搜索量、趋势
4. **侵权初筛**: 商标、专利、版权
5. **禁品过滤**: 违禁品、受限品

---

### 3.3 商品管理 (backend/modules/product_mgmt/)

#### 子模块

| 子模块 | 文件 | 功能 |
|--------|------|------|
| 元数据清洗 | `cleaning.py` | 脏数据清洗、无效规格剔除、WC类目映射 |
| 多语言翻译 | `translation.py` | 中英文互译、降级字典 |
| SKU定价 | `sku_pricing.py` | SKU创建、规格绑定、定价配置 |
| 人工校对 | `proofread.py` | 运营核对、批准/拒绝/修改 |

---

### 3.4 AI视觉中心 (backend/modules/vision/)

#### 子模块

| 子模块 | 文件 | 功能 |
|--------|------|------|
| I2I调度 | `scheduler.py` | 火山引擎API调用、Prompt组装 |
| 图片质检 | `qc.py` | 分辨率、比例、水印、主体还原度 |
| 素材库 | `asset_library.py` | CDN上传、SKU绑定 |
| 视觉工单 | `ticket.py` | 失败工单、人工修图 |

#### 图片约束（锁定）

```json
{
  "mainImages": {
    "count": 5,
    "ratio": "1:1",
    "width": 2048,
    "height": 2048,
    "format": "PNG",
    "quality": 95
  },
  "detailImages": {
    "count": 6,
    "ratio": "3:4",
    "width": 1536,
    "height": 2048,
    "format": "PNG",
    "quality": 95
  }
}
```

---

### 3.5 上架管理 (backend/modules/listing/)

#### 子模块

| 子模块 | 文件 | 功能 |
|--------|------|------|
| 预上架校验 | `validation.py` | 必填字段、SKU合法性、CDN链接、类目 |
| 数据包打包 | `packager.py` | WooCommerce REST API JSON Payload |
| 上架草稿池 | `draft_pool.py` | 待推送商品队列 |

---

### 3.6 同步中心 (backend/modules/sync/)

#### 子模块

| 子模块 | 文件 | 功能 |
|--------|------|------|
| API网关 | `api_gateway.py` | WC密钥管理、鉴权、限流 |
| 推送队列 | `push_queue.py` | 异步队列、并发控制、重试 |
| 回调监听 | `callback_listener.py` | WC Webhook处理 |
| 双向同步 | `sync_daemon.py` | 定时轮询、库存价格同步 |

---

## 4. 数据库设计

### 4.1 数据库文件

| 文件 | 路径 | 说明 |
|------|------|------|
| workflow_state.db | `data/` | 工作流实例、历史、日志、工单 |
| archive_pool.db | `data/` | 候选归档池 |
| collection_logs.db | `data/` | 采集日志、牛顿AI日志 |
| asset_library.db | `data/` | 素材库 |
| draft_pool.db | `data/` | 上架草稿池 |

### 4.2 核心表结构

#### workflow_instances

```sql
CREATE TABLE workflow_instances (
    instance_id TEXT PRIMARY KEY,
    product_data TEXT NOT NULL,        -- JSON
    current_node TEXT,
    status TEXT DEFAULT 'running',
    trigger_source TEXT,
    ticket_id TEXT,
    metadata TEXT,                      -- JSON
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

#### workflow_tickets

```sql
CREATE TABLE workflow_tickets (
    ticket_id TEXT PRIMARY KEY,
    instance_id TEXT,
    ticket_type TEXT,                   -- image_generation, wc_sync
    module TEXT,
    status TEXT DEFAULT 'new',
    title TEXT,
    description TEXT,
    assignee TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    resolved_at TEXT,
    resolution_notes TEXT
);
```

---

## 5. 重试策略

| 场景 | 最大重试 | 策略 | 延迟 | 失败动作 |
|------|---------|------|------|---------|
| 牛顿AI评分 | 2 | 立即重试 | 0 | 降级评分 |
| AI生图 | 2 | 立即重试 | 0 | 生成工单 |
| WC推送 | 3 | 指数退避 | 5s × 2^n | 生成工单 |

### 指数退避示例

```
第1次失败: 等待 5秒
第2次失败: 等待 10秒
第3次失败: 等待 20秒
```

---

## 6. 工单机制

### 6.1 工单类型

| 类型 | 触发条件 | 挂起节点 | 恢复方式 |
|------|---------|---------|---------|
| image_generation | AI生图失败2次 | vision | 人工修图后恢复 |
| wc_sync | WC推送失败3次 | sync | 人工处理WC后恢复 |

### 6.2 工单状态流转

```
new → assigned → in_progress → resolved
                  ↓
              cancelled
```

---

## 7. 触发类型

| 类型 | 说明 | 示例 |
|------|------|------|
| manual | 人工手动触发 | 运营点击"采集商品" |
| auto | 上一节点完成后自动流转 | 评分通过后自动进入预审 |
| manualTrigger | 人工主动点击按钮 | 点击"发起AI生图" |
| autoCallback | 外部API回调触发 | WC Webhook回调 |
| cronDaemon | 定时守护进程 | 每6小时双向同步 |

---

## 8. 禁止项（5条硬性约束）

1. **禁止降低图片规格要求** - 主图必须2048×2048，详情图必须1536×2048
2. **禁止删除子模块、截断流程分支** - 所有27个子模块必须完整实现
3. **禁止硬编码业务参数** - 所有配置必须放在JSON或环境变量中
4. **禁止异常直接终止流程** - 异常必须生成工单挂起
5. **禁止替换选品AI源** - 选品推理固定调用牛顿AI

---

## 9. API端点汇总

### 9.1 工作流管理

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/workflow/config` | GET | 获取工作流配置 |
| `/api/v1/workflow/instance/create` | POST | 创建实例 |
| `/api/v1/workflow/instance/{id}` | GET | 查询实例 |
| `/api/v1/workflow/instance/pause` | POST | 暂停实例 |
| `/api/v1/workflow/instance/resume` | POST | 恢复实例 |

### 9.2 选品中心

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/selection/collect` | POST | 采集商品 |
| `/api/v1/selection/score` | POST | 牛顿AI评分 |
| `/api/v1/selection/review` | POST | 人工预审 |
| `/api/v1/selection/archive` | POST | 归档商品 |

### 9.3 商品管理

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/product-mgmt/clean` | POST | 元数据清洗 |
| `/api/v1/product-mgmt/translate` | POST | 多语言翻译 |
| `/api/v1/product-mgmt/sku/create` | POST | 创建SKU |
| `/api/v1/product-mgmt/proofread` | POST | 人工校对 |

### 9.4 AI视觉中心

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/vision/task/create` | POST | 创建生图任务 |
| `/api/v1/vision/task/execute` | POST | 执行生图任务 |
| `/api/v1/vision/assets/{sku}` | GET | 获取素材 |
| `/api/v1/vision/ticket/create` | POST | 创建工单 |

### 9.5 上架管理

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/listing/validate` | POST | 预上架校验 |
| `/api/v1/listing/pack` | POST | 打包数据包 |
| `/api/v1/listing/draft/create` | POST | 创建草稿 |

### 9.6 同步中心

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/sync/push/{draft_id}` | POST | 推送商品 |
| `/api/v1/sync/webhook` | POST | WC Webhook |
| `/api/v1/sync/sync/manual` | POST | 手动同步 |

---

## 10. 部署指南

### 10.1 本地开发

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 初始化数据库
python backend/init_db.py

# 3. 启动服务
uvicorn backend.main:app --reload --port 8000

# 4. 访问文档
open http://localhost:8000/docs
```

### 10.2 Docker部署

```bash
# 构建镜像
docker build -t nuotao-ai-os .

# 运行容器
docker run -p 8000:8000 \
  -v ./data:/app/data \
  -v ./workflow:/app/workflow \
  nuotao-ai-os

# 或使用docker-compose
docker compose up -d
```

### 10.3 环境变量配置

```bash
# 复制配置模板
cp .env.example .env

# 编辑填入真实密钥
vim .env
```

---

## 11. 测试

### 11.1 测试文件

| 文件 | 测试项 | 通过 |
|------|--------|------|
| `test_workflow_engine.py` | 引擎核心 | 6/6 |
| `test_selection_module.py` | 选品中心 | 5/5 |
| `test_product_mgmt.py` | 商品管理 | 4/4 |
| `test_vision_module.py` | AI视觉中心 | 4/4 |
| `test_listing_module.py` | 上架管理 | 3/3 |
| `test_sync_module.py` | 同步中心 | 4/4 |
| **总计** | | **26/26** |

### 11.2 运行测试

```bash
# 运行所有测试
for test in tests/test_*.py; do
  python "$test"
done
```

---

## 12. 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-09-24 | 初始版本，完成6个模块27个子模块 |

---

## 附录

### A. 目录结构

```
backend/
├── main.py                    # FastAPI主应用
├── init_db.py                 # 数据库初始化
├── engine/                    # 工作流引擎
│   ├── core.py
│   ├── executor.py
│   ├── state.py
│   └── scheduler.py
├── integrations/              # 外部集成
│   ├── config.py
│   └── newton_ai.py
├── modules/                   # 业务模块
│   ├── selection/             # 选品中心
│   ├── product_mgmt/          # 商品管理
│   ├── vision/                # AI视觉中心
│   ├── listing/               # 上架管理
│   ├── sync/                  # 同步中心
│   └── workflow_api.py        # 工作流API
├── data/                      # 数据库文件
├── workflow/                  # 工作流配置
└── tests/                     # 测试脚本
```

### B. 外部依赖

| 服务 | 用途 | 降级方案 |
|------|------|---------|
| 牛顿AI | 选品评分 | 规则引擎降级 |
| 火山引擎 | AI生图 | 占位图片 |
| WooCommerce | 商品推送 | 本地草稿池 |
| 阿里云OSS | CDN素材 | 本地存储 |