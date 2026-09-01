# Nuotao AI OS 云服务器部署指南

## 1. 云服务器选择建议

### 推荐配置
| 配置项 | 最低要求 | 推荐配置 |
|---|---|---|
| CPU | 2 核 | 4 核 |
| 内存 | 4 GB | 8 GB |
| 硬盘 | 40 GB SSD | 80 GB SSD |
| 带宽 | 5 Mbps | 10 Mbps |
| 操作系统 | Ubuntu 22.04 LTS | Ubuntu 24.04 LTS |

### 推荐云服务商
- **阿里云**: 轻量应用服务器（性价比高）
- **腾讯云**: 轻量应用服务器（新人优惠）
- **华为云**: 弹性云服务器
- **AWS**: EC2 t3.medium（海外业务）
- **DigitalOcean**: Droplet（海外业务）

---

## 2. 部署前准备

### 2.1 域名解析
1. 登录域名管理面板（如阿里云、Cloudflare）
2. 添加 A 记录：`your-domain.com` → 服务器 IP
3. 添加 A 记录：`www.your-domain.com` → 服务器 IP
4. 等待 DNS 生效（通常 5-30 分钟）

### 2.2 安全组配置
在云服务商控制台开放以下端口：
| 端口 | 协议 | 用途 |
|---|---|---|
| 22 | TCP | SSH 远程登录 |
| 80 | TCP | HTTP |
| 443 | TCP | HTTPS |
| 9090 | TCP | Prometheus（仅内网） |
| 3000 | TCP | Grafana（仅内网） |

---

## 3. 服务器初始化

### 3.1 连接服务器
```bash
ssh root@your-server-ip
```

### 3.2 上传初始化脚本
在本地执行：
```bash
scp infra/setup-server.sh root@your-server-ip:/root/
```

### 3.3 执行初始化脚本
```bash
chmod +x /root/setup-server.sh
/root/setup-server.sh
```

脚本会自动完成：
- ✅ 系统更新
- ✅ 安装 Docker + Docker Compose
- ✅ 配置防火墙（UFW）
- ✅ 安装 Fail2Ban
- ✅ 安装 Node Exporter（监控）
- ✅ 创建应用目录
- ✅ 优化系统参数

### 3.4 验证初始化
```bash
docker --version
docker compose version
ufw status
systemctl status node_exporter
```

---

## 4. 部署应用

### 4.1 上传代码
方式一：使用 Git（推荐）
```bash
cd /opt/nuotao-ai-os
git clone https://github.com/your-username/nuotao-ai-os.git .
```

方式二：使用 SCP
```bash
# 在本地执行
scp -r nuotao-ai-os/* root@your-server-ip:/opt/nuotao-ai-os/
```

### 4.2 配置环境变量
```bash
cd /opt/nuotao-ai-os
cp .env.production.example .env
nano .env
```

**必须修改的配置项**：
```env
# 应用配置
APP_ENV=production
APP_SECRET_KEY=your-secret-key-here（用 openssl rand -hex 32 生成）

# 数据库配置
POSTGRES_PASSWORD=your-strong-password
POSTGRES_USER=nuotao
POSTGRES_DB=nuotao

# Redis 配置
REDIS_PASSWORD=your-redis-password

# LLM 配置
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx

# WooCommerce 配置
WOOCOMMERCE_BASE_URL=https://your-domain.com
WOOCOMMERCE_CONSUMER_KEY=ck_xxxxxxxxxxxxxxxx
WOOCOMMERCE_CONSUMER_SECRET=cs_xxxxxxxxxxxxxxxx

# 域名配置（用于 SSL 证书）
DOMAIN=your-domain.com
SSL_EMAIL=your-email@example.com
```

### 4.3 启动应用
```bash
cd /opt/nuotao-ai-os
chmod +x infra/deploy.sh
./infra/deploy.sh deploy
```

部署脚本会自动完成：
1. ✅ 备份数据库
2. ✅ 构建 Docker 镜像
3. ✅ 停止旧服务
4. ✅ 启动新服务
5. ✅ 运行数据库迁移
6. ✅ 健康检查

### 4.4 查看服务状态
```bash
./infra/deploy.sh status
```

预期输出：
```
NAME                STATUS
nuotao-api          running
nuotao-worker       running
nuotao-postgres     running
nuotao-redis        running
nuotao-nginx        running
nuotao-prometheus   running
nuotao-grafana      running
nuotao-alertmanager running
```

---

## 5. SSL 证书配置

### 5.1 使用 Certbot 自动申请
```bash
docker compose -f docker-compose.prod.yml run --rm certbot certonly --webroot --webroot-path /var/www/certbot -d your-domain.com -d www.your-domain.com
```

### 5.2 配置 Nginx 使用 SSL
编辑 `infra/nginx/nginx.conf`，取消 HTTPS 配置注释：
```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # ... 其他配置
}
```

### 5.3 重启 Nginx
```bash
docker compose -f docker-compose.prod.yml restart nginx
```

---

## 6. 验证部署

### 6.1 健康检查
```bash
curl https://your-domain.com/api/v1/healthz
```
预期输出：`{"status":"ok"}`

### 6.2 访问前端
在浏览器中打开：`https://your-domain.com`

### 6.3 访问 API 文档
在浏览器中打开：`https://your-domain.com/docs`

### 6.4 访问 Grafana
在浏览器中打开：`https://your-domain.com/grafana`
- 默认账号：`admin`
- 默认密码：`admin`（首次登录后修改）

### 6.5 访问 Prometheus
在浏览器中打开：`https://your-domain.com/prometheus`

---

## 7. 日常运维

### 7.1 查看日志
```bash
# 查看所有服务日志
./infra/deploy.sh logs

# 查看特定服务日志
./infra/deploy.sh logs api
./infra/deploy.sh logs worker
./infra/deploy.sh logs postgres
```

### 7.2 重启服务
```bash
# 重启所有服务
./infra/deploy.sh restart

# 重启特定服务
./infra/deploy.sh restart api
```

### 7.3 停止服务
```bash
./infra/deploy.sh stop
```

### 7.4 备份数据库
```bash
./infra/deploy.sh backup
```

备份文件位置：`/opt/nuotao-ai-os/backups/`

### 7.5 恢复数据库
```bash
./infra/deploy.sh restore backups/nuotao_20240101_120000.sql.gz
```

### 7.6 更新应用
```bash
cd /opt/nuotao-ai-os
git pull
./infra/deploy.sh deploy
```

### 7.7 回滚到上一版本
```bash
./infra/deploy.sh rollback
```

---

## 8. 监控告警配置

### 8.1 导入 Grafana 仪表盘
1. 登录 Grafana
2. 进入 Dashboards → New → Import
3. 上传 `infra/grafana/dashboards/nuotao-ai-os.json`
4. 选择 Prometheus 数据源
5. 点击 Import

### 8.2 配置 Alertmanager
编辑 `infra/alertmanager/alertmanager.yml`，填写通知渠道：
```yaml
global:
  smtp_smarthost: 'smtp.gmail.com:587'
  smtp_from: 'alerts@your-domain.com'
  smtp_auth_username: 'alerts@your-domain.com'
  smtp_auth_password: 'your-email-password'

  dingtalk_api_url: 'https://oapi.dingtalk.com/robot/send?access_token=your-token'
  wechat_api_url: 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=your-key'
```

重启 Alertmanager：
```bash
docker compose -f docker-compose.prod.yml restart alertmanager
```

---

## 9. 常见问题

### Q1: 部署后无法访问网站
**检查清单**：
1. 安全组是否开放 80/443 端口
2. 防火墙是否开放 80/443 端口：`ufw status`
3. Nginx 是否正常运行：`docker ps | grep nginx`
4. Nginx 日志：`docker logs nuotao-nginx`
5. DNS 是否解析正确：`nslookup your-domain.com`

### Q2: 数据库连接失败
**检查清单**：
1. PostgreSQL 是否运行：`docker ps | grep postgres`
2. 数据库密码是否正确：检查 `.env` 文件
3. 数据库日志：`docker logs nuotao-postgres`
4. 手动测试连接：`docker exec -it nuotao-postgres psql -U nuotao -d nuotao`

### Q3: LLM API 调用失败
**检查清单**：
1. API Key 是否正确：检查 `.env` 文件
2. 网络是否能访问 API 服务商：`curl https://api.deepseek.com`
3. API 额度是否充足：登录服务商控制台查看
4. 后端日志：`docker logs nuotao-api`

### Q4: WooCommerce 同步失败
**检查清单**：
1. Consumer Key/Secret 是否正确
2. WooCommerce REST API 是否启用
3. 店铺是否能正常访问：`curl https://your-shop.com`
4. 后端日志：`docker logs nuotao-api`

### Q5: 如何查看系统资源使用
```bash
# 查看 Docker 容器资源使用
docker stats

# 查看系统内存使用
free -h

# 查看磁盘使用
df -h

# 查看 CPU 使用
top
```

---

## 10. 安全建议

1. **修改默认密码**：Grafana、数据库、Redis 都要修改默认密码
2. **启用 HTTPS**：所有外部访问都使用 HTTPS
3. **定期备份**：配置每日自动备份
4. **限制 SSH 访问**：使用密钥登录，禁用密码登录
5. **更新系统**：定期更新系统补丁
6. **监控告警**：配置告警通知，及时发现问题
7. **日志审计**：定期检查访问日志和错误日志

---

## 11. 联系支持

如遇问题，请检查：
1. 后端日志：`docker logs nuotao-api`
2. Worker 日志：`docker logs nuotao-worker`
3. Nginx 日志：`docker logs nuotao-nginx`
4. 系统状态：`./infra/deploy.sh status`
5. 健康检查：`./infra/deploy.sh health`

---

**部署完成后，请记录以下信息**：
- 服务器 IP：__________
- 域名：__________
- 数据库密码：__________（妥善保管）
- Redis 密码：__________
- Grafana 账号：__________
- SSH 密钥：__________（妥善保管）
