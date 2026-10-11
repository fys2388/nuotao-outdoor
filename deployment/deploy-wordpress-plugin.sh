#!/bin/bash
# ============================================================
# Nuotao AI OS - WordPress 插件一键部署脚本
# ============================================================
# 功能: 上传并安装 SEO Meta REST 注册插件
# 使用: bash deploy-wordpress-plugin.sh
# ============================================================

set -e

echo "=========================================="
echo "Nuotao AI OS - WordPress 插件部署"
echo "=========================================="
echo ""

# 配置变量
WP_USERNAME="fys2388@gmail.com"
WP_APP_PASSWORD="Nh7c PVfF G029 gORK 39BE ozBr"
WP_SITE_URL="https://nuotaooutdoor.com"
PLUGIN_FILE="wp-plugin-register-seo-meta.zip"
UPLOAD_URL="${WP_SITE_URL}/wp-content/uploads/2026/10/wp-plugin-register-seo-meta.zip"

# 创建认证头
COLON=$(printf "\\:")
AUTH_STRING="${WP_USERNAME}${COLON}${WP_APP_PASSWORD}"
BASE64_AUTH=$(echo -n "$AUTH_STRING" | base64)

echo "步骤 1/4: 检查 WordPress REST API..."
# 测试 REST API 连接
curl -s -H "Authorization: Basic $BASE64_AUTH" "${WP_SITE_URL}/wp-json/" | python3 -c "import sys,json; data=json.load(sys.stdin); print('✅ REST API 连接成功')" || echo "❌ REST API 连接失败"

echo ""
echo "步骤 2/4: 检查插件文件..."
if [ -f "$PLUGIN_FILE" ]; then
    echo "✅ 插件文件存在: $PLUGIN_FILE"
else
    echo "❌ 插件文件不存在: $PLUGIN_FILE"
    echo "请先创建插件文件..."
    exit 1
fi

echo ""
echo "步骤 3/4: 上传插件到 WordPress..."
# 上传文件到 Media Library
UPLOAD_RESPONSE=$(curl -s -X POST "${WP_SITE_URL}/wp-json/wp/v2/media" \
    -H "Authorization: Basic $BASE64_AUTH" \
    -F "file=@${PLUGIN_FILE}" \
    -F "title=WP Plugin Register SEO Meta")

echo "上传响应: $UPLOAD_RESPONSE"

# 检查上传是否成功
if echo "$UPLOAD_RESPONSE" | python3 -c "import sys,json; data=json.load(sys.stdin); print(data['id'])" 2>/dev/null; then
    echo "✅ 文件上传成功"
    MEDIA_ID=$(echo "$UPLOAD_RESPONSE" | python3 -c "import sys,json; data=json.load(sys.stdin); print(data['id'])")
    echo "Media ID: $MEDIA_ID"
else
    echo "❌ 文件上传失败"
    exit 1
fi

echo ""
echo "步骤 4/4: 安装并激活插件..."
echo ""
echo "=========================================="
echo "⚠️  需要手动完成以下步骤:"
echo "=========================================="
echo ""
echo "由于 WordPress REST API 不支持直接安装插件，"
echo "请按照以下步骤手动安装:"
echo ""
echo "方法 1: 通过 WordPress 后台安装"
echo "1. 登录: https://nuotaooutdoor.com/wp-admin/"
echo "2. 导航到: Plugins → Add New"
echo "3. 点击: Upload Plugin"
echo "4. 上传文件: $PLUGIN_FILE"
echo "5. 点击: Install Now"
echo "6. 点击: Activate Plugin"
echo ""
echo "方法 2: 使用 FTP/SSH 安装"
echo "1. 上传插件文件到服务器:"
echo "   scp $PLUGIN_FILE user@nuotaooutdoor.com:/tmp/"
echo ""
echo "2. SSH 到服务器:"
echo "   ssh user@nuotaooutdoor.com"
echo ""
echo "3. 解压插件:"
echo "   cd /var/www/html/wp-content/plugins"
echo "   unzip /tmp/$PLUGIN_FILE"
echo ""
echo "4. 激活插件:"
echo "   wp plugin activate wp-plugin-register-seo-meta"
echo ""
echo "=========================================="
echo "插件安装完成后，运行以下命令验证:"
echo ""
echo "# 测试获取 SEO 数据"
echo "curl -X GET ${WP_SITE_URL}/wp-json/nuotao/v1/seo/2372 \\"
echo "  -u \"${WP_USERNAME}:${WP_APP_PASSWORD}\""
echo ""
echo "# 测试更新 SEO 数据"
echo "curl -X POST ${WP_SITE_URL}/wp-json/nuotao/v1/seo/2372 \\"
echo "  -u \"${WP_USERNAME}:${WP_APP_PASSWORD}\" \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -d '{\"seo_title\": \"Test Title\", \"meta_description\": \"Test Description\"}'"
echo ""
echo "=========================================="
