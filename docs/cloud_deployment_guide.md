# Nuotao AI OS - 云服务器选择与部署指南

## 一、云服务商推荐

### 1.1 国内云服务商（推荐国内用户）

| 服务商 | 最低配置 | 月费（约） | 优势 | 劣势 |
|--------|----------|------------|------|------|
| **阿里云** | 2核4G 40G SSD | ¥60-100 | 稳定、生态完善、国内访问快 | 需备案、价格较高 |
| **腾讯云** | 2核4G 50G SSD | ¥50-90 | 性价比高、轻量应用服务器 | 需备案、生态略逊 |
| **华为云** | 2核4G 40G SSD | ¥60-100 | 企业级稳定、安全合规 | 需备案、文档较少 |

### 1.2 海外云服务商（推荐海外用户/无需备案）

| 服务商 | 最低配置 | 月费（约） | 优势 | 劣势 |
|--------|----------|------------|------|------|
| **Vultr** | 1核1G 25G SSD | $5-6 | 按小时计费、全球节点多、支持支付宝 | 国内访问可能较慢 |
| **DigitalOcean** | 1核1G 25G SSD | $5-6 | 简单易用、文档完善 | 国内访问较慢、不支持支付宝 |
| **AWS Lightsail** | 1核2G 40G SSD | $5-10 | 稳定、可升级到EC2 | 配置复杂、超额收费 |
| **Hetzner** | 2核4G 40G SSD | €4-6 | 性价比极高、欧洲节点 | 仅欧洲节点、需信用卡 |

### 1.3 免费套餐（适合测试/小流量）

| 服务商 | 免费额度 | 限制 |
|--------|----------|------|
| **Oracle Cloud** | 4核24G 永久免费 | 需信用卡验证、注册严格（之前被拒） |
| **AWS Free Tier** | 1核1G 12个月 | 需信用卡、超额收费 |
| **Google Cloud** | $300 额度 90天 | 需信用卡、地区限制 |
| **阿里云免费试用** | 3个月 2核2G | 新用户专享、需实名 |

---

## 二、服务器配置建议

### 2.1 最低配置（测试/小流量）

| 组件 | 配置 |
|------|------|
| CPU | 1核 |
| 内存 | 2GB |
| 硬盘 | 25GB SSD |
| 带宽 | 1Mbps |
| 系统 | Ubuntu 22.04 LTS |

**适用场景**：开发测试、日访问量 < 1000

### 2.2 推荐配置（生产环境）

| 组件 | 配置 |
|------|------|
| CPU | 2核 |
| 内存 | 4GB |
| 硬盘 | 50GB SSD |
| 带宽 | 3-5Mbps |
| 系统 | Ubuntu 22.04 LTS |

**适用场景**：日访问量 1000-10000，中小型电商

### 2.3 高性能配置（大流量）

| 组件 | 配置 |
|------|------|
| CPU | 4核 |
| 内存 | 8GB |
| 硬盘 | 100GB SSD |
| 带宽 | 10Mbps+ |
| 系统 | Ubuntu 22.04 LTS |

**适用场景**：日访问量 > 10000，大型促销活动

---

## 三、部署步骤

### 3.1 购买服务器

1. 选择云服务商，注册账号
2. 选择配置（推荐 2核4G 50G SSD）
3. 选择系统（Ubuntu 22.04 LTS）
4. 设置 SSH 密钥或 root 密码
5. 购买并等待服务器启动

### 3.2 域名解析（如使用域名）

1. 在域名服务商处添加 A 记录：
   - `@` → 服务器 IP
   - `www` → 服务器 IP
2. 等待 DNS 生效（通常 5-30 分钟）

### 3.3 服务器初始化

```bash
# SSH 登录服务器
ssh root@your-server-ip

# 上传部署脚本（或直接复制内容）
# 方法1: 使用 scp
scp infra/server-setup.sh root@your-server-ip:/root/
scp infra/deploy-production.sh root@your-server-ip:/root/

# 方法2: 直接在服务器上创建文件
nano server-setup.sh
# 粘贴内容，保存退出

# 运行服务器初始化脚本
chmod +x server-setup.sh
sudo bash server-setup.sh
```

### 3.4 应用部署

```bash
# 编辑部署脚本，修改 GIT_REPO 为实际仓库地址
nano deploy-production.sh

# 运行部署脚本
chmod +x deploy-production.sh
sudo bash deploy-production.sh
```

### 3.5 配置生产环境

```bash
# 编辑环境变量
sudo nano /opt/nuotao-ai-os/backend/.env

# 必须修改的配置：
# - DATABASE_URL（数据库密码）
# - REDIS_URL（Redis 密码）
# - JWT_SECRET_KEY（强随机密钥）
# - WOOCOMMERCE_*（店铺密钥）
# - LLM_API_KEY（AI 模型密钥）
# - FEISHU_WEBHOOK_URL（飞书通知）

# 重启服务
sudo systemctl restart nuotao-backend
```

### 3.6 SSL 证书配置

```bash
# 使用 Certbot 申请免费 SSL 证书
sudo certbot --nginx -d nuotaooutdoor.com -d www.nuotaooutdoor.com

# 证书自动续期（Certbox 会自动配置）
sudo certbot renew --dry-run
```

### 3.7 验证部署

```bash
# 检查服务状态
sudo systemctl status nuotao-backend
sudo systemctl status nginx
sudo systemctl status postgresql
sudo systemctl status redis-server

# 检查端口
sudo netstat -tlnp | grep -E '80|443|8000|5432|6379'

# 查看日志
sudo journalctl -u nuotao-backend -f
sudo tail -f /var/log/nginx/access.log

# 测试 API
curl http://localhost:8000/health
curl https://your-domain.com/api/v1/health
```

---

## 四、安全配置清单

部署完成后，必须完成以下安全配置：

- [ ] 修改 PostgreSQL 默认密码
- [ ] 修改 Redis 默认密码
- [ ] 修改管理员账号默认密码（admin/Admin@2026）
- [ ] 配置 JWT 强随机密钥
- [ ] 配置 SSH 密钥登录，禁用密码登录
- [ ] 配置防火墙（仅开放 22/80/443）
- [ ] 配置 Fail2ban 防暴力破解
- [ ] 配置数据库自动备份
- [ ] 配置监控告警
- [ ] 配置 SSL 证书自动续期
- [ ] 配置系统自动安全更新
- [ ] 定期更新系统和依赖包

---

## 五、成本估算

### 5.1 服务器成本

| 配置 | 月费（国内） | 月费（海外） |
|------|--------------|--------------|
| 最低（1核2G） | ¥40-60 | $5-6 |
| 推荐（2核4G） | ¥60-100 | $10-15 |
| 高性能（4核8G） | ¥150-250 | $25-40 |

### 5.2 其他成本

| 项目 | 费用 |
|------|------|
| 域名 | ¥50-100/年 |
| SSL 证书 | 免费（Let's Encrypt） |
| CDN | ¥0-50/月（按需） |
| 对象存储 | ¥0-20/月（按需） |
| LLM API | $10-50/月（按需） |
| 邮件服务 | $0-10/月（按需） |

### 5.3 月度总成本估算

| 规模 | 服务器 | 其他 | 总计 |
|------|--------|------|------|
| 起步 | ¥60 | ¥50 | **¥110/月** |
| 成长 | ¥100 | ¥100 | **¥200/月** |
| 成熟 | ¥200 | ¥200 | **¥400/月** |

---

## 六、常见问题

### Q: 国内服务器必须备案吗？
A: 使用国内服务器 + 域名访问网站，必须完成 ICP 备案（约 7-20 个工作日）。使用海外服务器无需备案。

### Q: 可以先在本地运行，后期再部署到云服务器吗？
A: 可以。项目支持本地开发和生产部署两种模式。准备好后运行部署脚本即可上线。

### Q: 如何从本地迁移到云服务器？
A: 1) 在云服务器运行部署脚本；2) 导出本地数据库；3) 导入到云服务器；4) 修改配置指向云服务器。

### Q: 服务器被攻击了怎么办？
A: 1) 立即断开网络或关闭服务器；2) 查看日志分析攻击来源；3) 恢复备份；4) 加强安全配置；5) 考虑使用 CDN 和 WAF。

---

**文档版本**：v1.0
**最后更新**：2026-09-02
