# ADR AGENTS-001 — Agent 业务范围与权限隔离

> 状态：**Accepted**（2026-09-13）  
> 决策编号：AGENTS-001  
> 关联：`COMMERCE-001`、`docs/b2c_b2b_compatibility_audit.md`

---

## Context（背景）

Nuotao AI OS 的 Agent Runtime 是 B2C 与 B2B 共享的系统底座。原有
`agents.domain` 只能表达产品、营销、客户、供应链和运营领域，不能表达
B2C、B2B 或跨业务共享范围。

如果只增加菜单或提示词里的业务描述，B2B Agent 仍可能调用 B2C 工具、
读取跨渠道预算、使用错误的执行策略，或由不具备相应业务权限的审批人处理
高风险动作。因此业务范围必须成为运行时和数据库中的强约束，而不是表单字段。

## Decision（决策）

### 1. 统一范围值域

```text
business_scope = B2C | B2B | SHARED
```

- `B2C`：只服务零售业务，可使用 B2C 与共享能力。
- `B2B`：只服务批发业务，可使用 B2B 与共享能力。
- `SHARED`：可服务两侧，但每次任务仍应记录实际业务范围。

### 2. 范围快照贯穿执行链

以下对象必须保存 `business_scope`：

- Agent 注册表与配置版本。
- 任务、执行、工具。
- 执行策略与预算策略。
- 审批对象与审批角色。

任务创建后，范围不可由执行器或工具调用临时改变。

### 3. 工具访问采用方向性兼容

```text
B2C -> B2C | SHARED
B2B -> B2B | SHARED
SHARED -> B2C | B2B | SHARED
```

未知范围按不兼容处理，禁止默认放行。

### 4. 共享 Agent 也不能隐式获得全范围权限

SHARED Agent 创建任务时应显式提供 B2C、B2B 或 SHARED。为兼容历史 B2C
调用，未提供范围时安全回落为 B2C，而不是 SHARED。

### 5. 版本与注册更新不得自动扩权

- 非 SHARED Agent 不能通过注册更新改为其他范围或 SHARED。
- 非 SHARED Agent 不能发布或激活扩大权限的配置版本。
- SHARED Agent 可以收敛到 B2C 或 B2B，但后续恢复共享需要治理流程。
- 范围变更应通过版本发布和激活留痕，而不是直接覆盖注册表。

### 6. 预算和审批按范围隔离

- 执行策略与预算策略按 `(agent, business_scope)` 独立版本化。
- 月预算使用量按执行范围汇总，B2C 与 B2B 不互相挤占。
- 审批角色带业务范围；B2C 审批人不能处理 B2B 审批。
- 旧数据统一回填 `SHARED`，避免迁移中断，但新任务默认保持最小权限。

## Consequences（后果）

### 正面

- B2C 与 B2B Agent 可以在同一 Runtime 上安全共存。
- 工具、预算和审批形成一致的业务边界。
- 所有执行保留范围快照，便于审计、归因和成本分析。
- 后续增加 B2B Sales、Quotation、Collection Agent 时无需重做权限底座。

### 成本

- 任务创建、策略配置和审批角色需要增加业务范围参数。
- 历史 SHARED Agent 的任务生产者应逐步显式传入范围。
- 旧数据的范围回填采用 SHARED，生产上线前需要按实际职责收敛。

## Verification（验收）

- B2C Agent 调用 B2B 工具被拒绝。
- B2B Agent 调用 B2C 工具被拒绝。
- B2C/B2B Agent 可使用 SHARED 工具。
- 跨范围任务创建、策略配置、预算统计和审批决定被拒绝或隔离。
- 非共享 Agent 无法通过注册更新或版本激活自动扩权。
- 旧数据迁移后默认 `SHARED`。
- PostgreSQL `0039 -> 0040 -> 0039 -> 0040` 迁移往返成功。
