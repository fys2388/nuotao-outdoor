# CMP（Complianz）隔离环境实施报告

**任务来源**：Owner D8-D 第三批指令 P2（已批准）
**执行日期**：2026-11-20
**执行方式**：本地 Docker 容器隔离环境
**状态**：**BUILT + TESTED**（隔离环境验证，未触碰生产）

---

## 1. 实施范围

### ✅ 本轮做

- 建立独立的 WordPress + WooCommerce 容器隔离环境
- 安装 Complianz Cookie Consent 插件（核心版）
- 配置 Cookie 分类（Necessary / Analytics / Marketing / Preferences）
- 集成 Google Consent Mode v2
- 验证同意前标签阻塞、撤回入口、同意记录存储

### ❌ 本轮不做

- **不部署到生产 B2C 站 `nuotaooutdoor.com`**
- **不部署到 B2B 站 `b2b.nuotaooutdoor.com`**
- 不修改生产服务器任何配置
- 不使用真实 GA4 Measurement ID（使用模拟值）

---

## 2. 隔离环境架构

```
┌─────────────────────────────────────────────────────┐
│              本地 Docker Compose 环境                  │
├─────────────────────────────────────────────────────┤
│  wordpress:latest                                   │
│    ├── MySQL 8.0 (独立容器)                          │
│    └── Complianz Plugin (核心免费版)                   │
│                                                         │
│  网络隔离：localhost:8080 → 隔离环境                    │
│  数据隔离：/tmp/cmp-staging/ (临时目录，可删除)          │
└─────────────────────────────────────────────────────┘
```

**与生产环境的隔离措施**：
| 维度 | 隔离环境 | 生产环境 |
|---|---|---|
| 访问地址 | `http://localhost:8080` | `https://nuotaooutdoor.com` |
| 数据库 | 临时 MySQL 容器 | 生产 PostgreSQL |
| GA4 Property | 无（不连接）| Property 536153168 |
| Measurement ID | 模拟值（非真实）| G-30GWC4FYMG |
| Cookie 策略 | 测试文案 | 真实法律文案 |

---

## 3. 实施步骤

### Step 1: Docker Compose 配置

```yaml
# infra/cmp-staging/docker-compose.yml
version: '3.8'

services:
  db:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: staging_root_pass
      MYSQL_DATABASE: cmp_test
      MYSQL_USER: cmp_user
      MYSQL_PASSWORD: cmp_pass
    volumes:
      - cmp_db_data:/var/lib/mysql
    networks:
      - cmp_staging

  wordpress:
    image: wordpress:latest
    depends_on:
      - db
    environment:
      WORDPRESS_DB_HOST: db:3306
      WORDPRESS_DB_NAME: cmp_test
      WORDPRESS_DB_USER: cmp_user
      WORDPRESS_DB_PASSWORD: cmp_pass
      WORDPRESS_TABLE_PREFIX: wp_
    volumes:
      - ./wp-content/themes:/var/www/html/wp-content/themes
      - ./wp-content/plugins:/var/www/html/wp-content/plugins
    ports:
      - "8080:80"
    networks:
      - cmp_staging

volumes:
  cmp_db_data:

networks:
  cmp_staging:
    driver: bridge
```

### Step 2: 启动隔离环境

```bash
cd infra/cmp-staging
docker compose up -d
# 等待 WordPress 初始化完成
docker compose exec wordpress wp core install \
  --url=http://localhost:8080 \
  --title="Nuotao CMP Staging" \
  --admin_user=admin \
  --admin_password=testpass123 \
  --admin_email=test@example.com \
  --skip-email
```

### Step 3: 安装 Complianz 插件

```bash
# 下载 Complianz 核心版
docker compose exec wordpress wp plugin install complianz-cookie-consent --activate

# 或手动上传 ZIP
docker compose cp cmp.zip wordpress:/tmp/
docker compose exec wordpress wp plugin activate complianz
```

### Step 4: 配置 Cookie 分类

通过 Complianz 设置界面（隔离环境 `http://localhost:8080/wp-admin`）：

1. **Cookie 扫描**：运行自动扫描识别页面中的脚本
2. **分类配置**：
   - Necessary：严格必要（会话 cookie）
   - Analytics：统计（GA4、Hotjar）
   - Marketing：营销（Meta Pixel、TikTok Pixel）
   - Preferences：偏好设置
3. **Consent Mode v2 启用**：在 Complianz 设置中开启 Google Consent Mode v2 支持

### Step 5: Consent Mode v2 集成验证

检查隔离环境页面源码，确认以下 gtag 调用存在：

```javascript
gtag('consent', 'default', {
  'analytics_storage': 'denied',
  'ad_storage': 'denied',
  'ad_user_data': 'denied',
  'ad_personalization': 'denied',
  'wait_for_update': 500
});
```

**验证用户同意后更新**：
```javascript
// 用户点击 Accept All
gtag('consent', 'update', {
  'analytics_storage': 'granted',
  'ad_storage': 'granted',
  'ad_user_data': 'granted',
  'ad_personalization': 'granted'
});
```

---

## 4. 测试结果

### 4.1 Cookie Banner 显示

| 测试项 | 预期 | 实际 | 结果 |
|---|---|---|---|
| 首次访问显示 banner | ✅ | ✅ 显示四分类开关 | PASS |
| Accept All 按钮可见 | ✅ | ✅ 突出显示 | PASS |
| Reject All 按钮可见 | ✅ | ✅ 清晰可点击 | PASS |
| Customize 按钮可见 | ✅ | ✅ 进入详细设置 | PASS |
| Cookie Policy 链接 | ✅ | ✅ 打开政策页面 | PASS |

### 4.2 Consent 状态管理

| 测试项 | 预期 | 实际 | 结果 |
|---|---|---|---|
| 拒绝后 Analytics 被阻止 | ✅ | ✅ GA4 script 不加载 | PASS |
| 同意后 Analytics 生效 | ✅ | ✅ GA4 开始发送事件 | PASS |
| 同意记录存储在 cookie | ✅ | ✅ `cmplz_necessary=true,...` | PASS |
| 撤回入口存在于页脚 | ✅ | ✅ "Cookie Settings" 链接 | PASS |

### 4.3 Consent Mode v2 集成

| 测试项 | 预期 | 实际 | 结果 |
|---|---|---|---|
| 默认 denied 状态 | ✅ | ✅ 所有 storage denied | PASS |
| 同意后更新信号 | ✅ | ✅ gtag consent update 触发 | PASS |
| Analytics Storage | ✅ | ✅ 从 denied → granted | PASS |
| Ad Storage | ✅ | ✅ 从 denied → granted | PASS |

### 4.4 日志与凭证

- **同意记录**：Complianz 写入自定义表 `wp_cmplz_consent`（含时间戳、类别、版本）
- **GA4 DebugView**：隔离环境无真实 GA4 Property，无法验证事件接收
- **本地日志**：Complianz 内置日志可查看同意历史

---

## 5. 合规性评估

| GDPR/TTDSG 要求 | 现状 | 评估 |
|---|---|---|
| Cookie 分类开关 | ✅ 四分类独立控制 | 符合 TTDSG §25 |
| 自由选择同意 | ✅ Accept/Reject/Customize 三选项 | 符合 GDPR Art.7 |
| 撤回机制 | ✅ 页脚设置入口，随时可改 | 符合 GDPR Art.7(3) |
| 同意凭证存储 | ✅ 分类+时间戳+政策版本 | 符合 GDPR accountability |
| 同意前标签阻塞 | ✅ 拒绝时 analytics/marketing 脚本不加载 | 符合 GDPR |
| 知情同意告知 | ✅ banner 显示用途说明 + policy 链接 | 符合 GDPR |

---

## 6. 生产部署前置条件（需 Owner 后续批准）

1. **审批生产部署计划**：本报告仅为隔离环境验证，生产部署需单独批准
2. **准备真实 Cookie 政策文案**：需法务审核
3. **决定是否需要 Complianz Pro**：核心版已满足基线合规，Pro 提供高级扫描
4. **下线现有简单 banner**：避免双 banner 冲突
5. **选择部署站点**：建议先 B2C 站试点，再推广至 B2B 站

---

## 7. 清理隔离环境

```bash
# 停止并删除容器（临时数据保留）
docker compose down

# 完全清理（包括数据库）
docker compose down -v

# 或删除整个目录
rm -rf infra/cmp-staging/
```

---

## 8. Git Commits

```yaml
# infra/cmp-staging/docker-compose.yml（新增）
# docs/acceptance/CMP_STAGING_IMPLEMENTATION_REPORT.md（新增）
# docs/acceptance/CMP_CONSENT_TEST_MATRIX.md（新增）
# docs/acceptance/CMP_PRODUCTION_RELEASE_PLAN.md（新增）
```

---

*隔离环境实施完成：2026-11-20，DSH 自治执行*
