const API_BASE = '/api/v1'

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })
  if (!response.ok) {
    throw new Error(`API Error: ${response.status}`)
  }
  return response.json()
}

export const api = {
  // 经营看板
  getDashboardSummary: () => request('/dashboard/summary'),
  getKeyMetrics: () => request('/dashboard/key-metrics'),
  getProductPerformance: (limit = 10) => request(`/dashboard/product-performance?limit=${limit}`),

  // 经营预警
  getAlerts: (status?: string, severity?: string) => {
    const params = new URLSearchParams()
    if (status) params.set('alert_status', status)
    if (severity) params.set('severity', severity)
    return request(`/alerts?${params.toString()}`)
  },
  updateAlertStatus: (id: string, status: string, notes = '') =>
    request(`/alerts/${id}/status`, {
      method: 'PUT',
      body: JSON.stringify({ status, updated_by: 'admin', notes }),
    }),

  // 库存管理
  getWarehouses: () => request('/p3/inventory/warehouses'),
  createWarehouse: (data: any) =>
    request('/p3/inventory/warehouses', { method: 'POST', body: JSON.stringify(data) }),
  getWarehouseStatus: (id: string) => request(`/p3/inventory/warehouses/${id}`),

  // 选品
  getProducts: () => request('/sourcing/products'),

  // 采购
  getPurchaseOrders: () => request('/purchase-automation/orders'),

  // 物流
  getShipments: () => request('/logistics/shipments'),

  // 内容
  getContents: () => request('/content-generation/items'),

  // EDM
  getCampaigns: () => request('/edm/campaigns'),

  // 周报
  getWeeklyReports: () => request('/weekly-report'),

  // B2B
  getAgents: () => request('/p3/b2b/agents'),
  getB2BOrders: () => request('/p3/b2b/orders'),
}
