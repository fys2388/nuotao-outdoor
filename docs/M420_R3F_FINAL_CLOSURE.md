# M4.2.0-R3-Final — 采购成本真实性 + 权限审计收尾

Owner 指令来源：ChatGPT 对 PR #26 commit b886c64 的复审。R3 六项主整改已通过，
R3-Final 是复审提出的补充收尾（3 个缺口 + 1 项文档修复）。本提交为独立追加，
保留 R0/R1/R2/R3 全部历史，不合并 PR #26。

## R3-F1 成本来源真实性补强（P0）

`supply_chain._resolve_real_item_cost` 由返回裸 `Decimal` 升级为返回**可审计结构**：

```python
{product_id, sku, product_cost_id, purchase_cost,
 currency, version, valid_from}
```

- 逐 SKU 记录来源 ProductCost 的身份（`product_cost_id`）与版本（`version`）、生效时间（`valid_from`），确认事件可追溯「哪条成本行/哪个版本产出了确认金额」。
- **币种护栏（fail-closed，不引入自动汇率）**：`confirm_purchase_order_cost` 强制校验 `ProductCost.currency == PO.currency`；不一致 → `SupplyChainError("currency mismatch ... no auto FX")`，绝不把别币种金额写进 PO，也绝不自动换汇。本轮明确不做自动 FX。
- **product_id / SKU 一致性护栏**：当 item 同时带 product_id 与 sku，二者必须指向同一 Product；不一致（product.sku != item.sku）→ 拒绝（返回 None → 整单回滚）。杜绝 SKU 兜底静默取到「别家成本」。
- `cost_snapshot` 补全来源字段：`product_cost_id` / `product_cost_version` / `product_cost_valid_from` / `currency` / `line_total`（此前只有 sku/quantity/unit_cost）。

## R3-F2 操作者角色审计闭环（P1）

修复「身份已 DB 验证、但事件 actor_role 留空」的审计缺口：

- `_validate_approver` / `_validate_procurement_actor` 由只返回 `user.id` 改为返回 `(user_id, role)`——role 来自 DB `users.role`，非调用方传入。
- 四操作函数 `order/cancel/receive/partial_receive`：解构 (id, role)，把 DB 验证的 role 作为 `caller_role` 透传给 `_transition_purchase_order`，事件 payload `actor_role` 记录权威角色（此前四函数不传 role → payload `actor_role=None`）。
- `approve_purchase_order` / `transition_purchase_order_status`：同步解构并透传验证后的 role。
- `create_purchase_order` / `update_purchase_order`：service 层新增 `_validate_procurement_actor` DB 校验，事件补 `actor_role`（此前仅记录 caller 传入的 actor_user_id）。
- `confirm_purchase_order_cost`：事件 `actor_role` 记录确认人 DB 角色（替换掉实现期的占位逻辑）。

## R3-F3 财务金额与审计幂等测试（P1）

新增 `tests/test_r3f_financial_audit.py`（6 个测试，读 DB + event_log，不只断言返回值）：

1. **多 SKU 精确金额**：两种不同真实成本 → 逐 SKU unit_cost/line_total、subtotal/total 全部从 ProductCost 精确重算（读 purchase_order_items 验证）。
2. **币种不一致失败**：CNY 成本 vs USD PO → fail-closed，status/cost_confirmed/金额均不变，零成本确认事件。
3. **product_id/SKU 不一致失败**：标识冲突 → 整单回滚，不确认。
4. **幂等单事件**：重复确认 → event_log 恰一条 `supply.purchase_order_cost_confirmed`。
5. **全链路 actor_role**：cost-confirm= admin、ordered/partial_received/received= operator、created 事件 actor_role 均非空且匹配 DB 用户角色。
6. **create/update 事件 actor_role**：两者事件均记录非空 actor_role = operator。

> 实现说明：测试用 `supply_chain.create_purchase_order`（item 带 product_id）直接建 PO，
> 绕开 `fulfillment_service.create_purchase_order_from_order` 的 SKU 兜底路径——该路径
> `_get_product_cost_detailed` 访问 `product.cost` 关系会触发 async 惰性加载
> （MissingGreenlet）。这是既存代码的既存特性，非本轮引入；R3-F3 的目标是直接测
> `confirm_purchase_order_cost`，故绕开它。

## R3-F4 文档与编码修复

- 恢复 `fulfillment_service.py` 头部及全文中文文档字符串/注释（R3 提交时被 ruff-format 按错误编码写成 mojibake 乱码，如 `閲囪喘/鍙戣揣鏈嶅姟`）。现已全部还原为正确中文。
- 本报告 + 校正文档指引。

## 验证

- `tests/test_r3f_financial_audit.py`：6 passed。
- 回归 `test_cost_blocker + governance_t02 + supply_chain + r1_fulfilment`：50 passed（R3-F1/F2 改动未破坏现有功能）。
- ruff 阻塞门禁（F821/F811/E9/F）全绿；`py_compile` 通过。

## 明确禁止（遵守）

未自动采购/审批/下单、未接真实支付、未部署生产、未改全局硬规则、未引入自动汇率、未合并 PR #26。

## 关联

- PR #26（保持 Open）
- 前序：commit b886c64（R3 六项）
