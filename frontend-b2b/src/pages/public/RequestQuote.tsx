import React, { useState, useEffect } from 'react'
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
  Checkbox,
} from 'antd'
import { CheckCircleOutlined } from '@ant-design/icons'
import { publicApi, LeadSubmitResponse } from '../../api/publicApi'
import PublicLayout, { COLORS } from './PublicLayout'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

interface RequestQuoteFormValues {
  company_name: string
  contact_name: string
  business_email: string
  country_region: string
  business_type: string
  products_of_interest: string
  message: string
  privacy_consent: boolean
  company_website?: string
  whatsapp?: string
  wechat?: string
  estimated_order_quantity?: string
  annual_purchase_range?: string
  destination_market?: string
}

const BUSINESS_TYPE_OPTIONS = [
  { value: 'retailer', label: 'Retailer' },
  { value: 'distributor', label: 'Distributor' },
  { value: 'wholesaler', label: 'Wholesaler' },
  { value: 'ecommerce_seller', label: 'E-commerce Seller' },
  { value: 'brand', label: 'Brand' },
  { value: 'other', label: 'Other' },
]

function readProductFromQuery(): string {
  const params = new URLSearchParams(window.location.search)
  return params.get('product') ?? ''
}

export default function RequestQuote({ prefillProduct }: { prefillProduct?: string }) {
  const [form] = Form.useForm<RequestQuoteFormValues>()
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successResult, setSuccessResult] = useState<LeadSubmitResponse | null>(null)

  const initialProduct = prefillProduct ?? readProductFromQuery()

  useEffect(() => {
    if (initialProduct) {
      form.setFieldValue('products_of_interest', initialProduct)
    }
  }, [form, initialProduct])

  const onFinish = async (values: RequestQuoteFormValues) => {
    setSubmitting(true)
    setError(null)
    try {
      const res = await publicApi.submitLead({ ...values })
      // Only treat the enquiry as successful when the server explicitly confirms it.
      if (res && res.success) {
        setSuccessResult(res)
      } else {
        setError(res?.message || 'Failed to submit enquiry. Please try again.')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to submit enquiry. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  if (successResult) {
    return (
      <PublicLayout currentPath="/request-a-quote">
        <div style={{ maxWidth: 720, margin: '0 auto', padding: '60px 32px', textAlign: 'center' }}>
          <CheckCircleOutlined style={{ fontSize: 64, color: COLORS.forest, marginBottom: 16 }} />
          <Title level={3} style={{ color: COLORS.charcoal, marginBottom: 8 }}>
            Enquiry Submitted
          </Title>
          <Paragraph style={{ color: COLORS.charcoal, fontSize: 16 }}>
            Thank you for your enquiry. Our team will review your request and get back to you.
          </Paragraph>
          <Card style={{ marginTop: 24, textAlign: 'left' }}>
            <Text strong>Reference Number: </Text>
            <Text code style={{ fontSize: 16 }}>
              {successResult.reference_number}
            </Text>
            <Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
              Please keep this reference number for any follow-up communication.
            </Paragraph>
          </Card>
        </div>
      </PublicLayout>
    )
  }

  return (
    <PublicLayout currentPath="/request-a-quote">
      <div style={{ maxWidth: 820, margin: '0 auto', padding: '40px 32px' }}>
        <Title level={2} style={{ color: COLORS.charcoal, marginBottom: 8 }}>
          Request a Quote
        </Title>
        <Paragraph style={{ color: COLORS.charcoal, fontSize: 16, marginBottom: 24 }}>
          Tell us about your business and the products you are interested in. Our team will follow
          up to discuss sourcing options.
        </Paragraph>

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

        <Card>
          <Form
            form={form}
            layout="vertical"
            onFinish={onFinish}
            initialValues={{ privacy_consent: false }}
          >
            <Row gutter={16}>
              <Col xs={24} sm={12}>
                <Form.Item
                  name="company_name"
                  label="Company Name"
                  rules={[{ required: true, message: 'Please enter your company name' }]}
                >
                  <Input placeholder="Your company name" />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12}>
                <Form.Item
                  name="contact_name"
                  label="Contact Name"
                  rules={[{ required: true, message: 'Please enter your name' }]}
                >
                  <Input placeholder="Your full name" />
                </Form.Item>
              </Col>
            </Row>

            <Row gutter={16}>
              <Col xs={24} sm={12}>
                <Form.Item
                  name="business_email"
                  label="Business Email"
                  rules={[
                    { required: true, message: 'Please enter your business email' },
                    { type: 'email', message: 'Please enter a valid email address' },
                  ]}
                >
                  <Input placeholder="you@company.com" />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12}>
                <Form.Item
                  name="country_region"
                  label="Country / Region"
                  rules={[{ required: true, message: 'Please enter your country or region' }]}
                >
                  <Input placeholder="e.g. United States" />
                </Form.Item>
              </Col>
            </Row>

            <Row gutter={16}>
              <Col xs={24} sm={12}>
                <Form.Item
                  name="business_type"
                  label="Business Type"
                  rules={[{ required: true, message: 'Please select your business type' }]}
                >
                  <Select placeholder="Select business type" options={BUSINESS_TYPE_OPTIONS} />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12}>
                <Form.Item
                  name="company_website"
                  label="Company Website"
                >
                  <Input placeholder="https://yourcompany.com" />
                </Form.Item>
              </Col>
            </Row>

            <Form.Item
              name="products_of_interest"
              label="Products of Interest"
              rules={[{ required: true, message: 'Please enter the products you are interested in' }]}
            >
              <Input placeholder="e.g. Camping tents, hiking backpacks" />
            </Form.Item>

            <Row gutter={16}>
              <Col xs={24} sm={8}>
                <Form.Item name="whatsapp" label="WhatsApp">
                  <Input placeholder="Optional" />
                </Form.Item>
              </Col>
              <Col xs={24} sm={8}>
                <Form.Item name="wechat" label="WeChat">
                  <Input placeholder="Optional" />
                </Form.Item>
              </Col>
              <Col xs={24} sm={8}>
                <Form.Item name="estimated_order_quantity" label="Estimated Order Quantity">
                  <Input placeholder="Optional" />
                </Form.Item>
              </Col>
            </Row>

            <Row gutter={16}>
              <Col xs={24} sm={12}>
                <Form.Item name="annual_purchase_range" label="Annual Purchase Range">
                  <Select
                    placeholder="Optional"
                    allowClear
                    options={[
                      { value: 'under_10k', label: 'Under 10,000 units' },
                      { value: '10k_50k', label: '10,000 - 50,000 units' },
                      { value: '50k_100k', label: '50,000 - 100,000 units' },
                      { value: 'over_100k', label: 'Over 100,000 units' },
                    ]}
                  />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12}>
                <Form.Item name="destination_market" label="Destination Market">
                  <Input placeholder="Optional, e.g. North America" />
                </Form.Item>
              </Col>
            </Row>

            <Form.Item
              name="message"
              label="Message"
              rules={[{ required: true, message: 'Please enter a message' }]}
            >
              <TextArea rows={4} placeholder="Tell us about your requirements..." />
            </Form.Item>

            <Form.Item
              name="privacy_consent"
              valuePropName="checked"
              rules={[
                {
                  validator: (_, value: boolean) =>
                    value
                      ? Promise.resolve()
                      : Promise.reject(new Error('Please agree to the privacy policy to continue')),
                },
              ]}
            >
              <Checkbox>
                I agree that my information may be used to respond to this enquiry.
              </Checkbox>
            </Form.Item>

            <Form.Item style={{ marginBottom: 0 }}>
              <Button
                type="primary"
                htmlType="submit"
                size="large"
                loading={submitting}
                style={{ background: COLORS.forest, borderColor: COLORS.forest, fontWeight: 600 }}
              >
                Submit Enquiry
              </Button>
            </Form.Item>
          </Form>
        </Card>
      </div>
    </PublicLayout>
  )
}
