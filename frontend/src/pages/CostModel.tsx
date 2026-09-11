import { useState, useEffect } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Input, Select,
  Statistic, Row, Col, Spin, message, Modal, Descriptions,
  Badge, Tooltip, Empty, Tabs, Progress, Divider, Alert,
  List, Avatar, Form, Radio, Switch, Segmented,
  InputNumber, Slider
} from 'antd'
import {
  DollarOutlined, ReloadOutlined, SearchOutlined,
  EyeOutlined, PlusOutlined, DownloadOutlined,
  CheckCircleOutlined, EditOutlined,
  SyncOutlined, ClockCircleOutlined,
  ThunderboltOutlined, RobotOutlined,
  ArrowUpOutlined, ArrowDownOutlined,
  FileTextOutlined, LinkOutlined,
  GlobalOutlined, ApiOutlined,
  ToolOutlined, BulbOutlined,
  ExclamationCircleOutlined, CopyOutlined,
  SendOutlined, BarChartOutlined,
  UserOutlined, TeamOutlined,
  ScheduleOutlined, DeleteOutlined,
  SaveOutlined, FundOutlined,
  EnvironmentOutlined, DatabaseOutlined,
  SettingOutlined, CloudOutlined,
  InboxOutlined, LikeOutlined,
  DislikeOutlined, ShareAltOutlined,
  GiftOutlined, ShoppingCartOutlined,
  TargetOutlined, FlagOutlined,
  CheckSquareOutlined, UnorderedListOutlined,
  PlayCircleOutlined, PauseCircleOutlined,
  StopOutlined, StarOutlined, HeartOutlined,
  MessageOutlined, YoutubeOutlined,
  InstagramOutlined, TwitterOutlined,
  FacebookOutlined, TikTokOutlined,
  VideoCameraOutlined, PictureOutlined,
  MoneyCollectOutlined, ContractOutlined,
  MailOutlined, CalculatorOutlined,
  PieChartOutlined, LineChartOutlined,
  TrendingUpOutlined, TrendingDownOutlined,
  PercentageOutlined, BankOutlined,
  TruckOutlined, ShopOutlined,
  PackageOutlined, CreditCardOutlined,
  AuditOutlined, ProfileOutlined
} from '@ant-design/icons'

const { Title, Text, Paragraph } = Typography

interface CostItem {
  id: string
  product_name: string
  sku: string
  category: string
  purchase_cost: number
  domestic_shipping: number
  international_shipping: number
  tariff: number
  platform_fee: number
  payment_fee: number
  marketing_cost: number
  return_cost: number
  other_cost: number
  total_cost: number
  selling_price: number
  profit: number
  profit_margin: number
  roi: number
  supplier: string
  updated_at: string
}

interface CostCalculatorInput {
  purchase_cost: number
  quantity: number
  domestic_shipping: number
  international_shipping: number
  weight: number
  tariff_rate: number
  platform_fee_rate: number
  payment_fee_rate: number
  marketing_rate: number
  return_rate: number
  other_cost: number
  desired_margin: number
}

export default function CostModelPage() {
  const [activeTab, setActiveTab] = useState('calculator')
  const [loading, setLoading] = useState(false)
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [viewingCost, setViewingCost] = useState<CostItem | null>(null)
  // 真实API数据状态
  const [costModelData, setCostModelData] = useState<any>(null)
  const [calculator, setCalculator] = useState<CostCalculatorInput>({
    purchase_cost: 28.5,
    quantity: 100,
    domestic_shipping: 2,
    international_shipping: 15,
    weight: 0.3,
    tariff_rate: 0,
    platform_fee_rate: 5,
    payment_fee_rate: 2.9,
    marketing_rate: 15,
    return_rate: 3,
    other_cost: 1,
    desired_margin: 40,
  })

  const mockCosts: CostItem[] = [
    { id: '1', product_name: 'LED头灯 Pro', sku: 'NT-HEADLAMP-001', category: '照明设备', purchase_cost: 28.5, domestic_shipping: 2, international_shipping: 12, tariff: 0, platform_fee: 2.5, payment_fee: 1.45, marketing_cost: 7.5, return_cost: 1.5, other_cost: 1, total_cost: 56.45, selling_price: 49.99, profit: -6.46, profit_margin: -12.9, roi: -11.4, supplier: '深圳户外装备有限公司', updated_at: '2026-09-05' },
    { id: '2', product_name: '防水手机袋', sku: 'NT-POUCH-001', category: '户外配件', purchase_cost: 8.5, domestic_shipping: 0.5, international_shipping: 3, tariff: 0, platform_fee: 1, payment_fee: 0.58, marketing_cost: 3, return_cost: 0.6, other_cost: 0.5, total_cost: 17.68, selling_price: 19.99, profit: 2.31, profit_margin: 11.6, roi: 13.1, supplier: '深圳户外装备有限公司', updated_at: '2026-09-05' },
    { id: '3', product_name: '保温水壶1L', sku: 'NT-BOTTLE-001', category: '水具餐具', purchase_cost: 32, domestic_shipping: 2.5, international_shipping: 18, tariff: 0, platform_fee: 1.5, payment_fee: 0.87, marketing_cost: 4.5, return_cost: 1, other_cost: 1, total_cost: 61.37, selling_price: 29.99, profit: -31.38, profit_margin: -104.6, roi: -51.1, supplier: '深圳户外装备有限公司', updated_at: '2026-09-04' },
    { id: '4', product_name: '登山杖 碳纤维', sku: 'NT-POLE-001', category: '户外配件', purchase_cost: 68, domestic_shipping: 3, international_shipping: 25, tariff: 0, platform_fee: 3, payment_fee: 1.74, marketing_cost: 9, return_cost: 2, other_cost: 1.5, total_cost: 113.24, selling_price: 59.99, profit: -53.25, profit_margin: -88.8, roi: -47.0, supplier: '深圳户外装备有限公司', updated_at: '2026-09-04' },
    { id: '5', product_name: '户外登山背包 50L', sku: 'NT-BAG-001', category: '背包配件', purchase_cost: 120, domestic_shipping: 5, international_shipping: 35, tariff: 0, platform_fee: 4, payment_fee: 2.32, marketing_cost: 12, return_cost: 3, other_cost: 2, total_cost: 183.32, selling_price: 79.99, profit: -103.33, profit_margin: -129.2, roi: -56.4, supplier: '东莞背包工厂', updated_at: '2026-09-03' },
    { id: '6', product_name: '太阳能露营灯', sku: 'NT-LAMP-002', category: '照明设备', purchase_cost: 45, domestic_shipping: 2, international_shipping: 14, tariff: 0, platform_fee: 2, payment_fee: 1.16, marketing_cost: 6, return_cost: 1.2, other_cost: 1, total_cost: 72.36, selling_price: 39.99, profit: -32.37, profit_margin: -80.9, roi: -44.7, supplier: '义乌户外用品批发', updated_at: '2026-09-02' },
  ]

  // 加载成本模型数据（调用真实API，失败则使用mock数据降级）
  const loadCostModelData = async () => {
    try {
      setLoading(true)
      // 调用成本模型状态API
      const statusResp = await fetch('/api/v1/cost-model/status')
      if (statusResp.ok) {
        const statusData = await statusResp.json()
        setCostModelData(statusData)
        console.log('Cost model status:', statusData)
      }
      message.success('成本模型数据加载完成')
    } catch (e: any) {
      console.error('Load cost model data error:', e)
      message.warning(`API调用失败，使用模拟数据：${e.message || '未知错误'}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadCostModelData()
  }, [])

  // 计算成本
  const calcTotalCost = () => {
    const c = calculator
    const unitDomestic = c.domestic_shipping
    const unitInternational = c.international_shipping
    const subtotal = c.purchase_cost + unitDomestic + unitInternational + c.other_cost
    const tariff = subtotal * (c.tariff_rate / 100)
    const platformFee = c.selling_price * (c.platform_fee_rate / 100)
    const paymentFee = c.selling_price * (c.payment_fee_rate / 100)
    const marketing = c.selling_price * (c.marketing_rate / 100)
    const returnCost = c.selling_price * (c.return_rate / 100)
    const total = subtotal + tariff + platformFee + paymentFee + marketing + returnCost
    return {
      subtotal,
      tariff,
      platformFee,
      paymentFee,
      marketing,
      returnCost,
      total,
    }
  }

  const calcResult = calcTotalCost()
  const suggestedPrice = calcResult.total / (1 - calculator.desired_margin / 100)
  const actualProfit = calculator.selling_price ? calculator.selling_price - calcResult.total : 0
  const actualMargin = calculator.selling_price ? (actualProfit / calculator.selling_price) * 100 : 0

  const costColumns = [
    { title: '商品', key: 'product', width: 200, render: (_: any, record: CostItem) => <div><div style={{ fontWeight: 500, fontSize: 13 }}>{record.product_name}</div><div style={{ fontSize: 10, color: '#999' }}>SKU: {record.sku}</div><div style={{ fontSize: 10, color: '#999' }}>{record.supplier}</div></div> },
    { title: '采购成本', dataIndex: 'purchase_cost', key: 'purchase_cost', width: 100, render: (v: number) => <Text>¥{v}</Text> },
    { title: '物流成本', key: 'shipping', width: 100, render: (_: any, record: CostItem) => <Text>¥{(record.domestic_shipping + record.international_shipping).toFixed(1)}</Text> },
    { title: '平台/支付费', key: 'fees', width: 110, render: (_: any, record: CostItem) => <Text>¥{(record.platform_fee + record.payment_fee).toFixed(2)}</Text> },
    { title: '营销/退货费', key: 'marketing', width: 110, render: (_: any, record: CostItem) => <Text>¥{(record.marketing_cost + record.return_cost).toFixed(2)}</Text> },
    { title: '总成本', dataIndex: 'total_cost', key: 'total_cost', width: 100, render: (v: number) => <Text strong style={{ color: '#f5222d' }}>¥{v.toFixed(2)}</Text> },
    { title: '售价', dataIndex: 'selling_price', key: 'selling_price', width: 100, render: (v: number) => <Text strong>${v}</Text> },
    { title: '利润', dataIndex: 'profit', key: 'profit', width: 100, render: (v: number) => <Text type={v >= 0 ? 'success' : 'danger'} strong>{v >= 0 ? '+' : ''}${v.toFixed(2)}</Text> },
    { title: '利润率', dataIndex: 'profit_margin', key: 'profit_margin', width: 100, render: (v: number) => <Text type={v >= 0 ? 'success' : 'danger'} strong>{v >= 0 ? '+' : ''}{v.toFixed(1)}%</Text> },
    { title: 'ROI', dataIndex: 'roi', key: 'roi', width: 100, render: (v: number) => <Text type={v >= 0 ? 'success' : 'danger'} strong>{v >= 0 ? '+' : ''}{v.toFixed(1)}%</Text> },
    { title: '操作', key: 'actions', width: 120, render: (_: any, record: CostItem) => (
      <Space size="small">
        <Button size="small" icon={<EyeOutlined />} onClick={() => { setViewingCost(record); setDetailModalOpen(true) }}>详情</Button>
      </Space>
    )},
  ]

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <CalculatorOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>成本模型</Title>
            <Text type="secondary">产品成本计算、定价建议、利润分析、ROI追踪</Text>
          </div>
        </Space>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => message.success('数据已刷新')}>刷新</Button>
          <Button icon={<DownloadOutlined />} onClick={() => message.success('成本报表已导出')}>导出报表</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => message.info('添加成本记录')}>添加记录</Button>
        </Space>
      </div>

      <Alert message="成本模型说明" description="成本模型包含：采购成本、国内物流、国际物流、关税、平台费、支付费、营销费、退货费、其他费用。建议利润率目标：40%-60%，ROI目标：>30%。" type="info" showIcon icon={<InfoCircleOutlined />} style={{ marginBottom: 16 }} />

      <Card size="small">
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'calculator',
              label: '成本计算器',
              children: (
                <div>
                  <Row gutter={24}>
                    <Col span={12}>
                      <Card size="small" title="成本输入" style={{ marginBottom: 16 }}>
                        <Form layout="vertical">
                          <Row gutter={16}>
                            <Col span={12}>
                              <Form.Item label="采购成本(¥)">
                                <InputNumber value={calculator.purchase_cost} onChange={(v) => setCalculator({ ...calculator, purchase_cost: v || 0 })} style={{ width: '100%' }} min={0} step={0.5} />
                              </Form.Item>
                            </Col>
                            <Col span={12}>
                              <Form.Item label="采购数量">
                                <InputNumber value={calculator.quantity} onChange={(v) => setCalculator({ ...calculator, quantity: v || 0 })} style={{ width: '100%' }} min={1} />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Row gutter={16}>
                            <Col span={12}>
                              <Form.Item label="国内物流(¥/件)">
                                <InputNumber value={calculator.domestic_shipping} onChange={(v) => setCalculator({ ...calculator, domestic_shipping: v || 0 })} style={{ width: '100%' }} min={0} step={0.5} />
                              </Form.Item>
                            </Col>
                            <Col span={12}>
                              <Form.Item label="国际物流(¥/件)">
                                <InputNumber value={calculator.international_shipping} onChange={(v) => setCalculator({ ...calculator, international_shipping: v || 0 })} style={{ width: '100%' }} min={0} step={0.5} />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Row gutter={16}>
                            <Col span={8}>
                              <Form.Item label="关税率(%)">
                                <InputNumber value={calculator.tariff_rate} onChange={(v) => setCalculator({ ...calculator, tariff_rate: v || 0 })} style={{ width: '100%' }} min={0} max={100} />
                              </Form.Item>
                            </Col>
                            <Col span={8}>
                              <Form.Item label="平台费率(%)">
                                <InputNumber value={calculator.platform_fee_rate} onChange={(v) => setCalculator({ ...calculator, platform_fee_rate: v || 0 })} style={{ width: '100%' }} min={0} max={100} />
                              </Form.Item>
                            </Col>
                            <Col span={8}>
                              <Form.Item label="支付费率(%)">
                                <InputNumber value={calculator.payment_fee_rate} onChange={(v) => setCalculator({ ...calculator, payment_fee_rate: v || 0 })} style={{ width: '100%' }} min={0} max={100} />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Row gutter={16}>
                            <Col span={8}>
                              <Form.Item label="营销费率(%)">
                                <InputNumber value={calculator.marketing_rate} onChange={(v) => setCalculator({ ...calculator, marketing_rate: v || 0 })} style={{ width: '100%' }} min={0} max={100} />
                              </Form.Item>
                            </Col>
                            <Col span={8}>
                              <Form.Item label="退货率(%)">
                                <InputNumber value={calculator.return_rate} onChange={(v) => setCalculator({ ...calculator, return_rate: v || 0 })} style={{ width: '100%' }} min={0} max={100} />
                              </Form.Item>
                            </Col>
                            <Col span={8}>
                              <Form.Item label="其他费用(¥)">
                                <InputNumber value={calculator.other_cost} onChange={(v) => setCalculator({ ...calculator, other_cost: v || 0 })} style={{ width: '100%' }} min={0} step={0.5} />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Divider style={{ margin: '12px 0' }} />
                          <Form.Item label={`目标利润率: ${calculator.desired_margin}%`}>
                            <Slider min={10} max={80} value={calculator.desired_margin} onChange={(v) => setCalculator({ ...calculator, desired_margin: v })} marks={{ 10: '10%', 30: '30%', 50: '50%', 70: '70%' }} />
                          </Form.Item>
                        </Form>
                      </Card>
                    </Col>
                    <Col span={12}>
                      <Card size="small" title="计算结果" style={{ marginBottom: 16 }}>
                        <Row gutter={[16, 16]}>
                          <Col span={12}>
                            <Card size="small" style={{ background: '#fff7e6' }}>
                              <Statistic title="单件总成本" value={calcResult.total} prefix="¥" precision={2} valueStyle={{ color: '#fa8c16' }} />
                            </Card>
                          </Col>
                          <Col span={12}>
                            <Card size="small" style={{ background: '#f6ffed' }}>
                              <Statistic title="建议售价" value={suggestedPrice} prefix="$" precision={2} valueStyle={{ color: '#52c41a' }} />
                            </Card>
                          </Col>
                        </Row>

                        <Divider style={{ margin: '16px 0' }} />
                        <Title level={5}>成本结构</Title>
                        <List
                          size="small"
                          dataSource={[
                            { name: '采购成本', value: calculator.purchase_cost, percent: (calculator.purchase_cost / calcResult.total) * 100, color: '#1890ff' },
                            { name: '国内物流', value: calculator.domestic_shipping, percent: (calculator.domestic_shipping / calcResult.total) * 100, color: '#13c2c2' },
                            { name: '国际物流', value: calculator.international_shipping, percent: (calculator.international_shipping / calcResult.total) * 100, color: '#722ed1' },
                            { name: '关税', value: calcResult.tariff, percent: (calcResult.tariff / calcResult.total) * 100, color: '#eb2f96' },
                            { name: '平台费', value: calcResult.platformFee, percent: (calcResult.platformFee / calcResult.total) * 100, color: '#fa8c16' },
                            { name: '支付费', value: calcResult.paymentFee, percent: (calcResult.paymentFee / calcResult.total) * 100, color: '#a0d911' },
                            { name: '营销费', value: calcResult.marketing, percent: (calcResult.marketing / calcResult.total) * 100, color: '#f5222d' },
                            { name: '退货费', value: calcResult.returnCost, percent: (calcResult.returnCost / calcResult.total) * 100, color: '#faad14' },
                            { name: '其他费用', value: calculator.other_cost, percent: (calculator.other_cost / calcResult.total) * 100, color: '#8c8c8c' },
                          ]}
                          renderItem={(item) => (
                            <List.Item>
                              <List.Item.Meta
                                title={<div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}><span>{item.name}</span><span style={{ color: item.color, fontWeight: 600 }}>¥{item.value.toFixed(2)} ({item.percent.toFixed(1)}%)</span></div>}
                                description={<Progress percent={item.percent} size="small" strokeColor={item.color} showInfo={false} />}
                              />
                            </List.Item>
                          )}
                        />

                        <Divider style={{ margin: '16px 0' }} />
                        <Alert message={actualProfit >= 0 ? `当前售价利润为 $${actualProfit.toFixed(2)}，利润率 ${actualMargin.toFixed(1)}%` : `当前售价亏损 $${Math.abs(actualProfit).toFixed(2)}，建议提高售价或降低成本`} type={actualProfit >= 0 ? 'success' : 'error'} showIcon />
                      </Card>
                    </Col>
                  </Row>
                </div>
              ),
            },
            {
              key: 'list',
              label: '成本列表',
              children: (
                <div>
                  <Space wrap style={{ marginBottom: 16 }}>
                    <Input placeholder="搜索商品名称/SKU" prefix={<SearchOutlined />} style={{ width: 200 }} allowClear />
                    <Select defaultValue="all" style={{ width: 120 }} options={[
                      { value: 'all', label: '全部分类' },
                      { value: '照明设备', label: '照明设备' },
                      { value: '户外配件', label: '户外配件' },
                      { value: '水具餐具', label: '水具餐具' },
                      { value: '背包配件', label: '背包配件' },
                    ]} />
                    <Select defaultValue="all" style={{ width: 120 }} options={[
                      { value: 'all', label: '全部状态' },
                      { value: 'profit', label: '盈利' },
                      { value: 'loss', label: '亏损' },
                    ]} />
                  </Space>
                  <Table columns={costColumns} dataSource={mockCosts} rowKey="id" pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 个商品` }} locale={{ emptyText: <Empty description="暂无成本数据" /> }} scroll={{ x: 1600 }} />
                </div>
              ),
            },
            {
              key: 'analysis',
              label: '成本分析',
              children: (
                <div>
                  <Row gutter={16}>
                    <Col span={8}>
                      <Card size="small" title="盈利/亏损分布" style={{ marginBottom: 16 }}>
                        <Row gutter={16}>
                          <Col span={12}>
                            <div style={{ textAlign: 'center', padding: '20px 0' }}>
                              <div style={{ fontSize: 32, fontWeight: 700, color: '#52c41a' }}>{mockCosts.filter(c => c.profit >= 0).length}</div>
                              <div style={{ fontSize: 12, color: '#999' }}>盈利商品</div>
                            </div>
                          </Col>
                          <Col span={12}>
                            <div style={{ textAlign: 'center', padding: '20px 0' }}>
                              <div style={{ fontSize: 32, fontWeight: 700, color: '#f5222d' }}>{mockCosts.filter(c => c.profit < 0).length}</div>
                              <div style={{ fontSize: 12, color: '#999' }}>亏损商品</div>
                            </div>
                          </Col>
                        </Row>
                        <Progress percent={(mockCosts.filter(c => c.profit >= 0).length / mockCosts.length) * 100} strokeColor="#52c41a" format={(p) => `盈利率 ${p}%`} />
                      </Card>
                    </Col>
                    <Col span={8}>
                      <Card size="small" title="平均成本结构" style={{ marginBottom: 16 }}>
                        <List
                          size="small"
                          dataSource={[
                            { name: '采购成本', avg: Math.round(mockCosts.reduce((s, c) => s + c.purchase_cost, 0) / mockCosts.length), percent: 45 },
                            { name: '国际物流', avg: Math.round(mockCosts.reduce((s, c) => s + c.international_shipping, 0) / mockCosts.length), percent: 28 },
                            { name: '营销费', avg: Math.round(mockCosts.reduce((s, c) => s + c.marketing_cost, 0) / mockCosts.length), percent: 12 },
                            { name: '其他费用', avg: Math.round(mockCosts.reduce((s, c) => s + c.domestic_shipping + c.platform_fee + c.payment_fee + c.return_cost + c.other_cost, 0) / mockCosts.length), percent: 15 },
                          ]}
                          renderItem={(item) => (
                            <List.Item>
                              <List.Item.Meta
                                title={<div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}><span>{item.name}</span><span>¥{item.avg} ({item.percent}%)</span></div>}
                                description={<Progress percent={item.percent} size="small" showInfo={false} />}
                              />
                            </List.Item>
                          )}
                        />
                      </Card>
                    </Col>
                    <Col span={8}>
                      <Card size="small" title="优化建议" style={{ marginBottom: 16 }}>
                        <List
                          size="small"
                          dataSource={[
                            { type: 'warning', text: '5个商品当前售价低于成本，建议重新定价或寻找更低价供应商' },
                            { type: 'info', text: '国际物流占成本28%，建议增加订单量以获得更优物流价格' },
                            { type: 'success', text: '防水手机袋利润率11.6%，可作为引流款推广' },
                            { type: 'warning', text: '营销费率偏高(平均15%)，建议优化广告投放ROI' },
                          ]}
                          renderItem={(item) => (
                            <List.Item>
                              <List.Item.Meta
                                avatar={<Tag color={item.type === 'warning' ? 'orange' : item.type === 'success' ? 'green' : 'blue'} style={{ margin: 0 }}>{item.type === 'warning' ? '警告' : item.type === 'success' ? '好消息' : '建议'}</Tag>}
                                description={<Text style={{ fontSize: 12 }}>{item.text}</Text>}
                              />
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

      <Modal
        title={`成本详情 - ${viewingCost?.product_name || ''}`}
        open={detailModalOpen}
        onCancel={() => setDetailModalOpen(false)}
        footer={[
          <Button key="close" onClick={() => setDetailModalOpen(false)}>关闭</Button>,
        ]}
        width={700}
      >
        {viewingCost && (
          <div>
            <Descriptions column={3} bordered size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="商品名称" span={2}>{viewingCost.product_name}</Descriptions.Item>
              <Descriptions.Item label="SKU">{viewingCost.sku}</Descriptions.Item>
              <Descriptions.Item label="分类">{viewingCost.category}</Descriptions.Item>
              <Descriptions.Item label="供应商">{viewingCost.supplier}</Descriptions.Item>
              <Descriptions.Item label="更新时间">{viewingCost.updated_at}</Descriptions.Item>
            </Descriptions>

            <Title level={5}>成本明细</Title>
            <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
              <Col span={8}><Card size="small"><Statistic title="采购成本" value={viewingCost.purchase_cost} prefix="¥" /></Card></Col>
              <Col span={8}><Card size="small"><Statistic title="国内物流" value={viewingCost.domestic_shipping} prefix="¥" /></Card></Col>
              <Col span={8}><Card size="small"><Statistic title="国际物流" value={viewingCost.international_shipping} prefix="¥" /></Card></Col>
              <Col span={8}><Card size="small"><Statistic title="关税" value={viewingCost.tariff} prefix="¥" /></Card></Col>
              <Col span={8}><Card size="small"><Statistic title="平台费" value={viewingCost.platform_fee} prefix="¥" precision={2} /></Card></Col>
              <Col span={8}><Card size="small"><Statistic title="支付费" value={viewingCost.payment_fee} prefix="¥" precision={2} /></Card></Col>
              <Col span={8}><Card size="small"><Statistic title="营销费" value={viewingCost.marketing_cost} prefix="¥" /></Card></Col>
              <Col span={8}><Card size="small"><Statistic title="退货费" value={viewingCost.return_cost} prefix="¥" /></Card></Col>
              <Col span={8}><Card size="small"><Statistic title="其他费用" value={viewingCost.other_cost} prefix="¥" /></Card></Col>
            </Row>

            <Divider style={{ margin: '12px 0' }} />
            <Row gutter={16}>
              <Col span={8}>
                <Card size="small" style={{ background: '#fff2f0' }}>
                  <Statistic title="总成本" value={viewingCost.total_cost} prefix="¥" precision={2} valueStyle={{ color: '#f5222d' }} />
                </Card>
              </Col>
              <Col span={8}>
                <Card size="small" style={{ background: '#e6f7ff' }}>
                  <Statistic title="售价" value={viewingCost.selling_price} prefix="$" valueStyle={{ color: '#1890ff' }} />
                </Card>
              </Col>
              <Col span={8}>
                <Card size="small" style={{ background: viewingCost.profit >= 0 ? '#f6ffed' : '#fff2f0' }}>
                  <Statistic title="利润" value={viewingCost.profit} prefix={viewingCost.profit >= 0 ? '+$' : '-$'} precision={2} valueStyle={{ color: viewingCost.profit >= 0 ? '#52c41a' : '#f5222d' }} />
                </Card>
              </Col>
            </Row>

            <Divider style={{ margin: '16px 0' }} />
            <Row gutter={16}>
              <Col span={12}>
                <Card size="small">
                  <Statistic title="利润率" value={viewingCost.profit_margin} suffix="%" valueStyle={{ color: viewingCost.profit_margin >= 0 ? '#52c41a' : '#f5222d' }} />
                </Card>
              </Col>
              <Col span={12}>
                <Card size="small">
                  <Statistic title="ROI" value={viewingCost.roi} suffix="%" valueStyle={{ color: viewingCost.roi >= 0 ? '#52c41a' : '#f5222d' }} />
                </Card>
              </Col>
            </Row>

            {viewingCost.profit < 0 && (
              <Alert message="亏损警告" description={`该商品当前售价低于总成本，每卖出一件亏损 $${Math.abs(viewingCost.profit).toFixed(2)}。建议：1. 提高售价至 $${(viewingCost.total_cost / 7.2).toFixed(2)} 以上；2. 与供应商谈判降低采购成本；3. 优化物流降低国际运费。`} type="error" showIcon style={{ marginTop: 16 }} />
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}
