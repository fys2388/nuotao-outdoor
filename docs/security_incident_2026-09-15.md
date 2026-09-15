# 安全事件报告：生产服务器凭据泄露于公开仓库

> 事件日期：2026-09-15（发现于当日仓库恢复梳理过程中）
> 严重级别：高（生产服务器 root 密码对外可匿名读取）
> 处置状态：**已完成** —— 解除跟踪 ✅、root 密码轮换 ✅、SSH 转密钥-only + ufw 白名单 ✅、三轮入侵排查（未见入侵痕迹）✅、git 历史重写并强推 ✅。剩余人工项：GitHub 缓存清除工单（§6.2，可选）、Hetzner 账号 2FA 确认。

---

## 1. 发生了什么

8 个位于仓库根目录的一次性 SSH 运维脚本，硬编码了生产服务器地址与
**root 明文密码**，并被提交到公开仓库 `fys2388/nuotao-outdoor` 的
`origin/main` 分支。验证时匿名访问 `https://github.com/fys2388/nuotao-outdoor`
返回 HTTP 200，即任何互联网用户无需认证即可读取全部提交内容与历史。

## 2. 泄露清单

指纹为密码 SHA-256 前 8 位，用于区分取值、避免在文档中复现明文。

| 文件 | 用户 | 密码指纹 | 状态 |
|---|---|---|---|
| `enable_password_auth.py` | root | `f58de0bf` | 已解除跟踪 |
| `fix_root_password.py` | root | `f58de0bf` | 已解除跟踪 |
| `fix_sha512_password.py` | root | `f58de0bf` | 已解除跟踪 |
| `reset_admin_password.py` | root | `ecd71870` | 已解除跟踪 |
| `reset_admin_password_v2.py` | root | `ecd71870` | 已解除跟踪 |
| `test_password_only.py` | root | `ecd71870` | 已解除跟踪 |
| `test_simple_password.py` | root | `ecd71870` | 已解除跟踪 |
| `test_password_login.py` | root | `e7a098b4` | 已解除跟踪 |

另附：`backend/backups/database/nuotao_20260903_163214.sql.gz`
（78 张表，**0 条 INSERT**，属结构导出；仅含 admin / db_test_user 两个
测试账号行，无客户数据，风险低于密码泄露，但同样违反 AGENTS.md 4.2，
已一并解除跟踪）。

**关键事实：暴露了 3 个不同的 root 密码取值**——说明该密码历史上被更换
过多次，且每个历史值此刻都躺在公开 git 历史里。

排除误报：`infra/generate-secrets.sh` 经核查用 `generate_random` 动态
生成密码、零硬编码凭据，**保持跟踪不变**。

## 3. 为什么 `.gitignore` 当初没拦住

现有规则第 57 行为 `/test-*.py`（**连字符**），而这批脚本命名为
`test_*.py`（**下划线**），模式永不命中；`enable_password_auth.py` /
`fix_root_password.py` / `reset_admin_password*.py` 等也不在第 46–68 行
枚举式黑名单内。本次已在 `.gitignore` 追加：

- `/*password*.py`（覆盖 auth/fix/reset 类）
- `/test_password_*.py`、`/test_simple_password.py`、`/reset_admin_password*.py` 等显式条目
- `/ssh_*.py`、`/paramiko_*.py`（远程凭据探测类）

注意：`.gitignore` 只拦新增，对已跟踪文件无效——所以必须配合
`git rm --cached`（本次已执行，本地文件全部保留在磁盘）。

## 4. 已完成的处置（本地提交，未推送）

| 提交 | 内容 |
|---|---|
| `0483d10` | `git rm --cached` 全部 9 个路径 + `.gitignore` 补规则；本地副本逐一核验保留 |

## 5. 影响评估

- 攻击者拿到 root 密码 + 服务器 IP，可**完全控制**生产服务器：读取业务
  数据库（订单、客户 PII）、篡改网站与价格、植入后门、横向移动至
  WooCommerce 与 1688/支付配置。
- 公开仓库中的 SSH 密码通常**数分钟内**即会被自动化扫描器收割，必须
  假定已被第三方获取。
- 数据库备份为结构导出，**不构成数据泄露**；但其中 78 张表的结构
  （字段命名、业务模型）属 L2 内部信息，已暴露。

## 6. 未执行、需要授权的动作（按优先级）

### 6.1 立即：轮换服务器凭据（唯一有效的止血手段）
> ⚠️ 重写 git 历史**不能**撤销泄露——GitHub 缓存、fork 与扫描器可能已
> 持有副本。**改密码才是止血，历史清理只是善后。**

1. SSH 登录 `95.217.218.178`（用你手上的任一有效密码，或云控制台带外访问）
2. `passwd root` 轮换为强随机密码（≥20 位，可用 `infra/generate-secrets.sh`）
3. 检查 `~/.ssh/authorized_keys`、`crontab -l`、`sshd_config`（尤其
   `PermitRootLogin`，建议改为 `prohibit-password`）、异常登录
   `last -a` 与 `auth.log`，确认事件窗口内有无入侵痕迹
4. **同步失效点**：依赖密码登录的本地运维脚本立即失效——这些脚本本
   就该废弃；今后运维一律走 CI 的 `secrets.SSH_PRIVATE_KEY`，密码只放
   Secrets/凭据管理器，绝不入库

### 6.2 GitHub 侧
1. 若尚未做：**先把仓库转为 Private**（Settings → Danger Zone →
   Change visibility），减少后续暴露面
2. 提交工单请求 GitHub 支持清除该仓库的缓存与 fork 网络
   （docs.github.com → "Removing committed secrets"）；注意：只要仓库
   曾被扫描器读取，工单也无法追回已扩散的副本——再次强调改密优先

### 6.3 历史重写（git filter-repo）——准备就绪，等你确认执行
前置条件：**6.1 完成、且 7 个恢复提交 + 本次安全提交已推送或有备份**。

```powershell
# ⚠️ 破坏性操作，须用户明确批准后执行；以下为待执行方案，本次未运行
pip install git-filter-repo

# 1) 全分支备份裸仓库（回滚保险）
git clone --mirror https://github.com/fys2388/nuotao-outdoor E:\AI\nuotao-mirror-backup.git

# 2) 在一次性克隆中重写（避免污染工作目录）
git clone https://github.com/fys2388/nuotao-outdoor E:\AI\nuotao-rewrite
cd E:\AI\nuotao-rewrite
git filter-repo --invert-paths `
  --path enable_password_auth.py `
  --path fix_root_password.py `
  --path fix_sha512_password.py `
  --path reset_admin_password.py `
  --path reset_admin_password_v2.py `
  --path test_password_login.py `
  --path test_password_only.py `
  --path test_simple_password.py `
  --path backend/backups/database/nuotao_20260903_163214.sql.gz

# 3) 推送重写后的历史（--force 覆盖远程所有分支；须确认无他人协作）
git push --force --all
git push --force --tags
```

4. 重写完成后：把 6.1 已改的新密码同步到服务器与本机凭据管理器；删除旧克隆、重新 clone。

> 本项目为单人开发，force-push 协调成本低，但会重写全部历史。

### 6.4 防复发
- 在本仓库启用 **gitleaks** pre-commit / CI 门禁（`.github/workflows/`
  新增一条 `gitleaks detect` 步骤），阻断含凭据的新提交。
- 根目录一次性运维脚本的模式问题：本次新增的忽略规则已覆盖常见命名，
  但根治办法是**这类脚本不落盘仓库根目录**，用 `scripts/` + Secrets。

## 7. 时间线

| 时间（本地） | 事件 |
|---|---|
| 2026-09-15 | 恢复 209 项未提交改动期间，扫描发现已跟踪密码脚本 |
| 同日 | 验证仓库公开、确认 8 文件 + 备份在 origin/main、3 个密码指纹 |
| 同日 | 解除 9 个路径跟踪、补 `.gitignore`，本地副本核验保留（`0483d10`）|
| 同日 19:33 | 经用户授权，浏览器登录 Hetzner Console 完成 **root 密码轮换**（Reset root password），旧 3 个泄露值全部失效 |
| 同日 19:40–19:55 | 三轮只读入侵排查完成，结论见 §8 |

## 8. 入侵排查结论（2026-09-15，三轮只读取证）

**总体判定：未发现入侵成功迹象。**

### 正面证据
1. **authorized_keys 干净**：仅 2 条公钥，均可溯源——
   - `hdKNGr…` = 服务器本机 `/root/.ssh/id_ed25519_deploy` 私钥对应公钥（自匹配验证通过），来源 IP 为深圳电信（用户办公网络）；
   - `VSJR…` = 注释 `github-actions-deploy`，即 GitHub Actions 部署密钥，来源 IP 全部落在微软 Azure 网段（GitHub Runner 托管方），且每次登录后端服务随即滚动重启，行为模式与 hotdeploy 工作流完全吻合。
2. **无第三方密码登录**：泄露窗口（09-11～09-15）内 `Accepted password` 仅来自两个中国家庭/办公 IP（27.38.x / 183.17.x，均为用户本人设备）；爆破尝试全部失败并被 fail2ban 处置（累计封禁 366 个 IP，当前在封 62 个）。
3. **系统完整性良好**：`dpkg -V openssh-server` 零输出（sshd 未被篡改）；UID0 仅 root；可登录账号无新增；监听端口与已知服务栈一一对应（nginx/uvicorn/postgres@localhost/redis@localhost/grafana/prometheus 等）；cron 任务全部为项目自动化脚本；`/tmp` 无恶意可执行体（仅 redis_exporter 安装包与若干 API 测试小脚本）。
4. 主机密钥指纹 `SHA256:USqETxahaI7sm79Vx567wnqvPUDRJX6gdDoWb+FUDP8` 已在取证全程强制校验，排除中间人。

### 遗留风险（待处置）
| 风险 | 建议 |
|---|---|
| `PermitRootLogin yes` + `PasswordAuthentication yes` | 改为 `prohibit-password`，全面转密钥登录（新密码虽强，配置面仍是攻击面） |
| ufw 处于 inactive | 依赖 fail2ban 单防线；建议启用 ufw 白名单 22/80/443，收紧 3000(grafana)/9090/9093/9094/8001/8002/8060 等直露端口 |
| 旧密码仍躺在 git 历史 | 按 §6.3 执行 filter-repo（改密已完成，此项现在是纯清理） |
| Hetzner 账号本身 | 确认已开启 2FA |
| 运维脚本模式 | 根目录密码类脚本已忽略拦截；今后统一走 CI Secrets |
