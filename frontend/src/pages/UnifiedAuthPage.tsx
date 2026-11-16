import { Button, Card, Col, Row, Space, Typography } from 'antd'
import {
  BuildOutlined,
  ShopOutlined,
  TeamOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'

const { Title, Text, Paragraph } = Typography

export default function UnifiedAuthPage() {
  const navigate = useNavigate()

  return (
    <div style={{ minHeight: '100vh', background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '40px 0' }}>
      <div style={{ maxWidth: '900px', width: '100%' }}>
        {/* Brand Header */}
        <div style={{ textAlign: 'center', marginBottom: '48px' }}>
          <div style={{ fontSize: '32px', fontWeight: 700, color: '#fff', marginBottom: '8px' }}>
            NUOTAO OUTDOOR
          </div>
          <Text style={{ color: 'rgba(255,255,255,0.8)', fontSize: '16px' }}>
            AI-Driven Outdoor Commerce OS
          </Text>
          <Paragraph style={{ color: 'rgba(255,255,255,0.6)', marginTop: '16px', maxWidth: '600px', marginInline: 'auto' }}>
            一套系统，同时经营零售与批发。<br />
            统一商品、供应链、库存、物流和 AI Agent。
          </Paragraph>
        </div>

        {/* Entry Points */}
        <Row gutter={[24, 24]} justify="center">
          {/* B2B Partner Portal */}
          <Col xs={24} sm={12} lg={8}>
            <Card
              hoverable
              onClick={() => navigate('/portal/login')}
              style={{ cursor: 'pointer', borderRadius: '12px', borderTop: '4px solid #52c41a' }}
              bodyStyle={{ padding: '32px' }}
            >
              <div style={{ textAlign: 'center' }}>
                <div style={{ width: '64px', height: '64px', borderRadius: '50%', background: '#f6ffed', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>
                  <TeamOutlined style={{ fontSize: '32px', color: '#52c41a' }} />
                </div>
                <Title level={4} style={{ marginBottom: '8px' }}>合作伙伴门户</Title>
                <Text type="secondary" style={{ display: 'block', marginBottom: '16px' }}>
                  代理商/批发商自助服务
                </Text>
                <Space direction="vertical" size="small" style={{ width: '100%', textAlign: 'left' }}>
                  <Text className="text-item">✓ 查看批发价与MOQ</Text>
                  <Text className="text-item">✓ 提交RFQ询盘</Text>
                  <Text className="text-item">✓ 合同签署与订单管理</Text>
                  <Text className="text-item">✓ 信用额度与账期查询</Text>
                </Space>
                <Button type="primary" block style={{ marginTop: '24px', borderRadius: '6px' }}>
                  登录 / 注册
                </Button>
                <Text type="secondary" style={{ fontSize: '12px', display: 'block', marginTop: '8px' }}>
                  还没有账号？立即申请合作
                </Text>
              </div>
            </Card>
          </Col>

          {/* Internal Operations */}
          <Col xs={24} sm={12} lg={8}>
            <Card
              hoverable
              onClick={() => navigate('/login')}
              style={{ cursor: 'pointer', borderRadius: '12px', borderTop: '4px solid #1890ff' }}
              bodyStyle={{ padding: '32px' }}
            >
              <div style={{ textAlign: 'center' }}>
                <div style={{ width: '64px', height: '64px', borderRadius: '50%', background: '#e6f7ff', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>
                  <BuildOutlined style={{ fontSize: '32px', color: '#1890ff' }} />
                </div>
                <Title level={4} style={{ marginBottom: '8px' }}>运营管理后台</Title>
                <Text type="secondary" style={{ display: 'block', marginBottom: '16px' }}>
                  公司内部运营团队
                </Text>
                <Space direction="vertical" size="small" style={{ width: '100%', textAlign: 'left' }}>
                  <Text className="text-item">✓ 商品选品与上架管理</Text>
                  <Text className="text-item">✓ 供应链与采购订单</Text>
                  <Text className="text-item">✓ AI Agent调度与监控</Text>
                  <Text className="text-item">✓ 经营数据看板分析</Text>
                </Space>
                <Button type="primary" block style={{ marginTop: '24px', borderRadius: '6px', background: '#1890ff', borderColor: '#1890ff' }}>
                  员工登录
                </Button>
                <Text type="secondary" style={{ fontSize: '12px', display: 'block', marginTop: '8px' }}>
                  仅内部授权人员可访问
                </Text>
              </div>
            </Card>
          </Col>

          {/* B2C Store */}
          <Col xs={24} sm={12} lg={8}>
            <Card
              style={{ borderRadius: '12px', borderTop: '4px solid #faad14', background: 'rgba(255,255,255,0.95)' }}
              bodyStyle={{ padding: '32px' }}
            >
              <div style={{ textAlign: 'center' }}>
                <div style={{ width: '64px', height: '64px', borderRadius: '50%', background: '#fffbe6', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>
                  <ShopOutlined style={{ fontSize: '32px', color: '#faad14' }} />
                </div>
                <Title level={4} style={{ marginBottom: '8px' }}>零售商城</Title>
                <Text type="secondary" style={{ display: 'block', marginBottom: '16px' }}>
                  面向海外消费者
                </Text>
                <Space direction="vertical" size="small" style={{ width: '100%', textAlign: 'left' }}>
                  <Text className="text-item">✓ 浏览60+户外商品</Text>
                  <Text className="text-item">✓ 直发全球， tracked物流</Text>
                  <Text className="text-item">✓ 中文客服，7×24响应</Text>
                  <Text className="text-item">✓ Stripe/PayPal安全支付</Text>
                </Space>
                <Button 
                  type="primary" 
                  block 
                  style={{ marginTop: '24px', borderRadius: '6px', background: '#faad14', borderColor: '#faad14' }}
                  onClick={(e) => {
                    e.stopPropagation()
                    window.open('https://nuotaooutdoor.com', '_blank')
                  }}
                >
                  前往商城
                </Button>
                <Text type="secondary" style={{ fontSize: '12px', display: 'block', marginTop: '8px' }}>
                  nuotaooutdoor.com
                </Text>
              </div>
            </Card>
          </Col>
        </Row>

        {/* Footer Info */}
        <div style={{ textAlign: 'center', marginTop: '48px', color: 'rgba(255,255,255,0.6)', fontSize: '14px' }}>
          <Space split={<span style={{ opacity: 0.5 }}>|</span>}>
            <span>🔒 端到端加密</span>
            <span>🌍 支持多币种结算</span>
            <span>⚡ AI驱动运营</span>
          </Space>
          <Paragraph style={{ marginTop: '16px', marginBottom: 0 }}>
            © 2026 Nuotao Outdoor. All rights reserved.
          </Paragraph>
        </div>
      </div>
    </div>
  )
}
