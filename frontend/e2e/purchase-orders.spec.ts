import { expect, test } from '@playwright/test'

const baseURL =
  process.env.E2E_PURCHASE_ORDERS_URL ||
  process.env.E2E_ADMIN_URL

test.use({
  baseURL: baseURL || 'http://127.0.0.1:3011',
  channel: 'chrome',
  viewport: { width: 1440, height: 1000 },
})

test('purchase order page exposes the real lifecycle entry points', async ({ page }) => {
  test.skip(!baseURL, 'Set E2E_PURCHASE_ORDERS_URL to run this live test')

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

  const ordersResponse = page.waitForResponse(
    (response) =>
      response.url().includes('/api/v1/purchase-orders') &&
      response.request().method() === 'GET',
  )
  await page.goto('/supply/purchases')

  await expect(page.getByRole('heading', { name: '采购订单' })).toBeVisible()
  await expect(page.getByRole('button', { name: '新建采购单' })).toBeVisible()
  await expect(page.getByText('采购单使用独立生命周期')).toBeVisible()
  expect((await ordersResponse).status()).toBe(200)

  await page.getByRole('button', { name: '新建采购单' }).click()
  await expect(page.getByRole('dialog', { name: '新建采购单' })).toBeVisible()
  await expect(page.getByLabel('采购单号')).toBeVisible()
  await expect(page.getByLabel('供应商')).toBeVisible()
  await expect(page.getByLabel('采购备注')).toBeVisible()
  await expect(page.getByRole('button', { name: '创建草稿' })).toBeVisible()

  expect(apiFailures).toEqual([])
  expect(
    consoleErrors.filter(
      (text) =>
        !text.includes('Instance created by `useForm` is not connected') &&
        !text.includes('[antd: Space] `direction` is deprecated'),
    ),
  ).toEqual([])
})
