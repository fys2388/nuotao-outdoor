import { useState, useEffect } from 'react';
import { api } from '../api/client';
import {
  Table,
  Button,
  Modal,
  Tag,
  Space,
  message,
  Card,
  Row,
  Col,
  Statistic,
  Descriptions,
  Badge,
  Timeline,
  Select,
  Input,
} from 'antd';
import {
  EyeOutlined,
  SearchOutlined,
  DownloadOutlined,
  ReloadOutlined,
  TruckOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';

// 订单类型定义
interface Order {
  id: number;
  order_number: string;
  customer_name: string;
  customer_email: string;
  total: number;
  status: 'pending' | 'processing' | 'shipped' | 'completed' | 'cancelled' | 'refunded';
  payment_method: string;
  shipping_address: string;
  items: OrderItem[];
  created_at: string;
  updated_at: string;
  woocommerce_id?: number;
}

interface OrderItem {
  product_name: string;
  quantity: number;
  price: number;
  subtotal: number;
}

const { Option } = Select;

// 模拟数据
const mockOrders: Order[] = [
  {
    id: 1,
    order_number: 'NT-2024-0001',
    customer_name: '张三',
    customer_email: 'zhangsan@example.com',
    total: 728.00,
    status: 'completed',
    payment_method: 'PayPal',
    shipping_address: '广东省深圳市南山区科技园路1号',
    items: [
      { product_name: '户外露营帐篷 4人', quantity: 1, price: 599.00, subtotal: 599.00 },
      { product_name: '便携折叠椅', quantity: 1, price: 129.00, subtotal: 129.00 },
    ],
    created_at: '2024-03-15 10:30:00',
    updated_at: '2024-03-18 14:20:00',
    woocommerce_id: 201,
  },
  {
    id: 2,
    order_number: 'NT-2024-0002',
    customer_name: '李四',
    customer_email: 'lisi@example.com',
    total: 89.00,
    status: 'shipped',
    payment_method: 'Stripe',
    shipping_address: '北京市朝阳区建国路88号',
    items: [
      { product_name: '户外保温壶 1L', quantity: 1, price: 89.00, subtotal: 89.00 },
    ],
    created_at: '2024-03-20 09:15:00',
    updated_at: '2024-03-21 16:45:00',
    woocommerce_id: 202,
  },
  {
    id: 3,
    order_number: 'NT-2024-0003',
    customer_name: '王五',
    customer_email: 'wangwu@example.com',
    total: 1198.00,
    status: 'processing',
    payment_method: 'PayPal',
    shipping_address: '上海市浦东新区陆家嘴环路1000号',
    items: [
      { product_name: '户外露营帐篷 4人', quantity: 2, price: 599.00, subtotal: 1198.00 },
    ],
    created_at: '2024-03-22 14:00:00',
    updated_at: '2024-03-22 14:00:00',
    woocommerce_id: 203,
  },
  {
    id: 4,
    order_number: 'NT-2024-0004',
    customer_name: '赵六',
    customer_email: 'zhaoliu@example.com',
    total: 59.00,
    status: 'pending',
    payment_method: 'Stripe',
    shipping_address: '浙江省杭州市西湖区文三路90号',
    items: [
      { product_name: 'LED头灯', quantity: 1, price: 59.00, subtotal: 59.00 },
    ],
    created_at: '2024-03-23 11:30:00',
    updated_at: '2024-03-23 11:30:00',
    woocommerce_id: 204,
  },
  {
    id: 5,
    order_number: 'NT-2024-0005',
    customer_name: '孙七',
    customer_email: 'sunqi@example.com',
    total: 399.00,
    status: 'cancelled',
    payment_method: 'PayPal',
    shipping_address: '四川省成都市武侯区天府大道100号',
    items: [
      { product_name: '登山背包 50L', quantity: 1, price: 399.00, subtotal: 399.00 },
    ],
    created_at: '2024-03-10 16:20:00',
    updated_at: '2024-03-11 09:00:00',
    woocommerce_id: 205,
  },
];

// 状态配置
const statusConfig: Record<string, { color: string; text: string; icon: React.ReactNode }> = {
  pending: { color: 'orange', text: '待付款', icon: <ClockCircleOutlined /> },
  processing: { color: 'blue', text: '处理中', icon: <ClockCircleOutlined /> },
  shipped: { color: 'cyan', text: '已发货', icon: <TruckOutlined /> },
  completed: { color: 'green', text: '已完成', icon: <CheckCircleOutlined /> },
  cancelled: { color: 'red', text: '已取消', icon: <CloseCircleOutlined /> },
  refunded: { color: 'purple', text: '已退款', icon: <CloseCircleOutlined /> },
};

const OrdersPage = () => {
  const [orders, setOrders] = useState<Order[]>(mockOrders);
  const [loading, setLoading] = useState(false);
  const [detailVisible, setDetailVisible] = useState(false);
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);
  const [searchText, setSearchText] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');

  // 加载订单
  const loadOrders = async () => {
    setLoading(true);
    setTimeout(() => {
      setOrders(mockOrders);
      setLoading(false);
    }, 500);
  };

  useEffect(() => {
    loadOrders();
  }, []);

  // 查看订单详情
  const viewDetail = (order: Order) => {
    setSelectedOrder(order);
    setDetailVisible(true);
  };

  // 更新订单状态
  const updateStatus = (orderId: number, newStatus: Order['status']) => {
    setOrders(
      orders.map((o) =>
        o.id === orderId
          ? { ...o, status: newStatus, updated_at: new Date().toLocaleString('zh-CN') }
          : o
      )
    );
    message.success(`订单状态已更新为: ${statusConfig[newStatus].text}`);
  };

  // 导出订单
  const handleExport = () => {
    const csvContent = [
      ['订单号', '客户', '邮箱', '金额', '状态', '支付方式', '创建时间'].join(','),
      ...orders.map((o) =>
        [o.order_number, o.customer_name, o.customer_email, o.total, o.status, o.payment_method, o.created_at].join(',')
      ),
    ].join('\n');

    const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `orders_${new Date().toISOString().split('T')[0]}.csv`;
    link.click();
    message.success('订单导出成功');
  };

  // 表格列
  const columns: ColumnsType<Order> = [
    {
      title: '订单号',
      dataIndex: 'order_number',
      key: 'order_number',
      render: (text: string) => <span style={{ fontWeight: 500, color: '#1890ff' }}>{text}</span>,
    },
    {
      title: '客户',
      key: 'customer',
      render: (_, record) => (
        <div>
          <div style={{ fontWeight: 500 }}>{record.customer_name}</div>
          <div style={{ color: '#999', fontSize: 12 }}>{record.customer_email}</div>
        </div>
      ),
    },
    {
      title: '商品数量',
      key: 'items_count',
      width: 100,
      render: (_, record) => <span>{record.items.reduce((sum, item) => sum + item.quantity, 0)} 件</span>,
    },
    {
      title: '订单金额',
      dataIndex: 'total',
      key: 'total',
      width: 120,
      render: (total: number) => <span style={{ color: '#f5222d', fontWeight: 600, fontSize: 16 }}>¥{total.toFixed(2)}</span>,
      sorter: (a, b) => a.total - b.total,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: string) => {
        const config = statusConfig[status] || { color: 'default', text: status, icon: null };
        return (
          <Tag color={config.color} icon={config.icon}>
            {config.text}
          </Tag>
        );
      },
    },
    {
      title: '支付方式',
      dataIndex: 'payment_method',
      key: 'payment_method',
      width: 100,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      sorter: (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_, record) => (
        <Space size="small">
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => viewDetail(record)}>
            详情
          </Button>
          {record.status === 'pending' && (
            <Button type="link" size="small" onClick={() => updateStatus(record.id, 'processing')}>
              确认
            </Button>
          )}
          {record.status === 'processing' && (
            <Button type="link" size="small" onClick={() => updateStatus(record.id, 'shipped')}>
              发货
            </Button>
          )}
          {record.status === 'shipped' && (
            <Button type="link" size="small" onClick={() => updateStatus(record.id, 'completed')}>
              完成
            </Button>
          )}
        </Space>
      ),
    },
  ];

  // 过滤订单
  const filteredOrders = orders.filter((o) => {
    const matchSearch =
      !searchText ||
      o.order_number.toLowerCase().includes(searchText.toLowerCase()) ||
      o.customer_name.toLowerCase().includes(searchText.toLowerCase()) ||
      o.customer_email.toLowerCase().includes(searchText.toLowerCase());
    const matchStatus = statusFilter === 'all' || o.status === statusFilter;
    return matchSearch && matchStatus;
  });

  // 统计数据
  const stats = {
    total: orders.length,
    pending: orders.filter((o) => o.status === 'pending').length,
    processing: orders.filter((o) => o.status === 'processing').length,
    shipped: orders.filter((o) => o.status === 'shipped').length,
    completed: orders.filter((o) => o.status === 'completed').length,
    totalRevenue: orders.filter((o) => o.status === 'completed').reduce((sum, o) => sum + o.total, 0),
  };

  return (
    <div style={{ padding: 24 }}>
      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={4}>
          <Card>
            <Statistic title="订单总数" value={stats.total} suffix="单" />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic title="待付款" value={stats.pending} suffix="单" valueStyle={{ color: '#fa8c16' }} />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic title="处理中" value={stats.processing} suffix="单" valueStyle={{ color: '#1890ff' }} />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic title="已发货" value={stats.shipped} suffix="单" valueStyle={{ color: '#13c2c2' }} />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic title="已完成" value={stats.completed} suffix="单" valueStyle={{ color: '#52c41a' }} />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic title="总收入" value={stats.totalRevenue} prefix="¥" precision={2} />
          </Card>
        </Col>
      </Row>

      {/* 操作栏 */}
      <Card style={{ marginBottom: 16 }}>
        <Space wrap>
          <Input
            placeholder="搜索订单号/客户名/邮箱"
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ width: 280 }}
            allowClear
          />
          <Select value={statusFilter} onChange={setStatusFilter} style={{ width: 140 }}>
            <Option value="all">全部状态</Option>
            <Option value="pending">待付款</Option>
            <Option value="processing">处理中</Option>
            <Option value="shipped">已发货</Option>
            <Option value="completed">已完成</Option>
            <Option value="cancelled">已取消</Option>
            <Option value="refunded">已退款</Option>
          </Select>
          <Button icon={<ReloadOutlined />} onClick={loadOrders}>
            刷新
          </Button>
          <Button icon={<DownloadOutlined />} onClick={handleExport}>
            导出 CSV
          </Button>
        </Space>
      </Card>

      {/* 订单表格 */}
      <Card>
        <Table
          columns={columns}
          dataSource={filteredOrders}
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

      {/* 订单详情弹窗 */}
      <Modal
        title={`订单详情 - ${selectedOrder?.order_number}`}
        open={detailVisible}
        onCancel={() => setDetailVisible(false)}
        footer={[
          <Button key="close" onClick={() => setDetailVisible(false)}>
            关闭
          </Button>,
        ]}
        width={800}
      >
        {selectedOrder && (
          <div>
            {/* 订单状态 */}
            <div style={{ marginBottom: 24, textAlign: 'center' }}>
              <Badge
                status={statusConfig[selectedOrder.status]?.color as any}
                text={
                  <span style={{ fontSize: 18, fontWeight: 600 }}>
                    {statusConfig[selectedOrder.status]?.text}
                  </span>
                }
              />
            </div>

            {/* 订单信息 */}
            <Descriptions title="订单信息" bordered column={2} size="small" style={{ marginBottom: 24 }}>
              <Descriptions.Item label="订单号">{selectedOrder.order_number}</Descriptions.Item>
              <Descriptions.Item label="创建时间">{selectedOrder.created_at}</Descriptions.Item>
              <Descriptions.Item label="支付方式">{selectedOrder.payment_method}</Descriptions.Item>
              <Descriptions.Item label="更新时间">{selectedOrder.updated_at}</Descriptions.Item>
              <Descriptions.Item label="WooCommerce ID">
                {selectedOrder.woocommerce_id ? `#${selectedOrder.woocommerce_id}` : '未同步'}
              </Descriptions.Item>
              <Descriptions.Item label="订单金额">
                <span style={{ color: '#f5222d', fontWeight: 600 }}>¥{selectedOrder.total.toFixed(2)}</span>
              </Descriptions.Item>
            </Descriptions>

            {/* 客户信息 */}
            <Descriptions title="客户信息" bordered column={2} size="small" style={{ marginBottom: 24 }}>
              <Descriptions.Item label="客户姓名">{selectedOrder.customer_name}</Descriptions.Item>
              <Descriptions.Item label="邮箱">{selectedOrder.customer_email}</Descriptions.Item>
              <Descriptions.Item label="收货地址" span={2}>
                {selectedOrder.shipping_address}
              </Descriptions.Item>
            </Descriptions>

            {/* 商品列表 */}
            <h4>商品列表</h4>
            <Table
              dataSource={selectedOrder.items}
              rowKey="product_name"
              pagination={false}
              size="small"
              columns={[
                { title: '商品名称', dataIndex: 'product_name', key: 'product_name' },
                { title: '单价', dataIndex: 'price', key: 'price', render: (v) => `¥${v.toFixed(2)}` },
                { title: '数量', dataIndex: 'quantity', key: 'quantity' },
                { title: '小计', dataIndex: 'subtotal', key: 'subtotal', render: (v) => `¥${v.toFixed(2)}` },
              ]}
              summary={() => (
                <Table.Summary.Row>
                  <Table.Summary.Cell index={0} colSpan={3}>
                    <strong>合计</strong>
                  </Table.Summary.Cell>
                  <Table.Summary.Cell index={1}>
                    <strong style={{ color: '#f5222d' }}>¥{selectedOrder.total.toFixed(2)}</strong>
                  </Table.Summary.Cell>
                </Table.Summary.Row>
              )}
            />

            {/* 订单时间线 */}
            <h4 style={{ marginTop: 24 }}>订单进度</h4>
            <Timeline
              items={[
                {
                  color: 'green',
                  children: (
                    <div>
                      <p><strong>订单创建</strong></p>
                      <p style={{ color: '#999' }}>{selectedOrder.created_at}</p>
                    </div>
                  ),
                },
                ...(selectedOrder.status !== 'pending'
                  ? [
                      {
                        color: 'blue',
                        children: (
                          <div>
                            <p><strong>订单确认</strong></p>
                            <p style={{ color: '#999' }}>{selectedOrder.updated_at}</p>
                          </div>
                        ),
                      },
                    ]
                  : []),
                ...(['shipped', 'completed'].includes(selectedOrder.status)
                  ? [
                      {
                        color: 'cyan',
                        children: (
                          <div>
                            <p><strong>商品发货</strong></p>
                            <p style={{ color: '#999' }}>{selectedOrder.updated_at}</p>
                          </div>
                        ),
                      },
                    ]
                  : []),
                ...(selectedOrder.status === 'completed'
                  ? [
                      {
                        color: 'green',
                        children: (
                          <div>
                            <p><strong>订单完成</strong></p>
                            <p style={{ color: '#999' }}>{selectedOrder.updated_at}</p>
                          </div>
                        ),
                      },
                    ]
                  : []),
              ]}
            />
          </div>
        )}
      </Modal>
    </div>
  );
};

export default OrdersPage;
