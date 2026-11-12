import React from 'react'
import { Layout, Button, Typography } from 'antd'
import { navigate } from '../../api/publicApi'

const { Header, Content, Footer } = Layout
const { Text } = Typography

// Shared brand palette for the public B2B showcase.
export const COLORS = {
  forest: '#2E5E3A',
  orange: '#E8743B',
  charcoal: '#2B2B2B',
  white: '#FAFAF7',
}

interface NavItem {
  label: string
  path: string
}

const NAV_ITEMS: NavItem[] = [
  { label: 'Home', path: '/' },
  { label: 'Products', path: '/products' },
  { label: 'About', path: '/about' },
  { label: 'Cooperation', path: '/cooperation' },
]

function isNavActive(itemPath: string, currentPath: string): boolean {
  if (itemPath === '/') return currentPath === '/'
  return currentPath === itemPath || currentPath.startsWith(itemPath + '/')
}

export default function PublicLayout({
  children,
  currentPath,
}: {
  children: React.ReactNode
  currentPath: string
}) {
  return (
    <Layout style={{ minHeight: '100vh', background: COLORS.white }}>
      <Header
        style={{
          background: COLORS.white,
          borderBottom: '1px solid #E0E0DA',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 32px',
          height: 64,
          lineHeight: 'normal',
        }}
      >
        <div
          onClick={() => navigate('/')}
          style={{
            cursor: 'pointer',
            color: COLORS.forest,
            fontSize: 20,
            fontWeight: 700,
            letterSpacing: 0.2,
            whiteSpace: 'nowrap',
          }}
        >
          Nuotao Outdoor
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 28 }}>
          <nav style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
            {NAV_ITEMS.map((item) => {
              const active = isNavActive(item.path, currentPath)
              return (
                <span
                  key={item.path}
                  onClick={() => navigate(item.path)}
                  style={{
                    cursor: 'pointer',
                    fontSize: 15,
                    fontWeight: active ? 600 : 400,
                    color: active ? COLORS.forest : COLORS.charcoal,
                    borderBottom: active ? `2px solid ${COLORS.orange}` : '2px solid transparent',
                    paddingBottom: 4,
                  }}
                >
                  {item.label}
                </span>
              )
            })}
          </nav>

          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <Button
              type="primary"
              onClick={() => navigate('/request-a-quote')}
              style={{ background: COLORS.forest, borderColor: COLORS.forest, fontWeight: 600 }}
            >
              Request a Quote
            </Button>
            <span
              onClick={() => navigate('/login')}
              style={{ cursor: 'pointer', fontSize: 14, color: COLORS.charcoal }}
            >
              Partner Login
            </span>
          </div>
        </div>
      </Header>

      <Content style={{ background: COLORS.white }}>{children}</Content>

      <Footer
        style={{
          background: COLORS.charcoal,
          color: '#EDEDE6',
          padding: '40px 32px 24px',
        }}
      >
        <div
          style={{
            maxWidth: 1200,
            margin: '0 auto',
            display: 'flex',
            flexWrap: 'wrap',
            justifyContent: 'space-between',
            gap: 32,
          }}
        >
          <div style={{ maxWidth: 360 }}>
            <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 8, color: '#FFFFFF' }}>
              Nuotao Outdoor
            </div>
            <Text style={{ color: '#C9C9C1', fontSize: 14 }}>
              Practical camping and hiking products for retail and wholesale buyers.
            </Text>
          </div>

          <div>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, color: '#FFFFFF' }}>
              Links
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <span
                onClick={() => navigate('/apply')}
                style={{ cursor: 'pointer', fontSize: 14, color: '#C9C9C1' }}
              >
                Wholesale / B2B
              </span>
              <span
                onClick={() => navigate('/login')}
                style={{ cursor: 'pointer', fontSize: 14, color: '#C9C9C1' }}
              >
                Already a partner? Log in
              </span>
              <span
                onClick={() => navigate('/request-a-quote')}
                style={{ cursor: 'pointer', fontSize: 14, color: '#C9C9C1' }}
              >
                Request a Quote
              </span>
            </div>
          </div>
        </div>

        <div
          style={{
            maxWidth: 1200,
            margin: '24px auto 0',
            borderTop: '1px solid #44443F',
            paddingTop: 16,
          }}
        >
          <Text style={{ color: '#9C9C94', fontSize: 13 }}>© 2026 Nuotao Outdoor</Text>
        </div>
      </Footer>
    </Layout>
  )
}
