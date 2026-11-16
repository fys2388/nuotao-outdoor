import { useCallback, useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Col,
  Divider,
  Form,
  Input,
  Row,
  Select,
  Space,
  Spin,
  Typography,
  message,
} from 'antd'
import {
  MailOutlined,
  UserOutlined,
  CheckCircleOutlined,
  SendOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { portalApi, type PortalAgent } from '../api/b2bPortal'

const { Title, Text, Paragraph } = Typography

// M3.37: Business types for registration form
const BUSINESS_TYPES = [
  { value: 'retailer', label: 'Retailer / 零售商' },
  { value: 'distributor', label: 'Distributor / 分销商' },
  { value: 'wholesaler', label: 'Wholesaler / 批发商' },
  { value: 'ecommerce_seller', label: 'E-commerce Seller / 电商卖家' },
  { value: 'brand', label: 'Brand / 品牌方' },
  { value: 'other', label: 'Other / 其他' },
]

const COUNTRY_OPTIONS = [
  { value: 'US', label: 'United States / 美国' },
  { value: 'DE', label: 'Germany / 德国' },
  { value: 'GB', label: 'United Kingdom / 英国' },
  { value: 'CA', label: 'Canada / 加拿大' },
  { value: 'AU', label: 'Australia / 澳大利亚' },
  { value: 'JP', label: 'Japan / 日本' },
  { value: 'KR', label: 'South Korea / 韩国' },
  { value: 'CN', label: 'China / 中国' },
  { value: 'OTHER', label: 'Other / 其他国家' },
]

export default function B2BRegisterPage() {
  const navigate = useNavigate()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [agent, setAgent] = useState<PortalAgent | null>(null)
  const [resending, setResending] = useState(false)
  const [verificationEmail, setVerificationEmail] = useState<string | null>(null)

  // Check if user is already logged in
  useEffect(() => {
    const token = localStorage.getItem('portal_token')
    if (token) {
      navigate('/portal', { replace: true })
    }
  }, [navigate])

  const handleSubmit = async (values: Record<string, any>) => {
    setLoading(true)
    try {
      const response = await portalApi.apply({
        company_name: values.company_name,
        contact_name: values.contact_name,
        email: values.email,
        password: values.password,
        phone: values.phone || null,
        whatsapp: values.whatsapp || null,
        wechat: values.wechat || null,
        country: values.country || null,
        city: values.city || null,
        address: values.address || null,
        business_type: values.business_type || null,
        website: values.website || null,
        estimated_annual_volume: values.estimated_annual_volume || null,
        product_interests: values.product_interests || null,
        message: values.message || null,
      })

      setSubmitted(true)
      setAgent((response as { agent: PortalAgent }).agent)
      setVerificationEmail(values.email)
      
      // TODO: In production, this would trigger an actual email send
      console.log('Application submitted:', response)
      message.success('Application submitted successfully! Please check your email for verification.')
    } catch (error: any) {
      const messageText = error?.response?.data?.detail || 'Failed to submit application. Please try again.'
      message.error(messageText)
    } finally {
      setLoading(false)
    }
  }

  const handleResendVerification = async () => {
    if (!verificationEmail) return
    
    setResending(true)
    try {
      await portalApi.resendVerification(verificationEmail)
      message.success('Verification email has been resent!')
    } catch (error: any) {
      // Silent fail to prevent email enumeration
      message.info('If the email exists, a verification link has been sent.')
    } finally {
      setResending(false)
    }
  }

  if (submitted && agent) {
    return (
      <Row justify="center" style={{ minHeight: '100vh', background: '#f5f5f5', padding: '40px 0' }}>
        <Col xs={24} sm={20} md={16} lg={12}>
          <Card>
            <div style={{ textAlign: 'center', padding: '20px 0' }}>
              <CheckCircleOutlined style={{ fontSize: 64, color: '#52c41a' }} />
              <Title level={2} style={{ marginTop: 20 }}>Application Submitted!</Title>
              <Paragraph type="secondary">
                Thank you for registering as a Nuotao Outdoor partner.
              </Paragraph>
            </div>

            <Divider />

            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              <Alert
                message="Next Steps"
                description={
                  <ol style={{ margin: 0, paddingLeft: 20 }}>
                    <li>Check your email inbox for the verification link</li>
                    <li>Click the link to verify your email address</li>
                    <li>Wait for our team to review and approve your application</li>
                    <li>Once approved, you can log in to the B2B portal</li>
                  </ol>
                }
                type="info"
                showIcon
              />

              {verificationEmail && (
                <Alert
                  message={`Verification link sent to: ${verificationEmail}`}
                  type="success"
                  showIcon
                />
              )}

              <Button
                type="primary"
                block
                loading={resending}
                onClick={handleResendVerification}
              >
                <SendOutlined /> Resend Verification Email
              </Button>

              <Button block onClick={() => navigate('/portal/login')}>
                Back to Login
              </Button>
            </Space>
          </Card>
        </Col>
      </Row>
    )
  }

  return (
    <Row justify="center" style={{ minHeight: '100vh', background: '#f5f5f5', padding: '40px 0' }}>
      <Col xs={24} sm={20} md={16} lg={12}>
        <Card title={<Title level={3}>Become a Nuotao Partner</Title>}>
          <Space direction="vertical" style={{ width: '100%' }} size="large">
            <Alert
              message="Partner Registration"
              description="Apply to become a Nuotao Outdoor authorized distributor. Our team will review your application within 1-2 business days."
              type="info"
              showIcon
            />

            <Spin spinning={loading}>
              <Form
                form={form}
                layout="vertical"
                onFinish={handleSubmit}
                initialValues={{ business_type: 'retailer' }}
              >
                <Row gutter={16}>
                  <Col span={12}>
                    <Form.Item
                      name="company_name"
                      label="Company Name"
                      rules={[{ required: true, message: 'Please enter your company name' }]}
                    >
                      <Input prefix={<UserOutlined />} placeholder="Acme Outdoor Co." />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item
                      name="business_type"
                      label="Business Type"
                      rules={[{ required: true, message: 'Please select your business type' }]}
                    >
                      <Select options={BUSINESS_TYPES} />
                    </Form.Item>
                  </Col>
                </Row>

                <Row gutter={16}>
                  <Col span={12}>
                    <Form.Item
                      name="contact_name"
                      label="Contact Person"
                      rules={[{ required: true, message: 'Please enter contact name' }]}
                    >
                      <Input prefix={<UserOutlined />} placeholder="John Doe" />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item
                      name="email"
                      label="Email Address"
                      rules={[
                        { required: true, type: 'email', message: 'Please enter a valid email' },
                      ]}
                    >
                      <Input prefix={<MailOutlined />} placeholder="john@acme.com" />
                    </Form.Item>
                  </Col>
                </Row>

                <Form.Item
                  name="password"
                  label="Password"
                  rules={[
                    { required: true, message: 'Please enter a password' },
                    { min: 8, message: 'Password must be at least 8 characters' },
                  ]}
                >
                  <Input.Password placeholder="Create a strong password" />
                </Form.Item>

                <Row gutter={16}>
                  <Col span={12}>
                    <Form.Item name="phone" label="Phone Number">
                      <Input placeholder="+1 234 567 8900" />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item name="country" label="Country/Region">
                      <Select
                        placeholder="Select country"
                        options={COUNTRY_OPTIONS}
                        allowClear
                      />
                    </Form.Item>
                  </Col>
                </Row>

                <Row gutter={16}>
                  <Col span={12}>
                    <Form.Item name="city" label="City">
                      <Input placeholder="City" />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item name="website" label="Website">
                      <Input placeholder="https://your-company.com" />
                    </Form.Item>
                  </Col>
                </Row>

                <Form.Item name="address" label="Address">
                  <Input.TextArea rows={2} placeholder="Full address" />
                </Form.Item>

                <Row gutter={16}>
                  <Col span={12}>
                    <Form.Item name="whatsapp" label="WhatsApp">
                      <Input placeholder="+1 234 567 8900" />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item name="wechat" label="WeChat">
                      <Input placeholder="Your WeChat ID" />
                    </Form.Item>
                  </Col>
                </Row>

                <Form.Item name="estimated_annual_volume" label="Estimated Annual Purchase Volume">
                  <Select
                    placeholder="Select range"
                    options={[
                      { value: 'under_10k', label: 'Under $10,000' },
                      { value: '10k_50k', label: '$10,000 - $50,000' },
                      { value: '50k_100k', label: '$50,000 - $100,000' },
                      { value: '100k_500k', label: '$100,000 - $500,000' },
                      { value: 'over_500k', label: 'Over $500,000' },
                    ]}
                    allowClear
                  />
                </Form.Item>

                <Form.Item name="product_interests" label="Products of Interest">
                  <Input placeholder="e.g., Backpacks, Tents, Sleeping Bags" />
                </Form.Item>

                <Form.Item name="message" label="Additional Message">
                  <Input.TextArea rows={3} placeholder="Any questions or special requirements..." />
                </Form.Item>

                <Form.Item>
                  <Button
                    type="primary"
                    htmlType="submit"
                    block
                    size="large"
                    loading={loading}
                  >
                    Submit Application
                  </Button>
                </Form.Item>
              </Form>
            </Spin>

            <Divider />

            <Space direction="vertical" style={{ width: '100%' }}>
              <Text type="secondary">Already have an account?</Text>
              <Button block onClick={() => navigate('/portal/login')}>
                Login to B2B Portal
              </Button>
            </Space>
          </Space>
        </Card>
      </Col>
    </Row>
  )
}
