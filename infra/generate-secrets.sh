#!/bin/bash
# ============================================
# Nuotao AI OS - 生产环境密钥生成脚本
# ============================================
# 功能：
#   1. 生成所有必需的强随机密钥
#   2. 输出到终端和密钥文件
#   3. 提供 .env 配置模板
#
# 用法：
#   bash generate-secrets.sh
#   bash generate-secrets.sh --output .env.production
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

# 输出文件
OUTPUT_FILE=""
if [ "$1" = "--output" ] && [ -n "$2" ]; then
    OUTPUT_FILE="$2"
fi

echo "============================================"
echo " Nuotao AI OS - Secret Key Generator"
echo "============================================"
echo ""

# ============================================
# 密钥生成函数
# ============================================

# 生成随机字符串（指定长度）
generate_random() {
    local length=$1
    # 使用 /dev/urandom 生成安全随机字符串
    tr -dc 'A-Za-z0-9!@#$%^&*()_+-=[]{}|;:,.<>?' < /dev/urandom | head -c $length
}

# 生成十六进制随机字符串（JWT 密钥）
generate_hex() {
    local length=$1
    openssl rand -hex $length
}

# 生成 base64 随机字符串
generate_base64() {
    local length=$1
    openssl rand -base64 $length | tr -d '\n' | tr -d '/+=' | head -c $length
}

# 生成 UUID
generate_uuid() {
    cat /proc/sys/kernel/random/uuid 2>/dev/null || python3 -c "import uuid; print(uuid.uuid4())"
}

# ============================================
# 生成所有密钥
# ============================================

log_info "生成生产环境密钥..."

# 1. JWT 密钥（64 字符十六进制）
JWT_SECRET=$(generate_hex 32)
log_info "JWT_SECRET_KEY 已生成 (64字符)"

# 2. 数据库密码（32 字符强密码）
DB_PASSWORD=$(generate_random 32)
log_info "数据库密码已生成 (32字符)"

# 3. Redis 密码（32 字符）
REDIS_PASSWORD=$(generate_random 32)
log_info "Redis 密码已生成 (32字符)"

# 4. WooCommerce Webhook Secret（32 字符）
WOOCOMMERCE_WEBHOOK_SECRET=$(generate_random 32)
log_info "WooCommerce Webhook Secret 已生成"

# 5. 会话密钥（用于会话加密）
SESSION_SECRET=$(generate_hex 32)
log_info "会话密钥已生成"

# 6. API 签名密钥
API_SIGNING_SECRET=$(generate_hex 32)
log_info "API 签名密钥已生成"

# 7. 加密密钥（用于 PII 加密）
ENCRYPTION_KEY=$(generate_hex 32)
log_info "PII 加密密钥已生成"

# 8. 管理员初始密码（16 字符强密码）
ADMIN_PASSWORD=$(generate_random 16)
log_info "管理员初始密码已生成 (16字符)"

# 9. 工作空间 ID
WORKSPACE_ID=$(generate_uuid)
log_info "工作空间 ID 已生成"

# ============================================
# 输出密钥
# ============================================

echo ""
echo "============================================"
echo " 生成的生产环境密钥"
echo "============================================"
echo ""
echo "⚠️  请立即复制并妥善保存！这些密钥只显示一次。"
echo "⚠️  不要提交到代码仓库，不要分享给他人。"
echo ""

# 构建输出内容
OUTPUT_CONTENT=""
OUTPUT_CONTENT+="# ============================================\n"
OUTPUT_CONTENT+="# Nuotao AI OS - Production Secrets\n"
OUTPUT_CONTENT+="# Generated: $(date -u +"%Y-%m-%d %H:%M:%S UTC")\n"
OUTPUT_CONTENT+="# WARNING: Keep these secrets secure! Do not commit to git.\n"
OUTPUT_CONTENT+="# ============================================\n\n"

OUTPUT_CONTENT+="# --- 认证与安全 ---\n"
OUTPUT_CONTENT+="JWT_SECRET_KEY=$JWT_SECRET\n"
OUTPUT_CONTENT+="SESSION_SECRET=$SESSION_SECRET\n"
OUTPUT_CONTENT+="API_SIGNING_SECRET=$API_SIGNING_SECRET\n"
OUTPUT_CONTENT+="ENCRYPTION_KEY=$ENCRYPTION_KEY\n\n"

OUTPUT_CONTENT+="# --- 数据库 ---\n"
OUTPUT_CONTENT+="DB_PASSWORD=$DB_PASSWORD\n"
OUTPUT_CONTENT+="DATABASE_URL=postgresql+asyncpg://nuotao:$DB_PASSWORD@localhost:5432/nuotao\n\n"

OUTPUT_CONTENT+="# --- Redis ---\n"
OUTPUT_CONTENT+="REDIS_PASSWORD=$REDIS_PASSWORD\n"
OUTPUT_CONTENT+="REDIS_URL=redis://:$REDIS_PASSWORD@localhost:6379/0\n\n"

OUTPUT_CONTENT+="# --- WooCommerce ---\n"
OUTPUT_CONTENT+="WOOCOMMERCE_WEBHOOK_SECRET=$WOOCOMMERCE_WEBHOOK_SECRET\n"
OUTPUT_CONTENT+="# WOOCOMMERCE_CONSUMER_KEY=ck_xxx (从 WooCommerce 后台获取)\n"
OUTPUT_CONTENT+="# WOOCOMMERCE_CONSUMER_SECRET=cs_xxx (从 WooCommerce 后台获取)\n\n"

OUTPUT_CONTENT+="# --- 管理员账号 ---\n"
OUTPUT_CONTENT+="ADMIN_USERNAME=admin\n"
OUTPUT_CONTENT+="ADMIN_PASSWORD=$ADMIN_PASSWORD\n"
OUTPUT_CONTENT+="ADMIN_EMAIL=admin@nuotaooutdoor.com\n\n"

OUTPUT_CONTENT+="# --- 系统 ---\n"
OUTPUT_CONTENT+="WORKSPACE_ID=$WORKSPACE_ID\n"
OUTPUT_CONTENT+="ENVIRONMENT=production\n"

# 输出到终端
echo -e "$OUTPUT_CONTENT"

# 输出到文件
if [ -n "$OUTPUT_FILE" ]; then
    echo -e "$OUTPUT_CONTENT" > "$OUTPUT_FILE"
    chmod 600 "$OUTPUT_FILE"
    echo ""
    log_success "密钥已保存到: $OUTPUT_FILE"
    log_info "文件权限已设置为 600 (仅所有者可读写)"
fi

# ============================================
# 配置步骤提示
# ============================================

echo ""
echo "============================================"
echo " 后续配置步骤"
echo "============================================"
echo ""
echo "1. 修改数据库密码："
echo "   sudo -u postgres psql -c \"ALTER USER nuotao WITH PASSWORD '$DB_PASSWORD';\""
echo ""
echo "2. 修改 Redis 密码："
echo "   sudo sed -i 's/^# requirepass .*/requirepass $REDIS_PASSWORD/' /etc/redis/redis.conf"
echo "   sudo systemctl restart redis-server"
echo ""
echo "3. 更新 .env 文件："
echo "   将上述密钥复制到 /opt/nuotao-ai-os/backend/.env"
echo ""
echo "4. 修改 WooCommerce Webhook Secret："
echo "   在 WooCommerce 后台 → 设置 → 高级 → Webhook 中更新"
echo ""
echo "5. 重启服务："
echo "   sudo systemctl restart nuotao-backend"
echo ""
echo "============================================"
echo " 安全提示"
echo "============================================"
echo ""
echo "✅ 密钥已使用加密安全随机数生成"
echo "✅ 建议使用密码管理器保存（如 1Password、Bitwarden）"
echo "✅ 建议每 90 天轮换一次密钥"
echo "❌ 不要将密钥提交到 Git 仓库"
echo "❌ 不要通过邮件/即时通讯发送密钥"
echo "❌ 不要在代码中硬编码密钥"
echo "============================================"
