# Owner D8-E Round 4 完整执行指令（2026-11-20）

**授权来源**：ChatGPT "制定D8-E优先级" 对话（Owner）
**阶段**：Production Security Remediation & CMP Staging
**执行模式**：DSH 自治执行，严格遵守生产变更边界

---

## 一、三项 Owner 决策（基于 Round 3 汇报）

### D1：CMP Staging 路径 → **批准 B 方案**（Hostinger 手动独立子站）
- 暂不升级 Hostinger 套餐，不急于在生产 Hetzner 服务器增加 Docker 负载
- 原因：CMP 是 WordPress 前端功能，优先在与生产相同的 Hostinger 环境测试，减少环境差异
- **必须**：独立网站目录、独立数据库、独立账号，不复制生产凭据；关闭邮件、支付、Webhook、自动订单及其他可能触发生产业务的功能

### D2：生产机密迁移与轮换 → **立即授权**（F2 最高优先级）
- 将 deploy.yml 硬编码的 DB 密码和 1688 LOGIN_COOKIE 迁移到 GitHub Secrets
- **必须完成真实凭据轮换、旧凭据失效、工作流验证及历史暴露检查**
- 按凭据可能已经泄露处理，不能只删除当前文件明文就宣布完成

### D3：WordPress 21 个插件漏洞 → **批准审计**
- 先查明 21 项到底是 21 个漏洞还是 21 个扫描发现
- 识别插件、版本、CVE、严重程度、是否正在使用、可利用攻击路径
- 优先已知被利用的漏洞及高危 RCE；先 Staging 验证，再提生产修复方案

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
- **Step 2 生成全新唯一凭据**：通过安全渠道完成更新
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
