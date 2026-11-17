# M420-01 审计报告：B2B 展示商品定位与映射

> 状态：**PASS** ｜ 范围：M420-01 ｜ 日期：2026-11-17

## 结论
- 生产 WC 12 款 `publish` 商品已定位并映射到 nuotao `products` 表（`woocommerce_id` 唯一键）。
- B2B 展示商品数：**12/12**（`b2b_showcase_enabled=true`，1 页）。
- 类别原值三种形态（英文内部 key / 数字 ID / WC 英文名+中文历史值）已统一映射。

## 证据
- API `GET /api/v1/b2b-showcase/products?page_size=50` → `total=12`、`items=12`。
- 12 款均含 `woocommerce_id`、`sku`、5 张真实图（`https://nuotaooutdoor.com/wp-content/uploads/...`）。
- 关闭 12 款历史遗留展示商品（非 WC 12 款）后，展示集合 = WC 12 款。

## 备注
- 12 款封闭商品保留在库（`b2b_showcase_enabled=false`，可逆）。
