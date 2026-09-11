# CI/CD 配置指南

## 概述

本项目使用 GitHub Actions 实现完整的 CI/CD 流水线，包括代码检查、测试、安全扫描、Docker 镜像构建和自动部署。

## 工作流文件

| 文件 | 触发条件 | 功能 |
|------|----------|------|
| `ci-cd.yml` | push / PR | 完整 CI/CD 流水线（后端 + 前端 + 安全 + Docker + 部署） |
| `deploy.yml` | 手动触发 | 手动部署到指定环境（staging / production） |
| `dependency-review.yml` | PR | 依赖漏洞审查 |

## CI 流水线阶段

### 1. 后端 CI (backend-ci)
- ✅ Python 3.12 环境
- ✅ Ruff 代码检查
- ✅ Ruff 格式检查
- ✅ Mypy 类型检查
- ✅ Bandit 安全扫描
- ✅ pip-audit 依赖漏洞扫描
- ✅ Pytest 单元测试 + 覆盖率
- ✅ Codecov 覆盖率上传

### 2. 前端 CI (frontend-ci)
- ✅ Node.js 20 环境
- ✅ ESLint 代码检查
- ✅ TypeScript 类型检查
- ✅ 生产构建
- ✅ 单元测试
- ✅ 构建产物上传

### 3. 安全扫描 (security-scan)
- ✅ Trivy 文件系统漏洞扫描
- ✅ TruffleHog 密钥泄露检测

### 4. Docker 镜像构建 (docker-build)
- ✅ 后端 Docker 镜像构建
- ✅ 推送到 GitHub Container Registry (GHCR)
- ✅ 镜像缓存加速

### 5. 自动部署 (deploy)
- ✅ SSH 连接服务器
- ✅ Git 拉取最新代码
- ✅ Docker Compose 滚动更新
- ✅ 旧镜像清理

## 必需的 GitHub Secrets

在仓库 `Settings → Secrets and variables → Actions` 中配置以下 Secrets：

### 部署相关
| Secret 名称 | 说明 | 示例 |
|-------------|------|------|
| `SERVER_HOST` | 服务器 IP 地址或域名 | `192.168.1.100` |
| `SERVER_USER` | SSH 登录用户名 | `ubuntu` |
| `SERVER_PORT` | SSH 端口（可选，默认 22） | `22` |
| `SSH_PRIVATE_KEY` | SSH 私钥内容 | `-----BEGIN OPENSSH PRIVATE KEY-----...` |

### 代码质量相关
| Secret 名称 | 说明 | 可选 |
|-------------|------|------|
| `CODECOV_TOKEN` | Codecov 覆盖率报告 Token | ✅ |

### 环境保护规则
在 `Settings → Environments` 中创建：
- `staging` - 预发布环境
- `production` - 生产环境（建议启用审批保护）

## 本地验证

在提交代码前，建议本地运行以下检查：

```bash
# 后端
cd backend
ruff check .
ruff format --check .
pytest

# 前端
cd frontend
npm run lint
npm run build
npm run test
```

## 部署流程

### 自动部署
1. 代码合并到 `main` 分支
2. CI 流水线自动运行
3. 所有检查通过后自动构建 Docker 镜像
4. 自动部署到生产环境

### 手动部署
1. 进入仓库 `Actions` 页面
2. 选择 `Manual Deploy` 工作流
3. 点击 `Run workflow`
4. 选择环境（staging / production）
5. 可选输入版本号
6. 点击 `Run workflow` 开始部署

## 服务器准备

在部署前，服务器需要：

1. 安装 Docker 和 Docker Compose
2. 创建部署目录 `/opt/nuotao-ai-os`
3. 配置 SSH 密钥认证
4. 配置环境变量文件 `.env.production`
5. 开放必要端口（80, 443, 5432, 6379 等）

## 回滚策略

如果部署失败：

```bash
# 在服务器上执行
cd /opt/nuotao-ai-os

# 回滚到上一个版本
git reset --hard HEAD~1

# 重新启动
docker compose -f docker-compose.prod.yml up -d
```

## 监控和告警

部署后配置：
- Grafana 仪表盘监控系统指标
- Alertmanager 告警通知（飞书/邮件）
- Prometheus 指标采集
- 应用健康检查端点 `/api/v1/healthz`
