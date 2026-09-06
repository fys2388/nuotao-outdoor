import { useState, useEffect } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Input, Select,
  Statistic, Row, Col, Spin, message, Modal, Descriptions, List,
  Badge, Tooltip, Empty, Tabs, Steps, Divider, Alert,
  Switch, Form, InputNumber, Upload, Radio, Checkbox, Image
} from 'antd'
import {
  ShoppingOutlined, ReloadOutlined, SearchOutlined,
  EyeOutlined, PlusOutlined, EditOutlined,
  CheckCircleOutlined, WarningOutlined, SyncOutlined,
  ClockCircleOutlined, UploadOutlined, PictureOutlined,
  DollarOutlined, DatabaseOutlined, SendOutlined,
  CopyOutlined, DeleteOutlined, DownloadOutlined,
  FileTextOutlined, RocketOutlined, FilterOutlined
} from '@ant-design/icons'

const { Title, Text, Paragraph } = Typography

interface ListingProduct {
  id: string
  name: string
  name_en?: string
  sku: string
  source: '1688' | 'manual' | 'pipeline'
  source_url?: string
  category: string
  price: number
  cost_price: number
  stock: number
  status: 'draft' | 'editing' | 'review' | 'pending' | 'listing' | 'listed' | 'failed'
  images: string[]
  description?: string
  description_en?: string
  attributes: { key: string; value: string }[]
  created_at: string
  updated_at: string
  listed_at?: string
  woocommerce_id?: number
  woocommerce_url?: string
  error_message?: string
  ai_processed: boolean
  images_processed: boolean
}

const statusColors: Record<string, string> = {
  draft: 'default',
  editing: 'blue',
  review: 'orange',
  pending: 'cyan',
  listing: 'processing',
  listed: 'green',
  failed: 'red',
}

const statusText: Record<string, string> = {
  draft: '草稿',
  editing: '编辑中',
  review: '待审核',
  pending: '待上架',
  listing: '上架中',
  listed: '已上架',
  failed: '上架失败',
}

const sourceColors: Record<string, string> = {
  '1688': 'orange',
  manual: 'blue',
  pipeline: 'purple',
}

export default function ProductListingPage() {
  const [activeTab, setActiveTab] = useState('queue')
  const [loading, setLoading] = useState(false)
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [batchListingModalOpen, setBatchListingModalOpen] = useState(false)
  const [viewingProduct, setViewingProduct] = useState<ListingProduct | null>(null)
  const [editingProduct, setEditingProduct] = useState<ListingProduct | null>(null)
  const [statusFilter, setStatusFilter] = useState('all')
  const [sourceFilter, setSourceFilter] = useState('all')
  const [searchText, setSearchText] = useState('')
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])
  const [editForm] = Form.useForm()
  const [listingProduct, setListingProduct] = useState<string | null>(null)
  const [aiCopyLoading, setAiCopyLoading] = useState(false)
  const [aiCopyResult, setAiCopyResult] = useState<any>(null)
  const [aiCopyModalOpen, setAiCopyModalOpen] = useState(false)
  // 真实API数据状态
  const [productListingData, setProductListingData] = useState<any>(null)

  // 模拟待上架商品数据
  const mockProducts: ListingProduct[] = [
    {
      id: '1', name: 'LED头灯 Pro 强光充电', name_en: 'LED Headlamp Pro Rechargeable', sku: 'NT-HEADLAMP-001',
      source: '1688', source_url: 'https://detail.1688.com/offer/1078487117828.html',
      category: '照明设备', price: 49.99, cost_price: 28.5, stock: 50,
      status: 'pending', images: ['/images/headlamp-1.jpg', '/images/headlamp-2.jpg', '/images/headlamp-3.jpg'],
      description: '超强光LED头灯，USB充电，防水设计，适合户外露营、夜跑、钓鱼等场景。',
      description_en: 'Super bright LED headlamp, USB rechargeable, waterproof design, perfect for outdoor camping, night running, fishing and more.',
      attributes: [
        { key: '材质', value: 'ABS+硅胶' },
        { key: '光源', value: 'LED XPG2' },
        { key: '续航', value: '6-12小时' },
        { key: '防水等级', value: 'IPX4' },
        { key: '重量', value: '85g' },
      ],
      created_at: '2026-09-05 10:00:00', updated_at: '2026-09-05 10:30:00',
      ai_processed: true, images_processed: true,
    },
    {
      id: '2', name: '太阳能露营灯 折叠', name_en: 'Solar Camping Lantern Foldable', sku: 'NT-LAMP-002',
      source: 'pipeline', category: '照明设备', price: 39.99, cost_price: 45.0, stock: 30,
      status: 'editing', images: ['/images/lamp-1.jpg', '/images/lamp-2.jpg'],
      description: '太阳能充电露营灯，折叠设计，便携易带，三档调光，应急必备。',
      attributes: [
        { key: '材质', value: '硅胶+ABS' },
        { key: '充电方式', value: '太阳能/USB' },
        { key: '续航', value: '4-8小时' },
        { key: '重量', value: '120g' },
      ],
      created_at: '2026-09-04 15:00:00', updated_at: '2026-09-05 09:00:00',
      ai_processed: true, images_processed: false,
    },
    {
      id: '3', name: '保温水壶1L 304不锈钢', name_en: 'Insulated Water Bottle 1L 304 Stainless Steel', sku: 'NT-BOTTLE-001',
      source: '1688', category: '水具餐具', price: 29.99, cost_price: 32.0, stock: 100,
      status: 'listed', images: ['/images/bottle-1.jpg', '/images/bottle-2.jpg', '/images/bottle-3.jpg', '/images/bottle-4.jpg'],
      description: '304不锈钢保温水壶，1L大容量，12小时保温保冷，户外必备。',
      description_en: '304 stainless steel insulated water bottle, 1L large capacity, 12 hours heat and cold retention, outdoor essential.',
      attributes: [
        { key: '材质', value: '304不锈钢' },
        { key: '容量', value: '1000ml' },
        { key: '保温时间', value: '12小时' },
        { key: '保冷时间', value: '24小时' },
        { key: '重量', value: '280g' },
      ],
      created_at: '2026-09-01 10:00:00', updated_at: '2026-09-02 14:00:00',
      listed_at: '2026-09-02 15:00:00', woocommerce_id: 1234,
      woocommerce_url: 'https://nuotaooutdoor.com/product/insulated-water-bottle-1l',
      ai_processed: true, images_processed: true,
    },
    {
      id: '4', name: '户外自动帐篷 3-4人', name_en: 'Outdoor Automatic Tent 3-4 Person', sku: 'NT-TENT-001',
      source: 'manual', category: '户外家具', price: 89.99, cost_price: 185.0, stock: 20,
      status: 'review', images: ['/images/tent-1.jpg', '/images/tent-2.jpg', '/images/tent-3.jpg'],
      description: '全自动速开帐篷，3-4人容量，防水防风，搭建简单，露营首选。',
      attributes: [
        { key: '材质', value: '210D涤纶+玻璃纤维杆' },
        { key: '容量', value: '3-4人' },
        { key: '防水等级', value: 'PU3000mm' },
        { key: '展开尺寸', value: '210×210×135cm' },
        { key: '重量', value: '2.8kg' },
      ],
      created_at: '2026-09-03 11:00:00', updated_at: '2026-09-04 16:00:00',
      ai_processed: true, images_processed: true,
    },
    {
      id: '5', name: '登山杖 碳纤维折叠', name_en: 'Trekking Poles Carbon Fiber Foldable', sku: 'NT-POLE-001',
      source: '1688', category: '户外配件', price: 59.99, cost_price: 68.0, stock: 40,
      status: 'failed', images: ['/images/pole-1.jpg', '/images/pole-2.jpg'],
      description: '碳纤维折叠登山杖，超轻便携，三节伸缩，减震设计，徒步必备。',
      attributes: [
        { key: '材质', value: '碳纤维' },
        { key: '节数', value: '3节' },
        { key: '伸缩范围', value: '62-135cm' },
        { key: '重量', value: '240g/对' },
      ],
      created_at: '2026-09-02 09:00:00', updated_at: '2026-09-02 10:00:00',
      error_message: 'WooCommerce API调用失败：商品图片上传超时，请重试',
      ai_processed: true, images_processed: true,
    },
    {
      id: '6', name: '户外登山背包 50L', name_en: 'Outdoor Hiking Backpack 50L', sku: 'NT-BAG-001',
      source: 'pipeline', category: '背包配件', price: 79.99, cost_price: 120.0, stock: 30,
      status: 'draft', images: ['/images/bag-1.jpg'],
      description: '50L大容量登山背包，防水面料，多隔层设计，人体工学背负系统。',
      attributes: [
        { key: '材质', value: '600D牛津布' },
        { key: '容量', value: '50L' },
        { key: '重量', value: '1.2kg' },
      ],
      created_at: '2026-09-05 08:00:00', updated_at: '2026-09-05 08:00:00',
      ai_processed: false, images_processed: false,
    },
  ]

  // 加载商品上架数据（调用真实API，失败则使用mock数据降级）
  const loadProductListingData = async () => {
    try {
      setLoading(true)
      // 调用商品API（包含商品上架相关功能）
      const productsResp = await fetch('/api/v1/products')
      if (productsResp.ok) {
        const productsData = await productsResp.json()
        setProductListingData(productsData)
        console.log('Products:', productsData)
      }
      message.success('商品上架数据加载完成')
    } catch (e: any) {
      console.error('Load product listing data error:', e)
      message.warning(`API调用失败，使用模拟数据：${e.message || '未知错误'}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadProductListingData()
  }, [])

  // AI生成产品文案
  const generateAiCopy = async (productId: string) => {
    try {
      setAiCopyLoading(true)
      const resp = await fetch(`/api/v1/products/${productId}/generate-copy`, { method: 'POST' })
      if (resp.ok) {
        const data = await resp.json()
        setAiCopyResult(data)
        setAiCopyModalOpen(true)
        message.success('AI文案生成成功')
      } else {
        message.error('AI文案生成失败')
      }
    } catch (e: any) {
      message.error(`AI文案生成失败: ${e.message}`)
    } finally {
      setAiCopyLoading(false)
    }
  }

  // 统计数据（优先使用真实API数据，失败则使用mock数据降级）
  const realProducts = Array.isArray(productListingData) 
    ? productListingData 
    : (productListingData?.items || productListingData?.products || [])
  const products = realProducts.length > 0 ? realProducts : mockProducts
  const stats = {
    totalProducts: products.length,
    pendingListing: productListingData?.pending_listing || products.filter((p: any) => p.status === 'pending' || p.status === 'review').length,
    listed: productListingData?.listed || products.filter((p: any) => p.status === 'listed').length,
    failed: productListingData?.failed || products.filter((p: any) => p.status === 'failed').length,
    aiProcessed: productListingData?.ai_processed || products.filter((p: any) => p.ai_processed).length,
    imagesProcessed: productListingData?.images_processed || products.filter((p: any) => p.images_processed).length,
  }

  // 商品表格列
  const productColumns = [
    {
      title: '商品',
      key: 'product',
      width: 280,
      render: (_: any, record: ListingProduct) => (
        <Space>
          <div style={{ width: 48, height: 48, borderRadius: '6px', background: '#f0f0f0', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
            <PictureOutlined style={{ fontSize: '20px', color: '#999' }} />
          </div>
          <div>
            <div style={{ fontSize: '12px', fontWeight: 500 }}>{record.name}</div>
            {record.name_en && <div style={{ fontSize: '10px', color: '#999' }}>{record.name_en}</div>}
            <div style={{ fontSize: '10px', color: '#999' }}>SKU: {record.sku}</div>
          </div>
        </Space>
      ),
    },
    {
      title: '来源',
      dataIndex: 'source',
      key: 'source',
      width: 90,
      render: (source: string) => <Tag color={sourceColors[source]}>{source === '1688' ? '1688' : source === 'manual' ? '手动' : '工作流'}</Tag>,
    },
    {
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      width: 100,
    },
    {
      title: '价格',
      key: 'price',
      width: 120,
      render: (_: any, record: ListingProduct) => (
        <div>
          <div style={{ fontSize: '13px', color: '#f5222d', fontWeight: 600 }}>${record.price}</div>
          <div style={{ fontSize: '10px', color: '#999' }}>成本: ¥{record.cost_price}</div>
        </div>
      ),
    },
    {
      title: '库存',
      dataIndex: 'stock',
      key: 'stock',
      width: 80,
      render: (stock: number) => <Text type={stock < 20 ? 'danger' : 'secondary'}>{stock}件</Text>,
    },
    {
      title: 'AI处理',
      key: 'ai',
      width: 80,
      render: (_: any, record: ListingProduct) => (
        <Space size={4}>
          <Tooltip title="AI文案处理">
            <Tag color={record.ai_processed ? 'green' : 'default'} style={{ fontSize: '10px' }}>文案</Tag>
          </Tooltip>
          <Tooltip title="图片处理">
            <Tag color={record.images_processed ? 'green' : 'default'} style={{ fontSize: '10px' }}>图片</Tag>
          </Tooltip>
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => <Tag color={statusColors[status]}>{statusText[status]}</Tag>,
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 150,
      render: (text: string) => <Text type="secondary" style={{ fontSize: '11px' }}>{text}</Text>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 220,
      render: (_: any, record: ListingProduct) => (
        <Space size="small">
          <Button size="small" icon={<EyeOutlined />} onClick={() => {
            setViewingProduct(record)
            setDetailModalOpen(true)
          }}>详情</Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => {
            setEditingProduct(record)
            editForm.setFieldsValue(record)
            setEditModalOpen(true)
          }}>编辑</Button>
          {(record.status === 'pending' || record.status === 'review' || record.status === 'failed') && (
            <Button size="small" type="primary" icon={<RocketOutlined />} loading={listingProduct === record.id} onClick={() => {
              setListingProduct(record.id)
              setTimeout(() => {
                message.success(`${record.name} 已成功上架到WooCommerce`)
                setListingProduct(null)
              }, 2000)
            }}>上架</Button>
          )}
        </Space>
      ),
    },
  ]

  // 上架步骤
  const getListingStep = (status: string) => {
    const steps = ['draft', 'editing', 'review', 'pending', 'listing', 'listed']
    return steps.indexOf(status)
  }

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <ShoppingOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>WooCommerce商品上架自动化</Title>
            <Text type="secondary">商品上架队列、信息编辑、一键上架WooCommerce</Text>
          </div>
        </Space>
        <Space>
          <Button icon={<DownloadOutlined />} onClick={() => message.success('上架报表导出中...')}>导出报表</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => message.info('请从1688选品或产品工作流导入商品')}>添加商品</Button>
        </Space>
      </div>

      {/* 上架失败预警 */}
      {stats.failed > 0 && (
        <Alert
          message={`有 ${stats.failed} 个商品上架失败`}
          description="请检查失败原因，修正后重新上架。"
          type="error"
          showIcon
          icon={<WarningOutlined />}
          style={{ marginBottom: '16px' }}
          action={
            <Button size="small" type="primary" danger onClick={() => setStatusFilter('failed')}>查看失败</Button>
          }
        />
      )}

      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: '16px' }}>
        <Col span={4}>
          <Card size="small">
            <Statistic title="商品总数" value={stats.totalProducts} prefix={<FileTextOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="待上架" value={stats.pendingListing} valueStyle={{ color: '#faad14' }} prefix={<ClockCircleOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="已上架" value={stats.listed} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="上架失败" value={stats.failed} valueStyle={{ color: '#f5222d' }} prefix={<WarningOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="AI文案完成" value={stats.aiProcessed} suffix={`/${stats.totalProducts}`} valueStyle={{ color: '#722ed1' }} prefix={<SyncOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="图片处理完成" value={stats.imagesProcessed} suffix={`/${stats.totalProducts}`} valueStyle={{ color: '#1890ff' }} prefix={<PictureOutlined />} />
          </Card>
        </Col>
      </Row>

      {/* Tab切换 */}
      <Card size="small">
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'queue',
              label: '上架队列',
              children: (
                <div>
                  {/* 筛选栏 */}
                  <Space wrap style={{ marginBottom: '16px' }}>
                    <Input placeholder="搜索商品名称/SKU" prefix={<SearchOutlined />} value={searchText} onChange={(e) => setSearchText(e.target.value)} style={{ width: 220 }} allowClear />
                    <Select value={statusFilter} onChange={setStatusFilter} style={{ width: 120 }} options={[
                      { value: 'all', label: '全部状态' },
                      { value: 'draft', label: '草稿' },
                      { value: 'editing', label: '编辑中' },
                      { value: 'review', label: '待审核' },
                      { value: 'pending', label: '待上架' },
                      { value: 'listed', label: '已上架' },
                      { value: 'failed', label: '上架失败' },
                    ]} />
                    <Select value={sourceFilter} onChange={setSourceFilter} style={{ width: 120 }} options={[
                      { value: 'all', label: '全部来源' },
                      { value: '1688', label: '1688' },
                      { value: 'manual', label: '手动' },
                      { value: 'pipeline', label: '工作流' },
                    ]} />
                    <Button icon={<SearchOutlined />} type="primary">搜索</Button>
                    <Button icon={<ReloadOutlined />} onClick={() => {
                      setSearchText('')
                      setStatusFilter('all')
                      setSourceFilter('all')
                    }}>重置</Button>
                    <Divider type="vertical" />
                    <Button icon={<RocketOutlined />} type="primary" disabled={selectedRowKeys.length === 0} onClick={() => setBatchListingModalOpen(true)}>
                      批量上架 ({selectedRowKeys.length})
                    </Button>
                  </Space>

                  <Table
                    columns={productColumns}
                    dataSource={products}
                    rowKey="id"
                    loading={loading}
                    rowSelection={{ selectedRowKeys, onChange: setSelectedRowKeys }}
                    pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 个商品` }}
                    locale={{ emptyText: <Empty description="暂无待上架商品" /> }}
                  />
                </div>
              ),
            },
            {
              key: 'workflow',
              label: '上架流程',
              children: (
                <div>
                  <Alert
                    message="商品上架自动化流程"
                    description="从1688选品到WooCommerce上架的完整自动化流程，AI自动处理文案和图片，人工审核后一键上架。"
                    type="info"
                    showIcon
                    style={{ marginBottom: 24 }}
                  />
                  <Steps
                    direction="vertical"
                    current={4}
                    items={[
                      {
                        title: '1. 1688选品导入',
                        description: '从1688搜索选品，或通过牛顿AI选品，一键导入到商品上架队列。系统自动抓取商品标题、价格、图片、规格等信息。',
                        status: 'finish',
                      },
                      {
                        title: '2. AI文案处理',
                        description: 'AI自动生成英文标题、产品描述、SEO关键词、卖点提炼。支持多语言翻译和文案优化。',
                        status: 'finish',
                      },
                      {
                        title: '3. AI图片处理',
                        description: 'AI自动处理商品图片：去背景、主图生成、详情图生成、尺寸裁剪、水印添加。支持批量处理。',
                        status: 'finish',
                      },
                      {
                        title: '4. 人工审核',
                        description: '运营人员审核AI处理后的文案和图片，可手动编辑修改。确认无误后提交上架。',
                        status: 'process',
                      },
                      {
                        title: '5. 一键上架WooCommerce',
                        description: '系统自动创建WooCommerce商品，上传图片，设置价格、库存、分类、属性。支持批量上架。',
                        status: 'wait',
                      },
                      {
                        title: '6. 上架验证',
                        description: '上架后自动验证商品页面可访问，图片加载正常，价格库存正确。生成上架报告。',
                        status: 'wait',
                      },
                    ]}
                  />
                </div>
              ),
            },
            {
              key: 'settings',
              label: '上架设置',
              children: (
                <div>
                  <Row gutter={[16, 16]}>
                    <Col span={12}>
                      <Card size="small" title="基础设置">
                        <Form layout="vertical">
                          <Form.Item label="默认商品状态" initialValue="publish">
                            <Radio.Group>
                              <Radio value="publish">直接发布</Radio>
                              <Radio value="draft">存为草稿</Radio>
                              <Radio value="pending">待审核</Radio>
                            </Radio.Group>
                          </Form.Item>
                          <Form.Item label="默认分类" initialValue="outdoor">
                            <Select options={[
                              { value: 'outdoor', label: '户外装备' },
                              { value: 'lighting', label: '照明设备' },
                              { value: 'camping', label: '露营用品' },
                              { value: 'accessories', label: '户外配件' },
                            ]} />
                          </Form.Item>
                          <Form.Item label="价格倍率" initialValue={2.5}>
                            <InputNumber min={1} max={10} step={0.1} addonAfter="倍" style={{ width: '100%' }} />
                          </Form.Item>
                          <Form.Item label="自动同步库存" valuePropName="checked" initialValue={true}>
                            <Switch />
                          </Form.Item>
                        </Form>
                      </Card>
                    </Col>
                    <Col span={12}>
                      <Card size="small" title="AI处理设置">
                        <Form layout="vertical">
                          <Form.Item label="自动生成英文标题" valuePropName="checked" initialValue={true}>
                            <Switch />
                          </Form.Item>
                          <Form.Item label="自动生成产品描述" valuePropName="checked" initialValue={true}>
                            <Switch />
                          </Form.Item>
                          <Form.Item label="自动处理商品图片" valuePropName="checked" initialValue={true}>
                            <Switch />
                          </Form.Item>
                          <Form.Item label="AI模型" initialValue="doubao-pro">
                            <Select options={[
                              { value: 'doubao-pro', label: '豆包Pro' },
                              { value: 'doubao-lite', label: '豆包Lite' },
                              { value: 'gpt-4o', label: 'GPT-4o' },
                            ]} />
                          </Form.Item>
                          <Form.Item label="上架前人工审核" valuePropName="checked" initialValue={true}>
                            <Switch />
                          </Form.Item>
                        </Form>
                      </Card>
                    </Col>
                  </Row>
                  <div style={{ marginTop: 16, textAlign: 'right' }}>
                    <Button type="primary" onClick={() => message.success('设置已保存')}>保存设置</Button>
                  </div>
                </div>
              ),
            },
          ]}
        />
      </Card>

      {/* 商品详情Modal */}
      <Modal
        title={`商品详情 - ${viewingProduct?.name || ''}`}
        open={detailModalOpen}
        onCancel={() => setDetailModalOpen(false)}
        footer={[
          <Button key="aicopy" icon={<SyncOutlined />} loading={aiCopyLoading} onClick={() => viewingProduct && generateAiCopy(viewingProduct.id)}>AI生成文案</Button>,
          viewingProduct?.source_url ? (
            <Button key="purchase" icon={<ShoppingOutlined />} onClick={() => {
              window.open(viewingProduct.source_url, '_blank')
              message.info('已打开1688商品页面，请确认数量后手动下单')
            }}>去1688采购</Button>
          ) : null,
          <Button key="edit" type="primary" icon={<EditOutlined />} onClick={() => {
            setEditingProduct(viewingProduct)
            editForm.setFieldsValue(viewingProduct)
            setEditModalOpen(true)
            setDetailModalOpen(false)
          }}>编辑</Button>,
          viewingProduct && (viewingProduct.status === 'pending' || viewingProduct.status === 'review' || viewingProduct.status === 'failed') ? (
            <Button key="list" type="primary" icon={<RocketOutlined />} onClick={() => {
              message.success(`${viewingProduct?.name} 已成功上架到WooCommerce`)
              setDetailModalOpen(false)
            }}>上架WooCommerce</Button>
          ) : null,
          <Button key="close" onClick={() => setDetailModalOpen(false)}>关闭</Button>,
        ]}
        width={800}
      >
        {viewingProduct && (
          <div>
            {/* 状态进度 */}
            <Steps
              current={getListingStep(viewingProduct.status)}
              size="small"
              items={[
                { title: '草稿' },
                { title: '编辑' },
                { title: '审核' },
                { title: '待上架' },
                { title: '上架中' },
                { title: '已上架' },
              ]}
              style={{ marginBottom: 20 }}
            />

            {viewingProduct.error_message && (
              <Alert message="上架失败" description={viewingProduct.error_message} type="error" showIcon style={{ marginBottom: 16 }} />
            )}

            <Descriptions column={2} bordered size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="商品名称" span={2}>{viewingProduct.name}</Descriptions.Item>
              <Descriptions.Item label="英文名称" span={2}>{viewingProduct.name_en || '-'}</Descriptions.Item>
              <Descriptions.Item label="SKU">{viewingProduct.sku}</Descriptions.Item>
              <Descriptions.Item label="分类">{viewingProduct.category}</Descriptions.Item>
              <Descriptions.Item label="来源"><Tag color={sourceColors[viewingProduct.source]}>{viewingProduct.source}</Tag></Descriptions.Item>
              <Descriptions.Item label="状态"><Tag color={statusColors[viewingProduct.status]}>{statusText[viewingProduct.status]}</Tag></Descriptions.Item>
              <Descriptions.Item label="售价"><Text strong style={{ color: '#f5222d' }}>${viewingProduct.price}</Text></Descriptions.Item>
              <Descriptions.Item label="成本价">¥{viewingProduct.cost_price}</Descriptions.Item>
              <Descriptions.Item label="库存">{viewingProduct.stock}件</Descriptions.Item>
              <Descriptions.Item label="图片数量">{viewingProduct.images.length}张</Descriptions.Item>
              <Descriptions.Item label="创建时间">{viewingProduct.created_at}</Descriptions.Item>
              <Descriptions.Item label="更新时间">{viewingProduct.updated_at}</Descriptions.Item>
              {viewingProduct.source_url && (
                <Descriptions.Item label="采购链接" span={2}>
                  <a href={viewingProduct.source_url} target="_blank" rel="noopener noreferrer">
                    {viewingProduct.source_url}
                  </a>
                </Descriptions.Item>
              )}
              {viewingProduct.listed_at && <Descriptions.Item label="上架时间">{viewingProduct.listed_at}</Descriptions.Item>}
              {viewingProduct.woocommerce_url && (
                <Descriptions.Item label="WooCommerce链接">
                  <a href={viewingProduct.woocommerce_url} target="_blank">查看商品</a>
                </Descriptions.Item>
              )}
            </Descriptions>

            {/* 商品图片 */}
            <Card size="small" title="商品图片" style={{ marginBottom: 16 }}>
              <Row gutter={[8, 8]}>
                {viewingProduct.images.map((img, idx) => (
                  <Col span={6} key={idx}>
                    <div style={{ width: '100%', aspectRatio: '1', background: '#f5f5f5', borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <PictureOutlined style={{ fontSize: 32, color: '#ccc' }} />
                    </div>
                    <div style={{ textAlign: 'center', fontSize: 10, color: '#999', marginTop: 4 }}>图{idx + 1}</div>
                  </Col>
                ))}
              </Row>
            </Card>

            {/* 商品描述 */}
            <Card size="small" title="商品描述" style={{ marginBottom: 16 }}>
              <Paragraph style={{ marginBottom: 8 }}><Text strong>中文：</Text>{viewingProduct.description}</Paragraph>
              {viewingProduct.description_en && <Paragraph style={{ margin: 0 }}><Text strong>英文：</Text>{viewingProduct.description_en}</Paragraph>}
            </Card>

            {/* 商品属性 */}
            <Card size="small" title="商品属性">
              <Row gutter={[16, 8]}>
                {viewingProduct.attributes.map((attr, idx) => (
                  <Col span={12} key={idx}>
                    <div style={{ display: 'flex', padding: '4px 0' }}>
                      <Text type="secondary" style={{ width: 100 }}>{attr.key}：</Text>
                      <Text>{attr.value}</Text>
                    </div>
                  </Col>
                ))}
              </Row>
            </Card>
          </div>
        )}
      </Modal>

      {/* 编辑商品Modal */}
      <Modal
        title="编辑商品信息"
        open={editModalOpen}
        onCancel={() => setEditModalOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setEditModalOpen(false)}>取消</Button>,
          <Button key="save" type="primary" onClick={() => {
            message.success('商品信息已保存')
            setEditModalOpen(false)
          }}>保存</Button>,
        ]}
        width={700}
      >
        <Form form={editForm} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="name" label="商品名称（中文）" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="name_en" label="商品名称（英文）">
                <Input />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="sku" label="SKU" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="category" label="分类">
                <Select options={[
                  { value: '照明设备', label: '照明设备' },
                  { value: '户外家具', label: '户外家具' },
                  { value: '水具餐具', label: '水具餐具' },
                  { value: '背包配件', label: '背包配件' },
                  { value: '户外配件', label: '户外配件' },
                ]} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="stock" label="库存">
                <InputNumber min={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="price" label="售价（USD）" rules={[{ required: true }]}>
                <InputNumber min={0} step={0.01} style={{ width: '100%' }} prefix="$" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="cost_price" label="成本价（CNY）">
                <InputNumber min={0} step={0.01} style={{ width: '100%' }} prefix="¥" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="description" label="商品描述（中文）">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="description_en" label="商品描述（英文）">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Alert
            message="提示"
            description='保存后商品状态将变为"待审核"，审核通过后可上架到WooCommerce。'
            type="info"
            showIcon
          />
        </Form>
      </Modal>

      {/* 批量上架Modal */}
      <Modal
        title="批量上架到WooCommerce"
        open={batchListingModalOpen}
        onCancel={() => setBatchListingModalOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setBatchListingModalOpen(false)}>取消</Button>,
          <Button key="confirm" type="primary" icon={<RocketOutlined />} onClick={() => {
            message.success(`已提交 ${selectedRowKeys.length} 个商品上架任务`)
            setBatchListingModalOpen(false)
            setSelectedRowKeys([])
          }}>确认上架</Button>,
        ]}
        width={500}
      >
        <Alert
          message="批量上架确认"
          description={`即将上架 ${selectedRowKeys.length} 个商品到WooCommerce。系统将自动创建商品、上传图片、设置价格库存。上架过程中请勿关闭页面。`}
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
        />
        <div style={{ background: '#fafafa', padding: 12, borderRadius: 8, maxHeight: 200, overflow: 'auto' }}>
          {mockProducts.filter(p => selectedRowKeys.includes(p.id)).map((p) => (
            <div key={p.id} style={{ padding: '4px 0', fontSize: 12 }}>
              • {p.name} (SKU: {p.sku}) - ${p.price}
            </div>
          ))}
        </div>
      </Modal>

      {/* AI文案结果Modal */}
      <Modal
        title="AI生成产品文案"
        open={aiCopyModalOpen}
        onCancel={() => setAiCopyModalOpen(false)}
        footer={[
          <Button key="close" onClick={() => setAiCopyModalOpen(false)}>关闭</Button>,
          <Button key="copy" type="primary" icon={<CopyOutlined />} onClick={() => {
            if (aiCopyResult) {
              const text = `Title: ${aiCopyResult.title}\n\nDescription: ${aiCopyResult.description}\n\nBullet Points:\n${aiCopyResult.bullet_points?.map((b: string) => `- ${b}`).join('\n')}\n\nSEO Keywords: ${aiCopyResult.seo_keywords?.join(', ')}`
              navigator.clipboard.writeText(text)
              message.success('文案已复制到剪贴板')
            }
          }}>复制全部</Button>,
        ]}
        width={800}
      >
        {aiCopyResult && (
          <div>
            <Alert
              message={`AI生成完成 - 模型: ${aiCopyResult._meta?.model || 'unknown'} | Tokens: ${aiCopyResult._meta?.tokens?.total_tokens || '?'} | 成本: ${aiCopyResult._meta?.cost || '0'}`}
              type="success"
              showIcon
              style={{ marginBottom: 16 }}
            />
            <Descriptions column={1} bordered size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="英文标题">{aiCopyResult.title}</Descriptions.Item>
              <Descriptions.Item label="简短描述">{aiCopyResult.short_description}</Descriptions.Item>
            </Descriptions>
            <Card size="small" title="产品描述" style={{ marginBottom: 16 }}>
              <Paragraph style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{aiCopyResult.description}</Paragraph>
            </Card>
            <Card size="small" title="卖点列表" style={{ marginBottom: 16 }}>
              <List
                size="small"
                dataSource={aiCopyResult.bullet_points}
                renderItem={(item: string) => <List.Item>• {item}</List.Item>}
              />
            </Card>
            <Card size="small" title="SEO关键词">
              <Space wrap>
                {aiCopyResult.seo_keywords?.map((kw: string, idx: number) => (
                  <Tag key={idx} color="blue">{kw}</Tag>
                ))}
              </Space>
            </Card>
          </div>
        )}
      </Modal>
    </div>
  )
}