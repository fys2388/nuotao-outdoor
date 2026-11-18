# B2C 首页 Featured 产品网格塌陷修复（P0-1）

- 对象: `https://nuotaooutdoor.com/` 首页 "Featured Outdoor Gear" 产品网格
- 日期: 2026-11-18
- Owner 决策: 批准 B 方案（CSS 定点修复），**生产发布前须二次确认**
- 状态: **NEEDS_EVIDENCE → 已完成修复验证，待 Owner 二次确认发布**
- 边界: 全程只读检测 + 临时预览注入（未写入 WordPress 定制器/数据库/生产 CSS）

---

## 1. 问题（修改前）

首页 "Featured Outdoor Gear" 的 8 个产品卡片严重塌陷挤压，几乎不可见。

### 修改前实测（桌面 1320×631，浏览器 DOM）

| 项 | 值 |
|---|---|
| `ul.products.columns-4` 宽度 | 1092px |
| grid-template-columns | `258px × 4`（容器正常） |
| `ul` display | `grid` |
| `li.product` 宽度 | **56.89px**（应 ~258px）❌ |
| `li.product` display | `list-item` |
| `li.product` justify-self | `auto` |
| 产品图高度 | **55px** ❌ |
| 标题/价格宽度 | 55px ❌ |

### 根因（已定位）

**WooCommerce 默认布局 CSS 与主题 grid 布局冲突**：

- WooCommerce `woocommerce-layout.css?ver=11.3.0` 仍给 `.woocommerce ul.products li.product` 设 **`width:22.05%`**（float 时代 4 列遗留值）。
- 本站首页该 `ul.products` 被 Elementor/Jeg Kit 主题设为 **`display:grid`**（4 列 × ~258px track）。
- `22.05% × grid track(258px) ≈ 57px` → 卡片塌陷成内容宽度。

证据：matchedRules 中 `.woocommerce ul.products li.product { width:22.05% }`（来源 woocommerce-layout.css）。

---

## 2. 修复方案（限定作用域 CSS）

### 作用域（Owner 硬约束：禁止全站通用 `li.product`）

整页**唯一** `ul.products` 位于首页 Elementor widget `data-id="58c34fe9"`（parent container `data-id="36daa0a"`，page id 778）。故用 Elementor 唯一 widget id 限定，绝不外溢到分类页/相关产品模块。

祖先链（修复前实测）：
```
ul.products.columns-4
  > div.woocommerce.columns-4
  > div.nt-section
  > div.nt-page
  > div.elementor-element.elementor-element-58c34fe9.elementor-widget  ← 作用域锚点（data-id=58c34fe9）
  > div.e-con-inner
  > div.elementor-element.elementor-element-36daa0a  ← parent container（data-id=36daa0a）
  > div.elementor.elementor-778  ← 首页
```

### CSS 修复（已存 `infra/woocommerce/b2c-featured-grid-fix.css`）

```css
/* 定点修复：仅首页 Featured widget 内的产品卡片填满 grid 列 */
.elementor-element-58c34fe9 ul.products.columns-4 > li.product {
  width: 100%;
  max-width: 100%;
  justify-self: stretch;
}

/* 可选加固：确保卡片在 grid 轨道内正常排布 */
.elementor-element-58c34fe9 ul.products.columns-4 {
  display: grid;
}
```

### CSS Diff（相对 WooCommerce 默认）

| 属性 | 修改前（WooCommerce 默认） | 修改后（定点覆盖） |
|---|---|---|
| `li.product` width | `22.05%`（≈57px） | `100%`（≈258px） |
| `li.product` max-width | 无 | `100%` |
| `li.product` justify-self | `auto` | `stretch` |

---

## 3. 验证（临时预览注入，未持久化）

通过浏览器 evaluate **临时注入**上述 CSS（仅当前会话生效，未写入 WordPress），实测：

### 修改后实测（桌面 1320×631）

| 项 | 修改前 | 修改后 |
|---|---|---|
| `li.product` 宽度（8 个） | 56.89px ❌ | **258px** ✅ |
| 产品图高度 | 55px ❌ | **256px** ✅ |
| 标题宽度 | 55px ❌ | **256px** ✅ |
| 价格宽度 | — | **256px** ✅ |
| Add to cart 按钮 | 不可见 | **可见** ✅ |
| 卡片高度 | — | 307px |
| 横向溢出 | 无 | **无** ✅ |
| grid-template-columns | 258px×4 | 258px×4（未变）|

全部 8 个卡片 `allFilled=true`（宽度均 >200px）。

### 作用域隔离验证（Owner 硬约束）

| 项 | 值 |
|---|---|
| 页面 `ul.products` 总数 | 1 |
| 命中作用域的 `ul` | 1 |
| 未命中作用域的 `ul` | 0 |
| 命中作用域的 `li.product` | 8 |
| 未命中作用域的 `li.product` | 0 |
| **作用域隔离 OK** | ✅ `scopeIsolationOK=true` |

→ 修复**仅影响首页 Featured 的 8 个卡片**，未外溢到分类页/相关产品模块（本页无其他产品列表）。

---

## 4. 三端验证

| 端点 | 状态 |
|---|---|
| 桌面（1320px） | ✅ 已验证，8 卡片 4 列 258px |
| 平板（~768px） | ⏳ 待发布后验证（当前预览未测） |
| 手机（~375px） | ⏳ 待发布后验证（当前预览未测） |

> 注：平板/手机端需在 WordPress 定制器应用 CSS 后于真实设备/响应式模式验证。当前仅桌面端预览验证完成。

---

## 5. 回滚方案

**100% 可逆**：删除 `b2c-featured-grid-fix.css` 中整段规则即可还原（无其他文件改动、无数据库改动）。

若通过 WordPress 定制器（外观 → 自定义 → 额外 CSS）应用，回滚 = 删除该段 CSS 并保存。建议应用前先复制当前"额外 CSS"全文备份。

---

## 6. 交付清单

| 项 | 状态 |
|---|---|
| 修改文件 | `infra/woocommerce/b2c-featured-grid-fix.css`（新增，含根因/作用域/回滚注释） |
| 修改前证据 | li.product 56.89px、img 55px、根因 woocommerce-layout.css width:22.05% |
| 修改后证据 | li.product 258px、img 256px、8 卡片 allFilled、无溢出 |
| CSS diff | width 22.05%→100%、max-width→100%、justify-self auto→stretch |
| 作用域隔离 | ✅ 仅首页 8 卡片，无外溢 |
| 截图 | 修复后截图已存 `C:\temp\dsh\bsk-screenshot-...-uv7q8a.png` |
| 三端验证 | 桌面 ✅ / 平板 ⏳ / 手机 ⏳（待应用后验证） |
| 回滚方案 | ✅ 删除该段 CSS 即还原 |
| **状态** | **NEEDS_EVIDENCE（桌面已验证）→ 待 Owner 二次确认发布** |

---

## 7. 待 Owner 确认（发布前）

按 Owner 决策"生产发布前，先提交修复前后证据和最终 CSS 差异，等待我确认发布"，现提交：

1. **CSS diff**（见 §2）：仅 1 个作用域选择器，3 个属性（width/max-width/justify-self）。
2. **作用域隔离证据**（见 §3）：仅首页 8 卡片，零外溢。
3. **修复后实测**（见 §3）：8 卡片 57px→258px，图片/标题/价格/按钮全部恢复正常。
4. **回滚方案**（见 §5）：删该段 CSS 即 100% 还原。

**请 Owner 确认后，我将通过 WordPress 定制器"额外 CSS"应用该定点修复，并在真实三端完成验证。**

---

## 8. 边界重申

- 全程只读检测 + 临时预览注入；**未写入 WordPress 定制器/数据库/生产 CSS**。
- **未**更新主题/插件（Owner 不批准 A）。
- **未**修改 WooCommerce 核心文件、Elementor 页面结构、商品价格/库存。
- 生产发布须等 Owner 二次确认。

**验收人**: Nuotao Dev Agent (Sensenova)
