# Website P0/P1 Fix Plan — nuotaooutdoor.com

> 版本：v1.0 | 日期：2026-09-07 | 状态：执行中
> 依据：nuotao-website-audit.html 体检报告

## 修复范围

### P0 严重（必须修复）
| # | 问题 | 负责模块 | 验证标准 |
|---|------|----------|----------|
| 1 | 满$150免邮未生效 | WooCommerce配送 | 购物车≥$150美国地址运费$0 |
| 2 | 分类图/Hero图AI水印/1688图 | 视觉资产+Elementor | 全部图片无水印、无中文、实景级 |
| 3 | 页脚残缺 | Elementor页脚 | 含Shop/Help/Company/版权/支付图标 |
| 4 | 空分类与死链 | 分类+重定向 | 导航分类均有产品，旧链接301 |
| 5 | 结算条款链接指回自身 | WooCommerce页面设置 | Terms指向/terms-conditions/ |
| 6 | 安全维护（11项更新+版本泄露） | WordPress核心/插件 | 全部更新完成，generator meta移除 |

### P1 中等
| # | 问题 | 负责模块 |
|---|------|----------|
| 7 | SEO首页title/多余H1 | Rank Math |
| 8 | 商品无SKU/描述模板不统一 | 产品编辑 |
| 9 | PayPal Checkout评估 | 支付 |
| 10 | About/Contact地址不一致 | 页面内容 |
| 11 | jQuery迁移警告 | 主题/插件升级 |

### 品牌Logo与UI
- Logo优化：简约科技风，域名首字母/极简元素
- UI整体：hero布局、分类卡片、产品卡片、按钮、配色、间距、移动端

## 执行阶段

### Phase 1（并行）
- **视觉资产**：生成Logo + 6分类图 + Hero图 → 保存至 website-assets/
- **WordPress后端**：免邮配置、条款页、SEO、分类、安全、商品、品牌口径

### Phase 2（串行，依赖Phase 1产物）
- **Elementor前端**：上传图片、替换、页脚重做、UI优化

### Phase 3
- **全量检验**：逐项实测，输出检验报告

## 回滚策略
- 修改前通过WordPress后台或插件完成全站备份
- 图片替换保留原图，不删除媒体库文件
- 配置变更可在对应设置页手动还原
