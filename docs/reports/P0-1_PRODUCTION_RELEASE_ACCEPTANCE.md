# P0-1 B2C 首页产品网格修复 — 生产发布验收报告

- 对象: `https://nuotaooutdoor.com/` 首页 "Featured Outdoor Gear" 产品网格
- 发布日期: 2026-11-18 (UTC)
- Owner 授权: ChatGPT「系统开发和优化」对话明确批准「应用该段 CSS 到生产」
- 授权范围: 仅本次首页 Featured Outdoor Gear 产品网格修复，不含其他生产变更
- 应用方式: WordPress 定制器（外观 → 自定义 → 额外 CSS）追加
- **状态: PASS**（三端验证全部通过）

---

## 1. 生产应用记录

| 项 | 值 |
|---|---|
| 应用路径 | WordPress 定制器 → Additional CSS → CSS code（CodeMirror） |
| 应用动作 | 在现有「额外 CSS」末尾**追加**修复段（未覆盖/未清理其他 CSS） |
| 定制器状态 | `wp.customize.state('saved')` 由 `false` → `true`，Publish 按钮变 "Published"（禁用） |
| 发布确认 | ✅ Publish 成功（savedState=true，无待保存变更） |
| 生产页面确认 | 导航到线上 `https://nuotaooutdoor.com/`（非定制器预览 iframe），CSS 已生效 |

### 应用前「额外 CSS」备份

应用前完整备份（Owner 硬要求），存档 `infra/woocommerce/backup-additional-css-pre-p0-1.css`：

```css
.nuotao-footer a[href*="b2b.nuotaooutdoor.com"], footer a[href*="b2b.nuotaooutdoor.com"] { display:none !important; }
```

（仅 1 条规则，117 字符。发布后「额外 CSS」= 上述原规则 + 追加的 P0-1 修复段，共 747 字符。）

### 应用后「额外 CSS」追加段

```css
/* P0-1 fix: homepage Featured Outdoor Gear product grid collapse (2026-11-18).
   Root cause: WooCommerce woocommerce-layout.css sets li.product width:22.05% (float-era
   4-col value) while this ul is display:grid (4 x ~258px tracks) -> 22.05% x 258px = 57px.
   Scope: homepage Elementor widget data-id="58c34fe9" ONLY (never global li.product).
   Rollback: delete this block. See infra/woocommerce/b2c-featured-grid-fix.css */
.elementor-element-58c34fe9 ul.products.columns-4 > li.product {
  width: 100%;
  max-width: 100%;
  justify-self: stretch;
}
.elementor-element-58c34fe9 ul.products.columns-4 {
  display: grid;
}
```

源文件: `infra/woocommerce/b2c-featured-grid-fix.css`（内容一致）。

---

## 2. 缓存清理记录

| 缓存层 | 动作 | 结果 |
|---|---|---|
| WordPress / LiteSpeed (LSCache) | 管理栏 LiteSpeed → **Purge All**（`litespeed_type=purge_all`） | ✅ 已执行（跳转回首页） |
| Cloudflare 页面缓存 | 无凭据，未直接清 CDN | ⚠️ 见下方说明 |

> **Cloudflare 缓存说明（诚实边界）**：本次执行无 Cloudflare API 凭据，未直接 purge CDN 边缘缓存。但 CSS 已在真实生产页面**三端 DOM 实测生效**（见 §3），且 WordPress「额外 CSS」以内联 `<style>` 输出、随 HTML 一起变更，故页面缓存未阻塞本次修复可见性。如 CDN 仍缓存旧 HTML，边缘缓存会按其 TTL 自然过期；若需立即全球生效，请 Owner 用 Cloudflare 控制台执行一次 "Purge Everything"。

---

## 3. 三端验证（真实生产页面 DOM 实测）

### 3.1 桌面端（1331px 视口）

| 项 | 修复前 | 修复后（生产实测） |
|---|---|---|
| `li.product` 宽度（8 个） | 56.89px ❌ | **258px** ✅ |
| 产品图高度 | 55px ❌ | **256px** ✅ |
| 标题宽度 | 55px ❌ | **256px** ✅ |
| Add to cart 按钮 | 不可见 | **可见** ✅ |
| grid-template-columns | 258px×4 | **258px×4**（4 列）✅ |
| 横向溢出 | 无 | **无**（scrollWidth 不超 clientWidth）✅ |
| 8 卡片 allFilled | 否 | **是** ✅ |

截图: `docs/reports/evidence/p0-1/desktop-homepage-featured-grid.png`

### 3.2 平板端（ipad-mini，744px 视口）

| 项 | 值 |
|---|---|
| 视口宽 | 744px |
| `ul.products` 宽 | 676px |
| grid-template-columns | **328px×2**（2 列）|
| `li.product` 宽度（8 个） | **328px** ✅ |
| 产品图高度 | **326px** ✅ |
| Add to cart 按钮 | **可见** ✅ |
| 卡片塌陷（<120px） | **无** ✅ |
| 横向溢出 | **无**（scrollW 744 = clientW 744）✅ |

截图: `docs/reports/evidence/p0-1/tablet-homepage-featured-grid.png`

### 3.3 手机端（iphone-se，375px 视口）

| 项 | 值 |
|---|---|
| 视口宽 | 375px |
| `ul.products` 宽 | 307px |
| 列数 | **单列** |
| `li.product` 宽度（8 个） | **307px** ✅ |
| 产品图高度 | **305px** ✅ |
| Add to cart 按钮 | **可见** ✅ |
| 卡片塌陷（<120px） | **无** ✅ |
| 横向溢出 | **无**（scrollW 375 = clientW 375）✅ |

截图: `docs/reports/evidence/p0-1/mobile-homepage-featured-grid.png`

### 三端验收对照（Owner 发布后验收标准）

| 验收项 | PASS 标准 | 结果 |
|---|---|---|
| 首页 8 个产品卡片 | 全部正常填满 Grid 列 | ✅ 三端均填满 |
| 产品图片 | 无异常压缩/裁切/变形 | ✅ 256/326/305px 正常 |
| 产品标题 | 正常换行、无溢出 | ✅ 宽度随卡片 256px |
| Add to cart | 正常显示、可操作 | ✅ 三端均可见 |
| 桌面端 | 4 列布局正常 | ✅ 258px×4 |
| 平板端 | 无挤压、无横向溢出 | ✅ 328px×2，无溢出 |
| 手机端 | 卡片布局正常、按钮可见 | ✅ 单列 307px，按钮可见 |
| 其他页面 | 无 CSS 外溢 | ✅ 见 §4 隔离验证 |
| 缓存 | 清理后重新加载仍正常 | ✅ LiteSpeed Purge All 后实测正常 |

---

## 4. 隔离验证（Owner 硬约束：分类页/详情页/相关产品不受影响）

作用域选择器 `.elementor-element-58c34fe9` 仅命中首页唯一 Elementor widget，理论零外溢。已在真实生产页面实测确认：

| 页面 | `ul.products` | 命中首页作用域 | 卡片宽度 | 塌陷 | 横向溢出 | 结论 |
|---|---|---|---|---|---|---|
| 首页 `/`（Featured） | 1 个 | 是（8 卡片） | 258px | 无 | 无 | ✅ 修复生效 |
| 分类页 `/shop/` | 1 个（12 卡片） | **否**（`inHomepageWidget=false`） | 262–263px | 无 | 无 | ✅ 未受影响 |
| 产品详情页 `/product/rechargeable-headlamp-mh1/`（相关产品） | 1 个（2 卡片） | **否** | 251px | 无 | 无 | ✅ 未受影响 |

- 分类页 12 卡片全部正常（262px），主区布局正常，未被首页作用域命中。
- 详情页相关产品模块卡片 251px 正常，主产品摘要区 547px 正常，无外溢。
- **隔离结论: PASS** — 修复仅影响首页 Featured 的 8 个卡片，分类页/详情页/相关产品零外溢。

---

## 5. 回滚方案（100% 可逆）

若出现布局异常、按钮不可用或其他页面受影响：

1. 进入 WordPress 定制器 → Additional CSS；
2. **仅删除本次追加的 P0-1 修复段**（`/* P0-1 fix ... */` 起至 `.elementor-element-58c34fe9 ul.products.columns-4 { display:grid; }` 止）；
3. 保留原有 `.nuotao-footer ... display:none !important;` 规则（或整体恢复 `backup-additional-css-pre-p0-1.css` 内容）；
4. 点击 Publish；
5. LiteSpeed Purge All 清缓存；
6. 重新验证首页恢复原状。

无其他文件改动、无数据库改动、无主题/插件/WooCommerce 核心改动。

---

## 6. 交付清单（对照 Owner 要求）

| Owner 要求项 | 状态 |
|---|---|
| 生产应用时间 | ✅ 2026-11-18 (UTC) |
| WordPress「额外 CSS」应用前后记录 | ✅ 见 §1（备份 + 追加段） |
| 桌面/平板/手机截图 | ✅ `docs/reports/evidence/p0-1/` 三张 |
| 8 个卡片实际 DOM 宽度 | ✅ 见 §3（258/328/307px） |
| 分类页和产品详情页隔离验证 | ✅ 见 §4 |
| 缓存清理记录 | ✅ 见 §2（LiteSpeed 已清；Cloudflare 见说明） |
| 最终 Git Commit | ✅ 见本次提交 |
| 验收报告 | ✅ 本文件 |

### 边界重申（授权范围）

- **仅**应用了首页 Featured 网格修复 CSS，未做其他生产变更。
- **未**更新主题/插件（管理栏仍显示 "14 updates available"，未触碰）。
- **未**修改 WooCommerce 核心文件、Elementor 页面结构、商品价格/库存。
- **未**修改生产数据库（CSS 通过定制器标准接口应用）。
- Cloudflare CDN 缓存未直接 purge（无凭据），见 §2 说明。

---

## 7. 最终结论

- 根因: WooCommerce `li.product{width:22.05%}` 与主题 grid 冲突 → 卡片塌陷至 ~57px。
- 修复: 用 Elementor 唯一 widget id `58c34fe9` 限定作用域，覆盖 `li.product` 宽度为 `100%`。
- 生产发布: ✅ 已通过 WordPress 定制器应用并 Publish，三端 + 隔离全部实测通过。
- **P0-1 状态: PASS**。

**验收人**: Nuotao Dev Agent (Sensenova)
**发布授权**: ChatGPT（Owner）—「应用该段 CSS 到生产」
