/**
 * 机会池（Opportunity Pool）— 生命周期阶段②。
 *
 * 契约：backend/app/schemas/opportunity.py + endpoints/opportunity.py
 * 真实端点（全部 fetch('/api/v1/...')）：
 *   GET    /api/v1/opportunities/meta
 *   GET    /api/v1/opportunities
 *   POST   /api/v1/opportunities
 *   GET    /api/v1/opportunities/{id}
 *   PATCH  /api/v1/opportunities/{id}
 *   POST   /api/v1/opportunities/{id}/candidates
 *   DELETE /api/v1/opportunities/{id}/candidates/{product_id}
 *   GET    /api/v1/products              （关联候选弹窗挑产品用）
 *
 * 关键约束：
 * - 枚举「值」一律来自 GET /meta，页内不硬编码枚举数组；
 *   仅中文 label / Tag 颜色映射是展示层写死。
 * - 阶段定义只从 ../lifecycle/stages 取，不在页面内硬编码阶段数组。
 * - 零 mock 数据：后端不可达时渲染显式 Alert + message.error，绝不编造。
 * - antd v6.6.2 / @ant-design/icons 6.3.4：Steps.Step / List.height 已移除；
 *   Modal 用 open（非 visible）；Tabs 用 items=；Drawer 用 open=；
 *   PlayOutlined 不存在（本组件未使用任何不存在图标名）。
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  message,
  Modal,
  Progress,
  Row,
  Select,
  Space,
  Spin,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import type { TableProps } from 'antd'
import {
  BulbOutlined,
  CompassOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  EditOutlined,
  ExclamationCircleOutlined,
  EyeOutlined,
  FileTextOutlined,
  FilterOutlined,
  FireOutlined,
  InfoCircleOutlined,
  LinkOutlined,
  PlusOutlined,
  ProfileOutlined,
  ReloadOutlined,
  SearchOutlined,
  SolutionOutlined,
} from '@ant-design/icons'
import { getProductImageUrl, type ProductWithMeta } from '../utils/productImage'
import { STAGE_BY_ID } from '../lifecycle/stages'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

// =============================================================================
// 数据契约（对齐 backend/app/schemas/opportunity.py 与 product.py）
//
// 说明：真实后端契约与任务描述的差异（在交付报告「契约不一致」中列出）：
// - GET /api/v1/opportunities 实际返回 list[OpportunityOut]（非 {items,total}），
//   且不支持 signal_type 查询参数（仅 status / category / limit / offset），
//   因此 signal_type 过滤在前端完成。
// - GET /api/v1/opportunities/{id}/candidates 实际返回 list[OpportunityCandidateOut]。
// - GET /api/v1/products 实际返回 list[ProductOut]。
// - OpportunityDetail = OpportunityOut + candidates[]，
//   因此本组件在详情抽屉里直接复用 GET /{id} 内联的 candidates，
//   不再重复调 GET /{id}/candidates（等价且更省一次往返）。
//
// 本组件对响应体采用「数组 或 {items: []}」双路兼容读取，不做任何 mock。
// =============================================================================

interface OpportunityOut {
  id: string
  workspace_id: string
  title: string
  description: string | null
  category: string | null
  keywords: unknown[]
  signal_type: string
  signal_source: Record<string, unknown> | null
  market_signals: unknown[]
  evidence: unknown[]
  status: string
  confidence: number | string | null
  closed_at: string | null
  closed_reason: string | null
  created_at: string
  updated_at: string
  candidate_count: number
}

interface OpportunityDetail extends OpportunityOut {
  candidates: OpportunityCandidateOut[]
}

interface OpportunityCandidateOut {
  id: string
  opportunity_id: string
  product_id: string
  linked_at: string
  link_reason: string | null
  product_sku: string | null
  product_name: string | null
  product_status: string | null
  candidate_status: string | null
}

interface OpportunityMeta {
  statuses: string[]
  signal_types: string[]
}

interface ProductLite {
  id: string
  sku: string
  name: string
  category?: string | null
  status?: string
  candidate_status?: string | null
}

interface OpportunityCreatePayload {
  title: string
  description?: string | null
  category?: string | null
  keywords?: string[]
  signal_type?: string
  confidence?: number | null
}

interface OpportunityUpdatePayload {
  title?: string
  description?: string | null
  category?: string | null
  keywords?: string[] | null
  status?: string
  confidence?: number | null
  closed_reason?: string | null
}

// =============================================================================
// 枚举中文文案与 Tag 颜色（值来自 GET /meta；仅 label/color 是展示层写死）
// =============================================================================

const STATUS_LABELS: Record<string, string> = {
  open: '进行中',
  evaluating: '评估中',
  converting: '转化中',
  closed: '已关闭',
  discarded: '已放弃',
}

const STATUS_COLORS: Record<string, string> = {
  open: 'blue',
  evaluating: 'gold',
  converting: 'purple',
  closed: 'default',
  discarded: 'red',
}

const SIGNAL_LABELS: Record<string, string> = {
  search_trend: '搜索趋势',
  competitor_gap: '竞品缺口',
  review_pain: '评论痛点',
  social: '社媒讨论',
  manual: '手工录入',
  other: '其他',
}

const SIGNAL_COLORS: Record<string, string> = {
  search_trend: 'cyan',
  competitor_gap: 'orange',
  review_pain: 'red',
  social: 'magenta',
  manual: 'geekblue',
  other: 'default',
}

const CANDIDATE_STATUS_LABELS: Record<string, string> = {
  candidate: '候选中',
  approved: '已批准',
  testing: '测试中',
  winner: '已胜出',
  rejected: '已拒绝',
}

const CANDIDATE_STATUS_COLORS: Record<string, string> = {
  candidate: 'orange',
  approved: 'green',
  testing: 'blue',
  winner: 'purple',
  rejected: 'red',
}

const MASTER_STATUS_LABELS: Record<string, string> = {
  active: '已转正',
  draft: '草稿',
  inactive: '已停用',
  listed: '已上架',
  pending: '待处理',
}

const statusLabel = (v: string | null | undefined): string =>
  v ? STATUS_LABELS[v] ?? v : '-'
const statusColor = (v: string | null | undefined): string =>
  v ? STATUS_COLORS[v] ?? 'default' : 'default'
const signalLabel = (v: string | null | undefined): string =>
  v ? SIGNAL_LABELS[v] ?? v : '-'
const signalColor = (v: string | null | undefined): string =>
  v ? SIGNAL_COLORS[v] ?? 'default' : 'default'
const candStatusLabel = (v: string | null | undefined): string =>
  v ? CANDIDATE_STATUS_LABELS[v] ?? v : '-'
const candStatusCode = (v: string | null | undefined): string =>
  v ? CANDIDATE_STATUS_COLORS[v] ?? 'default' : 'default'
const masterStatusLabel = (v: string | null | undefined): string =>
  v ? MASTER_STATUS_LABELS[v] ?? v : '-'

// =============================================================================
// 通用渲染辅助
// =============================================================================

const fmtDate = (v: string | null | undefined): string =>
  v ? new Date(v).toLocaleString() : '-'

const toNumber = (v: unknown): number | undefined => {
  if (v === null || v === undefined || v === '') return undefined
  if (typeof v === 'number') return Number.isFinite(v) ? v : undefined
  if (typeof v === 'string') {
    const n = Number(v)
    return Number.isFinite(n) ? n : undefined
  }
  return undefined
}

/** 从后端响应中提取数组（兼容 list[] 与 {items: []} 两种形状） */
const extractList = <T,>(body: unknown): T[] => {
  if (Array.isArray(body)) return body as T[]
  if (body && typeof body === 'object' && Array.isArray((body as { items?: unknown }).items)) {
    return (body as { items: T[] }).items
  }
  return []
}

/** 从后端错误响应中提取可读 message（detail 可能是字符串或 FastAPI 校验错误数组） */
const extractError = async (resp: Response): Promise<string> => {
  try {
    const data = await resp.json()
    const d = data?.detail
    if (typeof d === 'string') return d
    if (Array.isArray(d) && d.length > 0) {
      return d
        .map((item: { msg?: string; field?: unknown }) => {
          const field = item?.field ? String(item.field) : ''
          return field ? `${field}: ${item?.msg ?? ''}` : item?.msg ?? ''
        })
        .filter(Boolean)
        .join('；')
    }
    return `HTTP ${resp.status}`
  } catch {
    return `HTTP ${resp.status}`
  }
}

/** 可读 JSON 展示（对象 / 数组），空态友好 */
const JsonBlock = ({
  data,
  emptyHint = '未记录',
}: {
  data: unknown
  emptyHint?: string
}): React.ReactElement => {
  if (data === null || data === undefined) {
    return <Text type="secondary">{emptyHint}</Text>
  }
  if (Array.isArray(data) && data.length === 0) {
    return <Text type="secondary">{emptyHint}</Text>
  }
  if (typeof data === 'object' && !Array.isArray(data) && Object.keys(data as object).length === 0) {
    return <Text type="secondary">{emptyHint}</Text>
  }
  const text = JSON.stringify(data, null, 2)
  return (
    <pre
      style={{
        background: '#f5f5f5',
        padding: 12,
        borderRadius: 4,
        margin: 0,
        maxHeight: 320,
        overflow: 'auto',
        fontSize: 12,
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-all',
        lineHeight: 1.6,
      }}
    >
      {text}
    </pre>
  )
}

/** 关键词展示（keywords 是 list[Any]，元素可能是字符串或对象） */
const KeywordsDisplay = ({
  keywords,
}: {
  keywords: unknown[] | null | undefined
}): React.ReactElement => {
  if (!keywords || keywords.length === 0) return <Text type="secondary">-</Text>
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
      {keywords.map((k, i) => {
        const text = typeof k === 'object' && k !== null ? JSON.stringify(k) : String(k)
        return (
          <Tag key={i} color="geekblue" style={{ margin: 0 }}>
            {text}
          </Tag>
        )
      })}
    </div>
  )
}

/** 置信度条（0-100；后端返回 Decimal，可能是数字或字符串） */
const ConfidenceBar = ({ value }: { value: unknown }): React.ReactElement => {
  const n = toNumber(value)
  if (n === undefined) return <Text type="secondary">-</Text>
  const color = n >= 70 ? '#52c41a' : n >= 40 ? '#fa8c16' : '#f5222d'
  return (
    <div style={{ minWidth: 100 }}>
      <Progress percent={n} size="small" showInfo={false} strokeColor={color} style={{ margin: 0 }} />
      <Text style={{ fontSize: 12 }}>{n}%</Text>
    </div>
  )
}

// =============================================================================
// 主组件
// =============================================================================

export default function Opportunity() {
  const stage = STAGE_BY_ID.get('opportunity')

  // ---- 枚举字典（GET /api/v1/opportunities/meta）----
  const [meta, setMeta] = useState<OpportunityMeta | null>(null)
  const [metaError, setMetaError] = useState<string | null>(null)

  // ---- 列表 ----
  const [list, setList] = useState<OpportunityOut[]>([])
  const [listLoading, setListLoading] = useState(false)
  const [listError, setListError] = useState<string | null>(null)
  const [filterStatus, setFilterStatus] = useState<string | undefined>(undefined)
  const [filterSignalType, setFilterSignalType] = useState<string | undefined>(undefined)
  const [filterCategory, setFilterCategory] = useState<string | undefined>(undefined)
  const [keyword, setKeyword] = useState('')

  // ---- 新建弹窗 ----
  const [createOpen, setCreateOpen] = useState(false)
  const [createLoading, setCreateLoading] = useState(false)
  const [createForm] = Form.useForm<OpportunityCreatePayload>()

  // ---- 详情抽屉 ----
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [current, setCurrent] = useState<OpportunityDetail | null>(null)
  const [detailTab, setDetailTab] = useState('info')
  const [statusForm] = Form.useForm<{ status: string; closed_reason?: string }>()
  const [statusSaving, setStatusSaving] = useState(false)

  // ---- 关联候选弹窗 ----
  const [linkOpen, setLinkOpen] = useState(false)
  const [linkLoading, setLinkLoading] = useState(false)
  const [products, setProducts] = useState<ProductLite[]>([])
  const [productsLoading, setProductsLoading] = useState(false)
  const [productsError, setProductsError] = useState<string | null>(null)
  const [linkForm] = Form.useForm<{ product_id: string; link_reason?: string }>()
  const [unlinking, setUnlinking] = useState(false)

  // ---------------------------------------------------------------------------
  // 加载枚举字典
  // ---------------------------------------------------------------------------
  const loadMeta = useCallback(async () => {
    try {
      const resp = await fetch('/api/v1/opportunities/meta')
      if (!resp.ok) throw new Error(await extractError(resp))
      const data = (await resp.json()) as OpportunityMeta
      setMeta({ statuses: data.statuses ?? [], signal_types: data.signal_types ?? [] })
      setMetaError(null)
    } catch (e) {
      const msg = (e as Error)?.message || '网络错误'
      setMetaError(msg)
      message.error(`加载枚举字典失败：${msg}`)
    }
  }, [])

  // ---------------------------------------------------------------------------
  // 加载列表（GET /api/v1/opportunities）
  // 后端不支持 signal_type 查询参数，signal_type 过滤在前端完成。
  // ---------------------------------------------------------------------------
  const loadList = useCallback(
    async () => {
      setListLoading(true)
      setListError(null)
      try {
        const params = new URLSearchParams()
        params.set('limit', '200')
        params.set('offset', '0')
        if (filterStatus) params.set('status', filterStatus)
        if (filterCategory) params.set('category', filterCategory)
        const resp = await fetch(`/api/v1/opportunities?${params.toString()}`)
        if (!resp.ok) throw new Error(await extractError(resp))
        const body = await resp.json()
        setList(extractList<OpportunityOut>(body))
      } catch (e) {
        const msg = (e as Error)?.message || '网络错误'
        setList([])
        setListError(msg)
        message.error(`加载机会列表失败：${msg}`)
      } finally {
        setListLoading(false)
      }
    },
    [filterStatus, filterCategory],
  )

  useEffect(() => {
    loadMeta()
  }, [loadMeta])

  useEffect(() => {
    loadList()
  }, [loadList])

  // ---------------------------------------------------------------------------
  // 前端过滤（signal_type + 关键词）
  // ---------------------------------------------------------------------------
  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase()
    return list.filter((o) => {
      if (filterSignalType && o.signal_type !== filterSignalType) return false
      if (!kw) return true
      const kwText = o.keywords
        .map((k) => (typeof k === 'object' && k !== null ? JSON.stringify(k) : String(k)))
        .join(' ')
      const hay = `${o.title} ${o.category ?? ''} ${o.description ?? ''} ${kwText}`.toLowerCase()
      return hay.includes(kw)
    })
  }, [list, keyword, filterSignalType])

  // 分类选项（从已加载数据派生，不做前端硬编码）
  const categoryOptions = useMemo(() => {
    const set = new Set<string>()
    for (const o of list) if (o.category) set.add(o.category)
    return Array.from(set).map((v) => ({ value: v, label: v }))
  }, [list])

  const statusFilterOptions = useMemo(
    () => (meta?.statuses ?? []).map((s) => ({ value: s, label: statusLabel(s) })),
    [meta],
  )
  const signalFilterOptions = useMemo(
    () => (meta?.signal_types ?? []).map((s) => ({ value: s, label: signalLabel(s) })),
    [meta],
  )

  // ---------------------------------------------------------------------------
  // 新建机会（POST /api/v1/opportunities）
  // ---------------------------------------------------------------------------
  const openCreate = () => {
    createForm.resetFields()
    createForm.setFieldsValue({ signal_type: 'manual' })
    setCreateOpen(true)
  }

  const handleCreate = async () => {
    let values: OpportunityCreatePayload
    try {
      values = await createForm.validateFields()
    } catch {
      return
    }
    setCreateLoading(true)
    try {
      const body: Record<string, unknown> = {
        title: values.title,
        description: values.description ?? null,
        category: values.category ?? null,
        keywords: values.keywords ?? [],
        signal_type: values.signal_type || 'manual',
      }
      const conf = toNumber(values.confidence)
      if (conf !== undefined) body.confidence = conf
      const resp = await fetch('/api/v1/opportunities', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!resp.ok) {
        message.error(`新建失败：${await extractError(resp)}`)
        return
      }
      message.success('已创建机会')
      setCreateOpen(false)
      createForm.resetFields()
      loadList()
    } catch (e) {
      message.error(`新建失败：${(e as Error)?.message || '网络错误'}`)
    } finally {
      setCreateLoading(false)
    }
  }

  // ---------------------------------------------------------------------------
  // 详情抽屉（GET /api/v1/opportunities/{id}）
  // ---------------------------------------------------------------------------
  const openDetail = async (id: string) => {
    setDetailOpen(true)
    setDetailTab('info')
    setDetailLoading(true)
    setDetailError(null)
    setCurrent(null)
    statusForm.resetFields()
    try {
      const resp = await fetch(`/api/v1/opportunities/${id}`)
      if (!resp.ok) throw new Error(await extractError(resp))
      const data = (await resp.json()) as OpportunityDetail
      setCurrent(data)
      statusForm.setFieldsValue({
        status: data.status,
        closed_reason: data.closed_reason ?? '',
      })
    } catch (e) {
      const msg = (e as Error)?.message || '网络错误'
      setDetailError(msg)
      message.error(`加载详情失败：${msg}`)
    } finally {
      setDetailLoading(false)
    }
  }

  const refreshDetail = async () => {
    if (!current) return
    try {
      const resp = await fetch(`/api/v1/opportunities/${current.id}`)
      if (!resp.ok) throw new Error(await extractError(resp))
      const data = (await resp.json()) as OpportunityDetail
      setCurrent(data)
      statusForm.setFieldsValue({
        status: data.status,
        closed_reason: data.closed_reason ?? '',
      })
    } catch (e) {
      message.error(`刷新详情失败：${(e as Error)?.message || '网络错误'}`)
    }
  }

  // ---------------------------------------------------------------------------
  // 状态更新（PATCH /api/v1/opportunities/{id}）
  // 关闭/放弃必填 closed_reason；从关闭状态改回仅带 status。
  // ---------------------------------------------------------------------------
  const handleStatusChange = async () => {
    if (!current) return
    let values: { status: string; closed_reason?: string }
    try {
      values = await statusForm.validateFields()
    } catch {
      return
    }
    setStatusSaving(true)
    try {
      const payload: OpportunityUpdatePayload = { status: values.status }
      const isClosing = values.status === 'closed' || values.status === 'discarded'
      if (isClosing) {
        if (!values.closed_reason?.trim()) {
          message.error('关闭或放弃机会时必须填写关闭原因')
          return
        }
        payload.closed_reason = values.closed_reason.trim()
      }
      const resp = await fetch(`/api/v1/opportunities/${current.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!resp.ok) {
        message.error(`更新状态失败：${await extractError(resp)}`)
        return
      }
      const data = (await resp.json()) as Partial<OpportunityOut>
      message.success('状态已更新')
      setCurrent({ ...current, ...data })
      loadList()
    } catch (e) {
      message.error(`更新状态失败：${(e as Error)?.message || '网络错误'}`)
    } finally {
      setStatusSaving(false)
    }
  }

  // ---------------------------------------------------------------------------
  // 关联候选（GET /api/v1/products → POST /{id}/candidates）
  // ---------------------------------------------------------------------------
  const openLinkModal = async () => {
    if (!current) return
    setLinkOpen(true)
    linkForm.resetFields()
    setProducts([])
    setProductsError(null)
    setProductsLoading(true)
    try {
      const resp = await fetch('/api/v1/products?limit=200&offset=0')
      if (!resp.ok) throw new Error(await extractError(resp))
      const body = await resp.json()
      setProducts(extractList<ProductLite>(body))
    } catch (e) {
      const msg = (e as Error)?.message || '网络错误'
      setProductsError(msg)
      message.error(`加载产品列表失败：${msg}`)
    } finally {
      setProductsLoading(false)
    }
  }

  const handleLink = async () => {
    if (!current) return
    let values: { product_id: string; link_reason?: string }
    try {
      values = await linkForm.validateFields()
    } catch {
      return
    }
    setLinkLoading(true)
    try {
      const body: Record<string, unknown> = { product_id: values.product_id }
      if (values.link_reason?.trim()) body.link_reason = values.link_reason.trim()
      const resp = await fetch(`/api/v1/opportunities/${current.id}/candidates`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!resp.ok) {
        message.error(`关联失败：${await extractError(resp)}`)
        return
      }
      message.success('已关联候选')
      setLinkOpen(false)
      linkForm.resetFields()
      await refreshDetail()
      loadList()
    } catch (e) {
      message.error(`关联失败：${(e as Error)?.message || '网络错误'}`)
    } finally {
      setLinkLoading(false)
    }
  }

  // ---------------------------------------------------------------------------
  // 解除关联（DELETE /api/v1/opportunities/{id}/candidates/{product_id}）
  // ---------------------------------------------------------------------------
  const handleUnlink = (candidate: OpportunityCandidateOut) => {
    if (!current) return
    const displayName =
      candidate.product_name || candidate.product_sku || candidate.product_id
    Modal.confirm({
      title: '确认解除关联？',
      icon: <ExclamationCircleOutlined />,
      content: `将把「${displayName}」从当前机会中移除。该操作不影响产品本身，只删除机会-候选归属关系。`,
      okText: '确认解除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        setUnlinking(true)
        try {
          const resp = await fetch(
            `/api/v1/opportunities/${current.id}/candidates/${candidate.product_id}`,
            { method: 'DELETE' },
          )
          // DELETE 成功返回 204（无 body）；其他非 2xx 视为失败
          if (!resp.ok && resp.status !== 204) {
            throw new Error(await extractError(resp))
          }
          message.success('已解除关联')
          await refreshDetail()
          loadList()
        } catch (e) {
          message.error(`解除关联失败：${(e as Error)?.message || '网络错误'}`)
        } finally {
          setUnlinking(false)
        }
      },
    })
  }

  // ---------------------------------------------------------------------------
  // 主表格列
  // ---------------------------------------------------------------------------
  const columns: TableProps<OpportunityOut>['columns'] = [
    {
      title: '机会标题',
      dataIndex: 'title',
      key: 'title',
      width: 260,
      ellipsis: true,
      render: (_: unknown, o: OpportunityOut) => (
        <div>
          <div style={{ fontWeight: 600, fontSize: 13, color: '#1f1f1f', lineHeight: '18px' }}>
            {o.title}
          </div>
          {o.description && (
            <div
              style={{
                fontSize: 11,
                color: '#8c8c8c',
                marginTop: 2,
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                maxWidth: 240,
              }}
            >
              {o.description}
            </div>
          )}
        </div>
      ),
    },
    {
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      width: 120,
      render: (c: string | null) => (c ? <Text>{c}</Text> : <Text type="secondary">-</Text>),
    },
    {
      title: '信号类型',
      dataIndex: 'signal_type',
      key: 'signal_type',
      width: 120,
      render: (v: string) => (
        <Tag color={signalColor(v)} icon={<CompassOutlined />}>
          {signalLabel(v)}
        </Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (v: string) => <Tag color={statusColor(v)}>{statusLabel(v)}</Tag>,
    },
    {
      title: '置信度',
      dataIndex: 'confidence',
      key: 'confidence',
      width: 130,
      render: (v: unknown) => <ConfidenceBar value={v} />,
    },
    {
      title: '关联候选',
      dataIndex: 'candidate_count',
      key: 'candidate_count',
      width: 90,
      align: 'center',
      render: (n: number) =>
        n > 0 ? (
          <Tag color="purple" icon={<LinkOutlined />}>
            {n}
          </Tag>
        ) : (
          <Text type="secondary">0</Text>
        ),
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
      render: (_: unknown, o: OpportunityOut) => (
        <Button size="small" icon={<EyeOutlined />} onClick={() => openDetail(o.id)}>
          详情
        </Button>
      ),
    },
  ]

  // ---------------------------------------------------------------------------
  // 详情 Tab：基本信息
  // ---------------------------------------------------------------------------
  const renderInfoTab = (o: OpportunityDetail): React.ReactElement => (
    <div>
      <Descriptions column={2} bordered size="small">
        <Descriptions.Item label="机会标题" span={2}>
          <Text strong>{o.title}</Text>
        </Descriptions.Item>
        <Descriptions.Item label="机会 ID">{o.id}</Descriptions.Item>
        <Descriptions.Item label="工作区 ID">{o.workspace_id}</Descriptions.Item>
        <Descriptions.Item label="分类">{o.category || '-'}</Descriptions.Item>
        <Descriptions.Item label="信号类型">
          <Tag color={signalColor(o.signal_type)} icon={<CompassOutlined />}>
            {signalLabel(o.signal_type)}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="状态">
          <Tag color={statusColor(o.status)}>{statusLabel(o.status)}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="置信度">
          <ConfidenceBar value={o.confidence} />
        </Descriptions.Item>
        <Descriptions.Item label="关联候选数">
          <Text>{o.candidate_count}</Text>
        </Descriptions.Item>
        <Descriptions.Item label="关键词" span={2}>
          <KeywordsDisplay keywords={o.keywords} />
        </Descriptions.Item>
        <Descriptions.Item label="描述" span={2}>
          {o.description ? (
            <Paragraph style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{o.description}</Paragraph>
          ) : (
            <Text type="secondary">-</Text>
          )}
        </Descriptions.Item>
        <Descriptions.Item label="关闭时间">{fmtDate(o.closed_at)}</Descriptions.Item>
        <Descriptions.Item label="关闭原因">
          {o.closed_reason || <Text type="secondary">-</Text>}
        </Descriptions.Item>
        <Descriptions.Item label="创建时间">{fmtDate(o.created_at)}</Descriptions.Item>
        <Descriptions.Item label="更新时间">{fmtDate(o.updated_at)}</Descriptions.Item>
      </Descriptions>
    </div>
  )

  // ---------------------------------------------------------------------------
  // 详情 Tab：状态
  // ---------------------------------------------------------------------------
  const renderStatusTab = (o: OpportunityDetail): React.ReactElement => {
    const isClosing = o.status === 'closed' || o.status === 'discarded'
    return (
      <div>
        <Alert
          type="info"
          showIcon
          icon={<InfoCircleOutlined />}
          style={{ marginBottom: 16 }}
          message="端点"
          description={
            <span>
              <Text code>PATCH /api/v1/opportunities/{'{id}'}</Text>，请求体
              <Text code>OpportunityUpdate</Text>（全可选，只写传入字段）。切到
              <Text code>closed</Text> 或 <Text code>discarded</Text> 时必填
              <Text code>closed_reason</Text>；从关闭状态改回只带 <Text code>status</Text> 即可。
            </span>
          }
        />
        <Alert
          type={isClosing ? 'warning' : 'success'}
          showIcon
          style={{ marginBottom: 16 }}
          message={`当前状态：${statusLabel(o.status)}`}
          description={
            isClosing
              ? `关闭时间：${fmtDate(o.closed_at)} · 原因：${o.closed_reason || '-'}`
              : '可在此切换到任意状态；选择「已关闭」或「已放弃」时，需填写关闭原因。'
          }
        />
        <Card size="small">
          <Form form={statusForm} layout="vertical" onFinish={handleStatusChange}>
            <Row gutter={16}>
              <Col xs={24} sm={12} md={8}>
                <Form.Item
                  name="status"
                  label="状态"
                  rules={[{ required: true, message: '请选择状态' }]}
                >
                  <Select
                    options={statusFilterOptions}
                    placeholder="选择状态"
                    style={{ width: '100%' }}
                    disabled={!meta}
                  />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12} md={16}>
                <Form.Item
                  name="closed_reason"
                  label="关闭原因（closed_reason）"
                  dependencies={['status']}
                  rules={[
                    { max: 256, message: '最长 256 字' },
                    ({ getFieldValue }) => ({
                      validator(_, value) {
                        const s = getFieldValue('status')
                        if ((s === 'closed' || s === 'discarded') && !value?.trim()) {
                          return Promise.reject(new Error('关闭或放弃时必填'))
                        }
                        return Promise.resolve()
                      },
                    }),
                  ]}
                >
                  <TextArea
                    maxLength={256}
                    showCount
                    placeholder="切到「已关闭」或「已放弃」时必填；从关闭状态改回时留空即可"
                    autoSize={{ minRows: 2, maxRows: 4 }}
                  />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item style={{ marginBottom: 0 }}>
              <Space>
                <Button type="primary" htmlType="submit" loading={statusSaving}>
                  保存状态
                </Button>
                <Button icon={<ReloadOutlined />} onClick={loadList} disabled={statusSaving}>
                  同步列表
                </Button>
              </Space>
            </Form.Item>
          </Form>
        </Card>
      </div>
    )
  }

  // ---------------------------------------------------------------------------
  // 详情 Tab：关联候选
  // ---------------------------------------------------------------------------
  const candidateColumns: TableProps<OpportunityCandidateOut>['columns'] = [
    {
      title: '产品',
      key: 'product',
      width: 260,
      render: (_: unknown, c: OpportunityCandidateOut) => {
        // OpportunityCandidateOut 只返回 product_sku/product_name/product_status，
        // 不含 meta/images，因此这里恒为 null、渲染下方「无图」占位块。
        const imageUrl = getProductImageUrl(c as unknown as ProductWithMeta)
        return (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {imageUrl ? (
              <img 
                src={imageUrl} 
                alt={c.product_name ?? ''} 
                style={{ width: 40, height: 40, borderRadius: '4px', objectFit: 'cover', border: '1px solid #f0f0f0', flexShrink: 0 }}
                onError={(e) => { e.currentTarget.style.display = 'none' }}
              />
            ) : (
              <div style={{ width: 40, height: 40, borderRadius: '4px', background: '#f5f5f5', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#999', fontSize: 10, flexShrink: 0 }}>
                无图
              </div>
            )}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 600, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {c.product_name || <Text type="secondary">（未回填名称）</Text>}
              </div>
              <div style={{ fontSize: 11, color: '#8c8c8c', marginTop: 2 }}>
                SKU：{c.product_sku || '-'}
              </div>
            </div>
          </div>
        )
      },
    },
    {
      title: '产品状态',
      dataIndex: 'product_status',
      key: 'product_status',
      width: 100,
      render: (v: string | null) => <Tag color="blue">{masterStatusLabel(v)}</Tag>,
    },
    {
      title: '候选状态',
      dataIndex: 'candidate_status',
      key: 'candidate_status',
      width: 100,
      render: (v: string | null) => <Tag color={candStatusCode(v)}>{candStatusLabel(v)}</Tag>,
    },
    {
      title: '关联原因',
      dataIndex: 'link_reason',
      key: 'link_reason',
      ellipsis: true,
      render: (v: string | null) => (v ? <Text>{v}</Text> : <Text type="secondary">-</Text>),
    },
    {
      title: '关联时间',
      dataIndex: 'linked_at',
      key: 'linked_at',
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
      render: (_: unknown, c: OpportunityCandidateOut) => (
        <Button
          size="small"
          danger
          icon={<DeleteOutlined />}
          loading={unlinking}
          onClick={() => handleUnlink(c)}
        >
          解除
        </Button>
      ),
    },
  ]

  const renderCandidatesTab = (o: OpportunityDetail): React.ReactElement => (
    <div>
      <Alert
        type="info"
        showIcon
        icon={<InfoCircleOutlined />}
        style={{ marginBottom: 16 }}
        message="端点"
        description={
          <span>
            关联：<Text code>POST /api/v1/opportunities/{'{id}'}/candidates</Text> ·
            解除：<Text code>DELETE /api/v1/opportunities/{'{id}'}/candidates/{'{product_id}'}</Text>
            。关联不影响候选的 <Text code>candidate_status</Text>，仅建立多对多归属关系。
          </span>
        }
      />
      <div style={{ marginBottom: 12 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={openLinkModal}>
          关联产品
        </Button>
        <Text type="secondary" style={{ marginLeft: 12 }}>
          已关联 {o.candidates.length} 个候选
        </Text>
      </div>
      <Table
        columns={candidateColumns}
        dataSource={o.candidates}
        rowKey="id"
        size="small"
        pagination={false}
        locale={{ emptyText: <Empty description="暂无关联候选" /> }}
      />
    </div>
  )

  // ---------------------------------------------------------------------------
  // 详情 Tab：信号与证据
  // ---------------------------------------------------------------------------
  const renderSignalsTab = (o: OpportunityDetail): React.ReactElement => (
    <div>
      <Alert
        type="info"
        showIcon
        icon={<InfoCircleOutlined />}
        style={{ marginBottom: 16 }}
        message="端点"
        description={
          <span>
            信号与证据字段由机会实体自身承载，通过
            <Text code>GET /api/v1/opportunities/{'{id}'}</Text> 返回。以可读 JSON 展示，
            未做任何模拟填充。
          </span>
        }
      />
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card
            size="small"
            title={
              <Space>
                <DatabaseOutlined />
                <span>信号源（signal_source）</span>
              </Space>
            }
          >
            <JsonBlock data={o.signal_source} emptyHint="未记录信号源" />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card
            size="small"
            title={
              <Space>
                <CompassOutlined />
                <span>市场信号（market_signals）</span>
              </Space>
            }
          >
            <JsonBlock data={o.market_signals} emptyHint="空数组" />
          </Card>
        </Col>
        <Col xs={24}>
          <Card
            size="small"
            title={
              <Space>
                <FileTextOutlined />
                <span>证据（evidence）</span>
              </Space>
            }
          >
            <JsonBlock data={o.evidence} emptyHint="空数组" />
          </Card>
        </Col>
      </Row>
    </div>
  )

  // ---------------------------------------------------------------------------
  // 渲染
  // ---------------------------------------------------------------------------
  return (
    <div style={{ padding: 24, maxWidth: 1400, margin: '0 auto' }}>
      {/* 顶部：阶段② label + description */}
      <div style={{ marginBottom: 20 }}>
        <Space align="center" size="middle" wrap>
          <FireOutlined style={{ fontSize: 28, color: '#fa541c' }} />
          <div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
              <Title level={3} style={{ margin: 0 }}>
                {stage?.label ?? '机会池'}
              </Title>
              <Tag color="orange">生命周期阶段 ② · {stage?.n ?? 2}</Tag>
            </div>
            <Text type="secondary">
              {stage?.description ?? '将市场信号聚合为可查询、可引用、可追溯的机会实体'}
            </Text>
          </div>
        </Space>
        <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
          机会是市场信号的归属实体：把「搜索趋势 / 竞品缺口 / 评论痛点 / 社媒讨论」等信号聚合为一等公民，
          作为候选产品可追溯的来路。
        </Paragraph>
      </div>

      {/* 后端依赖 Alert：枚举字典不可达 */}
      {metaError && !meta && (
        <Alert
          type="warning"
          showIcon
          icon={<ExclamationCircleOutlined />}
          style={{ marginBottom: 16 }}
          message="枚举字典不可达"
          description={
            <span>
              依赖端点 <Text code>GET /api/v1/opportunities/meta</Text>（返回
              <Text code>{'{ statuses, signal_types }'}</Text>）。当前调用失败：{metaError}。
              页面的状态与信号类型下拉需要该端点返回的枚举值，故暂不可交互；
              本页面不做任何模拟数据填充，错误一律通过 message.error 提示。
            </span>
          }
        />
      )}

      {/* 后端依赖 Alert：列表不可达 */}
      {listError && (
        <Alert
          type="error"
          showIcon
          icon={<ExclamationCircleOutlined />}
          style={{ marginBottom: 16 }}
          message="后端不可达"
          description={
            <span>
              机会列表依赖 <Text code>GET /api/v1/opportunities</Text>
              （query: <Text code>status</Text> / <Text code>category</Text> /
              <Text code>limit</Text> / <Text code>offset</Text>），
              当前调用失败：{listError}。本页面不使用任何模拟数据。
            </span>
          }
        />
      )}

      {/* 工具栏 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap size="middle">
          <Tooltip title="按标题 / 分类 / 描述 / 关键词模糊搜索（前端过滤）">
            <Input
              placeholder="搜索标题 / 分类 / 描述 / 关键词"
              prefix={<SearchOutlined />}
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              allowClear
              style={{ width: 260 }}
            />
          </Tooltip>
          <Space size={4}>
            <FilterOutlined style={{ color: '#8c8c8c' }} />
            <Select
              value={filterStatus}
              onChange={setFilterStatus}
              options={statusFilterOptions}
              style={{ width: 160 }}
              placeholder="按状态筛选"
              allowClear
              disabled={!meta}
            />
            <Select
              value={filterSignalType}
              onChange={setFilterSignalType}
              options={signalFilterOptions}
              style={{ width: 170 }}
              placeholder="按信号类型筛选"
              allowClear
              disabled={!meta}
            />
            <Select
              value={filterCategory}
              onChange={setFilterCategory}
              options={categoryOptions}
              style={{ width: 150 }}
              placeholder="按分类筛选"
              allowClear
            />
          </Space>
          <Button icon={<ReloadOutlined />} onClick={loadList} loading={listLoading}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新建机会
          </Button>
        </Space>
      </Card>

      {/* 主表 */}
      <Card size="small">
        <Table
          columns={columns}
          dataSource={filtered}
          rowKey="id"
          loading={listLoading}
          scroll={{ x: 1200 }}
          pagination={{
            defaultPageSize: 10,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (t) => `共 ${t} 条机会`,
          }}
          locale={
            listError
              ? { emptyText: <Empty description="后端不可达，无法读取机会列表" /> }
              : filtered.length === 0
                ? {
                    emptyText: (
                      <Empty
                        description={
                          keyword || filterStatus || filterSignalType || filterCategory
                            ? '当前筛选条件下无机会'
                            : '暂无机会，可点击「新建机会」创建第一条'
                        }
                      />
                    ),
                  }
                : undefined
          }
        />
      </Card>

      {/* 新建机会弹窗 */}
      <Modal
        title={
          <Space>
            <BulbOutlined />
            <span>新建机会</span>
          </Space>
        }
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={handleCreate}
        confirmLoading={createLoading}
        okText="创建"
        cancelText="取消"
        destroyOnClose
        width={640}
      >
        <Form
          form={createForm}
          layout="vertical"
          initialValues={{ signal_type: 'manual', keywords: [] }}
        >
          <Form.Item
            name="title"
            label="标题"
            rules={[
              { required: true, message: '请输入标题' },
              { min: 1, max: 128, message: '标题长度 1-128' },
            ]}
          >
            <Input placeholder="一句话概括这个市场机会" maxLength={128} showCount autoFocus />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <TextArea rows={3} placeholder="机会的详细描述（选填）" maxLength={2000} showCount />
          </Form.Item>
          <Row gutter={16}>
            <Col xs={24} sm={12}>
              <Form.Item name="category" label="分类">
                <Input placeholder="如：露营装备、户外照明（选填）" maxLength={128} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item name="signal_type" label="信号类型">
                <Select
                  options={signalFilterOptions}
                  placeholder="选择信号类型（默认 manual）"
                  disabled={!meta}
                />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col xs={24} sm={12}>
              <Form.Item name="keywords" label="关键词">
                <Select
                  mode="tags"
                  placeholder="回车添加关键词（可选）"
                  tokenSeparators={[',', ' ', '、']}
                />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item
                name="confidence"
                label="置信度（0-100）"
                rules={[
                  {
                    type: 'number',
                    min: 0,
                    max: 100,
                    message: '置信度必须在 0-100 之间',
                  },
                ]}
              >
                <InputNumber
                  min={0}
                  max={100}
                  step={1}
                  placeholder="0-100（选填）"
                  style={{ width: '100%' }}
                />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      {/* 详情抽屉 */}
      <Drawer
        title={
          current ? (
            <Space align="center" wrap>
              <FireOutlined style={{ color: '#fa541c' }} />
              <span style={{ fontWeight: 600 }}>{current.title}</span>
              <Tag color={statusColor(current.status)}>{statusLabel(current.status)}</Tag>
              <Tag color={signalColor(current.signal_type)}>
                <CompassOutlined /> {signalLabel(current.signal_type)}
              </Tag>
            </Space>
          ) : (
            '机会详情'
          )
        }
        open={detailOpen}
        onClose={() => {
          setDetailOpen(false)
          setCurrent(null)
          setDetailError(null)
        }}
        width={880}
        extra={
          current ? (
            <Space>
              <Text type="secondary" style={{ fontSize: 12 }}>
                关联候选 {current.candidate_count} 个
              </Text>
              <Button icon={<ReloadOutlined />} onClick={refreshDetail} size="small">
                刷新
              </Button>
            </Space>
          ) : null
        }
      >
        {detailLoading && (
          <div style={{ textAlign: 'center', padding: '80px 0' }}>
            <Spin size="large" />
            <Paragraph type="secondary" style={{ marginTop: 12 }}>
              加载机会详情中…
            </Paragraph>
          </div>
        )}

        {!detailLoading && detailError && (
          <Alert
            type="error"
            showIcon
            icon={<ExclamationCircleOutlined />}
            message="加载详情失败"
            description={detailError}
          />
        )}

        {!detailLoading && !detailError && current && (
          <Tabs
            activeKey={detailTab}
            onChange={setDetailTab}
            items={[
              {
                key: 'info',
                label: (
                  <Space>
                    <ProfileOutlined />
                    <span>基本信息</span>
                  </Space>
                ),
                children: renderInfoTab(current),
              },
              {
                key: 'status',
                label: (
                  <Space>
                    <EditOutlined />
                    <span>状态</span>
                  </Space>
                ),
                children: renderStatusTab(current),
              },
              {
                key: 'candidates',
                label: (
                  <Space>
                    <LinkOutlined />
                    <span>关联候选（{current.candidates.length}）</span>
                  </Space>
                ),
                children: renderCandidatesTab(current),
              },
              {
                key: 'signals',
                label: (
                  <Space>
                    <SolutionOutlined />
                    <span>信号与证据</span>
                  </Space>
                ),
                children: renderSignalsTab(current),
              },
            ]}
          />
        )}
      </Drawer>

      {/* 关联产品弹窗 */}
      <Modal
        title={
          <Space>
            <LinkOutlined />
            <span>关联产品</span>
          </Space>
        }
        open={linkOpen}
        onCancel={() => setLinkOpen(false)}
        onOk={handleLink}
        confirmLoading={linkLoading}
        okText="关联"
        cancelText="取消"
        destroyOnClose
        width={560}
      >
        {current && (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message="目标机会"
            description={<Text strong>{current.title}</Text>}
          />
        )}
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="端点"
          description={
            <span>
              产品列表：<Text code>GET /api/v1/products</Text> ·
              关联：<Text code>POST /api/v1/opportunities/{'{id}'}/candidates</Text>
            </span>
          }
        />
        {productsError && (
          <Alert
            type="error"
            showIcon
            style={{ marginBottom: 16 }}
            message="加载产品失败"
            description={productsError}
          />
        )}
        <Form form={linkForm} layout="vertical">
          <Form.Item
            name="product_id"
            label="选择产品"
            rules={[{ required: true, message: '请选择一个产品' }]}
          >
            <Select
              showSearch
              placeholder="选择要关联的产品"
              loading={productsLoading}
              optionFilterProp="label"
              options={products.map((p) => ({
                value: p.id,
                label: `${p.sku} · ${p.name}`,
              }))}
              notFoundContent={
                productsLoading ? '加载中…' : productsError ? '加载失败' : '暂无产品'
              }
            />
          </Form.Item>
          <Form.Item
            name="link_reason"
            label="关联理由（link_reason，选填）"
            rules={[{ max: 256, message: '最长 256 字' }]}
          >
            <TextArea
              rows={2}
              placeholder="例如：与本次搜索趋势高度相关"
              maxLength={256}
              showCount
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
