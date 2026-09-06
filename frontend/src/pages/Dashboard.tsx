import { useState, useEffect } from 'react'
import {
  Card, Row, Col, Statistic, Typography, Table, Tag, Progress,
  Space, Button, DatePicker, Select, Spin, message, Empty, Tooltip,
  Divider, List, Badge, Alert
} from 'antd'
import {
  DollarOutlined, ShoppingCartOutlined, RiseOutlined,
  UserOutlined, ReloadOutlined, TrophyOutlined,
  ArrowUpOutlined, ArrowDownOutlined, StockOutlined
} from '@ant-design/icons'
import dayjs from 'dayjs'

const { Title, Text, Paragraph } = Typography
const { RangePicker } = DatePicker

// 模拟数据（实际项目中从API获取）
const mockSalesData = [
  { date: '09-01', sales: 12500, orders: 45 },
  { date: '09-02', sales: 15800, orders: 52 },
  { date: '09-03', sales: 18200, orders: 61 },
  { date: '09-04', sales: 14600, orders: 48 },
  { date: '09-05', sales: 21000, orders: 72 },
  { date: '09-06', sales: 19500, orders: 65 },
  { date: '09-07', sales: 23800, orders: 78 },
]

const mockTopProducts = [
  { rank: 1, name: '便携榨汁杯', sku: 'NT-JUICER-001', sales: 156, revenue: 4680, growth: 25 },
  { rank: 2, name: 'LED头灯', sku: 'NT-LIGHT-001', sales: 142, revenue: 4260, growth: 18 },
  { rank: 3, name: '折叠露营椅', sku: 'NT-CHAIR-001', sales: 98, revenue: 6860, growth: 12 },
  { rank: 4, name: '保温水壶1L', sku: 'NT-BOTTLE-001', sales: 87, revenue: 3480, growth: -5 },
  { rank: 5, name: '太阳能露营灯', sku: 'NT-LANTERN-001', sales: 76, revenue: 3800, growth: 32 },
]

const mockOrderStatus = [
  { status: 'processing', count: 23, color: 'blue' },
  { status: 'completed', count: 156, color: 'green' },
  { status: 'pending', count: 12, color: 'orange' },
  { status: 'cancelled', count: 8, color: 'default' },
  { status: 'refunded', count: 3, color: 'red' },
]

const mockSourcingEffect = [
  { category: '露营装备', products: 12, listed: 8, sold: 156, conversion: 6.5 },
  { category: '照明设备', products: 8, listed: 6, sold: 218, conversion: 8.2 },
  { category: '户外厨房', products: 10, listed: 7, sold: 98, conversion: 5.1 },
  { category: '户外服装', products: 6, listed: 3, sold: 45, conversion: 3.8 },
  { category: '户外配件', products: 15, listed: 10, sold: 187, conversion: 7.3 },
]

export default function DashboardPage() {
  const [loading, setLoading] = useState(false)
  const [dateRange, setDateRange] = useState<any>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  // 真实API数据状态
  const [summaryData, setSummaryData] = useState<any>(null)
  const [productPerformance, setProductPerformance] = useState<any[]>([])

  // 加载数据
  const loadData = async () => {
    setLoading(true)
    try {
      // 调用真实API获取汇总数据
      const summaryResp = await fetch('/api/v1/dashboard/summary')
      const summaryJson = await summaryResp.json()
      if (summaryJson.success && summaryJson.summary) {
        setSummaryData(summaryJson.summary)
      }

      // 调用真实API获取产品表现排行
      const perfResp = await fetch('/api/v1/dashboard/product-performance?limit=5')
      const perfJson = await perfResp.json()
      if (perfJson.success && perfJson.performance) {
        setProductPerformance(perfJson.performance)
      }

      message.success('数据加载完成')
    } catch (e: any) {
      console.error('Load dashboard data error:', e)
      message.warning(`API调用失败，使用模拟数据：${e.message || '未知错误'}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [refreshKey])

  // 计算统计数据（优先使用真实API数据，失败则使用mock数据降级）
  const keyMetrics = summaryData?.key_metrics || {}
  const totalSales = keyMetrics.today_revenue || mockSalesData.reduce((sum, d) => sum + d.sales, 0)
  const totalOrders = keyMetrics.today_orders || mockSalesData.reduce((sum, d) => sum + d.orders, 0)
  const avgOrderValue = totalOrders > 0 ? totalSales / totalOrders : 0
  const conversionRate = keyMetrics.conversion_rate || 5.8 // 模拟转化率

  // 销售趋势最大值（用于计算柱状图高度）
  const maxSales = Math.max(...mockSalesData.map(d => d.sales))

  // 订单状态总数
  const totalOrderStatus = mockOrderStatus.reduce((sum, s) => sum + s.count, 0)

  // 产品表现数据（优先使用真实API数据）
  const topProducts = productPerformance.length > 0 ? productPerformance.map((p: any, idx: number) => ({
    rank: idx + 1,
    name: p.product_name || p.name || '-',
    sku: p.sku || '-',
    sales: p.units_sold || p.sales || 0,
    revenue: p.revenue || 0,
    growth: p.growth_rate || 0,
  })) : mockTopProducts

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <StockOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>数据看板</Title>
            <Text type="secondary">销售数据、选品效果、转化率可视化分析</Text>
          </div>
        </Space>
        <Space>
          <RangePicker
            showTime
            value={dateRange}
            onChange={setDateRange}
            placeholder={['开始日期', '结束日期']}
          />
          <Select
            defaultValue="7days"
            style={{ width: 120 }}
            options={[
              { value: 'today', label: '今天' },
              { value: '7days', label: '近7天' },
              { value: '30days', label: '近30天' },
              { value: '90days', label: '近90天' },
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={() => setRefreshKey(k => k + 1)} loading={loading}>刷新</Button>
        </Space>
      </div>

      <Spin spinning={loading}>
        {/* 统计卡片 */}
        <Row gutter={[16, 16]} style={{ marginBottom: '16px' }}>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="总销售额"
                value={totalSales}
                precision={2}
                prefix={<DollarOutlined />}
                valueStyle={{ color: '#722ed1' }}
                suffix={<Tooltip title="较上周 +12.5%"><Tag color="green" icon={<ArrowUpOutlined />}>+12.5%</Tag></Tooltip>}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="订单数"
                value={totalOrders}
                prefix={<ShoppingCartOutlined />}
                valueStyle={{ color: '#1890ff' }}
                suffix={<Tooltip title="较上周 +8.3%"><Tag color="green" icon={<ArrowUpOutlined />}>+8.3%</Tag></Tooltip>}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="客单价"
                value={avgOrderValue}
                precision={2}
                prefix={<DollarOutlined />}
                valueStyle={{ color: '#52c41a' }}
                suffix={<Tooltip title="较上周 +3.8%"><Tag color="green" icon={<ArrowUpOutlined />}>+3.8%</Tag></Tooltip>}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="转化率"
                value={conversionRate}
                precision={1}
                suffix="%"
                prefix={<RiseOutlined />}
                valueStyle={{ color: '#fa8c16' }}
              />
            </Card>
          </Col>
        </Row>

        {/* 销售趋势 + 订单状态 */}
        <Row gutter={[16, 16]} style={{ marginBottom: '16px' }}>
          <Col span={16}>
            <Card
              size="small"
              title={
                <Space>
                  <RiseOutlined />
                  <span>销售趋势</span>
                  <Tag color="blue">近7天</Tag>
                </Space>
              }
              extra={<Text type="secondary">总销售额: ${totalSales.toLocaleString()}</Text>}
            >
              {/* 简单柱状图 */}
              <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', height: '200px', padding: '0 8px' }}>
                {mockSalesData.map((item, index) => (
                  <div key={index} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', height: '100%', justifyContent: 'flex-end' }}>
                    <Tooltip title={`${item.date}: $${item.sales.toLocaleString()} / ${item.orders}单`}>
                      <div
                        style={{
                          width: '60%',
                          height: `${(item.sales / maxSales) * 160}px`,
                          background: 'linear-gradient(180deg, #722ed1 0%, #9254de 100%)',
                          borderRadius: '4px 4px 0 0',
                          minHeight: '4px',
                          transition: 'height 0.3s',
                          cursor: 'pointer',
                        }}
                      />
                    </Tooltip>
                    <Text type="secondary" style={{ fontSize: '11px', marginTop: '8px' }}>{item.date}</Text>
                    <Text strong style={{ fontSize: '11px', color: '#722ed1' }}>${(item.sales / 1000).toFixed(1)}k</Text>
                  </div>
                ))}
              </div>
              <Divider style={{ margin: '12px 0' }} />
              <Row gutter={16}>
                <Col span={8}>
                  <Statistic title="日均销售额" value={(totalSales / 7).toFixed(0)} prefix="$" size="small" />
                </Col>
                <Col span={8}>
                  <Statistic title="日均订单" value={(totalOrders / 7).toFixed(0)} size="small" />
                </Col>
                <Col span={8}>
                  <Statistic title="最高日销售" value={Math.max(...mockSalesData.map(d => d.sales)).toLocaleString()} prefix="$" size="small" valueStyle={{ color: '#52c41a' }} />
                </Col>
              </Row>
            </Card>
          </Col>

          <Col span={8}>
            <Card
              size="small"
              title={
                <Space>
                  <ShoppingCartOutlined />
                  <span>订单状态分布</span>
                </Space>
              }
            >
              <List
                size="small"
                dataSource={mockOrderStatus}
                renderItem={(item) => (
                  <List.Item>
                    <List.Item.Meta
                      title={<Tag color={item.color}>{item.status === 'processing' ? '处理中' : item.status === 'completed' ? '已完成' : item.status === 'pending' ? '待支付' : item.status === 'cancelled' ? '已取消' : '已退款'}</Tag>}
                      description={`${item.count} 单 (${((item.count / totalOrderStatus) * 100).toFixed(1)}%)`}
                    />
                    <Progress
                      percent={((item.count / totalOrderStatus) * 100)}
                      size="small"
                      style={{ width: '80px' }}
                      strokeColor={item.color === 'blue' ? '#1890ff' : item.color === 'green' ? '#52c41a' : item.color === 'orange' ? '#fa8c16' : item.color === 'red' ? '#ff4d4f' : '#999'}
                      showInfo={false}
                    />
                  </List.Item>
                )}
              />
            </Card>
          </Col>
        </Row>

        {/* 热销产品排行 + 选品效果 */}
        <Row gutter={[16, 16]}>
          <Col span={12}>
            <Card
              size="small"
              title={
                <Space>
                  <TrophyOutlined />
                  <span>热销产品 TOP 5</span>
                </Space>
              }
              extra={<Button type="link" size="small">查看全部</Button>}
            >
              <Table
                dataSource={topProducts}
                rowKey="rank"
                size="small"
                pagination={false}
                columns={[
                  {
                    title: '排名',
                    dataIndex: 'rank',
                    key: 'rank',
                    width: 60,
                    render: (rank: number) => (
                      <Badge
                        count={rank}
                        style={{
                          backgroundColor: rank === 1 ? '#fadb14' : rank === 2 ? '#d9d9d9' : rank === 3 ? '#d48806' : '#722ed1',
                          fontSize: '12px',
                        }}
                      />
                    ),
                  },
                  {
                    title: '产品名称',
                    dataIndex: 'name',
                    key: 'name',
                    render: (text: string, record: any) => (
                      <div>
                        <div style={{ fontWeight: 500 }}>{text}</div>
                        <div style={{ color: '#999', fontSize: '11px' }}>SKU: {record.sku}</div>
                      </div>
                    ),
                  },
                  {
                    title: '销量',
                    dataIndex: 'sales',
                    key: 'sales',
                    width: 80,
                    render: (sales: number) => <Text strong>{sales}</Text>,
                  },
                  {
                    title: '销售额',
                    dataIndex: 'revenue',
                    key: 'revenue',
                    width: 100,
                    render: (revenue: number) => <Text strong style={{ color: '#722ed1' }}>${revenue}</Text>,
                  },
                  {
                    title: '增长',
                    dataIndex: 'growth',
                    key: 'growth',
                    width: 80,
                    render: (growth: number) => (
                      <Tag color={growth >= 0 ? 'green' : 'red'} icon={growth >= 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />}>
                        {growth >= 0 ? '+' : ''}{growth}%
                      </Tag>
                    ),
                  },
                ]}
              />
            </Card>
          </Col>

          <Col span={12}>
            <Card
              size="small"
              title={
                <Space>
                  <RiseOutlined />
                  <span>选品效果分析</span>
                </Space>
              }
              extra={<Tag color="purple">按类目</Tag>}
            >
              <Table
                dataSource={mockSourcingEffect}
                rowKey="category"
                size="small"
                pagination={false}
                columns={[
                  {
                    title: '类目',
                    dataIndex: 'category',
                    key: 'category',
                    render: (text: string) => <Text strong>{text}</Text>,
                  },
                  {
                    title: '选品数',
                    dataIndex: 'products',
                    key: 'products',
                    width: 70,
                    render: (num: number) => num,
                  },
                  {
                    title: '上架数',
                    dataIndex: 'listed',
                    key: 'listed',
                    width: 70,
                    render: (num: number, record: any) => (
                      <div>
                        <Text>{num}</Text>
                        <Progress
                          percent={(num / record.products) * 100}
                          size="small"
                          style={{ width: '50px', marginTop: '4px' }}
                          showInfo={false}
                          strokeColor="#722ed1"
                        />
                      </div>
                    ),
                  },
                  {
                    title: '销量',
                    dataIndex: 'sold',
                    key: 'sold',
                    width: 70,
                    render: (num: number) => <Text strong>{num}</Text>,
                  },
                  {
                    title: '转化率',
                    dataIndex: 'conversion',
                    key: 'conversion',
                    width: 90,
                    render: (rate: number) => (
                      <Tag color={rate >= 7 ? 'green' : rate >= 5 ? 'blue' : 'orange'}>
                        {rate}%
                      </Tag>
                    ),
                  },
                ]}
              />
              <Divider style={{ margin: '12px 0' }} />
              <Alert
                message="选品建议"
                description="照明设备类目转化率最高(8.2%)，建议增加该类目选品投入；户外服装类目转化率最低(3.8%)，建议优化选品策略。"
                type="info"
                showIcon
              />
            </Card>
          </Col>
        </Row>
      </Spin>
    </div>
  )
}
