import { useEffect, useState } from 'react'
import { Row, Col, Card, Statistic, Table, Tag, Spin, Alert, Progress } from 'antd'
import {
  DollarOutlined,
  ShoppingCartOutlined,
  RiseOutlined,
  FallOutlined,
  TeamOutlined,
  WarningOutlined,
  TruckOutlined,
} from '@ant-design/icons'
import { api } from '../api/client'

interface KeyMetrics {
  today_revenue: number
  today_orders: number
  today_gross_margin: number
  today_roas: number
  week_revenue: number
  week_orders: number
  month_revenue: number
  month_orders: number
}

interface Trend {
  change_percent: number
  direction: string
}

interface Product {
  rank: number
  name: string
  sku: string
  units_sold: number
  revenue: number
  gross_margin: number
  trend: string
}

export default function DashboardPage() {
  const [loading, setLoading] = useState(true)
  const [metrics, setMetrics] = useState<KeyMetrics | null>(null)
  const [trends, setTrends] = useState<Record<string, Trend>>({})
  const [products, setProducts] = useState<Product[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true)
        const [keyData, productData] = await Promise.all([
          api.getKeyMetrics(),
          api.getProductPerformance(5),
        ]) as any
        setMetrics(keyData.key_metrics)
        setTrends(keyData.trends)
        setProducts(productData.performance?.products || [])
      } catch (e: any) {
        setError(e.message)
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [])

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />
  if (error) return <Alert type="error" message={`加载失败: ${error}`} description="请确保后端服务运行在 http://localhost:8000" showIcon />

  const revenueTrend = trends?.revenue_week_over_week
  const ordersTrend = trends?.orders_week_over_week

  const columns = [
    { title: '排名', dataIndex: 'rank', key: 'rank', width: 60 },
    { title: '产品名称', dataIndex: 'name', key: 'name' },
    { title: 'SKU', dataIndex: 'sku', key: 'sku' },
    { title: '销量', dataIndex: 'units_sold', key: 'units_sold', sorter: (a: Product, b: Product) => a.units_sold - b.units_sold },
    { title: '收入', dataIndex: 'revenue', key: 'revenue', render: (v: number) => `$${v.toLocaleString()}`, sorter: (a: Product, b: Product) => a.revenue - b.revenue },
    { title: '毛利率', dataIndex: 'gross_margin', key: 'gross_margin', render: (v: number) => `${v}%` },
    {
      title: '趋势',
      dataIndex: 'trend',
      key: 'trend',
      render: (v: string) => {
        const colorMap: Record<string, string> = { up: 'green', down: 'red', flat: 'default' }
        const iconMap: Record<string, any> = { up: <RiseOutlined />, down: <FallOutlined />, flat: '-' }
        return <Tag color={colorMap[v]} icon={iconMap[v]}>{v === 'up' ? '上升' : v === 'down' ? '下降' : '持平'}</Tag>
      },
    },
  ]

  return (
    <div>
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <Card className="stat-card">
            <Statistic
              title="今日收入"
              value={metrics?.today_revenue || 0}
              prefix={<DollarOutlined />}
              precision={2}
              suffix="USD"
              valueStyle={{ color: '#3f8600' }}
            />
            {revenueTrend && (
              <div style={{ marginTop: 8 }}>
                <Tag color={revenueTrend.direction === 'up' ? 'green' : 'red'}>
                  周环比 {revenueTrend.change_percent}%
                </Tag>
              </div>
            )}
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card className="stat-card">
            <Statistic
              title="今日订单"
              value={metrics?.today_orders || 0}
              prefix={<ShoppingCartOutlined />}
              valueStyle={{ color: '#1677ff' }}
            />
            {ordersTrend && (
              <div style={{ marginTop: 8 }}>
                <Tag color={ordersTrend.direction === 'up' ? 'green' : 'red'}>
                  周环比 {ordersTrend.change_percent}%
                </Tag>
              </div>
            )}
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card className="stat-card">
            <Statistic
              title="毛利率"
              value={metrics?.today_gross_margin || 0}
              suffix="%"
              valueStyle={{ color: metrics && metrics.today_gross_margin >= 30 ? '#3f8600' : '#cf1322' }}
            />
            <div style={{ marginTop: 8 }}>
              <Progress percent={metrics?.today_gross_margin || 0} size="small" status={metrics && metrics.today_gross_margin >= 30 ? 'success' : 'exception'} />
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card className="stat-card">
            <Statistic
              title="广告 ROAS"
              value={metrics?.today_roas || 0}
              precision={2}
              valueStyle={{ color: '#722ed1' }}
            />
            <div style={{ marginTop: 8 }}>
              <Tag color="blue">行业基准 3.0</Tag>
            </div>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={16}>
          <Card title="畅销产品 TOP 5" extra={<Tag color="blue">本周</Tag>}>
            <Table
              dataSource={products}
              columns={columns}
              rowKey="rank"
              pagination={false}
              size="small"
            />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="经营概览">
            <Row gutter={[16, 16]}>
              <Col span={12}>
                <Statistic title="本周收入" value={metrics?.week_revenue || 0} prefix={<DollarOutlined />} precision={2} />
              </Col>
              <Col span={12}>
                <Statistic title="本周订单" value={metrics?.week_orders || 0} prefix={<ShoppingCartOutlined />} />
              </Col>
              <Col span={12}>
                <Statistic title="本月收入" value={metrics?.month_revenue || 0} prefix={<DollarOutlined />} precision={2} />
              </Col>
              <Col span={12}>
                <Statistic title="本月订单" value={metrics?.month_orders || 0} prefix={<ShoppingCartOutlined />} />
              </Col>
            </Row>
          </Card>
          <Card title="快捷入口" style={{ marginTop: 16 }}>
            <Row gutter={[8, 8]}>
              <Col span={12}><Tag icon={<WarningOutlined />} color="red">3 个待处理预警</Tag></Col>
              <Col span={12}><Tag icon={<TeamOutlined />} color="blue">1 个活跃代理商</Tag></Col>
              <Col span={12}><Tag icon={<ShoppingCartOutlined />} color="green">2 个仓库运营中</Tag></Col>
              <Col span={12}><Tag icon={<TruckOutlined />} color="orange">1 个在途入库单</Tag></Col>
            </Row>
          </Card>
        </Col>
      </Row>
    </div>
  )
}
