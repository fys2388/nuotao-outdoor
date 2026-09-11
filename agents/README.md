# Agents — AI Agent 定义目录

M0 阶段**不开发业务 Agent**。本目录预留给五个业务 Agent 的规格与定义：

- `product_manager/` — AI 产品经理（依据 `docs/product_strategy.md` 与 `docs/operating_rules.md`）
- `marketing_manager/` — AI 营销经理
- `supply_chain_manager/` — AI 供应链经理
- `customer_manager/` — AI 客户经理
- `business_analyst/` — AI 商业分析

开发原则（详见 `AGENTS.md` §3）：

- Agent 只通过 `services` 层与规则引擎访问数据，禁止直连数据库/文件系统。
- 高风险操作只提议，人工审批后执行；全链路审计（`ai_agent_runs`）。