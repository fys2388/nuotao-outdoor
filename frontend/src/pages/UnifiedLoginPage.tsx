import { useEffect, useState } from 'react'
import { Alert, Button, Form, Input, message, Space, Typography } from 'antd'
import { LockOutlined, UserOutlined } from '@ant-design/icons'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { portalApi, setPortalToken } from '../api/b2bPortal'
import { login as adminLogin } from '../auth/AuthProvider'

const { Title, Text } = Typography

interface LoginValues {
  email: string
  password: string
}

export default function UnifiedLoginPage() {
  const [form] = Form.useForm<LoginValues>()
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const nextPath = searchParams.get('next') || '/dashboard'

  // Check if already authenticated
  useEffect(() => {
    const adminToken = localStorage.getItem('admin_token')
    const portalToken = localStorage.getItem('portal_token')
    
    if (adminToken) {
      navigate(nextPath, { replace: true })
    } else if (portalToken) {
      navigate('/portal', { replace: true })
    }
  }, [navigate, nextPath])

  const handleSubmit = async (values: LoginValues) => {
    setSubmitting(true)
    setError(null)

    try {
      // First try B2B portal login
      try {
        const portalResponse = await portalApi.login(values.email, values.password)
        setPortalToken(portalResponse.access_token)
        message.success(`欢迎回来，${portalResponse.agent.company_name}`)
        navigate('/portal', { replace: true })
        return
      } catch (portalError: any) {
        // 仅当 B2B 明确返回"账号状态类"错误时才提示并终止；其余（401/404/网络等）fall through 到 admin 登录
        const detail = typeof portalError?.detail === 'string' ? portalError.detail : ''
        const isPortalStatusError = ['pending', 'rejected', 'suspended', 'verify'].some((k) =>
          detail.includes(k),
        )
        if (isPortalStatusError) {
          if (detail.includes('pending')) {
            setError('您的申请正在审核中，请耐心等待。')
          } else if (detail.includes('rejected')) {
            setError('您的申请已被拒绝，请联系管理员。')
          } else if (detail.includes('suspended')) {
            setError('您的账号已被暂停，请联系客服。')
          } else {
            setError('请先验证您的邮箱地址，请检查收件箱中的验证链接。')
          }
          return
        }
      }

      // Fall back to admin login
      try {
        await adminLogin(values.email.trim(), values.password)
        message.success('登录成功')
        navigate(nextPath, { replace: true })
      } catch (adminError) {
        setError('用户名或密码错误，或您没有访问该系统的权限')
      }
    } finally {
      // 无论成功失败都复位 loading（成功路径 navigate 后复位无害，React 18 无卸载警告）
      setSubmitting(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: '#f0f2f5', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ maxWidth: '400px', width: '100%', padding: '20px' }}>
        {/* Brand */}
        <div style={{ textAlign: 'center', marginBottom: '32px' }}>
          <div style={{ fontSize: '32px', fontWeight: 700, color: '#1890ff', marginBottom: '8px' }}>
            NUOTAO OUTDOOR
          </div>
          <Text type="secondary">AI-Driven Outdoor Commerce OS</Text>
          <div style={{ marginTop: '16px' }}>
            <Text type="secondary" style={{ fontSize: '12px' }}>
              一套系统 · 双业务模式 · 权限隔离
            </Text>
          </div>
        </div>

        {/* Login Card */}
        <div style={{ background: '#fff', borderRadius: '8px', padding: '32px', boxShadow: '0 2px 8px rgba(0,0,0,0.08)' }}>
          <Title level={4} style={{ marginBottom: '24px', textAlign: 'center' }}>
            统一登录
          </Title>

          {error && (
            <Alert
              message={error}
              type="error"
              showIcon
              style={{ marginBottom: '16px' }}
            />
          )}

          <Form
            form={form}
            layout="vertical"
            onFinish={() => void handleSubmit(form.getFieldsValue())}
            initialValues={{ email: '', password: '' }}
          >
            <Form.Item
              name="email"
              label="邮箱"
              rules={[
                { required: true, message: '请输入邮箱' },
                { type: 'email', message: '邮箱格式不正确' },
              ]}
            >
              <Input
                prefix={<UserOutlined />}
                placeholder="name@company.com"
                size="large"
                autoComplete="username"
              />
            </Form.Item>

            <Form.Item
              name="password"
              label="密码"
              rules={[{ required: true, message: '请输入密码' }]}
            >
              <Input.Password
                prefix={<LockOutlined />}
                placeholder="••••••••"
                size="large"
                autoComplete="current-password"
              />
            </Form.Item>

            <Button
              type="primary"
              htmlType="submit"
              size="large"
              block
              loading={submitting}
              style={{ marginTop: '8px' }}
            >
              登录
            </Button>
          </Form>

          {/* Info Section */}
          <div style={{ marginTop: '24px', paddingTop: '24px', borderTop: '1px solid #f0f0f0' }}>
            <Text type="secondary" style={{ display: 'block', textAlign: 'center', marginBottom: '16px', fontSize: '12px' }}>
              不同身份使用相同邮箱登录，系统将自动识别您的角色
            </Text>
            
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div style={{ padding: '12px', background: '#e6f7ff', borderRadius: '6px', textAlign: 'center' }}>
                <div style={{ fontSize: '20px', marginBottom: '4px' }}>🏢</div>
                <Text strong style={{ fontSize: '12px' }}>内部运营</Text>
                <div style={{ fontSize: '10px', color: '#666' }}>商品/订单/供应链</div>
              </div>
              <div style={{ padding: '12px', background: '#f6ffed', borderRadius: '6px', textAlign: 'center' }}>
                <div style={{ fontSize: '20px', marginBottom: '4px' }}>🤝</div>
                <Text strong style={{ fontSize: '12px' }}>合作伙伴</Text>
                <div style={{ fontSize: '10px', color: '#666' }}>批发价/询盘/合同</div>
              </div>
            </div>
          </div>
        </div>

        {/* Footer Links */}
        <div style={{ textAlign: 'center', marginTop: '24px' }}>
          <Space direction="vertical" size="small">
            <Button 
              type="link" 
              size="small" 
              onClick={() => navigate('/portal/register')}
            >
              还没有合作伙伴账号？立即申请
            </Button>
            <Button 
              type="link" 
              size="small" 
              onClick={() => window.open('https://nuotaooutdoor.com', '_blank')}
            >
              前往零售商城
            </Button>
          </Space>
        </div>
      </div>
    </div>
  )
}
