import { useCallback, useEffect, useMemo, useState, type Key } from 'react'
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Col,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Select,
  Skeleton,
  Space,
  Statistic,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  ApartmentOutlined,
  BankOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  GlobalOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'
import { api, ApiError } from '../api/client'

const { Title, Text, Paragraph } = Typography
const { RangePicker } = DatePicker

type BusinessModel = 'B2C' | 'B2B'
type AttributionEntityType = 'b2c_order' | 'b2b_order' | 'b2b_invoice'
type DataQualityStatus = 'verified' | 'partial' | 'missing'

interface ListResponse<T> {
  items: T[]
  total: number
}

interface LegalEntity {
  id: string
  code: string
  name: string
  legal_name: string
  country: string
  functional_currency: string
  status: string
}

interface Brand {
  id: string
  code: string
  name: string
  status: string
  default_legal_entity_id: string | null
  default_legal_entity_name: string | null
}

interface Attribution {
  id: string
  entity_type: AttributionEntityType
  entity_id: string
  brand_id: string | null
  brand_name: string | null
  legal_entity_id: string | null
  legal_entity_name: string | null
  assignment_source: string
  is_intercompany: boolean
  counterparty_legal_entity_id: string | null
  counterparty_legal_entity_name: string | null
  elimination_status: string
  elimination_amount: string
  assigned_by: string
  approved_by: string | null
  approved_at: string | null
}

interface ProductBrandGap {
  product_id: string
  sku: string
  name: string
  status: string
  category: string | null
  legacy_brand: string | null
  created_at: string
}

interface ProductBrandBulkResult {
  requested: number
  assigned: number
  skipped: number
  failed: number
  items: Array<{
    product_id: string
    sku: string | null
    status: string
    error: string | null
  }>
}

interface AttributionGap {
  entity_type: AttributionEntityType
  entity_id: string
  reference: string
  occurred_at: string
  business_model: BusinessModel
  amount: string
  currency: string
  reason: string
  product_count: number
  sample_skus: string[]
  suggested_brand_id: string | null
  suggested_brand_name: string | null
  suggested_legal_entity_id: string | null
  suggested_legal_entity_name: string | null
}

interface AttributionReconcileResult {
  attempted: number
  created: number
  skipped: number
  items: Array<{
    entity_type: AttributionEntityType
    entity_id: string
    reference: string
    status: string
    reason: string
  }>
}

interface ConsolidationRow {
  brand_id: string | null
  brand_name: string
  legal_entity_id: string | null
  legal_entity_name: string
  business_model: BusinessModel
  currency: string
  gross_revenue: string
  intercompany_revenue: string
  external_revenue: string
  orders: number
  open_receivables: string
  profit_revenue: string
  gross_profit: string | null
  gross_margin_percent: string | null
  cost_coverage_percent: string
  attribution_status: 'complete' | 'partial' | 'missing'
}

interface ConsolidationReport {
  period: { start_date: string; end_date: string }
  reporting_currency: string | null
  totals: {
    currency: string | null
    gross_revenue: string | null
    intercompany_revenue: string | null
    external_revenue: string | null
    gross_profit: string | null
    orders: number
  }
  rows: ConsolidationRow[]
  data_quality: {
    status: DataQualityStatus
    attributed_order_percent: string | null
    cost_coverage_percent: string | null
    notes: string[]
  }
  notes: string[]
}

interface BrandForm {
  code: string
  name: string
  default_legal_entity_id?: string
  notes?: string
}

interface LegalEntityForm {
  code: string
  name: string
  legal_name: string
  country: string
  functional_currency: string
  notes?: string
}

interface AttributionForm {
  entity_type: AttributionEntityType
  entity_id: string
  brand_id: string
  legal_entity_id: string
  is_intercompany: boolean
  counterparty_legal_entity_id?: string
  evidence_note?: string
}

const qualityMeta: Record<DataQualityStatus, { color: string; label: string }> = {
  verified: { color: 'green', label: '归因完整' },
  partial: { color: 'orange', label: '存在缺口' },
  missing: { color: 'default', label: '未归因' },
}

const entityLabel: Record<AttributionEntityType, string> = {
  b2c_order: 'B2C 订单',
  b2b_order: 'B2B 订单',
  b2b_invoice: 'B2B 发票',
}

const gapReasonMeta: Record<string, { color: string; label: string }> = {
  ready: { color: 'green', label: '可自动补全' },
  ready_from_order: { color: 'green', label: '可继承订单归因' },
  missing_product_reference: {
    color: 'default',
    label: '缺少商品关联',
  },
  product_not_found: { color: 'red', label: '商品不存在' },
  missing_product_brand: { color: 'orange', label: '商品未绑定品牌' },
  product_brand_not_found: { color: 'red', label: '商品品牌不存在' },
  mixed_brand: { color: 'orange', label: '订单包含多个品牌' },
  missing_default_legal_entity: {
    color: 'orange',
    label: '品牌未配置默认法人',
  },
}

const eliminationMeta: Record<string, { color: string; label: string }> = {
  not_applicable: { color: 'default', label: '外部交易' },
  pending: { color: 'orange', label: '待审批' },
  approved: { color: 'green', label: '已批准消除' },
  rejected: { color: 'red', label: '已拒绝' },
}

function money(
  value: string | number | null | undefined,
  currency = 'USD',
): string {
  if (value === null || value === undefined || value === '') return '--'
  const amount = Number(value)
  if (Number.isNaN(amount)) return '--'
  try {
    return new Intl.NumberFormat('zh-CN', {
      style: 'currency',
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount)
  } catch {
    return `${currency} ${amount.toFixed(2)}`
  }
}

function percent(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '--'
  const amount = Number(value)
  return Number.isNaN(amount) ? '--' : `${amount.toFixed(1)}%`
}

function dateTime(value: string): string {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString('zh-CN', { hour12: false })
}

const attributionStatusMeta = {
  complete: { color: 'green', label: '完整' },
  partial: { color: 'orange', label: '部分' },
  missing: { color: 'default', label: '未归因' },
}

export default function ConsolidationPage() {
  const { message } = AntApp.useApp()
  const [range, setRange] = useState<[Dayjs, Dayjs]>([
    dayjs().subtract(29, 'day'),
    dayjs(),
  ])
  const [reportingCurrency, setReportingCurrency] = useState('')
  const [brandFilter, setBrandFilter] = useState<string>()
  const [legalEntityFilter, setLegalEntityFilter] = useState<string>()
  const [report, setReport] = useState<ConsolidationReport | null>(null)
  const [brands, setBrands] = useState<Brand[]>([])
  const [legalEntities, setLegalEntities] = useState<LegalEntity[]>([])
  const [attributions, setAttributions] = useState<Attribution[]>([])
  const [productBrandGaps, setProductBrandGaps] = useState<ProductBrandGap[]>([])
  const [attributionGaps, setAttributionGaps] = useState<AttributionGap[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [dimensionModal, setDimensionModal] = useState<'brand' | 'legal' | null>(
    null,
  )
  const [editingBrand, setEditingBrand] = useState<Brand | null>(null)
  const [brandDefaults, setBrandDefaults] = useState<Partial<BrandForm>>({})
  const [brandFormKey, setBrandFormKey] = useState(0)
  const [activeTab, setActiveTab] = useState('legal-entities')
  const [attributionModalOpen, setAttributionModalOpen] = useState(false)
  const [attributionDefaults, setAttributionDefaults] = useState<
    Partial<AttributionForm>
  >({ entity_type: 'b2b_order', is_intercompany: false })
  const [attributionFormKey, setAttributionFormKey] = useState(0)
  const [selectedProductIds, setSelectedProductIds] = useState<Key[]>([])
  const [bulkBrandId, setBulkBrandId] = useState<string>()
  const [bulkAssigning, setBulkAssigning] = useState(false)
  const [bulkAssignResult, setBulkAssignResult] =
    useState<ProductBrandBulkResult | null>(null)
  const [reconciling, setReconciling] = useState(false)
  const [reconcileResult, setReconcileResult] =
    useState<AttributionReconcileResult | null>(null)
  const [productSearch, setProductSearch] = useState('')
  const [decision, setDecision] = useState<{
    attribution: Attribution
    mode: 'approve' | 'reject'
  } | null>(null)
  const [decisionSubmitting, setDecisionSubmitting] = useState(false)
  const [brandForm] = Form.useForm<BrandForm>()
  const [legalForm] = Form.useForm<LegalEntityForm>()
  const [attributionForm] = Form.useForm<AttributionForm>()
  const [decisionForm] = Form.useForm<{ elimination_amount: number; note?: string }>()

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [
        reportPayload,
        brandPayload,
        legalPayload,
        attributionPayload,
        productGapPayload,
        attributionGapPayload,
      ] = await Promise.all([
        api.getConsolidationReport({
          startDate: range[0].format('YYYY-MM-DD'),
          endDate: range[1].format('YYYY-MM-DD'),
          reportingCurrency: reportingCurrency || undefined,
          brandId: brandFilter,
          legalEntityId: legalEntityFilter,
        }),
        api.getBrands(),
        api.getLegalEntities(),
        api.getCommerceAttributions(),
        api.getProductBrandGaps(),
        api.getAttributionGaps(),
      ])
      setReport(reportPayload as ConsolidationReport)
      setBrands((brandPayload as ListResponse<Brand>).items)
      setLegalEntities((legalPayload as ListResponse<LegalEntity>).items)
      setAttributions(
        (attributionPayload as ListResponse<Attribution>).items,
      )
      setProductBrandGaps(
        (productGapPayload as ListResponse<ProductBrandGap>).items,
      )
      setAttributionGaps(
        (attributionGapPayload as ListResponse<AttributionGap>).items,
      )
    } catch (requestError) {
      setReport(null)
      setError(
        requestError instanceof ApiError && requestError.status === 401
          ? '登录状态已失效，请重新登录后查看合并报表。'
          : requestError instanceof Error
            ? requestError.message
            : '合并经营报表加载失败',
      )
    } finally {
      setLoading(false)
    }
  }, [
    brandFilter,
    legalEntityFilter,
    range,
    reportingCurrency,
  ])

  useEffect(() => {
    void load()
  }, [load])

  const intercompanyRows = useMemo(
    () => attributions.filter((row) => row.is_intercompany),
    [attributions],
  )
  const pendingCount = intercompanyRows.filter(
    (row) => row.elimination_status === 'pending',
  ).length
  const filteredProductBrandGaps = useMemo(() => {
    const keyword = productSearch.trim().toLowerCase()
    if (!keyword) return productBrandGaps
    return productBrandGaps.filter(
      (row) =>
        row.sku.toLowerCase().includes(keyword) ||
        row.name.toLowerCase().includes(keyword),
    )
  }, [productBrandGaps, productSearch])
  const autoReadyCount = attributionGaps.filter((row) =>
    ['ready', 'ready_from_order'].includes(row.reason),
  ).length
  const quality = report?.data_quality
  const totalCurrency = report?.totals.currency || reportingCurrency || 'USD'

  const openAttribution = (gap?: AttributionGap) => {
    setAttributionDefaults(
      gap
        ? {
            entity_type: gap.entity_type,
            entity_id: gap.entity_id,
            brand_id: gap.suggested_brand_id || undefined,
            legal_entity_id: gap.suggested_legal_entity_id || undefined,
            is_intercompany: false,
          }
        : {
            entity_type: 'b2b_order',
            entity_id: undefined,
            brand_id: undefined,
            legal_entity_id: undefined,
            is_intercompany: false,
          },
    )
    setAttributionFormKey((current) => current + 1)
    setAttributionModalOpen(true)
  }

  const openBrand = (brand?: Brand) => {
    setEditingBrand(brand || null)
    setBrandDefaults(
      brand
        ? {
            code: brand.code,
            name: brand.name,
            default_legal_entity_id:
              brand.default_legal_entity_id || undefined,
          }
        : {},
    )
    setBrandFormKey((current) => current + 1)
    setDimensionModal('brand')
  }

  const submitDimension = async () => {
    try {
      if (dimensionModal === 'brand') {
        const values = await brandForm.validateFields()
        if (editingBrand) {
          const { code: _code, ...changes } = values
          await api.updateBrand(editingBrand.id, {
            ...changes,
            default_legal_entity_id:
              changes.default_legal_entity_id || undefined,
          })
        } else {
          await api.createBrand(values)
        }
        brandForm.resetFields()
        message.success(editingBrand ? '品牌已更新' : '品牌已创建')
      } else if (dimensionModal === 'legal') {
        const values = await legalForm.validateFields()
        await api.createLegalEntity(values)
        legalForm.resetFields()
        message.success('法人主体已创建')
      }
      setEditingBrand(null)
      setDimensionModal(null)
      await load()
    } catch (requestError) {
      if (requestError instanceof ApiError) {
        message.error(requestError.message)
      }
    }
  }

  const submitAttribution = async () => {
    try {
      const values = await attributionForm.validateFields()
      const { entity_type, entity_id, ...payload } = values
      await api.upsertCommerceAttribution(entity_type, entity_id, {
        brand_id: payload.brand_id,
        legal_entity_id: payload.legal_entity_id,
        is_intercompany: payload.is_intercompany,
        counterparty_legal_entity_id: payload.is_intercompany
          ? payload.counterparty_legal_entity_id
          : undefined,
        evidence: payload.evidence_note
          ? { note: payload.evidence_note }
          : {},
      })
      message.success('交易归因已保存')
      setAttributionModalOpen(false)
      attributionForm.resetFields()
      await load()
    } catch (requestError) {
      if (requestError instanceof ApiError) {
        message.error(requestError.message)
      }
    }
  }

  const submitBulkAssignment = async () => {
    if (!selectedProductIds.length || !bulkBrandId) {
      message.warning('请选择商品和目标品牌')
      return
    }
    setBulkAssigning(true)
    try {
      const result = (await api.bulkAssignProductBrands(
        selectedProductIds.map(String),
        bulkBrandId,
      )) as ProductBrandBulkResult
      setBulkAssignResult(result)
      setSelectedProductIds([])
      setBulkBrandId(undefined)
      if (result.failed || result.skipped) {
        message.warning(
          `已绑定 ${result.assigned} 个，跳过 ${result.skipped} 个，失败 ${result.failed} 个`,
        )
      } else {
        message.success(`已绑定 ${result.assigned} 个商品`)
      }
      await load()
    } catch (requestError) {
      if (requestError instanceof ApiError) {
        message.error(requestError.message)
      }
    } finally {
      setBulkAssigning(false)
    }
  }

  const submitReconcile = async () => {
    setReconciling(true)
    try {
      const result = (await api.reconcileAttributionGaps()) as
        AttributionReconcileResult
      setReconcileResult(result)
      if (result.created) {
        message.success(`已自动补全 ${result.created} 条交易归因`)
      } else {
        message.info('当前没有可自动补全的归因缺口')
      }
      await load()
    } catch (requestError) {
      if (requestError instanceof ApiError) {
        message.error(requestError.message)
      }
    } finally {
      setReconciling(false)
    }
  }

  const submitDecision = async () => {
    if (!decision || decisionSubmitting) return
    setDecisionSubmitting(true)
    try {
      if (decision.mode === 'approve') {
        const values = await decisionForm.validateFields()
        await api.approveElimination(
          decision.attribution.id,
          String(values.elimination_amount),
          values.note ? { note: values.note } : {},
        )
      } else {
        await api.rejectElimination(
          decision.attribution.id,
          { note: '管理员拒绝内部交易消除' },
        )
      }
      if (decision.mode === 'approve') {
        decisionForm.resetFields()
      }
      setDecision(null)
      message.success(
        decision.mode === 'approve'
          ? '内部交易消除已批准'
          : '内部交易消除已拒绝',
      )
      await load()
    } catch (requestError) {
      if (requestError instanceof ApiError) {
        message.error(requestError.message)
      }
    } finally {
      setDecisionSubmitting(false)
    }
  }

  const reportColumns: ColumnsType<ConsolidationRow> = [
    {
      title: '品牌',
      dataIndex: 'brand_name',
      width: 150,
      render: (value: string, row) => (
        <div className="primary-cell">
          <strong>{value}</strong>
          <span>{row.brand_id || '待归因'}</span>
        </div>
      ),
    },
    {
      title: '法人主体',
      dataIndex: 'legal_entity_name',
      width: 170,
      render: (value: string, row) => (
        <div className="primary-cell">
          <strong>{value}</strong>
          <span>{row.legal_entity_id || '待归因'}</span>
        </div>
      ),
    },
    {
      title: '模式',
      dataIndex: 'business_model',
      width: 80,
      render: (value: BusinessModel) => (
        <Tag color={value === 'B2B' ? 'orange' : 'green'}>{value}</Tag>
      ),
    },
    { title: '币种', dataIndex: 'currency', width: 76 },
    {
      title: '账面收入',
      dataIndex: 'gross_revenue',
      align: 'right',
      render: (value: string, row) => money(value, row.currency),
    },
    {
      title: '内部交易',
      dataIndex: 'intercompany_revenue',
      align: 'right',
      render: (value: string, row) => (
        <Text type={Number(value) > 0 ? 'warning' : undefined}>
          {money(value, row.currency)}
        </Text>
      ),
    },
    {
      title: '外部收入',
      dataIndex: 'external_revenue',
      align: 'right',
      render: (value: string, row) => money(value, row.currency),
    },
    { title: '订单', dataIndex: 'orders', align: 'right', width: 74 },
    {
      title: '未结应收',
      dataIndex: 'open_receivables',
      align: 'right',
      render: (value: string, row) => money(value, row.currency),
    },
    {
      title: '毛利',
      dataIndex: 'gross_profit',
      align: 'right',
      render: (value: string | null, row) =>
        value === null ? (
          <Text type="secondary">成本不足</Text>
        ) : (
          money(value, row.currency)
        ),
    },
    {
      title: '归因',
      dataIndex: 'attribution_status',
      width: 88,
      render: (value: keyof typeof attributionStatusMeta) => (
        <Tag color={attributionStatusMeta[value].color}>
          {attributionStatusMeta[value].label}
        </Tag>
      ),
    },
  ]

  const attributionColumns: ColumnsType<Attribution> = [
    {
      title: '业务事实',
      dataIndex: 'entity_type',
      width: 112,
      render: (value: AttributionEntityType, row) => (
        <div className="primary-cell">
          <strong>{entityLabel[value]}</strong>
          <span>{row.entity_id}</span>
        </div>
      ),
    },
    { title: '品牌', dataIndex: 'brand_name', render: (value) => value || '--' },
    {
      title: '销售法人',
      dataIndex: 'legal_entity_name',
      render: (value) => value || '--',
    },
    {
      title: '交易属性',
      dataIndex: 'elimination_status',
      width: 116,
      render: (value: string, row) =>
        row.is_intercompany ? (
          <Tag color={eliminationMeta[value]?.color}>
            {eliminationMeta[value]?.label || value}
          </Tag>
        ) : (
          <Tag>外部交易</Tag>
        ),
    },
    {
      title: '对手法人',
      dataIndex: 'counterparty_legal_entity_name',
      render: (value) => value || '--',
    },
    {
      title: '已批准消除',
      dataIndex: 'elimination_amount',
      align: 'right',
      render: (value: string) =>
        Number(value) > 0 ? value : <Text type="secondary">--</Text>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 170,
      render: (_, row) =>
        row.is_intercompany && row.elimination_status === 'pending' ? (
          <Space>
            <Button
              size="small"
              type="primary"
              icon={<CheckCircleOutlined />}
              onClick={() => setDecision({ attribution: row, mode: 'approve' })}
            >
              批准消除
            </Button>
            <Button
              size="small"
              danger
              icon={<CloseCircleOutlined />}
              onClick={() => setDecision({ attribution: row, mode: 'reject' })}
            >
              拒绝
            </Button>
          </Space>
        ) : (
          <Text type="secondary">已处理</Text>
        ),
    },
  ]

  const productBrandGapColumns: ColumnsType<ProductBrandGap> = [
    {
      title: '商品',
      dataIndex: 'name',
      render: (value: string, row) => (
        <div className="primary-cell">
          <strong>{value}</strong>
          <span>{row.sku}</span>
        </div>
      ),
    },
    {
      title: '分类',
      dataIndex: 'category',
      width: 140,
      render: (value: string | null) => value || '--',
    },
    {
      title: '旧品牌文本',
      dataIndex: 'legacy_brand',
      width: 150,
      render: (value: string | null) =>
        value ? <Tag>{value}</Tag> : <Text type="secondary">--</Text>,
    },
    {
      title: '商品状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string) => <Tag>{value}</Tag>,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 170,
      render: (value: string) => dateTime(value),
    },
  ]

  const attributionGapColumns: ColumnsType<AttributionGap> = [
    {
      title: '业务事实',
      dataIndex: 'reference',
      width: 210,
      render: (value: string, row) => (
        <div className="primary-cell">
          <strong>{entityLabel[row.entity_type]}</strong>
          <span>{value}</span>
        </div>
      ),
    },
    {
      title: '发生时间',
      dataIndex: 'occurred_at',
      width: 170,
      render: (value: string) => dateTime(value),
    },
    {
      title: '金额',
      dataIndex: 'amount',
      align: 'right',
      render: (value: string, row) => money(value, row.currency),
    },
    {
      title: '缺口原因',
      dataIndex: 'reason',
      width: 160,
      render: (value: string) => (
        <Tag color={gapReasonMeta[value]?.color}>
          {gapReasonMeta[value]?.label || value}
        </Tag>
      ),
    },
    {
      title: '商品',
      key: 'products',
      width: 180,
      render: (_, row) => (
        <div className="primary-cell">
          <strong>{row.product_count} 个商品</strong>
          <span>{row.sample_skus.join(', ') || '无 SKU 证据'}</span>
        </div>
      ),
    },
    {
      title: '建议归因',
      key: 'suggestion',
      width: 180,
      render: (_, row) => (
        <div className="primary-cell">
          <strong>{row.suggested_brand_name || '待选择品牌'}</strong>
          <span>{row.suggested_legal_entity_name || '待选择法人'}</span>
        </div>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 110,
      render: (_, row) => (
        <Button size="small" onClick={() => openAttribution(row)}>
          登记归因
        </Button>
      ),
    },
  ]

  return (
    <div className="resource-page">
      <div className="page-heading">
        <div>
          <div className="page-kicker">MULTI-BRAND & MULTI-ENTITY CONSOLIDATION</div>
          <Title level={2}>合并经营报表</Title>
          <Paragraph>
            按品牌、法人、业务模式和币种归因；内部交易只有管理员批准后才从外部收入中消除。
          </Paragraph>
        </div>
        <Space wrap>
          <RangePicker
            allowClear={false}
            value={range}
            onChange={(value) => {
              if (value?.[0] && value[1]) setRange([value[0], value[1]])
            }}
          />
          <Select
            aria-label="合并币种"
            value={reportingCurrency}
            style={{ width: 132 }}
            onChange={setReportingCurrency}
            options={[
              { value: '', label: '原始币种' },
              { value: 'USD', label: '合并为 USD' },
              { value: 'EUR', label: '合并为 EUR' },
              { value: 'CNY', label: '合并为 CNY' },
              { value: 'GBP', label: '合并为 GBP' },
            ]}
          />
          <Select
            aria-label="品牌筛选"
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="全部品牌"
            value={brandFilter}
            style={{ width: 150 }}
            onChange={setBrandFilter}
            options={brands.map((row) => ({ value: row.id, label: row.name }))}
          />
          <Select
            aria-label="法人筛选"
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="全部法人"
            value={legalEntityFilter}
            style={{ width: 160 }}
            onChange={setLegalEntityFilter}
            options={legalEntities.map((row) => ({
              value: row.id,
              label: row.name,
            }))}
          />
          <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>
            刷新
          </Button>
        </Space>
      </div>

      {error && (
        <Alert
          className="page-alert"
          type={error.includes('登录') ? 'warning' : 'error'}
          showIcon
          title="合并报表当前不可用"
          description={error}
        />
      )}
      {quality && (
        <Alert
          className="page-alert"
          type={
            quality.status === 'verified'
              ? 'success'
              : quality.status === 'partial'
                ? 'warning'
                : 'info'
          }
          showIcon
          title={`归因质量：${qualityMeta[quality.status].label}`}
          description={`完整归因 ${percent(
            quality.attributed_order_percent,
          )}，成本覆盖 ${percent(quality.cost_coverage_percent)}。${quality.notes.join(
            ' ',
          )}`}
        />
      )}

      <Skeleton active loading={loading}>
        <Row gutter={[14, 14]} className="resource-metrics">
          <Col xs={24} sm={12} xl={6}>
            <Card variant="borderless">
              <Statistic
                title="账面收入"
                value={money(report?.totals.gross_revenue, totalCurrency)}
                prefix={<GlobalOutlined />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} xl={6}>
            <Card variant="borderless">
              <Statistic
                title="内部交易"
                value={money(report?.totals.intercompany_revenue, totalCurrency)}
                prefix={<ApartmentOutlined />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} xl={6}>
            <Card variant="borderless">
              <Statistic
                title="外部收入"
                value={money(report?.totals.external_revenue, totalCurrency)}
                prefix={<BankOutlined />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} xl={6}>
            <Card variant="borderless">
              <Statistic
                title="待审批内部交易"
                value={pendingCount}
                prefix={<CheckCircleOutlined />}
              />
            </Card>
          </Col>
        </Row>

        <Card variant="borderless" className="resource-panel" title="品牌与法人合并视图">
          <Table
            rowKey={(row) =>
              `${row.brand_id || 'none'}-${row.legal_entity_id || 'none'}-${row.business_model}-${row.currency}`
            }
            pagination={false}
            dataSource={report?.rows || []}
            scroll={{ x: 1250 }}
            locale={{ emptyText: '选定期间没有经营数据' }}
            columns={reportColumns}
          />
        </Card>

        <Card variant="borderless" className="resource-panel">
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            items={[
              {
                key: 'legal-entities',
                label: '法人主体',
                children: (
                  <>
                    <Space style={{ marginBottom: 12 }}>
                      <Button
                        type="primary"
                        icon={<PlusOutlined />}
                        onClick={() => setDimensionModal('legal')}
                      >
                        新建法人
                      </Button>
                    </Space>
                    <Table
                      rowKey="id"
                      pagination={false}
                      dataSource={legalEntities}
                      scroll={{ x: 800 }}
                      columns={[
                        { title: '编码', dataIndex: 'code', width: 110 },
                        { title: '名称', dataIndex: 'name' },
                        { title: '法定名称', dataIndex: 'legal_name' },
                        { title: '国家', dataIndex: 'country', width: 80 },
                        {
                          title: '本位币',
                          dataIndex: 'functional_currency',
                          width: 90,
                        },
                        {
                          title: '状态',
                          dataIndex: 'status',
                          width: 86,
                          render: (value: string) => (
                            <Tag color={value === 'active' ? 'green' : 'default'}>
                              {value === 'active' ? '启用' : '停用'}
                            </Tag>
                          ),
                        },
                      ]}
                    />
                  </>
                ),
              },
              {
                key: 'brands',
                label: '品牌',
                children: (
                  <>
                    <Space style={{ marginBottom: 12 }}>
                      <Button
                        type="primary"
                        icon={<PlusOutlined />}
                        onClick={() => openBrand()}
                      >
                        新建品牌
                      </Button>
                    </Space>
                    <Table
                      rowKey="id"
                      pagination={false}
                      dataSource={brands}
                      scroll={{ x: 800 }}
                      columns={[
                        { title: '编码', dataIndex: 'code', width: 110 },
                        { title: '品牌', dataIndex: 'name' },
                        {
                          title: '默认销售法人',
                          dataIndex: 'default_legal_entity_name',
                          render: (value) => value || '未配置',
                        },
                        {
                          title: '状态',
                          dataIndex: 'status',
                          width: 86,
                          render: (value: string) => (
                            <Tag color={value === 'active' ? 'green' : 'default'}>
                              {value === 'active' ? '启用' : '停用'}
                            </Tag>
                          ),
                        },
                        {
                          title: '操作',
                          key: 'actions',
                          width: 90,
                          render: (_, row) => (
                            <Button size="small" onClick={() => openBrand(row)}>
                              编辑
                            </Button>
                          ),
                        },
                      ]}
                    />
                  </>
                ),
              },
              {
                key: 'product-brands',
                label: `商品品牌${productBrandGaps.length ? ` (${productBrandGaps.length})` : ''}`,
                children: (
                  <>
                    <Space wrap style={{ marginBottom: 12 }}>
                      <Input.Search
                        allowClear
                        value={productSearch}
                        onChange={(event) => setProductSearch(event.target.value)}
                        placeholder="搜索 SKU 或商品名称"
                        style={{ width: 240 }}
                      />
                      <Select
                        id="bulk_brand_id"
                        showSearch
                        optionFilterProp="label"
                        value={bulkBrandId}
                        onChange={setBulkBrandId}
                        placeholder="选择目标品牌"
                        style={{ width: 220 }}
                        options={brands
                          .filter((row) => row.status === 'active')
                          .map((row) => ({
                            value: row.id,
                            label: row.default_legal_entity_name
                              ? `${row.name} · ${row.default_legal_entity_name}`
                              : `${row.name} · 未配置法人`,
                          }))}
                      />
                      <Button
                        type="primary"
                        loading={bulkAssigning}
                        disabled={!selectedProductIds.length || !bulkBrandId}
                        onClick={() => void submitBulkAssignment()}
                      >
                        批量绑定
                      </Button>
                      <Text type="secondary">
                        已选 {selectedProductIds.length} 个商品
                      </Text>
                    </Space>
                    {bulkAssignResult ? (
                      <Alert
                        showIcon
                        className="page-alert"
                        type={
                          bulkAssignResult.failed
                            ? 'error'
                            : bulkAssignResult.skipped
                              ? 'warning'
                              : 'success'
                        }
                        title={`已绑定 ${bulkAssignResult.assigned} 个，跳过 ${bulkAssignResult.skipped} 个，失败 ${bulkAssignResult.failed} 个`}
                        description={
                          bulkAssignResult.items
                            .filter((item) => item.status !== 'assigned')
                            .slice(0, 5)
                            .map(
                              (item) =>
                                `${item.sku || item.product_id}: ${
                                  item.error || item.status
                                }`,
                            )
                            .join('；') || undefined
                        }
                      />
                    ) : null}
                    <Table
                      rowKey="product_id"
                      pagination={{ pageSize: 10 }}
                      dataSource={filteredProductBrandGaps}
                      rowSelection={{
                        selectedRowKeys: selectedProductIds,
                        onChange: setSelectedProductIds,
                        preserveSelectedRowKeys: true,
                      }}
                      scroll={{ x: 900 }}
                      locale={{ emptyText: '当前没有未绑定品牌的商品' }}
                      columns={productBrandGapColumns}
                    />
                  </>
                ),
              },
              {
                key: 'attribution-gaps',
                label: `归因缺口${attributionGaps.length ? ` (${attributionGaps.length})` : ''}`,
                children: (
                  <>
                    <Space wrap style={{ marginBottom: 12 }}>
                      <Button
                        type="primary"
                        loading={reconciling}
                        disabled={!autoReadyCount}
                        onClick={() => void submitReconcile()}
                      >
                        补全可自动归因 ({autoReadyCount})
                      </Button>
                      <Text type="secondary">
                        只处理商品品牌唯一且默认法人完整的交易
                      </Text>
                    </Space>
                    {reconcileResult ? (
                      <Alert
                        showIcon
                        className="page-alert"
                        type={reconcileResult.created ? 'success' : 'info'}
                        title={`检查 ${reconcileResult.attempted} 条，自动补全 ${reconcileResult.created} 条，跳过 ${reconcileResult.skipped} 条`}
                        description={
                          reconcileResult.items
                            .filter((item) => item.status === 'skipped')
                            .slice(0, 5)
                            .map(
                              (item) =>
                                `${entityLabel[item.entity_type]} ${item.reference}: ${
                                  gapReasonMeta[item.reason]?.label || item.reason
                                }`,
                            )
                            .join('；') || undefined
                        }
                      />
                    ) : null}
                    <Table
                      rowKey={(row) => `${row.entity_type}-${row.entity_id}`}
                      pagination={{ pageSize: 10 }}
                      dataSource={attributionGaps}
                      scroll={{ x: 1250 }}
                      locale={{ emptyText: '当前没有交易归因缺口' }}
                      columns={attributionGapColumns}
                    />
                  </>
                ),
              },
              {
                key: 'attributions',
                label: `交易归因${pendingCount ? ` (${pendingCount})` : ''}`,
                children: (
                  <>
                    <Space style={{ marginBottom: 12 }}>
                      <Button
                        type="primary"
                        icon={<PlusOutlined />}
                        onClick={() => openAttribution()}
                        disabled={!brands.length || !legalEntities.length}
                      >
                        登记归因
                      </Button>
                    </Space>
                    <Table
                      rowKey="id"
                      pagination={{ pageSize: 10 }}
                      dataSource={intercompanyRows}
                      scroll={{ x: 1100 }}
                      locale={{ emptyText: '当前没有内部交易归因' }}
                      columns={attributionColumns}
                    />
                  </>
                ),
              },
            ]}
          />
        </Card>
      </Skeleton>

      <Modal
        open={dimensionModal === 'legal'}
        title="新建法人主体"
        okText="创建"
        onOk={() => void submitDimension()}
        onCancel={() => {
          setDimensionModal(null)
          legalForm.resetFields()
        }}
      >
        <Form form={legalForm} layout="vertical">
          <Form.Item name="code" label="编码" rules={[{ required: true }]}>
            <Input placeholder="nuotao-us" />
          </Form.Item>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input placeholder="Nuotao US" />
          </Form.Item>
          <Form.Item name="legal_name" label="法定名称" rules={[{ required: true }]}>
            <Input placeholder="Nuotao US LLC" />
          </Form.Item>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="country" label="国家" rules={[{ required: true }]}>
                <Input placeholder="US" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="functional_currency"
                label="本位币"
                rules={[{ required: true }]}
              >
                <Input placeholder="USD" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="notes" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={dimensionModal === 'brand'}
        title={editingBrand ? '编辑品牌' : '新建品牌'}
        okText={editingBrand ? '保存' : '创建'}
        onOk={() => void submitDimension()}
        onCancel={() => {
          setDimensionModal(null)
          setEditingBrand(null)
          brandForm.resetFields()
        }}
      >
        <Form
          key={brandFormKey}
          form={brandForm}
          layout="vertical"
          initialValues={brandDefaults}
        >
          <Form.Item name="code" label="编码" rules={[{ required: true }]}>
            <Input placeholder="nuotao" disabled={Boolean(editingBrand)} />
          </Form.Item>
          <Form.Item name="name" label="品牌名称" rules={[{ required: true }]}>
            <Input placeholder="Nuotao Outdoor" />
          </Form.Item>
          <Form.Item name="default_legal_entity_id" label="默认销售法人">
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              options={legalEntities.map((row) => ({
                value: row.id,
                label: row.name,
              }))}
            />
          </Form.Item>
          <Form.Item name="notes" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={attributionModalOpen}
        title="登记交易归因"
        okText="保存"
        onOk={() => void submitAttribution()}
        onCancel={() => {
          setAttributionModalOpen(false)
          attributionForm.resetFields()
        }}
      >
        <Form
          key={attributionFormKey}
          form={attributionForm}
          layout="vertical"
          initialValues={attributionDefaults}
        >
          <Form.Item name="entity_type" label="业务事实" rules={[{ required: true }]}>
            <Select
              options={Object.entries(entityLabel).map(([value, label]) => ({
                value,
                label,
              }))}
            />
          </Form.Item>
          <Form.Item name="entity_id" label="业务事实 ID" rules={[{ required: true }]}>
            <Input placeholder="UUID" />
          </Form.Item>
          <Form.Item name="brand_id" label="品牌" rules={[{ required: true }]}>
            <Select
              showSearch
              optionFilterProp="label"
              options={brands.map((row) => ({ value: row.id, label: row.name }))}
            />
          </Form.Item>
          <Form.Item name="legal_entity_id" label="销售法人" rules={[{ required: true }]}>
            <Select
              showSearch
              optionFilterProp="label"
              options={legalEntities.map((row) => ({
                value: row.id,
                label: row.name,
              }))}
            />
          </Form.Item>
          <Form.Item name="is_intercompany" label="内部交易" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item
            noStyle
            shouldUpdate={(previous, current) =>
              previous.is_intercompany !== current.is_intercompany
            }
          >
            {({ getFieldValue }) =>
              getFieldValue('is_intercompany') ? (
                <Form.Item
                  name="counterparty_legal_entity_id"
                  label="对手法人"
                  rules={[{ required: true }]}
                >
                  <Select
                    showSearch
                    optionFilterProp="label"
                    options={legalEntities.map((row) => ({
                      value: row.id,
                      label: row.name,
                    }))}
                  />
                </Form.Item>
              ) : null
            }
          </Form.Item>
          <Form.Item name="evidence_note" label="依据说明">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={decision !== null}
        title={decision?.mode === 'approve' ? '批准内部交易消除' : '拒绝内部交易消除'}
        okText={decision?.mode === 'approve' ? '批准' : '拒绝'}
        confirmLoading={decisionSubmitting}
        okButtonProps={{ danger: decision?.mode === 'reject' }}
        onOk={() => void submitDecision()}
        onCancel={() => {
          setDecision(null)
          decisionForm.resetFields()
        }}
      >
        {decision?.mode === 'approve' ? (
          <Form form={decisionForm} layout="vertical">
            <Form.Item
              name="elimination_amount"
              label="本次消除金额"
              rules={[{ required: true }]}
            >
              <InputNumber min={0.01} precision={2} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="note" label="审批依据">
              <Input.TextArea rows={3} />
            </Form.Item>
          </Form>
        ) : (
          <Text>确认拒绝该内部交易消除申请？该金额将继续计入外部收入。</Text>
        )}
      </Modal>
    </div>
  )
}
