import { useState, useEffect, lazy, Suspense } from 'react'
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
  ShopOutlined,
  RocketOutlined,
  UserOutlined,
  GiftOutlined,
  CustomerServiceOutlined,
  FundOutlined,
  ApiOutlined,
  ThunderboltOutlined,
  SafetyCertificateOutlined,
  AccountBookOutlined,
} from '@ant-design/icons'
// 懒加载页面组件（减少初始 bundle 体积）
const DashboardPage = lazy(() => import('./pages/Dashboard'))
const AlertsPage = lazy(() => import('./pages/Alerts'))
const InventoryPage = lazy(() => import('./pages/Inventory'))
const NewtonSourcingPage = lazy(() => import('./pages/NewtonSourcing'))
const ProcurementWorkbenchPage = lazy(() => import('./pages/ProcurementWorkbench'))
const ProductAnalysisPage = lazy(() => import('./pages/ProductAnalysis'))
const MainImageGeneratorPage = lazy(() => import('./pages/MainImageGenerator'))
const ImageStudioPage = lazy(() => import('./pages/ImageStudio'))
const ProductPipelinePage = lazy(() => import('./pages/ProductPipeline'))
const ProductsPage = lazy(() => import('./pages/Products'))
const OrdersPage = lazy(() => import('./pages/Orders'))
const CustomersPage = lazy(() => import('./pages/Customers'))
const MarketingPage = lazy(() => import('./pages/Marketing'))
const LogisticsPage = lazy(() => import('./pages/Logistics'))
const TicketsPage = lazy(() => import('./pages/Tickets'))
const FinancePage = lazy(() => import('./pages/Finance'))
const SuppliersPage = lazy(() => import('./pages/Suppliers'))
const SettingsPage = lazy(() => import('./pages/Settings'))
const LogsPage = lazy(() => import('./pages/Logs'))
const ApiManagementPage = lazy(() => import('./pages/ApiManagement'))
const ProductListingPage = lazy(() => import('./pages/ProductListing'))
const WarehousePage = lazy(() => import('./pages/Warehouse'))
const CRMPage = lazy(() => import('./pages/CRM'))
const FinanceReportPage = lazy(() => import('./pages/FinanceReport'))
const ModulePage = lazy(() => import('./pages/ModulePage'))
// P0-P3 新页面
const SourcingPage = lazy(() => import('./pages/Sourcing'))
const PurchaseAutomationPage = lazy(() => import('./pages/PurchaseAutomation'))
const WeeklyReportPage = lazy(() => import('./pages/WeeklyReport'))
const OverseasWarehousePage = lazy(() => import('./pages/OverseasWarehouse'))
const ContentGeneratorPage = lazy(() => import('./pages/ContentGenerator'))
const SEOPage = lazy(() => import('./pages/SEO'))
const EDMPage = lazy(() => import('./pages/EDM'))
const ActivityPlannerPage = lazy(() => import('./pages/ActivityPlanner'))
const InfluencerPage = lazy(() => import('./pages/Influencer'))
const CostModelPage = lazy(() => import('./pages/CostModel'))
const ListingLocalizationPage = lazy(() => import('./pages/ListingLocalization'))
const CustomerTemplatesPage = lazy(() => import('./pages/CustomerTemplates'))
const B2BAgentsPage = lazy(() => import('./pages/B2BAgents'))
const AgentSuggestionsPage = lazy(() => import('./pages/AgentSuggestions'))
const AgentMonitorPage = lazy(() => import('./pages/AgentMonitor'))
const MemoryReviewPage = lazy(() => import('./pages/MemoryReview'))
const SettlementsPage = lazy(() => import('./pages/Settlements'))
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
  | 'activity-planner'
  | 'influencer'
  | 'listing-localization'
  | 'customer-templates'
  | 'newton-sourcing'
  | 'procurement'
  | 'product-analysis'
  | 'main-image-generator'
  | 'image-studio'
  | 'product-pipeline'
  | 'products'
  | 'orders'
  | 'customers'
  | 'marketing'
  | 'logistics'
  | 'tickets'
  | 'finance'
  | 'suppliers'
  | 'settings'
  | 'logs'
  | 'api-management'
  | 'product-listing'
  | 'warehouse'
  | 'crm'
  | 'finance-report'
  | 'agent-suggestions'
  | 'agent-monitor'
  | 'memory-review'
  | 'settlements'

const menuItems = [
  { key: 'dashboard', icon: <DashboardOutlined />, label: '经营看板' },
  { key: 'alerts', icon: <AlertOutlined />, label: '预警中心', dynamicBadge: 'alerts' },
  { key: 'agent-suggestions', icon: <RobotOutlined />, label: 'AI建议审批', dynamicBadge: 'pending' },
  { key: 'agent-monitor', icon: <ThunderboltOutlined />, label: 'Agent监控' },
  { key: 'memory-review', icon: <SafetyCertificateOutlined />, label: '记忆审核' },
  { key: 'settlements', icon: <AccountBookOutlined />, label: '回款台账' },
  {
    key: 'group-supply',
    icon: <ShoppingCartOutlined />,
    label: '供应链',
    children: [
      { key: 'sourcing', icon: <ShoppingOutlined />, label: '选品管理' },
      { key: 'suppliers', icon: <ShopOutlined />, label: '供应商管理' },
      { key: 'newton-sourcing', icon: <RobotOutlined />, label: '牛顿AI选品' },
      { key: 'product-analysis', icon: <RobotOutlined />, label: 'AI产品分析' },
      { key: 'product-pipeline', icon: <RocketOutlined />, label: '产品工作流' },
      { key: 'product-listing', icon: <ShoppingOutlined />, label: '商品上架' },
      { key: 'products', icon: <FileTextOutlined />, label: '产品管理' },
      { key: 'orders', icon: <ShoppingCartOutlined />, label: '订单管理' },
      { key: 'customers', icon: <UserOutlined />, label: '客户管理' },
      { key: 'cost', icon: <DollarOutlined />, label: '成本模型' },
      { key: 'purchase', icon: <ShoppingCartOutlined />, label: '采购自动化' },
      { key: 'procurement', icon: <ShoppingCartOutlined />, label: '代采工作台' },
      { key: 'logistics', icon: <TruckOutlined />, label: '物流监控' },
    ],
  },
  {
    key: 'group-marketing',
    icon: <MailOutlined />,
    label: '营销增长',
    children: [
      { key: 'marketing', icon: <GiftOutlined />, label: '营销活动' },
      { key: 'content', icon: <FileTextOutlined />, label: '内容生成' },
      { key: 'seo', icon: <SearchOutlined />, label: 'SEO基建' },
      { key: 'edm', icon: <MailOutlined />, label: 'EDM营销' },
      { key: 'image-studio', icon: <PictureOutlined />, label: 'AI生图工作台' },
      { key: 'main-image-generator', icon: <PictureOutlined />, label: '电商主图生产器' },
      { key: 'activity-planner', icon: <CalendarOutlined />, label: '活动策划' },
      { key: 'influencer', icon: <TeamOutlined />, label: '达人/KOL运营' },
      { key: 'listing-localization', icon: <GlobalOutlined />, label: '多语言Listing' },
      { key: 'customer-templates', icon: <MessageOutlined />, label: '客服话术模板' },
      { key: 'tickets', icon: <CustomerServiceOutlined />, label: '客服工单' },
    ],
  },
  {
    key: 'group-analytics',
    icon: <BarChartOutlined />,
    label: '经营分析',
    children: [
      { key: 'reports', icon: <BarChartOutlined />, label: '统一看板' },
      { key: 'finance', icon: <FundOutlined />, label: '财务对账' },
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
  { key: 'logs', icon: <FileTextOutlined />, label: '操作日志' },
  { key: 'api-management', icon: <ApiOutlined />, label: 'API管理' },
  { key: 'warehouse', icon: <DatabaseOutlined />, label: '物流仓配' },
  { key: 'crm', icon: <TeamOutlined />, label: '客户CRM' },
  { key: 'finance-report', icon: <BarChartOutlined />, label: '财务报表' },
]

const pageTitles: Record<MenuKey, string> = {
  dashboard: '经营看板',
  alerts: '预警中心',
  sourcing: '选品管理',
  'newton-sourcing': '牛顿AI智能选品',
  'product-analysis': 'AI产品分析与Prompt生成',
  'product-pipeline': '产品端到端工作流',
  'products': '产品管理',
  'orders': '订单管理',
  'customers': '客户管理',
  'marketing': '营销活动',
  'main-image-generator': '电商主图生产器',
  'image-studio': 'AI生图工作台',
  cost: '成本模型',
  purchase: '采购自动化',
  procurement: '代采工作台',
  logistics: '物流监控',
  tickets: '客服工单',
  finance: '财务对账',
  suppliers: '供应商管理',
  content: '内容生成系统',
  seo: 'SEO基建',
  edm: 'EDM营销自动化',
  reports: '统一经营看板',
  'weekly-report': 'AI经营周报',
  inventory: '多仓库库存管理',
  overseas: '海外仓对接',
  b2b: 'B2B代理商管理',
  'activity-planner': '电商活动策划',
  influencer: '达人/KOL运营',
  'listing-localization': '多语言Listing本地化',
  'customer-templates': '客服话术模板',
  settings: '系统设置',
  logs: '操作日志',
  'api-management': 'API管理',
  'product-listing': '商品上架自动化',
  warehouse: '物流仓配管理',
  crm: '客户CRM系统',
  'finance-report': '财务报表系统',
  'agent-monitor': 'Agent 运行监控',
  'memory-review': '成长记忆审核',
  'settlements': '回款台账',
}

function App() {
  const [collapsed, setCollapsed] = useState(false)
  const [activeKey, setActiveKey] = useState<MenuKey>('dashboard')
  const [pendingCount, setPendingCount] = useState(0)
  const [alertsCount, setAlertsCount] = useState(0)
  const {
    token: { colorBgContainer, borderRadiusLG },
  } = theme.useToken()

  // 动态获取待审批建议数量（导航角标）
  useEffect(() => {
    const fetchPending = async () => {
      try {
        const res = await fetch('/api/v1/agent-suggestions?status=pending_approval&limit=1')
        if (res.ok) {
          const data = await res.json()
          const total = data.total ?? data.items?.length ?? 0
          setPendingCount(total)
        }
      } catch {
        // 静默失败，角标显示 0
      }
      try {
        const res2 = await fetch('/api/v1/alerts?status=open&limit=1')
        if (res2.ok) {
          const data2 = await res2.json()
          const total2 = data2.total ?? data2.items?.length ?? 0
          setAlertsCount(total2)
        }
      } catch {
        // 静默失败
      }
    }
    fetchPending()
    // 每 60 秒刷新一次
    const timer = setInterval(fetchPending, 60000)
    return () => clearInterval(timer)
  }, [])

  const renderContent = () => {
    const content = (() => {
      switch (activeKey) {
        case 'dashboard':
        case 'reports':
          return <DashboardPage />
        case 'alerts':
          return <AlertsPage />
        case 'agent-suggestions':
          return <AgentSuggestionsPage />
        case 'agent-monitor':
          return <AgentMonitorPage />
        case 'memory-review':
          return <MemoryReviewPage />
        case 'settlements':
          return <SettlementsPage />
        case 'inventory':
          return <InventoryPage />
        case 'newton-sourcing':
          return <NewtonSourcingPage />
        case 'product-analysis':
          return <ProductAnalysisPage />
        case 'product-pipeline':
          return <ProductPipelinePage />
        case 'products':
          return <ProductsPage />
        case 'orders':
          return <OrdersPage />
        case 'customers':
          return <CustomersPage />
        case 'marketing':
          return <MarketingPage />
        case 'logistics':
          return <LogisticsPage />
        case 'tickets':
          return <TicketsPage />
        case 'finance':
          return <FinancePage />
        case 'suppliers':
          return <SuppliersPage />
        case 'settings':
          return <SettingsPage />
        case 'logs':
          return <LogsPage />
        case 'api-management':
          return <ApiManagementPage />
        case 'product-listing':
          return <ProductListingPage />
        case 'warehouse':
          return <WarehousePage />
        case 'crm':
          return <CRMPage />
        case 'finance-report':
          return <FinanceReportPage />
        case 'main-image-generator':
          return <MainImageGeneratorPage />
        case 'image-studio':
          return <ImageStudioPage />
        case 'procurement':
          return <ProcurementWorkbenchPage />
        // P0-P3 新页面路由
        case 'sourcing':
          return <SourcingPage />
        case 'purchase':
          return <PurchaseAutomationPage />
        case 'weekly-report':
          return <WeeklyReportPage />
        case 'overseas':
          return <OverseasWarehousePage />
        case 'content':
          return <ContentGeneratorPage />
        case 'seo':
          return <SEOPage />
        case 'edm':
          return <EDMPage />
        case 'activity-planner':
          return <ActivityPlannerPage />
        case 'influencer':
          return <InfluencerPage />
        case 'cost':
          return <CostModelPage />
        case 'listing-localization':
          return <ListingLocalizationPage />
        case 'customer-templates':
          return <CustomerTemplatesPage />
        case 'b2b':
          return <B2BAgentsPage />
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
          items={menuItems.map(item => {
            const badgeCount = item.dynamicBadge === 'pending' ? pendingCount : (item.dynamicBadge === 'alerts' ? alertsCount : item.badge)
            return {
              ...item,
              label: badgeCount ? (
                <Space>
                  {item.label}
                  <Badge count={badgeCount} size="small" />
                </Space>
              ) : item.label,
            }
          })}
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
