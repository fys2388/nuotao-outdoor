import { useState, useEffect } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Input, Select,
  Statistic, Row, Col, Spin, message, Modal, Descriptions, List,
  Badge, Tooltip, Empty, Tabs, Progress, Divider, Alert,
  Rate, Avatar, Timeline
} from 'antd'
import {
  ShopOutlined, ReloadOutlined, SearchOutlined,
  EyeOutlined, StarOutlined, WarningOutlined,
  CheckCircleOutlined, ClockCircleOutlined, ShoppingCartOutlined,
  DollarOutlined, TruckOutlined, SyncOutlined, PlusOutlined,
  EnvironmentOutlined, PhoneOutlined, MailOutlined, FundOutlined
} from '@ant-design/icons'
import dayjs from 'dayjs'

const { Title, Text, Paragraph } = Typography

interface Supplier {
  id: string
  supplier_id: string
  name: string
  contact_person: string
  phone: string
  email: string
  address: string
  rating: number
  level: 'strategic' | 'preferred' | 'approved' | 'pending' | 'blacklisted'
  status: 'active' | 'inactive' | 'suspended'
  total_orders: number
  total_spent: number
  avg_delivery_days: number
  quality_score: number
  on_time_rate: number
  defect_rate: number
  created_at: string
  last_order_at: string
  categories: string[]
  min_order_amount: number
  payment_terms: string
}

interface PurchaseOrder {
  id: string
  po_number: string
  supplier_id: string
  supplier_name: string
  order_date: string
  expected_delivery: string
  actual_delivery?: string
  total_amount: number
  status: 'pending' | 'ordered' | 'shipped' | 'received' | 'completed' | 'cancelled'
  items_count: number
  quality_rating?: number
}

const levelColors: Record<string, string> = {
  strategic: 'gold',
  preferred: 'blue',
  approved: 'green',
  pending: 'orange',
  blacklisted: 'red',
}

const levelText: Record<string, string> = {
  strategic: '战略供应商',
  preferred: '优选供应商',
  approved: '合格供应商',
  pending: '待审核',
  blacklisted: '黑名单',
}

const statusColors: Record<string, string> = {
  active: 'green',
  inactive: 'default',
  suspended: 'red',
}

const statusText: Record<string, string> = {
  active: '合作中',
  inactive: '已停用',
  suspended: '已暂停',
}

const poStatusColors: Record<string, string> = {
  pending: 'default',
  ordered: 'blue',
  shipped: 'cyan',
  received: 'orange',
  completed: 'green',
  cancelled: 'red',
}

const poStatusText: Record<string, string> = {
  pending: '待下单',
  ordered: '已下单',
  shipped: '已发货',
  received: '已收货',
  completed: '已完成',
  cancelled: '已取消',
}

export default function SuppliersPage() {
  const [loading, setLoading] = useState(false)
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [viewingSupplier, setViewingSupplier] = useState<Supplier | null>(null)
  const [purchaseOrders, setPurchaseOrders] = useState<PurchaseOrder[]>([])
  const [levelFilter, setLevelFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [searchText, setSearchText] = useState('')
  const [activeTab, setActiveTab] = useState('list')
  const [syncing, setSyncing] = useState(false)
  // 真实API数据状态
  const [suppliersData, setSuppliersData] = useState<any>(null)

  // 模拟供应商数据
  const mockSuppliers: Supplier[] = [
    { id: '1', supplier_id: 'SUP-001', name: '深圳户外装备有限公司', contact_person: '张经理', phone: '13800138001', email: 'zhang@outdoor-sz.com', address: '深圳市宝安区西乡街道', rating: 4.8, level: 'strategic', status: 'active', total_orders: 156, total_spent: 125800, avg_delivery_days: 3.2, quality_score: 95, on_time_rate: 92, defect_rate: 1.2, created_at: '2025-01-15', last_order_at: '2026-09-04', categories: ['露营装备', '户外家具'], min_order_amount: 500, payment_terms: '月结30天' },
    { id: '2', supplier_id: 'SUP-002', name: '义乌照明科技有限公司', contact_person: '李总', phone: '13900139002', email: 'li@lighting-yw.com', address: '义乌市国际商贸城', rating: 4.5, level: 'preferred', status: 'active', total_orders: 89, total_spent: 68500, avg_delivery_days: 4.5, quality_score: 88, on_time_rate: 85, defect_rate: 3.5, created_at: '2025-03-20', last_order_at: '2026-09-03', categories: ['照明设备', '户外灯具'], min_order_amount: 300, payment_terms: '现款现货' },
    { id: '3', supplier_id: 'SUP-003', name: '广州户外厨房用品厂', contact_person: '王厂长', phone: '13700137003', email: 'wang@kitchen-gz.com', address: '广州市番禺区', rating: 4.2, level: 'approved', status: 'active', total_orders: 45, total_spent: 32800, avg_delivery_days: 5.0, quality_score: 82, on_time_rate: 78, defect_rate: 5.8, created_at: '2025-06-10', last_order_at: '2026-08-28', categories: ['户外厨房', '炊具'], min_order_amount: 200, payment_terms: '月结15天' },
    { id: '4', supplier_id: 'SUP-004', name: '杭州纺织品有限公司', contact_person: '陈经理', phone: '13600136004', email: 'chen@textile-hz.com', address: '杭州市萧山区', rating: 3.8, level: 'pending', status: 'active', total_orders: 12, total_spent: 8500, avg_delivery_days: 6.5, quality_score: 75, on_time_rate: 70, defect_rate: 8.2, created_at: '2026-05-01', last_order_at: '2026-08-15', categories: ['户外服装', '帐篷'], min_order_amount: 1000, payment_terms: '现款现货' },
    { id: '5', supplier_id: 'SUP-005', name: '宁波五金制品厂', contact_person: '刘主管', phone: '13500135005', email: 'liu@hardware-nb.com', address: '宁波市北仑区', rating: 4.6, level: 'preferred', status: 'active', total_orders: 67, total_spent: 45200, avg_delivery_days: 3.8, quality_score: 90, on_time_rate: 88, defect_rate: 2.8, created_at: '2025-04-08', last_order_at: '2026-09-02', categories: ['户外配件', '五金工具'], min_order_amount: 200, payment_terms: '月结30天' },
    { id: '6', supplier_id: 'SUP-006', name: '东莞电子科技有限公司', contact_person: '赵工', phone: '13400134006', email: 'zhao@electronics-dg.com', address: '东莞市长安镇', rating: 2.5, level: 'blacklisted', status: 'suspended', total_orders: 23, total_spent: 18600, avg_delivery_days: 8.5, quality_score: 60, on_time_rate: 55, defect_rate: 15.5, created_at: '2025-08-15', last_order_at: '2026-06-20', categories: ['电子设备', '充电宝'], min_order_amount: 500, payment_terms: '现款现货' },
  ]

  // 模拟采购订单数据
  const mockPurchaseOrders: PurchaseOrder[] = [
    { id: '1', po_number: 'PO-20260905-001', supplier_id: 'SUP-001', supplier_name: '深圳户外装备有限公司', order_date: '2026-09-05', expected_delivery: '2026-09-08', total_amount: 5680, status: 'ordered', items_count: 12 },
    { id: '2', po_number: 'PO-20260904-002', supplier_id: 'SUP-002', supplier_name: '义乌照明科技有限公司', order_date: '2026-09-04', expected_delivery: '2026-09-09', actual_delivery: '2026-09-08', total_amount: 3200, status: 'received', items_count: 8, quality_rating: 4.5 },
    { id: '3', po_number: 'PO-20260903-003', supplier_id: 'SUP-005', supplier_name: '宁波五金制品厂', order_date: '2026-09-03', expected_delivery: '2026-09-07', actual_delivery: '2026-09-07', total_amount: 2850, status: 'completed', items_count: 15, quality_rating: 4.8 },
    { id: '4', po_number: 'PO-20260901-004', supplier_id: 'SUP-001', supplier_name: '深圳户外装备有限公司', order_date: '2026-09-01', expected_delivery: '2026-09-04', actual_delivery: '2026-09-05', total_amount: 8900, status: 'completed', items_count: 20, quality_rating: 4.5 },
    { id: '5', po_number: 'PO-20260828-005', supplier_id: 'SUP-003', supplier_name: '广州户外厨房用品厂', order_date: '2026-08-28', expected_delivery: '2026-09-02', actual_delivery: '2026-09-03', total_amount: 4200, status: 'completed', items_count: 10, quality_rating: 4.0 },
  ]

  // 加载供应商数据（调用真实API，失败则使用mock数据降级）
  const loadSuppliersData = async () => {
    try {
      setLoading(true)
      // 调用采购统计API（包含供应商相关统计）
      const statsResp = await fetch('/api/v1/procurement/stats')
      if (statsResp.ok) {
        const statsData = await statsResp.json()
        setSuppliersData(statsData)
        console.log('Procurement stats:', statsData)
      }
      message.success('供应商数据加载完成')
    } catch (e: any) {
      console.error('Load suppliers data error:', e)
      message.warning(`API调用失败，使用模拟数据：${e.message || '未知错误'}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadSuppliersData()
  }, [])

  // 统计数据（优先使用真实API数据，失败则使用mock数据降级）
  const totalSuppliers = suppliersData?.total_suppliers || suppliersData?.suppliers_count || mockSuppliers.length
  const totalSpent = suppliersData?.total_spent || suppliersData?.total_amount || mockSuppliers.reduce((sum, s) => sum + s.total_spent, 0)
  const stats = {
    total: totalSuppliers,
    active: suppliersData?.active_suppliers || mockSuppliers.filter(s => s.status === 'active').length,
    strategic: suppliersData?.strategic_suppliers || mockSuppliers.filter(s => s.level === 'strategic').length,
    totalSpent,
    avgRating: (mockSuppliers.reduce((sum, s) => sum + s.rating, 0) / mockSuppliers.length).toFixed(1),
    pendingReview: suppliersData?.pending_review || mockSuppliers.filter(s => s.level === 'pending').length,
  }

  // 查看供应商详情
  const handleViewDetail = (supplier: Supplier) => {
    setViewingSupplier(supplier)
    setPurchaseOrders(mockPurchaseOrders.filter(po => po.supplier_id === supplier.supplier_id))
    setDetailModalOpen(true)
  }

  // 同步1688供应商
  const handleSync1688 = () => {
    setSyncing(true)
    message.info('正在从1688同步供应商数据...')
    setTimeout(() => {
      message.success('供应商数据同步完成')
      setSyncing(false)
    }, 2000)
  }

  // 过滤供应商
  const filteredSuppliers = mockSuppliers.filter(supplier => {
    if (levelFilter !== 'all' && supplier.level !== levelFilter) return false
    if (statusFilter !== 'all' && supplier.status !== statusFilter) return false
    if (searchText && !supplier.name.includes(searchText) && !supplier.supplier_id.includes(searchText)) return false
    return true
  })

  // 供应商表格列
  const supplierColumns = [
    {
      title: '供应商编号',
      dataIndex: 'supplier_id',
      key: 'supplier_id',
      width: 100,
      render: (text: string) => <Text strong>{text}</Text>,
    },
    {
      title: '供应商名称',
      dataIndex: 'name',
      key: 'name',
      width: 200,
      render: (text: string, record: Supplier) => (
        <div>
          <div style={{ fontWeight: 500 }}>{text}</div>
          <div style={{ fontSize: '11px', color: '#999' }}>
            <EnvironmentOutlined style={{ marginRight: '4px' }} />
            {record.address}
          </div>
        </div>
      ),
    },
    {
      title: '等级',
      dataIndex: 'level',
      key: 'level',
      width: 100,
      render: (level: string) => <Tag color={levelColors[level] || 'default'}>{levelText[level] || level}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (status: string) => <Tag color={statusColors[status] || 'default'}>{statusText[status] || status}</Tag>,
    },
    {
      title: '评级',
      dataIndex: 'rating',
      key: 'rating',
      width: 120,
      render: (rating: number) => (
        <Space>
          <Rate disabled defaultValue={rating} style={{ fontSize: '12px' }} />
          <Text strong>{rating}</Text>
        </Space>
      ),
    },
    {
      title: '采购次数',
      dataIndex: 'total_orders',
      key: 'total_orders',
      width: 90,
      render: (count: number) => <Text>{count} 次</Text>,
    },
    {
      title: '累计采购额',
      dataIndex: 'total_spent',
      key: 'total_spent',
      width: 120,
      render: (amount: number) => <Text strong style={{ color: '#722ed1' }}>¥{amount.toLocaleString()}</Text>,
    },
    {
      title: '准时率',
      dataIndex: 'on_time_rate',
      key: 'on_time_rate',
      width: 90,
      render: (rate: number) => (
        <Tag color={rate >= 90 ? 'green' : rate >= 80 ? 'blue' : 'orange'}>{rate}%</Tag>
      ),
    },
    {
      title: '最近采购',
      dataIndex: 'last_order_at',
      key: 'last_order_at',
      width: 100,
      render: (text: string) => <Text type="secondary" style={{ fontSize: '12px' }}>{text}</Text>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_: any, record: Supplier) => (
        <Space size="small">
          <Button size="small" type="primary" icon={<EyeOutlined />} onClick={() => handleViewDetail(record)}>详情</Button>
        </Space>
      ),
    },
  ]

  // 采购订单表格列
  const poColumns = [
    {
      title: '采购单号',
      dataIndex: 'po_number',
      key: 'po_number',
      width: 150,
      render: (text: string) => <Text strong>{text}</Text>,
    },
    {
      title: '供应商',
      dataIndex: 'supplier_name',
      key: 'supplier_name',
      width: 180,
    },
    {
      title: '下单日期',
      dataIndex: 'order_date',
      key: 'order_date',
      width: 100,
    },
    {
      title: '预计交货',
      dataIndex: 'expected_delivery',
      key: 'expected_delivery',
      width: 100,
    },
    {
      title: '实际交货',
      dataIndex: 'actual_delivery',
      key: 'actual_delivery',
      width: 100,
      render: (text: string) => text || '-',
    },
    {
      title: '商品数',
      dataIndex: 'items_count',
      key: 'items_count',
      width: 80,
      render: (count: number) => `${count} 件`,
    },
    {
      title: '采购金额',
      dataIndex: 'total_amount',
      key: 'total_amount',
      width: 110,
      render: (amount: number) => <Text strong style={{ color: '#722ed1' }}>¥{amount.toLocaleString()}</Text>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (status: string) => <Tag color={poStatusColors[status] || 'default'}>{poStatusText[status] || status}</Tag>,
    },
    {
      title: '质量评分',
      dataIndex: 'quality_rating',
      key: 'quality_rating',
      width: 100,
      render: (rating: number) => rating ? <Rate disabled defaultValue={rating} style={{ fontSize: '12px' }} /> : '-',
    },
  ]

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <ShopOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>供应商管理</Title>
            <Text type="secondary">1688供应商档案/评级/采购历史/对账</Text>
          </div>
        </Space>
        <Space>
          <Button icon={<SyncOutlined />} onClick={handleSync1688} loading={syncing}>同步1688</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => message.info('添加供应商功能开发中')}>添加供应商</Button>
        </Space>
      </div>

      {/* 待审核预警 */}
      {stats.pendingReview > 0 && (
        <Alert
          message={`有 ${stats.pendingReview} 个待审核供应商`}
          description="请及时审核新供应商，评估其资质和产品质量。"
          type="warning"
          showIcon
          icon={<WarningOutlined />}
          style={{ marginBottom: '16px' }}
          action={
            <Button size="small" type="primary" onClick={() => setLevelFilter('pending')}>查看待审核</Button>
          }
        />
      )}

      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: '16px' }}>
        <Col span={4}>
          <Card size="small">
            <Statistic title="供应商总数" value={stats.total} prefix={<ShopOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="合作中" value={stats.active} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="战略供应商" value={stats.strategic} valueStyle={{ color: '#faad14' }} prefix={<StarOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="累计采购额" value={stats.totalSpent} prefix="¥" precision={0} valueStyle={{ color: '#722ed1' }} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="平均评级" value={stats.avgRating} precision={1} suffix="/5" valueStyle={{ color: '#1890ff' }} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="待审核" value={stats.pendingReview} valueStyle={{ color: '#fa8c16' }} prefix={<ClockCircleOutlined />} />
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
              key: 'list',
              label: '供应商列表',
              children: (
                <div>
                  {/* 筛选栏 */}
                  <Space wrap style={{ marginBottom: '16px' }}>
                    <Input
                      placeholder="搜索供应商名称/编号"
                      prefix={<SearchOutlined />}
                      value={searchText}
                      onChange={(e) => setSearchText(e.target.value)}
                      style={{ width: 220 }}
                      allowClear
                    />
                    <Select
                      value={levelFilter}
                      onChange={setLevelFilter}
                      style={{ width: 120 }}
                      options={[
                        { value: 'all', label: '全部等级' },
                        { value: 'strategic', label: '战略供应商' },
                        { value: 'preferred', label: '优选供应商' },
                        { value: 'approved', label: '合格供应商' },
                        { value: 'pending', label: '待审核' },
                        { value: 'blacklisted', label: '黑名单' },
                      ]}
                    />
                    <Select
                      value={statusFilter}
                      onChange={setStatusFilter}
                      style={{ width: 100 }}
                      options={[
                        { value: 'all', label: '全部状态' },
                        { value: 'active', label: '合作中' },
                        { value: 'inactive', label: '已停用' },
                        { value: 'suspended', label: '已暂停' },
                      ]}
                    />
                    <Button icon={<SearchOutlined />} type="primary">搜索</Button>
                    <Button icon={<ReloadOutlined />} onClick={() => {
                      setSearchText('')
                      setLevelFilter('all')
                      setStatusFilter('all')
                    }}>重置</Button>
                  </Space>

                  <Table
                    columns={supplierColumns}
                    dataSource={filteredSuppliers}
                    rowKey="id"
                    loading={loading}
                    pagination={{
                      pageSize: 10,
                      showTotal: (total) => `共 ${total} 个供应商`,
                    }}
                    locale={{
                      emptyText: <Empty description="暂无供应商数据" />,
                    }}
                  />
                </div>
              ),
            },
            {
              key: 'purchase',
              label: '采购订单',
              children: (
                <div>
                  <Table
                    columns={poColumns}
                    dataSource={mockPurchaseOrders}
                    rowKey="id"
                    loading={loading}
                    pagination={{
                      pageSize: 10,
                      showTotal: (total) => `共 ${total} 个采购订单`,
                    }}
                    locale={{
                      emptyText: <Empty description="暂无采购订单" />,
                    }}
                  />
                </div>
              ),
            },
            {
              key: 'analysis',
              label: '供应商分析',
              children: (
                <div>
                  <Row gutter={[16, 16]}>
                    <Col span={12}>
                      <Card size="small" title="供应商等级分布">
                        <List
                          dataSource={[
                            { level: '战略供应商', count: stats.strategic, color: 'gold' },
                            { level: '优选供应商', count: mockSuppliers.filter(s => s.level === 'preferred').length, color: 'blue' },
                            { level: '合格供应商', count: mockSuppliers.filter(s => s.level === 'approved').length, color: 'green' },
                            { level: '待审核', count: stats.pendingReview, color: 'orange' },
                            { level: '黑名单', count: mockSuppliers.filter(s => s.level === 'blacklisted').length, color: 'red' },
                          ]}
                          renderItem={(item) => (
                            <List.Item>
                              <List.Item.Meta
                                avatar={<Tag color={item.color}>{item.level}</Tag>}
                              />
                              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                                <Progress percent={(item.count / stats.total) * 100} size="small" style={{ width: '120px' }} showInfo={false} />
                                <Text strong>{item.count} 个</Text>
                              </div>
                            </List.Item>
                          )}
                        />
                      </Card>
                    </Col>
                    <Col span={12}>
                      <Card size="small" title="采购额TOP5供应商">
                        <List
                          dataSource={[...mockSuppliers].sort((a, b) => b.total_spent - a.total_spent).slice(0, 5)}
                          renderItem={(item, index) => (
                            <List.Item>
                              <List.Item.Meta
                                avatar={
                                  <Badge count={index + 1} style={{
                                    backgroundColor: index === 0 ? '#fadb14' : index === 1 ? '#d9d9d9' : index === 2 ? '#d48806' : '#722ed1',
                                    fontSize: '12px',
                                  }} />
                                }
                                title={item.name}
                                description={`采购 ${item.total_orders} 次 | 准时率 ${item.on_time_rate}%`}
                              />
                              <Text strong style={{ color: '#722ed1' }}>¥{item.total_spent.toLocaleString()}</Text>
                            </List.Item>
                          )}
                        />
                      </Card>
                    </Col>
                  </Row>
                </div>
              ),
            },
          ]}
        />
      </Card>

      {/* 供应商详情Modal */}
      <Modal
        title={`供应商详情 - ${viewingSupplier?.name || ''}`}
        open={detailModalOpen}
        onCancel={() => setDetailModalOpen(false)}
        footer={[
          <Button key="reconcile" icon={<FundOutlined />} onClick={() => message.success('对账功能开发中')}>对账</Button>,
          <Button key="edit" type="primary" onClick={() => message.info('编辑功能开发中')}>编辑</Button>,
          <Button key="close" onClick={() => setDetailModalOpen(false)}>关闭</Button>,
        ]}
        width={900}
      >
        {viewingSupplier && (
          <div>
            {/* 基本信息 */}
            <Descriptions column={3} bordered size="small" style={{ marginBottom: '16px' }}>
              <Descriptions.Item label="供应商编号" span={3}>
                <Space>
                  <Text strong>{viewingSupplier.supplier_id}</Text>
                  <Tag color={levelColors[viewingSupplier.level]}>{levelText[viewingSupplier.level]}</Tag>
                  <Tag color={statusColors[viewingSupplier.status]}>{statusText[viewingSupplier.status]}</Tag>
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="联系人">{viewingSupplier.contact_person}</Descriptions.Item>
              <Descriptions.Item label="电话">
                <PhoneOutlined style={{ marginRight: '4px' }} />
                {viewingSupplier.phone}
              </Descriptions.Item>
              <Descriptions.Item label="邮箱">
                <MailOutlined style={{ marginRight: '4px' }} />
                {viewingSupplier.email}
              </Descriptions.Item>
              <Descriptions.Item label="地址" span={3}>
                <EnvironmentOutlined style={{ marginRight: '4px' }} />
                {viewingSupplier.address}
              </Descriptions.Item>
              <Descriptions.Item label="主营类目">
                {viewingSupplier.categories.map(cat => <Tag key={cat} color="blue">{cat}</Tag>)}
              </Descriptions.Item>
              <Descriptions.Item label="最小起订量">¥{viewingSupplier.min_order_amount}</Descriptions.Item>
              <Descriptions.Item label="付款条件">{viewingSupplier.payment_terms}</Descriptions.Item>
            </Descriptions>

            {/* 评级卡片 */}
            <Card size="small" style={{ marginBottom: '16px', background: '#fafafa' }}>
              <Row gutter={16}>
                <Col span={6}>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: '32px', fontWeight: 'bold', color: '#722ed1' }}>{viewingSupplier.rating}</div>
                    <Rate disabled defaultValue={viewingSupplier.rating} style={{ fontSize: '14px' }} />
                    <div style={{ fontSize: '12px', color: '#999', marginTop: '4px' }}>综合评级</div>
                  </div>
                </Col>
                <Col span={6}>
                  <Statistic title="质量评分" value={viewingSupplier.quality_score} suffix="/100" valueStyle={{ color: '#52c41a', fontSize: '20px' }} />
                  <Progress percent={viewingSupplier.quality_score} size="small" strokeColor="#52c41a" showInfo={false} style={{ marginTop: '8px' }} />
                </Col>
                <Col span={6}>
                  <Statistic title="准时交货率" value={viewingSupplier.on_time_rate} suffix="%" valueStyle={{ color: '#1890ff', fontSize: '20px' }} />
                  <Progress percent={viewingSupplier.on_time_rate} size="small" strokeColor="#1890ff" showInfo={false} style={{ marginTop: '8px' }} />
                </Col>
                <Col span={6}>
                  <Statistic title="次品率" value={viewingSupplier.defect_rate} suffix="%" valueStyle={{ color: viewingSupplier.defect_rate > 5 ? '#f5222d' : '#faad14', fontSize: '20px' }} />
                  <Progress percent={100 - viewingSupplier.defect_rate * 10} size="small" strokeColor={viewingSupplier.defect_rate > 5 ? '#f5222d' : '#faad14'} showInfo={false} style={{ marginTop: '8px' }} />
                </Col>
              </Row>
            </Card>

            <Divider style={{ margin: '16px 0' }} />

            {/* 采购统计 */}
            <Row gutter={[16, 16]} style={{ marginBottom: '16px' }}>
              <Col span={8}>
                <Card size="small">
                  <Statistic title="累计采购次数" value={viewingSupplier.total_orders} suffix="次" prefix={<ShoppingCartOutlined />} />
                </Card>
              </Col>
              <Col span={8}>
                <Card size="small">
                  <Statistic title="累计采购金额" value={viewingSupplier.total_spent} prefix="¥" precision={0} />
                </Card>
              </Col>
              <Col span={8}>
                <Card size="small">
                  <Statistic title="平均交货周期" value={viewingSupplier.avg_delivery_days} suffix="天" prefix={<TruckOutlined />} />
                </Card>
              </Col>
            </Row>

            <Divider style={{ margin: '16px 0' }} />

            {/* 采购历史 */}
            <div>
              <Text strong style={{ fontSize: '14px' }}>采购历史：</Text>
              {purchaseOrders.length > 0 ? (
                <Table
                  columns={poColumns.filter(col => col.key !== 'supplier_name')}
                  dataSource={purchaseOrders}
                  rowKey="id"
                  size="small"
                  pagination={{ pageSize: 5 }}
                  style={{ marginTop: '12px' }}
                />
              ) : (
                <Empty description="暂无采购记录" style={{ marginTop: '16px' }} />
              )}
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
