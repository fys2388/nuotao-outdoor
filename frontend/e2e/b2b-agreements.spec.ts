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

test('agreement progress, approval, and rebate approval use real backend state', async ({
  page,
  request,
}) => {
  const consoleErrors: string[] = []
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
  const operatorUsername = `agreement-operator-${unique}`
  const operatorPassword = 'AgreementTest@2026'

  const createUser = await request.post(`${API_URL}/auth/users`, {
    headers: authHeaders(adminToken!),
    data: {
      username: operatorUsername,
      email: `${operatorUsername}@example.com`,
      full_name: 'Agreement E2E Operator',
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

  const agentResponse = await request.post(`${API_URL}/admin/b2b/agents`, {
    headers: authHeaders(adminToken!),
    data: {
      email: `agreement-agent-${unique}@example.com`,
      password: 'AgreementAgent@2026',
      company_name: `Agreement E2E Agent ${unique}`,
      contact_name: 'Agreement Buyer',
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

  const agreementName = `E2E Annual Agreement ${unique}`
  const agreementResponse = await request.post(`${API_URL}/admin/b2b/agreements`, {
    headers: authHeaders(operatorToken),
    data: {
      agent_id: agent.id,
      name: agreementName,
      currency: 'USD',
      effective_from: '2026-01-01',
      effective_to: '2026-12-31',
      target_amount: 200,
      qualification_basis: 'ordered',
      calculation_method: 'retroactive',
      notes: 'Chrome E2E agreement',
    },
  })
  const agreementBody = await agreementResponse.text()
  expect(agreementResponse.status(), agreementBody).toBe(201)
  const agreement = JSON.parse(agreementBody) as {
    id: string
    agreement_number: string
  }

  for (const tier of [
    { min_sales_amount: 0, max_sales_amount: 100, rebate_percent: 1 },
    { min_sales_amount: 100, max_sales_amount: null, rebate_percent: 3 },
  ]) {
    const tierResponse = await request.post(
      `${API_URL}/admin/b2b/agreements/${agreement.id}/tiers`,
      {
        headers: authHeaders(operatorToken),
        data: tier,
      },
    )
    expect(tierResponse.status(), await tierResponse.text()).toBe(201)
  }

  const seedOutput = execFileSync(
    resolve(process.cwd(), '../backend/.venv/Scripts/python.exe'),
    [
      '-m',
      'tests.seed_b2b_order',
      '--agent-id',
      agent.id,
      '--amount',
      '120.00',
      '--order-number',
      `B2B-AGR-${unique}`,
      '--created-at',
      '2026-06-15T10:00:00+00:00',
      '--workspace-id',
      WORKSPACE_ID,
    ],
    {
      cwd: resolve(process.cwd(), '../backend'),
      encoding: 'utf8',
    },
  )
  expect(JSON.parse(seedOutput) as { id: string }).toHaveProperty('id')

  const submitAgreement = await request.post(
    `${API_URL}/admin/b2b/agreements/${agreement.id}/submit`,
    { headers: authHeaders(operatorToken) },
  )
  expect(submitAgreement.status(), await submitAgreement.text()).toBe(200)

  await page.goto('/b2b/agreements')
  await expect(
    page.getByRole('heading', { name: '代理商年度协议与分级返利' }),
  ).toBeVisible()
  await page.getByPlaceholder('搜索协议号或名称').fill(agreementName)
  await page.getByPlaceholder('搜索协议号或名称').press('Enter')
  const row = page.getByRole('row', { name: new RegExp(agreementName) })
  await expect(row).toBeVisible()
  await row.getByRole('button', { name: '查看' }).click()

  await expect(page.getByText(agreement.agreement_number).first()).toBeVisible()
  await expect(page.getByText('待审批').first()).toBeVisible()
  await page.getByRole('button', { name: '审批生效' }).click()
  await expect(page.getByText('年度协议已生效')).toBeVisible()
  await expect(page.getByText('纳入 1 条事实', { exact: false })).toBeVisible()
  await expect(
    page.locator('.ant-statistic-content').filter({ hasText: /120\.00/ }).first(),
  ).toBeVisible()

  const accrualResponse = await request.post(
    `${API_URL}/admin/b2b/agreements/${agreement.id}/rebate-accruals`,
    {
      headers: authHeaders(operatorToken),
      data: {
        period_start: '2026-01-01',
        period_end: '2026-12-31',
      },
    },
  )
  const accrualBody = await accrualResponse.text()
  expect(accrualResponse.status(), accrualBody).toBe(201)
  const accrual = JSON.parse(accrualBody) as { id: string; rebate_amount: number }
  expect(accrual.rebate_amount).toBe(3.6)

  const submitAccrual = await request.post(
    `${API_URL}/admin/b2b/rebate-accruals/${accrual.id}/submit`,
    { headers: authHeaders(operatorToken) },
  )
  expect(submitAccrual.status(), await submitAccrual.text()).toBe(200)

  await page.reload()
  await page.getByPlaceholder('搜索协议号或名称').fill(agreementName)
  await page.getByPlaceholder('搜索协议号或名称').press('Enter')
  const refreshedRow = page.getByRole('row', {
    name: new RegExp(agreementName),
  })
  await expect(refreshedRow).toBeVisible()
  await refreshedRow.getByRole('button', { name: '查看' }).click()
  await expect(page.getByText('待审批', { exact: true }).last()).toBeVisible()
  await page.getByRole('button', { name: '批准' }).click()
  await expect(page.getByText('返利计算单已批准并形成负债')).toBeVisible()
  await expect(page.getByText('已批准').first()).toBeVisible()

  expect(consoleErrors).toEqual([])
})
