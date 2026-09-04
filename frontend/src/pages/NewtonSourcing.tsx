import { useEffect, useState } from 'react'
import {
  Input, Button, Space, Card, Row, Col, Tag, Spin, Alert, Statistic,
  Typography, List, Badge, Tooltip, Empty, message, Divider, Rate
} from 'antd'
import {
  SearchOutlined, RobotOutlined, ThunderboltOutlined,
  DollarOutlined, ShopOutlined, StarOutlined, CheckCircleOutlined
} from '@ant-design/icons'
import { api } from '../api/client'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

interface NewtonProduct {
  product_id: string
  subject: string
  price: string | number
  min_order_qty: number
  supplier: string
  image_url: string
  detail_url: string
  score: number
  reason: string
}

interface SearchResult {
  success: boolean
  query: string
  total: number
  products: NewtonProduct[]
  summary: string
  task_id: string
}

const scoreColor = (score: number) => {
  if (score >= 80) return '#52c41a'
  if (score >= 65) return '#1890ff'
  if (score >= 50) return '#faad14'
  return '#ff4d4f'
}

const scoreGrade = (score: number) => {
  if (score >= 80) return { label: 'S', color: '#52c41a' }
  if (score >= 65) return { label: 'A', color: '#1890ff' }
  if (score >= 50) return { label: 'B', color: '#faad14' }
  return { label: 'C', color: '#ff4d4f' }
}

export default function NewtonSourcingPage() {
  const [query, setQuery] = useState('')
  const [minPrice, setMinPrice] = useState<number | undefined>(undefined)
  const [maxPrice, setMaxPrice] = useState<number | undefined>(undefined)
  const [minOrderQty, setMinOrderQty] = useState<number | undefined>(undefined)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<SearchResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState<any>(null)
  const [credits, setCredits] = useState<any>(null)

  const fetchStatus = async () => {
    try {
      const data: any = await api.getNewtonStatus()
      setStatus(data.data)
    } catch (e) {
      // 静默失败
    }
  }

  const fetchCredits = async () => {
    try {
      const data: any = await api.getNewtonCostCredits()
      setCredits(data.data)
    } catch (e) {
      // 静默失败
    }
  }

  useEffect(() => {
    fetchStatus()
    fetchCredits()
  }, [])

  const handleSearch = async () => {
    if (!query.trim()) {
      message.warning('请输入找品需求')
      return
    }

    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const data: any = await api.newtonSearch(
        query.trim(),
        minPrice,
        maxPrice,
        minOrderQty
      )

      if (data.success && data.data) {
        setResult(data.data)
        message.success(`找到 ${data.data.total || 0} 个商品`)
      } else {
        setError(data.error || '找品失败')
      }
    } catch (e: any) {
      setError(e.message || '网络错误')
    } finally {
      setLoading(false)
      fetchCredits()
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSearch()
    }
  }

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: '24px' }}>
        <Space align="center">
          <RobotOutlined style={{ fontSize: '32px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>牛顿AI智能选品</Title>
            <Text type="secondary">基于阿里牛顿云端Agent，自然语言找品、比价、筛选</Text>
          </div>
        </Space>
      </div>

      {/* 状态卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: '24px' }}>
        <Col xs={24} sm={8}>
          <Card size="small">
            <Statistic
              title="API状态"
              value={status?.configured ? '已配置' : '未配置'}
              valueStyle={{ color: status?.configured ? '#52c41a' : '#ff4d4f', fontSize: '18px' }}
              prefix={<CheckCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card size="small">
            <Statistic
              title="每日额度"
              value={status?.daily_limit || 5000}
              suffix="次/天"
              valueStyle={{ fontSize: '18px' }}
              prefix={<ThunderboltOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card size="small">
            <Statistic
              title="可用积分"
              value={credits?.available_credits || 0}
              precision={1}
              valueStyle={{ fontSize: '18px', color: '#722ed1' }}
              prefix={<DollarOutlined />}
            />
          </Card>
        </Col>
      </Row>

      {/* 搜索表单 */}
      <Card style={{ marginBottom: '24px' }}>
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <div>
            <Text strong style={{ display: 'block', marginBottom: '8px' }}>
              <SearchOutlined /> 找品需求
            </Text>
            <TextArea
              rows={3}
              placeholder="例如：户外露营灯，10-30元，USB充电，轻量化，适合跨境电商销售"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyPress={handleKeyPress}
              disabled={loading}
            />
          </div>

          <Row gutter={[16, 8]}>
            <Col xs={12} sm={6}>
              <Input
                type="number"
                placeholder="最低价格(元)"
                value={minPrice}
                onChange={(e) => setMinPrice(e.target.value ? Number(e.target.value) : undefined)}
                disabled={loading}
                prefix="¥"
              />
            </Col>
            <Col xs={12} sm={6}>
              <Input
                type="number"
                placeholder="最高价格(元)"
                value={maxPrice}
                onChange={(e) => setMaxPrice(e.target.value ? Number(e.target.value) : undefined)}
                disabled={loading}
                prefix="¥"
              />
            </Col>
            <Col xs={12} sm={6}>
              <Input
                type="number"
                placeholder="最小起订量"
                value={minOrderQty}
                onChange={(e) => setMinOrderQty(e.target.value ? Number(e.target.value) : undefined)}
                disabled={loading}
                suffix="个"
              />
            </Col>
            <Col xs={12} sm={6}>
              <Button
                type="primary"
                size="large"
                icon={<SearchOutlined />}
                onClick={handleSearch}
                loading={loading}
                block
              >
                {loading ? 'AI找品中...' : '开始找品'}
              </Button>
            </Col>
          </Row>
        </Space>
      </Card>

      {/* 错误提示 */}
      {error && (
        <Alert
          type="error"
          message={error}
          showIcon
          style={{ marginBottom: '24px' }}
          action={
            <Button size="small" onClick={handleSearch}>重试</Button>
          }
        />
      )}

      {/* 加载中 */}
      {loading && (
        <div style={{ textAlign: 'center', padding: '60px 0' }}>
          <Spin size="large" tip="牛顿Agent正在1688找品、比价、筛选..." />
          <Paragraph type="secondary" style={{ marginTop: '16px' }}>
            通常需要30-60秒，Agent会自动搜索商品、计算性价比、生成推荐
          </Paragraph>
        </div>
      )}

      {/* 搜索结果 */}
      {result && !loading && (
        <>
          {/* AI总结 */}
          {result.summary && (
            <Card
              style={{ marginBottom: '24px' }}
              title={
                <Space>
                  <RobotOutlined style={{ color: '#722ed1' }} />
                  <span>AI选品总结</span>
                </Space>
              }
            >
              <Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
                {result.summary}
              </Paragraph>
            </Card>
          )}

          {/* 商品列表 */}
          <Card
            title={
              <Space>
                <ShopOutlined />
                <span>推荐商品</span>
                <Tag color="purple">{result.total || 0} 个</Tag>
              </Space>
            }
            extra={
              <Text type="secondary">任务ID: {result.task_id?.substring(0, 8)}...</Text>
            }
          >
            {result.products && result.products.length > 0 ? (
              <List
                itemLayout="vertical"
                dataSource={result.products}
                renderItem={(item, index) => {
                  const grade = scoreGrade(item.score)
                  return (
                    <List.Item key={item.product_id || index}>
                      <Row gutter={[16, 16]} align="top">
                        {/* 排名 */}
                        <Col flex="60px">
                          <div style={{
                            width: '48px',
                            height: '48px',
                            borderRadius: '50%',
                            background: index < 3 ? grade.color : '#f0f0f0',
                            color: index < 3 ? '#fff' : '#666',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontSize: '20px',
                            fontWeight: 'bold',
                          }}>
                            {index + 1}
                          </div>
                        </Col>

                        {/* 商品信息 */}
                        <Col flex="auto">
                          <Space direction="vertical" size={4} style={{ width: '100%' }}>
                            <Space wrap>
                              <Text strong style={{ fontSize: '15px' }}>
                                {item.subject || '未知商品'}
                              </Text>
                              <Tag color={grade.color} style={{ fontSize: '13px', padding: '2px 10px' }}>
                                {grade.label}级
                              </Tag>
                              <Badge
                                count={`${item.score}分`}
                                style={{ backgroundColor: scoreColor(item.score), fontSize: '12px' }}
                              />
                            </Space>

                            <Row gutter={[16, 8]}>
                              <Col span={8}>
                                <Text type="secondary">价格：</Text>
                                <Text strong style={{ color: '#ff4d4f', fontSize: '16px' }}>
                                  ¥{item.price || 'N/A'}
                                </Text>
                              </Col>
                              <Col span={8}>
                                <Text type="secondary">起订：</Text>
                                <Text>{item.min_order_qty || 1} 个</Text>
                              </Col>
                              <Col span={8}>
                                <Text type="secondary">供应商：</Text>
                                <Text>{item.supplier || 'N/A'}</Text>
                              </Col>
                            </Row>

                            {item.reason && (
                              <Alert
                                type="info"
                                showIcon
                                message={item.reason}
                                style={{ marginTop: '8px' }}
                              />
                            )}

                            <Space style={{ marginTop: '8px' }}>
                              {item.detail_url && (
                                <Button
                                  type="link"
                                  href={item.detail_url}
                                  target="_blank"
                                  size="small"
                                >
                                  查看商品详情
                                </Button>
                              )}
                              <Button
                                size="small"
                                icon={<StarOutlined />}
                                onClick={() => message.success('已加入选品候选库')}
                              >
                                加入候选
                              </Button>
                            </Space>
                          </Space>
                        </Col>
                      </Row>
                    </List.Item>
                  )
                }}
              />
            ) : (
              <Empty description="未找到符合条件的商品" />
            )}
          </Card>
        </>
      )}

      {/* 空状态 */}
      {!result && !loading && !error && (
        <Card>
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <div>
                <Paragraph>输入找品需求，牛顿Agent会自动在1688搜索、比价、筛选</Paragraph>
                <Space wrap>
                  <Tag color="blue">自然语言找品</Tag>
                  <Tag color="green">智能比价</Tag>
                  <Tag color="orange">性价比评分</Tag>
                  <Tag color="purple">批量筛选</Tag>
                </Space>
              </div>
            }
          />
        </Card>
      )}
    </div>
  )
}
