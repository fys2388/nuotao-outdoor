# Nginx 配置模板

本目录存放 Nuotao AI OS 的 Nginx 站点配置模板，全部纳入版本管理。

## 文件说明

| 文件 | 用途 | 安装路径 |
|------|------|----------|
| `console.conf` | AI OS 控制台 SPA（:8081） | `/etc/nginx/sites-available/nuotao-console` |

## 使用规则

1. **禁止在服务器上手工修改 Nginx 配置**——配置漂移是历史故障根源。
2. 需要调整配置时：修改本目录模板 → PR → 合并 main → 由 `deploy.yml` 部署安装。
3. 部署时执行 `nginx -t` 校验通过后才 `systemctl reload nginx`，失败自动回滚。

## 安装步骤（deploy.yml 内自动化）

```bash
cp /opt/nuotao/infra/nginx/console.conf /etc/nginx/sites-available/nuotao-console
ln -sf /etc/nginx/sites-available/nuotao-console /etc/nginx/sites-enabled/nuotao-console
nginx -t && systemctl reload nginx
```
