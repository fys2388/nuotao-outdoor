# Nuotao AI OS - 工作流引擎API文档

> 版本: 1.0.0 | 最后更新: 2026-09-24

---

## 概述

工作流引擎是 Nuotao AI OS 的核心调度组件，采用 JSON 驱动配置，支持：
- 6个主模块、27个子模块的完整业务链路
- 自动流转与人工触发混合模式
- 异常工单挂起与断点续跑
- 重试策略（指数退避、立即重试）

---

## 快速开始

### 启动服务

```bash
# 一键启动
python start.py

# 或手动启动
python backend/init_db.py
uvicorn backend.main:app --reload --port 8000
```

### 访问文档

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- 健康检查: http://localhost:8000/health

---

## API端点

### 1. 工作流实例管理

#### 创建实例
```
POST /api/v1/workflow/instance/create
```

**请求体:**
```json
{
  "product_data": {
    "sku": "TEST-001",
    "name": "户外露营帐篷",
    "price": 99.99
  },
  "trigger_source": "manual",
  "options": {}
}
```

**响应:**
```json
{
  "success": true,
  "data": {
    "instance_id": "8d15aa6f-..."
  }
}
```

#### 查询实例
```
GET /api/v1/workflow/instance/{instance_id}
```

#### 实例列表
```
GET /api/v1/workflow/instances?status=running&limit=50
```

#### 暂停实例
```
POST /api/v1/workflow/instance/pause
{
  "instance_id": "8d15aa6f-...",
  "reason": "manual_pause"
}
```

#### 恢复实例（断点续跑）
```
POST /api/v1/workflow/instance/resume
{
  "instance_id": "8d15aa6f-...",
  "from_node": "vision",
  "reason": "manual_resume"
}
```

---

### 2. 工作流配置

#### 获取完整配置
```
GET /api/v1/workflow/config
```

**响应示例:**
```json
{
  "workflowId": "nuotao_product_wc_publish_v1",
  "version": "1.0.0",
  "nodes": [
    {
      "id": "selection",
      "module": 1,
      "name": "选品中心"
    }
  ],
  "imageConstraints": {
    "locked": true,
    "mainImages": {
      "count": 5,
      "ratio": "1:1",
      "width": 2048,
      "height": 2048
    },
    "detailImages": {
      "count": 6,
      "ratio": "3:4",
      "width": 1536,
      "height": 2048
    }
  }
}
```

#### 获取图片约束（锁定）
```
GET /api/v1/workflow/config/constraints
```

---

### 3. 选品中心

#### 采集商品
```
POST /api/v1/selection/collect
```

**请求体:**
```json
{
  "url": "https://detail.1688.com/offer/123456.html",
  "source": "1688"
}
```

#### 牛顿AI评分
```
POST /api/v1/selection/score
```

**请求体:**
```json
{
  "product_data": {
    "sku": "TEST-001",
    "title": "户外帐篷"
  },
  "target_market": "US"
}
```

#### 人工预审
```
POST /api/v1/selection/review
```

**请求体:**
```json
{
  "product_data": {"sku": "TEST-001"},
  "score_result": {"score": 75, "score_level": "high"},
  "decision": "approved",
  "reviewer": "admin"
}
```

---

### 4. 商品管理

#### 元数据清洗
```
POST /api/v1/product-mgmt/clean
```

#### 多语言翻译
```
POST /api/v1/product-mgmt/translate
```

#### 创建SKU
```
POST /api/v1/product-mgmt/sku/create
```

---

### 5. AI视觉中心

#### 创建生图任务
```
POST /api/v1/vision/task/create
```

**请求体:**
```json
{
  "product_data": {
    "sku": "TEST-001",
    "title_en": "Outdoor Tent"
  },
  "image_type": "main",
  "triggered_by": "manual"
}
```

#### 执行生图任务
```
POST /api/v1/vision/task/execute
{
  "task_id": "VIS-ABC12345"
}
```

---

### 6. 上架管理

#### 预上架校验
```
POST /api/v1/listing/validate
```

#### 打包WC数据包
```
POST /api/v1/listing/pack
```

#### 创建草稿
```
POST /api/v1/listing/draft/create
```

---

### 7. 同步中心

#### 推送商品到WC
```
POST /api/v1/sync/push/{draft_id}
```

#### WC Webhook回调
```
POST /api/v1/sync/webhook
```

#### 手动触发同步
```
POST /api/v1/sync/sync/manual
```

---

## 模块架构

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
│  选品中心      │    │  商品管理      │    │  AI视觉中心    │
│  selection    │    │  product_mgmt │    │  vision       │
└───────┬───────┘    └───────┬───────┘    └───────┬───────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │    上架管理        │
                    │    listing         │
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │    同步中心        │
                    │    sync            │
                    └───────────────────┘
```

---

## 状态流转

```
selection → product_mgmt → vision → listing → sync
    │            │            │         │        │
    │            │            │         │        ▼
    ▼            ▼            ▼         ▼    [同步完成]
 归档池       人工校对      视觉工单   草稿池
```

---

## 重试策略

| 场景 | 最大重试 | 策略 | 失败动作 |
|------|---------|------|---------|
| 牛顿AI | 2 | 立即重试 | 降级评分 |
| AI生图 | 2 | 立即重试 | 生成工单 |
| WC推送 | 3 | 指数退避 | 生成工单 |

---

## 禁止项

1. 禁止降低图片规格要求
2. 禁止删除子模块、截断流程分支
3. 禁止硬编码业务参数
4. 禁止异常直接终止流程
5. 禁止替换选品AI源

---

## 数据库表

| 数据库 | 表名 | 说明 |
|--------|------|------|
| workflow_state.db | workflow_instances | 工作流实例 |
| workflow_state.db | workflow_history | 执行历史 |
| workflow_state.db | workflow_logs | 运行日志 |
| workflow_state.db | workflow_tickets | 异常工单 |
| archive_pool.db | archived_products | 候选归档池 |
| collection_logs.db | collection_logs | 采集日志 |
| collection_logs.db | newton_ai_logs | 牛顿AI日志 |
| asset_library.db | assets | 素材库 |
| draft_pool.db | drafts | 上架草稿池 |

---

## 环境变量

```bash
# 牛顿AI
NEWTON_API_KEY=your_key
NEWTON_BASE_URL=https://api.newton.ai/v1

# 火山引擎
VOLCENGINE_API_KEY=your_key
VOLCENGINE_API_SECRET=your_secret

# WooCommerce
WC_CONSUMER_KEY=your_key
WC_CONSUMER_SECRET=your_secret
WC_BASE_URL=https://nuotaooutdoor.com
```

---

## 测试

```bash
# 运行所有测试
python tests/test_workflow_engine.py
python tests/test_selection_module.py
python tests/test_product_mgmt.py
python tests/test_vision_module.py
python tests/test_listing_module.py
python tests/test_sync_module.py
```

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-09-24 | 初始版本，完成6个模块 |