import { expect, test } from '@playwright/test'

test.use({
  baseURL: 'http://127.0.0.1:3001',
  channel: 'chrome',
  viewport: { width: 1440, height: 1000 },
})

test('B2B P1 routes load against the local API', async ({ page }) => {
  const apiFailures: string[] = []
  const consoleErrors: string[] = []

  page.on('response', (response) => {
    if (
      response.url().includes('/api/v1/') &&
      [401, 403].includes(response.status())
    ) {
      apiFailures.push(`${response.status()} ${response.request().method()} ${response.url()}`)
    }
  })
  page.on('console', (message) => {
    if (message.type() === 'error') {
      consoleErrors.push(message.text())
    }
  })

  await page.goto('/login')
  await page.getByLabel('用户名').fill('admin')
  await page.getByLabel('密码').fill('Admin@2026')
  await page.getByRole('button', { name: '进入控制台' }).click()
  await expect(page).toHaveURL(/\/dashboard/)

  const routes = [
    ['/b2b/pricing', '商品目录与阶梯价'],
    ['/b2b/rfqs', '询盘、报价与合同'],
    ['/b2b/quotes', '询盘、报价与合同'],
    ['/b2b/orders', 'B2B 代理商管理'],
    ['/b2b/agreements', '代理商年度协议与分级返利'],
    ['/b2b/receivables', '发票、收款与应收账款'],
    ['/b2b/credit', '信用风控与信用保险'],
    ['/b2b/ai', 'B2B 专业 Agent'],
  ] as const

  for (const [path, heading] of routes) {
    await page.goto(path)
    await expect(page.getByText(heading, { exact: false }).first()).toBeVisible()
    await expect(page.locator('body')).not.toContainText('数据加载失败')
    await expect(page.locator('body')).not.toContainText('登录状态已失效')
  }

  expect(apiFailures).toEqual([])
  expect(consoleErrors).toEqual([])
})
