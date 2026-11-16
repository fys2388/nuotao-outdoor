# 1688 来源去重：重复选品与重复上架修复

> **版本**: v1.0
> **最后更新**: 2026-10-03
> **状态**: Active
> **关联文档**: `PRODUCT_LIFECYCLE_WORKFLOW.md`、`wc_unpublish_design.md`、`AGENTS.md`

---

## 1. 问题

审计确认存在两个 bug，第二个是第一个传导出来的。

### Bug-1：同一 1688 链接被重复「选品」

`products` 表对 1688 链接**没有任何唯一约束**——唯一的唯一性保障是 `(workspace_id, sku)`
部分唯一索引。而全库检索确认：**所有候选/产品创建的查重都按 SKU，没有任何一处按
`source_url` / `offer_id` / `meta->>'source_id'` 查重**。

致命放大器是 SKU 的生成方式：`NT-<LLM生成标题>-<MMDDHHMM>`（分钟级时间戳 + AI 标题）。
同一个链接在不同时间导入必然得到不同 SKU，因此连 SKU 查重也一起失效。

次要路径同样漏：`create_product_candidate` 无条件 INSERT 且 SKU 缺省为
`SKU-<epoch秒>`；牛顿选品的 SKU 拼了列表下标 `_i`（换个位置就是另一个 SKU）。

### Bug-2：同一 1688 商品被重复「上架」到 WooCommerce

由 Bug-1 传导：同一 offer 的两条候选 SKU 不同 → 各自推送 → gated 通道的「按 SKU
收养已有商品」只对本行自己的 SKU 生效 → 两条都不匹配 → 各自 POST → **WC 里两个商品**。

另有两条独立缺口：

- **旧推送通道**（`woocommerce_sync_service.push_product_to_woocommerce`）只看
  `meta["woocommerce_id"]`，**没有任何 SKU 反查**，也不读 `product_mappings`；
- **`list_to_woocommerce`** 无条件 POST，只新建不更新，且上架后不回写 `wc_id`
  （`auto_list` 路径因此永远学不到自己的 WC 商品 ID）。

---

## 2. 根因分层与对应修复

| 层 | 根因 | 修复 |
|---|---|---|
| ① 数据模型 | 对来源链接没有唯一约束，应用层「先查后插」可被并发绕过 | 新增 `source_offer_id` + 部分唯一索引 |
| ② 标识 | SKU 由 LLM 标题 + 时间戳构成，天然漂移 | 有 offer id 时 SKU 完全由它决定 |
| ③ 通道 | 两条推送实现并存且幂等能力不同；映射表从未被写入 | 统一「认领 + 回写」，三处通道共用 |

**顺序有意义**：① 是根本防线（数据库约束），② 让 SKU 层也能对账，③ 保证不会因为
映射丢失而重复创建。

---

## 3. 修复①：来源唯一键

### 3.1 数据模型

`products` 新增列：

```
source_offer_id VARCHAR(32) NULL   -- 规范化后的 1688 数字 offer id
```

新增部分唯一索引（迁移 `0069_product_source_offer_id.py`）：

```sql
CREATE UNIQUE INDEX uq_products_workspace_source_offer
    ON products (workspace_id, source_offer_id)
    WHERE deleted_at IS NULL AND source_offer_id IS NOT NULL;
```

两个条件都是刻意的：

- `deleted_at IS NULL`：商品进回收站后不占用来源键，同一 offer 可以重新建档，
  与既有 `uq_products_workspace_sku` 的口径一致；
- `source_offer_id IS NOT NULL`：非 1688 来源（手工录入、CSV 导入、WooCommerce
  反向同步）完全不受约束。

### 3.2 来源识别

`product_source_identity.py` 提供唯一真相源：

| 函数 | 作用 |
|---|---|
| `normalize_offer_id(value)` | 只接受 6–32 位纯数字，拒绝空串/空格/带参数/超长 |
| `extract_1688_offer_id(url)` | 支持 `/offer/<id>.html`、`offerId=<id>`、`offer/<id>`、纯 ID |
| `resolve_source_offer_id(...)` | 优先级：显式 `source_id` → `source_url` → `meta` 历史键 |

`meta` 历史键包含 `source_id`、`offer_id`、`product_id_1688`、`ali1688_product_id`
（牛顿选品用的那个）。

**拒绝脏值很重要**：一个带空格或查询串的值写进唯一索引列，会把「同一来源」拆成
多个不同键，反而绕过约束。

### 3.3 幂等建档

`get_or_create_by_source(session, workspace_id, source_offer_id, build, fallback_sku)`
返回 `(product, created)`：

1. 先按 `source_offer_id` 查活行；
2. 再按 `fallback_sku` 查——兼容 `source_offer_id` 列存在之前建立的历史候选；命中时
   **顺手补写来源键**，让它下次直接命中来源查重；
3. 都没有才创建。

**并发安全**：插入包在 `session.begin_nested()`（savepoint）里。撞唯一索引时只回滚
这一次插入并回查已存在的行——没有 savepoint 的话，`IntegrityError` 会让整个请求事务
进入 aborted 状态，同一事务里后续所有语句都会失败。

### 3.4 接入的创建入口

| 入口 | 文件 | 变更 |
|---|---|---|
| pipeline V3.0 闸门建档 | `product_pipeline_service.run_v3_gate` | 改用 `get_or_create_by_source` |
| 手工录入候选 | `sourcing_service.create_product_candidate` | 原无条件 INSERT，改为幂等 |
| 产品智能录入 | `product_intelligence.intake_product` | 原按 SKU 查（且不过滤 `deleted_at`），改为幂等 |
| 牛顿选品 | `newton_sourcing_storage` | 显式传 `source_id`（经 `create_product_candidate` 生效） |

CSV 导入与 WooCommerce 反向同步**不在范围内**：它们不来自 1688，`source_offer_id`
保持 NULL，不受新索引约束。

---

## 4. 修复②：SKU 确定性

### 4.1 规则

```
有 offer id  →  NT-<offer_id>                    # 完全由来源决定
无 offer id  →  NT-<关键词>-<MMDDHHMM>            # 时间戳兜底
```

### 4.2 为什么 SKU 里**不能**保留标题词

第一版实现是 `NT-<关键词>-<offer_id>`，看起来既确定又可读，但**仍然是错的**：
关键词来自 LLM 生成的标题，标题措辞会漂移。

SKU 一旦掺进会漂移的文本：

- 同一 offer 在不同运行里得到不同 SKU，SKU 查重失效；
- 更关键的是 **WooCommerce 侧的 SKU 唯一性防线也失效**——推送时 SKU 不同，WC 就
  不会用 `product_invalid_sku` 拒绝，于是真的建出第二个商品。

因此有 offer id 时 SKU 完全由它决定。可读性由 `name` / 描述承担，SKU 只做标识。

### 4.3 顺带修掉的一个坑

英文本地化流程会「保留原 SKU 的时间戳后缀」：

```python
ts_match = re.search(r"(\d{6,})$", old_sku)
new_sku = re.sub(r"\d{6,}$", ts_match.group(1), new_sku)
```

offer id 本身就是 12 位数字，会被这个正则当成时间戳替换掉，把确定性 SKU 改回漂移值。
现在有 offer id 时**跳过整个后缀搬运**。

### 4.4 其他 SKU 生成点

| 位置 | 变更 |
|---|---|
| `product_intelligence._derive_sku` | 1688 链接优先取 offer id；原先直接 sha1 原始 URL，短链/长链/带 query 串会得到不同 SKU |
| `newton_sourcing_storage` | 去掉列表下标 `_i`，有 offer id 时 SKU 固定 |
| `sourcing_service` | 有来源键时用 `SKU-1688-<offer_id>`，否则时间戳兜底 |

---

## 5. 修复③：推送通道统一

### 5.1 关联管理收敛到一处

`wc_product_link_service.py`：

| 函数 | 作用 |
|---|---|
| `resolve_wc_product_id(product, ...)` | 返回 `(wc_id, adopted)`；`meta` 优先，丢失时按 SKU 反查并标记 `adopted=True` |
| `remember_wc_product(session, product, wc_id, slug)` | 同时写 `meta` 与 `product_mappings`（幂等） |

`product_mappings` 的写入包在 savepoint 里：该表 `woocommerce_id` 唯一，历史脏数据或
并发可能撞约束，此时只回滚这次写入并记日志，**meta 回写仍然保留**（它才是推送路径的
判据），不阻断推送。

### 5.2 三处通道的变更

| 通道 | 原先 | 现在 |
|---|---|---|
| `listing_publish`（gated） | 有 SKU 反查，只写 meta | 补写 `product_mappings` |
| `woocommerce_sync_service.push_product_to_woocommerce` | 只看 meta，无 SKU 反查 | 接入 `resolve_wc_product_id`；创建**或认领**后都回写 meta + mappings |
| `product_listing_service.list_to_woocommerce` | 无条件 POST | 先按 SKU 反查，命中则 PUT 更新，返回 `action: create/update` |

`list_to_woocommerce` 的反查失败按「没有」处理是安全的降级方向：宁可走 POST
（WooCommerce 会用 `product_invalid_sku` 拦住重复 SKU），也不要因为一次反查失败就让
整单上架失败。

### 5.3 补上 auto_list 的回写

`run_pipeline` 的 Step 7 `auto_list` 上架成功后，通过新增的 `_remember_listed_product`
把 WC 商品 ID 写回本地。此前只有 `/product-pipeline/confirm-list` 会回写，导致这条路径
上架的本地行永远没有 `meta.woocommerce_id`，之后任何一次推送都会重新 POST 建新商品。

回写失败不影响流水线结果——商品确实已经在 WooCommerce 上架了，这里只补本地关联。

---

## 6. 存量数据处理

迁移**不回填**存量数据：回填需要与 `extract_1688_offer_id` 一致的正则，且很可能发现
已经存在的重复行。

使用 `backend/scripts/backfill_source_offer_id.py`：

```console
cd backend
python scripts/backfill_source_offer_id.py            # 只读诊断（默认）
python scripts/backfill_source_offer_id.py --apply    # 执行回填
```

脚本行为：

- 从 `source_url` 与 `meta` 解析 offer id；
- **同一 offer 已有多条活行时不动这一组**（否则会撞唯一索引），而是列出
  `id / sku / created_at / name` 交人工处置；
- 只回填「该来源组内仅一行」的记录。

**建议执行顺序**：先跑迁移 → 再跑只读诊断 → 根据重复组规模决定合并策略 → 最后
`--apply`。

> 重复数据该合并、该下架还是该保留是业务决定。脚本刻意不替用户做这个决定。

---

## 7. 落地文件

| 文件 | 内容 |
|---|---|
| `backend/alembic/versions/0069_product_source_offer_id.py` | 加列 + 部分唯一索引 |
| `backend/app/models/product.py` | `source_offer_id` 列与索引定义 |
| `backend/app/services/product_source_identity.py` | 来源识别 + 幂等建档 |
| `backend/app/services/wc_product_link_service.py` | 关联解析 + 回写 |
| `backend/app/services/product_pipeline_service.py` | SKU 确定性 + 闸门建档 + auto_list 回写 |
| `backend/app/services/sourcing_service.py` | 手工录入幂等 |
| `backend/app/services/product_intelligence.py` | intake 幂等 + `_derive_sku` |
| `backend/app/services/newton_sourcing_storage.py` | SKU 去下标 + 来源键 |
| `backend/app/services/woocommerce_sync_service.py` | 旧通道接入反查与回写 |
| `backend/app/services/product_listing_service.py` | 上架改为「存在即更新」 |
| `backend/app/api/v1/endpoints/listing_publish.py` | 补写映射表 |
| `backend/scripts/backfill_source_offer_id.py` | 存量回填与冲突诊断 |

### 测试

| 文件 | 用例数 | 覆盖 |
|---|---|---|
| `tests/test_product_source_identity.py` | 22 | 提取/规范化/优先级；**同一 offer 不同 SKU 不重复建档**；历史行认领；软删不占用来源键；唯一索引兜底 |
| `tests/test_sku_determinism.py` | 6 | SKU 不随标题漂移、不随时间变化；URL 变体得到同一 SKU |
| `tests/test_wc_product_link_service.py` | 11 | 关联解析（含脏值回退）；meta+mapping 双写幂等；映射冲突不阻断；上架 PUT/POST 分支 |

> 本地测试环境的既有阻塞：`tests/conftest.py` 用 SQLite 建表，而
> `users.mfa_backup_codes` 是 PostgreSQL 专有的 `JSONB`，导致全部 DB 相关用例在 setup
> 阶段报错。上述测试刻意**只建所需表**（products、product_mappings），因此可独立运行。

---

## 8. 收尾修复

初次交付后梳理出的缺口已全部处理，仅一项有意保留（见 §9）。

### 8.1 并发推送竞态 → 商品行锁

`resolve_wc_product_id` 之后到 POST 之间是裸窗口：两个并发请求都可能读到「meta 里
还没有 `woocommerce_id`」，于是各自 POST 一次。

修复：创建/认领路径对商品行加 `SELECT ... FOR UPDATE`。

- `listing_publish._load_product(for_update=True)`
- `woocommerce_sync_service.push_product_to_woocommerce`

第二个请求会等在锁上；第一个在 POST 成功后回写 `meta` 并 `commit`（释放锁），于是
第二个拿到锁时已经能看到 id，走**更新**而不是创建。锁与它保护的数据在同一个事务里，
不存在 Redis 短锁那种「锁过期了但事务还没提交」的窗口。

只读预览（`preview_listing_gate`）刻意不加锁，避免无谓阻塞推送。

### 8.2 `product_mappings` 缺 workspace 维度 → 迁移 0070

原约束是全局的 `uq_product_mappings_nuotao_id` / `uq_product_mappings_woo_id`。
WooCommerce 按店铺隔离，同一个数字商品 ID 在不同 workspace 里可能是两个不同商品，
全局唯一会把它们错误地互斥。

改为 `(workspace_id, nuotao_product_id)` 与 `(workspace_id, woocommerce_id)`。

### 8.3 上架回写不再复活软删行

`upsert_local_listed_product` 原来按「workspace + SKU」查**含软删行**并复活。

这与本次新增的来源键唯一索引冲突：`uq_products_workspace_source_offer` 是
`WHERE deleted_at IS NULL` 的部分索引，回收站行不占用键位；若期间同一个 offer 已经
重新建档，复活旧行会直接撞唯一索引。

改为只查活行、找不到就新建，与 WooCommerce 反向同步「删后重传走新建」的口径统一。

### 8.4 异步抓取任务落库

`product_import_job_service._run_fetch_job` 调 `import_from_1688` 时未传 session，
于是异步路径的 V3.0 闸门被标记 skipped、候选也不落库——同一次业务操作，同步接口落
候选、异步任务不落。

修复：任务内用 `async_session_factory` 开会话并传下去。

### 8.5 上架端点鉴权

`listing_publish.py` 的推送端点此前**没有任何鉴权依赖**，而 `api_router` 也没有全局
鉴权，等于任何能访问该 API 的人都能操作线上店铺。

修复：`push_product_to_woocommerce_gated`、`push_products_to_woocommerce_gated`、
`preview_listing_gate` 均挂上 `get_current_user`。

批量端点内部是直接函数调用（不走 FastAPI 依赖注入），因此显式传入了 `_current_user`；
`listing_jobs.push_listing_job` 的调用点也一并更新——这一处如果漏改，会在运行时抛
`TypeError`。

---

## 9. 有意保留

**`parse_1688_url` 与 `extract_1688_offer_id` 正则重复**：保留前者是因为它承载
「解析失败即抛 `ValueError`」的历史契约，且对极短数字 ID 更宽松（纯数字直接返回）。
两处规则目前一致，修改时需同步。

---

## 9. 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-10-03 | 初始版本：来源唯一键、SKU 确定性、推送通道统一三层修复 |
| v1.1 | 2026-10-03 | 收尾五项：并发推送行锁、映射表 workspace 维度、上架回写不复活软删行、异步任务落库、上架端点鉴权 |
