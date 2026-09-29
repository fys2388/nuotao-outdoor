# 产品生命周期工作流 (Product Lifecycle Workflow)

> **版本**: v1.0  
> **最后更新**: 2026-09-28  
> **状态**: Active

---

## 1. 概述

本文档定义了 Nuotao AI OS 中产品的完整生命周期工作流。产品从市场机会识别开始，经过 AI 分析、人工审批、Product Master 创建，最终发布到 WooCommerce 前台。

---

## 2. 生命周期阶段

### 2.1 阶段定义

| 阶段 | 标识符 | 类型 | 说明 |
|------|--------|------|------|
| **机会识别** | `opportunity` | 中间态 | 市场机会被识别，等待启动分析 |
| **候选产品** | `candidate` | 中间态 | 产品进入候选池，等待 AI 分析 |
| **AI 分析中** | `analysis` | 中间态 | AI 正在分析产品数据 |
| **待审批** | `pending_approval` | 中间态 | 等待人工审批决策 |
| **已批准** | `approved` | 中间态 | 已通过审批，等待生成 Listing |
| **Product Master** | `product_master` | 中间态 | 产品主数据已创建 |
| **B2C Listing** | `listing` | 中间态 | Listing 正在同步到 WooCommerce |
| **WC 已发布** | `wc_published` | 终态 | 产品已在 WooCommerce 前台发布 |
| **已淘汰** | `rejected` | 终态 | 产品被拒绝/淘汰 |

### 2.2 阶段优先级

```
rejected (终态)
  ↓
wc_published (终态)
  ↓
listing (中间态)
  ↓
pending_approval (中间态)
  ↓
approved (中间态)
  ↓
product_master (中间态)
  ↓
analysis (中间态)
  ↓
candidate (中间态)
  ↓
unknown (兜底)
```

**重要**: 终态必须优先于中间态。如果产品状态冲突，以更靠前的状态为准。

---

## 3. 后端状态轴 (Orthogonal State Axes)

### 3.1 Product 表状态字段

| 字段 | 类型 | 值域 | 说明 |
|------|------|------|------|
| `status` | VARCHAR | `draft`, `active`, `inactive`, `pending` | 产品基础状态 |
| `candidate_status` | VARCHAR | `candidate`, `approved`, `testing`, `winner`, `rejected`, `NULL` | 候选审批状态 |
| `funnel_stage` | VARCHAR | `recalled`, `screened`, `deep_candidate`, `test_candidate`, `testing`, `hero`, `rejected`, `NULL` | AI 漏斗阶段 |
| `mastered_at` | TIMESTAMP | `NULL` 或时间戳 | Product Master 创建时间 |
| `mastered_by` | VARCHAR | 用户 ID | Product Master 创建者 |

### 3.2 ListingJob 表状态

| 字段 | 值域 | 说明 |
|------|------|------|
| `status` | `pending`, `approved`, `processing`, `rejected`, `published`, `failed` | Listing 同步状态 |

### 3.3 ProductDecision 表状态

| 字段 | 值域 | 说明 |
|------|------|------|
| `approval_status` | `pending`, `approved`, `rejected` | 审批状态 |

---

## 4. 前端用户阶段映射

### 4.1 派生函数 (UI-only)

```typescript
function deriveUserStage(product: {
  candidate_status?: string | null
  funnel_stage?: string | null
  mastered_at?: string | null
  wc_status?: string | null
  listing_status?: string | null
}): string {
  // 1. Terminal: rejected
  if (product.candidate_status === 'rejected') return 'rejected'
  
  // 2. Terminal: WC Published
  if (product.wc_status === 'synced') return 'wc_published'
  
  // 3. Intermediate: Listing in progress
  if (product.listing_status && ['pending', 'approved', 'processing'].includes(product.listing_status)) {
    return 'listing'
  }
  
  // 4. Intermediate: Approved (with mastered_at)
  if (product.candidate_status === 'approved' && product.mastered_at) {
    return 'approved'
  }
  
  // 5. Intermediate: Product Master
  if (product.mastered_at) return 'product_master'
  
  // 6. Intermediate: AI Analysis
  if (product.funnel_stage && ['recalled', 'screened', 'deep_candidate'].includes(product.funnel_stage)) {
    return 'analysis'
  }
  
  // 7. Intermediate: Candidate
  if (product.candidate_status === 'candidate') return 'candidate'
  
  // 8. Fallback
  return 'unknown'
}
```

### 4.2 阶段徽章配置

```typescript
const STAGE_BADGE: Record<string, { text: string; color: string }> = {
  candidate: { text: '候选', color: 'orange' },
  analysis: { text: 'AI分析中', color: 'purple' },
  pending_approval: { text: '待审批', color: 'warning' },
  approved: { text: '已批准', color: 'success' },
  product_master: { text: 'Product Master', color: 'blue' },
  listing: { text: '上架中', color: 'cyan' },
  wc_published: { text: 'WC 已发布', color: 'geekblue' },
  rejected: { text: '已淘汰', color: 'default' },
  unknown: { text: '未知', color: 'default' },
}
```

---

## 5. API 端点

### 5.1 Workbench Summary

```
GET /api/v1/products/workbench/summary
```

返回 8 个阶段的计数和下一步操作。

### 5.2 Workbench Tasks

```
GET /api/v1/products/workbench/tasks
```

返回可操作的任务列表。

### 5.3 Product Rule Results

```
GET /api/v1/products/{product_id}/rule-results
```

返回产品 Hard Rule 评估结果。

### 5.4 Product WC Status

```
GET /api/v1/products/{product_id}/wc-status
```

返回产品 WooCommerce 同步状态。

---

## 6. 状态转换图

```
                    ┌─────────────┐
                    │ Opportunity │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Candidate  │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Analysis   │
                    └──────┬──────┘
                           │
                    ┌──────▼───────────┐
                    │ Pending Approval │
                    └──────┬───────────┘
                           │
              ┌────────────┼────────────┐
              │                        │
    ┌─────────▼─────────┐    ┌─────────▼─────────┐
    │      Rejected     │    │     Approved      │
    └───────────────────┘    └─────────┬─────────┘
                                       │
                                ┌──────▼──────┐
                                │Product Master│
                                └──────┬──────┘
                                       │
                                ┌──────▼──────┐
                                │   Listing   │
                                └──────┬──────┘
                                       │
                                ┌──────▼──────┐
                                │WC Published │
                                └─────────────┘
```

---

## 7. 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-09-28 | 初始版本，定义 8 个阶段和状态转换 |
