import { useState, lazy, Suspense } from 'react'
import { Layout, Menu, theme, Typography, Tag, Space, Badge, Spin } from 'antd'
import {
  DashboardOutlined,
  ShoppingOutlined,
  DollarOutlined,
  ShoppingCartOutlined,
  TruckOutlined,
  FileTextOutlined,
  SearchOutlined,
  MailOutlined,
  BarChartOutlined,
  FileTextOutlined as ReportIcon,
  AlertOutlined,
  DatabaseOutlined,
  GlobalOutlined,
  TeamOutlined,
  SettingOutlined,
  PictureOutlined,
  CalendarOutlined,
  MessageOutlined,
  RobotOutlined,
} from '@ant-design/icons'
// 懒加载页面组件（减少初始 bundle 体积）
const DashboardPage = lazy(() => import('./pages/Dashboard'))
const AlertsPage = lazy(() => import('./pages/Alerts'))
const InventoryPage = lazy(() => import('./pages/Inventory'))
const NewtonSourcingPage = lazy(() => import('./pages/NewtonSourcing'))
const ModulePage = lazy(() => import('./pages/ModulePage'))
import { moduleConfigs } from './pages/moduleConfigs'

// 加载占位组件
const PageLoader = () => (
  <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '60vh' }}>
    <Spin size="large" tip="加载中..." />
  </div>
)

const { Header, Sider, Content } = Layout
const { Title } = Typography

type MenuKey =
  | 'dashboard'
  | 'sourcing'
  | 'cost'
  | 'selection'
  | 'purchase'
  | 'logistics'
  | 'content'
  | 'seo'
  | 'edm'
  | 'reports'
  | 'weekly-report'
  | 'alerts'
  | 'inventory'
  | 'overseas'
  | 'b2b'
  | 'image-gen'
  | 'activity-planner'
  | 'influencer'
  | 'listing-localization'
  | 'customer-templates'
  | 'newton-sourcing'
  | 'settings'

const menuItems = [
  { key: 'dashboard', icon: <DashboardOutlined />, label: '经营看板' },
  { key: 'alerts', icon: <AlertOutlined />, label: '预警中心', badge: 3 },
  {
    key: 'group-supply',
    icon: <ShoppingCartOutlined />,
    label: '供应链',
    children: [
      { key: 'sourcing', icon: <ShoppingOutlined />, label: '选品管理' },
      { key: 'newton-sourcing', icon: <RobotOutlined />, label: '牛顿AI选品' },
      { key: 'cost', icon: <DollarOutlined />, label: '成本模型' },
      { key: 'selection', icon: <BarChartOutlined />, label: 'AI选品建议' },
      { key: 'purchase', icon: <ShoppingCartOutlined />, label: '采购自动化' },
      { key: 'logistics', icon: <TruckOutlined />, label: '物流监控' },
    ],
  },
  {
    key: 'group-marketing',
    icon: <MailOutlined />,
    label: '营销增长',
    children: [
      { key: 'content', icon: <FileTextOutlined />, label: '内容生成' },
      { key: 'seo', icon: <SearchOutlined />, label: 'SEO基建' },
      { key: 'edm', icon: <MailOutlined />, label: 'EDM营销' },
      { key: 'image-gen', icon: <PictureOutlined />, label: '商品图片生成' },
      { key: 'activity-planner', icon: <CalendarOutlined />, label: '活动策划' },
      { key: 'influencer', icon: <TeamOutlined />, label: '达人/KOL运营' },
      { key: 'listing-localization', icon: <GlobalOutlined />, label: '多语言Listing' },
      { key: 'customer-templates', icon: <MessageOutlined />, label: '客服话术模板' },
    ],
  },
  {
    key: 'group-analytics',
    icon: <BarChartOutlined />,
    label: '经营分析',
    children: [
      { key: 'reports', icon: <BarChartOutlined />, label: '统一看板' },
      { key: 'weekly-report', icon: <ReportIcon />, label: 'AI经营周报' },
    ],
  },
  {
    key: 'group-p3',
    icon: <GlobalOutlined />,
    label: 'M5/M6 能力',
    children: [
      { key: 'inventory', icon: <DatabaseOutlined />, label: '多仓库存' },
      { key: 'overseas', icon: <GlobalOutlined />, label: '海外仓对接' },
      { key: 'b2b', icon: <TeamOutlined />, label: 'B2B代理商' },
    ],
  },
  { key: 'settings', icon: <SettingOutlined />, label: '系统设置' },
]

const pageTitles: Record<MenuKey, string> = {
  dashboard: '经营看板',
  alerts: '预警中心',
  sourcing: '选品管理',
  'newton-sourcing': '牛顿AI智能选品',
  cost: '成本模型',
  selection: 'AI选品建议',
  purchase: '采购自动化',
  logistics: '物流监控',
  content: '内容生成系统',
  seo: 'SEO基建',
  edm: 'EDM营销自动化',
  reports: '统一经营看板',
  'weekly-report': 'AI经营周报',
  inventory: '多仓库库存管理',
  overseas: '海外仓对接',
  b2b: 'B2B代理商管理',
  'image-gen': '商品图片生成',
  'activity-planner': '电商活动策划',
  influencer: '达人/KOL运营',
  'listing-localization': '多语言Listing本地化',
  'customer-templates': '客服话术模板',
  settings: '系统设置',
}

function App() {
  const [collapsed, setCollapsed] = useState(false)
  const [activeKey, setActiveKey] = useState<MenuKey>('dashboard')
  const {
    token: { colorBgContainer, borderRadiusLG },
  } = theme.useToken()

  const renderContent = () => {
    const content = (() => {
      switch (activeKey) {
        case 'dashboard':
        case 'reports':
          return <DashboardPage />
        case 'alerts':
          return <AlertsPage />
        case 'inventory':
          return <InventoryPage />
        case 'newton-sourcing':
          return <NewtonSourcingPage />
        default:
          const config = moduleConfigs[activeKey]
          if (config) {
            return <ModulePage config={config} />
          }
          return <div>页面开发中...</div>
      }
    })()
    return <Suspense fallback={<PageLoader />}>{content}</Suspense>
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        width={220}
      >
        <div className="app-logo">
          <span style={{ fontSize: 20 }}>🏕️</span>
          {!collapsed && <span>Nuotao AI OS</span>}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          defaultOpenKeys={['group-supply', 'group-marketing', 'group-analytics', 'group-p3']}
          selectedKeys={[activeKey]}
          onClick={({ key }) => setActiveKey(key as MenuKey)}
          items={menuItems.map(item => ({
            ...item,
            label: item.badge ? (
              <Space>
                {item.label}
                <Badge count={item.badge} size="small" />
              </Space>
            ) : item.label,
          }))}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            padding: '0 24px',
            background: colorBgContainer,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <Title level={4} style={{ margin: 0 }}>
            {pageTitles[activeKey]}
          </Title>
          <Space>
            <Tag color="green">本地开发环境</Tag>
            <Tag color="blue">v0.3.0</Tag>
          </Space>
        </Header>
        <Content
          style={{
            margin: '24px',
            padding: '24px',
            background: colorBgContainer,
            borderRadius: borderRadiusLG,
            minHeight: 280,
          }}
        >
          {renderContent()}
        </Content>
      </Layout>
    </Layout>
  )
}

export default App
