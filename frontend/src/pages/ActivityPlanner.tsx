import { useState, useEffect } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Input, Select,
  Statistic, Row, Col, Spin, message, Modal, Descriptions,
  Badge, Tooltip, Empty, Tabs, Progress, Divider, Alert,
  List, Avatar, Form, Radio, Switch, Segmented,
  Timeline, Calendar, Badge as AntBadge
} from 'antd'
import {
  CalendarOutlined, ReloadOutlined, SearchOutlined,
  EyeOutlined, PlusOutlined, DownloadOutlined,
  CheckCircleOutlined, EditOutlined,
  SyncOutlined, ClockCircleOutlined,
  ThunderboltOutlined, RobotOutlined,
  ArrowUpOutlined, ArrowDownOutlined,
  FileTextOutlined, LinkOutlined,
  GlobalOutlined, ApiOutlined,
  ToolOutlined, BulbOutlined,
  ExclamationCircleOutlined, CopyOutlined,
  SendOutlined, BarChartOutlined,
  UserOutlined, TeamOutlined,
  ScheduleOutlined, DeleteOutlined,
  SaveOutlined, FundOutlined,
  EnvironmentOutlined, DatabaseOutlined,
  SettingOutlined, CloudOutlined,
  InboxOutlined, LikeOutlined,
  DislikeOutlined, ShareAltOutlined,
  GiftOutlined, ShoppingCartOutlined,
  DollarOutlined, TargetOutlined,
  FlagOutlined, CheckSquareOutlined,
  UnorderedListOutlined, PlayCircleOutlined,
  PauseCircleOutlined, StopOutlined
} from '@ant-design/icons'

const { Title, Text, Paragraph } = Typography

interface MarketingActivity {
  id: string
  name: string
  type: 'flash_sale' | 'discount' | 'bundle' | 'coupon' | 'seasonal' | 'new_product' | 'loyalty'
  status: 'planning' | 'ongoing' | 'upcoming' | 'ended' | 'paused'
  description: string
  start_date: string
  end_date: string
  budget: number
  spent: number
  target_revenue: number
  actual_revenue: number
  target_orders: number
  actual_orders: number
  discount_rate: number
  products_count: number
  channels: string[]
  created_at: string
}

interface ActivityTask {
  id: string
  activity_id: string
  name: string
  assignee: string
  status: 'pending' | 'in_progress' | 'completed'
  due_date: string
  priority: 'high' | 'medium' | 'low'
}

const activityTypeColors: Record<string, string> = {
  flash_sale: 'red',
  discount: 'orange',
  bundle: 'blue',
  coupon: 'purple',
  seasonal: 'green',
  new_product: 'cyan',
  loyalty: 'gold',
}

const activityTypeText: Record<string, string> = {
  flash_sale: '限时秒杀',
  discount: '折扣促销',
  bundle: '捆绑销售',
  coupon: '优惠券',
  seasonal: '节日活动',
  new_product: '新品发布',
  loyalty: '会员专享',
}

const activityStatusColors: Record<string, string> = {
  planning: 'default',
  ongoing: 'green',
  upcoming: 'blue',
  ended: 'orange',
  paused: 'red',
}

const activityStatusText: Record<string, string> = {
  planning: '策划中',
  ongoing: '进行中',
  upcoming: '即将开始',
  ended: '已结束',
  paused: '已暂停',
}

export default function ActivityPlannerPage() {
  const [activeTab, setActiveTab] = useState('list')
  const [loading, setLoading] = useState(false)
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [viewingActivity, setViewingActivity] = useState<MarketingActivity | null>(null)
  const [createModalOpen, setCreateModalOpen] = useState(false)
  // 真实API数据状态
  const [activityData, setActivityData] = useState<any>(null)
  const [createForm] = Form.useForm()

  const mockActivities: MarketingActivity[] = [
    { id: '1', name: '秋季新品发布', type: 'new_product', status: 'ongoing', description: '秋季新品系列发布，包含LED头灯、登山杖、保温水壶等新品，全场新品8折优惠。', start_date: '2026-09-01', end_date: '2026-09-15', budget: 5000, spent: 3200, target_revenue: 25000, actual_revenue: 18500, target_orders: 200, actual_orders: 156, discount_rate: 20, products_count: 8, channels: ['网站', 'EDM', '社交媒体'], created_at: '2026-08-20' },
    { id: '2', name: '中秋限时秒杀', type: 'flash_sale', status: 'upcoming', description: '中秋节限时秒杀活动，每天10点、15点、20点三场秒杀，爆款产品低至5折。', start_date: '2026-09-15', end_date: '2026-09-17', budget: 3000, spent: 0, target_revenue: 15000, actual_revenue: 0, target_orders: 150, actual_orders: 0, discount_rate: 50, products_count: 5, channels: ['网站', 'APP推送'], created_at: '2026-09-01' },
    { id: '3', name: 'VIP会员专享周', type: 'loyalty', status: 'planning', description: 'VIP会员专享优惠周，全场额外9折，双倍积分，专属客服通道。', start_date: '2026-09-20', end_date: '2026-09-27', budget: 2000, spent: 0, target_revenue: 12000, actual_revenue: 0, target_orders: 100, actual_orders: 0, discount_rate: 10, products_count: 0, channels: ['EDM', '站内信'], created_at: '2026-09-05' },
    { id: '4', name: '夏季清仓大促', type: 'discount', status: 'ended', description: '夏季产品清仓大促，低至3折，满$100减$20，满$200减$50。', start_date: '2026-08-15', end_date: '2026-08-31', budget: 8000, spent: 7500, target_revenue: 40000, actual_revenue: 45600, target_orders: 400, actual_orders: 485, discount_rate: 30, products_count: 25, channels: ['网站', 'EDM', '社交媒体', '广告投放'], created_at: '2026-07-25' },
    { id: '5', name: '户外装备捆绑套餐', type: 'bundle', status: 'ongoing', description: '精选户外装备捆绑套餐，露营三件套、徒步四件套，购买套餐比单独购买省25%。', start_date: '2026-08-20', end_date: '2026-09-30', budget: 1500, spent: 800, target_revenue: 10000, actual_revenue: 6800, target_orders: 80, actual_orders: 52, discount_rate: 25, products_count: 6, channels: ['网站', '社交媒体'], created_at: '2026-08-10' },
    { id: '6', name: '新客优惠券活动', type: 'coupon', status: 'ongoing', description: '新用户注册即送$10优惠券，首单满$50可用，邀请好友再得$5。', start_date: '2026-09-01', end_date: '2026-12-31', budget: 10000, spent: 2500, target_revenue: 50000, actual_revenue: 18500, target_orders: 500, actual_orders: 185, discount_rate: 20, products_count: 0, channels: ['网站', 'EDM', '社交媒体'], created_at: '2026-08-15' },
  ]

  const mockTasks: ActivityTask[] = [
    { id: '1', activity_id: '1', name: '确定活动产品清单', assignee: '产品经理', status: 'completed', due_date: '2026-08-25', priority: 'high' },
    { id: '2', activity_id: '1', name: '设计活动Banner和素材', assignee: '设计师', status: 'completed', due_date: '2026-08-28', priority: 'high' },
    { id: '3', activity_id: '1', name: '配置活动价格和库存', assignee: '运营', status: 'completed', due_date: '2026-08-30', priority: 'high' },
    { id: '4', activity_id: '1', name: '编写EDM邮件文案', assignee: '内容运营', status: 'completed', due_date: '2026-08-31', priority: 'medium' },
    { id: '5', activity_id: '1', name: '社交媒体推广素材', assignee: '社媒运营', status: 'in_progress', due_date: '2026-09-08', priority: 'medium' },
    { id: '6', activity_id: '1', name: '活动效果数据分析', assignee: '数据分析师', status: 'pending', due_date: '2026-09-16', priority: 'low' },
    { id: '7', activity_id: '2', name: '秒杀活动产品选品', assignee: '产品经理', status: 'in_progress', due_date: '2026-09-10', priority: 'high' },
    { id: '8', activity_id: '2', name: '秒杀系统配置测试', assignee: '技术', status: 'pending', due_date: '2026-09-12', priority: 'high' },
  ]

  // 加载活动策划数据（调用真实API，失败则使用mock数据降级）
  const loadActivityPlannerData = async () => {
    try {
      setLoading(true)
      // 调用内容生成API（包含营销活动相关功能）
      const contentResp = await fetch('/api/v1/content/status')
      if (contentResp.ok) {
        const contentData = await contentResp.json()
        setActivityData(contentData)
        console.log('Content status:', contentData)
      }
      message.success('活动策划数据加载完成')
    } catch (e: any) {
      console.error('Load activity planner data error:', e)
      message.warning(`API调用失败，使用模拟数据：${e.message || '未知错误'}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadActivityPlannerData()
  }, [])

  // 统计数据（优先使用真实API数据，失败则使用mock数据降级）
  const stats = {
    totalActivities: activityData?.total_activities || mockActivities.length,
    ongoing: activityData?.ongoing_activities || mockActivities.filter(a => a.status === 'ongoing').length,
    upcoming: activityData?.upcoming_activities || mockActivities.filter(a => a.status === 'upcoming').length,
    planning: activityData?.planning_activities || mockActivities.filter(a => a.status === 'planning').length,
    totalBudget: activityData?.total_budget || mockActivities.reduce((s, a) => s + a.budget, 0),
    totalRevenue: activityData?.total_revenue || mockActivities.reduce((s, a) => s + a.actual_revenue, 0),
  }

  const activityColumns = [
    { title: '活动名称', dataIndex: 'name', key: 'name', width: 200, render: (n: string, record: MarketingActivity) => <div><div style={{ fontWeight: 500, fontSize: 13 }}>{n}</div><div style={{ fontSize: 10, color: '#999' }}>{record.description.substring(0, 40)}...</div></div> },
    { title: '类型', dataIndex: 'type', key: 'type', width: 100, render: (t: string) => <Tag color={activityTypeColors[t]}>{activityTypeText[t]}</Tag> },
    { title: '状态', dataIndex: 'status', key: 'status', width: 100, render: (s: string) => <Tag color={activityStatusColors[s]} icon={s === 'ongoing' ? <PlayCircleOutlined /> : null}>{activityStatusText[s]}</Tag> },
    { title: '活动时间', key: 'time', width: 200, render: (_: any, record: MarketingActivity) => <div><div style={{ fontSize: 12 }}>{record.start_date}</div><div style={{ fontSize: 10, color: '#999' }}>至 {record.end_date}</div></div> },
    { title: '预算', dataIndex: 'budget', key: 'budget', width: 100, render: (v: number) => <Text>${v.toLocaleString()}</Text> },
    { title: '已花费', dataIndex: 'spent', key: 'spent', width: 100, render: (v: number, record: MarketingActivity) => <div><Text>${v.toLocaleString()}</Text><Progress percent={Math.round((v / record.budget) * 100)} size="small" showInfo={false} style={{ marginTop: 4 }} /></div> },
    { title: '目标收入', dataIndex: 'target_revenue', key: 'target_revenue', width: 110, render: (v: number) => <Text>${v.toLocaleString()}</Text> },
    { title: '实际收入', dataIndex: 'actual_revenue', key: 'actual_revenue', width: 110, render: (v: number, record: MarketingActivity) => v > 0 ? <div><Text strong style={{ color: v >= record.target_revenue ? '#52c41a' : '#faad14' }}>${v.toLocaleString()}</Text><div style={{ fontSize: 10, color: v >= record.target_revenue ? '#52c41a' : '#faad14' }}>{Math.round((v / record.target_revenue) * 100)}% 达成</div></div> : '-' },
    { title: '折扣力度', dataIndex: 'discount_rate', key: 'discount_rate', width: 100, render: (v: number) => v > 0 ? <Tag color="red">{v}% OFF</Tag> : '-' },
    { title: '操作', key: 'actions', width: 180, render: (_: any, record: MarketingActivity) => (
      <Space size="small">
        <Button size="small" icon={<EyeOutlined />} onClick={() => { setViewingActivity(record); setDetailModalOpen(true) }}>详情</Button>
        <Button size="small" icon={<EditOutlined />} onClick={() => message.info('编辑活动')}>编辑</Button>
        {record.status === 'planning' && <Button size="small" type="primary" icon={<PlayCircleOutlined />} onClick={() => message.success('活动已启动')}>启动</Button>}
        {record.status === 'ongoing' && <Button size="small" danger icon={<PauseCircleOutlined />} onClick={() => message.info('活动已暂停')}>暂停</Button>}
      </Space>
    )},
  ]

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <CalendarOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>营销活动策划</Title>
            <Text type="secondary">活动日历、活动管理、任务清单、效果分析</Text>
          </div>
        </Space>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => message.success('数据已刷新')}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { createForm.resetFields(); setCreateModalOpen(true) }}>创建活动</Button>
        </Space>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={4}><Card size="small"><Statistic title="活动总数" value={stats.totalActivities} prefix={<CalendarOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="进行中" value={stats.ongoing} valueStyle={{ color: '#52c41a' }} prefix={<PlayCircleOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="即将开始" value={stats.upcoming} valueStyle={{ color: '#1890ff' }} prefix={<ClockCircleOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="策划中" value={stats.planning} valueStyle={{ color: '#faad14' }} prefix={<EditOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="总预算" value={stats.totalBudget} prefix="$" valueStyle={{ color: '#722ed1' }} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="累计收入" value={stats.totalRevenue} prefix="$" valueStyle={{ color: '#52c41a' }} /></Card></Col>
      </Row>

      <Card size="small">
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'list',
              label: '活动列表',
              children: (
                <div>
                  <Space wrap style={{ marginBottom: 16 }}>
                    <Input placeholder="搜索活动名称" prefix={<SearchOutlined />} style={{ width: 200 }} allowClear />
                    <Select defaultValue="all" style={{ width: 120 }} options={[
                      { value: 'all', label: '全部类型' },
                      { value: 'flash_sale', label: '限时秒杀' },
                      { value: 'discount', label: '折扣促销' },
                      { value: 'bundle', label: '捆绑销售' },
                      { value: 'coupon', label: '优惠券' },
                      { value: 'seasonal', label: '节日活动' },
                      { value: 'new_product', label: '新品发布' },
                      { value: 'loyalty', label: '会员专享' },
                    ]} />
                    <Select defaultValue="all" style={{ width: 120 }} options={[
                      { value: 'all', label: '全部状态' },
                      { value: 'planning', label: '策划中' },
                      { value: 'ongoing', label: '进行中' },
                      { value: 'upcoming', label: '即将开始' },
                      { value: 'ended', label: '已结束' },
                    ]} />
                  </Space>
                  <Table columns={activityColumns} dataSource={mockActivities} rowKey="id" pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 个活动` }} locale={{ emptyText: <Empty description="暂无活动" /> }} scroll={{ x: 1600 }} />
                </div>
              ),
            },
            {
              key: 'calendar',
              label: '活动日历',
              children: (
                <div>
                  <Alert message="2026年9月活动日历" description="点击日期查看当天活动详情，绿色表示进行中，蓝色表示即将开始，橙色表示已结束。" type="info" showIcon style={{ marginBottom: 16 }} />
                  <Card size="small">
                    <Calendar
                      fullscreen={false}
                      dateRender={(date) => {
                        const day = date.date()
                        let activities: MarketingActivity[] = []
                        mockActivities.forEach(a => {
                          const start = new Date(a.start_date).getDate()
                          const end = new Date(a.end_date).getDate()
                          if (day >= start && day <= end) {
                            activities.push(a)
                          }
                        })
                        return (
                          <div style={{ height: '100%' }}>
                            {activities.length > 0 && (
                              <div style={{ marginTop: 4 }}>
                                {activities.slice(0, 2).map((a, idx) => (
                                  <div key={idx} style={{ fontSize: 10, padding: '2px 4px', background: a.status === 'ongoing' ? '#f6ffed' : a.status === 'upcoming' ? '#e6f7ff' : '#fff7e6', borderRadius: 2, marginBottom: 2, color: a.status === 'ongoing' ? '#52c41a' : a.status === 'upcoming' ? '#1890ff' : '#faad14', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                    {a.name}
                                  </div>
                                ))}
                                {activities.length > 2 && <div style={{ fontSize: 10, color: '#999' }}>+{activities.length - 2}更多</div>}
                              </div>
                            )}
                          </div>
                        )
                      }}
                    />
                  </Card>
                </div>
              ),
            },
            {
              key: 'tasks',
              label: '任务清单',
              children: (
                <div>
                  <Space wrap style={{ marginBottom: 16 }}>
                    <Select defaultValue="all" style={{ width: 150 }} options={[
                      { value: 'all', label: '全部活动' },
                      ...mockActivities.map(a => ({ value: a.id, label: a.name })),
                    ]} />
                    <Select defaultValue="all" style={{ width: 120 }} options={[
                      { value: 'all', label: '全部状态' },
                      { value: 'pending', label: '待处理' },
                      { value: 'in_progress', label: '进行中' },
                      { value: 'completed', label: '已完成' },
                    ]} />
                    <Button type="primary" icon={<PlusOutlined />} onClick={() => message.info('添加任务')}>添加任务</Button>
                  </Space>
                  <Table
                    dataSource={mockTasks}
                    rowKey="id"
                    pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 个任务` }}
                    locale={{ emptyText: <Empty description="暂无任务" /> }}
                    columns={[
                      { title: '任务名称', dataIndex: 'name', key: 'name', width: 250 },
                      { title: '所属活动', dataIndex: 'activity_id', key: 'activity_id', width: 150, render: (id: string) => mockActivities.find(a => a.id === id)?.name || '-' },
                      { title: '负责人', dataIndex: 'assignee', key: 'assignee', width: 120 },
                      { title: '优先级', dataIndex: 'priority', key: 'priority', width: 100, render: (p: string) => <Tag color={p === 'high' ? 'red' : p === 'medium' ? 'orange' : 'blue'}>{p === 'high' ? '高' : p === 'medium' ? '中' : '低'}</Tag> },
                      { title: '截止日期', dataIndex: 'due_date', key: 'due_date', width: 120 },
                      { title: '状态', dataIndex: 'status', key: 'status', width: 100, render: (s: string) => <Tag color={s === 'completed' ? 'green' : s === 'in_progress' ? 'blue' : 'default'} icon={s === 'in_progress' ? <SyncOutlined spin /> : null}>{s === 'completed' ? '已完成' : s === 'in_progress' ? '进行中' : '待处理'}</Tag> },
                      { title: '操作', key: 'actions', width: 120, render: (_: any, record: ActivityTask) => (
                        <Space size="small">
                          {record.status !== 'completed' && <Button size="small" type="primary" icon={<CheckSquareOutlined />} onClick={() => message.success('任务已完成')}>完成</Button>}
                        </Space>
                      )},
                    ]}
                  />
                </div>
              ),
            },
            {
              key: 'analytics',
              label: '效果分析',
              children: (
                <div>
                  <Row gutter={16}>
                    <Col span={12}>
                      <Card size="small" title="活动收入对比" style={{ marginBottom: 16 }}>
                        <div style={{ height: 250, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#fafafa', borderRadius: 8 }}>
                          <Text type="secondary">收入对比图表（接入真实数据后展示）</Text>
                        </div>
                      </Card>
                    </Col>
                    <Col span={12}>
                      <Card size="small" title="活动类型效果排名" style={{ marginBottom: 16 }}>
                        <List
                          size="small"
                          dataSource={[
                            { type: '夏季清仓大促', revenue: 45600, roi: 6.1, orders: 485 },
                            { type: '秋季新品发布', revenue: 18500, roi: 5.8, orders: 156 },
                            { type: '新客优惠券活动', revenue: 18500, roi: 7.4, orders: 185 },
                            { type: '户外装备捆绑套餐', revenue: 6800, roi: 8.5, orders: 52 },
                          ]}
                          renderItem={(item, idx) => (
                            <List.Item>
                              <List.Item.Meta
                                avatar={<Avatar size="small" style={{ backgroundColor: idx < 3 ? '#f5222d' : '#1890ff' }}>{idx + 1}</Avatar>}
                                title={<div style={{ display: 'flex', justifyContent: 'space-between' }}><Text style={{ fontSize: 13 }}>{item.type}</Text><Text strong style={{ color: '#52c41a' }}>${item.revenue.toLocaleString()}</Text></div>}
                                description={<div style={{ display: 'flex', gap: 16, fontSize: 11, color: '#999' }}><span>ROI: {item.roi}:1</span><span>订单: {item.orders}</span></div>}
                              />
                            </List.Item>
                          )}
                        />
                      </Card>
                    </Col>
                  </Row>
                </div>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title={`活动详情 - ${viewingActivity?.name || ''}`}
        open={detailModalOpen}
        onCancel={() => setDetailModalOpen(false)}
        footer={[
          <Button key="close" onClick={() => setDetailModalOpen(false)}>关闭</Button>,
        ]}
        width={800}
      >
        {viewingActivity && (
          <div>
            <Descriptions column={3} bordered size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="活动类型"><Tag color={activityTypeColors[viewingActivity.type]}>{activityTypeText[viewingActivity.type]}</Tag></Descriptions.Item>
              <Descriptions.Item label="状态"><Tag color={activityStatusColors[viewingActivity.status]}>{activityStatusText[viewingActivity.status]}</Tag></Descriptions.Item>
              <Descriptions.Item label="折扣力度">{viewingActivity.discount_rate > 0 ? <Tag color="red">{viewingActivity.discount_rate}% OFF</Tag> : '-'}</Descriptions.Item>
              <Descriptions.Item label="开始时间">{viewingActivity.start_date}</Descriptions.Item>
              <Descriptions.Item label="结束时间">{viewingActivity.end_date}</Descriptions.Item>
              <Descriptions.Item label="参与产品">{viewingActivity.products_count}个</Descriptions.Item>
              <Descriptions.Item label="推广渠道" span={3}><Space wrap>{viewingActivity.channels.map((c, idx) => <Tag key={idx} color="blue">{c}</Tag>)}</Space></Descriptions.Item>
            </Descriptions>

            <Alert message="活动描述" description={viewingActivity.description} type="info" showIcon style={{ marginBottom: 16 }} />

            <Title level={5}>预算与花费</Title>
            <Row gutter={16} style={{ marginBottom: 16 }}>
              <Col span={8}><Card size="small"><Statistic title="预算" value={viewingActivity.budget} prefix="$" /></Card></Col>
              <Col span={8}><Card size="small"><Statistic title="已花费" value={viewingActivity.spent} prefix="$" valueStyle={{ color: '#faad14' }} /></Card></Col>
              <Col span={8}><Card size="small"><Statistic title="剩余预算" value={viewingActivity.budget - viewingActivity.spent} prefix="$" valueStyle={{ color: '#52c41a' }} /></Card></Col>
            </Row>

            <Title level={5}>目标与实际</Title>
            <Row gutter={16}>
              <Col span={6}>
                <Card size="small">
                  <Statistic title="目标收入" value={viewingActivity.target_revenue} prefix="$" />
                  <Divider style={{ margin: '8px 0' }} />
                  <Statistic title="实际收入" value={viewingActivity.actual_revenue} prefix="$" valueStyle={{ color: viewingActivity.actual_revenue >= viewingActivity.target_revenue ? '#52c41a' : '#faad14' }} />
                  <div style={{ fontSize: 11, color: '#999', marginTop: 4 }}>达成率: {viewingActivity.target_revenue > 0 ? Math.round((viewingActivity.actual_revenue / viewingActivity.target_revenue) * 100) : 0}%</div>
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small">
                  <Statistic title="目标订单" value={viewingActivity.target_orders} suffix="单" />
                  <Divider style={{ margin: '8px 0' }} />
                  <Statistic title="实际订单" value={viewingActivity.actual_orders} suffix="单" valueStyle={{ color: viewingActivity.actual_orders >= viewingActivity.target_orders ? '#52c41a' : '#faad14' }} />
                  <div style={{ fontSize: 11, color: '#999', marginTop: 4 }}>达成率: {viewingActivity.target_orders > 0 ? Math.round((viewingActivity.actual_orders / viewingActivity.target_orders) * 100) : 0}%</div>
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small">
                  <Statistic title="客单价" value={viewingActivity.actual_orders > 0 ? Math.round(viewingActivity.actual_revenue / viewingActivity.actual_orders) : 0} prefix="$" />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small">
                  <Statistic title="ROI" value={viewingActivity.spent > 0 ? (viewingActivity.actual_revenue / viewingActivity.spent).toFixed(1) : 0} suffix=":1" valueStyle={{ color: '#52c41a' }} />
                </Card>
              </Col>
            </Row>
          </div>
        )}
      </Modal>

      <Modal
        title="创建营销活动"
        open={createModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setCreateModalOpen(false)}>取消</Button>,
          <Button key="save" icon={<SaveOutlined />} onClick={() => { message.success('活动已保存为草稿'); setCreateModalOpen(false) }}>保存草稿</Button>,
          <Button key="create" type="primary" icon={<PlusOutlined />} onClick={() => { message.success('活动已创建'); setCreateModalOpen(false) }}>创建活动</Button>,
        ]}
        width={600}
      >
        <Form form={createForm} layout="vertical">
          <Form.Item name="name" label="活动名称" rules={[{ required: true }]}>
            <Input placeholder="请输入活动名称" />
          </Form.Item>
          <Form.Item name="type" label="活动类型" rules={[{ required: true }]}>
            <Select options={[
              { value: 'flash_sale', label: '限时秒杀' },
              { value: 'discount', label: '折扣促销' },
              { value: 'bundle', label: '捆绑销售' },
              { value: 'coupon', label: '优惠券' },
              { value: 'seasonal', label: '节日活动' },
              { value: 'new_product', label: '新品发布' },
              { value: 'loyalty', label: '会员专享' },
            ]} />
          </Form.Item>
          <Form.Item name="description" label="活动描述">
            <Input.TextArea rows={3} placeholder="请输入活动描述" />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="start_date" label="开始日期" rules={[{ required: true }]}>
                <Input type="date" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="end_date" label="结束日期" rules={[{ required: true }]}>
                <Input type="date" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="budget" label="预算($)" rules={[{ required: true }]}>
                <Input type="number" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="target_revenue" label="目标收入($)" rules={[{ required: true }]}>
                <Input type="number" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="discount_rate" label="折扣力度(%)">
                <Input type="number" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="channels" label="推广渠道">
            <Select mode="multiple" options={[
              { value: '网站', label: '网站' },
              { value: 'EDM', label: 'EDM邮件' },
              { value: '社交媒体', label: '社交媒体' },
              { value: '广告投放', label: '广告投放' },
              { value: 'APP推送', label: 'APP推送' },
              { value: '站内信', label: '站内信' },
            ]} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
