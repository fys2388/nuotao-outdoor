import { useState, useEffect } from 'react'
import {
  Card, Form, Input, Button, Space, Typography, Steps, Tag, Alert,
  Row, Col, Spin, message, Tabs, Divider, Select, Image, Badge,
  Statistic, Progress, Empty, Tooltip, Modal
} from 'antd'
import {
  PictureOutlined, CodeOutlined, CopyOutlined, ThunderboltOutlined,
  CheckCircleOutlined, CloseCircleOutlined, DownloadOutlined,
  HistoryOutlined, SettingOutlined, ImportOutlined, DeleteOutlined
} from '@ant-design/icons'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

// 模型配置
const MODEL_OPTIONS = [
  { value: 'wan2.7-image', label: 'Wan 2.7 Image（推荐）' },
  { value: 'wan2.1-t2i', label: 'Wan 2.1 T2I' },
  { value: 'gpt-image-1', label: 'GPT Image 1' },
  { value: 'dall-e-3', label: 'DALL-E 3' },
]

// 尺寸配置
const SIZE_OPTIONS = [
  { value: '1024x1024', label: '1:1 正方形（1024×1024）', width: 1024, height: 1024 },
  { value: '768x1024', label: '3:4 竖版（768×1024）', width: 768, height: 1024 },
  { value: '1024x768', label: '4:3 横版（1024×768）', width: 1024, height: 768 },
  { value: '1024x576', label: '16:9 宽屏（1024×576）', width: 1024, height: 576 },
  { value: '576x1024', label: '9:16 竖屏（576×1024）', width: 576, height: 1024 },
]

// 用途配置
const USE_CASE_OPTIONS = [
  { value: 'main_image', label: '商品主图' },
  { value: 'detail_image', label: '详情页图' },
  { value: 'lifestyle_image', label: '场景图' },
  { value: 'marketing_image', label: '营销图' },
  { value: 'variant_image', label: '变体图' },
]

// 预设Prompt模板
const PROMPT_TEMPLATES = [
  {
    name: '电商主图-白底',
    prompt: '专业电商产品摄影，纯白色背景，产品居中，柔和均匀光线，高清细节，商业广告质感，4K分辨率，无阴影或极淡阴影',
  },
  {
    name: '电商主图-场景',
    prompt: '专业电商产品摄影，真实使用场景，自然光线，生活化氛围，产品清晰突出，高清细节，商业广告质感，4K分辨率',
  },
  {
    name: '详情页-功能卖点',
    prompt: '电商详情页功能展示，产品结构清晰，核心卖点突出，简约现代设计，干净背景，专业排版，高清细节，商业质感',
  },
  {
    name: '详情页-场景展示',
    prompt: '电商详情页场景展示，多个使用场景拼接，自然光线，生活气息，产品融入场景，高清细节，商业广告质感',
  },
]

interface GeneratedImage {
  id: string
  url: string
  prompt: string
  model: string
  width: number
  height: number
  cost: number
  status: string
  created_at: string
}

export default function ImageStudio() {
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [form] = Form.useForm()

  // 服务状态
  const [serviceStatus, setServiceStatus] = useState<any>(null)
  // 生成的图片
  const [generatedImages, setGeneratedImages] = useState<GeneratedImage[]>([])
  // 历史任务
  const [historyTasks, setHistoryTasks] = useState<any[]>([])
  // 选中的图片
  const [selectedImage, setSelectedImage] = useState<GeneratedImage | null>(null)
  // 预览图片
  const [previewImage, setPreviewImage] = useState<string | null>(null)
  // 生成进度
  const [generateProgress, setGenerateProgress] = useState(0)
  // 当前生成数量
  const [generateCount, setGenerateCount] = useState(1)

  // 加载服务状态
  useEffect(() => {
    loadServiceStatus()
    loadHistory()

    // 检查是否有从产品工作流发送过来的Prompt
    const savedPrompt = localStorage.getItem('image_studio_prompt')
    if (savedPrompt) {
      try {
        const promptData = JSON.parse(savedPrompt)
        if (promptData.main_prompt) {
          form.setFieldsValue({ prompt: promptData.main_prompt })
          message.success(`已从产品工作流导入Prompt（${promptData.product_name || '未知产品'}）`)
        }
        // 清除已读取的Prompt
        localStorage.removeItem('image_studio_prompt')
      } catch (e) {
        console.error('Parse saved prompt error:', e)
      }
    }
  }, [])

  // 加载服务状态
  const loadServiceStatus = async () => {
    try {
      const resp = await fetch('/api/v1/image-gen/status')
      const data = await resp.json()
      setServiceStatus(data)
    } catch (e) {
      console.error('Load service status error:', e)
    }
  }

  // 加载历史任务
  const loadHistory = async () => {
    try {
      const resp = await fetch('/api/v1/image-gen/tasks?limit=20')
      const data = await resp.json()
      if (data.tasks) {
        setHistoryTasks(data.tasks)
      }
    } catch (e) {
      console.error('Load history error:', e)
    }
  }

  // 生成图片
  const handleGenerate = async () => {
    try {
      const values = await form.validateFields()
      if (!values.prompt || values.prompt.trim().length === 0) {
        message.error('请输入生图Prompt')
        return
      }

      setGenerating(true)
      setGenerateProgress(0)
      setGeneratedImages([])

      const sizeConfig = SIZE_OPTIONS.find(s => s.value === values.size) || SIZE_OPTIONS[0]
      const count = values.count || 1

      // 批量生成
      const results: GeneratedImage[] = []
      for (let i = 0; i < count; i++) {
        setGenerateProgress(Math.round((i / count) * 100))

        try {
          const resp = await fetch('/api/v1/image-gen/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              prompt: values.prompt,
              negative_prompt: values.negative_prompt,
              use_case: values.use_case,
              model: values.model,
              width: sizeConfig.width,
              height: sizeConfig.height,
            }),
          })
          const data = await resp.json()

          if (data.task || data.id) {
            const task = data.task || data
            results.push({
              id: task.id || `temp-${i}`,
              url: task.image_url || task.local_path || '',
              prompt: values.prompt,
              model: values.model,
              width: sizeConfig.width,
              height: sizeConfig.height,
              cost: task.cost_cny || 0,
              status: task.status || 'generated',
              created_at: task.created_at || new Date().toISOString(),
            })
          }
        } catch (e) {
          console.error(`Generate image ${i + 1} error:`, e)
          message.error(`第${i + 1}张图片生成失败`)
        }
      }

      setGenerateProgress(100)
      setGeneratedImages(results)

      if (results.length > 0) {
        message.success(`成功生成${results.length}张图片`)
        loadHistory()
      } else {
        message.error('图片生成失败，请检查API配置')
      }
    } catch (e: any) {
      message.error(e.message || '生成失败')
    } finally {
      setGenerating(false)
      setTimeout(() => setGenerateProgress(0), 2000)
    }
  }

  // 批准图片
  const handleApprove = async (image: GeneratedImage) => {
    try {
      const resp = await fetch(`/api/v1/image-gen/tasks/${image.id}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved_by: 'admin' }),
      })
      if (resp.ok) {
        message.success('图片已批准')
        setGeneratedImages(prev =>
          prev.map(img => img.id === image.id ? { ...img, status: 'approved' } : img)
        )
        loadHistory()
      }
    } catch (e) {
      message.error('批准失败')
    }
  }

  // 拒绝图片
  const handleReject = async (image: GeneratedImage) => {
    try {
      const resp = await fetch(`/api/v1/image-gen/tasks/${image.id}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'manual_reject' }),
      })
      if (resp.ok) {
        message.success('图片已拒绝')
        setGeneratedImages(prev =>
          prev.map(img => img.id === image.id ? { ...img, status: 'rejected' } : img)
        )
        loadHistory()
      }
    } catch (e) {
      message.error('拒绝失败')
    }
  }

  // 应用Prompt模板
  const applyTemplate = (template: any) => {
    form.setFieldsValue({ prompt: template.prompt })
    message.success(`已应用模板：${template.name}`)
  }

  // 复制Prompt
  const handleCopyPrompt = (text: string) => {
    navigator.clipboard.writeText(text)
    message.success('Prompt已复制')
  }

  // 获取状态标签颜色
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'generated': return 'blue'
      case 'approved': return 'green'
      case 'rejected': return 'red'
      case 'pending': return 'orange'
      case 'processing': return 'processing'
      default: return 'default'
    }
  }

  // 获取状态文本
  const getStatusText = (status: string) => {
    switch (status) {
      case 'generated': return '已生成'
      case 'approved': return '已批准'
      case 'rejected': return '已拒绝'
      case 'pending': return '待处理'
      case 'processing': return '生成中'
      default: return status
    }
  }

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: '24px' }}>
        <Space>
          <PictureOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>AI生图工作台</Title>
            <Text type="secondary">Prompt编辑 → 一键生图 → 多方案对比 → 筛选批准</Text>
          </div>
        </Space>
      </div>

      {/* 预算和统计 */}
      {serviceStatus && (
        <Row gutter={[16, 16]} style={{ marginBottom: '24px' }}>
          <Col span={6}>
            <Card size="small">
              <Statistic title="月度预算" value={serviceStatus.monthly_budget_cny} suffix="元" precision={2} />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic title="默认模型" value={serviceStatus.default_model} />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic title="可用模型" value={serviceStatus.available_models?.length || 0} />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic title="高成本阈值" value={serviceStatus.high_cost_threshold_cny} suffix="元/张" precision={2} />
            </Card>
          </Col>
        </Row>
      )}

      <Spin spinning={loading}>
        <Row gutter={[24, 24]}>
          {/* 左侧：Prompt编辑区 */}
          <Col xs={24} lg={10}>
            <Card title="Prompt编辑" size="small" extra={<Button size="small" icon={<ImportOutlined />} onClick={() => message.info('可从产品分析/主图生产器页面复制Prompt')}>导入Prompt</Button>}>
              <Form form={form} layout="vertical" initialValues={{ model: 'wan2.7-image', size: '1024x1024', use_case: 'main_image', count: 1 }}>
                {/* Prompt模板 */}
                <div style={{ marginBottom: '12px' }}>
                  <Text type="secondary" style={{ fontSize: '12px' }}>快速模板：</Text>
                  <Space wrap style={{ marginTop: '4px' }}>
                    {PROMPT_TEMPLATES.map((t, i) => (
                      <Tag key={i} color="purple" style={{ cursor: 'pointer' }} onClick={() => applyTemplate(t)}>
                        {t.name}
                      </Tag>
                    ))}
                  </Space>
                </div>

                <Form.Item name="prompt" label="主Prompt" rules={[{ required: true, message: '请输入生图Prompt' }]}>
                  <TextArea rows={6} placeholder="请输入详细的生图描述，包括：产品主体、背景、光线、构图、风格、画质要求等..." />
                </Form.Item>

                <Form.Item name="negative_prompt" label="负面Prompt（可选）">
                  <TextArea rows={2} placeholder="不希望出现的内容，如：低质量、模糊、变形、水印、文字等" />
                </Form.Item>

                <Row gutter={[12, 12]}>
                  <Col span={12}>
                    <Form.Item name="model" label="模型">
                      <Select options={MODEL_OPTIONS} />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item name="size" label="尺寸">
                      <Select options={SIZE_OPTIONS} />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item name="use_case" label="用途">
                      <Select options={USE_CASE_OPTIONS} />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item name="count" label="生成数量">
                      <Select options={[
                        { value: 1, label: '1张' },
                        { value: 2, label: '2张' },
                        { value: 3, label: '3张（推荐）' },
                        { value: 4, label: '4张' },
                        { value: 5, label: '5张' },
                      ]} onChange={setGenerateCount} />
                    </Form.Item>
                  </Col>
                </Row>

                <Button type="primary" icon={<ThunderboltOutlined />} onClick={handleGenerate} block size="large" loading={generating}>
                  {generating ? `生成中... ${generateProgress}%` : `一键生成${generateCount}张图片`}
                </Button>

                {generating && (
                  <Progress percent={generateProgress} status="active" style={{ marginTop: '12px' }} />
                )}
              </Form>
            </Card>

            {/* 使用提示 */}
            <Card title="生图技巧" size="small" style={{ marginTop: '16px' }}>
              <ul style={{ paddingLeft: '20px', margin: 0, fontSize: '13px', lineHeight: '1.8' }}>
                <li>Prompt越具体，生成效果越好（主体+背景+光线+构图+风格+画质）</li>
                <li>建议一次生成3张，从中选最优，避免单张赌运气</li>
                <li>电商主图推荐1:1正方形，详情页推荐3:4竖版</li>
                <li>负面Prompt可有效避免低质量、变形、水印等问题</li>
                <li>生成后可批准优质图片，拒绝不满意的图片</li>
              </ul>
            </Card>
          </Col>

          {/* 右侧：生成结果和历史 */}
          <Col xs={24} lg={14}>
            <Tabs
              defaultActiveKey="result"
              items={[
                {
                  key: 'result',
                  label: `生成结果（${generatedImages.length}）`,
                  children: (
                    <Card size="small" title="本次生成结果">
                      {generating ? (
                        <div style={{ textAlign: 'center', padding: '60px 0' }}>
                          <Spin size="large" />
                          <Paragraph type="secondary" style={{ marginTop: '16px' }}>
                            AI正在生成图片，请稍候...
                          </Paragraph>
                        </div>
                      ) : generatedImages.length > 0 ? (
                        <Row gutter={[16, 16]}>
                          {generatedImages.map((image, index) => (
                            <Col xs={24} sm={12} key={image.id}>
                              <Card
                                size="small"
                                hoverable
                                cover={
                                  image.url ? (
                                    <div style={{ position: 'relative', cursor: 'pointer' }} onClick={() => setPreviewImage(image.url)}>
                                      <img
                                        alt={`Generated ${index + 1}`}
                                        src={image.url}
                                        style={{ width: '100%', height: '200px', objectFit: 'cover' }}
                                      />
                                      <Badge count={index + 1} style={{ position: 'absolute', top: '8px', left: '8px' }} />
                                    </div>
                                  ) : (
                                    <div style={{ height: '200px', background: '#f5f5f5', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                      <Text type="secondary">图片URL不可用</Text>
                                    </div>
                                  )
                                }
                                actions={[
                                  <Tooltip title="批准"><CheckCircleOutlined key="approve" style={{ color: '#52c41a' }} onClick={() => handleApprove(image)} /></Tooltip>,
                                  <Tooltip title="拒绝"><CloseCircleOutlined key="reject" style={{ color: '#ff4d4f' }} onClick={() => handleReject(image)} /></Tooltip>,
                                  <Tooltip title="下载"><DownloadOutlined key="download" onClick={() => image.url && window.open(image.url, '_blank')} /></Tooltip>,
                                  <Tooltip title="复制Prompt"><CopyOutlined key="copy" onClick={() => handleCopyPrompt(image.prompt)} /></Tooltip>,
                                ]}
                              >
                                <Card.Meta
                                  title={<Space><Tag color={getStatusColor(image.status)}>{getStatusText(image.status)}</Tag><Text type="secondary" style={{ fontSize: '11px' }}>¥{image.cost?.toFixed(4)}</Text></Space>}
                                  description={<Paragraph ellipsis={{ rows: 2 }} style={{ fontSize: '12px', margin: 0 }}>{image.prompt}</Paragraph>}
                                />
                              </Card>
                            </Col>
                          ))}
                        </Row>
                      ) : (
                        <Empty description="暂无生成结果，请在左侧输入Prompt并点击生成" />
                      )}
                    </Card>
                  ),
                },
                {
                  key: 'history',
                  label: `历史任务（${historyTasks.length}）`,
                  children: (
                    <Card size="small" title="历史生成记录" extra={<Button size="small" onClick={loadHistory}>刷新</Button>}>
                      {historyTasks.length > 0 ? (
                        <List
                          dataSource={historyTasks}
                          renderItem={(item: any) => (
                            <List.Item
                              actions={[
                                <Tag color={getStatusColor(item.status)} key="status">{getStatusText(item.status)}</Tag>,
                                <Text type="secondary" key="cost" style={{ fontSize: '12px' }}>¥{item.cost_cny?.toFixed(4)}</Text>,
                              ]}
                            >
                              <List.Item.Meta
                                avatar={<PictureOutlined style={{ fontSize: '24px', color: '#722ed1' }} />}
                                title={<Text ellipsis style={{ maxWidth: '400px' }}>{item.prompt}</Text>}
                                description={
                                  <Space>
                                    <Text type="secondary" style={{ fontSize: '12px' }}>{item.model}</Text>
                                    <Text type="secondary" style={{ fontSize: '12px' }}>{item.width}×{item.height}</Text>
                                    <Text type="secondary" style={{ fontSize: '12px' }}>{new Date(item.created_at).toLocaleString()}</Text>
                                  </Space>
                                }
                              />
                            </List.Item>
                          )}
                        />
                      ) : (
                        <Empty description="暂无历史记录" />
                      )}
                    </Card>
                  ),
                },
              ]}
            />
          </Col>
        </Row>
      </Spin>

      {/* 图片预览Modal */}
      <Modal
        open={!!previewImage}
        footer={null}
        onCancel={() => setPreviewImage(null)}
        width={800}
        centered
      >
        {previewImage && (
          <img src={previewImage} alt="Preview" style={{ width: '100%', maxHeight: '70vh', objectFit: 'contain' }} />
        )}
      </Modal>
    </div>
  )
}
