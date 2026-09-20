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
  BankOutlined,
  CheckCircleOutlined,
  ClusterOutlined,
  FileSearchOutlined,
  LockOutlined,
  ReloadOutlined,
  ShoppingCartOutlined,
  TeamOutlined,
  WalletOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useAuth } from '../auth/AuthProvider'

const { Title, Text, Paragraph } = Typography

interface B2BStats {
  total_agents: number
  active_agents: number
  pending_agents: number
  suspended_agents: number
  total_orders: number
  total_revenue: number
  pending_orders: number
  total_credit_limit: number
  total_outstanding_balance: number
}

interface B2BOrder {
  id: string
  order_number: string
  agent_company: string
  status: string
  payment_status: string
  total: number
  currency: string
  created_at: string
}

interface B2BOrderResponse {
  items: B2BOrder[]
  total: number
}

const stageDefinitions = [
  { key: 'rfq', label: 'RFQ 询盘', icon: <FileSearchOutlined />, status: 'live' },
  { key: 'quote', label: '报价与合同', icon: <BankOutlined />, status: 'live' },
  { key: 'order', label: 'B2B 订单', icon: <ShoppingCartOutlined />, status: 'live' },
  { key: 'logistics', label: '出库与国际物流', icon: <ClusterOutlined />, status: 'live' },
  { key: 'receivable', label: '应收账款', icon: <WalletOutlined />, status: 'live' },
]

export default function B2BOverview() {
  const { authenticated, loading: authLoading } = useAuth()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [stats, setStats] = useState<B2BStats | null>(null)
  const [orders, setOrders] = useState<B2BOrderResponse>({ items: [], total: 0 })

  const load = useCallback(async () => {
    if (!authenticated) {
      setLoading(false)
      return
    }

    setLoading(true)
    setError(null)
    try {
      const [statsResponse, orderResponse] = await Promise.all([
        api.getB2BStats(),
        api.getB2BOrders(),
      ])
      setStats(statsResponse as B2BStats)
      setOrders(orderResponse as B2BOrderResponse)
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.status === 401) {
        setError('登录状态已失效，请重新登录后查看 B2B 数据。')
      } else {
        setError(requestError instanceof Error ? requestError.message : 'B2B 数据加载失败')
      }
    } finally {
      setLoading(false)
    }
  }, [authenticated])

  useEffect(() => {
    void load()
  }, [load])

  if (!authLoading && !authenticated) {
    return (
      <div className="dashboard-page">
        <div className="page-heading">
          <div>
            <div className="page-kicker page-kicker--b2b">B2B WHOLESALE OPERATIONS</div>
            <Title level={2}>B2B 批发经营</Title>
            <Paragraph>代理商、批发订单、阶梯价与账期需要在受保护的管理会话中查看。</Paragraph>
          </div>
        </div>
        <Card variant="borderless" className="auth-gate">
          <LockOutlined />
          <Title level={3}>需要登录</Title>
          <Text type="secondary">B2B 数据接口要求内部管理员身份，未登录时不会展示任何业务数字。</Text>
          <Button type="primary" onClick={() => navigate('/login?next=%2Fb2b%2Foverview')}>
            登录管理账号
          </Button>
        </Card>
      </div>
    )
  }

  return (
    <div className="dashboard-page">
      <div className="page-heading">
        <div>
          <div className="page-kicker page-kicker--b2b">B2B WHOLESALE OPERATIONS</div>
          <Title level={2}>B2B 批发经营</Title>
          <Paragraph>经销商、代理商与小 B 客户共享商品和库存，但订单、价格和账期独立管理。</Paragraph>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
          刷新
        </Button>
      </div>

      {error && (
        <Alert
          type={error.includes('登录') ? 'warning' : 'error'}
          showIcon
          title="B2B 数据当前不可用"
          description={error}
          className="page-alert"
          action={
            error.includes('登录') ? (
              <Button size="small" onClick={() => navigate('/login?next=%2Fb2b%2Foverview')}>
                重新登录
              </Button>
            ) : undefined
          }
        />
      )}

      <Skeleton active loading={loading}>
        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} xl={6}>
            <Card variant="borderless">
              <Statistic title="活跃代理商" value={stats?.active_agents ?? 0} prefix={<TeamOutlined />} />
            </Card>
          </Col>
          <Col xs={24} sm={12} xl={6}>
            <Card variant="borderless">
              <Statistic
                title="待审核"
                value={stats?.pending_agents ?? 0}
                styles={{ content: { color: stats?.pending_agents ? '#c27622' : undefined } }}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} xl={6}>
            <Card variant="borderless">
              <Statistic title="B2B 订单" value={stats?.total_orders ?? 0} prefix={<ShoppingCartOutlined />} />
            </Card>
          </Col>
          <Col xs={24} sm={12} xl={6}>
            <Card variant="borderless">
              <Statistic title="B2B 累计收入" value={stats?.total_revenue ?? 0} precision={2} prefix="$" />
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
                  <span>最近 B2B 订单</span>
                </Space>
              }
              extra={
                <Button type="link" onClick={() => navigate('/b2b/orders')}>
                  订单工作台 <ArrowRightOutlined />
                </Button>
              }
            >
              <Table
                rowKey="id"
                size="small"
                pagination={false}
                dataSource={orders.items.slice(0, 6)}
                locale={{ emptyText: '当前没有 B2B 订单' }}
                columns={[
                  { title: '订单号', dataIndex: 'order_number', render: (value: string) => <Text strong>{value}</Text> },
                  { title: '客户', dataIndex: 'agent_company', ellipsis: true },
                  {
                    title: '状态',
                    dataIndex: 'status',
                    render: (value: string) => <Tag color={value === 'delivered' ? 'green' : 'blue'}>{value}</Tag>,
                  },
                  {
                    title: '收款',
                    dataIndex: 'payment_status',
                    render: (value: string) => (
                      <Tag color={value === 'paid' ? 'green' : value === 'overdue' ? 'red' : 'orange'}>
                        {value}
                      </Tag>
                    ),
                  },
                  {
                    title: '金额',
                    dataIndex: 'total',
                    align: 'right',
                    render: (value: number, row: B2BOrder) => `${row.currency || 'USD'} ${Number(value).toFixed(2)}`,
                  },
                  {
                    title: '创建时间',
                    dataIndex: 'created_at',
                    width: 150,
                    render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm'),
                  },
                ]}
              />
            </Card>
          </Col>

          <Col xs={24} xl={9}>
            <Card variant="borderless" title="信用与应收风险">
              <div className="credit-summary">
                <div>
                  <Text type="secondary">总信用额度</Text>
                  <strong>${Number(stats?.total_credit_limit ?? 0).toLocaleString()}</strong>
                </div>
                <div>
                  <Text type="secondary">已占用额度</Text>
                  <strong className="danger">${Number(stats?.total_outstanding_balance ?? 0).toLocaleString()}</strong>
                </div>
                <div>
                  <Text type="secondary">待确认订单</Text>
                  <strong>{stats?.pending_orders ?? 0} 笔</strong>
                </div>
              </div>
              <Alert
                type="info"
                showIcon
                title="应收账款已接入"
                description="发票、收款、核销、账龄和坏账核销使用独立账簿，并同步客户余额与订单收款状态。"
                action={
                  <Button size="small" onClick={() => navigate('/b2b/receivables')}>
                    进入应收
                  </Button>
                }
              />
            </Card>
          </Col>
        </Row>

        <Card variant="borderless" className="flow-card" title="B2B 目标业务闭环">
          <div className="business-flow business-flow--b2b">
            {stageDefinitions.map((stage) => (
              <div key={stage.key} className={`business-flow__step business-flow__step--${stage.status}`}>
                <span>{stage.icon}</span>
                <strong>{stage.label}</strong>
                <small>{stage.status === 'live' ? '已接入' : '待建设'}</small>
              </div>
            ))}
          </div>
          <div className="flow-source">
            <CheckCircleOutlined />
            已接入的能力使用真实 B2B 管理接口；待建设能力跳转到明确的能力缺口页面。
          </div>
        </Card>
      </Skeleton>
    </div>
  )
}
