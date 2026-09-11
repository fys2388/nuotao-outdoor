import { useState } from 'react'
import {
  Card, Form, Input, Button, Space, Typography, Steps, Tag, Alert,
  Descriptions, Row, Col, Spin, message, Tabs, Divider, Select, List,
  Checkbox, Collapse, Badge
} from 'antd'
import {
  PictureOutlined, FileTextOutlined, CodeOutlined, CopyOutlined,
  ThunderboltOutlined, CheckCircleOutlined, AppstoreOutlined,
  AuditOutlined, RocketOutlined
} from '@ant-design/icons'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input
const { Panel } = Collapse

// 卖点类型配置
const SELLING_POINT_OPTIONS = [
  { value: 'portability', label: '便携卖点' },
  { value: 'capacity', label: '容量卖点' },
  { value: 'cleaning', label: '清洁卖点' },
  { value: 'scene', label: '场景卖点' },
  { value: 'quality', label: '品质卖点' },
  { value: 'function', label: '功能卖点' },
  { value: 'design', label: '设计卖点' },
  { value: 'price', label: '性价比卖点' },
]

// 主图方向配置
const DIRECTION_CONFIG: Record<string, { name: string; color: string; icon: string }> = {
  white_background: { name: '白底清爽', color: 'blue', icon: '⬜' },
  real_scene: { name: '真实场景', color: 'green', icon: '🏞️' },
  promotion_conversion: { name: '促销转化', color: 'orange', icon: '🎯' },
}

export default function MainImageGenerator() {
  const [currentStep, setCurrentStep] = useState(0)
  const [loading, setLoading] = useState(false)
  const [form] = Form.useForm()

  // 商品信息
  const [productInfo, setProductInfo] = useState<any>(null)
  // 3套主图方向
  const [directions, setDirections] = useState<any>(null)
  // 主图文案
  const [mainCopy, setMainCopy] = useState<any>(null)
  // 所有卖点文案
  const [allCopy, setAllCopy] = useState<any>(null)
  // 批量变体
  const [variants, setVariants] = useState<any>(null)
  // 执行清单
  const [checklist, setChecklist] = useState<any>(null)
  // 完整工作流结果
  const [workflowResult, setWorkflowResult] = useState<any>(null)
  // 完整Prompt模板
  const [template, setTemplate] = useState<string>('')

  // 选中的卖点类型
  const [selectedPointType, setSelectedPointType] = useState('portability')
  // 选中的基础方向
  const [selectedBaseDirection, setSelectedBaseDirection] = useState('white_background')

  // 一键运行完整工作流
  const handleRunWorkflow = async () => {
    try {
      const values = await form.validateFields()
      setLoading(true)
      setProductInfo(values)

      const resp = await fetch('/api/v1/main-image/workflow', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      })
      const data = await resp.json()
      if (data.success) {
        setWorkflowResult(data.data)
        setDirections(data.data.workflow.step02_three_directions)
        setVariants(data.data.workflow.step04_variants)
        setAllCopy(data.data.workflow.step05_copy)
        setChecklist(data.data.workflow.step06_checklist)
        setCurrentStep(5)
        message.success('完整6步工作流运行完成')
      } else {
        message.error(data.error || '工作流运行失败')
      }
    } catch (e: any) {
      message.error(e.message || '工作流运行失败')
    } finally {
      setLoading(false)
    }
  }

  // 生成3套主图方向
  const handleGenerateDirections = async () => {
    try {
      const values = await form.validateFields()
      setLoading(true)
      setProductInfo(values)

      const resp = await fetch('/api/v1/main-image/directions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      })
      const data = await resp.json()
      if (data.success) {
        setDirections(data.data)
        setCurrentStep(1)
        message.success('3套主图方向生成完成')
      } else {
        message.error(data.error || '生成失败')
      }
    } catch (e: any) {
      message.error(e.message || '生成失败')
    } finally {
      setLoading(false)
    }
  }

  // 生成主图文案
  const handleGenerateCopy = async () => {
    try {
      const values = await form.validateFields()
      setLoading(true)

      const resp = await fetch('/api/v1/main-image/copy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...values, selling_point_type: selectedPointType, count: 3, max_length: 10 }),
      })
      const data = await resp.json()
      if (data.success) {
        setMainCopy(data.data)
        message.success('主图文案生成完成')
      } else {
        message.error(data.error || '生成失败')
      }
    } catch (e: any) {
      message.error(e.message || '生成失败')
    } finally {
      setLoading(false)
    }
  }

  // 生成所有卖点文案
  const handleGenerateAllCopy = async () => {
    try {
      const values = await form.validateFields()
      setLoading(true)

      const resp = await fetch('/api/v1/main-image/all-copy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      })
      const data = await resp.json()
      if (data.success) {
        setAllCopy(data.data)
        message.success(`生成${data.data.total_count}条文案完成`)
      } else {
        message.error(data.error || '生成失败')
      }
    } catch (e: any) {
      message.error(e.message || '生成失败')
    } finally {
      setLoading(false)
    }
  }

  // 生成批量变体
  const handleGenerateVariants = async () => {
    try {
      const values = await form.validateFields()
      setLoading(true)

      const resp = await fetch('/api/v1/main-image/variants', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...values, base_direction: selectedBaseDirection, variant_count: 10 }),
      })
      const data = await resp.json()
      if (data.success) {
        setVariants(data.data)
        setCurrentStep(3)
        message.success(`生成${data.data.variant_count}个变体完成`)
      } else {
        message.error(data.error || '生成失败')
      }
    } catch (e: any) {
      message.error(e.message || '生成失败')
    } finally {
      setLoading(false)
    }
  }

  // 生成执行清单
  const handleGenerateChecklist = async () => {
    try {
      const values = await form.validateFields()
      setLoading(true)

      const resp = await fetch('/api/v1/main-image/checklist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ product_info: values, variants: variants?.variants }),
      })
      const data = await resp.json()
      if (data.success) {
        setChecklist(data.data)
        setCurrentStep(5)
        message.success('执行清单生成完成')
      } else {
        message.error(data.error || '生成失败')
      }
    } catch (e: any) {
      message.error(e.message || '生成失败')
    } finally {
      setLoading(false)
    }
  }

  // 获取完整Prompt模板
  const handleGetTemplate = async () => {
    try {
      const resp = await fetch('/api/v1/main-image/template')
      const data = await resp.json()
      if (data.success) {
        setTemplate(data.data.template)
        message.success('Prompt模板已加载')
      }
    } catch (e: any) {
      message.error(e.message || '获取失败')
    }
  }

  // 复制文本
  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text)
    message.success('已复制到剪贴板')
  }

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: '24px' }}>
        <Space>
          <PictureOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>电商主图生产器</Title>
            <Text type="secondary">6步完整流程：商品信息→3套方向→绘图提示词→批量变体→主图文案→执行清单</Text>
          </div>
        </Space>
      </div>

      {/* 步骤条 */}
      <Steps
        current={currentStep}
        style={{ marginBottom: '24px' }}
        items={[
          { title: '商品信息', description: '4维度输入', icon: <FileTextOutlined /> },
          { title: '3套方向', description: '白底/场景/促销', icon: <AppstoreOutlined /> },
          { title: '绘图提示词', description: '4部分结构', icon: <CodeOutlined /> },
          { title: '批量变体', description: '10个变体', icon: <PictureOutlined /> },
          { title: '主图文案', description: '10字以内', icon: <FileTextOutlined /> },
          { title: '执行清单', description: '检查项', icon: <AuditOutlined /> },
        ]}
      />

      <Spin spinning={loading} tip="生成中...">
        <Row gutter={[24, 24]}>
          {/* 左侧：商品信息输入 */}
          <Col xs={24} lg={8}>
            <Card title="商品信息（Step 01）" size="small">
              <Alert
                message="资料越具体，出图越稳定"
                type="info"
                showIcon
                style={{ marginBottom: '16px' }}
              />
              <Form form={form} layout="vertical">
                <Form.Item name="name" label="产品名称" rules={[{ required: true, message: '请输入产品名称' }]}>
                  <Input placeholder="如：便携榨汁杯" />
                </Form.Item>
                <Form.Item name="category" label="产品类目">
                  <Input placeholder="如：厨房用品/小家电" />
                </Form.Item>
                <Form.Item name="price" label="产品价格">
                  <Input placeholder="如：¥99" />
                </Form.Item>
                <Form.Item name="target_audience" label="目标人群">
                  <Input placeholder="如：25-35岁都市白领" />
                </Form.Item>
                <Form.Item name="core_selling_points" label="核心卖点（每行一个）">
                  <TextArea rows={3} placeholder={'便携易带\n一杯刚刚好\n拆洗方便'} />
                </Form.Item>
                <Form.Item name="usage_scenarios" label="使用场景（每行一个）">
                  <TextArea rows={3} placeholder={'办公室\n健身房\n通勤路上'} />
                </Form.Item>
                <Form.Item name="description" label="产品描述">
                  <TextArea rows={2} placeholder="可选：产品详细描述" />
                </Form.Item>

                <Divider style={{ margin: '12px 0' }} />

                <Space direction="vertical" style={{ width: '100%' }}>
                  <Button type="primary" icon={<RocketOutlined />} onClick={handleRunWorkflow} block size="large">
                    一键运行完整6步工作流
                  </Button>
                  <Button icon={<AppstoreOutlined />} onClick={handleGenerateDirections} block>
                    仅生成3套主图方向
                  </Button>
                </Space>
              </Form>
            </Card>

            {/* 完整Prompt模板 */}
            <Card title="可直接照抄的Prompt模板" size="small" style={{ marginTop: '16px' }}>
              <Button icon={<CodeOutlined />} onClick={handleGetTemplate} block style={{ marginBottom: '12px' }}>
                加载完整Prompt模板
              </Button>
              {template && (
                <>
                  <div style={{ background: '#f6f8fa', padding: '12px', borderRadius: '8px', marginBottom: '8px' }}>
                    <pre style={{ whiteSpace: 'pre-wrap', margin: 0, fontSize: '12px', lineHeight: '1.6' }}>
                      {template}
                    </pre>
                  </div>
                  <Button icon={<CopyOutlined />} onClick={() => handleCopy(template)} block>
                    复制Prompt模板
                  </Button>
                </>
              )}
            </Card>
          </Col>

          {/* 右侧：结果展示 */}
          <Col xs={24} lg={16}>
            <Tabs
              activeKey={currentStep.toString()}
              onChange={(key) => setCurrentStep(parseInt(key))}
              items={[
                {
                  key: '1',
                  label: 'Step 02 3套主图方向',
                  children: directions ? (
                    <Row gutter={[16, 16]}>
                      {Object.entries(directions.directions || {}).map(([key, value]: [string, any]) => {
                        const config = DIRECTION_CONFIG[key] || { name: key, color: 'default', icon: '📌' }
                        const isRecommended = directions.recommendation?.direction === key
                        return (
                          <Col xs={24} md={8} key={key}>
                            <Card
                              size="small"
                              title={
                                <Space>
                                  <span>{config.icon}</span>
                                  <span>{config.name}</span>
                                  {isRecommended && <Tag color="green">推荐</Tag>}
                                </Space>
                              }
                            >
                              <Paragraph type="secondary" style={{ fontSize: '12px', marginBottom: '8px' }}>
                                {value.description}
                              </Paragraph>
                              <Divider style={{ margin: '8px 0' }} />
                              <Text strong style={{ fontSize: '12px' }}>测试目标：</Text>
                              <Paragraph style={{ fontSize: '12px', margin: '4px 0' }}>{value.test_goal}</Paragraph>
                              <Divider style={{ margin: '8px 0' }} />
                              <Text strong style={{ fontSize: '12px' }}>推荐文案：</Text>
                              <div style={{ marginTop: '4px' }}>
                                {value.recommended_copy?.map((copy: string, i: number) => (
                                  <Tag key={i} color={config.color} style={{ marginBottom: '4px' }}>{copy}</Tag>
                                ))}
                              </div>
                            </Card>
                          </Col>
                        )
                      })}
                    </Row>
                  ) : (
                    <Alert message="请先输入商品信息并点击生成3套主图方向" type="info" showIcon />
                  ),
                },
                {
                  key: '3',
                  label: 'Step 04 批量变体',
                  children: variants ? (
                    <Card size="small" title={`批量变体（${variants.variant_count}个）`}>
                      <Alert
                        message="一张跑通后再批量，每张图都要承担一个测试任务"
                        type="warning"
                        showIcon
                        style={{ marginBottom: '16px' }}
                      />
                      <List
                        dataSource={variants.variants}
                        renderItem={(item: any) => (
                          <List.Item>
                            <List.Item.Meta
                              avatar={<Badge count={item.id} style={{ backgroundColor: '#722ed1' }} />}
                              title={
                                <Space>
                                  <Text strong>{item.filename}</Text>
                                  <Tag color="blue">{item.variant_name}</Tag>
                                </Space>
                              }
                              description={
                                <div>
                                  <Text type="secondary" style={{ fontSize: '12px' }}>
                                    测试目标：{item.test_goal}
                                  </Text>
                                  <br />
                                  <Text type="secondary" style={{ fontSize: '12px' }}>
                                    推荐文案：{item.recommended_copy?.join(' | ')}
                                  </Text>
                                </div>
                              }
                            />
                          </List.Item>
                        )}
                      />
                    </Card>
                  ) : (
                    <Alert message="请先生成批量变体" type="info" showIcon />
                  ),
                },
                {
                  key: '4',
                  label: 'Step 05 主图文案',
                  children: (
                    <Card size="small" title="主图文案生成器">
                      <Alert
                        message="主图文案只讲一个卖点，每条控制在10个字以内。直接、具体、不过度承诺。"
                        type="info"
                        showIcon
                        style={{ marginBottom: '16px' }}
                      />
                      <Space style={{ marginBottom: '16px' }}>
                        <Select
                          value={selectedPointType}
                          onChange={setSelectedPointType}
                          options={SELLING_POINT_OPTIONS}
                          style={{ width: 160 }}
                        />
                        <Button type="primary" onClick={handleGenerateCopy}>生成该卖点文案</Button>
                        <Button onClick={handleGenerateAllCopy}>生成所有卖点文案</Button>
                      </Space>

                      {mainCopy && (
                        <div style={{ marginBottom: '16px' }}>
                          <Title level={5}>{mainCopy.selling_point_name}</Title>
                          <Row gutter={[8, 8]}>
                            {mainCopy.copies?.map((copy: any, i: number) => (
                              <Col key={i}>
                                <Card size="small" style={{ width: 120, textAlign: 'center' }}>
                                  <Title level={4} style={{ margin: 0 }}>{copy.text}</Title>
                                  <Text type="secondary" style={{ fontSize: '11px' }}>{copy.length}字</Text>
                                </Card>
                              </Col>
                            ))}
                          </Row>
                        </div>
                      )}

                      {allCopy && (
                        <Collapse>
                          {Object.entries(allCopy.all_copies || {}).map(([key, copies]: [string, any]) => {
                            const pointName = SELLING_POINT_OPTIONS.find(o => o.value === key)?.label || key
                            return (
                              <Panel header={`${pointName}（${copies.length}条）`} key={key}>
                                <Space wrap>
                                  {copies.map((copy: any, i: number) => (
                                    <Tag key={i} color="purple" style={{ fontSize: '14px', padding: '4px 12px' }}>
                                      {copy.text}
                                    </Tag>
                                  ))}
                                </Space>
                              </Panel>
                            )
                          })}
                        </Collapse>
                      )}
                    </Card>
                  ),
                },
                {
                  key: '5',
                  label: 'Step 06 执行清单',
                  children: checklist ? (
                    <Card size="small" title="执行清单和检查项">
                      <Alert
                        message="从试试看，变成可交付"
                        type="success"
                        showIcon
                        style={{ marginBottom: '16px' }}
                      />

                      <Title level={5}>文件名规范</Title>
                      <Descriptions column={1} size="small" bordered style={{ marginBottom: '16px' }}>
                        <Descriptions.Item label="格式">{checklist.filename_spec?.format}</Descriptions.Item>
                        <Descriptions.Item label="示例">{checklist.filename_spec?.example}</Descriptions.Item>
                        <Descriptions.Item label="规则">
                          {checklist.filename_spec?.rules?.map((rule: string, i: number) => (
                            <div key={i}>• {rule}</div>
                          ))}
                        </Descriptions.Item>
                      </Descriptions>

                      <Title level={5}>检查项（{checklist.total_check_items}项）</Title>
                      <Row gutter={[16, 16]}>
                        {Object.entries(checklist.checklist || {}).map(([key, value]: [string, any]) => (
                          <Col xs={24} md={12} key={key}>
                            <Card size="small" title={value.name}>
                              <Paragraph type="secondary" style={{ fontSize: '12px' }}>
                                {value.description}
                              </Paragraph>
                              <div>
                                {value.items?.map((item: string, i: number) => (
                                  <div key={i} style={{ marginBottom: '4px' }}>
                                    <Checkbox>{item}</Checkbox>
                                  </div>
                                ))}
                              </div>
                            </Card>
                          </Col>
                        ))}
                      </Row>
                    </Card>
                  ) : (
                    <Alert message="请先生成执行清单" type="info" showIcon />
                  ),
                },
              ]}
            />

            {/* 工作流摘要 */}
            {workflowResult && (
              <Card size="small" title="工作流摘要" style={{ marginTop: '16px' }}>
                <Row gutter={[16, 16]}>
                  <Col span={6}>
                    <div style={{ textAlign: 'center' }}>
                      <Title level={2} style={{ color: '#722ed1', margin: 0 }}>{workflowResult.summary?.directions_count}</Title>
                      <Text type="secondary">套主图方向</Text>
                    </div>
                  </Col>
                  <Col span={6}>
                    <div style={{ textAlign: 'center' }}>
                      <Title level={2} style={{ color: '#52c41a', margin: 0 }}>{workflowResult.summary?.variants_count}</Title>
                      <Text type="secondary">个主图变体</Text>
                    </div>
                  </Col>
                  <Col span={6}>
                    <div style={{ textAlign: 'center' }}>
                      <Title level={2} style={{ color: '#faad14', margin: 0 }}>{workflowResult.summary?.copy_count}</Title>
                      <Text type="secondary">条主图文案</Text>
                    </div>
                  </Col>
                  <Col span={6}>
                    <div style={{ textAlign: 'center' }}>
                      <Title level={2} style={{ color: '#f5222d', margin: 0 }}>{workflowResult.summary?.check_items_count}</Title>
                      <Text type="secondary">项检查清单</Text>
                    </div>
                  </Col>
                </Row>
              </Card>
            )}
          </Col>
        </Row>
      </Spin>
    </div>
  )
}
