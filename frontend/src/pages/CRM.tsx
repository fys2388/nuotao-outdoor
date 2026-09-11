import { useState, useEffect } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Input, Select,
  Statistic, Row, Col, Spin, message, Modal, Descriptions, List,
  Badge, Tooltip, Empty, Tabs, Timeline, Divider, Alert,
  Progress, Form, InputNumber, Radio, DatePicker, Avatar
} from 'antd'
import {
  UserOutlined, ReloadOutlined, SearchOutlined,
  EyeOutlined, PlusOutlined, EditOutlined,
  DollarOutlined, CheckCircleOutlined, WarningOutlined,
  SyncOutlined, ClockCircleOutlined, ShopOutlined,
  MailOutlined, PhoneOutlined, GlobalOutlined,
  HeartOutlined, StarOutlined, FireOutlined,
  GiftOutlined, SendOutlined, BarChartOutlined,
  TeamOutlined, CrownOutlined, MessageOutlined
} from '@ant-design/icons'

const { Title, Text, Paragraph } = Typography

interface Customer {
  id: string
  name: string
  email: string
  phone: string
  country: string
  city: string
  address: string
  level: 'vip' | 'gold' | 'silver' | 'bronze' | 'new'
  total_orders: number
  total_spent: number
  avg_order_value: number
  last_order_date: string
  first_order_date: string
  status: 'active' | 'inactive' | 'churn_risk'
  tags: string[]
  rfm_score: { r: number; f: number; m: number; total: number }
  lifetime_value: number
  preferred_category: string
  notes?: string
  created_at: string
}

interface CustomerOrder {
  order_id: string
  order_number: string
  date: string
  status: string
  total: number
  items: number
  payment_method: string
}

interface Communication {
  id: string
  date: string
  type: 'email' | 'phone' | 'chat' | 'note'
  content: string
  staff: string
  result?: string
}

interface MarketingCampaign {
  id: string
  name: string
  type: 'email' | 'sms' | 'discount' | 'loyalty'
  target_segment: string
  target_count: number
  status: 'draft' | 'running' | 'completed' | 'paused'
  sent_count: number
  open_rate: number
  click_rate: number
  conversion_rate: number
  revenue: number
  created_at: string
  start_date?: string
  end_date?: string
}

const levelColors: Record<string, string> = {
  vip: 'gold',
  gold: 'orange',
  silver: 'default',
  bronze: 'brown',
  new: 'blue',
}

const levelText: Record<string, string> = {
  vip: 'VIP',
  gold: '金牌',
  silver: '银牌',
  bronze: '铜牌',
  new: '新客户',
}

const statusColors: Record<string, string> = {
  active: 'green',
  inactive: 'default',
  churn_risk: 'orange',
}

const statusText: Record<string, string> = {
  active: '活跃',
  inactive: '不活跃',
  churn_risk: '流失风险',
}

const campaignStatusColors: Record<string, string> = {
  draft: 'default',
  running: 'blue',
  completed: 'green',
  paused: 'orange',
}

export default function CRMPage() {
  const [activeTab, setActiveTab] = useState('customers')
  const [loading, setLoading] = useState(false)
  const [customerDetailOpen, setCustomerDetailOpen] = useState(false)
  const [campaignDetailOpen, setCampaignDetailOpen] = useState(false)
  const [createCampaignOpen, setCreateCampaignOpen] = useState(false)
  const [viewingCustomer, setViewingCustomer] = useState<Customer | null>(null)
  const [viewingCampaign, setViewingCampaign] = useState<MarketingCampaign | null>(null)
  const [levelFilter, setLevelFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [searchText, setSearchText] = useState('')
  // 真实API数据状态
  const [crmData, setCrmData] = useState<any>(null)
  const [campaignForm] = Form.useForm()

  // 模拟客户数据
  const mockCustomers: Customer[] = [
    { id: '1', name: 'John Smith', email: 'john.smith@email.com', phone: '+1-555-0101', country: '美国', city: '纽约', address: '123 Main St, New York, NY 10001', level: 'vip', total_orders: 45, total_spent: 12580, avg_order_value: 279.56, last_order_date: '2026-09-04', first_order_date: '2025-03-15', status: 'active', tags: ['户外爱好者', '高消费', '复购客户'], rfm_score: { r: 5, f: 5, m: 5, total: 15 }, lifetime_value: 15000, preferred_category: '户外装备', notes: '重要客户，优先服务', created_at: '2025-03-15' },
    { id: '2', name: 'Emma Wilson', email: 'emma.wilson@email.com', phone: '+44-555-0202', country: '英国', city: '伦敦', address: '456 Oxford St, London W1D 2HG', level: 'gold', total_orders: 28, total_spent: 6890, avg_order_value: 246.07, last_order_date: '2026-09-02', first_order_date: '2025-06-20', status: 'active', tags: ['露营爱好者', '中高消费'], rfm_score: { r: 4, f: 4, m: 4, total: 12 }, lifetime_value: 8500, preferred_category: '露营用品', created_at: '2025-06-20' },
    { id: '3', name: 'Hans Mueller', email: 'hans.mueller@email.de', phone: '+49-555-0303', country: '德国', city: '柏林', address: '789 Berlin Str, 10115 Berlin', level: 'silver', total_orders: 12, total_spent: 2340, avg_order_value: 195, last_order_date: '2026-08-15', first_order_date: '2025-09-10', status: 'active', tags: ['徒步爱好者'], rfm_score: { r: 3, f: 3, m: 3, total: 9 }, lifetime_value: 3200, preferred_category: '徒步装备', created_at: '2025-09-10' },
    { id: '4', name: 'Marie Dubois', email: 'marie.dubois@email.fr', phone: '+33-555-0404', country: '法国', city: '巴黎', address: '321 Rue de Paris, 75001 Paris', level: 'bronze', total_orders: 5, total_spent: 580, avg_order_value: 116, last_order_date: '2026-07-20', first_order_date: '2026-01-15', status: 'churn_risk', tags: ['新客户', '价格敏感'], rfm_score: { r: 2, f: 2, m: 2, total: 6 }, lifetime_value: 800, preferred_category: '户外配件', notes: '超过45天未下单，有流失风险', created_at: '2026-01-15' },
    { id: '5', name: 'James Brown', email: 'james.brown@email.co.uk', phone: '+44-555-0505', country: '英国', city: '曼彻斯特', address: '555 Manchester Rd, M1 1AB', level: 'new', total_orders: 1, total_spent: 89, avg_order_value: 89, last_order_date: '2026-09-05', first_order_date: '2026-09-05', status: 'active', tags: ['新客户'], rfm_score: { r: 5, f: 1, m: 1, total: 7 }, lifetime_value: 200, preferred_category: '照明设备', created_at: '2026-09-05' },
    { id: '6', name: 'Anna Kowalski', email: 'anna.kowalski@email.pl', phone: '+48-555-0606', country: '波兰', city: '华沙', address: '777 Warsaw St, 00-001 Warsaw', level: 'gold', total_orders: 32, total_spent: 8920, avg_order_value: 278.75, last_order_date: '2026-09-03', first_order_date: '2025-04-10', status: 'active', tags: ['户外爱好者', '高消费', 'KOL'], rfm_score: { r: 5, f: 5, m: 4, total: 14 }, lifetime_value: 11000, preferred_category: '户外装备', notes: '户外博主，可合作推广', created_at: '2025-04-10' },
    { id: '7', name: 'Peter Johnson', email: 'peter.johnson@email.com', phone: '+1-555-0707', country: '美国', city: '洛杉矶', address: '888 LA Blvd, Los Angeles, CA 90001', level: 'silver', total_orders: 8, total_spent: 1560, avg_order_value: 195, last_order_date: '2026-06-10', first_order_date: '2025-11-20', status: 'inactive', tags: ['偶尔购买'], rfm_score: { r: 1, f: 2, m: 3, total: 6 }, lifetime_value: 2000, preferred_category: '水具餐具', created_at: '2025-11-20' },
    { id: '8', name: 'Sophie Martin', email: 'sophie.martin@email.fr', phone: '+33-555-0808', country: '法国', city: '里昂', address: '999 Lyon Ave, 69001 Lyon', level: 'vip', total_orders: 52, total_spent: 15680, avg_order_value: 301.54, last_order_date: '2026-09-05', first_order_date: '2025-02-01', status: 'active', tags: ['户外爱好者', '超高消费', '品牌忠实'], rfm_score: { r: 5, f: 5, m: 5, total: 15 }, lifetime_value: 18000, preferred_category: '户外装备', notes: '最高价值客户，品牌大使', created_at: '2025-02-01' },
  ]

  // 模拟客户订单数据
  const mockCustomerOrders: CustomerOrder[] = [
    { order_id: '1', order_number: 'WO-20260904-001', date: '2026-09-04', status: 'completed', total: 156.80, items: 3, payment_method: 'Stripe' },
    { order_id: '2', order_number: 'WO-20260820-005', date: '2026-08-20', status: 'completed', total: 289.50, items: 2, payment_method: 'PayPal' },
    { order_id: '3', order_number: 'WO-20260715-008', date: '2026-07-15', status: 'completed', total: 199.99, items: 1, payment_method: 'Stripe' },
    { order_id: '4', order_number: 'WO-20260601-012', date: '2026-06-01', status: 'refunded', total: 89.00, items: 1, payment_method: 'Stripe' },
    { order_id: '5', order_number: 'WO-20260510-015', date: '2026-05-10', status: 'completed', total: 345.00, items: 4, payment_method: 'PayPal' },
  ]

  // 模拟沟通记录
  const mockCommunications: Communication[] = [
    { id: '1', date: '2026-09-04 14:30', type: 'email', content: '发送新品上市邮件，客户打开并点击了头灯产品链接', staff: '系统', result: '已打开' },
    { id: '2', date: '2026-08-25 10:15', type: 'chat', content: '客户咨询帐篷防水性能，客服解答后客户下单', staff: '客服小美', result: '转化下单' },
    { id: '3', date: '2026-08-20 16:00', type: 'email', content: '订单发货通知邮件', staff: '系统', result: '已送达' },
    { id: '4', date: '2026-07-15 09:30', type: 'phone', content: '客户来电询问物流进度，告知预计3天送达', staff: '客服小王' },
    { id: '5', date: '2026-06-01 11:00', type: 'note', content: '客户申请退款，原因：尺寸不合适。已处理退款并推荐合适尺寸', staff: '客服小美', result: '已退款' },
  ]

  // 模拟营销活动数据
  const mockCampaigns: MarketingCampaign[] = [
    { id: '1', name: '秋季新品上市推广', type: 'email', target_segment: '全量客户', target_count: 12500, status: 'running', sent_count: 8500, open_rate: 32.5, click_rate: 8.2, conversion_rate: 2.1, revenue: 15680, created_at: '2026-09-01', start_date: '2026-09-01', end_date: '2026-09-30' },
    { id: '2', name: 'VIP客户专属折扣', type: 'discount', target_segment: 'VIP客户', target_count: 156, status: 'running', sent_count: 156, open_rate: 68.5, click_rate: 45.2, conversion_rate: 28.5, revenue: 45600, created_at: '2026-08-15', start_date: '2026-08-15', end_date: '2026-09-15' },
    { id: '3', name: '流失客户召回', type: 'email', target_segment: '流失风险客户', target_count: 890, status: 'completed', sent_count: 890, open_rate: 25.8, click_rate: 5.6, conversion_rate: 3.2, revenue: 8900, created_at: '2026-07-01', start_date: '2026-07-01', end_date: '2026-07-31' },
    { id: '4', name: '会员积分双倍活动', type: 'loyalty', target_segment: '金牌及以上客户', target_count: 580, status: 'completed', sent_count: 580, open_rate: 45.2, click_rate: 22.8, conversion_rate: 15.6, revenue: 28900, created_at: '2026-06-01', start_date: '2026-06-01', end_date: '2026-06-30' },
    { id: '5', name: '新客户欢迎邮件', type: 'email', target_segment: '新客户', target_count: 2300, status: 'running', sent_count: 1800, open_rate: 55.2, click_rate: 18.5, conversion_rate: 8.9, revenue: 12300, created_at: '2026-01-01' },
    { id: '6', name: '圣诞大促预热', type: 'sms', target_segment: '全量客户', target_count: 12500, status: 'draft', sent_count: 0, open_rate: 0, click_rate: 0, conversion_rate: 0, revenue: 0, created_at: '2026-09-05', start_date: '2026-12-01', end_date: '2026-12-25' },
  ]

  // 加载CRM数据（调用真实API，失败则使用mock数据降级）
  const loadCRMData = async () => {
    try {
      setLoading(true)
      // 调用客户档案API
      const customersResp = await fetch('/api/v1/customer-profiles')
      if (customersResp.ok) {
        const customersData = await customersResp.json()
        setCrmData(customersData)
        console.log('Customer profiles:', customersData)
      }
      message.success('CRM数据加载完成')
    } catch (e: any) {
      console.error('Load CRM data error:', e)
      message.warning(`API调用失败，使用模拟数据：${e.message || '未知错误'}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadCRMData()
  }, [])

  // 统计数据（优先使用真实API数据，失败则使用mock数据降级）
  const realCustomers = crmData?.items || crmData?.customers || []
  const customers = realCustomers.length > 0 ? realCustomers : mockCustomers
  const stats = {
    totalCustomers: customers.length,
    activeCustomers: crmData?.active_customers || customers.filter((c: any) => c.status === 'active').length,
    vipCustomers: crmData?.vip_customers || customers.filter((c: any) => c.level === 'vip').length,
    churnRisk: crmData?.churn_risk || customers.filter((c: any) => c.status === 'churn_risk').length,
    totalRevenue: crmData?.total_revenue || customers.reduce((sum: number, c: any) => sum + (c.total_spent || 0), 0),
    avgLTV: crmData?.avg_ltv || Math.round(customers.reduce((sum: number, c: any) => sum + (c.lifetime_value || 0), 0) / customers.length),
  }

  // 客户表格列
  const customerColumns = [
    {
      title: '客户',
      key: 'customer',
      width: 200,
      render: (_: any, record: Customer) => (
        <Space>
          <Avatar size={40} style={{ backgroundColor: '#722ed1' }} icon={<UserOutlined />} />
          <div>
            <div style={{ fontWeight: 500 }}>{record.name}</div>
            <div style={{ fontSize: '10px', color: '#999' }}>{record.email}</div>
          </div>
        </Space>
      ),
    },
    {
      title: '等级',
      dataIndex: 'level',
      key: 'level',
      width: 100,
      render: (level: string) => (
        <Tag color={levelColors[level]} icon={level === 'vip' ? <CrownOutlined /> : null}>
          {levelText[level]}
        </Tag>
      ),
    },
    {
      title: '国家/地区',
      key: 'location',
      width: 120,
      render: (_: any, record: Customer) => (
        <Space>
          <GlobalOutlined style={{ fontSize: '12px', color: '#999' }} />
          <Text style={{ fontSize: '12px' }}>{record.country} {record.city}</Text>
        </Space>
      ),
    },
    {
      title: '订单数',
      dataIndex: 'total_orders',
      key: 'total_orders',
      width: 80,
      render: (count: number) => <Text strong>{count}</Text>,
    },
    {
      title: '消费总额',
      dataIndex: 'total_spent',
      key: 'total_spent',
      width: 110,
      render: (amount: number) => <Text strong style={{ color: '#f5222d' }}>${amount.toLocaleString()}</Text>,
    },
    {
      title: '客单价',
      dataIndex: 'avg_order_value',
      key: 'avg_order_value',
      width: 100,
      render: (amount: number) => <Text>${amount.toFixed(2)}</Text>,
    },
    {
      title: 'RFM评分',
      key: 'rfm',
      width: 120,
      render: (_: any, record: Customer) => (
        <div>
          <Progress percent={(record.rfm_score.total / 15) * 100} size="small" strokeColor="#722ed1" format={() => `${record.rfm_score.total}/15`} />
          <div style={{ fontSize: '10px', color: '#999' }}>R{record.rfm_score.r} F{record.rfm_score.f} M{record.rfm_score.m}</div>
        </div>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => <Tag color={statusColors[status]}>{statusText[status]}</Tag>,
    },
    {
      title: '最后下单',
      dataIndex: 'last_order_date',
      key: 'last_order_date',
      width: 110,
      render: (text: string) => <Text type="secondary" style={{ fontSize: '11px' }}>{text}</Text>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 150,
      render: (_: any, record: Customer) => (
        <Space size="small">
          <Button size="small" icon={<EyeOutlined />} onClick={() => {
            setViewingCustomer(record)
            setCustomerDetailOpen(true)
          }}>详情</Button>
          <Button size="small" icon={<MailOutlined />} onClick={() => message.success(`已向${record.name}发送营销邮件`)}>营销</Button>
        </Space>
      ),
    },
  ]

  // 营销活动表格列
  const campaignColumns = [
    {
      title: '活动名称',
      dataIndex: 'name',
      key: 'name',
      width: 200,
      render: (text: string, record: MarketingCampaign) => (
        <div>
          <div style={{ fontWeight: 500 }}>{text}</div>
          <div style={{ fontSize: '10px', color: '#999' }}>{record.type === 'email' ? '邮件营销' : record.type === 'sms' ? '短信营销' : record.type === 'discount' ? '折扣活动' : '会员活动'}</div>
        </div>
      ),
    },
    {
      title: '目标客群',
      dataIndex: 'target_segment',
      key: 'target_segment',
      width: 150,
    },
    {
      title: '目标人数',
      dataIndex: 'target_count',
      key: 'target_count',
      width: 100,
      render: (count: number) => <Text>{count.toLocaleString()}</Text>,
    },
    {
      title: '发送进度',
      key: 'progress',
      width: 150,
      render: (_: any, record: MarketingCampaign) => (
        <div>
          <Progress percent={Math.round((record.sent_count / record.target_count) * 100)} size="small" />
          <div style={{ fontSize: '10px', color: '#999' }}>{record.sent_count.toLocaleString()} / {record.target_count.toLocaleString()}</div>
        </div>
      ),
    },
    {
      title: '打开率',
      dataIndex: 'open_rate',
      key: 'open_rate',
      width: 90,
      render: (rate: number) => <Text type={rate > 30 ? 'success' : 'secondary'}>{rate}%</Text>,
    },
    {
      title: '点击率',
      dataIndex: 'click_rate',
      key: 'click_rate',
      width: 90,
      render: (rate: number) => <Text type={rate > 10 ? 'success' : 'secondary'}>{rate}%</Text>,
    },
    {
      title: '转化率',
      dataIndex: 'conversion_rate',
      key: 'conversion_rate',
      width: 90,
      render: (rate: number) => <Text type={rate > 5 ? 'success' : 'secondary'}>{rate}%</Text>,
    },
    {
      title: '带来收入',
      dataIndex: 'revenue',
      key: 'revenue',
      width: 110,
      render: (amount: number) => <Text strong style={{ color: '#52c41a' }}>${amount.toLocaleString()}</Text>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (status: string) => <Tag color={campaignStatusColors[status]}>{status === 'draft' ? '草稿' : status === 'running' ? '进行中' : status === 'completed' ? '已完成' : '已暂停'}</Tag>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_: any, record: MarketingCampaign) => (
        <Space size="small">
          <Button size="small" icon={<EyeOutlined />} onClick={() => {
            setViewingCampaign(record)
            setCampaignDetailOpen(true)
          }}>详情</Button>
        </Space>
      ),
    },
  ]

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <TeamOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>客户CRM系统</Title>
            <Text type="secondary">客户画像、消费分析、营销自动化</Text>
          </div>
        </Space>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => message.success('数据已刷新')}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateCampaignOpen(true)}>创建营销活动</Button>
        </Space>
      </div>

      {/* 流失风险预警 */}
      {stats.churnRisk > 0 && (
        <Alert
          message={`有 ${stats.churnRisk} 个客户存在流失风险`}
          description="建议及时发起召回营销活动，通过专属折扣或新品推荐挽回客户。"
          type="warning"
          showIcon
          icon={<WarningOutlined />}
          style={{ marginBottom: '16px' }}
          action={
            <Button size="small" type="primary" onClick={() => message.info('正在创建流失客户召回活动')}>发起召回</Button>
          }
        />
      )}

      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: '16px' }}>
        <Col span={4}>
          <Card size="small">
            <Statistic title="客户总数" value={stats.totalCustomers} prefix={<UserOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="活跃客户" value={stats.activeCustomers} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="VIP客户" value={stats.vipCustomers} valueStyle={{ color: '#faad14' }} prefix={<CrownOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="流失风险" value={stats.churnRisk} valueStyle={{ color: '#f5222d' }} prefix={<WarningOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="累计收入" value={stats.totalRevenue} prefix="$" valueStyle={{ color: '#722ed1' }} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="平均LTV" value={stats.avgLTV} prefix="$" valueStyle={{ color: '#1890ff' }} />
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
              key: 'customers',
              label: '客户管理',
              children: (
                <div>
                  {/* 筛选栏 */}
                  <Space wrap style={{ marginBottom: '16px' }}>
                    <Input placeholder="搜索客户姓名/邮箱" prefix={<SearchOutlined />} value={searchText} onChange={(e) => setSearchText(e.target.value)} style={{ width: 220 }} allowClear />
                    <Select value={levelFilter} onChange={setLevelFilter} style={{ width: 120 }} options={[
                      { value: 'all', label: '全部等级' },
                      { value: 'vip', label: 'VIP' },
                      { value: 'gold', label: '金牌' },
                      { value: 'silver', label: '银牌' },
                      { value: 'bronze', label: '铜牌' },
                      { value: 'new', label: '新客户' },
                    ]} />
                    <Select value={statusFilter} onChange={setStatusFilter} style={{ width: 120 }} options={[
                      { value: 'all', label: '全部状态' },
                      { value: 'active', label: '活跃' },
                      { value: 'inactive', label: '不活跃' },
                      { value: 'churn_risk', label: '流失风险' },
                    ]} />
                    <Button icon={<SearchOutlined />} type="primary">搜索</Button>
                    <Button icon={<ReloadOutlined />} onClick={() => {
                      setSearchText('')
                      setLevelFilter('all')
                      setStatusFilter('all')
                    }}>重置</Button>
                  </Space>

                  <Table
                    columns={customerColumns}
                    dataSource={mockCustomers}
                    rowKey="id"
                    loading={loading}
                    pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 个客户` }}
                    locale={{ emptyText: <Empty description="暂无客户" /> }}
                  />
                </div>
              ),
            },
            {
              key: 'segments',
              label: '客户分层',
              children: (
                <div>
                  <Row gutter={[16, 16]}>
                    {[
                      { level: 'vip', name: 'VIP客户', count: mockCustomers.filter(c => c.level === 'vip').length, color: '#faad14', icon: <CrownOutlined />, desc: '最高价值客户，专属服务' },
                      { level: 'gold', name: '金牌客户', count: mockCustomers.filter(c => c.level === 'gold').length, color: '#fa8c16', icon: <StarOutlined />, desc: '高价值客户，重点维护' },
                      { level: 'silver', name: '银牌客户', count: mockCustomers.filter(c => c.level === 'silver').length, color: '#8c8c8c', icon: <HeartOutlined />, desc: '中等价值，潜力培育' },
                      { level: 'bronze', name: '铜牌客户', count: mockCustomers.filter(c => c.level === 'bronze').length, color: '#d48806', icon: <UserOutlined />, desc: '低价值，激活转化' },
                      { level: 'new', name: '新客户', count: mockCustomers.filter(c => c.level === 'new').length, color: '#1890ff', icon: <PlusOutlined />, desc: '新注册，欢迎引导' },
                    ].map((segment, idx) => (
                      <Col span={8} key={idx}>
                        <Card size="small" hoverable>
                          <Space direction="vertical" style={{ width: '100%' }}>
                            <Space>
                              <div style={{ width: 40, height: 40, borderRadius: '50%', background: `${segment.color}20`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                <span style={{ fontSize: 20, color: segment.color }}>{segment.icon}</span>
                              </div>
                              <div>
                                <div style={{ fontWeight: 600, fontSize: 16 }}>{segment.name}</div>
                                <div style={{ fontSize: 12, color: '#999' }}>{segment.desc}</div>
                              </div>
                            </Space>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                              <Text type="secondary">客户数量</Text>
                              <Text strong style={{ fontSize: 24, color: segment.color }}>{segment.count}</Text>
                            </div>
                            <Button type="primary" block onClick={() => message.info(`查看${segment.name}列表`)}>查看客户</Button>
                          </Space>
                        </Card>
                      </Col>
                    ))}
                  </Row>

                  <Divider />

                  <Card size="small" title="RFM模型说明">
                    <Row gutter={16}>
                      <Col span={8}>
                        <div style={{ padding: 12, background: '#f6ffed', borderRadius: 8 }}>
                          <Text strong style={{ color: '#52c41a' }}>R (Recency) 最近消费</Text>
                          <Paragraph style={{ margin: '8px 0 0 0', fontSize: 12 }}>客户最近一次下单距离现在的时间。越近得分越高。</Paragraph>
                        </div>
                      </Col>
                      <Col span={8}>
                        <div style={{ padding: 12, background: '#e6f7ff', borderRadius: 8 }}>
                          <Text strong style={{ color: '#1890ff' }}>F (Frequency) 消费频率</Text>
                          <Paragraph style={{ margin: '8px 0 0 0', fontSize: 12 }}>客户在一定时间内的下单次数。次数越多得分越高。</Paragraph>
                        </div>
                      </Col>
                      <Col span={8}>
                        <div style={{ padding: 12, background: '#fff7e6', borderRadius: 8 }}>
                          <Text strong style={{ color: '#fa8c16' }}>M (Monetary) 消费金额</Text>
                          <Paragraph style={{ margin: '8px 0 0 0', fontSize: 12 }}>客户在一定时间内的消费总额。金额越高得分越高。</Paragraph>
                        </div>
                      </Col>
                    </Row>
                  </Card>
                </div>
              ),
            },
            {
              key: 'marketing',
              label: '营销自动化',
              children: (
                <div>
                  <Alert
                    message="营销自动化"
                    description="基于客户分层和RFM模型，自动触发个性化营销活动，提升客户转化率和复购率。"
                    type="info"
                    showIcon
                    style={{ marginBottom: 16 }}
                  />
                  <Table
                    columns={campaignColumns}
                    dataSource={mockCampaigns}
                    rowKey="id"
                    loading={loading}
                    pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 个营销活动` }}
                    locale={{ emptyText: <Empty description="暂无营销活动" /> }}
                  />
                </div>
              ),
            },
          ]}
        />
      </Card>

      {/* 客户详情Modal */}
      <Modal
        title={`客户详情 - ${viewingCustomer?.name || ''}`}
        open={customerDetailOpen}
        onCancel={() => setCustomerDetailOpen(false)}
        footer={[
          <Button key="email" icon={<MailOutlined />} onClick={() => message.success('营销邮件已发送')}>发送邮件</Button>,
          <Button key="close" onClick={() => setCustomerDetailOpen(false)}>关闭</Button>,
        ]}
        width={800}
      >
        {viewingCustomer && (
          <div>
            {/* 客户基本信息 */}
            <Card size="small" style={{ marginBottom: 16 }}>
              <Row gutter={16}>
                <Col span={12}>
                  <Space>
                    <Avatar size={64} style={{ backgroundColor: '#722ed1' }} icon={<UserOutlined />} />
                    <div>
                      <div style={{ fontSize: 20, fontWeight: 600 }}>{viewingCustomer.name}</div>
                      <div style={{ fontSize: 12, color: '#999' }}>{viewingCustomer.email}</div>
                      <div style={{ marginTop: 4 }}>
                        <Tag color={levelColors[viewingCustomer.level]} icon={viewingCustomer.level === 'vip' ? <CrownOutlined /> : null}>
                          {levelText[viewingCustomer.level]}
                        </Tag>
                        <Tag color={statusColors[viewingCustomer.status]}>{statusText[viewingCustomer.status]}</Tag>
                      </div>
                    </div>
                  </Space>
                </Col>
                <Col span={12}>
                  <Row gutter={[8, 8]}>
                    <Col span={12}>
                      <Statistic title="累计消费" value={viewingCustomer.total_spent} prefix="$" valueStyle={{ fontSize: 18, color: '#f5222d' }} />
                    </Col>
                    <Col span={12}>
                      <Statistic title="订单数" value={viewingCustomer.total_orders} valueStyle={{ fontSize: 18 }} />
                    </Col>
                    <Col span={12}>
                      <Statistic title="客单价" value={viewingCustomer.avg_order_value} prefix="$" precision={2} valueStyle={{ fontSize: 18 }} />
                    </Col>
                    <Col span={12}>
                      <Statistic title="生命周期价值" value={viewingCustomer.lifetime_value} prefix="$" valueStyle={{ fontSize: 18, color: '#722ed1' }} />
                    </Col>
                  </Row>
                </Col>
              </Row>
            </Card>

            {/* RFM评分 */}
            <Card size="small" title="RFM评分" style={{ marginBottom: 16 }}>
              <Row gutter={16}>
                <Col span={8}>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 32, fontWeight: 700, color: '#52c41a' }}>{viewingCustomer.rfm_score.r}</div>
                    <div style={{ fontSize: 12, color: '#999' }}>R (最近消费)</div>
                  </div>
                </Col>
                <Col span={8}>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 32, fontWeight: 700, color: '#1890ff' }}>{viewingCustomer.rfm_score.f}</div>
                    <div style={{ fontSize: 12, color: '#999' }}>F (消费频率)</div>
                  </div>
                </Col>
                <Col span={8}>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 32, fontWeight: 700, color: '#fa8c16' }}>{viewingCustomer.rfm_score.m}</div>
                    <div style={{ fontSize: 12, color: '#999' }}>M (消费金额)</div>
                  </div>
                </Col>
              </Row>
              <Divider style={{ margin: '12px 0' }} />
              <div style={{ textAlign: 'center' }}>
                <Text type="secondary">综合评分：</Text>
                <Text strong style={{ fontSize: 20, color: '#722ed1' }}>{viewingCustomer.rfm_score.total}/15</Text>
              </div>
            </Card>

            {/* 客户标签 */}
            <Card size="small" title="客户标签" style={{ marginBottom: 16 }}>
              <Space wrap>
                {viewingCustomer.tags.map((tag, idx) => (
                  <Tag key={idx} color="blue">{tag}</Tag>
                ))}
                <Tag color="green">偏好：{viewingCustomer.preferred_category}</Tag>
              </Space>
            </Card>

            {/* 购买历史 */}
            <Card size="small" title="购买历史" style={{ marginBottom: 16 }}>
              <Table
                dataSource={mockCustomerOrders}
                rowKey="order_id"
                size="small"
                pagination={false}
                columns={[
                  { title: '订单号', dataIndex: 'order_number', key: 'order_number', render: (t) => <Text code style={{ fontSize: 11 }}>{t}</Text> },
                  { title: '日期', dataIndex: 'date', key: 'date' },
                  { title: '商品数', dataIndex: 'items', key: 'items' },
                  { title: '金额', dataIndex: 'total', key: 'total', render: (t) => <Text strong>${t}</Text> },
                  { title: '支付方式', dataIndex: 'payment_method', key: 'payment_method' },
                  { title: '状态', dataIndex: 'status', key: 'status', render: (s) => <Tag color={s === 'completed' ? 'green' : s === 'refunded' ? 'red' : 'blue'}>{s}</Tag> },
                ]}
              />
            </Card>

            {/* 沟通记录 */}
            <Card size="small" title="沟通记录">
              <Timeline>
                {mockCommunications.map((comm) => (
                  <Timeline.Item key={comm.id} color={comm.type === 'email' ? 'blue' : comm.type === 'phone' ? 'green' : comm.type === 'chat' ? 'cyan' : 'gray'}>
                    <div>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <Text strong>{comm.type === 'email' ? '邮件' : comm.type === 'phone' ? '电话' : comm.type === 'chat' ? '在线客服' : '备注'} - {comm.staff}</Text>
                        <Text type="secondary" style={{ fontSize: 11 }}>{comm.date}</Text>
                      </div>
                      <Paragraph style={{ margin: '4px 0 0 0', fontSize: 12 }}>{comm.content}</Paragraph>
                      {comm.result && <Tag color="blue" style={{ marginTop: 4 }}>{comm.result}</Tag>}
                    </div>
                  </Timeline.Item>
                ))}
              </Timeline>
            </Card>
          </div>
        )}
      </Modal>

      {/* 营销活动详情Modal */}
      <Modal
        title={`营销活动详情 - ${viewingCampaign?.name || ''}`}
        open={campaignDetailOpen}
        onCancel={() => setCampaignDetailOpen(false)}
        footer={[
          <Button key="close" onClick={() => setCampaignDetailOpen(false)}>关闭</Button>,
        ]}
        width={700}
      >
        {viewingCampaign && (
          <div>
            <Descriptions column={2} bordered size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="活动名称" span={2}>{viewingCampaign.name}</Descriptions.Item>
              <Descriptions.Item label="活动类型">{viewingCampaign.type === 'email' ? '邮件营销' : viewingCampaign.type === 'sms' ? '短信营销' : viewingCampaign.type === 'discount' ? '折扣活动' : '会员活动'}</Descriptions.Item>
              <Descriptions.Item label="状态"><Tag color={campaignStatusColors[viewingCampaign.status]}>{viewingCampaign.status}</Tag></Descriptions.Item>
              <Descriptions.Item label="目标客群">{viewingCampaign.target_segment}</Descriptions.Item>
              <Descriptions.Item label="目标人数">{viewingCampaign.target_count.toLocaleString()}</Descriptions.Item>
              <Descriptions.Item label="创建时间">{viewingCampaign.created_at}</Descriptions.Item>
              <Descriptions.Item label="活动周期">{viewingCampaign.start_date || '-'} ~ {viewingCampaign.end_date || '-'}</Descriptions.Item>
            </Descriptions>

            <Row gutter={16} style={{ marginBottom: 16 }}>
              <Col span={6}>
                <Card size="small">
                  <Statistic title="发送数" value={viewingCampaign.sent_count} />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small">
                  <Statistic title="打开率" value={viewingCampaign.open_rate} suffix="%" valueStyle={{ color: '#1890ff' }} />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small">
                  <Statistic title="点击率" value={viewingCampaign.click_rate} suffix="%" valueStyle={{ color: '#52c41a' }} />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small">
                  <Statistic title="转化率" value={viewingCampaign.conversion_rate} suffix="%" valueStyle={{ color: '#722ed1' }} />
                </Card>
              </Col>
            </Row>

            <Card size="small" title="活动效果">
              <Row gutter={16}>
                <Col span={12}>
                  <div style={{ padding: 16, background: '#f6ffed', borderRadius: 8, textAlign: 'center' }}>
                    <div style={{ fontSize: 12, color: '#999' }}>带来收入</div>
                    <div style={{ fontSize: 28, fontWeight: 700, color: '#52c41a' }}>${viewingCampaign.revenue.toLocaleString()}</div>
                  </div>
                </Col>
                <Col span={12}>
                  <div style={{ padding: 16, background: '#e6f7ff', borderRadius: 8, textAlign: 'center' }}>
                    <div style={{ fontSize: 12, color: '#999' }}>ROI</div>
                    <div style={{ fontSize: 28, fontWeight: 700, color: '#1890ff' }}>{(viewingCampaign.revenue / (viewingCampaign.sent_count * 0.05)).toFixed(1)}x</div>
                  </div>
                </Col>
              </Row>
            </Card>
          </div>
        )}
      </Modal>

      {/* 创建营销活动Modal */}
      <Modal
        title="创建营销活动"
        open={createCampaignOpen}
        onCancel={() => setCreateCampaignOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setCreateCampaignOpen(false)}>取消</Button>,
          <Button key="save" type="primary" onClick={() => {
            message.success('营销活动已创建')
            setCreateCampaignOpen(false)
          }}>创建</Button>,
        ]}
        width={600}
      >
        <Form form={campaignForm} layout="vertical">
          <Form.Item name="name" label="活动名称" rules={[{ required: true }]}>
            <Input placeholder="例如：秋季新品上市推广" />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="type" label="活动类型" rules={[{ required: true }]}>
                <Select options={[
                  { value: 'email', label: '邮件营销' },
                  { value: 'sms', label: '短信营销' },
                  { value: 'discount', label: '折扣活动' },
                  { value: 'loyalty', label: '会员活动' },
                ]} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="target_segment" label="目标客群" rules={[{ required: true }]}>
                <Select options={[
                  { value: 'all', label: '全量客户' },
                  { value: 'vip', label: 'VIP客户' },
                  { value: 'gold', label: '金牌客户' },
                  { value: 'churn_risk', label: '流失风险客户' },
                  { value: 'new', label: '新客户' },
                ]} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="start_date" label="开始日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="end_date" label="结束日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="content" label="活动内容">
            <Input.TextArea rows={3} placeholder="活动内容描述" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
