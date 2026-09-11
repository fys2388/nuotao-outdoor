const API_BASE = '/api/v1/b2b-portal'

function getToken(): string | null {
  return localStorage.getItem('b2b_token')
}

export function setToken(token: string) {
  localStorage.setItem('b2b_token', token)
}

export function clearToken() {
  localStorage.removeItem('b2b_token')
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  })

  if (response.status === 401) {
    clearToken()
    window.location.href = '/login'
    throw new Error('Unauthorized')
  }

  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(data.detail || `API Error: ${response.status}`)
  }
  return response.json()
}

export interface AgentProfile {
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

export interface Product {
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
  images: string[]
  attributes: Record<string, any>
  weight_kg?: number | null
  dimensions?: Record<string, any> | null
}

export interface ProductListResponse {
  items: Product[]
  total: number
  page: number
  page_size: number
}

export interface OrderItem {
  id: string
  product_id: string
  product_name: string
  sku: string
  quantity: number
  unit_price: number
  subtotal: number
}

export interface Order {
  id: string
  order_number: string
  status: string
  payment_status: string
  subtotal: number
  discount_amount: number
  shipping_cost: number
  total: number
  currency: string
  shipping_address: Record<string, any>
  payment_due_date: string | null
  tracking_number: string | null
  tracking_carrier: string | null
  notes: string | null
  items: OrderItem[]
  created_at: string
  updated_at: string
}

export interface OrderListResponse {
  items: Order[]
  total: number
  page: number
  page_size: number
}

export interface AccountSummary {
  agent: AgentProfile
  total_orders: number
  total_revenue: number
  pending_payments: number
  payment_due_date: string | null
}

export const api = {
  // Auth
  login: (email: string, password: string) =>
    request<{ access_token: string; token_type: string; agent: AgentProfile }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  getMe: () => request<AgentProfile>('/auth/me'),
  changePassword: (oldPassword: string, newPassword: string) =>
    request('/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
    }),

  // Applications (public)
  submitApplication: (data: Record<string, any>) =>
    request<{ id: string; email: string; company_name: string; status: string; message: string }>(
      '/applications',
      { method: 'POST', body: JSON.stringify(data) },
    ),

  // Products
  getProducts: (page = 1, pageSize = 20, search?: string, category?: string, inStockOnly = false) => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
    if (search) params.set('search', search)
    if (category) params.set('category', category)
    if (inStockOnly) params.set('in_stock_only', 'true')
    return request<ProductListResponse>(`/products?${params.toString()}`)
  },
  getProduct: (id: string) => request<Product>(`/products/${id}`),

  // Orders
  createOrder: (items: { product_id: string; quantity: number }[], shippingAddress?: Record<string, any>, notes?: string) =>
    request<Order>('/orders', {
      method: 'POST',
      body: JSON.stringify({ items, shipping_address: shippingAddress, notes }),
    }),
  getOrders: (page = 1, pageSize = 20, status?: string) => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
    if (status) params.set('status', status)
    return request<OrderListResponse>(`/orders?${params.toString()}`)
  },
  getOrder: (id: string) => request<Order>(`/orders/${id}`),

  // Account
  getAccountSummary: () => request<AccountSummary>('/account/summary'),
}
