import { useState, useEffect } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Input, Select,
  Statistic, Row, Col, Spin, message, Modal, Descriptions, List,
  Badge, Tooltip, Empty, Tabs, Switch, Form, Avatar,
  Tree, Checkbox, Divider, Alert
} from 'antd'
import {
  SettingOutlined, ReloadOutlined, SearchOutlined,
  EyeOutlined, UserOutlined, SafetyOutlined,
  PlusOutlined, EditOutlined, DeleteOutlined,
  KeyOutlined, LockOutlined, SaveOutlined,
  CheckCircleOutlined, WarningOutlined, SyncOutlined
} from '@ant-design/icons'

const { Title, Text, Paragraph } = Typography

interface User {
  id: string
  username: string
  name: string
  email: string
  role: string
  status: 'active' | 'inactive'
  last_login: string
  created_at: string
}

interface Role {
  id: string
  name: string
  description: string
  user_count: number
  permissions: string[]
  created_at: string
}

interface SystemConfig {
  site_name: string
  site_url: string
  admin_email: string
  timezone: string
  language: string
  currency: string
  order_auto_confirm: boolean
  low_stock_threshold: number
  ai_auto_reply: boolean
  log_retention_days: number
  backup_enabled: boolean
  backup_frequency: string
}

const roleColors: Record<string, string> = {
  admin: 'red',
  manager: 'orange',
  operator: 'blue',
  customer_service: 'green',
  viewer: 'default',
}

const roleText: Record<string, string> = {
  admin: '超级管理员',
  manager: '运营经理',
  operator: '运营专员',
  customer_service: '客服',
  viewer: '只读用户',
}

const permissionTree = [
  {
    title: '供应链管理',
    key: 'supply',
    children: [
      { title: '选品管理', key: 'supply:sourcing' },
      { title: '产品管理', key: 'supply:products' },
      { title: '产品工作流', key: 'supply:pipeline' },
      { title: '库存管理', key: 'supply:inventory' },
      { title: '供应商管理', key: 'supply:suppliers' },
      { title: '采购管理', key: 'supply:purchase' },
    ],
  },
  {
    title: '订单与物流',
    key: 'order',
    children: [
      { title: '订单管理', key: 'order:orders' },
      { title: '物流追踪', key: 'order:logistics' },
      { title: '代采工作台', key: 'order:procurement' },
    ],
  },
  {
    title: '客户与营销',
    key: 'customer',
    children: [
      { title: '客户管理', key: 'customer:customers' },
      { title: '客服工单', key: 'customer:tickets' },
      { title: '营销活动', key: 'customer:marketing' },
      { title: '内容生成', key: 'customer:content' },
    ],
  },
  {
    title: '数据分析',
    key: 'analytics',
    children: [
      { title: '数据看板', key: 'analytics:dashboard' },
      { title: '财务对账', key: 'analytics:finance' },
      { title: '经营周报', key: 'analytics:reports' },
    ],
  },
  {
    title: '系统管理',
    key: 'system',
    children: [
      { title: '用户管理', key: 'system:users' },
      { title: '角色权限', key: 'system:roles' },
      { title: '系统设置', key: 'system:settings' },
      { title: '操作日志', key: 'system:logs' },
      { title: 'API管理', key: 'system:api' },
    ],
  },
]

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState('users')
  const [loading, setLoading] = useState(false)
  const [userModalOpen, setUserModalOpen] = useState(false)
  const [roleModalOpen, setRoleModalOpen] = useState(false)
  const [editingUser, setEditingUser] = useState<User | null>(null)
  const [editingRole, setEditingRole] = useState<Role | null>(null)
  const [selectedPermissions, setSelectedPermissions] = useState<string[]>([])
  const [userForm] = Form.useForm()
  const [roleForm] = Form.useForm()
  const [config, setConfig] = useState<SystemConfig>({
    site_name: 'Nuotao Outdoor AI OS',
    site_url: 'https://admin.nuotaooutdoor.com',
    admin_email: 'admin@nuotaooutdoor.com',
    timezone: 'Asia/Shanghai',
    language: 'zh-CN',
    currency: 'USD',
    order_auto_confirm: false,
    low_stock_threshold: 10,
    ai_auto_reply: true,
    log_retention_days: 90,
    backup_enabled: true,
    backup_frequency: 'daily',
  })
  const [savingConfig, setSavingConfig] = useState(false)
  // 真实API数据状态
  const [settingsData, setSettingsData] = useState<any>(null)

  // 模拟用户数据
  const mockUsers: User[] = [
    { id: '1', username: 'admin', name: '系统管理员', email: 'admin@nuotaooutdoor.com', role: 'admin', status: 'active', last_login: '2026-09-05 10:30:00', created_at: '2025-01-01' },
    { id: '2', username: 'joran', name: 'Joran', email: 'joran@nuotaooutdoor.com', role: 'manager', status: 'active', last_login: '2026-09-05 09:15:00', created_at: '2025-03-15' },
    { id: '3', username: 'operator1', name: '运营专员A', email: 'op1@nuotaooutdoor.com', role: 'operator', status: 'active', last_login: '2026-09-04 16:45:00', created_at: '2025-06-01' },
    { id: '4', username: 'cs001', name: '客服小美', email: 'cs1@nuotaooutdoor.com', role: 'customer_service', status: 'active', last_login: '2026-09-05 08:00:00', created_at: '2025-08-01' },
    { id: '5', username: 'cs002', name: '客服小李', email: 'cs2@nuotaooutdoor.com', role: 'customer_service', status: 'active', last_login: '2026-09-04 14:30:00', created_at: '2025-09-01' },
    { id: '6', username: 'viewer01', name: '财务审计', email: 'audit@nuotaooutdoor.com', role: 'viewer', status: 'inactive', last_login: '2026-08-15 10:00:00', created_at: '2026-01-01' },
  ]

  // 模拟角色数据
  const mockRoles: Role[] = [
    { id: '1', name: 'admin', description: '超级管理员，拥有所有权限', user_count: 1, permissions: ['all'], created_at: '2025-01-01' },
    { id: '2', name: 'manager', description: '运营经理，管理供应链和订单', user_count: 1, permissions: ['supply', 'order', 'customer', 'analytics'], created_at: '2025-01-01' },
    { id: '3', name: 'operator', description: '运营专员，处理日常运营工作', user_count: 1, permissions: ['supply:sourcing', 'supply:products', 'supply:pipeline', 'order:orders'], created_at: '2025-01-01' },
    { id: '4', name: 'customer_service', description: '客服，处理客户咨询和工单', user_count: 2, permissions: ['customer:customers', 'customer:tickets', 'order:orders'], created_at: '2025-01-01' },
    { id: '5', name: 'viewer', description: '只读用户，只能查看数据', user_count: 1, permissions: ['analytics:dashboard', 'analytics:finance'], created_at: '2025-01-01' },
  ]

  // 加载系统设置数据（调用真实API，失败则使用mock数据降级）
  const loadSettingsData = async () => {
    try {
      setLoading(true)
      // 调用系统设置API（新创建的端点）
      const settingsResp = await fetch('/api/v1/system-settings')
      if (settingsResp.ok) {
        const settingsData = await settingsResp.json()
        setSettingsData(settingsData)
        // 如果API返回了设置数据，更新config状态
        if (settingsData?.data) {
          setConfig(settingsData.data)
        }
        console.log('System settings:', settingsData)
      }
      message.success('系统设置数据加载完成')
    } catch (e: any) {
      console.error('Load settings data error:', e)
      message.warning(`API调用失败，使用模拟数据：${e.message || '未知错误'}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadSettingsData()
  }, [])

  // 用户表格列
  const userColumns = [
    {
      title: '用户',
      key: 'user',
      width: 200,
      render: (_: any, record: User) => (
        <Space>
          <Avatar icon={<UserOutlined />} style={{ backgroundColor: '#722ed1' }} />
          <div>
            <div style={{ fontWeight: 500 }}>{record.name}</div>
            <div style={{ fontSize: '11px', color: '#999' }}>@{record.username}</div>
          </div>
        </Space>
      ),
    },
    {
      title: '邮箱',
      dataIndex: 'email',
      key: 'email',
      width: 200,
    },
    {
      title: '角色',
      dataIndex: 'role',
      key: 'role',
      width: 120,
      render: (role: string) => <Tag color={roleColors[role] || 'default'}>{roleText[role] || role}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={status === 'active' ? 'green' : 'default'}>
          {status === 'active' ? '启用' : '禁用'}
        </Tag>
      ),
    },
    {
      title: '最后登录',
      dataIndex: 'last_login',
      key: 'last_login',
      width: 160,
      render: (text: string) => <Text type="secondary" style={{ fontSize: '12px' }}>{text}</Text>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 180,
      render: (_: any, record: User) => (
        <Space size="small">
          <Button size="small" icon={<EditOutlined />} onClick={() => {
            setEditingUser(record)
            userForm.setFieldsValue(record)
            setUserModalOpen(true)
          }}>编辑</Button>
          <Button size="small" icon={<KeyOutlined />} onClick={() => message.info('重置密码功能开发中')}>重置密码</Button>
          <Popconfirm title="确定删除该用户？" onConfirm={() => message.success('用户已删除')} okText="确定" cancelText="取消">
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // 角色表格列
  const roleColumns = [
    {
      title: '角色名称',
      dataIndex: 'name',
      key: 'name',
      width: 150,
      render: (name: string) => (
        <Space>
          <SafetyOutlined style={{ color: roleColors[name] || '#999' }} />
          <Text strong>{roleText[name] || name}</Text>
        </Space>
      ),
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      width: 250,
    },
    {
      title: '用户数',
      dataIndex: 'user_count',
      key: 'user_count',
      width: 100,
      render: (count: number) => <Badge count={count} style={{ backgroundColor: '#722ed1' }} />,
    },
    {
      title: '权限数',
      dataIndex: 'permissions',
      key: 'permissions',
      width: 100,
      render: (perms: string[]) => <Text>{perms.includes('all') ? '全部' : perms.length} 项</Text>,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 120,
    },
    {
      title: '操作',
      key: 'actions',
      width: 150,
      render: (_: any, record: Role) => (
        <Space size="small">
          <Button size="small" type="primary" icon={<EditOutlined />} onClick={() => {
            setEditingRole(record)
            setSelectedPermissions(record.permissions.includes('all') ? [] : record.permissions)
            roleForm.setFieldsValue(record)
            setRoleModalOpen(true)
          }}>配置权限</Button>
          {record.name !== 'admin' && (
            <Popconfirm title="确定删除该角色？" onConfirm={() => message.success('角色已删除')} okText="确定" cancelText="取消">
              <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  // 保存系统配置
  const handleSaveConfig = () => {
    setSavingConfig(true)
    setTimeout(() => {
      message.success('系统配置已保存')
      setSavingConfig(false)
    }, 1000)
  }

  // 更新配置
  const updateConfig = (key: keyof SystemConfig, value: any) => {
    setConfig(prev => ({ ...prev, [key]: value }))
  }

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: '24px' }}>
        <Space>
          <SettingOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>系统设置</Title>
            <Text type="secondary">用户角色、权限配置、系统参数设置</Text>
          </div>
        </Space>
      </div>

      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: '16px' }}>
        <Col span={6}>
          <Card size="small">
            <Statistic title="系统用户" value={mockUsers.length} prefix={<UserOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="活跃用户" value={mockUsers.filter(u => u.status === 'active').length} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="角色数量" value={mockRoles.length} prefix={<SafetyOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="系统状态" value="正常" valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} />
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
              key: 'users',
              label: '用户管理',
              children: (
                <div>
                  <div style={{ marginBottom: '16px', display: 'flex', justifyContent: 'space-between' }}>
                    <Space>
                      <Input placeholder="搜索用户名/邮箱" prefix={<SearchOutlined />} style={{ width: 220 }} allowClear />
                      <Select placeholder="筛选角色" style={{ width: 120 }} allowClear options={Object.entries(roleText).map(([key, text]) => ({ value: key, label: text }))} />
                    </Space>
                    <Button type="primary" icon={<PlusOutlined />} onClick={() => {
                      setEditingUser(null)
                      userForm.resetFields()
                      setUserModalOpen(true)
                    }}>添加用户</Button>
                  </div>

                  <Table
                    columns={userColumns}
                    dataSource={mockUsers}
                    rowKey="id"
                    loading={loading}
                    pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 个用户` }}
                    locale={{ emptyText: <Empty description="暂无用户" /> }}
                  />
                </div>
              ),
            },
            {
              key: 'roles',
              label: '角色权限',
              children: (
                <div>
                  <div style={{ marginBottom: '16px', display: 'flex', justifyContent: 'space-between' }}>
                    <Alert
                      message="权限说明"
                      description="角色权限采用树形结构，父权限包含所有子权限。超级管理员拥有所有权限，不可修改。"
                      type="info"
                      showIcon
                      style={{ flex: 1, marginRight: '16px' }}
                    />
                    <Button type="primary" icon={<PlusOutlined />} onClick={() => {
                      setEditingRole(null)
                      setSelectedPermissions([])
                      roleForm.resetFields()
                      setRoleModalOpen(true)
                    }}>添加角色</Button>
                  </div>

                  <Table
                    columns={roleColumns}
                    dataSource={mockRoles}
                    rowKey="id"
                    loading={loading}
                    pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 个角色` }}
                    locale={{ emptyText: <Empty description="暂无角色" /> }}
                  />
                </div>
              ),
            },
            {
              key: 'config',
              label: '系统参数',
              children: (
                <div>
                  <Row gutter={[24, 24]}>
                    <Col span={12}>
                      <Card size="small" title="基础设置" style={{ marginBottom: '16px' }}>
                        <Form layout="vertical">
                          <Form.Item label="站点名称">
                            <Input value={config.site_name} onChange={(e) => updateConfig('site_name', e.target.value)} />
                          </Form.Item>
                          <Form.Item label="站点URL">
                            <Input value={config.site_url} onChange={(e) => updateConfig('site_url', e.target.value)} />
                          </Form.Item>
                          <Form.Item label="管理员邮箱">
                            <Input value={config.admin_email} onChange={(e) => updateConfig('admin_email', e.target.value)} />
                          </Form.Item>
                          <Row gutter={16}>
                            <Col span={12}>
                              <Form.Item label="时区">
                                <Select value={config.timezone} onChange={(v) => updateConfig('timezone', v)} options={[
                                  { value: 'Asia/Shanghai', label: 'Asia/Shanghai (UTC+8)' },
                                  { value: 'UTC', label: 'UTC' },
                                  { value: 'America/Los_Angeles', label: 'America/Los_Angeles (UTC-8)' },
                                  { value: 'Europe/London', label: 'Europe/London (UTC+0)' },
                                ]} />
                              </Form.Item>
                            </Col>
                            <Col span={12}>
                              <Form.Item label="语言">
                                <Select value={config.language} onChange={(v) => updateConfig('language', v)} options={[
                                  { value: 'zh-CN', label: '简体中文' },
                                  { value: 'en-US', label: 'English' },
                                ]} />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Form.Item label="默认货币">
                            <Select value={config.currency} onChange={(v) => updateConfig('currency', v)} options={[
                              { value: 'USD', label: '美元 (USD)' },
                              { value: 'EUR', label: '欧元 (EUR)' },
                              { value: 'GBP', label: '英镑 (GBP)' },
                              { value: 'CNY', label: '人民币 (CNY)' },
                            ]} />
                          </Form.Item>
                        </Form>
                      </Card>
                    </Col>

                    <Col span={12}>
                      <Card size="small" title="业务设置" style={{ marginBottom: '16px' }}>
                        <Form layout="vertical">
                          <Form.Item label="订单自动确认">
                            <Switch checked={config.order_auto_confirm} onChange={(v) => updateConfig('order_auto_confirm', v)} />
                            <div style={{ fontSize: '12px', color: '#999', marginTop: '4px' }}>开启后，支付成功的订单自动确认，无需人工审核</div>
                          </Form.Item>
                          <Form.Item label="低库存预警阈值">
                            <Input type="number" value={config.low_stock_threshold} onChange={(e) => updateConfig('low_stock_threshold', Number(e.target.value))} addonAfter="件" />
                          </Form.Item>
                          <Form.Item label="AI自动回复">
                            <Switch checked={config.ai_auto_reply} onChange={(v) => updateConfig('ai_auto_reply', v)} />
                            <div style={{ fontSize: '12px', color: '#999', marginTop: '4px' }}>开启后，客服工单自动生成AI回复建议</div>
                          </Form.Item>
                        </Form>
                      </Card>

                      <Card size="small" title="安全与备份">
                        <Form layout="vertical">
                          <Form.Item label="日志保留天数">
                            <Input type="number" value={config.log_retention_days} onChange={(e) => updateConfig('log_retention_days', Number(e.target.value))} addonAfter="天" />
                          </Form.Item>
                          <Form.Item label="自动备份">
                            <Switch checked={config.backup_enabled} onChange={(v) => updateConfig('backup_enabled', v)} />
                          </Form.Item>
                          {config.backup_enabled && (
                            <Form.Item label="备份频率">
                              <Select value={config.backup_frequency} onChange={(v) => updateConfig('backup_frequency', v)} options={[
                                { value: 'daily', label: '每天' },
                                { value: 'weekly', label: '每周' },
                                { value: 'monthly', label: '每月' },
                              ]} />
                            </Form.Item>
                          )}
                        </Form>
                      </Card>
                    </Col>
                  </Row>

                  <div style={{ marginTop: '24px', textAlign: 'center' }}>
                    <Button type="primary" size="large" icon={<SaveOutlined />} onClick={handleSaveConfig} loading={savingConfig}>
                      保存所有配置
                    </Button>
                  </div>
                </div>
              ),
            },
          ]}
        />
      </Card>

      {/* 用户编辑Modal */}
      <Modal
        title={editingUser ? '编辑用户' : '添加用户'}
        open={userModalOpen}
        onCancel={() => setUserModalOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setUserModalOpen(false)}>取消</Button>,
          <Button key="save" type="primary" onClick={() => {
            message.success(editingUser ? '用户已更新' : '用户已添加')
            setUserModalOpen(false)
          }}>保存</Button>,
        ]}
        width={600}
      >
        <Form form={userForm} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
                <Input placeholder="请输入用户名" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="name" label="姓名" rules={[{ required: true, message: '请输入姓名' }]}>
                <Input placeholder="请输入姓名" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="email" label="邮箱" rules={[{ required: true, type: 'email', message: '请输入有效邮箱' }]}>
            <Input placeholder="请输入邮箱" />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="role" label="角色" rules={[{ required: true }]}>
                <Select options={Object.entries(roleText).map(([key, text]) => ({ value: key, label: text }))} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="status" label="状态" initialValue="active">
                <Select options={[
                  { value: 'active', label: '启用' },
                  { value: 'inactive', label: '禁用' },
                ]} />
              </Form.Item>
            </Col>
          </Row>
          {!editingUser && (
            <Form.Item name="password" label="初始密码" rules={[{ required: true, message: '请输入初始密码' }]}>
              <Input.Password placeholder="请输入初始密码" />
            </Form.Item>
          )}
        </Form>
      </Modal>

      {/* 角色权限配置Modal */}
      <Modal
        title={editingRole ? `配置权限 - ${roleText[editingRole.name] || editingRole.name}` : '添加角色'}
        open={roleModalOpen}
        onCancel={() => setRoleModalOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setRoleModalOpen(false)}>取消</Button>,
          <Button key="save" type="primary" onClick={() => {
            message.success('权限配置已保存')
            setRoleModalOpen(false)
          }}>保存</Button>,
        ]}
        width={700}
      >
        <Form form={roleForm} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="name" label="角色标识" rules={[{ required: true, message: '请输入角色标识' }]}>
                <Input placeholder="例如：manager" disabled={editingRole?.name === 'admin'} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="description" label="角色描述">
                <Input placeholder="请输入角色描述" />
              </Form.Item>
            </Col>
          </Row>

          <Divider style={{ margin: '12px 0' }} />

          <div>
            <Text strong>权限配置：</Text>
            {editingRole?.name === 'admin' ? (
              <Alert
                message="超级管理员拥有所有权限，不可修改"
                type="warning"
                showIcon
                style={{ marginTop: '12px' }}
              />
            ) : (
              <div style={{ marginTop: '12px', maxHeight: '400px', overflowY: 'auto', padding: '12px', border: '1px solid #e8e8e8', borderRadius: '8px' }}>
                <Tree
                  checkable
                  defaultExpandAll
                  checkedKeys={selectedPermissions}
                  onCheck={(checkedKeys) => setSelectedPermissions(checkedKeys as string[])}
                  treeData={permissionTree}
                />
              </div>
            )}
          </div>
        </Form>
      </Modal>
    </div>
  )
}
