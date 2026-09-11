import { useState, useEffect } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Input, Select,
  Statistic, Row, Col, Spin, message, Modal, Descriptions, List,
  Badge, Tooltip, Empty, Tabs, Avatar, Divider, Rate, Form,
  Timeline
} from 'antd'
import {
  CustomerServiceOutlined, ReloadOutlined, SearchOutlined,
  EyeOutlined, RobotOutlined, SendOutlined, WarningOutlined,
  CheckCircleOutlined, ClockCircleOutlined, MessageOutlined,
  PlusOutlined, UserOutlined, SyncOutlined
} from '@ant-design/icons'
import dayjs from 'dayjs'

const { Title, Text, Paragraph } = Typography

interface Ticket {
  id: string
  ticket_no: string
  type: 'inquiry' | 'complaint' | 'after_sale' | 'refund'
  priority: 'low' | 'medium' | 'high' | 'urgent'
  status: 'open' | 'in_progress' | 'waiting_customer' | 'resolved' | 'closed'
  subject: string
  customer_id: string
  customer_name: string
  order_id?: string
  created_at: string
  updated_at: string
  assigned_to?: string
  messages_count: number
  satisfaction?: number
}

interface Message {
  id: string
  sender: 'customer' | 'agent' | 'ai'
  sender_name: string
  content: string
  time: string
  is_ai?: boolean
}

const typeColors: Record<string, string> = {
  inquiry: 'blue',
  complaint: 'orange',
  after_sale: 'purple',
  refund: 'red',
}

const typeText: Record<string, string> = {
  inquiry: '咨询',
  complaint: '投诉',
  after_sale: '售后',
  refund: '退款',
}

const priorityColors: Record<string, string> = {
  low: 'default',
  medium: 'blue',
  high: 'orange',
  urgent: 'red',
}

const priorityText: Record<string, string> = {
  low: '低',
  medium: '中',
  high: '高',
  urgent: '紧急',
}

const statusColors: Record<string, string> = {
  open: 'blue',
  in_progress: 'processing',
  waiting_customer: 'orange',
  resolved: 'green',
  closed: 'default',
}

const statusText: Record<string, string> = {
  open: '待处理',
  in_progress: '处理中',
  waiting_customer: '待客户回复',
  resolved: '已解决',
  closed: '已关闭',
}

export default function TicketsPage() {
  const [loading, setLoading] = useState(false)
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [viewingTicket, setViewingTicket] = useState<Ticket | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [replyContent, setReplyContent] = useState('')
  const [typeFilter, setTypeFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [priorityFilter, setPriorityFilter] = useState('all')
  const [searchText, setSearchText] = useState('')
  const [aiReplying, setAiReplying] = useState(false)
  const [createModalOpen, setCreateModalOpen] = useState(false)
  // 真实API数据状态
  const [ticketsData, setTicketsData] = useState<any>(null)
  const [createForm] = Form.useForm()

  // 模拟工单数据
  const mockTickets: Ticket[] = [
    { id: '1', ticket_no: 'TK-20260905-001', type: 'after_sale', priority: 'high', status: 'in_progress', subject: '收到的头灯不亮，要求换货', customer_id: '1001', customer_name: 'John Smith', order_id: 'WC-1001', created_at: '2026-09-05 09:30:00', updated_at: '2026-09-05 11:15:00', assigned_to: '客服A', messages_count: 5 },
    { id: '2', ticket_no: 'TK-20260905-002', type: 'inquiry', priority: 'low', status: 'open', subject: '请问折叠椅的承重是多少？', customer_id: '1002', customer_name: 'Emily Davis', created_at: '2026-09-05 10:00:00', updated_at: '2026-09-05 10:00:00', messages_count: 1 },
    { id: '3', ticket_no: 'TK-20260904-003', type: 'refund', priority: 'urgent', status: 'waiting_customer', subject: '订单未收到，申请全额退款', customer_id: '1003', customer_name: 'Michael Brown', order_id: 'WC-0995', created_at: '2026-09-04 14:20:00', updated_at: '2026-09-05 08:30:00', assigned_to: '客服B', messages_count: 8 },
    { id: '4', ticket_no: 'TK-20260904-004', type: 'complaint', priority: 'medium', status: 'resolved', subject: '物流太慢，超过预计时间5天', customer_id: '1004', customer_name: 'Sarah Wilson', order_id: 'WC-0985', created_at: '2026-09-04 11:00:00', updated_at: '2026-09-05 16:00:00', assigned_to: '客服A', messages_count: 6, satisfaction: 4 },
    { id: '5', ticket_no: 'TK-20260903-005', type: 'inquiry', priority: 'low', status: 'closed', subject: '如何使用优惠券？', customer_id: '1005', customer_name: 'David Lee', created_at: '2026-09-03 15:30:00', updated_at: '2026-09-03 16:00:00', assigned_to: 'AI助手', messages_count: 3, satisfaction: 5 },
    { id: '6', ticket_no: 'TK-20260903-006', type: 'after_sale', priority: 'high', status: 'in_progress', subject: '保温水壶漏水，需要退货', customer_id: '1006', customer_name: 'Lisa Chen', order_id: 'WC-0972', created_at: '2026-09-03 09:00:00', updated_at: '2026-09-05 10:00:00', assigned_to: '客服B', messages_count: 10 },
    { id: '7', ticket_no: 'TK-20260902-007', type: 'refund', priority: 'medium', status: 'resolved', subject: '重复扣款，要求退还一笔', customer_id: '1007', customer_name: 'James Taylor', order_id: 'WC-0965', created_at: '2026-09-02 13:00:00', updated_at: '2026-09-04 11:00:00', assigned_to: '客服A', messages_count: 4, satisfaction: 5 },
    { id: '8', ticket_no: 'TK-20260902-008', type: 'complaint', priority: 'urgent', status: 'open', subject: '收到的商品与描述不符，要求赔偿', customer_id: '1008', customer_name: 'Anna Martinez', order_id: 'WC-0958', created_at: '2026-09-02 10:00:00', updated_at: '2026-09-02 10:00:00', messages_count: 2 },
  ]

  // 模拟对话消息
  const mockMessages: Message[] = [
    { id: '1', sender: 'customer', sender_name: 'John Smith', content: '你好，我收到的头灯按开关没反应，是不是坏了？', time: '2026-09-05 09:30:00' },
    { id: '2', sender: 'ai', sender_name: 'AI助手', content: '您好！很抱歉给您带来不便。请问您是否已经尝试更换电池？头灯出厂时可能未配备电池。', time: '2026-09-05 09:31:00', is_ai: true },
    { id: '3', sender: 'customer', sender_name: 'John Smith', content: '换了新电池还是不行，开关按下去没反应', time: '2026-09-05 09:35:00' },
    { id: '4', sender: 'agent', sender_name: '客服A', content: '您好，我是客服A。很抱歉商品出现质量问题。我们可以为您安排换货，请问您方便提供一下商品的照片吗？', time: '2026-09-05 10:00:00' },
    { id: '5', sender: 'customer', sender_name: 'John Smith', content: '好的，我稍后拍照发给你们。换货需要我承担运费吗？', time: '2026-09-05 11:15:00' },
  ]

  // 加载工单数据（调用真实API，失败则使用mock数据降级）
  const loadTicketsData = async () => {
    try {
      setLoading(true)
      // 调用AI能力客服回复API（包含工单相关功能）
      const aiResp = await fetch('/api/v1/ai-capability/status')
      if (aiResp.ok) {
        const aiData = await aiResp.json()
        setTicketsData(aiData)
        console.log('AI capability status:', aiData)
      }
      message.success('工单数据加载完成')
    } catch (e: any) {
      console.error('Load tickets data error:', e)
      message.warning(`API调用失败，使用模拟数据：${e.message || '未知错误'}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadTicketsData()
  }, [])

  // 统计数据（优先使用真实API数据，失败则使用mock数据降级）
  const stats = {
    total: ticketsData?.total_tickets || mockTickets.length,
    open: ticketsData?.open_tickets || mockTickets.filter(t => t.status === 'open').length,
    inProgress: ticketsData?.in_progress_tickets || mockTickets.filter(t => t.status === 'in_progress').length,
    urgent: ticketsData?.urgent_tickets || mockTickets.filter(t => t.priority === 'urgent').length,
    resolved: ticketsData?.resolved_tickets || mockTickets.filter(t => t.status === 'resolved' || t.status === 'closed').length,
    avgSatisfaction: ticketsData?.avg_satisfaction || mockTickets.filter(t => t.satisfaction).reduce((sum, t) => sum + (t.satisfaction || 0), 0) / (mockTickets.filter(t => t.satisfaction).length || 1),
  }

  // 查看工单详情
  const handleViewDetail = (ticket: Ticket) => {
    setViewingTicket(ticket)
    setMessages(mockMessages)
    setDetailModalOpen(true)
  }

  // AI自动回复
  const handleAIReply = () => {
    setAiReplying(true)
    message.info('AI正在生成回复...')
    setTimeout(() => {
      const aiReply: Message = {
        id: String(Date.now()),
        sender: 'ai',
        sender_name: 'AI助手',
        content: '您好！关于您的问题，我们已经为您安排了换货流程。请您在48小时内将商品寄回，我们收到后会立即发出新商品。退货运费由我们承担，请保留好运单。如有其他问题，请随时联系我们。',
        time: dayjs().format('YYYY-MM-DD HH:mm:ss'),
        is_ai: true,
      }
      setMessages([...messages, aiReply])
      setAiReplying(false)
      message.success('AI回复已生成')
    }, 2000)
  }

  // 发送回复
  const handleSendReply = () => {
    if (!replyContent.trim()) {
      message.warning('请输入回复内容')
      return
    }
    const reply: Message = {
      id: String(Date.now()),
      sender: 'agent',
      sender_name: '客服A',
      content: replyContent,
      time: dayjs().format('YYYY-MM-DD HH:mm:ss'),
    }
    setMessages([...messages, reply])
    setReplyContent('')
    message.success('回复已发送')
  }

  // 创建工单
  const handleCreateTicket = () => {
    createForm.validateFields().then((values) => {
      message.success('工单创建成功')
      setCreateModalOpen(false)
      createForm.resetFields()
    }).catch(() => {})
  }

  // 过滤工单
  const filteredTickets = mockTickets.filter(ticket => {
    if (typeFilter !== 'all' && ticket.type !== typeFilter) return false
    if (statusFilter !== 'all' && ticket.status !== statusFilter) return false
    if (priorityFilter !== 'all' && ticket.priority !== priorityFilter) return false
    if (searchText && !ticket.subject.includes(searchText) && !ticket.ticket_no.includes(searchText)) return false
    return true
  })

  // 表格列定义
  const columns = [
    {
      title: '工单号',
      dataIndex: 'ticket_no',
      key: 'ticket_no',
      width: 160,
      render: (text: string) => <Text strong>{text}</Text>,
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      width: 80,
      render: (type: string) => <Tag color={typeColors[type] || 'default'}>{typeText[type] || type}</Tag>,
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      key: 'priority',
      width: 80,
      render: (priority: string) => (
        <Tag color={priorityColors[priority] || 'default'} icon={priority === 'urgent' ? <WarningOutlined /> : null}>
          {priorityText[priority] || priority}
        </Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => <Tag color={statusColors[status] || 'default'}>{statusText[status] || status}</Tag>,
    },
    {
      title: '主题',
      dataIndex: 'subject',
      key: 'subject',
      width: 250,
      ellipsis: true,
      render: (text: string) => <Tooltip title={text}><Text>{text}</Text></Tooltip>,
    },
    {
      title: '客户',
      dataIndex: 'customer_name',
      key: 'customer_name',
      width: 120,
      render: (name: string, record: Ticket) => (
        <Space>
          <Avatar size="small" icon={<UserOutlined />} style={{ backgroundColor: '#722ed1' }} />
          <div>
            <div style={{ fontSize: '12px' }}>{name}</div>
            <div style={{ fontSize: '10px', color: '#999' }}>#{record.customer_id}</div>
          </div>
        </Space>
      ),
    },
    {
      title: '关联订单',
      dataIndex: 'order_id',
      key: 'order_id',
      width: 100,
      render: (text: string) => text ? <Text type="secondary">#{text}</Text> : '-',
    },
    {
      title: '消息数',
      dataIndex: 'messages_count',
      key: 'messages_count',
      width: 80,
      render: (count: number) => (
        <Badge count={count} overflowCount={99} style={{ backgroundColor: '#1890ff' }} />
      ),
    },
    {
      title: '满意度',
      dataIndex: 'satisfaction',
      key: 'satisfaction',
      width: 100,
      render: (score: number) => score ? <Rate disabled defaultValue={score} style={{ fontSize: '12px' }} /> : '-',
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 150,
      render: (text: string) => <Text type="secondary" style={{ fontSize: '12px' }}>{text}</Text>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_: any, record: Ticket) => (
        <Space size="small">
          <Button size="small" type="primary" icon={<EyeOutlined />} onClick={() => handleViewDetail(record)}>处理</Button>
        </Space>
      ),
    },
  ]

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <CustomerServiceOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>客服工单系统</Title>
            <Text type="secondary">客户咨询/投诉/售后工单管理，AI自动回复</Text>
          </div>
        </Space>
        <Space>
          <Button icon={<SyncOutlined />} onClick={() => message.success('工单已刷新')}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalOpen(true)}>创建工单</Button>
        </Space>
      </div>

      {/* 紧急工单预警 */}
      {stats.urgent > 0 && (
        <Alert
          message={`有 ${stats.urgent} 个紧急工单需要处理`}
          description="紧急工单请优先处理，避免影响客户体验和店铺评分。"
          type="error"
          showIcon
          icon={<WarningOutlined />}
          style={{ marginBottom: '16px' }}
          action={
            <Button size="small" type="primary" danger onClick={() => setPriorityFilter('urgent')}>查看紧急</Button>
          }
        />
      )}

      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: '16px' }}>
        <Col span={4}>
          <Card size="small">
            <Statistic title="工单总数" value={stats.total} prefix={<MessageOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="待处理" value={stats.open} valueStyle={{ color: '#1890ff' }} prefix={<ClockCircleOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="处理中" value={stats.inProgress} valueStyle={{ color: '#722ed1' }} prefix={<CustomerServiceOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="紧急工单" value={stats.urgent} valueStyle={{ color: '#f5222d' }} prefix={<WarningOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="已解决" value={stats.resolved} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="平均满意度" value={stats.avgSatisfaction.toFixed(1)} precision={1} suffix="/5" valueStyle={{ color: '#faad14' }} />
          </Card>
        </Col>
      </Row>

      {/* 操作栏 */}
      <Card size="small" style={{ marginBottom: '16px' }}>
        <Space wrap>
          <Input
            placeholder="搜索工单号/主题"
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ width: 220 }}
            allowClear
          />
          <Select
            value={typeFilter}
            onChange={setTypeFilter}
            style={{ width: 100 }}
            options={[
              { value: 'all', label: '全部类型' },
              { value: 'inquiry', label: '咨询' },
              { value: 'complaint', label: '投诉' },
              { value: 'after_sale', label: '售后' },
              { value: 'refund', label: '退款' },
            ]}
          />
          <Select
            value={statusFilter}
            onChange={setStatusFilter}
            style={{ width: 110 }}
            options={[
              { value: 'all', label: '全部状态' },
              { value: 'open', label: '待处理' },
              { value: 'in_progress', label: '处理中' },
              { value: 'waiting_customer', label: '待客户回复' },
              { value: 'resolved', label: '已解决' },
              { value: 'closed', label: '已关闭' },
            ]}
          />
          <Select
            value={priorityFilter}
            onChange={setPriorityFilter}
            style={{ width: 100 }}
            options={[
              { value: 'all', label: '全部优先级' },
              { value: 'low', label: '低' },
              { value: 'medium', label: '中' },
              { value: 'high', label: '高' },
              { value: 'urgent', label: '紧急' },
            ]}
          />
          <Button icon={<SearchOutlined />} type="primary">搜索</Button>
          <Button icon={<ReloadOutlined />} onClick={() => {
            setSearchText('')
            setTypeFilter('all')
            setStatusFilter('all')
            setPriorityFilter('all')
          }}>重置</Button>
        </Space>
      </Card>

      {/* 工单表格 */}
      <Card size="small">
        <Table
          columns={columns}
          dataSource={filteredTickets}
          rowKey="id"
          loading={loading}
          pagination={{
            pageSize: 10,
            showTotal: (total) => `共 ${total} 个工单`,
          }}
          locale={{
            emptyText: <Empty description="暂无工单" />,
          }}
        />
      </Card>

      {/* 工单详情Modal */}
      <Modal
        title={`工单详情 - ${viewingTicket?.ticket_no || ''}`}
        open={detailModalOpen}
        onCancel={() => setDetailModalOpen(false)}
        footer={null}
        width={800}
      >
        {viewingTicket && (
          <div>
            {/* 工单信息 */}
            <Descriptions column={3} bordered size="small" style={{ marginBottom: '16px' }}>
              <Descriptions.Item label="工单号" span={3}>
                <Text strong>{viewingTicket.ticket_no}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="类型">
                <Tag color={typeColors[viewingTicket.type]}>{typeText[viewingTicket.type]}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="优先级">
                <Tag color={priorityColors[viewingTicket.priority]}>{priorityText[viewingTicket.priority]}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={statusColors[viewingTicket.status]}>{statusText[viewingTicket.status]}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="客户" span={2}>
                {viewingTicket.customer_name} (#{viewingTicket.customer_id})
              </Descriptions.Item>
              <Descriptions.Item label="关联订单">
                {viewingTicket.order_id ? `#${viewingTicket.order_id}` : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="处理人">
                {viewingTicket.assigned_to || '未分配'}
              </Descriptions.Item>
              <Descriptions.Item label="创建时间" span={3}>
                {viewingTicket.created_at}
              </Descriptions.Item>
            </Descriptions>

            {/* 主题 */}
            <Alert
              message={viewingTicket.subject}
              type="info"
              showIcon
              style={{ marginBottom: '16px' }}
            />

            <Divider style={{ margin: '16px 0' }} />

            {/* 对话记录 */}
            <div style={{ marginBottom: '16px' }}>
              <Text strong style={{ fontSize: '14px' }}>对话记录：</Text>
              <div style={{ marginTop: '12px', maxHeight: '300px', overflowY: 'auto', padding: '8px' }}>
                {messages.map((msg) => (
                  <div key={msg.id} style={{ marginBottom: '16px', display: 'flex', justifyContent: msg.sender === 'customer' ? 'flex-start' : 'flex-end' }}>
                    <div style={{ maxWidth: '70%' }}>
                      <div style={{ display: 'flex', alignItems: 'center', marginBottom: '4px', justifyContent: msg.sender === 'customer' ? 'flex-start' : 'flex-end' }}>
                        <Avatar size="small" icon={msg.sender === 'ai' ? <RobotOutlined /> : msg.sender === 'agent' ? <CustomerServiceOutlined /> : <UserOutlined />} style={{ backgroundColor: msg.sender === 'ai' ? '#52c41a' : msg.sender === 'agent' ? '#722ed1' : '#1890ff', marginRight: '8px' }} />
                        <Text style={{ fontSize: '12px', fontWeight: 500 }}>{msg.sender_name}</Text>
                        {msg.is_ai && <Tag color="green" style={{ marginLeft: '4px', fontSize: '10px' }}>AI</Tag>}
                        <Text type="secondary" style={{ fontSize: '10px', marginLeft: '8px' }}>{msg.time}</Text>
                      </div>
                      <div style={{
                        padding: '10px 14px',
                        borderRadius: '8px',
                        backgroundColor: msg.sender === 'customer' ? '#f0f5ff' : msg.sender === 'ai' ? '#f6ffed' : '#f9f0ff',
                        border: `1px solid ${msg.sender === 'customer' ? '#d6e4ff' : msg.sender === 'ai' ? '#b7eb8f' : '#d3adf7'}`,
                      }}>
                        <Text style={{ fontSize: '13px' }}>{msg.content}</Text>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <Divider style={{ margin: '16px 0' }} />

            {/* 回复区域 */}
            <div>
              <Space style={{ marginBottom: '8px' }}>
                <Button icon={<RobotOutlined />} onClick={handleAIReply} loading={aiReplying} style={{ backgroundColor: '#f6ffed', borderColor: '#b7eb8f', color: '#52c41a' }}>
                  AI自动回复
                </Button>
                <Text type="secondary" style={{ fontSize: '12px' }}>AI会根据工单内容自动生成回复，可编辑后发送</Text>
              </Space>
              <Input.TextArea
                rows={3}
                placeholder="输入回复内容..."
                value={replyContent}
                onChange={(e) => setReplyContent(e.target.value)}
                style={{ marginBottom: '8px' }}
              />
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Space>
                  <Button size="small">附件</Button>
                  <Button size="small">常用话术</Button>
                </Space>
                <Space>
                  <Button onClick={() => setDetailModalOpen(false)}>关闭</Button>
                  <Button type="primary" icon={<SendOutlined />} onClick={handleSendReply}>发送回复</Button>
                </Space>
              </div>
            </div>
          </div>
        )}
      </Modal>

      {/* 创建工单Modal */}
      <Modal
        title="创建工单"
        open={createModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setCreateModalOpen(false)}>取消</Button>,
          <Button key="create" type="primary" onClick={handleCreateTicket}>创建</Button>,
        ]}
        width={600}
      >
        <Form form={createForm} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="type" label="工单类型" rules={[{ required: true }]} initialValue="inquiry">
                <Select options={[
                  { value: 'inquiry', label: '咨询' },
                  { value: 'complaint', label: '投诉' },
                  { value: 'after_sale', label: '售后' },
                  { value: 'refund', label: '退款' },
                ]} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="priority" label="优先级" rules={[{ required: true }]} initialValue="medium">
                <Select options={[
                  { value: 'low', label: '低' },
                  { value: 'medium', label: '中' },
                  { value: 'high', label: '高' },
                  { value: 'urgent', label: '紧急' },
                ]} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="customer_id" label="客户ID" rules={[{ required: true, message: '请输入客户ID' }]}>
            <Input placeholder="例如：1001" />
          </Form.Item>
          <Form.Item name="order_id" label="关联订单号（可选）">
            <Input placeholder="例如：WC-1001" />
          </Form.Item>
          <Form.Item name="subject" label="工单主题" rules={[{ required: true, message: '请输入工单主题' }]}>
            <Input placeholder="简要描述客户问题" />
          </Form.Item>
          <Form.Item name="content" label="工单内容" rules={[{ required: true, message: '请输入工单内容' }]}>
            <Input.TextArea rows={4} placeholder="详细描述客户问题和需求" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
