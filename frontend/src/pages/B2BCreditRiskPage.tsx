import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Col,
  DatePicker,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Select,
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
  CheckCircleOutlined,
  CloseCircleOutlined,
  EditOutlined,
  FileProtectOutlined,
  LockOutlined,
  PlusOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SendOutlined,
  UnlockOutlined,
} from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'
import { api, ApiError } from '../api/client'
import { useAuth } from '../auth/AuthProvider'

const { Title, Text } = Typography

type CreditStatus = 'normal' | 'watch' | 'hold' | 'frozen'
type RiskAction = 'none' | 'watch' | 'hold' | 'freeze'

interface ListResponse<T> {
  items: T[]
  total: number
}

interface CreditPolicy {
  id: string
  version_number: number
  status: string
  watch_score: number
  hold_score: number
  freeze_score: number
  max_utilization_percent: number
  max_overdue_days: number
  auto_hold_enabled: boolean
  auto_freeze_enabled: boolean
  insurance_required_above: number
  notes: string | null
  created_by: string
  submitted_by: string | null
  submitted_at: string | null
  approved_by: string | null
  approved_at: string | null
  rejected_by: string | null
  rejected_at: string | null
  rejection_reason: string | null
  created_at: string
  updated_at: string
}

interface CreditPolicyList extends ListResponse<CreditPolicy> {
  active_policy: CreditPolicy | null
}

interface RiskAssessment {
  id: string
  agent_id: string
  policy_id: string
  score: number
  risk_level: string
  recommended_action: RiskAction
  applied_action: RiskAction
  credit_status_before: CreditStatus
  credit_status_after: CreditStatus
  exposure_amount: number
  overdue_amount: number
  utilization_percent: number
  overdue_ratio_percent: number
  max_days_overdue: number
  past_due_invoice_count: number
  written_off_amount: number
  insurance_coverage_amount: number
  insurance_coverage_percent: number
  net_exposure_amount: number
  factors: Record<string, unknown>
  message: string | null
  assessed_by: string
  assessed_at: string
  created_at: string
}

interface AgentRisk {
  id: string
  agent_number: string
  company_name: string
  contact_name: string
  email: string
  country: string | null
  status: string
  credit_status: CreditStatus
  credit_status_reason: string | null
  credit_status_updated_by: string | null
  credit_status_updated_at: string | null
  credit_limit: number
  current_balance: number
  currency: string
  latest_assessment: RiskAssessment | null
}

interface CreditRiskOverview extends ListResponse<AgentRisk> {
  active_policy: CreditPolicy | null
}

interface CreditStatusEvent {
  id: string
  agent_id: string
  assessment_id: string | null
  previous_status: CreditStatus
  new_status: CreditStatus
  action: string
  reason: string
  actor: string
  evidence: Record<string, unknown>
  created_at: string
}

interface InsurancePolicy {
  id: string
  agent_id: string
  agent_company: string
  policy_number: string
  provider: string
  status: string
  currency: string
  coverage_limit: number
  coverage_percent: number
  effective_from: string
  effective_to: string
  notes: string | null
  created_by: string
  updated_by: string
  created_at: string
  updated_at: string
}

interface InsuranceClaim {
  id: string
  claim_number: string
  policy_id: string
  policy_number: string
  invoice_id: string
  invoice_number: string
  agent_id: string
  agent_company: string
  status: string
  claimed_amount: number
  recovered_amount: number
  currency: string
  reason: string
  evidence: Record<string, unknown>
  created_by: string
  submitted_by: string | null
  submitted_at: string | null
  decided_by: string | null
  decided_at: string | null
  rejection_reason: string | null
  settled_by: string | null
  settled_at: string | null
  settlement_reference: string | null
  created_at: string
  updated_at: string
}

interface InvoiceRecord {
  id: string
  invoice_number: string
  agent_id: string
  agent_company: string
  effective_status: string
  currency: string
  balance_due: number
  due_date: string
}

type StatusDecision = 'hold' | 'frozen' | 'normal'
type ClaimDecision = 'reject' | 'settle'

const policyStatus: Record<string, { color: string; label: string }> = {
  draft: { color: 'default', label: '草稿' },
  pending_approval: { color: 'orange', label: '待审批' },
  active: { color: 'green', label: '生效' },
  rejected: { color: 'red', label: '已驳回' },
  superseded: { color: 'blue', label: '历史版本' },
}

const creditStatus: Record<CreditStatus, { color: string; label: string }> = {
  normal: { color: 'green', label: '正常' },
  watch: { color: 'orange', label: '观察' },
  hold: { color: 'volcano', label: '暂停接单' },
  frozen: { color: 'red', label: '冻结' },
}

const riskLevel: Record<string, { color: string; label: string }> = {
  low: { color: 'green', label: '低风险' },
  medium: { color: 'orange', label: '中风险' },
  high: { color: 'volcano', label: '高风险' },
  critical: { color: 'red', label: '严重风险' },
}

const actionLabel: Record<RiskAction, string> = {
  none: '无需动作',
  watch: '观察',
  hold: '暂停接单',
  freeze: '冻结',
}

const insuranceStatus: Record<string, { color: string; label: string }> = {
  draft: { color: 'default', label: '草稿' },
  active: { color: 'green', label: '生效' },
  expired: { color: 'default', label: '已过期' },
  cancelled: { color: 'red', label: '已取消' },
}

const claimStatus: Record<string, { color: string; label: string }> = {
  draft: { color: 'default', label: '草稿' },
  submitted: { color: 'orange', label: '待决定' },
  approved: { color: 'blue', label: '已批准' },
  rejected: { color: 'red', label: '已驳回' },
  settled: { color: 'green', label: '已结算' },
}

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
  }).format(Number(value || 0))
}

function formatDateTime(value: string | null): string {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '-'
}

function emptyText(label: string) {
  return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={label} />
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

export default function B2BCreditRiskPage() {
  const { user } = useAuth()
  const { message } = AntApp.useApp()
  const canEdit = user?.role === 'admin' || user?.role === 'operator'
  const canAdmin = user?.role === 'admin'

  const [activeTab, setActiveTab] = useState('risks')
  const [policies, setPolicies] = useState<CreditPolicy[]>([])
  const [activePolicy, setActivePolicy] = useState<CreditPolicy | null>(null)
  const [risks, setRisks] = useState<AgentRisk[]>([])
  const [insurancePolicies, setInsurancePolicies] = useState<InsurancePolicy[]>([])
  const [claims, setClaims] = useState<InsuranceClaim[]>([])
  const [invoices, setInvoices] = useState<InvoiceRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [selectedAgent, setSelectedAgent] = useState<AgentRisk | null>(null)
  const [history, setHistory] = useState<CreditStatusEvent[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)

  const [policyModalOpen, setPolicyModalOpen] = useState(false)
  const [insuranceModalOpen, setInsuranceModalOpen] = useState(false)
  const [editingInsurance, setEditingInsurance] =
    useState<InsurancePolicy | null>(null)
  const [claimModalOpen, setClaimModalOpen] = useState(false)
  const [statusDecision, setStatusDecision] = useState<StatusDecision | null>(null)
  const [claimDecision, setClaimDecision] = useState<ClaimDecision | null>(null)
  const [decisionPolicy, setDecisionPolicy] = useState<CreditPolicy | null>(null)
  const [decisionClaim, setDecisionClaim] = useState<InsuranceClaim | null>(null)

  const [policyForm] = Form.useForm()
  const [insuranceForm] = Form.useForm()
  const [claimForm] = Form.useForm()
  const [decisionForm] = Form.useForm()

  const loadAgentDetail = useCallback(async (agentId: string) => {
    setHistoryLoading(true)
    try {
      const [agent, events] = await Promise.all([
        api.getB2BCreditAgent(agentId) as Promise<AgentRisk>,
        api.getB2BCreditAgentHistory(agentId) as Promise<CreditStatusEvent[]>,
      ])
      setSelectedAgent(agent)
      setHistory(events)
    } finally {
      setHistoryLoading(false)
    }
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [
        policyResponse,
        riskResponse,
        insuranceResponse,
        claimResponse,
        invoiceResponse,
      ] = await Promise.all([
        api.getB2BCreditPolicies() as Promise<CreditPolicyList>,
        api.getB2BCreditRisks() as Promise<CreditRiskOverview>,
        api.getB2BCreditInsurance() as Promise<ListResponse<InsurancePolicy>>,
        api.getB2BCreditClaims() as Promise<ListResponse<InsuranceClaim>>,
        api.getB2BInvoices(1, 200) as Promise<ListResponse<InvoiceRecord>>,
      ])
      setPolicies(policyResponse.items || [])
      setActivePolicy(
        policyResponse.active_policy || riskResponse.active_policy || null,
      )
      setRisks(riskResponse.items || [])
      setInsurancePolicies(insuranceResponse.items || [])
      setClaims(claimResponse.items || [])
      setInvoices(invoiceResponse.items || [])
      if (selectedAgent) {
        const latest = (riskResponse.items || []).find(
          (row) => row.id === selectedAgent.id,
        )
        if (latest) {
          setSelectedAgent(latest)
          await loadAgentDetail(latest.id)
        }
      }
    } catch (loadError) {
      setError(errorMessage(loadError))
    } finally {
      setLoading(false)
    }
  }, [loadAgentDetail, selectedAgent])

  useEffect(() => {
    void load()
    // Data refresh keeps the current drawer selection in sync.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const runAction = async (action: () => Promise<unknown>, success: string) => {
    setSaving(true)
    try {
      await action()
      message.success(success)
      await load()
    } catch (actionError) {
      message.error(errorMessage(actionError))
    } finally {
      setSaving(false)
    }
  }

  const openAgent = async (agent: AgentRisk) => {
    setSelectedAgent(agent)
    setHistory([])
    try {
      await loadAgentDetail(agent.id)
    } catch (detailError) {
      message.error(errorMessage(detailError))
    }
  }

  const closeAgent = () => {
    setSelectedAgent(null)
    setHistory([])
  }

  const openPolicyModal = () => {
    policyForm.resetFields()
    policyForm.setFieldsValue({
      watch_score: 35,
      hold_score: 60,
      freeze_score: 80,
      max_utilization_percent: 100,
      max_overdue_days: 60,
      auto_hold_enabled: true,
      auto_freeze_enabled: false,
      insurance_required_above: 0,
    })
    setPolicyModalOpen(true)
  }

  const createPolicy = async () => {
    try {
      const values = await policyForm.validateFields()
      setSaving(true)
      await api.createB2BCreditPolicy(values)
      message.success('信用政策草稿已创建')
      setPolicyModalOpen(false)
      await load()
    } catch (saveError) {
      if (saveError instanceof Error && 'errorFields' in saveError) return
      message.error(`创建失败：${errorMessage(saveError)}`)
    } finally {
      setSaving(false)
    }
  }

  const openPolicyDecision = (policy: CreditPolicy) => {
    decisionForm.resetFields()
    setDecisionPolicy(policy)
  }

  const rejectPolicy = async () => {
    if (!decisionPolicy) return
    try {
      const values = await decisionForm.validateFields()
      setSaving(true)
      await api.rejectB2BCreditPolicy(decisionPolicy.id, values.reason)
      message.success('信用政策已驳回')
      setDecisionPolicy(null)
      await load()
    } catch (saveError) {
      if (saveError instanceof Error && 'errorFields' in saveError) return
      message.error(errorMessage(saveError))
    } finally {
      setSaving(false)
    }
  }

  const openInsuranceModal = (policy?: InsurancePolicy) => {
    setEditingInsurance(policy || null)
    insuranceForm.resetFields()
    if (policy) {
      insuranceForm.setFieldsValue({
        ...policy,
        effective_from: dayjs(policy.effective_from),
        effective_to: dayjs(policy.effective_to),
      })
    } else {
      insuranceForm.setFieldsValue({
        currency: activePolicy ? 'USD' : 'USD',
        status: 'draft',
        coverage_percent: 80,
        effective_from: dayjs(),
        effective_to: dayjs().add(1, 'year'),
      })
    }
    setInsuranceModalOpen(true)
  }

  const saveInsurance = async () => {
    try {
      const values = await insuranceForm.validateFields()
      const payload: Record<string, unknown> = {
        agent_id: values.agent_id,
        policy_number: values.policy_number,
        provider: values.provider,
        currency: values.currency,
        coverage_limit: values.coverage_limit,
        coverage_percent: values.coverage_percent,
        effective_from: (values.effective_from as Dayjs).format('YYYY-MM-DD'),
        effective_to: (values.effective_to as Dayjs).format('YYYY-MM-DD'),
        status: values.status,
        notes: values.notes || null,
      }
      setSaving(true)
      if (editingInsurance) {
        delete payload.agent_id
        delete payload.policy_number
        delete payload.currency
        await api.updateB2BCreditInsurance(editingInsurance.id, payload)
        message.success('信用保险保单已更新')
      } else {
        await api.createB2BCreditInsurance(payload)
        message.success('信用保险保单已创建')
      }
      setInsuranceModalOpen(false)
      await load()
    } catch (saveError) {
      if (saveError instanceof Error && 'errorFields' in saveError) return
      message.error(`保存失败：${errorMessage(saveError)}`)
    } finally {
      setSaving(false)
    }
  }

  const openClaimModal = () => {
    claimForm.resetFields()
    claimForm.setFieldsValue({})
    setClaimModalOpen(true)
  }

  const createClaim = async () => {
    try {
      const values = await claimForm.validateFields()
      setSaving(true)
      await api.createB2BCreditClaim({
        policy_id: values.policy_id,
        invoice_id: values.invoice_id,
        claimed_amount: values.claimed_amount,
        reason: values.reason,
        evidence: {},
      })
      message.success('保险索赔草稿已创建')
      setClaimModalOpen(false)
      await load()
    } catch (saveError) {
      if (saveError instanceof Error && 'errorFields' in saveError) return
      message.error(`创建失败：${errorMessage(saveError)}`)
    } finally {
      setSaving(false)
    }
  }

  const openStatusDecision = (status: StatusDecision) => {
    decisionForm.resetFields()
    setStatusDecision(status)
  }

  const submitStatusDecision = async () => {
    if (!selectedAgent || !statusDecision) return
    try {
      const values = await decisionForm.validateFields()
      setSaving(true)
      await api.updateB2BCreditAgentStatus(
        selectedAgent.id,
        statusDecision,
        values.reason,
      )
      message.success(
        statusDecision === 'normal'
          ? '客户信用限制已解除'
          : statusDecision === 'frozen'
            ? '客户已冻结'
            : '客户已暂停接单',
      )
      setStatusDecision(null)
      await load()
      await loadAgentDetail(selectedAgent.id)
    } catch (saveError) {
      if (saveError instanceof Error && 'errorFields' in saveError) return
      message.error(errorMessage(saveError))
    } finally {
      setSaving(false)
    }
  }

  const openClaimDecision = (
    decision: ClaimDecision,
    claim: InsuranceClaim,
  ) => {
    decisionForm.resetFields()
    if (decision === 'settle') {
      decisionForm.setFieldsValue({
        recovered_amount: claim.claimed_amount,
      })
    }
    setClaimDecision(decision)
    setDecisionClaim(claim)
  }

  const submitClaimDecision = async () => {
    if (!decisionClaim || !claimDecision) return
    try {
      const values = await decisionForm.validateFields()
      setSaving(true)
      if (claimDecision === 'reject') {
        await api.rejectB2BCreditClaim(decisionClaim.id, values.reason)
        message.success('保险索赔已驳回')
      } else {
        await api.settleB2BCreditClaim(
          decisionClaim.id,
          values.recovered_amount ?? null,
          values.settlement_reference,
        )
        message.success('保险赔款结算凭证已登记')
      }
      setClaimDecision(null)
      setDecisionClaim(null)
      await load()
    } catch (saveError) {
      if (saveError instanceof Error && 'errorFields' in saveError) return
      message.error(errorMessage(saveError))
    } finally {
      setSaving(false)
    }
  }

  const metrics = useMemo(() => {
    const riskCount = risks.filter((row) =>
      ['high', 'critical'].includes(row.latest_assessment?.risk_level || ''),
    ).length
    const blockedCount = risks.filter((row) =>
      ['hold', 'frozen'].includes(row.credit_status),
    ).length
    const activeInsuranceCount = insurancePolicies.filter(
      (row) => row.status === 'active',
    ).length
    const pendingClaims = claims.filter(
      (row) => row.status === 'submitted',
    ).length
    return { riskCount, blockedCount, activeInsuranceCount, pendingClaims }
  }, [claims, insurancePolicies, risks])

  const activeInsurance = useMemo(
    () => insurancePolicies.filter((row) => row.status === 'active'),
    [insurancePolicies],
  )

  const agentOptions = useMemo(
    () =>
      risks.map((agent) => ({
        value: agent.id,
        label: `${agent.agent_number} · ${agent.company_name}`,
      })),
    [risks],
  )

  const riskColumns: ColumnsType<AgentRisk> = [
    {
      title: '客户',
      fixed: 'left',
      width: 230,
      render: (_, row) => (
        <Space orientation="vertical" size={0}>
          <Text strong>{row.company_name}</Text>
          <Text type="secondary">
            {row.agent_number} · {row.country || '未填写国家'}
          </Text>
        </Space>
      ),
    },
    {
      title: '信用状态',
      width: 110,
      render: (_, row) => (
        <StatusTag value={row.credit_status} labels={creditStatus} />
      ),
    },
    {
      title: '风险评分',
      width: 145,
      render: (_, row) =>
        row.latest_assessment ? (
          <Space orientation="vertical" size={0}>
            <Text strong>{row.latest_assessment.score} / 100</Text>
            <StatusTag
              value={row.latest_assessment.risk_level}
              labels={riskLevel}
            />
          </Space>
        ) : (
          <Text type="secondary">尚未评估</Text>
        ),
    },
    {
      title: '建议动作',
      width: 115,
      render: (_, row) =>
        row.latest_assessment ? (
          <Tag>{actionLabel[row.latest_assessment.recommended_action]}</Tag>
        ) : (
          '-'
        ),
    },
    {
      title: '信用额度',
      width: 150,
      align: 'right',
      render: (_, row) => (
        <Space orientation="vertical" size={0}>
          <Text>{formatMoney(row.credit_limit, row.currency)}</Text>
          <Text type="secondary">
            当前余额 {formatMoney(row.current_balance, row.currency)}
          </Text>
        </Space>
      ),
    },
    {
      title: '应收 / 逾期',
      width: 165,
      align: 'right',
      render: (_, row) => (
        <Space orientation="vertical" size={0}>
          <Text>
            {formatMoney(
              row.latest_assessment?.exposure_amount ?? row.current_balance,
              row.currency,
            )}
          </Text>
          <Text type="danger">
            逾期{' '}
            {formatMoney(
              row.latest_assessment?.overdue_amount ?? 0,
              row.currency,
            )}
          </Text>
        </Space>
      ),
    },
    {
      title: '最大逾期',
      width: 95,
      align: 'right',
      render: (_, row) => (
        <Text type={(row.latest_assessment?.max_days_overdue || 0) > 0 ? 'danger' : 'secondary'}>
          {row.latest_assessment?.max_days_overdue || 0} 天
        </Text>
      ),
    },
    {
      title: '额度利用',
      width: 100,
      align: 'right',
      render: (_, row) =>
        row.latest_assessment
          ? `${Number(row.latest_assessment.utilization_percent).toFixed(2)}%`
          : '-',
    },
    {
      title: '保险覆盖',
      width: 160,
      align: 'right',
      render: (_, row) =>
        row.latest_assessment?.insurance_coverage_amount ? (
          <Space orientation="vertical" size={0}>
            <Text strong>
              {formatMoney(
                row.latest_assessment.insurance_coverage_amount,
                row.currency,
              )}
            </Text>
            <Text type="secondary">
              {Number(
                row.latest_assessment.insurance_coverage_percent,
              ).toFixed(2)}
              %
            </Text>
          </Space>
        ) : (
          <Text type="secondary">无有效覆盖</Text>
        ),
    },
    {
      title: '操作',
      fixed: 'right',
      width: 155,
      render: (_, row) => (
        <Space size="small">
          <Button type="link" size="small" onClick={() => void openAgent(row)}>
            查看
          </Button>
          {canEdit && (
            <Button
              type="link"
              size="small"
              loading={saving}
              onClick={() =>
                void runAction(
                  () => api.assessB2BCreditAgent(row.id),
                  '风险评估已生成',
                )
              }
            >
              评估
            </Button>
          )}
        </Space>
      ),
    },
  ]

  const policyColumns: ColumnsType<CreditPolicy> = [
    {
      title: '版本',
      width: 90,
      render: (_, row) => <Text strong>v{row.version_number}</Text>,
    },
    {
      title: '状态',
      width: 110,
      render: (_, row) => (
        <StatusTag value={row.status} labels={policyStatus} />
      ),
    },
    {
      title: '评分阈值',
      width: 230,
      render: (_, row) => (
        <Space wrap size={4}>
          <Tag color="orange">观察 {row.watch_score}</Tag>
          <Tag color="volcano">暂停 {row.hold_score}</Tag>
          <Tag color="red">冻结 {row.freeze_score}</Tag>
        </Space>
      ),
    },
    {
      title: '额度 / 逾期',
      width: 170,
      render: (_, row) => (
        <Space orientation="vertical" size={0}>
          <Text>利用率 {Number(row.max_utilization_percent).toFixed(2)}%</Text>
          <Text type="secondary">最大逾期 {row.max_overdue_days} 天</Text>
        </Space>
      ),
    },
    {
      title: '自动动作',
      width: 190,
      render: (_, row) => (
        <Space wrap size={4}>
          <Tag color={row.auto_hold_enabled ? 'orange' : 'default'}>
            自动暂停 {row.auto_hold_enabled ? '开' : '关'}
          </Tag>
          <Tag color={row.auto_freeze_enabled ? 'red' : 'default'}>
            自动冻结 {row.auto_freeze_enabled ? '开' : '关'}
          </Tag>
        </Space>
      ),
    },
    {
      title: '审批链',
      width: 220,
      render: (_, row) => (
        <Space orientation="vertical" size={0}>
          <Text type="secondary">创建：{row.created_by}</Text>
          <Text type="secondary">提交：{row.submitted_by || '-'}</Text>
          <Text type="secondary">审批：{row.approved_by || '-'}</Text>
        </Space>
      ),
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      width: 150,
      render: formatDateTime,
    },
    {
      title: '操作',
      fixed: 'right',
      width: 200,
      render: (_, row) => (
        <Space size="small">
          {canEdit && ['draft', 'rejected'].includes(row.status) && (
            <Button
              type="link"
              size="small"
              icon={<SendOutlined />}
              loading={saving}
              onClick={() =>
                void runAction(
                  () => api.submitB2BCreditPolicy(row.id),
                  '信用政策已提交审批',
                )
              }
            >
              提交审批
            </Button>
          )}
          {canAdmin && row.status === 'pending_approval' && (
            <>
              <Button
                type="link"
                size="small"
                icon={<CheckCircleOutlined />}
                loading={saving}
                onClick={() =>
                  void runAction(
                    () => api.approveB2BCreditPolicy(row.id),
                    '信用政策已生效',
                  )
                }
              >
                审批生效
              </Button>
              <Button
                type="link"
                danger
                size="small"
                icon={<CloseCircleOutlined />}
                onClick={() => openPolicyDecision(row)}
              >
                驳回
              </Button>
            </>
          )}
        </Space>
      ),
    },
  ]

  const insuranceColumns: ColumnsType<InsurancePolicy> = [
    {
      title: '保单',
      fixed: 'left',
      width: 220,
      render: (_, row) => (
        <Space orientation="vertical" size={0}>
          <Text strong>{row.policy_number}</Text>
          <Text type="secondary">{row.provider}</Text>
        </Space>
      ),
    },
    { title: '客户', dataIndex: 'agent_company', width: 190 },
    {
      title: '状态',
      width: 100,
      render: (_, row) => (
        <StatusTag value={row.status} labels={insuranceStatus} />
      ),
    },
    {
      title: '覆盖上限',
      width: 150,
      align: 'right',
      render: (_, row) => (
        <Text strong>{formatMoney(row.coverage_limit, row.currency)}</Text>
      ),
    },
    {
      title: '覆盖比例',
      width: 100,
      align: 'right',
      render: (_, row) => `${Number(row.coverage_percent).toFixed(2)}%`,
    },
    {
      title: '有效期',
      width: 200,
      render: (_, row) => `${row.effective_from} 至 ${row.effective_to}`,
    },
    {
      title: '更新',
      dataIndex: 'updated_at',
      width: 150,
      render: formatDateTime,
    },
    {
      title: '操作',
      fixed: 'right',
      width: 100,
      render: (_, row) =>
        canEdit ? (
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => openInsuranceModal(row)}
          >
            编辑
          </Button>
        ) : (
          <Text type="secondary">只读</Text>
        ),
    },
  ]

  const claimColumns: ColumnsType<InsuranceClaim> = [
    {
      title: '索赔单',
      fixed: 'left',
      width: 190,
      render: (_, row) => (
        <Space orientation="vertical" size={0}>
          <Text strong>{row.claim_number}</Text>
          <Text type="secondary">{row.policy_number}</Text>
        </Space>
      ),
    },
    { title: '客户', dataIndex: 'agent_company', width: 180 },
    {
      title: '发票',
      dataIndex: 'invoice_number',
      width: 170,
    },
    {
      title: '状态',
      width: 100,
      render: (_, row) => (
        <StatusTag value={row.status} labels={claimStatus} />
      ),
    },
    {
      title: '申请金额',
      width: 135,
      align: 'right',
      render: (_, row) => (
        <Text strong>{formatMoney(row.claimed_amount, row.currency)}</Text>
      ),
    },
    {
      title: '已回收',
      width: 130,
      align: 'right',
      render: (_, row) => formatMoney(row.recovered_amount, row.currency),
    },
    {
      title: '索赔原因',
      dataIndex: 'reason',
      width: 220,
      ellipsis: true,
    },
    {
      title: '操作',
      fixed: 'right',
      width: 230,
      render: (_, row) => (
        <Space size="small">
          {canEdit && row.status === 'draft' && (
            <Button
              type="link"
              size="small"
              icon={<SendOutlined />}
              loading={saving}
              onClick={() =>
                void runAction(
                  () => api.submitB2BCreditClaim(row.id),
                  '保险索赔已提交',
                )
              }
            >
              提交
            </Button>
          )}
          {canAdmin && row.status === 'submitted' && (
            <>
              <Button
                type="link"
                size="small"
                icon={<CheckCircleOutlined />}
                loading={saving}
                onClick={() =>
                  void runAction(
                    () => api.approveB2BCreditClaim(row.id),
                    '保险索赔已批准',
                  )
                }
              >
                批准
              </Button>
              <Button
                type="link"
                danger
                size="small"
                onClick={() => openClaimDecision('reject', row)}
              >
                驳回
              </Button>
            </>
          )}
          {canAdmin && row.status === 'approved' && (
            <Button
              type="link"
              size="small"
              icon={<FileProtectOutlined />}
              onClick={() => openClaimDecision('settle', row)}
            >
              登记结算
            </Button>
          )}
        </Space>
      ),
    },
  ]

  const tabItems = [
    {
      key: 'risks',
      label: '风险总览',
      children: (
        <>
          {!activePolicy && (
            <Alert
              type="warning"
              showIcon
              title="尚未启用信用政策"
              description="只有管理员审批生效的政策才能用于评分和自动暂停/冻结。"
              className="page-alert"
            />
          )}
          <div className="table-toolbar">
            <Text type="secondary">共 {risks.length} 个 B2B 客户</Text>
            <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>
              刷新风险
            </Button>
          </div>
          <Table
            rowKey="id"
            loading={loading}
            columns={riskColumns}
            dataSource={risks}
            scroll={{ x: 1580 }}
            pagination={{ pageSize: 20, showSizeChanger: false }}
            locale={{ emptyText: emptyText('还没有 B2B 客户') }}
          />
        </>
      ),
    },
    {
      key: 'policies',
      label: '信用政策',
      children: (
        <>
          <div className="table-toolbar">
            <Space wrap>
              <Text type="secondary">共 {policies.length} 个政策版本</Text>
              {activePolicy && (
                <Tag color="green">当前生效 v{activePolicy.version_number}</Tag>
              )}
            </Space>
            {canEdit && (
              <Button type="primary" icon={<PlusOutlined />} onClick={openPolicyModal}>
                新建政策
              </Button>
            )}
          </div>
          <Table
            rowKey="id"
            loading={loading}
            columns={policyColumns}
            dataSource={policies}
            scroll={{ x: 1320 }}
            pagination={false}
            expandable={{
              expandedRowRender: (row) => (
                <Descriptions size="small" column={{ xs: 1, md: 3 }}>
                  <Descriptions.Item label="保险要求阈值">
                    {formatMoney(row.insurance_required_above, 'USD')}
                  </Descriptions.Item>
                  <Descriptions.Item label="提交时间">
                    {formatDateTime(row.submitted_at)}
                  </Descriptions.Item>
                  <Descriptions.Item label="审批时间">
                    {formatDateTime(row.approved_at)}
                  </Descriptions.Item>
                  <Descriptions.Item label="备注" span={3}>
                    {row.notes || '-'}
                  </Descriptions.Item>
                  {row.rejection_reason && (
                    <Descriptions.Item label="驳回原因" span={3}>
                      <Text type="danger">{row.rejection_reason}</Text>
                    </Descriptions.Item>
                  )}
                </Descriptions>
              ),
            }}
            locale={{ emptyText: emptyText('尚未创建信用政策') }}
          />
        </>
      ),
    },
    {
      key: 'insurance',
      label: '信用保险',
      children: (
        <>
          <div className="table-toolbar">
            <Text type="secondary">
              共 {insurancePolicies.length} 份保单，其中 {activeInsurance.length} 份生效
            </Text>
            {canEdit && (
              <Button
                type="primary"
                icon={<SafetyCertificateOutlined />}
                disabled={!risks.length}
                onClick={() => openInsuranceModal()}
              >
                新建保单
              </Button>
            )}
          </div>
          <Table
            rowKey="id"
            loading={loading}
            columns={insuranceColumns}
            dataSource={insurancePolicies}
            scroll={{ x: 1230 }}
            pagination={{ pageSize: 20, showSizeChanger: false }}
            locale={{ emptyText: emptyText('尚未登记信用保险保单') }}
          />
        </>
      ),
    },
    {
      key: 'claims',
      label: '保险索赔',
      children: (
        <>
          <div className="table-toolbar">
            <Text type="secondary">共 {claims.length} 笔索赔</Text>
            {canEdit && (
              <Button
                type="primary"
                icon={<PlusOutlined />}
                disabled={!activeInsurance.length || !invoices.length}
                onClick={openClaimModal}
              >
                新建索赔
              </Button>
            )}
          </div>
          <Table
            rowKey="id"
            loading={loading}
            columns={claimColumns}
            dataSource={claims}
            scroll={{ x: 1390 }}
            pagination={{ pageSize: 20, showSizeChanger: false }}
            locale={{ emptyText: emptyText('尚未登记保险索赔') }}
          />
        </>
      ),
    },
  ]

  return (
    <div className="dashboard-page">
      <div className="page-heading">
        <div>
          <div className="page-kicker page-kicker--b2b">B2B CREDIT CONTROL</div>
          <Title level={2}>信用风控与信用保险</Title>
          <p>
            统一管理客户信用状态、风险评分、自动冻结和信用保险。评分与动作由后端确定性规则计算，AI
            只能解释和建议。
          </p>
        </div>
        <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>
          刷新
        </Button>
      </div>

      {error && (
        <Alert
          type="error"
          showIcon
          title="信用风控数据加载失败"
          description={error}
          className="page-alert"
        />
      )}

      <Row gutter={[16, 16]}>
        <Col xs={12} lg={6}>
          <Card variant="borderless">
            <Statistic
              title="当前政策"
              value={activePolicy ? `v${activePolicy.version_number}` : '未启用'}
            />
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card variant="borderless">
            <Statistic title="高风险客户" value={metrics.riskCount} />
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card variant="borderless">
            <Statistic title="暂停 / 冻结" value={metrics.blockedCount} />
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card variant="borderless">
            <Statistic
              title="有效保单 / 待审索赔"
              value={`${metrics.activeInsuranceCount} / ${metrics.pendingClaims}`}
            />
          </Card>
        </Col>
      </Row>

      <Card variant="borderless" style={{ marginTop: 16 }}>
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} />
      </Card>

      <Drawer
        title="客户信用档案"
        size={720}
        open={Boolean(selectedAgent)}
        onClose={closeAgent}
        loading={historyLoading}
      >
        {selectedAgent && (
          <Space orientation="vertical" size={16} style={{ width: '100%' }}>
            <Descriptions bordered size="small" column={2}>
              <Descriptions.Item label="客户" span={2}>
                {selectedAgent.company_name}
              </Descriptions.Item>
              <Descriptions.Item label="客户编号">
                {selectedAgent.agent_number}
              </Descriptions.Item>
              <Descriptions.Item label="联系人">
                {selectedAgent.contact_name || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="信用状态">
                <StatusTag
                  value={selectedAgent.credit_status}
                  labels={creditStatus}
                />
              </Descriptions.Item>
              <Descriptions.Item label="更新时间">
                {formatDateTime(selectedAgent.credit_status_updated_at)}
              </Descriptions.Item>
              <Descriptions.Item label="信用额度">
                {formatMoney(selectedAgent.credit_limit, selectedAgent.currency)}
              </Descriptions.Item>
              <Descriptions.Item label="当前余额">
                {formatMoney(selectedAgent.current_balance, selectedAgent.currency)}
              </Descriptions.Item>
              <Descriptions.Item label="状态原因" span={2}>
                {selectedAgent.credit_status_reason || '-'}
              </Descriptions.Item>
            </Descriptions>

            {selectedAgent.latest_assessment ? (
              <Card size="small" title="最新风险评估">
                <Row gutter={[12, 12]}>
                  <Col span={6}>
                    <Statistic
                      title="评分"
                      value={selectedAgent.latest_assessment.score}
                      suffix="/ 100"
                    />
                  </Col>
                  <Col span={6}>
                    <Statistic
                      title="额度利用率"
                      value={selectedAgent.latest_assessment.utilization_percent}
                      suffix="%"
                      precision={2}
                    />
                  </Col>
                  <Col span={6}>
                    <Statistic
                      title="最大逾期"
                      value={selectedAgent.latest_assessment.max_days_overdue}
                      suffix="天"
                    />
                  </Col>
                  <Col span={6}>
                    <Statistic
                      title="净敞口"
                      value={selectedAgent.latest_assessment.net_exposure_amount}
                      precision={2}
                      prefix={selectedAgent.currency}
                    />
                  </Col>
                </Row>
                <Descriptions size="small" column={2} style={{ marginTop: 14 }}>
                  <Descriptions.Item label="风险级别">
                    <StatusTag
                      value={selectedAgent.latest_assessment.risk_level}
                      labels={riskLevel}
                    />
                  </Descriptions.Item>
                  <Descriptions.Item label="建议动作">
                    {actionLabel[
                      selectedAgent.latest_assessment.recommended_action
                    ]}
                  </Descriptions.Item>
                  <Descriptions.Item label="保险覆盖">
                    {formatMoney(
                      selectedAgent.latest_assessment.insurance_coverage_amount,
                      selectedAgent.currency,
                    )}
                  </Descriptions.Item>
                  <Descriptions.Item label="评估人">
                    {selectedAgent.latest_assessment.assessed_by}
                  </Descriptions.Item>
                  <Descriptions.Item label="评估说明" span={2}>
                    {selectedAgent.latest_assessment.message || '-'}
                  </Descriptions.Item>
                </Descriptions>
              </Card>
            ) : (
              <Alert
                type="info"
                showIcon
                title="尚未评估"
                description="启用信用政策后，可运行风险评估生成可审计快照。"
              />
            )}

            <Card size="small" title="信用操作">
              <Space wrap>
                {canEdit && (
                  <Button
                    icon={<ReloadOutlined />}
                    loading={saving}
                    onClick={() =>
                      void runAction(
                        () => api.assessB2BCreditAgent(selectedAgent.id),
                        '风险评估已生成',
                      )
                    }
                  >
                    重新评估
                  </Button>
                )}
                {canAdmin && selectedAgent.credit_status !== 'hold' && (
                  <Button
                    icon={<LockOutlined />}
                    onClick={() => openStatusDecision('hold')}
                  >
                    暂停接单
                  </Button>
                )}
                {canAdmin && selectedAgent.credit_status !== 'frozen' && (
                  <Button
                    danger
                    icon={<LockOutlined />}
                    onClick={() => openStatusDecision('frozen')}
                  >
                    冻结客户
                  </Button>
                )}
                {canAdmin &&
                  ['hold', 'frozen', 'watch'].includes(
                    selectedAgent.credit_status,
                  ) && (
                    <Button
                      type="primary"
                      icon={<UnlockOutlined />}
                      onClick={() => openStatusDecision('normal')}
                    >
                      解除限制
                    </Button>
                  )}
              </Space>
            </Card>

            <Card size="small" title="状态历史">
              <Table
                rowKey="id"
                size="small"
                loading={historyLoading}
                dataSource={history}
                pagination={false}
                locale={{ emptyText: emptyText('还没有信用状态变化') }}
                columns={[
                  {
                    title: '状态变化',
                    width: 150,
                    render: (_, row) => (
                      <Space size={4}>
                        <StatusTag
                          value={row.previous_status}
                          labels={creditStatus}
                        />
                        <span>→</span>
                        <StatusTag value={row.new_status} labels={creditStatus} />
                      </Space>
                    ),
                  },
                  {
                    title: '动作',
                    dataIndex: 'action',
                    width: 120,
                  },
                  {
                    title: '原因',
                    dataIndex: 'reason',
                    ellipsis: true,
                  },
                  {
                    title: '操作者',
                    dataIndex: 'actor',
                    width: 170,
                  },
                  {
                    title: '时间',
                    dataIndex: 'created_at',
                    width: 150,
                    render: formatDateTime,
                  },
                ]}
              />
            </Card>
          </Space>
        )}
      </Drawer>

      <Modal
        title="新建信用政策"
        open={policyModalOpen}
        width={760}
        okText="创建草稿"
        confirmLoading={saving}
        onOk={() => void createPolicy()}
        onCancel={() => setPolicyModalOpen(false)}
        forceRender
      >
        <Alert
          type="info"
          showIcon
          title="政策需由不同管理员审批后才会生效；自动冻结默认关闭。"
          style={{ marginBottom: 16 }}
        />
        <Form form={policyForm} layout="vertical">
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item
                name="watch_score"
                label="观察阈值"
                rules={[{ required: true }]}
              >
                <InputNumber min={0} max={99} precision={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="hold_score"
                label="暂停阈值"
                rules={[{ required: true }]}
              >
                <InputNumber min={1} max={100} precision={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="freeze_score"
                label="冻结阈值"
                rules={[{ required: true }]}
              >
                <InputNumber min={1} max={100} precision={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="max_utilization_percent"
                label="最大额度利用率"
                rules={[{ required: true }]}
              >
                <InputNumber min={0} precision={2} suffix="%" style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="max_overdue_days"
                label="最大逾期天数"
                rules={[{ required: true }]}
              >
                <InputNumber min={0} precision={0} suffix="天" style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="insurance_required_above"
                label="保险提示敞口阈值"
                rules={[{ required: true }]}
              >
                <InputNumber min={0} precision={2} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item
                name="auto_hold_enabled"
                label="自动暂停"
                valuePropName="checked"
              >
                <Switch checkedChildren="开" unCheckedChildren="关" />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item
                name="auto_freeze_enabled"
                label="自动冻结"
                valuePropName="checked"
              >
                <Switch checkedChildren="开" unCheckedChildren="关" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="notes" label="政策说明">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={
          editingInsurance
            ? `编辑保单 ${editingInsurance.policy_number}`
            : '新建信用保险保单'
        }
        open={insuranceModalOpen}
        width={720}
        okText="保存保单"
        confirmLoading={saving}
        onOk={() => void saveInsurance()}
        onCancel={() => setInsuranceModalOpen(false)}
        forceRender
      >
        <Form form={insuranceForm} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="agent_id"
                label="被保险人 / 客户"
                rules={[{ required: true, message: '请选择客户' }]}
              >
                <Select
                  showSearch
                  optionFilterProp="label"
                  disabled={Boolean(editingInsurance)}
                  options={agentOptions}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="policy_number"
                label="保单号"
                rules={[{ required: true, message: '请输入保单号' }]}
              >
                <Input
                  disabled={Boolean(editingInsurance)}
                  placeholder="INS-2026-001"
                />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="provider"
                label="承保机构"
                rules={[{ required: true, message: '请输入承保机构' }]}
              >
                <Input placeholder="信用保险公司名称" />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="currency" label="币种" rules={[{ required: true }]}>
                <Select
                  disabled={Boolean(editingInsurance)}
                  options={currencyOptions}
                />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="status" label="状态" rules={[{ required: true }]}>
                <Select
                  options={[
                    { value: 'draft', label: '草稿' },
                    { value: 'active', label: '生效' },
                    { value: 'expired', label: '已过期' },
                    { value: 'cancelled', label: '已取消' },
                  ]}
                />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="coverage_limit"
                label="覆盖上限"
                rules={[{ required: true, message: '请输入覆盖上限' }]}
              >
                <InputNumber min={0.01} precision={2} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="coverage_percent"
                label="覆盖比例"
                rules={[{ required: true, message: '请输入覆盖比例' }]}
              >
                <InputNumber
                  min={0.01}
                  max={100}
                  precision={2}
                  suffix="%"
                  style={{ width: '100%' }}
                />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="effective_from"
                label="生效日期"
                rules={[{ required: true }]}
              >
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="effective_to"
                label="结束日期"
                rules={[{ required: true }]}
              >
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="notes" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="新建保险索赔"
        open={claimModalOpen}
        width={680}
        okText="创建草稿"
        confirmLoading={saving}
        onOk={() => void createClaim()}
        onCancel={() => setClaimModalOpen(false)}
        forceRender
      >
        <Alert
          type="info"
          showIcon
          title="索赔批准和结算只登记审计结果，不会自动核销发票；实际赔款仍走收款流程。"
          style={{ marginBottom: 16 }}
        />
        <Form form={claimForm} layout="vertical">
          <Form.Item
            name="policy_id"
            label="信用保险保单"
            rules={[{ required: true, message: '请选择保单' }]}
          >
            <Select
              showSearch
              optionFilterProp="label"
              options={activeInsurance.map((policy) => ({
                value: policy.id,
                label: `${policy.policy_number} · ${policy.agent_company} · ${formatMoney(policy.coverage_limit, policy.currency)}`,
              }))}
            />
          </Form.Item>
          <Form.Item noStyle shouldUpdate>
            {({ getFieldValue }) => {
              const selectedPolicy = insurancePolicies.find(
                (policy) => policy.id === getFieldValue('policy_id'),
              )
              const invoiceOptions = invoices
                .filter(
                  (invoice) =>
                    selectedPolicy &&
                    invoice.agent_id === selectedPolicy.agent_id &&
                    invoice.currency === selectedPolicy.currency &&
                    Number(invoice.balance_due) > 0,
                )
                .map((invoice) => ({
                  value: invoice.id,
                  label: `${invoice.invoice_number} · 待收 ${formatMoney(invoice.balance_due, invoice.currency)} · 到期 ${invoice.due_date}`,
                }))
              return (
                <Form.Item
                  name="invoice_id"
                  label="关联发票"
                  rules={[{ required: true, message: '请选择发票' }]}
                >
                  <Select
                    showSearch
                    optionFilterProp="label"
                    disabled={!selectedPolicy}
                    options={invoiceOptions}
                    notFoundContent={
                      selectedPolicy ? '该客户没有同币种未结发票' : '请先选择保单'
                    }
                  />
                </Form.Item>
              )
            }}
          </Form.Item>
          <Form.Item
            name="claimed_amount"
            label="申请索赔金额"
            rules={[{ required: true, message: '请输入申请金额' }]}
          >
            <InputNumber min={0.01} precision={2} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="reason"
            label="索赔原因"
            rules={[{ required: true, message: '请输入索赔原因' }]}
          >
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={
          decisionPolicy
            ? `驳回政策 v${decisionPolicy.version_number}`
            : statusDecision === 'normal'
              ? '解除信用限制'
              : statusDecision === 'frozen'
                ? '冻结客户'
                : '暂停客户接单'
        }
        open={Boolean(decisionPolicy || statusDecision)}
        zIndex={1300}
        okText={
          decisionPolicy
            ? '确认驳回'
            : statusDecision === 'normal'
              ? '确认解除'
              : statusDecision === 'frozen'
                ? '确认冻结'
                : '确认暂停'
        }
        okButtonProps={{
          danger: Boolean(decisionPolicy || statusDecision !== 'normal'),
        }}
        confirmLoading={saving}
        onOk={() => void (decisionPolicy ? rejectPolicy() : submitStatusDecision())}
        onCancel={() => {
          setDecisionPolicy(null)
          setStatusDecision(null)
        }}
        forceRender
      >
        <Alert
          type={statusDecision === 'normal' ? 'warning' : 'info'}
          showIcon
          title={
            decisionPolicy
              ? '驳回原因会进入政策审批审计。'
              : statusDecision === 'normal'
                ? '解除后客户可继续创建赊销订单。'
                : '该动作会立即阻断客户新增订单。'
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
        title={claimDecision === 'settle' ? '登记保险赔款结算' : '驳回保险索赔'}
        open={Boolean(claimDecision)}
        okText={claimDecision === 'settle' ? '登记结算' : '确认驳回'}
        okButtonProps={{ danger: claimDecision === 'reject' }}
        confirmLoading={saving}
        onOk={() => void submitClaimDecision()}
        onCancel={() => {
          setClaimDecision(null)
          setDecisionClaim(null)
        }}
        forceRender
      >
        <Form form={decisionForm} layout="vertical">
          {claimDecision === 'settle' ? (
            <>
              <Form.Item
                name="recovered_amount"
                label="确认回收金额"
                rules={[{ required: true, message: '请输入回收金额' }]}
              >
                <InputNumber min={0.01} precision={2} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item
                name="settlement_reference"
                label="结算凭证号"
                rules={[{ required: true, message: '请输入结算凭证号' }]}
              >
                <Input placeholder="INS-PAY-2026-001" />
              </Form.Item>
            </>
          ) : (
            <Form.Item
              name="reason"
              label="驳回原因"
              rules={[{ required: true, message: '请输入驳回原因' }]}
            >
              <Input.TextArea rows={3} />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </div>
  )
}
