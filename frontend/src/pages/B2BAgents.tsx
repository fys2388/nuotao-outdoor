/**
 * B2B 代理商管理页面框架
 * 支持代理商注册、订单管理、结算管理
 */
import React, { useState, useEffect } from 'react';
import {
  Card,
  Table,
  Button,
  Modal,
  Form,
  Input,
  Select,
  Tag,
  Statistic,
  Row,
  Col,
  DatePicker,
  message,
  Tabs,
  Space,
  Avatar,
  Typography,
  Divider,
} from 'antd';
import {
  UserOutlined,
  ShoppingCartOutlined,
  DollarOutlined,
  PlusOutlined,
  SearchOutlined,
  ExportOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  WarningOutlined,
} from '@ant-design/icons';

const { Title, Text } = Typography;
const { RangePicker } = DatePicker;
const { TabPane } = Tabs;

// 代理商数据类型
interface Agent {
  id: string;
  name: string;
  email: string;
  phone: string;
  company: string;
  country: string;
  status: 'active' | 'pending' | 'suspended';
  level: 'bronze' | 'silver' | 'gold' | 'platinum';
  commissionRate: number;
  totalOrders: number;
  totalRevenue: number;
  joinedAt: string;
  lastActiveAt: string;
}

// B2B订单类型
interface B2BOrder {
  id: string;
  agentId: string;
  agentName: string;
  customerName: string;
  products: Array<{ name: string; quantity: number; price: number }>;
  totalAmount: number;
  commission: number;
  status: 'pending' | 'confirmed' | 'processing' | 'shipped' | 'delivered' | 'cancelled';
  paymentStatus: 'unpaid' | 'partial' | 'paid';
  createdAt: string;
  updatedAt: string;
}

// 结算记录类型
interface Settlement {
  id: string;
  agentId: string;
  agentName: string;
  period: string;
  totalOrders: number;
  totalRevenue: number;
  totalCommission: number;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  payoutAmount: number;
  payoutMethod: string;
  createdAt: string;
  completedAt?: string;
}

// 模拟数据
const mockAgents: Agent[] = [
  {
    id: 'agent-001',
    name: 'John Smith',
    email: 'john@example.com',
    phone: '+1-555-0101',
    company: 'Smith Outdoor Co.',
    country: 'United States',
    status: 'active',
    level: 'gold',
    commissionRate: 15,
    totalOrders: 156,
    totalRevenue: 45600,
    joinedAt: '2026-01-15',
    lastActiveAt: '2026-09-05',
  },
  {
    id: 'agent-002',
    name: 'Maria Garcia',
    email: 'maria@example.com',
    phone: '+34-555-0202',
    company: 'Garcia Outdoor SL',
    country: 'Spain',
    status: 'active',
    level: 'silver',
    commissionRate: 12,
    totalOrders: 89,
    totalRevenue: 23400,
    joinedAt: '2026-03-20',
    lastActiveAt: '2026-09-04',
  },
  {
    id: 'agent-003',
    name: 'Hans Mueller',
    email: 'hans@example.com',
    phone: '+49-555-0303',
    company: 'Mueller Outdoor GmbH',
    country: 'Germany',
    status: 'pending',
    level: 'bronze',
    commissionRate: 10,
    totalOrders: 12,
    totalRevenue: 3200,
    joinedAt: '2026-08-10',
    lastActiveAt: '2026-09-01',
  },
];

const mockB2BOrders: B2BOrder[] = [
  {
    id: 'B2B-2026-0905-001',
    agentId: 'agent-001',
    agentName: 'John Smith',
    customerName: 'Outdoor Store Inc.',
    products: [
      { name: 'LED Headlamp Pro', quantity: 50, price: 29.99 },
      { name: 'Camping Tent 4P', quantity: 20, price: 89.99 },
    ],
    totalAmount: 3299.3,
    commission: 494.9,
    status: 'confirmed',
    paymentStatus: 'paid',
    createdAt: '2026-09-05 10:30:00',
    updatedAt: '2026-09-05 14:20:00',
  },
  {
    id: 'B2B-2026-0904-002',
    agentId: 'agent-002',
    agentName: 'Maria Garcia',
    customerName: 'Aventura Outdoor ES',
    products: [
      { name: 'Hiking Backpack 40L', quantity: 30, price: 59.99 },
    ],
    totalAmount: 1799.7,
    commission: 215.96,
    status: 'processing',
    paymentStatus: 'partial',
    createdAt: '2026-09-04 09:15:00',
    updatedAt: '2026-09-05 08:00:00',
  },
];

const mockSettlements: Settlement[] = [
  {
    id: 'SET-2026-08',
    agentId: 'agent-001',
    agentName: 'John Smith',
    period: '2026-08',
    totalOrders: 45,
    totalRevenue: 12500,
    totalCommission: 1875,
    status: 'completed',
    payoutAmount: 1875,
    payoutMethod: 'PayPal',
    createdAt: '2026-09-01 00:00:00',
    completedAt: '2026-09-02 10:30:00',
  },
  {
    id: 'SET-2026-08-002',
    agentId: 'agent-002',
    agentName: 'Maria Garcia',
    period: '2026-08',
    totalOrders: 28,
    totalRevenue: 7200,
    totalCommission: 864,
    status: 'processing',
    payoutAmount: 864,
    payoutMethod: 'Bank Transfer',
    createdAt: '2026-09-01 00:00:00',
  },
];

// 状态标签配置
const statusColors: Record<string, string> = {
  active: 'green',
  pending: 'orange',
  suspended: 'red',
  confirmed: 'blue',
  processing: 'cyan',
  shipped: 'geekblue',
  delivered: 'green',
  cancelled: 'red',
  unpaid: 'red',
  partial: 'orange',
  paid: 'green',
  completed: 'green',
  failed: 'red',
};

const levelColors: Record<string, string> = {
  bronze: 'orange',
  silver: 'default',
  gold: 'gold',
  platinum: 'purple',
};

const B2BAgentsPage: React.FC = () => {
  const [agents, setAgents] = useState<Agent[]>(mockAgents);
  const [orders, setOrders] = useState<B2BOrder[]>(mockB2BOrders);
  const [settlements, setSettlements] = useState<Settlement[]>(mockSettlements);
  const [loading, setLoading] = useState(false);
  const [agentModalVisible, setAgentModalVisible] = useState(false);
  const [orderModalVisible, setOrderModalVisible] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [searchText, setSearchText] = useState('');

  // 统计数据
  const stats = {
    totalAgents: agents.filter(a => a.status === 'active').length,
    pendingAgents: agents.filter(a => a.status === 'pending').length,
    totalB2BOrders: orders.length,
    totalB2BRevenue: orders.reduce((sum, o) => sum + o.totalAmount, 0),
    pendingSettlements: settlements.filter(s => s.status === 'pending' || s.status === 'processing').length,
    totalCommission: settlements.reduce((sum, s) => sum + s.totalCommission, 0),
  };

  // 加载数据（实际应从API加载）
  useEffect(() => {
    // 这里可以调用API加载真实数据
    // fetch('/api/v1/p3/b2b/agents').then(...)
  }, []);

  // 代理商表格列
  const agentColumns = [
    {
      title: '代理商',
      dataIndex: 'name',
      key: 'name',
      render: (text: string, record: Agent) => (
        <Space>
          <Avatar icon={<UserOutlined />} />
          <div>
            <div><Text strong>{text}</Text></div>
            <div><Text type="secondary">{record.company}</Text></div>
          </div>
        </Space>
      ),
    },
    {
      title: '国家/地区',
      dataIndex: 'country',
      key: 'country',
    },
    {
      title: '等级',
      dataIndex: 'level',
      key: 'level',
      render: (level: string) => <Tag color={levelColors[level]}>{level.toUpperCase()}</Tag>,
    },
    {
      title: '佣金率',
      dataIndex: 'commissionRate',
      key: 'commissionRate',
      render: (rate: number) => `${rate}%`,
    },
    {
      title: '订单数',
      dataIndex: 'totalOrders',
      key: 'totalOrders',
    },
    {
      title: '总营收',
      dataIndex: 'totalRevenue',
      key: 'totalRevenue',
      render: (revenue: number) => `$${revenue.toLocaleString()}`,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => <Tag color={statusColors[status]}>{status}</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: Agent) => (
        <Space>
          <Button type="link" size="small" onClick={() => handleViewAgent(record)}>查看</Button>
          <Button type="link" size="small" onClick={() => handleEditAgent(record)}>编辑</Button>
        </Space>
      ),
    },
  ];

  // B2B订单表格列
  const orderColumns = [
    {
      title: '订单号',
      dataIndex: 'id',
      key: 'id',
      render: (text: string) => <Text strong>{text}</Text>,
    },
    {
      title: '代理商',
      dataIndex: 'agentName',
      key: 'agentName',
    },
    {
      title: '客户',
      dataIndex: 'customerName',
      key: 'customerName',
    },
    {
      title: '商品数',
      key: 'productCount',
      render: (_: any, record: B2BOrder) => record.products.length,
    },
    {
      title: '总金额',
      dataIndex: 'totalAmount',
      key: 'totalAmount',
      render: (amount: number) => `$${amount.toLocaleString()}`,
    },
    {
      title: '佣金',
      dataIndex: 'commission',
      key: 'commission',
      render: (commission: number) => `$${commission.toFixed(2)}`,
    },
    {
      title: '订单状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => <Tag color={statusColors[status]}>{status}</Tag>,
    },
    {
      title: '支付状态',
      dataIndex: 'paymentStatus',
      key: 'paymentStatus',
      render: (status: string) => <Tag color={statusColors[status]}>{status}</Tag>,
    },
    {
      title: '创建时间',
      dataIndex: 'createdAt',
      key: 'createdAt',
    },
  ];

  // 结算表格列
  const settlementColumns = [
    {
      title: '结算单号',
      dataIndex: 'id',
      key: 'id',
      render: (text: string) => <Text strong>{text}</Text>,
    },
    {
      title: '代理商',
      dataIndex: 'agentName',
      key: 'agentName',
    },
    {
      title: '结算周期',
      dataIndex: 'period',
      key: 'period',
    },
    {
      title: '订单数',
      dataIndex: 'totalOrders',
      key: 'totalOrders',
    },
    {
      title: '总营收',
      dataIndex: 'totalRevenue',
      key: 'totalRevenue',
      render: (revenue: number) => `$${revenue.toLocaleString()}`,
    },
    {
      title: '总佣金',
      dataIndex: 'totalCommission',
      key: 'totalCommission',
      render: (commission: number) => `$${commission.toFixed(2)}`,
    },
    {
      title: '打款金额',
      dataIndex: 'payoutAmount',
      key: 'payoutAmount',
      render: (amount: number) => <Text strong>${amount.toFixed(2)}</Text>,
    },
    {
      title: '打款方式',
      dataIndex: 'payoutMethod',
      key: 'payoutMethod',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => <Tag color={statusColors[status]}>{status}</Tag>,
    },
  ];

  // 处理函数
  const handleViewAgent = (agent: Agent) => {
    setSelectedAgent(agent);
    setAgentModalVisible(true);
  };

  const handleEditAgent = (agent: Agent) => {
    setSelectedAgent(agent);
    message.info(`编辑代理商: ${agent.name}`);
  };

  const handleAddAgent = () => {
    setSelectedAgent(null);
    setAgentModalVisible(true);
  };

  const handleExport = () => {
    message.success('导出成功');
  };

  return (
    <div style={{ padding: '24px' }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: '24px' }}>
        <Title level={3}>B2B 代理商管理</Title>
        <Text type="secondary">管理代理商、B2B订单和佣金结算</Text>
      </div>

      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: '24px' }}>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="活跃代理商"
              value={stats.totalAgents}
              prefix={<UserOutlined />}
              valueStyle={{ color: '#3f8600' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="待审核代理商"
              value={stats.pendingAgents}
              prefix={<ClockCircleOutlined />}
              valueStyle={{ color: '#cf1322' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="B2B订单总数"
              value={stats.totalB2BOrders}
              prefix={<ShoppingCartOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="B2B总营收"
              value={stats.totalB2BRevenue}
              prefix={<DollarOutlined />}
              precision={2}
              valueStyle={{ color: '#3f8600' }}
            />
          </Card>
        </Col>
      </Row>

      {/* 标签页 */}
      <Card>
        <Tabs defaultActiveKey="agents">
          {/* 代理商管理 */}
          <TabPane tab="代理商管理" key="agents">
            <div style={{ marginBottom: '16px', display: 'flex', justifyContent: 'space-between' }}>
              <Space>
                <Input
                  placeholder="搜索代理商名称/公司/邮箱"
                  prefix={<SearchOutlined />}
                  value={searchText}
                  onChange={(e) => setSearchText(e.target.value)}
                  style={{ width: 300 }}
                  allowClear
                />
                <Select
                  placeholder="状态筛选"
                  style={{ width: 120 }}
                  allowClear
                  options={[
                    { value: 'active', label: '活跃' },
                    { value: 'pending', label: '待审核' },
                    { value: 'suspended', label: '已暂停' },
                  ]}
                />
              </Space>
              <Space>
                <Button icon={<ExportOutlined />} onClick={handleExport}>导出</Button>
                <Button type="primary" icon={<PlusOutlined />} onClick={handleAddAgent}>
                  添加代理商
                </Button>
              </Space>
            </div>

            <Table
              columns={agentColumns}
              dataSource={agents}
              rowKey="id"
              loading={loading}
              pagination={{ pageSize: 10, showSizeChanger: true }}
            />
          </TabPane>

          {/* B2B订单 */}
          <TabPane tab="B2B订单" key="orders">
            <div style={{ marginBottom: '16px', display: 'flex', justifyContent: 'space-between' }}>
              <Space>
                <RangePicker />
                <Select
                  placeholder="订单状态"
                  style={{ width: 120 }}
                  allowClear
                  options={[
                    { value: 'pending', label: '待确认' },
                    { value: 'confirmed', label: '已确认' },
                    { value: 'processing', label: '处理中' },
                    { value: 'shipped', label: '已发货' },
                    { value: 'delivered', label: '已送达' },
                    { value: 'cancelled', label: '已取消' },
                  ]}
                />
              </Space>
              <Button icon={<ExportOutlined />} onClick={handleExport}>导出订单</Button>
            </div>

            <Table
              columns={orderColumns}
              dataSource={orders}
              rowKey="id"
              loading={loading}
              pagination={{ pageSize: 10, showSizeChanger: true }}
            />
          </TabPane>

          {/* 佣金结算 */}
          <TabPane tab="佣金结算" key="settlements">
            <div style={{ marginBottom: '16px', display: 'flex', justifyContent: 'space-between' }}>
              <Space>
                <RangePicker />
                <Select
                  placeholder="结算状态"
                  style={{ width: 120 }}
                  allowClear
                  options={[
                    { value: 'pending', label: '待处理' },
                    { value: 'processing', label: '处理中' },
                    { value: 'completed', label: '已完成' },
                    { value: 'failed', label: '失败' },
                  ]}
                />
              </Space>
              <Button type="primary" icon={<DollarOutlined />}>生成结算单</Button>
            </div>

            <Table
              columns={settlementColumns}
              dataSource={settlements}
              rowKey="id"
              loading={loading}
              pagination={{ pageSize: 10, showSizeChanger: true }}
            />
          </TabPane>
        </Tabs>
      </Card>

      {/* 代理商详情弹窗 */}
      <Modal
        title={selectedAgent ? '代理商详情' : '添加代理商'}
        open={agentModalVisible}
        onCancel={() => setAgentModalVisible(false)}
        footer={[
          <Button key="cancel" onClick={() => setAgentModalVisible(false)}>取消</Button>,
          <Button key="submit" type="primary" onClick={() => { message.success('保存成功'); setAgentModalVisible(false); }}>
            保存
          </Button>,
        ]}
        width={600}
      >
        {selectedAgent && (
          <div>
            <Descriptions title="基本信息" column={2} bordered size="small">
              <Descriptions.Item label="代理商ID">{selectedAgent.id}</Descriptions.Item>
              <Descriptions.Item label="姓名">{selectedAgent.name}</Descriptions.Item>
              <Descriptions.Item label="公司">{selectedAgent.company}</Descriptions.Item>
              <Descriptions.Item label="国家">{selectedAgent.country}</Descriptions.Item>
              <Descriptions.Item label="邮箱">{selectedAgent.email}</Descriptions.Item>
              <Descriptions.Item label="电话">{selectedAgent.phone}</Descriptions.Item>
              <Descriptions.Item label="等级">
                <Tag color={levelColors[selectedAgent.level]}>{selectedAgent.level.toUpperCase()}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="佣金率">{selectedAgent.commissionRate}%</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={statusColors[selectedAgent.status]}>{selectedAgent.status}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="加入时间">{selectedAgent.joinedAt}</Descriptions.Item>
            </Descriptions>

            <Divider />

            <Descriptions title="业务数据" column={2} bordered size="small">
              <Descriptions.Item label="总订单数">{selectedAgent.totalOrders}</Descriptions.Item>
              <Descriptions.Item label="总营收">${selectedAgent.totalRevenue.toLocaleString()}</Descriptions.Item>
              <Descriptions.Item label="最后活跃">{selectedAgent.lastActiveAt}</Descriptions.Item>
            </Descriptions>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default B2BAgentsPage;
