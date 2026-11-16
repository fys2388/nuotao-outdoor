# M3.35-01｜60 SKU 证据总账（Evidence Ledger）
**生成时间**：2026-11-16  
**阶段**：M3.35 — SKU Evidence Validation & Unit Economics  
**权限**：READ-ONLY + LOCAL MODEL + REPORT  
**基准**：M3.34-01~08 / M3.33.1-3
---
## 0. 诚实边界声明（先读）
> 1. **本总账不改变任何售价/库存/上下架状态**，不调用 WooCommerce API，不触碰生产。  
> 2. **估算数据绝不自动升级为 VERIFIED**：只有具备本地真实记录（1688 实价）的字段标 VERIFIED；重量/尺寸/HS/清关费/代垫费全部 MISSING 或 ESTIMATED（假设）。  
> 3. **严格 E 体系下，当前 60 SKU 无任何一个达到 E2**（E2 需实测净重+毛重+包装尺寸，而 0 个实测完成）。M3.34-01 曾标 'E2 18 个'，属**宽松口径**（有采购价依据即视为 E2 级），本报告按严格定义重估，并记录差异。  
> 4. **数据冲突保留**：M3.33.2-02 早期口径（采购价 真实18/区间5/估算37）与 M3.33.2-03 更新口径（A13/B11/C2/D34）不一致，本报告采用 **M3.33.2-03 更新口径**为主，差异记入 §7。
---
## 1. 证据状态定义
| 状态 | 含义 |
|---|---|
| VERIFIED | 具备本地真实记录（如 1688 实价、实测数据、正式函件） |
| ESTIMATED | 假设/区间/可核对但非定点（如品类估算、区间中值、假设费率） |
| MISSING | 无任何本地依据，需补证 |
| CONFLICTED | 数据源之间存在矛盾，保留原值待仲裁 |
---
## 2. 汇总统计
- SKU 总数：**60**
- 采购价证据：A 直接实价 13 / B 区间 11 / C 文档单一价 2 / D 品类估算 34（有本地依据 A+B+C = 26）
- 实测重量：**0 / 60**（全部为品类假设，M3.34-P2 进度 0/10）
- HTSUS 正式归类：**0 / 60**（全部无正式归类意见书，仅品类候选编码）
- 证据等级（严格 E 体系）：E1（有采购价记录）26 / E0（纯品类估算）34；**E2+：0**
- CAC、退货预留、头程/尾程/燃油费率：全部为**假设**（$15、12%、$2/kg、$5.5/$11、3.5%）
- 清关费 `customs_broker_fee` 与货代代垫费 `carrier_disbursement_fee`：**漏列，按 $0 处理**（M3.33.2-02）
---
## 3. 逐 SKU 证据总账（60 行）
| WC | 商品 | 采购价 | 采购证据 | 证据等级 | 重量kg | 重量状态 | HTSUS候选 | 关税 | 运费 | 清关/代垫 | CAC | 退货预留 | 缺失字段数 | 分类 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| #968 | 不锈钢保温瓶 | ¥35* ($4.86) | MISSING [D] D 品类估算（无本地记录） | E0 | 0.5* | MISSING(假设) | 9617/3924/8421 | 301 ~28%-29% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 走量潜力 |
| #957 | 折叠硅胶水壶 | ¥12* ($1.67) | MISSING [D] D 品类估算（无本地记录） | E0 | 0.15* | MISSING(假设) | 9617/3924/8421 | 301 ~28%-29% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 走量潜力 |
| #907 | 3L战术水袋背包 | ¥40* ($5.56) | ESTIMATED [C] C 文档记载单一价（无1688佐证） | E1 | 0.4* | MISSING(假设) | 4202.92 | 301适用 40%+ | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 走量潜力 |
| #917 | 月亮椅 | ¥60* ($8.33) | ESTIMATED [C] C 文档记载单一价（无1688佐证） | E1 | 1.2* | MISSING(假设) | 9401/9403 | 301未定(或0%) 0%~25% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 走量潜力 |
| #990 | 防水收纳袋套装6件 | ¥25* ($3.47) | ESTIMATED [B] B 区间取中值（1688实查区间） | E1 | 0.4* | MISSING(假设) | 6307/3923/3005 | 301(急救或0%) ~28%-32% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 走量潜力 |
| #991 | 迷你急救包100PCS | ¥25* ($3.47) | ESTIMATED [B] B 区间取中值（1688实查区间） | E1 | 0.4* | MISSING(假设) | 3005 | 301 0%~25% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 走量潜力 |
| #992 | 铝合金登山杖折叠5节 | ¥40* ($5.56) | ESTIMATED [B] B 区间取中值（1688实查区间） | E1 | 0.25* | MISSING(假设) | 9506/8203 | 301 ~29%-30% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 走量潜力 |
| #994 | 复古太阳能露营马灯 | ¥30* ($4.17) | MISSING [D] D 品类估算（无本地记录） | E0 | 0.5* | MISSING(假设) | 8513/9405 | 301 ~29%-31% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 走量潜力 |
| #995 | 便携卡式炉单头 | ¥35* ($4.86) | ESTIMATED [B] B 区间取中值（1688实查区间） | E1 | 0.5* | MISSING(假设) | 7615/7321 | 301 ~28%-29% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 走量潜力 |
| #996 | 10件套铝制锅具3-4人 | ¥120* ($16.67) | ESTIMATED [B] B 区间取中值（1688实查区间） | E1 | 2.0* | MISSING(假设) | 7615/7321 | 301 ~28%-29% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 走量潜力 |
| #997 | 40L徒步背包 | ¥110* ($15.28) | ESTIMATED [B] B 区间取中值（1688实查区间） | E1 | 0.9* | MISSING(假设) | 4202.92 | 301适用 40%+ | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 走量潜力 |
| #998 | 3-4人自动速开帐篷 | ¥150* ($20.83) | MISSING [D] D 品类估算（无本地记录） | E0 | 3.0* | MISSING(假设) | 6306/6304/6307 | 301 ~30%-32% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 证据待补齐 |
| #1009 | 信封式睡袋3季超轻 | ¥40 ($5.54) | VERIFIED [A] A 直接实价（本地实价记录） | E1 | 0.8* | MISSING(假设) | 9404/6114 | 301 ~29%-35% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 8 | 明星商品 |
| #1010 | 自充气睡垫带枕 | ¥27 ($3.68) | VERIFIED [A] A 直接实价（本地实价记录） | E1 | 1.0* | MISSING(假设) | 9404/9506 | 歧义 0%~29% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 8 | 证据待补齐 |
| #1011 | 3x3m涂银天幕含杆 | ¥59 ($8.19) | ESTIMATED [B] B 区间取中值（1688实查区间） | E1 | 2.5* | MISSING(假设) | 6306/6304/6307 | 301 ~30%-32% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 明星商品 |
| #1012 | 铝合金折叠蛋卷桌 | ¥45 ($6.25) | VERIFIED [A] A 直接实价（本地实价记录） | E1 | 2.5* | MISSING(假设) | 9401/9403 | 301未定(或0%) 0%~25% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 8 | 证据待补齐 |
| #1013 | 35L折叠收纳箱木盖 | ¥25 ($3.42) | VERIFIED [A] A 直接实价（本地实价记录） | E1 | 1.5* | MISSING(假设) | 6307/3923/3005 | 301(急救或0%) ~28%-32% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 8 | STOP_CANDIDATE |
| #1014 | 不锈钢折叠烧烤架 | ¥30 ($4.17) | VERIFIED [A] A 直接实价（本地实价记录） | E1 | 1.8* | MISSING(假设) | 7615/7321 | 301 ~28%-29% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 8 | STOP_CANDIDATE |
| #1021 | USB-C感应头灯 | ¥22 ($3.12) | VERIFIED [A] A 直接实价（本地实价记录） | E1 | 0.15* | MISSING(假设) | 8513/9405 | 301 ~29%-31% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 8 | 明星商品 |
| #1022 | 便携净水壶 | ¥36 ($5.01) | VERIFIED [A] A 直接实价（本地实价记录） | E1 | 0.3* | MISSING(假设) | 9617/3924/8421 | 301 ~28%-29% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 8 | 明星商品 |
| #1023 | 高背躺椅带腿托 | ¥21 ($2.97) | VERIFIED [A] A 直接实价（本地实价记录） | E1 | 1.8* | MISSING(假设) | 9401/9403 | 301未定(或0%) 0%~25% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 8 | 明星商品 |
| #1024 | 折叠餐具套装 | ¥5 ($0.71) | VERIFIED [A] A 直接实价（本地实价记录） | E1 | 0.3* | MISSING(假设) | 7615/7321 | 301 ~28%-29% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 8 | 明星商品 |
| #1025 | 露营防蚊帐 | ¥9 ($1.26) | VERIFIED [A] A 直接实价（本地实价记录） | E1 | 0.6* | MISSING(假设) | 6306/6304/6307 | 301 ~30%-32% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 8 | 明星商品 |
| #1030 | 3D海绵充气枕 | ¥16 ($2.22) | VERIFIED [A] A 直接实价（本地实价记录） | E1 | 0.15* | MISSING(假设) | 9404/9506 | 歧义 0%~29% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 8 | 明星商品 |
| #1031 | USB-C强光手电 | ¥18 ($2.49) | VERIFIED [A] A 直接实价（本地实价记录） | E1 | 0.15* | MISSING(假设) | 8513/9405 | 301 ~29%-31% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 8 | 明星商品 |
| #1032 | 铝合金行军床 | ¥168 ($23.33) | VERIFIED [A] A 直接实价（本地实价记录） | E1 | 3.0* | MISSING(假设) | 9401/9403 | 301未定(或0%) 0%~25% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 8 | 走量潜力 |
| #1425 | 户外手冲咖啡壶套装 | ¥50 ($6.94) | ESTIMATED [B] B 区间取中值（1688实查区间） | E1 | 0.6* | MISSING(假设) | 7615/7321 | 301 ~28%-29% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 明星商品 |
| #1426 | 露营LED氛围串灯 | ¥22 ($2.99) | ESTIMATED [B] B 区间取中值（1688实查区间） | E1 | 0.3* | MISSING(假设) | 8513/9405 | 301 ~29%-31% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 明星商品 |
| #1427 | 20L保温冷藏包 | ¥40 ($5.56) | ESTIMATED [B] B 区间取中值（1688实查区间） | E1 | 0.8* | MISSING(假设) | 4202.92 | 301适用 40%+ | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 明星商品 |
| #1428 | 露营地布2.5x2.5m | ¥22 ($2.99) | ESTIMATED [B] B 区间取中值（1688实查区间） | E1 | 0.8* | MISSING(假设) | 6306 | 301 ~30% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 证据待补齐 |
| #1474 | 钛合金折叠杯450ml | ¥55* ($7.64) | MISSING [D] D 品类估算（无本地记录） | E0 | 0.15* | MISSING(假设) | 8205/7615 | 301(材质歧义) ~28%-29% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 证据待补齐 |
| #1475 | 折叠硅胶碗2件套 | ¥15* ($2.08) | MISSING [D] D 品类估算（无本地记录） | E0 | 0.2* | MISSING(假设) | 7615/7321 | 301 ~28%-29% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 证据待补齐 |
| #1476 | 户外调料盒6格套装 | ¥15* ($2.08) | MISSING [D] D 品类估算（无本地记录） | E0 | 0.4* | MISSING(假设) | 6307/3923/3005 | 301(急救或0%) ~28%-32% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 证据待补齐 |
| #1477 | 折叠砧板带刀具 | ¥25* ($3.47) | MISSING [D] D 品类估算（无本地记录） | E0 | 0.5* | MISSING(假设) | 7615/7321 | 301 ~28%-29% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 证据待补齐 |
| #1478 | 10W太阳能充电板 | ¥70* ($9.72) | MISSING [D] D 品类估算（无本地记录） | E0 | 0.6* | MISSING(假设) | 8507/8541 | 电池/反倾销歧义 0%~28% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 证据待补齐 |
| #1479 | 1000流明营地主灯 | ¥45* ($6.25) | MISSING [D] D 品类估算（无本地记录） | E0 | 0.4* | MISSING(假设) | 8513/9405 | 301 ~29%-31% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 证据待补齐 |
| #1480 | 折叠露营灯杆 | ¥20* ($2.78) | MISSING [D] D 品类估算（无本地记录） | E0 | 0.5* | MISSING(假设) | 8513/9405 | 301 ~29%-31% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 证据待补齐 |
| #1481 | 户外收纳袋3件套 | ¥30* ($4.17) | MISSING [D] D 品类估算（无本地记录） | E0 | 0.4* | MISSING(假设) | 6307/3923/3005 | 301(急救或0%) ~28%-32% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 证据待补齐 |
| #1482 | 压缩收纳袋2件套 | ¥18* ($2.50) | MISSING [D] D 品类估算（无本地记录） | E0 | 0.3* | MISSING(假设) | 6307/3923/3005 | 301(急救或0%) ~28%-32% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 证据待补齐 |
| #1483 | 悬挂式洗漱包 | ¥20* ($2.78) | MISSING [D] D 品类估算（无本地记录） | E0 | 0.3* | MISSING(假设) | 6307/3923/3005 | 301(急救或0%) ~28%-32% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 证据待补齐 |
| #1484 | 抓绒睡袋内胆 | ¥35* ($4.86) | MISSING [D] D 品类估算（无本地记录） | E0 | 0.6* | MISSING(假设) | 9404/6114 | 301 ~29%-35% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 证据待补齐 |
| #1485 | 眼罩+耳塞套装 | ¥5* ($0.69) | MISSING [D] D 品类估算（无本地记录） | E0 | 0.05* | MISSING(假设) | 6307/3923/3005 | 301(急救或0%) ~28%-32% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 证据待补齐 |
| #1486 | 快速搭建沙滩遮阳棚 | ¥60* ($8.33) | MISSING [D] D 品类估算（无本地记录） | E0 | 1.8* | MISSING(假设) | 6306/6304/6307 | 301 ~30%-32% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 证据待补齐 |
| #1487 | 铝合金地钉8根套装 | ¥10* ($1.39) | MISSING [D] D 品类估算（无本地记录） | E0 | 0.3* | MISSING(假设) | 9506/8203 | 301 ~29%-30% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 证据待补齐 |
| #1488 | 户外腰包/胸包 | ¥30* ($4.17) | MISSING [D] D 品类估算（无本地记录） | E0 | 0.3* | MISSING(假设) | 4202.92 | 301适用 40%+ | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 证据待补齐 |
| #1489 | 背包防雨罩 | ¥12* ($1.67) | MISSING [D] D 品类估算（无本地记录） | E0 | 0.15* | MISSING(假设) | 4202.92 | 301适用 40%+ | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 证据待补齐 |
| #1490 | 多功能折叠工具钳 | ¥35* ($4.86) | MISSING [D] D 品类估算（无本地记录） | E0 | 0.3* | MISSING(假设) | 9506/8203 | 301 ~29%-30% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 证据待补齐 |
| #1491 | 反光风绳+地钉套装 | ¥12* ($1.67) | MISSING [D] D 品类估算（无本地记录） | E0 | 0.3* | MISSING(假设) | 9506/8203 | 301 ~29%-30% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 证据待补齐 |
| #1492 | 运动挤压水壶750ml | ¥15* ($2.08) | MISSING [D] D 品类估算（无本地记录） | E0 | 0.15* | MISSING(假设) | 9617/3924/8421 | 301 ~28%-29% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 证据待补齐 |
| #1493 | 咖啡保温杯350ml | ¥40* ($5.56) | MISSING [D] D 品类估算（无本地记录） | E0 | 0.4* | MISSING(假设) | 9617/3924/8421 | 301 ~28%-29% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 证据待补齐 |
| #1719 | 高端双人双层帐篷 | ¥360* ($50.00) | MISSING [D] D 品类估算（无本地记录） | E0 | 4.5* | MISSING(假设) | 6306/6304/6307 | 301 ~30%-32% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 证据待补齐 |
| #1720 | 650蓬羽绒睡袋-10C | ¥350* ($48.61) | MISSING [D] D 品类估算（无本地记录） | E0 | 1.8* | MISSING(假设) | 9404/6114 | 301 ~29%-35% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 证据待补齐 |
| #1721 | 一体式反应堆炉具 | ¥220* ($30.56) | MISSING [D] D 品类估算（无本地记录） | E0 | 0.8* | MISSING(假设) | 7615/7321 | 301 ~28%-29% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 证据待补齐 |
| #1722 | 55L重装徒步背包 | ¥280* ($38.89) | MISSING [D] D 品类估算（无本地记录） | E0 | 1.8* | MISSING(假设) | 4202.92 | 301适用 40%+ | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | RESTRUCTURE_CANDIDATE |
| #1723 | 纯钛炊具3件套 | ¥260* ($36.11) | MISSING [D] D 品类估算（无本地记录） | E0 | 0.7* | MISSING(假设) | 8205/7615 | 301(材质歧义) ~28%-29% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 证据待补齐 |
| #1724 | 100Wh便携储能电源 | ¥500* ($69.44) | MISSING [D] D 品类估算（无本地记录） | E0 | 1.2* | MISSING(假设) | 8507/8541 | 电池/反倾销歧义 0%~28% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 证据待补齐 |
| #1725 | 航空铝折叠桌 | ¥180* ($25.00) | MISSING [D] D 品类估算（无本地记录） | E0 | 3.0* | MISSING(假设) | 9401/9403 | 301未定(或0%) 0%~25% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 证据待补齐 |
| #1726 | 加大加厚高背椅 | ¥200* ($27.78) | MISSING [D] D 品类估算（无本地记录） | E0 | 3.5* | MISSING(假设) | 9401/9403 | 301未定(或0%) 0%~25% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 证据待补齐 |
| #1727 | 智能营地灯2000流明 | ¥160* ($22.22) | MISSING [D] D 品类估算（无本地记录） | E0 | 0.7* | MISSING(假设) | 8513/9405 | 301 ~29%-31% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 证据待补齐 |
| #1728 | 自充气睡垫R4.0 | ¥260* ($36.11) | MISSING [D] D 品类估算（无本地记录） | E0 | 1.5* | MISSING(假设) | 9404/9506 | 歧义 0%~29% | ESTIMATED($2/kg+$5.5/$11) | MISSING(按$0) | ESTIMATED | ESTIMATED | 9 | 证据待补齐 |
---
## 4. 证据等级差异记录（M3.34-01 vs M3.35-01 严格口径）
| 口径 | E0 | E1 | E2 | 说明 |
|---|---|---|---|---|
| M3.34-01（宽松） | 0 | 42 | 18 | 有采购价依据即视为 E2（重量为假设仍计 E2） |
| M3.35-01（严格） | 34 | 26 | **0** | E2 需实测净重+毛重+尺寸；当前 0 实测 |
> 差异根因：M3.34-01 将『有采购价+假设重量』乐观计为 E2；严格按 E0-E5 定义，E2 必须实测重量/尺寸，故重估为 0。保留 M3.34-01 原始分级作为历史记录。
---
## 5. 逐 SKU 缺失字段清单（节选：每 SKU 缺失项）
- **#968 不锈钢保温瓶**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#957 折叠硅胶水壶**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#907 3L战术水袋背包**（E1）：实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 1688供应商佐证; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#917 月亮椅**（E1）：实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 1688供应商佐证; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#990 防水收纳袋套装6件**（E1）：实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 供应商定点确认; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#991 迷你急救包100PCS**（E1）：实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 供应商定点确认; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#992 铝合金登山杖折叠5节**（E1）：实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 供应商定点确认; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#994 复古太阳能露营马灯**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#995 便携卡式炉单头**（E1）：实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 供应商定点确认; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#996 10件套铝制锅具3-4人**（E1）：实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 供应商定点确认; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#997 40L徒步背包**（E1）：实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 供应商定点确认; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#998 3-4人自动速开帐篷**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1009 信封式睡袋3季超轻**（E1）：实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1010 自充气睡垫带枕**（E1）：实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1011 3x3m涂银天幕含杆**（E1）：实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 供应商定点确认; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1012 铝合金折叠蛋卷桌**（E1）：实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1013 35L折叠收纳箱木盖**（E1）：实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1014 不锈钢折叠烧烤架**（E1）：实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1021 USB-C感应头灯**（E1）：实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1022 便携净水壶**（E1）：实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1023 高背躺椅带腿托**（E1）：实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1024 折叠餐具套装**（E1）：实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1025 露营防蚊帐**（E1）：实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1030 3D海绵充气枕**（E1）：实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1031 USB-C强光手电**（E1）：实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1032 铝合金行军床**（E1）：实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1425 户外手冲咖啡壶套装**（E1）：实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 供应商定点确认; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1426 露营LED氛围串灯**（E1）：实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 供应商定点确认; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1427 20L保温冷藏包**（E1）：实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 供应商定点确认; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1428 露营地布2.5x2.5m**（E1）：实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 供应商定点确认; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1474 钛合金折叠杯450ml**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1475 折叠硅胶碗2件套**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1476 户外调料盒6格套装**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1477 折叠砧板带刀具**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1478 10W太阳能充电板**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1479 1000流明营地主灯**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1480 折叠露营灯杆**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1481 户外收纳袋3件套**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1482 压缩收纳袋2件套**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1483 悬挂式洗漱包**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1484 抓绒睡袋内胆**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1485 眼罩+耳塞套装**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1486 快速搭建沙滩遮阳棚**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1487 铝合金地钉8根套装**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1488 户外腰包/胸包**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1489 背包防雨罩**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1490 多功能折叠工具钳**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1491 反光风绳+地钉套装**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1492 运动挤压水壶750ml**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1493 咖啡保温杯350ml**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1719 高端双人双层帐篷**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1720 650蓬羽绒睡袋-10C**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1721 一体式反应堆炉具**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1722 55L重装徒步背包**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1723 纯钛炊具3件套**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1724 100Wh便携储能电源**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1725 航空铝折叠桌**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1726 加大加厚高背椅**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1727 智能营地灯2000流明**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
- **#1728 自充气睡垫R4.0**（E0）：真实采购价(1688定点); 实测净重; 实测毛重; 实测包装尺寸; HTSUS正式归类; customs_broker_fee; carrier_disbursement_fee; 真实头程/尾程/燃油费率; 真实退货率/CAC
---
*本报告为证据总账，不做定价建议；估算值一律不冒充真实。*
