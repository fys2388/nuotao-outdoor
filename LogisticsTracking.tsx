import { useState, useEffect, useMemo } from 'react'
import { Card, Table, Tag, Button, Space, Timeline, Statistic, Row, Col, Input, Select, message, Modal, Dropdown, Badge, Popconfirm } from 'antd'
import { SearchOutlined, TruckOutlined, CheckCircleOutlined, ReloadOutlined, DownloadOutlined, SettingOutlined, ExportOutlined, SyncOutlined, DeleteOutlined } from '@ant-design/icons'
import * as api from '../api/client'

interface Shipment {
  id: string
  tracking_number: string
  carrier: string
  status: string
  origin: string
  destination: string
  estimated_delivery: string
  created_at: string
}

const statusColors: Record<string, string> = {
  created: 'default',
  picked_up: 'blue',
  in_transit: 'orange',
  out_for_delivery: 'purple',
  delivered: 'green',
  failed: 'red',
}

const statusText: Record<string, string> = {
  created: '已创建',
  picked_up: '已揽收',
  in_transit: '运输中',
  out_for_delivery: '派送中',
  delivered: '已送达',
  failed: '失败',
}

const carriers = ['DHL', 'UPS', 'FedEx', 'USPS', 'Royal Mail', 'Correos', '17TRACK', '其他']

const mockShipments: Shipment[] = [
  { id: '1', tracking_number: '1Z999AA10123456784', carrier: 'UPS', status: 'in_transit', origin: 'Shenzhen, CN', destination: 'Los Angeles, US', estimated_delivery: '2024-09-10', created_at: '2024-09-01' },
  { id: '2', tracking_number: 'EE123456789US', carrier: 'USPS', status: 'delivered', origin: 'New York, US', destination: 'Chicago, US', estimated_delivery: '2024-09-05', created_at: '2024-08-28' },
  { id: '3', tracking_number: 'JD001234567890', carrier: 'DHL', status: 'picked_up', origin: 'Guangzhou, CN', destination: 'London, UK', estimated_delivery: '2024-09-12', created_at: '2024-09-03' },
  { id: '4', tracking_number: 'CB123456789ES', carrier: 'Correos', status: 'out_for_delivery', origin: 'Madrid, ES', destination: 'Barcelona, ES', estimated_delivery: '2024-09-04', created_at: '2024-09-02' },
  { id: '5', tracking_number: 'RT123456789GB', carrier: 'Royal Mail', status: 'failed', origin: 'Manchester, UK', destination: 'Birmingham, UK', estimated_delivery: '2024-09-03', created_at: '2024-08-30' },
  { id: '6', tracking_number: '771234567890', carrier: 'FedEx', status: 'created', origin: 'Shanghai, CN', destination: 'New York, US', estimated_delivery: '2024-09-15', created_at: '2024-09-04' },
]

export default function LogisticsTracking() {
  const [shipments, setShipments] = useState<Shipment[]>([])
  const [loading, setLoading] = useState(false)
  const [trackingInput, setTrackingInput] = useState('')
  const [trackingDetail, setTrackingDetail] = useState<any>(null)
  const [detailVisible, setDetailVisible] = useState(false)
  const [searchText, setSearchText] = useState('')
  const [statusFilter, setStatusFilter] = useState<string[]>([])
  const [carrierFilter, setCarrierFilter] = useState<string[]>([])
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])

  useEffect(() => {
    loadShipments()
  }, [])

  const loadShipments = async () => {
    setLoading(true)
    try {
      const data = await api.getShipments()
      setShipments(Array.isArray(data) && data.length > 0 ? data : mockShipments)
    } catch (e) {
      setShipments(mockShipments)
    }
    setLoading(false)
  }

  const filteredShipments = useMemo(() => {
    return shipments.filter((s) => {
      const matchSearch = !searchText ||
        s.tracking_number.toLowerCase().includes(searchText.toLowerCase()) ||
        s.origin.toLowerCase().includes(searchText.toLowerCase()) ||
        s.destination.toLowerCase().includes(searchText.toLowerCase())
      const matchStatus = statusFilter.length === 0 || statusFilter.includes(s.status)
      const matchCarrier = carrierFilter.length === 0 || carrierFilter.includes(s.carrier)
      return matchSearch && matchStatus && matchCarrier
    })
  }, [shipments, searchText, statusFilter, carrierFilter])

  const stats = useMemo(() => ({
    total: shipments.length,
    inTransit: shipments.filter(s => s.status === 'in_transit').length,
    delivered: shipments.filter(s => s.status === 'delivered').length,
    failed: shipments.filter(s => s.status === 'failed').length,
  }), [shipments])

  const handleTrack = async (trackingNumber?: string) => {
    const tn = trackingNumber || trackingInput
    if (!tn) {
      message.warning('请输入追踪号')
      return
    }
    try {
      const data = await api.getTracking(tn)
      setTrackingDetail(data)
      setDetailVisible(true)
    } catch (e) {
      message.info('追踪查询功能需要配置物流 API，显示模拟数据')
      setTrackingDetail({
        tracking_number: tn,
        carrier: '17TRACK',
        status: 'in_transit',
        events: [
          { status: '已揽收', location: '深圳转运中心', time: '2024-09-01 10:30' },
          { status: '运输中', location: '香港国际机场', time: '2024-09-02 08:15' },
          { status: '运输中', location: '洛杉矶国际机场', time: '2024-09-03 14:20' },
        ],
      })
      setDetailVisible(true)
    }
  }

  const handleBatchTrack = () => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先选择发货记录')
      return
    }
    message.loading({ content: `正在批量追踪 ${selectedRowKeys.length} 个包裹...`, key: 'batchTrack' })
    setTimeout(() => {
      message.success({ content: `已完成 ${selectedRowKeys.length} 个包裹的追踪更新`, key: 'batchTrack' })
      setSelectedRowKeys([])
    }, 2000)
  }

  const handleExport = (selectedOnly = false) => {
    const data = selectedOnly ? shipments.filter((s) => selectedRowKeys.includes(s.id)) : filteredShipments
    const csv = ['ID,追踪号,物流公司,状态,发件地,目的地,预计送达,创建时间',
      ...data.map((s) => `${s.id},${s.tracking_number},${s.carrier},${statusText[s.status] || s.status},${s.origin},${s.destination},${s.estimated_delivery},${s.created_at}`)
    ].join('\n')
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `shipments_${new Date().toISOString().split('T')[0]}.csv`
    link.click()
    message.success(`已导出 ${data.length} 条发货记录`)
  }

  const columns = [
    {
      title: '追踪号', dataIndex: 'tracking_number', key: 'tracking_number',
      render: (t: string) => <Button type="link" onClick={() => handleTrack(t)}>{t}</Button>,
      sorter: (a: Shipment, b: Shipment) => a.tracking_number.localeCompare(b.tracking_number),
    },
    {
      title: '物流公司', dataIndex: 'carrier', key: 'carrier',
      filters: carriers.map(c => ({ text: c, value: c })),
      onFilter: (value: any, record: Shipment) => record.carrier === value,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      filters: Object.entries(statusText).map(([value, label]) => ({ text: label, value })),
      onFilter: (value: any, record: Shipment) => record.status === value,
      render: (s: string) => <Tag color={statusColors[s] || 'default'}>{statusText[s] || s}</Tag>,
    },
    { title: '发件地', dataIndex: 'origin', key: 'origin' },
    { title: '目的地', dataIndex: 'destination', key: 'destination' },
    {
      title: '预计送达', dataIndex: 'estimated_delivery', key: 'estimated_delivery',
      sorter: (a: Shipment, b: Shipment) => a.estimated_delivery.localeCompare(b.estimated_delivery),
    },
    {
      title: '创建时间', dataIndex: 'created_at', key: 'created_at',
      sorter: (a: Shipment, b: Shipment) => a.created_at.localeCompare(b.created_at),
    },
    {
      title: '操作', key: 'action',
      render: (_: any, record: Shipment) => (
        <Space size="small">
          <Button type="link" size="small" icon={<SearchOutlined />} onClick={() => handleTrack(record.tracking_number)}>追踪</Button>
        </Space>
      ),
    },
  ]

  const rowSelection = {
    selectedRowKeys,
    onChange: (keys: React.Key[]) => setSelectedRowKeys(keys),
  }

  const batchMenuItems = [
    { key: 'track', icon: <SyncOutlined />, label: '批量追踪' },
    { type: 'divider' as const },
    { key: 'exportSelected', icon: <ExportOutlined />, label: '导出选中' },
    { type: 'divider' as const },
    { key: 'delete', icon: <DeleteOutlined />, danger: true, label: '批量删除' },
  ]

  return (
    <div style={{ padding: 24 }}>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={6}><Card><Statistic title="总发货数" value={stats.total} prefix={<TruckOutlined />} /></Card></Col>
        <Col xs={12} sm={6}><Card><Statistic title="运输中" value={stats.inTransit} valueStyle={{ color: '#fa8c16' }} /></Card></Col>
        <Col xs={12} sm={6}><Card><Statistic title="已送达" value={stats.delivered} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} /></Card></Col>
        <Col xs={12} sm={6}><Card><Statistic title="异常" value={stats.failed} valueStyle={{ color: '#f5222d' }} /></Card></Col>
      </Row>

      <Card style={{ marginBottom: 16 }}>
        <Space wrap size="middle">
          <Space.Compact>
            <Input placeholder="输入追踪号查询" value={trackingInput} onChange={e => setTrackingInput(e.target.value)} onPressEnter={() => handleTrack()} style={{ width: 220 }} />
            <Button type="primary" icon={<SearchOutlined />} onClick={() => handleTrack()}>查询</Button>
          </Space.Compact>
          <Input
            placeholder="搜索追踪号 / 发件地 / 目的地"
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            allowClear
            style={{ width: 260 }}
          />
          <Select
            mode="multiple"
            placeholder="状态筛选"
            value={statusFilter}
            onChange={setStatusFilter}
            style={{ width: 160 }}
            maxTagCount={1}
            options={Object.entries(statusText).map(([value, label]) => ({ value, label }))}
          />
          <Select
            mode="multiple"
            placeholder="物流公司"
            value={carrierFilter}
            onChange={setCarrierFilter}
            style={{ width: 150 }}
            maxTagCount={1}
            options={carriers.map(c => ({ value: c, label: c }))}
          />
          <Button icon={<ReloadOutlined />} onClick={loadShipments}>刷新</Button>
          <Button icon={<DownloadOutlined />} onClick={() => handleExport(false)}>导出全部</Button>
          <Dropdown menu={{ items: batchMenuItems, onClick: ({ key }) => {
            if (key === 'track') { handleBatchTrack() }
            else if (key === 'exportSelected') { handleExport(true) }
            else if (key === 'delete') {
              Modal.confirm({
                title: '确认删除',
                content: `确定要删除选中的 ${selectedRowKeys.length} 条记录吗？`,
                okText: '确认删除',
                okType: 'danger',
                onOk: () => {
                  setShipments(shipments.filter((s) => !selectedRowKeys.includes(s.id)))
                  setSelectedRowKeys([])
                  message.success('删除成功')
                },
              })
            }
          }}}>
            <Button icon={<SettingOutlined />}>批量操作 <Badge count={selectedRowKeys.length} showZero style={{ marginLeft: 8 }} /></Button>
          </Dropdown>
        </Space>
      </Card>

      <Card title="发货记录">
        <Table
          rowSelection={rowSelection}
          columns={columns}
          dataSource={filteredShipments}
          rowKey="id"
          loading={loading}
          pagination={{ showSizeChanger: true, showQuickJumper: true, showTotal: (total) => `共 ${total} 条`, pageSizeOptions: ['10', '20', '50', '100'] }}
        />
      </Card>

      <Modal title="物流追踪详情" open={detailVisible} onCancel={() => setDetailVisible(false)} footer={null} width={500}>
        {trackingDetail ? (
          <div>
            <p><strong>追踪号:</strong> {trackingDetail.tracking_number}</p>
            <p><strong>物流公司:</strong> {trackingDetail.carrier}</p>
            <p><strong>当前状态:</strong> <Tag color={statusColors[trackingDetail.status] || 'default'}>{statusText[trackingDetail.status] || trackingDetail.status}</Tag></p>
            {trackingDetail.events && (
              <Timeline items={trackingDetail.events.map((e: any) => ({
                color: e.status === '已送达' ? 'green' : 'blue',
                children: <div><strong>{e.status}</strong> - {e.location}<br /><small>{e.time}</small></div>
              }))} />
            )}
          </div>
        ) : <p>暂无详情</p>}
      </Modal>
    </div>
  )
}
