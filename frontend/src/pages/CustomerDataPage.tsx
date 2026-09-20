import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Col,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Input,
  Modal,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  LinkOutlined,
  MergeCellsOutlined,
  PlusOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { api, ApiError } from '../api/client'
import { useAuth } from '../auth/AuthProvider'

const { Title, Text } = Typography

interface ListResponse<T> {
  items: T[]
  total: number
}

interface CustomerAccount {
  id: string
  customer_number: string
  customer_type: string
  business_model: string
  display_name: string | null
  status: string
  country: string | null
  default_currency: string
  merged_into_account_id: string | null
  merged_at: string | null
  created_at: string
  updated_at: string
}

interface IdentityLink {
  id: string
  customer_account_id: string
  channel: string
  external_system: string
  identity_type: string
  fingerprint: string
  hash_key_version: string
  verification_status: string
  source: string
  verified_at: string | null
  last_seen_at: string | null
  disabled_at: string | null
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

interface AccountMerge {
  id: string
  source_account_id: string
  target_account_id: string
  status: string
  match_type: string
  match_hash_prefix: string
  evidence: Record<string, unknown>
  reason: string
  requested_by: string
  reviewed_by: string | null
  reviewed_at: string | null
  rejection_reason: string | null
  completed_by: string | null
  completed_at: string | null
  result_summary: Record<string, unknown>
  created_at: string
  updated_at: string
}

interface ConsentSummaryItem {
  purpose: string
  channel: string
  status: string
  policy_version: string
  source: string
  occurred_at: string
  recorded_by: string
  event_id: string
}

interface ConsentEvent {
  id: string
  customer_account_id: string
  purpose: string
  channel: string
  status: string
  policy_version: string
  source: string
  occurred_at: string
  recorded_by: string
  evidence: Record<string, unknown>
  created_at: string
}

interface DataSubjectRequest {
  id: string
  request_number: string
  customer_account_id: string | null
  request_type: string
  status: string
  identity_hash_prefix: string | null
  verification_method: string | null
  verified_by: string | null
  verified_at: string | null
  due_at: string
  handled_by: string | null
  decided_at: string | null
  completed_at: string | null
  rejection_reason: string | null
  request_details: string | null
  result_summary: Record<string, unknown>
  evidence: Record<string, unknown>
  requested_by: string
  created_at: string
  updated_at: string
}

interface DataSubjectRequestDetail extends DataSubjectRequest {
  actions: Array<{
    id: string
    action_type: string
    actor: string
    note: string | null
    result: Record<string, unknown>
    created_at: string
  }>
}

interface CustomerDataStats {
  accounts: number
  conflicts: number
  pending_merges: number
  requests: Record<string, number>
}

const identityTypeOptions = [
  { value: 'email', label: '邮箱' },
  { value: 'phone', label: '电话' },
  { value: 'woocommerce_customer_id', label: 'WooCommerce 客户 ID' },
  { value: 'company_tax_id', label: '企业税号' },
  { value: 'other', label: '其他' },
]

const channelOptions = [
  { value: 'b2c_store', label: 'B2C 店铺' },
  { value: 'b2b_portal', label: 'B2B 门户' },
  { value: 'email', label: '邮件' },
  { value: 'support', label: '客服' },
  { value: 'crm', label: 'CRM' },
  { value: 'other', label: '其他' },
]

const consentPurposeOptions = [
  { value: 'marketing_email', label: '营销邮件' },
  { value: 'transactional_email', label: '交易邮件' },
  { value: 'analytics', label: '分析' },
  { value: 'personalization', label: '个性化' },
  { value: 'ai_processing', label: 'AI 处理' },
]

const requestTypeOptions = [
  { value: 'access', label: '访问' },
  { value: 'export', label: '导出' },
  { value: 'delete', label: '删除' },
  { value: 'correct', label: '更正' },
  { value: 'restrict', label: '限制处理' },
]

const identityStatus: Record<string, { color: string; label: string }> = {
  pending: { color: 'default', label: '待验证' },
  verified: { color: 'green', label: '已验证' },
  conflict: { color: 'volcano', label: '冲突' },
  rejected: { color: 'red', label: '已拒绝' },
  revoked: { color: 'default', label: '已撤销' },
  merged: { color: 'blue', label: '已合并' },
}

const mergeStatus: Record<string, { color: string; label: string }> = {
  pending: { color: 'orange', label: '待审批' },
  approved: { color: 'blue', label: '已批准' },
  rejected: { color: 'red', label: '已驳回' },
  completed: { color: 'green', label: '已完成' },
  cancelled: { color: 'default', label: '已取消' },
}

const requestStatus: Record<string, { color: string; label: string }> = {
  received: { color: 'orange', label: '已受理' },
  verifying: { color: 'blue', label: '待审批' },
  approved: { color: 'cyan', label: '待执行' },
  processing: { color: 'processing', label: '处理中' },
  completed: { color: 'green', label: '已完成' },
  rejected: { color: 'red', label: '已驳回' },
  cancelled: { color: 'default', label: '已取消' },
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  return error instanceof Error ? error.message : '操作失败'
}

function formatTime(value: string | null | undefined): string {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '-'
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

export default function CustomerDataPage() {
  const { user } = useAuth()
  const { message } = AntApp.useApp()
  const canEdit = user?.role === 'admin' || user?.role === 'operator'
  const canAdmin = user?.role === 'admin'

  const [activeTab, setActiveTab] = useState('identities')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [stats, setStats] = useState<CustomerDataStats | null>(null)
  const [accounts, setAccounts] = useState<CustomerAccount[]>([])
  const [identityStatusFilter, setIdentityStatusFilter] = useState<string>()
  const [identities, setIdentities] = useState<IdentityLink[]>([])
  const [merges, setMerges] = useState<AccountMerge[]>([])
  const [requests, setRequests] = useState<DataSubjectRequest[]>([])

  const [identityModalOpen, setIdentityModalOpen] = useState(false)
  const [identityMode, setIdentityMode] = useState<'resolve' | 'link'>('resolve')
  const [mergeModalOpen, setMergeModalOpen] = useState(false)
  const [mergeRejectTarget, setMergeRejectTarget] =
    useState<AccountMerge | null>(null)
  const [consentAccountId, setConsentAccountId] = useState<string>()
  const [consentSummary, setConsentSummary] = useState<ConsentSummaryItem[]>([])
  const [consentHistory, setConsentHistory] = useState<ConsentEvent[]>([])
  const [consentModalOpen, setConsentModalOpen] = useState(false)
  const [requestModalOpen, setRequestModalOpen] = useState(false)
  const [selectedRequest, setSelectedRequest] =
    useState<DataSubjectRequestDetail | null>(null)
  const [decisionAction, setDecisionAction] = useState<
    'approve' | 'reject' | 'cancel' | 'execute' | null
  >(null)
  const [decisionRequest, setDecisionRequest] =
    useState<DataSubjectRequest | null>(null)
  const [verificationRequest, setVerificationRequest] =
    useState<DataSubjectRequest | null>(null)

  const [identityForm] = Form.useForm()
  const [mergeForm] = Form.useForm()
  const [mergeDecisionForm] = Form.useForm()
  const [consentForm] = Form.useForm()
  const [requestForm] = Form.useForm()
  const [decisionForm] = Form.useForm()
  const [verificationForm] = Form.useForm()

  const accountLabel = useCallback(
    (accountId: string | null) => {
      if (!accountId) return '-'
      const account = accounts.find((item) => item.id === accountId)
      return account
        ? `${account.customer_number} · ${account.display_name || account.customer_type}`
        : accountId.slice(0, 8)
    },
    [accounts],
  )

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [
        statsResponse,
        accountResponse,
        identityResponse,
        mergeResponse,
        requestResponse,
      ] = await Promise.all([
        api.getCustomerDataStats() as Promise<CustomerDataStats>,
        api.getCustomerAccounts({ limit: 1000 }) as Promise<CustomerAccount[]>,
        api.getCustomerIdentities({
          status: identityStatusFilter,
          limit: 2000,
        }) as Promise<ListResponse<IdentityLink>>,
        api.getCustomerMerges() as Promise<ListResponse<AccountMerge>>,
        api.getDataSubjectRequests({ limit: 1000 }) as Promise<
          ListResponse<DataSubjectRequest>
        >,
      ])
      setStats(statsResponse)
      setAccounts(accountResponse)
      setIdentities(identityResponse.items || [])
      setMerges(mergeResponse.items || [])
      setRequests(requestResponse.items || [])
      setConsentAccountId((current) => current || accountResponse[0]?.id)
    } catch (loadError) {
      setError(errorMessage(loadError))
    } finally {
      setLoading(false)
    }
  }, [identityStatusFilter])

  const loadConsent = useCallback(async (accountId: string) => {
    const [summary, history] = await Promise.all([
      api.getCustomerConsentSummary(accountId) as Promise<{
        customer_account_id: string
        items: ConsentSummaryItem[]
      }>,
      api.getCustomerConsentHistory(accountId) as Promise<
        ListResponse<ConsentEvent>
      >,
    ])
    setConsentSummary(summary.items || [])
    setConsentHistory(history.items || [])
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (!consentAccountId) {
      setConsentSummary([])
      setConsentHistory([])
      return
    }
    void loadConsent(consentAccountId).catch((loadError) => {
      message.error(errorMessage(loadError))
    })
  }, [consentAccountId, loadConsent, message])

  const runAction = async (action: () => Promise<unknown>, success: string) => {
    setSaving(true)
    try {
      await action()
      message.success(success)
      await load()
      if (consentAccountId) await loadConsent(consentAccountId)
    } catch (actionError) {
      message.error(errorMessage(actionError))
    } finally {
      setSaving(false)
    }
  }

  const openIdentityModal = (mode: 'resolve' | 'link') => {
    setIdentityMode(mode)
    identityForm.resetFields()
    identityForm.setFieldsValue({
      identity_type: 'email',
      channel: 'email',
      external_system: 'manual',
      source: 'admin_ui',
      customer_type: 'CONSUMER',
      business_model: 'B2C',
      create_if_missing: false,
    })
    setIdentityModalOpen(true)
  }

  const saveIdentity = async () => {
    try {
      const values = await identityForm.validateFields()
      setSaving(true)
      if (identityMode === 'resolve') {
        const result = (await api.resolveCustomerIdentity({
          identity_type: values.identity_type,
          identity_value: values.identity_value,
          channel: values.channel,
          external_system: values.external_system,
          create_if_missing: values.create_if_missing,
          customer_type: values.customer_type,
          business_model: values.business_model,
        })) as { resolved: boolean }
        message.success(
          result.resolved ? '身份已解析到统一客户账户' : '未找到已有账户',
        )
      } else {
        await api.linkCustomerIdentity({
          customer_account_id: values.customer_account_id,
          identity_type: values.identity_type,
          identity_value: values.identity_value,
          channel: values.channel,
          external_system: values.external_system,
          source: values.source,
          metadata: {},
        })
        message.success('身份链接已登记')
      }
      setIdentityModalOpen(false)
      await load()
    } catch (saveError) {
      if (saveError instanceof Error && 'errorFields' in saveError) return
      message.error(errorMessage(saveError))
    } finally {
      setSaving(false)
    }
  }

  const createMerge = async () => {
    try {
      const values = await mergeForm.validateFields()
      setSaving(true)
      await api.createCustomerMerge(values)
      message.success('合并申请已创建，等待管理员审批')
      setMergeModalOpen(false)
      await load()
    } catch (saveError) {
      if (saveError instanceof Error && 'errorFields' in saveError) return
      message.error(errorMessage(saveError))
    } finally {
      setSaving(false)
    }
  }

  const rejectMerge = async () => {
    if (!mergeRejectTarget) return
    try {
      const values = await mergeDecisionForm.validateFields()
      setSaving(true)
      await api.rejectCustomerMerge(mergeRejectTarget.id, values.reason)
      message.success('合并申请已驳回')
      setMergeRejectTarget(null)
      await load()
    } catch (saveError) {
      if (saveError instanceof Error && 'errorFields' in saveError) return
      message.error(errorMessage(saveError))
    } finally {
      setSaving(false)
    }
  }

  const openConsentModal = (status: 'granted' | 'withdrawn') => {
    if (!consentAccountId) {
      message.warning('请先选择客户账户')
      return
    }
    consentForm.resetFields()
    consentForm.setFieldsValue({
      purpose: 'marketing_email',
      channel: 'email',
      status,
      policy_version: 'privacy-console-v1',
      source: 'admin_ui',
      idempotency_key: `ui-${Date.now()}-${status}`,
    })
    setConsentModalOpen(true)
  }

  const appendConsent = async () => {
    try {
      const values = await consentForm.validateFields()
      setSaving(true)
      await api.appendCustomerConsent({
        customer_account_id: consentAccountId,
        purpose: values.purpose,
        channel: values.channel,
        status: values.status,
        policy_version: values.policy_version,
        source: values.source,
        idempotency_key: values.idempotency_key,
        evidence: {},
      })
      message.success(
        values.status === 'withdrawn' ? '同意已撤回并立即生效' : '同意事件已登记',
      )
      setConsentModalOpen(false)
      if (consentAccountId) await loadConsent(consentAccountId)
    } catch (saveError) {
      if (saveError instanceof Error && 'errorFields' in saveError) return
      message.error(errorMessage(saveError))
    } finally {
      setSaving(false)
    }
  }

  const createRequest = async () => {
    try {
      const values = await requestForm.validateFields()
      setSaving(true)
      await api.createDataSubjectRequest({
        request_type: values.request_type,
        customer_account_id: values.customer_account_id,
        request_details: values.request_details || null,
        verification_method: null,
        evidence: {},
      })
      message.success('数据主体请求已登记')
      setRequestModalOpen(false)
      await load()
    } catch (saveError) {
      if (saveError instanceof Error && 'errorFields' in saveError) return
      message.error(errorMessage(saveError))
    } finally {
      setSaving(false)
    }
  }

  const openRequestDetail = async (request: DataSubjectRequest) => {
    try {
      const detail = (await api.getDataSubjectRequest(
        request.id,
      )) as DataSubjectRequestDetail
      setSelectedRequest(detail)
    } catch (detailError) {
      message.error(errorMessage(detailError))
    }
  }

  const openDecision = (
    action: 'approve' | 'reject' | 'cancel' | 'execute',
    request: DataSubjectRequest,
  ) => {
    decisionForm.resetFields()
    setDecisionAction(action)
    setDecisionRequest(request)
  }

  const submitDecision = async () => {
    if (!decisionAction || !decisionRequest) return
    try {
      const values = await decisionForm.validateFields()
      setSaving(true)
      if (decisionAction === 'approve') {
        await api.approveDataSubjectRequest(
          decisionRequest.id,
          values.note || null,
        )
        message.success('请求已批准，等待执行')
      } else if (decisionAction === 'reject') {
        await api.rejectDataSubjectRequest(decisionRequest.id, values.reason)
        message.success('请求已驳回')
      } else if (decisionAction === 'cancel') {
        await api.cancelDataSubjectRequest(
          decisionRequest.id,
          values.note || null,
        )
        message.success('请求已取消')
      } else {
        await api.executeDataSubjectRequest(
          decisionRequest.id,
          values.note || null,
        )
        message.success('请求已执行并写入审计')
      }
      setDecisionAction(null)
      setDecisionRequest(null)
      setSelectedRequest(null)
      await load()
    } catch (saveError) {
      if (saveError instanceof Error && 'errorFields' in saveError) return
      message.error(errorMessage(saveError))
    } finally {
      setSaving(false)
    }
  }

  const verifyRequest = async () => {
    if (!verificationRequest) return
    try {
      const values = await verificationForm.validateFields()
      setSaving(true)
      await api.verifyDataSubjectRequest(verificationRequest.id, {
        verification_method: values.verification_method,
        note: values.note || null,
      })
      message.success('身份核验已登记')
      setVerificationRequest(null)
      await load()
    } catch (saveError) {
      if (saveError instanceof Error && 'errorFields' in saveError) return
      message.error(errorMessage(saveError))
    } finally {
      setSaving(false)
    }
  }

  const accountOptions = useMemo(
    () =>
      accounts.map((account) => ({
        value: account.id,
        label: `${account.customer_number} · ${
          account.display_name || account.customer_type
        } · ${account.business_model}`,
      })),
    [accounts],
  )

  const identityColumns: ColumnsType<IdentityLink> = [
    {
      title: '客户账户',
      width: 220,
      render: (_, row) => accountLabel(row.customer_account_id),
    },
    {
      title: '状态',
      width: 100,
      render: (_, row) => (
        <StatusTag value={row.verification_status} labels={identityStatus} />
      ),
    },
    { title: '身份类型', dataIndex: 'identity_type', width: 150 },
    {
      title: '渠道',
      width: 150,
      render: (_, row) => `${row.channel} / ${row.external_system}`,
    },
    {
      title: '审计指纹',
      width: 190,
      render: (_, row) => <Text code>{row.fingerprint}</Text>,
    },
    {
      title: '最近观测',
      dataIndex: 'last_seen_at',
      width: 160,
      render: formatTime,
    },
    {
      title: '冲突信息',
      ellipsis: true,
      render: (_, row) =>
        row.metadata.conflict_customer_account_id
          ? accountLabel(String(row.metadata.conflict_customer_account_id))
          : '-',
    },
  ]

  const mergeColumns: ColumnsType<AccountMerge> = [
    {
      title: '来源账户',
      width: 220,
      render: (_, row) => accountLabel(row.source_account_id),
    },
    {
      title: '目标账户',
      width: 220,
      render: (_, row) => accountLabel(row.target_account_id),
    },
    {
      title: '匹配依据',
      width: 150,
      render: (_, row) => `${row.match_type} / ${row.match_hash_prefix}`,
    },
    {
      title: '状态',
      width: 100,
      render: (_, row) => (
        <StatusTag value={row.status} labels={mergeStatus} />
      ),
    },
    { title: '申请人', dataIndex: 'requested_by', width: 180 },
    {
      title: '申请原因',
      dataIndex: 'reason',
      ellipsis: true,
    },
    {
      title: '操作',
      width: 230,
      fixed: 'right',
      render: (_, row) => (
        <Space wrap>
          {canAdmin && row.status === 'pending' && (
            <>
              <Button
                size="small"
                type="primary"
                onClick={() =>
                  void runAction(
                    () => api.approveCustomerMerge(row.id),
                    '合并申请已批准',
                  )
                }
              >
                批准
              </Button>
              <Button
                size="small"
                danger
                onClick={() => {
                  mergeDecisionForm.resetFields()
                  setMergeRejectTarget(row)
                }}
              >
                驳回
              </Button>
            </>
          )}
          {canAdmin && row.status === 'approved' && (
            <Button
              size="small"
              type="primary"
              onClick={() =>
                void runAction(
                  () => api.completeCustomerMerge(row.id),
                  '账户合并已完成',
                )
              }
            >
              执行合并
            </Button>
          )}
        </Space>
      ),
    },
  ]

  const requestColumns: ColumnsType<DataSubjectRequest> = [
    {
      title: '请求编号',
      width: 190,
      render: (_, row) => <Text strong>{row.request_number}</Text>,
    },
    {
      title: '类型',
      width: 100,
      render: (_, row) =>
        requestTypeOptions.find((item) => item.value === row.request_type)
          ?.label || row.request_type,
    },
    {
      title: '客户账户',
      width: 220,
      render: (_, row) => accountLabel(row.customer_account_id),
    },
    {
      title: '状态',
      width: 100,
      render: (_, row) => (
        <StatusTag value={row.status} labels={requestStatus} />
      ),
    },
    {
      title: '截止时间',
      dataIndex: 'due_at',
      width: 160,
      render: formatTime,
    },
    { title: '申请人', dataIndex: 'requested_by', width: 180 },
    {
      title: '操作',
      width: 290,
      fixed: 'right',
      render: (_, row) => (
        <Space wrap>
          <Button size="small" onClick={() => void openRequestDetail(row)}>
            查看
          </Button>
          {canAdmin && row.status === 'received' && (
            <Button
              size="small"
              type="primary"
              onClick={() => {
                verificationForm.resetFields()
                setVerificationRequest(row)
              }}
            >
              核验
            </Button>
          )}
          {canAdmin && row.status === 'verifying' && (
            <>
              <Button
                size="small"
                type="primary"
                onClick={() => openDecision('approve', row)}
              >
                批准
              </Button>
              <Button
                size="small"
                danger
                onClick={() => openDecision('reject', row)}
              >
                驳回
              </Button>
            </>
          )}
          {canAdmin && row.status === 'approved' && (
            <>
              <Button
                size="small"
                type="primary"
                onClick={() => openDecision('execute', row)}
              >
                执行
              </Button>
              <Button
                size="small"
                danger
                onClick={() => openDecision('reject', row)}
              >
                驳回
              </Button>
            </>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div className="customer-data-page">
      <Space orientation="vertical" size={16} style={{ width: '100%' }}>
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>
            客户身份与隐私
          </Title>
          <Text type="secondary">
            统一 B2C/B2B 客户身份，管理同意账本、合并审批与数据主体请求。
          </Text>
        </div>

        {error && (
          <Alert
            type="error"
            showIcon
            title="客户数据加载失败"
            description={error}
            action={
              <Button icon={<ReloadOutlined />} onClick={() => void load()}>
                重试
              </Button>
            }
          />
        )}

        <Row gutter={[12, 12]}>
          <Col xs={12} md={6}>
            <Card size="small">
              <Statistic title="统一客户账户" value={stats?.accounts || 0} />
            </Card>
          </Col>
          <Col xs={12} md={6}>
            <Card size="small">
              <Statistic
                title="身份冲突"
                value={stats?.conflicts || 0}
              />
            </Card>
          </Col>
          <Col xs={12} md={6}>
            <Card size="small">
              <Statistic
                title="待审批合并"
                value={stats?.pending_merges || 0}
              />
            </Card>
          </Col>
          <Col xs={12} md={6}>
            <Card size="small">
              <Statistic
                title="未完成隐私请求"
                value={
                  (stats?.requests.received || 0) +
                  (stats?.requests.verifying || 0) +
                  (stats?.requests.approved || 0) +
                  (stats?.requests.processing || 0)
                }
              />
            </Card>
          </Col>
        </Row>

        <Card>
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            tabBarExtraContent={
              <Button
                icon={<ReloadOutlined />}
                loading={loading}
                onClick={() => void load()}
              >
                刷新
              </Button>
            }
            items={[
              {
                key: 'identities',
                label: '身份链接与冲突',
                children: (
                  <Space orientation="vertical" size={12} style={{ width: '100%' }}>
                    <Space wrap>
                      <Select
                        allowClear
                        placeholder="全部状态"
                        style={{ width: 160 }}
                        value={identityStatusFilter}
                        onChange={setIdentityStatusFilter}
                        options={Object.entries(identityStatus).map(
                          ([value, item]) => ({
                            value,
                            label: item.label,
                          }),
                        )}
                      />
                      {canEdit && (
                        <>
                          <Button
                            icon={<LinkOutlined />}
                            onClick={() => openIdentityModal('link')}
                          >
                            登记身份
                          </Button>
                          <Button
                            type="primary"
                            icon={<SafetyCertificateOutlined />}
                            onClick={() => openIdentityModal('resolve')}
                          >
                            解析身份
                          </Button>
                        </>
                      )}
                    </Space>
                    <Table
                      rowKey="id"
                      size="small"
                      loading={loading}
                      dataSource={identities}
                      pagination={{ pageSize: 20, showSizeChanger: false }}
                      scroll={{ x: 1180 }}
                      locale={{ emptyText: emptyText('还没有身份链接') }}
                      columns={identityColumns}
                    />
                  </Space>
                ),
              },
              {
                key: 'merges',
                label: '合并审批',
                children: (
                  <Space orientation="vertical" size={12} style={{ width: '100%' }}>
                    {canEdit && (
                      <Button
                        type="primary"
                        icon={<MergeCellsOutlined />}
                        onClick={() => {
                          mergeForm.resetFields()
                          setMergeModalOpen(true)
                        }}
                      >
                        新建合并申请
                      </Button>
                    )}
                    <Alert
                      type="info"
                      showIcon
                      title="合并必须基于两个账户共同拥有的确定性身份，且只能由管理员批准和执行。"
                    />
                    <Table
                      rowKey="id"
                      size="small"
                      loading={loading}
                      dataSource={merges}
                      pagination={{ pageSize: 20, showSizeChanger: false }}
                      scroll={{ x: 1320 }}
                      locale={{ emptyText: emptyText('还没有合并申请') }}
                      columns={mergeColumns}
                    />
                  </Space>
                ),
              },
              {
                key: 'consent',
                label: '同意账本',
                children: (
                  <Space orientation="vertical" size={12} style={{ width: '100%' }}>
                    <Space wrap>
                      <Select
                        aria-label="同意账本客户账户"
                        showSearch
                        optionFilterProp="label"
                        style={{ width: 360, maxWidth: '100%' }}
                        placeholder="选择客户账户"
                        value={consentAccountId}
                        onChange={setConsentAccountId}
                        options={accountOptions}
                      />
                      {canEdit && (
                        <>
                          <Button
                            icon={<CheckCircleOutlined />}
                            onClick={() => openConsentModal('granted')}
                          >
                            登记授权
                          </Button>
                          <Button
                            danger
                            icon={<CloseCircleOutlined />}
                            onClick={() => openConsentModal('withdrawn')}
                          >
                            撤回同意
                          </Button>
                        </>
                      )}
                    </Space>
                    <Row gutter={[12, 12]}>
                      <Col xs={24} xl={10}>
                        <Card size="small" title="当前有效同意">
                          <Table
                            rowKey={(row) => `${row.purpose}-${row.channel}`}
                            size="small"
                            pagination={false}
                            dataSource={consentSummary}
                            locale={{ emptyText: emptyText('没有同意的兼容记录') }}
                            columns={[
                              { title: '用途', dataIndex: 'purpose' },
                              { title: '渠道', dataIndex: 'channel' },
                              {
                                title: '状态',
                                width: 90,
                                render: (_, row) => (
                                  <Tag
                                    color={
                                      row.status === 'granted'
                                        ? 'green'
                                        : 'red'
                                    }
                                  >
                                    {row.status === 'granted'
                                      ? '已授权'
                                      : '已撤回'}
                                  </Tag>
                                ),
                              },
                            ]}
                          />
                        </Card>
                      </Col>
                      <Col xs={24} xl={14}>
                        <Card size="small" title="追加式同意历史">
                          <Table
                            rowKey="id"
                            size="small"
                            pagination={{ pageSize: 10, showSizeChanger: false }}
                            dataSource={consentHistory}
                            scroll={{ x: 800 }}
                            locale={{ emptyText: emptyText('还没有同意事件') }}
                            columns={[
                              { title: '用途', dataIndex: 'purpose' },
                              { title: '渠道', dataIndex: 'channel' },
                              {
                                title: '状态',
                                width: 90,
                                render: (_, row) => (
                                  <Tag
                                    color={
                                      row.status === 'granted'
                                        ? 'green'
                                        : 'red'
                                    }
                                  >
                                    {row.status === 'granted'
                                      ? '已授权'
                                      : '已撤回'}
                                  </Tag>
                                ),
                              },
                              { title: '策略版本', dataIndex: 'policy_version' },
                              { title: '来源', dataIndex: 'source' },
                              {
                                title: '时间',
                                dataIndex: 'occurred_at',
                                width: 160,
                                render: formatTime,
                              },
                            ]}
                          />
                        </Card>
                      </Col>
                    </Row>
                  </Space>
                ),
              },
              {
                key: 'requests',
                label: '数据主体请求',
                children: (
                  <Space orientation="vertical" size={12} style={{ width: '100%' }}>
                    {canEdit && (
                      <Button
                        type="primary"
                        icon={<PlusOutlined />}
                        onClick={() => {
                          requestForm.resetFields()
                          requestForm.setFieldsValue({
                            request_type: 'access',
                            customer_account_id: consentAccountId,
                          })
                          setRequestModalOpen(true)
                        }}
                      >
                        登记请求
                      </Button>
                    )}
                    <Alert
                      type="warning"
                      showIcon
                      title="删除请求只匿名化直接身份和行为数据，订单、发票、合同与账务事实依法保留。"
                    />
                    <Table
                      rowKey="id"
                      size="small"
                      loading={loading}
                      dataSource={requests}
                      pagination={{ pageSize: 20, showSizeChanger: false }}
                      scroll={{ x: 1320 }}
                      locale={{ emptyText: emptyText('还没有数据主体请求') }}
                      columns={requestColumns}
                    />
                  </Space>
                ),
              },
            ]}
          />
        </Card>
      </Space>

      <Modal
        title={identityMode === 'resolve' ? '解析客户身份' : '登记客户身份'}
        open={identityModalOpen}
        width={640}
        confirmLoading={saving}
        okText={identityMode === 'resolve' ? '解析' : '登记'}
        onOk={() => void saveIdentity()}
        onCancel={() => setIdentityModalOpen(false)}
        forceRender
      >
        <Alert
          type="info"
          showIcon
          title="原始邮箱、电话、税号或外部 ID 只用于当前请求计算 HMAC，不会落入身份链接表。"
          style={{ marginBottom: 16 }}
        />
        <Form form={identityForm} layout="vertical">
          {identityMode === 'link' && (
            <Form.Item
              name="customer_account_id"
              label="客户账户"
              rules={[{ required: true, message: '请选择客户账户' }]}
            >
              <Select
                showSearch
                optionFilterProp="label"
                options={accountOptions}
              />
            </Form.Item>
          )}
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item
                name="identity_type"
                label="身份类型"
                rules={[{ required: true }]}
              >
                <Select options={identityTypeOptions} />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item
                name="identity_value"
                label="身份值"
                rules={[{ required: true, message: '请输入身份值' }]}
              >
                <Input autoComplete="off" placeholder="仅用于内存计算指纹" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item name="channel" label="渠道" rules={[{ required: true }]}>
                <Select options={channelOptions} />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item
                name="external_system"
                label="外部系统"
                rules={[{ required: true }]}
              >
                <Input />
              </Form.Item>
            </Col>
          </Row>
          {identityMode === 'resolve' && (
            <>
              <Row gutter={16}>
                <Col xs={24} md={12}>
                  <Form.Item name="customer_type" label="缺失时客户类型">
                    <Select
                      options={[
                        { value: 'CONSUMER', label: '消费者' },
                        { value: 'RETAILER', label: '零售商' },
                        { value: 'WHOLESALER', label: '批发商' },
                        { value: 'DISTRIBUTOR', label: '分销商' },
                        { value: 'AGENT', label: '代理商' },
                      ]}
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item name="business_model" label="缺失时业务模式">
                    <Select
                      options={[
                        { value: 'B2C', label: 'B2C' },
                        { value: 'B2B', label: 'B2B' },
                        { value: 'BOTH', label: '双业务' },
                      ]}
                    />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item name="create_if_missing" label="缺失时创建账户">
                <Select
                  options={[
                    { value: false, label: '只查询，不创建' },
                    { value: true, label: '创建统一客户账户' },
                  ]}
                />
              </Form.Item>
            </>
          )}
          {identityMode === 'link' && (
            <Form.Item
              name="source"
              label="登记来源"
              rules={[{ required: true }]}
            >
              <Input />
            </Form.Item>
          )}
        </Form>
      </Modal>

      <Modal
        title="新建账户合并申请"
        open={mergeModalOpen}
        width={640}
        confirmLoading={saving}
        okText="提交审批"
        onOk={() => void createMerge()}
        onCancel={() => setMergeModalOpen(false)}
        forceRender
      >
        <Alert
          type="warning"
          showIcon
          title="两侧必须至少有一个相同确定性身份。系统不会自动合并，批准后才能执行。"
          style={{ marginBottom: 16 }}
        />
        <Form form={mergeForm} layout="vertical">
          <Form.Item
            name="source_account_id"
            label="来源账户"
            rules={[{ required: true, message: '请选择来源账户' }]}
          >
            <Select
              showSearch
              optionFilterProp="label"
              options={accountOptions}
            />
          </Form.Item>
          <Form.Item
            name="target_account_id"
            label="目标账户"
            rules={[{ required: true, message: '请选择目标账户' }]}
          >
            <Select
              showSearch
              optionFilterProp="label"
              options={accountOptions}
            />
          </Form.Item>
          <Form.Item
            name="reason"
            label="合并原因"
            rules={[
              { required: true },
              { min: 10, message: '请写明可审计的合并依据' },
            ]}
          >
            <Input.TextArea rows={4} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="登记同意事件"
        open={consentModalOpen}
        confirmLoading={saving}
        okText="写入账本"
        onOk={() => void appendConsent()}
        onCancel={() => setConsentModalOpen(false)}
        forceRender
      >
        <Alert
          type="info"
          showIcon
          title="账本是追加式记录；撤回事件会立即阻断对应营销发送。"
          style={{ marginBottom: 16 }}
        />
        <Form form={consentForm} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="purpose"
                label="用途"
                rules={[{ required: true }]}
              >
                <Select options={consentPurposeOptions} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="channel"
                label="渠道"
                rules={[{ required: true }]}
              >
                <Select options={channelOptions} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="status"
                label="状态"
                rules={[{ required: true }]}
              >
                <Select
                  options={[
                    { value: 'granted', label: '授权' },
                    { value: 'withdrawn', label: '撤回' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="policy_version"
                label="策略版本"
                rules={[{ required: true }]}
              >
                <Input />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="source" label="来源" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item
            name="idempotency_key"
            label="幂等键"
            rules={[{ required: true }, { min: 8 }]}
          >
            <Input />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="驳回账户合并申请"
        open={Boolean(mergeRejectTarget)}
        confirmLoading={saving}
        okText="确认驳回"
        okButtonProps={{ danger: true }}
        onOk={() => void rejectMerge()}
        onCancel={() => setMergeRejectTarget(null)}
        forceRender
      >
        <Alert
          type="warning"
          showIcon
          title="驳回原因会进入不可变审批审计记录。"
          style={{ marginBottom: 16 }}
        />
        <Form form={mergeDecisionForm} layout="vertical">
          <Form.Item
            name="reason"
            label="驳回原因"
            rules={[{ required: true }, { min: 2 }]}
          >
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="登记数据主体请求"
        open={requestModalOpen}
        confirmLoading={saving}
        okText="登记"
        onOk={() => void createRequest()}
        onCancel={() => setRequestModalOpen(false)}
        forceRender
      >
        <Form form={requestForm} layout="vertical">
          <Form.Item
            name="request_type"
            label="请求类型"
            rules={[{ required: true }]}
          >
            <Select options={requestTypeOptions} />
          </Form.Item>
          <Form.Item
            name="customer_account_id"
            label="客户账户"
            rules={[{ required: true, message: '请选择客户账户' }]}
          >
            <Select
              showSearch
              optionFilterProp="label"
              options={accountOptions}
            />
          </Form.Item>
          <Form.Item name="request_details" label="请求说明">
            <Input.TextArea rows={4} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="核验数据主体身份"
        open={Boolean(verificationRequest)}
        confirmLoading={saving}
        okText="确认核验"
        onOk={() => void verifyRequest()}
        onCancel={() => setVerificationRequest(null)}
        forceRender
      >
        <Alert
          type="warning"
          showIcon
          title="核验后仍需管理员独立批准；开发和运营角色不能直接执行删除。"
          style={{ marginBottom: 16 }}
        />
        <Form form={verificationForm} layout="vertical">
          <Form.Item
            name="verification_method"
            label="核验方式"
            rules={[{ required: true, message: '请输入核验方式' }]}
          >
            <Input placeholder="例如：账户邮箱控制权 + 订单号核对" />
          </Form.Item>
          <Form.Item name="note" label="核验说明">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={
          decisionAction === 'approve'
            ? '批准数据主体请求'
            : decisionAction === 'reject'
              ? '驳回数据主体请求'
              : decisionAction === 'cancel'
                ? '取消数据主体请求'
                : '执行数据主体请求'
        }
        open={Boolean(decisionAction && decisionRequest)}
        confirmLoading={saving}
        okText={decisionAction === 'execute' ? '确认执行' : '确认'}
        okButtonProps={{
          danger: decisionAction === 'reject',
        }}
        onOk={() => void submitDecision()}
        onCancel={() => {
          setDecisionAction(null)
          setDecisionRequest(null)
        }}
        forceRender
      >
        <Alert
          type={decisionAction === 'execute' ? 'warning' : 'info'}
          showIcon
          title={
            decisionAction === 'execute'
              ? '执行会写入不可变动作日志。删除只匿名化直接身份，财务事实保留。'
              : '该动作会记录操作者、时间和原因。'
          }
          style={{ marginBottom: 16 }}
        />
        <Form form={decisionForm} layout="vertical">
          {decisionAction === 'reject' ? (
            <Form.Item
              name="reason"
              label="驳回原因"
              rules={[{ required: true }, { min: 2 }]}
            >
              <Input.TextArea rows={3} />
            </Form.Item>
          ) : (
            <Form.Item name="note" label="处理说明">
              <Input.TextArea rows={3} />
            </Form.Item>
          )}
        </Form>
      </Modal>

      <Drawer
        title="数据主体请求详情"
        size="large"
        open={Boolean(selectedRequest)}
        onClose={() => setSelectedRequest(null)}
      >
        {selectedRequest && (
          <Space orientation="vertical" size={16} style={{ width: '100%' }}>
            <Descriptions size="small" column={2} bordered>
              <Descriptions.Item label="请求编号" span={2}>
                {selectedRequest.request_number}
              </Descriptions.Item>
              <Descriptions.Item label="类型">
                {requestTypeOptions.find(
                  (item) => item.value === selectedRequest.request_type,
                )?.label || selectedRequest.request_type}
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                <StatusTag
                  value={selectedRequest.status}
                  labels={requestStatus}
                />
              </Descriptions.Item>
              <Descriptions.Item label="客户账户">
                {accountLabel(selectedRequest.customer_account_id)}
              </Descriptions.Item>
              <Descriptions.Item label="截止时间">
                {formatTime(selectedRequest.due_at)}
              </Descriptions.Item>
              <Descriptions.Item label="核验方式" span={2}>
                {selectedRequest.verification_method || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="请求说明" span={2}>
                {selectedRequest.request_details || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="处理结果" span={2}>
                <Text code>
                  {JSON.stringify(selectedRequest.result_summary || {})}
                </Text>
              </Descriptions.Item>
            </Descriptions>
            <Card size="small" title="不可变动作日志">
              <Table
                rowKey="id"
                size="small"
                pagination={false}
                dataSource={selectedRequest.actions}
                locale={{ emptyText: emptyText('没有动作记录') }}
                columns={[
                  { title: '动作', dataIndex: 'action_type', width: 180 },
                  { title: '操作者', dataIndex: 'actor', width: 180 },
                  { title: '说明', dataIndex: 'note', ellipsis: true },
                  {
                    title: '时间',
                    dataIndex: 'created_at',
                    width: 160,
                    render: formatTime,
                  },
                ]}
              />
            </Card>
          </Space>
        )}
      </Drawer>
    </div>
  )
}
