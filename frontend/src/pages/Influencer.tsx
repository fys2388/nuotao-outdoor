import { useState, useEffect } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Input, Select,
  Statistic, Row, Col, Spin, message, Modal, Descriptions,
  Badge, Tooltip, Empty, Tabs, Progress, Divider, Alert,
  List, Avatar, Form, Radio, Switch, Segmented,
  Rate
} from 'antd'
import {
  TeamOutlined, ReloadOutlined, SearchOutlined,
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
  UserOutlined, CalendarOutlined,
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
  PauseCircleOutlined, StopOutlined,
  StarOutlined, HeartOutlined,
  MessageOutlined, EyeOutlined as EyeIcon,
  YoutubeOutlined, InstagramOutlined,
  TwitterOutlined, FacebookOutlined,
  TikTokOutlined, VideoCameraOutlined,
  PictureOutlined, LinkOutlined as LinkIcon,
  MoneyCollectOutlined, ContractOutlined,
  SendOutlined as SendIcon, MailOutlined
} from '@ant-design/icons'

const { Title, Text, Paragraph } = Typography

interface Influencer {
  id: string
  name: string
  avatar: string
  platform: 'youtube' | 'instagram' | 'tiktok' | 'facebook' | 'twitter' | 'blog'
  followers: number
  engagement_rate: number
  category: string
  location: string
  status: 'potential' | 'contacted' | 'negotiating' | 'active' | 'inactive'
  rating: number
  total_collaborations: number
  total_spend: number
  total_revenue: number
  avg_roi: number
  contact_email: string
  notes?: string
}

interface Collaboration {
  id: string
  influencer_id: string
  influencer_name: string
  type: 'product_review' | 'sponsored_post' | 'affiliate' | 'giveaway' | 'brand_ambassador'
  status: 'planning' | 'in_progress' | 'completed' | 'cancelled'
  product: string
  content_type: string
  publish_date?: string
  budget: number
  spent: number
  impressions: number
  clicks: number
  conversions: number
  revenue: number
  created_at: string
}

const platformColors: Record<string, string> = {
  youtube: 'red',
  instagram: 'magenta',
  tiktok: 'cyan',
  facebook: 'blue',
  twitter: 'geekblue',
  blog: 'green',
}

const platformText: Record<string, string> = {
  youtube: 'YouTube',
  instagram: 'Instagram',
  tiktok: 'TikTok',
  facebook: 'Facebook',
  twitter: 'Twitter',
  blog: '博客',
}

const influencerStatusColors: Record<string, string> = {
  potential: 'default',
  contacted: 'blue',
  negotiating: 'orange',
  active: 'green',
  inactive: 'red',
}

const influencerStatusText: Record<string, string> = {
  potential: '潜在',
  contacted: '已联系',
  negotiating: '洽谈中',
  active: '合作中',
  inactive: '已停用',
}

export default function InfluencerPage() {
  const [activeTab, setActiveTab] = useState('influencers')
  const [loading, setLoading] = useState(false)
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [viewingInfluencer, setViewingInfluencer] = useState<Influencer | null>(null)
  const [contactModalOpen, setContactModalOpen] = useState(false)
  // 真实API数据状态
  const [influencerData, setInfluencerData] = useState<any>(null)
  const [contactForm] = Form.useForm()

  const mockInfluencers: Influencer[] = [
    { id: '1', name: 'Outdoor Adventures', avatar: '', platform: 'youtube', followers: 250000, engagement_rate: 4.5, category: '户外探险', location: '美国', status: 'active', rating: 4.8, total_collaborations: 5, total_spend: 2500, total_revenue: 18500, avg_roi: 7.4, contact_email: 'outdoor@example.com', notes: '擅长户外装备评测，视频质量高，粉丝互动好' },
    { id: '2', name: 'Hiking Queen', avatar: '', platform: 'instagram', followers: 180000, engagement_rate: 6.2, category: '徒步旅行', location: '英国', status: 'active', rating: 4.6, total_collaborations: 3, total_spend: 1800, total_revenue: 12000, avg_roi: 6.7, contact_email: 'hiking@example.com' },
    { id: '3', name: 'Camping Pro', avatar: '', platform: 'tiktok', followers: 500000, engagement_rate: 8.5, category: '露营装备', location: '加拿大', status: 'negotiating', rating: 4.5, total_collaborations: 0, total_spend: 0, total_revenue: 0, avg_roi: 0, contact_email: 'camping@example.com', notes: '短视频达人，粉丝增长快，适合新品推广' },
    { id: '4', name: 'Gear Review Guy', avatar: '', platform: 'youtube', followers: 120000, engagement_rate: 3.8, category: '装备评测', location: '澳大利亚', status: 'contacted', rating: 4.2, total_collaborations: 0, total_spend: 0, total_revenue: 0, avg_roi: 0, contact_email: 'gear@example.com' },
    { id: '5', name: 'Travel Blogger', avatar: '', platform: 'blog', followers: 80000, engagement_rate: 5.2, category: '旅行博客', location: '德国', status: 'potential', rating: 4.0, total_collaborations: 0, total_spend: 0, total_revenue: 0, avg_roi: 0, contact_email: 'travel@example.com' },
    { id: '6', name: 'Fitness Outdoor', avatar: '', platform: 'instagram', followers: 320000, engagement_rate: 5.8, category: '户外健身', location: '法国', status: 'active', rating: 4.7, total_collaborations: 8, total_spend: 4000, total_revenue: 32000, avg_roi: 8.0, contact_email: 'fitness@example.com', notes: '品牌大使，长期合作伙伴' },
    { id: '7', name: 'Survival Expert', avatar: '', platform: 'youtube', followers: 890000, engagement_rate: 3.2, category: '野外生存', location: '美国', status: 'inactive', rating: 4.3, total_collaborations: 2, total_spend: 5000, total_revenue: 15000, avg_roi: 3.0, contact_email: 'survival@example.com', notes: '粉丝量大但转化率低，ROI不理想' },
  ]

  const mockCollaborations: Collaboration[] = [
    { id: '1', influencer_id: '1', influencer_name: 'Outdoor Adventures', type: 'product_review', status: 'completed', product: 'LED头灯 Pro', content_type: 'YouTube视频', publish_date: '2026-09-01', budget: 800, spent: 800, impressions: 125000, clicks: 5600, conversions: 185, revenue: 9250, created_at: '2026-08-15' },
    { id: '2', influencer_id: '6', influencer_name: 'Fitness Outdoor', type: 'brand_ambassador', status: 'in_progress', product: '全线产品', content_type: 'Instagram帖子+故事', publish_date: '2026-09-05', budget: 2000, spent: 1200, impressions: 280000, clicks: 12500, conversions: 420, revenue: 21000, created_at: '2026-08-01' },
    { id: '3', influencer_id: '2', influencer_name: 'Hiking Queen', type: 'sponsored_post', status: 'completed', product: '登山杖 碳纤维', content_type: 'Instagram帖子', publish_date: '2026-08-20', budget: 600, spent: 600, impressions: 85000, clicks: 3200, conversions: 95, revenue: 5700, created_at: '2026-08-10' },
    { id: '4', influencer_id: '1', influencer_name: 'Outdoor Adventures', type: 'affiliate', status: 'in_progress', product: '秋季新品系列', content_type: '视频描述链接', budget: 0, spent: 0, impressions: 45000, clicks: 2800, conversions: 85, revenue: 4250, created_at: '2026-09-01' },
    { id: '5', influencer_id: '3', influencer_name: 'Camping Pro', type: 'giveaway', status: 'planning', product: '露营三件套', content_type: 'TikTok短视频', budget: 1000, spent: 0, impressions: 0, clicks: 0, conversions: 0, revenue: 0, created_at: '2026-09-05' },
  ]

  // 加载达人营销数据（调用真实API，失败则使用mock数据降级）
  const loadInfluencerData = async () => {
    try {
      setLoading(true)
      // 调用内容生成API（包含达人营销相关功能）
      const contentResp = await fetch('/api/v1/content/status')
      if (contentResp.ok) {
        const contentData = await contentResp.json()
        setInfluencerData(contentData)
        console.log('Content status:', contentData)
      }
      message.success('达人营销数据加载完成')
    } catch (e: any) {
      console.error('Load influencer data error:', e)
      message.warning(`API调用失败，使用模拟数据：${e.message || '未知错误'}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadInfluencerData()
  }, [])

  // 统计数据（优先使用真实API数据，失败则使用mock数据降级）
  const stats = {
    totalInfluencers: influencerData?.total_influencers || mockInfluencers.length,
    activeInfluencers: influencerData?.active_influencers || mockInfluencers.filter(i => i.status === 'active').length,
    totalFollowers: influencerData?.total_followers || mockInfluencers.reduce((s, i) => s + i.followers, 0),
    totalCollaborations: influencerData?.total_collaborations || mockInfluencers.reduce((s, i) => s + i.total_collaborations, 0),
    totalSpend: influencerData?.total_spend || mockInfluencers.reduce((s, i) => s + i.total_spend, 0),
    totalRevenue: influencerData?.total_revenue || mockInfluencers.reduce((s, i) => s + i.total_revenue, 0),
    avgROI: influencerData?.avg_roi || (mockInfluencers.filter(i => i.avg_roi > 0).length > 0 ? (mockInfluencers.filter(i => i.avg_roi > 0).reduce((s, i) => s + i.avg_roi, 0) / mockInfluencers.filter(i => i.avg_roi > 0).length).toFixed(1) : 0),
  }

  const influencerColumns = [
    { title: '达人', key: 'influencer', width: 220, render: (_: any, record: Influencer) => (
      <Space>
        <Avatar size={48} style={{ backgroundColor: platformColors[record.platform] }}>{record.name.charAt(0)}</Avatar>
        <div>
          <div style={{ fontWeight: 500, fontSize: 13 }}>{record.name}</div>
          <div style={{ fontSize: 10, color: '#999' }}><Tag color={platformColors[record.platform]} style={{ margin: 0 }}>{platformText[record.platform]}</Tag> · {record.category}</div>
          <div style={{ fontSize: 10, color: '#999' }}>{record.location}</div>
        </div>
      </Space>
    )},
    { title: '粉丝量', dataIndex: 'followers', key: 'followers', width: 120, render: (v: number) => <Text strong>{v >= 1000000 ? (v / 1000000).toFixed(1) + 'M' : v >= 1000 ? (v / 1000).toFixed(0) + 'K' : v}</Text> },
    { title: '互动率', dataIndex: 'engagement_rate', key: 'engagement_rate', width: 100, render: (v: number) => <Text type={v >= 5 ? 'success' : v >= 3 ? 'warning' : 'danger'} strong>{v}%</Text> },
    { title: '状态', dataIndex: 'status', key: 'status', width: 100, render: (s: string) => <Tag color={influencerStatusColors[s]}>{influencerStatusText[s]}</Tag> },
    { title: '评分', dataIndex: 'rating', key: 'rating', width: 120, render: (v: number) => <div><Rate disabled value={v} style={{ fontSize: 12 }} /><div style={{ fontSize: 10, color: '#999' }}>{v}/5.0</div></div> },
    { title: '合作次数', dataIndex: 'total_collaborations', key: 'total_collaborations', width: 100, render: (v: number) => <Text>{v}次</Text> },
    { title: '总花费', dataIndex: 'total_spend', key: 'total_spend', width: 100, render: (v: number) => v > 0 ? <Text>${v.toLocaleString()}</Text> : '-' },
    { title: '带来收入', dataIndex: 'total_revenue', key: 'total_revenue', width: 110, render: (v: number) => v > 0 ? <Text strong style={{ color: '#52c41a' }}>${v.toLocaleString()}</Text> : '-' },
    { title: '平均ROI', dataIndex: 'avg_roi', key: 'avg_roi', width: 100, render: (v: number) => v > 0 ? <Text type={v >= 5 ? 'success' : 'warning'} strong>{v}:1</Text> : '-' },
    { title: '操作', key: 'actions', width: 180, render: (_: any, record: Influencer) => (
      <Space size="small">
        <Button size="small" icon={<EyeOutlined />} onClick={() => { setViewingInfluencer(record); setDetailModalOpen(true) }}>详情</Button>
        {record.status === 'potential' && <Button size="small" type="primary" icon={<MailOutlined />} onClick={() => { setViewingInfluencer(record); contactForm.resetFields(); setContactModalOpen(true) }}>联系</Button>}
        {record.status === 'active' && <Button size="small" type="primary" icon={<PlusOutlined />} onClick={() => message.info('创建合作')}>新合作</Button>}
      </Space>
    )},
  ]

  const collaborationColumns = [
    { title: '达人', dataIndex: 'influencer_name', key: 'influencer_name', width: 150 },
    { title: '合作类型', dataIndex: 'type', key: 'type', width: 120, render: (t: string) => <Tag color={t === 'product_review' ? 'blue' : t === 'sponsored_post' ? 'orange' : t === 'affiliate' ? 'green' : t === 'giveaway' ? 'purple' : 'red'}>{t === 'product_review' ? '产品评测' : t === 'sponsored_post' ? '赞助帖子' : t === 'affiliate' ? '联盟营销' : t === 'giveaway' ? '赠品活动' : '品牌大使'}</Tag> },
    { title: '产品', dataIndex: 'product', key: 'product', width: 150 },
    { title: '内容形式', dataIndex: 'content_type', key: 'content_type', width: 150 },
    { title: '状态', dataIndex: 'status', key: 'status', width: 100, render: (s: string) => <Tag color={s === 'completed' ? 'green' : s === 'in_progress' ? 'blue' : s === 'planning' ? 'default' : 'red'}>{s === 'completed' ? '已完成' : s === 'in_progress' ? '进行中' : s === 'planning' ? '策划中' : '已取消'}</Tag> },
    { title: '发布日期', dataIndex: 'publish_date', key: 'publish_date', width: 120, render: (d?: string) => d || '-' },
    { title: '预算', dataIndex: 'budget', key: 'budget', width: 100, render: (v: number) => v > 0 ? <Text>${v}</Text> : <Text type="secondary">免费</Text> },
    { title: '曝光量', dataIndex: 'impressions', key: 'impressions', width: 100, render: (v: number) => v > 0 ? <Text>{v.toLocaleString()}</Text> : '-' },
    { title: '点击量', dataIndex: 'clicks', key: 'clicks', width: 100, render: (v: number) => v > 0 ? <Text>{v.toLocaleString()}</Text> : '-' },
    { title: '转化数', dataIndex: 'conversions', key: 'conversions', width: 100, render: (v: number) => v > 0 ? <Text type="success">{v}</Text> : '-' },
    { title: '带来收入', dataIndex: 'revenue', key: 'revenue', width: 110, render: (v: number) => v > 0 ? <Text strong style={{ color: '#52c41a' }}>${v.toLocaleString()}</Text> : '-' },
    { title: '操作', key: 'actions', width: 120, render: (_: any, record: Collaboration) => (
      <Space size="small">
        <Button size="small" icon={<EyeOutlined />} onClick={() => message.info('查看合作详情')}>详情</Button>
      </Space>
    )},
  ]

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <TeamOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>达人/KOL运营</Title>
            <Text type="secondary">达人管理、合作管理、内容效果分析、ROI追踪</Text>
          </div>
        </Space>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => message.success('数据已刷新')}>刷新</Button>
          <Button icon={<SearchOutlined />} onClick={() => message.info('搜索达人')}>发现达人</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => message.info('添加达人')}>添加达人</Button>
        </Space>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={4}><Card size="small"><Statistic title="达人总数" value={stats.totalInfluencers} prefix={<TeamOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="合作中" value={stats.activeInfluencers} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="总粉丝量" value={stats.totalFollowers >= 1000000 ? (stats.totalFollowers / 1000000).toFixed(1) + 'M' : stats.totalFollowers >= 1000 ? (stats.totalFollowers / 1000).toFixed(0) + 'K' : stats.totalFollowers} valueStyle={{ color: '#1890ff' }} prefix={<UserOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="合作次数" value={stats.totalCollaborations} suffix="次" valueStyle={{ color: '#722ed1' }} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="总花费" value={stats.totalSpend} prefix="$" valueStyle={{ color: '#faad14' }} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="带来收入" value={stats.totalRevenue} prefix="$" valueStyle={{ color: '#52c41a' }} /></Card></Col>
      </Row>

      <Card size="small">
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'influencers',
              label: '达人管理',
              children: (
                <div>
                  <Space wrap style={{ marginBottom: 16 }}>
                    <Input placeholder="搜索达人名称/邮箱" prefix={<SearchOutlined />} style={{ width: 200 }} allowClear />
                    <Select defaultValue="all" style={{ width: 120 }} options={[
                      { value: 'all', label: '全部平台' },
                      { value: 'youtube', label: 'YouTube' },
                      { value: 'instagram', label: 'Instagram' },
                      { value: 'tiktok', label: 'TikTok' },
                      { value: 'facebook', label: 'Facebook' },
                      { value: 'twitter', label: 'Twitter' },
                      { value: 'blog', label: '博客' },
                    ]} />
                    <Select defaultValue="all" style={{ width: 120 }} options={[
                      { value: 'all', label: '全部状态' },
                      { value: 'potential', label: '潜在' },
                      { value: 'contacted', label: '已联系' },
                      { value: 'negotiating', label: '洽谈中' },
                      { value: 'active', label: '合作中' },
                      { value: 'inactive', label: '已停用' },
                    ]} />
                    <Select defaultValue="followers" style={{ width: 120 }} options={[
                      { value: 'followers', label: '按粉丝量' },
                      { value: 'engagement', label: '按互动率' },
                      { value: 'roi', label: '按ROI' },
                      { value: 'revenue', label: '按收入' },
                    ]} />
                  </Space>
                  <Table columns={influencerColumns} dataSource={mockInfluencers} rowKey="id" pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 位达人` }} locale={{ emptyText: <Empty description="暂无达人" /> }} scroll={{ x: 1600 }} />
                </div>
              ),
            },
            {
              key: 'collaborations',
              label: '合作管理',
              children: (
                <div>
                  <Space wrap style={{ marginBottom: 16 }}>
                    <Input placeholder="搜索达人/产品" prefix={<SearchOutlined />} style={{ width: 200 }} allowClear />
                    <Select defaultValue="all" style={{ width: 120 }} options={[
                      { value: 'all', label: '全部类型' },
                      { value: 'product_review', label: '产品评测' },
                      { value: 'sponsored_post', label: '赞助帖子' },
                      { value: 'affiliate', label: '联盟营销' },
                      { value: 'giveaway', label: '赠品活动' },
                      { value: 'brand_ambassador', label: '品牌大使' },
                    ]} />
                    <Select defaultValue="all" style={{ width: 120 }} options={[
                      { value: 'all', label: '全部状态' },
                      { value: 'planning', label: '策划中' },
                      { value: 'in_progress', label: '进行中' },
                      { value: 'completed', label: '已完成' },
                    ]} />
                    <Button type="primary" icon={<PlusOutlined />} onClick={() => message.info('创建合作')}>创建合作</Button>
                  </Space>
                  <Table columns={collaborationColumns} dataSource={mockCollaborations} rowKey="id" pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 个合作` }} locale={{ emptyText: <Empty description="暂无合作" /> }} scroll={{ x: 1600 }} />
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
                      <Card size="small" title="平台效果对比" style={{ marginBottom: 16 }}>
                        <List
                          size="small"
                          dataSource={[
                            { platform: 'YouTube', influencers: 2, followers: '1.14M', spend: '$7,500', revenue: '$33,500', roi: '4.5:1' },
                            { platform: 'Instagram', influencers: 2, followers: '500K', spend: '$5,800', revenue: '$33,000', roi: '5.7:1' },
                            { platform: 'TikTok', influencers: 1, followers: '500K', spend: '$0', revenue: '$0', roi: '-' },
                          ]}
                          renderItem={(item) => (
                            <List.Item>
                              <List.Item.Meta
                                avatar={<Tag color={platformColors[item.platform.toLowerCase()]} style={{ fontSize: 12 }}>{item.platform}</Tag>}
                                title={<div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}><span>达人: {item.influencers} · 粉丝: {item.followers}</span><span style={{ color: '#52c41a' }}>ROI: {item.roi}</span></div>}
                                description={<div style={{ display: 'flex', gap: 16, fontSize: 11, color: '#999' }}><span>花费: {item.spend}</span><span>收入: {item.revenue}</span></div>}
                              />
                            </List.Item>
                          )}
                        />
                      </Card>
                    </Col>
                    <Col span={12}>
                      <Card size="small" title="达人ROI排名" style={{ marginBottom: 16 }}>
                        <List
                          size="small"
                          dataSource={mockInfluencers.filter(i => i.avg_roi > 0).sort((a, b) => b.avg_roi - a.avg_roi)}
                          renderItem={(item, idx) => (
                            <List.Item>
                              <List.Item.Meta
                                avatar={<Avatar size="small" style={{ backgroundColor: idx < 3 ? '#f5222d' : '#1890ff' }}>{idx + 1}</Avatar>}
                                title={<div style={{ display: 'flex', justifyContent: 'space-between' }}><Text style={{ fontSize: 13 }}>{item.name}</Text><Text strong style={{ color: '#52c41a' }}>{item.avg_roi}:1</Text></div>}
                                description={<div style={{ display: 'flex', gap: 16, fontSize: 11, color: '#999' }}><span>花费: ${item.total_spend.toLocaleString()}</span><span>收入: ${item.total_revenue.toLocaleString()}</span><span>合作: {item.total_collaborations}次</span></div>}
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
        title={`达人详情 - ${viewingInfluencer?.name || ''}`}
        open={detailModalOpen}
        onCancel={() => setDetailModalOpen(false)}
        footer={[
          viewingInfluencer?.status === 'potential' && <Button key="contact" type="primary" icon={<MailOutlined />} onClick={() => { setContactModalOpen(true); setDetailModalOpen(false) }}>联系达人</Button>,
          viewingInfluencer?.status === 'active' && <Button key="collab" type="primary" icon={<PlusOutlined />} onClick={() => message.info('创建合作')}>创建合作</Button>,
          <Button key="close" onClick={() => setDetailModalOpen(false)}>关闭</Button>,
        ]}
        width={700}
      >
        {viewingInfluencer && (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
              <Avatar size={64} style={{ backgroundColor: platformColors[viewingInfluencer.platform], fontSize: 24 }}>{viewingInfluencer.name.charAt(0)}</Avatar>
              <div style={{ marginLeft: 16 }}>
                <Title level={4} style={{ margin: 0 }}>{viewingInfluencer.name}</Title>
                <div style={{ marginTop: 4 }}>
                  <Tag color={platformColors[viewingInfluencer.platform]}>{platformText[viewingInfluencer.platform]}</Tag>
                  <Tag color={influencerStatusColors[viewingInfluencer.status]}>{influencerStatusText[viewingInfluencer.status]}</Tag>
                  <Tag>{viewingInfluencer.category}</Tag>
                </div>
              </div>
            </div>

            <Descriptions column={3} bordered size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="粉丝量">{viewingInfluencer.followers.toLocaleString()}</Descriptions.Item>
              <Descriptions.Item label="互动率"><Text type={viewingInfluencer.engagement_rate >= 5 ? 'success' : 'warning'} strong>{viewingInfluencer.engagement_rate}%</Text></Descriptions.Item>
              <Descriptions.Item label="评分"><Rate disabled value={viewingInfluencer.rating} style={{ fontSize: 14 }} /></Descriptions.Item>
              <Descriptions.Item label="地区">{viewingInfluencer.location}</Descriptions.Item>
              <Descriptions.Item label="联系邮箱" span={2}><Text copyable>{viewingInfluencer.contact_email}</Text></Descriptions.Item>
              <Descriptions.Item label="合作次数">{viewingInfluencer.total_collaborations}次</Descriptions.Item>
              <Descriptions.Item label="总花费">${viewingInfluencer.total_spend.toLocaleString()}</Descriptions.Item>
              <Descriptions.Item label="带来收入"><Text strong style={{ color: '#52c41a' }}>${viewingInfluencer.total_revenue.toLocaleString()}</Text></Descriptions.Item>
              <Descriptions.Item label="平均ROI" span={3}>{viewingInfluencer.avg_roi > 0 ? <Text type={viewingInfluencer.avg_roi >= 5 ? 'success' : 'warning'} strong>{viewingInfluencer.avg_roi}:1</Text> : '-'}</Descriptions.Item>
            </Descriptions>

            {viewingInfluencer.notes && (
              <Alert message="备注" description={viewingInfluencer.notes} type="info" showIcon />
            )}
          </div>
        )}
      </Modal>

      <Modal
        title={`联系达人 - ${viewingInfluencer?.name || ''}`}
        open={contactModalOpen}
        onCancel={() => setContactModalOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setContactModalOpen(false)}>取消</Button>,
          <Button key="send" type="primary" icon={<SendOutlined />} onClick={() => { message.success('合作邀请已发送'); setContactModalOpen(false) }}>发送邀请</Button>,
        ]}
        width={600}
      >
        <Form form={contactForm} layout="vertical">
          <Form.Item name="subject" label="邮件主题" rules={[{ required: true }]} initialValue={`合作邀请 | Nuotao Outdoor × ${viewingInfluencer?.name || ''}`}>
            <Input />
          </Form.Item>
          <Form.Item name="type" label="合作类型" rules={[{ required: true }]}>
            <Select options={[
              { value: 'product_review', label: '产品评测' },
              { value: 'sponsored_post', label: '赞助帖子' },
              { value: 'affiliate', label: '联盟营销' },
              { value: 'giveaway', label: '赠品活动' },
              { value: 'brand_ambassador', label: '品牌大使' },
            ]} />
          </Form.Item>
          <Form.Item name="budget" label="预算范围($)">
            <Select options={[
              { value: '100-500', label: '$100 - $500' },
              { value: '500-1000', label: '$500 - $1,000' },
              { value: '1000-3000', label: '$1,000 - $3,000' },
              { value: '3000+', label: '$3,000+' },
              { value: 'free_product', label: '免费产品+佣金' },
            ]} />
          </Form.Item>
          <Form.Item name="message" label="合作内容" rules={[{ required: true }]}>
            <Input.TextArea rows={5} placeholder="请描述合作内容、期望和条件..." />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
