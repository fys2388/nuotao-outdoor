import { useState, useEffect, useCallback } from 'react'
import {
  Card, Row, Col, Typography, Spin, Empty, Alert, Table, Tag,
  Button, Switch, Modal, Form, Input, Select, Space,
} from 'antd'
import {
  ThunderboltOutlined, ReloadOutlined, PlusOutlined,
  DeleteOutlined, EditOutlined, PlayCircleOutlined,
} from '@ant-design/icons'
import { api, ApiError } from '../api/client'

const { Title, Text } = Typography

interface Workflow {
  id: string
  name: string
  description: string
  trigger: string
  status: 'active' | 'inactive'
  last_run?: string
  success_rate: number
  created_at: string
}

export default function CreativeAutomation() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [workflows, setWorkflows] = useState<Workflow[]>([])
  const [modalVisible, setModalVisible] = useState(false)
  const [form] = Form.useForm()

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.getCreativeAutomationWorkflows(50, 0)
      setWorkflows((data as any).workflows || [])
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

  const handleCreate = async () => {
    try {
      const values = await form.validateFields()
      await api.createCreativeAutomationWorkflow(values)
      setModalVisible(false)
      form.resetFields()
      await loadData()
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`创建失败: ${err.message}`)
      }
    }
  }

  const handleToggle = async (id: string, active: boolean) => {
    try {
      await api.updateCreativeAutomationWorkflow(id, { status: active ? 'active' : 'inactive' })
      await loadData()
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`更新失败: ${err.message}`)
      }
    }
  }

  const handleTrigger = async (id: string) => {
    try {
      await api.triggerCreativeAutomationWorkflow(id)
      await loadData()
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`触发失败: ${err.message}`)
      }
    }
  }

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
            <ThunderboltOutlined /> Automation Builder
          </Title>
          <Text type="secondary">自动化工作流管理</Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => void loadData()}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalVisible(true)}>
            New Workflow
          </Button>
        </Space>
      </div>

      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} showIcon />}

      <Card title="Workflows" size="small">
        {workflows.length === 0 ? (
          <Empty description="暂无工作流。点击 New Workflow 创建。" />
        ) : (
          <Table
            size="small"
            dataSource={workflows}
            rowKey="id"
            pagination={{ pageSize: 10 }}
            columns={[
              { title: 'Name', dataIndex: 'name', key: 'name', width: 200 },
              { title: 'Trigger', dataIndex: 'trigger', key: 'trigger', width: 120,
                render: (t: string) => <Tag color="blue">{t}</Tag> },
              { title: 'Status', dataIndex: 'status', key: 'status', width: 100,
                render: (s: string, record: Workflow) => (
                  <Switch
                    checked={s === 'active'}
                    onChange={(checked) => void handleToggle(record.id, checked)}
                    checkedChildren="Active"
                    unCheckedChildren="Inactive"
                  />
                ) },
              { title: 'Success Rate', dataIndex: 'success_rate', key: 'success_rate', width: 100,
                render: (r: number) => <Tag color={r > 0.8 ? 'success' : r > 0.5 ? 'warning' : 'error'}>
                  {(r * 100).toFixed(0)}%
                </Tag> },
              { title: 'Last Run', dataIndex: 'last_run', key: 'last_run', width: 160,
                render: (d: string) => d ? new Date(d).toLocaleString() : '-' },
              { title: 'Actions', key: 'actions', width: 150,
                render: (_: unknown, record: Workflow) => (
                  <Space>
                    <Button size="small" type="link" icon={<PlayCircleOutlined />}
                      onClick={() => void handleTrigger(record.id)}>
                      Run
                    </Button>
                  </Space>
                ) },
            ]}
          />
        )}
      </Card>

      {/* Create Workflow Modal */}
      <Modal
        open={modalVisible}
        title="New Workflow"
        onCancel={() => setModalVisible(false)}
        onOk={() => void handleCreate()}
        okText="Create"
        cancelText="Cancel"
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input placeholder="Workflow name" />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <Input.TextArea placeholder="Workflow description" />
          </Form.Item>
          <Form.Item name="trigger" label="Trigger" rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'manual', label: 'Manual' },
                { value: 'scheduled', label: 'Scheduled' },
                { value: 'event', label: 'Event' },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}