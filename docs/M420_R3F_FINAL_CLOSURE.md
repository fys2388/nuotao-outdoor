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

- `tests/test_r3f_financial_audit.py`：**9 passed**（经 R3-Final.1/.2 追加，见下）。
- 回归 `test_cost_blocker + governance_t02 + supply_chain + r1_fulfilment`：共 59 passed（R3-F1/F2 改动未破坏现有功能）。
- ruff 阻塞门禁（F821/F811/E9/F + RUF002/RUF059）全绿；`py_compile` 通过。
- CI（commit 0780aa6）全部 pass，含 PostgreSQL 双连接并发 job（真并发 3 passed）。

## 明确禁止（遵守）

未自动采购/审批/下单、未接真实支付、未部署生产、未改全局硬规则、未引入自动汇率、未合并 PR #26。

## 关联

- PR #26（保持 Open）
- 前序：commit b886c64（R3 六项）、350992e（R2 审计文档校正）

---

# R3-Final.1 / R3-Final.2 — 复审窄范围补修

Owner（ChatGPT）对 R3-Final 首轮提交 `4004239` 独立复审后，点名 4 个缺口并授权窄范围
补修（不扩大采购治理范围）。分两个独立 commit 落地，全部保留历史、不合并 PR #26。

## commit ee38dad — R3-F1 SKU 兜底漏洞（P0）

`_resolve_real_item_cost` 存在身份绕过：当 `product_id` 有值但解析不到对应 Product 时
（`product_by_id=None`），旧实现会跳过一致性护栏、继续走 SKU 兜底，从而取到**另一个产品
的成本**。

修复（P0，成本身份权威化）：
- 只要 `item.product_id` 非空，就必须由它解析出当前 workspace 中真实存在的 Product 且其
  ProductCost 有效；否则 **fail-closed 返回 None**，绝不回落到 SKU。
- SKU 兜底路径**仅在完全没有 product_id 时**启用。
- `product_id` 与 `sku` 同时存在时要求 `product.sku == item.sku`，不一致也拒绝。

## commit 0780aa6 — R3-Final.2 四项收尾

### 缺口 2 — R3-F2 履约尾状态 actor_role 透传（P1）
`transition_purchase_order_status` 的 shipped/delivered/completed 分支调
`_transition_purchase_order` 时漏传 `caller_role`，导致这些事件 `actor_role` 为 None。
已补 `caller_role=caller_role`（该函数顶部已 `caller_role = verified_actor_role` 即 DB
验证角色）。同步把 `_validate_approver` 返回类型注解由 `-> str` 更正为 `-> tuple[str, str]`。

### 缺口 3 — R3-F3 非零运费 + 完整成本快照断言（P1）
`test_nonzero_shipping_and_full_audit_snapshot` 加强：
- 运费用 **12.34**，断言 `subtotal=18.00 / shipping=12.34 / total=30.34` 精确；
- cost-confirmed 事件断言 PO 级 `from_status` / `to_status` / `actor_user_id` / `actor_role` / `trace_id`；
- `cost_snapshot` 逐 SKU 断言全字段，**含 `product_cost_valid_from`**。

### 缺口 1 回归测试 — 幽灵 product_id + 有效 SKU（P0）
新增 `test_product_id_without_product_rejects_no_sku_fallback`：建有效 PO 后把 item 的
`product_id` 改成不存在的幽灵 id（保留有效 sku），断言成本确认失败、`cost_confirmed`
仍为 False、状态停在 `pending_cost_confirmation`——证明 ee38dad 的 SKU 兜底修复生效。

### 缺口 4 — R3-F4 mojibake 全文清零（P1）
清理 `fulfillment_service.py` 剩余 3 处乱码（`榛樿工作空间`→`默认工作空间`、
`浼樺厛绾э細`→`优先级:`、`缁熻总数`→`统计总数`），全文乱码扫描归零，通过 RUF002 检查。

## R3-F3 测试清单（最终 9 个，读 DB + event_log，不只断言返回值）

1. 多 SKU 精确金额（逐 SKU 从 ProductCost 重算）
2. 币种不一致 → fail-closed，金额/状态不变、零事件
3. product_id/SKU 不一致 → 整单回滚
4. 幂等单事件（重复确认恰一条成本确认事件）
5. 全链路 actor_role 非空且匹配 DB 角色（cost-confirm/ordered/partial_received/received/created）
6. create/update 事件 actor_role 非空
7. **非零运费 12.34 + 完整成本快照断言**（PO 级 + 逐 SKU 含 valid_from）
8. **取消操作 actor_role**（cancelled 事件 = operator）
9. **幽灵 product_id fail-closed**（不触发 SKU 兜底，成本确认失败）

## R3-Final.1/.2 验证

- `tests/test_r3f_financial_audit.py`：9 passed。
- 采购治理回归共 59 passed。
- ruff 阻塞门禁全绿；`py_compile` 通过。
- CI（commit 0780aa6）全部 pass，含 PostgreSQL 双连接并发（真并发 3 passed）。

## 明确禁止（持续遵守）

未自动采购/审批/下单、未接真实支付、未部署生产、未改全局硬规则、未引入自动汇率、
未扩展 M4.2.1、未合并 PR #26。
