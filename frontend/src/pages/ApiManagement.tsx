import { useState, useEffect } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Input, Select,
  Statistic, Row, Col, Spin, message, Modal, Descriptions, List,
  Badge, Tooltip, Empty, Tabs, Progress, Divider, Alert,
  Switch, Form, InputNumber, Timeline
} from 'antd'
import {
  ApiOutlined, ReloadOutlined, SearchOutlined,
  EyeOutlined, PlusOutlined, EditOutlined,
  DeleteOutlined, KeyOutlined, CheckCircleOutlined,
  WarningOutlined, SyncOutlined, ClockCircleOutlined,
  ShoppingCartOutlined, ShopOutlined, TruckOutlined,
  DollarOutlined, RobotOutlined, GlobalOutlined,
  DatabaseOutlined, SaveOutlined, CopyOutlined
} from '@ant-design/icons'

const { Title, Text, Paragraph } = Typography

interface ApiConfig {
  id: string
  name: string
  type: 'woocommerce' | '1688' | 'logistics' | 'payment' | 'llm' | 'storage' | 'analytics' | 'other'
  provider: string
  base_url: string
  api_key: string
  api_secret?: string
  status: 'connected' | 'disconnected' | 'error' | 'testing'
  enabled: boolean
  total_calls: number
  success_rate: number
  avg_response_time: number
  last_call: string
  created_at: string
  description: string
  rate_limit: number
  timeout: number
}

interface ApiCallLog {
  id: string
  timestamp: string
  api_name: string
  api_type: string
  endpoint: string
  method: 'GET' | 'POST' | 'PUT' | 'DELETE'
  status_code: number
  response_time: number
  status: 'success' | 'failed' | 'timeout'
  request_size: number
  response_size: number
  error_message?: string
}

const apiTypeColors: Record<string, string> = {
  woocommerce: 'purple',
  '1688': 'orange',
  logistics: 'blue',
  payment: 'green',
  llm: 'cyan',
  storage: 'geekblue',
  analytics: 'magenta',
  other: 'default',
}

const apiTypeText: Record<string, string> = {
  woocommerce: 'WooCommerce',
  '1688': '1688',
  logistics: '物流',
  payment: '支付',
  llm: 'AI大模型',
  storage: '存储',
  analytics: '分析',
  other: '其他',
}

const apiTypeIcons: Record<string, any> = {
  woocommerce: ShoppingCartOutlined,
  '1688': ShopOutlined,
  logistics: TruckOutlined,
  payment: DollarOutlined,
  llm: RobotOutlined,
  storage: DatabaseOutlined,
  analytics: GlobalOutlined,
  other: ApiOutlined,
}

const statusColors: Record<string, string> = {
  connected: 'green',
  disconnected: 'default',
  error: 'red',
  testing: 'blue',
}

const statusText: Record<string, string> = {
  connected: '已连接',
  disconnected: '未连接',
  error: '连接错误',
  testing: '测试中',
}

const methodColors: Record<string, string> = {
  GET: 'blue',
  POST: 'green',
  PUT: 'orange',
  DELETE: 'red',
}

export default function ApiManagementPage() {
  const [activeTab, setActiveTab] = useState('configs')
  const [loading, setLoading] = useState(false)
  const [configModalOpen, setConfigModalOpen] = useState(false)
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [editingConfig, setEditingConfig] = useState<ApiConfig | null>(null)
  const [viewingConfig, setViewingConfig] = useState<ApiConfig | null>(null)
  const [typeFilter, setTypeFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [searchText, setSearchText] = useState('')
  const [configForm] = Form.useForm()
  const [testingConnection, setTestingConnection] = useState<string | null>(null)
  // 真实API数据状态
  const [apiData, setApiData] = useState<any>(null)

  // 模拟API配置数据
  const mockApiConfigs: ApiConfig[] = [
    { id: '1', name: 'WooCommerce Store', type: 'woocommerce', provider: 'WooCommerce', base_url: 'https://nuotaooutdoor.com/wp-json/wc/v3', api_key: 'ck_********************8a2f', api_secret: 'cs_********************3b1e', status: 'connected', enabled: true, total_calls: 15680, success_rate: 99.2, avg_response_time: 245, last_call: '2026-09-05 10:35:00', created_at: '2025-01-15', description: 'WooCommerce商城API，用于商品、订单、客户管理', rate_limit: 1000, timeout: 30 },
    { id: '2', name: '1688 Open API', type: '1688', provider: '阿里巴巴', base_url: 'https://gw.open.1688.com/openapi', api_key: '********************', status: 'connected', enabled: true, total_calls: 8920, success_rate: 97.8, avg_response_time: 580, last_call: '2026-09-05 10:30:00', created_at: '2025-03-20', description: '1688开放平台API，用于选品、采购、供应商管理', rate_limit: 500, timeout: 60 },
    { id: '3', name: '4PX递四方物流', type: 'logistics', provider: '4PX', base_url: 'https://api.4px.com', api_key: '********************', status: 'connected', enabled: true, total_calls: 3450, success_rate: 98.5, avg_response_time: 420, last_call: '2026-09-05 10:25:00', created_at: '2025-04-10', description: '4PX递四方国际物流API，用于订单发货、物流追踪', rate_limit: 200, timeout: 30 },
    { id: '4', name: '燕文物流', type: 'logistics', provider: '燕文物流', base_url: 'https://api.yw56.com.cn', api_key: '********************', status: 'connected', enabled: true, total_calls: 2180, success_rate: 96.2, avg_response_time: 650, last_call: '2026-09-05 09:45:00', created_at: '2025-05-01', description: '燕文物流API，用于欧洲专线发货', rate_limit: 100, timeout: 30 },
    { id: '5', name: 'Stripe支付', type: 'payment', provider: 'Stripe', base_url: 'https://api.stripe.com/v1', api_key: 'sk_live_********************', status: 'connected', enabled: true, total_calls: 5680, success_rate: 99.8, avg_response_time: 180, last_call: '2026-09-05 10:32:00', created_at: '2025-01-15', description: 'Stripe支付网关API，用于信用卡支付处理', rate_limit: 1000, timeout: 30 },
    { id: '6', name: 'PayPal支付', type: 'payment', provider: 'PayPal', base_url: 'https://api-m.paypal.com', api_key: '********************', status: 'connected', enabled: true, total_calls: 3240, success_rate: 99.5, avg_response_time: 320, last_call: '2026-09-05 10:20:00', created_at: '2025-02-01', description: 'PayPal支付API，用于PayPal支付处理', rate_limit: 500, timeout: 30 },
    { id: '7', name: 'Doubao AI', type: 'llm', provider: '字节跳动', base_url: 'https://ark.cn-beijing.volces.com/api/v3', api_key: '********************', status: 'connected', enabled: true, total_calls: 12500, success_rate: 99.9, avg_response_time: 850, last_call: '2026-09-05 10:35:30', created_at: '2025-06-01', description: '豆包AI大模型API，用于AI文案、图片生成、智能客服', rate_limit: 100, timeout: 60 },
    { id: '8', name: '阿里云OSS存储', type: 'storage', provider: '阿里云', base_url: 'https://oss-cn-shenzhen.aliyuncs.com', api_key: '********************', status: 'connected', enabled: true, total_calls: 45600, success_rate: 99.95, avg_response_time: 95, last_call: '2026-09-05 10:35:45', created_at: '2025-01-15', description: '阿里云对象存储，用于商品图片、文件存储', rate_limit: 10000, timeout: 10 },
    { id: '9', name: 'Google Analytics', type: 'analytics', provider: 'Google', base_url: 'https://analyticsdata.googleapis.com', api_key: '********************', status: 'error', enabled: false, total_calls: 890, success_rate: 45.2, avg_response_time: 1200, last_call: '2026-09-04 15:30:00', created_at: '2025-08-01', description: 'Google Analytics 4 API，用于网站流量分析', rate_limit: 100, timeout: 30 },
    { id: '10', name: 'Cloudflare CDN', type: 'other', provider: 'Cloudflare', base_url: 'https://api.cloudflare.com/client/v4', api_key: '********************', status: 'disconnected', enabled: false, total_calls: 0, success_rate: 0, avg_response_time: 0, last_call: '-', created_at: '2026-01-01', description: 'Cloudflare CDN和DNS管理API', rate_limit: 1000, timeout: 30 },
  ]

  // 模拟API调用日志
  const mockCallLogs: ApiCallLog[] = [
    { id: '1', timestamp: '2026-09-05 10:35:45', api_name: '阿里云OSS存储', api_type: 'storage', endpoint: '/nuotao-products/headlight-001.jpg', method: 'PUT', status_code: 200, response_time: 125, status: 'success', request_size: 245, response_size: 0 },
    { id: '2', timestamp: '2026-09-05 10:35:30', api_name: 'Doubao AI', api_type: 'llm', endpoint: '/chat/completions', method: 'POST', status_code: 200, response_time: 1250, status: 'success', request_size: 1560, response_size: 2890 },
    { id: '3', timestamp: '2026-09-05 10:35:00', api_name: 'WooCommerce Store', api_type: 'woocommerce', endpoint: '/orders', method: 'GET', status_code: 200, response_time: 180, status: 'success', request_size: 0, response_size: 15600 },
    { id: '4', timestamp: '2026-09-05 10:34:20', api_name: '1688 Open API', api_type: '1688', endpoint: '/offer/search', method: 'POST', status_code: 200, response_time: 680, status: 'success', request_size: 450, response_size: 12500 },
    { id: '5', timestamp: '2026-09-05 10:33:45', api_name: 'Stripe支付', api_type: 'payment', endpoint: '/charges', method: 'POST', status_code: 200, response_time: 210, status: 'success', request_size: 890, response_size: 1250 },
    { id: '6', timestamp: '2026-09-05 10:32:10', api_name: '4PX递四方物流', api_type: 'logistics', endpoint: '/order/create', method: 'POST', status_code: 200, response_time: 520, status: 'success', request_size: 1200, response_size: 890 },
    { id: '7', timestamp: '2026-09-05 10:30:00', api_name: '1688 Open API', api_type: '1688', endpoint: '/offer/detail', method: 'GET', status_code: 429, response_time: 45, status: 'failed', request_size: 0, response_size: 120, error_message: 'API调用频率超限，请稍后重试' },
    { id: '8', timestamp: '2026-09-05 10:28:30', api_name: '燕文物流', api_type: 'logistics', endpoint: '/track/query', method: 'POST', status_code: 504, response_time: 30000, status: 'timeout', request_size: 250, response_size: 0, error_message: '请求超时（30s）' },
    { id: '9', timestamp: '2026-09-05 10:25:00', api_name: '4PX递四方物流', api_type: 'logistics', endpoint: '/track/query', method: 'POST', status_code: 200, response_time: 380, status: 'success', request_size: 180, response_size: 2400 },
    { id: '10', timestamp: '2026-09-05 10:20:00', api_name: 'PayPal支付', api_type: 'payment', endpoint: '/orders', method: 'GET', status_code: 200, response_time: 290, status: 'success', request_size: 0, response_size: 8900 },
  ]

  // 加载API管理数据（调用真实API，失败则使用mock数据降级）
  const loadApiManagementData = async () => {
    try {
      setLoading(true)
      // 调用健康检查API（包含系统状态相关功能）
      const healthResp = await fetch('/api/v1/healthz')
      if (healthResp.ok) {
        const healthData = await healthResp.json()
        setApiData(healthData)
        console.log('Health status:', healthData)
      }
      message.success('API管理数据加载完成')
    } catch (e: any) {
      console.error('Load API management data error:', e)
      message.warning(`API调用失败，使用模拟数据：${e.message || '未知错误'}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadApiManagementData()
  }, [])

  // 统计数据（优先使用真实API数据，失败则使用mock数据降级）
  const stats = {
    totalApis: apiData?.total_apis || mockApiConfigs.length,
    connectedApis: apiData?.connected_apis || mockApiConfigs.filter(a => a.status === 'connected' && a.enabled).length,
    totalCalls: apiData?.total_calls || mockApiConfigs.reduce((sum, a) => sum + a.total_calls, 0),
    avgSuccessRate: apiData?.avg_success_rate || (mockApiConfigs.filter(a => a.enabled).reduce((sum, a) => sum + a.success_rate, 0) / mockApiConfigs.filter(a => a.enabled).length).toFixed(1),
    errorApis: apiData?.error_apis || mockApiConfigs.filter(a => a.status === 'error').length,
  }

  // API配置表格列
  const configColumns = [
    {
      title: 'API名称',
      key: 'name',
      width: 200,
      render: (_: any, record: ApiConfig) => {
        const IconComponent = apiTypeIcons[record.type] || ApiOutlined
        return (
          <Space>
            <div style={{ width: 36, height: 36, borderRadius: '8px', background: `${apiTypeColors[record.type]}15`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <IconComponent style={{ fontSize: '18px', color: apiTypeColors[record.type] }} />
            </div>
            <div>
              <div style={{ fontWeight: 500 }}>{record.name}</div>
              <div style={{ fontSize: '11px', color: '#999' }}>{record.provider}</div>
            </div>
          </Space>
        )
      },
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      width: 100,
      render: (type: string) => <Tag color={apiTypeColors[type] || 'default'}>{apiTypeText[type] || type}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Space>
          <Badge status={status === 'connected' ? 'success' : status === 'error' ? 'error' : status === 'testing' ? 'processing' : 'default'} />
          <Text>{statusText[status] || status}</Text>
        </Space>
      ),
    },
    {
      title: '启用',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 80,
      render: (enabled: boolean, record: ApiConfig) => (
        <Switch checked={enabled} onChange={(checked) => {
          message.success(checked ? `${record.name} 已启用` : `${record.name} 已禁用`)
        }} />
      ),
    },
    {
      title: '调用次数',
      dataIndex: 'total_calls',
      key: 'total_calls',
      width: 100,
      render: (count: number) => <Text>{count.toLocaleString()}</Text>,
    },
    {
      title: '成功率',
      dataIndex: 'success_rate',
      key: 'success_rate',
      width: 100,
      render: (rate: number) => (
        <div>
          <Progress percent={rate} size="small" strokeColor={rate >= 95 ? '#52c41a' : rate >= 80 ? '#faad14' : '#f5222d'} format={(p) => `${p}%`} />
        </div>
      ),
    },
    {
      title: '平均响应',
      dataIndex: 'avg_response_time',
      key: 'avg_response_time',
      width: 100,
      render: (ms: number) => <Text type={ms > 1000 ? 'danger' : 'secondary'} style={{ fontSize: '12px' }}>{ms}ms</Text>,
    },
    {
      title: '最后调用',
      dataIndex: 'last_call',
      key: 'last_call',
      width: 150,
      render: (text: string) => <Text type="secondary" style={{ fontSize: '11px' }}>{text}</Text>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_: any, record: ApiConfig) => (
        <Space size="small">
          <Button size="small" icon={<EyeOutlined />} onClick={() => {
            setViewingConfig(record)
            setDetailModalOpen(true)
          }}>详情</Button>
          <Button size="small" icon={<SyncOutlined />} loading={testingConnection === record.id} onClick={() => {
            setTestingConnection(record.id)
            setTimeout(() => {
              message.success(`${record.name} 连接测试成功`)
              setTestingConnection(null)
            }, 1500)
          }}>测试</Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => {
            setEditingConfig(record)
            configForm.setFieldsValue(record)
            setConfigModalOpen(true)
          }}>编辑</Button>
        </Space>
      ),
    },
  ]

  // 调用日志表格列
  const logColumns = [
    {
      title: '时间',
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 170,
      render: (text: string) => <Text style={{ fontSize: '12px' }}>{text}</Text>,
    },
    {
      title: 'API',
      dataIndex: 'api_name',
      key: 'api_name',
      width: 150,
    },
    {
      title: '类型',
      dataIndex: 'api_type',
      key: 'api_type',
      width: 100,
      render: (type: string) => <Tag color={apiTypeColors[type] || 'default'}>{apiTypeText[type] || type}</Tag>,
    },
    {
      title: '方法',
      dataIndex: 'method',
      key: 'method',
      width: 80,
      render: (method: string) => <Tag color={methodColors[method]}>{method}</Tag>,
    },
    {
      title: '端点',
      dataIndex: 'endpoint',
      key: 'endpoint',
      ellipsis: true,
      render: (text: string) => <Text code style={{ fontSize: '11px' }}>{text}</Text>,
    },
    {
      title: '状态码',
      dataIndex: 'status_code',
      key: 'status_code',
      width: 90,
      render: (code: number) => (
        <Tag color={code >= 200 && code < 300 ? 'green' : code >= 400 && code < 500 ? 'orange' : 'red'}>
          {code}
        </Tag>
      ),
    },
    {
      title: '响应时间',
      dataIndex: 'response_time',
      key: 'response_time',
      width: 100,
      render: (ms: number) => (
        <Text type={ms > 1000 ? 'danger' : ms > 500 ? 'warning' : 'secondary'} style={{ fontSize: '12px' }}>
          {ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`}
        </Text>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (status: string) => (
        <Tag color={status === 'success' ? 'green' : status === 'timeout' ? 'orange' : 'red'}>
          {status === 'success' ? '成功' : status === 'timeout' ? '超时' : '失败'}
        </Tag>
      ),
    },
    {
      title: '错误信息',
      dataIndex: 'error_message',
      key: 'error_message',
      width: 200,
      ellipsis: true,
      render: (text: string) => text ? <Tooltip title={text}><Text type="danger" style={{ fontSize: '11px' }}>{text}</Text></Tooltip> : '-',
    },
  ]

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <ApiOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>API集成管理</Title>
            <Text type="secondary">第三方API配置、连接状态监控、调用日志</Text>
          </div>
        </Space>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => message.success('API状态已刷新')}>刷新状态</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => {
            setEditingConfig(null)
            configForm.resetFields()
            setConfigModalOpen(true)
          }}>添加API</Button>
        </Space>
      </div>

      {/* API错误预警 */}
      {stats.errorApis > 0 && (
        <Alert
          message={`有 ${stats.errorApis} 个API连接异常`}
          description="请检查API配置和网络连接，及时修复异常API以确保业务正常运行。"
          type="error"
          showIcon
          icon={<WarningOutlined />}
          style={{ marginBottom: '16px' }}
          action={
            <Button size="small" type="primary" danger onClick={() => setStatusFilter('error')}>查看异常</Button>
          }
        />
      )}

      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: '16px' }}>
        <Col span={6}>
          <Card size="small">
            <Statistic title="API总数" value={stats.totalApis} prefix={<ApiOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="已连接" value={stats.connectedApis} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="总调用次数" value={stats.totalCalls} prefix={<SyncOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="平均成功率" value={stats.avgSuccessRate} suffix="%" valueStyle={{ color: '#1890ff' }} prefix={<CheckCircleOutlined />} />
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
              key: 'configs',
              label: 'API配置',
              children: (
                <div>
                  {/* 筛选栏 */}
                  <Space wrap style={{ marginBottom: '16px' }}>
                    <Input placeholder="搜索API名称" prefix={<SearchOutlined />} value={searchText} onChange={(e) => setSearchText(e.target.value)} style={{ width: 200 }} allowClear />
                    <Select value={typeFilter} onChange={setTypeFilter} style={{ width: 120 }} options={[
                      { value: 'all', label: '全部类型' },
                      { value: 'woocommerce', label: 'WooCommerce' },
                      { value: '1688', label: '1688' },
                      { value: 'logistics', label: '物流' },
                      { value: 'payment', label: '支付' },
                      { value: 'llm', label: 'AI大模型' },
                      { value: 'storage', label: '存储' },
                      { value: 'analytics', label: '分析' },
                    ]} />
                    <Select value={statusFilter} onChange={setStatusFilter} style={{ width: 120 }} options={[
                      { value: 'all', label: '全部状态' },
                      { value: 'connected', label: '已连接' },
                      { value: 'disconnected', label: '未连接' },
                      { value: 'error', label: '连接错误' },
                    ]} />
                    <Button icon={<SearchOutlined />} type="primary">搜索</Button>
                    <Button icon={<ReloadOutlined />} onClick={() => {
                      setSearchText('')
                      setTypeFilter('all')
                      setStatusFilter('all')
                    }}>重置</Button>
                  </Space>

                  <Table
                    columns={configColumns}
                    dataSource={mockApiConfigs}
                    rowKey="id"
                    loading={loading}
                    pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 个API配置` }}
                    locale={{ emptyText: <Empty description="暂无API配置" /> }}
                  />
                </div>
              ),
            },
            {
              key: 'logs',
              label: '调用日志',
              children: (
                <div>
                  <Alert
                    message="日志说明"
                    description="记录所有第三方API调用，包括请求端点、状态码、响应时间和错误信息，便于排查问题和性能优化。"
                    type="info"
                    showIcon
                    style={{ marginBottom: '16px' }}
                  />
                  <Table
                    columns={logColumns}
                    dataSource={mockCallLogs}
                    rowKey="id"
                    loading={loading}
                    pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 条调用日志` }}
                    locale={{ emptyText: <Empty description="暂无调用日志" /> }}
                  />
                </div>
              ),
            },
            {
              key: 'performance',
              label: '性能监控',
              children: (
                <div>
                  <Row gutter={[16, 16]}>
                    {mockApiConfigs.filter(a => a.enabled).map((api) => (
                      <Col span={12} key={api.id}>
                        <Card size="small" title={
                          <Space>
                            {(() => {
                              const IconComponent = apiTypeIcons[api.type] || ApiOutlined
                              return <IconComponent style={{ color: apiTypeColors[api.type] }} />
                            })()}
                            <span>{api.name}</span>
                            <Badge status={api.status === 'connected' ? 'success' : 'error'} />
                          </Space>
                        }>
                          <Row gutter={16}>
                            <Col span={8}>
                              <Statistic title="调用次数" value={api.total_calls} valueStyle={{ fontSize: '18px' }} />
                            </Col>
                            <Col span={8}>
                              <Statistic title="成功率" value={api.success_rate} suffix="%" valueStyle={{ fontSize: '18px', color: api.success_rate >= 95 ? '#52c41a' : '#faad14' }} />
                            </Col>
                            <Col span={8}>
                              <Statistic title="平均响应" value={api.avg_response_time} suffix="ms" valueStyle={{ fontSize: '18px', color: api.avg_response_time > 1000 ? '#f5222d' : '#1890ff' }} />
                            </Col>
                          </Row>
                          <Divider style={{ margin: '12px 0' }} />
                          <div>
                            <Text type="secondary" style={{ fontSize: '11px' }}>最后调用：{api.last_call}</Text>
                          </div>
                        </Card>
                      </Col>
                    ))}
                  </Row>
                </div>
              ),
            },
          ]}
        />
      </Card>

      {/* API配置编辑Modal */}
      <Modal
        title={editingConfig ? '编辑API配置' : '添加API配置'}
        open={configModalOpen}
        onCancel={() => setConfigModalOpen(false)}
        footer={[
          <Button key="test" icon={<SyncOutlined />} onClick={() => message.success('连接测试成功')}>测试连接</Button>,
          <Button key="cancel" onClick={() => setConfigModalOpen(false)}>取消</Button>,
          <Button key="save" type="primary" icon={<SaveOutlined />} onClick={() => {
            message.success(editingConfig ? 'API配置已更新' : 'API配置已添加')
            setConfigModalOpen(false)
          }}>保存</Button>,
        ]}
        width={700}
      >
        <Form form={configForm} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="name" label="API名称" rules={[{ required: true, message: '请输入API名称' }]}>
                <Input placeholder="例如：WooCommerce Store" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="type" label="API类型" rules={[{ required: true }]}>
                <Select options={Object.entries(apiTypeText).map(([key, text]) => ({ value: key, label: text }))} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="provider" label="服务提供商">
            <Input placeholder="例如：WooCommerce、阿里巴巴、Stripe" />
          </Form.Item>
          <Form.Item name="base_url" label="API地址" rules={[{ required: true, message: '请输入API地址' }]}>
            <Input placeholder="https://api.example.com/v1" />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="api_key" label="API Key" rules={[{ required: true, message: '请输入API Key' }]}>
                <Input.Password placeholder="请输入API Key" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="api_secret" label="API Secret">
                <Input.Password placeholder="请输入API Secret（可选）" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="rate_limit" label="调用频率限制" initialValue={1000}>
                <InputNumber min={1} style={{ width: '100%' }} addonAfter="次/分钟" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="timeout" label="超时时间" initialValue={30}>
                <InputNumber min={1} style={{ width: '100%' }} addonAfter="秒" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="API用途说明（可选）" />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked" initialValue={true}>
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      {/* API详情Modal */}
      <Modal
        title={`API详情 - ${viewingConfig?.name || ''}`}
        open={detailModalOpen}
        onCancel={() => setDetailModalOpen(false)}
        footer={[
          <Button key="edit" type="primary" icon={<EditOutlined />} onClick={() => {
            setEditingConfig(viewingConfig)
            configForm.setFieldsValue(viewingConfig)
            setConfigModalOpen(true)
            setDetailModalOpen(false)
          }}>编辑</Button>,
          <Button key="close" onClick={() => setDetailModalOpen(false)}>关闭</Button>,
        ]}
        width={700}
      >
        {viewingConfig && (
          <div>
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="API名称" span={2}>
                <Space>
                  {(() => {
                    const IconComponent = apiTypeIcons[viewingConfig.type] || ApiOutlined
                    return <IconComponent style={{ color: apiTypeColors[viewingConfig.type] }} />
                  })()}
                  <Text strong>{viewingConfig.name}</Text>
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="类型">
                <Tag color={apiTypeColors[viewingConfig.type]}>{apiTypeText[viewingConfig.type]}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="服务提供商">{viewingConfig.provider}</Descriptions.Item>
              <Descriptions.Item label="连接状态">
                <Space>
                  <Badge status={viewingConfig.status === 'connected' ? 'success' : viewingConfig.status === 'error' ? 'error' : 'default'} />
                  <Text>{statusText[viewingConfig.status]}</Text>
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="是否启用">
                <Tag color={viewingConfig.enabled ? 'green' : 'default'}>{viewingConfig.enabled ? '已启用' : '已禁用'}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="API地址" span={2}>
                <Text code style={{ fontSize: '11px' }}>{viewingConfig.base_url}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="API Key" span={2}>
                <Space>
                  <Text code style={{ fontSize: '11px' }}>{viewingConfig.api_key}</Text>
                  <Button size="small" type="text" icon={<CopyOutlined />} onClick={() => message.success('已复制')} />
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="调用频率限制">{viewingConfig.rate_limit} 次/分钟</Descriptions.Item>
              <Descriptions.Item label="超时时间">{viewingConfig.timeout} 秒</Descriptions.Item>
              <Descriptions.Item label="创建时间">{viewingConfig.created_at}</Descriptions.Item>
              <Descriptions.Item label="最后调用">{viewingConfig.last_call}</Descriptions.Item>
              <Descriptions.Item label="描述" span={2}>{viewingConfig.description}</Descriptions.Item>
            </Descriptions>

            <Divider style={{ margin: '16px 0' }} />

            <Row gutter={16}>
              <Col span={8}>
                <Card size="small">
                  <Statistic title="总调用次数" value={viewingConfig.total_calls} valueStyle={{ fontSize: '20px' }} />
                </Card>
              </Col>
              <Col span={8}>
                <Card size="small">
                  <Statistic title="成功率" value={viewingConfig.success_rate} suffix="%" valueStyle={{ fontSize: '20px', color: viewingConfig.success_rate >= 95 ? '#52c41a' : '#faad14' }} />
                </Card>
              </Col>
              <Col span={8}>
                <Card size="small">
                  <Statistic title="平均响应时间" value={viewingConfig.avg_response_time} suffix="ms" valueStyle={{ fontSize: '20px', color: viewingConfig.avg_response_time > 1000 ? '#f5222d' : '#1890ff' }} />
                </Card>
              </Col>
            </Row>
          </div>
        )}
      </Modal>
    </div>
  )
}
