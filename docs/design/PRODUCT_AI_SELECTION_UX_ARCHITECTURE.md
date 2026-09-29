# 商品与 AI 选品 UX 重构 — Information Architecture / State Mapping

> 阶段: Phase 2 — Information Architecture / State Mapping
> 基于: docs/audits/PRODUCT_AI_SELECTION_UX_AUDIT.md (Phase 1)
> 依赖: ADR COMMERCE-001, ADR AGENTS-001, ADR IDENTITY-001
> 约束: 禁止修改业务代码。本阶段仅输出设计方案。

---

## 1. 设计目标

### 1.1 核心原则

```
用户每个页面都知道下一步应该做什么。

ONE PRIMARY ACTION: 每个生命周期阶段只允许一个主动作。
```

### 1.2 具体目标

| # | 目标 | 验收标准 |
|---|------|---------|
| 1 | 用户阶段视图 | UI 显示统一阶段，后端保持正交状态轴 |
| 2 | Candidate ≠ Product Master | 明确分界，不伪造 mastered_at |
| 3 | 待审批工作台 | 集中展示待决策产品，只显示审批动作 |
| 4 | Listing → WC 门控 | 只有 Listing Approved 才能 Sync WC |
| 5 | 消除重复页面 | 用户只需记住一个入口: 产品工作台 |
| 6 | 状态可追溯 | 每个产品有完整 Lifecycle Timeline |
| 7 | API/UI 一致 | 不创建 fake API，不伪造状态 |

### 1.3 非目标 (Non-Goals)

- ❌ 不创建新的单一 backend status
- ❌ 不重写整个前端
- ❌ 不改变正交状态轴设计
- ❌ 不绕过认证/RBAC/Workspace/Approval
- ❌ 不恢复 force=true 绕过

---

## 2. 信息架构

### 2.1 新导航结构

```
商品与 AI 选品
├── 📊 产品工作台          /products/workbench          (新增)
│
├── 🤖 AI 选品
│   ├── 🎯 市场机会         /products/opportunities      (复用 MarketOpportunities)
│   ├── 🔍 牛顿选品         /products/newton-sourcing    (复用 NewtonSourcing)
│   ├── 📋 候选产品         /products/candidates         (重构 ProductCandidatesPage)
│   ├── 📊 AI 分析          /products/analysis           (复用 ProductAnalysis)
│   ├── ⏳ 待审批           /products/approvals          (新增 Approval Workbench)
│   └── ❌ 已淘汰           /products/rejected           (新增归档视图)
│
├── 📦 商品中心
│   ├── 🏭 Product Master   /products/master             (重构 Products)
│   ├── 📝 B2C Listing      /products/listing            (新增 Listing 页面)
│   ├── 🏪 WooCommerce      /products/woocommerce        (重构 ProductPublish)
│   └── 📦 已下架           /products/archived           (新增归档视图)
│
├── 💰 成本与定价           /products/costs              (复用 ProductCostsPage)
└── ⚖️ 规则与审核           /products/rules              (新增 Hard Rules 集中管理)
```

### 2.2 与现有页面的映射

| 新页面 | 现有页面 | 操作 | 说明 |
|--------|---------|------|------|
| 产品工作台 | — | 新增 | 生命周期总览 + "下一步"指引 |
| 市场机会 | MarketOpportunities | 复用 | 路由从 /products/publish 改为 /products/opportunities |
| 牛顿选品 | NewtonSourcing | 复用 | 路由不变 |
| 候选产品 | ProductCandidatesPage | 重构 | 卡片增加 Hard Rules / Cost / AI Rec |
| AI 分析 | ProductAnalysis | 复用 | 路由不变 |
| 待审批 | — | 新增 | Approval Workbench |
| 已淘汰 | — | 新增 | 归档视图 |
| Product Master | Products | 重构 | 移除 WC 同步功能，纯 Product Master |
| B2C Listing | — | 新增 | 独立 Listing 内容生成 |
| WooCommerce | ProductPublish | 重构 | 只保留 WC 同步，移除 Listing 生成 |
| 已下架 | — | 新增 | 归档视图 |
| 成本与定价 | ProductCostsPage | 复用 | 路由不变 |
| 规则与审核 | — | 新增 | Hard Rules 集中管理 |

### 2.3 废弃/Redirect 的旧页面

| 旧路由 | 旧页面 | 新路由 | 说明 |
|--------|--------|--------|------|
| /products/publish | MarketOpportunities | /products/opportunities | 301 redirect |
| /products/listing | ProductPublish | /products/woocommerce | 301 redirect |
| /products | Products | /products/master | 保留原路由但改为 Product Master |
| /products/pipeline | ProductPipeline | — | 保留但标记 deprecated |
| /products/listing-jobs | ListingJobs | — | 保留但标记 deprecated |
| /products/costs | ProductCostsPage | /products/costs | 不变 |

---

## 3. 页面结构

### 3.1 产品工作台 (Product Workbench)

**URL**: `/products/workbench`

**第一屏: 生命周期看板**

```
┌─────────────────────────────────────────────────────────────┐
│  📊 产品工作台                                                │
│                                                              │
│  ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐     │
│  │机会  │ → │候选  │ → │AI分析│ → │待审批│ → │已批准│     │
│  │  12  │   │  8   │   │  5   │   │  3   │   │  7   │     │
│  └──────┘   └──────┘   └──────┘   └──────┘   └──────┘     │
│                                                              │
│  ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐     │
│  │上架中│ → │WC发布│ → │已下架│   │已淘汰│   │       │     │
│  │  4   │   │ 24   │   │  3   │   │  3   │   │       │     │
│  └──────┘   └──────┘   └──────┘   └──────┘   └──────┘     │
│                                                              │
│  每个节点可点击 → 跳转到对应筛选视图                          │
└─────────────────────────────────────────────────────────────┘
```

**第二屏: 今日需要处理**

```
┌─────────────────────────────────────────────────────────────┐
│  ⚠️ 今日需要处理                                              │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ ⚠️ 待审批: 3 件              [去审批 →]                  ││
│  │    - 户外折叠桌 ¥22.5 → $45.00 (Hard Rules: FAIL)       ││
│  │    - 便携榨汁杯 ¥35.0 → $59.99 (Hard Rules: UNKNOWN)    ││
│  │    - 露营灯 ¥18.5 → $39.99 (Hard Rules: PASS)           ││
│  ├─────────────────────────────────────────────────────────┤│
│  │ ⚠️ 数据不完整: 5 件            [补充数据 →]              ││
│  │    - 缺少成本数据 (3件)                                    ││
│  │    - 缺少图片 (2件)                                       ││
│  ├─────────────────────────────────────────────────────────┤│
│  │ ⚠️ Hard Rule 风险: 2 件          [查看风险 →]            ││
│  │    - Rule V8: Brand Fit < 5 (1件)                        ││
│  │    - Rule V3: Margin < 50% (1件)                         ││
│  ├─────────────────────────────────────────────────────────┤│
│  │ ⚠️ Listing 待处理: 4 件           [去生成 →]              ││
│  │    - 已批准但未生成 Listing (4件)                          ││
│  ├─────────────────────────────────────────────────────────┤│
│  │ ⚠️ WC 同步失败: 1 件             [重试 →]                ││
│  │    - WC API Error: 分类不存在 (1件)                       ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

**设计原则**: 不只展示统计数字，而是提供明确的"下一步"操作入口。

---

## 4. Product Workbench 设计

### 4.1 生命周期阶段定义

```
用户阶段           派生逻辑                        主动作
─────────────────────────────────────────────────────────────
机会               无 candidate 记录              创建候选
候选               candidate_status='candidate'   启动 AI 分析
AI 分析中          analysis_status='running'      等待分析完成
分析完成           analysis_status='completed'    提交审批
待审批             decision.approval='pending'    审批 / 驳回 / 请求修改
已批准             decision.approval='approved'   建立 Product Master
Product Master     mastered_at 有值               生成 B2C Listing
Listing 生成中     listing_status='generating'    等待生成完成
Listing 待审       listing_status='pending'       审批 Listing
Listing 已批准     listing_status='approved'      同步 WooCommerce
WC 同步中          wc_sync_status='syncing'       等待同步完成
WC 已发布          wc_sync_status='published'     查看前台
WC 同步失败        wc_sync_status='failed'        重试 / 修复
已下架             status='inactive'              归档 / 重新上架
已淘汰             candidate_status='rejected'    查看原因 / 归档
```

### 4.2 状态筛选视图

点击看板节点后，页面下方显示筛选后的产品列表:

```
[筛选: 待审批]  3 件产品
┌─────────────────────────────────────────────────────────────┐
│ 产品名称    │ 采购价  │ 建议售价 │ Hard Rules │ AI Rec │ 操作 │
│─────────────┼─────────┼─────────┼────────────┼────────┼─────│
│ 户外折叠桌  │ ¥22.5   │ $45.00  │ ❌ FAIL    │ Review │ [查看]│
│ 便携榨汁杯  │ ¥35.0   │ $59.99  │ ⚠️ UNKNOWN │ Recommend│[查看]│
│ 露营灯      │ ¥18.5   │ $39.99  │ ✅ PASS    │ Recommend│[查看]│
└─────────────────────────────────────────────────────────────┘
```

---

## 5. Product Decision Cockpit 设计

### 5.1 页面布局

**URL**: `/products/:productId`

```
┌─────────────────────────────────────────────────────────────┐
│  产品: 户外折叠桌                                    [返回工作台]│
│  SKU: NT-OUTDOOR-09281224                                   │
│                                                              │
│  当前阶段: 待审批    │    当前状态: Hard Rules FAIL           │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  ⚠️ 下一步: 查看 Hard Rules 详情并决定是否继续审批       ││
│  │  [查看 Hard Rules] [提交审批] [驳回]                     ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  ⚠️ 风险:                                                 ││
│  │  - Rule V3: 利润率 42% < 50% 阈值                        ││
│  │  - Rule V8: Brand Fit 4.2 < 5.0 (一票否决)              ││
│  │                                                           ││
│  │  阻断原因: Hard Rules FAIL (V8 一票否决)                 ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### 5.2 主体内容区 (Tabs)

```
Tabs:
[Product Facts] [Market] [AI Analysis] [Cost/Profit] [Supply Chain] 
[Hard Rules] [Approval] [Product Master] [B2C Listing] [WooCommerce] 
[Lifecycle Timeline]
```

#### Tab 1: Product Facts

```
┌─────────────────────────────────────────────────────────────┐
│  Product Facts                                                │
│                                                              │
│  名称: 户外折叠桌                                             │
│  SKU: NT-OUTDOOR-09281224                                    │
│  来源: 1688 (https://detail.1688.com/offer/972628402150.html)│
│  供应商: 永康市茹轩不锈钢制品厂                                │
│  品牌: Nuotao                                                 │
│  类目: 露营装备 > 折叠桌                                      │
│  目标市场: US                                                 │
│  重量: 2.5 kg                                                │
│  尺寸: 60x40x75 cm                                           │
│  采购价: ¥22.5                                                │
│  创建时间: 2026-09-28 12:15                                   │
└─────────────────────────────────────────────────────────────┘
```

#### Tab 2: Market

```
┌─────────────────────────────────────────────────────────────┐
│  Market Analysis                                              │
│                                                              │
│  市场需求: [8/10] ████████░░                                  │
│  竞争度: [6/10] ██████░░░░                                    │
│  趋势: [7/10] ███████░░░                                     │
│                                                              │
│  AI 洞察:                                                     │
│  "美国户外露营市场持续增长，折叠桌品类年搜索量增长 35%。       │
│   竞争度中等，头部品牌集中度低，适合新品牌切入。"              │
└─────────────────────────────────────────────────────────────┘
```

#### Tab 3: AI Analysis

```
┌─────────────────────────────────────────────────────────────┐
│  AI Analysis                                                  │
│                                                              │
│  产品报告 (17字段):                                            │
│  - 产品名称: 户外战术折叠桌                                   │
│  - 产品类别: 露营装备                                         │
│  - 产品尺寸: 60x40x75 cm                                      │
│  - 材质工艺: 碳钢 + 高温喷塑涂层                               │
│  - 核心卖点: [折叠收纳, 30kg承重, 军绿战术风]                  │
│  - 目标人群: 户外露营爱好者                                   │
│  - 使用场景: [露营, 野餐, 战术作业]                            │
│  ...                                                          │
│                                                              │
│  分析引擎: heuristic-v1                                      │
│  分析时间: 2026-09-28 12:20                                   │
│  Token 使用: 1,234 tokens                                     │
│  估算成本: $0.03                                             │
└─────────────────────────────────────────────────────────────┘
```

#### Tab 4: Cost / Profit

```
┌─────────────────────────────────────────────────────────────┐
│  Cost / Profit                                                │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  Landed Cost: $28.50                                     ││
│  │                                                          ││
│  │  Purchase Cost:         ¥22.50                           ││
│  │  Domestic Shipping:     ¥5.00                            ││
│  │  Intl Shipping:         $12.00                           ││
│  │  Packaging:             $2.50                            ││
│  │  Tax Estimate:          $3.50                            ││
│  │  Handling:              $3.00                            ││
│  │  ─────────────────────────────────────────────           ││
│  │  Total Landed:          $28.50                           ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  建议售价: $45.00                                             │
│  贡献毛利: $16.50 (36.7%)                                    │
│  ⚠️ 警告: 利润率 36.7% < 50% 阈值 (Rule V3)                │
│                                                              │
│  Return Rate: UNKNOWN (无历史数据)                            │
│  Cost Status: KNOWN                                          │
│  Cost Version: v1                                            │
│  Valid From: 2026-09-28                                      │
└─────────────────────────────────────────────────────────────┘
```

**关键规则**: 
- Landed Cost 优先显示
- UNKNOWN 绝不写成 0
- Return Rate 无数据时显示 UNKNOWN，不自动 PASS

#### Tab 5: Supply Chain

```
┌─────────────────────────────────────────────────────────────┐
│  Supply Chain                                                 │
│                                                              │
│  供应商: 永康市茹轩不锈钢制品厂                                │
│  采购价: ¥22.5                                                │
│  起订量: 100 件                                               │
│  交期: 15 天                                                  │
│  履约支揽率: 86.4%                                            │
│  回头率: 48%                                                  │
│  诚信通: 11 年                                                │
│                                                              │
│  供应商评分: [7.2/10]                                         │
│  风险: 低                                                     │
└─────────────────────────────────────────────────────────────┘
```

#### Tab 6: Hard Rules

```
┌─────────────────────────────────────────────────────────────┐
│  Hard Rules                                                   │
│                                                              │
│  总体: ❌ FAIL (1 项一票否决)                                  │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ ❌ FAIL  Rule V8 (v1) - Brand Fit Hard Veto              ││
│  │   原因: Brand Fit Score 4.2 < 5.0                       ││
│  │   阈值: 5.0 (brand_fit_threshold)                        ││
│  │   操作: 需人工复核，不可自动绕过                            ││
│  ├─────────────────────────────────────────────────────────┤│
│  │ ⚠️ FAIL  Rule V3 (v1) - Minimum Margin                   ││
│  │   原因: Margin Rate 36.7% < 50%                          ││
│  │   阈值: 50% (min_margin_rate)                             ││
│  │   操作: 需提价或降低成本                                   ││
│  ├─────────────────────────────────────────────────────────┤│
│  │ ✅ PASS  Rule V1 (v1) - Category Whitelist               ││
│  │   原因: 类目 "露营装备" 在白名单内                        ││
│  ├─────────────────────────────────────────────────────────┤│
│  │ ⚠️ UNKNOWN  Rule V5 (v1) - Weight Threshold              ││
│  │   原因: 重量数据缺失                                      ││
│  │   操作: 需补充数据后重新评估                               ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  ⚠️ FAIL 时不能显示"AI 建议发布"作为绕过                       │
│  ⚠️ UNKNOWN 时进入 REVIEW / NEED DATA                        │
└─────────────────────────────────────────────────────────────┘
```

#### Tab 7: Human Approval

```
┌─────────────────────────────────────────────────────────────┐
│  Human Approval                                               │
│                                                              │
│  🤖 AI Recommendation: REVIEW                                │
│  Reasons: [利润率偏低, Brand Fit 一票否决]                     │
│  Risks: [合规风险, 市场风险]                                  │
│                                                              │
│  ─────────────────────────────────────────────────────       │
│                                                              │
│  👤 Human Decision: [未决策]                                  │
│                                                              │
│  [批准]  [驳回]  [请求修改]                                   │
│                                                              │
│  ⚠️ AI 不等于最终审批。AI 仅提供建议，人工决策为准。            │
│                                                              │
│  ─────────────────────────────────────────────────────       │
│                                                              │
│  审批历史:                                                    │
│  - 2026-09-28 12:25 - AI 提交审批请求                        │
│  - (等待人工决策)                                              │
└─────────────────────────────────────────────────────────────┘
```

#### Tab 8: Product Master

```
┌─────────────────────────────────────────────────────────────┐
│  Product Master                                               │
│                                                              │
│  状态: ❌ Not Created                                        │
│                                                              │
│  ⚠️ 需要先通过审批才能创建 Product Master                      │
│                                                              │
│  当前 Candidate 状态: candidate                               │
│  当前 Approval 状态: pending                                  │
│                                                              │
│  mastered_at: Not recorded                                    │
│                                                              │
│  [提交审批 →]  (跳转到 Approval tab)                          │
└─────────────────────────────────────────────────────────────┘
```

**当 Product Master 已创建时**:

```
┌─────────────────────────────────────────────────────────────┐
│  Product Master                                               │
│                                                              │
│  ✅ Created                                                  │
│                                                              │
│  Product ID: uuid-xxx                                        │
│  SKU: NT-OUTDOOR-09281224                                    │
│  mastered_at: 2026-09-28 12:31                               │
│                                                              │
│  下一步: 生成 B2C Listing                                     │
│  [生成 Listing →]                                             │
└─────────────────────────────────────────────────────────────┘
```

#### Tab 9: B2C Listing

```
┌─────────────────────────────────────────────────────────────┐
│  B2C Listing                                                  │
│                                                              │
│  状态: ❌ Not Generated                                       │
│                                                              │
│  ⚠️ 需要先创建 Product Master 才能生成 Listing                 │
│                                                              │
│  Product Master 状态: Not Created                             │
│                                                              │
│  [创建 Product Master →]                                     │
└─────────────────────────────────────────────────────────────┘
```

**当 Listing 已生成时**:

```
┌─────────────────────────────────────────────────────────────┐
│  B2C Listing                                                  │
│                                                              │
│  状态: ⏳ Generated (待审核)                                   │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  Title: Nuotao Folding Tactical Table - Portable...       ││
│  │  Description: [基于产品事实的英文描述]                     ││
│  │  Images: 5 main + 6 detail                               ││
│  │  Price: $45.00                                           ││
│  │  Attributes: [Material: Carbon Steel, ...]               ││
│  │  SEO: Title + Description                                 ││
│  │  Compliance: [Passed]                                     ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  Listing Status: generated                                   │
│  Created: 2026-09-28 12:35                                   │
│                                                              │
│  [批准 Listing]  [修改]  [重新生成]                           │
└─────────────────────────────────────────────────────────────┘
```

#### Tab 10: WooCommerce

```
┌─────────────────────────────────────────────────────────────┐
│  WooCommerce                                                  │
│                                                              │
│  状态: ❌ Not Synced                                         │
│                                                              │
│  ⚠️ 需要先批准 Listing 才能同步 WooCommerce                    │
│                                                              │
│  Listing 状态: generated (未批准)                             │
│                                                              │
│  [批准 Listing →]                                            │
└─────────────────────────────────────────────────────────────┘
```

**当 WC 已同步时**:

```
┌─────────────────────────────────────────────────────────────┐
│  WooCommerce                                                  │
│                                                              │
│  ✅ Synced                                                    │
│                                                              │
│  Nuotao Product ID: uuid-xxx                                  │
│  ↔                                                           │
│  WC Product ID: 2196                                          │
│  WC Slug: outdoor-folding-tactical-table                      │
│  Sync Status: published                                       │
│  Last Sync: 2026-09-28 12:45                                  │
│  Last Error: None                                             │
│  Retry Count: 0                                               │
│                                                              │
│  前台链接: https://shop.nuotao.com/product/2196/              │
│                                                              │
│  [同步到 WC]  [回读验证]  [下架]                               │
└─────────────────────────────────────────────────────────────┘
```

**Listing 未批准时 — 按钮不存在或 disabled**:

```
┌─────────────────────────────────────────────────────────────┐
│  WooCommerce                                                  │
│                                                              │
│  ❌ Blocked                                                   │
│                                                              │
│  ⚠️ Listing 未批准，无法同步 WooCommerce                       │
│                                                              │
│  Listing 状态: generated (待批准)                             │
│                                                              │
│  [同步到 WC]  ← disabled                                     │
│  [批准 Listing →]                                             │
└─────────────────────────────────────────────────────────────┘
```

#### Tab 11: Lifecycle Timeline

```
┌─────────────────────────────────────────────────────────────┐
│  Lifecycle Timeline                                           │
│                                                              │
│  📍 Candidate        2026-09-28 12:15  AI 选品导入            │
│  │                                                           │
│  📍 Analysis          2026-09-28 12:20  AI 分析完成            │
│  │                                                           │
│  📍 Rule Evaluation   2026-09-28 12:22  Hard Rules 评估        │
│  │    - V3: FAIL (margin 36.7% < 50%)                        │
│  │    - V8: FAIL (brand fit 4.2 < 5.0) ← 一票否决             │
│  │    - V1: PASS                                              │
│  │    - V5: UNKNOWN (weight missing)                          │
│  │                                                           │
│  📍 Approval Requested    2026-09-28 12:25  AI 提交审批         │
│  │                                                           │
│  ⏳ [等待人工决策]                                          │
│  │                                                           │
│  ⬜ Approval Decision      Not yet                            │
│  ⬜ Product Master         Not yet                            │
│  ⬜ Content Generation     Not yet                            │
│  ⬜ Listing Approved       Not yet                            │
│  ⬜ WC Sync                Not yet                            │
│  ⬜ Published              Not yet                            │
└─────────────────────────────────────────────────────────────┘

数据来源: event_log + operation_log + trace_id
如果没有数据: 显示 "Not available" — 不伪造事件
```

---

## 6. Approval Workbench 设计

### 6.1 页面布局

**URL**: `/products/approvals`

```
┌─────────────────────────────────────────────────────────────┐
│  ⏳ 待审批                                                    │
│                                                              │
│  3 件产品等待你的决策                                          │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  1. 户外折叠桌 NT-OUTDOOR-09281224                        ││
│  │                                                           ││
│  │  🤖 AI: REVIEW                                           ││
│  │  Reasons: [利润率 36.7% < 50%, Brand Fit 4.2 < 5.0]     ││
│  │  Risks: [合规风险, 市场风险]                               ││
│  │                                                           ││
│  │  Hard Rules: ❌ FAIL (V8 一票否决)                        ││
│  │  Cost: $28.50 landed → $45.00 suggested                  ││
│  │  Margin: 36.7%                                             ││
│  │  Supply Chain: 履约率 86.4%, 回头率 48%                   ││
│  │                                                           ││
│  │  [批准]  [驳回]  [请求修改]  [查看详情 →]                  ││
│  ├─────────────────────────────────────────────────────────┤│
│  │  2. 便携榨汁杯 NT-JUICER-USB-0928001                      ││
│  │  ...                                                      ││
│  ├─────────────────────────────────────────────────────────┤│
│  │  3. 露营灯 NT-LANTERN-0928002                             ││
│  │  ...                                                      ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  ⚠️ 不允许: Publish to WooCommerce                            │
│  ⚠️ 只能: Approve / Reject / Request Revision                │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 每条审批显示的信息

| 字段 | 来源 | 说明 |
|------|------|------|
| Product | Product.name + sku | 产品基本信息 |
| AI Recommendation | ProductDecision.decision | Recommend / Reject / Review |
| Reasons | ProductDecision.reasons | AI 推荐原因 |
| Risks | ProductDecision.risks | AI 识别的风险 |
| Rule Result | ProductNuotaoScore.reject_reasons | Hard Rules 结果 |
| Cost | ProductCost.total_landed_cost | 落地成本 |
| Margin | ProductCost.contribution_margin | 贡献毛利 |
| Supply Chain | ProductSource + SourcingCandidate | 供应商信息 |
| Next Action | 派生 | Approve / Reject / Request Revision |

### 6.3 主操作

```
[批准]          → 批准候选产品，进入 Product Master 创建流程
[驳回]          → 驳回候选产品，candidate_status = 'rejected'
[请求修改]      → 要求补充数据或修改后重新提交
[查看详情 →]    → 跳转到 Product Decision Cockpit
```

**禁止出现**:
- ❌ Publish to WooCommerce
- ❌ Sync to WC
- ❌ 任何发布相关按钮

---

## 7. Candidate / Master 边界

### 7.1 后端现状

```python
# 当前: 同一 Product 行兼任 Candidate 和 Product Master
class Product:
    status: str                    # 'draft' | 'active' | 'inactive'
    candidate_status: str | None   # 'candidate' | 'approved' | 'winner' | ...
    funnel_stage: str | None       # 'recalled' | 'screened' | ... | 'hero'
```

### 7.2 UI 如何表达边界

```
Candidate 阶段:
┌─────────────────────────────────────────────────────────────┐
│  Product Candidate                                           │
│                                                              │
│  这是一个候选产品，正在等待审批决策。                          │
│                                                              │
│  当前状态: candidate                                          │
│  当前阶段: 待审批                                             │
│                                                              │
│  [提交审批]                                                  │
└─────────────────────────────────────────────────────────────┘

                          ↓ Approved

Product Master 阶段:
┌─────────────────────────────────────────────────────────────┐
│  ✅ Product Master Created                                    │
│                                                              │
│  这是一个已批准的商品主数据。                                  │
│                                                              │
│  Product ID: uuid-xxx                                         │
│  SKU: NT-OUTDOOR-09281224                                    │
│  mastered_at: 2026-09-28 12:31                                │
│                                                              │
│  [生成 B2C Listing]                                          │
└─────────────────────────────────────────────────────────────┘
```

### 7.3 mastered_at 处理

**后端没有 `mastered_at` 字段时**:

```
mastered_at: Not recorded
```

**绝不伪造时间。**

**后端需要新增**:
- `Product.mastered_at: datetime | None` — 在 Approval 通过时设置
- `Product.mastered_by: str | None` — 批准人
- `Product.mastered_trace_id: str | None` — 审批追踪 ID

---

## 8. Listing Gate 设计

### 8.1 完整门控链

```
Product Master (已批准)
    ↓ 可以生成 Listing
B2C Listing (generated)
    ↓ 可以提交审核
Listing Validation
    ↓ 可以批准
Listing Approved
    ↓ 可以同步 WC
WooCommerce Sync
```

### 8.2 每一步的门控条件

| 步骤 | 前置条件 | 动作 | 门控逻辑 |
|------|---------|------|---------|
| Product Master | candidate_status='approved' | 创建 Master | 必须有 Approval |
| B2C Listing | mastered_at 有值 | 生成 Listing | 必须有 Product Master |
| Listing Validation | listing_status='generated' | 提交审核 | 必须有 Listing |
| Listing Approved | listing_validation='passed' | 批准 Listing | 必须通过验证 |
| WC Sync | listing_status='approved' | 同步 WC | 必须有 Listing Approved |

### 8.3 按钮可见性规则

```
Listing 页面:
  if Product Master 不存在:
    显示: "⚠️ 需要先创建 Product Master"
    按钮: [创建 Product Master →]
    隐藏: [生成 Listing]

  elif Listing 未生成:
    显示: Product Master 信息
    按钮: [生成 B2C Listing]
    隐藏: [Sync to WC]

  elif Listing 已生成但未批准:
    显示: Listing 内容
    按钮: [批准 Listing] [修改] [重新生成]
    隐藏: [Sync to WC]

  elif Listing 已批准:
    显示: Listing 内容 + WC 同步状态
    按钮: [同步到 WC] [回读验证]
    显示: WC mapping

WooCommerce 页面:
  if Listing 未批准:
    显示: "⚠️ Listing 未批准，无法同步"
    按钮: [同步到 WC] ← disabled
    显示: [批准 Listing →]
    
  elif Listing 已批准且未同步:
    按钮: [同步到 WC]
    
  elif 已同步:
    按钮: [重新同步] [回读验证] [下架]
```

### 8.4 禁止 force=true

```
UI 层:
  - 不显示 force=true 参数
  - 不提供绕过门控的选项
  
API 层:
  - POST /products/push-woocommerce 必须检查 listing_status='approved'
  - 如果不满足，返回 403 + 明确原因
  - 不允许 force=true 参数绕过
```

---

## 9. WooCommerce Gate 设计

### 9.1 Nuotao Product ↔ WC Product Mapping

```
┌─────────────────────────────────────────────────────────────┐
│  WooCommerce Mapping                                          │
│                                                              │
│  ┌──────────────┐       ┌──────────────┐                    │
│  │ Nuotao Product│       │ WC Product   │                    │
│  │ ID: uuid-xxx │       │ ID: 2196     │                    │
│  │ SKU: NT-...  │       │ Slug: outdoor │                    │
│  │ Status: active│      │ Status: publish│                   │
│  └──────┬───────┘       └──────┬───────┘                    │
│         │                      │                             │
│         └──────────────────────┘                             │
│                  ↕ mapping                                    │
│                                                              │
│  Sync Status: ✅ published                                   │
│  Last Sync: 2026-09-28 12:45                                 │
│  Last Error: None                                            │
│  Retry Count: 0                                              │
│                                                              │
│  [同步到 WC]  [回读验证]  [下架]  [解除映射]                  │
└─────────────────────────────────────────────────────────────┘
```

### 9.2 WC 同步状态机

```
Listing Approved
    ↓
pending          → 工单已创建，等待调度
    ↓
processing       → WC 推送中
    ↓ (成功)
published        → WC 已创建/更新，回读校验通过
    ↓
active           → 前台可见

    ↓ (失败)
failed           → 推送失败
    ↓
processing       → 重试 (最多3次)
    ↓ (超过3次)
failed           → 终态失败，需人工介入
```

### 9.3 回读验证

同步完成后，系统必须:
1. 从 WC 回读产品数据
2. 对比 Nuotao 端数据
3. 验证: 名称、价格、图片、描述是否一致
4. 记录验证结果: `wc_verify_status: 'verified' | 'partial' | 'failed'`

---

## 10. 状态映射表

### 10.1 完整映射

| 用户阶段 | identity | lifecycle (candidate_status) | approval (ProductDecision) | publication (listing_status) | sync (ListingJob) | UI 主状态 | 主动作 |
|---------|----------|------------------------------|---------------------------|------------------------------|-------------------|----------|--------|
| 机会 | — | NULL | — | — | — | 市场机会 | 创建候选 |
| 候选 | — | candidate | — | — | — | 候选产品 | 启动 AI 分析 |
| AI 分析中 | — | candidate | — | — | — | AI 分析中 | 等待 |
| 分析完成 | — | candidate | — | — | — | 分析完成 | 提交审批 |
| 待审批 | — | candidate | pending | — | — | 待审批 | 批准/驳回/修改 |
| 已批准 | — | approved | approved | — | — | 已批准 | 创建 Product Master |
| Product Master | — | winner | approved | — | — | Product Master | 生成 Listing |
| Listing 生成中 | — | winner | approved | generating | — | Listing 生成中 | 等待 |
| Listing 待审 | — | winner | approved | generated | — | Listing 待审 | 批准 Listing |
| Listing 已批准 | — | winner | approved | approved | — | Listing 已批准 | 同步 WC |
| WC 同步中 | — | winner | approved | approved | processing | WC 同步中 | 等待 |
| WC 已发布 | — | winner | approved | approved | published | WC 已发布 | 查看前台 |
| WC 失败 | — | winner | approved | approved | failed | WC 失败 | 重试/修复 |
| 已下架 | — | winner | approved | archived | published | 已下架 | 归档/重上架 |
| 已淘汰 | — | rejected | rejected | — | — | 已淘汰 | 归档 |

### 10.2 重要原则

```
UI 主状态是派生视图 (Derived View)。
不能新建一个数据库字段来替代正交状态轴。

后端保持:
  - Product.status (commerce: draft/active/inactive/pending)
  - Product.candidate_status (candidate/approved/testing/winner/rejected/NULL)
  - Product.funnel_stage (recalled/screened/deep_candidate/test_candidate/testing/hero/rejected/NULL)
  - ProductDecision.approval_status (pending/approved/rejected)
  - ListingJob.status (pending/approved/processing/rejected/published/failed)
  
UI 派生:
  - 用户阶段 = f(candidate_status, funnel_stage, decision, listing, sync)
```

### 10.3 阶段派生逻辑 (Pseudocode)

```python
def derive_user_stage(product, decision, listing_job) -> str:
    # 已淘汰
    if product.candidate_status == 'rejected':
        return 'rejected'
    
    # WC 已发布
    if listing_job and listing_job.status == 'published':
        return 'wc_published'
    
    # WC 失败
    if listing_job and listing_job.status == 'failed':
        return 'wc_failed'
    
    # WC 同步中
    if listing_job and listing_job.status == 'processing':
        return 'wc_syncing'
    
    # Listing 已批准
    if listing_job and listing_job.status == 'approved':
        return 'listing_approved'
    
    # Listing 待审
    if listing_job and listing_job.status == 'pending':
        return 'listing_pending'
    
    # Product Master 已创建
    if product.mastered_at:
        return 'product_master'
    
    # 已批准
    if product.candidate_status == 'approved':
        return 'approved'
    
    # 待审批
    if decision and decision.approval_status == 'pending':
        return 'pending_approval'
    
    # AI 分析完成
    if product.funnel_stage in ('deep_candidate', 'test_candidate'):
        return 'analysis_complete'
    
    # AI 分析中
    if product.funnel_stage in ('recalled', 'screened'):
        return 'analysis_running'
    
    # 候选
    if product.candidate_status == 'candidate':
        return 'candidate'
    
    return 'unknown'
```

---

## 11. 重复页面治理

### 11.1 当前重复页面

| 重复组 | 现有页面 | 保留 | 废弃/Redirect | 合并 |
|--------|---------|------|--------------|------|
| 选品 | Sourcing.tsx | — | 废弃 | — |
| 选品 | NewtonSourcing.tsx | ✅ 保留 | — | — |
| 选品 | MarketOpportunities.tsx | ✅ 保留 | redirect | — |
| 选品 | ProductAnalysis.tsx (导入部分) | 合并到分析页 | redirect | — |
| 分析 | AIAnalysis.tsx | — | 废弃 | — |
| 分析 | ProductAnalysis.tsx | ✅ 保留 | — | — |
| 上架 | ProductPublish.tsx | 重构为 WC | redirect | — |
| 上架 | ListingJobs.tsx | 保留但标记 deprecated | — | — |
| 上架 | Products.tsx (WC同步部分) | 移除 WC 功能 | — | 合并到 WC 页 |
| 工作台 | ProductPipeline.tsx | 保留但 deprecated | — | — |
| 成本 | CostModel.tsx | — | 废弃 | — |
| 成本 | ProductCostsPage.tsx | ✅ 保留 | — | — |

### 11.2 Redirect 映射

```
/products/publish        → /products/opportunities     (301)
/products/listing        → /products/woocommerce       (301)
/products/pipeline       → /products/workbench         (301, 旧工作台)
/sourcing                → /products/newton-sourcing   (301)
/ai-analysis             → /products/analysis           (301)
/cost-model              → /products/costs              (301)
```

### 11.3 用户入口收敛

```
用户只需要记住一个入口: "产品工作台"

产品工作台
  ├── 生命周期看板 → 点击阶段进入筛选视图
  ├── 今日需要处理 → 点击任务进入对应页面
  ├── 所有产品列表 → 点击进入 Product Decision Cockpit
  └── 待审批列表 → 点击产品进入审批流程
```

---

## 12. 导航设计

### 12.1 三层导航

```
1. 左侧导航 (全局)
   商品与 AI 选品
   ├── 📊 产品工作台          ← 入口
   ├── 🤖 AI 选品 (子菜单)
   ├── 📦 商品中心 (子菜单)
   ├── 💰 成本与定价
   └── ⚖️ 规则与审核

2. 页面顶部阶段导航 (产品流程内)
   [机会] → [候选] → [AI分析] → [待审批] → [Product Master] → [Listing] → [WooCommerce]
   ─────   ─────   ──────   ───────   ──────────────   ───────   ──────────────
   当前阶段高亮，可点击跳转

3. 产品详情生命周期导航 (Product Decision Cockpit)
   顶部显示当前阶段 + 状态 + 下一步
   Tab 切换查看各维度
```

### 12.2 任何页面都能:

- **返回产品工作台**: 顶部固定按钮 "← 返回工作台"
- **查看当前阶段**: 顶部阶段导航条
- **查看下一步**: 当前阶段下方显示"下一步主动作"
- **查看产品详情**: 点击产品名称 → Product Decision Cockpit

### 12.3 导航不依赖菜单猜测

```
用户从任何页面都能:
1. 看到自己在哪个阶段 (顶部阶段导航)
2. 知道下一步做什么 (当前阶段下方提示)
3. 返回工作台 (顶部固定按钮)
4. 查看产品详情 (点击产品名称)
5. 查看生命周期时间线 (Product Decision Cockpit Tab)
```

---

## 13. 用户主流程

### 13.1 完整用户旅程

```
1. 用户进入 "产品工作台"
   ↓
2. 看到 "今日需要处理" → 点击 "去审批"
   ↓
3. 进入 "待审批" 页面 → 看到 3 件待审批产品
   ↓
4. 点击第一个产品 → 进入 Product Decision Cockpit
   ↓
5. 查看 Hard Rules tab → 看到 V8 一票否决 (FAIL)
   ↓
6. 查看 Cost tab → 看到利润率 36.7% < 50%
   ↓
7. 查看 AI Analysis tab → 看到 AI 建议 REVIEW
   ↓
8. 查看 Lifecycle Timeline → 了解产品历史
   ↓
9. 决定: [驳回] (因为 Brand Fit 一票否决)
   ↓
10. 填写驳回原因 → 确认
   ↓
11. 返回 "待审批" 页面 → 产品消失
   ↓
12. 进入 "已淘汰" 页面 → 看到驳回产品
   ↓
13. 查看驳回原因 → 确认无误
```

### 13.2 正常上架流程

```
1. 用户进入 "产品工作台"
   ↓
2. 点击 "AI 选品" → "牛顿选品"
   ↓
3. 搜索 "户外折叠桌" → 看到结果
   ↓
4. 选中产品 → "加入候选"
   ↓
5. 进入 "候选产品" 页面 → 看到新候选
   ↓
6. 点击产品 → 进入 Product Decision Cockpit
   ↓
7. 查看 AI Analysis tab → AI 分析已完成
   ↓
8. 查看 Hard Rules tab → 全部 PASS
   ↓
9. 点击 [提交审批] → 进入 "待审批"
   ↓
10. 在 "待审批" 页面看到该产品
    ↓
11. 查看 Cockpit → 确认所有维度
    ↓
12. 点击 [批准] → Product Master Created
    ↓
13. 进入 "Product Master" tab → 看到 mastered_at
    ↓
14. 点击 [生成 B2C Listing] → Listing 生成中
    ↓
15. Listing 生成完成 → 查看 Listing tab
    ↓
16. 审核 Listing 内容 → 点击 [批准 Listing]
    ↓
17. Listing 已批准 → 进入 "WooCommerce" tab
    ↓
18. 点击 [同步到 WC] → WC 同步中
    ↓
19. 同步完成 → 看到 WC Product ID
    ↓
20. 点击 [回读验证] → 验证通过
    ↓
21. 点击前台链接 → 确认产品已发布
```

---

## 14. 页面→API 映射需求

### 14.1 Product Workbench

| UI 元素 | API | 状态 |
|---------|-----|------|
| 生命周期看板统计 | GET /products/workbench/summary | ❌ 缺失 |
| 今日需要处理 | GET /products/workbench/tasks | ❌ 缺失 |
| 阶段筛选列表 | GET /products?stage=xxx | ❌ 需改造 |

### 14.2 Product Decision Cockpit

| UI 元素 | API | 状态 |
|---------|-----|------|
| Product Facts | GET /products/:id | ✅ 已有 |
| Market Analysis | GET /products/:id/intelligence | ✅ 已有 |
| AI Analysis | GET /products/:id/intelligence | ✅ 已有 |
| Cost / Profit | GET /products/:id/cost-snapshots | ✅ 已有 |
| Supply Chain | GET /products/:id/sources | ✅ 已有 |
| Hard Rules | GET /products/:id/rule-results | ❌ 缺失 |
| Approval | GET /products/:id/decision | ✅ 已有 |
| Product Master | GET /products/:id | ✅ 已有 (需 mastered_at) |
| B2C Listing | GET /products/:id/listing | ❌ 缺失 |
| WooCommerce | GET /products/:id/wc-status | ❌ 缺失 |
| Lifecycle Timeline | GET /products/:id/timeline | ❌ 缺失 |

### 14.3 Approval Workbench

| UI 元素 | API | 状态 |
|---------|-----|------|
| 待审批列表 | GET /product-decisions?status=pending | ✅ 已有 |
| 批量审批 | POST /product-decisions/:id/approve | ✅ 已有 |
| 批量驳回 | POST /product-decisions/:id/reject | ✅ 已有 |

### 14.4 B2C Listing

| UI 元素 | API | 状态 |
|---------|-----|------|
| 生成 Listing | POST /products/:id/listing/generate | ❌ 缺失 |
| 查看 Listing | GET /products/:id/listing | ❌ 缺失 |
| 批准 Listing | POST /products/:id/listing/approve | ❌ 缺失 |
| 修改 Listing | PUT /products/:id/listing | ❌ 缺失 |

### 14.5 WooCommerce

| UI 元素 | API | 状态 |
|---------|-----|------|
| 同步 WC | POST /products/push-woocommerce | ✅ 已有 (需门控) |
| WC 状态 | GET /products/:id/wc-status | ❌ 缺失 |
| 回读验证 | POST /products/:id/wc-verify | ❌ 缺失 |
| 解除映射 | DELETE /products/:id/wc-mapping | ❌ 缺失 |

---

## 15. 尚缺少的 Backend 能力

### 15.1 必须新增

| # | 能力 | 说明 | 优先级 |
|---|------|------|--------|
| 1 | Product.mastered_at | Product Master 创建时间 | **P0** |
| 2 | Product.mastered_by | Product Master 批准人 | **P0** |
| 3 | Product.mastered_trace_id | 审批追踪 ID | **P1** |
| 4 | GET /products/:id/rule-results | Hard Rules 评估结果详情 | **P0** |
| 5 | GET /products/:id/timeline | 产品生命周期时间线 | **P1** |
| 6 | POST /products/:id/listing/generate | 生成 B2C Listing | **P0** |
| 7 | GET /products/:id/listing | 查看 Listing 内容 | **P0** |
| 8 | POST /products/:id/listing/approve | 批准 Listing | **P0** |
| 9 | GET /products/:id/wc-status | WC 同步状态 | **P0** |
| 10 | POST /products/:id/wc-verify | WC 回读验证 | **P1** |
| 11 | GET /products/workbench/summary | 工作台看板数据 | **P0** |
| 12 | GET /products/workbench/tasks | 工作台任务列表 | **P0** |

### 15.2 必须改造

| # | 能力 | 当前 | 改造需求 | 优先级 |
|---|------|------|---------|--------|
| 1 | push-woocommerce | 直接推送 | 必须检查 listing_status='approved' | **P0** |
| 2 | Product 列表 | 只按 status 筛选 | 增加 stage 派生筛选 | **P1** |
| 3 | ProductDecision | 只有 decision | 增加 rejection_reasons 详情 | **P1** |

### 15.3 已有的可复用

| # | 能力 | API | 状态 |
|---|------|-----|------|
| 1 | Product CRUD | /products | ✅ |
| 2 | Product Intelligence | /products/:id/intelligence | ✅ |
| 3 | Cost Snapshots | /products/:id/cost-snapshots | ✅ |
| 4 | Product Sources | /products/:id/sources | ✅ |
| 5 | Product Decision | /product-decisions | ✅ |
| 6 | Approval | /product-decisions/:id/approve | ✅ |
| 7 | Nuotao Score | /selection/nuotao/evaluate | ✅ |
| 8 | Pipeline | /product-pipeline | ✅ (但 deprecated) |
| 9 | ListingJob | /listing-jobs | ✅ |
| 10 | WC Sync | /products/sync-woocommerce | ✅ |
| 11 | WC Push | /products/push-woocommerce | ✅ (需门控) |

---

## 16. 分阶段实施计划

### Phase 2A: Information Architecture (当前)
```
✅ 本文件 — 设计方案
输出: docs/design/PRODUCT_AI_SELECTION_UX_ARCHITECTURE.md
```

### Phase 2B: Product Workbench
```
Implement:
  - 新增 /products/workbench 页面
  - 生命周期看板组件
  - "今日需要处理"任务列表
  - 阶段筛选视图

API:
  - 新增 GET /products/workbench/summary
  - 新增 GET /products/workbench/tasks

Test:
  - 看板数据统计正确
  - 任务列表显示正确
  - 阶段筛选正确
  - 跳转正确

Browser Verify:
  - 访问 /products/workbench
  - 验证看板显示
  - 验证任务列表
  - 验证跳转

Review:
  - 代码审查
  - 设计一致性审查
```

### Phase 2C: Decision Cockpit
```
Implement:
  - 重构 /products/:id 为 Product Decision Cockpit
  - 11 个 Tab 组件
  - 顶部阶段导航
  - 下一步指引

API:
  - 新增 Product.mastered_at 字段 + migration
  - 新增 GET /products/:id/rule-results
  - 新增 GET /products/:id/timeline

Test:
  - 每个 Tab 正确加载
  - 阶段导航正确
  - 下一步指引正确
  - Hard Rules 显示正确

Browser Verify:
  - 访问产品详情
  - 验证所有 Tab
  - 验证阶段导航
  - 验证下一步指引

Review:
  - 代码审查
  - 设计一致性审查
```

### Phase 2D: Approval Workbench
```
Implement:
  - 新增 /products/approvals 页面
  - 审批卡片组件
  - 批量操作

API:
  - 复用 /product-decisions (已有)
  - 增加 rejection_reasons 字段

Test:
  - 待审批列表正确
  - 批准/驳回正确
  - 批量操作正确

Browser Verify:
  - 访问 /products/approvals
  - 验证列表
  - 验证审批操作

Review:
  - 代码审查
  - 设计一致性审查
```

### Phase 2E: B2C Listing
```
Implement:
  - 新增 /products/listing 页面
  - Listing 生成/查看/批准
  - Listing 内容编辑器

API:
  - 新增 B2C Listing 模型 + migration
  - 新增 POST /products/:id/listing/generate
  - 新增 GET /products/:id/listing
  - 新增 POST /products/:id/listing/approve

Test:
  - Listing 生成正确
  - Listing 显示正确
  - Listing 批准正确
  - 门控正确 (Product Master 不存在时禁止生成)

Browser Verify:
  - 访问 Listing 页面
  - 验证生成/查看/批准
  - 验证门控

Review:
  - 代码审查
  - 设计一致性审查
```

### Phase 2F: WooCommerce Gate
```
Implement:
  - 重构 /products/woocommerce 页面
  - WC 同步门控
  - Nuotao ↔ WC mapping 显示
  - 回读验证

API:
  - 改造 push-woocommerce 增加门控检查
  - 新增 GET /products/:id/wc-status
  - 新增 POST /products/:id/wc-verify
  - 新增 DELETE /products/:id/wc-mapping

Test:
  - 门控正确 (Listing 未批准时禁止同步)
  - 同步正确
  - 回读验证正确
  - 门控绕过被阻止

Browser Verify:
  - 访问 WC 页面
  - 验证门控
  - 验证同步
  - 验证回读

Review:
  - 代码审查
  - 安全审查 (force=true 绕过)
  - 设计一致性审查
```

---

## 17. 最终检查清单

### 17.1 设计一致性

- [ ] UI 主状态是派生视图，不新增 backend status
- [ ] Candidate 和 Product Master 有明确分界
- [ ] mastered_at 不存在时不伪造
- [ ] 每个阶段只有一个主动作
- [ ] 不允许 force=true 绕过门控
- [ ] AI Recommendation 和 Human Decision 明确区分
- [ ] Hard Rules 明显区别于 AI Score
- [ ] UNKNOWN 不写成 0，不自动 PASS
- [ ] 页面不产生假成功
- [ ] 不创建 fake API

### 17.2 用户能回答

- [ ] "我现在在哪里？" → 顶部阶段导航
- [ ] "这个产品是什么状态？" → 当前状态卡片
- [ ] "为什么是这个状态？" → Lifecycle Timeline
- [ ] "我下一步应该做什么？" → 下一步指引

### 17.3 安全

- [ ] 所有审批操作遵循 RBAC
- [ ] 所有发布操作遵循 Workspace 隔离
- [ ] 所有 WC 同步操作有门控
- [ ] 不绕过认证/RBAC/Workspace/Approval

---

## 附录: 与现有 ADR 的一致性

| ADR | 一致性检查 |
|-----|-----------|
| COMMERCE-001 | ✅ 共享底座 + 业务分流。Product Master 是共享底座，B2C Listing 是 B2C 分流 |
| AGENTS-001 | ✅ Agent 按业务边界分层。Product Agent 按 B2C/B2B/SHARED 范围隔离 |
| IDENTITY-001 | ✅ 生产可信身份。所有审批操作必须经 JWT 验证的 actor |
| PRICING-001 | ✅ 价格版本化。B2C Listing 价格基于 Product Master 成本，不硬编码 |

---

## 附录: 文件索引

### 本阶段输出
- `docs/design/PRODUCT_AI_SELECTION_UX_ARCHITECTURE.md` — 本文档

### 引用文档
- `docs/audits/PRODUCT_AI_SELECTION_UX_AUDIT.md` — Phase 1 审计
- `docs/business_decisions/ADR/COMMERCE-001.md`
- `docs/business_decisions/ADR/AGENTS-001.md`
- `docs/business_decisions/ADR/IDENTITY-001.md`
- `docs/business_decisions/ADR/PRICING-001.md`

### 相关代码
- `frontend/src/config/navigation.tsx` — 导航配置
- `frontend/src/app/AppRoutes.tsx` — 路由配置
- `frontend/src/pages/*.tsx` — 现有页面
- `backend/app/models/product.py` — Product 模型
- `backend/app/models/product_intelligence.py` — 智能模型
- `backend/app/models/listing_job.py` — 工单模型
- `backend/app/services/product_pipeline_service.py` — Pipeline 服务
