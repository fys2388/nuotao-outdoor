import React, { useState } from 'react'
import {
  Card,
  Form,
  Input,
  Select,
  Button,
  Typography,
  Row,
  Col,
  Alert,
  Space,
  Divider,
} from 'antd'
import {
  ShopOutlined,
  CheckCircleOutlined,
  ArrowLeftOutlined,
} from '@ant-design/icons'
import { api } from '../api/client'
import { navigateTo } from '../navigate'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

interface ApplyFormValues {
  company_name: string
  contact_name: string
  email: string
  phone?: string
  whatsapp?: string
  wechat?: string
  country?: string
  city?: string
  address?: string
  password: string
  business_type?: string
  website?: string
  estimated_annual_volume?: string
  product_interests?: string
  message?: string
}

export default function ApplyPage() {
  const [form] = Form.useForm<ApplyFormValues>()
  const [submitting, setSubmitting] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const onFinish = async (values: ApplyFormValues) => {
    setSubmitting(true)
    setError(null)
    try {
      await api.submitApplication(values)
      setSuccess(true)
    } catch (err: any) {
      const detail = err?.response?.data?.detail || 'Failed to submit application. Please try again.'
      setError(detail)
    } finally {
      setSubmitting(false)
    }
  }

  if (success) {
    return (
      <div style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        padding: 24,
      }}>
        <Card style={{ maxWidth: 520, width: '100%', textAlign: 'center', borderRadius: 12 }}>
          <CheckCircleOutlined style={{ fontSize: 64, color: '#52c41a', marginBottom: 16 }} />
          <Title level={3} style={{ marginBottom: 8 }}>Application Submitted!</Title>
          <Paragraph type="secondary" style={{ marginBottom: 24 }}>
            Thank you for applying to become a Nuotao Outdoor B2B partner.
            Our team will review your application and contact you within 1-2 business days.
            You will receive an email notification once your account is approved.
          </Paragraph>
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            <Alert
              message="What happens next?"
              description={
                <ul style={{ margin: 0, paddingLeft: 20, textAlign: 'left' }}>
                  <li>Our B2B team reviews your application</li>
                  <li>We may contact you for additional information</li>
                  <li>Upon approval, your account is activated</li>
                  <li>You can log in with your email and password</li>
                </ul>
              }
              type="info"
              showIcon
            />
            <Button type="primary" size="large" onClick={() => navigateTo('/login')}>
              Back to Login
            </Button>
          </Space>
        </Card>
      </div>
    )
  }

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      padding: '24px 16px',
    }}>
      <Card style={{ maxWidth: 720, width: '100%', borderRadius: 12 }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <ShopOutlined style={{ fontSize: 48, color: '#1890ff', marginBottom: 12 }} />
          <Title level={3} style={{ marginBottom: 4 }}>Become a B2B Partner</Title>
          <Text type="secondary">
            Apply for wholesale pricing, credit terms, and exclusive partner benefits.
          </Text>
        </div>

        {error && (
          <Alert
            message="Submission Failed"
            description={error}
            type="error"
            showIcon
            closable
            onClose={() => setError(null)}
            style={{ marginBottom: 16 }}
          />
        )}

        <Form
          form={form}
          layout="vertical"
          onFinish={onFinish}
          requiredMark="optional"
          initialValues={{ country: '', business_type: '' }}
        >
          <Divider orientation="left" orientationMargin={0}>Company Information</Divider>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="company_name"
                label="Company Name *"
                rules={[{ required: true, message: 'Please enter company name' }]}
              >
                <Input placeholder="Your company name" size="large" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="business_type"
                label="Business Type"
              >
                <Select
                  placeholder="Select business type"
                  size="large"
                  allowClear
                  options={[
                    { value: 'Retailer', label: 'Retailer / Online Store' },
                    { value: 'Distributor', label: 'Distributor / Wholesaler' },
                    { value: 'Brand', label: 'Brand / ODM/OEM' },
                    { value: 'Outdoor_Chain', label: 'Outdoor Chain Store' },
                    { value: 'E_commerce', label: 'E-commerce Seller' },
                    { value: 'Other', label: 'Other' },
                  ]}
                />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="website"
                label="Company Website"
              >
                <Input placeholder="https://yourcompany.com" size="large" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="estimated_annual_volume"
                label="Estimated Annual Purchase Volume"
              >
                <Select
                  placeholder="Select range"
                  size="large"
                  allowClear
                  options={[
                    { value: '< $10k', label: 'Less than $10,000' },
                    { value: '$10k - $50k', label: '$10,000 - $50,000' },
                    { value: '$50k - $100k', label: '$50,000 - $100,000' },
                    { value: '$100k - $500k', label: '$100,000 - $500,000' },
                    { value: '> $500k', label: 'More than $500,000' },
                  ]}
                />
              </Form.Item>
            </Col>
          </Row>

          <Divider orientation="left" orientationMargin={0}>Contact Person</Divider>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="contact_name"
                label="Full Name *"
                rules={[{ required: true, message: 'Please enter your name' }]}
              >
                <Input placeholder="Your full name" size="large" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="email"
                label="Business Email *"
                rules={[
                  { required: true, message: 'Please enter email' },
                  { type: 'email', message: 'Please enter a valid email' },
                ]}
              >
                <Input placeholder="you@company.com" size="large" />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="phone" label="Phone">
                <Input placeholder="+1 234 567 8900" size="large" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="whatsapp" label="WhatsApp">
                <Input placeholder="+1 234 567 8900" size="large" prefix={<span style={{ color: '#25D366' }}>✆</span>} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="wechat" label="WeChat / 微信">
                <Input placeholder="WeChat ID" size="large" />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="country" label="Country">
                <Input placeholder="Country" size="large" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="city" label="City">
                <Input placeholder="City" size="large" />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item name="address" label="Street Address">
            <Input placeholder="Street address, postal code" size="large" />
          </Form.Item>

          <Divider orientation="left" orientationMargin={0}>Account Setup</Divider>

          <Form.Item
            name="password"
            label="Set Password *"
            rules={[
              { required: true, message: 'Please set a password' },
              { min: 8, message: 'Password must be at least 8 characters' },
            ]}
            extra="You will use this password to log in after your application is approved."
          >
            <Input.Password placeholder="Minimum 8 characters" size="large" />
          </Form.Item>

          <Form.Item name="product_interests" label="Product Categories of Interest">
            <Select
              mode="tags"
              placeholder="e.g. Water Bottles, Camping Gear, Outdoor Apparel"
              size="large"
              tokenSeparators={[',']}
              style={{ width: '100%' }}
            />
          </Form.Item>

          <Form.Item name="message" label="Additional Message">
            <TextArea rows={3} placeholder="Tell us about your business and partnership goals..." />
          </Form.Item>

          <Form.Item style={{ marginBottom: 0, marginTop: 8 }}>
            <Space direction="vertical" style={{ width: '100%' }}>
              <Button
                type="primary"
                htmlType="submit"
                size="large"
                block
                loading={submitting}
              >
                Submit Application
              </Button>
              <Button
                type="link"
                icon={<ArrowLeftOutlined />}
                onClick={() => (window.location.hash = '/login')}
                style={{ padding: 0 }}
              >
                Already have an account? Sign in
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}
