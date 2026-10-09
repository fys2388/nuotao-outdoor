import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Row, Col, Button, Space, Typography, Alert, message,
  Table, Tag, Progress, Input, Select, Modal, Form,
  Tooltip, Statistic,
} from 'antd'
import {
  RobotOutlined, ReloadOutlined, CheckCircleOutlined,
  ExclamationCircleOutlined, SettingOutlined, DatabaseOutlined,
} from '@ant-design/icons'
import { api } from '../api/client'

const { Text, Paragraph } = Typography
const { Option } = Select

interface ProductItem {
  id: string
  sku: string
  name: string
  description?: string
  category: string
  status: string
  data_integrity_score: number
  data_integrity_status: string
  data_integrity_missing: string[]
  meta: Record<string, unknown>
}

export default function ProductEnrichmentPage() {
  const navigate = useNavigate()
  const [products, setProducts] = useState<ProductItem[]>([])
  const [loading, setLoading] = useState(false)
  const [optimizing, setOptimizing] = useState(false)
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [autoFillPrice, setAutoFillPrice] = useState(true)
  const [autoFillImages, setAutoFillImages] = useState(true)
  const [autoFillDescription, setAutoFillDescription] = useState(true)
  const [optimizeResult, setOptimizeResult] = useState<any>(null)
  const [updateModalOpen, setUpdateModalOpen] = useState(false)
  const [updateProductId, setUpdateProductId] = useState<string>('')
  const [updateForm] = Form.useForm()
  const [updating, setUpdating] = useState(false)

  const fetchProducts = async () => {
    setLoading(true)
    try {
      const data = await api.getProducts(100, 0) as any
      setProducts(data.data || data || [])
    } catch {
      message.error('获取产品列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchProducts()
  }, [])

  const handleAutoOptimize = async () => {
    if (selectedIds.length === 0) {
      message.warning('请先选择产品')
      return
    }
    setOptimizing(true)
    try {
      const result = await api.autoOptimizeProducts({
        product_ids: selectedIds,
        auto_fill_price: autoFillPrice,
        auto_fill_images: autoFillImages,
        auto_fill_description: autoFillDescription,
      }) as any
      setOptimizeResult(result)
      message.success(`已处理 ${result.total_processed} 个产品，更新 ${result.total_updated} 个`)
      setSelectedIds([])
      fetchProducts()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '优化失败')
    } finally {
      setOptimizing(false)
    }
  }

  const handleOpenUpdate = (product: ProductItem) => {
    setUpdateProductId(product.id)
    const tags = product.meta?.tags
    updateForm.setFieldsValue({
      name: product.name || '',
      description: product.description || '',
      category: product.category || '',
      brand: product.meta?.brand as string || '',
      price: product.meta?.price as string || '',
      tags: Array.isArray(tags) ? tags.join(', ') : '',
    })
    setUpdateModalOpen(true)
  }

  const handleSaveUpdate = async () => {
    try {
      const values = await updateForm.validateFields()
      setUpdating(true)
      await api.fullUpdateProduct(updateProductId, {
        name: values.name || undefined,
        description: values.description || undefined,
        category: values.category || undefined,
        brand: values.brand || undefined,
        price: values.price || undefined,
        tags: values.tags ? values.tags.split(',').map((t: string) => t.trim()).filter(Boolean) : undefined,
      })
      message.success('产品更新成功')
      setUpdateModalOpen(false)
      fetchProducts()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '更新失败')
    } finally {
      setUpdating(false)
    }
  }

  const integrityStatusColor: Record<string, string> = {
    complete: 'green',
    partial: 'orange',
    missing: 'red',
  }

  const columns = [
    {
      title: 'SKU',
      dataIndex: 'sku',
      key: 'sku',
      width: 180,
      render: (sku: string) => <Text code>{sku}</Text>,
    },
    {
      title: '产品名称',
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
      render: (name: string) => name || <Text type="secondary">未命名</Text>,
    },
    {
      title: '类目',
      dataIndex: 'category',
      key: 'category',
      width: 120,
      render: (v: string) => v ? <Tag color="blue">{v}</Tag> : <Tag>未分类</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (v: string) => (
        <Tag color={v === 'active' ? 'green' : v === 'draft' ? 'default' : 'gold'}>
          {v || 'unknown'}
        </Tag>
      ),
    },
    {
      title: '数据完整度',
      key: 'integrity',
      width: 160,
      render: (_: any, record: ProductItem) => (
        <Space direction="vertical" size={0}>
          <Progress
            percent={Math.round(record.data_integrity_score || 0)}
            size="small"
            status={record.data_integrity_status === 'complete' ? 'success' : record.data_integrity_status === 'partial' ? 'normal' : 'exception'}
            showInfo={false}
          />
          <Tag color={integrityStatusColor[record.data_integrity_status] || 'default'}>
            {record.data_integrity_status || 'unknown'}
          </Tag>
        </Space>
      ),
    },
    {
      title: '缺失字段',
      dataIndex: 'data_integrity_missing',
      key: 'missing',
      ellipsis: true,
      render: (missing: string[]) =>
        missing && missing.length > 0 ? (
          <Tooltip title={missing.join(', ')}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {missing.slice(0, 3).join(', ')}{missing.length > 3 ? ` +${missing.length - 3}` : ''}
            </Text>
          </Tooltip>
        ) : (
          <CheckCircleOutlined style={{ color: '#52c41a' }} />
        ),
    },
    {
      title: '操作',
      key: 'action',
      width: 120,
      render: (_: any, record: ProductItem) => (
        <Button
          size="small"
          icon={<SettingOutlined />}
          onClick={() => handleOpenUpdate(record)}
        >
          编辑
        </Button>
      ),
    },
  ]

  const missingCount = products.filter(p => (p.data_integrity_score || 0) < 60).length
  const avgScore = products.length > 0
    ? Math.round(products.reduce((s, p) => s + (p.data_integrity_score || 0), 0) / products.length)
    : 0

  return (
    <div style={{ padding: 24 }}>
      <div style={{ marginBottom: 24 }}>
        <Typography.Title level={3} style={{ marginBottom: 4 }}>
          <RobotOutlined style={{ marginRight: 8, color: '#1890ff' }} />
          产品数据增强
        </Typography.Title>
        <Typography.Text type="secondary">
          自动补充产品缺失数据，提升数据完整度评分
        </Typography.Text>
      </div>

      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic title="产品总数" value={products.length} suffix="个" />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="低完整度"
              value={missingCount}
              suffix="个"
              valueStyle={{ color: missingCount > 0 ? '#ff4d4f' : '#52c41a' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="完整度 ≥ 60%"
              value={products.length - missingCount}
              suffix="个"
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="平均完整度" value={avgScore} suffix="%" />
          </Card>
        </Col>
      </Row>

      {/* 自动优化工具栏 */}
      <Card
        title={
          <Space>
            <RobotOutlined />
            <span>批量自动优化</span>
          </Space>
        }
        style={{ marginBottom: 24 }}
      >
        <Space wrap>
          <Typography.Text>自动填充:</Typography.Text>
          <Select
            value={autoFillPrice ? 'price' : undefined}
            onChange={(v) => setAutoFillPrice(v === 'price')}
            style={{ width: 100 }}
            options={[{ value: 'price', label: '价格' }]}
          />
          <Select
            value={autoFillImages ? 'images' : undefined}
            onChange={(v) => setAutoFillImages(v === 'images')}
            style={{ width: 100 }}
            options={[{ value: 'images', label: '图片' }]}
          />
          <Select
            value={autoFillDescription ? 'description' : undefined}
            onChange={(v) => setAutoFillDescription(v === 'description')}
            style={{ width: 100 }}
            options={[{ value: 'description', label: '描述' }]}
          />
          <Button
            type="primary"
            icon={<ReloadOutlined />}
            loading={optimizing}
            disabled={selectedIds.length === 0}
            onClick={handleAutoOptimize}
          >
            开始优化 ({selectedIds.length})
          </Button>
          <Button onClick={fetchProducts} icon={<ReloadOutlined />}>
            刷新
          </Button>
        </Space>
        {optimizeResult && (
          <Alert
            style={{ marginTop: 16 }}
            type="success"
            icon={<CheckCircleOutlined />}
            message={`处理完成: ${optimizeResult.total_processed} 个产品，更新 ${optimizeResult.total_updated} 个`}
          />
        )}
      </Card>

      {/* 产品列表 */}
      <Card
        title={
          <Space>
            <DatabaseOutlined />
            <span>产品数据列表</span>
            <Tag color="blue">{products.length} 个</Tag>
          </Space>
        }
        extra={
          <Button type="link" onClick={() => navigate('/products/workbench')}>
            返回工作台
          </Button>
        }
      >
        <Table
          rowKey="id"
          columns={columns}
          dataSource={products}
          loading={loading}
          rowSelection={{
            selectedRowKeys: selectedIds,
            onChange: (keys) => setSelectedIds(keys as string[]),
          }}
          pagination={{ pageSize: 20, showSizeChanger: true }}
        />
      </Card>

      {/* 全字段更新弹窗 */}
      <Modal
        title={<Space><SettingOutlined />编辑产品信息</Space>}
        open={updateModalOpen}
        onOk={handleSaveUpdate}
        onCancel={() => setUpdateModalOpen(false)}
        confirmLoading={updating}
        width={600}
        destroyOnHidden
      >
        <Form form={updateForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="name" label="产品名称">
            <Input placeholder="请输入产品名称" />
          </Form.Item>
          <Form.Item name="description" label="产品描述">
            <Input.TextArea rows={3} placeholder="请输入产品描述" />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="category" label="类目">
                <Input placeholder="如: 户外装备" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="brand" label="品牌">
                <Input placeholder="如: Nuotao" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="price" label="售价">
                <Input prefix="¥" placeholder="如: 199.00" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="tags" label="标签（逗号分隔）">
                <Input placeholder="如: 户外, 登山, 背包" />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>
    </div>
  )
}
