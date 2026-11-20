# Owner D8-E Round 4 完整执行指令（2026-11-20）

**授权来源**：ChatGPT "制定D8-E优先级" 对话（Owner）
**阶段**：Production Security Remediation & CMP Staging
**执行模式**：DSH 自治执行，严格遵守生产变更边界

---

## 一、三项 Owner 决策（基于 Round 3 汇报）

### D1：CMP Staging 路径 → **批准 C 方案**（Hetzner Docker，需先核实隔离条件）
- 批准 Hetzner Docker 方案，但必须先核实服务器隔离条件
- **硬性要求**：独立数据库、独立网络、资源限制、无生产数据、无生产凭据
- **关键**：如果只能与生产后端共用同一台服务器，必须如实标记为共享宿主机隔离，不能宣称已实现基础设施级隔离
- **安装 Docker 或修改生产宿主机网络配置之前，先提交环境评估**
- 关闭邮件、支付、Webhook、自动订单及其他可能触发生产业务的功能

### D2：生产机密迁移与轮换 → **立即授权**（F2 最高优先级）+ **P0-1 再次轮换**
- 将 deploy.yml 硬编码的 DB 密码和 1688 LOGIN_COOKIE 迁移到 GitHub Secrets
- **P0-1 关键**：上一轮公开到聊天内容的 DB 凭据视为已泄露，**生成全新且唯一凭据**
- 验证：新密码连接 / 旧密码认证失败 / healthz / readyz / CI 无明文残留
- **后续任何报告只允许显示 REDACTED 或指纹，不允许显示真实密码**

### D3：WordPress 漏洞 → **批准分级授权**
- **WordPress Core 7.1.5 安全更新**：批准生产预检查及受控更新（2026-11-18 官方发布，修复 SQLi/XSS/权限提升/信息泄露）
- **三个插件在 Staging 升级验证**（不批准直接批量更新生产）
- **Owner 纠正**：Elementor 4.3.6 是 CVE-2026-104718 修复版本（不应单独认定受影响）；ElementsKit Lite 4.0.7（修复 4.2.0）和 Jeg Kit 3.2.20（修复 3.3.1）为优先升级验证

---

## 二、两个审计修正

### F2 必须按凭据泄露处理（关键）
- **将上一轮公开到聊天内容的新 DB 凭据视为已泄露**
- **生成全新且唯一的凭据，通过安全渠道完成更新**
- 验收逻辑：
  - 当前代码不再包含明文
  - Actions 通过受保护 Secrets 获取配置
  - 生产 DB 新凭据实际连接成功
  - 1688 旧会话 Cookie 已撤销或失效
  - 旧 DB 密码已失效
  - Git 历史、分支、标签、Actions 日志、构建产物均完成暴露检查
- **不要在报告、终端截图或 Actions 日志打印密码和 Cookie**

### F1 GDPR 修正
- 不能仅凭 Banner 二元断言 GDPR 不合规
- 需检查实际 Cookie、第三方脚本、数据处理目的及同意控制机制

---

## 三、Round 4 执行指令

### P0：F2 生产机密迁移与轮换（立即执行）
- **Step 1 完整暴露面审计**：deploy.yml DB 密码 / 1688 LOGIN_COOKIE / 当前 Git 代码 / Git 历史/分支/标签 / Actions 日志 / workflow artifacts / 生产服务器配置文件 / 其他自动化任务
- **Step 2 生成全新唯一凭据**：通过安全渠道完成更新（**已完成，P0-1 PASS**）
- **P0-3 历史泄露凭据（升级 P0）**：PGPASSWORD（DB 密码，已轮换失效）/ API_TOKEN（Hetzner）/ JWT（admin token）/ rescue_password（SSH）——**如仍有效必须轮换或吊销；JWT 必须先评估消费者、密钥版本和会话影响，安排兼容轮换**
- **P0-4 WordPress Core 7.1.5 安全更新**：批准生产预检查及受控更新（备份 + 兼容性检查 + 受控更新）
- **Step 3 验证**：生产 DB 连接 / 后端服务与连接池 / healthz / readyz / 旧密码认证失败 / CI 和服务器文件无明文残留 / 保留可恢复配置变更记录

### P1：CMP Staging 手动独立子站
- WordPress 独立容器 / MySQL 独立容器 / 独立数据库 / 独立 Docker Network / 资源限制 / 访问认证 / 搜索引擎禁止索引
- 不接入生产 DB / 不使用生产 Secret / 不发送真实邮件 / 不触发真实支付/订单/Webhook
- 优先独立 VM 或独立宿主机；如共用生产宿主机须明确记录共享内核和资源竞争风险
- 输出：`CMP_STAGING_INFRASTRUCTURE_REPORT.md` + `CMP_STAGING_PHASE1_EXECUTION_REPORT.md`

### P2：WordPress 21 项漏洞审计
### P3：CI、Secret、SSH 持续监控（CI 全部 Gate / Secret Scanning / Gitleaks / SSH S4 / Fail2ban / GA4）

---

## 四、生产授权边界

**允许**：DB 凭据再次轮换 / 1688 Cookie 轮换 / 历史有效凭据轮换 / WordPress Core 7.1.5 安全更新（按授权及维护前置条件）/ CMP 独立 Staging 建设

**不允许**：插件批量生产更新 / 生产 CMP 替换 / 生产 GA4 修改 / WooCommerce 业务逻辑变更 / 生产业务数据库结构调整 / B2B 数据注入 / 新 Agent 上线 / 未经额外授权的 Git 历史重写

---

## 五、最终验收

- 输出：`D8_E_ROUND4_EXECUTION_SUMMARY.md`
- 任务区分：PASS / VERIFIED / PARTIAL / BLOCKED / FAILED / NOT VERIFIED
- 每项提供：Git Commit / Actions Run ID / 执行时间 / 原始证据路径 / 验证结果 / 回滚方案 / 遗留风险 / Owner 待决事项
- **核心验收**：
  - 所有仍有效的历史暴露凭据必须完成轮换或吊销
  - 生产服务保持健康
  - WordPress Core 安全更新完成或有明确阻塞证据
  - 三个插件完成漏洞核对及 Staging 兼容验证
  - CMP Staging 具备真实测试条件
  - 无未经授权的生产变更
- **本轮以安全闭环为目的，不以 Commit 数量和 PASS 数量为目标**
- **立即从 P0-1 开始执行**

---

*Owner Round 4 指令存档：2026-11-20，DSH 从 ChatGPT 对话提取*
