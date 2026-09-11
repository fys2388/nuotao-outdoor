# 性能优化指南

## 概述

本指南涵盖 Nuotao AI OS 项目的全栈性能优化措施，包括前端、后端、数据库、Nginx 和 CDN 配置。

## 一、前端性能优化

### 1.1 构建优化

**已配置（vite.config.ts）：**
- ✅ 代码分割（manualChunks）：React、UI、图表、工具库分离
- ✅ Terser 压缩：移除 console、debugger、注释
- ✅ 资源哈希：文件名带内容哈希，支持长期缓存
- ✅ 资源分类：图片、字体、CSS、JS 分目录存储
- ✅ 小资源内联：小于 4kb 的资源内联减少请求
- ✅ 依赖预构建：optimizeDeps 预构建常用库
- ✅ 打包分析：rollup-plugin-visualizer 生成体积报告

### 1.2 运行时优化

**建议实施：**
- 路由懒加载：`React.lazy()` + `Suspense`
- 组件懒加载：大组件按需加载
- 图片优化：WebP/AVIF 格式、懒加载、响应式图片
- 虚拟列表：长列表使用 `react-window`
- 防抖节流：搜索、滚动等高频操作
- 状态管理优化：避免不必要的重渲染
- Service Worker：离线缓存（PWA）

### 1.3 网络优化

- HTTP/2：多路复用
- 预连接：`<link rel="preconnect">`
- 预加载：`<link rel="preload">`
- DNS 预解析：`<link rel="dns-prefetch">`

## 二、后端性能优化

### 2.1 缓存策略

**已配置（app/core/performance.py）：**
- ✅ Redis 缓存装饰器：`@cache(ttl=300)`
- ✅ 缓存失效装饰器：`@invalidate_cache(["products:*"])`
- ✅ API 响应缓存：Nginx 层缓存 GET 请求
- ✅ 静态资源缓存：7 天缓存，不可变资源 1 年

**缓存层级：**
```
浏览器缓存 → CDN 缓存 → Nginx 缓存 → Redis 缓存 → 数据库
```

### 2.2 数据库优化

**连接池配置（已配置）：**
- 连接池大小：20
- 最大溢出：10
- 连接回收：3600 秒
- 连接前 ping：启用
- 获取超时：30 秒

**索引优化建议：**
```sql
-- 产品表
CREATE INDEX idx_products_sku ON products(sku);
CREATE INDEX idx_products_category ON products(category_id);
CREATE INDEX idx_products_status ON products(status);
CREATE INDEX idx_products_created_at ON products(created_at DESC);

-- 订单表
CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_created_at ON orders(created_at DESC);
CREATE INDEX idx_orders_total ON orders(total DESC);

-- 客户表
CREATE INDEX idx_customers_email ON customers(email);
CREATE INDEX idx_customers_phone ON customers(phone);
CREATE INDEX idx_customers_created_at ON customers(created_at DESC);
```

**查询优化：**
- 使用 `selectinload` 替代 N+1 查询
- 分页查询：`limit` + `offset` 或游标分页
- 只查询需要的字段
- 避免在循环中查询数据库

### 2.3 异步优化

- ✅ 全异步：FastAPI + SQLAlchemy 异步 + Redis 异步
- ✅ 并发处理：asyncio.gather 并行执行独立任务
- ✅ 后台任务：FastAPI BackgroundTasks
- ✅ 任务队列：Celery / RQ 处理耗时任务

### 2.4 限流与保护

**已配置：**
- ✅ 请求限流：基于 IP 的限流（100 req/s）
- ✅ 连接限制：每 IP 50 个连接
- ✅ 超时控制：连接 30s、发送 60s、读取 120s
- ✅ 熔断降级：外部服务不可用时降级

## 三、Nginx 性能优化

### 3.1 已配置（infra/nginx/nginx.conf）

- ✅ Gzip 压缩：6 级压缩，覆盖所有文本类型
- ✅ HTTP/2：多路复用、头部压缩
- ✅ 静态资源缓存：7 天 + 不可变资源 1 年
- ✅ API 缓存：GET 请求 1 分钟缓存
- ✅ 反向代理：后端负载均衡
- ✅ Keepalive：上游连接复用
- ✅ 安全头：HSTS、CSP、X-Frame-Options 等
- ✅ SSL 优化：TLS 1.2/1.3、OCSP Stapling
- ✅ 限流：API 100 req/s、通用 50 req/s
- ✅ 日志缓冲：减少磁盘 I/O

### 3.2 Brotli 压缩（可选）

需要编译 `ngx_brotli` 模块：
```nginx
brotli on;
brotli_comp_level 6;
brotli_types text/plain text/css application/json application/javascript;
```

## 四、CDN 配置

### 4.1 推荐 CDN 服务商

| 服务商 | 优势 | 适用场景 |
|--------|------|----------|
| Cloudflare | 免费套餐强大、全球节点多 | 静态资源、安全防护 |
| AWS CloudFront | 与 AWS 生态集成 | 全球分发、低延迟 |
| Akamai | 企业级、节点最多 | 大规模、高要求 |
| 阿里云 CDN | 国内节点多、备案友好 | 国内访问优化 |

### 4.2 Cloudflare 配置建议

**缓存规则：**
- 静态资源（js/css/images/fonts）：缓存 1 年
- HTML 页面：不缓存或短缓存
- API 响应：根据业务决定，通常不缓存

**性能功能：**
- ✅ Auto Minify：压缩 HTML/CSS/JS
- ✅ Brotli：启用 Brotli 压缩
- ✅ Rocket Loader：异步加载 JS
- ✅ Mirage：移动端图片优化
- ✅ Polish：图片优化（WebP/AVIF）
- ✅ Argo Smart Routing：智能路由
- ✅ HTTP/2 / HTTP/3 (QUIC)

**安全功能：**
- ✅ WAF：Web 应用防火墙
- ✅ DDoS 防护
- ✅ Bot 管理
- ✅ SSL/TLS：Full (strict)

## 五、监控与调优

### 5.1 性能指标

**前端指标：**
- LCP (Largest Contentful Paint)：< 2.5s
- FID (First Input Delay)：< 100ms
- CLS (Cumulative Layout Shift)：< 0.1
- TTFB (Time to First Byte)：< 200ms

**后端指标：**
- 响应时间：P50 < 100ms，P95 < 500ms，P99 < 1s
- 吞吐量：> 1000 req/s
- 错误率：< 0.1%
- 数据库查询时间：< 50ms

### 5.2 监控工具

- ✅ Prometheus：指标采集
- ✅ Grafana：可视化仪表盘
- ✅ Alertmanager：告警通知（飞书）
- ✅ Sentry：错误追踪
- ✅ Lighthouse：前端性能审计
- ✅ New Relic / Datadog：APM（可选）

### 5.3 压测工具

```bash
# wrk - HTTP 压测
wrk -t4 -c100 -d30s http://localhost:8000/api/v1/healthz

# k6 - 现代压测工具
k6 run --vus 100 --duration 30s script.js

# Apache Bench
ab -n 10000 -c 100 http://localhost:8000/api/v1/healthz
```

## 六、部署检查清单

- [ ] Nginx Gzip 压缩已启用
- [ ] 静态资源缓存策略已配置
- [ ] API 缓存策略已配置
- [ ] 数据库连接池已优化
- [ ] Redis 缓存已启用
- [ ] 前端代码分割已配置
- [ ] 前端资源压缩已配置
- [ ] CDN 已配置并启用
- [ ] SSL/TLS 已配置
- [ ] 安全头已添加
- [ ] 请求限流已配置
- [ ] 监控告警已配置
- [ ] 压测已通过
- [ ] 性能指标达标

## 七、持续优化

1. **定期性能审计**：每月运行 Lighthouse 和压测
2. **监控告警**：设置性能阈值告警
3. **A/B 测试**：优化措施效果验证
4. **用户反馈**：收集真实用户体验数据
5. **技术债务**：定期清理和重构
