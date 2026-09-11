import React, { useState, useEffect } from 'react'
import { Table, Card, Tag, Typography, Select, Pagination, Spin, Empty, Button } from 'antd'
import { EyeOutlined } from '@ant-design/icons'
import { api, Order } from '../api/client'
import { navigateTo } from '../navigate'

const { Title, Text } = Typography

const statusColors: Record<string, string> = {
  pending: 'orange',
  confirmed: 'blue',
  processing: 'cyan',
  shipped: 'geekblue',
  delivered: 'green',
  cancelled: 'red',
}

const paymentColors: Record<string, string> = {
  unpaid: 'red',
  partial: 'orange',
  paid: 'green',
  overdue: 'red',
}

export default function OrdersPage() {
  const [orders, setOrders] = useState<Order[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(10)
  const [loading, setLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState<string | undefined>()

  const loadOrders = async () => {
    setLoading(true)
    try {
      const res = await api.getOrders(page, pageSize, statusFilter)
      setOrders(res.items)
      setTotal(res.total)
    } catch (e: any) {
      // error handled globally
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadOrders()
  }, [page, statusFilter])

  const columns = [
    {
      title: 'Order Number',
      dataIndex: 'order_number',
      key: 'order_number',
      render: (v: string, record: Order) => (
        <a onClick={() => { navigateTo(`/orders/${record.id}`) }}>
          <Text strong>{v}</Text>
        </a>
      ),
    },
    {
      title: 'Date',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (v: string) => new Date(v).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' }),
    },
    {
      title: 'Items',
      key: 'items',
      render: (_: any, record: Order) => `${record.items.length} product(s), ${record.items.reduce((s, i) => s + i.quantity, 0)} pcs`,
    },
    {
      title: 'Total',
      dataIndex: 'total',
      key: 'total',
      render: (v: number, record: Order) => <Text strong>${v.toFixed(2)} {record.currency}</Text>,
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (v: string) => <Tag color={statusColors[v] || 'default'}>{v.toUpperCase()}</Tag>,
    },
    {
      title: 'Payment',
      dataIndex: 'payment_status',
      key: 'payment_status',
      render: (v: string) => <Tag color={paymentColors[v] || 'default'}>{v.toUpperCase()}</Tag>,
    },
    {
      title: 'Tracking',
      key: 'tracking',
      render: (_: any, record: Order) =>
        record.tracking_number ? (
          <Text type="secondary" style={{ fontSize: 12 }}>{record.tracking_carrier}: {record.tracking_number}</Text>
        ) : <Text type="secondary">—</Text>,
    },
    {
      title: 'Action',
      key: 'action',
      render: (_: any, record: Order) => (
        <Button type="link" icon={<EyeOutlined />} onClick={() => { navigateTo(`/orders/${record.id}`) }}>
          View
        </Button>
      ),
    },
  ]

  return (
    <div>
      <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={4} style={{ margin: 0 }}>My Orders</Title>
        <Select
          placeholder="Filter by status"
          value={statusFilter}
          onChange={v => { setStatusFilter(v); setPage(1) }}
          style={{ width: 180 }}
          allowClear
          options={[
            { value: 'pending', label: 'Pending' },
            { value: 'confirmed', label: 'Confirmed' },
            { value: 'processing', label: 'Processing' },
            { value: 'shipped', label: 'Shipped' },
            { value: 'delivered', label: 'Delivered' },
            { value: 'cancelled', label: 'Cancelled' },
          ]}
        />
      </div>

      <Card>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin size="large" /></div>
        ) : orders.length === 0 ? (
          <Empty description="No orders yet" />
        ) : (
          <>
            <Table
              dataSource={orders}
              columns={columns}
              rowKey="id"
              pagination={false}
            />
            <div style={{ textAlign: 'center', marginTop: 16 }}>
              <Pagination
                current={page}
                pageSize={pageSize}
                total={total}
                onChange={setPage}
                showSizeChanger={false}
              />
            </div>
          </>
        )}
      </Card>
    </div>
  )
}
