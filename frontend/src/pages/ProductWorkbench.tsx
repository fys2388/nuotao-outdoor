import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Row, Col, Statistic, Badge, Table, Tag, Button, Space, Typography,
  Alert, Spin, Empty, message, Tooltip, Progress, Divider, Select,
} from 'antd'
import {
  ReloadOutlined, RightOutlined, ExclamationCircleOutlined,
  CheckCircleOutlined, ClockCircleOutlined, WarningOutlined,
  ThunderboltOutlined, SearchOutlined, RobotOutlined,
  DeploymentUnitOutlined, ShoppingCartOutlined, GlobalOutlined,
  DatabaseOutlined, TrophyOutlined, InboxOutlined,
} from '@ant-design/icons'
import { api, type WorkbenchSummary, type WorkbenchTask, type RuleResultsResponse } from '../api/client'

const { Title, Text, Paragraph } = Typography

// ── Stage metadata ───────────────────────────────────────────────────
const STAGE_META: Record<string, { label: string; icon: React.ReactNode; color: string }> = {
  candidate: { label: '候选产品', icon: <ThunderboltOutlined />, color: '#faad14' },
  analysis: { label: 'AI 分析中', icon: <RobotOutlined />, color: '#722ed1' },
  pending_approval: { label: '待审批', icon: <ClockCircleOutlined />, color: '#fa8c16' },
  approved: { label: '已批准', icon: <CheckCircleOutlined />, color: '#52c41a' },
  product_master: { label: 'Product Master', icon: <DeploymentUnitOutlined />, color: '#1890ff' },
  listing: { label: '上架中', icon: <ShoppingCartOutlined />, color: '#13c2c2' },
  wc_published: { label: 'WC 已发布', icon: <GlobalOutlined />, color: '#2f54eb' },
  rejected: { label: '已淘汰', icon: <InboxOutlined />, color: '#8c8c8c' },
}

const PRIORITY_META: Record<string, { color: string; label: string }> = {
  high: { color: '#f5222d', label: '高' },
  medium: { color: '#faad14', label: '中' },
  low: { color: '#52c41a', label: '低' },
}

// ── User Stage View derivation (UI-only, priority state machine) ───
// Terminal states must be checked before intermediate states.
// Priority: rejected > wc_published > listing > pending_approval
//           > approved > product_master > analysis > candidate > unknown
function deriveUserStage(product: {
  candidate_status?: string | null
  funnel_stage?: string | null
  mastered_at?: string | null
  status?: string
  wc_status?: string | null
  listing_status?: string | null
}): string {
  // 1. Terminal: rejected
  if (product.candidate_status === 'rejected') return 'rejected'
  
  // 2. Terminal: WC Published
  if (product.wc_status === 'synced') return 'wc_published'
  
  // 3. Intermediate: Listing in progress
  if (product.listing_status && ['pending', 'approved', 'processing'].includes(product.listing_status)) {
    return 'listing'
  }
  
  // 4. Intermediate: Approved (with mastered_at)
  if (product.candidate_status === 'approved' && product.mastered_at) {
    return 'approved'
  }
  
  // 5. Intermediate: Product Master
  if (product.mastered_at) return 'product_master'
  
  // 6. Intermediate: AI Analysis
  if (product.funnel_stage && ['recalled', 'screened', 'deep_candidate'].includes(product.funnel_stage)) {
    return 'analysis'
  }
  
  // 7. Intermediate: Candidate
  if (product.candidate_status === 'candidate') return 'candidate'
  
  // 8. Fallback
  return 'unknown'
}

const STAGE_BADGE: Record<string, { text: string; color: string }> = {
  candidate: { text: '候选', color: 'orange' },
  analysis: { text: 'AI分析中', color: 'purple' },
  pending_approval: { text: '待审批', color: 'warning' },
  approved: { text: '已批准', color: 'success' },
  product_master: { text: 'Product Master', color: 'blue' },
  listing: { text: '上架中', color: 'cyan' },
  wc_published: { text: 'WC 已发布', color: 'geekblue' },
  rejected: { text: '已淘汰', color: 'default' },
}

export default function ProductWorkbench() {
  const navigate = useNavigate()
  const [summary, setSummary] = useState<WorkbenchSummary | null>(null)
  const [tasks, setTasks] = useState<WorkbenchTask[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Filters
  const [filterStage, setFilterStage] = useState<string>('')
  const [filterPriority, setFilterPriority] = useState<string>('')

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [summaryRes, tasksRes] = await Promise.all([
        api.getWorkbenchSummary(),
        api.getWorkbenchTasks(50),
      ])
      setSummary(summaryRes as WorkbenchSummary)
      setTasks(tasksRes as WorkbenchTask[])
    } catch (err: any) {
      const msg = err?.message || '加载数据失败'
      setError(msg)
      message.error(msg)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  const filteredTasks = tasks.filter(t => {
    if (filterStage && t.stage !== filterStage) return false
    if (filterPriority && t.priority !== filterPriority) return false
    return true
  })

  // ── Render ─────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div style={{ padding: 24, textAlign: 'center' }}>
        <Spin size="large" tip="加载产品工作台..." />
      </div>
    )
  }

  if (error && !summary) {
    return (
      <div style={{ padding: 24 }}>
        <Alert
          type="error"
          message="加载失败"
          description={error}
          action={
            <Button type="primary" onClick={loadData} icon={<ReloadOutlined />}>
              重试
            </Button>
          }
        />
      </div>
    )
  }

  return (
    <div style={{ padding: 24 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>产品工作台</Title>
          <Text type="secondary">商品与 AI 选品 — 统一入口</Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
      </div>

      {/* Section 1: Lifecycle Summary */}
      <Card title="生命周期概览" style={{ marginBottom: 24 }}>
        <Row gutter={[16, 16]}>
          {summary?.stages.map(item => {
            const meta = STAGE_META[item.stage] || { label: item.label, icon: <DatabaseOutlined />, color: '#8c8c8c' }
            return (
              <Col key={item.stage} xs={12} sm={8} md={6} lg={3}>
                <Card
                  hoverable
                  style={{ textAlign: 'center', borderColor: meta.color + '40' }}
                  onClick={() => setFilterStage(item.stage)}
                >
                  <div style={{ color: meta.color, fontSize: 20, marginBottom: 8 }}>
                    {meta.icon}
                  </div>
                  <Statistic
                    value={item.count}
                    title={item.label}
                    valueStyle={{ color: item.count > 0 ? meta.color : undefined }}
                  />
                  {item.blocked_count > 0 && (
                    <Badge
                      count={item.blocked_count}
                      style={{ backgroundColor: '#f5222d', marginTop: 4, display: 'block' }}
                      title={`${item.blocked_count} 项阻断`}
                    />
                  )}
                </Card>
              </Col>
            )
          })}
        </Row>
        {summary?.stages.length === 0 && (
          <Empty description="暂无统计数据" style={{ padding: 24 }} />
        )}
      </Card>

      {/* Section 2: Tasks */}
      <Card
        title={
          <Space>
            <ExclamationCircleOutlined style={{ color: '#faad14' }} />
            <span>今日需要处理</span>
            <Text type="secondary">({filteredTasks.length} 项)</Text>
          </Space>
        }
        extra={
          <Space>
            <Select
              placeholder="阶段"
              allowClear
              style={{ width: 120 }}
              value={filterStage || undefined}
              onChange={v => setFilterStage(v || '')}
              options={[
                { value: 'pending_approval', label: '待审批' },
                { value: 'wc_failed', label: 'WC 失败' },
                { value: 'approved', label: '已批准' },
              ]}
            />
            <Select
              placeholder="优先级"
              allowClear
              style={{ width: 100 }}
              value={filterPriority || undefined}
              onChange={v => setFilterPriority(v || '')}
              options={[
                { value: 'high', label: '高' },
                { value: 'medium', label: '中' },
                { value: 'low', label: '低' },
              ]}
            />
          </Space>
        }
      >
        {filteredTasks.length === 0 ? (
          <Empty description="🎉 没有待处理任务" style={{ padding: 24 }} />
        ) : (
          <div>
            {filteredTasks.map(task => {
              const stageBadge = STAGE_BADGE[task.stage] || { text: task.stage, color: 'default' }
              const priorityMeta = PRIORITY_META[task.priority] || { color: '#8c8c8c', label: task.priority }
              return (
                <Card
                  key={task.id}
                  size="small"
                  style={{ marginBottom: 8, borderLeft: `4px solid ${priorityMeta.color}` }}
                  hoverable
                  onClick={() => navigate(`/products/workbench/${task.product_id}`)}
                >
                  <Row gutter={[16, 8]} align="middle">
                    <Col flex="none" style={{ minWidth: 100 }}>
                      <Tag color={stageBadge.color}>{stageBadge.text}</Tag>
                      <div style={{ marginTop: 4 }}>
                        <Badge color={priorityMeta.color} text={priorityMeta.label} />
                      </div>
                    </Col>
                    <Col flex="auto">
                      <div style={{ fontWeight: 600, fontSize: 14 }}>{task.name}</div>
                      <Text type="secondary" style={{ fontSize: 12 }}>SKU: {task.sku}</Text>
                    </Col>
                    <Col flex="none" style={{ maxWidth: 300 }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {task.reason}
                      </Text>
                    </Col>
                    <Col flex="none" style={{ width: 160, textAlign: 'right' }}>
                      <Button
                        type="primary"
                        size="small"
                        icon={<RightOutlined />}
                        style={{ whiteSpace: 'nowrap' }}
                      >
                        {task.next_action}
                      </Button>
                    </Col>
                  </Row>
                </Card>
              )
            })}
          </div>
        )}
      </Card>

      {/* Section 3: Quick Links */}
      <Row gutter={16} style={{ marginTop: 24 }}>
        <Col xs={24} sm={8} md={6}>
          <Card
            hoverable
            onClick={() => navigate('/products/candidates')}
            style={{ height: '100%' }}
          >
            <div style={{ textAlign: 'center', padding: '12px 0' }}>
              <SearchOutlined style={{ fontSize: 24, color: '#1890ff' }} />
              <div style={{ marginTop: 8 }}>候选产品</div>
              <Text type="secondary" style={{ fontSize: 12 }}>查看和管理候选</Text>
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={8} md={6}>
          <Card
            hoverable
            onClick={() => navigate('/products/analysis')}
            style={{ height: '100%' }}
          >
            <div style={{ textAlign: 'center', padding: '12px 0' }}>
              <RobotOutlined style={{ fontSize: 24, color: '#722ed1' }} />
              <div style={{ marginTop: 8 }}>AI 分析</div>
              <Text type="secondary" style={{ fontSize: 12 }}>AI 产品分析报告</Text>
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={8} md={6}>
          <Card
            hoverable
            onClick={() => navigate('/products/costs')}
            style={{ height: '100%' }}
          >
            <div style={{ textAlign: 'center', padding: '12px 0' }}>
              <DeploymentUnitOutlined style={{ fontSize: 24, color: '#13c2c2' }} />
              <div style={{ marginTop: 8 }}>成本与利润</div>
              <Text type="secondary" style={{ fontSize: 12 }}>管理产品成本</Text>
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={8} md={6}>
          <Card
            hoverable
            onClick={() => navigate('/products/listing-jobs')}
            style={{ height: '100%' }}
          >
            <div style={{ textAlign: 'center', padding: '12px 0' }}>
              <ShoppingCartOutlined style={{ fontSize: 24, color: '#2f54eb' }} />
              <div style={{ marginTop: 8 }}>上架工单</div>
              <Text type="secondary" style={{ fontSize: 12 }}>管理上架任务</Text>
            </div>
          </Card>
        </Col>
      </Row>
    </div>
  )
}
