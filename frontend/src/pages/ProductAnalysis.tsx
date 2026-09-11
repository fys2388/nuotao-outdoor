import { useState } from 'react'
import {
  Card, Form, Input, Button, Space, Typography, Steps, Tag, Alert,
  Descriptions, Row, Col, Spin, message, Tabs, Divider, Select, Tooltip
} from 'antd'
import {
  RobotOutlined, FileTextOutlined, CodeOutlined, CopyOutlined,
  ThunderboltOutlined, CheckCircleOutlined, ReloadOutlined
} from '@ant-design/icons'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

// 10字段AI识别结果配置
const AI_RECOGNITION_FIELDS = [
  { key: 'brand_name', label: '品牌名称/Logo' },
  { key: 'product_category', label: '产品类目' },
  { key: 'product_appearance', label: '产品外观' },
  { key: 'material_texture', label: '材质质感' },
  { key: 'core_selling_points', label: '核心卖点', isArray: true },
  { key: 'usage_scenarios', label: '适用场景', isArray: true },
  { key: 'target_audience', label: '目标人群' },
  { key: 'visual_style', label: '视觉风格' },
  { key: 'primary_colors', label: '主色调', isArray: true },
  { key: 'extendable_page_types', label: '可延展页面', isArray: true },
]

// 17字段产品信息报告配置
const PRODUCT_REPORT_FIELDS = [
  { key: 'brand_name', label: '品牌名称', span: 2 },
  { key: 'product_name', label: '产品名称', span: 2 },
  { key: 'product_category', label: '产品类别', span: 1 },
  { key: 'product_dimensions', label: '产品尺寸', span: 1 },
  { key: 'material_craft', label: '材质工艺', span: 2 },
  { key: 'product_color', label: '产品颜色', span: 1 },
  { key: 'product_capacity', label: '产品容量/规格', span: 1 },
  { key: 'applicable_target', label: '适用对象', span: 2 },
  { key: 'core_selling_points', label: '核心卖点', isArray: true, span: 2 },
  { key: 'product_features', label: '产品功能', isArray: true, span: 2 },
  { key: 'target_audience', label: '目标人群', span: 2 },
  { key: 'usage_scenarios', label: '使用场景', isArray: true, span: 2 },
  { key: 'visual_style', label: '视觉风格', span: 1 },
  { key: 'primary_colors', label: '主色调', isArray: true, span: 1 },
  { key: 'extendable_pages', label: '可延展页面', isArray: true, span: 2 },
  { key: 'product_description', label: '产品详细描述', span: 2, isTextarea: true },
  { key: 'quality_assurance', label: '品质保障', span: 2, isTextarea: true },
]

// 详情页类型配置
const PAGE_TYPE_OPTIONS = [
  { value: 'brand_scene', label: '品牌场景页' },
  { value: 'product_hero', label: '产品主视觉页' },
  { value: 'feature_selling', label: '功能卖点页' },
  { value: 'scene_showcase', label: '场景展示页' },
  { value: 'detail_closeup', label: '细节特写页' },
  { value: 'quality_assurance', label: '品质保障页' },
  { value: 'comparison', label: '对比图页' },
  { value: 'faq', label: 'FAQ页' },
]

export default function ProductAnalysis() {
  const [currentStep, setCurrentStep] = useState(0)
  const [loading, setLoading] = useState(false)
  const [form] = Form.useForm()

  // 产品信息
  const [productInfo, setProductInfo] = useState<any>(null)
  // AI识别结果
  const [aiRecognition, setAiRecognition] = useState<any>(null)
  // 产品信息报告
  const [productReport, setProductReport] = useState<any>(null)
  // 生成的Prompt
  const [generatedPrompt, setGeneratedPrompt] = useState<any>(null)
  // 批量Prompts
  const [batchPrompts, setBatchPrompts] = useState<any>(null)
  // 选中的页面类型
  const [selectedPageType, setSelectedPageType] = useState('brand_scene')

  // STEP 01: AI产品分析
  const handleAnalyze = async () => {
    try {
      const values = await form.validateFields()
      setLoading(true)
      setProductInfo(values)

      const resp = await fetch('/api/v1/product-analysis/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      })
      const data = await resp.json()
      if (data.success) {
        setAiRecognition(data.data.ai_recognition)
        setCurrentStep(1)
        message.success('AI产品分析完成')
      } else {
        message.error(data.error || '分析失败')
      }
    } catch (e: any) {
      message.error(e.message || '分析失败')
    } finally {
      setLoading(false)
    }
  }

  // STEP 02: 生成产品信息报告
  const handleGenerateReport = async () => {
    try {
      setLoading(true)
      const resp = await fetch('/api/v1/product-analysis/report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          product_info: productInfo,
          ai_recognition: aiRecognition,
        }),
      })
      const data = await resp.json()
      if (data.success) {
        setProductReport(data.data.product_report)
        setCurrentStep(2)
        message.success('产品信息报告生成完成')
      } else {
        message.error(data.error || '报告生成失败')
      }
    } catch (e: any) {
      message.error(e.message || '报告生成失败')
    } finally {
      setLoading(false)
    }
  }

  // 一键完成分析+报告
  const handleAnalyzeAndReport = async () => {
    try {
      const values = await form.validateFields()
      setLoading(true)
      setProductInfo(values)

      const resp = await fetch('/api/v1/product-analysis/analyze-and-report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ product_info: values }),
      })
      const data = await resp.json()
      if (data.success) {
        setAiRecognition(data.data.ai_recognition)
        setProductReport(data.data.product_report)
        setCurrentStep(2)
        message.success('分析+报告一键完成')
      } else {
        message.error(data.error || '失败')
      }
    } catch (e: any) {
      message.error(e.message || '失败')
    } finally {
      setLoading(false)
    }
  }

  // STEP 03: 生成Prompt
  const handleGeneratePrompt = async () => {
    try {
      setLoading(true)
      const resp = await fetch('/api/v1/product-analysis/prompt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          product_report: productReport,
          page_type: selectedPageType,
        }),
      })
      const data = await resp.json()
      if (data.success) {
        setGeneratedPrompt(data.data)
        setCurrentStep(3)
        message.success('Prompt生成完成')
      } else {
        message.error(data.error || 'Prompt生成失败')
      }
    } catch (e: any) {
      message.error(e.message || 'Prompt生成失败')
    } finally {
      setLoading(false)
    }
  }

  // 批量生成Prompt
  const handleBatchPrompts = async () => {
    try {
      setLoading(true)
      const resp = await fetch('/api/v1/product-analysis/batch-prompts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ product_report: productReport }),
      })
      const data = await resp.json()
      if (data.success) {
        setBatchPrompts(data.data)
        message.success(`批量生成${data.data.count}个Prompt完成`)
      } else {
        message.error(data.error || '批量生成失败')
      }
    } catch (e: any) {
      message.error(e.message || '批量生成失败')
    } finally {
      setLoading(false)
    }
  }

  // 复制Prompt
  const handleCopyPrompt = (text: string) => {
    navigator.clipboard.writeText(text)
    message.success('Prompt已复制到剪贴板')
  }

  // 渲染数组字段
  const renderArrayField = (value: any) => {
    if (Array.isArray(value)) {
      return value.map((v: string, i: number) => (
        <Tag key={i} color="blue" style={{ marginBottom: 4 }}>{v}</Tag>
      ))
    }
    return value || '-'
  }

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: '24px' }}>
        <Space>
          <RobotOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>AI产品分析与Prompt生成</Title>
            <Text type="secondary">STEP 01 AI读懂产品 → STEP 02 产品信息报告 → STEP 03 自动生成生图Prompt</Text>
          </div>
        </Space>
      </div>

      {/* 步骤条 */}
      <Steps
        current={currentStep}
        style={{ marginBottom: '24px' }}
        items={[
          { title: 'AI产品分析', description: '10字段识别结果', icon: <RobotOutlined /> },
          { title: '产品信息报告', description: '17字段报告+人工校对', icon: <FileTextOutlined /> },
          { title: '生成Prompt', description: '8部分完整Prompt', icon: <CodeOutlined /> },
        ]}
      />

      <Spin spinning={loading} tip="AI分析中...">
        <Row gutter={[24, 24]}>
          {/* 左侧：产品信息输入 */}
          <Col xs={24} lg={8}>
            <Card title="1688商品信息" size="small">
              <Form form={form} layout="vertical">
                <Form.Item name="name" label="产品名称" rules={[{ required: true, message: '请输入产品名称' }]}>
                  <Input placeholder="请输入1688产品名称" />
                </Form.Item>
                <Form.Item name="category" label="产品类目">
                  <Input placeholder="如：户外用品/露营装备" />
                </Form.Item>
                <Form.Item name="price" label="产品价格">
                  <Input placeholder="如：¥6.50" />
                </Form.Item>
                <Form.Item name="supplier_name" label="供应商名称">
                  <Input placeholder="如：深圳市贝尔户外用品有限公司" />
                </Form.Item>
                <Form.Item name="description" label="产品描述">
                  <TextArea rows={4} placeholder="请输入产品详细描述" />
                </Form.Item>
                <Form.Item name="images" label="产品图片URL（每行一个）">
                  <TextArea rows={3} placeholder="https://..." />
                </Form.Item>
                <Form.Item name="additional_info" label="额外信息">
                  <TextArea rows={2} placeholder="可选：材质、规格、卖点等补充信息" />
                </Form.Item>
                <Space direction="vertical" style={{ width: '100%' }}>
                  <Button type="primary" icon={<ThunderboltOutlined />} onClick={handleAnalyzeAndReport} block>
                    一键分析+报告
                  </Button>
                  <Button icon={<RobotOutlined />} onClick={handleAnalyze} block>
                    仅AI分析（STEP 01）
                  </Button>
                </Space>
              </Form>
            </Card>
          </Col>

          {/* 右侧：分析结果 */}
          <Col xs={24} lg={16}>
            <Tabs
              activeKey={currentStep.toString()}
              onChange={(key) => setCurrentStep(parseInt(key))}
              items={[
                {
                  key: '0',
                  label: 'STEP 01 AI识别结果',
                  children: aiRecognition ? (
                    <Card size="small" title="AI产品识别结果（10字段）">
                      <Descriptions column={2} bordered size="small">
                        {AI_RECOGNITION_FIELDS.map((field) => (
                          <Descriptions.Item key={field.key} label={field.label} span={field.isArray ? 2 : 1}>
                            {field.isArray ? renderArrayField(aiRecognition[field.key]) : (aiRecognition[field.key] || '-')}
                          </Descriptions.Item>
                        ))}
                      </Descriptions>
                      <Divider />
                      <Button type="primary" icon={<FileTextOutlined />} onClick={handleGenerateReport}>
                        生成产品信息报告（STEP 02）
                      </Button>
                    </Card>
                  ) : (
                    <Alert message="请先在左侧输入产品信息并点击AI分析" type="info" showIcon />
                  ),
                },
                {
                  key: '1',
                  label: 'STEP 02 产品信息报告',
                  children: productReport ? (
                    <Card size="small" title="产品信息报告（17字段）" extra={<Tag color="green">可编辑</Tag>}>
                      <Descriptions column={2} bordered size="small">
                        {PRODUCT_REPORT_FIELDS.map((field) => (
                          <Descriptions.Item key={field.key} label={field.label} span={field.span || 1}>
                            {field.isArray ? renderArrayField(productReport[field.key]) : (
                              field.isTextarea ? (
                                <Paragraph style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{productReport[field.key] || '-'}</Paragraph>
                              ) : (productReport[field.key] || '-')
                            )}
                          </Descriptions.Item>
                        ))}
                      </Descriptions>
                      <Divider />
                      <Space>
                        <Button type="primary" icon={<CodeOutlined />} onClick={handleGeneratePrompt}>
                          生成生图Prompt（STEP 03）
                        </Button>
                        <Button icon={<ThunderboltOutlined />} onClick={handleBatchPrompts}>
                          批量生成6种页面Prompt
                        </Button>
                      </Space>
                    </Card>
                  ) : (
                    <Alert message="请先完成STEP 01 AI分析，然后生成产品信息报告" type="info" showIcon />
                  ),
                },
                {
                  key: '2',
                  label: 'STEP 03 生成Prompt',
                  children: generatedPrompt ? (
                    <Card size="small" title={`生成的Prompt - ${generatedPrompt.metadata?.page_type_name || ''}`}>
                      <Space style={{ marginBottom: '16px' }}>
                        <Select
                          value={selectedPageType}
                          onChange={setSelectedPageType}
                          options={PAGE_TYPE_OPTIONS}
                          style={{ width: 200 }}
                        />
                        <Button icon={<ReloadOutlined />} onClick={handleGeneratePrompt}>重新生成</Button>
                        <Tooltip title="复制完整Prompt">
                          <Button icon={<CopyOutlined />} onClick={() => handleCopyPrompt(generatedPrompt.full_prompt)}>
                            复制Prompt
                          </Button>
                        </Tooltip>
                      </Space>

                      <Alert
                        message={`Prompt长度: ${generatedPrompt.metadata?.prompt_length} 字符 | 画面比例: ${generatedPrompt.metadata?.aspect_ratio}`}
                        type="success"
                        showIcon
                        style={{ marginBottom: '16px' }}
                      />

                      <Tabs
                        items={[
                          {
                            key: 'full',
                            label: '完整Prompt',
                            children: (
                              <div style={{ background: '#f6f8fa', padding: '16px', borderRadius: '8px', maxHeight: '500px', overflow: 'auto' }}>
                                <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0, fontSize: '13px', lineHeight: '1.6' }}>
                                  {generatedPrompt.full_prompt}
                                </pre>
                              </div>
                            ),
                          },
                          {
                            key: 'parts',
                            label: '8部分结构',
                            children: (
                              <Space direction="vertical" style={{ width: '100%' }}>
                                {Object.entries(generatedPrompt.parts || {}).map(([key, value]: [string, any]) => (
                                  <Card key={key} size="small" title={<Tag color="purple">{key}</Tag>}>
                                    <Paragraph style={{ margin: 0, whiteSpace: 'pre-wrap', fontSize: '13px' }}>{value}</Paragraph>
                                  </Card>
                                ))}
                              </Space>
                            ),
                          },
                        ]}
                      />
                    </Card>
                  ) : (
                    <Alert message="请先完成STEP 02产品信息报告，然后生成生图Prompt" type="info" showIcon />
                  ),
                },
              ]}
            />

            {/* 批量Prompts展示 */}
            {batchPrompts && (
              <Card size="small" title={`批量生成的Prompt（${batchPrompts.count}个）`} style={{ marginTop: '24px' }}>
                <Row gutter={[16, 16]}>
                  {Object.entries(batchPrompts.prompts || {}).map(([key, value]: [string, any]) => (
                    <Col xs={24} md={12} key={key}>
                      <Card
                        size="small"
                        title={value.metadata?.page_type_name || key}
                        extra={
                          <Button size="small" icon={<CopyOutlined />} onClick={() => handleCopyPrompt(value.full_prompt)}>
                            复制
                          </Button>
                        }
                      >
                        <Text type="secondary">长度: {value.metadata?.prompt_length} 字符</Text>
                        <Paragraph ellipsis={{ rows: 3 }} style={{ marginTop: '8px', fontSize: '12px' }}>
                          {value.full_prompt?.substring(0, 200)}...
                        </Paragraph>
                      </Card>
                    </Col>
                  ))}
                </Row>
              </Card>
            )}
          </Col>
        </Row>
      </Spin>
    </div>
  )
}
