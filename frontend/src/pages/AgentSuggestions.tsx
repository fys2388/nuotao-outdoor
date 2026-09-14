import { useState, useEffect } from 'react'
import {
  Alert,
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
  source: string
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
  approved_by?: string
  approved_at?: string
  approval_comment?: string
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
  b2b_sales_follow_up: 'B2B 询盘跟进',
  b2b_quote_recommendation: 'B2B 报价建议',
  b2b_collection_action: 'B2B 回款跟进',
}

// 行动中心排序权重：high=P0、medium=P1、low=P2，未知优先级排最后。
const priorityRank: Record<string, number> = { high: 0, medium: 1, low: 2 }

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
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])
  const [batchLoading, setBatchLoading] = useState(false)
  // 行动中心：全部待审批建议，按优先级排序后以行动卡呈现。
  const [actionItems, setActionItems] = useState<AgentSuggestion[]>([])

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
      const allItems = allData.items || allData || []
      setStats({
        pending: allItems.filter((s: AgentSuggestion) => s.status === 'pending_approval').length,
        approved: allItems.filter((s: AgentSuggestion) => s.status === 'approved').length,
        completed: allItems.filter((s: AgentSuggestion) => s.status === 'completed').length,
        failed: allItems.filter((s: AgentSuggestion) => s.status === 'failed').length,
      })
      // 行动中心只信任后端 pending_approval 过滤的结果；不能从「前 N 条全量」里筛待办，
      // 因为已完成记录可能占满分页，把待办挤到后面导致漏算（与待审批计数不一致同源）。
      try {
        const pendingResponse = await fetch(`${API_BASE}?status=pending_approval&limit=200`)
        const pendingPayload = await pendingResponse.json()
        const pendingItems = (pendingPayload.items || pendingPayload || []) as AgentSuggestion[]
        setActionItems(
          pendingItems.sort(
            (a, b) => (priorityRank[a.priority] ?? 99) - (priorityRank[b.priority] ?? 99),
          ),
        )
      } catch {
        setActionItems([])
      }
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
      const res = await fetch(`${API_BASE}/${id}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved_by: 'admin', auto_execute: true }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      message.success('建议已批准')
      fetchSuggestions(statusFilter)
    } catch (error) {
      message.error('批准失败')
      console.error(error)
    }
  }

  const handleReject = async (id: string) => {
    try {
      const res = await fetch(`${API_BASE}/${id}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rejected_by: 'admin' }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      message.success('建议已拒绝')
      fetchSuggestions(statusFilter)
    } catch (error) {
      message.error('拒绝失败')
      console.error(error)
    }
  }

  const handleExecute = async (id: string) => {
    try {
      const response = await fetch(`${API_BASE}/${id}/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      message.success('执行请求已发送')
      console.log('执行结果:', data)
      fetchSuggestions(statusFilter)
    } catch (error) {
      message.error('执行失败')
      console.error(error)
    }
  }

  const handleBatchApprove = async () => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先选择要批准的建议')
      return
    }
    setBatchLoading(true)
    let success = 0
    let failed = 0
    for (const id of selectedRowKeys) {
      try {
        const res = await fetch(`${API_BASE}/${id}/approve`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ approved_by: 'admin', auto_execute: true }),
        })
        if (res.ok) success++
        else failed++
      } catch {
        failed++
      }
    }
    message.success(`批量批准完成：成功 ${success} 条，失败 ${failed} 条`)
    setSelectedRowKeys([])
    setBatchLoading(false)
    fetchSuggestions(statusFilter)
  }

  const handleBatchReject = async () => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先选择要拒绝的建议')
      return
    }
    setBatchLoading(true)
    let success = 0
    let failed = 0
    for (const id of selectedRowKeys) {
      try {
        const res = await fetch(`${API_BASE}/${id}/reject`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ rejected_by: 'admin' }),
        })
        if (res.ok) success++
        else failed++
      } catch {
        failed++
      }
    }
    message.success(`批量拒绝完成：成功 ${success} 条，失败 ${failed} 条`)
    setSelectedRowKeys([])
    setBatchLoading(false)
    fetchSuggestions(statusFilter)
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
              {record.execution_action === 'manual_review' ? '确认处理' : '执行'}
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
      <Card
        variant="borderless"
        className="action-center"
        title={
          <Space>
            <RobotOutlined />
            <span>今日待办行动</span>
            <Tag color="orange">{actionItems.length >= 200 ? '200+' : actionItems.length}</Tag>
          </Space>
        }
      >
        {actionItems.length === 0 ? (
          <Alert
            type="success"
            showIcon
            icon={<CheckCircleOutlined />}
            title="当前没有待审批的 AI 行动"
            description="所有建议均已处理；新建议产生后会按 P0 / P1 / P2 优先级出现在这里。"
          />
        ) : (
          (['high', 'medium', 'low'] as const).map((level) => {
            const items = actionItems.filter((s) => s.priority === level)
            if (items.length === 0) return null
            const groupLabel =
              level === 'high' ? 'P0 · 立即处理' : level === 'medium' ? 'P1 · 重点关注' : 'P2 · 备查'
            return (
              <div key={level}>
                <div className="ac-group-title">
                  <Tag color={priorityColors[level] || 'default'}>{groupLabel}</Tag>
                  <Text type="secondary">{items.length} 项</Text>
                </div>
                <div className="ac-list">
                  {items.map((s) => (
                    <div key={s.id} className={`ac-card ac-card--${level}`}>
                      <div className="ac-card-head">
                        <Tag color="blue">{typeLabels[s.suggestion_type] || s.suggestion_type}</Tag>
                        <Tag
                          color={
                            s.risk_level === 'high'
                              ? 'red'
                              : s.risk_level === 'medium'
                                ? 'orange'
                                : 'green'
                          }
                        >
                          风险{s.risk_level === 'high' ? '高' : s.risk_level === 'medium' ? '中' : '低'}
                        </Tag>
                        <Text type="secondary" style={{ fontSize: 11 }}>
                          {s.agent_id}
                        </Text>
                      </div>
                      <div className="ac-card-title">{s.title}</div>
                      {s.description && <div className="ac-card-desc">{s.description}</div>}
                      <div className="ac-card-actions">
                        <Button size="small" onClick={() => setDetailModal(s)}>
                          查看计算
                        </Button>
                        <Button
                          size="small"
                          type="primary"
                          icon={<CheckCircleOutlined />}
                          onClick={() => handleApprove(s.id)}
                        >
                          {s.execution_action === 'manual_review' ? '确认处理' : '批准并执行'}
                        </Button>
                        <Button
                          size="small"
                          danger
                          icon={<CloseCircleOutlined />}
                          onClick={() => handleReject(s.id)}
                        >
                          拒绝
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )
          })
        )}
      </Card>

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
            {selectedRowKeys.length > 0 && (
              <>
                <span style={{ color: '#666' }}>已选 {selectedRowKeys.length} 项</span>
                <Button
                  type="primary"
                  icon={<CheckCircleOutlined />}
                  loading={batchLoading}
                  onClick={handleBatchApprove}
                >
                  批量批准
                </Button>
                <Button
                  danger
                  icon={<CloseCircleOutlined />}
                  loading={batchLoading}
                  onClick={handleBatchReject}
                >
                  批量拒绝
                </Button>
                <Button onClick={() => setSelectedRowKeys([])}>取消选择</Button>
              </>
            )}
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
          rowSelection={{
            selectedRowKeys,
            onChange: (keys) => setSelectedRowKeys(keys),
            getCheckboxProps: (record: AgentSuggestion) => ({
              disabled: record.status !== 'pending_approval',
            }),
          }}
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
                {detailModal.execution_action === 'manual_review'
                  ? '批准建议'
                  : '批准并执行'}
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
                  {detailModal.source === 'b2b_agent' && <Tag color="gold">B2B 人工确认</Tag>}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="来源">
                {detailModal.source === 'b2b_agent' ? 'B2B Agent' : detailModal.source}
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

            {detailModal.approved_at && (
              <>
                <Divider>人工审批记录</Divider>
                <Descriptions bordered column={1} size="small">
                  <Descriptions.Item label="审批人">
                    {detailModal.approved_by || '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label="审批时间">
                    {new Date(detailModal.approved_at).toLocaleString('zh-CN')}
                  </Descriptions.Item>
                  <Descriptions.Item label="审批意见">
                    {detailModal.approval_comment || '无'}
                  </Descriptions.Item>
                </Descriptions>
              </>
            )}

            {detailModal.execution_params?.evidence && (
              <>
                <Divider>决策证据</Divider>
                <Alert
                  type="warning"
                  showIcon
                  title="仅作业务建议，不会自动报价、改价、发送催收或核销应收"
                  style={{ marginBottom: 12 }}
                />
                <pre
                  style={{
                    background: '#fffbe6',
                    padding: 12,
                    borderRadius: 4,
                    maxHeight: 320,
                    overflow: 'auto',
                  }}
                >
                  {JSON.stringify(detailModal.execution_params.evidence, null, 2)}
                </pre>
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
