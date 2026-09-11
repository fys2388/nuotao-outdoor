import { useState } from 'react'
import {
  Card, Form, Input, Button, Space, Typography, Steps, Tag, Alert,
  Row, Col, Spin, message, Tabs, Divider, Select, Descriptions, Collapse,
  Statistic, Progress, Empty, Tooltip, Modal, List, Badge
} from 'antd'
import {
  ThunderboltOutlined, CheckCircleOutlined, CloseCircleOutlined,
  LoadingOutlined, CopyOutlined, ShopOutlined, FileTextOutlined,
  PictureOutlined, RocketOutlined, HistoryOutlined, PlayCircleOutlined
} from '@ant-design/icons'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input
const { Step } = Steps

// 工作流步骤配置
const PIPELINE_STEPS = [
  { id: 'input', title: '商品信息', description: '输入或导入商品信息', icon: FileTextOutlined },
  { id: 'analysis', title: 'AI产品分析', description: '10字段识别+17字段报告', icon: RocketOutlined },
  { id: 'main_image', title: '主图生产', description: '3套方向+文案+变体', icon: PictureOutlined },
  { id: 'prompt', title: '生图Prompt', description: '主图+详情页Prompt', icon: FileTextOutlined },
  { id: 'listing_data', title: '上架数据', description: '名称/描述/价格/SKU', icon: ShopOutlined },
  { id: 'listing', title: '上架WC', description: '人工确认后上架', icon: ThunderboltOutlined },
]

// 类目选项
const CATEGORY_OPTIONS = [
  { value: '露营装备', label: '露营装备' },
  { value: '照明设备', label: '照明设备' },
  { value: '户外厨房', label: '户外厨房' },
  { value: '户外服装', label: '户外服装' },
  { value: '户外配件', label: '户外配件' },
  { value: '其他', label: '其他' },
]

interface PipelineResult {
  success: boolean
  data: {
    pipeline_id: string
    status: string
    completed_steps: number
    total_steps: number
    progress: number
    elapsed_time_seconds: number
    steps: Record<string, any>
    errors: string[]
    product_name: string
    sku: string
  }
  error: string | null
}

export default function ProductPipeline() {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [pipelineResult, setPipelineResult] = useState<PipelineResult | null>(null)
  const [listingModalOpen, setListingModalOpen] = useState(false)
  const [listingLoading, setListingLoading] = useState(false)
  const [history, setHistory] = useState<PipelineResult[]>([])
  const [generatingImage, setGeneratingImage] = useState(false)
  const [generatedImages, setGeneratedImages] = useState<string[]>([])
  const [batchQueue, setBatchQueue] = useState<any[]>([])
  const [currentBatchIndex, setCurrentBatchIndex] = useState(0)
  const [importUrl, setImportUrl] = useState('')
  const [importLoading, setImportLoading] = useState(false)
  const [autoRunPipeline, setAutoRunPipeline] = useState(false)

  // 生成主图
  const handleGenerateImage = async () => {
    if (!pipelineResult?.data?.steps?.prompt?.data?.main_image_prompt) {
      message.error('请先运行工作流生成生图Prompt')
      return
    }

    try {
      setGeneratingImage(true)
      const prompt = pipelineResult.data.steps.prompt.data.main_image_prompt

      const resp = await fetch('/api/v1/image-gen/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: prompt,
          use_case: 'main_image',
          model: 'wan2.7-image',
          width: 1024,
          height: 1024,
        }),
      })
      const data = await resp.json()

      if (data.task || data.id) {
        const task = data.task || data
        const imageUrl = task.image_url || task.local_path || ''
        if (imageUrl) {
          setGeneratedImages(prev => [...prev, imageUrl])
          // 自动回填到上架数据
          if (pipelineResult?.data?.steps?.listing_data?.data) {
            const updatedResult = { ...pipelineResult }
            if (!updatedResult.data.steps.listing_data.data.images) {
              updatedResult.data.steps.listing_data.data.images = []
            }
            updatedResult.data.steps.listing_data.data.images.push({
              src: imageUrl,
              name: `main_image_${Date.now()}`,
            })
            setPipelineResult(updatedResult)
          }
          message.success('主图生成成功，已自动回填到上架数据')
        } else {
          message.warning('图片生成成功，但URL不可用')
        }
      } else {
        message.error(data.error || '图片生成失败')
      }
    } catch (e: any) {
      message.error(e.message || '图片生成失败')
    } finally {
      setGeneratingImage(false)
    }
  }

  // 页面加载时检查是否有从牛顿选品发送过来的商品信息
  useEffect(() => {
    const savedProduct = localStorage.getItem('product_pipeline_input')
    if (savedProduct) {
      try {
        const productData = JSON.parse(savedProduct)
        form.setFieldsValue({
          name: productData.name || '',
          category: productData.category || '',
          price: productData.price || '',
          description: productData.description || '',
          core_selling_points: Array.isArray(productData.core_selling_points)
            ? productData.core_selling_points.join('\n')
            : productData.core_selling_points || '',
          target_audience: productData.target_audience || '',
          usage_scenarios: Array.isArray(productData.usage_scenarios)
            ? productData.usage_scenarios.join('\n')
            : productData.usage_scenarios || '',
          product_features: Array.isArray(productData.product_features)
            ? productData.product_features.join('\n')
            : productData.product_features || '',
        })
        message.success(`已从牛顿选品导入商品信息（${productData.name || '未知商品'}）`)
        // 清除已读取的商品信息
        localStorage.removeItem('product_pipeline_input')
      } catch (e) {
        console.error('Parse saved product error:', e)
      }
    }

    // 检查是否有批量商品数据
    const savedBatch = localStorage.getItem('product_pipeline_batch')
    if (savedBatch) {
      try {
        const batchData = JSON.parse(savedBatch)
        if (batchData.products && batchData.products.length > 0) {
          setBatchQueue(batchData.products)
          setCurrentBatchIndex(0)
          // 自动填充第一个商品
          const firstProduct = batchData.products[0]
          form.setFieldsValue({
            name: firstProduct.name || '',
            category: firstProduct.category || '',
            price: firstProduct.price || '',
            description: firstProduct.description || '',
            core_selling_points: Array.isArray(firstProduct.core_selling_points)
              ? firstProduct.core_selling_points.join('\n')
              : firstProduct.core_selling_points || '',
            target_audience: firstProduct.target_audience || '',
            usage_scenarios: Array.isArray(firstProduct.usage_scenarios)
              ? firstProduct.usage_scenarios.join('\n')
              : firstProduct.usage_scenarios || '',
            product_features: Array.isArray(firstProduct.product_features)
              ? firstProduct.product_features.join('\n')
              : firstProduct.product_features || '',
          })
          message.success(`已从牛顿选品导入${batchData.products.length}个商品，正在处理第1个`)
          // 清除已读取的批量数据
          localStorage.removeItem('product_pipeline_batch')
        }
      } catch (e) {
        console.error('Parse saved batch error:', e)
      }
    }
  }, [])

  // 从1688导入商品信息
  const handleImportFrom1688 = async () => {
    if (!importUrl || importUrl.trim().length === 0) {
      message.error('请输入1688商品URL或商品ID')
      return
    }

    try {
      setImportLoading(true)
      const resp = await fetch('/api/v1/product-pipeline/import-from-1688', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url_or_id: importUrl.trim(),
          auto_run_pipeline: autoRunPipeline,
          auto_list: false,
        }),
      })

      const result = await resp.json()

      if (result.success && result.data?.product_info) {
        const productInfo = result.data.product_info
        form.setFieldsValue({
          name: productInfo.name || '',
          category: productInfo.category || '',
          price: productInfo.price || '',
          description: productInfo.description || '',
          core_selling_points: Array.isArray(productInfo.core_selling_points)
            ? productInfo.core_selling_points.join('\n')
            : productInfo.core_selling_points || '',
          target_audience: productInfo.target_audience || '',
          usage_scenarios: Array.isArray(productInfo.usage_scenarios)
            ? productInfo.usage_scenarios.join('\n')
            : productInfo.usage_scenarios || '',
          product_features: Array.isArray(productInfo.product_features)
            ? productInfo.product_features.join('\n')
            : productInfo.product_features || '',
        })

        message.success(`已从1688导入商品：${productInfo.name || '未知商品'}（SKU: ${productInfo.sku || '未生成'}，图片: ${productInfo.images?.length || 0}张）`)

        // 如果自动运行工作流
        if (autoRunPipeline && result.data?.pipeline_result) {
          setPipelineResult(result.data.pipeline_result)
          message.info('工作流已自动运行完成')
        }

        setImportUrl('')
      } else {
        message.error(`导入失败：${result.error || '未知错误'}`)
      }
    } catch (e: any) {
      console.error('Import from 1688 error:', e)
      message.error(`导入失败：${e.message || '网络错误'}`)
    } finally {
      setImportLoading(false)
    }
  }

  // 运行工作流
  const handleRunPipeline = async () => {
    try {
      const values = await form.validateFields()
      if (!values.name || values.name.trim().length === 0) {
        message.error('请输入商品名称')
        return
      }

      setLoading(true)
      setPipelineResult(null)

      const productInfo = {
        name: values.name,
        category: values.category || '',
        price: values.price || '',
        description: values.description || '',
        core_selling_points: values.core_selling_points?.split('\n').filter(Boolean) || [],
        target_audience: values.target_audience || '',
        usage_scenarios: values.usage_scenarios?.split('\n').filter(Boolean) || [],
        product_features: values.product_features?.split('\n').filter(Boolean) || [],
      }

      const resp = await fetch('/api/v1/product-pipeline/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          product_info: productInfo,
          auto_list: false,
          include_images: false,
        }),
      })
      const data = await resp.json()

      if (data.success || data.data) {
        setPipelineResult(data)
        setHistory(prev => [data, ...prev].slice(0, 10))
        message.success(`工作流完成：${data.data?.completed_steps || 0}/${data.data?.total_steps || 6}步成功`)
      } else {
        message.error(data.error || '工作流执行失败')
      }
    } catch (e: any) {
      message.error(e.message || '工作流执行失败')
    } finally {
      setLoading(false)
    }
  }

  // 确认上架
  const handleConfirmListing = async (status: string = 'publish') => {
    if (!pipelineResult) return

    try {
      setListingLoading(true)
      const resp = await fetch('/api/v1/product-pipeline/confirm-list', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pipeline_result: pipelineResult,
          status: status,
        }),
      })
      const data = await resp.json()

      if (data.success) {
        message.success(`上架成功！WooCommerce ID: ${data.data?.woocommerce_id}`)
        setListingModalOpen(false)
        // 更新工作流结果中的上架状态
        setPipelineResult(prev => prev ? {
          ...prev,
          data: {
            ...prev.data,
            steps: {
              ...prev.data.steps,
              listing: { status: 'completed', data: data.data }
            }
          }
        } : null)
      } else {
        message.error(data.error || '上架失败')
      }
    } catch (e: any) {
      message.error(e.message || '上架失败')
    } finally {
      setListingLoading(false)
    }
  }

  // 获取步骤状态
  const getStepStatus = (stepId: string) => {
    if (!pipelineResult) return 'wait'
    const step = pipelineResult.data?.steps?.[stepId]
    if (!step) return 'wait'
    switch (step.status) {
      case 'completed': return 'finish'
      case 'failed': return 'error'
      case 'running': return 'process'
      case 'pending_confirmation': return 'wait'
      case 'skipped': return 'wait'
      default: return 'wait'
    }
  }

  // 获取步骤状态颜色
  const getStepColor = (stepId: string) => {
    if (!pipelineResult) return 'default'
    const step = pipelineResult.data?.steps?.[stepId]
    if (!step) return 'default'
    switch (step.status) {
      case 'completed': return 'green'
      case 'failed': return 'red'
      case 'running': return 'blue'
      case 'pending_confirmation': return 'orange'
      default: return 'default'
    }
  }

  // 获取上架数据
  const getListingData = () => {
    return pipelineResult?.data?.steps?.listing_data?.data || null
  }

  // 复制文本
  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text)
    message.success('已复制')
  }

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: '24px' }}>
        <Space>
          <RocketOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>产品端到端工作流</Title>
            <Text type="secondary">选品 → AI分析 → 主图生产 → 生图Prompt → 上架数据 → WooCommerce上架</Text>
          </div>
        </Space>
      </div>

      <Spin spinning={loading} tip="AI正在处理，请稍候...">
        <Row gutter={[24, 24]}>
          {/* 左侧：商品信息输入 */}
          <Col xs={24} lg={8}>
            {/* 批量处理提示 */}
            {batchQueue.length > 0 && (
              <Alert
                message={`批量处理中：第 ${currentBatchIndex + 1}/${batchQueue.length} 个商品`}
                description={
                  <Space>
                    <Progress percent={Math.round((currentBatchIndex / batchQueue.length) * 100)} size="small" style={{ width: '150px' }} />
                    <Button size="small" onClick={() => {
                      if (currentBatchIndex < batchQueue.length - 1) {
                        const nextIndex = currentBatchIndex + 1
                        const nextProduct = batchQueue[nextIndex]
                        setCurrentBatchIndex(nextIndex)
                        form.setFieldsValue({
                          name: nextProduct.name || '',
                          category: nextProduct.category || '',
                          price: nextProduct.price || '',
                          description: nextProduct.description || '',
                          core_selling_points: Array.isArray(nextProduct.core_selling_points)
                            ? nextProduct.core_selling_points.join('\n')
                            : nextProduct.core_selling_points || '',
                          target_audience: nextProduct.target_audience || '',
                          usage_scenarios: Array.isArray(nextProduct.usage_scenarios)
                            ? nextProduct.usage_scenarios.join('\n')
                            : nextProduct.usage_scenarios || '',
                          product_features: Array.isArray(nextProduct.product_features)
                            ? nextProduct.product_features.join('\n')
                            : nextProduct.product_features || '',
                        })
                        setPipelineResult(null)
                        setGeneratedImages([])
                        message.success(`已切换到第 ${nextIndex + 1} 个商品`)
                      } else {
                        message.success('批量处理完成！')
                        setBatchQueue([])
                        setCurrentBatchIndex(0)
                      }
                    }} disabled={currentBatchIndex >= batchQueue.length}>
                      {currentBatchIndex < batchQueue.length - 1 ? '下一个商品' : '完成批量处理'}
                    </Button>
                  </Space>
                }
                type="info"
                showIcon
                style={{ marginBottom: '16px' }}
              />
            )}
            <Card title="商品信息输入" size="small" extra={<Button size="small" type="primary" icon={<PlayCircleOutlined />} onClick={handleRunPipeline} loading={loading}>一键运行</Button>}>
              {/* 1688一键导入 */}
              <div style={{ marginBottom: '16px', padding: '12px', background: '#f6f8fa', borderRadius: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', marginBottom: '8px' }}>
                  <ThunderboltOutlined style={{ color: '#1890ff', marginRight: '8px' }} />
                  <Text strong style={{ fontSize: '13px' }}>1688一键导入</Text>
                  <Tag color="blue" style={{ marginLeft: '8px' }}>新功能</Tag>
                </div>
                <Space.Compact style={{ width: '100%', marginBottom: '8px' }}>
                  <Input
                    placeholder="输入1688商品URL或商品ID，例如：https://detail.1688.com/offer/123456789.html"
                    value={importUrl}
                    onChange={(e) => setImportUrl(e.target.value)}
                    onPressEnter={handleImportFrom1688}
                    allowClear
                  />
                  <Button
                    type="primary"
                    icon={<ThunderboltOutlined />}
                    onClick={handleImportFrom1688}
                    loading={importLoading}
                  >
                    导入
                  </Button>
                </Space.Compact>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Switch
                    size="small"
                    checked={autoRunPipeline}
                    onChange={setAutoRunPipeline}
                    checkedChildren="自动运行"
                    unCheckedChildren="仅导入"
                  />
                  <Text type="secondary" style={{ fontSize: '11px' }}>
                    自动获取商品名称/价格/描述/图片/属性，转换为工作流输入格式
                  </Text>
                </div>
              </div>

              <Form form={form} layout="vertical" size="small">
                <Form.Item name="name" label="商品名称 *" rules={[{ required: true, message: '请输入商品名称' }]}>
                  <Input placeholder="例如：便携榨汁杯" />
                </Form.Item>

                <Form.Item name="category" label="商品类目">
                  <Select options={CATEGORY_OPTIONS} placeholder="选择类目" allowClear />
                </Form.Item>

                <Form.Item name="price" label="1688采购价">
                  <Input placeholder="例如：¥29.9" />
                </Form.Item>

                <Form.Item name="description" label="商品描述">
                  <TextArea rows={3} placeholder="商品简短描述" />
                </Form.Item>

                <Form.Item name="core_selling_points" label="核心卖点（每行一个）">
                  <TextArea rows={3} placeholder={'便携易带\n一杯刚刚好\n拆洗方便'} />
                </Form.Item>

                <Form.Item name="target_audience" label="目标人群">
                  <Input placeholder="例如：25-35岁都市白领" />
                </Form.Item>

                <Form.Item name="usage_scenarios" label="使用场景（每行一个）">
                  <TextArea rows={2} placeholder={'办公室\n健身房\n户外'} />
                </Form.Item>

                <Form.Item name="product_features" label="产品功能（每行一个）">
                  <TextArea rows={2} placeholder={'USB充电\n300ml容量\n食品级材质'} />
                </Form.Item>
              </Form>
            </Card>

            {/* 使用说明 */}
            <Card title="工作流说明" size="small" style={{ marginTop: '16px' }}>
              <ol style={{ paddingLeft: '20px', margin: 0, fontSize: '13px', lineHeight: '2' }}>
                <li><b>商品信息</b>：输入或从牛顿选品结果导入商品信息</li>
                <li><b>AI产品分析</b>：自动识别10个字段，生成17字段产品报告</li>
                <li><b>主图生产</b>：生成3套主图方向、短文案、10个变体</li>
                <li><b>生图Prompt</b>：生成主图和详情页的完整生图Prompt</li>
                <li><b>上架数据</b>：自动生成名称、描述、价格、SKU、分类、标签</li>
                <li><b>上架WC</b>：人工确认后上架到WooCommerce（默认草稿）</li>
              </ol>
              <Alert
                message="Human-in-the-loop：上架前必须人工确认，不会自动发布"
                type="info"
                showIcon
                style={{ marginTop: '12px' }}
              />
            </Card>
          </Col>

          {/* 右侧：工作流结果 */}
          <Col xs={24} lg={16}>
            {/* 工作流进度 */}
            <Card title="工作流进度" size="small" style={{ marginBottom: '16px' }}>
              {pipelineResult ? (
                <>
                  <Row gutter={[16, 16]} style={{ marginBottom: '16px' }}>
                    <Col span={6}>
                      <Statistic title="完成步骤" value={`${pipelineResult.data.completed_steps}/${pipelineResult.data.total_steps}`} />
                    </Col>
                    <Col span={6}>
                      <Statistic title="进度" value={pipelineResult.data.progress} suffix="%" />
                    </Col>
                    <Col span={6}>
                      <Statistic title="耗时" value={pipelineResult.data.elapsed_time_seconds} suffix="秒" />
                    </Col>
                    <Col span={6}>
                      <Statistic title="状态" value={pipelineResult.data.status === 'completed' ? '成功' : pipelineResult.data.status === 'partial' ? '部分成功' : '失败'} valueStyle={{ color: pipelineResult.data.status === 'completed' ? '#52c41a' : pipelineResult.data.status === 'partial' ? '#faad14' : '#ff4d4f' }} />
                    </Col>
                  </Row>

                  <Progress percent={pipelineResult.data.progress} status={pipelineResult.data.status === 'completed' ? 'success' : pipelineResult.data.status === 'failed' ? 'exception' : 'active'} />

                  <Steps direction="vertical" size="small" style={{ marginTop: '24px' }} current={pipelineResult.data.completed_steps}>
                    {PIPELINE_STEPS.map((step, index) => {
                      const StepIcon = step.icon
                      const status = getStepStatus(step.id)
                      const stepData = pipelineResult.data.steps?.[step.id]
                      return (
                        <Step
                          key={step.id}
                          title={<Space><StepIcon /> {step.title} <Tag color={getStepColor(step.id)}>{stepData?.status || 'wait'}</Tag></Space>}
                          description={step.description}
                          status={status}
                        />
                      )
                    })}
                  </Steps>

                  {pipelineResult.data.errors?.length > 0 && (
                    <Alert
                      message={`${pipelineResult.data.errors.length}个错误`}
                      description={pipelineResult.data.errors.map((e, i) => <div key={i}>{e}</div>)}
                      type="warning"
                      showIcon
                      style={{ marginTop: '16px' }}
                    />
                  )}
                </>
              ) : (
                <Empty description="请在左侧输入商品信息并点击'一键运行'" />
              )}
            </Card>

            {/* 结果详情 */}
            {pipelineResult && (
              <Tabs
                defaultActiveKey="listing"
                items={[
                  {
                    key: 'listing',
                    label: '上架数据',
                    children: (
                      <Card size="small" title="上架数据预览" extra={
                        <Space>
                          <Button size="small" icon={<CopyOutlined />} onClick={() => handleCopy(JSON.stringify(getListingData(), null, 2))}>复制JSON</Button>
                          <Button size="small" type="primary" icon={<ShopOutlined />} onClick={() => setListingModalOpen(true)} disabled={!getListingData()}>确认上架</Button>
                        </Space>
                      }>
                        {getListingData() ? (
                          <Descriptions column={2} size="small" bordered>
                            <Descriptions.Item label="商品名称" span={2}>{getListingData().name}</Descriptions.Item>
                            <Descriptions.Item label="SKU">{getListingData().sku}</Descriptions.Item>
                            <Descriptions.Item label="售价">${getListingData().regular_price || '待设置'}</Descriptions.Item>
                            <Descriptions.Item label="库存">{getListingData().stock_quantity}</Descriptions.Item>
                            <Descriptions.Item label="状态">{getListingData().status === 'draft' ? '草稿' : getListingData().status}</Descriptions.Item>
                            <Descriptions.Item label="分类" span={2}>{getListingData().categories?.map((c: any) => c.id).join(', ')}</Descriptions.Item>
                            <Descriptions.Item label="标签" span={2}>{getListingData().tags?.map((t: any) => t.name).join(', ') || '无'}</Descriptions.Item>
                            <Descriptions.Item label="短描述" span={2}><Paragraph ellipsis={{ rows: 2 }} style={{ margin: 0 }}>{getListingData().short_description}</Paragraph></Descriptions.Item>
                            <Descriptions.Item label="完整描述" span={2}><Paragraph ellipsis={{ rows: 4 }} style={{ margin: 0 }}>{getListingData().description}</Paragraph></Descriptions.Item>
                          </Descriptions>
                        ) : (
                          <Empty description="无上架数据" />
                        )}
                      </Card>
                    ),
                  },
                  {
                    key: 'analysis',
                    label: '产品分析',
                    children: (
                      <Card size="small" title="AI产品分析结果">
                        {pipelineResult.data.steps?.analysis?.data?.product_report ? (
                          <Descriptions column={2} size="small" bordered>
                            <Descriptions.Item label="产品名称" span={2}>{pipelineResult.data.steps.analysis.data.product_report.product_name}</Descriptions.Item>
                            <Descriptions.Item label="产品类目">{pipelineResult.data.steps.analysis.data.product_report.product_category}</Descriptions.Item>
                            <Descriptions.Item label="目标人群">{pipelineResult.data.steps.analysis.data.product_report.target_audience}</Descriptions.Item>
                            <Descriptions.Item label="核心卖点" span={2}>{pipelineResult.data.steps.analysis.data.product_report.core_selling_points?.join('、')}</Descriptions.Item>
                            <Descriptions.Item label="使用场景" span={2}>{pipelineResult.data.steps.analysis.data.product_report.usage_scenarios?.join('、')}</Descriptions.Item>
                            <Descriptions.Item label="产品功能" span={2}>{pipelineResult.data.steps.analysis.data.product_report.product_features?.join('、')}</Descriptions.Item>
                          </Descriptions>
                        ) : (
                          <Empty description="无分析结果" />
                        )}
                      </Card>
                    ),
                  },
                  {
                    key: 'main_image',
                    label: '主图生产',
                    children: (
                      <Card size="small" title="主图生产结果">
                        {pipelineResult.data.steps?.main_image?.data ? (
                          <>
                            <Row gutter={[16, 16]}>
                              {pipelineResult.data.steps.main_image.data.directions?.map((dir: any, i: number) => (
                                <Col span={8} key={i}>
                                  <Card size="small" title={dir.name}>
                                    <Paragraph ellipsis={{ rows: 3 }} style={{ margin: 0, fontSize: '12px' }}>{dir.prompt}</Paragraph>
                                  </Card>
                                </Col>
                              ))}
                            </Row>
                            <Divider style={{ margin: '16px 0' }} />
                            <Text type="secondary">变体数量：{pipelineResult.data.steps.main_image.data.variants?.length || 0}</Text>
                          </>
                        ) : (
                          <Empty description="无主图结果" />
                        )}
                      </Card>
                    ),
                  },
                  {
                    key: 'prompt',
                    label: '生图Prompt',
                    children: (
                      <Card size="small" title="生图Prompt" extra={
                        <Space>
                          <Button size="small" type="primary" icon={<ThunderboltOutlined />} onClick={handleGenerateImage} loading={generatingImage} disabled={!pipelineResult.data.steps?.prompt?.data}>
                            一键生图
                          </Button>
                          <Button size="small" icon={<PictureOutlined />} onClick={() => {
                            const promptData = {
                              main_prompt: pipelineResult.data.steps?.prompt?.data?.main_image_prompt || '',
                              detail_prompt: pipelineResult.data.steps?.prompt?.data?.detail_image_prompt || '',
                              product_name: pipelineResult.data.product_name || '',
                              source: 'product_pipeline',
                              timestamp: new Date().toISOString(),
                            }
                            localStorage.setItem('image_studio_prompt', JSON.stringify(promptData))
                            message.success('Prompt已发送到生图工作台，正在跳转...')
                            setTimeout(() => {
                              window.location.hash = '#/image-studio'
                            }, 500)
                          }} disabled={!pipelineResult.data.steps?.prompt?.data}>
                            发送到生图工作台
                          </Button>
                        </Space>
                      }>
                        {pipelineResult.data.steps?.prompt?.data ? (
                          <>
                            <Collapse
                              items={[
                                {
                                  key: 'main',
                                  label: '主图Prompt',
                                  children: (
                                    <div>
                                      <Button size="small" icon={<CopyOutlined />} onClick={() => handleCopy(pipelineResult.data.steps.prompt.data.main_image_prompt)} style={{ marginBottom: '8px' }}>复制</Button>
                                      <Paragraph style={{ whiteSpace: 'pre-wrap', fontSize: '12px', background: '#f5f5f5', padding: '12px', borderRadius: '4px' }}>{pipelineResult.data.steps.prompt.data.main_image_prompt}</Paragraph>
                                    </div>
                                  ),
                                },
                                {
                                  key: 'detail',
                                  label: '详情页Prompt',
                                  children: (
                                    <div>
                                      <Button size="small" icon={<CopyOutlined />} onClick={() => handleCopy(pipelineResult.data.steps.prompt.data.detail_image_prompt)} style={{ marginBottom: '8px' }}>复制</Button>
                                      <Paragraph style={{ whiteSpace: 'pre-wrap', fontSize: '12px', background: '#f5f5f5', padding: '12px', borderRadius: '4px' }}>{pipelineResult.data.steps.prompt.data.detail_image_prompt}</Paragraph>
                                    </div>
                                  ),
                                },
                              ]}
                            />
                            {/* 生成的图片预览 */}
                            {generatedImages.length > 0 && (
                              <>
                                <Divider style={{ margin: '16px 0' }} />
                                <div>
                                  <Text strong>已生成图片（{generatedImages.length}张，已自动回填到上架数据）：</Text>
                                  <Row gutter={[16, 16]} style={{ marginTop: '12px' }}>
                                    {generatedImages.map((url, i) => (
                                      <Col span={8} key={i}>
                                        <img
                                          src={url}
                                          alt={`Generated ${i + 1}`}
                                          style={{ width: '100%', height: '150px', objectFit: 'cover', borderRadius: '8px', cursor: 'pointer' }}
                                          onClick={() => window.open(url, '_blank')}
                                        />
                                      </Col>
                                    ))}
                                  </Row>
                                </div>
                              </>
                            )}
                            {generatingImage && (
                              <div style={{ textAlign: 'center', padding: '20px' }}>
                                <Spin size="large" />
                                <Paragraph type="secondary" style={{ marginTop: '8px' }}>AI正在生成主图，请稍候...</Paragraph>
                              </div>
                            )}
                          </>
                        ) : (
                          <Empty description="无Prompt结果，请先运行工作流" />
                        )}
                      </Card>
                    ),
                  },
                ]}
              />
            )}

            {/* 历史记录 */}
            {history.length > 0 && (
              <Card title="历史记录" size="small" style={{ marginTop: '16px' }}>
                <List
                  size="small"
                  dataSource={history}
                  renderItem={(item, index) => (
                    <List.Item
                      actions={[
                        <Tag color={item.data.status === 'completed' ? 'green' : item.data.status === 'partial' ? 'orange' : 'red'} key="status">{item.data.status}</Tag>,
                        <Text type="secondary" key="time" style={{ fontSize: '12px' }}>{item.data.elapsed_time_seconds}s</Text>,
                      ]}
                    >
                      <List.Item.Meta
                        avatar={<Badge count={index + 1} />}
                        title={<Text ellipsis style={{ maxWidth: '300px' }}>{item.data.product_name}</Text>}
                        description={<Text type="secondary" style={{ fontSize: '12px' }}>SKU: {item.data.sku} | {item.data.completed_steps}/{item.data.total_steps}步</Text>}
                      />
                    </List.Item>
                  )}
                />
              </Card>
            )}
          </Col>
        </Row>
      </Spin>

      {/* 上架确认Modal */}
      <Modal
        title="确认上架到WooCommerce"
        open={listingModalOpen}
        onCancel={() => setListingModalOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setListingModalOpen(false)}>取消</Button>,
          <Button key="draft" onClick={() => handleConfirmListing('draft')} loading={listingLoading}>保存为草稿</Button>,
          <Button key="publish" type="primary" onClick={() => handleConfirmListing('publish')} loading={listingLoading}>直接发布</Button>,
        ]}
      >
        <Alert
          message="上架确认"
          description="即将将以下商品上架到WooCommerce。请确认商品信息无误后选择上架方式。"
          type="warning"
          showIcon
          style={{ marginBottom: '16px' }}
        />
        {getListingData() && (
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="商品名称">{getListingData().name}</Descriptions.Item>
            <Descriptions.Item label="SKU">{getListingData().sku}</Descriptions.Item>
            <Descriptions.Item label="售价">${getListingData().regular_price || '待设置'}</Descriptions.Item>
            <Descriptions.Item label="库存">{getListingData().stock_quantity}</Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </div>
  )
}
