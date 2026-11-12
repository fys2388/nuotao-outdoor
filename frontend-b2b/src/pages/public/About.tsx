import React from 'react'
import { Card, Typography, Row, Col } from 'antd'
import PublicLayout, { COLORS } from './PublicLayout'

const { Title, Text, Paragraph } = Typography

// About page copy — edited for overseas B2B buyers (wholesale / distribution / small-B).
// Editorial rules (AGENTS.md): fact-checked, neutral, professional trade tone,
// no exaggeration, no unverifiable claims (no founding year, factory size, or
// certification assertions unless documented). Sourced from the verified DTC
// positioning: lightweight camping / hiking gear with clear product information.

const ABOUT_SECTIONS: { title: string; body: string }[] = [
  {
    title: 'Who We Are',
    body:
      'Nuotao Outdoor is an outdoor equipment brand focused on lightweight camping and hiking ' +
      'gear. Headquartered in Hong Kong with operations and supply chain in Shenzhen, China, we ' +
      'develop and supply practical outdoor products for retail and wholesale buyers around the ' +
      'world.',
  },
  {
    title: 'What We Make',
    body:
      'Our range covers everyday outdoor essentials: rechargeable headlamps, titanium cookware ' +
      'and water bottles, inflatable sleeping pads and liners, gaiters, traction devices, ' +
      'storage organisers, and portable water filtration. Each product is designed around ' +
      'practical use, clear specifications, and dependable everyday performance.',
  },
  {
    title: 'How We Work With Buyers',
    body:
      'We keep product information clear and straightforward so buyers can evaluate items ' +
      'quickly. Public product pages present specifications and imagery without retail pricing; ' +
      'wholesale pricing and availability are shared directly through our enquiry process. This ' +
      'keeps the public catalogue simple while giving buyers the detail they need to decide.',
  },
  {
    title: 'Who We Serve',
    body:
      'We work with outdoor retailers, wholesalers, distributors, and smaller businesses looking ' +
      'for reliable lightweight camping and hiking products. Whether you are stocking a retail ' +
      'range, building a distribution portfolio, or sourcing for a specific requirement, we aim ' +
      'to make the process clear and straightforward.',
  },
]

export default function About() {
  return (
    <PublicLayout currentPath="/about">
      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '40px 32px' }}>
        <Title level={2} style={{ color: COLORS.charcoal, marginBottom: 8 }}>
          About Nuotao Outdoor
        </Title>
        <Paragraph style={{ color: COLORS.charcoal, fontSize: 16, maxWidth: 760 }}>
          A focused outdoor equipment brand supplying lightweight camping and hiking gear to
          retail and wholesale buyers worldwide.
        </Paragraph>

        <Row gutter={[16, 16]} style={{ marginTop: 24 }}>
          {ABOUT_SECTIONS.map((section) => (
            <Col xs={24} md={12} key={section.title}>
              <Card style={{ height: '100%' }}>
                <Title level={4} style={{ color: COLORS.forest, marginTop: 0 }}>
                  {section.title}
                </Title>
                <Paragraph style={{ color: COLORS.charcoal, marginBottom: 0 }}>
                  {section.body}
                </Paragraph>
              </Card>
            </Col>
          ))}
        </Row>
      </div>
    </PublicLayout>
  )
}