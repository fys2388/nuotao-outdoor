# M4 V2.6 71 行身份回填报告（隔离数据模拟）

> 版本：v2.6.0 | 输入：`docs/_audit/PRICING_V2_3_SKU_UNIQUENESS.csv`（71 行）
> 执行：隔离内存 SQLite（测试环境），**未触碰生产库**

## 1. 分类结果

| 身份 | 行数 | 说明 |
|---|---|---|
| `VARIATION` | 70 | 有 `wc_variation_id` 的变体行 |
| `PRODUCT` | 1 | 商品 2687（父商品，无变体 SKU，显式 `product_has_variations=False`） |
| `UNKNOWN_LEGACY` | 0 | 无未归类行 |
| **合计** | **71** | |

## 2. 关键校验点（对应测试）

- **70 变体无身份冲突**：每个 `(workspace, woocommerce_id, woocommerce_variation_id)` 仅一条变体级映射。
- **PRODUCT 未被误归类**：2687 判定为 `PRODUCT`（`attrs` 含「父商品」/`has_unique_variation_id='NO_MISSING_ID'` 且无变体 SKU）。
- **`UNKNOWN_LEGACY` 不自动 `PRODUCT`**：空 vid + 无证据 → 保持 `UNKNOWN_LEGACY`，不做商品级映射。
- **错误映射不覆盖正确映射**：同键（同 Offer）更早 `effective_at` → `archived`，保留最新。
- **多供应商/多 Offer 独立**：不同 `source_offer_id` 不构成冲突。
- **历史 `OrderItem` / 成本快照不重链接**：新增列不强制重写历史行。
- **幂等回填**：第二次回填全部 `skipped`（命中部分唯一键），不重复创建。

## 3. 回填结果（模拟）

| 项 | 第一次 | 第二次（幂等） |
|---|---|---|
| created | 71 | 0 |
| skipped | 0 | 71 |
| errors | 0 | 0 |

## 4. 生产回填状态

**未执行**。生产回填需 Owner 单独书面授权后执行（指令 §8）；本报告为隔离数据模拟验证结果。

## 5. 数据来源

- `docs/_audit/PRICING_V2_5_IDENTITY_71ROW_AUDIT.md`：71 行审计分析。
- `docs/_audit/PRICING_V2_3_SKU_UNIQUENESS.csv`：71 行原始数据（70 变体 + 1 父商品 2687）。
