# M420-05 页面验证报告

> 状态：**PASS** ｜ 范围：M420-05 ｜ 日期：2026-11-17

## 结论
- 12 款展示商品：**标题全英文**（`cjk_titles=0`）、**类别全英文**（`cjk_categories=0`）、真实图 5 张、无价格。
- MH1 头灯（WC 2565，slug `nuotao-mh1`）中文标题/描述 → **英文**（`nuotao Duke MH1 Rechargeable Headlamp…`，`cjk=0`，desc_len=697）。
- 前端 `stripHtml` 清洗描述（无 `<p>` 残留、无 `dangerouslySetInnerHTML`）。

## 实现
- `frontend-b2b/src/utils/text.ts`（stripHtml：去标签+解实体）；`PublicProductDetail.tsx`、`PublicCatalog.tsx` 使用。
- MH1 英文文案：`b8ce74f1-b805-4c2c-9e07-9ac524738e0b`（展示层更新，不动 WC）。

## 证据
- API `products`：`total=12`、`cjk_titles=0`、`cjk_categories=0`、12 款 5 图。
- MH1 API 输出：英文标题、`desc_len=697`、`cjk=0`、`showcase=True`。

## 备注
- 误改的 `LED感应头灯`（`7355fbde…`，sku `NT-LT-001`，非 B2B 展示 `showcase=False`）：name 已恢复，误写的 MH1 描述已清空（原值无备份，`desc_len=0`；非展示产品，无用户可见影响）。
