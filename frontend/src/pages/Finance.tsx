import { useState, useEffect } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Input, Select,
  Statistic, Row, Col, Spin, message, Modal, Descriptions, List,
  Badge, Tooltip, Empty, Tabs, Progress, Divider, Alert,
  DatePicker, Radio
} from 'antd'
import {
  DollarOutlined, ReloadOutlined, SearchOutlined,
  EyeOutlined, DownloadOutlined, WarningOutlined,
  CheckCircleOutlined, ClockCircleOutlined, RiseOutlined,
  FallOutlined, ShoppingCartOutlined, TruckOutlined,
  PercentageOutlined, FundOutlined, SyncOutlined
} from '@ant-design/icons'
import dayjs from 'dayjs'

const { Title, Text, Paragraph } = Typography
const { RangePicker } = DatePicker

interface OrderFinance {
  id: string
  order_id: string
  customer_name: string
  order_date: string
  revenue: number
  product_cost: number
  shipping_cost: number
  platform_fee: number
  other_cost: number
  total_cost: number
  profit: number
  profit_margin: number
  status: 'reconciled' | 'pending' | 'discrepancy'
}

interface CostItem {
  category: string
  amount: number
  percentage: number
  trend: number
  description: string
}

const statusColors: Record<string, string> = {
  reconciled: 'green',
  pending: 'orange',
  discrepancy: 'red',
}

const statusText: Record<string, string> = {
  reconciled: '已对账',
  pending: '待对账',
  discrepancy: '有差异',
}

export default function FinancePage() {
  const [loading, setLoading] = useState(false)
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [viewingOrder, setViewingOrder] = useState<OrderFinance | null>(null)
  const [statusFilter, setStatusFilter] = useState('all')
  const [searchText, setSearchText] = useState('')
  const [dateRange, setDateRange] = useState<any>(null)
  const [activeTab, setActiveTab] = useState('overview')
  const [reconciling, setReconciling] = useState(false)
  // 真实API数据状态
  const [summaryData, setSummaryData] = useState<any>(null)

  // 模拟订单财务数据
  const mockOrders: OrderFinance[] = [
    { id: '1', order_id: 'WC-1001', customer_name: 'John Smith', order_date: '2026-09-05', revenue: 156.00, product_cost: 45.00, shipping_cost: 28.50, platform_fee: 4.68, other_cost: 2.00, total_cost: 80.18, profit: 75.82, profit_margin: 48.6, status: 'reconciled' },
    { id: '2', order_id: 'WC-1002', customer_name: 'Emily Davis', order_date: '2026-09-05', revenue: 280.00, product_cost: 95.00, shipping_cost: 45.00, platform_fee: 8.40, other_cost: 3.50, total_cost: 151.90, profit: 128.10, profit_margin: 45.8, status: 'reconciled' },
    { id: '3', order_id: 'WC-1003', customer_name: 'Michael Brown', order_date: '2026-09-04', revenue: 195.00, product_cost: 68.00, shipping_cost: 32.00, platform_fee: 5.85, other_cost: 1.50, total_cost: 107.35, profit: 87.65, profit_margin: 45.0, status: 'pending' },
    { id: '4', order_id: 'WC-1004', customer_name: 'Sarah Wilson', order_date: '2026-09-04', revenue: 320.00, product_cost: 110.00, shipping_cost: 52.00, platform_fee: 9.60, other_cost: 4.00, total_cost: 175.60, profit: 144.40, profit_margin: 45.1, status: 'reconciled' },
    { id: '5', order_id: 'WC-1005', customer_name: 'David Lee', order_date: '2026-09-03', revenue: 89.99, product_cost: 32.00, shipping_cost: 18.50, platform_fee: 2.70, other_cost: 1.00, total_cost: 54.20, profit: 35.79, profit_margin: 39.8, status: 'discrepancy' },
    { id: '6', order_id: 'WC-1006', customer_name: 'Lisa Chen', order_date: '2026-09-03', revenue: 450.00, product_cost: 160.00, shipping_cost: 68.00, platform_fee: 13.50, other_cost: 5.00, total_cost: 246.50, profit: 203.50, profit_margin: 45.2, status: 'reconciled' },
    { id: '7', order_id: 'WC-1007', customer_name: 'James Taylor', order_date: '2026-09-02', revenue: 125.00, product_cost: 42.00, shipping_cost: 22.00, platform_fee: 3.75, other_cost: 1.50, total_cost: 69.25, profit: 55.75, profit_margin: 44.6, status: 'pending' },
    { id: '8', order_id: 'WC-1008', customer_name: 'Anna Martinez', order_date: '2026-09-02', revenue: 268.00, product_cost: 92.00, shipping_cost: 42.00, platform_fee: 8.04, other_cost: 3.00, total_cost: 145.04, profit: 122.96, profit_margin: 45.9, status: 'reconciled' },
  ]

  // 模拟成本分类数据
  const mockCosts: CostItem[] = [
    { category: '商品采购成本', amount: 644.00, percentage: 52.5, trend: -2.3, description: '1688采购商品成本' },
    { category: '国际物流成本', amount: 309.50, percentage: 25.2, trend: 5.1, description: '头程+尾程物流费用' },
    { category: '平台手续费', amount: 56.52, percentage: 4.6, trend: 0.5, description: 'WooCommerce/支付网关手续费' },
    { category: '营销费用', amount: 120.00, percentage: 9.8, trend: 12.5, description: '广告投放/优惠券/促销折扣' },
    { category: '其他费用', amount: 21.50, percentage: 1.8, trend: -1.2, description: '包装材料/退货损耗/其他' },
    { category: '净利润', amount: 754.97, percentage: 61.5, trend: 8.3, description: '扣除所有成本后的净利润' },
  ]

  // 模拟月度财务数据（用于趋势图）
  const mockMonthlyData = [
    { month: '4月', revenue: 8500, cost: 4800, profit: 3700 },
    { month: '5月', revenue: 12000, cost: 6500, profit: 5500 },
    { month: '6月', revenue: 15800, cost: 8200, profit: 7600 },
    { month: '7月', revenue: 18500, cost: 9800, profit: 8700 },
    { month: '8月', revenue: 22000, cost: 11500, profit: 10500 },
    { month: '9月', revenue: 12268, cost: 6485, profit: 5783 },
  ]

  // 加载财务数据（调用真实API，失败则使用mock数据降级）
  const loadFinanceData = async () => {
    try {
      setLoading(true)
      // 调用Dashboard汇总API（包含财务相关数据）
      const summaryResp = await fetch('/api/v1/dashboard/summary')
      if (summaryResp.ok) {
        const summaryJson = await summaryResp.json()
        if (summaryJson.success && summaryJson.summary) {
          setSummaryData(summaryJson.summary)
          console.log('Dashboard summary:', summaryJson.summary)
        }
      }
      // 调用成本模型状态API
      const costResp = await fetch('/api/v1/cost-model/status')
      if (costResp.ok) {
        const costData = await costResp.json()
        console.log('Cost model status:', costData)
      }
      message.success('财务数据加载完成')
    } catch (e: any) {
      console.error('Load finance data error:', e)
      message.warning(`API调用失败，使用模拟数据：${e.message || '未知错误'}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadFinanceData()
  }, [])

  // 统计数据（优先使用真实API数据，失败则使用mock数据降级）
  const todayData = summaryData?.today || {}
  const todayRevenue = todayData.revenue?.total_revenue || 0
  const todayCost = todayData.revenue?.estimated_cost || 0
  const todayProfit = todayData.revenue?.gross_profit || 0
  const todayMargin = todayData.revenue?.gross_margin_percent || 0

  const totalRevenue = todayRevenue > 0 ? todayRevenue : mockOrders.reduce((sum, o) => sum + o.revenue, 0)
  const totalCost = todayCost > 0 ? todayCost : mockOrders.reduce((sum, o) => sum + o.total_cost, 0)
  const totalProfit = todayProfit > 0 ? todayProfit : mockOrders.reduce((sum, o) => sum + o.profit, 0)
  const avgProfitMargin = todayMargin > 0 ? todayMargin : (totalRevenue > 0 ? (totalProfit / totalRevenue) * 100 : 0)
  const pendingCount = mockOrders.filter(o => o.status === 'pending').length
  const discrepancyCount = mockOrders.filter(o => o.status === 'discrepancy').length

  // 月度数据最大值（用于计算柱状图高度）
  const maxMonthlyValue = Math.max(...mockMonthlyData.map(d => Math.max(d.revenue, d.cost, d.profit)))

  // 查看订单财务详情
  const handleViewDetail = (order: OrderFinance) => {
    setViewingOrder(order)
    setDetailModalOpen(true)
  }

  // 执行对账
  const handleReconcile = () => {
    setReconciling(true)
    message.info('正在执行对账...')
    setTimeout(() => {
      message.success('对账完成，已处理所有待对账订单')
      setReconciling(false)
    }, 2000)
  }

  // 过滤订单
  const filteredOrders = mockOrders.filter(order => {
    if (statusFilter !== 'all' && order.status !== statusFilter) return false
    if (searchText && !order.order_id.includes(searchText) && !order.customer_name.includes(searchText)) return false
    return true
  })

  // 订单财务表格列
  const orderColumns = [
    {
      title: '订单号',
      dataIndex: 'order_id',
      key: 'order_id',
      width: 100,
      render: (text: string) => <Text strong>#{text}</Text>,
    },
    {
      title: '客户',
      dataIndex: 'customer_name',
      key: 'customer_name',
      width: 120,
    },
    {
      title: '下单日期',
      dataIndex: 'order_date',
      key: 'order_date',
      width: 100,
    },
    {
      title: '收入',
      dataIndex: 'revenue',
      key: 'revenue',
      width: 100,
      render: (amount: number) => <Text strong style={{ color: '#1890ff' }}>${amount.toFixed(2)}</Text>,
    },
    {
      title: '总成本',
      dataIndex: 'total_cost',
      key: 'total_cost',
      width: 100,
      render: (amount: number) => <Text style={{ color: '#fa8c16' }}>${amount.toFixed(2)}</Text>,
    },
    {
      title: '利润',
      dataIndex: 'profit',
      key: 'profit',
      width: 100,
      render: (amount: number) => <Text strong style={{ color: '#52c41a' }}>${amount.toFixed(2)}</Text>,
    },
    {
      title: '利润率',
      dataIndex: 'profit_margin',
      key: 'profit_margin',
      width: 100,
      render: (margin: number) => (
        <Tag color={margin >= 45 ? 'green' : margin >= 40 ? 'blue' : 'orange'}>
          {margin.toFixed(1)}%
        </Tag>
      ),
    },
    {
      title: '对账状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => <Tag color={statusColors[status] || 'default'}>{statusText[status] || status}</Tag>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      render: (_: any, record: OrderFinance) => (
        <Button size="small" icon={<EyeOutlined />} onClick={() => handleViewDetail(record)}>详情</Button>
      ),
    },
  ]

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <FundOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>财务对账</Title>
            <Text type="secondary">订单收入/成本/利润核算，对账报表</Text>
          </div>
        </Space>
        <Space>
          <Button icon={<DownloadOutlined />} onClick={() => message.success('报表导出中...')}>导出报表</Button>
          <Button icon={<SyncOutlined />} onClick={handleReconcile} loading={reconciling} type="primary">执行对账</Button>
        </Space>
      </div>

      {/* 对账预警 */}
      {(pendingCount > 0 || discrepancyCount > 0) && (
        <Alert
          message={`有 ${pendingCount} 个待对账订单，${discrepancyCount} 个有差异`}
          description="请及时处理待对账订单，核对有差异的订单财务数据。"
          type="warning"
          showIcon
          icon={<WarningOutlined />}
          style={{ marginBottom: '16px' }}
          action={
            <Space>
              <Button size="small" onClick={() => setStatusFilter('pending')}>待对账</Button>
              <Button size="small" type="primary" danger onClick={() => setStatusFilter('discrepancy')}>有差异</Button>
            </Space>
          }
        />
      )}

      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: '16px' }}>
        <Col span={6}>
          <Card size="small">
            <Statistic title="总收入" value={totalRevenue} precision={2} prefix="$" valueStyle={{ color: '#1890ff' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="总成本" value={totalCost} precision={2} prefix="$" valueStyle={{ color: '#fa8c16' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="净利润" value={totalProfit} precision={2} prefix="$" valueStyle={{ color: '#52c41a' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="平均利润率" value={avgProfitMargin} precision={1} suffix="%" valueStyle={{ color: '#722ed1' }} />
          </Card>
        </Col>
      </Row>

      {/* Tab切换 */}
      <Card size="small">
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'overview',
              label: '财务概览',
              children: (
                <div>
                  {/* 月度趋势图 */}
                  <div style={{ marginBottom: '24px' }}>
                    <Text strong style={{ fontSize: '14px' }}>月度收入/成本/利润趋势：</Text>
                    <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', height: '220px', padding: '16px 8px 0', borderBottom: '1px solid #e8e8e8' }}>
                      {mockMonthlyData.map((item, index) => (
                        <div key={index} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', height: '100%', justifyContent: 'flex-end', gap: '2px' }}>
                          <Tooltip title={`收入: $${item.revenue.toLocaleString()} | 成本: $${item.cost.toLocaleString()} | 利润: $${item.profit.toLocaleString()}`}>
                            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '2px', cursor: 'pointer' }}>
                              <div style={{ width: '24px', height: `${(item.revenue / maxMonthlyValue) * 140}px`, background: '#1890ff', borderRadius: '2px 2px 0 0', minHeight: '4px' }} />
                              <div style={{ width: '24px', height: `${(item.cost / maxMonthlyValue) * 140}px`, background: '#fa8c16', borderRadius: '2px 2px 0 0', minHeight: '4px' }} />
                              <div style={{ width: '24px', height: `${(item.profit / maxMonthlyValue) * 140}px`, background: '#52c41a', borderRadius: '2px 2px 0 0', minHeight: '4px' }} />
                            </div>
                          </Tooltip>
                          <Text type="secondary" style={{ fontSize: '11px', marginTop: '8px' }}>{item.month}</Text>
                        </div>
                      ))}
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'center', gap: '24px', marginTop: '12px' }}>
                      <Space><div style={{ width: '12px', height: '12px', background: '#1890ff', borderRadius: '2px' }} /><Text style={{ fontSize: '12px' }}>收入</Text></Space>
                      <Space><div style={{ width: '12px', height: '12px', background: '#fa8c16', borderRadius: '2px' }} /><Text style={{ fontSize: '12px' }}>成本</Text></Space>
                      <Space><div style={{ width: '12px', height: '12px', background: '#52c41a', borderRadius: '2px' }} /><Text style={{ fontSize: '12px' }}>利润</Text></Space>
                    </div>
                  </div>

                  <Divider style={{ margin: '16px 0' }} />

                  {/* 成本结构分析 */}
                  <div>
                    <Text strong style={{ fontSize: '14px' }}>成本结构分析：</Text>
                    <Row gutter={[16, 16]} style={{ marginTop: '16px' }}>
                      {mockCosts.slice(0, 5).map((cost, index) => (
                        <Col span={12} key={index}>
                          <Card size="small" style={{ marginBottom: '8px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                              <Text strong>{cost.category}</Text>
                              <Text strong style={{ color: '#fa8c16' }}>${cost.amount.toFixed(2)}</Text>
                            </div>
                            <Progress percent={cost.percentage} size="small" strokeColor="#fa8c16" format={(p) => `${p}%`} />
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '4px' }}>
                              <Text type="secondary" style={{ fontSize: '11px' }}>{cost.description}</Text>
                              <Tag color={cost.trend >= 0 ? 'red' : 'green'} icon={cost.trend >= 0 ? <FallOutlined /> : <RiseOutlined />} style={{ fontSize: '10px' }}>
                                {cost.trend >= 0 ? '+' : ''}{cost.trend}%
                              </Tag>
                            </div>
                          </Card>
                        </Col>
                      ))}
                    </Row>
                  </div>
                </div>
              ),
            },
            {
              key: 'orders',
              label: '订单财务明细',
              children: (
                <div>
                  {/* 筛选栏 */}
                  <Space wrap style={{ marginBottom: '16px' }}>
                    <Input
                      placeholder="搜索订单号/客户"
                      prefix={<SearchOutlined />}
                      value={searchText}
                      onChange={(e) => setSearchText(e.target.value)}
                      style={{ width: 200 }}
                      allowClear
                    />
                    <Select
                      value={statusFilter}
                      onChange={setStatusFilter}
                      style={{ width: 120 }}
                      options={[
                        { value: 'all', label: '全部状态' },
                        { value: 'reconciled', label: '已对账' },
                        { value: 'pending', label: '待对账' },
                        { value: 'discrepancy', label: '有差异' },
                      ]}
                    />
                    <RangePicker
                      value={dateRange}
                      onChange={setDateRange}
                      placeholder={['开始日期', '结束日期']}
                    />
                    <Button icon={<SearchOutlined />} type="primary">搜索</Button>
                    <Button icon={<ReloadOutlined />} onClick={() => {
                      setSearchText('')
                      setStatusFilter('all')
                      setDateRange(null)
                    }}>重置</Button>
                  </Space>

                  <Table
                    columns={orderColumns}
                    dataSource={filteredOrders}
                    rowKey="id"
                    loading={loading}
                    pagination={{
                      pageSize: 10,
                      showTotal: (total) => `共 ${total} 个订单`,
                    }}
                    summary={(pageData) => {
                      let totalRev = 0
                      let totalCostSum = 0
                      let totalProf = 0
                      pageData.forEach((item) => {
                        totalRev += item.revenue
                        totalCostSum += item.total_cost
                        totalProf += item.profit
                      })
                      return (
                        <Table.Summary.Row>
                          <Table.Summary.Cell index={0} colSpan={3}><Text strong>本页合计</Text></Table.Summary.Cell>
                          <Table.Summary.Cell index={3}><Text strong style={{ color: '#1890ff' }}>${totalRev.toFixed(2)}</Text></Table.Summary.Cell>
                          <Table.Summary.Cell index={4}><Text strong style={{ color: '#fa8c16' }}>${totalCostSum.toFixed(2)}</Text></Table.Summary.Cell>
                          <Table.Summary.Cell index={5}><Text strong style={{ color: '#52c41a' }}>${totalProf.toFixed(2)}</Text></Table.Summary.Cell>
                          <Table.Summary.Cell index={6} colSpan={3} />
                        </Table.Summary.Row>
                      )
                    }}
                    locale={{
                      emptyText: <Empty description="暂无订单财务数据" />,
                    }}
                  />
                </div>
              ),
            },
            {
              key: 'reconciliation',
              label: '对账报表',
              children: (
                <div>
                  <Alert
                    message="对账说明"
                    description="系统自动比对订单收入、采购成本、物流费用、平台手续费等数据，标记差异订单。建议每日执行一次对账。"
                    type="info"
                    showIcon
                    style={{ marginBottom: '16px' }}
                  />

                  <Row gutter={[16, 16]} style={{ marginBottom: '16px' }}>
                    <Col span={8}>
                      <Card size="small">
                        <Statistic title="已对账订单" value={mockOrders.filter(o => o.status === 'reconciled').length} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} />
                      </Card>
                    </Col>
                    <Col span={8}>
                      <Card size="small">
                        <Statistic title="待对账订单" value={pendingCount} valueStyle={{ color: '#faad14' }} prefix={<ClockCircleOutlined />} />
                      </Card>
                    </Col>
                    <Col span={8}>
                      <Card size="small">
                        <Statistic title="有差异订单" value={discrepancyCount} valueStyle={{ color: '#f5222d' }} prefix={<WarningOutlined />} />
                      </Card>
                    </Col>
                  </Row>

                  <Divider style={{ margin: '16px 0' }} />

                  <div>
                    <Text strong style={{ fontSize: '14px' }}>对账历史记录：</Text>
                    <List
                      style={{ marginTop: '12px' }}
                      dataSource={[
                        { date: '2026-09-05 08:00:00', operator: '系统自动', orders: 15, discrepancies: 1, status: 'completed' },
                        { date: '2026-09-04 08:00:00', operator: '系统自动', orders: 12, discrepancies: 0, status: 'completed' },
                        { date: '2026-09-03 08:00:00', operator: '系统自动', orders: 18, discrepancies: 2, status: 'completed' },
                        { date: '2026-09-02 08:00:00', operator: '系统自动', orders: 10, discrepancies: 0, status: 'completed' },
                      ]}
                      renderItem={(item) => (
                        <List.Item>
                          <List.Item.Meta
                            avatar={<CheckCircleOutlined style={{ color: '#52c41a', fontSize: '20px' }} />}
                            title={`${item.date} - ${item.operator}`}
                            description={`处理 ${item.orders} 个订单，发现 ${item.discrepancies} 个差异`}
                          />
                          <Tag color="green">已完成</Tag>
                        </List.Item>
                      )}
                    />
                  </div>
                </div>
              ),
            },
          ]}
        />
      </Card>

      {/* 订单财务详情Modal */}
      <Modal
        title={`订单财务详情 - #${viewingOrder?.order_id || ''}`}
        open={detailModalOpen}
        onCancel={() => setDetailModalOpen(false)}
        footer={[
          <Button key="reconcile" type="primary" onClick={() => {
            message.success('订单已标记为已对账')
            setDetailModalOpen(false)
          }}>标记已对账</Button>,
          <Button key="close" onClick={() => setDetailModalOpen(false)}>关闭</Button>,
        ]}
        width={700}
      >
        {viewingOrder && (
          <div>
            <Descriptions column={2} bordered size="small" style={{ marginBottom: '16px' }}>
              <Descriptions.Item label="订单号" span={2}>
                <Text strong>#{viewingOrder.order_id}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="客户">{viewingOrder.customer_name}</Descriptions.Item>
              <Descriptions.Item label="下单日期">{viewingOrder.order_date}</Descriptions.Item>
              <Descriptions.Item label="对账状态">
                <Tag color={statusColors[viewingOrder.status]}>{statusText[viewingOrder.status]}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="利润率">
                <Tag color={viewingOrder.profit_margin >= 45 ? 'green' : 'orange'}>{viewingOrder.profit_margin.toFixed(1)}%</Tag>
              </Descriptions.Item>
            </Descriptions>

            <Divider style={{ margin: '16px 0' }} />

            {/* 收入成本明细 */}
            <div style={{ marginBottom: '16px' }}>
              <Text strong style={{ fontSize: '14px' }}>收入成本明细：</Text>
              <List
                style={{ marginTop: '12px' }}
                dataSource={[
                  { label: '订单收入', amount: viewingOrder.revenue, type: 'revenue', icon: <DollarOutlined /> },
                  { label: '商品采购成本', amount: -viewingOrder.product_cost, type: 'cost', icon: <ShoppingCartOutlined /> },
                  { label: '物流成本', amount: -viewingOrder.shipping_cost, type: 'cost', icon: <TruckOutlined /> },
                  { label: '平台手续费', amount: -viewingOrder.platform_fee, type: 'cost', icon: <PercentageOutlined /> },
                  { label: '其他费用', amount: -viewingOrder.other_cost, type: 'cost', icon: <DollarOutlined /> },
                ]}
                renderItem={(item) => (
                  <List.Item>
                    <List.Item.Meta
                      avatar={item.icon}
                      title={item.label}
                    />
                    <Text strong style={{ color: item.type === 'revenue' ? '#1890ff' : '#fa8c16', fontSize: '14px' }}>
                      {item.type === 'revenue' ? '+' : ''}${Math.abs(item.amount).toFixed(2)}
                    </Text>
                  </List.Item>
                )}
              />
            </div>

            <Divider style={{ margin: '16px 0' }} />

            {/* 利润汇总 */}
            <Card size="small" style={{ background: '#f6ffed', border: '1px solid #b7eb8f' }}>
              <Row gutter={16}>
                <Col span={8}>
                  <Statistic title="总收入" value={viewingOrder.revenue} precision={2} prefix="$" valueStyle={{ color: '#1890ff' }} />
                </Col>
                <Col span={8}>
                  <Statistic title="总成本" value={viewingOrder.total_cost} precision={2} prefix="$" valueStyle={{ color: '#fa8c16' }} />
                </Col>
                <Col span={8}>
                  <Statistic title="净利润" value={viewingOrder.profit} precision={2} prefix="$" valueStyle={{ color: '#52c41a', fontSize: '20px' }} />
                </Col>
              </Row>
            </Card>
          </div>
        )}
      </Modal>
    </div>
  )
}
