/**
 * Product Master — 生命周期阶段 ⑨⑪ 单一详情视图。
 *
 * ADR IDENTITY-002 §5：`Products` + `ProductListing` → `ProductMaster`。
 * 硬约束：**不建 Product Master 独立表**，沿用 `products` 单表 + 三轴正交：
 *   - `products.candidate_status` 候选漏斗（NULL = 下游渠道商品）
 *   - `products.status`           商业执行状态（draft/active/inactive/listed/pending）
 *   - `products.meta.woocommerce_id` 渠道映射（ProductOut 不返回顶层，见 wcIdOf）
 *
 * 本页所有数据来自真实 `/api/v1/...`。后端能力缺失（无 create/update/delete、无库存端点）
 * 时渲染显式「后端未接入」契约态，禁止 mock、禁止假装保存成功。
 */

import { useState, useEffect, useMemo } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Input, Select,
  Statistic, Row, Col, Drawer, Tabs, Descriptions, Alert,
  Spin, Empty, Divider, Tooltip, Upload, Modal, message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { api } from '../api/client'
import {
  FileTextOutlined, SearchOutlined, ReloadOutlined, ShopOutlined,
  SyncOutlined, CheckCircleOutlined, ExclamationCircleOutlined,
  StopOutlined, EyeOutlined, ThunderboltOutlined, DatabaseOutlined,
  DownloadOutlined, UploadOutlined, LinkOutlined, SendOutlined,
  WarningOutlined, ClockCircleOutlined, FormOutlined,
} from '@ant-design/icons'
import ProductTimeline from '../components/lifecycle/ProductTimeline'
import { STAGE_BY_ID } from '../lifecycle/stages'
import { getProductImageUrl } from '../utils/productImage'

const { Title, Text, Paragraph } = Typography

// ---------------------------------------------------------------------------
// Types — 与后端 `app/schemas/product.py::ProductOut` 对齐
// ---------------------------------------------------------------------------

interface Product {
  id: string
  workspace_id?: string
  sku: string
  name: string
  description?: string | null
  category?: string | null
  brand?: string | null
  status: string
  candidate_status?: string | null
  source?: string
  source_url?: string | null
  tags?: Array<string | number>
  attributes?: Record<string, unknown>
  meta?: Record<string, unknown> | null
  weight_kg?: number | string | null
  dimensions?: Record<string, unknown> | null
  target_market?: string
  /** 兼容旧数据：ProductOut 不返回顶层，权威位置在 meta.woocommerce_id */
  woocommerce_id?: number
  /** 兼容旧数据：ProductOut 不含 stock_quantity，仅保留读取 */
  stock_quantity?: number
  created_at: string
  updated_at: string
}

interface GateReason { code: string; message: string }

interface GatePreview {
  gate: 'passed' | 'needs_review' | 'blocked'
  reasons: GateReason[]
  hard: boolean
  forceable: boolean
  product_id: string
  sku: string
  name: string
  candidate_status: string | null
  product_status: string
}

interface PushErrorDetail {
  status: number
  detail: {
    gate?: string
    gate_reasons?: GateReason[]
    forceable?: boolean
    message?: string
  }
}

interface CopyResult {
  title?: string
  description?: string
  short_description?: string
  bullet_points?: string[]
  seo_keywords?: string[]
  _meta?: { model?: string; tokens?: { total_tokens?: number }; cost?: string | number }
}

// ---------------------------------------------------------------------------
// WC ID 读取（ProductOut 权威位置是 meta.woocommerce_id）
// ---------------------------------------------------------------------------

const wcIdOf = (p: Product): number | undefined =>
  (p.woocommerce_id as number | undefined) ?? (p.meta?.woocommerce_id as number | undefined)

const wcUrlOf = (p: Product): string | undefined =>
  (p.meta?.woocommerce_url as string | undefined)

// ---------------------------------------------------------------------------
// 展示映射
// ---------------------------------------------------------------------------

const statusColors: Record<string, string> = {
  active: 'green',
  inactive: 'default',
  draft: 'orange',
  listed: 'blue',
  pending: 'purple',
}
const statusText: Record<string, string> = {
  active: '上架',
  inactive: '下架',
  draft: '草稿',
  listed: '已上架',
  pending: '待处理',
}
const candidateText: Record<string, string> = {
  candidate: '候选中',
  approved: '已批准',
  testing: '测试中',
  winner: '已胜出',
  rejected: '已拒绝',
}

const gateReasonLabels: Record<string, string> = {
  missing_sku: '缺 SKU',
  cjk_without_localization: '中文文案无英文本地化',
  missing_price: '缺价格',
  unapproved_candidate: '候选未批准',
  cjk_in_approved_copy: '已批准文案含 CJK',
  unapproved_copy: '英文文案未批准',
  thin_copy: '文案过短',
}

const candidateOptions = [
  { value: 'all', label: '全部候选状态' },
  { value: 'null', label: '渠道导入（NULL）' },
  { value: 'candidate', label: '候选中' },
  { value: 'approved', label: '已批准' },
  { value: 'testing', label: '测试中' },
  { value: 'winner', label: '已胜出' },
  { value: 'rejected', label: '已拒绝' },
]

const statusOptions = [
  { value: 'all', label: '全部状态' },
  { value: 'active', label: '上架' },
  { value: 'draft', label: '草稿' },
  { value: 'inactive', label: '下架' },
  { value: 'listed', label: '已上架' },
  { value: 'pending', label: '待处理' },
]

// ---------------------------------------------------------------------------
// CSV 辅助
// ---------------------------------------------------------------------------

const CSV_COLUMNS = [
  'sku', 'name', 'description', 'category', 'brand', 'tags',
  'attributes', 'source_url', 'supplier_code',
]

const escapeCsv = (v: unknown): string => {
  if (v == null) return '""'
  const s = typeof v === 'string' ? v : JSON.stringify(v)
  return `"${s.replace(/"/g, '""')}"`
}

// ---------------------------------------------------------------------------
// 组件
// ---------------------------------------------------------------------------

export default function ProductMaster() {
  // === 列表状态 ===
  const [products, setProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(false)
  const [searchText, setSearchText] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [candidateFilter, setCandidateFilter] = useState<string>('all')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])

  // === 详情 Drawer ===
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerProduct, setDrawerProduct] = useState<Product | null>(null)
  const [activeTab, setActiveTab] = useState<string>('info')

  // === 闸门预览（打开 Drawer 时拉取） ===
  const [gate, setGate] = useState<GatePreview | null>(null)
  const [gateLoading, setGateLoading] = useState(false)
  const [gateError, setGateError] = useState<string | null>(null)

  // === AI 文案 ===
  const [copyResult, setCopyResult] = useState<CopyResult | null>(null)
  const [copyLoading, setCopyLoading] = useState(false)

  // === 推送 ===
  const [pushing, setPushing] = useState(false)
  const [pushResult, setPushResult] = useState<Record<string, any> | null>(null)
  const [pushError, setPushError] = useState<PushErrorDetail | null>(null)

  // === 批量 / 同步 / 导入 ===
  const [batchPushing, setBatchPushing] = useState(false)
  const [wcSyncing, setWcSyncing] = useState(false)
  const [csvUploading, setCsvUploading] = useState(false)

  // 阶段定义（禁止硬编码阶段数组）
  const masterStage = STAGE_BY_ID.get('master')
  const wcSyncStage = STAGE_BY_ID.get('wc_sync')

  // ---------------------------------------------------------------------
  // 数据加载
  // ---------------------------------------------------------------------

  const loadProducts = async () => {
    try {
      setLoading(true)
      const params = new URLSearchParams({
        limit: String(pageSize),
        offset: String((page - 1) * pageSize),
      })
      if (statusFilter !== 'all') params.append('status', statusFilter)
      const token = localStorage.getItem('admin_token') || ''
      const headers: HeadersInit = {}
      if (token) headers['Authorization'] = `Bearer ${token}`
      const resp = await fetch(`/api/v1/products?${params}`, { headers })
      if (!resp.ok) {
        message.error(`加载产品列表失败：${resp.statusText}`)
        return
      }
      const data = await resp.json()
      setProducts(Array.isArray(data) ? data : [])
    } catch (e: any) {
      message.error(`加载产品列表失败：${e.message || '网络错误'}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadProducts()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize, statusFilter])

  // 前端过滤（searchText + candidateFilter 走客户端）
  const filtered = useMemo(() => {
    const term = searchText.trim().toLowerCase()
    return products.filter((p) => {
      const matchSearch =
        !term ||
        (p.name || '').toLowerCase().includes(term) ||
        (p.sku || '').toLowerCase().includes(term) ||
        (p.category || '').toLowerCase().includes(term)
      const matchCandidate =
        candidateFilter === 'all' ||
        (candidateFilter === 'null' ? p.candidate_status == null : p.candidate_status === candidateFilter)
      return matchSearch && matchCandidate
    })
  }, [products, searchText, candidateFilter])

  const stats = useMemo(() => ({
    total: products.length,
    active: products.filter((p) => p.status === 'active').length,
    draft: products.filter((p) => p.status === 'draft').length,
    synced: products.filter((p) => Boolean(wcIdOf(p))).length,
  }), [products])

  // ---------------------------------------------------------------------
  // Drawer / Gate
  // ---------------------------------------------------------------------

  const openDetailInTab = (product: Product, tab: string = 'info') => {
    setDrawerProduct(product)
    setDrawerOpen(true)
    setActiveTab(tab)
    setGate(null)
    setGateError(null)
    setCopyResult(null)
    setPushResult(null)
    setPushError(null)
    loadGate(product.id)
  }

  const closeDrawer = () => {
    setDrawerOpen(false)
    setDrawerProduct(null)
    setGate(null)
    setGateError(null)
    setCopyResult(null)
    setPushResult(null)
    setPushError(null)
  }

  const loadGate = async (productId: string) => {
    try {
      setGateLoading(true)
      setGateError(null)
      const gateToken = localStorage.getItem('admin_token') || ''
      const gateHeaders: HeadersInit = {}
      if (gateToken) gateHeaders['Authorization'] = `Bearer ${gateToken}`
      const resp = await fetch(`/api/v1/products/${productId}/listing-gate`, { headers: gateHeaders })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}))
        setGateError(typeof err.detail === 'string' ? err.detail : resp.statusText)
        return
      }
      const data = await resp.json()
      setGate(data)
    } catch (e: any) {
      setGateError(e.message || '网络错误')
    } finally {
      setGateLoading(false)
    }
  }

  // ---------------------------------------------------------------------
  // 工具栏动作
  // ---------------------------------------------------------------------

  const handleWcSync = async () => {
    try {
      setWcSyncing(true)
      message.loading({ content: '正在从 WooCommerce 反向同步…', key: 'wc-sync' })
      const syncToken = localStorage.getItem('admin_token') || ''
      const syncHeaders: HeadersInit = { 'Content-Type': 'application/json' }
      if (syncToken) syncHeaders['Authorization'] = `Bearer ${syncToken}`
      const resp = await fetch('/api/v1/products/sync-woocommerce', { method: 'POST', headers: syncHeaders })
      const data = await resp.json().catch(() => ({}))
      if (resp.ok) {
        const created = data.created ?? data.imported ?? 0
        const updated = data.updated ?? 0
        message.success({
          content: `反向同步完成：新增 ${created} / 更新 ${updated}`,
          key: 'wc-sync',
        })
        loadProducts()
      } else {
        message.error({
          content: `反向同步失败：${data.detail || resp.statusText}`,
          key: 'wc-sync',
        })
      }
    } catch (e: any) {
      message.error({ content: `反向同步失败：${e.message}`, key: 'wc-sync' })
    } finally {
      setWcSyncing(false)
    }
  }

  const handleBatchPush = async () => {
    const ids = selectedRowKeys.map((k) => String(k))
    if (ids.length === 0) return
    try {
      setBatchPushing(true)
      message.loading({ content: `批量推送 ${ids.length} 个产品…`, key: 'batch-push' })
      const pushToken = localStorage.getItem('admin_token') || ''
      const pushHeaders: HeadersInit = { 'Content-Type': 'application/json' }
      if (pushToken) pushHeaders['Authorization'] = `Bearer ${pushToken}`
      const resp = await fetch('/api/v1/products/push-woocommerce', {
        method: 'POST',
        headers: pushHeaders,
        body: JSON.stringify({ product_ids: ids }),
      })
      const data = await resp.json().catch(() => ({}))
      if (resp.ok) {
        const success = data.success ?? data.pushed ?? 0
        const failed = data.failed ?? 0
        message.success({
          content: `批量推送完成：成功 ${success} / 失败 ${failed}`,
          key: 'batch-push',
        })
        setSelectedRowKeys([])
        loadProducts()
      } else {
        message.error({
          content: `批量推送失败：${data.detail || resp.statusText}`,
          key: 'batch-push',
        })
      }
    } catch (e: any) {
      message.error({ content: `批量推送失败：${e.message}`, key: 'batch-push' })
    } finally {
      setBatchPushing(false)
    }
  }

  const handleCsvImport = async (file: File) => {
    if (file.size > 5 * 1024 * 1024) {
      message.error('CSV 文件不能超过 5 MiB')
      return
    }
    setCsvUploading(true)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const resp = await fetch('/api/v1/products/import', { method: 'POST', body: fd })
      const data = await resp.json().catch(() => ({}))
      if (resp.ok) {
        message.success(
          `导入完成：新增 ${data.imported ?? 0} / 更新 ${data.updated ?? 0} / 失败 ${data.failed ?? 0}`,
        )
        if (Array.isArray(data.errors) && data.errors.length > 0) {
          Modal.warning({
            title: '部分行导入失败',
            content: (
              <div style={{ maxHeight: 300, overflow: 'auto', fontSize: 12 }}>
                {data.errors.map((e: any, i: number) => (
                  <div key={i} style={{ padding: '2px 0', borderLeft: '2px solid #faad14', paddingLeft: 8 }}>
                    <Text type="secondary">第 {e.row} 行：</Text>{e.message}
                  </div>
                ))}
              </div>
            ),
          })
        }
        loadProducts()
      } else {
        message.error(`导入失败：${data.detail || resp.statusText}`)
      }
    } catch (e: any) {
      message.error(`导入失败：${e.message || '网络错误'}`)
    } finally {
      setCsvUploading(false)
    }
  }

  const handleExportCsv = () => {
    const header = [
      'sku', 'name', 'category', 'brand', 'status', 'candidate_status',
      'source_url', 'supplier_code', 'woocommerce_id', 'stock_quantity', 'created_at',
    ].join(',')
    const rows = products.map((p) => [
      escapeCsv(p.sku),
      escapeCsv(p.name),
      escapeCsv(p.category),
      escapeCsv(p.brand),
      escapeCsv(p.status),
      escapeCsv(p.candidate_status ?? ''),
      escapeCsv(p.source_url ?? ''),
      escapeCsv((p.meta?.supplier_code as string) ?? ''),
      escapeCsv(wcIdOf(p) ?? ''),
      escapeCsv(p.stock_quantity ?? 0),
      escapeCsv(p.created_at),
    ].join(','))
    const csv = [header, ...rows].join('\n')
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `products_${new Date().toISOString().split('T')[0]}.csv`
    link.click()
    URL.revokeObjectURL(link.href)
    message.success(`导出 ${products.length} 条产品`)
  }

  // ---------------------------------------------------------------------
  // Drawer 内动作：文案生成 / 推送
  // ---------------------------------------------------------------------

  const handleGenerateCopy = async () => {
    if (!drawerProduct) return
    try {
      setCopyLoading(true)
      const copyToken = localStorage.getItem('admin_token') || ''
      const copyHeaders: HeadersInit = {}
      if (copyToken) copyHeaders['Authorization'] = `Bearer ${copyToken}`
      const resp = await fetch(`/api/v1/products/${drawerProduct.id}/generate-copy`, {
        method: 'POST',
        headers: copyHeaders,
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}))
        message.error(`文案生成失败：${err.detail || resp.statusText}`)
        return
      }
      const data = await resp.json()
      setCopyResult(data)
      message.success('AI 文案生成成功')
    } catch (e: any) {
      message.error(`文案生成失败：${e.message || '网络错误'}`)
    } finally {
      setCopyLoading(false)
    }
  }

  const handlePush = async (force = false) => {
    if (!drawerProduct) return
    try {
      setPushing(true)
      setPushError(null)
      setPushResult(null)
      const pushToken = localStorage.getItem('admin_token') || ''
      const pushHeaders: HeadersInit = {}
      if (pushToken) pushHeaders['Authorization'] = `Bearer ${pushToken}`
      const url = force
        ? `/api/v1/products/${drawerProduct.id}/push-woocommerce?force=true`
        : `/api/v1/products/${drawerProduct.id}/push-woocommerce`
      const resp = await fetch(url, { method: 'POST', headers: pushHeaders })
      const data = await resp.json().catch(() => ({}))
      if (resp.ok) {
        setPushResult(data)
        message.success(`推送成功：${data.name || drawerProduct.name}`)
        loadProducts()
      } else if (resp.status === 409) {
        setPushError({ status: 409, detail: data.detail })
      } else if (resp.status === 422) {
        setPushError({ status: 422, detail: data.detail })
      } else {
        message.error(`推送失败：${data.detail || resp.statusText}`)
      }
    } catch (e: any) {
      message.error(`推送失败：${e.message || '网络错误'}`)
    } finally {
      setPushing(false)
    }
  }

  const confirmForcePush = () => {
    Modal.confirm({
      title: '强制放行确认',
      content: '闸门返回 needs_review。你已完成人工复核？确认强制推送到 WooCommerce？',
      okText: '我已人工复核，强制放行',
      cancelText: '取消',
      onOk: () => handlePush(true),
    })
  }

  // ---------------------------------------------------------------------
  // 闸门裁决展示（复用于「闸门预览」与「发布」两个 Tab）
  // ---------------------------------------------------------------------

  const renderGateResult = (g: GatePreview) => {
    const passed = g.gate === 'passed'
    const needsReview = g.gate === 'needs_review'
    const blocked = g.gate === 'blocked'
    return (
      <div>
        <Alert
          type={passed ? 'success' : needsReview ? 'warning' : 'error'}
          showIcon
          icon={passed ? <CheckCircleOutlined /> : needsReview ? <ExclamationCircleOutlined /> : <StopOutlined />}
          message={
            <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
              <Text strong>
                闸门裁决：{passed ? '通过' : needsReview ? '需人工复核' : '硬阻断'}
              </Text>
              <Tag icon={<ThunderboltOutlined />}>hard: {String(g.hard)}</Tag>
              <Tag>forceable: {String(g.forceable)}</Tag>
            </div>
          }
          description={
            blocked
              ? '硬阻断不可强制放行。请补齐必填字段（SKU、英文本地化）后重试。'
              : needsReview
                ? '以下条目需要人工复核。复核完成后可在「发布」页点击「我已人工复核，强制放行」带 force=true 重试。'
                : '闸门通过，可以直接推送到 WooCommerce。'
          }
        />
        {g.reasons.length > 0 && (
          <Card size="small" title={`原因明细（${g.reasons.length}）`} style={{ marginTop: 12 }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {g.reasons.map((r, i) => (
                <div key={i} style={{ padding: '8px 10px', background: '#fafafa', borderRadius: 4 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <Tag color="orange">{gateReasonLabels[r.code] || r.code}</Tag>
                    <Text code style={{ fontSize: 11 }}>{r.code}</Text>
                  </div>
                  <div style={{ marginTop: 4, fontSize: 12 }}>{r.message}</div>
                </div>
              ))}
            </div>
          </Card>
        )}
      </div>
    )
  }

  // ---------------------------------------------------------------------
  // 表格列定义
  // ---------------------------------------------------------------------

  const columns: ColumnsType<Product> = [
    {
      title: '图片',
      key: 'image',
      width: 70,
      align: 'center' as const,
      render: (_: unknown, p: Product) => {
        const imageUrl = getProductImageUrl(p)
        if (!imageUrl) {
          return (
            <div style={{ width: 60, height: 60, background: '#f5f5f5', borderRadius: 4, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#999', fontSize: 10 }}>
              无图
            </div>
          )
        }
        return (
          <img 
            src={imageUrl} 
            alt={p.name} 
            style={{ width: 60, height: 60, objectFit: 'cover', borderRadius: 4, border: '1px solid #f0f0f0' }}
            onError={(e) => { e.currentTarget.style.display = 'none' }}
          />
        )
      },
    },
    {
      title: '产品',
      key: 'product',
      width: 240,
      render: (_: unknown, p: Product) => (
        <div>
          <div style={{ fontWeight: 500 }}>{p.name}</div>
          <div style={{ color: '#999', fontSize: 12 }}>SKU: {p.sku}</div>
        </div>
      ),
    },
    {
      title: '分类',
      dataIndex: 'category',
      width: 120,
      render: (v: string | null) => v || <Text type="secondary">-</Text>,
    },
    {
      title: '来源',
      dataIndex: 'source',
      width: 90,
      render: (v: string | undefined) => v || <Text type="secondary">-</Text>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (s: string) => (
        <Tag color={statusColors[s] || 'default'}>{statusText[s] || s}</Tag>
      ),
    },
    {
      title: '候选',
      dataIndex: 'candidate_status',
      width: 110,
      render: (cs: string | null) => {
        if (cs == null) return <Tag>渠道导入</Tag>
        return <Tag color="orange">{candidateText[cs] || cs}</Tag>
      },
    },
    {
      title: 'WC ID',
      key: 'wc_id',
      width: 110,
      render: (_: unknown, p: Product) => {
        const id = wcIdOf(p)
        if (!id) return <Text type="secondary">-</Text>
        const url = wcUrlOf(p)
        return url ? (
          <Tooltip title="点击打开 WC 商品页">
            <a href={url} target="_blank" rel="noopener noreferrer">
              <ShopOutlined /> #{id}
            </a>
          </Tooltip>
        ) : (
          <Tag color="blue"><ShopOutlined /> #{id}</Tag>
        )
      },
    },
    {
      title: '库存',
      dataIndex: 'stock_quantity',
      width: 90,
      render: (stock: number | undefined, p: Product) => {
        const qty = stock ?? ((p.attributes?.stock_quantity as number | undefined) ?? 0)
        if (qty === 0) return <Tag color="red">缺货</Tag>
        if (qty < 10) return <Tag color="orange">{qty}</Tag>
        return <Tag color="green">{qty}</Tag>
      },
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 130,
      render: (t: string) => (t ? new Date(t).toLocaleDateString() : '-'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 180,
      render: (_: unknown, p: Product) => (
        <Space size="small">
          <Button size="small" icon={<EyeOutlined />} onClick={() => openDetailInTab(p, 'info')}>
            详情
          </Button>
          <Button size="small" type="primary" icon={<SendOutlined />} onClick={() => openDetailInTab(p, 'publish')}>
            推送
          </Button>
        </Space>
      ),
    },
  ]

  // ---------------------------------------------------------------------
  // 渲染
  // ---------------------------------------------------------------------

  return (
    <div style={{ padding: 24, maxWidth: 1400, margin: '0 auto' }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: 20 }}>
        <Space align="start" size="middle">
          <FileTextOutlined style={{ fontSize: 32, color: '#722ed1', marginTop: 2 }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>Product Master</Title>
            <Text type="secondary">
              生命周期阶段 {masterStage?.n} · {masterStage?.label}
              {' + '}阶段 {wcSyncStage?.n} · {wcSyncStage?.label}
              ：文案生成 → 闸门预览 → 推 WooCommerce 在同一详情视图完成
            </Text>
          </div>
        </Space>
      </div>

      {/* 契约态说明：不建新表 + 后端能力缺口清单 */}
      <Alert
        type="info"
        showIcon
        icon={<DatabaseOutlined />}
        style={{ marginBottom: 16 }}
        message="数据模型与后端能力契约"
        description={
          <div style={{ fontSize: 13, lineHeight: 1.8 }}>
            <div>
              <Text strong>数据模型：</Text>
              不新建 Product Master 独立表，沿用 <Text code>products</Text> 单表 +
              三轴正交：<Text code>candidate_status</Text>（候选漏斗，NULL = 渠道导入）、
              <Text code>status</Text>（商业执行状态）、<Text code>meta.woocommerce_id</Text>（渠道映射）。
            </div>
            <div style={{ marginTop: 4 }}>
              <Text strong>后端已接入：</Text>
              <Text code>GET /api/v1/products</Text>、
              <Text code>POST /api/v1/products/import</Text>（CSV）、
              <Text code>POST /api/v1/products/sync-woocommerce</Text>、
              <Text code>POST /api/v1/products/push-woocommerce</Text>（批量）、
              <Text code>POST /api/v1/products/{'{id}'}/push-woocommerce</Text>（单个，可 force）、
              <Text code>GET /api/v1/products/{'{id}'}/listing-gate</Text>（闸门预览）、
              <Text code>POST /api/v1/products/{'{id}'}/generate-copy</Text>（AI 文案）。
            </div>
            <div style={{ marginTop: 4 }}>
              <Text strong type="danger">后端未接入（无对应端点）：</Text>
              新增（<Text code>POST /</Text>）、编辑（<Text code>PUT/PATCH /{'{id}'}</Text>）、
              删除（<Text code>DELETE /{'{id}'}</Text>）、库存调整、
              mastered_at 时间标记。任何写操作请通过 <Text strong>CSV 导入</Text>（按 SKU upsert）完成，本页不渲染假「保存成功」。
            </div>
          </div>
        }
      />

      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small">
            <Statistic title="产品总数" value={stats.total} prefix={<FileTextOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="上架产品"
              value={stats.active}
              valueStyle={{ color: '#52c41a' }}
              prefix={<CheckCircleOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="草稿产品"
              value={stats.draft}
              valueStyle={{ color: '#fa8c16' }}
              prefix={<ClockCircleOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="已同步 WC"
              value={stats.synced}
              valueStyle={{ color: '#1890ff' }}
              prefix={<ShopOutlined />}
            />
          </Card>
        </Col>
      </Row>

      {/* 工具栏 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Input
            placeholder="搜索名称 / SKU / 分类"
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ width: 240 }}
            allowClear
          />
          <Select
            value={statusFilter}
            onChange={(v) => { setStatusFilter(v); setPage(1) }}
            style={{ width: 130 }}
            options={statusOptions}
          />
          <Select
            value={candidateFilter}
            onChange={setCandidateFilter}
            style={{ width: 160 }}
            options={candidateOptions}
          />
          <Button icon={<ReloadOutlined />} onClick={loadProducts} loading={loading}>刷新</Button>
          <Divider type="vertical" />
          <Upload
            accept=".csv"
            showUploadList={false}
            beforeUpload={(file) => {
              handleCsvImport(file as File)
              return false
            }}
          >
            <Button icon={<UploadOutlined />} loading={csvUploading}>CSV 导入</Button>
          </Upload>
          <Button icon={<DownloadOutlined />} onClick={handleExportCsv} disabled={products.length === 0}>
            导出 CSV
          </Button>
          <Button icon={<SyncOutlined />} onClick={handleWcSync} loading={wcSyncing}>
            WC 反向同步
          </Button>
          <Divider type="vertical" />
          <Button
            type="primary"
            icon={<SendOutlined />}
            loading={batchPushing}
            disabled={selectedRowKeys.length === 0}
            onClick={handleBatchPush}
          >
            批量推送 WC ({selectedRowKeys.length})
          </Button>
        </Space>
        <div style={{ marginTop: 8, fontSize: 12 }}>
          <Text type="secondary">
            CSV 列（UTF-8）：<Text code>{CSV_COLUMNS.join(', ')}</Text>；tags 用分号分隔；attributes 用 JSON 对象；supplier_code 须已在 suppliers 表中。
          </Text>
        </div>
      </Card>

      {/* 产品表格 */}
      <Card size="small">
        <Table<Product>
          columns={columns}
          dataSource={filtered}
          rowKey="id"
          loading={loading}
          rowSelection={{ selectedRowKeys, onChange: setSelectedRowKeys }}
          pagination={{
            current: page,
            pageSize,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (t) => `共 ${t} 条`,
            onChange: (p, ps) => { setPage(p); setPageSize(ps) },
          }}
          locale={{
            emptyText: <Empty description="暂无产品数据：点击「CSV 导入」或「WC 反向同步」载入" />,
          }}
        />
      </Card>

      {/* 详情 Drawer */}
      <Drawer
        title={drawerProduct ? `${drawerProduct.name} · ${drawerProduct.sku}` : '产品详情'}
        open={drawerOpen}
        onClose={closeDrawer}
        width={880}
        destroyOnClose
      >
        {drawerProduct && (
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            items={[
              {
                key: 'info',
                label: <span><FileTextOutlined /> 基本信息</span>,
                children: (
                  <div>
                    <ProductTimeline product={drawerProduct} style={{ marginBottom: 16 }} />

                    <Descriptions column={2} bordered size="small" style={{ marginBottom: 16 }}>
                      <Descriptions.Item label="产品名称" span={2}>{drawerProduct.name}</Descriptions.Item>
                      <Descriptions.Item label="SKU">{drawerProduct.sku}</Descriptions.Item>
                      <Descriptions.Item label="分类">{drawerProduct.category || '-'}</Descriptions.Item>
                      <Descriptions.Item label="品牌">{drawerProduct.brand || '-'}</Descriptions.Item>
                      <Descriptions.Item label="状态">
                        <Tag color={statusColors[drawerProduct.status] || 'default'}>
                          {statusText[drawerProduct.status] || drawerProduct.status}
                        </Tag>
                      </Descriptions.Item>
                      <Descriptions.Item label="候选状态">
                        {drawerProduct.candidate_status == null
                          ? <Tag>渠道导入</Tag>
                          : <Tag color="orange">{candidateText[drawerProduct.candidate_status] || drawerProduct.candidate_status}</Tag>}
                      </Descriptions.Item>
                      <Descriptions.Item label="来源">{drawerProduct.source || '-'}</Descriptions.Item>
                      <Descriptions.Item label="目标市场">{drawerProduct.target_market || '-'}</Descriptions.Item>
                      <Descriptions.Item label="WooCommerce ID">
                        {wcIdOf(drawerProduct) ? (
                          <Tag color="blue"><ShopOutlined /> #{wcIdOf(drawerProduct)}</Tag>
                        ) : (
                          <Text type="secondary">未同步</Text>
                        )}
                      </Descriptions.Item>
                      <Descriptions.Item label="库存">
                        {(() => {
                          const q = drawerProduct.stock_quantity ?? ((drawerProduct.attributes?.stock_quantity as number | undefined) ?? 0)
                          return (
                            <Text strong style={{ color: q === 0 ? '#ff4d4f' : q < 10 ? '#faad14' : '#52c41a' }}>
                              {q}
                            </Text>
                          )
                        })()}
                      </Descriptions.Item>
                      {drawerProduct.weight_kg != null && (
                        <Descriptions.Item label="重量（kg）">{String(drawerProduct.weight_kg)}</Descriptions.Item>
                      )}
                      <Descriptions.Item label="产品 ID">{drawerProduct.id}</Descriptions.Item>
                      <Descriptions.Item label="创建时间" span={2}>
                        {drawerProduct.created_at ? new Date(drawerProduct.created_at).toLocaleString() : '-'}
                      </Descriptions.Item>
                      <Descriptions.Item label="更新时间" span={2}>
                        {drawerProduct.updated_at ? new Date(drawerProduct.updated_at).toLocaleString() : '-'}
                      </Descriptions.Item>
                    </Descriptions>

                    {drawerProduct.description && (
                      <Card size="small" title="描述" style={{ marginBottom: 12 }}>
                        <Paragraph style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{drawerProduct.description}</Paragraph>
                      </Card>
                    )}

                    {drawerProduct.tags && drawerProduct.tags.length > 0 && (
                      <Card size="small" title="标签" style={{ marginBottom: 12 }}>
                        <Space wrap>
                          {drawerProduct.tags.map((t, i) => (
                            <Tag key={i} color="purple">{String(t)}</Tag>
                          ))}
                        </Space>
                      </Card>
                    )}

                    {drawerProduct.attributes && Object.keys(drawerProduct.attributes).length > 0 && (
                      <Card size="small" title="属性" style={{ marginBottom: 12 }}>
                        <Descriptions column={2} size="small">
                          {Object.entries(drawerProduct.attributes).map(([k, v]) => (
                            <Descriptions.Item key={k} label={k}>{String(v ?? '')}</Descriptions.Item>
                          ))}
                        </Descriptions>
                      </Card>
                    )}

                    {drawerProduct.meta && Object.keys(drawerProduct.meta).length > 0 && (
                      <Card size="small" title="Meta（关键字段）" style={{ marginBottom: 12 }}>
                        <Descriptions column={1} size="small">
                          {wcIdOf(drawerProduct) && (
                            <Descriptions.Item label="meta.woocommerce_id">#{wcIdOf(drawerProduct)}</Descriptions.Item>
                          )}
                          {wcUrlOf(drawerProduct) && (
                            <Descriptions.Item label="meta.woocommerce_url">
                              <a href={wcUrlOf(drawerProduct)} target="_blank" rel="noopener noreferrer">
                                <LinkOutlined /> {wcUrlOf(drawerProduct)}
                              </a>
                            </Descriptions.Item>
                          )}
                          {drawerProduct.meta?.localizations != null && (
                            <Descriptions.Item label="meta.localizations">
                              <pre style={{ margin: 0, fontSize: 12, whiteSpace: 'pre-wrap', wordBreak: 'break-all', background: '#fafafa', padding: 8, borderRadius: 4 }}>
                                {JSON.stringify(drawerProduct.meta.localizations, null, 2)}
                              </pre>
                            </Descriptions.Item>
                          )}
                        </Descriptions>
                      </Card>
                    )}

                    {drawerProduct.source_url && (
                      <div style={{ padding: '8px 0' }}>
                        <Text strong>来源链接：</Text>
                        <a
                          href={drawerProduct.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{ marginLeft: 8, display: 'block', marginTop: 4, wordBreak: 'break-all' }}
                        >
                          <LinkOutlined /> {drawerProduct.source_url}
                        </a>
                      </div>
                    )}

                    <Alert
                      type="warning"
                      showIcon
                      icon={<ExclamationCircleOutlined />}
                      message="本页不提供编辑 / 删除 / 库存调整"
                      description={
                        <div style={{ fontSize: 13 }}>
                          后端 <Text code>products.py</Text> 无 <Text code>POST ''</Text>、
                          <Text code>PUT/PATCH /{'{id}'}</Text>、<Text code>DELETE /{'{id}'}</Text>、无库存端点。
                          如需修改：编辑 CSV 中该 SKU 行（列：<Text code>{CSV_COLUMNS.join(', ')}</Text>）→ 用「CSV 导入」按 SKU upsert。
                        </div>
                      }
                      style={{ marginTop: 16 }}
                    />
                  </div>
                ),
              },
              {
                key: 'gate',
                label: <span><ThunderboltOutlined /> 闸门预览</span>,
                children: (
                  <div>
                    <Paragraph type="secondary" style={{ marginTop: 0 }}>
                      调用 <Text code>GET /api/v1/products/{'{id}'}/listing-gate</Text>，返回闸门裁决、原因、
                      <Text code>hard</Text> 与 <Text code>forceable</Text>。仅预览，不执行推送。
                    </Paragraph>

                    {gateLoading && (
                      <div style={{ textAlign: 'center', padding: 40 }}>
                        <Spin tip="正在加载闸门预览…" />
                      </div>
                    )}

                    {!gateLoading && gateError && (
                      <Alert
                        type="error"
                        showIcon
                        icon={<WarningOutlined />}
                        message="闸门预览加载失败"
                        description={gateError}
                      />
                    )}

                    {!gateLoading && !gateError && !gate && (
                      <Empty description="闸门数据为空" />
                    )}

                    {!gateLoading && !gateError && gate && renderGateResult(gate)}

                    {!gateLoading && gate && (
                      <Alert
                        type="info"
                        showIcon
                        style={{ marginTop: 16 }}
                        message="闸门 reason code 语义"
                        description={
                          <div style={{ fontSize: 12, lineHeight: 1.8 }}>
                            <div><Text code>missing_sku</Text> · 缺 SKU（硬阻断）</div>
                            <div><Text code>cjk_without_localization</Text> · 中文文案无英文本地化（硬阻断）</div>
                            <div><Text code>missing_price</Text> · 缺价格（可强制）</div>
                            <div><Text code>unapproved_candidate</Text> · candidate_status 未为 approved（可强制）</div>
                            <div><Text code>cjk_in_approved_copy</Text> · 已批准英文文案含 CJK（可强制）</div>
                            <div><Text code>unapproved_copy</Text> · meta.localizations.en.status 未为 approved（可强制）</div>
                            <div><Text code>thin_copy</Text> · 英文描述少于 600 字符（可强制）</div>
                          </div>
                        }
                      />
                    )}
                  </div>
                ),
              },
              {
                key: 'copy',
                label: <span><FormOutlined /> 文案</span>,
                children: (
                  <div>
                    <Alert
                      type="info"
                      showIcon
                      message="AI 文案生成"
                      description="调用 <Text code>POST /api/v1/products/{'{id}'}/generate-copy</Text> 生成英文标题、描述、卖点与 SEO 关键词。"
                      style={{ marginBottom: 12 }}
                    />
                    <Space style={{ marginBottom: 16 }}>
                      <Button
                        type="primary"
                        icon={<ThunderboltOutlined />}
                        loading={copyLoading}
                        onClick={handleGenerateCopy}
                      >
                        生成 AI 文案
                      </Button>
                    </Space>

                    {copyLoading && <Spin tip="正在生成文案…" />}

                    {!copyLoading && !copyResult && (
                      <Empty description="点击「生成 AI 文案」开始" />
                    )}

                    {!copyLoading && copyResult && (
                      <div>
                        <Descriptions column={1} size="small" style={{ marginBottom: 12 }}>
                          {copyResult.title && (
                            <Descriptions.Item label="英文标题">
                              <Space>
                                <span>{copyResult.title}</span>
                                <Tooltip title="复制">
                                  <Button
                                    size="small"
                                    icon={<LinkOutlined />}
                                    onClick={() => {
                                      navigator.clipboard.writeText(copyResult.title || '')
                                      message.success('已复制标题')
                                    }}
                                  />
                                </Tooltip>
                              </Space>
                            </Descriptions.Item>
                          )}
                          {copyResult.short_description && (
                            <Descriptions.Item label="简短描述">
                              <Space>
                                <span>{copyResult.short_description}</span>
                                <Tooltip title="复制">
                                  <Button
                                    size="small"
                                    icon={<LinkOutlined />}
                                    onClick={() => {
                                      navigator.clipboard.writeText(copyResult.short_description || '')
                                      message.success('已复制简短描述')
                                    }}
                                  />
                                </Tooltip>
                              </Space>
                            </Descriptions.Item>
                          )}
                          {copyResult._meta?.model && (
                            <Descriptions.Item label="生成元数据">
                              模型：{copyResult._meta.model} ·
                              Tokens：{copyResult._meta.tokens?.total_tokens ?? '?'} ·
                              成本：{copyResult._meta.cost ?? '-'}
                            </Descriptions.Item>
                          )}
                        </Descriptions>

                        {copyResult.description && (
                          <Card size="small" title="产品描述" style={{ marginBottom: 12 }}>
                            <Paragraph style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
                              {copyResult.description}
                            </Paragraph>
                          </Card>
                        )}

                        {copyResult.bullet_points && copyResult.bullet_points.length > 0 && (
                          <Card size="small" title="卖点" style={{ marginBottom: 12 }}>
                            <ul style={{ margin: 0, paddingLeft: 20 }}>
                              {copyResult.bullet_points.map((b, i) => (
                                <li key={i}>{b}</li>
                              ))}
                            </ul>
                          </Card>
                        )}

                        {copyResult.seo_keywords && copyResult.seo_keywords.length > 0 && (
                          <Card size="small" title="SEO 关键词">
                            <Space wrap>
                              {copyResult.seo_keywords.map((kw, i) => (
                                <Tag key={i} color="blue">{kw}</Tag>
                              ))}
                            </Space>
                          </Card>
                        )}
                      </div>
                    )}

                    <Alert
                      type="warning"
                      showIcon
                      icon={<ExclamationCircleOutlined />}
                      style={{ marginTop: 16 }}
                      message="写回限制（后端无更新端点）"
                      description={
                        <div style={{ fontSize: 13 }}>
                          后端 <Text code>products.py</Text> 无 <Text code>PUT/PATCH /{'{id}'}</Text>，
                          无法把生成的英文文案直接写入 <Text code>meta.localizations.en</Text>。
                          如需落库：（1）复制上方字段；（2）在 CSV 中修改该 SKU 行（<Text code>name</Text>、<Text code>description</Text>）；
                          （3）通过工具栏「CSV 导入」按 SKU upsert；（4）在闸门预览中会看到 <Text code>unapproved_copy</Text> / <Text code>cjk_without_localization</Text>，
                          需人工将 <Text code>meta.localizations.en.status</Text> 置为 <Text code>approved</Text>（亦需走 CSV）。
                        </div>
                      }
                    />
                  </div>
                ),
              },
              {
                key: 'publish',
                label: <span><SendOutlined /> 发布</span>,
                children: (
                  <div>
                    <Card size="small" title="闸门状态" style={{ marginBottom: 16 }}>
                      {gateLoading && <Spin />}
                      {!gateLoading && gate && renderGateResult(gate)}
                      {!gateLoading && !gate && gateError && (
                        <Alert type="error" showIcon icon={<WarningOutlined />} message={gateError} />
                      )}
                      {!gateLoading && !gate && !gateError && (
                        <Empty description="闸门数据为空" />
                      )}
                    </Card>

                    <Card size="small" title="推送操作" style={{ marginBottom: 16 }}>
                      <Paragraph type="secondary" style={{ marginTop: 0 }}>
                        调用 <Text code>POST /api/v1/products/{'{id}'}/push-woocommerce</Text>；
                        409 = 需人工复核（可带 <Text code>force=true</Text> 重试）；
                        422 = 硬阻断（不可放行）。
                      </Paragraph>
                      <Space wrap>
                        <Button
                          type="primary"
                          icon={<SendOutlined />}
                          loading={pushing}
                          disabled={gateLoading || gate?.gate === 'blocked'}
                          onClick={() => handlePush(false)}
                        >
                          推送到 WooCommerce
                        </Button>
                        {/* 按钮以 forceable 为准，而非仅看 409：cjk_in_approved_copy 这类
                            needs_review 原因不在 REVIEW_REQUIRED 内，后端 force=true 仍会拒绝，
                            仅按 409 显示按钮会造成点了必失败的死路。 */}
                        {pushError?.status === 409 && pushError.detail?.forceable === true && (
                          <Button danger icon={<SendOutlined />} loading={pushing} onClick={confirmForcePush}>
                            我已人工复核，强制放行
                          </Button>
                        )}
                      </Space>
                      {gate?.gate === 'blocked' && (
                        <Alert
                          type="error"
                          showIcon
                          icon={<StopOutlined />}
                          message="硬阻断（422）"
                          description="闸门 hard=true，无法通过 force 放行。请补齐必填字段（SKU / 英文本地化）后重试。"
                          style={{ marginTop: 12 }}
                        />
                      )}
                    </Card>

                    {pushError && (
                      <Alert
                        type={pushError.status === 422 ? 'error' : 'warning'}
                        showIcon
                        icon={pushError.status === 422 ? <StopOutlined /> : <ExclamationCircleOutlined />}
                        message={
                          pushError.status === 422
                            ? `硬阻断（HTTP ${pushError.status}）· 不可强制放行`
                            : `需人工复核（HTTP ${pushError.status}）· 可带 force=true 重试`
                        }
                        description={
                          <div>
                            {pushError.detail?.message && <div>{pushError.detail.message}</div>}
                            {pushError.detail?.forceable != null && (
                              <div style={{ marginTop: 4 }}>
                                <Text strong>forceable：</Text>
                                <Tag>{String(pushError.detail.forceable)}</Tag>
                              </div>
                            )}
                            {pushError.detail?.forceable === false && (
                              <div style={{ marginTop: 4 }}>
                                <Text strong>不可强制放行：</Text>
                                <Text type="secondary">
                                  以下原因不在可复核清单内（后端 force=true 会拒绝），需修正内容后重新推送。
                                </Text>
                              </div>
                            )}
                            {Array.isArray(pushError.detail?.gate_reasons) &&
                              pushError.detail.gate_reasons.length > 0 && (
                                <div style={{ marginTop: 8 }}>
                                  <Text strong>原因明细：</Text>
                                  <ul style={{ margin: '4px 0 0', paddingLeft: 20 }}>
                                    {pushError.detail.gate_reasons.map((r, i) => (
                                      <li key={i}>
                                        <Tag color="orange">{gateReasonLabels[r.code] || r.code}</Tag>
                                        <Text code style={{ fontSize: 11 }}>{r.code}</Text>
                                        {' — '}{r.message}
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                          </div>
                        }
                        style={{ marginBottom: 16 }}
                      />
                    )}

                    {pushResult && (
                      <Card size="small" title="推送成功">
                        <Descriptions column={2} size="small" bordered>
                          <Descriptions.Item label="产品">{pushResult.name || drawerProduct.name}</Descriptions.Item>
                          <Descriptions.Item label="SKU">{pushResult.sku || drawerProduct.sku}</Descriptions.Item>
                          <Descriptions.Item label="WooCommerce ID">
                            {pushResult.woocommerce_id ? (
                              <Tag color="green"><ShopOutlined /> #{pushResult.woocommerce_id}</Tag>
                            ) : (
                              <Text type="secondary">-</Text>
                            )}
                          </Descriptions.Item>
                          <Descriptions.Item label="动作">{pushResult.action || '-'}</Descriptions.Item>
                          <Descriptions.Item label="闸门">{pushResult.gate || '-'}</Descriptions.Item>
                          <Descriptions.Item label="已强制放行">
                            <Tag color={pushResult.forced ? 'orange' : 'default'}>
                              {String(pushResult.forced ?? false)}
                            </Tag>
                          </Descriptions.Item>
                          <Descriptions.Item label="已验证" span={2}>
                            {pushResult.verified ? (
                              <Tag color="green" icon={<CheckCircleOutlined />}>已验证</Tag>
                            ) : (
                              <Tag>未验证</Tag>
                            )}
                          </Descriptions.Item>
                          {pushResult.woocommerce_url && (
                            <Descriptions.Item label="WooCommerce 链接" span={2}>
                              <a
                                href={pushResult.woocommerce_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                style={{ wordBreak: 'break-all' }}
                              >
                                <LinkOutlined /> {pushResult.woocommerce_url}
                              </a>
                            </Descriptions.Item>
                          )}
                        </Descriptions>
                        <Button
                          icon={<ReloadOutlined />}
                          style={{ marginTop: 12 }}
                          onClick={() => loadGate(drawerProduct.id)}
                        >
                          重新加载闸门
                        </Button>
                      </Card>
                    )}
                  </div>
                ),
              },
            ]}
          />
        )}
      </Drawer>
    </div>
  )
}
