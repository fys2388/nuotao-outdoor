# 部署纪律规则（Deploy Discipline）

> 沉淀于 2026-09-24 Nuotao AI OS 前端误部署事故复盘。
> 触发场景：`/opt/nuotao/frontend` 本身是 git 仓库时，从本地 working tree `scp dist/` 上传，导致生产 dist 与服务器 git HEAD 分裂。

## 铁律 1：服务器是 git 仓库时，禁止本地 scp dist 上传

**判定**：`ssh <host> "cd <proj> && git rev-parse --is-inside-work-tree"` 返回 `true`。

**正确做法**：在服务器上直接 build，保证 dist 与 git HEAD 严格一致。

```bash
ssh root@<host>
cd /opt/nuotao/frontend
git rev-parse HEAD                    # 确认分支
git status --short                    # 工作树应干净
npm run build                         # 或 pnpm build
chmod 755 dist && chmod -R a+rX dist  # 修 nginx 可读
```

**错误做法（禁止）**：
```bash
# ❌ 禁止
scp -r frontend/dist/* root@host:/opt/nuotao/frontend/dist/
```

原因：本地 working tree 可能与服务器 git HEAD 不一致（本地未提交修改、本地不同分支、本地分支落后），scp 上传会把"幽灵 dist"送到生产，源码仓库却不知情。

## 铁律 2：部署前先"备份 + 确认"

```bash
TS=$(date +%Y%m%d%H%M%S)
cp -a /opt/nuotao/frontend/dist /opt/nuotao/frontend/dist.bak.$TS
# build
# 出问题立即回滚：
rm -rf /opt/nuotao/frontend/dist && mv /opt/nuotao/frontend/dist.bak.$TS /opt/nuotao/frontend/dist
```

## 铁律 3：dist 目录权限

- 目录：`755`（`rwxr-xr-x`）——否则 nginx `www-data` 进不去
- 文件：`644`（`r--r--r--`）
- 修复命令：`chmod 755 dist && chmod -R a+rX dist`

## 铁律 4：Cloudflare 边缘缓存

`/assets/*.js` 响应头是 `Cache-Control: public, max-age=31536000, immutable`（nginx 配置）。

- CDN 侧：Vite 每次 build 会重新 hash 文件名（`NewtonSourcing-<hash>.js`），新 build 后 index.html 引用新 hash，旧文件自然 404，无需手动 purge
- 浏览器侧：如果 index.html 已被浏览器 disk cache 命中，浏览器不会重新拿 index.html，就会一直请求旧 hash 文件
- **验证部署是否生效**：`curl -sI -H "Cache-Control: no-cache" https://<domain>/ | grep -i "last-modified"`，看 Last-Modified 时间戳

## 铁律 5：nginx 本地验证必须带 Host header

```bash
curl -sI -H 'Host: admin.nuotaooutdoor.com' http://127.0.0.1/assets/<file>.js
```

不带 Host 会路由到 default server（可能是 `b2b` 或 `listen 8081` 的 `root /var/www/nuotao`），得到误导性 404。

## 铁律 6：`/opt/nuotao/frontend/dist` vs `/var/www/nuotao`

- **`/opt/nuotao/frontend/dist`** 是 nginx `sites-enabled/nuotao` 的 root（生产）
- **`/var/www/nuotao`** 是 `listen 8081` 的 root（另一条独立入口，可能是 staging 或遗留）
- **`/opt/nuotao/staging/frontend/dist`** 是 staging 环境的 dist

三个位置不要混淆，scp 前 `grep root /etc/nginx/sites-enabled/nuotao` 确认。

## 事故复盘（2026-09-24）

**触发**：本地 `hotfix/listing-gate` 分支 build 的 dist 被 scp 上传覆盖 `/opt/nuotao/frontend/dist`。

**症状**：
- 生产 index.html 引用 `index-17pGboz7.js`（我本地 build 产物）
- 服务器 git HEAD 是 `8903f9f`（main），源码里 NewtonSourcing.tsx 调用 `POST /newton/sourcing/import`
- 我本地 build 的产物走 `POST /sourcing/candidates`（另一个 API 路径）
- 源码和 dist 分裂，两条 API 路径混在生产

**恢复**：
1. `cp -a dist dist.before-main-build`（备份错误产物）
2. `cd /opt/nuotao/frontend && npm run build`（用 main HEAD 源码重 build）
3. `chmod 755 dist && chmod -R a+rX dist`（修权限）
4. 公网 curl 验证：`index-Cs7hFBGw.js` 200，`NewtonSourcing-B9ge3PRJ.js` 200
5. 浏览器 disk cache 顽固 → 需用户手动清或换 session

**教训**：即便"两条路径都能工作"，源码和 dist 分裂也是灾难——下次 build 时任何源码改动都会让生产与仓库脱节，无法用 git bisect 定位问题。
