import { useState, useEffect, useCallback } from 'react'
import {
  Card, Row, Col, Typography, Spin, Empty, Alert, Statistic,
  Progress, Table, Tag, Divider, Select, Button, message,
} from 'antd'
import {
  PictureOutlined, RocketOutlined, CheckCircleOutlined,
  RobotOutlined, DollarOutlined, ClockCircleOutlined,
  BarChartOutlined, FileTextOutlined, DownloadOutlined,
} from '@ant-design/icons'
import { api, ApiError } from '../api/client'

const { Title, Text } = Typography

// ── Types ──────────────────────────────────────────────────────────────
interface DashboardMetrics {
  assets: {
    total: number
    by_status: Record<string, number>
    approved_rate: number
  }
  generation: {
    total_runs: number
    success_rate: number
    avg_latency_ms: number
  }
  cost: {
    total_cost_cny: number
    avg_cost_per_asset: number
    by_model: Record<string, number>
  }
  templates: {
    total: number
    active: number
  }
  knowledge: {
    total_entries: number
    recent: number
  }
  approvals: {
    pending: number
    approved: number
    rejected: number
  }
  briefs: {
    total: number
    completed: number
  }
}

interface PerformanceMetrics {
  generation_time: {
    avg_ms: number
    p50_ms: number
    p95_ms: number
  }
  cost_per_asset: {
    avg_cny: number
    by_type: Record<string, number>
  }
  review: {
    avg_review_time_hours: number
    ai_qc_pass_rate: number
    human_approval_rate: number
  }
}

export default function CreativeAnalytics() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [days, setDays] = useState(30)
  const [dashboard, setDashboard] = useState<DashboardMetrics | null>(null)
  const [performance, setPerformance] = useState<PerformanceMetrics | null>(null)

  // Load data
  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [dashData, perfData] = await Promise.all([
        api.getCreativeAnalyticsDashboard(days),
        api.getCreativeAnalyticsPerformance(days),
      ])
      setDashboard(dashData as DashboardMetrics)
      setPerformance(perfData as PerformanceMetrics)
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`加载失败: ${err.message}`)
      } else {
        setError('加载失败：网络错误')
      }
    } finally {
      setLoading(false)
    }
  }, [days])

  useEffect(() => {
    void loadData()
  }, [loadData])

  // Export dashboard data as CSV
  const handleExportCSV = () => {
    if (!dashboard || !performance) {
      message.warning('暂无数据可导出')
      return
    }
    
    const rows = [
      ['Category', 'Metric', 'Value'],
      ['Assets', 'Total', dashboard.assets.total],
      ['Assets', 'Approved Rate', `${(dashboard.assets.approved_rate * 100).toFixed(1)}%`],
      ['Generation', 'Total Runs', dashboard.generation.total_runs],
      ['Generation', 'Success Rate', `${(dashboard.generation.success_rate * 100).toFixed(1)}%`],
      ['Generation', 'Avg Latency', `${(dashboard.generation.avg_latency_ms / 1000).toFixed(1)}s`],
      ['Cost', 'Total Cost (CNY)', dashboard.cost.total_cost_cny.toFixed(2)],
      ['Cost', 'Avg Cost per Asset', dashboard.cost.avg_cost_per_asset.toFixed(4)],
      ['Templates', 'Total', dashboard.templates.total],
      ['Templates', 'Active', dashboard.templates.active],
      ['Knowledge', 'Total Entries', dashboard.knowledge.total_entries],
      ['Knowledge', 'Recent', dashboard.knowledge.recent],
      ['Approvals', 'Pending', dashboard.approvals.pending],
      ['Approvals', 'Approved', dashboard.approvals.approved],
      ['Approvals', 'Rejected', dashboard.approvals.rejected],
      ['Briefs', 'Total', dashboard.briefs.total],
      ['Briefs', 'Completed', dashboard.briefs.completed],
      ['Review', 'Avg Review Time (h)', performance.review.avg_review_time_hours.toFixed(2)],
      ['Review', 'AI QC Pass Rate', `${(performance.review.ai_qc_pass_rate * 100).toFixed(1)}%`],
      ['Review', 'Human Approval Rate', `${(performance.review.human_approval_rate * 100).toFixed(1)}%`],
    ]
    
    const csv = rows.map(r => r.join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `creative-analytics-${days}days-${new Date().toISOString().slice(0, 10)}.csv`
    link.click()
    URL.revokeObjectURL(url)
    message.success('CSV 导出成功')
  }

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 100 }}>
        <Spin size="large" />
        <div style={{ marginTop: 16 }}><Text>加载 Analytics...</Text></div>
      </div>
    )
  }

  return (
    <div style={{ padding: 16, margin: '-24px' }}>
      <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <Title level={3} style={{ margin: 0 }}>
            <BarChartOutlined /> Creative Analytics
          </Title>
          <Text type="secondary">创意生成性能与成本分析</Text>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Select
            value={days}
            onChange={setDays}
            options={[
              { value: 7, label: '7 days' },
              { value: 30, label: '30 days' },
              { value: 90, label: '90 days' },
            ]}
            style={{ width: 120 }}
          />
          <Button
            icon={<DownloadOutlined />}
            onClick={handleExportCSV}
            disabled={!dashboard}
          >
            导出 CSV
          </Button>
        </div>
      </div>

      {error && (
        <Alert type="error" message={error} style={{ marginBottom: 16 }} showIcon />
      )}

      {!dashboard ? (
        <Empty description="暂无数据" />
      ) : (
        <>
          {/* Summary Stats */}
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={24} sm={12} md={6}>
              <Card size="small">
                <Statistic
                  title="Total Assets"
                  value={dashboard.assets.total}
                  prefix={<PictureOutlined />}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} md={6}>
              <Card size="small">
                <Statistic
                  title="Generation Runs"
                  value={dashboard.generation.total_runs}
                  prefix={<RocketOutlined />}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} md={6}>
              <Card size="small">
                <Statistic
                  title="Approved Rate"
                  value={(dashboard.assets.approved_rate * 100).toFixed(1)}
                  suffix="%"
                  valueStyle={{ color: '#52c41a' }}
                  prefix={<CheckCircleOutlined />}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} md={6}>
              <Card size="small">
                <Statistic
                  title="Total Cost"
                  value={dashboard.cost.total_cost_cny}
                  precision={2}
                  prefix={<DollarOutlined />}
                  suffix="CNY"
                />
              </Card>
            </Col>
          </Row>

          {/* Asset Status Breakdown */}
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={24} md={8}>
              <Card title="Asset Status" size="small">
                {Object.entries(dashboard.assets.by_status).map(([status, count]) => (
                  <div key={status} style={{ marginBottom: 8 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                      <Text>{status}</Text>
                      <Text strong>{count}</Text>
                    </div>
                    <Progress
                      percent={(count / dashboard.assets.total) * 100}
                      size="small"
                      showInfo={false}
                    />
                  </div>
                ))}
              </Card>
            </Col>

            <Col span={8}>
              <Card title="Generation Performance" size="small">
                <Statistic
                  title="Success Rate"
                  value={(dashboard.generation.success_rate * 100).toFixed(1)}
                  suffix="%"
                  valueStyle={{ color: dashboard.generation.success_rate > 0.8 ? '#52c41a' : '#faad14' }}
                />
                <Divider />
                <Statistic
                  title="Avg Latency"
                  value={(dashboard.generation.avg_latency_ms / 1000).toFixed(1)}
                  suffix="s"
                  prefix={<ClockCircleOutlined />}
                />
                {performance && (
                  <>
                    <Divider />
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      P50: {(performance.generation_time.p50_ms / 1000).toFixed(1)}s ·
                      P95: {(performance.generation_time.p95_ms / 1000).toFixed(1)}s
                    </Text>
                  </>
                )}
              </Card>
            </Col>

            <Col span={8}>
              <Card title="Cost Analysis" size="small">
                <Statistic
                  title="Avg Cost/Asset"
                  value={dashboard.cost.avg_cost_per_asset}
                  precision={3}
                  prefix={<DollarOutlined />}
                  suffix="CNY"
                />
                <Divider />
                {Object.entries(dashboard.cost.by_model).map(([model, cost]) => (
                  <div key={model} style={{ marginBottom: 4 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                      <Text>{model}</Text>
                      <Text>¥{cost.toFixed(2)}</Text>
                    </div>
                  </div>
                ))}
              </Card>
            </Col>
          </Row>

          {/* Review Metrics */}
          {performance && (
            <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
              <Col span={8}>
                <Card title="Review Metrics" size="small">
                  <Statistic
                    title="AI QC Pass Rate"
                    value={(performance.review.ai_qc_pass_rate * 100).toFixed(1)}
                    suffix="%"
                    prefix={<RobotOutlined />}
                    valueStyle={{ color: performance.review.ai_qc_pass_rate > 0.7 ? '#52c41a' : '#faad14' }}
                  />
                  <Divider />
                  <Statistic
                    title="Human Approval Rate"
                    value={(performance.review.human_approval_rate * 100).toFixed(1)}
                    suffix="%"
                    prefix={<CheckCircleOutlined />}
                  />
                  <Divider />
                  <Statistic
                    title="Avg Review Time"
                    value={performance.review.avg_review_time_hours.toFixed(1)}
                    suffix="h"
                    prefix={<ClockCircleOutlined />}
                  />
                </Card>
              </Col>

              <Col span={8}>
                <Card title="Templates" size="small">
                  <Statistic
                    title="Total Templates"
                    value={dashboard.templates.total}
                    prefix={<FileTextOutlined />}
                  />
                  <Divider />
                  <Statistic
                    title="Active Templates"
                    value={dashboard.templates.active}
                  />
                  <Divider />
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    Usage rate: {dashboard.templates.total > 0
                      ? ((dashboard.templates.active / dashboard.templates.total) * 100).toFixed(0)
                      : 0}%
                  </Text>
                </Card>
              </Col>

              <Col span={8}>
                <Card title="Approvals" size="small">
                  <Statistic
                    title="Pending"
                    value={dashboard.approvals.pending}
                    valueStyle={{ color: '#faad14' }}
                  />
                  <Divider />
                  <Statistic
                    title="Approved"
                    value={dashboard.approvals.approved}
                    valueStyle={{ color: '#52c41a' }}
                  />
                  <Divider />
                  <Statistic
                    title="Rejected"
                    value={dashboard.approvals.rejected}
                    valueStyle={{ color: '#f5222d' }}
                  />
                </Card>
              </Col>
            </Row>
          )}

          {/* Cost by Asset Type */}
          {performance && Object.keys(performance.cost_per_asset.by_type).length > 0 && (
            <Card title="Cost by Asset Type" size="small">
              <Table
                size="small"
                dataSource={Object.entries(performance.cost_per_asset.by_type).map(([type, cost]) => ({
                  type,
                  cost,
                }))}
                columns={[
                  { title: 'Asset Type', dataIndex: 'type', key: 'type' },
                  { title: 'Avg Cost (CNY)', dataIndex: 'cost', key: 'cost',
                    render: (c: number) => `¥${c.toFixed(3)}` },
                ]}
                pagination={false}
              />
            </Card>
          )}
        </>
      )}
    </div>
  )
}