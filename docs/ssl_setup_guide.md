# Nuotao AI OS - 域名解析与 SSL 配置指南

## 一、域名准备

### 1.1 域名注册

推荐域名注册商：

| 注册商 | 优势 | 价格（约） |
|--------|------|------------|
| **阿里云万网** | 国内访问快、备案方便 | ¥50-100/年 |
| **腾讯云DNSPod** | 解析稳定、管理方便 | ¥50-80/年 |
| **Namecheap** | 价格便宜、隐私保护 | $8-15/年 |
| **Cloudflare** | 免费DNS、CDN加速 | $10-20/年 |

### 1.2 域名备案（国内服务器必须）

如果使用国内云服务器（阿里云/腾讯云/华为云），必须完成 ICP 备案：

1. 登录云服务商备案系统
2. 填写主体信息（个人/企业）
3. 填写网站信息
4. 上传证件材料
5. 等待审核（约 7-20 个工作日）
6. 备案成功后获取备案号

**备案期间网站无法访问**，建议提前备案。

---

## 二、域名解析配置

### 2.1 A 记录配置（最常用）

将域名指向服务器 IP 地址：

| 记录类型 | 主机记录 | 记录值 | TTL |
|----------|----------|--------|-----|
| A | @ | 服务器公网IP | 600 |
| A | www | 服务器公网IP | 600 |

**说明**：
- `@` 表示主域名（如 nuotaooutdoor.com）
- `www` 表示带 www 的域名（如 www.nuotaooutdoor.com）
- TTL（生存时间）建议设置为 600 秒（10分钟），便于快速切换

### 2.2 CNAME 记录配置（用于 CDN）

如果使用 CDN 服务，需要配置 CNAME 记录：

| 记录类型 | 主机记录 | 记录值 | TTL |
|----------|----------|--------|-----|
| CNAME | @ | cdn-provider-domain.com | 600 |
| CNAME | www | cdn-provider-domain.com | 600 |

### 2.3 MX 记录配置（企业邮箱）

如果使用企业邮箱，需要配置 MX 记录：

| 记录类型 | 主机记录 | 记录值 | 优先级 | TTL |
|----------|----------|--------|--------|-----|
| MX | @ | mx1.qq.com | 5 | 600 |
| MX | @ | mx2.qq.com | 10 | 600 |

### 2.4 TXT 记录配置（验证/SPF）

用于域名验证和邮件 SPF 配置：

| 记录类型 | 主机记录 | 记录值 | TTL |
|----------|----------|--------|-----|
| TXT | @ | v=spf1 include:spf.mail.qq.com ~all | 600 |
| TXT | _dmarc | v=DMARC1; p=none; rua=mailto:admin@domain.com | 600 |

---

## 三、解析验证

### 3.1 检查解析是否生效

```bash
# 检查 A 记录
dig nuotaooutdoor.com A +short
nslookup nuotaooutdoor.com

# 检查 CNAME 记录
dig www.nuotaooutdoor.com CNAME +short

# 检查 MX 记录
dig nuotaooutdoor.com MX +short

# 检查所有记录
dig nuotaooutdoor.com ANY
```

### 3.2 在线工具

- [DNS Checker](https://dnschecker.org/) - 全球 DNS 解析检查
- [What's My DNS](https://whatsmydns.net/) - DNS 传播检查
- [MX Toolbox](https://mxtoolbox.com/) - 邮件记录检查

### 3.3 解析生效时间

- 新增解析：通常 1-5 分钟生效
- 修改解析：取决于 TTL 设置（600秒 = 10分钟）
- 全球传播：最多 24-48 小时（通常 1-2 小时）

---

## 四、SSL 证书配置

### 4.1 证书类型选择

| 证书类型 | 验证方式 | 有效期 | 价格 | 适用场景 |
|----------|----------|--------|------|----------|
| **DV（域名验证）** | 域名所有权 | 90天 | 免费 | 个人网站、测试 |
| **OV（组织验证）** | 企业资质 | 1-2年 | ¥500-2000/年 | 企业官网 |
| **EV（扩展验证）** | 严格审核 | 1-2年 | ¥2000-10000/年 | 金融、电商 |

**推荐**：使用 Let's Encrypt 免费 DV 证书，支持自动续期。

### 4.2 自动配置（推荐）

使用项目提供的脚本自动配置：

```bash
# 上传脚本到服务器
scp infra/setup-ssl.sh root@your-server:/root/

# 运行脚本
sudo bash setup-ssl.sh nuotaooutdoor.com
```

脚本会自动完成：
1. 检查域名解析
2. 安装 Certbot
3. 申请 SSL 证书
4. 配置 Nginx HTTPS
5. 设置自动续期
6. 验证 SSL 配置

### 4.3 手动配置

#### 步骤 1：安装 Certbot

```bash
sudo apt-get update
sudo apt-get install -y certbot python3-certbot-nginx
```

#### 步骤 2：申请证书

```bash
# 单域名
sudo certbot --nginx -d nuotaooutdoor.com

# 多域名（主域名 + www）
sudo certbot --nginx -d nuotaooutdoor.com -d www.nuotaooutdoor.com

# 非交互式（适合脚本）
sudo certbot --nginx \
    -d nuotaooutdoor.com -d www.nuotaooutdoor.com \
    --email admin@nuotaooutdoor.com \
    --agree-tos --no-eff-email \
    --redirect --non-interactive
```

#### 步骤 3：验证证书

```bash
# 查看证书信息
sudo certbot certificates

# 测试 HTTPS 访问
curl -I https://nuotaooutdoor.com

# 检查 SSL 等级
echo | openssl s_client -connect nuotaooutdoor.com:443 -servername nuotaooutdoor.com 2>/dev/null | openssl x509 -noout -subject -issuer -dates
```

### 4.4 自动续期

Let's Encrypt 证书有效期 90 天，需要自动续期：

```bash
# 测试续期（不会实际续期）
sudo certbot renew --dry-run

# 手动续期
sudo certbot renew

# 查看续期定时器状态
sudo systemctl status certbot.timer

# 续期后自动重启 Nginx（已配置钩子）
cat /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
```

---

## 五、Nginx HTTPS 配置

### 5.1 完整配置示例

```nginx
# HTTP 重定向到 HTTPS
server {
    listen 80;
    server_name nuotaooutdoor.com www.nuotaooutdoor.com;
    return 301 https://$server_name$request_uri;
}

# HTTPS 主配置
server {
    listen 443 ssl http2;
    server_name nuotaooutdoor.com www.nuotaooutdoor.com;

    # SSL 证书
    ssl_certificate /etc/letsencrypt/live/nuotaooutdoor.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/nuotaooutdoor.com/privkey.pem;

    # SSL 安全配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # 安全头
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # 前端静态文件
    root /opt/nuotao-ai-os/frontend/dist;
    index index.html;

    # API 反向代理
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # SPA 路由
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

### 5.2 安全头说明

| 头名称 | 作用 | 推荐值 |
|--------|------|--------|
| **Strict-Transport-Security** | 强制使用 HTTPS | max-age=31536000; includeSubDomains |
| **X-Frame-Options** | 防止点击劫持 | SAMEORIGIN |
| **X-Content-Type-Options** | 防止 MIME 类型嗅探 | nosniff |
| **X-XSS-Protection** | 启用 XSS 过滤 | 1; mode=block |
| **Referrer-Policy** | 控制 Referrer 信息 | strict-origin-when-cross-origin |

---

## 六、SSL 检测与优化

### 6.1 在线检测工具

- [SSL Labs Server Test](https://www.ssllabs.com/ssltest/) - 全面 SSL 安全评级
- [SSL Shopper](https://www.sslshopper.com/ssl-checker.html) - 证书信息检查
- [Mozilla SSL Config Generator](https://ssl-config.mozilla.org/) - SSL 配置生成器

### 6.2 优化建议

1. **启用 HTTP/2**：提升加载速度
2. **启用 OCSP Stapling**：减少证书验证时间
3. **配置 HSTS**：强制 HTTPS，防止降级攻击
4. **使用 TLS 1.3**：最新协议，更快更安全
5. **定期更新**：保持 OpenSSL 和 Nginx 最新版本

---

## 七、常见问题

### Q: 证书申请失败怎么办？
A: 检查以下几点：
1. 域名解析是否生效（`dig your-domain.com`）
2. 80 端口是否开放（`sudo ufw allow 80`）
3. Nginx 是否运行（`sudo systemctl status nginx`）
4. 防火墙是否拦截 Certbot 验证请求

### Q: 证书到期前会提醒吗？
A: Let's Encrypt 会在到期前 20 天发送邮件提醒。同时 Certbot 会自动续期（每天检查两次）。

### Q: 可以使用通配符证书吗？
A: 可以。Let's Encrypt 支持通配符证书（如 *.domain.com），但需要使用 DNS 验证：
```bash
sudo certbot certonly --manual --preferred-challenges dns -d "*.domain.com" -d domain.com
```

### Q: 多个域名可以用一个证书吗？
A: 可以。申请时添加多个 -d 参数：
```bash
sudo certbot --nginx -d domain1.com -d domain2.com -d domain3.com
```

---

**文档版本**：v1.0
**最后更新**：2026-09-02
