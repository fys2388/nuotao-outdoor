import { useState, useEffect } from 'react'
import {
  Card, Button, Space, Typography, Input, Modal, message,
  QRCode, Spin, Alert, Divider, Checkbox, Form
} from 'antd'
import {
  SafetyOutlined, CheckCircleOutlined,
  QrcodeOutlined, LockOutlined, CloseOutlined
} from '@ant-design/icons'
import { apiClient } from '../api/client'

const { Title, Text, Paragraph } = Typography

interface MFASecret {
  secret: string
  provisioning_uri: string
  qr_code_base64: string
}

export default function MFASetup() {
  const [secret, setSecret] = useState<MFASecret | null>(null)
  const [loading, setLoading] = useState(false)
  const [verifying, setVerifying] = useState(false)
  const [code, setCode] = useState('')
  const [verified, setVerified] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Generate MFA secret
  const generateSecret = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await apiClient.post('/auth/mfa/setup', {}, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('admin_token')}`
        }
      })
      setSecret(response.data)
      message.success('TOTP 密钥已生成')
    } catch (err: any) {
      setError(err.response?.data?.detail || '生成失败')
      message.error('生成 MFA 密钥失败')
    } finally {
      setLoading(false)
    }
  }

  // Verify MFA code
  const verifyCode = async () => {
    if (!secret || code.length !== 6) {
      message.warning('请输入 6 位验证码')
      return
    }

    setVerifying(true)
    setError(null)
    try {
      const response = await apiClient.post('/auth/mfa/verify-code', {
        code,
        secret: secret.secret
      }, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('admin_token')}`
        }
      })
      
      if (response.data.success) {
        setVerified(true)
        message.success('MFA 验证成功！')
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || '验证失败')
      message.error('验证码错误')
    } finally {
      setVerifying(false)
    }
  }

  // Confirm MFA setup
  const confirmSetup = async () => {
    setShowConfirm(true)
  }

  const handleConfirm = async () => {
    try {
      // TODO: Store secret in user profile
      message.success('MFA 已启用！')
      setShowConfirm(false)
    } catch (err) {
      message.error('启用失败')
    }
  }

  return (
    <Card title={<><SafetyOutlined /> 多因素认证 (MFA)</>} style={{ maxWidth: 600, margin: '50px auto' }}>
      {!secret ? (
        <div style={{ textAlign: 'center', padding: '40px 0' }}>
          <LockOutlined style={{ fontSize: 48, color: '#1890ff', marginBottom: 24 }} />
          <Paragraph>
            启用 MFA 可以为您的账户提供额外的安全保护。
            使用 TOTP (时间一次性密码) 应用如 Google Authenticator、Authy 等。
          </Paragraph>
          <Button 
            type="primary" 
            size="large"
            icon={<QrcodeOutlined />}
            onClick={generateSecret}
            loading={loading}
          >
            生成 TOTP 密钥
          </Button>
        </div>
      ) : (
        <div>
          <Alert
            message="请扫码并验证"
            description="使用 TOTP 应用扫描下方二维码，然后输入 6 位验证码"
            type="info"
            showIcon
            style={{ marginBottom: 24 }}
          />
          
          <div style={{ textAlign: 'center', marginBottom: 24 }}>
            <QRCode value={secret.provisioning_uri} size={200} />
            <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
              扫码添加认证器
            </Text>
          </div>

          <Divider />

          <Paragraph>
            或者手动输入密钥: <Text code copyable>{secret.secret}</Text>
          </Paragraph>

          <Form layout="inline" style={{ justifyContent: 'center', marginTop: 24 }}>
            <Form.Item>
              <Input
                placeholder="6 位验证码"
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                maxLength={6}
                size="large"
                style={{ width: 200, textAlign: 'center' }}
                disabled={verified}
              />
            </Form.Item>
            <Form.Item>
              <Button
                type="primary"
                size="large"
                icon={<CheckCircleOutlined />}
                onClick={verifyCode}
                loading={verifying}
                disabled={verified}
              >
                验证
              </Button>
            </Form.Item>
          </Form>

          {error && (
            <Alert
              message="验证失败"
              description={error}
              type="error"
              showIcon
              style={{ marginTop: 16 }}
            />
          )}

          {verified && (
            <Alert
              message="验证成功！"
              description="点击确认按钮启用 MFA"
              type="success"
              showIcon
              style={{ marginTop: 16 }}
              action={
                <Button type="primary" onClick={confirmSetup} size="small">
                  确认启用
                </Button>
              }
            />
          )}

          <div style={{ marginTop: 24, textAlign: 'center' }}>
            <Button onClick={generateSecret} disabled={verifying}>
              重新生成密钥
            </Button>
          </div>
        </div>
      )}

      <Modal
        title="确认启用 MFA"
        open={showConfirm}
        onOk={handleConfirm}
        onCancel={() => setShowConfirm(false)}
        okText="确认启用"
        cancelText="取消"
      >
        <p>启用后，每次登录都需要输入 TOTP 验证码。</p>
        <p>请确保已保存备用验证码。</p>
        <Divider />
        <Checkbox>我已了解并确认启用 MFA</Checkbox>
      </Modal>
    </Card>
  )
}