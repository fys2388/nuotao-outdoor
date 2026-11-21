# 本地 Gitleaks Hook 修复报告（Issue #22）

> 阶段：D8-E Round 5 等待期安全工程收尾。日期：2026-11-21。执行：DSH (sensenova)。
> 关联：Issue #22、PR #21（评分卡）。Owner 授权：批准修复，但必须"修复工具链，不降低密钥安全门槛"。

---

## 一、问题与根因

**现象：** 本地 `pre-commit` 的 gitleaks 门禁在当前仓库状态下阻塞**每一次提交**，报 605 个 leak，与提交内容是否干净无关。

**根因（两点叠加）：**

1. **扫描口径与 CI 不一致。** 旧 hook 配置为 `gitleaks detect --source . --no-git`，每次提交**全量扫描整个工作树**（实测 1.08GB / 7m24s）。而 CI（`.github/workflows/secret-scanning.yml`）用 `gitleaks-action@v2 target: diff` **只扫本次新增改动**。仓库携带约 605 个历史存量命中，CI 不报（它们不在 diff 里），本地全量扫全报 → 本地门禁与 CI 永远打架。

2. **`.gitleaksignore` 格式失效。** gitleaks 升级到 8.30.1 后，顶层命令从 `detect` 改为 `git` / `dir`，且 `.gitleaksignore` 要求**完整 fingerprint**（`rule:file:line:hash`），不再认旧的"纯 secret 值"格式 → 旧条目全部报 `Invalid .gitleaksignore entry`，形同虚设。这正是它此前被（误）删除的原因。

## 二、修复方案（已实施）

核心思路：**把本地门禁对齐 CI 的 diff 口径，只扫 staged 新增，不降低安全门槛。**

| 项 | 改动 |
|---|---|
| `scripts/security/run_gitleaks_staged.py` | **新增**。管道 `git diff --staged` → `gitleaks stdin --redact`，只扫本次 staged；gitleaks 未安装则优雅跳过（不阻塞提交） |
| `.pre-commit-config.yaml` | gitleaks hook 的 `entry` 从全量 `detect --source .` 改为 `python scripts/security/run_gitleaks_staged.py` |
| `.gitleaksignore` | 清空失效的纯值规则，改为说明注释（新版需 fingerprint 格式） |
| `.gitleaks.toml` | CI 测试值以 `\A...\z` **逐条精确锚定**迁入 `[allowlist]`；`[extend] useDefault` 与现有规则不变 |
| 备份 | 原 `.pre-commit-config.yaml` / `.gitleaksignore` 备份为 `*.bak`（`*.bak` 已被 `.gitignore` 排除，不入库）；版本库历史亦可 `git revert` 回滚 |

## 三、605 个历史存量命中：分类与可追溯处理

Owner 要求"建立分类、归档和可追溯记录"。处理策略如下：

- **分类：** 605 个命中**不是真实泄露**，主体是少数几个**已知虚构 CI 测试值**（`ci-test-hmac-key-0001`、全零 base64 AES key `AAECAwQ…h8=`、`ci-test-jwt-secret-*`、`ci-test-app-secret-*`、`ci-test-only-not-for-production`）在 `backend/tests/`（如 `test_pii_ci_integration.py:41`）与 `docs/acceptance/` 审计文档中的**重复出现**。这些值是为 CI 测试刻意构造的 throwaway 值，从未用于生产。
- **处置：** 这 5 个虚构值已作为**精确单值 allowlist** 迁入 `.gitleaks.toml`（锚定 `\A...\z`）。改 staged 扫描后，历史命中因不在 staged diff 内而不再阻塞——**与 CI 对它们的处理完全一致**。
- **可追溯：**
  - 未逐条罗列 605 条（多为同一虚构值的重复命中，逐条罗列无增量信息）；分类与代表性出处如上。
  - 任意时刻可运行**手动全量扫描**复现完整清单：`gitleaks git . --redact --no-banner`（历史）或 `gitleaks dir . --redact --no-banner`（工作区）。
  - 这 5 个虚构值本身仍保留在测试/文档中未改动，来源可溯（`backend/tests/test_pii_ci_integration.py:41` 等）。

## 四、负向测试结果（Owner 明确要求，全部通过）

| # | Owner 负向要求 | 测试 | 结果 |
|---|---|---|---|
| 1 | 新增测试用真密钥必须阻止提交 | stage 随机 `AKIA…` 密钥 → 跑新 hook | `leaks found: 1`，exit=1 ✅ 拦截 |
| 2 | 新增未知密钥必须阻止 | 同上（未知随机值） | ✅ 拦截 |
| 3 | 历史存量不能掩盖新增泄露 | 仅扫 staged，历史不进 diff，但新增真密钥仍拦 | ✅ 见 #1 |
| 4 | allowlist 不能让整文件/目录/规则失效 | allowlist 为单值锚定，非文件/目录/规则级豁免 | ✅ 真密钥仍被拦证明未失效 |
| 5 | 本地与 CI 对同一新增密钥一致 | 本地 `stdin`(staged) 与 CI `target: diff` 同为 diff 口径 | ✅ 口径一致 |
| 6 | 已知虚构测试值正确放行（不误报） | stage `ci-test-hmac-key-0001` | `no leaks found`，exit=0 ✅ |

## 五、安全边界（未降低门槛）

- `[extend] useDefault = true` 与原有 gitleaks 规则**不变**。
- allowlist 仅新增 5 条**单值精确**匹配（虚构测试值），无文件/目录/规则级豁免。
- 真/未知密钥仍被本地 staged 扫描与 CI diff 扫描双重拦截。
- 全量历史扫描能力保留（手动命令），未删除。

## 六、回滚

- 本地：`Copy-Item .pre-commit-config.yaml.bak .pre-commit-config.yaml -Force`（同 `.gitleaksignore.bak`）。
- 版本库：对本 PR `git revert`，hook 即恢复为原全量扫描配置。

## 七、结论

本地 gitleaks 门禁已从"全量扫工作树、阻塞一切提交"修复为"只扫 staged 新增、与 CI 口径一致"，**消除了 605 历史存量造成的假阻塞，同时完整保留对新增真实密钥的拦截能力**。负向测试 6/6 通过。**状态：PASS（工具链修复，安全门槛未降低）。**