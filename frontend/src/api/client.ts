export const ADMIN_TOKEN_KEY = 'admin_token'
export const ADMIN_REFRESH_TOKEN_KEY = 'admin_refresh_token'
export const API_BASE = '/api/v1'

export interface ImportAndAnalyzeData {
  import_id: string
  product_id: string
  source_url: string
  data_source?: string
  product_info: Record<string, any>
  ai_recognition: Record<string, any>
  product_report: Record<string, any>
  analysis_metadata?: Record<string, any>
}

export class ApiError extends Error {
  status: number
  detail: unknown
  traceId?: string

  constructor(message: string, status: number, detail?: unknown, traceId?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
    this.traceId = traceId
  }
}

interface RequestOptions extends RequestInit {
  timeoutMs?: number
}

export function getAccessToken(): string | null {
  return localStorage.getItem(ADMIN_TOKEN_KEY)
}

export function setAuthTokens(accessToken: string, refreshToken?: string): void {
  localStorage.setItem(ADMIN_TOKEN_KEY, accessToken)
  if (refreshToken) {
    localStorage.setItem(ADMIN_REFRESH_TOKEN_KEY, refreshToken)
  }
}

export function clearAuthTokens(): void {
  localStorage.removeItem(ADMIN_TOKEN_KEY)
  localStorage.removeItem(ADMIN_REFRESH_TOKEN_KEY)
}

function buildUrl(endpoint: string): string {
  if (endpoint.startsWith('/api/')) return endpoint
  return `${API_BASE}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`
}

function parseError(payload: unknown, fallback: string): string {
  if (typeof payload === 'string' && payload.trim()) return payload
  if (payload && typeof payload === 'object') {
    const record = payload as Record<string, unknown>
    const detail = record.detail
    if (typeof detail === 'string' && detail.trim()) return detail
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as Record<string, unknown>
      if (typeof first?.msg === 'string') return first.msg
    }
    if (typeof record.message === 'string' && record.message.trim()) return record.message
  }
  return fallback
}

export async function request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { timeoutMs = 30000, ...fetchOptions } = options
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  const token = getAccessToken()
  const isFormData = fetchOptions.body instanceof FormData
  const headers = new Headers(fetchOptions.headers)

  if (!isFormData && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  try {
    const response = await fetch(buildUrl(endpoint), {
      ...fetchOptions,
      headers,
      signal: controller.signal,
    })
    const contentType = response.headers.get('content-type') || ''
    const payload = contentType.includes('application/json')
      ? await response.json().catch(() => null)
      : await response.text().catch(() => '')

    if (!response.ok) {
      throw new ApiError(
        parseError(payload, `请求失败（HTTP ${response.status}）`),
        response.status,
        payload,
        response.headers.get('x-trace-id') || undefined,
      )
    }

    return payload as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError('请求超时，请检查网络或后端服务状态', 408)
    }
    throw new ApiError(error instanceof Error ? error.message : '网络请求失败', 0)
  } finally {
    window.clearTimeout(timer)
  }
}

export const api = {
  getDashboardSummary: (startDate?: string, endDate?: string) => {
    const params = new URLSearchParams()
    if (startDate) params.set('start_date', startDate)
    if (endDate) params.set('end_date', endDate)
    const query = params.toString()
    return request(`/dashboard/summary${query ? `?${query}` : ''}`)
  },
  getDashboardKeyMetrics: () => request('/dashboard/key-metrics'),
  getChannelPerformance: (
    startDate?: string,
    endDate?: string,
    currency?: string,
    reportingCurrency?: string,
  ) => {
    const params = new URLSearchParams()
    if (startDate) params.set('start_date', startDate)
    if (endDate) params.set('end_date', endDate)
    if (currency) params.set('currency', currency)
    if (reportingCurrency) params.set('reporting_currency', reportingCurrency)
    const query = params.toString()
    return request(`/analytics/channel-performance${query ? `?${query}` : ''}`)
  },
  getConsolidationReport: (params?: {
    startDate?: string
    endDate?: string
    reportingCurrency?: string
    brandId?: string
    legalEntityId?: string
  }) => {
    const query = new URLSearchParams()
    if (params?.startDate) query.set('start_date', params.startDate)
    if (params?.endDate) query.set('end_date', params.endDate)
    if (params?.reportingCurrency) {
      query.set('reporting_currency', params.reportingCurrency)
    }
    if (params?.brandId) query.set('brand_id', params.brandId)
    if (params?.legalEntityId) query.set('legal_entity_id', params.legalEntityId)
    return request(
      `/analytics/consolidation${query.size ? `?${query.toString()}` : ''}`,
    )
  },
  getBrands: () => request('/admin/consolidation/brands'),
  getProductBrandGaps: (search?: string) => {
    const query = new URLSearchParams()
    if (search) query.set('search', search)
    return request(
      `/admin/consolidation/product-brand-gaps${query.size ? `?${query.toString()}` : ''}`,
    )
  },
  bulkAssignProductBrands: (productIds: string[], brandId: string) =>
    request('/admin/consolidation/product-brands/bulk', {
      method: 'POST',
      body: JSON.stringify({ product_ids: productIds, brand_id: brandId }),
    }),
  createBrand: (data: {
    code: string
    name: string
    status?: string
    default_legal_entity_id?: string
    notes?: string
  }) =>
    request('/admin/consolidation/brands', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateBrand: (
    brandId: string,
    data: {
      name?: string
      status?: string
      default_legal_entity_id?: string
      notes?: string
    },
  ) =>
    request(`/admin/consolidation/brands/${brandId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  getLegalEntities: () => request('/admin/consolidation/legal-entities'),
  createLegalEntity: (data: {
    code: string
    name: string
    legal_name: string
    country: string
    functional_currency: string
    notes?: string
  }) =>
    request('/admin/consolidation/legal-entities', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  getCommerceAttributions: (params?: {
    entityType?: string
    eliminationStatus?: string
  }) => {
    const query = new URLSearchParams()
    if (params?.entityType) query.set('entity_type', params.entityType)
    if (params?.eliminationStatus) {
      query.set('elimination_status', params.eliminationStatus)
    }
    return request(
      `/admin/consolidation/attributions${query.size ? `?${query.toString()}` : ''}`,
    )
  },
  getAttributionGaps: (entityType?: string) => {
    const query = new URLSearchParams()
    if (entityType) query.set('entity_type', entityType)
    return request(
      `/admin/consolidation/attribution-gaps${query.size ? `?${query.toString()}` : ''}`,
    )
  },
  reconcileAttributionGaps: (entityType?: string) => {
    const query = new URLSearchParams()
    if (entityType) query.set('entity_type', entityType)
    return request(
      `/admin/consolidation/attribution-gaps/reconcile${
        query.size ? `?${query.toString()}` : ''
      }`,
      { method: 'POST' },
    )
  },
  upsertCommerceAttribution: (
    entityType: string,
    entityId: string,
    data: {
      brand_id: string
      legal_entity_id: string
      is_intercompany: boolean
      counterparty_legal_entity_id?: string
      evidence?: Record<string, unknown>
    },
  ) =>
    request(
      `/admin/consolidation/attributions/${entityType}/${entityId}`,
      {
        method: 'PUT',
        body: JSON.stringify(data),
      },
    ),
  approveElimination: (
    attributionId: string,
    eliminationAmount: string,
    evidence: Record<string, unknown> = {},
  ) =>
    request(
      `/admin/consolidation/attributions/${attributionId}/approve-elimination`,
      {
        method: 'POST',
        body: JSON.stringify({
          elimination_amount: eliminationAmount,
          evidence,
        }),
      },
    ),
  rejectElimination: (
    attributionId: string,
    evidence: Record<string, unknown> = {},
  ) =>
    request(
      `/admin/consolidation/attributions/${attributionId}/reject-elimination`,
      {
        method: 'POST',
        body: JSON.stringify({ evidence }),
      },
    ),
  getExchangeRates: (params?: {
    baseCurrency?: string
    quoteCurrency?: string
    asOf?: string
    limit?: number
  }) => {
    const query = new URLSearchParams()
    if (params?.baseCurrency) query.set('base_currency', params.baseCurrency)
    if (params?.quoteCurrency) query.set('quote_currency', params.quoteCurrency)
    if (params?.asOf) query.set('as_of', params.asOf)
    if (params?.limit) query.set('limit', String(params.limit))
    return request(`/admin/currency-rates${query.size ? `?${query.toString()}` : ''}`)
  },
  createExchangeRate: (data: {
    base_currency: string
    quote_currency: string
    rate: string
    effective_date: string
    source: string
    source_reference?: string
  }) =>
    request('/admin/currency-rates', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getAlerts: (status?: string, severity?: string) => {
    const params = new URLSearchParams()
    if (status) params.set('alert_status', status)
    if (severity) params.set('severity', severity)
    return request(`/alerts${params.size ? `?${params.toString()}` : ''}`)
  },
  updateAlertStatus: (id: string, status: string, notes = '') =>
    request(`/alerts/${id}/status`, {
      method: 'PUT',
      body: JSON.stringify({ status, notes }),
    }),

  getWarehouses: () => request('/inventory/warehouses'),
  createWarehouse: (data: Record<string, unknown>) =>
    request('/inventory/warehouses', { method: 'POST', body: JSON.stringify(data) }),
  getWarehouseStatus: (id: string) => request(`/inventory/warehouses/${id}`),

  getProducts: (limit = 100, offset = 0, status?: string, category?: string) => {
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
    })
    if (status) params.set('status', status)
    if (category) params.set('category', category)
    return request(`/products?${params.toString()}`)
  },
  deleteProduct: (productId: string) =>
    request<{ deleted: number; not_found: string[] }>(`/products/${productId}`, {
      method: 'DELETE',
    }),
  batchDeleteProducts: (productIds: string[]) =>
    request<{ deleted: number; not_found: string[] }>('/products/batch-delete', {
      method: 'POST',
      body: JSON.stringify({ product_ids: productIds }),
    }),
  getSourcingCandidates: (status = 'all', limit = 100, offset = 0) => {
    const params = new URLSearchParams({
      status,
      limit: String(limit),
      offset: String(offset),
    })
    return request(`/sourcing/candidates?${params.toString()}`)
  },
  intakeProduct: (data: Record<string, unknown>) =>
    request('/products/intake', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  analyzeProduct: (productId: string) =>
    request(`/products/${productId}/analyze`, { method: 'POST' }),
  getProductIntelligence: (productId: string) =>
    request(`/products/${productId}/intelligence`),
  getProductScoreEvidence: (scoreId: string) =>
    request(`/product-decisions/scores/${scoreId}/evidence`),
  getProductCostSnapshots: (productId: string) =>
    request(`/products/${productId}/cost-snapshots`),
  getCostOverview: (
    params: { search?: string; costStatus?: string; limit?: number; offset?: number } = {},
  ) => {
    const q = new URLSearchParams()
    if (params.search) q.set('search', params.search)
    if (params.costStatus) q.set('cost_status', params.costStatus)
    q.set('limit', String(params.limit ?? 200))
    q.set('offset', String(params.offset ?? 0))
    return request(`/products/cost-overview?${q.toString()}`)
  },
  saveProductCost: (productId: string, payload: Record<string, unknown>) =>
    request(`/products/${productId}/cost-snapshots`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getProfitAnalysis: (productId: string, salePrice?: number | string) => {
    const q = new URLSearchParams()
    if (salePrice !== undefined && salePrice !== null && salePrice !== '') {
      q.set('sale_price', String(salePrice))
    }
    const suffix = q.toString()
    return request(`/products/${productId}/profit-analysis${suffix ? `?${suffix}` : ''}`)
  },
  getProductSources: (productId: string) =>
    request(`/products/${productId}/sources`),
  generateProductCopy: (productId: string) =>
    request(`/products/${productId}/generate-copy`, { method: 'POST', timeoutMs: 120000 }),
  approveProductLocalization: (productId: string, language: string, actor = 'admin') =>
    request(`/products/${productId}/localizations/${language}/approve`, {
      method: 'POST',
      body: JSON.stringify({ actor }),
    }),
  getImageTasks: (productId?: string, limit = 50) => {
    const params = new URLSearchParams({ limit: String(limit) })
    if (productId) params.set('product_id', productId)
    return request(`/image-gen/tasks?${params.toString()}`)
  },
  generateProductImage: (data: {
    productId: string
    prompt: string
    useCase?: string
  }) =>
    request('/image-gen/generate', {
      method: 'POST',
      body: JSON.stringify({
        product_id: data.productId,
        prompt: data.prompt,
        use_case: data.useCase || 'main_image',
        model: 'wan2.7-image',
        width: 1024,
        height: 1024,
      }),
      timeoutMs: 300000,
    }),
  approveProductImage: (taskId: string, actor = 'admin') =>
    request(`/image-gen/tasks/${taskId}/approve`, {
      method: 'POST',
      body: JSON.stringify({ approved_by: actor }),
    }),
  rejectProductImage: (taskId: string) =>
    request(`/image-gen/tasks/${taskId}/reject`, {
      method: 'POST',
    }),
  attachProductImage: (
    productId: string,
    taskId: string,
    placement: 'main' | 'detail' = 'main',
    actor = 'admin',
  ) =>
    request(`/products/${productId}/media/approved-image`, {
      method: 'POST',
      body: JSON.stringify({ task_id: taskId, placement, actor }),
    }),
  updateProductCandidateStatus: (
    productId: string,
    data: { status: string; actor: string; note?: string },
  ) =>
    request(`/product-candidates/${productId}/status`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  promoteProductCandidate: (
    productId: string,
    data: { actor: string; note?: string },
  ) =>
    request(`/product-candidates/${productId}/promote`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  syncProductsFromWooCommerce: (perPage = 100) =>
    request(`/products/sync-woocommerce?per_page=${perPage}`, { method: 'POST' }),
  pushProductsToWooCommerce: (productIds: string[]) =>
    request('/products/push-woocommerce', {
      method: 'POST',
      body: JSON.stringify({ product_ids: productIds }),
    }),
  importAndAnalyzeFrom1688: (data: {
    url_or_id: string
    temperature?: number
    max_tokens?: number
  }) =>
    request('/product-pipeline/import-and-analyze-1688', {
      method: 'POST',
      body: JSON.stringify(data),
      timeoutMs: 420000,
    }),
  createImportAndAnalyzeFrom1688Job: (data: {
    url_or_id: string
    temperature?: number
    max_tokens?: number
  }) =>
    request<{
      success: boolean
      data: { job_id: string; status: string } | null
      error?: string | null
    }>('/product-pipeline/import-and-analyze-1688/jobs', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  getImportAndAnalyzeFrom1688Job: (jobId: string) =>
    request<{
      success: boolean
      data: {
        job_id: string
        status: 'pending' | 'running' | 'succeeded' | 'failed'
        data?: ImportAndAnalyzeData | null
        error?: string | null
      } | null
      error?: string | null
    }>(`/product-pipeline/import-and-analyze-1688/jobs/${jobId}`),

  getOrders: (
    limit = 100,
    offset = 0,
    status?: string,
    externalOrderId?: string,
  ) => {
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
    })
    if (status) params.set('status', status)
    if (externalOrderId) params.set('external_order_id', externalOrderId)
    return request(`/orders?${params.toString()}`)
  },
  getOrder: (orderId: string) => request(`/orders/${orderId}`),
  syncOrdersFromWooCommerce: (days = 30, maxOrders = 500) =>
    request(`/orders/sync-woocommerce?days=${days}&max_orders=${maxOrders}`, {
      method: 'POST',
      timeoutMs: 120000,
    }),

  getCustomerProfiles: (limit = 100, offset = 0, segment?: string, country?: string) => {
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
    })
    if (segment) params.set('segment', segment)
    if (country) params.set('country', country)
    return request(`/customer-profiles?${params.toString()}`)
  },
  getCustomerInteractions: (limit = 100, customerId?: string) => {
    const params = new URLSearchParams({ limit: String(limit) })
    if (customerId) params.set('customer_id', customerId)
    return request(`/customer-interactions?${params.toString()}`)
  },

  getPurchaseOrders: () => request('/purchase-automation/orders'),
  getSupplyPurchaseOrders: (limit = 100, offset = 0, status?: string) => {
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
    })
    if (status) params.set('status', status)
    return request(`/purchase-orders?${params.toString()}`)
  },
  createSupplyPurchaseOrder: (data: Record<string, unknown>) =>
    request('/purchase-orders', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  approveSupplyPurchaseOrder: (purchaseOrderId: string) =>
    request(`/purchase-orders/${purchaseOrderId}/approve`, { method: 'POST' }),
  orderSupplyPurchaseOrder: (purchaseOrderId: string) =>
    request(`/purchase-orders/${purchaseOrderId}/order`, { method: 'POST' }),
  partialReceiveSupplyPurchaseOrder: (purchaseOrderId: string) =>
    request(`/purchase-orders/${purchaseOrderId}/partial-receive`, { method: 'POST' }),
  receiveSupplyPurchaseOrder: (purchaseOrderId: string) =>
    request(`/purchase-orders/${purchaseOrderId}/receive`, { method: 'POST' }),
  cancelSupplyPurchaseOrder: (purchaseOrderId: string) =>
    request(`/purchase-orders/${purchaseOrderId}/cancel`, { method: 'POST' }),
  getSuppliers: (limit = 100, status?: string, search?: string) => {
    const params = new URLSearchParams({ limit: String(limit) })
    if (status) params.set('status', status)
    if (search) params.set('search', search)
    return request(`/suppliers?${params.toString()}`)
  },
  createSupplier: (data: Record<string, unknown>) =>
    request('/suppliers', { method: 'POST', body: JSON.stringify(data) }),
  getInventorySnapshots: (limit = 100, location?: string) => {
    const params = new URLSearchParams({ limit: String(limit) })
    if (location) params.set('location', location)
    return request(`/inventory-snapshots?${params.toString()}`)
  },
  getSupplyShipments: (limit = 100, status?: string, carrier?: string) => {
    const params = new URLSearchParams({ limit: String(limit) })
    if (status) params.set('status', status)
    if (carrier) params.set('carrier', carrier)
    return request(`/shipments?${params.toString()}`)
  },
  getShipments: () => request('/logistics/shipments'),
  getContents: () => request('/content-generation/items'),
  getCampaigns: (limit = 100, offset = 0, status?: string) => {
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
    })
    if (status) params.set('status', status)
    return request(`/campaigns?${params.toString()}`)
  },
  createCampaign: (data: Record<string, unknown>) =>
    request('/campaigns', { method: 'POST', body: JSON.stringify(data) }),
  getRefunds: (limit = 100, status?: string) => {
    const params = new URLSearchParams({ limit: String(limit) })
    if (status) params.set('status', status)
    return request(`/refunds?${params.toString()}`)
  },
  getRefundStats: () => request('/refund-cases/stats'),
  getWeeklyReports: () => request('/weekly-report'),

  getB2BStats: () => request('/admin/b2b/stats'),
  getB2BAgents: () => request('/admin/b2b/agents'),
  getB2BOrders: () => request('/admin/b2b/orders'),
  getB2BPrices: () => request('/admin/b2b/prices'),
  getB2BPriceBooks: () => request('/admin/b2b/price-books'),
  createB2BPriceBook: (data: Record<string, unknown>) =>
    request('/admin/b2b/price-books', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  getB2BPriceVersions: (priceBookId: string) =>
    request(`/admin/b2b/price-books/${priceBookId}/versions`),
  createB2BPriceVersion: (priceBookId: string, data: Record<string, unknown>) =>
    request(`/admin/b2b/price-books/${priceBookId}/versions`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  getB2BPriceVersion: (priceVersionId: string) =>
    request(`/admin/b2b/price-versions/${priceVersionId}`),
  createB2BPriceTier: (priceVersionId: string, data: Record<string, unknown>) =>
    request(`/admin/b2b/price-versions/${priceVersionId}/tiers`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateB2BPriceTier: (priceTierId: string, data: Record<string, unknown>) =>
    request(`/admin/b2b/price-tiers/${priceTierId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  deleteB2BPriceTier: (priceTierId: string) =>
    request(`/admin/b2b/price-tiers/${priceTierId}`, { method: 'DELETE' }),
  submitB2BPriceVersion: (priceVersionId: string) =>
    request(`/admin/b2b/price-versions/${priceVersionId}/submit`, {
      method: 'POST',
    }),
  approveB2BPriceVersion: (priceVersionId: string) =>
    request(`/admin/b2b/price-versions/${priceVersionId}/approve`, {
      method: 'POST',
    }),
  rejectB2BPriceVersion: (priceVersionId: string, reason: string) =>
    request(`/admin/b2b/price-versions/${priceVersionId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  previewB2BPrice: (productId: string, agentId: string, quantity: number, asOf?: string) => {
    const params = new URLSearchParams({
      product_id: productId,
      agent_id: agentId,
      quantity: String(quantity),
    })
    if (asOf) params.set('as_of', asOf)
    return request(`/admin/b2b/price-resolution/preview?${params.toString()}`)
  },
  getB2BRFQs: (page = 1, pageSize = 50, status?: string) => {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    })
    if (status) params.set('status', status)
    return request(`/admin/b2b/rfqs?${params.toString()}`)
  },
  createB2BRFQ: (data: Record<string, unknown>) =>
    request('/admin/b2b/rfqs', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateB2BRFQStatus: (rfqId: string, status: string, reason?: string) =>
    request(`/admin/b2b/rfqs/${rfqId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status, reason }),
    }),
  createB2BQuoteFromRFQ: (rfqId: string, data: Record<string, unknown>) =>
    request(`/admin/b2b/rfqs/${rfqId}/quotes`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  getB2BQuotes: (page = 1, pageSize = 50, status?: string) => {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    })
    if (status) params.set('status', status)
    return request(`/admin/b2b/quotes?${params.toString()}`)
  },
  getB2BQuote: (quoteId: string) => request(`/admin/b2b/quotes/${quoteId}`),
  createB2BQuoteVersion: (
    quoteId: string,
    data: Record<string, unknown>,
  ) =>
    request(`/admin/b2b/quotes/${quoteId}/versions`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateB2BQuoteStatus: (quoteId: string, status: string, reason?: string) =>
    request(`/admin/b2b/quotes/${quoteId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status, reason }),
    }),
  createB2BContractFromQuote: (
    quoteId: string,
    data: Record<string, unknown>,
  ) =>
    request(`/admin/b2b/quotes/${quoteId}/contracts`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  convertB2BQuoteToOrder: (quoteId: string) =>
    request(`/admin/b2b/quotes/${quoteId}/convert-to-order`, {
      method: 'POST',
    }),
  getB2BContracts: (page = 1, pageSize = 50, status?: string) => {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    })
    if (status) params.set('status', status)
    return request(`/admin/b2b/contracts?${params.toString()}`)
  },
  updateB2BContractStatus: (
    contractId: string,
    status: string,
    reason?: string,
  ) =>
    request(`/admin/b2b/contracts/${contractId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status, reason }),
    }),
  signB2BContract: (
    contractId: string,
    party: 'customer' | 'company',
    signedBy: string,
  ) =>
    request(`/admin/b2b/contracts/${contractId}/sign`, {
      method: 'POST',
      body: JSON.stringify({ party, signed_by: signedBy }),
    }),
  getB2BInvoices: (page = 1, pageSize = 100, status?: string, agentId?: string) => {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    })
    if (status) params.set('status', status)
    if (agentId) params.set('agent_id', agentId)
    return request(`/admin/b2b/invoices?${params.toString()}`)
  },
  createB2BInvoice: (data: Record<string, unknown>) =>
    request('/admin/b2b/invoices', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  issueB2BInvoice: (invoiceId: string) =>
    request(`/admin/b2b/invoices/${invoiceId}/issue`, { method: 'POST' }),
  writeOffB2BInvoice: (invoiceId: string, data: Record<string, unknown>) =>
    request(`/admin/b2b/invoices/${invoiceId}/write-off`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  getB2BReceipts: (page = 1, pageSize = 100, status?: string, agentId?: string) => {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    })
    if (status) params.set('status', status)
    if (agentId) params.set('agent_id', agentId)
    return request(`/admin/b2b/receipts?${params.toString()}`)
  },
  createB2BReceipt: (data: Record<string, unknown>) =>
    request('/admin/b2b/receipts', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  allocateB2BReceipt: (receiptId: string, data: Record<string, unknown>) =>
    request(`/admin/b2b/receipts/${receiptId}/allocate`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  getB2BReceivables: (overdueOnly = false, agentId?: string) => {
    const params = new URLSearchParams({
      page: '1',
      page_size: '200',
      overdue_only: String(overdueOnly),
    })
    if (agentId) params.set('agent_id', agentId)
    return request(`/admin/b2b/receivables?${params.toString()}`)
  },
  getB2BReceivableStats: () => request('/admin/b2b/receivables/stats'),
  getB2BAgreements: (
    page = 1,
    pageSize = 50,
    status?: string,
    agentId?: string,
    search?: string,
  ) => {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    })
    if (status) params.set('status', status)
    if (agentId) params.set('agent_id', agentId)
    if (search) params.set('search', search)
    return request(`/admin/b2b/agreements?${params.toString()}`)
  },
  getB2BAgreement: (agreementId: string) =>
    request(`/admin/b2b/agreements/${agreementId}`),
  createB2BAgreement: (data: Record<string, unknown>) =>
    request('/admin/b2b/agreements', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateB2BAgreement: (agreementId: string, data: Record<string, unknown>) =>
    request(`/admin/b2b/agreements/${agreementId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  createB2BAgreementTier: (
    agreementId: string,
    data: Record<string, unknown>,
  ) =>
    request(`/admin/b2b/agreements/${agreementId}/tiers`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateB2BAgreementTier: (
    agreementId: string,
    tierId: string,
    data: Record<string, unknown>,
  ) =>
    request(`/admin/b2b/agreements/${agreementId}/tiers/${tierId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  deleteB2BAgreementTier: (agreementId: string, tierId: string) =>
    request(`/admin/b2b/agreements/${agreementId}/tiers/${tierId}`, {
      method: 'DELETE',
    }),
  submitB2BAgreement: (agreementId: string) =>
    request(`/admin/b2b/agreements/${agreementId}/submit`, {
      method: 'POST',
    }),
  approveB2BAgreement: (agreementId: string) =>
    request(`/admin/b2b/agreements/${agreementId}/approve`, {
      method: 'POST',
    }),
  rejectB2BAgreement: (agreementId: string, reason: string) =>
    request(`/admin/b2b/agreements/${agreementId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  terminateB2BAgreement: (agreementId: string, reason: string) =>
    request(`/admin/b2b/agreements/${agreementId}/terminate`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  getB2BAgreementProgress: (agreementId: string, asOf?: string) => {
    const params = new URLSearchParams()
    if (asOf) params.set('as_of', asOf)
    return request(
      `/admin/b2b/agreements/${agreementId}/progress${
        params.size ? `?${params.toString()}` : ''
      }`,
    )
  },
  getB2BRebateAccruals: (
    page = 1,
    pageSize = 200,
    status?: string,
    agreementId?: string,
    agentId?: string,
  ) => {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    })
    if (status) params.set('status', status)
    if (agreementId) params.set('agreement_id', agreementId)
    if (agentId) params.set('agent_id', agentId)
    return request(`/admin/b2b/rebate-accruals?${params.toString()}`)
  },
  calculateB2BRebateAccrual: (
    agreementId: string,
    data: Record<string, unknown>,
  ) =>
    request(`/admin/b2b/agreements/${agreementId}/rebate-accruals`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  submitB2BRebateAccrual: (accrualId: string) =>
    request(`/admin/b2b/rebate-accruals/${accrualId}/submit`, {
      method: 'POST',
    }),
  approveB2BRebateAccrual: (accrualId: string) =>
    request(`/admin/b2b/rebate-accruals/${accrualId}/approve`, {
      method: 'POST',
    }),
  rejectB2BRebateAccrual: (accrualId: string, reason: string) =>
    request(`/admin/b2b/rebate-accruals/${accrualId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  settleB2BRebateAccrual: (
    accrualId: string,
    settlementReference: string,
  ) =>
    request(`/admin/b2b/rebate-accruals/${accrualId}/settle`, {
      method: 'POST',
      body: JSON.stringify({ settlement_reference: settlementReference }),
    }),

  getB2BCreditPolicies: () =>
    request('/admin/b2b/credit/policies'),
  createB2BCreditPolicy: (data: Record<string, unknown>) =>
    request('/admin/b2b/credit/policies', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  submitB2BCreditPolicy: (policyId: string) =>
    request(`/admin/b2b/credit/policies/${policyId}/submit`, {
      method: 'POST',
    }),
  approveB2BCreditPolicy: (policyId: string) =>
    request(`/admin/b2b/credit/policies/${policyId}/approve`, {
      method: 'POST',
    }),
  rejectB2BCreditPolicy: (policyId: string, reason: string) =>
    request(`/admin/b2b/credit/policies/${policyId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  getB2BCreditRisks: (limit = 200) =>
    request(`/admin/b2b/credit/risks?limit=${limit}`),
  getB2BCreditAgent: (agentId: string) =>
    request(`/admin/b2b/credit/agents/${agentId}`),
  assessB2BCreditAgent: (agentId: string) =>
    request(`/admin/b2b/credit/agents/${agentId}/assess`, {
      method: 'POST',
    }),
  updateB2BCreditAgentStatus: (
    agentId: string,
    status: 'normal' | 'watch' | 'hold' | 'frozen',
    reason: string,
  ) =>
    request(`/admin/b2b/credit/agents/${agentId}/status`, {
      method: 'POST',
      body: JSON.stringify({ status, reason }),
    }),
  getB2BCreditAgentHistory: (agentId: string, limit = 100) =>
    request(`/admin/b2b/credit/agents/${agentId}/history?limit=${limit}`),
  getB2BCreditInsurance: (agentId?: string) => {
    const params = new URLSearchParams()
    if (agentId) params.set('agent_id', agentId)
    return request(
      `/admin/b2b/credit/insurance${
        params.size ? `?${params.toString()}` : ''
      }`,
    )
  },
  createB2BCreditInsurance: (data: Record<string, unknown>) =>
    request('/admin/b2b/credit/insurance', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateB2BCreditInsurance: (
    policyId: string,
    data: Record<string, unknown>,
  ) =>
    request(`/admin/b2b/credit/insurance/${policyId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  getB2BCreditClaims: (status?: string, agentId?: string) => {
    const params = new URLSearchParams()
    if (status) params.set('status', status)
    if (agentId) params.set('agent_id', agentId)
    return request(
      `/admin/b2b/credit/claims${
        params.size ? `?${params.toString()}` : ''
      }`,
    )
  },
  createB2BCreditClaim: (data: Record<string, unknown>) =>
    request('/admin/b2b/credit/claims', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  submitB2BCreditClaim: (claimId: string) =>
    request(`/admin/b2b/credit/claims/${claimId}/submit`, {
      method: 'POST',
    }),
  approveB2BCreditClaim: (claimId: string) =>
    request(`/admin/b2b/credit/claims/${claimId}/approve`, {
      method: 'POST',
    }),
  rejectB2BCreditClaim: (claimId: string, reason: string) =>
    request(`/admin/b2b/credit/claims/${claimId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  settleB2BCreditClaim: (
    claimId: string,
    recoveredAmount: number | null,
    settlementReference: string,
  ) =>
    request(`/admin/b2b/credit/claims/${claimId}/settle`, {
      method: 'POST',
      body: JSON.stringify({
        recovered_amount: recoveredAmount,
        settlement_reference: settlementReference,
      }),
    }),

  getCustomerDataStats: () => request('/admin/customer-data/stats'),
  getCustomerAccounts: (params?: {
    status?: string
    businessModel?: string
    limit?: number
  }) => {
    const query = new URLSearchParams()
    if (params?.status) query.set('status', params.status)
    if (params?.businessModel) query.set('business_model', params.businessModel)
    if (params?.limit) query.set('limit', String(params.limit))
    return request(
      `/admin/customer-data/accounts${query.size ? `?${query.toString()}` : ''}`,
    )
  },
  resolveCustomerIdentity: (data: Record<string, unknown>) =>
    request('/admin/customer-data/identities/resolve', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  linkCustomerIdentity: (data: Record<string, unknown>) =>
    request('/admin/customer-data/identities', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  getCustomerIdentities: (params?: {
    status?: string
    customerAccountId?: string
    limit?: number
  }) => {
    const query = new URLSearchParams()
    if (params?.status) query.set('status', params.status)
    if (params?.customerAccountId) {
      query.set('customer_account_id', params.customerAccountId)
    }
    if (params?.limit) query.set('limit', String(params.limit))
    return request(
      `/admin/customer-data/identities${query.size ? `?${query.toString()}` : ''}`,
    )
  },
  getCustomerMerges: (status?: string) => {
    const query = new URLSearchParams()
    if (status) query.set('status', status)
    return request(
      `/admin/customer-data/merges${query.size ? `?${query.toString()}` : ''}`,
    )
  },
  createCustomerMerge: (data: {
    source_account_id: string
    target_account_id: string
    reason: string
  }) =>
    request('/admin/customer-data/merges', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  approveCustomerMerge: (mergeId: string, reason?: string) =>
    request(`/admin/customer-data/merges/${mergeId}/approve`, {
      method: 'POST',
      body: JSON.stringify({ reason: reason || null }),
    }),
  rejectCustomerMerge: (mergeId: string, reason: string) =>
    request(`/admin/customer-data/merges/${mergeId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  completeCustomerMerge: (mergeId: string) =>
    request(`/admin/customer-data/merges/${mergeId}/complete`, {
      method: 'POST',
    }),
  getCustomerConsentSummary: (customerAccountId: string) =>
    request(
      `/admin/customer-data/consent?customer_account_id=${customerAccountId}`,
    ),
  getCustomerConsentHistory: (
    customerAccountId: string,
    params?: { purpose?: string; channel?: string; limit?: number },
  ) => {
    const query = new URLSearchParams({
      customer_account_id: customerAccountId,
    })
    if (params?.purpose) query.set('purpose', params.purpose)
    if (params?.channel) query.set('channel', params.channel)
    if (params?.limit) query.set('limit', String(params.limit))
    return request(
      `/admin/customer-data/consent/history?${query.toString()}`,
    )
  },
  appendCustomerConsent: (data: Record<string, unknown>) =>
    request('/admin/customer-data/consent/events', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  getDataSubjectRequests: (params?: {
    status?: string
    requestType?: string
    limit?: number
  }) => {
    const query = new URLSearchParams()
    if (params?.status) query.set('status', params.status)
    if (params?.requestType) query.set('request_type', params.requestType)
    if (params?.limit) query.set('limit', String(params.limit))
    return request(
      `/admin/customer-data/requests${query.size ? `?${query.toString()}` : ''}`,
    )
  },
  createDataSubjectRequest: (data: Record<string, unknown>) =>
    request('/admin/customer-data/requests', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  getDataSubjectRequest: (requestId: string) =>
    request(`/admin/customer-data/requests/${requestId}`),
  verifyDataSubjectRequest: (
    requestId: string,
    data: { verification_method: string; note?: string | null },
  ) =>
    request(`/admin/customer-data/requests/${requestId}/verify`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  approveDataSubjectRequest: (requestId: string, note?: string | null) =>
    request(`/admin/customer-data/requests/${requestId}/approve`, {
      method: 'POST',
      body: JSON.stringify({ note: note || null }),
    }),
  rejectDataSubjectRequest: (requestId: string, reason: string) =>
    request(`/admin/customer-data/requests/${requestId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  cancelDataSubjectRequest: (requestId: string, note?: string | null) =>
    request(`/admin/customer-data/requests/${requestId}/cancel`, {
      method: 'POST',
      body: JSON.stringify({ note: note || null }),
    }),
  executeDataSubjectRequest: (requestId: string, note?: string | null) =>
    request(`/admin/customer-data/requests/${requestId}/execute`, {
      method: 'POST',
      body: JSON.stringify({ note: note || null }),
    }),

  getNewtonStatus: () => request('/newton/status'),
  getNewtonModels: () => request('/newton/models'),
  getNewtonPoints: () => request('/newton/points'),
  createNewtonTask: (message: string, auto = true, model?: string) =>
    request('/newton/tasks', { method: 'POST', body: JSON.stringify({ message, auto, model }) }),
  getNewtonTask: (taskId: string) => request(`/newton/tasks/${taskId}`),
  newtonSearch: (
    query: string,
    minPrice?: number,
    maxPrice?: number,
    minOrderQty?: number,
    category?: string,
  ) =>
    request('/newton/search', {
      method: 'POST',
      body: JSON.stringify({
        query,
        min_price: minPrice,
        max_price: maxPrice,
        min_order_qty: minOrderQty,
        category,
      }),
    }),
  newtonBatchInquiry: (productIds: string[], inquiryMessage: string) =>
    request('/newton/inquiry', {
      method: 'POST',
      body: JSON.stringify({ product_ids: productIds, inquiry_message: inquiryMessage }),
    }),
  importNewtonSourcing: (
    products: Record<string, unknown>[],
    sourcingId = '',
    sourceQuery = '',
  ) =>
    request('/newton/sourcing/import', {
      method: 'POST',
      body: JSON.stringify({
        products,
        sourcing_id: sourcingId,
        source_query: sourceQuery,
      }),
    }),
  getNewtonCostDaily: () => request('/newton/cost/daily'),
  getNewtonCostAlerts: () => request('/newton/cost/alerts'),
  getNewtonCostCredits: () => request('/newton/cost/credits'),
}
