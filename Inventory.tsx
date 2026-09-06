import { useEffect, useState, useMemo } from 'react'
import { Table, Tag, Button, Space, Modal, Form, Input, InputNumber, Select, Spin, Alert, Row, Col, Card, Statistic, Popconfirm, message, Dropdown, Badge } from 'antd'
import { DatabaseOutlined, PlusOutlined, ShopOutlined, SearchOutlined, ReloadOutlined, DownloadOutlined, DeleteOutlined, CheckCircleOutlined, CloseCircleOutlined, SettingOutlined, ExportOutlined } from '@ant-design/icons'
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

const mockWarehouses: Warehouse[] = [
  { id: '1', name: '深圳国内仓', type: 'domestic', status: 'active', country: 'China', city: 'Shenzhen', total_sku: 120, created_at: '2024-01-15' },
  { id: '2', name: '洛杉矶海外仓', type: 'overseas', status: 'active', country: 'USA', city: 'Los Angeles', total_sku: 85, created_at: '2024-02-10' },
  { id: '3', name: '法兰克福履约中心', type: 'fulfillment_center', status: 'active', country: 'Germany', city: 'Frankfurt', total_sku: 60, created_at: '2024-03-01' },
  { id: '4', name: '广州代发仓', type: 'drop_shipping', status: 'inactive', country: 'China', city: 'Guangzhou', total_sku: 200, created_at: '2024-01-20' },
  { id: '5', name: '英国海外仓', type: 'overseas', status: 'active', country: 'UK', city: 'London', total_sku: 45, created_at: '2024-04-01' },
]

export default function InventoryPage() {
  const [loading, setLoading] = useState(true)
  const [warehouses, setWarehouses] = useState<Warehouse[]>([])
  const [createModal, setCreateModal] = useState(false)
  const [form] = Form.useForm()
  const [error, setError] = useState<string | null>(null)
  const [searchText, setSearchText] = useState('')
  const [typeFilter, setTypeFilter] = useState<string[]>([])
  const [statusFilter, setStatusFilter] = useState<string[]>([])
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])

  const fetchWarehouses = async () => {
    try {
      setLoading(true)
      const data: any = await api.getWarehouses()
      setWarehouses(data.warehouses?.length ? data.warehouses : mockWarehouses)
    } catch (e: any) {
      setWarehouses(mockWarehouses)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchWarehouses()
  }, [])

  const filteredWarehouses = useMemo(() => {
    return warehouses.filter((w) => {
      const matchSearch = !searchText ||
        w.name.toLowerCase().includes(searchText.toLowerCase()) ||
        w.country.toLowerCase().includes(searchText.toLowerCase()) ||
        w.city.toLowerCase().includes(searchText.toLowerCase())
      const matchType = typeFilter.length === 0 || typeFilter.includes(w.type)
      const matchStatus = statusFilter.length === 0 || statusFilter.includes(w.status)
      return matchSearch && matchType && matchStatus
    })
  }, [warehouses, searchText, typeFilter, statusFilter])

  const stats = useMemo(() => ({
    total: warehouses.length,
    overseas: warehouses.filter(w => w.type === 'overseas').length,
    domestic: warehouses.filter(w => w.type === 'domestic').length,
    active: warehouses.filter(w => w.status === 'active').length,
    totalSku: warehouses.reduce((sum, w) => sum + w.total_sku, 0),
  }), [warehouses])

  const handleBatchAction = (action: string) => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先选择仓库')
      return
    }
    if (action === 'delete') {
      Modal.confirm({
        title: '确认删除',
        content: `确定要删除选中的 ${selectedRowKeys.length} 个仓库吗？`,
        okText: '确认删除',
        okType: 'danger',
        onOk: () => {
          setWarehouses(warehouses.filter((w) => !selectedRowKeys.includes(w.id)))
          setSelectedRowKeys([])
          message.success('删除成功')
        },
      })
      return
    }
    const newStatus = action === 'enable' ? 'active' : 'inactive'
    setWarehouses(warehouses.map((w) =>
      selectedRowKeys.includes(w.id) ? { ...w, status: newStatus } : w
    ))
    message.success(`已${action === 'enable' ? '启用' : '禁用'} ${selectedRowKeys.length} 个仓库`)
  }

  const handleExport = () => {
    const data = filteredWarehouses
    const csv = ['ID,仓库名称,类型,状态,国家,城市,SKU数量,创建时间',
      ...data.map((w) => `${w.id},${w.name},${typeMap[w.type]?.label || w.type},${w.status === 'active' ? '运营中' : w.status},${w.country},${w.city},${w.total_sku},${w.created_at}`)
    ].join('\n')
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `warehouses_${new Date().toISOString().split('T')[0]}.csv`
    link.click()
    message.success(`已导出 ${data.length} 个仓库`)
  }

  const columns = [
    { title: '仓库名称', dataIndex: 'name', key: 'name', sorter: (a: Warehouse, b: Warehouse) => a.name.localeCompare(b.name) },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      filters: Object.entries(typeMap).map(([value, { label }]) => ({ text: label, value })),
      onFilter: (value: any, record: Warehouse) => record.type === value,
      render: (v: string) => <Tag color={typeMap[v]?.color}>{typeMap[v]?.label || v}</Tag>,
    },
    { title: '国家', dataIndex: 'country', key: 'country', sorter: (a: Warehouse, b: Warehouse) => a.country.localeCompare(b.country) },
    { title: '城市', dataIndex: 'city', key: 'city' },
    { title: 'SKU 数量', dataIndex: 'total_sku', key: 'total_sku', sorter: (a: Warehouse, b: Warehouse) => a.total_sku - b.total_sku },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      filters: [{ text: '运营中', value: 'active' }, { text: '已禁用', value: 'inactive' }],
      onFilter: (value: any, record: Warehouse) => record.status === value,
      render: (v: string) => <Tag color={v === 'active' ? 'green' : 'default'}>{v === 'active' ? '运营中' : '已禁用'}</Tag>,
    },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', sorter: (a: Warehouse, b: Warehouse) => a.created_at.localeCompare(b.created_at) },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: Warehouse) => (
        <Space size="small">
          <Button type="link" size="small">编辑</Button>
          <Popconfirm title="确定删除该仓库？" onConfirm={() => { setWarehouses(warehouses.filter(w => w.id !== record.id)); message.success('删除成功') }} okText="确定" cancelText="取消">
            <Button type="link" size="small" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const rowSelection = {
    selectedRowKeys,
    onChange: (keys: React.Key[]) => setSelectedRowKeys(keys),
  }

  const batchMenuItems = [
    { key: 'enable', icon: <CheckCircleOutlined />, label: '批量启用' },
    { key: 'disable', icon: <CloseCircleOutlined />, label: '批量禁用' },
    { type: 'divider' as const },
    { key: 'export', icon: <ExportOutlined />, label: '导出选中' },
    { type: 'divider' as const },
    { key: 'delete', icon: <DeleteOutlined />, danger: true, label: '批量删除' },
  ]

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />

  return (
    <div style={{ padding: 24 }}>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={6}><Card><Statistic title="仓库总数" value={stats.total} prefix={<ShopOutlined />} /></Card></Col>
        <Col xs={12} sm={6}><Card><Statistic title="海外仓" value={stats.overseas} valueStyle={{ color: '#52c41a' }} /></Card></Col>
        <Col xs={12} sm={6}><Card><Statistic title="国内仓" value={stats.domestic} valueStyle={{ color: '#1677ff' }} /></Card></Col>
        <Col xs={12} sm={6}><Card><Statistic title="SKU总数" value={stats.totalSku} prefix={<DatabaseOutlined />} /></Card></Col>
      </Row>

      <Card style={{ marginBottom: 16 }}>
        <Space wrap size="middle">
          <Input
            placeholder="搜索仓库名称 / 国家 / 城市"
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            allowClear
            style={{ width: 260 }}
          />
          <Select
            mode="multiple"
            placeholder="仓库类型"
            value={typeFilter}
            onChange={setTypeFilter}
            style={{ width: 160 }}
            maxTagCount={1}
            options={Object.entries(typeMap).map(([value, { label }]) => ({ value, label }))}
          />
          <Select
            mode="multiple"
            placeholder="状态"
            value={statusFilter}
            onChange={setStatusFilter}
            style={{ width: 130 }}
            maxTagCount={1}
            options={[{ value: 'active', label: '运营中' }, { value: 'inactive', label: '已禁用' }]}
          />
          <Button icon={<ReloadOutlined />} onClick={fetchWarehouses}>刷新</Button>
          <Button icon={<DownloadOutlined />} onClick={handleExport}>导出</Button>
          <Dropdown menu={{ items: batchMenuItems, onClick: ({ key }) => { if (key === 'export') { handleExport() } else { handleBatchAction(key) } } }}>
            <Button icon={<SettingOutlined />}>批量操作 <Badge count={selectedRowKeys.length} showZero style={{ marginLeft: 8 }} /></Button>
          </Dropdown>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModal(true)}>新建仓库</Button>
        </Space>
      </Card>

      <Card>
        <Table
          rowSelection={rowSelection}
          dataSource={filteredWarehouses}
          columns={columns}
          rowKey="id"
          pagination={{ showSizeChanger: true, showQuickJumper: true, showTotal: (total) => `共 ${total} 条`, pageSizeOptions: ['10', '20', '50'] }}
          size="middle"
        />
      </Card>

      <Modal title="新建仓库" open={createModal} onCancel={() => setCreateModal(false)} footer={null} width={600}>
        <Form form={form} layout="vertical" onFinish={(values) => {
          const newWarehouse: Warehouse = {
            id: String(Date.now()),
            name: values.name,
            type: values.warehouse_type,
            status: 'active',
            country: values.country,
            city: values.city,
            total_sku: 0,
            created_at: new Date().toISOString().split('T')[0],
          }
          setWarehouses([newWarehouse, ...warehouses])
          setCreateModal(false)
          form.resetFields()
          message.success('仓库创建成功')
        }}>
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
          <Form.Item>
            <Button type="primary" htmlType="submit" block>创建仓库</Button>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
