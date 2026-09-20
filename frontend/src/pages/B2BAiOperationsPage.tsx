import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  InputNumber,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  DollarOutlined,
  FileSearchOutlined,
  ReloadOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { ApiError, request } from '../api/client'
import { useAuth } from '../auth/AuthProvider'

const { Title, Text, Paragraph } = Typography

interface AgentRecord {
  id: string
  agent_id: string
  name: string
  domain: string
  status: string
  permission_level: string
  business_scope: string
  description: string | null
  updated_at: string
}

interface AgentTask {
  id: string
  agent_id: string | null
  status: string
  business_scope: string
  input: Record<string, unknown>
  result: Record<string, unknown>
  error_message: string | null
  created_at: string
  completed_at: string | null
}

interface RFQ {
  id: string
  rfq_number: string
  status: string
  requested_currency: string
  created_at: string
}

interface RFQResponse {
  items: RFQ[]
  total: number
}

const agents = [
  {
    agentId: 'b2b_sales_agent',
    title: 'B2B Sales Agent',
    description: '按询盘时效、阶段和金额识别优先跟进机会。',
    actionLabel: '生成销售优先级',
    icon: <FileSearchOutlined />,
  },
  {
    agentId: 'b2b_quotation_agent',
    title: 'B2B Quotation Agent',
    description: '按已发布阶梯价、MOQ、目标价和到岸成本给出报价建议。',
    actionLabel: '生成报价建议',
    icon: <DollarOutlined />,
  },
  {
    agentId: 'b2b_collection_agent',
    title: 'B2B Collection Agent',
    description: '按账龄、余额和信用占用优先级给出回款跟进建议。',
    actionLabel: '生成回款优先级',
    icon: <ThunderboltOutlined />,
  },
]

const taskStatus: Record<string, { color: string; label: string }> = {
  pending: { color: 'orange', label: '待运行' },
  running: { color: 'blue', label: '运行中' },
  waiting_approval: { color: 'purple', label: '待审批' },
  completed: { color: 'green', label: '已完成' },
  failed: { color: 'red', label: '失败' },
  cancelled: { color: 'default', label: '已取消' },
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  return error instanceof Error ? error.message : '操作失败'
}

function makeIdempotencyKey(prefix: string): string {
  const value =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`
  return `${prefix}-${value}`
}

export default function B2BAiOperationsPage() {
  const { user } = useAuth()
  const [agentRows, setAgentRows] = useState<AgentRecord[]>([])
  const [tasks, setTasks] = useState<AgentTask[]>([])
  const [rfqs, setRfqs] = useState<RFQ[]>([])
  const [selectedRfqId, setSelectedRfqId] = useState<string>()
  const [targetMargin, setTargetMargin] = useState(20)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [agentResponse, taskResponse, submitted, inReview] = await Promise.all([
        request<AgentRecord[]>('/agent-registry?business_scope=B2B'),
        request<AgentTask[]>('/agent-tasks?business_scope=B2B&limit=100'),
        request<RFQResponse>('/admin/b2b/rfqs?page=1&page_size=200&status=submitted'),
        request<RFQResponse>('/admin/b2b/rfqs?page=1&page_size=200&status=in_review'),
      ])
      setAgentRows(agentResponse)
      setTasks(taskResponse)
      setRfqs([...(submitted.items || []), ...(inReview.items || [])])
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const agentByCode = useMemo(
    () => new Map(agentRows.map((agent) => [agent.agent_id, agent])),
    [agentRows],
  )
  const agentNameById = useMemo(
    () => new Map(agentRows.map((agent) => [agent.id, agent.name])),
    [agentRows],
  )

  const bootstrap = async () => {
    setSubmitting('bootstrap')
    try {
      await request('/agent-registry/b2b/bootstrap', {
        method: 'POST',
        body: JSON.stringify({ actor: user?.username || 'admin' }),
      })
      message.success('B2B Agents 已初始化')
      await load()
    } catch (requestError) {
      message.error(errorMessage(requestError))
    } finally {
      setSubmitting(null)
    }
  }

  const createTask = async (
    agentId: string,
    input: Record<string, unknown>,
    actionKey: string,
  ) => {
    const agent = agentByCode.get(agentId)
    if (!agent) {
      message.error('Agent 尚未初始化')
      return
    }
    setSubmitting(actionKey)
    try {
      await request('/agent-tasks', {
        method: 'POST',
        body: JSON.stringify({
          agent_id: agent.id,
          business_scope: 'B2B',
          input,
          priority: 3,
          idempotency_key: makeIdempotencyKey(actionKey),
        }),
      })
      message.success('分析任务已进入队列')
      await load()
    } catch (requestError) {
      message.error(errorMessage(requestError))
    } finally {
      setSubmitting(null)
    }
  }

  const columns: ColumnsType<AgentTask> = [
    {
      title: 'Agent',
      dataIndex: 'agent_id',
      width: 190,
      render: (value: string | null) => (value ? agentNameById.get(value) || value : '-'),
    },
    {
      title: '任务输入',
      dataIndex: 'input',
      render: (value: Record<string, unknown>) => (
        <Text code>{JSON.stringify(value).slice(0, 120)}</Text>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string) => {
        const item = taskStatus[value] || { color: 'default', label: value }
        return <Tag color={item.color}>{item.label}</Tag>
      },
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 170,
      render: (value: string) => new Date(value).toLocaleString('zh-CN'),
    },
    {
      title: '错误',
      dataIndex: 'error_message',
      width: 220,
      ellipsis: true,
      render: (value: string | null) => value || '-',
    },
  ]

  const completedCount = tasks.filter((task) => task.status === 'completed').length
  const pendingCount = tasks.filter((task) =>
    ['pending', 'running', 'waiting_approval'].includes(task.status),
  ).length

  return (
    <div>
      {error && <Alert type="error" showIcon title={error} style={{ marginBottom: 16 }} />}

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} md={8}>
          <Card>
            <Statistic
              title="已注册 B2B Agent"
              value={agentRows.length}
              prefix={<RobotOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card>
            <Statistic title="队列中任务" value={pendingCount} />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card>
            <Statistic title="已完成分析" value={completedCount} />
          </Card>
        </Col>
      </Row>

      <Card
        title="B2B 专业 Agent"
        extra={
          <Space>
            <Button
              icon={<SafetyCertificateOutlined />}
              loading={submitting === 'bootstrap'}
              onClick={bootstrap}
            >
              初始化
            </Button>
            <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>
              刷新
            </Button>
          </Space>
        }
        style={{ marginBottom: 16 }}
      >
        <Row gutter={[16, 16]}>
          {agents.map((definition) => {
            const registered = agentByCode.get(definition.agentId)
            return (
              <Col xs={24} xl={8} key={definition.agentId}>
                <Card
                  size="small"
                  title={
                    <Space>
                      {definition.icon}
                      <span>{definition.title}</span>
                    </Space>
                  }
                  extra={
                    <Tag color={registered ? 'green' : 'default'}>
                      {registered ? '已启用' : '未初始化'}
                    </Tag>
                  }
                >
                  <Paragraph type="secondary">{definition.description}</Paragraph>
                  <Space orientation="vertical" style={{ width: '100%' }}>
                    <Text>
                      权限：{registered?.permission_level || 'L2'} · 业务范围：B2B
                    </Text>
                    {definition.agentId === 'b2b_quotation_agent' && (
                      <Space orientation="vertical" style={{ width: '100%' }}>
                        <Select
                          showSearch
                          optionFilterProp="label"
                          placeholder="选择待报价 RFQ"
                          value={selectedRfqId}
                          onChange={setSelectedRfqId}
                          options={rfqs.map((rfq) => ({
                            value: rfq.id,
                            label: `${rfq.rfq_number} · ${rfq.status}`,
                          }))}
                          style={{ width: '100%' }}
                        />
                        <InputNumber
                          min={0}
                          max={100}
                          value={targetMargin}
                          onChange={(value) => setTargetMargin(value || 0)}
                          formatter={(value) =>
                            value === undefined || value === null ? '' : `${value}%`
                          }
                          parser={(value) =>
                            Number(value?.replace('%', '').trim() || 0)
                          }
                          placeholder="目标毛利"
                          style={{ width: '100%' }}
                        />
                      </Space>
                    )}
                    <Button
                      type="primary"
                      block
                      disabled={
                        !registered ||
                        (definition.agentId === 'b2b_quotation_agent' && !selectedRfqId)
                      }
                      loading={submitting === definition.agentId}
                      onClick={() => {
                        if (definition.agentId === 'b2b_sales_agent') {
                          void createTask(
                            definition.agentId,
                            { action: 'pipeline_review', stale_days: 3 },
                            definition.agentId,
                          )
                        } else if (definition.agentId === 'b2b_quotation_agent') {
                          void createTask(
                            definition.agentId,
                            {
                              rfq_id: selectedRfqId,
                              target_margin_percent: targetMargin,
                              valid_days: 14,
                            },
                            definition.agentId,
                          )
                        } else {
                          void createTask(
                            definition.agentId,
                            { action: 'collections_review', overdue_only: false },
                            definition.agentId,
                          )
                        }
                      }}
                    >
                      {definition.actionLabel}
                    </Button>
                  </Space>
                </Card>
              </Col>
            )
          })}
        </Row>
      </Card>

      <Card
        title={
          <Space>
            <Title level={5} style={{ margin: 0 }}>
              B2B Agent 任务
            </Title>
            <Tag color="blue">Human-in-the-loop</Tag>
          </Space>
        }
      >
        {tasks.length === 0 ? (
          <Empty description="暂无 B2B Agent 任务" />
        ) : (
          <Table
            rowKey="id"
            columns={columns}
            dataSource={tasks}
            loading={loading}
            size="small"
            pagination={{ pageSize: 10 }}
            scroll={{ x: 900 }}
          />
        )}
      </Card>
    </div>
  )
}
