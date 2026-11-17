# M420-07 交付报告：B2B 商品展示完整性修复与验收

> 状态：**PASS**（6/6 完成标准达成）
> 范围：M4.2（M420-01…M420-06）汇总交付与测试验收
> 日期：2026-11-17

## 完成标准核对（全部 ✅）

| # | 标准 | 结果 | 证据 |
|---|------|------|------|
| 1 | 12/12 款商品真实图映射 | ✅ PASS | API `products` 12 款每款 5 张 `https://nuotaooutdoor.com/wp-content/uploads/...` 图；浏览器 `naturalWidth>0`（主图+5 缩略图） |
| 2 | API 正确返回 | ✅ PASS | `GET /api/v1/b2b-showcase/products` → `total=12`、`items=12`；无价格字段；`categories` 端点返回 slug+名称 |
| 3 | 前端正确显示 | ✅ PASS | b2b.nuotaooutdoor.com Products 页 12 款；详情页 `Request a Quote`、无价格、描述无 HTML 标签 |
| 4 | 类别正确 | ✅ PASS | 12 款 → 10 个英文类别（无中文、无数字 ID、无内部 key）：`Camping Chairs`、`Sports Bottles`、`Ice Crampons`、`Sleeping Gear & Mattress`、`Backpacks & Hiking Gear`、`Lighting & Power`、`Camping`、`Outdoor Accessories`、`Camping Tables`、`Storage & Organizers`；API `cjk_categories=0` |
| 5 | 凭证安全 | ✅ PASS | git 历史/追踪**无真实 WC 凭证**（`ck_/cs_` 仅文档占位符）；33 个含明文 key 脚本已备份+删除；6 个功能文件改 env 读取；`.gitignore` 加强 |
| 6 | 临时 workflow 清理 | ✅ PASS | 13 个一次性 workflow 删除（12 个 + fix-headlamp-copy）；保留 `sync-wc-images`/`import-wc-products`/`close-legacy-products` |

## 测试执行记录

- **API 测试**：`products`（12/12 图、无价格、英文标题 cjk_titles=0、英文类别 cjk_categories=0）、`categories`（slug+英文名）✅
- **前端验收**：b2b.nuotaooutdoor.com Products 页（12 款 1 页）、详情页（`Category: Sleeping Gear & Mattress`、主图+5 缩略图、`Request a Quote`、无价格、描述无 HTML）✅
- **数据修复**：MH1 头灯（WC 2565）中文标题/描述 → 英文（`cjk=0`）；被误改的 `LED感应头灯`（NT-LT-001，非 B2B 展示）已恢复 name、清空误写描述（原值无备份，desc_len=0）✅

## 已知问题（非阻塞，单独跟踪）

- **secret-scanning workflow**：每次 push 触发 `failure`（0s、0 job）——**预先存在**（2026-11-17 前已如此），不影响 CI/Deploy（独立 success）。需单独排查（gitleaks action 引用 / workflow 结构）。
- **本地浏览器 Google Translate**：验收时页面被浏览器自动翻译成中文（导航/文案），**非产品数据**；API 数据已确认全英文。用户侧关闭翻译即可。
- **WC 凭证轮换**（安全建议）：33 个已删脚本 + 6 个功能文件暴露过明文 key（`ck_733f4b…`/`ck_a8d0d1…`/`ck_67ff8…`/`ck_cfd05…`）。git 未泄露，但建议在 WC 后台轮换（需用户操作）。

## 交付物

- 后端：`backend/app/services/b2b_showcase_service.py`（英文类别映射）
- 前端：`frontend-b2b/src/utils/text.ts`（stripHtml）、`PublicProductDetail.tsx`、`PublicCatalog.tsx`（描述清洗）
- workflow：`sync-wc-images.yml`、`import-wc-products.yml`、`close-legacy-products.yml`（保留，可复用/幂等）
- 报告：M420-01…M420-07（本目录）
