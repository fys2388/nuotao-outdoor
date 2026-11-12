/**
 * M2.5.6: frontend automated tests (Vitest + React Testing Library).
 *
 * Coverage per spec:
 * - Public catalogue renders approved products, never prices, never internal fields.
 * - Request-a-Quote form: required-field + privacy-consent validation, success only
 *   after a server-persistence response, and an explicit API-failure state.
 * - Portal: protected routes redirect anonymous visitors to login.
 */
import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from '../App'
import PublicCatalog from '../pages/public/PublicCatalog'
import RequestQuote from '../pages/public/RequestQuote'

// ---- fetch mocking helpers -------------------------------------------------

function jsonResponse(body: unknown, ok = true, status = 200) {
  return {
    ok,
    status,
    json: async () => body,
  } as Response
}

const SAMPLE_PRODUCTS = [
  {
    slug: 'alpine-tent',
    title: 'Alpine Four-Season Tent',
    images: ['https://example.com/tent.jpg'],
    category: 'Tents',
    description: 'A rugged four-season expedition tent.',
    specifications: { capacity: '4' },
    enquiry_cta_context: { product: 'alpine-tent' },
  },
]

function mockPublicCatalogFetch() {
  return vi.fn(async (url: string) => {
    if (String(url).includes('/b2b-showcase/categories')) {
      return jsonResponse([{ slug: 'tents', name: 'Tents', product_count: 1 }])
    }
    if (String(url).includes('/b2b-showcase/products')) {
      return jsonResponse({
        items: SAMPLE_PRODUCTS,
        total: 1,
        page: 1,
        page_size: 12,
      })
    }
    return jsonResponse({}, true, 200)
  }) as unknown as typeof fetch
}

beforeEach(() => {
  window.history.pushState({}, '', '/')
})
afterEach(() => {
  vi.restoreAllMocks()
})

// ---- Public catalogue ------------------------------------------------------

describe('Public catalogue (no-price showcase)', () => {
  it('renders approved products without any price or internal fields', async () => {
    vi.stubGlobal('fetch', mockPublicCatalogFetch())
    render(<PublicCatalog />)

    // Approved product is visible.
    expect(await screen.findByText('Alpine Four-Season Tent')).toBeInTheDocument()

    // No actual PRICE amount is rendered anywhere (currency symbol + digits).
    const body = document.body.textContent ?? ''
    expect(body).not.toMatch(/[$€£]\s?\d/)

    // The public product payload/render must not include internal procurement
    // fields (cost, margin, stock, internal SKU, supplier). We assert no such
    // field LABEL is rendered for the product.
    for (const internalLabel of ['Cost:', 'Margin:', 'Stock:', 'SKU:', 'Supplier:']) {
      expect(body).not.toContain(internalLabel)
    }

    // Defensive: the mock product intentionally carries no price/internal keys,
    // so nothing numeric-looking priced can leak into the card.
    const card = screen.getByText('Alpine Four-Season Tent').closest('.ant-card')
    expect(card).toBeTruthy()
    expect((card as HTMLElement).textContent).not.toMatch(/[$€£]\s?\d/)
  })
})

// ---- Request-a-Quote form --------------------------------------------------

describe('Request a Quote form', () => {
  it('blocks submission and shows validation errors when required fields are empty', async () => {
    vi.stubGlobal('fetch', vi.fn())
    render(<RequestQuote />)

    const submit = await screen.findByRole('button', { name: /submit/i })
    await userEvent.click(submit)

    // Required-field validation messages appear (company, name, email, country...).
    expect(await screen.findByText(/please enter your company name/i)).toBeInTheDocument()
    expect(await screen.findByText(/please enter your name/i)).toBeInTheDocument()
    // Privacy consent is mandatory.
    expect(await screen.findByText(/privacy/i)).toBeInTheDocument()
    // No submission request was made because validation failed.
    expect(fetch).not.toHaveBeenCalled()
  })

  it('shows a success state with a reference number only after the server confirms', async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (String(url).includes('/b2b-showcase/leads')) {
        return jsonResponse({
          success: true,
          reference_number: 'LD-20261112-ABC123',
          message: 'Thank you.',
        })
      }
      return jsonResponse({}, true)
    })
    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch)
    render(<RequestQuote />)

    await userEvent.type(await screen.findByPlaceholderText(/your company name/i), 'Acme Retail')
    await userEvent.type(await screen.findByPlaceholderText(/your full name/i), 'Jane Doe')
    await userEvent.type(await screen.findByPlaceholderText(/you@company\.com/i), 'jane@acme.com')
    await userEvent.type(await screen.findByPlaceholderText(/united states/i), 'United States')

    // Select business type from the antd Select.
    const bizSelect = screen.getAllByRole('combobox')[0]
    await userEvent.click(bizSelect)
    await userEvent.click(await screen.findByText('Retailer'))

    await userEvent.type(screen.getByLabelText(/products of interest/i), 'alpine-tent')
    await userEvent.type(screen.getByLabelText(/message/i), 'We want wholesale pricing.')

    // Tick the mandatory privacy consent checkbox.
    const consent = screen.getByRole('checkbox')
    await userEvent.click(consent)

    await userEvent.click(screen.getByRole('button', { name: /submit/i }))

    // Success screen with the server-issued reference number.
    expect(await screen.findByText(/enquiry submitted/i)).toBeInTheDocument()
    expect(await screen.findByText('LD-20261112-ABC123')).toBeInTheDocument()
  })

  it('surfaces an explicit error state when the API submission fails', async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (String(url).includes('/b2b-showcase/leads')) {
        return jsonResponse({ detail: 'Server exploded' }, false, 500)
      }
      return jsonResponse({}, true)
    })
    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch)
    render(<RequestQuote />)

    await userEvent.type(await screen.findByPlaceholderText(/your company name/i), 'Acme')
    await userEvent.type(await screen.findByPlaceholderText(/your full name/i), 'Jane')
    await userEvent.type(await screen.findByPlaceholderText(/you@company\.com/i), 'jane@acme.com')
    await userEvent.type(await screen.findByPlaceholderText(/united states/i), 'USA')
    await userEvent.click(screen.getAllByRole('combobox')[0])
    await userEvent.click(await screen.findByText('Retailer'))
    await userEvent.type(screen.getByLabelText(/products of interest/i), 'alpine-tent')
    await userEvent.type(screen.getByLabelText(/message/i), 'Hello.')
    await userEvent.click(screen.getByRole('checkbox'))
    await userEvent.click(screen.getByRole('button', { name: /submit/i }))

    expect(await screen.findByText(/submission failed/i)).toBeInTheDocument()
    // Must NOT show the success screen.
    expect(screen.queryByText(/enquiry submitted/i)).not.toBeInTheDocument()
  })
})

// ---- Portal protected route ------------------------------------------------

describe('Portal route protection', () => {
  it('redirects anonymous visitors on a /portal/* route to login', async () => {
    // Anonymous: auth "me" lookup fails with 401 -> no partner session.
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ detail: 'Not authenticated' }, false, 401)) as unknown as typeof fetch,
    )
    window.history.pushState({}, '', '/portal/products')
    render(<App />)

    // Unauthenticated users are shown the login gate, not the wholesale catalogue.
    await waitFor(() => {
      expect(screen.queryByText(/sign in|login/i)).toBeTruthy()
    })
    expect(screen.queryByText('Alpine Four-Season Tent')).not.toBeInTheDocument()
  })
})