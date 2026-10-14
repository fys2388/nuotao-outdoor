# Nuotao AI OS — Git History Remediation Plan

## 0. Scope and hard limits

This document is the **history-remediation plan** for credential-related cleanup.

Hard limits for this phase:
- do **not** run `git filter-repo`
- do **not** run BFG
- do **not** force push
- do **not** rewrite history
- do **not** delete remote refs
- do **not** mutate local branch topology

This document is intentionally a **plan**, not an execution record.

## 1. What this plan covers

The repository contains many credential-shaped references, but the current working tree evidence shows:
- real `.env` files are **not tracked by Git**
- tracked files do contain credential names, placeholders, and several default development values
- workflow files reference GitHub Actions secrets such as `SERVER_HOST`, `SERVER_USER`, `SSH_PRIVATE_KEY`, and `GITHUB_TOKEN`
- runtime production secrets are injected on the server via `EnvironmentFile=/opt/nuotao/backend/.env` in systemd units

So the question is not "was every secret committed?" but:
- **which tracked paths could plausibly contain secret-shaped values in history**
- **which refs could be affected**
- **what must be rotated before any history rewrite**
- **how to verify the rewrite**

## 2. Credential families that may have touched history

| Credential family | Why it may be relevant |
|---|---|
| SSH / root access | workflow files historically referenced `SSH_PRIVATE_KEY` / server access |
| Production JWT signing secret | current code still has a hardcoded development secret in `backend/app/core/security.py` |
| WooCommerce consumer keys | multiple services read env-var credentials; historical examples may have included placeholders or test values |
| WooCommerce webhook secret | default placeholder exists in code and docs |
| Feishu webhook / callback / app secret | service files and workflow files reference these directly |
| Database / Redis credentials | compose and deployment files reference default development values |
| Provider API keys | OpenAI / DeepSeek / SenseNova / DashScope / Volcengine / 1688 / Stripe / PayPal / logistics keys are env-driven |
| GitHub Actions secrets | workflows reference `secrets.*` values |

## 3. Tracked paths that should be treated as risk surfaces

### 3.1 Configuration / runtime defaults

- `backend/app/core/config.py`
- `backend/app/core/security.py`
- `docker-compose.yml`
- `docker-compose.dev.yml`
- `backend/.env.production.template`

Why:
- these files can contain placeholder credentials, development defaults, and env-var wiring

### 3.2 Service integrations that read secrets

- `backend/app/integrations/payment.py`
- `backend/app/integrations/image_gen.py`
- `backend/app/integrations/logistics_provider.py`
- `backend/app/integrations/woocommerce.py`
- `backend/app/services/feishu_approval_service.py`
- `backend/app/services/feishu_notification_service.py`
- `backend/app/services/product_listing_service.py`
- `backend/app/services/product_pipeline_service.py`
- `backend/app/services/woocommerce_sync_service.py`
- `backend/app/services/newton_agent_service.py`
- `backend/app/services/sourcing_1688_service.py`
- `backend/app/services/deployment_service.py`

Why:
- these files show how credentials are loaded and can expose env-var names, fallbacks, or historical implementation choices

### 3.3 Deployment / operations

- `infra/systemd/*.service`
- `.github/workflows/*.yml`
- `.github/workflows/deploy.yml`
- `.github/workflows/server-preflight.yml`
- `.github/workflows/database-backup.yml`
- `.github/workflows/db-migration-and-scheduler.yml`
- `.github/workflows/update-feishu-env.yml`
- `.github/workflows/ops-image-gen-env.yml`
- `.github/workflows/ops-backup-prod-code.yml`

Why:
- deployment files may include environment wiring and secret-name references

### 3.4 Docs and audit artifacts

- `docs/production_secrets_guide.md`
- `docs/deployment_guide.md`
- `docs/multi_environment_guide.md`
- `docs/cloud_deployment_guide.md`
- `docs/development.md`
- `docs/audits/*`

Why:
- docs may contain placeholders, sample credential names, or historical guidance that should be considered sensitive if rewritten into history

### 3.5 Files that may have been changed outside this phase

The current working tree also shows many modified files from previous work. Those are not automatically considered historical leaks, but they should still be reviewed if a history rewrite is later performed.

## 4. Commit-range guidance

A future history rewrite should inspect commit ranges that touched the paths above.

Recommended audit query set:
- `git log --oneline -- backend/app/core/security.py`
- `git log --oneline -- backend/app/core/config.py`
- `git log --oneline -- docker-compose.yml docker-compose.dev.yml`
- `git log --oneline -- backend/.env.production.template`
- `git log --oneline -- backend/app/integrations/payment.py backend/app/integrations/image_gen.py backend/app/integrations/logistics_provider.py`
- `git log --oneline -- backend/app/services/feishu_approval_service.py backend/app/services/feishu_notification_service.py`
- `git log --oneline -- backend/app/services/product_listing_service.py backend/app/services/product_pipeline_service.py backend/app/services/woocommerce_sync_service.py`
- `git log --oneline -- backend/app/services/deployment_service.py`
- `git log --oneline -- infra/systemd .github/workflows docs/production_secrets_guide.md docs/deployment_guide.md`

Important interpretation rules:
- presence of a **name** does not mean presence of a **secret**
- placeholder strings such as `CHANGE_ME`, `dev-webhook-secret-change-me`, and example URLs are not proof of a real production secret leak
- a real secret is a value that should never have been stored in the repository at all

## 5. Refs at risk

If a future rewrite is approved, these refs should be considered at risk:
- the main development branch
- any production deployment branch
- release tags
- hotfix branches that were cut from older history
- any remote-tracking refs that mirror rewritten commits

Practical rule:
- treat **all** branches and tags that contain the credential-bearing paths as rewrite candidates until proven otherwise

## 6. History rewrite prerequisites

Do **not** rewrite history until these conditions are met:

1. **Rotation is complete for every real credential that may have been in history.**
2. **Provider-side verification is complete for the new credentials.**
3. **The old credential has been revoked or disabled at the provider.**
4. **A full commit-range audit has been performed for the paths listed above.**
5. **The list of affected refs has been confirmed.**
6. **A rollback snapshot has been prepared outside the repository.**
7. **The team has an explicit change window for force-push coordination.**

## 7. Rotation-first rule

For every credential family, use this order:

1. rotate the real provider secret
2. update runtime environment injection
3. verify the new credential works
4. verify the old credential fails
5. then consider whether history needs to be rewritten

This avoids the common failure mode of cleaning history while the leaked credential is still live.

## 8. Post-rewrite verification method

After any future rewrite, verify:

1. the rewritten branch no longer contains the target secret-bearing blobs
2. the replacement history still builds
3. CI still passes on the rewritten branch
4. deployment refs resolve to the rewritten topology
5. no remote still points at the old pre-rewrite objects
6. the new credential is the only one accepted by providers
7. the old credential is rejected

Suggested verification checks:
- rebuild the backend after the rewrite
- run the same targeted auth/security/woocommerce tests used in this phase
- run a clean checkout from the rewritten ref
- verify systemd / workflow config still points at the same runtime env path

## 9. What this plan does **not** claim

This plan does **not** claim:
- that real production secrets were committed
- that any branch is clean
- that any tag is safe
- that any credential is already rotated
- that history rewrite is necessary

It only identifies the **risk surfaces** and the **conditions** for later remediation.

## 10. Immediate action status

Current status:
- **No rewrite performed**
- **No force push performed**
- **No remote refs mutated**

This is the correct state for this phase.

## 11. Credential inventory to rotate before any rewrite

At minimum, rotate or explicitly defer:
- `PROD-SH-01`
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

## 12. Reference to the paired runbook

For the full rotation matrix and verification checklist, see:

- `docs/audits/CREDENTIAL_ROTATION_RUNBOOK.md`
