import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Card, Row, Col, Button, Typography, Spin, Empty, Alert, Table, Tag,
  Select, Space, Badge, Statistic, Divider, Tabs, Image, Modal,
  Progress, Descriptions, Tooltip, Steps, Radio, Upload, InputNumber, Switch,
} from 'antd'
import {
  PictureOutlined, RocketOutlined, CheckCircleOutlined,
  ClockCircleOutlined, RobotOutlined, ExclamationCircleOutlined,
  LoadingOutlined, ArrowLeftOutlined, ReloadOutlined, EyeOutlined,
  PlayCircleOutlined, StopOutlined, DollarOutlined,
  CloudUploadOutlined, AuditOutlined, FileTextOutlined, InboxOutlined,
} from '@ant-design/icons'
import { api, ApiError } from '../api/client'
import { useAuth } from '../auth/AuthProvider'
import { usePolling } from '../hooks/usePolling'

const { Title, Text, Paragraph } = Typography

// ── Types ──────────────────────────────────────────────────────────────
interface Product {
  id: string
  name: string
  sku?: string
  category?: string
  description?: string
  attributes?: Record<string, unknown>
}

interface Brief {
  id: string
  product_id: string
  objective: string
  channel?: string
  target_market?: string
  visual_style?: string
  status: string
  required_assets?: { asset_type: string; count: number; priority: string; prompt_hint?: string; aspect_ratio?: string }[]
  constraints?: Record<string, unknown>
  created_at?: string
  updated_at?: string
  created_by?: string
}

interface GenerationRun {
  id: string
  brief_id?: string
  operation: string
  model?: string
  provider?: string
  status: string
  input_asset_ids?: string[]
  output_asset_ids?: string[]
  parameters?: Record<string, unknown>
  prompt_template_id?: string
  prompt_version?: string
  dedup_key?: string
  estimated_cost?: number
  actual_cost?: number
  error_code?: string
  error_message?: string
  latency_ms?: number
  created_at?: string
  completed_at?: string
  trace_id?: string
}

interface Asset {
  id: string
  product_id?: string
  brief_id?: string
  asset_type: string
  source_type: string
  storage_key?: string
  preview_url?: string
  width?: number
  height?: number
  ratio?: string
  mime_type?: string
  generation_run_id?: string
  version: number
  status: string
  quality_result?: Record<string, unknown>
  compliance_result?: Record<string, unknown>
  created_by?: string
  reviewed_by?: string
  approved_at?: string
  wc_pushed_at?: string
  wc_media_id?: string
  created_at?: string
  updated_at?: string
}

interface Review {
  id: string
  asset_id: string
  review_type: string
  reviewer_type: string
  result: string
  reasons?: Record<string, unknown>
  reviewer_id?: string
  created_at?: string
}

interface QcResult {
  summary?: string
  overall_score?: number
  vision_analysis_performed?: boolean
  image_integrity?: { passed: boolean; score: number; issues?: string[] }
  product_presence?: { passed: boolean; score: number; notes?: string }
  visual_quality?: { passed: boolean; score: number; issues?: string[] }
  composition?: { passed: boolean; score: number; notes?: string }
  color_consistency?: { passed: boolean; score: number; notes?: string }
  background_quality?: { passed: boolean; score: number; notes?: string }
  text_artifact?: { passed: boolean; score: number; issues?: string[] }
  brand_consistency?: { passed: boolean; score: number; notes?: string }
  policy_flags?: { passed: boolean; flags?: string[] }
  confidence?: number
  recommendation?: string
}

// ── Status metadata ────────────────────────────────────────────────────
const STATUS_META: Record<string, { color: string; label: string }> = {
  DRAFT: { color: 'default', label: '草稿' },
  IN_PROGRESS: { color: 'processing', label: '进行中' },
  COMPLETED: { color: 'success', label: '已完成' },
  REJECTED: { color: 'error', label: '已拒绝' },
  QUEUED: { color: 'default', label: '排队中' },
  RUNNING: { color: 'processing', label: '运行中' },
  SUCCEEDED: { color: 'success', label: '成功' },
  FAILED: { color: 'error', label: '失败' },
  QC_PASSED: { color: 'success', label: 'QC 通过' },
  APPROVED: { color: 'success', label: '已批准' },
}

const ASSET_STATUS_META: Record<string, { color: string; label: string; icon: React.ReactNode }> = {
  DRAFT: { color: 'default', label: '草稿', icon: <ClockCircleOutlined /> },
  QUEUED: { color: 'default', label: '排队中', icon: <LoadingOutlined /> },
  RUNNING: { color: 'processing', label: '生成中', icon: <LoadingOutlined /> },
  QC_PASSED: { color: 'success', label: 'QC 通过', icon: <RobotOutlined /> },
  APPROVED: { color: 'success', label: '已批准', icon: <CheckCircleOutlined /> },
  REJECTED: { color: 'error', label: '已拒绝', icon: <ExclamationCircleOutlined /> },
}

export default function CreativeWorkbench() {
  const { productId } = useParams<{ productId: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [product, setProduct] = useState<Product | null>(null)
  const [briefs, setBriefs] = useState<Brief[]>([])
  const [runs, setRuns] = useState<GenerationRun[]>([])
  const [assets, setAssets] = useState<Asset[]>([])
  const [operations, setOperations] = useState<Record<string, { status: string; description?: string; reason?: string }>>({})
  const [selectedAsset, setSelectedAsset] = useState<Asset | null>(null)
  const [selectedReview, setSelectedReview] = useState<Review | null>(null)
  const [reviews, setReviews] = useState<Review[]>([])
  const [generating, setGenerating] = useState(false)
  const [aiQcRunning, setAiQcRunning] = useState(false)
  const [reviewModalVisible, setReviewModalVisible] = useState(false)
  const [reviewDecision, setReviewDecision] = useState<'approve' | 'reject'>('approve')
  const [activeTab, setActiveTab] = useState('overview')
  // P1-1: Asset Upload & Batch Generation
  const [uploading, setUploading] = useState(false)
  const [batchModalVisible, setBatchModalVisible] = useState(false)
  const [batchCount, setBatchCount] = useState(4)
  const [batchGenerating, setBatchGenerating] = useState(false)
  // Auto-refresh polling
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [refreshInterval, setRefreshInterval] = useState(30) // seconds

  // Load workspace data
  const loadData = useCallback(async () => {
    if (!productId) return
    setLoading(true)
    setError(null)
    try {
      const [workspaceData, operationsData, runsData, assetsData] = await Promise.all([
        api.getCreativeWorkspace(productId),
        api.getCreativeOperations(),
        api.getCreativeRuns(50, 0, undefined, productId),
        api.getCreativeAssets(50, 0, undefined, productId),
      ])

      setProduct((workspaceData as any).product || { id: productId, name: 'Product' })
      setBriefs((workspaceData as any).briefs || [])
      setRuns((runsData as any).runs || [])
      setAssets((assetsData as any).assets || [])

      // Build operations map
      const opMap: Record<string, { status: string; description?: string; reason?: string }> = {}
      for (const op of operationsData as any) {
        opMap[op.operation] = {
          status: op.status,
          description: op.description,
          reason: op.reason,
        }
      }
      setOperations(opMap)
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setError('未授权：请先登录或联系管理员获取权限')
        } else if (err.status === 403) {
          setError('权限不足：需要 Operator 角色')
        } else if (err.status === 404) {
          setError('商品未找到')
        } else {
          setError(`加载失败: ${err.message}`)
        }
      } else {
        setError('加载失败：网络错误')
      }
    } finally {
      setLoading(false)
    }
  }, [productId])

  useEffect(() => {
    void loadData()
  }, [loadData])

  // Auto-refresh polling
  const { stop: stopPolling, isPolling } = usePolling(
    loadData,
    { intervalMs: refreshInterval * 1000, enabled: autoRefresh }
  )

  // Load reviews for selected asset
  useEffect(() => {
    if (selectedAsset) {
      api.getCreativeReviews(20, selectedAsset.id)
        .then((r) => setReviews((r as any).reviews || []))
        .catch(() => setReviews([]))
    }
  }, [selectedAsset])

  // ── Actions ─────────────────────────────────────────────────────────
  const handleGenerate = async () => {
    if (!briefs[0]) return
    setGenerating(true)
    try {
      await api.generateFromCreativeBrief(briefs[0].id, {
        count: 4,
        model: 'doubao-seedream-5-0-pro-260628',
        width: 2048,
        height: 2048,
        created_by: user?.username || 'admin',
      })
      await loadData()
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`生成失败: ${err.message}`)
      }
    } finally {
      setGenerating(false)
    }
  }

  const handleAiQc = async (assetId: string) => {
    setAiQcRunning(true)
    try {
      await api.runCreativeAiQc(assetId)
      await loadData()
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`AI QC 失败: ${err.message}`)
      }
    } finally {
      setAiQcRunning(false)
    }
  }

  const handleReview = async () => {
    if (!selectedAsset) return
    try {
      await api.reviewCreativeAsset(selectedAsset.id, {
        decision: reviewDecision,
        reviewer: user?.username || 'admin',
      })
      setReviewModalVisible(false)
      await loadData()
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`审批失败: ${err.message}`)
      }
    }
  }

  const handlePushToWc = async (assetId: string) => {
    try {
      await api.pushCreativeAssetToWc(assetId)
      await loadData()
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`推送 WC 失败: ${err.message}`)
      }
    }
  }

  // P1-1: Asset Upload handler
  const handleUpload = async (file: File) => {
    if (!productId) return false
    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('product_id', productId)
      if (briefs[0]) formData.append('brief_id', briefs[0].id)
      formData.append('asset_type', 'hero_image')
      
      // Use fetch for file upload
      const token = localStorage.getItem('admin_token') || ''
      const response = await fetch(`/api/v1/creative/assets/upload`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
        body: formData,
      })
      
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}))
        throw new ApiError(errData.detail || 'Upload failed', response.status)
      }
      
      await loadData()
      return true
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`上传失败: ${err.message}`)
      }
      return false
    } finally {
      setUploading(false)
    }
  }

  // P1-2: Batch Generation handler
  const handleBatchGenerate = async () => {
    if (!briefs[0]) return
    setBatchGenerating(true)
    try {
      await api.generateFromCreativeBrief(briefs[0].id, {
        count: batchCount,
        model: 'doubao-seedream-5-0-pro-260628',
        width: 2048,
        height: 2048,
        created_by: user?.username || 'admin',
      })
      setBatchModalVisible(false)
      await loadData()
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`批量生成失败: ${err.message}`)
      }
    } finally {
      setBatchGenerating(false)
    }
  }

  // ── Render helpers ──────────────────────────────────────────────────
  const getAssetImage = (asset: Asset): string | null => {
    if (asset.preview_url) return asset.preview_url
    if (asset.storage_key) return api.getCreativeAssetImage(asset.id)
    return null
  }

  const getQcResult = (asset: Asset): QcResult | null => {
    return (asset.quality_result as QcResult) || null
  }

  const canPushToWc = (asset: Asset): boolean => {
    // Only show push button if backend returns eligibility
    // Backend will return 400 if not eligible, so we just show the button
    // and let the backend decide
    return asset.status === 'APPROVED'
  }

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 100 }}>
        <Spin indicator={<LoadingOutlined />} size="large" />
        <div style={{ marginTop: 16 }}><Text>加载 Creative Workbench...</Text></div>
      </div>
    )
  }

  return (
    <div style={{ padding: 24 }}>
      {/* Header */}
      <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <Button
            icon={<ArrowLeftOutlined />}
            type="text"
            onClick={() => navigate('/creative')}
            style={{ marginBottom: 8 }}
          />
          <Title level={3} style={{ margin: 0 }}>
            <PictureOutlined /> Creative Workbench
          </Title>
          <Text type="secondary" ellipsis>{product?.name || productId}</Text>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Switch
            size="small"
            checked={autoRefresh}
            onChange={(checked) => {
              setAutoRefresh(checked)
              if (!checked) stopPolling()
            }}
          />
          <Text type="secondary" style={{ fontSize: 12 }}>自动刷新</Text>
          <Select
            size="small"
            value={refreshInterval}
            onChange={setRefreshInterval}
            options={[
              { value: 10, label: '10s' },
              { value: 30, label: '30s' },
              { value: 60, label: '60s' },
            ]}
            style={{ width: 60 }}
            disabled={!autoRefresh}
          />
          <Button icon={<ReloadOutlined />} onClick={() => void loadData()}>
            刷新
          </Button>
        </div>
      </div>

      {error && (
        <Alert 
          type="error" 
          message={error} 
          style={{ marginBottom: 16 }} 
          showIcon 
          closable 
          onClose={() => setError(null)}
          action={
            <Button size="small" icon={<ReloadOutlined />} onClick={() => void loadData()}>
              重试
            </Button>
          }
        />
      )}

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          // ── Overview Tab ──────────────────────────────────────────
          {
            key: 'overview',
            label: <span><EyeOutlined /> 概览</span>,
            children: (
              <Row gutter={[16, 16]}>
                <Col span={24}>
                  <Card title="生产流程" size="small">
                    <Steps
                      size="small"
                      current={0}
                      items={[
                        { title: 'Product Master', status: 'finish' },
                        { title: 'Creative Brief', status: briefs.length > 0 ? 'finish' : 'process' },
                        { title: 'Generate', status: runs.length > 0 ? 'finish' : 'wait' },
                        { title: 'AI QC', status: assets.some(a => a.quality_result) ? 'finish' : 'wait' },
                        { title: 'Human Review', status: assets.some(a => a.status === 'APPROVED') ? 'finish' : 'wait' },
                        { title: 'Creative Approved', status: assets.some(a => a.wc_pushed_at) ? 'finish' : 'wait' },
                      ]}
                    />
                  </Card>
                </Col>

                <Col xs={24} sm={12} md={6}>
                  <Card size="small">
                    <Statistic title="Briefs" value={briefs.length} prefix={<FileTextOutlined />} />
                  </Card>
                </Col>
                <Col xs={24} sm={12} md={6}>
                  <Card size="small">
                    <Statistic title="Generation Runs" value={runs.length} prefix={<RocketOutlined />} />
                  </Card>
                </Col>
                <Col xs={24} sm={12} md={6}>
                  <Card size="small">
                    <Statistic title="Assets" value={assets.length} prefix={<PictureOutlined />} />
                  </Card>
                </Col>
                <Col xs={24} sm={12} md={6}>
                  <Card size="small">
                    <Statistic
                      title="Approved"
                      value={assets.filter(a => a.status === 'APPROVED').length}
                      valueStyle={{ color: '#52c41a' }}
                      prefix={<CheckCircleOutlined />}
                    />
                  </Card>
                </Col>

                {/* Brief Details */}
                {briefs.length > 0 && (
                  <Col span={24}>
                    <Card title="Creative Brief" size="small">
                      <Descriptions column={2} size="small">
                        <Descriptions.Item label="ID">{briefs[0].id.slice(0, 8)}...</Descriptions.Item>
                        <Descriptions.Item label="Status">
                          <Tag color={STATUS_META[briefs[0].status]?.color}>{STATUS_META[briefs[0].status]?.label || briefs[0].status}</Tag>
                        </Descriptions.Item>
                        <Descriptions.Item label="Objective" span={2}>{briefs[0].objective}</Descriptions.Item>
                        <Descriptions.Item label="Channel">{briefs[0].channel || '-'}</Descriptions.Item>
                        <Descriptions.Item label="Target Market">{briefs[0].target_market || '-'}</Descriptions.Item>
                        <Descriptions.Item label="Visual Style" span={2}>{briefs[0].visual_style || '-'}</Descriptions.Item>
                        <Descriptions.Item label="Required Assets" span={2}>
                          {briefs[0].required_assets?.map((a, i) => (
                            <Tag key={i} color="blue">{a.asset_type} ×{a.count}</Tag>
                          )) || '-'}
                        </Descriptions.Item>
                      </Descriptions>
                    </Card>
                  </Col>
                )}
              </Row>
            ),
          },

          // ── Assets Tab ────────────────────────────────────────────
          {
            key: 'assets',
            label: <span><PictureOutlined /> Assets ({assets.length})</span>,
            children: (
              <div>
                <div style={{ marginBottom: 16, display: 'flex', gap: 8 }}>
                  <Button
                    type="primary"
                    icon={<RocketOutlined />}
                    loading={generating}
                    disabled={briefs.length === 0}
                    onClick={() => void handleGenerate()}
                  >
                    Generate (4 assets)
                  </Button>
                  <Button
                    icon={<PlayCircleOutlined />}
                    disabled={briefs.length === 0}
                    onClick={() => setBatchModalVisible(true)}
                  >
                    Batch Generate
                  </Button>
                  <Upload
                    accept="image/*"
                    showUploadList={false}
                    beforeUpload={(file) => void handleUpload(file)}
                    disabled={uploading || !productId}
                  >
                    <Button
                      icon={<InboxOutlined />}
                      loading={uploading}
                      disabled={!productId}
                    >
                      Upload Image
                    </Button>
                  </Upload>
                </div>

                {assets.length === 0 ? (
                  <Empty description="暂无 Assets。点击 Generate 开始生成。" />
                ) : (
                  <Row gutter={[16, 16]}>
                    {assets.map((asset) => {
                      const qc = getQcResult(asset)
                      const img = getAssetImage(asset)
                      const statusMeta = ASSET_STATUS_META[asset.status] || { color: 'default', label: asset.status, icon: null }
                      const isGenerateSupported = operations['generate']?.status === 'SUPPORTED'

                      return (
                        <Col xs={24} sm={12} md={6} key={asset.id}>
                          <Card
                            size="small"
                            hoverable
                            onClick={() => setSelectedAsset(asset)}
                            style={{ cursor: 'pointer' }}
                          >
                            <div style={{ marginBottom: 8 }}>
                              <div style={{ width: '100%', height: 160, background: '#f5f5f5', borderRadius: 4, overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                {img ? (
                                  <img src={img} alt={asset.asset_type} style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }} />
                                ) : (
                                  <Text type="secondary">No preview</Text>
                                )}
                              </div>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                              <Text strong style={{ fontSize: 13 }}>{asset.asset_type}</Text>
                              <Tag color={statusMeta.color} icon={statusMeta.icon}>{statusMeta.label}</Tag>
                            </div>
                            <Text type="secondary" style={{ fontSize: 11 }}>
                              v{asset.version} · {asset.width}×{asset.height}
                            </Text>

                            {/* QC Score */}
                            {qc && (
                              <div style={{ marginTop: 8 }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                                  <Text type="secondary">AI QC Score</Text>
                                  <Text>{qc.overall_score?.toFixed(1) || '-'}/5</Text>
                                </div>
                                <Progress
                                  percent={((qc.overall_score || 0) / 5) * 100}
                                  size="small"
                                  showInfo={false}
                                  strokeColor={(qc.overall_score || 0) >= 3.5 ? '#52c41a' : (qc.overall_score || 0) >= 2.5 ? '#faad14' : '#f5222d'}
                                />
                                {qc.vision_analysis_performed === false && (
                                  <Text type="warning" style={{ fontSize: 10 }}>
                                    ⚠ Text-only analysis (no vision)
                                  </Text>
                                )}
                              </div>
                            )}

                            {/* WC Push Status */}
                            {asset.wc_pushed_at && (
                              <div style={{ marginTop: 4 }}>
                                <Tag color="geekblue" icon={<CloudUploadOutlined />}>
                                  WC Pushed: {new Date(asset.wc_pushed_at).toLocaleDateString()}
                                </Tag>
                              </div>
                            )}

                            {/* Actions */}
                            <div style={{ marginTop: 8, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                              {isGenerateSupported && asset.status !== 'APPROVED' && (
                                <Button size="small" type="link" icon={<RobotOutlined />}
                                  loading={aiQcRunning}
                                  onClick={(e) => { e.stopPropagation(); void handleAiQc(asset.id) }}
                                >
                                  AI QC
                                </Button>
                              )}
                              {asset.status === 'QC_PASSED' || asset.status === 'APPROVED' ? (
                                <Button size="small" type="link" icon={<AuditOutlined />}
                                  onClick={(e) => { e.stopPropagation(); setSelectedAsset(asset); setReviewModalVisible(true) }}
                                >
                                  Review
                                </Button>
                              ) : null}
                              {canPushToWc(asset) && !asset.wc_pushed_at && (
                                <Button size="small" type="link" icon={<CloudUploadOutlined />}
                                  onClick={(e) => { e.stopPropagation(); void handlePushToWc(asset.id) }}
                                >
                                  Push WC
                                </Button>
                              )}
                            </div>
                          </Card>
                        </Col>
                      )
                    })}
                  </Row>
                )}
              </div>
            ),
          },

          // ── Runs Tab ──────────────────────────────────────────────
          {
            key: 'runs',
            label: <span><RocketOutlined /> Runs ({runs.length})</span>,
            children: (
              <Table
                size="small"
                dataSource={runs}
                rowKey="id"
                pagination={{ pageSize: 10 }}
                columns={[
                  { title: 'Run ID', dataIndex: 'id', key: 'id', width: 100,
                    render: (id: string) => <Text code style={{ fontSize: 11 }}>{id.slice(0, 8)}...</Text> },
                  { title: 'Operation', dataIndex: 'operation', key: 'operation', width: 100 },
                  { title: 'Model', dataIndex: 'model', key: 'model', width: 120,
                    render: (m: string) => m || '-' },
                  { title: 'Status', dataIndex: 'status', key: 'status', width: 100,
                    render: (s: string) => {
                      const meta = STATUS_META[s] || { color: 'default', label: s }
                      return <Tag color={meta.color}>{meta.label}</Tag>
                    } },
                  { title: 'Cost (CNY)', dataIndex: 'actual_cost', key: 'cost', width: 100,
                    render: (c: number) => c ? `¥${c.toFixed(2)}` : '-' },
                  { title: 'Latency', dataIndex: 'latency_ms', key: 'latency', width: 100,
                    render: (ms: number) => ms ? `${(ms / 1000).toFixed(1)}s` : '-' },
                  { title: 'Error', dataIndex: 'error_message', key: 'error', ellipsis: true,
                    render: (e: string) => e ? <Tooltip title={e}><Text type="danger" style={{ cursor: 'help' }}>Error</Text></Tooltip> : '-' },
                  { title: 'Created', dataIndex: 'created_at', key: 'created_at', width: 160,
                    render: (d: string) => d ? new Date(d).toLocaleString() : '-' },
                ]}
              />
            ),
          },

          // ── Reviews Tab ───────────────────────────────────────────
          {
            key: 'reviews',
            label: <span><AuditOutlined /> Reviews</span>,
            children: (
              <Table
                size="small"
                dataSource={reviews}
                rowKey="id"
                pagination={false}
                columns={[
                  { title: 'Review ID', dataIndex: 'id', key: 'id', width: 100,
                    render: (id: string) => <Text code style={{ fontSize: 11 }}>{id.slice(0, 8)}...</Text> },
                  { title: 'Type', dataIndex: 'review_type', key: 'review_type', width: 120 },
                  { title: 'Reviewer', dataIndex: 'reviewer_type', key: 'reviewer_type', width: 100 },
                  { title: 'Result', dataIndex: 'result', key: 'result', width: 100,
                    render: (r: string) => <Tag color={r === 'approved' ? 'success' : r === 'rejected' ? 'error' : 'default'}>{r}</Tag> },
                  { title: 'Reviewer ID', dataIndex: 'reviewer_id', key: 'reviewer_id', width: 120 },
                  { title: 'Created', dataIndex: 'created_at', key: 'created_at', width: 160,
                    render: (d: string) => d ? new Date(d).toLocaleString() : '-' },
                ]}
              />
            ),
          },
        ]}
      />

      {/* Asset Detail Modal */}
      <Modal
        open={!!selectedAsset}
        onCancel={() => setSelectedAsset(null)}
        footer={null}
        width="80%"
        title={selectedAsset ? `Asset Detail: ${selectedAsset.asset_type}` : ''}
      >
        {selectedAsset && (
          <Row gutter={16}>
            <Col span={12}>
              {getAssetImage(selectedAsset) && (
                <Image src={getAssetImage(selectedAsset)!} style={{ maxWidth: '100%' }} />
              )}
              <Divider />
              <Descriptions column={1} size="small" title="Generation Info">
                <Descriptions.Item label="ID">{selectedAsset.id}</Descriptions.Item>
                <Descriptions.Item label="Type">{selectedAsset.asset_type}</Descriptions.Item>
                <Descriptions.Item label="Source">{selectedAsset.source_type}</Descriptions.Item>
                <Descriptions.Item label="Version">v{selectedAsset.version}</Descriptions.Item>
                <Descriptions.Item label="Dimensions">{selectedAsset.width}×{selectedAsset.height}</Descriptions.Item>
                <Descriptions.Item label="Ratio">{selectedAsset.ratio || '-'}</Descriptions.Item>
                <Descriptions.Item label="MIME">{selectedAsset.mime_type || '-'}</Descriptions.Item>
                <Descriptions.Item label="Created">{selectedAsset.created_at ? new Date(selectedAsset.created_at).toLocaleString() : '-'}</Descriptions.Item>
                <Descriptions.Item label="Review By">{selectedAsset.reviewed_by || '-'}</Descriptions.Item>
                <Descriptions.Item label="Approved At">{selectedAsset.approved_at ? new Date(selectedAsset.approved_at).toLocaleString() : '-'}</Descriptions.Item>
              </Descriptions>
            </Col>
            <Col span={12}>
              {/* QC Results */}
              {selectedAsset.quality_result && (
                <Card title="AI QC Results" size="small" style={{ marginBottom: 16 }}>
                  <QcResultDisplay qc={selectedAsset.quality_result as QcResult} />
                </Card>
              )}

              {/* Compliance Results */}
              {selectedAsset.compliance_result && (
                <Card title="Compliance Results" size="small" style={{ marginBottom: 16 }}>
                  <pre style={{ fontSize: 12, margin: 0 }}>
                    {JSON.stringify(selectedAsset.compliance_result, null, 2)}
                  </pre>
                </Card>
              )}

              {/* WC Status */}
              <Card title="WooCommerce Status" size="small">
                <Descriptions column={1} size="small">
                  <Descriptions.Item label="Creative Approval">
                    <Tag color={selectedAsset.status === 'APPROVED' ? 'success' : 'default'}>
                      {selectedAsset.status === 'APPROVED' ? 'Approved' : 'Not Approved'}
                    </Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="Listing Approval">
                    <Tag color="default">Not Checked</Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="WC Push Eligibility">
                    <Tag color={selectedAsset.status === 'APPROVED' ? 'success' : 'error'}>
                      {selectedAsset.status === 'APPROVED' ? 'Eligible' : 'Not Eligible'}
                    </Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="WC Pushed At">
                    {selectedAsset.wc_pushed_at ? new Date(selectedAsset.wc_pushed_at).toLocaleString() : 'Not pushed'}
                  </Descriptions.Item>
                  <Descriptions.Item label="WC Media ID">{selectedAsset.wc_media_id || '-'}</Descriptions.Item>
                </Descriptions>
              </Card>
            </Col>
          </Row>
        )}
      </Modal>

      {/* Review Modal */}
      <Modal
        open={reviewModalVisible}
        title="Human Review"
        onCancel={() => setReviewModalVisible(false)}
        onOk={() => void handleReview()}
        okText="Submit Review"
        cancelText="Cancel"
      >
        {selectedAsset && (
          <div>
            <p>
              <Text strong>Asset:</Text> {selectedAsset.asset_type} (v{selectedAsset.version})
            </p>
            {getAssetImage(selectedAsset) && (
              <Image src={getAssetImage(selectedAsset)!} style={{ maxWidth: '100%', marginBottom: 16 }} />
            )}

            {/* AI QC Summary */}
            {selectedAsset.quality_result && (
              <Card title="AI QC Summary" size="small" style={{ marginBottom: 16 }}>
                <QcResultDisplay qc={selectedAsset.quality_result as QcResult} />
              </Card>
            )}

            <div style={{ marginBottom: 16 }}>
              <Text type="warning">⚠ AI QC Passed ≠ Human Approved. 请独立判断图片质量。</Text>
            </div>

            <Space direction="vertical" style={{ width: '100%' }}>
              <Radio.Group
                value={reviewDecision}
                onChange={(e) => setReviewDecision(e.target.value)}
                buttonStyle="solid"
                style={{ width: '100%' }}
              >
                <Radio.Button value="approve" style={{ width: '50%' }}>
                  <CheckCircleOutlined /> Approve
                </Radio.Button>
                <Radio.Button value="reject" style={{ width: '50%' }}>
                  <ExclamationCircleOutlined /> Reject
                </Radio.Button>
              </Radio.Group>
            </Space>
          </div>
        )}
      </Modal>

      {/* P1-2: Batch Generate Modal */}
      <Modal
        open={batchModalVisible}
        title="Batch Generate"
        onCancel={() => setBatchModalVisible(false)}
        onOk={() => void handleBatchGenerate()}
        okText="Start Generation"
        cancelText="Cancel"
        confirmLoading={batchGenerating}
      >
        <div style={{ marginBottom: 16 }}>
          <Text>Number of assets to generate:</Text>
          <InputNumber
            min={1}
            max={10}
            value={batchCount}
            onChange={(v) => setBatchCount(v || 1)}
            style={{ marginLeft: 8, width: 100 }}
          />
        </div>
        <div style={{ marginBottom: 16 }}>
          <Text>Model:</Text>
          <div style={{ marginTop: 4 }}>
            <Tag color="blue">doubao-seedream-5-0-pro-260628</Tag>
          </div>
        </div>
        <div style={{ marginBottom: 16 }}>
          <Text>Dimensions:</Text>
          <div style={{ marginTop: 4 }}>
            <Tag>2048×2048 (1:1)</Tag>
          </div>
        </div>
        <Alert
          type="info"
          message="Batch generation will create multiple assets in parallel"
          description={`Estimated cost: ${batchCount} × ¥0.03 = ¥${(batchCount * 0.03).toFixed(2)}`}
          showIcon
        />
      </Modal>
    </div>
  )
}

// ── QC Result Display Component ────────────────────────────────────────
function QcResultDisplay({ qc }: { qc: QcResult }) {
  const items: { label: string; passed: boolean; score: number; notes?: string; issues?: string[] }[] = [
    { label: 'Image Integrity', passed: qc.image_integrity?.passed ?? false, score: qc.image_integrity?.score ?? 0, notes: '', issues: qc.image_integrity?.issues },
    { label: 'Product Presence', passed: qc.product_presence?.passed ?? false, score: qc.product_presence?.score ?? 0, notes: qc.product_presence?.notes },
    { label: 'Visual Quality', passed: qc.visual_quality?.passed ?? false, score: qc.visual_quality?.score ?? 0, notes: '', issues: qc.visual_quality?.issues },
    { label: 'Composition', passed: qc.composition?.passed ?? false, score: qc.composition?.score ?? 0, notes: qc.composition?.notes },
    { label: 'Color Consistency', passed: qc.color_consistency?.passed ?? false, score: qc.color_consistency?.score ?? 0, notes: qc.color_consistency?.notes },
    { label: 'Background Quality', passed: qc.background_quality?.passed ?? false, score: qc.background_quality?.score ?? 0, notes: qc.background_quality?.notes },
    { label: 'Text Artifact', passed: qc.text_artifact?.passed ?? false, score: qc.text_artifact?.score ?? 0, notes: '', issues: qc.text_artifact?.issues },
    { label: 'Brand Consistency', passed: qc.brand_consistency?.passed ?? false, score: qc.brand_consistency?.score ?? 0, notes: qc.brand_consistency?.notes },
    { label: 'Policy Flags', passed: qc.policy_flags?.passed ?? false, score: 0, notes: '', issues: qc.policy_flags?.flags },
  ]

  return (
    <div>
      {/* Vision Analysis Flag */}
      {qc.vision_analysis_performed === false && (
        <Alert
          type="warning"
          message="Text-only analysis (no vision model)"
          description="AI QC was performed using text metadata only. Visual inspection was not possible."
          showIcon
          style={{ marginBottom: 12 }}
        />
      )}

      {/* Overall Score */}
      <div style={{ marginBottom: 12, textAlign: 'center' }}>
        <Statistic
          title="Overall Score"
          value={qc.overall_score || 0}
          precision={1}
          suffix="/5"
          valueStyle={{
            color: (qc.overall_score || 0) >= 3.5 ? '#52c41a' : (qc.overall_score || 0) >= 2.5 ? '#faad14' : '#f5222d',
            fontSize: 32,
          }}
        />
        <Text type="secondary">
          Confidence: {qc.confidence ? `${(qc.confidence * 100).toFixed(0)}%` : '-'}
          {' · '}
          Recommendation: <Tag color={qc.recommendation === 'approve' ? 'success' : qc.recommendation === 'reject' ? 'error' : 'warning'}>
            {qc.recommendation || 'unknown'}
          </Tag>
        </Text>
      </div>

      {/* Individual Checks */}
      <Row gutter={[8, 8]}>
        {items.map((item, i) => (
          <Col span={8} key={i}>
            <div style={{
              padding: 8,
              borderRadius: 4,
              background: item.passed ? '#f6ffed' : '#fff2f0',
              border: `1px solid ${item.passed ? '#b7eb8f' : '#ffccc7'}`,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                <Text strong style={{ fontSize: 11 }}>{item.label}</Text>
                <Tag color={item.passed ? 'success' : 'error'} style={{ fontSize: 10, lineHeight: '16px' }}>
                  {item.passed ? 'PASS' : 'FAIL'}
                </Tag>
              </div>
              <Progress
                percent={(item.score / 5) * 100}
                size="small"
                showInfo={false}
                strokeColor={item.score >= 3.5 ? '#52c41a' : item.score >= 2.5 ? '#faad14' : '#f5222d'}
              />
              {item.notes && <Text type="secondary" style={{ fontSize: 10, display: 'block', marginTop: 4 }}>{item.notes}</Text>}
              {item.issues && item.issues.length > 0 && (
                <ul style={{ fontSize: 10, margin: '4px 0 0', paddingLeft: 16 }}>
                  {item.issues.map((issue, j) => <li key={j}>{issue}</li>)}
                </ul>
              )}
            </div>
          </Col>
        ))}
      </Row>
    </div>
  )
}