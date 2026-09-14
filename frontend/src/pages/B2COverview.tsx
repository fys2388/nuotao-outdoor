import { useCallback, useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Col,
  Row,
  Skeleton,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd'
import {
  ArrowRightOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CustomerServiceOutlined,
  MailOutlined,
  ReloadOutlined,
  ShopOutlined,
  ShoppingCartOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api/client'

const { Title, Text, Paragraph } = Typography

interface OrderRow {
  id: string
  external_order_id: string
  status: string
  payment_status: string | null
  fulfillment_status: string | null
  currency: string
  total: number
  received_at: string
}

interface OrderListResponse {
  items: OrderRow[]
  total: number
}

interface SummaryResponse {
  summary?: {
    key_metrics: {
      today_revenue: number
      today_orders: number
      month_revenue: number
      month_orders: number
    }
    period?: { generated_at: string }
  }
}

const orderStatusLabels: Record<string, string> = {
  pending: '待支付',
  processing: '处理中',
  completed: '已完成',
  cancelled: '已取消',
  refunded: '已退款',
  failed: '失败',
}

export default function B2COverview() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [orders, setOrders] = useState<OrderListResponse>({ items: [], total: 0 })
  const [summary, setSummary] = useState<SummaryResponse['summary'] | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [summaryResponse, orderResponse] = await Promise.all([
        api.getDashboardSummary(),
        api.getOrders(100),
      ])
      setSummary((summaryResponse as SummaryResponse).summary || null)
      setOrders(orderResponse as OrderListResponse)
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : 'B2C 数据加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const metrics = summary?.key_metrics
  const pendingFulfillment = orders.items.filter(
    (order) => order.status === 'processing' && order.fulfillment_status !== 'fulfilled',
  ).length
  const refundOrders = orders.items.filter((order) => order.status === 'refunded').length

  return (
    <div className="dashboard-page">
      <div className="page-heading">
        <div>
          <div className="page-kicker page-kicker--b2c">B2C RETAIL OPERATIONS</div>
          <Title level={2}>B2C 零售经营</Title>
          <Paragraph>独立站、平台与社媒订单共享同一套商品、库存与履约底座。</Paragraph>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
          刷新
        </Button>
      </div>

      {error && (
        <Alert
          type="error"
          showIcon
          title="B2C 数据当前不可用"
          description={error}
          className="page-alert"
        />
      )}

      <Skeleton active loading={loading}>
        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} xl={6}>
            <Card variant="borderless">
              <Statistic title="今日订单" value={metrics?.today_orders ?? 0} prefix={<ShoppingCartOutlined />} />
            </Card>
          </Col>
          <Col xs={24} sm={12} xl={6}>
            <Card variant="borderless">
              <Statistic title="本月零售收入" value={metrics?.month_revenue ?? 0} precision={2} prefix="$" />
            </Card>
          </Col>
          <Col xs={24} sm={12} xl={6}>
            <Card variant="borderless">
              <Statistic title="待履约订单" value={pendingFulfillment} styles={{ content: { color: '#c27622' } }} />
            </Card>
          </Col>
          <Col xs={24} sm={12} xl={6}>
            <Card variant="borderless">
              <Statistic title="当前页退款订单" value={refundOrders} styles={{ content: { color: '#bd4b4b' } }} />
            </Card>
          </Col>
        </Row>

        <Row gutter={[18, 18]} className="dashboard-business-grid">
          <Col xs={24} xl={15}>
            <Card
              variant="borderless"
              title={
                <Space>
                  <ShoppingCartOutlined />
                  <span>最近 B2C 订单</span>
                </Space>
              }
              extra={
                <Button type="link" onClick={() => navigate('/b2c/orders')}>
                  查看全部订单 <ArrowRightOutlined />
                </Button>
              }
            >
              <Table
                rowKey="id"
                size="small"
                pagination={false}
                dataSource={orders.items.slice(0, 6)}
                columns={[
                  {
                    title: '订单号',
                    dataIndex: 'external_order_id',
                    render: (value: string) => <Text strong>#{value}</Text>,
                  },
                  {
                    title: '状态',
                    dataIndex: 'status',
                    render: (value: string) => (
                      <Tag color={value === 'completed' ? 'green' : value === 'refunded' ? 'red' : 'blue'}>
                        {orderStatusLabels[value] || value}
                      </Tag>
                    ),
                  },
                  {
                    title: '履约',
                    dataIndex: 'fulfillment_status',
                    render: (value: string | null) => (
                      <Tag color={value === 'fulfilled' ? 'green' : value === 'partial' ? 'orange' : 'default'}>
                        {value === 'fulfilled' ? '已发货' : value === 'partial' ? '部分发货' : '未发货'}
                      </Tag>
                    ),
                  },
                  {
                    title: '金额',
                    dataIndex: 'total',
                    align: 'right',
                    render: (value: number, row: OrderRow) => `${row.currency} ${Number(value).toFixed(2)}`,
                  },
                  {
                    title: '下单时间',
                    dataIndex: 'received_at',
                    width: 170,
                    render: (value: string) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '-'),
                  },
                ]}
              />
            </Card>
          </Col>

          <Col xs={24} xl={9}>
            <Card variant="borderless" title="零售业务动作">
              <div className="action-stack">
                <Button type="primary" icon={<ShopOutlined />} onClick={() => navigate('/b2c/products')}>
                  管理零售商品
                </Button>
                <Button icon={<ClockCircleOutlined />} onClick={() => navigate('/b2c/orders')}>
                  处理待履约订单
                </Button>
                <Button icon={<CustomerServiceOutlined />} onClick={() => navigate('/b2c/after-sales')}>
                  进入售后服务
                </Button>
                <Button icon={<MailOutlined />} onClick={() => navigate('/b2c/marketing')}>
                  查看营销活动
                </Button>
              </div>
            </Card>
          </Col>
        </Row>

        <Card variant="borderless" className="flow-card" title="B2C 标准履约流程">
          <div className="business-flow">
            {['消费者下单', '支付确认', '库存预占', '拣货出库', '国际物流', '妥投', '售后与复购'].map((step, index) => (
              <div key={step} className="business-flow__step">
                <span>{index + 1}</span>
                <strong>{step}</strong>
              </div>
            ))}
          </div>
          <div className="flow-source">
            <CheckCircleOutlined />
            页面数据来自真实订单接口；库存与物流结果以后端状态机为准。
          </div>
        </Card>
      </Skeleton>
    </div>
  )
}
