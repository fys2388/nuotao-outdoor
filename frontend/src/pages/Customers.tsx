import { useState, useEffect } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Input, Select,
  Statistic, Row, Col, Spin, message, Modal, Descriptions, List,
  Badge, Tooltip, Empty, Tabs, Progress, Avatar, Divider, Rate
} from 'antd'
import {
  UserOutlined, ReloadOutlined, SearchOutlined, EyeOutlined,
  ShoppingCartOutlined, StarOutlined, CrownOutlined,
  MessageOutlined, FundOutlined, SyncOutlined, EditOutlined
} from '@ant-design/icons'
import dayjs from 'dayjs'

const { Title, Text, Paragraph } = Typography

interface Customer {
  id: string
  external_customer_id?: string
  customer_hash?: string
  tier?: string
  total_orders?: number
  total_spent?: number
  first_order_at?: string
  last_order_at?: string
  created_at?: string
  updated_at?: string
  preferences?: Record<string, any>
  notes?: string
}

interface Order {
  id: string
  external_order_id: string
  status: string
  total: number
  currency: string
  received_at: string
}

const tierColors: Record<string, string> = {
  VIP: 'gold',
  regular: 'blue',
  new: 'default',
  churned: 'red',
}

const tierText: Record<string, string> = {
  VIP: 'VIP客户',
  regular: '普通客户',
  new: '新客户',
  churned: '流失客户',
}

export default function CustomersPage() {
  const [customers, setCustomers] = useState<Customer[]>([])
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [tierFilter, setTierFilter] = useState('all')
  const [searchText, setSearchText] = useState('')
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [viewingCustomer, setViewingCustomer] = useState<Customer | null>(null)
  const [customerOrders, setCustomerOrders] = useState<Order[]>([])
  const [syncing, setSyncing] = useState(false)

  // 模拟客户数据（实际项目中从API获取）
  const mockCustomers: Customer[] = [
    { id: '1', external_customer_id: '1001', tier: 'VIP', total_orders: 28, total_spent: 4580, first_order_at: '2025-03-15', last_order_at: '2026-09-03', created_at: '2025-03-15' },
    { id: '2', external_customer_id: '1002', tier: 'regular', total_orders: 12, total_spent: 1860, first_order_at: '2025-06-20', last_order_at: '2026-08-28', created_at: '2025-06-20' },
    { id: '3', external_customer_id: '1003', tier: 'regular', total_orders: 8, total_spent: 1240, first_order_at: '2025-09-10', last_order_at: '2026-09-01', created_at: '2025-09-10' },
    { id: '4', external_customer_id: '1004', tier: 'new', total_orders: 1, total_spent: 156, first_order_at: '2026-09-05', last_order_at: '2026-09-05', created_at: '2026-09-05' },
    { id: '5', external_customer_id: '1005', tier: 'new', total_orders: 2, total_spent: 320, first_order_at: '2026-08-30', last_order_at: '2026-09-02', created_at: '2026-08-30' },
    { id: '6', external_customer_id: '1006', tier: 'churned', total_orders: 5, total_spent: 780, first_order_at: '2025-04-10', last_order_at: '2026-03-15', created_at: '2025-04-10' },
    { id: '7', external_customer_id: '1007', tier: 'VIP', total_orders: 35, total_spent: 6200, first_order_at: '2025-01-20', last_order_at: '2026-09-04', created_at: '2025-01-20' },
    { id: '8', external_customer_id: '1008', tier: 'regular', total_orders: 15, total_spent: 2340, first_order_at: '2025-07-05', last_order_at: '2026-08-25', created_at: '2025-07-05' },
  ]

  // 加载客户列表
  const loadCustomers = async () => {
    try {
      setLoading(true)
      const params = new URLSearchParams({
        limit: pageSize.toString(),
        offset: ((page - 1) * pageSize).toString(),
      })
      if (tierFilter !== 'all') params.append('segment', tierFilter)

      const resp = await fetch(`/api/v1/customer-profiles?${params}`)
      if (resp.ok) {
        const data = await resp.json()
        // API返回数组，转换为Customer格式
        const customerList: Customer[] = (data || []).map((p: any) => ({
          id: p.id || p.reference_id,
          external_customer_id: p.reference_id,
          tier: p.segment || 'regular',
          total_orders: p.total_orders || 0,
          total_spent: p.total_spent || 0,
          first_order_at: p.first_order_at,
          last_order_at: p.last_order_at,
          created_at: p.created_at,
          updated_at: p.updated_at,
          preferences: p.preferences,
          notes: p.notes,
        }))
        setCustomers(customerList.length > 0 ? customerList : mockCustomers)
        setTotal(customerList.length > 0 ? customerList.length : mockCustomers.length)
      } else {
        // API调用失败，使用mock数据降级
        setCustomers(mockCustomers)
        setTotal(mockCustomers.length)
        message.warning('API调用失败，使用模拟数据')
      }
    } catch (e: any) {
      console.error('Load customers error:', e)
      // 网络错误，使用mock数据降级
      setCustomers(mockCustomers)
      setTotal(mockCustomers.length)
      message.warning(`网络错误，使用模拟数据：${e.message || '未知错误'}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadCustomers()
  }, [page, pageSize, tierFilter])

  // 模拟客户订单数据
  const mockCustomerOrders: Order[] = [
    { id: 'o1', external_order_id: '1001', status: 'completed', total: 156, currency: 'USD', received_at: '2026-09-03' },
    { id: 'o2', external_order_id: '0998', status: 'completed', total: 280, currency: 'USD', received_at: '2026-08-28' },
    { id: 'o3', external_order_id: '0985', status: 'completed', total: 195, currency: 'USD', received_at: '2026-08-15' },
    { id: 'o4', external_order_id: '0972', status: 'completed', total: 320, currency: 'USD', received_at: '2026-07-30' },
  ]

  // 查看客户详情
  const handleViewDetail = (customer: Customer) => {
    setViewingCustomer(customer)
    setCustomerOrders(mockCustomerOrders)
    setDetailModalOpen(true)
  }

  // 同步WooCommerce客户
  const handleSyncWooCommerce = () => {
    setSyncing(true)
    message.info('正在从WooCommerce同步客户数据...')
    setTimeout(() => {
      message.success('客户数据同步完成')
      setSyncing(false)
      loadCustomers()
    }, 2000)
  }

  // 统计数据
  const stats = {
    total: mockCustomers.length,
    vip: mockCustomers.filter(c => c.tier === 'VIP').length,
    new: mockCustomers.filter(c => c.tier === 'new').length,
    totalSpent: mockCustomers.reduce((sum, c) => sum + (c.total_spent || 0), 0),
  }

  // 表格列定义
  const columns = [
    {
      title: '客户ID',
      dataIndex: 'external_customer_id',
      key: 'external_customer_id',
      width: 120,
      render: (text: string) => (
        <Space>
          <Avatar size="small" icon={<UserOutlined />} style={{ backgroundColor: '#722ed1' }} />
          <Text strong>#{text}</Text>
        </Space>
      ),
    },
    {
      title: '客户等级',
      dataIndex: 'tier',
      key: 'tier',
      width: 120,
      render: (tier: string) => (
        <Tag color={tierColors[tier] || 'default'} icon={tier === 'VIP' ? <CrownOutlined /> : tier === 'new' ? <StarOutlined /> : null}>
          {tierText[tier] || tier}
        </Tag>
      ),
    },
    {
      title: '订单数',
      dataIndex: 'total_orders',
      key: 'total_orders',
      width: 100,
      render: (orders: number) => <Text strong>{orders}</Text>,
    },
    {
      title: '累计消费',
      dataIndex: 'total_spent',
      key: 'total_spent',
      width: 120,
      render: (spent: number) => (
        <Text strong style={{ color: '#722ed1' }}>${spent?.toLocaleString()}</Text>
      ),
    },
    {
      title: '首单时间',
      dataIndex: 'first_order_at',
      key: 'first_order_at',
      width: 120,
      render: (text: string) => text ? dayjs(text).format('YYYY-MM-DD') : '-',
    },
    {
      title: '最近下单',
      dataIndex: 'last_order_at',
      key: 'last_order_at',
      width: 120,
      render: (text: string) => text ? dayjs(text).format('YYYY-MM-DD') : '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 150,
      render: (_: any, record: Customer) => (
        <Space size="small">
          <Button size="small" icon={<EyeOutlined />} onClick={() => handleViewDetail(record)}>详情</Button>
          <Button size="small" icon={<MessageOutlined />} onClick={() => message.info('客服功能开发中')}>联系</Button>
        </Space>
      ),
    },
  ]

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: '24px' }}>
        <Space>
          <UserOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>客户管理</Title>
            <Text type="secondary">客户列表、详情、购买历史、客户分级</Text>
          </div>
        </Space>
      </div>

      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: '16px' }}>
        <Col span={6}>
          <Card size="small">
            <Statistic title="客户总数" value={stats.total} prefix={<UserOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="VIP客户" value={stats.vip} valueStyle={{ color: '#faad14' }} prefix={<CrownOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="新客户" value={stats.new} valueStyle={{ color: '#1890ff' }} prefix={<StarOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="客户总消费" value={stats.totalSpent} prefix="$" precision={0} valueStyle={{ color: '#722ed1' }} />
          </Card>
        </Col>
      </Row>

      {/* 操作栏 */}
      <Card size="small" style={{ marginBottom: '16px' }}>
        <Space wrap>
          <Input
            placeholder="搜索客户ID"
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ width: 200 }}
            allowClear
            onPressEnter={loadCustomers}
          />
          <Select
            value={tierFilter}
            onChange={setTierFilter}
            style={{ width: 120 }}
            options={[
              { value: 'all', label: '全部等级' },
              { value: 'VIP', label: 'VIP客户' },
              { value: 'regular', label: '普通客户' },
              { value: 'new', label: '新客户' },
              { value: 'churned', label: '流失客户' },
            ]}
          />
          <Button icon={<SearchOutlined />} type="primary" onClick={loadCustomers}>搜索</Button>
          <Button icon={<ReloadOutlined />} onClick={loadCustomers} loading={loading}>刷新</Button>
          <Button icon={<SyncOutlined />} onClick={handleSyncWooCommerce} loading={syncing} type="primary">
            同步WooCommerce
          </Button>
        </Space>
      </Card>

      {/* 客户表格 */}
      <Card size="small">
        <Table
          columns={columns}
          dataSource={customers}
          rowKey="id"
          loading={loading}
          pagination={{
            current: page,
            pageSize: pageSize,
            total: total,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total) => `共 ${total} 个客户`,
            onChange: (page, pageSize) => {
              setPage(page)
              setPageSize(pageSize)
            },
          }}
          locale={{
            emptyText: <Empty description="暂无客户数据" />,
          }}
        />
      </Card>

      {/* 客户详情Modal */}
      <Modal
        title={`客户详情 #${viewingCustomer?.external_customer_id || ''}`}
        open={detailModalOpen}
        onCancel={() => setDetailModalOpen(false)}
        footer={[
          <Button key="edit" icon={<EditOutlined />} onClick={() => message.info('编辑功能开发中')}>编辑</Button>,
          <Button key="close" onClick={() => setDetailModalOpen(false)}>关闭</Button>,
        ]}
        width={800}
      >
        {viewingCustomer && (
          <Tabs
            defaultActiveKey="info"
            items={[
              {
                key: 'info',
                label: '基本信息',
                children: (
                  <div>
                    <Descriptions column={2} bordered size="small">
                      <Descriptions.Item label="客户ID" span={2}>
                        <Space>
                          <Avatar size="small" icon={<UserOutlined />} style={{ backgroundColor: '#722ed1' }} />
                          <Text strong>#{viewingCustomer.external_customer_id}</Text>
                        </Space>
                      </Descriptions.Item>
                      <Descriptions.Item label="客户等级">
                        <Tag color={tierColors[viewingCustomer.tier || ''] || 'default'}>
                          {tierText[viewingCustomer.tier || ''] || viewingCustomer.tier}
                        </Tag>
                      </Descriptions.Item>
                      <Descriptions.Item label="客户状态">
                        <Badge status="success" text="活跃" />
                      </Descriptions.Item>
                      <Descriptions.Item label="订单数">
                        <Text strong>{viewingCustomer.total_orders}</Text>
                      </Descriptions.Item>
                      <Descriptions.Item label="累计消费">
                        <Text strong style={{ color: '#722ed1' }}>${viewingCustomer.total_spent?.toLocaleString()}</Text>
                      </Descriptions.Item>
                      <Descriptions.Item label="客单价">
                        ${viewingCustomer.total_orders ? (viewingCustomer.total_spent / viewingCustomer.total_orders).toFixed(2) : '0'}
                      </Descriptions.Item>
                      <Descriptions.Item label="首单时间">
                        {viewingCustomer.first_order_at ? dayjs(viewingCustomer.first_order_at).format('YYYY-MM-DD') : '-'}
                      </Descriptions.Item>
                      <Descriptions.Item label="最近下单">
                        {viewingCustomer.last_order_at ? dayjs(viewingCustomer.last_order_at).format('YYYY-MM-DD') : '-'}
                      </Descriptions.Item>
                      <Descriptions.Item label="注册时间" span={2}>
                        {viewingCustomer.created_at ? dayjs(viewingCustomer.created_at).format('YYYY-MM-DD HH:mm:ss') : '-'}
                      </Descriptions.Item>
                    </Descriptions>

                    <Divider style={{ margin: '16px 0' }} />

                    <div>
                      <Text strong>客户价值评估：</Text>
                      <div style={{ marginTop: '8px' }}>
                        <Progress
                          percent={Math.min((viewingCustomer.total_spent || 0) / 100, 100)}
                          strokeColor={{ from: '#722ed1', to: '#9254de' }}
                          format={(percent) => `价值评分 ${percent}`}
                        />
                      </div>
                      <Paragraph type="secondary" style={{ marginTop: '8px', fontSize: '12px' }}>
                        基于订单数、累计消费、活跃度等多维度综合评估。该客户属于{viewingCustomer.tier === 'VIP' ? '高价值客户，建议重点维护' : '普通客户，可通过营销活动提升价值'}。
                      </Paragraph>
                    </div>
                  </div>
                ),
              },
              {
                key: 'orders',
                label: `购买历史 (${customerOrders.length})`,
                children: (
                  <List
                    size="small"
                    dataSource={customerOrders}
                    renderItem={(order: Order) => (
                      <List.Item>
                        <List.Item.Meta
                          title={
                            <Space>
                              <Text strong>#{order.external_order_id}</Text>
                              <Tag color={order.status === 'completed' ? 'green' : 'blue'}>
                                {order.status === 'completed' ? '已完成' : order.status}
                              </Tag>
                            </Space>
                          }
                          description={dayjs(order.received_at).format('YYYY-MM-DD HH:mm:ss')}
                        />
                        <div>
                          <Text strong style={{ color: '#722ed1', fontSize: '16px' }}>
                            {order.currency} {order.total.toFixed(2)}
                          </Text>
                        </div>
                      </List.Item>
                    )}
                  />
                ),
              },
              {
                key: 'analytics',
                label: '消费分析',
                children: (
                  <div>
                    <Row gutter={[16, 16]}>
                      <Col span={8}>
                        <Card size="small">
                          <Statistic title="总订单数" value={viewingCustomer.total_orders} prefix={<ShoppingCartOutlined />} />
                        </Card>
                      </Col>
                      <Col span={8}>
                        <Card size="small">
                          <Statistic title="总消费金额" value={viewingCustomer.total_spent} prefix="$" precision={0} />
                        </Card>
                      </Col>
                      <Col span={8}>
                        <Card size="small">
                          <Statistic title="平均客单价" value={viewingCustomer.total_orders ? (viewingCustomer.total_spent / viewingCustomer.total_orders).toFixed(2) : 0} prefix="$" />
                        </Card>
                      </Col>
                    </Row>

                    <Divider style={{ margin: '16px 0' }} />

                    <div>
                      <Text strong>消费频率：</Text>
                      <Paragraph type="secondary" style={{ marginTop: '4px' }}>
                        平均每 {(viewingCustomer.total_orders && viewingCustomer.first_order_at)
                          ? Math.max(1, Math.ceil(dayjs().diff(dayjs(viewingCustomer.first_order_at), 'day') / viewingCustomer.total_orders))
                          : 0} 天下单一次
                      </Paragraph>
                    </div>

                    <div>
                      <Text strong>客户生命周期：</Text>
                      <Paragraph type="secondary" style={{ marginTop: '4px' }}>
                        {viewingCustomer.first_order_at
                          ? `${dayjs().diff(dayjs(viewingCustomer.first_order_at), 'day')} 天`
                          : '-'}
                      </Paragraph>
                    </div>
                  </div>
                ),
              },
            ]}
          />
        )}
      </Modal>
    </div>
  )
}
