import { useState, useEffect } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Input, Select,
  Statistic, Row, Col, Spin, message, Modal, Descriptions, List,
  Badge, Tooltip, Empty, Tabs, Timeline, Divider, Alert,
  Steps, Form, InputNumber, Radio, Progress, Popconfirm
} from 'antd'
import {
  DatabaseOutlined, ReloadOutlined, SearchOutlined,
  EyeOutlined, PlusOutlined, EditOutlined,
  TruckOutlined, CheckCircleOutlined, WarningOutlined,
  SyncOutlined, ClockCircleOutlined, ShopOutlined,
  DollarOutlined, InboxOutlined, CopyOutlined,
  GlobalOutlined, HomeOutlined, ExportOutlined,
  ImportOutlined, SwapOutlined, EnvironmentOutlined
} from '@ant-design/icons'

const { Title, Text, Paragraph } = Typography

interface Warehouse {
  id: string
  name: string
  code: string
  type: 'domestic' | 'overseas' | 'forwarding'
  address: string
  country: string
  city: string
  manager: string
  phone: string
  status: 'active' | 'inactive' | 'maintenance'
  total_sku: number
  total_stock: number
  used_capacity: number
  total_capacity: number
  created_at: string
}

interface TransferOrder {
  id: string
  transfer_number: string
  from_warehouse: string
  to_warehouse: string
  items: Array<{ product_name: string; sku: string; quantity: number }>
  total_quantity: number
  status: 'draft' | 'pending' | 'shipped' | 'received' | 'completed' | 'cancelled'
  created_at: string
  shipped_at?: string
  received_at?: string
  tracking_number?: string
  logistics_company?: string
  creator: string
  notes?: string
}

interface LogisticsProvider {
  id: string
  name: string
  code: string
  type: 'domestic' | 'international' | 'express' | 'special_line'
  channels: string[]
  coverage: string[]
  avg_delivery_days: number
  success_rate: number
  price_per_kg: number
  status: 'active' | 'inactive'
  api_connected: boolean
  total_shipments: number
  rating: number
}

const warehouseTypeColors: Record<string, string> = {
  domestic: 'blue',
  overseas: 'green',
  forwarding: 'orange',
}

const warehouseTypeText: Record<string, string> = {
  domestic: '国内仓',
  overseas: '海外仓',
  forwarding: '货代仓',
}

const transferStatusColors: Record<string, string> = {
  draft: 'default',
  pending: 'orange',
  shipped: 'cyan',
  received: 'blue',
  completed: 'green',
  cancelled: 'red',
}

const transferStatusText: Record<string, string> = {
  draft: '草稿',
  pending: '待发货',
  shipped: '运输中',
  received: '已收货',
  completed: '已完成',
  cancelled: '已取消',
}

const logisticsTypeColors: Record<string, string> = {
  domestic: 'blue',
  international: 'green',
  express: 'purple',
  special_line: 'orange',
}

const logisticsTypeText: Record<string, string> = {
  domestic: '国内物流',
  international: '国际物流',
  express: '快递',
  special_line: '专线',
}

export default function WarehousePage() {
  const [activeTab, setActiveTab] = useState('warehouses')
  const [loading, setLoading] = useState(false)
  const [warehouseDetailOpen, setWarehouseDetailOpen] = useState(false)
  const [transferDetailOpen, setTransferDetailOpen] = useState(false)
  const [createTransferOpen, setCreateTransferOpen] = useState(false)
  const [viewingWarehouse, setViewingWarehouse] = useState<Warehouse | null>(null)
  const [viewingTransfer, setViewingTransfer] = useState<TransferOrder | null>(null)
  const [warehouseStatusFilter, setWarehouseStatusFilter] = useState('all')
  const [transferStatusFilter, setTransferStatusFilter] = useState('all')
  const [searchText, setSearchText] = useState('')
  // 真实API数据状态
  const [warehouseData, setWarehouseData] = useState<any>(null)
  const [transferForm] = Form.useForm()

  // 模拟仓库数据
  const mockWarehouses: Warehouse[] = [
    { id: '1', name: '深圳宝安仓', code: 'SZ-BA-01', type: 'domestic', address: '深圳市宝安区西乡街道XX路XX号', country: '中国', city: '深圳', manager: '王经理', phone: '138****1234', status: 'active', total_sku: 156, total_stock: 8520, used_capacity: 68, total_capacity: 10000, created_at: '2025-01-15' },
    { id: '2', name: '义乌小商品仓', code: 'YW-SP-01', type: 'domestic', address: '义乌市国际商贸城XX区XX号', country: '中国', city: '义乌', manager: '李经理', phone: '139****5678', status: 'active', total_sku: 89, total_stock: 12300, used_capacity: 82, total_capacity: 15000, created_at: '2025-03-20' },
    { id: '3', name: '广州货代仓', code: 'GZ-FW-01', type: 'forwarding', address: '广州市白云区XX物流园XX栋', country: '中国', city: '广州', manager: '张经理', phone: '137****9012', status: 'active', total_sku: 45, total_stock: 3200, used_capacity: 45, total_capacity: 8000, created_at: '2025-04-10' },
    { id: '4', name: '匈牙利布达佩斯海外仓', code: 'HU-BP-01', type: 'overseas', address: 'Budapest, Hungary, XX Street XX', country: '匈牙利', city: '布达佩斯', manager: 'Robert', phone: '+36-30-XXXXXXX', status: 'active', total_sku: 67, total_stock: 2100, used_capacity: 35, total_capacity: 6000, created_at: '2025-06-01' },
    { id: '5', name: '西班牙马德里海外仓', code: 'ES-MD-01', type: 'overseas', address: 'Madrid, Spain, Calle XX XX', country: '西班牙', city: '马德里', manager: 'Maria', phone: '+34-6XX-XXXXXX', status: 'maintenance', total_sku: 34, total_stock: 890, used_capacity: 20, total_capacity: 5000, created_at: '2025-08-15' },
  ]

  // 模拟调拨单数据
  const mockTransfers: TransferOrder[] = [
    {
      id: '1', transfer_number: 'TR-20260905-001', from_warehouse: '深圳宝安仓', to_warehouse: '广州货代仓',
      items: [
        { product_name: 'LED头灯 Pro', sku: 'NT-HEADLAMP-001', quantity: 100 },
        { product_name: '保温水壶1L', sku: 'NT-BOTTLE-001', quantity: 50 },
      ],
      total_quantity: 150, status: 'shipped', created_at: '2026-09-05 09:00:00', shipped_at: '2026-09-05 14:00:00',
      tracking_number: 'SF1234567890', logistics_company: '顺丰速运', creator: 'admin', notes: '紧急补货，客户订单等待发货',
    },
    {
      id: '2', transfer_number: 'TR-20260904-002', from_warehouse: '义乌小商品仓', to_warehouse: '深圳宝安仓',
      items: [
        { product_name: '太阳能露营灯', sku: 'NT-LAMP-002', quantity: 200 },
      ],
      total_quantity: 200, status: 'received', created_at: '2026-09-04 10:00:00', shipped_at: '2026-09-04 16:00:00', received_at: '2026-09-05 08:30:00',
      tracking_number: 'YT9876543210', logistics_company: '圆通速递', creator: 'operator1',
    },
    {
      id: '3', transfer_number: 'TR-20260903-003', from_warehouse: '深圳宝安仓', to_warehouse: '匈牙利布达佩斯海外仓',
      items: [
        { product_name: '户外自动帐篷', sku: 'NT-TENT-001', quantity: 30 },
        { product_name: '登山杖 碳纤维', sku: 'NT-POLE-001', quantity: 60 },
        { product_name: '户外登山背包50L', sku: 'NT-BAG-001', quantity: 40 },
      ],
      total_quantity: 130, status: 'pending', created_at: '2026-09-03 15:00:00',
      creator: 'admin', notes: '欧洲市场备货，预计海运15天',
    },
    {
      id: '4', transfer_number: 'TR-20260902-004', from_warehouse: '广州货代仓', to_warehouse: '深圳宝安仓',
      items: [
        { product_name: 'LED头灯 Pro', sku: 'NT-HEADLAMP-001', quantity: 50 },
      ],
      total_quantity: 50, status: 'completed', created_at: '2026-09-02 11:00:00', shipped_at: '2026-09-02 15:00:00', received_at: '2026-09-03 09:00:00',
      tracking_number: 'ZTO1122334455', logistics_company: '中通快递', creator: 'operator1',
    },
    {
      id: '5', transfer_number: 'TR-20260901-005', from_warehouse: '深圳宝安仓', to_warehouse: '西班牙马德里海外仓',
      items: [
        { product_name: '保温水壶1L', sku: 'NT-BOTTLE-001', quantity: 100 },
      ],
      total_quantity: 100, status: 'cancelled', created_at: '2026-09-01 10:00:00',
      creator: 'admin', notes: '海外仓维护中，取消调拨',
    },
  ]

  // 模拟物流商数据
  const mockLogisticsProviders: LogisticsProvider[] = [
    { id: '1', name: '4PX递四方', code: '4PX', type: 'international', channels: ['专线小包', '海外仓', 'FBA头程'], coverage: ['欧洲', '美国', '东南亚'], avg_delivery_days: 12, success_rate: 98.5, price_per_kg: 65, status: 'active', api_connected: true, total_shipments: 3450, rating: 4.7 },
    { id: '2', name: '燕文物流', code: 'YW', type: 'special_line', channels: ['欧洲专线', '美国专线'], coverage: ['欧洲', '美国'], avg_delivery_days: 10, success_rate: 96.2, price_per_kg: 58, status: 'active', api_connected: true, total_shipments: 2180, rating: 4.5 },
    { id: '3', name: '顺丰速运', code: 'SF', type: 'express', channels: ['国内快递', '国际快递'], coverage: ['中国', '全球'], avg_delivery_days: 2, success_rate: 99.8, price_per_kg: 25, status: 'active', api_connected: true, total_shipments: 5680, rating: 4.9 },
    { id: '4', name: '圆通速递', code: 'YT', type: 'domestic', channels: ['国内快递'], coverage: ['中国'], avg_delivery_days: 3, success_rate: 97.5, price_per_kg: 8, status: 'active', api_connected: false, total_shipments: 1250, rating: 4.3 },
    { id: '5', name: 'DHL', code: 'DHL', type: 'international', channels: ['国际快递'], coverage: ['全球'], avg_delivery_days: 5, success_rate: 99.2, price_per_kg: 180, status: 'active', api_connected: false, total_shipments: 890, rating: 4.8 },
    { id: '6', name: '云途物流', code: 'YunExpress', type: 'special_line', channels: ['跨境专线', '邮政小包'], coverage: ['欧洲', '美国', '澳洲'], avg_delivery_days: 14, success_rate: 95.8, price_per_kg: 52, status: 'inactive', api_connected: false, total_shipments: 450, rating: 4.2 },
  ]

  // 加载仓库数据（调用真实API，失败则使用mock数据降级）
  const loadWarehouseData = async () => {
    try {
      setLoading(true)
      // 调用库存状态API
      const statusResp = await fetch('/api/v1/inventory/status')
      if (statusResp.ok) {
        const statusData = await statusResp.json()
        console.log('Inventory status:', statusData)
      }
      // 调用仓库列表API
      const warehousesResp = await fetch('/api/v1/inventory/warehouses')
      if (warehousesResp.ok) {
        const warehousesData = await warehousesResp.json()
        setWarehouseData(warehousesData)
        console.log('Warehouses:', warehousesData)
      }
      message.success('仓库数据加载完成')
    } catch (e: any) {
      console.error('Load warehouse data error:', e)
      message.warning(`API调用失败，使用模拟数据：${e.message || '未知错误'}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadWarehouseData()
  }, [])

  // 统计数据（优先使用真实API数据，失败则使用mock数据降级）
  const realWarehouses = warehouseData?.items || warehouseData?.warehouses || []
  const warehouses = realWarehouses.length > 0 ? realWarehouses : mockWarehouses
  const stats = {
    totalWarehouses: warehouses.length,
    activeWarehouses: warehouses.filter((w: any) => w.status === 'active').length,
    totalStock: warehouses.reduce((sum: number, w: any) => sum + (w.total_stock || w.stock || 0), 0),
    totalTransfers: mockTransfers.length,
    pendingTransfers: mockTransfers.filter(t => t.status === 'pending' || t.status === 'shipped').length,
    activeLogistics: mockLogisticsProviders.filter(l => l.status === 'active').length,
  }

  // 仓库表格列
  const warehouseColumns = [
    {
      title: '仓库名称',
      key: 'name',
      width: 200,
      render: (_: any, record: Warehouse) => (
        <Space>
          <div style={{ width: 36, height: 36, borderRadius: '8px', background: `${warehouseTypeColors[record.type]}15`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <HomeOutlined style={{ fontSize: '18px', color: warehouseTypeColors[record.type] }} />
          </div>
          <div>
            <div style={{ fontWeight: 500 }}>{record.name}</div>
            <div style={{ fontSize: '10px', color: '#999' }}>{record.code}</div>
          </div>
        </Space>
      ),
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      width: 100,
      render: (type: string) => <Tag color={warehouseTypeColors[type]}>{warehouseTypeText[type]}</Tag>,
    },
    {
      title: '位置',
      key: 'location',
      width: 150,
      render: (_: any, record: Warehouse) => (
        <Space>
          <EnvironmentOutlined style={{ fontSize: '12px', color: '#999' }} />
          <Text style={{ fontSize: '12px' }}>{record.country} {record.city}</Text>
        </Space>
      ),
    },
    {
      title: '负责人',
      key: 'manager',
      width: 120,
      render: (_: any, record: Warehouse) => (
        <div>
          <div style={{ fontSize: '12px' }}>{record.manager}</div>
          <div style={{ fontSize: '10px', color: '#999' }}>{record.phone}</div>
        </div>
      ),
    },
    {
      title: 'SKU数',
      dataIndex: 'total_sku',
      key: 'total_sku',
      width: 80,
      render: (count: number) => <Text>{count}</Text>,
    },
    {
      title: '库存',
      dataIndex: 'total_stock',
      key: 'total_stock',
      width: 100,
      render: (count: number) => <Text strong>{count.toLocaleString()}</Text>,
    },
    {
      title: '容量使用',
      key: 'capacity',
      width: 150,
      render: (_: any, record: Warehouse) => (
        <div>
          <Progress percent={record.used_capacity} size="small" strokeColor={record.used_capacity > 80 ? '#f5222d' : record.used_capacity > 60 ? '#faad14' : '#52c41a'} format={(p) => `${p}%`} />
          <div style={{ fontSize: '10px', color: '#999' }}>{record.total_stock.toLocaleString()} / {record.total_capacity.toLocaleString()}</div>
        </div>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={status === 'active' ? 'green' : status === 'maintenance' ? 'orange' : 'default'}>
          {status === 'active' ? '正常' : status === 'maintenance' ? '维护中' : '停用'}
        </Tag>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 150,
      render: (_: any, record: Warehouse) => (
        <Space size="small">
          <Button size="small" icon={<EyeOutlined />} onClick={() => {
            setViewingWarehouse(record)
            setWarehouseDetailOpen(true)
          }}>详情</Button>
          <Button size="small" icon={<SwapOutlined />} onClick={() => message.info(`从${record.name}调拨库存`)}>调拨</Button>
        </Space>
      ),
    },
  ]

  // 调拨单表格列
  const transferColumns = [
    {
      title: '调拨单号',
      dataIndex: 'transfer_number',
      key: 'transfer_number',
      width: 160,
      render: (text: string) => <Text strong style={{ fontSize: '12px' }}>{text}</Text>,
    },
    {
      title: '调出仓',
      dataIndex: 'from_warehouse',
      key: 'from_warehouse',
      width: 140,
      render: (text: string) => (
        <Space>
          <ExportOutlined style={{ fontSize: '11px', color: '#1890ff' }} />
          <Text style={{ fontSize: '12px' }}>{text}</Text>
        </Space>
      ),
    },
    {
      title: '调入仓',
      dataIndex: 'to_warehouse',
      key: 'to_warehouse',
      width: 140,
      render: (text: string) => (
        <Space>
          <ImportOutlined style={{ fontSize: '11px', color: '#52c41a' }} />
          <Text style={{ fontSize: '12px' }}>{text}</Text>
        </Space>
      ),
    },
    {
      title: '商品数',
      key: 'items',
      width: 80,
      render: (_: any, record: TransferOrder) => <Text>{record.items.length}款</Text>,
    },
    {
      title: '总数量',
      dataIndex: 'total_quantity',
      key: 'total_quantity',
      width: 80,
      render: (qty: number) => <Text strong>{qty}件</Text>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => <Tag color={transferStatusColors[status]}>{transferStatusText[status]}</Tag>,
    },
    {
      title: '物流信息',
      key: 'logistics',
      width: 150,
      render: (_: any, record: TransferOrder) => record.tracking_number ? (
        <div>
          <div style={{ fontSize: '11px' }}>{record.logistics_company}</div>
          <div style={{ fontSize: '10px', color: '#999' }}>{record.tracking_number}</div>
        </div>
      ) : <Text type="secondary" style={{ fontSize: '11px' }}>-</Text>,
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
      width: 150,
      render: (_: any, record: TransferOrder) => (
        <Space size="small">
          <Button size="small" icon={<EyeOutlined />} onClick={() => {
            setViewingTransfer(record)
            setTransferDetailOpen(true)
          }}>详情</Button>
          {record.status === 'pending' && (
            <Button size="small" type="primary" icon={<TruckOutlined />} onClick={() => message.success('已标记发货')}>发货</Button>
          )}
          {record.status === 'shipped' && (
            <Button size="small" type="primary" icon={<InboxOutlined />} onClick={() => message.success('已确认收货')}>收货</Button>
          )}
        </Space>
      ),
    },
  ]

  // 物流商表格列
  const logisticsColumns = [
    {
      title: '物流商',
      key: 'name',
      width: 180,
      render: (_: any, record: LogisticsProvider) => (
        <Space>
          <div style={{ width: 36, height: 36, borderRadius: '8px', background: `${logisticsTypeColors[record.type]}15`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <TruckOutlined style={{ fontSize: '18px', color: logisticsTypeColors[record.type] }} />
          </div>
          <div>
            <div style={{ fontWeight: 500 }}>{record.name}</div>
            <div style={{ fontSize: '10px', color: '#999' }}>{record.code}</div>
          </div>
        </Space>
      ),
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      width: 100,
      render: (type: string) => <Tag color={logisticsTypeColors[type]}>{logisticsTypeText[type]}</Tag>,
    },
    {
      title: '物流渠道',
      dataIndex: 'channels',
      key: 'channels',
      width: 200,
      render: (channels: string[]) => (
        <Space size={4} wrap>
          {channels.map((c, i) => <Tag key={i} color="blue" style={{ fontSize: '10px' }}>{c}</Tag>)}
        </Space>
      ),
    },
    {
      title: '覆盖范围',
      dataIndex: 'coverage',
      key: 'coverage',
      width: 150,
      render: (coverage: string[]) => coverage.join('、'),
    },
    {
      title: '平均时效',
      dataIndex: 'avg_delivery_days',
      key: 'avg_delivery_days',
      width: 100,
      render: (days: number) => <Text>{days}天</Text>,
    },
    {
      title: '成功率',
      dataIndex: 'success_rate',
      key: 'success_rate',
      width: 100,
      render: (rate: number) => (
        <div>
          <Progress percent={rate} size="small" strokeColor={rate >= 98 ? '#52c41a' : rate >= 95 ? '#faad14' : '#f5222d'} format={(p) => `${p}%`} />
        </div>
      ),
    },
    {
      title: '参考价格',
      dataIndex: 'price_per_kg',
      key: 'price_per_kg',
      width: 100,
      render: (price: number) => <Text strong style={{ color: '#f5222d' }}>¥{price}/kg</Text>,
    },
    {
      title: 'API对接',
      dataIndex: 'api_connected',
      key: 'api_connected',
      width: 100,
      render: (connected: boolean) => (
        <Tag color={connected ? 'green' : 'default'}>
          {connected ? '已对接' : '未对接'}
        </Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (status: string) => <Tag color={status === 'active' ? 'green' : 'default'}>{status === 'active' ? '启用' : '停用'}</Tag>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_: any, record: LogisticsProvider) => (
        <Space size="small">
          <Button size="small" icon={<EyeOutlined />} onClick={() => message.info(`查看${record.name}详情`)}>详情</Button>
          {!record.api_connected && (
            <Button size="small" type="primary" icon={<SyncOutlined />} onClick={() => message.success(`正在对接${record.name}API`)}>对接</Button>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <DatabaseOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>物流仓配管理</Title>
            <Text type="secondary">多仓库管理、库存调拨、物流商管理</Text>
          </div>
        </Space>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => message.success('数据已刷新')}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateTransferOpen(true)}>新建调拨</Button>
        </Space>
      </div>

      {/* 仓库维护预警 */}
      {mockWarehouses.filter(w => w.status === 'maintenance').length > 0 && (
        <Alert
          message={`有 ${mockWarehouses.filter(w => w.status === 'maintenance').length} 个仓库维护中`}
          description="维护中的仓库无法进行出库操作，请合理安排调拨计划。"
          type="warning"
          showIcon
          icon={<WarningOutlined />}
          style={{ marginBottom: '16px' }}
        />
      )}

      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: '16px' }}>
        <Col span={4}>
          <Card size="small">
            <Statistic title="仓库总数" value={stats.totalWarehouses} prefix={<HomeOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="正常运行" value={stats.activeWarehouses} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="总库存" value={stats.totalStock} prefix={<InboxOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="调拨单" value={stats.totalTransfers} prefix={<SwapOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="运输中" value={stats.pendingTransfers} valueStyle={{ color: '#1890ff' }} prefix={<TruckOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="物流商" value={stats.activeLogistics} valueStyle={{ color: '#722ed1' }} prefix={<TruckOutlined />} />
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
              key: 'warehouses',
              label: '仓库管理',
              children: (
                <div>
                  {/* 筛选栏 */}
                  <Space wrap style={{ marginBottom: '16px' }}>
                    <Input placeholder="搜索仓库名称/编码" prefix={<SearchOutlined />} value={searchText} onChange={(e) => setSearchText(e.target.value)} style={{ width: 220 }} allowClear />
                    <Select value={warehouseStatusFilter} onChange={setWarehouseStatusFilter} style={{ width: 120 }} options={[
                      { value: 'all', label: '全部状态' },
                      { value: 'active', label: '正常' },
                      { value: 'maintenance', label: '维护中' },
                      { value: 'inactive', label: '停用' },
                    ]} />
                    <Button icon={<SearchOutlined />} type="primary">搜索</Button>
                    <Button icon={<ReloadOutlined />} onClick={() => {
                      setSearchText('')
                      setWarehouseStatusFilter('all')
                    }}>重置</Button>
                  </Space>

                  <Table
                    columns={warehouseColumns}
                    dataSource={mockWarehouses}
                    rowKey="id"
                    loading={loading}
                    pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 个仓库` }}
                    locale={{ emptyText: <Empty description="暂无仓库" /> }}
                  />
                </div>
              ),
            },
            {
              key: 'transfers',
              label: '库存调拨',
              children: (
                <div>
                  {/* 筛选栏 */}
                  <Space wrap style={{ marginBottom: '16px' }}>
                    <Input placeholder="搜索调拨单号" prefix={<SearchOutlined />} style={{ width: 220 }} allowClear />
                    <Select value={transferStatusFilter} onChange={setTransferStatusFilter} style={{ width: 120 }} options={[
                      { value: 'all', label: '全部状态' },
                      { value: 'draft', label: '草稿' },
                      { value: 'pending', label: '待发货' },
                      { value: 'shipped', label: '运输中' },
                      { value: 'received', label: '已收货' },
                      { value: 'completed', label: '已完成' },
                      { value: 'cancelled', label: '已取消' },
                    ]} />
                    <Button icon={<SearchOutlined />} type="primary">搜索</Button>
                    <Button icon={<PlusOutlined />} type="primary" onClick={() => setCreateTransferOpen(true)}>新建调拨</Button>
                  </Space>

                  <Table
                    columns={transferColumns}
                    dataSource={mockTransfers}
                    rowKey="id"
                    loading={loading}
                    pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 个调拨单` }}
                    locale={{ emptyText: <Empty description="暂无调拨单" /> }}
                  />
                </div>
              ),
            },
            {
              key: 'logistics',
              label: '物流商管理',
              children: (
                <div>
                  <Alert
                    message="物流商管理"
                    description="管理国内外物流商，查看时效、价格、成功率，支持API对接自动下单。"
                    type="info"
                    showIcon
                    style={{ marginBottom: 16 }}
                  />
                  <Table
                    columns={logisticsColumns}
                    dataSource={mockLogisticsProviders}
                    rowKey="id"
                    loading={loading}
                    pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 个物流商` }}
                    locale={{ emptyText: <Empty description="暂无物流商" /> }}
                  />
                </div>
              ),
            },
          ]}
        />
      </Card>

      {/* 仓库详情Modal */}
      <Modal
        title={`仓库详情 - ${viewingWarehouse?.name || ''}`}
        open={warehouseDetailOpen}
        onCancel={() => setWarehouseDetailOpen(false)}
        footer={[
          <Button key="transfer" type="primary" icon={<SwapOutlined />} onClick={() => {
            message.info('新建库存调拨')
            setWarehouseDetailOpen(false)
            setCreateTransferOpen(true)
          }}>库存调拨</Button>,
          <Button key="close" onClick={() => setWarehouseDetailOpen(false)}>关闭</Button>,
        ]}
        width={700}
      >
        {viewingWarehouse && (
          <div>
            <Descriptions column={2} bordered size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="仓库名称" span={2}>{viewingWarehouse.name}</Descriptions.Item>
              <Descriptions.Item label="仓库编码">{viewingWarehouse.code}</Descriptions.Item>
              <Descriptions.Item label="仓库类型"><Tag color={warehouseTypeColors[viewingWarehouse.type]}>{warehouseTypeText[viewingWarehouse.type]}</Tag></Descriptions.Item>
              <Descriptions.Item label="国家/地区">{viewingWarehouse.country}</Descriptions.Item>
              <Descriptions.Item label="城市">{viewingWarehouse.city}</Descriptions.Item>
              <Descriptions.Item label="详细地址" span={2}>{viewingWarehouse.address}</Descriptions.Item>
              <Descriptions.Item label="负责人">{viewingWarehouse.manager}</Descriptions.Item>
              <Descriptions.Item label="联系电话">{viewingWarehouse.phone}</Descriptions.Item>
              <Descriptions.Item label="状态"><Tag color={viewingWarehouse.status === 'active' ? 'green' : 'orange'}>{viewingWarehouse.status === 'active' ? '正常' : '维护中'}</Tag></Descriptions.Item>
              <Descriptions.Item label="创建时间">{viewingWarehouse.created_at}</Descriptions.Item>
            </Descriptions>

            <Row gutter={16}>
              <Col span={8}>
                <Card size="small">
                  <Statistic title="SKU数量" value={viewingWarehouse.total_sku} />
                </Card>
              </Col>
              <Col span={8}>
                <Card size="small">
                  <Statistic title="库存数量" value={viewingWarehouse.total_stock} />
                </Card>
              </Col>
              <Col span={8}>
                <Card size="small">
                  <Statistic title="容量使用率" value={viewingWarehouse.used_capacity} suffix="%" valueStyle={{ color: viewingWarehouse.used_capacity > 80 ? '#f5222d' : '#52c41a' }} />
                </Card>
              </Col>
            </Row>
          </div>
        )}
      </Modal>

      {/* 调拨单详情Modal */}
      <Modal
        title={`调拨单详情 - ${viewingTransfer?.transfer_number || ''}`}
        open={transferDetailOpen}
        onCancel={() => setTransferDetailOpen(false)}
        footer={[
          <Button key="close" onClick={() => setTransferDetailOpen(false)}>关闭</Button>,
        ]}
        width={700}
      >
        {viewingTransfer && (
          <div>
            {/* 状态进度 */}
            <Steps
              current={['draft', 'pending', 'shipped', 'received', 'completed'].indexOf(viewingTransfer.status)}
              size="small"
              items={[
                { title: '创建', description: viewingTransfer.created_at },
                { title: '待发货' },
                { title: '已发货', description: viewingTransfer.shipped_at || '-' },
                { title: '已收货', description: viewingTransfer.received_at || '-' },
                { title: '完成' },
              ]}
              style={{ marginBottom: 20 }}
            />

            <Descriptions column={2} bordered size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="调拨单号">{viewingTransfer.transfer_number}</Descriptions.Item>
              <Descriptions.Item label="状态"><Tag color={transferStatusColors[viewingTransfer.status]}>{transferStatusText[viewingTransfer.status]}</Tag></Descriptions.Item>
              <Descriptions.Item label="调出仓库">{viewingTransfer.from_warehouse}</Descriptions.Item>
              <Descriptions.Item label="调入仓库">{viewingTransfer.to_warehouse}</Descriptions.Item>
              <Descriptions.Item label="创建人">{viewingTransfer.creator}</Descriptions.Item>
              <Descriptions.Item label="创建时间">{viewingTransfer.created_at}</Descriptions.Item>
              {viewingTransfer.logistics_company && <Descriptions.Item label="物流公司">{viewingTransfer.logistics_company}</Descriptions.Item>}
              {viewingTransfer.tracking_number && <Descriptions.Item label="运单号"><Text code>{viewingTransfer.tracking_number}</Text></Descriptions.Item>}
            </Descriptions>

            {/* 商品列表 */}
            <Card size="small" title="调拨商品" style={{ marginBottom: 16 }}>
              <Table
                dataSource={viewingTransfer.items}
                rowKey="sku"
                size="small"
                pagination={false}
                columns={[
                  { title: '商品名称', dataIndex: 'product_name', key: 'product_name' },
                  { title: 'SKU', dataIndex: 'sku', key: 'sku', render: (t) => <Text code style={{ fontSize: '11px' }}>{t}</Text> },
                  { title: '数量', dataIndex: 'quantity', key: 'quantity', render: (q) => <Text strong>{q}件</Text> },
                ]}
              />
              <div style={{ textAlign: 'right', marginTop: 12, paddingTop: 12, borderTop: '1px solid #f0f0f0' }}>
                <Text strong>合计：</Text>
                <Text strong style={{ fontSize: '18px', color: '#722ed1' }}>{viewingTransfer.total_quantity}件</Text>
              </div>
            </Card>

            {viewingTransfer.notes && (
              <Alert message="备注" description={viewingTransfer.notes} type="info" showIcon />
            )}

            {/* 物流追踪 */}
            {viewingTransfer.tracking_number && (
              <Card size="small" title="物流追踪" style={{ marginTop: 16 }}>
                <Timeline>
                  <Timeline.Item color="green">已签收 - {viewingTransfer.received_at || '派送中'}</Timeline.Item>
                  <Timeline.Item color="blue">运输中 - 已到达目的地转运中心</Timeline.Item>
                  <Timeline.Item color="blue">已揽收 - {viewingTransfer.shipped_at}</Timeline.Item>
                  <Timeline.Item>商家已发货</Timeline.Item>
                </Timeline>
              </Card>
            )}
          </div>
        )}
      </Modal>

      {/* 新建调拨Modal */}
      <Modal
        title="新建库存调拨"
        open={createTransferOpen}
        onCancel={() => setCreateTransferOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setCreateTransferOpen(false)}>取消</Button>,
          <Button key="save" type="primary" onClick={() => {
            message.success('调拨单已创建')
            setCreateTransferOpen(false)
          }}>创建</Button>,
        ]}
        width={600}
      >
        <Form form={transferForm} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="from_warehouse" label="调出仓库" rules={[{ required: true }]}>
                <Select placeholder="选择调出仓库" options={mockWarehouses.filter(w => w.status === 'active').map(w => ({ value: w.name, label: w.name }))} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="to_warehouse" label="调入仓库" rules={[{ required: true }]}>
                <Select placeholder="选择调入仓库" options={mockWarehouses.filter(w => w.status === 'active').map(w => ({ value: w.name, label: w.name }))} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item label="调拨商品">
            <Alert message="请在商品列表中选择需要调拨的商品和数量" type="info" showIcon />
          </Form.Item>
          <Form.Item name="logistics_company" label="物流公司">
            <Select placeholder="选择物流公司（可选）" allowClear options={mockLogisticsProviders.filter(l => l.status === 'active').map(l => ({ value: l.name, label: l.name }))} />
          </Form.Item>
          <Form.Item name="notes" label="备注">
            <Input.TextArea rows={2} placeholder="调拨备注（可选）" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
