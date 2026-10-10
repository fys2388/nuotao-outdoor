import { useState, useEffect, useCallback } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Select, Drawer, Descriptions,
  Statistic, Row, Col, message, Modal, Alert, Badge, Tooltip, Empty, Divider,
  Input,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  ReloadOutlined, CheckOutlined, CloseOutlined, InboxOutlined,
  ExperimentOutlined, PauseCircleOutlined, StopOutlined, SendOutlined,
  EyeOutlined, ThunderboltOutlined,
} from '@ant-design/icons'

const { Text, Paragraph } = Typography
const { TextArea } = Input

/**
 * 阶段⑧ AI 决策 + 人审（ADR IDENTITY-002 §7）
 *
 * 契约来源（已核对后端实际实现）：
 * - `backend/app/api/v1/endpoints/selection.py`
 * - `backend/app/services/selection_manager_service.py`
 *
 * 重要事实（实施时修正了 ADR 的过度承诺）：
 * - 后端 `ProductDecision` **不含 veto 规则字段**。V1–V12 的 pass/fail/pending
 *   三态目前只存在于 `hotfix-listing-gate/`（未应用的补丁目录），主后端无实现。
 *   因此本页展示后端真实返回的 `reasons` / `risks` / `score`，不伪造闸门明细。
 * - 后端只支持 **approve / reject** 两个动作，无「请求修改」端点。
 *   拒绝时可填写原因（`reject_reason`），用于回流到 risks。
 */

// ---------------------------------------------------------------------------
// 类型 —— 严格对齐后端返回结构，字段名禁止改写
// ---------------------------------------------------------------------------

interface RecommendationScore {
  total: number
  profit: number
  logistics: number
  demand: number
  competition: number
  differentiation: number
  compliance: number
}

interface Recommendation {
  product_id: string
  product_name: string
  sku: string
  category?: string | null
  candidate_status?: string | null
  score: RecommendationScore
  recommendation: 'strong_buy' | 'buy' | 'watch' | 'reject'
  recommendation_label: string
  suggested_action: 'test' | 'hold' | 'reject'
  reasons: string[]
  risks: string[]
  suggested_test_quantity: number | null
  suggested_test_days: number | null
  scored_at?: string | null
}

interface RecommendationPayload {
  recommendations: Recommendation[]
  stats: {
    total_scanned: number
    meeting_threshold: number
    strong_buy: number
    buy: number
    watch: number
    reject: number
  }
  thresholds: Record<string, number>
  generated_at: string
}

type DecisionType = 'test' | 'hold' | 'reject'
type ApprovalStatus = 'pending' | 'approved' | 'rejected'

interface SelectionDecision {
  id: string
  product_id: string
  decision: DecisionType
  score: number | null
  confidence: number | null
  reasons: string[]
  risks: string[]
  recommended_price: number | null
  test_quantity: number | null
  test_days: number | null
  approval_status: ApprovalStatus
  approved_by?: string | null
  approved_at?: string | null
  created_at?: string | null
}

interface DecisionListPayload {
  decisions: SelectionDecision[]
  total: number
  limit: number
  offset: number
}

// ---------------------------------------------------------------------------
// 展示常量
// ---------------------------------------------------------------------------

const DECISION_META: Record<DecisionType, { text: string; color: string; icon: JSX.Element }> = {
  test: { text: '试销', color: 'blue', icon: <ExperimentOutlined /> },
  hold: { text: '观望', color: 'default', icon: <PauseCircleOutlined /> },
  reject: { text: '拒绝', color: 'red', icon: <StopOutlined /> },
}

const APPROVAL_META: Record<ApprovalStatus, { text: string; color: string }> = {
  pending: { text: '待审批', color: 'gold' },
  approved: { text: '已通过', color: 'green' },
  rejected: { text: '已拒绝', color: 'red' },
}

const REC_META: Record<Recommendation['recommendation'], { color: string }> = {
  strong_buy: { color: 'green' },
  buy: { color: 'blue' },
  watch: { color: 'gold' },
  reject: { color: 'red' },
}

const APPROVED_BY = 'admin'

// ---------------------------------------------------------------------------
// 组件
// ---------------------------------------------------------------------------

export default function DecisionQueue() {
  const [decisions, setDecisions] = useState<SelectionDecision[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState<'all' | ApprovalStatus>('pending')
  const [typeFilter, setTypeFilter] = useState<'all' | DecisionType>('all')

  const [recommendations, setRecommendations] = useState<Recommendation[]>([])
  const [recStats, setRecStats] = useState<RecommendationPayload['stats'] | null>(null)
  const [recLoading, setRecLoading] = useState(false)

  // 详情抽屉
  const [detailOpen, setDetailOpen] = useState(false)
  const [viewing, setViewing] = useState<SelectionDecision | null>(null)

  // 拒绝原因弹窗
  const [rejecting, setRejecting] = useState<SelectionDecision | null>(null)
  const [rejectReason, setRejectReason] = useState('')

  // 创建决策（从 AI 建议）
  const [creating, setCreating] = useState<Recommendation | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)

  // ---------------- 决策队列 ----------------

  const loadDecisions = useCallback(async () => {
    try {
      setLoading(true)
      const params = new URLSearchParams({ limit: '100' })
      if (statusFilter !== 'all') params.append('approval_status', statusFilter)
      if (typeFilter !== 'all') params.append('decision_type', typeFilter)

      const resp = await fetch(`/api/v1/selection/decisions?${params}`)
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}))
        throw new Error(body?.detail || `HTTP ${resp.status}`)
      }
      const data: DecisionListPayload = await resp.json()
      setDecisions(data.decisions || [])
      setTotal(data.total || 0)
    } catch (e) {
      console.error('Load decisions error:', e)
      message.error(e instanceof Error ? e.message : '加载决策队列失败')
    } finally {
      setLoading(false)
    }
  }, [statusFilter, typeFilter])

  // ---------------- AI 建议 ----------------

  const loadRecommendations = useCallback(async () => {
    try {
      setRecLoading(true)
      const resp = await fetch('/api/v1/selection/recommendations?limit=30&min_score=50')
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}))
        throw new Error(body?.detail || `HTTP ${resp.status}`)
      }
      const data: RecommendationPayload = await resp.json()
      setRecommendations(data.recommendations || [])
      setRecStats(data.stats || null)
    } catch (e) {
      console.error('Load recommendations error:', e)
      message.warning('AI 建议加载失败：' + (e instanceof Error ? e.message : ''))
    } finally {
      setRecLoading(false)
    }
  }, [])

  useEffect(() => {
    loadDecisions()
  }, [loadDecisions])

  useEffect(() => {
    loadRecommendations()
  }, [loadRecommendations])

  // ---------------- 审批动作 ----------------

  const handleApprove = async (decision: SelectionDecision) => {
    setBusyId(decision.id)
    try {
      const resp = await fetch(
        `/api/v1/selection/decisions/${decision.id}/approve`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ approved_by: APPROVED_BY }),
        },
      )
      const body = await resp.json().catch(() => ({}))
      if (!resp.ok) throw new Error(body?.detail || `HTTP ${resp.status}`)
      message.success('已通过，决策已生效')
      setDetailOpen(false)
      loadDecisions()
      loadRecommendations()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '审批失败')
    } finally {
      setBusyId(null)
    }
  }

  const openReject = (decision: SelectionDecision) => {
    setRejecting(decision)
    setRejectReason('')
  }

  const confirmReject = async () => {
    if (!rejecting) return
    if (!rejectReason.trim()) {
      message.warning('请填写拒绝原因，便于回流到产品风险记录')
      return
    }
    setBusyId(rejecting.id)
    try {
      const resp = await fetch(
        `/api/v1/selection/decisions/${rejecting.id}/reject`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            approved_by: APPROVED_BY,
            reject_reason: rejectReason.trim(),
          }),
        },
      )
      const body = await resp.json().catch(() => ({}))
      if (!resp.ok) throw new Error(body?.detail || `HTTP ${resp.status}`)
      message.success('已拒绝')
      setRejecting(null)
      setDetailOpen(false)
      loadDecisions()
      loadRecommendations()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '拒绝操作失败')
    } finally {
      setBusyId(null)
    }
  }

  // ---------------- 从 AI 建议创建决策 ----------------

  const submitCreate = async () => {
    if (!creating) return
    setBusyId(creating.product_id)
    try {
      const resp = await fetch('/api/v1/selection/decisions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          product_id: creating.product_id,
          decision: creating.suggested_action,
          score: creating.score.total,
          reasons: creating.reasons,
          risks: creating.risks,
          test_quantity: creating.suggested_test_quantity,
          test_days: creating.suggested_test_days,
        }),
      })
      const body = await resp.json().catch(() => ({}))
      if (!resp.ok) throw new Error(body?.detail || `HTTP ${resp.status}`)
      message.success('决策已创建，进入审批队列')
      setCreating(null)
      loadDecisions()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '创建决策失败')
    } finally {
      setBusyId(null)
    }
  }

  // ---------------- 决策列 ----------------

  const decisionColumns: ColumnsType<SelectionDecision> = [
    {
      title: '产品',
      dataIndex: 'product_id',
      key: 'product',
      render: (_v, r) => (
        <div>
          <Text strong>{r.product_id.slice(0, 8)}…</Text>
          {r.score != null && (
            <div>
              <Text type="secondary" style={{ fontSize: 12 }}>
                评分 {r.score.toFixed(1)}
                {r.confidence != null ? ` · 置信 ${(r.confidence * 100).toFixed(0)}%` : ''}
              </Text>
            </div>
          )}
        </div>
      ),
    },
    {
      title: '决策',
      dataIndex: 'decision',
      key: 'decision',
      width: 110,
      render: (v: DecisionType) => {
        const m = DECISION_META[v] ?? DECISION_META.hold
        return (
          <Tag color={m.color} icon={m.icon}>
            {m.text}
          </Tag>
        )
      },
    },
    {
      title: '建议参数',
      key: 'params',
      width: 180,
      render: (_v, r) => {
        if (r.decision === 'test') {
          return (
            <Text type="secondary" style={{ fontSize: 12 }}>
              {r.test_quantity ?? '-'} 件 / {r.test_days ?? '-'} 天
              {r.recommended_price != null ? ` / ¥${r.recommended_price}` : ''}
            </Text>
          )
        }
        return <Text type="secondary">—</Text>
      },
    },
    {
      title: '理由 / 风险',
      key: 'reasons_risks',
      width: 200,
      render: (_v, r) => (
        <div style={{ fontSize: 12, lineHeight: 1.6 }}>
          {r.reasons?.length > 0 && (
            <Tooltip title={r.reasons.join('；')} placement="topLeft">
              <div style={{ color: '#389e0d' }}>
                理由 {(r.reasons.length) > 2 ? r.reasons.slice(0, 2).join('；') + '…' : r.reasons.join('；')}
              </div>
            </Tooltip>
          )}
          {r.risks?.length > 0 && (
            <Tooltip title={r.risks.join('；')} placement="topLeft">
              <div style={{ color: '#cf1322' }}>
                风险 {(r.risks.length) > 2 ? r.risks.slice(0, 2).join('；') + '…' : r.risks.join('；')}
              </div>
            </Tooltip>
          )}
          {(!r.reasons?.length && !r.risks?.length) && <Text type="secondary">—</Text>}
        </div>
      ),
    },
    {
      title: '状态',
      dataIndex: 'approval_status',
      key: 'status',
      width: 100,
      render: (v: ApprovalStatus) => {
        const m = APPROVAL_META[v] ?? APPROVAL_META.pending
        return <Tag color={m.color}>{m.text}</Tag>
      },
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 150,
      render: (v?: string) => v ? <Text type="secondary" style={{ fontSize: 12 }}>{new Date(v).toLocaleString('zh-CN')}</Text> : <Text type="secondary">—</Text>,
    },
    {
      title: '操作',
      key: 'action',
      width: 150,
      fixed: 'right',
      render: (_v, r) => (
        <Space size="small">
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => {
              setViewing(r)
              setDetailOpen(true)
            }}
          >
            详情
          </Button>
          {r.approval_status === 'pending' && (
            <>
              <Button
                size="small"
                type="primary"
                icon={<CheckOutlined />}
                loading={busyId === r.id}
                onClick={() => handleApprove(r)}
              >
                通过
              </Button>
              <Button
                size="small"
                danger
                icon={<CloseOutlined />}
                disabled={busyId === r.id}
                onClick={() => openReject(r)}
              >
                拒绝
              </Button>
            </>
          )}
        </Space>
      ),
    },
  ]

  // ---------------- 建议列 ----------------

  const recommendationColumns: ColumnsType<Recommendation> = [
    {
      title: '产品',
      dataIndex: 'product_name',
      key: 'name',
      ellipsis: true,
      render: (v: string, r) => (
        <div>
          <Text strong>{v}</Text>
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {r.sku}
              {r.category ? ` · ${r.category}` : ''}
            </Text>
          </div>
        </div>
      ),
    },
    {
      title: '总分',
      dataIndex: ['score', 'total'],
      key: 'total',
      width: 90,
      sorter: (a: Recommendation, b: Recommendation) => a.score.total - b.score.total,
      defaultSortOrder: 'descend',
      render: (v: number) => <Text strong style={{ fontSize: 15 }}>{v.toFixed(1)}</Text>,
    },
    {
      title: '建议',
      dataIndex: 'recommendation_label',
      key: 'recommendation',
      width: 100,
      render: (_v, r) => (
        <Tag color={REC_META[r.recommendation]?.color ?? 'default'}>
          {r.recommendation_label}
        </Tag>
      ),
    },
    {
      title: '建议动作',
      dataIndex: 'suggested_action',
      key: 'action',
      width: 100,
      render: (v: DecisionType) => {
        const m = DECISION_META[v] ?? DECISION_META.hold
        return (
          <Tag color={m.color} icon={m.icon}>
            {m.text}
          </Tag>
        )
      },
    },
    {
      title: '评分明细',
      key: 'dims',
      width: 220,
      render: (_v, r) => (
        <div style={{ fontSize: 12, lineHeight: 1.5 }}>
          <span>利润 {r.score.profit}</span> · <span>物流 {r.score.logistics}</span> ·{' '}
          <span>需求 {r.score.demand}</span> · <span>竞争 {r.score.competition}</span> ·{' '}
          <span>合规 {r.score.compliance}</span>
        </div>
      ),
    },
    {
      title: '候选状态',
      dataIndex: 'candidate_status',
      key: 'candidate_status',
      width: 110,
      render: (v?: string | null) =>
        v ? <Tag>{v}</Tag> : <Tag color="orange">渠道导入·未经候选评审</Tag>,
    },
    {
      title: '操作',
      key: 'op',
      width: 110,
      fixed: 'right',
      render: (_v, r) => (
        <Button
          size="small"
          type="primary"
          ghost
          icon={<SendOutlined />}
          loading={busyId === r.product_id}
          onClick={() => setCreating(r)}
        >
          转决策
        </Button>
      ),
    },
  ]

  // ---------------- 渲染 ----------------

  return (
    <div>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="Human-in-the-loop：AI 只产出建议，通过 / 拒绝必须由人确认"
        description="本页数据来自 /api/v1/selection/*。AI 建议（下方）需先「转决策」进入队列，再由人审批。拒绝时填写的原因会回流到该产品的 risks 记录。"
      />

      <Divider style={{ margin: '8px 0 16px' }} />

      <Card
        title={
          <Space>
            <InboxOutlined />
            <span>决策审批队列</span>
            <Badge count={decisions.filter((d) => d.approval_status === 'pending').length} color="gold" />
          </Space>
        }
        extra={
          <Space>
            <Select
              size="small"
              value={statusFilter}
              onChange={setStatusFilter}
              style={{ width: 120 }}
              options={[
                { value: 'pending', label: '待审批' },
                { value: 'approved', label: '已通过' },
                { value: 'rejected', label: '已拒绝' },
                { value: 'all', label: '全部' },
              ]}
            />
            <Select
              size="small"
              value={typeFilter}
              onChange={setTypeFilter}
              style={{ width: 120 }}
              options={[
                { value: 'all', label: '全部动作' },
                { value: 'test', label: '试销' },
                { value: 'hold', label: '观望' },
                { value: 'reject', label: '拒绝' },
              ]}
            />
            <Button icon={<ReloadOutlined />} loading={loading} onClick={loadDecisions}>
              刷新
            </Button>
          </Space>
        }
      >
        <Table<SelectionDecision>
          rowKey="id"
          columns={decisionColumns}
          dataSource={decisions}
          loading={loading}
          pagination={false}
          scroll={{ x: 900 }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="审批队列为空。可在下方「AI 选品建议」中点击「转决策」创建。"
              />
            ),
          }}
        />
      </Card>

      <Card
        title={
          <Space>
            <ThunderboltOutlined />
            <span>AI 选品建议</span>
            <Text type="secondary" style={{ fontSize: 12, fontWeight: 'normal' }}>
              按最新产品评分生成，非持久化决策
            </Text>
          </Space>
        }
        extra={
          <Button icon={<ReloadOutlined />} loading={recLoading} onClick={loadRecommendations}>
            重新生成
          </Button>
        }
        style={{ marginTop: 16 }}
      >
        {recStats && (
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={4}>
              <Statistic title="扫描评分数" value={recStats.total_scanned} />
            </Col>
            <Col span={4}>
              <Statistic title="达标" value={recStats.meeting_threshold} />
            </Col>
            <Col span={4}>
              <Statistic title="强烈推荐" value={recStats.strong_buy} valueStyle={{ color: '#389e0d' }} />
            </Col>
            <Col span={4}>
              <Statistic title="推荐" value={recStats.buy} valueStyle={{ color: '#1677ff' }} />
            </Col>
            <Col span={4}>
              <Statistic title="观察" value={recStats.watch} valueStyle={{ color: '#d48806' }} />
            </Col>
            <Col span={4}>
              <Statistic title="建议拒绝" value={recStats.reject} valueStyle={{ color: '#cf1322' }} />
            </Col>
          </Row>
        )}
        <Table<Recommendation>
          rowKey="product_id"
          columns={recommendationColumns}
          dataSource={recommendations}
          loading={recLoading}
          pagination={false}
          scroll={{ x: 1000 }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="暂无达标建议。需先有产品评分数据（ProductScore）。"
              />
            ),
          }}
        />
      </Card>

      {/* 详情抽屉 */}
      <Drawer
        title={
          viewing ? (
            <Space>
              <span>决策详情</span>
              {viewing && (
                <Tag color={(APPROVAL_META[viewing.approval_status] ?? APPROVAL_META.pending).color}>
                  {(APPROVAL_META[viewing.approval_status] ?? APPROVAL_META.pending).text}
                </Tag>
              )}
            </Space>
          ) : '决策详情'
        }
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        width={560}
        footer={
          viewing && viewing.approval_status === 'pending' ? (
            <Space>
              <Button
                type="primary"
                icon={<CheckOutlined />}
                loading={busyId === viewing.id}
                onClick={() => handleApprove(viewing)}
              >
                通过
              </Button>
              <Button danger icon={<CloseOutlined />} onClick={() => openReject(viewing)}>
                拒绝
              </Button>
            </Space>
          ) : null
        }
      >
        {viewing && (
          <div>
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label="决策 ID">
                <Text copyable style={{ fontSize: 12 }}>{viewing.id}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="产品 ID">
                <Text copyable style={{ fontSize: 12 }}>{viewing.product_id}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="决策类型">
                {(() => {
                  const m = DECISION_META[viewing.decision] ?? DECISION_META.hold
                  return <Tag color={m.color} icon={m.icon}>{m.text}</Tag>
                })()}
              </Descriptions.Item>
              <Descriptions.Item label="评分">
                {viewing.score != null ? viewing.score.toFixed(1) : '—'}
              </Descriptions.Item>
              <Descriptions.Item label="置信度">
                {viewing.confidence != null
                  ? `${(viewing.confidence * 100).toFixed(0)}%`
                  : <Text type="secondary">后端未提供</Text>}
              </Descriptions.Item>
              <Descriptions.Item label="建议售价">
                {viewing.recommended_price != null ? `¥${viewing.recommended_price}` : '—'}
              </Descriptions.Item>
              <Descriptions.Item label="测试数量 / 天数">
                {viewing.decision === 'test'
                  ? `${viewing.test_quantity ?? '-'} 件 / ${viewing.test_days ?? '-'} 天`
                  : '—'}
              </Descriptions.Item>
              <Descriptions.Item label="审批人">
                {viewing.approved_by ?? '—'}
              </Descriptions.Item>
              <Descriptions.Item label="审批时间">
                {viewing.approved_at ? new Date(viewing.approved_at).toLocaleString('zh-CN') : '—'}
              </Descriptions.Item>
              <Descriptions.Item label="创建时间">
                {viewing.created_at ? new Date(viewing.created_at).toLocaleString('zh-CN') : '—'}
              </Descriptions.Item>
            </Descriptions>

            <Divider style={{ margin: '16px 0 12px' }} />

            {viewing.reasons?.length > 0 && (
              <>
                <Text strong>决策理由</Text>
                <Paragraph style={{ margin: '6px 0 14px' }}>
                  {viewing.reasons.map((r, i) => (
                    <div key={i} style={{ color: '#389e0d', fontSize: 13, lineHeight: 1.8 }}>
                      · {r}
                    </div>
                  ))}
                </Paragraph>
              </>
            )}

            {viewing.risks?.length > 0 && (
              <>
                <Text strong>风险提示</Text>
                <Paragraph style={{ margin: '6px 0 14px' }}>
                  {viewing.risks.map((r, i) => (
                    <div key={i} style={{ color: '#cf1322', fontSize: 13, lineHeight: 1.8 }}>
                      · {r}
                    </div>
                  ))}
                </Paragraph>
              </>
            )}

            {viewing.reasons?.length === 0 && viewing.risks?.length === 0 && (
              <Alert
                type="warning"
                showIcon
                message="该决策未携带理由或风险记录"
                description="创建决策时未传入 reasons / risks，建议在拒绝时补充原因以回流到产品风险记录。"
              />
            )}

            <Alert
              type="info"
              showIcon
              style={{ marginTop: 8 }}
              message="闸门明细未接入"
              description="V1–V12 Hard Rules 的逐条 pass/fail/pending 结果目前未包含在决策载荷中（实现位于 hotfix-listing-gate/ 补丁目录，尚未应用）。本页只展示后端真实返回的评分、理由与风险，不伪造闸门状态。"
            />
          </div>
        )}
      </Drawer>

      {/* 拒绝原因弹窗 */}
      <Modal
        title="拒绝该决策"
        open={rejecting !== null}
        onOk={confirmReject}
        onCancel={() => setRejecting(null)}
        okText="确认拒绝"
        okButtonProps={{ danger: true, loading: rejecting ? busyId === rejecting.id : false }}
        cancelText="取消"
      >
        {rejecting && (
          <div>
            <Paragraph style={{ marginBottom: 12 }}>
              产品 <Text strong>{rejecting.product_id.slice(0, 8)}…</Text> · 决策{' '}
              {(() => {
                const m = DECISION_META[rejecting.decision] ?? DECISION_META.hold
                return <Tag color={m.color}>{m.text}</Tag>
              })()}
            </Paragraph>
            <Text>拒绝原因（必填，将追加到该决策的 risks 记录）：</Text>
            <TextArea
              rows={3}
              style={{ marginTop: 8 }}
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="例如：利润率低于目标，暂不试销"
              maxLength={500}
              showCount
            />
          </div>
        )}
      </Modal>

      {/* 从建议创建决策弹窗 */}
      <Modal
        title="转入选品决策队列"
        open={creating !== null}
        onOk={submitCreate}
        onCancel={() => setCreating(null)}
        okText="创建决策"
        okButtonProps={{ loading: creating ? busyId === creating.product_id : false }}
        cancelText="取消"
      >
        {creating && (
          <div>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="产品">{creating.product_name}</Descriptions.Item>
              <Descriptions.Item label="SKU">{creating.sku}</Descriptions.Item>
              <Descriptions.Item label="总分">
                <Text strong>{creating.score.total.toFixed(1)}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="AI 建议">
                <Tag color={REC_META[creating.recommendation]?.color ?? 'default'}>
                  {creating.recommendation_label}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="建议动作">
                {(() => {
                  const m = DECISION_META[creating.suggested_action] ?? DECISION_META.hold
                  return <Tag color={m.color} icon={m.icon}>{m.text}</Tag>
                })()}
              </Descriptions.Item>
              {creating.suggested_test_quantity != null && (
                <Descriptions.Item label="建议测试">
                  {creating.suggested_test_quantity} 件 / {creating.suggested_test_days} 天
                </Descriptions.Item>
              )}
            </Descriptions>
            {creating.reasons?.length > 0 && (
              <Paragraph style={{ marginTop: 12, marginBottom: 4 }}>
                <Text strong>将带入的理由：</Text>
                {creating.reasons.map((r, i) => (
                  <div key={i} style={{ color: '#389e0d', fontSize: 13, lineHeight: 1.8 }}>
                    · {r}
                  </div>
                ))}
              </Paragraph>
            )}
            {creating.risks?.length > 0 && (
              <Paragraph style={{ marginTop: 8, marginBottom: 0 }}>
                <Text strong>将带入的风险：</Text>
                {creating.risks.map((r, i) => (
                  <div key={i} style={{ color: '#cf1322', fontSize: 13, lineHeight: 1.8 }}>
                    · {r}
                  </div>
                ))}
              </Paragraph>
            )}
            <Alert
              type="info"
              showIcon
              style={{ marginTop: 12 }}
              message="创建后状态为 pending，仍需人工审批"
            />
          </div>
        )}
      </Modal>
    </div>
  )
}
