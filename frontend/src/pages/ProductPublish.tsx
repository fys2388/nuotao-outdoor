import { useState, useEffect } from 'react'
import {
  Card, Tabs, Table, Button, Tag, Space, Typography, message,
  Row, Col, Statistic, Modal, Form, InputNumber, Divider, Alert, Badge,
  Descriptions, Tooltip
} from 'antd'
import {
  ShopOutlined, RocketOutlined, SyncOutlined, PlusOutlined,
  DollarOutlined, TeamOutlined, CheckCircleOutlined,
  FileTextOutlined, AuditOutlined
} from '@ant-design/icons'
import { request, api } from '../api/client'

const { Title, Text, Paragraph } = Typography

interface Product {
  id: string
  sku: string
  name: string
  description?: string
  category?: string
  brand?: string
  status: string
  woocommerce_id?: number
  stock_quantity?: number
  target_market?: string
  source?: string
  candidate_status?: string | null
  meta?: Record<string, any>
  created_at: string
  updated_at: string
}

interface WholesaleTier {
  moq: number
  price: number
  lead_days?: number
}

function getWholesaleTiers(p: Product): WholesaleTier[] {
  return p?.meta?.wholesale_tiers || []
}

// 后端返回的商品名可能含 HTML 转义（如 &amp;），展示前需还原，
// 否则会把双重转义写进 WooCommerce 标题。
function decodeHtmlEntities(value?: string): string {
  if (!value) return ''
  return value
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&apos;/g, "'")
}

// 上架前可见的零售价：优先英文本地化价格，其次 meta.price。
// 返回 null 表示缺失——定价是禁止凭感觉的关键决策，缺失必须显式暴露。
function getRetailPrice(p: Product): number | null {
  const en = p?.meta?.localizations?.en
  const raw = en?.price ?? p?.meta?.price
  const n = typeof raw === 'number' ? raw : parseFloat(String(raw ?? ''))
  return Number.isFinite(n) && n > 0 ? n : null
}

// 后端把 WooCommerce ID 写在 meta.woocommerce_id（products.py 序列化），
// 顶层没有该字段；历史上页面按顶层读取导致同步状态恒为「未同步」。
// 两处都读，兼容后端两种序列化路径。
function getWcId(p: Product): number | undefined {
  const id = p?.woocommerce_id ?? p?.meta?.woocommerce_id
  return typeof id === 'number' ? id : undefined
}

// 已批准的英文文案是推送到英文站的硬前置：后端拒绝把中文商品直接推上商城，
// 也拒绝以 0 元价格创建商品。状态机 none → generated → approved。
type CopyState = 'none' | 'generated' | 'approved'
function getCopyState(p: Product): CopyState {
  const en = p?.meta?.localizations?.en
  if (!en || typeof en !== 'object') return 'none'
  return en.status === 'approved' ? 'approved' : 'generated'
}

export default function ProductPublish() {
  const [products, setProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(false)
  const [activeTab, setActiveTab] = useState('b2c')
  const [publishingId, setPublishingId] = useState<string | null>(null)
  const [copywritingId, setCopywritingId] = useState<string | null>(null)
  const [tierModalOpen, setTierModalOpen] = useState(false)
  const [editingProduct, setEditingProduct] = useState<Product | null>(null)
  const [tiers, setTiers] = useState<WholesaleTier[]>([])
  const [form] = Form.useForm()

  const loadProducts = async () => {
    try {
      setLoading(true)
      const data = await request<any>('/products?limit=200&offset=0')
      setProducts(Array.isArray(data) ? data : [])
    } catch (e) {
      message.error('加载商品失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadProducts() }, [])

  const draftProducts = products.filter(p => p.status === 'draft')
  const activeProducts = products.filter(p => p.status === 'active')
  const pendingProducts = products.filter(p => p.status === 'pending')
  const syncedCount = products.filter(p => getWcId(p)).length

  // 推送前必须人工确认（AGENTS.md 3.1「关键动作人审」）：
  // 推送会写入外部 WooCommerce 系统，且受后端 V3.0 选品闸门约束。
  const confirmPush = (p: Product) => {
    if (getWcId(p)) return
    Modal.confirm({
      title: `推送到 WooCommerce：${decodeHtmlEntities(p.name)}`,
      content: (
        <div>
          <p>该动作会先过 V3.0 选品闸门校验，通过后在 WooCommerce 创建或更新商品。</p>
          <Alert
            type="info"
            showIcon
            message="触发一票否决的商品会被硬阻断；低分或数据缺失的商品需再次人工复核。"
          />
        </div>
      ),
      okText: '推送',
      cancelText: '取消',
      onOk: () => pushToWooCommerce(p.id),
    })
  }

  const pushToWooCommerce = async (productId: string, force = false) => {
    setPublishingId(productId)
    try {
      const data = await request<any>(
        `/products/${productId}/push-woocommerce${force ? '?force=true' : ''}`,
        { method: 'POST', timeoutMs: 120000 },
      )
      message.success(`已推送：${data?.data?.name || '商品'}`)
      loadProducts()
    } catch (e: any) {
      const status = e?.status
      if (status === 409 && !force) {
        // V3.0 闸门 needs_review：需人工复核后显式放行
        Modal.confirm({
          title: '未通过 V3.0 选品闸门，需要人工复核',
          content: (
            <div>
              <p style={{ marginBottom: 12 }}>{e?.message || '需人工复核确认后放行'}</p>
              <Alert
                type="warning"
                showIcon
                message="强制放行只针对「低分 / 数据缺失」，不会绕过一票否决硬阻断。"
              />
            </div>
          ),
          okText: '我已人工复核，强制放行',
          cancelText: '取消',
          onOk: () => pushToWooCommerce(productId, true),
        })
        return
      }
      if (status === 422) {
        // 触发一票否决：硬阻断，不提供放行入口
        Modal.error({
          title: 'V3.0 选品闸门阻断，禁止上架',
          content: e?.message || '该商品触发一票否决，请回候选库补全数据或淘汰后再试。',
        })
        return
      }
      // 其余错误（含 400 文案校验、5xx、网络）：用持久弹窗而非 toast。
      // 这类失败常发生在「我已人工复核，强制放行」确认后，Modal.confirm 已关闭，
      // toast 会在关闭瞬间消失，用户会误以为操作成功（BUG-19）。
      Modal.error({
        title: '未推送到 WooCommerce',
        content: (
          <div>
            <p style={{ marginBottom: 8, whiteSpace: 'pre-wrap' }}>
              {e?.message || '推送失败，请重试'}
            </p>
            {e?.traceId && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                追踪ID：{e.traceId}
              </Text>
            )}
          </div>
        ),
        okText: '我知道了',
      })
    } finally {
      setPublishingId(null)
    }
  }

  // 生成英文文案（LLM 调用，耗时可达数十秒）。
  // 中文商品直接上英文站不可接受，这是后端强制校验的前置条件。
  const generateCopywriting = async (p: Product) => {
    const shortName = decodeHtmlEntities(p.name).slice(0, 20)
    setCopywritingId(p.id)
    message.loading({
      content: `正在为「${shortName}」生成英文文案…（约 30-120 秒）`,
      key: 'copy',
      duration: 0,
    })
    try {
      await api.generateProductCopy(p.id)
      message.success({ content: '英文文案已生成，请审核后批准', key: 'copy' })
      await loadProducts()
    } catch (e: any) {
      message.error({ content: e?.message || '文案生成失败，请重试', key: 'copy' })
    } finally {
      setCopywritingId(null)
    }
  }

  // 审批已生成的英文文案。文案未经人工审核不得上架（AGENTS.md 3.1 关键动作人审）。
  // 弹窗内展示完整文案供运营核对，避免盲批。
  const approveCopywriting = (p: Product) => {
    const en = (p?.meta?.localizations?.en || {}) as Record<string, any>
    Modal.confirm({
      title: '批准英文文案上架',
      width: 680,
      content: (
        <div>
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            message="批准后将标记为「已审核」，商品才可推送到 WooCommerce。"
          />
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="英文标题">
              <Text strong>{decodeHtmlEntities(en.title || '（空）')}</Text>
            </Descriptions.Item>
            {en.short_description ? (
              <Descriptions.Item label="摘要">
                <Paragraph ellipsis={{ rows: 2 }} style={{ marginBottom: 0 }}>
                  {decodeHtmlEntities(en.short_description)}
                </Paragraph>
              </Descriptions.Item>
            ) : null}
            {en.bullet_points && en.bullet_points.length > 0 ? (
              <Descriptions.Item label="卖点">
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  {en.bullet_points.map((b: string, i: number) => (
                    <li key={i}>{decodeHtmlEntities(String(b))}</li>
                  ))}
                </ul>
              </Descriptions.Item>
            ) : null}
          </Descriptions>
        </div>
      ),
      okText: '我已审核，批准上架',
      cancelText: '再看一下',
      onOk: async () => {
        setCopywritingId(p.id)
        try {
          await api.approveProductLocalization(p.id, 'en')
          message.success('文案已批准，现在可以推送到 WooCommerce')
          await loadProducts()
        } catch (e: any) {
          message.error(e?.message || '批准失败，请重试')
        } finally {
          setCopywritingId(null)
        }
      },
    })
  }

  const openTierModal = (p: Product) => {
    setEditingProduct(p)
    setTiers(getWholesaleTiers(p).length > 0 ? getWholesaleTiers(p) : [{ moq: 100, price: 39, lead_days: 14 }])
    setTierModalOpen(true)
  }

  const saveTiers = async () => {
    if (!editingProduct) return
    try {
      const newMeta = { ...(editingProduct.meta || {}), wholesale_tiers: tiers }
      await request(`/products/${editingProduct.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ meta: newMeta })
      })
      message.success('批发价已保存')
      setTierModalOpen(false)
      loadProducts()
    } catch (e: any) {
      message.error(e.message || '网络错误')
    }
  }

  const b2cColumns = [
    { title: '商品', dataIndex: 'name', key: 'name', render: (v: string, r: Product) => (
      <div>
        <Text strong>{decodeHtmlEntities(v)}</Text>
        <br />
        <Text type="secondary" style={{ fontSize: 12 }}>SKU: {r.sku}</Text>
      </div>
    )},
    { title: '状态', dataIndex: 'status', key: 'status', render: (s: string) => {
      const map: Record<string, {color:string, text:string}> = {
        draft: {color:'orange', text:'草稿'},
        pending: {color:'blue', text:'待审'},
        active: {color:'green', text:'已发布'},
      }
      const m = map[s] || {color:'default', text:s}
      return <Tag color={m.color}>{m.text}</Tag>
    }},
    { title: '零售价', key: 'retail', render: (_: any, r: Product) => {
      const price = getRetailPrice(r)
      return price === null
        ? <Tag color="red">缺失</Tag>
        : <Text strong>${price.toFixed(2)}</Text>
    }},
    { title: '候选状态', dataIndex: 'candidate_status', key: 'cand', render: (v?: string) =>
      v ? <Tag>{v}</Tag> : <Tag color="orange">未进入选品</Tag>
    },
    { title: '英文文案', key: 'copy', render: (_: any, r: Product) => {
      const cs = getCopyState(r)
      if (cs === 'approved') return <Tag color="green">已批准</Tag>
      if (cs === 'generated') return <Tag color="blue">待审批</Tag>
      return <Tag color="red">缺失</Tag>
    }},
    { title: 'WC同步', key: 'wc', render: (_: any, r: Product) => {
      const id = getWcId(r)
      return id ? <Tag color="green">已同步 #{id}</Tag> : <Tag>未同步</Tag>
    }},
    { title: '操作', key: 'op', width: 220, render: (_: any, r: Product) => {
      const wcId = getWcId(r)
      const cs = getCopyState(r)
      const busy = copywritingId === r.id
      if (wcId) {
        return <Button size="small" icon={<CheckCircleOutlined />} disabled>已推送</Button>
      }
      return (
        <Space wrap size={4}>
          {cs === 'none' && (
            <Button size="small" icon={<FileTextOutlined />}
              loading={busy} onClick={() => generateCopywriting(r)}>
              生成英文文案
            </Button>
          )}
          {cs === 'generated' && (
            <Button size="small" type="primary" ghost icon={<AuditOutlined />}
              loading={busy} onClick={() => approveCopywriting(r)}>
              审核并批准
            </Button>
          )}
          <Tooltip title={cs === 'approved' ? '' : '需先完成英文文案审核与批准'}>
            <Button size="small" type="primary" icon={<RocketOutlined />}
              loading={publishingId === r.id}
              disabled={cs !== 'approved'}
              onClick={() => confirmPush(r)}>
              推送到 WC
            </Button>
          </Tooltip>
        </Space>
      )
    }},
  ]

  const b2bColumns = [
    { title: '商品', dataIndex: 'name', key: 'name', render: (v: string, r: Product) => (
      <div>
        <Text strong>{decodeHtmlEntities(v)}</Text>
        <br />
        <Text type="secondary" style={{ fontSize: 12 }}>SKU: {r.sku}</Text>
      </div>
    )},
    { title: '零售参考价', key: 'retail', render: (_: any, r: Product) => {
      const en = r.meta?.localizations?.en
      const price = en?.price || r.meta?.price || '-'
      return <Text>${price}</Text>
    }},
    { title: '批发阶梯价', key: 'tiers', render: (_: any, r: Product) => {
      const tiers = getWholesaleTiers(r)
      if (tiers.length === 0) return <Tag color="orange">未配置</Tag>
      return (
        <Space size={4}>
          {tiers.map((t, i) => (
            <Tag key={i}>{t.moq}+: ${t.price}</Tag>
          ))}
        </Space>
      )
    }},
    { title: '操作', key: 'op', render: (_: any, r: Product) => (
      <Button size="small" icon={<DollarOutlined />} onClick={() => openTierModal(r)}>
        配置批发价
      </Button>
    )},
  ]

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}>🚀 渠道与上架</Title>
      <Paragraph type="secondary">B2C（WooCommerce 独立站）与 B2B（批发目录）双渠道发布中心。商品从"商品工作台"审批通过后进入这里。</Paragraph>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="上架流程：生成英文文案 → 人工审核批准 → 推送 WooCommerce"
        description="英文站不接受中文商品。后端强制校验：缺少已批准英文文案或无有效零售价时禁止推送，不会以 0 元价格创建无法购买的商品。"
      />

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card size="small"><Statistic title="草稿商品" value={draftProducts.length} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="待审" value={pendingProducts.length} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="已发布" value={activeProducts.length} valueStyle={{ color: '#52c41a' }} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="WC 已同步" value={syncedCount} valueStyle={{ color: '#1890ff' }} /></Card></Col>
      </Row>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'b2c',
            label: <span><ShopOutlined /> B2C 零售（WooCommerce）</span>,
            children: (
              <Card size="small">
                <Table
                  rowKey="id"
                  loading={loading}
                  columns={b2cColumns}
                  dataSource={products}
                  pagination={{ pageSize: 15 }}
                  size="small"
                />
              </Card>
            ),
          },
          {
            key: 'b2b',
            label: <span><TeamOutlined /> B2B 批发目录</span>,
            children: (
              <Card size="small">
                <Alert
                  message="B2B 批发层：为每个商品配置阶梯价（MOQ 区间 → 批发价），供批发客户询价使用。"
                  type="info"
                  showIcon
                  style={{ marginBottom: 12 }}
                />
                <Table
                  rowKey="id"
                  loading={loading}
                  columns={b2bColumns}
                  dataSource={products}
                  pagination={{ pageSize: 15 }}
                  size="small"
                />
              </Card>
            ),
          },
        ]}
      />

      <Modal
        title={`配置批发阶梯价 — ${editingProduct?.name || ''}`}
        open={tierModalOpen}
        onCancel={() => setTierModalOpen(false)}
        onOk={saveTiers}
        okText="保存"
      >
        <Paragraph type="secondary" style={{ fontSize: 12 }}>
          设置批发客户的阶梯价（MOQ 最小起订量 → 单价）。B2C 零售价保持不变。
        </Paragraph>
        {tiers.map((t, i) => (
          <Row gutter={8} key={i} style={{ marginBottom: 8 }}>
            <Col span={8}>
              <Text type="secondary" style={{ fontSize: 12 }}>MOQ（件）</Text>
              <InputNumber min={1} value={t.moq} onChange={(v) => {
                const nt = [...tiers]
                nt[i] = { ...t, moq: v || 1 }
                setTiers(nt)
              }} style={{ width: '100%' }} />
            </Col>
            <Col span={8}>
              <Text type="secondary" style={{ fontSize: 12 }}>批发价（USD）</Text>
              <InputNumber min={0} value={t.price} onChange={(v) => {
                const nt = [...tiers]
                nt[i] = { ...t, price: v || 0 }
                setTiers(nt)
              }} style={{ width: '100%' }} />
            </Col>
            <Col span={6}>
              <Text type="secondary" style={{ fontSize: 12 }}>交期（天）</Text>
              <InputNumber min={1} value={t.lead_days || 14} onChange={(v) => {
                const nt = [...tiers]
                nt[i] = { ...t, lead_days: v || 14 }
                setTiers(nt)
              }} style={{ width: '100%' }} />
            </Col>
            <Col span={2}>
              <Button danger size="small" onClick={() => setTiers(tiers.filter((_, idx) => idx !== i))}>删</Button>
            </Col>
          </Row>
        ))}
        <Button type="dashed" size="small" icon={<PlusOutlined />} onClick={() => setTiers([...tiers, { moq: 500, price: 32, lead_days: 21 }])}>
          加一档
        </Button>
      </Modal>
    </div>
  )
}
