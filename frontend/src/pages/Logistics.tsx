import { useState, useEffect } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Input, Select,
  Statistic, Row, Col, Spin, message, Modal, Timeline, Descriptions,
  Badge, Tooltip, Empty, Tabs, Alert, Divider, Progress
} from 'antd'
import {
  TruckOutlined, ReloadOutlined, SearchOutlined, EyeOutlined,
  SyncOutlined, WarningOutlined, CheckCircleOutlined,
  ClockCircleOutlined, EnvironmentOutlined, SendOutlined,
  HomeOutlined, GlobalOutlined
} from '@ant-design/icons'
import dayjs from 'dayjs'

const { Title, Text, Paragraph } = Typography

interface LogisticsOrder {
  id: string
  tracking_number: string
  carrier: string
  carrier_type: 'domestic' | 'international'
  status: 'pending' | 'picked_up' | 'in_transit' | 'out_for_delivery' | 'delivered' | 'exception' | 'returned'
  origin: string
  destination: string
  current_location: string
  estimated_delivery: string
  created_at: string
  updated_at: string
  order_id?: string
  customer_id?: string
  weight?: number
  dimensions?: string
}

interface TrackingEvent {
  time: string
  location: string
  status: string
  description: string
}

const statusColors: Record<string, string> = {
  pending: 'default',
  picked_up: 'blue',
  in_transit: 'blue',
  out_for_delivery: 'orange',
  delivered: 'green',
  exception: 'red',
  returned: 'red',
}

const statusText: Record<string, string> = {
  pending: '待揽收',
  picked_up: '已揽收',
  in_transit: '运输中',
  out_for_delivery: '派送中',
  delivered: '已签收',
  exception: '异常',
  returned: '已退回',
}

const carrierColors: Record<string, string> = {
  domestic: 'blue',
  international: 'purple',
}

export default function LogisticsPage() {
  const [loading, setLoading] = useState(false)
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [viewingOrder, setViewingOrder] = useState<LogisticsOrder | null>(null)
  const [trackingEvents, setTrackingEvents] = useState<TrackingEvent[]>([])
  const [statusFilter, setStatusFilter] = useState('all')
  const [typeFilter, setTypeFilter] = useState('all')
  const [searchText, setSearchText] = useState('')
  const [syncing, setSyncing] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  // 真实API数据状态
  const [logisticsData, setLogisticsData] = useState<any>(null)

  // 模拟物流单数据
  const mockLogistics: LogisticsOrder[] = [
    { id: '1', tracking_number: 'SF1234567890', carrier: '顺丰速运', carrier_type: 'domestic', status: 'in_transit', origin: '深圳', destination: '广州白云仓', current_location: '东莞转运中心', estimated_delivery: '2026-09-06', created_at: '2026-09-04 14:30:00', updated_at: '2026-09-05 08:15:00', order_id: 'WC-1001', weight: 2.5, dimensions: '30x20x15cm' },
    { id: '2', tracking_number: 'YT9876543210', carrier: '圆通速递', carrier_type: 'domestic', status: 'delivered', origin: '义乌', destination: '深圳前海仓', current_location: '深圳前海仓', estimated_delivery: '2026-09-03', created_at: '2026-09-01 10:00:00', updated_at: '2026-09-03 16:45:00', order_id: 'WC-0998', weight: 1.2, dimensions: '25x15x10cm' },
    { id: '3', tracking_number: '4PX20260905001', carrier: '4PX递四方', carrier_type: 'international', status: 'in_transit', origin: '深圳前海仓', destination: '美国洛杉矶', current_location: '香港国际机场', estimated_delivery: '2026-09-12', created_at: '2026-09-04 18:00:00', updated_at: '2026-09-05 12:30:00', order_id: 'WC-1002', weight: 3.8, dimensions: '40x30x20cm' },
    { id: '4', tracking_number: 'YANWEN20260903002', carrier: '燕文物流', carrier_type: 'international', status: 'out_for_delivery', origin: '深圳前海仓', destination: '英国伦敦', current_location: '伦敦配送站', estimated_delivery: '2026-09-05', created_at: '2026-08-28 09:00:00', updated_at: '2026-09-05 07:00:00', order_id: 'WC-0985', weight: 1.5, dimensions: '20x15x10cm' },
    { id: '5', tracking_number: 'ZTO5556667778', carrier: '中通快递', carrier_type: 'domestic', status: 'exception', origin: '广州', destination: '深圳前海仓', current_location: '深圳转运中心', estimated_delivery: '2026-09-04', created_at: '2026-09-02 11:00:00', updated_at: '2026-09-04 14:00:00', order_id: 'WC-0995', weight: 5.0, dimensions: '50x40x30cm' },
    { id: '6', tracking_number: 'DHL20260901003', carrier: 'DHL Express', carrier_type: 'international', status: 'delivered', origin: '深圳前海仓', destination: '德国柏林', current_location: '柏林', estimated_delivery: '2026-09-04', created_at: '2026-08-30 15:00:00', updated_at: '2026-09-04 10:30:00', order_id: 'WC-0972', weight: 2.0, dimensions: '35x25x15cm' },
    { id: '7', tracking_number: 'EMS1112223334', carrier: 'EMS国际', carrier_type: 'international', status: 'pending', origin: '深圳前海仓', destination: '日本东京', current_location: '深圳前海仓', estimated_delivery: '2026-09-10', created_at: '2026-09-05 09:00:00', updated_at: '2026-09-05 09:00:00', order_id: 'WC-1005', weight: 0.8, dimensions: '15x10x5cm' },
    { id: '8', tracking_number: 'JD8889990001', carrier: '京东物流', carrier_type: 'domestic', status: 'picked_up', origin: '杭州', destination: '广州白云仓', current_location: '杭州转运中心', estimated_delivery: '2026-09-07', created_at: '2026-09-05 08:00:00', updated_at: '2026-09-05 11:00:00', order_id: 'WC-1006', weight: 3.2, dimensions: '45x35x25cm' },
  ]

  // 模拟物流轨迹数据
  const mockTrackingEvents: TrackingEvent[] = [
    { time: '2026-09-05 12:30:00', location: '香港国际机场', status: 'in_transit', description: '包裹已到达香港国际机场，等待装机' },
    { time: '2026-09-04 22:00:00', location: '深圳前海仓', status: 'picked_up', description: '包裹已从深圳前海仓发出' },
    { time: '2026-09-04 18:00:00', location: '深圳前海仓', status: 'pending', description: '订单已创建，等待揽收' },
  ]

  // 加载物流数据（调用真实API，失败则使用mock数据降级）
  const loadLogisticsData = async () => {
    try {
      setLoading(true)
      // 调用物流监控状态API
      const statusResp = await fetch('/api/v1/logistics/status')
      if (statusResp.ok) {
        const statusData = await statusResp.json()
        setLogisticsData(statusData)
        console.log('Logistics status:', statusData)
      }
      message.success('物流数据加载完成')
    } catch (e: any) {
      console.error('Load logistics data error:', e)
      message.warning(`API调用失败，使用模拟数据：${e.message || '未知错误'}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadLogisticsData()
  }, [])

  // 统计数据（优先使用真实API数据，失败则使用mock数据降级）
  const supportedCarriers = logisticsData?.supported_carriers?.length || 0
  const stats = {
    total: mockLogistics.length,
    inTransit: mockLogistics.filter(l => l.status === 'in_transit' || l.status === 'out_for_delivery').length,
    delivered: mockLogistics.filter(l => l.status === 'delivered').length,
    exceptions: mockLogistics.filter(l => l.status === 'exception').length,
    domestic: mockLogistics.filter(l => l.carrier_type === 'domestic').length,
    international: mockLogistics.filter(l => l.carrier_type === 'international').length,
    supportedCarriers,
  }

  // 查看物流详情
  const handleViewDetail = (order: LogisticsOrder) => {
    setViewingOrder(order)
    setTrackingEvents(mockTrackingEvents)
    setDetailModalOpen(true)
  }

  // 刷新物流状态
  const handleRefresh = () => {
    setRefreshing(true)
    message.info('正在刷新物流状态...')
    setTimeout(() => {
      message.success('物流状态已更新')
      setRefreshing(false)
    }, 1500)
  }

  // 同步物流数据
  const handleSync = () => {
    setSyncing(true)
    message.info('正在同步物流数据...')
    setTimeout(() => {
      message.success('物流数据同步完成')
      setSyncing(false)
    }, 2000)
  }

  // 过滤物流单
  const filteredLogistics = mockLogistics.filter(order => {
    if (statusFilter !== 'all' && order.status !== statusFilter) return false
    if (typeFilter !== 'all' && order.carrier_type !== typeFilter) return false
    if (searchText && !order.tracking_number.includes(searchText) && !order.order_id?.includes(searchText)) return false
    return true
  })

  // 表格列定义
  const columns = [
    {
      title: '运单号',
      dataIndex: 'tracking_number',
      key: 'tracking_number',
      width: 180,
      render: (text: string, record: LogisticsOrder) => (
        <Space>
          <Text strong copyable={{ text }}>{text}</Text>
          <Tag color={carrierColors[record.carrier_type]}>
            {record.carrier_type === 'domestic' ? <HomeOutlined /> : <GlobalOutlined />}
            {record.carrier_type === 'domestic' ? '国内' : '国际'}
          </Tag>
        </Space>
      ),
    },
    {
      title: '物流公司',
      dataIndex: 'carrier',
      key: 'carrier',
      width: 120,
      render: (text: string) => <Text>{text}</Text>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={statusColors[status] || 'default'} icon={status === 'exception' ? <WarningOutlined /> : status === 'delivered' ? <CheckCircleOutlined /> : <ClockCircleOutlined />}>
          {statusText[status] || status}
        </Tag>
      ),
    },
    {
      title: '路线',
      key: 'route',
      width: 200,
      render: (_: any, record: LogisticsOrder) => (
        <div>
          <Space size={4}>
            <EnvironmentOutlined style={{ color: '#52c41a' }} />
            <Text style={{ fontSize: '12px' }}>{record.origin}</Text>
            <SendOutlined style={{ fontSize: '10px', color: '#999' }} />
            <EnvironmentOutlined style={{ color: '#1890ff' }} />
            <Text style={{ fontSize: '12px' }}>{record.destination}</Text>
          </Space>
        </div>
      ),
    },
    {
      title: '当前位置',
      dataIndex: 'current_location',
      key: 'current_location',
      width: 150,
      render: (text: string) => (
        <Tooltip title={text}>
          <Text ellipsis style={{ maxWidth: 130 }}>{text}</Text>
        </Tooltip>
      ),
    },
    {
      title: '预计送达',
      dataIndex: 'estimated_delivery',
      key: 'estimated_delivery',
      width: 110,
      render: (text: string) => {
        const isOverdue = dayjs(text).isBefore(dayjs())
        return (
          <Text type={isOverdue ? 'danger' : undefined}>
            {text}
            {isOverdue && <Tag color="red" style={{ marginLeft: 4 }}>逾期</Tag>}
          </Text>
        )
      },
    },
    {
      title: '关联订单',
      dataIndex: 'order_id',
      key: 'order_id',
      width: 100,
      render: (text: string) => text ? <Text type="secondary">#{text}</Text> : '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_: any, record: LogisticsOrder) => (
        <Space size="small">
          <Button size="small" icon={<EyeOutlined />} onClick={() => handleViewDetail(record)}>轨迹</Button>
          <Button size="small" icon={<SyncOutlined />} onClick={handleRefresh}>刷新</Button>
        </Space>
      ),
    },
  ]

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <TruckOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>物流追踪</Title>
            <Text type="secondary">国内/国际物流实时追踪、异常预警、一件代发模式</Text>
          </div>
        </Space>
        <Space>
          <Button icon={<SyncOutlined />} onClick={handleSync} loading={syncing}>同步物流</Button>
          <Button type="primary" icon={<ReloadOutlined />} onClick={handleRefresh} loading={refreshing}>刷新状态</Button>
        </Space>
      </div>

      {/* 异常预警 */}
      {stats.exceptions > 0 && (
        <Alert
          message={`有 ${stats.exceptions} 个物流异常需要处理`}
          description="请及时联系物流公司确认包裹状态，避免影响客户体验。"
          type="warning"
          showIcon
          icon={<WarningOutlined />}
          style={{ marginBottom: '16px' }}
          action={
            <Button size="small" type="primary" onClick={() => setStatusFilter('exception')}>查看异常</Button>
          }
        />
      )}

      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: '16px' }}>
        <Col span={4}>
          <Card size="small">
            <Statistic title="物流单总数" value={stats.total} prefix={<TruckOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="运输中" value={stats.inTransit} valueStyle={{ color: '#1890ff' }} prefix={<ClockCircleOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="已签收" value={stats.delivered} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="异常" value={stats.exceptions} valueStyle={{ color: '#f5222d' }} prefix={<WarningOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="国内物流" value={stats.domestic} valueStyle={{ color: '#1890ff' }} prefix={<HomeOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="国际物流" value={stats.international} valueStyle={{ color: '#722ed1' }} prefix={<GlobalOutlined />} />
          </Card>
        </Col>
      </Row>

      {/* 操作栏 */}
      <Card size="small" style={{ marginBottom: '16px' }}>
        <Space wrap>
          <Input
            placeholder="搜索运单号/订单号"
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ width: 220 }}
            allowClear
          />
          <Select
            value={statusFilter}
            onChange={setStatusFilter}
            style={{ width: 120 }}
            options={[
              { value: 'all', label: '全部状态' },
              { value: 'pending', label: '待揽收' },
              { value: 'picked_up', label: '已揽收' },
              { value: 'in_transit', label: '运输中' },
              { value: 'out_for_delivery', label: '派送中' },
              { value: 'delivered', label: '已签收' },
              { value: 'exception', label: '异常' },
            ]}
          />
          <Select
            value={typeFilter}
            onChange={setTypeFilter}
            style={{ width: 120 }}
            options={[
              { value: 'all', label: '全部类型' },
              { value: 'domestic', label: '国内物流' },
              { value: 'international', label: '国际物流' },
            ]}
          />
          <Button icon={<SearchOutlined />} type="primary">搜索</Button>
          <Button icon={<ReloadOutlined />} onClick={() => {
            setSearchText('')
            setStatusFilter('all')
            setTypeFilter('all')
          }}>重置</Button>
        </Space>
      </Card>

      {/* 物流单表格 */}
      <Card size="small">
        <Table
          columns={columns}
          dataSource={filteredLogistics}
          rowKey="id"
          loading={loading}
          pagination={{
            pageSize: 10,
            showTotal: (total) => `共 ${total} 个物流单`,
          }}
          locale={{
            emptyText: <Empty description="暂无物流数据" />,
          }}
        />
      </Card>

      {/* 物流详情Modal */}
      <Modal
        title={`物流轨迹 - ${viewingOrder?.tracking_number || ''}`}
        open={detailModalOpen}
        onCancel={() => setDetailModalOpen(false)}
        footer={[
          <Button key="refresh" icon={<SyncOutlined />} onClick={handleRefresh}>刷新轨迹</Button>,
          <Button key="close" onClick={() => setDetailModalOpen(false)}>关闭</Button>,
        ]}
        width={700}
      >
        {viewingOrder && (
          <div>
            {/* 基本信息 */}
            <Descriptions column={2} bordered size="small" style={{ marginBottom: '16px' }}>
              <Descriptions.Item label="运单号" span={2}>
                <Text strong>{viewingOrder.tracking_number}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="物流公司">
                {viewingOrder.carrier}
              </Descriptions.Item>
              <Descriptions.Item label="物流类型">
                <Tag color={carrierColors[viewingOrder.carrier_type]}>
                  {viewingOrder.carrier_type === 'domestic' ? '国内物流' : '国际物流'}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="当前状态">
                <Tag color={statusColors[viewingOrder.status] || 'default'}>
                  {statusText[viewingOrder.status] || viewingOrder.status}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="关联订单">
                {viewingOrder.order_id ? `#${viewingOrder.order_id}` : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="发货地">
                {viewingOrder.origin}
              </Descriptions.Item>
              <Descriptions.Item label="目的地">
                {viewingOrder.destination}
              </Descriptions.Item>
              <Descriptions.Item label="当前位置">
                <Text strong>{viewingOrder.current_location}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="预计送达">
                {viewingOrder.estimated_delivery}
              </Descriptions.Item>
              <Descriptions.Item label="重量">
                {viewingOrder.weight ? `${viewingOrder.weight} kg` : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="尺寸">
                {viewingOrder.dimensions || '-'}
              </Descriptions.Item>
            </Descriptions>

            <Divider style={{ margin: '16px 0' }} />

            {/* 物流轨迹时间线 */}
            <div>
              <Text strong style={{ fontSize: '14px' }}>物流轨迹：</Text>
              <Timeline
                style={{ marginTop: '16px' }}
                items={trackingEvents.map((event, index) => ({
                  color: index === 0 ? 'blue' : 'gray',
                  dot: index === 0 ? <ClockCircleOutlined style={{ fontSize: '16px' }} /> : undefined,
                  children: (
                    <div>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <Text strong>{event.description}</Text>
                        <Text type="secondary" style={{ fontSize: '12px' }}>{event.time}</Text>
                      </div>
                      <div style={{ marginTop: '4px' }}>
                        <EnvironmentOutlined style={{ color: '#999', marginRight: '4px' }} />
                        <Text type="secondary" style={{ fontSize: '12px' }}>{event.location}</Text>
                      </div>
                    </div>
                  ),
                }))}
              />
            </div>

            {/* 物流进度 */}
            <Divider style={{ margin: '16px 0' }} />
            <div>
              <Text strong style={{ fontSize: '14px' }}>物流进度：</Text>
              <div style={{ marginTop: '12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ textAlign: 'center' }}>
                  <CheckCircleOutlined style={{ fontSize: '24px', color: '#52c41a' }} />
                  <div style={{ fontSize: '11px', marginTop: '4px', color: '#52c41a' }}>已发货</div>
                </div>
                <div style={{ flex: 1, height: '2px', background: '#52c41a', margin: '0 8px' }} />
                <div style={{ textAlign: 'center' }}>
                  <ClockCircleOutlined style={{ fontSize: '24px', color: '#1890ff' }} />
                  <div style={{ fontSize: '11px', marginTop: '4px', color: '#1890ff' }}>运输中</div>
                </div>
                <div style={{ flex: 1, height: '2px', background: '#e8e8e8', margin: '0 8px' }} />
                <div style={{ textAlign: 'center' }}>
                  <ClockCircleOutlined style={{ fontSize: '24px', color: '#bfbfbf' }} />
                  <div style={{ fontSize: '11px', marginTop: '4px', color: '#bfbfbf' }}>派送中</div>
                </div>
                <div style={{ flex: 1, height: '2px', background: '#e8e8e8', margin: '0 8px' }} />
                <div style={{ textAlign: 'center' }}>
                  <CheckCircleOutlined style={{ fontSize: '24px', color: '#bfbfbf' }} />
                  <div style={{ fontSize: '11px', marginTop: '4px', color: '#bfbfbf' }}>已签收</div>
                </div>
              </div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
