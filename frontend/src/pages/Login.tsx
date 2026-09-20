import { useEffect, useState } from 'react'
import { Alert, Button, Form, Input, Typography } from 'antd'
import { LockOutlined, SafetyCertificateOutlined, UserOutlined } from '@ant-design/icons'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthProvider'

const { Title, Text } = Typography

interface LoginValues {
  username: string
  password: string
}

export default function LoginPage() {
  const { login, authenticated, loading } = useAuth()
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const nextPath = searchParams.get('next') || '/dashboard'

  useEffect(() => {
    if (!loading && authenticated) {
      navigate(nextPath, { replace: true })
    }
  }, [authenticated, loading, navigate, nextPath])

  const handleSubmit = async (values: LoginValues) => {
    setSubmitting(true)
    setError(null)
    try {
      await login(values.username.trim(), values.password)
      navigate(nextPath, { replace: true })
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '登录失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="login-page">
      <section className="login-page__context">
        <div className="login-page__eyebrow">NUOTAO OUTDOOR</div>
        <h1>
          一套系统，
          <br />
          同时经营零售与批发。
        </h1>
        <p>
          统一商品、供应链、库存、物流和 AI Agent，让 B2C 零售与 B2B
          批发共享同一个经营底座。
        </p>
        <div className="login-page__principles">
          <span>Human in the loop</span>
          <span>数据可追溯</span>
          <span>双业务分流</span>
        </div>
      </section>

      <section className="login-panel">
        <div className="login-panel__mark">
          <SafetyCertificateOutlined />
        </div>
        <Title level={2}>登录经营控制台</Title>
        <Text type="secondary">使用 Nuotao AI OS 管理账号登录</Text>

        {error && <Alert type="error" showIcon title={error} className="login-panel__alert" />}

        <Form<LoginValues>
          layout="vertical"
          size="large"
          initialValues={{ username: '' }}
          onFinish={handleSubmit}
          requiredMark={false}
        >
          <Form.Item
            label="用户名"
            name="username"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input prefix={<UserOutlined />} autoComplete="username" placeholder="管理员用户名" />
          </Form.Item>
          <Form.Item
            label="密码"
            name="password"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              autoComplete="current-password"
              placeholder="登录密码"
            />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={submitting}>
            进入控制台
          </Button>
        </Form>

        <div className="login-panel__footnote">
          登录凭证仅用于向后端换取短期 Token，不会保存在密码字段或日志中。
        </div>
      </section>
    </main>
  )
}
