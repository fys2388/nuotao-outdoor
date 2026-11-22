# M4.2.0-R3 PostgreSQL CI 并发验证证据报告

> 采购审批治理 R3 轮 · 并发安全证据
> 关联文件：`.github/workflows/ci-check.yml`、`backend/tests/test_concurrency_approval_postgres.py`、`backend/app/services/supply_chain.py`
> 报告目的：向 Owner 证明「CI 真跑双连接并发审批、不能 skip」这一要求如何落地，并诚实标注哪些已验证、哪些需 CI 运行时确认。

---

## 1. 目标

Owner 明确要求：**CI 必须真跑双连接并发审批，不能 skip。**

拆解为两条可验收标准：

1. 必须存在**两个独立连接/会话**同时审批同一张 draft 采购单（PO）的真实竞态，而不是单连接顺序调用。
2. 该竞态必须在 CI 中**实际执行**，不能因为「环境缺 Postgres」而被 `pytest.skip` 静默跳过。

R2 阶段已写好并发测试文件（Postgres 用例在无 Postgres 时 skip），R3 补齐了让它在 CI 里**真跑**的基础设施。

---

## 2. 为什么需要独立 Postgres job

CI 原有的 `backend` job 使用**内存 SQLite**。SQLite 单文件/单连接模型下，无法在同一时刻承载两个独立写者，因此：

- 内存 SQLite **物理上无法复现**两个连接争抢同一行的写-写竞态；
- 在 SQLite 上「并发」只能退化为顺序调用，第二个调用读到第一个已提交的状态——这验证的是**应用层不变量**（状态机拒绝二次审批），而非**物理层行锁竞态**。

结论：要让 Postgres 双连接用例真跑，必须有一个**独立 job 专门提供 PostgreSQL service** 并设好连接串。这就是 R3.5 新增 `postgres-concurrency` job 的原因。它与 SQLite 的 `backend` job 互补并存，不是替换。

---

## 3. CI job 设计

`.github/workflows/ci-check.yml` 现有**三个并列 job**：`backend`、`postgres-concurrency`、`frontend`。新增的 `postgres-concurrency` job（第 48–94 行）设计如下。

### 3.1 PostgreSQL service container

```yaml
services:
  postgres:
    image: postgres:16
    env:
      POSTGRES_USER: nuotao
      POSTGRES_PASSWORD: nuotao
      POSTGRES_DB: nuotao_test
    ports:
      - 5432:5432
    options: >-
      --health-cmd "pg_isready -U nuotao"
      --health-interval 10s
      --health-timeout 5s
      --health-retries 5
```

- 镜像 `postgres:16`，与生产基线（PostgreSQL 16）一致。
- user/pass `nuotao/nuotao`，db `nuotao_test`，端口 `5432`。
- 带 `pg_isready` health check（间隔 10s、超时 5s、重试 5 次），service 就绪后才进入测试步骤。

### 3.2 环境变量 TEST_DATABASE_URL

```yaml
env:
  TEST_DATABASE_URL: postgresql+asyncpg://nuotao:nuotao@localhost:5432/nuotao_test
```

这是「不能 skip」的关键开关：并发测试文件里的 `_is_postgres()` 通过判断 `TEST_DATABASE_URL` 是否以 `postgres`/`postgresql` 开头来决定跑真并发还是 skip。本 job 设了指向 Postgres 的连接串，所以 Postgres 用例**真跑、不 skip**。

> job 同时注入 `JWT_SECRET_KEY`/`PII_HMAC_KEY`/`PII_ENCRYPTION_KEY`（CI 测试值），与 `backend` job 一致，保证应用模块在 import 期可正常加载。

### 3.3 Wait for PostgreSQL 步骤

```yaml
- name: Wait for PostgreSQL
  run: |
    for i in $(seq 1 30); do
      if pg_isready -h localhost -p 5432 -U nuotao; then echo "postgres ready"; break; fi
      sleep 2
    done
```

在 service health check 之外再做一次显式轮询（最多 30 次 × 2s = 60s），降低偶发连接失败导致的 flaky。

### 3.4 真跑命令

```yaml
- name: Dual-connection concurrent approval tests (real row locks)
  run: pytest tests/test_concurrency_approval_postgres.py -q --no-header -p no:warnings
```

直接针对并发测试文件运行 pytest。

### 3.5 与 backend SQLite job 互补

| job | 数据库 | 跑什么 | 物理竞态 |
|---|---|---|---|
| `backend` | 内存 SQLite | 全量单元测试（应用层不变量）；Postgres 用例 skip | 否（单连接） |
| `postgres-concurrency` | Postgres 16 service | 仅 `test_concurrency_approval_postgres.py`；Postgres 用例真跑 | **是**（双连接行锁） |

两者互补：`backend` 保证应用层状态机在默认环境全绿；`postgres-concurrency` 专门验证物理层双连接竞态。

---

## 4. 并发测试三用例

文件 `backend/tests/test_concurrency_approval_postgres.py` 含三个测试。

### 4.1 `test_concurrent_approve_postgres_single_winner`（Postgres 真并发）

- 依赖 `pg_engine` fixture：仅当 `TEST_DATABASE_URL` 指向 Postgres 才创建真实异步引擎；否则 `pytest.skip`（fixture 内显式 skip）。
- 准备两个独立 admin 用户（admin_a / admin_b）和一张 `cost_confirmed=True` 的 draft PO。
- 通过 `asyncio.gather` 让 `_attempt(admin_a)` 与 `_attempt(admin_b)` **各自持独立 session/connection** 并发审批同一 PO。
- 断言：恰一个 winner（`ok`）、一个 loser（捕获 `SupplyChainError`）、`approved_by` 记录唯一 winner 且属于两位竞速者之一、终态 `status == "approved"`。

### 4.2 `test_concurrent_approve_sqlite_application_invariant`（SQLite 降级）

- 在 CI 默认 SQLite 环境跑。同一 `db_session` 上顺序调用两次审批：第二次读到第一次已提交的非 `draft` 状态，被状态机拒绝。
- 断言同样恰一 winner / 一 loser，但明确这是**应用层不变量**，物理竞态无法在 SQLite 上复现。

### 4.3 `test_concurrency_mode_is_declared`（模式声明）

- 诚实声明当前跑的是 `postgres_dual_connection` 还是 `sqlite_application_invariant`，防止在 SQLite 环境里静默夸大成「已覆盖物理并发」。SQLite 模式下额外断言 `not _is_postgres()`，把「未跑物理竞态」显式记录。

---

## 5. 审批行级锁机制

`backend/app/services/supply_chain.py` 中的锁实现（R2 收尾 commit `1fc9645` 补齐）：

`_load_purchase_order` 增加 `for_update` 参数（第 706–727 行）：

```python
if for_update:
    stmt = stmt.with_for_update()
return (await session.execute(stmt)).scalar_one_or_none()
```

- `for_update=True` 时附加 `.with_for_update()`，生成 `SELECT .. FOR UPDATE`，在 Postgres 上对目标行加**行级写锁**。
- 审批 choke point `_transition_purchase_order`（第 819 行起）调用它时传 `for_update=True`（第 847–848 行），使所有审批写路径都经过该锁。
- `approve_purchase_order` 路径（第 614–615 行）同样传 `for_update=True`。

**single-winner 保证**：两个连接同时审批同一 PO 时，Postgres 行锁把写者**串行化**——第二个连接的 `SELECT .. FOR UPDATE` 阻塞直到第一个提交；随后它重新读到 `status != "draft"`，`_apply_status_transition` 抛 `SupplyChainError`，fail-closed。于是恰一 winner。

> 注：SQLite 下 `.with_for_update()` 是 no-op，锁不生效，故 SQLite 只能验证应用层不变量——这正是需要独立 Postgres job 的根本原因。

---

## 6. 验证状态（诚实）

必须清晰区分「已就绪」与「已执行验证」：

**已就绪（代码层面，已人工核对）：**

- 并发测试文件三用例写就，Postgres 用例具备真实双连接竞态逻辑；
- CI `postgres-concurrency` job 写就，提供 Postgres 16 service + `TEST_DATABASE_URL` + 真跑 pytest 命令；
- 审批行级锁代码写就，`for_update=True` 贯穿审批 choke point。

**实际执行验证发生在 CI 运行时：**

- 本次撰写环境（DSH 开发环境）本地**仅有 SQLite，无 Docker/Postgres**，**无法在本地实跑 Postgres 双连接竞态**。
- 因此对「物理层双连接竞态」的定性是：**测试代码就绪 + CI job 就绪 + 行级锁代码就绪；实际执行验证发生在 CI `postgres-concurrency` job 运行时，需 CI 跑一次确认绿。**
- **不声称**「已在本地验证物理竞态」。

**backend job（SQLite）验证范围：**

- 验证应用层不变量（状态机拒绝二次审批），这是 Postgres 竞态 single-winner 所依赖的同一道应用层护栏。

一句话边界：**基础设施已 100% 就绪，但「物理竞态真跑且绿」这一结论要等 CI `postgres-concurrency` job 实际运行一次才能盖章。**

---

## 7. 如何本地复现

在本地起一个 Postgres 并设 `TEST_DATABASE_URL`，即可真跑双连接竞态：

```bash
# 1. 起 Postgres（Docker）
docker run -d --name nuotao-pg-test \
  -e POSTGRES_USER=nuotao -e POSTGRES_PASSWORD=nuotao -e POSTGRES_DB=nuotao_test \
  -p 5432:5432 postgres:16

# 2. 等待就绪
docker exec nuotao-pg-test pg_isready -U nuotao

# 3. 设连接串并跑并发测试（backend 目录）
cd backend
export TEST_DATABASE_URL=postgresql+asyncpg://nuotao:nuotao@localhost:5432/nuotao_test
pytest tests/test_concurrency_approval_postgres.py -q
```

此时 `_is_postgres()` 为真，`test_concurrent_approve_postgres_single_winner` 真跑、不 skip。

> 注：撰写环境本地无 Docker，上述命令未在本地执行，仅供复现参考。

---

## 8. 结论

- **已就绪**：Postgres 双连接并发测试（三用例）、CI 独立 `postgres-concurrency` job（Postgres 16 service + `TEST_DATABASE_URL` + 真跑命令）、审批行级锁（`SELECT .. FOR UPDATE` 贯穿 choke point）。
- **实际执行在哪**：物理层双连接竞态的执行验证在 CI `postgres-concurrency` job 运行时；应用层不变量验证在 `backend`（SQLite）job。
- **边界清晰**：两者互补；本地（无 Docker/Postgres）无法实跑物理竞态，故本报告不声称本地已验证物理竞态。「CI 真跑、不能 skip」由 `postgres-concurrency` job 设 `TEST_DATABASE_URL` 指向 Postgres 保证——该 job 下 Postgres 用例真跑、不 skip，满足 Owner 要求；最终以 CI 一次绿色运行为盖章。