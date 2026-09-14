import { Button, Result } from 'antd'
import { useNavigate } from 'react-router-dom'

export default function NotFoundPage() {
  const navigate = useNavigate()

  return (
    <Result
      status="404"
      title="页面不存在"
      subTitle="当前地址没有对应的经营模块，请从左侧导航重新进入。"
      extra={
        <Button type="primary" onClick={() => navigate('/dashboard')}>
          返回经营总览
        </Button>
      }
    />
  )
}
