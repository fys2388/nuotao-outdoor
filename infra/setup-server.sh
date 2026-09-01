#!/bin/bash
# ============================================================
# Nuotao AI OS - 云服务器初始化脚本
# 支持: Ubuntu 22.04/24.04, Debian 12
# 功能: 安装 Docker、Docker Compose、配置防火墙、创建用户
# ============================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 检查是否为 root
if [ "$EUID" -ne 0 ]; then
    log_error "请使用 root 用户运行此脚本"
    exit 1
fi

# 检查操作系统
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$NAME
    VER=$VERSION_ID
else
    log_error "无法检测操作系统"
    exit 1
fi

log_info "检测到操作系统: $OS $VER"

# ============================================================
# 1. 系统更新
# ============================================================
log_info "更新系统包..."
apt-get update -qq
apt-get upgrade -y -qq
log_success "系统更新完成"

# ============================================================
# 2. 安装基础工具
# ============================================================
log_info "安装基础工具..."
apt-get install -y -qq \
    curl \
    wget \
    git \
    vim \
    htop \
    net-tools \
    unzip \
    software-properties-common \
    ca-certificates \
    gnupg \
    lsb-release \
    ufw \
    fail2ban
log_success "基础工具安装完成"

# ============================================================
# 3. 安装 Docker
# ============================================================
log_info "安装 Docker..."

# 移除旧版本
apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

# 添加 Docker 官方 GPG 密钥
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

# 添加 Docker 仓库
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null

# 安装 Docker
apt-get update -qq
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 启动 Docker
systemctl enable docker
systemctl start docker

# 验证安装
docker --version
docker compose version
log_success "Docker 安装完成"

# ============================================================
# 4. 配置防火墙
# ============================================================
log_info "配置防火墙..."

# 允许 SSH
ufw allow 22/tcp
# 允许 HTTP
ufw allow 80/tcp
# 允许 HTTPS
ufw allow 443/tcp
# 允许 Prometheus (仅内网)
ufw allow from 127.0.0.1 to any port 9090
# 允许 Grafana (仅内网)
ufw allow from 127.0.0.1 to any port 3000

# 启用防火墙
ufw --force enable
log_success "防火墙配置完成"

# ============================================================
# 5. 配置 Fail2Ban
# ============================================================
log_info "配置 Fail2Ban..."
cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true
port = 22
EOF

systemctl enable fail2ban
systemctl restart fail2ban
log_success "Fail2Ban 配置完成"

# ============================================================
# 6. 创建应用目录
# ============================================================
log_info "创建应用目录..."
mkdir -p /opt/nuotao-ai-os
mkdir -p /opt/nuotao-ai-os/backups
mkdir -p /opt/nuotao-ai-os/logs
mkdir -p /opt/nuotao-ai-os/data
log_success "应用目录创建完成"

# ============================================================
# 7. 配置系统参数
# ============================================================
log_info "配置系统参数..."

# 增加文件描述符限制
cat >> /etc/security/limits.conf << 'EOF'
* soft nofile 65536
* hard nofile 65536
EOF

# 优化网络参数
cat >> /etc/sysctl.conf << 'EOF'
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 65535
net.ipv4.ip_forward = 1
vm.swappiness = 10
EOF

sysctl -p
log_success "系统参数配置完成"

# ============================================================
# 8. 安装监控代理 (可选)
# ============================================================
log_info "安装 Node Exporter (Prometheus 监控)..."
NODE_EXPORTER_VERSION="1.8.2"
wget -q https://github.com/prometheus/node_exporter/releases/download/v${NODE_EXPORTER_VERSION}/node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64.tar.gz
tar xzf node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64.tar.gz
cp node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64/node_exporter /usr/local/bin/
rm -rf node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64*

# 创建 systemd 服务
cat > /etc/systemd/system/node_exporter.service << 'EOF'
[Unit]
Description=Node Exporter
After=network.target

[Service]
User=root
ExecStart=/usr/local/bin/node_exporter
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable node_exporter
systemctl start node_exporter
log_success "Node Exporter 安装完成"

# ============================================================
# 完成
# ============================================================
echo ""
echo "============================================================"
echo -e "${GREEN}✅ 云服务器初始化完成！${NC}"
echo "============================================================"
echo ""
echo "下一步操作:"
echo "  1. 将项目代码上传到 /opt/nuotao-ai-os"
echo "  2. 复制 .env.production.example 为 .env 并填写配置"
echo "  3. 运行 ./infra/deploy-production.sh 部署应用"
echo ""
echo "重要信息:"
echo "  - Docker 已安装并启用"
echo "  - 防火墙已配置 (22/80/443)"
echo "  - Fail2Ban 已启用"
echo "  - Node Exporter 已运行 (端口 9100)"
echo "  - 应用目录: /opt/nuotao-ai-os"
echo ""
echo "请记录以下信息:"
echo "  - 服务器 IP: $(curl -s ifconfig.me)"
echo "  - SSH 端口: 22"
echo "============================================================"
