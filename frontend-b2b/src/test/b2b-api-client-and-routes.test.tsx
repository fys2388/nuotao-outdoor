/**
 * M2.6-G: API client behaviour + route-transition regression tests.
 *
 * Adds coverage ChatGPT required on top of the M2.5.6 public/portal suite:
 * - Portal API client: attaches Bearer auth, clears session + redirects on 401,
 *   surfaces server error detail, and reaches the correct endpoint.
 * - Route transitions: authenticated partner on the public root is forwarded to
 *   the wholesale portal; anonymous visitors stay on public routes.
 */
import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import App from '../App'
import { api, setToken, clearToken } from '../api/client'

function jsonResponse(body: unknown, ok = true, status = 200) {
  return {
    ok,
    status,
    json: async () => body,
  } as Response
}

beforeEach(() => {
  clearToken()
  window.history.pushState({}, '', '/')
  vi.restoreAllMocks()
})

afterEach(() => {
  vi.restoreAllMocks()
  clearToken()
})

// ---- Portal API client behaviour -------------------------------------------

describe('Portal API client behaviour', () => {
  it('attaches the Bearer token to authenticated requests', async () => {
    setToken('test-token-123')
    const fetchMock = vi.fn(async () =>
      jsonResponse({ items: [], total: 0, page: 1, page_size: 20 }),
    )
    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch)

    await api.getProducts()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toContain('/api/v1/b2b-portal/products')
    const headers = init.headers as Record<string, string>
    expect(headers['Authorization']).toBe('Bearer test-token-123')
  })

  it('sends no Authorization header when no token is stored', async () => {
    clearToken()
    const fetchMock = vi.fn(async () =>
      jsonResponse({ items: [], total: 0, page: 1, page_size: 20 }),
    )
    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch)

    await api.getProducts()

    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    const headers = init.headers as Record<string, string>
    expect(headers['Authorization']).toBeUndefined()
  })

  it('clears the stored token and redirects to /login on a 401 response', async () => {
    setToken('expired-token')
    // jsdom cannot perform real navigation; observe the redirect side effect by
    // stubbing window.location where possible.
    const originalLocation = window.location
    let redirectedTo: string | null = null
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        ...originalLocation,
        get href() {
          return redirectedTo ?? ''
        },
        set href(v: string) {
          redirectedTo = v
        },
      },
    })

    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ detail: 'Not authenticated' }, false, 401)) as unknown as typeof fetch,
    )

    await expect(api.getAccountSummary()).rejects.toThrow(/unauthorized/i)
    // Session is cleared so the next request will not re-send the stale token.
    expect(window.localStorage.getItem('b2b_token')).toBeNull()
    // Client forwards the user to the login route.
    expect(redirectedTo).toBe('/login')

    Object.defineProperty(window, 'location', { configurable: true, value: originalLocation })
  })

  it('surfaces the server-provided error detail on a non-401 failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse({ detail: 'Insufficient credit limit' }, false, 400),
      ) as unknown as typeof fetch,
    )

    await expect(
      api.createOrder([{ product_id: 'p1', quantity: 1 }]),
    ).rejects.toThrow('Insufficient credit limit')
  })

  it('logs in and returns the access token from the auth endpoint', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({ access_token: 'jwt-abc', token_type: 'bearer', agent: { id: 'a1' } }),
    )
    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch)

    const res = await api.login('buyer@example.com', 'secret')

    expect(res.access_token).toBe('jwt-abc')
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toContain('/api/v1/b2b-portal/auth/login')
    expect(init.method).toBe('POST')
  })
})

// ---- Route transitions -----------------------------------------------------

describe('Route transitions', () => {
  it('forwards an authenticated partner on the public root to the wholesale portal', async () => {
    // AuthProvider only calls getMe when a token is present, so seed one.
    setToken('valid-token')
    const agent = {
      id: 'agent-1',
      agent_number: 'AG-001',
      company_name: 'Acme Outdoor Retail',
      contact_name: 'Jane',
      email: 'jane@acme.com',
      phone: null,
      country: 'United States',
      city: null,
      address: null,
      tier: 'standard',
      status: 'approved',
      commission_rate: 0,
      discount_percent: 10,
      credit_limit: 50000,
      current_balance: 0,
      available_credit: 50000,
      payment_terms_days: 30,
      currency: 'USD',
      last_login_at: null,
    }
    const fetchMock = vi.fn(async (url: string) => {
      if (String(url).includes('/auth/me')) {
        return jsonResponse(agent)
      }
      // Portal product list (post-redirect).
      return jsonResponse({ items: [], total: 0, page: 1, page_size: 20 })
    })
    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch)

    window.history.pushState({}, '', '/')
    render(<App />)

    await waitFor(() => {
      expect(window.location.pathname).toBe('/portal/products')
    })
  })

  it('keeps an anonymous visitor on the public route (no portal access)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (String(url).includes('/auth/me')) {
          return jsonResponse({ detail: 'Not authenticated' }, false, 401)
        }
        if (String(url).includes('/b2b-showcase/')) {
          return jsonResponse({ items: [], total: 0, page: 1, page_size: 12 })
        }
        return jsonResponse({}, true)
      }) as unknown as typeof fetch,
    )

    window.history.pushState({}, '', '/about')
    render(<App />)

    // Stays on the public about route, not redirected into the portal.
    await waitFor(() => {
      expect(window.location.pathname).toBe('/about')
    })
  })
})