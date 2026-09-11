import { useState } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Input, Select,
  Statistic, Row, Col, Spin, message, Modal, Descriptions,
  Badge, Tooltip, Empty, Tabs, Progress, Divider, Alert,
  Radio, Slider, Checkbox
} from 'antd'
import {
  ShoppingOutlined, ReloadOutlined, SearchOutlined,
  EyeOutlined, PlusOutlined, EditOutlined,
  CheckCircleOutlined, CloseCircleOutlined, WarningOutlined,
  SyncOutlined, ClockCircleOutlined, ShopOutlined,
  DollarOutlined, BarChartOutlined, FireOutlined,
  ThunderboltOutlined, ImportOutlined, ExportOutlined,
  RocketOutlined, StarOutlined, ArrowUpOutlined, ArrowDownOutlined
} from '@ant-design/icons'

const { Title, Text, Paragraph } = Typography

interface SourcingProduct {
  id: string
  name: string
  name_en?: string
  source: '1688' | 'manual' | 'ai'
  source_url?: string
  category: string
  cost_price: number
  suggested_price: number
  profit_margin: number
  market_demand: 'high' | 'medium' | 'low'
  competition: 'high' | 'medium' | 'low'
  status: 'pending' | 'analyzing' | 'approved' | 'rejected' | 'listed'
  score: number
  sales_30d: number
  search_volume: number
  supplier: string
  moq: number
  created_at: string
  tags: string[]
  notes?: string
}

const statusColors: Record<string, string> = {
  pending: 'default',
  analyzing: 'blue',
  approved: 'green',
  rejected: 'red',
  listed: 'purple',
}

const statusText: Record<string, string> = {
  pending: '待分析',
  analyzing: '分析中',
  approved: '已通过',
  rejected: '已拒绝',
  listed: '已上架',
}

const demandColors: Record<string, string> = {
  high: 'red',
  medium: 'orange',
  low: 'green',
}

const demandText: Record<string, string> = {
  high: '高需求',
  medium: '中需求',
  low: '低需求',
}

export default function SourcingPage() {
  const [activeTab, setActiveTab] = useState('list')
  const [loading, setLoading] = useState(false)
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [viewingProduct, setViewingProduct] = useState<SourcingProduct | null>(null)
  const [statusFilter, setStatusFilter] = useState('all')
  const [categoryFilter, setCategoryFilter] = useState('all')
  const [searchText, setSearchText] = useState('')
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])
  const [analyzing, setAnalyzing] = useState(false)
  // 1688搜索状态
  const [searchKeyword, setSearchKeyword] = useState('')
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchResults, setSearchResults] = useState<any[]>([])
  const [importLoading, setImportLoading] = useState<string | null>(null)

  const mockProducts: SourcingProduct[] = [
    { id: '1', name: 'LED头灯 Pro 强光充电', name_en: 'LED Headlamp Pro Rechargeable', source: '1688', source_url: 'https://detail.1688.com/offer/1078487117828.html', category: '照明设备', cost_price: 28.5, suggested_price: 49.99, profit_margin: 75.4, market_demand: 'high', competition: 'medium', status: 'approved', score: 88, sales_30d: 1250, search_volume: 8500, supplier: '深圳户外装备有限公司', moq: 50, created_at: '2026-09-05 10:00:00', tags: ['爆款', '高利润', '低竞争'] },
    { id: '2', name: '太阳能露营灯 折叠', name_en: 'Solar Camping Lantern Foldable', source: 'ai', category: '照明设备', cost_price: 45.0, suggested_price: 39.99, profit_margin: -11.1, market_demand: 'medium', competition: 'high', status: 'rejected', score: 45, sales_30d: 320, search_volume: 3200, supplier: '义乌户外用品批发', moq: 30, created_at: '2026-09-04 15:00:00', tags: ['价格倒挂', '高竞争'], notes: '建议售价低于成本价，不建议采购' },
    { id: '3', name: '保温水壶1L 304不锈钢', name_en: 'Insulated Water Bottle 1L', source: '1688', category: '水具餐具', cost_price: 32.0, suggested_price: 29.99, profit_margin: -6.3, market_demand: 'high', competition: 'high', status: 'pending', score: 62, sales_30d: 2100, search_volume: 12000, supplier: '深圳户外装备有限公司', moq: 100, created_at: '2026-09-05 08:00:00', tags: ['高需求', '高竞争'] },
    { id: '4', name: '户外自动帐篷 3-4人', name_en: 'Outdoor Automatic Tent 3-4 Person', source: 'manual', category: '户外家具', cost_price: 185.0, suggested_price: 89.99, profit_margin: -51.4, market_demand: 'medium', competition: 'medium', status: 'analyzing', score: 55, sales_30d: 450, search_volume: 5600, supplier: '广州帐篷制造厂', moq: 20, created_at: '2026-09-03 11:00:00', tags: ['大件商品', '物流成本高'] },
    { id: '5', name: '登山杖 碳纤维折叠', name_en: 'Trekking Poles Carbon Fiber', source: '1688', category: '户外配件', cost_price: 68.0, suggested_price: 59.99, profit_margin: -11.8, market_demand: 'medium', competition: 'low', status: 'approved', score: 78, sales_30d: 680, search_volume: 4500, supplier: '深圳户外装备有限公司', moq: 40, created_at: '2026-09-02 09:00:00', tags: ['低竞争', '高复购'] },
    { id: '6', name: '户外登山背包 50L', name_en: 'Outdoor Hiking Backpack 50L', source: 'ai', category: '背包配件', cost_price: 120.0, suggested_price: 79.99, profit_margin: -33.3, market_demand: 'high', competition: 'medium', status: 'listed', score: 82, sales_30d: 890, search_volume: 9800, supplier: '东莞背包工厂', moq: 30, created_at: '2026-09-01 10:00:00', tags: ['已上架', '热销'] },
    { id: '7', name: '便携折叠桌椅套装', name_en: 'Portable Folding Table and Chairs Set', source: '1688', category: '户外家具', cost_price: 156.0, suggested_price: 129.99, profit_margin: -16.7, market_demand: 'low', competition: 'low', status: 'pending', score: 58, sales_30d: 120, search_volume: 1800, supplier: '义乌户外用品批发', moq: 10, created_at: '2026-09-05 09:00:00', tags: ['低需求', '低竞争'] },
    { id: '8', name: '防水手机袋 触屏', name_en: 'Waterproof Phone Pouch Touchscreen', source: '1688', category: '户外配件', cost_price: 8.5, suggested_price: 19.99, profit_margin: 135.2, market_demand: 'high', competition: 'high', status: 'approved', score: 85, sales_30d: 3500, search_volume: 15000, supplier: '深圳户外装备有限公司', moq: 200, created_at: '2026-08-30 14:00:00', tags: ['超高利润', '引流款'] },
  ]

  const stats = {
    total: mockProducts.length,
    pending: mockProducts.filter(p => p.status === 'pending' || p.status === 'analyzing').length,
    approved: mockProducts.filter(p => p.status === 'approved').length,
    rejected: mockProducts.filter(p => p.status === 'rejected').length,
    listed: mockProducts.filter(p => p.status === 'listed').length,
    avgScore: Math.round(mockProducts.reduce((s, p) => s + p.score, 0) / mockProducts.length),
  }

  // 1688商品搜索
  const handleSearch1688 = async () => {
    if (!searchKeyword || searchKeyword.trim().length === 0) {
      message.error('请输入搜索关键词')
      return
    }

    try {
      setSearchLoading(true)
      setSearchResults([])
      const resp = await fetch(`/api/v1/sourcing/1688/search?keyword=${encodeURIComponent(searchKeyword)}&page=1&page_size=20`)
      const data = await resp.json()

      if (data.success && data.data?.products) {
        setSearchResults(data.data.products)
        message.success(`找到 ${data.data.products.length} 个1688商品`)
      } else {
        message.warning(data.error || '未找到相关商品')
        setSearchResults([])
      }
    } catch (e: any) {
      console.error('Search 1688 error:', e)
      message.error(`搜索失败：${e.message || '网络错误'}`)
    } finally {
      setSearchLoading(false)
    }
  }

  // 导入1688商品到产品工作流
  const handleImportToPipeline = async (product: any) => {
    const productId = product.product_id || product.id || product.offer_id
    if (!productId) {
      message.error('无法获取商品ID')
      return
    }

    try {
      setImportLoading(productId)
      const resp = await fetch('/api/v1/product-pipeline/import-from-1688', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url_or_id: String(productId),
          auto_run_pipeline: false,
        }),
      })

      const data = await resp.json()

      if (data.success && data.data?.product_info) {
        const info = data.data.product_info
        message.success(`已导入：${info.name || '未知商品'}（SKU: ${info.sku || '未生成'}，图片: ${info.images?.length || 0}张）`)
        // 跳转到产品工作流页面
        window.location.hash = '#/product-pipeline'
      } else {
        message.error(`导入失败：${data.error || '未知错误'}`)
      }
    } catch (e: any) {
      console.error('Import to pipeline error:', e)
      message.error(`导入失败：${e.message || '网络错误'}`)
    } finally {
      setImportLoading(null)
    }
  }

  const productColumns = [
    {
      title: '商品',
      key: 'product',
      width: 250,
      render: (_: any, record: SourcingProduct) => (
        <Space>
          <div style={{ width: 48, height: 48, borderRadius: '6px', background: '#f0f0f0', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <ShoppingOutlined style={{ fontSize: '20px', color: '#999' }} />
          </div>
          <div>
            <div style={{ fontWeight: 500, fontSize: 13 }}>{record.name}</div>
            {record.name_en && <div style={{ fontSize: 10, color: '#999' }}>{record.name_en}</div>}
            <div style={{ fontSize: 10, color: '#999' }}>供应商：{record.supplier}</div>
          </div>
        </Space>
      ),
    },
    {
      title: '来源',
      dataIndex: 'source',
      key: 'source',
      width: 80,
      render: (source: string) => <Tag color={source === '1688' ? 'orange' : source === 'ai' ? 'purple' : 'blue'}>{source === '1688' ? '1688' : source === 'ai' ? 'AI推荐' : '手动'}</Tag>,
    },
    {
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      width: 100,
    },
    {
      title: '成本价',
      dataIndex: 'cost_price',
      key: 'cost_price',
      width: 90,
      render: (price: number) => <Text>¥{price}</Text>,
    },
    {
      title: '建议售价',
      dataIndex: 'suggested_price',
      key: 'suggested_price',
      width: 100,
      render: (price: number) => <Text strong>${price}</Text>,
    },
    {
      title: '利润率',
      dataIndex: 'profit_margin',
      key: 'profit_margin',
      width: 100,
      render: (margin: number) => (
        <Text type={margin > 50 ? 'success' : margin > 0 ? 'warning' : 'danger'} strong>
          {margin > 0 ? '+' : ''}{margin.toFixed(1)}%
        </Text>
      ),
    },
    {
      title: '市场需求',
      dataIndex: 'market_demand',
      key: 'market_demand',
      width: 100,
      render: (demand: string) => <Tag color={demandColors[demand]}>{demandText[demand]}</Tag>,
    },
    {
      title: '选品评分',
      dataIndex: 'score',
      key: 'score',
      width: 120,
      render: (score: number) => (
        <div>
          <Progress percent={score} size="small" strokeColor={score >= 80 ? '#52c41a' : score >= 60 ? '#faad14' : '#f5222d'} format={(p) => `${p}分`} />
        </div>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (status: string) => <Tag color={statusColors[status]}>{statusText[status]}</Tag>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_: any, record: SourcingProduct) => (
        <Space size="small">
          <Button size="small" icon={<EyeOutlined />} onClick={() => {
            setViewingProduct(record)
            setDetailModalOpen(true)
          }}>详情</Button>
          {(record.status === 'pending' || record.status === 'analyzing') && (
            <>
              <Button size="small" type="primary" icon={<CheckCircleOutlined />} onClick={() => message.success(`${record.name} 已通过选品`)}>通过</Button>
              <Button size="small" danger icon={<CloseCircleOutlined />} onClick={() => message.info(`${record.name} 已拒绝`)}>拒绝</Button>
            </>
          )}
          {record.status === 'approved' && (
            <Button size="small" type="primary" icon={<RocketOutlined />} onClick={() => message.success('已加入上架队列')}>上架</Button>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <ShoppingOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>选品管理</Title>
            <Text type="secondary">1688选品、AI分析、利润评估、上架决策</Text>
          </div>
        </Space>
        <Space>
          <Button icon={<ImportOutlined />} onClick={() => message.info('从1688导入商品')}>1688导入</Button>
          <Button icon={<ReloadOutlined />} onClick={() => message.success('数据已刷新')}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => message.info('手动添加选品')}>添加选品</Button>
        </Space>
      </div>

      {stats.pending > 0 && (
        <Alert
          message={`有 ${stats.pending} 个商品待分析`}
          description="请及时完成选品分析，通过后可加入上架队列。"
          type="warning"
          showIcon
          icon={<WarningOutlined />}
          style={{ marginBottom: '16px' }}
          action={<Button size="small" type="primary" onClick={() => setStatusFilter('pending')}>查看待分析</Button>}
        />
      )}

      <Row gutter={[16, 16]} style={{ marginBottom: '16px' }}>
        <Col span={4}><Card size="small"><Statistic title="选品总数" value={stats.total} prefix={<ShoppingOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="待分析" value={stats.pending} valueStyle={{ color: '#faad14' }} prefix={<ClockCircleOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="已通过" value={stats.approved} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="已拒绝" value={stats.rejected} valueStyle={{ color: '#f5222d' }} prefix={<CloseCircleOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="已上架" value={stats.listed} valueStyle={{ color: '#722ed1' }} prefix={<RocketOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="平均评分" value={stats.avgScore} suffix="分" valueStyle={{ color: '#1890ff' }} prefix={<StarOutlined />} /></Card></Col>
      </Row>

      <Card size="small">
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'list',
              label: '选品列表',
              children: (
                <div>
                  <Space wrap style={{ marginBottom: '16px' }}>
                    <Input placeholder="搜索商品名称/供应商" prefix={<SearchOutlined />} value={searchText} onChange={(e) => setSearchText(e.target.value)} style={{ width: 220 }} allowClear />
                    <Select value={statusFilter} onChange={setStatusFilter} style={{ width: 120 }} options={[
                      { value: 'all', label: '全部状态' },
                      { value: 'pending', label: '待分析' },
                      { value: 'analyzing', label: '分析中' },
                      { value: 'approved', label: '已通过' },
                      { value: 'rejected', label: '已拒绝' },
                      { value: 'listed', label: '已上架' },
                    ]} />
                    <Select value={categoryFilter} onChange={setCategoryFilter} style={{ width: 120 }} options={[
                      { value: 'all', label: '全部分类' },
                      { value: '照明设备', label: '照明设备' },
                      { value: '户外家具', label: '户外家具' },
                      { value: '水具餐具', label: '水具餐具' },
                      { value: '背包配件', label: '背包配件' },
                      { value: '户外配件', label: '户外配件' },
                    ]} />
                    <Button icon={<SearchOutlined />} type="primary">搜索</Button>
                    <Button icon={<ReloadOutlined />} onClick={() => { setSearchText(''); setStatusFilter('all'); setCategoryFilter('all'); }}>重置</Button>
                    <Divider type="vertical" />
                    <Button icon={<ThunderboltOutlined />} type="primary" loading={analyzing} onClick={() => {
                      setAnalyzing(true)
                      setTimeout(() => { message.success('批量AI分析完成'); setAnalyzing(false) }, 2000)
                    }}>AI批量分析</Button>
                    <Button icon={<CheckCircleOutlined />} disabled={selectedRowKeys.length === 0} onClick={() => message.success(`已通过 ${selectedRowKeys.length} 个商品`)}>批量通过</Button>
                    <Button icon={<RocketOutlined />} disabled={selectedRowKeys.length === 0} onClick={() => message.success(`已加入上架队列 ${selectedRowKeys.length} 个商品`)}>批量上架</Button>
                  </Space>

                  <Table
                    columns={productColumns}
                    dataSource={mockProducts}
                    rowKey="id"
                    loading={loading}
                    rowSelection={{ selectedRowKeys, onChange: setSelectedRowKeys }}
                    pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 个选品` }}
                    locale={{ emptyText: <Empty description="暂无选品数据" /> }}
                  />
                </div>
              ),
            },
            {
              key: '1688-search',
              label: '1688搜索',
              children: (
                <div>
                  <Alert message="1688商品搜索" description="输入关键词搜索1688商品，可一键导入产品工作流进行AI分析、主图生成和上架。" type="info" showIcon style={{ marginBottom: 16 }} />
                  <Space wrap style={{ marginBottom: '16px' }}>
                    <Input
                      placeholder="搜索1688商品，例如：头灯、帐篷、登山杖"
                      prefix={<SearchOutlined />}
                      value={searchKeyword}
                      onChange={(e) => setSearchKeyword(e.target.value)}
                      onPressEnter={handleSearch1688}
                      style={{ width: 320 }}
                      allowClear
                    />
                    <Button type="primary" icon={<SearchOutlined />} loading={searchLoading} onClick={handleSearch1688}>
                      搜索1688
                    </Button>
                    <Button icon={<ReloadOutlined />} onClick={() => { setSearchKeyword(''); setSearchResults([]); }}>
                      清空
                    </Button>
                  </Space>

                  {searchLoading && (
                    <div style={{ textAlign: 'center', padding: '40px 0' }}>
                      <Spin size="large" />
                      <div style={{ marginTop: 16, color: '#999' }}>正在搜索1688商品...</div>
                    </div>
                  )}

                  {!searchLoading && searchResults.length > 0 && (
                    <Table
                      columns={[
                        {
                          title: '商品',
                          key: 'product',
                          width: 300,
                          render: (_: any, record: any) => (
                            <Space>
                              <div style={{ width: 48, height: 48, borderRadius: '6px', background: '#f0f0f0', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
                                {record.image_url ? (
                                  <img src={record.image_url} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                                ) : (
                                  <ShoppingOutlined style={{ fontSize: '20px', color: '#999' }} />
                                )}
                              </div>
                              <div>
                                <div style={{ fontWeight: 500, fontSize: '13px', maxWidth: 220 }}>{record.subject || record.title || record.name}</div>
                                <div style={{ fontSize: '11px', color: '#999', marginTop: 2 }}>
                                  {record.supplier || record.company_name || '未知供应商'}
                                </div>
                              </div>
                            </Space>
                          ),
                        },
                        {
                          title: '价格',
                          key: 'price',
                          width: 120,
                          render: (_: any, record: any) => {
                            const price = record.price || record.price_range?.[0]?.price || 0
                            return <Text strong style={{ color: '#f5222d' }}>¥{Number(price).toFixed(2)}</Text>
                          },
                        },
                        {
                          title: '销量',
                          dataIndex: 'sale_count',
                          key: 'sales',
                          width: 100,
                          render: (v: any) => <Text>{v || '-'}</Text>,
                        },
                        {
                          title: '起订量',
                          dataIndex: 'moq',
                          key: 'moq',
                          width: 80,
                          render: (v: any) => <Text>{v || '-'}</Text>,
                        },
                        {
                          title: '操作',
                          key: 'action',
                          width: 180,
                          render: (_: any, record: any) => {
                            const productId = record.product_id || record.id || record.offer_id
                            return (
                              <Space>
                                <Button
                                  size="small"
                                  type="primary"
                                  icon={<ImportOutlined />}
                                  loading={importLoading === String(productId)}
                                  onClick={() => handleImportToPipeline(record)}
                                >
                                  导入工作流
                                </Button>
                                {record.detail_url || record.url ? (
                                  <Button size="small" icon={<EyeOutlined />} onClick={() => window.open(record.detail_url || record.url, '_blank')}>
                                    查看
                                  </Button>
                                ) : null}
                              </Space>
                            )
                          },
                        },
                      ]}
                      dataSource={searchResults}
                      rowKey={(record: any) => record.product_id || record.id || record.offer_id || Math.random()}
                      pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 个1688商品` }}
                      locale={{ emptyText: <Empty description="暂无搜索结果" /> }}
                    />
                  )}

                  {!searchLoading && searchResults.length === 0 && searchKeyword && (
                    <Empty description="未找到相关商品，请尝试其他关键词" style={{ padding: '40px 0' }} />
                  )}

                  {!searchLoading && searchResults.length === 0 && !searchKeyword && (
                    <Empty description="输入关键词开始搜索1688商品" style={{ padding: '40px 0' }} />
                  )}
                </div>
              ),
            },
            {
              key: 'analysis',
              label: '选品分析',
              children: (
                <div>
                  <Alert message="AI选品分析模型" description="基于市场需求、竞争度、利润空间、供应链稳定性等多维度进行AI评分，帮助快速决策。" type="info" showIcon style={{ marginBottom: 16 }} />
                  <Row gutter={16}>
                    <Col span={12}>
                      <Card size="small" title="评分分布">
                        <div style={{ padding: '20px 0' }}>
                          {[
                            { label: '优秀 (80-100分)', count: mockProducts.filter(p => p.score >= 80).length, color: '#52c41a' },
                            { label: '良好 (60-79分)', count: mockProducts.filter(p => p.score >= 60 && p.score < 80).length, color: '#faad14' },
                            { label: '一般 (40-59分)', count: mockProducts.filter(p => p.score >= 40 && p.score < 60).length, color: '#fa8c16' },
                            { label: '较差 (<40分)', count: mockProducts.filter(p => p.score < 40).length, color: '#f5222d' },
                          ].map((item, idx) => (
                            <div key={idx} style={{ marginBottom: 16 }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                                <Text>{item.label}</Text>
                                <Text strong>{item.count}个</Text>
                              </div>
                              <Progress percent={(item.count / mockProducts.length) * 100} size="small" strokeColor={item.color} showInfo={false} />
                            </div>
                          ))}
                        </div>
                      </Card>
                    </Col>
                    <Col span={12}>
                      <Card size="small" title="品类分布">
                        <div style={{ padding: '20px 0' }}>
                          {['照明设备', '户外家具', '水具餐具', '背包配件', '户外配件'].map((cat, idx) => {
                            const count = mockProducts.filter(p => p.category === cat).length
                            return (
                              <div key={idx} style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <Text>{cat}</Text>
                                <Space>
                                  <Progress percent={(count / mockProducts.length) * 100} size="small" style={{ width: 120 }} showInfo={false} />
                                  <Text strong>{count}个</Text>
                                </Space>
                              </div>
                            )
                          })}
                        </div>
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
        title={`选品详情 - ${viewingProduct?.name || ''}`}
        open={detailModalOpen}
        onCancel={() => setDetailModalOpen(false)}
        footer={[
          viewingProduct && (viewingProduct.status === 'pending' || viewingProduct.status === 'analyzing') ? (
            <>
              <Button key="reject" danger icon={<CloseCircleOutlined />} onClick={() => { message.success('已拒绝'); setDetailModalOpen(false) }}>拒绝</Button>
              <Button key="approve" type="primary" icon={<CheckCircleOutlined />} onClick={() => { message.success('已通过选品'); setDetailModalOpen(false) }}>通过选品</Button>
            </>
          ) : viewingProduct?.status === 'approved' ? (
            <Button key="list" type="primary" icon={<RocketOutlined />} onClick={() => { message.success('已加入上架队列'); setDetailModalOpen(false) }}>加入上架队列</Button>
          ) : null,
          <Button key="close" onClick={() => setDetailModalOpen(false)}>关闭</Button>,
        ]}
        width={700}
      >
        {viewingProduct && (
          <div>
            <Descriptions column={2} bordered size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="商品名称" span={2}>{viewingProduct.name}</Descriptions.Item>
              <Descriptions.Item label="英文名称" span={2}>{viewingProduct.name_en || '-'}</Descriptions.Item>
              <Descriptions.Item label="来源"><Tag color={viewingProduct.source === '1688' ? 'orange' : 'purple'}>{viewingProduct.source === '1688' ? '1688' : 'AI推荐'}</Tag></Descriptions.Item>
              <Descriptions.Item label="分类">{viewingProduct.category}</Descriptions.Item>
              <Descriptions.Item label="供应商">{viewingProduct.supplier}</Descriptions.Item>
              <Descriptions.Item label="起订量">{viewingProduct.moq}件</Descriptions.Item>
              <Descriptions.Item label="成本价"><Text strong>¥{viewingProduct.cost_price}</Text></Descriptions.Item>
              <Descriptions.Item label="建议售价"><Text strong style={{ color: '#52c41a' }}>${viewingProduct.suggested_price}</Text></Descriptions.Item>
              <Descriptions.Item label="利润率">
                <Text type={viewingProduct.profit_margin > 50 ? 'success' : viewingProduct.profit_margin > 0 ? 'warning' : 'danger'} strong>
                  {viewingProduct.profit_margin > 0 ? '+' : ''}{viewingProduct.profit_margin.toFixed(1)}%
                </Text>
              </Descriptions.Item>
              <Descriptions.Item label="市场需求"><Tag color={demandColors[viewingProduct.market_demand]}>{demandText[viewingProduct.market_demand]}</Tag></Descriptions.Item>
              <Descriptions.Item label="30天销量">{viewingProduct.sales_30d.toLocaleString()}件</Descriptions.Item>
              <Descriptions.Item label="搜索量">{viewingProduct.search_volume.toLocaleString()}/月</Descriptions.Item>
              <Descriptions.Item label="状态"><Tag color={statusColors[viewingProduct.status]}>{statusText[viewingProduct.status]}</Tag></Descriptions.Item>
              {viewingProduct.source_url && <Descriptions.Item label="来源链接" span={2}><a href={viewingProduct.source_url} target="_blank">查看1688商品</a></Descriptions.Item>}
            </Descriptions>

            <Card size="small" title="AI选品评分" style={{ marginBottom: 16 }}>
              <div style={{ textAlign: 'center', marginBottom: 16 }}>
                <div style={{ fontSize: 48, fontWeight: 700, color: viewingProduct.score >= 80 ? '#52c41a' : viewingProduct.score >= 60 ? '#faad14' : '#f5222d' }}>
                  {viewingProduct.score}
                </div>
                <div style={{ fontSize: 14, color: '#999' }}>综合评分（满分100）</div>
              </div>
              <Row gutter={16}>
                <Col span={8}>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 20, fontWeight: 600, color: '#1890ff' }}>{viewingProduct.market_demand === 'high' ? 90 : viewingProduct.market_demand === 'medium' ? 60 : 30}</div>
                    <div style={{ fontSize: 12, color: '#999' }}>市场需求</div>
                  </div>
                </Col>
                <Col span={8}>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 20, fontWeight: 600, color: '#722ed1' }}>{viewingProduct.competition === 'low' ? 90 : viewingProduct.competition === 'medium' ? 60 : 30}</div>
                    <div style={{ fontSize: 12, color: '#999' }}>竞争程度</div>
                  </div>
                </Col>
                <Col span={8}>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 20, fontWeight: 600, color: '#52c41a' }}>{Math.max(0, Math.min(100, viewingProduct.profit_margin + 50))}</div>
                    <div style={{ fontSize: 12, color: '#999' }}>利润空间</div>
                  </div>
                </Col>
              </Row>
            </Card>

            <div>
              <Text strong>标签：</Text>
              <Space wrap style={{ marginLeft: 8 }}>
                {viewingProduct.tags.map((tag, idx) => <Tag key={idx} color="blue">{tag}</Tag>)}
              </Space>
            </div>

            {viewingProduct.notes && (
              <Alert message="AI分析备注" description={viewingProduct.notes} type="warning" showIcon style={{ marginTop: 16 }} />
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}
