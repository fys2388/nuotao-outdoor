import { useEffect, useState } from 'react'
import { Card, Spin, Tooltip, Typography } from 'antd'
import {
  AppstoreOutlined,
  ArrowRightOutlined,
  BulbOutlined,
  CarOutlined,
  DatabaseOutlined,
  DollarOutlined,
  LineChartOutlined,
  RobotOutlined,
  ShoppingCartOutlined,
  ShoppingOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import type { ReactNode } from 'react'
import { api, request } from '../api/client'

const { Text } = Typography

/**
 * 端到端价值流主带。
 * 只做两件事：1) 沿「选品→采购→库存→订单→物流→回款→复盘」给出真实规模脉搏；
 * 2) 一键进入对应环节，把原本互相孤立的页面按业务流向串起来。
 * 所有计数均来自现有只读接口，独立容错：任一环节取数失败只显示 “–”，绝不伪造数字，也不阻断其它环节。
 * 当返回条数达到本次取数上限时显示 “N+”，避免把分页上限误呈现为精确总数。
 */

interface CountState {
  count: number | null
  capped: boolean
}

interface Stage {
  key: string
  label: string
  route: string
  icon: ReactNode
  hint: string
  pageLimit: number
  loader: () => Promise<unknown>
  highlight?: boolean
}

// 从后端各异的列表返回结构中稳健提取记录数。
// 数组/列表长度达到本次取数上限时标记 capped（真实总数可能更多）；对象自带 total/count 时视为精确值。
function readCount(payload: unknown, pageLimit: number): CountState {
  if (Array.isArray(payload)) {
    return { count: payload.length, capped: payload.length >= pageLimit }
  }
  if (payload && typeof payload === 'object') {
    const record = payload as Record<string, unknown>
    for (const field of ['items', 'records', 'data', 'list']) {
      const value = record[field]
      if (Array.isArray(value)) {
        return { count: value.length, capped: value.length >= pageLimit }
      }
    }
    if (typeof record.total === 'number') return { count: record.total, capped: false }
    if (typeof record.count === 'number') return { count: record.count, capped: false }
  }
  return { count: null, capped: false }
}

function formatCount(state: CountState | undefined): string {
  if (!state || state.count === null) return '–'
  return state.capped ? `${state.count}+` : String(state.count)
}

const STAGES: Stage[] = [
  {
    key: 'candidate',
    label: '选品',
    route: '/products/candidates',
    icon: <BulbOutlined />,
    hint: '1688 导入与候选评估',
    pageLimit: 100,
    loader: () => api.getSourcingCandidates('all', 100),
  },
  {
    key: 'product',
    label: '商品',
    route: '/products',
    icon: <AppstoreOutlined />,
    hint: '商品主数据 / 上架 WooCommerce',
    pageLimit: 100,
    loader: () => api.getProducts(100),
  },
  {
    key: 'purchase',
    label: '采购',
    route: '/supply/purchases',
    icon: <ShoppingOutlined />,
    hint: '采购订单状态机',
    pageLimit: 100,
    loader: () => api.getSupplyPurchaseOrders(100),
  },
  {
    key: 'inventory',
    label: '库存',
    route: '/supply/inventory',
    icon: <DatabaseOutlined />,
    hint: '仓库与库存快照',
    pageLimit: 100,
    loader: () => api.getInventorySnapshots(100),
  },
  {
    key: 'order',
    label: '订单',
    route: '/b2c/orders',
    icon: <ShoppingCartOutlined />,
    hint: 'B2C 订单履约',
    pageLimit: 100,
    loader: () => api.getOrders(100),
  },
  {
    key: 'logistics',
    label: '物流',
    route: '/supply/logistics',
    icon: <CarOutlined />,
    hint: '发货与妥投轨迹',
    pageLimit: 100,
    loader: () => api.getSupplyShipments(100),
  },
  {
    key: 'receivable',
    label: '回款',
    route: '/b2b/receivables',
    icon: <DollarOutlined />,
    hint: '应收 / 发票 / 收款核销',
    pageLimit: 100,
    loader: () => api.getB2BReceivables(),
  },
  {
    key: 'review',
    label: '复盘',
    route: '/analytics/channels',
    icon: <LineChartOutlined />,
    hint: '渠道表现与经营分析',
    pageLimit: 100,
    loader: () => Promise.resolve(null),
  },
]

type CountMap = Record<string, CountState>
const ACTION_PAGE_LIMIT = 200

export default function ValueStreamBar() {
  const navigate = useNavigate()
  const [counts, setCounts] = useState<CountMap>({})
  const [loading, setLoading] = useState(true)
  const [pendingActions, setPendingActions] = useState<CountState | undefined>(undefined)

  useEffect(() => {
    let cancelled = false

    async function load() {
      // AI 行动待办（待审批建议数），单独取，失败静默。
      request(`/agent-suggestions?status=pending_approval&limit=${ACTION_PAGE_LIMIT}`)
        .then((payload) => {
          if (!cancelled) setPendingActions(readCount(payload, ACTION_PAGE_LIMIT))
        })
        .catch(() => {
          if (!cancelled) setPendingActions({ count: null, capped: false })
        })

      const entries = await Promise.all(
        STAGES.map(async (stage) => {
          try {
            const payload = await stage.loader()
            return [stage.key, readCount(payload, stage.pageLimit)] as const
          } catch {
            return [stage.key, { count: null, capped: false }] as const
          }
        }),
      )
      if (!cancelled) {
        setCounts(Object.fromEntries(entries) as CountMap)
        setLoading(false)
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <Card variant="borderless" className="value-stream-bar">
      <div className="vsb-header">
        <Text strong>端到端价值流</Text>
        <Text type="secondary" className="vsb-sub">
          沿业务流向进入各环节 · 数字为当前记录规模（真实接口，N+ 表示超过取数上限）
        </Text>
      </div>

      {loading ? (
        <div className="vsb-loading">
          <Spin size="small" />
        </div>
      ) : (
        <div className="vsb-track">
          {STAGES.map((stage, index) => (
            <div className="vsb-step" key={stage.key}>
              <Tooltip title={stage.hint}>
                <button
                  type="button"
                  className="vsb-stage"
                  onClick={() => navigate(stage.route)}
                >
                  <span className="vsb-icon">{stage.icon}</span>
                  <span className="vsb-body">
                    <span className="vsb-label">{stage.label}</span>
                    <span className="vsb-count">{formatCount(counts[stage.key])}</span>
                  </span>
                </button>
              </Tooltip>
              {index < STAGES.length - 1 && (
                <ArrowRightOutlined className="vsb-arrow" aria-hidden />
              )}
            </div>
          ))}

          <div className="vsb-step">
            <Tooltip title="AI 建议审批中心：待你确认的行动">
              <button
                type="button"
                className="vsb-stage vsb-stage--ai"
                onClick={() => navigate('/ai/suggestions')}
              >
                <span className="vsb-icon">
                  <RobotOutlined />
                </span>
                <span className="vsb-body">
                  <span className="vsb-label">AI 行动</span>
                  <span className="vsb-count">
                    {pendingActions?.count === null || pendingActions === undefined
                      ? '–'
                      : `${formatCount(pendingActions)} 待办`}
                  </span>
                </span>
              </button>
            </Tooltip>
          </div>
        </div>
      )}
    </Card>
  )
}
