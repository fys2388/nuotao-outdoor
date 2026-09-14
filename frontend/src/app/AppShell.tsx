import { useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  Avatar,
  Badge,
  Button,
  Drawer,
  Dropdown,
  Grid,
  Layout,
  Menu,
  Segmented,
  Space,
  Tag,
  Typography,
  type MenuProps,
} from 'antd'
import {
  BellOutlined,
  GlobalOutlined,
  LoginOutlined,
  LogoutOutlined,
  MenuOutlined,
  SafetyCertificateOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { api, request } from '../api/client'
import { useAuth } from '../auth/AuthProvider'
import {
  filterNavigationGroups,
  findNavigationItem,
  navigationGroups,
  standaloneGovernanceItems,
  standaloneTopItems,
  type BadgeKey,
  type BusinessScope,
  type NavigationItem,
} from '../config/navigation'

const { Header, Sider, Content } = Layout
const { Text } = Typography
const { useBreakpoint } = Grid

interface BadgeState {
  alerts: number
  pending: number
  b2bPending: number
}

function itemLabel(item: NavigationItem, badgeCount: number): ReactNode {
  return (
    <Space size={6}>
      <span>{item.label}</span>
      {item.status === 'planned' && <Tag className="nav-status-tag">待接入</Tag>}
      {badgeCount > 0 && <Badge count={badgeCount} size="small" overflowCount={99} />}
    </Space>
  )
}

function itemToMenu(item: NavigationItem, badges: BadgeState): NonNullable<MenuProps['items']>[number] {
  return {
    key: item.key,
    icon: item.icon,
    label: itemLabel(item, item.badge ? badges[item.badge] : 0),
  }
}

export default function AppShell() {
  const location = useLocation()
  const navigate = useNavigate()
  const screens = useBreakpoint()
  const { user, authenticated, logout } = useAuth()
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [scope, setScope] = useState<BusinessScope>(() => {
    const saved = localStorage.getItem('business_scope')
    return saved === 'b2c' || saved === 'b2b' ? saved : 'all'
  })
  const [badges, setBadges] = useState<BadgeState>({
    alerts: 0,
    pending: 0,
    b2bPending: 0,
  })

  const currentItem = findNavigationItem(location.pathname)

  useEffect(() => {
    const loadBadges = async () => {
      const next: BadgeState = { alerts: 0, pending: 0, b2bPending: 0 }
      const [suggestions, alerts, b2b] = await Promise.allSettled([
        request<{ total?: number; items?: unknown[] }>(
          '/agent-suggestions?status=pending_approval&limit=1',
        ),
        api.getAlerts() as Promise<{ total?: number; alerts?: unknown[] }>,
        authenticated
          ? (api.getB2BStats() as Promise<{ pending_agents?: number }>)
          : Promise.resolve({ pending_agents: 0 }),
      ])

      if (suggestions.status === 'fulfilled') {
        next.pending = suggestions.value.total ?? suggestions.value.items?.length ?? 0
      }
      if (alerts.status === 'fulfilled') {
        next.alerts = alerts.value.total ?? alerts.value.alerts?.length ?? 0
      }
      if (b2b.status === 'fulfilled') {
        next.b2bPending = b2b.value.pending_agents ?? 0
      }
      setBadges(next)
    }

    void loadBadges()
    const timer = window.setInterval(() => void loadBadges(), 60000)
    return () => window.clearInterval(timer)
  }, [authenticated])

  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  const menuItems = useMemo<MenuProps['items']>(() => {
    const top = standaloneTopItems.map((item) => itemToMenu(item, badges))
    const groups = filterNavigationGroups(scope).map((group) => ({
      key: group.key,
      icon: group.icon,
      label: group.label,
      children: group.children.map((item) => itemToMenu(item, badges)),
    }))
    const governance = standaloneGovernanceItems.map((item) => itemToMenu(item, badges))

    return [
      ...top,
      { type: 'divider' as const },
      ...groups,
      { type: 'divider' as const },
      ...governance,
    ]
  }, [badges, scope])

  const openKeys = useMemo(() => {
    return navigationGroups
      .filter((group) => group.children.some((item) => item.key === currentItem?.key))
      .map((group) => group.key)
  }, [currentItem?.key])

  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    const target = [...standaloneTopItems, ...navigationGroups.flatMap((group) => group.children), ...standaloneGovernanceItems]
      .find((item) => item.key === key)
    if (target) navigate(target.path)
  }

  const handleScopeChange = (value: string | number) => {
    const nextScope = value as BusinessScope
    setScope(nextScope)
    localStorage.setItem('business_scope', nextScope)
    if (nextScope === 'b2c' && location.pathname.startsWith('/b2b')) {
      navigate('/b2c/overview')
    }
    if (nextScope === 'b2b' && location.pathname.startsWith('/b2c')) {
      navigate('/b2b/overview')
    }
  }

  const accountMenu: MenuProps = {
    items: authenticated
      ? [
          { key: 'role', label: `${user?.username || '管理员'} · ${user?.role || 'user'}`, disabled: true },
          { type: 'divider' },
          {
            key: 'logout',
            icon: <LogoutOutlined />,
            label: '退出登录',
            onClick: () => {
              logout()
              navigate('/login')
            },
          },
        ]
      : [
          {
            key: 'login',
            icon: <LoginOutlined />,
            label: '登录管理账号',
            onClick: () => navigate(`/login?next=${encodeURIComponent(location.pathname)}`),
          },
        ],
  }

  const navigationMenu = (
    <>
      <button
        type="button"
        className="app-brand"
        onClick={() => navigate('/dashboard')}
        aria-label="返回经营总览"
      >
        <div className="app-brand__mark">N</div>
        <div className="app-brand__copy">
          <strong>Nuotao AI OS</strong>
          <span>跨境经营操作系统</span>
        </div>
      </button>
      <Menu
        className="main-navigation"
        theme="dark"
        mode="inline"
        selectedKeys={currentItem ? [currentItem.key] : []}
        defaultOpenKeys={openKeys}
        items={menuItems}
        onClick={handleMenuClick}
      />
    </>
  )

  const desktopSider = screens.lg && (
    <Sider
      className="app-sider"
      width={248}
      collapsedWidth={78}
      collapsible
      collapsed={collapsed}
      onCollapse={setCollapsed}
      trigger={null}
    >
      {navigationMenu}
    </Sider>
  )

  return (
    <Layout className="app-layout">
      {desktopSider}
      {!screens.lg && (
        <Drawer
          className="mobile-navigation-drawer"
          placement="left"
          size={286}
          open={mobileOpen}
          onClose={() => setMobileOpen(false)}
          styles={{ body: { padding: 0, background: '#173c35' } }}
          closable={false}
        >
          {navigationMenu}
        </Drawer>
      )}

      <Layout>
        <Header className="app-header">
          <div className="app-header__left">
            {!screens.lg && (
              <Button
                className="mobile-menu-button"
                type="text"
                icon={<MenuOutlined />}
                onClick={() => setMobileOpen(true)}
                aria-label="打开导航"
              />
            )}
            <div className="page-context">
              <Text type="secondary">当前模块</Text>
              <strong>{currentItem?.label || '经营总览'}</strong>
            </div>
          </div>

          <div className="app-header__right">
            <Segmented
              className="business-scope-control"
              value={scope}
              onChange={handleScopeChange}
              options={[
                { value: 'all', label: '全盘' },
                { value: 'b2c', label: 'B2C' },
                { value: 'b2b', label: 'B2B' },
              ]}
            />
            <Tag className="environment-tag" icon={<GlobalOutlined />}>
              {import.meta.env.MODE === 'production' ? 'Production' : 'Local'}
            </Tag>
            <Button
              type="text"
              icon={<BellOutlined />}
              onClick={() => navigate('/alerts')}
              aria-label="业务预警"
            />
            <Dropdown menu={accountMenu} placement="bottomRight" trigger={['click']}>
              <Button type="text" className="account-button">
                <Avatar size={28} icon={authenticated ? <UserOutlined /> : <SafetyCertificateOutlined />} />
                <span>{authenticated ? user?.username : '未登录'}</span>
              </Button>
            </Dropdown>
          </div>
        </Header>

        <Content className="app-content">
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
