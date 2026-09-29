import { useState, useEffect, useCallback } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Card, Row, Col, Tag, Button, Space, Typography, Spin, Empty, Alert,
  Descriptions, Tabs, Table, Badge, Divider, Tooltip, Progress, Statistic,
  Timeline, List, message, Modal, Input, Checkbox, Form,
} from 'antd'
import {
  ArrowLeftOutlined, ReloadOutlined, CheckCircleOutlined,
  CloseCircleOutlined, MinusCircleOutlined, QuestionCircleOutlined,
  WarningOutlined, RightOutlined, SyncOutlined,
  ThunderboltOutlined, RobotOutlined, CalculatorOutlined,
  AuditOutlined, DatabaseOutlined, ShoppingCartOutlined,
  GlobalOutlined, ClockCircleOutlined, ExclamationCircleOutlined,
  PlusOutlined,
} from '@ant-design/icons'
import {
  api,
  type RuleResultsResponse,
  type WcStatusResponse,
  type ProductDecisionRequest,
  type ProductDecisionResult,
  type DecisionType,
} from '../api/client'

const { Title, Text, Paragraph } = Typography

// ── Stage derivation (UI-only, priority state machine) ──────────────
// Terminal states must be checked before intermediate states.
// Priority order: rejected > wc_published > listing > pending_approval
//                 > approved > product_master > analysis > candidate > unknown
function deriveUserStage(product: {
  candidate_status?: string | null
  funnel_stage?: string | null
  mastered_at?: string | null
  status?: string
  wc_status?: string | null  // From /wc-status endpoint
  listing_status?: string | null  // From listing job info
}): string {
  // 1. Terminal: rejected
  if (product.candidate_status === 'rejected') return 'rejected'
  
  // 2. Terminal: WC Published (needs wc_status from separate API)
  if (product.wc_status === 'synced') return 'wc_published'
  
  // 3. Intermediate: Listing in progress (needs listing_status)
  if (product.listing_status && ['pending', 'approved', 'processing'].includes(product.listing_status)) {
    return 'listing'
  }
  
  // 4. Intermediate: Pending Approval (needs decision info)
  // Note: pending_approval requires joining with ProductDecision, not available in product object
  // This would be determined by the workbench summary or tasks API
  
  // 5. Intermediate: Approved (candidate_status = approved AND mastered_at)
  if (product.candidate_status === 'approved' && product.mastered_at) {
    return 'approved'
  }
  
  // 6. Intermediate: Product Master (mastered_at IS NOT NULL)
  if (product.mastered_at) return 'product_master'
  
  // 7. Intermediate: AI Analysis (funnel_stage in recalled/screened/deep_candidate)
  if (product.funnel_stage && ['recalled', 'screened', 'deep_candidate'].includes(product.funnel_stage)) {
    return 'analysis'
  }
  
  // 8. Intermediate: Candidate (candidate_status = candidate)
  if (product.candidate_status === 'candidate') return 'candidate'
  
  // 9. Fallback
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
  unknown: { text: '未知', color: 'default' },
}

const RESULT_META: Record<string, { icon: React.ReactNode; color: string; label: string }> = {
  PASS: { icon: <CheckCircleOutlined />, color: '#52c41a', label: 'PASS' },
  FAIL: { icon: <CloseCircleOutlined />, color: '#f5222d', label: 'FAIL' },
  UNKNOWN: { icon: <MinusCircleOutlined />, color: '#faad14', label: 'UNKNOWN' },
}

export default function ProductDecisionCockpit() {
  const { productId } = useParams<{ productId: string }>()
  const navigate = useNavigate()

  const [product, setProduct] = useState<any | null>(null)
  const [ruleResults, setRuleResults] = useState<RuleResultsResponse | null>(null)
  const [wcStatus, setWcStatus] = useState<WcStatusResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState('facts')

  // Decision state
  const [decisionModalOpen, setDecisionModalOpen] = useState(false)
  const [decisionModalType, setDecisionModalType] = useState<DecisionType | null>(null)
  const [decisionSubmitting, setDecisionSubmitting] = useState(false)
  const [decisionReason, setDecisionReason] = useState('')
  const [supplementFields, setSupplementFields] = useState<string[]>([])
  const [decisionResult, setDecisionResult] = useState<ProductDecisionResult | null>(null)
  const [decisionResultModalOpen, setDecisionResultModalOpen] = useState(false)

  // Supplement data options
  const SUPPLEMENT_OPTIONS = [
    { label: '零售价 (Retail Price)', value: 'retail_price' },
    { label: '采购成本 (Purchase Cost)', value: 'purchase_cost' },
    { label: '重量 (Weight)', value: 'weight' },
    { label: '尺寸 (Dimensions)', value: 'dimensions' },
    { label: '品牌 (Brand)', value: 'brand' },
    { label: '供应商信息 (Supplier)', value: 'supplier' },
    { label: '库存信息 (Inventory)', value: 'inventory' },
    { label: '物流信息 (Shipping)', value: 'shipping' },
  ]

  const loadData = useCallback(async () => {
    if (!productId) return
    setLoading(true)
    setError(null)
    try {
      // Load product, rule results, and WC status in parallel
      const [productRes, ruleRes, wcRes] = await Promise.allSettled([
        api.getProductById(productId),
        api.getRuleResults(productId),
        api.getWcStatus(productId),
      ])

      if (productRes.status === 'fulfilled' && productRes.value) {
        setProduct(productRes.value)
      }

      if (ruleRes.status === 'fulfilled' && ruleRes.value) {
        setRuleResults(ruleRes.value as RuleResultsResponse)
      }
      if (wcRes.status === 'fulfilled' && wcRes.value) {
        setWcStatus(wcRes.value as WcStatusResponse)
      }
    } catch (err: any) {
      const msg = err?.message || '加载产品详情失败'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [productId])

  useEffect(() => {
    loadData()
  }, [loadData])

  // Decision handlers
  const openDecisionModal = useCallback((decisionType: DecisionType) => {
    setDecisionModalType(decisionType)
    setDecisionReason('')
    setSupplementFields([])
    setDecisionModalOpen(true)
  }, [])

  const closeDecisionModal = useCallback(() => {
    setDecisionModalOpen(false)
    setDecisionModalType(null)
  }, [])

  const handleDecisionSubmit = useCallback(async () => {
    if (!productId || !decisionModalType) return

    setDecisionSubmitting(true)
    try {
      const body: ProductDecisionRequest = {
        decision: decisionModalType,
        actor: 'test-admin', // TODO: Get from auth context
      }

      if (decisionReason.trim()) {
        body.reason = decisionReason.trim()
      }

      if (decisionModalType === 'SUPPLEMENT_DATA') {
        if (supplementFields.length === 0) {
          message.warning('请至少选择一个需要补充的字段')
          return
        }
        body.supplement_fields = supplementFields
      }

      const result = await api.applyProductDecision(productId, body)
      setDecisionResult(result)
      setDecisionResultModalOpen(true)
      closeDecisionModal()

      if (result.success) {
        message.success(`决策成功：${result.current_status}`)
        // Refresh product data
        setTimeout(() => loadData(), 500)
      } else {
        message.error(`决策失败：${result.error || '未知错误'}`)
      }
    } catch (err: any) {
      message.error(err?.message || '决策提交失败')
    } finally {
      setDecisionSubmitting(false)
    }
  }, [productId, decisionModalType, decisionReason, supplementFields, closeDecisionModal, loadData])

  // Determine which decision buttons to show based on current stage
  const getAvailableDecisions = (): DecisionType[] => {
    if (!product) return []

    const status = product.candidate_status

    // Terminal states: no decisions available
    if (status === 'winner' || status === 'rejected') return []

    // Available decisions for all non-terminal states
    const decisions: DecisionType[] = ['SUPPLEMENT_DATA']

    // CONTINUE and APPROVE for non-terminal states
    if (status !== 'winner') {
      decisions.push('CONTINUE', 'APPROVE')
    }

    // REJECT for non-terminal states
    if (status !== 'rejected') {
      decisions.push('REJECT')
    }

    return decisions
  }

  if (loading && !product) {
    return (
      <div style={{ padding: 24, textAlign: 'center' }}>
        <Spin size="large" tip="加载产品详情..." />
      </div>
    )
  }

  if (error && !product) {
    return (
      <div style={{ padding: 24 }}>
        <Alert
          type="error"
          message="加载失败"
          description={error}
          action={
            <Button type="primary" onClick={() => { loadData(); navigate('/products/workbench') }} icon={<ReloadOutlined />}>
              返回工作台
            </Button>
          }
        />
      </div>
    )
  }

  const userStage = product ? deriveUserStage(product) : 'unknown'
  const stageBadge = STAGE_BADGE[userStage] || { text: userStage, color: 'default' }

  // Determine next action based on stage
  const getNextAction = (): { text: string; path: string } => {
    switch (userStage) {
      case 'candidate':
        return { text: '启动 AI 分析', path: '/products/analysis' }
      case 'analysis':
        return { text: '等待分析完成', path: '' }
      case 'approved':
        return { text: '生成 B2C Listing', path: '/products/listing' }
      case 'product_master':
        return { text: '同步到 WooCommerce', path: '/products/listing-jobs' }
      case 'rejected':
        return { text: '查看淘汰原因', path: '' }
      default:
        return { text: '查看详情', path: '' }
    }
  }
  const nextAction = getNextAction()

  return (
    <div style={{ padding: 24 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <Space>
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate('/products/workbench')}
          >
            返回工作台
          </Button>
          <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
        </Space>
        <div style={{ textAlign: 'right' }}>
          <Title level={5} style={{ margin: 0 }}>
            {product?.name || '加载中...'}
          </Title>
          {product?.sku && <Text type="secondary">SKU: {product.sku}</Text>}
        </div>
      </div>

      {/* Status Bar */}
      <Card style={{ marginBottom: 24 }}>
        <Row gutter={[24, 16]} align="middle">
          <Col xs={24} sm={6} md={4}>
            <div>
              <Text type="secondary">当前阶段</Text>
              <div style={{ marginTop: 4 }}>
                <Tag color={stageBadge.color} style={{ fontSize: 14, padding: '4px 12px' }}>
                  {stageBadge.text}
                </Tag>
              </div>
            </div>
          </Col>
          <Col xs={24} sm={6} md={4}>
            <div>
              <Text type="secondary">当前状态</Text>
              <div style={{ marginTop: 4 }}>
                <Tag>{product?.status || '—'}</Tag>
                {product?.candidate_status && (
                  <Tag style={{ marginLeft: 4 }}>{product.candidate_status}</Tag>
                )}
              </div>
            </div>
          </Col>
          <Col xs={24} sm={12} md={8} style={{ textAlign: 'right' }}>
            <Text type="secondary">下一步主动作</Text>
            <div style={{ marginTop: 4 }}>
              {nextAction.path ? (
                <Button
                  type="primary"
                  size="large"
                  icon={<RightOutlined />}
                  onClick={() => navigate(nextAction.path)}
                  style={{ fontSize: 14 }}
                >
                  {nextAction.text}
                </Button>
              ) : (
                <Text type="secondary">{nextAction.text}</Text>
              )}
            </div>
          </Col>
        </Row>

        {/* Decision Actions */}
        {getAvailableDecisions().length > 0 && (
          <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid #f0f0f0' }}>
            <Text strong style={{ display: 'block', marginBottom: 12 }}>
              <ThunderboltOutlined style={{ color: '#faad14' }} /> 决策操作
            </Text>
            <Space wrap>
              <Button
                type="primary"
                icon={<RightOutlined />}
                onClick={() => openDecisionModal('CONTINUE')}
              >
                继续推进 (CONTINUE)
              </Button>
              <Button
                type="primary"
                icon={<CheckCircleOutlined />}
                onClick={() => openDecisionModal('APPROVE')}
                style={{ backgroundColor: '#52c41a', borderColor: '#52c41a' }}
              >
                批准 (APPROVE)
              </Button>
              <Button
                icon={<QuestionCircleOutlined />}
                onClick={() => openDecisionModal('SUPPLEMENT_DATA')}
                style={{ borderColor: '#faad14', color: '#faad14' }}
              >
                请求补充数据 (SUPPLEMENT_DATA)
              </Button>
              <Button
                danger
                icon={<CloseCircleOutlined />}
                onClick={() => openDecisionModal('REJECT')}
              >
                拒绝 (REJECT)
              </Button>
            </Space>
          </div>
        )}
      </Card>

      {/* Main Tabs */}
      <Card>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'facts',
              label: (
                <span><DatabaseOutlined /> Product Facts</span>
              ),
              children: (
                <Descriptions column={2} bordered>
                  <Descriptions.Item label="产品名称">{product?.name || '—'}</Descriptions.Item>
                  <Descriptions.Item label="SKU">{product?.sku || '—'}</Descriptions.Item>
                  <Descriptions.Item label="来源">{product?.source_url || '—'}</Descriptions.Item>
                  <Descriptions.Item label="供应商">{product?.supplier_code || '—'}</Descriptions.Item>
                  <Descriptions.Item label="品牌">{product?.brand || '—'}</Descriptions.Item>
                  <Descriptions.Item label="类目">{product?.category || '—'}</Descriptions.Item>
                  <Descriptions.Item label="目标市场">{product?.target_market || 'US'}</Descriptions.Item>
                  <Descriptions.Item label="重量">{product?.weight_kg ? `${product.weight_kg} kg` : '待补充'}</Descriptions.Item>
                  <Descriptions.Item label="尺寸" span={2}>
                    {product?.dimensions ? JSON.stringify(product.dimensions) : '待补充'}
                  </Descriptions.Item>
                  <Descriptions.Item label="采购价">
                    {product?.purchase_cost ? `¥${product.purchase_cost}` : '待补充'}
                  </Descriptions.Item>
                  <Descriptions.Item label="创建时间">{product?.created_at || '—'}</Descriptions.Item>
                </Descriptions>
              ),
            },
            {
              key: 'rules',
              label: (
                <span>
                  <AuditOutlined /> Hard Rules
                  {ruleResults && (
                    <Badge
                      count={ruleResults.results.filter(r => r.result === 'FAIL').length}
                      style={{ marginLeft: 8 }}
                    />
                  )}
                </span>
              ),
              children: (
                <div>
                  {ruleResults ? (
                    <>
                      {/* Overall Result */}
                      <div style={{ marginBottom: 16 }}>
                        <Space>
                          <Text strong>总体结果：</Text>
                          {(() => {
                            const meta = RESULT_META[ruleResults.overall] || RESULT_META.UNKNOWN
                            return (
                              <Badge status={ruleResults.overall === 'PASS' ? 'success' : ruleResults.overall === 'FAIL' ? 'error' : 'warning'}>
                                <Tag color={meta.color}>{meta.label}</Tag>
                              </Badge>
                            )
                          })()}
                          {ruleResults.evaluated_at && (
                            <Text type="secondary">
                              评估时间: {new Date(ruleResults.evaluated_at).toLocaleString()}
                            </Text>
                          )}
                        </Space>
                      </div>

                      {/* Rule Details */}
                      {ruleResults.results.length === 0 ? (
                        <Empty description="无规则评估结果" />
                      ) : (
                        <Table
                          dataSource={ruleResults.results}
                          columns={[
                            {
                              title: 'Rule ID',
                              dataIndex: 'rule_id',
                              width: 100,
                              render: (id: string) => <Text strong>{id}</Text>,
                            },
                            {
                              title: '版本',
                              dataIndex: 'rule_version',
                              width: 80,
                            },
                            {
                              title: '结果',
                              dataIndex: 'result',
                              width: 120,
                              render: (result: string) => {
                                const meta = RESULT_META[result] || RESULT_META.UNKNOWN
                                return (
                                  <Badge status={result === 'PASS' ? 'success' : result === 'FAIL' ? 'error' : 'warning'}>
                                    <Tag color={meta.color}>{meta.label}</Tag>
                                  </Badge>
                                )
                              },
                            },
                            {
                              title: '原因',
                              dataIndex: 'reason',
                              ellipsis: true,
                            },
                          ]}
                          pagination={false}
                          size="small"
                        />
                      )}
                    </>
                  ) : (
                    <Empty description="暂无规则评估数据" />
                  )}
                </div>
              ),
            },
            {
              key: 'wc',
              label: (
                <span><GlobalOutlined /> WooCommerce</span>
              ),
              children: (
                <div>
                  {wcStatus ? (
                    <>
                      <Descriptions column={2} bordered>
                        <Descriptions.Item label="WC Product ID">
                          {wcStatus.wc_product_id || '—'}
                        </Descriptions.Item>
                        <Descriptions.Item label="WC Slug">
                          {wcStatus.wc_slug || '—'}
                        </Descriptions.Item>
                        <Descriptions.Item label="同步状态">
                          {(() => {
                            const statusMap: Record<string, { text: string; color: string }> = {
                              not_synced: { text: '未同步', color: 'default' },
                              synced: { text: '已同步', color: 'success' },
                              syncing: { text: '同步中', color: 'processing' },
                              failed: { text: '同步失败', color: 'error' },
                            }
                            const meta = statusMap[wcStatus.sync_status] || { text: wcStatus.sync_status, color: 'default' }
                            return <Tag color={meta.color}>{meta.text}</Tag>
                          })()}
                        </Descriptions.Item>
                        <Descriptions.Item label="最后同步时间">
                          {wcStatus.last_synced_at
                            ? new Date(wcStatus.last_synced_at).toLocaleString()
                            : '—'}
                        </Descriptions.Item>
                        <Descriptions.Item label="最后错误">
                          {wcStatus.last_error ? (
                            <Text type="danger">{wcStatus.last_error}</Text>
                          ) : '—'}
                        </Descriptions.Item>
                        <Descriptions.Item label="重试次数">
                          {wcStatus.retry_count}
                        </Descriptions.Item>
                        <Descriptions.Item label="映射类型">
                          {wcStatus.is_legacy_mapping ? 'Legacy (meta)' : '正式映射'}
                        </Descriptions.Item>
                        <Descriptions.Item label="验证状态">
                          {wcStatus.wc_verify_status || '—'}
                        </Descriptions.Item>
                      </Descriptions>

                      <Divider />

                      {/* Sync Button */}
                      <div>
                        <Button
                          type="primary"
                          size="large"
                          disabled={wcStatus.sync_status !== 'synced'}
                          icon={<SyncOutlined />}
                          onClick={() => {
                            message.info('同步功能将在后续阶段实现')
                          }}
                        >
                          同步到 WooCommerce
                        </Button>
                        {wcStatus.sync_status !== 'synced' && (
                          <div style={{ marginTop: 8 }}>
                            <Text type="secondary">
                              <WarningOutlined /> 当前状态不允许同步。需要同步状态为 "synced"。
                            </Text>
                          </div>
                        )}
                      </div>
                    </>
                  ) : (
                    <Empty description="暂无 WC 同步数据" />
                  )}
                </div>
              ),
            },
            {
              key: 'timeline',
              label: (
                <span><ClockCircleOutlined /> Lifecycle Timeline</span>
              ),
              children: (
                <div>
                  {!product ? (
                    <Empty description="暂无时间线数据" />
                  ) : (
                    <Timeline
                      items={[
                        {
                          children: (
                            <div>
                              <Text strong>创建</Text>
                              <div><Text type="secondary">{product.created_at ? new Date(product.created_at).toLocaleString() : '—'}</Text></div>
                            </div>
                          ),
                          dot: <ClockCircleOutlined />,
                        },
                        ...(product.mastered_at ? [{
                          children: (
                            <div>
                              <Text strong style={{ color: '#52c41a' }}>Product Master Created</Text>
                              <div><Text type="secondary">{new Date(product.mastered_at).toLocaleString()}</Text></div>
                              {product.mastered_by && (
                                <div><Text type="secondary">by: {product.mastered_by}</Text></div>
                              )}
                            </div>
                          ),
                          color: 'green',
                          dot: <CheckCircleOutlined />,
                        }] : []),
                        ...(product.updated_at && product.updated_at !== product.created_at ? [{
                          children: (
                            <div>
                              <Text strong>最后更新</Text>
                              <div><Text type="secondary">{new Date(product.updated_at).toLocaleString()}</Text></div>
                            </div>
                          ),
                          dot: <ClockCircleOutlined />,
                        }] : []),
                      ]}
                    />
                  )}
                </div>
              ),
            },
          ]}
        />
      </Card>

      {/* Decision Modal */}
      <Modal
        title={
          <Space>
            <ThunderboltOutlined style={{ color: '#faad14' }} />
            <span>
              {decisionModalType === 'CONTINUE' && '继续推进'}
              {decisionModalType === 'APPROVE' && '批准产品'}
              {decisionModalType === 'SUPPLEMENT_DATA' && '请求补充数据'}
              {decisionModalType === 'REJECT' && '拒绝产品'}
            </span>
          </Space>
        }
        open={decisionModalOpen}
        onOk={handleDecisionSubmit}
        onCancel={closeDecisionModal}
        confirmLoading={decisionSubmitting}
        okText="确认"
        cancelText="取消"
        width={500}
      >
        <div style={{ marginTop: 16 }}>
          {decisionModalType && (
            <Alert
              type={decisionModalType === 'REJECT' ? 'error' : decisionModalType === 'SUPPLEMENT_DATA' ? 'warning' : 'info'}
              message={
                decisionModalType === 'CONTINUE' && '将推进产品到下一个生命周期阶段'
              }
              description={
                decisionModalType === 'REJECT'
                  ? '拒绝后产品将进入终态，无法继续推进。请确认是否继续。'
                  : decisionModalType === 'SUPPLEMENT_DATA'
                  ? '请选择需要补充的数据字段。产品状态不会变更。'
                  : '请确认决策理由（可选）。'
              }
              showIcon
              style={{ marginBottom: 16 }}
            />
          )}

          {decisionModalType === 'SUPPLEMENT_DATA' && (
            <div style={{ marginBottom: 16 }}>
              <Text strong>需要补充的字段：</Text>
              <div style={{ marginTop: 8 }}>
                <Checkbox.Group
                  value={supplementFields}
                  onChange={(values) => setSupplementFields(values as string[])}
                >
                  <Row gutter={[16, 8]}>
                    {SUPPLEMENT_OPTIONS.map(opt => (
                      <Col key={opt.value} span={12}>
                        <Checkbox value={opt.value}>{opt.label}</Checkbox>
                      </Col>
                    ))}
                  </Row>
                </Checkbox.Group>
              </div>
            </div>
          )}

          <div>
            <Text strong>决策理由（可选）：</Text>
            <div style={{ marginTop: 8 }}>
              <Input.TextArea
                rows={3}
                value={decisionReason}
                onChange={(e) => setDecisionReason(e.target.value)}
                placeholder="输入决策理由..."
                maxLength={500}
                showCount
              />
            </div>
          </div>
        </div>
      </Modal>

      {/* Decision Result Modal */}
      <Modal
        title={
          <Space>
            {decisionResult?.success ? (
              <CheckCircleOutlined style={{ color: '#52c41a' }} />
            ) : (
              <ExclamationCircleOutlined style={{ color: '#faad14' }} />
            )}
            <span>决策结果</span>
          </Space>
        }
        open={decisionResultModalOpen}
        onOk={() => setDecisionResultModalOpen(false)}
        onCancel={() => setDecisionResultModalOpen(false)}
        footer={[
          <Button key="ok" type="primary" onClick={() => setDecisionResultModalOpen(false)}>
            关闭
          </Button>,
        ]}
        width={600}
      >
        {decisionResult && (
          <div>
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label="决策类型">
                <Tag>{decisionResult.decision}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="结果">
                <Tag color={decisionResult.success ? 'success' : 'warning'}>
                  {decisionResult.success ? '成功' : '失败'}
                </Tag>
              </Descriptions.Item>
              {decisionResult.success ? (
                <>
                  <Descriptions.Item label="状态变更">
                    {decisionResult.previous_status} → {decisionResult.current_status}
                  </Descriptions.Item>
                  <Descriptions.Item label="下一步">
                    {decisionResult.next_action}
                  </Descriptions.Item>
                </>
              ) : (
                <Descriptions.Item label="错误信息">
                  <Text type="danger">{decisionResult.error}</Text>
                </Descriptions.Item>
              )}
              {decisionResult.reason && (
                <Descriptions.Item label="理由">
                  {decisionResult.reason}
                </Descriptions.Item>
              )}
              {decisionResult.blockers && decisionResult.blockers.length > 0 && (
                <Descriptions.Item label="阻塞项">
                  {decisionResult.blockers.map((blocker, idx) => (
                    <div key={idx} style={{ marginBottom: 4 }}>
                      <Tag color={blocker.severity === 'high' ? 'red' : blocker.severity === 'medium' ? 'orange' : 'blue'}>
                        {blocker.code}
                      </Tag>
                      <Text>{blocker.message}</Text>
                    </div>
                  ))}
                </Descriptions.Item>
              )}
              <Descriptions.Item label="Trace ID">
                <Text code>{decisionResult.trace_id}</Text>
              </Descriptions.Item>
            </Descriptions>
          </div>
        )}
      </Modal>
    </div>
  )
}
