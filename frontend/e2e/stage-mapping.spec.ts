import { expect, test } from '@playwright/test'

/**
 * Stage Mapping Unit Tests
 * 
 * Tests the deriveUserStage() priority state machine.
 * Terminal states MUST be checked before intermediate states.
 */

// ── Priority order (terminal → intermediate → fallback) ─────────────
// rejected > wc_published > listing > pending_approval
//           > approved > product_master > analysis > candidate > unknown

// Replicate the deriveUserStage logic from ProductDecisionCockpit.tsx
function deriveUserStage(product: {
  candidate_status?: string | null
  funnel_stage?: string | null
  mastered_at?: string | null
  wc_status?: string | null
  listing_status?: string | null
}): string {
  // 1. Terminal: rejected
  if (product.candidate_status === 'rejected') return 'rejected'
  
  // 2. Terminal: WC Published
  if (product.wc_status === 'synced') return 'wc_published'
  
  // 3. Intermediate: Listing in progress
  if (product.listing_status && ['pending', 'approved', 'processing'].includes(product.listing_status)) {
    return 'listing'
  }
  
  // 4. Intermediate: Approved (with mastered_at)
  if (product.candidate_status === 'approved' && product.mastered_at) {
    return 'approved'
  }
  
  // 5. Intermediate: Product Master
  if (product.mastered_at) return 'product_master'
  
  // 6. Intermediate: AI Analysis
  if (product.funnel_stage && ['recalled', 'screened', 'deep_candidate'].includes(product.funnel_stage)) {
    return 'analysis'
  }
  
  // 7. Intermediate: Candidate
  if (product.candidate_status === 'candidate') return 'candidate'
  
  // 8. Fallback
  return 'unknown'
}

// ── Test Suite ───────────────────────────────────────────────────────

test.describe('Stage Mapping - deriveUserStage()', () => {
  // ── Terminal States (highest priority) ────────────────────────────
  
  test('rejected - terminal state, highest priority', () => {
    const product = { candidate_status: 'rejected' }
    expect(deriveUserStage(product)).toBe('rejected')
  })
  
  test('rejected - overrides all other states', () => {
    // Even if wc_status is synced, rejected should win
    const product = { 
      candidate_status: 'rejected', 
      wc_status: 'synced',
      mastered_at: '2026-01-01T00:00:00Z'
    }
    expect(deriveUserStage(product)).toBe('rejected')
  })
  
  test('wc_published - terminal state, second priority', () => {
    const product = { wc_status: 'synced' }
    expect(deriveUserStage(product)).toBe('wc_published')
  })
  
  test('wc_published - overrides listing in progress', () => {
    // Even if listing_status is processing, synced WC should win
    const product = { 
      wc_status: 'synced',
      listing_status: 'processing'
    }
    expect(deriveUserStage(product)).toBe('wc_published')
  })
  
  test('wc_published - overrides approved', () => {
    const product = { 
      wc_status: 'synced',
      candidate_status: 'approved',
      mastered_at: '2026-01-01T00:00:00Z'
    }
    expect(deriveUserStage(product)).toBe('wc_published')
  })
  
  // ── Intermediate States (medium priority) ─────────────────────────
  
  test('listing - intermediate state', () => {
    const product = { listing_status: 'pending' }
    expect(deriveUserStage(product)).toBe('listing')
  })
  
  test('listing - approved listing status', () => {
    const product = { listing_status: 'approved' }
    expect(deriveUserStage(product)).toBe('listing')
  })
  
  test('listing - processing listing status', () => {
    const product = { listing_status: 'processing' }
    expect(deriveUserStage(product)).toBe('listing')
  })
  
  test('listing - overrides product_master', () => {
    const product = { 
      listing_status: 'pending',
      mastered_at: '2026-01-01T00:00:00Z'
    }
    expect(deriveUserStage(product)).toBe('listing')
  })
  
  test('listing - overrides candidate', () => {
    const product = { 
      listing_status: 'processing',
      candidate_status: 'candidate'
    }
    expect(deriveUserStage(product)).toBe('listing')
  })
  
  test('approved - with mastered_at', () => {
    const product = { 
      candidate_status: 'approved',
      mastered_at: '2026-01-01T00:00:00Z'
    }
    expect(deriveUserStage(product)).toBe('approved')
  })
  
  test('approved - without mastered_at falls through', () => {
    // Approved without mastered_at should not return 'approved'
    // It should check product_master next (which also won't match)
    // Then fall through to candidate or unknown
    const product = { 
      candidate_status: 'approved',
      mastered_at: null
    }
    // Should NOT be 'approved' because mastered_at is null
    // Should fall through to other checks
    const result = deriveUserStage(product)
    expect(result).not.toBe('approved')
  })
  
  test('product_master - mastered_at present', () => {
    const product = { 
      mastered_at: '2026-01-01T00:00:00Z'
    }
    expect(deriveUserStage(product)).toBe('product_master')
  })
  
  test('product_master - overrides analysis', () => {
    const product = { 
      mastered_at: '2026-01-01T00:00:00Z',
      funnel_stage: 'recalled'
    }
    expect(deriveUserStage(product)).toBe('product_master')
  })
  
  test('analysis - funnel_stage recalled', () => {
    const product = { 
      funnel_stage: 'recalled'
    }
    expect(deriveUserStage(product)).toBe('analysis')
  })
  
  test('analysis - funnel_stage screened', () => {
    const product = { 
      funnel_stage: 'screened'
    }
    expect(deriveUserStage(product)).toBe('analysis')
  })
  
  test('analysis - funnel_stage deep_candidate', () => {
    const product = { 
      funnel_stage: 'deep_candidate'
    }
    expect(deriveUserStage(product)).toBe('analysis')
  })
  
  test('analysis - overrides candidate', () => {
    const product = { 
      funnel_stage: 'screened',
      candidate_status: 'candidate'
    }
    expect(deriveUserStage(product)).toBe('analysis')
  })
  
  test('candidate - candidate_status candidate', () => {
    const product = { 
      candidate_status: 'candidate'
    }
    expect(deriveUserStage(product)).toBe('candidate')
  })
  
  // ── Boundary Cases ────────────────────────────────────────────────
  
  test('unknown - no matching state', () => {
    const product = { 
      candidate_status: null,
      funnel_stage: null,
      mastered_at: null,
      wc_status: null,
      listing_status: null
    }
    expect(deriveUserStage(product)).toBe('unknown')
  })
  
  test('unknown - empty object', () => {
    expect(deriveUserStage({})).toBe('unknown')
  })
  
  test('boundary - wc_published > listing', () => {
    // WC synced should override listing in progress
    const product = { 
      wc_status: 'synced',
      listing_status: 'pending'
    }
    expect(deriveUserStage(product)).toBe('wc_published')
  })
  
  test('boundary - listing > product_master', () => {
    // Listing in progress should override product master
    const product = { 
      listing_status: 'processing',
      mastered_at: '2026-01-01T00:00:00Z'
    }
    expect(deriveUserStage(product)).toBe('listing')
  })
  
  test('boundary - approved > product_master', () => {
    // Approved with mastered_at should return approved, not product_master
    const product = { 
      candidate_status: 'approved',
      mastered_at: '2026-01-01T00:00:00Z'
    }
    expect(deriveUserStage(product)).toBe('approved')
  })
  
  test('boundary - product_master > analysis', () => {
    // Product master should override analysis stage
    const product = { 
      mastered_at: '2026-01-01T00:00:00Z',
      funnel_stage: 'deep_candidate'
    }
    expect(deriveUserStage(product)).toBe('product_master')
  })
  
  test('boundary - analysis > candidate', () => {
    // Analysis should override candidate
    const product = { 
      funnel_stage: 'recalled',
      candidate_status: 'candidate'
    }
    expect(deriveUserStage(product)).toBe('analysis')
  })
  
  test('boundary - rejected > everything', () => {
    // Rejected should override everything
    const product = { 
      candidate_status: 'rejected',
      wc_status: 'synced',
      listing_status: 'processing',
      mastered_at: '2026-01-01T00:00:00Z',
      funnel_stage: 'recalled'
    }
    expect(deriveUserStage(product)).toBe('rejected')
  })
  
  test('boundary - all intermediate states combined', () => {
    // Should return the highest priority intermediate state
    const product = { 
      listing_status: 'pending',
      candidate_status: 'approved',
      mastered_at: '2026-01-01T00:00:00Z',
      funnel_stage: 'recalled',
      candidate_status_2: 'candidate' // won't match because of previous checks
    }
    expect(deriveUserStage(product)).toBe('listing')
  })
  
  // ── Edge Cases ────────────────────────────────────────────────────
  
  test('edge - listing_status failed should not match', () => {
    // Failed listing should not be 'listing' stage
    const product = { 
      listing_status: 'failed'
    }
    const result = deriveUserStage(product)
    expect(result).not.toBe('listing')
    // Should fall through to unknown or other states
  })
  
  test('edge - listing_status rejected should not match', () => {
    const product = { 
      listing_status: 'rejected'
    }
    const result = deriveUserStage(product)
    expect(result).not.toBe('listing')
  })
  
  test('edge - funnel_stage test_candidate should not match analysis', () => {
    // test_candidate is not in analysis stages (recalled/screened/deep_candidate)
    const product = { 
      funnel_stage: 'test_candidate'
    }
    const result = deriveUserStage(product)
    expect(result).not.toBe('analysis')
  })
  
  test('edge - funnel_stage testing should not match analysis', () => {
    const product = { 
      funnel_stage: 'testing'
    }
    const result = deriveUserStage(product)
    expect(result).not.toBe('analysis')
  })
  
  test('edge - funnel_stage hero should not match analysis', () => {
    const product = { 
      funnel_stage: 'hero'
    }
    const result = deriveUserStage(product)
    expect(result).not.toBe('analysis')
  })
  
  test('edge - wc_status syncing should not match wc_published', () => {
    const product = { 
      wc_status: 'syncing'
    }
    const result = deriveUserStage(product)
    expect(result).not.toBe('wc_published')
  })
  
  test('edge - wc_status failed should not match wc_published', () => {
    const product = { 
      wc_status: 'failed'
    }
    const result = deriveUserStage(product)
    expect(result).not.toBe('wc_published')
  })
  
  test('edge - wc_status not_synced should not match wc_published', () => {
    const product = { 
      wc_status: 'not_synced'
    }
    const result = deriveUserStage(product)
    expect(result).not.toBe('wc_published')
  })
})
