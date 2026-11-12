import React, { useState, useEffect, useCallback } from 'react'
import { Row, Col, Card, Select, Pagination, Spin, Empty, Typography, Alert } from 'antd'
import { publicApi, navigate, PublicCategory, PublicProduct } from '../../api/publicApi'
import PublicLayout, { COLORS } from './PublicLayout'

const { Title, Text } = Typography

const PAGE_SIZE = 12

function readInitialCategory(): string | undefined {
  const params = new URLSearchParams(window.location.search)
  const cat = params.get('category')
  return cat && cat.length > 0 ? cat : undefined
}

export default function PublicCatalog() {
  const [products, setProducts] = useState<PublicProduct[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [category, setCategory] = useState<string | undefined>(readInitialCategory)
  const [categories, setCategories] = useState<PublicCategory[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const loadCategories = async () => {
      try {
        const cats = await publicApi.getCategories()
        if (!cancelled) setCategories(cats)
      } catch {
        // Category filter is optional; catalogue still works without it.
      }
    }
    loadCategories()
    return () => {
      cancelled = true
    }
  }, [])

  const loadProducts = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await publicApi.getProducts(page, PAGE_SIZE, category)
      setProducts(res.items)
      setTotal(res.total)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load products')
    } finally {
      setLoading(false)
    }
  }, [page, category])

  useEffect(() => {
    loadProducts()
  }, [loadProducts])

  const handleCategoryChange = (value: string | undefined) => {
    setCategory(value)
    setPage(1)
  }

  return (
    <PublicLayout currentPath="/products">
      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '40px 32px' }}>
        <Title level={2} style={{ color: COLORS.charcoal, marginBottom: 8 }}>
          Products
        </Title>
        <Text type="secondary" style={{ display: 'block', marginBottom: 24 }}>
          Browse our outdoor product range. Contact us for wholesale pricing and availability.
        </Text>

        <div style={{ marginBottom: 24, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <Select
            placeholder="Filter by category"
            value={category}
            onChange={handleCategoryChange}
            allowClear
            style={{ width: 240 }}
            options={categories.map((c) => ({ value: c.slug, label: c.name }))}
          />
        </div>

        {error && (
          <Alert
            message="Could not load products"
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
        ) : products.length === 0 ? (
          <Empty description="No products found" />
        ) : (
          <>
            <Row gutter={[16, 16]}>
              {products.map((product) => (
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
            <div style={{ textAlign: 'center', marginTop: 24 }}>
              <Pagination
                current={page}
                pageSize={PAGE_SIZE}
                total={total}
                onChange={setPage}
                showSizeChanger={false}
              />
            </div>
          </>
        )}
      </div>
    </PublicLayout>
  )
}
