# Owner 待办事项（D8-E Round 5 · Owner 安全事项等待阶段）

> 本文件记录 Owner 侧需完成的安全事项。DSH 不得代为执行这些 Owner 专属操作。
> Owner 完成并通知后，DSH 恢复相应任务。

## Owner 待办（按优先级）

| # | 事项 | 操作 | 状态 |
|---|---|---|---|
| 1 | **启用 Hetzner 账号 2FA** | Hetzner Console → 账号安全设置 → 启用双因素认证 + 保存恢复码 | ⏳ 待 Owner |
| 2 | **安全保存新 API Token** | 新 Token `nuotao-agent-2026-rotated`（前缀 `FlAQ38lz…`）→ GitHub Actions Secret 或密码管理器；确认生产调用方已使用新 Token；**不得明文发给 DSH/写入 Git** | ⏳ 待 Owner |
| 3 | **复核 API Token 最小权限** | Read & Write 是否为实际业务所必需；若不需要写权限，降级为 Read | ⏳ 待 Owner |
| 4 | **1688 Cookie 官方登录 + 安全渠道写入** | 1688 官方登录 → 新 Cookie 通过安全渠道写入指定 Secret → 通知 DSH 执行迁移/验证（禁聊天明文） | ⏳ 待 Owner（机制已就绪，见下） |

### Item #4 进展（2026-11-20 更新）
- **旧 Cookie 已确诊失效**：`verify-1688-cookie.yml` 用非硬编码商品实测，Playwright 走 Cookie 注入抓回的是 `1688 Product` 占位名（登录墙外壳），非真实商品 → Cookie 过期。
- **轮换机制已建成并端到端验证**：`rotate-1688-cookie.yml`（GitHub Secret `ALI1688_LOGIN_COOKIE` → 原子写服务器 `.env` → 重启 `nuotao-backend` → 自动诊断）。Cookie 全程 `::add-mask::` 掩码，日志只回长度与"有效/失效"判定，绝不回显值。
- **Owner 现在只剩一步**：把新 Cookie 粘进 Secret `ALI1688_LOGIN_COOKIE` → 触发 `Rotate 1688 LOGIN_COOKIE` workflow → 看诊断是否 `LOGIN_COOKIE VALID`。
- **兜底假数据已加闸门**：`import_from_1688` 现在对 `data_source=hardcoded_fallback` 阻断自动流转/上架（`pipeline_skipped_reason` 标记），防止过期价格/SKU 静默上架 WooCommerce（PR #13，CI 已验证）。

## Owner 待确认事项
- 新 root 密码（`/root/.hetzner/rescue_root_password_new`）是否确有保留必要：
  - 若不需要：安全转存后**删除服务器明文副本**（避免服务器成为凭据集中暴露点）
  - 若需要：保留（chmod 600）并记录用途

## 完成标准（凭据轮换真正闭环）
新密钥安全存储 ✅ / 生产调用迁移 ✅ / 旧密钥失效 ✅ / 权限最小化 ✅ / 证据归档 ✅ —— 全部完成后才能宣布 D8-E Round 5 完成。
