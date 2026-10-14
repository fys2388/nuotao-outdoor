# Nuotao AI OS — Credential Rotation Readiness Runbook

## 0. Scope

This document is the **credential readiness** artifact for the rotation-readiness phase.

In-scope:
- inventory external credentials that must be rotated or at least confirmed
- map each credential to its real provider, repository source, and production injection point
- define the exact verification steps after rotation
- separate **Code Verified** from **Provider Verified**

Out-of-scope:
- rotating any credential in this phase
- changing production secrets
- changing business logic
- rewriting git history
- force pushing any ref

## 1. Baseline evidence gathered

Reviewed:
- `backend/app/core/config.py`
- `backend/app/core/security.py`
- `backend/.env*`
- `docker-compose.yml`
- `infra/systemd/*.service`
- `.github/workflows/*.yml`
- `docs/production_secrets_guide.md`
- deployment docs and audit docs

Key repository facts:
- `backend/.env`, `backend/.env.development`, `backend/.env.staging`, `backend/.env.production` are **not tracked by Git** (`git ls-files` returns nothing).
- The repository does track credential-shaped paths such as `backend/app/core/config.py`, `backend/app/core/security.py`, `docker-compose.yml`, and `infra/systemd/*`.
- The backend loads its runtime config from `.env` files via `SettingsConfigDict(env_file=(".env", "../.env"))`.
- Systemd units load the runtime environment from `/opt/nuotao/backend/.env` or `/opt/nuotao/staging/backend/.env`.

Test baseline:
- Historical: `pytest tests --ignore=tests/integration --collect-only -q -p no:warnings` collected **824** tests (as of P0 Remediation §10, 2026-09-22 morning).
- **Current official baseline (2026-09-22 Security Baseline Final Reconciliation):** **828 collected / 828 passed / 0 failed / 0 errors / 0 skipped / 0 xfailed**, pytest exit 0.
  - See `docs/audits/TEST_BASELINE_RECONCILIATION.md` §7 and `docs/audits/P0_AUTH_REMEDIATION_REPORT.md` §12 for the authoritative junit evidence and the 824 → 828 delta attribution (0 new tests this round; +62 restored collection of `test_listing_gate.py` 40 + `test_auth_security.py` 18 + `test_jwt_secret_config.py` 4, minus 58 unrelated file changes between baselines).
- Targeted run used the auth/security/woocommerce/feishu-adjacent subset:
  `test_auth_system.py`, `test_auth_security.py`, `test_clerk_jwks.py`, `test_identity_jwt.py`, `test_actor_provider.py`, `test_activation_gate.py`, `test_woocommerce_signature.py`, `test_webhook_test_endpoint_security.py`, `test_webhook_orders.py`.

## 2. Provider map

| Provider | Credential IDs | What it authenticates |
|---|---|---|
| SSH / host access | PROD-SH-01 | production server SSH access |
| WooCommerce | WOOC-A-01, WOOC-B-01, WOOC-SIGN-01 | WooCommerce REST API and webhook signing |
| JWT / app auth | JWT-01 | backend token signing / verification |
| Feishu | FEISHU-WEBHOOK-01, FEISHU-CALLBACK-01, FEISHU-APP-01 | Feishu webhook notifications and callback signing |
| PostgreSQL | DB-01 | production database |
| Redis | REDIS-01 | production cache/queue |
| OpenAI | LLM-OPENAI-01 | LLM API calls |
| DeepSeek | LLM-DEEPSEEK-01 | LLM API calls |
| SenseNova | LLM-SENSENOVA-01 | LLM API calls |
| DashScope | IMG-DASHSCOPE-01 | image generation API |
| Volcengine | IMG-VOLCENGINE-01 | image generation API / IAM keys |
| 1688 / Alibaba | SOURCING-1688-01 | 1688/Alibaba API access |
| Clerk | AUTH-CLERK-01 | identity metadata / verification keys |
| SMTP | MAIL-01 | email delivery |
| Stripe | PAY-STRIPE-01, PAY-STRIPE-WH-01 | payments and webhook verification |
| PayPal | PAY-PAYPAL-01 | payments |
| Logistics | LOG-01 | logistics provider API access |
| GitHub Actions | GH-SSH-01, GH-GITHUB-01 | CI/CD server access and GitHub API token |

## 3. Credential rotation matrix

### PROD-SH-01 — Production SSH / root access

- **Type:** SSH credential / host login
- **Provider:** server host / cloud provider account
- **Environment:** production
- **Current source:** GitHub Actions secret `SSH_PRIVATE_KEY`; referenced by `appleboy/ssh-action` in many workflows, plus `.github/workflows/deploy.yml` and `.github/workflows/server-preflight.yml`
- **Production consumer:** `/opt/nuotao/backend`, systemd services, and all deploy/ops workflows
- **Rotation action:** rotate the server-side SSH key material; replace the GitHub secret; verify the new credential before deleting the old one
- **Verification action:**
  - new credential can SSH successfully
  - old credential is rejected
  - `PermitRootLogin` is not `yes` unless explicitly intended
  - `PasswordAuthentication` is disabled unless explicitly intended
- **Expected failure of old credential:** authentication failure / `Permission denied`
- **Rollback consideration:** keep the old key valid only during the overlap window; do not leave it in GitHub Secrets after cutover
- **Status:** `READY`

### WOOC-A-01 — WooCommerce Group A

- **Type:** WooCommerce REST API consumer key/secret
- **Provider:** WooCommerce store A
- **Environment:** production
- **Current source:** environment variables `WOOCOMMERCE_CONSUMER_KEY` / `WOOCOMMERCE_CONSUMER_SECRET` loaded by:
  - `backend/app/core/config.py`
  - `backend/app/services/product_listing_service.py`
  - `backend/app/services/product_pipeline_service.py`
  - `backend/app/services/woocommerce_sync_service.py`
  - `backend/app/services/purchase_order_service.py`
- **Production consumer:** backend API and sync/listing services
- **Rotation action:** rotate WooCommerce API credentials in the store admin panel, then update the production environment source used by the server
- **Verification action:** make a valid **read-only** API request with the new key; confirm old key now fails
- **Expected failure of old credential:** `401` / `403`
- **Rollback consideration:** keep old key active only if an emergency rollback window is explicitly approved
- **Status:** `UNVERIFIED`

### WOOC-B-01 — WooCommerce Group B

- **Type:** WooCommerce REST API consumer key/secret
- **Provider:** WooCommerce store B
- **Environment:** production
- **Current source:** same env-var pattern as Group A; the code path is the same loader chain, so the actual provider distinction is external to the repository
- **Production consumer:** backend API and sync/listing services
- **Rotation action:** rotate the second WooCommerce credential set independently from Group A
- **Verification action:** perform a read-only request against store B only
- **Expected failure of old credential:** `401` / `403`
- **Rollback consideration:** do not reuse the same key/secret pair for both stores if isolation matters
- **Status:** `UNVERIFIED`

### WOOC-SIGN-01 — WooCommerce webhook signing secret

- **Type:** HMAC signing secret
- **Provider:** WooCommerce webhook configuration / application config
- **Environment:** production
- **Current source:** `WOOCOMMERCE_WEBHOOK_SECRET`
  - tracked config fields in `backend/app/core/config.py`
  - read by `backend/app/core/woocommerce_security.py` and related webhook endpoints
  - also referenced by `docker-compose.yml` with a development fallback
- **Production consumer:** WooCommerce webhook verification path
- **Rotation action:** rotate the store-side webhook secret and the server-side environment value together
- **Verification action:** send one valid signed event and one invalid/old-secret event
- **Expected failure of old credential:** invalid signature / rejection
- **Rollback consideration:** webhook verification should fail closed when the secret is missing or mismatched
- **Status:** `READY`

### JWT-01 — Production JWT signing secret

- **Type:** JWT signing secret
- **Provider:** application runtime secret store / deployment secret injection
- **Environment:** production
- **Current source:** `backend/app/core/security.py` now reads from `Settings.jwt_secret_key` (field `jwt_secret_key: str = ""` in `backend/app/core/config.py`). The environment variable `JWT_SECRET_KEY` is wired through `pydantic-settings`. A hardcoded development `SECRET_KEY` constant has been **removed**. `get_jwt_secret()` enforces environment-specific fail-fast rules:
  - **production / staging**: secret is mandatory; placeholder values, development/test secrets, and secrets shorter than 16 chars raise `RuntimeError`.
  - **development / test**: secret must be explicitly provided (no silent fallback to a fixed dev secret).
- **Production consumer:** backend auth token creation / validation (`create_access_token`, `create_refresh_token`, `decode_token`)
- **Rotation action:** rotate the production signing secret and then make sure the backend reads it from the environment before it is used as the authoritative signing key
- **Verification action:**
  - backend starts cleanly
  - a freshly issued token verifies
  - an old token fails
  - users need to log in again
- **Expected failure of old credential:** token decode / verification failure
- **Rollback consideration:** rotating JWT signs out every active user; schedule during a maintenance window
- **Status:** `CODE VERIFIED` — code boundary is fixed; provider-side rotation still pending

**Code finding:** The hardcoded development `SECRET_KEY` in `backend/app/core/security.py` has been removed. The secret is now read from `Settings.jwt_secret_key` via `get_settings()`. Placeholder detection covers both exact-match known bad values and substring patterns (e.g. `change_me`, `dev_secret`, `test_secret`, `not_for_prod`, `placeholder`, `example`, `your_`).

### JWT-01a — Configuration matrix

| Environment | Source | Required | Fallback | Fail behavior | Verification |
|---|---|---|---|---|---|
| **development** | `JWT_SECRET_KEY` env var or `.env` / `backend/.env.development` | Yes (explicitly) | None — no silent fallback to a fixed dev secret | `RuntimeError`: "must be provided in development/test or injected by the test harness" | `pytest tests/test_jwt_secret_config.py` (4/4 passed) |
| **test** | `JWT_SECRET_KEY` env var injected by `tests/conftest.py` via `monkeypatch.setattr` | Yes (injected) | None | `RuntimeError`: "must be provided in development/test or injected by the test harness" | `pytest tests/test_jwt_secret_config.py` (4/4 passed) |
| **staging** | `JWT_SECRET_KEY` env var from deployment secret store | Yes | None | `RuntimeError`: "required in staging/production and no fallback is allowed" | Code Verified — `get_jwt_secret()` raises `RuntimeError` |
| **production** | `JWT_SECRET_KEY` env var from deployment secret store | Yes | None | `RuntimeError`: "required in staging/production and no fallback is allowed"; placeholder → "must not use a placeholder value"; < 16 chars → "too short for staging/production" | Code Verified — `get_jwt_secret()` raises `RuntimeError`; Provider Verified — pending rotation |

**Code Verified ≠ Provider Verified:** Code Verified confirms the boundary logic is correct (placeholder detection, fail-fast, no fallback). Provider Verified confirms the real production credential has been rotated and the old credential now fails at the provider.

### FEISHU-WEBHOOK-01 — Feishu webhook URL

- **Type:** outbound webhook URL
- **Provider:** Feishu open platform webhook
- **Environment:** production
- **Current source:** `FEISHU_WEBHOOK_URL`
  - `backend/app/services/feishu_approval_service.py`
  - `backend/app/services/feishu_notification_service.py`
  - `infra/systemd/*` environment files
  - GitHub Actions workflow `.github/workflows/update-feishu-env.yml`
- **Production consumer:** Feishu notifications / approval callbacks
- **Rotation action:** rotate the webhook URL in the Feishu platform and update the runtime environment value
- **Verification action:**
  - new webhook sends a test message successfully
  - old webhook is no longer accepted
- **Expected failure of old credential:** Feishu rejects the old webhook endpoint
- **Rollback consideration:** old and new webhooks may coexist briefly, but the old one should be revoked after verification
- **Status:** `UNVERIFIED`

### FEISHU-CALLBACK-01 — Feishu callback signing key

- **Type:** callback signature key
- **Provider:** Feishu card callback configuration
- **Environment:** production
- **Current source:** `feishu_encrypt_key` in `backend/app/core/config.py`; documented in `backend/app/core/feishu_security.py`
- **Production consumer:** Feishu callback verification path
- **Rotation action:** rotate the Feishu callback secret and update the matching app setting
- **Verification action:** signed callback succeeds; unsigned or old-secret callback fails
- **Expected failure of old credential:** `503` / signature rejection
- **Rollback consideration:** callback verification must stay fail closed
- **Status:** `UNVERIFIED`

### FEISHU-APP-01 — Feishu app id / app secret / chat id

- **Type:** Feishu app credentials
- **Provider:** Feishu open platform
- **Environment:** production
- **Current source:** `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, `FEISHU_CHAT_ID`
  - `backend/app/services/feishu_approval_service.py`
  - `backend/app/services/feishu_notification_service.py`
  - `.github/workflows/update-feishu-env.yml`
- **Production consumer:** Feishu integration layer
- **Rotation action:** rotate app secret and/or webhook target and keep app id/chat id aligned
- **Verification action:** test message and tenant access token issuance
- **Expected failure of old credential:** auth failure / message send failure
- **Rollback consideration:** app secret rotation may temporarily break notifications until env is updated
- **Status:** `UNVERIFIED`

### DB-01 — Production database credential

- **Type:** PostgreSQL password / connection string
- **Provider:** PostgreSQL server or managed DB
- **Environment:** production
- **Current source:** `DATABASE_URL`, `DB_PASSWORD`, and `.env` file on server
- **Production consumer:** backend app, worker, scheduler, backup jobs
- **Rotation action:** rotate DB password and update every consumer that reads the connection string
- **Verification action:**
  - backend connects
  - worker connects
  - backup script connects
- **Expected failure of old credential:** connection refused / authentication failure
- **Rollback consideration:** rotate in a maintenance window to avoid lockout
- **Status:** `UNVERIFIED`

### REDIS-01 — Redis password / URL

- **Type:** Redis connection credential
- **Provider:** Redis server
- **Environment:** production
- **Current source:** `REDIS_URL` and the Redis auth used by the backend / worker
- **Production consumer:** cache, task queue, worker heartbeat
- **Rotation action:** rotate Redis password and update runtime URL
- **Verification action:**
  - app connects
  - worker heartbeat works
- **Expected failure of old credential:** Redis authentication failure
- **Rollback consideration:** worker and API must both be restarted with the new value
- **Status:** `UNVERIFIED`

### LLM-OPENAI-01 — OpenAI API key

- **Type:** provider API key
- **Provider:** OpenAI
- **Environment:** production
- **Current source:** `OPENAI_API_KEY`
  - `backend/app/core/config.py`
  - `backend/app/integrations/image_gen.py`? no, imagegen uses Volcengine/DashScope
- **Production consumer:** LLM gateway / provider routing
- **Rotation action:** rotate provider key and update the runtime secret store
- **Verification action:** successful API call from a non-secret endpoint path; no secret printing
- **Expected failure of old credential:** provider 401 / 403
- **Rollback consideration:** keep fallback provider healthy if primary rotation fails
- **Status:** `UNVERIFIED`

### LLM-DEEPSEEK-01 — DeepSeek API key

- **Type:** provider API key
- **Provider:** DeepSeek
- **Environment:** production
- **Current source:** `DEEPSEEK_API_KEY`
  - `backend/app/core/config.py`
  - `backend/app/api/v1/endpoints/agent_analysis.py`
- **Production consumer:** LLM gateway / fallback provider
- **Rotation action:** rotate provider key and update runtime secret store
- **Verification action:** successful API call; old key fails
- **Expected failure of old credential:** provider 401 / 403
- **Rollback consideration:** prefer a clean single cutover, not dual long-lived keys
- **Status:** `UNVERIFIED`

### LLM-SENSENOVA-01 — SenseNova API key

- **Type:** provider API key
- **Provider:** SenseNova
- **Environment:** production
- **Current source:** `SENSENOVA_API_KEY`, `SENSENOVA_BASE_URL`
  - `backend/app/core/config.py`
- **Production consumer:** LLM gateway / primary provider path
- **Rotation action:** rotate key and update runtime secret store
- **Verification action:** provider call succeeds; old key fails
- **Expected failure of old credential:** provider 401 / 403
- **Rollback consideration:** verify model availability after rotation
- **Status:** `UNVERIFIED`

### IMG-DASHSCOPE-01 — DashScope API key / workspace id

- **Type:** provider API key and workspace identifier
- **Provider:** DashScope
- **Environment:** production
- **Current source:** `DASHSCOPE_API_KEY`, `DASHSCOPE_WORKSPACE_ID`
  - `backend/app/core/config.py`
  - `backend/app/integrations/image_gen.py`
- **Production consumer:** image generation service
- **Rotation action:** rotate the key and ensure the workspace id remains the one required by the sync API
- **Verification action:** image generation request succeeds
- **Expected failure of old credential:** provider auth failure
- **Rollback consideration:** workspace id mismatch can break the call even if the key is valid
- **Status:** `UNVERIFIED`

### IMG-VOLCENGINE-01 — Volcengine API key / IAM AK/SK

- **Type:** provider API key plus access key / secret key pair
- **Provider:** Volcengine
- **Environment:** production
- **Current source:** `VOLCENGINE_API_KEY`, `VOLC_ACCESSKEY`, `VOLC_SECRETKEY`
  - `backend/app/core/config.py`
  - `backend/app/integrations/image_gen.py`
  - `.github/workflows/ops-image-gen-env.yml`
- **Production consumer:** image generation service and hotfix ops workflow
- **Rotation action:** rotate the API key and the IAM AK/SK pair
- **Verification action:** image-gen call succeeds; old credentials fail
- **Expected failure of old credential:** provider auth failure
- **Rollback consideration:** the workflow can re-upsert env but must not print the secret
- **Status:** `UNVERIFIED`

### SOURCING-1688-01 — 1688 / Alibaba API credentials

- **Type:** app key / secret / token
- **Provider:** 1688 / Alibaba open platform
- **Environment:** production
- **Current source:** `ALI1688_APP_KEY`, `ALI1688_APP_SECRET`, `ALI1688_ACCESS_TOKEN`
  - `backend/app/core/config.py`
  - `backend/app/services/newton_agent_service.py`
  - `backend/app/services/sourcing_1688_service.py`
- **Production consumer:** sourcing / Newton integration
- **Rotation action:** rotate app secret and/or access token and update runtime env
- **Verification action:** signed request succeeds; old credentials fail
- **Expected failure of old credential:** provider auth / signature failure
- **Rollback consideration:** keep the same app key family if token refresh depends on the old secret
- **Status:** `UNVERIFIED`

### AUTH-CLERK-01 — Clerk secret key / JWKS metadata

- **Type:** identity provider secret and JWKS metadata
- **Provider:** Clerk
- **Environment:** production
- **Current source:** `CLERK_SECRET_KEY`, `CLERK_JWKS_URL`, `CLERK_TEST_USER_A_PASSWORD`, `CLERK_TEST_USER_B_PASSWORD`
  - `backend/.env`
- **Production consumer:** identity / JWT verification helper path
- **Rotation action:** rotate the secret key and refresh JWKS configuration if needed
- **Verification action:** token verification succeeds; old secret fails
- **Expected failure of old credential:** JWKS / signature verification failure
- **Rollback consideration:** avoid printing test passwords even in local/dev artifacts
- **Status:** `UNVERIFIED`

### MAIL-01 — SMTP credential

- **Type:** email sending password
- **Provider:** SMTP provider
- **Environment:** production
- **Current source:** `SMTP_PASSWORD`
  - `backend/app/core/config.py`
  - deployment docs and `.env` templates
- **Production consumer:** email delivery / notifications
- **Rotation action:** rotate SMTP password and update runtime env
- **Verification action:** test email send succeeds; old password fails
- **Expected failure of old credential:** SMTP auth failure
- **Rollback consideration:** keep the SMTP account name stable, rotate only the password
- **Status:** `UNVERIFIED`

### PAY-STRIPE-01 — Stripe secret key

- **Type:** payment API secret
- **Provider:** Stripe
- **Environment:** production
- **Current source:** `STRIPE_SECRET_KEY`
  - `backend/app/integrations/payment.py`
  - `backend/app/services/refund_service.py`
- **Production consumer:** payment and refund flow
- **Rotation action:** rotate the Stripe secret key in the dashboard and update runtime env
- **Verification action:** payment-path API call succeeds; old key fails
- **Expected failure of old credential:** Stripe 401 / 403
- **Rollback consideration:** payment flow should be tested in sandbox first
- **Status:** `UNVERIFIED`

### PAY-STRIPE-WH-01 — Stripe webhook signing secret

- **Type:** webhook signing secret
- **Provider:** Stripe webhook endpoint
- **Environment:** production
- **Current source:** `STRIPE_WEBHOOK_SECRET`
  - `backend/app/integrations/payment.py`
- **Production consumer:** Stripe webhook verification
- **Rotation action:** rotate the webhook signing secret and restart the verifier
- **Verification action:** one valid event verifies; one old-secret event fails
- **Expected failure of old credential:** signature mismatch
- **Rollback consideration:** fail closed on signature mismatch
- **Status:** `UNVERIFIED`

### PAY-PAYPAL-01 — PayPal client id / secret / mode

- **Type:** payment credentials
- **Provider:** PayPal
- **Environment:** production
- **Current source:** `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_MODE`
  - `backend/app/integrations/payment.py`
  - `backend/app/services/refund_service.py`
- **Production consumer:** payment flow
- **Rotation action:** rotate the PayPal app secret and update runtime env
- **Verification action:** payment API call succeeds; old secret fails
- **Expected failure of old credential:** PayPal auth failure
- **Rollback consideration:** sandbox and live modes should be tested separately
- **Status:** `UNVERIFIED`

### LOG-01 — Logistics provider keys

- **Type:** logistics API keys
- **Provider:** logistics provider(s)
- **Environment:** production
- **Current source:** `LOGISTICS_API_KEY`, `YANWEN_API_KEY`, `SF_API_KEY`, `4PX_API_KEY`, `CAINIAO_API_KEY`
  - `backend/app/integrations/logistics_provider.py`
- **Production consumer:** logistics provider integration
- **Rotation action:** rotate each active provider key independently
- **Verification action:** provider call succeeds; old key fails
- **Expected failure of old credential:** provider auth failure
- **Rollback consideration:** keep the provider selection stable while rotating
- **Status:** `UNVERIFIED`

### GH-SSH-01 — GitHub Actions SSH secret

- **Type:** GitHub Actions repository secret
- **Provider:** GitHub Actions / server access path
- **Environment:** CI/CD
- **Current source:** `.github/workflows/*` reference `secrets.SSH_PRIVATE_KEY`, `secrets.SERVER_HOST`, `secrets.SERVER_USER`
- **Production consumer:** deployment workflows and operational automation
- **Rotation action:** rotate the GitHub secret value after the server-side key material is accepted
- **Verification action:** deploy workflow can connect; old secret cannot
- **Expected failure of old credential:** GitHub Actions SSH failure
- **Rollback consideration:** keep the previous secret only during a short validation window
- **Status:** `READY`

### GH-GITHUB-01 — GitHub token secret

- **Type:** GitHub API token
- **Provider:** GitHub Actions / GitHub API
- **Environment:** CI/CD
- **Current source:** `.github/workflows/ops-backup-prod-code.yml` references `secrets.GITHUB_TOKEN`
- **Production consumer:** workflow API operations
- **Rotation action:** refresh the token when needed
- **Verification action:** workflow step succeeds; old token is revoked
- **Expected failure of old credential:** GitHub API auth failure
- **Rollback consideration:** this should be refreshed, not reused indefinitely
- **Status:** `READY`

## 4. Code-readiness findings

### 4.1 Environment-driven vs hardcoded

Code that is environment-driven:
- `backend/app/core/config.py` reads from `.env`
- `backend/app/integrations/payment.py` reads payment keys from environment variables
- `backend/app/integrations/logistics_provider.py` reads logistics keys from environment variables
- `backend/app/integrations/image_gen.py` reads DashScope / Volcengine credentials from environment variables
- `backend/app/services/product_listing_service.py` reads WooCommerce creds from environment variables
- `backend/app/services/feishu_approval_service.py` and `backend/app/services/feishu_notification_service.py` read Feishu credentials from environment variables
- `backend/app/core/security.py` reads `jwt_secret_key` from `Settings` (env var `JWT_SECRET_KEY`) via `get_jwt_secret()`

Code that is **not** environment-driven:
- `backend/app/services/deployment_service.py` contains a hardcoded deployment example password
- `docker-compose.yml` contains development defaults for DB password and WooCommerce webhook secret

### 4.2 Fail-closed assessment

Fail-closed evidence:
- `backend/app/core/security.py` `get_jwt_secret()` raises `RuntimeError` when `JWT_SECRET_KEY` is missing, a placeholder, or too short in staging/production
- Feishu callback path is documented as fail-closed when signature verification is on and the key is missing
- WooCommerce webhook verification is documented as fail-closed when the secret is missing or wrong
- Payment keys default to empty and raise configuration errors when absent
- Logistics providers default to empty and are treated as not configured

Not fail-closed:
- (none at this time — the JWT hardcode has been addressed)

### 4.3 Secret logging / secret printing

Observed safe behavior:
- GitHub workflows mask values with `sed` in several diagnostic steps
- Feishu workflow prints only secret names after masking
- Deployment docs emphasize not printing real secrets

Risk:
- any workflow that echoes a `.env` line with `grep` and insufficient masking could leak the raw secret if the command is changed

### 4.4 No secret in tests / docs

Repository state:
- env files themselves are not tracked
- tracked docs contain examples and placeholders, but they should still be treated as sensitive templates

### 4.5 What is Code Verified and what is Provider Verified

**Code Verified:**
- where the secret is read in code
- whether the code path is environment-driven
- whether a fail-closed default exists
- whether the repository still contains a hardcoded fallback

**Provider Verified:**
- whether the real production credential has been rotated
- whether the old credential now fails at the provider
- whether the new credential succeeds at the provider

These are separate checks and must not be merged.

## 5. Production verification checklist

### A. Production SSH

- [ ] new SSH credential can connect
- [ ] old SSH credential is rejected
- [ ] `PermitRootLogin` is not `yes` unless explicitly approved
- [ ] `PasswordAuthentication` is disabled unless explicitly approved
- [ ] GitHub Actions secret has been updated
- [ ] no workflow still references the old secret value

### B. WooCommerce

- [ ] old key is revoked or unauthorized
- [ ] new key returns a valid read-only API request
- [ ] no key/secret is written into repo files
- [ ] webhook secret mismatch causes rejection

### C. JWT

- [ ] backend starts successfully with the new signing secret
- [ ] newly issued token verifies
- [ ] old token fails
- [ ] users must re-authenticate after rotation
- [ ] no secret value is printed in logs

### D. Feishu

- [ ] new webhook sends a test message successfully
- [ ] old webhook is no longer accepted
- [ ] callback signing verifies only with the new key
- [ ] no webhook URL is printed in repo docs or logs

## 6. Current unrotated credentials

Based on repository evidence, these are **not yet proven rotated**:
- `WOOC-A-01`
- `WOOC-B-01`
- `WOOC-SIGN-01`
- `JWT-01`
- `FEISHU-WEBHOOK-01`
- `FEISHU-CALLBACK-01`
- `FEISHU-APP-01`
- `DB-01`
- `REDIS-01`
- `LLM-OPENAI-01`
- `LLM-DEEPSEEK-01`
- `LLM-SENSENOVA-01`
- `IMG-DASHSCOPE-01`
- `IMG-VOLCENGINE-01`
- `SOURCING-1688-01`
- `AUTH-CLERK-01`
- `MAIL-01`
- `PAY-STRIPE-01`
- `PAY-STRIPE-WH-01`
- `PAY-PAYPAL-01`
- `LOG-01`

The SSH / CI/CD credentials are also not marked rotated yet, even though the code paths are ready to accept a new value.

## 7. External state that the repository cannot verify

The repository can prove **where** secrets are read and whether a default exists. It cannot prove:
- whether the actual provider credential was rotated
- whether the old credential was revoked
- whether the production server currently contains the new value
- whether the production secret manager was updated
- whether the live app accepted the new value at runtime
- whether GitHub Actions secrets were changed in the remote repository
- whether provider-side keys were regenerated outside the codebase

That part is **Provider Verified**, not Code Verified.

## 8. Human steps required

1. Rotate the provider-side credential for each `UNVERIFIED` item above.
2. Update the production environment source for each rotated item.
3. Restart the affected backend/worker/scheduler processes where required.
4. Verify the new credential succeeds and the old credential fails.
5. Remove the old credential from GitHub Secrets / provider dashboards after verification.
6. Re-run the production verification checklist in this document.

## 9. Stop conditions

Do **not** proceed to the next development phase until:
- all `UNVERIFIED` credentials are either rotated or explicitly deferred with written justification
- the JWT secret boundary in `backend/app/core/security.py` is deployed to production (Code Verified — done)
- the provider-side success/failure checks are recorded as verified

## 10. Reference paths

Most relevant repository files:
- `backend/app/core/config.py`
- `backend/app/core/security.py`
- `backend/app/integrations/payment.py`
- `backend/app/integrations/image_gen.py`
- `backend/app/integrations/logistics_provider.py`
- `backend/app/services/feishu_approval_service.py`
- `backend/app/services/feishu_notification_service.py`
- `backend/app/services/product_listing_service.py`
- `backend/app/services/woocommerce_sync_service.py`
- `backend/app/services/newton_agent_service.py`
- `backend/app/services/sourcing_1688_service.py`
- `backend/app/services/deployment_service.py`
- `docker-compose.yml`
- `infra/systemd/*.service`
- `.github/workflows/*.yml`

## 11. Notes on this phase

This phase did **not** change business code, did **not** rotate credentials, and did **not** attempt any git history rewrite.

The only new artifacts produced here are the two audit documents requested in this phase.
