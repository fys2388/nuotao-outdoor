import React, { useState, useEffect } from 'react'
import { Row, Col, Card, Button, Typography, Spin, Alert } from 'antd'
import { publicApi, navigate, PublicCategory, PublicProduct } from '../../api/publicApi'
import PublicLayout, { COLORS } from './PublicLayout'

const { Title, Text, Paragraph } = Typography

const WHY_POINTS: { title: string; description: string }[] = [
  {
    title: 'Curated product range',
    description:
      'A focused selection of practical camping and hiking products, chosen for everyday outdoor use.',
  },
  {
    title: 'Responsive sourcing support',
    description:
      'We work with buyers to understand their product needs and respond with suitable options.',
  },
  {
    title: 'Wholesale partnership focus',
    description:
      'Our showcase is built for retailers and distributors rather than individual retail shoppers.',
  },
  {
    title: 'Clear enquiry process',
    description:
      'Share your requirements through a simple enquiry and our team follows up with next steps.',
  },
]

export default function PublicHome() {
  const [categories, setCategories] = useState<PublicCategory[]>([])
  const [featured, setFeatured] = useState<PublicProduct[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const [cats, prods] = await Promise.all([
          publicApi.getCategories(),
          publicApi.getProducts(1, 8),
        ])
        if (cancelled) return
        setCategories(cats)
        setFeatured(prods.items)
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load content')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <PublicLayout currentPath="/">
      {/* Hero */}
      <div style={{ background: COLORS.forest, color: '#FFFFFF', padding: '72px 32px' }}>
        <div style={{ maxWidth: 1200, margin: '0 auto' }}>
          <Title level={1} style={{ color: '#FFFFFF', marginBottom: 16, fontSize: 40 }}>
            Outdoor Gear Wholesale &amp; Product Sourcing
          </Title>
          <Paragraph style={{ color: '#E4EDE6', fontSize: 18, maxWidth: 720, marginBottom: 32 }}>
            Discover practical camping and hiking products for your retail business. Explore our
            product range and discuss sourcing opportunities with Nuotao Outdoor.
          </Paragraph>
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            <Button
              size="large"
              onClick={() => navigate('/request-a-quote')}
              style={{ background: COLORS.orange, borderColor: COLORS.orange, fontWeight: 600 }}
            >
              Request a Quote
            </Button>
            <Button
              size="large"
              onClick={() => navigate('/products')}
              style={{
                background: 'transparent',
                borderColor: '#FFFFFF',
                color: '#FFFFFF',
                fontWeight: 600,
              }}
            >
              Explore Products
            </Button>
          </div>
        </div>
      </div>

      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '48px 32px' }}>
        {error && (
          <Alert
            message="Could not load content"
            description={error}
            type="warning"
            showIcon
            style={{ marginBottom: 24 }}
          />
        )}

        {loading ? (
          <div style={{ textAlign: 'center', padding: 60 }}>
            <Spin size="large" />
          </div>
        ) : (
          <>
            {/* Product categories */}
            {categories.length > 0 && (
              <section style={{ marginBottom: 56 }}>
                <Title level={2} style={{ color: COLORS.charcoal, marginBottom: 24 }}>
                  Product Categories
                </Title>
                <Row gutter={[16, 16]}>
                  {categories.map((cat) => (
                    <Col xs={24} sm={12} md={8} lg={6} key={cat.slug}>
                      <Card
                        hoverable
                        onClick={() => navigate(`/products?category=${encodeURIComponent(cat.slug)}`)}
                        style={{ height: '100%' }}
                      >
                        <Title level={4} style={{ margin: 0, color: COLORS.forest }}>
                          {cat.name}
                        </Title>
                        <Text type="secondary">
                          {cat.product_count} product{cat.product_count === 1 ? '' : 's'}
                        </Text>
                      </Card>
                    </Col>
                  ))}
                </Row>
              </section>
            )}

            {/* Featured products */}
            {featured.length > 0 && (
              <section style={{ marginBottom: 56 }}>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'baseline',
                    marginBottom: 24,
                  }}
                >
                  <Title level={2} style={{ color: COLORS.charcoal, margin: 0 }}>
                    Featured Products
                  </Title>
                  <span
                    onClick={() => navigate('/products')}
                    style={{ cursor: 'pointer', color: COLORS.forest, fontWeight: 600 }}
                  >
                    View all products
                  </span>
                </div>
                <Row gutter={[16, 16]}>
                  {featured.map((product) => (
                    <Col xs={24} sm={12} md={8} lg={6} key={product.slug}>
                      <Card
                        hoverable
                        onClick={() => navigate(`/products/${product.slug}`)}
                        style={{ height: '100%' }}
                        cover={
                          <div
                            style={{
                              height: 180,
                              background: '#ECECE5',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              overflow: 'hidden',
                            }}
                          >
                            {product.images && product.images.length > 0 ? (
                              <img
                                src={product.images[0]}
                                alt={product.title}
                                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                              />
                            ) : (
                              <Text type="secondary">No Image</Text>
                            )}
                          </div>
                        }
                      >
                        <Card.Meta
                          title={product.title}
                          description={
                            <>
                              {product.category && (
                                <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>
                                  {product.category}
                                </Text>
                              )}
                              <Text style={{ display: 'block' }}>
                                {product.description
                                  ? product.description.length > 90
                                    ? product.description.slice(0, 90) + '…'
                                    : product.description
                                  : ''}
                              </Text>
                            </>
                          }
                        />
                      </Card>
                    </Col>
                  ))}
                </Row>
              </section>
            )}

            {/* Why work with Nuotao */}
            <section style={{ marginBottom: 56 }}>
              <Title level={2} style={{ color: COLORS.charcoal, marginBottom: 24 }}>
                Why Work with Nuotao
              </Title>
              <Row gutter={[16, 16]}>
                {WHY_POINTS.map((point) => (
                  <Col xs={24} sm={12} md={6} key={point.title}>
                    <Card style={{ height: '100%' }}>
                      <Title level={4} style={{ color: COLORS.forest, marginTop: 0 }}>
                        {point.title}
                      </Title>
                      <Text style={{ color: COLORS.charcoal }}>{point.description}</Text>
                    </Card>
                  </Col>
                ))}
              </Row>
            </section>

            {/* Business cooperation */}
            <section>
              <Card
                style={{ background: COLORS.forest, border: 'none' }}
                bodyStyle={{ padding: '40px 32px' }}
              >
                <Title level={2} style={{ color: '#FFFFFF', marginTop: 0 }}>
                  Business Cooperation
                </Title>
                <Paragraph style={{ color: '#E4EDE6', fontSize: 16, maxWidth: 720 }}>
                  We collaborate with retailers, distributors, and e-commerce sellers looking for
                  reliable outdoor product supply. Tell us about your business and the products you
                  are interested in, and we will discuss how we can support your sourcing needs.
                </Paragraph>
                <Button
                  size="large"
                  onClick={() => navigate('/request-a-quote')}
                  style={{ background: COLORS.orange, borderColor: COLORS.orange, fontWeight: 600 }}
                >
                  Contact Us / Send an Enquiry
                </Button>
              </Card>
            </section>
          </>
        )}
      </div>
    </PublicLayout>
  )
}
