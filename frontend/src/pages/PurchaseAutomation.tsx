import { useState } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Input, Select,
  Statistic, Row, Col, Spin, message, Modal, Descriptions,
  Badge, Tooltip, Empty, Tabs, Progress, Divider, Alert,
  Switch, Form, InputNumber, Slider
} from 'antd'
import {
  ShoppingCartOutlined, ReloadOutlined, SearchOutlined,
  EyeOutlined, PlusOutlined, EditOutlined,
  CheckCircleOutlined, CloseCircleOutlined, WarningOutlined,
  SyncOutlined, ClockCircleOutlined, ShopOutlined,
  DollarOutlined, BarChartOutlined, ThunderboltOutlined,
  SettingOutlined, RobotOutlined, PackageOutlined,
  ArrowUpOutlined, ArrowDownOutlined, PlayCircleOutlined,
  PauseCircleOutlined, HistoryOutlined, FundOutlined
} from '@ant-design/icons'

const { Title, Text, Paragraph } = Typography

interface PurchaseRule {
  id: string
  product_name: string
  sku: string
  category: string
  min_stock: number
  max_stock: number
  reorder_quantity: number
  supplier: string
  auto_purchase: boolean
  status: 'active' | 'paused'
  last_purchase_date?: string
  total_purchases: number
  total_amount: number
}

interface PurchaseSuggestion {
  id: string
  product_name: string
  sku: string
  current_stock: number
  safe_stock: number
  suggested_quantity: number
  estimated_cost: number
  supplier: string
  reason: string
  priority: 'high' | 'medium' | 'low'
  status: 'pending' | 'approved' | 'rejected' | 'executed'
  created_at: string
}

interface AutoPurchaseTask {
  id: string
  task_id: string
  product_name: string
  sku: string
  quantity: number
  unit_price: number
  total_amount: number
  supplier: string
  status: 'success' | 'failed' | 'processing'
  trigger_type: 'auto' | 'manual'
  executed_at: string
  error_message?: string
}

const priorityColors: Record<string, string> = {
  high: 'red',
  medium: 'orange',
  low: 'blue',
}

const priorityText: Record<string, string> = {
  high: '高优先级',
  medium: '中优先级',
  low: '低优先级',
}

export default function PurchaseAutomationPage() {
  const [activeTab, setActiveTab] = useState('suggestions')
  const [loading, setLoading] = useState(false)
  const [ruleModalOpen, setRuleModalOpen] = useState(false)
  const [editingRule, setEditingRule] = useState<PurchaseRule | null>(null)
  const [statusFilter, setStatusFilter] = useState('all')
  const [searchText, setSearchText] = useState('')
  const [ruleForm] = Form.useForm()
  const [executing, setExecuting] = useState(false)
  // 真实采购单数据
  const [purchaseOrders, setPurchaseOrders] = useState<any[]>([])
  const [purchaseOrdersLoading, setPurchaseOrdersLoading] = useState(false)
  const [purchaseStats, setPurchaseStats] = useState<any>(null)

  const mockRules: PurchaseRule[] = [
    { id: '1', product_name: 'LED头灯 Pro', sku: 'NT-HEADLAMP-001', category: '照明设备', min_stock: 20, max_stock: 100, reorder_quantity: 50, supplier: '深圳户外装备有限公司', auto_purchase: true, status: 'active', last_purchase_date: '2026-09-05', total_purchases: 12, total_amount: 17100 },
    { id: '2', product_name: '保温水壶1L', sku: 'NT-BOTTLE-001', category: '水具餐具', min_stock: 50, max_stock: 200, reorder_quantity: 100, supplier: '深圳户外装备有限公司', auto_purchase: true, status: 'active', last_purchase_date: '2026-09-04', total_purchases: 8, total_amount: 25600 },
    { id: '3', product_name: '太阳能露营灯', sku: 'NT-LAMP-002', category: '照明设备', min_stock: 15, max_stock: 80, reorder_quantity: 30, supplier: '义乌户外用品批发', auto_purchase: false, status: 'active', last_purchase_date: '2026-08-20', total_purchases: 5, total_amount: 6750 },
    { id: '4', product_name: '户外自动帐篷', sku: 'NT-TENT-001', category: '户外家具', min_stock: 10, max_stock: 50, reorder_quantity: 20, supplier: '广州帐篷制造厂', auto_purchase: true, status: 'paused', last_purchase_date: '2026-09-03', total_purchases: 3, total_amount: 11100 },
    { id: '5', product_name: '登山杖 碳纤维', sku: 'NT-POLE-001', category: '户外配件', min_stock: 20, max_stock: 100, reorder_quantity: 40, supplier: '深圳户外装备有限公司', auto_purchase: true, status: 'active', last_purchase_date: '2026-09-02', total_purchases: 6, total_amount: 16320 },
    { id: '6', product_name: '防水手机袋', sku: 'NT-POUCH-001', category: '户外配件', min_stock: 100, max_stock: 500, reorder_quantity: 200, supplier: '深圳户外装备有限公司', auto_purchase: true, status: 'active', last_purchase_date: '2026-08-30', total_purchases: 10, total_amount: 17000 },
  ]

  const mockSuggestions: PurchaseSuggestion[] = [
    { id: '1', product_name: 'LED头灯 Pro', sku: 'NT-HEADLAMP-001', current_stock: 15, safe_stock: 20, suggested_quantity: 50, estimated_cost: 1425, supplier: '深圳户外装备有限公司', reason: '库存低于安全阈值，且近7天销量增长25%', priority: 'high', status: 'pending', created_at: '2026-09-05 10:00:00' },
    { id: '2', product_name: '保温水壶1L', sku: 'NT-BOTTLE-001', current_stock: 45, safe_stock: 50, suggested_quantity: 100, estimated_cost: 3200, supplier: '深圳户外装备有限公司', reason: '库存低于安全阈值', priority: 'high', status: 'pending', created_at: '2026-09-05 09:00:00' },
    { id: '3', product_name: '太阳能露营灯', sku: 'NT-LAMP-002', current_stock: 25, safe_stock: 15, suggested_quantity: 30, estimated_cost: 1350, supplier: '义乌户外用品批发', reason: '预测未来14天销量将增长，建议提前备货', priority: 'medium', status: 'pending', created_at: '2026-09-05 08:00:00' },
    { id: '4', product_name: '登山杖 碳纤维', sku: 'NT-POLE-001', current_stock: 35, safe_stock: 20, suggested_quantity: 40, estimated_cost: 2720, supplier: '深圳户外装备有限公司', reason: '秋季徒步旺季来临，建议增加库存', priority: 'medium', status: 'approved', created_at: '2026-09-04 15:00:00' },
    { id: '5', product_name: '户外登山背包', sku: 'NT-BAG-001', current_stock: 18, safe_stock: 15, suggested_quantity: 30, estimated_cost: 3600, supplier: '东莞背包工厂', reason: '库存接近安全阈值', priority: 'low', status: 'rejected', created_at: '2026-09-04 10:00:00' },
    { id: '6', product_name: '防水手机袋', sku: 'NT-POUCH-001', current_stock: 80, safe_stock: 100, suggested_quantity: 200, estimated_cost: 1700, supplier: '深圳户外装备有限公司', reason: '库存低于安全阈值，引流款需保证库存', priority: 'high', status: 'executed', created_at: '2026-09-03 14:00:00' },
  ]

  const mockTasks: AutoPurchaseTask[] = [
    { id: '1', task_id: 'AP-20260905-001', product_name: 'LED头灯 Pro', sku: 'NT-HEADLAMP-001', quantity: 50, unit_price: 28.5, total_amount: 1425, supplier: '深圳户外装备有限公司', status: 'success', trigger_type: 'auto', executed_at: '2026-09-05 10:30:00' },
    { id: '2', task_id: 'AP-20260905-002', product_name: '保温水壶1L', sku: 'NT-BOTTLE-001', quantity: 100, unit_price: 32.0, total_amount: 3200, supplier: '深圳户外装备有限公司', status: 'success', trigger_type: 'auto', executed_at: '2026-09-05 09:30:00' },
    { id: '3', task_id: 'AP-20260904-003', product_name: '登山杖 碳纤维', sku: 'NT-POLE-001', quantity: 40, unit_price: 68.0, total_amount: 2720, supplier: '深圳户外装备有限公司', status: 'success', trigger_type: 'manual', executed_at: '2026-09-04 16:00:00' },
    { id: '4', task_id: 'AP-20260904-002', product_name: '太阳能露营灯', sku: 'NT-LAMP-002', quantity: 30, unit_price: 45.0, total_amount: 1350, supplier: '义乌户外用品批发', status: 'failed', trigger_type: 'auto', executed_at: '2026-09-04 11:00:00', error_message: '供应商API连接超时，请手动下单' },
    { id: '5', task_id: 'AP-20260903-001', product_name: '防水手机袋', sku: 'NT-POUCH-001', quantity: 200, unit_price: 8.5, total_amount: 1700, supplier: '深圳户外装备有限公司', status: 'success', trigger_type: 'auto', executed_at: '2026-09-03 14:30:00' },
    { id: '6', task_id: 'AP-20260902-001', product_name: '户外自动帐篷', sku: 'NT-TENT-001', quantity: 20, unit_price: 185.0, total_amount: 3700, supplier: '广州帐篷制造厂', status: 'processing', trigger_type: 'manual', executed_at: '2026-09-02 10:00:00' },
  ]

  const stats = {
    totalRules: mockRules.length,
    activeRules: mockRules.filter(r => r.status === 'active' && r.auto_purchase).length,
    pendingSuggestions: mockSuggestions.filter(s => s.status === 'pending').length,
    todayTasks: mockTasks.filter(t => t.executed_at.startsWith('2026-09-05')).length,
    successRate: Math.round((mockTasks.filter(t => t.status === 'success').length / mockTasks.length) * 100),
    totalSaved: mockTasks.reduce((s, t) => s + t.total_amount, 0),
  }

  // 获取真实采购单列表和统计
  const fetchPurchaseOrders = async (status?: string) => {
    try {
      setPurchaseOrdersLoading(true)
      const url = status && status !== 'all'
        ? `/api/v1/procurement/orders?status=${status}&limit=50`
        : '/api/v1/procurement/orders?limit=50'
      const resp = await fetch(url)
      const data = await resp.json()
      if (data.success && data.data?.orders) {
        setPurchaseOrders(data.data.orders)
      } else {
        setPurchaseOrders([])
      }
    } catch (e: any) {
      console.error('Fetch purchase orders error:', e)
      message.error(`获取采购单失败：${e.message || '网络错误'}`)
    } finally {
      setPurchaseOrdersLoading(false)
    }
  }

  const fetchPurchaseStats = async () => {
    try {
      const resp = await fetch('/api/v1/procurement/stats')
      const data = await resp.json()
      if (data.success && data.data) {
        setPurchaseStats(data.data)
      }
    } catch (e: any) {
      console.error('Fetch purchase stats error:', e)
    }
  }

  const suggestionColumns = [
    { title: '商品', key: 'product', width: 200, render: (_: any, record: PurchaseSuggestion) => (
      <div><div style={{ fontWeight: 500, fontSize: 13 }}>{record.product_name}</div><div style={{ fontSize: 10, color: '#999' }}>SKU: {record.sku}</div></div>
    )},
    { title: '当前库存', dataIndex: 'current_stock', key: 'current_stock', width: 100, render: (stock: number, record: PurchaseSuggestion) => <Text type={stock < record.safe_stock ? 'danger' : 'secondary'}>{stock}件</Text> },
    { title: '安全库存', dataIndex: 'safe_stock', key: 'safe_stock', width: 100, render: (stock: number) => <Text>{stock}件</Text> },
    { title: '建议采购量', dataIndex: 'suggested_quantity', key: 'suggested_quantity', width: 110, render: (qty: number) => <Text strong style={{ color: '#1890ff' }}>{qty}件</Text> },
    { title: '预估成本', dataIndex: 'estimated_cost', key: 'estimated_cost', width: 110, render: (cost: number) => <Text strong style={{ color: '#f5222d' }}>¥{cost.toLocaleString()}</Text> },
    { title: '供应商', dataIndex: 'supplier', key: 'supplier', width: 150 },
    { title: '优先级', dataIndex: 'priority', key: 'priority', width: 100, render: (p: string) => <Tag color={priorityColors[p]}>{priorityText[p]}</Tag> },
    { title: '状态', dataIndex: 'status', key: 'status', width: 90, render: (s: string) => <Tag color={s === 'pending' ? 'default' : s === 'approved' ? 'green' : s === 'rejected' ? 'red' : 'purple'}>{s === 'pending' ? '待处理' : s === 'approved' ? '已批准' : s === 'rejected' ? '已拒绝' : '已执行'}</Tag> },
    { title: 'AI分析原因', dataIndex: 'reason', key: 'reason', ellipsis: true, render: (text: string) => <Tooltip title={text}><Text style={{ fontSize: 12 }}>{text}</Text></Tooltip> },
    { title: '操作', key: 'actions', width: 180, render: (_: any, record: PurchaseSuggestion) => (
      <Space size="small">
        {record.status === 'pending' && (
          <>
            <Button size="small" type="primary" icon={<CheckCircleOutlined />} onClick={() => message.success('已批准采购建议')}>批准</Button>
            <Button size="small" danger icon={<CloseCircleOutlined />} onClick={() => message.info('已拒绝采购建议')}>拒绝</Button>
          </>
        )}
        {record.status === 'approved' && (
          <Button size="small" type="primary" icon={<PlayCircleOutlined />} onClick={() => message.success('已执行采购')}>执行采购</Button>
        )}
      </Space>
    )},
  ]

  const ruleColumns = [
    { title: '商品', key: 'product', width: 200, render: (_: any, record: PurchaseRule) => (
      <div><div style={{ fontWeight: 500, fontSize: 13 }}>{record.product_name}</div><div style={{ fontSize: 10, color: '#999' }}>SKU: {record.sku}</div></div>
    )},
    { title: '分类', dataIndex: 'category', key: 'category', width: 100 },
    { title: '安全库存', dataIndex: 'min_stock', key: 'min_stock', width: 100, render: (v: number) => <Text>{v}件</Text> },
    { title: '最大库存', dataIndex: 'max_stock', key: 'max_stock', width: 100, render: (v: number) => <Text>{v}件</Text> },
    { title: '补货量', dataIndex: 'reorder_quantity', key: 'reorder_quantity', width: 100, render: (v: number) => <Text strong style={{ color: '#1890ff' }}>{v}件</Text> },
    { title: '供应商', dataIndex: 'supplier', key: 'supplier', width: 150 },
    { title: '自动采购', dataIndex: 'auto_purchase', key: 'auto_purchase', width: 100, render: (v: boolean) => <Switch checked={v} size="small" onChange={(checked) => message.success(checked ? '已开启自动采购' : '已关闭自动采购')} /> },
    { title: '状态', dataIndex: 'status', key: 'status', width: 90, render: (s: string) => <Tag color={s === 'active' ? 'green' : 'orange'}>{s === 'active' ? '运行中' : '已暂停'}</Tag> },
    { title: '累计采购', key: 'total', width: 120, render: (_: any, record: PurchaseRule) => <div><div style={{ fontSize: 12 }}>{record.total_purchases}次</div><div style={{ fontSize: 10, color: '#999' }}>¥{record.total_amount.toLocaleString()}</div></div> },
    { title: '操作', key: 'actions', width: 120, render: (_: any, record: PurchaseRule) => (
      <Space size="small">
        <Button size="small" icon={<EditOutlined />} onClick={() => { setEditingRule(record); ruleForm.setFieldsValue(record); setRuleModalOpen(true) }}>编辑</Button>
      </Space>
    )},
  ]

  const taskColumns = [
    { title: '任务ID', dataIndex: 'task_id', key: 'task_id', width: 160, render: (t: string) => <Text code style={{ fontSize: 11 }}>{t}</Text> },
    { title: '商品', key: 'product', width: 180, render: (_: any, record: AutoPurchaseTask) => (
      <div><div style={{ fontWeight: 500, fontSize: 13 }}>{record.product_name}</div><div style={{ fontSize: 10, color: '#999' }}>SKU: {record.sku}</div></div>
    )},
    { title: '数量', dataIndex: 'quantity', key: 'quantity', width: 80, render: (v: number) => <Text>{v}件</Text> },
    { title: '单价', dataIndex: 'unit_price', key: 'unit_price', width: 90, render: (v: number) => <Text>¥{v}</Text> },
    { title: '总金额', dataIndex: 'total_amount', key: 'total_amount', width: 100, render: (v: number) => <Text strong style={{ color: '#f5222d' }}>¥{v.toLocaleString()}</Text> },
    { title: '供应商', dataIndex: 'supplier', key: 'supplier', width: 150 },
    { title: '触发方式', dataIndex: 'trigger_type', key: 'trigger_type', width: 90, render: (t: string) => <Tag color={t === 'auto' ? 'blue' : 'orange'}>{t === 'auto' ? '自动' : '手动'}</Tag> },
    { title: '状态', dataIndex: 'status', key: 'status', width: 100, render: (s: string) => <Tag color={s === 'success' ? 'green' : s === 'failed' ? 'red' : 'blue'} icon={s === 'processing' ? <SyncOutlined spin /> : null}>{s === 'success' ? '成功' : s === 'failed' ? '失败' : '处理中'}</Tag> },
    { title: '执行时间', dataIndex: 'executed_at', key: 'executed_at', width: 160, render: (t: string) => <Text type="secondary" style={{ fontSize: 11 }}>{t}</Text> },
    { title: '错误信息', dataIndex: 'error_message', key: 'error_message', ellipsis: true, render: (text: string) => text ? <Tooltip title={text}><Text type="danger" style={{ fontSize: 11 }}>{text}</Text></Tooltip> : '-' },
  ]

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <RobotOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>采购自动化</Title>
            <Text type="secondary">AI智能补货、自动采购规则、采购任务执行</Text>
          </div>
        </Space>
        <Space>
          <Button icon={<HistoryOutlined />} onClick={() => setActiveTab('tasks')}>执行记录</Button>
          <Button icon={<ReloadOutlined />} onClick={() => message.success('数据已刷新')}>刷新</Button>
          <Button type="primary" icon={<ThunderboltOutlined />} loading={executing} onClick={() => {
            setExecuting(true)
            setTimeout(() => { message.success('AI采购建议已生成'); setExecuting(false) }, 2000)
          }}>AI生成采购建议</Button>
        </Space>
      </div>

      {stats.pendingSuggestions > 0 && (
        <Alert message={`有 ${stats.pendingSuggestions} 条采购建议待处理`} description="请及时审核采购建议，批准后可自动执行采购。" type="warning" showIcon icon={<WarningOutlined />} style={{ marginBottom: '16px' }} action={<Button size="small" type="primary" onClick={() => setActiveTab('suggestions')}>查看建议</Button>} />
      )}

      <Row gutter={[16, 16]} style={{ marginBottom: '16px' }}>
        <Col span={4}><Card size="small"><Statistic title="采购规则" value={stats.totalRules} prefix={<SettingOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="自动采购中" value={stats.activeRules} valueStyle={{ color: '#52c41a' }} prefix={<PlayCircleOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="待处理建议" value={stats.pendingSuggestions} valueStyle={{ color: '#faad14' }} prefix={<ClockCircleOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="今日执行" value={stats.todayTasks} valueStyle={{ color: '#1890ff' }} prefix={<ThunderboltOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="成功率" value={stats.successRate} suffix="%" valueStyle={{ color: '#722ed1' }} prefix={<CheckCircleOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="累计采购额" value={stats.totalSaved} prefix="¥" valueStyle={{ color: '#f5222d' }} /></Card></Col>
      </Row>

      <Card size="small">
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'suggestions',
              label: 'AI采购建议',
              children: (
                <div>
                  <Alert message="AI采购建议引擎" description="基于库存水平、销量趋势、季节因素、供应商交期等多维度，智能生成采购建议，降低缺货风险和库存成本。" type="info" showIcon style={{ marginBottom: 16 }} />
                  <Space wrap style={{ marginBottom: '16px' }}>
                    <Input placeholder="搜索商品名称/SKU" prefix={<SearchOutlined />} value={searchText} onChange={(e) => setSearchText(e.target.value)} style={{ width: 220 }} allowClear />
                    <Select value={statusFilter} onChange={setStatusFilter} style={{ width: 120 }} options={[
                      { value: 'all', label: '全部状态' },
                      { value: 'pending', label: '待处理' },
                      { value: 'approved', label: '已批准' },
                      { value: 'rejected', label: '已拒绝' },
                      { value: 'executed', label: '已执行' },
                    ]} />
                    <Button icon={<SearchOutlined />} type="primary">搜索</Button>
                    <Button icon={<CheckCircleOutlined />} type="primary" onClick={() => message.success('已批量批准所有待处理建议')}>批量批准</Button>
                    <Button icon={<PlayCircleOutlined />} type="primary" onClick={() => message.success('已批量执行批准的建议')}>批量执行</Button>
                  </Space>
                  <Table columns={suggestionColumns} dataSource={mockSuggestions} rowKey="id" loading={loading} pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 条建议` }} locale={{ emptyText: <Empty description="暂无采购建议" /> }} />
                </div>
              ),
            },
            {
              key: 'purchase-orders',
              label: '采购单列表',
              children: (
                <div>
                  <Alert message="真实采购单数据" description="从后端API获取的采购单列表，支持状态筛选和查看详情。点击'代采工作台'可进入完整代采流程。" type="info" showIcon style={{ marginBottom: 16 }} />
                  <Space wrap style={{ marginBottom: '16px' }}>
                    <Select
                      value={statusFilter}
                      onChange={(v) => { setStatusFilter(v); fetchPurchaseOrders(v); }}
                      style={{ width: 140 }}
                      options={[
                        { value: 'all', label: '全部状态' },
                        { value: 'pending', label: '待确认' },
                        { value: 'confirmed', label: '已确认' },
                        { value: 'ordered', label: '已下单' },
                        { value: 'shipped', label: '国内已发货' },
                        { value: 'international_shipped', label: '国际已发货' },
                        { value: 'completed', label: '已完成' },
                        { value: 'cancelled', label: '已取消' },
                      ]}
                    />
                    <Button icon={<ReloadOutlined />} onClick={() => { fetchPurchaseOrders(statusFilter); fetchPurchaseStats(); }}>
                      刷新
                    </Button>
                    <Button type="primary" icon={<ShoppingCartOutlined />} onClick={() => window.location.hash = '#/procurement-workbench'}>
                      进入代采工作台
                    </Button>
                  </Space>

                  {purchaseStats && (
                    <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
                      <Col span={6}>
                        <Card size="small">
                          <Statistic title="采购单总数" value={purchaseStats.total || 0} />
                        </Card>
                      </Col>
                      <Col span={6}>
                        <Card size="small">
                          <Statistic title="待确认" value={purchaseStats.pending || 0} valueStyle={{ color: '#faad14' }} />
                        </Card>
                      </Col>
                      <Col span={6}>
                        <Card size="small">
                          <Statistic title="已下单" value={purchaseStats.ordered || 0} valueStyle={{ color: '#722ed1' }} />
                        </Card>
                      </Col>
                      <Col span={6}>
                        <Card size="small">
                          <Statistic title="已完成" value={purchaseStats.completed || 0} valueStyle={{ color: '#52c41a' }} />
                        </Card>
                      </Col>
                    </Row>
                  )}

                  <Table
                    columns={[
                      { title: '采购单号', dataIndex: 'purchase_order_id', key: 'po_id', width: 160, render: (v: string) => <Text strong>{v}</Text> },
                      { title: 'WC订单', key: 'wc_order', width: 120, render: (_: any, record: any) => (
                        <a href={`https://nuotaooutdoor.com/wp-admin/post.php?post=${record.wc_order_id}&action=edit`} target="_blank" rel="noreferrer">
                          #{record.wc_order_number}
                        </a>
                      )},
                      { title: '状态', dataIndex: 'status', key: 'status', width: 100, render: (v: string) => {
                        const statusMap: Record<string, { color: string; label: string }> = {
                          pending: { color: 'orange', label: '待确认' },
                          confirmed: { color: 'blue', label: '已确认' },
                          ordered: { color: 'purple', label: '已下单' },
                          shipped: { color: 'cyan', label: '国内已发货' },
                          international_shipped: { color: 'geekblue', label: '国际已发货' },
                          completed: { color: 'green', label: '已完成' },
                          cancelled: { color: 'default', label: '已取消' },
                        }
                        const s = statusMap[v] || { color: 'default', label: v }
                        return <Tag color={s.color}>{s.label}</Tag>
                      }},
                      { title: '商品数', key: 'items', width: 80, render: (_: any, record: any) => record.items?.length || 0 },
                      { title: '总成本', dataIndex: 'total_cost', key: 'cost', width: 100, render: (v: number) => <Text strong style={{ color: '#f5222d' }}>¥{Number(v || 0).toFixed(2)}</Text> },
                      { title: '客户', key: 'customer', width: 120, render: (_: any, record: any) => record.customer?.name || '-' },
                      { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 160, render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '-' },
                    ]}
                    dataSource={purchaseOrders}
                    rowKey="purchase_order_id"
                    loading={purchaseOrdersLoading}
                    pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 个采购单` }}
                    locale={{ emptyText: <Empty description="暂无采购单数据" /> }}
                    onRow={(record) => ({
                      onClick: () => window.location.hash = '#/procurement-workbench',
                      style: { cursor: 'pointer' },
                    })}
                  />
                </div>
              ),
            },
            {
              key: 'rules',
              label: '采购规则',
              children: (
                <div>
                  <Space wrap style={{ marginBottom: '16px' }}>
                    <Input placeholder="搜索商品名称/SKU" prefix={<SearchOutlined />} style={{ width: 220 }} allowClear />
                    <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditingRule(null); ruleForm.resetFields(); setRuleModalOpen(true) }}>添加规则</Button>
                  </Space>
                  <Table columns={ruleColumns} dataSource={mockRules} rowKey="id" loading={loading} pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 条规则` }} locale={{ emptyText: <Empty description="暂无采购规则" /> }} />
                </div>
              ),
            },
            {
              key: 'tasks',
              label: '执行记录',
              children: (
                <div>
                  <Table columns={taskColumns} dataSource={mockTasks} rowKey="id" loading={loading} pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 条记录` }} locale={{ emptyText: <Empty description="暂无执行记录" /> }} />
                </div>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title={editingRule ? '编辑采购规则' : '添加采购规则'}
        open={ruleModalOpen}
        onCancel={() => setRuleModalOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setRuleModalOpen(false)}>取消</Button>,
          <Button key="save" type="primary" onClick={() => { message.success('采购规则已保存'); setRuleModalOpen(false) }}>保存</Button>,
        ]}
        width={600}
      >
        <Form form={ruleForm} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="product_name" label="商品名称" rules={[{ required: true }]}><Input placeholder="请输入商品名称" /></Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="sku" label="SKU" rules={[{ required: true }]}><Input placeholder="请输入SKU" /></Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="min_stock" label="安全库存" initialValue={20}><InputNumber min={0} style={{ width: '100%' }} addonAfter="件" /></Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="max_stock" label="最大库存" initialValue={100}><InputNumber min={0} style={{ width: '100%' }} addonAfter="件" /></Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="reorder_quantity" label="补货数量" initialValue={50}><InputNumber min={1} style={{ width: '100%' }} addonAfter="件" /></Form.Item>
            </Col>
          </Row>
          <Form.Item name="supplier" label="默认供应商" rules={[{ required: true }]}>
            <Select options={[
              { value: '深圳户外装备有限公司', label: '深圳户外装备有限公司' },
              { value: '义乌户外用品批发', label: '义乌户外用品批发' },
              { value: '广州帐篷制造厂', label: '广州帐篷制造厂' },
              { value: '东莞背包工厂', label: '东莞背包工厂' },
            ]} />
          </Form.Item>
          <Form.Item name="auto_purchase" label="自动采购" valuePropName="checked" initialValue={false}>
            <Switch checkedChildren="开启" unCheckedChildren="关闭" />
          </Form.Item>
          <Alert message="开启自动采购后，当库存低于安全阈值时，系统将自动创建采购单并通知供应商。" type="info" showIcon />
        </Form>
      </Modal>
    </div>
  )
}
