import React, { useState, useEffect } from 'react'
import { Card, Row, Col, Statistic, Descriptions, Tag, Typography, Spin, Progress, Divider, Form, Input, Button, message } from 'antd'
import {
  DollarOutlined,
  ShoppingCartOutlined,
  CreditCardOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { api, AccountSummary } from '../api/client'
import { useAuth } from '../auth'

const { Title, Text } = Typography

const tierColors: Record<string, string> = {
  bronze: 'orange',
  silver: 'default',
  gold: 'gold',
  platinum: 'purple',
}

export default function AccountPage() {
  const { agent, refreshAgent } = useAuth()
  const [summary, setSummary] = useState<AccountSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [pwdForm] = Form.useForm()
  const [pwdLoading, setPwdLoading] = useState(false)

  const loadSummary = async () => {
    setLoading(true)
    try {
      const s = await api.getAccountSummary()
      setSummary(s)
    } catch (e: any) {
      // handled
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadSummary()
  }, [])

  const handleChangePassword = async (values: any) => {
    setPwdLoading(true)
    try {
      await api.changePassword(values.old_password, values.new_password)
      message.success('Password changed successfully')
      pwdForm.resetFields()
    } catch (e: any) {
      message.error(e.message || 'Failed to change password')
    } finally {
      setPwdLoading(false)
    }
  }

  if (loading || !agent) {
    return <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>
  }

  const creditUsedPercent = agent.credit_limit > 0
    ? Math.min((agent.current_balance / agent.credit_limit) * 100, 100)
    : 0

  return (
    <div>
      <Title level={4}>Account Center</Title>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="Total Orders"
              value={summary?.total_orders || 0}
              prefix={<ShoppingCartOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="Total Revenue"
              value={summary?.total_revenue || 0}
              precision={2}
              prefix={<DollarOutlined />}
              valueStyle={{ color: '#3f8600' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="Pending Payments"
              value={summary?.pending_payments || 0}
              precision={2}
              prefix={<WarningOutlined />}
              valueStyle={{ color: summary && summary.pending_payments > 0 ? '#cf1322' : undefined }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="Available Credit"
              value={agent.available_credit}
              precision={2}
              prefix={<CreditCardOutlined />}
              suffix={agent.currency}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col xs={24} md={14}>
          <Card title="Company Information" style={{ marginBottom: 16 }}>
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="Agent Number">{agent.agent_number}</Descriptions.Item>
              <Descriptions.Item label="Tier">
                <Tag color={tierColors[agent.tier]}>{agent.tier.toUpperCase()}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="Company" span={2}>{agent.company_name}</Descriptions.Item>
              <Descriptions.Item label="Contact Person">{agent.contact_name}</Descriptions.Item>
              <Descriptions.Item label="Email">{agent.email}</Descriptions.Item>
              <Descriptions.Item label="Phone">{agent.phone || '—'}</Descriptions.Item>
              <Descriptions.Item label="Country">{agent.country || '—'}</Descriptions.Item>
              <Descriptions.Item label="City">{agent.city || '—'}</Descriptions.Item>
              <Descriptions.Item label="Address" span={2}>{agent.address || '—'}</Descriptions.Item>
              <Descriptions.Item label="Status">
                <Tag color={agent.status === 'active' ? 'green' : 'orange'}>{agent.status.toUpperCase()}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="Currency">{agent.currency}</Descriptions.Item>
            </Descriptions>
          </Card>

          <Card title="Payment Terms">
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="Commission Rate">{agent.commission_rate}%</Descriptions.Item>
              <Descriptions.Item label="Tier Discount">{agent.discount_percent}%</Descriptions.Item>
              <Descriptions.Item label="Payment Terms">{agent.payment_terms_days} days</Descriptions.Item>
              <Descriptions.Item label="Credit Limit">${agent.credit_limit.toFixed(2)}</Descriptions.Item>
              <Descriptions.Item label="Current Balance" span={2}>
                <div style={{ marginBottom: 8 }}>
                  <Text strong>${agent.current_balance.toFixed(2)}</Text>
                  <Text type="secondary" style={{ marginLeft: 8 }}>
                    of ${agent.credit_limit.toFixed(2)} limit
                  </Text>
                </div>
                <Progress
                  percent={Math.round(creditUsedPercent)}
                  status={creditUsedPercent > 80 ? 'exception' : 'active'}
                  size="small"
                />
              </Descriptions.Item>
              {summary?.payment_due_date && (
                <Descriptions.Item label="Next Payment Due" span={2}>
                  <Text type="warning">{summary.payment_due_date}</Text>
                </Descriptions.Item>
              )}
            </Descriptions>
          </Card>
        </Col>

        <Col xs={24} md={10}>
          <Card title="Change Password">
            <Form form={pwdForm} layout="vertical" onFinish={handleChangePassword}>
              <Form.Item
                name="old_password"
                label="Current Password"
                rules={[{ required: true, message: 'Please input current password' }]}
              >
                <Input.Password />
              </Form.Item>
              <Form.Item
                name="new_password"
                label="New Password"
                rules={[
                  { required: true, message: 'Please input new password' },
                  { min: 8, message: 'Password must be at least 8 characters' },
                ]}
              >
                <Input.Password />
              </Form.Item>
              <Form.Item
                name="confirm_password"
                label="Confirm New Password"
                dependencies={['new_password']}
                rules={[
                  { required: true, message: 'Please confirm new password' },
                  ({ getFieldValue }) => ({
                    validator(_, value) {
                      if (!value || getFieldValue('new_password') === value) {
                        return Promise.resolve()
                      }
                      return Promise.reject(new Error('Passwords do not match'))
                    },
                  }),
                ]}
              >
                <Input.Password />
              </Form.Item>
              <Form.Item>
                <Button type="primary" htmlType="submit" loading={pwdLoading} block>
                  Update Password
                </Button>
              </Form.Item>
            </Form>
          </Card>

          <Card title="Need Help?" style={{ marginTop: 16 }}>
            <Text type="secondary">
              For questions about pricing, orders, or your account, contact our B2B support team:
            </Text>
            <Divider style={{ margin: '12px 0' }} />
            <div>
              <Text strong>Email: </Text>
              <a href="mailto:partners@nuotaooutdoor.com">partners@nuotaooutdoor.com</a>
            </div>
            <div style={{ marginTop: 4 }}>
              <Text strong>Response Time: </Text>
              <Text>Within 24 hours (Mon-Fri)</Text>
            </div>
          </Card>
        </Col>
      </Row>
    </div>
  )
}
