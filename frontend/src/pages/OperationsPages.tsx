import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Image,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  AppstoreAddOutlined,
  CalculatorOutlined,
  CheckCircleOutlined,
  CloudSyncOutlined,
  CustomerServiceOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  DollarOutlined,
  FileSearchOutlined,
  InboxOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  ShopOutlined,
  ShoppingCartOutlined,
  TeamOutlined,
  TruckOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { api, ApiError, request } from '../api/client'

const { Title, Text, Paragraph } = Typography

interface ResourcePageProps {
  kicker: string
  title: string
  description: string
  onRefresh?: () => void
  loading?: boolean
  extra?: ReactNode
  error?: string | null
  children: ReactNode
}

function ResourcePage({
  kicker,
  title,
  description,
  onRefresh,
  loading,
  extra,
  error,
  children,
}: ResourcePageProps) {
  return (
    <div className="resource-page">
      <div className="page-heading">
        <div>
          <div className="page-kicker">{kicker}</div>
          <Title level={2}>{title}</Title>
          <Paragraph>{description}</Paragraph>
        </div>
        <Space wrap>
          {extra}
          {onRefresh && (
            <Button icon={<ReloadOutlined />} onClick={onRefresh} loading={loading}>
              刷新
            </Button>
          )}
        </Space>
      </div>
      {error && (
        <Alert
          className="page-alert"
          type="error"
          showIcon
          title="真实数据加载失败"
          description={error}
        />
      )}
      {children}
    </div>
  )
}

function emptyText(label: string) {
  return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={label} />
}

function apiErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.traceId ? `${error.message}（Trace: ${error.traceId}）` : error.message
  }
  return error instanceof Error ? error.message : '未知错误'
}

function currency(value: unknown, currencyCode = 'USD'): string {
  const amount = Number(value || 0)
  return `${currencyCode} ${amount.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

interface ProductRecord {
  id: string
  sku: string
  name: string
  description: string | null
  category: string | null
  brand: string | null
  status: string
  candidate_status: string | null
  source: string
  source_url: string | null
  attributes: Record<string, unknown>
  meta: Record<string, any>
  weight_kg: number | string | null
  dimensions: Record<string, unknown> | null
  target_market: string
  created_at: string
  updated_at: string
}

const productStatus: Record<string, { color: string; label: string }> = {
  active: { color: 'green', label: '可销售' },
  draft: { color: 'default', label: '草稿' },
  inactive: { color: 'orange', label: '停用' },
  pending: { color: 'blue', label: '待审核' },
}

function productImages(product: ProductRecord | null): string[] {
  if (!product) return []
  const media = product.meta?.media
  const candidates = media?.images || media?.gallery_images || product.meta?.images || []
  if (!Array.isArray(candidates)) return []
  return Array.from(
    new Set(
      candidates
        .map((item) => (typeof item === 'string' ? item : item?.url || item?.src))
        .filter((url): url is string => typeof url === 'string' && /^https?:\/\//.test(url)),
    ),
  )
}

function englishLocalization(product: ProductRecord | null): Record<string, any> | null {
  const localization = product?.meta?.localizations?.en
  return localization && typeof localization === 'object' ? localization : null
}

export function ProductsPage() {
  const [products, setProducts] = useState<ProductRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('all')
  const [selectedKeys, setSelectedKeys] = useState<React.Key[]>([])
  const [pushing, setPushing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [detailProduct, setDetailProduct] = useState<ProductRecord | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await api.getProducts(500, 0, status === 'all' ? undefined : status)
      setProducts((response as ProductRecord[]) || [])
    } catch (loadError) {
      setProducts([])
      setError(apiErrorMessage(loadError))
    } finally {
      setLoading(false)
    }
  }, [status])

  useEffect(() => {
    void load()
  }, [load])

  const visibleProducts = useMemo(() => {
    const keyword = search.trim().toLowerCase()
    if (!keyword) return products
    return products.filter((product) =>
      [product.name, product.sku, product.category, product.brand]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(keyword)),
    )
  }, [products, search])

  const stats = useMemo(
    () => ({
      total: products.length,
      sellable: products.filter((product) => product.status === 'active').length,
      candidate: products.filter((product) => Boolean(product.candidate_status)).length,
      missingSource: products.filter((product) => !product.source_url).length,
    }),
    [products],
  )

  const syncProducts = () => {
    Modal.confirm({
      title: '从 WooCommerce 同步商品主数据',
      content: '同步会按 workspace + SKU 更新本地商品记录，数据量较大时可能需要较长时间。',
      okText: '开始同步',
      cancelText: '取消',
      onOk: async () => {
        try {
          const result = (await api.syncProductsFromWooCommerce()) as Record<string, unknown>
          message.success(
            `同步完成：新增/更新 ${Number(result.imported || result.updated || 0)}，失败 ${Number(result.failed || 0)}`,
          )
          await load()
        } catch (syncError) {
          message.error(`同步失败：${apiErrorMessage(syncError)}`)
          throw syncError
        }
      },
    })
  }

  const pushSelected = async () => {
    if (selectedKeys.length === 0) {
      message.warning('请先选择需要推送的商品')
      return
    }
    setPushing(true)
    try {
      const result = (await api.pushProductsToWooCommerce(selectedKeys.map(String))) as {
        success?: number
        failed?: number
        blocked?: number
        needs_review?: number
        results?: Array<{
          product_id?: string
          sku?: string | null
          status?: string
          message?: string
        }>
      }
      const ok = Number(result.success || 0)
      const blocked = Number(result.blocked || 0)
      const review = Number(result.needs_review || 0)
      const errored = Math.max(0, Number(result.failed || 0) - blocked - review)
      const results = result.results || []
      const problems = results.filter((r) => r.status && r.status !== 'pushed')

      // 200 只表示批量请求处理完，不代表商品都进了 WooCommerce：闸门阻断和
      // 待人工复核都不计入失败，但商品同样没推上去。按结果分级提示，否则
      // 全绿的"成功"会掩盖需要运营补数据或复核的商品。
      const parts = [
        ok ? `成功 ${ok}` : null,
        blocked ? `闸门阻断 ${blocked}` : null,
        review ? `待人工复核 ${review}` : null,
        errored ? `推送失败 ${errored}` : null,
      ].filter(Boolean) as string[]

      const summary = `推送完成：${parts.join('，')}`
      if (problems.length) message.warning(summary)
      else message.success(summary)

      if (problems.length > 0) {
        Modal.info({
          title: '部分商品未完成推送',
          width: 640,
          content: (
            <div>
              <ul style={{ marginBottom: 0, paddingLeft: 20, maxHeight: 320, overflow: 'auto' }}>
                {problems.map((r, i) => (
                  <li key={i}>
                    <strong>{r.sku || '(无 SKU)'}</strong>
                    {` — ${r.message || r.status}`}
                  </li>
                ))}
              </ul>
              <p style={{ marginTop: 12, marginBottom: 0, color: '#888' }}>
                闸门阻断需回候选库补全数据；待人工复核可在单个推送时确认强制放行。
              </p>
            </div>
          ),
        })
      }

      // 只清掉真正推上去的，剩下待处理的保留勾选，便于继续处理。
      const pushed = new Set(
        results.filter((r) => r.status === 'pushed' && r.product_id).map((r) => String(r.product_id)),
      )
      setSelectedKeys(selectedKeys.filter((k) => !pushed.has(String(k))))
      await load()
    } catch (pushError) {
      message.error(`推送失败：${apiErrorMessage(pushError)}`)
    } finally {
      setPushing(false)
    }
  }

  const deleteOne = (product: ProductRecord) => {
    Modal.confirm({
      title: '删除该商品？',
      content: `将软删「${product.name}」（SKU: ${product.sku}），列表不再显示，可在数据库中恢复。`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        const result = (await api.deleteProduct(String(product.id))) as {
          deleted: number
          not_found: string[]
        }
        if (result.deleted > 0) {
          message.success(`已删除 ${result.deleted} 个商品`)
        } else {
          message.warning('该商品已被删除或不存在')
        }
        setSelectedKeys((keys) => keys.filter((key) => String(key) !== String(product.id)))
        await load()
      },
    })
  }

  const batchDelete = () => {
    if (selectedKeys.length === 0) {
      message.warning('请先勾选需要删除的商品')
      return
    }
    const count = selectedKeys.length
    Modal.confirm({
      title: `批量删除选中的 ${count} 个商品？`,
      content: '将对选中商品执行软删，列表不再显示，可在数据库中恢复。',
      okText: `删除 ${count} 个`,
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        setDeleting(true)
        try {
          const result = (await api.batchDeleteProducts(selectedKeys.map(String))) as {
            deleted: number
            not_found: string[]
          }
          message.success(
            `已删除 ${result.deleted} 个` +
              (result.not_found.length ? `，${result.not_found.length} 个不存在已跳过` : ''),
          )
          setSelectedKeys([])
          await load()
        } catch (deleteError) {
          message.error(`删除失败：${apiErrorMessage(deleteError)}`)
          throw deleteError
        } finally {
          setDeleting(false)
        }
      },
    })
  }

  const columns: ColumnsType<ProductRecord> = [
    {
      title: '商品',
      dataIndex: 'name',
      render: (value: string, record) => (
        <div className="primary-cell">
          <strong>{value}</strong>
          <span>SKU: {record.sku}</span>
        </div>
      ),
    },
    { title: '分类', dataIndex: 'category', width: 130, render: (value) => value || '-' },
    { title: '品牌', dataIndex: 'brand', width: 130, render: (value) => value || '-' },
    {
      title: '业务状态',
      dataIndex: 'status',
      width: 110,
      render: (value: string) => {
        const display = productStatus[value] || { color: 'default', label: value }
        return <Tag color={display.color}>{display.label}</Tag>
      },
    },
    {
      title: '候选状态',
      dataIndex: 'candidate_status',
      width: 110,
      render: (value: string | null) => (value ? <Tag>{value}</Tag> : <Text type="secondary">商品主数据</Text>),
    },
    { title: '来源', dataIndex: 'source', width: 100 },
    { title: '目标市场', dataIndex: 'target_market', width: 100 },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      width: 155,
      render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: '操作',
      key: 'actions',
      fixed: 'right',
      width: 130,
      render: (_, record) => (
        <Space size={0}>
          <Button
            type="link"
            size="small"
            onClick={() => {
              setDetailProduct(record)
              setDetailOpen(true)
            }}
          >
            查看
          </Button>
          <Button
            type="link"
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => deleteOne(record)}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ]

  const detailImages = productImages(detailProduct)
  const localization = englishLocalization(detailProduct)
  const detailAttributes = Object.entries(detailProduct?.attributes || {})

  return (
    <ResourcePage
      kicker="SHARED PRODUCT MASTER"
      title="商品与 AI 选品"
      description="B2C 与 B2B 共享同一套商品、成本和供应链主数据；渠道价格与销售状态在各自业务域管理。"
      onRefresh={() => void load()}
      loading={loading}
      error={error}
      extra={
        <>
          <Button
            icon={<CloudSyncOutlined />}
            onClick={syncProducts}
            disabled={Boolean(error)}
          >
            同步 WooCommerce
          </Button>
          <Button
            type="primary"
            icon={<AppstoreAddOutlined />}
            onClick={() => void pushSelected()}
            loading={pushing}
          >
            推送选中商品
          </Button>
          <Button
            danger
            icon={<DeleteOutlined />}
            onClick={batchDelete}
            loading={deleting}
            disabled={selectedKeys.length === 0}
          >
            批量删除{selectedKeys.length > 0 ? `（${selectedKeys.length}）` : ''}
          </Button>
        </>
      }
    >
      <Row gutter={[14, 14]} className="resource-metrics">
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="商品主数据" value={stats.total} prefix={<ShopOutlined />} /></Card></Col>
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="可销售" value={stats.sellable} styles={{ content: { color: '#2f8b64' } }} /></Card></Col>
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="候选商品" value={stats.candidate} /></Card></Col>
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="缺少来源链接" value={stats.missingSource} styles={{ content: { color: '#c27622' } }} /></Card></Col>
      </Row>

      <Card variant="borderless" className="resource-panel">
        <div className="resource-toolbar">
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索名称、SKU、分类或品牌"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <Select
            value={status}
            onChange={setStatus}
            options={[
              { value: 'all', label: '全部状态' },
              { value: 'active', label: '可销售' },
              { value: 'draft', label: '草稿' },
              { value: 'pending', label: '待审核' },
              { value: 'inactive', label: '停用' },
            ]}
          />
          <Text type="secondary">当前展示 {visibleProducts.length} 条</Text>
        </div>
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={visibleProducts}
          rowSelection={{ selectedRowKeys: selectedKeys, onChange: setSelectedKeys }}
          scroll={{ x: 1100 }}
          pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (total) => `共 ${total} 条` }}
          locale={{ emptyText: emptyText('当前没有商品主数据') }}
        />
      </Card>
      <Drawer
        width={760}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        title={detailProduct?.name || '商品详情'}
      >
        {detailProduct && (
          <Space direction="vertical" size={18} style={{ width: '100%' }}>
            <Descriptions
              size="small"
              column={2}
              items={[
                { key: 'sku', label: 'SKU', children: detailProduct.sku },
                {
                  key: 'status',
                  label: '业务状态',
                  children: productStatus[detailProduct.status]?.label || detailProduct.status,
                },
                { key: 'category', label: '分类', children: detailProduct.category || '-' },
                { key: 'brand', label: '品牌', children: detailProduct.brand || '-' },
                {
                  key: 'candidate',
                  label: '候选状态',
                  children: detailProduct.candidate_status || '商品主数据',
                },
                { key: 'market', label: '目标市场', children: detailProduct.target_market || '-' },
                {
                  key: 'source',
                  label: '来源',
                  span: 2,
                  children: detailProduct.source_url ? (
                    <a href={detailProduct.source_url} target="_blank" rel="noreferrer">
                      {detailProduct.source_url}
                    </a>
                  ) : (
                    detailProduct.source
                  ),
                },
                {
                  key: 'weight',
                  label: '重量',
                  children: detailProduct.weight_kg ? `${detailProduct.weight_kg} kg` : '待补充',
                },
                {
                  key: 'dimensions',
                  label: '尺寸',
                  children: detailProduct.dimensions
                    ? JSON.stringify(detailProduct.dimensions)
                    : '待补充',
                },
              ]}
            />

            <div>
              <Text strong>商品描述</Text>
              <Paragraph style={{ marginTop: 8, whiteSpace: 'pre-wrap' }}>
                {detailProduct.description || '尚未导入商品描述'}
              </Paragraph>
            </div>

            <div>
              <Text strong>商品主图与详情图</Text>
              {detailImages.length > 0 ? (
                <Image.PreviewGroup>
                  <Space wrap size={12} style={{ marginTop: 10 }}>
                    {detailImages.map((url, index) => (
                      <Space key={url} direction="vertical" size={4}>
                        <Image
                          src={url}
                          alt={`商品图片 ${index + 1}`}
                          width={150}
                          height={150}
                          style={{ objectFit: 'cover', borderRadius: 8 }}
                        />
                        <Text type="secondary">{index === 0 ? '主图' : `详情图 ${index}`}</Text>
                      </Space>
                    ))}
                  </Space>
                </Image.PreviewGroup>
              ) : (
                emptyText('当前商品没有持久化图片')
              )}
            </div>

            <div>
              <Text strong>商品参数</Text>
              {detailAttributes.length > 0 ? (
                <Descriptions
                  size="small"
                  column={1}
                  style={{ marginTop: 10 }}
                  items={detailAttributes.map(([key, value]) => ({
                    key,
                    label: key,
                    children:
                      typeof value === 'string' || typeof value === 'number'
                        ? String(value)
                        : JSON.stringify(value),
                  }))}
                />
              ) : (
                <Paragraph type="secondary">尚未导入结构化参数</Paragraph>
              )}
            </div>

            <div>
              <Text strong>英文文案</Text>
              {localization ? (
                <Space direction="vertical" size={8} style={{ width: '100%', marginTop: 10 }}>
                  <Space wrap>
                    <Tag color={localization.status === 'approved' ? 'green' : 'orange'}>
                      {localization.status === 'approved' ? '已确认' : '待确认'}
                    </Tag>
                    <Text strong>{localization.title}</Text>
                  </Space>
                  <Paragraph style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
                    {localization.description}
                  </Paragraph>
                  {Array.isArray(localization.bullet_points) && (
                    <Space wrap>
                      {localization.bullet_points.map((item: string) => (
                        <Tag key={item}>{item}</Tag>
                      ))}
                    </Space>
                  )}
                </Space>
              ) : (
                <Paragraph type="secondary">尚未生成英文文案</Paragraph>
              )}
            </div>
          </Space>
        )}
      </Drawer>
    </ResourcePage>
  )
}

interface OrderRecord {
  id: string
  external_order_id: string
  status: string
  payment_status: string | null
  fulfillment_status: string | null
  currency: string
  country: string | null
  source: string
  total: number
  received_at: string
  profit_snapshot: Record<string, unknown>
}

interface OrderListResponse {
  items: OrderRecord[]
  total: number
}

interface OrderDetail extends OrderRecord {
  items: Array<{
    id: string
    sku: string | null
    name: string
    quantity: number
    unit_price: number
    line_total: number
  }>
}

export function OrdersPage() {
  const [orders, setOrders] = useState<OrderRecord[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState('all')
  const [search, setSearch] = useState('')
  const [detail, setDetail] = useState<OrderDetail | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = (await api.getOrders(
        200,
        0,
        status === 'all' ? undefined : status,
        search.trim() || undefined,
      )) as OrderListResponse
      setOrders(response.items || [])
      setTotal(response.total || 0)
    } catch (loadError) {
      setOrders([])
      setTotal(0)
      setError(apiErrorMessage(loadError))
    } finally {
      setLoading(false)
    }
  }, [search, status])

  useEffect(() => {
    void load()
  }, [load])

  const openDetail = async (orderId: string) => {
    try {
      const response = (await api.getOrder(orderId)) as OrderDetail
      setDetail(response)
      setDetailOpen(true)
    } catch (detailError) {
      message.error(`订单详情加载失败：${apiErrorMessage(detailError)}`)
    }
  }

  const syncOrders = () => {
    Modal.confirm({
      title: '从 WooCommerce 同步零售订单',
      content: '默认同步最近 30 天、最多 500 个订单。同步完成后可刷新查看真实结果。',
      okText: '开始同步',
      cancelText: '取消',
      onOk: async () => {
        try {
          const result = (await api.syncOrdersFromWooCommerce()) as Record<string, unknown>
          message.success(
            `同步完成：订单 ${Number(result.total_orders || result.synced || 0)}，客户 ${Number(result.new_customers || 0)}`,
          )
          await load()
        } catch (syncError) {
          message.error(`同步失败：${apiErrorMessage(syncError)}`)
          throw syncError
        }
      },
    })
  }

  const stats = useMemo(
    () => ({
      revenue: orders.reduce((sum, order) => sum + Number(order.total || 0), 0),
      paid: orders.filter((order) => order.payment_status === 'completed').length,
      pending: orders.filter((order) =>
        ['pending', 'on-hold', 'received'].includes(order.status),
      ).length,
      countries: new Set(orders.map((order) => order.country).filter(Boolean)).size,
    }),
    [orders],
  )

  const columns: ColumnsType<OrderRecord> = [
    {
      title: '订单',
      dataIndex: 'external_order_id',
      render: (value: string, record) => (
        <div className="primary-cell">
          <Button type="link" onClick={() => void openDetail(record.id)}>#{value}</Button>
          <span>{record.source}</span>
        </div>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (value: string) => <Tag color={value === 'completed' ? 'green' : value === 'cancelled' ? 'red' : 'blue'}>{value}</Tag>,
    },
    {
      title: '支付',
      dataIndex: 'payment_status',
      width: 110,
      render: (value: string | null) => value ? <Tag color={value === 'completed' ? 'green' : 'orange'}>{value}</Tag> : <Text type="secondary">未知</Text>,
    },
    {
      title: '履约',
      dataIndex: 'fulfillment_status',
      width: 110,
      render: (value: string | null) => value || <Text type="secondary">未同步</Text>,
    },
    { title: '国家', dataIndex: 'country', width: 80, render: (value) => value || '-' },
    {
      title: '订单金额',
      dataIndex: 'total',
      align: 'right',
      width: 130,
      render: (value: number, record) => currency(value, record.currency),
    },
    {
      title: '接收时间',
      dataIndex: 'received_at',
      width: 160,
      render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: '操作',
      width: 90,
      render: (_, record) => <Button type="link" onClick={() => void openDetail(record.id)}>详情</Button>,
    },
  ]

  return (
    <ResourcePage
      kicker="B2C RETAIL ORDER DESK"
      title="B2C 零售订单"
      description="当前视图只展示零售订单接口返回的真实数据。B2B 订单使用独立的报价、合同和账期状态机。"
      onRefresh={() => void load()}
      loading={loading}
      error={error}
      extra={<Button type="primary" icon={<CloudSyncOutlined />} onClick={syncOrders}>同步 WooCommerce 订单</Button>}
    >
      <Row gutter={[14, 14]} className="resource-metrics">
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="当前批次订单" value={orders.length} prefix={<ShoppingCartOutlined />} /></Card></Col>
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="当前批次收入" value={stats.revenue} precision={2} prefix="$" /></Card></Col>
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="待处理" value={stats.pending} styles={{ content: { color: '#c27622' } }} /></Card></Col>
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="覆盖国家" value={stats.countries} /></Card></Col>
      </Row>

      <Card variant="borderless" className="resource-panel">
        <div className="resource-toolbar">
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="输入 WooCommerce 订单号查询"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            onPressEnter={() => void load()}
          />
          <Select
            value={status}
            onChange={setStatus}
            options={[
              { value: 'all', label: '全部状态' },
              { value: 'pending', label: '待付款' },
              { value: 'processing', label: '处理中' },
              { value: 'completed', label: '已完成' },
              { value: 'cancelled', label: '已取消' },
              { value: 'refunded', label: '已退款' },
            ]}
          />
          <Button icon={<SearchOutlined />} onClick={() => void load()}>查询</Button>
          <Text type="secondary">数据库共 {total} 条</Text>
        </div>
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={orders}
          scroll={{ x: 1050 }}
          pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (count) => `当前页共 ${count} 条` }}
          locale={{ emptyText: emptyText('当前筛选条件下没有订单') }}
        />
      </Card>

      <Drawer title="订单详情" size={720} open={detailOpen} onClose={() => setDetailOpen(false)}>
        {detail ? (
          <Space direction="vertical" size={18} style={{ width: '100%' }}>
            <Descriptions bordered size="small" column={2}>
              <Descriptions.Item label="订单号" span={2}>#{detail.external_order_id}</Descriptions.Item>
              <Descriptions.Item label="状态">{detail.status}</Descriptions.Item>
              <Descriptions.Item label="支付">{detail.payment_status || '-'}</Descriptions.Item>
              <Descriptions.Item label="国家">{detail.country || '-'}</Descriptions.Item>
              <Descriptions.Item label="订单金额">{currency(detail.total, detail.currency)}</Descriptions.Item>
              <Descriptions.Item label="来源">{detail.source}</Descriptions.Item>
              <Descriptions.Item label="接收时间">{dayjs(detail.received_at).format('YYYY-MM-DD HH:mm:ss')}</Descriptions.Item>
            </Descriptions>
            <Table
              size="small"
              rowKey="id"
              pagination={false}
              dataSource={detail.items || []}
              columns={[
                { title: '商品', dataIndex: 'name' },
                { title: 'SKU', dataIndex: 'sku', render: (value) => value || '-' },
                { title: '数量', dataIndex: 'quantity', width: 70 },
                { title: '单价', dataIndex: 'unit_price', width: 100, render: (value) => currency(value, detail.currency) },
                { title: '小计', dataIndex: 'line_total', width: 100, render: (value) => currency(value, detail.currency) },
              ]}
            />
          </Space>
        ) : (
          emptyText('暂无订单详情')
        )}
      </Drawer>
    </ResourcePage>
  )
}

interface CustomerRecord {
  id: string
  customer_reference_id: string
  country: string | null
  language: string | null
  segment: string | null
  tags: string[]
  total_orders: number
  total_revenue: number
  first_order_at: string | null
  updated_at: string
}

interface InteractionRecord {
  id: string
  channel: string
  interaction_type: string
  content: string
  sentiment: string
  created_at: string
}

export function CustomersPage() {
  const [customers, setCustomers] = useState<CustomerRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [segment, setSegment] = useState('all')
  const [selected, setSelected] = useState<CustomerRecord | null>(null)
  const [interactions, setInteractions] = useState<InteractionRecord[]>([])
  const [interactionLoading, setInteractionLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await api.getCustomerProfiles(500, 0, segment === 'all' ? undefined : segment)
      setCustomers((response as CustomerRecord[]) || [])
    } catch (loadError) {
      setCustomers([])
      setError(apiErrorMessage(loadError))
    } finally {
      setLoading(false)
    }
  }, [segment])

  useEffect(() => {
    void load()
  }, [load])

  const visibleCustomers = useMemo(() => {
    const keyword = search.trim().toLowerCase()
    if (!keyword) return customers
    return customers.filter((customer) =>
      [customer.customer_reference_id, customer.country, customer.segment, ...(customer.tags || [])]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(keyword)),
    )
  }, [customers, search])

  const openCustomer = async (customer: CustomerRecord) => {
    setSelected(customer)
    setInteractionLoading(true)
    try {
      const response = await api.getCustomerInteractions(100, customer.id)
      setInteractions((response as InteractionRecord[]) || [])
    } catch {
      setInteractions([])
    } finally {
      setInteractionLoading(false)
    }
  }

  const stats = useMemo(
    () => ({
      total: customers.length,
      repeat: customers.filter((customer) => customer.total_orders > 1).length,
      revenue: customers.reduce((sum, customer) => sum + Number(customer.total_revenue || 0), 0),
      segments: new Set(customers.map((customer) => customer.segment).filter(Boolean)).size,
    }),
    [customers],
  )

  const columns: ColumnsType<CustomerRecord> = [
    {
      title: '客户引用号',
      dataIndex: 'customer_reference_id',
      render: (value: string, record) => (
        <Button type="link" onClick={() => void openCustomer(record)}>{value}</Button>
      ),
    },
    { title: '国家', dataIndex: 'country', width: 80, render: (value) => value || '-' },
    { title: '语言', dataIndex: 'language', width: 90, render: (value) => value || '-' },
    {
      title: '分群',
      dataIndex: 'segment',
      width: 110,
      render: (value: string | null) => value ? <Tag color="blue">{value}</Tag> : <Text type="secondary">未分群</Text>,
    },
    { title: '订单数', dataIndex: 'total_orders', width: 90 },
    {
      title: '累计消费',
      dataIndex: 'total_revenue',
      align: 'right',
      width: 130,
      render: (value: number) => currency(value),
    },
    {
      title: '最近更新',
      dataIndex: 'updated_at',
      width: 155,
      render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm'),
    },
  ]

  return (
    <ResourcePage
      kicker="NON-PII CUSTOMER INTELLIGENCE"
      title="B2C 客户"
      description="客户档案仅保存非识别性引用号和行为聚合数据，不展示姓名、邮箱、电话或地址等 PII。"
      onRefresh={() => void load()}
      loading={loading}
      error={error}
    >
      <Row gutter={[14, 14]} className="resource-metrics">
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="客户档案" value={stats.total} prefix={<TeamOutlined />} /></Card></Col>
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="复购客户" value={stats.repeat} styles={{ content: { color: '#2f8b64' } }} /></Card></Col>
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="累计消费" value={stats.revenue} precision={2} prefix="$" /></Card></Col>
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="客户分群" value={stats.segments} /></Card></Col>
      </Row>

      <Card variant="borderless" className="resource-panel">
        <div className="resource-toolbar">
          <Input allowClear prefix={<SearchOutlined />} placeholder="搜索客户引用号、国家或标签" value={search} onChange={(event) => setSearch(event.target.value)} />
          <Select
            value={segment}
            onChange={setSegment}
            options={[
              { value: 'all', label: '全部分群' },
              { value: 'new', label: '新客户' },
              { value: 'returning', label: '复购客户' },
              { value: 'vip', label: 'VIP' },
              { value: 'churn_risk', label: '流失风险' },
            ]}
          />
          <Text type="secondary">当前展示 {visibleCustomers.length} 条</Text>
        </div>
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={visibleCustomers}
          scroll={{ x: 900 }}
          pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (total) => `共 ${total} 条` }}
          locale={{ emptyText: emptyText('当前没有客户档案') }}
        />
      </Card>

      <Drawer title="客户档案与互动" size={720} open={Boolean(selected)} onClose={() => setSelected(null)}>
        {selected && (
          <Space direction="vertical" size={18} style={{ width: '100%' }}>
            <Descriptions bordered size="small" column={2}>
              <Descriptions.Item label="引用号" span={2}>{selected.customer_reference_id}</Descriptions.Item>
              <Descriptions.Item label="国家">{selected.country || '-'}</Descriptions.Item>
              <Descriptions.Item label="语言">{selected.language || '-'}</Descriptions.Item>
              <Descriptions.Item label="订单数">{selected.total_orders}</Descriptions.Item>
              <Descriptions.Item label="累计消费">{currency(selected.total_revenue)}</Descriptions.Item>
              <Descriptions.Item label="标签" span={2}>
                {(selected.tags || []).length ? selected.tags.map((tag) => <Tag key={tag}>{tag}</Tag>) : '-'}
              </Descriptions.Item>
            </Descriptions>
            <Table
              size="small"
              rowKey="id"
              loading={interactionLoading}
              dataSource={interactions}
              pagination={{ pageSize: 8 }}
              locale={{ emptyText: emptyText('暂无互动记录') }}
              columns={[
                { title: '渠道', dataIndex: 'channel', width: 90 },
                { title: '类型', dataIndex: 'interaction_type', width: 100 },
                { title: '内容', dataIndex: 'content', ellipsis: true },
                { title: '情绪', dataIndex: 'sentiment', width: 90 },
                { title: '时间', dataIndex: 'created_at', width: 140, render: (value) => dayjs(value).format('YYYY-MM-DD HH:mm') },
              ]}
            />
          </Space>
        )}
      </Drawer>
    </ResourcePage>
  )
}

interface CampaignRecord {
  id: string
  platform: string
  campaign_id: string
  name: string | null
  status: string
  currency: string
  budget: number
  spend: number
  impressions: number
  clicks: number
  conversion: number
  revenue: number
  roas: string | number | null
  roi: string | number | null
  started_at: string | null
  updated_at: string
}

export function MarketingPage() {
  const [campaigns, setCampaigns] = useState<CampaignRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm()

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await api.getCampaigns(200)
      setCampaigns((response as CampaignRecord[]) || [])
    } catch (loadError) {
      setCampaigns([])
      setError(apiErrorMessage(loadError))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const stats = useMemo(() => {
    const spend = campaigns.reduce((sum, row) => sum + Number(row.spend || 0), 0)
    const revenue = campaigns.reduce((sum, row) => sum + Number(row.revenue || 0), 0)
    const conversions = campaigns.reduce((sum, row) => sum + Number(row.conversion || 0), 0)
    const clicks = campaigns.reduce((sum, row) => sum + Number(row.clicks || 0), 0)
    const impressions = campaigns.reduce((sum, row) => sum + Number(row.impressions || 0), 0)
    return {
      spend,
      revenue,
      conversion: conversions,
      ctr: impressions > 0 ? (clicks / impressions) * 100 : 0,
      roas: spend > 0 ? revenue / spend : 0,
    }
  }, [campaigns])

  const createCampaign = async () => {
    try {
      const values = await form.validateFields()
      setSaving(true)
      await api.createCampaign(values)
      message.success('营销活动已登记，后续表现以平台回传数据为准')
      setModalOpen(false)
      form.resetFields()
      await load()
    } catch (createError) {
      if (createError instanceof Error) {
        message.error(`创建失败：${apiErrorMessage(createError)}`)
      }
    } finally {
      setSaving(false)
    }
  }

  const columns: ColumnsType<CampaignRecord> = [
    {
      title: '活动',
      dataIndex: 'name',
      render: (value: string | null, record) => (
        <div className="primary-cell">
          <strong>{value || record.campaign_id}</strong>
          <span>{record.campaign_id}</span>
        </div>
      ),
    },
    { title: '平台', dataIndex: 'platform', width: 100, render: (value) => <Tag>{value}</Tag> },
    { title: '状态', dataIndex: 'status', width: 100 },
    { title: '预算', dataIndex: 'budget', align: 'right', width: 110, render: (value, row) => currency(value, row.currency) },
    { title: '花费', dataIndex: 'spend', align: 'right', width: 110, render: (value, row) => currency(value, row.currency) },
    { title: '收入', dataIndex: 'revenue', align: 'right', width: 110, render: (value, row) => currency(value, row.currency) },
    { title: '转化', dataIndex: 'conversion', align: 'right', width: 80 },
    {
      title: 'ROAS',
      dataIndex: 'roas',
      width: 90,
      render: (value, row) => {
        const calculated = Number(value ?? 0) || (Number(row.spend) > 0 ? Number(row.revenue) / Number(row.spend) : 0)
        return calculated ? calculated.toFixed(2) : '-'
      },
    },
  ]

  return (
    <ResourcePage
      kicker="B2C GROWTH OPERATIONS"
      title="B2C 营销"
      description="只展示已回传并入库的营销数据。系统不会自动创建广告、修改预算或宣称投放成功。"
      onRefresh={() => void load()}
      loading={loading}
      error={error}
      extra={<Button type="primary" onClick={() => setModalOpen(true)}>登记营销活动</Button>}
    >
      <Row gutter={[14, 14]} className="resource-metrics">
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="累计花费" value={stats.spend} precision={2} prefix="$" /></Card></Col>
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="归因收入" value={stats.revenue} precision={2} prefix="$" /></Card></Col>
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="转化" value={stats.conversion} prefix={<CheckCircleOutlined />} /></Card></Col>
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="ROAS" value={stats.roas} precision={2} suffix={`CTR ${stats.ctr.toFixed(2)}%`} /></Card></Col>
      </Row>
      <Card variant="borderless" className="resource-panel">
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={campaigns}
          scroll={{ x: 950 }}
          pagination={{ pageSize: 20, showTotal: (total) => `共 ${total} 条` }}
          locale={{ emptyText: emptyText('暂无已入库的营销活动') }}
        />
      </Card>
      <Modal title="登记营销活动" open={modalOpen} onOk={() => void createCampaign()} onCancel={() => setModalOpen(false)} confirmLoading={saving} okText="登记" cancelText="取消">
        <Form form={form} layout="vertical" initialValues={{ platform: 'meta', status: 'active', currency: 'USD', budget: 0 }}>
          <Form.Item name="campaign_id" label="平台活动 ID" rules={[{ required: true, message: '请输入平台活动 ID' }]}>
            <Input placeholder="例如 Meta campaign id" />
          </Form.Item>
          <Form.Item name="name" label="活动名称"><Input /></Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="platform" label="平台" rules={[{ required: true }]}>
                <Select options={['meta', 'google', 'tiktok', 'pinterest', 'other'].map((value) => ({ value, label: value }))} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="status" label="状态" rules={[{ required: true }]}>
                <Select options={['active', 'paused', 'completed', 'archived'].map((value) => ({ value, label: value }))} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="budget" label="预算" rules={[{ required: true }]}>
            <InputNumber min={0} precision={2} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </ResourcePage>
  )
}

interface SupplierRecord {
  id: string
  code: string
  name: string
  platform: string
  shop_url: string | null
  rating: string
  status: string
  contact: Record<string, unknown>
  created_at: string
}

export function SuppliersPage() {
  const [suppliers, setSuppliers] = useState<SupplierRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [modalOpen, setModalOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm()

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await api.getSuppliers(500, undefined, search.trim() || undefined)
      setSuppliers((response as SupplierRecord[]) || [])
    } catch (loadError) {
      setSuppliers([])
      setError(apiErrorMessage(loadError))
    } finally {
      setLoading(false)
    }
  }, [search])

  useEffect(() => {
    void load()
  }, [load])

  const createSupplier = async () => {
    try {
      const values = await form.validateFields()
      setSaving(true)
      await api.createSupplier(values)
      message.success('供应商已创建')
      setModalOpen(false)
      form.resetFields()
      await load()
    } catch (createError) {
      if (createError instanceof Error) {
        message.error(`创建失败：${apiErrorMessage(createError)}`)
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <ResourcePage
      kicker="SHARED SUPPLY BASE"
      title="采购与供应商"
      description="B2C 与 B2B 共用的供应商主数据。供应商评级和风险画像需要独立的数据证据支持。"
      onRefresh={() => void load()}
      loading={loading}
      error={error}
      extra={<Button type="primary" icon={<ShopOutlined />} onClick={() => setModalOpen(true)}>新增供应商</Button>}
    >
      <Card variant="borderless" className="resource-panel">
        <div className="resource-toolbar">
          <Input allowClear prefix={<SearchOutlined />} placeholder="搜索供应商编号或名称" value={search} onChange={(event) => setSearch(event.target.value)} onPressEnter={() => void load()} />
          <Button icon={<SearchOutlined />} onClick={() => void load()}>查询</Button>
          <Text type="secondary">当前展示 {suppliers.length} 条</Text>
        </div>
        <Table
          rowKey="id"
          loading={loading}
          dataSource={suppliers}
          scroll={{ x: 900 }}
          pagination={{ pageSize: 20, showTotal: (total) => `共 ${total} 条` }}
          locale={{ emptyText: emptyText('当前没有供应商数据') }}
          columns={[
            { title: '供应商编号', dataIndex: 'code', width: 150 },
            { title: '供应商名称', dataIndex: 'name' },
            { title: '平台', dataIndex: 'platform', width: 100, render: (value) => <Tag>{value}</Tag> },
            { title: '评级', dataIndex: 'rating', width: 80 },
            { title: '状态', dataIndex: 'status', width: 100 },
            {
              title: '店铺',
              dataIndex: 'shop_url',
              width: 100,
              render: (value: string | null) => value ? <a href={value} target="_blank" rel="noreferrer">打开</a> : '-',
            },
            { title: '创建时间', dataIndex: 'created_at', width: 155, render: (value) => dayjs(value).format('YYYY-MM-DD HH:mm') },
          ]}
        />
      </Card>
      <Modal title="新增供应商" open={modalOpen} onOk={() => void createSupplier()} onCancel={() => setModalOpen(false)} confirmLoading={saving} okText="创建" cancelText="取消">
        <Form form={form} layout="vertical" initialValues={{ platform: '1688', rating: 'C', status: 'active' }}>
          <Form.Item name="code" label="供应商编号" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="name" label="供应商名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Row gutter={16}>
            <Col span={12}><Form.Item name="platform" label="平台"><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="rating" label="评级"><Select options={['A', 'B', 'C', 'D'].map((value) => ({ value, label: value }))} /></Form.Item></Col>
          </Row>
          <Form.Item name="shop_url" label="店铺链接"><Input /></Form.Item>
        </Form>
      </Modal>
    </ResourcePage>
  )
}

interface WarehouseRecord {
  id: string
  name: string
  type: string
  status: string
  country: string
  city: string
  total_sku: number
  created_at: string
}

interface InventorySnapshotRecord {
  id: string
  workspace_id: string
  product_id: string | null
  location: string
  quantity: number
  reserved: number
  available: number
  in_transit: number
  snapshot_time: string
  updated_at: string
}

const warehouseTypeLabels: Record<string, string> = {
  domestic: '国内仓',
  overseas: '海外仓',
  fulfillment_center: '履约中心',
  drop_shipping: '代发仓',
}

export function InventoryPage() {
  const [warehouses, setWarehouses] = useState<WarehouseRecord[]>([])
  const [snapshots, setSnapshots] = useState<InventorySnapshotRecord[]>([])
  const [location, setLocation] = useState('all')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [warehouseResponse, inventoryResponse] = await Promise.all([
        api.getWarehouses() as Promise<{ warehouses?: WarehouseRecord[] }>,
        api.getInventorySnapshots(200, location === 'all' ? undefined : location),
      ])
      setWarehouses(warehouseResponse.warehouses || [])
      setSnapshots((inventoryResponse as InventorySnapshotRecord[]) || [])
    } catch (loadError) {
      setWarehouses([])
      setSnapshots([])
      setError(apiErrorMessage(loadError))
    } finally {
      setLoading(false)
    }
  }, [location])

  useEffect(() => {
    void load()
  }, [load])

  const totals = useMemo(
    () =>
      snapshots.reduce(
        (result, row) => ({
          quantity: result.quantity + Number(row.quantity || 0),
          reserved: result.reserved + Number(row.reserved || 0),
          available: result.available + Number(row.available || 0),
          inTransit: result.inTransit + Number(row.in_transit || 0),
        }),
        { quantity: 0, reserved: 0, available: 0, inTransit: 0 },
      ),
    [snapshots],
  )

  return (
    <ResourcePage
      kicker="SHARED WMS INVENTORY"
      title="WMS 库存仓储"
      description="仓库和库存快照来自后端主数据。当前页面只提供只读台账，库存调整必须通过受审计的库存服务执行。"
      onRefresh={() => void load()}
      loading={loading}
      error={error}
    >
      <Alert
        className="page-alert"
        type="info"
        showIcon
        title="库存调整入口暂未开放"
        description="现有快照模型按商品和地区记录库存，尚未形成仓库库位、批次、冻结和盘点闭环。查看真实数据，不提供未审计的直接改库存按钮。"
      />
      <Row gutter={[14, 14]} className="resource-metrics">
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="仓库" value={warehouses.length} prefix={<DatabaseOutlined />} /></Card></Col>
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="账面库存" value={totals.quantity} /></Card></Col>
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="可用库存" value={totals.available} styles={{ content: { color: '#2f8b64' } }} /></Card></Col>
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="在途库存" value={totals.inTransit} styles={{ content: { color: '#4b7890' } }} /></Card></Col>
      </Row>
      <Row gutter={[14, 14]}>
        <Col xs={24} xl={9}>
          <Card variant="borderless" title="仓库主数据" className="resource-panel">
            <Table
              rowKey="id"
              loading={loading}
              dataSource={warehouses}
              pagination={false}
              locale={{ emptyText: emptyText('当前没有仓库主数据') }}
              columns={[
                { title: '仓库', dataIndex: 'name', render: (value: string, record) => <div className="primary-cell"><strong>{value}</strong><span>{record.city}, {record.country}</span></div> },
                { title: '类型', dataIndex: 'type', width: 100, render: (value: string) => <Tag>{warehouseTypeLabels[value] || value}</Tag> },
                { title: 'SKU', dataIndex: 'total_sku', width: 70 },
                { title: '状态', dataIndex: 'status', width: 90, render: (value: string) => <Tag color={value === 'active' ? 'green' : 'default'}>{value === 'active' ? '运营中' : value}</Tag> },
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} xl={15}>
          <Card variant="borderless" title="库存快照" className="resource-panel">
            <div className="resource-toolbar">
              <Select
                value={location}
                onChange={setLocation}
                options={[
                  { value: 'all', label: '全部地区' },
                  { value: 'cn', label: '中国' },
                  { value: 'us', label: '美国' },
                  { value: 'eu', label: '欧洲' },
                ]}
              />
              <Text type="secondary">当前展示 {snapshots.length} 条</Text>
            </div>
            <Table
              rowKey="id"
              loading={loading}
              dataSource={snapshots}
              scroll={{ x: 760 }}
              pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 条` }}
              locale={{ emptyText: emptyText('当前没有库存快照') }}
              columns={[
                { title: '商品 ID', dataIndex: 'product_id', width: 150, render: (value: string | null) => value ? value.slice(0, 8) : '未绑定' },
                { title: '地区', dataIndex: 'location', width: 80, render: (value: string) => <Tag>{value.toUpperCase()}</Tag> },
                { title: '账面', dataIndex: 'quantity', align: 'right', width: 90 },
                { title: '预占', dataIndex: 'reserved', align: 'right', width: 90 },
                { title: '可用', dataIndex: 'available', align: 'right', width: 90, render: (value: number) => <strong>{value}</strong> },
                { title: '在途', dataIndex: 'in_transit', align: 'right', width: 90 },
                { title: '快照时间', dataIndex: 'snapshot_time', width: 155, render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm') },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </ResourcePage>
  )
}

interface ShipmentRecord {
  id: string
  carrier: string
  origin: string | null
  destination: string | null
  tracking_number: string | null
  status: string
  ship_date: string | null
  delivery_time_days: number | null
  delay_reason: string | null
  updated_at: string
}

export function LogisticsPage() {
  const [shipments, setShipments] = useState<ShipmentRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState('all')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await api.getSupplyShipments(300, status === 'all' ? undefined : status)
      setShipments((response as ShipmentRecord[]) || [])
    } catch (loadError) {
      setShipments([])
      setError(apiErrorMessage(loadError))
    } finally {
      setLoading(false)
    }
  }, [status])

  useEffect(() => {
    void load()
  }, [load])

  const statusColor: Record<string, string> = {
    created: 'default',
    in_transit: 'blue',
    delivered: 'green',
    failed: 'red',
    delayed: 'orange',
  }

  return (
    <ResourcePage
      kicker="SHARED TMS OPERATIONS"
      title="TMS 国际物流"
      description="物流轨迹只来自 TMS 入库记录。缺少承运商或轨迹时显示未同步，不生成推测轨迹。"
      onRefresh={() => void load()}
      loading={loading}
      error={error}
    >
      <Row gutter={[14, 14]} className="resource-metrics">
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="物流单" value={shipments.length} prefix={<TruckOutlined />} /></Card></Col>
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="运输中" value={shipments.filter((row) => row.status === 'in_transit').length} styles={{ content: { color: '#4b7890' } }} /></Card></Col>
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="已送达" value={shipments.filter((row) => row.status === 'delivered').length} styles={{ content: { color: '#2f8b64' } }} /></Card></Col>
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="异常/延迟" value={shipments.filter((row) => ['failed', 'delayed'].includes(row.status)).length} styles={{ content: { color: '#bd4b4b' } }} /></Card></Col>
      </Row>
      <Card variant="borderless" className="resource-panel">
        <div className="resource-toolbar">
          <Select
            value={status}
            onChange={setStatus}
            options={[
              { value: 'all', label: '全部状态' },
              { value: 'created', label: '已创建' },
              { value: 'in_transit', label: '运输中' },
              { value: 'delivered', label: '已送达' },
              { value: 'delayed', label: '延迟' },
              { value: 'failed', label: '失败' },
            ]}
          />
          <Text type="secondary">当前展示 {shipments.length} 条</Text>
        </div>
        <Table
          rowKey="id"
          loading={loading}
          dataSource={shipments}
          scroll={{ x: 1000 }}
          pagination={{ pageSize: 20, showTotal: (total) => `共 ${total} 条` }}
          locale={{ emptyText: emptyText('当前没有物流记录') }}
          columns={[
            { title: '承运商', dataIndex: 'carrier', width: 110 },
            { title: '物流单号', dataIndex: 'tracking_number', width: 180, render: (value) => value || <Text type="secondary">未回填</Text> },
            { title: '状态', dataIndex: 'status', width: 100, render: (value) => <Tag color={statusColor[value] || 'default'}>{value}</Tag> },
            { title: '起点', dataIndex: 'origin', render: (value) => value || '-' },
            { title: '目的地', dataIndex: 'destination', render: (value) => value || '-' },
            { title: '发货日期', dataIndex: 'ship_date', width: 120, render: (value) => value ? dayjs(value).format('YYYY-MM-DD') : '-' },
            { title: '时效天数', dataIndex: 'delivery_time_days', width: 90, render: (value) => value ?? '-' },
            { title: '异常原因', dataIndex: 'delay_reason', ellipsis: true, render: (value) => value || '-' },
          ]}
        />
      </Card>
    </ResourcePage>
  )
}

interface RefundRecord {
  id: string
  order_id: string | null
  reason: string
  category: string
  refund_type: string
  requested_amount: number
  status: string
  approved_amount: number | null
  executed_amount: number | null
  payment_provider: string
  error_message: string | null
  retry_count: number
  created_at: string
  updated_at: string
}

export function AfterSalesPage() {
  const [refunds, setRefunds] = useState<RefundRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState('all')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await api.getRefunds(200, status === 'all' ? undefined : status)
      setRefunds((response as RefundRecord[]) || [])
    } catch (loadError) {
      setRefunds([])
      setError(apiErrorMessage(loadError))
    } finally {
      setLoading(false)
    }
  }, [status])

  useEffect(() => {
    void load()
  }, [load])

  const pending = refunds.filter((row) =>
    ['requested', 'pending_approval', 'approved', 'processing'].includes(row.status),
  ).length

  return (
    <ResourcePage
      kicker="B2C AFTER-SALES"
      title="B2C 售后与退款"
      description="退款状态只以后端状态机为准。支付渠道未配置时会明确失败，不会伪造退款成功。"
      onRefresh={() => void load()}
      loading={loading}
      error={error}
    >
      <Alert
        className="page-alert"
        type="success"
        showIcon
        title="退款写操作已启用可信身份与 RBAC"
        description="创建、提交、审批、驳回、取消、执行和重试均记录认证用户；支付渠道未配置时执行退款会明确失败。"
      />
      <Row gutter={[14, 14]} className="resource-metrics">
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="退款案件" value={refunds.length} prefix={<CustomerServiceOutlined />} /></Card></Col>
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="处理中" value={pending} styles={{ content: { color: '#c27622' } }} /></Card></Col>
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="已成功" value={refunds.filter((row) => row.status === 'succeeded').length} styles={{ content: { color: '#2f8b64' } }} /></Card></Col>
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="失败待处理" value={refunds.filter((row) => row.status === 'failed').length} styles={{ content: { color: '#bd4b4b' } }} /></Card></Col>
      </Row>
      <Card variant="borderless" className="resource-panel">
        <div className="resource-toolbar">
          <Select
            value={status}
            onChange={setStatus}
            options={[
              { value: 'all', label: '全部状态' },
              { value: 'requested', label: '已申请' },
              { value: 'pending_approval', label: '待审批' },
              { value: 'approved', label: '已批准' },
              { value: 'processing', label: '处理中' },
              { value: 'succeeded', label: '已退款' },
              { value: 'failed', label: '失败' },
              { value: 'rejected', label: '已拒绝' },
            ]}
          />
          <Text type="secondary">当前展示 {refunds.length} 条</Text>
        </div>
        <Table
          rowKey="id"
          loading={loading}
          dataSource={refunds}
          scroll={{ x: 1100 }}
          pagination={{ pageSize: 20, showTotal: (total) => `共 ${total} 条` }}
          locale={{ emptyText: emptyText('当前没有退款案件') }}
          columns={[
            { title: '订单', dataIndex: 'order_id', width: 180, render: (value) => value ? `#${value.slice(0, 8)}` : '-' },
            { title: '原因', dataIndex: 'reason', ellipsis: true },
            { title: '分类', dataIndex: 'category', width: 110, render: (value) => <Tag>{value}</Tag> },
            { title: '类型', dataIndex: 'refund_type', width: 90 },
            { title: '申请金额', dataIndex: 'requested_amount', align: 'right', width: 110, render: (value) => currency(value) },
            { title: '状态', dataIndex: 'status', width: 120, render: (value) => <Tag color={value === 'succeeded' ? 'green' : value === 'failed' ? 'red' : 'blue'}>{value}</Tag> },
            { title: '支付渠道', dataIndex: 'payment_provider', width: 110 },
            { title: '重试', dataIndex: 'retry_count', width: 70 },
            { title: '更新时间', dataIndex: 'updated_at', width: 155, render: (value) => dayjs(value).format('YYYY-MM-DD HH:mm') },
          ]}
        />
      </Card>
    </ResourcePage>
  )
}

interface DashboardSummary {
  today?: {
    revenue?: {
      total_revenue?: number
      estimated_cost?: number
      gross_profit?: number
      gross_margin_percent?: number
    }
    orders?: number
    customers?: number
  }
  week?: {
    revenue?: {
      total_revenue?: number
      gross_profit?: number
    }
    orders?: number
  }
}

export function FinanceOverviewPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [refunds, setRefunds] = useState<RefundRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [summaryResponse, refundResponse] = await Promise.all([
        api.getDashboardSummary(),
        api.getRefunds(200),
      ])
      setSummary(summaryResponse as DashboardSummary)
      setRefunds((refundResponse as RefundRecord[]) || [])
    } catch (loadError) {
      setSummary(null)
      setRefunds([])
      setError(apiErrorMessage(loadError))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const revenue = summary?.today?.revenue?.total_revenue || 0
  const estimatedCost = summary?.today?.revenue?.estimated_cost || 0
  const profit = summary?.today?.revenue?.gross_profit || 0
  const margin = summary?.today?.revenue?.gross_margin_percent || 0
  const refunded = refunds
    .filter((row) => row.status === 'succeeded')
    .reduce((sum, row) => sum + Number(row.executed_amount ?? row.requested_amount ?? 0), 0)

  return (
    <ResourcePage
      kicker="FINANCE CONTROL"
      title="财务对账"
      description="展示后端已回传的收入、预估成本、毛利和已执行退款。这里不推断未入账收入或缺失成本。"
      onRefresh={() => void load()}
      loading={loading}
      error={error}
    >
      <Row gutter={[14, 14]} className="resource-metrics">
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="今日收入" value={revenue} precision={2} prefix={<DollarOutlined />} /></Card></Col>
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="预估成本" value={estimatedCost} precision={2} prefix={<CalculatorOutlined />} /></Card></Col>
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="毛利" value={profit} precision={2} styles={{ content: { color: profit >= 0 ? '#2f8b64' : '#bd4b4b' } }} /></Card></Col>
        <Col xs={12} lg={6}><Card variant="borderless"><Statistic title="毛利率" value={margin} precision={1} suffix="%" /></Card></Col>
      </Row>
      <Row gutter={[14, 14]}>
        <Col xs={24} lg={10}>
          <Card variant="borderless" title="财务数据边界" className="resource-panel">
            <Descriptions column={1} size="small">
              <Descriptions.Item label="今日订单">{summary?.today?.orders ?? 0}</Descriptions.Item>
              <Descriptions.Item label="今日客户">{summary?.today?.customers ?? 0}</Descriptions.Item>
              <Descriptions.Item label="已执行退款">{currency(refunded)}</Descriptions.Item>
              <Descriptions.Item label="退款案件">{refunds.length}</Descriptions.Item>
            </Descriptions>
            <Alert
              type="warning"
              showIcon
              title="成本可信度"
              description="预估成本依赖商品成本快照和物流费用。成本缺失时不得把预估值当作已核对利润。"
            />
          </Card>
        </Col>
        <Col xs={24} lg={14}>
          <Card variant="borderless" title="最近退款" className="resource-panel">
            <Table
              size="small"
              rowKey="id"
              loading={loading}
              dataSource={refunds.slice(0, 8)}
              pagination={false}
              locale={{ emptyText: emptyText('暂无退款记录') }}
              columns={[
                { title: '状态', dataIndex: 'status', width: 110, render: (value) => <Tag>{value}</Tag> },
                { title: '原因', dataIndex: 'reason', ellipsis: true },
                { title: '金额', dataIndex: 'requested_amount', align: 'right', width: 110, render: (value) => currency(value) },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </ResourcePage>
  )
}

interface PurchaseOrderRecord {
  id: string
  po_number: string
  supplier_id: string | null
  status: string
  currency: string
  subtotal: string | number
  shipping_cost: string | number
  total: string | number
  expected_delivery_at: string | null
  created_at: string
}

interface PurchaseOrderFormValues {
  po_number: string
  supplier_id: string
  currency: string
  shipping_cost?: number
  notes?: string
  items: Array<{
    sku: string
    name: string
    quantity: number
    unit_cost: number
  }>
}

const PURCHASE_STATUS_META: Record<string, { label: string; color: string }> = {
  draft: { label: '草稿', color: 'default' },
  approved: { label: '已审批', color: 'blue' },
  ordered: { label: '已下单', color: 'purple' },
  partial_received: { label: '部分收货', color: 'orange' },
  received: { label: '已收货', color: 'green' },
  cancelled: { label: '已取消', color: 'red' },
}

const PURCHASE_ACTION_META: Record<
  'approve' | 'order' | 'partial-receive' | 'receive' | 'cancel',
  {
    confirmTitle: string
    confirmContent: string
    okText: string
    successMessage: string
    failurePrefix: string
    run: (purchaseOrderId: string) => Promise<unknown>
  }
> = {
  approve: {
    confirmTitle: '审批采购单',
    confirmContent: '审批后采购单将进入可下单状态，但不会自动向供应商付款或下单。',
    okText: '确认审批',
    successMessage: '采购单已审批',
    failurePrefix: '审批失败',
    run: api.approveSupplyPurchaseOrder,
  },
  order: {
    confirmTitle: '确认已向供应商下单',
    confirmContent: '请先在 1688 或供应商渠道完成真实下单，再确认此动作。',
    okText: '确认已下单',
    successMessage: '采购单已标记为已下单',
    failurePrefix: '下单状态更新失败',
    run: api.orderSupplyPurchaseOrder,
  },
  'partial-receive': {
    confirmTitle: '登记部分收货',
    confirmContent: '仅在第一批货物真实到达后操作，系统不会自动核验实物数量。',
    okText: '确认部分收货',
    successMessage: '采购单已更新为部分收货',
    failurePrefix: '部分收货更新失败',
    run: api.partialReceiveSupplyPurchaseOrder,
  },
  receive: {
    confirmTitle: '确认全部收货',
    confirmContent: '确认采购商品已全部到货后，采购单将结束收货流程。',
    okText: '确认全部收货',
    successMessage: '采购单已确认收货',
    failurePrefix: '收货更新失败',
    run: api.receiveSupplyPurchaseOrder,
  },
  cancel: {
    confirmTitle: '取消采购单',
    confirmContent: '取消后该采购单不能继续审批或收货，请确认没有已发生的采购承诺。',
    okText: '确认取消',
    successMessage: '采购单已取消',
    failurePrefix: '取消失败',
    run: api.cancelSupplyPurchaseOrder,
  },
}

export function PurchaseOrdersPage() {
  const [orders, setOrders] = useState<PurchaseOrderRecord[]>([])
  const [suppliers, setSuppliers] = useState<SupplierRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [form] = Form.useForm<PurchaseOrderFormValues>()

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [orderResponse, supplierResponse] = await Promise.all([
        api.getSupplyPurchaseOrders(300),
        api.getSuppliers(500, 'active'),
      ])
      setOrders((orderResponse as PurchaseOrderRecord[]) || [])
      setSuppliers((supplierResponse as SupplierRecord[]) || [])
    } catch (loadError) {
      setOrders([])
      setSuppliers([])
      setError(apiErrorMessage(loadError))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const openCreate = () => {
    form.resetFields()
    form.setFieldsValue({
      po_number: `PO-${dayjs().format('YYYYMMDD-HHmmss')}`,
      currency: 'CNY',
      shipping_cost: 0,
      items: [{ quantity: 1, unit_cost: 0 }],
    })
    setCreateOpen(true)
  }

  const createPurchaseOrder = async () => {
    try {
      const values = await form.validateFields()
      if (!values.items?.length) {
        message.warning('至少添加一个采购商品')
        return
      }
      setSaving(true)
      await api.createSupplyPurchaseOrder({
        po_number: values.po_number.trim(),
        supplier_id: values.supplier_id,
        currency: values.currency,
        shipping_cost: values.shipping_cost || 0,
        notes: values.notes?.trim() || null,
        items: values.items.map((item) => ({
          sku: item.sku.trim(),
          name: item.name.trim(),
          quantity: item.quantity,
          unit_cost: item.unit_cost,
        })),
      })
      message.success('采购订单已创建，状态为草稿')
      setCreateOpen(false)
      form.resetFields()
      await load()
    } catch (createError) {
      if (createError instanceof Error) {
        message.error(`创建失败：${apiErrorMessage(createError)}`)
      }
    } finally {
      setSaving(false)
    }
  }

  const runAction = (
    order: PurchaseOrderRecord,
    action: 'approve' | 'order' | 'partial-receive' | 'receive' | 'cancel',
  ) => {
    const meta = PURCHASE_ACTION_META[action]
    Modal.confirm({
      title: `${meta.confirmTitle}：${order.po_number}`,
      content: meta.confirmContent,
      okText: meta.okText,
      cancelText: '取消',
      okButtonProps: action === 'cancel' ? { danger: true } : undefined,
      onOk: async () => {
        setActionLoading(`${action}:${order.id}`)
        try {
          await meta.run(order.id)
          message.success(meta.successMessage)
          await load()
        } catch (actionError) {
          message.error(`${meta.failurePrefix}：${apiErrorMessage(actionError)}`)
          throw actionError
        } finally {
          setActionLoading(null)
        }
      },
    })
  }

  return (
    <ResourcePage
      kicker="SHARED PROCUREMENT"
      title="采购订单"
      description="采购单使用独立生命周期：草稿、审批、下单、收货与取消。库存只应通过后端状态流转更新。"
      onRefresh={() => void load()}
      loading={loading}
      error={error}
      extra={<Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建采购单</Button>}
    >
      <Card variant="borderless" className="resource-panel">
        <Table
          rowKey="id"
          loading={loading}
          dataSource={orders}
          scroll={{ x: 1250 }}
          pagination={{ pageSize: 20, showTotal: (total) => `共 ${total} 条` }}
          locale={{ emptyText: emptyText('暂无采购订单，点击右上角“新建采购单”开始') }}
          columns={[
            { title: '采购单号', dataIndex: 'po_number', width: 180 },
            {
              title: '供应商',
              dataIndex: 'supplier_id',
              width: 180,
              render: (value: string | null) => {
                const supplier = suppliers.find((item) => item.id === value)
                return supplier ? `${supplier.code} · ${supplier.name}` : '-'
              },
            },
            {
              title: '状态',
              dataIndex: 'status',
              width: 110,
              render: (value: string) => {
                const meta = PURCHASE_STATUS_META[value] || { label: value, color: 'default' }
                return <Tag color={meta.color}>{meta.label}</Tag>
              },
            },
            { title: '币种', dataIndex: 'currency', width: 80 },
            { title: '小计', dataIndex: 'subtotal', align: 'right', width: 110 },
            { title: '运费', dataIndex: 'shipping_cost', align: 'right', width: 110 },
            { title: '合计', dataIndex: 'total', align: 'right', width: 110 },
            { title: '预计到货', dataIndex: 'expected_delivery_at', width: 150, render: (value) => value ? dayjs(String(value)).format('YYYY-MM-DD HH:mm') : '-' },
            { title: '创建时间', dataIndex: 'created_at', width: 150, render: (value) => dayjs(String(value)).format('YYYY-MM-DD HH:mm') },
            {
              title: '操作',
              key: 'actions',
              fixed: 'right',
              width: 230,
              render: (_, record) => (
                <Space size={4}>
                  {record.status === 'draft' && (
                    <>
                      <Button
                        type="link"
                        size="small"
                        loading={actionLoading === `approve:${record.id}`}
                        onClick={() => runAction(record, 'approve')}
                      >
                        审批
                      </Button>
                      <Button
                        type="link"
                        size="small"
                        danger
                        loading={actionLoading === `cancel:${record.id}`}
                        onClick={() => runAction(record, 'cancel')}
                      >
                        取消
                      </Button>
                    </>
                  )}
                  {record.status === 'approved' && (
                    <>
                      <Button
                        type="link"
                        size="small"
                        loading={actionLoading === `order:${record.id}`}
                        onClick={() => runAction(record, 'order')}
                      >
                        下单
                      </Button>
                      <Button
                        type="link"
                        size="small"
                        danger
                        loading={actionLoading === `cancel:${record.id}`}
                        onClick={() => runAction(record, 'cancel')}
                      >
                        取消
                      </Button>
                    </>
                  )}
                  {record.status === 'ordered' && (
                    <>
                      <Button
                        type="link"
                        size="small"
                        loading={actionLoading === `partial-receive:${record.id}`}
                        onClick={() => runAction(record, 'partial-receive')}
                      >
                        分批收货
                      </Button>
                      <Button
                        type="link"
                        size="small"
                        loading={actionLoading === `receive:${record.id}`}
                        onClick={() => runAction(record, 'receive')}
                      >
                        确认收货
                      </Button>
                    </>
                  )}
                  {record.status === 'partial_received' && (
                    <Button
                      type="link"
                      size="small"
                      loading={actionLoading === `receive:${record.id}`}
                      onClick={() => runAction(record, 'receive')}
                    >
                      确认收货
                    </Button>
                  )}
                  {!['draft', 'approved', 'ordered', 'partial_received'].includes(record.status) && (
                    <Text type="secondary">已结束</Text>
                  )}
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        width={760}
        title="新建采购单"
        open={createOpen}
        okText="创建草稿"
        cancelText="取消"
        confirmLoading={saving}
        onOk={() => void createPurchaseOrder()}
        onCancel={() => setCreateOpen(false)}
        forceRender
      >
        <Form<PurchaseOrderFormValues> form={form} layout="vertical">
          <Row gutter={12}>
            <Col xs={24} md={12}>
              <Form.Item
                name="po_number"
                label="采购单号"
                rules={[{ required: true, message: '请输入采购单号' }]}
              >
                <Input placeholder="例如 PO-20260913-001" />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item
                name="supplier_id"
                label="供应商"
                rules={[{ required: true, message: '请选择供应商' }]}
              >
                <Select
                  showSearch
                  optionFilterProp="label"
                  placeholder="请选择已创建的供应商"
                  options={suppliers.map((supplier) => ({
                    value: supplier.id,
                    label: `${supplier.code} · ${supplier.name}`,
                  }))}
                  notFoundContent="暂无供应商，请先到“采购与供应商”创建"
                />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={12}>
            <Col xs={24} md={12}>
              <Form.Item
                name="currency"
                label="币种"
                rules={[{ required: true, message: '请选择币种' }]}
              >
                <Select
                  options={['CNY', 'USD', 'EUR'].map((value) => ({ value, label: value }))}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item name="shipping_cost" label="运费">
                <InputNumber min={0} precision={2} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>

          <Form.List name="items">
            {(fields, { add, remove }) => (
              <Space orientation="vertical" size={10} style={{ width: '100%' }}>
                <Text strong>采购商品</Text>
                {fields.map((field, index) => (
                  <Card
                    key={field.key}
                    size="small"
                    title={`商品 ${index + 1}`}
                    extra={
                      fields.length > 1 ? (
                        <Button
                          type="text"
                          danger
                          size="small"
                          icon={<DeleteOutlined />}
                          onClick={() => remove(field.name)}
                        >
                          删除
                        </Button>
                      ) : null
                    }
                  >
                    <Row gutter={12}>
                      <Col xs={24} md={8}>
                        <Form.Item
                          name={[field.name, 'sku']}
                          label="SKU"
                          rules={[{ required: true, message: '请输入 SKU' }]}
                        >
                          <Input placeholder="例如 NTO-001" />
                        </Form.Item>
                      </Col>
                      <Col xs={24} md={8}>
                        <Form.Item
                          name={[field.name, 'name']}
                          label="商品名称"
                          rules={[{ required: true, message: '请输入商品名称' }]}
                        >
                          <Input placeholder="采购商品名称" />
                        </Form.Item>
                      </Col>
                      <Col xs={12} md={4}>
                        <Form.Item
                          name={[field.name, 'quantity']}
                          label="数量"
                          rules={[{ required: true, message: '请输入数量' }]}
                        >
                          <InputNumber min={1} precision={0} style={{ width: '100%' }} />
                        </Form.Item>
                      </Col>
                      <Col xs={12} md={4}>
                        <Form.Item
                          name={[field.name, 'unit_cost']}
                          label="采购单价"
                          rules={[{ required: true, message: '请输入采购单价' }]}
                        >
                          <InputNumber min={0} precision={2} style={{ width: '100%' }} />
                        </Form.Item>
                      </Col>
                    </Row>
                  </Card>
                ))}
                <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({ quantity: 1, unit_cost: 0 })} block>
                  添加采购商品
                </Button>
              </Space>
            )}
          </Form.List>

          <Form.Item name="notes" label="采购备注" style={{ marginTop: 16 }}>
            <Input.TextArea rows={2} maxLength={1000} placeholder="例如：要求供应商提供无品牌包装" />
          </Form.Item>
        </Form>
      </Modal>
    </ResourcePage>
  )
}

export function ApiCapabilityPage() {
  return (
    <ResourcePage
      kicker="SYSTEM GOVERNANCE"
      title="API 与连接器"
      description="连接器健康度、凭证轮换和失败重试必须在后端统一管理，前端只展示脱敏状态。"
    >
      <Alert
        type="warning"
        showIcon
        title="治理接口尚未完成前端接入"
        description="当前后端已有连接器和系统设置接口，但缺少统一的管理员权限、密钥脱敏和写操作审计契约。"
      />
    </ResourcePage>
  )
}
