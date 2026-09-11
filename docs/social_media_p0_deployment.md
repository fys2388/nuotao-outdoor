# Nuotao Outdoor 社媒引流 P0 部署规划

> 版本: v1.0 | 日期: 2026-09-08 | 状态: 执行中
> 关联: `docs/development_roadmap.md` (M3 营销与内容系统)、`docs/p0_production_verification_checklist.md`

---

## 一、背景与目标

### 1.1 背景

- WooCommerce 独立站已上线（nuotaooutdoor.com），30 SKU 已上架
- 后端管理控制台已部署（admin.nuotaooutdoor.com）
- 社媒引流基础设施（页脚链接、分享按钮、Pixel、GA4）尚未部署
- 路线图 M3（营销与内容系统）计划 2026-12 启动，但基础引流层应提前部署

### 1.2 目标

P0 阶段部署社媒引流的**最小基础设施**，为后续营销活动提供数据追踪和流量入口：

1. ✅ 页脚社媒图标链接（FB/IG/TikTok/Pinterest/YouTube）
2. ✅ 商品页/博客页社媒分享按钮
3. ✅ Facebook Pixel + TikTok Pixel 基础追踪代码
4. ✅ GA4 社媒渠道分组与 UTM 规范文档

### 1.3 非目标（P1/P2 阶段）

- 社媒内容自动发布/调度（P1）
- 社媒广告自动投放（P2，环境变量已预留）
- 社媒私信接入客服（P2）
- 红人 outreach 自动化（P1，当前 Influencer 模块仅为 CRM 式记录）

---

## 二、当前环境探查结果

### 2.1 托管环境

| 项 | 值 |
|---|---|
| 托管平台 | Hostinger（hpanel） |
| Web 服务器 | LiteSpeed |
| WordPress 路径 | `/home/u289509695/domains/nuotaooutdoor.com/public_html/` |
| WordPress 版本 | 7.1 |
| WooCommerce 版本 | 11.1.0 |
| PHP 版本 | 8.3.30 |
| 数据库 | MariaDB 11.8.8 |
| CDN/代理 | Cloudflare |

### 2.2 主题与插件

| 项 | 值 |
|---|---|
| 当前主题 | Hello Elementor v3.5.1（非子主题） |
| 页面构建器 | Elementor |
| 已激活插件数 | 10 |
| 已知插件 | Elementor、WooCommerce 等 |

### 2.3 已有社媒相关能力（后端/管理层）

| 模块 | 状态 |
|---|---|
| Influencer 红人营销 | ✅ 已部署（后端+前端，支持 8 平台） |
| Marketing 广告活动数据采集 | ✅ 已部署（campaigns 表，支持 meta/google/tiktok/pinterest） |
| 内容生成（social_post） | ✅ 已部署（ContentGenerator + ActivityPlanner） |
| SEO 社媒链接（JSON-LD） | ✅ 已部署（seo_service.py） |
| Facebook Ads 环境变量 | ⚠️ 模板预留，值为空 |

---

## 三、部署方案

### 3.1 方案选型

采用**自定义轻量级插件**方案，而非安装多个第三方插件：

| 方案 | 优点 | 缺点 | 选择 |
|---|---|---|---|
| 多个第三方插件（AddToAny + PixelYourSite + 等） | 功能丰富 | 插件过多、性能影响、更新维护成本高 | ❌ |
| 自定义插件（nuotao-social-enhancements） | 轻量、可控、无依赖、统一管理 | 需要自行维护 | ✅ |
| 修改主题 functions.php | 简单 | 主题更新会覆盖、不可复用 | ❌ |

### 3.2 插件功能设计

**插件名称**: Nuotao Social Enhancements
**插件目录**: `nuotao-social-enhancements/`
**主文件**: `nuotao-social-enhancements.php`

#### 功能模块

1. **社媒链接管理**
   - WordPress 后台设置页（Settings → Nuotao Social）
   - 配置各平台 URL（Facebook/Instagram/TikTok/Pinterest/YouTube/X）
   - Shortcode `[nuotao_social_links]` 可在任意位置插入
   - 页脚自动注入（可开关）

2. **社媒分享按钮**
   - 商品详情页、博客文章页自动注入
   - 支持平台：Facebook、X (Twitter)、Pinterest、LinkedIn、WhatsApp、Email、复制链接
   - 浮动侧边栏 + 内容底部两种位置可选
   - 纯前端实现，无外部依赖，不加载第三方脚本

3. **追踪代码注入**
   - Facebook Pixel ID 配置
   - TikTok Pixel ID 配置
   - GA4 Measurement ID 配置
   - 通过 `wp_head` 注入，支持排除管理员
   - 符合 GDPR：默认加载，后续可集成 Cookie 同意

4. **UTM 参数生成器**
   - 后台工具页：输入来源/媒介/活动名称，生成带 UTM 的 URL
   - 短代码 `[nuotao_utm_builder]`（可选，P1）

### 3.3 社媒账号配置（默认值）

| 平台 | URL | 状态 |
|---|---|---|
| Facebook | https://facebook.com/nuotaooutdoor | 待注册/确认 |
| Instagram | https://instagram.com/nuotaooutdoor | 待注册/确认 |
| TikTok | https://tiktok.com/@nuotaooutdoor | 待注册/确认 |
| Pinterest | https://pinterest.com/nuotaooutdoor | 待注册/确认 |
| YouTube | https://youtube.com/@nuotaooutdoor | 待注册/确认 |
| X (Twitter) | https://x.com/nuotaooutdoor | 待注册/确认 |

> 注意：以上账号名为规划默认值，需用户确认是否已注册。插件设置页可随时修改。

### 3.4 Pixel/GA4 配置（待用户提供 ID）

| 工具 | ID 字段 | 状态 |
|---|---|---|
| Facebook Pixel | `FB_PIXEL_ID` | 待用户提供 |
| TikTok Pixel | `TIKTOK_PIXEL_ID` | 待用户提供 |
| GA4 | `GA4_MEASUREMENT_ID` | 待用户提供 |

> 插件安装后，如未配置 ID，则不注入对应代码，不影响网站运行。

---

## 四、实施步骤

### 阶段 1：插件开发（本地）

1. 创建插件目录结构和主文件
2. 实现设置页（Settings API）
3. 实现社媒链接 shortcode 和页脚注入
4. 实现分享按钮（纯 CSS/JS，无外部依赖）
5. 实现 Pixel/GA4 代码注入
6. 本地代码审查和安全检查

### 阶段 2：插件安装（生产）

1. 打包为 zip 文件
2. 通过 WordPress 后台上传安装（Plugins → Add New → Upload Plugin）
3. 激活插件
4. 配置社媒链接 URL
5. 配置 Pixel/GA4 ID（如已有）

### 阶段 3：页脚配置

1. 通过 Elementor 编辑器编辑页脚模板
2. 添加社媒图标链接模块（或使用 shortcode）
3. 配置导航菜单中的社媒链接（如主题支持）

### 阶段 4：GA4 配置

1. 在 GA4 后台配置社媒渠道分组
2. 配置 UTM 命名规范
3. 验证实时数据流入

### 阶段 5：验证

1. 前台验证：页脚链接可见、分享按钮可点击
2. 代码验证：Pixel/GA4 代码已注入
3. 功能验证：分享链接正确跳转
4. 性能验证：无明显页面加载延迟
5. 移动验证：响应式布局正常

---

## 五、验证标准

### 5.1 功能验证清单

| # | 检查项 | 验证方法 | 预期结果 |
|---|---|---|---|
| 1 | 页脚社媒链接 | 前台查看页脚 | FB/IG/TikTok/Pinterest/YT 图标可见，链接正确 |
| 2 | 商品页分享按钮 | 打开任意商品详情页 | 分享按钮可见，点击弹出对应平台分享窗口 |
| 3 | 博客页分享按钮 | 打开任意博客文章 | 分享按钮可见 |
| 4 | Facebook Pixel | 查看页面源码，搜索 `fbq` | Pixel 代码已注入（如已配置 ID） |
| 5 | TikTok Pixel | 查看页面源码，搜索 `tiktok` | Pixel 代码已注入（如已配置 ID） |
| 6 | GA4 | 查看页面源码，搜索 `gtag` | GA4 代码已注入（如已配置 ID） |
| 7 | 后台设置页 | WP Admin → Settings → Nuotao Social | 设置页可访问，字段可保存 |
| 8 | 响应式 | 移动设备查看 | 分享按钮和页脚链接在移动端正常显示 |
| 9 | 性能 | GTmetrix / PageSpeed | 无明显性能下降（< 200ms 额外加载） |
| 10 | 安全 | 检查代码 | 无 XSS、无硬编码密钥、所有输入有转义 |

### 5.2 回滚方案

如插件导致问题：
1. WP Admin → Plugins → Deactivate "Nuotao Social Enhancements"
2. 如无法访问后台，通过 FTP/Hostinger 文件管理器重命名插件目录
3. 网站立即恢复到插件安装前状态

---

## 六、后续迭代（P1/P2）

### P1（M3 阶段，2026-12）

- 社媒内容自动发布（先支持手动审批后发布到 FB/IG）
- UTM 参数管理和流量归因看板（复用 campaigns 表）
- 社媒互动数据采集（点赞、评论、分享数）
- Cookie 同意横幅（GDPR 合规）

### P2（后续）

- Meta Marketing API / TikTok Marketing API 自动投放
- 社媒私信接入客服（customer_interactions 已支持 social channel）
- 红人 outreach 自动化流程
- 社媒竞品监控

---

## 七、成本与资源

| 项 | 成本 | 说明 |
|---|---|---|
| 插件开发 | 0 | 自研，无第三方依赖 |
| 社媒账号注册 | 0 | 免费 |
| Facebook Pixel | 0 | 免费 |
| TikTok Pixel | 0 | 免费 |
| GA4 | 0 | 免费 |
| 后续广告投放 | 按需 | 有预算上限控制 |

---

## 八、风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| 第三方平台政策变化 | Pixel/分享功能失效 | 关注平台更新，及时调整代码 |
| GDPR/隐私合规 | 法律风险 | P1 阶段添加 Cookie 同意；当前仅做基础追踪 |
| 社媒账号未注册 | 链接无效 | 先部署链接结构，账号注册后更新 URL 即可 |
| 插件与主题/其他插件冲突 | 网站异常 | 采用标准 WordPress API，充分测试；有回滚方案 |
| Pixel ID 配置错误 | 数据丢失 | 提供配置验证功能（发送测试事件） |

---

## 九、变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-09-08 | 初始版本，P0 社媒引流基础设施部署规划 |

---

*文档结束*
