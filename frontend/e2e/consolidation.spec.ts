import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

const API_URL = 'http://127.0.0.1:8001/api/v1'
const WORKSPACE_ID = '00000000-0000-0000-0000-000000000001'

test.use({
  baseURL: 'http://127.0.0.1:3001',
  channel: 'chrome',
  viewport: { width: 1440, height: 1000 },
})

test.setTimeout(90000)

function authHeaders(token: string) {
  return { Authorization: `Bearer ${token}` }
}

async function login(page: Page) {
  await page.goto('/login')
  await page.getByLabel('用户名').fill('admin')
  await page.getByLabel('密码').fill('Admin@2026')
  await page.getByRole('button', { name: '进入控制台' }).click()
  await expect(page).toHaveURL(/\/dashboard/)
  const token = await page.evaluate(() => localStorage.getItem('admin_token'))
  expect(token).toBeTruthy()
  return token!
}

async function selectOption(page: Page, fieldId: string, option: string) {
  const field = page.locator(`#${fieldId}`)
  await field.click()
  await field.fill(option)
  await field.press('ArrowDown')
  await field.press('Enter')
}

async function createLegalEntity(
  page: Page,
  values: { code: string; name: string; legalName: string; country: string },
) {
  await page.getByRole('button', { name: '新建法人' }).click()
  const dialog = page.getByRole('dialog', { name: '新建法人主体' })
  await dialog.locator('#code').fill(values.code)
  await dialog.locator('#name').fill(values.name)
  await dialog.locator('#legal_name').fill(values.legalName)
  await dialog.locator('#country').fill(values.country)
  await dialog.locator('#functional_currency').fill('USD')
  await dialog.locator('.ant-modal-footer button.ant-btn-primary').click()
  await expect(page.getByText('法人主体已创建')).toBeVisible()
}

async function createBrand(
  page: Page,
  values: { code: string; name: string; legalEntityName: string },
) {
  await page.getByRole('tab', { name: '品牌', exact: true }).click()
  await page.getByRole('button', { name: '新建品牌' }).click()
  const dialog = page.getByRole('dialog', { name: '新建品牌' })
  await dialog.locator('#code').fill(values.code)
  await dialog.locator('#name').fill(values.name)
  await selectOption(page, 'default_legal_entity_id', values.legalEntityName)
  await dialog.locator('.ant-modal-footer button.ant-btn-primary').click()
  await expect(page.getByText('品牌已创建')).toBeVisible()
}

test('brand, legal entity, intercompany elimination, and consolidated report use real state', async ({
  page,
  request,
}) => {
  const consoleErrors: string[] = []
  const apiFailures: string[] = []
  const approvalStatuses: number[] = []
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
    if (
      response.url().includes('/approve-elimination') &&
      response.request().method() === 'POST'
    ) {
      approvalStatuses.push(response.status())
    }
  })

  const token = await login(page)
  const unique = Date.now()
  const suffix = String(unique).slice(-8)
  const sellerName = `Nuotao Consolidation Seller ${unique}`
  const buyerName = `Nuotao Consolidation Buyer ${unique}`
  const brandName = `Consolidation Brand ${unique}`

  await page.goto('/analytics/consolidation')
  await expect(
    page.getByRole('heading', { name: '合并经营报表' }),
  ).toBeVisible()

  await page.getByRole('tab', { name: '法人主体' }).click()
  await createLegalEntity(page, {
    code: `SELLER-${suffix}`,
    name: sellerName,
    legalName: `${sellerName} LLC`,
    country: 'US',
  })
  await createLegalEntity(page, {
    code: `BUYER-${suffix}`,
    name: buyerName,
    legalName: `${buyerName} GmbH`,
    country: 'DE',
  })
  await createBrand(page, {
    code: `BRAND-${suffix}`,
    name: brandName,
    legalEntityName: sellerName,
  })

  const agentResponse = await request.post(`${API_URL}/admin/b2b/agents`, {
    headers: authHeaders(token),
    data: {
      email: `consolidation-agent-${unique}@example.com`,
      password: 'ConsolidationAgent@2026',
      company_name: `Consolidation Agent ${unique}`,
      contact_name: 'Consolidation Buyer',
      country: 'DE',
      tier: 'gold',
      status: 'active',
      credit_limit: 100000,
      payment_terms_days: 30,
      currency: 'USD',
    },
  })
  const agentBody = await agentResponse.text()
  expect(agentResponse.status(), agentBody).toBe(201)
  const agent = JSON.parse(agentBody) as { id: string }

  const seedOutput = execFileSync(
    resolve(process.cwd(), '../backend/.venv/Scripts/python.exe'),
    [
      '-m',
      'tests.seed_b2b_order',
      '--agent-id',
      agent.id,
      '--amount',
      '200.00',
      '--order-number',
      `B2B-CONS-${unique}`,
      '--created-at',
      new Date().toISOString(),
      '--workspace-id',
      WORKSPACE_ID,
    ],
    {
      cwd: resolve(process.cwd(), '../backend'),
      encoding: 'utf8',
    },
  )
  const order = JSON.parse(seedOutput) as { id: string }

  const brandPayload = await request.get(`${API_URL}/admin/consolidation/brands`, {
    headers: authHeaders(token),
  })
  expect(brandPayload.status(), await brandPayload.text()).toBe(200)
  const brand = (
    JSON.parse(await brandPayload.text()) as {
      items: Array<{ id: string; name: string }>
    }
  ).items.find((row) => row.name === brandName)
  expect(brand).toBeTruthy()

  await page.reload()
  await page.getByRole('tab', { name: /交易归因/ }).click()
  await page.getByRole('button', { name: '登记归因' }).click()
  const dialog = page.getByRole('dialog', { name: '登记交易归因' })
  await dialog.locator('#entity_id').fill(order.id)
  await selectOption(page, 'brand_id', brandName)
  await selectOption(page, 'legal_entity_id', sellerName)
  await page.locator('#is_intercompany').click()
  await selectOption(page, 'counterparty_legal_entity_id', buyerName)
  await dialog
    .locator('#evidence_note')
    .fill('Chrome E2E intercompany contract IC-2026-001')
  await dialog.locator('.ant-modal-footer button.ant-btn-primary').click()
  await expect(page.getByText('交易归因已保存')).toBeVisible()

  const attributionRow = page
    .getByRole('tabpanel')
    .getByRole('row')
    .filter({ hasText: brandName })
    .filter({ hasText: sellerName })
  await expect(attributionRow).toContainText('待审批')
  await attributionRow.getByRole('button', { name: '批准消除' }).click()
  const decisionDialog = page.getByRole('dialog', {
    name: '批准内部交易消除',
  })
  await decisionDialog.locator('#elimination_amount').fill('200')
  await decisionDialog.locator('#note').fill('Chrome E2E approval')
  const approvalResponsePromise = page.waitForResponse(
    (response) =>
      response.url().includes('/approve-elimination') &&
      response.request().method() === 'POST',
  )
  await decisionDialog.locator('.ant-modal-footer button.ant-btn-primary').click()
  const approvalResponse = await approvalResponsePromise
  expect(approvalResponse.status(), await approvalResponse.text()).toBe(200)
  await page.waitForTimeout(500)
  expect(approvalStatuses).toEqual([200])
  await expect(decisionDialog).toBeHidden({ timeout: 5000 })

  await page.reload()
  await page.getByRole('tab', { name: /交易归因/ }).click()
  const approvedRow = page
    .getByRole('tabpanel')
    .getByRole('row')
    .filter({ hasText: brandName })
    .filter({ hasText: sellerName })
  await expect(approvedRow).toContainText('已批准消除')
  await expect(approvedRow.getByRole('button', { name: '批准消除' })).toHaveCount(
    0,
  )

  const reportResponse = await request.get(
    `${API_URL}/analytics/consolidation?start_date=${new Date()
      .toISOString()
      .slice(0, 10)}&end_date=${new Date()
      .toISOString()
      .slice(0, 10)}&brand_id=${brand!.id}`,
    { headers: authHeaders(token) },
  )
  const reportBody = await reportResponse.text()
  expect(reportResponse.status(), reportBody).toBe(200)
  const report = JSON.parse(reportBody) as {
    totals: {
      gross_revenue: string
      intercompany_revenue: string
      external_revenue: string
    }
    rows: Array<{
      brand_name: string
      legal_entity_name: string
      gross_revenue: string
      intercompany_revenue: string
      external_revenue: string
    }>
  }
  expect(report.totals.gross_revenue).toBe('200.00')
  expect(report.totals.intercompany_revenue).toBe('200.00')
  expect(report.totals.external_revenue).toBe('0.00')
  expect(report.rows).toHaveLength(1)
  expect(report.rows[0].brand_name).toBe(brandName)
  expect(report.rows[0].legal_entity_name).toBe(sellerName)

  await page.getByRole('button', { name: '刷新' }).click()
  const reportRow = page
    .locator('tr.ant-table-row[data-row-key$="-B2B-USD"]')
    .filter({ hasText: brandName })
    .filter({ hasText: sellerName })
  await expect(reportRow).toHaveCount(1)
  await expect(reportRow).toContainText('200.00')
  await expect(reportRow).toContainText('0.00')

  expect(apiFailures).toEqual([])
  expect(consoleErrors).toEqual([])
})

test('product brand governance reconciles historical attribution', async ({
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

  const token = await login(page)
  const unique = Date.now()
  const suffix = String(unique).slice(-8)
  const sku = `GOV-SKU-${suffix}`
  const orderNumber = `B2B-GOV-${unique}`
  const brandName = `Governance Brand ${unique}`

  const legalResponse = await request.post(
    `${API_URL}/admin/consolidation/legal-entities`,
    {
      headers: authHeaders(token),
      data: {
        code: `GOV-LE-${suffix}`,
        name: `Governance Legal ${unique}`,
        legal_name: `Governance Legal ${unique} LLC`,
        country: 'US',
        functional_currency: 'USD',
      },
    },
  )
  const legalBody = await legalResponse.text()
  expect(legalResponse.status(), legalBody).toBe(201)

  const brandResponse = await request.post(
    `${API_URL}/admin/consolidation/brands`,
    {
      headers: authHeaders(token),
      data: {
        code: `GOV-BRAND-${suffix}`,
        name: brandName,
      },
    },
  )
  const brandBody = await brandResponse.text()
  expect(brandResponse.status(), brandBody).toBe(201)
  const brand = JSON.parse(brandBody) as { id: string }

  const agentResponse = await request.post(`${API_URL}/admin/b2b/agents`, {
    headers: authHeaders(token),
    data: {
      email: `governance-agent-${unique}@example.com`,
      password: 'GovernanceAgent@2026',
      company_name: `Governance Agent ${unique}`,
      contact_name: 'Governance Buyer',
      country: 'US',
      tier: 'gold',
      status: 'active',
      credit_limit: 100000,
      payment_terms_days: 30,
      currency: 'USD',
    },
  })
  const agentBody = await agentResponse.text()
  expect(agentResponse.status(), agentBody).toBe(201)
  const agent = JSON.parse(agentBody) as { id: string }

  const seedOutput = execFileSync(
    resolve(process.cwd(), '../backend/.venv/Scripts/python.exe'),
    [
      '-m',
      'tests.seed_b2b_order',
      '--agent-id',
      agent.id,
      '--amount',
      '300.00',
      '--order-number',
      orderNumber,
      '--created-at',
      new Date().toISOString(),
      '--workspace-id',
      WORKSPACE_ID,
      '--product-sku',
      sku,
      '--product-name',
      `Governance Product ${unique}`,
    ],
    {
      cwd: resolve(process.cwd(), '../backend'),
      encoding: 'utf8',
    },
  )
  const seeded = JSON.parse(seedOutput) as {
    id: string
    product_id: string
  }
  expect(seeded.product_id).toBeTruthy()

  await page.goto('/analytics/consolidation')
  await expect(
    page.getByRole('heading', { name: '合并经营报表' }),
  ).toBeVisible()
  await page.getByRole('tab', { name: /归因缺口/ }).click()
  const gapRow = page.getByRole('row').filter({ hasText: orderNumber })
  await expect(gapRow).toContainText('商品未绑定品牌')

  await page.getByRole('tab', { name: /商品品牌/ }).click()
  const productRow = page.getByRole('row').filter({ hasText: sku })
  await expect(productRow).toHaveCount(1)
  await productRow.getByRole('checkbox').check()
  await selectOption(page, 'bulk_brand_id', brandName)
  await page.getByRole('button', { name: '批量绑定' }).click()
  await expect(page.getByText('已绑定 1 个商品')).toBeVisible()

  await page.getByRole('tab', { name: /归因缺口/ }).click()
  const legalGapRow = page.getByRole('row').filter({ hasText: orderNumber })
  await expect(legalGapRow).toContainText('品牌未配置默认法人')

  await page.getByRole('tab', { name: '品牌', exact: true }).click()
  const brandRow = page.getByRole('row').filter({ hasText: brandName })
  await expect(brandRow).toHaveCount(1)
  await brandRow.getByRole('button', { name: /编\s*辑/ }).click()
  const editBrandDialog = page.getByRole('dialog', { name: '编辑品牌' })
  await selectOption(
    page,
    'default_legal_entity_id',
    `Governance Legal ${unique}`,
  )
  await editBrandDialog
    .locator('.ant-modal-footer button.ant-btn-primary')
    .click()
  await expect(page.getByText('品牌已更新')).toBeVisible()

  await page.getByRole('tab', { name: /归因缺口/ }).click()
  const readyRow = page.getByRole('row').filter({ hasText: orderNumber })
  await expect(readyRow).toContainText('可自动补全')
  await page.getByRole('button', { name: /补全可自动归因/ }).click()
  await expect(page.getByText('已自动补全 1 条交易归因')).toBeVisible()

  const gapsResponse = await request.get(
    `${API_URL}/admin/consolidation/attribution-gaps?entity_type=b2b_order`,
    { headers: authHeaders(token) },
  )
  const gapsBody = await gapsResponse.text()
  expect(gapsResponse.status(), gapsBody).toBe(200)
  const gaps = JSON.parse(gapsBody) as {
    items: Array<{ entity_id: string }>
  }
  expect(gaps.items.some((row) => row.entity_id === seeded.id)).toBe(false)

  const reportResponse = await request.get(
    `${API_URL}/analytics/consolidation?start_date=${new Date()
      .toISOString()
      .slice(0, 10)}&end_date=${new Date()
      .toISOString()
      .slice(0, 10)}&brand_id=${brand.id}`,
    { headers: authHeaders(token) },
  )
  const reportBody = await reportResponse.text()
  expect(reportResponse.status(), reportBody).toBe(200)
  const report = JSON.parse(reportBody) as {
    rows: Array<{
      brand_name: string
      legal_entity_name: string
      gross_revenue: string
    }>
  }
  expect(report.rows).toHaveLength(1)
  expect(report.rows[0].brand_name).toBe(brandName)
  expect(report.rows[0].legal_entity_name).toContain('Governance Legal')
  expect(report.rows[0].gross_revenue).toBe('300.00')

  expect(apiFailures).toEqual([])
  expect(consoleErrors).toEqual([])
})

test('consolidation page has no horizontal overflow on a 390px viewport', async ({
  page,
}) => {
  await login(page)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/analytics/consolidation')
  await expect(
    page.getByRole('heading', { name: '合并经营报表' }),
  ).toBeVisible()

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  )
  expect(overflow).toBeLessThanOrEqual(1)
})
