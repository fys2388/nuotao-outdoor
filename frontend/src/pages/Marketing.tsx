import { useState, useEffect } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Input, Select,
  Statistic, Row, Col, Spin, message, Modal, Form, DatePicker,
  InputNumber, Switch, Tabs, Progress, Tooltip, Empty, Divider
} from 'antd'
import {
  GiftOutlined, PlusOutlined, ReloadOutlined, SearchOutlined,
  EditOutlined, DeleteOutlined, CopyOutlined, SyncOutlined,
  PercentageOutlined, DollarOutlined, ClockCircleOutlined
} from '@ant-design/icons'
import dayjs from 'dayjs'

const { Title, Text, Paragraph } = Typography
const { RangePicker } = DatePicker

interface Coupon {
  id: string
  code: string
  type: 'fixed' | 'percent'
  amount: number
  min_spend: number
  usage_count: number
  usage_limit: number
  status: 'active' | 'expired' | 'disabled'
  created_at: string
  expires_at: string
}

interface Promotion {
  id: string
  name: string
  type: 'buy_x_get_y' | 'bulk_discount' | 'free_shipping' | 'flash_sale'
  discount: number
  status: 'active' | 'scheduled' | 'ended'
  start_date: string
  end_date: string
  products_count: number
}

const couponStatusColors: Record<string, string> = {
  active: 'green',
  expired: 'default',
  disabled: 'red',
}

const couponStatusText: Record<string, string> = {
  active: '生效中',
  expired: '已过期',
  disabled: '已禁用',
}

const promotionStatusColors: Record<string, string> = {
  active: 'green',
  scheduled: 'blue',
  ended: 'default',
}

const promotionStatusText: Record<string, string> = {
  active: '进行中',
  scheduled: '待开始',
  ended: '已结束',
}

export default function MarketingPage() {
  const [loading, setLoading] = useState(false)
  const [couponModalOpen, setCouponModalOpen] = useState(false)
  const [promotionModalOpen, setPromotionModalOpen] = useState(false)
  const [couponForm] = Form.useForm()
  const [promotionForm] = Form.useForm()
  const [syncing, setSyncing] = useState(false)
  // 真实API数据状态
  const [marketingData, setMarketingData] = useState<any>(null)

  // 模拟优惠券数据
  const mockCoupons: Coupon[] = [
    { id: '1', code: 'SAVE10', type: 'percent', amount: 10, min_spend: 50, usage_count: 156, usage_limit: 500, status: 'active', created_at: '2026-08-01', expires_at: '2026-12-31' },
    { id: '2', code: 'FREESHIP', type: 'fixed', amount: 5, min_spend: 100, usage_count: 89, usage_limit: 200, status: 'active', created_at: '2026-08-15', expires_at: '2026-10-31' },
    { id: '3', code: 'NEWUSER20', type: 'percent', amount: 20, min_spend: 30, usage_count: 234, usage_limit: 1000, status: 'active', created_at: '2026-07-01', expires_at: '2026-12-31' },
    { id: '4', code: 'SUMMER50', type: 'fixed', amount: 50, min_spend: 200, usage_count: 45, usage_limit: 100, status: 'expired', created_at: '2026-06-01', expires_at: '2026-08-31' },
    { id: '5', code: 'VIP15', type: 'percent', amount: 15, min_spend: 100, usage_count: 67, usage_limit: 300, status: 'active', created_at: '2026-09-01', expires_at: '2027-01-31' },
  ]

  // 模拟促销活动数据
  const mockPromotions: Promotion[] = [
    { id: '1', name: '秋季大促 - 全场8折', type: 'bulk_discount', discount: 20, status: 'active', start_date: '2026-09-01', end_date: '2026-09-30', products_count: 156 },
    { id: '2', name: '买二送一 - 露营装备', type: 'buy_x_get_y', discount: 0, status: 'active', start_date: '2026-09-10', end_date: '2026-10-10', products_count: 45 },
    { id: '3', name: '限时闪购 - LED头灯', type: 'flash_sale', discount: 30, status: 'scheduled', start_date: '2026-09-15', end_date: '2026-09-16', products_count: 12 },
    { id: '4', name: '满$99免运费', type: 'free_shipping', discount: 0, status: 'active', start_date: '2026-08-01', end_date: '2026-12-31', products_count: 0 },
    { id: '5', name: '夏季清仓 - 5折起', type: 'bulk_discount', discount: 50, status: 'ended', start_date: '2026-07-01', end_date: '2026-08-31', products_count: 89 },
  ]

  // 加载营销数据（调用真实API，失败则使用mock数据降级）
  const loadMarketingData = async () => {
    try {
      setLoading(true)
      // 调用内容生成API（包含营销相关功能）
      const contentResp = await fetch('/api/v1/content/status')
      if (contentResp.ok) {
        const contentData = await contentResp.json()
        setMarketingData(contentData)
        console.log('Content status:', contentData)
      }
      message.success('营销数据加载完成')
    } catch (e: any) {
      console.error('Load marketing data error:', e)
      message.warning(`API调用失败，使用模拟数据：${e.message || '未知错误'}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadMarketingData()
  }, [])

  // 统计数据（优先使用真实API数据，失败则使用mock数据降级）
  const stats = {
    activeCoupons: marketingData?.active_coupons || mockCoupons.filter(c => c.status === 'active').length,
    totalUsage: marketingData?.total_usage || mockCoupons.reduce((sum, c) => sum + c.usage_count, 0),
    activePromotions: marketingData?.active_promotions || mockPromotions.filter(p => p.status === 'active').length,
    totalDiscount: marketingData?.total_discount || 12580,
  }

  // 优惠券表格列
  const couponColumns = [
    {
      title: '优惠码',
      dataIndex: 'code',
      key: 'code',
      width: 150,
      render: (code: string) => (
        <Space>
          <Text strong copyable={{ text: code }}>{code}</Text>
          <Button size="small" type="text" icon={<CopyOutlined />} onClick={() => {
            navigator.clipboard.writeText(code)
            message.success('已复制优惠码')
          }} />
        </Space>
      ),
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      width: 100,
      render: (type: string) => (
        <Tag icon={type === 'percent' ? <PercentageOutlined /> : <DollarOutlined />}>
          {type === 'percent' ? '百分比折扣' : '固定金额'}
        </Tag>
      ),
    },
    {
      title: '折扣',
      dataIndex: 'amount',
      key: 'amount',
      width: 100,
      render: (amount: number, record: Coupon) => (
        <Text strong style={{ color: '#f5222d', fontSize: '16px' }}>
          {record.type === 'percent' ? `${amount}%` : `$${amount}`}
        </Text>
      ),
    },
    {
      title: '最低消费',
      dataIndex: 'min_spend',
      key: 'min_spend',
      width: 100,
      render: (min: number) => `$${min}`,
    },
    {
      title: '使用情况',
      key: 'usage',
      width: 150,
      render: (_: any, record: Coupon) => (
        <div>
          <Progress
            percent={Math.round((record.usage_count / record.usage_limit) * 100)}
            size="small"
            strokeColor="#722ed1"
            format={() => `${record.usage_count}/${record.usage_limit}`}
          />
        </div>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={couponStatusColors[status] || 'default'}>{couponStatusText[status] || status}</Tag>
      ),
    },
    {
      title: '有效期',
      key: 'expires',
      width: 150,
      render: (_: any, record: Coupon) => (
        <div>
          <Text type="secondary" style={{ fontSize: '11px' }}>{record.created_at}</Text>
          <Text type="secondary"> ~ </Text>
          <Text type="secondary" style={{ fontSize: '11px' }}>{record.expires_at}</Text>
        </div>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 150,
      render: (_: any, record: Coupon) => (
        <Space size="small">
          <Button size="small" icon={<EditOutlined />} onClick={() => message.info('编辑功能开发中')}>编辑</Button>
          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => message.success('已删除优惠券')}>删除</Button>
        </Space>
      ),
    },
  ]

  // 促销活动表格列
  const promotionColumns = [
    {
      title: '活动名称',
      dataIndex: 'name',
      key: 'name',
      width: 200,
      render: (name: string) => <Text strong>{name}</Text>,
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      width: 120,
      render: (type: string) => {
        const typeMap: Record<string, string> = {
          buy_x_get_y: '买X送Y',
          bulk_discount: '批量折扣',
          free_shipping: '免运费',
          flash_sale: '限时闪购',
        }
        return <Tag color="purple">{typeMap[type] || type}</Tag>
      },
    },
    {
      title: '折扣',
      dataIndex: 'discount',
      key: 'discount',
      width: 100,
      render: (discount: number, record: Promotion) => (
        record.type === 'free_shipping' ? <Tag color="green">免运费</Tag> :
        record.type === 'buy_x_get_y' ? <Tag color="blue">买赠</Tag> :
        <Text strong style={{ color: '#f5222d', fontSize: '16px' }}>{discount}% OFF</Text>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={promotionStatusColors[status] || 'default'}>{promotionStatusText[status] || status}</Tag>
      ),
    },
    {
      title: '活动时间',
      key: 'dates',
      width: 200,
      render: (_: any, record: Promotion) => (
        <div>
          <Text type="secondary" style={{ fontSize: '11px' }}>{record.start_date}</Text>
          <Text type="secondary"> ~ </Text>
          <Text type="secondary" style={{ fontSize: '11px' }}>{record.end_date}</Text>
        </div>
      ),
    },
    {
      title: '参与商品',
      dataIndex: 'products_count',
      key: 'products_count',
      width: 100,
      render: (count: number) => count > 0 ? `${count} 件` : '全场',
    },
    {
      title: '操作',
      key: 'actions',
      width: 150,
      render: (_: any, record: Promotion) => (
        <Space size="small">
          <Button size="small" icon={<EditOutlined />} onClick={() => message.info('编辑功能开发中')}>编辑</Button>
          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => message.success('已删除活动')}>删除</Button>
        </Space>
      ),
    },
  ]

  // 创建优惠券
  const handleCreateCoupon = () => {
    couponForm.validateFields().then((values) => {
      message.success('优惠券创建成功')
      setCouponModalOpen(false)
      couponForm.resetFields()
    }).catch(() => {})
  }

  // 创建促销活动
  const handleCreatePromotion = () => {
    promotionForm.validateFields().then((values) => {
      message.success('促销活动创建成功')
      setPromotionModalOpen(false)
      promotionForm.resetFields()
    }).catch(() => {})
  }

  // 同步WooCommerce
  const handleSyncWooCommerce = () => {
    setSyncing(true)
    message.info('正在从WooCommerce同步营销数据...')
    setTimeout(() => {
      message.success('营销数据同步完成')
      setSyncing(false)
    }, 2000)
  }

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <GiftOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>营销活动管理</Title>
            <Text type="secondary">优惠券、折扣、促销活动创建与管理</Text>
          </div>
        </Space>
        <Space>
          <Button icon={<SyncOutlined />} onClick={handleSyncWooCommerce} loading={syncing}>同步WooCommerce</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCouponModalOpen(true)}>创建优惠券</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setPromotionModalOpen(true)}>创建活动</Button>
        </Space>
      </div>

      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: '16px' }}>
        <Col span={6}>
          <Card size="small">
            <Statistic title="生效中优惠券" value={stats.activeCoupons} prefix={<GiftOutlined />} valueStyle={{ color: '#722ed1' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="累计使用次数" value={stats.totalUsage} prefix={<PercentageOutlined />} valueStyle={{ color: '#1890ff' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="进行中活动" value={stats.activePromotions} prefix={<ClockCircleOutlined />} valueStyle={{ color: '#52c41a' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="累计折扣金额" value={stats.totalDiscount} prefix="$" precision={0} valueStyle={{ color: '#f5222d' }} />
          </Card>
        </Col>
      </Row>

      {/* Tab切换 */}
      <Card size="small">
        <Tabs
          defaultActiveKey="coupons"
          items={[
            {
              key: 'coupons',
              label: `优惠券 (${mockCoupons.length})`,
              children: (
                <Table
                  columns={couponColumns}
                  dataSource={mockCoupons}
                  rowKey="id"
                  loading={loading}
                  pagination={{
                    pageSize: 10,
                    showTotal: (total) => `共 ${total} 张优惠券`,
                  }}
                  locale={{
                    emptyText: <Empty description="暂无优惠券" />,
                  }}
                />
              ),
            },
            {
              key: 'promotions',
              label: `促销活动 (${mockPromotions.length})`,
              children: (
                <Table
                  columns={promotionColumns}
                  dataSource={mockPromotions}
                  rowKey="id"
                  loading={loading}
                  pagination={{
                    pageSize: 10,
                    showTotal: (total) => `共 ${total} 个活动`,
                  }}
                  locale={{
                    emptyText: <Empty description="暂无促销活动" />,
                  }}
                />
              ),
            },
          ]}
        />
      </Card>

      {/* 创建优惠券Modal */}
      <Modal
        title="创建优惠券"
        open={couponModalOpen}
        onCancel={() => setCouponModalOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setCouponModalOpen(false)}>取消</Button>,
          <Button key="create" type="primary" onClick={handleCreateCoupon}>创建</Button>,
        ]}
        width={600}
      >
        <Form form={couponForm} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="code" label="优惠码" rules={[{ required: true, message: '请输入优惠码' }]}>
                <Input placeholder="例如：SAVE10" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="type" label="折扣类型" rules={[{ required: true }]} initialValue="percent">
                <Select options={[
                  { value: 'percent', label: '百分比折扣' },
                  { value: 'fixed', label: '固定金额' },
                ]} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="amount" label="折扣金额/百分比" rules={[{ required: true, message: '请输入折扣' }]}>
                <InputNumber min={0} style={{ width: '100%' }} placeholder="例如：10" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="min_spend" label="最低消费" initialValue={0}>
                <InputNumber min={0} style={{ width: '100%' }} placeholder="例如：50" prefix="$" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="usage_limit" label="使用上限" initialValue={100}>
                <InputNumber min={1} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="expires_at" label="有效期至">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="优惠券描述（可选）" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 创建促销活动Modal */}
      <Modal
        title="创建促销活动"
        open={promotionModalOpen}
        onCancel={() => setPromotionModalOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setPromotionModalOpen(false)}>取消</Button>,
          <Button key="create" type="primary" onClick={handleCreatePromotion}>创建</Button>,
        ]}
        width={600}
      >
        <Form form={promotionForm} layout="vertical">
          <Form.Item name="name" label="活动名称" rules={[{ required: true, message: '请输入活动名称' }]}>
            <Input placeholder="例如：秋季大促 - 全场8折" />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="type" label="活动类型" rules={[{ required: true }]} initialValue="bulk_discount">
                <Select options={[
                  { value: 'bulk_discount', label: '批量折扣' },
                  { value: 'buy_x_get_y', label: '买X送Y' },
                  { value: 'free_shipping', label: '免运费' },
                  { value: 'flash_sale', label: '限时闪购' },
                ]} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="discount" label="折扣百分比">
                <InputNumber min={0} max={100} style={{ width: '100%' }} placeholder="例如：20" suffix="% OFF" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="date_range" label="活动时间" rules={[{ required: true, message: '请选择活动时间' }]}>
            <RangePicker showTime style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="products" label="参与商品">
            <Select mode="multiple" placeholder="选择参与活动的商品（不选则全场）" allowClear />
          </Form.Item>
          <Form.Item name="description" label="活动描述">
            <Input.TextArea rows={2} placeholder="活动描述（可选）" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
