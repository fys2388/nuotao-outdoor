import React from 'react'
import { Card, Typography, Row, Col, Button, Space } from 'antd'
import { navigate } from '../../api/publicApi'
import { SITE_CONFIG } from '../../config/site'
import PublicLayout, { COLORS } from './PublicLayout'

const { Title, Text, Paragraph } = Typography

// Cooperation page copy — aimed at wholesalers / distributors / small-B buyers.
// Editorial rules (AGENTS.md): neutral, professional trade tone, no exaggeration,
// no unverifiable claims. Contact details come from SITE_CONFIG (not hardcoded here).

const COOPERATION_TYPES: { title: string; description: string }[] = [
  {
    title: 'Wholesale Purchasing',
    description:
      'For retailers and wholesalers purchasing our outdoor products in quantity. We discuss ' +
      'available product options, wholesale pricing, and order arrangements directly through our ' +
      'enquiry process.',
  },
  {
    title: 'Distribution Cooperation',
    description:
      'For partners representing our products in regional markets. We work with distributors to ' +
      'define the product selection and supply arrangements that fit their market.',
  },
  {
    title: 'Product Sourcing',
    description:
      'If you need specific camping or hiking products, share your requirements and we will ' +
      'explore suitable options within our range and supply capability.',
  },
  {
    title: 'Long-term Supply',
    description:
      'For businesses seeking an ongoing supply relationship, we welcome enquiries about ' +
      'establishing recurring orders and a longer-term cooperation.',
  },
]

export default function Cooperation() {
  const whatsappHref = `${SITE_CONFIG.contact.whatsappUrl}?text=${encodeURIComponent(
    'Hello Nuotao Outdoor, I would like to discuss a wholesale / B2B enquiry.'
  )}`

  return (
    <PublicLayout currentPath="/cooperation">
      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '40px 32px' }}>
        <Title level={2} style={{ color: COLORS.charcoal, marginBottom: 8 }}>
          Cooperation
        </Title>
        <Paragraph style={{ color: COLORS.charcoal, fontSize: 16, maxWidth: 760 }}>
          We work with outdoor retailers, wholesalers, distributors, and smaller businesses across
          several cooperation models. Choose the area that best matches your needs and get in
          touch.
        </Paragraph>

        <Row gutter={[16, 16]} style={{ marginTop: 24 }}>
          {COOPERATION_TYPES.map((item) => (
            <Col xs={24} md={12} key={item.title}>
              <Card style={{ height: '100%' }}>
                <Title level={4} style={{ color: COLORS.forest, marginTop: 0 }}>
                  {item.title}
                </Title>
                <Text style={{ color: COLORS.charcoal }}>{item.description}</Text>
              </Card>
            </Col>
          ))}
        </Row>

        <Row gutter={[16, 16]} style={{ marginTop: 8, marginBottom: 40 }}>
          <Col xs={24} md={12}>
            <Card style={{ height: '100%' }}>
              <Title level={4} style={{ color: COLORS.forest, marginTop: 0 }}>
                How to Start
              </Title>
              <Paragraph style={{ color: COLORS.charcoal, marginBottom: 0 }}>
                Send us an enquiry with your business details and the products you are interested
                in. Our team will follow up to discuss wholesale pricing, minimum order quantities,
                and next steps.
              </Paragraph>
            </Card>
          </Col>
          <Col xs={24} md={12}>
            <Card style={{ height: '100%' }}>
              <Title level={4} style={{ color: COLORS.forest, marginTop: 0 }}>
                OEM / ODM
              </Title>
              <Paragraph style={{ color: COLORS.charcoal, marginBottom: 0 }}>
                For selected product categories we can discuss OEM / ODM arrangements, including
                customisation and private-label options, subject to order volume and
                feasibility. Share your requirements and we will assess what is possible.
              </Paragraph>
            </Card>
          </Col>
        </Row>

        <Card style={{ background: COLORS.forest, border: 'none' }} bodyStyle={{ padding: '32px' }}>
          <Title level={3} style={{ color: '#FFFFFF', marginTop: 0 }}>
            Start a Conversation
          </Title>
          <Paragraph style={{ color: '#E4EDE6', fontSize: 15, maxWidth: 640 }}>
            Send us your enquiry and our team will follow up to discuss wholesale pricing and next
            steps. You can reach us through any of the channels below.
          </Paragraph>
          <Space wrap size="middle" style={{ marginTop: 8 }}>
            <Button
              size="large"
              onClick={() => navigate('/request-a-quote')}
              style={{ background: COLORS.orange, borderColor: COLORS.orange, fontWeight: 600 }}
            >
              Request a Quote
            </Button>
            <Button
              size="large"
              href={whatsappHref}
              target="_blank"
              rel="noopener noreferrer"
              style={{ background: '#25D366', borderColor: '#25D366', color: '#FFFFFF', fontWeight: 600 }}
            >
              Chat on WhatsApp
            </Button>
            <Button
              size="large"
              href={`mailto:${SITE_CONFIG.contact.email}`}
              style={{ background: 'transparent', borderColor: '#E4EDE6', color: '#FFFFFF', fontWeight: 600 }}
            >
              Email Our B2B Team
            </Button>
          </Space>
        </Card>
      </div>
    </PublicLayout>
  )
}