import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Divider,
  Drawer,
  Empty,
  Form,
  Input,
  message,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import type { TableProps } from 'antd'
import {
  ArrowRightOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  DollarOutlined,
  DatabaseOutlined,
  ExclamationCircleOutlined,
  EyeOutlined,
  FileTextOutlined,
  FilterOutlined,
  ImportOutlined,
  LinkOutlined,
  ReloadOutlined,
  RocketOutlined,
  RobotOutlined,
  SearchOutlined,
  ShopOutlined,
  StarOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import ProductTimeline from '../components/lifecycle/ProductTimeline'
import { STAGE_BY_ID } from '../lifecycle/stages'
import { api } from '../api/client'

const { Title, Text, Paragraph } = Typography

// ---------------------------------------------------------------------------
// 数据契约（与后端 app/schemas/product.py::ProductOut 对齐）
//
// 候选 = products 表中 candidate_status != null 的行。
// 后端 GET /api/v1/products 不支持 candidate_status 过滤，因此本页面拉取
// 最近一页（limit=500，接口上限）后在前端做 candidate_status 判定。
//
// 注意：woocommerce_id 不在顶层，权威位置是 meta.woocommerce_id
// （app/services/listing_publish.py），顶层仅为旧数据兼容。
// ---------------------------------------------------------------------------

interface CandidateProduct {
  id: string
  workspace_id?: string
  sku: string
  name: string
  description?: string | null
  category?: string | null
  brand?: string | null
  status: string
  /** 候选生命周期状态；null = 下游渠道商品（如 WC 反向同步），不在候选漏斗内 */
  candidate_status?: string | null
  source: string
  source_url?: string | null
  tags?: Array<string | number | Record<string, unknown>>
  attributes?: Record<string, unknown>
  /** JSON 列：cost_price / suggested_price / woocommerce_id / listing_data_snapshot */
  meta?: Record<string, unknown> | null
  weight_kg?: number | null
  dimensions?: Record<string, unknown> | null
  target_market?: string
  created_at: string
  updated_at?: string
  /** 旧数据/legacy 兼容字段（ProductOut 不含，见 Products.tsx） */
  supplier_code?: string
  stock_quantity?: number
  woocommerce_id?: number
}

const toNum = (v: unknown): number | undefined => {
  if (v === null || v === undefined || v === '') return undefined
  const n = Number(v)
  return Number.isFinite(n) ? n : undefined
}

/** WC 产品 ID 兼容读取：顶层优先（旧数据），回退 meta.woocommerce_id */
const wcIdOf = (p: CandidateProduct): number | undefined => {
  const top = toNum((p as { woocommerce_id?: unknown }).woocommerce_id)
  if (top !== undefined) return top
  return toNum(p.meta?.woocommerce_id)
}

const costPriceOf = (p: CandidateProduct): number | undefined => toNum(p.meta?.cost_price)
const suggestedPriceOf = (p: CandidateProduct): number | undefined => toNum(p.meta?.suggested_price)

const fmtCny = (v: number | undefined): string => (v === undefined ? '-' : `¥${v.toFixed(2)}`)
const fmtUsd = (v: number | undefined): string => (v === undefined ? '-' : `$${v.toFixed(2)}`)
const fmtDate = (v: string | null | undefined): string =>
  v ? new Date(v).toLocaleString() : '-'

const numVal = (v: unknown, digits = 2): string => {
  const n = toNum(v)
  return n === undefined ? '-' : n.toFixed(digits)
}

/** 渲染 meta 内未知类型的字段值，避免 unknown 直接作为 ReactNode */
const renderMetaVal = (v: unknown) =>
  v === undefined || v === null || v === '' ? (
    <Text type="secondary">空</Text>
  ) : (
    <span>{String(v)}</span>
  )

// candidate_status 展示映射（业务状态枚举，非生命周期阶段定义；阶段定义只在 lifecycle/stages）
const CANDIDATE_STATUS_META: Record<string, { label: string; color: string }> = {
  candidate: { label: '候选中', color: 'orange' },
  approved: { label: '已批准', color: 'green' },
  testing: { label: '测试中', color: 'blue' },
  winner: { label: '已胜出', color: 'purple' },
  rejected: { label: '已拒绝', color: 'red' },
}

const candidateStatusMeta = (v: string | null | undefined) =>
  (v && CANDIDATE_STATUS_META[v]) || { label: v || '未标注', color: 'default' }

const MASTER_STATUS_TEXT: Record<string, string> = {
  active: '已转正',
  draft: '草稿',
  inactive: '已停用',
  listed: '已上架',
  pending: '待处理',
}

const SOURCE_COLORS: Record<string, string> = {
  '1688': 'orange',
  ai_pipeline: 'purple',
  newton: 'geekblue',
  newton_sourcing: 'geekblue',
  manual: 'blue',
  woocommerce: 'cyan',
  csv: 'green',
}

// ---------------------------------------------------------------------------
// AI 分析结果展示配置（字段表与 ProductAnalysis.tsx 保持一致，仅为展示标签）
// ---------------------------------------------------------------------------

interface AiField {
  key: string
  label: string
  span?: number
  isArray?: boolean
  isTextarea?: boolean
}

const AI_RECOGNITION_FIELDS: AiField[] = [
  { key: 'brand_name', label: '品牌名称/Logo' },
  { key: 'product_category', label: '产品类目' },
  { key: 'product_appearance', label: '产品外观' },
  { key: 'material_texture', label: '材质质感' },
  { key: 'core_selling_points', label: '核心卖点', isArray: true, span: 2 },
  { key: 'usage_scenarios', label: '适用场景', isArray: true, span: 2 },
  { key: 'target_audience', label: '目标人群' },
  { key: 'visual_style', label: '视觉风格' },
  { key: 'primary_colors', label: '主色调', isArray: true },
  { key: 'extendable_page_types', label: '可延展页面', isArray: true, span: 2 },
]

const PRODUCT_REPORT_FIELDS: AiField[] = [
  { key: 'brand_name', label: '品牌名称', span: 2 },
  { key: 'product_name', label: '产品名称', span: 2 },
  { key: 'product_category', label: '产品类别' },
  { key: 'product_dimensions', label: '产品尺寸' },
  { key: 'material_craft', label: '材质工艺', span: 2 },
  { key: 'product_color', label: '产品颜色' },
  { key: 'product_capacity', label: '产品容量/规格' },
  { key: 'applicable_target', label: '适用对象', span: 2 },
  { key: 'core_selling_points', label: '核心卖点', isArray: true, span: 2 },
  { key: 'product_features', label: '产品功能', isArray: true, span: 2 },
  { key: 'target_audience', label: '目标人群', span: 2 },
  { key: 'usage_scenarios', label: '使用场景', isArray: true, span: 2 },
  { key: 'visual_style', label: '视觉风格' },
  { key: 'primary_colors', label: '主色调', isArray: true },
  { key: 'extendable_pages', label: '可延展页面', isArray: true, span: 2 },
  { key: 'product_description', label: '产品详细描述', span: 2, isTextarea: true },
  { key: 'quality_assurance', label: '品质保障', span: 2, isTextarea: true },
]

const renderArrayField = (value: unknown) => {
  if (Array.isArray(value)) {
    if (value.length === 0) return <Text type="secondary">-</Text>
    return (
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
        {value.map((v, i) => (
          <Tag key={i} color="blue" style={{ margin: 0 }}>
            {String(v)}
          </Tag>
        ))}
      </div>
    )
  }
  if (value === null || value === undefined || value === '') return <Text type="secondary">-</Text>
  return <span>{String(value)}</span>
}

const renderFieldCell = (field: AiField, data: Record<string, any> | null) => {
  if (!data) return <Text type="secondary">-</Text>
  const v = data[field.key]
  if (field.isArray) return renderArrayField(v)
  if (field.isTextarea) return v ? <Paragraph style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{String(v)}</Paragraph> : <Text type="secondary">-</Text>
  if (v === null || v === undefined || v === '') return <Text type="secondary">-</Text>
  return <span>{String(v)}</span>
}

const PROFIT_STATUS_TEXT: Record<string, string> = {
  healthy: '健康（≥30%）',
  acceptable: '可接受（15–30%）',
  low: '偏低（<15%）',
  loss: '亏损',
}

// ---------------------------------------------------------------------------
// 组件
// ---------------------------------------------------------------------------

type CostTabState =
  | { mode: 'idle' }
  | { mode: 'loading' }
  | { mode: 'error'; message: string }
  | { mode: 'contract'; missing: string[] }
  | { mode: 'done'; result: Record<string, any>; config: Record<string, any> | null }

const PAGE_LIMIT = 500 // GET /api/v1/products 单页上限

export default function CandidatePool() {
  const candidateStage = STAGE_BY_ID.get('candidate')

  // ---- 列表状态 ----
  const [products, setProducts] = useState<CandidateProduct[]>([])
  const [loading, setLoading] = useState(false)
  const [listError, setListError] = useState<string | null>(null)

  const [searchText, setSearchText] = useState('')
  const [candidateStatusFilter, setCandidateStatusFilter] = useState('all')
  const [sourceFilter, setSourceFilter] = useState('all')
  const [categoryFilter, setCategoryFilter] = useState('all')

  // ---- 详情抽屉 ----
  const [detailOpen, setDetailOpen] = useState(false)
  const [current, setCurrent] = useState<CandidateProduct | null>(null)

  // ---- 1688 导入 ----
  const [importOpen, setImportOpen] = useState(false)
  const [importLoading, setImportLoading] = useState(false)
  const [importForm] = Form.useForm<{ url_or_id: string }>()

  // ---- AI 分析 Tab ----
  const [aiLoading, setAiLoading] = useState(false)
  const [aiError, setAiError] = useState<string | null>(null)
  const [aiRecognition, setAiRecognition] = useState<Record<string, any> | null>(null)
  const [productReport, setProductReport] = useState<Record<string, any> | null>(null)

  // ---- 成本利润 Tab ----
  const [costState, setCostState] = useState<CostTabState>({ mode: 'idle' })
  
  // ---- 自动预填成本状态 ----
  const [autoPrefillState, setAutoPrefillState] = useState<{
    loading: boolean
    result: Record<string, any> | null
    error: string | null
  }>({ loading: false, result: null, error: null })
  
  // ---- 归档池状态 (新API) ----
  const [archiveProducts, setArchiveProducts] = useState<any[]>([])
  const [archiveLoading, setArchiveLoading] = useState(false)

  // 加载归档商品列表
  const loadArchiveProducts = useCallback(async () => {
    try {
      setArchiveLoading(true)
      const data = await api.getArchiveList(100)
      if (data.success && data.data) {
        setArchiveProducts(data.data.products || [])
      }
    } catch (e: any) {
      console.error('Load archive products error:', e)
    } finally {
      setArchiveLoading(false)
    }
  }, [])

  useEffect(() => {
    loadArchiveProducts()
  }, [loadArchiveProducts])

  // -----------------------------------------------------------------------
  // 加载候选列表（真实端点：GET /api/v1/products）
  // -----------------------------------------------------------------------
  const loadCandidates = useCallback(async () => {
    setLoading(true)
    setListError(null)
    try {
      const params = new URLSearchParams()
      params.set('limit', String(PAGE_LIMIT))
      params.set('offset', '0')
      if (categoryFilter !== 'all') params.set('category', categoryFilter)

      const resp = await fetch(`/api/v1/products?${params.toString()}`)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)

      const body = await resp.json()
      const rows: CandidateProduct[] = Array.isArray(body) ? body : []
      setProducts(rows)
    } catch (e: any) {
      setProducts([])
      setListError(e?.message || '网络错误')
      message.error(`加载候选列表失败：${e?.message || '网络错误'}`)
    } finally {
      setLoading(false)
    }
  }, [categoryFilter])

  useEffect(() => {
    loadCandidates()
  }, [loadCandidates])

  // 切换候选商品时重置两个动态 Tab 的状态
  useEffect(() => {
    setAiRecognition(null)
    setProductReport(null)
    setAiError(null)
    setAiLoading(false)
    setCostState({ mode: 'idle' })
  }, [current?.id])

  // -----------------------------------------------------------------------
  // 派生数据
  // -----------------------------------------------------------------------
  const candidates = useMemo(
    () => products.filter((p) => p.candidate_status !== null && p.candidate_status !== undefined),
    [products],
  )

  const statusCounts = useMemo(() => {
    const m: Record<string, number> = {}
    for (const p of candidates) m[p.candidate_status as string] = (m[p.candidate_status as string] || 0) + 1
    return m
  }, [candidates])

  const candidateStatusOptions = useMemo(() => {
    const set = new Set<string>()
    for (const p of candidates) if (p.candidate_status) set.add(p.candidate_status)
    return [
      { value: 'all', label: '全部候选状态' },
      ...Array.from(set).map((v) => ({ value: v, label: `${candidateStatusMeta(v).label}（${v}）` })),
    ]
  }, [candidates])

  const sourceOptions = useMemo(() => {
    const set = new Set<string>()
    for (const p of candidates) if (p.source) set.add(p.source)
    return [{ value: 'all', label: '全部来源' }, ...Array.from(set).map((v) => ({ value: v, label: v }))]
  }, [candidates])

  const categoryOptions = useMemo(() => {
    const set = new Set<string>()
    for (const p of products) if (p.category) set.add(p.category)
    return [{ value: 'all', label: '全部分类' }, ...Array.from(set).map((v) => ({ value: v, label: v }))]
  }, [products])

  const filtered = useMemo(() => {
    const kw = searchText.trim().toLowerCase()
    return candidates.filter((p) => {
      if (kw && !`${p.name} ${p.sku}`.toLowerCase().includes(kw)) return false
      if (candidateStatusFilter !== 'all' && p.candidate_status !== candidateStatusFilter) return false
      if (sourceFilter !== 'all' && p.source !== sourceFilter) return false
      return true
    })
  }, [candidates, searchText, candidateStatusFilter, sourceFilter])

  // -----------------------------------------------------------------------
  // 1688 导入（真实端点：POST /api/v1/product-pipeline/import-from-1688）
  // -----------------------------------------------------------------------
  const openImport = () => {
    importForm.resetFields()
    setImportOpen(true)
  }

  const handleImport1688 = async () => {
    let values: { url_or_id: string }
    try {
      values = await importForm.validateFields()
    } catch {
      return // 表单校验失败
    }
    const urlOrId = (values.url_or_id || '').trim()
    if (!urlOrId) {
      message.error('请输入 1688 商品 URL 或商品 ID')
      return
    }

    setImportLoading(true)
    try {
      const resp = await fetch('/api/v1/product-pipeline/import-from-1688', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url_or_id: urlOrId,
          auto_run_pipeline: false,
          auto_list: false,
        }),
      })
      const data = await resp.json().catch(() => null)
      if (resp.ok && data?.success && data.data?.product_info) {
        const info = data.data.product_info
        message.success(`已导入候选：${info.name || '未知商品'}（product_id: ${data.data.product_id || '未返回'}）`)
        setImportOpen(false)
        importForm.resetFields()
        loadCandidates()
      } else {
        const msg = data?.error || data?.detail || `HTTP ${resp.status}`
        message.error(`导入失败：${msg}`)
      }
    } catch (e: any) {
      message.error(`导入失败：${e?.message || '网络错误'}`)
    } finally {
      setImportLoading(false)
    }
  }

  // -----------------------------------------------------------------------
  // 详情抽屉
  // -----------------------------------------------------------------------
  const openDetail = (p: CandidateProduct) => {
    setCurrent(p)
    setDetailOpen(true)
  }

  // ---- AI 分析：POST /api/v1/product-analysis/analyze-and-report ----
  const runAiAnalysis = async (p: CandidateProduct) => {
    setAiLoading(true)
    setAiError(null)
    setAiRecognition(null)
    setProductReport(null)

    const meta = p.meta ?? {}
    const snap = (meta.listing_data_snapshot ?? {}) as Record<string, any>
    const imagesRaw = Array.isArray(meta.images)
      ? meta.images
      : typeof snap.images === 'string'
        ? snap.images
        : Array.isArray(snap.images)
          ? snap.images
          : []

    const productInfo = {
      name: p.name,
      description: p.description ?? '',
      price: costPriceOf(p) !== undefined ? `¥${costPriceOf(p)}` : '',
      category: p.category ?? '',
      images: Array.isArray(imagesRaw) ? imagesRaw.map(String).filter(Boolean) : [],
      supplier_name: p.supplier_code ?? '',
      additional_info: typeof snap.description === 'string' ? snap.description : '',
    }

    try {
      const resp = await fetch('/api/v1/product-analysis/analyze-and-report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ product_info: productInfo }),
      })
      const data = await resp.json().catch(() => null)
      if (resp.ok && data?.success && data.data) {
        setAiRecognition((data.data.ai_recognition as Record<string, any> | null) ?? null)
        setProductReport((data.data.product_report as Record<string, any> | null) ?? null)
        message.success('AI 分析完成')
      } else {
        const msg = data?.error || data?.detail || `HTTP ${resp.status}`
        setAiError(msg)
        message.error(`AI 分析失败：${msg}`)
      }
    } catch (e: any) {
      const msg = e?.message || '网络错误'
      setAiError(msg)
      message.error(`AI 分析失败：${msg}`)
    } finally {
      setAiLoading(false)
    }
  }

  // ---- 成本利润：GET /api/v1/cost-model/status + POST /api/v1/cost-model/calculate ----
  const runCostCalc = async (p: CandidateProduct) => {
    const cost = costPriceOf(p)
    const price = suggestedPriceOf(p)

    const missing: string[] = []
    if (cost === undefined || cost <= 0) missing.push('cost_price')
    if (price === undefined || price <= 0) missing.push('suggested_price')
    if (missing.length > 0) {
      setCostState({ mode: 'contract', missing })
      return
    }

    setCostState({ mode: 'loading' })
    try {
      // 配置（非阻塞：失败不阻断计算）
      let config: Record<string, any> | null = null
      try {
        const statusResp = await fetch('/api/v1/cost-model/status')
        if (statusResp.ok) config = await statusResp.json()
      } catch {
        config = null
      }

      const order = {
        total_amount: price as number,
        subtotal: price as number,
        currency: 'USD',
        country_code: p.target_market && p.target_market.length <= 2 ? p.target_market : 'US',
        items: [
          {
            product_id: p.id,
            name: p.name,
            quantity: 1,
            unit_price: price as number,
            cost_price: cost as number,
          },
        ],
        shipping_weight: p.weight_kg ?? undefined,
      }

      const resp = await fetch('/api/v1/cost-model/calculate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ order }),
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}))
        throw new Error(err?.detail || `HTTP ${resp.status}`)
      }
      const data = await resp.json()
      setCostState({ mode: 'done', result: data, config })
    } catch (e: any) {
      const msg = e?.message || '网络错误'
      setCostState({ mode: 'error', message: msg })
      message.error(`成本计算失败：${msg}`)
    }
  }

  // ---- 自动预填成本利润 ----
  const runAutoPrefill = async (p: CandidateProduct) => {
    setAutoPrefillState({ loading: true, result: null, error: null })
    try {
      const resp = await fetch('/api/v1/cost-prefill/auto-prefill-product', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          product_id: p.id,
          persist: true,
        }),
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}))
        throw new Error(err?.detail || `HTTP ${resp.status}`)
      }
      const data = await resp.json()
      setAutoPrefillState({ loading: false, result: data, error: null })
      message.success('成本模型已自动计算并保存')
    } catch (e: any) {
      const msg = e?.message || '网络错误'
      setAutoPrefillState({ loading: false, result: null, error: msg })
      message.error(`自动预填失败：${msg}`)
    }
  }

  // -----------------------------------------------------------------------
  // 表格列
  // -----------------------------------------------------------------------
  const columns: TableProps<CandidateProduct>['columns'] = [
    {
      title: '候选商品',
      key: 'product',
      width: 280,
      render: (_: unknown, p: CandidateProduct) => (
        <div>
          <div style={{ fontWeight: 600, fontSize: 13, color: '#1f1f1f', lineHeight: '18px' }}>
            {p.name}
          </div>
          <div style={{ fontSize: 11, color: '#8c8c8c', marginTop: 2 }}>SKU：{p.sku}</div>
        </div>
      ),
    },
    {
      title: '来源',
      dataIndex: 'source',
      key: 'source',
      width: 120,
      render: (s: string) => (
        <Tag color={SOURCE_COLORS[s] ?? 'default'} icon={s === '1688' ? <ShopOutlined /> : undefined}>
          {s || '-'}
        </Tag>
      ),
    },
    {
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      width: 120,
      render: (c: string | null | undefined) =>
        c ? <Text>{c}</Text> : <Text type="secondary">-</Text>,
    },
    {
      title: '候选状态',
      dataIndex: 'candidate_status',
      key: 'candidate_status',
      width: 110,
      render: (cs: string | null | undefined) => {
        const m = candidateStatusMeta(cs)
        return <Tag color={m.color}>{m.label}</Tag>
      },
    },
    {
      title: '成本价',
      key: 'cost_price',
      width: 100,
      render: (_: unknown, p: CandidateProduct) => <Text>{fmtCny(costPriceOf(p))}</Text>,
    },
    {
      title: '建议价',
      key: 'suggested_price',
      width: 100,
      render: (_: unknown, p: CandidateProduct) => {
        const v = suggestedPriceOf(p)
        return <Text strong type={v !== undefined ? 'success' : undefined}>{fmtUsd(v)}</Text>
      },
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (v: string) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {fmtDate(v)}
        </Text>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 90,
      fixed: 'right',
      render: (_: unknown, p: CandidateProduct) => (
        <Button size="small" icon={<EyeOutlined />} onClick={() => openDetail(p)}>
          详情
        </Button>
      ),
    },
  ]

  // -----------------------------------------------------------------------
  // 详情抽屉 Tab 渲染
  // -----------------------------------------------------------------------
  const renderInfoTab = (p: CandidateProduct) => {
    const cs = candidateStatusMeta(p.candidate_status)
    const wcId = wcIdOf(p)
    const attrs = p.attributes ?? {}
    const attrEntries = Object.entries(attrs)
    const tags = Array.isArray(p.tags) ? p.tags : []

    return (
      <div>
        <ProductTimeline product={p} style={{ marginBottom: 16 }} />

        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="产品名称" span={2}>{p.name}</Descriptions.Item>
          <Descriptions.Item label="SKU">{p.sku}</Descriptions.Item>
          <Descriptions.Item label="品牌">{p.brand || '-'}</Descriptions.Item>
          <Descriptions.Item label="分类">{p.category || '-'}</Descriptions.Item>
          <Descriptions.Item label="目标市场">{p.target_market || '-'}</Descriptions.Item>
          <Descriptions.Item label="Master 状态">
            <Tag color="blue">{MASTER_STATUS_TEXT[p.status] ?? p.status}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="候选状态">
            <Tag color={cs.color}>{cs.label}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="来源">
            <Tag color={SOURCE_COLORS[p.source] ?? 'default'}>{p.source || '-'}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="供应商编号">{p.supplier_code || '-'}</Descriptions.Item>
          <Descriptions.Item label="库存">
            {p.stock_quantity !== undefined ? `${p.stock_quantity} 件` : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="WooCommerce">
            {wcId ? <Tag color="blue" icon={<ShopOutlined />}>#{wcId}</Tag> : <Text type="secondary">未同步</Text>}
          </Descriptions.Item>
          <Descriptions.Item label="来源链接" span={2}>
            {p.source_url ? (
              <a href={p.source_url} target="_blank" rel="noopener noreferrer">
                <LinkOutlined style={{ marginRight: 4 }} />
                {p.source_url}
              </a>
            ) : (
              <Text type="secondary">未记录</Text>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="成本价（meta）">
            <Text type="warning">{fmtCny(costPriceOf(p))}</Text>
          </Descriptions.Item>
          <Descriptions.Item label="建议价（meta）">
            <Text type="success">{fmtUsd(suggestedPriceOf(p))}</Text>
          </Descriptions.Item>
          <Descriptions.Item label="重量（kg）">{p.weight_kg ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="创建时间">{fmtDate(p.created_at)}</Descriptions.Item>
          <Descriptions.Item label="更新时间" span={2}>{fmtDate(p.updated_at)}</Descriptions.Item>
        </Descriptions>

        {p.description && (
          <div style={{ marginTop: 16 }}>
            <Text strong>产品描述：</Text>
            <Paragraph style={{ marginTop: 8, background: '#f5f5f5', padding: 12, borderRadius: 4 }}>
              {p.description}
            </Paragraph>
          </div>
        )}

        {tags.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <Text strong>标签：</Text>
            <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {tags.map((t, i) => (
                <Tag key={i} color="purple">{String(t)}</Tag>
              ))}
            </div>
          </div>
        )}

        {attrEntries.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <Text strong>产品属性（attributes）：</Text>
            <Descriptions column={2} size="small" style={{ marginTop: 8 }}>
              {attrEntries.map(([k, v]) => (
                <Descriptions.Item key={k} label={k}>
                  {typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v)}
                </Descriptions.Item>
              ))}
            </Descriptions>
          </div>
        )}

        <div style={{ marginTop: 16 }}>
          <Text strong>meta 关键字段：</Text>
          <Descriptions column={1} size="small" style={{ marginTop: 8 }}>
            <Descriptions.Item label="meta.woocommerce_id">
              {wcId ? <Tag color="blue">#{wcId}</Tag> : <Text type="secondary">空</Text>}
            </Descriptions.Item>
            <Descriptions.Item label="meta.cost_price">
              {renderMetaVal(p.meta?.cost_price)}
            </Descriptions.Item>
            <Descriptions.Item label="meta.suggested_price">
              {renderMetaVal(p.meta?.suggested_price)}
            </Descriptions.Item>
            <Descriptions.Item label="meta.listing_data_snapshot">
              {p.meta?.listing_data_snapshot
                ? <Tag color="green">存在</Tag>
                : <Text type="secondary">不存在</Text>}
            </Descriptions.Item>
          </Descriptions>
        </div>
      </div>
    )
  }

  const renderAiTab = (p: CandidateProduct) => {
    return (
      <div>
        <Alert
          type="info"
          showIcon
          icon={<RobotOutlined />}
          style={{ marginBottom: 16 }}
          message="AI 产品分析"
          description={
            <span>
              真实端点：<Text code>POST /api/v1/product-analysis/analyze-and-report</Text>
              （一步产出 10 字段 AI 识别 + 17 字段产品信息报告）。请求体
              <Text code>product_info</Text> 由当前候选的 name / category / description /
              meta.cost_price / meta.listing_data_snapshot 组装。
            </span>
          }
        />

        <Space style={{ marginBottom: 16 }} wrap>
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            loading={aiLoading}
            onClick={() => runAiAnalysis(p)}
          >
            开始 AI 分析
          </Button>
          {(aiRecognition || productReport) && (
            <Button icon={<ReloadOutlined />} loading={aiLoading} onClick={() => runAiAnalysis(p)}>
              重新分析
            </Button>
          )}
        </Space>

        {aiLoading && (
          <div style={{ textAlign: 'center', padding: '48px 0' }}>
            <Spin size="large" />
            <Paragraph type="secondary" style={{ marginTop: 12 }}>
              AI 正在识别产品并生成信息报告，通常需要 30–90 秒…
            </Paragraph>
          </div>
        )}

        {!aiLoading && aiError && (
          <Alert
            type="error"
            showIcon
            icon={<ExclamationCircleOutlined />}
            message="AI 分析失败"
            description={aiError}
            style={{ marginBottom: 16 }}
          />
        )}

        {!aiLoading && !aiError && !aiRecognition && !productReport && (
          <Empty description="尚未分析，点击上方按钮开始" />
        )}

        {aiRecognition && (
          <Card
            size="small"
            title={
              <Space>
                <RobotOutlined />
                <span>AI 识别结果（10 字段）</span>
              </Space>
            }
            style={{ marginBottom: 16 }}
          >
            <Descriptions column={2} bordered size="small">
              {AI_RECOGNITION_FIELDS.map((f) => (
                <Descriptions.Item key={f.key} label={f.label} span={f.span ?? 1}>
                  {renderFieldCell(f, aiRecognition)}
                </Descriptions.Item>
              ))}
            </Descriptions>
          </Card>
        )}

        {productReport && (
          <Card
            size="small"
            title={
              <Space>
                <FileTextOutlined />
                <span>产品信息报告（17 字段）</span>
              </Space>
            }
          >
            <Descriptions column={2} bordered size="small">
              {PRODUCT_REPORT_FIELDS.map((f) => (
                <Descriptions.Item key={f.key} label={f.label} span={f.span ?? 1}>
                  {renderFieldCell(f, productReport)}
                </Descriptions.Item>
              ))}
            </Descriptions>
          </Card>
        )}
      </div>
    )
  }

  const renderCostTab = (p: CandidateProduct) => {
    return (
      <div>
        <Alert
          type="info"
          showIcon
          icon={<DollarOutlined />}
          style={{ marginBottom: 16 }}
          message="成本利润测算"
          description={
            <span>
              系统支持两种模式：
              <Tag color="blue" style={{ margin: '0 4px' }}>传统计算</Tag>
              以建议价作为单件售价、meta.cost_price 作为采购价，构造 1 件订单进行落地成本与毛利测算；
              <Tag color="green" style={{ margin: '0 4px' }}>自动预填</Tag>
              基于行业基线自动计算全成本模型并持久化。后期如有差异可人工修改。
            </span>
          }
        />

        <Space style={{ marginBottom: 16 }}>
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            loading={costState.mode === 'loading'}
            onClick={() => runCostCalc(p)}
          >
            传统成本计算
          </Button>
          <Button
            type="primary"
            icon={<RobotOutlined />}
            loading={autoPrefillState.loading}
            onClick={() => runAutoPrefill(p)}
            style={{ backgroundColor: '#52c41a', borderColor: '#52c41a' }}
          >
            自动预填成本
          </Button>
        </Space>

        {/* 自动预填结果展示 */}
        {autoPrefillState.loading && (
          <div style={{ textAlign: 'center', padding: '48px 0', marginBottom: 16 }}>
            <Spin size="large" />
          </div>
        )}

        {autoPrefillState.error && (
          <Alert
            type="error"
            showIcon
            icon={<ExclamationCircleOutlined />}
            message="自动预填失败"
            description={autoPrefillState.error}
            style={{ marginBottom: 16 }}
          />
        )}

        {autoPrefillState.result && (
          <Card
            title={
              <Space>
                <RobotOutlined />
                <span>自动预填结果（{autoPrefillState.result.sku}）</span>
                {autoPrefillState.result.persisted && (
                  <Tag color="green">已保存</Tag>
                )}
              </Space>
            }
            size="small"
            style={{ marginBottom: 16, background: '#f6ffed' }}
          >
            <Row gutter={[16, 16]}>
              <Col xs={24} sm={8}>
                <Card size="small">
                  <Statistic
                    title="采购成本"
                    value={toNum(autoPrefillState.result.cost_breakdown?.purchase_cost) ?? 0}
                    prefix="$"
                    precision={2}
                  />
                </Card>
              </Col>
              <Col xs={24} sm={8}>
                <Card size="small">
                  <Statistic
                    title="落地总成本"
                    value={toNum(autoPrefillState.result.cost_breakdown?.total_landed_cost) ?? 0}
                    prefix="$"
                    precision={2}
                    valueStyle={{ color: '#fa8c16' }}
                  />
                </Card>
              </Col>
              <Col xs={24} sm={8}>
                <Card size="small">
                  <Statistic
                    title="全成本"
                    value={toNum(autoPrefillState.result.cost_breakdown?.total_cost_full) ?? 0}
                    prefix="$"
                    precision={2}
                    valueStyle={{ color: '#f5222d' }}
                  />
                </Card>
              </Col>
            </Row>

            <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
              <Col xs={24} sm={8}>
                <Card size="small" style={{ background: '#e6f7ff' }}>
                  <Statistic
                    title="建议售价"
                    value={toNum(autoPrefillState.result.cost_breakdown?.suggested_selling_price) ?? 0}
                    prefix="$"
                    precision={2}
                    valueStyle={{ color: '#1890ff' }}
                  />
                </Card>
              </Col>
              <Col xs={24} sm={8}>
                <Card size="small" style={{ background: '#f6ffed' }}>
                  <Statistic
                    title="毛利"
                    value={toNum(autoPrefillState.result.cost_breakdown?.gross_margin) ?? 0}
                    prefix="$"
                    precision={2}
                    valueStyle={{ color: '#52c41a' }}
                  />
                </Card>
              </Col>
              <Col xs={24} sm={8}>
                <Card size="small" style={{ background: '#f6ffed' }}>
                  <Statistic
                    title="净利"
                    value={toNum(autoPrefillState.result.cost_breakdown?.net_margin) ?? 0}
                    prefix="$"
                    precision={2}
                    valueStyle={{ color: '#52c41a' }}
                  />
                </Card>
              </Col>
            </Row>

            <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
              <Col xs={24} sm={8}>
                <Card size="small">
                  <Statistic
                    title="保本售价"
                    value={toNum(autoPrefillState.result.cost_breakdown?.break_even_price) ?? 0}
                    prefix="$"
                    precision={2}
                    valueStyle={{ color: '#faad14' }}
                  />
                </Card>
              </Col>
              <Col xs={24} sm={8}>
                <Card size="small">
                  <Statistic
                    title="贡献毛利"
                    value={toNum(autoPrefillState.result.cost_breakdown?.contribution_margin) ?? 0}
                    prefix="$"
                    precision={2}
                  />
                </Card>
              </Col>
              <Col xs={24} sm={8}>
                <Card size="small">
                  <Statistic
                    title="贡献毛利率"
                    value={toNum(autoPrefillState.result.cost_breakdown?.contribution_margin_rate) ?? 0}
                    suffix="%"
                    precision={1}
                  />
                </Card>
              </Col>
            </Row>

            <Divider style={{ margin: '16px 0' }} />
            <Text strong>成本明细：</Text>
            <div style={{ marginTop: 8 }}>
              {[
                { label: '固定分摊', key: 'fixed_amortization' },
                { label: '国内物流', key: 'domestic_shipping' },
                { label: '头程物流', key: 'first_leg_shipping' },
                { label: '尾程物流', key: 'last_leg_shipping' },
                { label: '关税', key: 'tax_estimate' },
                { label: '包装', key: 'packaging' },
                { label: '操作费', key: 'handling' },
                { label: '支付费', key: 'payment_fee' },
                { label: '营销费 (CAC)', key: 'marketing_amortization' },
                { label: '售后损耗', key: 'after_sales_loss' },
              ].map(({ label, key }) => (
                <div
                  key={key}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '6px 0',
                    borderBottom: '1px solid #f0f0f0',
                    fontSize: 12,
                  }}
                >
                  <Text>{label}</Text>
                  <Text strong>${(toNum(autoPrefillState.result.cost_breakdown?.[key]) ?? 0).toFixed(2)}</Text>
                </div>
              ))}
            </div>

            <Alert
              style={{ marginTop: 16 }}
              type="info"
              showIcon
              message="自动预填说明"
              description={
                <span>
                  成本模型基于行业基线自动计算，已保存到数据库（version: v2-auto）。
                  建议售价基于 35% 目标毛利率倒推。如有差异可人工修改。
                  <br />
                  建议售价（CNY）：¥{toNum(autoPrefillState.result.suggested_price_cny) ?? 0}
                </span>
              }
            />
          </Card>
        )}

        {costState.mode === 'contract' && (
          <Alert
            type="warning"
            showIcon
            icon={<ExclamationCircleOutlined />}
            message="无法计算：候选缺少定价字段"
            description={
              <div>
                <Paragraph style={{ marginBottom: 8 }}>
                  端点 <Text code>POST /api/v1/cost-model/calculate</Text> 已存在，但其请求体要求
                  <Text code>order.items[0].cost_price &gt; 0</Text> 与
                  <Text code>order.total_amount &gt; 0</Text>。当前候选缺少：
                </Paragraph>
                <ul style={{ marginBottom: 8, paddingLeft: 20 }}>
                  {costState.missing.map((m) => (
                    <li key={m}>
                      <Text code>meta.{m}</Text>
                    </li>
                  ))}
                </ul>
                <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                  期望契约：模型 <Text code>OrderCostRequest</Text>（backend
                  /api/v1/cost-model/calculate），输入需写入
                  <Text code>meta.cost_price</Text> 与 <Text code>meta.suggested_price</Text>。
                </Paragraph>
              </div>
            }
          />
        )}

        {costState.mode === 'loading' && (
          <div style={{ textAlign: 'center', padding: '48px 0' }}>
            <Spin size="large" />
          </div>
        )}

        {costState.mode === 'error' && (
          <Alert
            type="error"
            showIcon
            icon={<ExclamationCircleOutlined />}
            message="成本计算失败"
            description={costState.message}
          />
        )}

        {costState.mode === 'done' && (
          <div>
            <Row gutter={[16, 16]}>
              <Col xs={24} sm={8}>
                <Card size="small">
                  <Statistic title="售价（subtotal）" value={toNum(costState.result?.revenue?.subtotal) ?? 0} prefix="$" precision={2} />
                </Card>
              </Col>
              <Col xs={24} sm={8}>
                <Card size="small">
                  <Statistic title="落地总成本" value={toNum(costState.result?.costs?.total_cost) ?? 0} prefix="$" precision={2} valueStyle={{ color: '#f5222d' }} />
                </Card>
              </Col>
              <Col xs={24} sm={8}>
                <Card size="small">
                  <Statistic
                    title="毛利率"
                    value={toNum(costState.result?.profit?.gross_margin_percent) ?? 0}
                    suffix="%"
                    precision={1}
                    valueStyle={{
                      color: (toNum(costState.result?.profit?.gross_margin_percent) ?? 0) >= 0 ? '#52c41a' : '#f5222d',
                    }}
                  />
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    毛利 ${numVal(costState.result?.profit?.gross_profit)} ·
                    {PROFIT_STATUS_TEXT[String(costState.result?.profit?.status)] ??
                      String(costState.result?.profit?.status ?? '-')}
                  </Text>
                </Card>
              </Col>
            </Row>

            {Object.keys((costState.result?.costs?.breakdown ?? {}) as Record<string, any>).length > 0 && (
              <div style={{ marginTop: 16 }}>
                <Text strong>成本明细：</Text>
                <div style={{ marginTop: 8 }}>
                  {Object.entries((costState.result?.costs?.breakdown ?? {}) as Record<string, any>).map(
                    ([k, v]) => (
                      <div
                        key={k}
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          padding: '6px 0',
                          borderBottom: '1px solid #f0f0f0',
                          fontSize: 12,
                        }}
                      >
                        <Text>{(v?.description as string) || k}</Text>
                        <Space>
                          <Text strong>${numVal(v?.amount)}</Text>
                          <Tag style={{ margin: 0 }}>{numVal(v?.percentage, 1)}%</Tag>
                        </Space>
                      </div>
                    ),
                  )}
                </div>
              </div>
            )}

            {costState.config &&
              Object.keys(costState.config).length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <Text strong>成本模型配置（/cost-model/status）：</Text>
                  <Descriptions column={2} size="small" style={{ marginTop: 8 }}>
                    {Object.entries(costState.config)
                      .filter(([, v]) => typeof v === 'number' || typeof v === 'string')
                      .map(([k, v]) => (
                        <Descriptions.Item key={k} label={k}>
                          {String(v)}
                        </Descriptions.Item>
                      ))}
                  </Descriptions>
                </div>
              )}

            {costState.result?.profit?.note && (
              <Alert
                style={{ marginTop: 16 }}
                type={
                  (costState.result?.profit?.status as string) === 'loss'
                    ? 'error'
                    : (costState.result?.profit?.status as string) === 'healthy'
                      ? 'success'
                      : 'info'
                }
                showIcon
                message="模型判定"
                description={String(costState.result.profit.note)}
              />
            )}
          </div>
        )}

        {costState.mode === 'idle' && (
          <Empty description="点击上方按钮开始测算" />
        )}
      </div>
    )
  }

  const renderSourceTab = (p: CandidateProduct) => {
    const snap = (p.meta?.listing_data_snapshot ?? null) as Record<string, any> | null
    return (
      <div>
        <Card size="small" style={{ marginBottom: 16 }}>
          <Descriptions column={1} size="small">
            <Descriptions.Item label="来源">
              <Tag color={SOURCE_COLORS[p.source] ?? 'default'}>{p.source || '-'}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="来源链接">
              {p.source_url ? (
                <a href={p.source_url} target="_blank" rel="noopener noreferrer">
                  <LinkOutlined style={{ marginRight: 4 }} />
                  {p.source_url}
                </a>
              ) : (
                <Text type="secondary">未记录 source_url</Text>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="供应商编号">{p.supplier_code || '-'}</Descriptions.Item>
            <Descriptions.Item label="目标市场">{p.target_market || '-'}</Descriptions.Item>
          </Descriptions>
        </Card>

        {snap ? (
          <Card
            size="small"
            title={
              <Space>
                <DatabaseOutlined />
                <span>product_info 快照（meta.listing_data_snapshot）</span>
              </Space>
            }
          >
            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label="name">{String(snap.name ?? '-')}</Descriptions.Item>
              <Descriptions.Item label="regular_price">{fmtUsd(toNum(snap.regular_price))}</Descriptions.Item>
              <Descriptions.Item label="sale_price">{fmtUsd(toNum(snap.sale_price))}</Descriptions.Item>
              <Descriptions.Item label="抓取字段数">
                {Object.keys(snap).length}
              </Descriptions.Item>
            </Descriptions>
          </Card>
        ) : (
          <Alert
            type="info"
            showIcon
            icon={<DatabaseOutlined />}
            message="未找到 1688 抓取快照"
            description={
              <span>
                期望字段 <Text code>meta.listing_data_snapshot</Text>（由
                <Text code>POST /api/v1/product-pipeline/import-from-1688</Text> 写入）。
                当前候选的 meta 中不存在该键，因此无法展示快照——不做任何模拟填充。
              </span>
            }
          />
        )}
      </div>
    )
  }

  // -----------------------------------------------------------------------
  // 渲染
  // -----------------------------------------------------------------------
  return (
    <div style={{ padding: '24px', maxWidth: 1400, margin: '0 auto' }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: 20 }}>
        <Space align="center" size="middle" wrap>
          <RocketOutlined style={{ fontSize: 28, color: '#722ed1' }} />
          <div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
              <Title level={3} style={{ margin: 0 }}>
                候选池
              </Title>
              <Tag color="purple">
                生命周期阶段 ③ · {candidateStage?.label ?? '产品候选'}
              </Tag>
            </div>
            <Text type="secondary">{candidateStage?.description ?? '从 1688 / 供应商 / 手工录入建立候选，尚未成为正式产品。'}</Text>
          </div>
        </Space>
      </div>

      {/* 后端契约态 */}
      {listError && (
        <Alert
          type="warning"
          showIcon
          icon={<ExclamationCircleOutlined />}
          style={{ marginBottom: 16 }}
          message="后端未接入或不可达"
          description={
            <div>
              <Paragraph style={{ marginBottom: 8 }}>
                候选池依赖真实端点 <Text code>GET /api/v1/products</Text>（模型
                <Text code>Product</Text>），当前调用失败：{listError}
              </Paragraph>
              <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                期望契约：返回 <Text code>list[ProductOut]</Text>，其中
                <Text code>candidate_status != null</Text> 的行即候选。本页面不使用任何模拟数据填充。
              </Paragraph>
            </div>
          }
        />
      )}

      {/* 统计卡 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={8} md={6}>
          <Card size="small">
            <Statistic
              title="候选总数"
              value={candidates.length}
              prefix={<StarOutlined />}
              valueStyle={{ color: '#722ed1' }}
            />
          </Card>
        </Col>
        {Object.entries(statusCounts).map(([k, v]) => {
          const m = candidateStatusMeta(k)
          return (
            <Col key={k} xs={24} sm={8} md={6}>
              <Card size="small">
                <Statistic
                  title={m.label}
                  value={v}
                  prefix={m.color === 'green' ? <CheckCircleOutlined /> : <ClockCircleOutlined />}
                  valueStyle={{ color: m.color === 'red' ? '#f5222d' : m.color === 'green' ? '#52c41a' : m.color === 'orange' ? '#fa8c16' : '#1f1f1f' }}
                />
              </Card>
            </Col>
          )
        })}
      </Row>

      {/* 工具栏 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap size="middle">
          <Tooltip title="按名称或 SKU 模糊搜索">
            <Input
              placeholder="搜索名称 / SKU"
              prefix={<SearchOutlined />}
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              allowClear
              style={{ width: 220 }}
            />
          </Tooltip>
          <Space size={4}>
            <FilterOutlined style={{ color: '#8c8c8c' }} />
            <Select
              value={candidateStatusFilter}
              onChange={setCandidateStatusFilter}
              options={candidateStatusOptions}
              style={{ width: 170 }}
              placeholder="候选状态"
            />
          </Space>
          <Select
            value={sourceFilter}
            onChange={setSourceFilter}
            options={sourceOptions}
            style={{ width: 160 }}
            placeholder="来源"
          />
          <Select
            value={categoryFilter}
            onChange={setCategoryFilter}
            options={categoryOptions}
            style={{ width: 150 }}
            placeholder="分类"
          />
          <Button icon={<ReloadOutlined />} onClick={loadCandidates} loading={loading}>
            刷新
          </Button>
          <Button type="primary" icon={<ImportOutlined />} onClick={openImport}>
            从 1688 导入
          </Button>
        </Space>
      </Card>

      {/* 表格 */}
      <Card size="small">
        <Table
          columns={columns}
          dataSource={filtered}
          rowKey="id"
          loading={loading}
          scroll={{ x: 1200 }}
          pagination={{
            defaultPageSize: 10,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (t) => `共 ${t} 个候选`,
          }}
          locale={{
            emptyText: listError ? (
              <Empty description="后端不可达，无法读取候选" />
            ) : candidates.length === 0 ? (
              <Empty description="暂无候选（products.candidate_status 均为空）。可通过「从 1688 导入」建立第一个候选。" />
            ) : (
              <Empty description="当前筛选条件下无候选" />
            ),
          }}
        />
      </Card>

      {/* 详情 Drawer */}
      <Drawer
        title={
          current ? (
            <Space align="center">
              <FileTextOutlined />
              <span>{current.name}</span>
              <Tag color={candidateStatusMeta(current.candidate_status).color}>
                {candidateStatusMeta(current.candidate_status).label}
              </Tag>
            </Space>
          ) : (
            '候选详情'
          )
        }
        open={detailOpen}
        onClose={() => {
          setDetailOpen(false)
          setCurrent(null)
        }}
        width={960}
      >
        {current ? (
          <Tabs
            defaultActiveKey="info"
            items={[
              {
                key: 'info',
                label: (
                  <Space>
                    <FileTextOutlined />
                    <span>基本信息</span>
                  </Space>
                ),
                children: renderInfoTab(current),
              },
              {
                key: 'ai',
                label: (
                  <Space>
                    <RobotOutlined />
                    <span>AI 分析</span>
                  </Space>
                ),
                children: renderAiTab(current),
              },
              {
                key: 'cost',
                label: (
                  <Space>
                    <DollarOutlined />
                    <span>成本利润</span>
                  </Space>
                ),
                children: renderCostTab(current),
              },
              {
                key: 'source',
                label: (
                  <Space>
                    <ShopOutlined />
                    <span>1688 来源</span>
                  </Space>
                ),
                children: renderSourceTab(current),
              },
            ]}
          />
        ) : (
          <Empty description="未选择候选" />
        )}
      </Drawer>

      {/* 1688 导入弹窗 */}
      <Drawer
        title={
          <Space>
            <ImportOutlined />
            <span>从 1688 导入候选</span>
          </Space>
        }
        open={importOpen}
        onClose={() => setImportOpen(false)}
        width={480}
        extra={
          <Space>
            <Button onClick={() => setImportOpen(false)}>取消</Button>
            <Button
              type="primary"
              icon={importLoading ? <ReloadOutlined /> : <ArrowRightOutlined />}
              loading={importLoading}
              onClick={handleImport1688}
            >
              导入
            </Button>
          </Space>
        }
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="端点"
          description={
            <span>
              <Text code>POST /api/v1/product-pipeline/import-from-1688</Text>，body：
              <Text code>{'{ url_or_id, auto_run_pipeline: false, auto_list: false }'}</Text>
              。导入成功后会创建 products 行（candidate_status = candidate），不自动跑工作流、不自动上架。
            </span>
          }
        />
        <Form form={importForm} layout="vertical">
          <Form.Item
            name="url_or_id"
            label="1688 商品 URL 或商品 ID"
            rules={[{ required: true, message: '请输入 1688 商品 URL 或商品 ID' }]}
          >
            <Input
              placeholder="https://detail.1688.com/offer/1078487117828.html 或 1078487117828"
              allowClear
              autoFocus
              onPressEnter={handleImport1688}
            />
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  )
}
