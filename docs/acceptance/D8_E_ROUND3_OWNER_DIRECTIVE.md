# Owner D8-E 第三轮（Round 3）完整执行指令

**来源**：ChatGPT "制定D8-E优先级" 对话（2026-11-20）
**授权人**：Owner
**项目**：Nuotao AI OS
**阶段**：D8-E Round 3 — 安全整改、CMP 实测、漏洞治理

---

## 一、总体目标

基于第二轮结果（P0 审计完成、P1 BLOCKED、F2 机密发现），进入 Round 3：
1. 消除生产部署工作流中的**硬编码机密风险**（F2）。
2. 建立独立、安全、可复现的 **WordPress CMP Staging 环境**。
3. 完成生产 WordPress **21 项插件漏洞的风险分级**。
4. 保持 GA4 真实访客验证机制。
5. 保持现有 CI、SSH、生产核心工作流稳定。

---

## 二、执行顺序与任务

### 1. F2 生产机密整改（第一优先）
- 清除 `deploy.yml` hotfix-env 硬编码机密（DB_PW + 1688 LOGIN_COOKIE）
- 迁移到 GitHub Secrets
- **轮换真实凭据**（DB 密码 + 1688 Cookie）
- 旧凭据失效
- 输出：`F2_PRODUCTION_SECRET_REMEDIATION_REPORT.md`

### 2. CMP Staging Phase 1 实测
- 建立独立、安全、可复现的 WP CMP Staging 环境
- 不直接修改生产 Banner / 生产 CMP 配置
- 完成 Phase 1 验收（T1-T8 测试）
- 输出：`CMP_STAGING_PHASE1_EXECUTION_REPORT.md`

### 3. WP 21 项漏洞专项审计
- 完整漏洞台账（每项含：编号/插件/版本/是否启用/CVE/严重性/在野利用/受影响功能/已修复版本/升级兼容性/推荐方案）
- 风险排序：Critical → High → Medium → Low
- 特别识别：在野利用、RCE、权限提升、SQLi、文件上传、任意文件读取、停止维护
- 不批准批量修改生产 WP 插件；先在 CMP Staging 验证
- 输出：`WORDPRESS_21_VULNERABILITIES_SECURITY_AUDIT.md`

### 4. 持续运营监控
- 保持：CI Secret Scanning / CI Pre-check / Staging Acceptance / Production Deploy / SSH S4 / Fail2ban / Gitleaks
- 不允许为了维持绿色状态而屏蔽失败检查
- GA4：继续真实访客触发原则，不创建虚假访客、不注入测试事件、不创建测试订单、不修改生产 GA4 配置

---

## 三、生产变更授权边界

- **本轮特别授权**：仅允许为 F2 机密整改进行必要的生产配置和凭据轮换。
- **其他**（生产功能、数据库业务数据、WooCommerce、GA4、CMP、B2B）均不在本次生产变更授权范围。
- CMP Staging 和插件漏洞测试必须与生产隔离。
- 任何影响生产业务连续性的异常，立即停止相关变更并执行已验证的回滚方案。

---

## 四、最终交付

必须提交：
1. `F2_PRODUCTION_SECRET_REMEDIATION_REPORT.md`
2. `CMP_STAGING_PHASE1_EXECUTION_REPORT.md`
3. `WORDPRESS_21_VULNERABILITIES_SECURITY_AUDIT.md`
4. `D8_E_ROUND3_EXECUTION_SUMMARY.md`

总结报告必须明确区分：VERIFIED / PASS / BLOCKED / PARTIAL / FAILED / NOT VERIFIED
报告包含 Git Commit、工作流 Run ID、测试时间、证据路径、遗留风险及负责人。

---

## 五、最终完成标准

- **F2**：生产硬编码机密清除，真实凭据完成轮换，旧凭据失效。
- **CMP**：完成隔离环境部署和 Phase 1 验收。
- **WP**：21 项漏洞完成完整分级和整改计划。
- **GA4**：没有违反真实访客验证原则。
- **CI**：所有既有核心 Gate 继续正常。
- **生产**：没有未经授权的业务变更。

---

## 六、红线与原则

- 禁止为了追求 ALL GREEN 而降低验收标准。
- 不允许直接修改生产 Banner 或生产 CMP 配置。
- 发现正在被利用的 Critical 漏洞时，立即提交 Owner 紧急风险通知，不得等待例行报告。
- 第一优先：F2 生产机密整改。
- **现在开始执行。**

---

*Owner 第三轮指令存档：2026-11-20，DSH 从 ChatGPT 对话提取*
