/**
 * 产品生命周期阶段的唯一来源（ADR IDENTITY-002）。
 *
 * 两个正交模型，都在此定义，禁止在其他文件重复：
 *
 * 1. `LIFECYCLE_STAGES` — 业务生命周期 12 阶段，驱动侧边栏 IA 与产品时间线。
 * 2. `PIPELINE_STEPS` — 单次管线运行的技术执行步骤，仅用于「产品工作流」运行工具。
 *    它标注了每步对应的生命周期阶段，但**不是**生命周期阶段本身：一次管线运行
 *    覆盖候选、分析、内容、上架四段，与 12 阶段并非一一对应。
 *
 * 约束（ADR IDENTITY-002）：
 * - 阶段定义只允许在此定义，禁止页面内硬编码步骤数组。
 * - `backend: 'missing' | 'partial'` 的阶段必须渲染显式契约态，禁止 mock 数据。
 */

// ---------------------------------------------------------------------------
// 生命周期道
// ---------------------------------------------------------------------------

export type Lane = 'opportunity' | 'review' | 'decision' | 'launch' | 'growth'

export type BackendState = 'ready' | 'partial' | 'missing'

export interface LaneDef {
  id: Lane
  label: string
  /** 属于该道的阶段序号 */
  stages: readonly number[]
}

export const LANES: readonly LaneDef[] = [
  { id: 'opportunity', label: '机会', stages: [1, 2] },
  { id: 'review', label: '候选评估', stages: [3, 4, 5, 6, 7] },
  { id: 'decision', label: '决策', stages: [8, 9] },
  { id: 'launch', label: '内容与发布', stages: [10, 11] },
  { id: 'growth', label: '经营回流', stages: [12] },
]

// ---------------------------------------------------------------------------
// 12 个生命周期阶段
// ---------------------------------------------------------------------------

export interface LifecycleStage {
  /** 稳定 id，用于组件 key、URL 片段、埋点 */
  id: string
  /** 阶段序号 1-12 */
  n: number
  lane: Lane
  label: string
  /** 一句话职责 */
  description: string
  /** 后端能力就绪度 */
  backend: BackendState
  /** 对应的现有前端菜单 key（可能为空 = 无页面） */
  pages: readonly string[]
  /** backend 为 missing/partial 时展示的期望契约，用于「后端未接入」契约态 */
  contract?: {
    model?: string
    endpoints?: readonly string[]
    gap: string
  }
}

export const LIFECYCLE_STAGES: readonly LifecycleStage[] = [
  {
    id: 'market_intel',
    n: 1,
    lane: 'opportunity',
    label: '市场情报',
    description: '市场信号采集：搜索趋势、竞品价格、评论痛点、社媒讨论',
    backend: 'partial',
    pages: [],
    contract: {
      endpoints: ['/api/v1/market-trend/*', '/api/v1/competitor-analysis/*'],
      gap: '信号产出仍无独立采集流水线；但阶段② Opportunity 已作为一等实体落地，可人工沉淀与引用。',
    },
  },
  {
    id: 'opportunity',
    n: 2,
    lane: 'opportunity',
    label: '机会池',
    description: '将市场信号聚合为可查询、可引用、可追溯的机会实体',
    backend: 'ready',
    pages: ['opportunity'],
  },
  {
    id: 'candidate',
    n: 3,
    lane: 'review',
    label: '产品候选',
    description: '从 1688 / 供应商 / 手工录入建立候选，尚未成为正式产品',
    backend: 'ready',
    pages: ['sourcing', 'newton-sourcing'],
  },
  {
    id: 'analysis',
    n: 4,
    lane: 'review',
    label: 'AI 分析',
    description: 'Product Analyst 综合市场、产品、成本、竞争、供应链、风险、B2C/B2B',
    backend: 'ready',
    pages: ['product-analysis', 'product-pipeline'],
  },
  {
    id: 'cost_profit',
    n: 5,
    lane: 'review',
    label: '成本利润',
    description: 'Landed Cost 建模、毛利/贡献边际/ROI/运费占比/退货风险',
    backend: 'ready',
    pages: ['cost'],
  },
  {
    id: 'risk_supply',
    n: 6,
    lane: 'review',
    label: '风险供应链',
    description: 'Hard Rules（V1–V12）+ 供应商 MOQ/交期/产能/合规',
    backend: 'partial',
    pages: ['suppliers'],
    contract: {
      endpoints: ['/api/v1/suppliers'],
      gap: '供应商数据后端就绪；发布前闸门 6 条规则已接入主后端（listing_gate.py），但 V1–V12 完整规则集从未在任何已应用代码中实现。',
    },
  },
  {
    id: 'channel_eval',
    n: 7,
    lane: 'review',
    label: 'B2C/B2B 评估',
    description: '同一候选评估 B2C 零售与 B2B 批发两种销售模式可行性',
    backend: 'partial',
    pages: ['b2b'],
    contract: {
      endpoints: ['/api/v1/selection/recommendations'],
      gap: 'B2B 侧后端就绪；B2C/B2B 双通道并列评估的前端视图未建立。',
    },
  },
  {
    id: 'decision',
    n: 8,
    lane: 'decision',
    label: 'AI 决策 + 人审',
    description: 'Decision Engine 输出建议，人工通过 / 拒绝（后端无「请求修改」端点）',
    backend: 'ready',
    pages: ['decision-queue'],
  },
  {
    id: 'master',
    n: 9,
    lane: 'decision',
    label: 'Product Master',
    description: '批准后成为系统正式商品；此后才有内容生成与发布',
    backend: 'partial',
    pages: ['products'],
    contract: {
      model: 'Product',
      endpoints: ['/api/v1/products'],
      gap: '单表 products + candidate_status 列已承担该职责，但无可审计的转正时间标记（mastered_at）。Product Master 不建新表、不建新枚举。',
    },
  },
  {
    id: 'content',
    n: 10,
    lane: 'launch',
    label: 'AI 内容',
    description: '基于已验证产品事实生成标题/描述/卖点/SEO，经校验与合规',
    backend: 'ready',
    pages: ['product-listing', 'content', 'listing-localization', 'seo'],
  },
  {
    id: 'wc_sync',
    n: 11,
    lane: 'launch',
    label: 'WC 同步',
    description: '推 WooCommerce 并回写 woocommerce_id 映射（发布前闸门已接入）',
    backend: 'partial',
    pages: ['products'],
    contract: {
      endpoints: ['/api/v1/products'],
      gap: '闸门 6 条发布前规则已接入：缺失 SKU / 缺失定价 / 未过审 / 硬阻断（缺 SKU、无英文本地化）不可 force，needs_review 可 force。仅完整 V1–V12 供应链规则集仍未实现。',
    },
  },
  {
    id: 'growth_loop',
    n: 12,
    lane: 'growth',
    label: '经营回流',
    description: '销售数据 → 事件 → 学习 → 校准，回流影响下一轮选品',
    backend: 'partial',
    pages: ['events'],
    contract: {
      model: 'Event',
      endpoints: ['/api/v1/events', '/api/v1/weekly-report'],
      gap: '后端 event.py 模型、feedback_loop.py、WC 订单同步均已存在；Events.tsx 无 API 调用，「上一轮表现 → 下一轮选品」的学习闭环未在前端实证。',
    },
  },
]

// ---------------------------------------------------------------------------
// 查询辅助
// ---------------------------------------------------------------------------

export const STAGE_BY_ID: ReadonlyMap<string, LifecycleStage> = new Map(
  LIFECYCLE_STAGES.map((s) => [s.id, s]),
)

export const STAGES_OF_LANE = (lane: Lane): readonly LifecycleStage[] =>
  LIFECYCLE_STAGES.filter((s) => s.lane === lane)

/** backend 非 ready 的阶段，用于「后端未接入」契约态渲染 */
export const STAGES_WITH_GAP: readonly LifecycleStage[] = LIFECYCLE_STAGES.filter(
  (s) => s.backend !== 'ready' && s.contract,
)

// ---------------------------------------------------------------------------
// 单次管线执行步骤（ProductPipeline 运行工具用）
// ---------------------------------------------------------------------------

export interface PipelineStep {
  /** 与后端 product-pipeline 返回的 step id 对齐，禁止改动 */
  id: string
  title: string
  description: string
  /** 该步骤服务的生命周期阶段 id */
  stageId: string
}

export const PIPELINE_STEPS: readonly PipelineStep[] = [
  {
    id: 'input',
    title: '商品信息',
    description: '输入或导入商品信息',
    stageId: 'candidate',
  },
  {
    id: 'analysis',
    title: 'AI 产品分析',
    description: '10 字段识别 + 17 字段报告',
    stageId: 'analysis',
  },
  {
    id: 'main_image',
    title: '主图生产',
    description: '3 套方向 + 文案 + 变体',
    stageId: 'content',
  },
  {
    id: 'prompt',
    title: '生图 Prompt',
    description: '主图 + 详情页 Prompt',
    stageId: 'content',
  },
  {
    id: 'listing_data',
    title: '上架数据',
    description: '名称 / 描述 / 价格 / SKU',
    stageId: 'content',
  },
  {
    id: 'listing',
    title: '上架 WC',
    description: '人工确认后上架',
    stageId: 'wc_sync',
  },
]
