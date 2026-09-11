# Nuotao Social Enhancements

WordPress 插件，为 Nuotao Outdoor 独立站提供社媒引流基础设施。

## 功能

### 1. 社媒链接管理
- 后台设置页配置各平台 URL（Facebook/Instagram/TikTok/Pinterest/YouTube/X）
- Shortcode `[nuotao_social_links]` 可在任意位置插入
- 页脚自动注入（可开关）
- 支持三种尺寸（small/medium/large）、三种对齐方式

### 2. 社媒分享按钮
- 商品详情页、博客文章页自动注入
- 支持平台：Facebook、X (Twitter)、Pinterest、LinkedIn、WhatsApp、Email、复制链接
- 浮动侧边栏 + 内容底部两种位置可选
- 纯前端实现，无外部依赖，不加载第三方脚本

### 3. 追踪代码注入
- Facebook Pixel（含 WooCommerce 事件：ViewContent/AddToCart/Purchase）
- TikTok Pixel（含 WooCommerce 事件）
- Google Analytics 4（含 WooCommerce 事件）
- 支持排除管理员追踪
- 符合 GDPR：anonymize_ip 启用

### 4. UTM 链接生成器
- 后台工具页生成带 UTM 参数的 URL
- 预设常见社媒平台和营销媒介
- 一键复制

## 安装

### 方法一：WordPress 后台上传（推荐）

1. 登录 WordPress 后台
2. 进入 Plugins → Add New → Upload Plugin
3. 选择 `nuotao-social-enhancements.zip`
4. 点击 Install Now，然后 Activate

### 方法二：FTP 上传

1. 解压 `nuotao-social-enhancements.zip`
2. 将 `nuotao-social-enhancements` 文件夹上传到 `/wp-content/plugins/` 目录
3. 登录 WordPress 后台，进入 Plugins，找到 "Nuotao Social Enhancements"，点击 Activate

## 配置

1. 登录 WordPress 后台
2. 进入 Settings → Nuotao Social
3. 配置各平台社媒链接 URL
4. 配置分享按钮显示位置和平台
5. 配置 Facebook Pixel ID、TikTok Pixel ID、GA4 Measurement ID（如已有）
6. 点击 Save Changes

## Shortcode 使用

基本用法：
```
[nuotao_social_links]
```

带参数：
```
[nuotao_social_links size="medium" align="left" show_labels="false"]
```

参数说明：
- `size`: small / medium / large（默认 medium）
- `align`: left / center / right（默认 left）
- `show_labels`: true / false（默认 false）

## 文件结构

```
nuotao-social-enhancements/
├── nuotao-social-enhancements.php    # 主插件文件
├── README.md                           # 说明文档
├── includes/
│   ├── class-settings.php              # 设置页
│   ├── class-social-links.php          # 社媒链接
│   ├── class-share-buttons.php         # 分享按钮
│   ├── class-tracking.php              # 追踪代码
│   └── class-utm-builder.php           # UTM 生成器
└── assets/
    ├── css/
    │   ├── frontend.css                # 前端样式
    │   └── admin.css                   # 后台样式
    └── js/
        ├── frontend.js                 # 前端脚本
        └── admin.js                    # 后台脚本
```

## 安全

- 所有用户输入经过 sanitize 和 escape
- 所有 URL 经过 esc_url / esc_url_raw
- 所有输出经过 esc_html / esc_attr / esc_js
- 追踪代码不包含硬编码密钥
- 支持排除管理员追踪

## 兼容性

- WordPress: 5.8+
- WooCommerce: 5.0+
- PHP: 7.4+
- 浏览器：所有现代浏览器

## 变更记录

### v1.0.0 (2026-09-08)
- 初始版本
- 社媒链接管理
- 分享按钮
- Facebook/TikTok Pixel + GA4 追踪
- UTM 链接生成器
