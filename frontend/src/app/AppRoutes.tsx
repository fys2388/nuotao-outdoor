import { lazy, Suspense, type ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { RequireAuth } from '../auth/AuthProvider'
import {
  AfterSalesPage,
  ApiCapabilityPage,
  CustomersPage,
  FinanceOverviewPage,
  InventoryPage,
  LogisticsPage,
  MarketingPage,
  OrdersPage,
  ProductsPage,
  PurchaseOrdersPage,
  SuppliersPage,
} from '../pages/OperationsPages'
import AppShell from './AppShell'

const DashboardPage = lazy(() => import('../pages/Dashboard'))
const AlertsPage = lazy(() => import('../pages/Alerts'))
const LoginPage = lazy(() => import('../pages/Login'))
const B2COverviewPage = lazy(() => import('../pages/B2COverview'))
const B2BOverviewPage = lazy(() => import('../pages/B2BOverview'))
const CapabilityPage = lazy(() => import('../pages/CapabilityPage'))
const NotFoundPage = lazy(() => import('../pages/NotFound'))

const ProductAnalysisPage = lazy(() => import('../pages/ProductAnalysis'))
const ProductCandidatesPage = lazy(() => import('../pages/ProductCandidatesPage'))
const ProductCostsPage = lazy(() => import('../pages/ProductCostsPage'))
const AgentSuggestionsPage = lazy(() => import('../pages/AgentSuggestions'))
const AgentMonitorPage = lazy(() => import('../pages/AgentMonitor'))
const MemoryReviewPage = lazy(() => import('../pages/MemoryReview'))
const B2BAgentsPage = lazy(() => import('../pages/B2BAgents'))
const B2BPricingPage = lazy(() => import('../pages/B2BPricingPage'))
const B2BSalesPage = lazy(() => import('../pages/B2BSalesPage'))
const B2BReceivablesPage = lazy(() => import('../pages/B2BReceivablesPage'))
const B2BAgreementsPage = lazy(() => import('../pages/B2BAgreementsPage'))
const B2BCreditRiskPage = lazy(() => import('../pages/B2BCreditRiskPage'))
const B2BAiOperationsPage = lazy(() => import('../pages/B2BAiOperationsPage'))
const B2BPortalPage = lazy(() => import('../pages/B2BPortal'))
const ChannelAnalyticsPage = lazy(() => import('../pages/ChannelAnalytics'))
const ConsolidationPage = lazy(() => import('../pages/ConsolidationPage'))
const ExchangeRatesPage = lazy(() => import('../pages/ExchangeRates'))
const CustomerDataPage = lazy(() => import('../pages/CustomerDataPage'))

function PageLoader() {
  return (
    <div className="route-loading">
      <span className="route-loading__mark" />
      <span>正在加载经营模块</span>
    </div>
  )
}

function page(element: ReactNode) {
  return <Suspense fallback={<PageLoader />}>{element}</Suspense>
}

function Protected({ children }: { children: ReactNode }) {
  return (
    <RequireAuth>
      <Suspense fallback={<PageLoader />}>{children}</Suspense>
    </RequireAuth>
  )
}

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={page(<LoginPage />)} />
      <Route path="/portal/*" element={page(<B2BPortalPage />)} />

      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={page(<DashboardPage />)} />
        <Route path="alerts" element={page(<AlertsPage />)} />

        <Route path="products" element={page(<ProductsPage />)} />
        <Route path="products/candidates" element={page(<ProductCandidatesPage />)} />
        <Route path="products/analysis" element={page(<ProductAnalysisPage />)} />
        <Route path="products/listing" element={page(<ProductsPage />)} />
        <Route path="products/costs" element={page(<ProductCostsPage />)} />

        <Route path="b2c/overview" element={page(<B2COverviewPage />)} />
        <Route path="b2c/products" element={page(<ProductsPage />)} />
        <Route path="b2c/orders" element={page(<OrdersPage />)} />
        <Route path="b2c/customers" element={page(<CustomersPage />)} />
        <Route path="b2c/marketing" element={page(<MarketingPage />)} />
        <Route path="b2c/after-sales" element={page(<AfterSalesPage />)} />

        <Route
          path="b2b/overview"
          element={<Protected><B2BOverviewPage /></Protected>}
        />
        <Route
          path="b2b/partners"
          element={<Protected><B2BAgentsPage initialTab="agents" /></Protected>}
        />
        <Route
          path="b2b/pricing"
          element={<Protected><B2BPricingPage /></Protected>}
        />
        <Route
          path="b2b/orders"
          element={<Protected><B2BAgentsPage initialTab="orders" /></Protected>}
        />
        <Route
          path="b2b/rfqs"
          element={<Protected><B2BSalesPage initialTab="rfqs" /></Protected>}
        />
        <Route
          path="b2b/quotes"
          element={<Protected><B2BSalesPage initialTab="quotes" /></Protected>}
        />
        <Route
          path="b2b/receivables"
          element={<Protected><B2BReceivablesPage /></Protected>}
        />
        <Route
          path="b2b/agreements"
          element={<Protected><B2BAgreementsPage /></Protected>}
        />
        <Route
          path="b2b/credit"
          element={<Protected><B2BCreditRiskPage /></Protected>}
        />
        <Route
          path="b2b/ai"
          element={<Protected><B2BAiOperationsPage /></Protected>}
        />

        <Route path="supply/suppliers" element={page(<SuppliersPage />)} />
        <Route path="supply/purchases" element={page(<PurchaseOrdersPage />)} />
        <Route path="supply/inventory" element={page(<InventoryPage />)} />
        <Route path="supply/logistics" element={page(<LogisticsPage />)} />

        <Route path="marketing/campaigns" element={page(<MarketingPage />)} />
        <Route
          path="marketing/content"
          element={
            page(
              <CapabilityPage
                title="内容工作台"
                description="统一管理商品内容、社媒内容、广告素材和发布状态。"
                requiredApis={[
                  'GET /api/v1/content-items',
                  'POST /api/v1/content-items',
                  'POST /api/v1/content-items/{id}/review',
                ]}
                requiredModels={[
                  'Content Item：渠道、语言、商品、版本、发布状态和来源',
                  'Content Review：审核人、意见、结果和版本',
                  'Publication Event：目标平台、发布时间、外部 ID 和失败原因',
                ]}
                blockers={[
                  '当前旧页面仍包含模拟内容列表和模拟浏览量',
                  '内容生成接口存在，但缺少内容主数据、审核和发布回执接口',
                  '未接入真实平台回执前不得展示阅读量、转化量或发布成功状态',
                ]}
              />,
            )
          }
        />
        <Route
          path="marketing/seo"
          element={
            page(
              <CapabilityPage
                title="SEO 基建"
                description="管理关键词、技术问题、外链和自然搜索表现。"
                requiredApis={[
                  'GET /api/v1/seo/audits',
                  'POST /api/v1/seo/audits/run',
                  'GET /api/v1/seo/keywords',
                ]}
                requiredModels={[
                  'SEO Audit：页面、问题、严重度、证据、修复状态',
                  'Keyword Rank：关键词、搜索引擎、地区、排名时间和来源',
                  'Backlink Record：来源、目标、锚文本、发现时间和失效状态',
                ]}
                blockers={[
                  '当前旧页面使用模拟关键词、外链和问题数据',
                  '必须接入可追溯的数据源，例如 GSC、GA4 和站点爬虫结果',
                  '排名、自然流量和外链指标必须带采集时间和来源',
                ]}
              />,
            )
          }
        />
        <Route
          path="marketing/edm"
          element={
            page(
              <CapabilityPage
                title="EDM 营销自动化"
                description="管理订阅分群、邮件模板、发送任务、退订和合规审计。"
                requiredApis={[
                  'GET /api/v1/edm/campaigns',
                  'POST /api/v1/edm/campaigns/{id}/schedule',
                  'GET /api/v1/edm/compliance-events',
                ]}
                requiredModels={[
                  'EDM Campaign：主题、模板、分群、发送窗口和状态',
                  'Consent Event：订阅、退订、投诉和来源',
                  'Delivery Event：发送、送达、退信、点击和转化',
                ]}
                blockers={[
                  '发送前必须完成 GDPR 同意校验',
                  '邮件模板与内容需要版本化和人工审批',
                  '未接入真实投递回执前不得展示打开率或转化率',
                ]}
              />,
            )
          }
        />

        <Route path="ai/suggestions" element={page(<AgentSuggestionsPage />)} />
        <Route path="ai/agents" element={page(<AgentMonitorPage />)} />
        <Route path="ai/memory" element={page(<MemoryReviewPage />)} />

        <Route path="analytics" element={page(<DashboardPage />)} />
        <Route
          path="analytics/channels"
          element={<Protected><ChannelAnalyticsPage /></Protected>}
        />
        <Route
          path="analytics/consolidation"
          element={<Protected><ConsolidationPage /></Protected>}
        />
        <Route path="analytics/finance" element={page(<FinanceOverviewPage />)} />
        <Route
          path="analytics/weekly"
          element={
            page(
              <CapabilityPage
                title="AI 经营周报"
                description="基于真实订单、成本、物流、退款和营销数据生成可追溯经营周报。"
                requiredApis={[
                  'POST /api/v1/weekly-reports/generate',
                  'GET /api/v1/weekly-reports',
                  'GET /api/v1/weekly-reports/{id}/evidence',
                ]}
                requiredModels={[
                  'Weekly Report：周期、版本、生成时间、数据快照和审核状态',
                  'Metric Evidence：每个经营指标对应的查询口径和数据来源',
                  'Report Action：行动项、负责人、截止时间和执行结果',
                ]}
                blockers={[
                  '当前后端服务在没有经营数据时会生成硬编码模拟周报',
                  '周报指标必须来自数据库聚合，并保留数据快照和口径版本',
                  'AI 洞察、预测和行动建议必须绑定证据，不能虚构渠道表现',
                ]}
              />,
            )
          }
        />

        <Route
          path="settings"
          element={
            <Protected>
              <CapabilityPage
                title="系统设置"
                description="集中管理用户角色、业务参数、连接器凭证和系统开关。"
                requiredApis={[
                  'GET /api/v1/system-settings',
                  'PUT /api/v1/system-settings',
                  'GET /api/v1/users',
                ]}
                requiredModels={[
                  'System Setting：配置键、值、类型、版本和审批状态',
                  'Role Permission：角色、权限、数据范围和工作区',
                  'Credential Metadata：连接器、轮换时间和脱敏状态，不返回密钥明文',
                ]}
                blockers={[
                  '当前系统设置接口缺少统一管理员权限校验',
                  '配置写入必须保留前后值和操作者审计',
                  '密钥只能进入 Secrets 管理，禁止前端读取或回显',
                ]}
              />
            </Protected>
          }
        />
        <Route
          path="settings/currency-rates"
          element={
            <Protected>
              <ExchangeRatesPage />
            </Protected>
          }
        />
        <Route
          path="settings/customer-data"
          element={
            <Protected>
              <CustomerDataPage />
            </Protected>
          }
        />
        <Route
          path="logs"
          element={
            <Protected>
              <CapabilityPage
                title="操作日志与审计"
                description="查询关键业务写操作、审批、连接器调用和权限变更记录。"
                requiredApis={[
                  'GET /api/v1/operation-logs',
                  'GET /api/v1/operation-logs/stats',
                  'GET /api/v1/audit-trails',
                ]}
                requiredModels={[
                  'Operation Log：操作者、模块、动作、目标、结果、trace_id',
                  'Audit Trail：变更前后值、审批与版本',
                  'Security Event：登录、权限变更、密钥轮换和异常访问',
                ]}
                blockers={[
                  '后端必须统一写入认证主体，禁止前端传入操作者',
                  '日志必须脱敏并设置保留期限',
                  '不得用演示日志替代真实审计数据',
                ]}
              />
            </Protected>
          }
        />
        <Route
          path="api-management"
          element={
            <Protected>
              <ApiCapabilityPage />
            </Protected>
          }
        />

        <Route path="*" element={page(<NotFoundPage />)} />
      </Route>
    </Routes>
  )
}
