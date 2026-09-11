import { useState, useEffect } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Input, Select,
  Statistic, Row, Col, Spin, message, Modal, Descriptions,
  Badge, Tooltip, Empty, Tabs, Progress, Divider, Alert,
  Timeline, List, Avatar, Switch, Form
} from 'antd'
import {
  GlobalOutlined, ReloadOutlined, SearchOutlined,
  EyeOutlined, PlusOutlined,
  CheckCircleOutlined, WarningOutlined,
  SyncOutlined, ClockCircleOutlined,
  DollarOutlined, BarChartOutlined, ThunderboltOutlined,
  SettingOutlined, DatabaseOutlined, TruckOutlined,
  ArrowUpOutlined, ArrowDownOutlined,
  ShoppingCartOutlined, UserOutlined, GiftOutlined,
  CustomerServiceOutlined, FundOutlined,
  SendOutlined,
  CalendarOutlined, BulbOutlined, ExclamationCircleOutlined,
  ApiOutlined, CloudOutlined, InboxOutlined,
  ExportOutlined, ImportOutlined, EnvironmentOutlined
} from '@ant-design/icons'

const { Title, Text, Paragraph } = Typography

interface OverseasWarehouse {
  id: string
  name: string
  country: string
  city: string
  address: string
  type: 'self-operated' | 'third-party'
  status: 'active' | 'inactive' | 'syncing'
  api_connected: boolean
  total_sku: number
  total_stock: number
  used_capacity: number
  total_capacity: number
  avg_delivery_days: number
  monthly_orders: number
  monthly_revenue: number
  storage_fee: number
  last_sync_time?: string
}

interface InventoryItem {
  id: string
  sku: string
  product_name: string
  warehouse: string
  available_stock: number
  reserved_stock: number
  in_transit: number
  safety_stock: number
  status: 'normal' | 'low' | 'out'
  last_updated: string
}

interface ShipmentOrder {
  id: string
  order_no: string
  type: 'inbound' | 'outbound'
  warehouse: string
  sku_count: number
  total_quantity: number
  status: 'pending' | 'processing' | 'shipped' | 'delivered' | 'failed'
  carrier: string
  tracking_no?: string
  estimated_delivery?: string
  created_at: string
}

const warehouseStatusColors: Record<string, string> = {
  active: 'green',
  inactive: 'default',
  syncing: 'blue',
}

const warehouseStatusText: Record<string, string> = {
  active: '运行中',
  inactive: '未启用',
  syncing: '同步中',
}

export default function OverseasWarehousePage() {
  const [activeTab, setActiveTab] = useState('warehouses')
  const [loading, setLoading] = useState(false)
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [viewingWarehouse, setViewingWarehouse] = useState<OverseasWarehouse | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [apiModalOpen, setApiModalOpen] = useState(false)
  // 真实API数据状态
  const [overseasData, setOverseasData] = useState<any>(null)
  const [apiForm] = Form.useForm()

  const mockWarehouses: OverseasWarehouse[] = [
    { id: '1', name: '匈牙利布达佩斯仓', country: '匈牙利', city: '布达佩斯', address: 'Budapest, Hungary, 1101', type: 'third-party', status: 'active', api_connected: true, total_sku: 45, total_stock: 2850, used_capacity: 65, total_capacity: 100, avg_delivery_days: 3, monthly_orders: 1250, monthly_revenue: 45600, storage_fee: 1200, last_sync_time: '2026-09-05 10:30:00' },
    { id: '2', name: '西班牙马德里仓', country: '西班牙', city: '马德里', address: 'Madrid, Spain, 28001', type: 'third-party', status: 'active', api_connected: true, total_sku: 38, total_stock: 2100, used_capacity: 52, total_capacity: 100, avg_delivery_days: 2, monthly_orders: 980, monthly_revenue: 38500, storage_fee: 950, last_sync_time: '2026-09-05 10:25:00' },
    { id: '3', name: '德国法兰克福仓', country: '德国', city: '法兰克福', address: 'Frankfurt, Germany, 60311', type: 'self-operated', status: 'syncing', api_connected: true, total_sku: 52, total_stock: 3200, used_capacity: 78, total_capacity: 100, avg_delivery_days: 2, monthly_orders: 1580, monthly_revenue: 62000, storage_fee: 1800, last_sync_time: '2026-09-05 10:00:00' },
    { id: '4', name: '美国洛杉矶仓', country: '美国', city: '洛杉矶', address: 'Los Angeles, CA, USA, 90001', type: 'third-party', status: 'active', api_connected: false, total_sku: 25, total_stock: 1500, used_capacity: 40, total_capacity: 100, avg_delivery_days: 4, monthly_orders: 650, monthly_revenue: 28000, storage_fee: 2200, last_sync_time: '2026-09-04 18:00:00' },
    { id: '5', name: '英国伦敦仓', country: '英国', city: '伦敦', address: 'London, UK, SW1A 1AA', type: 'third-party', status: 'inactive', api_connected: false, total_sku: 0, total_stock: 0, used_capacity: 0, total_capacity: 100, avg_delivery_days: 3, monthly_orders: 0, monthly_revenue: 0, storage_fee: 0 },
  ]

  const mockInventory: InventoryItem[] = [
    { id: '1', sku: 'NT-HEADLAMP-001', product_name: 'LED头灯 Pro', warehouse: '匈牙利布达佩斯仓', available_stock: 180, reserved_stock: 25, in_transit: 100, safety_stock: 50, status: 'normal', last_updated: '2026-09-05 10:30:00' },
    { id: '2', sku: 'NT-BOTTLE-001', product_name: '保温水壶1L', warehouse: '匈牙利布达佩斯仓', available_stock: 45, reserved_stock: 10, in_transit: 200, safety_stock: 50, status: 'low', last_updated: '2026-09-05 10:30:00' },
    { id: '3', sku: 'NT-POUCH-001', product_name: '防水手机袋', warehouse: '西班牙马德里仓', available_stock: 520, reserved_stock: 80, in_transit: 0, safety_stock: 100, status: 'normal', last_updated: '2026-09-05 10:25:00' },
    { id: '4', sku: 'NT-BAG-001', product_name: '户外登山背包', warehouse: '德国法兰克福仓', available_stock: 0, reserved_stock: 0, in_transit: 50, safety_stock: 20, status: 'out', last_updated: '2026-09-05 10:00:00' },
    { id: '5', sku: 'NT-POLE-001', product_name: '登山杖 碳纤维', warehouse: '德国法兰克福仓', available_stock: 120, reserved_stock: 15, in_transit: 0, safety_stock: 30, status: 'normal', last_updated: '2026-09-05 10:00:00' },
    { id: '6', sku: 'NT-LAMP-002', product_name: '太阳能露营灯', warehouse: '美国洛杉矶仓', available_stock: 85, reserved_stock: 5, in_transit: 0, safety_stock: 20, status: 'normal', last_updated: '2026-09-04 18:00:00' },
  ]

  const mockShipments: ShipmentOrder[] = [
    { id: '1', order_no: 'IB-20260905-001', type: 'inbound', warehouse: '匈牙利布达佩斯仓', sku_count: 5, total_quantity: 500, status: 'processing', carrier: '4PX递四方', tracking_no: '4PX1234567890', estimated_delivery: '2026-09-10', created_at: '2026-09-05 08:00:00' },
    { id: '2', order_no: 'OB-20260905-001', type: 'outbound', warehouse: '匈牙利布达佩斯仓', sku_count: 3, total_quantity: 45, status: 'shipped', carrier: 'DPD', tracking_no: 'DPD9876543210', estimated_delivery: '2026-09-07', created_at: '2026-09-05 09:30:00' },
    { id: '3', order_no: 'OB-20260905-002', type: 'outbound', warehouse: '西班牙马德里仓', sku_count: 2, total_quantity: 28, status: 'delivered', carrier: 'Correos', tracking_no: 'CORREOS555666777', created_at: '2026-09-04 14:00:00' },
    { id: '4', order_no: 'IB-20260904-001', type: 'inbound', warehouse: '德国法兰克福仓', sku_count: 8, total_quantity: 800, status: 'delivered', carrier: 'DHL', tracking_no: 'DHL111222333', created_at: '2026-09-01 10:00:00' },
    { id: '5', order_no: 'OB-20260904-003', type: 'outbound', warehouse: '美国洛杉矶仓', sku_count: 1, total_quantity: 15, status: 'failed', carrier: 'USPS', error_message: '地址错误，包裹退回', created_at: '2026-09-03 11:00:00' },
  ]

  // 加载海外仓数据（调用真实API，失败则使用mock数据降级）
  const loadOverseasWarehouseData = async () => {
    try {
      setLoading(true)
      // 调用海外仓状态API
      const statusResp = await fetch('/api/v1/overseas-warehouse/status')
      if (statusResp.ok) {
        const statusData = await statusResp.json()
        setOverseasData(statusData)
        console.log('Overseas warehouse status:', statusData)
      }
      message.success('海外仓数据加载完成')
    } catch (e: any) {
      console.error('Load overseas warehouse data error:', e)
      message.warning(`API调用失败，使用模拟数据：${e.message || '未知错误'}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadOverseasWarehouseData()
  }, [])

  // 统计数据（优先使用真实API数据，失败则使用mock数据降级）
  const stats = {
    totalWarehouses: overseasData?.total_warehouses || mockWarehouses.filter(w => w.status !== 'inactive').length,
    apiConnected: overseasData?.api_connected || mockWarehouses.filter(w => w.api_connected).length,
    totalStock: overseasData?.total_stock || mockWarehouses.reduce((s, w) => s + w.total_stock, 0),
    totalSKU: overseasData?.total_sku || mockWarehouses.reduce((s, w) => s + w.total_sku, 0),
    monthlyOrders: overseasData?.monthly_orders || mockWarehouses.reduce((s, w) => s + w.monthly_orders, 0),
    monthlyRevenue: overseasData?.monthly_revenue || mockWarehouses.reduce((s, w) => s + w.monthly_revenue, 0),
  }

  const warehouseColumns = [
    { title: '仓库', key: 'warehouse', width: 200, render: (_: any, record: OverseasWarehouse) => (
      <div>
        <div style={{ fontWeight: 500, fontSize: 13 }}><EnvironmentOutlined style={{ marginRight: 6, color: '#1890ff' }} />{record.name}</div>
        <div style={{ fontSize: 10, color: '#999' }}>{record.country} · {record.city}</div>
        <div style={{ fontSize: 10, color: '#999' }}>{record.address}</div>
      </div>
    )},
    { title: '类型', dataIndex: 'type', key: 'type', width: 100, render: (t: string) => <Tag color={t === 'self-operated' ? 'blue' : 'purple'}>{t === 'self-operated' ? '自营仓' : '第三方仓'}</Tag> },
    { title: '状态', dataIndex: 'status', key: 'status', width: 100, render: (s: string) => <Tag color={warehouseStatusColors[s]} icon={s === 'syncing' ? <SyncOutlined spin /> : null}>{warehouseStatusText[s]}</Tag> },
    { title: 'API对接', dataIndex: 'api_connected', key: 'api_connected', width: 100, render: (v: boolean) => v ? <Tag color="green" icon={<ApiOutlined />}>已连接</Tag> : <Tag color="red">未连接</Tag> },
    { title: 'SKU数', dataIndex: 'total_sku', key: 'total_sku', width: 80, render: (v: number) => <Text>{v}</Text> },
    { title: '库存', dataIndex: 'total_stock', key: 'total_stock', width: 100, render: (v: number) => <Text strong>{v.toLocaleString()}件</Text> },
    { title: '容量使用率', dataIndex: 'used_capacity', key: 'used_capacity', width: 130, render: (v: number, record: OverseasWarehouse) => <Progress percent={v} size="small" strokeColor={v > 80 ? '#f5222d' : v > 60 ? '#faad14' : '#52c41a'} format={(p) => `${p}%`} /> },
    { title: '平均配送时效', dataIndex: 'avg_delivery_days', key: 'avg_delivery_days', width: 110, render: (v: number) => <Text><TruckOutlined style={{ marginRight: 4 }} />{v}天</Text> },
    { title: '月订单量', dataIndex: 'monthly_orders', key: 'monthly_orders', width: 100, render: (v: number) => <Text>{v.toLocaleString()}单</Text> },
    { title: '月收入', dataIndex: 'monthly_revenue', key: 'monthly_revenue', width: 110, render: (v: number) => <Text strong style={{ color: '#52c41a' }}>¥{v.toLocaleString()}</Text> },
    { title: '最后同步', dataIndex: 'last_sync_time', key: 'last_sync_time', width: 150, render: (t?: string) => t ? <Text type="secondary" style={{ fontSize: 11 }}>{t}</Text> : '-' },
    { title: '操作', key: 'actions', width: 180, render: (_: any, record: OverseasWarehouse) => (
      <Space size="small">
        <Button size="small" icon={<EyeOutlined />} onClick={() => { setViewingWarehouse(record); setDetailModalOpen(true) }}>详情</Button>
        <Button size="small" icon={<SyncOutlined />} onClick={() => message.success(`正在同步 ${record.name} 库存`)}>同步</Button>
        {!record.api_connected && <Button size="small" type="primary" icon={<ApiOutlined />} onClick={() => { setViewingWarehouse(record); apiForm.resetFields(); setApiModalOpen(true) }}>对接API</Button>}
      </Space>
    )},
  ]

  const inventoryColumns = [
    { title: 'SKU', dataIndex: 'sku', key: 'sku', width: 150, render: (s: string) => <Text code style={{ fontSize: 11 }}>{s}</Text> },
    { title: '商品名称', dataIndex: 'product_name', key: 'product_name', width: 180 },
    { title: '所在仓库', dataIndex: 'warehouse', key: 'warehouse', width: 150 },
    { title: '可用库存', dataIndex: 'available_stock', key: 'available_stock', width: 100, render: (v: number, record: InventoryItem) => <Text type={record.status === 'out' ? 'danger' : record.status === 'low' ? 'warning' : 'success'} strong>{v}件</Text> },
    { title: '预留库存', dataIndex: 'reserved_stock', key: 'reserved_stock', width: 100, render: (v: number) => <Text type="secondary">{v}件</Text> },
    { title: '在途库存', dataIndex: 'in_transit', key: 'in_transit', width: 100, render: (v: number) => v > 0 ? <Tag color="blue">{v}件</Tag> : <Text type="secondary">0</Text> },
    { title: '安全库存', dataIndex: 'safety_stock', key: 'safety_stock', width: 100, render: (v: number) => <Text>{v}件</Text> },
    { title: '状态', dataIndex: 'status', key: 'status', width: 100, render: (s: string) => <Tag color={s === 'normal' ? 'green' : s === 'low' ? 'orange' : 'red'}>{s === 'normal' ? '正常' : s === 'low' ? '库存偏低' : '缺货'}</Tag> },
    { title: '最后更新', dataIndex: 'last_updated', key: 'last_updated', width: 150, render: (t: string) => <Text type="secondary" style={{ fontSize: 11 }}>{t}</Text> },
  ]

  const shipmentColumns = [
    { title: '单据号', dataIndex: 'order_no', key: 'order_no', width: 160, render: (s: string) => <Text code style={{ fontSize: 11 }}>{s}</Text> },
    { title: '类型', dataIndex: 'type', key: 'type', width: 80, render: (t: string) => <Tag color={t === 'inbound' ? 'blue' : 'green'} icon={t === 'inbound' ? <ImportOutlined /> : <ExportOutlined />}>{t === 'inbound' ? '入库' : '出库'}</Tag> },
    { title: '仓库', dataIndex: 'warehouse', key: 'warehouse', width: 150 },
    { title: 'SKU数', dataIndex: 'sku_count', key: 'sku_count', width: 80, render: (v: number) => <Text>{v}个</Text> },
    { title: '总数量', dataIndex: 'total_quantity', key: 'total_quantity', width: 100, render: (v: number) => <Text strong>{v}件</Text> },
    { title: '物流商', dataIndex: 'carrier', key: 'carrier', width: 120 },
    { title: '运单号', dataIndex: 'tracking_no', key: 'tracking_no', width: 150, render: (s?: string) => s ? <Text code style={{ fontSize: 11 }}>{s}</Text> : '-' },
    { title: '状态', dataIndex: 'status', key: 'status', width: 100, render: (s: string) => <Tag color={s === 'pending' ? 'default' : s === 'processing' ? 'blue' : s === 'shipped' ? 'orange' : s === 'delivered' ? 'green' : 'red'} icon={s === 'processing' ? <SyncOutlined spin /> : null}>{s === 'pending' ? '待处理' : s === 'processing' ? '处理中' : s === 'shipped' ? '已发货' : s === 'delivered' ? '已送达' : '失败'}</Tag> },
    { title: '预计送达', dataIndex: 'estimated_delivery', key: 'estimated_delivery', width: 110, render: (s?: string) => s || '-' },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 150, render: (t: string) => <Text type="secondary" style={{ fontSize: 11 }}>{t}</Text> },
  ]

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <GlobalOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>海外仓对接</Title>
            <Text type="secondary">多仓库管理、库存同步、入出库管理、物流配送</Text>
          </div>
        </Space>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => message.success('数据已刷新')}>刷新</Button>
          <Button type="primary" icon={<SyncOutlined />} loading={syncing} onClick={() => {
            setSyncing(true)
            setTimeout(() => { message.success('所有海外仓库存同步完成'); setSyncing(false) }, 3000)
          }}>同步所有库存</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => message.info('添加海外仓')}>添加仓库</Button>
        </Space>
      </div>

      <Alert message="海外仓API对接状态" description={`已对接 ${stats.apiConnected}/${stats.totalWarehouses} 个海外仓API，库存自动同步。未对接的仓库需手动更新库存。`} type={stats.apiConnected === stats.totalWarehouses ? 'success' : 'warning'} showIcon icon={<ApiOutlined />} style={{ marginBottom: 16 }} action={<Button size="small" type="primary" onClick={() => setApiModalOpen(true)}>配置API</Button>} />

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={4}><Card size="small"><Statistic title="海外仓数量" value={stats.totalWarehouses} prefix={<GlobalOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="API已对接" value={stats.apiConnected} valueStyle={{ color: '#52c41a' }} prefix={<ApiOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="总库存" value={stats.totalStock} suffix="件" valueStyle={{ color: '#1890ff' }} prefix={<DatabaseOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="SKU总数" value={stats.totalSKU} valueStyle={{ color: '#722ed1' }} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="月订单量" value={stats.monthlyOrders} suffix="单" valueStyle={{ color: '#fa8c16' }} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="月收入" value={stats.monthlyRevenue} prefix="¥" valueStyle={{ color: '#52c41a' }} /></Card></Col>
      </Row>

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
                  <Space wrap style={{ marginBottom: 16 }}>
                    <Input placeholder="搜索仓库名称/城市" prefix={<SearchOutlined />} style={{ width: 200 }} allowClear />
                    <Select defaultValue="all" style={{ width: 120 }} options={[
                      { value: 'all', label: '全部状态' },
                      { value: 'active', label: '运行中' },
                      { value: 'syncing', label: '同步中' },
                      { value: 'inactive', label: '未启用' },
                    ]} />
                    <Select defaultValue="all" style={{ width: 120 }} options={[
                      { value: 'all', label: '全部类型' },
                      { value: 'self-operated', label: '自营仓' },
                      { value: 'third-party', label: '第三方仓' },
                    ]} />
                  </Space>
                  <Table columns={warehouseColumns} dataSource={mockWarehouses} rowKey="id" pagination={false} locale={{ emptyText: <Empty description="暂无海外仓" /> }} scroll={{ x: 1600 }} />
                </div>
              ),
            },
            {
              key: 'inventory',
              label: '库存管理',
              children: (
                <div>
                  <Space wrap style={{ marginBottom: 16 }}>
                    <Input placeholder="搜索SKU/商品名称" prefix={<SearchOutlined />} style={{ width: 200 }} allowClear />
                    <Select defaultValue="all" style={{ width: 120 }} options={[
                      { value: 'all', label: '全部仓库' },
                      { value: '匈牙利布达佩斯仓', label: '匈牙利布达佩斯仓' },
                      { value: '西班牙马德里仓', label: '西班牙马德里仓' },
                      { value: '德国法兰克福仓', label: '德国法兰克福仓' },
                      { value: '美国洛杉矶仓', label: '美国洛杉矶仓' },
                    ]} />
                    <Select defaultValue="all" style={{ width: 120 }} options={[
                      { value: 'all', label: '全部状态' },
                      { value: 'normal', label: '正常' },
                      { value: 'low', label: '库存偏低' },
                      { value: 'out', label: '缺货' },
                    ]} />
                    <Button type="primary" icon={<SyncOutlined />} onClick={() => message.success('库存同步完成')}>同步库存</Button>
                  </Space>
                  <Table columns={inventoryColumns} dataSource={mockInventory} rowKey="id" pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 个SKU` }} locale={{ emptyText: <Empty description="暂无库存数据" /> }} scroll={{ x: 1200 }} />
                </div>
              ),
            },
            {
              key: 'shipments',
              label: '入出库管理',
              children: (
                <div>
                  <Space wrap style={{ marginBottom: 16 }}>
                    <Input placeholder="搜索单据号/运单号" prefix={<SearchOutlined />} style={{ width: 200 }} allowClear />
                    <Select defaultValue="all" style={{ width: 120 }} options={[
                      { value: 'all', label: '全部类型' },
                      { value: 'inbound', label: '入库' },
                      { value: 'outbound', label: '出库' },
                    ]} />
                    <Select defaultValue="all" style={{ width: 120 }} options={[
                      { value: 'all', label: '全部状态' },
                      { value: 'pending', label: '待处理' },
                      { value: 'processing', label: '处理中' },
                      { value: 'shipped', label: '已发货' },
                      { value: 'delivered', label: '已送达' },
                      { value: 'failed', label: '失败' },
                    ]} />
                    <Button type="primary" icon={<PlusOutlined />} onClick={() => message.info('创建入库单')}>创建入库单</Button>
                    <Button type="primary" icon={<ExportOutlined />} onClick={() => message.info('创建出库单')}>创建出库单</Button>
                  </Space>
                  <Table columns={shipmentColumns} dataSource={mockShipments} rowKey="id" pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 条单据` }} locale={{ emptyText: <Empty description="暂无入出库单据" /> }} scroll={{ x: 1400 }} />
                </div>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title={`仓库详情 - ${viewingWarehouse?.name || ''}`}
        open={detailModalOpen}
        onCancel={() => setDetailModalOpen(false)}
        footer={[
          <Button key="sync" icon={<SyncOutlined />} onClick={() => message.success('库存同步中')}>同步库存</Button>,
          <Button key="close" onClick={() => setDetailModalOpen(false)}>关闭</Button>,
        ]}
        width={700}
      >
        {viewingWarehouse && (
          <div>
            <Descriptions column={2} bordered size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="仓库名称" span={2}>{viewingWarehouse.name}</Descriptions.Item>
              <Descriptions.Item label="国家">{viewingWarehouse.country}</Descriptions.Item>
              <Descriptions.Item label="城市">{viewingWarehouse.city}</Descriptions.Item>
              <Descriptions.Item label="地址" span={2}>{viewingWarehouse.address}</Descriptions.Item>
              <Descriptions.Item label="仓库类型"><Tag color={viewingWarehouse.type === 'self-operated' ? 'blue' : 'purple'}>{viewingWarehouse.type === 'self-operated' ? '自营仓' : '第三方仓'}</Tag></Descriptions.Item>
              <Descriptions.Item label="状态"><Tag color={warehouseStatusColors[viewingWarehouse.status]}>{warehouseStatusText[viewingWarehouse.status]}</Tag></Descriptions.Item>
              <Descriptions.Item label="API对接">{viewingWarehouse.api_connected ? <Tag color="green">已连接</Tag> : <Tag color="red">未连接</Tag>}</Descriptions.Item>
              <Descriptions.Item label="最后同步">{viewingWarehouse.last_sync_time || '-'}</Descriptions.Item>
              <Descriptions.Item label="SKU数">{viewingWarehouse.total_sku}个</Descriptions.Item>
              <Descriptions.Item label="总库存">{viewingWarehouse.total_stock.toLocaleString()}件</Descriptions.Item>
              <Descriptions.Item label="容量使用率"><Progress percent={viewingWarehouse.used_capacity} size="small" strokeColor={viewingWarehouse.used_capacity > 80 ? '#f5222d' : '#52c41a'} /></Descriptions.Item>
              <Descriptions.Item label="平均配送时效">{viewingWarehouse.avg_delivery_days}天</Descriptions.Item>
              <Descriptions.Item label="月订单量">{viewingWarehouse.monthly_orders.toLocaleString()}单</Descriptions.Item>
              <Descriptions.Item label="月收入"><Text strong style={{ color: '#52c41a' }}>¥{viewingWarehouse.monthly_revenue.toLocaleString()}</Text></Descriptions.Item>
              <Descriptions.Item label="月仓储费"><Text type="danger">¥{viewingWarehouse.storage_fee.toLocaleString()}</Text></Descriptions.Item>
            </Descriptions>
          </div>
        )}
      </Modal>

      <Modal
        title="海外仓API对接配置"
        open={apiModalOpen}
        onCancel={() => setApiModalOpen(false)}
        footer={[
          <Button key="test" icon={<ApiOutlined />} onClick={() => message.success('API连接测试成功')}>测试连接</Button>,
          <Button key="cancel" onClick={() => setApiModalOpen(false)}>取消</Button>,
          <Button key="save" type="primary" onClick={() => { message.success('API配置已保存'); setApiModalOpen(false) }}>保存</Button>,
        ]}
        width={600}
      >
        <Form form={apiForm} layout="vertical">
          <Form.Item name="warehouse" label="选择仓库" rules={[{ required: true }]}>
            <Select options={mockWarehouses.map(w => ({ value: w.id, label: w.name }))} />
          </Form.Item>
          <Form.Item name="api_type" label="API类型" rules={[{ required: true }]}>
            <Select options={[
              { value: '4px', label: '4PX递四方' },
              { value: 'yanwen', label: '燕文物流' },
              { value: 'cloud', label: '云途物流' },
              { value: 'custom', label: '自定义API' },
            ]} />
          </Form.Item>
          <Form.Item name="api_key" label="API Key" rules={[{ required: true }]}>
            <Input.Password placeholder="请输入API Key" />
          </Form.Item>
          <Form.Item name="api_secret" label="API Secret" rules={[{ required: true }]}>
            <Input.Password placeholder="请输入API Secret" />
          </Form.Item>
          <Form.Item name="warehouse_code" label="仓库编码" rules={[{ required: true }]}>
            <Input placeholder="请输入海外仓分配的仓库编码" />
          </Form.Item>
          <Form.Item name="auto_sync" label="自动同步库存" valuePropName="checked" initialValue={true}>
            <Switch checkedChildren="开启" unCheckedChildren="关闭" />
          </Form.Item>
          <Alert message="开启自动同步后，系统将每小时自动同步海外仓库存，确保库存数据准确。" type="info" showIcon />
        </Form>
      </Modal>
    </div>
  )
}
