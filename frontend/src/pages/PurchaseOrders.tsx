import { useState, useEffect } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Input, Select,
  Statistic, Row, Col, Spin, message, Modal, Descriptions, DatePicker,
  Empty, Tabs
} from 'antd'
import {
  ShoppingCartOutlined, DollarOutlined, CheckCircleOutlined,
  TruckOutlined, ClockCircleOutlined, SearchOutlined, ReloadOutlined,
  EyeOutlined, PlusOutlined
} from '@ant-design/icons'
import dayjs from 'dayjs'

const { Title, Text } = Typography
const { RangePicker } = DatePicker

interface PurchaseOrder {
  id: string
  po_number: string
  supplier_id: string | null
  supplier_name: string
  status: string
  currency: string
  subtotal: number
  shipping_cost: number
  total: number
  expected_delivery_at: string | null
  received_at: string | null
  notes: string | null
  created_at: string
}

const statusColors: Record<string, string> = {
  pending: 'default',
  ordered: 'blue',
  shipped: 'cyan',
  received: 'green',
  completed: 'green',
  cancelled: 'red',
}

const statusText: Record<string, string> = {
  pending: '待下单',
  ordered: '已下单',
  shipped: '运输中',
  received: '已收货',
  completed: '已完成',
  cancelled: '已取消',
}

export default function PurchaseOrdersPage() {
  const [loading, setLoading] = useState(false)
  const [orders, setOrders] = useState<PurchaseOrder[]>([])
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [createForm, setCreateForm] = useState({
    supplier_id: '',
    subtotal: '',
    shipping_cost: '',
    expected_delivery_at: '',
    notes: '',
  })
  const [viewingOrder, setViewingOrder] = useState<PurchaseOrder | null>(null)
  const [statusFilter, setStatusFilter] = useState('all')
  const [searchText, setSearchText] = useState('')
  const [stats, setStats] = useState({
    total_orders: 0,
    total_amount: 0,
    received: 0,
    shipped: 0,
    ordered: 0,
  })

  const handleCreateOrder = async () => {
    try {
      setCreating(true)
      const subtotal = parseFloat(createForm.subtotal) || 0
      const shipping_cost = parseFloat(createForm.shipping_cost) || 0
      
      const resp = await fetch('/api/v1/supply-chain/purchase-orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          supplier_id: createForm.supplier_id || null,
          subtotal,
          shipping_cost,
          total: subtotal + shipping_cost,
          expected_delivery_at: createForm.expected_delivery_at || null,
          notes: createForm.notes,
          status: 'ordered',
        }),
      })
      
      if (resp.ok) {
        message.success('采购订单创建成功')
        setCreateModalOpen(false)
        setCreateForm({ supplier_id: '', subtotal: '', shipping_cost: '', expected_delivery_at: '', notes: '' })
        loadOrders()
      } else {
        const err = await resp.json().catch(() => ({}))
        message.error(`创建失败: ${err.detail || resp.statusText}`)
      }
    } catch (e: any) {
      message.error(`创建失败: ${e.message}`)
    } finally {
      setCreating(false)
    }
  }

  const handleUpdateStatus = async (order: PurchaseOrder, newStatus: string) => {
    try {
      const resp = await fetch(`/api/v1/supply-chain/purchase-orders/${order.id}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      })
      
      if (resp.ok) {
        message.success(`状态已更新为: ${statusText[newStatus] || newStatus}`)
        loadOrders()
      } else {
        const err = await resp.json().catch(() => ({}))
        message.error(`更新失败: ${err.detail || resp.statusText}`)
      }
    } catch (e: any) {
      message.error(`更新失败: ${e.message}`)
    }
  }

  const loadOrders = async () => {
    try {
      setLoading(true)
      // 从API获取采购订单（如果API存在）
      const resp = await fetch('/api/v1/supply-chain/purchase-orders')
      if (resp.ok) {
        const data = await resp.json()
        setOrders(data)
      } else {
        // API不存在时使用空数据
        setOrders([])
        message.info('采购订单API暂未实现，显示示例数据')
      }
      
      // 获取统计数据
      const statsResp = await fetch('/api/v1/supply-chain/purchase-orders/stats')
      if (statsResp.ok) {
        const statsData = await statsResp.json()
        setStats({
          total_orders: statsData.total_orders || 0,
          total_amount: statsData.total_amount || 0,
          received: 0,
          shipped: 0,
          ordered: 0,
        })
      }
    } catch (e: any) {
      console.error('Load purchase orders error:', e)
      setOrders([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadOrders()
  }, [])

  const filteredOrders = orders.filter(order => {
    const matchStatus = statusFilter === 'all' || order.status === statusFilter
    const matchSearch = !searchText || 
      order.po_number.toLowerCase().includes(searchText.toLowerCase()) ||
      order.supplier_name.toLowerCase().includes(searchText.toLowerCase())
    return matchStatus && matchSearch
  })

  const columns = [
    {
      title: '订单号',
      dataIndex: 'po_number',
      key: 'po_number',
      width: 180,
      render: (text: string) => <Text strong>{text}</Text>,
    },
    {
      title: '供应商',
      dataIndex: 'supplier_name',
      key: 'supplier_name',
      width: 200,
      ellipsis: true,
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
      title: '金额',
      dataIndex: 'total',
      key: 'total',
      width: 120,
      render: (total: number, record: PurchaseOrder) => (
        <Text strong>{record.currency} {total.toLocaleString()}</Text>
      ),
    },
    {
      title: '预计交货',
      dataIndex: 'expected_delivery_at',
      key: 'expected_delivery_at',
      width: 120,
      render: (date: string | null) => date ? dayjs(date).format('YYYY-MM-DD') : '-',
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 120,
      render: (date: string) => dayjs(date).format('YYYY-MM-DD'),
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_: any, record: PurchaseOrder) => (
        <Button type="link" icon={<EyeOutlined />} onClick={() => {
          setViewingOrder(record)
          setDetailModalOpen(true)
        }}>
          详情
        </Button>
      ),
    },
  ]

  return (
    <div style={{ padding: '24px' }}>
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <Title level={3} style={{ margin: 0 }}>
            <ShoppingCartOutlined style={{ marginRight: '8px', color: '#1890ff' }} />
            采购订单管理
          </Title>
          <Text type="secondary">采购订单列表、跟踪与对账</Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadOrders}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalOpen(true)}>新建采购单</Button>
        </Space>
      </div>

      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: '24px' }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="采购订单总数"
              value={stats.total_orders}
              prefix={<ShoppingCartOutlined style={{ color: '#1890ff' }} />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="采购总金额"
              value={stats.total_amount}
              precision={2}
              prefix={<DollarOutlined style={{ color: '#52c41a' }} />}
              suffix="CNY"
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="已收货"
              value={stats.received}
              prefix={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="运输中"
              value={stats.shipped}
              prefix={<TruckOutlined style={{ color: '#13c2c2' }} />}
            />
          </Card>
        </Col>
      </Row>

      {/* 筛选栏 */}
      <Card style={{ marginBottom: '16px' }}>
        <Space wrap>
          <Input
            placeholder="搜索订单号/供应商"
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ width: 240 }}
            allowClear
          />
          <Select
            value={statusFilter}
            onChange={setStatusFilter}
            style={{ width: 140 }}
            options={[
              { value: 'all', label: '全部状态' },
              { value: 'pending', label: '待下单' },
              { value: 'ordered', label: '已下单' },
              { value: 'shipped', label: '运输中' },
              { value: 'received', label: '已收货' },
              { value: 'completed', label: '已完成' },
              { value: 'cancelled', label: '已取消' },
            ]}
          />
          <RangePicker placeholder={['开始日期', '结束日期']} />
        </Space>
      </Card>

      {/* 订单列表 */}
      <Card>
        <Spin spinning={loading}>
          <Table
            columns={columns}
            dataSource={filteredOrders}
            rowKey="id"
            pagination={{
              pageSize: 20,
              showSizeChanger: true,
              showTotal: (total) => `共 ${total} 条订单`,
            }}
            locale={{
              emptyText: <Empty description="暂无采购订单，点击"新建采购单"创建" />,
            }}
          />
        </Spin>
      </Card>

      {/* 订单详情弹窗 */}
      <Modal
        title="采购订单详情"
        open={detailModalOpen}
        onCancel={() => setDetailModalOpen(false)}
        footer={[
          <Button key="close" onClick={() => setDetailModalOpen(false)}>关闭</Button>,
        ]}
        width={700}
      >
        {viewingOrder && (
          <div>
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="订单号" span={2}>
                <Text strong>{viewingOrder.po_number}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="供应商">{viewingOrder.supplier_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={statusColors[viewingOrder.status] || 'default'}>
                  {statusText[viewingOrder.status] || viewingOrder.status}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="货币">{viewingOrder.currency}</Descriptions.Item>
              <Descriptions.Item label="小计">{viewingOrder.subtotal.toLocaleString()}</Descriptions.Item>
              <Descriptions.Item label="运费">{viewingOrder.shipping_cost.toLocaleString()}</Descriptions.Item>
              <Descriptions.Item label="总金额">
                <Text strong style={{ color: '#f5222d' }}>{viewingOrder.total.toLocaleString()}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="预计交货">
                {viewingOrder.expected_delivery_at ? dayjs(viewingOrder.expected_delivery_at).format('YYYY-MM-DD') : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="实际收货">
                {viewingOrder.received_at ? dayjs(viewingOrder.received_at).format('YYYY-MM-DD') : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="创建时间" span={2}>
                {dayjs(viewingOrder.created_at).format('YYYY-MM-DD HH:mm:ss')}
              </Descriptions.Item>
              {viewingOrder.notes && (
                <Descriptions.Item label="备注" span={2}>{viewingOrder.notes}</Descriptions.Item>
              )}
            </Descriptions>
          </div>
        )}
      </Modal>
    </div>

      {/* 新建采购单弹窗 */}
      <Modal
        title="新建采购订单"
        open={createModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setCreateModalOpen(false)}>取消</Button>,
          <Button key="submit" type="primary" loading={creating} onClick={handleCreateOrder}>创建</Button>,
        ]}
        width={600}
      >
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="供应商" span={2}>
            <Select
              style={{ width: '100%' }}
              placeholder="选择供应商"
              value={createForm.supplier_id || undefined}
              onChange={(value) => setCreateForm({ ...createForm, supplier_id: value })}
              options={[
                { value: '0deef793-744b-4fdc-8c5f-70f8dcc8a75b', label: '义乌市浩宇户外用品有限公司' },
                { value: 'ffa86a22-d3f0-4e2c-be20-6bd26aedf2d0', label: '深圳市腾飞露营装备厂' },
                { value: 'a72966e5-8555-4dee-b76d-dc70974848a4', label: '宁波市明亮照明电器有限公司' },
                { value: '73102aab-01c2-4865-8357-1c906d1f78a7', label: '南通市暖睡家纺制品厂' },
                { value: 'b3539998-badd-4258-8a2f-5b614a1d53cf', label: '永康市野营炊具制造有限公司' },
              ]}
            />
          </Descriptions.Item>
          <Descriptions.Item label="商品金额">
            <Input
              type="number"
              prefix="¥"
              placeholder="0.00"
              value={createForm.subtotal}
              onChange={(e) => setCreateForm({ ...createForm, subtotal: e.target.value })}
            />
          </Descriptions.Item>
          <Descriptions.Item label="运费">
            <Input
              type="number"
              prefix="¥"
              placeholder="0.00"
              value={createForm.shipping_cost}
              onChange={(e) => setCreateForm({ ...createForm, shipping_cost: e.target.value })}
            />
          </Descriptions.Item>
          <Descriptions.Item label="预计交货日期" span={2}>
            <Input
              type="date"
              value={createForm.expected_delivery_at}
              onChange={(e) => setCreateForm({ ...createForm, expected_delivery_at: e.target.value })}
            />
          </Descriptions.Item>
          <Descriptions.Item label="备注" span={2}>
            <Input.TextArea
              rows={3}
              placeholder="采购备注..."
              value={createForm.notes}
              onChange={(e) => setCreateForm({ ...createForm, notes: e.target.value })}
            />
          </Descriptions.Item>
        </Descriptions>
      </Modal>
  </div>
  )
}
