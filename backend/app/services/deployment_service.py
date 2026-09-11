"""
本地生产环境部署服务
提供生产环境配置、服务管理、健康检查等功能
"""
from __future__ import annotations

import logging
import os
import platform
import sys
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "deployment",
)

# 项目路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")

# 服务配置
SERVICES = {
    "backend": {
        "name": "Nuotao AI OS Backend",
        "host": "0.0.0.0",
        "port": 8000,
        "workers": 2,
        "command": "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2",
        "health_check_url": "http://localhost:8000/api/v1/health",
    },
    "frontend": {
        "name": "Nuotao AI OS Frontend",
        "host": "0.0.0.0",
        "port": 5173,
        "command": "npm run dev -- --host 0.0.0.0",
        "health_check_url": "http://localhost:5173",
    },
    "postgresql": {
        "name": "PostgreSQL Database",
        "port": 5432,
        "host": "localhost",
        "database": "nuotao",
        "user": "nuotao",
    },
    "redis": {
        "name": "Redis Cache",
        "port": 6379,
        "host": "localhost",
    },
}


def _ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def get_system_info() -> dict[str, Any]:
    """获取系统信息"""
    return {
        "os": platform.system(),
        "os_version": platform.version(),
        "os_release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python_version": sys.version,
        "hostname": platform.node(),
        "current_time": datetime.now().isoformat(),
    }


def get_project_structure() -> dict[str, Any]:
    """获取项目结构信息"""
    structure = {
        "project_root": PROJECT_ROOT,
        "backend_dir": BACKEND_DIR,
        "frontend_dir": FRONTEND_DIR,
        "backend_exists": os.path.exists(BACKEND_DIR),
        "frontend_exists": os.path.exists(FRONTEND_DIR),
        "backend_venv_exists": os.path.exists(os.path.join(BACKEND_DIR, ".venv")),
        "frontend_node_modules_exists": os.path.exists(os.path.join(FRONTEND_DIR, "node_modules")),
    }

    # 检查关键文件
    key_files = {
        "backend_main": os.path.join(BACKEND_DIR, "app", "main.py"),
        "backend_requirements": os.path.join(BACKEND_DIR, "requirements.txt"),
        "frontend_package_json": os.path.join(FRONTEND_DIR, "package.json"),
        "frontend_vite_config": os.path.join(FRONTEND_DIR, "vite.config.ts"),
        "docker_compose": os.path.join(PROJECT_ROOT, "docker-compose.yml"),
        "nginx_config": os.path.join(PROJECT_ROOT, "infra", "nginx", "nginx.conf"),
    }

    structure["key_files"] = {
        name: {"path": path, "exists": os.path.exists(path)}
        for name, path in key_files.items()
    }

    return structure


def check_service_health(service_name: str) -> dict[str, Any]:
    """检查服务健康状态"""
    if service_name not in SERVICES:
        return {"success": False, "error": f"Unknown service: {service_name}"}

    service = SERVICES[service_name]
    result = {
        "service": service_name,
        "name": service["name"],
        "port": service.get("port"),
        "status": "unknown",
        "message": "",
    }

    # 检查端口是否监听
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result_port = sock.connect_ex(("localhost", service["port"]))
        sock.close()

        if result_port == 0:
            result["status"] = "running"
            result["message"] = f"Port {service['port']} is listening"
        else:
            result["status"] = "stopped"
            result["message"] = f"Port {service['port']} is not listening"
    except Exception as e:
        result["status"] = "error"
        result["message"] = f"Health check failed: {e!s}"

    return result


def check_all_services() -> dict[str, Any]:
    """检查所有服务健康状态"""
    services_status = {}
    all_running = True

    for service_name in SERVICES:
        status = check_service_health(service_name)
        services_status[service_name] = status
        if status["status"] != "running":
            all_running = False

    return {
        "success": True,
        "all_running": all_running,
        "services": services_status,
        "summary": {
            "total": len(SERVICES),
            "running": sum(1 for s in services_status.values() if s["status"] == "running"),
            "stopped": sum(1 for s in services_status.values() if s["status"] == "stopped"),
        },
    }


def generate_nginx_config() -> str:
    """生成 Nginx 反向代理配置"""
    return """# Nuotao AI OS - Nginx 反向代理配置
# 适用于本地生产环境和云服务器部署

upstream nuotao_backend {
    server 127.0.0.1:8000;
    keepalive 32;
}

upstream nuotao_frontend {
    server 127.0.0.1:5173;
    keepalive 32;
}

server {
    listen 80;
    server_name localhost nuotao.local;

    # 前端静态文件和开发服务器
    location / {
        proxy_pass http://nuotao_frontend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }

    # 后端 API 代理
    location /api/ {
        proxy_pass http://nuotao_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
        client_max_body_size 50M;
    }

    # API 文档
    location /docs {
        proxy_pass http://nuotao_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /openapi.json {
        proxy_pass http://nuotao_backend;
    }

    # WebSocket 支持
    location /ws/ {
        proxy_pass http://nuotao_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }

    # 健康检查
    location /health {
        proxy_pass http://nuotao_backend/api/v1/health;
    }

    # 安全头
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Gzip 压缩
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript application/x-javascript application/xml+rss application/javascript application/json;
}

# HTTPS 配置（云服务器部署时启用，需先配置 SSL 证书）
# server {
#     listen 443 ssl http2;
#     server_name your-domain.com;
#
#     ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
#     ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
#     ssl_protocols TLSv1.2 TLSv1.3;
#     ssl_ciphers HIGH:!aNULL:!MD5;
#     ssl_prefer_server_ciphers on;
#
#     # 其余配置同上
# }
"""


def generate_windows_startup_script() -> str:
    """生成 Windows 自启动脚本"""
    return """@echo off
:: Nuotao AI OS - Windows 自启动脚本
:: 将此脚本放入启动文件夹：shell:startup

echo ========================================
echo   Nuotao AI OS 启动脚本
echo ========================================
echo.

:: 启动 PostgreSQL
echo [1/4] 启动 PostgreSQL...
net start postgresql-x64-17 2>nul
echo PostgreSQL 已启动

:: 启动 Redis
echo [2/4] 启动 Redis...
start "Redis" /min cmd /c "cd /d E:\\AI\\redis5 && redis-server.exe redis.windows.conf"
timeout /t 2 /nobreak >nul
echo Redis 已启动

:: 启动后端
echo [3/4] 启动后端服务...
start "Nuotao Backend" /min cmd /c "cd /d E:\\AI\\nuotao-ai-os\\backend && .venv\\Scripts\\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
timeout /t 3 /nobreak >nul
echo 后端服务已启动

:: 启动前端
echo [4/4] 启动前端服务...
start "Nuotao Frontend" /min cmd /c "cd /d E:\\AI\\nuotao-ai-os\\frontend && npm run dev"
timeout /t 3 /nobreak >nul
echo 前端服务已启动

echo.
echo ========================================
echo   所有服务启动完成！
echo   管理控制台: http://localhost:5173
echo   API 文档: http://localhost:8000/docs
echo ========================================
echo.
pause
"""


def generate_linux_systemd_config() -> str:
    """生成 Linux systemd 服务配置（云服务器部署用）"""
    return """# Nuotao AI OS - systemd 服务配置
# 适用于 Linux 云服务器部署
# 放置路径: /etc/systemd/system/nuotao-ai-os.service

[Unit]
Description=Nuotao AI OS - AI Native Outdoor Commerce Operating System
After=network.target postgresql.service redis.service
Wants=postgresql.service redis.service

[Service]
Type=simple
User=nuotao
Group=nuotao
WorkingDirectory=/opt/nuotao-ai-os/backend
Environment="PATH=/opt/nuotao-ai-os/backend/.venv/bin"
Environment="DATABASE_URL=postgresql://nuotao:your_password@localhost:5432/nuotao"
Environment="REDIS_URL=redis://localhost:6379/0"
Environment="WOOCOMMERCE_URL=https://nuotaooutdoor.com"
Environment="FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your-hook-id"

ExecStart=/opt/nuotao-ai-os/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=nuotao-ai-os

# 安全限制
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/nuotao-ai-os/backend/data

[Install]
WantedBy=multi-user.target
"""


def generate_deployment_guide() -> str:
    """生成云服务器部署指南"""
    return """# Nuotao AI OS 云服务器部署指南

## 一、服务器要求

### 最低配置
- CPU: 2 核
- 内存: 4 GB
- 硬盘: 40 GB SSD
- 带宽: 5 Mbps
- 操作系统: Ubuntu 22.04 LTS / Debian 12 / CentOS 8

### 推荐配置
- CPU: 4 核
- 内存: 8 GB
- 硬盘: 80 GB SSD
- 带宽: 10 Mbps

## 二、免费/低成本云服务器选项

| 服务商 | 免费额度 | 备注 |
|--------|---------|------|
| Oracle Cloud | 永久免费（AMD 1核1G + ARM 4核24G） | 需国际信用卡 |
| AWS Free Tier | 12个月免费（t2.micro 1核1G） | 需国际信用卡 |
| Google Cloud | 300美元信用额度（90天） | 需国际信用卡 |
| 阿里云 | 新用户 99元/年（2核2G） | 需国内信用卡 |
| 腾讯云 | 新用户 99元/年（2核2G） | 需国内信用卡 |
| 华为云 | 新用户优惠 | 需国内信用卡 |

## 三、部署步骤

### 1. 基础环境安装

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装基础工具
sudo apt install -y git curl wget nginx python3 python3-pip python3-venv postgresql postgresql-contrib redis-server

# 安装 Node.js 18
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs
```

### 2. 数据库配置

```bash
# 创建数据库和用户
sudo -u postgres psql
CREATE DATABASE nuotao;
CREATE USER nuotao WITH PASSWORD 'your_strong_password';
GRANT ALL PRIVILEGES ON DATABASE nuotao TO nuotao;
\\q

# 启用 pgvector 扩展
sudo apt install -y postgresql-14-pgvector
sudo -u postgres psql -d nuotao -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### 3. 项目部署

```bash
# 创建项目目录
sudo mkdir -p /opt/nuotao-ai-os
sudo chown $USER:$USER /opt/nuotao-ai-os

# 克隆项目
cd /opt
git clone https://github.com/your-username/nuotao-ai-os.git
cd nuotao-ai-os

# 后端配置
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
nano .env  # 编辑配置

# 数据库迁移
alembic upgrade head

# 前端构建
cd ../frontend
npm install
npm run build
```

### 4. 服务配置

```bash
# 复制 systemd 服务配置
sudo cp infra/systemd/nuotao-ai-os.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable nuotao-ai-os
sudo systemctl start nuotao-ai-os

# 配置 Nginx
sudo cp infra/nginx/nginx.conf /etc/nginx/sites-available/nuotao-ai-os
sudo ln -s /etc/nginx/sites-available/nuotao-ai-os /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 5. SSL 证书配置

```bash
# 安装 Certbot
sudo apt install -y certbot python3-certbot-nginx

# 申请证书（需先配置域名解析）
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# 自动续期
sudo certbot renew --dry-run
```

### 6. 防火墙配置

```bash
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

## 四、本地生产环境（当前方案）

由于 Docker Desktop 虚拟化问题和 Oracle Cloud 信用卡问题，当前采用本地生产环境：

### 已配置
- ✅ PostgreSQL 17（端口 5432）
- ✅ Redis 7.2（端口 6379）
- ✅ 后端 FastAPI（端口 8000，uvicorn）
- ✅ 前端 React/Vite（端口 5173）
- ✅ Nginx 反向代理配置（已生成，待安装 Nginx）
- ✅ Windows 自启动脚本（已生成）
- ✅ 健康检查 API

### 可选：安装 Nginx for Windows
1. 下载: http://nginx.org/en/download.html
2. 解压到 C:\\nginx
3. 复制配置文件到 C:\\nginx\\conf\\nginx.conf
4. 启动: start nginx
5. 访问: http://localhost（自动代理到前端和后端）

## 五、监控与维护

### 日志查看
```bash
# 后端日志
sudo journalctl -u nuotao-ai-os -f

# Nginx 日志
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### 数据库备份
```bash
# 手动备份
pg_dump -U nuotao nuotao > backup_$(date +%Y%m%d).sql

# 自动备份（添加到 crontab）
0 2 * * * pg_dump -U nuotao nuotao | gzip > /backup/nuotao_$(date +%Y%m%d).sql.gz
```

### 服务更新
```bash
cd /opt/nuotao-ai-os
git pull
cd backend && source .venv/bin/activate && pip install -r requirements.txt && alembic upgrade head
cd ../frontend && npm install && npm run build
sudo systemctl restart nuotao-ai-os
```

## 六、安全检查清单

- [ ] 修改所有默认密码（数据库、Redis、管理后台）
- [ ] 配置 SSL 证书（HTTPS）
- [ ] 配置防火墙（只开放必要端口）
- [ ] 配置数据库自动备份
- [ ] 配置日志轮转
- [ ] 配置监控告警（Prometheus + Grafana）
- [ ] 启用 Fail2ban（防止暴力破解）
- [ ] 定期更新系统和依赖
- [ ] 配置 Secrets 管理（不硬编码密钥）
- [ ] 配置 GDPR 合规（隐私政策、数据导出/删除）
"""


def get_deployment_status() -> dict[str, Any]:
    """获取部署状态"""
    system_info = get_system_info()
    project_structure = get_project_structure()
    services_status = check_all_services()

    return {
        "success": True,
        "deployment_mode": "local_production",
        "system_info": system_info,
        "project_structure": project_structure,
        "services": services_status,
        "configured_features": [
            "postgresql_database",
            "redis_cache",
            "fastapi_backend",
            "react_frontend",
            "woocommerce_integration",
            "feishu_notifications",
            "health_check_api",
            "nginx_config_generated",
            "windows_startup_script_generated",
            "linux_systemd_config_generated",
            "deployment_guide_generated",
        ],
        "next_steps": [
            "安装 Nginx for Windows 启用反向代理",
            "配置 Windows 自启动脚本",
            "考虑云服务器部署（阿里云/腾讯云 99元/年）",
            "配置 SSL 证书（云服务器部署后）",
            "配置数据库自动备份",
            "配置监控告警",
        ],
    }
