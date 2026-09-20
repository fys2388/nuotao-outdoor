export const B2B_PORTAL_TOKEN_KEY = 'b2b_portal_token'
export const B2B_PORTAL_BASE = '/api/v1/b2b-portal'

export class PortalApiError extends Error {
  status: number
  detail: unknown

  constructor(message: string, status: number, detail?: unknown) {
    super(message)
    this.name = 'PortalApiError'
    this.status = status
    this.detail = detail
  }
}

interface PortalRequestOptions extends RequestInit {
  timeoutMs?: number
}

export function getPortalToken(): string | null {
  return localStorage.getItem(B2B_PORTAL_TOKEN_KEY)
}

export function setPortalToken(token: string): void {
  localStorage.setItem(B2B_PORTAL_TOKEN_KEY, token)
}

export function clearPortalToken(): void {
  localStorage.removeItem(B2B_PORTAL_TOKEN_KEY)
}

function parseError(payload: unknown, fallback: string): string {
  if (typeof payload === 'string' && payload.trim()) return payload
  if (payload && typeof payload === 'object') {
    const record = payload as Record<string, unknown>
    if (typeof record.detail === 'string' && record.detail.trim()) {
      return record.detail
    }
    if (Array.isArray(record.detail) && record.detail.length > 0) {
      const first = record.detail[0] as Record<string, unknown>
      if (typeof first?.msg === 'string') return first.msg
    }
  }
  return fallback
}

export async function portalRequest<T>(
  endpoint: string,
  options: PortalRequestOptions = {},
): Promise<T> {
  const { timeoutMs = 30000, ...fetchOptions } = options
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  const token = getPortalToken()
  const headers = new Headers(fetchOptions.headers)

  if (!(fetchOptions.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  try {
    const response = await fetch(`${B2B_PORTAL_BASE}${endpoint}`, {
      ...fetchOptions,
      headers,
      signal: controller.signal,
    })
    const contentType = response.headers.get('content-type') || ''
    const payload = contentType.includes('application/json')
      ? await response.json().catch(() => null)
      : await response.text().catch(() => '')

    if (!response.ok) {
      if (response.status === 401) clearPortalToken()
      throw new PortalApiError(
        parseError(payload, `请求失败（HTTP ${response.status}）`),
        response.status,
        payload,
      )
    }
    return payload as T
  } catch (error) {
    if (error instanceof PortalApiError) throw error
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new PortalApiError('请求超时', 408)
    }
    throw new PortalApiError(error instanceof Error ? error.message : '网络请求失败', 0)
  } finally {
    window.clearTimeout(timer)
  }
}

export const portalApi = {
  login: (email: string, password: string) =>
    portalRequest<PortalLoginResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  apply: (data: Record<string, unknown>) =>
    portalRequest('/applications', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  me: () => portalRequest<PortalAgent>('/auth/me'),
  summary: () => portalRequest<PortalAccountSummary>('/account/summary'),
  products: (search?: string) => {
    const params = new URLSearchParams({ page: '1', page_size: '100' })
    if (search) params.set('search', search)
    return portalRequest<PortalProductList>(`/products?${params.toString()}`)
  },
  rfqs: (page = 1, pageSize = 100) =>
    portalRequest<PortalRFQList>(`/rfqs?page=${page}&page_size=${pageSize}`),
  createRfq: (data: Record<string, unknown>) =>
    portalRequest<PortalRFQ>('/rfqs', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  quotes: (page = 1, pageSize = 100) =>
    portalRequest<PortalQuoteList>(`/quotes?page=${page}&page_size=${pageSize}`),
  acceptQuote: (id: string) =>
    portalRequest<PortalQuote>(`/quotes/${id}/accept`, { method: 'POST' }),
  rejectQuote: (id: string, reason: string) =>
    portalRequest<PortalQuote>(`/quotes/${id}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  contracts: (page = 1, pageSize = 100) =>
    portalRequest<PortalContractList>(`/contracts?page=${page}&page_size=${pageSize}`),
  signContract: (id: string, signedBy: string) =>
    portalRequest<PortalContract>(`/contracts/${id}/sign`, {
      method: 'POST',
      body: JSON.stringify({ signed_by: signedBy }),
    }),
  convertContract: (id: string) =>
    portalRequest<PortalOrderConversion>(`/contracts/${id}/convert-to-order`, {
      method: 'POST',
    }),
  orders: (page = 1, pageSize = 100) =>
    portalRequest<PortalOrderList>(`/orders?page=${page}&page_size=${pageSize}`),
}

export interface PortalAgent {
  id: string
  agent_number: string
  company_name: string
  contact_name: string
  email: string
  phone: string | null
  country: string | null
  city: string | null
  address: string | null
  tier: string
  status: string
  commission_rate: number
  discount_percent: number
  credit_limit: number
  current_balance: number
  available_credit: number
  payment_terms_days: number
  currency: string
  last_login_at: string | null
}

export interface PortalLoginResponse {
  access_token: string
  token_type: string
  agent: PortalAgent
}

export interface PortalAccountSummary {
  agent: PortalAgent
  total_orders: number
  total_revenue: number
  pending_payments: number
  payment_due_date: string | null
}

export interface PortalProduct {
  id: string
  sku: string
  name: string
  description: string | null
  category: string | null
  brand: string | null
  wholesale_price: number
  retail_price: number | null
  moq: number
  currency: string
  in_stock: boolean
  stock_quantity: number
}

interface PortalProductList {
  items: PortalProduct[]
  total: number
}

export interface PortalRFQItem {
  id: string
  product_id: string
  sku_snapshot: string
  product_name_snapshot: string
  requested_quantity: number
  target_unit_price: number | null
  notes: string | null
}

export interface PortalRFQ {
  id: string
  rfq_number: string
  status: string
  source: string
  requested_currency: string
  destination_country: string | null
  incoterm: string | null
  requested_delivery_date: string | null
  notes: string | null
  submitted_at: string | null
  closed_at: string | null
  items: PortalRFQItem[]
  created_at: string
  updated_at: string
}

interface PortalRFQList {
  items: PortalRFQ[]
  total: number
}

export interface PortalQuoteItem {
  id: string
  product_id: string
  sku_snapshot: string
  product_name_snapshot: string
  quantity: number
  unit_price: number
  discount_percent: number
  line_subtotal: number
  line_total: number
  price_source: string
}

export interface PortalContractSummary {
  id: string
  contract_number: string
  status: string
  customer_signed_at: string | null
  company_signed_at: string | null
  activated_at: string | null
}

export interface PortalQuote {
  id: string
  quote_number: string
  version_number: number
  rfq_id: string | null
  rfq_number: string | null
  status: string
  currency: string
  valid_until: string
  payment_terms_days: number
  incoterm: string | null
  shipping_terms: string | null
  subtotal: number
  discount_amount: number
  shipping_cost: number
  tax_amount: number
  total: number
  sent_at: string | null
  accepted_at: string | null
  rejected_at: string | null
  rejection_reason: string | null
  notes: string | null
  items: PortalQuoteItem[]
  contract: PortalContractSummary | null
  created_at: string
  updated_at: string
}

interface PortalQuoteList {
  items: PortalQuote[]
  total: number
}

export interface PortalContract {
  id: string
  contract_number: string
  quote_id: string
  quote_number: string | null
  version_number: number | null
  status: string
  effective_from: string
  effective_to: string | null
  currency: string
  total: number
  document_url: string | null
  terms: Record<string, unknown>
  customer_signed_by: string | null
  customer_signed_at: string | null
  company_signed_at: string | null
  activated_at: string | null
  terminated_at: string | null
  items: PortalQuoteItem[]
  created_at: string
  updated_at: string
}

interface PortalContractList {
  items: PortalContract[]
  total: number
}

export interface PortalOrderItem {
  id: string
  product_id: string
  product_name: string
  sku: string
  quantity: number
  unit_price: number
  subtotal: number
}

export interface PortalOrder {
  id: string
  order_number: string
  status: string
  payment_status: string
  subtotal: number
  discount_amount: number
  shipping_cost: number
  total: number
  currency: string
  shipping_address: Record<string, unknown>
  payment_due_date: string | null
  tracking_number: string | null
  tracking_carrier: string | null
  notes: string | null
  items: PortalOrderItem[]
  created_at: string
  updated_at: string
}

interface PortalOrderList {
  items: PortalOrder[]
  total: number
}

export interface PortalOrderConversion {
  id: string
  order_number: string
  quote_id: string
  contract_id: string
  status: string
  payment_status: string
  total: number
  currency: string
}
