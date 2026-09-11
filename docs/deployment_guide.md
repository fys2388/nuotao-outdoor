# Nuotao AI OS 部署指南

本文档介绍 Nuotao AI OS 的两种部署方式：本地原生部署和 Docker 容器化部署。

## 目录

1. [系统要求](#系统要求)
2. [环境变量配置](#环境变量配置)
3. [方式一：本地原生部署（Windows/Linux）](#方式一本地原生部署)
4. [方式二：Docker 容器化部署](#方式二docker-容器化部署)
5. [前端部署](#前端部署)
6. [数据备份与恢复](#数据备份与恢复)
7. [监控与运维](#监控与运维)

---

## 系统要求

### 最低配置
- CPU: 2 核
- 内存: 4 GB
- 磁盘: 20 GB
- 操作系统: Windows 10/11, Ubuntu 20.04+, macOS 12+

### 推荐配置
- CPU: 4 核+
- 内存: 8 GB+
- 磁盘: 50 GB+ SSD
- 网络: 稳定的互联网连接（用于 LLM API 调用）

### 依赖软件
- Python 3.12+
- PostgreSQL 16+
- Redis 5.0+（必须支持 Stream 命令，推荐 Redis 7.x）
- Node.js 18+（前端构建）
- Docker 24+ + Docker Compose v2（容器化部署）

---

## 环境变量配置

复制 `.env.example` 为 `.env`，并根据实际情况修改：

```bash
cp .env.example .env
```

### 核心配置

| 变量 | 说明 | 默认值 |
|---|---|---|
| `ENVIRONMENT` | 运行环境 | `production` |
| `DEBUG` | 调试模式 | `false` |
| `LOG_LEVEL` | 日志级别 | `INFO` |
| `SECRET_KEY` | 应用密钥（生产环境必须修改） | - |

### 数据库配置

| 变量 | 说明 | 默认值 |
|---|---|---|
| `DATABASE_URL` | PostgreSQL 连接字符串 | `postgresql+asyncpg://nuotao:nuotao_dev_password@localhost:5432/nuotao` |
| `POSTGRES_USER` | 数据库用户名 | `nuotao` |
| `POSTGRES_PASSWORD` | 数据库密码 | `nuotao_dev_password` |
| `POSTGRES_DB` | 数据库名 | `nuotao` |

### Redis 配置

| 变量 | 说明 | 默认值 |
|---|---|---|
| `REDIS_URL` | Redis 连接字符串 | `redis://localhost:6379/0` |
| `TASK_QUEUE_BACKEND` | 任务队列后端 | `redis`（必须，Redis 5.0+） |

### LLM 配置

| 变量 | 说明 | 默认值 |
|---|---|---|
| `LLM_PROVIDER` | 主 LLM 提供商 | `deepseek` |
| `LLM_FALLBACK_PROVIDER` | 备用 LLM 提供商 | `openai` |
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | - |
| `DEEPSEEK_BASE_URL` | DeepSeek API 地址 | `https://api.deepseek.com/v1` |
| `DEEPSEEK_DEFAULT_MODEL` | DeepSeek 模型 | `deepseek-chat` |
| `OPENAI_API_KEY` | OpenAI API 密钥 | - |
| `OPENAI_BASE_URL` | OpenAI API 地址 | `https://api.openai.com/v1` |
| `OPENAI_DEFAULT_MODEL` | OpenAI 模型 | `gpt-4o-mini` |

### Worker 配置

| 变量 | 说明 | 默认值 |
|---|---|---|
| `AGENT_WORKER_CONCURRENCY` | Worker 并发数 | `4` |
| `AGENT_ALERT_SCHEDULER_ENABLED` | 启用告警调度器 | `true` |
| `AGENT_ALERT_INTERVAL_SECONDS` | 告警检查间隔（秒） | `60` |

### 业务配置

| 变量 | 说明 | 默认值 |
|---|---|---|
| `PAYMENT_FEE_RATE` | 支付手续费率 | `0.029` |
| `PAYMENT_FEE_FIXED` | 支付固定手续费 | `0.30` |
| `WOOCOMMERCE_WEBHOOK_SECRET` | WooCommerce Webhook 密钥 | - |

---

## 方式一：本地原生部署

### 1. 安装依赖

#### Windows

```powershell
# 安装 PostgreSQL 16+
# 下载地址: https://www.postgresql.org/download/windows/

# 安装 Redis 7.x（Windows 推荐使用 tporadowski/redis）
# 下载地址: https://github.com/tporadowski/redis/releases
# 注意: Redis 3.0 不支持 Stream 命令，必须使用 Redis 5.0+

# 安装 Python 3.12+
# 下载地址: https://www.python.org/downloads/

# 安装 Node.js 18+
# 下载地址: https://nodejs.org/
```

#### Ubuntu/Debian

```bash
# 安装 PostgreSQL 16
sudo apt update
sudo apt install -y postgresql postgresql-contrib

# 安装 Redis 7
sudo apt install -y redis-server

# 安装 Python 3.12
sudo apt install -y python3.12 python3.12-venv python3.12-dev

# 安装 Node.js 18
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs
```

### 2. 配置数据库

```bash
# 创建数据库和用户
sudo -u postgres psql
```

```sql
CREATE USER nuotao WITH PASSWORD 'your_secure_password';
CREATE DATABASE nuotao OWNER nuotao;
GRANT ALL PRIVILEGES ON DATABASE nuotao TO nuotao;
\q
```

### 3. 配置后端

```bash
cd backend

# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# 安装依赖
pip install -e .

# 配置环境变量
cp ../.env.example ../.env
# 编辑 .env 文件，设置数据库密码和 API 密钥

# 运行数据库迁移
alembic upgrade head

# 初始化 AI Agent（可选）
python init_all_agents.py
```

### 4. 启动后端服务

需要启动三个独立进程：API 服务、Worker、Scheduler。

```bash
# 终端 1: 启动 API 服务
cd backend
.venv\Scripts\activate  # Windows
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 终端 2: 启动 Worker
cd backend
.venv\Scripts\activate  # Windows
python run_worker.py

# 终端 3: 启动 Scheduler（可选，run_worker.py 已包含）
# 无需单独启动
```

### 5. 构建并启动前端

```bash
cd frontend

# 安装依赖
npm install

# 开发模式
npm run dev

# 生产构建
npm run build

# 预览生产构建
npm run preview
```

生产环境建议使用 Nginx 托管前端静态文件，并反向代理 API 请求。

---

## 方式二：Docker 容器化部署

### 1. 安装 Docker 和 Docker Compose

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，设置生产环境配置
# 注意: docker-compose.yml 中的服务名是 postgres 和 redis
# DATABASE_URL=postgresql+asyncpg://nuotao:password@postgres:5432/nuotao
# REDIS_URL=redis://redis:6379/0
```

### 3. 构建并启动服务

```bash
# 构建并启动所有服务
docker compose up -d --build

# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f scheduler

# 水平扩展 Worker
docker compose up -d --scale worker=4
```

### 4. 验证部署

```bash
# 健康检查
curl http://localhost:8000/api/v1/healthz
curl http://localhost:8000/api/v1/readyz

# 查看 API 文档
# 浏览器打开 http://localhost:8000/docs
```

### 5. 停止服务

```bash
# 停止服务（保留数据）
docker compose down

# 停止服务并删除数据卷（危险！）
docker compose down -v
```

---

## 前端部署

### 构建生产版本

```bash
cd frontend
npm install
npm run build
```

构建产物在 `frontend/dist` 目录。

### Nginx 配置示例

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # 前端静态文件
    root /var/www/nuotao-ai-os/dist;
    index index.html;

    # API 反向代理
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # SPA 路由回退
    location / {
        try_files $uri $uri/ /index.html;
    }

    # 静态资源缓存
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

### HTTPS 配置（推荐）

使用 Let's Encrypt 免费证书：

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

---

## 数据备份与恢复

### PostgreSQL 备份

```bash
# 备份
docker compose exec postgres pg_dump -U nuotao nuotao > backup_$(date +%Y%m%d).sql

# 恢复
docker compose exec -T postgres psql -U nuotao nuotao < backup_20240101.sql
```

### Redis 备份

```bash
# 备份（RDB）
docker compose exec redis redis-cli BGSAVE
docker compose cp redis:/data/dump.rdb ./redis_backup.rdb

# 恢复
docker compose cp ./redis_backup.rdb redis:/data/dump.rdb
docker compose restart redis
```

### 自动备份脚本

```bash
#!/bin/bash
# backup.sh - 每日自动备份脚本

BACKUP_DIR="/var/backups/nuotao-ai-os"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# PostgreSQL 备份
docker compose exec -T postgres pg_dump -U nuotao nuotao | gzip > $BACKUP_DIR/postgres_$DATE.sql.gz

# Redis 备份
docker compose exec redis redis-cli BGSAVE
sleep 2
docker compose cp redis:/data/dump.rdb $BACKUP_DIR/redis_$DATE.rdb

# 保留最近 30 天的备份
find $BACKUP_DIR -name "*.gz" -mtime +30 -delete
find $BACKUP_DIR -name "*.rdb" -mtime +30 -delete

echo "Backup completed: $DATE"
```

添加到 crontab：

```bash
crontab -e
# 每天凌晨 3 点执行备份
0 3 * * * /path/to/backup.sh >> /var/log/nuotao-backup.log 2>&1
```

---

## 监控与运维

### 健康检查端点

- `GET /api/v1/healthz` - 存活检查（不依赖数据库）
- `GET /api/v1/readyz` - 就绪检查（数据库 + Redis 连接）

### 日志查看

```bash
# API 日志
docker compose logs -f api

# Worker 日志
docker compose logs -f worker

# Scheduler 日志
docker compose logs -f scheduler

# 所有服务日志
docker compose logs -f
```

### 性能监控

推荐使用 Prometheus + Grafana 监控：

- PostgreSQL: postgres_exporter
- Redis: redis_exporter
- API: FastAPI metrics endpoint（需配置）
- 系统: node_exporter

### 常用运维命令

```bash
# 查看服务状态
docker compose ps

# 重启服务
docker compose restart api
docker compose restart worker

# 进入容器
docker compose exec api bash
docker compose exec postgres psql -U nuotao

# 查看资源使用
docker stats

# 清理未使用的镜像和容器
docker system prune -a
```

### 升级流程

```bash
# 1. 拉取最新代码
git pull origin main

# 2. 备份数据库
./backup.sh

# 3. 重新构建并启动
docker compose up -d --build

# 4. 验证服务
curl http://localhost:8000/api/v1/healthz

# 5. 查看迁移日志
docker compose logs api | grep -i alembic
```

---

## 故障排查

### API 服务返回 502

- 检查 API 服务是否运行：`docker compose ps api`
- 查看 API 日志：`docker compose logs api`
- 检查数据库连接：`docker compose exec postgres pg_isready -U nuotao`
- 检查 Redis 连接：`docker compose exec redis redis-cli ping`

### Worker 不消费任务

- 检查 Redis 版本是否 >= 5.0（支持 Stream 命令）
- 查看 Worker 日志：`docker compose logs worker`
- 检查任务队列：`docker compose exec redis redis-cli XLEN nuotao:agent-tasks`
- 检查 Worker 心跳：`docker compose exec redis redis-cli KEYS nuotao:agent-worker:*`

### LLM API 调用失败

- 检查 API 密钥是否正确配置
- 检查网络连接是否正常
- 查看 LLM 网关日志
- 检查 API 配额和余额

### 数据库迁移失败

- 查看迁移日志：`docker compose logs api | grep -i alembic`
- 手动运行迁移：`docker compose exec api alembic upgrade head`
- 检查数据库连接配置

---

## 安全建议

1. **修改默认密码**：生产环境必须修改 PostgreSQL、Redis 默认密码
2. **配置 HTTPS**：使用 Nginx + Let's Encrypt 配置 HTTPS
3. **防火墙**：只开放必要端口（80, 443），数据库和 Redis 不对外暴露
4. **定期备份**：配置每日自动备份，并定期验证恢复流程
5. **日志审计**：定期审查 API 访问日志和 Agent 运行记录
6. **依赖更新**：定期更新 Python 和 Node.js 依赖，修复安全漏洞
7. **密钥管理**：使用环境变量或密钥管理服务，不要将密钥提交到代码仓库

---

## 联系与支持

- 项目文档：`docs/` 目录
- API 文档：`http://localhost:8000/docs`
- 问题反馈：提交 GitHub Issue
