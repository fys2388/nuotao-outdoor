# M4 V2.6 — Product / Variation 身份模型实现与数据关联验证（Owner 正式指令）

> 来源：ChatGPT「定价原则评审」会话（2026-11-23），V2.5 终审通过后下达。
> 状态：**正式启动**（生产权限保持关闭）。

## 1. 本轮目标

将 M4 V2.5 已验收的 PRODUCT / VARIATION / UNKNOWN_LEGACY 三态身份设计，推进到**本地开发和隔离测试环境可运行实现**。目标是解决以下实体的身份关联：WooCommerce Product / WooCommerce Variation / Supplier / 1688 Offer / ProductMapping / OrderItem / InventorySnapshot / ProductCost / CostSnapshot。**本轮不是生产上线任务。**

## 2. P0：整理 V2.5 交付并建立 Git 基线

- 执行 `git status --short`，列出全部 tracked / modified / untracked 文件。
- 逐一确认 V2.5 文档交付文件。
- 检查是否意外包含 Cookie、Token、API Key、密码、个人信息、生产数据。
- 执行 `git diff --check`。
- 确认提交范围仅包含已验收的 V2.5 审计与设计文档。
- 文档单独提交，**禁止使用 `git add .`**。
- 记录文档提交 SHA，建立 V2.6 开发基线。
- 不得提交未审核的业务代码或无关文件。

## 3. P0：实现商品身份模型

根据现有数据模型设计实现，**不得绕过现有 workspace 隔离和 event_service 写入规范**。身份至少包含：PRODUCT / VARIATION / UNKNOWN_LEGACY。关键要求：

1. `wc_product_id` 明确对应 WooCommerce Product ID。
2. `wc_variation_id` 明确对应 WooCommerce Variation ID。
3. `variation_sku` 作为辅助识别字段，**不得作为身份主键**。
4. `wc_variation_id` 为空**不自动认定为 PRODUCT**。
5. `UNKNOWN_LEGACY` 必须保留未知状态，**不允许自动关联到某个具体变体**。
6. `workspace_id` 必须参与所有身份关联和唯一性约束。
7. 商品级与变体级**分别设置唯一性约束**。
8. 使用符合 PostgreSQL 语义的**部分唯一索引**，测试 NULL 和重复记录边界。
9. 保留历史数据兼容路径。
10. 必须提供完整 **Alembic migration 和 downgrade 草案**。

## 4. P0：Supplier / 1688 Offer 独立映射

**不得**把 `source_offer_id` 简单设计成 WooCommerce 变体的一对一属性。必须支持：一个变体对应多个供应商；一个变体对应多个 Offer；同一供应商不同规格与不同 Offer；Offer 更换、失效、历史报价保留；规格映射不确定时保持未确认状态。建议建立**独立的供应商报价及映射实体**。映射至少有：`workspace_id / supplier_id / source_offer_id / wc_product_id / wc_variation_id / specification_mapping / mapping_status / evidence_source / effective_at / source_timestamp`。具体字段可结合现有模型调整，但必须提供关系图、唯一性和冲突处理策略。

## 5. P0：核心业务关系改造

审计并实现以下模块的变体身份关联：ProductMapping / OrderItem / InventorySnapshot / ProductCost / CostSnapshot / Inventory upsert / Inventory alert / Product upsert。要求：

- 新订单优先记录确定的 Product / Variation 身份。
- 历史订单身份无法确定时保留 UNKNOWN_LEGACY。
- 库存更新以确定的 Variation 身份为主要依据。
- 不允许仅凭父 SKU 更新整个变体集合。
- 成本快照必须明确对应 Product 或 Variation。
- 供应商报价变化不得覆盖已形成的历史成本快照。
- 所有写操作继续走 event_service。
- 变体身份和历史关系变更必须保留 trace_id 及审计记录。

## 6. P1：历史数据回填模拟

基于 V2.5 核实后的 71 行数据制作隔离测试数据：70 个 VARIATION；1 个 PRODUCT；0 个 UNKNOWN_LEGACY。额外制作无法识别、缺失 ID、重复映射、错误 SKU、多个 Offer 冲突等异常样本。测试必须证明：70 个变体不会发生身份冲突；PRODUCT 记录不会被错误归入 VARIATION；UNKNOWN_LEGACY 不会被自动识别为 PRODUCT；错误映射不会覆盖正确映射；多供应商报价可以独立存在；历史 OrderItem 和成本快照不会被错误重关联；重复执行回填不会重复创建数据。**不得对生产数据库执行历史回填。**

## 7. P1：自动化测试

至少覆盖：PRODUCT 创建和读取；VARIATION 创建和读取；UNKNOWN_LEGACY；Product/Variation 唯一性；SKU 重复和 SKU 缺失；workspace 隔离；多 Offer 映射；Offer 失效；ProductMapping 冲突；OrderItem 变体关联；Inventory 变体级更新；Inventory 防止父商品误更新；CostSnapshot 历史一致性；回填幂等；Migration upgrade/downgrade；event_log 和 trace_id；历史兼容。**不得只以单元测试代替真实 PostgreSQL 集成测试。**

## 8. 明确禁止

本轮不授权：生产数据库迁移；生产历史数据回填；生产库存同步；生产 WooCommerce API 写入；自动采购；自动加购；促销及价格调整；修改生产 SKU；自动变更生产规则；任何未经 Owner 批准的生产部署。所有 migration 只能在隔离开发或测试数据库验证。

## 9. 交付与停止条件

提交：V2.5 文档 Git commit SHA；V2.6 身份模型实现说明；ER 关系图；数据库迁移及回滚文件；Supplier/Offer 映射设计；ProductMapping、OrderItem、InventorySnapshot、CostSnapshot 改造报告；71 行历史数据模拟回填报告；PostgreSQL 集成测试结果；完整测试数量及 PASS/FAIL；Ruff 结果；migration upgrade/downgrade 结果；Git diff、commit SHA、branch、worktree 状态。

**完成后立即停止，提交 Owner 终审。** 没有新的书面授权，禁止任何生产环境操作。
