import { useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Descriptions,
  Divider,
  Empty,
  Form,
  Input,
  List,
  Progress,
  Row,
  Select,
  Space,
  Spin,
  Steps,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  CodeOutlined,
  CopyOutlined,
  DeleteOutlined,
  FileTextOutlined,
  LinkOutlined,
  LoadingOutlined,
  ReloadOutlined,
  RobotOutlined,
  StarOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { api, request } from '../api/client'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

const MAX_BATCH_SIZE = 20
const IMPORT_CONCURRENCY = 3
const IMPORT_JOB_TIMEOUT_MS = 20 * 60 * 1000
const IMPORT_JOB_POLL_MS = 3000

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

type ImportStatus = 'pending' | 'importing' | 'success' | 'error'

interface ImportedProductItem {
  id: string
  source: string
  status: ImportStatus
  productId?: string
  candidateProductId?: string
  productName?: string
  dataSource?: string
  productInfo?: Record<string, any>
  aiRecognition?: Record<string, any>
  productReport?: Record<string, any>
  analysisMetadata?: Record<string, any>
  error?: string
}

interface StandardResponse<T> {
  success: boolean
  data: T | null
  error?: string | null
}

interface ImportAndAnalyzeData {
  import_id: string
  product_id: string
  source_url: string
  data_source?: string
  product_info: Record<string, any>
  ai_recognition: Record<string, any>
  product_report: Record<string, any>
  analysis_metadata?: Record<string, any>
}

export function parse1688Sources(raw: string): string[] {
  const candidates = raw.match(/https?:\/\/[^\s,，;；]+|\b\d{8,}\b/g) || []
  const seen = new Set<string>()
  const result: string[] = []

  for (const candidate of candidates) {
    const source = candidate.replace(/[)\]}>，。；;]+$/g, '')
    const productId = (
      source.match(/\/offer\/(\d+)\.html/i)
      || source.match(/offerId=(\d+)/i)
      || source.match(/offer\/(\d+)/i)
      || source.match(/^(\d{8,})$/)
    )?.[1]
    const key = productId || source
    if (!seen.has(key)) {
      seen.add(key)
      result.push(source)
    }
  }

  return result
}

function normalizeManualValues(values: Record<string, any>): Record<string, any> {
  const images = Array.isArray(values.images)
    ? values.images
    : String(values.images || '')
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean)

  return {
    ...values,
    images,
  }
}

function normalizeAttributeMap(value: unknown): Record<string, unknown> {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>
  }
  if (!Array.isArray(value)) return {}
  return value.reduce<Record<string, unknown>>((attributes, item) => {
    if (!item || typeof item !== 'object') return attributes
    const record = item as Record<string, unknown>
    const key = textValue(record.name || record.key || record.attributeName)
    const attributeValue = record.value ?? record.option ?? record.attributeValue
    if (key && attributeValue !== undefined) {
      attributes[key] = attributeValue
    }
    return attributes
  }, {})
}

function statusTag(status: ImportStatus) {
  if (status === 'success') return <Tag color="success" icon={<CheckCircleOutlined />}>已完成</Tag>
  if (status === 'error') return <Tag color="error" icon={<CloseCircleOutlined />}>失败</Tag>
  if (status === 'importing') return <Tag color="processing" icon={<LoadingOutlined />}>分析中</Tag>
  return <Tag>待处理</Tag>
}

function dataSourceTag(source?: string) {
  if (source === '1688_open_api') return <Tag color="blue">1688 开放平台</Tag>
  if (source === 'newton_agent') return <Tag color="geekblue">牛顿 Agent</Tag>
  return null
}

function textValue(value: unknown, fallback = ''): string {
  if (value === null || value === undefined) return fallback
  return String(value).trim()
}

function numericValue(value: unknown): number {
  const match = String(value ?? '').replace(/,/g, '').match(/\d+(?:\.\d+)?/)
  if (!match) return 0
  const parsed = Number(match[0])
  return Number.isFinite(parsed) ? parsed : 0
}

function sourceUrlValue(value: string | null | undefined): string | undefined {
  const source = textValue(value)
  if (!source) return undefined
  if (/^https?:\/\//i.test(source)) return source.slice(0, 512)
  if (/^\d{8,}$/.test(source)) {
    return `https://detail.1688.com/offer/${source}.html`
  }
  return undefined
}

export default function ProductAnalysis() {
  const navigate = useNavigate()
  const [currentStep, setCurrentStep] = useState(0)
  const [loading, setLoading] = useState(false)
  const [importing, setImporting] = useState(false)
  const [progress, setProgress] = useState(0)
  const [sourceText, setSourceText] = useState('')
  const [importItems, setImportItems] = useState<ImportedProductItem[]>([])
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null)
  const [form] = Form.useForm()

  const [productInfo, setProductInfo] = useState<Record<string, any> | null>(null)
  const [aiRecognition, setAiRecognition] = useState<Record<string, any> | null>(null)
  const [productReport, setProductReport] = useState<Record<string, any> | null>(null)
  const [generatedPrompt, setGeneratedPrompt] = useState<Record<string, any> | null>(null)
  const [batchPrompts, setBatchPrompts] = useState<Record<string, any> | null>(null)
  const [selectedPageType, setSelectedPageType] = useState('brand_scene')
  const [candidateSubmitting, setCandidateSubmitting] = useState<string | null>(null)
  const [currentCandidateId, setCurrentCandidateId] = useState<string | null>(null)

  const parsedSources = useMemo(() => parse1688Sources(sourceText), [sourceText])
  const successCount = importItems.filter((item) => item.status === 'success').length
  const errorCount = importItems.filter((item) => item.status === 'error').length
  const selectedItem = importItems.find((item) => item.id === selectedItemId) || null

  const clearGeneratedContent = () => {
    setGeneratedPrompt(null)
    setBatchPrompts(null)
  }

  const applyImportedItem = (item: ImportedProductItem) => {
    setSelectedItemId(item.id)
    setCurrentCandidateId(item.candidateProductId || null)
    setProductInfo(item.productInfo || null)
    setAiRecognition(item.aiRecognition || null)
    setProductReport(item.productReport || null)
    clearGeneratedContent()
    setCurrentStep(item.productReport ? 2 : item.aiRecognition ? 1 : 0)
  }

  const updateImportItem = (nextItem: ImportedProductItem) => {
    setImportItems((items) => items.map((item) => (
      item.id === nextItem.id ? nextItem : item
    )))
  }

  const runImportItem = async (source: string, id: string): Promise<ImportedProductItem> => {
    updateImportItem({ id, source, status: 'importing' })

    try {
      const submitted = await api.createImportAndAnalyzeFrom1688Job({
        url_or_id: source,
        temperature: 0.3,
        max_tokens: 2000,
      })
      if (!submitted.success || !submitted.data) {
        const failedItem: ImportedProductItem = {
          id,
          source,
          status: 'error',
          error: submitted.error || '无法提交导入任务',
        }
        updateImportItem(failedItem)
        return failedItem
      }

      const deadline = Date.now() + IMPORT_JOB_TIMEOUT_MS
      let completedData: ImportAndAnalyzeData | null = null
      let completedError = ''

      while (Date.now() < deadline) {
        await new Promise((resolve) => window.setTimeout(resolve, IMPORT_JOB_POLL_MS))
        const jobResponse = await api.getImportAndAnalyzeFrom1688Job(submitted.data.job_id)
        const job = jobResponse.data
        if (!jobResponse.success || !job) {
          completedError = jobResponse.error || '无法读取导入任务状态'
          break
        }
        if (job.status === 'succeeded') {
          completedData = job.data as ImportAndAnalyzeData | null
          break
        }
        if (job.status === 'failed') {
          completedError = job.error || '导入或分析失败'
          break
        }
      }

      if (!completedData) {
        const failedItem: ImportedProductItem = {
          id,
          source,
          status: 'error',
          error: completedError || '导入任务超时，请重试',
        }
        updateImportItem(failedItem)
        return failedItem
      }

      const completedItem: ImportedProductItem = {
        id,
        source,
        status: 'success',
        productId: completedData.product_id,
        productName: completedData.product_info?.name || completedData.product_report?.product_name,
        dataSource: completedData.data_source,
        productInfo: completedData.product_info,
        aiRecognition: completedData.ai_recognition,
        productReport: completedData.product_report,
        analysisMetadata: completedData.analysis_metadata,
      }
      updateImportItem(completedItem)
      return completedItem
    } catch (error: any) {
      const failedItem: ImportedProductItem = {
        id,
        source,
        status: 'error',
        error: error?.message || '网络请求失败',
      }
      updateImportItem(failedItem)
      return failedItem
    }
  }

  const handleImportSources = async () => {
    if (parsedSources.length === 0) {
      message.warning('请粘贴至少一个 1688 商品链接或商品 ID')
      return
    }

    const sources = parsedSources.slice(0, MAX_BATCH_SIZE)
    if (parsedSources.length > MAX_BATCH_SIZE) {
      message.warning(`单次最多处理 ${MAX_BATCH_SIZE} 条，已自动保留前 ${MAX_BATCH_SIZE} 条`)
    }

    const initialItems = sources.map((source, index) => ({
      id: `${Date.now()}-${index}`,
      source,
      status: 'pending' as const,
    }))
    setImportItems(initialItems)
    setSelectedItemId(null)
    setCurrentCandidateId(null)
    setProductInfo(null)
    setAiRecognition(null)
    setProductReport(null)
    clearGeneratedContent()
    setCurrentStep(0)
    setProgress(0)
    setImporting(true)

    let firstSuccess: ImportedProductItem | null = null
    let succeeded = 0
    let completed = 0
    let nextIndex = 0

    const worker = async () => {
      while (nextIndex < initialItems.length) {
        const index = nextIndex
        nextIndex += 1
        const seeded = initialItems[index]
        const result = await runImportItem(seeded.source, seeded.id)
        completed += 1
        if (result.status === 'success') {
          succeeded += 1
          if (!firstSuccess) firstSuccess = result
        }
        setProgress(Math.round((completed / initialItems.length) * 100))
      }
    }

    await Promise.all(
      Array.from(
        { length: Math.min(IMPORT_CONCURRENCY, initialItems.length) },
        () => worker(),
      ),
    )

    if (firstSuccess) applyImportedItem(firstSuccess)
    setImporting(false)

    if (succeeded === initialItems.length) {
      message.success(`${succeeded} 条商品已完成导入、AI分析和产品报告`)
    } else {
      message.warning(`处理完成：成功 ${succeeded} 条，失败 ${initialItems.length - succeeded} 条`)
    }
  }

  const handleRetryItem = async (item: ImportedProductItem) => {
    setImporting(true)
    const result = await runImportItem(item.source, item.id)
    if (result.status === 'success') applyImportedItem(result)
    setImporting(false)
  }

  const handleAnalyze = async () => {
    try {
      const values = normalizeManualValues(await form.validateFields())
      setLoading(true)
      setProductInfo(values)
      setCurrentCandidateId(null)

      const data = await request<StandardResponse<{
        ai_recognition: Record<string, any>
      }>>('/product-analysis/analyze', {
        method: 'POST',
        body: JSON.stringify(values),
        timeoutMs: 120000,
      })
      if (data.success && data.data) {
        setAiRecognition(data.data.ai_recognition)
        setProductReport(null)
        clearGeneratedContent()
        setCurrentStep(1)
        message.success('AI产品分析完成')
      } else {
        message.error(data.error || '分析失败')
      }
    } catch (error: any) {
      message.error(error?.message || '分析失败')
    } finally {
      setLoading(false)
    }
  }

  const handleGenerateReport = async () => {
    if (!productInfo || !aiRecognition) return

    try {
      setLoading(true)
      const data = await request<StandardResponse<{
        product_report: Record<string, any>
      }>>('/product-analysis/report', {
        method: 'POST',
        body: JSON.stringify({
          product_info: productInfo,
          ai_recognition: aiRecognition,
        }),
        timeoutMs: 120000,
      })
      if (data.success && data.data) {
        setProductReport(data.data.product_report)
        setCurrentStep(2)
        message.success('产品信息报告生成完成')
      } else {
        message.error(data.error || '报告生成失败')
      }
    } catch (error: any) {
      message.error(error?.message || '报告生成失败')
    } finally {
      setLoading(false)
    }
  }

  const handleAnalyzeAndReport = async () => {
    try {
      const values = normalizeManualValues(await form.validateFields())
      setLoading(true)
        setProductInfo(values)
        setCurrentCandidateId(null)

      const data = await request<StandardResponse<{
        ai_recognition: Record<string, any>
        product_report: Record<string, any>
      }>>('/product-analysis/analyze-and-report', {
        method: 'POST',
        body: JSON.stringify({ product_info: values }),
        timeoutMs: 180000,
      })
      if (data.success && data.data) {
        setAiRecognition(data.data.ai_recognition)
        setProductReport(data.data.product_report)
        clearGeneratedContent()
        setCurrentStep(2)
        message.success('分析+报告一键完成')
      } else {
        message.error(data.error || '失败')
      }
    } catch (error: any) {
      message.error(error?.message || '失败')
    } finally {
      setLoading(false)
    }
  }

  const handleGeneratePrompt = async () => {
    if (!productReport) return

    try {
      setLoading(true)
      const data = await request<StandardResponse<Record<string, any>>>('/product-analysis/prompt', {
        method: 'POST',
        body: JSON.stringify({
          product_report: productReport,
          page_type: selectedPageType,
        }),
      })
      if (data.success && data.data) {
        setGeneratedPrompt(data.data)
        setCurrentStep(3)
        message.success('Prompt生成完成')
      } else {
        message.error(data.error || 'Prompt生成失败')
      }
    } catch (error: any) {
      message.error(error?.message || 'Prompt生成失败')
    } finally {
      setLoading(false)
    }
  }

  const handleBatchPrompts = async () => {
    if (!productReport) return

    try {
      setLoading(true)
      const data = await request<StandardResponse<Record<string, any>>>('/product-analysis/batch-prompts', {
        method: 'POST',
        body: JSON.stringify({ product_report: productReport }),
      })
      if (data.success && data.data) {
        setBatchPrompts(data.data)
        message.success(`批量生成${data.data.count}个Prompt完成`)
      } else {
        message.error(data.error || '批量生成失败')
      }
    } catch (error: any) {
      message.error(error?.message || '批量生成失败')
    } finally {
      setLoading(false)
    }
  }

  const handleCopyPrompt = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      message.success('Prompt已复制到剪贴板')
    } catch {
      message.error('复制失败，请手动选择文本')
    }
  }

  const addCandidate = async (
    source: {
      key: string
      title?: unknown
      category?: unknown
      description?: unknown
      sourceUrl?: string | null
      sourceType?: '1688' | 'MANUAL' | 'OTHER'
      price?: unknown
      weight?: unknown
      dimensions?: unknown
      images?: unknown
      attributes?: unknown
      supplierName?: unknown
      sourceId?: unknown
      aiRecognition?: Record<string, any>
      productReport?: Record<string, any>
    },
    importedItemId?: string,
  ) => {
    const title = textValue(source.title)
    if (!title) {
      message.warning('缺少商品名称，无法加入候选池')
      return
    }

    setCandidateSubmitting(source.key)
    try {
      const result = (await api.intakeProduct({
        title: title.slice(0, 255),
        description: textValue(source.description).slice(0, 2000) || title,
        category: textValue(source.category).slice(0, 128) || undefined,
        source_type: source.sourceType || 'MANUAL',
        source_url: sourceUrlValue(source.sourceUrl),
        purchase_cost: numericValue(source.price),
        domestic_shipping: 0,
        first_leg_shipping: 0,
        last_leg_shipping: 0,
        weight_kg: numericValue(source.weight) || undefined,
        dimensions:
          source.dimensions && typeof source.dimensions === 'object'
            ? source.dimensions
            : undefined,
        images: Array.isArray(source.images) ? source.images : [],
        attributes: normalizeAttributeMap(source.attributes),
        supplier_name: textValue(source.supplierName) || undefined,
        source_id: textValue(source.sourceId) || undefined,
        ai_recognition: source.aiRecognition || {},
        product_report: source.productReport || {},
        target_market: 'US',
        currency: 'CNY',
      })) as { product?: { id?: string } }
      const candidateProductId = result.product?.id || null
      setCurrentCandidateId(candidateProductId)

      if (importedItemId) {
        setImportItems((items) => items.map((item) => (
          item.id === importedItemId
            ? { ...item, candidateProductId: candidateProductId || undefined }
            : item
        )))
      }

      message.success('已加入候选池并完成首轮评分，正在打开候选产品页')
      navigate('/products/candidates')
    } catch (error: any) {
      message.error(error?.message || '加入候选池失败')
    } finally {
      setCandidateSubmitting(null)
    }
  }

  const handleAddCurrentCandidate = () => {
    if (!productInfo) return
    const sourceUrl = textValue(productInfo.source_url)
    void addCandidate({
      key: 'current',
      title: productReport?.product_name || productInfo.name,
      category: productReport?.product_category || productInfo.category,
      description: productReport?.product_description || productInfo.description,
      sourceUrl,
      sourceType: sourceUrl.includes('1688.com') ? '1688' : 'MANUAL',
      price: productInfo.price,
      weight: productInfo.weight_kg || productInfo.weight,
      dimensions: productInfo.dimensions,
      images: productInfo.images,
      attributes: productInfo.attributes,
      supplierName:
        productInfo.supplier?.company_name
        || productInfo.supplier_name,
      sourceId: productInfo.source_id,
      aiRecognition: aiRecognition || undefined,
      productReport: productReport || undefined,
    })
  }

  const renderArrayField = (value: any) => {
    if (Array.isArray(value)) {
      return value.map((item: string, index: number) => (
        <Tag key={`${item}-${index}`} color="blue" style={{ marginBottom: 4 }}>{item}</Tag>
      ))
    }
    return value || '-'
  }

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      <div style={{ marginBottom: '24px' }}>
        <Space align="start">
          <RobotOutlined style={{ fontSize: '28px', color: '#1677ff' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>1688 商品导入与 AI 产品分析</Title>
            <Text type="secondary">
              粘贴一个或多个 1688 链接，系统自动抓取商品、完成 10 字段识别和 17 字段产品报告
            </Text>
          </div>
        </Space>
      </div>

      <Steps
        current={currentStep}
        style={{ marginBottom: '24px' }}
        items={[
          { title: '1688 导入', description: '链接或商品 ID', icon: <LinkOutlined /> },
          { title: 'AI产品分析', description: '10字段识别', icon: <RobotOutlined /> },
          { title: '产品报告', description: '17字段报告', icon: <FileTextOutlined /> },
          { title: '生成Prompt', description: '详情页生图提示词', icon: <CodeOutlined /> },
        ]}
      />

      <Spin spinning={loading} tip="AI分析中...">
        <Row gutter={[24, 24]}>
          <Col xs={24} lg={9}>
            <Card
              title="导入 1688 商品"
              size="small"
              extra={<Tag color="blue"><LinkOutlined /> 支持批量</Tag>}
            >
              <TextArea
                rows={8}
                value={sourceText}
                onChange={(event) => setSourceText(event.target.value)}
                placeholder={[
                  '每行一个链接或商品 ID，例如：',
                  'https://detail.1688.com/offer/1075485124628.html',
                  'https://detail.1688.com/offer/1062605203200.html',
                  '1075485124628',
                ].join('\n')}
                disabled={importing}
              />

              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 12 }}>
                <Text type="secondary">
                  已识别 <Text strong>{parsedSources.length}</Text> 条，单次最多 {MAX_BATCH_SIZE} 条
                </Text>
                <Button
                  type="text"
                  size="small"
                  icon={<DeleteOutlined />}
                  disabled={!sourceText || importing}
                  onClick={() => setSourceText('')}
                >
                  清空
                </Button>
              </div>

              <Button
                type="primary"
                icon={<ThunderboltOutlined />}
                block
                style={{ marginTop: 12 }}
                loading={importing}
                disabled={parsedSources.length === 0}
                onClick={() => void handleImportSources()}
              >
                {parsedSources.length > 1 ? `导入并分析 ${Math.min(parsedSources.length, MAX_BATCH_SIZE)} 个商品` : '导入并分析'}
              </Button>

              {importing && (
                <Progress
                  percent={progress}
                  size="small"
                  status="active"
                  style={{ marginTop: 12 }}
                />
              )}
            </Card>

            {importItems.length > 0 && (
              <Card
                title="导入结果"
                size="small"
                style={{ marginTop: 16 }}
                extra={<Text type="secondary">{successCount}/{importItems.length}</Text>}
              >
                <Space size="small" style={{ marginBottom: 12 }}>
                  <Tag color="success">成功 {successCount}</Tag>
                  <Tag color={errorCount ? 'error' : 'default'}>失败 {errorCount}</Tag>
                </Space>
                <List
                  size="small"
                  dataSource={importItems}
                  renderItem={(item) => (
                    <List.Item
                      style={{ cursor: item.status === 'success' ? 'pointer' : 'default' }}
                      onClick={() => item.status === 'success' && applyImportedItem(item)}
                      actions={[
                        item.status === 'error' ? (
                          <Button
                            key="retry"
                            type="link"
                            size="small"
                            disabled={importing}
                            onClick={(event) => {
                              event.stopPropagation()
                              void handleRetryItem(item)
                            }}
                          >
                            重试
                          </Button>
                        ) : null,
                      ].filter(Boolean)}
                    >
                      <List.Item.Meta
                        title={(
                          <Space size={8}>
                            {statusTag(item.status)}
                            <Text
                              strong={item.id === selectedItemId}
                              ellipsis
                              style={{ maxWidth: 240 }}
                            >
                              {item.productName || item.productId || item.source}
                            </Text>
                            {dataSourceTag(item.dataSource)}
                          </Space>
                        )}
                        description={(
                          <Tooltip title={item.error || item.source}>
                            <Text
                              type={item.status === 'error' ? 'danger' : 'secondary'}
                              ellipsis
                              style={{ display: 'block', maxWidth: 300 }}
                            >
                              {item.error || item.source}
                            </Text>
                          </Tooltip>
                        )}
                      />
                    </List.Item>
                  )}
                />
              </Card>
            )}

            <Collapse
              ghost
              style={{ marginTop: 12 }}
              items={[
                {
                  key: 'manual',
                  label: '手工录入（备用）',
                  children: (
                    <Form form={form} layout="vertical">
                      <Form.Item name="name" label="产品名称" rules={[{ required: true, message: '请输入产品名称' }]}>
                        <Input placeholder="请输入产品名称" />
                      </Form.Item>
                      <Form.Item name="category" label="产品类目">
                        <Input placeholder="如：户外用品/露营装备" />
                      </Form.Item>
                      <Form.Item name="price" label="产品价格">
                        <Input placeholder="如：¥6.50" />
                      </Form.Item>
                      <Form.Item name="supplier_name" label="供应商名称">
                        <Input placeholder="供应商名称" />
                      </Form.Item>
                      <Form.Item name="description" label="产品描述">
                        <TextArea rows={3} placeholder="产品详细描述" />
                      </Form.Item>
                      <Form.Item name="images" label="产品图片URL">
                        <TextArea rows={2} placeholder="每行一个图片 URL" />
                      </Form.Item>
                      <Space direction="vertical" style={{ width: '100%' }}>
                        <Button type="primary" icon={<ThunderboltOutlined />} onClick={() => void handleAnalyzeAndReport()} block>
                          一键分析+报告
                        </Button>
                        <Button icon={<RobotOutlined />} onClick={() => void handleAnalyze()} block>
                          仅AI分析
                        </Button>
                      </Space>
                    </Form>
                  ),
                },
              ]}
            />
          </Col>

          <Col xs={24} lg={15}>
            {!aiRecognition && (
              <Alert
                type="info"
                showIcon
                message="等待导入商品"
                description="在左侧粘贴 1688 商品链接后点击“导入并分析”。导入完成后可在这里查看识别结果、产品报告并生成生图 Prompt。"
                style={{ marginBottom: 16 }}
              />
            )}

            {selectedItem && (
              <Alert
                type="success"
                showIcon
                style={{ marginBottom: 16 }}
                    message={selectedItem.productName || selectedItem.productId}
                    description={(
                      <Space wrap>
                        <Text type="secondary">商品 ID：{selectedItem.productId || '-'}</Text>
                        {dataSourceTag(selectedItem.dataSource)}
                        {selectedItem.candidateProductId && (
                          <Tag color="green" icon={<CheckCircleOutlined />}>已加入候选池</Tag>
                        )}
                        {selectedItem.source.startsWith('http') && (
                      <a href={selectedItem.source} target="_blank" rel="noreferrer">
                        <LinkOutlined /> 查看1688原链接
                      </a>
                    )}
                  </Space>
                )}
              />
            )}

            <Tabs
              activeKey={currentStep.toString()}
              onChange={(key) => setCurrentStep(Number(key))}
              items={[
                {
                  key: '1',
                  label: 'AI识别结果',
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
                      <Button type="primary" icon={<FileTextOutlined />} onClick={() => void handleGenerateReport()}>
                        生成产品信息报告
                      </Button>
                    </Card>
                  ) : (
                    <Empty description="导入商品后显示 AI 识别结果" />
                  ),
                },
                {
                  key: '2',
                  label: '产品信息报告',
                  children: productReport ? (
                    <Card size="small" title="产品信息报告（17字段）" extra={<Tag color="green">可用于详情页策划</Tag>}>
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
                      <Space wrap>
                        <Button
                          icon={<StarOutlined />}
                          loading={candidateSubmitting === selectedItem?.id || candidateSubmitting === 'current'}
                          disabled={Boolean(selectedItem?.candidateProductId || currentCandidateId)}
                          onClick={() => {
                            if (selectedItem) {
                              void addCandidate({
                                key: selectedItem.id,
                                title: selectedItem.productReport?.product_name || selectedItem.productName,
                                category:
                                  selectedItem.productReport?.product_category
                                  || selectedItem.productInfo?.category,
                                description:
                                  selectedItem.productReport?.product_description
                                  || selectedItem.productInfo?.description,
                                sourceUrl: selectedItem.source,
                                sourceType: '1688',
                                price: selectedItem.productInfo?.price,
                                weight:
                                  selectedItem.productInfo?.weight_kg
                                  || selectedItem.productInfo?.weight,
                                dimensions: selectedItem.productInfo?.dimensions,
                                images: selectedItem.productInfo?.images,
                                attributes: selectedItem.productInfo?.attributes,
                                supplierName:
                                  selectedItem.productInfo?.supplier?.company_name
                                  || selectedItem.productInfo?.supplier_name,
                                sourceId: selectedItem.productInfo?.source_id,
                                aiRecognition: selectedItem.aiRecognition,
                                productReport: selectedItem.productReport,
                              }, selectedItem.id)
                            } else {
                              handleAddCurrentCandidate()
                            }
                          }}
                        >
                          {selectedItem?.candidateProductId || currentCandidateId ? '已加入候选池' : '加入候选池'}
                        </Button>
                        <Button type="primary" icon={<CodeOutlined />} onClick={() => void handleGeneratePrompt()}>
                          生成生图Prompt
                        </Button>
                        <Button icon={<ThunderboltOutlined />} onClick={() => void handleBatchPrompts()}>
                          批量生成页面Prompt
                        </Button>
                      </Space>
                    </Card>
                  ) : (
                    <Empty description="完成 AI 分析后生成产品报告" />
                  ),
                },
                {
                  key: '3',
                  label: '生成Prompt',
                  children: generatedPrompt ? (
                    <Card size="small" title={`生成的Prompt - ${generatedPrompt.metadata?.page_type_name || ''}`}>
                      <Space style={{ marginBottom: '16px' }} wrap>
                        <Select
                          value={selectedPageType}
                          onChange={setSelectedPageType}
                          options={PAGE_TYPE_OPTIONS}
                          style={{ width: 200 }}
                        />
                        <Button icon={<ReloadOutlined />} onClick={() => void handleGeneratePrompt()}>重新生成</Button>
                        <Tooltip title="复制完整Prompt">
                          <Button icon={<CopyOutlined />} onClick={() => void handleCopyPrompt(generatedPrompt.full_prompt)}>
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
                            label: '结构拆解',
                            children: (
                              <Space direction="vertical" style={{ width: '100%' }}>
                                {Object.entries(generatedPrompt.parts || {}).map(([key, value]: [string, any]) => (
                                  <Card key={key} size="small" title={<Tag color="blue">{key}</Tag>}>
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
                    <Empty description="完成产品报告后生成生图 Prompt" />
                  ),
                },
              ]}
            />

            {batchPrompts && (
              <Card size="small" title={`批量生成的Prompt（${batchPrompts.count}个）`} style={{ marginTop: '24px' }}>
                <Row gutter={[16, 16]}>
                  {Object.entries(batchPrompts.prompts || {}).map(([key, value]: [string, any]) => (
                    <Col xs={24} md={12} key={key}>
                      <Card
                        size="small"
                        title={value.metadata?.page_type_name || key}
                        extra={(
                          <Button size="small" icon={<CopyOutlined />} onClick={() => void handleCopyPrompt(value.full_prompt)}>
                            复制
                          </Button>
                        )}
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
