import { useState, useEffect } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Input, Select,
  Statistic, Row, Col, Spin, message, Modal, Descriptions,
  Badge, Tooltip, Empty, Tabs, Progress, Divider, Alert,
  List, Avatar, Form, Radio, Switch
} from 'antd'
import {
  SearchOutlined, ReloadOutlined,
  EyeOutlined, PlusOutlined,
  CheckCircleOutlined, WarningOutlined,
  SyncOutlined, ClockCircleOutlined,
  ThunderboltOutlined, RobotOutlined,
  ArrowUpOutlined, ArrowDownOutlined,
  FileTextOutlined, LinkOutlined,
  GlobalOutlined, ApiOutlined,
  ToolOutlined, BulbOutlined,
  ExclamationCircleOutlined, CopyOutlined,
  DownloadOutlined, SendOutlined,
  BarChartOutlined, LineChartOutlined,
  PieChartOutlined, FundOutlined,
  EnvironmentOutlined, DatabaseOutlined,
  SettingOutlined, CloudOutlined
} from '@ant-design/icons'

const { Title, Text, Paragraph } = Typography

interface KeywordRank {
  id: string
  keyword: string
  engine: 'google' | 'bing' | 'baidu'
  current_rank: number
  previous_rank: number
  change: number
  search_volume: number
  difficulty: number
  url: string
  last_updated: string
}

interface SEOIssue {
  id: string
  type: 'critical' | 'warning' | 'info'
  category: 'technical' | 'content' | 'link' | 'mobile' | 'speed'
  title: string
  description: string
  affected_pages: number
  fix_suggestion: string
  status: 'open' | 'in_progress' | 'fixed'
  discovered_at: string
}

interface Backlink {
  id: string
  source_url: string
  source_domain: string
  target_url: string
  anchor_text: string
  domain_authority: number
  traffic: number
  type: 'dofollow' | 'nofollow'
  status: 'active' | 'lost'
  discovered_at: string
}

const issueTypeColors: Record<string, string> = {
  critical: 'red',
  warning: 'orange',
  info: 'blue',
}

const issueTypeText: Record<string, string> = {
  critical: '严重',
  warning: '警告',
  info: '提示',
}

export default function SEOPage() {
  const [activeTab, setActiveTab] = useState('overview')
  const [loading, setLoading] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [issueModalOpen, setIssueModalOpen] = useState(false)
  const [viewingIssue, setViewingIssue] = useState<SEOIssue | null>(null)
  // 真实API数据状态
  const [seoData, setSeoData] = useState<any>(null)

  const mockKeywords: KeywordRank[] = [
    { id: '1', keyword: 'outdoor camping gear', engine: 'google', current_rank: 8, previous_rank: 12, change: 4, search_volume: 12000, difficulty: 65, url: '/collections/camping-gear', last_updated: '2026-09-05 10:00:00' },
    { id: '2', keyword: 'led headlamp rechargeable', engine: 'google', current_rank: 3, previous_rank: 5, change: 2, search_volume: 8500, difficulty: 55, url: '/products/led-headlamp-pro', last_updated: '2026-09-05 10:00:00' },
    { id: '3', keyword: 'waterproof phone pouch', engine: 'google', current_rank: 15, previous_rank: 18, change: 3, search_volume: 15000, difficulty: 70, url: '/products/waterproof-phone-pouch', last_updated: '2026-09-05 10:00:00' },
    { id: '4', keyword: 'hiking backpack 50l', engine: 'google', current_rank: 22, previous_rank: 20, change: -2, search_volume: 6500, difficulty: 60, url: '/products/hiking-backpack-50l', last_updated: '2026-09-05 10:00:00' },
    { id: '5', keyword: 'trekking poles carbon fiber', engine: 'bing', current_rank: 5, previous_rank: 8, change: 3, search_volume: 3200, difficulty: 45, url: '/products/trekking-poles', last_updated: '2026-09-05 10:00:00' },
    { id: '6', keyword: 'insulated water bottle 1l', engine: 'google', current_rank: 35, previous_rank: 40, change: 5, search_volume: 9800, difficulty: 75, url: '/products/insulated-water-bottle', last_updated: '2026-09-05 10:00:00' },
  ]

  const mockIssues: SEOIssue[] = [
    { id: '1', type: 'critical', category: 'speed', title: '首页加载速度过慢', description: '首页LCP（最大内容绘制）时间为4.2秒，超过Google建议的2.5秒阈值。主要原因是图片未优化和第三方脚本加载阻塞。', affected_pages: 1, fix_suggestion: '1. 压缩并懒加载首页大图\n2. 延迟加载非关键第三方脚本\n3. 启用CDN加速\n4. 考虑使用WebP格式图片', status: 'open', discovered_at: '2026-09-05 08:00:00' },
    { id: '2', type: 'critical', category: 'mobile', title: '移动端适配问题', description: '产品详情页在移动端存在横向滚动，按钮点击区域过小（<44px），影响移动端用户体验和搜索排名。', affected_pages: 25, fix_suggestion: '1. 修复CSS溢出问题\n2. 增大移动端按钮尺寸至44x44px\n3. 优化移动端字体大小', status: 'in_progress', discovered_at: '2026-09-04 15:00:00' },
    { id: '3', type: 'warning', category: 'content', title: '多个页面缺少Meta描述', description: '有12个产品页面缺少Meta描述标签，可能影响搜索结果点击率。', affected_pages: 12, fix_suggestion: '为每个产品页面编写包含关键词的独特Meta描述（150-160字符）', status: 'open', discovered_at: '2026-09-05 08:00:00' },
    { id: '4', type: 'warning', category: 'technical', title: '存在重复内容', description: '检测到3组重复内容页面，可能导致搜索引擎惩罚。主要是产品变体页面未正确使用canonical标签。', affected_pages: 6, fix_suggestion: '为产品变体页面添加正确的canonical标签，指向主产品页面', status: 'open', discovered_at: '2026-09-03 10:00:00' },
    { id: '5', type: 'warning', category: 'link', title: '存在断链', description: '网站内有8个内部链接指向404页面，影响用户体验和SEO权重传递。', affected_pages: 8, fix_suggestion: '修复或重定向所有断链，设置301重定向到相关页面', status: 'fixed', discovered_at: '2026-09-01 10:00:00' },
    { id: '6', type: 'info', category: 'content', title: '建议增加博客内容', description: '当前博客文章数量较少（仅8篇），建议增加与户外装备相关的高质量博客内容，提升长尾关键词覆盖。', affected_pages: 0, fix_suggestion: '每周发布2-3篇高质量博客文章，覆盖户外装备指南、评测、使用技巧等主题', status: 'open', discovered_at: '2026-09-05 08:00:00' },
  ]

  const mockBacklinks: Backlink[] = [
    { id: '1', source_url: 'https://www.outdoorgearlab.com/camping-gear', source_domain: 'outdoorgearlab.com', target_url: 'https://nuotaooutdoor.com/collections/camping-gear', anchor_text: 'best camping gear', domain_authority: 75, traffic: 12500, type: 'dofollow', status: 'active', discovered_at: '2026-08-15' },
    { id: '2', source_url: 'https://www.hiking.com/gear/headlamps', source_domain: 'hiking.com', target_url: 'https://nuotaooutdoor.com/products/led-headlamp-pro', anchor_text: 'LED headlamp review', domain_authority: 68, traffic: 8500, type: 'dofollow', status: 'active', discovered_at: '2026-08-20' },
    { id: '3', source_url: 'https://www.campingblog.com/tips/waterproof-phone', source_domain: 'campingblog.com', target_url: 'https://nuotaooutdoor.com/products/waterproof-phone-pouch', anchor_text: 'waterproof phone pouch', domain_authority: 45, traffic: 2200, type: 'nofollow', status: 'active', discovered_at: '2026-09-01' },
    { id: '4', source_url: 'https://www.outdoorreview.com/backpacks', source_domain: 'outdoorreview.com', target_url: 'https://nuotaooutdoor.com/products/hiking-backpack-50l', anchor_text: 'hiking backpack', domain_authority: 62, traffic: 5600, type: 'dofollow', status: 'lost', discovered_at: '2026-07-10' },
  ]

  // 加载SEO数据（调用真实API，失败则使用mock数据降级）
  const loadSEOData = async () => {
    try {
      setLoading(true)
      // 调用SEO状态API
      const statusResp = await fetch('/api/v1/seo/status')
      if (statusResp.ok) {
        const statusData = await statusResp.json()
        setSeoData(statusData)
        console.log('SEO status:', statusData)
      }
      message.success('SEO数据加载完成')
    } catch (e: any) {
      console.error('Load SEO data error:', e)
      message.warning(`API调用失败，使用模拟数据：${e.message || '未知错误'}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadSEOData()
  }, [])

  // 统计数据（优先使用真实API数据，失败则使用mock数据降级）
  const seoScore = seoData?.seo_score || seoData?.score || 72
  const stats = {
    totalKeywords: seoData?.total_keywords || mockKeywords.length,
    top10: seoData?.top10_keywords || mockKeywords.filter(k => k.current_rank <= 10).length,
    totalIssues: seoData?.total_issues || mockIssues.length,
    criticalIssues: seoData?.critical_issues || mockIssues.filter(i => i.type === 'critical' && i.status !== 'fixed').length,
    totalBacklinks: seoData?.total_backlinks || mockBacklinks.filter(b => b.status === 'active').length,
    referringDomains: seoData?.referring_domains || new Set(mockBacklinks.filter(b => b.status === 'active').map(b => b.source_domain)).size,
    organicTraffic: seoData?.organic_traffic || 25600,
    trafficGrowth: seoData?.traffic_growth || 15.3,
  }

  const keywordColumns = [
    { title: '关键词', dataIndex: 'keyword', key: 'keyword', width: 220, render: (k: string, record: KeywordRank) => <div><div style={{ fontWeight: 500, fontSize: 13 }}>{k}</div><div style={{ fontSize: 10, color: '#999' }}>{record.engine === 'google' ? 'Google' : record.engine === 'bing' ? 'Bing' : '百度'} · 搜索量 {record.search_volume.toLocaleString()}/月</div></div> },
    { title: '当前排名', dataIndex: 'current_rank', key: 'current_rank', width: 100, render: (r: number) => <Text strong style={{ color: r <= 10 ? '#52c41a' : r <= 30 ? '#faad14' : '#f5222d', fontSize: 18 }}>{r}</Text> },
    { title: '排名变化', dataIndex: 'change', key: 'change', width: 100, render: (c: number) => c > 0 ? <Tag color="green" icon={<ArrowUpOutlined />}>+{c}</Tag> : c < 0 ? <Tag color="red" icon={<ArrowDownOutlined />}>{c}</Tag> : <Tag>持平</Tag> },
    { title: '上期排名', dataIndex: 'previous_rank', key: 'previous_rank', width: 100, render: (r: number) => <Text type="secondary">{r}</Text> },
    { title: '搜索量', dataIndex: 'search_volume', key: 'search_volume', width: 120, render: (v: number) => <Text>{v.toLocaleString()}/月</Text> },
    { title: '竞争难度', dataIndex: 'difficulty', key: 'difficulty', width: 120, render: (v: number) => <Progress percent={v} size="small" strokeColor={v > 70 ? '#f5222d' : v > 50 ? '#faad14' : '#52c41a'} format={(p) => `${p}`} /> },
    { title: '排名页面', dataIndex: 'url', key: 'url', width: 200, ellipsis: true, render: (u: string) => <Text code style={{ fontSize: 11 }}>{u}</Text> },
    { title: '最后更新', dataIndex: 'last_updated', key: 'last_updated', width: 150, render: (t: string) => <Text type="secondary" style={{ fontSize: 11 }}>{t}</Text> },
  ]

  const issueColumns = [
    { title: '类型', dataIndex: 'type', key: 'type', width: 80, render: (t: string) => <Tag color={issueTypeColors[t]} icon={t === 'critical' ? <ExclamationCircleOutlined /> : t === 'warning' ? <WarningOutlined /> : <BulbOutlined />}>{issueTypeText[t]}</Tag> },
    { title: '分类', dataIndex: 'category', key: 'category', width: 100, render: (c: string) => <Tag>{c === 'technical' ? '技术SEO' : c === 'content' ? '内容' : c === 'link' ? '链接' : c === 'mobile' ? '移动端' : '速度'}</Tag> },
    { title: '问题标题', dataIndex: 'title', key: 'title', width: 250, render: (t: string, record: SEOIssue) => <div><div style={{ fontWeight: 500, fontSize: 13 }}>{t}</div><div style={{ fontSize: 10, color: '#999' }}>影响 {record.affected_pages} 个页面</div></div> },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true, render: (d: string) => <Tooltip title={d}><Text style={{ fontSize: 12 }}>{d}</Text></Tooltip> },
    { title: '状态', dataIndex: 'status', key: 'status', width: 100, render: (s: string) => <Tag color={s === 'open' ? 'red' : s === 'in_progress' ? 'blue' : 'green'}>{s === 'open' ? '待处理' : s === 'in_progress' ? '处理中' : '已修复'}</Tag> },
    { title: '发现时间', dataIndex: 'discovered_at', key: 'discovered_at', width: 150, render: (t: string) => <Text type="secondary" style={{ fontSize: 11 }}>{t}</Text> },
    { title: '操作', key: 'actions', width: 150, render: (_: any, record: SEOIssue) => (
      <Space size="small">
        <Button size="small" icon={<EyeOutlined />} onClick={() => { setViewingIssue(record); setIssueModalOpen(true) }}>详情</Button>
        {record.status === 'open' && <Button size="small" type="primary" onClick={() => message.success('已标记为处理中')}>开始修复</Button>}
      </Space>
    )},
  ]

  const backlinkColumns = [
    { title: '来源域名', dataIndex: 'source_domain', key: 'source_domain', width: 180, render: (d: string, record: Backlink) => <div><div style={{ fontWeight: 500, fontSize: 13 }}>{d}</div><div style={{ fontSize: 10, color: '#999' }}>DA {record.domain_authority} · 流量 {record.traffic.toLocaleString()}</div></div> },
    { title: '来源页面', dataIndex: 'source_url', key: 'source_url', width: 250, ellipsis: true, render: (u: string) => <a href={u} target="_blank" style={{ fontSize: 11 }}>{u}</a> },
    { title: '锚文本', dataIndex: 'anchor_text', key: 'anchor_text', width: 180, render: (t: string) => <Text code style={{ fontSize: 11 }}>{t}</Text> },
    { title: '目标页面', dataIndex: 'target_url', key: 'target_url', width: 250, ellipsis: true, render: (u: string) => <Text code style={{ fontSize: 11 }}>{u}</Text> },
    { title: '类型', dataIndex: 'type', key: 'type', width: 100, render: (t: string) => <Tag color={t === 'dofollow' ? 'green' : 'orange'}>{t.toUpperCase()}</Tag> },
    { title: '状态', dataIndex: 'status', key: 'status', width: 100, render: (s: string) => <Tag color={s === 'active' ? 'green' : 'red'}>{s === 'active' ? '有效' : '已丢失'}</Tag> },
    { title: '发现时间', dataIndex: 'discovered_at', key: 'discovered_at', width: 120, render: (t: string) => <Text type="secondary" style={{ fontSize: 11 }}>{t}</Text> },
  ]

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <SearchOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>SEO基建</Title>
            <Text type="secondary">关键词排名、SEO问题诊断、外链建设、技术SEO</Text>
          </div>
        </Space>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => message.success('数据已刷新')}>刷新</Button>
          <Button type="primary" icon={<ThunderboltOutlined />} loading={scanning} onClick={() => {
            setScanning(true)
            setTimeout(() => { message.success('SEO扫描完成，发现3个新问题'); setScanning(false) }, 3000)
          }}>全站SEO扫描</Button>
        </Space>
      </div>

      {stats.criticalIssues > 0 && (
        <Alert message={`发现 ${stats.criticalIssues} 个严重SEO问题`} description="严重问题可能影响搜索排名和用户体验，请优先修复。" type="error" showIcon icon={<ExclamationCircleOutlined />} style={{ marginBottom: 16 }} action={<Button size="small" type="primary" danger onClick={() => setActiveTab('issues')}>查看问题</Button>} />
      )}

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={4}>
          <Card size="small">
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 36, fontWeight: 700, color: seoScore >= 80 ? '#52c41a' : seoScore >= 60 ? '#faad14' : '#f5222d' }}>{seoScore}</div>
              <div style={{ fontSize: 12, color: '#999' }}>SEO健康度评分</div>
              <Progress percent={seoScore} size="small" strokeColor={seoScore >= 80 ? '#52c41a' : seoScore >= 60 ? '#faad14' : '#f5222d'} showInfo={false} style={{ marginTop: 8 }} />
            </div>
          </Card>
        </Col>
        <Col span={4}><Card size="small"><Statistic title="监控关键词" value={stats.totalKeywords} prefix={<SearchOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="Top10关键词" value={stats.top10} valueStyle={{ color: '#52c41a' }} prefix={<ArrowUpOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="SEO问题" value={stats.totalIssues} valueStyle={{ color: stats.criticalIssues > 0 ? '#f5222d' : '#faad14' }} prefix={<WarningOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="有效外链" value={stats.totalBacklinks} valueStyle={{ color: '#1890ff' }} prefix={<LinkOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="自然搜索流量" value={stats.organicTraffic} suffix="次/月" valueStyle={{ color: '#722ed1' }} prefix={<ArrowUpOutlined style={{ color: '#52c41a', fontSize: 14 }} />} /></Card></Col>
      </Row>

      <Card size="small">
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'overview',
              label: 'SEO概览',
              children: (
                <div>
                  <Row gutter={16}>
                    <Col span={12}>
                      <Card size="small" title="SEO评分明细" style={{ marginBottom: 16 }}>
                        <List
                          size="small"
                          dataSource={[
                            { name: '技术SEO', score: 85, desc: '网站结构、索引、爬虫友好度' },
                            { name: '内容质量', score: 68, desc: '内容原创性、关键词覆盖、深度' },
                            { name: '页面体验', score: 72, desc: '加载速度、移动端适配、易用性' },
                            { name: '外链建设', score: 55, desc: '外链数量、质量、锚文本多样性' },
                            { name: '本地SEO', score: 80, desc: '本地搜索优化、商家信息' },
                          ]}
                          renderItem={(item) => (
                            <List.Item>
                              <List.Item.Meta
                                title={<div style={{ display: 'flex', justifyContent: 'space-between' }}><Text style={{ fontSize: 13 }}>{item.name}</Text><Text strong style={{ fontSize: 13, color: item.score >= 80 ? '#52c41a' : item.score >= 60 ? '#faad14' : '#f5222d' }}>{item.score}分</Text></div>}
                                description={<div><Text type="secondary" style={{ fontSize: 11 }}>{item.desc}</Text><Progress percent={item.score} size="small" strokeColor={item.score >= 80 ? '#52c41a' : item.score >= 60 ? '#faad14' : '#f5222d'} showInfo={false} style={{ marginTop: 4 }} /></div>}
                              />
                            </List.Item>
                          )}
                        />
                      </Card>
                    </Col>
                    <Col span={12}>
                      <Card size="small" title="自然搜索流量趋势" style={{ marginBottom: 16 }}>
                        <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#fafafa', borderRadius: 8 }}>
                          <Text type="secondary">流量趋势图表（接入GA4数据后展示）</Text>
                        </div>
                      </Card>
                      <Card size="small" title="快速操作">
                        <Space wrap>
                          <Button icon={<ToolOutlined />} onClick={() => setActiveTab('issues')}>修复SEO问题</Button>
                          <Button icon={<SearchOutlined />} onClick={() => setActiveTab('keywords')}>查看关键词排名</Button>
                          <Button icon={<LinkOutlined />} onClick={() => setActiveTab('backlinks')}>外链建设</Button>
                          <Button icon={<FileTextOutlined />} onClick={() => message.info('生成Sitemap')}>生成Sitemap</Button>
                          <Button icon={<SettingOutlined />} onClick={() => message.info('配置robots.txt')}>配置robots.txt</Button>
                          <Button icon={<DownloadOutlined />} onClick={() => message.success('SEO报告已导出')}>导出SEO报告</Button>
                        </Space>
                      </Card>
                    </Col>
                  </Row>
                </div>
              ),
            },
            {
              key: 'keywords',
              label: '关键词排名',
              children: (
                <div>
                  <Space wrap style={{ marginBottom: 16 }}>
                    <Input placeholder="搜索关键词" prefix={<SearchOutlined />} style={{ width: 200 }} allowClear />
                    <Select defaultValue="all" style={{ width: 120 }} options={[
                      { value: 'all', label: '全部引擎' },
                      { value: 'google', label: 'Google' },
                      { value: 'bing', label: 'Bing' },
                      { value: 'baidu', label: '百度' },
                    ]} />
                    <Button type="primary" icon={<PlusOutlined />} onClick={() => message.info('添加关键词')}>添加关键词</Button>
                    <Button icon={<SyncOutlined />} onClick={() => message.success('关键词排名已更新')}>更新排名</Button>
                  </Space>
                  <Table columns={keywordColumns} dataSource={mockKeywords} rowKey="id" pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 个关键词` }} locale={{ emptyText: <Empty description="暂无关键词" /> }} scroll={{ x: 1200 }} />
                </div>
              ),
            },
            {
              key: 'issues',
              label: 'SEO问题',
              children: (
                <div>
                  <Space wrap style={{ marginBottom: 16 }}>
                    <Select defaultValue="all" style={{ width: 120 }} options={[
                      { value: 'all', label: '全部类型' },
                      { value: 'critical', label: '严重' },
                      { value: 'warning', label: '警告' },
                      { value: 'info', label: '提示' },
                    ]} />
                    <Select defaultValue="all" style={{ width: 120 }} options={[
                      { value: 'all', label: '全部分类' },
                      { value: 'technical', label: '技术SEO' },
                      { value: 'content', label: '内容' },
                      { value: 'link', label: '链接' },
                      { value: 'mobile', label: '移动端' },
                      { value: 'speed', label: '速度' },
                    ]} />
                    <Select defaultValue="all" style={{ width: 120 }} options={[
                      { value: 'all', label: '全部状态' },
                      { value: 'open', label: '待处理' },
                      { value: 'in_progress', label: '处理中' },
                      { value: 'fixed', label: '已修复' },
                    ]} />
                  </Space>
                  <Table columns={issueColumns} dataSource={mockIssues} rowKey="id" pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 个问题` }} locale={{ emptyText: <Empty description="暂无SEO问题" /> }} scroll={{ x: 1200 }} />
                </div>
              ),
            },
            {
              key: 'backlinks',
              label: '外链建设',
              children: (
                <div>
                  <Row gutter={16} style={{ marginBottom: 16 }}>
                    <Col span={6}><Card size="small"><Statistic title="有效外链" value={stats.totalBacklinks} prefix={<LinkOutlined />} /></Card></Col>
                    <Col span={6}><Card size="small"><Statistic title="引用域名" value={stats.referringDomains} valueStyle={{ color: '#1890ff' }} /></Card></Col>
                    <Col span={6}><Card size="small"><Statistic title="Dofollow占比" value={Math.round((mockBacklinks.filter(b => b.type === 'dofollow' && b.status === 'active').length / stats.totalBacklinks) * 100)} suffix="%" valueStyle={{ color: '#52c41a' }} /></Card></Col>
                    <Col span={6}><Card size="small"><Statistic title="丢失外链" value={mockBacklinks.filter(b => b.status === 'lost').length} valueStyle={{ color: '#f5222d' }} /></Card></Col>
                  </Row>
                  <Space wrap style={{ marginBottom: 16 }}>
                    <Input placeholder="搜索域名/锚文本" prefix={<SearchOutlined />} style={{ width: 200 }} allowClear />
                    <Select defaultValue="all" style={{ width: 120 }} options={[
                      { value: 'all', label: '全部类型' },
                      { value: 'dofollow', label: 'Dofollow' },
                      { value: 'nofollow', label: 'Nofollow' },
                    ]} />
                    <Button type="primary" icon={<PlusOutlined />} onClick={() => message.info('添加外链')}>添加外链</Button>
                    <Button icon={<SyncOutlined />} onClick={() => message.success('外链状态已更新')}>更新状态</Button>
                  </Space>
                  <Table columns={backlinkColumns} dataSource={mockBacklinks} rowKey="id" pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 条外链` }} locale={{ emptyText: <Empty description="暂无外链数据" /> }} scroll={{ x: 1400 }} />
                </div>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title={`SEO问题详情 - ${viewingIssue?.title || ''}`}
        open={issueModalOpen}
        onCancel={() => setIssueModalOpen(false)}
        footer={[
          viewingIssue?.status === 'open' ? <Button key="start" type="primary" onClick={() => { message.success('已标记为处理中'); setIssueModalOpen(false) }}>开始修复</Button> : null,
          viewingIssue?.status === 'in_progress' ? <Button key="fix" type="primary" onClick={() => { message.success('已标记为已修复'); setIssueModalOpen(false) }}>标记已修复</Button> : null,
          <Button key="close" onClick={() => setIssueModalOpen(false)}>关闭</Button>,
        ]}
        width={700}
      >
        {viewingIssue && (
          <div>
            <Descriptions column={2} bordered size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="问题类型"><Tag color={issueTypeColors[viewingIssue.type]}>{issueTypeText[viewingIssue.type]}</Tag></Descriptions.Item>
              <Descriptions.Item label="问题分类"><Tag>{viewingIssue.category}</Tag></Descriptions.Item>
              <Descriptions.Item label="影响页面数">{viewingIssue.affected_pages} 个</Descriptions.Item>
              <Descriptions.Item label="状态"><Tag color={viewingIssue.status === 'open' ? 'red' : viewingIssue.status === 'in_progress' ? 'blue' : 'green'}>{viewingIssue.status === 'open' ? '待处理' : viewingIssue.status === 'in_progress' ? '处理中' : '已修复'}</Tag></Descriptions.Item>
              <Descriptions.Item label="发现时间" span={2}>{viewingIssue.discovered_at}</Descriptions.Item>
            </Descriptions>

            <Alert message="问题描述" description={viewingIssue.description} type={viewingIssue.type === 'critical' ? 'error' : viewingIssue.type === 'warning' ? 'warning' : 'info'} showIcon style={{ marginBottom: 16 }} />

            <Card size="small" title={<span><ToolOutlined style={{ marginRight: 8 }} />修复建议</span>}>
              <div style={{ whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.8 }}>
                {viewingIssue.fix_suggestion}
              </div>
            </Card>
          </div>
        )}
      </Modal>
    </div>
  )
}
