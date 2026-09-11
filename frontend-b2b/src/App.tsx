import React, { useState, useEffect } from 'react'
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
import LoginPage from './pages/Login'
import ApplyPage from './pages/Apply'
import ProductsPage from './pages/Products'
import ProductDetailPage from './pages/ProductDetail'
import CartPage from './pages/Cart'
import OrdersPage from './pages/Orders'
import OrderDetailPage from './pages/OrderDetail'
import AccountPage from './pages/Account'

const { Header, Content, Footer } = Layout
const { Title, Text } = Typography

type Route =
  | { name: 'login' }
  | { name: 'apply' }
  | { name: 'products' }
  | { name: 'product-detail'; productId: string }
  | { name: 'cart' }
  | { name: 'orders' }
  | { name: 'order-detail'; orderId: string }
  | { name: 'account' }

function parsePath(): Route {
  const path = window.location.pathname.replace(/^\//, '') || 'products'
  const [seg, ...rest] = path.split('/')
  switch (seg) {
    case 'login':
      return { name: 'login' }
    case 'apply':
      return { name: 'apply' }
    case 'products':
      return { name: 'products' }
    case 'product':
      return { name: 'product-detail', productId: rest[0] || '' }
    case 'cart':
      return { name: 'cart' }
    case 'orders':
      if (rest[0]) return { name: 'order-detail', orderId: rest[0] }
      return { name: 'orders' }
    case 'account':
      return { name: 'account' }
    default:
      return { name: 'products' }
  }
}

function navigate(route: string) {
  const url = route.startsWith('/') ? route : '/' + route
  window.history.pushState({}, '', url)
  window.dispatchEvent(new PopStateEvent('popstate'))
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

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin size="large" />
      </div>
    )
  }

  // 申请页面不需要登录
  if (route.name === 'apply') {
    return <ApplyPage />
  }

  if (!agent || route.name === 'login') {
    return <LoginPage />
  }

  const menuItems = [
    { key: '/products', icon: <HomeOutlined />, label: 'Products' },
    { key: '/orders', icon: <FileTextOutlined />, label: 'My Orders' },
    { key: '/account', icon: <UserOutlined />, label: 'Account' },
  ]

  const userMenu = {
    items: [
      { key: 'account', icon: <UserOutlined />, label: 'Account', onClick: () => navigate('/account') },
      { type: 'divider' as const },
      { key: 'logout', icon: <LogoutOutlined />, label: 'Sign Out', onClick: logout },
    ],
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: '#001529', padding: '0 24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 32 }}>
          <div onClick={() => navigate('/products')} style={{ cursor: 'pointer', color: '#fff', fontSize: 20, fontWeight: 600 }}>
            <ShoppingOutlined style={{ marginRight: 8 }} />
            Nuotao B2B
          </div>
          <Menu
            theme="dark"
            mode="horizontal"
            selectedKeys={[`/${route.name === 'product-detail' ? 'products' : route.name}`]}
            items={menuItems}
            onClick={({ key }) => navigate(key)}
            style={{ background: 'transparent', border: 'none', minWidth: 300 }}
          />
        </div>
        <Space size="large">
          <Badge count={totalItems} size="small">
            <Button type="text" icon={<ShoppingCartOutlined />} onClick={() => navigate('/cart')} style={{ color: '#fff' }}>
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
        {route.name === 'products' && <ProductsPage />}
        {route.name === 'product-detail' && <ProductDetailPage productId={route.productId} />}
        {route.name === 'cart' && <CartPage />}
        {route.name === 'orders' && <OrdersPage />}
        {route.name === 'order-detail' && <OrderDetailPage orderId={route.orderId} />}
        {route.name === 'account' && <AccountPage />}
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
