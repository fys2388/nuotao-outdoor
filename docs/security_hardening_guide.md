# Nuotao AI OS - 生产环境安全加固指南

## �?、默认密码修改清�?

部署到生产环境后，必须修改以下默认密码：

### 1.1 系统账号

| 账号 | 默认密码 | 修改方式 | 优先�? |
|------|----------|----------|--------|
| **root** | 云服务商设置 | `passwd root` | 🔴 �? |
| **nuotao**（应用用户） | �? | `passwd nuotao` | 🔴 �? |
| **SSH 密钥** | - | 配置密钥登录，禁用密码登�? | 🔴 �? |

### 1.2 数据�?

| 账号 | 默认密码 | 修改方式 | 优先�? |
|------|----------|----------|--------|
| **postgres** | 无（本地信任�? | `ALTER USER postgres WITH PASSWORD 'xxx';` | 🔴 �? |
| **nuotao** | `REDACTED_DEFAULT_DB` | `ALTER USER nuotao WITH PASSWORD 'xxx';` | 🔴 �? |

### 1.3 缓存

| 账号 | 默认密码 | 修改方式 | 优先�? |
|------|----------|----------|--------|
| **Redis** | 无（无密码） | 修改 `redis.conf` 中的 `requirepass` | 🔴 �? |

### 1.4 应用

| 账号 | 默认密码 | 修改方式 | 优先�? |
|------|----------|----------|--------|
| **admin**（管理员�? | `***REMOVED***` | 通过 API 或数据库修改 | 🔴 �? |
| **JWT 密钥** | �?发默认�?? | 修改 `.env` 中的 `JWT_SECRET_KEY` | 🔴 �? |
| **Webhook Secret** | �?发默认�?? | 修改 `.env` �? WooCommerce 后台 | 🔴 �? |

### 1.5 监控（如已安装）

| 账号 | 默认密码 | 修改方式 | 优先�? |
|------|----------|----------|--------|
| **Grafana admin** | `admin/admin` | 首次登录时修�? | 🟡 �? |
| **Prometheus** | �? | 配置基础认证 | 🟡 �? |
| **Node Exporter** | �? | 配置防火墙限�? | 🟡 �? |

---

## 二�?�自动修改脚�?

使用项目提供的脚本一键修改所有默认密码：

```bash
# 上传脚本到服务器
scp infra/change-default-passwords.sh root@your-server:/root/

# 运行脚本
sudo bash change-default-passwords.sh
```

脚本会自动完成：
1. 修改 PostgreSQL 默认密码
2. 修改 Redis 默认密码
3. 禁用 Redis 危险命令
4. 修改管理员默认密�?
5. �?查其他默认密�?
6. 生成安全报告

---

## 三�?�手动修改步�?

### 3.1 修改 PostgreSQL 密码

```bash
# 登录 PostgreSQL
sudo -u postgres psql

# 修改 postgres 用户密码
ALTER USER postgres WITH PASSWORD 'your-strong-password';

# 修改 nuotao 用户密码
ALTER USER nuotao WITH PASSWORD 'your-strong-password';

# �?�?
\q

# 修改 pg_hba.conf，强制密码认�?
sudo nano /etc/postgresql/16/main/pg_hba.conf

# 将以下行�?
# local   all             all                                     peer
# host    all             all             127.0.0.1/32            trust
# 修改为：
# local   all             all                                     md5
# host    all             all             127.0.0.1/32            md5

# 重启 PostgreSQL
sudo systemctl restart postgresql
```

### 3.2 修改 Redis 密码

```bash
# 编辑 Redis 配置
sudo nano /etc/redis/redis.conf

# 找到并修改（取消注释，设置强密码�?
# requirepass your-strong-password

# 禁用危险命令（添加到配置末尾�?
rename-command FLUSHDB ""
rename-command FLUSHALL ""
rename-command CONFIG ""
rename-command KEYS ""

# 绑定到本地（只允许本地访问）
bind 127.0.0.1

# 重启 Redis
sudo systemctl restart redis-server

# 验证
redis-cli -a your-strong-password ping
# 应返�? PONG
```

### 3.3 修改管理员密�?

```bash
# 方法1：�?�过 API 修改（推荐）
curl -X POST https://your-domain.com/api/v1/auth/change-password \
  -H "Authorization: Bearer your-jwt-token" \
  -H "Content-Type: application/json" \
  -d '{"old_password":"***REMOVED***","new_password":"your-new-strong-password"}'

# 方法2：直接修改数据库
sudo -u postgres psql -d nuotao

# 生成新密码哈希（在应用服务器上执行）
python3 -c "
from app.core.security import get_password_hash
print(get_password_hash('your-new-strong-password'))
"

# 更新数据�?
UPDATE users 
SET hashed_password = 'generated-hash-here'
WHERE username = 'admin';

\q
```

### 3.4 修改 JWT 密钥

```bash
# 生成新密�?
openssl rand -hex 32

# 编辑 .env 文件
sudo nano /opt/nuotao-ai-os/backend/.env

# 修改 JWT_SECRET_KEY
# JWT_SECRET_KEY=your-new-64-char-hex-key

# 重启服务（所有用户会被强制登出）
sudo systemctl restart nuotao-backend
```

---

## 四�?�系统安全加�?

### 4.1 SSH 安全

```bash
# 编辑 SSH 配置
sudo nano /etc/ssh/sshd_config

# 修改以下配置�?
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
ClientAliveInterval 300
ClientAliveCountMax 2

# 重启 SSH
sudo systemctl restart sshd
```

### 4.2 防火墙配�?

```bash
# 查看当前状�??
sudo ufw status verbose

# 默认策略
sudo ufw default deny incoming
sudo ufw default allow outgoing

# 允许必要端口
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 80/tcp      # HTTP
sudo ufw allow 443/tcp     # HTTPS

# 拒绝其他端口（数据库/缓存只允许本地访问）
sudo ufw deny 5432/tcp     # PostgreSQL
sudo ufw deny 6379/tcp     # Redis
sudo ufw deny 8000/tcp     # 后端 API（�?�过 Nginx 代理�?

# 启用防火�?
sudo ufw enable
```

### 4.3 Fail2ban 防暴力破�?

```bash
# 安装
sudo apt-get install -y fail2ban

# 配置 SSH 防护
sudo nano /etc/fail2ban/jail.local

# 添加以下配置�?
[sshd]
enabled = true
port = 22
maxretry = 3
findtime = 300
bantime = 3600

# 启动
sudo systemctl enable fail2ban
sudo systemctl start fail2ban

# 查看状�??
sudo fail2ban-client status sshd
```

### 4.4 自动安全更新

```bash
# 安装
sudo apt-get install -y unattended-upgrades

# 配置
sudo dpkg-reconfigure -plow unattended-upgrades

# 编辑配置
sudo nano /etc/apt/apt.conf.d/50unattended-upgrades

# 启用安全更新
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}";
    "${distro_id}:${distro_codename}-security";
};

# 自动重启（如�?�?
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "02:00";
```

---

## 五�?�应用安全加�?

### 5.1 文件权限

```bash
# 应用目录权限
sudo chown -R nuotao:nuotao /opt/nuotao-ai-os
sudo chmod -R 755 /opt/nuotao-ai-os
sudo chmod 600 /opt/nuotao-ai-os/backend/.env

# 日志目录
sudo chown -R nuotao:nuotao /var/log/nuotao
sudo chmod 750 /var/log/nuotao

# 备份目录
sudo chown -R nuotao:nuotao /var/backups/nuotao
sudo chmod 750 /var/backups/nuotao
```

### 5.2 Nginx 安全�?

�? Nginx 配置中添加安全头�?

```nginx
# 安全�?
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self' https:; frame-ancestors 'self';" always;

# 隐藏 Nginx 版本
server_tokens off;

# 限制请求大小
client_max_body_size 10m;

# 限制请求速率
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
```

### 5.3 API 安全

```bash
# 编辑 .env 文件
sudo nano /opt/nuotao-ai-os/backend/.env

# 启用速率限制
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS_PER_MINUTE=60

# 启用 PII 加密
PII_ENCRYPTION_ENABLED=true

# 配置 CORS（只允许可信域名�?
CORS_ORIGINS=https://nuotaooutdoor.com,https://www.nuotaooutdoor.com
```

---

## 六�?�监控与审计

### 6.1 日志监控

```bash
# 查看登录日志
sudo last -n 20
sudo cat /var/log/auth.log | grep "Failed password"

# 查看 Nginx 访问日志
sudo tail -f /var/log/nginx/access.log

# 查看应用日志
sudo journalctl -u nuotao-backend -f
```

### 6.2 定期审计

建议每月执行以下审计�?

- [ ] �?查系统用户列表，删除未使用账�?
- [ ] �?�? SSH 登录记录，发现异常登�?
- [ ] �?查数据库用户权限
- [ ] �?查文件权限是否正�?
- [ ] �?查防火墙规则
- [ ] �?�? SSL 证书有效�?
- [ ] �?查备份是否正�?
- [ ] �?查磁盘空间使�?
- [ ] 更新系统和依赖包

---

## 七�?�安全检查清�?

部署完成后，逐项验证�?

### 系统安全
- [ ] root 密码已修�?
- [ ] SSH 密钥登录已配置，密码登录已禁�?
- [ ] root SSH 登录已禁�?
- [ ] 防火墙已配置（仅�?�? 22/80/443�?
- [ ] Fail2ban 已安装并运行
- [ ] 自动安全更新已配�?
- [ ] 系统时间已同步（NTP�?

### 数据库安�?
- [ ] postgres 用户密码已修�?
- [ ] nuotao 用户密码已修�?
- [ ] 数据库只允许本地访问
- [ ] pg_hba.conf 已配置为 md5 认证
- [ ] 数据库备份已配置

### 缓存安全
- [ ] Redis 密码已设�?
- [ ] Redis 只绑定到 127.0.0.1
- [ ] Redis 危险命令已禁�?
- [ ] Redis 数据持久化已配置

### 应用安全
- [ ] 管理员默认密码已修改
- [ ] JWT 密钥已修改（�?64字符�?
- [ ] WooCommerce Webhook Secret 已修�?
- [ ] �?有第三方 API Key 已更�?
- [ ] .env 文件权限�? 600
- [ ] .env 文件未提交到 Git
- [ ] CORS 已配置为可信域名
- [ ] API 速率限制已启�?
- [ ] PII 加密已启�?

### Web 安全
- [ ] SSL 证书已配置并生效
- [ ] HTTP 已重定向�? HTTPS
- [ ] HSTS 头已配置
- [ ] 其他安全头已配置（X-Frame-Options 等）
- [ ] Nginx 版本已隐�?
- [ ] 请求大小限制已配�?

### 监控与备�?
- [ ] 系统监控已配�?
- [ ] 告警通知已配置（飞书/邮件�?
- [ ] 数据库自动备份已配置
- [ ] 备份已验证可恢复
- [ ] 日志已配置轮�?
- [ ] 磁盘空间监控已配�?

---

**文档版本**：v1.0
**�?后更�?**�?2026-09-02
