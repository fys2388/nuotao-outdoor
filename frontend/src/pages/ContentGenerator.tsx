import { useState } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Input, Select,
  Statistic, Row, Col, Spin, message, Modal, Descriptions,
  Badge, Tooltip, Empty, Tabs, Progress, Divider, Alert,
  List, Avatar, Form, Radio, Slider
} from 'antd'
import {
  FileTextOutlined, ReloadOutlined, SearchOutlined,
  EyeOutlined, PlusOutlined, DownloadOutlined,
  CheckCircleOutlined, EditOutlined,
  SyncOutlined, ClockCircleOutlined,
  ThunderboltOutlined, RobotOutlined,
  ArrowUpOutlined, ArrowDownOutlined,
  ShoppingCartOutlined, UserOutlined, GiftOutlined,
  CustomerServiceOutlined, FundOutlined,
  SendOutlined,
  CalendarOutlined, BulbOutlined, ExclamationCircleOutlined,
  ApiOutlined, CloudOutlined, InboxOutlined,
  ExportOutlined, ImportOutlined, EnvironmentOutlined,
  CopyOutlined, DeleteOutlined, SaveOutlined,
  BookOutlined, MailOutlined, ShareAltOutlined,
  SoundOutlined, PictureOutlined
} from '@ant-design/icons'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

interface ContentItem {
  id: string
  title: string
  type: 'blog' | 'product' | 'social' | 'email' | 'ad'
  status: 'draft' | 'review' | 'published' | 'archived'
  content: string
  keywords: string[]
  word_count: number
  language: 'zh' | 'en'
  created_at: string
  updated_at: string
  views?: number
  conversions?: number
}

const typeColors: Record<string, string> = {
  blog: 'blue',
  product: 'green',
  social: 'purple',
  email: 'orange',
  ad: 'red',
}

const typeText: Record<string, string> = {
  blog: '博客文章',
  product: '产品描述',
  social: '社交媒体',
  email: '邮件营销',
  ad: '广告文案',
}

const statusColors: Record<string, string> = {
  draft: 'default',
  review: 'blue',
  published: 'green',
  archived: 'orange',
}

const statusText: Record<string, string> = {
  draft: '草稿',
  review: '待审核',
  published: '已发布',
  archived: '已归档',
}

export default function ContentGeneratorPage() {
  const [activeTab, setActiveTab] = useState('generate')
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [previewModalOpen, setPreviewModalOpen] = useState(false)
  const [viewingContent, setViewingContent] = useState<ContentItem | null>(null)
  const [contentType, setContentType] = useState('blog')
  const [language, setLanguage] = useState('en')
  const [tone, setTone] = useState('professional')
  const [wordCount, setWordCount] = useState(500)
  const [topic, setTopic] = useState('')
  const [keywords, setKeywords] = useState('')
  const [generatedContent, setGeneratedContent] = useState('')
  const [generatedTitle, setGeneratedTitle] = useState('')

  const mockContents: ContentItem[] = [
    { id: '1', title: '10 Best Outdoor Camping Gear for 2026', type: 'blog', status: 'published', content: 'Discover the top 10 outdoor camping gear essentials for 2026...', keywords: ['camping', 'outdoor gear', '2026'], word_count: 1250, language: 'en', created_at: '2026-09-05 10:00:00', updated_at: '2026-09-05 10:30:00', views: 1250, conversions: 45 },
    { id: '2', title: 'LED Headlamp Pro - Ultimate Outdoor Lighting Solution', type: 'product', status: 'published', content: 'Experience unmatched brightness with our LED Headlamp Pro...', keywords: ['headlamp', 'LED', 'outdoor lighting'], word_count: 350, language: 'en', created_at: '2026-09-04 15:00:00', updated_at: '2026-09-04 15:30:00', views: 890, conversions: 120 },
    { id: '3', title: '秋季户外装备推荐：5件必备单品', type: 'social', status: 'draft', content: '秋天是户外活动的最佳季节，以下5件装备让你的秋季户外之旅更加精彩...', keywords: ['秋季', '户外装备', '推荐'], word_count: 280, language: 'zh', created_at: '2026-09-05 09:00:00', updated_at: '2026-09-05 09:15:00' },
    { id: '4', title: 'Welcome to Nuotao Outdoor - Your Adventure Starts Here', type: 'email', status: 'review', content: 'Dear Customer, Welcome to Nuotao Outdoor...', keywords: ['welcome', 'new customer', 'discount'], word_count: 420, language: 'en', created_at: '2026-09-03 14:00:00', updated_at: '2026-09-03 14:30:00' },
    { id: '5', title: 'Flash Sale - 50% Off All Outdoor Gear', type: 'ad', status: 'published', content: 'Limited time offer! Get 50% off all outdoor gear...', keywords: ['sale', 'discount', 'flash sale'], word_count: 150, language: 'en', created_at: '2026-09-02 10:00:00', updated_at: '2026-09-02 10:15:00', views: 5600, conversions: 280 },
    { id: '6', title: 'How to Choose the Right Trekking Poles', type: 'blog', status: 'draft', content: 'Trekking poles are essential for any hiker...', keywords: ['trekking poles', 'hiking', 'buying guide'], word_count: 980, language: 'en', created_at: '2026-09-01 11:00:00', updated_at: '2026-09-01 11:30:00' },
  ]

  const stats = {
    total: mockContents.length,
    published: mockContents.filter(c => c.status === 'published').length,
    draft: mockContents.filter(c => c.status === 'draft').length,
    review: mockContents.filter(c => c.status === 'review').length,
    totalViews: mockContents.reduce((s, c) => s + (c.views || 0), 0),
    totalConversions: mockContents.reduce((s, c) => s + (c.conversions || 0), 0),
  }

  const contentColumns = [
    { title: '标题', dataIndex: 'title', key: 'title', width: 250, ellipsis: true, render: (t: string, record: ContentItem) => <div><div style={{ fontWeight: 500, fontSize: 13 }}>{t}</div><div style={{ fontSize: 10, color: '#999' }}>{record.type === 'blog' ? <BookOutlined /> : record.type === 'product' ? <ShoppingCartOutlined /> : record.type === 'social' ? <ShareAltOutlined /> : record.type === 'email' ? <MailOutlined /> : <SoundOutlined />} {typeText[record.type]} · {record.word_count}字 · {record.language === 'zh' ? '中文' : '英文'}</div></div> },
    { title: '类型', dataIndex: 'type', key: 'type', width: 100, render: (t: string) => <Tag color={typeColors[t]}>{typeText[t]}</Tag> },
    { title: '状态', dataIndex: 'status', key: 'status', width: 100, render: (s: string) => <Tag color={statusColors[s]}>{statusText[s]}</Tag> },
    { title: '关键词', dataIndex: 'keywords', key: 'keywords', width: 200, render: (k: string[]) => <Space wrap>{k.map((kw, idx) => <Tag key={idx} color="blue">{kw}</Tag>)}</Space> },
    { title: '字数', dataIndex: 'word_count', key: 'word_count', width: 80, render: (v: number) => <Text>{v}</Text> },
    { title: '浏览量', dataIndex: 'views', key: 'views', width: 100, render: (v?: number) => v ? <Text>{v.toLocaleString()}</Text> : '-' },
    { title: '转化数', dataIndex: 'conversions', key: 'conversions', width: 100, render: (v?: number) => v ? <Text type="success">{v}</Text> : '-' },
    { title: '更新时间', dataIndex: 'updated_at', key: 'updated_at', width: 150, render: (t: string) => <Text type="secondary" style={{ fontSize: 11 }}>{t}</Text> },
    { title: '操作', key: 'actions', width: 200, render: (_: any, record: ContentItem) => (
      <Space size="small">
        <Button size="small" icon={<EyeOutlined />} onClick={() => { setViewingContent(record); setPreviewModalOpen(true) }}>预览</Button>
        <Button size="small" icon={<EditOutlined />} onClick={() => message.info('编辑内容')}>编辑</Button>
        {record.status === 'draft' && <Button size="small" type="primary" icon={<SendOutlined />} onClick={() => message.success('已提交审核')}>提交审核</Button>}
        {record.status === 'review' && <Button size="small" type="primary" icon={<CheckCircleOutlined />} onClick={() => message.success('已发布')}>发布</Button>}
      </Space>
    )},
  ]

  const handleGenerate = async () => {
    if (!topic) {
      message.warning('请输入内容主题')
      return
    }
    setGenerating(true)
    try {
      const resp = await fetch('/api/v1/content/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topic: topic,
          content_type: contentType,
          tone: tone,
          language: language,
          keywords: keywords ? keywords.split(',').map(k => k.trim()) : [],
        }),
      })
      const data = await resp.json()
      if (data.success && data.data) {
        setGeneratedTitle(data.data.title || `${topic} - ${typeText[contentType]} Guide`)
        setGeneratedContent(data.data.content || data.data.generated_content || '')
        message.success('内容生成完成')
      } else {
        // API调用失败，使用模拟内容作为降级
        setGeneratedTitle(`${topic} - ${typeText[contentType]} Guide`)
        setGeneratedContent(`# ${topic}\n\n## Introduction\n\nThis is an AI-generated ${typeText[contentType]} about "${topic}".\n\n## Key Points\n\n1. First important point about ${topic}\n2. Second important point with detailed explanation\n3. Third point with practical examples\n\n## Conclusion\n\nIn summary, ${topic} is an important topic.`)
        message.warning('API调用失败，已使用模拟内容')
      }
    } catch (e: any) {
      console.error('Generate content error:', e)
      // 网络错误，使用模拟内容作为降级
      setGeneratedTitle(`${topic} - ${typeText[contentType]} Guide`)
      setGeneratedContent(`# ${topic}\n\n## Introduction\n\nThis is an AI-generated ${typeText[contentType]} about "${topic}".\n\n## Key Points\n\n1. First important point about ${topic}\n2. Second important point with detailed explanation\n\n## Conclusion\n\nIn summary, ${topic} is an important topic.`)
      message.warning(`网络错误，已使用模拟内容：${e.message || '未知错误'}`)
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <RobotOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>AI内容生成</Title>
            <Text type="secondary">博客文章、产品描述、社交媒体、邮件营销、广告文案</Text>
          </div>
        </Space>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => message.success('数据已刷新')}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setActiveTab('generate')}>新建内容</Button>
        </Space>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={4}><Card size="small"><Statistic title="内容总数" value={stats.total} prefix={<FileTextOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="已发布" value={stats.published} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="草稿" value={stats.draft} valueStyle={{ color: '#faad14' }} prefix={<EditOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="待审核" value={stats.review} valueStyle={{ color: '#1890ff' }} prefix={<ClockCircleOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="总浏览量" value={stats.totalViews} valueStyle={{ color: '#722ed1' }} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="总转化数" value={stats.totalConversions} valueStyle={{ color: '#52c41a' }} /></Card></Col>
      </Row>

      <Card size="small">
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'generate',
              label: 'AI生成',
              children: (
                <div>
                  <Row gutter={24}>
                    <Col span={10}>
                      <Card size="small" title="生成设置" style={{ marginBottom: 16 }}>
                        <Form layout="vertical">
                          <Form.Item label="内容类型" required>
                            <Radio.Group value={contentType} onChange={(e) => setContentType(e.target.value)}>
                              <Space direction="vertical">
                                <Radio value="blog"><BookOutlined /> 博客文章</Radio>
                                <Radio value="product"><ShoppingCartOutlined /> 产品描述</Radio>
                                <Radio value="social"><ShareAltOutlined /> 社交媒体帖子</Radio>
                                <Radio value="email"><MailOutlined /> 邮件营销</Radio>
                                <Radio value="ad"><SoundOutlined /> 广告文案</Radio>
                              </Space>
                            </Radio.Group>
                          </Form.Item>
                          <Form.Item label="语言" required>
                            <Radio.Group value={language} onChange={(e) => setLanguage(e.target.value)}>
                              <Radio value="en">英文</Radio>
                              <Radio value="zh">中文</Radio>
                            </Radio.Group>
                          </Form.Item>
                          <Form.Item label="语气风格" required>
                            <Select value={tone} onChange={setTone} options={[
                              { value: 'professional', label: '专业正式' },
                              { value: 'friendly', label: '友好亲切' },
                              { value: 'casual', label: '轻松随意' },
                              { value: 'persuasive', label: '说服性' },
                              { value: 'humorous', label: '幽默风趣' },
                            ]} />
                          </Form.Item>
                          <Form.Item label={`目标字数: ${wordCount}字`}>
                            <Slider min={100} max={2000} step={50} value={wordCount} onChange={setWordCount} marks={{ 100: '100', 500: '500', 1000: '1000', 1500: '1500', 2000: '2000' }} />
                          </Form.Item>
                          <Form.Item label="内容主题" required>
                            <Input placeholder="请输入内容主题，如：户外露营装备推荐" value={topic} onChange={(e) => setTopic(e.target.value)} />
                          </Form.Item>
                          <Form.Item label="关键词（逗号分隔）">
                            <Input placeholder="如：camping, outdoor gear, 2026" value={keywords} onChange={(e) => setKeywords(e.target.value)} />
                          </Form.Item>
                          <Button type="primary" icon={<ThunderboltOutlined />} loading={generating} onClick={handleGenerate} block size="large">
                            AI生成内容
                          </Button>
                        </Form>
                      </Card>
                    </Col>
                    <Col span={14}>
                      <Card size="small" title="生成结果" extra={generatedContent ? <Space><Button size="small" icon={<CopyOutlined />} onClick={() => { navigator.clipboard.writeText(generatedContent); message.success('已复制到剪贴板') }}>复制</Button><Button size="small" icon={<SaveOutlined />} onClick={() => message.success('已保存到内容库')}>保存</Button><Button size="small" type="primary" icon={<SendOutlined />} onClick={() => message.success('已提交审核')}>提交审核</Button></Space> : null}>
                        {generating ? (
                          <div style={{ textAlign: 'center', padding: '60px 0' }}>
                            <Spin size="large" />
                            <div style={{ marginTop: 16, color: '#999' }}>AI正在生成内容，请稍候...</div>
                          </div>
                        ) : generatedContent ? (
                          <div>
                            <Title level={4} style={{ marginBottom: 16 }}>{generatedTitle}</Title>
                            <div style={{ whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.8, maxHeight: 500, overflow: 'auto' }}>
                              {generatedContent}
                            </div>
                          </div>
                        ) : (
                          <div style={{ textAlign: 'center', padding: '60px 0' }}>
                            <RobotOutlined style={{ fontSize: 48, color: '#ddd' }} />
                            <div style={{ marginTop: 16, color: '#999' }}>填写左侧设置，点击"AI生成内容"开始生成</div>
                          </div>
                        )}
                      </Card>
                    </Col>
                  </Row>
                </div>
              ),
            },
            {
              key: 'library',
              label: '内容库',
              children: (
                <div>
                  <Space wrap style={{ marginBottom: 16 }}>
                    <Input placeholder="搜索标题/关键词" prefix={<SearchOutlined />} style={{ width: 200 }} allowClear />
                    <Select defaultValue="all" style={{ width: 120 }} options={[
                      { value: 'all', label: '全部类型' },
                      { value: 'blog', label: '博客文章' },
                      { value: 'product', label: '产品描述' },
                      { value: 'social', label: '社交媒体' },
                      { value: 'email', label: '邮件营销' },
                      { value: 'ad', label: '广告文案' },
                    ]} />
                    <Select defaultValue="all" style={{ width: 120 }} options={[
                      { value: 'all', label: '全部状态' },
                      { value: 'draft', label: '草稿' },
                      { value: 'review', label: '待审核' },
                      { value: 'published', label: '已发布' },
                      { value: 'archived', label: '已归档' },
                    ]} />
                    <Button type="primary" icon={<DownloadOutlined />} onClick={() => message.success('内容已导出')}>导出</Button>
                  </Space>
                  <Table columns={contentColumns} dataSource={mockContents} rowKey="id" pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 篇内容` }} locale={{ emptyText: <Empty description="暂无内容" /> }} scroll={{ x: 1400 }} />
                </div>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title={`内容预览 - ${viewingContent?.title || ''}`}
        open={previewModalOpen}
        onCancel={() => setPreviewModalOpen(false)}
        footer={[
          <Button key="copy" icon={<CopyOutlined />} onClick={() => message.success('已复制')}>复制</Button>,
          <Button key="edit" icon={<EditOutlined />} onClick={() => message.info('编辑内容')}>编辑</Button>,
          <Button key="close" onClick={() => setPreviewModalOpen(false)}>关闭</Button>,
        ]}
        width={800}
      >
        {viewingContent && (
          <div>
            <Descriptions column={3} size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="类型"><Tag color={typeColors[viewingContent.type]}>{typeText[viewingContent.type]}</Tag></Descriptions.Item>
              <Descriptions.Item label="状态"><Tag color={statusColors[viewingContent.status]}>{statusText[viewingContent.status]}</Tag></Descriptions.Item>
              <Descriptions.Item label="语言">{viewingContent.language === 'zh' ? '中文' : '英文'}</Descriptions.Item>
              <Descriptions.Item label="字数">{viewingContent.word_count}字</Descriptions.Item>
              <Descriptions.Item label="浏览量">{viewingContent.views?.toLocaleString() || '-'}</Descriptions.Item>
              <Descriptions.Item label="转化数">{viewingContent.conversions || '-'}</Descriptions.Item>
            </Descriptions>
            <Divider style={{ margin: '12px 0' }} />
            <Title level={4} style={{ marginBottom: 16 }}>{viewingContent.title}</Title>
            <div style={{ whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.8, maxHeight: 400, overflow: 'auto' }}>
              {viewingContent.content}
            </div>
            <Divider style={{ margin: '12px 0' }} />
            <div>
              <Text strong>关键词：</Text>
              <Space wrap style={{ marginLeft: 8 }}>
                {viewingContent.keywords.map((kw, idx) => <Tag key={idx} color="blue">{kw}</Tag>)}
              </Space>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
