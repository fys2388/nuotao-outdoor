import { useState, useEffect } from 'react'
import {
  Card,
  Table,
  Tag,
  Button,
  Space,
  Modal,
  Descriptions,
  message,
  Select,
  Row,
  Col,
  Statistic,
  Divider,
  Typography,
} from 'antd'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  SyncOutlined,
  RobotOutlined,
} from '@ant-design/icons'

const { Title, Text } = Typography
const { Option } = Select

interface AgentSuggestion {
  id: string
  agent_id: string
  suggestion_type: string
  title: string
  description: string
  priority: string
  status: string
  risk_level: string
  execution_action: string
  execution_params: Record<string, any>
  expected_impact: string
  created_at: string
  approved_at?: string
  executed_at?: string
  execution_result?: Record<string, any>
}

const API_BASE = '/api/v1/agent-suggestions'

const statusColors: Record<string, string> = {
  pending_approval: 'orange',
  approved: 'blue',
  rejected: 'red',
  executing: 'cyan',
  completed: 'green',
  failed: 'red',
}

const statusLabels: Record<string, string> = {
  pending_approval: '待审批',
  approved: '已批准',
  rejected: '已拒绝',
  executing: '执行中',
  completed: '已完成',
  failed: '执行失败',
}

const priorityColors: Record<string, string> = {
  high: 'red',
  medium: 'orange',
  low: 'blue',
}

const typeLabels: Record<string, string> = {
  product_optimization: '产品优化',
  marketing_optimization: '营销优化',
  inventory_restock: '库存补货',
  pricing_adjustment: '价格调整',
  listing_optimization: '上架优化',
  customer_operation: '客户运营',
  supply_chain: '供应链优化',
  business_insight: '商业洞察',
}

export default function AgentSuggestionsPage() {
  const [suggestions, setSuggestions] = useState<AgentSuggestion[]>([])
  const [loading, setLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState<string>('pending_approval')
  const [detailModal, setDetailModal] = useState<AgentSuggestion | null>(null)
  const [stats, setStats] = useState({
    pending: 0,
    approved: 0,
    completed: 0,
    failed: 0,
  })

  const fetchSuggestions = async (status?: string) => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ limit: '50' })
      if (status && status !== 'all') {
        params.set('status', status)
      }
      const response = await fetch(`${API_BASE}?${params.toString()}`)
      const data = await response.json()
      setSuggestions(data.items || data || [])

      // 统计
      const allResponse = await fetch(`${API_BASE}?limit=200`)
      const allData = await allResponse.json()
      const all = allData.items || allData || []
      setStats({
        pending: all.filter((s: AgentSuggestion) => s.status === 'pending_approval').length,
        approved: all.filter((s: AgentSuggestion) => s.status === 'approved').length,
        completed: all.filter((s: AgentSuggestion) => s.status === 'completed').length,
        failed: all.filter((s: AgentSuggestion) => s.status === 'failed').length,
      })
    } catch (error) {
      message.error('获取建议列表失败')
      console.error(error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchSuggestions(statusFilter)
  }, [statusFilter])

  const handleApprove = async (id: string) => {
    try {
      await fetch(`${API_BASE}/${id}/approve`, { method: 'POST' })
      message.success('建议已批准')
      fetchSuggestions(statusFilter)
    } catch (error) {
      message.error('批准失败')
      console.error(error)
    }
  }

  const handleReject = async (id: string) => {
    try {
      await fetch(`${API_BASE}/${id}/reject`, { method: 'POST' })
      message.success('建议已拒绝')
      fetchSuggestions(statusFilter)
    } catch (error) {
      message.error('拒绝失败')
      console.error(error)
    }
  }

  const handleExecute = async (id: string) => {
    try {
      const response = await fetch(`${API_BASE}/${id}/execute`, { method: 'POST' })
      const data = await response.json()
      message.success('执行请求已发送')
      console.log('执行结果:', data)
      fetchSuggestions(statusFilter)
    } catch (error) {
      message.error('执行失败')
      console.error(error)
    }
  }

  const columns = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      width: 250,
      render: (text: string, record: AgentSuggestion) => (
        <a onClick={() => setDetailModal(record)}>{text}</a>
      ),
    },
    {
      title: '类型',
      dataIndex: 'suggestion_type',
      key: 'suggestion_type',
      width: 100,
      render: (type: string) => (
        <Tag color="blue">{typeLabels[type] || type}</Tag>
      ),
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      key: 'priority',
      width: 80,
      render: (priority: string) => (
        <Tag color={priorityColors[priority] || 'default'}>
          {priority === 'high' ? '高' : priority === 'medium' ? '中' : '低'}
        </Tag>
      ),
    },
    {
      title: '风险等级',
      dataIndex: 'risk_level',
      key: 'risk_level',
      width: 80,
      render: (risk: string) => (
        <Tag color={risk === 'high' ? 'red' : risk === 'medium' ? 'orange' : 'green'}>
          {risk === 'high' ? '高' : risk === 'medium' ? '中' : '低'}
        </Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={statusColors[status] || 'default'}>
          {statusLabels[status] || status}
        </Tag>
      ),
    },
    {
      title: 'Agent',
      dataIndex: 'agent_id',
      key: 'agent_id',
      width: 120,
      render: (agent: string) => (
        <Space>
          <RobotOutlined />
          <Text>{agent}</Text>
        </Space>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (date: string) => new Date(date).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_: any, record: AgentSuggestion) => (
        <Space size="small">
          {record.status === 'pending_approval' && (
            <>
              <Button
                type="primary"
                size="small"
                icon={<CheckCircleOutlined />}
                onClick={() => handleApprove(record.id)}
              >
                批准
              </Button>
              <Button
                danger
                size="small"
                icon={<CloseCircleOutlined />}
                onClick={() => handleReject(record.id)}
              >
                拒绝
              </Button>
            </>
          )}
          {record.status === 'approved' && (
            <Button
              type="primary"
              size="small"
              icon={<SyncOutlined />}
              onClick={() => handleExecute(record.id)}
            >
              执行
            </Button>
          )}
          <Button size="small" onClick={() => setDetailModal(record)}>
            详情
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="待审批"
              value={stats.pending}
              valueStyle={{ color: '#fa8c16' }}
              prefix={<ClockCircleOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="已批准"
              value={stats.approved}
              valueStyle={{ color: '#1890ff' }}
              prefix={<CheckCircleOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="已完成"
              value={stats.completed}
              valueStyle={{ color: '#52c41a' }}
              prefix={<CheckCircleOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="执行失败"
              value={stats.failed}
              valueStyle={{ color: '#ff4d4f' }}
              prefix={<CloseCircleOutlined />}
            />
          </Card>
        </Col>
      </Row>

      <Card
        title={
          <Space>
            <Title level={4} style={{ margin: 0 }}>
              AI 建议审批中心
            </Title>
            <Select
              value={statusFilter}
              onChange={setStatusFilter}
              style={{ width: 120 }}
            >
              <Option value="pending_approval">待审批</Option>
              <Option value="approved">已批准</Option>
              <Option value="completed">已完成</Option>
              <Option value="failed">执行失败</Option>
              <Option value="all">全部</Option>
            </Select>
            <Button icon={<SyncOutlined />} onClick={() => fetchSuggestions(statusFilter)}>
              刷新
            </Button>
          </Space>
        }
      >
        <Table
          columns={columns}
          dataSource={suggestions}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10, showSizeChanger: true }}
          scroll={{ x: 1200 }}
        />
      </Card>

      <Modal
        title="建议详情"
        open={!!detailModal}
        onCancel={() => setDetailModal(null)}
        footer={
          detailModal?.status === 'pending_approval' ? (
            <Space>
              <Button
                type="primary"
                icon={<CheckCircleOutlined />}
                onClick={() => {
                  handleApprove(detailModal.id)
                  setDetailModal(null)
                }}
              >
                批准并执行
              </Button>
              <Button
                danger
                icon={<CloseCircleOutlined />}
                onClick={() => {
                  handleReject(detailModal.id)
                  setDetailModal(null)
                }}
              >
                拒绝
              </Button>
            </Space>
          ) : (
            <Button onClick={() => setDetailModal(null)}>关闭</Button>
          )
        }
        width={800}
      >
        {detailModal && (
          <div>
            <Descriptions title="基本信息" bordered column={2}>
              <Descriptions.Item label="标题" span={2}>
                {detailModal.title}
              </Descriptions.Item>
              <Descriptions.Item label="类型">
                <Tag color="blue">{typeLabels[detailModal.suggestion_type] || detailModal.suggestion_type}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={statusColors[detailModal.status]}>
                  {statusLabels[detailModal.status] || detailModal.status}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="优先级">
                <Tag color={priorityColors[detailModal.priority]}>
                  {detailModal.priority === 'high' ? '高' : detailModal.priority === 'medium' ? '中' : '低'}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="风险等级">
                <Tag color={detailModal.risk_level === 'high' ? 'red' : detailModal.risk_level === 'medium' ? 'orange' : 'green'}>
                  {detailModal.risk_level === 'high' ? '高' : detailModal.risk_level === 'medium' ? '中' : '低'}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="Agent" span={2}>
                <Space>
                  <RobotOutlined />
                  {detailModal.agent_id}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="执行动作">
                <code>{detailModal.execution_action || '无'}</code>
              </Descriptions.Item>
              <Descriptions.Item label="创建时间">
                {new Date(detailModal.created_at).toLocaleString('zh-CN')}
              </Descriptions.Item>
            </Descriptions>

            <Divider>建议描述</Divider>
            <div style={{ padding: '12px', background: '#f5f5f5', borderRadius: 4 }}>
              <Text>{detailModal.description}</Text>
            </div>

            {detailModal.expected_impact && (
              <>
                <Divider>预期影响</Divider>
                <div style={{ padding: '12px', background: '#e6f7ff', borderRadius: 4 }}>
                  <Text>{detailModal.expected_impact}</Text>
                </div>
              </>
            )}

            {detailModal.execution_params && Object.keys(detailModal.execution_params).length > 0 && (
              <>
                <Divider>执行参数</Divider>
                <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 4, maxHeight: 200, overflow: 'auto' }}>
                  {JSON.stringify(detailModal.execution_params, null, 2)}
                </pre>
              </>
            )}

            {detailModal.execution_result && (
              <>
                <Divider>执行结果</Divider>
                <pre style={{ background: '#f6ffed', padding: 12, borderRadius: 4, maxHeight: 200, overflow: 'auto' }}>
                  {JSON.stringify(detailModal.execution_result, null, 2)}
                </pre>
              </>
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}
