# M420-04 类别映射报告

> 状态：**PASS** ｜ 范围：M420-04 ｜ 日期：2026-11-17（英文统一版）

## 结论
- `category` 字段历史脏数据（英文内部 key / 数字 ID / WC 英文名 / 中文历史值）统一映射为**英文显示名 + 英文 slug**。
- 12 款 → 10 个英文类别，无中文、无数字 ID、无内部 key 暴露。
- 前端直接显示 API `category`（无本地中文硬编码）。

## 实现
- `backend/app/services/b2b_showcase_service.py`：`_CATEGORY_EN`（`raw → (英文名, slug)`）+ `_category_display()`（未命中映射 → 英文兜底 `Outdoor Gear`）+ `_category_db_values()`（slug 筛选）。
- 提交：`76ce4e6`（fix(b2b) unify showcase category display to English）。

## 证据
- API `products` → `cjk_categories=0`；10 类别：`Camping Chairs`、`Sports Bottles`、`Ice Crampons`、`Sleeping Gear & Mattress`、`Backpacks & Hiking Gear`、`Lighting & Power`、`Camping`、`Outdoor Accessories`、`Camping Tables`、`Storage & Organizers`。
- `categories` 端点返回 slug + 英文名。

## 备注
- 早期版本曾映射为中文（M420-04 首版）；按用户"统一英文"决策改版（`76ce4e6`）。
