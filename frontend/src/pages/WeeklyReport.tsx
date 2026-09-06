import { useState } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Input, Select,
  Statistic, Row, Col, Spin, message, Modal, Descriptions,
  Badge, Tooltip, Empty, Tabs, Progress, Divider, Alert,
  Timeline, List, Avatar, Segmented
} from 'antd'
import {
  FileTextOutlined, ReloadOutlined, SearchOutlined,
  EyeOutlined, PlusOutlined, DownloadOutlined,
  CheckCircleOutlined, WarningOutlined,
  SyncOutlined, ClockCircleOutlined,
  DollarOutlined, BarChartOutlined, ThunderboltOutlined,
  RobotOutlined, ArrowUpOutlined, ArrowDownOutlined,
  ShoppingCartOutlined, UserOutlined, GiftOutlined,
  TruckOutlined, CustomerServiceOutlined, FundOutlined,
  SendOutlined,
  CalendarOutlined, BulbOutlined, ExclamationCircleOutlined
} from '@ant-design/icons'

const { Title, Text, Paragraph } = Typography

interface WeeklyReport {
  id: string
  week: string
  start_date: string
  end_date: string
  status: 'generated' | 'generating' | 'draft'
  revenue: number
  orders: number
  profit: number
  conversion_rate: number
  new_customers: number
  avg_order_value: number
  return_rate: number
  ai_summary: string
  highlights: string[]
  issues: string[]
  suggestions: string[]
  generated_at: string
}

export default function WeeklyReportPage() {
  const [activeTab, setActiveTab] = useState('current')
  const [loading, setLoading] = useState(false)
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [viewingReport, setViewingReport] = useState<WeeklyReport | null>(null)
  const [generating, setGenerating] = useState(false)
  const [period, setPeriod] = useState('this-week')
  // 真实API对接状态
  const [realReports, setRealReports] = useState<any[]>([])
  const [reportsLoading, setReportsLoading] = useState(false)
  const [generateLoading, setGenerateLoading] = useState(false)

  const mockReports: WeeklyReport[] = [
    {
      id: '1', week: '2026年第36周', start_date: '2026-09-01', end_date: '2026-09-07', status: 'generated',
      revenue: 125680, orders: 342, profit: 38900, conversion_rate: 2.8, new_customers: 89, avg_order_value: 367.5, return_rate: 3.2,
      ai_summary: '本周整体表现良好，收入环比增长15.3%，主要得益于LED头灯新品上架和秋季营销活动。转化率提升至2.8%，但退货率略有上升，需关注产品质量和描述准确性。',
      highlights: ['LED头灯新品上架首周销量突破120件，成为爆款', '秋季营销活动带来35%的流量增长', '新客户获取成本下降12%，ROI提升至4.2', '客户满意度评分达到4.6/5.0'],
      issues: ['退货率上升至3.2%，主要集中在帐篷类产品', '2个SKU库存不足，导致15笔订单延迟发货', '欧洲物流时效延长，平均配送时间增加2天'],
      suggestions: ['增加帐篷类产品的质检环节，降低退货率', '对热销SKU设置安全库存预警，避免缺货', '考虑增加欧洲海外仓，缩短配送时效', '下周重点推广登山杖和保温水壶，迎接秋季徒步旺季'],
      generated_at: '2026-09-08 08:00:00',
    },
    {
      id: '2', week: '2026年第35周', start_date: '2026-08-25', end_date: '2026-08-31', status: 'generated',
      revenue: 109000, orders: 298, profit: 32500, conversion_rate: 2.5, new_customers: 76, avg_order_value: 365.8, return_rate: 2.8,
      ai_summary: '本周收入稳定增长，转化率略有提升。防水手机袋持续热销，成为引流款。但客单价略有下降，建议增加捆绑销售和高客单价产品推荐。',
      highlights: ['防水手机袋周销量突破500件，引流效果显著', '网站跳出率下降8%，用户停留时间增加', 'EDM营销打开率达到32%，高于行业平均'],
      issues: ['客单价下降5%，低客单价产品占比增加', '3个产品页面加载速度慢，影响用户体验'],
      suggestions: ['优化产品页面加载速度，目标<3秒', '增加捆绑销售套餐，提升客单价', '对高价值客户推送VIP专属优惠'],
      generated_at: '2026-09-01 08:00:00',
    },
    {
      id: '3', week: '2026年第34周', start_date: '2026-08-18', end_date: '2026-08-24', status: 'generated',
      revenue: 98500, orders: 275, profit: 28900, conversion_rate: 2.3, new_customers: 68, avg_order_value: 358.2, return_rate: 2.5,
      ai_summary: '本周收入环比增长8.5%，新客户获取稳定。SEO优化效果开始显现，自然搜索流量增长15%。建议继续加强内容营销和外链建设。',
      highlights: ['自然搜索流量增长15%，SEO优化效果显著', '新客户转化率提升至3.1%', '客户复购率达到28%，高于行业平均'],
      issues: ['移动端转化率低于桌面端15%', '部分产品评价不足，影响购买决策'],
      suggestions: ['优化移动端购物体验，提升转化率', '主动邀请已购买客户留下评价', '增加产品视频展示，提升购买信心'],
      generated_at: '2026-08-25 08:00:00',
    },
  ]

  // 获取真实周报列表
  const fetchRealReports = async () => {
    try {
      setReportsLoading(true)
      const resp = await fetch('/api/v1/weekly-report?limit=10')
      const data = await resp.json()
      if (data.success && data.data?.reports) {
        setRealReports(data.data.reports)
      }
    } catch (e: any) {
      console.error('Fetch weekly reports error:', e)
    } finally {
      setReportsLoading(false)
    }
  }

  // 生成周报
  const handleGenerateReport = async () => {
    try {
      setGenerateLoading(true)
      const resp = await fetch('/api/v1/weekly-report/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ period: period }),
      })
      const data = await resp.json()
      if (data.success) {
        message.success('周报生成成功')
        fetchRealReports()
      } else {
        message.error(`周报生成失败：${data.error || '未知错误'}`)
      }
    } catch (e: any) {
      console.error('Generate weekly report error:', e)
      message.error(`周报生成失败：${e.message || '网络错误'}`)
    } finally {
      setGenerateLoading(false)
    }
  }

  const currentReport = mockReports[0]

  const stats = {
    revenue: currentReport.revenue,
    revenueGrowth: 15.3,
    orders: currentReport.orders,
    ordersGrowth: 14.8,
    profit: currentReport.profit,
    profitGrowth: 19.7,
    conversion: currentReport.conversion_rate,
    conversionGrowth: 12.0,
    newCustomers: currentReport.new_customers,
    newCustomersGrowth: 17.1,
    avgOrder: currentReport.avg_order_value,
    avgOrderGrowth: 0.5,
    returnRate: currentReport.return_rate,
    returnRateGrowth: 14.3,
  }

  const reportColumns = [
    { title: '周次', dataIndex: 'week', key: 'week', width: 150, render: (w: string, r: WeeklyReport) => <div><div style={{ fontWeight: 500 }}>{w}</div><div style={{ fontSize: 10, color: '#999' }}>{r.start_date} ~ {r.end_date}</div></div> },
    { title: '收入', dataIndex: 'revenue', key: 'revenue', width: 120, render: (v: number) => <Text strong style={{ color: '#52c41a' }}>¥{v.toLocaleString()}</Text> },
    { title: '订单数', dataIndex: 'orders', key: 'orders', width: 100, render: (v: number) => <Text>{v}单</Text> },
    { title: '利润', dataIndex: 'profit', key: 'profit', width: 120, render: (v: number) => <Text strong style={{ color: '#1890ff' }}>¥{v.toLocaleString()}</Text> },
    { title: '转化率', dataIndex: 'conversion_rate', key: 'conversion_rate', width: 100, render: (v: number) => <Text>{v}%</Text> },
    { title: '新客户', dataIndex: 'new_customers', key: 'new_customers', width: 100, render: (v: number) => <Text>{v}人</Text> },
    { title: '退货率', dataIndex: 'return_rate', key: 'return_rate', width: 100, render: (v: number) => <Text type={v > 3 ? 'danger' : 'secondary'}>{v}%</Text> },
    { title: '状态', dataIndex: 'status', key: 'status', width: 100, render: (s: string) => <Tag color={s === 'generated' ? 'green' : s === 'generating' ? 'blue' : 'orange'} icon={s === 'generating' ? <SyncOutlined spin /> : null}>{s === 'generated' ? '已生成' : s === 'generating' ? '生成中' : '草稿'}</Tag> },
    { title: '生成时间', dataIndex: 'generated_at', key: 'generated_at', width: 160, render: (t: string) => <Text type="secondary" style={{ fontSize: 11 }}>{t}</Text> },
    { title: '操作', key: 'actions', width: 150, render: (_: any, record: WeeklyReport) => (
      <Space size="small">
        <Button size="small" icon={<EyeOutlined />} onClick={() => { setViewingReport(record); setDetailModalOpen(true) }}>查看</Button>
        <Button size="small" icon={<DownloadOutlined />} onClick={() => message.success('周报已导出')}>导出</Button>
      </Space>
    )},
  ]

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <RobotOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>AI经营周报</Title>
            <Text type="secondary">AI自动生成经营分析、问题诊断、优化建议</Text>
          </div>
        </Space>
        <Space>
          <Segmented value={period} onChange={setPeriod} options={[
            { label: '本周', value: 'this-week' },
            { label: '上周', value: 'last-week' },
            { label: '本月', value: 'this-month' },
          ]} />
          <Button icon={<ReloadOutlined />} onClick={fetchRealReports} loading={reportsLoading}>刷新</Button>
          <Button icon={<DownloadOutlined />} onClick={() => message.success('周报已导出PDF')}>导出PDF</Button>
          <Button type="primary" icon={<ThunderboltOutlined />} loading={generateLoading} onClick={handleGenerateReport}>生成周报</Button>
        </Space>
      </div>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Alert
          message={`${currentReport.week} 经营周报已生成`}
          description={currentReport.ai_summary}
          type="info"
          showIcon
          icon={<RobotOutlined />}
          action={<Button size="small" type="primary" onClick={() => setActiveTab('history')}>查看历史周报</Button>}
        />
      </Card>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'current',
            label: '本周概览',
            children: (
              <div>
                <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
                  <Col span={6}>
                    <Card size="small">
                      <Statistic title="本周收入" value={stats.revenue} prefix="¥" valueStyle={{ color: '#52c41a' }} suffix={<span style={{ fontSize: 12, color: '#52c41a' }}><ArrowUpOutlined /> {stats.revenueGrowth}%</span>} />
                    </Card>
                  </Col>
                  <Col span={6}>
                    <Card size="small">
                      <Statistic title="订单数" value={stats.orders} suffix="单" valueStyle={{ color: '#1890ff' }} prefix={<span style={{ fontSize: 12, color: '#52c41a' }}><ArrowUpOutlined /> {stats.ordersGrowth}%</span>} />
                    </Card>
                  </Col>
                  <Col span={6}>
                    <Card size="small">
                      <Statistic title="利润" value={stats.profit} prefix="¥" valueStyle={{ color: '#722ed1' }} suffix={<span style={{ fontSize: 12, color: '#52c41a' }}><ArrowUpOutlined /> {stats.profitGrowth}%</span>} />
                    </Card>
                  </Col>
                  <Col span={6}>
                    <Card size="small">
                      <Statistic title="转化率" value={stats.conversion} suffix="%" valueStyle={{ color: '#fa8c16' }} prefix={<span style={{ fontSize: 12, color: '#52c41a' }}><ArrowUpOutlined /> {stats.conversionGrowth}%</span>} />
                    </Card>
                  </Col>
                </Row>

                <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
                  <Col span={6}>
                    <Card size="small">
                      <Statistic title="新客户" value={stats.newCustomers} suffix="人" valueStyle={{ color: '#13c2c2' }} prefix={<span style={{ fontSize: 12, color: '#52c41a' }}><ArrowUpOutlined /> {stats.newCustomersGrowth}%</span>} />
                    </Card>
                  </Col>
                  <Col span={6}>
                    <Card size="small">
                      <Statistic title="客单价" value={stats.avgOrder} valueStyle={{ color: '#eb2f96' }} prefix={<span style={{ fontSize: 12, color: '#52c41a' }}><ArrowUpOutlined /> {stats.avgOrderGrowth}%</span>} />
                    </Card>
                  </Col>
                  <Col span={6}>
                    <Card size="small">
                      <Statistic title="退货率" value={stats.returnRate} suffix="%" valueStyle={{ color: '#f5222d' }} prefix={<span style={{ fontSize: 12, color: '#f5222d' }}><ArrowUpOutlined /> {stats.returnRateGrowth}%</span>} />
                    </Card>
                  </Col>
                  <Col span={6}>
                    <Card size="small">
                      <Statistic title="毛利率" value={30.9} suffix="%" valueStyle={{ color: '#52c41a' }} />
                    </Card>
                  </Col>
                </Row>

                <Row gutter={16}>
                  <Col span={8}>
                    <Card size="small" title={<span><CheckCircleOutlined style={{ color: '#52c41a', marginRight: 8 }} />本周亮点</span>}>
                      <List
                        size="small"
                        dataSource={currentReport.highlights}
                        renderItem={(item, idx) => (
                          <List.Item>
                            <List.Item.Meta
                              avatar={<Avatar size="small" style={{ backgroundColor: '#52c41a' }}>{idx + 1}</Avatar>}
                              description={<Text style={{ fontSize: 12 }}>{item}</Text>}
                            />
                          </List.Item>
                        )}
                      />
                    </Card>
                  </Col>
                  <Col span={8}>
                    <Card size="small" title={<span><ExclamationCircleOutlined style={{ color: '#faad14', marginRight: 8 }} />存在问题</span>}>
                      <List
                        size="small"
                        dataSource={currentReport.issues}
                        renderItem={(item, idx) => (
                          <List.Item>
                            <List.Item.Meta
                              avatar={<Avatar size="small" style={{ backgroundColor: '#faad14' }}>{idx + 1}</Avatar>}
                              description={<Text style={{ fontSize: 12 }}>{item}</Text>}
                            />
                          </List.Item>
                        )}
                      />
                    </Card>
                  </Col>
                  <Col span={8}>
                    <Card size="small" title={<span><BulbOutlined style={{ color: '#1890ff', marginRight: 8 }} />AI建议</span>}>
                      <List
                        size="small"
                        dataSource={currentReport.suggestions}
                        renderItem={(item, idx) => (
                          <List.Item>
                            <List.Item.Meta
                              avatar={<Avatar size="small" style={{ backgroundColor: '#1890ff' }}>{idx + 1}</Avatar>}
                              description={<Text style={{ fontSize: 12 }}>{item}</Text>}
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
          {
            key: 'analysis',
            label: '深度分析',
            children: (
              <div>
                <Row gutter={16}>
                  <Col span={12}>
                    <Card size="small" title="销售趋势" style={{ marginBottom: 16 }}>
                      <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#fafafa', borderRadius: 8 }}>
                        <Text type="secondary">销售趋势图表（接入真实数据后展示）</Text>
                      </div>
                    </Card>
                  </Col>
                  <Col span={12}>
                    <Card size="small" title="品类销售占比" style={{ marginBottom: 16 }}>
                      <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#fafafa', borderRadius: 8 }}>
                        <Text type="secondary">品类占比图表（接入真实数据后展示）</Text>
                      </div>
                    </Card>
                  </Col>
                </Row>
                <Row gutter={16}>
                  <Col span={12}>
                    <Card size="small" title="热销商品TOP5">
                      <List
                        size="small"
                        dataSource={[
                          { name: 'LED头灯 Pro', sales: 120, revenue: 5999 },
                          { name: '防水手机袋', sales: 520, revenue: 10395 },
                          { name: '户外登山背包', sales: 85, revenue: 6799 },
                          { name: '保温水壶1L', sales: 95, revenue: 2849 },
                          { name: '登山杖 碳纤维', sales: 68, revenue: 4079 },
                        ]}
                        renderItem={(item, idx) => (
                          <List.Item>
                            <List.Item.Meta
                              avatar={<Avatar size="small" style={{ backgroundColor: idx < 3 ? '#f5222d' : '#1890ff' }}>{idx + 1}</Avatar>}
                              title={<Text style={{ fontSize: 13 }}>{item.name}</Text>}
                              description={<Text type="secondary" style={{ fontSize: 11 }}>销量 {item.sales}件 · 收入 ¥{item.revenue.toLocaleString()}</Text>}
                            />
                          </List.Item>
                        )}
                      />
                    </Card>
                  </Col>
                  <Col span={12}>
                    <Card size="small" title="流量来源分析">
                      <List
                        size="small"
                        dataSource={[
                          { name: '自然搜索', visits: 8500, rate: 35.2 },
                          { name: '直接访问', visits: 5200, rate: 21.5 },
                          { name: '社交媒体', visits: 4800, rate: 19.9 },
                          { name: 'EDM营销', visits: 3200, rate: 13.3 },
                          { name: '广告投放', visits: 2400, rate: 10.1 },
                        ]}
                        renderItem={(item) => (
                          <List.Item>
                            <List.Item.Meta
                              title={<div style={{ display: 'flex', justifyContent: 'space-between' }}><Text style={{ fontSize: 13 }}>{item.name}</Text><Text strong style={{ fontSize: 13 }}>{item.rate}%</Text></div>}
                              description={<Progress percent={item.rate} size="small" showInfo={false} strokeColor="#1890ff" />}
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
          {
            key: 'history',
            label: '历史周报',
            children: (
              <div>
                <Space wrap style={{ marginBottom: 16 }}>
                  <Input placeholder="搜索周次" prefix={<SearchOutlined />} style={{ width: 200 }} allowClear />
                  <Select defaultValue="all" style={{ width: 120 }} options={[
                    { value: 'all', label: '全部状态' },
                    { value: 'generated', label: '已生成' },
                    { value: 'draft', label: '草稿' },
                  ]} />
                  <Button type="primary" icon={<PlusOutlined />} onClick={() => message.info('创建新周报')}>创建周报</Button>
                </Space>
                <Table columns={reportColumns} dataSource={mockReports} rowKey="id" pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 份周报` }} locale={{ emptyText: <Empty description="暂无周报" /> }} />
              </div>
            ),
          },
        ]}
      />

      <Modal
        title={`周报详情 - ${viewingReport?.week || ''}`}
        open={detailModalOpen}
        onCancel={() => setDetailModalOpen(false)}
        footer={[
          <Button key="export" icon={<DownloadOutlined />} onClick={() => message.success('周报已导出')}>导出</Button>,
          <Button key="close" onClick={() => setDetailModalOpen(false)}>关闭</Button>,
        ]}
        width={800}
      >
        {viewingReport && (
          <div>
            <Descriptions column={4} bordered size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="周次" span={2}>{viewingReport.week}</Descriptions.Item>
              <Descriptions.Item label="周期" span={2}>{viewingReport.start_date} ~ {viewingReport.end_date}</Descriptions.Item>
              <Descriptions.Item label="收入"><Text strong style={{ color: '#52c41a' }}>¥{viewingReport.revenue.toLocaleString()}</Text></Descriptions.Item>
              <Descriptions.Item label="订单">{viewingReport.orders}单</Descriptions.Item>
              <Descriptions.Item label="利润"><Text strong style={{ color: '#1890ff' }}>¥{viewingReport.profit.toLocaleString()}</Text></Descriptions.Item>
              <Descriptions.Item label="转化率">{viewingReport.conversion_rate}%</Descriptions.Item>
              <Descriptions.Item label="新客户">{viewingReport.new_customers}人</Descriptions.Item>
              <Descriptions.Item label="客单价">¥{viewingReport.avg_order_value}</Descriptions.Item>
              <Descriptions.Item label="退货率"><Text type={viewingReport.return_rate > 3 ? 'danger' : 'secondary'}>{viewingReport.return_rate}%</Text></Descriptions.Item>
              <Descriptions.Item label="生成时间" span={2}>{viewingReport.generated_at}</Descriptions.Item>
            </Descriptions>

            <Alert message="AI分析摘要" description={viewingReport.ai_summary} type="info" showIcon icon={<RobotOutlined />} style={{ marginBottom: 16 }} />

            <Row gutter={16}>
              <Col span={8}>
                <Card size="small" title={<span><CheckCircleOutlined style={{ color: '#52c41a' }} /> 亮点</span>}>
                  <List size="small" dataSource={viewingReport.highlights} renderItem={(item, idx) => <List.Item><Text style={{ fontSize: 11 }}>{idx + 1}. {item}</Text></List.Item>} />
                </Card>
              </Col>
              <Col span={8}>
                <Card size="small" title={<span><ExclamationCircleOutlined style={{ color: '#faad14' }} /> 问题</span>}>
                  <List size="small" dataSource={viewingReport.issues} renderItem={(item, idx) => <List.Item><Text style={{ fontSize: 11 }}>{idx + 1}. {item}</Text></List.Item>} />
                </Card>
              </Col>
              <Col span={8}>
                <Card size="small" title={<span><BulbOutlined style={{ color: '#1890ff' }} /> 建议</span>}>
                  <List size="small" dataSource={viewingReport.suggestions} renderItem={(item, idx) => <List.Item><Text style={{ fontSize: 11 }}>{idx + 1}. {item}</Text></List.Item>} />
                </Card>
              </Col>
            </Row>
          </div>
        )}
      </Modal>
    </div>
  )
}
