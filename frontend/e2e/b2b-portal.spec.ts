import { expect, test } from '@playwright/test'

test.use({
  baseURL: 'http://127.0.0.1:3001',
  channel: 'chrome',
  viewport: { width: 1440, height: 1000 },
})

test('B2B customer portal loads with an isolated customer session', async ({ page }) => {
  const portalFailures: string[] = []
  const consoleErrors: string[] = []

  page.on('response', (response) => {
    if (
      response.url().includes('/api/v1/b2b-portal/') &&
      [401, 403].includes(response.status())
    ) {
      portalFailures.push(
        `${response.status()} ${response.request().method()} ${response.url()}`,
      )
    }
  })
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })

  await page.goto('/login')
  await page.getByLabel('用户名').fill('admin')
  await page.getByLabel('密码').fill('Admin@2026')
  await page.getByRole('button', { name: '进入控制台' }).click()
  await expect(page).toHaveURL(/\/dashboard/)

  const adminToken = await page.evaluate(() => localStorage.getItem('admin_token'))
  expect(adminToken).toBeTruthy()

  const unique = Date.now()
  const email = `portal-e2e-${unique}@example.com`
  const password = 'PortalTest@2026'
  const created = await page.request.post(
    'http://127.0.0.1:8001/api/v1/admin/b2b/agents',
    {
      headers: { Authorization: `Bearer ${adminToken}` },
      data: {
        email,
        password,
        company_name: `Portal E2E ${unique}`,
        contact_name: 'Portal Buyer',
        country: 'US',
        tier: 'bronze',
        status: 'active',
        credit_limit: 100000,
        payment_terms_days: 30,
        currency: 'USD',
      },
    },
  )
  expect(created.status(), await created.text()).toBe(201)

  await page.goto('/portal/login')
  await page.getByLabel('登录邮箱').fill(email)
  await page.getByLabel('密码').fill(password)
  await page.getByRole('button', { name: /登\s*录/ }).click()
  await expect(page).toHaveURL(/\/portal$/)
  await expect(page.getByRole('heading', { name: '工作台' })).toBeVisible()

  const routes = [
    ['/portal/products', '商品目录'],
    ['/portal/rfqs', 'RFQ 询盘'],
    ['/portal/quotes', '报价'],
    ['/portal/contracts', '合同'],
    ['/portal/orders', '订单'],
    ['/portal/account', '账户'],
  ] as const

  for (const [path, heading] of routes) {
    await page.goto(path)
    await expect(page.getByRole('heading', { name: heading })).toBeVisible()
    await expect(page.locator('body')).not.toContainText('门户数据加载失败')
  }

  expect(portalFailures).toEqual([])
  expect(consoleErrors).toEqual([])
})
