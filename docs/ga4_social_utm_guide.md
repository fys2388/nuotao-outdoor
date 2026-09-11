# GA4 社媒渠道配置与 UTM 命名规范

> 版本: v1.1 | 日期: 2026-09-08
> 关联: `docs/social_media_p0_deployment.md`

---

## 〇、配置状态（已完成）

| 项目 | 值 | 状态 |
|---|---|---|
| GA4 属性 | nuotaooutdoor.com | ✅ 已存在 |
| Property ID | 536153168 | ✅ |
| Measurement ID | **G-30GWC4FYMG** | ✅ 已填入 WordPress 插件 |
| 数据流 ID | 14811702943 | ✅ |
| 代码注入 | 已验证（原始 HTML 包含 gtag/Measurement ID） | ✅ |
| 自定义渠道组 | Nuotao Social Channels | ✅ 已创建 |
| 增强型衡量 | 已启用（网页浏览量/滚动/出站点击等） | ✅ |
| 管理员排除 | 已启用（管理员访问不追踪） | ✅ |

**插件设置入口**: WP Admin → Settings → Nuotao Social → GA4 Measurement ID

---

## 一、GA4 社媒渠道分组配置

### 1.1 默认渠道分组（Default Channel Grouping）

GA4 默认的渠道分组可能无法准确识别社媒流量。需要自定义渠道分组规则。

#### 自定义渠道分组规则

| 渠道名称 | 匹配条件 | 说明 |
|---|---|---|
| **Organic Social** | `Session source` matches regex `facebook|instagram|tiktok|pinterest|youtube|twitter|x\.com|linkedin|reddit|snapchat` **AND** `Session medium` matches regex `social|organic|referral|^(\\s*)$` | 自然社媒流量 |
| **Paid Social** | `Session source` matches regex `facebook|instagram|tiktok|pinterest|youtube|twitter|x\.com|linkedin` **AND** `Session medium` matches regex `cpc|ppc|paid|ads|social_ads` | 付费社媒广告 |
| **Email** | `Session medium` matches regex `email|e-mail|e_mail|e mail` **OR** `Session source` matches regex `email|mailchimp|klaviyo|sendgrid` | 邮件营销 |
| **Organic Search** | `Session medium` matches regex `organic|search` **OR** `Session source` matches regex `google|bing|yahoo|baidu|duckduckgo` **AND** `Session medium` matches regex `^(\\s*)$` | 自然搜索 |
| **Paid Search** | `Session medium` matches regex `cpc|ppc|paidsearch` **AND** `Session source` matches regex `google|bing|yahoo` | 付费搜索 |
| **Direct** | `Session source` matches regex `direct|^(\\s*)$` **AND** `Session medium` matches regex `direct|none|^(\\s*)$` | 直接访问 |
| **Referral** | 其他所有未匹配的流量 | 引荐流量 |

### 1.2 配置步骤

1. 登录 [Google Analytics 4](https://analytics.google.com/)
2. 进入 **Admin** → **Property** → **Data Settings** → **Channel Groups**
3. 点击 **Create new channel group**（或编辑默认的 "Custom Channel Group"）
4. 按照上表逐条添加规则
5. 点击 **Save**

### 1.3 社媒平台 Source 命名规范

| 平台 | utm_source 值 | 备注 |
|---|---|---|
| Facebook | `facebook` | 统一小写 |
| Instagram | `instagram` | |
| TikTok | `tiktok` | |
| Pinterest | `pinterest` | |
| YouTube | `youtube` | |
| X (Twitter) | `twitter` 或 `x` | 建议用 `twitter` 保持兼容 |
| LinkedIn | `linkedin` | |
| Reddit | `reddit` | |
| 邮件营销 | `email` 或具体服务商（mailchimp/klaviyo） | |

---

## 二、GA4 关键转化事件配置

### 2.1 需标记的关键事件

| 事件名称 | 类型 | 说明 | 标记状态 |
|---|---|---|---|
| `purchase` | 电商标准事件 | 购买完成（含订单号、金额、商品明细） | ⏳ 待触发后标记 |
| `add_to_cart` | 电商标准事件 | 加入购物车（含商品 ID、名称、价格、数量） | ⏳ 待触发后标记 |
| `begin_checkout` | 电商标准事件 | 开始结账 | ⏳ 待触发后标记 |
| `view_item` | 电商标准事件 | 查看商品详情 | ⏳ 待触发后标记 |

### 2.2 插件已集成的事件

Nuotao Social Enhancements 插件已通过 WooCommerce 钩子自动触发以下事件：

| 事件 | 触发时机 | 包含参数 |
|---|---|---|
| `view_item` | 商品详情页加载 | items（id/name/price/quantity）、value、currency |
| `add_to_cart` | 点击加入购物车 | items、value、currency |
| `purchase` | 订单完成页（Thank You） | transaction_id、value、currency、items、tax、shipping |

> Facebook Pixel 和 TikTok Pixel 也同步触发对应的 `ViewContent`/`AddToCart`/`Purchase` 事件。

### 2.3 标记关键事件的操作步骤

> **前提**：事件必须至少被触发一次，才会出现在 GA4 事件列表中，才能标记为关键事件。

1. 登录 [Google Analytics 4](https://analytics.google.com/)
2. 进入 **Admin** → **Property** → **Data display** → **Events**（管理 → 媒体资源 → 数据显示 → 事件）
3. 在事件列表中找到目标事件（如 `purchase`、`add_to_cart`）
4. 点击事件名称左侧的**星号图标**，将其标记为关键事件
5. 星号变为黄色即表示标记成功

### 2.4 验证事件触发的方法

1. **实时报告**：GA4 → Reports → Realtime（报告 → 实时），执行加购/购买操作后 1-2 分钟内可看到事件
2. **DebugView**：GA4 → Admin → DebugView，安装 Google Analytics Debugger 浏览器扩展后可实时查看事件详情
3. **Tag Assistant**：使用 Google Tag Assistant 浏览器扩展检查页面中的 gtag 事件

### 2.5 当前状态说明

- 网站为新上线状态，暂无实际电商交易数据
- `purchase` 事件已出现在 GA4 关键事件列表中（GA4 默认推荐），但因尚未被触发，星号按钮暂为禁用状态
- 一旦有真实用户执行加购/购买操作，事件会自动触发并出现在列表中，届时可一键标记为关键事件
- GA4 代码已通过原始 HTML 验证成功注入（包含 `googletagmanager` 脚本、`gtag` 函数、`G-30GWC4FYMG` 配置）
- Measurement ID: **G-30GWC4FYMG**，已填入插件设置并保存

### 2.6 已知问题与修复建议（TODO）

> **问题**：`add_to_cart` 事件在 WooCommerce AJAX 加购时不触发

**现象**：
- WooCommerce 默认使用 AJAX 异步加购（点击 "Add to cart" 后页面不刷新）
- 插件当前通过 `woocommerce_add_to_cart` 钩子将数据存入 `$_SESSION`，再通过 `wp_footer` 输出 JS
- AJAX 加购不触发页面刷新，`wp_footer` 不执行，导致 `add_to_cart` 事件 JS 不输出

**影响**：
- `view_item` 事件正常（商品详情页加载时触发）
- `purchase` 事件正常（订单完成页刷新时触发）
- `add_to_cart` 事件在 AJAX 加购时丢失

**修复方案**（优先级：高）：
在前端 JS 中监听 WooCommerce 的 `added_to_cart` jQuery 事件，触发时调用 `gtag('event', 'add_to_cart', ...)`：

```javascript
// 监听 WooCommerce AJAX 加购成功事件
$(document).on('added_to_cart', function(event, fragments, cart_hash, button) {
    var productData = button.data('product_id') ? {
        items: [{
            id: button.data('product_sku') || button.data('product_id'),
            name: button.closest('.product').find('.product_title').text(),
            price: button.data('price') || '',
            quantity: button.closest('form').find('input[name="quantity"]').val() || 1
        }],
        value: 0, // 需从按钮或表单获取价格
        currency: 'USD'
    } : {};
    if (typeof gtag === 'function' && productData.items) {
        gtag('event', 'add_to_cart', productData);
    }
});
```

**替代方案**：在 WooCommerce 设置中禁用 AJAX 加购（WooCommerce → Settings → Products → 取消 "Enable AJAX add to cart buttons on archives"），但这会影响用户体验。

**验证方法**：修复后在商品页点击 "Add to cart"，通过浏览器控制台检查 `dataLayer` 中是否有 `add_to_cart` 事件，或在 GA4 实时报告中查看。

---

## 三、UTM 命名规范

### 2.1 UTM 参数说明

| 参数 | 必需 | 说明 | 示例 |
|---|---|---|---|
| `utm_source` | ✅ | 流量来源（平台名） | `facebook`, `instagram`, `tiktok`, `email` |
| `utm_medium` | ✅ | 营销媒介 | `social`, `cpc`, `email`, `referral` |
| `utm_campaign` | ✅ | 活动名称 | `summer_sale_2026`, `product_launch_headlamp`, `black_friday_2026` |
| `utm_term` | ❌ | 关键词（付费搜索用） | `camping_headlamp`, `outdoor_gear` |
| `utm_content` | ❌ | 内容区分（A/B测试用） | `banner_v1`, `video_ad`, `text_link` |

### 2.2 命名规则

#### 通用规则
1. **全小写**：所有值使用小写字母
2. **下划线分隔**：使用 `_` 分隔单词，不使用空格、连字符或驼峰
3. **简洁明了**：每个值不超过 30 个字符
4. **一致性**：同一活动在不同平台使用相同的 `utm_campaign`
5. **日期格式**：包含日期时使用 `YYYYMMDD` 或 `YYYY_QX` 格式

#### utm_source 规则
- 使用平台名称的小写形式
- 邮件营销使用 `email` 或具体服务商名（`mailchimp`, `klaviyo`）
- 联盟营销使用 `affiliate` 或具体联盟名

#### utm_medium 规则
| 媒介类型 | 值 | 说明 |
|---|---|---|
| 自然社媒 | `social` | 帖子、故事、简介链接 |
| 付费社媒广告 | `cpc` 或 `paid_social` | Facebook Ads、TikTok Ads 等 |
| 邮件营销 | `email` | 所有邮件渠道 |
| 付费搜索 | `cpc` | Google Ads、Bing Ads |
| 自然搜索 | `organic` | |
| 展示广告 | `display` | 横幅广告、展示广告 |
| 联盟营销 | `affiliate` | |
| 引荐 | `referral` | 其他网站引荐 |

#### utm_campaign 规则
- 格式：`{活动类型}_{产品/主题}_{时间}`
- 活动类型：`sale`（促销）、`launch`（新品发布）、`awareness`（品牌认知）、`retargeting`（再营销）、`holiday`（节日）
- 示例：
  - `sale_summer_2026`
  - `launch_headlamp_sep2026`
  - `holiday_blackfriday_2026`
  - `retargeting_cart_abandon_q3`
  - `awareness_brand_q4_2026`

#### utm_content 规则
- 用于区分同一活动中的不同创意/素材
- 格式：`{格式}_{版本}`
- 示例：`banner_v1`, `video_30s`, `carousel_2`, `story_v1`, `reel_v2`

### 2.3 常见场景 UTM 示例

#### 场景 1：Facebook 有机帖子推广新品
```
https://nuotaooutdoor.com/product/led-headlamp?utm_source=facebook&utm_medium=social&utm_campaign=launch_headlamp_sep2026&utm_content=post_v1
```

#### 场景 2：Instagram Reels 推广促销活动
```
https://nuotaooutdoor.com/shop?utm_source=instagram&utm_medium=social&utm_campaign=sale_summer_2026&utm_content=reel_v2
```

#### 场景 3：TikTok 付费广告
```
https://nuotaooutdoor.com/product/camping-chair?utm_source=tiktok&utm_medium=cpc&utm_campaign=awareness_camping_gear_q3&utm_content=video_ad_v1
```

#### 场景 4：邮件营销 - 弃购挽回
```
https://nuotaooutdoor.com/cart?utm_source=mailchimp&utm_medium=email&utm_campaign=retargeting_cart_abandon_q3&utm_content=email_v2
```

#### 场景 5：Pinterest 有机 Pin
```
https://nuotaooutdoor.com/product/camping-tent?utm_source=pinterest&utm_medium=social&utm_campaign=awareness_outdoor_gear_q3&utm_content=pin_v1
```

#### 场景 6：YouTube 视频描述链接
```
https://nuotaooutdoor.com/shop?utm_source=youtube&utm_medium=social&utm_campaign=awareness_brand_q4_2026&utm_content=video_desc
```

---

## 三、GA4 事件追踪配置

### 3.1 插件自动追踪的事件

Nuotao Social Enhancements 插件自动追踪以下 WooCommerce 事件：

| 事件 | Facebook Pixel | TikTok Pixel | GA4 | 触发时机 |
|---|---|---|---|---|
| PageView | ✅ | ✅ (ttq.page) | ✅ | 所有页面 |
| ViewContent | ✅ | ✅ | ✅ (view_item) | 商品详情页 |
| AddToCart | ✅ | ✅ | ✅ (add_to_cart) | 加入购物车 |
| Purchase | ✅ | ✅ (CompletePayment) | ✅ (purchase) | 订单完成页 |

### 3.2 推荐配置的自定义事件

在 GA4 中配置以下自定义事件（通过 Google Tag Manager 或自定义代码）：

| 事件名 | 触发时机 | 参数 |
|---|---|---|
| `share_click` | 用户点击分享按钮 | `share_method`, `page_url`, `product_id` |
| `social_link_click` | 用户点击页脚社媒链接 | `social_platform`, `page_url` |
| `utm_link_generated` | 后台生成 UTM 链接 | `utm_source`, `utm_medium`, `utm_campaign` |

### 3.3 转化事件配置

在 GA4 中将以下事件标记为转化（Conversions）：

1. `purchase` - 购买（默认）
2. `add_to_cart` - 加入购物车
3. `begin_checkout` - 开始结账
4. `sign_up` - 注册（如有）

配置路径：**Admin** → **Property** → **Conversions** → **New conversion event**

---

## 四、受众群体（Audiences）配置

### 4.1 推荐创建的受众

| 受众名称 | 条件 | 用途 |
|---|---|---|
| **All Visitors** | 所有访问者 | 基础受众 |
| **Product Viewers** | `view_item` 事件 | 商品浏览者再营销 |
| **Add to Cart Non-Buyers** | `add_to_cart` 且未 `purchase` | 弃购挽回 |
| **Buyers** | `purchase` 事件 | 已有客户，相似受众 |
| **Social Traffic** | `Session medium` = `social` 或 `cpc` 且来源为社媒平台 | 社媒流量分析 |
| **High Value Customers** | `purchase` 且收入 > $100 | 高价值客户 |

### 4.2 配置步骤

1. GA4 → **Admin** → **Property** → **Audiences**
2. 点击 **New audience** → **Create a custom audience**
3. 按照上表配置条件
4. 选择受众有效期（建议 30-90 天）
5. 点击 **Save**

---

## 五、数据验证清单

### 5.1 上线前验证

- [ ] GA4 实时报告中能看到自己的访问
- [ ] Facebook Pixel 测试工具（Events Manager）能看到 PageView 事件
- [ ] TikTok Pixel 测试工具能看到 PageView 事件
- [ ] 商品详情页能触发 ViewContent 事件
- [ ] 加入购物车能触发 AddToCart 事件
- [ ] 测试订单能触发 Purchase 事件（金额正确）
- [ ] UTM 链接访问后，流量来源显示正确（GA4 实时报告 → Traffic source）
- [ ] 社媒渠道分组规则生效（GA4 → Acquisition → Traffic acquisition）

### 5.2 每周检查

- [ ] 社媒流量占比趋势
- [ ] 各社媒平台转化率对比
- [ ] UTM 链接使用规范性（是否有未命名的活动）
- [ ] Pixel 事件触发率（是否有丢失）

---

## 六、工具推荐

| 工具 | 用途 | 链接 |
|---|---|---|
| GA4 DebugView | 实时调试事件 | GA4 → Admin → DebugView |
| Facebook Pixel Helper | Chrome 扩展，检查 Pixel | Chrome Web Store |
| TikTok Pixel Helper | Chrome 扩展，检查 TikTok Pixel | Chrome Web Store |
| Google Tag Assistant | 检查各种跟踪代码 | Chrome Web Store |
| Campaign URL Builder | Google 官方 UTM 生成器 | https://ga-dev-tools.google.com/campaign-url-builder/ |

---

## 七、变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-09-08 | 初始版本，GA4 社媒渠道配置与 UTM 命名规范 |

---

*文档结束*
