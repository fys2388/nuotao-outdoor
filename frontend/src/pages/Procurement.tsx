import { useState, useEffect } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Input, Select,
  Statistic, Row, Col, Spin, message, Modal, Descriptions, List,
  Badge, Tooltip, Empty, Tabs, Timeline, Divider, Alert,
  Steps, Form, InputNumber, Upload, Radio, DatePicker
} from 'antd'
import {
  ShoppingCartOutlined, ReloadOutlined, SearchOutlined,
  EyeOutlined, PlusOutlined, EditOutlined,
  TruckOutlined, CheckCircleOutlined, WarningOutlined,
  SyncOutlined, ClockCircleOutlined, ShopOutlined,
  DollarOutlined, PackageOutlined, CopyOutlined,
  SendOutlined, DownloadOutlined, FileTextOutlined,
  UserOutlined, PhoneOutlined, GlobalOutlined
} from '@ant-design/icons'

const { Title, Text, Paragraph } = Typography

interface PurchaseOrder {
  id: string
  po_number: string
  supplier: string
  supplier_contact: string
  supplier_phone: string
  items: PurchaseItem[]
  total_amount: number
  status: 'draft' | 'pending_payment' | 'paid' | 'shipped' | 'received' | 'completed' | 'cancelled'
  payment_method: string
  created_at: string
  paid_at?: string
  shipped_at?: string
  received_at?: string
  tracking_number?: string
  logistics_company?: string
  source: '1688' | 'manual' | 'auto'
  notes?: string
  woocommerce_orders: string[]
}

interface PurchaseItem {
  id: string
  product_name: string
  sku: string
  quantity: number
  unit_price: number
  total_price: number
  supplier_url?: string
  image?: string
}

const statusColors: Record<string, string> = {
  draft: 'default',
  pending_payment: 'orange',
  paid: 'blue',
  shipped: 'cyan',
  received: 'green',
  completed: 'green',
  cancelled: 'red',
}

const statusText: Record<string, string> = {
  draft: '草稿',
  pending_payment: '待付款',
  paid: '已付款',
  shipped: '已发货',
  received: '已收货',
  completed: '已完成',
  cancelled: '已取消',
}

const sourceColors: Record<string, string> = {
  '1688': 'orange',
  manual: 'blue',
  auto: 'purple',
}

export default function ProcurementPage() {
  const [activeTab, setActiveTab] = useState('orders')
  const [loading, setLoading] = useState(false)
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [payModalOpen, setPayModalOpen] = useState(false)
  const [viewingOrder, setViewingOrder] = useState<PurchaseOrder | null>(null)
  const [payingOrder, setPayingOrder] = useState<PurchaseOrder | null>(null)
  const [statusFilter, setStatusFilter] = useState('all')
  const [sourceFilter, setSourceFilter] = useState('all')
  const [searchText, setSearchText] = useState('')
  // 真实API数据状态
  const [procurementData, setProcurementData] = useState<any>(null)
  const [createForm] = Form.useForm()

  // 模拟采购单数据
  const mockPurchaseOrders: PurchaseOrder[] = [
    {
      id: '1', po_number: 'PO-20260905-001', supplier: '深圳户外装备有限公司', supplier_contact: '张经理', supplier_phone: '138****1234',
      items: [
        { id: '1', product_name: 'LED头灯 Pro 强光充电', sku: 'NT-HEADLAMP-001', quantity: 50, unit_price: 28.5, total_price: 1425, supplier_url: 'https://detail.1688.com/offer/1078487117828.html' },
        { id: '2', product_name: '太阳能露营灯 折叠', sku: 'NT-LAMP-002', quantity: 30, unit_price: 45.0, total_price: 1350 },
      ],
      total_amount: 2775, status: 'pending_payment', payment_method: '1688支付宝', created_at: '2026-09-05 10:28:03',
      source: '1688', notes: '客户订单WO-20260905-001, WO-20260905-002', woocommerce_orders: ['WO-20260905-001', 'WO-20260905-002'],
    },
    {
      id: '2', po_number: 'PO-20260904-003', supplier: '义乌户外用品批发', supplier_contact: '李老板', supplier_phone: '139****5678',
      items: [
        { id: '1', product_name: '保温水壶1L 304不锈钢', sku: 'NT-BOTTLE-001', quantity: 100, unit_price: 32.0, total_price: 3200 },
      ],
      total_amount: 3200, status: 'shipped', payment_method: '1688支付宝', created_at: '2026-09-04 14:30:00',
      paid_at: '2026-09-04 15:00:00', shipped_at: '2026-09-05 09:00:00', tracking_number: 'SF1234567890', logistics_company: '顺丰速运',
      source: '1688', woocommerce_orders: ['WO-20260904-005'],
    },
    {
      id: '3', po_number: 'PO-20260903-002', supplier: '广州帐篷制造厂', supplier_contact: '王厂长', supplier_phone: '137****9012',
      items: [
        { id: '1', product_name: '户外自动帐篷 3-4人', sku: 'NT-TENT-001', quantity: 20, unit_price: 185.0, total_price: 3700 },
        { id: '2', product_name: '帐篷地席 防水', sku: 'NT-MAT-001', quantity: 20, unit_price: 25.0, total_price: 500 },
      ],
      total_amount: 4200, status: 'received', payment_method: '银行转账', created_at: '2026-09-03 11:00:00',
      paid_at: '2026-09-03 11:30:00', shipped_at: '2026-09-03 16:00:00', received_at: '2026-09-05 10:00:00',
      tracking_number: 'YT9876543210', logistics_company: '圆通速递', source: 'manual', woocommerce_orders: [],
    },
    {
      id: '4', po_number: 'PO-20260902-001', supplier: '深圳户外装备有限公司', supplier_contact: '张经理', supplier_phone: '138****1234',
      items: [
        { id: '1', product_name: '登山杖 碳纤维折叠', sku: 'NT-POLE-001', quantity: 40, unit_price: 68.0, total_price: 2720 },
      ],
      total_amount: 2720, status: 'completed', payment_method: '1688支付宝', created_at: '2026-09-02 09:00:00',
      paid_at: '2026-09-02 09:30:00', shipped_at: '2026-09-02 14:00:00', received_at: '2026-09-04 10:00:00',
      tracking_number: 'ZTO1122334455', logistics_company: '中通快递', source: '1688', woocommerce_orders: ['WO-20260902-001'],
    },
    {
      id: '5', po_number: 'PO-20260901-005', supplier: '东莞背包工厂', supplier_contact: '陈主管', supplier_phone: '136****3456',
      items: [
        { id: '1', product_name: '户外登山背包 50L', sku: 'NT-BAG-001', quantity: 30, unit_price: 120.0, total_price: 3600 },
      ],
      total_amount: 3600, status: 'cancelled', payment_method: '-', created_at: '2026-09-01 16:00:00',
      source: 'auto', notes: '供应商缺货，已取消', woocommerce_orders: [],
    },
  ]

  // 加载采购数据（调用真实API，失败则使用mock数据降级）
  const loadProcurementData = async () => {
    try {
      setLoading(true)
      // 调用采购单列表API
      const ordersResp = await fetch('/api/v1/procurement/orders')
      if (ordersResp.ok) {
        const ordersData = await ordersResp.json()
        setProcurementData(ordersData)
        console.log('Procurement orders:', ordersData)
      }
      message.success('采购数据加载完成')
    } catch (e: any) {
      console.error('Load procurement data error:', e)
      message.warning(`API调用失败，使用模拟数据：${e.message || '未知错误'}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadProcurementData()
  }, [])

  // 统计数据（优先使用真实API数据，失败则使用mock数据降级）
  const realOrders = procurementData?.items || procurementData?.orders || []
  const orders = realOrders.length > 0 ? realOrders : mockPurchaseOrders
  const stats = {
    totalOrders: orders.length,
    pendingPayment: orders.filter((o: any) => o.status === 'pending_payment' || o.status === 'pending').length,
    inTransit: orders.filter((o: any) => o.status === 'shipped' || o.status === 'in_transit').length,
    totalAmount: orders.reduce((sum: number, o: any) => sum + (o.total_amount || o.amount || 0), 0),
    thisMonthAmount: orders.filter((o: any) => (o.created_at || '').startsWith('2026-09')).reduce((sum: number, o: any) => sum + (o.total_amount || o.amount || 0), 0),
  }

  // 采购单表格列
  const orderColumns = [
    {
      title: '采购单号',
      dataIndex: 'po_number',
      key: 'po_number',
      width: 160,
      render: (text: string, record: PurchaseOrder) => (
        <Space>
          <Text strong style={{ fontSize: '12px' }}>{text}</Text>
          <Tag color={sourceColors[record.source]} style={{ fontSize: '10px' }}>{record.source}</Tag>
        </Space>
      ),
    },
    {
      title: '供应商',
      dataIndex: 'supplier',
      key: 'supplier',
      width: 180,
      render: (text: string, record: PurchaseOrder) => (
        <div>
          <div style={{ fontSize: '12px' }}>{text}</div>
          <div style={{ fontSize: '10px', color: '#999' }}>{record.supplier_contact} {record.supplier_phone}</div>
        </div>
      ),
    },
    {
      title: '商品',
      key: 'items',
      width: 200,
      render: (_: any, record: PurchaseOrder) => (
        <div>
          {record.items.slice(0, 2).map((item, idx) => (
            <div key={idx} style={{ fontSize: '11px', color: '#666' }}>
              {item.product_name} × {item.quantity}
            </div>
          ))}
          {record.items.length > 2 && <div style={{ fontSize: '10px', color: '#999' }}>等{record.items.length}件商品</div>}
        </div>
      ),
    },
    {
      title: '金额',
      dataIndex: 'total_amount',
      key: 'total_amount',
      width: 100,
      render: (amount: number) => <Text strong style={{ color: '#f5222d' }}>¥{amount.toLocaleString()}</Text>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => <Tag color={statusColors[status]}>{statusText[status]}</Tag>,
    },
    {
      title: '关联订单',
      dataIndex: 'woocommerce_orders',
      key: 'woocommerce_orders',
      width: 120,
      render: (orders: string[]) => orders.length > 0 ? (
        <Space size={4}>
          {orders.slice(0, 2).map((o, i) => <Tag key={i} color="purple" style={{ fontSize: '10px' }}>{o}</Tag>)}
          {orders.length > 2 && <Text type="secondary" style={{ fontSize: '10px' }}>+{orders.length - 2}</Text>}
        </Space>
      ) : <Text type="secondary" style={{ fontSize: '11px' }}>备货采购</Text>,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 150,
      render: (text: string) => <Text type="secondary" style={{ fontSize: '11px' }}>{text}</Text>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_: any, record: PurchaseOrder) => (
        <Space size="small">
          <Button size="small" icon={<EyeOutlined />} onClick={() => {
            setViewingOrder(record)
            setDetailModalOpen(true)
          }}>详情</Button>
          {record.status === 'pending_payment' && (
            <Button size="small" type="primary" icon={<DollarOutlined />} onClick={() => {
              setPayingOrder(record)
              setPayModalOpen(true)
            }}>去付款</Button>
          )}
          {record.status === 'shipped' && (
            <Button size="small" icon={<PackageOutlined />} onClick={() => message.success('已确认收货')}>确认收货</Button>
          )}
        </Space>
      ),
    },
  ]

  // 状态步骤
  const getStatusStep = (status: string) => {
    const steps = ['draft', 'pending_payment', 'paid', 'shipped', 'received', 'completed']
    return steps.indexOf(status)
  }

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <ShoppingCartOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>代采ERP工作台</Title>
            <Text type="secondary">1688半自动下单、采购单管理、物流追踪</Text>
          </div>
        </Space>
        <Space>
          <Button icon={<DownloadOutlined />} onClick={() => message.success('采购报表导出中...')}>导出报表</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => {
            createForm.resetFields()
            setCreateModalOpen(true)
          }}>新建采购单</Button>
        </Space>
      </div>

      {/* 待付款预警 */}
      {stats.pendingPayment > 0 && (
        <Alert
          message={`有 ${stats.pendingPayment} 个采购单待付款`}
          description="请及时完成付款，避免影响发货和客户订单履约。"
          type="warning"
          showIcon
          icon={<WarningOutlined />}
          style={{ marginBottom: '16px' }}
          action={
            <Button size="small" type="primary" onClick={() => setStatusFilter('pending_payment')}>查看待付款</Button>
          }
        />
      )}

      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: '16px' }}>
        <Col span={5}>
          <Card size="small">
            <Statistic title="采购单总数" value={stats.totalOrders} prefix={<FileTextOutlined />} />
          </Card>
        </Col>
        <Col span={5}>
          <Card size="small">
            <Statistic title="待付款" value={stats.pendingPayment} valueStyle={{ color: '#faad14' }} prefix={<DollarOutlined />} />
          </Card>
        </Col>
        <Col span={5}>
          <Card size="small">
            <Statistic title="运输中" value={stats.inTransit} valueStyle={{ color: '#1890ff' }} prefix={<TruckOutlined />} />
          </Card>
        </Col>
        <Col span={5}>
          <Card size="small">
            <Statistic title="本月采购额" value={stats.thisMonthAmount} prefix="¥" valueStyle={{ color: '#f5222d' }} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="累计采购额" value={stats.totalAmount} prefix="¥" />
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
              key: 'orders',
              label: '采购单管理',
              children: (
                <div>
                  {/* 筛选栏 */}
                  <Space wrap style={{ marginBottom: '16px' }}>
                    <Input placeholder="搜索采购单号/供应商" prefix={<SearchOutlined />} value={searchText} onChange={(e) => setSearchText(e.target.value)} style={{ width: 220 }} allowClear />
                    <Select value={statusFilter} onChange={setStatusFilter} style={{ width: 120 }} options={[
                      { value: 'all', label: '全部状态' },
                      { value: 'draft', label: '草稿' },
                      { value: 'pending_payment', label: '待付款' },
                      { value: 'paid', label: '已付款' },
                      { value: 'shipped', label: '已发货' },
                      { value: 'received', label: '已收货' },
                      { value: 'completed', label: '已完成' },
                      { value: 'cancelled', label: '已取消' },
                    ]} />
                    <Select value={sourceFilter} onChange={setSourceFilter} style={{ width: 120 }} options={[
                      { value: 'all', label: '全部来源' },
                      { value: '1688', label: '1688' },
                      { value: 'manual', label: '手动创建' },
                      { value: 'auto', label: '自动生成' },
                    ]} />
                    <DatePicker.RangePicker showTime placeholder={['开始日期', '结束日期']} />
                    <Button icon={<SearchOutlined />} type="primary">搜索</Button>
                    <Button icon={<ReloadOutlined />} onClick={() => {
                      setSearchText('')
                      setStatusFilter('all')
                      setSourceFilter('all')
                    }}>重置</Button>
                  </Space>

                  <Table
                    columns={orderColumns}
                    dataSource={mockPurchaseOrders}
                    rowKey="id"
                    loading={loading}
                    pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 个采购单` }}
                    locale={{ emptyText: <Empty description="暂无采购单" /> }}
                  />
                </div>
              ),
            },
            {
              key: 'suppliers',
              label: '供应商管理',
              children: (
                <div>
                  <Row gutter={[16, 16]}>
                    {[
                      { name: '深圳户外装备有限公司', contact: '张经理', phone: '138****1234', products: 15, totalOrders: 28, totalAmount: 45600, rating: 4.8 },
                      { name: '义乌户外用品批发', contact: '李老板', phone: '139****5678', products: 8, totalOrders: 15, totalAmount: 28900, rating: 4.5 },
                      { name: '广州帐篷制造厂', contact: '王厂长', phone: '137****9012', products: 5, totalOrders: 10, totalAmount: 32500, rating: 4.7 },
                      { name: '东莞背包工厂', contact: '陈主管', phone: '136****3456', products: 6, totalOrders: 12, totalAmount: 28800, rating: 4.6 },
                    ].map((supplier, idx) => (
                      <Col span={12} key={idx}>
                        <Card size="small" title={
                          <Space>
                            <ShopOutlined style={{ color: '#fa8c16' }} />
                            <span>{supplier.name}</span>
                          </Space>
                        }>
                          <Row gutter={16}>
                            <Col span={12}>
                              <Descriptions column={1} size="small">
                                <Descriptions.Item label="联系人">{supplier.contact}</Descriptions.Item>
                                <Descriptions.Item label="电话">{supplier.phone}</Descriptions.Item>
                                <Descriptions.Item label="商品数">{supplier.products} 款</Descriptions.Item>
                              </Descriptions>
                            </Col>
                            <Col span={12}>
                              <Descriptions column={1} size="small">
                                <Descriptions.Item label="合作订单">{supplier.totalOrders} 单</Descriptions.Item>
                                <Descriptions.Item label="累计金额">¥{supplier.totalAmount.toLocaleString()}</Descriptions.Item>
                                <Descriptions.Item label="评分">
                                  <Text type="warning">★ {supplier.rating}</Text>
                                </Descriptions.Item>
                              </Descriptions>
                            </Col>
                          </Row>
                        </Card>
                      </Col>
                    ))}
                  </Row>
                </div>
              ),
            },
            {
              key: 'analytics',
              label: '采购分析',
              children: (
                <div>
                  <Row gutter={[16, 16]} style={{ marginBottom: '16px' }}>
                    <Col span={8}>
                      <Card size="small" title="本月采购趋势">
                        <div style={{ height: 200, display: 'flex', alignItems: 'flex-end', justifyContent: 'space-around', padding: '20px 0' }}>
                          {[65, 82, 45, 90, 75, 88, 95].map((h, i) => (
                            <div key={i} style={{ textAlign: 'center' }}>
                              <div style={{ width: 30, height: h * 1.5, background: 'linear-gradient(180deg, #722ed1, #9254de)', borderRadius: '4px 4px 0 0' }} />
                              <div style={{ fontSize: '10px', color: '#999', marginTop: 4 }}>9/{i + 1}</div>
                            </div>
                          ))}
                        </div>
                      </Card>
                    </Col>
                    <Col span={8}>
                      <Card size="small" title="供应商采购占比">
                        <div style={{ padding: '20px 0' }}>
                          {[
                            { name: '深圳户外装备', percent: 35, color: '#722ed1' },
                            { name: '广州帐篷制造', percent: 25, color: '#1890ff' },
                            { name: '东莞背包工厂', percent: 22, color: '#52c41a' },
                            { name: '义乌户外批发', percent: 18, color: '#faad14' },
                          ].map((item, i) => (
                            <div key={i} style={{ marginBottom: 12 }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                                <Text style={{ fontSize: '12px' }}>{item.name}</Text>
                                <Text type="secondary" style={{ fontSize: '12px' }}>{item.percent}%</Text>
                              </div>
                              <div style={{ height: 8, background: '#f0f0f0', borderRadius: 4 }}>
                                <div style={{ width: `${item.percent}%`, height: '100%', background: item.color, borderRadius: 4 }} />
                              </div>
                            </div>
                          ))}
                        </div>
                      </Card>
                    </Col>
                    <Col span={8}>
                      <Card size="small" title="采购品类分布">
                        <div style={{ padding: '20px 0' }}>
                          {[
                            { name: '照明设备', count: 45, amount: 12800 },
                            { name: '户外家具', count: 30, amount: 15600 },
                            { name: '背包配件', count: 38, amount: 9800 },
                            { name: '水具餐具', count: 52, amount: 8500 },
                            { name: '其他', count: 25, amount: 6200 },
                          ].map((item, i) => (
                            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #f0f0f0' }}>
                              <Text style={{ fontSize: '12px' }}>{item.name}</Text>
                              <Space>
                                <Text type="secondary" style={{ fontSize: '11px' }}>{item.count}件</Text>
                                <Text strong style={{ fontSize: '12px', color: '#f5222d' }}>¥{item.amount.toLocaleString()}</Text>
                              </Space>
                            </div>
                          ))}
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

      {/* 采购单详情Modal */}
      <Modal
        title={`采购单详情 - ${viewingOrder?.po_number || ''}`}
        open={detailModalOpen}
        onCancel={() => setDetailModalOpen(false)}
        footer={[
          <Button key="close" onClick={() => setDetailModalOpen(false)}>关闭</Button>,
        ]}
        width={800}
      >
        {viewingOrder && (
          <div>
            {/* 状态进度 */}
            <Steps
              current={getStatusStep(viewingOrder.status)}
              size="small"
              items={[
                { title: '创建', description: viewingOrder.created_at },
                { title: '待付款', description: viewingOrder.status !== 'draft' ? '已提交' : '-' },
                { title: '已付款', description: viewingOrder.paid_at || '-' },
                { title: '已发货', description: viewingOrder.shipped_at || '-' },
                { title: '已收货', description: viewingOrder.received_at || '-' },
                { title: '完成' },
              ]}
              style={{ marginBottom: '20px' }}
            />

            <Descriptions column={2} bordered size="small" style={{ marginBottom: '16px' }}>
              <Descriptions.Item label="采购单号">{viewingOrder.po_number}</Descriptions.Item>
              <Descriptions.Item label="状态"><Tag color={statusColors[viewingOrder.status]}>{statusText[viewingOrder.status]}</Tag></Descriptions.Item>
              <Descriptions.Item label="供应商">{viewingOrder.supplier}</Descriptions.Item>
              <Descriptions.Item label="联系人">{viewingOrder.supplier_contact} ({viewingOrder.supplier_phone})</Descriptions.Item>
              <Descriptions.Item label="来源"><Tag color={sourceColors[viewingOrder.source]}>{viewingOrder.source}</Tag></Descriptions.Item>
              <Descriptions.Item label="支付方式">{viewingOrder.payment_method}</Descriptions.Item>
              <Descriptions.Item label="创建时间">{viewingOrder.created_at}</Descriptions.Item>
              <Descriptions.Item label="关联WC订单">
                {viewingOrder.woocommerce_orders.length > 0 ? viewingOrder.woocommerce_orders.join(', ') : '备货采购'}
              </Descriptions.Item>
            </Descriptions>

            {/* 商品列表 */}
            <Card size="small" title="采购商品" style={{ marginBottom: '16px' }}>
              <Table
                dataSource={viewingOrder.items}
                rowKey="id"
                size="small"
                pagination={false}
                columns={[
                  { title: '商品名称', dataIndex: 'product_name', key: 'product_name' },
                  { title: 'SKU', dataIndex: 'sku', key: 'sku', render: (t) => <Text code style={{ fontSize: '11px' }}>{t}</Text> },
                  { title: '单价', dataIndex: 'unit_price', key: 'unit_price', render: (p) => `¥${p}` },
                  { title: '数量', dataIndex: 'quantity', key: 'quantity' },
                  { title: '小计', dataIndex: 'total_price', key: 'total_price', render: (p) => <Text strong style={{ color: '#f5222d' }}>¥{p}</Text> },
                  {
                    title: '1688链接', key: 'url',
                    render: (_: any, record: PurchaseItem) => record.supplier_url ? (
                      <Button size="small" type="link" href={record.supplier_url} target="_blank">查看</Button>
                    ) : '-',
                  },
                ]}
              />
              <div style={{ textAlign: 'right', marginTop: 12, paddingTop: 12, borderTop: '1px solid #f0f0f0' }}>
                <Text strong style={{ fontSize: '16px' }}>合计：</Text>
                <Text strong style={{ fontSize: '20px', color: '#f5222d' }}>¥{viewingOrder.total_amount.toLocaleString()}</Text>
              </div>
            </Card>

            {/* 物流信息 */}
            {viewingOrder.tracking_number && (
              <Card size="small" title="物流信息">
                <Descriptions column={2} size="small">
                  <Descriptions.Item label="物流公司">{viewingOrder.logistics_company}</Descriptions.Item>
                  <Descriptions.Item label="运单号">
                    <Space>
                      <Text code>{viewingOrder.tracking_number}</Text>
                      <Button size="small" type="text" icon={<CopyOutlined />} onClick={() => message.success('已复制')} />
                    </Space>
                  </Descriptions.Item>
                </Descriptions>
                <Timeline style={{ marginTop: 16 }}>
                  <Timeline.Item color="green">已签收 - {viewingOrder.received_at || '派送中'}</Timeline.Item>
                  <Timeline.Item color="blue">运输中 - 已到达深圳转运中心</Timeline.Item>
                  <Timeline.Item color="blue">已揽收 - {viewingOrder.shipped_at}</Timeline.Item>
                  <Timeline.Item>商家已发货</Timeline.Item>
                </Timeline>
              </Card>
            )}

            {viewingOrder.notes && (
              <Alert message="备注" description={viewingOrder.notes} type="info" showIcon style={{ marginTop: 16 }} />
            )}
          </div>
        )}
      </Modal>

      {/* 1688半自动付款Modal */}
      <Modal
        title="1688半自动付款"
        open={payModalOpen}
        onCancel={() => setPayModalOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setPayModalOpen(false)}>取消</Button>,
          <Button key="copy" icon={<CopyOutlined />} onClick={() => message.success('采购信息已复制到剪贴板')}>复制采购信息</Button>,
          <Button key="open" type="primary" icon={<GlobalOutlined />} onClick={() => {
            message.success('正在打开1688订单页面，请在浏览器中完成支付')
            setPayModalOpen(false)
          }}>打开1688付款</Button>,
        ]}
        width={600}
      >
        {payingOrder && (
          <div>
            <Alert
              message="半自动付款模式"
              description="系统已为您预填采购信息，请点击下方按钮打开1688完成支付。支付完成后系统将自动更新采购单状态。"
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
            />
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label="采购单号">{payingOrder.po_number}</Descriptions.Item>
              <Descriptions.Item label="供应商">{payingOrder.supplier}</Descriptions.Item>
              <Descriptions.Item label="商品数量">{payingOrder.items.length} 款 / {payingOrder.items.reduce((s, i) => s + i.quantity, 0)} 件</Descriptions.Item>
              <Descriptions.Item label="应付金额"><Text strong style={{ color: '#f5222d', fontSize: '18px' }}>¥{payingOrder.total_amount.toLocaleString()}</Text></Descriptions.Item>
            </Descriptions>
            <Divider />
            <div style={{ background: '#fafafa', padding: 12, borderRadius: 8 }}>
              <Text type="secondary" style={{ fontSize: '12px' }}>
                操作步骤：<br />
                1. 点击"打开1688付款"按钮<br />
                2. 在1688页面确认商品和金额<br />
                3. 完成支付宝支付<br />
                4. 返回系统，采购单状态将自动更新为"已付款"
              </Text>
            </div>
          </div>
        )}
      </Modal>

      {/* 新建采购单Modal */}
      <Modal
        title="新建采购单"
        open={createModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setCreateModalOpen(false)}>取消</Button>,
          <Button key="save" type="primary" onClick={() => {
            message.success('采购单已创建')
            setCreateModalOpen(false)
          }}>创建</Button>,
        ]}
        width={700}
      >
        <Form form={createForm} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="supplier" label="供应商" rules={[{ required: true }]}>
                <Select placeholder="选择供应商" options={[
                  { value: '深圳户外装备有限公司', label: '深圳户外装备有限公司' },
                  { value: '义乌户外用品批发', label: '义乌户外用品批发' },
                  { value: '广州帐篷制造厂', label: '广州帐篷制造厂' },
                  { value: '东莞背包工厂', label: '东莞背包工厂' },
                ]} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="source" label="采购来源" initialValue="1688">
                <Select options={[
                  { value: '1688', label: '1688' },
                  { value: 'manual', label: '手动创建' },
                ]} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="notes" label="备注">
            <Input.TextArea rows={2} placeholder="采购备注（可选）" />
          </Form.Item>
          <Alert
            message="提示"
            description="创建采购单后，可在详情页添加采购商品。1688来源的采购单支持半自动付款。"
            type="info"
            showIcon
          />
        </Form>
      </Modal>
    </div>
  )
}
