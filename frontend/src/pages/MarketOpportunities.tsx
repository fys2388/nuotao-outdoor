// Market Intelligence page: AI-discovered opportunities for outdoor categories.
// MVP: calls Newton Agent with a market-trend prompt, renders opportunity cards.
import { useState } from 'react'
import {
  Card, Input, Button, Typography, Row, Col, Tag, Space, message, Alert, Spin
} from 'antd'
import { RocketOutlined, ThunderboltOutlined, TrendChartOutlined } from '@ant-design/icons'

const { Title, Paragraph, Text } = Typography
const { TextArea } = Input

interface Opportunity {
  keyword: string
  growth_90d?: string
  competition?: string
  margin_estimate?: string
  rationale?: string
}

export default function MarketOpportunities() {
  const [category, setCategory] = useState('ultralight camping chair')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<string>('')

  const discover = async () => {
    if (!category.trim()) {
      message.warning('请输入户外品类关键词')
      return
    }
    setLoading(true)
    setResult('')
    try {
      const resp = await fetch('/api/v1/newton/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: `你是 Nuotao 的市场情报 Agent。请分析户外品类「${category}」在美国市场的机会：\n1. 过去 90 天搜索/销量趋势\n2. Amazon 竞争度（Top10 品牌集中度）\n3. 预估毛利空间（成本 $15-25，售价 $60-90）\n4. 风险（侵权/季节性/物流）\n5. 推荐 3 个具体切入点\n用 JSON 返回，key: trend, competition, margin, risk, angles[3]`,
        }),
      })
      const data = await resp.json()
      const text = data?.data?.summary || data?.summary || data?.data?.content || JSON.stringify(data, null, 2)
      setResult(text)
    } catch (e: any) {
      message.error(e.message || '分析失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}>🎯 市场机会发现</Title>
      <Paragraph type="secondary">
        AI 主动发现户外品类机会。输入品类关键词，AI 分析趋势、竞争、利润、风险，给出切入点建议。
        阶段 1（Market Intelligence）。
      </Paragraph>

      <Card size="small" style={{ marginBottom: 16 }}>
        <TextArea
          rows={2}
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          placeholder="例如：ultralight camping chair / camping lantern / collapsible water bottle"
        />
        <Button
          type="primary"
          icon={<RocketOutlined />}
          loading={loading}
          onClick={discover}
          style={{ marginTop: 12 }}
        >
          AI 分析机会
        </Button>
      </Card>

      {loading && <Spin tip="AI 正在分析市场机会..." />}

      {result && (
        <Card size="small" title="分析结果">
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 13 }}>{result}</pre>
          <Alert
            message="下一步"
            description="复制切入点关键词到「牛顿 AI 对话选品」，AI 会去 1688 找具体货源。"
            type="info"
            showIcon
            style={{ marginTop: 12 }}
          />
        </Card>
      )}
    </div>
  )
}
