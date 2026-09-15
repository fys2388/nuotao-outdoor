import { expect, test } from '@playwright/test'

const baseURL =
  process.env.E2E_PRODUCT_CANDIDATES_URL ||
  process.env.E2E_PRODUCT_ANALYSIS_URL

test.use({
  baseURL: baseURL || 'http://127.0.0.1:3001',
  channel: 'chrome',
  viewport: { width: 1440, height: 1000 },
})

test('product candidates page is connected to the live candidate API', async ({ page }) => {
  test.skip(!baseURL, 'Set E2E_PRODUCT_CANDIDATES_URL to run this live test')

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

  const candidatesResponse = page.waitForResponse(
    (response) =>
      response.url().includes('/api/v1/sourcing/candidates') &&
      response.request().method() === 'GET',
  )
  await page.goto('/products/candidates')

  await expect(page.getByRole('heading', { name: '候选产品与选品' })).toBeVisible()
  await expect(
    page.getByText(/候选商品、六维评分、落地成本和人工选品状态统一在这里管理/),
  ).toBeVisible()
  await expect(page.locator('body')).not.toContainText('尚未接入')
  await expect(page.getByRole('button', { name: '录入候选' })).toBeVisible()
  await expect(page.getByPlaceholder('搜索商品、SKU、分类或来源链接')).toBeVisible()

  expect((await candidatesResponse).status()).toBe(200)
  expect(apiFailures).toEqual([])
  expect(consoleErrors).toEqual([])
})
