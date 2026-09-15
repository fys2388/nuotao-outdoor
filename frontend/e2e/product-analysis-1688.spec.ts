import { expect, test } from '@playwright/test'

const baseURL = process.env.E2E_PRODUCT_ANALYSIS_URL
const productURL =
  process.env.E2E_PRODUCT_1688_URL ||
  'https://detail.1688.com/offer/1075485124628.html'

test.use({
  baseURL: baseURL || 'http://127.0.0.1:3001',
  channel: 'chrome',
  viewport: { width: 1440, height: 1000 },
})

test('1688 product analysis completes through the async job flow', async ({ page }) => {
  test.skip(!baseURL, 'Set E2E_PRODUCT_ANALYSIS_URL to run this production/live test')
  test.setTimeout(15 * 60 * 1000)

  const apiFailures: string[] = []
  const consoleErrors: string[] = []
  page.on('response', (response) => {
    if (
      response.url().includes('/api/v1/') &&
      [401, 403, 500].includes(response.status())
    ) {
      apiFailures.push(`${response.status()} ${response.request().method()} ${response.url()}`)
    }
  })
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })

  await page.goto('/login')
  await page.getByLabel('用户名').fill(process.env.E2E_ADMIN_USERNAME || 'admin')
  await page
    .getByLabel('密码')
    .fill(process.env.E2E_ADMIN_PASSWORD || 'Nuotao@2026!Admin')
  await page.getByRole('button', { name: '进入控制台' }).click()
  await expect(page).toHaveURL(/\/dashboard/)

  await page.goto('/products/analysis')
  await page.getByPlaceholder(/每行一个链接或商品 ID/).fill(productURL)
  await page.getByRole('button', { name: /导入并分析/ }).click()

  await expect(page.getByText('产品信息报告（17字段）')).toBeVisible({
    timeout: 14 * 60 * 1000,
  })
  await expect(page.getByText('牛顿 Agent').first()).toBeVisible()
  await expect(page.locator('body')).not.toContainText('失败 1')
  expect(apiFailures).toEqual([])
  expect(consoleErrors).toEqual([])
})
