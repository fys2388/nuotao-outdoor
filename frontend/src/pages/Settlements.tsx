import { useState, useEffect, useCallback } from 'react'
import {
  Card,
  Table,
  Tag,
  Row,
  Col,
  Statistic,
  Button,
  Space,
  Typography,
  Input,
  Select,
  Form,
  DatePicker,
  InputNumber,
  message,
} from 'antd'
import {
  PlusOutlined,
  AccountBookOutlined,
  DollarOutlined,
  WarningOutlined,
  CheckCircleOutlined,
  SyncOutlined,
} from '@ant-design/icons'

const { Title, Text } = Typography
const { TextArea } = Input

const statusColors: Record<string, string> = {
  expected: 'orange',
  partial: 'blue',
  received: 'green',
  disputed: 'red',
}

const statusLabels: Record<string, string> = {
  expected: '待收',
  partial: '部分回款',
  received: '已收',
  disputed: '争议',
}

const kindLabels: Record<string, string> = {
  cod: 'COD 回款',
  clearance: '清关',
  fee: '杂费',
  refund: '退款',
}

interface SettlementItem {
  id: string
  external_order_id?: string | null
  carrier: string
  settlement_kind: string
  expected_amount: string
  received_amount: string
  fees: string
  currency: string
  status: string
  due_date?: string | null
  received_at?: string | null
  note?: string | null
  created_at?: string | null
}

interface StatsData {
  totals: {
    entries: number
    expected_amount: string
    received_amount: string
    pending_amount: string
  }
  by_status: Record<string, { count: number; expected_amount: string; received_amount: string; pending_amount: string }>
  by_carrier: Record<string, { count: number; expected_amount: string; received_amount: string; pending_amount: string }>
}

export default function SettlementsPage() {
  const [items, setItems] = useState<SettlementItem[]>([])
  const [stats, setStats] = useState<StatsData | null>(null)
  const [loading, setLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [carrierFilter, setCarrierFilter] = useState<string>('')
  const [showForm, setShowForm] = useState(false)
  const [form] = Form.useForm()

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/settlements/stats')
      if (res.ok) {
        setStats(await res.json())
      }
    } catch {
      // 静默失败
    }
  }, [])

  const fetchList = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ limit: '200' })
      if (statusFilter) params.set('status', statusFilter)
      if (carrierFilter) params.set('carrier', carrierFilter)
      const res = await fetch(`/api/v1/settlements?${params.toString()}`)
      if (res.ok) {
        const data = await res.json()
        setItems(data.items || [])
      }
    } catch {
      // 静默失败
    } finally {
      setLoading(false)
    }
  }, [statusFilter, carrierFilter])

  useEffect(() => {
    fetchList()
    fetchStats()
  }, [fetchList, fetchStats])

  const handleRegister = async () => {
    try {
      const values = await form.validateFields()
      const payload: Record<string, unknown> = {
        carrier: values.carrier,
        expected_amount: String(values.expected_amount),
        settlement_kind: values.settlement_kind || 'cod',
        currency: 'USD',
        note: values.note || null,
      }
      if (values.external_order_id) payload.external_order_id = values.external_order_id
      if (values.due_date) payload.due_date = values.due_date.format('YYYY-MM-DD')
      if (values.fees) payload.fees = String(values.fees)
      const res = await fetch('/api/v1/settlements', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (res.ok) {
        message.success('回款登记成功')
        setShowForm(false)
        form.resetFields()
        fetchList()
        fetchStats()
      } else {
        const err = await res.json().catch(() => null)
        message.error(err?.detail || '登记失败')
      }
    } catch {
      // 表单校验失败
    }
  }

  const handleReceipt = async (item: SettlementItem) => {
    const input = window.prompt(
      `登记实收（${item.carrier} 应回款 ${item.expected_amount} ${item.currency}）\n格式：实收金额 扣费（可选），如 115.5 4.5`,
    )
    if (input === null || input.trim() === '') return
    const parts = input.trim().split(/\s+/)
    const received = parts[0]
    const fees = parts[1]
    try {
      const payload: Record<string, unknown> = { received_amount: received }
      if (fees) payload.fees = fees
      const res = await fetch(`/api/v1/settlements/${item.id}/receipt`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (res.ok) {
        message.success('实收登记成功')
        fetchList()
        fetchStats()
      } else {
        const err = await res.json().catch(() => null)
        message.error(err?.detail || '登记失败')
      }
    } catch {
      message.error('登记失败')
    }
  }

  const handleDispute = async (item: SettlementItem) => {
    const note = window.prompt('争议说明（将保留在待追讨列表）')
    if (note === null) return
    const res = await fetch(`/api/v1/settlements/${item.id}/dispute?note=${encodeURIComponent(note || '')}`, {
      method: 'POST',
    })
    if (res.ok) {
      message.success('已标记争议')
      fetchList()
      fetchStats()
    }
  }

  const pendingAmount = stats?.totals?.pending_amount ?? '0.00'
  const receivedAmount = stats?.totals?.received_amount ?? '0.00'
  const disputedCount = stats?.by_status?.disputed?.count ?? 0

  const columns = [
    {
      title: '渠道',
      dataIndex: 'carrier',
      key: 'carrier',
      render: (v: string) => <Text strong>{v}</Text>,
    },
    {
      title: '类型',
      dataIndex: 'settlement_kind',
      key: 'kind',
      width: 100,
      render: (v: string) => <Tag>{kindLabels[v] || v}</Tag>,
    },
    {
      title: '外部单号',
      dataIndex: 'external_order_id',
      key: 'order',
      render: (v?: string | null) => v || '—',
    },
    {
      title: '应回款',
      dataIndex: 'expected_amount',
      key: 'expected',
      align: 'right' as const,
      render: (v: string, r: SettlementItem) => `${v} ${r.currency}`,
    },
    {
      title: '实收',
      dataIndex: 'received_amount',
      key: 'received',
      align: 'right' as const,
    },
    {
      title: '扣费',
      dataIndex: 'fees',
      key: 'fees',
      align: 'right' as const,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (v: string) => <Tag color={statusColors[v] || 'default'}>{statusLabels[v] || v}</Tag>,
    },
    {
      title: '备注',
      dataIndex: 'note',
      key: 'note',
      ellipsis: true,
      render: (v?: string | null) => v || '—',
    },
    {
      title: '操作',
      key: 'action',
      width: 160,
      render: (_: unknown, r: SettlementItem) => (
        <Space size="small">
          {r.status !== 'received' && r.status !== 'disputed' && (
            <Button size="small" type="primary" onClick={() => handleReceipt(r)}>
              登记实收
            </Button>
          )}
          {r.status !== 'disputed' && r.status !== 'received' && (
            <Button size="small" danger onClick={() => handleDispute(r)}>
              争议
            </Button>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Title level={4}>
        <AccountBookOutlined /> 回款台账
      </Title>
      <Text type="secondary">
        COD 回款、清关账单等资金流登记与对账——待收 / 已收 / 争议金额可查、可审计（数据源：settlements 台账）
      </Text>

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col xs={24} sm={12} md={6}>
          <Card size="small">
            <Statistic
              title="待回款"
              value={Number(pendingAmount)}
              precision={2}
              prefix={<DollarOutlined style={{ color: '#FAAD14' }} />}
              suffix="USD"
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card size="small">
            <Statistic
              title="已回款"
              value={Number(receivedAmount)}
              precision={2}
              prefix={<CheckCircleOutlined style={{ color: '#52C41A' }} />}
              suffix="USD"
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card size="small">
            <Statistic
              title="争议中"
              value={disputedCount}
              prefix={<WarningOutlined style={{ color: '#EA6668' }} />}
              suffix="笔"
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card size="small">
            <Statistic
              title="台账笔数"
              value={stats?.totals?.entries ?? 0}
              suffix="笔"
            />
          </Card>
        </Col>
      </Row>

      <Card
        size="small"
        style={{ marginTop: 16 }}
        title="筛选与登记"
        extra={
          <Space>
            <Select
              placeholder="状态"
              allowClear
              style={{ width: 120 }}
              value={statusFilter || undefined}
              onChange={(v) => setStatusFilter(v || '')}
              options={Object.entries(statusLabels).map(([k, v]) => ({ value: k, label: v }))}
            />
            <Select
              placeholder="渠道"
              allowClear
              style={{ width: 150 }}
              value={carrierFilter || undefined}
              onChange={(v) => setCarrierFilter(v || '')}
              options={[
                { value: 'correos', label: 'correos' },
                { value: 'clearance_hungary', label: 'clearance_hungary' },
                { value: 'stripe', label: 'stripe' },
                { value: 'paypal', label: 'paypal' },
              ]}
            />
            <Button icon={<SyncOutlined />} onClick={() => { fetchList(); fetchStats() }}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setShowForm(!showForm)}>
              {showForm ? '收起登记' : '登记回款'}
            </Button>
          </Space>
        }
      >
        {showForm && (
          <Form
            form={form}
            layout="inline"
            style={{ marginBottom: 16, rowGap: 12 }}
            onFinish={handleRegister}
          >
            <Form.Item name="carrier" label="渠道" rules={[{ required: true, message: '必填' }]}>
              <Input placeholder="correos / clearance_hungary" style={{ width: 180 }} />
            </Form.Item>
            <Form.Item name="settlement_kind" label="类型" initialValue="cod">
              <Select
                style={{ width: 130 }}
                options={Object.entries(kindLabels).map(([k, v]) => ({ value: k, label: v }))}
              />
            </Form.Item>
            <Form.Item name="expected_amount" label="应回款" rules={[{ required: true, message: '必填' }]}>
              <InputNumber min={0} precision={2} style={{ width: 120 }} />
            </Form.Item>
            <Form.Item name="fees" label="扣费">
              <InputNumber min={0} precision={2} style={{ width: 100 }} />
            </Form.Item>
            <Form.Item name="external_order_id" label="外部单号">
              <Input style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="due_date" label="应回款日">
              <DatePicker style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="note" label="备注">
              <TextArea rows={1} style={{ width: 180 }} />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit">
                保存
              </Button>
            </Form.Item>
          </Form>
        )}
        <Table
          rowKey="id"
          columns={columns}
          dataSource={items}
          loading={loading}
          size="small"
          pagination={{ pageSize: 20, showSizeChanger: false }}
          scroll={{ x: 900 }}
        />
      </Card>
    </div>
  )
}
