import React, { useState, useEffect, lazy, Suspense } from 'react'
import { Layout, Menu, Badge, Button, Typography, Space, Dropdown, Spin } from 'antd'
import {
  ShoppingOutlined,
  ShoppingCartOutlined,
  UserOutlined,
  LogoutOutlined,
  HomeOutlined,
  FileTextOutlined,
} from '@ant-design/icons'
import { AuthProvider, useAuth } from './auth'
import { CartProvider, useCart } from './cart'

// M2.5.7: route-level code splitting. Each page is a separate chunk so the
// public showcase and the authenticated portal don't ship in one 1.1MB bundle.
const LoginPage = lazy(() => import('./pages/Login'))
const ApplyPage = lazy(() => import('./pages/Apply'))
const ProductsPage = lazy(() => import('./pages/Products'))
const ProductDetailPage = lazy(() => import('./pages/ProductDetail'))
const CartPage = lazy(() => import('./pages/Cart'))
const OrdersPage = lazy(() => import('./pages/Orders'))
const OrderDetailPage = lazy(() => import('./pages/OrderDetail'))
const AccountPage = lazy(() => import('./pages/Account'))
// Public (no-login) showcase layer
const PublicHome = lazy(() => import('./pages/public/PublicHome'))
const PublicCatalog = lazy(() => import('./pages/public/PublicCatalog'))
const PublicProductDetail = lazy(() => import('./pages/public/PublicProductDetail'))
const About = lazy(() => import('./pages/public/About'))
const Cooperation = lazy(() => import('./pages/public/Cooperation'))
const RequestQuote = lazy(() => import('./pages/public/RequestQuote'))

const PageFallback = (
  <div style={{ display: 'flex', justifyContent: 'center', padding: '48px 0' }}>
    <Spin size="large" />
  </div>
)

const { Header, Content, Footer } = Layout
const { Title, Text } = Typography

type Route =
  // Public showcase (no login required)
  | { name: 'home' }
  | { name: 'public-products' }
  | { name: 'public-product-detail'; slug: string }
  | { name: 'about' }
  | { name: 'cooperation' }
  | { name: 'request-quote'; prefill?: string }
  // Public application / login
  | { name: 'login' }
  | { name: 'apply' }
  // Authenticated wholesale portal (moved under /portal/*)
  | { name: 'portal-products' }
  | { name: 'portal-product-detail'; productId: string }
  | { name: 'portal-cart' }
  | { name: 'portal-orders' }
  | { name: 'portal-order-detail'; orderId: string }
  | { name: 'portal-account' }

const PUBLIC_ROUTES: Route['name'][] = [
  'home',
  'public-products',
  'public-product-detail',
  'about',
  'cooperation',
  'request-quote',
]

function parsePath(): Route {
  const path = window.location.pathname.replace(/^\//, '')
  const [seg, ...rest] = path.split('/')
  switch (seg) {
    case '':
      return { name: 'home' }
    case 'products':
      if (rest[0]) return { name: 'public-product-detail', slug: rest[0] }
      return { name: 'public-products' }
    case 'about':
      return { name: 'about' }
    case 'cooperation':
      return { name: 'cooperation' }
    case 'request-a-quote':
      return {
        name: 'request-quote',
        prefill: new URLSearchParams(window.location.search).get('product') || undefined,
      }
    case 'login':
      return { name: 'login' }
    case 'apply':
      return { name: 'apply' }
    case 'portal': {
      const sub = rest[0]
      if (sub === 'product') return { name: 'portal-product-detail', productId: rest[1] || '' }
      if (sub === 'cart') return { name: 'portal-cart' }
      if (sub === 'orders') {
        if (rest[1]) return { name: 'portal-order-detail', orderId: rest[1] }
        return { name: 'portal-orders' }
      }
      if (sub === 'account') return { name: 'portal-account' }
      return { name: 'portal-products' }
    }
    default:
      return { name: 'home' }
  }
}

function navigate(route: string) {
  const url = route.startsWith('/') ? route : '/' + route
  window.history.pushState({}, '', url)
  window.dispatchEvent(new PopStateEvent('popstate'))
}

function isPublic(name: Route['name']): boolean {
  return PUBLIC_ROUTES.includes(name)
}

function AppShell() {
  const { agent, loading, logout } = useAuth()
  const { totalItems } = useCart()
  const [route, setRoute] = useState<Route>(parsePath())

  useEffect(() => {
    const onPopState = () => setRoute(parsePath())
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  // Authenticated partners landing on the public root are taken to the
  // wholesale portal (public root stays a no-price showcase for anonymous visitors).
  useEffect(() => {
    if (!loading && agent && route.name === 'home') {
      navigate('/portal/products')
    }
  }, [loading, agent, route.name])

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin size="large" />
      </div>
    )
  }

  // Public showcase layer — never gated behind login.
  if (isPublic(route.name)) {
    return (
      <Suspense fallback={PageFallback}>
        {route.name === 'home' && <PublicHome />}
        {route.name === 'public-products' && <PublicCatalog />}
        {route.name === 'public-product-detail' && <PublicProductDetail slug={route.slug} />}
        {route.name === 'about' && <About />}
        {route.name === 'cooperation' && <Cooperation />}
        {route.name === 'request-quote' && <RequestQuote prefillProduct={route.prefill} />}
      </Suspense>
    )
  }

  // Application page does not require login.
  if (route.name === 'apply') {
    return (
      <Suspense fallback={PageFallback}>
        <ApplyPage />
      </Suspense>
    )
  }

  // Authenticated wholesale portal requires a valid partner session.
  if (!agent || route.name === 'login') {
    return (
      <Suspense fallback={PageFallback}>
        <LoginPage />
      </Suspense>
    )
  }

  const menuItems = [
    { key: '/portal/products', icon: <HomeOutlined />, label: 'Products' },
    { key: '/portal/orders', icon: <FileTextOutlined />, label: 'My Orders' },
    { key: '/portal/account', icon: <UserOutlined />, label: 'Account' },
  ]

  const userMenu = {
    items: [
      { key: 'account', icon: <UserOutlined />, label: 'Account', onClick: () => navigate('/portal/account') },
      { type: 'divider' as const },
      { key: 'showcase', icon: <HomeOutlined />, label: 'Public Showcase', onClick: () => navigate('/') },
      { type: 'divider' as const },
      { key: 'logout', icon: <LogoutOutlined />, label: 'Sign Out', onClick: logout },
    ],
  }

  const selectedKey =
    route.name === 'portal-product-detail'
      ? '/portal/products'
      : route.name === 'portal-order-detail'
      ? '/portal/orders'
      : `/${route.name.replace('portal-', 'portal/')}`

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: '#001529', padding: '0 24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 32 }}>
          <div onClick={() => navigate('/portal/products')} style={{ cursor: 'pointer', color: '#fff', fontSize: 20, fontWeight: 600 }}>
            <ShoppingOutlined style={{ marginRight: 8 }} />
            Nuotao B2B
          </div>
          <Menu
            theme="dark"
            mode="horizontal"
            selectedKeys={[selectedKey]}
            items={menuItems}
            onClick={({ key }) => navigate(key)}
            style={{ background: 'transparent', border: 'none', minWidth: 300 }}
          />
        </div>
        <Space size="large">
          <Badge count={totalItems} size="small">
            <Button type="text" icon={<ShoppingCartOutlined />} onClick={() => navigate('/portal/cart')} style={{ color: '#fff' }}>
              Cart
            </Button>
          </Badge>
          <Dropdown menu={userMenu} placement="bottomRight">
            <Button type="text" icon={<UserOutlined />} style={{ color: '#fff' }}>
              {agent.company_name}
            </Button>
          </Dropdown>
        </Space>
      </Header>

      <Content style={{ padding: '24px', maxWidth: 1400, margin: '0 auto', width: '100%' }}>
        <Suspense fallback={PageFallback}>
          {route.name === 'portal-products' && <ProductsPage />}
          {route.name === 'portal-product-detail' && <ProductDetailPage productId={route.productId} />}
          {route.name === 'portal-cart' && <CartPage />}
          {route.name === 'portal-orders' && <OrdersPage />}
          {route.name === 'portal-order-detail' && <OrderDetailPage orderId={route.orderId} />}
          {route.name === 'portal-account' && <AccountPage />}
        </Suspense>
      </Content>

      <Footer style={{ textAlign: 'center', background: '#f5f5f5' }}>
        <Text type="secondary">
          © 2026 Nuotao Outdoor. B2B Wholesale Portal. For authorized partners only.
        </Text>
      </Footer>
    </Layout>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <CartProvider>
        <AppShell />
      </CartProvider>
    </AuthProvider>
  )
}