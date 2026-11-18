# M4.4 下一步指令（来自 ChatGPT，2026-11-17）

> ChatGPT 在「系统开发和优化」对话基于 M4.3 开发状态报告生成的完整下一步指令。
> 对话回复标题：**Nuotao B2B 下一阶段开发指令**
> 回复状态：**回答已完成**（停止按钮消失、复制/评价/朗读/分享可用）。

## 指令结论（核心）
- **下一阶段：M4.4 — B2B Lead Management & Sales Workflow**
- 目标：从「询价成功入库」升级到「内部可管理、可跟进、可报价、可审计的业务闭环」。
- 完成定义：一条真实 Lead 从创建到关闭，所有状态变化、责任人、报价记录和通知结果均可追踪。
- 优先级：**P0** = Lead 数据审计 / Admin Lead 管理 / 权限与隐私；**P1** = 报价管理 / 通知可靠性 / 审计统计；**P2** = 销售分析。

## M440 子任务
- **M440-01 前置审计**：只读检查 Git/commit、`b2b_leads` 结构/迁移、`create_public_lead`/`notify_new_lead`/`convert_lead_to_application`、Admin RBAC、PII 存储（明文→需报告+迁移方案）、两条测试 Lead（LD-20261117-6B43B6 / LD-20261117-3ECF02）标记、secret-scanning 失败原因。输出 `reports/b2b/M440-01_PRE_AUDIT.md`。
- **M440-02 Lead 状态机**：NEW/ASSIGNED/CONTACTED/QUALIFIED/QUOTING/QUOTED/NEGOTIATING/CONVERTED/CLOSED_WON/CLOSED_LOST/SPAM；后端状态转换服务；非法转换拒绝；每次变化记录 actor/old/new/time/reason；审计日志。
- **M440-03 Admin Lead 管理**：列表/分页/筛选（状态/SKU/国家/时间）、详情、分配负责人、状态更新、内部跟进备注、状态历史、通知历史；遵循 RBAC；Public API 不得读取 Lead。
- **M440-04 报价管理**：Lead Quote 模型（quote_id/lead_id/quote_version/currency/unit_price/quantity/shipping_cost/estimated_total/valid_until/payment_terms/shipping_terms/approval_status/approved_by/created_at）；版本不可覆盖；未审批不发送；注明币种与贸易条件；不自动生成未验证盈利承诺。
- **M440-05 通知可靠性**：通知状态/失败原因/重试次数/重试记录/重复通知防护/最终失败状态；Lead 创建与通知解耦；通知失败不回滚 Lead。
- **M440-06 安全与隐私**：Public API 不能读 Lead；Admin 认证+RBAC；内部备注不暴露；PII 按项目规范；日志不泄露凭证/PII；状态/报价/分配可审计。PII 明文→P0 风险报告。
- **M440-07 测试与数据质量**：Lead 创建/读取权限、状态合法/非法转换、负责人分配、备注权限、报价版本、报价审批、通知失败重试、重复通知防护、测试 Lead 排除、PII 脱敏、Admin 越权、Public 越权。不删真实数据。
- **M440-08 经营统计**：Total/Valid Leads、By Country/Product/Status、Avg Response Time、Quote/Conversion Rate、Lost Reasons；排除测试/垃圾/无效 Lead；缺失数据不补造。
- **M440-09 最终验收与报告**：输出 M440-01…09 报告；每项 PASS/NEEDS_EVIDENCE/BLOCKED/NOT_STARTED；含 Git commit/变更文件/迁移/测试/Ruff/构建/E2E/安全/未完成/Owner 待决。

## 三个独立问题（不混入 M4.4）
1. **secret-scanning 0-job failure**：必须查明具体原因（不能仅凭「预先存在」视为无风险），单独建立 CI 安全问题记录。
2. **测试 Lead 标记**：LD-20261117-6B43B6 / LD-20261117-3ECF02 必须标记为测试数据，不得计入真实销售统计。
3. 其余按 ChatGPT 对话说明。

## 安全与生产授权边界（本阶段）
- 允许：本地开发/测试、测试环境验证、文档与测试代码修改。
- **不默认授权**：生产 DB 迁移、生产 Lead 批量修改、删除真实 Lead、生产报价发送、客户自动邮件、Admin API 对公网开放、DNS/Cloudflare/Nginx 配置、生产部署、生产 WC 商品/价格/库存修改、联系供应商或客户。
- 需 Owner 审批：生产迁移/部署/数据修改/正式报价发送。

## 完成标准（M4.4）
1. Lead 生命周期可完整管理；2. Admin 权限与客户隐私通过测试；3. 状态转换有审计；4. 报价版本与审批有效；5. 通知失败可追踪恢复；6. 测试 Lead 不污染统计；7. 自动化测试通过；8. 生产安全边界未突破。任何 P0 未通过 → COMPLETED_WITH_NEEDS_EVIDENCE 或 BLOCKED，不得宣布全面完成。

## 完整指令
完整 DSH 执行指令文档（:::writing 块，含 M440-01…09 细节）保存在 ChatGPT「系统开发和优化」对话本回复；本文件为摘要，执行时按对话全文核对。
