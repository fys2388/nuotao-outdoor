import { useCallback, useEffect, useState } from 'react'
import { Alert, Button, Card, Col, Progress, Row, Skeleton, Space, Tag, Typography } from 'antd'
import {
  ArrowDownOutlined,
  ArrowRightOutlined,
  ArrowUpOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  ClusterOutlined,
  DollarOutlined,
  ReloadOutlined,
  RiseOutlined,
  ShopOutlined,
  ShoppingCartOutlined,
  TeamOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useAuth } from '../auth/AuthProvider'
import ValueStreamBar from '../components/ValueStreamBar'

const { Title, Text, Paragraph } = Typography

interface KeyMetrics {
  today_revenue: number
  today_orders: number
  today_gross_margin: number | null
  today_roas: number | null
  week_revenue: number
  week_orders: number
  month_revenue: number
  month_orders: number
}

interface DashboardSummary {
  key_metrics: KeyMetrics
  trends: {
    revenue_week_over_week?: {
      change_percent: number
      direction: 'up' | 'down' | 'flat'
    }
    orders_week_over_week?: {
      change_percent: number
      direction: 'up' | 'down' | 'flat'
    }
  }
  period?: {
    start_date: string
    end_date: string
    generated_at: string
  }
  today?: {
    data_quality?: {
      has_real_data: boolean
      cost_status?: 'verified' | 'partial' | 'missing'
      cost_coverage_percent?: number
      profit_known_orders?: number
      orders_count?: number
      note?: string
    }
  }
  data_source?: string
}

interface AlertResponse {
  alerts?: Array<unknown>
  summary?: {
    total?: number
    critical_count?: number
    warning_count?: number
    new_count?: number
  }
}

interface B2BStats {
  total_agents: number
  active_agents: number
  pending_agents: number
  total_orders: number
  total_revenue: number
  pending_orders: number
  total_credit_limit: number
  total_outstanding_balance: number
}

interface LoadState {
  summary: DashboardSummary | null
  alerts: AlertResponse | null
  b2b: B2BStats | null
  productCount: number | null
}

type DataKey = keyof LoadState

function formatMoney(value: number | undefined): string {
  if (value === undefined || Number.isNaN(value)) return '--'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value)
}

function formatNumber(value: number | undefined): string {
  if (value === undefined || Number.isNaN(value)) return '--'
  return new Intl.NumberFormat('zh-CN').format(value)
}

function TrendTag({ value }: { value?: { change_percent: number; direction: 'up' | 'down' | 'flat' } }) {
  if (!value) return <Tag>暂无对比</Tag>
  if (value.direction === 'flat') return <Tag>持平</Tag>
  const positive = value.direction === 'up'
  return (
    <Tag color={positive ? 'green' : 'red'} icon={positive ? <ArrowUpOutlined /> : <ArrowDownOutlined />}>
      {Math.abs(value.change_percent).toFixed(1)}%
    </Tag>
  )
}

function MetricCard({
  label,
  value,
  note,
  accent,
}: {
  label: string
  value: string
  note: string
  accent: 'forest' | 'orange' | 'blue' | 'slate'
}) {
  return (
    <Card className={`metric-card metric-card--${accent}`} variant="borderless">
      <Text className="metric-card__label">{label}</Text>
      <div className="metric-card__value">{value}</div>
      <Text className="metric-card__note">{note}</Text>
    </Card>
  )
}

export default function DashboardPage() {
  const { authenticated, user } = useAuth()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [errors, setErrors] = useState<Partial<Record<DataKey, string>>>({})
  const [data, setData] = useState<LoadState>({
    summary: null,
    alerts: null,
    b2b: null,
    productCount: null,
  })

  const loadData = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true)
    else setLoading(true)

    const nextErrors: Partial<Record<DataKey, string>> = {}
    const requests = [
      api.getDashboardSummary()
        .then((response) => {
          const payload = response as { summary?: DashboardSummary }
          setData((current) => ({ ...current, summary: payload.summary || null }))
        })
        .catch((error) => {
          nextErrors.summary = error instanceof Error ? error.message : '经营数据加载失败'
        }),
      api.getAlerts()
        .then((response) => {
          setData((current) => ({ ...current, alerts: response as AlertResponse }))
        })
        .catch((error) => {
          nextErrors.alerts = error instanceof Error ? error.message : '预警数据加载失败'
        }),
      api.getProducts(1)
        .then((response) => {
          const products = Array.isArray(response) ? response : []
          setData((current) => ({ ...current, productCount: products.length }))
        })
        .catch((error) => {
          nextErrors.productCount = error instanceof Error ? error.message : '商品数据加载失败'
        }),
    ]

    if (authenticated) {
      requests.push(
        api.getB2BStats()
          .then((response) => {
            setData((current) => ({ ...current, b2b: response as B2BStats }))
          })
          .catch((error) => {
            nextErrors.b2b = error instanceof ApiError && error.status === 401
              ? 'B2B 数据需要登录后查看'
              : error instanceof Error
                ? error.message
                : 'B2B 数据加载失败'
          }),
      )
    }

    await Promise.allSettled(requests)
    setErrors(nextErrors)
    setLoading(false)
    setRefreshing(false)
  }, [authenticated])

  useEffect(() => {
    void loadData()
  }, [loadData])

  const metrics = data.summary?.key_metrics
  const todayRevenue = metrics?.today_revenue
  const todayOrders = metrics?.today_orders
  const averageOrderValue =
    todayRevenue !== undefined && todayOrders !== undefined && todayOrders > 0
      ? todayRevenue / todayOrders
      : undefined
  const alertSummary = data.alerts?.summary
  const alertCount = alertSummary?.total ?? data.alerts?.alerts?.length ?? 0
  const pendingB2B = data.b2b?.pending_agents ?? 0
  const dataUnavailable = Boolean(errors.summary)
  const costStatus = data.summary?.today?.data_quality?.cost_status
  const costCoverage = data.summary?.today?.data_quality?.cost_coverage_percent
  const b2bRevenueShare =
    data.b2b && metrics?.month_revenue
      ? Math.min(100, (data.b2b.total_revenue / (data.b2b.total_revenue + metrics.month_revenue)) * 100)
      : null

  return (
    <div className="dashboard-page">
      <div className="page-heading">
        <div>
          <div className="page-kicker">EXECUTIVE CONTROL TOWER</div>
          <Title level={2}>经营总览</Title>
          <Paragraph>
            同时观察 B2C 零售与 B2B 批发，所有指标保留数据来源与可信状态。
          </Paragraph>
        </div>
        <Button
          icon={<ReloadOutlined />}
          loading={refreshing}
          onClick={() => void loadData(true)}
        >
          刷新数据
        </Button>
      </div>

      {dataUnavailable && (
        <Alert
          type="error"
          showIcon
          title="经营数据当前不可用"
          description={errors.summary}
          action={
            <Button size="small" onClick={() => navigate('/api-management')}>
              检查连接器
            </Button>
          }
          className="page-alert"
        />
      )}

      <ValueStreamBar />

      <Skeleton active loading={loading}>
        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} xl={6}>
            <MetricCard
              label="今日收入"
              value={formatMoney(todayRevenue)}
              note="来源：WooCommerce 真实订单"
              accent="forest"
            />
          </Col>
          <Col xs={24} sm={12} xl={6}>
            <MetricCard
              label="今日订单"
              value={formatNumber(todayOrders)}
              note="统计时区：UTC，时间范围：今日"
              accent="blue"
            />
          </Col>
          <Col xs={24} sm={12} xl={6}>
            <MetricCard
              label="今日客单价"
              value={formatMoney(averageOrderValue)}
              note="系统计算：今日收入 / 今日订单"
              accent="slate"
            />
          </Col>
          <Col xs={24} sm={12} xl={6}>
            <MetricCard
              label="今日毛利率"
              value={
                metrics?.today_gross_margin == null
                  ? '--'
                  : `${metrics.today_gross_margin.toFixed(1)}%`
              }
              note={
                costStatus === 'verified'
                  ? '来源：订单利润快照，成本覆盖完整'
                  : costStatus === 'partial'
                    ? `部分成本快照，覆盖 ${costCoverage ?? 0}% 订单`
                    : '缺少成本快照，不展示推断利润'
              }
              accent="orange"
            />
          </Col>
        </Row>

        <Row gutter={[18, 18]} className="dashboard-business-grid">
          <Col xs={24} xl={12}>
            <Card
              variant="borderless"
              className="business-lane business-lane--b2c"
              title={
                <Space>
                  <ShopOutlined />
                  <span>B2C 零售通道</span>
                  <Tag color="green">DTC 主站</Tag>
                </Space>
              }
              extra={
                <Button type="link" onClick={() => navigate('/b2c/overview')}>
                  查看零售经营 <ArrowRightOutlined />
                </Button>
              }
            >
              <Row gutter={[14, 14]}>
                <Col span={12}>
                  <div className="mini-stat">
                    <Text>本月零售收入</Text>
                    <strong>{formatMoney(metrics?.month_revenue)}</strong>
                  </div>
                </Col>
                <Col span={12}>
                  <div className="mini-stat">
                    <Text>本月零售订单</Text>
                    <strong>{formatNumber(metrics?.month_orders)}</strong>
                  </div>
                </Col>
              </Row>
              <div className="lane-metrics">
                <div>
                  <Text type="secondary">周收入趋势</Text>
                  <TrendTag value={data.summary?.trends.revenue_week_over_week} />
                </div>
                <div>
                  <Text type="secondary">周订单趋势</Text>
                  <TrendTag value={data.summary?.trends.orders_week_over_week} />
                </div>
              </div>
            </Card>
          </Col>

          <Col xs={24} xl={12}>
            <Card
              variant="borderless"
              className="business-lane business-lane--b2b"
              title={
                <Space>
                  <ClusterOutlined />
                  <span>B2B 批发通道</span>
                  <Tag color="orange">代理商与小 B</Tag>
                </Space>
              }
              extra={
                <Button type="link" onClick={() => navigate('/b2b/overview')}>
                  查看批发经营 <ArrowRightOutlined />
                </Button>
              }
            >
              {!authenticated ? (
                <div className="lane-locked">
                  <WarningOutlined />
                  <div>
                    <strong>登录后查看 B2B 经营数据</strong>
                    <Text type="secondary">代理商、批发订单和信用敞口均按权限展示。</Text>
                  </div>
                  <Button type="primary" onClick={() => navigate('/login?next=%2Fb2b%2Foverview')}>
                    登录
                  </Button>
                </div>
              ) : (
                <>
                  <Row gutter={[14, 14]}>
                    <Col span={12}>
                      <div className="mini-stat">
                        <Text>活跃代理商</Text>
                        <strong>{formatNumber(data.b2b?.active_agents)}</strong>
                      </div>
                    </Col>
                    <Col span={12}>
                      <div className="mini-stat">
                        <Text>B2B 累计收入</Text>
                        <strong>{formatMoney(data.b2b?.total_revenue)}</strong>
                      </div>
                    </Col>
                  </Row>
                  <div className="lane-metrics">
                    <div>
                      <Text type="secondary">待审核客户</Text>
                      <Tag color={pendingB2B ? 'orange' : 'default'}>{pendingB2B} 家</Tag>
                    </div>
                    <div>
                      <Text type="secondary">信用敞口</Text>
                      <Tag color={data.b2b?.total_outstanding_balance ? 'red' : 'green'}>
                        {formatMoney(data.b2b?.total_outstanding_balance)}
                      </Tag>
                    </div>
                  </div>
                </>
              )}
            </Card>
          </Col>
        </Row>

        <Row gutter={[18, 18]} className="dashboard-lower-grid">
          <Col xs={24} xl={16}>
            <Card variant="borderless" title="经营状态与待办">
              <Row gutter={[16, 16]}>
                <Col xs={24} md={8}>
                  <div className="status-tile">
                    <WarningOutlined />
                    <div>
                      <strong>{formatNumber(alertCount)}</strong>
                      <span>业务预警</span>
                    </div>
                    <Button type="link" onClick={() => navigate('/alerts')}>
                      处理
                    </Button>
                  </div>
                </Col>
                <Col xs={24} md={8}>
                  <div className="status-tile">
                    <TeamOutlined />
                    <div>
                      <strong>{formatNumber(pendingB2B)}</strong>
                      <span>待审核 B2B 客户</span>
                    </div>
                    <Button type="link" onClick={() => navigate('/b2b/partners')}>
                      审核
                    </Button>
                  </div>
                </Col>
                <Col xs={24} md={8}>
                  <div className="status-tile">
                    <ShoppingCartOutlined />
                    <div>
                      <strong>{formatNumber(data.productCount ?? 0)}</strong>
                      <span>当前页商品主数据</span>
                    </div>
                    <Button type="link" onClick={() => navigate('/products')}>
                      查看
                    </Button>
                  </div>
                </Col>
              </Row>

              {b2bRevenueShare !== null && (
                <div className="revenue-mix">
                  <div>
                    <Text strong>本月业务收入结构</Text>
                    <Text type="secondary">按当前可读取的零售与 B2B 收入计算，未归因时仅供参考</Text>
                  </div>
                  <Progress
                    percent={Number(b2bRevenueShare.toFixed(1))}
                    strokeColor="#d9773b"
                    railColor="#2f7367"
                    format={(percent) => `B2B ${percent}%`}
                  />
                </div>
              )}
            </Card>
          </Col>

          <Col xs={24} xl={8}>
            <Card variant="borderless" title="数据可信状态">
              <div className="data-source-list">
                <div>
                  <CheckCircleOutlined className="source-icon source-icon--good" />
                  <span>
                    <strong>订单与收入</strong>
                    <small>PostgreSQL / WooCommerce</small>
                  </span>
                  <Tag color="green">真实</Tag>
                </div>
                <div>
                  {costStatus === 'verified' ? (
                    <CheckCircleOutlined className="source-icon source-icon--good" />
                  ) : (
                    <ClockCircleOutlined className="source-icon source-icon--warn" />
                  )}
                  <span>
                    <strong>毛利成本</strong>
                    <small>
                      {costStatus === 'verified'
                        ? '订单利润快照，成本覆盖完整'
                        : costStatus === 'partial'
                          ? `订单利润快照，覆盖 ${costCoverage ?? 0}%`
                          : '未找到可用成本快照'}
                    </small>
                  </span>
                  <Tag color={costStatus === 'verified' ? 'green' : costStatus === 'partial' ? 'orange' : 'default'}>
                    {costStatus === 'verified' ? '已核对' : costStatus === 'partial' ? '部分' : '缺失'}
                  </Tag>
                </div>
                <div>
                  <DollarOutlined className="source-icon" />
                  <span>
                    <strong>ROAS / 广告投入</strong>
                    <small>{metrics?.today_roas ? '已读取到广告投入' : '未配置广告数据源'}</small>
                  </span>
                  <Tag color={metrics?.today_roas ? 'blue' : 'default'}>
                    {metrics?.today_roas ? '已读取' : '数据不足'}
                  </Tag>
                </div>
                <div>
                  <RiseOutlined className="source-icon" />
                  <span>
                    <strong>更新时间</strong>
                    <small>{data.summary?.period?.generated_at || '尚未返回'}</small>
                  </span>
                  <Tag>UTC</Tag>
                </div>
              </div>
              {user && (
                <div className="data-source-footer">
                  当前账号：{user.username} · {user.role}
                </div>
              )}
            </Card>
          </Col>
        </Row>
      </Skeleton>
    </div>
  )
}
