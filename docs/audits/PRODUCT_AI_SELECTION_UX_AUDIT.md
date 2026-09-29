# 商品与 AI 选品模块 UX / Workflow 审计报告

> 审计日期: 2026-09-28
> 审计范围: frontend/src/pages/*, backend/app/models/*, backend/app/services/product_*, backend/app/api/v1/endpoints/*
> 审计目的: 定位当前产品生命周期 UX 断点，为重构提供事实基础

---

## 1. 当前页面结构

### 1.1 导航分组 (navigation.tsx)

```
商品与 AI 选品 (group-products)
├── 市场机会          /products/publish          → MarketOpportunities
├── 牛顿 AI 对话选品  /products/newton-sourcing  → NewtonSourcing
├── 候选产品与选品    /products/candidates       → ProductCandidatesPage
├── AI 产品分析        /products/analysis         → ProductAnalysis
├── 成本与利润        /products/costs            → ProductCostsPage
├── 商品工作台        /products/pipeline         → ProductPipeline
├── 渠道与上架        /products/listing          → ProductPublish
├── 上架工单          /products/listing-jobs     → ListingJobs
└── 商品主数据        /products                  → Products
```

### 1.2 后端数据模型 (orthogonal status axes)

| 状态轴 | 字段 | 取值 | 说明 |
|--------|------|------|------|
| Commerce | `Product.status` | draft / active / inactive / pending | 商业执行状态 |
| Candidate | `Product.candidate_status` | candidate / approved / testing / winner / rejected / NULL | NULL=非候选商品(如WC同步的) |
| Funnel | `Product.funnel_stage` | recalled / screened / deep_candidate / test_candidate / testing / hero / rejected / NULL | V3.0选品漏斗 |
| Approval | `ProductDecision.approval_status` | pending / approved / rejected | 人工审批 |
| WC Sync | `ListingJob.status` | pending / approved / processing / rejected / published / failed | WC工单状态机 |
| Cost | `ProductCost` | cost_status: KNOWN / MISSING | 成本数据状态 |
| Score | `ProductNuotaoScore.grade` | hero / core / long_tail / reject | V3.0评分等级 |
| Draft | `WooCommerceDraft.status` | generated | 草稿载荷 |

**关键设计原则**: 后端采用正交状态轴，每个轴独立演进。UI 可以提供用户视角的阶段视图，但后端状态保持真实。

---

## 2. 当前用户流程

```
市场机会(MarketOpportunities)
  → 牛顿AI选品(NewtonSourcing)
    → 候选产品(ProductCandidatesPage)
      → AI产品分析(ProductAnalysis)
        → 成本与利润(ProductCostsPage)
          → 商品工作台(ProductPipeline) ← 一键批量流程
            → 渠道与上架(ProductPublish)
              → 上架工单(ListingJobs)
                → 商品主数据(Products) ← 最终数据
```

### 实际测试验证的流程 (2026-09-28 E2E测试)

```
1. 牛顿AI选品搜索 "户外折叠桌" → 成功返回10+结果 (~90秒)
2. 选中结果 → "带入工作流编辑" → 跳转到 ProductPipeline
3. 一键运行 → 6/7步完成 (90秒)
   - ✅ 商品信息
   - ✅ AI产品分析
   - ✅ 主图生产
   - ✅ 生图Prompt
   - ✅ 上架数据
   - ⏳ 上架WC (pending_review)
4. 上架数据预览:
   - SKU: NT-OUTDOOR-09281224
   - 售价: $45.00
   - 库存: 100
   - 短描述: "牛顿AI按性价比排序推荐（650+）" ← BUG!
   - 标签: 产品描述文本 ← BUG!
   - 分类: 120 (数字ID) ← BUG!
```

---

## 3. 当前存在的断点

### 3.1 流程断点 (Flow Breakpoints)

| # | 断点位置 | 描述 | 严重度 |
|---|---------|------|--------|
| 1 | 候选→审批 | Candidate 页面有 approve/reject 按钮，但无审批队列/待审视图 | **高** |
| 2 | 审批→Product Master | Approved 后没有明确的 "Product Master Created" 步骤 | **严重** |
| 3 | Product Master→Listing | 没有 Product Master → B2C Listing 的明确跳转 | **高** |
| 4 | Listing→WC | 上架按钮直接推 WC，无 Listing Approved 前置 | **严重** |
| 5 | 工作台→生命周期 | ProductPipeline 是一次性批量流程，不与生命周期阶段绑定 | **高** |
| 6 | 成本→审批 | 成本页面独立存在，不与审批闸门绑定 | 中 |
| 7 | Hard Rules→审批 | Hard Rules 评估结果没有明确展示在审批流程中 | **高** |

### 3.2 数据断点 (Data Breakpoints)

| # | 断点 | 当前值 | 应有值 |
|---|------|--------|--------|
| 1 | 短描述 | "牛顿AI按性价比排序推荐（650+）" | 产品描述 |
| 2 | 标签 | 产品描述文本(逗号分隔) | 关键词标签 |
| 3 | 分类 | 数字 "120" | 分类名称 |
| 4 | 品牌 | 空 | 品牌名 |
| 5 | 重量/尺寸 | "待补充" | 实际数值或 UNKNOWN |
| 6 | WC图片 | 无 | 生成图片URL |

### 3.3 状态断点 (State Breakpoints)

| # | 断点 | 描述 |
|---|------|------|
| 1 | Candidate vs Product | 同一 Product 行既是 Candidate 又是 Product Master，无明确分界 |
| 2 | Pipeline vs Lifecycle | Pipeline 是批量工作流，不追踪每个产品的生命周期阶段 |
| 3 | Approval vs Publication | 审批和发布没有独立的门控 |
| 4 | WC Sync Visibility | 用户无法看到 WC 同步的详细状态和错误 |

---

## 4. 重复功能

| # | 重复组 | 页面 | 问题 |
|---|--------|------|------|
| 1 | 选品相关 | Sourcing.tsx, NewtonSourcing.tsx, MarketOpportunities.tsx, ProductAnalysis.tsx | 4个选品/分析页面功能重叠 |
| 2 | AI分析相关 | AIAnalysis.tsx, ProductAnalysis.tsx | 2个分析页面 |
| 3 | 上架相关 | ProductPublish.tsx, ListingJobs.tsx, Products.tsx | 3个页面都有WC同步功能 |
| 4 | 工作台 | ProductPipeline.tsx, ProductAnalysis.tsx | 都做导入+分析 |
| 5 | 成本相关 | CostModel.tsx, ProductCostsPage.tsx | 2个成本页面 |

---

## 5. 状态混乱

### 5.1 Product 模型的 3 个状态字段并存

```python
# Product 表同时有:
status: str          # 'draft' | 'active' | 'inactive' | 'pending'
candidate_status: str | None  # 'candidate' | 'approved' | 'testing' | 'winner' | 'rejected' | None
funnel_stage: str | None     # 'recalled' | 'screened' | ... | None
```

- `status` 和 `candidate_status` 独立演进，没有强制一致性
- `funnel_stage` 完全独立于另外两个
- 前端页面各自读取不同字段，用户看到的状态不一致

### 5.2 Candidate 和 Product Master 共用一行

- 没有独立的 Product Master 创建步骤
- Candidate approved 后直接复用 Product 行
- 没有 `mastered_at` 时间戳
- 无法区分"正在选品的候选品"和"已批准的商品主数据"

### 5.3 Pipeline 状态和生命周期状态脱节

- ProductPipeline 有自己的 pipeline_id 和 6 步状态
- 与 Product.candidate_status / funnel_stage 完全无关
- Pipeline 完成后不会更新产品的生命周期状态
- 用户无法从 Pipeline 页面得知产品的实际生命周期阶段

---

## 6. 无法理解的按钮

| # | 按钮 | 页面 | 问题 |
|---|------|------|------|
| 1 | "一键运行" | ProductPipeline | 不清楚会执行什么，等待时间未知 |
| 2 | "确认上架" | ProductPipeline | 不清楚是上架到WC还是只是保存 |
| 3 | "推送WC" | Products | 不清楚推送哪些产品，无前置检查 |
| 4 | "同步WC" | Products | 不清楚是拉取还是推送 |
| 5 | "带入工作流" | NewtonSourcing | 不清楚导入后能做什么 |
| 6 | "加入候选" | NewtonSourcing | 不清楚候选和Product的关系 |
| 7 | "一键运行" | ProductAnalysis | 不清楚会执行什么步骤 |
| 8 | "导入并分析" | ProductAnalysis | 不清楚导入的是什么数据 |

---

## 7. API 与 UI 不一致

| # | 问题 | API 端点 | UI 行为 |
|---|------|---------|---------|
| 1 | Pipeline 完成不更新产品状态 | POST /product-pipeline/run | 前端只展示pipeline结果，不更新Product |
| 2 | WC 推送无审批门控 | POST /products/push-woocommerce | UI 直接推送，无 ListingJob 前置 |
| 3 | Candidate 审批不创建 Product Master | POST /product-candidates/{id}/promote | 只更新 candidate_status，不创建新实体 |
| 4 | 成本保存不更新 cost_status | POST /products/{id}/cost-snapshots | 前端不区分 KNOWN/MISSING |
| 5 | Hard Rules 评估结果不返回 | POST /selection/nuotao/evaluate | 前端只展示 total score，不展示 rule details |
| 6 | WC 同步无回读验证 | POST /products/sync-woocommerce | 前端不展示同步后验证结果 |

---

## 8. Product Candidate / Master / Listing / WC 的边界问题

### 当前边界 (模糊)

```
Product (candidate_status='candidate')
  → Product (candidate_status='approved')
    → Product (status='draft')
      → Product (status='active', woocommerce_id=xxx)
```

- **Candidate** 和 **Product Master** 是同一行数据
- **Listing** 和 **WC** 没有独立实体，直接写入 Product.meta
- **B2C Listing** 没有独立页面，混在 Products.tsx 中

### 应有边界 (清晰)

```
Candidate (独立实体或 candidate_status)
  → Approval (ProductDecision.approval_status)
    → Product Master (candidate_status='approved', 明确标记 mastered_at)
      → B2C Listing (独立 payload，包含 title/desc/images/attributes)
        → WC Sync (ListingJob，独立状态机)
```

---

## 9. 推荐的新信息架构

### 原则

1. **ONE PRIMARY ACTION**: 每个生命周期阶段只允许一个主动作
2. **用户阶段视图 ≠ 后端状态**: UI 可以简化展示，但后端保持正交状态
3. **候选 ≠ 商品**: Candidate 和 Product Master 有明确分界
4. **AI 建议 ≠ 人工决策**: 明确区分 AI Recommendation 和 Human Decision
5. **Listing ≠ WC**: Listing 是内容生成，WC 是发布同步

### 新导航结构

```
商品与 AI 选品
├── 📊 产品工作台 (新增) — 生命周期总览 + "下一步"指引
│
├── 🤖 AI 选品
│   ├── 🎯 市场机会 (复用 MarketOpportunities)
│   ├── 🔍 牛顿选品 (复用 NewtonSourcing)
│   ├── 📋 候选产品 (重构 ProductCandidatesPage)
│   ├── 📊 AI 分析 (重构 ProductAnalysis)
│   ├── ⏳ 待审批 (新增 — 审批队列)
│   └── ❌ 已淘汰 (新增 — 归档视图)
│
├── 📦 商品中心
│   ├── 🏭 Product Master (重构 Products)
│   ├── 📝 B2C Listing (新增 — 内容生成)
│   ├── 🏪 WooCommerce (重构 ProductPublish)
│   └── 📦 已下架 (新增 — 归档视图)
│
├── 💰 成本与定价 (复用 ProductCostsPage)
└── ⚖️ 规则与审核 (新增 — Hard Rules + Approval 集中管理)
```

---

## 10. 推荐的新页面结构

### 10.1 产品工作台 (Product Workbench) — 新增

**URL**: `/products/workbench`

**第一屏**:
```
生命周期看板:
  [机会 12] → [候选 8] → [AI分析 5] → [待审批 3] → [已批准 7] → [上架中 4] → [WC已发布 24] → [淘汰 3]

今日需要处理:
  ⚠️ 待审批: 3 件 → 去审批
  ⚠️ 数据不完整: 5 件 → 补充数据
  ⚠️ Hard Rule 风险: 2 件 → 查看风险
  ⚠️ Listing 待处理: 4 件 → 去生成
  ⚠️ WC 同步失败: 1 件 → 重试
```

**不是只展示统计数字**，而是提供明确的"下一步"操作入口。

### 10.2 AI 选品流水线 — 重构

**顶部生命周期条**:
```
[机会] → [候选] → [AI分析] → [待决策] → [Product Master] → [Listing] → [WooCommerce]
         ↑ 当前阶段高亮，可点击跳转
```

**尊重后端正交状态**:
- UI 显示用户阶段视图
- 后端保持 identity / lifecycle / publication / approval / sync 正交状态轴
- 不创建新的单一 backend status

### 10.3 候选产品卡片 — 重构

每个 Candidate 卡片必须显示:

```
产品: [名称] [SKU] [来源]
供应商: [名称] [采购价]

市场: [评分/10]
利润: [评分/10]
供应链: [评分/10]
风险: [评分/10]

Purchase Cost: ¥22.5
Landed Cost: $XX.XX (或 UNKNOWN)
Recommended Price: $XX.XX

Hard Rules: [PASS] / [FAIL] / [UNKNOWN]
  - rule_id: X
  - rule_version: vX
  - reason: ...

🤖 AI Recommendation: Recommend / Reject / Review
  Reasons: ...
  Risks: ...

[ONE PRIMARY ACTION] — 根据当前阶段只显示一个主按钮
```

### 10.4 产品详情页 — Product Decision Cockpit

**包含**:
1. Product facts (基本事实)
2. Market analysis (市场分析)
3. AI analysis (AI分析)
4. Cost / Profit (成本利润)
5. Supply Chain (供应链)
6. Hard Rules (硬规则)
7. Approval (审批)
8. Product Master (商品主数据)
9. B2C Listing (B2C内容)
10. WooCommerce (WC同步)
11. Lifecycle Timeline (生命周期时间线)

**顶部/右侧显示**:
- 当前阶段
- 当前状态
- 下一步动作

### 10.5 Cost / Profit UI — 重构

**必须优先显示**:
```
Landed Cost: $XX.XX (或 UNKNOWN — 绝不显示 0)

明细:
  Purchase Cost:     ¥XX.XX
  Domestic Shipping: ¥XX.XX
  Intl Shipping:     $XX.XX
  Packaging:         $XX.XX
  Tax Estimate:      $XX.XX
  Handling:          $XX.XX
  ─────────────────────────
  Total Landed:      $XX.XX
```

**Return Rate**:
```
如果无真实数据: 显示 "UNKNOWN"
绝不显示: 0%
绝不自动: PASS
```

### 10.6 Hard Rules UI — 新增

**必须明显区别于 AI Score**:

```
Hard Rules: [PASS] / [FAIL] / [UNKNOWN]

详细:
  [PASS] RULE-ID-X (v1): 规则描述 — reason
  [FAIL] RULE-ID-Y (v2): 规则描述 — reason
  [UNKNOWN] RULE-ID-Z (v3): 规则描述 — reason (需数据)

FAIL → 不能显示"AI建议发布"作为绕过
UNKNOWN → 进入 REVIEW / NEED DATA
```

### 10.7 AI Recommendation vs Human Decision

```
🤖 AI Recommendation: Recommend / Reject / Review
  Reasons: ...
  Risks: ...

👤 Human Decision: [Approve] [Reject] [Request Revision]
  (独立于 AI，AI 不等于最终审批)
```

### 10.8 Product Master — 明确分界

```
Candidate → Approved 后:

✅ Product Master Created
  Product ID: xxx
  SKU: xxx
  mastered_at: YYYY-MM-DD HH:MM (如果后端暂时没有，显示 "Not Available" — 不伪造)

然后进入:
  → B2C Listing
  → B2B
  → Commerce
```

### 10.9 B2C Listing — 新增独立页面

**内容必须基于 verified product facts**:
```
Title: [基于产品事实]
Description: [基于产品事实，AI不添加未验证事实]
Images: [已批准图片]
Attributes: [产品属性]
Price: [已批准价格]
Variants: [变体]
SEO: [标题/描述]
Compliance: [合规检查]
```

### 10.10 WooCommerce — 独立页面

**只有 B2C Listing Approved 才允许**:
```
Sync to WooCommerce

显示:
  Nuotao Product ID: xxx
  ↔
  WC Product ID: xxx (或 "Not synced")
  Sync status: [状态]
  Last sync: YYYY-MM-DD HH:MM
  Last error: xxx (如有)
```

**禁止在 Candidate 页面直接出现 "Push to WC"**

### 10.11 Lifecycle Timeline — 新增

```
Candidate    → 2026-09-28 12:15 (AI选品导入)
Analysis     → 2026-09-28 12:20 (AI分析完成)
Rule Eval    → 2026-09-28 12:25 (Hard Rules 评估)
Approval     → 2026-09-28 12:30 (人工审批通过)
Master       → 2026-09-28 12:31 (Product Master Created)
Content      → 2026-09-28 12:35 (B2C Listing 生成)
Listing      → 2026-09-28 12:40 (Listing Approved)
WC Sync      → 2026-09-28 12:45 (WC 同步完成)
Published    → 2026-09-28 12:45 (前台可见)

使用系统已有的 event / audit / trace_id
如果没有数据: 显示 "Not available" — 不伪造事件
```

---

## 11. API 与前端原则

### 11.1 禁止

- ❌ 为 UI 临时写 fake API
- ❌ Mock business data
- ❌ Hardcode fake counts
- ❌ 假装 WC 已同步
- ❌ 假装 Product Master 已创建
- ❌ 创建新的虚假 state

### 11.2 如果后端缺接口

按顺序识别 gap:
1. **frontend gap** — UI 需要但 API 不支持
2. **API gap** — API 需要但 Service 不支持
3. **data-model gap** — Service 需要但 Model 不支持

然后按层实施:
```
UI → API → Service → Model
```

### 11.3 安全要求

所有涉及以下操作的 UI 路径必须遵循认证/RBAC/Workspace/Approval:
- Approve / Reject
- Publish
- Push WC
- Pricing
- Inventory
- Delete

特别检查:
- `push-woocommerce?force=true` 不能出现在没有权限控制的 UI 路径中

---

## 12. 实施顺序

| Phase | 内容 | 依赖 |
|-------|------|------|
| 1 | READ / AUDIT (本文档) | — |
| 2 | UX Information Architecture (本文件 §9-10) | Phase 1 |
| 3 | Product Workbench (工作台) | Phase 2 |
| 4 | AI Candidate / Analysis UX | Phase 2 |
| 5 | Product Decision Cockpit | Phase 2 |
| 6 | Product Master / Listing | Phase 5 |
| 7 | WooCommerce Sync | Phase 6 |
| 8 | Timeline / Audit | Phase 7 |

每阶段:
```
implement → test → browser verify → review
```

---

## 13. 当前代码中已有的可复用组件

| 组件 | 文件 | 可复用程度 |
|------|------|-----------|
| 市场机会页面 | MarketOpportunities.tsx | 可直接复用 |
| 牛顿选品页面 | NewtonSourcing.tsx | 可复用搜索和结果展示 |
| 候选产品页面 | ProductCandidatesPage.tsx | 需重构卡片和审批流程 |
| 成本页面 | ProductCostsPage.tsx | 可复用成本展示 |
| 上架工单 | ListingJobs.tsx | 可复用工单状态机 |
| Pipeline 服务 | product_pipeline_service.py | 可复用部分步骤逻辑 |
| 后端 Product 模型 | product.py | 已有正交状态轴 |
| 后端 ProductIntelligence | product_intelligence.py | 已有评分/分析/决策模型 |
| 后端 ListingJob | listing_job.py | 已有完整工单状态机 |
| 后端 Rule | rule.py | 已有规则注册表 |

---

## 14. 测试验证结果

### 14.1 浏览器验证通过

- ✅ AI 选品搜索成功返回结果
- ✅ 产品带入工作流成功
- ✅ 一键运行完成 6/7 步
- ✅ SKU 自动生成: NT-OUTDOOR-09281224
- ✅ 售价自动计算: $45.00

### 14.2 浏览器验证失败 (BUG)

- ❌ 短描述: "牛顿AI按性价比排序推荐（650+）" — 应该是产品描述
- ❌ 标签: 产品描述文本 — 应该是关键词标签
- ❌ 分类: 数字 120 — 应该是分类名称
- ❌ 品牌: 空 — 应该从1688提取
- ❌ 重量/尺寸: "待补充" — 应该从1688提取或标记 UNKNOWN
- ❌ WC 图片: 无 — 应该包含生成的图片

### 14.3 未验证

- ❌ 1688 重复上传防护
- ❌ Product Master 创建
- ❌ B2C Listing 独立生成
- ❌ Hard Rules 展示
- ❌ Lifecycle Timeline
- ❌ 审批队列
- ❌ WC 同步验证

---

## 15. 与 PRODUCT_LIFECYCLE_WORKFLOW.md 的一致性检查

**注意**: `PRODUCT_LIFECYCLE_WORKFLOW.md` 和 `PRODUCT_LIFECYCLE_IMPLEMENTATION_ROADMAP.md` 文件目前不存在于代码仓库中。

**基于代码和文档推断的生命周期**:

```
docs/development_roadmap.md: 选品→上架全链路
docs/shop_launch_plan.md: 1688选品 → 人工审批 → pipeline自动推进
docs/agent_automation_upgrade_p0_p2.md: 选品→信息录入→文案→图片→定价→库存→上架→SEO (8步)
```

**当前前端 ProductPipeline.tsx 定义**:
```
6步: 商品信息 → AI分析 → 主图 → Prompt → 上架数据 → WC上架
```

**差异**:
- 文档要求 8 步 (含定价、库存、SEO)
- 前端实现 6 步 (缺少定价、库存、SEO)
- ProductPipeline 是一次性批量流程，不是生命周期追踪

---

## 16. 结论

### 用户是否可以清楚地完成全流程？

**当前答案: 不能。**

关键断点:

1. **Candidate → Product Master**: 没有明确分界，同一行数据兼任两个角色
2. **审批队列缺失**: 没有集中展示"待审批"产品的视图
3. **Hard Rules 不可见**: 规则评估结果没有展示在审批流程中
4. **Product Master → Listing**: 没有从 Product Master 生成 B2C Listing 的步骤
5. **Listing → WC**: 没有 Listing Approved 前置门控
6. **"下一步"缺失**: 每个页面都不知道下一步应该做什么
7. **数据质量问题**: 短描述、标签、分类等字段数据错误

### 需要回答的关键问题

1. 用户"我现在在哪里？" → 当前无法回答
2. 用户"这个产品是什么状态？" → 多个状态字段并存，无法统一回答
3. 用户"为什么是这个状态？" → 没有状态变更原因追踪
4. 用户"我下一步应该做什么？" → 没有"下一步"指引

---

## 附录: 文件索引

### 前端
- `frontend/src/config/navigation.tsx` — 导航配置
- `frontend/src/app/AppRoutes.tsx` — 路由配置
- `frontend/src/pages/ProductPipeline.tsx` — 商品工作台 (927行)
- `frontend/src/pages/ProductCandidatesPage.tsx` — 候选产品 (2239行)
- `frontend/src/pages/ProductAnalysis.tsx` — AI产品分析 (1077行)
- `frontend/src/pages/Products.tsx` — 商品主数据 (810行)
- `frontend/src/pages/ProductPublish.tsx` — 渠道与上架 (798行)
- `frontend/src/pages/ProductCostsPage.tsx` — 成本与利润 (668行)
- `frontend/src/pages/NewtonSourcing.tsx` — 牛顿选品 (675行)
- `frontend/src/pages/MarketOpportunities.tsx` — 市场机会 (98行)
- `frontend/src/pages/ListingJobs.tsx` — 上架工单 (428行)
- `frontend/src/api/client.ts` — API 客户端 (1239行)

### 后端
- `backend/app/models/product.py` — Product/Cost 模型
- `backend/app/models/product_intelligence.py` — 智能模型 (583行)
- `backend/app/models/listing_job.py` — 工单模型 (203行)
- `backend/app/models/product_mapping.py` — 映射模型
- `backend/app/models/rule.py` — 规则模型
- `backend/app/models/identity.py` — 身份模型
- `backend/app/services/product_pipeline_service.py` — Pipeline 服务 (1819行)
