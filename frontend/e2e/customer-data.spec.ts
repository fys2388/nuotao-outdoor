import { expect, test, type APIRequestContext } from '@playwright/test'

const API_URL = 'http://127.0.0.1:8001/api/v1'

test.use({
  baseURL: 'http://127.0.0.1:3001',
  channel: 'chrome',
  viewport: { width: 1440, height: 1000 },
})

test.setTimeout(120000)

function authHeaders(token: string) {
  return { Authorization: `Bearer ${token}` }
}

async function loginThroughUi(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.getByLabel('用户名').fill('admin')
  await page.getByLabel('密码').fill('Admin@2026')
  await page.getByRole('button', { name: '进入控制台' }).click()
  await expect(page).toHaveURL(/\/dashboard/)
  const token = await page.evaluate(() => localStorage.getItem('admin_token'))
  expect(token).toBeTruthy()
  return token!
}

async function createAccount(
  request: APIRequestContext,
  token: string,
  identityType: 'email' | 'phone',
  identityValue: string,
) {
  const response = await request.post(
    `${API_URL}/admin/customer-data/identities/resolve`,
    {
      headers: authHeaders(token),
      data: {
        identity_type: identityType,
        identity_value: identityValue,
        channel: identityType === 'email' ? 'email' : 'crm',
        external_system: 'chrome-e2e',
        create_if_missing: true,
        customer_type: 'CONSUMER',
        business_model: identityType === 'email' ? 'B2C' : 'BOTH',
      },
    },
  )
  const body = await response.text()
  expect(response.status(), body).toBe(200)
  return JSON.parse(body) as {
    resolved: boolean
    account: { id: string; customer_number: string }
  }
}

test('customer data workflows use real APIs on desktop', async ({
  page,
  request,
}) => {
  const consoleErrors: string[] = []
  const apiFailures: string[] = []
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })
  page.on('response', (response) => {
    if (
      response.url().includes('/api/v1/') &&
      [401, 403, 500].includes(response.status())
    ) {
      apiFailures.push(
        `${response.status()} ${response.request().method()} ${response.url()}`,
      )
    }
  })

  const token = await loginThroughUi(page)
  const unique = Date.now()
  const sourceIdentity = `privacy-source-${unique}@example.com`
  const targetPhone = `+1415${String(unique).slice(-7)}`
  const source = await createAccount(request, token, 'email', sourceIdentity)
  const target = await createAccount(request, token, 'phone', targetPhone)

  const conflictLink = await request.post(
    `${API_URL}/admin/customer-data/identities`,
    {
      headers: authHeaders(token),
      data: {
        customer_account_id: target.account.id,
        identity_type: 'email',
        identity_value: sourceIdentity,
        channel: 'email',
        external_system: 'chrome-e2e',
        source: 'chrome_e2e',
        metadata: {},
      },
    },
  )
  expect(conflictLink.status(), await conflictLink.text()).toBe(201)

  const mergeResponse = await request.post(
    `${API_URL}/admin/customer-data/merges`,
    {
      headers: authHeaders(token),
      data: {
        source_account_id: source.account.id,
        target_account_id: target.account.id,
        reason: `Chrome E2E deterministic identity match ${unique}`,
      },
    },
  )
  const mergeBody = await mergeResponse.text()
  expect(mergeResponse.status(), mergeBody).toBe(201)

  await page.goto('/settings/customer-data')
  await expect(
    page.getByRole('heading', { name: '客户身份与隐私' }),
  ).toBeVisible()
  await expect(page.getByText('身份链接与冲突')).toBeVisible()

  await page.getByRole('tab', { name: '合并审批' }).click()
  const mergeRow = page
    .getByRole('row')
    .filter({
      hasText: `Chrome E2E deterministic identity match ${unique}`,
    })
  await expect(mergeRow).toBeVisible()
  await mergeRow.getByRole('button', { name: /批\s*准/ }).click()
  await expect(page.getByText('合并申请已批准')).toBeVisible()
  await mergeRow.getByRole('button', { name: /执行合并/ }).click()
  await expect(page.getByText('账户合并已完成')).toBeVisible()

  await page.getByRole('tab', { name: '同意账本' }).click()
  const consentAccount = page.getByLabel('同意账本客户账户')
  await consentAccount.fill(target.account.customer_number)
  await page.keyboard.press('Enter')
  await page.getByRole('button', { name: '登记授权' }).click()
  const consentModal = page.getByRole('dialog', { name: '登记同意事件' })
  await consentModal.getByRole('button', { name: '写入账本' }).click()
  await expect(page.getByText('同意事件已登记')).toBeVisible()
  await page.getByRole('button', { name: '撤回同意' }).click()
  const withdrawModal = page.getByRole('dialog', { name: '登记同意事件' })
  await withdrawModal.getByRole('button', { name: '写入账本' }).click()
  await expect(page.getByText('同意已撤回并立即生效')).toBeVisible()

  await page.getByRole('tab', { name: '数据主体请求' }).click()
  await page.getByRole('button', { name: '登记请求' }).click()
  const requestModal = page.getByRole('dialog', { name: '登记数据主体请求' })
  const requestAccount = requestModal.getByLabel('客户账户')
  await requestAccount.fill(target.account.customer_number)
  await page.keyboard.press('Enter')
  await requestModal.getByLabel('请求说明').fill('Chrome E2E access request')
  await requestModal.getByRole('button', { name: /登\s*记/ }).click()
  await expect(page.getByText('数据主体请求已登记')).toBeVisible()

  const requestRow = page
    .getByRole('row')
    .filter({ hasText: target.account.customer_number })
    .filter({ hasText: '访问' })
    .first()
  await expect(requestRow).toContainText('已受理')
  await requestRow.getByRole('button', { name: /核\s*验/ }).click()
  const verifyModal = page.getByRole('dialog', { name: '核验数据主体身份' })
  await verifyModal
    .getByLabel('核验方式')
    .fill('Chrome E2E account control verification')
  await verifyModal.getByRole('button', { name: '确认核验' }).click()
  await expect(page.getByText('身份核验已登记')).toBeVisible()
  await expect(requestRow).toContainText('待审批')

  await requestRow.getByRole('button', { name: /批\s*准/ }).click()
  const approveModal = page.getByRole('dialog', { name: '批准数据主体请求' })
  await approveModal.getByRole('textbox').fill('Verified access request')
  await approveModal.getByRole('button', { name: /确\s*认/ }).click()
  await expect(page.getByText('请求已批准，等待执行')).toBeVisible()
  await expect(requestRow).toContainText('待执行')

  await requestRow.getByRole('button', { name: /执\s*行/ }).click()
  const executeModal = page.getByRole('dialog', {
    name: '执行数据主体请求',
  })
  await executeModal.getByRole('textbox').fill('Export snapshot generated')
  await executeModal.getByRole('button', { name: '确认执行' }).click()
  await expect(page.getByText('请求已执行并写入审计')).toBeVisible()
  await expect(requestRow).toContainText('已完成')

  expect(apiFailures).toEqual([])
  expect(consoleErrors).toEqual([])
})

test('customer data page is usable at 390px', async ({ page }) => {
  const consoleErrors: string[] = []
  const apiFailures: string[] = []
  await page.setViewportSize({ width: 390, height: 844 })
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })
  page.on('response', (response) => {
    if (
      response.url().includes('/api/v1/') &&
      [401, 403, 500].includes(response.status())
    ) {
      apiFailures.push(
        `${response.status()} ${response.request().method()} ${response.url()}`,
      )
    }
  })

  await loginThroughUi(page)
  await page.goto('/settings/customer-data')
  const heading = page.getByRole('heading', { name: '客户身份与隐私' })
  await expect(heading).toBeVisible()
  await expect(page.getByText('统一客户账户')).toBeVisible()
  await expect(page.getByRole('tab', { name: '身份链接与冲突' })).toBeVisible()
  await expect(page.getByRole('button', { name: '刷新' })).toBeVisible()

  const layout = await page.evaluate(() => {
    const body = document.body
    const headingElement = Array.from(document.querySelectorAll('h3')).find(
      (element) => element.textContent?.includes('客户身份与隐私'),
    )
    const button = Array.from(document.querySelectorAll('button')).find(
      (element) => element.textContent?.includes('刷新'),
    )
    return {
      viewportWidth: window.innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      headingRight: headingElement?.getBoundingClientRect().right || 0,
      buttonRight: button?.getBoundingClientRect().right || 0,
      bodyHeight: body.getBoundingClientRect().height,
    }
  })
  expect(layout.documentWidth).toBeLessThanOrEqual(layout.viewportWidth + 1)
  expect(layout.headingRight).toBeLessThanOrEqual(layout.viewportWidth)
  expect(layout.buttonRight).toBeLessThanOrEqual(layout.viewportWidth)
  expect(layout.bodyHeight).toBeGreaterThan(500)

  expect(apiFailures).toEqual([])
  expect(consoleErrors).toEqual([])
})
