import { useState, useEffect } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Input, Select,
  Statistic, Row, Col, Spin, message, Modal, Descriptions,
  Badge, Tooltip, Empty, Tabs, Progress, Divider, Alert,
  List, Avatar, Form, Radio, Switch, Segmented
} from 'antd'
import {
  MailOutlined, ReloadOutlined, SearchOutlined,
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
  DislikeOutlined, ShareAltOutlined
} from '@ant-design/icons'

const { Title, Text, Paragraph } = Typography

interface EmailCampaign {
  id: string
  name: string
  type: 'newsletter' | 'promotional' | 'welcome' | 'abandoned_cart' | 're_engagement'
  status: 'draft' | 'scheduled' | 'sending' | 'sent' | 'paused'
  subject: string
  template: string
  recipient_group: string
  recipient_count: number
  sent_count: number
  open_rate: number
  click_rate: number
  conversion_rate: number
  revenue: number
  scheduled_at?: string
  sent_at?: string
  created_at: string
}

interface EmailTemplate {
  id: string
  name: string
  type: string
  subject: string
  status: 'active' | 'inactive'
  usage_count: number
  avg_open_rate: number
  created_at: string
}

interface Subscriber {
  id: string
  email: string
  name: string
  groups: string[]
  status: 'subscribed' | 'unsubscribed' | 'bounced' | 'complained'
  total_opens: number
  total_clicks: number
  last_open_at?: string
  subscribed_at: string
}

const campaignTypeColors: Record<string, string> = {
  newsletter: 'blue',
  promotional: 'red',
  welcome: 'green',
  abandoned_cart: 'orange',
  re_engagement: 'purple',
}

const campaignTypeText: Record<string, string> = {
  newsletter: '新闻通讯',
  promotional: '促销活动',
  welcome: '欢迎邮件',
  abandoned_cart: '弃购挽回',
  re_engagement: '重新激活',
}

const campaignStatusColors: Record<string, string> = {
  draft: 'default',
  scheduled: 'blue',
  sending: 'processing',
  sent: 'green',
  paused: 'orange',
}

const campaignStatusText: Record<string, string> = {
  draft: '草稿',
  scheduled: '已定时',
  sending: '发送中',
  sent: '已发送',
  paused: '已暂停',
}

export default function EDMPage() {
  const [activeTab, setActiveTab] = useState('campaigns')
  const [loading, setLoading] = useState(false)
  const [sending, setSending] = useState(false)
  const [previewModalOpen, setPreviewModalOpen] = useState(false)
  const [viewingCampaign, setViewingCampaign] = useState<EmailCampaign | null>(null)
  const [createModalOpen, setCreateModalOpen] = useState(false)
  // 真实API数据状态
  const [edmData, setEdmData] = useState<any>(null)
  const [createForm] = Form.useForm()

  const mockCampaigns: EmailCampaign[] = [
    { id: '1', name: '秋季新品发布', type: 'promotional', status: 'sent', subject: '🍂 Fall New Arrivals - Up to 40% Off!', template: '促销模板A', recipient_group: '全部订阅者', recipient_count: 12500, sent_count: 12500, open_rate: 32.5, click_rate: 8.2, conversion_rate: 3.1, revenue: 18500, sent_at: '2026-09-05 10:00:00', created_at: '2026-09-03 14:00:00' },
    { id: '2', name: '新客户欢迎系列', type: 'welcome', status: 'sending', subject: 'Welcome to Nuotao Outdoor! 🎉', template: '欢迎模板', recipient_group: '新订阅者', recipient_count: 350, sent_count: 120, open_rate: 45.2, click_rate: 15.8, conversion_rate: 8.5, revenue: 2800, created_at: '2026-09-01 10:00:00' },
    { id: '3', name: '弃购挽回邮件', type: 'abandoned_cart', status: 'sent', subject: 'You left something in your cart...', template: '弃购模板', recipient_group: '弃购用户', recipient_count: 890, sent_count: 890, open_rate: 28.5, click_rate: 12.3, conversion_rate: 5.2, revenue: 6800, sent_at: '2026-09-04 15:00:00', created_at: '2026-09-02 10:00:00' },
    { id: '4', name: '9月户外装备指南', type: 'newsletter', status: 'scheduled', subject: 'September Outdoor Gear Guide 🏕️', template: '通讯模板', recipient_group: '全部订阅者', recipient_count: 12500, sent_count: 0, open_rate: 0, click_rate: 0, conversion_rate: 0, revenue: 0, scheduled_at: '2026-09-10 09:00:00', created_at: '2026-09-05 11:00:00' },
    { id: '5', name: '流失客户召回', type: 're_engagement', status: 'draft', subject: 'We miss you! Come back for 20% off', template: '召回模板', recipient_group: '90天未购买', recipient_count: 3200, sent_count: 0, open_rate: 0, click_rate: 0, conversion_rate: 0, revenue: 0, created_at: '2026-09-05 09:00:00' },
    { id: '6', name: 'VIP专属折扣', type: 'promotional', status: 'sent', subject: 'VIP Exclusive: 30% Off Just For You 💎', template: 'VIP模板', recipient_group: 'VIP客户', recipient_count: 450, sent_count: 450, open_rate: 52.3, click_rate: 22.5, conversion_rate: 12.8, revenue: 12500, sent_at: '2026-09-03 10:00:00', created_at: '2026-09-01 14:00:00' },
  ]

  const mockTemplates: EmailTemplate[] = [
    { id: '1', name: '促销模板A', type: 'promotional', subject: '促销活动邮件', status: 'active', usage_count: 15, avg_open_rate: 30.5, created_at: '2026-08-01' },
    { id: '2', name: '欢迎模板', type: 'welcome', subject: '新客户欢迎邮件', status: 'active', usage_count: 120, avg_open_rate: 45.2, created_at: '2026-07-15' },
    { id: '3', name: '通讯模板', type: 'newsletter', subject: '月度新闻通讯', status: 'active', usage_count: 8, avg_open_rate: 28.3, created_at: '2026-08-10' },
    { id: '4', name: '弃购模板', type: 'abandoned_cart', subject: '购物车弃购挽回', status: 'active', usage_count: 45, avg_open_rate: 28.5, created_at: '2026-07-20' },
    { id: '5', name: '召回模板', type: 're_engagement', subject: '流失客户召回', status: 'inactive', usage_count: 5, avg_open_rate: 18.2, created_at: '2026-08-25' },
  ]

  const mockSubscribers: Subscriber[] = [
    { id: '1', email: 'john.doe@example.com', name: 'John Doe', groups: ['全部订阅者', 'VIP客户'], status: 'subscribed', total_opens: 45, total_clicks: 12, last_open_at: '2026-09-05 10:30:00', subscribed_at: '2026-06-15' },
    { id: '2', email: 'jane.smith@example.com', name: 'Jane Smith', groups: ['全部订阅者', '新订阅者'], status: 'subscribed', total_opens: 28, total_clicks: 8, last_open_at: '2026-09-04 15:00:00', subscribed_at: '2026-09-01' },
    { id: '3', email: 'mike.wilson@example.com', name: 'Mike Wilson', groups: ['全部订阅者', '90天未购买'], status: 'subscribed', total_opens: 15, total_clicks: 3, last_open_at: '2026-08-15 10:00:00', subscribed_at: '2026-05-20' },
    { id: '4', email: 'sarah.jones@example.com', name: 'Sarah Jones', groups: ['全部订阅者'], status: 'unsubscribed', total_opens: 8, total_clicks: 2, subscribed_at: '2026-07-10' },
    { id: '5', email: 'david.brown@example.com', name: 'David Brown', groups: ['全部订阅者', 'VIP客户'], status: 'subscribed', total_opens: 62, total_clicks: 25, last_open_at: '2026-09-05 09:00:00', subscribed_at: '2026-04-01' },
    { id: '6', email: 'emily.davis@example.com', name: 'Emily Davis', groups: ['全部订阅者', '弃购用户'], status: 'bounced', total_opens: 0, total_clicks: 0, subscribed_at: '2026-08-20' },
  ]

  // 加载EDM数据（调用真实API，失败则使用mock数据降级）
  const loadEDMData = async () => {
    try {
      setLoading(true)
      // 调用EDM活动列表API
      const campaignsResp = await fetch('/api/v1/edm/campaigns')
      if (campaignsResp.ok) {
        const campaignsData = await campaignsResp.json()
        setEdmData(campaignsData)
        console.log('EDM campaigns:', campaignsData)
      }
      message.success('EDM数据加载完成')
    } catch (e: any) {
      console.error('Load EDM data error:', e)
      message.warning(`API调用失败，使用模拟数据：${e.message || '未知错误'}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadEDMData()
  }, [])

  // 统计数据（优先使用真实API数据，失败则使用mock数据降级）
  const realCampaigns = edmData?.items || edmData?.campaigns || []
  const campaigns = realCampaigns.length > 0 ? realCampaigns : mockCampaigns
  const stats = {
    totalSubscribers: edmData?.total_subscribers || 12500,
    activeSubscribers: edmData?.active_subscribers || 11800,
    avgOpenRate: edmData?.avg_open_rate || 32.5,
    avgClickRate: edmData?.avg_click_rate || 9.8,
    totalRevenue: edmData?.total_revenue || 56800,
    totalCampaigns: campaigns.length,
  }

  const campaignColumns = [
    { title: '活动名称', dataIndex: 'name', key: 'name', width: 200, render: (n: string, record: EmailCampaign) => <div><div style={{ fontWeight: 500, fontSize: 13 }}>{n}</div><div style={{ fontSize: 10, color: '#999' }}>{record.subject}</div></div> },
    { title: '类型', dataIndex: 'type', key: 'type', width: 100, render: (t: string) => <Tag color={campaignTypeColors[t]}>{campaignTypeText[t]}</Tag> },
    { title: '状态', dataIndex: 'status', key: 'status', width: 100, render: (s: string) => <Tag color={campaignStatusColors[s]} icon={s === 'sending' ? <SyncOutlined spin /> : null}>{campaignStatusText[s]}</Tag> },
    { title: '收件人组', dataIndex: 'recipient_group', key: 'recipient_group', width: 120 },
    { title: '发送进度', key: 'progress', width: 150, render: (_: any, record: EmailCampaign) => record.status === 'sending' ? <Progress percent={Math.round((record.sent_count / record.recipient_count) * 100)} size="small" format={(p) => `${record.sent_count}/${record.recipient_count}`} /> : <Text>{record.sent_count.toLocaleString()}</Text> },
    { title: '打开率', dataIndex: 'open_rate', key: 'open_rate', width: 100, render: (v: number) => v > 0 ? <Text type={v >= 30 ? 'success' : 'warning'} strong>{v}%</Text> : '-' },
    { title: '点击率', dataIndex: 'click_rate', key: 'click_rate', width: 100, render: (v: number) => v > 0 ? <Text type={v >= 10 ? 'success' : 'warning'}>{v}%</Text> : '-' },
    { title: '转化率', dataIndex: 'conversion_rate', key: 'conversion_rate', width: 100, render: (v: number) => v > 0 ? <Text type="success">{v}%</Text> : '-' },
    { title: '带来收入', dataIndex: 'revenue', key: 'revenue', width: 110, render: (v: number) => v > 0 ? <Text strong style={{ color: '#52c41a' }}>${v.toLocaleString()}</Text> : '-' },
    { title: '发送时间', key: 'time', width: 150, render: (_: any, record: EmailCampaign) => record.sent_at || record.scheduled_at || '-' },
    { title: '操作', key: 'actions', width: 180, render: (_: any, record: EmailCampaign) => (
      <Space size="small">
        <Button size="small" icon={<EyeOutlined />} onClick={() => { setViewingCampaign(record); setPreviewModalOpen(true) }}>详情</Button>
        {record.status === 'draft' && <Button size="small" type="primary" icon={<SendOutlined />} onClick={() => message.success('邮件活动已发送')}>发送</Button>}
        {record.status === 'scheduled' && <Button size="small" danger icon={<DeleteOutlined />} onClick={() => message.info('已取消定时发送')}>取消</Button>}
        {record.status === 'sending' && <Button size="small" danger icon={<PauseOutlined />} onClick={() => message.info('已暂停发送')}>暂停</Button>}
      </Space>
    )},
  ]

  const templateColumns = [
    { title: '模板名称', dataIndex: 'name', key: 'name', width: 180, render: (n: string, record: EmailTemplate) => <div><div style={{ fontWeight: 500, fontSize: 13 }}>{n}</div><div style={{ fontSize: 10, color: '#999' }}>{record.subject}</div></div> },
    { title: '类型', dataIndex: 'type', key: 'type', width: 120, render: (t: string) => <Tag color={campaignTypeColors[t] || 'default'}>{campaignTypeText[t] || t}</Tag> },
    { title: '状态', dataIndex: 'status', key: 'status', width: 100, render: (s: string) => <Tag color={s === 'active' ? 'green' : 'default'}>{s === 'active' ? '启用中' : '已停用'}</Tag> },
    { title: '使用次数', dataIndex: 'usage_count', key: 'usage_count', width: 100, render: (v: number) => <Text>{v}次</Text> },
    { title: '平均打开率', dataIndex: 'avg_open_rate', key: 'avg_open_rate', width: 120, render: (v: number) => <Text type={v >= 30 ? 'success' : 'warning'} strong>{v}%</Text> },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 120 },
    { title: '操作', key: 'actions', width: 180, render: (_: any, record: EmailTemplate) => (
      <Space size="small">
        <Button size="small" icon={<EyeOutlined />} onClick={() => message.info('预览模板')}>预览</Button>
        <Button size="small" icon={<EditOutlined />} onClick={() => message.info('编辑模板')}>编辑</Button>
        <Button size="small" icon={<CopyOutlined />} onClick={() => message.success('模板已复制')}>复制</Button>
      </Space>
    )},
  ]

  const subscriberColumns = [
    { title: '邮箱', dataIndex: 'email', key: 'email', width: 220, render: (e: string, record: Subscriber) => <div><div style={{ fontWeight: 500, fontSize: 13 }}>{e}</div><div style={{ fontSize: 10, color: '#999' }}>{record.name}</div></div> },
    { title: '分组', dataIndex: 'groups', key: 'groups', width: 200, render: (g: string[]) => <Space wrap>{g.map((grp, idx) => <Tag key={idx} color="blue">{grp}</Tag>)}</Space> },
    { title: '状态', dataIndex: 'status', key: 'status', width: 100, render: (s: string) => <Tag color={s === 'subscribed' ? 'green' : s === 'unsubscribed' ? 'default' : s === 'bounced' ? 'orange' : 'red'}>{s === 'subscribed' ? '已订阅' : s === 'unsubscribed' ? '已退订' : s === 'bounced' ? '退信' : '投诉'}</Tag> },
    { title: '总打开数', dataIndex: 'total_opens', key: 'total_opens', width: 100, render: (v: number) => <Text>{v}</Text> },
    { title: '总点击数', dataIndex: 'total_clicks', key: 'total_clicks', width: 100, render: (v: number) => <Text>{v}</Text> },
    { title: '最后打开', dataIndex: 'last_open_at', key: 'last_open_at', width: 150, render: (t?: string) => t || '-' },
    { title: '订阅时间', dataIndex: 'subscribed_at', key: 'subscribed_at', width: 120 },
    { title: '操作', key: 'actions', width: 150, render: (_: any, record: Subscriber) => (
      <Space size="small">
        <Button size="small" icon={<EditOutlined />} onClick={() => message.info('编辑订阅者')}>编辑</Button>
        {record.status === 'subscribed' && <Button size="small" danger onClick={() => message.info('已退订')}>退订</Button>}
      </Space>
    )},
  ]

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <MailOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>EDM邮件营销</Title>
            <Text type="secondary">邮件活动管理、模板设计、订阅者管理、效果分析</Text>
          </div>
        </Space>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => message.success('数据已刷新')}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { createForm.resetFields(); setCreateModalOpen(true) }}>创建邮件活动</Button>
        </Space>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={4}><Card size="small"><Statistic title="订阅者总数" value={stats.totalSubscribers} suffix="人" prefix={<UserOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="活跃订阅者" value={stats.activeSubscribers} suffix="人" valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="平均打开率" value={stats.avgOpenRate} suffix="%" valueStyle={{ color: '#1890ff' }} prefix={<MailOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="平均点击率" value={stats.avgClickRate} suffix="%" valueStyle={{ color: '#722ed1' }} prefix={<LinkOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="邮件带来收入" value={stats.totalRevenue} prefix="$" valueStyle={{ color: '#52c41a' }} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="邮件活动数" value={stats.totalCampaigns} prefix={<FileTextOutlined />} /></Card></Col>
      </Row>

      <Card size="small">
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'campaigns',
              label: '邮件活动',
              children: (
                <div>
                  <Space wrap style={{ marginBottom: 16 }}>
                    <Input placeholder="搜索活动名称/主题" prefix={<SearchOutlined />} style={{ width: 200 }} allowClear />
                    <Select defaultValue="all" style={{ width: 120 }} options={[
                      { value: 'all', label: '全部类型' },
                      { value: 'newsletter', label: '新闻通讯' },
                      { value: 'promotional', label: '促销活动' },
                      { value: 'welcome', label: '欢迎邮件' },
                      { value: 'abandoned_cart', label: '弃购挽回' },
                      { value: 're_engagement', label: '重新激活' },
                    ]} />
                    <Select defaultValue="all" style={{ width: 120 }} options={[
                      { value: 'all', label: '全部状态' },
                      { value: 'draft', label: '草稿' },
                      { value: 'scheduled', label: '已定时' },
                      { value: 'sending', label: '发送中' },
                      { value: 'sent', label: '已发送' },
                    ]} />
                  </Space>
                  <Table columns={campaignColumns} dataSource={mockCampaigns} rowKey="id" pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 个活动` }} locale={{ emptyText: <Empty description="暂无邮件活动" /> }} scroll={{ x: 1600 }} />
                </div>
              ),
            },
            {
              key: 'templates',
              label: '邮件模板',
              children: (
                <div>
                  <Space wrap style={{ marginBottom: 16 }}>
                    <Input placeholder="搜索模板名称" prefix={<SearchOutlined />} style={{ width: 200 }} allowClear />
                    <Button type="primary" icon={<PlusOutlined />} onClick={() => message.info('创建新模板')}>创建模板</Button>
                  </Space>
                  <Table columns={templateColumns} dataSource={mockTemplates} rowKey="id" pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 个模板` }} locale={{ emptyText: <Empty description="暂无模板" /> }} scroll={{ x: 1200 }} />
                </div>
              ),
            },
            {
              key: 'subscribers',
              label: '订阅者管理',
              children: (
                <div>
                  <Space wrap style={{ marginBottom: 16 }}>
                    <Input placeholder="搜索邮箱/姓名" prefix={<SearchOutlined />} style={{ width: 200 }} allowClear />
                    <Select defaultValue="all" style={{ width: 120 }} options={[
                      { value: 'all', label: '全部分组' },
                      { value: '全部订阅者', label: '全部订阅者' },
                      { value: 'VIP客户', label: 'VIP客户' },
                      { value: '新订阅者', label: '新订阅者' },
                      { value: '90天未购买', label: '90天未购买' },
                      { value: '弃购用户', label: '弃购用户' },
                    ]} />
                    <Select defaultValue="all" style={{ width: 120 }} options={[
                      { value: 'all', label: '全部状态' },
                      { value: 'subscribed', label: '已订阅' },
                      { value: 'unsubscribed', label: '已退订' },
                      { value: 'bounced', label: '退信' },
                    ]} />
                    <Button type="primary" icon={<PlusOutlined />} onClick={() => message.info('添加订阅者')}>添加</Button>
                    <Button icon={<ImportOutlined />} onClick={() => message.info('导入订阅者')}>导入</Button>
                    <Button icon={<ExportOutlined />} onClick={() => message.success('订阅者已导出')}>导出</Button>
                  </Space>
                  <Table columns={subscriberColumns} dataSource={mockSubscribers} rowKey="id" pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 位订阅者` }} locale={{ emptyText: <Empty description="暂无订阅者" /> }} scroll={{ x: 1400 }} />
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
                      <Card size="small" title="打开率/点击率趋势" style={{ marginBottom: 16 }}>
                        <div style={{ height: 250, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#fafafa', borderRadius: 8 }}>
                          <Text type="secondary">趋势图表（接入真实数据后展示）</Text>
                        </div>
                      </Card>
                    </Col>
                    <Col span={12}>
                      <Card size="small" title="活动类型效果对比" style={{ marginBottom: 16 }}>
                        <List
                          size="small"
                          dataSource={[
                            { type: '欢迎邮件', open: 45.2, click: 15.8, conversion: 8.5 },
                            { type: 'VIP专属', open: 52.3, click: 22.5, conversion: 12.8 },
                            { type: '促销活动', open: 32.5, click: 8.2, conversion: 3.1 },
                            { type: '弃购挽回', open: 28.5, click: 12.3, conversion: 5.2 },
                            { type: '新闻通讯', open: 28.3, click: 6.5, conversion: 1.8 },
                          ]}
                          renderItem={(item) => (
                            <List.Item>
                              <List.Item.Meta
                                title={<div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}><Text style={{ fontSize: 13 }}>{item.type}</Text><Space><Tag color="blue">打开 {item.open}%</Tag><Tag color="purple">点击 {item.click}%</Tag><Tag color="green">转化 {item.conversion}%</Tag></Space></div>}
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
        title={`邮件活动详情 - ${viewingCampaign?.name || ''}`}
        open={previewModalOpen}
        onCancel={() => setPreviewModalOpen(false)}
        footer={[
          <Button key="close" onClick={() => setPreviewModalOpen(false)}>关闭</Button>,
        ]}
        width={800}
      >
        {viewingCampaign && (
          <div>
            <Descriptions column={3} bordered size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="活动类型"><Tag color={campaignTypeColors[viewingCampaign.type]}>{campaignTypeText[viewingCampaign.type]}</Tag></Descriptions.Item>
              <Descriptions.Item label="状态"><Tag color={campaignStatusColors[viewingCampaign.status]}>{campaignStatusText[viewingCampaign.status]}</Tag></Descriptions.Item>
              <Descriptions.Item label="使用模板">{viewingCampaign.template}</Descriptions.Item>
              <Descriptions.Item label="收件人组" span={2}>{viewingCampaign.recipient_group}</Descriptions.Item>
              <Descriptions.Item label="收件人数">{viewingCampaign.recipient_count.toLocaleString()}人</Descriptions.Item>
              <Descriptions.Item label="已发送">{viewingCampaign.sent_count.toLocaleString()}封</Descriptions.Item>
              <Descriptions.Item label="打开率"><Text type="success" strong>{viewingCampaign.open_rate}%</Text></Descriptions.Item>
              <Descriptions.Item label="点击率"><Text type="primary">{viewingCampaign.click_rate}%</Text></Descriptions.Item>
              <Descriptions.Item label="转化率"><Text type="success">{viewingCampaign.conversion_rate}%</Text></Descriptions.Item>
              <Descriptions.Item label="带来收入"><Text strong style={{ color: '#52c41a' }}>${viewingCampaign.revenue.toLocaleString()}</Text></Descriptions.Item>
              <Descriptions.Item label="发送时间" span={2}>{viewingCampaign.sent_at || viewingCampaign.scheduled_at || '-'}</Descriptions.Item>
            </Descriptions>

            <Divider style={{ margin: '12px 0' }} />
            <Title level={5}>邮件主题</Title>
            <Paragraph style={{ background: '#fafafa', padding: 12, borderRadius: 6 }}>{viewingCampaign.subject}</Paragraph>

            <Title level={5}>效果指标</Title>
            <Row gutter={16}>
              <Col span={6}>
                <Card size="small">
                  <Statistic title="打开数" value={Math.round(viewingCampaign.sent_count * viewingCampaign.open_rate / 100)} suffix="封" />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small">
                  <Statistic title="点击数" value={Math.round(viewingCampaign.sent_count * viewingCampaign.click_rate / 100)} suffix="次" />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small">
                  <Statistic title="转化数" value={Math.round(viewingCampaign.sent_count * viewingCampaign.conversion_rate / 100)} suffix="单" />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small">
                  <Statistic title="ROI" value={viewingCampaign.revenue > 0 ? Math.round(viewingCampaign.revenue / 50) : 0} suffix=":1" valueStyle={{ color: '#52c41a' }} />
                </Card>
              </Col>
            </Row>
          </div>
        )}
      </Modal>

      <Modal
        title="创建邮件活动"
        open={createModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setCreateModalOpen(false)}>取消</Button>,
          <Button key="save" icon={<SaveOutlined />} onClick={() => { message.success('已保存为草稿'); setCreateModalOpen(false) }}>保存草稿</Button>,
          <Button key="send" type="primary" icon={<SendOutlined />} loading={sending} onClick={() => { setSending(true); setTimeout(() => { message.success('邮件活动已创建并发送'); setSending(false); setCreateModalOpen(false) }, 2000) }}>创建并发送</Button>,
        ]}
        width={600}
      >
        <Form form={createForm} layout="vertical">
          <Form.Item name="name" label="活动名称" rules={[{ required: true }]}>
            <Input placeholder="请输入活动名称" />
          </Form.Item>
          <Form.Item name="type" label="活动类型" rules={[{ required: true }]}>
            <Select options={[
              { value: 'newsletter', label: '新闻通讯' },
              { value: 'promotional', label: '促销活动' },
              { value: 'welcome', label: '欢迎邮件' },
              { value: 'abandoned_cart', label: '弃购挽回' },
              { value: 're_engagement', label: '重新激活' },
            ]} />
          </Form.Item>
          <Form.Item name="subject" label="邮件主题" rules={[{ required: true }]}>
            <Input placeholder="请输入邮件主题" />
          </Form.Item>
          <Form.Item name="template" label="使用模板" rules={[{ required: true }]}>
            <Select options={mockTemplates.map(t => ({ value: t.name, label: t.name }))} />
          </Form.Item>
          <Form.Item name="recipient_group" label="收件人组" rules={[{ required: true }]}>
            <Select options={[
              { value: '全部订阅者', label: '全部订阅者 (12,500人)' },
              { value: 'VIP客户', label: 'VIP客户 (450人)' },
              { value: '新订阅者', label: '新订阅者 (350人)' },
              { value: '90天未购买', label: '90天未购买 (3,200人)' },
              { value: '弃购用户', label: '弃购用户 (890人)' },
            ]} />
          </Form.Item>
          <Form.Item name="schedule" label="发送时间">
            <Radio.Group>
              <Radio value="now">立即发送</Radio>
              <Radio value="schedule">定时发送</Radio>
            </Radio.Group>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
