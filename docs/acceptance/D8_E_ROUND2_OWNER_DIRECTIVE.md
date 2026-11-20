# Owner 第二轮完整执行授权指令（D8-E）

**来源**：ChatGPT "D8-E下一步指示" 对话（2026-11-20）
**授权人**：Owner
**项目**：Nuotao AI OS
**阶段**：Production Operational Assurance & CMP Staging Validation

---

## 一、总体目标

基于 D8-E 第一轮 ALL CORE WORKFLOWS GREEN 的结果，进入第二轮运营验收。本轮目标：
1. 完成第一轮 6 份交付报告的 **Owner 独立审核**。
2. 消除 CMP Staging Phase 1 的**前置阻塞**。
3. 完成 CMP Staging **真实环境测试**（前提是获得合法测试凭证）。
4. 建立 GA4 **真实访客条件触发机制**。
5. 持续验证 **CI、Secret、SSH 及生产工作流稳定性**。

---

## 二、任务执行顺序

### P0：D8-E 第一轮独立审计

- 逐份审查 6 份报告。
- 必须区分状态：**VERIFIED**（有独立原始证据）/ **PASS**（符合验收标准）/ **READY**（准备完成但未实测）/ **BLOCKED**（存在外部依赖）/ **NOT VERIFIED**（缺乏充分证据）。
- **不得将 READY 或 BLOCKED 标记为 PASS。**
- 重点核实：
  - 是否存在只有报告、没有原始证据的情况？
  - CI 成功是否真正代表部署和运行成功？
  - SSH S4 是否具备独立验证证据？
  - CMP 是否存在同意记录、撤回、拒绝 Cookie 等缺口？
  - Secret 是否存在误配置、过期或权限过大的问题？
  - 是否存在尚未披露的生产风险？
- **输出：`D8_E_ROUND2_OWNER_INDEPENDENT_AUDIT.md`**

### P1：CMP Staging Phase 1

- 需要准备：**Staging WordPress URL、独立 Staging 管理员账号、必要的测试权限**。
- **注意：账号凭证通过安全渠道提供，不要写入 Git、日志或普通报告。**
- 测试范围（验收目标）：
  | 测试项目 | 验收目标 |
  |---|---|
  | 首次访问 | Consent Banner 正常显示 |
  | Accept All | 同意状态正确记录 |
  | Reject All | 非必要 Cookie 不加载 |
  | Customize | 分类设置有效 |
  | Withdraw Consent | 撤回后状态正确 |
  | 页面刷新 | Consent 状态持久化 |
  | 不同浏览器 | 行为一致 |
  | 网络及脚本异常 | Fail-closed，不默认放行 |
- 必须保留浏览器证据、Network 请求记录、Cookie 状态及测试时间。
- **未通过验收，不允许进入生产发布。**
- **输出：`CMP_STAGING_PHASE1_EXECUTION_REPORT.md`**

### P2：GA4 Realtime

- 保持等待真实访客触发。
- 禁止：人工制造虚假访客、创建测试订单、修改生产 GA4 配置、将内部测试流量误认为真实访客。
- 真实访客出现后，按既定验证方案执行。
- **输出：`GA4_REALTIME_VERIFICATION_RESULT.md`**

### P3：CI + Secret 持续运营审计

- 持续检查：GitHub Actions 工作流、Secret 配置状态、Secret Scanning、CI Pre-check、Staging Acceptance、Production Deploy。
- 发生异常时，**先定位原因，再提出修复方案**。
- **不得擅自轮换生产密钥或改变生产权限。**
- 输出：CI_SECRET_OPS_AUDIT_ROUND2.md

---

## 三、本轮绝对禁止事项（未经 Owner 单独授权）

1. 不允许生产发布。
2. 不允许生产数据库修改。
3. 不允许修改生产 GA4。
4. 不允许创建真实订单。
5. 不允许注入 B2B 数据。
6. 不允许绕过 CMP Consent。
7. 不允许修改生产 Secret。
8. 不允许扩大用户授权范围。

---

## 四、交付要求

每项任务必须提供：
- 执行时间
- Git Commit（如适用）
- 执行命令
- 原始证据
- 测试结果
- 遗留问题
- 风险等级
- 是否需要 Owner 决策

最终生成：`D8_E_ROUND2_EXECUTION_SUMMARY.md`

---

## 五、最终验收标准

只有满足以下条件，才能宣布第二轮完成：
- P0：6 份报告完成独立审核。
- P1：CMP Staging Phase 1 完成真实环境验收，**或者明确记录外部阻塞**。
- P2：GA4 保持真实流量触发原则。
- P3：CI 和 Secret 审计持续正常。
- 所有未解决风险均有责任人和后续计划。

**特别注意**：本轮目标是提高系统可信度和运营成熟度，**不是追求更多代码、更多 Commit 或更多 PASS 数量**。任何未经验证的结果不得宣布完成。

---

*Owner 权威指令存档：2026-11-20，DSH 从 ChatGPT 对话提取*
