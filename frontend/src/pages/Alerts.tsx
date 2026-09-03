import { useEffect, useState } from 'react'
import { Table, Tag, Button, Space, Modal, Input, Select, Spin, Alert, Row, Col, Card, Statistic } from 'antd'
import { WarningOutlined, CheckCircleOutlined, ExclamationCircleOutlined } from '@ant-design/icons'
import { api } from '../api/client'

interface AlertItem {
  id: string
  type: string
  severity: string
  title: string
  description: string
  status: string
  created_at: string
  recommended_action: string
  metric_data: Record<string, any>
}

const severityMap: Record<string, { color: string; label: string; icon: any }> = {
  critical: { color: 'red', label: '严重', icon: <ExclamationCircleOutlined /> },
  warning: { color: 'orange', label: '警告', icon: <WarningOutlined /> },
  info: { color: 'blue', label: '提示', icon: <InfoCircle /> },
}

function InfoCircle(props: any) {
  return <span {...props}>ℹ️</span>
}

const statusMap: Record<string, string> = {
  new: '新建',
  acknowledged: '已确认',
  investigating: '调查中',
  resolved: '已解决',
  dismissed: '已忽略',
}

export default function AlertsPage() {
  const [loading, setLoading] = useState(true)
  const [alerts, setAlerts] = useState<AlertItem[]>([])
  const [summary, setSummary] = useState<Record<string, number>>({})
  const [filterStatus, setFilterStatus] = useState<string | undefined>()
  const [filterSeverity, setFilterSeverity] = useState<string | undefined>()
  const [detailModal, setDetailModal] = useState<AlertItem | null>(null)
  const [error, setError] = useState<string | null>(null)

  const fetchAlerts = async () => {
    try {
      setLoading(true)
      const data: any = await api.getAlerts(filterStatus, filterSeverity)
      setAlerts(data.alerts || [])
      setSummary(data.summary || {})
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchAlerts()
  }, [filterStatus, filterSeverity])

  const handleAcknowledge = async (id: string) => {
    await api.updateAlertStatus(id, 'acknowledged', '已确认，开始处理')
    fetchAlerts()
  }

  const handleResolve = async (id: string) => {
    await api.updateAlertStatus(id, 'resolved', '问题已解决')
    fetchAlerts()
  }

  const columns = [
    {
      title: '严重程度',
      dataIndex: 'severity',
      key: 'severity',
      width: 100,
      render: (v: string) => {
        const s = severityMap[v] || severityMap.info
        return <Tag color={s.color} icon={s.icon}>{s.label}</Tag>
      },
    },
    { title: '类型', dataIndex: 'type', key: 'type', width: 140 },
    { title: '标题', dataIndex: 'title', key: 'title', ellipsis: true },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (v: string) => <Tag color={v === 'resolved' ? 'green' : v === 'new' ? 'red' : 'blue'}>{statusMap[v] || v}</Tag>,
    },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 170, render: (v: string) => new Date(v).toLocaleString('zh-CN') },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_: any, record: AlertItem) => (
        <Space>
          <Button size="small" onClick={() => setDetailModal(record)}>详情</Button>
          {record.status === 'new' && (
            <Button size="small" type="primary" onClick={() => handleAcknowledge(record.id)}>确认</Button>
          )}
          {record.status !== 'resolved' && record.status !== 'dismissed' && (
            <Button size="small" type="primary" ghost onClick={() => handleResolve(record.id)}>解决</Button>
          )}
        </Space>
      ),
    },
  ]

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />
  if (error) return <Alert type="error" message={`加载失败: ${error}`} showIcon />

  return (
    <div>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={6}>
          <Card><Statistic title="预警总数" value={summary.total || alerts.length} prefix={<WarningOutlined />} /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card><Statistic title="严重" value={summary.critical_count || 0} valueStyle={{ color: '#cf1322' }} /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card><Statistic title="警告" value={summary.warning_count || 0} valueStyle={{ color: '#fa8c16' }} /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card><Statistic title="待处理" value={summary.new_count || 0} valueStyle={{ color: '#1677ff' }} /></Card>
        </Col>
      </Row>

      <Space style={{ marginBottom: 16 }}>
        <Select
          placeholder="按状态筛选"
          allowClear
          style={{ width: 150 }}
          value={filterStatus}
          onChange={setFilterStatus}
          options={Object.entries(statusMap).map(([k, v]) => ({ value: k, label: v }))}
        />
        <Select
          placeholder="按严重程度筛选"
          allowClear
          style={{ width: 150 }}
          value={filterSeverity}
          onChange={setFilterSeverity}
          options={[
            { value: 'critical', label: '严重' },
            { value: 'warning', label: '警告' },
            { value: 'info', label: '提示' },
          ]}
        />
      </Space>

      <Table
        dataSource={alerts}
        columns={columns}
        rowKey="id"
        pagination={{ pageSize: 10 }}
        size="middle"
      />

      <Modal
        title="预警详情"
        open={!!detailModal}
        onCancel={() => setDetailModal(null)}
        footer={[
          <Button key="close" onClick={() => setDetailModal(null)}>关闭</Button>,
        ]}
        width={700}
      >
        {detailModal && (
          <div>
            <p><strong>类型：</strong>{detailModal.type}</p>
            <p><strong>严重程度：</strong><Tag color={severityMap[detailModal.severity]?.color}>{severityMap[detailModal.severity]?.label}</Tag></p>
            <p><strong>标题：</strong>{detailModal.title}</p>
            <p><strong>描述：</strong>{detailModal.description}</p>
            <p><strong>建议行动：</strong>{detailModal.recommended_action}</p>
            <p><strong>指标数据：</strong></p>
            <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 4, maxHeight: 200, overflow: 'auto' }}>
              {JSON.stringify(detailModal.metric_data, null, 2)}
            </pre>
          </div>
        )}
      </Modal>
    </div>
  )
}
