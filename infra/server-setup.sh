#!/bin/bash
# ============================================
# Nuotao AI OS - 服务器初始化脚本 (Ubuntu 22.04/24.04)
# ============================================
# 功能：
#   1. 系统更新和基础工具安装
#   2. PostgreSQL 16 安装和配置
#   3. Redis 7 安装和配置
#   4. Nginx 安装和配置
#   5. Python 3.12 安装
#   6. Node.js 20 安装
#   7. 防火墙配置
#   8. 系统安全加固
#
# 用法：
#   sudo bash server-setup.sh
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
echo " Nuotao AI OS - Server Setup"
echo "============================================"
echo ""

# ============================================
# 1. 系统更新和基础工具
# ============================================
log_info "Step 1/8: 系统更新和基础工具安装..."

apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq \
    curl wget git unzip zip \
    build-essential software-properties-common \
    apt-transport-https ca-certificates gnupg \
    htop net-tools vim nano \
    ufw fail2ban \
    certbot python3-certbot-nginx

log_success "系统更新和基础工具安装完成"

# ============================================
# 2. PostgreSQL 16 安装
# ============================================
log_info "Step 2/8: PostgreSQL 16 安装和配置..."

# 添加 PostgreSQL 官方源
sh -c 'echo "deb https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list'
wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add -

apt-get update -qq
apt-get install -y -qq postgresql-16 postgresql-contrib-16

# 启动 PostgreSQL
systemctl enable postgresql
systemctl start postgresql

# 创建数据库和用户
log_info "创建数据库和用户..."
sudo -u postgres psql <<EOF
CREATE USER nuotao WITH PASSWORD 'CHANGE_ME_STRONG_DB_PASSWORD';
CREATE DATABASE nuotao OWNER nuotao;
GRANT ALL PRIVILEGES ON DATABASE nuotao TO nuotao;
EOF

# 配置 PostgreSQL 允许本地连接
sed -i "s/#listen_addresses = 'localhost'/listen_addresses = 'localhost'/" /etc/postgresql/16/main/postgresql.conf

systemctl restart postgresql

log_success "PostgreSQL 16 安装完成"

# ============================================
# 3. Redis 7 安装
# ============================================
log_info "Step 3/8: Redis 7 安装和配置..."

apt-get install -y -qq redis-server

# 配置 Redis
sed -i 's/^bind 127.0.0.1 ::1/bind 127.0.0.1/' /etc/redis/redis.conf
sed -i 's/^protected-mode yes/protected-mode yes/' /etc/redis/redis.conf
sed -i 's/^# requirepass .*/requirepass CHANGE_ME_STRONG_REDIS_PASSWORD/' /etc/redis/redis.conf
sed -i 's/^# maxmemory .*/maxmemory 256mb/' /etc/redis/redis.conf
sed -i 's/^# maxmemory-policy .*/maxmemory-policy allkeys-lru/' /etc/redis/redis.conf

systemctl enable redis-server
systemctl restart redis-server

log_success "Redis 7 安装完成"

# ============================================
# 4. Nginx 安装
# ============================================
log_info "Step 4/8: Nginx 安装和配置..."

apt-get install -y -qq nginx

systemctl enable nginx
systemctl start nginx

log_success "Nginx 安装完成"

# ============================================
# 5. Python 3.12 安装
# ============================================
log_info "Step 5/8: Python 3.12 安装..."

add-apt-repository -y ppa:deadsnakes/ppa
apt-get update -qq
apt-get install -y -qq \
    python3.12 python3.12-venv python3.12-dev \
    python3-pip python3.12-distutils

# 设置 Python 3.12 为默认
update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1

log_success "Python 3.12 安装完成"

# ============================================
# 6. Node.js 20 安装
# ============================================
log_info "Step 6/8: Node.js 20 安装..."

curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y -qq nodejs

log_success "Node.js 20 安装完成 (版本: $(node -v))"

# ============================================
# 7. 防火墙配置
# ============================================
log_info "Step 7/8: 防火墙配置..."

ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow http
ufw allow https
ufw --force enable

log_success "防火墙配置完成 (SSH/HTTP/HTTPS 已开放)"

# ============================================
# 8. 系统安全加固
# ============================================
log_info "Step 8/8: 系统安全加固..."

# 配置 fail2ban
systemctl enable fail2ban
systemctl start fail2ban

# 创建应用用户
log_info "创建应用用户 nuotao..."
id -u nuotao &>/dev/null || useradd -m -s /bin/bash nuotao

# 创建应用目录
mkdir -p /opt/nuotao-ai-os
mkdir -p /var/log/nuotao
mkdir -p /var/backups/nuotao
chown -R nuotao:nuotao /opt/nuotao-ai-os
chown -R nuotao:nuotao /var/log/nuotao
chown -R nuotao:nuotao /var/backups/nuotao

# 配置自动安全更新
apt-get install -y -qq unattended-upgrades
dpkg-reconfigure -plow unattended-upgrades

log_success "系统安全加固完成"

# ============================================
# 完成
# ============================================
echo ""
echo "============================================"
echo " Server Setup Complete!"
echo "============================================"
echo ""
echo "已安装组件："
echo "  - PostgreSQL 16 (端口 5432)"
echo "  - Redis 7 (端口 6379)"
echo "  - Nginx (端口 80/443)"
echo "  - Python 3.12"
echo "  - Node.js 20"
echo "  - UFW 防火墙"
echo "  - Fail2ban"
echo ""
echo "重要提示："
echo "  1. 请修改以下默认密码："
echo "     - PostgreSQL: CHANGE_ME_STRONG_DB_PASSWORD"
echo "     - Redis: CHANGE_ME_STRONG_REDIS_PASSWORD"
echo "  2. 运行部署脚本安装应用："
echo "     sudo bash deploy-production.sh"
echo "  3. 配置 SSL 证书："
echo "     sudo certbot --nginx -d nuotaooutdoor.com -d www.nuotaooutdoor.com"
echo ""
echo "系统信息："
echo "  OS: $(lsb_release -d | cut -f2)"
echo "  内核: $(uname -r)"
echo "  内存: $(free -h | grep Mem | awk '{print $2}')"
echo "  磁盘: $(df -h / | tail -1 | awk '{print $2}')"
echo "============================================"
