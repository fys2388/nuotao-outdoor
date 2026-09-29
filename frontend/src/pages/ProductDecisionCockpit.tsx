import { useState, useEffect, useCallback } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Card, Row, Col, Tag, Button, Space, Typography, Spin, Empty, Alert,
  Descriptions, Tabs, Table, Badge, Divider, Tooltip, Progress, Statistic,
  Timeline, List, message,
} from 'antd'
import {
  ArrowLeftOutlined, ReloadOutlined, CheckCircleOutlined,
  CloseCircleOutlined, MinusCircleOutlined, QuestionCircleOutlined,
  WarningOutlined, RightOutlined, SyncOutlined,
  ThunderboltOutlined, RobotOutlined, CalculatorOutlined,
  AuditOutlined, DatabaseOutlined, ShoppingCartOutlined,
  GlobalOutlined, ClockCircleOutlined,
} from '@ant-design/icons'
import {
  api,
  type RuleResultsResponse,
  type WcStatusResponse,
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
    </div>
  )
}
