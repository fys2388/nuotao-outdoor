import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Image,
  Input,
  InputNumber,
  Modal,
  Progress,
  Row,
  Segmented,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExperimentOutlined,
  FileSearchOutlined,
  PictureOutlined,
  PlusOutlined,
  ReloadOutlined,
  RocketOutlined,
  SearchOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useAuth } from '../auth/AuthProvider'

const { Title, Text, Paragraph } = Typography

const CANDIDATE_STATUSES = ['candidate', 'approved', 'testing', 'winner', 'rejected'] as const
type CandidateStatus = (typeof CANDIDATE_STATUSES)[number]

const STATUS_META: Record<CandidateStatus, { label: string; color: string }> = {
  candidate: { label: '待评估', color: 'blue' },
  approved: { label: '已通过', color: 'cyan' },
  testing: { label: '测试中', color: 'orange' },
  winner: { label: '已胜出', color: 'green' },
  rejected: { label: '已淘汰', color: 'red' },
}

const SCORE_LABELS: Record<string, string> = {
  profit: '利润',
  logistics: '物流',
  demand: '需求',
  competition: '竞争',
  differentiation: '差异化',
  compliance: '合规',
}

interface CandidateScore {
  id: string
  total: string
  profit: string
  logistics: string
  demand: string
  competition: string
  differentiation: string
  compliance: string
  model_version: string
  rule_version: string
  scored_at: string
  evidence?: ScoreEvidence[]
}

interface ScoreEvidence {
  id: string
  dimension: string
  score: string
  source: string
  evidence: unknown[]
  confidence: string
  version: string
}

interface CandidateCost {
  id: string
  currency: string
  purchase_cost: string
  total_landed_cost: string
  total_cost: string
  version: string
  valid_from: string
}

interface Candidate {
  id: string
  sku: string
  name: string
  description: string | null
  category: string | null
  status: string
  candidate_status: CandidateStatus
  source: string
  source_url: string | null
  target_market: string
  weight_kg: string | null
  dimensions?: Record<string, unknown> | null
  attributes?: Record<string, unknown>
  meta?: Record<string, any>
  latest_score: CandidateScore | null
  latest_cost: CandidateCost | null
  created_at: string | null
  updated_at: string | null
}

interface ProductSourceRecord {
  id: string
  source_type: string
  source_url: string | null
  captured_at: string
  raw_data: Record<string, any>
}

interface ProductImageTask {
  id: string
  use_case: string
  status: string
  image_url: string | null
  image_path: string | null
  error_message: string | null
  created_at: string
}

interface CandidateListResponse {
  products: Candidate[]
  total: number
}

interface ProductIntelligenceResponse {
  product: Candidate
  score: CandidateScore | null
  decision: {
    id: string
    decision: string
    approval_status: string
    reasons: unknown[]
    risks: unknown[]
    created_at: string
  } | null
}

interface NuotaoV3Finding {
  rule_id: string
  status: 'pass' | 'fail' | 'pending'
  detail: string
}

interface NuotaoV3Evaluation {
  score_id: string
  product_id: string
  nuotao_total: number
  grade: string | null
  dimensions: Record<string, number>
  reject_reasons: NuotaoV3Finding[]
  dimension_evidence?: Record<string, unknown>
  funnel_stage?: string | null
  scored_at?: string | null
}

const NUOTAO_GRADE_META: Record<string, { label: string; color: string }> = {
  hero: { label: 'Hero', color: 'green' },
  core: { label: 'Core', color: 'blue' },
  long_tail: { label: 'Long-tail', color: 'gold' },
  reject: { label: 'Reject', color: 'red' },
}

const FUNNEL_META: Record<string, { label: string; color: string }> = {
  recalled: { label: '召回', color: 'default' },
  screened: { label: '初筛', color: 'default' },
  deep_candidate: { label: '深评', color: 'cyan' },
  test_candidate: { label: '测试候选', color: 'blue' },
  testing: { label: '测试中', color: 'orange' },
  hero: { label: 'Hero', color: 'green' },
  rejected: { label: '已否决', color: 'red' },
}

const NUOTAO_DIM_LABELS: Array<[string, string]> = [
  ['value', 'Value 价值'],
  ['utility', 'Utility 效用'],
  ['weight_packability', 'Weight 易运'],
  ['durability', 'Durability 耐用'],
  ['brand_fit', 'Brand Fit 品牌'],
  ['differentiation', 'Differentiation 差异'],
]

interface IntakeFormValues {
  title: string
  sku?: string
  category?: string
  source_url?: string
  source_type: '1688' | 'MANUAL' | 'OTHER'
  supplier_code?: string
  purchase_cost: number
  domestic_shipping?: number
  first_leg_shipping?: number
  last_leg_shipping?: number
  weight_kg?: number
  target_market: string
  currency: string
}

function apiErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.traceId ? `${error.message}（Trace: ${error.traceId}）` : error.message
  }
  return error instanceof Error ? error.message : '未知错误'
}

function numeric(value: unknown): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function money(value: unknown, currencyCode = 'CNY'): string {
  return `${currencyCode} ${numeric(value).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

function statusTag(status: CandidateStatus) {
  const meta = STATUS_META[status] || { label: status, color: 'default' }
  return <Tag color={meta.color}>{meta.label}</Tag>
}

function scoreColor(score: number): string {
  if (score >= 75) return '#2f8b64'
  if (score >= 60) return '#c27622'
  return '#b64a4a'
}

export default function ProductCandidatesPage() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<'all' | CandidateStatus>('all')
  const [search, setSearch] = useState('')
  const [detail, setDetail] = useState<ProductIntelligenceResponse | null>(null)
  const [detailCost, setDetailCost] = useState<CandidateCost | null>(null)
  const [detailSources, setDetailSources] = useState<ProductSourceRecord[]>([])
  const [detailImages, setDetailImages] = useState<ProductImageTask[]>([])
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [contentLoading, setContentLoading] = useState<string | null>(null)
  const [intakeOpen, setIntakeOpen] = useState(false)
  const [intakeSubmitting, setIntakeSubmitting] = useState(false)
  const [form] = Form.useForm<IntakeFormValues>()
  const [nuotaoMap, setNuotaoMap] = useState<Record<string, NuotaoV3Evaluation>>({})
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([])
  const [v3BatchLoading, setV3BatchLoading] = useState(false)

  const loadCandidates = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = (await api.getSourcingCandidates(
        'all',
        200,
        0,
      )) as CandidateListResponse
      const products = response.products || []
      setCandidates(products)
      const ids = products.map((product) => product.id)
      if (ids.length === 0) {
        setNuotaoMap({})
      } else {
        try {
          const v3 = (await api.getNuotaoV3LatestBatch(ids)) as {
            items: Record<string, NuotaoV3Evaluation>
          }
          setNuotaoMap(v3.items || {})
        } catch {
          setNuotaoMap({})
        }
      }
    } catch (loadError) {
      setCandidates([])
      setError(apiErrorMessage(loadError))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadCandidates()
  }, [loadCandidates])

  const stats = useMemo(() => {
    const scored = candidates.filter((candidate) => candidate.latest_score)
    return {
      total: candidates.length,
      pending: candidates.filter((candidate) => candidate.candidate_status === 'candidate').length,
      testing: candidates.filter((candidate) => candidate.candidate_status === 'testing').length,
      winners: candidates.filter((candidate) => candidate.candidate_status === 'winner').length,
      averageScore: scored.length
        ? scored.reduce(
            (total, candidate) => total + numeric(candidate.latest_score?.total),
            0,
          ) / scored.length
        : 0,
    }
  }, [candidates])

  const filteredCandidates = useMemo(() => {
    const keyword = search.trim().toLowerCase()
    return candidates.filter((candidate) => {
      const statusMatches =
        statusFilter === 'all' || candidate.candidate_status === statusFilter
      const searchMatches =
        !keyword ||
        [candidate.name, candidate.sku, candidate.category, candidate.source_url]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(keyword))
      return statusMatches && searchMatches
    })
  }, [candidates, search, statusFilter])

  const openDetail = async (candidate: Candidate) => {
    setDetailOpen(true)
    setDetailLoading(true)
    setDetail(null)
    setDetailCost(candidate.latest_cost)
    try {
      const [intelligence, costs, sources, imageTasks] = await Promise.all([
        api.getProductIntelligence(candidate.id) as Promise<ProductIntelligenceResponse>,
        api.getProductCostSnapshots(candidate.id) as Promise<CandidateCost[]>,
        api.getProductSources(candidate.id) as Promise<ProductSourceRecord[]>,
        api.getImageTasks(candidate.id) as Promise<{ tasks: ProductImageTask[] }>,
      ])
      const score = intelligence.score
      if (score?.id) {
        const evidence = (await api.getProductScoreEvidence(score.id)) as ScoreEvidence[]
        setDetail({
          ...intelligence,
          score: { ...score, evidence },
        })
      } else {
        setDetail(intelligence)
      }
      setDetailCost(costs[0] || candidate.latest_cost)
      setDetailSources(sources || [])
      setDetailImages(imageTasks.tasks || [])
    } catch (detailError) {
      message.error(`候选详情加载失败：${apiErrorMessage(detailError)}`)
    } finally {
      setDetailLoading(false)
    }
  }

  const generateEnglishContent = async (candidate: Candidate) => {
    setContentLoading(`copy:${candidate.id}`)
    try {
      await api.generateProductCopy(candidate.id)
      message.success('英文商品文案已生成，请核查后确认用于上架')
      await refreshDetail(candidate.id)
    } catch (actionError) {
      message.error(`AI 英文文案生成失败：${apiErrorMessage(actionError)}`)
    } finally {
      setContentLoading(null)
    }
  }

  const approveEnglishContent = async (candidate: Candidate) => {
    setContentLoading(`approve:${candidate.id}`)
    try {
      await api.approveProductLocalization(candidate.id, 'en', user?.username || 'admin')
      message.success('英文文案已确认，可用于商品上架')
      await refreshDetail(candidate.id)
    } catch (actionError) {
      message.error(`英文文案确认失败：${apiErrorMessage(actionError)}`)
    } finally {
      setContentLoading(null)
    }
  }

  const generateMainImage = (candidate: Candidate) => {
    Modal.confirm({
      title: `AI 生成主图：${candidate.name}`,
      content: '图片生成会产生模型费用。生成结果不会自动上架，需要人工审核。',
      okText: '开始生成',
      cancelText: '取消',
      onOk: async () => {
        setContentLoading(`image:${candidate.id}`)
        try {
          const report = detail?.product?.meta?.analysis?.product_report || {}
          const prompt = [
            `Professional ecommerce main image for ${candidate.name}`,
            report.product_category ? `Category: ${report.product_category}` : '',
            report.material_craft ? `Materials: ${report.material_craft}` : '',
            report.primary_colors ? `Colors: ${JSON.stringify(report.primary_colors)}` : '',
            'Outdoor camping product, realistic photography, clean light background, no text, no watermark',
          ].filter(Boolean).join('. ')
          await api.generateProductImage({
            productId: candidate.id,
            prompt,
            useCase: 'main_image',
          })
          message.success('主图已生成，请在媒体区审核')
          await refreshDetail(candidate.id)
        } catch (actionError) {
          message.error(`主图生成失败：${apiErrorMessage(actionError)}`)
          throw actionError
        } finally {
          setContentLoading(null)
        }
      },
    })
  }

  const approveImageTask = async (candidate: Candidate, task: ProductImageTask) => {
    setContentLoading(`image-approve:${task.id}`)
    try {
      await api.approveProductImage(task.id, user?.username || 'admin')
      message.success('图片已审核通过，可写入商品主图或详情图')
      await refreshDetail(candidate.id)
    } catch (actionError) {
      message.error(`图片审核失败：${apiErrorMessage(actionError)}`)
    } finally {
      setContentLoading(null)
    }
  }

  const rejectImageTask = async (candidate: Candidate, task: ProductImageTask) => {
    setContentLoading(`image-reject:${task.id}`)
    try {
      await api.rejectProductImage(task.id)
      message.success('图片已拒绝')
      await refreshDetail(candidate.id)
    } catch (actionError) {
      message.error(`图片拒绝失败：${apiErrorMessage(actionError)}`)
    } finally {
      setContentLoading(null)
    }
  }

  const attachImageTask = async (
    candidate: Candidate,
    task: ProductImageTask,
    placement: 'main' | 'detail',
  ) => {
    setContentLoading(`image-attach:${task.id}:${placement}`)
    try {
      await api.attachProductImage(
        candidate.id,
        task.id,
        placement,
        user?.username || 'admin',
      )
      message.success(placement === 'main' ? '已设为商品主图' : '已加入商品详情图')
      await refreshDetail(candidate.id)
    } catch (actionError) {
      message.error(`写入商品媒体失败：${apiErrorMessage(actionError)}`)
    } finally {
      setContentLoading(null)
    }
  }

  const refreshDetail = async (candidateId: string) => {
    await loadCandidates()
    const updated = (await api.getSourcingCandidates('all', 200, 0)) as CandidateListResponse
    const candidate = updated.products.find((item) => item.id === candidateId)
    if (candidate && detailOpen) await openDetail(candidate)
  }

  const analyzeCandidate = async (candidate: Candidate) => {
    setActionLoading(`score:${candidate.id}`)
    try {
      await api.analyzeProduct(candidate.id)
      message.success('六维评分已重新计算并写入审计记录')
      await refreshDetail(candidate.id)
    } catch (actionError) {
      message.error(`评分失败：${apiErrorMessage(actionError)}`)
    } finally {
      setActionLoading(null)
    }
  }

  const evaluateV3 = async (candidate: Candidate) => {
    setActionLoading(`v3:${candidate.id}`)
    try {
      const result = (await api.evaluateNuotaoV3(candidate.id)) as {
        evaluation: NuotaoV3Evaluation & {
          funnel_stage: string
          veto: { failed: string[]; pending: string[]; vetoed: boolean }
        }
      }
      const evaluation = result.evaluation
      message.success(
        `V3.0 评估完成：${evaluation.grade || '—'} ${numeric(
          evaluation.nuotao_total,
        ).toFixed(1)} 分（${evaluation.funnel_stage}）`,
      )
      await loadCandidates()
      if (detailOpen) await refreshDetail(candidate.id)
    } catch (actionError) {
      message.error(`V3.0 评估失败：${apiErrorMessage(actionError)}`)
    } finally {
      setActionLoading(null)
    }
  }

  const evaluateV3Batch = async () => {
    const ids = selectedRowKeys
    if (!ids.length) {
      message.info('请先勾选要评估的候选商品')
      return
    }
    setV3BatchLoading(true)
    try {
      const result = (await api.evaluateNuotaoV3Batch(ids)) as {
        count: number
        skipped?: Array<{ product_id: string; reason: string }>
        errors: Array<{ product_id: string; error: string }>
      }
      const failed = result.errors?.length || 0
      const skippedCount = result.skipped?.length || 0
      message.success(
        `V3.0 批量评估完成 ${result.count} 条` +
          (skippedCount ? `，跳过 ${skippedCount} 条（已删/缺失）` : '') +
          (failed ? `，${failed} 条失败` : ''),
      )
      setSelectedRowKeys([])
      await loadCandidates()
    } catch (actionError) {
      message.error(`批量评估失败：${apiErrorMessage(actionError)}`)
    } finally {
      setV3BatchLoading(false)
    }
  }

  const moveCandidate = (candidate: Candidate, status: CandidateStatus) => {
    const nextLabel = STATUS_META[status].label
    Modal.confirm({
      title: `${nextLabel}：${candidate.name}`,
      content: '该动作会写入候选状态机审计记录，且必须由人工操作。',
      okText: '确认',
      cancelText: '取消',
      onOk: async () => {
        setActionLoading(`status:${candidate.id}`)
        try {
          await api.updateProductCandidateStatus(candidate.id, {
            status,
            actor: user?.username || 'admin',
          })
          message.success(`候选状态已更新为“${nextLabel}”`)
          await refreshDetail(candidate.id)
        } catch (actionError) {
          message.error(`状态更新失败：${apiErrorMessage(actionError)}`)
          throw actionError
        } finally {
          setActionLoading(null)
        }
      },
    })
  }

  const promoteCandidate = (candidate: Candidate) => {
    Modal.confirm({
      title: `提交商品上架审批：${candidate.name}`,
      content: '审批通过后只生成 WooCommerce 草稿数据，不会直接发布商品。',
      okText: '提交审批',
      cancelText: '取消',
      onOk: async () => {
        setActionLoading(`promote:${candidate.id}`)
        try {
          await api.promoteProductCandidate(candidate.id, {
            actor: user?.username || 'admin',
          })
          message.success('上架审批已提交，请到审批中心处理')
          await refreshDetail(candidate.id)
        } catch (actionError) {
          message.error(`提交审批失败：${apiErrorMessage(actionError)}`)
          throw actionError
        } finally {
          setActionLoading(null)
        }
      },
    })
  }

  const submitIntake = async (values: IntakeFormValues) => {
    setIntakeSubmitting(true)
    try {
      await api.intakeProduct({
        ...values,
        description: values.title,
        domestic_shipping: values.domestic_shipping || 0,
        first_leg_shipping: values.first_leg_shipping || 0,
        last_leg_shipping: values.last_leg_shipping || 0,
      })
      message.success('候选商品已录入并完成首轮评分')
      setIntakeOpen(false)
      form.resetFields()
      await loadCandidates()
    } catch (submitError) {
      message.error(`录入失败：${apiErrorMessage(submitError)}`)
    } finally {
      setIntakeSubmitting(false)
    }
  }

  const columns: ColumnsType<Candidate> = [
    {
      title: '候选商品',
      dataIndex: 'name',
      width: 300,
      render: (value: string, record) => (
        <div className="primary-cell">
          <strong>{value}</strong>
          <span>{record.sku}</span>
        </div>
      ),
    },
    {
      title: '来源',
      dataIndex: 'source',
      width: 110,
      render: (value: string, record) =>
        record.source_url ? (
          <Tooltip title={record.source_url}>
            <Tag color={value === '1688' ? 'orange' : 'default'}>{value || 'OTHER'}</Tag>
          </Tooltip>
        ) : (
          <Tag>{value || 'OTHER'}</Tag>
        ),
    },
    {
      title: '运营分(内部)',
      dataIndex: 'latest_score',
      width: 130,
      render: (score: CandidateScore | null) =>
        score ? (
          <Space size={8}>
            <Progress
              type="circle"
              size={36}
              percent={Math.round(numeric(score.total))}
              strokeColor={scoreColor(numeric(score.total))}
              format={(value) => value}
            />
            <Text type="secondary">{score.rule_version}</Text>
          </Space>
        ) : (
          <Text type="secondary">未评分</Text>
        ),
    },
    {
      title: 'Nuotao 分 / 漏斗',
      key: 'nuotao_v3',
      width: 158,
      render: (_, record) => {
        const v3 = nuotaoMap[record.id]
        if (!v3) return <Text type="secondary">未评估</Text>
        const grade =
          NUOTAO_GRADE_META[v3.grade || ''] || {
            label: v3.grade || '—',
            color: 'default',
          }
        const funnel = v3.funnel_stage ? FUNNEL_META[v3.funnel_stage] : null
        const hardFailed = (v3.reject_reasons || []).filter(
          (finding) => finding.status === 'fail',
        ).length
        return (
          <div className="primary-cell">
            <Space size={4} wrap>
              <Tag color={grade.color}>{grade.label}</Tag>
              <strong>{numeric(v3.nuotao_total).toFixed(1)}</strong>
              {hardFailed > 0 && <Tag color="red">否决×{hardFailed}</Tag>}
            </Space>
            {funnel && (
              <Tag color={funnel.color} style={{ marginTop: 2 }}>
                {funnel.label}
              </Tag>
            )}
          </div>
        )
      },
    },
    {
      title: '落地成本',
      dataIndex: 'latest_cost',
      width: 145,
      render: (cost: CandidateCost | null) =>
        cost ? (
          <div className="primary-cell">
            <strong>{money(cost.total_landed_cost, cost.currency)}</strong>
            <span>采购 {money(cost.purchase_cost, cost.currency)}</span>
          </div>
        ) : (
          <Text type="secondary">待补充</Text>
        ),
    },
    {
      title: '状态',
      dataIndex: 'candidate_status',
      width: 100,
      render: (status: CandidateStatus) => statusTag(status),
    },
    {
      title: '目标市场',
      dataIndex: 'target_market',
      width: 100,
    },
    {
      title: '操作',
      key: 'actions',
      fixed: 'right',
      width: 260,
      render: (_, record) => (
        <Space size={4}>
          <Button type="link" size="small" onClick={() => void openDetail(record)}>
            查看
          </Button>
          <Button
            type="link"
            size="small"
            icon={<ThunderboltOutlined />}
            loading={actionLoading === `score:${record.id}`}
            onClick={() => void analyzeCandidate(record)}
          >
            评分
          </Button>
          <Button
            type="link"
            size="small"
            icon={<ExperimentOutlined />}
            loading={actionLoading === `v3:${record.id}`}
            onClick={() => void evaluateV3(record)}
          >
            V3评估
          </Button>
          {record.candidate_status === 'candidate' && (
            <Button
              type="link"
              size="small"
              onClick={() => moveCandidate(record, 'approved')}
            >
              通过
            </Button>
          )}
          {record.candidate_status === 'approved' && (
            <Button
              type="link"
              size="small"
              onClick={() => moveCandidate(record, 'testing')}
            >
              测试
            </Button>
          )}
          {record.candidate_status === 'testing' && (
            <Button
              type="link"
              size="small"
              onClick={() => moveCandidate(record, 'winner')}
            >
              胜出
            </Button>
          )}
        </Space>
      ),
    },
  ]

  const detailCandidate = detail?.product
  const detailScore = detail?.score || detailCandidate?.latest_score || null
  const detailNuotao = detailCandidate ? nuotaoMap[detailCandidate.id] || null : null
  const englishLocalization = detailCandidate?.meta?.localizations?.en
  const englishGenerated = Boolean(englishLocalization?.title)
  const englishApproved = englishLocalization?.status === 'approved'
  const sourceImages = useMemo(() => {
    const urls = new Set<string>()
    for (const source of detailSources) {
      const candidates = source.raw_data?.images || source.raw_data?.image_urls || []
      for (const image of candidates) {
        const url = typeof image === 'string' ? image : image?.url || image?.src
        if (typeof url === 'string' && /^https?:\/\//.test(url)) urls.add(url)
      }
    }
    const media = detailCandidate?.meta?.media
    const stored = media?.images || detailCandidate?.meta?.images || []
    for (const image of stored) {
      if (typeof image === 'string' && /^https?:\/\//.test(image)) urls.add(image)
    }
    return Array.from(urls)
  }, [detailCandidate, detailSources])
  const generatedImages = detailImages
    .map((task) => task.image_url || task.image_path)
    .filter((url): url is string => Boolean(url))

  return (
    <div className="resource-page">
      <div className="page-heading">
        <div>
          <div className="page-kicker">PRODUCT SOURCING</div>
          <Title level={2}>候选产品与选品</Title>
          <Paragraph>
            候选商品、六维评分、落地成本和人工选品状态统一在这里管理，支持从 1688
            链接或 AI 产品分析结果进入。
          </Paragraph>
        </div>
        <Space wrap>
          <Button
            icon={<ExperimentOutlined />}
            loading={v3BatchLoading}
            disabled={selectedRowKeys.length === 0}
            onClick={() => void evaluateV3Batch()}
          >
            V3批量评估{selectedRowKeys.length ? `（${selectedRowKeys.length}）` : ''}
          </Button>
          <Button icon={<ReloadOutlined />} onClick={() => void loadCandidates()} loading={loading}>
            刷新
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              form.setFieldsValue({
                source_type: '1688',
                target_market: 'US',
                currency: 'CNY',
                purchase_cost: 0,
              })
              setIntakeOpen(true)
            }}
          >
            录入候选
          </Button>
        </Space>
      </div>

      {error && (
        <Alert
          className="page-alert"
          type="error"
          showIcon
          title="候选商品加载失败"
          description={error}
        />
      )}

      <Row gutter={[14, 14]} className="resource-metrics">
        <Col xs={12} lg={6}>
          <Card variant="borderless">
            <Statistic title="候选总数" value={stats.total} prefix={<FileSearchOutlined />} />
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card variant="borderless">
            <Statistic title="待评估" value={stats.pending} />
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card variant="borderless">
            <Statistic title="测试中" value={stats.testing} prefix={<ExperimentOutlined />} />
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card variant="borderless">
            <Statistic
              title="平均评分"
              value={stats.averageScore}
              precision={1}
              suffix="/ 100"
              prefix={<RocketOutlined />}
            />
          </Card>
        </Col>
      </Row>

      <Card variant="borderless" className="resource-panel">
        <div className="resource-toolbar">
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索商品、SKU、分类或来源链接"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <Segmented
            value={statusFilter}
            onChange={(value) => setStatusFilter(value as 'all' | CandidateStatus)}
            options={[
              { value: 'all', label: '全部' },
              ...CANDIDATE_STATUSES.map((status) => ({
                value: status,
                label: STATUS_META[status].label,
              })),
            ]}
          />
          <Text type="secondary">当前展示 {filteredCandidates.length} 条</Text>
        </div>

        <Table
          rowKey="id"
          rowSelection={{
            selectedRowKeys,
            onChange: (keys) => setSelectedRowKeys(keys as string[]),
          }}
          loading={loading}
          columns={columns}
          dataSource={filteredCandidates}
          scroll={{ x: 1320 }}
          pagination={{
            pageSize: 20,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 条`,
          }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="候选池为空"
              >
                <Space>
                  <Button onClick={() => navigate('/products/analysis')}>去 AI 产品分析</Button>
                  <Button type="primary" onClick={() => setIntakeOpen(true)}>
                    手工录入
                  </Button>
                </Space>
              </Empty>
            ),
          }}
        />
      </Card>

      <Drawer
        width={720}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        title={detailCandidate?.name || '候选商品详情'}
        loading={detailLoading}
        extra={
          detailCandidate && (
            <Space wrap>
              <Button
                icon={<FileSearchOutlined />}
                loading={contentLoading === `copy:${detailCandidate.id}`}
                onClick={() => void generateEnglishContent(detailCandidate)}
              >
                {englishGenerated ? '重新生成英文文案' : '生成英文文案'}
              </Button>
              {englishGenerated && !englishApproved && (
                <Button
                  type="primary"
                  icon={<CheckCircleOutlined />}
                  loading={contentLoading === `approve:${detailCandidate.id}`}
                  onClick={() => void approveEnglishContent(detailCandidate)}
                >
                  确认英文文案
                </Button>
              )}
              {englishApproved && <Tag color="green">英文文案已确认</Tag>}
              <Button
                icon={<ThunderboltOutlined />}
                loading={actionLoading === `score:${detailCandidate.id}`}
                onClick={() => void analyzeCandidate(detailCandidate)}
              >
                重新评分
              </Button>
              {detailCandidate.candidate_status === 'candidate' && (
                <Button
                  type="primary"
                  icon={<CheckCircleOutlined />}
                  onClick={() => moveCandidate(detailCandidate, 'approved')}
                >
                  通过选品
                </Button>
              )}
              {detailCandidate.candidate_status === 'approved' && (
                <Button
                  type="primary"
                  icon={<ExperimentOutlined />}
                  onClick={() => moveCandidate(detailCandidate, 'testing')}
                >
                  进入测试
                </Button>
              )}
              {detailCandidate.candidate_status === 'testing' && (
                <Button
                  type="primary"
                  icon={<CheckCircleOutlined />}
                  onClick={() => moveCandidate(detailCandidate, 'winner')}
                >
                  标记胜出
                </Button>
              )}
              {detailCandidate.candidate_status === 'winner' && (
                <Button
                  type="primary"
                  icon={<RocketOutlined />}
                  onClick={() => promoteCandidate(detailCandidate)}
                >
                  提交上架审批
                </Button>
              )}
              {!['winner', 'rejected'].includes(detailCandidate.candidate_status) && (
                <Button
                  danger
                  icon={<CloseCircleOutlined />}
                  onClick={() => moveCandidate(detailCandidate, 'rejected')}
                >
                  淘汰
                </Button>
              )}
            </Space>
          )
        }
      >
        {detailCandidate && (
          <Space direction="vertical" size={18} style={{ width: '100%' }}>
            <Descriptions
              size="small"
              column={2}
              items={[
                { key: 'sku', label: 'SKU', children: detailCandidate.sku },
                {
                  key: 'status',
                  label: '候选状态',
                  children: statusTag(detailCandidate.candidate_status),
                },
                { key: 'category', label: '分类', children: detailCandidate.category || '-' },
                { key: 'market', label: '目标市场', children: detailCandidate.target_market },
                {
                  key: 'source',
                  label: '来源',
                  span: 2,
                  children: detailCandidate.source_url ? (
                    <a href={detailCandidate.source_url} target="_blank" rel="noreferrer">
                      {detailCandidate.source_url}
                    </a>
                  ) : (
                    detailCandidate.source
                  ),
                },
              ]}
            />

            <Card variant="borderless" title="商品内容">
              <Descriptions
                size="small"
                column={2}
                items={[
                  {
                    key: 'weight',
                    label: '重量',
                    children: detailCandidate.weight_kg
                      ? `${detailCandidate.weight_kg} kg`
                      : '待补充',
                  },
                  {
                    key: 'dimensions',
                    label: '尺寸',
                    children: detailCandidate.dimensions
                      ? JSON.stringify(detailCandidate.dimensions)
                      : '待补充',
                  },
                  {
                    key: 'description',
                    label: '原始描述',
                    span: 2,
                    children: (
                      <Paragraph style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
                        {detailCandidate.description || '尚未持久化商品描述'}
                      </Paragraph>
                    ),
                  },
                  {
                    key: 'english',
                    label: '英文文案',
                    span: 2,
                    children: englishGenerated ? (
                      <Space direction="vertical" size={6} style={{ width: '100%' }}>
                        <Space wrap>
                          <Tag color={englishApproved ? 'green' : 'orange'}>
                            {englishApproved ? '已确认' : '待确认'}
                          </Tag>
                          <Text strong>{englishLocalization.title}</Text>
                        </Space>
                        <Paragraph style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
                          {englishLocalization.description}
                        </Paragraph>
                        {Array.isArray(englishLocalization.bullet_points) && (
                          <Space wrap>
                            {englishLocalization.bullet_points.map((item: string) => (
                              <Tag key={item}>{item}</Tag>
                            ))}
                          </Space>
                        )}
                      </Space>
                    ) : (
                      <Text type="secondary">尚未生成英文文案</Text>
                    ),
                  },
                ]}
              />
            </Card>

            <Card
              variant="borderless"
              title="商品图片与媒体"
              extra={
                <Button
                  icon={<PictureOutlined />}
                  loading={contentLoading === `image:${detailCandidate.id}`}
                  onClick={() => generateMainImage(detailCandidate)}
                >
                  AI 生成主图
                </Button>
              }
            >
              {(sourceImages.length > 0 || generatedImages.length > 0) ? (
                <Image.PreviewGroup>
                  <Space wrap size={12}>
                    {[...sourceImages, ...generatedImages].map((url, index) => (
                      <Space key={`${url}-${index}`} direction="vertical" size={4}>
                        <Image
                          src={url}
                          alt={`商品图片 ${index + 1}`}
                          width={150}
                          height={150}
                          style={{ objectFit: 'cover', borderRadius: 8 }}
                        />
                        <Text type="secondary" style={{ fontSize: 11 }}>
                          {index < sourceImages.length ? '1688 原图' : 'AI 生成图'}
                        </Text>
                      </Space>
                    ))}
                  </Space>
                </Image.PreviewGroup>
              ) : (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="当前商品没有持久化图片，可使用 AI 生成主图"
                />
              )}
              {detailImages.length > 0 && (
                <Table
                  style={{ marginTop: 16 }}
                  rowKey="id"
                  size="small"
                  pagination={false}
                  dataSource={detailImages}
                  columns={[
                    { title: '用途', dataIndex: 'use_case', width: 120 },
                    {
                      title: '状态',
                      dataIndex: 'status',
                      width: 110,
                      render: (value: string) => (
                        <Tag color={value === 'approved' ? 'green' : value === 'failed' ? 'red' : 'blue'}>
                          {value}
                        </Tag>
                      ),
                    },
                    {
                      title: '图片',
                      dataIndex: 'image_url',
                      render: (value: string | null) =>
                        value ? (
                          <a href={value} target="_blank" rel="noreferrer">查看</a>
                        ) : '-',
                    },
                    {
                      title: '错误',
                      dataIndex: 'error_message',
                      ellipsis: true,
                      render: (value: string | null) => value || '-',
                    },
                    {
                      title: '操作',
                      key: 'actions',
                      width: 220,
                      render: (_: unknown, task: ProductImageTask) => (
                        <Space wrap size={4}>
                          {task.status === 'generated' && (
                            <>
                              <Button
                                size="small"
                                type="primary"
                                loading={contentLoading === `image-approve:${task.id}`}
                                onClick={() => void approveImageTask(detailCandidate, task)}
                              >
                                审核通过
                              </Button>
                              <Button
                                size="small"
                                danger
                                loading={contentLoading === `image-reject:${task.id}`}
                                onClick={() => void rejectImageTask(detailCandidate, task)}
                              >
                                拒绝
                              </Button>
                            </>
                          )}
                          {['approved', 'published'].includes(task.status) && (
                            <>
                              <Button
                                size="small"
                                type="primary"
                                loading={contentLoading === `image-attach:${task.id}:main`}
                                onClick={() => void attachImageTask(detailCandidate, task, 'main')}
                              >
                                设为主图
                              </Button>
                              <Button
                                size="small"
                                loading={contentLoading === `image-attach:${task.id}:detail`}
                                onClick={() => void attachImageTask(detailCandidate, task, 'detail')}
                              >
                                加入详情图
                              </Button>
                            </>
                          )}
                        </Space>
                      ),
                    },
                  ]}
                />
              )}
            </Card>

            <Card variant="borderless" title="商品属性">
              {Object.keys(detailCandidate.attributes || {}).length > 0 ? (
                <Descriptions
                  size="small"
                  column={2}
                  items={Object.entries(detailCandidate.attributes || {}).map(
                    ([key, value]) => ({
                      key,
                      label: key,
                      children: Array.isArray(value)
                        ? value.join(' / ')
                        : typeof value === 'object'
                          ? JSON.stringify(value)
                          : String(value),
                    }),
                  )}
                />
              ) : (
                <Text type="secondary">尚未持久化商品属性</Text>
              )}
            </Card>

            <Card variant="borderless" title="1688 原始数据">
              {detailSources.length > 0 ? (
                <Collapse
                  items={detailSources.map((source, index) => ({
                    key: source.id,
                    label: `${source.source_type} 原始快照 ${index + 1}`,
                    children: (
                      <pre style={{ maxHeight: 360, overflow: 'auto', whiteSpace: 'pre-wrap' }}>
                        {JSON.stringify(source.raw_data, null, 2)}
                      </pre>
                    ),
                  }))}
                />
              ) : (
                <Text type="secondary">暂无来源快照</Text>
              )}
            </Card>

            <Card
              variant="borderless"
              title={
                <Space>
                  <ExperimentOutlined />
                  <span>Nuotao Score V3.0（品牌双轨评分）</span>
                  {detailNuotao?.funnel_stage && FUNNEL_META[detailNuotao.funnel_stage] && (
                    <Tag color={FUNNEL_META[detailNuotao.funnel_stage].color}>
                      {FUNNEL_META[detailNuotao.funnel_stage].label}
                    </Tag>
                  )}
                </Space>
              }
              extra={
                detailCandidate ? (
                  <Button
                    size="small"
                    icon={<ExperimentOutlined />}
                    loading={actionLoading === `v3:${detailCandidate.id}`}
                    onClick={() => void evaluateV3(detailCandidate)}
                  >
                    重新评估
                  </Button>
                ) : null
              }
            >
              {detailNuotao ? (
                <Space direction="vertical" size={12} style={{ width: '100%' }}>
                  <Space size={16} wrap align="center">
                    <Tag
                      color={
                        (NUOTAO_GRADE_META[detailNuotao.grade || ''] || {}).color || 'default'
                      }
                    >
                      {(NUOTAO_GRADE_META[detailNuotao.grade || ''] || {}).label ||
                        detailNuotao.grade}
                    </Tag>
                    <Text strong style={{ fontSize: 22 }}>
                      {numeric(detailNuotao.nuotao_total).toFixed(1)}
                    </Text>
                    <Text type="secondary">
                      满分 100 · Value25 / Utility20 / Weight15 / Durability15 / Brand15 / Diff10
                    </Text>
                  </Space>
                  <Row gutter={[12, 10]}>
                    {NUOTAO_DIM_LABELS.map(([key, label]) => (
                      <Col span={12} key={key}>
                        <Text type="secondary">{label}</Text>
                        <Progress
                          percent={Math.round(
                            numeric(detailNuotao.dimensions?.[key]) * 10,
                          )}
                          size="small"
                          strokeColor={scoreColor(
                            numeric(detailNuotao.dimensions?.[key]) * 10,
                          )}
                        />
                      </Col>
                    ))}
                  </Row>
                  <div>
                    <Text strong>一票否决 V1–V12（通过 / 待定 / 否决）</Text>
                    <div style={{ marginTop: 8 }}>
                      <Space size={[6, 6]} wrap>
                        {(detailNuotao.reject_reasons || []).map((finding) => (
                          <Tooltip key={finding.rule_id} title={finding.detail}>
                            <Tag
                              color={
                                finding.status === 'fail'
                                  ? 'red'
                                  : finding.status === 'pending'
                                    ? 'orange'
                                    : 'green'
                              }
                            >
                              {finding.rule_id} ·{' '}
                              {finding.status === 'fail'
                                ? '否决'
                                : finding.status === 'pending'
                                  ? '待定'
                                  : '通过'}
                            </Tag>
                          </Tooltip>
                        ))}
                      </Space>
                    </div>
                  </div>
                </Space>
              ) : (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="尚未执行 V3.0 评估，点击右上角“重新评估”生成品牌双轨评分与否决结论"
                />
              )}
            </Card>

            <Card variant="borderless" title="六维评分与证据">
              {detailScore ? (
                <Space direction="vertical" size={14} style={{ width: '100%' }}>
                  <Space size={20} wrap>
                    <Progress
                      type="dashboard"
                      percent={Math.round(numeric(detailScore.total))}
                      strokeColor={scoreColor(numeric(detailScore.total))}
                    />
                    <Space direction="vertical" size={2}>
                      <Text strong>模型 {detailScore.model_version}</Text>
                      <Text type="secondary">规则 {detailScore.rule_version}</Text>
                      <Text type="secondary">
                        评分时间 {new Date(detailScore.scored_at).toLocaleString()}
                      </Text>
                    </Space>
                  </Space>
                  <Row gutter={[12, 12]}>
                    {Object.keys(SCORE_LABELS).map((dimension) => (
                      <Col xs={12} md={8} key={dimension}>
                        <div className="score-dimension">
                          <Text type="secondary">{SCORE_LABELS[dimension]}</Text>
                          <Progress
                            percent={numeric(
                              (detailScore as unknown as Record<string, unknown>)[dimension],
                            ) * 10}
                            showInfo={false}
                            strokeColor={scoreColor(
                              numeric(
                                (detailScore as unknown as Record<string, unknown>)[dimension],
                              ) * 10,
                            )}
                          />
                          <Text strong>
                            {numeric(
                              (detailScore as unknown as Record<string, unknown>)[dimension],
                            ).toFixed(1)}
                            /10
                          </Text>
                        </div>
                      </Col>
                    ))}
                  </Row>
                  {detailScore.evidence && detailScore.evidence.length > 0 && (
                    <Table
                      rowKey="id"
                      size="small"
                      pagination={false}
                      dataSource={detailScore.evidence}
                      columns={[
                        {
                          title: '维度',
                          dataIndex: 'dimension',
                          width: 90,
                          render: (value: string) => SCORE_LABELS[value] || value,
                        },
                        {
                          title: '评分',
                          dataIndex: 'score',
                          width: 70,
                          render: (value: string) => numeric(value).toFixed(1),
                        },
                        { title: '来源', dataIndex: 'source', width: 120 },
                        {
                          title: '置信度',
                          dataIndex: 'confidence',
                          width: 90,
                          render: (value: string) => `${Math.round(numeric(value) * 100)}%`,
                        },
                        {
                          title: '证据',
                          dataIndex: 'evidence',
                          ellipsis: true,
                          render: (value: unknown[]) => JSON.stringify(value),
                        },
                      ]}
                    />
                  )}
                </Space>
              ) : (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="该候选还没有评分"
                >
                  <Button
                    type="primary"
                    icon={<ThunderboltOutlined />}
                    onClick={() => void analyzeCandidate(detailCandidate)}
                  >
                    立即评分
                  </Button>
                </Empty>
              )}
            </Card>

            <Card variant="borderless" title="最新成本">
              {detailCost ? (
                <Descriptions
                  size="small"
                  column={2}
                  items={[
                    {
                      key: 'purchase',
                      label: '采购成本',
                      children: money(detailCost.purchase_cost, detailCost.currency),
                    },
                    {
                      key: 'landed',
                      label: '总落地成本',
                      children: money(detailCost.total_landed_cost, detailCost.currency),
                    },
                    { key: 'version', label: '成本版本', children: detailCost.version },
                    {
                      key: 'valid',
                      label: '生效时间',
                      children: new Date(detailCost.valid_from).toLocaleString(),
                    },
                  ]}
                />
              ) : (
                <Text type="secondary">尚未记录成本快照，重新录入商品后会生成。</Text>
              )}
            </Card>
          </Space>
        )}
      </Drawer>

      <Modal
        open={intakeOpen}
        title="录入候选商品"
        okText="录入并评分"
        cancelText="取消"
        confirmLoading={intakeSubmitting}
        onCancel={() => setIntakeOpen(false)}
        onOk={() => form.submit()}
        destroyOnHidden
      >
        <Form<IntakeFormValues>
          form={form}
          layout="vertical"
          onFinish={(values) => void submitIntake(values)}
        >
          <Form.Item
            name="title"
            label="商品名称"
            rules={[{ required: true, message: '请输入商品名称' }]}
          >
            <Input placeholder="请输入候选商品名称" />
          </Form.Item>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="sku" label="SKU">
                <Input placeholder="留空则自动生成" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="category" label="分类">
                <Input placeholder="如：户外照明" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item
            name="source_url"
            label="来源链接"
            rules={[{ type: 'url', message: '请输入有效的 http(s) 链接' }]}
          >
            <Input placeholder="https://detail.1688.com/offer/..." />
          </Form.Item>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="source_type" label="来源类型" rules={[{ required: true }]}>
                <Select
                  options={[
                    { value: '1688', label: '1688' },
                    { value: 'MANUAL', label: '手工录入' },
                    { value: 'OTHER', label: '其他' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="supplier_code" label="供应商编码">
                <Input placeholder="可选" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item
                name="purchase_cost"
                label="采购成本"
                rules={[{ required: true, message: '请输入采购成本' }]}
              >
                <InputNumber min={0} precision={2} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="currency" label="币种">
                <Select
                  options={[
                    { value: 'CNY', label: 'CNY' },
                    { value: 'USD', label: 'USD' },
                    { value: 'EUR', label: 'EUR' },
                  ]}
                />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={12}>
            <Col span={8}>
              <Form.Item name="domestic_shipping" label="国内运费">
                <InputNumber min={0} precision={2} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="first_leg_shipping" label="头程运费">
                <InputNumber min={0} precision={2} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="last_leg_shipping" label="尾程运费">
                <InputNumber min={0} precision={2} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="weight_kg" label="重量（kg）">
                <InputNumber min={0.001} precision={3} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="target_market" label="目标市场">
                <Select
                  options={[
                    { value: 'US', label: '美国' },
                    { value: 'EU', label: '欧盟' },
                    { value: 'GB', label: '英国' },
                    { value: 'CA', label: '加拿大' },
                    { value: 'AU', label: '澳大利亚' },
                  ]}
                />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>
    </div>
  )
}
