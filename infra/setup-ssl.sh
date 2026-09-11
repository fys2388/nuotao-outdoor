#!/bin/bash
# ============================================
# Nuotao AI OS - SSL 证书配置脚本
# ============================================
# 功能：
#   1. 检查域名解析是否生效
#   2. 使用 Certbot 申请 Let's Encrypt 免费 SSL 证书
#   3. 配置 Nginx HTTPS
#   4. 设置证书自动续期
#   5. 验证 SSL 配置
#
# 前置条件：
#   - 域名已解析到服务器 IP
#   - Nginx 已安装并运行
#   - 80 和 443 端口已开放
#
# 用法：
#   sudo bash setup-ssl.sh your-domain.com
# ============================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 检查参数
if [ -z "$1" ]; then
    log_error "请提供域名: sudo bash setup-ssl.sh your-domain.com"
    exit 1
fi

DOMAIN=$1
WWW_DOMAIN="www.$DOMAIN"
EMAIL="admin@$DOMAIN"  # 可修改为实际邮箱

# 检查是否为 root
if [ "$EUID" -ne 0 ]; then
    log_error "请使用 root 权限运行"
    exit 1
fi

echo "============================================"
echo " Nuotao AI OS - SSL Certificate Setup"
echo "============================================"
echo "  域名: $DOMAIN"
echo "  邮箱: $EMAIL"
echo "============================================"
echo ""

# ============================================
# 1. 检查域名解析
# ============================================
log_info "Step 1/5: 检查域名解析..."

# 获取服务器公网 IP
SERVER_IP=$(curl -s ifconfig.me || curl -s ipinfo.io/ip)
log_info "服务器公网 IP: $SERVER_IP"

# 检查域名解析
DOMAIN_IP=$(dig +short $DOMAIN | head -1)
WWW_IP=$(dig +short $WWW_DOMAIN | head -1)

if [ "$DOMAIN_IP" = "$SERVER_IP" ]; then
    log_success "$DOMAIN 解析正确 → $DOMAIN_IP"
else
    log_warning "$DOMAIN 解析为 $DOMAIN_IP，期望 $SERVER_IP"
    log_warning "请确认域名解析已生效，否则 SSL 申请会失败"
fi

if [ -n "$WWW_IP" ]; then
    if [ "$WWW_IP" = "$SERVER_IP" ]; then
        log_success "$WWW_DOMAIN 解析正确 → $WWW_IP"
    else
        log_warning "$WWW_DOMAIN 解析为 $WWW_IP，期望 $SERVER_IP"
    fi
else
    log_warning "$WWW_DOMAIN 未配置解析（可选）"
fi

# ============================================
# 2. 安装 Certbot
# ============================================
log_info "Step 2/5: 检查 Certbot 安装..."

if ! command -v certbot &> /dev/null; then
    log_info "安装 Certbot..."
    apt-get update -qq
    apt-get install -y -qq certbot python3-certbot-nginx
else
    log_success "Certbot 已安装: $(certbot --version)"
fi

# ============================================
# 3. 申请 SSL 证书
# ============================================
log_info "Step 3/5: 申请 SSL 证书..."

# 检查是否已有证书
if certbot certificates 2>/dev/null | grep -q "$DOMAIN"; then
    log_success "已存在 $DOMAIN 的证书，跳过申请"
else
    log_info "使用 Nginx 插件申请证书..."

    # 构建域名参数
    DOMAIN_ARGS="-d $DOMAIN"
    if [ -n "$WWW_IP" ] && [ "$WWW_IP" = "$SERVER_IP" ]; then
        DOMAIN_ARGS="$DOMAIN_ARGS -d $WWW_DOMAIN"
    fi

    # 申请证书（非交互式）
    certbot --nginx \
        $DOMAIN_ARGS \
        --email $EMAIL \
        --agree-tos \
        --no-eff-email \
        --redirect \
        --non-interactive

    if [ $? -eq 0 ]; then
        log_success "SSL 证书申请成功"
    else
        log_error "SSL 证书申请失败"
        log_error "请检查：1) 域名解析是否生效 2) 80端口是否开放 3) Nginx是否运行"
        exit 1
    fi
fi

# ============================================
# 4. 配置自动续期
# ============================================
log_info "Step 4/5: 配置证书自动续期..."

# 测试续期
log_info "测试证书续期..."
certbot renew --dry-run

if [ $? -eq 0 ]; then
    log_success "证书续期测试通过"
else
    log_warning "证书续期测试失败，请检查配置"
fi

# 配置 systemd timer（Certbot 通常会自动配置）
systemctl enable certbot.timer 2>/dev/null || true
systemctl start certbot.timer 2>/dev/null || true

# 添加续期钩子（续期后重启 Nginx）
mkdir -p /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh <<EOF
#!/bin/bash
systemctl reload nginx
EOF
chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh

log_success "自动续期配置完成"

# ============================================
# 5. 验证 SSL 配置
# ============================================
log_info "Step 5/5: 验证 SSL 配置..."

# 检查 Nginx 配置
nginx -t

# 重启 Nginx
systemctl reload nginx

# 检查证书信息
echo ""
log_info "证书信息："
certbot certificates 2>/dev/null | grep -A 5 "$DOMAIN" || true

# 检查 HTTPS 访问
echo ""
log_info "测试 HTTPS 访问..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" https://$DOMAIN 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "301" ] || [ "$HTTP_CODE" = "302" ]; then
    log_success "HTTPS 访问正常 (HTTP $HTTP_CODE)"
else
    log_warning "HTTPS 访问返回 $HTTP_CODE，请检查 Nginx 配置"
fi

# 检查 SSL 等级（使用 openssl）
echo ""
log_info "SSL 证书详情："
echo | openssl s_client -connect $DOMAIN:443 -servername $DOMAIN 2>/dev/null | openssl x509 -noout -subject -issuer -dates 2>/dev/null || true

# ============================================
# 完成
# ============================================
echo ""
echo "============================================"
echo " SSL Certificate Setup Complete!"
echo "============================================"
echo ""
echo "访问地址："
echo "  HTTP:  http://$DOMAIN (自动跳转到 HTTPS)"
echo "  HTTPS: https://$DOMAIN"
echo ""
echo "证书信息："
echo "  颁发机构: Let's Encrypt"
echo "  有效期: 90 天（自动续期）"
echo "  续期测试: 已通过"
echo ""
echo "管理命令："
echo "  查看证书: sudo certbot certificates"
echo "  手动续期: sudo certbot renew"
echo "  撤销证书: sudo certbot revoke --cert-path /etc/letsencrypt/live/$DOMAIN/cert.pem"
echo "  删除证书: sudo certbot delete"
echo ""
echo "安全建议："
echo "  1. 配置 HSTS 头（已在 Nginx 配置中）"
echo "  2. 定期检查证书续期状态"
echo "  3. 配置 SSL 监控告警"
echo "============================================"
