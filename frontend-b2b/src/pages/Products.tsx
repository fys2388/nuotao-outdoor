import React, { useState, useEffect } from 'react'
import { Row, Col, Card, Input, Select, Button, Tag, Pagination, Spin, Empty, Typography, message } from 'antd'
import { SearchOutlined, ShoppingCartOutlined } from '@ant-design/icons'
import { api, Product } from '../api/client'
import { useCart } from '../cart'
import { navigateTo } from '../navigate'

const { Title, Text } = Typography

export default function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(12)
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState<string | undefined>()
  const [inStockOnly, setInStockOnly] = useState(false)
  const { addToCart } = useCart()

  const loadProducts = async () => {
    setLoading(true)
    try {
      const res = await api.getProducts(page, pageSize, search, category, inStockOnly)
      setProducts(res.items)
      setTotal(res.total)
    } catch (e: any) {
      message.error(e.message || 'Failed to load products')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadProducts()
  }, [page, inStockOnly])

  const handleSearch = () => {
    setPage(1)
    loadProducts()
  }

  const handleAddToCart = (product: Product) => {
    addToCart(product, product.moq)
    message.success(`Added ${product.name} to cart (MOQ: ${product.moq})`)
  }

  return (
    <div>
      <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>Wholesale Catalog</Title>
          <Text type="secondary">Browse products with your exclusive wholesale pricing</Text>
        </div>
      </div>

      <Card style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <Input
            placeholder="Search by name or SKU"
            prefix={<SearchOutlined />}
            value={search}
            onChange={e => setSearch(e.target.value)}
            onPressEnter={handleSearch}
            style={{ width: 300 }}
            allowClear
          />
          <Select
            placeholder="Category"
            value={category}
            onChange={v => { setCategory(v); setPage(1) }}
            style={{ width: 180 }}
            allowClear
            options={[
              { value: 'Tents', label: 'Tents' },
              { value: 'Lighting', label: 'Lighting' },
              { value: 'Backpacks', label: 'Backpacks' },
              { value: 'Cookware', label: 'Cookware' },
              { value: 'Furniture', label: 'Furniture' },
              { value: 'Accessories', label: 'Accessories' },
            ]}
          />
          <Select
            placeholder="Availability"
            value={inStockOnly ? 'in_stock' : undefined}
            onChange={v => { setInStockOnly(v === 'in_stock'); setPage(1) }}
            style={{ width: 150 }}
            allowClear
            options={[{ value: 'in_stock', label: 'In Stock Only' }]}
          />
          <Button type="primary" onClick={handleSearch}>Search</Button>
        </div>
      </Card>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>
      ) : products.length === 0 ? (
        <Empty description="No products found" />
      ) : (
        <>
          <Row gutter={[16, 16]}>
            {products.map(product => (
              <Col xs={24} sm={12} md={8} lg={6} key={product.id}>
                <Card
                  hoverable
                  actions={[
                    <Button
                      type="primary"
                      icon={<ShoppingCartOutlined />}
                      onClick={() => handleAddToCart(product)}
                      disabled={!product.in_stock}
                      block
                    >
                      Add to Cart
                    </Button>,
                  ]}
                >
                  <div
                    onClick={() => { navigateTo(`/product/${product.id}`) }}
                    style={{ cursor: 'pointer' }}
                  >
                    <div style={{
                      height: 160,
                      background: '#f0f0f0',
                      borderRadius: 4,
                      marginBottom: 12,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      overflow: 'hidden',
                    }}>
                      {product.images && product.images.length > 0 ? (
                        <img src={product.images[0]} alt={product.name} style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'cover' }} />
                      ) : (
                        <Text type="secondary">No Image</Text>
                      )}
                    </div>
                    <Text strong style={{ fontSize: 14, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden', minHeight: 40 }}>
                      {product.name}
                    </Text>
                    <div style={{ marginTop: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <Text style={{ color: '#1677ff', fontSize: 18, fontWeight: 600 }}>
                          ${product.wholesale_price.toFixed(2)}
                        </Text>
                        {product.retail_price && (
                          <Text delete type="secondary" style={{ fontSize: 12, marginLeft: 6 }}>
                            ${product.retail_price.toFixed(2)}
                          </Text>
                        )}
                      </div>
                      <Tag color={product.in_stock ? 'green' : 'red'}>
                        {product.in_stock ? 'In Stock' : 'Out of Stock'}
                      </Tag>
                    </div>
                    <div style={{ marginTop: 4 }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        MOQ: {product.moq} | SKU: {product.sku}
                      </Text>
                    </div>
                  </div>
                </Card>
              </Col>
            ))}
          </Row>
          <div style={{ textAlign: 'center', marginTop: 24 }}>
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
    </div>
  )
}
