import { useState, useEffect, useCallback } from 'react'
import {
  Layout, Typography, Card, Table, Tag, Space, Input, Button, Select, Row, Col,
  Statistic, Row as AntRow, Col as AntCol, Drawer, Descriptions, Badge, Tooltip,
  Spin, Empty, message, Popconfirm, Divider,
} from 'antd'
import {
  SearchOutlined, ReloadOutlined, LinkOutlined, GlobalOutlined,
  DatabaseOutlined, ShopOutlined, CheckCircleOutlined, SyncOutlined,
  ExclamationCircleOutlined, CopyOutlined, DownloadOutlined,
} from '@ant-design/icons'

const { Title, Text, Paragraph } = Typography
const { Search } = Input

// 类型定义
interface Product {
  id: string
  sku: string
  name: string
  category?: string
  status: string
  candidate_status?: string
  source: string
  source_url?: string
  meta: {
    woocommerce_id?: number
    woocommerce_slug?: string
    regular_price?: string
  }
  created_at: string
  updated_at: string
}

interface MappingRow {
  key: string
  nuotao_id: string
  sku: string
  name: string
  ali1688_id: string
  ali1688_url: string
  wc_id: number | null
  wc_slug: string
  wc_status: string
  price: string
  source: string
  status: string
  updated_at: string
}

const SOURCE_COLORS: Record<string, string> = {
  '1688': 'orange',
  '拉取': 'blue',
  '手工': 'green',
  'pipeline': 'purple',
  'manual': 'green',
}

const STATUS_COLORS: Record<string, string> = {
  'active': 'green',
  'draft': 'orange',
  'archived': 'default',
  'publish': 'green',
  'candidate': 'blue',
  'approved': 'green',
  'testing': 'gold',
  'intake': 'default',
}

// 从 URL 提取 1688 ID
function extract1688Id(url?: string): string {
  if (!url) return '-'
  const match = url.match(/offer\/(\d+)/)
  if (match) return match[1]
  const match2 = url.match(/(\d{9,})/)
  return match2 ? match2[1] : '-'
}

export default function ProductMappingPage() {
  const [loading, setLoading] = useState(false)
  const [products, setProducts] = useState<Product[]>([])
  const [filteredProducts, setFilteredProducts] = useState<Product[]>([])
  const [searchText, setSearchText] = useState('')
  const [filterSource, setFilterSource] = useState<string | undefined>()
  const [filterStatus, setFilterStatus] = useState<string | undefined>()
  const [detailProduct, setDetailProduct] = useState<Product | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)

  // 加载产品数据
  const loadProducts = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/v1/products?limit=200')
      if (res.ok) {
        const data = await res.json()
        setProducts(data as Product[])
        setFilteredProducts(data as Product[])
      } else {
        message.error('加载产品数据失败')
      }
    } catch {
      message.error('网络请求失败')
    } finally {
      setLoading(false)
    }
  }, [])

  // 加载时获取数据
  useEffect(() => {
    loadProducts()
  }, [loadProducts])

  // 过滤产品
  useEffect(() => {
    let filtered = [...products]

    if (searchText) {
      const lower = searchText.toLowerCase()
      filtered = filtered.filter(p =>
        p.name.toLowerCase().includes(lower) ||
        p.sku.toLowerCase().includes(lower) ||
        p.id.toLowerCase().includes(lower) ||
        (p.source_url && p.source_url.toLowerCase().includes(lower)) ||
        (p.meta.woocommerce_id && String(p.meta.woocommerce_id).includes(lower))
      )
    }

    if (filterSource) {
      filtered = filtered.filter(p => p.source === filterSource)
    }

    if (filterStatus) {
      filtered = filtered.filter(p => p.status === filterStatus)
    }

    setFilteredProducts(filtered)
  }, [products, searchText, filterSource, filterStatus])

  // 转换为表格数据
  const dataSource: MappingRow[] = filteredProducts.map(p => ({
    key: p.id,
    nuotao_id: p.id,
    sku: p.sku,
    name: p.name,
    ali1688_id: extract1688Id(p.source_url),
    ali1688_url: p.source_url || '-',
    wc_id: p.meta?.woocommerce_id || null,
    wc_slug: p.meta?.woocommerce_slug || '-',
    wc_status: p.meta?.woocommerce_id ? 'synced' : '-',
    price: p.meta?.regular_price || '-',
    source: p.source,
    status: p.status,
    updated_at: p.updated_at,
  }))

  // 统计数据
  const stats = {
    total: products.length,
    synced: products.filter(p => p.meta?.woocommerce_id).length,
    from1688: products.filter(p => p.source_url && p.source_url.includes('1688')).length,
    active: products.filter(p => p.status === 'active').length,
  }

  // 表格列配置
  const columns = [
    {
      title: 'Nuotao ID',
      dataIndex: 'nuotao_id',
      key: 'nuotao_id',
      width: 180,
      render: (id: string) => (
        <Tooltip title={id}>
          <Text copyable={{ text: id }} style={{ fontSize: 12 }}>
            {id.slice(0, 8)}...
          </Text>
        </Tooltip>
      ),
    },
    {
      title: 'SKU',
      dataIndex: 'sku',
      key: 'sku',
      width: 180,
      render: (sku: string) => (
        <Text strong copyable={{ text: sku }}>
          {sku}
        </Text>
      ),
    },
    {
      title: '商品名称',
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
      render: (name: string) => (
        <Tooltip title={name}>
          <Text>{name.length > 30 ? name.slice(0, 30) + '...' : name}</Text>
        </Tooltip>
      ),
    },
    {
      title: '1688 ID',
      dataIndex: 'ali1688_id',
      key: 'ali1688_id',
      width: 140,
      render: (id: string, record: MappingRow) => {
        if (id === '-') return <Text type="secondary">-</Text>
        return (
          <a
            href={record.ali1688_url}
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: '#fa8c16' }}
          >
            {id}
          </a>
        )
      },
    },
    {
      title: 'WC ID',
      dataIndex: 'wc_id',
      key: 'wc_id',
      width: 100,
      render: (id: number | null) => {
        if (!id) return <Tag>未同步</Tag>
        return (
          <a
            href={`https://nuotaooutdoor.com/wp-admin/post.php?post=${id}&action=edit`}
            target="_blank"
            rel="noopener noreferrer"
          >
            <Tag color="green">#{id}</Tag>
          </a>
        )
      },
    },
    {
      title: '来源',
      dataIndex: 'source',
      key: 'source',
      width: 100,
      render: (source: string) => (
        <Tag color={SOURCE_COLORS[source] || 'default'}>
          {source === '1688' ? <><ShopOutlined /> 1688</> : source}
        </Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Badge
          status={status === 'active' ? 'success' : status === 'draft' ? 'warning' : 'default'}
          text={status === 'active' ? '可销售' : status === 'draft' ? '草稿' : status}
        />
      ),
    },
    {
      title: '价格',
      dataIndex: 'price',
      key: 'price',
      width: 100,
      render: (price: string) => price === '-' ? <Text type="secondary">-</Text> : `$${price}`,
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 160,
      render: (date: string) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {new Date(date).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
        </Text>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_: any, record: MappingRow) => (
        <Button
          type="link"
          size="small"
          onClick={() => {
            const product = filteredProducts.find(p => p.id === record.key)
            if (product) {
              setDetailProduct(product)
              setDrawerOpen(true)
            }
          }}
        >
          详情
        </Button>
      ),
    },
  ]

  // 导出数据
  const handleExport = () => {
    const csvHeader = 'Nuotao ID,SKU,名称,1688 ID,1688 URL,WC ID,WC Slug,来源,状态,价格,更新时间\n'
    const csvRows = dataSource.map(row =>
      `"${row.nuotao_id}","${row.sku}","${row.name.replace(/"/g, '""')}","${row.ali1688_id}","${row.ali1688_url}","${row.wc_id || ''}","${row.wc_slug}","${row.source}","${row.status}","${row.price}","${row.updated_at}"`
    ).join('\n')
    const csvContent = csvHeader + csvRows
    const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `product_mappings_${new Date().toISOString().slice(0, 10)}.csv`
    link.click()
    message.success('导出成功')
  }

  return (
    <Layout>
      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="总产品数"
              value={stats.total}
              prefix={<DatabaseOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="已同步 WC"
              value={stats.synced}
              prefix={<SyncOutlined />}
              valueStyle={{ color: '#3f8600' }}
              suffix={`/ ${stats.total}`}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="1688 来源"
              value={stats.from1688}
              prefix={<ShopOutlined />}
              valueStyle={{ color: '#fa8c16' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="可销售"
              value={stats.active}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
      </Row>

      {/* 数据流说明 */}
      <Card style={{ marginBottom: 24 }}>
        <Title level={4} style={{ marginTop: 0 }}>
          <LinkOutlined /> 产品 ID 映射关系
        </Title>
        <Row gutter={16}>
          <Col span={8}>
            <Card type="inner" title="1688 平台" size="small">
              <Paragraph style={{ marginBottom: 8 }}>
                <Text strong>唯一 ID:</Text> Offer ID
              </Paragraph>
              <Paragraph style={{ marginBottom: 8 }}>
                <Text strong>示例:</Text> 994277857137
              </Paragraph>
              <Paragraph>
                <Text strong>存储位置:</Text> products.source_url
              </Paragraph>
            </Card>
          </Col>
          <Col span={8}>
            <Card type="inner" title="Nuotao AI OS" size="small">
              <Paragraph style={{ marginBottom: 8 }}>
                <Text strong>唯一 ID:</Text> UUID (products.id)
              </Paragraph>
              <Paragraph style={{ marginBottom: 8 }}>
                <Text strong>示例:</Text> 78b0a7f7-25d4-...
              </Paragraph>
              <Paragraph>
                <Text strong>存储位置:</Text> products.id (主键)
              </Paragraph>
            </Card>
          </Col>
          <Col span={8}>
            <Card type="inner" title="WooCommerce" size="small">
              <Paragraph style={{ marginBottom: 8 }}>
                <Text strong>唯一 ID:</Text> woocommerce_id
              </Paragraph>
              <Paragraph style={{ marginBottom: 8 }}>
                <Text strong>示例:</Text> #2184
              </Paragraph>
              <Paragraph>
                <Text strong>存储位置:</Text> products.meta.woocommerce_id
              </Paragraph>
            </Card>
          </Col>
        </Row>
      </Card>

      {/* 搜索和过滤 */}
      <Card style={{ marginBottom: 16 }}>
        <Space wrap>
          <Input
            placeholder="搜索 ID、SKU、名称、1688 URL..."
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ width: 300 }}
            allowClear
          />
          <Select
            placeholder="来源"
            value={filterSource}
            onChange={setFilterSource}
            style={{ width: 150 }}
            allowClear
            options={[
              { value: '1688', label: '1688' },
              { value: '拉取', label: '拉取' },
              { value: '手工', label: '手工' },
              { value: 'pipeline', label: 'Pipeline' },
            ]}
          />
          <Select
            placeholder="状态"
            value={filterStatus}
            onChange={setFilterStatus}
            style={{ width: 150 }}
            allowClear
            options={[
              { value: 'active', label: '可销售' },
              { value: 'draft', label: '草稿' },
              { value: 'archived', label: '归档' },
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={loadProducts}>
            刷新
          </Button>
          <Button icon={<DownloadOutlined />} onClick={handleExport}>
            导出 CSV
          </Button>
        </Space>
      </Card>

      {/* 数据表格 */}
      <Card>
        <Table
          columns={columns}
          dataSource={dataSource}
          loading={loading}
          pagination={{
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total) => `共 ${total} 条`,
            pageSizeOptions: [10, 20, 50, 100],
          }}
          scroll={{ x: 1400 }}
          locale={{
            emptyText: <Empty description="暂无数据" />,
          }}
        />
      </Card>

      {/* 详情抽屉 */}
      <Drawer
        title="产品映射详情"
        placement="right"
        width={500}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      >
        {detailProduct && (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="Nuotao ID">
              <Text copyable>{detailProduct.id}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="SKU">
              <Text strong copyable>{detailProduct.sku}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="商品名称">
              {detailProduct.name}
            </Descriptions.Item>
            <Descriptions.Item label="1688 ID">
              {extract1688Id(detailProduct.source_url)}
            </Descriptions.Item>
            <Descriptions.Item label="1688 URL">
              {detailProduct.source_url ? (
                <a href={detailProduct.source_url} target="_blank" rel="noopener noreferrer">
                  {detailProduct.source_url}
                </a>
              ) : (
                <Text type="secondary">无</Text>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="WC ID">
              {detailProduct.meta?.woocommerce_id ? (
                <Tag color="green">#{detailProduct.meta.woocommerce_id}</Tag>
              ) : (
                <Tag>未同步</Tag>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="WC Slug">
              {detailProduct.meta?.woocommerce_slug || <Text type="secondary">无</Text>}
            </Descriptions.Item>
            <Descriptions.Item label="来源">
              <Tag color={SOURCE_COLORS[detailProduct.source] || 'default'}>
                {detailProduct.source}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="状态">
              <Badge
                status={detailProduct.status === 'active' ? 'success' : 'warning'}
                text={detailProduct.status}
              />
            </Descriptions.Item>
            <Descriptions.Item label="分类">
              {detailProduct.category || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="价格">
              {detailProduct.meta?.regular_price ? `$${detailProduct.meta.regular_price}` : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="创建时间">
              {new Date(detailProduct.created_at).toLocaleString('zh-CN')}
            </Descriptions.Item>
            <Descriptions.Item label="更新时间">
              {new Date(detailProduct.updated_at).toLocaleString('zh-CN')}
            </Descriptions.Item>
          </Descriptions>
        )}
      </Drawer>
    </Layout>
  )
}
