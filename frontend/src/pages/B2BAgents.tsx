/**
 * B2B 代理商管理页面（对接真实 API）
 * 支持代理商管理、B2B订单管理、批发价管理
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Table, Button, Modal, Form, Input, Select, Tag, Statistic,
  Row, Col, DatePicker, message, Tabs, Space, Avatar, Typography,
  Divider, Descriptions, InputNumber, Switch, Popconfirm,
} from 'antd';
import {
  UserOutlined, ShoppingCartOutlined, DollarOutlined, PlusOutlined,
  SearchOutlined, ExportOutlined, EditOutlined, KeyOutlined,
  CheckCircleOutlined, StopOutlined, EyeOutlined,
} from '@ant-design/icons';

const { Title, Text } = Typography;
const { RangePicker } = DatePicker;
const { TabPane } = Tabs;

const API_BASE = '/api/v1/admin/b2b';

// ==================== 类型定义 ====================

interface Agent {
  id: string;
  agent_number: string;
  company_name: string;
  contact_name: string;
  email: string;
  phone: string | null;
  country: string | null;
  city: string | null;
  address: string | null;
  tier: 'bronze' | 'silver' | 'gold' | 'platinum';
  status: 'pending' | 'active' | 'suspended' | 'rejected';
  commission_rate: number;
  discount_percent: number;
  credit_limit: number;
  current_balance: number;
  available_credit: number;
  payment_terms_days: number;
  currency: string;
  notes: string | null;
  last_login_at: string | null;
  created_at: string;
  order_count: number;
  total_revenue: number;
}

interface B2BOrder {
  id: string;
  order_number: string;
  agent_id: string;
  agent_company: string;
  agent_email: string;
  status: string;
  payment_status: string;
  subtotal: number;
  discount_amount: number;
  shipping_cost: number;
  total: number;
  currency: string;
  shipping_address: Record<string, any>;
  payment_due_date: string | null;
  tracking_number: string | null;
  tracking_carrier: string | null;
  notes: string | null;
  items: Array<{ id: string; product_id: string; product_name: string; sku: string; quantity: number; unit_price: number; subtotal: number }>;
  created_at: string;
  updated_at: string;
}

interface Price {
  id: string;
  product_id: string;
  product_name: string;
  product_sku: string;
  tier: string | null;
  agent_id: string | null;
  agent_company: string | null;
  wholesale_price: number;
  moq: number;
  currency: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

interface Stats {
  total_agents: number;
  active_agents: number;
  pending_agents: number;
  suspended_agents: number;
  total_orders: number;
  total_revenue: number;
  pending_orders: number;
  total_credit_limit: number;
  total_outstanding_balance: number;
}

// ==================== 常量配置 ====================

const statusColors: Record<string, string> = {
  active: 'green', pending: 'orange', suspended: 'red', rejected: 'default',
  confirmed: 'blue', processing: 'cyan', shipped: 'geekblue',
  delivered: 'green', cancelled: 'red',
  unpaid: 'red', partial: 'orange', paid: 'green', overdue: 'red',
};

const levelColors: Record<string, string> = {
  bronze: 'orange', silver: 'default', gold: 'gold', platinum: 'purple',
};

const tierOptions = [
  { value: 'bronze', label: 'Bronze' },
  { value: 'silver', label: 'Silver' },
  { value: 'gold', label: 'Gold' },
  { value: 'platinum', label: 'Platinum' },
];

const statusOptions = [
  { value: 'active', label: '活跃' },
  { value: 'pending', label: '待审核' },
  { value: 'suspended', label: '已暂停' },
  { value: 'rejected', label: '已拒绝' },
];

const orderStatusOptions = [
  { value: 'pending', label: '待确认' },
  { value: 'confirmed', label: '已确认' },
  { value: 'processing', label: '处理中' },
  { value: 'shipped', label: '已发货' },
  { value: 'delivered', label: '已送达' },
  { value: 'cancelled', label: '已取消' },
];

// ==================== API 辅助函数 ====================

async function apiFetch<T = any>(url: string, options?: RequestInit): Promise<T | null> {
  try {
    const token = localStorage.getItem('admin_token')
    const headers: Record<string, string> = { 'Content-Type': 'application/json', ...(options?.headers as Record<string, string> || {}) }
    if (token) headers['Authorization'] = `Bearer ${token}`
    const resp = await fetch(`${API_BASE}${url}`, {
      ...options,
      headers,
    });
    if (resp.ok) return resp.json();
    const err = await resp.json().catch(() => ({}));
    message.error(`API错误(${resp.status}): ${err.detail || resp.statusText}`);
    return null;
  } catch (e: any) {
    message.error(`网络错误: ${e.message}`);
    return null;
  }
}

// ==================== 主组件 ====================

const B2BAgentsPage: React.FC = () => {
  const [stats, setStats] = useState<Stats | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [orders, setOrders] = useState<B2BOrder[]>([]);
  const [prices, setPrices] = useState<Price[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('agents');

  // 代理商筛选
  const [agentSearch, setAgentSearch] = useState('');
  const [agentStatusFilter, setAgentStatusFilter] = useState<string | undefined>();
  const [agentTierFilter, setAgentTierFilter] = useState<string | undefined>();
  const [agentPage, setAgentPage] = useState(1);
  const [agentTotal, setAgentTotal] = useState(0);

  // 订单筛选
  const [orderStatusFilter, setOrderStatusFilter] = useState<string | undefined>();
  const [orderPage, setOrderPage] = useState(1);
  const [orderTotal, setOrderTotal] = useState(0);

  // 定价筛选
  const [priceTierFilter, setPriceTierFilter] = useState<string | undefined>();
  const [pricePage, setPricePage] = useState(1);
  const [priceTotal, setPriceTotal] = useState(0);

  // 弹窗
  const [agentModalOpen, setAgentModalOpen] = useState(false);
  const [editingAgent, setEditingAgent] = useState<Agent | null>(null);
  const [viewingAgent, setViewingAgent] = useState<Agent | null>(null);
  const [viewAgentModalOpen, setViewAgentModalOpen] = useState(false);
  const [passwordModalOpen, setPasswordModalOpen] = useState(false);
  const [passwordAgent, setPasswordAgent] = useState<Agent | null>(null);
  const [orderModalOpen, setOrderModalOpen] = useState(false);
  const [viewingOrder, setViewingOrder] = useState<B2BOrder | null>(null);
  const [priceModalOpen, setPriceModalOpen] = useState(false);
  const [editingPrice, setEditingPrice] = useState<Price | null>(null);

  const [agentForm] = Form.useForm();
  const [passwordForm] = Form.useForm();
  const [priceForm] = Form.useForm();
  const [orderStatusForm] = Form.useForm();

  // ==================== 数据加载 ====================

  const loadStats = useCallback(async () => {
    const data = await apiFetch<Stats>('/stats');
    if (data) setStats(data);
  }, []);

  const loadAgents = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams({ page: agentPage.toString(), page_size: '10' });
    if (agentSearch) params.append('search', agentSearch);
    if (agentStatusFilter) params.append('status', agentStatusFilter);
    if (agentTierFilter) params.append('tier', agentTierFilter);
    const data = await apiFetch<{ items: Agent[]; total: number }>(`/agents?${params}`);
    if (data) { setAgents(data.items); setAgentTotal(data.total); }
    setLoading(false);
  }, [agentPage, agentSearch, agentStatusFilter, agentTierFilter]);

  const loadOrders = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams({ page: orderPage.toString(), page_size: '10' });
    if (orderStatusFilter) params.append('status', orderStatusFilter);
    const data = await apiFetch<{ items: B2BOrder[]; total: number }>(`/orders?${params}`);
    if (data) { setOrders(data.items); setOrderTotal(data.total); }
    setLoading(false);
  }, [orderPage, orderStatusFilter]);

  const loadPrices = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams({ page: pricePage.toString(), page_size: '20' });
    if (priceTierFilter) params.append('tier', priceTierFilter);
    const data = await apiFetch<{ items: Price[]; total: number }>(`/prices?${params}`);
    if (data) { setPrices(data.items); setPriceTotal(data.total); }
    setLoading(false);
  }, [pricePage, priceTierFilter]);

  useEffect(() => { loadStats(); }, [loadStats]);
  useEffect(() => { if (activeTab === 'agents') loadAgents(); }, [activeTab, loadAgents]);
  useEffect(() => { if (activeTab === 'orders') loadOrders(); }, [activeTab, loadOrders]);
  useEffect(() => { if (activeTab === 'prices') loadPrices(); }, [activeTab, loadPrices]);

  // ==================== 代理商操作 ====================

  const handleAddAgent = () => {
    setEditingAgent(null);
    agentForm.resetFields();
    agentForm.setFieldsValue({ tier: 'bronze', status: 'active', commission_rate: 5, credit_limit: 0, payment_terms_days: 30 });
    setAgentModalOpen(true);
  };

  const handleEditAgent = (agent: Agent) => {
    setEditingAgent(agent);
    agentForm.setFieldsValue({
      company_name: agent.company_name, contact_name: agent.contact_name,
      email: agent.email, phone: agent.phone, country: agent.country,
      city: agent.city, address: agent.address, tier: agent.tier,
      status: agent.status, commission_rate: agent.commission_rate,
      discount_percent: agent.discount_percent, credit_limit: agent.credit_limit,
      payment_terms_days: agent.payment_terms_days, notes: agent.notes,
    });
    setAgentModalOpen(true);
  };

  const handleSaveAgent = async () => {
    try {
      const values = await agentForm.validateFields();
      if (editingAgent) {
        const ok = await apiFetch(`/agents/${editingAgent.id}`, {
          method: 'PUT', body: JSON.stringify(values),
        });
        if (ok) { message.success('代理商已更新'); setAgentModalOpen(false); loadAgents(); loadStats(); }
      } else {
        const ok = await apiFetch('/agents', { method: 'POST', body: JSON.stringify(values) });
        if (ok) { message.success('代理商已创建'); setAgentModalOpen(false); loadAgents(); loadStats(); }
      }
    } catch { /* 表单校验失败 */ }
  };

  const handleChangeStatus = async (agent: Agent, newStatus: string) => {
    const ok = await apiFetch(`/agents/${agent.id}/status`, {
      method: 'PATCH', body: JSON.stringify({ status: newStatus }),
    });
    if (ok) { message.success(`状态已更新为 ${newStatus}`); loadAgents(); loadStats(); }
  };

  const handleResetPassword = async () => {
    try {
      const values = await passwordForm.validateFields();
      if (!passwordAgent) return;
      const ok = await apiFetch(`/agents/${passwordAgent.id}/reset-password`, {
        method: 'POST', body: JSON.stringify({ new_password: values.new_password }),
      });
      if (ok) { message.success('密码已重置'); setPasswordModalOpen(false); passwordForm.resetFields(); }
    } catch { /* 校验失败 */ }
  };

  // ==================== 订单操作 ====================

  const handleViewOrder = (order: B2BOrder) => {
    setViewingOrder(order);
    orderStatusForm.setFieldsValue({ status: order.status, tracking_number: order.tracking_number, tracking_carrier: order.tracking_carrier });
    setOrderModalOpen(true);
  };

  const handleUpdateOrderStatus = async () => {
    try {
      const values = await orderStatusForm.validateFields();
      if (!viewingOrder) return;
      const ok = await apiFetch(`/orders/${viewingOrder.id}/status`, {
        method: 'PATCH', body: JSON.stringify(values),
      });
      if (ok) { message.success('订单状态已更新'); setOrderModalOpen(false); loadOrders(); loadStats(); }
    } catch { /* 校验失败 */ }
  };

  // ==================== 定价操作 ====================

  const handleAddPrice = () => {
    setEditingPrice(null);
    priceForm.resetFields();
    priceForm.setFieldsValue({ tier: 'bronze', moq: 10, currency: 'USD', is_active: true });
    setPriceModalOpen(true);
  };

  const handleEditPrice = (price: Price) => {
    setEditingPrice(price);
    priceForm.setFieldsValue({
      product_id: price.product_id, tier: price.tier,
      wholesale_price: price.wholesale_price, moq: price.moq,
      currency: price.currency, is_active: price.is_active,
    });
    setPriceModalOpen(true);
  };

  const handleSavePrice = async () => {
    try {
      const values = await priceForm.validateFields();
      if (editingPrice) {
        const ok = await apiFetch(`/prices/${editingPrice.id}`, {
          method: 'PUT', body: JSON.stringify(values),
        });
        if (ok) { message.success('定价已更新'); setPriceModalOpen(false); loadPrices(); }
      } else {
        const ok = await apiFetch('/prices', { method: 'POST', body: JSON.stringify(values) });
        if (ok) { message.success('定价已创建'); setPriceModalOpen(false); loadPrices(); }
      }
    } catch { /* 校验失败 */ }
  };

  // ==================== 表格列定义 ====================

  const agentColumns = [
    {
      title: '代理商', dataIndex: 'company_name', key: 'company_name', width: 260,
      render: (_: any, r: Agent) => (
        <Space>
          <Avatar icon={<UserOutlined />} />
          <div>
            <div><Text strong>{r.company_name}</Text> <Text type="secondary" style={{ fontSize: 12 }}>{r.agent_number}</Text></div>
            <div><Text type="secondary">{r.contact_name} · {r.email}</Text></div>
          </div>
        </Space>
      ),
    },
    { title: '国家', dataIndex: 'country', key: 'country', width: 120 },
    {
      title: '等级', dataIndex: 'tier', key: 'tier', width: 100,
      render: (t: string) => <Tag color={levelColors[t]}>{t.toUpperCase()}</Tag>,
    },
    { title: '佣金率', dataIndex: 'commission_rate', key: 'commission_rate', width: 80, render: (v: number) => `${v}%` },
    { title: '订单数', dataIndex: 'order_count', key: 'order_count', width: 80 },
    { title: '总营收', dataIndex: 'total_revenue', key: 'total_revenue', width: 110, render: (v: number) => `$${Number(v).toLocaleString()}` },
    { title: '信用额度', dataIndex: 'credit_limit', key: 'credit_limit', width: 110, render: (v: number) => `$${Number(v).toLocaleString()}` },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 100,
      render: (s: string) => <Tag color={statusColors[s]}>{s}</Tag>,
    },
    {
      title: '操作', key: 'action', width: 200,
      render: (_: any, r: Agent) => (
        <Space size="small">
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => { setViewingAgent(r); setViewAgentModalOpen(true); }}>详情</Button>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEditAgent(r)}>编辑</Button>
          <Button type="link" size="small" icon={<KeyOutlined />} onClick={() => { setPasswordAgent(r); setPasswordModalOpen(true); }}>密码</Button>
          {r.status === 'active' ? (
            <Popconfirm title="确定暂停该代理商？" onConfirm={() => handleChangeStatus(r, 'suspended')}>
              <Button type="link" size="small" danger icon={<StopOutlined />}>暂停</Button>
            </Popconfirm>
          ) : r.status === 'suspended' ? (
            <Popconfirm title="确定启用该代理商？" onConfirm={() => handleChangeStatus(r, 'active')}>
              <Button type="link" size="small" icon={<CheckCircleOutlined />}>启用</Button>
            </Popconfirm>
          ) : r.status === 'pending' ? (
            <Popconfirm title="审核通过该代理商？" onConfirm={() => handleChangeStatus(r, 'active')}>
              <Button type="primary" size="small" icon={<CheckCircleOutlined />}>通过</Button>
            </Popconfirm>
          ) : null}
        </Space>
      ),
    },
  ];

  const orderColumns = [
    { title: '订单号', dataIndex: 'order_number', key: 'order_number', render: (t: string) => <Text strong>{t}</Text> },
    { title: '代理商', dataIndex: 'agent_company', key: 'agent_company' },
    { title: '商品数', key: 'items', render: (_: any, r: B2BOrder) => r.items?.length || 0 },
    { title: '总金额', dataIndex: 'total', key: 'total', render: (v: number) => `$${Number(v).toLocaleString()}` },
    { title: '订单状态', dataIndex: 'status', key: 'status', render: (s: string) => <Tag color={statusColors[s]}>{s}</Tag> },
    { title: '支付状态', dataIndex: 'payment_status', key: 'payment_status', render: (s: string) => <Tag color={statusColors[s]}>{s}</Tag> },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', render: (t: string) => new Date(t).toLocaleString('zh-CN') },
    {
      title: '操作', key: 'action',
      render: (_: any, r: B2BOrder) => (
        <Button type="link" size="small" onClick={() => handleViewOrder(r)}>管理</Button>
      ),
    },
  ];

  const priceColumns = [
    { title: 'SKU', dataIndex: 'product_sku', key: 'product_sku', width: 180 },
    { title: '商品名称', dataIndex: 'product_name', key: 'product_name', ellipsis: true },
    {
      title: '适用对象', key: 'target', width: 140,
      render: (_: any, r: Price) => r.tier ? <Tag color={levelColors[r.tier]}>{r.tier.toUpperCase()}</Tag> : <Tag color="blue">专属</Tag>,
    },
    { title: '代理商', dataIndex: 'agent_company', key: 'agent_company', width: 160, render: (v: string) => v || '-' },
    { title: '批发价', dataIndex: 'wholesale_price', key: 'wholesale_price', width: 100, render: (v: number) => `$${v}` },
    { title: 'MOQ', dataIndex: 'moq', key: 'moq', width: 80 },
    { title: '币种', dataIndex: 'currency', key: 'currency', width: 70 },
    {
      title: '状态', dataIndex: 'is_active', key: 'is_active', width: 80,
      render: (v: boolean) => v ? <Tag color="green">启用</Tag> : <Tag color="default">停用</Tag>,
    },
    {
      title: '操作', key: 'action', width: 100,
      render: (_: any, r: Price) => (
        <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEditPrice(r)}>编辑</Button>
      ),
    },
  ];

  // ==================== 渲染 ====================

  return (
    <div style={{ padding: '24px' }}>
      <div style={{ marginBottom: '24px' }}>
        <Title level={3}>B2B 代理商管理</Title>
        <Text type="secondary">管理代理商账号、B2B 订单和批发定价</Text>
      </div>

      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: '24px' }}>
        <Col xs={24} sm={12} md={6}>
          <Card><Statistic title="活跃代理商" value={stats?.active_agents ?? 0} prefix={<UserOutlined />} valueStyle={{ color: '#3f8600' }} /></Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card><Statistic title="待审核" value={stats?.pending_agents ?? 0} prefix={<UserOutlined />} valueStyle={{ color: '#d48806' }} /></Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card><Statistic title="B2B 订单总数" value={stats?.total_orders ?? 0} prefix={<ShoppingCartOutlined />} /></Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card><Statistic title="B2B 总营收" value={stats?.total_revenue ?? 0} prefix={<DollarOutlined />} precision={2} valueStyle={{ color: '#3f8600' }} /></Card>
        </Col>
      </Row>

      <Card>
        <Tabs activeKey={activeTab} onChange={setActiveTab}>
          {/* 代理商管理 */}
          <TabPane tab="代理商管理" key="agents">
            <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
              <Space>
                <Input placeholder="搜索公司/联系人/邮箱/编号" prefix={<SearchOutlined />} value={agentSearch}
                  onChange={(e) => { setAgentSearch(e.target.value); setAgentPage(1); }} style={{ width: 280 }} allowClear />
                <Select placeholder="状态" allowClear style={{ width: 110 }} value={agentStatusFilter}
                  onChange={(v) => { setAgentStatusFilter(v); setAgentPage(1); }} options={statusOptions} />
                <Select placeholder="等级" allowClear style={{ width: 110 }} value={agentTierFilter}
                  onChange={(v) => { setAgentTierFilter(v); setAgentPage(1); }} options={tierOptions} />
              </Space>
              <Button type="primary" icon={<PlusOutlined />} onClick={handleAddAgent}>添加代理商</Button>
            </div>
            <Table columns={agentColumns} dataSource={agents} rowKey="id" loading={loading}
              scroll={{ x: 'max-content' }}
              pagination={{ current: agentPage, pageSize: 10, total: agentTotal, showSizeChanger: false,
                onChange: (p) => setAgentPage(p) }} />
          </TabPane>

          {/* B2B 订单 */}
          <TabPane tab="B2B 订单" key="orders">
            <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
              <Space>
                <RangePicker />
                <Select placeholder="订单状态" allowClear style={{ width: 120 }} value={orderStatusFilter}
                  onChange={(v) => { setOrderStatusFilter(v); setOrderPage(1); }} options={orderStatusOptions} />
              </Space>
              <Button icon={<ExportOutlined />}>导出订单</Button>
            </div>
            <Table columns={orderColumns} dataSource={orders} rowKey="id" loading={loading} scroll={{ x: 'max-content' }}
              pagination={{ current: orderPage, pageSize: 10, total: orderTotal, showSizeChanger: false,
                onChange: (p) => setOrderPage(p) }} />
          </TabPane>

          {/* 批发价管理 */}
          <TabPane tab="批发价管理" key="prices">
            <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
              <Space>
                <Select placeholder="按等级筛选" allowClear style={{ width: 140 }} value={priceTierFilter}
                  onChange={(v) => { setPriceTierFilter(v); setPricePage(1); }} options={tierOptions} />
              </Space>
              <Button type="primary" icon={<PlusOutlined />} onClick={handleAddPrice}>添加定价</Button>
            </div>
            <Table columns={priceColumns} dataSource={prices} rowKey="id" loading={loading} scroll={{ x: 'max-content' }}
              pagination={{ current: pricePage, pageSize: 20, total: priceTotal, showSizeChanger: false,
                onChange: (p) => setPricePage(p) }} />
          </TabPane>
        </Tabs>
      </Card>

      {/* 代理商编辑弹窗 */}
      <Modal title={editingAgent ? '编辑代理商' : '添加代理商'} open={agentModalOpen}
        onCancel={() => setAgentModalOpen(false)} onOk={handleSaveAgent} width={700} destroyOnClose>
        <Form form={agentForm} layout="vertical">
          <Row gutter={16}>
            <Col span={12}><Form.Item name="company_name" label="公司名称" rules={[{ required: true }]}><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="contact_name" label="联系人" rules={[{ required: true }]}><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="email" label="邮箱" rules={[{ required: true, type: 'email' }]}><Input disabled={!!editingAgent} /></Form.Item></Col>
            <Col span={12}><Form.Item name="phone" label="电话"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="country" label="国家"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="city" label="城市"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="tier" label="等级" rules={[{ required: true }]}><Select options={tierOptions} /></Form.Item></Col>
            <Col span={24}><Form.Item name="address" label="地址"><Input /></Form.Item></Col>
            {!editingAgent && <Col span={12}><Form.Item name="password" label="初始密码" rules={[{ required: true, min: 8 }]}><Input.Password /></Form.Item></Col>}
            <Col span={12}><Form.Item name="status" label="状态"><Select options={statusOptions} /></Form.Item></Col>
            <Col span={8}><Form.Item name="commission_rate" label="佣金率(%)"><InputNumber min={0} max={100} style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={8}><Form.Item name="discount_percent" label="折扣(%)"><InputNumber min={0} max={100} style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={8}><Form.Item name="credit_limit" label="信用额度"><InputNumber min={0} style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={12}><Form.Item name="payment_terms_days" label="账期(天)"><InputNumber min={0} max={365} style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={24}><Form.Item name="notes" label="备注"><Input.TextArea rows={2} /></Form.Item></Col>
          </Row>
        </Form>
      </Modal>

      {/* 代理商详情弹窗 */}
      <Modal title="代理商详情" open={viewAgentModalOpen} onCancel={() => setViewAgentModalOpen(false)}
        footer={<Button onClick={() => setViewAgentModalOpen(false)}>关闭</Button>} width={700}>
        {viewingAgent && (
          <>
            <Descriptions title="基本信息" column={2} bordered size="small">
              <Descriptions.Item label="代理商编号">{viewingAgent.agent_number}</Descriptions.Item>
              <Descriptions.Item label="状态"><Tag color={statusColors[viewingAgent.status]}>{viewingAgent.status}</Tag></Descriptions.Item>
              <Descriptions.Item label="公司">{viewingAgent.company_name}</Descriptions.Item>
              <Descriptions.Item label="联系人">{viewingAgent.contact_name}</Descriptions.Item>
              <Descriptions.Item label="邮箱">{viewingAgent.email}</Descriptions.Item>
              <Descriptions.Item label="电话">{viewingAgent.phone || '-'}</Descriptions.Item>
              <Descriptions.Item label="国家/城市">{viewingAgent.country} {viewingAgent.city}</Descriptions.Item>
              <Descriptions.Item label="等级"><Tag color={levelColors[viewingAgent.tier]}>{viewingAgent.tier.toUpperCase()}</Tag></Descriptions.Item>
              <Descriptions.Item label="佣金率">{viewingAgent.commission_rate}%</Descriptions.Item>
              <Descriptions.Item label="折扣">{viewingAgent.discount_percent}%</Descriptions.Item>
            </Descriptions>
            <Divider />
            <Descriptions title="业务数据" column={2} bordered size="small">
              <Descriptions.Item label="信用额度">${Number(viewingAgent.credit_limit).toLocaleString()}</Descriptions.Item>
              <Descriptions.Item label="已用额度">${Number(viewingAgent.current_balance).toLocaleString()}</Descriptions.Item>
              <Descriptions.Item label="可用额度">${Number(viewingAgent.available_credit).toLocaleString()}</Descriptions.Item>
              <Descriptions.Item label="账期">{viewingAgent.payment_terms_days} 天</Descriptions.Item>
              <Descriptions.Item label="订单数">{viewingAgent.order_count}</Descriptions.Item>
              <Descriptions.Item label="总营收">${Number(viewingAgent.total_revenue).toLocaleString()}</Descriptions.Item>
              <Descriptions.Item label="注册时间">{new Date(viewingAgent.created_at).toLocaleString('zh-CN')}</Descriptions.Item>
              <Descriptions.Item label="最后登录">{viewingAgent.last_login_at ? new Date(viewingAgent.last_login_at).toLocaleString('zh-CN') : '从未登录'}</Descriptions.Item>
            </Descriptions>
          </>
        )}
      </Modal>

      {/* 重置密码弹窗 */}
      <Modal title="重置密码" open={passwordModalOpen} onCancel={() => setPasswordModalOpen(false)}
        onOk={handleResetPassword} destroyOnClose>
        <Text type="secondary">为代理商 <strong>{passwordAgent?.company_name}</strong> 重置登录密码</Text>
        <Form form={passwordForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="new_password" label="新密码" rules={[{ required: true, min: 8, message: '密码至少8位' }]}>
            <Input.Password placeholder="至少8位" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 订单管理弹窗 */}
      <Modal title="订单管理" open={orderModalOpen} onCancel={() => setOrderModalOpen(false)}
        onOk={handleUpdateOrderStatus} width={700} destroyOnClose>
        {viewingOrder && (
          <>
            <Descriptions column={2} bordered size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="订单号">{viewingOrder.order_number}</Descriptions.Item>
              <Descriptions.Item label="代理商">{viewingOrder.agent_company}</Descriptions.Item>
              <Descriptions.Item label="总金额">${Number(viewingOrder.total).toLocaleString()}</Descriptions.Item>
              <Descriptions.Item label="支付状态"><Tag color={statusColors[viewingOrder.payment_status]}>{viewingOrder.payment_status}</Tag></Descriptions.Item>
              <Descriptions.Item label="创建时间">{new Date(viewingOrder.created_at).toLocaleString('zh-CN')}</Descriptions.Item>
              <Descriptions.Item label="付款截止">{viewingOrder.payment_due_date || '-'}</Descriptions.Item>
            </Descriptions>
            <Divider orientation="left">商品明细</Divider>
            <Table dataSource={viewingOrder.items} rowKey="id" size="small" pagination={false}
              columns={[
                { title: '商品', dataIndex: 'product_name', key: 'product_name' },
                { title: 'SKU', dataIndex: 'sku', key: 'sku' },
                { title: '数量', dataIndex: 'quantity', key: 'quantity', width: 80 },
                { title: '单价', dataIndex: 'unit_price', key: 'unit_price', width: 100, render: (v: number) => `$${v}` },
                { title: '小计', dataIndex: 'subtotal', key: 'subtotal', width: 100, render: (v: number) => `$${v}` },
              ]} />
            <Divider orientation="left">更新状态</Divider>
            <Form form={orderStatusForm} layout="vertical">
              <Row gutter={16}>
                <Col span={12}><Form.Item name="status" label="订单状态" rules={[{ required: true }]}><Select options={orderStatusOptions} /></Form.Item></Col>
                <Col span={12}><Form.Item name="tracking_carrier" label="物流公司"><Input placeholder="如 DHL / FedEx" /></Form.Item></Col>
                <Col span={24}><Form.Item name="tracking_number" label="物流单号"><Input placeholder="发货后填写" /></Form.Item></Col>
              </Row>
            </Form>
          </>
        )}
      </Modal>

      {/* 定价编辑弹窗 */}
      <Modal title={editingPrice ? '编辑批发价' : '添加批发价'} open={priceModalOpen}
        onCancel={() => setPriceModalOpen(false)} onOk={handleSavePrice} width={600} destroyOnClose>
        <Form form={priceForm} layout="vertical">
          <Form.Item name="product_id" label="商品 ID" rules={[{ required: true }]}>
            <Input placeholder="商品 UUID" disabled={!!editingPrice} />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}><Form.Item name="tier" label="适用等级"><Select allowClear options={tierOptions} placeholder="留空则为代理商专属" /></Form.Item></Col>
            <Col span={12}><Form.Item name="moq" label="MOQ(起订量)" rules={[{ required: true }]}><InputNumber min={1} style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={12}><Form.Item name="wholesale_price" label="批发价" rules={[{ required: true }]}><InputNumber min={0.01} step={0.01} style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={12}><Form.Item name="currency" label="币种"><Input /></Form.Item></Col>
            <Col span={24}><Form.Item name="is_active" label="启用" valuePropName="checked"><Switch /></Form.Item></Col>
          </Row>
          <Text type="secondary">提示：tier 和 agent_id 二选一。设置 tier 为等级统一定价，留空 tier 并指定 agent_id 为代理商专属定价。</Text>
        </Form>
      </Modal>
    </div>
  );
};

export default B2BAgentsPage;
