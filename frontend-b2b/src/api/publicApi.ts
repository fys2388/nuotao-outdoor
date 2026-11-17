// Public B2B showcase API (no auth, never sends token, never redirects on 401).
// Talks to the public, price-redacted catalogue + public lead submission.
// On the static Cloudflare Pages host there is no /api backend, so the
// production build points this at the public backend API on the console
// origin (admin.nuotaooutdoor.com), which nginx proxies to FastAPI.
const PUBLIC_API_BASE =
  import.meta.env.VITE_B2B_SHOWCASE_API || '/api/v1/b2b-showcase'

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
  submitLead: (data: Record<string, any>) => {
    // The public form uses friendlier field names; the backend schema expects
    // `email` / `country` and `products_of_interest` as a list. Map here so a
    // submission never fails validation on naming alone.
    const { business_email, country_region, products_of_interest, ...rest } = data
    const productsList = Array.isArray(products_of_interest)
      ? products_of_interest
      : products_of_interest
        ? String(products_of_interest)
            .split(',')
            .map((s) => s.trim())
            .filter(Boolean)
        : null
    return publicRequest<LeadSubmitResponse>('/leads', {
      method: 'POST',
      body: JSON.stringify({
        ...rest,
        email: business_email,
        country: country_region,
        products_of_interest: productsList,
      }),
    })
  },
}