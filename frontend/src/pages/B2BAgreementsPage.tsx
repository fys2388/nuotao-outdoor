import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Col,
  DatePicker,
  Descriptions,
  Divider,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Progress as AntProgress,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  DeleteOutlined,
  EditOutlined,
  FileDoneOutlined,
  PlusOutlined,
  ReloadOutlined,
  SendOutlined,
  StopOutlined,
  WalletOutlined,
} from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'
import { api, ApiError } from '../api/client'
import { useAuth } from '../auth/AuthProvider'

const { Title, Text } = Typography

type QualificationBasis = 'ordered' | 'invoiced' | 'paid'

interface AgentRecord {
  id: string
  agent_number: string
  company_name: string
  currency: string
}

interface RebateTier {
  id: string
  agreement_id: string
  min_sales_amount: number
  max_sales_amount: number | null
  rebate_percent: number
  created_at: string
  updated_at: string
}

interface Agreement {
  id: string
  agreement_number: string
  agent_id: string
  agent_company: string
  agent_number: string
  name: string
  status: string
  effective_status: string
  currency: string
  effective_from: string
  effective_to: string
  target_amount: number
  qualification_basis: QualificationBasis
  calculation_method: 'retroactive'
  notes: string | null
  created_by: string
  submitted_by: string | null
  submitted_at: string | null
  approved_by: string | null
  approved_at: string | null
  rejection_reason: string | null
  terminated_by: string | null
  terminated_at: string | null
  termination_reason: string | null
  tiers: RebateTier[]
  accrual_count: number
  created_at: string
  updated_at: string
}

interface AgreementProgress {
  agreement_id: string
  as_of: string
  period_start: string
  period_end: string
  currency: string
  qualification_basis: QualificationBasis
  target_amount: number
  qualifying_sales: number
  achievement_percent: number
  remaining_amount: number
  current_tier_id: string | null
  current_rebate_percent: number
  projected_rebate_amount: number
  next_tier_min_sales: number | null
  amount_to_next_tier: number | null
  days_remaining: number
  included_record_count: number
  excluded_record_count: number
  missing_rate_currencies: string[]
}

interface RebateAccrual {
  id: string
  accrual_number: string
  agreement_id: string
  agreement_number: string
  agent_id: string
  agent_company: string
  status: string
  period_start: string
  period_end: string
  qualification_basis: QualificationBasis
  calculation_method: 'retroactive'
  qualifying_sales: number
  rebate_percent: number
  rebate_amount: number
  currency: string
  evidence: Record<string, unknown>
  created_by: string
  submitted_by: string | null
  submitted_at: string | null
  approved_by: string | null
  approved_at: string | null
  rejected_by: string | null
  rejected_at: string | null
  rejection_reason: string | null
  settled_by: string | null
  settled_at: string | null
  settlement_reference: string | null
  created_at: string
  updated_at: string
}

interface ListResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

type DecisionMode =
  | 'agreement_reject'
  | 'agreement_terminate'
  | 'accrual_reject'

const agreementStatus: Record<string, { color: string; label: string }> = {
  draft: { color: 'default', label: '草稿' },
  pending_approval: { color: 'orange', label: '待审批' },
  active: { color: 'green', label: '生效' },
  rejected: { color: 'red', label: '已驳回' },
  expired: { color: 'default', label: '已过期' },
  terminated: { color: 'red', label: '已终止' },
}

const accrualStatus: Record<string, { color: string; label: string }> = {
  draft: { color: 'default', label: '待提交' },
  pending_approval: { color: 'orange', label: '待审批' },
  approved: { color: 'blue', label: '已批准' },
  rejected: { color: 'red', label: '已驳回' },
  settled: { color: 'green', label: '已结算' },
}

const basisOptions = [
  { value: 'invoiced', label: '已开票金额' },
  { value: 'ordered', label: '订单金额' },
  { value: 'paid', label: '已收款金额' },
] as const

const currencyOptions = ['USD', 'EUR', 'GBP', 'AUD', 'CAD', 'CNY'].map(
  (value) => ({ value, label: value }),
)

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  return error instanceof Error ? error.message : '操作失败'
}

function formatMoney(value: number, currency: string): string {
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: currency || 'USD',
    maximumFractionDigits: 2,
  }).format(value)
}

function currentStatus(row: Agreement): string {
  return row.effective_status || row.status
}

function StatusTag({
  value,
  labels,
}: {
  value: string
  labels: Record<string, { color: string; label: string }>
}) {
  const item = labels[value] || { color: 'default', label: value }
  return <Tag color={item.color}>{item.label}</Tag>
}

function emptyText(label: string) {
  return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={label} />
}

function tierRange(tier: Pick<RebateTier, 'min_sales_amount' | 'max_sales_amount'>): string {
  const minimum = Number(tier.min_sales_amount).toLocaleString('zh-CN')
  if (tier.max_sales_amount == null) return `${minimum}+`
  return `${minimum} - ${Number(tier.max_sales_amount).toLocaleString('zh-CN')}`
}

function assertContinuousTiers(
  tiers: Array<{
    min_sales_amount: number
    max_sales_amount: number | null
    rebate_percent: number
  }>,
) {
  if (!tiers.length) throw new Error('至少需要一档返利阶梯')
  const sorted = [...tiers].sort(
    (left, right) => Number(left.min_sales_amount) - Number(right.min_sales_amount),
  )
  if (Number(sorted[0].min_sales_amount) !== 0) {
    throw new Error('首档必须从 0 开始')
  }
  sorted.forEach((tier, index) => {
    if (
      tier.max_sales_amount != null &&
      Number(tier.max_sales_amount) <= Number(tier.min_sales_amount)
    ) {
      throw new Error(`第 ${index + 1} 档的上限必须大于下限`)
    }
    if (index < sorted.length - 1) {
      if (tier.max_sales_amount == null) {
        throw new Error('只有最后一档可以无上限')
      }
      if (Number(sorted[index + 1].min_sales_amount) !== Number(tier.max_sales_amount)) {
        throw new Error('返利阶梯必须连续衔接，不能有缺口或重叠')
      }
    }
  })
  if (sorted[sorted.length - 1].max_sales_amount != null) {
    throw new Error('最后一档必须无上限')
  }
}

export default function B2BAgreementsPage() {
  const { user } = useAuth()
  const { message } = AntApp.useApp()
  const [agents, setAgreementsAgents] = useState<AgentRecord[]>([])
  const [agreements, setAgreements] = useState<Agreement[]>([])
  const [accruals, setAccruals] = useState<RebateAccrual[]>([])
  const [selectedAgreement, setSelectedAgreement] = useState<Agreement | null>(null)
  const [selectedProgress, setSelectedProgress] = useState<AgreementProgress | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<string>()
  const [search, setSearch] = useState('')

  const [agreementModalOpen, setAgreementModalOpen] = useState(false)
  const [tierModalOpen, setTierModalOpen] = useState(false)
  const [accrualModalOpen, setAccrualModalOpen] = useState(false)
  const [decisionMode, setDecisionMode] = useState<DecisionMode | null>(null)
  const [decisionTarget, setDecisionTarget] = useState<Agreement | RebateAccrual | null>(null)
  const [settlementTarget, setSettlementTarget] = useState<RebateAccrual | null>(null)
  const [editingTier, setEditingTier] = useState<RebateTier | null>(null)

  const [agreementForm] = Form.useForm()
  const [tierForm] = Form.useForm()
  const [accrualForm] = Form.useForm()
  const [decisionForm] = Form.useForm()
  const [settlementForm] = Form.useForm()

  const canAdmin = user?.role === 'admin'
  const selectedAccruals = useMemo(
    () =>
      selectedAgreement
        ? accruals.filter((row) => row.agreement_id === selectedAgreement.id)
        : [],
    [accruals, selectedAgreement],
  )

  const activeAgreements = agreements.filter(
    (row) => currentStatus(row) === 'active',
  )
  const pendingAgreements = agreements.filter(
    (row) => row.status === 'pending_approval',
  )
  const pendingAccruals = accruals.filter(
    (row) => row.status === 'pending_approval',
  )
  const approvedAccruals = accruals.filter((row) => row.status === 'approved')
  const settledByCurrency = useMemo(() => {
    const totals = new Map<string, number>()
    accruals
      .filter((row) => row.status === 'settled')
      .forEach((row) => {
        totals.set(row.currency, (totals.get(row.currency) || 0) + Number(row.rebate_amount))
      })
    return [...totals.entries()]
  }, [accruals])

  const loadSelectedAgreement = useCallback(
    async (agreementId: string) => {
      const [agreement, progress] = await Promise.all([
        api.getB2BAgreement(agreementId) as Promise<Agreement>,
        api
          .getB2BAgreementProgress(agreementId)
          .catch(() => null) as Promise<AgreementProgress | null>,
      ])
      setSelectedAgreement(agreement)
      setSelectedProgress(progress)
    },
    [],
  )

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [agreementResponse, accrualResponse, agentResponse] = await Promise.all([
        api.getB2BAgreements(
          1,
          200,
          statusFilter,
          undefined,
          search.trim() || undefined,
        ) as Promise<ListResponse<Agreement>>,
        api.getB2BRebateAccruals(1, 200) as Promise<ListResponse<RebateAccrual>>,
        api.getB2BAgents() as Promise<ListResponse<AgentRecord>>,
      ])
      const nextAgreements = agreementResponse.items || []
      setAgreements(nextAgreements)
      setAccruals(accrualResponse.items || [])
      setAgreementsAgents(agentResponse.items || [])
      if (selectedAgreement) {
        const refreshed = nextAgreements.find((row) => row.id === selectedAgreement.id)
        if (refreshed) {
          setSelectedAgreement(refreshed)
          await loadSelectedAgreement(refreshed.id)
        }
      }
    } catch (loadError) {
      setError(errorMessage(loadError))
    } finally {
      setLoading(false)
    }
  }, [loadSelectedAgreement, search, selectedAgreement, statusFilter])

  useEffect(() => {
    void load()
  }, [statusFilter])

  const runAction = async (action: () => Promise<unknown>, success: string) => {
    setSaving(true)
    try {
      await action()
      message.success(success)
      await load()
      if (selectedAgreement) await loadSelectedAgreement(selectedAgreement.id)
    } catch (actionError) {
      message.error(errorMessage(actionError))
    } finally {
      setSaving(false)
    }
  }

  const openAgreement = async (agreement: Agreement) => {
    setDrawerOpen(true)
    setSelectedAgreement(agreement)
    setSelectedProgress(null)
    setLoading(true)
    try {
      await loadSelectedAgreement(agreement.id)
    } catch (loadError) {
      message.error(errorMessage(loadError))
    } finally {
      setLoading(false)
    }
  }

  const openCreateAgreement = () => {
    const start = dayjs().startOf('year')
    agreementForm.resetFields()
    agreementForm.setFieldsValue({
      currency: 'USD',
      effective_from: start,
      effective_to: start.endOf('year'),
      qualification_basis: 'invoiced',
      tiers: [
        {
          min_sales_amount: 0,
          max_sales_amount: null,
          rebate_percent: 0,
        },
      ],
    })
    setAgreementModalOpen(true)
  }

  const createAgreement = async () => {
    try {
      const values = await agreementForm.validateFields()
      const tiers = values.tiers as Array<{
        min_sales_amount: number
        max_sales_amount: number | null
        rebate_percent: number
      }>
      assertContinuousTiers(tiers)
      setSaving(true)
      const agreement = (await api.createB2BAgreement({
        agent_id: values.agent_id,
        name: values.name,
        currency: values.currency,
        effective_from: (values.effective_from as Dayjs).format('YYYY-MM-DD'),
        effective_to: (values.effective_to as Dayjs).format('YYYY-MM-DD'),
        target_amount: values.target_amount,
        qualification_basis: values.qualification_basis,
        calculation_method: 'retroactive',
        notes: values.notes || null,
      })) as Agreement
      for (const tier of tiers) {
        await api.createB2BAgreementTier(agreement.id, {
          min_sales_amount: tier.min_sales_amount,
          max_sales_amount: tier.max_sales_amount,
          rebate_percent: tier.rebate_percent,
        })
      }
      message.success(
        tiers.length
          ? '年度协议与返利阶梯已创建'
          : '年度协议草稿已创建，请补充返利阶梯',
      )
      setAgreementModalOpen(false)
      await load()
      await openAgreement(
        (await api.getB2BAgreement(agreement.id)) as Agreement,
      )
    } catch (saveError) {
      if (
        saveError instanceof Error &&
        'errorFields' in saveError
      ) {
        return
      }
      message.error(`创建失败：${errorMessage(saveError)}`)
    } finally {
      setSaving(false)
    }
  }

  const openTierModal = (tier?: RebateTier) => {
    setEditingTier(tier || null)
    tierForm.resetFields()
    if (tier) {
      tierForm.setFieldsValue({
        min_sales_amount: tier.min_sales_amount,
        max_sales_amount: tier.max_sales_amount,
        rebate_percent: tier.rebate_percent,
      })
    } else {
      const lastTier = selectedAgreement?.tiers[selectedAgreement.tiers.length - 1]
      tierForm.setFieldsValue({
        min_sales_amount: lastTier?.max_sales_amount ?? 0,
        max_sales_amount: null,
        rebate_percent: lastTier?.rebate_percent ?? 0,
      })
    }
    setTierModalOpen(true)
  }

  const saveTier = async () => {
    if (!selectedAgreement) return
    try {
      const values = await tierForm.validateFields()
      setSaving(true)
      const payload = {
        min_sales_amount: values.min_sales_amount,
        max_sales_amount: values.max_sales_amount ?? null,
        rebate_percent: values.rebate_percent,
      }
      if (editingTier) {
        await api.updateB2BAgreementTier(
          selectedAgreement.id,
          editingTier.id,
          payload,
        )
      } else {
        await api.createB2BAgreementTier(selectedAgreement.id, payload)
      }
      message.success(editingTier ? '返利阶梯已更新' : '返利阶梯已添加')
      setTierModalOpen(false)
      await load()
      await loadSelectedAgreement(selectedAgreement.id)
    } catch (saveError) {
      if (saveError instanceof Error && 'errorFields' in saveError) return
      message.error(`保存失败：${errorMessage(saveError)}`)
    } finally {
      setSaving(false)
    }
  }

  const openDecision = (
    mode: DecisionMode,
    target: Agreement | RebateAccrual,
  ) => {
    decisionForm.resetFields()
    setDecisionMode(mode)
    setDecisionTarget(target)
  }

  const submitDecision = async () => {
    if (!decisionTarget || !decisionMode) return
    try {
      const values = await decisionForm.validateFields()
      setSaving(true)
      if (decisionMode === 'agreement_reject') {
        await api.rejectB2BAgreement(
          (decisionTarget as Agreement).id,
          values.reason,
        )
      } else if (decisionMode === 'agreement_terminate') {
        await api.terminateB2BAgreement(
          (decisionTarget as Agreement).id,
          values.reason,
        )
      } else {
        await api.rejectB2BRebateAccrual(
          (decisionTarget as RebateAccrual).id,
          values.reason,
        )
      }
      message.success(
        decisionMode === 'agreement_terminate'
          ? '协议已终止'
          : '已驳回并保留审计原因',
      )
      setDecisionMode(null)
      setDecisionTarget(null)
      await load()
      if (selectedAgreement) await loadSelectedAgreement(selectedAgreement.id)
    } catch (saveError) {
      if (saveError instanceof Error && 'errorFields' in saveError) return
      message.error(errorMessage(saveError))
    } finally {
      setSaving(false)
    }
  }

  const openAccrualModal = () => {
    if (!selectedAgreement) return
    accrualForm.resetFields()
    accrualForm.setFieldsValue({
      period_start: dayjs(selectedAgreement.effective_from),
      period_end: dayjs(selectedAgreement.effective_to),
    })
    setAccrualModalOpen(true)
  }

  const calculateAccrual = async () => {
    if (!selectedAgreement) return
    try {
      const values = await accrualForm.validateFields()
      setSaving(true)
      await api.calculateB2BRebateAccrual(selectedAgreement.id, {
        period_start: (values.period_start as Dayjs).format('YYYY-MM-DD'),
        period_end: (values.period_end as Dayjs).format('YYYY-MM-DD'),
      })
      message.success('返利快照已计算，请核对后提交审批')
      setAccrualModalOpen(false)
      await load()
      await loadSelectedAgreement(selectedAgreement.id)
    } catch (saveError) {
      if (saveError instanceof Error && 'errorFields' in saveError) return
      message.error(`计算失败：${errorMessage(saveError)}`)
    } finally {
      setSaving(false)
    }
  }

  const settleAccrual = async () => {
    if (!settlementTarget) return
    try {
      const values = await settlementForm.validateFields()
      setSaving(true)
      await api.settleB2BRebateAccrual(
        settlementTarget.id,
        values.settlement_reference,
      )
      message.success('结算凭证已登记')
      setSettlementTarget(null)
      await load()
      if (selectedAgreement) await loadSelectedAgreement(selectedAgreement.id)
    } catch (saveError) {
      if (saveError instanceof Error && 'errorFields' in saveError) return
      message.error(errorMessage(saveError))
    } finally {
      setSaving(false)
    }
  }

  const agreementColumns: ColumnsType<Agreement> = [
    {
      title: '协议',
      fixed: 'left',
      width: 210,
      render: (_, row) => (
        <Space orientation="vertical" size={0}>
          <Text strong>{row.agreement_number}</Text>
          <Text type="secondary">{row.name}</Text>
        </Space>
      ),
    },
    {
      title: '客户',
      width: 200,
      render: (_, row) => (
        <Space orientation="vertical" size={0}>
          <Text>{row.agent_company || row.agent_id}</Text>
          <Text type="secondary">{row.agent_number}</Text>
        </Space>
      ),
    },
    {
      title: '状态',
      width: 100,
      render: (_, row) => (
        <StatusTag value={currentStatus(row)} labels={agreementStatus} />
      ),
    },
    {
      title: '周期',
      width: 190,
      render: (_, row) => `${row.effective_from} 至 ${row.effective_to}`,
    },
    {
      title: '目标口径',
      width: 130,
      render: (_, row) => (
        <Tag>{basisOptions.find((item) => item.value === row.qualification_basis)?.label}</Tag>
      ),
    },
    {
      title: '目标额',
      width: 150,
      align: 'right',
      render: (_, row) => (
        <Text strong>{formatMoney(row.target_amount, row.currency)}</Text>
      ),
    },
    {
      title: '阶梯',
      dataIndex: 'tiers',
      width: 80,
      align: 'center',
      render: (tiers: RebateTier[]) => tiers.length,
    },
    {
      title: '返利单',
      dataIndex: 'accrual_count',
      width: 80,
      align: 'center',
    },
    {
      title: '操作',
      fixed: 'right',
      width: 100,
      render: (_, row) => (
        <Button type="link" size="small" onClick={() => void openAgreement(row)}>
          查看
        </Button>
      ),
    },
  ]

  const tierColumns: ColumnsType<RebateTier> = [
    {
      title: '销售区间',
      render: (_, row) => tierRange(row),
    },
    {
      title: '返利比例',
      width: 120,
      align: 'right',
      render: (_, row) => `${Number(row.rebate_percent).toFixed(2)}%`,
    },
    {
      title: '操作',
      width: 150,
      render: (_, row) =>
        selectedAgreement && ['draft', 'rejected'].includes(selectedAgreement.status) ? (
          <Space size={4}>
            <Button
              type="link"
              size="small"
              icon={<EditOutlined />}
              onClick={() => openTierModal(row)}
            >
              编辑
            </Button>
            <Popconfirm
              title="删除该返利阶梯？"
              onConfirm={() =>
                void runAction(
                  () =>
                    api.deleteB2BAgreementTier(selectedAgreement.id, row.id),
                  '返利阶梯已删除',
                )
              }
            >
              <Button
                type="link"
                danger
                size="small"
                icon={<DeleteOutlined />}
              >
                删除
              </Button>
            </Popconfirm>
          </Space>
        ) : (
          <Text type="secondary">只读</Text>
        ),
    },
  ]

  const accrualColumns: ColumnsType<RebateAccrual> = [
    {
      title: '返利计算单',
      width: 190,
      render: (_, row) => (
        <Space orientation="vertical" size={0}>
          <Text strong>{row.accrual_number}</Text>
          <Text type="secondary">
            {row.period_start} 至 {row.period_end}
          </Text>
        </Space>
      ),
    },
    {
      title: '状态',
      width: 100,
      render: (_, row) => (
        <StatusTag value={row.status} labels={accrualStatus} />
      ),
    },
    {
      title: '销售额',
      width: 140,
      align: 'right',
      render: (_, row) => formatMoney(row.qualifying_sales, row.currency),
    },
    {
      title: '比例',
      dataIndex: 'rebate_percent',
      width: 90,
      align: 'right',
      render: (value: number) => `${Number(value).toFixed(2)}%`,
    },
    {
      title: '返利负债',
      width: 150,
      align: 'right',
      render: (_, row) => (
        <Text strong>{formatMoney(row.rebate_amount, row.currency)}</Text>
      ),
    },
    {
      title: '审计',
      width: 180,
      render: (_, row) => (
        <Space orientation="vertical" size={0}>
          <Text type="secondary">创建 {row.created_by}</Text>
          <Text type="secondary">
            {row.settlement_reference
              ? `结算 ${row.settlement_reference}`
              : `审批 ${row.approved_by || '-'}`}
          </Text>
        </Space>
      ),
    },
    {
      title: '操作',
      fixed: 'right',
      width: 230,
      render: (_, row) => (
        <Space wrap size={2}>
          {['draft', 'rejected'].includes(row.status) && (
            <Button
              type="link"
              size="small"
              icon={<SendOutlined />}
              onClick={() =>
                void runAction(
                  () => api.submitB2BRebateAccrual(row.id),
                  '返利计算单已提交审批',
                )
              }
            >
              提交
            </Button>
          )}
          {row.status === 'pending_approval' && canAdmin && (
            <>
              <Button
                type="link"
                size="small"
                icon={<CheckCircleOutlined />}
                onClick={() =>
                  void runAction(
                    () => api.approveB2BRebateAccrual(row.id),
                    '返利计算单已批准并形成负债',
                  )
                }
              >
                批准
              </Button>
              <Button
                type="link"
                danger
                size="small"
                onClick={() => openDecision('accrual_reject', row)}
              >
                驳回
              </Button>
            </>
          )}
          {row.status === 'approved' && canAdmin && (
            <Button
              type="link"
              size="small"
              icon={<WalletOutlined />}
              onClick={() => {
                settlementForm.resetFields()
                setSettlementTarget(row)
              }}
            >
              登记结算
            </Button>
          )}
          {row.status === 'settled' && (
            <Text type="secondary">{row.settlement_reference}</Text>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div className="dashboard-page">
      <div className="page-heading">
        <div>
          <div className="page-kicker page-kicker--b2b">B2B PERFORMANCE CONTROL</div>
          <Title level={2}>代理商年度协议与分级返利</Title>
          <p>
            目标进度读取真实订单、发票或收款事实；返利快照经过提交、审批和结算登记后形成可审计链路。
          </p>
        </div>
        <Space wrap>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreateAgreement}>
            新建年度协议
          </Button>
        </Space>
      </div>

      {error && (
        <Alert
          className="page-alert"
          type="error"
          showIcon
          title="协议数据加载失败"
          description={error}
        />
      )}

      <Row gutter={[14, 14]}>
        <Col xs={12} xl={6}>
          <Card variant="borderless">
            <Statistic title="生效协议" value={activeAgreements.length} />
          </Card>
        </Col>
        <Col xs={12} xl={6}>
          <Card variant="borderless">
            <Statistic title="待审批协议" value={pendingAgreements.length} />
          </Card>
        </Col>
        <Col xs={12} xl={6}>
          <Card variant="borderless">
            <Statistic title="待审批返利" value={pendingAccruals.length} />
          </Card>
        </Col>
        <Col xs={12} xl={6}>
          <Card variant="borderless">
            <Statistic title="已批准待结算" value={approvedAccruals.length} />
          </Card>
        </Col>
      </Row>

      <Card
        variant="borderless"
        style={{ marginTop: 16 }}
        title="年度协议台账"
        extra={
          settledByCurrency.length ? (
            <Text type="secondary">
              已结算：
              {settledByCurrency
                .map(([currency, amount]) => formatMoney(amount, currency))
                .join(' / ')}
            </Text>
          ) : null
        }
      >
        <div className="table-toolbar">
          <Space wrap>
            <Input.Search
              allowClear
              placeholder="搜索协议号或名称"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              onSearch={() => void load()}
              style={{ width: 260 }}
            />
            <Select
              allowClear
              placeholder="按状态筛选"
              value={statusFilter}
              onChange={setStatusFilter}
              options={Object.entries(agreementStatus).map(([value, item]) => ({
                value,
                label: item.label,
              }))}
              style={{ width: 150 }}
            />
          </Space>
          <Text type="secondary">共 {agreements.length} 份协议</Text>
        </div>
        <Table
          rowKey="id"
          loading={loading}
          columns={agreementColumns}
          dataSource={agreements}
          scroll={{ x: 1220 }}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          locale={{ emptyText: emptyText('还没有年度协议') }}
        />
      </Card>

      <Drawer
        title={selectedAgreement?.agreement_number || '年度协议详情'}
        size={920}
        open={drawerOpen}
        onClose={() => {
          setDrawerOpen(false)
          setSelectedAgreement(null)
          setSelectedProgress(null)
        }}
      >
        {selectedAgreement && (
          <Space orientation="vertical" size={18} style={{ width: '100%' }}>
            <Descriptions bordered size="small" column={{ xs: 1, md: 2 }}>
              <Descriptions.Item label="协议名称">
                {selectedAgreement.name}
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                <StatusTag
                  value={currentStatus(selectedAgreement)}
                  labels={agreementStatus}
                />
              </Descriptions.Item>
              <Descriptions.Item label="客户">
                {selectedAgreement.agent_company || selectedAgreement.agent_id}
              </Descriptions.Item>
              <Descriptions.Item label="目标口径">
                {basisOptions.find(
                  (item) => item.value === selectedAgreement.qualification_basis,
                )?.label || selectedAgreement.qualification_basis}
              </Descriptions.Item>
              <Descriptions.Item label="目标额">
                {formatMoney(
                  selectedAgreement.target_amount,
                  selectedAgreement.currency,
                )}
              </Descriptions.Item>
              <Descriptions.Item label="周期">
                {selectedAgreement.effective_from} 至 {selectedAgreement.effective_to}
              </Descriptions.Item>
              <Descriptions.Item label="返利方法">
                命中档位后按总销售额追溯
              </Descriptions.Item>
              <Descriptions.Item label="审批人">
                {selectedAgreement.approved_by || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="备注">
                {selectedAgreement.notes || '-'}
              </Descriptions.Item>
            </Descriptions>

            {selectedAgreement.rejection_reason && (
              <Alert
                type="error"
                showIcon
                title="审批驳回"
                description={selectedAgreement.rejection_reason}
              />
            )}

            <Card
              size="small"
              title="协议操作"
              extra={<Tag>创建人 {selectedAgreement.created_by}</Tag>}
            >
              <Space wrap>
                {['draft', 'rejected'].includes(selectedAgreement.status) && (
                  <>
                    <Button
                      icon={<PlusOutlined />}
                      onClick={() => openTierModal()}
                    >
                      添加阶梯
                    </Button>
                    <Button
                      type="primary"
                      icon={<SendOutlined />}
                      disabled={!selectedAgreement.tiers.length}
                      loading={saving}
                      onClick={() =>
                        void runAction(
                          () => api.submitB2BAgreement(selectedAgreement.id),
                          '协议已提交审批',
                        )
                      }
                    >
                      提交审批
                    </Button>
                  </>
                )}
                {selectedAgreement.status === 'pending_approval' && canAdmin && (
                  <>
                    <Button
                      type="primary"
                      icon={<CheckCircleOutlined />}
                      loading={saving}
                      onClick={() =>
                        void runAction(
                          () => api.approveB2BAgreement(selectedAgreement.id),
                          '年度协议已生效',
                        )
                      }
                    >
                      审批生效
                    </Button>
                    <Button
                      danger
                      icon={<CloseCircleOutlined />}
                      onClick={() => openDecision('agreement_reject', selectedAgreement)}
                    >
                      驳回
                    </Button>
                  </>
                )}
                {selectedAgreement.status === 'active' && canAdmin && (
                  <Button
                    danger
                    icon={<StopOutlined />}
                    onClick={() =>
                      openDecision('agreement_terminate', selectedAgreement)
                    }
                  >
                    终止协议
                  </Button>
                )}
              </Space>
            </Card>

            <Card
              size="small"
              title="返利阶梯"
              extra={
                <Text type="secondary">
                  连续、首档从 0 开始、尾档无上限
                </Text>
              }
            >
              <Table
                rowKey="id"
                size="small"
                columns={tierColumns}
                dataSource={selectedAgreement.tiers}
                pagination={false}
                locale={{ emptyText: emptyText('尚未配置返利阶梯') }}
              />
            </Card>

            <Card
              size="small"
              title="目标进度"
              extra={
                selectedProgress ? (
                  <Text type="secondary">统计至 {selectedProgress.as_of}</Text>
                ) : null
              }
            >
              {selectedProgress ? (
                <Space orientation="vertical" size={14} style={{ width: '100%' }}>
                  <Row gutter={[12, 12]}>
                    <Col xs={12} md={6}>
                      <Statistic
                        title="已达成"
                        value={selectedProgress.qualifying_sales}
                        precision={2}
                        prefix={selectedProgress.currency}
                      />
                    </Col>
                    <Col xs={12} md={6}>
                      <Statistic
                        title="剩余目标"
                        value={selectedProgress.remaining_amount}
                        precision={2}
                        prefix={selectedProgress.currency}
                      />
                    </Col>
                    <Col xs={12} md={6}>
                      <Statistic
                        title="当前比例"
                        value={selectedProgress.current_rebate_percent}
                        suffix="%"
                      />
                    </Col>
                    <Col xs={12} md={6}>
                      <Statistic
                        title="预估返利"
                        value={selectedProgress.projected_rebate_amount}
                        precision={2}
                        prefix={selectedProgress.currency}
                      />
                    </Col>
                  </Row>
                  <AntProgress
                    percent={Math.max(
                      0,
                      Math.min(100, Number(selectedProgress.achievement_percent)),
                    )}
                    status="active"
                  />
                  <Text type="secondary">
                    纳入 {selectedProgress.included_record_count} 条事实，排除{' '}
                    {selectedProgress.excluded_record_count} 条；距下一档还需{' '}
                    {selectedProgress.amount_to_next_tier == null
                      ? '已到最高档'
                      : formatMoney(
                          selectedProgress.amount_to_next_tier,
                          selectedProgress.currency,
                        )}
                  </Text>
                  {selectedProgress.missing_rate_currencies.length > 0 && (
                    <Alert
                      type="warning"
                      showIcon
                      title={`缺少直接汇率：${selectedProgress.missing_rate_currencies.join(
                        '、',
                      )}`}
                      description="缺失汇率的记录未计入目标，不会按 1:1 估算。"
                    />
                  )}
                </Space>
              ) : (
                emptyText('配置返利阶梯后可查看目标进度')
              )}
            </Card>

            <Card
              size="small"
              title="返利计算与结算"
              extra={
                selectedAgreement.status === 'active' ? (
                  <Button
                    type="primary"
                    size="small"
                    icon={<FileDoneOutlined />}
                    onClick={openAccrualModal}
                  >
                    计算周期返利
                  </Button>
                ) : null
              }
            >
              <Table
                rowKey="id"
                size="small"
                columns={accrualColumns}
                dataSource={selectedAccruals}
                pagination={false}
                scroll={{ x: 1080 }}
                locale={{ emptyText: emptyText('当前协议还没有返利计算单') }}
              />
            </Card>
          </Space>
        )}
      </Drawer>

      <Modal
        title="新建年度协议"
        open={agreementModalOpen}
        width={820}
        okText="创建协议"
        confirmLoading={saving}
        onOk={() => void createAgreement()}
        onCancel={() => setAgreementModalOpen(false)}
        forceRender
      >
        <Form form={agreementForm} layout="vertical">
          <Row gutter={16}>
            <Col xs={24} md={14}>
              <Form.Item
                name="agent_id"
                label="代理商 / 批发客户"
                rules={[{ required: true, message: '请选择客户' }]}
              >
                <Select
                  showSearch
                  optionFilterProp="label"
                  options={agents.map((agent) => ({
                    value: agent.id,
                    label: `${agent.agent_number} · ${agent.company_name}`,
                  }))}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={10}>
              <Form.Item
                name="name"
                label="协议名称"
                rules={[{ required: true, message: '请输入协议名称' }]}
              >
                <Input placeholder="2026 年度经销合作协议" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col xs={24} md={8}>
              <Form.Item
                name="currency"
                label="协议币种"
                rules={[{ required: true }]}
              >
                <Select options={currencyOptions} />
              </Form.Item>
            </Col>
            <Col xs={24} md={8}>
              <Form.Item
                name="target_amount"
                label="年度目标"
                rules={[{ required: true, message: '请输入目标金额' }]}
              >
                <InputNumber
                  min={0.01}
                  precision={2}
                  style={{ width: '100%' }}
                  placeholder="不换算多币种目标"
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={8}>
              <Form.Item
                name="qualification_basis"
                label="达成口径"
                rules={[{ required: true }]}
              >
                <Select options={[...basisOptions]} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item
                name="effective_from"
                label="生效日期"
                rules={[{ required: true }]}
              >
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item
                name="effective_to"
                label="结束日期"
                rules={[{ required: true }]}
              >
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="notes" label="协议备注">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Divider titlePlacement="start">初始返利阶梯</Divider>
          <Alert
            type="info"
            showIcon
            title="阶梯必须从 0 开始、连续衔接，最后一档留空表示无上限。"
            style={{ marginBottom: 14 }}
          />
          <Form.List name="tiers">
            {(fields, { add, remove }) => (
              <Space orientation="vertical" size={8} style={{ width: '100%' }}>
                {fields.map((field, index) => (
                  <Row key={field.key} gutter={8} align="middle">
                    <Col xs={7}>
                      <Form.Item
                        name={[field.name, 'min_sales_amount']}
                        rules={[{ required: true, message: '请输入下限' }]}
                        style={{ marginBottom: 8 }}
                      >
                        <InputNumber
                          min={0}
                          precision={2}
                          style={{ width: '100%' }}
                          placeholder="下限"
                        />
                      </Form.Item>
                    </Col>
                    <Col xs={7}>
                      <Form.Item
                        name={[field.name, 'max_sales_amount']}
                        style={{ marginBottom: 8 }}
                      >
                        <InputNumber
                          min={0}
                          precision={2}
                          style={{ width: '100%' }}
                          placeholder="上限，尾档留空"
                        />
                      </Form.Item>
                    </Col>
                    <Col xs={7}>
                      <Form.Item
                        name={[field.name, 'rebate_percent']}
                        rules={[{ required: true, message: '请输入比例' }]}
                        style={{ marginBottom: 8 }}
                      >
                        <InputNumber
                          min={0}
                          max={100}
                          precision={2}
                          style={{ width: '100%' }}
                        />
                      </Form.Item>
                    </Col>
                    <Col xs={3}>
                      {fields.length > 1 && (
                        <Button
                          type="text"
                          danger
                          aria-label={`删除第 ${index + 1} 档`}
                          onClick={() => remove(field.name)}
                        >
                          删除
                        </Button>
                      )}
                    </Col>
                  </Row>
                ))}
                <Button
                  type="dashed"
                  icon={<PlusOutlined />}
                  onClick={() =>
                    add({
                      min_sales_amount: 0,
                      max_sales_amount: null,
                      rebate_percent: 0,
                    })
                  }
                >
                  添加阶梯
                </Button>
              </Space>
            )}
          </Form.List>
        </Form>
      </Modal>

      <Modal
        title={editingTier ? '编辑返利阶梯' : '添加返利阶梯'}
        open={tierModalOpen}
        confirmLoading={saving}
        onOk={() => void saveTier()}
        onCancel={() => setTierModalOpen(false)}
        forceRender
      >
        <Form form={tierForm} layout="vertical">
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item
                name="min_sales_amount"
                label="销售下限"
                rules={[{ required: true }]}
              >
                <InputNumber min={0} precision={2} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="max_sales_amount" label="销售上限">
                <InputNumber
                  min={0}
                  precision={2}
                  style={{ width: '100%' }}
                  placeholder="留空表示无上限"
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="rebate_percent"
                label="返利比例"
                rules={[{ required: true }]}
              >
                <InputNumber
                  min={0}
                  max={100}
                  precision={2}
                  style={{ width: '100%' }}
                />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      <Modal
        title="计算周期返利"
        open={accrualModalOpen}
        confirmLoading={saving}
        okText="计算并生成快照"
        onOk={() => void calculateAccrual()}
        onCancel={() => setAccrualModalOpen(false)}
        forceRender
      >
        <Alert
          type="info"
          showIcon
          title="计算只生成可审批快照，不会付款、核销应收或改写历史订单价格。"
          style={{ marginBottom: 16 }}
        />
        <Form form={accrualForm} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="period_start"
                label="周期开始"
                rules={[{ required: true }]}
              >
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="period_end"
                label="周期结束"
                rules={[{ required: true }]}
              >
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      <Modal
        title={
          decisionMode === 'agreement_terminate'
            ? '终止年度协议'
            : '填写驳回原因'
        }
        open={Boolean(decisionMode)}
        confirmLoading={saving}
        okText={decisionMode === 'agreement_terminate' ? '确认终止' : '确认驳回'}
        okButtonProps={{ danger: true }}
        onOk={() => void submitDecision()}
        onCancel={() => {
          setDecisionMode(null)
          setDecisionTarget(null)
        }}
        forceRender
      >
        <Alert
          type="warning"
          showIcon
          title={
            decisionMode === 'agreement_terminate'
              ? '终止后该协议不能继续计算返利。'
              : '驳回原因会保留在审批审计记录中。'
          }
          style={{ marginBottom: 16 }}
        />
        <Form form={decisionForm} layout="vertical">
          <Form.Item
            name="reason"
            label="原因"
            rules={[{ required: true, message: '请输入原因' }]}
          >
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`登记结算凭证 ${settlementTarget?.accrual_number || ''}`}
        open={Boolean(settlementTarget)}
        confirmLoading={saving}
        okText="登记结算"
        onOk={() => void settleAccrual()}
        onCancel={() => setSettlementTarget(null)}
        forceRender
      >
        <Alert
          type="info"
          showIcon
          title="此处只登记银行流水或凭证号，不会自动执行资金支付。"
          style={{ marginBottom: 16 }}
        />
        <Form form={settlementForm} layout="vertical">
          <Form.Item
            name="settlement_reference"
            label="结算凭证号"
            rules={[{ required: true, message: '请输入结算凭证号' }]}
          >
            <Input placeholder="BANK-REBATE-2026-001" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
