# CMP Phase 1 Staging 阻塞清单（D8-E 第二轮 P1）

**执行日期**：2026-11-20
**调查方式**：Hostinger 控制面板实测 + 服务器 SSH 文件系统检查 + 生产站源码分析
**结论**：**BLOCKED（3 条可行路径，均需 Owner 决策）**

---

## 1. 当前环境事实（实测确认）

| 环境组件 | 实际位置 | 状态 |
|---|---|---|
| B2C WordPress `nuotaooutdoor.com` | **Hostinger 托管** | 运行中，WP 7.1.4 / PHP 8.3 / Hello Elementor |
| B2C 后端 FastAPI | Hetzner `95.217.218.178` uvicorn:8000 | 运行中 |
| B2B 站 `b2b.nuotaooutdoor.com` | Hostinger（独立 WP）| 待确认 |
| Hostinger 官方 staging 功能 | Hostinger 控制面板 → WordPress → 暂存 | **需升级套餐**（见 §2）|
| 服务器 Docker 环境 | Hetzner（docker v29.1.3）| 运行 scheduler/postgres/redis 生产容器 |
| CMP 隔离环境（Docker Compose）| — | 已清理，未持久化 |
| 本地 Docker | 开发机 | **不可用**（docker 命令未安装）|

### 1.1 生产 B2C 当前 consent 实现（实测源码）

```javascript
// 自研 banner（localStorage nuotao_consent_v2），非 Complianz
gtag('consent','default',{...all denied except security_storage...});
// 仅二元 Accept/Reject，无四分类、无撤回入口
```

✅ 生产已有 Consent Mode v2 默认值，但 **非 Complianz、不满足 GDPR 四分类**。

---

## 2. Hostinger staging 功能限制（P1 核心阻塞）

**实测**（Hostinger 控制面板 → 暂存 页面）：
> "您当前的套餐是 **Premium Web Hosting**。要继续创建暂存环境，**建议您升级您的套餐**。"

- 当前套餐：**Premium Web Hosting**（磁盘 20GB，节点 400K，网站 1/3）
- **官方 staging 功能：需升级套餐**（Business 及以上才含 staging）
- 升级涉及**付费** → 需 Owner 决策，且不可由 DSH 擅自执行

---

## 3. 三条可行路径（需 Owner 选择）

### 路径 A：升级 Hostinger 套餐（官方 staging）✅ 最干净
- **操作**：升级到含 staging 的套餐 → 用官方暂存功能复制生产 → 安装 Complianz
- **优点**：官方支持，一键复制生产，隔离最彻底
- **缺点**：**付费升级**，需 Owner 批准；升级后月费增加
- **风险**：低（官方隔离）

### 路径 B：Hostinger 手动子站 staging（免费，利用剩余网站位）🟡
- **操作**：利用套餐剩余 2 个网站位（当前 1/3）创建 `staging.nuotaooutdoor.com` 子域名 + 独立 WP 安装 → 安装 Complianz
- **优点**：不付费，隔离独立（独立 DB + 独立 WP）
- **缺点**：需手动配置子域名 DNS + WP 安装 + 插件；不自动同步生产数据
- **风险**：中（需手动操作，且子域名 DNS 在 Cloudflare）

### 路径 C：Hetzner Docker 隔离环境（已有基础）🟢
- **操作**：在 Hetzner 服务器用 Docker 起独立 WordPress + MySQL + Complianz（复用 CMP 实施报告的 docker-compose）
- **优点**：完全隔离，不触碰生产；已在 CMP_STAGING_IMPLEMENTATION_REPORT 验证过 8/8 测试
- **缺点**：需重新搭建（之前环境已清理）；不与生产 WP 同环境，兼容性验证有限
- **风险**：低（完全隔离）

---

## 4. 所需决策

| # | 决策项 | Owner 选项 |
|---|---|---|
| D1 | 选择 staging 路径 | A（升级付费）/ B（免费子站）/ C（Docker 隔离）|
| D2 | 是否批准升级 Hostinger 套餐 | 若选 A，需批准付费 |
| D3 | 生产 WP 21 个插件漏洞处理 | 优先修复（安全）或延后（staging 先行）|
| D4 | 生产 cookie banner 下线时机 | CMP 上线后替换自研 banner |

---

## 5. 关联安全发现

### 5.1 生产 WP 21 个插件漏洞（Hostinger 站点健康）

Hostinger 控制面板显示：
```
WordPress 版本: 7.1.4（可更新 7.1.5）
PHP 版本: 8.3
已激活主题: Hello Elementor 3.5.1
插件: 12 个（有更新）
漏洞: 21 检测到  ⚠️
```

**评估**：21 个插件漏洞需尽快核查；但**修复属于生产变更**，需 Owner 批准，不得在 CMP 阶段擅自动生产。

### 5.2 deploy.yml hotfix-env 硬编码机密（与 P0 审计 F2 一致）

`hotfix-env` job 硬编码生产 DB 密码 `UFMmchfTXuRk` + 1688 LOGIN_COOKIE → 已在 `D8_E_ROUND2_OWNER_INDEPENDENT_AUDIT.md` §3.2 记录，需 Owner 批准迁移 + 轮换。

---

## 6. 红线遵守

- ✅ 未触碰生产 B2C/B2B 站（仅只读 curl + 面板查看）
- ✅ 未创建任何订单/请求
- ✅ 未修改生产 GA4 / Secret / DB
- ✅ 未执行 Hostinger 套餐升级（需 Owner 批准）

---

*阻塞清单生成：2026-11-20，DSH 自治调查*
