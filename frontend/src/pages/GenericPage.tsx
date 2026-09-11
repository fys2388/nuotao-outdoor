import { Card, Descriptions, Tag, Space, Alert, List, Typography, Divider, Row, Col } from 'antd'
import { ApiOutlined, CheckCircleOutlined, RocketOutlined } from '@ant-design/icons'

const { Title, Paragraph } = Typography

interface ModuleInfo {
  key: string
  name: string
  description: string
  apiEndpoints: string[]
  features: string[]
  status: string
}

const moduleMap: Record<string, ModuleInfo> = {
  sourcing: {
    key: 'sourcing',
    name: '选品管理',
    description: '支持人工录入、批量导入、AI 结构化分析质检、6 维度产品评分',
    apiEndpoints: ['/api/v1/sourcing/products', '/api/v1/sourcing/import', '/api/v1/sourcing/ai-quality-check', '/api/v1/sourcing/score'],
    features: ['人工录入', '批量导入', 'AI 质检', '6 维度评分', '产品候选管理'],
    status: '已完成',
  },
  cost: {
    key: 'cost',
    name: '成本模型',
    description: '5 项成本组成，支持美国 51 州销售税、欧盟 27 国 VAT、IOSS，4 级盈利状态判断',
    apiEndpoints: ['/api/v1/cost-model/calculate', '/api/v1/cost-model/us-sales-tax', '/api/v1/cost-model/eu-vat', '/api/v1/cost-model/rules'],
    features: ['产品成本', '运费', '关税/VAT', '支付手续费', '营销费用', '美国销售税', '欧盟 VAT', 'IOSS'],
    status: '已完成',
  },
  selection: {
    key: 'selection',
    name: 'AI 选品建议',
    description: '4 级分级建议，选品决策创建，人工审批流程，审批通过后自动更新产品状态',
    apiEndpoints: ['/api/v1/selection/recommendations', '/api/v1/selection/decisions', '/api/v1/selection/decisions/{id}/approve'],
    features: ['4 级分级', '决策创建', '人工审批', '产品状态更新'],
    status: '已完成',
  },
  purchase: {
    key: 'purchase',
    name: '采购自动化',
    description: '8 项可配置采购规则，6 种异常检测，阻塞性异常拦截，低价值自动审批',
    apiEndpoints: ['/api/v1/purchase-automation/orders', '/api/v1/purchase-automation/rules', '/api/v1/purchase-automation/check-exceptions'],
    features: ['规则配置', '异常检测', '自动审批', '审批队列'],
    status: '已完成',
  },
  logistics: {
    key: 'logistics',
    name: '物流监控',
    description: '12 个物流商支持，8 种物流状态，轨迹同步，时效异常预警',
    apiEndpoints: ['/api/v1/logistics/shipments', '/api/v1/logistics/shipments/{id}/track', '/api/v1/logistics/alerts'],
    features: ['12 物流商', '8 种状态', '轨迹同步', '时效预警'],
    status: '已完成',
  },
  content: {
    key: 'content',
    name: '内容生成系统',
    description: '6 种内容类型，自动质量检查，审核流程，审核历史',
    apiEndpoints: ['/api/v1/content-generation/generate', '/api/v1/content-generation/items', '/api/v1/content-generation/items/{id}/review'],
    features: ['产品卖点', 'SEO 文章', 'EDM 邮件', '广告文案', '质量检查', '审核流程'],
    status: '已完成',
  },
  seo: {
    key: 'seo',
    name: 'SEO 基建',
    description: '4 种结构化数据，XML Sitemap，robots.txt，关键词策略，SEO 审计',
    apiEndpoints: ['/api/v1/seo/structured-data/product', '/api/v1/seo/sitemap', '/api/v1/seo/keyword-strategy', '/api/v1/seo/audit'],
    features: ['结构化数据', 'Sitemap', 'robots.txt', '关键词策略', 'SEO 审计'],
    status: '已完成',
  },
  edm: {
    key: 'edm',
    name: 'EDM 营销自动化',
    description: '7 种活动类型，3 个预设流程，邮件发送，7 种事件追踪，收入归因',
    apiEndpoints: ['/api/v1/edm/campaigns', '/api/v1/edm/send', '/api/v1/edm/track', '/api/v1/edm/campaigns/{id}/stats'],
    features: ['弃购挽回', '复购营销', '欢迎系列', '邮件发送', '事件追踪', '收入归因'],
    status: '已完成',
  },
  'weekly-report': {
    key: 'weekly-report',
    name: 'AI 经营周报',
    description: '自动生成周报，异常检测，趋势分析，AI 洞察，行动项，风险识别，下周展望',
    apiEndpoints: ['/api/v1/weekly-report/generate', '/api/v1/weekly-report/{id}', '/api/v1/weekly-report/{id}/anomalies', '/api/v1/weekly-report/{id}/action-items'],
    features: ['自动生成', '异常检测', '趋势分析', 'AI 洞察', '行动项', '风险识别', '下周展望'],
    status: '已完成',
  },
  overseas: {
    key: 'overseas',
    name: '海外仓对接',
    description: '入库单管理，出库单管理，库存同步，物流跟踪',
    apiEndpoints: ['/api/v1/p3/overseas/inbound', '/api/v1/p3/overseas/outbound', '/api/v1/p3/overseas/sync-inventory'],
    features: ['入库管理', '出库管理', '库存同步', '物流跟踪'],
    status: '已完成',
  },
  b2b: {
    key: 'b2b',
    name: 'B2B 代理商管理',
    description: '4 级代理体系，佣金率，折扣，信用额度，B2B 订单，账期管理，付款记录',
    apiEndpoints: ['/api/v1/p3/b2b/agents', '/api/v1/p3/b2b/orders', '/api/v1/p3/b2b/orders/{id}/payment'],
    features: ['代理商管理', '分级定价', '佣金跟踪', '信用管理', 'B2B 订单', '账期管理'],
    status: '已完成',
  },
  settings: {
    key: 'settings',
    name: '系统设置',
    description: '系统配置、预警规则、LLM 网关、集成管理',
    apiEndpoints: ['/api/v1/alerts/rules', '/api/v1/llm-gateway/status'],
    features: ['预警规则配置', 'LLM 网关', '系统参数', '集成管理'],
    status: '开发中',
  },
}

export default function GenericPage({ title, moduleKey }: { title: string; moduleKey: string }) {
  const info = moduleMap[moduleKey] || {
    key: moduleKey,
    name: title,
    description: '该模块后端 API 已完成，前端页面开发中',
    apiEndpoints: [],
    features: [],
    status: '开发中',
  }

  return (
    <div>
      <Alert
        type={info.status === '已完成' ? 'success' : 'info'}
        message={
          <Space>
            {info.status === '已完成' ? <CheckCircleOutlined /> : <RocketOutlined />}
            <strong>{info.name}</strong> - 后端 API {info.status}，前端页面开发中
          </Space>
        }
        description={info.description}
        showIcon
        style={{ marginBottom: 24 }}
      />

      <Row gutter={[24, 24]}>
        <Col xs={24} lg={14}>
          <Card title="模块功能" extra={<Tag color="blue">{info.features.length} 项功能</Tag>}>
            <List
              dataSource={info.features}
              renderItem={(item) => (
                <List.Item>
                  <Space>
                    <CheckCircleOutlined style={{ color: '#52c41a' }} />
                    {item}
                  </Space>
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title={<Space><ApiOutlined /> API 端点</Space>} extra={<Tag color="green">{info.apiEndpoints.length} 个</Tag>}>
            <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 12 }}>
              可通过 http://localhost:8000/docs 查看完整 API 文档并交互测试
            </Paragraph>
            <List
              size="small"
              dataSource={info.apiEndpoints}
              renderItem={(item) => (
                <List.Item>
                  <code style={{ background: '#f5f5f5', padding: '2px 8px', borderRadius: 4, fontSize: 12 }}>{item}</code>
                </List.Item>
              )}
            />
          </Card>
          <Card title="模块状态" style={{ marginTop: 16 }}>
            <Descriptions column={1} size="small">
              <Descriptions.Item label="模块名称">{info.name}</Descriptions.Item>
              <Descriptions.Item label="开发状态">
                <Tag color={info.status === '已完成' ? 'green' : 'orange'}>{info.status}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="API 文档">
                <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer">Swagger UI</a>
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
      </Row>

      <Divider />
      <Alert
        type="info"
        message="前端开发说明"
        description="当前管理控制台已完成核心框架（侧边栏导航、经营看板、预警中心、库存管理）。其余模块的前端页面可基于现有 API 端点快速开发，所有 API 均可在 http://localhost:8000/docs 中查看和测试。"
        showIcon
      />
    </div>
  )
}
