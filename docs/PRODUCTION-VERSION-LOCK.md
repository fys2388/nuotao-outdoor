# 📌 生产版本锁定说明

**锁定时间**: 2026-09-27 01:47:35 UTC  
**版本标签**: `production-lock-20260927`  
**Git 分支**: `main`  
**提交哈希**: `8903f9fe7db8ddd5baccff703601546a4574031e`

---

## ⚠️ 重要提示

**这是生产环境基准版本，请勿随意修改！**

后期所有功能开发应基于此版本进行：
1. 从 `main` 分支创建新的功能分支
2. 在功能分支上开发和测试
3. 测试通过后合并回 `main` 分支
4. 重新部署前确认版本变更

---

## 🔒 版本保护

### 1. Git 标签保护
```bash
# 查看锁定标签
git tag -l 'production-lock-*'

# 查看标签详情
git show production-lock-20260927

# 强制回滚到锁定版本
git checkout production-lock-20260927
```

### 2. 部署保护
- 部署前确认分支: `git branch --show-current`
- 部署前确认提交: `git log --oneline -1`
- 部署前确认服务: `systemctl is-active nuotao-backend`

### 3. 备份保护
- 代码备份分支: `backup/production-20260911`
- 版本锁定文件: `/opt/nuotao/docs/production-version-lock.json`
- Nginx 配置备份: `/etc/nginx/sites-enabled/nuotao.bak`

---

## 📋 当前版本功能

### 后端服务
- **服务**: `nuotao-backend` (uvicorn, 2 workers)
- **端口**: 8000
- **状态**: active

### 前端应用
- **路径**: `/opt/nuotao/frontend/dist`
- **构建时间**: 2026-09-27 01:44:00 UTC
- **Nginx**: `/etc/nginx/sites-enabled/nuotao`

### 主要功能
- ✅ BUG #12: stats use meta.woocommerce_id fallback
- ✅ BUG #10: guard scan 1s interval
- ✅ WC sync stats show push/pull breakdown
- ✅ WC sync retry alert + OSS upload
- ✅ WC clickback events (impression/click/view/cart/purchase)

---

## 🚀 新功能开发流程

### 1. 创建功能分支
```bash
cd /opt/nuotao
git checkout main
git pull origin main
git checkout -b feat/your-feature-name
```

### 2. 开发测试
```bash
# 后端开发
cd /opt/nuotao/backend
pip install -e .
uvicorn app.main:app --reload

# 前端开发
cd /opt/nuotao/frontend
npm run dev
```

### 3. 部署到生产
```bash
# 确认分支
git checkout main
git merge feat/your-feature-name

# 重新构建前端
cd /opt/nuotao/frontend
npm run build

# 重启后端
systemctl restart nuotao-backend

# 验证部署
curl -s http://localhost:8000/api/v1/health
```

---

## 🔄 紧急回滚

如果部署出错，立即回滚到锁定版本：

```bash
cd /opt/nuotao

# 1. 回滚代码
git checkout main
git reset --hard 8903f9fe

# 2. 重新构建前端
cd /opt/nuotao/frontend
rm -rf dist
npm run build

# 3. 重启服务
systemctl restart nuotao-backend

# 4. 验证服务
systemctl is-active nuotao-backend
curl -s http://localhost:8000/api/v1/health
```

---

## 📞 联系信息

- **服务器**: 95.217.218.178
- **SSH 密钥**: ~/.ssh/id_ed25519_nuotao
- **Git 仓库**: /opt/nuotao
- **版本锁定文件**: /opt/nuotao/docs/production-version-lock.json

---

*最后更新: 2026-09-27 01:47:35 UTC*
