import { Alert, Button, Card, Space, Tag, Typography } from 'antd'
import {
  ApiOutlined,
  ArrowLeftOutlined,
  DatabaseOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'

const { Title, Text, Paragraph } = Typography

interface CapabilityPageProps {
  title: string
  description: string
  requiredApis: string[]
  requiredModels: string[]
  blockers: string[]
}

export default function CapabilityPage({
  title,
  description,
  requiredApis,
  requiredModels,
  blockers,
}: CapabilityPageProps) {
  const navigate = useNavigate()

  return (
    <div className="capability-page">
      <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate('/b2b/overview')}>
        返回 B2B 经营
      </Button>

      <div className="page-heading">
        <div>
          <div className="page-kicker page-kicker--b2b">CAPABILITY GAP</div>
          <Title level={2}>{title}</Title>
          <Paragraph>{description}</Paragraph>
        </div>
        <Tag color="orange">尚未接入</Tag>
      </div>

      <Alert
        type="warning"
        showIcon
        title="当前页面不会展示模拟业务数据"
        description="在前端接入前，必须先完成后端数据模型、状态机、权限、审计和 API 契约。"
        className="page-alert"
      />

      <div className="capability-grid">
        <Card
          variant="borderless"
          title={
            <Space>
              <ApiOutlined />
              必需 API
            </Space>
          }
        >
          <ul className="capability-list">
            {requiredApis.map((item) => (
              <li key={item}>
                <code>{item}</code>
              </li>
            ))}
          </ul>
        </Card>

        <Card
          variant="borderless"
          title={
            <Space>
              <DatabaseOutlined />
              必需数据模型
            </Space>
          }
        >
          <ul className="capability-list">
            {requiredModels.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </Card>

        <Card
          variant="borderless"
          title={
            <Space>
              <SafetyCertificateOutlined />
              上线前置条件
            </Space>
          }
          className="capability-grid__wide"
        >
          <ul className="capability-list">
            {blockers.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </Card>
      </div>

      <Text type="secondary">
        该页面代表产品能力边界，不代表功能已经开发完成。开发前应先更新
        `docs/frontend_b2c_b2b_architecture.md` 和后端 ADR。
      </Text>
    </div>
  )
}
