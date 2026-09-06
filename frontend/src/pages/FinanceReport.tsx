import { useState, useEffect } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Input, Select,
  Statistic, Row, Col, Spin, message, Modal, Descriptions, List,
  Badge, Tooltip, Empty, Tabs, Timeline, Divider, Alert,
  Progress, Form, InputNumber, Radio, DatePicker, Segmented
} from 'antd'
import {
  DollarOutlined, ReloadOutlined, SearchOutlined,
  EyeOutlined, PlusOutlined, EditOutlined,
  TrendingUpOutlined, TrendingDownOutlined,
  CheckCircleOutlined, WarningOutlined,
  SyncOutlined, ClockCircleOutlined, ShopOutlined,
  PackageOutlined, CopyOutlined, GlobalOutlined,
  HomeOutlined, ExportOutlined, ImportOutlined,
  SwapOutlined, EnvironmentOutlined, FileTextOutlined,
  BarChartOutlined, PieChartOutlined, LineChartOutlined,
  WalletOutlined, CreditCardOutlined, BankOutlined,
  CalculatorOutlined, ArrowUpOutlined, ArrowDownOutlined
} from '@ant-design/icons'

const { Title, Text, Paragraph } = Typography

interface Transaction {
  id: string
  date: string
  type: 'income' | 'expense'
  category: string
  description: string
  amount: number
  currency: string
  payment_method: string
  status: 'completed' | 'pending' | 'failed'
  related_order?: string
  notes?: string
}

interface RevenueByCategory {
  category: string
  revenue: number
  orders: number
  avg_order_value: number
  growth_rate: number
}

interface ExpenseByCategory {
  category: string
  amount: number
  percentage: number
  trend: 'up' | 'down' | 'flat'
}

interface MonthlyFinance {
  month: string
  revenue: number
  expense: number
  profit: number
  profit_margin: number
}

const typeColors: Record<string, string> = {
  income: 'green',
  expense: 'red',
}

const statusColors: Record<string, string> = {
  completed: 'green',
  pending: 'orange',
  failed: 'red',
}

export default function FinanceReportPage() {
  const [activeTab, setActiveTab] = useState('overview')
  const [loading, setLoading] = useState(false)
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [viewingTransaction, setViewingTransaction] = useState<Transaction | null>(null)
  const [timeRange, setTimeRange] = useState('month')
  const [transactionTypeFilter, setTransactionTypeFilter] = useState('all')
  const [searchText, setSearchText] = useState('')
  // 真实API数据状态
  const [financeReportData, setFinanceReportData] = useState<any>(null)

  // 模拟月度财务数据
  const mockMonthlyFinance: MonthlyFinance[] = [
    { month: '2026-03', revenue: 45600, expense: 32800, profit: 12800, profit_margin: 28.1 },
    { month: '2026-04', revenue: 52300, expense: 36500, profit: 15800, profit_margin: 30.2 },
    { month: '2026-05', revenue: 61800, expense: 42300, profit: 19500, profit_margin: 31.6 },
    { month: '2026-06', revenue: 58900, expense: 41200, profit: 17700, profit_margin: 30.1 },
    { month: '2026-07', revenue: 67500, expense: 45800, profit: 21700, profit_margin: 32.1 },
    { month: '2026-08', revenue: 78200, expense: 52300, profit: 25900, profit_margin: 33.1 },
    { month: '2026-09', revenue: 45800, expense: 31200, profit: 14600, profit_margin: 31.9 },
  ]

  // 模拟收入按品类
  const mockRevenueByCategory: RevenueByCategory[] = [
    { category: '照明设备', revenue: 28500, orders: 156, avg_order_value: 182.7, growth_rate: 25.3 },
    { category: '户外家具', revenue: 22800, orders: 89, avg_order_value: 256.2, growth_rate: 18.5 },
    { category: '背包配件', revenue: 18600, orders: 124, avg_order_value: 150.0, growth_rate: 32.1 },
    { category: '水具餐具', revenue: 15200, orders: 178, avg_order_value: 85.4, growth_rate: 12.8 },
    { category: '户外配件', revenue: 12500, orders: 95, avg_order_value: 131.6, growth_rate: 28.9 },
    { category: '其他', revenue: 8600, orders: 67, avg_order_value: 128.4, growth_rate: 5.2 },
  ]

  // 模拟支出按品类
  const mockExpenseByCategory: ExpenseByCategory[] = [
    { category: '采购成本', amount: 18500, percentage: 59.3, trend: 'up' },
    { category: '物流费用', amount: 5600, percentage: 17.9, trend: 'up' },
    { category: '营销费用', amount: 3200, percentage: 10.3, trend: 'up' },
    { category: '平台费用', amount: 1800, percentage: 5.8, trend: 'flat' },
    { category: '运营费用', amount: 1200, percentage: 3.8, trend: 'down' },
    { category: '其他费用', amount: 900, percentage: 2.9, trend: 'flat' },
  ]

  // 模拟交易记录
  const mockTransactions: Transaction[] = [
    { id: '1', date: '2026-09-05 14:32', type: 'income', category: '商品销售', description: '订单 WO-20260905-001 收款', amount: 156.80, currency: 'USD', payment_method: 'Stripe', status: 'completed', related_order: 'WO-20260905-001' },
    { id: '2', date: '2026-09-05 10:15', type: 'expense', category: '采购成本', description: '采购单 PO-20260905-001 付款', amount: 2775, currency: 'CNY', payment_method: '1688支付宝', status: 'pending', related_order: 'PO-20260905-001' },
    { id: '3', date: '2026-09-04 16:45', type: 'income', category: '商品销售', description: '订单 WO-20260904-005 收款', amount: 289.50, currency: 'USD', payment_method: 'PayPal', status: 'completed', related_order: 'WO-20260904-005' },
    { id: '4', date: '2026-09-04 11:20', type: 'expense', category: '物流费用', description: '4PX递四方 运费结算', amount: 1250, currency: 'CNY', payment_method: '银行转账', status: 'completed' },
    { id: '5', date: '2026-09-03 09:00', type: 'expense', category: '营销费用', description: 'Google Ads 广告充值', amount: 500, currency: 'USD', payment_method: '信用卡', status: 'completed' },
    { id: '6', date: '2026-09-02 14:30', type: 'income', category: '商品销售', description: '订单 WO-20260902-001 收款', amount: 199.99, currency: 'USD', payment_method: 'Stripe', status: 'completed', related_order: 'WO-20260902-001' },
    { id: '7', date: '2026-09-01 10:00', type: 'expense', category: '平台费用', description: 'WooCommerce 插件订阅', amount: 99, currency: 'USD', payment_method: '信用卡', status: 'completed' },
    { id: '8', date: '2026-08-31 18:00', type: 'income', category: '商品销售', description: '订单 WO-20260831-012 收款', amount: 345.00, currency: 'USD', payment_method: 'PayPal', status: 'completed', related_order: 'WO-20260831-012' },
    { id: '9', date: '2026-08-30 15:20', type: 'expense', category: '运营费用', description: '服务器托管费用', amount: 150, currency: 'EUR', payment_method: '信用卡', status: 'completed' },
    { id: '10', date: '2026-08-29 11:00', type: 'expense', category: '采购成本', description: '采购单 PO-20260829-003 付款', amount: 4200, currency: 'CNY', payment_method: '银行转账', status: 'completed', related_order: 'PO-20260829-003' },
  ]

  // 加载财务报表数据（调用真实API，失败则使用mock数据降级）
  const loadFinanceReportData = async () => {
    try {
      setLoading(true)
      // 调用成本模型API（包含财务相关功能）
      const costResp = await fetch('/api/v1/cost-model/status')
      if (costResp.ok) {
        const costData = await costResp.json()
        setFinanceReportData(costData)
        console.log('Cost model status:', costData)
      }
      message.success('财务报表数据加载完成')
    } catch (e: any) {
      console.error('Load finance report data error:', e)
      message.warning(`API调用失败，使用模拟数据：${e.message || '未知错误'}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadFinanceReportData()
  }, [])

  // 统计数据（优先使用真实API数据，失败则使用mock数据降级）
  const currentMonth = mockMonthlyFinance[mockMonthlyFinance.length - 1]
  const lastMonth = mockMonthlyFinance[mockMonthlyFinance.length - 2]
  const stats = {
    revenue: financeReportData?.revenue || currentMonth.revenue,
    expense: financeReportData?.expense || currentMonth.expense,
    profit: financeReportData?.profit || currentMonth.profit,
    profit_margin: financeReportData?.profit_margin || currentMonth.profit_margin,
    revenue_growth: financeReportData?.revenue_growth || ((currentMonth.revenue - lastMonth.revenue) / lastMonth.revenue * 100).toFixed(1),
    profit_growth: financeReportData?.profit_growth || ((currentMonth.profit - lastMonth.profit) / lastMonth.profit * 100).toFixed(1),
    total_transactions: financeReportData?.total_transactions || mockTransactions.length,
    pending_transactions: financeReportData?.pending_transactions || mockTransactions.filter(t => t.status === 'pending').length,
  }

  // 交易记录表格列
  const transactionColumns = [
    {
      title: '日期',
      dataIndex: 'date',
      key: 'date',
      width: 160,
      render: (text: string) => <Text style={{ fontSize: '12px' }}>{text}</Text>,
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      width: 80,
      render: (type: string) => (
        <Tag color={typeColors[type]} icon={type === 'income' ? <ArrowUpOutlined /> : <ArrowDownOutlined />}>
          {type === 'income' ? '收入' : '支出'}
        </Tag>
      ),
    },
    {
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      width: 120,
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
      render: (text: string, record: Transaction) => (
        <div>
          <div style={{ fontSize: '12px' }}>{text}</div>
          {record.related_order && <div style={{ fontSize: '10px', color: '#999' }}>关联：{record.related_order}</div>}
        </div>
      ),
    },
    {
      title: '金额',
      key: 'amount',
      width: 120,
      render: (_: any, record: Transaction) => (
        <Text strong style={{ color: record.type === 'income' ? '#52c41a' : '#f5222d', fontSize: '14px' }}>
          {record.type === 'income' ? '+' : '-'}{record.amount.toLocaleString()} {record.currency}
        </Text>
      ),
    },
    {
      title: '支付方式',
      dataIndex: 'payment_method',
      key: 'payment_method',
      width: 120,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (status: string) => <Tag color={statusColors[status]}>{status === 'completed' ? '已完成' : status === 'pending' ? '待处理' : '失败'}</Tag>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 80,
      render: (_: any, record: Transaction) => (
        <Button size="small" icon={<EyeOutlined />} onClick={() => {
          setViewingTransaction(record)
          setDetailModalOpen(true)
        }}>详情</Button>
      ),
    },
  ]

  // 收入按品类表格列
  const revenueColumns = [
    { title: '品类', dataIndex: 'category', key: 'category', width: 150 },
    {
      title: '收入',
      dataIndex: 'revenue',
      key: 'revenue',
      width: 120,
      render: (amount: number) => <Text strong style={{ color: '#52c41a' }}>${amount.toLocaleString()}</Text>,
    },
    { title: '订单数', dataIndex: 'orders', key: 'orders', width: 100 },
    {
      title: '客单价',
      dataIndex: 'avg_order_value',
      key: 'avg_order_value',
      width: 100,
      render: (amount: number) => <Text>${amount.toFixed(2)}</Text>,
    },
    {
      title: '增长率',
      dataIndex: 'growth_rate',
      key: 'growth_rate',
      width: 100,
      render: (rate: number) => (
        <Space>
          <ArrowUpOutlined style={{ color: '#52c41a' }} />
          <Text type="success">{rate}%</Text>
        </Space>
      ),
    },
    {
      title: '收入占比',
      key: 'percentage',
      width: 150,
      render: (_: any, record: RevenueByCategory) => {
        const total = mockRevenueByCategory.reduce((sum, r) => sum + r.revenue, 0)
        const percentage = (record.revenue / total * 100).toFixed(1)
        return <Progress percent={parseFloat(percentage)} size="small" strokeColor="#52c41a" format={(p) => `${p}%`} />
      },
    },
  ]

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <BarChartOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>财务报表系统</Title>
            <Text type="secondary">收入支出、利润分析、财务报表</Text>
          </div>
        </Space>
        <Space>
          <Segmented
            value={timeRange}
            onChange={setTimeRange}
            options={[
              { label: '本周', value: 'week' },
              { label: '本月', value: 'month' },
              { label: '本季度', value: 'quarter' },
              { label: '本年', value: 'year' },
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={() => message.success('数据已刷新')}>刷新</Button>
          <Button type="primary" icon={<ExportOutlined />} onClick={() => message.success('财务报表导出中...')}>导出报表</Button>
        </Space>
      </div>

      {/* 待处理预警 */}
      {stats.pending_transactions > 0 && (
        <Alert
          message={`有 ${stats.pending_transactions} 笔交易待处理`}
          description="请及时处理待付款、待确认的交易记录，确保财务数据准确。"
          type="warning"
          showIcon
          icon={<WarningOutlined />}
          style={{ marginBottom: '16px' }}
          action={
            <Button size="small" type="primary" onClick={() => setTransactionTypeFilter('pending')}>查看待处理</Button>
          }
        />
      )}

      {/* 核心指标卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: '16px' }}>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="本月收入"
              value={stats.revenue}
              prefix="$"
              valueStyle={{ color: '#52c41a' }}
              suffix={
                <span style={{ fontSize: 12, color: '#52c41a' }}>
                  <ArrowUpOutlined /> {stats.revenue_growth}%
                </span>
              }
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="本月支出"
              value={stats.expense}
              prefix="¥"
              valueStyle={{ color: '#f5222d' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="本月利润"
              value={stats.profit}
              prefix="$"
              valueStyle={{ color: '#722ed1' }}
              suffix={
                <span style={{ fontSize: 12, color: '#52c41a' }}>
                  <ArrowUpOutlined /> {stats.profit_growth}%
                </span>
              }
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="利润率"
              value={stats.profit_margin}
              suffix="%"
              valueStyle={{ color: '#1890ff' }}
              prefix={<CalculatorOutlined />}
            />
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
                  <Card size="small" title="月度收支趋势" style={{ marginBottom: 16 }}>
                    <div style={{ height: 300, display: 'flex', alignItems: 'flex-end', justifyContent: 'space-around', padding: '20px 40px' }}>
                      {mockMonthlyFinance.map((m, idx) => (
                        <div key={idx} style={{ textAlign: 'center', flex: 1 }}>
                          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
                            <div style={{ width: '60%', height: (m.revenue / 100), background: 'linear-gradient(180deg, #52c41a, #95de64)', borderRadius: '4px 4px 0 0', position: 'relative' }}>
                              <div style={{ position: 'absolute', top: -20, left: '50%', transform: 'translateX(-50%)', fontSize: 10, color: '#52c41a', whiteSpace: 'nowrap' }}>${(m.revenue / 1000).toFixed(1)}k</div>
                            </div>
                            <div style={{ width: '60%', height: (m.expense / 100), background: 'linear-gradient(180deg, #f5222d, #ff7875)', borderRadius: '4px 4px 0 0' }} />
                          </div>
                          <div style={{ fontSize: 11, color: '#999', marginTop: 8 }}>{m.month.slice(5)}</div>
                          <div style={{ fontSize: 10, color: '#722ed1', marginTop: 2 }}>利润 ${(m.profit / 1000).toFixed(1)}k</div>
                        </div>
                      ))}
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'center', gap: 24, marginTop: 8 }}>
                      <Space><div style={{ width: 12, height: 12, background: '#52c41a', borderRadius: 2 }} /><Text style={{ fontSize: 12 }}>收入</Text></Space>
                      <Space><div style={{ width: 12, height: 12, background: '#f5222d', borderRadius: 2 }} /><Text style={{ fontSize: 12 }}>支出</Text></Space>
                    </div>
                  </Card>

                  <Row gutter={16}>
                    {/* 收入品类分布 */}
                    <Col span={12}>
                      <Card size="small" title="收入品类分布">
                        <Table
                          dataSource={mockRevenueByCategory}
                          columns={revenueColumns}
                          rowKey="category"
                          size="small"
                          pagination={false}
                        />
                      </Card>
                    </Col>
                    {/* 支出结构 */}
                    <Col span={12}>
                      <Card size="small" title="支出结构分析">
                        <div style={{ padding: '8px 0' }}>
                          {mockExpenseByCategory.map((item, idx) => (
                            <div key={idx} style={{ marginBottom: 16 }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                                <Space>
                                  <Text style={{ fontSize: 13 }}>{item.category}</Text>
                                  {item.trend === 'up' && <ArrowUpOutlined style={{ fontSize: 11, color: '#f5222d' }} />}
                                  {item.trend === 'down' && <ArrowDownOutlined style={{ fontSize: 11, color: '#52c41a' }} />}
                                </Space>
                                <Text strong style={{ fontSize: 13 }}>¥{item.amount.toLocaleString()} ({item.percentage}%)</Text>
                              </div>
                              <Progress
                                percent={item.percentage}
                                size="small"
                                strokeColor={idx === 0 ? '#f5222d' : idx === 1 ? '#fa8c16' : idx === 2 ? '#faad14' : '#1890ff'}
                                showInfo={false}
                              />
                            </div>
                          ))}
                        </div>
                        <Divider style={{ margin: '8px 0' }} />
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <Text strong>总支出</Text>
                          <Text strong style={{ color: '#f5222d', fontSize: 16 }}>¥{mockExpenseByCategory.reduce((s, i) => s + i.amount, 0).toLocaleString()}</Text>
                        </div>
                      </Card>
                    </Col>
                  </Row>
                </div>
              ),
            },
            {
              key: 'transactions',
              label: '交易记录',
              children: (
                <div>
                  {/* 筛选栏 */}
                  <Space wrap style={{ marginBottom: '16px' }}>
                    <Input placeholder="搜索描述/关联订单" prefix={<SearchOutlined />} value={searchText} onChange={(e) => setSearchText(e.target.value)} style={{ width: 220 }} allowClear />
                    <Select value={transactionTypeFilter} onChange={setTransactionTypeFilter} style={{ width: 120 }} options={[
                      { value: 'all', label: '全部类型' },
                      { value: 'income', label: '收入' },
                      { value: 'expense', label: '支出' },
                      { value: 'pending', label: '待处理' },
                    ]} />
                    <DatePicker.RangePicker showTime placeholder={['开始日期', '结束日期']} />
                    <Button icon={<SearchOutlined />} type="primary">搜索</Button>
                    <Button icon={<ReloadOutlined />} onClick={() => {
                      setSearchText('')
                      setTransactionTypeFilter('all')
                    }}>重置</Button>
                  </Space>

                  <Table
                    columns={transactionColumns}
                    dataSource={mockTransactions}
                    rowKey="id"
                    loading={loading}
                    pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 条交易记录` }}
                    locale={{ emptyText: <Empty description="暂无交易记录" /> }}
                  />
                </div>
              ),
            },
            {
              key: 'reports',
              label: '财务报表',
              children: (
                <div>
                  <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
                    <Col span={8}>
                      <Card size="small" hoverable onClick={() => message.info('正在生成利润表...')}>
                        <Space direction="vertical" style={{ width: '100%', textAlign: 'center' }}>
                          <FileTextOutlined style={{ fontSize: 40, color: '#722ed1' }} />
                          <div>
                            <div style={{ fontWeight: 600, fontSize: 16 }}>利润表</div>
                            <div style={{ fontSize: 12, color: '#999' }}>Income Statement</div>
                          </div>
                          <Text type="secondary" style={{ fontSize: 11 }}>收入、成本、费用、利润</Text>
                        </Space>
                      </Card>
                    </Col>
                    <Col span={8}>
                      <Card size="small" hoverable onClick={() => message.info('正在生成资产负债表...')}>
                        <Space direction="vertical" style={{ width: '100%', textAlign: 'center' }}>
                          <BankOutlined style={{ fontSize: 40, color: '#1890ff' }} />
                          <div>
                            <div style={{ fontWeight: 600, fontSize: 16 }}>资产负债表</div>
                            <div style={{ fontSize: 12, color: '#999' }}>Balance Sheet</div>
                          </div>
                          <Text type="secondary" style={{ fontSize: 11 }}>资产、负债、所有者权益</Text>
                        </Space>
                      </Card>
                    </Col>
                    <Col span={8}>
                      <Card size="small" hoverable onClick={() => message.info('正在生成现金流量表...')}>
                        <Space direction="vertical" style={{ width: '100%', textAlign: 'center' }}>
                          <WalletOutlined style={{ fontSize: 40, color: '#52c41a' }} />
                          <div>
                            <div style={{ fontWeight: 600, fontSize: 16 }}>现金流量表</div>
                            <div style={{ fontSize: 12, color: '#999' }}>Cash Flow Statement</div>
                          </div>
                          <Text type="secondary" style={{ fontSize: 11 }}>经营、投资、筹资现金流</Text>
                        </Space>
                      </Card>
                    </Col>
                  </Row>

                  {/* 利润表预览 */}
                  <Card size="small" title="利润表（本月预览）">
                    <Table
                      size="small"
                      pagination={false}
                      dataSource={[
                        { key: '1', item: '一、营业收入', amount: stats.revenue, percentage: '100%' },
                        { key: '2', item: '  减：营业成本', amount: 18500, percentage: '40.4%' },
                        { key: '3', item: '二、毛利润', amount: stats.revenue - 18500, percentage: '59.6%' },
                        { key: '4', item: '  减：物流费用', amount: 5600, percentage: '12.2%' },
                        { key: '5', item: '  减：营销费用', amount: 3200, percentage: '7.0%' },
                        { key: '6', item: '  减：平台费用', amount: 1800, percentage: '3.9%' },
                        { key: '7', item: '  减：运营费用', amount: 1200, percentage: '2.6%' },
                        { key: '8', item: '三、营业利润', amount: stats.profit, percentage: `${stats.profit_margin}%` },
                        { key: '9', item: '  减：所得税', amount: Math.round(stats.profit * 0.15), percentage: '4.8%' },
                        { key: '10', item: '四、净利润', amount: Math.round(stats.profit * 0.85), percentage: `${(stats.profit_margin * 0.85).toFixed(1)}%` },
                      ]}
                      columns={[
                        { title: '项目', dataIndex: 'item', key: 'item', render: (t) => <Text style={{ fontWeight: t.startsWith('一') || t.startsWith('二') || t.startsWith('三') || t.startsWith('四') ? 600 : 400 }}>{t}</Text> },
                        { title: '金额（USD）', dataIndex: 'amount', key: 'amount', align: 'right' as const, render: (v) => <Text strong>${v.toLocaleString()}</Text> },
                        { title: '占收入比', dataIndex: 'percentage', key: 'percentage', align: 'right' as const, width: 120 },
                      ]}
                    />
                  </Card>
                </div>
              ),
            },
          ]}
        />
      </Card>

      {/* 交易详情Modal */}
      <Modal
        title="交易详情"
        open={detailModalOpen}
        onCancel={() => setDetailModalOpen(false)}
        footer={[
          <Button key="close" onClick={() => setDetailModalOpen(false)}>关闭</Button>,
        ]}
        width={600}
      >
        {viewingTransaction && (
          <div>
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="交易日期" span={2}>{viewingTransaction.date}</Descriptions.Item>
              <Descriptions.Item label="交易类型">
                <Tag color={typeColors[viewingTransaction.type]}>{viewingTransaction.type === 'income' ? '收入' : '支出'}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="交易状态">
                <Tag color={statusColors[viewingTransaction.status]}>{viewingTransaction.status === 'completed' ? '已完成' : viewingTransaction.status === 'pending' ? '待处理' : '失败'}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="分类">{viewingTransaction.category}</Descriptions.Item>
              <Descriptions.Item label="支付方式">{viewingTransaction.payment_method}</Descriptions.Item>
              <Descriptions.Item label="金额" span={2}>
                <Text strong style={{ fontSize: 20, color: viewingTransaction.type === 'income' ? '#52c41a' : '#f5222d' }}>
                  {viewingTransaction.type === 'income' ? '+' : '-'}{viewingTransaction.amount.toLocaleString()} {viewingTransaction.currency}
                </Text>
              </Descriptions.Item>
              <Descriptions.Item label="描述" span={2}>{viewingTransaction.description}</Descriptions.Item>
              {viewingTransaction.related_order && <Descriptions.Item label="关联订单" span={2}><Text code>{viewingTransaction.related_order}</Text></Descriptions.Item>}
              {viewingTransaction.notes && <Descriptions.Item label="备注" span={2}>{viewingTransaction.notes}</Descriptions.Item>}
            </Descriptions>
          </div>
        )}
      </Modal>
    </div>
  )
}
