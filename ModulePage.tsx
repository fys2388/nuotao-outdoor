import { useState, useEffect, useMemo } from 'react'
import {
  Table, Button, Modal, Form, Input, Select, InputNumber,
  DatePicker, Space, Tag, Card, Row, Col, Statistic, message,
  Popconfirm, Typography, Descriptions, Badge, Dropdown
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, EyeOutlined,
  ReloadOutlined, SearchOutlined, SettingOutlined, ExportOutlined,
  CheckCircleOutlined, CloseCircleOutlined, FilterOutlined
} from '@ant-design/icons'
import type { ColumnsType, TableRowSelection } from 'antd/es/table'

const { Title, Text } = Typography
const { TextArea } = Input
const { RangePicker } = DatePicker

export interface FieldConfig {
  key: string
  label: string
  type: 'text' | 'textarea' | 'number' | 'select' | 'date' | 'status'
  options?: { label: string; value: string }[]
  required?: boolean
  placeholder?: string
  inForm?: boolean
  inTable?: boolean
  width?: number
  filterable?: boolean
}

export interface ModuleConfig {
  key: string
  title: string
  description: string
  apiEndpoint: string
  fields: FieldConfig[]
  stats?: { title: string; value: number | string; color?: string }[]
  defaultData?: Record<string, any>[]
}

interface ModulePageProps {
  config: ModuleConfig
}

export default function ModulePage({ config }: ModulePageProps) {
  const [data, setData] = useState<Record<string, any>[]>(config.defaultData || [])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)
  const [editingRecord, setEditingRecord] = useState<Record<string, any> | null>(null)
  const [detailRecord, setDetailRecord] = useState<Record<string, any> | null>(null)
  const [form] = Form.useForm()
  const [searchText, setSearchText] = useState('')
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])
  const [filterValues, setFilterValues] = useState<Record<string, string[]>>({})

  useEffect(() => {
    if (config.defaultData && config.defaultData.length > 0) {
      setData(config.defaultData)
    }
  }, [config])

  const tableFields = config.fields.filter(f => f.inTable !== false)

  // 可筛选的字段（select和status类型）
  const filterableFields = config.fields.filter(f =>
    (f.type === 'select' || f.type === 'status') && f.filterable !== false && f.options
  )

  const getStatusColor = (status: string) => {
    const colors: Record<string, string> = {
      active: 'green', enabled: 'green', completed: 'green', success: 'green',
      pending: 'orange', processing: 'blue', draft: 'default',
      inactive: 'red', disabled: 'red', failed: 'red', error: 'red',
      sent: 'blue', scheduled: 'purple', published: 'green',
    }
    return colors[status?.toLowerCase()] || 'default'
  }

  const columns: ColumnsType<Record<string, any>> = [
    ...tableFields.map(field => ({
      title: field.label,
      dataIndex: field.key,
      key: field.key,
      width: field.width,
      filters: (field.type === 'select' || field.type === 'status') && field.options
        ? field.options.map(o => ({ text: o.label, value: o.value }))
        : undefined,
      onFilter: (value: any, record: Record<string, any>) => record[field.key] === value,
      render: (value: any) => {
        if (field.type === 'status') {
          return <Tag color={getStatusColor(value)}>{value}</Tag>
        }
        if (field.type === 'select' && field.options) {
          const opt = field.options.find(o => o.value === value)
          return opt ? opt.label : value
        }
        if (typeof value === 'boolean') {
          return <Badge status={value ? 'success' : 'error'} text={value ? '是' : '否'} />
        }
        return value || '-'
      },
    })),
    {
      title: '操作',
      key: 'actions',
      width: 180,
      fixed: 'right' as const,
      render: (_: any, record: Record<string, any>) => (
        <Space size="small">
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => handleView(record)}>
            查看
          </Button>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>
            编辑
          </Button>
          <Popconfirm title="确定删除？" onConfirm={() => handleDelete(record)}>
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const handleView = (record: Record<string, any>) => {
    setDetailRecord(record)
    setDetailOpen(true)
  }

  const handleEdit = (record: Record<string, any>) => {
    setEditingRecord(record)
    form.setFieldsValue(record)
    setModalOpen(true)
  }

  const handleAdd = () => {
    setEditingRecord(null)
    form.resetFields()
    setModalOpen(true)
  }

  const handleDelete = (record: Record<string, any>) => {
    setData(prev => prev.filter(item => item.id !== record.id))
    message.success('删除成功')
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      if (editingRecord) {
        setData(prev => prev.map(item =>
          item.id === editingRecord.id ? { ...item, ...values } : item
        ))
        message.success('更新成功')
      } else {
        const newRecord = { ...values, id: Date.now(), created_at: new Date().toISOString() }
        setData(prev => [newRecord, ...prev])
        message.success('创建成功')
      }
      setModalOpen(false)
    } catch {
      // 表单验证失败
    }
  }

  const handleRefresh = () => {
    setLoading(true)
    setTimeout(() => {
      setLoading(false)
      message.success('数据已刷新')
    }, 500)
  }

  // 批量操作
  const handleBatchDelete = () => {
    Modal.confirm({
      title: '确认批量删除',
      content: `确定要删除选中的 ${selectedRowKeys.length} 条记录吗？此操作不可恢复。`,
      okText: '确认删除',
      okType: 'danger',
      onOk: () => {
        setData(prev => prev.filter(item => !selectedRowKeys.includes(item.id)))
        setSelectedRowKeys([])
        message.success(`已删除 ${selectedRowKeys.length} 条记录`)
      },
    })
  }

  const handleBatchStatus = (status: string) => {
    setData(prev => prev.map(item =>
      selectedRowKeys.includes(item.id) ? { ...item, status } : item
    ))
    message.success(`已将 ${selectedRowKeys.length} 条记录状态更新为「${status}」`)
    setSelectedRowKeys([])
  }

  const handleExport = (selectedOnly = false) => {
    const exportData = selectedOnly ? data.filter(item => selectedRowKeys.includes(item.id)) : filteredData
    const headers = tableFields.map(f => f.label).join(',')
    const rows = exportData.map(item =>
      tableFields.map(f => {
        const val = item[f.key]
        if (typeof val === 'string' && val.includes(',')) return `"${val}"`
        return val ?? ''
      }).join(',')
    )
    const csv = [headers, ...rows].join('\n')
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `${config.key}_${new Date().toISOString().split('T')[0]}.csv`
    link.click()
    message.success(`已导出 ${exportData.length} 条记录`)
  }

  const resetFilters = () => {
    setSearchText('')
    setFilterValues({})
    message.info('筛选条件已重置')
  }

  // 筛选后的数据
  const filteredData = useMemo(() => {
    return data.filter(item => {
      // 搜索
      const matchSearch = !searchText ||
        Object.values(item).some(v =>
          String(v).toLowerCase().includes(searchText.toLowerCase())
        )
      // 筛选器
      const matchFilters = Object.entries(filterValues).every(([key, values]) =>
        values.length === 0 || values.includes(item[key])
      )
      return matchSearch && matchFilters
    })
  }, [data, searchText, filterValues])

  const formFields = config.fields.filter(f => f.inForm !== false)

  const rowSelection: TableRowSelection<Record<string, any>> = {
    selectedRowKeys,
    onChange: (keys) => setSelectedRowKeys(keys),
    preserveSelectedRowKeys: true,
  }

  const batchMenuItems = [
    { key: 'activate', icon: <CheckCircleOutlined />, label: '批量启用' },
    { key: 'deactivate', icon: <CloseCircleOutlined />, label: '批量禁用' },
    { type: 'divider' as const },
    { key: 'exportSelected', icon: <ExportOutlined />, label: '导出选中' },
    { type: 'divider' as const },
    { key: 'delete', icon: <DeleteOutlined />, danger: true, label: '批量删除' },
  ]

  return (
    <div>
      {/* 统计卡片 */}
      {config.stats && config.stats.length > 0 && (
        <Row gutter={16} style={{ marginBottom: 24 }}>
          {config.stats.map((stat, idx) => (
            <Col span={24 / config.stats!.length} key={idx}>
              <Card>
                <Statistic title={stat.title} value={stat.value} valueStyle={{ color: stat.color || '#1677ff' }} />
              </Card>
            </Col>
          ))}
        </Row>
      )}

      {/* 模块描述 */}
      <Card style={{ marginBottom: 16 }}>
        <Text type="secondary">{config.description}</Text>
      </Card>

      {/* 筛选栏 */}
      {filterableFields.length > 0 && (
        <Card style={{ marginBottom: 16 }}>
          <Space wrap size="middle">
            <Input
              placeholder="搜索..."
              prefix={<SearchOutlined />}
              value={searchText}
              onChange={e => setSearchText(e.target.value)}
              style={{ width: 240 }}
              allowClear
            />
            {filterableFields.map(field => (
              <Select
                key={field.key}
                mode="multiple"
                placeholder={field.label}
                value={filterValues[field.key] || []}
                onChange={(values) => setFilterValues(prev => ({ ...prev, [field.key]: values }))}
                style={{ width: 150 }}
                maxTagCount={1}
                options={field.options}
              />
            ))}
            <Button icon={<FilterOutlined />} onClick={resetFilters}>重置筛选</Button>
            <span style={{ color: '#999', fontSize: 12 }}>
              筛选结果: {filteredData.length} / {data.length} 条
            </span>
          </Space>
        </Card>
      )}

      {/* 工具栏 */}
      <Card>
        <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
          <Space wrap>
            {filterableFields.length === 0 && (
              <Input
                placeholder="搜索..."
                prefix={<SearchOutlined />}
                value={searchText}
                onChange={e => setSearchText(e.target.value)}
                style={{ width: 240 }}
                allowClear
              />
            )}
            <Button icon={<ReloadOutlined />} onClick={handleRefresh}>刷新</Button>
            <Button icon={<ExportOutlined />} onClick={() => handleExport(false)}>导出全部</Button>
            <Dropdown menu={{
              items: batchMenuItems,
              onClick: ({ key }) => {
                if (selectedRowKeys.length === 0 && key !== 'exportAll') {
                  message.warning('请先选择记录')
                  return
                }
                if (key === 'delete') handleBatchDelete()
                else if (key === 'activate') handleBatchStatus('active')
                else if (key === 'deactivate') handleBatchStatus('inactive')
                else if (key === 'exportSelected') handleExport(true)
              }
            }}>
              <Button icon={<SettingOutlined />}>
                批量操作 <Badge count={selectedRowKeys.length} showZero style={{ marginLeft: 8 }} />
              </Button>
            </Dropdown>
            {selectedRowKeys.length > 0 && (
              <span style={{ color: '#1677ff' }}>
                已选择 {selectedRowKeys.length} 项
                <Button type="link" onClick={() => setSelectedRowKeys([])}>取消选择</Button>
              </span>
            )}
          </Space>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
            新建{config.title.replace('管理', '').replace('系统', '').replace('自动化', '')}
          </Button>
        </Space>

        {/* 数据表格 */}
        <Table
          rowSelection={rowSelection}
          columns={columns}
          dataSource={filteredData}
          rowKey="id"
          loading={loading}
          pagination={{
            pageSize: 10,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total) => `共 ${total} 条`,
          }}
          scroll={{ x: 'max-content' }}
        />
      </Card>

      {/* 新建/编辑弹窗 */}
      <Modal
        title={editingRecord ? `编辑${config.title}` : `新建${config.title}`}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleSubmit}
        width={640}
        destroyOnClose
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          {formFields.map(field => (
            <Form.Item
              key={field.key}
              name={field.key}
              label={field.label}
              rules={field.required ? [{ required: true, message: `请输入${field.label}` }] : []}
            >
              {field.type === 'text' && <Input placeholder={field.placeholder || `请输入${field.label}`} />}
              {field.type === 'textarea' && <TextArea rows={3} placeholder={field.placeholder || `请输入${field.label}`} />}
              {field.type === 'number' && <InputNumber style={{ width: '100%' }} placeholder={field.placeholder || `请输入${field.label}`} />}
              {field.type === 'select' && (
                <Select placeholder={field.placeholder || `请选择${field.label}`} options={field.options} />
              )}
              {field.type === 'date' && <DatePicker style={{ width: '100%' }} />}
              {field.type === 'status' && (
                <Select placeholder="请选择状态" options={[
                  { label: '启用', value: 'active' },
                  { label: '禁用', value: 'inactive' },
                  { label: '待处理', value: 'pending' },
                  { label: '处理中', value: 'processing' },
                  { label: '已完成', value: 'completed' },
                ]} />
              )}
            </Form.Item>
          ))}
        </Form>
      </Modal>

      {/* 详情弹窗 */}
      <Modal
        title={`${config.title}详情`}
        open={detailOpen}
        onCancel={() => setDetailOpen(false)}
        footer={null}
        width={640}
      >
        {detailRecord && (
          <Descriptions bordered column={1} size="small">
            {config.fields.map(field => (
              <Descriptions.Item key={field.key} label={field.label}>
                {field.type === 'status' ? (
                  <Tag color={getStatusColor(detailRecord[field.key])}>{detailRecord[field.key]}</Tag>
                ) : (
                  String(detailRecord[field.key] || '-')
                )}
              </Descriptions.Item>
            ))}
          </Descriptions>
        )}
      </Modal>
    </div>
  )
}
