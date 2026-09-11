# Nuotao AI OS - 生产环境密钥配置指南

## 一、密钥清单

部署到生产环境前，必须配置以下密钥：

### 1.1 认证与安全密钥

| 密钥名称 | 长度要求 | 用途 | 生成方式 |
|----------|----------|------|----------|
| **JWT_SECRET_KEY** | ≥64字符 | JWT Token 签名验证 | `openssl rand -hex 32` |
| **SESSION_SECRET** | ≥64字符 | 会话加密 | `openssl rand -hex 32` |
| **API_SIGNING_SECRET** | ≥64字符 | API 请求签名 | `openssl rand -hex 32` |
| **ENCRYPTION_KEY** | ≥64字符 | PII 数据加密 | `openssl rand -hex 32` |

### 1.2 数据库密钥

| 密钥名称 | 长度要求 | 用途 |
|----------|----------|------|
| **DB_PASSWORD** | ≥32字符 | PostgreSQL 数据库密码 |
| **DATABASE_URL** | - | 完整数据库连接字符串 |

### 1.3 Redis 密钥

| 密钥名称 | 长度要求 | 用途 |
|----------|----------|------|
| **REDIS_PASSWORD** | ≥32字符 | Redis 访问密码 |
| **REDIS_URL** | - | 完整 Redis 连接字符串 |

### 1.4 第三方服务密钥

| 密钥名称 | 来源 | 用途 |
|----------|------|------|
| **WOOCOMMERCE_CONSUMER_KEY** | WooCommerce 后台 | 店铺 API 访问 |
| **WOOCOMMERCE_CONSUMER_SECRET** | WooCommerce 后台 | 店铺 API 密钥 |
| **WOOCOMMERCE_WEBHOOK_SECRET** | 自定义 | Webhook 签名验证 |
| **LLM_API_KEY** | AI 模型服务商 | AI Agent 调用 |
| **FEISHU_WEBHOOK_URL** | 飞书开放平台 | 告警通知 |
| **SMTP_PASSWORD** | 邮件服务商 | 邮件发送 |

### 1.5 管理员账号

| 密钥名称 | 长度要求 | 用途 |
|----------|----------|------|
| **ADMIN_USERNAME** | - | 管理员用户名 |
| **ADMIN_PASSWORD** | ≥16字符 | 管理员初始密码 |
| **ADMIN_EMAIL** | - | 管理员邮箱 |

---

## 二、密钥生成

### 2.1 自动生成（推荐）

使用项目提供的脚本一键生成所有密钥：

```bash
# 生成并显示在终端
bash infra/generate-secrets.sh

# 生成并保存到文件
bash infra/generate-secrets.sh --output .env.production
```

### 2.2 手动生成

```bash
# JWT 密钥（64字符十六进制）
openssl rand -hex 32

# 强密码（32字符）
openssl rand -base64 24 | tr -d '\n'

# UUID
cat /proc/sys/kernel/random/uuid

# 或使用 Python
python3 -c "import secrets; print(secrets.token_hex(32))"
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 2.3 密码强度要求

生产环境密码必须满足：

- [ ] 长度 ≥ 16 字符（推荐 32 字符）
- [ ] 包含大写字母 (A-Z)
- [ ] 包含小写字母 (a-z)
- [ ] 包含数字 (0-9)
- [ ] 包含特殊字符 (!@#$%^&*等)
- [ ] 不包含常见单词或模式
- [ ] 不与其他服务密码重复

---

## 三、密钥配置步骤

### 3.1 修改数据库密码

```bash
# 登录 PostgreSQL
sudo -u postgres psql

# 修改用户密码
ALTER USER nuotao WITH PASSWORD 'your-strong-password';

# 验证
\q

# 更新 pg_hba.conf（如需）
sudo nano /etc/postgresql/16/main/pg_hba.conf

# 重启 PostgreSQL
sudo systemctl restart postgresql
```

### 3.2 修改 Redis 密码

```bash
# 编辑 Redis 配置
sudo nano /etc/redis/redis.conf

# 找到并修改（取消注释，设置强密码）
# requirepass your-strong-password

# 重启 Redis
sudo systemctl restart redis-server

# 验证
redis-cli -a your-strong-password ping
# 应返回 PONG
```

### 3.3 配置环境变量

```bash
# 编辑生产环境配置
sudo nano /opt/nuotao-ai-os/backend/.env

# 必须修改以下配置：
# DATABASE_URL=postgresql+asyncpg://nuotao:your-db-password@localhost:5432/nuotao
# REDIS_URL=redis://:your-redis-password@localhost:6379/0
# JWT_SECRET_KEY=your-jwt-secret
# WOOCOMMERCE_WEBHOOK_SECRET=your-webhook-secret
# LLM_API_KEY=your-llm-api-key
# FEISHU_WEBHOOK_URL=your-feishu-webhook

# 设置文件权限（仅所有者可读写）
sudo chmod 600 /opt/nuotao-ai-os/backend/.env
sudo chown nuotao:nuotao /opt/nuotao-ai-os/backend/.env

# 重启服务
sudo systemctl restart nuotao-backend
```

### 3.4 修改 WooCommerce Webhook Secret

1. 登录 WooCommerce 后台
2. 进入 **WooCommerce → 设置 → 高级 → Webhooks**
3. 编辑对应的 Webhook
4. 修改 **Secret** 字段为新生成的密钥
5. 保存更改

### 3.5 修改管理员密码

```bash
# 方法1：通过 API 修改
curl -X POST https://your-domain.com/api/v1/auth/change-password \
  -H "Authorization: Bearer your-token" \
  -H "Content-Type: application/json" \
  -d '{"old_password":"Admin@2026","new_password":"your-new-strong-password"}'

# 方法2：直接修改数据库
sudo -u postgres psql -d nuotao -c "
UPDATE users 
SET hashed_password = '\$2b\$12\$...' 
WHERE username = 'admin';
"
```

---

## 四、密钥管理最佳实践

### 4.1 存储安全

| 方式 | 推荐度 | 说明 |
|------|--------|------|
| **密码管理器** | ⭐⭐⭐⭐⭐ | 1Password、Bitwarden、KeePass |
| **云密钥管理** | ⭐⭐⭐⭐⭐ | AWS Secrets Manager、阿里云 KMS |
| **环境变量文件** | ⭐⭐⭐⭐ | .env 文件，权限 600，不提交 Git |
| **配置文件** | ⭐⭐⭐ | 单独配置文件，权限 600 |
| **代码硬编码** | ⭐ | ❌ 绝对禁止 |
| **明文文档** | ⭐ | ❌ 绝对禁止 |

### 4.2 .gitignore 配置

确保以下文件不被提交到 Git：

```gitignore
# 环境变量
.env
.env.local
.env.production
.env.staging
*.env

# 密钥文件
secrets/
keys/
*.pem
*.key
*.p12
*.pfx

# 配置文件（含密钥）
config/secrets.json
config/database.yml
```

### 4.3 密钥轮换策略

| 密钥类型 | 轮换频率 | 说明 |
|----------|----------|------|
| JWT_SECRET_KEY | 每 90 天 | 轮换后所有用户需重新登录 |
| 数据库密码 | 每 90 天 | 需要同时更新应用配置 |
| Redis 密码 | 每 90 天 | 需要同时更新应用配置 |
| API 密钥 | 每 180 天 | WooCommerce、LLM 等 |
| 管理员密码 | 每 90 天 | 强制修改 |
| Webhook Secret | 每 180 天 | 需要同时更新 WooCommerce |

### 4.4 密钥泄露应急响应

如果怀疑密钥泄露：

1. **立即轮换**：生成新密钥并更新所有配置
2. **撤销旧密钥**：在第三方服务后台撤销旧 API Key
3. **审计日志**：检查是否有异常访问或操作
4. **通知相关方**：通知团队成员和客户
5. **调查原因**：找出泄露原因并修复
6. **记录事件**：记录事件经过和处理措施

---

## 五、密钥验证清单

部署完成后，逐项验证：

- [ ] JWT_SECRET_KEY 已配置（≥64字符）
- [ ] 数据库密码已修改（≥32字符）
- [ ] Redis 密码已修改（≥32字符）
- [ ] WooCommerce Consumer Key/Secret 已配置
- [ ] WooCommerce Webhook Secret 已配置
- [ ] LLM API Key 已配置
- [ ] 飞书 Webhook URL 已配置
- [ ] SMTP 密码已配置
- [ ] 管理员默认密码已修改
- [ ] .env 文件权限为 600
- [ ] .env 文件未提交到 Git
- [ ] 所有密钥已保存到密码管理器
- [ ] 密钥轮换计划已制定

---

## 六、常见问题

### Q: 忘记密钥怎么办？
A: 
1. 检查密码管理器是否已保存
2. 检查服务器上的 .env 文件
3. 如果都找不到，重新生成密钥并更新所有配置
4. 数据库密码可以通过 root 权限重置

### Q: 可以使用同一个密钥用于多个服务吗？
A: 不建议。不同服务应使用不同密钥，这样即使一个密钥泄露，其他服务仍然安全。

### Q: 密钥需要多复杂？
A: 对于机器生成的随机密钥，32 字符（256位熵）已经足够安全。对于人工设置的密码，建议 16 字符以上并包含多种字符类型。

### Q: 如何安全地分享密钥给团队成员？
A: 
1. 使用密码管理器的共享功能
2. 使用加密通信工具（如 Signal）
3. 不要通过邮件、微信、钉钉等发送完整密钥
4. 可以分开发送（如密码前半部分通过邮件，后半部分通过电话）

---

**文档版本**：v1.0
**最后更新**：2026-09-02
