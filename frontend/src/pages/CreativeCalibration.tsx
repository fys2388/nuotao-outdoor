import { useState, useEffect, useCallback } from 'react'
import {
  Card, Row, Col, Typography, Spin, Empty, Alert, Table, Tag,
  Button, Progress, Descriptions,
} from 'antd'
import {
  ExperimentOutlined, ReloadOutlined, CheckCircleOutlined,
  CloseCircleOutlined, LoadingOutlined,
} from '@ant-design/icons'
import { api, ApiError } from '../api/client'

const { Title, Text } = Typography

interface CalibrationRun {
  id: string
  status: string
  model: string
  baseline_score: number
  calibrated_score: number
  improvement: number
  created_at: string
  completed_at?: string
}

export default function CreativeCalibration() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [runs, setRuns] = useState<CalibrationRun[]>([])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.getCreativeCalibrationRuns(20)
      setRuns((data as any).runs || [])
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
            <ExperimentOutlined /> Calibration
          </Title>
          <Text type="secondary">模型校准与质量调优</Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => void loadData()}>刷新</Button>
      </div>

      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} showIcon />}

      <Card title="Calibration Runs" size="small">
        {runs.length === 0 ? (
          <Empty description="暂无校准运行" />
        ) : (
          <Table
            size="small"
            dataSource={runs}
            rowKey="id"
            pagination={false}
            columns={[
              { title: 'Run ID', dataIndex: 'id', key: 'id', width: 100,
                render: (id: string) => <Text code style={{ fontSize: 11 }}>{id.slice(0, 8)}...</Text> },
              { title: 'Model', dataIndex: 'model', key: 'model', width: 200 },
              { title: 'Status', dataIndex: 'status', key: 'status', width: 100,
                render: (s: string) => {
                  const icon = s === 'completed' ? <CheckCircleOutlined />
                    : s === 'failed' ? <CloseCircleOutlined />
                    : <LoadingOutlined />
                  return <Tag color={s === 'completed' ? 'success' : s === 'failed' ? 'error' : 'processing'} icon={icon}>
                    {s}
                  </Tag>
                } },
              { title: 'Baseline', dataIndex: 'baseline_score', key: 'baseline', width: 100,
                render: (s: number) => s.toFixed(3) },
              { title: 'Calibrated', dataIndex: 'calibrated_score', key: 'calibrated', width: 100,
                render: (s: number) => s.toFixed(3) },
              { title: 'Improvement', dataIndex: 'improvement', key: 'improvement', width: 120,
                render: (i: number) => <Tag color={i > 0 ? 'success' : i < 0 ? 'error' : 'default'}>
                  {i > 0 ? '+' : ''}{(i * 100).toFixed(1)}%
                </Tag> },
              { title: 'Created', dataIndex: 'created_at', key: 'created_at', width: 160,
                render: (d: string) => d ? new Date(d).toLocaleString() : '-' },
            ]}
          />
        )}
      </Card>
    </div>
  )
}