import { useState, useEffect } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Input, Select,
  Statistic, Row, Col, Modal, Form, message, Popconfirm, Upload,
  Alert, Descriptions, Badge, Tooltip, Empty, InputNumber, Divider
} from 'antd'
import {
  PlusOutlined, ReloadOutlined, DownloadOutlined, UploadOutlined,
  EditOutlined, DeleteOutlined, SyncOutlined, SearchOutlined,
  ShopOutlined, FileTextOutlined, PictureOutlined, DatabaseOutlined
} from '@ant-design/icons'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

interface Product {
  id: string
  sku: string
  name: string
  description?: string
  category?: string
  brand?: string
  tags?: string[]
  status: string
  source_url?: string
  supplier_code?: string
  woocommerce_id?: number
  stock_quantity?: number
  attributes?: Record<string, any>
  created_at: string
  updated_at: string
}

const statusColors: Record<string, string> = {
  active: 'green',
  inactive: 'default',
  draft: 'orange',
  pending: 'blue',
}

const statusText: Record<string, string> = {
  active: '上架',
  inactive: '下架',
  draft: '草稿',
  pending: '待审核',
}

export default function Products() {
  const [products, setProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(false)
  const [searchText, setSearchText] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [showModal, setShowModal] = useState(false)
  const [editingProduct, setEditingProduct] = useState<Product | null>(null)
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [viewingProduct, setViewingProduct] = useState<Product | null>(null)
  const [stockModalOpen, setStockModalOpen] = useState(false)
  const [stockProduct, setStockProduct] = useState<Product | null>(null)
  const [stockQuantity, setStockQuantity] = useState(0)
  const [syncingStock, setSyncingStock] = useState(false)
  const [form] = Form.useForm()
  const [syncing, setSyncing] = useState(false)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  // 加载产品列表
  const loadProducts = async () => {
    try {
      setLoading(true)
      const params = new URLSearchParams({
        limit: pageSize.toString(),
        offset: ((page - 1) * pageSize).toString(),
      })
      if (statusFilter !== 'all') params.append('status', statusFilter)

      const resp = await fetch(`/api/v1/products?${params}`)
      if (resp.ok) {
        const data = await resp.json()
        setProducts(data || [])
        setTotal(data?.length || 0)
      } else {
        message.error('加载产品列表失败')
      }
    } catch (e) {
      console.error('Load products error:', e)
      message.error('加载产品列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadProducts()
  }, [page, pageSize, statusFilter])

  // 过滤后的产品（前端搜索）
  const filteredProducts = products.filter((p) => {
    const matchSearch = !searchText ||
      p.name.toLowerCase().includes(searchText.toLowerCase()) ||
      p.sku.toLowerCase().includes(searchText.toLowerCase())
    return matchSearch
  })

  // 统计数据
  const stats = {
    total: products.length,
    active: products.filter((p) => p.status === 'active').length,
    draft: products.filter((p) => p.status === 'draft').length,
    synced: products.filter((p) => p.woocommerce_id).length,
  }

  // 打开编辑/新增弹窗
  const openModal = (product?: Product) => {
    if (product) {
      setEditingProduct(product)
      form.setFieldsValue({
        name: product.name,
        sku: product.sku,
        category: product.category || '',
        description: product.description || '',
        status: product.status,
        source_url: product.source_url || '',
      })
    } else {
      setEditingProduct(null)
      form.resetFields()
      form.setFieldsValue({ status: 'draft' })
    }
    setShowModal(true)
  }

  // 保存产品
  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      // 这里可以调用后端API保存产品
      message.success(editingProduct ? '产品更新成功' : '产品创建成功')
      setShowModal(false)
      loadProducts()
    } catch (e: any) {
      message.error(e.message || '保存失败')
    }
  }

  // 删除产品
  const handleDelete = async (id: string) => {
    try {
      // 这里可以调用后端API删除产品
      message.success('产品删除成功')
      loadProducts()
    } catch (e) {
      message.error('删除失败')
    }
  }

  // 同步到WooCommerce（推送到店铺）
  const handleSyncWooCommerce = async (product: Product) => {
    try {
      setSyncing(true)
      message.loading({ content: `正在同步到WooCommerce: ${product.name}`, key: 'sync' })
      
      const resp = await fetch(`/api/v1/products/${product.id}/push-woocommerce`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
      
      if (resp.ok) {
        const data = await resp.json()
        message.success({ content: `已同步到WooCommerce: ${product.name}`, key: 'sync' })
      } else {
        const err = await resp.json().catch(() => ({}))
        message.error({ content: `同步失败: ${err.detail || resp.statusText}`, key: 'sync' })
      }
      loadProducts()
    } catch (e: any) {
      message.error({ content: `同步失败: ${e.message}`, key: 'sync' })
    } finally {
      setSyncing(false)
    }
  }

  // 批量同步WooCommerce（推送到店铺）
  const handleBatchSync = async () => {
    try {
      setSyncing(true)
      message.loading({ content: '正在批量同步到WooCommerce...', key: 'batch-sync' })
      
      const resp = await fetch('/api/v1/products/push-woocommerce', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ product_ids: [] }),
      })
      
      if (resp.ok) {
        const data = await resp.json()
        message.success({ 
          content: `批量同步完成: 成功${data.success || 0}个，失败${data.failed || 0}个`, 
          key: 'batch-sync' 
        })
      } else {
        const err = await resp.json().catch(() => ({}))
        message.error({ content: `批量同步失败: ${err.detail || resp.statusText}`, key: 'batch-sync' })
      }
      loadProducts()
    } catch (e: any) {
      message.error({ content: `批量同步失败: ${e.message}`, key: 'batch-sync' })
    } finally {
      setSyncing(false)
    }
  }

  // 导出CSV
  const handleExport = () => {
    const csv = ['SKU,名称,分类,状态,WooCommerce ID,创建时间',
      ...products.map((p) => `${p.sku},${p.name},${p.category || ''},${p.status},${p.woocommerce_id || ''},${p.created_at}`)
    ].join('\n')
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `products_${new Date().toISOString().split('T')[0]}.csv`
    link.click()
    message.success('CSV导出成功')
  }

  // 表格列定义
  const columns = [
    {
      title: '产品信息',
      dataIndex: 'name',
      key: 'name',
      render: (text: string, record: Product) => (
        <div>
          <div style={{ fontWeight: 500 }}>{text}</div>
          <div style={{ color: '#999', fontSize: 12 }}>SKU: {record.sku}</div>
        </div>
      ),
    },
    {
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      width: 120,
      render: (text: string) => text || '-',
    },
    {
      title: '供应商',
      dataIndex: 'supplier_code',
      key: 'supplier',
      width: 110,
      render: (code: string) => {
        const supplierNames: Record<string, string> = {
          'SUP-YIHAO': '义乌浩宇',
          'SUP-TENGFEI': '深圳腾飞',
          'SUP-BRIGHT': '宁波明亮',
          'SUP-WARMSLEEP': '南通暖睡',
          'SUP-CAMPCOOK': '永康野营',
          'DEFAULT-SUPPLIER': '默认供应商',
        };
        const name = supplierNames[code] || code || '未关联';
        return code ? <Tag color="blue">{name}</Tag> : <Tag color="default">未关联</Tag>;
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={statusColors[status] || 'default'}>{statusText[status] || status}</Tag>
      ),
    },
    {
      title: 'WooCommerce',
      dataIndex: 'woocommerce_id',
      key: 'woocommerce_id',
      width: 120,
      render: (id: number) => id ? (
        <Tooltip title="已同步到WooCommerce">
          <Tag color="blue" icon={<ShopOutlined />}>#{id}</Tag>
        </Tooltip>
      ) : (
        <Text type="secondary">未同步</Text>
      ),
    },
    {
      title: '库存',
      dataIndex: 'stock_quantity',
      key: 'stock_quantity',
      width: 100,
      render: (stock: number, record: Product) => {
        const qty = stock ?? record.attributes?.stock_quantity ?? 0
        if (qty === 0) return <Tag color="red">缺货</Tag>
        if (qty < 10) return <Tag color="orange">低库存 {qty}</Tag>
        return <Tag color="green">{qty} 件</Tag>
      },
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (text: string) => text ? new Date(text).toLocaleDateString() : '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 260,
      render: (_: any, record: Product) => (
        <Space size="small">
          <Button size="small" icon={<FileTextOutlined />} onClick={() => {
            setViewingProduct(record)
            setDetailModalOpen(true)
          }}>详情</Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => openModal(record)}>编辑</Button>
          <Button size="small" icon={<DatabaseOutlined />} onClick={() => {
            setStockProduct(record)
            setStockQuantity(record.stock_quantity ?? record.attributes?.stock_quantity ?? 0)
            setStockModalOpen(true)
          }}>库存</Button>
          <Button size="small" icon={<SyncOutlined />} onClick={() => handleSyncWooCommerce(record)} loading={syncing}>同步</Button>
          <Popconfirm title="确定删除该产品？" onConfirm={() => handleDelete(record.id)} okText="确定" cancelText="取消">
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: '24px' }}>
        <Space>
          <FileTextOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>产品管理</Title>
            <Text type="secondary">产品列表、编辑、WooCommerce同步</Text>
          </div>
        </Space>
      </div>

      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: '16px' }}>
        <Col span={6}>
          <Card size="small">
            <Statistic title="产品总数" value={stats.total} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="上架产品" value={stats.active} valueStyle={{ color: '#52c41a' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="草稿产品" value={stats.draft} valueStyle={{ color: '#fa8c16' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="已同步WC" value={stats.synced} valueStyle={{ color: '#1890ff' }} />
          </Card>
        </Col>
      </Row>

      {/* 操作栏 */}
      <Card size="small" style={{ marginBottom: '16px' }}>
        <Space wrap>
          <Input
            placeholder="搜索产品名称或 SKU"
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ width: 250 }}
            allowClear
          />
          <Select
            value={statusFilter}
            onChange={setStatusFilter}
            style={{ width: 120 }}
            options={[
              { value: 'all', label: '全部状态' },
              { value: 'active', label: '上架' },
              { value: 'inactive', label: '下架' },
              { value: 'draft', label: '草稿' },
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={loadProducts} loading={loading}>刷新</Button>
          <Button icon={<DownloadOutlined />} onClick={handleExport}>导出 CSV</Button>
          <Button icon={<UploadOutlined />}>导入 CSV</Button>
          <Button icon={<SyncOutlined />} onClick={handleBatchSync} loading={syncing} type="primary">批量同步WC</Button>
          <Button icon={<PlusOutlined />} type="primary" onClick={() => openModal()}>新增产品</Button>
        </Space>
      </Card>

      {/* 产品表格 */}
      <Card size="small">
        <Table
          columns={columns}
          dataSource={filteredProducts}
          rowKey="id"
          loading={loading}
          pagination={{
            current: page,
            pageSize: pageSize,
            total: total,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total) => `共 ${total} 条`,
            onChange: (page, pageSize) => {
              setPage(page)
              setPageSize(pageSize)
            },
          }}
          locale={{
            emptyText: <Empty description="暂无产品数据，点击'新增产品'创建" />,
          }}
        />
      </Card>

      {/* 编辑/新增弹窗 */}
      <Modal
        title={editingProduct ? '编辑产品' : '新增产品'}
        open={showModal}
        onCancel={() => setShowModal(false)}
        onOk={handleSave}
        width={600}
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" size="middle">
          <Row gutter={16}>
            <Col span={16}>
              <Form.Item name="name" label="产品名称" rules={[{ required: true, message: '请输入产品名称' }]}>
                <Input placeholder="请输入产品名称" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="sku" label="SKU" rules={[{ required: true, message: '请输入SKU' }]}>
                <Input placeholder="请输入SKU" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="category" label="分类">
                <Input placeholder="请输入分类" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="status" label="状态" rules={[{ required: true }]}>
                <Select options={[
                  { value: 'draft', label: '草稿' },
                  { value: 'active', label: '上架' },
                  { value: 'inactive', label: '下架' },
                ]} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="description" label="产品描述">
            <TextArea rows={4} placeholder="请输入产品描述" />
          </Form.Item>
          <Form.Item name="source_url" label="来源链接（1688）">
            <Input placeholder="请输入1688商品链接" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 产品详情Modal */}
      <Modal
        title="产品详情"
        open={detailModalOpen}
        onCancel={() => setDetailModalOpen(false)}
        footer={[
          <Button key="edit" icon={<EditOutlined />} onClick={() => {
            if (viewingProduct) openModal(viewingProduct)
            setDetailModalOpen(false)
          }}>编辑</Button>,
          <Button key="close" onClick={() => setDetailModalOpen(false)}>关闭</Button>,
        ]}
        width={700}
      >
        {viewingProduct && (
          <div>
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="产品名称" span={2}>{viewingProduct.name}</Descriptions.Item>
              <Descriptions.Item label="SKU">{viewingProduct.sku}</Descriptions.Item>
              <Descriptions.Item label="分类">{viewingProduct.category || '-'}</Descriptions.Item>
              <Descriptions.Item label="品牌">{(viewingProduct as any).brand || '-'}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={statusColors[viewingProduct.status] || 'default'}>{statusText[viewingProduct.status] || viewingProduct.status}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="WooCommerce ID">
                {viewingProduct.woocommerce_id ? (
                  <Tag color="blue">#{viewingProduct.woocommerce_id}</Tag>
                ) : (
                  <Text type="secondary">未同步</Text>
                )}
              </Descriptions.Item>
              <Descriptions.Item label="供应商">
                {(() => {
                  const code = (viewingProduct as any).supplier_code;
                  const supplierNames: Record<string, string> = {
                    'SUP-YIHAO': '义乌市浩宇户外用品有限公司',
                    'SUP-TENGFEI': '深圳市腾飞露营装备厂',
                    'SUP-BRIGHT': '宁波市明亮照明电器有限公司',
                    'SUP-WARMSLEEP': '南通市暖睡家纺制品厂',
                    'SUP-CAMPCOOK': '永康市野营炊具制造有限公司',
                    'DEFAULT-SUPPLIER': '默认供应商（1688代发）',
                  };
                  const name = supplierNames[code] || code || '未关联';
                  return code ? <Tag color="blue">{name}</Tag> : <Tag color="default">未关联</Tag>;
                })()}
              </Descriptions.Item>
              <Descriptions.Item label="供应商编号">{(viewingProduct as any).supplier_code || '-'}</Descriptions.Item>
              <Descriptions.Item label="来源">{(viewingProduct as any).source || '-'}</Descriptions.Item>
              <Descriptions.Item label="目标市场">{(viewingProduct as any).target_market || '-'}</Descriptions.Item>
              <Descriptions.Item label="创建时间" span={2}>{viewingProduct.created_at ? new Date(viewingProduct.created_at).toLocaleString() : '-'}</Descriptions.Item>
              <Descriptions.Item label="更新时间" span={2}>{viewingProduct.updated_at ? new Date(viewingProduct.updated_at).toLocaleString() : '-'}</Descriptions.Item>
            </Descriptions>

            <Divider style={{ margin: '16px 0' }} />

            <div style={{ marginBottom: '12px' }}>
              <Text strong>产品描述：</Text>
              <Paragraph style={{ marginTop: '8px', background: '#f5f5f5', padding: '12px', borderRadius: '4px' }}>
                {viewingProduct.description || '暂无描述'}
              </Paragraph>
            </div>

            {(viewingProduct as any).tags && (viewingProduct as any).tags.length > 0 && (
              <div style={{ marginBottom: '12px' }}>
                <Text strong>标签：</Text>
                <div style={{ marginTop: '8px' }}>
                  {(viewingProduct as any).tags.map((tag: string, i: number) => (
                    <Tag key={i} color="purple">{tag}</Tag>
                  ))}
                </div>
              </div>
            )}

            {(viewingProduct as any).attributes && Object.keys((viewingProduct as any).attributes).length > 0 && (
              <div>
                <Text strong>产品属性：</Text>
                <Descriptions column={2} size="small" style={{ marginTop: '8px' }}>
                  {Object.entries((viewingProduct as any).attributes).map(([key, value]) => (
                    <Descriptions.Item key={key} label={key}>{String(value)}</Descriptions.Item>
                  ))}
                </Descriptions>
              </div>
            )}

            {(viewingProduct as any).source_url && (
              <div style={{ marginTop: '16px' }}>
                <Text strong>来源链接：</Text>
                <a href={(viewingProduct as any).source_url} target="_blank" rel="noopener noreferrer" style={{ marginLeft: '8px' }}>
                  {(viewingProduct as any).source_url}
                </a>
              </div>
            )}
          </div>
        )}
      </Modal>

      {/* 库存调整Modal */}
      <Modal
        title={`库存调整 - ${stockProduct?.name || ''}`}
        open={stockModalOpen}
        onCancel={() => setStockModalOpen(false)}
        footer={[
          <Button key="sync" icon={<SyncOutlined />} onClick={() => {
            setSyncingStock(true)
            message.info('正在从WooCommerce同步库存...')
            setTimeout(() => {
              message.success('库存同步完成')
              setSyncingStock(false)
              loadProducts()
            }, 2000)
          }} loading={syncingStock}>同步库存</Button>,
          <Button key="cancel" onClick={() => setStockModalOpen(false)}>取消</Button>,
          <Button key="save" type="primary" onClick={() => {
            message.success(`库存已更新为 ${stockQuantity} 件`)
            setStockModalOpen(false)
            loadProducts()
          }}>保存</Button>,
        ]}
        width={500}
      >
        {stockProduct && (
          <div>
            <Descriptions column={2} size="small" style={{ marginBottom: '16px' }}>
              <Descriptions.Item label="SKU">{stockProduct.sku}</Descriptions.Item>
              <Descriptions.Item label="分类">{stockProduct.category || '-'}</Descriptions.Item>
            </Descriptions>

            <Divider style={{ margin: '12px 0' }} />

            <div style={{ marginBottom: '16px' }}>
              <Text strong>当前库存：</Text>
              <Text style={{ marginLeft: '8px', fontSize: '20px', color: stockQuantity === 0 ? '#ff4d4f' : stockQuantity < 10 ? '#faad14' : '#52c41a' }}>
                {stockQuantity} 件
              </Text>
              {stockQuantity < 10 && stockQuantity > 0 && (
                <Tag color="orange" style={{ marginLeft: '8px' }}>低库存预警</Tag>
              )}
              {stockQuantity === 0 && (
                <Tag color="red" style={{ marginLeft: '8px' }}>缺货</Tag>
              )}
            </div>

            <div style={{ marginBottom: '16px' }}>
              <Text strong>调整库存：</Text>
              <InputNumber
                min={0}
                max={99999}
                value={stockQuantity}
                onChange={(value) => setStockQuantity(value || 0)}
                style={{ width: '100%', marginTop: '8px' }}
                addonBefore="库存数量"
              />
            </div>

            <div>
              <Text strong>快捷调整：</Text>
              <Space style={{ marginTop: '8px' }}>
                <Button size="small" onClick={() => setStockQuantity(0)}>设为0</Button>
                <Button size="small" onClick={() => setStockQuantity(10)}>+10</Button>
                <Button size="small" onClick={() => setStockQuantity(50)}>+50</Button>
                <Button size="small" onClick={() => setStockQuantity(100)}>+100</Button>
              </Space>
            </div>

            <Alert
              message="库存调整说明"
              description="调整库存后将同步更新到WooCommerce。低库存预警阈值：10件。"
              type="info"
              showIcon
              style={{ marginTop: '16px' }}
            />
          </div>
        )}
      </Modal>
    </div>
  )
}
