# M4 V2.5 P0-2 — 历史数据身份分类及 71 行逐行核对报告

- 指令：`docs/_audit/V2_5_CHATGPT_DIRECTIVE.md`（三、P0，交付第 4 项）
- 数据源：`docs/_audit/PRICING_V2_3_SKU_UNIQUENESS.csv`（71 行 WC 快照）
- 核对方法：逐行判定 `identity_state`（VARIATION / PRODUCT / UNKNOWN_LEGACY）+ 唯一性校验

---

## 1. 汇总

| 身份状态 | 行数 | 说明 |
|---|---|---|
| `VARIATION` | **70** | 每行唯一 wc_variation_id + 唯一 WC 变体 SKU（0 重复） |
| `PRODUCT` | **1** | 2687 净水器（无变体，商品级正确） |
| `UNKNOWN_LEGACY` | **0** | 本批 71 行快照全部可确定身份 |
| **合计** | **71** | 70 变体 + 1 产品级商品 |

- 唯一性校验：70 个变体 ID 全部唯一；70 个 WC 变体 SKU 全部唯一；无冲突。
- **71 行 = 70 个有效变体 + 1 个产品级商品**（2687），与"70 个有效变体"一致。
- 结论：**本批快照无 UNKNOWN_LEGACY**；但历史订单/库存/成本快照可能含无法确定变体的记录（设计层面保留 UNKNOWN_LEGACY，见身份模型）。

## 2. 商品分布（70 变体，11 商品）

| wc_product_id | 商品 | 变体数 |
|---|---|---|
| 2549 | 防水手机袋 | 3 |
| 2565 | 迷你工作灯 | 2 |
| 2593 | 徒步背包 | 3 |
| 2669 | 月亮椅 | 3 |
| 2698 | 充气睡垫 | 13 |
| 2743 | 加热睡袋内胆 | 14 |
| 2763 | 冰爪（含本次改价 2771/2772） | 12 |
| 2785 | 收纳包（含本次改价 2792） | 10 |
| 2818 | 雪套 | 2 |
| 2838 | 钛水壶 | 6 |
| 2864 | MH1 头灯 | 2 |
| **合计** | | **70** |

## 3. 逐行核对表

- PRODUCT（1 行）：2687 / （空） / NT-972602197791 / Portable Water Filter / PRODUCT。
- VARIATION（70 行）：完整逐行表见 `docs/_audit/PRICING_V2_5_IDENTITY_71ROW_DETAIL.md`（70 行，每行 wc_product_id / wc_variation_id / 变体 SKU / 商品名 / VARIATION，全部唯一）。

### 关键变体行（本次改价 + 加购门禁）

| wc_product_id | wc_variation_id | 变体 SKU | 身份 | 备注 |
|---|---|---|---|---|
| 2763 | 2772 | NT-746435358585-10-B-M | VARIATION | 本次改价 $11.57→$11.99 |
| 2763 | 2771 | NT-746435358585-10-O-M | VARIATION | 本次改价 $11.57→$11.99 |
| 2785 | 2792 | NT-818076845448-100x20x20 | VARIATION | 本次改价 $11.58→$11.99 |
| 2763 | 2769 / 2770 | NT-746435358585-8-*-M | VARIATION | ADDON CONDITIONAL |
| 2785 | 2791 | NT-818076845448-90x20x20 | VARIATION | ADDON BLOCKED |

## 4. 结论

- 71 行快照身份**全部确定**：70 VARIATION + 1 PRODUCT + 0 UNKNOWN_LEGACY。
- 唯一性无冲突（变体 ID / 变体 SKU 均唯一）。
- 身份模型按 `PRICING_V2_5_IDENTITY_MODEL.md` 落地（PRODUCT/VARIATION/UNKNOWN_LEGACY 三态 + 部分唯一索引）；本批快照可安全回填为 PRODUCT/VARIATION，无 UNKNOWN_LEGACY 需人工核对。
