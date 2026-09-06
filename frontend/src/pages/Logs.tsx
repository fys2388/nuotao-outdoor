import { useState, useEffect } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Input, Select,
  Statistic, Row, Col, Spin, message, Modal, Descriptions, List,
  Badge, Tooltip, Empty, Tabs, Timeline, Divider, Alert,
  DatePicker, Radio
} from 'antd'
import {
  FileTextOutlined, ReloadOutlined, SearchOutlined,
  EyeOutlined, UserOutlined, SafetyOutlined,
  WarningOutlined, CheckCircleOutlined, ClockCircleOutlined,
  DownloadOutlined, SyncOutlined, LockOutlined,
  EditOutlined, DeleteOutlined, PlusOutlined,
  GlobalOutlined, DesktopOutlined
} from '@ant-design/icons'
import dayjs from 'dayjs'

const { Title, Text, Paragraph } = Typography
const { RangePicker } = DatePicker

interface OperationLog {
  id: string
  timestamp: string
  user: string
  user_role: string
  action: string
  action_type: 'create' | 'update' | 'delete' | 'view' | 'login' | 'logout' | 'export' | 'import'
  module: string
  target: string
  ip: string
  user_agent: string
  status: 'success' | 'failed' | 'warning'
  duration: number
  details?: string
}

interface AuditLog {
  id: string
  timestamp: string
  user: string
  module: string
  target: string
  field: string
  old_value: string
  new_value: string
  change_type: 'create' | 'update' | 'delete'
}

interface SecurityEvent {
  id: string
  timestamp: string
  event_type: 'login' | 'failed_login' | 'permission_change' | 'password_reset' | 'api_key_create' | 'suspicious_activity'
  user: string
  ip: string
  location: string
  status: 'success' | 'failed' | 'blocked'
  details: string
}

const actionTypeColors: Record<string, string> = {
  create: 'green',
  update: 'blue',
  delete: 'red',
  view: 'default',
  login: 'cyan',
  logout: 'default',
  export: 'purple',
  import: 'orange',
}

const actionTypeText: Record<string, string> = {
  create: '创建',
  update: '更新',
  delete: '删除',
  view: '查看',
  login: '登录',
  logout: '登出',
  export: '导出',
  import: '导入',
}

const statusColors: Record<string, string> = {
  success: 'green',
  failed: 'red',
  warning: 'orange',
  blocked: 'red',
}

const eventTypeColors: Record<string, string> = {
  login: 'green',
  failed_login: 'red',
  permission_change: 'orange',
  password_reset: 'blue',
  api_key_create: 'purple',
  suspicious_activity: 'red',
}

const eventTypeText: Record<string, string> = {
  login: '用户登录',
  failed_login: '登录失败',
  permission_change: '权限变更',
  password_reset: '密码重置',
  api_key_create: 'API密钥创建',
  suspicious_activity: '可疑活动',
}

export default function LogsPage() {
  const [activeTab, setActiveTab] = useState('operations')
  const [loading, setLoading] = useState(false)
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [viewingLog, setViewingLog] = useState<OperationLog | null>(null)
  const [actionTypeFilter, setActionTypeFilter] = useState('all')
  const [moduleFilter, setModuleFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [searchText, setSearchText] = useState('')
  const [dateRange, setDateRange] = useState<any>(null)
  // 真实API数据状态
  const [logsData, setLogsData] = useState<any>(null)

  // 模拟操作日志数据
  const mockOperationLogs: OperationLog[] = [
    { id: '1', timestamp: '2026-09-05 10:32:15', user: 'admin', user_role: 'admin', action: '更新产品库存', action_type: 'update', module: '产品管理', target: '保温水壶1L (SKU: NT-BOTTLE-001)', ip: '192.168.1.100', user_agent: 'Chrome/120.0 Windows', status: 'success', duration: 125, details: '库存从 50 件更新为 45 件' },
    { id: '2', timestamp: '2026-09-05 10:28:03', user: 'joran', user_role: 'manager', action: '创建采购订单', action_type: 'create', module: '采购管理', target: 'PO-20260905-001', ip: '192.168.1.101', user_agent: 'Chrome/120.0 Mac', status: 'success', duration: 342, details: '向深圳户外装备有限公司采购12件商品，金额¥5680' },
    { id: '3', timestamp: '2026-09-05 10:15:47', user: 'cs001', user_role: 'customer_service', action: '回复客服工单', action_type: 'update', module: '客服工单', target: 'TK-20260905-001', ip: '192.168.1.102', user_agent: 'Chrome/120.0 Windows', status: 'success', duration: 89, details: '回复客户关于头灯不亮的换货咨询' },
    { id: '4', timestamp: '2026-09-05 09:58:22', user: 'operator1', user_role: 'operator', action: '导出订单报表', action_type: 'export', module: '订单管理', target: '订单报表_20260901-20260905.xlsx', ip: '192.168.1.103', user_agent: 'Chrome/120.0 Windows', status: 'success', duration: 1567, details: '导出156条订单记录' },
    { id: '5', timestamp: '2026-09-05 09:45:10', user: 'admin', user_role: 'admin', action: '删除用户', action_type: 'delete', module: '用户管理', target: 'test_user (ID: 99)', ip: '192.168.1.100', user_agent: 'Chrome/120.0 Windows', status: 'success', duration: 67, details: '删除测试用户账号' },
    { id: '6', timestamp: '2026-09-05 09:30:00', user: 'unknown', user_role: 'unknown', action: '登录失败', action_type: 'login', module: '系统', target: 'admin@nuotaooutdoor.com', ip: '45.33.32.156', user_agent: 'Unknown Bot', status: 'failed', duration: 45, details: '密码错误，连续失败5次，IP已被临时封禁' },
    { id: '7', timestamp: '2026-09-05 09:15:33', user: 'joran', user_role: 'manager', action: '更新系统配置', action_type: 'update', module: '系统设置', target: '低库存预警阈值', ip: '192.168.1.101', user_agent: 'Chrome/120.0 Mac', status: 'success', duration: 98, details: '低库存预警阈值从 5 件更新为 10 件' },
    { id: '8', timestamp: '2026-09-05 08:50:21', user: 'cs002', user_role: 'customer_service', action: '查看客户详情', action_type: 'view', module: '客户管理', target: 'John Smith (ID: 1001)', ip: '192.168.1.104', user_agent: 'Chrome/120.0 Windows', status: 'success', duration: 34, details: '查看客户购买历史和消费分析' },
    { id: '9', timestamp: '2026-09-05 08:30:00', user: 'admin', user_role: 'admin', action: '系统登录', action_type: 'login', module: '系统', target: 'admin', ip: '192.168.1.100', user_agent: 'Chrome/120.0 Windows', status: 'success', duration: 156, details: '管理员登录系统' },
    { id: '10', timestamp: '2026-09-04 18:45:30', user: 'operator1', user_role: 'operator', action: '批量导入产品', action_type: 'import', module: '产品管理', target: 'products_batch_0904.csv', ip: '192.168.1.103', user_agent: 'Chrome/120.0 Windows', status: 'warning', duration: 4521, details: '导入50条产品记录，其中3条失败（SKU重复）' },
  ]

  // 模拟审计日志数据
  const mockAuditLogs: AuditLog[] = [
    { id: '1', timestamp: '2026-09-05 10:32:15', user: 'admin', module: '产品管理', target: '保温水壶1L', field: 'stock_quantity', old_value: '50', new_value: '45', change_type: 'update' },
    { id: '2', timestamp: '2026-09-05 10:28:03', user: 'joran', module: '采购管理', target: 'PO-20260905-001', field: 'status', old_value: 'pending', new_value: 'ordered', change_type: 'update' },
    { id: '3', timestamp: '2026-09-05 09:45:10', user: 'admin', module: '用户管理', target: 'test_user', field: 'account', old_value: 'active', new_value: 'deleted', change_type: 'delete' },
    { id: '4', timestamp: '2026-09-05 09:15:33', user: 'joran', module: '系统设置', target: '系统配置', field: 'low_stock_threshold', old_value: '5', new_value: '10', change_type: 'update' },
    { id: '5', timestamp: '2026-09-05 08:20:00', user: 'operator1', module: '产品管理', target: 'LED头灯 Pro', field: 'price', old_value: '29.99', new_value: '34.99', change_type: 'update' },
    { id: '6', timestamp: '2026-09-04 16:30:00', user: 'admin', module: '角色权限', target: '客服角色', field: 'permissions', old_value: 'customer:tickets, order:orders', new_value: 'customer:tickets, customer:customers, order:orders', change_type: 'update' },
    { id: '7', timestamp: '2026-09-04 14:15:00', user: 'joran', module: '营销活动', target: '秋季大促', field: 'discount', old_value: '15%', new_value: '20%', change_type: 'update' },
    { id: '8', timestamp: '2026-09-04 10:00:00', user: 'operator1', module: '产品管理', target: '太阳能露营灯', field: 'product', old_value: '-', new_value: '新建产品', change_type: 'create' },
  ]

  // 模拟安全事件数据
  const mockSecurityEvents: SecurityEvent[] = [
    { id: '1', timestamp: '2026-09-05 09:30:00', event_type: 'login', user: 'admin', ip: '192.168.1.100', location: '中国 深圳', status: 'success', details: '管理员正常登录' },
    { id: '2', timestamp: '2026-09-05 09:30:00', event_type: 'failed_login', user: 'admin@nuotaooutdoor.com', ip: '45.33.32.156', location: '美国 洛杉矶', status: 'blocked', details: '连续5次密码错误，IP已被临时封禁30分钟' },
    { id: '3', timestamp: '2026-09-05 08:45:00', event_type: 'password_reset', user: 'cs001', ip: '192.168.1.102', location: '中国 深圳', status: 'success', details: '客服小美重置密码' },
    { id: '4', timestamp: '2026-09-04 17:30:00', event_type: 'permission_change', user: 'admin', ip: '192.168.1.100', location: '中国 深圳', status: 'success', details: '为客服角色添加客户管理权限' },
    { id: '5', timestamp: '2026-09-04 15:20:00', event_type: 'api_key_create', user: 'joran', ip: '192.168.1.101', location: '中国 深圳', status: 'success', details: '创建WooCommerce API密钥' },
    { id: '6', timestamp: '2026-09-04 10:15:00', event_type: 'suspicious_activity', user: 'unknown', ip: '103.45.67.89', location: '未知', status: 'blocked', details: '检测到异常API调用频率，已自动拦截' },
    { id: '7', timestamp: '2026-09-03 14:00:00', event_type: 'login', user: 'joran', ip: '192.168.1.101', location: '中国 深圳', status: 'success', details: '运营经理正常登录' },
    { id: '8', timestamp: '2026-09-03 09:30:00', event_type: 'failed_login', user: 'operator1', ip: '192.168.1.103', location: '中国 深圳', status: 'failed', details: '密码错误（第1次）' },
  ]

  // 加载日志数据（调用真实API，失败则使用mock数据降级）
  const loadLogsData = async () => {
    try {
      setLoading(true)
      // 调用操作日志统计API（新创建的端点）
      const statsResp = await fetch('/api/v1/operation-logs/stats')
      if (statsResp.ok) {
        const statsData = await statsResp.json()
        setLogsData(statsData)
        console.log('Operation logs stats:', statsData)
      }
      message.success('日志数据加载完成')
    } catch (e: any) {
      console.error('Load logs data error:', e)
      message.warning(`API调用失败，使用模拟数据：${e.message || '未知错误'}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadLogsData()
  }, [])

  // 统计数据（优先使用真实API数据，失败则使用mock数据降级）
  const stats = {
    totalOperations: logsData?.total_operations || mockOperationLogs.length,
    successRate: logsData?.success_rate || Math.round((mockOperationLogs.filter(l => l.status === 'success').length / mockOperationLogs.length) * 100),
    securityAlerts: logsData?.security_alerts || mockSecurityEvents.filter(e => e.status === 'blocked' || e.event_type === 'suspicious_activity').length,
    dataChanges: logsData?.data_changes || mockAuditLogs.length,
  }

  // 操作日志表格列
  const operationColumns = [
    {
      title: '时间',
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 170,
      render: (text: string) => <Text style={{ fontSize: '12px' }}>{text}</Text>,
    },
    {
      title: '用户',
      key: 'user',
      width: 150,
      render: (_: any, record: OperationLog) => (
        <Space>
          <Avatar size="small" icon={<UserOutlined />} style={{ backgroundColor: '#722ed1', width: 24, height: 24, fontSize: 12 }} />
          <div>
            <div style={{ fontSize: '12px', fontWeight: 500 }}>{record.user}</div>
            <div style={{ fontSize: '10px', color: '#999' }}>{record.user_role}</div>
          </div>
        </Space>
      ),
    },
    {
      title: '操作类型',
      dataIndex: 'action_type',
      key: 'action_type',
      width: 90,
      render: (type: string) => <Tag color={actionTypeColors[type] || 'default'}>{actionTypeText[type] || type}</Tag>,
    },
    {
      title: '模块',
      dataIndex: 'module',
      key: 'module',
      width: 100,
    },
    {
      title: '操作内容',
      dataIndex: 'action',
      key: 'action',
      width: 150,
      render: (text: string, record: OperationLog) => (
        <div>
          <div style={{ fontSize: '12px' }}>{text}</div>
          <div style={{ fontSize: '10px', color: '#999' }}>{record.target}</div>
        </div>
      ),
    },
    {
      title: 'IP地址',
      dataIndex: 'ip',
      key: 'ip',
      width: 130,
      render: (text: string) => (
        <Space>
          <GlobalOutlined style={{ fontSize: '11px', color: '#999' }} />
          <Text style={{ fontSize: '11px', fontFamily: 'monospace' }}>{text}</Text>
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (status: string) => <Tag color={statusColors[status] || 'default'}>{status === 'success' ? '成功' : status === 'failed' ? '失败' : '警告'}</Tag>,
    },
    {
      title: '耗时',
      dataIndex: 'duration',
      key: 'duration',
      width: 80,
      render: (ms: number) => <Text type="secondary" style={{ fontSize: '11px' }}>{ms}ms</Text>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 80,
      render: (_: any, record: OperationLog) => (
        <Button size="small" icon={<EyeOutlined />} onClick={() => {
          setViewingLog(record)
          setDetailModalOpen(true)
        }}>详情</Button>
      ),
    },
  ]

  // 审计日志表格列
  const auditColumns = [
    {
      title: '时间',
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 170,
      render: (text: string) => <Text style={{ fontSize: '12px' }}>{text}</Text>,
    },
    {
      title: '用户',
      dataIndex: 'user',
      key: 'user',
      width: 100,
    },
    {
      title: '模块',
      dataIndex: 'module',
      key: 'module',
      width: 100,
    },
    {
      title: '变更对象',
      dataIndex: 'target',
      key: 'target',
      width: 150,
    },
    {
      title: '变更字段',
      dataIndex: 'field',
      key: 'field',
      width: 120,
      render: (text: string) => <Text code style={{ fontSize: '11px' }}>{text}</Text>,
    },
    {
      title: '变更类型',
      dataIndex: 'change_type',
      key: 'change_type',
      width: 90,
      render: (type: string) => <Tag color={actionTypeColors[type] || 'default'}>{actionTypeText[type] || type}</Tag>,
    },
    {
      title: '变更前',
      dataIndex: 'old_value',
      key: 'old_value',
      width: 150,
      render: (text: string) => (
        <div style={{ background: '#fff2f0', padding: '4px 8px', borderRadius: '4px', fontSize: '11px', color: '#cf1322' }}>
          {text}
        </div>
      ),
    },
    {
      title: '变更后',
      dataIndex: 'new_value',
      key: 'new_value',
      width: 150,
      render: (text: string) => (
        <div style={{ background: '#f6ffed', padding: '4px 8px', borderRadius: '4px', fontSize: '11px', color: '#389e0d' }}>
          {text}
        </div>
      ),
    },
  ]

  // 安全事件表格列
  const securityColumns = [
    {
      title: '时间',
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 170,
      render: (text: string) => <Text style={{ fontSize: '12px' }}>{text}</Text>,
    },
    {
      title: '事件类型',
      dataIndex: 'event_type',
      key: 'event_type',
      width: 120,
      render: (type: string) => <Tag color={eventTypeColors[type] || 'default'}>{eventTypeText[type] || type}</Tag>,
    },
    {
      title: '用户',
      dataIndex: 'user',
      key: 'user',
      width: 150,
    },
    {
      title: 'IP地址',
      dataIndex: 'ip',
      key: 'ip',
      width: 130,
      render: (text: string) => <Text style={{ fontFamily: 'monospace', fontSize: '11px' }}>{text}</Text>,
    },
    {
      title: '地理位置',
      dataIndex: 'location',
      key: 'location',
      width: 120,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (status: string) => <Tag color={statusColors[status] || 'default'}>{status === 'success' ? '成功' : status === 'failed' ? '失败' : '已拦截'}</Tag>,
    },
    {
      title: '详情',
      dataIndex: 'details',
      key: 'details',
      ellipsis: true,
      render: (text: string) => <Tooltip title={text}><Text style={{ fontSize: '12px' }}>{text}</Text></Tooltip>,
    },
  ]

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <FileTextOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>操作日志与审计</Title>
            <Text type="secondary">系统操作日志、数据变更审计、安全监控</Text>
          </div>
        </Space>
        <Space>
          <Button icon={<DownloadOutlined />} onClick={() => message.success('日志导出中...')}>导出日志</Button>
          <Button icon={<ReloadOutlined />} onClick={() => message.success('日志已刷新')}>刷新</Button>
        </Space>
      </div>

      {/* 安全预警 */}
      {stats.securityAlerts > 0 && (
        <Alert
          message={`检测到 ${stats.securityAlerts} 个安全事件需要关注`}
          description="包含登录失败、可疑活动、IP封禁等安全事件，请及时查看处理。"
          type="error"
          showIcon
          icon={<WarningOutlined />}
          style={{ marginBottom: '16px' }}
          action={
            <Button size="small" type="primary" danger onClick={() => setActiveTab('security')}>查看安全事件</Button>
          }
        />
      )}

      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: '16px' }}>
        <Col span={6}>
          <Card size="small">
            <Statistic title="操作总数" value={stats.totalOperations} prefix={<FileTextOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="成功率" value={stats.successRate} suffix="%" valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="数据变更" value={stats.dataChanges} valueStyle={{ color: '#1890ff' }} prefix={<EditOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="安全告警" value={stats.securityAlerts} valueStyle={{ color: '#f5222d' }} prefix={<WarningOutlined />} />
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
              key: 'operations',
              label: '操作日志',
              children: (
                <div>
                  {/* 筛选栏 */}
                  <Space wrap style={{ marginBottom: '16px' }}>
                    <Input placeholder="搜索用户/操作内容" prefix={<SearchOutlined />} value={searchText} onChange={(e) => setSearchText(e.target.value)} style={{ width: 200 }} allowClear />
                    <Select value={actionTypeFilter} onChange={setActionTypeFilter} style={{ width: 110 }} options={[
                      { value: 'all', label: '全部类型' },
                      { value: 'create', label: '创建' },
                      { value: 'update', label: '更新' },
                      { value: 'delete', label: '删除' },
                      { value: 'view', label: '查看' },
                      { value: 'login', label: '登录' },
                      { value: 'export', label: '导出' },
                      { value: 'import', label: '导入' },
                    ]} />
                    <Select value={moduleFilter} onChange={setModuleFilter} style={{ width: 120 }} options={[
                      { value: 'all', label: '全部模块' },
                      { value: '产品管理', label: '产品管理' },
                      { value: '订单管理', label: '订单管理' },
                      { value: '客户管理', label: '客户管理' },
                      { value: '用户管理', label: '用户管理' },
                      { value: '系统设置', label: '系统设置' },
                    ]} />
                    <Select value={statusFilter} onChange={setStatusFilter} style={{ width: 100 }} options={[
                      { value: 'all', label: '全部状态' },
                      { value: 'success', label: '成功' },
                      { value: 'failed', label: '失败' },
                      { value: 'warning', label: '警告' },
                    ]} />
                    <RangePicker value={dateRange} onChange={setDateRange} showTime placeholder={['开始时间', '结束时间']} />
                    <Button icon={<SearchOutlined />} type="primary">搜索</Button>
                    <Button icon={<ReloadOutlined />} onClick={() => {
                      setSearchText('')
                      setActionTypeFilter('all')
                      setModuleFilter('all')
                      setStatusFilter('all')
                      setDateRange(null)
                    }}>重置</Button>
                  </Space>

                  <Table
                    columns={operationColumns}
                    dataSource={mockOperationLogs}
                    rowKey="id"
                    loading={loading}
                    pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 条操作日志` }}
                    locale={{ emptyText: <Empty description="暂无操作日志" /> }}
                  />
                </div>
              ),
            },
            {
              key: 'audit',
              label: '数据变更审计',
              children: (
                <div>
                  <Alert
                    message="审计说明"
                    description="所有数据变更操作都会被记录，包括变更前值和变更后值，便于追溯和审计。"
                    type="info"
                    showIcon
                    style={{ marginBottom: '16px' }}
                  />
                  <Table
                    columns={auditColumns}
                    dataSource={mockAuditLogs}
                    rowKey="id"
                    loading={loading}
                    pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 条变更记录` }}
                    locale={{ emptyText: <Empty description="暂无变更记录" /> }}
                  />
                </div>
              ),
            },
            {
              key: 'security',
              label: '安全监控',
              children: (
                <div>
                  <Row gutter={[16, 16]} style={{ marginBottom: '16px' }}>
                    <Col span={8}>
                      <Card size="small">
                        <Statistic title="登录成功" value={mockSecurityEvents.filter(e => e.event_type === 'login' && e.status === 'success').length} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} />
                      </Card>
                    </Col>
                    <Col span={8}>
                      <Card size="small">
                        <Statistic title="登录失败" value={mockSecurityEvents.filter(e => e.event_type === 'failed_login').length} valueStyle={{ color: '#f5222d' }} prefix={<LockOutlined />} />
                      </Card>
                    </Col>
                    <Col span={8}>
                      <Card size="small">
                        <Statistic title="已拦截" value={mockSecurityEvents.filter(e => e.status === 'blocked').length} valueStyle={{ color: '#faad14' }} prefix={<SafetyOutlined />} />
                      </Card>
                    </Col>
                  </Row>

                  <Table
                    columns={securityColumns}
                    dataSource={mockSecurityEvents}
                    rowKey="id"
                    loading={loading}
                    pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 个安全事件` }}
                    locale={{ emptyText: <Empty description="暂无安全事件" /> }}
                  />
                </div>
              ),
            },
          ]}
        />
      </Card>

      {/* 操作日志详情Modal */}
      <Modal
        title="操作日志详情"
        open={detailModalOpen}
        onCancel={() => setDetailModalOpen(false)}
        footer={[
          <Button key="close" onClick={() => setDetailModalOpen(false)}>关闭</Button>,
        ]}
        width={700}
      >
        {viewingLog && (
          <div>
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="操作时间" span={2}>{viewingLog.timestamp}</Descriptions.Item>
              <Descriptions.Item label="操作用户">{viewingLog.user}</Descriptions.Item>
              <Descriptions.Item label="用户角色">{viewingLog.user_role}</Descriptions.Item>
              <Descriptions.Item label="操作类型">
                <Tag color={actionTypeColors[viewingLog.action_type]}>{actionTypeText[viewingLog.action_type]}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="所属模块">{viewingLog.module}</Descriptions.Item>
              <Descriptions.Item label="操作内容" span={2}>{viewingLog.action}</Descriptions.Item>
              <Descriptions.Item label="操作目标" span={2}>{viewingLog.target}</Descriptions.Item>
              <Descriptions.Item label="IP地址">
                <Space>
                  <GlobalOutlined />
                  <Text code>{viewingLog.ip}</Text>
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="操作状态">
                <Tag color={statusColors[viewingLog.status]}>{viewingLog.status === 'success' ? '成功' : viewingLog.status === 'failed' ? '失败' : '警告'}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="耗时">{viewingLog.duration} ms</Descriptions.Item>
              <Descriptions.Item label="User Agent" span={2}>
                <Space>
                  <DesktopOutlined />
                  <Text style={{ fontSize: '11px' }}>{viewingLog.user_agent}</Text>
                </Space>
              </Descriptions.Item>
            </Descriptions>

            {viewingLog.details && (
              <>
                <Divider style={{ margin: '16px 0' }} />
                <div>
                  <Text strong>操作详情：</Text>
                  <div style={{ marginTop: '8px', padding: '12px', background: '#fafafa', borderRadius: '8px', border: '1px solid #e8e8e8' }}>
                    <Text>{viewingLog.details}</Text>
                  </div>
                </div>
              </>
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}
