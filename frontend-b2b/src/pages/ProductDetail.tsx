import React, { useState, useEffect } from 'react'
import { Row, Col, Card, Button, Tag, InputNumber, Typography, Descriptions, Spin, message, Breadcrumb } from 'antd'
import { ShoppingCartOutlined, LeftOutlined } from '@ant-design/icons'
import { api, Product } from '../api/client'
import { useCart } from '../cart'
import { navigateTo } from '../navigate'

const { Title, Text, Paragraph } = Typography

export default function ProductDetailPage({ productId }: { productId: string }) {
  const [product, setProduct] = useState<Product | null>(null)
  const [loading, setLoading] = useState(true)
  const [quantity, setQuantity] = useState(1)
  const { addToCart } = useCart()

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      try {
        const p = await api.getProduct(productId)
        setProduct(p)
        setQuantity(p.moq)
      } catch (e: any) {
        message.error(e.message || 'Failed to load product')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [productId])

  if (loading) {
    return <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>
  }

  if (!product) {
    return <div style={{ textAlign: 'center', padding: 60 }}><Text type="secondary">Product not found</Text></div>
  }

  const handleAddToCart = () => {
    addToCart(product, quantity)
    message.success(`Added ${quantity} × ${product.name} to cart`)
  }

  return (
    <div>
      <Breadcrumb style={{ marginBottom: 16 }}>
        <Breadcrumb.Item><a href="/products" onClick={(e) => { e.preventDefault(); navigateTo('/products') }}>Products</a></Breadcrumb.Item>
        <Breadcrumb.Item>{product.name}</Breadcrumb.Item>
      </Breadcrumb>

      <Row gutter={24}>
        <Col xs={24} md={10}>
          <Card>
            <div style={{
              height: 360,
              background: '#f0f0f0',
              borderRadius: 4,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              overflow: 'hidden',
            }}>
              {product.images && product.images.length > 0 ? (
                <img src={product.images[0]} alt={product.name} style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }} />
              ) : (
                <Text type="secondary">No Image Available</Text>
              )}
            </div>
          </Card>
        </Col>

        <Col xs={24} md={14}>
          <Card>
            <Title level={3} style={{ marginTop: 0 }}>{product.name}</Title>
            <div style={{ marginBottom: 16 }}>
              <Tag color="blue">SKU: {product.sku}</Tag>
              {product.category && <Tag>{product.category}</Tag>}
              {product.brand && <Tag>{product.brand}</Tag>}
              <Tag color={product.in_stock ? 'green' : 'red'}>
                {product.in_stock ? `In Stock (${product.stock_quantity})` : 'Out of Stock'}
              </Tag>
            </div>

            <div style={{ background: '#f6ffed', border: '1px solid #b7eb8f', borderRadius: 6, padding: 16, marginBottom: 20 }}>
              <Row align="middle">
                <Col>
                  <Text type="secondary">Wholesale Price</Text>
                  <div>
                    <Text style={{ fontSize: 32, fontWeight: 700, color: '#389e0d' }}>
                      ${product.wholesale_price.toFixed(2)}
                    </Text>
                    <Text style={{ marginLeft: 8 }}>{product.currency}</Text>
                  </div>
                </Col>
                {product.retail_price && (
                  <Col style={{ marginLeft: 32 }}>
                    <Text type="secondary">Suggested Retail</Text>
                    <div>
                      <Text delete style={{ fontSize: 18 }}>${product.retail_price.toFixed(2)}</Text>
                    </div>
                  </Col>
                )}
                <Col style={{ marginLeft: 32 }}>
                  <Text type="secondary">Minimum Order</Text>
                  <div>
                    <Text strong style={{ fontSize: 18 }}>{product.moq} pcs</Text>
                  </div>
                </Col>
              </Row>
            </div>

            {product.description && (
              <div style={{ marginBottom: 20 }}>
                <Title level={5}>Description</Title>
                <Paragraph>{product.description}</Paragraph>
              </div>
            )}

            <Descriptions column={2} size="small" style={{ marginBottom: 20 }}>
              {product.weight_kg && <Descriptions.Item label="Weight">{product.weight_kg} kg</Descriptions.Item>}
              {product.dimensions && (
                <Descriptions.Item label="Dimensions">
                  {product.dimensions.length}×{product.dimensions.width}×{product.dimensions.height} cm
                </Descriptions.Item>
              )}
            </Descriptions>

            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              <div>
                <Text type="secondary" style={{ marginRight: 8 }}>Quantity:</Text>
                <InputNumber
                  min={product.moq}
                  value={quantity}
                  onChange={v => setQuantity(v || product.moq)}
                  size="large"
                  style={{ width: 120 }}
                />
                <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
                  (MOQ: {product.moq})
                </Text>
              </div>
              <Button
                type="primary"
                size="large"
                icon={<ShoppingCartOutlined />}
                onClick={handleAddToCart}
                disabled={!product.in_stock}
              >
                Add to Cart — ${(product.wholesale_price * quantity).toFixed(2)}
              </Button>
            </div>
          </Card>
        </Col>
      </Row>
    </div>
  )
}
