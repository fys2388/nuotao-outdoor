import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  DatePicker,
  Descriptions,
  Divider,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  FileDoneOutlined,
  FileSearchOutlined,
  PlusOutlined,
  ReloadOutlined,
  SendOutlined,
  ShoppingCartOutlined,
} from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'
import { api, ApiError } from '../api/client'

const { Title, Text } = Typography

interface AgentRecord {
  id: string
  agent_number: string
  company_name: string
  tier: string
  currency: string
}

interface ProductRecord {
  id: string
  sku: string
  name: string
}

interface RFQItem {
  id: string
  product_id: string
  sku_snapshot: string
  product_name_snapshot: string
  requested_quantity: number
  target_unit_price: number | null
  notes: string | null
}

interface RFQ {
  id: string
  rfq_number: string
  agent_id: string
  agent_company: string
  status: string
  source: string
  requested_currency: string
  destination_country: string | null
  incoterm: string | null
  requested_delivery_date: string | null
  notes: string | null
  created_by: string
  submitted_at: string | null
  closed_at: string | null
  items: RFQItem[]
  created_at: string
  updated_at: string
}

interface QuoteItem {
  id: string
  product_id: string
  sku_snapshot: string
  product_name_snapshot: string
  quantity: number
  unit_price: number
  discount_percent: number
  line_total: number
  price_source: string
  price_tier_id: string | null
}

interface ContractSummary {
  id: string
  contract_number: string
  status: string
  customer_signed_at: string | null
  company_signed_at: string | null
  activated_at: string | null
}

interface Quote {
  id: string
  quote_number: string
  version_number: number
  rfq_id: string | null
  rfq_number: string | null
  agent_id: string
  agent_company: string
  status: string
  currency: string
  base_currency: string
  exchange_rate_to_base: number
  price_book_version_id: string | null
  valid_until: string
  payment_terms_days: number
  incoterm: string | null
  subtotal: number
  discount_amount: number
  shipping_cost: number
  tax_amount: number
  total: number
  created_by: string
  approved_by: string | null
  rejection_reason: string | null
  notes: string | null
  items: QuoteItem[]
  contract: ContractSummary | null
  created_at: string
  updated_at: string
}

interface Contract {
  id: string
  contract_number: string
  quote_id: string
  quote_number: string | null
  version_number: number | null
  agent_id: string
  agent_company: string
  status: string
  effective_from: string
  effective_to: string | null
  currency: string
  total: number
  document_url: string | null
  customer_signed_by: string | null
  customer_signed_at: string | null
  company_signed_by: string | null
  company_signed_at: string | null
  activated_at: string | null
  items: QuoteItem[]
  created_at: string
  updated_at: string
}

interface ListResponse<T> {
  items: T[]
  total: number
}

interface B2BSalesPageProps {
  initialTab?: 'rfqs' | 'quotes' | 'contracts'
}

const rfqStatus: Record<string, { color: string; label: string }> = {
  draft: { color: 'default', label: '草稿' },
  submitted: { color: 'blue', label: '已提交' },
  in_review: { color: 'orange', label: '评审中' },
  quoted: { color: 'purple', label: '已报价' },
  won: { color: 'green', label: '已成交' },
  lost: { color: 'red', label: '已流失' },
  cancelled: { color: 'default', label: '已取消' },
}

const quoteStatus: Record<string, { color: string; label: string }> = {
  draft: { color: 'default', label: '草稿' },
  pending_approval: { color: 'orange', label: '待审批' },
  sent: { color: 'blue', label: '已发送' },
  accepted: { color: 'green', label: '已接受' },
  rejected: { color: 'red', label: '已拒绝' },
  expired: { color: 'default', label: '已过期' },
  converted: { color: 'cyan', label: '已转订单' },
  cancelled: { color: 'default', label: '已取消' },
}

const contractStatus: Record<string, { color: string; label: string }> = {
  draft: { color: 'default', label: '草稿' },
  pending_signature: { color: 'orange', label: '待签署' },
  active: { color: 'green', label: '已生效' },
  expired: { color: 'default', label: '已过期' },
  terminated: { color: 'red', label: '已终止' },
  cancelled: { color: 'default', label: '已取消' },
}

const priceSourceLabel: Record<string, string> = {
  TIER: '等级阶梯价',
  AGENT: '客户专属价',
  QUOTE: '报价价',
}

function formatMoney(value: number, currency: string): string {
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: currency || 'USD',
    maximumFractionDigits: 2,
  }).format(value)
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  return error instanceof Error ? error.message : '操作失败'
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

export default function B2BSalesPage({ initialTab = 'rfqs' }: B2BSalesPageProps) {
  const [activeTab, setActiveTab] = useState(initialTab)
  const [agents, setAgents] = useState<AgentRecord[]>([])
  const [products, setProducts] = useState<ProductRecord[]>([])
  const [rfqs, setRfqs] = useState<RFQ[]>([])
  const [quotes, setQuotes] = useState<Quote[]>([])
  const [contracts, setContracts] = useState<Contract[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [rfqStatusFilter, setRfqStatusFilter] = useState<string>()
  const [quoteStatusFilter, setQuoteStatusFilter] = useState<string>()
  const [contractStatusFilter, setContractStatusFilter] = useState<string>()

  const [rfqModalOpen, setRfqModalOpen] = useState(false)
  const [quoteModalRfq, setQuoteModalRfq] = useState<RFQ | null>(null)
  const [contractModalQuote, setContractModalQuote] = useState<Quote | null>(null)
  const [signingContract, setSigningContract] = useState<Contract | null>(null)
  const [signingParty, setSigningParty] = useState<'customer' | 'company'>('customer')

  const [rfqForm] = Form.useForm()
  const [quoteForm] = Form.useForm()
  const [contractForm] = Form.useForm()
  const [signForm] = Form.useForm()

  const agentOptions = useMemo(
    () =>
      agents.map((agent) => ({
        value: agent.id,
        label: `${agent.company_name} · ${agent.agent_number}`,
      })),
    [agents],
  )

  const productOptions = useMemo(
    () =>
      products.map((product) => ({
        value: product.id,
        label: `${product.sku} · ${product.name}`,
      })),
    [products],
  )

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [rfqResponse, quoteResponse, contractResponse, agentResponse, productResponse] =
        await Promise.all([
          api.getB2BRFQs(1, 200, rfqStatusFilter) as Promise<ListResponse<RFQ>>,
          api.getB2BQuotes(1, 200, quoteStatusFilter) as Promise<ListResponse<Quote>>,
          api.getB2BContracts(1, 200, contractStatusFilter) as Promise<ListResponse<Contract>>,
          api.getB2BAgents() as Promise<ListResponse<AgentRecord>>,
          api.getProducts(500) as Promise<ProductRecord[]>,
        ])
      setRfqs(rfqResponse.items || [])
      setQuotes(quoteResponse.items || [])
      setContracts(contractResponse.items || [])
      setAgents(agentResponse.items || [])
      setProducts(productResponse || [])
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }, [contractStatusFilter, quoteStatusFilter, rfqStatusFilter])

  useEffect(() => {
    void load()
  }, [load])

  const runAction = async (action: () => Promise<unknown>, success: string) => {
    setSaving(true)
    try {
      await action()
      message.success(success)
      await load()
    } catch (requestError) {
      message.error(errorMessage(requestError))
    } finally {
      setSaving(false)
    }
  }

  const openRfqModal = () => {
    rfqForm.resetFields()
    rfqForm.setFieldsValue({
      requested_currency: 'USD',
      items: [{ quantity: 1 }],
    })
    setRfqModalOpen(true)
  }

  const submitRfq = async () => {
    const values = await rfqForm.validateFields()
    await runAction(
      () =>
        api.createB2BRFQ({
          agent_id: values.agent_id,
          source: 'manual',
          requested_currency: values.requested_currency,
          destination_country: values.destination_country,
          incoterm: values.incoterm,
          requested_delivery_date: values.requested_delivery_date
            ? (values.requested_delivery_date as Dayjs).format('YYYY-MM-DD')
            : null,
          notes: values.notes,
          items: values.items.map(
            (item: {
              product_id: string
              quantity: number
              target_unit_price?: number
              notes?: string
            }) => ({
              product_id: item.product_id,
              quantity: item.quantity,
              target_unit_price: item.target_unit_price ?? null,
              notes: item.notes,
              specifications: {},
            }),
          ),
        }),
      'RFQ 已创建',
    )
    setRfqModalOpen(false)
  }

  const openQuoteModal = (rfq: RFQ) => {
    quoteForm.resetFields()
    quoteForm.setFieldsValue({
      valid_until: dayjs().add(14, 'day'),
      payment_terms_days: 30,
      exchange_rate_to_base: 1,
      base_currency: rfq.requested_currency || 'USD',
      shipping_cost: 0,
      tax_amount: 0,
    })
    setQuoteModalRfq(rfq)
  }

  const submitQuote = async () => {
    if (!quoteModalRfq) return
    const values = await quoteForm.validateFields()
    await runAction(
      () =>
        api.createB2BQuoteFromRFQ(quoteModalRfq.id, {
          valid_until: (values.valid_until as Dayjs).format('YYYY-MM-DD'),
          payment_terms_days: values.payment_terms_days,
          exchange_rate_to_base: values.exchange_rate_to_base,
          base_currency: values.base_currency,
          shipping_cost: values.shipping_cost,
          tax_amount: values.tax_amount,
          shipping_terms: values.shipping_terms,
          notes: values.notes,
        }),
      '报价草稿已生成',
    )
    setQuoteModalRfq(null)
    setActiveTab('quotes')
  }

  const openContractModal = (quote: Quote) => {
    contractForm.resetFields()
    contractForm.setFieldsValue({
      effective_from: dayjs(),
    })
    setContractModalQuote(quote)
  }

  const submitContract = async () => {
    if (!contractModalQuote) return
    const values = await contractForm.validateFields()
    await runAction(
      () =>
        api.createB2BContractFromQuote(contractModalQuote.id, {
          effective_from: (values.effective_from as Dayjs).format('YYYY-MM-DD'),
          effective_to: values.effective_to
            ? (values.effective_to as Dayjs).format('YYYY-MM-DD')
            : null,
          document_url: values.document_url,
          terms: {
            payment_terms_days: contractModalQuote.payment_terms_days,
            incoterm: contractModalQuote.incoterm,
          },
        }),
      '合同草稿已创建',
    )
    setContractModalQuote(null)
    setActiveTab('contracts')
  }

  const openSignModal = (contract: Contract, party: 'customer' | 'company') => {
    signForm.resetFields()
    signForm.setFieldsValue({
      signed_by: party === 'customer' ? contract.agent_company : 'Nuotao',
    })
    setSigningContract(contract)
    setSigningParty(party)
  }

  const submitSignature = async () => {
    if (!signingContract) return
    const values = await signForm.validateFields()
    await runAction(
      () =>
        api.signB2BContract(
          signingContract.id,
          signingParty,
          values.signed_by as string,
        ),
      signingParty === 'customer' ? '客户签署已登记' : '公司签署已登记',
    )
    setSigningContract(null)
  }

  const rfqColumns: ColumnsType<RFQ> = [
    {
      title: 'RFQ',
      dataIndex: 'rfq_number',
      fixed: 'left',
      width: 170,
      render: (value: string, row) => (
        <Space orientation="vertical" size={0}>
          <Text strong>{value}</Text>
          <Text type="secondary">{dayjs(row.created_at).format('YYYY-MM-DD HH:mm')}</Text>
        </Space>
      ),
    },
    {
      title: '客户',
      dataIndex: 'agent_company',
      width: 180,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string) => <StatusTag value={value} labels={rfqStatus} />,
    },
    {
      title: '商品 / 数量',
      width: 250,
      render: (_, row) => (
        <Space orientation="vertical" size={2}>
          {row.items.slice(0, 2).map((item) => (
            <Text key={item.id}>
              {item.sku_snapshot} × {item.requested_quantity}
            </Text>
          ))}
          {row.items.length > 2 && <Text type="secondary">另有 {row.items.length - 2} 项</Text>}
        </Space>
      ),
    },
    {
      title: '贸易条件',
      width: 150,
      render: (_, row) => (
        <Space orientation="vertical" size={0}>
          <Text>{row.incoterm || '未指定 Incoterm'}</Text>
          <Text type="secondary">{row.destination_country || '目的地待确认'}</Text>
        </Space>
      ),
    },
    {
      title: '交期',
      dataIndex: 'requested_delivery_date',
      width: 110,
      render: (value: string | null) => value || '-',
    },
    {
      title: '操作',
      fixed: 'right',
      width: 260,
      render: (_, row) => (
        <Space wrap size={4}>
          {row.status === 'draft' && (
            <Button
              type="link"
              size="small"
              icon={<SendOutlined />}
              onClick={() =>
                void runAction(
                  () => api.updateB2BRFQStatus(row.id, 'submitted'),
                  'RFQ 已提交',
                )
              }
            >
              提交
            </Button>
          )}
          {row.status === 'submitted' && (
            <Button
              type="link"
              size="small"
              onClick={() =>
                void runAction(
                  () => api.updateB2BRFQStatus(row.id, 'in_review'),
                  'RFQ 已进入评审',
                )
              }
            >
              受理
            </Button>
          )}
          {['submitted', 'in_review'].includes(row.status) && (
            <Button type="link" size="small" onClick={() => openQuoteModal(row)}>
              生成报价
            </Button>
          )}
          {!['won', 'lost', 'cancelled', 'quoted'].includes(row.status) && (
            <Popconfirm
              title="确认取消该 RFQ？"
              onConfirm={() =>
                void runAction(
                  () => api.updateB2BRFQStatus(row.id, 'cancelled', 'cancelled by operator'),
                  'RFQ 已取消',
                )
              }
            >
              <Button type="link" danger size="small">
                取消
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  const quoteColumns: ColumnsType<Quote> = [
    {
      title: '报价',
      fixed: 'left',
      width: 180,
      render: (_, row) => (
        <Space orientation="vertical" size={0}>
          <Text strong>
            {row.quote_number} · V{row.version_number}
          </Text>
          <Text type="secondary">{row.rfq_number || '独立报价'}</Text>
        </Space>
      ),
    },
    { title: '客户', dataIndex: 'agent_company', width: 180 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string) => <StatusTag value={value} labels={quoteStatus} />,
    },
    {
      title: '金额',
      width: 140,
      render: (_, row) => (
        <Text strong>{formatMoney(row.total, row.currency)}</Text>
      ),
    },
    {
      title: '有效期',
      dataIndex: 'valid_until',
      width: 110,
      render: (value: string, row) => (
        <Space orientation="vertical" size={0}>
          <Text type={dayjs(value).isBefore(dayjs(), 'day') ? 'danger' : undefined}>
            {value}
          </Text>
          <Text type="secondary">账期 {row.payment_terms_days} 天</Text>
        </Space>
      ),
    },
    {
      title: '合同',
      width: 150,
      render: (_, row) =>
        row.contract ? (
          <Space orientation="vertical" size={0}>
            <Text>{row.contract.contract_number}</Text>
            <StatusTag value={row.contract.status} labels={contractStatus} />
          </Space>
        ) : (
          <Text type="secondary">未创建</Text>
        ),
    },
    {
      title: '操作',
      fixed: 'right',
      width: 280,
      render: (_, row) => (
        <Space wrap size={4}>
          {row.status === 'draft' && (
            <Button
              type="link"
              size="small"
              onClick={() =>
                void runAction(
                  () => api.updateB2BQuoteStatus(row.id, 'pending_approval'),
                  '报价已提交审批',
                )
              }
            >
              提交审批
            </Button>
          )}
          {row.status === 'pending_approval' && (
            <Button
              type="link"
              size="small"
              icon={<SendOutlined />}
              onClick={() =>
                void runAction(
                  () => api.updateB2BQuoteStatus(row.id, 'sent'),
                  '报价已审批并发送',
                )
              }
            >
              审批发送
            </Button>
          )}
          {row.status === 'sent' && (
            <>
              <Button
                type="link"
                size="small"
                icon={<CheckCircleOutlined />}
                onClick={() =>
                  void runAction(
                    () => api.updateB2BQuoteStatus(row.id, 'accepted'),
                    '客户接受报价',
                  )
                }
              >
                接受
              </Button>
              <Popconfirm
                title="确认客户拒绝该报价？"
                onConfirm={() =>
                  void runAction(
                    () =>
                      api.updateB2BQuoteStatus(
                        row.id,
                        'rejected',
                        'rejected by customer',
                      ),
                    '报价已标记为拒绝',
                  )
                }
              >
                <Button type="link" danger size="small" icon={<CloseCircleOutlined />}>
                  拒绝
                </Button>
              </Popconfirm>
            </>
          )}
          {row.status === 'accepted' && !row.contract && (
            <Button type="link" size="small" onClick={() => openContractModal(row)}>
              创建合同
            </Button>
          )}
          {row.contract?.status === 'active' && (
            <Popconfirm
              title="将该报价转换为正式 B2B 订单？"
              onConfirm={() =>
                void runAction(
                  () => api.convertB2BQuoteToOrder(row.id),
                  'B2B 订单已创建',
                )
              }
            >
              <Button type="link" size="small" icon={<ShoppingCartOutlined />}>
                转订单
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  const contractColumns: ColumnsType<Contract> = [
    {
      title: '合同',
      fixed: 'left',
      width: 180,
      render: (_, row) => (
        <Space orientation="vertical" size={0}>
          <Text strong>{row.contract_number}</Text>
          <Text type="secondary">
            {row.quote_number || '报价'} · V{row.version_number || 1}
          </Text>
        </Space>
      ),
    },
    { title: '客户', dataIndex: 'agent_company', width: 180 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string) => <StatusTag value={value} labels={contractStatus} />,
    },
    {
      title: '签署进度',
      width: 220,
      render: (_, row) => (
        <Space orientation="vertical" size={2}>
          <Text>
            客户：{row.customer_signed_by || '待签署'}
            {row.customer_signed_at ? ` · ${dayjs(row.customer_signed_at).format('YYYY-MM-DD')}` : ''}
          </Text>
          <Text>
            公司：{row.company_signed_by || '待签署'}
            {row.company_signed_at ? ` · ${dayjs(row.company_signed_at).format('YYYY-MM-DD')}` : ''}
          </Text>
        </Space>
      ),
    },
    {
      title: '金额',
      width: 140,
      render: (_, row) => <Text strong>{formatMoney(row.total, row.currency)}</Text>,
    },
    {
      title: '有效期',
      width: 190,
      render: (_, row) =>
        `${row.effective_from}${row.effective_to ? ` 至 ${row.effective_to}` : ' 起'}`,
    },
    {
      title: '操作',
      fixed: 'right',
      width: 280,
      render: (_, row) => (
        <Space wrap size={4}>
          {row.status === 'draft' && (
            <Button
              type="link"
              size="small"
              icon={<SendOutlined />}
              onClick={() =>
                void runAction(
                  () => api.updateB2BContractStatus(row.id, 'pending_signature'),
                  '合同已发起签署',
                )
              }
            >
              发起签署
            </Button>
          )}
          {row.status === 'pending_signature' && !row.customer_signed_at && (
            <Button type="link" size="small" onClick={() => openSignModal(row, 'customer')}>
              客户签署
            </Button>
          )}
          {row.status === 'pending_signature' && !row.company_signed_at && (
            <Button type="link" size="small" onClick={() => openSignModal(row, 'company')}>
              公司签署
            </Button>
          )}
          {row.status === 'active' && (
            <Popconfirm
              title="将该合同对应报价转换为 B2B 订单？"
              onConfirm={() =>
                void runAction(
                  () => api.convertB2BQuoteToOrder(row.quote_id),
                  'B2B 订单已创建',
                )
              }
            >
              <Button type="link" size="small" icon={<ShoppingCartOutlined />}>
                转订单
              </Button>
            </Popconfirm>
          )}
          {['draft', 'pending_signature'].includes(row.status) && (
            <Popconfirm
              title="确认取消该合同？"
              onConfirm={() =>
                void runAction(
                  () =>
                    api.updateB2BContractStatus(
                      row.id,
                      'cancelled',
                      'cancelled by operator',
                    ),
                  '合同已取消',
                )
              }
            >
              <Button type="link" danger size="small">
                取消
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  const tabItems = [
    {
      key: 'rfqs',
      label: (
        <Space>
          <FileSearchOutlined />
          RFQ 询盘
        </Space>
      ),
      children: (
        <>
          <div className="table-toolbar">
            <Space wrap>
              <Select
                allowClear
                placeholder="按状态筛选"
                value={rfqStatusFilter}
                onChange={setRfqStatusFilter}
                options={Object.entries(rfqStatus).map(([value, item]) => ({
                  value,
                  label: item.label,
                }))}
                style={{ width: 150 }}
              />
            </Space>
            <Button type="primary" icon={<PlusOutlined />} onClick={openRfqModal}>
              新建 RFQ
            </Button>
          </div>
          <Table
            rowKey="id"
            loading={loading}
            columns={rfqColumns}
            dataSource={rfqs}
            scroll={{ x: 1320 }}
            pagination={{ pageSize: 20, showSizeChanger: false }}
            expandable={{
              expandedRowRender: (row) => (
                <Descriptions size="small" column={{ xs: 1, md: 3 }}>
                  <Descriptions.Item label="来源">{row.source}</Descriptions.Item>
                  <Descriptions.Item label="币种">{row.requested_currency}</Descriptions.Item>
                  <Descriptions.Item label="创建人">{row.created_by}</Descriptions.Item>
                  <Descriptions.Item label="备注" span={3}>
                    {row.notes || '-'}
                  </Descriptions.Item>
                </Descriptions>
              ),
            }}
          />
        </>
      ),
    },
    {
      key: 'quotes',
      label: (
        <Space>
          <FileDoneOutlined />
          报价
        </Space>
      ),
      children: (
        <>
          <div className="table-toolbar">
            <Select
              allowClear
              placeholder="按状态筛选"
              value={quoteStatusFilter}
              onChange={setQuoteStatusFilter}
              options={Object.entries(quoteStatus).map(([value, item]) => ({
                value,
                label: item.label,
              }))}
              style={{ width: 150 }}
            />
          </div>
          <Table
            rowKey="id"
            loading={loading}
            columns={quoteColumns}
            dataSource={quotes}
            scroll={{ x: 1350 }}
            pagination={{ pageSize: 20, showSizeChanger: false }}
            expandable={{
              expandedRowRender: (row) => (
                <Space orientation="vertical" style={{ width: '100%' }}>
                  <Table
                    rowKey="id"
                    size="small"
                    pagination={false}
                    dataSource={row.items}
                    columns={[
                      { title: 'SKU', dataIndex: 'sku_snapshot', width: 140 },
                      { title: '商品', dataIndex: 'product_name_snapshot' },
                      { title: '数量', dataIndex: 'quantity', width: 90 },
                      {
                        title: '单价',
                        width: 110,
                        render: (_, item: QuoteItem) =>
                          formatMoney(item.unit_price, row.currency),
                      },
                      {
                        title: '价格来源',
                        width: 120,
                        render: (_, item: QuoteItem) =>
                          priceSourceLabel[item.price_source] || item.price_source,
                      },
                      {
                        title: '小计',
                        width: 120,
                        render: (_, item: QuoteItem) =>
                          formatMoney(item.line_total, row.currency),
                      },
                    ]}
                  />
                  {row.rejection_reason && (
                    <Alert type="warning" showIcon title={row.rejection_reason} />
                  )}
                </Space>
              ),
            }}
          />
        </>
      ),
    },
    {
      key: 'contracts',
      label: (
        <Space>
          <FileDoneOutlined />
          合同
        </Space>
      ),
      children: (
        <>
          <div className="table-toolbar">
            <Select
              allowClear
              placeholder="按状态筛选"
              value={contractStatusFilter}
              onChange={setContractStatusFilter}
              options={Object.entries(contractStatus).map(([value, item]) => ({
                value,
                label: item.label,
              }))}
              style={{ width: 150 }}
            />
          </div>
          <Table
            rowKey="id"
            loading={loading}
            columns={contractColumns}
            dataSource={contracts}
            scroll={{ x: 1280 }}
            pagination={{ pageSize: 20, showSizeChanger: false }}
            expandable={{
              expandedRowRender: (row) => (
                <Table
                  rowKey="id"
                  size="small"
                  pagination={false}
                  dataSource={row.items}
                  columns={[
                    { title: 'SKU', dataIndex: 'sku_snapshot', width: 150 },
                    { title: '商品', dataIndex: 'product_name_snapshot' },
                    { title: '数量', dataIndex: 'quantity', width: 100 },
                    {
                      title: '单价',
                      width: 120,
                      render: (_, item: QuoteItem) =>
                        formatMoney(item.unit_price, row.currency),
                    },
                  ]}
                />
              ),
            }}
          />
        </>
      ),
    },
  ]

  return (
    <div className="dashboard-page">
      <div className="page-heading">
        <div>
          <div className="page-kicker page-kicker--b2b">B2B SALES CHAIN</div>
          <Title level={2}>询盘、报价与合同</Title>
          <p>从客户 RFQ 到合同签署和订单转换，价格、版本、签署与审计链路保持连续。</p>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
          刷新
        </Button>
      </div>

      {error && (
        <Alert
          type="error"
          showIcon
          title="销售链路数据加载失败"
          description={error}
          className="page-alert"
        />
      )}

      <Card variant="borderless">
        <Tabs
          activeKey={activeTab}
          onChange={(key) => setActiveTab(key as 'rfqs' | 'quotes' | 'contracts')}
          items={tabItems}
        />
      </Card>

      <Modal
        open={rfqModalOpen}
        title="新建 RFQ"
        width={860}
        okText="创建"
        confirmLoading={saving}
        onOk={() => void submitRfq()}
        onCancel={() => setRfqModalOpen(false)}
        forceRender
      >
        <Form form={rfqForm} layout="vertical">
          <Form.Item
            name="agent_id"
            label="客户"
            rules={[{ required: true, message: '请选择客户' }]}
          >
            <Select
              showSearch
              optionFilterProp="label"
              options={agentOptions}
              placeholder="选择代理商或批发客户"
            />
          </Form.Item>
          <Space style={{ width: '100%' }} align="start">
            <Form.Item name="requested_currency" label="询价币种" initialValue="USD">
              <Select
                style={{ width: 120 }}
                options={['USD', 'EUR', 'GBP', 'AUD', 'CAD'].map((value) => ({
                  value,
                  label: value,
                }))}
              />
            </Form.Item>
            <Form.Item name="destination_country" label="目的国家">
              <Input style={{ width: 140 }} placeholder="如 US / DE" />
            </Form.Item>
            <Form.Item name="incoterm" label="Incoterm">
              <Select
                allowClear
                style={{ width: 140 }}
                options={['EXW', 'FOB', 'CIF', 'DDP', 'DAP'].map((value) => ({
                  value,
                  label: value,
                }))}
              />
            </Form.Item>
            <Form.Item name="requested_delivery_date" label="期望交期">
              <DatePicker />
            </Form.Item>
          </Space>
          <Divider titlePlacement="start">询价商品</Divider>
          <Form.List name="items">
            {(fields, { add, remove }) => (
              <Space orientation="vertical" style={{ width: '100%' }}>
                {fields.map((field) => (
                  <Space key={field.key} align="start" wrap>
                    <Form.Item
                      name={[field.name, 'product_id']}
                      rules={[{ required: true, message: '请选择商品' }]}
                      style={{ marginBottom: 8, width: 330 }}
                    >
                      <Select
                        showSearch
                        optionFilterProp="label"
                        options={productOptions}
                        placeholder="选择商品"
                      />
                    </Form.Item>
                    <Form.Item
                      name={[field.name, 'quantity']}
                      rules={[{ required: true, message: '请输入数量' }]}
                      style={{ marginBottom: 8, width: 130 }}
                    >
                      <InputNumber min={1} precision={0} placeholder="数量" />
                    </Form.Item>
                    <Form.Item
                      name={[field.name, 'target_unit_price']}
                      style={{ marginBottom: 8, width: 150 }}
                    >
                      <InputNumber min={0.01} placeholder="目标单价" />
                    </Form.Item>
                    <Form.Item
                      name={[field.name, 'notes']}
                      style={{ marginBottom: 8, width: 180 }}
                    >
                      <Input placeholder="行备注" />
                    </Form.Item>
                    {fields.length > 1 && (
                      <Button danger type="text" onClick={() => remove(field.name)}>
                        删除
                      </Button>
                    )}
                  </Space>
                ))}
                <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({ quantity: 1 })}>
                  添加商品
                </Button>
              </Space>
            )}
          </Form.List>
          <Form.Item name="notes" label="客户要求与备注" style={{ marginTop: 16 }}>
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={Boolean(quoteModalRfq)}
        title={`从 ${quoteModalRfq?.rfq_number || 'RFQ'} 生成报价`}
        okText="生成草稿"
        confirmLoading={saving}
        onOk={() => void submitQuote()}
        onCancel={() => setQuoteModalRfq(null)}
        forceRender
      >
        <Alert
          type="info"
          showIcon
          title="价格将从当前已发布价格版本解析并写入报价快照，后续价格调整不会改写历史报价。"
          style={{ marginBottom: 16 }}
        />
        <Form form={quoteForm} layout="vertical">
          <Space wrap align="start">
            <Form.Item
              name="valid_until"
              label="报价有效期"
              rules={[{ required: true }]}
            >
              <DatePicker />
            </Form.Item>
            <Form.Item name="payment_terms_days" label="账期（天）">
              <InputNumber min={0} max={365} precision={0} />
            </Form.Item>
            <Form.Item name="base_currency" label="基准币种">
              <Select
                style={{ width: 110 }}
                options={['USD', 'CNY', 'EUR'].map((value) => ({
                  value,
                  label: value,
                }))}
              />
            </Form.Item>
            <Form.Item name="exchange_rate_to_base" label="汇率">
              <InputNumber min={0.00000001} precision={8} />
            </Form.Item>
          </Space>
          <Space wrap align="start">
            <Form.Item name="shipping_cost" label="运费">
              <InputNumber min={0} precision={2} />
            </Form.Item>
            <Form.Item name="tax_amount" label="税费">
              <InputNumber min={0} precision={2} />
            </Form.Item>
          </Space>
          <Form.Item name="shipping_terms" label="运输条款">
            <Input />
          </Form.Item>
          <Form.Item name="notes" label="报价备注">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={Boolean(contractModalQuote)}
        title={`为 ${contractModalQuote?.quote_number || '报价'} 创建合同`}
        okText="创建草稿"
        confirmLoading={saving}
        onOk={() => void submitContract()}
        onCancel={() => setContractModalQuote(null)}
        forceRender
      >
        <Form form={contractForm} layout="vertical">
          <Space wrap align="start">
            <Form.Item
              name="effective_from"
              label="生效日期"
              rules={[{ required: true }]}
            >
              <DatePicker />
            </Form.Item>
            <Form.Item name="effective_to" label="失效日期">
              <DatePicker />
            </Form.Item>
          </Space>
          <Form.Item name="document_url" label="合同文件地址">
            <Input placeholder="https://..." />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={Boolean(signingContract)}
        title={signingParty === 'customer' ? '登记客户签署' : '登记公司签署'}
        okText="确认签署"
        confirmLoading={saving}
        onOk={() => void submitSignature()}
        onCancel={() => setSigningContract(null)}
        forceRender
      >
        <Form form={signForm} layout="vertical">
          <Form.Item
            name="signed_by"
            label="签署人"
            rules={[{ required: true, message: '请输入签署人' }]}
          >
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
