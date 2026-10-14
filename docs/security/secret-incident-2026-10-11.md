# 安全事故记录 — WooCommerce API 密钥泄露（2026-10-11）

> **状态**：仓库内密钥已全部清除；GitHub 历史**尚未**重写；密钥**必须由你**在
> WooCommerce 后台吊销。文档中只保留密钥前缀用于比对，不含完整值。

---

## 1. 事故概要

| 项目 | 内容 |
|---|---|
| 发现时间 | 2026-10-11 07:14:34 UTC |
| 发现方式 | GitGuardian「好撒玛利亚人计划」邮件告警 |
| 告警类型 | WooCommerce API 密钥 |
| 告警仓库 | `fys2388/nuotao-outdoor`（公开仓库） |
| 直接源头 | `docs/product_listing_sop_v1.0.md` —— 一份**文档**里写了真实密钥 |
| 实际影响 | 远超告警本身：共发现 **13 类、18 个凭据**被硬编码在 **175+ 个文件**中 |
| 严重度 | **严重**（可读写全部 WooCommerce 商品数据 + 直接访问 PostgreSQL + **可伪造管理员令牌**） |

### 为什么 GitGuardian 只报了一个？

因为它只扫 **Git 历史**里的**已知密钥格式**。你的告警命中的是 `ck_e87177ab…`，
它恰好存在于那份**被追踪的**文档里。

剩下的没被报出来，原因各有不同：

- **JWT SECRET_KEY**：格式是 `nuotao-ai-os-dev-secret-key-...`，不符合任何已知
  密钥模式，通用扫描器认不出来。
- **PostgreSQL 密码、SSH 密码**：随机字符串，没有厂商前缀，**没有任何扫描器能靠
  模式识别它们**——只能靠人眼或熵值检测。
- **第二套、第四套 WooCommerce 密钥**：在**未被追踪**的本地脚本里，根本不在
  Git 历史中，GitGuardian 看不到。
- **3 把 WordPress 应用密码**：`xxxx xxxx xxxx xxxx xxxx xxxx` 这种空格分隔格式
  不在标准检测规则里。
- **SenseNova / Agnes AI key**：`sk-` 前缀被当作 OpenAI key 家族处理，但长度和
  结构不同，可能没触发。

**结论**：依赖自动扫描是不够的。你的 `.gitignore` 第 44 行自己记着一段历史——
*「曾误提交 142 个，其中 execute5_final.py 含 DELETE 语句，在生产库上删掉了
1180 条采购单」*。这次是第 N 次了。

---

## 2. 泄露凭据完整清单

### 2.1 WooCommerce REST API 密钥（4 套）

| 编号 | Consumer Key 前缀 | 位置 | 是否在 GitHub |
|---|---|---|---|
| A | `ck_e87177ab…` | `docs/product_listing_sop_v1.0.md` + 24 个本地脚本 | ✅ **是**（文档） |
| B | `ck_3644da6e…` | `check_cjk_gate.py`、`check_cjk_gate2.py` | ❌ 仅本地 |
| C | `ck_483264900…` | `backend/image_processor_api.py` | ✅ **是** |
| D | `ck_52a9319d…` | `_local_dev.env`（注释标明是 staging 真实凭据） | ❌ 仅本地 |

### 2.2 其他泄露凭据

| 类型 | 位置 | 是否在 GitHub | 风险 |
|---|---|---|---|
| **WordPress 应用密码**（`fys2388@gmail.com`） | `deployment/DEPLOY_WORDPRESS_PLUGIN.md`、`deployment/deploy-wordpress-plugin.sh`、`docs/product_listing_sop_v1.0.md`、`docs/fix_system_issues_20261011.md`、`docs/production_validation_report_20261011.md` + 9 个本地脚本 | ⚠️ 需确认 | 可登录后台、改主题、装插件、**读取全部订单** |
| **PostgreSQL 密码** | `backend/cleanup_failed_suggestions.py`（×2）、`backend/deploy_and_cleanup.py`、`check_cjk_gate*.py` | ✅ **是** | 直接读写业务库 |
| **Brevo SMTP Key** | `backend/test-smtp-auth.py` | ❌ 仅本地 | 可以你的名义发邮件（含**密码重置钓鱼**） |
| **Webhook Secret** | `_local_dev.env`、`webhook_secret.txt` | ❌ 仅本地 | 可伪造 HMAC 签名推送假数据 |
| **Agnes AI 生图 API Key**（`sk-6ZoRZLvo…`） | `docs/product_listing_sop_v1.0.md`（3 处）+ 21 个本地脚本 + 2 个 backend 脚本 | ✅ **是**（文档） | 盗用你的额度跑生图，**持续产生费用** |
| 🔴 **JWT SECRET_KEY**（`nuotao-ai-os-dev-secret-key…`） | `backend/app/core/security.py` —— **主应用代码** | ✅ **是** | **最严重**：可伪造任意管理员 access/refresh token，等于拿到后台全权 |
| 🔴 **第二个 JWT 签名密钥**（`o4Deqs9kpV…`，64 字符） | `test_import_api.sh` 等 8 个 shell 脚本 | ❌ 仅本地（`/*.sh` 被忽略） | 同样是 JWT 签名密钥，用于给 API 造 admin token。如果它也是生产在用的那把，危害等同上一条 |
| 🔴 **Alertmanager SMTP 密码**（`security@nuotaooutdoor.com`） | `infra/alertmanager.yml` —— **`infra/` 不在 `.gitignore` 里** | ✅ **很可能已上 GitHub** | 安全告警邮箱的口令；可用于冒充 security@ 发件 |
| 🔴 **Grafana 数据源 DB 密码**（`REDACTED_DB_PASSWORD`） | `infra/grafana-datasources.yml` —— `.yml` 在 `infra/` 下**可提交** | ✅ **很可能已上 GitHub** | 直接访问业务数据库 |
| 🔴 **Grafana 管理员密码**（`NUOTA0_GRAFANA_ADMIN_PASSWORD`） | `infra/deploy_monitoring.sh` —— 少了 `$`，被当字面量写入配置 | ✅ **很可能已上 GitHub** | 监控后台管理员权限 |
| 🔴 **WordPress 应用密码（第 2 把）**（`7g7r yV5N…`） | `backend/bootstrap_shop_v5.py`、`bootstrap_shop_v6.py` | ❌ 仅本地 | 同 `Nh7c PVfF…`，同一账号的另一把钥匙 |
| 🔴 **WordPress 应用密码（第 3 把）**（`X6zR PvSR…`） | `optimize_product*.py`、`product_optimizer*.py`、`publish_product.py`（7 个文件） | ❌ 仅本地 | 同上 |
| 🔴 **服务器 SSH 密码**（`REDACTED_SSH_PASSWORD`） | `fix_final.py`、`fix_db.py`、`fix_db_2.py`、`fix_migration.py`、`fix_password.py`、`investigate.py` | ❌ 仅本地 | **服务器远程登录权限** |
| **SenseNova API Key**（`sk-Az1wKSUq…`） | `check_sensenova_api.py`、`check_sensenova_api2.py` | ❌ 仅本地 | 盗用 LLM 额度 |

> 🔴 **关于 JWT SECRET_KEY**：`security.py` 里的注释写着「从环境变量读取，有默认值」，
> 但代码**根本没有读环境变量**——它就写死了一行 `SECRET_KEY = "..."`。
> 这个值同时用于签发和校验 access token 与 refresh token，
> 且在公开仓库里。任何 clone 过仓库的人都能伪造管理员令牌。
> 本次已改为从 `JWT_SECRET_KEY` 环境变量读取，**任何环境**未配置都直接报错拒绝启动
> （不再保留仓库内默认值，避免同一个字符串继续出现在公开代码里）。

### 2.3 低风险（开发默认值，非本次事故重点）

- `REDACTED_DEFAULT_DB` —— `backend/app/core/config.py`、`docker-compose.yml`、
  `.env.example` 中的**开发默认值**。如果生产环境真的在用这个密码，请立刻改掉。
- `postgres:postgres` —— `backend/verify_persistence.py`（staging 默认值）。
- 测试用口令 `REDACTED_TEST_PASSWORD`、`REDACTED_TEST_PASSWORD_2` —— 仅存在于测试文件。

---

## 3. ⚡ 必须由你执行的吊销操作

**删除文件不能让密钥失效。已公开的东西必须假设已被拿走。**

### 3.1 WooCommerce 密钥（5 分钟）

1. 登录 WP 后台 → **设置 → 高级 → REST API**
2. 删除以 `ck_e87177ab`、`ck_3644da6e`、`ck_483264900`、`ck_52a9319d` 开头的**全部**密钥
3. 新建一套密钥，权限设为 **Read**（够用就别给 Write）
4. 把新密钥写入仓库根目录 `.env`（`WOOCOMMERCE_CONSUMER_KEY` / `WOOCOMMERCE_CONSUMER_SECRET`）
5. **审计**：查 WooCommerce 日志/订单表，看 2026-10-11 前后有无异常订单、批量改价、
   未授权商品变更

### 3.2 WordPress 应用密码（2 分钟）

1. WP 后台 → **用户 → 个人资料 → 应用密码**
2. 删除给 `fys2388@gmail.com` 生成的**全部**应用密码 —— 注意有 **3 把**：
   `Nh7c PVfF…`、`7g7r yV5N…`、`X6zR PvSR…`，一把都不能留
3. 重新生成**一把**，写入 `.env` 的 `WP_USERNAME` / `WP_APP_PASSWORD`
4. 不要给脚本多发钥匙。一个账号一把密钥，需要细分权限就建不同用户。

### 3.3 PostgreSQL 密码（3 分钟）

```sql
-- 在数据库管理端执行
ALTER USER nuotao WITH PASSWORD '新的强随机密码';
```

然后更新所有环境的 `.env` / Docker secrets。同时确认生产环境**没有**在用
`REDACTED_DEFAULT_DB` 这个开发默认值。

### 3.4 Brevo SMTP Key（2 分钟）

1. Brevo 后台 → **SMTP / Webhooks → SMTP 密钥**
2. 撤销以 `xsmtpsib-37c4ce6e` 开头的那把，重新生成，写入 `.env` 的 `BREVO_SMTP_KEY`

### 3.5 Webhook Secret（1 分钟）

改 `.env` 里的 `WOOCOMMERCE_WEBHOOK_SECRET` 为新的随机串（≥32 字节），
并同步到 WooCommerce 后台的 webhook 配置。

### 3.6 Agnes AI 生图 API Key（2 分钟）

1. Agnes AI 控制台 → **API Keys** → 撤销以 `sk-6ZoRZLvo` 开头的那把，重新生成
2. 写入 `.env` 的 `AGNES_API_KEY`
3. **查账单**：看这个 key 的用量，确认没有被异常刷量（生图是按张计费的）

### 3.7 🔴 JWT SECRET_KEY（3 分钟，最优先）

这是**全后台认证**的根密钥，优先级高于上面所有项：

```bash
# 1. 生成新密钥
python -c "import secrets; print(secrets.token_urlsafe(64))"

# 2. 写入所有环境的 .env
JWT_SECRET_KEY=<上面生成的值>

# 3. 重启服务
```

**后果说明**：旧的 access token 在重启后自动失效（签名对不上），
所有登录态会被清掉，用户需要重新登录。这是预期行为。

**审计建议**：查登录日志，看 2026-10-11 前后有无异常的管理员登录
（尤其是你不在的时间段、不在你常用的 IP 段）。

### 3.8 🔴 服务器 SSH 密码（3 分钟）

密码 `REDACTED_SSH_PASSWORD` 出现在 6 个运维脚本里，意味着**服务器远程登录口令曾以明文形式
散落在仓库中**。

1. 登录服务器 → `passwd` 改密码
2. **强烈建议改用 SSH key**，改完后在 `/etc/ssh/sshd_config` 里设
   `PasswordAuthentication no`
3. 查 `~/.bash_history`、`last`、`lastlog`，确认没有陌生登录
4. 同时检查：这个密码是不是也用在数据库或 MySQL 客户端上（脚本名暗示了这一点）

### 3.9 SenseNova API Key（2 分钟）

SenseNova 控制台 → **API Keys** → 撤销以 `sk-Az1wKSUq` 开头的那把，重新生成，
写入 `.env` 的 `SENSENOVA_API_KEY`。**查账单**确认没有被刷量。

### 3.10 🔴 Alertmanager SMTP 密码（2 分钟）

`security@nuotaooutdoor.com` 的口令 `Nuotao_SMTP_2024` 明文写在
`infra/alertmanager.yml` 里。**注意：`infra/` 目录不在 `.gitignore` 中**，
这个文件很可能已经被提交到公开仓库。

1. 立刻改 `security@nuotaooutdoor.com` 的口令
2. 把新口令放进**部署环境的密钥管理**（不要写回 yml）
3. 渲染时注入，例如：
   ```bash
   sed "s|__SMTP_PASSWORD__|$(vault read -field=password secret/alertmanager)|" \
       infra/alertmanager.yml > /etc/alertmanager/alertmanager.yml
   ```
4. 检查 GitHub Actions 里有没有把 `alertmanager.yml` 缓存过

### 3.11 🔴 第二个 JWT 签名密钥（2 分钟）

8 个 `test_*.sh` 脚本里硬编码了一把 64 字符的 JWT 签名密钥
（`o4Deqs9kpV…`），用于本地给 API 造 admin token。

1. **先确认这把和 3.7 里那把是不是同一个** —— 如果不同，说明你的项目里
   至少有两套 JWT 密钥在流通，这本身就是架构问题
2. 无论哪种情况，都按 3.7 的步骤重新生成并吊销
3. 已改为从 `JWT_SECRET_KEY` 环境变量读取

> 💡 **顺带一问**：`infra/alertmanager.yml` 在 `.gitignore` 之外。请检查
> `infra/` 下还有没有其他带真实值的配置文件。

### 3.12 关于 JWT 密钥的一个重要发现

排查中发现 `backend/.env` 里其实**已经配置了** `JWT_SECRET_KEY`，值是
`REDACTED_JWT_SECRET`——**和代码里硬编码的
那一串一模一样**。`backend/.env.development` 和 `backend/.env.staging` 同样是
这个值；`backend/.env.production` 里是 `CHANGE_ME_VERY_STRONG_RANDOM_KEY_...`
**占位符**（61 字符，看起来像真密钥但其实不是）。

**这意味着：所有环境都没有配置过真正的 JWT 密钥。**

1. 🔴 **生产环境的 `JWT_SECRET_KEY` 是占位符** `CHANGE_ME_...`，不是真密钥。
   如果生产服务正在运行，它要么在用代码里那个已公开的硬编码值，要么 fail-fast
   后启动了。请立刻生成真密钥并部署。
2. 🔴 **dev / staging 用的是那把公开的可预测密钥**。`"change-in-production"`
   写在变量名里不是缓解措施。
3. ✅ **本次已为 dev / staging / local 生成了新的随机密钥**
   （`secrets.token_urlsafe(64)`），写入对应 `.env`。生产环境请同样生成一把。

> 补充：因为 `.env` 里已经有 `JWT_SECRET_KEY`，本次新增的 fail-fast 守卫
> 在本仓库**不会**触发——脚本会静默读到 `.env` 里的值。这是"开箱即用"的预期行为。

---

## 4. 本次仓库修复内容

### 4.1 新增：共享密钥加载器

`scripts/wc_env.py` —— 所有维护脚本统一的凭据入口。脚本里**不再允许**出现
任何密钥字面量，缺失时会抛 `MissingSecret` 并给出可操作提示。

```python
from wc_env import wc_auth, wc_base_url, wp_auth

resp = requests.get(f"{wc_base_url()}/wp-json/wc/v3/products",
                    auth=wc_auth(), timeout=30)
```

`backend/image_processor_api.py`（真正的服务）改用 `backend/app/core/config.py`
的 `Settings`，与业务代码同源。

### 4.2 根因修复

| 根因 | 修复 |
|---|---|
| `.env.example` 缺少 WooCommerce / WP / SMTP 字段，开发者无处可放只能硬编码 | 已补全 `WOOCOMMERCE_*`、`WP_*`、`BREVO_SMTP_KEY` 及创建入口说明 |
| 无 pre-commit 密钥扫描 | 新增 `.pre-commit-config.yaml`（gitleaks + detect-secrets + 自定义 env 拦截） |
| 无 CI 密钥门禁 | 新增 `.github/workflows/secret-scanning.yml`（PR 增量 + main 全历史） |
| `.venv_nuotao/` 未被忽略，1395 个文件随时可能被 `git add -A` 带上 | 已加入 `.gitignore` |
| `_local_dev.env` 未被忽略且含真实 staging 密钥 | 已加入 `.gitignore` 并清空为占位符 |
| `backend/app/core/security.py` 的 `SECRET_KEY` 写死在代码里，注释谎称「从环境变量读取」 | 已改为读 `JWT_SECRET_KEY`，生产环境未配置时 fail closed |

### 4.3 新增文件

- `scripts/wc_env.py` —— 共享密钥加载器（所有维护脚本统一从这里读凭证）
- `scripts/security/check_no_env_in_commit.py` —— 拦截 `.env` 文件入库
- `scripts/security/run_detect_secrets.py` —— detect-secrets 包装器（无 baseline 时降级）
- `.pre-commit-config.yaml`
- `.github/workflows/secret-scanning.yml`
- `docs/security/secret-incident-2026-10-11.md`（本文档）

### 4.4 修改的核心文件

| 文件 | 变更 |
|---|---|
| `backend/app/core/security.py` | 移除硬编码 `SECRET_KEY`，改为 `JWT_SECRET_KEY` 环境变量 + fail closed |
| `backend/app/core/config.py` | 新增 `jwt_secret_key: str = ""` 字段 |
| `backend/image_processor_api.py` | WC 密钥改为经 `get_settings()` 读取 + 缺失时报错 |
| `backend/cleanup_failed_suggestions.py`、`backend/deploy_and_cleanup.py` | PostgreSQL 密码改为 `DATABASE_URL` 环境变量 |
| `scripts/wc_env.py` + 100+ 个脚本 | 全部硬编码密钥改为环境变量读取 |
| `.env.example` | 补上 `JWT_SECRET_KEY`、`WOOCOMMERCE_*`、`WP_*`、`AGNES_API_KEY`、`BREVO_SMTP_KEY` |
| `.gitignore` | 补上 `.venv_nuotao/`、`_*.env`、`secrets.txt` |

---

## 5. Git 历史重写（必须做，否则会持续泄露）

**当前状态**：以下凭据确定存在于 **Git 历史**中（来自被追踪的文件）。
即使从当前提交删掉，任何人 `git clone` 或翻历史都能拿到。

| 凭据 | 所在被追踪文件 |
|---|---|
| `ck_e87177ab…` / `cs_5388a693…` | `docs/product_listing_sop_v1.0.md` |
| `ck_483264900…` / `cs_0e6ba22a…` | `backend/image_processor_api.py` |
| `sk-6ZoRZLvo…`（Agnes AI） | `docs/product_listing_sop_v1.0.md` |
| `s2o7bdFwAX…`（PostgreSQL） | `backend/cleanup_failed_suggestions.py`、`backend/deploy_and_cleanup.py` |
| `Nuotao-ai-os-dev-secret-key…`（JWT） | `backend/app/core/security.py` |
| WordPress 应用密码 | `deployment/DEPLOY_WORDPRESS_PLUGIN.md`、`deployment/deploy-wordpress-plugin.sh`、`docs/product_listing_sop_v1.0.md`、`docs/fix_system_issues_20261011.md`、`docs/production_validation_report_20261011.md` |

> 另有若干密钥存在于**未被追踪**的本地脚本中（例如第二套与第四套 WooCommerce 密钥）。
> 它们不在 Git 历史里，但同样必须吊销——因为它们已经被复制到了被追踪的文件里，
> 同一批密钥极可能已经被拿去用过。
`git log -S` 一次就能找到。

> ⚠️ **重写历史会改变所有 commit hash**。这会：
> 1. 让所有已 fork/clone 的副本失效（需要重新 clone）
> 2. 让 GitHub Actions 上基于旧 SHA 的构建记录失效
> 3. **必须强推** `git push --force`
>
> 建议在低峰期做一次，通知协作者。

### 5.1 用 BFG（仓库里已有：`scripts/security/bfg-1.15.0.jar`）

```powershell
# 0. 备份（强烈建议）
git clone --mirror https://github.com/fys2388/nuotao-outdoor.git nuotao-backup.git

# 1. 从 Git 历史里提取真实密钥，生成待清除列表
#    （不要手抄，也不要把完整密钥写进任何会被提交的文件——包括本文档）
git grep -h -o -E "ck_[a-f0-9]{40}|cs_[a-f0-9]{40}|sk-[A-Za-z0-9]{30,}|xsmtpsib-[a-f0-9-]{40,}" \
    $(git rev-list --all) | sort -u > secrets.txt

# 正则抓不到的手工补入（WordPress 应用密码、DB 密码、webhook secret 等）
# 注意：只在你自己的本地 shell 里执行，不要把完整值贴进任何会被提交的文件
#   Add-Content secrets.txt "Nh7c PVfF ..."
#   Add-Content secrets.txt "<你的 PostgreSQL 密码>"

# 确认列表非空
Get-Content secrets.txt

# 2. 执行清理
java -jar scripts/security/bfg-1.15.0.jar `
    --replace-text secrets.txt `
    nuotao-backup.git

# 3. 清理悬空对象并强制推送
cd nuotao-backup.git
git reflog expire --expire=now --all
git gc --prune=now --aggressive
git push --force origin 'refs/heads/*:refs/heads/*'
git push --force --tags origin

# 4. 验证：全历史 grep 应无结果
git grep -n -I "ck_e87177ab\|ck_483264900\|ck_3644da6e\|ck_52a9319d\|s2o7bdFwAX\|Nh7c PVfF\|xsmtpsib-\|sk-6ZoRZLvo\|nuotao-ai-os-dev-secret-key" $(git rev-list --all)
```

### 5.2 重写后必须做

1. **所有协作者重新 clone**（旧副本已失效）
2. 在 GitHub 仓库 **Settings → General → 取消 Enable GitHub Actions cache** 等
   可能缓存旧状态的开关（如适用）
3. **确认第 3 节的密钥吊销已经完成** —— 历史重写只是擦掉证据，不解决泄露

---

## 6. 未来事件处理 Runbook

1. **先吊销，后清理**。密钥吊销是唯一能真正止血的动作。
2. 定位范围：`git grep -n -E "ck_[a-f0-9]{32,}|cs_[a-f0-9]{32,}" $(git rev-list --all)`
   （注意 `git grep HEAD` 只看当前树，**必须扫全历史**）
3. 判断哪些在公开仓库（`git ls-files` 与 `git log --oneline -- <file>`）。
4. 通知负责人；涉及 PII/支付数据时按 GDPR 24h/72h 通报要求走流程。
5. 走第 5 节的历史重写。
6. 复盘：补 `.env.example` 字段、补扫描规则、必要时加人审流程。

### 自查清单（PR 前 30 秒）

```bash
# 1. 扫已知密钥格式 + 通用高熵赋值（--no-ignore 很关键，否则被 .gitignore 排除的脚本会漏扫）
rg -n --no-ignore -e "ck_[a-f0-9]{32,}|cs_[a-f0-9]{32,}|sk-[A-Za-z0-9]{20,}|xsmtpsib-|BEGIN [A-Z ]*PRIVATE KEY|[A-Z][A-Z_]{3,}[:=][[:space:]]*['\"][A-Za-z0-9_\-]{16,}['\"]" . \
   --glob '!*.venv*' --glob '!node_modules*' --glob '!.git/*' --glob '!.env.example'

# 2. 检查本次改动有没有引入新文件
git diff --cached --name-only
```

- [ ] 上面的 grep **零命中**（除 `.env.example` 占位符和本文档的前缀说明）
- [ ] 新增的脚本是否从 `.env` 读凭据？（`from wc_env import wc_auth`）
- [ ] 新增环境变量是否已写入 `.env.example`？
- [ ] 文档示例里是否用了占位符而非真实值？
- [ ] **不要**在文档、注释、报错信息、日志里打印完整密钥

---

## 7. 时间线

| 时间 | 事件 |
|---|---|
| 2026-10-11 07:14:34 UTC | GitGuardian 告警：WooCommerce API 密钥暴露 |
| 2026-10-11 | 定位：13 类、18 个凭据、175+ 个文件、12 个文件在 GitHub |
| 2026-10-11 | 清理：全部密钥字面量替换为环境变量读取 |
| 2026-10-11 | 根因修复：`security.py` 硬编码 JWT 密钥改为 `JWT_SECRET_KEY` 环境变量 + fail closed |
| 2026-10-11 | 防护：pre-commit 钩子 + CI 门禁 + `.env.example` 补全 + `.gitignore` 修补 |
| 待办 | **吊销全部 15 个凭据**（需人工执行，见第 3 节） |
| 待办 | **Git 历史重写**（见第 5 节） |
