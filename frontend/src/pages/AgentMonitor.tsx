import { useState, useEffect, useCallback } from 'react'
import {
  Card,
  Table,
  Tag,
  Row,
  Col,
  Statistic,
  Select,
  Button,
  Space,
  Typography,
  Tooltip,
} from 'antd'
import {
  SyncOutlined,
  RobotOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  DollarOutlined,
  ThunderboltOutlined,
  ApiOutlined,
} from '@ant-design/icons'

const { Title, Text } = Typography
const { Option } = Select

const statusColors: Record<string, string> = {
  completed: 'green',
  running: 'blue',
  pending: 'orange',
  failed: 'red',
  approved: 'cyan',
  rejected: 'magenta',
  cancelled: 'default',
}

const statusLabels: Record<string, string> = {
  completed: '已完成',
  running: '运行中',
  pending: '待运行',
  failed: '失败',
  approved: '已批准',
  rejected: '已拒绝',
  cancelled: '已取消',
}

interface Execution {
  id: string
  agent_id?: string | null
  task_id?: string | null
  provider?: string | null
  model?: string | null
  tokens: Record<string, number>
  cost?: string | number | null
  latency_ms?: number | null
  status: string
  error_message?: string | null
  trace_id?: string | null
  started_at?: string | null
  completed_at?: string | null
  created_at: string
}

interface Task {
  id: string
  agent_id?: string | null
  name?: string
  status: string
  priority?: string
  created_at: string
}

export default function AgentMonitorPage() {
  const [overview, setOverview] = useState<any>(null)
  const [executions, setExecutions] = useState<Execution[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState<string>('')

  const fetchData = useCallback(async (status?: string) => {
    setLoading(true)
    try {
      // 1. 运行时总览
      const overviewRes = await fetch('/api/v1/agent-operations/runtime-overview')
      if (overviewRes.ok) {
        setOverview(await overviewRes.json())
      }

      // 2. 执行历史
      const execQuery = status ? `?status=${encodeURIComponent(status)}&limit=100` : '?limit=100'
      const execRes = await fetch(`/api/v1/agent-runtime/agent-executions${execQuery}`)
      if (execRes.ok) {
        const items = await execRes.json()
        setExecutions(Array.isArray(items) ? items : [])
      }

      // 3. 任务列表
      const taskRes = await fetch('/api/v1/agent-runtime/agent-tasks?limit=50')
      if (taskRes.ok) {
        const items = await taskRes.json()
        setTasks(Array.isArray(items) ? items : [])
      }
    } catch (error) {
      console.error('获取 Agent 运行数据失败', error)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData(statusFilter)
  }, [statusFilter, fetchData])

  const execStats = overview?.executions || {}
  const costInfo = overview?.cost || {}
  const costValue =
    typeof costInfo === 'object' && costInfo !== null
      ? Number(costInfo.total_usd ?? costInfo.total ?? 0)
      : 0

  const columns = [
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (v: string) => new Date(v).toLocaleString('zh-CN'),
    },
    {
      title: 'Agent',
      dataIndex: 'agent_id',
      key: 'agent_id',
      width: 140,
      render: (v: string | null) => (
        <Space size={4}>
          <RobotOutlined style={{ color: '#1890ff' }} />
          <Text>{v ? String(v).slice(0, 18) : '-'}</Text>
        </Space>
      ),
    },
    {
      title: '模型',
      key: 'model',
      width: 140,
      render: (_: any, r: Execution) => (
        <Space size={4}>
          <ApiOutlined style={{ color: '#722ed1' }} />
          <Text>{r.model || '-'}</Text>
          {r.provider && <Tag color="purple">{r.provider}</Tag>}
        </Space>
      ),
    },
    {
      title: 'Tokens',
      dataIndex: 'tokens',
      key: 'tokens',
      width: 100,
      render: (t: Record<string, number>) => (
        <Text>{t?.total_tokens ?? t?.completion_tokens ?? '-'}</Text>
      ),
    },
    {
      title: '成本 ($)',
      key: 'cost',
      width: 100,
      render: (_: any, r: Execution) => (
        <Text>{typeof r.cost === 'number' ? r.cost.toFixed(5) : r.cost ?? '-'}</Text>
      ),
    },
    {
      title: '延迟 (ms)',
      dataIndex: 'latency_ms',
      key: 'latency_ms',
      width: 90,
      render: (v: number | null) => v ?? '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (s: string) => (
        <Tag color={statusColors[s] || 'default'}>{statusLabels[s] || s}</Tag>
      ),
    },
    {
      title: 'Trace',
      dataIndex: 'trace_id',
      key: 'trace_id',
      width: 140,
      render: (v: string | null) =>
        v ? (
          <Tooltip title={v}>
            <Text code>{v.slice(0, 12)}...</Text>
          </Tooltip>
        ) : (
          '-'
        ),
    },
  ]

  const taskColumns = [
    {
      title: '任务',
      dataIndex: 'name',
      key: 'name',
      width: 220,
      render: (v: string | undefined, r: Task) => <Text strong>{v || r.id.slice(0, 12)}</Text>,
    },
    {
      title: 'Agent',
      dataIndex: 'agent_id',
      key: 'agent_id',
      width: 140,
      render: (v: string | null) => (v ? String(v).slice(0, 18) : '-'),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (s: string) => (
        <Tag color={statusColors[s] || 'default'}>{statusLabels[s] || s}</Tag>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (v: string) => new Date(v).toLocaleString('zh-CN'),
    },
  ]

  return (
    <div>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={4}>
          <Card size="small">
            <Statistic
              title="Agent 注册数"
              value={overview?.agents?.total ?? overview?.agents?.count ?? '-'}
              prefix={<RobotOutlined />}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic
              title="执行总数"
              value={execStats?.total ?? execStats?.count ?? executions.length}
              prefix={<ThunderboltOutlined />}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic
              title="待审批"
              value={overview?.approvals?.pending ?? overview?.approvals?.count ?? '-'}
              valueStyle={{ color: '#fa8c16' }}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic
              title="累计成本 ($)"
              value={costValue}
              precision={4}
              valueStyle={{ color: '#cf1322' }}
              prefix={<DollarOutlined />}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic
              title="成功率"
              value={overview?.success_rate != null ? (overview.success_rate * 100).toFixed(1) : '-'}
              suffix="%"
              valueStyle={{ color: '#52c41a' }}
              prefix={<CheckCircleOutlined />}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic
              title="失败率"
              value={overview?.failure_rate != null ? (overview.failure_rate * 100).toFixed(1) : '-'}
              suffix="%"
              valueStyle={{ color: '#ff4d4f' }}
              prefix={<CloseCircleOutlined />}
            />
          </Card>
        </Col>
      </Row>

      <Card
        title={
          <Space>
            <Title level={5} style={{ margin: 0 }}>
              Agent 运行历史
            </Title>
            <Select
              value={statusFilter}
              onChange={setStatusFilter}
              style={{ width: 130 }}
              allowClear
              placeholder="全部状态"
            >
              <Option value="completed">已完成</Option>
              <Option value="running">运行中</Option>
              <Option value="failed">失败</Option>
              <Option value="pending">待运行</Option>
            </Select>
            <Button icon={<SyncOutlined />} onClick={() => fetchData(statusFilter)}>
              刷新
            </Button>
          </Space>
        }
        style={{ marginBottom: 16 }}
      >
        <Table
          columns={columns}
          dataSource={executions}
          rowKey="id"
          loading={loading}
          size="small"
          pagination={{ pageSize: 10, showSizeChanger: true }}
          scroll={{ x: 1100 }}
        />
      </Card>

      <Card
        title={
          <Space>
            <Title level={5} style={{ margin: 0 }}>
              Agent 任务队列
            </Title>
          </Space>
        }
      >
        <Table
          columns={taskColumns}
          dataSource={tasks}
          rowKey="id"
          size="small"
          pagination={{ pageSize: 10 }}
          scroll={{ x: 700 }}
        />
      </Card>
    </div>
  )
}
