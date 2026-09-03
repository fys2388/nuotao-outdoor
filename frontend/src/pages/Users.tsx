import { useState, useEffect } from 'react';
import {
  Table,
  Button,
  Modal,
  Form,
  Input,
  Select,
  Tag,
  Space,
  message,
  Card,
  Row,
  Col,
  Statistic,
  Switch,
  Popconfirm,
  Avatar,
  Divider,
  List,
  Checkbox,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  SearchOutlined,
  ReloadOutlined,
  UserOutlined,
  SafetyOutlined,
  LockOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';

// 用户类型定义
interface User {
  id: number;
  username: string;
  email: string;
  full_name: string;
  role: 'admin' | 'manager' | 'operator' | 'customer_service' | 'viewer';
  status: 'active' | 'inactive';
  last_login: string;
  created_at: string;
  permissions: string[];
}

// 角色配置
const roleConfig: Record<string, { color: string; text: string; description: string }> = {
  admin: { color: 'red', text: '管理员', description: '拥有所有权限' },
  manager: { color: 'orange', text: '运营经理', description: '管理产品、订单、营销' },
  operator: { color: 'blue', text: '运营专员', description: '日常运营操作' },
  customer_service: { color: 'green', text: '客服', description: '处理客户咨询和售后' },
  viewer: { color: 'default', text: '只读用户', description: '仅查看数据' },
};

// 权限列表
const allPermissions = [
  { group: '产品管理', items: ['product:view', 'product:create', 'product:edit', 'product:delete', 'product:export'] },
  { group: '订单管理', items: ['order:view', 'order:create', 'order:edit', 'order:delete', 'order:export', 'order:refund'] },
  { group: '客户管理', items: ['customer:view', 'customer:create', 'customer:edit', 'customer:delete', 'customer:export'] },
  { group: '营销管理', items: ['marketing:view', 'marketing:create', 'marketing:edit', 'marketing:delete', 'marketing:send'] },
  { group: 'AI Agent', items: ['agent:view', 'agent:run', 'agent:config', 'agent:approve'] },
  { group: '数据分析', items: ['analytics:view', 'analytics:export', 'analytics:dashboard'] },
  { group: '系统设置', items: ['system:view', 'system:config', 'system:user', 'system:log', 'system:backup'] },
];

const { Option } = Select;

// 模拟数据
const mockUsers: User[] = [
  {
    id: 1,
    username: 'admin',
    email: 'admin@nuotaooutdoor.com',
    full_name: '系统管理员',
    role: 'admin',
    status: 'active',
    last_login: '2024-03-23 10:30:00',
    created_at: '2024-01-01',
    permissions: allPermissions.flatMap((g) => g.items),
  },
  {
    id: 2,
    username: 'joran',
    email: 'joran@nuotaooutdoor.com',
    full_name: 'Joran',
    role: 'manager',
    status: 'active',
    last_login: '2024-03-23 09:15:00',
    created_at: '2024-01-15',
    permissions: [
      'product:view', 'product:create', 'product:edit', 'product:export',
      'order:view', 'order:edit', 'order:export',
      'customer:view', 'customer:edit', 'customer:export',
      'marketing:view', 'marketing:create', 'marketing:edit', 'marketing:send',
      'agent:view', 'agent:run', 'agent:approve',
      'analytics:view', 'analytics:export', 'analytics:dashboard',
    ],
  },
  {
    id: 3,
    username: 'cs001',
    email: 'cs001@nuotaooutdoor.com',
    full_name: '客服小王',
    role: 'customer_service',
    status: 'active',
    last_login: '2024-03-22 16:45:00',
    created_at: '2024-02-01',
    permissions: [
      'order:view', 'order:edit',
      'customer:view', 'customer:edit',
      'agent:view', 'agent:run',
    ],
  },
  {
    id: 4,
    username: 'operator001',
    email: 'operator001@nuotaooutdoor.com',
    full_name: '运营小李',
    role: 'operator',
    status: 'active',
    last_login: '2024-03-23 08:00:00',
    created_at: '2024-02-15',
    permissions: [
      'product:view', 'product:create', 'product:edit',
      'order:view', 'order:edit',
      'marketing:view', 'marketing:create',
      'analytics:view',
    ],
  },
  {
    id: 5,
    username: 'viewer001',
    email: 'viewer001@nuotaooutdoor.com',
    full_name: '数据查看员',
    role: 'viewer',
    status: 'inactive',
    last_login: '2024-03-10 14:20:00',
    created_at: '2024-03-01',
    permissions: ['product:view', 'order:view', 'customer:view', 'analytics:view'],
  },
];

const UsersPage = () => {
  const [users, setUsers] = useState<User[]>(mockUsers);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [permissionModalVisible, setPermissionModalVisible] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [selectedPermissions, setSelectedPermissions] = useState<string[]>([]);
  const [searchText, setSearchText] = useState('');
  const [roleFilter, setRoleFilter] = useState<string>('all');
  const [form] = Form.useForm();

  // 加载用户
  const loadUsers = async () => {
    setLoading(true);
    setTimeout(() => {
      setUsers(mockUsers);
      setLoading(false);
    }, 500);
  };

  useEffect(() => {
    loadUsers();
  }, []);

  // 打开新增/编辑弹窗
  const openModal = (user?: User) => {
    setEditingUser(user || null);
    if (user) {
      form.setFieldsValue({
        username: user.username,
        email: user.email,
        full_name: user.full_name,
        role: user.role,
        status: user.status,
      });
    } else {
      form.resetFields();
    }
    setModalVisible(true);
  };

  // 保存用户
  const handleSave = async (values: any) => {
    try {
      if (editingUser) {
        const updatedUsers = users.map((u) =>
          u.id === editingUser.id ? { ...u, ...values } : u
        );
        setUsers(updatedUsers);
        message.success('用户更新成功');
      } else {
        const newUser: User = {
          id: Math.max(...users.map((u) => u.id)) + 1,
          ...values,
          last_login: '-',
          created_at: new Date().toISOString().split('T')[0],
          permissions: roleConfig[values.role] ? allPermissions.flatMap((g) => g.items) : [],
        };
        setUsers([newUser, ...users]);
        message.success('用户创建成功');
      }
      setModalVisible(false);
    } catch (error) {
      message.error('保存失败');
    }
  };

  // 删除用户
  const handleDelete = (id: number) => {
    setUsers(users.filter((u) => u.id !== id));
    message.success('用户删除成功');
  };

  // 切换用户状态
  const toggleStatus = (id: number, checked: boolean) => {
    setUsers(
      users.map((u) => (u.id === id ? { ...u, status: checked ? 'active' : 'inactive' } : u))
    );
    message.success(`用户已${checked ? '启用' : '禁用'}`);
  };

  // 打开权限编辑弹窗
  const openPermissionModal = (user: User) => {
    setEditingUser(user);
    setSelectedPermissions([...user.permissions]);
    setPermissionModalVisible(true);
  };

  // 保存权限
  const handleSavePermissions = () => {
    if (editingUser) {
      setUsers(
        users.map((u) => (u.id === editingUser.id ? { ...u, permissions: selectedPermissions } : u))
      );
      message.success('权限更新成功');
    }
    setPermissionModalVisible(false);
  };

  // 表格列
  const columns: ColumnsType<User> = [
    {
      title: '用户',
      key: 'user',
      render: (_, record) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Avatar size={40} icon={<UserOutlined />} style={{ backgroundColor: '#1890ff' }} />
          <div>
            <div style={{ fontWeight: 500 }}>{record.full_name}</div>
            <div style={{ color: '#999', fontSize: 12 }}>@{record.username}</div>
          </div>
        </div>
      ),
    },
    {
      title: '邮箱',
      dataIndex: 'email',
      key: 'email',
    },
    {
      title: '角色',
      dataIndex: 'role',
      key: 'role',
      width: 120,
      render: (role: string) => {
        const config = roleConfig[role] || { color: 'default', text: role };
        return <Tag color={config.color}>{config.text}</Tag>;
      },
      filters: Object.entries(roleConfig).map(([key, value]) => ({ text: value.text, value: key })),
      onFilter: (value, record) => record.role === value,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string, record) => (
        <Switch
          checked={status === 'active'}
          onChange={(checked) => toggleStatus(record.id, checked)}
          checkedChildren="启用"
          unCheckedChildren="禁用"
        />
      ),
    },
    {
      title: '权限数',
      key: 'permissions_count',
      width: 100,
      render: (_, record) => <Tag color="blue">{record.permissions.length} 项</Tag>,
    },
    {
      title: '最后登录',
      dataIndex: 'last_login',
      key: 'last_login',
      width: 170,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 120,
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_, record) => (
        <Space size="small">
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openModal(record)}>
            编辑
          </Button>
          <Button type="link" size="small" icon={<SafetyOutlined />} onClick={() => openPermissionModal(record)}>
            权限
          </Button>
          <Popconfirm title="确定删除该用户？" onConfirm={() => handleDelete(record.id)} okText="确定" cancelText="取消">
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  // 过滤用户
  const filteredUsers = users.filter((u) => {
    const matchSearch =
      !searchText ||
      u.username.toLowerCase().includes(searchText.toLowerCase()) ||
      u.email.toLowerCase().includes(searchText.toLowerCase()) ||
      u.full_name.toLowerCase().includes(searchText.toLowerCase());
    const matchRole = roleFilter === 'all' || u.role === roleFilter;
    return matchSearch && matchRole;
  });

  // 统计数据
  const stats = {
    total: users.length,
    active: users.filter((u) => u.status === 'active').length,
    admin: users.filter((u) => u.role === 'admin').length,
    roles: Object.keys(roleConfig).length,
  };

  return (
    <div style={{ padding: 24 }}>
      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic title="用户总数" value={stats.total} suffix="人" />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="活跃用户" value={stats.active} suffix="人" valueStyle={{ color: '#52c41a' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="管理员" value={stats.admin} suffix="人" valueStyle={{ color: '#f5222d' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="角色数量" value={stats.roles} suffix="种" />
          </Card>
        </Col>
      </Row>

      {/* 操作栏 */}
      <Card style={{ marginBottom: 16 }}>
        <Space wrap>
          <Input
            placeholder="搜索用户名/邮箱/姓名"
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ width: 280 }}
            allowClear
          />
          <Select value={roleFilter} onChange={setRoleFilter} style={{ width: 140 }}>
            <Option value="all">全部角色</Option>
            {Object.entries(roleConfig).map(([key, value]) => (
              <Option key={key} value={key}>
                {value.text}
              </Option>
            ))}
          </Select>
          <Button icon={<ReloadOutlined />} onClick={loadUsers}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => openModal()}>
            新增用户
          </Button>
        </Space>
      </Card>

      {/* 用户表格 */}
      <Card>
        <Table
          columns={columns}
          dataSource={filteredUsers}
          rowKey="id"
          loading={loading}
          pagination={{
            pageSize: 10,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total) => `共 ${total} 条记录`,
          }}
        />
      </Card>

      {/* 新增/编辑用户弹窗 */}
      <Modal
        title={editingUser ? '编辑用户' : '新增用户'}
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        footer={null}
        width={500}
      >
        <Form form={form} layout="vertical" onFinish={handleSave}>
          <Form.Item name="full_name" label="姓名" rules={[{ required: true, message: '请输入姓名' }]}>
            <Input placeholder="请输入姓名" />
          </Form.Item>

          <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input placeholder="请输入用户名" disabled={!!editingUser} />
          </Form.Item>

          <Form.Item name="email" label="邮箱" rules={[{ required: true, type: 'email', message: '请输入有效邮箱' }]}>
            <Input placeholder="请输入邮箱" />
          </Form.Item>

          <Form.Item name="role" label="角色" rules={[{ required: true, message: '请选择角色' }]}>
            <Select placeholder="请选择角色">
              {Object.entries(roleConfig).map(([key, value]) => (
                <Option key={key} value={key}>
                  {value.text} - {value.description}
                </Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item name="status" label="状态" rules={[{ required: true, message: '请选择状态' }]}>
            <Select placeholder="请选择状态">
              <Option value="active">启用</Option>
              <Option value="inactive">禁用</Option>
            </Select>
          </Form.Item>

          {!editingUser && (
            <Form.Item name="password" label="初始密码" rules={[{ required: true, message: '请输入初始密码' }]}>
              <Input.Password placeholder="请输入初始密码" />
            </Form.Item>
          )}

          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit">
                保存
              </Button>
              <Button onClick={() => setModalVisible(false)}>取消</Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* 权限编辑弹窗 */}
      <Modal
        title={`编辑权限 - ${editingUser?.full_name}`}
        open={permissionModalVisible}
        onCancel={() => setPermissionModalVisible(false)}
        footer={[
          <Button key="cancel" onClick={() => setPermissionModalVisible(false)}>
            取消
          </Button>,
          <Button key="save" type="primary" onClick={handleSavePermissions}>
            保存权限
          </Button>,
        ]}
        width={700}
      >
        <div style={{ marginBottom: 16 }}>
          <Space>
            <Button
              size="small"
              onClick={() => setSelectedPermissions(allPermissions.flatMap((g) => g.items))}
            >
              全选
            </Button>
            <Button size="small" onClick={() => setSelectedPermissions([])}>
              清空
            </Button>
            <span style={{ color: '#666' }}>已选择 {selectedPermissions.length} 项权限</span>
          </Space>
        </div>

        <Divider />

        {allPermissions.map((group) => (
          <div key={group.group} style={{ marginBottom: 24 }}>
            <h4 style={{ marginBottom: 12 }}>
              <LockOutlined style={{ marginRight: 8 }} />
              {group.group}
            </h4>
            <Checkbox.Group
              value={selectedPermissions}
              onChange={(checked) => setSelectedPermissions(checked as string[])}
              style={{ display: 'flex', flexWrap: 'wrap', gap: '8px 24px' }}
            >
              {group.items.map((perm) => (
                <Checkbox key={perm} value={perm}>
                  {perm.split(':')[1]}
                </Checkbox>
              ))}
            </Checkbox.Group>
          </div>
        ))}
      </Modal>
    </div>
  );
};

export default UsersPage;
