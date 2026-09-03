# Oracle Cloud 免费服务器注册与部署指南

> 本文档指导你注册 Oracle Cloud 永久免费账户，并部署 Nuotao AI OS 项目。

---

## 📋 目录

1. [注册前准备](#1-注册前准备)
2. [注册 Oracle Cloud 账户](#2-注册-oracle-cloud-账户)
3. [创建免费计算实例](#3-创建免费计算实例)
4. [配置网络和防火墙](#4-配置网络和防火墙)
5. [连接到服务器](#5-连接到服务器)
6. [部署 Nuotao AI OS](#6-部署-nuotao-ai-os)
7. [常见问题解答](#7-常见问题解答)

---

## 1. 注册前准备

### 1.1 需要准备的材料

| 材料 | 说明 | 备注 |
|---|---|---|
| 邮箱 | 建议使用 Gmail/Outlook | 不建议使用 QQ/163 邮箱 |
| 信用卡 | Visa/Mastercard | 仅验证，不扣费（可能预授权 $1） |
| 手机号 | 用于验证 | 支持中国手机号 |
| 地址 | 个人地址 | 建议填写真实地址 |
| SSH 密钥 | 用于登录服务器 | 注册后创建 |

### 1.2 注意事项

- ⚠️ **Oracle Cloud 注册审核较严格**，部分用户可能被拒绝
- ⚠️ 建议使用**美国/香港地址**注册，成功率更高
- ⚠️ 信用卡需要支持**国际支付**（Visa/Mastercard）
- ⚠️ 注册时可能需要**视频验证**（人脸验证）
- ⚠️ 一个人/一张信用卡只能注册一个账户

### 1.3 免费资源额度

| 资源 | 规格 | 数量 |
|---|---|---|
| ARM 计算实例 | Ampere A1，4核24G | 1台（可拆分） |
| x86 计算实例 | AMD VM.Standard.E2.1.Micro | 2台 |
| 块存储 | 200GB | - |
| 对象存储 | 10GB | - |
| 出站流量 | 10TB/月 | - |

---

## 2. 注册 Oracle Cloud 账户

### 2.1 访问注册页面

1. 打开浏览器，访问：https://signup.cloud.oracle.com/
2. 你会看到 Oracle Cloud Free Tier 注册页面

### 2.2 填写账户信息

**第一步：账户信息**

1. **Country/Territory**: 选择 `United States`（或 Hong Kong）
2. **First Name**: 你的名字（拼音，如 `Yongshun`）
3. **Last Name**: 你的姓（拼音，如 `Fan`）
4. **Email**: 你的邮箱（建议 Gmail）
5. **Password**: 设置密码（至少 12 位，包含大小写字母、数字、特殊字符）
6. **Company Name**: 可以填写个人名字或 `Personal`
7. **Cloud Account Name**: 自定义账户名（如 `nuotao-ai-os`）
8. **Home Region**: 选择 `US West (San Jose)` 或 `Singapore`

点击 **Continue**

### 2.3 验证邮箱

1. Oracle 会向你的邮箱发送验证邮件
2. 打开邮箱，找到来自 Oracle 的邮件
3. 点击邮件中的 **Verify Email** 按钮
4. 验证成功后会自动跳转到下一步

### 2.4 填写个人信息

**第二步：个人信息**

1. **Address**: 填写地址（建议美国地址，可使用随机地址生成器）
2. **City**: 城市（如 `San Jose`）
3. **State/Province**: 州（如 `California`）
4. **Postal Code**: 邮编（如 `95110`）
5. **Phone Number**: 手机号（中国手机号 +86）
6. **Date of Birth**: 出生日期

点击 **Continue**

### 2.5 手机验证

1. 输入你的手机号
2. 点击 **Send Code**
3. 输入收到的短信验证码
4. 点击 **Verify**

### 2.6 信用卡验证

**第三步：支付验证**

1. **Card Type**: 选择 Visa 或 Mastercard
2. **Name on Card**: 持卡人姓名（拼音）
3. **Card Number**: 信用卡号
4. **Expiration Date**: 有效期
5. **CVV**: 安全码

> 💡 Oracle 会预授权 $1（或等值货币）用于验证，随后会退款，不会实际扣费。

点击 **Continue**

### 2.7 完成注册

1. 阅读并同意服务条款
2. 点击 **Complete Registration**
3. 等待审核（通常几分钟到几小时）
4. 审核通过后会收到邮件通知

---

## 3. 创建免费计算实例

### 3.1 登录控制台

1. 访问 https://www.oracle.com/cloud/sign-in.html
2. 输入你的 Cloud Account Name（如 `nuotao-ai-os`）
3. 输入邮箱和密码登录
4. 进入 Oracle Cloud Console

### 3.2 创建 SSH 密钥

**在本地电脑生成 SSH 密钥（Windows）**

1. 打开 PowerShell
2. 运行以下命令：
```powershell
ssh-keygen -t ed25519 -C "oracle-cloud"
```
3. 按回车使用默认路径
4. 可以设置密码（也可以留空）
5. 密钥生成在 `C:\Users\你的用户名\.ssh\` 目录
   - `id_ed25519` - 私钥（保密，不要泄露）
   - `id_ed25519.pub` - 公钥（上传到服务器）

### 3.3 创建计算实例

1. 在 Console 左侧菜单，点击 **Compute** → **Instances**
2. 点击 **Create instance**
3. 填写实例信息：

**基本信息**
- **Name**: `nuotao-ai-os-server`
- **Create in compartment**: 保持默认

**放置**
- **Availability domain**: 选择任意一个（AD-1/AD-2/AD-3）

**安全**
- **Image**: 保持默认（Oracle Linux 或 Ubuntu）
- **Shape**: 点击 **Change shape**
  - 选择 **Ampere**（ARM 架构，免费额度大）
  - 选择 **VM.Standard.A1.Flex**
  - **Number of OCPUs**: 4（免费额度内）
  - **Amount of memory (GB)**: 24（免费额度内）
  - 点击 **Select shape**

> 💡 如果 Ampere 不可用，可以选择 **AMD** → **VM.Standard.E2.1.Micro**（1核1G，免费）

**网络**
- **Virtual cloud network**: 保持默认（Create new virtual cloud network）
- **Subnet**: 保持默认（Create new public subnet）
- **Public IP address**: 选择 **Assign a public IPv4 address**

**SSH 密钥**
- 选择 **Upload public key files (.pub)**
- 点击 **select files**，上传你刚才生成的 `id_ed25519.pub`

**引导卷**
- 保持默认（46.6GB，在免费额度内）

4. 点击 **Create**
5. 等待实例创建完成（状态变为 `RUNNING`）

### 3.4 记录服务器信息

实例创建完成后，记录以下信息：

| 信息 | 示例 |
|---|---|
| 公共 IP 地址 | `152.67.xxx.xxx` |
| 用户名 | `ubuntu`（Ubuntu）或 `opc`（Oracle Linux） |
| SSH 私钥路径 | `C:\Users\你的用户名\.ssh\id_ed25519` |
| 实例 OCID | `ocid1.instance.oc1...` |

---

## 4. 配置网络和防火墙

### 4.1 配置安全列表（开放端口）

1. 在实例详情页，点击 **Subnet** 链接
2. 点击 **Security Lists** → **Default Security List**
3. 点击 **Add Ingress Rules**
4. 添加以下规则：

**规则 1：SSH（22端口）**
- **Source CIDR**: `0.0.0.0/0`
- **IP Protocol**: `TCP`
- **Destination Port Range**: `22`

**规则 2：HTTP（80端口）**
- **Source CIDR**: `0.0.0.0/0`
- **IP Protocol**: `TCP`
- **Destination Port Range**: `80`

**规则 3：HTTPS（443端口）**
- **Source CIDR**: `0.0.0.0/0`
- **IP Protocol**: `TCP`
- **Destination Port Range**: `443`

5. 点击 **Add Ingress Rules**

### 4.2 配置服务器防火墙（Ubuntu）

连接到服务器后，运行以下命令：

```bash
# 允许 SSH
sudo ufw allow 22/tcp

# 允许 HTTP
sudo ufw allow 80/tcp

# 允许 HTTPS
sudo ufw allow 443/tcp

# 启用防火墙
sudo ufw enable

# 查看状态
sudo ufw status
```

---

## 5. 连接到服务器

### 5.1 使用 SSH 连接（Windows PowerShell）

```powershell
ssh -i "C:\Users\你的用户名\.ssh\id_ed25519" ubuntu@你的服务器IP
```

例如：
```powershell
ssh -i "C:\Users\神魂之人\.ssh\id_ed25519" ubuntu@152.67.1.100
```

### 5.2 首次连接

1. 首次连接会提示 `Are you sure you want to continue connecting?`
2. 输入 `yes` 并回车
3. 成功登录后会看到服务器命令行

### 5.3 测试连接

登录后运行以下命令测试：

```bash
# 查看系统信息
uname -a

# 查看 CPU 和内存
nproc
free -h

# 查看磁盘空间
df -h

# 查看 IP 地址
ip addr show
```

---

## 6. 部署 Nuotao AI OS

### 6.1 系统初始化

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装必要工具
sudo apt install -y git curl wget vim unzip

# 安装 Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 将当前用户加入 docker 组
sudo usermod -aG docker $USER

# 重新登录使组生效
exit
# 重新 SSH 连接

# 验证 Docker 安装
docker --version
docker compose version
```

### 6.2 克隆项目代码

```bash
# 创建项目目录
sudo mkdir -p /opt/nuotao-ai-os
sudo chown $USER:$USER /opt/nuotao-ai-os

# 克隆代码（如果代码在 GitHub）
cd /opt/nuotao-ai-os
git clone https://github.com/你的用户名/nuotao-ai-os.git .

# 如果代码不在 GitHub，可以通过 SCP 上传
# 在本地 PowerShell 运行：
# scp -i "C:\Users\你的用户名\.ssh\id_ed25519" -r E:\AI\nuotao-ai-os\* ubuntu@你的服务器IP:/opt/nuotao-ai-os/
```

### 6.3 配置环境变量

```bash
cd /opt/nuotao-ai-os

# 复制环境变量模板
cp .env.production.example .env

# 编辑环境变量
nano .env
```

**必须修改的配置项**：

```env
# 应用配置
APP_ENV=production
APP_SECRET_KEY=用 openssl rand -hex 32 生成

# 数据库配置
POSTGRES_PASSWORD=设置一个强密码
POSTGRES_USER=nuotao
POSTGRES_DB=nuotao

# Redis 配置
REDIS_PASSWORD=设置一个强密码

# LLM 配置
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-你的DeepSeek API Key

# WooCommerce 配置
WOOCOMMERCE_BASE_URL=https://nuotaooutdoor.com
WOOCOMMERCE_CONSUMER_KEY=ck_你的Consumer Key
WOOCOMMERCE_CONSUMER_SECRET=cs_你的Consumer Secret

# 飞书告警配置
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/你的飞书Webhook

# 域名配置
DOMAIN=你的域名（如 nuotao-ai-os.com）
SSL_EMAIL=你的邮箱
```

生成密钥：
```bash
openssl rand -hex 32
```

### 6.4 启动应用

```bash
cd /opt/nuotao-ai-os

# 构建并启动所有服务
docker compose -f docker-compose.prod.yml up -d --build

# 查看服务状态
docker compose -f docker-compose.prod.yml ps

# 查看日志
docker compose -f docker-compose.prod.yml logs -f
```

### 6.5 验证部署

```bash
# 健康检查
curl http://localhost:8000/api/v1/healthz

# 查看产品
curl http://localhost:8000/api/v1/products

# 查看指标
curl http://localhost:8000/metrics | head -20
```

### 6.6 配置域名和 SSL（可选）

如果你有域名：

1. 在域名管理面板添加 A 记录，指向服务器 IP
2. 等待 DNS 生效
3. 申请 SSL 证书：

```bash
# 安装 Certbot
sudo apt install -y certbot

# 申请证书
sudo certbot certonly --standalone -d 你的域名 -d www.你的域名

# 证书会保存在 /etc/letsencrypt/live/你的域名/
```

4. 配置 Nginx 使用 SSL（参考 `infra/nginx/nginx.conf`）

### 6.7 访问应用

部署完成后，可以通过以下地址访问：

| 服务 | 地址 |
|---|---|
| 前端 | `http://你的服务器IP` 或 `https://你的域名` |
| API 文档 | `http://你的服务器IP/docs` |
| Grafana | `http://你的服务器IP:3000`（默认 admin/admin） |
| Prometheus | `http://你的服务器IP:9090` |
| Alertmanager | `http://你的服务器IP:9093` |

---

## 7. 常见问题解答

### Q1: 注册时被拒绝怎么办？

**可能原因和解决方案**：
1. **邮箱问题**: 尝试使用 Gmail/Outlook，不要用 QQ/163
2. **地址问题**: 尝试使用美国地址（可使用随机地址生成器）
3. **信用卡问题**: 确保信用卡支持国际支付，尝试不同的卡
4. **IP 问题**: 尝试使用代理，切换到美国 IP
5. **手机号问题**: 尝试使用 Google Voice 或其他虚拟号

如果多次被拒绝，可以考虑使用其他免费方案：
- AWS Free Tier（12个月免费）
- Google Cloud（$300 信用额度）
- 本地部署（零成本）

### Q2: 创建实例时提示 "Out of capacity" 怎么办？

**解决方案**：
1. 切换到不同的 Availability Domain（AD-1/AD-2/AD-3）
2. 切换到不同的 Region（如从 San Jose 切换到 Phoenix）
3. 降低配置（如从 4核24G 降到 2核12G）
4. 尝试不同的时间段创建（如凌晨）
5. 使用 x86 架构的 VM.Standard.E2.1.Micro（更容易创建）

### Q3: SSH 连接失败怎么办？

**检查清单**：
1. 安全列表是否开放 22 端口
2. 服务器防火墙是否开放 22 端口
3. SSH 密钥是否正确（私钥路径、权限）
4. 用户名是否正确（Ubuntu 是 `ubuntu`，Oracle Linux 是 `opc`）
5. 服务器 IP 是否正确
6. 服务器状态是否为 RUNNING

**测试命令**：
```bash
# 测试端口连通性
telnet 你的服务器IP 22

# 详细调试模式
ssh -v -i "私钥路径" ubuntu@你的服务器IP
```

### Q4: Docker 启动失败怎么办？

**常见原因**：
1. **内存不足**: 检查 `free -h`，确保有足够内存
2. **端口被占用**: 检查 `netstat -tlnp`，确保 80/443/8000 等端口未被占用
3. **权限问题**: 确保当前用户在 docker 组中
4. **配置错误**: 检查 `.env` 文件配置是否正确
5. **镜像拉取失败**: 检查网络连接，尝试配置 Docker 镜像加速器

**查看日志**：
```bash
# 查看所有服务日志
docker compose -f docker-compose.prod.yml logs

# 查看特定服务日志
docker compose -f docker-compose.prod.yml logs api
docker compose -f docker-compose.prod.yml logs postgres
```

### Q5: 如何备份数据？

**数据库备份**：
```bash
# 备份 PostgreSQL
docker compose -f docker-compose.prod.yml exec postgres pg_dump -U nuotao nuotao | gzip > backup_$(date +%Y%m%d).sql.gz

# 恢复
gunzip -c backup_20240101.sql.gz | docker compose -f docker-compose.prod.yml exec -T postgres psql -U nuotao nuotao
```

**配置文件备份**：
```bash
# 备份配置
tar -czf config_backup_$(date +%Y%m%d).tar.gz .env infra/
```

### Q6: 如何更新应用？

```bash
cd /opt/nuotao-ai-os

# 拉取最新代码
git pull

# 重新构建并启动
docker compose -f docker-compose.prod.yml up -d --build

# 查看状态
docker compose -f docker-compose.prod.yml ps
```

### Q7: 免费额度会被回收吗？

**Oracle Cloud 免费政策**：
- 永久免费实例（Always Free）不会被自动回收
- 但如果账户欠费或被判定为滥用，可能会被暂停
- 建议保持账户活跃，定期登录
- 重要数据定期备份

### Q8: 如何监控服务器资源？

```bash
# 查看系统资源
htop

# 查看 Docker 容器资源使用
docker stats

# 查看磁盘使用
df -h

# 查看内存使用
free -h

# 查看网络流量
iftop
```

---

## 📞 获取帮助

如果在注册或部署过程中遇到问题：

1. **Oracle Cloud 文档**: https://docs.oracle.com/en-us/iaas/Content/home.htm
2. **Oracle Cloud 社区**: https://community.oracle.com/c/cloud/
3. **Nuotao AI OS 项目文档**: `docs/` 目录
4. **飞书告警群**: 可以在群里提问

---

## ✅ 部署完成检查清单

- [ ] Oracle Cloud 账户注册成功
- [ ] 免费计算实例创建成功（状态 RUNNING）
- [ ] SSH 可以正常登录
- [ ] 安全列表开放 22/80/443 端口
- [ ] Docker 安装成功
- [ ] 项目代码已上传
- [ ] `.env` 配置已填写
- [ ] `docker compose up -d` 启动成功
- [ ] 所有服务状态正常
- [ ] 健康检查通过（`/api/v1/healthz`）
- [ ] 前端页面可以访问
- [ ] API 文档可以访问
- [ ] Grafana 可以访问
- [ ] 飞书告警测试成功

---

**祝你部署顺利！** 🚀
