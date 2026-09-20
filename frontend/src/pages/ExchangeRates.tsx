import { useCallback, useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Modal,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import { PlusOutlined, ReloadOutlined, SwapOutlined } from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'
import { api, ApiError } from '../api/client'

const { Title, Paragraph, Text } = Typography

interface ExchangeRate {
  id: string
  base_currency: string
  quote_currency: string
  rate: string
  effective_date: string
  source: string
  source_reference: string | null
  created_by: string
  created_at: string
}

interface ExchangeRateList {
  items: ExchangeRate[]
  total: number
}

interface RateFormValues {
  base_currency: string
  quote_currency: string
  rate: string | number
  effective_date: Dayjs
  source: string
  source_reference?: string
}

export default function ExchangeRates() {
  const [rows, setRows] = useState<ExchangeRate[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [form] = Form.useForm<RateFormValues>()

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = (await api.getExchangeRates({ limit: 500 })) as ExchangeRateList
      setRows(response.items)
    } catch (requestError) {
      setRows([])
      setError(
        requestError instanceof ApiError && requestError.status === 403
          ? '当前账号没有汇率管理权限。'
          : requestError instanceof Error
            ? requestError.message
            : '汇率数据加载失败',
      )
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const submit = async () => {
    const values = await form.validateFields()
    setSaving(true)
    try {
      await api.createExchangeRate({
        base_currency: values.base_currency.trim().toUpperCase(),
        quote_currency: values.quote_currency.trim().toUpperCase(),
        rate: String(values.rate),
        effective_date: values.effective_date.format('YYYY-MM-DD'),
        source: values.source.trim(),
        source_reference: values.source_reference?.trim() || undefined,
      })
      message.success('汇率已保存')
      setModalOpen(false)
      form.resetFields()
      await load()
    } catch (requestError) {
      if (requestError instanceof ApiError) {
        message.error(requestError.message)
      } else if (requestError instanceof Error && requestError.message) {
        message.error(requestError.message)
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="resource-page">
      <div className="page-heading">
        <div>
          <div className="page-kicker">AUDITABLE CURRENCY CONVERSION</div>
          <Title level={2}>汇率管理</Title>
          <Paragraph>
            每个工作日维护直接汇率。经营报表只使用生效日不晚于业务日期的最近一条记录，
            缺失汇率时明确报错，不自动猜汇率。
          </Paragraph>
        </div>
        <Space wrap>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
            新增汇率
          </Button>
        </Space>
      </div>

      {error && (
        <Alert
          className="page-alert"
          type={error.includes('权限') ? 'warning' : 'error'}
          showIcon
          title="汇率数据当前不可用"
          description={error}
        />
      )}

      <Card variant="borderless" className="resource-panel" title="最新汇率记录">
        <Table
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          dataSource={rows}
          scroll={{ x: 900 }}
          locale={{ emptyText: '尚未维护汇率，合并报表将被后端拒绝' }}
          columns={[
            {
              title: '货币对',
              key: 'pair',
              render: (_, row) => (
                <Space>
                  <Tag>{row.base_currency}</Tag>
                  <SwapOutlined />
                  <Tag color="blue">{row.quote_currency}</Tag>
                </Space>
              ),
            },
            {
              title: '汇率',
              dataIndex: 'rate',
              align: 'right',
              render: (value: string, row) => (
                <Text>
                  1 {row.base_currency} = <strong>{value}</strong> {row.quote_currency}
                </Text>
              ),
            },
            { title: '生效日期', dataIndex: 'effective_date', width: 120 },
            { title: '来源', dataIndex: 'source', width: 120 },
            {
              title: '来源凭证',
              dataIndex: 'source_reference',
              ellipsis: true,
              render: (value: string | null) => value || '--',
            },
            { title: '维护人', dataIndex: 'created_by', width: 180 },
          ]}
        />
      </Card>

      <Modal
        title="新增汇率"
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => void submit()}
        confirmLoading={saving}
        okText="保存汇率"
        destroyOnHidden
      >
        <Alert
          type="info"
          showIcon
          title="汇率方向必须明确"
          description="例如 1 USD = 0.92 EUR，则应填写基础币种 USD、报价币种 EUR、汇率 0.92。"
          style={{ marginBottom: 16 }}
        />
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            base_currency: 'USD',
            quote_currency: 'EUR',
            effective_date: dayjs(),
            source: 'manual',
          }}
        >
          <Space align="start" style={{ width: '100%' }}>
            <Form.Item
              name="base_currency"
              label="基础币种"
              rules={[{ required: true, len: 3, message: '请输入 3 位币种代码' }]}
            >
              <Input maxLength={8} placeholder="USD" />
            </Form.Item>
            <Form.Item
              name="quote_currency"
              label="报价币种"
              rules={[{ required: true, len: 3, message: '请输入 3 位币种代码' }]}
            >
              <Input maxLength={8} placeholder="EUR" />
            </Form.Item>
          </Space>
          <Form.Item
            name="rate"
            label="汇率"
            rules={[{ required: true, message: '请输入大于 0 的汇率' }]}
          >
            <InputNumber
              stringMode
              min="0.000000000001"
              precision={12}
              style={{ width: '100%' }}
              placeholder="0.920000000000"
            />
          </Form.Item>
          <Form.Item
            name="effective_date"
            label="生效日期"
            rules={[{ required: true, message: '请选择生效日期' }]}
          >
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="source"
            label="来源"
            rules={[{ required: true, message: '请输入汇率来源' }]}
          >
            <Input maxLength={64} placeholder="ECB / 银行 / 财务确认" />
          </Form.Item>
          <Form.Item name="source_reference" label="来源凭证">
            <Input maxLength={255} placeholder="可选，例如银行牌价编号或 URL" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
