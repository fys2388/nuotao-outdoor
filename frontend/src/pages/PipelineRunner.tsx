import { useState, useEffect } from 'react'
import {
  Card, Button, Space, Typography, Steps, Tag, Alert, Row, Col,
  Spin, message, Input, Select, Descriptions, List, Empty, Progress, Statistic,
  Modal,
} from 'antd'
import {
  SearchOutlined, ReloadOutlined, RocketOutlined, PlayCircleOutlined,
  ThunderboltOutlined, CheckCircleOutlined, ExclamationCircleOutlined,
  ClockCircleOutlined, FileTextOutlined, PictureOutlined, ShopOutlined,
  DatabaseOutlined, ArrowRightOutlined, EyeOutlined, LinkOutlined,
  DeleteOutlined, SyncOutlined, SendOutlined, ImportOutlined,
} from '@ant-design/icons'
import ProductTimeline from '../components/lifecycle/ProductTimeline'
import { PIPELINE_STEPS, STAGE_BY_ID } from '../lifecycle/stages'

const { Title, Text, Paragraph } = Typography

/**
 * 管线运行器（ADR IDENTITY-002 §5）。
 *
 * 与 ProductPipeline 的区别：输入来自**候选池**（products 表 candidate_status ≠ null 的行），
 * 不再手填商品字段。1688 导入作为备选入口保留，但导入后仍走真实管线端点。
 *
 * 步骤定义从 `lifecycle/stages.ts::PIPELINE_STEPS` 取（禁止页面内硬编码）；
 * 阶段名从 `STAGE_BY_ID` 取。所有数据来自真实 `/api/v1/...` fetch，
 * 能力缺失时渲染显式「后端未接入」契约态。
 */

// 图标是渲染关注点，映射保留在本组件内（与 ProductPipeline.tsx 一致）
const STEP_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  input: FileTextOutlined,
  analysis: RocketOutlined,
  main_image: PictureOutlined,
  prompt: FileTextOutlined,
  listing_data: ShopOutlined,
  listing: ThunderboltOutlined,
}

// 闸门原因 code → 中文标签
const GATE_REASON_LABELS: Record<string, string> = {
  missing_sku: '缺少 SKU',
  cjk_without_localization: '中文文案无英文本地化',
  missing_price: '缺少有效零售价',
  unapproved_candidate: '候选未批准',
  cjk_in_approved_copy: '已批准文案含中文',
  unapproved_copy: '英文文案未批准',
  thin_copy: '文案内容过短',
}

// 硬阻断 code（不可强制放行）
const HARD_BLOCK_CODES = new Set<string>(['missing_sku', 'cjk_without_localization'])

// ProductOut 类型（对齐 backend/app/schemas/product.py::ProductOut）
interface Product {
  id: string
  sku: string
  name: string
  description?: string | null
  category?: string | null
  tags?: string[]
  status: string
  candidate_status?: string | null
  source?: string
  source_url?: string | null
  meta?: Record<string, any> | null
  created_at?: string
  updated_at?: string
}

// 管线结果（对齐 product_pipeline_service::run_pipeline 返回）
interface PipelineResult {
  success: boolean
  data: {
    pipeline_id: string
    status: string
    completed_steps: number
    total_steps: number
    progress: number
    elapsed_time_seconds: number
    steps: Record<string, any>
    errors: string[]
    product_name: string
    sku: string
  }
  error: string | null
}

// 闸门裁决（对齐 backend/app/services/listing_gate.py::gate_product_for_publish 与
// 后端 confirm-list / push-woocommerce 返回体）
interface GateVerdict {
  gate: 'needs_review' | 'blocked'
  gate_reasons: Array<{ code: string; message: string }>
  forceable?: boolean
  message?: string
  product_id?: string
}

// 契约态条目
interface ContractItem {
  endpoint: string
  desc: string
  state: 'ready' | 'partial' | 'missing'
  gap?: string
}

const CONTRACT_ITEMS: readonly ContractItem[] = [
  { endpoint: 'GET /api/v1/products?limit=200&status=draft', desc: '候选池加载', state: 'ready' },
  { endpoint: 'POST /api/v1/product-pipeline/import-from-1688', desc: '1688 导入（可选自动运行）', state: 'ready' },
  { endpoint: 'POST /api/v1/product-pipeline/run', desc: '管线执行（6 步）', state: 'ready' },
  { endpoint: 'POST /api/v1/product-pipeline/confirm-list', desc: '人工确认上架（含闸门）', state: 'ready' },
  { endpoint: 'POST /api/v1/products/{id}/push-woocommerce?force=true', desc: '闸门强制放行（产品管理复用）', state: 'ready' },
]

const stage4 = STAGE_BY_ID.get('analysis')
const stage10 = STAGE_BY_ID.get('content')
const stage11 = STAGE_BY_ID.get('wc_sync')

export default function PipelineRunner() {
  // Step 1: 候选池
  const [candidates, setCandidates] = useState<Product[]>([])
  const [candidatesLoading, setCandidatesLoading] = useState(false)
  const [candidatesError, setCandidatesError] = useState<string | null>(null)
  const [searchText, setSearchText] = useState('')
  const [selectedCandidate, setSelectedCandidate] = useState<Product | null>(null)
  const [importedInfo, setImportedInfo] = useState<Record<string, any> | null>(null)

  // 1688 导入
  const [importUrl, setImportUrl] = useState('')
  const [importLoading, setImportLoading] = useState(false)
  const [autoRunAfterImport, setAutoRunAfterImport] = useState(true)

  // Step 2: 管线运行
  const [running, setRunning] = useState(false)
  const [pipelineResult, setPipelineResult] = useState<PipelineResult | null>(null)
  const [runError, setRunError] = useState<string | null>(null)

  // Step 3: 确认上架
  const [confirmLoading, setConfirmLoading] = useState(false)
  const [gateVerdict, setGateVerdict] = useState<GateVerdict | null>(null)
  const [confirmError, setConfirmError] = useState<string | null>(null)
  const [confirmSuccess, setConfirmSuccess] = useState<Record<string, any> | null>(null)
  const [confirmStatus, setConfirmStatus] = useState<'publish' | 'draft' | 'pending'>('publish')
  const [jsonPreviewOpen, setJsonPreviewOpen] = useState(false)

  // ── 加载候选池 ─────────────────────────────────────────────────────────
  const loadCandidates = async () => {
    setCandidatesLoading(true)
    setCandidatesError(null)
    try {
      const token = localStorage.getItem('admin_token') || ''
      const headers: HeadersInit = {}
      if (token) headers['Authorization'] = `Bearer ${token}`
      const resp = await fetch('/api/v1/products?limit=200&status=draft', { headers })
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}))
        setCandidatesError(`HTTP ${resp.status}：${body.detail || body.error || resp.statusText}`)
        return
      }
      const list = await resp.json()
      const all: Product[] = Array.isArray(list) ? list : ((list as any).list ?? [])
      const filtered = all.filter((p) => p.candidate_status != null)
      // 若 status=draft 无候选，回退加载不带 status 的全量
      if (filtered.length === 0) {
        const resp2 = await fetch('/api/v1/products?limit=200', { headers })
        if (resp2.ok) {
          const list2 = await resp2.json()
          const all2: Product[] = Array.isArray(list2) ? list2 : ((list2 as any).list ?? [])
          setCandidates(all2.filter((p) => p.candidate_status != null))
        }
        setCandidates(filtered)
        return
      }
      setCandidates(filtered)
    } catch (e: any) {
      setCandidatesError(e.message || '网络错误')
      message.error(`候选池加载失败：${e.message || '网络错误'}`)
    } finally {
      setCandidatesLoading(false)
    }
  }

  useEffect(() => {
    loadCandidates()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── 1688 导入 ─────────────────────────────────────────────────────────
  const handleImport1688 = async () => {
    if (!importUrl.trim()) {
      message.error('请输入 1688 商品 URL 或商品 ID')
      return
    }
    setImportLoading(true)
    const token = localStorage.getItem('admin_token') || ''
    try {
      const resp = await fetch('/api/v1/product-pipeline/import-from-1688', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(token && { Authorization: `Bearer ${token}` }) },
        body: JSON.stringify({
          url_or_id: importUrl.trim(),
          auto_run_pipeline: autoRunAfterImport,
          auto_list: false,
        }),
      })
      const result = await resp.json()
      if (result.success && result.data?.product_info) {
        const pi = result.data.product_info
        const pseudo: Product = {
          id: result.data.product_id || `imported-${Date.now()}`,
          sku: pi.sku || '',
          name: pi.name || '未命名商品',
          description: pi.description || '',
          category: pi.category || '',
          status: 'draft',
          candidate_status: 'candidate',
          source: '1688',
          source_url: result.data.source_url || importUrl,
          meta: null,
        }
        setSelectedCandidate(pseudo)
        setImportedInfo(pi)
        setPipelineResult(result.data.pipeline_result || null)
        setRunError(null)
        setGateVerdict(null)
        setConfirmSuccess(null)
        setConfirmError(null)
        setImportUrl('')
        const skipReason = result.data.auto_list_skipped
        if (skipReason) {
          message.warning(`已导入商品：${pi.name || '未知商品'}；自动上架被跳过：${skipReason}`)
        } else if (result.data.pipeline_result) {
          message.success(`已导入并运行管线：${pi.name || '未知商品'}`)
        } else {
          message.success(`已导入商品：${pi.name || '未知商品'}`)
        }
      } else {
        message.error(`1688 导入失败：${result.error || '未知错误'}`)
      }
    } catch (e: any) {
      message.error(`1688 导入失败：${e.message || '网络错误'}`)
    } finally {
      setImportLoading(false)
    }
  }

  // ── 从候选/导入构建 product_info ─────────────────────────────────────
  const buildProductInfo = (): Record<string, any> => {
    const base = {
      name: selectedCandidate?.name || '',
      category: selectedCandidate?.category || '',
      price: '',
      description: selectedCandidate?.description || '',
      core_selling_points: [] as string[],
      target_audience: '',
      usage_scenarios: [] as string[],
      product_features: [] as string[],
    }
    if (importedInfo) {
      return { ...base, ...importedInfo }
    }
    return base
  }

  // ── 运行管线 ──────────────────────────────────────────────────────────
  const handleRun = async () => {
    if (!selectedCandidate) {
      message.error('请先在第一步选择候选，或从 1688 导入')
      return
    }
    setRunning(true)
    setPipelineResult(null)
    setRunError(null)
    setGateVerdict(null)
    setConfirmSuccess(null)
    setConfirmError(null)
    try {
      const runToken = localStorage.getItem('admin_token') || ''
      const resp = await fetch('/api/v1/product-pipeline/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(runToken && { Authorization: `Bearer ${runToken}` }) },
        body: JSON.stringify({
          product_info: buildProductInfo(),
          auto_list: false,
          include_images: false,
        }),
      })
      const data = await resp.json()
      if (data.success || data.data) {
        setPipelineResult(data)
        const st = data.data?.status
        if (st === 'failed') {
          setRunError(data.error || '管线执行失败')
          message.error(data.error || `管线失败：${data.data?.errors?.join('；') || '未知错误'}`)
        } else if (st === 'partial') {
          message.warning(`管线部分成功：${data.data?.completed_steps}/${data.data?.total_steps}`)
        } else {
          message.success(`管线完成：${data.data?.completed_steps}/${data.data?.total_steps}步成功`)
        }
      } else {
        setRunError(data.error || '管线执行失败')
        message.error(data.error || '管线执行失败')
      }
    } catch (e: any) {
      setRunError(e.message || '网络错误')
      message.error(`管线执行失败：${e.message || '网络错误'}`)
    } finally {
      setRunning(false)
    }
  }

  // ── 确认上架（含闸门裁决解析）────────────────────────────────────────
  const handleConfirm = async (force: boolean = false) => {
    if (!pipelineResult) return
    setConfirmLoading(true)
    setGateVerdict(null)
    setConfirmError(null)
    setConfirmSuccess(null)
    try {
      const confirmToken = localStorage.getItem('admin_token') || ''
      const resp = await fetch('/api/v1/product-pipeline/confirm-list', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(confirmToken && { Authorization: `Bearer ${confirmToken}` }) },
        body: JSON.stringify({
          pipeline_result: pipelineResult,
          status: confirmStatus,
          force,
        }),
      })

      // 契约 1：HTTP 409 / 422（push-woocommerce 风格 detail）
      if (resp.status === 409 || resp.status === 422) {
        const body = await resp.json().catch(() => ({}))
        const detail = body.detail || body
        if (detail?.gate === 'needs_review' || detail?.gate === 'blocked') {
          setGateVerdict({
            gate: detail.gate,
            gate_reasons: detail.gate_reasons || [],
            forceable: detail.forceable,
            message: detail.message,
            product_id: detail.product_id,
          })
          if (detail.gate === 'needs_review') {
            message.warning(`闸门需人工复核：${detail.message || '请查看 gate_reasons'}`)
          } else {
            message.error(`闸门硬阻断：${detail.message || '不可强制放行'}`)
          }
          return
        }
        setConfirmError(detail.message || detail.error || `HTTP ${resp.status}`)
        message.error(`上架失败：${detail.message || detail.error || `HTTP ${resp.status}`}`)
        return
      }

      // 契约 2：HTTP 200 + body.data.gate（confirm-list 当前返回体）
      const data = await resp.json()
      const innerGate = data?.data?.gate
      if (!data.success) {
        if (innerGate === 'needs_review' || innerGate === 'blocked') {
          setGateVerdict({
            gate: innerGate,
            gate_reasons: data.data.gate_reasons || [],
            forceable: data.data.forceable,
            message: data.data.error || data.error,
            product_id: data.data.product_id,
          })
          if (innerGate === 'needs_review') {
            message.warning(`闸门需人工复核：${data.data.error || data.error || ''}`)
          } else {
            message.error(`闸门硬阻断：${data.data.error || data.error || ''}`)
          }
          return
        }
        setConfirmError(data.error || `HTTP ${resp.status}`)
        message.error(data.error || `上架失败：HTTP ${resp.status}`)
        return
      }

      setConfirmSuccess(data.data)
      const wcId = data.data?.woocommerce_id
      message.success(wcId ? `上架成功，WooCommerce ID: #${wcId}` : '上架成功')
    } catch (e: any) {
      setConfirmError(e.message || '网络错误')
      message.error(`上架失败：${e.message || '网络错误'}`)
    } finally {
      setConfirmLoading(false)
    }
  }

  // ── 管线步骤渲染 ─────────────────────────────────────────────────────
  const getStepStatus = (stepId: string) => {
    if (!pipelineResult) return 'wait' as const
    const step = pipelineResult.data?.steps?.[stepId]
    if (!step) return 'wait' as const
    switch (step.status) {
      case 'completed': return 'finish' as const
      case 'failed': return 'error' as const
      case 'running': return 'process' as const
      default: return 'wait' as const
    }
  }

  const getStepColor = (stepId: string) => {
    if (!pipelineResult) return 'default'
    const step = pipelineResult.data?.steps?.[stepId]
    if (!step) return 'default'
    switch (step.status) {
      case 'completed': return 'green'
      case 'failed': return 'red'
      case 'running': return 'blue'
      default: return 'default'
    }
  }

  const getListingData = () => pipelineResult?.data?.steps?.listing_data?.data || null

  // ── 闸门 UI ──────────────────────────────────────────────────────────
  const renderGate = () => {
    if (!gateVerdict) return null
    const isBlocked = gateVerdict.gate === 'blocked'
    return (
      <Card
        size="small"
        title={
          <Space>
            {isBlocked
              ? <ExclamationCircleOutlined style={{ color: '#a8071a' }} />
              : <ClockCircleOutlined style={{ color: '#d48806' }} />}
            <span>{isBlocked ? '闸门硬阻断 · 不可放行' : '闸门需人工复核'}</span>
          </Space>
        }
        style={{
          marginTop: 12,
          borderColor: isBlocked ? '#ffccc7' : '#ffe7a1',
          background: isBlocked ? '#fff1f0' : '#fffbe6',
        }}
      >
        {gateVerdict.message && (
          <Paragraph style={{ marginTop: 0, marginBottom: 8 }}>{gateVerdict.message}</Paragraph>
        )}
        <List
          size="small"
          bordered
          dataSource={gateVerdict.gate_reasons}
          renderItem={(r) => (
            <List.Item>
              <Space align="start">
                <Tag color={HARD_BLOCK_CODES.has(r.code) ? 'red' : 'orange'}>
                  {GATE_REASON_LABELS[r.code] || r.code}
                </Tag>
                <div style={{ minWidth: 0 }}>
                  <Text code style={{ fontSize: 11 }}>{r.code}</Text>
                  <Paragraph style={{ margin: '2px 0 0', fontSize: 13 }}>{r.message}</Paragraph>
                </div>
              </Space>
            </List.Item>
          )}
        />
        {isBlocked ? (
          <Alert
            message="硬阻断：缺少 SKU 或中文文案无英文本地化，不可通过强制放行。请先补齐数据。"
            type="error"
            showIcon
            style={{ marginTop: 12 }}
          />
        ) : (
          <Space wrap style={{ marginTop: 12 }}>
            <Button
              type="primary"
              danger
              icon={<SendOutlined />}
              loading={confirmLoading}
              onClick={() => handleConfirm(true)}
            >
              我已人工复核，强制放行
            </Button>
            <Text type="secondary" style={{ fontSize: 12 }}>
              确认所有 gate_reasons 已评估后可放行；缺 SKU / 中文文案无英文本地化为硬阻断，不可强制。
            </Text>
          </Space>
        )}
      </Card>
    )
  }

  const filteredCandidates = candidates.filter((p) => {
    if (!searchText) return true
    const s = searchText.toLowerCase()
    return (
      p.name.toLowerCase().includes(s) ||
      p.sku.toLowerCase().includes(s) ||
      (p.category || '').toLowerCase().includes(s)
    )
  })

  const stepCurrent = !pipelineResult ? 1 : (pipelineResult.data?.steps?.listing?.status === 'completed' ? 3 : 2)

  return (
    <div style={{ padding: 24, maxWidth: 1400, margin: '0 auto' }}>
      {/* 标题 */}
      <div style={{ marginBottom: 16 }}>
        <Space align="start">
          <RocketOutlined style={{ fontSize: 28, color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>管线运行器</Title>
            <Text type="secondary">
              覆盖生命周期阶段：
              <Tag style={{ margin: '0 4px' }}>{stage4?.n}. {stage4?.label}</Tag>
              <Tag style={{ margin: '0 4px' }}>{stage10?.n}. {stage10?.label}</Tag>
              <Tag style={{ margin: '0 4px' }}>{stage11?.n}. {stage11?.label}</Tag>
            </Text>
          </div>
        </Space>
      </div>

      {/* 闸门说明 Alert */}
      <Alert
        type="info"
        showIcon
        icon={<ExclamationCircleOutlined />}
        style={{ marginBottom: 16 }}
        message="闸门已在后端生效"
        description="缺 SKU、中文文案无英文本地化为硬阻断（422，不可强制放行）；缺零售价、候选未批准、英文文案未批准、文案过短、已批准文案含中文为需人工复核（409，可强制放行）。"
      />

      <Steps
        size="small"
        current={stepCurrent}
        style={{ marginBottom: 16 }}
        items={[
          { title: '选择候选', icon: <ShopOutlined /> },
          { title: '运行管线', icon: <ThunderboltOutlined /> },
          { title: '确认上架', icon: <SendOutlined /> },
        ]}
      />

      {/* 第一步：选择候选 */}
      <Card
        size="small"
        title={<Space><ShopOutlined />第一步：选择候选商品</Space>}
        extra={
          selectedCandidate && (
            <Button
              size="small"
              icon={<DeleteOutlined />}
              onClick={() => {
                setSelectedCandidate(null)
                setImportedInfo(null)
                setPipelineResult(null)
                setRunError(null)
                setGateVerdict(null)
                setConfirmSuccess(null)
                setConfirmError(null)
              }}
            >
              清除选择
            </Button>
          )
        }
        style={{ marginBottom: 16 }}
      >
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={10}>
            <Space.Compact style={{ width: '100%', marginBottom: 12 }}>
              <Input
                placeholder="搜索候选名称 / SKU / 分类"
                prefix={<SearchOutlined />}
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                allowClear
              />
              <Button icon={<ReloadOutlined />} loading={candidatesLoading} onClick={loadCandidates}>
                刷新
              </Button>
            </Space.Compact>
            {candidatesError ? (
              <Alert
                type="error"
                showIcon
                message="候选池后端未接入"
                description={candidatesError}
                style={{ marginBottom: 8 }}
              />
            ) : null}
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 8 }}>
              候选池：status=draft 且 candidate_status ≠ null 的产品行（{candidates.length} 条）
            </Text>
            <List
              size="small"
              bordered
              style={{ overflowY: 'auto', maxHeight: 380 }}
              locale={{
                emptyText: candidatesLoading
                  ? <Spin size="small" />
                  : <Empty description="候选池为空，可从 1688 导入，或先去产品管理建立候选" />,
              }}
              dataSource={filteredCandidates}
              renderItem={(p) => {
                const active = selectedCandidate?.id === p.id
                return (
                  <List.Item
                    onClick={() => {
                      setSelectedCandidate(p)
                      setImportedInfo(null)
                      setPipelineResult(null)
                      setRunError(null)
                      setGateVerdict(null)
                      setConfirmSuccess(null)
                      setConfirmError(null)
                    }}
                    style={{
                      cursor: 'pointer',
                      background: active ? '#f0f5ff' : undefined,
                      padding: '10px 12px',
                    }}
                  >
                    <List.Item.Meta
                      avatar={<ShopOutlined style={{ color: '#722ed1' }} />}
                      title={
                        <Space wrap>
                          <Text strong>{p.name}</Text>
                          {p.candidate_status && <Tag color="orange">{p.candidate_status}</Tag>}
                        </Space>
                      }
                      description={
                        <div>
                          <Text type="secondary" style={{ fontSize: 12 }}>SKU: {p.sku || '-'}</Text>
                          {p.category && <Text type="secondary" style={{ marginLeft: 12, fontSize: 12 }}>分类: {p.category}</Text>}
                          {p.source && <Text type="secondary" style={{ marginLeft: 12, fontSize: 12 }}>来源: {p.source}</Text>}
                        </div>
                      }
                    />
                  </List.Item>
                )
              }}
            />
          </Col>
          <Col xs={24} lg={14}>
            {selectedCandidate ? (
              <Card
                size="small"
                title={<Space><EyeOutlined />候选详情预览</Space>}
                extra={
                  <Button
                    type="primary"
                    icon={<PlayCircleOutlined />}
                    loading={running}
                    onClick={handleRun}
                  >
                    运行管线 <ArrowRightOutlined />
                  </Button>
                }
                style={{ marginBottom: 16 }}
              >
                <ProductTimeline product={selectedCandidate} style={{ marginBottom: 12 }} />
                <Descriptions column={2} size="small" bordered>
                  <Descriptions.Item label="名称" span={2}>{selectedCandidate.name}</Descriptions.Item>
                  <Descriptions.Item label="SKU">{selectedCandidate.sku || '-'}</Descriptions.Item>
                  <Descriptions.Item label="分类">{selectedCandidate.category || '-'}</Descriptions.Item>
                  <Descriptions.Item label="状态">
                    <Tag color={selectedCandidate.status === 'active' ? 'green' : selectedCandidate.status === 'draft' ? 'orange' : 'default'}>
                      {selectedCandidate.status}
                    </Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="候选状态">
                    <Tag color="orange">{selectedCandidate.candidate_status || '无'}</Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="来源" span={2}>
                    {selectedCandidate.source_url ? (
                      <a href={selectedCandidate.source_url} target="_blank" rel="noopener noreferrer">
                        <LinkOutlined /> {selectedCandidate.source || selectedCandidate.source_url}
                      </a>
                    ) : selectedCandidate.source || '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label="描述" span={2}>
                    <Paragraph ellipsis={{ rows: 3, expandable: true }} style={{ margin: 0 }}>
                      {selectedCandidate.description || '暂无描述'}
                    </Paragraph>
                  </Descriptions.Item>
                  {selectedCandidate.tags && selectedCandidate.tags.length > 0 && (
                    <Descriptions.Item label="标签" span={2}>
                      {selectedCandidate.tags.map((t, i) => <Tag key={i}>{String(t)}</Tag>)}
                    </Descriptions.Item>
                  )}
                  {selectedCandidate.created_at && (
                    <Descriptions.Item label="创建时间" span={2}>
                      {new Date(selectedCandidate.created_at).toLocaleString()}
                    </Descriptions.Item>
                  )}
                </Descriptions>
              </Card>
            ) : (
              <Empty style={{ padding: '60px 0' }} description="从左侧候选列表选择一个商品，或从 1688 导入" />
            )}

            <Card size="small" title={<Space><ImportOutlined />从 1688 导入（备选入口）</Space>}>
              <Space.Compact style={{ width: '100%' }} block>
                <Input
                  placeholder="1688 商品 URL 或商品 ID"
                  prefix={<ImportOutlined />}
                  value={importUrl}
                  onChange={(e) => setImportUrl(e.target.value)}
                  onPressEnter={handleImport1688}
                  allowClear
                />
                <Button
                  type="primary"
                  icon={<ThunderboltOutlined />}
                  loading={importLoading}
                  onClick={handleImport1688}
                >
                  导入
                </Button>
              </Space.Compact>
              <div style={{ marginTop: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  <SyncOutlined style={{ marginRight: 4 }} />
                  auto_run_pipeline = {autoRunAfterImport ? 'true' : 'false'}
                </Text>
                <label style={{ fontSize: 12 }}>
                  <input
                    type="checkbox"
                    checked={autoRunAfterImport}
                    onChange={(e) => setAutoRunAfterImport(e.target.checked)}
                    style={{ marginRight: 4 }}
                  />
                  导入后自动运行管线
                </label>
              </div>
            </Card>
          </Col>
        </Row>
      </Card>

      {/* 第二步：运行管线 */}
      <Card
        size="small"
        title={<Space><ThunderboltOutlined />第二步：运行管线</Space>}
        extra={
          pipelineResult && (
            <Button
              size="small"
              icon={<ReloadOutlined />}
              loading={running}
              onClick={handleRun}
            >
              重新运行
            </Button>
          )
        }
        style={{ marginBottom: 16 }}
      >
        <Spin spinning={running} tip="管线执行中，请稍候…">
          {pipelineResult ? (
            <>
              <Row gutter={[16, 16]} style={{ marginBottom: 12 }}>
                <Col span={6}>
                  <Statistic title="完成步骤" value={`${pipelineResult.data.completed_steps}/${pipelineResult.data.total_steps}`} />
                </Col>
                <Col span={6}>
                  <Statistic title="进度" value={pipelineResult.data.progress} suffix="%" />
                </Col>
                <Col span={6}>
                  <Statistic title="耗时" value={pipelineResult.data.elapsed_time_seconds} suffix="秒" />
                </Col>
                <Col span={6}>
                  <Statistic
                    title="状态"
                    value={
                      pipelineResult.data.status === 'completed' ? '成功'
                        : pipelineResult.data.status === 'failed' ? '失败'
                        : pipelineResult.data.status === 'partial' ? '部分成功'
                        : pipelineResult.data.status
                    }
                    valueStyle={{
                      color: pipelineResult.data.status === 'completed' ? '#52c41a'
                        : pipelineResult.data.status === 'failed' ? '#ff4d4f'
                        : pipelineResult.data.status === 'partial' ? '#faad14'
                        : '#1890ff',
                    }}
                  />
                </Col>
              </Row>

              <Progress
                percent={pipelineResult.data.progress}
                status={pipelineResult.data.status === 'completed' ? 'success' : pipelineResult.data.status === 'failed' ? 'exception' : 'active'}
                style={{ margin: '8px 0' }}
              />

              {pipelineResult.data.errors && pipelineResult.data.errors.length > 0 && (
                <Alert
                  message={`${pipelineResult.data.errors.length} 个错误`}
                  description={pipelineResult.data.errors.map((e, i) => <div key={i}>{e}</div>)}
                  type="warning"
                  showIcon
                  style={{ margin: '12px 0' }}
                />
              )}

              <Steps
                direction="vertical"
                size="small"
                style={{ marginTop: 16 }}
                items={PIPELINE_STEPS.map((step) => {
                  const StepIcon = STEP_ICONS[step.id] ?? FileTextOutlined
                  const stepData = pipelineResult.data.steps?.[step.id]
                  const stage = STAGE_BY_ID.get(step.stageId)
                  return {
                    key: step.id,
                    title: (
                      <Space wrap>
                        <StepIcon />
                        <span>{step.title}</span>
                        <Tag color={getStepColor(step.id)}>{stepData?.status || 'wait'}</Tag>
                        {stage && <Text type="secondary" style={{ fontSize: 11 }}>阶段{stage.n} · {stage.label}</Text>}
                      </Space>
                    ),
                    description: step.description,
                    status: getStepStatus(step.id),
                  }
                })}
              />
            </>
          ) : runError ? (
            <Alert
              type="error"
              showIcon
              message="管线执行失败"
              description={runError}
              action={
                <Button size="small" icon={<ReloadOutlined />} loading={running} onClick={handleRun}>
                  重试
                </Button>
              }
            />
          ) : (
            <Empty description="请先在第一步选择候选，点击「运行管线」" />
          )}
        </Spin>
      </Card>

      {/* 第三步：确认上架 */}
      <Card
        size="small"
        title={<Space><ShopOutlined />第三步：人工确认上架</Space>}
        extra={
          getListingData() && (
            <Button size="small" icon={<EyeOutlined />} onClick={() => setJsonPreviewOpen(true)}>
              预览 JSON
            </Button>
          )
        }
      >
        {pipelineResult && getListingData() ? (
          <>
            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label="商品名称" span={2}>{getListingData()?.name}</Descriptions.Item>
              <Descriptions.Item label="SKU">
                {getListingData()?.sku
                  ? getListingData().sku
                  : <Tag color="red">缺失（将被闸门硬阻断）</Tag>}
              </Descriptions.Item>
              <Descriptions.Item label="售价">
                ${getListingData()?.regular_price || <Tag color="orange">待设置</Tag>}
              </Descriptions.Item>
              <Descriptions.Item label="库存">{getListingData()?.stock_quantity ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="状态">
                {getListingData()?.status === 'draft' ? '草稿' : (getListingData()?.status || 'publish')}
              </Descriptions.Item>
              <Descriptions.Item label="分类" span={2}>
                {getListingData()?.categories?.map((c: any, i: number) => (
                  <Tag key={i}>{c.name || c.id}</Tag>
                )) || <Text type="secondary">无</Text>}
              </Descriptions.Item>
              <Descriptions.Item label="标签" span={2}>
                {(getListingData()?.tags || []).map((t: any, i: number) => (
                  <Tag key={i}>{t.name || t}</Tag>
                )) || <Text type="secondary">无</Text>}
              </Descriptions.Item>
              <Descriptions.Item label="短描述" span={2}>
                <Paragraph ellipsis={{ rows: 2, expandable: true }} style={{ margin: 0 }}>
                  {getListingData()?.short_description || '-'}
                </Paragraph>
              </Descriptions.Item>
              <Descriptions.Item label="完整描述" span={2}>
                <Paragraph ellipsis={{ rows: 4, expandable: true }} style={{ margin: 0 }}>
                  {getListingData()?.description || '-'}
                </Paragraph>
              </Descriptions.Item>
            </Descriptions>

            <Space wrap style={{ marginTop: 16 }}>
              <Select
                value={confirmStatus}
                onChange={setConfirmStatus}
                style={{ width: 160 }}
                options={[
                  { value: 'publish', label: '直接发布' },
                  { value: 'draft', label: '保存为草稿' },
                  { value: 'pending', label: '待处理' },
                ]}
              />
              <Button
                type="primary"
                icon={<SendOutlined />}
                loading={confirmLoading}
                onClick={() => handleConfirm(false)}
              >
                人工确认后上架
              </Button>
            </Space>

            {renderGate()}

            {confirmSuccess && (
              <Alert
                type="success"
                showIcon
                icon={<CheckCircleOutlined />}
                style={{ marginTop: 12 }}
                message={
                  confirmSuccess.woocommerce_id
                    ? `上架成功，WooCommerce ID: #${confirmSuccess.woocommerce_id}`
                    : '上架成功'
                }
                description={
                  <Space direction="vertical" size={2} style={{ width: '100%' }}>
                    {confirmSuccess.product_id && (
                      <Text type="secondary" style={{ fontSize: 12 }}>本地 Product ID: {confirmSuccess.product_id}</Text>
                    )}
                    {confirmSuccess.slug && (
                      <Text type="secondary" style={{ fontSize: 12 }}>Slug: {confirmSuccess.slug}</Text>
                    )}
                    {confirmSuccess.permalink && (
                      <a href={confirmSuccess.permalink} target="_blank" rel="noopener noreferrer">
                        <LinkOutlined /> {confirmSuccess.permalink}
                      </a>
                    )}
                  </Space>
                }
              />
            )}

            {confirmError && (
              <Alert
                type="error"
                showIcon
                style={{ marginTop: 12 }}
                message={`上架失败：${confirmError}`}
              />
            )}
          </>
        ) : (
          <Empty
            description={
              pipelineResult
                ? '管线未生成 listing_data，无法确认上架'
                : '请先在第二步运行管线'
            }
          />
        )}
      </Card>

      {/* 契约态清单 */}
      <Card
        size="small"
        title={<Space><DatabaseOutlined />契约态清单（后端接入状态）</Space>}
        style={{ marginTop: 16 }}
      >
        <Paragraph type="secondary" style={{ marginTop: 0 }}>
          本页面依赖的后端能力与当前接入状态。所有 fetch 均使用真实端点；能力缺失时会在对应步骤渲染显式「后端未接入」契约态，不 mock。
        </Paragraph>
        <List
          size="small"
          bordered
          dataSource={[...CONTRACT_ITEMS]}
          renderItem={(item) => (
            <List.Item>
              <Space align="start" wrap>
                <Tag
                  color={item.state === 'ready' ? 'green' : item.state === 'partial' ? 'orange' : 'red'}
                >
                  {item.state === 'ready' ? '已接入' : item.state === 'partial' ? '部分' : '未接入'}
                </Tag>
                <div style={{ minWidth: 0 }}>
                  <Text code style={{ fontSize: 12 }}>{item.endpoint}</Text>
                  <Paragraph style={{ margin: '2px 0 0', fontSize: 13 }}>{item.desc}</Paragraph>
                  {item.gap && <Text type="secondary" style={{ fontSize: 12 }}>{item.gap}</Text>}
                </div>
              </Space>
            </List.Item>
          )}
        />
      </Card>

      {/* 预览 JSON Modal */}
      <Modal
        title="listing_data JSON 预览"
        open={jsonPreviewOpen}
        onCancel={() => setJsonPreviewOpen(false)}
        footer={[
          <Button key="close" onClick={() => setJsonPreviewOpen(false)}>关闭</Button>,
          <Button
            key="copy"
            type="primary"
            icon={<SendOutlined />}
            onClick={() => {
              navigator.clipboard.writeText(JSON.stringify(getListingData(), null, 2))
              message.success('已复制 JSON')
            }}
          >
            复制 JSON
          </Button>,
        ]}
        width={720}
      >
        <Paragraph
          style={{
            whiteSpace: 'pre-wrap',
            fontSize: 12,
            background: '#f5f5f5',
            padding: 12,
            borderRadius: 4,
            maxHeight: 480,
            overflow: 'auto',
            margin: 0,
          }}
        >
          {JSON.stringify(getListingData(), null, 2)}
        </Paragraph>
      </Modal>
    </div>
  )
}
