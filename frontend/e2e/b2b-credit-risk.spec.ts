import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
import { expect, test, type APIRequestContext } from '@playwright/test'

const API_URL = 'http://127.0.0.1:8001/api/v1'
const WORKSPACE_ID = '00000000-0000-0000-0000-000000000001'

test.use({
  baseURL: 'http://127.0.0.1:3001',
  channel: 'chrome',
  viewport: { width: 1440, height: 1000 },
})

test.setTimeout(60000)

async function loginApi(
  request: APIRequestContext,
  username: string,
  password: string,
): Promise<string> {
  const response = await request.post(`${API_URL}/auth/login`, {
    form: { username, password },
  })
  const body = await response.text()
  expect(response.status(), body).toBe(200)
  return (JSON.parse(body) as { access_token: string }).access_token
}

function authHeaders(token: string) {
  return { Authorization: `Bearer ${token}` }
}

function dateOffset(days: number): string {
  const date = new Date()
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

test('credit policy, risk hold, release, and insurance coverage use real backend state', async ({
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

  await page.goto('/login')
  await page.getByLabel('用户名').fill('admin')
  await page.getByLabel('密码').fill('Admin@2026')
  await page.getByRole('button', { name: '进入控制台' }).click()
  await expect(page).toHaveURL(/\/dashboard/)

  const adminToken = await page.evaluate(() => localStorage.getItem('admin_token'))
  expect(adminToken).toBeTruthy()
  const unique = Date.now()
  const operatorUsername = `credit-operator-${unique}`
  const operatorPassword = 'CreditTest@2026'

  const createUser = await request.post(`${API_URL}/auth/users`, {
    headers: authHeaders(adminToken!),
    data: {
      username: operatorUsername,
      email: `${operatorUsername}@example.com`,
      full_name: 'Credit E2E Operator',
      password: operatorPassword,
      role: 'operator',
      is_active: true,
    },
  })
  expect(createUser.status(), await createUser.text()).toBe(201)
  const operatorToken = await loginApi(
    request,
    operatorUsername,
    operatorPassword,
  )

  const companyName = `Credit E2E Agent ${unique}`
  const agentResponse = await request.post(`${API_URL}/admin/b2b/agents`, {
    headers: authHeaders(adminToken!),
    data: {
      email: `credit-agent-${unique}@example.com`,
      password: 'CreditAgent@2026',
      company_name: companyName,
      contact_name: 'Credit Buyer',
      country: 'US',
      tier: 'gold',
      status: 'active',
      credit_limit: 1000,
      payment_terms_days: 30,
      currency: 'USD',
    },
  })
  const agentBody = await agentResponse.text()
  expect(agentResponse.status(), agentBody).toBe(201)
  const agent = JSON.parse(agentBody) as { id: string }

  const policyResponse = await request.post(`${API_URL}/admin/b2b/credit/policies`, {
    headers: authHeaders(operatorToken),
    data: {
      watch_score: 35,
      hold_score: 65,
      freeze_score: 95,
      max_utilization_percent: 100,
      max_overdue_days: 60,
      auto_hold_enabled: true,
      auto_freeze_enabled: false,
      insurance_required_above: 0,
      notes: 'Chrome E2E credit policy',
    },
  })
  const policyBody = await policyResponse.text()
  expect(policyResponse.status(), policyBody).toBe(201)
  const policy = JSON.parse(policyBody) as { id: string }
  const submitPolicy = await request.post(
    `${API_URL}/admin/b2b/credit/policies/${policy.id}/submit`,
    { headers: authHeaders(operatorToken) },
  )
  expect(submitPolicy.status(), await submitPolicy.text()).toBe(200)

  const insuranceResponse = await request.post(
    `${API_URL}/admin/b2b/credit/insurance`,
    {
      headers: authHeaders(operatorToken),
      data: {
        agent_id: agent.id,
        policy_number: `INS-E2E-${unique}`,
        provider: 'Chrome E2E Credit Insurer',
        currency: 'USD',
        coverage_limit: 800,
        coverage_percent: 80,
        effective_from: dateOffset(-1),
        effective_to: dateOffset(365),
        status: 'active',
        notes: 'Chrome E2E insurance fixture',
      },
    },
  )
  expect(insuranceResponse.status(), await insuranceResponse.text()).toBe(201)

  const seedOutput = execFileSync(
    resolve(process.cwd(), '../backend/.venv/Scripts/python.exe'),
    [
      '-m',
      'tests.seed_b2b_order',
      '--agent-id',
      agent.id,
      '--amount',
      '800.00',
      '--order-number',
      `B2B-CREDIT-${unique}`,
      '--created-at',
      '2026-04-01T10:00:00+00:00',
      '--workspace-id',
      WORKSPACE_ID,
    ],
    {
      cwd: resolve(process.cwd(), '../backend'),
      encoding: 'utf8',
    },
  )
  const order = JSON.parse(seedOutput) as { id: string }

  const invoiceResponse = await request.post(`${API_URL}/admin/b2b/invoices`, {
    headers: authHeaders(adminToken!),
    data: {
      order_id: order.id,
      issue_date: dateOffset(-100),
      due_date: dateOffset(-70),
      notes: 'Chrome E2E overdue credit fixture',
    },
  })
  const invoiceBody = await invoiceResponse.text()
  expect(invoiceResponse.status(), invoiceBody).toBe(201)
  const invoice = JSON.parse(invoiceBody) as { id: string }
  const issueInvoice = await request.post(
    `${API_URL}/admin/b2b/invoices/${invoice.id}/issue`,
    { headers: authHeaders(adminToken!) },
  )
  expect(issueInvoice.status(), await issueInvoice.text()).toBe(200)

  await page.goto('/b2b/credit')
  await expect(
    page.getByRole('heading', { name: '信用风控与信用保险' }),
  ).toBeVisible()

  await page.getByRole('tab', { name: '信用政策' }).click()
  const policyRow = page
    .getByRole('row')
    .filter({ hasText: operatorUsername })
  await expect(policyRow).toContainText('待审批')
  await policyRow.getByRole('button', { name: '审批生效' }).click()
  await expect(page.getByText('信用政策已生效')).toBeVisible()

  await page.getByRole('tab', { name: '风险总览' }).click()
  const riskRow = page.getByRole('row').filter({ hasText: companyName })
  await expect(riskRow).toBeVisible()
  await riskRow.getByRole('button', { name: '评估' }).click()
  await expect(page.getByText('风险评估已生成')).toBeVisible()
  await expect(
    riskRow.getByText('暂停接单', { exact: true }).first(),
  ).toBeVisible()

  await riskRow.getByRole('button', { name: '查看' }).click()
  const drawer = page.locator('.ant-drawer')
  await expect(drawer.getByText('客户信用档案')).toBeVisible()
  await expect(drawer.getByText(/640\.00/).first()).toBeVisible()
  await drawer.getByRole('button', { name: '解除限制' }).click()
  const decisionModal = page.getByRole('dialog', { name: '解除信用限制' })
  await decisionModal
    .getByRole('textbox')
    .fill('Payment plan approved in Chrome E2E')
  await decisionModal.getByRole('button', { name: '确认解除' }).click()
  await expect(page.getByText('客户信用限制已解除')).toBeVisible()
  await expect(drawer.getByText('正常', { exact: true }).last()).toBeVisible()
  await drawer.getByRole('button', { name: '关闭' }).click()

  await page.getByRole('tab', { name: '信用保险' }).click()
  const insuranceRow = page
    .getByRole('row')
    .filter({ hasText: `INS-E2E-${unique}` })
  await expect(insuranceRow).toBeVisible()
  await expect(insuranceRow).toContainText('生效')
  await expect(insuranceRow).toContainText('80.00%')

  expect(apiFailures).toEqual([])
  expect(consoleErrors).toEqual([])
})
