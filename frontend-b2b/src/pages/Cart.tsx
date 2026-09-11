import React, { useState } from 'react'
import { Table, Button, InputNumber, Card, Typography, Space, message, Empty, Popconfirm, Modal, Form, Input, Select } from 'antd'
import { DeleteOutlined, ShoppingCartOutlined, CreditCardOutlined } from '@ant-design/icons'
import { useCart } from '../cart'
import { useAuth } from '../auth'
import { api, Order } from '../api/client'
import { navigateTo } from '../navigate'

const { Title, Text } = Typography

export default function CartPage() {
  const { items, updateQuantity, removeFromCart, clearCart, totalAmount, totalItems } = useCart()
  const { agent } = useAuth()
  const [checkoutLoading, setCheckoutLoading] = useState(false)
  const [checkoutModal, setCheckoutModal] = useState(false)
  const [form] = Form.useForm()

  const handleCheckout = async () => {
    try {
      const values = await form.validateFields()
      setCheckoutLoading(true)

      const shippingAddress = {
        company: values.company || agent?.company_name,
        contact: values.contact || agent?.contact_name,
        phone: values.phone || agent?.phone,
        country: values.country || agent?.country,
        city: values.city || agent?.city,
        address: values.address || agent?.address,
      }

      const order: Order = await api.createOrder(
        items.map(i => ({ product_id: i.product.id, quantity: i.quantity })),
        shippingAddress,
        values.notes
      )

      message.success(`Order ${order.order_number} placed successfully!`)
      clearCart()
      setCheckoutModal(false)
      navigateTo(`/orders/${order.id}`)
    } catch (e: any) {
      message.error(e.message || 'Failed to place order')
    } finally {
      setCheckoutLoading(false)
    }
  }

  const columns = [
    {
      title: 'Product',
      dataIndex: 'product',
      key: 'product',
      render: (_: any, record: any) => (
        <Space>
          <div style={{ width: 48, height: 48, background: '#f0f0f0', borderRadius: 4, display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
            {record.product.images?.[0] ? (
              <img src={record.product.images[0]} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            ) : <Text type="secondary" style={{ fontSize: 10 }}>No img</Text>}
          </div>
          <div>
            <div><Text strong>{record.product.name}</Text></div>
            <Text type="secondary" style={{ fontSize: 12 }}>SKU: {record.product.sku}</Text>
          </div>
        </Space>
      ),
    },
    {
      title: 'Unit Price',
      dataIndex: ['product', 'wholesale_price'],
      key: 'price',
      render: (v: number) => <Text strong>${v.toFixed(2)}</Text>,
    },
    {
      title: 'MOQ',
      dataIndex: ['product', 'moq'],
      key: 'moq',
    },
    {
      title: 'Quantity',
      key: 'quantity',
      render: (_: any, record: any) => (
        <InputNumber
          min={record.product.moq}
          value={record.quantity}
          onChange={v => updateQuantity(record.product.id, v || record.product.moq)}
          style={{ width: 100 }}
        />
      ),
    },
    {
      title: 'Subtotal',
      key: 'subtotal',
      render: (_: any, record: any) => (
        <Text strong style={{ color: '#1677ff' }}>
          ${(record.product.wholesale_price * record.quantity).toFixed(2)}
        </Text>
      ),
    },
    {
      title: 'Action',
      key: 'action',
      render: (_: any, record: any) => (
        <Popconfirm title="Remove this item?" onConfirm={() => removeFromCart(record.product.id)}>
          <Button type="text" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ]

  if (items.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <ShoppingCartOutlined style={{ fontSize: 64, color: '#d9d9d9', marginBottom: 16 }} />
        <Title level={4}>Your cart is empty</Title>
        <Text type="secondary">Browse our wholesale catalog and add products to your cart</Text>
        <div style={{ marginTop: 24 }}>
          <Button type="primary" size="large" onClick={() => { navigateTo('/products') }}>
            Browse Products
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div>
      <Title level={4}>Shopping Cart ({totalItems} items)</Title>

      <Card>
        <Table
          dataSource={items}
          columns={columns}
          rowKey={r => r.product.id}
          pagination={false}
          footer={() => (
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Popconfirm title="Clear all items?" onConfirm={clearCart}>
                <Button danger>Clear Cart</Button>
              </Popconfirm>
              <div style={{ textAlign: 'right' }}>
                <Text type="secondary">Subtotal: </Text>
                <Text style={{ fontSize: 24, fontWeight: 700, color: '#1677ff' }}>
                  ${totalAmount.toFixed(2)}
                </Text>
                {agent && agent.discount_percent > 0 && (
                  <div><Text type="secondary" style={{ fontSize: 12 }}>
                    Tier discount {agent.discount_percent}% will be applied at checkout
                  </Text></div>
                )}
              </div>
            </div>
          )}
        />
      </Card>

      <div style={{ marginTop: 24, textAlign: 'right' }}>
        <Space>
          <Button size="large" onClick={() => { navigateTo('/products') }}>
            Continue Shopping
          </Button>
          <Button
            type="primary"
            size="large"
            icon={<CreditCardOutlined />}
            onClick={() => setCheckoutModal(true)}
          >
            Proceed to Checkout
          </Button>
        </Space>
      </div>

      <Modal
        title="Confirm Order"
        open={checkoutModal}
        onCancel={() => setCheckoutModal(false)}
        footer={[
          <Button key="cancel" onClick={() => setCheckoutModal(false)}>Cancel</Button>,
          <Button key="submit" type="primary" loading={checkoutLoading} onClick={handleCheckout}>
            Place Order
          </Button>,
        ]}
        width={600}
      >
        <div style={{ background: '#f6ffed', padding: 12, borderRadius: 4, marginBottom: 16 }}>
          <Text strong>Order Total: ${totalAmount.toFixed(2)}</Text>
          {agent && (
            <div>
              <Text type="secondary" style={{ fontSize: 12 }}>
                Credit available: ${(agent.available_credit).toFixed(2)} | Payment terms: {agent.payment_terms_days} days
              </Text>
            </div>
          )}
        </div>

        <Form form={form} layout="vertical">
          <Form.Item name="company" label="Company" initialValue={agent?.company_name}>
            <Input />
          </Form.Item>
          <div style={{ display: 'flex', gap: 12 }}>
            <Form.Item name="contact" label="Contact Person" initialValue={agent?.contact_name} style={{ flex: 1 }}>
              <Input />
            </Form.Item>
            <Form.Item name="phone" label="Phone" initialValue={agent?.phone} style={{ flex: 1 }}>
              <Input />
            </Form.Item>
          </div>
          <div style={{ display: 'flex', gap: 12 }}>
            <Form.Item name="country" label="Country" initialValue={agent?.country} style={{ flex: 1 }}>
              <Input />
            </Form.Item>
            <Form.Item name="city" label="City" initialValue={agent?.city} style={{ flex: 1 }}>
              <Input />
            </Form.Item>
          </div>
          <Form.Item name="address" label="Shipping Address" initialValue={agent?.address}>
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="notes" label="Order Notes (optional)">
            <Input.TextArea rows={2} placeholder="Any special instructions..." />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
