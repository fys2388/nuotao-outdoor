#!/bin/bash
# B2B 端子部署脚本
# 在 Hetzner 生产服务器上执行
# 用法: bash deploy_b2b_portal.sh

set -e

B2B_DOMAIN="b2b.nuotaooutdoor.com"
B2B_WEBROOT="/var/www/b2b-portal"
BACKEND_URL="http://127.0.0.1:8000"
NGINX_CONF="/etc/nginx/sites-available/b2b"

echo "=== Nuotao B2B Portal Deployment ==="
echo "Domain: $B2B_DOMAIN"
echo ""

# 1. 创建 webroot 目录
echo "[1/5] Creating webroot directory..."
mkdir -p "$B2B_WEBROOT"

# 2. 写入 Nginx 配置
echo "[2/5] Writing Nginx configuration..."
cat > "$NGINX_CONF" << 'NGINX_EOF'
server {
    listen 80;
    server_name b2b.nuotaooutdoor.com;

    root /var/www/b2b-portal;
    index index.html;

    # B2B 门户前端静态文件
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API 反代到后端 FastAPI
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        proxy_connect_timeout 10s;
        client_max_body_size 20m;
    }

    # 安全头
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # 静态资源缓存
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # gzip
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;
    gzip_min_length 1024;
}
NGINX_EOF

# 3. 启用站点
echo "[3/5] Enabling site..."
ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/b2b

# 4. 测试 Nginx 配置
echo "[4/5] Testing Nginx configuration..."
nginx -t

# 5. 重载 Nginx
echo "[5/5] Reloading Nginx..."
systemctl reload nginx

echo ""
echo "=== Nginx configured successfully ==="
echo "Next steps:"
echo "  1. Ensure DNS A record for $B2B_DOMAIN points to this server"
echo "  2. Run: certbot --nginx -d $B2B_DOMAIN --non-interactive --agree-tos --email admin@nuotaooutdoor.com"
echo "  3. Upload frontend build to $B2B_WEBROOT"
echo "  4. Run Alembic migration: cd /opt/nuotao/backend && alembic upgrade head"
echo ""
