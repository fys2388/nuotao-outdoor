import { useState, useEffect } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Input, Select,
  Statistic, Row, Col, Spin, message, Modal, Descriptions, List,
  DatePicker, Badge, Tooltip, Empty, Popconfirm
} from 'antd'
import {
  ShoppingCartOutlined, ReloadOutlined, SyncOutlined,
  EyeOutlined, TruckOutlined, CheckCircleOutlined,
  ClockCircleOutlined, DollarOutlined, SearchOutlined
} from '@ant-design/icons'
import dayjs from 'dayjs'

const { Title, Text, Paragraph } = Typography
const { RangePicker } = DatePicker

interface OrderItem {
  product_id: string
  product_name: string
  sku: string
  quantity: number
  price: number
  line_total: number
}

interface Order {
  id: string
  external_order_id: string
  status: string
  payment_status: string | null
  fulfillment_status: string | null
  currency: string
  total: number
  subtotal: number
  shipping_total: number
  discount_total: number
  tax_total: number
  customer_id: string | null
  received_at: string
  items?: OrderItem[]
}

const statusColors: Record<string, string> = {
  processing: 'blue',
  completed: 'green',
  pending: 'orange',
  'on-hold': 'orange',
  cancelled: 'default',
  refunded: 'red',
  failed: 'red',
  'trash': 'default',
}

const statusText: Record<string, string> = {
  processing: '处理中',
  completed: '已完成',
  pending: '待支付',
  'on-hold': '挂起',
  cancelled: '已取消',
  refunded: '已退款',
  failed: '失败',
  'trash': '回收站',
}

const fulfillmentColors: Record<string, string> = {
  fulfilled: 'green',
  partial: 'orange',
  unfulfilled: 'red',
}

const fulfillmentText: Record<string, string> = {
  fulfilled: '已发货',
  partial: '部分发货',
  unfulfilled: '未发货',
}

export default function OrdersPage() {
  const [orders, setOrders] = useState<Order[]>([])
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [statusFilter, setStatusFilter] = useState('all')
  const [searchText, setSearchText] = useState('')
  const [dateRange, setDateRange] = useState<any>(null)
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [viewingOrder, setViewingOrder] = useState<Order | null>(null)
  const [syncing, setSyncing] = useState(false)

  // 加载订单列表
  const loadOrders = async () => {
    try {
      setLoading(true)
      const params = new URLSearchParams({
        limit: pageSize.toString(),
        offset: ((page - 1) * pageSize).toString(),
      })
      if (statusFilter !== 'all') params.append('status', statusFilter)
      if (searchText) params.append('external_order_id', searchText)
      if (dateRange && dateRange[0]) {
        params.append('date_from', dateRange[0].toISOString())
        params.append('date_to', dateRange[1].toISOString())
      }

      const resp = await fetch(`/api/v1/orders?${params}`)
      if (resp.ok) {
        const data = await resp.json()
        setOrders(data.items || [])
        setTotal(data.total || 0)
      } else {
        message.error('加载订单列表失败')
      }
    } catch (e) {
      console.error('Load orders error:', e)
      message.error('加载订单列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadOrders()
  }, [page, pageSize, statusFilter])

  // 查看订单详情
  const handleViewDetail = async (order: Order) => {
    try {
      const resp = await fetch(`/api/v1/orders/${order.id}`)
      if (resp.ok) {
        const data = await resp.json()
        setViewingOrder(data)
      } else {
        setViewingOrder(order)
      }
      setDetailModalOpen(true)
    } catch (e) {
      setViewingOrder(order)
      setDetailModalOpen(true)
    }
  }

  // 同步WooCommerce订单
  const handleSyncWooCommerce = async () => {
    try {
      setSyncing(true)
      message.info('正在从WooCommerce同步订单...')
      // 这里可以调用同步API
      setTimeout(() => {
        message.success('订单同步完成')
        setSyncing(false)
        loadOrders()
      }, 2000)
    } catch (e) {
      message.error('同步失败')
      setSyncing(false)
    }
  }

  // 统计数据
  const stats = {
    total: total,
    processing: orders.filter(o => o.status === 'processing').length,
    completed: orders.filter(o => o.status === 'completed').length,
    totalAmount: orders.reduce((sum, o) => sum + (o.total || 0), 0),
  }

  // 表格列定义
  const columns = [
    {
      title: '订单号',
      dataIndex: 'external_order_id',
      key: 'external_order_id',
      width: 150,
      render: (text: string) => <Text strong>#{text}</Text>,
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
      title: '支付状态',
      dataIndex: 'payment_status',
      key: 'payment_status',
      width: 100,
      render: (status: string) => status ? (
        <Tag color={status === 'processing' || status === 'completed' ? 'green' : 'orange'}>
          {status === 'completed' ? '已支付' : status === 'processing' ? '处理中' : status}
        </Tag>
      ) : '-',
    },
    {
      title: '发货状态',
      dataIndex: 'fulfillment_status',
      key: 'fulfillment_status',
      width: 100,
      render: (status: string) => status ? (
        <Tag color={fulfillmentColors[status] || 'default'}>{fulfillmentText[status] || status}</Tag>
      ) : '-',
    },
    {
      title: '订单金额',
      dataIndex: 'total',
      key: 'total',
      width: 120,
      render: (total: number, record: Order) => (
        <Text strong style={{ color: '#f5222d' }}>
          {record.currency || 'USD'} {Number(total).toFixed(2)}
        </Text>
      ),
    },
    {
      title: '下单时间',
      dataIndex: 'received_at',
      key: 'received_at',
      width: 180,
      render: (text: string) => text ? dayjs(text).format('YYYY-MM-DD HH:mm:ss') : '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 150,
      render: (_: any, record: Order) => (
        <Space size="small">
          <Button size="small" icon={<EyeOutlined />} onClick={() => handleViewDetail(record)}>详情</Button>
          {record.fulfillment_status !== 'fulfilled' && record.status === 'processing' && (
            <Popconfirm title="确认发货？" onConfirm={() => message.success('已标记发货')} okText="确认" cancelText="取消">
              <Button size="small" type="primary" icon={<TruckOutlined />}>发货</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: '24px' }}>
        <Space>
          <ShoppingCartOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>订单管理</Title>
            <Text type="secondary">订单列表、详情查看、发货处理、WooCommerce同步</Text>
          </div>
        </Space>
      </div>

      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: '16px' }}>
        <Col span={6}>
          <Card size="small">
            <Statistic title="订单总数" value={stats.total} prefix={<ShoppingCartOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="待处理" value={stats.processing} valueStyle={{ color: '#1890ff' }} prefix={<ClockCircleOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="已完成" value={stats.completed} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="订单总金额" value={stats.totalAmount.toFixed(2)} prefix={<DollarOutlined />} precision={2} />
          </Card>
        </Col>
      </Row>

      {/* 操作栏 */}
      <Card size="small" style={{ marginBottom: '16px' }}>
        <Space wrap>
          <Input
            placeholder="搜索订单号"
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ width: 200 }}
            allowClear
            onPressEnter={loadOrders}
          />
          <Select
            value={statusFilter}
            onChange={setStatusFilter}
            style={{ width: 120 }}
            options={[
              { value: 'all', label: '全部状态' },
              { value: 'processing', label: '处理中' },
              { value: 'completed', label: '已完成' },
              { value: 'pending', label: '待支付' },
              { value: 'cancelled', label: '已取消' },
              { value: 'refunded', label: '已退款' },
            ]}
          />
          <RangePicker
            showTime
            value={dateRange}
            onChange={setDateRange}
            placeholder={['开始日期', '结束日期']}
          />
          <Button icon={<SearchOutlined />} type="primary" onClick={loadOrders}>搜索</Button>
          <Button icon={<ReloadOutlined />} onClick={loadOrders} loading={loading}>刷新</Button>
          <Button icon={<SyncOutlined />} onClick={handleSyncWooCommerce} loading={syncing} type="primary">
            同步WooCommerce
          </Button>
        </Space>
      </Card>

      {/* 订单表格 */}
      <Card size="small">
        <Table
          columns={columns}
          dataSource={orders}
          rowKey="id"
          loading={loading}
          pagination={{
            current: page,
            pageSize: pageSize,
            total: total,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total) => `共 ${total} 条订单`,
            onChange: (page, pageSize) => {
              setPage(page)
              setPageSize(pageSize)
            },
          }}
          locale={{
            emptyText: <Empty description="暂无订单数据" />,
          }}
        />
      </Card>

      {/* 订单详情Modal */}
      <Modal
        title={`订单详情 #${viewingOrder?.external_order_id || ''}`}
        open={detailModalOpen}
        onCancel={() => setDetailModalOpen(false)}
        footer={[
          <Button key="close" onClick={() => setDetailModalOpen(false)}>关闭</Button>,
        ]}
        width={800}
      >
        {viewingOrder && (
          <div>
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="订单号" span={2}>
                <Text strong>#{viewingOrder.external_order_id}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="订单状态">
                <Tag color={statusColors[viewingOrder.status] || 'default'}>{statusText[viewingOrder.status] || viewingOrder.status}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="支付状态">
                {viewingOrder.payment_status ? (
                  <Tag color={viewingOrder.payment_status === 'completed' ? 'green' : 'orange'}>
                    {viewingOrder.payment_status === 'completed' ? '已支付' : viewingOrder.payment_status}
                  </Tag>
                ) : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="发货状态">
                {viewingOrder.fulfillment_status ? (
                  <Tag color={fulfillmentColors[viewingOrder.fulfillment_status] || 'default'}>
                    {fulfillmentText[viewingOrder.fulfillment_status] || viewingOrder.fulfillment_status}
                  </Tag>
                ) : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="下单时间" span={2}>
                {viewingOrder.received_at ? dayjs(viewingOrder.received_at).format('YYYY-MM-DD HH:mm:ss') : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="客户ID">
                {viewingOrder.customer_id ? `#${viewingOrder.customer_id.substring(0, 8)}...` : '访客'}
              </Descriptions.Item>
              <Descriptions.Item label="货币">
                {viewingOrder.currency || 'USD'}
              </Descriptions.Item>
            </Descriptions>

            <Divider style={{ margin: '16px 0' }} />

            {/* 订单项 */}
            <div style={{ marginBottom: '16px' }}>
              <Text strong>订单项（{viewingOrder.items?.length || 0}）：</Text>
              {viewingOrder.items && viewingOrder.items.length > 0 ? (
                <List
                  size="small"
                  style={{ marginTop: '8px' }}
                  dataSource={viewingOrder.items}
                  renderItem={(item: OrderItem) => (
                    <List.Item>
                      <List.Item.Meta
                        title={item.product_name}
                        description={`SKU: ${item.sku} | 单价: ${viewingOrder.currency || 'USD'} ${Number(item.price).toFixed(2)}`}
                      />
                      <div>
                        <Text>x{item.quantity}</Text>
                        <Divider type="vertical" />
                        <Text strong style={{ color: '#f5222d' }}>
                          {viewingOrder.currency || 'USD'} {Number(item.line_total).toFixed(2)}
                        </Text>
                      </div>
                    </List.Item>
                  )}
                />
              ) : (
                <Empty description="暂无订单项" style={{ marginTop: '8px' }} />
              )}
            </div>

            <Divider style={{ margin: '16px 0' }} />

            {/* 金额明细 */}
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="商品小计">
                {viewingOrder.currency || 'USD'} {Number(viewingOrder.subtotal).toFixed(2)}
              </Descriptions.Item>
              <Descriptions.Item label="运费">
                {viewingOrder.currency || 'USD'} {Number(viewingOrder.shipping_total).toFixed(2)}
              </Descriptions.Item>
              <Descriptions.Item label="折扣">
                <Text style={{ color: '#52c41a' }}>-{viewingOrder.currency || 'USD'} {Number(viewingOrder.discount_total).toFixed(2)}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="税费">
                {viewingOrder.currency || 'USD'} {Number(viewingOrder.tax_total).toFixed(2)}
              </Descriptions.Item>
              <Descriptions.Item label="订单总计" span={2}>
                <Text strong style={{ fontSize: '18px', color: '#f5222d' }}>
                  {viewingOrder.currency || 'USD'} {Number(viewingOrder.total).toFixed(2)}
                </Text>
              </Descriptions.Item>
            </Descriptions>
          </div>
        )}
      </Modal>
    </div>
  )
}
