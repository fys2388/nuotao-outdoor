# Staging 环境独立化方案

> 状态：配置模板已就绪，需在服务器上执行启用步骤。

## 当前状态

- `deploy.yml` 的 `stage-validate` job 在同一台服务器的 `/opt/nuotao/staging` 做 **dry-run**（rsync + alembic --sql + npm build），不启动服务
- 生产环境：后端 `:8000`、前端 `:8081`、systemd `nuotao-backend`
- 无独立 staging 服务，无法做真实流量验证

## 独立 Staging 架构

| 组件 | 生产 | Staging |
|------|------|---------|
| 代码目录 | `/opt/nuotao/` | `/opt/nuotao/staging/` |
| 后端端口 | `8000` | `8001` |
| 前端端口 | `8081` | `8082` |
| 前端目录 | `/var/www/nuotao/` | `/var/www/nuotao-staging/` |
| systemd 服务 | `nuotao-backend` | `nuotao-backend-staging` |
| nginx 配置 | `nuotao-console` | `nuotao-staging` |
| 数据库 | `nuotao`（生产） | `nuotao_staging`（独立库，从生产快照恢复） |
| .env | `/opt/nuotao/.env` | `/opt/nuotao/staging/.env`（端口+库名不同） |

## 启用步骤（服务器上执行）

### 1. 创建独立数据库

```bash
sudo -u postgres createdb nuotao_staging
# 从生产快照恢复（可选，用于真实数据验证）
PGPASSWORD=xxx pg_dump -h localhost -U nuotao nuotao | psql -h localhost -U nuotao nuotao_staging
```

### 2. 创建 staging .env

```bash
cp /opt/nuotao/.env /opt/nuotao/staging/.env
# 修改：DATABASE_URL 指向 nuotao_staging，端口保持 8001（uvicorn 命令行控制）
sed -i 's/nuotao$/nuotao_staging/' /opt/nuotao/staging/.env
```

### 3. 安装 staging systemd 服务

```bash
cp /opt/nuotao/infra/systemd/nuotao-backend-staging.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable nuotao-backend-staging
systemctl start nuotao-backend-staging
```

### 4. 部署 staging 前端

```bash
mkdir -p /var/www/nuotao-staging
cd /opt/nuotao/staging/frontend && npm install && npm run build
cp -r dist/* /var/www/nuotao-staging/
chown -R www-data:www-data /var/www/nuotao-staging
```

### 5. 安装 staging nginx 配置

```bash
cp /opt/nuotao/infra/nginx/staging-console.conf /etc/nginx/sites-available/nuotao-staging
ln -sf /etc/nginx/sites-available/nuotao-staging /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

### 6. 验证

```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8001/api/v1/readyz  # 应返回 200
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8082/                  # 应返回 200
```

## CI/CD 集成（后续）

启用独立 staging 后，可将 `deploy.yml` 的 `stage-validate` job 从 dry-run 升级为：
1. rsync 到 `/opt/nuotao/staging/`
2. alembic upgrade head（staging 库）
3. npm build → `/var/www/nuotao-staging/`
4. `systemctl restart nuotao-backend-staging`
5. 健康检查 `:8001/api/v1/readyz` + `:8082/`
6. 运行 smoke test（可选）
7. 通过后才触发 `deploy-production`

当前为降低风险，保持 dry-run 模式；模板就绪后可按需切换。

## 配置文件清单

- `infra/systemd/nuotao-backend-staging.service` — staging 后端 systemd 模板（端口 8001）
- `infra/nginx/staging-console.conf` — staging 前端 nginx 模板（端口 8082，API 代理到 8001）
- 本文档 — 启用步骤与架构说明
