import { useState, useEffect, useCallback } from 'react'
import {
  Card, Row, Col, Typography, Spin, Empty, Alert, Table, Tag,
  Button, Input, Space,
} from 'antd'
import {
  BookOutlined, SearchOutlined, ReloadOutlined,
  FileTextOutlined, BulbOutlined,
} from '@ant-design/icons'
import { api, ApiError } from '../api/client'

const { Title, Text } = Typography

interface KnowledgeEntry {
  id: string
  type: string
  content: string
  source: string
  confidence: number
  created_at: string
  tags?: string[]
}

interface KnowledgeSummary {
  total_entries: number
  by_type: Record<string, number>
  recent_count: number
  top_tags: string[]
}

export default function CreativeKnowledge() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [entries, setEntries] = useState<KnowledgeEntry[]>([])
  const [summary, setSummary] = useState<KnowledgeSummary | null>(null)
  const [searchQuery, setSearchQuery] = useState('')

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [entriesData, summaryData] = await Promise.all([
        api.getCreativeKnowledgeEntries(50, 0),
        api.getCreativeKnowledgeSummary(),
      ])
      setEntries((entriesData as any).entries || [])
      setSummary(summaryData as KnowledgeSummary)
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`加载失败: ${err.message}`)
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadData()
  }, [loadData])

  const filteredEntries = searchQuery
    ? entries.filter(e =>
        e.content.toLowerCase().includes(searchQuery.toLowerCase()) ||
        e.tags?.some(t => t.toLowerCase().includes(searchQuery.toLowerCase()))
      )
    : entries

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 100 }}>
        <Spin size="large" />
      </div>
    )
  }

  return (
    <div style={{ padding: 24 }}>
      <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <Title level={2} style={{ margin: 0 }}>
            <BookOutlined /> Creative Knowledge
          </Title>
          <Text type="secondary">Prompt 学习与知识库</Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => void loadData()}>刷新</Button>
      </div>

      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} showIcon />}

      {summary && (
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col span={6}>
            <Card size="small">
              <div style={{ textAlign: 'center' }}>
                <Text type="secondary">Total Entries</Text>
                <div style={{ fontSize: 24, fontWeight: 'bold' }}>{summary.total_entries}</div>
              </div>
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <div style={{ textAlign: 'center' }}>
                <Text type="secondary">Recent (7d)</Text>
                <div style={{ fontSize: 24, fontWeight: 'bold' }}>{summary.recent_count}</div>
              </div>
            </Card>
          </Col>
          <Col span={12}>
            <Card size="small" title="Top Tags">
              <Space wrap>
                {summary.top_tags?.map((tag, i) => (
                  <Tag key={i} color="blue">{tag}</Tag>
                )) || <Text type="secondary">No tags</Text>}
              </Space>
            </Card>
          </Col>
        </Row>
      )}

      <Card
        title="Knowledge Entries"
        size="small"
        extra={
          <Input
            placeholder="Search..."
            prefix={<SearchOutlined />}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{ width: 200 }}
          />
        }
      >
        {filteredEntries.length === 0 ? (
          <Empty description="暂无知识条目" />
        ) : (
          <Table
            size="small"
            dataSource={filteredEntries}
            rowKey="id"
            pagination={{ pageSize: 10 }}
            columns={[
              { title: 'Type', dataIndex: 'type', key: 'type', width: 100,
                render: (t: string) => <Tag color="blue">{t}</Tag> },
              { title: 'Content', dataIndex: 'content', key: 'content', ellipsis: true },
              { title: 'Source', dataIndex: 'source', key: 'source', width: 100 },
              { title: 'Confidence', dataIndex: 'confidence', key: 'confidence', width: 100,
                render: (c: number) => <Tag color={c > 0.7 ? 'success' : c > 0.4 ? 'warning' : 'error'}>
                  {(c * 100).toFixed(0)}%
                </Tag> },
              { title: 'Tags', dataIndex: 'tags', key: 'tags', width: 200,
                render: (tags: string[]) => tags?.map((t, i) => <Tag key={i}>{t}</Tag>) || '-' },
              { title: 'Created', dataIndex: 'created_at', key: 'created_at', width: 160,
                render: (d: string) => d ? new Date(d).toLocaleString() : '-' },
            ]}
          />
        )}
      </Card>
    </div>
  )
}