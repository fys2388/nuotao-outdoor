import { useEffect, useState } from 'react'
import { Table, Tag, Button, Space, Modal, Form, Input, InputNumber, Select, Spin, Alert, Row, Col, Card, Statistic } from 'antd'
import { DatabaseOutlined, PlusOutlined, ShopOutlined } from '@ant-design/icons'
import { api } from '../api/client'

interface Warehouse {
  id: string
  name: string
  type: string
  status: string
  country: string
  city: string
  total_sku: number
  created_at: string
}

const typeMap: Record<string, { color: string; label: string }> = {
  domestic: { color: 'blue', label: '国内仓' },
  overseas: { color: 'green', label: '海外仓' },
  fulfillment_center: { color: 'purple', label: '履约中心' },
  drop_shipping: { color: 'orange', label: '代发仓' },
}

export default function InventoryPage() {
  const [loading, setLoading] = useState(true)
  const [warehouses, setWarehouses] = useState<Warehouse[]>([])
  const [createModal, setCreateModal] = useState(false)
  const [form] = Form.useForm()
  const [error, setError] = useState<string | null>(null)

  const fetchWarehouses = async () => {
    try {
      setLoading(true)
      const data: any = await api.getWarehouses()
      setWarehouses(data.warehouses || [])
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchWarehouses()
  }, [])

  const handleCreate = async (values: any) => {
    try {
      await api.createWarehouse(values)
      setCreateModal(false)
      form.resetFields()
      fetchWarehouses()
    } catch (e: any) {
      setError(e.message)
    }
  }

  const columns = [
    { title: '仓库名称', dataIndex: 'name', key: 'name' },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      render: (v: string) => <Tag color={typeMap[v]?.color}>{typeMap[v]?.label || v}</Tag>,
    },
    { title: '国家', dataIndex: 'country', key: 'country' },
    { title: '城市', dataIndex: 'city', key: 'city' },
    { title: 'SKU 数量', dataIndex: 'total_sku', key: 'total_sku' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (v: string) => <Tag color={v === 'active' ? 'green' : 'default'}>{v === 'active' ? '运营中' : v}</Tag>,
    },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', render: (v: string) => new Date(v).toLocaleDateString('zh-CN') },
  ]

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />
  if (error) return <Alert type="error" message={`加载失败: ${error}`} showIcon />

  return (
    <div>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={8}>
          <Card><Statistic title="仓库总数" value={warehouses.length} prefix={<ShopOutlined />} /></Card>
        </Col>
        <Col xs={12} sm={8}>
          <Card><Statistic title="海外仓" value={warehouses.filter(w => w.type === 'overseas').length} valueStyle={{ color: '#52c41a' }} /></Card>
        </Col>
        <Col xs={12} sm={8}>
          <Card><Statistic title="国内仓" value={warehouses.filter(w => w.type === 'domestic').length} valueStyle={{ color: '#1677ff' }} /></Card>
        </Col>
      </Row>

      <div style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModal(true)}>
          新建仓库
        </Button>
      </div>

      <Table
        dataSource={warehouses}
        columns={columns}
        rowKey="id"
        pagination={{ pageSize: 10 }}
        size="middle"
      />

      <Modal
        title="新建仓库"
        open={createModal}
        onCancel={() => setCreateModal(false)}
        footer={null}
        width={600}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item name="name" label="仓库名称" rules={[{ required: true }]}>
            <Input placeholder="如：深圳国内仓、洛杉矶海外仓" />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="warehouse_type" label="仓库类型" rules={[{ required: true }]}>
                <Select options={[
                  { value: 'domestic', label: '国内仓' },
                  { value: 'overseas', label: '海外仓' },
                  { value: 'fulfillment_center', label: '履约中心' },
                  { value: 'drop_shipping', label: '代发仓' },
                ]} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="handling_days" label="处理天数" initialValue={2}>
                <InputNumber min={1} max={30} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="country" label="国家" rules={[{ required: true }]}>
                <Input placeholder="如：China、USA" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="city" label="城市" rules={[{ required: true }]}>
                <Input placeholder="如：Shenzhen、Los Angeles" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="address" label="详细地址">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="contact_person" label="联系人">
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="contact_email" label="联系邮箱">
                <Input />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item>
            <Button type="primary" htmlType="submit" block>创建仓库</Button>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
