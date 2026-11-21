# Owner 待办事项（D8-E Round 5 · Owner 安全事项等待阶段）

> 本文件记录 Owner 侧需完成的安全事项。DSH 不得代为执行这些 Owner 专属操作。
> Owner 完成并通知后，DSH 恢复相应任务。

## Owner 待办（按优先级）

| # | 事项 | 操作 | 状态 |
|---|---|---|---|
| 1 | **启用 Hetzner 账号 2FA** | Hetzner Console → 账号安全设置 → 启用双因素认证 + 保存恢复码 | ⏸️ **Owner 决定暂缓**（2026-11-21，见下方决定记录） |
| 2 | **安全保存新 API Token** | 新 Token `nuotao-agent-2026-rotated`（前缀 `FlAQ38lz…`）→ GitHub Actions Secret 或密码管理器；确认生产调用方已使用新 Token；**不得明文发给 DSH/写入 Git** | ⏸️ **Owner 决定暂缓**（2026-11-21，见下方决定记录） |
| 3 | **复核 API Token 最小权限** | Read & Write 是否为实际业务所必需；若不需要写权限，降级为 Read | ⏳ 待 Owner |
| 4 | **1688 Cookie 官方登录 + 安全渠道写入** | 1688 官方登录 → 新 Cookie 通过安全渠道写入指定 Secret → 通知 DSH 执行迁移/验证（禁聊天明文） | ⏳ 待 Owner（机制已就绪，见下） |

### Item #4 进展（2026-11-20 更新）
- **旧 Cookie 已确诊失效**：`verify-1688-cookie.yml` 用非硬编码商品实测，Playwright 走 Cookie 注入抓回的是 `1688 Product` 占位名（登录墙外壳），非真实商品 → Cookie 过期。
- **轮换机制已建成并端到端验证**：`rotate-1688-cookie.yml`（GitHub Secret `ALI1688_LOGIN_COOKIE` → 原子写服务器 `.env` → 重启 `nuotao-backend` → 自动诊断）。Cookie 全程 `::add-mask::` 掩码，日志只回长度与"有效/失效"判定，绝不回显值。
- **Owner 现在只剩一步**：把新 Cookie 粘进 Secret `ALI1688_LOGIN_COOKIE` → 触发 `Rotate 1688 LOGIN_COOKIE` workflow → 看诊断是否 `LOGIN_COOKIE VALID`。
- **兜底假数据已加闸门**：`import_from_1688` 现在对 `data_source=hardcoded_fallback` 阻断自动流转/上架（`pipeline_skipped_reason` 标记），防止过期价格/SKU 静默上架 WooCommerce（PR #13，CI 已验证）。

## Owner 决定记录（2026-11-21 收尾）

Owner 对本阶段遗留的安全事项作出如下明确决定（知情选择，非遗漏）。DSH 据此更新状态，不再作为阻塞 D8-E 收尾的待办：

| 事项 | Owner 决定 | 理由 / 影响 |
|---|---|---|
| **Hetzner 账号 2FA** | **暂不启用** | Owner 已有邮件验证兜底，判断为可接受折中。**风险已知**：2FA（每次登录动态码）比邮件验证（偏一次性确认）更强；Hetzner 账号是服务器总开关，建议 Owner 确保邮箱密码强度并开启邮箱侧验证作为补偿。可日后随时启用。 |
| **新 API Token 存 GitHub Secret** | **暂缓** | 生产服务器已有有效 Token（`/root/.hetzner/api_token_new`），GitHub Secret 仅为冗余备份，**不存不影响任何业务**。且 Hetzner Token 创建后不可回看明文，"重新获取"= 重新生成 = 作废服务器在用 Token + 需连带改服务器配置，风险 > 收益。待 Owner 日后手边有 Token 完整值时可 30 秒补存（GitHub「新建 Secret」页面 Name 填 `HETZNER_API_TOKEN`）。 |
| **1688 Cookie 官方登录** | **晚点做** | Owner 时间安排，机制已就绪（见 Item #4），Owner 方便时粘 Cookie 到 `ALI1688_LOGIN_COOKIE` 并触发轮换 workflow 即可。 |

> **仍开放（未被取消）：** Item #3「复核 API Token 最小权限」与 Item #4「1688 Cookie 官方登录」仍为 Owner 待办，Owner 方便时处理。

## Owner 待确认事项
- 新 root 密码（`/root/.hetzner/rescue_root_password_new`）是否确有保留必要：
  - 若不需要：安全转存后**删除服务器明文副本**（避免服务器成为凭据集中暴露点）
  - 若需要：保留（chmod 600）并记录用途

## 完成标准（凭据轮换真正闭环）
新密钥安全存储 ✅ / 生产调用迁移 ✅ / 旧密钥失效 ✅ / 权限最小化 ✅ / 证据归档 ✅ —— 全部完成后才能宣布 D8-E Round 5 完成。
