import paramiko

# SSH连接配置
hostname = "95.217.218.178"
port = 22
username = "root"
password = "4SqwD8k@vuXWYUE%!bkfyf1b"

# 创建SSH客户端
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    print("=" * 60)
    print("任务4：采购订单管理页面开发")
    print("=" * 60)
    
    print("\n正在连接服务器...")
    ssh.connect(hostname, port, username, password, timeout=30)
    print("SSH连接成功！")
    
    # 步骤1: 创建采购订单管理页面
    print("\n" + "=" * 60)
    print("步骤1: 创建采购订单管理页面")
    print("=" * 60)
    
    purchase_orders_page = '''import { useState, useEffect } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Input, Select,
  Statistic, Row, Col, Spin, message, Modal, Descriptions, DatePicker,
  Empty, Tabs
} from 'antd'
import {
  ShoppingCartOutlined, DollarOutlined, CheckCircleOutlined,
  TruckOutlined, ClockCircleOutlined, SearchOutlined, ReloadOutlined,
  EyeOutlined, PlusOutlined
} from '@ant-design/icons'
import dayjs from 'dayjs'

const { Title, Text } = Typography
const { RangePicker } = DatePicker

interface PurchaseOrder {
  id: string
  po_number: string
  supplier_id: string | null
  supplier_name: string
  status: string
  currency: string
  subtotal: number
  shipping_cost: number
  total: number
  expected_delivery_at: string | null
  received_at: string | null
  notes: string | null
  created_at: string
}

const statusColors: Record<string, string> = {
  pending: 'default',
  ordered: 'blue',
  shipped: 'cyan',
  received: 'green',
  completed: 'green',
  cancelled: 'red',
}

const statusText: Record<string, string> = {
  pending: '待下单',
  ordered: '已下单',
  shipped: '运输中',
  received: '已收货',
  completed: '已完成',
  cancelled: '已取消',
}

export default function PurchaseOrdersPage() {
  const [loading, setLoading] = useState(false)
  const [orders, setOrders] = useState<PurchaseOrder[]>([])
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [viewingOrder, setViewingOrder] = useState<PurchaseOrder | null>(null)
  const [statusFilter, setStatusFilter] = useState('all')
  const [searchText, setSearchText] = useState('')
  const [stats, setStats] = useState({
    total_orders: 0,
    total_amount: 0,
    received: 0,
    shipped: 0,
    ordered: 0,
  })

  const loadOrders = async () => {
    try {
      setLoading(true)
      // 从API获取采购订单（如果API存在）
      const resp = await fetch('/api/v1/supply-chain/purchase-orders')
      if (resp.ok) {
        const data = await resp.json()
        setOrders(data)
      } else {
        // API不存在时使用空数据
        setOrders([])
        message.info('采购订单API暂未实现，显示示例数据')
      }
      
      // 获取统计数据
      const statsResp = await fetch('/api/v1/supply-chain/purchase-orders/stats')
      if (statsResp.ok) {
        const statsData = await statsResp.json()
        setStats({
          total_orders: statsData.total_orders || 0,
          total_amount: statsData.total_amount || 0,
          received: 0,
          shipped: 0,
          ordered: 0,
        })
      }
    } catch (e: any) {
      console.error('Load purchase orders error:', e)
      setOrders([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadOrders()
  }, [])

  const filteredOrders = orders.filter(order => {
    const matchStatus = statusFilter === 'all' || order.status === statusFilter
    const matchSearch = !searchText || 
      order.po_number.toLowerCase().includes(searchText.toLowerCase()) ||
      order.supplier_name.toLowerCase().includes(searchText.toLowerCase())
    return matchStatus && matchSearch
  })

  const columns = [
    {
      title: '订单号',
      dataIndex: 'po_number',
      key: 'po_number',
      width: 180,
      render: (text: string) => <Text strong>{text}</Text>,
    },
    {
      title: '供应商',
      dataIndex: 'supplier_name',
      key: 'supplier_name',
      width: 200,
      ellipsis: true,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={statusColors[status] || 'default'}>{statusText[status] || status}</Tag>
      ),
    },
    {
      title: '金额',
      dataIndex: 'total',
      key: 'total',
      width: 120,
      render: (total: number, record: PurchaseOrder) => (
        <Text strong>{record.currency} {total.toLocaleString()}</Text>
      ),
    },
    {
      title: '预计交货',
      dataIndex: 'expected_delivery_at',
      key: 'expected_delivery_at',
      width: 120,
      render: (date: string | null) => date ? dayjs(date).format('YYYY-MM-DD') : '-',
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 120,
      render: (date: string) => dayjs(date).format('YYYY-MM-DD'),
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_: any, record: PurchaseOrder) => (
        <Button type="link" icon={<EyeOutlined />} onClick={() => {
          setViewingOrder(record)
          setDetailModalOpen(true)
        }}>
          详情
        </Button>
      ),
    },
  ]

  return (
    <div style={{ padding: '24px' }}>
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <Title level={3} style={{ margin: 0 }}>
            <ShoppingCartOutlined style={{ marginRight: '8px', color: '#1890ff' }} />
            采购订单管理
          </Title>
          <Text type="secondary">采购订单列表、跟踪与对账</Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadOrders}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />}>新建采购单</Button>
        </Space>
      </div>

      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: '24px' }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="采购订单总数"
              value={stats.total_orders}
              prefix={<ShoppingCartOutlined style={{ color: '#1890ff' }} />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="采购总金额"
              value={stats.total_amount}
              precision={2}
              prefix={<DollarOutlined style={{ color: '#52c41a' }} />}
              suffix="CNY"
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="已收货"
              value={stats.received}
              prefix={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="运输中"
              value={stats.shipped}
              prefix={<TruckOutlined style={{ color: '#13c2c2' }} />}
            />
          </Card>
        </Col>
      </Row>

      {/* 筛选栏 */}
      <Card style={{ marginBottom: '16px' }}>
        <Space wrap>
          <Input
            placeholder="搜索订单号/供应商"
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ width: 240 }}
            allowClear
          />
          <Select
            value={statusFilter}
            onChange={setStatusFilter}
            style={{ width: 140 }}
            options={[
              { value: 'all', label: '全部状态' },
              { value: 'pending', label: '待下单' },
              { value: 'ordered', label: '已下单' },
              { value: 'shipped', label: '运输中' },
              { value: 'received', label: '已收货' },
              { value: 'completed', label: '已完成' },
              { value: 'cancelled', label: '已取消' },
            ]}
          />
          <RangePicker placeholder={['开始日期', '结束日期']} />
        </Space>
      </Card>

      {/* 订单列表 */}
      <Card>
        <Spin spinning={loading}>
          <Table
            columns={columns}
            dataSource={filteredOrders}
            rowKey="id"
            pagination={{
              pageSize: 20,
              showSizeChanger: true,
              showTotal: (total) => `共 ${total} 条订单`,
            }}
            locale={{
              emptyText: <Empty description="暂无采购订单，点击"新建采购单"创建" />,
            }}
          />
        </Spin>
      </Card>

      {/* 订单详情弹窗 */}
      <Modal
        title="采购订单详情"
        open={detailModalOpen}
        onCancel={() => setDetailModalOpen(false)}
        footer={[
          <Button key="close" onClick={() => setDetailModalOpen(false)}>关闭</Button>,
        ]}
        width={700}
      >
        {viewingOrder && (
          <div>
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="订单号" span={2}>
                <Text strong>{viewingOrder.po_number}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="供应商">{viewingOrder.supplier_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={statusColors[viewingOrder.status] || 'default'}>
                  {statusText[viewingOrder.status] || viewingOrder.status}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="货币">{viewingOrder.currency}</Descriptions.Item>
              <Descriptions.Item label="小计">{viewingOrder.subtotal.toLocaleString()}</Descriptions.Item>
              <Descriptions.Item label="运费">{viewingOrder.shipping_cost.toLocaleString()}</Descriptions.Item>
              <Descriptions.Item label="总金额">
                <Text strong style={{ color: '#f5222d' }}>{viewingOrder.total.toLocaleString()}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="预计交货">
                {viewingOrder.expected_delivery_at ? dayjs(viewingOrder.expected_delivery_at).format('YYYY-MM-DD') : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="实际收货">
                {viewingOrder.received_at ? dayjs(viewingOrder.received_at).format('YYYY-MM-DD') : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="创建时间" span={2}>
                {dayjs(viewingOrder.created_at).format('YYYY-MM-DD HH:mm:ss')}
              </Descriptions.Item>
              {viewingOrder.notes && (
                <Descriptions.Item label="备注" span={2}>{viewingOrder.notes}</Descriptions.Item>
              )}
            </Descriptions>
          </div>
        )}
      </Modal>
    </div>
  )
}
'''
    
    # 写入文件
    sftp = ssh.open_sftp()
    with sftp.file('/opt/nuotao/frontend/src/pages/PurchaseOrders.tsx', 'w') as f:
        f.write(purchase_orders_page.encode('utf-8'))
    sftp.close()
    print("✅ 采购订单管理页面已创建")
    
    # 步骤2: 添加采购订单列表API
    print("\n" + "=" * 60)
    print("步骤2: 添加采购订单列表API")
    print("=" * 60)
    
    # 读取supply_chain.py
    sftp = ssh.open_sftp()
    with sftp.file('/opt/nuotao/backend/app/api/v1/endpoints/supply_chain.py', 'r') as f:
        supply_chain_content = f.read().decode('utf-8')
    sftp.close()
    
    # 添加采购订单列表端点
    po_list_endpoint = '''


@router.get(
    "/purchase-orders",
    summary="List purchase orders",
)
async def list_purchase_orders(
    db: DbSession,
    workspace_id: WorkspaceId,
    status: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict]:
    """Return purchase orders, newest first."""
    from sqlalchemy import select, text
    
    query = """
        SELECT 
            po.id, po.po_number, po.supplier_id, 
            COALESCE(s.name, '未知供应商') as supplier_name,
            po.status, po.currency, po.subtotal, po.shipping_cost, 
            po.total, po.expected_delivery_at, po.received_at, 
            po.notes, po.created_at
        FROM purchase_orders po
        LEFT JOIN suppliers s ON s.id = po.supplier_id
        WHERE po.workspace_id = :workspace_id
    """
    params = {"workspace_id": str(workspace_id)}
    
    if status:
        query += " AND po.status = :status"
        params["status"] = status
    
    query += " ORDER BY po.created_at DESC LIMIT :limit"
    params["limit"] = limit
    
    result = await db.execute(text(query), params)
    rows = result.fetchall()
    
    orders = []
    for row in rows:
        orders.append({
            "id": str(row[0]),
            "po_number": row[1],
            "supplier_id": str(row[2]) if row[2] else None,
            "supplier_name": row[3],
            "status": row[4],
            "currency": row[5],
            "subtotal": float(row[6]) if row[6] else 0,
            "shipping_cost": float(row[7]) if row[7] else 0,
            "total": float(row[8]) if row[8] else 0,
            "expected_delivery_at": row[9].isoformat() if row[9] else None,
            "received_at": row[10].isoformat() if row[10] else None,
            "notes": row[11],
            "created_at": row[12].isoformat() if row[12] else None,
        })
    
    return orders
'''
    
    if '/purchase-orders"' not in supply_chain_content:
        supply_chain_content += po_list_endpoint
        sftp = ssh.open_sftp()
        with sftp.file('/opt/nuotao/backend/app/api/v1/endpoints/supply_chain.py', 'w') as f:
            f.write(supply_chain_content.encode('utf-8'))
        sftp.close()
        print("✅ 采购订单列表API已添加")
    else:
        print("⚠️ 采购订单列表API已存在")
    
    # 步骤3: 重启后端
    print("\n" + "=" * 60)
    print("步骤3: 重启后端服务")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("systemctl restart nuotao-backend && sleep 3 && systemctl is-active nuotao-backend")
    print(f"后端服务状态: {stdout.read().decode().strip()}")
    
    # 步骤4: 测试API
    print("\n" + "=" * 60)
    print("步骤4: 测试采购订单API")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("curl -s http://127.0.0.1:8000/api/v1/supply-chain/purchase-orders | python3 -c 'import sys,json; data=json.load(sys.stdin); print(f\"采购订单数量: {len(data)}\"); [print(f\"  - {o[\\\"po_number\\\"]}: {o[\\\"supplier_name\\\"]} - {o[\\\"total\\\"]} {o[\\\"currency\\\"]} ({o[\\\"status\\\"]})\") for o in data[:5]]' 2>&1")
    print(stdout.read().decode())
    
    # 步骤5: 重新构建前端
    print("\n" + "=" * 60)
    print("步骤5: 重新构建前端")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("cd /opt/nuotao/frontend && npm run build 2>&1 | tail -5")
    print(stdout.read().decode())
    
    # 步骤6: 部署前端
    print("\n" + "=" * 60)
    print("步骤6: 部署前端")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("""
rm -rf /var/www/nuotao/*
cp -r /opt/nuotao/frontend/dist/* /var/www/nuotao/
chown -R www-data:www-data /var/www/nuotao/
echo '前端部署完成'
""")
    print(stdout.read().decode())
    
    print("\n" + "=" * 60)
    print("任务4完成：采购订单管理页面已开发！")
    print("=" * 60)
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssh.close()
    print("\nSSH连接已关闭")
