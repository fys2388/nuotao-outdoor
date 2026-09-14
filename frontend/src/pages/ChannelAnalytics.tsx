import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Row,
  Select,
  Skeleton,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import {
  BarChartOutlined,
  ClusterOutlined,
  ReloadOutlined,
  ShopOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'
import { api, ApiError } from '../api/client'

const { Title, Text, Paragraph } = Typography
const { RangePicker } = DatePicker

type BusinessModel = 'B2C' | 'B2B'
type DataQualityStatus = 'verified' | 'partial' | 'missing'

interface AnalyticsDataQuality {
  status: DataQualityStatus
  cost_coverage_percent: string | null
  notes: string[]
}

interface ChannelSummary {
  business_model: BusinessModel
  currency: string
  revenue: string
  orders: number
  units: number
  average_order_value: string
  profit_revenue: string
  gross_profit: string | null
  gross_margin_percent: string | null
  refund_amount: string
  advertising_cost: string
  roas: string | null
  data_quality: AnalyticsDataQuality
}

interface CustomerContribution {
  business_model: BusinessModel
  customer_id: string
  customer_name: string
  currency: string
  revenue: string
  orders: number
  profit_revenue: string
  gross_profit: string | null
  gross_margin_percent: string | null
  cost_coverage_percent: string
  credit_limit: string | null
  current_balance: string | null
  available_credit: string | null
}

interface ReceivableAging {
  currency: string
  current: string
  days_1_30: string
  days_31_60: string
  days_61_90: string
  days_over_90: string
  total: string
}

interface InventoryPerformance {
  product_id: string
  sku: string
  name: string
  b2c_units: number
  b2b_units: number
  total_units: number
  current_inventory: number
  reserved: number
  available: number
  in_transit: number
  turnover_ratio: string | null
  days_of_inventory: string | null
  inventory_basis: string
}

interface ChannelAnalyticsResponse {
  period: { start_date: string; end_date: string }
  generated_at: string
  currency_filter: string | null
  reporting_currency: string | null
  channel_summaries: ChannelSummary[]
  top_customers: CustomerContribution[]
  receivable_aging: ReceivableAging[]
  inventory_performance: InventoryPerformance[]
  data_quality: AnalyticsDataQuality
  notes: string[]
}

const qualityMeta: Record<DataQualityStatus, { color: string; label: string }> = {
  verified: { color: 'green', label: '成本完整' },
  partial: { color: 'orange', label: '部分成本' },
  missing: { color: 'default', label: '缺少成本' },
}

function money(value: string | number | null | undefined, currency = 'USD'): string {
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

function totalAging(rows: ReceivableAging[], fields: Array<keyof ReceivableAging>): number | null {
  const currencies = new Set(rows.map((row) => row.currency))
  if (currencies.size !== 1) return null
  return rows.reduce(
    (sum, row) => sum + fields.reduce((rowSum, field) => rowSum + Number(row[field] || 0), 0),
    0,
  )
}

export default function ChannelAnalytics() {
  const [range, setRange] = useState<[Dayjs, Dayjs]>([
    dayjs().subtract(29, 'day'),
    dayjs(),
  ])
  const [report, setReport] = useState<ChannelAnalyticsResponse | null>(null)
  const [reportingCurrency, setReportingCurrency] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = (await api.getChannelPerformance(
        range[0].format('YYYY-MM-DD'),
        range[1].format('YYYY-MM-DD'),
        undefined,
        reportingCurrency || undefined,
      )) as ChannelAnalyticsResponse
      setReport(response)
    } catch (requestError) {
      setReport(null)
      if (requestError instanceof ApiError && requestError.status === 401) {
        setError('登录状态已失效，请重新登录后查看渠道分析。')
      } else {
        setError(requestError instanceof Error ? requestError.message : '渠道经营分析加载失败')
      }
    } finally {
      setLoading(false)
    }
  }, [range, reportingCurrency])

  useEffect(() => {
    void load()
  }, [load])

  const b2c = report?.channel_summaries.find((row) => row.business_model === 'B2C')
  const b2b = report?.channel_summaries.find((row) => row.business_model === 'B2B')
  const overdue = useMemo(
    () => totalAging(report?.receivable_aging || [], ['days_1_30', 'days_31_60', 'days_61_90', 'days_over_90']),
    [report],
  )
  const quality = report?.data_quality

  return (
    <div className="resource-page">
      <div className="page-heading">
        <div>
          <div className="page-kicker">CHANNEL PROFITABILITY & WORKING CAPITAL</div>
          <Title level={2}>渠道经营分析</Title>
          <Paragraph>
            B2C 与 B2B 统一按业务模式归因，金额按币种分组，不用缺失成本或汇率推断利润。
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
            aria-label="报告币种"
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
          title="渠道分析当前不可用"
          description={error}
        />
      )}

      {quality && (
        <Alert
          className="page-alert"
          type={quality.status === 'verified' ? 'success' : quality.status === 'partial' ? 'warning' : 'info'}
          showIcon
          title={`数据可信状态：${qualityMeta[quality.status].label}`}
          description={`成本覆盖率 ${
            quality.cost_coverage_percent === null
              ? '请按渠道与币种查看'
              : percent(quality.cost_coverage_percent)
          }。${quality.notes.join(' ')}`}
        />
      )}

      <Skeleton active loading={loading}>
        <Row gutter={[14, 14]} className="resource-metrics">
          <Col xs={24} sm={12} xl={6}>
            <Card variant="borderless">
              <Statistic
                title="B2C 收入"
                value={b2c ? money(b2c.revenue, b2c.currency) : '--'}
                prefix={<ShopOutlined />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} xl={6}>
            <Card variant="borderless">
              <Statistic
                title="B2B 收入"
                value={b2b ? money(b2b.revenue, b2b.currency) : '--'}
                prefix={<ClusterOutlined />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} xl={6}>
            <Card variant="borderless">
              <Statistic
                title="综合成本覆盖"
                value={
                  quality?.cost_coverage_percent === null
                    ? '按渠道'
                    : percent(quality?.cost_coverage_percent)
                }
                prefix={<BarChartOutlined />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} xl={6}>
            <Card variant="borderless">
              <Statistic
                title="逾期应收"
                value={overdue === null ? '多币种' : money(overdue, report?.receivable_aging[0]?.currency)}
                prefix={<WarningOutlined />}
                valueStyle={{ color: overdue && overdue > 0 ? '#bd4b4b' : undefined }}
              />
            </Card>
          </Col>
        </Row>

        <Card variant="borderless" className="resource-panel" title="渠道收入与利润">
          <Table
            rowKey={(row) => `${row.business_model}-${row.currency}`}
            pagination={false}
            dataSource={report?.channel_summaries || []}
            scroll={{ x: 1200 }}
            locale={{ emptyText: '选定期间没有已确认的经营数据' }}
            columns={[
              {
                title: '业务模式',
                dataIndex: 'business_model',
                width: 100,
                render: (value: BusinessModel) => (
                  <Tag color={value === 'B2B' ? 'orange' : 'green'}>{value}</Tag>
                ),
              },
              { title: '币种', dataIndex: 'currency', width: 80 },
              {
                title: '收入',
                dataIndex: 'revenue',
                align: 'right',
                render: (value: string, row) => money(value, row.currency),
              },
              { title: '订单', dataIndex: 'orders', align: 'right', width: 80 },
              { title: '销售件数', dataIndex: 'units', align: 'right', width: 100 },
              {
                title: '客单价',
                dataIndex: 'average_order_value',
                align: 'right',
                render: (value: string, row) => money(value, row.currency),
              },
              {
                title: '毛利',
                dataIndex: 'gross_profit',
                align: 'right',
                render: (value: string | null, row) =>
                  value === null ? <Text type="secondary">成本不足</Text> : money(value, row.currency),
              },
              {
                title: '毛利率',
                dataIndex: 'gross_margin_percent',
                align: 'right',
                render: percent,
              },
              {
                title: '成本覆盖',
                dataIndex: 'data_quality',
                width: 110,
                render: (value: AnalyticsDataQuality) => (
                  <Tag color={qualityMeta[value.status].color}>
                    {percent(value.cost_coverage_percent)}
                  </Tag>
                ),
              },
              {
                title: '退款',
                dataIndex: 'refund_amount',
                align: 'right',
                render: (value: string, row) => money(value, row.currency),
              },
            ]}
          />
        </Card>

        <Card variant="borderless" className="resource-panel">
          <Tabs
            items={[
              {
                key: 'customers',
                label: '客户贡献',
                children: (
                  <Table
                    rowKey={(row) => `${row.business_model}-${row.customer_id}-${row.currency}`}
                    pagination={{ pageSize: 10 }}
                    dataSource={report?.top_customers || []}
                    scroll={{ x: 1150 }}
                    locale={{ emptyText: '选定期间没有客户贡献数据' }}
                    columns={[
                      {
                        title: '模式',
                        dataIndex: 'business_model',
                        width: 80,
                        render: (value: BusinessModel) => (
                          <Tag color={value === 'B2B' ? 'orange' : 'green'}>{value}</Tag>
                        ),
                      },
                      { title: '客户', dataIndex: 'customer_name', ellipsis: true },
                      {
                        title: '收入',
                        dataIndex: 'revenue',
                        align: 'right',
                        render: (value: string, row) => money(value, row.currency),
                      },
                      { title: '订单', dataIndex: 'orders', align: 'right', width: 80 },
                      {
                        title: '毛利',
                        dataIndex: 'gross_profit',
                        align: 'right',
                        render: (value: string | null, row) =>
                          value === null ? <Text type="secondary">--</Text> : money(value, row.currency),
                      },
                      {
                        title: '毛利率',
                        dataIndex: 'gross_margin_percent',
                        align: 'right',
                        render: percent,
                      },
                      {
                        title: '成本覆盖',
                        dataIndex: 'cost_coverage_percent',
                        align: 'right',
                        render: percent,
                      },
                      {
                        title: '可用信用',
                        dataIndex: 'available_credit',
                        align: 'right',
                        render: (value: string | null, row) =>
                          value === null ? '--' : money(value, row.currency),
                      },
                    ]}
                  />
                ),
              },
              {
                key: 'receivables',
                label: '应收账龄',
                children: (
                  <Table
                    rowKey="currency"
                    pagination={false}
                    dataSource={report?.receivable_aging || []}
                    locale={{ emptyText: '当前没有未结应收' }}
                    columns={[
                      { title: '币种', dataIndex: 'currency', width: 90 },
                      {
                        title: '未到期',
                        dataIndex: 'current',
                        align: 'right',
                        render: (value: string, row) => money(value, row.currency),
                      },
                      {
                        title: '1-30 天',
                        dataIndex: 'days_1_30',
                        align: 'right',
                        render: (value: string, row) => money(value, row.currency),
                      },
                      {
                        title: '31-60 天',
                        dataIndex: 'days_31_60',
                        align: 'right',
                        render: (value: string, row) => money(value, row.currency),
                      },
                      {
                        title: '61-90 天',
                        dataIndex: 'days_61_90',
                        align: 'right',
                        render: (value: string, row) => money(value, row.currency),
                      },
                      {
                        title: '90 天以上',
                        dataIndex: 'days_over_90',
                        align: 'right',
                        render: (value: string, row) => (
                          <Text type="danger">{money(value, row.currency)}</Text>
                        ),
                      },
                      {
                        title: '余额',
                        dataIndex: 'total',
                        align: 'right',
                        render: (value: string, row) => money(value, row.currency),
                      },
                    ]}
                  />
                ),
              },
              {
                key: 'inventory',
                label: '库存周转',
                children: (
                  <Table
                    rowKey="product_id"
                    pagination={{ pageSize: 10 }}
                    dataSource={report?.inventory_performance || []}
                    scroll={{ x: 1150 }}
                    locale={{ emptyText: '选定期间没有销量商品' }}
                    columns={[
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
                      { title: 'B2C 件数', dataIndex: 'b2c_units', align: 'right', width: 90 },
                      { title: 'B2B 件数', dataIndex: 'b2b_units', align: 'right', width: 90 },
                      { title: '总销量', dataIndex: 'total_units', align: 'right', width: 90 },
                      { title: '当前库存', dataIndex: 'current_inventory', align: 'right', width: 100 },
                      { title: '可用', dataIndex: 'available', align: 'right', width: 80 },
                      { title: '在途', dataIndex: 'in_transit', align: 'right', width: 80 },
                      {
                        title: '周转倍数',
                        dataIndex: 'turnover_ratio',
                        align: 'right',
                        render: (value: string | null) => value ?? '--',
                      },
                      {
                        title: '库存天数',
                        dataIndex: 'days_of_inventory',
                        align: 'right',
                        render: (value: string | null) => (value === null ? '--' : `${Number(value).toFixed(1)} 天`),
                      },
                    ]}
                  />
                ),
              },
            ]}
          />
        </Card>
      </Skeleton>
    </div>
  )
}
