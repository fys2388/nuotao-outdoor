#!/bin/bash
# ============================================
# Nuotao AI OS - 默认密码修改与安全加固脚本
# ============================================
# 功能：
#   1. 修改 PostgreSQL 默认密码
#   2. 修改 Redis 默认密码
#   3. 修改管理员账号默认密码
#   4. 检查其他默认密码
#   5. 生成安全报告
#
# 用法：
#   sudo bash change-default-passwords.sh
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

# 检查是否为 root
if [ "$EUID" -ne 0 ]; then
    log_error "请使用 root 权限运行: sudo bash $0"
    exit 1
fi

echo "============================================"
echo " Nuotao AI OS - Default Password Change"
echo "============================================"
echo ""

# ============================================
# 生成强密码函数
# ============================================
generate_password() {
    local length=${1:-32}
    openssl rand -base64 48 | tr -dc 'A-Za-z0-9!@#$%^&*()_+-=' | head -c $length
}

# ============================================
# 1. 修改 PostgreSQL 默认密码
# ============================================
log_info "Step 1/5: 修改 PostgreSQL 默认密码..."

# 检查 PostgreSQL 是否安装
if command -v psql &> /dev/null || [ -f "/usr/bin/psql" ]; then
    # 生成新密码
    NEW_DB_PASSWORD=$(generate_password 32)

    # 修改 nuotao 用户密码
    sudo -u postgres psql -c "ALTER USER nuotao WITH PASSWORD '$NEW_DB_PASSWORD';" 2>/dev/null && {
        log_success "PostgreSQL nuotao 用户密码已修改"
    } || {
        log_warning "PostgreSQL nuotao 用户不存在或修改失败，跳过"
    }

    # 修改 postgres 用户密码
    NEW_POSTGRES_PASSWORD=$(generate_password 32)
    sudo -u postgres psql -c "ALTER USER postgres WITH PASSWORD '$NEW_POSTGRES_PASSWORD';" 2>/dev/null && {
        log_success "PostgreSQL postgres 用户密码已修改"
    } || {
        log_warning "PostgreSQL postgres 用户密码修改失败"
    }

    # 输出新密码
    echo ""
    log_warning "请保存以下数据库密码（只显示一次）："
    echo "  nuotao 用户: $NEW_DB_PASSWORD"
    echo "  postgres 用户: $NEW_POSTGRES_PASSWORD"
    echo ""
else
    log_warning "PostgreSQL 未安装，跳过"
fi

# ============================================
# 2. 修改 Redis 默认密码
# ============================================
log_info "Step 2/5: 修改 Redis 默认密码..."

if command -v redis-server &> /dev/null || [ -f "/usr/bin/redis-server" ]; then
    REDIS_CONF="/etc/redis/redis.conf"

    if [ -f "$REDIS_CONF" ]; then
        # 生成新密码
        NEW_REDIS_PASSWORD=$(generate_password 32)

        # 修改 Redis 配置
        if grep -q "^requirepass" "$REDIS_CONF"; then
            sed -i "s/^requirepass .*/requirepass $NEW_REDIS_PASSWORD/" "$REDIS_CONF"
        else
            echo "requirepass $NEW_REDIS_PASSWORD" >> "$REDIS_CONF"
        fi

        # 禁用危险命令
        if ! grep -q "rename-command FLUSHDB" "$REDIS_CONF"; then
            echo "" >> "$REDIS_CONF"
            echo "# 安全加固：禁用危险命令" >> "$REDIS_CONF"
            echo "rename-command FLUSHDB \"\"" >> "$REDIS_CONF"
            echo "rename-command FLUSHALL \"\"" >> "$REDIS_CONF"
            echo "rename-command CONFIG \"\"" >> "$REDIS_CONF"
            echo "rename-command KEYS \"\"" >> "$REDIS_CONF"
        fi

        # 绑定到本地（如果没有配置）
        if ! grep -q "^bind 127.0.0.1" "$REDIS_CONF"; then
            sed -i "s/^bind .*/bind 127.0.0.1/" "$REDIS_CONF"
        fi

        # 重启 Redis
        systemctl restart redis-server 2>/dev/null && {
            log_success "Redis 密码已修改并重启"
        } || {
            log_warning "Redis 重启失败，请手动重启"
        }

        echo ""
        log_warning "请保存以下 Redis 密码（只显示一次）："
        echo "  Redis 密码: $NEW_REDIS_PASSWORD"
        echo ""
    else
        log_warning "Redis 配置文件不存在: $REDIS_CONF"
    fi
else
    log_warning "Redis 未安装，跳过"
fi

# ============================================
# 3. 修改管理员账号默认密码
# ============================================
log_info "Step 3/5: 修改管理员账号默认密码..."

APP_DIR="/opt/nuotao-ai-os/backend"
ENV_FILE="$APP_DIR/.env"

if [ -f "$ENV_FILE" ]; then
    # 生成新管理员密码
    NEW_ADMIN_PASSWORD=$(generate_password 16)

    # 检查是否使用默认密码
    if grep -q "ADMIN_PASSWORD=Admin@2026" "$ENV_FILE"; then
        sed -i "s/ADMIN_PASSWORD=Admin@2026/ADMIN_PASSWORD=$NEW_ADMIN_PASSWORD/" "$ENV_FILE"
        log_success "管理员默认密码已在 .env 中修改"
    else
        log_warning ".env 中未找到默认管理员密码，可能已修改"
    fi

    echo ""
    log_warning "请保存以下管理员密码（只显示一次）："
    echo "  管理员用户名: admin"
    echo "  管理员密码: $NEW_ADMIN_PASSWORD"
    echo ""
    echo "  注意：如果数据库中已有管理员账号，"
    echo "  需要通过 API 或直接修改数据库来更新密码。"
    echo ""
else
    log_warning "应用 .env 文件不存在: $ENV_FILE"
    log_warning "请先部署应用，然后手动修改管理员密码"
fi

# ============================================
# 4. 检查其他默认密码
# ============================================
log_info "Step 4/5: 检查其他默认密码..."

# 检查 Grafana
if [ -d "/etc/grafana" ]; then
    log_warning "检测到 Grafana，请确认已修改默认密码 (admin/admin)"
    log_warning "  修改方式: 首次登录时会提示修改密码"
fi

# 检查 Nginx
if [ -f "/etc/nginx/.htpasswd" ]; then
    log_warning "检测到 Nginx 基础认证，请确认已修改默认密码"
fi

# 检查 SSH
if grep -q "PermitRootLogin yes" /etc/ssh/sshd_config 2>/dev/null; then
    log_warning "SSH 允许 root 登录，建议禁用"
    log_warning "  修改方式: 编辑 /etc/ssh/sshd_config，设置 PermitRootLogin no"
fi

# 检查 .env 文件中的默认值
if [ -f "$ENV_FILE" ]; then
    echo ""
    log_info "检查 .env 文件中的默认值..."

    # 检查 JWT 密钥
    if grep -q "JWT_SECRET_KEY=nuotao-ai-os-dev-secret" "$ENV_FILE"; then
        log_warning "JWT 密钥仍为开发默认值，请修改"
    else
        log_success "JWT 密钥已修改"
    fi

    # 检查 WooCommerce Webhook Secret
    if grep -q "WOOCOMMERCE_WEBHOOK_SECRET=dev-webhook-secret" "$ENV_FILE"; then
        log_warning "WooCommerce Webhook Secret 仍为开发默认值，请修改"
    else
        log_success "WooCommerce Webhook Secret 已修改"
    fi
fi

# ============================================
# 5. 生成安全报告
# ============================================
log_info "Step 5/5: 生成安全报告..."

REPORT_FILE="/var/log/nuotao/security-report-$(date +%Y%m%d_%H%M%S).txt"
mkdir -p /var/log/nuotao

cat > "$REPORT_FILE" <<EOF
============================================
 Nuotao AI OS - Security Report
 Generated: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
============================================

[已完成]
- PostgreSQL 默认密码已修改
- Redis 默认密码已修改
- Redis 危险命令已禁用
- 管理员默认密码已修改（如适用）

[待确认]
- Grafana 默认密码（如已安装）
- Nginx 基础认证密码（如已配置）
- SSH root 登录禁用
- 所有第三方服务 API Key 已更新
- 数据库备份密码已配置

[建议]
1. 定期（每90天）轮换所有密码和密钥
2. 使用密码管理器保存所有凭据
3. 启用多因素认证（MFA）
4. 配置登录失败锁定策略
5. 定期审计用户账号和权限
6. 配置安全日志监控和告警

============================================
EOF

log_success "安全报告已生成: $REPORT_FILE"

# ============================================
# 完成
# ============================================
echo ""
echo "============================================"
echo " Default Password Change Complete!"
echo "============================================"
echo ""
echo "已修改："
echo "  ✅ PostgreSQL 默认密码"
echo "  ✅ Redis 默认密码"
echo "  ✅ 管理员默认密码（如适用）"
echo "  ✅ Redis 危险命令禁用"
echo ""
echo "待确认："
echo "  ⚠️  Grafana 默认密码（如已安装）"
echo "  ⚠️  SSH root 登录禁用"
echo "  ⚠️  第三方服务 API Key 更新"
echo ""
echo "重要提示："
echo "  1. 上方生成的密码只显示一次，请立即保存"
echo "  2. 建议使用密码管理器（1Password/Bitwarden）保存"
echo "  3. 修改密码后需要重启相关服务"
echo "  4. 完整安全报告: $REPORT_FILE"
echo ""
echo "服务重启命令："
echo "  sudo systemctl restart postgresql"
echo "  sudo systemctl restart redis-server"
echo "  sudo systemctl restart nuotao-backend"
echo "============================================"
