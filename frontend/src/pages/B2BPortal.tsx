import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Descriptions,
  Divider,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  BankOutlined,
  CheckCircleOutlined,
  FileDoneOutlined,
  FileSearchOutlined,
  LogoutOutlined,
  PlusOutlined,
  ReloadOutlined,
  ShoppingCartOutlined,
  TeamOutlined,
  WalletOutlined,
} from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  PortalApiError,
  clearPortalToken,
  getPortalToken,
  portalApi,
  setPortalToken,
  type PortalAccountSummary,
  type PortalAgent,
  type PortalContract,
  type PortalOrder,
  type PortalProduct,
  type PortalQuote,
  type PortalRFQ,
} from '../api/b2bPortal'

const { Title, Text, Paragraph } = Typography

const statusColors: Record<string, string> = {
  submitted: 'blue',
  in_review: 'orange',
  quoted: 'purple',
  won: 'green',
  lost: 'red',
  cancelled: 'default',
  sent: 'blue',
  accepted: 'green',
  rejected: 'red',
  expired: 'default',
  converted: 'cyan',
  pending_signature: 'orange',
  active: 'green',
  terminated: 'red',
  pending: 'orange',
  confirmed: 'blue',
  processing: 'purple',
  shipped: 'cyan',
  delivered: 'green',
  unpaid: 'orange',
  partial: 'gold',
  paid: 'green',
  overdue: 'red',
}

const statusLabels: Record<string, string> = {
  submitted: '已提交',
  in_review: '评审中',
  quoted: '已报价',
  won: '已成交',
  lost: '已流失',
  cancelled: '已取消',
  sent: '待确认',
  accepted: '已接受',
  rejected: '已拒绝',
  expired: '已过期',
  converted: '已转订单',
  pending_signature: '待签署',
  active: '已生效',
  terminated: '已终止',
  pending: '待确认',
  confirmed: '已确认',
  processing: '处理中',
  shipped: '已发货',
  delivered: '已送达',
  unpaid: '未付款',
  partial: '部分付款',
  paid: '已付款',
  overdue: '已逾期',
}

const navItems = [
  { key: 'overview', label: '工作台', icon: <BankOutlined /> },
  { key: 'products', label: '商品目录', icon: <TeamOutlined /> },
  { key: 'rfqs', label: 'RFQ 询盘', icon: <FileSearchOutlined /> },
  { key: 'quotes', label: '报价', icon: <FileDoneOutlined /> },
  { key: 'contracts', label: '合同', icon: <FileDoneOutlined /> },
  { key: 'orders', label: '订单', icon: <ShoppingCartOutlined /> },
  { key: 'account', label: '账户', icon: <WalletOutlined /> },
] as const

interface LoginFormValues {
  email: string
  password: string
}

interface RfqFormValues {
  requested_currency: string
  destination_country?: string
  incoterm?: string
  requested_delivery_date?: Dayjs
  notes?: string
  items: Array<{
    product_id: string
    quantity: number
    target_unit_price?: number
    notes?: string
  }>
}

interface SignFormValues {
  signed_by: string
}

interface RejectFormValues {
  reason: string
}

function money(value: number, currency: string): string {
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: currency || 'USD',
    maximumFractionDigits: 2,
  }).format(value)
}

function errorMessage(error: unknown): string {
  if (error instanceof PortalApiError) return error.message
  return error instanceof Error ? error.message : '操作失败'
}

function StatusTag({ value }: { value: string }) {
  return <Tag color={statusColors[value] || 'default'}>{statusLabels[value] || value}</Tag>
}

function PortalLoading() {
  return (
    <div className="portal-loading">
      <span className="route-loading__mark" />
      <span>正在加载客户门户</span>
    </div>
  )
}

function PortalLogin({ onAuthenticated }: { onAuthenticated: (agent: PortalAgent) => void }) {
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm<LoginFormValues>()

  const submit = async () => {
    const values = await form.validateFields()
    setSubmitting(true)
    try {
      const response = await portalApi.login(values.email, values.password)
      setPortalToken(response.access_token)
      onAuthenticated(response.agent)
    } catch (error) {
      message.error(errorMessage(error))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="portal-login-page">
      <section className="portal-login-panel">
        <div className="portal-login-brand">
          <span className="portal-mark">N</span>
          <div>
            <Title level={2}>Nuotao B2B</Title>
            <Text type="secondary">Partner Portal</Text>
          </div>
        </div>
        <Divider />
        <Form form={form} layout="vertical" onFinish={() => void submit()}>
          <Form.Item
            name="email"
            label="登录邮箱"
            rules={[
              { required: true, message: '请输入登录邮箱' },
              { type: 'email', message: '邮箱格式不正确' },
            ]}
          >
            <Input autoComplete="email" size="large" />
          </Form.Item>
          <Form.Item
            name="password"
            label="密码"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password autoComplete="current-password" size="large" />
          </Form.Item>
          <Button
            type="primary"
            htmlType="submit"
            size="large"
            block
            loading={submitting}
          >
            登录
          </Button>
        </Form>
      </section>
    </div>
  )
}

export default function B2BPortal() {
  const location = useLocation()
  const navigate = useNavigate()
  const [agent, setAgent] = useState<PortalAgent | null>(null)
  const [summary, setSummary] = useState<PortalAccountSummary | null>(null)
  const [products, setProducts] = useState<PortalProduct[]>([])
  const [rfqs, setRfqs] = useState<PortalRFQ[]>([])
  const [quotes, setQuotes] = useState<PortalQuote[]>([])
  const [contracts, setContracts] = useState<PortalContract[]>([])
  const [orders, setOrders] = useState<PortalOrder[]>([])
  const [loading, setLoading] = useState(Boolean(getPortalToken()))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [rfqModalOpen, setRfqModalOpen] = useState(false)
  const [rejectingQuote, setRejectingQuote] = useState<PortalQuote | null>(null)
  const [signingContract, setSigningContract] = useState<PortalContract | null>(null)
  const [rfqForm] = Form.useForm<RfqFormValues>()
  const [signForm] = Form.useForm<SignFormValues>()
  const [rejectForm] = Form.useForm<RejectFormValues>()

  const section = location.pathname.split('/')[2] || 'overview'

  const loadPortal = useCallback(async () => {
    if (!getPortalToken()) {
      setAgent(null)
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const [
        agentResponse,
        summaryResponse,
        productResponse,
        rfqResponse,
        quoteResponse,
        contractResponse,
        orderResponse,
      ] = await Promise.all([
        portalApi.me(),
        portalApi.summary(),
        portalApi.products(),
        portalApi.rfqs(),
        portalApi.quotes(),
        portalApi.contracts(),
        portalApi.orders(),
      ])
      setAgent(agentResponse)
      setSummary(summaryResponse)
      setProducts(productResponse.items || [])
      setRfqs(rfqResponse.items || [])
      setQuotes(quoteResponse.items || [])
      setContracts(contractResponse.items || [])
      setOrders(orderResponse.items || [])
    } catch (requestError) {
      if (requestError instanceof PortalApiError && requestError.status === 401) {
        clearPortalToken()
        setAgent(null)
      } else {
        setError(errorMessage(requestError))
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadPortal()
  }, [loadPortal])

  const logout = () => {
    clearPortalToken()
    setAgent(null)
    navigate('/portal', { replace: true })
  }

  const runAction = async (action: () => Promise<unknown>, success: string) => {
    setSaving(true)
    try {
      await action()
      message.success(success)
      await loadPortal()
    } catch (requestError) {
      message.error(errorMessage(requestError))
    } finally {
      setSaving(false)
    }
  }

  const productOptions = useMemo(
    () =>
      products.map((product) => ({
        value: product.id,
        label: `${product.sku} · ${product.name} · ${money(product.wholesale_price, product.currency)}`,
      })),
    [products],
  )

  const openRfqModal = () => {
    rfqForm.resetFields()
    rfqForm.setFieldsValue({
      requested_currency: agent?.currency || 'USD',
      items: [{ quantity: 1 }],
    })
    setRfqModalOpen(true)
  }

  const submitRfq = async () => {
    const values = await rfqForm.validateFields()
    await runAction(
      () =>
        portalApi.createRfq({
          requested_currency: values.requested_currency,
          destination_country: values.destination_country || null,
          incoterm: values.incoterm || null,
          requested_delivery_date: values.requested_delivery_date
            ? values.requested_delivery_date.format('YYYY-MM-DD')
            : null,
          notes: values.notes || null,
          items: values.items.map((item) => ({
            product_id: item.product_id,
            quantity: item.quantity,
            target_unit_price: item.target_unit_price ?? null,
            specifications: {},
            notes: item.notes || null,
          })),
        }),
      'RFQ 已提交',
    )
    setRfqModalOpen(false)
  }

  const submitSignature = async () => {
    if (!signingContract) return
    const values = await signForm.validateFields()
    await runAction(
      () => portalApi.signContract(signingContract.id, values.signed_by),
      '客户签署已登记',
    )
    setSigningContract(null)
  }

  const submitRejection = async () => {
    if (!rejectingQuote) return
    const values = await rejectForm.validateFields()
    await runAction(
      () => portalApi.rejectQuote(rejectingQuote.id, values.reason),
      '报价已拒绝',
    )
    setRejectingQuote(null)
  }

  if (!agent) {
    if (loading) return <PortalLoading />
    return <PortalLogin onAuthenticated={(authenticatedAgent) => {
      setAgent(authenticatedAgent)
      navigate('/portal', { replace: true })
      void loadPortal()
    }} />
  }

  const rfqColumns: ColumnsType<PortalRFQ> = [
    {
      title: 'RFQ',
      dataIndex: 'rfq_number',
      width: 170,
      render: (value: string, row) => (
        <Space orientation="vertical" size={0}>
          <Text strong>{value}</Text>
          <Text type="secondary">{dayjs(row.created_at).format('YYYY-MM-DD HH:mm')}</Text>
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string) => <StatusTag value={value} />,
    },
    {
      title: '商品',
      render: (_, row) => row.items.map((item) => `${item.sku_snapshot} × ${item.requested_quantity}`).join('，'),
    },
    { title: 'Incoterm', dataIndex: 'incoterm', width: 100 },
    {
      title: '期望交期',
      dataIndex: 'requested_delivery_date',
      width: 120,
      render: (value: string | null) => value || '-',
    },
  ]

  const quoteColumns: ColumnsType<PortalQuote> = [
    {
      title: '报价',
      dataIndex: 'quote_number',
      width: 180,
      render: (value: string, row) => (
        <Space orientation="vertical" size={0}>
          <Text strong>{value} · V{row.version_number}</Text>
          <Text type="secondary">{row.rfq_number || '-'}</Text>
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string) => <StatusTag value={value} />,
    },
    {
      title: '金额',
      width: 140,
      render: (_, row) => money(row.total, row.currency),
    },
    {
      title: '有效期',
      dataIndex: 'valid_until',
      width: 120,
      render: (value: string) => (
        <Text type={dayjs(value).isBefore(dayjs(), 'day') ? 'danger' : undefined}>{value}</Text>
      ),
    },
    {
      title: '合同',
      width: 150,
      render: (_, row) =>
        row.contract ? (
          <Space orientation="vertical" size={0}>
            <Text>{row.contract.contract_number}</Text>
            <StatusTag value={row.contract.status} />
          </Space>
        ) : (
          <Text type="secondary">待创建</Text>
        ),
    },
    {
      title: '操作',
      width: 170,
      fixed: 'right',
      render: (_, row) =>
        row.status === 'sent' ? (
          <Space size={4}>
            <Popconfirm
              title="确认接受该报价？"
              onConfirm={() =>
                void runAction(() => portalApi.acceptQuote(row.id), '报价已接受')
              }
            >
              <Button type="link" size="small" icon={<CheckCircleOutlined />}>
                接受
              </Button>
            </Popconfirm>
            <Button
              type="link"
              danger
              size="small"
              onClick={() => {
                rejectForm.resetFields()
                setRejectingQuote(row)
              }}
            >
              拒绝
            </Button>
          </Space>
        ) : (
          <Text type="secondary">-</Text>
        ),
    },
  ]

  const contractColumns: ColumnsType<PortalContract> = [
    {
      title: '合同',
      dataIndex: 'contract_number',
      width: 180,
      render: (value: string, row) => (
        <Space orientation="vertical" size={0}>
          <Text strong>{value}</Text>
          <Text type="secondary">{row.quote_number || '-'} · V{row.version_number || 1}</Text>
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (value: string) => <StatusTag value={value} />,
    },
    {
      title: '金额',
      width: 140,
      render: (_, row) => money(row.total, row.currency),
    },
    {
      title: '签署',
      width: 220,
      render: (_, row) => (
        <Space orientation="vertical" size={0}>
          <Text>客户：{row.customer_signed_at ? dayjs(row.customer_signed_at).format('YYYY-MM-DD HH:mm') : '待签署'}</Text>
          <Text>公司：{row.company_signed_at ? dayjs(row.company_signed_at).format('YYYY-MM-DD HH:mm') : '待签署'}</Text>
        </Space>
      ),
    },
    {
      title: '有效期',
      width: 200,
      render: (_, row) => `${row.effective_from}${row.effective_to ? ` 至 ${row.effective_to}` : ' 起'}`,
    },
    {
      title: '操作',
      width: 190,
      fixed: 'right',
      render: (_, row) => {
        if (row.status === 'pending_signature' && !row.customer_signed_at) {
          return (
            <Button
              type="link"
              size="small"
              onClick={() => {
                signForm.setFieldsValue({ signed_by: agent.contact_name })
                setSigningContract(row)
              }}
            >
              签署合同
            </Button>
          )
        }
        if (row.status === 'active') {
          return (
            <Popconfirm
              title="确认将该合同转换为订单？"
              onConfirm={() =>
                void runAction(
                  () => portalApi.convertContract(row.id),
                  'B2B 订单已创建',
                )
              }
            >
              <Button type="link" size="small" icon={<ShoppingCartOutlined />}>
                转为订单
              </Button>
            </Popconfirm>
          )
        }
        return <Text type="secondary">-</Text>
      },
    },
  ]

  const orderColumns: ColumnsType<PortalOrder> = [
    {
      title: '订单号',
      dataIndex: 'order_number',
      width: 190,
      render: (value: string) => <Text strong>{value}</Text>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (value: string) => <StatusTag value={value} />,
    },
    {
      title: '收款',
      dataIndex: 'payment_status',
      width: 110,
      render: (value: string) => <StatusTag value={value} />,
    },
    {
      title: '金额',
      width: 140,
      render: (_, row) => money(row.total, row.currency),
    },
    {
      title: '账期',
      dataIndex: 'payment_due_date',
      width: 120,
      render: (value: string | null) => value || '-',
    },
    {
      title: '物流',
      width: 180,
      render: (_, row) =>
        row.tracking_number ? `${row.tracking_carrier || ''} ${row.tracking_number}` : '待发货',
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 160,
      render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm'),
    },
  ]

  const productColumns: ColumnsType<PortalProduct> = [
    {
      title: 'SKU',
      dataIndex: 'sku',
      width: 150,
      render: (value: string) => <Text strong>{value}</Text>,
    },
    { title: '商品', dataIndex: 'name' },
    {
      title: '批发价',
      width: 140,
      render: (_, row) => money(row.wholesale_price, row.currency),
    },
    { title: 'MOQ', dataIndex: 'moq', width: 90 },
    {
      title: '库存',
      width: 120,
      render: (_, row) => (
        <Tag color={row.in_stock ? 'green' : 'red'}>
          {row.in_stock ? `${row.stock_quantity} 件` : '缺货'}
        </Tag>
      ),
    },
  ]

  const contentBySection: Record<string, ReactNode> = {
    overview: (
      <Space orientation="vertical" size={18} style={{ width: '100%' }}>
        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} xl={6}>
            <Card variant="borderless">
              <Statistic title="账户等级" value={agent.tier.toUpperCase()} />
            </Card>
          </Col>
          <Col xs={24} sm={12} xl={6}>
            <Card variant="borderless">
              <Statistic title="可用额度" value={agent.available_credit} precision={2} prefix="$" />
            </Card>
          </Col>
          <Col xs={24} sm={12} xl={6}>
            <Card variant="borderless">
              <Statistic title="待付款" value={summary?.pending_payments || 0} precision={2} prefix="$" />
            </Card>
          </Col>
          <Col xs={24} sm={12} xl={6}>
            <Card variant="borderless">
              <Statistic title="订单数" value={summary?.total_orders || 0} />
            </Card>
          </Col>
        </Row>
        <Row gutter={[18, 18]}>
          <Col xs={24} xl={14}>
            <Card variant="borderless" title="待处理报价">
              <Table
                rowKey="id"
                size="small"
                pagination={false}
                dataSource={quotes.filter((quote) => quote.status === 'sent').slice(0, 5)}
                locale={{ emptyText: '当前无待确认报价' }}
                columns={[
                  { title: '报价号', dataIndex: 'quote_number' },
                  {
                    title: '金额',
                    render: (_, row: PortalQuote) => money(row.total, row.currency),
                  },
                  { title: '有效期', dataIndex: 'valid_until' },
                  {
                    title: '状态',
                    dataIndex: 'status',
                    render: (value: string) => <StatusTag value={value} />,
                  },
                ]}
              />
            </Card>
          </Col>
          <Col xs={24} xl={10}>
            <Card variant="borderless" title="账户状态">
              <Descriptions column={1} size="small">
                <Descriptions.Item label="公司">{agent.company_name}</Descriptions.Item>
                <Descriptions.Item label="客户编号">{agent.agent_number}</Descriptions.Item>
                <Descriptions.Item label="信用额度">{money(agent.credit_limit, agent.currency)}</Descriptions.Item>
                <Descriptions.Item label="当前欠款">{money(agent.current_balance, agent.currency)}</Descriptions.Item>
                <Descriptions.Item label="账期">{agent.payment_terms_days} 天</Descriptions.Item>
              </Descriptions>
            </Card>
          </Col>
        </Row>
      </Space>
    ),
    products: (
      <Card variant="borderless" title="商品目录">
        <Table
          rowKey="id"
          loading={loading}
          columns={productColumns}
          dataSource={products}
          scroll={{ x: 760 }}
          pagination={{ pageSize: 20, showSizeChanger: false }}
        />
      </Card>
    ),
    rfqs: (
      <Card
        variant="borderless"
        title="RFQ 询盘"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={openRfqModal}>
            新建 RFQ
          </Button>
        }
      >
        <Table
          rowKey="id"
          loading={loading}
          columns={rfqColumns}
          dataSource={rfqs}
          scroll={{ x: 860 }}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          expandable={{
            expandedRowRender: (row) => (
              <Descriptions column={{ xs: 1, md: 3 }} size="small">
                <Descriptions.Item label="币种">{row.requested_currency}</Descriptions.Item>
                <Descriptions.Item label="目的国家">{row.destination_country || '-'}</Descriptions.Item>
                <Descriptions.Item label="备注" span={3}>{row.notes || '-'}</Descriptions.Item>
              </Descriptions>
            ),
          }}
        />
      </Card>
    ),
    quotes: (
      <Card variant="borderless" title="报价">
        <Table
          rowKey="id"
          loading={loading}
          columns={quoteColumns}
          dataSource={quotes}
          scroll={{ x: 1040 }}
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
                  { title: '数量', dataIndex: 'quantity', width: 90 },
                  {
                    title: '单价',
                    width: 120,
                    render: (_, item) => money(item.unit_price, row.currency),
                  },
                  {
                    title: '小计',
                    width: 120,
                    render: (_, item) => money(item.line_total, row.currency),
                  },
                ]}
              />
            ),
          }}
        />
      </Card>
    ),
    contracts: (
      <Card variant="borderless" title="合同">
        <Table
          rowKey="id"
          loading={loading}
          columns={contractColumns}
          dataSource={contracts}
          scroll={{ x: 1120 }}
          pagination={{ pageSize: 20, showSizeChanger: false }}
        />
      </Card>
    ),
    orders: (
      <Card variant="borderless" title="订单">
        <Table
          rowKey="id"
          loading={loading}
          columns={orderColumns}
          dataSource={orders}
          scroll={{ x: 1120 }}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          expandable={{
            expandedRowRender: (row) => (
              <Table
                rowKey="id"
                size="small"
                pagination={false}
                dataSource={row.items}
                columns={[
                  { title: 'SKU', dataIndex: 'sku', width: 150 },
                  { title: '商品', dataIndex: 'product_name' },
                  { title: '数量', dataIndex: 'quantity', width: 90 },
                  {
                    title: '单价',
                    width: 120,
                    render: (_, item) => money(item.unit_price, row.currency),
                  },
                  {
                    title: '小计',
                    width: 120,
                    render: (_, item) => money(item.subtotal, row.currency),
                  },
                ]}
              />
            ),
          }}
        />
      </Card>
    ),
    account: (
      <Row gutter={[18, 18]}>
        <Col xs={24} xl={14}>
          <Card variant="borderless" title="账户资料">
            <Descriptions column={{ xs: 1, md: 2 }}>
              <Descriptions.Item label="公司">{agent.company_name}</Descriptions.Item>
              <Descriptions.Item label="客户编号">{agent.agent_number}</Descriptions.Item>
              <Descriptions.Item label="联系人">{agent.contact_name}</Descriptions.Item>
              <Descriptions.Item label="邮箱">{agent.email}</Descriptions.Item>
              <Descriptions.Item label="电话">{agent.phone || '-'}</Descriptions.Item>
              <Descriptions.Item label="国家 / 城市">{`${agent.country || '-'} / ${agent.city || '-'}`}</Descriptions.Item>
              <Descriptions.Item label="地址" span={2}>{agent.address || '-'}</Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
        <Col xs={24} xl={10}>
          <Card variant="borderless" title="信用与账期">
            <Row gutter={[16, 16]}>
              <Col span={12}><Statistic title="信用额度" value={agent.credit_limit} precision={2} prefix="$" /></Col>
              <Col span={12}><Statistic title="可用额度" value={agent.available_credit} precision={2} prefix="$" /></Col>
              <Col span={12}><Statistic title="当前欠款" value={agent.current_balance} precision={2} prefix="$" /></Col>
              <Col span={12}><Statistic title="账期" value={agent.payment_terms_days} suffix="天" /></Col>
            </Row>
          </Card>
        </Col>
      </Row>
    ),
  }

  return (
    <div className="portal-shell">
      <header className="portal-topbar">
        <button type="button" className="portal-brand" onClick={() => navigate('/portal')}>
          <span className="portal-mark">N</span>
          <span>
            <strong>Nuotao B2B</strong>
            <small>{agent.company_name}</small>
          </span>
        </button>
        <Space>
          <Tag>{agent.agent_number}</Tag>
          <Button icon={<ReloadOutlined />} onClick={() => void loadPortal()} loading={loading}>
            刷新
          </Button>
          <Button icon={<LogoutOutlined />} onClick={logout}>
            退出
          </Button>
        </Space>
      </header>
      <nav className="portal-navigation">
        {navItems.map((item) => (
          <button
            key={item.key}
            type="button"
            className={section === item.key ? 'is-active' : undefined}
            onClick={() => navigate(item.key === 'overview' ? '/portal' : `/portal/${item.key}`)}
          >
            {item.icon}
            <span>{item.label}</span>
          </button>
        ))}
      </nav>
      <main className="portal-main">
        <div className="portal-heading">
          <div>
            <Text type="secondary">{agent.company_name}</Text>
            <Title level={2}>{navItems.find((item) => item.key === section)?.label || '工作台'}</Title>
          </div>
          <Paragraph>{`${agent.tier.toUpperCase()} · ${agent.payment_terms_days} 天账期 · ${agent.currency}`}</Paragraph>
        </div>
        {error && (
          <Alert
            type="error"
            showIcon
            title="门户数据加载失败"
            description={error}
            className="page-alert"
          />
        )}
        {contentBySection[section] || contentBySection.overview}
      </main>

      <Modal
        open={rfqModalOpen}
        title="新建 RFQ"
        width={820}
        okText="提交"
        confirmLoading={saving}
        onOk={() => void submitRfq()}
        onCancel={() => setRfqModalOpen(false)}
        forceRender
      >
        <Form form={rfqForm} layout="vertical">
          <Space wrap align="start">
            <Form.Item name="requested_currency" label="询价币种">
              <Select
                style={{ width: 110 }}
                options={['USD', 'EUR', 'GBP', 'AUD', 'CAD'].map((value) => ({
                  value,
                  label: value,
                }))}
              />
            </Form.Item>
            <Form.Item name="destination_country" label="目的国家">
              <Input style={{ width: 130 }} placeholder="US / DE" />
            </Form.Item>
            <Form.Item name="incoterm" label="Incoterm">
              <Select
                allowClear
                style={{ width: 120 }}
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
                      style={{ marginBottom: 8, width: 120 }}
                    >
                      <InputNumber min={1} precision={0} placeholder="数量" />
                    </Form.Item>
                    <Form.Item
                      name={[field.name, 'target_unit_price']}
                      style={{ marginBottom: 8, width: 150 }}
                    >
                      <InputNumber min={0.01} precision={2} placeholder="目标单价" />
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
          <Form.Item name="notes" label="备注" style={{ marginTop: 16 }}>
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={Boolean(rejectingQuote)}
        title={`拒绝 ${rejectingQuote?.quote_number || '报价'}`}
        okText="确认拒绝"
        okButtonProps={{ danger: true }}
        confirmLoading={saving}
        onOk={() => void submitRejection()}
        onCancel={() => setRejectingQuote(null)}
        forceRender
      >
        <Form form={rejectForm} layout="vertical">
          <Form.Item
            name="reason"
            label="原因"
            rules={[{ required: true, message: '请输入拒绝原因' }]}
          >
            <Input.TextArea rows={4} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={Boolean(signingContract)}
        title={`签署 ${signingContract?.contract_number || '合同'}`}
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
