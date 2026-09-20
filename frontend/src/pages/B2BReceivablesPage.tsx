import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  CheckCircleOutlined,
  DollarOutlined,
  FileTextOutlined,
  PlusOutlined,
  ReloadOutlined,
  WalletOutlined,
} from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'
import { api, ApiError } from '../api/client'

const { Title, Text } = Typography

interface AgentRecord {
  id: string
  agent_number: string
  company_name: string
  currency: string
}

interface OrderRecord {
  id: string
  order_number: string
  agent_id: string
  agent_company: string
  currency: string
  total: number
  payment_status: string
}

interface Invoice {
  id: string
  invoice_number: string
  order_id: string
  order_number: string
  agent_id: string
  agent_company: string
  status: string
  effective_status: string
  currency: string
  issue_date: string
  due_date: string
  subtotal: number
  discount_amount: number
  shipping_amount: number
  tax_amount: number
  total: number
  amount_paid: number
  amount_written_off: number
  balance_due: number
  age_days: number
  aging_bucket: string
  notes: string | null
  created_at: string
}

interface ReceiptAllocation {
  id: string
  invoice_id: string
  invoice_number: string
  amount: number
  currency: string
  occurred_at: string
  description: string | null
}

interface Receipt {
  id: string
  receipt_number: string
  agent_id: string
  agent_company: string
  status: string
  amount: number
  unapplied_amount: number
  currency: string
  received_at: string
  payment_method: string
  bank_reference: string | null
  idempotency_key: string
  notes: string | null
  allocations: ReceiptAllocation[]
  created_at: string
}

interface AgingBucket {
  count: number
  amount: number
}

interface ReceivableStats {
  as_of: string
  invoice_count: number
  open_invoice_count: number
  overdue_invoice_count: number
  outstanding_amount: number
  overdue_amount: number
  paid_amount: number
  written_off_amount: number
  aging: Record<string, AgingBucket>
}

interface ListResponse<T> {
  items: T[]
  total: number
}

const invoiceStatus: Record<string, { color: string; label: string }> = {
  draft: { color: 'default', label: '草稿' },
  issued: { color: 'blue', label: '已开票' },
  partially_paid: { color: 'orange', label: '部分收款' },
  paid: { color: 'green', label: '已收清' },
  overdue: { color: 'red', label: '已逾期' },
  written_off: { color: 'purple', label: '已核销' },
  void: { color: 'default', label: '已作废' },
}

const receiptStatus: Record<string, { color: string; label: string }> = {
  unapplied: { color: 'orange', label: '待核销' },
  partially_applied: { color: 'blue', label: '部分核销' },
  applied: { color: 'green', label: '已核销' },
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

function makeIdempotencyKey(prefix: string): string {
  const random =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`
  return `${prefix}-${random}`
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

export default function B2BReceivablesPage() {
  const [activeTab, setActiveTab] = useState('invoices')
  const [agents, setAgents] = useState<AgentRecord[]>([])
  const [orders, setOrders] = useState<OrderRecord[]>([])
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [receipts, setReceipts] = useState<Receipt[]>([])
  const [receivables, setReceivables] = useState<Invoice[]>([])
  const [stats, setStats] = useState<ReceivableStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [invoiceModalOpen, setInvoiceModalOpen] = useState(false)
  const [receiptModalOpen, setReceiptModalOpen] = useState(false)
  const [allocatingReceipt, setAllocatingReceipt] = useState<Receipt | null>(null)
  const [writeOffInvoice, setWriteOffInvoice] = useState<Invoice | null>(null)

  const [invoiceForm] = Form.useForm()
  const [receiptForm] = Form.useForm()
  const [allocationForm] = Form.useForm()
  const [writeOffForm] = Form.useForm()

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [
        invoiceResponse,
        receiptResponse,
        receivableResponse,
        statsResponse,
        agentResponse,
        orderResponse,
      ] = await Promise.all([
        api.getB2BInvoices(1, 200) as Promise<ListResponse<Invoice>>,
        api.getB2BReceipts(1, 200) as Promise<ListResponse<Receipt>>,
        api.getB2BReceivables() as Promise<ListResponse<Invoice>>,
        api.getB2BReceivableStats() as Promise<ReceivableStats>,
        api.getB2BAgents() as Promise<ListResponse<AgentRecord>>,
        api.getB2BOrders() as Promise<ListResponse<OrderRecord>>,
      ])
      setInvoices(invoiceResponse.items || [])
      setReceipts(receiptResponse.items || [])
      setReceivables(receivableResponse.items || [])
      setStats(statsResponse)
      setAgents(agentResponse.items || [])
      setOrders(orderResponse.items || [])
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }, [])

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

  const invoicedOrderIds = useMemo(
    () => new Set(invoices.map((invoice) => invoice.order_id)),
    [invoices],
  )
  const orderOptions = useMemo(
    () =>
      orders
        .filter((order) => !invoicedOrderIds.has(order.id))
        .map((order) => ({
          value: order.id,
          label: `${order.order_number} · ${order.agent_company || order.agent_id} · ${formatMoney(order.total, order.currency)}`,
        })),
    [invoicedOrderIds, orders],
  )
  const agentOptions = useMemo(
    () =>
      agents.map((agent) => ({
        value: agent.id,
        label: `${agent.company_name} · ${agent.agent_number}`,
      })),
    [agents],
  )
  const allocationInvoiceOptions = useMemo(() => {
    if (!allocatingReceipt) return []
    return receivables
      .filter(
        (invoice) =>
          invoice.agent_id === allocatingReceipt.agent_id &&
          invoice.currency === allocatingReceipt.currency,
      )
      .map((invoice) => ({
        value: invoice.id,
        label: `${invoice.invoice_number} · 待收 ${formatMoney(invoice.balance_due, invoice.currency)}`,
      }))
  }, [allocatingReceipt, receivables])

  const openInvoiceModal = () => {
    invoiceForm.resetFields()
    invoiceForm.setFieldsValue({ issue_date: dayjs() })
    setInvoiceModalOpen(true)
  }

  const submitInvoice = async () => {
    const values = await invoiceForm.validateFields()
    await runAction(
      () =>
        api.createB2BInvoice({
          order_id: values.order_id,
          issue_date: (values.issue_date as Dayjs).format('YYYY-MM-DD'),
          due_date: values.due_date
            ? (values.due_date as Dayjs).format('YYYY-MM-DD')
            : null,
          notes: values.notes,
        }),
      '发票草稿已创建',
    )
    setInvoiceModalOpen(false)
  }

  const openReceiptModal = () => {
    receiptForm.resetFields()
    receiptForm.setFieldsValue({
      currency: 'USD',
      received_at: dayjs(),
      payment_method: 'bank_transfer',
      idempotency_key: makeIdempotencyKey('receipt'),
    })
    setReceiptModalOpen(true)
  }

  const submitReceipt = async () => {
    const values = await receiptForm.validateFields()
    await runAction(
      () =>
        api.createB2BReceipt({
          agent_id: values.agent_id,
          amount: values.amount,
          currency: values.currency,
          idempotency_key: values.idempotency_key,
          received_at: (values.received_at as Dayjs).toISOString(),
          payment_method: values.payment_method,
          bank_reference: values.bank_reference,
          notes: values.notes,
        }),
      '收款已登记',
    )
    setReceiptModalOpen(false)
    setActiveTab('receipts')
  }

  const openAllocationModal = (receipt: Receipt) => {
    allocationForm.resetFields()
    allocationForm.setFieldsValue({
      amount: receipt.unapplied_amount,
      idempotency_key: makeIdempotencyKey('allocation'),
    })
    setAllocatingReceipt(receipt)
  }

  const submitAllocation = async () => {
    if (!allocatingReceipt) return
    const values = await allocationForm.validateFields()
    await runAction(
      () =>
        api.allocateB2BReceipt(allocatingReceipt.id, {
          invoice_id: values.invoice_id,
          amount: values.amount,
          idempotency_key: values.idempotency_key,
          notes: values.notes,
        }),
      '收款核销完成',
    )
    setAllocatingReceipt(null)
  }

  const openWriteOffModal = (invoice: Invoice) => {
    writeOffForm.resetFields()
    writeOffForm.setFieldsValue({
      amount: invoice.balance_due,
      idempotency_key: makeIdempotencyKey('writeoff'),
    })
    setWriteOffInvoice(invoice)
  }

  const submitWriteOff = async () => {
    if (!writeOffInvoice) return
    const values = await writeOffForm.validateFields()
    await runAction(
      () =>
        api.writeOffB2BInvoice(writeOffInvoice.id, {
          amount: values.amount,
          idempotency_key: values.idempotency_key,
          reason: values.reason,
        }),
      '坏账核销已入账',
    )
    setWriteOffInvoice(null)
  }

  const invoiceColumns: ColumnsType<Invoice> = [
    {
      title: '发票',
      fixed: 'left',
      width: 190,
      render: (_, row) => (
        <Space orientation="vertical" size={0}>
          <Text strong>{row.invoice_number}</Text>
          <Text type="secondary">{row.order_number || row.order_id}</Text>
        </Space>
      ),
    },
    { title: '客户', dataIndex: 'agent_company', width: 180 },
    {
      title: '状态',
      width: 110,
      render: (_, row) => (
        <StatusTag value={row.effective_status} labels={invoiceStatus} />
      ),
    },
    {
      title: '开票 / 到期',
      width: 150,
      render: (_, row) => (
        <Space orientation="vertical" size={0}>
          <Text>{row.issue_date}</Text>
          <Text type={row.effective_status === 'overdue' ? 'danger' : 'secondary'}>
            到期 {row.due_date}
          </Text>
        </Space>
      ),
    },
    {
      title: '发票金额',
      width: 130,
      align: 'right',
      render: (_, row) => formatMoney(row.total, row.currency),
    },
    {
      title: '已收',
      width: 120,
      align: 'right',
      render: (_, row) => formatMoney(row.amount_paid, row.currency),
    },
    {
      title: '未收',
      width: 120,
      align: 'right',
      render: (_, row) => (
        <Text strong type={row.balance_due > 0 ? 'warning' : 'success'}>
          {formatMoney(row.balance_due, row.currency)}
        </Text>
      ),
    },
    {
      title: '操作',
      fixed: 'right',
      width: 140,
      render: (_, row) =>
        row.status === 'draft' ? (
          <Button
            type="link"
            size="small"
            icon={<CheckCircleOutlined />}
            onClick={() =>
              void runAction(
                () => api.issueB2BInvoice(row.id),
                '发票已正式开出',
              )
            }
          >
            开票
          </Button>
        ) : (
          <Text type="secondary">-</Text>
        ),
    },
  ]

  const receiptColumns: ColumnsType<Receipt> = [
    {
      title: '收款单',
      fixed: 'left',
      width: 190,
      render: (_, row) => (
        <Space orientation="vertical" size={0}>
          <Text strong>{row.receipt_number}</Text>
          <Text type="secondary">
            {dayjs(row.received_at).format('YYYY-MM-DD HH:mm')}
          </Text>
        </Space>
      ),
    },
    { title: '客户', dataIndex: 'agent_company', width: 180 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (value: string) => <StatusTag value={value} labels={receiptStatus} />,
    },
    {
      title: '收款金额',
      width: 130,
      align: 'right',
      render: (_, row) => (
        <Text strong>{formatMoney(row.amount, row.currency)}</Text>
      ),
    },
    {
      title: '待核销',
      width: 130,
      align: 'right',
      render: (_, row) => formatMoney(row.unapplied_amount, row.currency),
    },
    {
      title: '方式',
      dataIndex: 'payment_method',
      width: 130,
    },
    {
      title: '银行流水',
      dataIndex: 'bank_reference',
      width: 160,
      render: (value: string | null) => value || '-',
    },
    {
      title: '操作',
      fixed: 'right',
      width: 120,
      render: (_, row) =>
        row.unapplied_amount > 0 ? (
          <Button type="link" size="small" onClick={() => openAllocationModal(row)}>
            核销
          </Button>
        ) : (
          <Text type="secondary">已核销</Text>
        ),
    },
  ]

  const receivableColumns: ColumnsType<Invoice> = [
    {
      title: '发票',
      fixed: 'left',
      width: 190,
      render: (_, row) => (
        <Space orientation="vertical" size={0}>
          <Text strong>{row.invoice_number}</Text>
          <Text type="secondary">{row.order_number || row.order_id}</Text>
        </Space>
      ),
    },
    { title: '客户', dataIndex: 'agent_company', width: 190 },
    {
      title: '到期日',
      dataIndex: 'due_date',
      width: 110,
    },
    {
      title: '逾期',
      width: 120,
      render: (_, row) =>
        row.age_days > 0 ? (
          <Tag color={row.age_days > 90 ? 'red' : 'orange'}>
            {row.age_days} 天
          </Tag>
        ) : (
          <Tag color="green">未逾期</Tag>
        ),
    },
    {
      title: '账龄桶',
      dataIndex: 'aging_bucket',
      width: 100,
    },
    {
      title: '应收余额',
      width: 140,
      align: 'right',
      render: (_, row) => (
        <Text strong>{formatMoney(row.balance_due, row.currency)}</Text>
      ),
    },
    {
      title: '操作',
      fixed: 'right',
      width: 130,
      render: (_, row) => (
        <Button type="link" danger size="small" onClick={() => openWriteOffModal(row)}>
          坏账核销
        </Button>
      ),
    },
  ]

  const tabItems = [
    {
      key: 'invoices',
      label: (
        <Space>
          <FileTextOutlined />
          发票
        </Space>
      ),
      children: (
        <>
          <div className="table-toolbar">
            <Text type="secondary">共 {invoices.length} 张发票</Text>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={openInvoiceModal}
              disabled={orderOptions.length === 0}
            >
              创建发票
            </Button>
          </div>
          <Table
            rowKey="id"
            loading={loading}
            columns={invoiceColumns}
            dataSource={invoices}
            scroll={{ x: 1250 }}
            pagination={{ pageSize: 20, showSizeChanger: false }}
            expandable={{
              expandedRowRender: (row) => (
                <Descriptions size="small" column={{ xs: 1, md: 4 }}>
                  <Descriptions.Item label="商品小计">
                    {formatMoney(row.subtotal, row.currency)}
                  </Descriptions.Item>
                  <Descriptions.Item label="折扣">
                    {formatMoney(row.discount_amount, row.currency)}
                  </Descriptions.Item>
                  <Descriptions.Item label="运费">
                    {formatMoney(row.shipping_amount, row.currency)}
                  </Descriptions.Item>
                  <Descriptions.Item label="税费">
                    {formatMoney(row.tax_amount, row.currency)}
                  </Descriptions.Item>
                  <Descriptions.Item label="已核销">
                    {formatMoney(row.amount_written_off, row.currency)}
                  </Descriptions.Item>
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
      key: 'receipts',
      label: (
        <Space>
          <DollarOutlined />
          收款
        </Space>
      ),
      children: (
        <>
          <div className="table-toolbar">
            <Text type="secondary">共 {receipts.length} 笔收款</Text>
            <Button type="primary" icon={<PlusOutlined />} onClick={openReceiptModal}>
              登记收款
            </Button>
          </div>
          <Table
            rowKey="id"
            loading={loading}
            columns={receiptColumns}
            dataSource={receipts}
            scroll={{ x: 1180 }}
            pagination={{ pageSize: 20, showSizeChanger: false }}
            expandable={{
              expandedRowRender: (row) => (
                <Table
                  rowKey="id"
                  size="small"
                  pagination={false}
                  dataSource={row.allocations}
                  locale={{ emptyText: '该收款尚未核销' }}
                  columns={[
                    {
                      title: '发票',
                      dataIndex: 'invoice_number',
                      width: 180,
                    },
                    {
                      title: '核销金额',
                      width: 130,
                      render: (_, item: ReceiptAllocation) =>
                        formatMoney(item.amount, item.currency),
                    },
                    {
                      title: '核销时间',
                      dataIndex: 'occurred_at',
                      width: 170,
                      render: (value: string) =>
                        dayjs(value).format('YYYY-MM-DD HH:mm'),
                    },
                    { title: '说明', dataIndex: 'description' },
                  ]}
                />
              ),
            }}
          />
        </>
      ),
    },
    {
      key: 'receivables',
      label: (
        <Space>
          <WalletOutlined />
          应收账龄
        </Space>
      ),
      children: (
        <>
          <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
            {(['current', '0-30', '31-60', '61-90', '90+'] as const).map((key) => {
              const bucket = stats?.aging?.[key] || { count: 0, amount: 0 }
              return (
                <Col xs={12} md={8} xl={4} key={key}>
                  <Card size="small" variant="borderless">
                    <Statistic
                      title={key === 'current' ? '未到期' : `${key} 天`}
                      value={bucket.amount}
                      precision={2}
                      prefix="$"
                    />
                    <Text type="secondary">{bucket.count} 张发票</Text>
                  </Card>
                </Col>
              )
            })}
          </Row>
          <Table
            rowKey="id"
            loading={loading}
            columns={receivableColumns}
            dataSource={receivables}
            scroll={{ x: 1150 }}
            pagination={{ pageSize: 20, showSizeChanger: false }}
          />
        </>
      ),
    },
  ]

  return (
    <div className="dashboard-page">
      <div className="page-heading">
        <div>
          <div className="page-kicker page-kicker--b2b">B2B RECEIVABLES</div>
          <Title level={2}>发票、收款与应收账款</Title>
          <p>发票、银行收款、逐笔核销、账龄和坏账处理共享一套可审计账簿。</p>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
          刷新
        </Button>
      </div>

      {error && (
        <Alert
          type="error"
          showIcon
          title="应收数据加载失败"
          description={error}
          className="page-alert"
        />
      )}

      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} xl={6}>
          <Card variant="borderless">
            <Statistic
              title="应收余额"
              value={stats?.outstanding_amount ?? 0}
              precision={2}
              prefix="$"
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <Card variant="borderless">
            <Statistic
              title="逾期余额"
              value={stats?.overdue_amount ?? 0}
              precision={2}
              prefix="$"
              styles={{ content: { color: (stats?.overdue_amount ?? 0) > 0 ? '#b42318' : undefined } }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <Card variant="borderless">
            <Statistic title="未结发票" value={stats?.open_invoice_count ?? 0} />
          </Card>
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <Card variant="borderless">
            <Statistic
              title="累计收款"
              value={stats?.paid_amount ?? 0}
              precision={2}
              prefix="$"
            />
          </Card>
        </Col>
      </Row>

      <Card variant="borderless">
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} />
      </Card>

      <Modal
        open={invoiceModalOpen}
        title="创建 B2B 发票"
        okText="创建草稿"
        confirmLoading={saving}
        onOk={() => void submitInvoice()}
        onCancel={() => setInvoiceModalOpen(false)}
        forceRender
      >
        <Form form={invoiceForm} layout="vertical">
          <Form.Item
            name="order_id"
            label="B2B 订单"
            rules={[{ required: true, message: '请选择订单' }]}
          >
            <Select
              showSearch
              optionFilterProp="label"
              options={orderOptions}
              placeholder="选择尚未开票的 B2B 订单"
            />
          </Form.Item>
          <Space wrap align="start">
            <Form.Item
              name="issue_date"
              label="开票日期"
              rules={[{ required: true }]}
            >
              <DatePicker />
            </Form.Item>
            <Form.Item name="due_date" label="到期日期">
              <DatePicker />
            </Form.Item>
          </Space>
          <Form.Item name="notes" label="备注">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={receiptModalOpen}
        title="登记 B2B 收款"
        okText="登记"
        confirmLoading={saving}
        onOk={() => void submitReceipt()}
        onCancel={() => setReceiptModalOpen(false)}
        forceRender
      >
        <Form form={receiptForm} layout="vertical">
          <Form.Item
            name="agent_id"
            label="客户"
            rules={[{ required: true, message: '请选择客户' }]}
          >
            <Select
              showSearch
              optionFilterProp="label"
              options={agentOptions}
              placeholder="选择付款客户"
            />
          </Form.Item>
          <Space wrap align="start">
            <Form.Item
              name="amount"
              label="实收金额"
              rules={[{ required: true, message: '请输入金额' }]}
            >
              <InputNumber min={0.01} precision={2} style={{ width: 180 }} />
            </Form.Item>
            <Form.Item name="currency" label="币种">
              <Select
                style={{ width: 110 }}
                options={['USD', 'EUR', 'GBP', 'AUD', 'CAD'].map((value) => ({
                  value,
                  label: value,
                }))}
              />
            </Form.Item>
            <Form.Item
              name="received_at"
              label="到账时间"
              rules={[{ required: true }]}
            >
              <DatePicker showTime />
            </Form.Item>
          </Space>
          <Space wrap align="start">
            <Form.Item name="payment_method" label="收款方式">
              <Select
                style={{ width: 160 }}
                options={[
                  { value: 'bank_transfer', label: '银行转账' },
                  { value: 'wire', label: '电汇' },
                  { value: 'credit_card', label: '信用卡' },
                  { value: 'paypal', label: 'PayPal' },
                  { value: 'other', label: '其他' },
                ]}
              />
            </Form.Item>
            <Form.Item name="bank_reference" label="银行流水号">
              <Input style={{ width: 260 }} />
            </Form.Item>
          </Space>
          <Form.Item
            name="idempotency_key"
            label="幂等键"
            rules={[{ required: true, message: '请输入幂等键' }]}
          >
            <Input />
          </Form.Item>
          <Form.Item name="notes" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={Boolean(allocatingReceipt)}
        title={`核销 ${allocatingReceipt?.receipt_number || '收款'}`}
        okText="确认核销"
        confirmLoading={saving}
        onOk={() => void submitAllocation()}
        onCancel={() => setAllocatingReceipt(null)}
        forceRender
      >
        <Alert
          type="info"
          showIcon
          title={`待核销 ${formatMoney(
            allocatingReceipt?.unapplied_amount ?? 0,
            allocatingReceipt?.currency || 'USD',
          )}`}
          style={{ marginBottom: 16 }}
        />
        {allocationInvoiceOptions.length === 0 ? (
          <Alert
            type="warning"
            showIcon
            title="当前客户没有同币种未结发票"
          />
        ) : (
          <Form form={allocationForm} layout="vertical">
            <Form.Item
              name="invoice_id"
              label="目标发票"
              rules={[{ required: true, message: '请选择发票' }]}
            >
              <Select
                showSearch
                optionFilterProp="label"
                options={allocationInvoiceOptions}
              />
            </Form.Item>
            <Form.Item
              name="amount"
              label="核销金额"
              rules={[{ required: true, message: '请输入金额' }]}
            >
              <InputNumber min={0.01} precision={2} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item
              name="idempotency_key"
              label="幂等键"
              rules={[{ required: true, message: '请输入幂等键' }]}
            >
              <Input />
            </Form.Item>
            <Form.Item name="notes" label="说明">
              <Input.TextArea rows={2} />
            </Form.Item>
          </Form>
        )}
      </Modal>

      <Modal
        open={Boolean(writeOffInvoice)}
        title={`坏账核销 ${writeOffInvoice?.invoice_number || ''}`}
        okText="确认核销"
        okButtonProps={{ danger: true }}
        confirmLoading={saving}
        onOk={() => void submitWriteOff()}
        onCancel={() => setWriteOffInvoice(null)}
        forceRender
      >
        <Alert
          type="warning"
          showIcon
          title="坏账核销会减少客户应收余额并保留不可变账本记录。"
          style={{ marginBottom: 16 }}
        />
        <Form form={writeOffForm} layout="vertical">
          <Form.Item
            name="amount"
            label="核销金额"
            rules={[{ required: true, message: '请输入金额' }]}
          >
            <InputNumber min={0.01} precision={2} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="idempotency_key"
            label="幂等键"
            rules={[{ required: true, message: '请输入幂等键' }]}
          >
            <Input />
          </Form.Item>
          <Form.Item
            name="reason"
            label="核销原因"
            rules={[{ required: true, message: '请输入原因' }]}
          >
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
