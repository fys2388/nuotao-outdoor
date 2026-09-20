import type { ReactNode } from 'react'
import {
  AlertOutlined,
  ApiOutlined,
  ApartmentOutlined,
  AppstoreOutlined,
  BarChartOutlined,
  BookOutlined,
  CalculatorOutlined,
  CarryOutOutlined,
  ClusterOutlined,
  CompassOutlined,
  CustomerServiceOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  DeploymentUnitOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  FundOutlined,
  GlobalOutlined,
  HistoryOutlined,
  MailOutlined,
  NodeIndexOutlined,
  ProductOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
  ShopOutlined,
  ShoppingCartOutlined,
  ShoppingOutlined,
  SolutionOutlined,
  TeamOutlined,
  ThunderboltOutlined,
  TrophyOutlined,
  TruckOutlined,
  WalletOutlined,
} from '@ant-design/icons'

export type BusinessScope = 'all' | 'b2c' | 'b2b'
export type BadgeKey = 'alerts' | 'pending' | 'b2bPending'
export type CapabilityStatus = 'live' | 'planned'

export interface NavigationItem {
  key: string
  label: string
  path: string
  icon: ReactNode
  badge?: BadgeKey
  status?: CapabilityStatus
}

export interface NavigationGroup {
  key: string
  label: string
  icon: ReactNode
  scope: BusinessScope
  children: NavigationItem[]
}

export const navigationGroups: NavigationGroup[] = [
  {
    key: 'group-products',
    label: '商品与 AI 选品',
    icon: <ProductOutlined />,
    scope: 'all',
    children: [
      // 流程顺序：发现 → 选品 → 审批 → 分析 → 成本(闸门前置) → 工作台(含闸门) → 上架 → 数据管理
      { key: 'product-market-opportunities', label: '市场机会', path: '/products/publish', icon: <ThunderboltOutlined /> },
      { key: 'product-newton', label: '牛顿 AI 对话选品', path: '/products/newton-sourcing', icon: <CompassOutlined /> },
      { key: 'product-candidates', label: '候选产品与选品', path: '/products/candidates', icon: <FileSearchOutlined /> },
      { key: 'product-analysis', label: 'AI 产品分析', path: '/products/analysis', icon: <RobotOutlined /> },
      { key: 'product-costs', label: '成本与利润', path: '/products/costs', icon: <CalculatorOutlined /> },
      { key: 'product-pipeline', label: '商品工作台', path: '/products/pipeline', icon: <DeploymentUnitOutlined /> },
      { key: 'product-listing', label: '渠道与上架', path: '/products/listing', icon: <GlobalOutlined /> },
      { key: 'products', label: '商品主数据', path: '/products', icon: <DatabaseOutlined /> },
    ],
  },
  {
    key: 'group-b2c',
    label: 'B2C 零售',
    icon: <ShopOutlined />,
    scope: 'b2c',
    children: [
      { key: 'b2c-overview', label: 'B2C 经营', path: '/b2c/overview', icon: <DashboardOutlined /> },
      { key: 'b2c-products', label: 'B2C 商品', path: '/b2c/products', icon: <ShoppingOutlined /> },
      { key: 'b2c-orders', label: 'B2C 订单', path: '/b2c/orders', icon: <ShoppingCartOutlined /> },
      { key: 'b2c-customers', label: 'B2C 客户', path: '/b2c/customers', icon: <TeamOutlined /> },
      { key: 'b2c-marketing', label: 'B2C 营销', path: '/b2c/marketing', icon: <MailOutlined /> },
      { key: 'b2c-after-sales', label: 'B2C 售后', path: '/b2c/after-sales', icon: <CustomerServiceOutlined /> },
    ],
  },
  {
    key: 'group-b2b',
    label: 'B2B 批发',
    icon: <ClusterOutlined />,
    scope: 'b2b',
    children: [
      { key: 'b2b-overview', label: 'B2B 经营', path: '/b2b/overview', icon: <DashboardOutlined /> },
      { key: 'b2b-partners', label: '客户与代理商', path: '/b2b/partners', icon: <TeamOutlined />, badge: 'b2bPending' },
      { key: 'b2b-pricing', label: '商品目录与阶梯价', path: '/b2b/pricing', icon: <SolutionOutlined /> },
      { key: 'b2b-rfqs', label: 'RFQ 询盘', path: '/b2b/rfqs', icon: <FileSearchOutlined /> },
      { key: 'b2b-quotes', label: '报价与合同', path: '/b2b/quotes', icon: <FileTextOutlined /> },
      { key: 'b2b-orders', label: 'B2B 订单', path: '/b2b/orders', icon: <ShoppingCartOutlined /> },
      { key: 'b2b-agreements', label: '年度协议与返利', path: '/b2b/agreements', icon: <TrophyOutlined /> },
      { key: 'b2b-receivables', label: '应收账款', path: '/b2b/receivables', icon: <WalletOutlined /> },
      { key: 'b2b-credit', label: '信用风控与保险', path: '/b2b/credit', icon: <SafetyCertificateOutlined /> },
      { key: 'b2b-ai', label: 'B2B AI 助手', path: '/b2b/ai', icon: <RobotOutlined /> },
    ],
  },
  {
    key: 'group-supply',
    label: '供应链共享底座',
    icon: <DeploymentUnitOutlined />,
    scope: 'all',
    children: [
      { key: 'suppliers', label: '采购与供应商', path: '/supply/suppliers', icon: <ShopOutlined /> },
      { key: 'purchase-orders', label: '采购订单', path: '/supply/purchases', icon: <CarryOutOutlined /> },
      { key: 'inventory', label: 'WMS 库存仓储', path: '/supply/inventory', icon: <DatabaseOutlined /> },
      { key: 'logistics', label: 'TMS 国际物流', path: '/supply/logistics', icon: <TruckOutlined /> },
    ],
  },
  {
    key: 'group-growth',
    label: '营销与增长',
    icon: <GlobalOutlined />,
    scope: 'all',
    children: [
      { key: 'marketing-campaigns', label: '营销活动', path: '/marketing/campaigns', icon: <MailOutlined /> },
      { key: 'marketing-content', label: '内容工作台', path: '/marketing/content', icon: <FileTextOutlined /> },
      { key: 'marketing-seo', label: 'SEO', path: '/marketing/seo', icon: <GlobalOutlined /> },
      { key: 'marketing-edm', label: 'EDM', path: '/marketing/edm', icon: <MailOutlined /> },
    ],
  },
  {
    key: 'group-ai',
    label: 'AI 智能层',
    icon: <RobotOutlined />,
    scope: 'all',
    children: [
      { key: 'ai-suggestions', label: 'AI 建议与审批', path: '/ai/suggestions', icon: <SolutionOutlined />, badge: 'pending' },
      { key: 'ai-agents', label: 'Agent 运行', path: '/ai/agents', icon: <NodeIndexOutlined /> },
      { key: 'ai-memory', label: '成长记忆', path: '/ai/memory', icon: <BookOutlined /> },
    ],
  },
  {
    key: 'group-analytics',
    label: '经营分析',
    icon: <BarChartOutlined />,
    scope: 'all',
    children: [
      { key: 'analytics', label: '统一经营看板', path: '/analytics', icon: <BarChartOutlined /> },
      { key: 'channel-analytics', label: '渠道经营分析', path: '/analytics/channels', icon: <FundOutlined /> },
      { key: 'consolidation-analytics', label: '合并经营报表', path: '/analytics/consolidation', icon: <ApartmentOutlined /> },
      { key: 'finance', label: '财务对账', path: '/analytics/finance', icon: <FundOutlined /> },
      { key: 'weekly-report', label: 'AI 经营周报', path: '/analytics/weekly', icon: <FileTextOutlined /> },
    ],
  },
]

export const standaloneTopItems: NavigationItem[] = [
  { key: 'dashboard', label: '经营总览', path: '/dashboard', icon: <AppstoreOutlined /> },
  { key: 'alerts', label: '业务预警', path: '/alerts', icon: <AlertOutlined />, badge: 'alerts' },
]

export const standaloneGovernanceItems: NavigationItem[] = [
  { key: 'settings', label: '系统设置', path: '/settings', icon: <SettingOutlined /> },
  { key: 'currency-rates', label: '汇率管理', path: '/settings/currency-rates', icon: <GlobalOutlined /> },
  { key: 'customer-data', label: '客户身份与隐私', path: '/settings/customer-data', icon: <SafetyCertificateOutlined /> },
  { key: 'logs', label: '操作日志', path: '/logs', icon: <HistoryOutlined /> },
  { key: 'api-management', label: 'API 与连接器', path: '/api-management', icon: <ApiOutlined /> },
]

export const allNavigationItems: NavigationItem[] = [
  ...standaloneTopItems,
  ...navigationGroups.flatMap((group) => group.children),
  ...standaloneGovernanceItems,
]

export function findNavigationItem(pathname: string): NavigationItem | undefined {
  return [...allNavigationItems]
    .sort((a, b) => b.path.length - a.path.length)
    .find((item) => pathname === item.path || pathname.startsWith(`${item.path}/`))
}

export function filterNavigationGroups(scope: BusinessScope): NavigationGroup[] {
  if (scope === 'all') return navigationGroups
  return navigationGroups.filter((group) => group.scope === 'all' || group.scope === scope)
}
