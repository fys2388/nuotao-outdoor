import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Form, Input, Button, Space, Typography, Steps, Tag, Alert,
  Row, Col, Spin, message, Tabs, Divider, Select, Descriptions, Collapse,
  Statistic, Progress, Empty, Tooltip, Modal, List, Badge, Switch, InputNumber
} from 'antd'
import {
  ThunderboltOutlined, CheckCircleOutlined, CloseCircleOutlined,
  LoadingOutlined, CopyOutlined, ShopOutlined, FileTextOutlined,
  PictureOutlined, RocketOutlined, HistoryOutlined, PlayCircleOutlined
} from '@ant-design/icons'
import { api } from '../api/client'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

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

// ---- 生图硬标准（Nuotao 上架规范，禁止擅自降级）----
// 主图 5 张 1:1 2048x2048、详情图 6 张 3:4 1536x2048；I2I 还原 1688 原图；
// 全英文 prompt、视觉方向多样化、无水印、无文字。
const IMAGE_GEN_MODEL = 'doubao-seedream-5-0-pro-260628'
const IMAGE_GEN_CONCURRENCY = 3
const MAIN_IMAGE_W = 2048
const MAIN_IMAGE_H = 2048
const DETAIL_IMAGE_W = 1536
const DETAIL_IMAGE_H = 2048
const MAIN_IMAGE_VARIANTS = [
  'professional e-commerce main image, pure white background (#FFFFFF), product centered and fully visible, soft studio lighting, ultra sharp photorealistic, no text, no logo, no watermark',
  'hero catalog image, light gray seamless studio background, slight three-quarter angle, realistic shadow, premium outdoor product photography, no text, no logo, no watermark',
  'bright clean outdoor campsite lifestyle scene, the product clearly featured as the subject, natural daylight, photorealistic, no text, no logo, no watermark',
  'front view product image on white with a soft platform shadow, close-up showing material texture and build detail, studio quality, no text, no logo, no watermark',
  'promotional marketplace main image, clean neutral gradient background, generous negative space around the centered product, high-end photorealistic render, no text, no logo, no watermark',
]
const DETAIL_IMAGE_VARIANTS = [
  'detail page macro close-up of the key material, fabric weave and stitching texture, sharp focus, neutral studio background, vertical composition, no text, no watermark',
  'detail page close-up of functional hardware, joints, zipper or buckle build quality, macro photography, clean background, vertical 3:4, no text, no watermark',
  'lifestyle usage scene in a realistic mountain campsite with a person using the product, natural environment, vertical composition, no text, no watermark',
  'full product hero shot on a soft neutral gradient background for the detail page, vertical 3:4, even studio lighting, photorealistic, no text, no watermark',
  'size and scale reference scene outdoors among common camping gear, photorealistic, informative product photography, vertical 3:4, no text, no watermark',
  'feature highlight close-up of a signature functional part in use, clean bright background, professional commercial product shot, vertical 3:4, no text, no watermark',
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
  const navigate = useNavigate()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [pipelineResult, setPipelineResult] = useState<PipelineResult | null>(null)
  const [listingModalOpen, setListingModalOpen] = useState(false)
  const [listingLoading, setListingLoading] = useState(false)
  const [history, setHistory] = useState<PipelineResult[]>([])
  const [generatingImage, setGeneratingImage] = useState(false)
  const [generatedImages, setGeneratedImages] = useState<string[]>([])
  const [detailImages, setDetailImages] = useState<string[]>([])
  const [sourceImages, setSourceImages] = useState<string[]>([])
  const [genProgress, setGenProgress] = useState<{ done: number; total: number }>({ done: 0, total: 0 })
  const [batchQueue, setBatchQueue] = useState<any[]>([])
  const [currentBatchIndex, setCurrentBatchIndex] = useState(0)
  const [importUrl, setImportUrl] = useState('')
  const [importLoading, setImportLoading] = useState(false)
  const [autoRunPipeline, setAutoRunPipeline] = useState(true)
  // BUG-21 (2026-10-12): 1688 导入得到的完整商品数据。此前只把 name/price 等
  // 标量回填进表单，运行管线时又从表单重建 product_info，于是 variations /
  // attributes / images / source_url / sku 全部丢失 —— 多规格商品必然退化成
  // 单 SKU 简单商品，且后端无法按来源键回查补数。这里保留原始导入结果，
  // 运行载荷以它为基础、表单值为覆盖。
  const [importedProductInfo, setImportedProductInfo] = useState<Record<string, any> | null>(null)
  // BUG-25: 导入失败的持久化提示（toast 会消失，长任务需要可回看的失败原因）
  const [importError, setImportError] = useState<string | null>(null)
  // 智能定价参数
  const [priceMarkup, setPriceMarkup] = useState(6.0)
  const [usdCnyRate, setUsdCnyRate] = useState(7.2)

  // 智能定价预览：根据采购价实时计算建议售价
  const calculateSuggestedPrice = (cnyPrice: string): string => {
    if (!cnyPrice) return ''
    // BUG-19 (2026-10-12): 原来先做 Number(cnyPrice) 判空，而 1688 导入的采购价
    // 常带货币符号或区间（"¥20" / "6.7-19.7"），Number() 直接是 NaN，于是预览
    // 永远显示 "$—"，运营以为公式坏了。改为先提取数字再判断。
    const match = String(cnyPrice).match(/\d+(?:\.\d+)?/)
    if (!match) return ''
    const price = parseFloat(match[0])
    if (isNaN(price) || price <= 0) return ''
    return `$${(price / usdCnyRate * priceMarkup).toFixed(2)}`
  }

  // 取 1688 原图作为 I2I 参考图（上架标准：生成图必须还原原图产品）
  const getReferenceImage = (): string => {
    const pick = (arr: any): string => {
      if (!Array.isArray(arr)) return ''
      const found = arr
        .map((x: any) => (typeof x === 'string' ? x : x?.src))
        .find((u: any) => typeof u === 'string' && u.startsWith('http'))
      return found || ''
    }
    return (
      pick(pipelineResult?.data?.steps?.input?.data?.images) ||
      pick(pipelineResult?.data?.steps?.listing_data?.data?.images) ||
      sourceImages.find((u) => u.startsWith('http')) ||
      ''
    )
  }

  // 单张生成：独立请求避免批量长连接被代理超时切断；I2I 失败直接计失败，绝不降级 mock
  const generateOneImage = async (
    prompt: string, useCase: string, width: number, height: number, reference: string,
  ): Promise<string> => {
    const imgToken = localStorage.getItem('admin_token') || ''
    const imgHeaders: HeadersInit = { 'Content-Type': 'application/json' }
    if (imgToken) imgHeaders['Authorization'] = `Bearer ${imgToken}`
    const resp = await fetch('/api/v1/image-gen/generate', {
      method: 'POST',
      headers: imgHeaders,
      body: JSON.stringify({
        prompt,
        use_case: useCase,
        model: IMAGE_GEN_MODEL,
        width,
        height,
        ...(reference ? { reference_image: reference } : {}),
      }),
    })
    const data = await resp.json()
    if (!resp.ok || !data.success) {
      throw new Error(data?.detail || data?.error || data?.task?.error_message || 'image generation failed')
    }
    if (data.mock) throw new Error('后端仅返回 mock 占位图（未配置真实生图模型），已中止')
    const url = data?.task?.image_url
    if (!url || typeof url !== 'string') throw new Error(data?.task?.error_message || '图片 URL 为空')
    return url
  }

  // 有界并发跑一组变体，结果按索引归位；单张失败不影响其他
  const runImageBatch = async (
    basePrompt: string, variants: string[], useCase: string,
    width: number, height: number, reference: string,
    setUrls: (updater: (prev: string[]) => string[]) => void,
  ): Promise<(string | null)[]> => {
    const results: (string | null)[] = new Array(variants.length).fill(null)
    let cursor = 0
    const worker = async () => {
      for (;;) {
        const i = cursor
        cursor += 1
        if (i >= variants.length) return
        const prompt = `${basePrompt} ${variants[i]}`.trim()
        try {
          const url = await generateOneImage(prompt, useCase, width, height, reference)
          results[i] = url
          setUrls((prev) => { const next = [...prev]; next[i] = url; return next })
        } catch (e: any) {
          results[i] = null
          console.error('image variant', i, 'failed:', e?.message)
        } finally {
          setGenProgress((prev) => ({ done: prev.done + 1, total: prev.total }))
        }
      }
    }
    await Promise.all(Array.from({ length: Math.min(IMAGE_GEN_CONCURRENCY, variants.length) }, worker))
    return results
  }

  // 一键生成：主图 5 张 2048x2048 + 详情图 6 张 1536x2048，全部 I2I 还原 1688 原图
  const handleGenerateImage = async () => {
    const promptData = pipelineResult?.data?.steps?.prompt?.data
    const mainPrompt = promptData?.main_image_prompt
    const detailPrompt = promptData?.detail_image_prompt
    if (!mainPrompt) {
      message.error('请先运行工作流生成生图Prompt')
      return
    }
    const reference = getReferenceImage()
    if (!reference) {
      message.warning('未找到 1688 原图，将退化为纯文生图；上架标准要求 I2I 还原原图，建议先从 1688 导入')
    }
    try {
      setGeneratingImage(true)
      setGeneratedImages(new Array(MAIN_IMAGE_VARIANTS.length).fill(''))
      setDetailImages(new Array(DETAIL_IMAGE_VARIANTS.length).fill(''))
      setGenProgress({ done: 0, total: MAIN_IMAGE_VARIANTS.length + DETAIL_IMAGE_VARIANTS.length })

      const mainUrls = await runImageBatch(
        mainPrompt, MAIN_IMAGE_VARIANTS, 'main_image', MAIN_IMAGE_W, MAIN_IMAGE_H, reference, setGeneratedImages,
      )
      const detailUrls = await runImageBatch(
        detailPrompt || mainPrompt, DETAIL_IMAGE_VARIANTS, 'detail_image', DETAIL_IMAGE_W, DETAIL_IMAGE_H, reference, setDetailImages,
      )

      const mainOk = mainUrls.filter(Boolean).length
      const detailOk = detailUrls.filter(Boolean).length

      if (mainOk + detailOk > 0 && pipelineResult?.data?.steps?.listing_data?.data) {
        const images: any[] = []
        mainUrls.forEach((u, i) => u && images.push({ src: u, name: `main_image_${i + 1}`, type: 'main' }))
        detailUrls.forEach((u, i) => u && images.push({ src: u, name: `detail_image_${i + 1}`, type: 'detail' }))
        const updated = { ...pipelineResult }
        updated.data.steps.listing_data.data.images = images
        setPipelineResult(updated)
      }

      if (mainOk === 0 && detailOk === 0) {
        message.error('所有图片生成失败，请检查生图模型配置或参考图后重试')
      } else if (mainOk < MAIN_IMAGE_VARIANTS.length || detailOk < DETAIL_IMAGE_VARIANTS.length) {
        message.warning(`部分成功：主图 ${mainOk}/${MAIN_IMAGE_VARIANTS.length}，详情图 ${detailOk}/${DETAIL_IMAGE_VARIANTS.length}，可重新生成补齐`)
      } else {
        message.success(`图片生成完成：主图 ${mainOk} 张 + 详情图 ${detailOk} 张，已回填上架数据`)
      }
    } catch (e: any) {
      message.error(e?.message || '图片生成失败')
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

  // 从1688导入商品信息（异步任务模式，适配牛顿Agent长耗时）
  const handleImportFrom1688 = async () => {
    if (!importUrl || importUrl.trim().length === 0) {
      message.error('请输入1688商品URL或商品ID')
      return
    }

    try {
      setImportLoading(true)
      setImportError(null)
      // Step 1: 提交后台任务
      const submitted = await api.createImportFrom1688Job({
        url_or_id: importUrl.trim(),
        auto_run_pipeline: autoRunPipeline,
        auto_list: false,
      })
      if (!submitted.success || !submitted.data) {
        message.error(`提交导入任务失败：${submitted.error || '未知错误'}`)
        return
      }

      const jobId = submitted.data.job_id
      const TIMEOUT_MS = 20 * 60 * 1000 // 20分钟
      const POLL_MS = 3000
      const deadline = Date.now() + TIMEOUT_MS

      message.loading({ content: '正在从1688导入商品，牛顿Agent处理中...', key: 'import1688', duration: 0 })

      // Step 2: 轮询任务状态
      let completedData: any = null
      let completedError = ''
      let elapsed = 0
      const steps = ['创建Agent任务', '抓取商品数据', '解析商品信息', '完成']
      let lastStep = 0

      while (Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, POLL_MS))
        elapsed = Math.round((Date.now() - (deadline - TIMEOUT_MS)) / 1000)

        const jobResponse = await api.getImportFrom1688Job(jobId)
        const job = jobResponse.data

        if (!jobResponse.success || !job) {
          completedError = jobResponse.error || '无法读取任务状态'
          break
        }

        if (job.status === 'succeeded') {
          completedData = job.data
          break
        }
        if (job.status === 'failed') {
          completedError = job.error || '导入失败'
          break
        }

        // 更新进度提示
        const newStep = elapsed < 15 ? 0 : elapsed < 60 ? 1 : elapsed < 100 ? 2 : 3
        if (newStep !== lastStep) {
          lastStep = newStep
          message.loading({ content: `${steps[lastStep]}… (${elapsed}s)`, key: 'import1688', duration: 0 })
        }
      }

      message.destroy('import1688')

      if (!completedData) {
        // BUG-25: 导入是 1-5 分钟的长任务，失败后原先只弹一条 3 秒的 toast，
        // 用户回头再看页面时毫无痕迹，无法判断究竟发生了什么（本轮真机验证中
        // 就出现过「按钮复位、表单空白、页面像没动过」的困惑）。
        // 改为同时落一个持久化的错误态，直到下一次导入或手动关闭。
        const reason = completedError || '任务超时'
        setImportError(reason)
        message.error(`导入失败：${reason}`, 10)
        return
      }
      setImportError(null)

      // Step 3: 填充表单
      const productInfo = completedData.product_info
      if (productInfo) {
        // 保留完整导入数据（含 variants/来源键），运行管线时要带上
        setImportedProductInfo(productInfo)
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
        if (Array.isArray(productInfo.images)) {
          setSourceImages(productInfo.images.filter((u: any) => typeof u === 'string' && u.startsWith('http')))
        }
      }

      // 如果自动运行工作流
      if (autoRunPipeline && completedData.pipeline_result) {
        setPipelineResult(completedData.pipeline_result)
        message.info('工作流已自动运行完成')
      }

      // BUG-22 (2026-10-12): 导入成功但自动运行管线失败时，后端把原因放在
      // pipeline_error（例如「同一链接禁止重复上架」），前端此前完全忽略，
      // 运营只看到表单被填好、进度区空白，无法判断发生了什么。必须显式提示。
      if (completedData.pipeline_error) {
        setImportError(`商品已导入，但自动运行管线失败：${completedData.pipeline_error}`)
        message.error({
          content: `商品已导入，但自动运行管线失败：${completedData.pipeline_error}`,
          duration: 10,
        })
      }

      setImportUrl('')
    } catch (e: any) {
      console.error('Import from 1688 error:', e)
      message.destroy('import1688')
      setImportError(e.message || '网络错误')
      message.error(`导入失败：${e.message || '网络错误'}`)
    } finally {
      setImportLoading(false)
    }
  }

  // 运行工作流（异步提交，轮询获取结果，避免网关超时）
  const handleRunPipeline = async () => {
    try {
      const values = await form.validateFields()
      if (!values.name || values.name.trim().length === 0) {
        message.error('请输入商品名称')
        return
      }

      setLoading(true)
      setPipelineResult(null)

      // BUG-21: 以完整导入数据为基底，表单值覆盖人工可编辑字段。
      // 只从表单重建会丢掉 variations/attributes/images/source_url/sku，
      // 多规格商品必然变成单 SKU，且售价为空（后端也无来源键可回查）。
      const imported = importedProductInfo || {}
      const pick = (formValue: any, fallback: any) => {
        // 表单留空时不要用空值覆盖导入值（运营清空输入框不应等于丢弃采购价）
        if (formValue === undefined || formValue === null) return fallback
        if (typeof formValue === 'string' && formValue.trim() === '') return fallback
        return formValue
      }
      const productInfo = {
        ...imported,
        name: values.name,
        category: pick(values.category, imported.category || ''),
        price: pick(values.price, imported.price || ''),
        description: pick(values.description, imported.description || ''),
        core_selling_points:
          values.core_selling_points?.split('\n').filter(Boolean) || [],
        target_audience: pick(values.target_audience, imported.target_audience || ''),
        usage_scenarios:
          values.usage_scenarios?.split('\n').filter(Boolean) || [],
        product_features:
          values.product_features?.split('\n').filter(Boolean) || [],
        price_markup: priceMarkup,
        usd_cny_rate: usdCnyRate,
      }

      const runToken = localStorage.getItem('admin_token') || ''
      const runHeaders: HeadersInit = { 'Content-Type': 'application/json' }
      if (runToken) runHeaders['Authorization'] = `Bearer ${runToken}`

      message.loading({ content: '正在提交工作流任务...', key: 'pipeline_progress', duration: 0 })

      // 提交异步任务
      const resp = await fetch('/api/v1/product-pipeline/run-async', {
        method: 'POST',
        headers: runHeaders,
        body: JSON.stringify({
          product_info: productInfo,
          auto_list: false,
          include_images: false,
        }),
      })
      const submitData = await resp.json()

      if (!submitData.success || !submitData.data?.job_id) {
        message.destroy('pipeline_progress')
        message.error(submitData.error || '提交工作流任务失败')
        setLoading(false)
        return
      }

      const jobId = submitData.data.job_id
      message.loading({ content: '🔄 AI工作流运行中...', key: 'pipeline_progress', duration: 0 })

      // 轮询任务状态
      const TIMEOUT_MS = 10 * 60 * 1000 // 10分钟
      const POLL_MS = 3000
      const deadline = Date.now() + TIMEOUT_MS

      while (Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, POLL_MS))

        const pollResp = await fetch(`/api/v1/product-pipeline/run-async/${jobId}`, {
          headers: runHeaders,
        })
        const pollData = await pollResp.json()

        if (pollData.success && pollData.data?.status === 'completed') {
          message.destroy('pipeline_progress')
          const resultData = pollData.data.data
          if (resultData?.success) {
            setPipelineResult(resultData as PipelineResult)
            setHistory(prev => [resultData, ...prev].slice(0, 10))
            const completed = resultData?.completed_steps || 0
            const total = resultData?.total_steps || 6
            const elapsed = resultData?.elapsed_time_seconds || 0
            message.success(`✅ 工作流完成：${completed}/${total}步成功，耗时 ${elapsed}s`)
            if (resultData?.steps?.listing_data?.data) {
              setListingModalOpen(true)
            }
          } else {
            message.error(resultData?.error || '工作流执行失败')
          }
          setLoading(false)
          return
        } else if (pollData.success && pollData.data?.status === 'failed') {
          message.destroy('pipeline_progress')
          message.error(pollData.data?.error || '工作流任务失败')
          setLoading(false)
          return
        }
      }

      // 超时
      message.destroy('pipeline_progress')
      message.error('工作流任务超时，请稍后在历史记录查看')
      setLoading(false)
    } catch (e: any) {
      message.destroy('pipeline_progress')
      message.error(e.message || '工作流执行失败')
      setLoading(false)
    }
  }

  // 确认上架
  const handleConfirmListing = async (status: string = 'publish') => {
    if (!pipelineResult) return

    let progressKey = 'listing_progress'
    try {
      setListingLoading(true)
      const confirmToken = localStorage.getItem('admin_token') || ''
      const confirmHeaders: HeadersInit = { 'Content-Type': 'application/json' }
      if (confirmToken) confirmHeaders['Authorization'] = `Bearer ${confirmToken}`

      progressKey = 'listing_progress'
      message.loading({ content: '正在提交上架任务...', key: progressKey, duration: 0 })

      // 使用异步端点，避免网关超时
      const resp = await fetch('/api/v1/product-pipeline/confirm-list-async', {
        method: 'POST',
        headers: confirmHeaders,
        body: JSON.stringify({
          pipeline_result: pipelineResult,
          status: status,
        }),
      })
      const data = await resp.json()

      if (!data.success || !data.data?.job_id) {
        message.destroy(progressKey)
        message.error(data.error || '提交上架任务失败')
        setListingLoading(false)
        return
      }

      const jobId = data.data.job_id
      message.loading({ content: '正在推送到WooCommerce...', key: progressKey, duration: 0 })

      // 轮询任务状态
      const pollInterval = setInterval(async () => {
        try {
          const pollResp = await fetch(`/api/v1/product-pipeline/confirm-list-async/${jobId}`, {
            headers: confirmHeaders,
          })
          const pollData = await pollResp.json()

          if (pollData.success && pollData.data?.status === 'completed') {
            clearInterval(pollInterval)
            message.destroy(progressKey)
            const resultData = pollData.data.data
            if (resultData?.success) {
              const wcId = resultData?.woocommerce_id || '—'
              const sku = resultData?.sku || pipelineResult.data?.steps?.listing_data?.data?.sku || ''
              message.success(`✅ 上架成功！WC产品ID: ${wcId}，SKU: ${sku}`)
              setListingModalOpen(false)
              setPipelineResult(prev => prev ? {
                ...prev,
                data: {
                  ...prev.data,
                  steps: {
                    ...prev.data.steps,
                    listing: { status: 'completed', data: resultData }
                  }
                }
              } : null)
              setTimeout(() => { navigate('/products/listing') }, 2000)
            } else {
              message.error(resultData?.error || '上架失败')
            }
            setListingLoading(false)
          } else if (pollData.success && pollData.data?.status === 'failed') {
            clearInterval(pollInterval)
            message.destroy(progressKey)
            message.error(pollData.data?.error || '上架任务失败')
            setListingLoading(false)
          }
          // pending/running: continue polling
        } catch (e: any) {
          console.error('Poll error:', e)
        }
      }, 3000)

      // 设置最大轮询时间（5分钟）
      const maxPollTime = setTimeout(() => {
        clearInterval(pollInterval)
        message.destroy(progressKey)
        message.error('上架任务超时，请稍后在商品列表查看')
        setListingLoading(false)
      }, 300000)

    } catch (e: any) {
      message.destroy(progressKey)
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
                    自动获取商品名称/价格/描述/图片/属性，转换为工作流输入格式。异步执行，约1-2分钟
                  </Text>
                </div>
                {/* BUG-25: 导入失败原因持久展示，长任务失败后仍可回看 */}
                {importError && (
                  <Alert
                    type="error"
                    showIcon
                    closable
                    onClose={() => setImportError(null)}
                    message="1688 导入未完成"
                    description={importError}
                    style={{ marginTop: '8px' }}
                  />
                )}
              </div>

              <Form form={form} layout="vertical" size="small">
                <Form.Item name="name" label="商品名称 *" rules={[{ required: true, message: '请输入商品名称' }]}>
                  <Input placeholder="例如：便携榨汁杯" />
                </Form.Item>

                <Form.Item name="category" label="商品类目">
                  <Select options={CATEGORY_OPTIONS} placeholder="选择类目" allowClear />
                </Form.Item>

                <Form.Item name="price" label="1688采购价">
                  <Input placeholder="例如：¥29.9" onChange={(e) => {
                    const val = e.target.value
                    form.setFieldsValue({ price: val })
                  }} />
                </Form.Item>

                {/* 智能定价预览 */}
                <div style={{ padding: '10px 12px', background: '#f0f5ff', borderRadius: '6px', marginBottom: '12px', border: '1px solid #adc6ff' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                    <Text strong style={{ fontSize: '12px', color: '#1890ff' }}>💰 智能定价预览</Text>
                    <Space size={8}>
                      <span style={{ fontSize: '11px' }}>汇率:</span>
                      <InputNumber size="small" min={6} max={8} step={0.1} value={usdCnyRate}
                        onChange={(v) => setUsdCnyRate(v || 7.2)} style={{ width: 60 }} formatter={v => `${v}`} parser={v => Number(v)} />
                      <span style={{ fontSize: '11px' }}>倍数:</span>
                      <InputNumber size="small" min={3} max={12} step={0.5} value={priceMarkup}
                        onChange={(v) => setPriceMarkup(v || 6)} style={{ width: 50 }} formatter={v => `${v}`} parser={v => Number(v)} />
                    </Space>
                  </div>
                  <div style={{ fontSize: '13px', color: '#595959' }}>
                    公式：采购价(CNY) ÷ {usdCnyRate} × {priceMarkup} ={' '}
                    <Text strong style={{ color: '#52c41a', fontSize: '16px' }}>
                      {(() => {
                        const priceStr = form.getFieldValue('price') || ''
                        return calculateSuggestedPrice(priceStr) || '$—'
                      })()}
                    </Text>
                    <Text type="secondary" style={{ fontSize: '11px', marginLeft: '8px' }}>&#xFF08;&#x4FDD;&#x8BC1;&#x5168;&#x6210;&#x672C;&#x5229;&#x6DA6;&#x7387; &gt; 60%&#xFF09;</Text>
                  </div>
                </div>

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

                  <Steps
                    direction="vertical"
                    size="small"
                    style={{ marginTop: '24px' }}
                    current={pipelineResult.data.completed_steps}
                    items={PIPELINE_STEPS.map((step) => {
                      const StepIcon = step.icon
                      const stepData = pipelineResult.data.steps?.[step.id]
                      return {
                        key: step.id,
                        title: (
                          <Space>
                            <StepIcon /> {step.title}{' '}
                            <Tag color={getStepColor(step.id)}>{stepData?.status || 'wait'}</Tag>
                          </Space>
                        ),
                        description: step.description,
                        status: getStepStatus(step.id),
                      }
                    })}
                  />

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
                            一键生图(5主图+6详情)
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
                            {/* 生成的图片预览：主图(5, 1:1 2048) + 详情图(6, 3:4 1536x2048) */}
                            {(generatedImages.some(Boolean) || detailImages.some(Boolean)) && (
                              <>
                                <Divider style={{ margin: '16px 0' }} />
                                <div>
                                  <Text strong>主图（{generatedImages.filter(Boolean).length}/5，2048x2048，已回填上架数据）：</Text>
                                  <Row gutter={[16, 16]} style={{ marginTop: '12px' }}>
                                    {generatedImages.map((url, i) => url ? (
                                      <Col span={8} key={`m${i}`}>
                                        <img src={url} alt={`Main ${i + 1}`} style={{ width: '100%', aspectRatio: '1/1', objectFit: 'cover', borderRadius: '8px', cursor: 'pointer' }} onClick={() => window.open(url, '_blank')} />
                                      </Col>
                                    ) : null)}
                                  </Row>
                                </div>
                                <div style={{ marginTop: '16px' }}>
                                  <Text strong>详情图（{detailImages.filter(Boolean).length}/6，1536x2048）：</Text>
                                  <Row gutter={[16, 16]} style={{ marginTop: '12px' }}>
                                    {detailImages.map((url, i) => url ? (
                                      <Col span={8} key={`d${i}`}>
                                        <img src={url} alt={`Detail ${i + 1}`} style={{ width: '100%', aspectRatio: '3/4', objectFit: 'cover', borderRadius: '8px', cursor: 'pointer' }} onClick={() => window.open(url, '_blank')} />
                                      </Col>
                                    ) : null)}
                                  </Row>
                                </div>
                              </>
                            )}
                            {generatingImage && (
                              <div style={{ textAlign: 'center', padding: '20px' }}>
                                <Spin size="large" />
                                <Paragraph type="secondary" style={{ marginTop: '8px' }}>
                                  AI 正在以 I2I 批量生成主图(5)+详情图(6)，已完成 {genProgress.done}/{genProgress.total}，约需数分钟...
                                </Paragraph>
                                <Progress percent={genProgress.total ? Math.round((genProgress.done / genProgress.total) * 100) : 0} size="small" style={{ maxWidth: 320, margin: '8px auto 0' }} />
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
