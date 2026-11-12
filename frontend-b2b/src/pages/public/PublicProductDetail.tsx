import React, { useState, useEffect } from 'react'
import { Row, Col, Card, Button, Typography, Spin, Alert, Descriptions, Space } from 'antd'
import { publicApi, navigate, PublicProduct } from '../../api/publicApi'
import PublicLayout, { COLORS } from './PublicLayout'

const { Title, Text, Paragraph } = Typography

export default function PublicProductDetail({ slug }: { slug: string }) {
  const [product, setProduct] = useState<PublicProduct | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeImage, setActiveImage] = useState(0)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setError(null)
      setActiveImage(0)
      try {
        const data = await publicApi.getProduct(slug)
        if (!cancelled) setProduct(data)
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load product')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [slug])

  const images: string[] = product?.images ?? []

  return (
    <PublicLayout currentPath="/products">
      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '40px 32px' }}>
        <span
          onClick={() => navigate('/products')}
          style={{ cursor: 'pointer', color: COLORS.forest, fontWeight: 600 }}
        >
          ← Back to Products
        </span>

        {loading ? (
          <div style={{ textAlign: 'center', padding: 60 }}>
            <Spin size="large" />
          </div>
        ) : error ? (
          <Alert
            message="Could not load product"
            description={error}
            type="warning"
            showIcon
            style={{ marginTop: 24 }}
          />
        ) : !product ? (
          <Alert message="Product not found" type="info" showIcon style={{ marginTop: 24 }} />
        ) : (
          <Row gutter={[32, 32]} style={{ marginTop: 24 }}>
            {/* Images */}
            <Col xs={24} md={12}>
              <div
                style={{
                  height: 400,
                  background: '#ECECE5',
                  borderRadius: 8,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  overflow: 'hidden',
                  marginBottom: 12,
                }}
              >
                {images.length > 0 ? (
                  <img
                    src={images[activeImage]}
                    alt={product.title}
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  />
                ) : (
                  <Text type="secondary">No Image</Text>
                )}
              </div>
              {images.length > 1 && (
                <Space wrap>
                  {images.map((img, idx) => (
                    <div
                      key={idx}
                      onClick={() => setActiveImage(idx)}
                      style={{
                        width: 64,
                        height: 64,
                        borderRadius: 6,
                        overflow: 'hidden',
                        cursor: 'pointer',
                        border: idx === activeImage ? `2px solid ${COLORS.forest}` : '2px solid transparent',
                        background: '#ECECE5',
                      }}
                    >
                      <img
                        src={img}
                        alt={`${product.title} thumbnail ${idx + 1}`}
                        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      />
                    </div>
                  ))}
                </Space>
              )}
            </Col>

            {/* Details */}
            <Col xs={24} md={12}>
              <Title level={2} style={{ color: COLORS.charcoal, marginTop: 0 }}>
                {product.title}
              </Title>
              {product.category && (
                <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
                  Category: {product.category}
                </Text>
              )}
              {product.description && (
                <Paragraph style={{ color: COLORS.charcoal, fontSize: 15 }}>
                  {product.description}
                </Paragraph>
              )}

              {product.specifications &&
                Object.keys(product.specifications).length > 0 && (
                  <Card style={{ marginBottom: 24 }} bodyStyle={{ padding: '16px 24px' }}>
                    <Title level={4} style={{ color: COLORS.forest, marginTop: 0 }}>
                      Specifications
                    </Title>
                    <Descriptions column={1} size="small">
                      {Object.entries(product.specifications).map(([key, value]) => (
                        <Descriptions.Item key={key} label={key}>
                          {String(value)}
                        </Descriptions.Item>
                      ))}
                    </Descriptions>
                  </Card>
                )}

              <Button
                type="primary"
                size="large"
                onClick={() => navigate(`/request-a-quote?product=${encodeURIComponent(slug)}`)}
                style={{ background: COLORS.forest, borderColor: COLORS.forest, fontWeight: 600 }}
              >
                Request a Quote
              </Button>
            </Col>
          </Row>
        )}
      </div>
    </PublicLayout>
  )
}
