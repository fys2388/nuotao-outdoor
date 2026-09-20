import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Descriptions,
  Divider,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  PlusOutlined,
  ReloadOutlined,
  SendOutlined,
  TagsOutlined,
} from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'
import { api, ApiError } from '../api/client'

const { Title, Text, Paragraph } = Typography

interface PriceBook {
  id: string
  code: string
  name: string
  currency: string
  status: string
  is_default: boolean
  notes: string | null
  created_at: string
  updated_at: string
}

interface PriceVersion {
  id: string
  price_book_id: string
  version_number: number
  status: string
  effective_from: string
  effective_to: string | null
  submitted_by: string | null
  submitted_at: string | null
  approved_by: string | null
  approved_at: string | null
  rejection_reason: string | null
  created_by: string
  notes: string | null
  tier_count: number
  created_at: string
  updated_at: string
}

interface PriceTier {
  id: string
  price_version_id: string
  product_id: string
  product_name: string
  product_sku: string
  tier: string | null
  agent_id: string | null
  agent_company: string | null
  min_quantity: number
  max_quantity: number | null
  unit_price: number
  currency: string
  is_active: boolean
  created_at: string
  updated_at: string
}

interface PriceVersionDetail extends PriceVersion {
  tiers: PriceTier[]
}

interface ProductRecord {
  id: string
  sku: string
  name: string
}

interface AgentRecord {
  id: string
  company_name: string
  agent_number: string
  tier: string
}

interface PricePreview {
  price_book_id: string
  price_book_version_id: string
  price_tier_id: string
  version_number: number
  source: string
  unit_price: number
  currency: string
  min_quantity: number
  max_quantity: number | null
}

const tierOptions = [
  { value: 'bronze', label: 'Bronze' },
  { value: 'silver', label: 'Silver' },
  { value: 'gold', label: 'Gold' },
  { value: 'platinum', label: 'Platinum' },
]

const versionStatus: Record<string, { color: string; label: string }> = {
  draft: { color: 'default', label: '草稿' },
  pending_approval: { color: 'orange', label: '待审批' },
  active: { color: 'green', label: '已发布' },
  rejected: { color: 'red', label: '已驳回' },
  superseded: { color: 'blue', label: '历史版本' },
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  return error instanceof Error ? error.message : '未知错误'
}

function emptyText(label: string) {
  return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={label} />
}

function quantityRange(tier: PriceTier): string {
  return tier.max_quantity == null
    ? `${tier.min_quantity}+`
    : `${tier.min_quantity}-${tier.max_quantity - 1}`
}

export default function B2BPricingPage() {
  const [books, setBooks] = useState<PriceBook[]>([])
  const [versions, setVersions] = useState<PriceVersion[]>([])
  const [selectedBookId, setSelectedBookId] = useState<string>()
  const [selectedVersionId, setSelectedVersionId] = useState<string>()
  const [versionDetail, setVersionDetail] = useState<PriceVersionDetail | null>(null)
  const [products, setProducts] = useState<ProductRecord[]>([])
  const [agents, setAgents] = useState<AgentRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const [bookModalOpen, setBookModalOpen] = useState(false)
  const [versionModalOpen, setVersionModalOpen] = useState(false)
  const [tierModalOpen, setTierModalOpen] = useState(false)
  const [editingTier, setEditingTier] = useState<PriceTier | null>(null)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [preview, setPreview] = useState<PricePreview | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)

  const [bookForm] = Form.useForm()
  const [versionForm] = Form.useForm()
  const [tierForm] = Form.useForm()
  const [previewForm] = Form.useForm()

  const selectedBook = useMemo(
    () => books.find((book) => book.id === selectedBookId) || null,
    [books, selectedBookId],
  )
  const editable = versionDetail
    ? ['draft', 'rejected'].includes(versionDetail.status)
    : false

  const loadVersionDetail = useCallback(async (versionId: string) => {
    const detail = (await api.getB2BPriceVersion(versionId)) as PriceVersionDetail
    setVersionDetail(detail)
  }, [])

  const loadVersions = useCallback(
    async (bookId: string, preferredVersionId?: string) => {
      const rows = (await api.getB2BPriceVersions(bookId)) as PriceVersion[]
      setVersions(rows)
      const selected =
        rows.find((row) => row.id === preferredVersionId) ||
        rows.find((row) => row.status === 'active') ||
        rows[0]
      if (selected) {
        setSelectedVersionId(selected.id)
        await loadVersionDetail(selected.id)
      } else {
        setSelectedVersionId(undefined)
        setVersionDetail(null)
      }
    },
    [loadVersionDetail],
  )

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [bookResponse, productResponse, agentResponse] = await Promise.all([
        api.getB2BPriceBooks() as Promise<{ items: PriceBook[] }>,
        api.getProducts(500) as Promise<ProductRecord[]>,
        api.getB2BAgents() as Promise<{ items: AgentRecord[] }>,
      ])
      const nextBooks = bookResponse.items || []
      setBooks(nextBooks)
      setProducts(productResponse || [])
      setAgents(agentResponse.items || [])
      const book =
        nextBooks.find((row) => row.id === selectedBookId) ||
        nextBooks.find((row) => row.is_default) ||
        nextBooks[0]
      if (book) {
        setSelectedBookId(book.id)
        await loadVersions(book.id, selectedVersionId)
      } else {
        setSelectedBookId(undefined)
        setVersions([])
        setVersionDetail(null)
      }
    } catch (loadError) {
      setError(errorMessage(loadError))
      setBooks([])
      setVersions([])
      setVersionDetail(null)
    } finally {
      setLoading(false)
    }
  }, [loadVersions, selectedBookId, selectedVersionId])

  useEffect(() => {
    void load()
    // Selection changes are handled directly by their controls.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const selectBook = async (bookId: string) => {
    setSelectedBookId(bookId)
    setSelectedVersionId(undefined)
    setVersionDetail(null)
    setLoading(true)
    try {
      await loadVersions(bookId)
    } catch (loadError) {
      setError(errorMessage(loadError))
    } finally {
      setLoading(false)
    }
  }

  const selectVersion = async (versionId: string) => {
    setSelectedVersionId(versionId)
    setLoading(true)
    try {
      await loadVersionDetail(versionId)
    } catch (loadError) {
      setError(errorMessage(loadError))
    } finally {
      setLoading(false)
    }
  }

  const createBook = async () => {
    try {
      const values = await bookForm.validateFields()
      setSaving(true)
      await api.createB2BPriceBook(values)
      message.success('价格簿已创建')
      setBookModalOpen(false)
      bookForm.resetFields()
      await load()
    } catch (saveError) {
      if (saveError instanceof Error && 'errorFields' in saveError) return
      message.error(`创建失败：${errorMessage(saveError)}`)
    } finally {
      setSaving(false)
    }
  }

  const createVersion = async () => {
    if (!selectedBookId) return
    try {
      const values = await versionForm.validateFields()
      setSaving(true)
      const created = (await api.createB2BPriceVersion(selectedBookId, {
        effective_from: (values.effective_from as Dayjs).format('YYYY-MM-DD'),
        effective_to: values.effective_to
          ? (values.effective_to as Dayjs).format('YYYY-MM-DD')
          : null,
        source_version_id: values.source_version_id || null,
        notes: values.notes || null,
      })) as PriceVersionDetail
      message.success(`价格版本 v${created.version_number} 已创建`)
      setVersionModalOpen(false)
      versionForm.resetFields()
      await loadVersions(selectedBookId, created.id)
    } catch (saveError) {
      if (saveError instanceof Error && 'errorFields' in saveError) return
      message.error(`创建失败：${errorMessage(saveError)}`)
    } finally {
      setSaving(false)
    }
  }

  const openCreateTier = () => {
    setEditingTier(null)
    tierForm.resetFields()
    tierForm.setFieldsValue({
      scope_type: 'tier',
      tier: 'bronze',
      min_quantity: 1,
      currency: selectedBook?.currency || 'USD',
      is_active: true,
    })
    setTierModalOpen(true)
  }

  const openEditTier = (tier: PriceTier) => {
    setEditingTier(tier)
    tierForm.setFieldsValue({
      product_id: tier.product_id,
      scope_type: tier.agent_id ? 'agent' : 'tier',
      tier: tier.tier || undefined,
      agent_id: tier.agent_id || undefined,
      min_quantity: tier.min_quantity,
      max_quantity: tier.max_quantity,
      unit_price: tier.unit_price,
      currency: tier.currency,
      is_active: tier.is_active,
    })
    setTierModalOpen(true)
  }

  const saveTier = async () => {
    if (!versionDetail) return
    try {
      const values = await tierForm.validateFields()
      setSaving(true)
      const payload = {
        product_id: values.product_id,
        tier: values.scope_type === 'tier' ? values.tier : null,
        agent_id: values.scope_type === 'agent' ? values.agent_id : null,
        min_quantity: values.min_quantity,
        max_quantity: values.max_quantity ?? null,
        unit_price: values.unit_price,
        currency: values.currency,
        is_active: values.is_active,
      }
      if (editingTier) {
        await api.updateB2BPriceTier(editingTier.id, {
          min_quantity: payload.min_quantity,
          max_quantity: payload.max_quantity,
          unit_price: payload.unit_price,
          is_active: payload.is_active,
        })
      } else {
        await api.createB2BPriceTier(versionDetail.id, payload)
      }
      message.success(editingTier ? '阶梯价已更新' : '阶梯价已创建')
      setTierModalOpen(false)
      await loadVersionDetail(versionDetail.id)
      await loadVersions(selectedBookId!, versionDetail.id)
    } catch (saveError) {
      if (saveError instanceof Error && 'errorFields' in saveError) return
      message.error(`保存失败：${errorMessage(saveError)}`)
    } finally {
      setSaving(false)
    }
  }

  const runVersionAction = async (
    action: 'submit' | 'approve' | 'reject',
    version: PriceVersion,
  ) => {
    try {
      setSaving(true)
      if (action === 'submit') await api.submitB2BPriceVersion(version.id)
      if (action === 'approve') await api.approveB2BPriceVersion(version.id)
      if (action === 'reject') {
        const reason = window.prompt('请输入驳回原因')
        if (!reason?.trim()) return
        await api.rejectB2BPriceVersion(version.id, reason.trim())
      }
      message.success(action === 'submit' ? '已提交审批' : action === 'approve' ? '价格版本已发布' : '价格版本已驳回')
      await loadVersions(selectedBookId!, version.id)
    } catch (actionError) {
      message.error(`操作失败：${errorMessage(actionError)}`)
    } finally {
      setSaving(false)
    }
  }

  const previewPrice = async () => {
    try {
      const values = await previewForm.validateFields()
      setSaving(true)
      setPreviewError(null)
      const result = (await api.previewB2BPrice(
        values.product_id,
        values.agent_id,
        values.quantity,
        values.as_of ? (values.as_of as Dayjs).format('YYYY-MM-DD') : undefined,
      )) as PricePreview
      setPreview(result)
      setPreviewOpen(true)
    } catch (previewFailure) {
      if (previewFailure instanceof Error && 'errorFields' in previewFailure) return
      setPreview(null)
      setPreviewError(errorMessage(previewFailure))
      setPreviewOpen(true)
    } finally {
      setSaving(false)
    }
  }

  const tierColumns: ColumnsType<PriceTier> = [
    {
      title: '商品',
      key: 'product',
      render: (_, row) => (
        <div className="primary-cell">
          <strong>{row.product_name || row.product_id}</strong>
          <span>{row.product_sku || row.product_id}</span>
        </div>
      ),
    },
    {
      title: '适用对象',
      key: 'scope',
      width: 160,
      render: (_, row) =>
        row.agent_id ? (
          <div className="primary-cell">
            <Tag color="blue">客户专属</Tag>
            <span>{row.agent_company || row.agent_id}</span>
          </div>
        ) : (
          <Tag color="gold">{(row.tier || '-').toUpperCase()}</Tag>
        ),
    },
    {
      title: '数量区间',
      key: 'quantity',
      width: 120,
      render: (_, row) => quantityRange(row),
    },
    {
      title: '单价',
      dataIndex: 'unit_price',
      width: 130,
      align: 'right',
      render: (value: number, row) => `${row.currency} ${Number(value).toFixed(2)}`,
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      width: 90,
      render: (value: boolean) => (
        <Tag color={value ? 'green' : 'default'}>{value ? '启用' : '停用'}</Tag>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 140,
      render: (_, row) =>
        editable ? (
          <Space size="small">
            <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEditTier(row)}>
              编辑
            </Button>
            <Popconfirm
              title="删除该阶梯价？"
              onConfirm={async () => {
                try {
                  await api.deleteB2BPriceTier(row.id)
                  message.success('阶梯价已删除')
                  await loadVersionDetail(versionDetail!.id)
                } catch (deleteError) {
                  message.error(`删除失败：${errorMessage(deleteError)}`)
                }
              }}
            >
              <Button type="link" danger size="small" icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
          </Space>
        ) : (
          <Text type="secondary">已发布只读</Text>
        ),
    },
  ]

  return (
    <div className="resource-page">
      <div className="page-heading">
        <div>
          <div className="page-kicker">B2B PRICE CONTROL</div>
          <Title level={2}>商品目录与阶梯价</Title>
          <Paragraph>
            价格按草稿、审批、发布和版本管理。订单只读取已发布价格，并保存成交价格版本快照。
          </Paragraph>
        </div>
        <Space wrap>
          <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
            刷新
          </Button>
          <Button icon={<PlusOutlined />} onClick={() => setBookModalOpen(true)}>
            新建价格簿
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            disabled={!selectedBookId}
            onClick={() => {
              versionForm.setFieldsValue({
                effective_from: dayjs(),
                source_version_id: versions.find((row) => row.status === 'active')?.id,
              })
              setVersionModalOpen(true)
            }}
          >
            新建版本
          </Button>
        </Space>
      </div>

      {error && (
        <Alert
          className="page-alert"
          type="error"
          showIcon
          title="价格数据加载失败"
          description={error}
        />
      )}

      <Row gutter={[14, 14]} className="resource-metrics">
        <Col xs={12} lg={6}>
          <Card variant="borderless">
            <Statistic title="价格簿" value={books.length} prefix={<TagsOutlined />} />
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card variant="borderless">
            <Statistic title="版本" value={versions.length} />
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card variant="borderless">
            <Statistic
              title="已发布阶梯价"
              value={versionDetail?.status === 'active' ? versionDetail.tiers.length : 0}
              styles={{ content: { color: '#2f8b64' } }}
            />
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card variant="borderless">
            <Statistic
              title="当前版本"
              value={versionDetail ? `v${versionDetail.version_number}` : '-'}
              prefix={<CopyOutlined />}
            />
          </Card>
        </Col>
      </Row>

      <Card variant="borderless" className="resource-panel">
        <div className="resource-toolbar">
          <Space wrap>
            <Select
              style={{ minWidth: 220 }}
              value={selectedBookId}
              onChange={(value) => void selectBook(value)}
              options={books.map((book) => ({
                value: book.id,
                label: `${book.name} · ${book.currency}${book.is_default ? ' · 默认' : ''}`,
              }))}
              placeholder="选择价格簿"
            />
            <Select
              style={{ minWidth: 220 }}
              value={selectedVersionId}
              onChange={(value) => void selectVersion(value)}
              options={versions.map((version) => ({
                value: version.id,
                label: `v${version.version_number} · ${versionStatus[version.status]?.label || version.status}`,
              }))}
              placeholder="选择版本"
            />
          </Space>
          <Button
            icon={<EyeOutlined />}
            disabled={!products.length || !agents.length}
            onClick={() => {
              previewForm.resetFields()
              previewForm.setFieldsValue({ quantity: 100, as_of: dayjs() })
              setPreviewOpen(true)
              setPreview(null)
              setPreviewError(null)
            }}
          >
            价格试算
          </Button>
        </div>

        {versionDetail ? (
          <>
            <Descriptions bordered size="small" column={{ xs: 1, md: 3 }}>
              <Descriptions.Item label="版本">
                v{versionDetail.version_number}
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={versionStatus[versionDetail.status]?.color}>
                  {versionStatus[versionDetail.status]?.label || versionDetail.status}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="币种">
                {selectedBook?.currency || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="生效期">
                {versionDetail.effective_from} 至 {versionDetail.effective_to || '长期'}
              </Descriptions.Item>
              <Descriptions.Item label="创建人">
                {versionDetail.created_by}
              </Descriptions.Item>
              <Descriptions.Item label="审批人">
                {versionDetail.approved_by || '-'}
              </Descriptions.Item>
            </Descriptions>
            <Divider />
            <div className="resource-toolbar">
              <Space wrap>
                {editable && (
                  <Button type="primary" icon={<PlusOutlined />} onClick={openCreateTier}>
                    添加阶梯价
                  </Button>
                )}
                {['draft', 'rejected'].includes(versionDetail.status) && (
                  <Button
                    icon={<SendOutlined />}
                    loading={saving}
                    disabled={versionDetail.tiers.length === 0}
                    onClick={() => void runVersionAction('submit', versionDetail)}
                  >
                    提交审批
                  </Button>
                )}
                {versionDetail.status === 'pending_approval' && (
                  <>
                    <Button
                      type="primary"
                      icon={<CheckCircleOutlined />}
                      loading={saving}
                      onClick={() => void runVersionAction('approve', versionDetail)}
                    >
                      审批发布
                    </Button>
                    <Button
                      danger
                      icon={<CloseCircleOutlined />}
                      loading={saving}
                      onClick={() => void runVersionAction('reject', versionDetail)}
                    >
                      驳回
                    </Button>
                  </>
                )}
              </Space>
              <Text type="secondary">
                {editable ? '当前版本可编辑' : '已发布或待审批版本只读'}
              </Text>
            </div>
            {versionDetail.rejection_reason && (
              <Alert
                className="page-alert"
                type="error"
                showIcon
                title="审批驳回"
                description={versionDetail.rejection_reason}
              />
            )}
            <Table
              rowKey="id"
              loading={loading}
              columns={tierColumns}
              dataSource={versionDetail.tiers}
              scroll={{ x: 900 }}
              pagination={{ pageSize: 20, showSizeChanger: true }}
              locale={{ emptyText: emptyText('当前版本还没有阶梯价') }}
            />
          </>
        ) : (
          emptyText('请选择或创建价格簿和价格版本')
        )}
      </Card>

      <Modal
        title="新建价格簿"
        open={bookModalOpen}
        onCancel={() => setBookModalOpen(false)}
        onOk={() => void createBook()}
        confirmLoading={saving}
        destroyOnHidden
      >
        <Form form={bookForm} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="code" label="编码" rules={[{ required: true }]}>
                <Input placeholder="DEFAULT / US / EU" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="currency" label="币种" rules={[{ required: true }]}>
                <Input placeholder="USD" maxLength={8} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input placeholder="默认 B2B 价格簿" />
          </Form.Item>
          <Form.Item name="is_default" label="设为默认价格簿" valuePropName="checked">
            <Select
              options={[
                { value: true, label: '是，订单默认使用此价格簿' },
                { value: false, label: '否' },
              ]}
            />
          </Form.Item>
          <Form.Item name="notes" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="新建价格版本"
        open={versionModalOpen}
        onCancel={() => setVersionModalOpen(false)}
        onOk={() => void createVersion()}
        confirmLoading={saving}
        destroyOnHidden
      >
        <Form form={versionForm} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="effective_from" label="生效日期" rules={[{ required: true }]}>
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="effective_to" label="失效日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="source_version_id" label="复制已有版本">
            <Select
              allowClear
              placeholder="不复制则创建空版本"
              options={versions.map((version) => ({
                value: version.id,
                label: `v${version.version_number} · ${versionStatus[version.status]?.label || version.status}`,
              }))}
            />
          </Form.Item>
          <Form.Item name="notes" label="版本说明">
            <Input.TextArea rows={3} placeholder="说明调价原因或适用市场" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={editingTier ? '编辑阶梯价' : '添加阶梯价'}
        open={tierModalOpen}
        onCancel={() => setTierModalOpen(false)}
        onOk={() => void saveTier()}
        confirmLoading={saving}
        width={680}
        destroyOnHidden
      >
        <Form form={tierForm} layout="vertical">
          <Form.Item name="product_id" label="商品" rules={[{ required: true }]}>
            <Select
              showSearch
              disabled={Boolean(editingTier)}
              optionFilterProp="label"
              options={products.map((product) => ({
                value: product.id,
                label: `${product.sku} · ${product.name}`,
              }))}
            />
          </Form.Item>
          <Form.Item name="scope_type" label="适用对象" rules={[{ required: true }]}>
            <Select
              disabled={Boolean(editingTier)}
              options={[
                { value: 'tier', label: '客户等级价' },
                { value: 'agent', label: '客户专属价' },
              ]}
            />
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(previous, current) => previous.scope_type !== current.scope_type}>
            {({ getFieldValue }) =>
              getFieldValue('scope_type') === 'agent' ? (
                <Form.Item name="agent_id" label="客户/代理商" rules={[{ required: true }]}>
                  <Select
                    showSearch
                    disabled={Boolean(editingTier)}
                    optionFilterProp="label"
                    options={agents.map((agent) => ({
                      value: agent.id,
                      label: `${agent.agent_number} · ${agent.company_name}`,
                    }))}
                  />
                </Form.Item>
              ) : (
                <Form.Item name="tier" label="客户等级" rules={[{ required: true }]}>
                  <Select disabled={Boolean(editingTier)} options={tierOptions} />
                </Form.Item>
              )
            }
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="min_quantity" label="最小数量（含）" rules={[{ required: true }]}>
                <InputNumber min={1} precision={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="max_quantity" label="最大数量（不含）">
                <InputNumber min={2} precision={0} style={{ width: '100%' }} placeholder="留空表示无上限" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="unit_price" label="单价" rules={[{ required: true }]}>
                <InputNumber min={0.01} precision={2} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="currency" label="币种" rules={[{ required: true }]}>
                <Input disabled />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="is_active" label="启用" valuePropName="checked">
            <Select
              options={[
                { value: true, label: '启用' },
                { value: false, label: '停用' },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title="B2B 成交价试算"
        size={560}
        open={previewOpen}
        onClose={() => setPreviewOpen(false)}
      >
        <Form form={previewForm} layout="vertical">
          <Form.Item name="product_id" label="商品" rules={[{ required: true }]}>
            <Select
              showSearch
              optionFilterProp="label"
              options={products.map((product) => ({
                value: product.id,
                label: `${product.sku} · ${product.name}`,
              }))}
            />
          </Form.Item>
          <Form.Item name="agent_id" label="客户/代理商" rules={[{ required: true }]}>
            <Select
              showSearch
              optionFilterProp="label"
              options={agents.map((agent) => ({
                value: agent.id,
                label: `${agent.agent_number} · ${agent.company_name} · ${agent.tier}`,
              }))}
            />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="quantity" label="购买数量" rules={[{ required: true }]}>
                <InputNumber min={1} precision={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="as_of" label="价格日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Button type="primary" block loading={saving} onClick={() => void previewPrice()}>
            解析成交价
          </Button>
        </Form>
        <Divider />
        {previewError && <Alert type="error" showIcon title="没有可用价格" description={previewError} />}
        {preview && (
          <Descriptions bordered size="small" column={1}>
            <Descriptions.Item label="成交单价">
              {preview.currency} {Number(preview.unit_price).toFixed(2)}
            </Descriptions.Item>
            <Descriptions.Item label="价格来源">{preview.source}</Descriptions.Item>
            <Descriptions.Item label="版本">v{preview.version_number}</Descriptions.Item>
            <Descriptions.Item label="数量区间">
              {quantityRange({
                ...preview,
                id: '',
                price_version_id: '',
                product_id: '',
                product_name: '',
                product_sku: '',
                tier: null,
                agent_id: null,
                agent_company: null,
                is_active: true,
                created_at: '',
                updated_at: '',
              })}
            </Descriptions.Item>
            <Descriptions.Item label="价格版本 ID">{preview.price_book_version_id}</Descriptions.Item>
            <Descriptions.Item label="阶梯价 ID">{preview.price_tier_id}</Descriptions.Item>
          </Descriptions>
        )}
      </Drawer>
    </div>
  )
}
