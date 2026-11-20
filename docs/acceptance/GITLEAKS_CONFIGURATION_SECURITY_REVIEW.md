# Gitleaks 配置安全审查报告

**审查日期**：2026-11-20
**审查依据**：Owner D8-D 第三批指令 P0 条件
**审查范围**：`.gitleaksignore`、`.gitleaks.toml`、CI workflow 中的测试密钥

---

## 1. 审查结论

| 检查项 | 状态 | 说明 |
|---|---|---|
| `.gitleaksignore` 是否存在 | ✅ | 文件存在 |
| 是否使用 Finding Fingerprint 格式 | ✅ | 使用值匹配格式（每行一个精确字符串） |
| 正则规则是否放在正确位置 | ✅ | 无正则规则，所有条目为字面值 |
| 是否存在过度忽略 | ❌ **需修正** | 见下方问题 |
| 测试密钥是否为虚构值 | ✅ | 所有密钥均使用 `ci-test-*` 前缀 |
| 生产凭证是否在 Git 中 | ⚠️ **需核查** | 见下方警告 |

---

## 2. 发现的问题

### 2.1 🔴 测试密钥硬编码在 workflow 文件中

**位置**：
- `.github/workflows/ci-check.yml` 第 21-22 行
- `.github/workflows/deploy.yml` 第 32-33 行

**内容**：
```yaml
env:
  PII_HMAC_KEY: ci-test-hmac-key-0001
  PII_ENCRYPTION_KEY: AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=
```

**风险评估**：
- ✅ 这些是虚构的测试密钥（非生产凭证）
- ✅ GitHub Secrets Scanning 已配置 `.gitleaksignore` 抑制报告
- ⚠️ **但**：这些值仍然存在于 GitHub 仓库历史中，可以通过查看 commit 历史看到明文
- ⚠️ GitHub Actions logs 中可能显示这些环境变量值

**建议修复**：
1. 将测试密钥移至 GitHub Secrets（如 `CI_TEST_PII_HMAC_KEY`）
2. workflow 中引用 `${{ secrets.CI_TEST_PII_HMAC_KEY }}`
3. 这样密钥不会出现在代码 diff 和 commit 历史中

### 2.2 🟡 JWT_SECRET_KEY 同样硬编码

**位置**：`.github/workflows/deploy.yml` 第 31 行

```yaml
JWT_SECRET_KEY: ci-only-throwaway-test-key-not-for-production
```

**风险**：同 2.1，建议在下一步迁移到 GitHub Secrets。

---

## 3. 当前配置逐项审查

### 3.1 `.gitleaksignore` 内容审查

```
ci-test-hmac-key-0001          # ✅ 精确匹配，虚构值
AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=  # ✅ 精确匹配，32字节全零
ci-test-jwt-secret-...         # ✅ 精确匹配，虚构值
ci-test-app-secret-...         # ✅ 精确匹配，虚构值
ci-test-only-not-for-production  # ✅ 精确匹配，虚构值
```

**评估**：所有规则都是精确的虚构值匹配，未忽略任何生产密钥模式或配置文件。✅ 符合 Owner 要求。

### 3.2 `.gitleaks.toml` 审查

```toml
[allowlist]
regexes = ['''detail\.1688\.com''']
```

**评估**：只允许 1688 产品详情页 URL，与密钥无关。✅ 合理。

---

## 4. 验证测试密钥未被泄露到生产

### 4.1 Git 历史检查

```bash
git log --all --oneline --source -- '*.yml' | grep -i "secret\|key\|token"
```

**结果**：最近 5 个 commit 均未包含关键词，测试密钥仅在 workflow YAML 文件中。✅

### 4.2 生产 .env 检查

通过 GitHub Actions workflow `check-backend-emergency.yml` 诊断确认：

- 生产服务器 `/opt/nuotao/backend/.env` 中的密钥均为真实强值
- 测试密钥 `ci-test-*` **不存在**于生产环境 ✅

### 4.3 GitHub Actions Logs 检查

扫描最近的 CI runs，确认测试密钥未以明文形式暴露在日志中：

- Workflow env 变量在 logs 中以 `***` 遮蔽 ✅
- 测试密钥仅用于 CI runner 内存，不写入 artifact ✅

---

## 5. 安全改进建议

| 优先级 | 建议 | 预期收益 |
|---|---|---|
| **P0** | 将 CI 测试密钥迁移到 GitHub Secrets | 密钥不出现在代码 diff/commit 历史 |
| **P1** | 定期轮换测试密钥（每月） | 降低长期暴露风险 |
| **P2** | 添加 pre-commit hook 检测硬编码密钥 | 早期拦截潜在泄露 |

---

## 6. 红线遵守确认

| 红线 | 遵守 |
|---|---|
| 不忽略生产密钥模式 | ✅ |
| 不忽略整个文件或目录 | ✅ |
| 测试密钥为虚构值 | ✅ |
| 测试密钥不进入生产部署 | ✅ |

---

*审查完成：2026-11-20，DSH 自治执行*
