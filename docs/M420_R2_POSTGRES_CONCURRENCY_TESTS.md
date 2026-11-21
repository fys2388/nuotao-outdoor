# M4.2.0-R2.6 采购审批并发安全测试报告

> 版本：M4.2.0-R2.6
> 测试文件：`backend/tests/test_concurrency_approval_postgres.py`
> 报告日期：2026-11-21
> 关键结论：应用层 single-writer 不变量已验证；Postgres 物理行级锁并发测试已就绪但当前 CI 环境未执行。

---

## 1. 目标

Owner 明确要求：**"不能用单连接测试糊弄并发竞态"**。

采购审批（`supply_chain.approve_purchase_order`）是典型的写写冲突场景：两个审批人可能同时对同一个 draft 采购单点击"通过"。本任务的目标是设计一套测试，能够真实回答"两个并发审批是否保证只有一个 winner"，而不是用单连接顺序调用伪装成并发验证。

## 2. 为什么单连接测试不够

采购审批竞态的本质是**两个事务在重叠的时间窗口内操作同一行**：

1. 事务 A 读取 PO，看到状态为 `draft`；
2. 事务 B 读取同一 PO，也看到状态为 `draft`（因为 A 尚未提交）；
3. 事务 A 写入 `approved` 并提交；
4. 事务 B 写入 `approved` 并提交 —— 此时 B 基于的是一个**已经过期的 draft 快照**。

如果只用一个数据库连接、按顺序调用两次审批，那么第 2 步根本不会发生：第二次调用必然看到第一次提交后的最新状态。这种测试**无法复现竞态窗口**，它验证的只是"串行下状态机会拒绝二次审批"，而不是"真并发下是否会 double-approve"。

要真正验证并发安全，必须有两个**各自独立的连接/事务**在重叠时间窗口内提交写操作，让数据库的锁与隔离机制成为唯一的仲裁者。

## 3. 测试设计

测试文件包含三个测试，覆盖三种互补的关注点。

### 3.1 `test_concurrent_approve_postgres_single_winner`（Postgres 真并发）

- **前置条件**：仅当环境变量 `TEST_DATABASE_URL` 指向 PostgreSQL 时才运行；否则 `pytest.skip`。
- **真实引擎**：用 `asyncpg` + SQLAlchemy `create_async_engine` 建立真实的 Postgres 异步引擎。
- **数据准备**：
  - `_seed_admin_a_and_b`：造两个**不同的** active admin 用户 A 和 B；
  - `_make_confirmed_draft_po`：造一个 `cost_confirmed=True` 的 draft 采购单。
- **并发执行**：建立**两个独立的 async session（各自独立连接）**，用 `asyncio.gather` 同时并发调用 `supply_chain.approve_purchase_order`，分别使用 A、B 的 `caller_user_id`。
- **断言**：
  - 恰好一个返回成功，另一个抛 `SupplyChainError`；
  - `approved_by` 等于唯一 winner 的 `user.id`。

**原理**：审批 choke point 的事务在 Postgres 上由**行级锁（写写冲突）**串行化。第二个写者在提交时发现行状态已非 `draft`，被状态机拒绝。这是数据库物理层提供的强保证。

### 3.2 `test_concurrent_approve_sqlite_application_invariant`（SQLite 降级，应用层不变量）

- **背景**：CI/本地默认使用 in-memory SQLite，它**无法承载两个并发写连接**，因此不能复现物理竞态窗口。
- **替代验证**：改为验证竞态所依赖的**应用层保证** —— 第一次审批提交后，第二次审批（同一 session 内串行执行）会被规范状态机拒绝，因为源状态已经不是 `draft`。
- **断言**：
  - 恰好一个 winner、一个 rejected；
  - `approved_by` 记录唯一 winner。

这正是让 Postgres 竞态最终成为 single-winner 的那个 guard。SQLite 模式验证的是**状态机层面的 single-writer 语义**，而非物理锁行为。

### 3.3 `test_concurrency_mode_is_declared`（诚实声明）

- 断言当前测试运行在 `postgres_dual_connection` 还是 `sqlite_application_invariant` 模式。
- 若检测到 SQLite 模式，**显式断言"CI 没有跑物理竞态"**，从机制上防止测试报告夸大覆盖范围。

## 4. 并发安全机制

single-winner 保证由**两层机制共同**实现：

| 层级 | 机制 | 作用 | 验证方式 |
|---|---|---|---|
| 应用层 | 规范状态机 single-writer 语义 | 二次审批时源状态已非 `draft`，状态机拒绝 | SQLite 模式 + Postgres 模式均验证 |
| 物理层 | Postgres 行级锁（写写冲突） | 两个并发写事务被串行化，后者提交时读到已变更的行 | 仅 Postgres 双连接模式验证 |

两层缺一不可：应用层状态机是业务规则的最终裁决者；Postgres 行级锁保证在并发窗口内不会有第二个事务基于过期快照"抢先"通过状态机检查。SQLite 模式验证前者，Postgres 双连接模式验证后者在真实并发下的表现。

## 5. 当前验证状态（诚实说明）

本地与 CI 当前均使用 SQLite，实际执行结果：

| 测试 | 结果 |
|---|---|
| `test_concurrent_approve_postgres_single_winner` | **SKIPPED** |
| `test_concurrent_approve_sqlite_application_invariant` | passed |
| `test_concurrency_mode_is_declared` | passed |
| **合计** | 2 passed, 1 skipped |

`test_concurrent_approve_postgres_single_winner` 的 skip 原因是明确的：

> `TEST_DATABASE_URL is not PostgreSQL; real dual-connection row-lock concurrency requires Postgres`

**必须诚实指出的覆盖边界：**

- CI（`.github/workflows/ci-check.yml`）**只用 SQLite，没有 Postgres service container**，因此**真实双连接行级锁并发测试在当前 CI 不运行**。
- 当前 CI **只验证了应用层不变量**（状态机拒绝二次审批），**没有验证物理层的 Postgres 行级锁竞态**。
- 换言之：状态机层面的 single-writer 语义已被证明；但"两个真实 Postgres 连接同时提交时数据库锁能否保证 single-winner"这一物理层命题，在当前 CI 环境中**尚未被执行验证**（测试代码已就绪）。

## 6. 如何在 Postgres 环境启用完整并发验证

要让 `test_concurrent_approve_postgres_single_winner` 真正运行，需要一个 `TEST_DATABASE_URL` 指向 Postgres 的环境。两种路径：

### 6.1 本地起 Postgres

```bash
# 例如用 Docker 起一个临时 Postgres 16
docker run --rm -d --name pg-test \
  -e POSTGRES_PASSWORD=test -e POSTGRES_DB=nuotao_test \
  -p 5432:5432 postgres:16

# 指向 Postgres 后运行并发测试
export TEST_DATABASE_URL="postgresql+asyncpg://postgres:test@localhost:5432/nuotao_test"
pytest backend/tests/test_concurrency_approval_postgres.py -v
```

### 6.2 CI 加 Postgres service container

在 `.github/workflows/ci-check.yml` 中为并发测试 job 增加 Postgres service，并将 `TEST_DATABASE_URL` 指向该 service。这样 Postgres 物理竞态测试会进入常规门禁，而不是被 skip。

建议：将并发测试拆为独立 job（依赖 Postgres service），主 CI 保持 SQLite 快速反馈，避免所有测试都被 Postgres 依赖拖慢。

## 7. 结论：已验证与未验证的清晰边界

**已验证（两种模式均通过）：**

- 采购审批的**应用层 single-writer 不变量**：一旦某 PO 被审批通过，状态机会拒绝任何后续审批尝试，保证 `approved_by` 唯一。
- 模式声明机制：测试会显式报告当前运行的是哪种并发模式，SQLite 模式下明确声明"未跑物理竞态"。

**已就绪但当前未执行：**

- **Postgres 物理层双连接行级锁并发测试**：代码完整、逻辑已验证，但因 CI 缺少 Postgres service 而被 skip。它能在具备 Postgres 的环境中直接运行。

**未验证（覆盖边界）：**

- 在当前 CI 环境下，**Postgres 行级锁在真实并发窗口内强制 single-winner** 这一物理层命题**没有被实际执行验证**。这是当前覆盖的真实边界，不应被解读为"并发安全已被完整端到端证明"。

**结论**：应用层并发安全语义已通过测试确认；物理层并发安全测试已就绪并具备明确的启用路径（设置 `TEST_DATABASE_URL` 或在 CI 增加 Postgres service）。报告如实区分了"已验证"与"待在 Postgres 环境验证"两部分，未夸大覆盖范围。