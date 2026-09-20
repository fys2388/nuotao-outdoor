import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Divider,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Row,
  Segmented,
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
  DollarOutlined,
  EditOutlined,
  LineChartOutlined,
  ReloadOutlined,
  SearchOutlined,
  WalletOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { api, ApiError } from '../api/client'

const { Title, Text, Paragraph } = Typography

interface CostRow {
  product_id: string
  sku: string
  name: string
  category: string | null
  target_market: string
  status: string
  has_cost: boolean
  currency: string | null
  version: string | null
  valid_from: string | null
  sale_price: string | null
  purchase_cost: string
  domestic_shipping: string
  first_leg_shipping: string
  last_leg_shipping: string
  international_shipping: string
  packaging: string
  tax_estimate: string
  handling: string
  payment_fee: string
  marketing_amortization: string
  after_sales_loss: string
  total_landed_cost: string
  period_cost: string
  contribution_margin: string | null
  margin_rate: string | null
}

interface CostOverview {
  items: CostRow[]
  total: number
  known: number
  missing: number
}

interface ProfitAnalysis {
  product_id: string
  sku: string
  name: string
  currency: string
  cost_status: 'KNOWN' | 'MISSING'
  version: string | null
  valid_from: string | null
  sale_price: string | null
  total_landed_cost: string
  payment_fee: string
  marketing_amortization: string
  after_sales_loss: string
  period_cost: string
  total_cost: string | null
  contribution_margin: string | null
  contribution_margin_rate: string | null
  markup_rate: string | null
  breakeven_price: string
}

type CostFilter = 'all' | 'known' | 'missing'

const COST_FIELDS = [
  { name: 'purchase_cost', label: '采购成本', required: true },
  { name: 'domestic_shipping', label: '国内段运费' },
  { name: 'first_leg_shipping', label: '头程运费' },
  { name: 'last_leg_shipping', label: '尾程运费' },
  { name: 'international_shipping', label: '国际段运费（留空=头程+尾程）' },
  { name: 'packaging', label: '包装费' },
  { name: 'tax_estimate', label: '关税/税费' },
  { name: 'handling', label: '处理费' },
] as const

const PERIOD_FIELDS = [
  { name: 'payment_fee', label: '支付手续费' },
  { name: 'marketing_amortization', label: '营销摊销' },
  { name: 'after_sales_loss', label: '售后损失' },
] as const

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

function money(value: unknown, currency = 'USD'): string {
  return `${currency} ${numeric(value).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

function marginColor(rate: string | null): string {
  if (rate === null || rate === undefined) return 'default'
  const value = numeric(rate)
  if (value >= 0.3) return 'green'
  if (value >= 0.1) return 'orange'
  return 'red'
}

export default function ProductCostsPage() {
  const [rows, setRows] = useState<CostRow[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<CostFilter>('all')
  const [coverage, setCoverage] = useState({ total: 0, known: 0, missing: 0 })

  const [editOpen, setEditOpen] = useState(false)
  const [editSaving, setEditSaving] = useState(false)
  const [editRow, setEditRow] = useState<CostRow | null>(null)
  const [costForm] = Form.useForm()
  const watched = Form.useWatch([], costForm) as Record<string, number | null> | undefined

  const [profitOpen, setProfitOpen] = useState(false)
  const [profitLoading, setProfitLoading] = useState(false)
  const [profitRow, setProfitRow] = useState<CostRow | null>(null)
  const [profit, setProfit] = useState<ProfitAnalysis | null>(null)
  const [whatIf, setWhatIf] = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.getCostOverview({ limit: 200 })
      const overview = data as CostOverview
      setRows(overview.items ?? [])
      setCoverage({ total: overview.total, known: overview.known, missing: overview.missing })
    } catch (loadError) {
      setError(apiErrorMessage(loadError))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const filteredRows = useMemo(() => {
    const keyword = search.trim().toLowerCase()
    return rows.filter((row) => {
      if (filter === 'known' && !row.has_cost) return false
      if (filter === 'missing' && row.has_cost) return false
      if (!keyword) return true
      return [row.sku, row.name, row.category ?? ''].some((field) =>
        field.toLowerCase().includes(keyword),
      )
    })
  }, [rows, search, filter])

  const averageMargin = useMemo(() => {
    const rates = rows
      .map((row) => numeric(row.margin_rate))
      .filter((_, index) => rows[index].margin_rate !== null)
    if (!rates.length) return null
    return rates.reduce((sum, value) => sum + value, 0) / rates.length
  }, [rows])

  const preview = useMemo(() => {
    const get = (key: string) => numeric(watched?.[key])
    const international =
      watched?.international_shipping !== null && watched?.international_shipping !== undefined
        ? get('international_shipping')
        : get('first_leg_shipping') + get('last_leg_shipping')
    const landed =
      get('purchase_cost') +
      get('domestic_shipping') +
      international +
      get('packaging') +
      get('tax_estimate') +
      get('handling')
    const period = get('payment_fee') + get('marketing_amortization') + get('after_sales_loss')
    return { landed: landed.toFixed(2), period: period.toFixed(2), breakeven: (landed + period).toFixed(2) }
  }, [watched])

  const openEdit = (row: CostRow) => {
    setEditRow(row)
    costForm.setFieldsValue({
      currency: row.currency ?? 'USD',
      purchase_cost: numeric(row.purchase_cost),
      domestic_shipping: numeric(row.domestic_shipping),
      first_leg_shipping: numeric(row.first_leg_shipping),
      last_leg_shipping: numeric(row.last_leg_shipping),
      international_shipping: row.has_cost ? numeric(row.international_shipping) : null,
      packaging: numeric(row.packaging),
      tax_estimate: numeric(row.tax_estimate),
      handling: numeric(row.handling),
      payment_fee: numeric(row.payment_fee),
      marketing_amortization: numeric(row.marketing_amortization),
      after_sales_loss: numeric(row.after_sales_loss),
    })
    setEditOpen(true)
  }

  const submitCost = async () => {
    if (!editRow) return
    const values = await costForm.validateFields()
    const payload: Record<string, unknown> = { ...values }
    if (payload.international_shipping === null || payload.international_shipping === undefined) {
      delete payload.international_shipping
    }
    setEditSaving(true)
    try {
      await api.saveProductCost(editRow.product_id, payload)
      message.success(`成本已保存为新版本并写入审计（${editRow.sku}）`)
      setEditOpen(false)
      await load()
    } catch (submitError) {
      message.error(`成本保存失败：${apiErrorMessage(submitError)}`)
    } finally {
      setEditSaving(false)
    }
  }

  const fetchProfit = useCallback(
    async (row: CostRow, salePrice?: number | null) => {
      setProfitLoading(true)
      try {
        const data = (await api.getProfitAnalysis(
          row.product_id,
          salePrice === null || salePrice === undefined ? undefined : salePrice,
        )) as ProfitAnalysis
        setProfit(data)
      } catch (fetchError) {
        message.error(`利润分析加载失败：${apiErrorMessage(fetchError)}`)
      } finally {
        setProfitLoading(false)
      }
    },
    [],
  )

  const openProfit = (row: CostRow) => {
    setProfitRow(row)
    setProfit(null)
    setWhatIf(null)
    setProfitOpen(true)
    void fetchProfit(row)
  }

  const columns: ColumnsType<CostRow> = [
    {
      title: '商品',
      dataIndex: 'name',
      key: 'name',
      width: 240,
      fixed: 'left',
      render: (_, row) => (
        <Space direction="vertical" size={0}>
          <Text strong>{row.name}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {row.sku} · {row.target_market}
          </Text>
        </Space>
      ),
    },
    {
      title: '成本状态',
      key: 'cost_status',
      width: 110,
      render: (_, row) =>
        row.has_cost ? (
          <Tag color="green">已维护 {row.version}</Tag>
        ) : (
          <Tag icon={<WarningOutlined />} color="red">
            缺成本
          </Tag>
        ),
    },
    {
      title: '采购',
      dataIndex: 'purchase_cost',
      width: 96,
      align: 'right',
      render: (value, row) => (row.has_cost ? money(value, row.currency ?? 'USD') : '—'),
    },
    {
      title: '头程+尾程',
      key: 'shipping',
      width: 110,
      align: 'right',
      render: (_, row) =>
        row.has_cost
          ? money(numeric(row.first_leg_shipping) + numeric(row.last_leg_shipping), row.currency ?? 'USD')
          : '—',
    },
    {
      title: '关税',
      dataIndex: 'tax_estimate',
      width: 90,
      align: 'right',
      render: (value, row) => (row.has_cost ? money(value, row.currency ?? 'USD') : '—'),
    },
    {
      title: '落地成本',
      dataIndex: 'total_landed_cost',
      width: 116,
      align: 'right',
      sorter: (a, b) => numeric(a.total_landed_cost) - numeric(b.total_landed_cost),
      render: (value, row) => (
        <Text strong>{row.has_cost ? money(value, row.currency ?? 'USD') : '—'}</Text>
      ),
    },
    {
      title: '期间成本',
      dataIndex: 'period_cost',
      width: 104,
      align: 'right',
      tooltip: '支付手续费 + 营销摊销 + 售后损失',
      render: (value, row) => (row.has_cost ? money(value, row.currency ?? 'USD') : '—'),
    },
    {
      title: '参考售价',
      dataIndex: 'sale_price',
      width: 104,
      align: 'right',
      render: (value, row) =>
        value !== null && value !== undefined ? money(value, row.currency ?? 'USD') : (
          <Text type="secondary">未定价</Text>
        ),
    },
    {
      title: '贡献毛利',
      dataIndex: 'contribution_margin',
      width: 108,
      align: 'right',
      sorter: (a, b) => numeric(a.contribution_margin) - numeric(b.contribution_margin),
      render: (value, row) => {
        if (value === null || value === undefined) return <Text type="secondary">—</Text>
        const positive = numeric(value) >= 0
        return (
          <Text strong style={{ color: positive ? '#3f8600' : '#cf1322' }}>
            {money(value, row.currency ?? 'USD')}
          </Text>
        )
      },
    },
    {
      title: '毛利率',
      dataIndex: 'margin_rate',
      width: 96,
      align: 'center',
      sorter: (a, b) => numeric(a.margin_rate) - numeric(b.margin_rate),
      render: (value) =>
        value === null || value === undefined ? (
          <Text type="secondary">—</Text>
        ) : (
          <Tag color={marginColor(value)}>{(numeric(value) * 100).toFixed(1)}%</Tag>
        ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 180,
      fixed: 'right',
      render: (_, row) => (
        <Space size="small">
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(row)}>
            成本
          </Button>
          <Button size="small" icon={<LineChartOutlined />} onClick={() => openProfit(row)}>
            利润
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div className="resource-page">
      <div className="page-heading">
        <div>
          <div className="page-kicker">PRODUCT COST &amp; PROFIT</div>
          <Title level={2}>成本与利润</Title>
          <Paragraph>
            按商品维护采购、头程、尾程、关税、支付、营销与售后成本，系统按权威落地成本（PROFIT-001）自动版本化，并结合参考售价计算贡献毛利；成本历史不可变、每次修改写入审计。
          </Paragraph>
        </div>
        <Space wrap>
          <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
            刷新
          </Button>
        </Space>
      </div>

      {error && (
        <Alert className="page-alert" type="error" showIcon message="成本数据加载失败" description={error} />
      )}

      <Row gutter={[14, 14]} className="resource-metrics">
        <Col xs={12} lg={6}>
          <Card variant="borderless">
            <Statistic title="商品总数" value={coverage.total} prefix={<DollarOutlined />} />
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card variant="borderless">
            <Statistic title="已维护成本" value={coverage.known} prefix={<WalletOutlined />} />
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card variant="borderless">
            <Statistic
              title="缺成本"
              value={coverage.missing}
              valueStyle={{ color: coverage.missing > 0 ? '#cf1322' : undefined }}
              prefix={<WarningOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card variant="borderless">
            <Statistic
              title="平均毛利率(已定价)"
              value={averageMargin === null ? '—' : (averageMargin * 100).toFixed(1)}
              precision={1}
              suffix={averageMargin === null ? '' : '%'}
            />
          </Card>
        </Col>
      </Row>

      <Card variant="borderless" className="resource-panel">
        <div className="resource-toolbar">
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索商品名、SKU 或分类"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            style={{ maxWidth: 320 }}
          />
          <Segmented
            value={filter}
            onChange={(value) => setFilter(value as CostFilter)}
            options={[
              { value: 'all', label: `全部 ${coverage.total}` },
              { value: 'known', label: `已维护 ${coverage.known}` },
              { value: 'missing', label: `缺成本 ${coverage.missing}` },
            ]}
          />
          <Text type="secondary">当前展示 {filteredRows.length} 条</Text>
        </div>

        <Table
          rowKey="product_id"
          loading={loading}
          columns={columns}
          dataSource={filteredRows}
          scroll={{ x: 1400 }}
          pagination={{
            pageSize: 20,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 条`,
          }}
          locale={{
            emptyText: (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无商品成本数据" />
            ),
          }}
        />
      </Card>

      <Drawer
        width={620}
        open={editOpen}
        onClose={() => setEditOpen(false)}
        title={editRow ? `维护成本 · ${editRow.sku}` : '维护成本'}
        extra={
          <Space>
            <Button onClick={() => setEditOpen(false)}>取消</Button>
            <Button type="primary" loading={editSaving} onClick={() => void submitCost()}>
              保存为新版本
            </Button>
          </Space>
        }
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="保存会生成新的成本版本并追加一条不可变历史快照，同时写入审计；不会覆盖历史版本。"
        />
        <Form form={costForm} layout="vertical">
          <Form.Item name="currency" label="币种" rules={[{ required: true }]}>
            <Input maxLength={8} style={{ width: 120 }} />
          </Form.Item>
          <Divider orientation="left" plain>
            落地成本
          </Divider>
          <Row gutter={12}>
            {COST_FIELDS.map((field) => (
              <Col xs={24} sm={12} key={field.name}>
                <Form.Item
                  name={field.name}
                  label={field.label}
                  rules={field.required ? [{ required: true, message: '请输入采购成本' }] : undefined}
                >
                  <InputNumber min={0} step={0.01} precision={2} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
            ))}
          </Row>
          <Divider orientation="left" plain>
            期间成本（按单摊销）
          </Divider>
          <Row gutter={12}>
            {PERIOD_FIELDS.map((field) => (
              <Col xs={24} sm={8} key={field.name}>
                <Form.Item name={field.name} label={field.label}>
                  <InputNumber min={0} step={0.01} precision={2} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
            ))}
          </Row>
          <Card size="small" variant="borderless" style={{ background: '#fafafa' }}>
            <Descriptions column={1} size="small">
              <Descriptions.Item label="落地成本合计">{preview.landed}</Descriptions.Item>
              <Descriptions.Item label="期间成本合计">{preview.period}</Descriptions.Item>
              <Descriptions.Item label="盈亏平衡售价（不亏最低价）">
                <Text strong>{preview.breakeven}</Text>
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </Form>
      </Drawer>

      <Drawer
        width={560}
        open={profitOpen}
        onClose={() => setProfitOpen(false)}
        title={profitRow ? `利润分析 · ${profitRow.sku}` : '利润分析'}
        loading={profitLoading}
      >
        {profit && (
          <>
            {profit.cost_status === 'MISSING' && (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 16 }}
                message="该商品尚未维护落地成本，无法计算可信利润，请先在“成本”中录入。"
              />
            )}
            <Space style={{ marginBottom: 16 }}>
              <InputNumber
                min={0}
                step={0.01}
                precision={2}
                placeholder="输入试算售价"
                value={whatIf}
                onChange={(value) => setWhatIf(value)}
                style={{ width: 160 }}
              />
              <Button
                onClick={() => profitRow && void fetchProfit(profitRow, whatIf)}
                disabled={whatIf === null}
              >
                按此售价试算
              </Button>
              <Button
                onClick={() => {
                  setWhatIf(null)
                  if (profitRow) void fetchProfit(profitRow)
                }}
              >
                用系统售价
              </Button>
            </Space>
            <Descriptions bordered column={1} size="small">
              <Descriptions.Item label="成本状态">
                {profit.cost_status === 'KNOWN' ? (
                  <Tag color="green">已核算 {profit.version}</Tag>
                ) : (
                  <Tag color="red">缺成本</Tag>
                )}
              </Descriptions.Item>
              <Descriptions.Item label="参考售价">
                {profit.sale_price === null ? '未定价' : money(profit.sale_price, profit.currency)}
              </Descriptions.Item>
              <Descriptions.Item label="落地成本">
                {money(profit.total_landed_cost, profit.currency)}
              </Descriptions.Item>
              <Descriptions.Item label="期间成本">
                <Tooltip title="支付 + 营销 + 售后">
                  {money(profit.period_cost, profit.currency)}
                </Tooltip>
              </Descriptions.Item>
              <Descriptions.Item label="总成本">
                {profit.total_cost === null ? '—' : money(profit.total_cost, profit.currency)}
              </Descriptions.Item>
              <Descriptions.Item label="盈亏平衡售价">
                {money(profit.breakeven_price, profit.currency)}
              </Descriptions.Item>
              <Descriptions.Item label="贡献毛利">
                {profit.contribution_margin === null ? (
                  '—'
                ) : (
                  <Text
                    strong
                    style={{
                      color: numeric(profit.contribution_margin) >= 0 ? '#3f8600' : '#cf1322',
                    }}
                  >
                    {money(profit.contribution_margin, profit.currency)}
                  </Text>
                )}
              </Descriptions.Item>
              <Descriptions.Item label="贡献毛利率">
                {profit.contribution_margin_rate === null ? (
                  '—'
                ) : (
                  <Tag color={marginColor(profit.contribution_margin_rate)}>
                    {(numeric(profit.contribution_margin_rate) * 100).toFixed(1)}%
                  </Tag>
                )}
              </Descriptions.Item>
              <Descriptions.Item label="成本加成率(对落地成本)">
                {profit.markup_rate === null ? '—' : `${(numeric(profit.markup_rate) * 100).toFixed(1)}%`}
              </Descriptions.Item>
            </Descriptions>
          </>
        )}
      </Drawer>
    </div>
  )
}
