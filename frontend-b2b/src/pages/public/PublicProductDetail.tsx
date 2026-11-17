import React, { useState, useEffect } from 'react'
import { Row, Col, Button, Typography, Spin, Alert, Descriptions, Space } from 'antd'
import { publicApi, navigate, PublicProduct } from '../../api/publicApi'
import PublicLayout, { COLORS } from './PublicLayout'
import { useSeo } from '../../hooks/useSeo'
import { stripHtml } from '../../utils/text'

const { Title, Text, Paragraph } = Typography

const S = {
  wrap: { maxWidth: 1200, margin: '0 auto', padding: '40px 32px 64px' },
  mainImg: {
    position: 'relative' as const,
    aspectRatio: '4 / 3',
    background: '#ECECE5',
    borderRadius: 14,
    overflow: 'hidden',
    marginBottom: 12,
  },
  img: { width: '100%', height: '100%', objectFit: 'cover' as const, display: 'block' },
  thumb: {
    width: 68,
    height: 68,
    borderRadius: 10,
    overflow: 'hidden',
    cursor: 'pointer',
    background: '#ECECE5',
    transition: 'borderColor 0.15s ease, transform 0.15s ease',
  },
  chip: {
    display: 'inline-block',
    padding: '2px 10px',
    borderRadius: 999,
    fontSize: 13,
    fontWeight: 600,
    color: COLORS.forest,
    background: 'rgba(46,94,58,0.09)',
    marginBottom: 14,
  },
  cta: {
    background: COLORS.forest,
    borderColor: COLORS.forest,
    fontWeight: 600,
    height: 48,
    padding: '0 28px',
  },
}

export default function PublicProductDetail({ slug }: { slug: string }) {
  const [product, setProduct] = useState<PublicProduct | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeImage, setActiveImage] = useState(0)

  useSeo(
    product
      ? `${product.title} — Nuotao Outdoor B2B`
      : 'Products — Nuotao Outdoor B2B',
    product?.description ?? 'Request wholesale pricing for this Nuotao Outdoor product. Bulk orders for retail and wholesale buyers.',
    product?.images?.[0],
  )

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
      <div style={S.wrap}>
        <span
          onClick={() => navigate('/products')}
          style={{ cursor: 'pointer', color: COLORS.forest, fontWeight: 600, fontSize: 14 }}
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
          <Row gutter={[40, 32]} style={{ marginTop: 24 }}>
            {/* Images */}
            <Col xs={24} md={12}>
              <div style={S.mainImg}>
                {images.length > 0 ? (
                  <img src={images[activeImage]} alt={product.title} style={S.img} />
                ) : (
                  <div
                    style={{
                      height: '100%',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: COLORS.charcoal,
                      opacity: 0.4,
                    }}
                  >
                    No Image
                  </div>
                )}
              </div>
              {images.length > 1 && (
                <Space wrap size={10}>
                  {images.map((img, idx) => (
                    <div
                      key={idx}
                      onClick={() => setActiveImage(idx)}
                      style={{
                        ...S.thumb,
                        border:
                          idx === activeImage
                            ? `2px solid ${COLORS.forest}`
                            : '2px solid transparent',
                      }}
                    >
                      <img
                        src={img}
                        alt={`${product.title} thumbnail ${idx + 1}`}
                        style={S.img}
                      />
                    </div>
                  ))}
                </Space>
              )}
            </Col>

            {/* Details */}
            <Col xs={24} md={12}>
              {product.category && <span style={S.chip}>{product.category}</span>}
              <Title level={2} style={{ color: COLORS.charcoal, marginTop: 0, lineHeight: 1.25 }}>
                {product.title}
              </Title>
              {product.description && (
                <Paragraph
                  style={{ color: COLORS.charcoal, fontSize: 15, lineHeight: 1.65, opacity: 0.9 }}
                >
                  {stripHtml(product.description)}
                </Paragraph>
              )}

              {product.specifications &&
                Object.keys(product.specifications).length > 0 && (
                  <div
                    style={{
                      border: '1px solid #E6E4DC',
                      borderRadius: 12,
                      padding: '18px 20px',
                      marginBottom: 28,
                      background: '#FFFFFF',
                    }}
                  >
                    <Title level={4} style={{ color: COLORS.forest, marginTop: 0, marginBottom: 12 }}>
                      Specifications
                    </Title>
                    <Descriptions column={1} size="small">
                      {Object.entries(product.specifications).map(([key, value]) => (
                        <Descriptions.Item key={key} label={key}>
                          {String(value)}
                        </Descriptions.Item>
                      ))}
                    </Descriptions>
                  </div>
                )}

              <Button
                type="primary"
                size="large"
                onClick={() => navigate(`/request-a-quote?product=${encodeURIComponent(slug)}`)}
                style={S.cta}
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