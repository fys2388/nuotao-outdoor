# WordPress MU-Plugin 部署指南

## 概述

本文档说明如何部署 `register-seo-meta.php` mu-plugin 到 WordPress 服务器，启用 Rank Math SEO meta 字段的 REST API 访问。

---

## 前置条件

1. **服务器访问权限**: SSH 或 FTP 访问权限
2. **WordPress 服务器**: nuotaooutdoor.com
3. **WordPress 版本**: 5.0+
4. **Rank Math 插件**: 已安装并激活

---

## 部署步骤

### 方法1: SSH 部署（推荐）

```bash
# 1. SSH 连接到服务器
ssh user@nuotaooutdoor.com

# 2. 创建 mu-plugins 目录（如果不存在）
mkdir -p /var/www/html/wp-content/mu-plugins

# 3. 上传插件文件
# 使用 scp 从本地上传
scp deployment/wordpress-mu-plugin-register-seo-meta.php user@nuotaooutdoor.com:/var/www/html/wp-content/mu-plugins/register-seo-meta.php

# 4. 设置文件权限
chmod 644 /var/www/html/wp-content/mu-plugins/register-seo-meta.php
chown www-data:www-data /var/www/html/wp-content/mu-plugins/register-seo-meta.php

# 5. 验证文件
ls -la /var/www/html/wp-content/mu-plugins/register-seo-meta.php
```

### 方法2: FTP 部署

```bash
# 1. 使用 FTP 客户端连接
# 2. 导航到 wp-content/mu-plugins/ 目录
# 3. 上传 register-seo-meta.php 文件
# 4. 确保文件权限为 644
```

### 方法3: 使用 WordPress 插件（如果无法 SSH）

1. 登录 WordPress 后台: https://nuotaooutdoor.com/wp-admin/
2. 安装插件: "WP File Manager" 或 "WP-File-Media"
3. 使用文件管理器创建 mu-plugins 目录并上传文件

---

## 验证部署

### 1. 检查插件是否加载

访问 WordPress 后台，检查是否有错误信息。

### 2. 测试 REST API

```bash
# 获取 SEO 数据
curl -X GET https://nuotaooutdoor.com/wp-json/nuotao/v1/seo/2372 \
  -u "fys2388@gmail.com:Nh7c PVfF G029 gORK 39BE ozBr"

# 预期响应:
# {
#   "id": 2372,
#   "type": "product",
#   "title": "Portable Folding Moon Chair...",
#   "seo_title": "Portable Folding Moon Chair for Camping & Patio - Nuotao Outdoor",
#   "meta_description": "Experience ultimate comfort...",
#   "focus_keyword": "portable folding moon chair",
#   "noindex": false,
#   "link": "https://nuotaooutdoor.com/product/..."
# }
```

```bash
# 更新 SEO 数据
curl -X POST https://nuotaooutdoor.com/wp-json/nuotao/v1/seo/2372 \
  -u "fys2388@gmail.com:Nh7c PVfF G029 gORK 39BE ozBr" \
  -H "Content-Type: application/json" \
  -d '{
    "seo_title": "Portable Folding Moon Chair for Camping & Patio - Nuotao Outdoor",
    "meta_description": "Experience ultimate comfort with our portable folding moon chair.",
    "focus_keyword": "portable folding moon chair",
    "noindex": false,
    "excerpt": "Experience ultimate comfort with our portable folding moon chair."
  }'
```

### 3. 检查 error_log

```bash
# 查看 WordPress 错误日志
tail -100 /var/www/html/wp-content/debug.log
# 或
tail -100 /var/www/html/wp-content/mu-plugins/../wp-content/debug.log

# 应该看到:
# [date] PHP Warning: Nuotao SEO Meta: Registered 12 meta fields for 3 post types
```

---

## 配置 WordPress 调试

编辑 `/var/www/html/wp-config.php`，添加调试配置：

```php
define('WP_DEBUG', true);
define('WP_DEBUG_LOG', true);
define('WP_DEBUG_DISPLAY', false);
define('SCRIPT_DEBUG', true);
```

---

## 回滚步骤

如果部署后出现问题：

```bash
# 1. 删除 mu-plugin 文件
rm /var/www/html/wp-content/mu-plugins/register-seo-meta.php

# 2. 清除缓存（如果使用了 LiteSpeed Cache）
# 登录 WordPress 后台 → LiteSpeed Cache → Tools → Clear All
```

---

## 常见问题

### Q: 部署后没有效果？
- 确保文件位于 `wp-content/mu-plugins/` 目录
- 确保文件权限正确 (644)
- 检查 WordPress 版本是否支持 register_post_meta (5.0+)
- 查看 error_log 是否有错误

### Q: REST API 返回 403？
- 确保使用了正确的 Application Password
- 确保当前用户有 `edit_posts` 权限

### Q: 为什么使用 mu-plugin 而不是普通插件？
- mu-plugin 无需手动激活，放在目录即生效
- 无法被禁用，确保 SEO 功能始终可用
- 更适合服务器级别的配置

---

## 部署后更新

部署 mu-plugin 后，需要更新 Nuotao AI OS 的 SEO 端点，使用新的 API：

```python
# 更新 seo.py 中的 update_wordpress_seo 函数
# 使用新的 /wp-json/nuotao/v1/seo/{post_id} 端点
```

---

## 相关文件

- `deployment/wordpress-mu-plugin-register-seo-meta.php` - mu-plugin 源码
- `backend/app/api/v1/endpoints/seo.py` - Nuotao AI OS SEO 端点
- `docs/fix_system_issues_20261011.md` - 系统修复文档
