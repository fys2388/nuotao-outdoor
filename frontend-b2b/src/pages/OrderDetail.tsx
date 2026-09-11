import React, { useState, useEffect } from 'react'
import { Card, Descriptions, Table, Tag, Typography, Spin, Breadcrumb, Button, Steps } from 'antd'
import { LeftOutlined } from '@ant-design/icons'
import { api, Order } from '../api/client'
import { navigateTo } from '../navigate'

const { Title, Text } = Typography

const statusFlow = ['pending', 'confirmed', 'processing', 'shipped', 'delivered']

export default function OrderDetailPage({ orderId }: { orderId: string }) {
  const [order, setOrder] = useState<Order | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      try {
        const o = await api.getOrder(orderId)
        setOrder(o)
      } catch (e: any) {
        // handled
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [orderId])

  if (loading) {
    return <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>
  }

  if (!order) {
    return <div style={{ textAlign: 'center', padding: 60 }}><Text type="secondary">Order not found</Text></div>
  }

  const currentStep = statusFlow.indexOf(order.status)
  const stepIndex = currentStep >= 0 ? currentStep : 0

  const itemColumns = [
    { title: 'Product', dataIndex: 'product_name', key: 'product_name' },
    { title: 'SKU', dataIndex: 'sku', key: 'sku' },
    { title: 'Unit Price', dataIndex: 'unit_price', key: 'unit_price', render: (v: number) => `$${v.toFixed(2)}` },
    { title: 'Quantity', dataIndex: 'quantity', key: 'quantity' },
    { title: 'Subtotal', dataIndex: 'subtotal', key: 'subtotal', render: (v: number) => <Text strong>${v.toFixed(2)}</Text> },
  ]

  return (
    <div>
      <Breadcrumb style={{ marginBottom: 16 }}>
        <Breadcrumb.Item><a href="/orders" onClick={(e) => { e.preventDefault(); navigateTo('/orders') }}>My Orders</a></Breadcrumb.Item>
        <Breadcrumb.Item>{order.order_number}</Breadcrumb.Item>
      </Breadcrumb>

      <div style={{ marginBottom: 16 }}>
        <Button type="link" icon={<LeftOutlined />} onClick={() => { navigateTo('/orders') }}>
          Back to Orders
        </Button>
      </div>

      <Card title={`Order ${order.order_number}`} style={{ marginBottom: 16 }}>
        <Steps
          current={stepIndex}
          items={statusFlow.map(s => ({ title: s.charAt(0).toUpperCase() + s.slice(1) }))}
          style={{ marginBottom: 24 }}
        />

        <Descriptions column={3} bordered size="small">
          <Descriptions.Item label="Order Date">
            {new Date(order.created_at).toLocaleString('en-US')}
          </Descriptions.Item>
          <Descriptions.Item label="Status">
            <Tag color={order.status === 'delivered' ? 'green' : order.status === 'cancelled' ? 'red' : 'blue'}>
              {order.status.toUpperCase()}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="Payment">
            <Tag color={order.payment_status === 'paid' ? 'green' : 'orange'}>
              {order.payment_status.toUpperCase()}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="Payment Due Date">
            {order.payment_due_date || '—'}
          </Descriptions.Item>
          <Descriptions.Item label="Currency">{order.currency}</Descriptions.Item>
          <Descriptions.Item label="Last Updated">
            {new Date(order.updated_at).toLocaleString('en-US')}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="Items" style={{ marginBottom: 16 }}>
        <Table
          dataSource={order.items}
          columns={itemColumns}
          rowKey="id"
          pagination={false}
          summary={() => (
            <>
              <Table.Summary.Row>
                <Table.Summary.Cell index={0} colSpan={4} align="right">
                  <Text strong>Subtotal</Text>
                </Table.Summary.Cell>
                <Table.Summary.Cell index={4}>
                  <Text strong>${order.subtotal.toFixed(2)}</Text>
                </Table.Summary.Cell>
              </Table.Summary.Row>
              {order.discount_amount > 0 && (
                <Table.Summary.Row>
                  <Table.Summary.Cell index={0} colSpan={4} align="right">
                    <Text type="secondary">Discount</Text>
                  </Table.Summary.Cell>
                  <Table.Summary.Cell index={4}>
                    <Text type="secondary">-${order.discount_amount.toFixed(2)}</Text>
                  </Table.Summary.Cell>
                </Table.Summary.Row>
              )}
              <Table.Summary.Row>
                <Table.Summary.Cell index={0} colSpan={4} align="right">
                  <Text strong style={{ fontSize: 16 }}>Total</Text>
                </Table.Summary.Cell>
                <Table.Summary.Cell index={4}>
                  <Text strong style={{ fontSize: 16, color: '#1677ff' }}>${order.total.toFixed(2)}</Text>
                </Table.Summary.Cell>
              </Table.Summary.Row>
            </>
          )}
        />
      </Card>

      <div style={{ display: 'flex', gap: 16 }}>
        <Card title="Shipping Address" style={{ flex: 1 }}>
          <Descriptions column={1} size="small">
            <Descriptions.Item label="Company">{order.shipping_address?.company || '—'}</Descriptions.Item>
            <Descriptions.Item label="Contact">{order.shipping_address?.contact || '—'}</Descriptions.Item>
            <Descriptions.Item label="Phone">{order.shipping_address?.phone || '—'}</Descriptions.Item>
            <Descriptions.Item label="Country">{order.shipping_address?.country || '—'}</Descriptions.Item>
            <Descriptions.Item label="City">{order.shipping_address?.city || '—'}</Descriptions.Item>
            <Descriptions.Item label="Address">{order.shipping_address?.address || '—'}</Descriptions.Item>
          </Descriptions>
        </Card>

        <Card title="Tracking" style={{ flex: 1 }}>
          {order.tracking_number ? (
            <Descriptions column={1} size="small">
              <Descriptions.Item label="Carrier">{order.tracking_carrier || '—'}</Descriptions.Item>
              <Descriptions.Item label="Tracking Number">
                <Text strong copyable>{order.tracking_number}</Text>
              </Descriptions.Item>
            </Descriptions>
          ) : (
            <Text type="secondary">Tracking information will be available once the order ships.</Text>
          )}
          {order.notes && (
            <div style={{ marginTop: 12 }}>
              <Text type="secondary">Notes: {order.notes}</Text>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
