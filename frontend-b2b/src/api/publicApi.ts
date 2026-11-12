// Public B2B showcase API (no auth, never sends token, never redirects on 401).
// Talks to the public, price-redacted catalogue + public lead submission.
const PUBLIC_API_BASE = '/api/v1/b2b-showcase'

// SPA navigation for the public showcase (same history-routing approach as the portal).
export function navigate(path: string) {
  const url = path.startsWith('/') ? path : '/' + path
  window.history.pushState({}, '', url)
  window.dispatchEvent(new PopStateEvent('popstate'))
}

async function publicRequest<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }
  const response = await fetch(`${PUBLIC_API_BASE}${endpoint}`, { ...options, headers })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(data.detail || `API Error: ${response.status}`)
  }
  return response.json()
}

// Public catalogue product — allowlisted fields only, never any price/cost/stock/SKU.
export interface PublicProduct {
  slug: string
  title: string
  images: string[]
  category: string | null
  description: string | null
  specifications: Record<string, any> | null
  enquiry_cta_context: Record<string, any> | null
}

export interface PublicProductListResponse {
  items: PublicProduct[]
  total: number
  page: number
  page_size: number
}

export interface PublicCategory {
  slug: string
  name: string
  product_count: number
}

export interface LeadSubmitResponse {
  success: boolean
  reference_number: string
  message: string
}

export const publicApi = {
  getCategories: () => publicRequest<PublicCategory[]>('/categories'),
  getProducts: (page = 1, pageSize = 20, category?: string) => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
    if (category) params.set('category', category)
    return publicRequest<PublicProductListResponse>(`/products?${params.toString()}`)
  },
  getProduct: (slug: string) => publicRequest<PublicProduct>(`/products/${slug}`),
  submitLead: (data: Record<string, any>) =>
    publicRequest<LeadSubmitResponse>('/leads', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
}