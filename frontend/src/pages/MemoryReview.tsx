import { useState, useEffect, useCallback } from 'react'
import {
  Card,
  Table,
  Tag,
  Row,
  Col,
  Statistic,
  Button,
  Space,
  Typography,
  Input,
  Popconfirm,
  message,
  Tabs,
} from 'antd'
import {
  CheckOutlined,
  CloseOutlined,
  SyncOutlined,
  SafetyCertificateOutlined,
  FileSearchOutlined,
} from '@ant-design/icons'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

const statusColors: Record<string, string> = {
  active: 'green',
  pending_review: 'orange',
  archived: 'default',
}

const statusLabels: Record<string, string> = {
  active: '已生效',
  pending_review: '待审核',
  archived: '已归档',
}

const memoryTypeLabels: Record<string, string> = {
  success_pattern: '成功模式',
  failure_lesson: '失败教训',
  market_insight: '市场洞察',
  customer_preference: '客户偏好',
  optimization_result: '优化结果',
  product_knowledge: '产品知识',
  other: '其他',
}

interface MemoryItem {
  id: number
  agent_id: string
  memory_type: string
  title: string
  content: string
  summary?: string | null
  tags: string[]
  source: string
  confidence: number
  status: string
  created_at?: string | null
}

export default function MemoryReviewPage() {
  const [items, setItems] = useState<MemoryItem[]>([])
  const [stats, setStats] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [rejectReason, setRejectReason] = useState('')
  const [activeTab, setActiveTab] = useState('pending_review')

  const fetchData = useCallback(async (status: string) => {
    setLoading(true)
    try {
      const res = await fetch(`/api/v1/memories?status=${encodeURIComponent(status)}&limit=100`)
      if (res.ok) {
        const data = await res.json()
        setItems(data.items || [])
      }
      const statsRes = await fetch('/api/v1/memories/stats')
      if (statsRes.ok) {
        setStats(await statsRes.json())
      }
    } catch (error) {
      console.error('获取记忆数据失败', error)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData(activeTab)
  }, [activeTab, fetchData])

  const decide = async (id: number, action: 'approve' | 'reject') => {
    try {
      const url = `/api/v1/memories/${id}/${action}`
      const body = action === 'reject' ? `reason=${encodeURIComponent(rejectReason)}` : ''
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body,
      })
      if (res.ok) {
        message.success(action === 'approve' ? '已通过，记忆将注入 Agent 上下文' : '已拒绝，记忆已归档')
        setRejectReason('')
        fetchData(activeTab)
      } else {
        message.error(`操作失败: ${res.status}`)
      }
    } catch (error) {
      message.error('网络错误')
    }
  }

  const columns = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      width: 260,
      render: (v: string, r: MemoryItem) => (
        <Space direction="vertical" size={2}>
          <Text strong>{v}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{r.summary || '-'}</Text>
        </Space>
      ),
    },
    {
      title: '类型',
      dataIndex: 'memory_type',
      key: 'memory_type',
      width: 110,
      render: (v: string) => <Tag color="blue">{memoryTypeLabels[v] || v}</Tag>,
    },
    {
      title: 'Agent',
      dataIndex: 'agent_id',
      key: 'agent_id',
      width: 130,
      render: (v: string) => <Text code>{v}</Text>,
    },
    {
      title: '置信度',
      dataIndex: 'confidence',
      key: 'confidence',
      width: 90,
      render: (v: number) => (
        <Tag color={v >= 0.7 ? 'green' : v >= 0.3 ? 'orange' : 'red'}>{(v * 100).toFixed(0)}%</Tag>
      ),
    },
    {
      title: '来源',
      dataIndex: 'source',
      key: 'source',
      width: 130,
      render: (v: string) => <Text type="secondary">{v}</Text>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (v: string) => <Tag color={statusColors[v] || 'default'}>{statusLabels[v] || v}</Tag>,
    },
    {
      title: '内容',
      dataIndex: 'content',
      key: 'content',
      ellipsis: true,
      render: (v: string) => <Paragraph ellipsis={{ rows: 2 }} style={{ marginBottom: 0 }}>{v}</Paragraph>,
    },
    {
      title: '操作',
      key: 'action',
      width: 170,
      render: (_: any, r: MemoryItem) =>
        r.status === 'pending_review' ? (
          <Space>
            <Popconfirm
              title="确认通过该记忆？"
              description="通过后置信度提升至 ≥70% 并注入 Agent 上下文"
              onConfirm={() => decide(r.id, 'approve')}
            >
              <Button size="small" type="primary" icon={<CheckOutlined />}>
                通过
              </Button>
            </Popconfirm>
            <Popconfirm
              title="确认拒绝该记忆？"
              description={rejectReason ? `原因: ${rejectReason}` : '未填写原因'}
              onConfirm={() => decide(r.id, 'reject')}
            >
              <Button size="small" danger icon={<CloseOutlined />}>
                拒绝
              </Button>
            </Popconfirm>
          </Space>
        ) : (
          <Text type="secondary">已处理</Text>
        ),
    },
  ]

  return (
    <div>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={4}>
          <Card size="small">
            <Statistic title="记忆总数" value={stats?.total ?? '-'} prefix={<FileSearchOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic
              title="待人工审核"
              value={stats?.pending_review ?? '-'}
              valueStyle={{ color: '#fa8c16' }}
              prefix={<SafetyCertificateOutlined />}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic
              title="平均置信度"
              value={stats?.avg_confidence != null ? (stats.avg_confidence * 100).toFixed(0) : '-'}
              suffix="%"
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="累计注入次数" value={stats?.total_accesses ?? '-'} />
          </Card>
        </Col>
      </Row>

      <Card
        title={
          <Space>
            <Title level={5} style={{ margin: 0 }}>
              成长记忆审核
            </Title>
            <Button icon={<SyncOutlined />} onClick={() => fetchData(activeTab)}>
              刷新
            </Button>
            <TextArea
              placeholder="拒绝原因（选填，审计留痕）"
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              style={{ width: 260, height: 28 }}
              autoSize={false}
            />
          </Space>
        }
      >
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            { key: 'pending_review', label: `待审核 (${stats?.pending_review ?? 0})` },
            { key: 'active', label: '已生效' },
            { key: 'archived', label: '已归档' },
          ]}
        />
        <Table
          columns={columns}
          dataSource={items}
          rowKey="id"
          loading={loading}
          size="small"
          pagination={{ pageSize: 10 }}
          scroll={{ x: 1100 }}
        />
      </Card>
    </div>
  )
}
