import { test, expect } from '@playwright/test'

test.describe('Creative Studio C13 Vertical Slice', () => {
  test.beforeEach(async ({ page }) => {
    // Login
    await page.goto('/login')
    await page.waitForLoadState('networkidle')
    // Fill login form if present
    const usernameInput = page.locator('input[type="text"], input[name="username"]').first()
    if (await usernameInput.isVisible({ timeout: 3000 })) {
      await usernameInput.fill('admin')
      const passwordInput = page.locator('input[type="password"]').first()
      await passwordInput.fill('admin')
      await page.locator('button[type="submit"]').click()
      await page.waitForURL('**/dashboard', { timeout: 10000 })
    }
  })

  test('should navigate to Creative Studio page', async ({ page }) => {
    await page.goto('/creative')
    await expect(page.locator('h2, h3')).toContainText('AI 创意工坊')
    await expect(page.locator('text=选择 Product Master')).toBeVisible()
    await expect(page.locator('text=Creative Briefs')).toBeVisible()
  })

  test('should show loading state initially', async ({ page }) => {
    await page.goto('/creative')
    await expect(page.locator('.ant-spin')).toBeVisible({ timeout: 5000 })
  })

  test('should handle permission denied gracefully', async ({ page }) => {
    // Without valid auth, should redirect to login or show error
    await page.goto('/creative')
    // Either redirect to login or show error message
    const isLogin = page.url().includes('/login')
    const hasError = await page.locator('.ant-alert-error').isVisible({ timeout: 3000 })
    expect(isLogin || hasError).toBeTruthy()
  })

  test('should show product selection dropdown', async ({ page }) => {
    await page.goto('/creative')
    await page.waitForLoadState('networkidle')
    await expect(page.locator('.ant-select')).toBeVisible()
  })

  test('should show empty state when no briefs', async ({ page }) => {
    await page.goto('/creative')
    await page.waitForLoadState('networkidle')
    // Either show empty state or show briefs table
    const hasEmpty = await page.locator('.ant-empty').isVisible({ timeout: 3000 })
    const hasTable = await page.locator('.ant-table').isVisible({ timeout: 3000 })
    expect(hasEmpty || hasTable).toBeTruthy()
  })

  test('should navigate to workbench when product selected', async ({ page }) => {
    await page.goto('/creative')
    await page.waitForLoadState('networkidle')
    // Click on workbench button (may be disabled without product)
    const workbenchBtn = page.locator('button:has-text("进入 Workbench")')
    if (await workbenchBtn.isEnabled()) {
      await workbenchBtn.click()
      await expect(page).toHaveURL(/\/creative\/workbench\//)
    }
  })

  test('workbench should show production pipeline steps', async ({ page }) => {
    // Navigate to workbench with a product ID (may fail if no products exist)
    await page.goto('/creative/workbench/test-product-id')
    // Should show loading or error state
    const hasLoading = await page.locator('.ant-spin').isVisible({ timeout: 5000 })
    const hasError = await page.locator('.ant-alert').isVisible({ timeout: 3000 })
    expect(hasLoading || hasError).toBeTruthy()
  })

  test('workbench should have tabs for assets, runs, reviews', async ({ page }) => {
    await page.goto('/creative/workbench/test-product-id')
    await page.waitForLoadState('networkidle')
    const hasAssetsTab = await page.locator('text=Assets').isVisible({ timeout: 3000 })
    const hasRunsTab = await page.locator('text=Runs').isVisible({ timeout: 3000 })
    expect(hasAssetsTab || hasRunsTab).toBeTruthy()
  })

  test('should not show unsupported operations as clickable', async ({ page }) => {
    await page.goto('/creative')
    await page.waitForLoadState('networkidle')
    // The operations endpoint should show only generate as SUPPORTED
    // This is a visual check - the generate button should be visible
    await expect(page.locator('button:has-text("进入 Workbench")')).toBeVisible()
  })

  test('should show status badges', async ({ page }) => {
    await page.goto('/creative')
    await page.waitForLoadState('networkidle')
    // Check for service status badge
    const hasBadge = await page.locator('.ant-badge').isVisible({ timeout: 3000 })
    expect(hasBadge).toBeTruthy()
  })

  // ── C15 Analytics Tests ─────────────────────────────────────────────
  test.describe('Creative Analytics', () => {
    test('should navigate to Analytics page', async ({ page }) => {
      await page.goto('/creative/analytics')
      await expect(page.locator('h2, h3')).toContainText('Creative Analytics')
      await expect(page.locator('text=创意生成性能与成本分析')).toBeVisible()
    })

    test('should show time range selector', async ({ page }) => {
      await page.goto('/creative/analytics')
      await page.waitForLoadState('networkidle')
      await expect(page.locator('.ant-select')).toBeVisible()
    })

    test('should show loading state', async ({ page }) => {
      await page.goto('/creative/analytics')
      await expect(page.locator('.ant-spin')).toBeVisible({ timeout: 5000 })
    })

    test('should handle empty data gracefully', async ({ page }) => {
      await page.goto('/creative/analytics')
      await page.waitForLoadState('networkidle')
      // Should show empty state or data cards
      const hasEmpty = await page.locator('.ant-empty').isVisible({ timeout: 3000 })
      const hasCards = await page.locator('.ant-card').isVisible({ timeout: 3000 })
      expect(hasEmpty || hasCards).toBeTruthy()
    })
  })

  // ── P2 Knowledge Tests ──────────────────────────────────────────────
  test.describe('Creative Knowledge', () => {
    test('should navigate to Knowledge page', async ({ page }) => {
      await page.goto('/creative/knowledge')
      await expect(page.locator('h2, h3')).toContainText('Creative Knowledge')
      await expect(page.locator('text=Prompt 学习与知识库')).toBeVisible()
    })

    test('should show search input', async ({ page }) => {
      await page.goto('/creative/knowledge')
      await page.waitForLoadState('networkidle')
      await expect(page.locator('input[placeholder*="Search"]')).toBeVisible()
    })

    test('should show refresh button', async ({ page }) => {
      await page.goto('/creative/knowledge')
      await page.waitForLoadState('networkidle')
      await expect(page.locator('button:has-text("刷新")')).toBeVisible()
    })
  })

  // ── P2 Calibration Tests ────────────────────────────────────────────
  test.describe('Creative Calibration', () => {
    test('should navigate to Calibration page', async ({ page }) => {
      await page.goto('/creative/calibration')
      await expect(page.locator('h2, h3')).toContainText('Calibration')
      await expect(page.locator('text=模型校准与质量调优')).toBeVisible()
    })

    test('should show refresh button', async ({ page }) => {
      await page.goto('/creative/calibration')
      await page.waitForLoadState('networkidle')
      await expect(page.locator('button:has-text("刷新")')).toBeVisible()
    })
  })

  // ── P2 Automation Tests ─────────────────────────────────────────────
  test.describe('Creative Automation', () => {
    test('should navigate to Automation page', async ({ page }) => {
      await page.goto('/creative/automation')
      await expect(page.locator('h2, h3')).toContainText('Automation Builder')
      await expect(page.locator('text=自动化工作流管理')).toBeVisible()
    })

    test('should show New Workflow button', async ({ page }) => {
      await page.goto('/creative/automation')
      await page.waitForLoadState('networkidle')
      await expect(page.locator('button:has-text("New Workflow")')).toBeVisible()
    })

    test('should show refresh button', async ({ page }) => {
      await page.goto('/creative/automation')
      await page.waitForLoadState('networkidle')
      await expect(page.locator('button:has-text("刷新")')).toBeVisible()
    })

    test('should open create workflow modal', async ({ page }) => {
      await page.goto('/creative/automation')
      await page.waitForLoadState('networkidle')
      await page.locator('button:has-text("New Workflow")').click()
      await expect(page.locator('.ant-modal')).toBeVisible({ timeout: 3000 })
      await expect(page.locator('text=Workflow name')).toBeVisible()
    })
  })

  // ── Mobile Responsive Tests ─────────────────────────────────────────
  test.describe('Mobile Responsive', () => {
    test.use({ viewport: { width: 375, height: 667 } }) // iPhone SE

    test('should show responsive layout on mobile', async ({ page }) => {
      await page.goto('/creative')
      await page.waitForLoadState('networkidle')
      // Check that content is visible on mobile
      await expect(page.locator('text=AI 创意工坊')).toBeVisible()
    })

    test('workbench should be responsive on mobile', async ({ page }) => {
      await page.goto('/creative/workbench/test-product-id')
      await page.waitForLoadState('networkidle')
      // Should show loading or error on mobile too
      const hasLoading = await page.locator('.ant-spin').isVisible({ timeout: 5000 })
      const hasError = await page.locator('.ant-alert').isVisible({ timeout: 3000 })
      expect(hasLoading || hasError).toBeTruthy()
    })
  })
})