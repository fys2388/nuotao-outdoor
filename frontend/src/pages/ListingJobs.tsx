import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Button,
  Card,
  Drawer,
  Form,
  Input,
  Modal,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ReloadOutlined,
  SendOutlined,
  StopOutlined,
  SyncOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { request } from '../api/client'

const { Title, Text, Paragraph } = Typography

type JobStatus = 'pending' | 'approved' | 'processing' | 'rejected' | 'published' | 'failed'

interface ListingJob {
  id: string
  workspace_id: string
  product_id: string
  sku: string
  name: string
  payload: Record<string, unknown>
  status: JobStatus
  note?: string | null
  reject_reasons: string[] | Array<{ code: string; message: string }>
  submitted_by: string
  reviewed_by?: string | null
  submitted_at: string
  reviewed_at?: string | null
  pushed_at?: string | null
  published_at?: string | null
  retry_count: number
  wc_product_id?: number | null
  wc_verify_status?: string | null
  wc_verify_detail?: string | null
  trace_id?: string | null
  created_at: string
  updated_at: string
}

const STATUS_TAG: Record<JobStatus, { color: string; label: string }> = {
  pending: { color: 'gold', label: '待终审' },
  approved: { color: 'blue', label: '已批准' },
  processing: { color: 'processing', label: '推送中' },
  rejected: { color: 'red', label: '已驳回' },
  published: { color: 'green', label: '已发布' },
  failed: { color: 'red', label: '推送失败' },
}

const STATUS_ORDER: JobStatus[] = [
  'pending', 'approved', 'processing', 'rejected', 'published', 'failed',
]

export default function ListingJobs() {
  const [jobs, setJobs] = useState<ListingJob[]>([])
  const [stats, setStats] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(false)
  const [activeStatus, setActiveStatus] = useState<string>('all')
  const [detailJob, setDetailJob] = useState<ListingJob | null>(null)
  const [reviewTarget, setReviewTarget] = useState<ListingJob | null>(null)
  const [reviewForm] = Form.useForm()
  const [pushingId, setPushingId] = useState<string | null>(null)

  const loadJobs = useCallback(async (status?: string) => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (status && status !== 'all') params.set('status', status)
      params.set('limit', '100')
      const qs = params.toString()
      const url = `/listing-jobs${qs ? `?${qs}` : ''}`
      const data = (await request(url)) as {
        data: ListingJob[]
        stats: Record<string, number>
      }
      setJobs(data.data ?? [])
      setStats(data.stats ?? {})
    } catch (err) {
      message.error(`加载上架工单失败：${err instanceof Error ? err.message : '未知错误'}`)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadJobs()
  }, [loadJobs])

  const handleReview = useCallback(async (decision: 'approve' | 'reject') => {
    if (!reviewTarget) return
    try {
      const values = await reviewForm.validateFields()
      await request(`/listing-jobs/${reviewTarget.id}/review`, {
        method: 'POST',
        body: JSON.stringify({
          decision,
          note: values.note ?? '',
          reject_reasons: decision === 'reject' ? (values.reasons ?? []) : [],
        }),
      })
      message.success(decision === 'approve' ? '已批准，可推送 WC' : '已驳回工单')
      setReviewTarget(null)
      reviewForm.resetFields()
      await loadJobs(activeStatus === 'all' ? undefined : activeStatus)
    } catch (err) {
      if (err instanceof Error) message.error(err.message)
    }
  }, [reviewTarget, reviewForm, activeStatus, loadJobs])

  const handlePush = useCallback(async (job: ListingJob) => {
    setPushingId(job.id)
    try {
      await request(`/listing-jobs/${job.id}/push`, { method: 'POST', timeoutMs: 120_000 })
      message.success('WC 推送已提交')
      await loadJobs(activeStatus === 'all' ? undefined : activeStatus)
    } catch (err) {
      message.error(`推送失败：${err instanceof Error ? err.message : '未知错误'}`)
      await loadJobs(activeStatus === 'all' ? undefined : activeStatus)
    } finally {
      setPushingId(null)
    }
  }, [activeStatus, loadJobs])

  const handleRetry = useCallback(async (job: ListingJob) => {
    setPushingId(job.id)
    try {
      await request(`/listing-jobs/${job.id}/retry`, { method: 'POST', timeoutMs: 120_000 })
      message.success('已重试推送')
      await loadJobs(activeStatus === 'all' ? undefined : activeStatus)
    } catch (err) {
      message.error(`重试失败：${err instanceof Error ? err.message : '未知错误'}`)
      await loadJobs(activeStatus === 'all' ? undefined : activeStatus)
    } finally {
      setPushingId(null)
    }
  }, [activeStatus, loadJobs])

  const columns = useMemo(
    () => [
      {
        title: 'SKU',
        dataIndex: 'sku',
        key: 'sku',
        width: 140,
        render: (v: string, r: ListingJob) => (
          <div>
            <Text strong>{v}</Text>
            <div style={{ fontSize: 12, color: '#888' }}>{r.id.slice(0, 8)}</div>
          </div>
        ),
      },
      {
        title: '商品名称',
        dataIndex: 'name',
        key: 'name',
        ellipsis: true,
      },
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        width: 100,
        render: (v: JobStatus) => {
          const t = STATUS_TAG[v] ?? { color: 'default', label: v }
          return <Tag color={t.color}>{t.label}</Tag>
        },
      },
      {
        title: '提交人 / 审核人',
        key: 'actor',
        width: 180,
        render: (_: unknown, r: ListingJob) => (
          <div>
            <div>提交：{r.submitted_by}</div>
            {r.reviewed_by && <div style={{ fontSize: 12, color: '#888' }}>审核：{r.reviewed_by}</div>}
          </div>
        ),
      },
      {
        title: '提交时间',
        dataIndex: 'submitted_at',
        key: 'submitted_at',
        width: 170,
        render: (v: string) => <Text type="secondary">{v.replace('T', ' ').slice(0, 19)}</Text>,
      },
      {
        title: 'WC 回读',
        key: 'wc',
        width: 160,
        render: (_: unknown, r: ListingJob) => {
          if (r.wc_verify_status === 'ok' && r.wc_product_id) {
            return <Tag color="green">WC #{r.wc_product_id}</Tag>
          }
          if (r.wc_verify_status === 'failed' || r.wc_verify_status === 'error' || r.wc_verify_status === 'timeout') {
            return (
              <Tooltip title={r.wc_verify_detail ?? ''}>
                <Tag color="red">回读失败</Tag>
              </Tooltip>
            )
          }
          return <Text type="secondary">—</Text>
        },
      },
      {
        title: '操作',
        key: 'actions',
        width: 220,
        render: (_: unknown, r: ListingJob) => (
          <Space size="small" wrap>
            <Button
              size="small"
              icon={<CheckCircleOutlined />}
              disabled={r.status !== 'pending'}
              onClick={() => {
                setReviewTarget(r)
                reviewForm.setFieldsValue({ decision: 'approve', note: '' })
              }}
            >
              批准
            </Button>
            <Button
              size="small"
              danger
              icon={<StopOutlined />}
              disabled={r.status !== 'pending'}
              onClick={() => {
                setReviewTarget(r)
                reviewForm.setFieldsValue({ decision: 'reject', note: '' })
              }}
            >
              驳回
            </Button>
            <Button
              size="small"
              type="primary"
              icon={<SendOutlined />}
              disabled={r.status !== 'approved' || pushingId === r.id}
              loading={pushingId === r.id}
              onClick={() => void handlePush(r)}
            >
              推送 WC
            </Button>
            <Tooltip title="重试失败推送">
              <Button
                size="small"
                icon={<ReloadOutlined />}
                disabled={!['failed', 'rejected'].includes(r.status) || pushingId === r.id}
                loading={pushingId === r.id}
                onClick={() => void handleRetry(r)}
              />
            </Tooltip>
          </Space>
        ),
      },
    ],
    [pushingId, handlePush, handleRetry, reviewForm],
  )

  const tabItems = [
    { key: 'all', label: <span>全部 <Tag>{jobs.length}</Tag></span> },
    ...STATUS_ORDER.map((s) => ({
      key: s,
      label: (
        <span>
          {STATUS_TAG[s].label} <Tag color={STATUS_TAG[s].color}>{stats[s] ?? 0}</Tag>
        </span>
      ),
    })),
  ]

  return (
    <Card
      title={
        <Space>
          <ThunderboltOutlined />
          <Title level={4} style={{ margin: 0 }}>上架工单</Title>
          <Text type="secondary">SOP 阶段 ③ 人工终审闸门</Text>
        </Space>
      }
      extra={
        <Button icon={<ReloadOutlined />} onClick={() => void loadJobs(activeStatus === 'all' ? undefined : activeStatus)}>
          刷新
        </Button>
      }
    >
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 12, marginBottom: 16 }}>
        {STATUS_ORDER.map((s) => (
          <Card size="small" key={s} style={{ textAlign: 'center' }}>
            <Statistic
              value={stats[s] ?? 0}
              prefix={
                s === 'published' ? <CheckCircleOutlined style={{ color: '#52c41a' }} />
                  : s === 'failed' || s === 'rejected' ? <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
                  : s === 'processing' ? <SyncOutlined spin style={{ color: '#1677ff' }} />
                  : <Tag color={STATUS_TAG[s].color} style={{ padding: 0 }}>{STATUS_TAG[s].label[0]}</Tag>
              }
              title={STATUS_TAG[s].label}
            />
          </Card>
        ))}
      </div>

      <Tabs
        activeKey={activeStatus}
        onChange={(k) => {
          setActiveStatus(k)
          void loadJobs(k === 'all' ? undefined : k)
        }}
        items={tabItems}
        size="small"
        style={{ marginBottom: 8 }}
      />

      <Table
        rowKey="id"
        columns={columns}
        dataSource={jobs}
        loading={loading}
        pagination={{ pageSize: 20, showSizeChanger: false }}
        size="small"
        onRow={(r) => ({
          onClick: () => setDetailJob(r),
          style: { cursor: 'pointer' },
        })}
      />

      <Modal
        title={reviewTarget ? `审核工单 ${reviewTarget.sku}` : ''}
        open={!!reviewTarget}
        onCancel={() => { setReviewTarget(null); reviewForm.resetFields() }}
        footer={null}
        width={640}
      >
        <Paragraph>
          <Text strong>商品：</Text> {reviewTarget?.name} <br />
          <Text strong>SKU：</Text> {reviewTarget?.sku}
        </Paragraph>
        <Form form={reviewForm} layout="vertical">
          <Form.Item name="note" label="备注 / 终审意见">
            <Input.TextArea rows={3} placeholder="填写审核意见（可留空）" />
          </Form.Item>
          <Form.Item name="reasons" label="驳回原因（多行，每行一条）">
            <Input.TextArea rows={2} placeholder="可选，驳回时填写" />
          </Form.Item>
        </Form>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <Button
            danger
            onClick={() => void handleReview('reject')}
          >
            驳回工单
          </Button>
          <Button
            type="primary"
            onClick={() => void handleReview('approve')}
          >
            批准并允许推送
          </Button>
        </div>
      </Modal>

      <Drawer
        title={detailJob ? `工单详情：${detailJob.sku}` : ''}
        open={!!detailJob}
        onClose={() => setDetailJob(null)}
        width={720}
      >
        {detailJob && (
          <div>
            <p><Text strong>状态：</Text> <Tag color={STATUS_TAG[detailJob.status].color}>{STATUS_TAG[detailJob.status].label}</Tag></p>
            <p><Text strong>提交人：</Text> {detailJob.submitted_by} · {detailJob.submitted_at}</p>
            {detailJob.reviewed_by && (
              <p><Text strong>审核人：</Text> {detailJob.reviewed_by} · {detailJob.reviewed_at}</p>
            )}
            <p><Text strong>重试次数：</Text> {detailJob.retry_count}</p>
            <p><Text strong>WC 回读状态：</Text> {detailJob.wc_verify_status ?? '未推送'}</p>
            {detailJob.wc_verify_detail && (
              <p><Text strong>WC 回读详情：</Text> <Paragraph style={{ margin: 0, marginTop: 4, whiteSpace: 'pre-wrap' }}>{detailJob.wc_verify_detail}</Paragraph></p>
            )}
            {detailJob.wc_product_id && (
              <p><Text strong>WC 商品 ID：</Text> #{detailJob.wc_product_id}</p>
            )}
            {detailJob.trace_id && (
              <p><Text strong>Trace ID：</Text> <Text code>{detailJob.trace_id}</Text></p>
            )}
            <Paragraph style={{ marginTop: 16 }}>
              <Text strong>完整 WC payload 快照：</Text>
            </Paragraph>
            <pre style={{
              background: '#f5f5f5',
              padding: 12,
              borderRadius: 4,
              maxHeight: 400,
              overflow: 'auto',
              fontSize: 12,
            }}>
              {JSON.stringify(detailJob.payload, null, 2)}
            </pre>
          </div>
        )}
      </Drawer>
    </Card>
  )
}
