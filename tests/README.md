# Tests — 测试策略与目录说明

分层策略（详见 `AGENTS.md` §2.5）：

| 层级 | 位置 | 说明 |
|---|---|---|
| 单元/接口测试 | `backend/tests` | pytest，随后端代码就近存放 |
| 集成测试 | `backend/tests`（M1 起，Testcontainers） | 数据库/外部系统 |
| E2E 测试 | `tests/e2e/`（M1 起，Playwright） | 订单全流程等跨层场景 |

质量门禁：lint + 单测 + 集成 + 依赖扫描全绿方可合并（见 `docs/development_roadmap.md`）。