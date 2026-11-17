import React, { useState, useEffect, useCallback } from 'react'
import { Row, Col, Select, Pagination, Spin, Empty, Typography, Alert } from 'antd'
import { publicApi, navigate, PublicCategory, PublicProduct } from '../../api/publicApi'
import PublicLayout, { COLORS } from './PublicLayout'
import { useSeo } from '../../hooks/useSeo'
import { stripHtml } from '../../utils/text'

const { Title, Text } = Typography

const PAGE_SIZE = 12

const S = {
  wrap: { maxWidth: 1200, margin: '0 auto', padding: '48px 32px 64px' },
  head: { marginBottom: 32 },
  sub: { display: 'block', marginTop: 8, color: COLORS.charcoal, opacity: 0.72, fontSize: 15 },
  filterRow: { marginBottom: 28, display: 'flex', gap: 12, flexWrap: 'wrap' as const, alignItems: 'center' },
  card: {
    display: 'block' as const,
    height: '100%',
    background: '#FFFFFF',
    borderRadius: 14,
    overflow: 'hidden',
    border: '1px solid #E6E4DC',
    boxShadow: '0 1px 2px rgba(43,43,43,0.04)',
    cursor: 'pointer',
    transition: 'transform 0.18s ease, boxShadow 0.18s ease',
    // hover lift handled by a wrapper class below (inline can't :hover)
  },
  imgWrap: {
    position: 'relative' as const,
    aspectRatio: '4 / 3',
    overflow: 'hidden',
    background: '#ECECE5',
  },
  img: {
    width: '100%',
    height: '100%',
    objectFit: 'cover' as const,
    display: 'block',
    transition: 'transform 0.25s ease',
  },
  chip: {
    display: 'inline-block',
    padding: '2px 10px',
    borderRadius: 999,
    fontSize: 12,
    fontWeight: 600,
    color: COLORS.forest,
    background: 'rgba(46,94,58,0.09)',
    marginBottom: 10,
  },
  body: { padding: '16px 18px 20px' },
  title: {
    fontSize: 16,
    fontWeight: 600,
    color: COLORS.charcoal,
    lineHeight: 1.35,
    display: '-webkit-box',
    WebkitLineClamp: 2,
    WebkitBoxOrient: 'vertical' as const,
    overflow: 'hidden',
    marginBottom: 8,
  },
  desc: {
    fontSize: 14,
    color: COLORS.charcoal,
    opacity: 0.7,
    lineHeight: 1.5,
    display: '-webkit-box',
    WebkitLineClamp: 3,
    WebkitBoxOrient: 'vertical' as const,
    overflow: 'hidden',
  },
}

const cardHoverClass = 'nuotao-cat-card'
const cardStyle = document.createElement('style')
cardStyle.textContent = `
.${cardHoverClass}:hover {
  transform: translateY(-3px);
  boxShadow: 0 10px 28px rgba(43,43,43,0.12);
  border-color: ${COLORS.orange};
}
.${cardHoverClass}:hover .nuotao-cat-img {
  transform: scale(1.03);
}
`
document.head.appendChild(cardStyle)

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

  useSeo(
    'Products — Nuotao Outdoor B2B',
    'Browse the Nuotao Outdoor wholesale catalogue. Request pricing and bulk order availability for retail and wholesale buyers.',
  )

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
      <div style={S.wrap}>
        <div style={S.head}>
          <Title level={2} style={{ color: COLORS.charcoal, margin: 0 }}>
            Products
          </Title>
          <Text style={S.sub}>
            Browse our outdoor product range. Contact us for wholesale pricing and availability.
          </Text>
        </div>

        <div style={S.filterRow}>
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
          <div style={{ textAlign: 'center', padding: 80 }}>
            <Spin size="large" />
          </div>
        ) : products.length === 0 ? (
          <Empty description="No products found" />
        ) : (
          <>
            <Row gutter={[24, 24]}>
              {products.map((product) => (
                <Col xs={24} sm={12} lg={8} key={product.slug}>
                  <div
                    className={cardHoverClass}
                    style={S.card}
                    onClick={() => navigate(`/products/${product.slug}`)}
                    role="link"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') navigate(`/products/${product.slug}`)
                    }}
                  >
                    <div style={S.imgWrap}>
                      {product.images && product.images.length > 0 ? (
                        <img
                          className="nuotao-cat-img"
                          src={product.images[0]}
                          alt={product.title}
                          loading="lazy"
                          style={S.img}
                        />
                      ) : (
                        <div
                          style={{
                            height: '100%',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            color: COLORS.charcoal,
                            opacity: 0.4,
                            fontSize: 13,
                          }}
                        >
                          No Image
                        </div>
                      )}
                    </div>
                    <div style={S.body}>
                      {product.category && <span style={S.chip}>{product.category}</span>}
                      <div style={S.title}>{product.title}</div>
                      <div style={S.desc}>
                        {product.description
                          ? stripHtml(product.description).slice(0, 160)
                          : ''}
                      </div>
                    </div>
                  </div>
                </Col>
              ))}
            </Row>
            <div style={{ textAlign: 'center', marginTop: 36 }}>
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