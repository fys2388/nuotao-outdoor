import { useEffect, useState } from 'react'
import {
  Table, Tag, Button, Space, Modal, Form, Input, Select, Spin, Alert,
  Row, Col, Card, Statistic, Typography, Popconfirm, message, Tabs,
  Descriptions, List, Badge, Tooltip, Empty
} from 'antd'
import {
  ShoppingCartOutlined, CheckCircleOutlined, TruckOutlined,
  DollarOutlined, LinkOutlined, EditOutlined, StopOutlined,
  ReloadOutlined, EyeOutlined, ExportOutlined
} from '@ant-design/icons'

const { Title, Text, Paragraph } = Typography

// 采购单状态配置（一件代发模式）
const STATUS_CONFIG: Record<string, { color: string; label: string; icon: any }> = {
  pending: { color: 'orange', label: '待确认', icon: <ShoppingCartOutlined /> },
  confirmed: { color: 'blue', label: '已确认', icon: <CheckCircleOutlined /> },
  ordered: { color: 'purple', label: '已下单', icon: <DollarOutlined /> },
  shipped: { color: 'cyan', label: '国内已发货', icon: <TruckOutlined /> },
  international_shipped: { color: 'geekblue', label: '国际已发货', icon: <ExportOutlined /> },
  completed: { color: 'green', label: '已完成', icon: <CheckCircleOutlined /> },
  cancelled: { color: 'default', label: '已取消', icon: <StopOutlined /> },
}

interface PurchaseOrder {
  purchase_order_id: string
  wc_order_id: number
  wc_order_number: string
  status: string
  created_at: string
  updated_at: string
  total_cost: number
  total_quantity: number
  items: Array<{
    woo_product_id: number
    woo_name: string
    quantity: number
    unit_cost: number
    ali1688_product_id: string
    ali1688_url: string
    ali1688_supplier: string
  }>
  unmapped_items: Array<any>
  customer: {
    name: string
    email: string
    country: string
  }
  ali1688_order_id: string
  ali1688_order_url: string
  tracking_number: string  // 国内采购物流号
  tracking_carrier: string
  tracking_url: string
  international_tracking_number: string  // 国际发货物流号（回传WC）
  international_tracking_carrier: string
  international_tracking_url: string
  notes: string
}

export default function ProcurementWorkbench() {
  const [loading, setLoading] = useState(true)
  const [orders, setOrders] = useState<PurchaseOrder[]>([])
  const [stats, setStats] = useState<any>(null)
  const [activeStatus, setActiveStatus] = useState<string>('all')
  const [detailModal, setDetailModal] = useState(false)
  const [currentOrder, setCurrentOrder] = useState<PurchaseOrder | null>(null)
  const [orderModal, setOrderModal] = useState(false)
  const [trackingModal, setTrackingModal] = useState(false)
  const [internationalTrackingModal, setInternationalTrackingModal] = useState(false)
  const [form] = Form.useForm()
  const [trackingForm] = Form.useForm()
  const [internationalTrackingForm] = Form.useForm()

  // 获取统计数据
  const fetchStats = async () => {
    try {
      const resp = await fetch('/api/v1/procurement/stats')
      const data = await resp.json()
      if (data.success) {
        setStats(data.data)
      }
    } catch (e) {
      console.error('Fetch stats failed:', e)
    }
  }

  // 获取采购单列表
  const fetchOrders = async (status?: string) => {
    try {
      setLoading(true)
      const url = status && status !== 'all'
        ? `/api/v1/procurement/orders?status=${status}&limit=100`
        : '/api/v1/procurement/orders?limit=100'
      const resp = await fetch(url)
      const data = await resp.json()
      if (data.success) {
        setOrders(data.data.orders || [])
      }
    } catch (e) {
      message.error('加载采购单失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchStats()
    fetchOrders()
  }, [])

  const handleStatusChange = (status: string) => {
    setActiveStatus(status)
    fetchOrders(status)
  }

  const handleRefresh = () => {
    fetchStats()
    fetchOrders(activeStatus)
    message.success('已刷新')
  }

  // 确认采购单
  const handleConfirm = async (poId: string) => {
    try {
      const resp = await fetch(`/api/v1/procurement/orders/${poId}/confirm`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notes: '代采工作台确认' }),
      })
      const data = await resp.json()
      if (data.success) {
        message.success('采购单已确认')
        fetchStats()
        fetchOrders(activeStatus)
        if (currentOrder?.purchase_order_id === poId) {
          setCurrentOrder(data.data)
        }
      } else {
        message.error(data.error || '确认失败')
      }
    } catch (e) {
      message.error('确认失败')
    }
  }

  // 标记已下单
  const handleMarkOrdered = async (values: any) => {
    if (!currentOrder) return
    try {
      const resp = await fetch(`/api/v1/procurement/orders/${currentOrder.purchase_order_id}/order`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      })
      const data = await resp.json()
      if (data.success) {
        message.success('已标记下单，1688订单号已回填')
        setOrderModal(false)
        form.resetFields()
        fetchStats()
        fetchOrders(activeStatus)
        setCurrentOrder(data.data)
      } else {
        message.error(data.error || '操作失败')
      }
    } catch (e) {
      message.error('操作失败')
    }
  }

  // 添加国内采购物流单号（不回传WC）
  const handleAddTracking = async (values: any) => {
    if (!currentOrder) return
    try {
      const resp = await fetch(`/api/v1/procurement/orders/${currentOrder.purchase_order_id}/tracking`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      })
      const data = await resp.json()
      if (data.success) {
        message.success('国内采购物流单号已添加')
        setTrackingModal(false)
        trackingForm.resetFields()
        fetchStats()
        fetchOrders(activeStatus)
        setCurrentOrder(data.data)
      } else {
        message.error(data.error || '操作失败')
      }
    } catch (e) {
      message.error('操作失败')
    }
  }

  // 添加国际发货物流单号（回传WC）
  const handleAddInternationalTracking = async (values: any) => {
    if (!currentOrder) return
    try {
      const resp = await fetch(`/api/v1/procurement/orders/${currentOrder.purchase_order_id}/international-tracking`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      })
      const data = await resp.json()
      if (data.success) {
        message.success('国际物流单号已添加，已回传WooCommerce')
        setInternationalTrackingModal(false)
        internationalTrackingForm.resetFields()
        fetchStats()
        fetchOrders(activeStatus)
        setCurrentOrder(data.data)
      } else {
        message.error(data.error || '操作失败')
      }
    } catch (e) {
      message.error('操作失败')
    }
  }

  // 完成采购单
  const handleComplete = async (poId: string) => {
    try {
      const resp = await fetch(`/api/v1/procurement/orders/${poId}/complete`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notes: '代采工作台完成' }),
      })
      const data = await resp.json()
      if (data.success) {
        message.success('采购单已完成')
        fetchStats()
        fetchOrders(activeStatus)
        if (currentOrder?.purchase_order_id === poId) {
          setCurrentOrder(data.data)
        }
      } else {
        message.error(data.error || '操作失败')
      }
    } catch (e) {
      message.error('操作失败')
    }
  }

  // 取消采购单
  const handleCancel = async (poId: string) => {
    try {
      const resp = await fetch(`/api/v1/procurement/orders/${poId}/cancel`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: '代采工作台取消' }),
      })
      const data = await resp.json()
      if (data.success) {
        message.success('采购单已取消')
        fetchStats()
        fetchOrders(activeStatus)
        if (currentOrder?.purchase_order_id === poId) {
          setCurrentOrder(data.data)
        }
      } else {
        message.error(data.error || '操作失败')
      }
    } catch (e) {
      message.error('操作失败')
    }
  }

  // 一键打开1688商品页
  const handleOpen1688 = (item: any) => {
    if (item.ali1688_url) {
      window.open(item.ali1688_url, '_blank')
    } else {
      message.warning('该商品未映射1688链接')
    }
  }

  // 打开详情
  const handleViewDetail = (order: PurchaseOrder) => {
    setCurrentOrder(order)
    setDetailModal(true)
  }

  // 表格列定义
  const columns = [
    {
      title: '采购单号',
      dataIndex: 'purchase_order_id',
      key: 'purchase_order_id',
      width: 180,
      render: (v: string) => <Text strong>{v}</Text>,
    },
    {
      title: 'WC订单',
      dataIndex: 'wc_order_number',
      key: 'wc_order_number',
      width: 100,
      render: (v: string, record: PurchaseOrder) => (
        <a href={`https://nuotaooutdoor.com/wp-admin/post.php?post=${record.wc_order_id}&action=edit`} target="_blank" rel="noreferrer">
          #{v}
        </a>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (v: string) => {
        const cfg = STATUS_CONFIG[v] || STATUS_CONFIG.pending
        return <Tag color={cfg.color} icon={cfg.icon}>{cfg.label}</Tag>
      },
    },
    {
      title: '商品数',
      dataIndex: 'total_quantity',
      key: 'total_quantity',
      width: 80,
    },
    {
      title: '成本',
      dataIndex: 'total_cost',
      key: 'total_cost',
      width: 100,
      render: (v: number) => <Text type="danger">¥{v?.toFixed(2) || '0.00'}</Text>,
    },
    {
      title: '客户',
      dataIndex: ['customer', 'name'],
      key: 'customer',
      width: 120,
      ellipsis: true,
    },
    {
      title: '1688订单号',
      dataIndex: 'ali1688_order_id',
      key: 'ali1688_order_id',
      width: 150,
      render: (v: string, record: PurchaseOrder) => v ? (
        record.ali1688_order_url ? (
          <a href={record.ali1688_order_url} target="_blank" rel="noreferrer">{v}</a>
        ) : v
      ) : <Text type="secondary">-</Text>,
    },
    {
      title: '国内物流',
      dataIndex: 'tracking_number',
      key: 'tracking_number',
      width: 140,
      render: (v: string, record: PurchaseOrder) => v ? (
        record.tracking_url ? (
          <a href={record.tracking_url} target="_blank" rel="noreferrer">{v}</a>
        ) : v
      ) : <Text type="secondary">-</Text>,
    },
    {
      title: '国际物流',
      dataIndex: 'international_tracking_number',
      key: 'international_tracking_number',
      width: 140,
      render: (v: string, record: PurchaseOrder) => v ? (
        record.international_tracking_url ? (
          <a href={record.international_tracking_url} target="_blank" rel="noreferrer">{v}</a>
        ) : v
      ) : <Text type="secondary">-</Text>,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 280,
      fixed: 'right' as const,
      render: (_: any, record: PurchaseOrder) => (
        <Space size="small" wrap>
          <Button size="small" icon={<EyeOutlined />} onClick={() => handleViewDetail(record)}>
            详情
          </Button>
          {record.status === 'pending' && (
            <Button size="small" type="primary" onClick={() => handleConfirm(record.purchase_order_id)}>
              确认
            </Button>
          )}
          {record.status === 'confirmed' && (
            <>
              <Button size="small" type="primary" icon={<LinkOutlined />} onClick={() => {
                setCurrentOrder(record)
                setOrderModal(true)
              }}>
                标记下单
              </Button>
              {record.items?.filter((i: any) => i.ali1688_url).map((item: any, idx: number) => (
                <Tooltip key={idx} title={`打开1688: ${item.woo_name}`}>
                  <Button size="small" icon={<ExportOutlined />} onClick={() => handleOpen1688(item)}>
                    1688
                  </Button>
                </Tooltip>
              ))}
            </>
          )}
          {record.status === 'ordered' && (
            <Button size="small" type="primary" icon={<TruckOutlined />} onClick={() => {
              setCurrentOrder(record)
              setTrackingModal(true)
            }}>
              国内物流
            </Button>
          )}
          {record.status === 'shipped' && (
            <Button size="small" type="primary" icon={<ExportOutlined />} onClick={() => {
              setCurrentOrder(record)
              setInternationalTrackingModal(true)
            }}>
              国际发货
            </Button>
          )}
          {['international_shipped'].includes(record.status) && (
            <Button size="small" type="primary" onClick={() => handleComplete(record.purchase_order_id)}>
              完成
            </Button>
          )}
          {['pending', 'confirmed', 'ordered'].includes(record.status) && (
            <Popconfirm title="确定取消此采购单？" onConfirm={() => handleCancel(record.purchase_order_id)}>
              <Button size="small" danger>取消</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  // 统计卡片
  const statCards = [
    { title: '待确认', value: stats?.by_status?.pending || 0, color: '#faad14', icon: <ShoppingCartOutlined />, status: 'pending' },
    { title: '已确认', value: stats?.by_status?.confirmed || 0, color: '#1890ff', icon: <CheckCircleOutlined />, status: 'confirmed' },
    { title: '已下单', value: stats?.by_status?.ordered || 0, color: '#722ed1', icon: <DollarOutlined />, status: 'ordered' },
    { title: '国内已发', value: stats?.by_status?.shipped || 0, color: '#13c2c2', icon: <TruckOutlined />, status: 'shipped' },
    { title: '国际已发', value: stats?.by_status?.international_shipped || 0, color: '#2f54eb', icon: <ExportOutlined />, status: 'international_shipped' },
    { title: '已完成', value: stats?.by_status?.completed || 0, color: '#52c41a', icon: <CheckCircleOutlined />, status: 'completed' },
  ]

  return (
    <div style={{ padding: '24px', maxWidth: '1600px', margin: '0 auto' }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <ShoppingCartOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>代采工作台（一件代发）</Title>
            <Text type="secondary">确认 → 1688下单 → 国内物流（供应商→货代）→ 国际发货（货代→客户，回传WC）→ 完成</Text>
          </div>
        </Space>
        <Button icon={<ReloadOutlined />} onClick={handleRefresh}>刷新</Button>
      </div>

      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: '24px' }}>
        {statCards.map((stat, idx) => (
          <Col xs={12} sm={8} md={4} key={idx}>
            <Card
              size="small"
              hoverable
              onClick={() => handleStatusChange(stat.status)}
              style={{ borderLeft: `3px solid ${stat.color}`, cursor: 'pointer' }}
            >
              <Statistic
                title={stat.title}
                value={stat.value}
                valueStyle={{ color: stat.color, fontSize: '24px' }}
                prefix={stat.icon}
              />
            </Card>
          </Col>
        ))}
        <Col xs={12} sm={8} md={4}>
          <Card size="small" style={{ borderLeft: '3px solid #d9d9d9' }}>
            <Statistic
              title="总成本"
              value={stats?.total_cost || 0}
              precision={2}
              prefix="¥"
              valueStyle={{ fontSize: '20px' }}
            />
          </Card>
        </Col>
      </Row>

      {/* 状态筛选标签 */}
      <Card size="small" style={{ marginBottom: '16px' }}>
        <Space wrap>
          <Button
            type={activeStatus === 'all' ? 'primary' : 'default'}
            onClick={() => handleStatusChange('all')}
          >
            全部 ({stats?.total || 0})
          </Button>
          {statCards.map((stat, idx) => (
            <Button
              key={idx}
              type={activeStatus === stat.status ? 'primary' : 'default'}
              onClick={() => handleStatusChange(stat.status)}
            >
              {stat.title} ({stat.value})
            </Button>
          ))}
        </Space>
      </Card>

      {/* 采购单列表 */}
      <Card>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '60px 0' }}>
            <Spin size="large" tip="加载采购单..." />
          </div>
        ) : orders.length === 0 ? (
          <Empty
            description={
              <div>
                <Paragraph>暂无采购单数据</Paragraph>
                <Text type="secondary">WooCommerce出单后会自动生成采购单</Text>
              </div>
            }
          />
        ) : (
          <Table
            columns={columns}
            dataSource={orders}
            rowKey="purchase_order_id"
            pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }}
            scroll={{ x: 1400 }}
            size="middle"
          />
        )}
      </Card>

      {/* 采购单详情弹窗 */}
      <Modal
        title={`采购单详情 - ${currentOrder?.purchase_order_id || ''}`}
        open={detailModal}
        onCancel={() => setDetailModal(false)}
        width={900}
        footer={[
          <Button key="close" onClick={() => setDetailModal(false)}>关闭</Button>,
        ]}
      >
        {currentOrder && (
          <div>
            <Descriptions bordered size="small" column={3} style={{ marginBottom: '16px' }}>
              <Descriptions.Item label="采购单号">{currentOrder.purchase_order_id}</Descriptions.Item>
              <Descriptions.Item label="WC订单">
                <a href={`https://nuotaooutdoor.com/wp-admin/post.php?post=${currentOrder.wc_order_id}&action=edit`} target="_blank" rel="noreferrer">
                  #{currentOrder.wc_order_number}
                </a>
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={STATUS_CONFIG[currentOrder.status]?.color}>
                  {STATUS_CONFIG[currentOrder.status]?.label}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="总成本">¥{currentOrder.total_cost?.toFixed(2)}</Descriptions.Item>
              <Descriptions.Item label="总数量">{currentOrder.total_quantity}</Descriptions.Item>
              <Descriptions.Item label="客户">{currentOrder.customer?.name} ({currentOrder.customer?.country})</Descriptions.Item>
              <Descriptions.Item label="1688订单号" span={2}>
                {currentOrder.ali1688_order_id ? (
                  currentOrder.ali1688_order_url ? (
                    <a href={currentOrder.ali1688_order_url} target="_blank" rel="noreferrer">
                      {currentOrder.ali1688_order_id}
                    </a>
                  ) : currentOrder.ali1688_order_id
                ) : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="国内物流">
                {currentOrder.tracking_number ? (
                  currentOrder.tracking_url ? (
                    <a href={currentOrder.tracking_url} target="_blank" rel="noreferrer">
                      {currentOrder.tracking_number}
                    </a>
                  ) : currentOrder.tracking_number
                ) : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="国际物流" span={2}>
                {currentOrder.international_tracking_number ? (
                  currentOrder.international_tracking_url ? (
                    <a href={currentOrder.international_tracking_url} target="_blank" rel="noreferrer">
                      {currentOrder.international_tracking_number}
                    </a>
                  ) : currentOrder.international_tracking_number
                ) : '-'}
              </Descriptions.Item>
            </Descriptions>

            <Title level={5}>商品明细</Title>
            <List
              size="small"
              bordered
              dataSource={currentOrder.items || []}
              renderItem={(item: any, idx: number) => (
                <List.Item
                  actions={[
                    item.ali1688_url && (
                      <Button
                        key="open"
                        size="small"
                        type="link"
                        icon={<ExportOutlined />}
                        onClick={() => handleOpen1688(item)}
                      >
                        打开1688
                      </Button>
                    ),
                  ]}
                >
                  <List.Item.Meta
                    title={`${idx + 1}. ${item.woo_name}`}
                    description={
                      <Space size="large">
                        <span>数量: <strong>{item.quantity}</strong></span>
                        <span>单价: ¥{item.unit_cost?.toFixed(2)}</span>
                        <span>小计: ¥{(item.unit_cost * item.quantity)?.toFixed(2)}</span>
                        <span>供应商: {item.ali1688_supplier || '-'}</span>
                        {item.ali1688_product_id && <span type="secondary">1688ID: {item.ali1688_product_id}</span>}
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />

            {currentOrder.unmapped_items?.length > 0 && (
              <Alert
                type="warning"
                message={`有 ${currentOrder.unmapped_items.length} 个商品未映射1688`}
                description={currentOrder.unmapped_items.map((i: any, idx: number) => (
                  <div key={idx}>{i.woo_name} (数量: {i.quantity}) - {i.reason}</div>
                ))}
                style={{ marginTop: '16px' }}
              />
            )}
          </div>
        )}
      </Modal>

      {/* 标记已下单弹窗 */}
      <Modal
        title="标记已下单 - 回填1688订单号"
        open={orderModal}
        onCancel={() => setOrderModal(false)}
        onOk={() => form.submit()}
        okText="确认下单"
      >
        <Alert
          type="info"
          message="请先在1688完成下单，然后回填订单信息"
          style={{ marginBottom: '16px' }}
        />
        {currentOrder?.items?.filter((i: any) => i.ali1688_url).map((item: any, idx: number) => (
          <Button
            key={idx}
            type="link"
            icon={<ExportOutlined />}
            onClick={() => handleOpen1688(item)}
            style={{ display: 'block', textAlign: 'left', padding: '4px 0' }}
          >
            打开1688商品页: {item.woo_name}
          </Button>
        ))}
        <Form form={form} layout="vertical" style={{ marginTop: '16px' }}>
          <Form.Item name="ali1688_order_id" label="1688订单号" rules={[{ required: true, message: '请输入1688订单号' }]}>
            <Input placeholder="请输入1688订单号" />
          </Form.Item>
          <Form.Item name="ali1688_order_url" label="1688订单链接">
            <Input placeholder="https://trade.1688.com/order/..." />
          </Form.Item>
          <Form.Item name="notes" label="备注">
            <Input.TextArea rows={2} placeholder="可选备注" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 添加国内采购物流单号弹窗 */}
      <Modal
        title="添加国内采购物流单号"
        open={trackingModal}
        onCancel={() => setTrackingModal(false)}
        onOk={() => trackingForm.submit()}
        okText="确认添加"
      >
        <Alert
          type="info"
          message="这是1688供应商→货代/集运仓的国内物流单号，不会回传WooCommerce订单"
          style={{ marginBottom: '16px' }}
        />
        <Form form={trackingForm} layout="vertical">
          <Form.Item name="tracking_number" label="国内物流单号" rules={[{ required: true, message: '请输入国内物流单号' }]}>
            <Input placeholder="请输入国内物流单号（韵达/中通/圆通等）" />
          </Form.Item>
          <Form.Item name="carrier" label="国内快递公司">
            <Select
              placeholder="请选择国内快递公司"
              allowClear
              options={[
                { value: '韵达快递', label: '韵达快递' },
                { value: '中通快递', label: '中通快递' },
                { value: '圆通快递', label: '圆通快递' },
                { value: '申通快递', label: '申通快递' },
                { value: '顺丰速运', label: '顺丰速运' },
                { value: '邮政EMS', label: '邮政EMS' },
                { value: '极兔速递', label: '极兔速递' },
                { value: '其他', label: '其他' },
              ]}
            />
          </Form.Item>
          <Form.Item name="tracking_url" label="国内物流查询链接">
            <Input placeholder="https://..." />
          </Form.Item>
          <Form.Item name="notes" label="备注">
            <Input.TextArea rows={2} placeholder="可选备注" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 添加国际发货物流单号弹窗 */}
      <Modal
        title="添加国际发货物流单号"
        open={internationalTrackingModal}
        onCancel={() => setInternationalTrackingModal(false)}
        onOk={() => internationalTrackingForm.submit()}
        okText="确认发货"
      >
        <Alert
          type="warning"
          message="这是货代/集运仓→海外客户的国际专线单号，添加后会自动回传WooCommerce订单"
          style={{ marginBottom: '16px' }}
        />
        <Form form={internationalTrackingForm} layout="vertical">
          <Form.Item name="tracking_number" label="国际物流单号" rules={[{ required: true, message: '请输入国际物流单号' }]}>
            <Input placeholder="请输入国际专线单号（4PX/燕文/云途等）" />
          </Form.Item>
          <Form.Item name="carrier" label="国际快递公司">
            <Select
              placeholder="请选择国际快递公司"
              allowClear
              options={[
                { value: '4PX递四方', label: '4PX递四方' },
                { value: '燕文物流', label: '燕文物流' },
                { value: '云途物流', label: '云途物流' },
                { value: '中国邮政', label: '中国邮政' },
                { value: 'DHL', label: 'DHL' },
                { value: 'FedEx', label: 'FedEx' },
                { value: 'UPS', label: 'UPS' },
                { value: '其他', label: '其他' },
              ]}
            />
          </Form.Item>
          <Form.Item name="tracking_url" label="国际物流查询链接">
            <Input placeholder="https://..." />
          </Form.Item>
          <Form.Item name="notes" label="备注">
            <Input.TextArea rows={2} placeholder="可选备注" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
