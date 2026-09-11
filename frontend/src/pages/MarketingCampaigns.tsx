import { useState, useEffect, useMemo } from 'react'
import { Card, Table, Tag, Button, Space, Statistic, Row, Col, Modal, Form, Input, InputNumber, Select, message, Dropdown, Badge, Popconfirm, Progress } from 'antd'
import { PlusOutlined, DollarOutlined, EyeOutlined, SearchOutlined, ReloadOutlined, DownloadOutlined, SettingOutlined, ExportOutlined, PlayCircleOutlined, PauseCircleOutlined, DeleteOutlined, BarChartOutlined } from '@ant-design/icons'
import * as api from '../api/client'

interface Campaign {
  id: string
  name: string
  platform: string
  status: string
  budget: number
  spend: number
  impressions: number
  clicks: number
  conversion: number
  revenue: number
  roas: number
  created_at?: string
}

const platformColors: Record<string, string> = {
  facebook: 'blue',
  google: 'green',
  tiktok: 'pink',
  instagram: 'magenta',
  youtube: 'red',
}

const platformText: Record<string, string> = {
  facebook: 'Facebook',
  google: 'Google Ads',
  tiktok: 'TikTok',
  instagram: 'Instagram',
  youtube: 'YouTube',
}

const statusText: Record<string, string> = {
  active: '活跃',
  paused: '暂停',
  ended: '已结束',
  draft: '草稿',
}

const mockCampaigns: Campaign[] = [
  { id: '1', name: '夏季露营装备促销', platform: 'facebook', status: 'active', budget: 5000, spend: 3200, impressions: 125000, clicks: 4200, conversion: 156, revenue: 12800, roas: 4.0, created_at: '2024-06-01' },
  { id: '2', name: 'Google搜索-户外帐篷', platform: 'google', status: 'active', budget: 3000, spend: 2100, impressions: 85000, clicks: 3100, conversion: 98, revenue: 8900, roas: 4.24, created_at: '2024-06-15' },
  { id: '3', name: 'TikTok短视频-露营灯', platform: 'tiktok', status: 'paused', budget: 2000, spend: 1800, impressions: 200000, clicks: 6500, conversion: 89, revenue: 3200, roas: 1.78, created_at: '2024-07-01' },
  { id: '4', name: 'Instagram网红合作', platform: 'instagram', status: 'active', budget: 1500, spend: 1200, impressions: 45000, clicks: 1800, conversion: 67, revenue: 5600, roas: 4.67, created_at: '2024-07-10' },
  { id: '5', name: 'YouTube视频广告-背包', platform: 'youtube', status: 'ended', budget: 4000, spend: 3800, impressions: 300000, clicks: 8200, conversion: 210, revenue: 15200, roas: 4.0, created_at: '2024-05-01' },
  { id: '6', name: 'Facebook再营销-弃购挽回', platform: 'facebook', status: 'draft', budget: 1000, spend: 0, impressions: 0, clicks: 0, conversion: 0, revenue: 0, roas: 0, created_at: '2024-09-01' },
]

export default function MarketingCampaigns() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [form] = Form.useForm()
  const [searchText, setSearchText] = useState('')
  const [platformFilter, setPlatformFilter] = useState<string[]>([])
  const [statusFilter, setStatusFilter] = useState<string[]>([])
  const [roasFilter, setRoasFilter] = useState<string>('all')
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])

  useEffect(() => {
    loadCampaigns()
  }, [])

  const loadCampaigns = async () => {
    setLoading(true)
    try {
      const data = await api.getCampaigns()
      setCampaigns(Array.isArray(data) && data.length > 0 ? data : mockCampaigns)
    } catch (e) {
      setCampaigns(mockCampaigns)
    }
    setLoading(false)
  }

  const filteredCampaigns = useMemo(() => {
    return campaigns.filter((c) => {
      const matchSearch = !searchText || c.name.toLowerCase().includes(searchText.toLowerCase())
      const matchPlatform = platformFilter.length === 0 || platformFilter.includes(c.platform)
      const matchStatus = statusFilter.length === 0 || statusFilter.includes(c.status)
      const roas = c.roas || (c.spend > 0 ? c.revenue / c.spend : 0)
      const matchRoas = roasFilter === 'all' ||
        (roasFilter === 'high' && roas >= 3) ||
        (roasFilter === 'medium' && roas >= 1 && roas < 3) ||
        (roasFilter === 'low' && roas < 1)
      return matchSearch && matchPlatform && matchStatus && matchRoas
    })
  }, [campaigns, searchText, platformFilter, statusFilter, roasFilter])

  const stats = useMemo(() => {
    const totalSpend = filteredCampaigns.reduce((s, c) => s + (c.spend || 0), 0)
    const totalRevenue = filteredCampaigns.reduce((s, c) => s + (c.revenue || 0), 0)
    const totalImpressions = filteredCampaigns.reduce((s, c) => s + (c.impressions || 0), 0)
    const totalClicks = filteredCampaigns.reduce((s, c) => s + (c.clicks || 0), 0)
    const avgRoas = totalSpend > 0 ? totalRevenue / totalSpend : 0
    const ctr = totalImpressions > 0 ? (totalClicks / totalImpressions * 100) : 0
    return { totalSpend, totalRevenue, totalImpressions, totalClicks, avgRoas, ctr }
  }, [filteredCampaigns])

  const handleCreate = async () => {
    try {
      const values = await form.validateFields()
      const newCampaign: Campaign = {
        id: String(Date.now()),
        ...values,
        spend: 0, impressions: 0, clicks: 0, conversion: 0, revenue: 0, roas: 0,
        created_at: new Date().toISOString().split('T')[0],
      }
      setCampaigns([newCampaign, ...campaigns])
      message.success('营销活动创建成功')
      setModalVisible(false)
      form.resetFields()
    } catch (e) {
      message.error('创建失败')
    }
  }

  const handleBatchAction = (action: string) => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先选择营销活动')
      return
    }
    if (action === 'delete') {
      Modal.confirm({
        title: '确认删除',
        content: `确定要删除选中的 ${selectedRowKeys.length} 个营销活动吗？`,
        okText: '确认删除',
        okType: 'danger',
        onOk: () => {
          setCampaigns(campaigns.filter((c) => !selectedRowKeys.includes(c.id)))
          setSelectedRowKeys([])
          message.success('删除成功')
        },
      })
      return
    }
    const newStatus = action === 'activate' ? 'active' : 'paused'
    setCampaigns(campaigns.map((c) =>
      selectedRowKeys.includes(c.id) ? { ...c, status: newStatus } : c
    ))
    message.success(`已${action === 'activate' ? '启用' : '暂停'} ${selectedRowKeys.length} 个活动`)
  }

  const handleExport = (selectedOnly = false) => {
    const data = selectedOnly ? campaigns.filter((c) => selectedRowKeys.includes(c.id)) : filteredCampaigns
    const csv = ['ID,活动名称,平台,状态,预算,花费,曝光,点击,转化,收入,ROAS,创建时间',
      ...data.map((c) => `${c.id},${c.name},${platformText[c.platform] || c.platform},${statusText[c.status] || c.status},${c.budget},${c.spend},${c.impressions},${c.clicks},${c.conversion},${c.revenue},${(c.roas || (c.spend > 0 ? c.revenue / c.spend : 0)).toFixed(2)},${c.created_at || ''}`)
    ].join('\n')
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `campaigns_${new Date().toISOString().split('T')[0]}.csv`
    link.click()
    message.success(`已导出 ${data.length} 个营销活动`)
  }

  const columns = [
    {
      title: '活动名称', dataIndex: 'name', key: 'name',
      sorter: (a: Campaign, b: Campaign) => a.name.localeCompare(b.name),
      render: (name: string) => <div style={{ fontWeight: 500 }}>{name}</div>,
    },
    {
      title: '平台', dataIndex: 'platform', key: 'platform',
      filters: Object.entries(platformText).map(([value, label]) => ({ text: label, value })),
      onFilter: (value: any, record: Campaign) => record.platform === value,
      render: (p: string) => <Tag color={platformColors[p] || 'default'}>{platformText[p] || p}</Tag>,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      filters: Object.entries(statusText).map(([value, label]) => ({ text: label, value })),
      onFilter: (value: any, record: Campaign) => record.status === value,
      render: (s: string) => <Tag color={s === 'active' ? 'green' : s === 'paused' ? 'orange' : s === 'ended' ? 'default' : 'blue'}>{statusText[s] || s}</Tag>,
    },
    {
      title: '预算使用', key: 'budget_usage', width: 150,
      render: (_: any, record: Campaign) => {
        const percent = record.budget > 0 ? Math.min(100, (record.spend / record.budget) * 100) : 0
        return (
          <div>
            <Progress percent={Math.round(percent)} size="small" status={percent > 90 ? 'exception' : percent > 70 ? 'active' : 'normal'} />
            <div style={{ fontSize: 12, color: '#999' }}>${record.spend.toFixed(0)} / ${record.budget.toFixed(0)}</div>
          </div>
        )
      },
    },
    {
      title: '曝光', dataIndex: 'impressions', key: 'impressions',
      sorter: (a: Campaign, b: Campaign) => a.impressions - b.impressions,
      render: (v: number) => v?.toLocaleString() || 0,
    },
    {
      title: '点击', dataIndex: 'clicks', key: 'clicks',
      sorter: (a: Campaign, b: Campaign) => a.clicks - b.clicks,
      render: (v: number) => v?.toLocaleString() || 0,
    },
    {
      title: '转化', dataIndex: 'conversion', key: 'conversion',
      sorter: (a: Campaign, b: Campaign) => a.conversion - b.conversion,
    },
    {
      title: '收入', dataIndex: 'revenue', key: 'revenue',
      sorter: (a: Campaign, b: Campaign) => a.revenue - b.revenue,
      render: (v: number) => <span style={{ color: '#52c41a', fontWeight: 500 }}>${v?.toFixed(2) || 0}</span>,
    },
    {
      title: 'ROAS', key: 'roas',
      sorter: (a: Campaign, b: Campaign) => (a.roas || (a.spend > 0 ? a.revenue / a.spend : 0)) - (b.roas || (b.spend > 0 ? b.revenue / b.spend : 0)),
      render: (_: any, record: Campaign) => {
        const roas = record.roas || (record.spend > 0 ? record.revenue / record.spend : 0)
        return <Tag color={roas >= 3 ? 'green' : roas >= 1 ? 'orange' : 'red'}>{roas?.toFixed(2) || 0}</Tag>
      },
    },
    {
      title: '操作', key: 'action', width: 120,
      render: (_: any, record: Campaign) => (
        <Space size="small">
          <Button type="link" size="small" icon={<EyeOutlined />}>查看</Button>
          <Popconfirm title="确定删除该活动？" onConfirm={() => { setCampaigns(campaigns.filter(c => c.id !== record.id)); message.success('删除成功') }} okText="确定" cancelText="取消">
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>删除</Button>
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
    { key: 'activate', icon: <PlayCircleOutlined />, label: '批量启用' },
    { key: 'pause', icon: <PauseCircleOutlined />, label: '批量暂停' },
    { type: 'divider' as const },
    { key: 'exportSelected', icon: <ExportOutlined />, label: '导出选中' },
    { type: 'divider' as const },
    { key: 'delete', icon: <DeleteOutlined />, danger: true, label: '批量删除' },
  ]

  return (
    <div style={{ padding: 24 }}>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={6}><Card><Statistic title="总花费" prefix={<DollarOutlined />} value={stats.totalSpend} precision={2} /></Card></Col>
        <Col xs={12} sm={6}><Card><Statistic title="总收入" value={stats.totalRevenue} precision={2} prefix="$" valueStyle={{ color: '#52c41a' }} /></Card></Col>
        <Col xs={12} sm={6}><Card><Statistic title="总曝光" value={stats.totalImpressions} /></Card></Col>
        <Col xs={12} sm={6}><Card><Statistic title="平均 ROAS" value={stats.avgRoas} precision={2} valueStyle={{ color: stats.avgRoas >= 3 ? '#3f8600' : '#cf1322' }} suffix={<span style={{ fontSize: 14, color: '#999' }}> CTR {stats.ctr.toFixed(2)}%</span>} /></Card></Col>
      </Row>

      <Card style={{ marginBottom: 16 }}>
        <Space wrap size="middle">
          <Input
            placeholder="搜索活动名称"
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            allowClear
            style={{ width: 220 }}
          />
          <Select
            mode="multiple"
            placeholder="平台筛选"
            value={platformFilter}
            onChange={setPlatformFilter}
            style={{ width: 150 }}
            maxTagCount={1}
            options={Object.entries(platformText).map(([value, label]) => ({ value, label }))}
          />
          <Select
            mode="multiple"
            placeholder="状态筛选"
            value={statusFilter}
            onChange={setStatusFilter}
            style={{ width: 140 }}
            maxTagCount={1}
            options={Object.entries(statusText).map(([value, label]) => ({ value, label }))}
          />
          <Select
            placeholder="ROAS筛选"
            value={roasFilter}
            onChange={setRoasFilter}
            style={{ width: 140 }}
            options={[
              { value: 'all', label: '全部ROAS' },
              { value: 'high', label: '高ROAS(≥3)' },
              { value: 'medium', label: '中ROAS(1-3)' },
              { value: 'low', label: '低ROAS(<1)' },
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={loadCampaigns}>刷新</Button>
          <Button icon={<DownloadOutlined />} onClick={() => handleExport(false)}>导出全部</Button>
          <Dropdown menu={{ items: batchMenuItems, onClick: ({ key }) => {
            if (key === 'exportSelected') { handleExport(true) }
            else { handleBatchAction(key) }
          }}}>
            <Button icon={<SettingOutlined />}>批量操作 <Badge count={selectedRowKeys.length} showZero style={{ marginLeft: 8 }} /></Button>
          </Dropdown>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalVisible(true)}>新建活动</Button>
        </Space>
      </Card>

      <Card title="营销活动列表">
        <Table
          rowSelection={rowSelection}
          columns={columns}
          dataSource={filteredCampaigns}
          rowKey="id"
          loading={loading}
          pagination={{ showSizeChanger: true, showQuickJumper: true, showTotal: (total) => `共 ${total} 条`, pageSizeOptions: ['10', '20', '50'] }}
          scroll={{ x: 1400 }}
        />
      </Card>

      <Modal title="新建营销活动" open={modalVisible} onOk={handleCreate} onCancel={() => setModalVisible(false)} width={600} okText="创建" cancelText="取消">
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="活动名称" rules={[{ required: true }]}><Input placeholder="如：夏季促销活动" /></Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="platform" label="平台" rules={[{ required: true }]}>
                <Select options={Object.entries(platformText).map(([value, label]) => ({ value, label }))} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="status" label="状态" initialValue="draft">
                <Select options={Object.entries(statusText).map(([value, label]) => ({ value, label }))} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="budget" label="预算 ($)" rules={[{ required: true }]}><InputNumber style={{ width: '100%' }} min={0} placeholder="请输入预算金额" /></Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
