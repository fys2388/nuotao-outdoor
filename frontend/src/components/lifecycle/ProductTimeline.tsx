/**
 * 产品三身份时间线（ADR IDENTITY-002 §3）。
 *
 * 从**已有后端字段**渲染 Candidate → Master → Listing 三个身份，
 * 不引入新状态字段、不引入线性状态枚举：
 *
 *   Candidate  ← products.candidate_status
 *   Master     ← products.status
 *   Listing    ← products.meta.woocommerce_id + meta.localizations
 *
 * 注意：`candidate_status = NULL` 是合法业务状态（下游渠道商品，不在候选漏斗内），
 * 但它同时也是当前治理缺口的表现（WC→DB 同步直接建行，绕过候选评审）。
 * 因此本组件将其显式渲染为「渠道导入 · 未经候选评审」告警态，而不是隐藏——
 * 让缺口在 UI 上可见，便于追踪与修复。
 *
 * 字段路径已与后端 `app/schemas/product.py::ProductOut` 核对：
 * `woocommerce_id` 不在顶层，位于 `meta.woocommerce_id`。
 */

import React from 'react'
import { Tag, Typography, Tooltip } from 'antd'
import {
  QuestionCircleOutlined,
  CheckCircleFilled,
  ClockCircleFilled,
  CloseCircleFilled,
  StopOutlined,
  ExportOutlined,
} from '@ant-design/icons'
import { STAGE_BY_ID } from '../../lifecycle/stages'

const { Text, Paragraph } = Typography

// ---------------------------------------------------------------------------
// 产品数据类型（与后端 ProductOut 对齐）
// ---------------------------------------------------------------------------

export interface ProductLifecycleData {
  id: string
  sku: string
  name: string
  status: string
  candidate_status?: string | null
  source?: string
  source_url?: string | null
  meta?: Record<string, any> | null
}

// ---------------------------------------------------------------------------
// 身份状态解析
// ---------------------------------------------------------------------------

type Tone = 'ok' | 'warn' | 'idle' | 'blocked'

interface IdentityState {
  identity: 'candidate' | 'master' | 'listing'
  title: string
  label: string
  tone: Tone
  detail: string
  /** 该身份是否已达到（用于箭头方向着色） */
  reached: boolean
}

const CANDIDATE_LABELS: Record<string, { label: string; tone: Tone; reached: boolean }> = {
  candidate: { label: '候选中', tone: 'warn', reached: true },
  approved: { label: '已批准', tone: 'ok', reached: true },
  testing: { label: '测试中', tone: 'ok', reached: true },
  winner: { label: '已胜出', tone: 'ok', reached: true },
  rejected: { label: '已拒绝', tone: 'blocked', reached: false },
}

const STATUS_LABELS: Record<string, { label: string; tone: Tone; reached: boolean }> = {
  draft: { label: '草稿', tone: 'idle', reached: false },
  active: { label: '已转正', tone: 'ok', reached: true },
  inactive: { label: '已停用', tone: 'blocked', reached: false },
  listed: { label: '已上架', tone: 'ok', reached: true },
  pending: { label: '待处理', tone: 'warn', reached: false },
}

const CONTENT_LABELS: Record<string, string> = {
  generated: 'AI 生成，待人审',
  approved: '已审核通过',
  pending: '待审',
}

const TONE_COLOR: Record<Tone, string> = {
  ok: '#2e7d32',
  warn: '#d48806',
  idle: '#8c8c8c',
  blocked: '#a8071a',
}

const TONE_BG: Record<Tone, string> = {
  ok: '#e8f5e9',
  warn: '#fff7e6',
  idle: '#f5f5f5',
  blocked: '#fff1f0',
}

export function resolveIdentities(p: ProductLifecycleData): IdentityState[] {
  // --- Candidate ---
  const cs = p.candidate_status ?? null
  let candidate: IdentityState
  if (cs === null) {
    candidate = {
      identity: 'candidate',
      title: '产品候选',
      label: '渠道导入 · 未经候选评审',
      tone: 'warn',
      detail:
        'candidate_status 为空：该行不是候选漏斗内的产品（典型来源为 WooCommerce 反向同步）。' +
        '闸门将视为「下游商品，免评审」。',
      reached: false,
    }
  } else {
    const c = CANDIDATE_LABELS[cs] ?? { label: cs, tone: 'warn' as Tone, reached: true }
    candidate = {
      identity: 'candidate',
      title: '产品候选',
      label: c.label,
      tone: c.tone,
      detail: `candidate_status = ${cs}`,
      reached: c.reached,
    }
  }

  // --- Master ---
  const m = STATUS_LABELS[p.status] ?? {
    label: p.status,
    tone: 'idle' as Tone,
    reached: false,
  }
  const master: IdentityState = {
    identity: 'master',
    title: 'Product Master',
    label: m.label,
    tone: m.tone,
    detail: `status = ${p.status}`,
    reached: m.reached,
  }

  // --- Listing ---
  const wcId = p.meta?.woocommerce_id
  const loc = p.meta?.localizations
  const enStatus = loc?.en?.status as string | undefined
  const hasContent = Boolean(
    (loc && Object.keys(loc).length > 0) ||
      (p.meta && (p.meta as Record<string, any>).content),
  )

  let listing: IdentityState
  if (wcId) {
    const contentNote = enStatus
      ? ` · 英文文案：${CONTENT_LABELS[enStatus] ?? enStatus}`
      : hasContent
        ? ' · 有本地化数据'
        : ''
    listing = {
      identity: 'listing',
      title: 'WooCommerce Listing',
      label: `已同步 #${wcId}`,
      tone: 'ok',
      detail: `meta.woocommerce_id = ${wcId}${contentNote}`,
      reached: true,
    }
  } else {
    listing = {
      identity: 'listing',
      title: 'WooCommerce Listing',
      label: hasContent ? '待同步' : '未同步',
      tone: hasContent ? 'warn' : 'idle',
      detail: 'meta.woocommerce_id 为空',
      reached: false,
    }
  }

  return [candidate, master, listing]
}

// ---------------------------------------------------------------------------
// 组件
// ---------------------------------------------------------------------------

interface ProductTimelineProps {
  product: ProductLifecycleData
  /** 紧凑模式用于列表行内渲染 */
  compact?: boolean
  style?: React.CSSProperties
}

function ToneIcon({ tone, reached }: { tone: Tone; reached: boolean }) {
  const color = TONE_COLOR[tone]
  if (tone === 'blocked') return <StopOutlined style={{ color }} />
  if (reached && tone === 'ok') return <CheckCircleFilled style={{ color }} />
  if (tone === 'warn') return <ClockCircleFilled style={{ color }} />
  return <ClockCircleFilled style={{ color }} />
}

export default function ProductTimeline({ product, compact = false, style }: ProductTimelineProps) {
  const identities = resolveIdentities(product)

  if (compact) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', ...style }}>
        {identities.map((it, i) => (
          <React.Fragment key={it.identity}>
            {i > 0 && (
              <Text type="secondary" style={{ fontSize: 11, margin: 0 }}>
                →
              </Text>
            )}
            <Tooltip title={`${it.title}：${it.detail}`}>
              <Tag
                color={TONE_COLOR[it.tone]}
                style={{ margin: 0, fontSize: 11, lineHeight: '16px', padding: '0 6px' }}
              >
                {it.label}
              </Tag>
            </Tooltip>
          </React.Fragment>
        ))}
      </div>
    )
  }

  return (
    <div
      style={{
        border: '1px solid #f0f0f0',
        borderRadius: 8,
        padding: 16,
        background: '#fafafa',
        ...style,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'stretch', gap: 0 }}>
        {identities.map((it, i) => (
          <React.Fragment key={it.identity}>
            {i > 0 && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  padding: '0 12px',
                  color: it.reached ? TONE_COLOR[it.tone] : '#d9d9d9',
                  fontSize: 18,
                }}
              >
                →
              </div>
            )}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{
                  background: TONE_BG[it.tone],
                  border: `1px solid ${TONE_COLOR[it.tone]}33`,
                  borderRadius: 6,
                  padding: '12px 14px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <ToneIcon tone={it.tone} reached={it.reached} />
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {STAGE_BY_ID.get(
                      it.identity === 'candidate'
                        ? 'candidate'
                        : it.identity === 'master'
                          ? 'master'
                          : 'wc_sync',
                    )?.n
                      ? `阶段 ${
                          STAGE_BY_ID.get(
                            it.identity === 'candidate'
                              ? 'candidate'
                              : it.identity === 'master'
                                ? 'master'
                                : 'wc_sync',
                          )?.n
                        } · `
                      : ''}
                    {it.title}
                  </Text>
                </div>
                <div style={{ marginTop: 6, fontWeight: 600, color: TONE_COLOR[it.tone] }}>
                  {it.label}
                </div>
                {it.identity === 'candidate' && it.reached === false && it.tone === 'warn' && (
                  <Tooltip
                    title="这是当前已知治理缺口：WooCommerce 反向同步会直接创建本地行且 candidate_status 为空，从而绕过候选评审闸门。"
                  >
                    <Paragraph
                      style={{
                        marginTop: 6,
                        fontSize: 12,
                        color: TONE_COLOR[it.tone],
                        marginBottom: 0,
                      }}
                    >
                      <QuestionCircleOutlined style={{ marginRight: 4 }} />
                      {it.detail}
                    </Paragraph>
                  </Tooltip>
                )}
              </div>
            </div>
          </React.Fragment>
        ))}
      </div>

      <div style={{ marginTop: 10, display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          SKU：{product.sku}
        </Text>
        {product.source && (
          <Text type="secondary" style={{ fontSize: 12 }}>
            来源：{product.source}
          </Text>
        )}
        {product.meta?.woocommerce_id && (
          <Text type="secondary" style={{ fontSize: 12 }}>
            <ExportOutlined style={{ marginRight: 4 }} />
            WC #{product.meta.woocommerce_id}
          </Text>
        )}
        {product.id !== undefined && (
          <Text type="secondary" style={{ fontSize: 12 }}>
            ID：{product.id.length > 8 ? `${product.id.slice(0, 8)}…` : product.id}
          </Text>
        )}
      </div>
    </div>
  )
}
