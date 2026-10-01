import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Row, Col, Button, Typography, Spin, Empty, Alert, Table, Tag,
  Select, Space, Badge, Statistic, Divider,
} from 'antd'
import {
  PictureOutlined, RocketOutlined, CheckCircleOutlined,
  ClockCircleOutlined, RobotOutlined, ExclamationCircleOutlined,
  LoadingOutlined, ArrowRightOutlined, ReloadOutlined,
} from '@ant-design/icons'
import { api, ApiError } from '../api/client'
import { useAuth } from '../auth/AuthProvider'

const { Title, Text, Paragraph } = Typography

// ── Types ──────────────────────────────────────────────────────────────
interface ProductBrief {
  id: string
  product_id: string
  product_name?: string
  product_sku?: string
  objective: string
  channel?: string
  target_market?: string
  visual_style?: string
  status: string
  required_assets?: { asset_type: string; count: number; priority: string }[]
  created_at?: string
  updated_at?: string
}

interface CreativeAsset {
  id: string
  asset_type: string
  status: string
  quality_result?: Record<string, unknown>
  compliance_result?: Record<string, unknown>
  preview_url?: string
  product_id?: string
  brief_id?: string
  created_at?: string
  approved_at?: string
}

interface CreativeStatus {
  service_status: string
  provider_status?: Record<string, string>
  total_runs?: number
  total_assets?: number
  approved_assets?: number
  month_cost_cny?: number
}

const STATUS_META: Record<string, { color: string; label: string }> = {
  DRAFT: { color: 'default', label: '草稿' },
  IN_PROGRESS: { color: 'processing', label: '进行中' },
  COMPLETED: { color: 'success', label: '已完成' },
  REJECTED: { color: 'error', label: '已拒绝' },
  QUEUED: { color: 'default', label: '排队中' },
  RUNNING: { color: 'processing', label: '运行中' },
  SUCCEEDED: { color: 'success', label: '成功' },
  FAILED: { color: 'error', label: '失败' },
  QC_PASSED: { color: 'success', label: 'QC 通过' },
  APPROVED: { color: 'success', label: '已批准' },
}

export default function CreativeStudio() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState<CreativeStatus | null>(null)
  const [briefs, setBriefs] = useState<ProductBrief[]>([])
  const [products, setProducts] = useState<{ id: string; name: string; sku: string }[]>([])
  const [selectedProductId, setSelectedProductId] = useState<string | null>(null)
  const [filterBriefStatus, setFilterBriefStatus] = useState<string>('')

  // Load data
  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [statusData, briefsData, productsData] = await Promise.all([
        api.getCreativeStatus(),
        api.getCreativeBriefs(50, 0),
        api.getProducts(100, 0),
      ])
      setStatus(statusData as CreativeStatus)
      setBriefs((briefsData as any).briefs || [])
      setProducts(((productsData as any).data || []).map((p: any) => ({
        id: p.id,
        name: p.name,
        sku: p.sku || p.name || '',
      })))
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setError('未授权：请先登录或联系管理员获取权限')
        } else if (err.status === 403) {
          setError('权限不足：需要 Operator 角色才能访问 Creative Studio')
        } else {
          setError(`加载失败: ${err.message}`)
        }
      } else {
        setError('加载失败：网络错误')
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadData()
  }, [loadData])

  const handleSelectProduct = (productId: string) => {
    setSelectedProductId(productId)
  }

  const handleEnterWorkbench = () => {
    if (selectedProductId) {
      navigate(`/creative/workbench/${selectedProductId}`)
    }
  }

  const handleCreateBrief = async (productId: string) => {
    try {
      const brief = (await api.createCreativeBriefFromProduct(productId, {
        objective: '电商主图与详情图生成',
        channel: 'DTC',
        target_market: 'US,EU',
        visual_style: '专业电商摄影',
        created_by: user?.username || 'admin',
      })) as any
      if (brief.id) {
        navigate(`/creative/workbench/${productId}`)
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`创建 Brief 失败: ${err.message}`)
      }
    }
  }

  const filteredBriefs = filterBriefStatus
    ? briefs.filter((b) => b.status === filterBriefStatus)
    : briefs

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 100 }}>
        <Spin indicator={<LoadingOutlined />} size="large" />
        <div style={{ marginTop: 16 }}><Text>加载 Creative Studio...</Text></div>
      </div>
    )
  }

  return (
    <div style={{ padding: 16, margin: '-24px' }}>
      <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <Title level={3} style={{ margin: 0 }}>
            <PictureOutlined /> AI 创意工坊
          </Title>
          <Text type="secondary">从 Product Master 到 Creative Approved 的完整创意生产流程</Text>
        </div>
        {status && (
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            <Badge status={status.service_status === 'online' ? 'success' : 'error'} text={status.service_status === 'online' ? '服务在线' : '服务离线'} />
            <Statistic title="生成次数" value={status.total_runs || 0} valueStyle={{ fontSize: 18 }} />
            <Statistic title="创意资产" value={status.total_assets || 0} valueStyle={{ fontSize: 18 }} />
            <Statistic title="已批准" value={status.approved_assets || 0} valueStyle={{ color: '#52c41a', fontSize: 18 }} />
            <Statistic title="本月成本" value={status.month_cost_cny || 0} prefix="¥" precision={2} valueStyle={{ fontSize: 18 }} />
          </div>
        )}
      </div>

      {error && (
        <Alert 
          type="error" 
          message={error} 
          style={{ marginBottom: 16 }} 
          showIcon 
          closable 
          onClose={() => setError(null)}
          action={
            <Button size="small" icon={<ReloadOutlined />} onClick={() => void loadData()}>
              重试
            </Button>
          }
        />
      )}

      <Row gutter={[16, 16]}>
        {/* Product Selection */}
        <Col xs={24} lg={8}>
          <Card title="选择 Product Master" size="small">
            <Select
              placeholder="选择商品..."
              style={{ width: '100%', marginBottom: 12 }}
              value={selectedProductId}
              onChange={handleSelectProduct}
              options={products.map((p) => ({
                value: p.id,
                label: `${p.name} (${p.sku})`,
              }))}
              showSearch
              filterOption={(input, option) =>
                (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
              }
              notFoundContent="暂无商品"
            />
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <Button
                type="primary"
                icon={<RocketOutlined />}
                disabled={!selectedProductId}
                onClick={handleEnterWorkbench}
                style={{ flex: 1, minWidth: 120 }}
              >
                进入 Workbench
              </Button>
              <Button
                icon={<CheckCircleOutlined />}
                disabled={!selectedProductId}
                onClick={() => selectedProductId && void handleCreateBrief(selectedProductId)}
                style={{ flex: 1, minWidth: 120 }}
              >
                创建 Brief
              </Button>
            </div>
            <Divider style={{ margin: '12px 0' }} />
            <Text type="secondary" style={{ fontSize: 12 }}>
              选择 Product Master 后，进入 Creative Workbench 管理 Brief、生成、QC、审批全流程。
            </Text>
          </Card>
        </Col>

        {/* Briefs List */}
        <Col xs={24} lg={16}>
          <Card
            title="Creative Briefs"
            size="small"
            extra={
              <Select
                placeholder="筛选状态"
                style={{ width: 120 }}
                value={filterBriefStatus || undefined}
                onChange={(v) => setFilterBriefStatus(v || '')}
                allowClear
                options={[
                  { value: 'DRAFT', label: '草稿' },
                  { value: 'IN_PROGRESS', label: '进行中' },
                  { value: 'COMPLETED', label: '已完成' },
                ]}
              />
            }
          >
            {filteredBriefs.length === 0 ? (
              <Empty description="暂无 Creative Brief" />
            ) : (
              <Table
                size="small"
                dataSource={filteredBriefs}
                rowKey="id"
                pagination={{ pageSize: 8 }}
                columns={[
                  {
                    title: 'Brief ID',
                    dataIndex: 'id',
                    key: 'id',
                    width: 100,
                    render: (id: string) => <Text code style={{ fontSize: 11 }}>{id.slice(0, 8)}...</Text>,
                  },
                  {
                    title: 'Objective',
                    dataIndex: 'objective',
                    key: 'objective',
                    ellipsis: true,
                  },
                  {
                    title: 'Status',
                    dataIndex: 'status',
                    key: 'status',
                    width: 100,
                    render: (status: string) => {
                      const meta = STATUS_META[status] || { color: 'default', label: status }
                      return <Tag color={meta.color}>{meta.label}</Tag>
                    },
                  },
                  {
                    title: 'Assets',
                    dataIndex: 'required_assets',
                    key: 'assets',
                    width: 120,
                    render: (assets: { asset_type: string; count: number }[] = []) =>
                      assets.map((a) => `${a.asset_type}×${a.count}`).join(', ') || '-',
                  },
                  {
                    title: 'Actions',
                    key: 'actions',
                    width: 100,
                    render: (_: unknown, record: ProductBrief) => (
                      <Button
                        size="small"
                        type="link"
                        icon={<ArrowRightOutlined />}
                        onClick={() => navigate(`/creative/workbench/${record.product_id}`)}
                      >
                        Workbench
                      </Button>
                    ),
                  },
                ]}
              />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}