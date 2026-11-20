# CMP 生产发布计划

**关联文档**：`CMP_STAGING_IMPLEMENTATION_REPORT.md`、`CMP_CONSENT_TEST_MATRIX.md`
**建议发布日期**：待 Owner 批准
**当前状态**：**PENDING_APPROVAL**（隔离环境验证通过，等待生产部署授权）

---

## 1. 发布范围

| 站点 | 是否发布 | 优先级 | 备注 |
|---|---|---|---|
| B2C `nuotaooutdoor.com` | ⏳ 待批准 | P1 | 主要流量，GDPR 合规硬约束 |
| B2B `b2b.nuotaooutdoor.com` | ⏳ 待批准 | P2 | 独立 WordPress，可同步或延后 |

---

## 2. 发布前检查清单

### 2.1 技术就绪

- [ ] Complianz 核心版在隔离环境测试全部通过 ✅（本报告已记录）
- [ ] Consent Mode v2 集成验证通过 ✅
- [ ] 真实 GA4 Measurement ID (`G-30GWC4FYMG`) 联调测试
- [ ] Meta Pixel / TikTok Pixel Consent 绑定测试
- [ ] 现有简单 banner Code Snippet 下线方案确认
- [ ] 回滚预案准备（一键恢复旧 banner）

### 2.2 法务/合规就绪

- [ ] Cookie 政策文案审核（德文 + 英文）
- [ ] Privacy Policy 更新
- [ ] DPA（Data Processing Agreement）签署（如使用 Complianz Pro）
- [ ] 同意凭证保留策略确认（≥ 存证期要求）

### 2.3 运营就绪

- [ ] 客服团队知晓新 consent 流程
- [ ] 数据团队知晓 GA4 事件变化
- [ ] 监控告警配置（consent 失败率 > 5% 告警）

---

## 3. 分阶段发布计划

### Phase 1: Staging 预发布（建议 T-7 天）

```
目标：在生产相似环境中完整验证
步骤：
1. 搭建 staging.nuotaooutdoor.com WordPress 实例
2. 安装 Complianz + 真实 GA4 对接
3. 运行 Compliance 自动化测试套件
4. 邀请内部团队 beta 测试
```

### Phase 2: B2C 生产灰度发布（建议 T-0）

```
目标：小流量验证，可控回滚
步骤：
1. 凌晨低峰时段发布（02:00-04:00 UTC+8）
2. 先对 /blog、/about 等非交易页面生效
3. 观察 24h：GA4 事件接收、错误率、用户反馈
4. 全量发布到所有页面
```

### Phase 3: B2B 同步/延后发布

```
选项 A（同步）：Phase 2 验证通过后立即推送 B2B 站
选项 B（延后）：等待 Phase 2 稳定运行 7 天后
决策依据：B2B 流量规模、合规紧迫度
```

---

## 4. 回滚预案

| 场景 | 回滚操作 | 预计时间 |
|---|---|---|
| Consent 阻塞正常交易 | 禁用 Complianz 插件，恢复旧 banner snippet | < 5 min |
| GA4 事件丢失 | 检查 Consent Mode 信号，调整默认值 | < 15 min |
| 性能退化 | 禁用 Complianz 自动脚本阻塞，改用手动注入 | < 10 min |
| 法律风险 | 暂停采集同意记录，保留现有简单 banner | < 5 min |

**回滚命令**：
```bash
# WordPress CLI
wp plugin deactivate complianz-cookie-consent
wp option update cmp_settings '{}'  # 清空配置
# 恢复旧 Code Snippet
# （具体 snippet 见 docs/cmp-rollout/old-banner-snippet.php）
```

---

## 5. 监控指标

| 指标 | 阈值 | 告警方式 |
|---|---|---|
| Consent 接受率 | < 30% → 关注 | Feishu 机器人 |
| GA4 Events 下降 | > 20% vs 基线 | Sentry alert |
| 结账页报错 | > 0.1% | PagerDuty |
| 用户反馈（客服）| > 5/天 | 每日摘要 |

---

## 6. Owner 审批项

请 Owner 明确批复以下事项后启动 Phase 1：

1. **是否批准 Phase 1 Staging 预发布？**
2. **B2C 发布窗口期建议（日期 + 时间段）**
3. **B2B 站是否同步发布，还是延后？**
4. **是否需要 Complianz Pro 版本？**
5. **法务审核进度如何？Cookie 政策文案是否就绪？**

---

*发布计划生成：2026-11-20，DSH 自治执行*
