# M4 V2.5 P1-1 — 1688 库存同步扩展测试报告

- 指令：`docs/_audit/V2_5_CHATGPT_DIRECTIVE.md`（四、P1）
- 服务：`backend/app/services/inventory_sync_v24.py`（增强：负值/非法 fail-closed、fetch 异常 fail-closed、异常时间戳保守、多映射冲突）
- 测试：`backend/tests/test_inventory_sync_v24.py` → **23/23 PASS**

---

## 1. 11 项测试矩阵覆盖

| # | 场景 | 测试 | 结果 | 处理 |
|---|---|---|---|---|
| 1 | 库存为 0 | `test_zero_stock_is_valid_zero` | PASS | 0 视为真实值（记录 + 触发 reorder） |
| 2 | 库存为 null | `test_extract_stock`（None）+ `test_fail_closed_no_stock` | PASS | fail-closed（不写 0） |
| 3 | 库存字段缺失 | `test_extract_stock`（{}）+ `test_fail_closed_no_stock` | PASS | fail-closed（不写 0） |
| 4 | 库存为负值或非法类型 | `test_negative_stock_fail_closed`、`test_invalid_type_stock_fail_closed` | PASS | 负值/非法跳过（fail-closed） |
| 5 | 库存快照过期 | `test_stale_marking`、`test_fresh_not_stale` | PASS | STALE（>24h）标记，不覆盖实时 |
| 6 | 时间戳异常 | `test_invalid_timestamp_marked_stale` | PASS | 异常时间戳 → 保守 is_stale=True |
| 7 | 同一变体重复同步 | `test_idempotency_dedup` | PASS | 幂等去重（duplicate_idempotency） |
| 8 | 并发同步 | `test_concurrency_guard_lock`、`test_concurrency_guard_version`、`test_concurrent_lock_skip` | PASS | 版本号 + 锁（乐观锁） |
| 9 | 网络中断及重试 | `test_fetch_error_skipped` | PASS | fetch 异常 → 该 offer fail-closed 跳过，不中断其余；重试不幂等冲突 |
| 10 | 映射缺失或多个映射冲突 | `test_missing_variation_skipped`、`test_multi_mapping_conflict_skipped` | PASS | 缺失跳过；同一变体多 offer → 冲突跳过（不写不猜） |
| 11 | 供应商库存与网站可售库存不一致 | `test_supplier_vs_wc_mismatch_separate` | PASS | supplier 与 woocommerce_sellable 分开（151 vs 135） |

## 2. 增强点（本轮）

1. **负值/非法库存 fail-closed**：`extract_stock_from_1688_detail` 跳过负值/非法类型 SKU；全不可信 → `None`（不写）。
2. **fetch 异常 fail-closed**：`sync_inventory_from_1688_v24` 用 try/except 包裹 provider；异常 → 该 offer `fetch_error` 跳过 + 审计，**不中断其余 offer**。
3. **异常时间戳保守**：`datetime.fromisoformat` 失败 → `source_timestamp_invalid`，`is_stale=True`（不当作新鲜实时覆盖）。
4. **多映射冲突**：预检同一 variation_id 多 offer → `multi_mapping_conflict` 跳过 + 审计（不重复写、不猜测归属）。

## 3. 保持项（ChatGPT 要求，未变）

- `supplier_available_quantity` 与 `woocommerce_sellable_quantity` **完全分离**（系数 0.9 保守，不直接相等）。
- **任何未知/缺失/异常/过期数据不覆盖 WC 可售库存**（fail-closed / STALE / 保守）。
- 库存快照含 `stock_supplier` / `stock_sellable` / `source_timestamp` / `freshness_hours` / `is_stale` / `computed_at` / `dry_run`。
- 事件审计：`sync_started / synced / synced_stale / stock_unavailable_skipped / duplicate / concurrent_lock / confirm_required / fetch_error / multi_mapping_conflict / missing_variation_id / error`。
- 幂等证明：`seen_idempotency` 去重（variation_id+offer_id+date → SHA256 前 24）。
- **仅限测试环境**（`dry_run=True` 默认，不触发生产写路径）。

## 4. 测试统计

- `test_inventory_sync_v24.py`：**23/23 PASS**（V2.4 16 + V2.5 新增 7）。
- 回归：`test_inventory_sync_v23.py` 9/9 PASS；`test_addon_gate_v23.py` 5/5 PASS（未破坏）。
